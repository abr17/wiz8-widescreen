"""Toolkit for extending (outpainting) backgrounds to wide screen (no third-party libraries).
  python artkit.py prep <in.sti> <outdir> <W>
      -> <name>_orig.png (640x480), <name>_W_input.png (original centered, side margins transparent),
         <name>_W_mask.png (white = to be painted), <name>_W_placeholder.png (margins = blurred mirror of the edges)
  python artkit.py tosti <in.png> <template.sti> <out.sti>
      -> 16-bit STI from PNG (8-bit RGB/RGBA, non-interlaced)"""
import os
import struct
import sys
import zlib


def read_sti16(path):
    d = open(path, 'rb').read()
    assert d[:4] == b'STCI'
    h, w = struct.unpack_from('<HH', d, 20)
    vals = struct.unpack_from(f'<{w*h}H', d, 64)
    px = [(((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31) for v in vals]
    return d[:64], w, h, px


def write_png(path, w, h, rows, alpha):
    ch = 4 if alpha else 3
    raw = b''.join(b'\0' + bytes(c for p in row for c in p[:ch]) for row in rows)

    def chunk(t, data):
        return struct.pack('>I', len(data)) + t + data + struct.pack('>I', zlib.crc32(t + data) & 0xffffffff)
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 6 if alpha else 2, 0, 0, 0)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def read_png(path):
    d = open(path, 'rb').read()
    assert d[:8] == b'\x89PNG\r\n\x1a\n'
    pos, idat, w = 8, b'', 0
    while pos < len(d):
        n, = struct.unpack_from('>I', d, pos)
        t = d[pos + 4:pos + 8]
        data = d[pos + 8:pos + 8 + n]
        if t == b'IHDR':
            w, h, depth, ctype, _, _, inter = struct.unpack('>IIBBBBB', data)
            assert depth == 8 and ctype in (2, 6) and inter == 0, 'need 8-bit RGB/RGBA non-interlaced PNG'
        elif t == b'IDAT':
            idat += data
        pos += 12 + n
    bpp = 3 if ctype == 2 else 4
    raw = zlib.decompress(idat)
    stride = w * bpp
    rows, prev, i = [], bytearray(stride), 0
    for _ in range(h):
        f = raw[i]; line = bytearray(raw[i + 1:i + 1 + stride]); i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if f == 1: line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + b) & 255
            elif f == 3: line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c; pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append([tuple(line[x * bpp:x * bpp + 3]) for x in range(w)])
        prev = line
    return w, h, rows


def prep(sti, outdir, W):
    _, w, h, px = read_sti16(sti)
    name = os.path.splitext(os.path.basename(sti))[0].lower()
    os.makedirs(outdir, exist_ok=True)
    rows = [px[y * w:(y + 1) * w] for y in range(h)]
    write_png(os.path.join(outdir, f'{name}_orig.png'), w, h, rows, False)
    ox = (W - w) // 2
    inp, mask, ph = [], [], []
    for y in range(h):
        r = rows[y]
        inp.append([(0, 0, 0, 0)] * ox + [p + (255,) for p in r] + [(0, 0, 0, 0)] * (W - w - ox))
        mask.append([(255, 255, 255)] * ox + [(0, 0, 0)] * w + [(255, 255, 255)] * (W - w - ox))
        left = [r[min(w - 1, ox - 1 - x)] for x in range(ox)]          # mirror of the left edge
        right = [r[max(0, w - 1 - x)] for x in range(W - w - ox)]       # mirror of the right edge
        ph.append(left + r + right)
    # simple blur and darkening of the margins so the mirror is not conspicuous
    def blur_dark(row, x0, x1, dist):
        out = list(row)
        for x in range(x0, x1):
            acc = [0, 0, 0]; n = 0
            for dx in range(-6, 7):
                xx = min(max(x + dx, x0), x1 - 1); p = row[xx]
                acc[0] += p[0]; acc[1] += p[1]; acc[2] += p[2]; n += 1
            k = max(0.35, 1 - dist(x) / (ox * 1.6))
            out[x] = tuple(int(c / n * k) for c in acc)
        return out
    ph = [blur_dark(blur_dark(r, 0, ox, lambda x: ox - x), ox + w, W, lambda x: x - ox - w + 1) for r in ph]
    write_png(os.path.join(outdir, f'{name}_{W}_input.png'), W, h, inp, True)
    write_png(os.path.join(outdir, f'{name}_{W}_mask.png'), W, h, mask, False)
    write_png(os.path.join(outdir, f'{name}_{W}_placeholder.png'), W, h, ph, False)
    print('ok', name, W)


