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
  (16-bit W x 480, strip at x [0, width + 2*ox), y from 0; 0 = transparent).
  Optional keys: "src": [lo, hi) - columns the pieces are taken from (default: grown from the
  slice by source_band); "period": 97 - keep the background tile phase; and (2026-10-17, against
  one feature repeating side by side) "spread": true - pick pieces whose columns are shown as far
  away as possible; "detrend": true - remove the per-row horizontal light gradient (bevels) from
  moved pieces; "patch": [P, OV]; "avoid": [[lo, hi), ...] - source columns never used (a
  distinctive crack/blob); "guide": [images], "guide_part": i - quilt several images of the STI
  stacked so that their variants (normal/selected rows) get one and the same layout.
  Without the new keys the output is byte-identical to the 2026-10-16 version."""
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


def row_slopes(cols, lo, hi):
    """Per row and channel: slope of the least-squares line through the pixels of columns
    [lo, hi) (the horizontal light gradient of bevels and frames)."""
    h = len(cols[0])
    out = []
    for y in range(h):
        pts = [(x, cols[x][y]) for x in range(lo, hi) if cols[x][y] is not None]
        if len(pts) < 2:
            out.append((0.0, 0.0, 0.0))
            continue
        mx = sum(x for x, _ in pts) / len(pts)
        sxx = sum((x - mx) ** 2 for x, _ in pts)
        out.append(tuple(sum((x - mx) * p[ch] for x, p in pts) / sxx for ch in range(3)))
    return out


def detrended(cols, slopes, xt):
    """Columns as if each were at x = xt: the per-row linear trend is moved out, so a piece
    taken from the bright (or dark) end of a gradient fits at xt without a tone jump."""
    out = []
    for x, col in enumerate(cols):
        nc = []
        for p, sl in zip(col, slopes):
            if p is None:
                nc.append(None)
            else:
                nc.append(tuple(max(0, min(255, int(round(p[ch] + sl[ch] * (xt - x))))) for ch in range(3)))
        out.append(nc)
    return out


def build(orig_cols, width, cut_left, cut_right, ox2, rng, P, OV, src=None, period=0,
          spread=False, qcols=None, want_map=False, avoid=()):
    """period > 0: the image pattern repeats exactly every period columns (the background
    of the log, options, saves - 97 px). Then a piece is taken only from the same place
    in the pattern as the left part continues it (source = output column - n*period): the pattern grid
    is not broken, while different period copies and the cut line remove tone jumps.
    spread: choose pieces so that the same source columns are shown as far apart as possible
    (no feature repeating side by side); qcols: detrended columns for the quilted pieces
    (default - orig_cols); want_map: also return, per output column and row, (source column,
    taken from qcols?)."""
    src_lo, src_hi = src if src else (cut_left, cut_right)
    """orig_cols: image columns as in the 640 window (x 0..width). Returns
    the columns of a strip of width width + ox2."""
    if qcols is None:
        qcols = orig_cols
    h = len(orig_cols[0])
    out = [None] * (width + ox2)
    smap = [None] * (width + ox2)
    colsrc = {}  # output column -> source column shown there (for spread)
    for c in range(cut_right):
        out[c] = list(orig_cols[c])
        smap[c] = [(c, False)] * h
        colsrc[c] = c
    # the right part + OV columns before it (its native continuation) are fixed
    right_from = cut_right + ox2
    for c in range(cut_right - OV, width):
        out[c + ox2] = list(orig_cols[c])
        smap[c + ox2] = [(c, False)] * h
        colsrc[c + ox2] = c
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
        shown = {}  # source column -> output columns already showing it (for spread)
        if spread:
            for o, q in colsrc.items():
                shown.setdefault(q, []).append(o)
        if period:
            # same phase as the left part continued: (s - pos) % period == 0. For a slice of
            # exactly one period this is the old rule cut_left + (pos - cut_right) % period.
            starts = [s for s in range(src_lo, src_hi - P + 1) if (s - pos) % period == 0]
            if not starts:
                starts = range(src_lo, src_hi - P + 1)
        else:
            starts = range(src_lo, src_hi - P + 1)
        if avoid:
            # source columns with a distinctive mark that must not be repeated
            ok_starts = [s for s in starts if not any(s < b and a < s + P for a, b in avoid)]
            starts = ok_starts or starts
        for s in starts:
            e = 0
            for c in left_ov:
                e += sum(column_cost(out[c], qcols[s + c - pos]))
            for c in right_ov:
                e += sum(column_cost(out[c], qcols[s + c - pos]))
            if spread:
                # for each source column q of [s, s + P): distance (in output columns) to the
                # nearest place already showing q, capped at the source width; mean over q
                cap = src_hi - src_lo
                tot = 0
                for q in range(s, s + P):
                    d = min([abs(o - (pos + q - s)) for o in shown.get(q, ())] or [cap])
                    tot += min(d, cap)
                cands.append((e, rng.random(), s, tot / P))
            else:
                cands.append((e, rng.random(), s))
        if spread:
            rmax = max(t[3] for t in cands)
            ok = sorted(t for t in cands if t[3] >= 0.85 * rmax)
            lim = ok[0][0] * 1.25 + 1
            pool = [t for t in ok if t[0] <= lim][:6]
        else:
            cands.sort()
            lim = cands[0][0] * 1.10 + 1
            pool = [t for t in cands if t[0] <= lim][:5]
        s = rng.choice(pool)[2]
        patch = {c: qcols[s + c - pos] for c in range(pos, pos + P)}
        pmap = {c: [(s + c - pos, True)] * h for c in range(pos, pos + P)}
        # seam with what is on the left
        if left_ov:
            errs = [column_cost(out[c], patch[c]) for c in left_ov]
            path = min_cut(errs)
            for i, c in enumerate(left_ov):
                out[c] = [patch[c][y] if i >= path[y] else out[c][y] for y in range(h)]
                smap[c] = [pmap[c][y] if i >= path[y] else smap[c][y] for y in range(h)]
        for c in range(filled_to, (fixed_left if last else pos + P)):
            out[c] = list(patch[c])
            smap[c] = pmap[c]
            colsrc[c] = s + c - pos
        # seam with the fixed right block
        if right_ov:
            errs = [column_cost(out[c], patch[c]) for c in right_ov]
            path = min_cut(errs)
            for i, c in enumerate(right_ov):
                out[c] = [patch[c][y] if i < path[y] else out[c][y] for y in range(h)]
                smap[c] = [pmap[c][y] if i < path[y] else smap[c][y] for y in range(h)]
        filled_to = pos + P
    assert all(col is not None for col in out)
    if want_map:
        return out, smap
    return out


def narrower_map(strip, remove, lo, hi, OV=12):
    """The narrower strip (16:10) is cut out of the wider one (16:9), like the backgrounds:
    `remove` columns are taken out of the quilted middle [lo, hi) where the two remaining
    sides fit best, and the join is a min-cut line through an OV-column overlap. Returns
    (a, path): output column c of the narrow strip, row y, shows wide column
    c if c < a + path[y] (and c < a + OV), else c + remove."""
    h = len(strip[0])
    n = len(strip)
    # Removing columns also brings things closer together: two near-identical columns that
    # stood remove + d apart in the wide strip end up only d apart. With a pattern that
    # repeats every 97 px (log, options, saves) a careless cut leaves a 9-px "stutter" -
    # a crack or blot shown twice side by side (skeptic review, 2026-10-17). So every cut
    # position is first scored by the near-duplicate column pairs it creates (closer = worse),
    # and only among the least-repeating positions the best-fitting seam is chosen.
    D = 150
    full = [[(-1 if p is None else (p[0] * 3 + p[1] * 6 + p[2]) // 10) for p in col] for col in strip]
    # only textured rows count: flat rows (frame lines, black bands) match everywhere
    mid = range(max(0, lo - D), min(n, hi + remove))
    rows = []
    for y in range(h):
        vals = [full[x][y] for x in mid if full[x][y] >= 0]
        if len(vals) > 10:
            m = sum(vals) / len(vals)
            if sum((v - m) ** 2 for v in vals) / len(vals) > 16:
                rows.append(y)
    rows = rows[::max(1, len(rows) // 120)] or list(range(h))
    lum = [[col[y] for y in rows] for col in full]

    def similar(x, y):
        cx, cy = lum[x], lum[y]
        same = sum(1 for p, q in zip(cx, cy) if abs(p - q) <= 2)
        return same / len(cx)

    near = {}  # (x, d) -> similarity of wide columns x and x + remove + d, only if a near-duplicate
    for x in range(max(0, lo - D), min(n, hi)):
        for d in range(1, D + 1):
            y = x + remove + d
            if y >= n:
                break
            s = similar(x, y)
            if s >= 0.8:
                near[(x, d)] = s
    best = None
    cands = []
    for a in range(lo, hi - remove - OV + 1):
        # new pairs: x left of the cut, x + remove + d right of it (wide coordinates)
        pen = 0.0
        for (x, d), s in near.items():
            if x < a + OV and x + remove + d >= a + remove:
                pen += s * (3.0 if d < 30 else 1.0) / d
        errs = [column_cost(strip[a + k], strip[a + remove + k]) for k in range(OV)]
        path = min_cut(errs)
        # cost of the cut: the error right at the cut line (old part ends, new part starts)
        cost = 0
        for y in range(h):
            i = path[y]
            cost += errs[min(i, OV - 1)][y] + (errs[i - 1][y] if i > 0 else 0)
        cands.append((pen, cost, a, path))
    # Local check on the composed result (round 2 of the review): a duplicate only 10-15 rows
    # tall (a blot's lower lobe shown twice, 9 px apart) is diluted in whole-column scores.
    # For the most promising cuts, compare every column pair across the join (distance
    # 2..24) row by row, count only pixels with detail, and take the worst 10-row window.
    def detail(c, y):
        v = full[c][y]
        # horizontal detail only: horizontal lines (frames) match along x everywhere
        return v >= 0 and c > 0 and full[c - 1][y] >= 0 and abs(v - full[c - 1][y]) > 6

    def stutter(a, path):
        W, R = 24, 10
        lo_c, hi_c = max(0, a - W), min(n - remove, a + OV + W)
        src = []  # narrow column c -> wide column per row
        for c in range(lo_c, hi_c):
            if c < a:
                src.append([c] * h)
            elif c < a + OV:
                src.append([c if c - a < path[y] else c + remove for y in range(h)])
            else:
                src.append([c + remove] * h)
        worst = 0.0
        for i in range(len(src)):
            c = lo_c + i
            if c >= a + OV:
                break
            for d in range(2, W + 1):
                j = i + d
                if j >= len(src) or lo_c + j < a:
                    continue
                si, sj = src[i], src[j]
                if si == sj:
                    continue
                hits = [1 if (si[y] != sj[y] and detail(si[y], y) and
                              abs(full[si[y]][y] - full[sj[y]][y]) <= 2) else 0 for y in range(h)]
                run = sum(hits[:R])
                best_run = run
                for y in range(R, h):
                    run += hits[y] - hits[y - R]
                    if run > best_run:
                        best_run = run
                worst = max(worst, best_run / R)
        return worst

    cands.sort(key=lambda c: (c[0], c[1]))
    pmin = cands[0][0]
    pool = [c for c in cands if c[0] <= pmin * 1.15 + 0.02]
    pool += [c for c in cands if c not in pool][:max(0, 24 - len(pool))]
    scored = [(stutter(c[2], c[3]), c) for c in pool]
    clean = [sc for sc in scored if sc[0] < 0.6]
    if clean:
        st, best = min(clean, key=lambda sc: (sc[1][0] > pmin * 1.15 + 0.02, sc[1][1]))
    else:
        st, best = min(scored, key=lambda sc: sc[0])
    print('  cut at', best[2], 'repeat penalty', round(best[0], 3), '(min', round(pmin, 3), ')',
          'local double', round(st, 2))
    return best[2], best[3]


def apply_narrower(strip, remove, a, path, OV=12, row_off=0):
    """Narrow strip from the wide one with the cut found by narrower_map (path rows start at
    row_off: the guide stack may be taller than this image)."""
    h = len(strip[0])
    out = []
    for c in range(len(strip) - remove):
        if c < a:
            out.append(list(strip[c]))
        elif c < a + OV:
            k = c - a
            out.append([strip[c][y] if k < path[y + row_off] else strip[c + remove][y] for y in range(h)])
        else:
            out.append(list(strip[c + remove]))
    return out


def image_cols(it, image):
    """Image `image` of the item's STI in call coordinates: columns x 0..width, None = transparent."""
    pal, frames = read_sti8(it['sti'])
    sx, sy, w, h, px = frames[image]
    width = it['width']
    rows = sy + h
    cols = [[None] * rows for _ in range(width)]
    for iy in range(h):
        for ix in range(w):
            v = px[iy][ix]
            if v is not None and 0 <= sx + ix < width:
                cols[sx + ix][sy + iy] = pal[v]
    return cols


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
        # optional (2026-10-17): "guide" - images of the same STI quilted together (stacked
        # vertically) so that variants of one panel (save row normal/selected, with/without
        # comment) get the same layout; "detrend" - remove the per-row horizontal light
        # gradient from the moved pieces; "spread" - keep repeated source columns far apart;
        # "patch": [P, OV] - piece width and overlap.
        guide = it.get('guide', [it['image']])
        gcols = cols if guide == [it['image']] else [sum(cc, []) for cc in zip(*[image_cols(it, g) for g in guide])]
        part_off = 0
        # "guide_part": which of the guide images has this image's layout (default: itself)
        for g in guide[:it.get('guide_part', guide.index(it['image']) if it['image'] in guide else 0)]:
            part_off += len(image_cols(it, g)[0])
        src = tuple(it['src']) if 'src' in it else source_band(gcols, cut_left, cut_right, width)
        slice_w = src[1] - src[0]
        P = max(8, min(32, slice_w * 2 // 3))
        OV = max(3, P // 4)
        if 'patch' in it:
            P, OV = it['patch']
        detrend = it.get('detrend', False)
        qg = detrended(gcols, row_slopes(gcols, *src), cut_right) if detrend else None
        qown = detrended(cols, row_slopes(cols, *src), cut_right) if detrend else cols
        # 16:9 (W = 856) is quilted; 16:10 (W = 768) is cut out of it (2026-10-17, owner: one
        # drawing for both, as with the backgrounds) - 88 columns removed from the quilted middle.
        W = 856
        ox2 = W - 640
        rng = random.Random(a.seed * 1000 + W)
        gstrip, smap = build(gcols, width, cut_left, cut_right, ox2, rng, P, OV, src, it.get('period', 0),
                             it.get('spread', False), qg, want_map=True, avoid=it.get('avoid', ()))
        if gcols is cols:
            wide = gstrip
        else:
            wide = [[(qown if f else cols)[s][y] for y, (s, f) in enumerate(smap[c][part_off:part_off + rows])]
                    for c in range(len(smap))]
        remove = 856 - 768
        # the cut may reach the right part's native continuation (its first OV columns), so the
        # right side can start phase-aligned with the original right part (one jump, as before)
        cut_hi = cut_right + ox2 + 12 - OV
        # strips whose middle repeats every `period` px: any cut inside the middle shifts the
        # pattern by period - remove (9 px) and shows a blot or hook twice side by side (review
        # rounds 1-3, 2026-10-17), so the right side must start exactly at the original right
        # part's native continuation - one phase jump next to the right part, as before
        cut_lo = cut_hi - 12 - remove if it.get('period', 0) else cut_right
        g_src, w_src = gstrip, wide
        if it.get('period', 0):
            # ...and from the original's own columns: in the 856 the OV columns before the right
            # part hold its last quilted piece blended in (that piece follows the 856's pattern
            # phase, 9 px off in the 768 - review round 4), so the 768 takes them unblended
            rf = cut_right + ox2
            g_src, w_src = list(gstrip), list(wide)
            for w in range(rf - OV, rf):
                g_src[w] = list(gcols[w - ox2])
                w_src[w] = list(cols[w - ox2])
        cut_a, cut_path = narrower_map(g_src, remove, cut_lo, cut_hi)
        for W in (768, 856):
            strip = wide if W == 856 else apply_narrower(w_src, remove, cut_a, cut_path, row_off=part_off)
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
