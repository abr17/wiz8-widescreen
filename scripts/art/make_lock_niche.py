"""Lockpick panel gaps from the original shaded niche (2026-10-16).
python -I make_lock_niche.py <lockpick_bottompanel_0.png> <out_dir> [--seed 7]

The niche is the left 29 columns of image 0 of the info panel (LOCKPICK_BOTTOMPANEL.STI):
x 0..12 - shadow from black to stone, x 13..28 - flat dark grainy stone.
A gap of width ox (64 for canvas 768, 108 for 856) = the whole niche + continuation
in blocks of the flat part (16 columns each, each with its own vertical cyclic
shift, odd ones mirrored) so the grain does not repeat in columns.

Writes <out_dir>/LOCKPICKGAPS_<W>.STI - a 16-bit W x 480 image (wide pair format,
wide_art.h): left gap in x [0, ox), right gap in [ox, 2*ox), rows 358..449
(as for the bottom sub-screens). Colors are converted like the game's palette images
(each channel >> 3); green is written so that after the low bit is dropped
on load (565 -> 555) exactly the same level remains. Also <out_dir>/preview_<W>.png."""
import argparse
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
import artkit  # noqa: E402

TOP, HEIGHT = 358, 92
NICHE_W, SHADOW_W = 29, 13


def read_png(path):
    # artkit.read_png -> (w, h, rows of (r,g,b))
    return artkit.read_png(path)


def build_gap(niche, width, rng):
    """niche: 92 rows of NICHE_W (r,g,b); result: 92 rows of width."""
    flat = [row[SHADOW_W:NICHE_W] for row in niche]  # 16 columns
    fw = len(flat[0])
    # the niche has its own vertical shading (top is darker): only the "grain"
    # (deviation from the row mean) is shifted; the row mean stays at its height
    means = [tuple(sum(p[c] for p in row) / fw for c in range(3)) for row in flat]
    grain = [[tuple(p[c] - means[y][c] for c in range(3)) for p in row] for y, row in enumerate(flat)]
    out = [list(row[:NICHE_W]) for row in niche]  # niche as is
    block = 0
    while len(out[0]) < width:
        block += 1
        shift = rng.randrange(HEIGHT)
        mirror = block % 2 == 1
        for y in range(HEIGHT):
            src = grain[(y + shift) % HEIGHT]
            src = list(reversed(src)) if mirror else src
            out[y].extend(tuple(max(0, min(255, int(round(means[y][c] + g[c])))) for c in range(3))
                          for g in src)
    return [row[:width] for row in out]


