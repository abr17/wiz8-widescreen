"""Seamless pre-made stretched UI images (2026-10-16).
With brightness turned up, the owner saw seams where the UI is stretched by repeating
an image slice (DrawCatalogImageWide): the pattern breaks off at the joints.
Here the middle of width 2*ox is quilted from vertical strips of the image itself
(from the same slice [cut_left, cut_right)), each strip full height - rows are not
shifted, all horizontal lines and frames stay in place. The strips
overlap, and the boundary between them follows the minimum-difference line (as in
image quilting, Efros-Freeman), so there is no straight seam. The middle is joined
to the left part of the image and to the right part (which moves by 2*ox in the game) the same way.

python -I stretch_quilt.py <config.json> <out_dir> [--only S087_0_0,...] [--preview DIR]
config.json: [{"key": "S087_0_0", "sti": "path to the extracted STI", "image": 0,
               "width": 384, "cut": [152, 249]}, ...]
  width/cut - in DrawCatalogImageWide call coordinates (from the draw point, including
  the image offset within the frame). Writes <out_dir>/<key>_768.sti and _856.sti
  (16-bit W x 480, strip at x [0, width + 2*ox), y from 0; 0 = transparent)."""
import argparse
import json
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
import artkit  # noqa: E402
from sti8 import read_sti8  # noqa: E402

TEMPLATE = r'C:\dev\wiz8-ws\assets\Data\WIDE\WIDEFRAME_%d.STI'
NONE = (-60, -60, -60)  # transparent pixel in comparisons


def encode(p):
    if p is None:
        return 0
    r, g, b = p
    # like make_lock_niche.encode: green survives 565 -> 555, and is never 0
    return ((r >> 3) << 11) | (min(63, 2 * (g >> 3) + 1) << 5) | (b >> 3)


