r"""Native-stone wings for Data\Wide\WideFrame_<W>.sti (method C "edge-extend": the window's own
marble continued outward). Since 1.0.2 this replaces the AI-painted marble; the shipped files
were made with: python -I native_wings.py --edge makewings --out DIR (owner's choice 2026-10-22:
native stone with make_wings.py's dark groove, shadow and bevel at the window edge), then
DIR\wings\WIDEFRAME_768/856.STI copied to assets\Data\WIDE. The review composites need the captures in
build\tmp\native-wings\capture (not in git); without them only the wings are made.

    python -I native_wings.py [--out DIR] [--seed 21] [--edge flush|makewings] [--no-composites]
    (defaults: --out build\tmp\native-wings\out, --slf games\reference\Data\DATA.SLF,
     --capture build\tmp\native-wings\capture)

final\ revision of edge-extend\build_wings.py (judges' fixes; all defaults reproduce final\):
  - --flatten 0.0 (was 0.65): the native mottling and crack contrast are kept (only the plane of
    the panel light is taken out; 0.35 still left the stone cloudier than native: blotch32 ~1.4
    against 2.2-2.6 native; 0.0 gives 2.2-2.5 and sd 6.9-7.2 like the window marble);
  - --seed 21 (was 8): picked from 24 seeds (tools\seedsweep.py) for the fewest repeats: no
    same-orientation copy anywhere, nothing within 120 px (tools\audit.ps1);
  - the small "box" crack cell (REVIEWITEMPAGE f2 x134-159 y45-70, a recognisable motif that the
    inventory window itself shows) is found by template matching in every source area, any
    orientation, and no piece may contain it (--box-thr; log in wings\box_exclusions.txt);
  - row equalisation of the assembled wing (--roweq): the low-frequency part of the robust row mean
    (13-row smoothing minus 81-row smoothing) is removed, so no full-width horizontal band remains;
  - each wing is levelled to the window marble's mean colour (--level), so left and right match.

What it does
  1. Reads, read-only, the game's own UI pictures straight from games\reference\Data\DATA.SLF:
     the large plain marble areas of the windows (CAMP item page behind the doll, creation skills
     page, automap frame, stats-page top-right panel). It is the same cracked-flagstone marble that
     forms the outer lip of the 4:3 windows (neutral grey, palette ~32/31/31).
  2. Takes out each area's slow light gradient (the windows light their panels from the top left; a
     moved piece would carry that gradient; --flatten F also takes out the share F of its large
     blotches, default 0) and brings all to one tone.
  3. Quilts the 16:9 wings (2 x 108 x 480) from 7 turned/flipped orientations of those areas
     (Efros-Freeman: 40-px pieces, 10-px overlap matched on brightness texture, each piece
     tone-matched to its neighbours along the overlap, then a minimum-error cut through every overlap
     - no straight join, no tone step). The original marble repeats a 128-px crack layout inside its own
     pictures, so a repeat penalty keeps a piece of that layout away from places that already show it:
     an identical copy anywhere on screen, a turned copy close by. wings\repeats.txt reports what
     is left.
  4. 16:10 = the inner 64 columns of the 16:9 wings (one drawing for both, as with the backgrounds).
  5. Edge: flush, no added frame or shadow - every 4:3 window already ends in its own groove/frame or a
     few px of the same marble, so the wing simply continues the wall (--edge makewings = the old
     seam/shadow/bevel of scripts\art\make_wings.py, for comparison). A slight darkening over the outer
     ~20 px toward the screen edge.
  6. Encodes like scripts\art\stretch_quilt.encode (green survives the game's 565 -> 555): on screen a
     wing pixel is exactly r>>3, g>>3, b>>3, like a native palette pixel; never 0x0000 (transparent).

Writes into --out:
  wings\wing_<W>.png          W x 480, authored colours, centre black
  wings\wing_<W>_shown.png    as the game shows it (5:6:5 -> 5:5:5)
  wings\WIDEFRAME_<W>.STI     candidate file (NOT installed anywhere)
  wings\pieces.txt, repeats.txt
  composites_exact\<shot>.png the static window rebuilt from the game's pieces (capture\native) + the
                              exact wing - for checking the joint pixel by pixel
  composites\<shot>.png       each capture in capture\canvas, centre untouched, side bars replaced by
                              the exact wing
  boost\<shot>_boost.png      composites at gamma 0.45 (the LUT of scripts\play\boost_shot.ps1), 2x
  compare\<shot>.png          current wings (top) vs native (bottom); normal | gamma 0.45
"""
import argparse
import math
import os
import random
import struct
import sys

sys.path.insert(0, r'C:\dev\wiz8-ws\scripts\art')
import artkit  # noqa: E402

ROOT = r'C:\dev\wiz8-ws'
SLF_DEFAULT = os.path.join(ROOT, r'games\reference\Data\DATA.SLF')
CAPTURE_DEFAULT = os.path.join(ROOT, r'build\tmp\native-wings\capture')
TEMPLATE = os.path.join(ROOT, r'assets\Data\WIDE\WIDEFRAME_%d.STI')
# orientations allowed per tile group: the unrotated stone of the CAMP item page (ip), the stats-page
# panel (cm), the creation skills page (cg) and the automap frame (mb, map with WideAutomap=0) is on
# screen in the 4:3 windows themselves, so only turned/flipped copies of it go into the wings
ORIENT = {'ip': range(1, 8), 'cm': range(1, 8), 'cg': range(1, 8), 'mb': range(1, 8)}

