"""Lockpick panel gaps "quilted" from pixels of the original niche itself (2026-10-16).
The owner rejected all Astra textures (different pattern and tint), so here there
is not a single foreign pixel: gap = the whole original niche (shadow + stone), then
image quilting (Efros-Freeman) with 8x8 patches from the niche's flat part
(x 13..28) - with a 3-pixel overlap and a minimum-error boundary cut, so there are
neither straight seams nor repeating columns. The niche's vertical lighting (row mean)
is preserved: only the deviation from the row mean is quilted.
python -I niche_quilt.py <lockpick_bottompanel_0.png> <out_dir> [--seed 1]
Output as in make_lock_niche.py: LOCKPICKGAPS_768/856.STI and preview_*.png."""
import argparse
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
import artkit  # noqa: E402
from make_lock_niche import TOP, HEIGHT, NICHE_W, SHADOW_W, encode  # noqa: E402

P, OV = 8, 3


def quilt(niche, width, rng, panel=None):
    flat = [row[SHADOW_W:NICHE_W] for row in niche]
    fw = len(flat[0])
    means = [tuple(sum(p[c] for p in row) / fw for c in range(3)) for row in flat]
    res = [[tuple(p[c] - means[y][c] for c in range(3)) for p in row] for y, row in enumerate(flat)]
    near = 24
    if panel is not None:
        # source - cracked marble from the middle of the info panel (x 36..145, y 22..86),
        # dimmed to the niche's brightness (contrast reduced in the same proportion)
        reg = [row[36:146] for row in panel[22:87]]
        pm = [sum(p[c] for row in reg for p in row) / (len(reg) * len(reg[0])) for c in range(3)]
        k = (sum(sum(m) for m in means) / len(means)) / sum(pm)
        res = [[tuple((p[c] - pm[c]) * k for c in range(3)) for p in row] for row in reg]
        fw = len(res[0])
        near = 10 ** 9
    # sources: PxP patches from the flat part + their horizontal mirrors
    srcs = []
    for sy in range(len(res) - P + 1):
        for sx in range(fw - P + 1):
            blk = [res[sy + j][sx:sx + P] for j in range(P)]
            srcs.append((sy, blk))
            srcs.append((sy, [list(reversed(r)) for r in blk]))
    # deviation canvas; the first NICHE_W columns are the original niche (its deviations from the mean)
    out = [[None] * width for _ in range(HEIGHT)]
    for y in range(HEIGHT):
        for x in range(NICHE_W):
            out[y][x] = tuple(niche[y][x][c] - means[y][c] for c in range(3))

    def d2(a, b):
        return sum((a[c] - b[c]) ** 2 for c in range(3))

    step = P - OV
    x0 = NICHE_W - OV
    while x0 < width:
        y0 = 0
        while y0 < HEIGHT:
            h = min(P, HEIGHT - y0)
            w = min(P, width - x0)
            best = []
            for sy, blk in srcs:
                if abs(sy - y0) > near:  # keep the patch close to its own height (lighting and character)
                    continue
                e = 0.0
                for j in range(h):
                    for i in range(w):
                        o = out[y0 + j][x0 + i]
                        if o is not None and (i < OV or j < OV):
                            e += d2(o, blk[j][i])
                best.append((e, rng.random(), blk))
            best.sort(key=lambda t: (t[0], t[1]))
            lim = best[0][0] * 1.15 + 1e-6
            cand = [b for b in best if b[0] <= lim][:8]
            blk = rng.choice(cand)[2]
            # mask: minimum-error cut in the left overlap (vertical)
            # and in the top overlap (horizontal)
            take = [[True] * w for _ in range(h)]
            if out[y0][x0] is not None and w > OV:
                err = [[d2(out[y0 + j][x0 + i], blk[j][i]) if out[y0 + j][x0 + i] is not None else 0
                        for i in range(OV)] for j in range(h)]
                cost = [row[:] for row in err]
                for j in range(1, h):
                    for i in range(OV):
                        cost[j][i] += min(cost[j - 1][k] for k in range(max(0, i - 1), min(OV, i + 2)))
                i = min(range(OV), key=lambda k: cost[h - 1][k])
                for j in range(h - 1, -1, -1):
                    for k in range(i):
                        take[j][k] = False
                    if j:
                        i = min(range(max(0, i - 1), min(OV, i + 2)), key=lambda k: cost[j - 1][k])
            if y0 > 0:
                err = [[d2(out[y0 + j][x0 + i], blk[j][i]) if out[y0 + j][x0 + i] is not None else 0
                        for i in range(w)] for j in range(OV)]
                cost = [[err[j][i] for i in range(w)] for j in range(OV)]
                for i in range(1, w):
                    for j in range(OV):
                        cost[j][i] += min(cost[k][i - 1] for k in range(max(0, j - 1), min(OV, j + 2)))
                j = min(range(OV), key=lambda k: cost[k][w - 1])
                for i in range(w - 1, -1, -1):
                    for k in range(j):
                        take[k][i] = False
                    if i:
                        j = min(range(max(0, j - 1), min(OV, j + 2)), key=lambda k: cost[k][i - 1])
            for j in range(h):
                for i in range(w):
                    if take[j][i] or out[y0 + j][x0 + i] is None:
                        if x0 + i >= NICHE_W or out[y0 + j][x0 + i] is None:
                            out[y0 + j][x0 + i] = blk[j][i]
            y0 += step if y0 + P < HEIGHT else P
        x0 += step
    return [[tuple(max(1, min(255, int(round(means[y][c] + out[y][x][c])))) for c in range(3))
             for x in range(width)] for y in range(HEIGHT)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('panel0')
    ap.add_argument('out_dir')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--marble', action='store_true', help='quilt from the panel marble instead of the niche')
    ap.add_argument('--template', default=r'C:\dev\wiz8-ws\assets\Data\WIDE\WIDEFRAME_%d.STI')
    a = ap.parse_args()
    _, h0, rows = artkit.read_png(a.panel0)
    assert h0 == HEIGHT
    niche = [row[:NICHE_W] for row in rows]
    os.makedirs(a.out_dir, exist_ok=True)
    # 16:9 (W = 856, gaps 108 wide) is quilted; 16:10 (gaps 64 wide) is cut out of it
    # (2026-10-17, owner: one drawing for both widths). Each gap = the niche + its quilted
    # continuation, so the narrower gap is the first 64 columns of the wider one.
    rng = random.Random(a.seed)
    wide_left = quilt(niche, 108, rng, rows if a.marble else None)
    wide_right = quilt(niche, 108, rng, rows if a.marble else None)
    for W in (768, 856):
        ox = (W - 640) // 2
        left = [row[:ox] for row in wide_left]
        right = [row[:ox] for row in wide_right]
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