def column_cost(a, b):
    """a, b - columns (lists of pixels); per-row difference."""
    out = []
    for p, q in zip(a, b):
        p = NONE if p is None else p
        q = NONE if q is None else q
        out.append((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)
    return out


def min_cut(err_cols):
    """err_cols[i][y] - error in overlap column i, row y. Returns, for
    each row, the column index from which the new part is taken (the old part is to the left)."""
    n = len(err_cols)
    h = len(err_cols[0])
    cost = [[err_cols[i][0] for i in range(n)]]
    back = []
    for y in range(1, h):
        prev = cost[-1]
        row, br = [], []
        for i in range(n):
            best = min(range(max(0, i - 1), min(n, i + 2)), key=lambda k: prev[k])
            row.append(prev[best] + err_cols[i][y])
            br.append(best)
        cost.append(row)
        back.append(br)
    i = min(range(n), key=lambda k: cost[-1][k])
    path = [0] * h
    for y in range(h - 1, -1, -1):
        path[y] = i
        if y:
            i = back[y - 1][i]
    return path


def source_band(cols, cut_left, cut_right, width):
    """Wider than the slice: neighboring columns whose vertical brightness profile resembles the
    slice itself (same frame top/bottom, same background) - more distinct pieces, less
    repeated pattern. Extends contiguously while the column is similar."""
    def prof(col):
        lum = [-20.0 if p is None else (p[0] + p[1] + p[2]) / 3.0 for p in col]
        h = len(lum)
        return [sum(lum[max(0, y - 2):y + 3]) / len(lum[max(0, y - 2):y + 3]) for y in range(h)]
    profs = [prof(c) for c in cols]
    h = len(profs[0])
    ref = [sum(profs[x][y] for x in range(cut_left, cut_right)) / (cut_right - cut_left) for y in range(h)]
    dist = lambda x: sum(abs(profs[x][y] - ref[y]) for y in range(h)) / h
    lim = max(dist(x) for x in range(cut_left, cut_right)) * 1.25
    lo, hi = cut_left, cut_right
    while lo > 0 and dist(lo - 1) <= lim:
        lo -= 1
    while hi < width and dist(hi) <= lim:
        hi += 1
    return lo, hi


def build(orig_cols, width, cut_left, cut_right, ox2, rng, P, OV, src=None, period=0):
    """period > 0: the image pattern repeats exactly every period columns (the background
    of the log, options, saves - 97 px). Then a piece is taken only from the same place
    in the pattern as with plain slice repetition (shift is a multiple of period): the pattern grid
    is not broken, while different period copies and the cut line remove tone jumps."""
    src_lo, src_hi = src if src else (cut_left, cut_right)
    """orig_cols: image columns as in the 640 window (x 0..width). Returns
    the columns of a strip of width width + ox2."""
    h = len(orig_cols[0])
    out = [None] * (width + ox2)
    for c in range(cut_right):
        out[c] = list(orig_cols[c])
    # the right part + OV columns before it (its native continuation) are fixed
    right_from = cut_right + ox2
    for c in range(cut_right - OV, width):
        out[c + ox2] = list(orig_cols[c])
    fixed_left = right_from - OV  # from this column on - the fixed right block
    start = cut_right - OV
    end = fixed_left + OV  # the last piece overlaps the right block by OV
    span = end - start
    k = max(1, -(-(span - P) // (P - OV)) + 1)
    step = (span - P) / (k - 1) if k > 1 else 0
    positions = [int(round(start + i * step)) for i in range(k)]
    filled_to = cut_right  # out[start:filled_to) is already filled (left part)
    for idx, pos in enumerate(positions):
        last = idx == k - 1
        left_ov = list(range(pos, filled_to))
        right_ov = list(range(fixed_left, pos + P)) if last else []
        cands = []
        if period:
            g = cut_left + (pos - cut_right) % (cut_right - cut_left)
            starts = [s for s in range(src_lo, src_hi - P + 1) if (s - g) % period == 0]
            if not starts:
                starts = range(src_lo, src_hi - P + 1)
        else:
            starts = range(src_lo, src_hi - P + 1)
        for s in starts:
            e = 0
            for c in left_ov:
                e += sum(column_cost(out[c], orig_cols[s + c - pos]))
            for c in right_ov:
                e += sum(column_cost(out[c], orig_cols[s + c - pos]))
            cands.append((e, rng.random(), s))
        cands.sort()
        lim = cands[0][0] * 1.10 + 1
        pool = [t for t in cands if t[0] <= lim][:5]
        s = rng.choice(pool)[2]
        patch = {c: orig_cols[s + c - pos] for c in range(pos, pos + P)}
        # seam with what is on the left
        if left_ov:
            errs = [column_cost(out[c], patch[c]) for c in left_ov]
            path = min_cut(errs)
            for i, c in enumerate(left_ov):
                out[c] = [patch[c][y] if i >= path[y] else out[c][y] for y in range(h)]
        for c in range(filled_to, (fixed_left if last else pos + P)):
            out[c] = list(patch[c])
        # seam with the fixed right block
        if right_ov:
            errs = [column_cost(out[c], patch[c]) for c in right_ov]
            path = min_cut(errs)
            for i, c in enumerate(right_ov):
                out[c] = [patch[c][y] if i < path[y] else out[c][y] for y in range(h)]
        filled_to = pos + P
    assert all(col is not None for col in out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('config')
    ap.add_argument('out_dir')
    ap.add_argument('--only', default='')
    ap.add_argument('--preview', default='')
    ap.add_argument('--seed', type=int, default=3)
    a = ap.parse_args()
    items = json.load(open(a.config, encoding='utf-8'))
    only = set(filter(None, a.only.split(',')))
    os.makedirs(a.out_dir, exist_ok=True)
    for it in items:
        if only and it['key'] not in only:
            continue
        pal, frames = read_sti8(it['sti'])
        sx, sy, w, h, px = frames[it['image']]
        width = it['width']
        cut_left, cut_right = it['cut']
        rows = sy + h
        # image in call coordinates: x = sx + ix, y = sy + iy
        cols = [[None] * rows for _ in range(width)]
        for iy in range(h):
            for ix in range(w):
                v = px[iy][ix]
                if v is not None and 0 <= sx + ix < width:
                    cols[sx + ix][sy + iy] = pal[v]
        src = tuple(it['src']) if 'src' in it else source_band(cols, cut_left, cut_right, width)
        slice_w = src[1] - src[0]
        P = max(8, min(32, slice_w * 2 // 3))
        OV = max(3, P // 4)
        for W in (768, 856):
            ox2 = W - 640
            rng = random.Random(a.seed * 1000 + W)
            strip = build(cols, width, cut_left, cut_right, ox2, rng, P, OV, src, it.get('period', 0))
            sw = len(strip)
            canvas = [[0] * W for _ in range(480)]
            for c in range(min(sw, W)):
                for y in range(min(rows, 480)):
                    canvas[y][c] = encode(strip[c][y])
            head = bytearray(open(TEMPLATE % W, 'rb').read()[:64])
            assert struct.unpack_from('<HH', head, 20) == (480, W)
            data = struct.pack('<%dH' % (W * 480), *[v for row in canvas for v in row])
            open(os.path.join(a.out_dir, '%s_%d.sti' % (it['key'], W)), 'wb').write(bytes(head) + data)
            if a.preview:
                os.makedirs(a.preview, exist_ok=True)
                prev = [[(255, 0, 255) if strip[c][y] is None else strip[c][y] for c in range(sw)]
                        for y in range(rows)]
                artkit.write_png(os.path.join(a.preview, '%s_%d.png' % (it['key'], W)), sw, rows, prev, False)
        print('ok', it['key'], 'cut', cut_left, cut_right, 'source', src, 'P', P, 'OV', OV)


if __name__ == '__main__':
    main()
