"""Remove the pinkish tint of 16-bit images that the game draws next to the original
(palette-based) UI: the marble wings Data\\Wide\\WideFrame_<W>.sti.
python -I neutralize_wings.py <in.sti> <out.sti>

Cause of the tint: the file is RGB 5:6:5 while the game's surfaces are 5:5:5. On load, SGP
(ConvertRGBDistribution565To555, himage.cpp) simply drops the low bit
of green, i.e. rounds it down, whereas artkit encodes red and blue with
round-to-nearest. On dark stone (~22 of 255) that is about -4 in green:
on-screen R:G:B 1.18:1:1.10 instead of ~1.05:1:1.02 for the original marble. Here green
is re-encoded so that after the bit is dropped the nearest value remains:
G6 = 2*round(G6/2.03) + 1. Red and blue, black 0 and dimensions are unchanged."""
import struct
import sys


def main():
    src, dst = sys.argv[1], sys.argv[2]
    d = open(src, 'rb').read()
    assert d[:4] == b'STCI'
    h, w = struct.unpack_from('<HH', d, 20)
    vals = list(struct.unpack_from('<%dH' % (w * h), d, 64))
    bayer = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))
    sg_old = sg_new = n = 0
    for i, v in enumerate(vals):
        if v == 0:
            continue
        x, y = i % w, i // w
        g6 = (v >> 5) & 63
        g8 = g6 * 255.0 / 63
        # 5-bit green with the same ordered dithering as R and B in artkit:
        # on average this gives the original brightness rather than rounding down
        t = (bayer[y & 3][x & 3] + 0.5) / 16.0
        g5 = min(31, int(g8 * 31 / 255.0 + t))
        g6n = min(63, 2 * g5 + 1)
        vals[i] = (v & 0xF81F) | (g6n << 5)
        sg_old += g6 >> 1
        sg_new += g6n >> 1
        n += 1
    out = bytearray(d[:64]) + struct.pack('<%dH' % (w * h), *vals) + d[64 + 2 * w * h:]
    open(dst, 'wb').write(out)
    print('%s: %dx%d, mean displayed G5 %.2f -> %.2f' % (dst, w, h, sg_old / n, sg_new / n))


if __name__ == '__main__':
    main()