# plain marble areas (inclusive pixel rectangles found by the capture step, frame coordinates)
# key, STI, frame, x, y, w, h, tile group (areas of one group share one 128-px marble layout)
REGIONS = [
    ('A1', r'REVIEW\REVIEWITEMPAGE.STI', 2, 128, 5, 116, 279, 'ip'),
    ('A2', r'REVIEW\REVIEWITEMPAGE.STI', 2, 84, 72, 44, 116, 'ip'),
    ('A3', r'REVIEW\REVIEWITEMPAGE.STI', 2, 280, 220, 84, 64, 'ip'),
    ('B1', r'CHAR GENERATION\CG_SKILLS.STI', 0, 8, 288, 212, 116, 'cg'),
    ('C1', r'AUTOMAP\MAP_BORDER.STI', 0, 484, 4, 152, 60, 'mb'),
    ('C2', r'AUTOMAP\MAP_BORDER.STI', 0, 484, 372, 152, 60, 'mb'),
    ('M1', r'REVIEW\COMMOD_BACK.STI', 0, 40, 64, 112, 52, 'cm'),
]
TARGET = (32.0, 31.2, 31.3)   # mean colour of the windows' plain marble (palette values)
TILE = 128

# synthesis parameters
P, OV = 40, 10        # piece size and overlap
STRIDE = 2            # candidate grid in the sources
WING = 108            # 16:9 wing width (ox at W = 856)
RO = 480.0            # repeat penalty: reach on screen
OW = 0.6              # ... weight of a turned/flipped copy (a same-orientation copy counts 1)
H = 480


# ---------------------------------------------------------------- game files (read-only)
def slf_read(slf, names):
    want = {n.lower() for n in names}
    out = {}
    with open(slf, 'rb') as f:
        entries = struct.unpack_from('<i', f.read(532), 512)[0]
        f.seek(0, 2)
        f.seek(f.tell() - entries * 280)
        table = f.read(entries * 280)
        for i in range(entries):
            r = table[i * 280:(i + 1) * 280]
            name = r[:256].split(b'\0')[0].decode('latin1')
            off, length, state = struct.unpack_from('<IIB', r, 256)
            if state or name.lower() not in want:
                continue
            f.seek(off)
            out[name.lower()] = f.read(length)
    missing = want - set(out)
    assert not missing, missing
    return out


def read_sti8(d):
    """8-bit ETRLE STI from bytes (same decoder as scripts\\art\\sti8.py)."""
    assert d[:4] == b'STCI'
    flags, = struct.unpack_from('<I', d, 16)
    assert flags & 0x8
    count, = struct.unpack_from('<H', d, 28)
    pal = [tuple(d[64 + i * 3:64 + i * 3 + 3]) for i in range(256)]
    sub = 64 + 768
    data = sub + count * 16
    frames = []
    for i in range(count):
        off, length, sx, sy, h, w = struct.unpack_from('<IIhhHH', d, sub + i * 16)
        src = d[data + off:data + off + length]
        px = [[None] * w for _ in range(h)]
        if flags & 0x20:
            p = 0
            for y in range(h):
                x = 0
                while p < len(src):
                    b = src[p]
                    p += 1
                    if b == 0:
                        break
                    if b & 0x80:
                        x += b & 0x7f
                    else:
                        for k in range(b):
                            if x < w:
                                px[y][x] = src[p + k]
                            x += 1
                        p += b
        else:
            for y in range(h):
                for x in range(w):
                    px[y][x] = src[y * w + x]
        frames.append((w, h, [[None if v is None else pal[v] for v in row] for row in px]))
    return frames


def lum(r, g, b):
    return (3 * r + 6 * g + b) / 10.0


def box_blur(vals, w, h, rad):
    """separable box blur of a flat list, edges clamped"""
    def blur_1d(line):
        n = len(line)
        pre = [0.0]
        for v in line:
            pre.append(pre[-1] + v)
        out = []
        for i in range(n):
            a, b = max(0, i - rad), min(n, i + rad + 1)
            out.append((pre[b] - pre[a]) / (b - a))
        return out
    rows = [blur_1d(vals[y * w:(y + 1) * w]) for y in range(h)]
    cols = [blur_1d([rows[y][x] for y in range(h)]) for x in range(w)]
    return [cols[x][y] for y in range(h) for x in range(w)]


# ---------------------------------------------------------------- sources
class Source:
    """One orientation of one marble area: flat R, G, B, L lists plus the map back to the
    area's frame coordinates (for the repeat penalty)."""

    def __init__(self, key, group, vw, vh, R, G, B, back):
        self.key, self.group, self.w, self.h = key, group, vw, vh
        self.R, self.G, self.B = R, G, B
        self.L = [lum(r, g, b) for r, g, b in zip(R, G, B)]
        self.back = back


def orient(t, w, h, x0, y0):
    """orientation t of a w x h area at (x0, y0): (variant width, height, (u, v) -> frame x, y)"""
    if t < 4:
        def back(u, v):
            return x0 + (u if t in (0, 2) else w - 1 - u), y0 + (v if t in (0, 1) else h - 1 - v)
        return w, h, back

    def back(u, v):
        return x0 + (v if t in (4, 5) else w - 1 - v), y0 + (u if t in (4, 6) else h - 1 - u)
    return h, w, back