BAYER4 = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))


def _q565(v, levels, x, y):
    """Channel 0..255 -> level 0..levels. A color that maps exactly to a level
    (original pixels read by read_sti16) is converted back unchanged.
    Others (the painted extension) use 4x4 Bayer ordered dithering, as in the
    game's original images: otherwise a smooth extension next to the "grainy"
    original shows up as a band (2026-10-12)."""
    lvl = (v * levels + 127) // 255
    if lvl * 255 // levels == v:
        return lvl
    t = (BAYER4[y & 3][x & 3] + 0.5) / 16.0
    return min(levels, int(v * levels / 255.0 + t))


def tosti(png, template, out, dither=True):
    head = bytearray(open(template, 'rb').read()[:64])
    w, h, rows = read_png(png)
    if dither:
        px = struct.pack(f'<{w*h}H', *[(_q565(r, 31, x, y) << 11) | (_q565(g, 63, x, y) << 5) | _q565(b, 31, x, y)
                                       for y, row in enumerate(rows) for x, (r, g, b) in enumerate(row)])
    else:
        px = struct.pack(f'<{w*h}H', *[(((r * 31 + 127) // 255) << 11) | (((g * 63 + 127) // 255) << 5) | ((b * 31 + 127) // 255) for row in rows for r, g, b in row])
    struct.pack_into('<II', head, 4, w * h * 2, w * h * 2)
    struct.pack_into('<HH', head, 20, h, w)
    open(out, 'wb').write(bytes(head) + px)
    print('ok', out, w, h)


def seamfix(png, out, inner_w=640, fade=48):
    """Removes the seam between the center (original) and the painted margins: in each row
    pulls margin brightness/color toward the original's edge, fading out deeper into the margin."""
    w, h, rows = read_png(png)
    ox = (w - inner_w) // 2
    res = []
    for y in range(h):
        r = [list(p) for p in rows[y]]
        y0, y1 = max(0, y - 6), min(h, y + 7)
        for side in (0, 1):
            if side == 0:
                cen = [rows[yy][x] for yy in range(y0, y1) for x in range(ox, ox + 6)]
                edge = [rows[yy][x] for yy in range(y0, y1) for x in range(ox - 6, ox)]
            else:
                cen = [rows[yy][x] for yy in range(y0, y1) for x in range(ox + inner_w - 6, ox + inner_w)]
                edge = [rows[yy][x] for yy in range(y0, y1) for x in range(ox + inner_w, ox + inner_w + 6)]
            d = [sum(p[c] for p in cen) / len(cen) - sum(p[c] for p in edge) / len(edge) for c in range(3)]
            for k in range(min(fade, ox)):
                x = ox - 1 - k if side == 0 else ox + inner_w + k
                t = 1 - k / fade
                for c in range(3):
                    r[x][c] = max(0, min(255, int(r[x][c] + d[c] * t)))
        res.append([tuple(p) for p in r])
    write_png(out, w, h, res, False)
    print('ok', out)


def cropcenter(png, out, w_out):
    """Cuts out the central strip of width w_out (e.g. 768 out of 856)."""
    w, h, rows = read_png(png)
    x0 = (w - w_out) // 2
    write_png(out, w_out, h, [r[x0:x0 + w_out] for r in rows], False)
    print('ok', out, w_out, h)


if __name__ == '__main__':
    if sys.argv[1] == 'crop':
        cropcenter(sys.argv[2], sys.argv[3], int(sys.argv[4]))
        sys.exit()
    if sys.argv[1] == 'seamfix':
        seamfix(sys.argv[2], sys.argv[3])
        sys.exit()
    if sys.argv[1] == 'prep':
        prep(sys.argv[2], sys.argv[3], int(sys.argv[4]))
    elif sys.argv[1] == 'tosti':
        tosti(sys.argv[2], sys.argv[3], sys.argv[4])
