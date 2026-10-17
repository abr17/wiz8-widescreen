""""Stone wings" image for UI windows: Data\\Wide\\WideFrame_<W>.STI.
python make_wings.py <out.sti> <W> <map_border_0.png> [gen856.png]
Without gen856.png the marble is taken from the game itself (automap frame, top panel
of the right column), tiled with mirroring. With gen856.png (Astra extension, canvas 856)
its margins are used (for W < 856 - the inner part of the margins). On top - a bevel at the edge
of the 640 window and slight darkening toward the screen edges. The central 640 is black (unused)."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import artkit

out, W, mb = sys.argv[1], int(sys.argv[2]), sys.argv[3]
gen = sys.argv[4] if len(sys.argv) > 4 else None
ox = (W - 640) // 2

if gen:
    gw, gh, grows = artkit.read_png(gen)
    gox = (gw - 640) // 2

    def source(x, y, side):
        # side 0: column x on the left (0..ox-1), side 1: on the right; take Astra's columns nearest the window
        return grows[y][gox - ox + x][:3] if side == 0 else grows[y][gox + 640 + x][:3]
else:
    _, _, mrows = artkit.read_png(mb)
    px0, py0, pw, ph = 486, 6, 148, 58
    patch = [[mrows[py0 + y][px0 + x][:3] for x in range(pw)] for y in range(ph)]

    def source(x, y, side):
        x += side * 977
        tx, ty, u, v = x // pw, y // ph, x % pw, y % ph
        if tx & 1:
            u = pw - 1 - u
        if ty & 1:
            v = ph - 1 - v
        c = patch[v][u]
        return tuple(int(ch * 0.85) for ch in c)


rows = []
for y in range(480):
    r = [(0, 0, 0)] * W
    for side in (0, 1):
        for x in range(ox):
            d = (ox - 1 - x) if side == 0 else x          # to the edge of the 640 window
            e = x if side == 0 else ox - 1 - x            # to the screen edge
            c = source(x, y, side)
            k = 1.0
            if d == 0:
                c, k = (10, 10, 10), 1.0                  # dark seam at the window frame
            elif d in (1, 2):
                k = 0.5                                   # shadow
            elif d == 3:
                k = 1.4                                   # bevel highlight
            elif d in (4, 5):
                k = 1.12
            if e < 12:
                k *= 0.55 + 0.0375 * e                    # soft darkening toward the screen edge
            if y < 3 or y > 476:
                k *= 0.6
            # at least 9: otherwise after 5:6:5 the pixel becomes 0x0000, which is transparent in the game
            r[x if side == 0 else ox + 640 + x] = tuple(max(9, min(255, int(ch * k))) for ch in c)
    rows.append(r)
png = os.path.splitext(out)[0] + '.png'
artkit.write_png(png, W, 480, rows, False)
template = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'assets', 'Data', 'OPTIONS', 'INTRO_BG_TEXT_768.STI')
artkit.tosti(png, template, out)