# ---------------------------------------------------------------- the "box" crack motif
# the same small square cell beside a crack junction exists in every flagstone tile; one template per
# tile (STI, frame, x, y, size; frame coords). Matches are also repeated at +-128 px inside their tile
# group (the layout repeats, e.g. the cut-off copy at the left edge of MAP_BORDER's C1 area).
BOXES = [
    (r'REVIEW\REVIEWITEMPAGE.STI', 2, 134, 45, 26),
    (r'AUTOMAP\MAP_BORDER.STI', 0, 606, 14, 26),
    (r'CHAR GENERATION\CG_SKILLS.STI', 0, 70, 356, 26),
]


def frame_lum(px, x0, y0, w, h):
    return [[lum(*px[y][x]) for x in range(x0, x0 + w)] for y in range(y0, y0 + h)]


def high_pass(L, r=6):
    """L minus its (2r+1)^2 box mean (window clipped at the edges), as judge-seams\\Rep.cs"""
    h, w = len(L), len(L[0])
    I = [[0.0] * (w + 1) for _ in range(h + 1)]
    for y in range(h):
        s = 0.0
        for x in range(w):
            s += L[y][x]
            I[y + 1][x + 1] = I[y][x + 1] + s
    out = []
    for y in range(h):
        y0, y1 = max(0, y - r), min(h, y + r + 1)
        row = []
        for x in range(w):
            x0, x1 = max(0, x - r), min(w, x + r + 1)
            m = (I[y1][x1] - I[y0][x1] - I[y1][x0] + I[y0][x0]) / ((x1 - x0) * (y1 - y0))
            row.append(L[y][x] - m)
        out.append(row)
    return out


def find_box(frames, thr, log):
    """Excluded rectangles (frame coords, inclusive) per region key: every window of a source area
    that matches one of the box templates at >= thr, plus its +-128 px copies in the tile group."""
    found = {}
    for box in BOXES:
        log.append('template %s f%d x%d y%d n%d' % box)
        for key, rects in find_one(frames, box, thr, log).items():
            found.setdefault(key, []).extend(rects)
    group_of = {r[0]: r[7] for r in REGIONS}
    by_group = {}
    for key, rects in found.items():
        by_group.setdefault(group_of[key], []).extend(rects)
    out = {}
    for key, s, f, x0, y0, w, h, group in REGIONS:
        rects = []
        for r in by_group.get(group, []):
            for dx in (-TILE, 0, TILE):
                for dy in (-TILE, 0, TILE):
                    q = (r[0] + dx, r[1] + dy, r[2] + dx, r[3] + dy)
                    if q[2] < x0 or q[0] > x0 + w - 1 or q[3] < y0 or q[1] > y0 + h - 1 or q in rects:
                        continue
                    rects.append(q)
        out[key] = rects
        log.append('%-3s excluded cores: %s' % (key, ' '.join('x%d-%d/y%d-%d' % (q[0], q[2], q[1], q[3]) for q in rects)))
    return out