def lighting(niche):
    """Lighting of the original niche: multiplier per shadow column (0..SHADOW_W-1) and per row
    of the flat part - ratio to the flat-part mean."""
    flat = [row[SHADOW_W:NICHE_W] for row in niche]
    lum = lambda p: (p[0] + p[1] + p[2]) / 3.0
    fmean = sum(lum(p) for row in flat for p in row) / (HEIGHT * len(flat[0]))
    rows = [sum(lum(p) for p in row) / len(row) / fmean for row in flat]
    cols = [sum(lum(niche[y][x]) for y in range(HEIGHT)) / HEIGHT / fmean for x in range(SHADOW_W)]
    stats = []
    for c in range(3):
        vals = [p[c] for row in flat for p in row]
        m = sum(vals) / len(vals)
        sd = (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5
        stats.append((m, sd))
    return rows, cols, stats


def area_resize(rows, w, h):
    sh, sw = len(rows), len(rows[0])
    out = []
    for y in range(h):
        y0, y1 = y * sh / h, (y + 1) * sh / h
        line = []
        for x in range(w):
            x0, x1 = x * sw / w, (x + 1) * sw / w
            acc = [0.0, 0.0, 0.0]
            tot = 0.0
            for yy in range(int(y0), min(sh, int(y1 + 0.999))):
                wy = min(yy + 1, y1) - max(yy, y0)
                for xx in range(int(x0), min(sw, int(x1 + 0.999))):
                    wx = min(xx + 1, x1) - max(xx, x0)
                    wgt = wx * wy
                    p = rows[yy][xx]
                    for c in range(3):
                        acc[c] += p[c] * wgt
                    tot += wgt
            line.append(tuple(v / tot for v in acc))
        out.append(line)
    return out


def box(lum, r=2):
    h, w = len(lum), len(lum[0])
    out = []
    for y in range(h):
        ys = range(max(0, y - r), min(h, y + r + 1))
        line = []
        for x in range(w):
            xs = range(max(0, x - r), min(w, x + r + 1))
            line.append(sum(lum[a][b] for a in ys for b in xs) / (len(ys) * len(xs)))
        out.append(line)
    return out


def split_sd(lum):
    """Spread of large blotches (5x5 blur) and fine grain (residual), separately."""
    lp = box(lum)
    lv = [v for row in lp for v in row]
    lm = sum(lv) / len(lv)
    lsd = (sum((v - lm) ** 2 for v in lv) / len(lv)) ** 0.5 or 1.0
    hv = [a - b for ra, rb in zip(lum, lp) for a, b in zip(ra, rb)]
    hsd = (sum(v * v for v in hv) / len(hv)) ** 0.5 or 1.0
    return lp, lm, lsd, hsd


def native_grain(niche, rows_l):
    """Grain of the original niche's flat part without its vertical lighting (each row
    divided by its lighting multiplier): spread of blotches and fine grain."""
    flat = [[(p[0] + p[1] + p[2]) / 3.0 / rows_l[y] for p in row[SHADOW_W:NICHE_W]]
            for y, row in enumerate(niche)]
    _, _, lsd, hsd = split_sd(flat)
    return lsd, hsd


def gap_from_texture(tex_rows, width, niche, light, x_offset):
    """Whole Astra texture (already downscaled to gap width x 92) -> gap.
    The texture's large blotches and fine grain are each matched to the original niche's spread
    (Astra's grain is twice as strong and its blotches larger - that made the niche look foreign); color -
    mean color of the niche's flat part, then the niche lighting: shadow at the left edge and the per-row profile."""
    rows_l, cols_l, stats = light
    nat_lsd, nat_hsd = native_grain(niche, rows_l)
    lum_t = [[(p[0] + p[1] + p[2]) / 3.0 for p in row] for row in tex_rows]
    lp, lm, lsd, hsd = split_sd(lum_t)
    mean_l = sum(m for m, _ in stats) / 3.0
    out = []
    for y in range(HEIGHT):
        line = []
        for x in range(width):
            d = (lp[y][x] - lm) / lsd * nat_lsd + (lum_t[y][x] - lp[y][x]) / hsd * nat_hsd
            k = rows_l[y] * (cols_l[x] if x < SHADOW_W else 1.0)
            line.append(tuple(max(0, min(255, int(round(m * (1 + d / mean_l) * k)))) for m, _ in stats))
        out.append(line)
    return out


def encode(r, g, b):
    r5, g5, b5 = r >> 3, g >> 3, b >> 3
    return (r5 << 11) | (min(63, 2 * g5 + 1) << 5) | b5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('panel0')
    ap.add_argument('out_dir')
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--texture', default='', help='whole Astra texture (PNG); without it - niche grain')
    ap.add_argument('--template', default=r'C:\dev\wiz8-ws\assets\Data\WIDE\WIDEFRAME_%d.STI')
    a = ap.parse_args()
    w0, h0, rows = read_png(a.panel0)
    assert h0 == HEIGHT, h0
    niche = [row[:NICHE_W] for row in rows]
    os.makedirs(a.out_dir, exist_ok=True)
    for W in (768, 856):
        ox = (W - 640) // 2
        rng = random.Random(a.seed)
        if a.texture:
            tw, th, trows = read_png(a.texture)
            light = lighting(niche)
            # one texture for both gaps (same grain scale: texture height =
            # 92 game pixels); the right gap is the same texture rotated by 180 degrees,
            # so the gaps are not copies (lighting is applied afterwards)
            scale = th / HEIGHT
            need = min(tw, int(round(ox * scale)))
            lt = area_resize([row[:need] for row in trows], ox, HEIGHT)
            flipped = [list(reversed(row)) for row in reversed(trows)]
            rt = area_resize([row[:need] for row in flipped], ox, HEIGHT)
            left = gap_from_texture(lt, ox, niche, light, 0)
            right = gap_from_texture(rt, ox, niche, light, 0)
        else:
            left = build_gap(niche, ox, rng)
            right = build_gap(niche, ox, rng)
        canvas = [[(0, 0, 0)] * W for _ in range(480)]
        for y in range(HEIGHT):
            canvas[TOP + y][0:ox] = left[y]
            canvas[TOP + y][ox:2 * ox] = right[y]
        head = bytearray(open(a.template % W, 'rb').read()[:64])
        assert struct.unpack_from('<HH', head, 20) == (480, W)
        data = struct.pack('<%dH' % (W * 480), *[encode(*p) for row in canvas for p in row])
        open(os.path.join(a.out_dir, 'LOCKPICKGAPS_%d.STI' % W), 'wb').write(bytes(head) + data)
        prev = [left[y] + [(255, 0, 255)] * 4 + right[y] for y in range(HEIGHT)]
        artkit.write_png(os.path.join(a.out_dir, 'preview_%d.png' % W), 2 * ox + 4, HEIGHT, prev, False)
        print('ok', W, ox)


if __name__ == '__main__':
    main()
