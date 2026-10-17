"""8-bit (palette, ETRLE) STI -> PNG. Read-only.
python sti8.py <in.sti> <outdir>
-> <name>_<i>.png for each frame (RGBA, index 0 transparent) and <name>_all.png:
   all frames on one canvas at their offsets (as the game places them from point 0,0)."""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
import artkit


def read_sti8(path):
    d = open(path, 'rb').read()
    assert d[:4] == b'STCI'
    flags, = struct.unpack_from('<I', d, 16)
    assert flags & 0x8, 'not an indexed STI'
    count, = struct.unpack_from('<H', d, 28)
    app_size, = struct.unpack_from('<I', d, 45)
    pal_off = 64
    pal = [tuple(d[pal_off + i * 3:pal_off + i * 3 + 3]) for i in range(256)]
    sub_off = pal_off + 768
    data_off = sub_off + count * 16
    frames = []
    for i in range(count):
        off, length, sx, sy, h, w = struct.unpack_from('<IIhhHH', d, sub_off + i * 16)
        src = d[data_off + off:data_off + off + length]
        px = [[None] * w for _ in range(h)]
        if flags & 0x20:  # ETRLE
            p = 0
            for y in range(h):
                x = 0
                while p < len(src):
                    b = src[p]; p += 1
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
        frames.append((sx, sy, w, h, px))
    return pal, frames


def to_rgba(pal, px):
    return [[(0, 0, 0, 0) if v is None else pal[v] + (255,) for v in row] for row in px]


if __name__ == '__main__':
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    name = os.path.splitext(os.path.basename(src))[0].lower()
    pal, frames = read_sti8(src)
    W = max(sx + w for sx, sy, w, h, px in frames)
    H = max(sy + h for sx, sy, w, h, px in frames)
    canvas = [[(0, 0, 0, 0)] * W for _ in range(H)]
    for i, (sx, sy, w, h, px) in enumerate(frames):
        rgba = to_rgba(pal, px)
        artkit.write_png(os.path.join(out, '%s_%d.png' % (name, i)), w, h, rgba, True)
        for y in range(h):
            for x in range(w):
                if rgba[y][x][3]:
                    canvas[sy + y][sx + x] = rgba[y][x]
        print('frame %d: %dx%d at (%d,%d)' % (i, w, h, sx, sy))
    artkit.write_png(os.path.join(out, name + '_all.png'), W, H, canvas, True)
    print('ok', name, len(frames), 'frames, canvas', W, H)