def find_one(frames, box, thr, log):
    sti, fi, tx, ty, n = box
    px = frames[sti][fi][2]
    T = high_pass(frame_lum(px, tx - 8, ty - 8, n + 16, n + 16))
    T = [row[8:8 + n] for row in T[8:8 + n]]
    variants = []
    for t in range(8):
        tv = []
        for v in range(n):
            for u in range(n):
                a, b = (u, v) if t < 4 else (v, u)
                if t in (1, 3, 5, 7):
                    a = n - 1 - a
                if t in (2, 3, 6, 7):
                    b = n - 1 - b
                tv.append(T[b][a])
        m = sum(tv) / len(tv)
        tv = [q - m for q in tv]
        variants.append((tv, math.sqrt(sum(q * q for q in tv))))
    sub = [(v * n + u) for v in range(0, n, 2) for u in range(0, n, 2)]
    out = {}
    for key, s, f, x0, y0, w, h, group in REGIONS:
        fpx = frames[s][f][2]
        # high-pass on the area plus a margin of real frame pixels where there are any
        mx0, my0 = max(0, x0 - 8), max(0, y0 - 8)
        mx1, my1 = min(frames[s][f][0], x0 + w + 8), min(frames[s][f][1], y0 + h + 8)
        Lm = [[lum(*fpx[y][x]) if fpx[y][x] is not None else 0.0 for x in range(mx0, mx1)] for y in range(my0, my1)]
        A = high_pass(Lm)
        A = [row[x0 - mx0:x0 - mx0 + w] for row in A[y0 - my0:y0 - my0 + h]]

        def ncc(ax, ay, t, idx=None):
            tv, tn = variants[t]
            ids = idx if idx is not None else range(n * n)
            vals = [A[ay + i // n][ax + i % n] for i in ids]
            tt = [tv[i] for i in ids]
            ma = sum(vals) / len(vals)
            mt = sum(tt) / len(tt)
            sab = sum((p - ma) * (q - mt) for p, q in zip(vals, tt))
            saa = sum((p - ma) ** 2 for p in vals)
            sbb = sum((q - mt) ** 2 for q in tt)
            return sab / math.sqrt(saa * sbb) if saa > 1e-9 and sbb > 1e-9 else 0.0
        hits = []
        for ay in range(0, h - n + 1, 2):
            for ax in range(0, w - n + 1, 2):
                for t in range(8):
                    r = ncc(ax, ay, t, sub)
                    if r >= thr - 0.15:
                        hits.append((r, ax, ay, t))
        fine = []
        for r0, ax, ay, t in sorted(hits, reverse=True):
            if any(abs(ax - q[1]) < n // 2 and abs(ay - q[2]) < n // 2 for q in fine):
                continue
            best = (-1, ax, ay, t)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    bx, by = ax + dx, ay + dy
                    if 0 <= bx <= w - n and 0 <= by <= h - n:
                        r = ncc(bx, by, t)
                        if r > best[0]:
                            best = (r, bx, by, t)
            if best[0] >= thr:
                fine.append(best)
        rects = []
        for r, ax, ay, t in fine:
            # core of the motif: the template window less 3 px on every side
            rects.append((x0 + ax + 3, y0 + ay + 3, x0 + ax + n - 4, y0 + ay + n - 4))
            log.append('%-3s ncc %.3f at frame (%3d,%3d) orientation %d -> excluded core x%d-%d y%d-%d'
                       % (key, r, x0 + ax, y0 + ay, t, rects[-1][0], rects[-1][2], rects[-1][1], rects[-1][3]))
        out[key] = rects
    return out


def blocked(src, cx, cy):
    """True when the piece at (cx, cy) of this source variant would contain an excluded motif."""
    rects = EXCL.get(src.key.split('/')[0])
    if not rects:
        return False
    xa, ya = src.back(cx, cy)
    xb, yb = src.back(cx + P - 1, cy + P - 1)
    x0, x1, y0, y1 = min(xa, xb), max(xa, xb), min(ya, yb), max(ya, yb)
    return any(not (x1 < r[0] or x0 > r[2] or y1 < r[1] or y0 > r[3]) for r in rects)


EXCL = {}


def read_frames(files):
    frames = {}
    for key, sti, fi, x0, y0, w, h, group in REGIONS:
        if sti not in frames:
            frames[sti] = read_sti8(files[sti.lower()])
    return frames


def prepare_sources(files, flatten=0.0, rad=14):
    frames = read_frames(files)
    sources = []
    for key, sti, fi, x0, y0, w, h, group in REGIONS:
        px = frames[sti][fi][2]
        rgb = []
        for y in range(y0, y0 + h):
            for x in range(x0, x0 + w):
                p = px[y][x]
                assert p is not None, (key, x, y)
                rgb.append(p)
        R = [float(p[0]) for p in rgb]
        G = [float(p[1]) for p in rgb]
        B = [float(p[2]) for p in rgb]
        L = [lum(r, g, b) for r, g, b in zip(R, G, B)]
        n = w * h
        # 1) plane fit of brightness (panel lighting), removed
        mx, my = (w - 1) / 2.0, (h - 1) / 2.0
        sxx = sum((x - mx) ** 2 for x in range(w)) * h
        syy = sum((y - my) ** 2 for y in range(h)) * w
        bx = sum((i % w - mx) * L[i] for i in range(n)) / sxx
        by = sum((i // w - my) * L[i] for i in range(n)) / syy
        # 2) large blotches / bands (e.g. the darker band at x163-176 of the item page), partly removed
        Lp = [L[i] - bx * (i % w - mx) - by * (i // w - my) for i in range(n)]
        blur = box_blur(Lp, w, h, rad)
        mL = sum(Lp) / n
        adj = [-bx * (i % w - mx) - by * (i // w - my) - flatten * (blur[i] - mL) for i in range(n)]
        R = [r + a for r, a in zip(R, adj)]
        G = [g + a for g, a in zip(G, adj)]
        B = [b + a for b, a in zip(B, adj)]
        # 3) one tone for all areas
        for ch, t in ((R, TARGET[0]), (G, TARGET[1]), (B, TARGET[2])):
            d = t - sum(ch) / n
            for i in range(n):
                ch[i] += d
        # 8 orientations: variant(u, v) = area(f(u, v)); cracks and blotches have no light direction
        for t in ORIENT[group]:
            vw, vh, back = orient(t, w, h, x0, y0)
            idx = []
            for v in range(vh):
                for u in range(vw):
                    ax, ay = back(u, v)
                    idx.append((ay - y0) * w + ax - x0)
            s = Source('%s/%d' % (key, t), group, vw, vh, [R[i] for i in idx], [G[i] for i in idx],
                       [B[i] for i in idx], back)
            s.variant = t
            sources.append(s)
    return sources


# ---------------------------------------------------------------- quilting
def min_cut(err):
    """err[r][c] (rows x cols): path of one column per row with steps of at most 1, minimum total."""
    rows, cols = len(err), len(err[0])
    cost = list(err[0])
    back = []
    for r in range(1, rows):
        nc, br = [], []
        for c in range(cols):
            best = c
            if c > 0 and cost[c - 1] < cost[best]:
                best = c - 1
            if c < cols - 1 and cost[c + 1] < cost[best]:
                best = c + 1
            nc.append(cost[best] + err[r][c])
            br.append(best)
        cost = nc
        back.append(br)
    c = min(range(cols), key=lambda k: cost[k])
    path = [0] * rows
    for r in range(rows - 1, -1, -1):
        path[r] = c
        if r:
            c = back[r - 1][c]
    return path


class Wing:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.R = [0.0] * (w * h)
        self.G = [0.0] * (w * h)
        self.B = [0.0] * (w * h)
        self.L = [0.0] * (w * h)
        self.filled = [False] * (w * h)
        self.S = [None] * (w * h)   # (source, index) per pixel, for the repeat report


def torus(a, b):
    d = abs(a - b) % TILE
    return min(d, TILE - d)


def quilt(sources, rng, placed, side, gx0, lam=4.0, keep=300, pool_tol=1.12, pool_n=4, ncand=9000):
    xs = list(range(0, WING - P + (P - OV), P - OV))
    while xs[-1] + P < WING:
        xs.append(xs[-1] + P - OV)
    ys = list(range(0, H - P + (P - OV), P - OV))
    while ys[-1] + P < H:
        ys.append(ys[-1] + P - OV)
    cw, ch = xs[-1] + P, ys[-1] + P
    wg = Wing(cw, ch)
    cands = [(si, cx, cy) for si, src in enumerate(sources)
             for cy in range(0, src.h - P + 1, STRIDE) for cx in range(0, src.w - P + 1, STRIDE)
             if not blocked(src, cx, cy)]
    for py in ys:
        for px in xs:
            samples = []
            for y in range(py, py + P):
                for x in range(px, px + P):
                    if wg.filled[y * cw + x]:
                        samples.append((x - px, y - py, wg.L[y * cw + x]))
            if samples:
                coarse = [s for s in samples if s[0] % 3 == 1 and s[1] % 3 == 1] or samples
                T = [t for _, _, t in coarse]
                offs = {}
                scored = []
                # a fresh random share of all candidate positions for every piece (speed + variety)
                for si, cx, cy in rng.sample(cands, min(len(cands), ncand)):
                    src = sources[si]
                    if si not in offs:
                        offs[si] = [dy * src.w + dx for dx, dy, _ in coarse]
                    Lv = src.L
                    base = cy * src.w + cx
                    e = s1 = 0.0
                    for o, t in zip(offs[si], T):
                        d = Lv[base + o] - t
                        e += d * d
                        s1 += d
                    # mostly texture: a plain tone offset is corrected when the piece is pasted
                    scored.append((e - TONE_K * s1 * s1 / len(T), src, cx, cy))
                scored.sort(key=lambda t: t[0])
                top = scored[:keep]
                fine = []
                for _, src, cx, cy in top:
                    Lv = src.L
                    e = s1 = 0.0
                    for dx, dy, t in samples:
                        d = Lv[(cy + dy) * src.w + cx + dx] - t
                        e += d * d
                        s1 += d
                    fine.append(((e - TONE_K * s1 * s1 / len(samples)) / len(samples), src, cx, cy))
            else:
                fine = []
                for src in sources:
                    for cy in range(0, src.h - P + 1, STRIDE * 2):
                        for cx in range(0, src.w - P + 1, STRIDE * 2):
                            if not blocked(src, cx, cy):
                                fine.append((1.0, src, cx, cy))
                rng.shuffle(fine)
                fine = fine[:keep]
            # repeat penalty: the same spot of a group's 128-px layout close by (both wings count)
            ocx, ocy = gx0 + px + P / 2.0, py + P / 2.0
            ranked = []
            for e, src, cx, cy in fine:
                ax, ay = src.back(cx + P // 2, cy + P // 2)
                pen = 0.0
                for q in placed:
                    if q[0] != src.group:
                        continue
                    # share of the piece's footprint in the marble layout that the other piece shows
                    tx, ty = torus(ax, q[1]), torus(ay, q[2])
                    if tx >= P or ty >= P:
                        continue
                    share = (1 - tx / P) * (1 - ty / P)
                    do = math.hypot(ocx - q[3], ocy - q[4])
                    if do >= RO:
                        continue
                    # an identical copy is recognisable anywhere on screen, a turned one only close by
                    pen += share * ((1 - do / RO) if q[5] == src.variant else OW * (1 - do / RO) ** 2)
                ranked.append((e * (1 + lam * pen), e, pen, src, cx, cy, ax, ay))
            ranked.sort(key=lambda t: t[0])
            lim = ranked[0][0] * pool_tol + 1e-6
            pool = [t for t in ranked if t[0] <= lim][:pool_n]
            _, e, pen, src, cx, cy, ax, ay = rng.choice(pool)
            placed.append((src.group, ax, ay, ocx, ocy, src.variant, side, src.key, px, py))
            # the piece, tone-matched to what is already there: along the left / top overlap the local
            # brightness difference (old - new, averaged across the overlap, smoothed along it) is added
            # in full and fades out over FADE px into the piece - no tone step can remain at the cut
            nL = [[src.L[(cy + r) * src.w + cx + c] for c in range(P)] for r in range(P)]
            cor = [[0.0] * P for _ in range(P)]
            dl = dt = None
            if px > 0:
                dl = smooth([sum(wg.L[(py + r) * cw + px + c] - nL[r][c] for c in range(OV)) / OV
                             for r in range(P)], TONE_R)
            if py > 0:
                dt = smooth([sum(wg.L[(py + r) * cw + px + c] - nL[r][c] for r in range(OV)) / OV
                             for c in range(P)], TONE_R)
            for r in range(P):
                wt = fade(r) if dt else 0.0
                for c in range(P):
                    wl = fade(c) if dl else 0.0
                    if wl + wt > 0:
                        cor[r][c] = ((wl * dl[r] if dl else 0.0) + (wt * dt[c] if dt else 0.0)) / max(1.0, wl + wt)
            # minimum-error cuts through the left and top overlaps (on the tone-matched piece)
            vpath = hpath = None
            if px > 0:
                err = [[(wg.L[(py + r) * cw + px + c] - nL[r][c] - cor[r][c]) ** 2
                        for c in range(OV)] for r in range(P)]
                vpath = min_cut(err)
            if py > 0:
                err = [[(wg.L[(py + r) * cw + px + c] - nL[r][c] - cor[r][c]) ** 2
                        for r in range(OV)] for c in range(P)]
                hpath = min_cut(err)
            for r in range(P):
                for c in range(P):
                    i = (py + r) * cw + px + c
                    if wg.filled[i]:
                        if vpath is not None and c < vpath[r]:
                            continue
                        if hpath is not None and r < hpath[c]:
                            continue
                    j = (cy + r) * src.w + cx + c
                    k = cor[r][c]
                    wg.R[i], wg.G[i], wg.B[i], wg.L[i] = src.R[j] + k, src.G[j] + k, src.B[j] + k, src.L[j] + k
                    wg.filled[i] = True
                    wg.S[i] = (src, j, len(placed) - 1)
    return wg


TONE_R, FADE, TONE_K = 6, 16, 0.7


def smooth(v, rad):
    n = len(v)
    return [sum(v[max(0, i - rad):i + rad + 1]) / len(v[max(0, i - rad):i + rad + 1]) for i in range(n)]


def fade(t):
    """correction weight at distance t from the piece's left/top edge: 1 inside the overlap, then a
    smoothstep down to 0 over FADE px"""
    if t < OV:
        return 1.0
    u = (t - OV) / float(FADE)
    if u >= 1:
        return 0.0
    return 1 - u * u * (3 - 2 * u)


def repeat_report(wings, sources, placed, path, near=(20, 480), min_area=150):
    """Pixels of the 16:9 wings that show the same spot of one 128-px marble layout (same group),
    binned by their displacement. A real duplicate is a large area at one displacement."""
    spots = {}
    for side, wg in enumerate(wings):
        for y in range(H):
            for x in range(WING):
                src, j, _ = wg.S[y * wg.w + x]
                ax, ay = src.back(j % src.w, j // src.w)
                gx = x if side == 0 else WING + 640 + x
                spots.setdefault((src.group, ax % TILE, ay % TILE), []).append((gx, y, src.variant))
    bins = {}
    for lst in spots.values():
        for i in range(len(lst)):
            for k in range(i + 1, len(lst)):
                a, b = lst[i], lst[k]
                dx, dy = b[0] - a[0], b[1] - a[1]
                if near[0] < math.hypot(dx, dy) < near[1]:
                    key = (dx // 4 * 4, dy // 4 * 4, a[2] == b[2])
                    bins[key] = bins.get(key, 0) + 1
    top = sorted(bins.items(), key=lambda kv: -kv[1])[:20]
    # any orientation: pairs of pieces that show the same marble spots (turned or flipped copies)
    owners = {}
    for side, wg in enumerate(wings):
        for y in range(H):
            for x in range(WING):
                src, j, pi = wg.S[y * wg.w + x]
                ax, ay = src.back(j % src.w, j // src.w)
                owners.setdefault((src.group, ax % TILE, ay % TILE), set()).add(pi)
    shared = {}
    for s in owners.values():
        if len(s) > 1:
            s = sorted(s)
            for i in range(len(s)):
                for k in range(i + 1, len(s)):
                    shared[(s[i], s[k])] = shared.get((s[i], s[k]), 0) + 1
    rows = []
    for (p, q), n in shared.items():
        a, b = placed[p], placed[q]
        dist = math.hypot(a[3] - b[3], a[4] - b[4])
        if dist < near[1]:
            rows.append((n, dist, a, b))
    rows.sort(key=lambda r: -r[0])
    with open(path, 'w') as f:
        f.write('same marble spot shown twice within %d..%d px (16:9 wings, both sides)\n' % near)
        f.write('displacement (dx,dy)  same orientation  pixels\n')
        for (dx, dy, same), n in top:
            f.write('  (%4d,%4d)  %-5s  %5d%s\n' % (dx, dy, same, n, '   <-- duplicate area' if n >= min_area else ''))
        f.write('\npieces showing the same marble spots in any orientation, closer than %d px\n' % near[1])
        for n, dist, a, b in rows[:20]:
            f.write('  %4d spots  %3.0f px apart  side %d (%3d,%3d) %-5s  side %d (%3d,%3d) %-5s%s\n'
                    % (n, dist, a[6], a[8], a[9], a[7], b[6], b[8], b[9], b[7],
                       '   same orientation' if a[5] == b[5] and a[7].split('/')[0][0] == b[7].split('/')[0][0] else ''))
    worst = top[0][1] if top else 0
    print('repeat report: largest same-spot area %d px (%s)' % (worst, path), flush=True)


# ---------------------------------------------------------------- whole-wing tone
def robust_row_means(wg, x0=0, x1=WING, lo=0.2, hi=0.8):
    """per row: the mean of the middle 60% of the brightness values (cracks and specks ignored)"""
    out = []
    for y in range(H):
        v = sorted(wg.L[y * wg.w + x] for x in range(x0, x1))
        a, b = int(len(v) * lo), int(len(v) * hi)
        out.append(sum(v[a:b]) / (b - a))
    return out


def row_equalize(wg, strength, side, r_small=6, r_big=40, inner=64, ramp=24):
    """remove the band part of the row brightness profile (smoothed over 13 rows minus smoothed over
    81 rows), so no horizontal band of 13-80 rows can remain; single cracks are ignored (robust
    means). Two passes: the 16:10 part (the inner 64 columns next to the window, faded out over 24
    more columns), then the whole 16:9 width."""
    x0, x1 = (WING - inner, WING) if side == 0 else (0, inner)
    for cols, weight in (((x0, x1), lambda x: max(0.0, 1.0 - max(x0 - x, x - (x1 - 1), 0) / float(ramp))),
                         ((0, WING), lambda x: 1.0)):
        rm = robust_row_means(wg, *cols)
        s, S = smooth(rm, r_small), smooth(rm, r_big)
        wts = [weight(x) for x in range(wg.w)]
        for y in range(H):
            d = -strength * (s[y] - S[y])
            for x in range(wg.w):
                if wts[x] <= 0:
                    continue
                i = y * wg.w + x
                k = d * wts[x]
                wg.R[i] += k
                wg.G[i] += k
                wg.B[i] += k
                wg.L[i] += k


def level(wg):
    """shift the wing (columns 0..WING-1, rows 0..H-1) to the window marble's mean colour"""
    n = WING * H
    for ch, t in ((wg.R, TARGET[0]), (wg.G, TARGET[1]), (wg.B, TARGET[2])):
        d = t - sum(ch[y * wg.w + x] for y in range(H) for x in range(WING)) / n
        for i in range(len(ch)):
            ch[i] += d
    for i in range(len(wg.L)):
        wg.L[i] = lum(wg.R[i], wg.G[i], wg.B[i])


# ---------------------------------------------------------------- edge, encode, output
def encode(r, g, b):
    """like scripts\\art\\stretch_quilt.encode: shown as r>>3, g>>3, b>>3 (green survives 565->555)"""
    return ((r >> 3) << 11) | (min(63, 2 * (g >> 3) + 1) << 5) | (b >> 3)


def shown(v):
    return (((v >> 11) & 31) * 255 // 31, ((v >> 6) & 31) * 255 // 31, (v & 31) * 255 // 31)


def edge_gain(d, e, side, opt):
    """d: distance to the window (0 = column next to it), e: distance to the screen edge."""
    k = 1.0
    if opt['edge'] == 'makewings':
        # scripts\art\make_wings.py: dark seam, 2 px shadow, bevel highlight (for comparison only)
        k = {0: 0.3, 1: 0.5, 2: 0.5, 3: 1.4, 4: 1.12, 5: 1.12}.get(d, 1.0)
    if side == 1:
        k *= 1.0 - opt['rshadow'] * math.exp(-d / opt['rtau'])
    else:
        k *= 1.0 - opt['lshadow'] * math.exp(-d / opt['ltau'])
    k *= 1.0 - opt['screen'] * math.exp(-e / opt['stau'])
    return k


def make_frame(W, wings, opt):
    ox = (W - 640) // 2
    rows_px = [[(0, 0, 0)] * W for _ in range(H)]
    vals = [[0] * W for _ in range(H)]
    for side in (0, 1):
        wg = wings[side]
        for x in range(ox):
            # wing column -> quilted column: 16:10 uses the inner part of the 16:9 wing
            if side == 0:
                qx = WING - ox + x
                d, e, sx = ox - 1 - x, x, x
            else:
                qx = x
                d, e, sx = x, ox - 1 - x, ox + 640 + x
            for y in range(H):
                i = y * wg.w + qx
                k = edge_gain(d, e, side, opt)
                # at least 8: a 5:5:5 pixel 0x0000 would be transparent in the game
                c = [max(8, min(255, int(round(v * k)))) for v in (wg.R[i], wg.G[i], wg.B[i])]
                rows_px[y][sx] = tuple(c)
                vals[y][sx] = encode(*c)
    return rows_px, vals


def write_sti(path, W, vals):
    head = bytearray(open(TEMPLATE % W, 'rb').read()[:64])
    assert struct.unpack_from('<HH', head, 20) == (H, W)
    data = struct.pack('<%dH' % (W * H), *[v for row in vals for v in row])
    struct.pack_into('<II', head, 4, W * H * 2, W * H * 2)
    open(path, 'wb').write(bytes(head) + data)


LUT = [min(255, round((i / 255.0) ** 0.45 * 255)) for i in range(256)]


def boosted(rows, zoom=2):
    out = []
    for r in rows:
        line = []
        for p in r:
            q = (LUT[p[0]], LUT[p[1]], LUT[p[2]])
            line.extend([q] * zoom)
        for _ in range(zoom):
            out.append(line)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--slf', default=SLF_DEFAULT)
    ap.add_argument('--out', default=os.path.join(ROOT, r'build\tmp\native-wings\out'))
    ap.add_argument('--capture', default=CAPTURE_DEFAULT)
    ap.add_argument('--seed', type=int, default=21)
    ap.add_argument('--rshadow', type=float, default=0.0)
    ap.add_argument('--rtau', type=float, default=3.0)
    ap.add_argument('--lshadow', type=float, default=0.0)
    ap.add_argument('--ltau', type=float, default=2.0)
    ap.add_argument('--screen', type=float, default=0.18)
    ap.add_argument('--stau', type=float, default=10.0)
    ap.add_argument('--flatten', type=float, default=0.0)
    ap.add_argument('--box-thr', type=float, default=0.6, help='box motif NCC threshold (0 = no exclusion)')
    ap.add_argument('--roweq', type=float, default=1.0, help='row band removal strength (0 = off)')
    ap.add_argument('--no-level', action='store_true')
    ap.add_argument('--edge', choices=('flush', 'makewings'), default='flush')
    ap.add_argument('--no-composites', action='store_true')
    a = ap.parse_args()
    opt = vars(a)
    files = slf_read(a.slf, sorted({r[1] for r in REGIONS}))
    for d in ('wings', 'composites', 'boost', 'compare'):
        os.makedirs(os.path.join(a.out, d), exist_ok=True)
    if a.box_thr > 0:
        log = []
        EXCL.update(find_box(read_frames(files), a.box_thr, log))
        open(os.path.join(a.out, 'wings', 'box_exclusions.txt'), 'w').write(
            'box crack motif, NCC threshold %.2f\n' % a.box_thr + '\n'.join(log) + '\n')
        print('box motif: %d excluded spots' % sum(len(v) for v in EXCL.values()), flush=True)
    sources = prepare_sources(files, flatten=a.flatten)
    rng = random.Random(a.seed)
    placed = []
    wings = []
    for side in (0, 1):
        wings.append(quilt(sources, rng, placed, side, gx0=0 if side == 0 else WING + 640))
        print('side', side, 'pieces', sum(1 for q in placed if q[6] == side), flush=True)
    for side, wg in enumerate(wings):
        if a.roweq > 0:
            row_equalize(wg, a.roweq, side)
        if not a.no_level:
            level(wg)
    with open(os.path.join(a.out, 'wings', 'pieces.txt'), 'w') as f:
        for q in placed:
            f.write('side %d  out (%3d,%3d)  from %-6s group %s  tile spot (%3d,%3d)\n'
                    % (q[6], q[8], q[9], q[7], q[0], q[1] % TILE, q[2] % TILE))
    frames = {}
    for W in (768, 856):
        rows_px, vals = make_frame(W, wings, opt)
        srows = [[shown(v) if v else (0, 0, 0) for v in row] for row in vals]
        artkit.write_png(os.path.join(a.out, 'wings', 'wing_%d.png' % W), W, H, rows_px, False)
        artkit.write_png(os.path.join(a.out, 'wings', 'wing_%d_shown.png' % W), W, H, srows, False)
        write_sti(os.path.join(a.out, 'wings', 'WIDEFRAME_%d.STI' % W), W, vals)
        frames[W] = srows
    repeat_report(wings, sources, placed, os.path.join(a.out, 'wings', 'repeats.txt'))
    cdir = os.path.join(a.capture, 'canvas')
    if a.no_composites:
        return
    if not os.path.isdir(cdir):
        print('no captures in %s: wings only, no composites' % cdir)
        return
    tmp = os.path.join(a.out, 'composites_exact')
    os.makedirs(tmp, exist_ok=True)
    for fn in sorted(os.listdir(cdir)):
        if not fn.endswith('.png'):
            continue
        name = fn[:-4]
        screen, W = name.rsplit('_', 1)
        W = int(W)
        cw, chh, cap = artkit.read_png(os.path.join(cdir, fn))
        assert (cw, chh) == (W, H)
        ox = (W - 640) // 2
        sides = list(range(ox)) + list(range(ox + 640, W))
        # exact frame: the static window background rebuilt from the game's pieces by the capture step
        # (palette colours shown as 5:5:5; runtime holes = magenta, filled from the capture) + the wing
        nw, nh, nat = artkit.read_png(os.path.join(a.capture, 'native', screen + '_native640.png'))
        exact = [list(r) for r in cap]
        for y in range(H):
            for x in range(640):
                p = nat[y][x]
                if p != (255, 0, 255):
                    exact[y][ox + x] = tuple((c >> 3) * 255 // 31 for c in p)
            for x in sides:
                exact[y][x] = frames[W][y][x]
        ep = os.path.join(tmp, name + '.png')
        artkit.write_png(ep, W, H, exact, False)
        # the capture with its side bars replaced by the exact wing (the captures are a little soft, the
        # wing is not: judge the joint on composites_exact, the overall look here)
        comp = [list(r) for r in cap]
        for y in range(H):
            for x in sides:
                comp[y][x] = exact[y][x]
        artkit.write_png(os.path.join(a.out, 'composites', name + '.png'), W, H, comp, False)
        artkit.write_png(os.path.join(a.out, 'boost', name + '_boost.png'), W * 2, H * 2, boosted(comp), False)
        cmp_rows = []
        for top in (cap, comp):
            b = boosted(top, 1)
            for y in range(H):
                cmp_rows.append(list(top[y]) + [(255, 255, 255)] * 8 + list(b[y]))
            if top is cap:
                cmp_rows.extend([[(255, 255, 255)] * (2 * W + 8)] * 8)
        artkit.write_png(os.path.join(a.out, 'compare', name + '.png'), 2 * W + 8, 2 * H + 8, cmp_rows, False)
        print('composite', name, flush=True)


if __name__ == '__main__':
    main()
