"""Catalog of images in DATA.SLF: STI/TGA/PCX sizes. Read-only.
python slf_images.py <DATA.SLF> [min_width]"""
import struct
import sys

path = sys.argv[1]
min_w = int(sys.argv[2]) if len(sys.argv) > 2 else 0
with open(path, 'rb') as f:
    head = f.read(532)
    entries = struct.unpack_from('<i', head, 512)[0]
    f.seek(0, 2)
    size = f.tell()
    f.seek(size - entries * 280)
    table = f.read(entries * 280)
    rows = []
    for i in range(entries):
        r = table[i * 280:(i + 1) * 280]
        name = r[:256].split(b'\0')[0].decode('latin1')
        off, length, state = struct.unpack_from('<IIB', r, 256)
        ext = name.rsplit('.', 1)[-1].upper()
        if state or ext not in ('STI', 'TGA', 'PCX'):
            continue
        f.seek(off)
        h = f.read(64)
        w = hh = 0
        kind = ext
        if ext == 'STI' and h[:4] == b'STCI':
            flags = struct.unpack_from('<I', h, 16)[0]
            hh, w = struct.unpack_from('<HH', h, 20)
            if flags & 8:  # indexed: the size in the header may be 0, take it from the sub-image
                nsub = struct.unpack_from('<H', h, 28)[0]
                kind = f'STI8x{nsub}'
                if w == 0 and nsub:
                    # 256*3 palette after the header, then the sub-image table (16 bytes: off,len,x,y,h,w)
                    f.seek(off + 64 + 768)
                    sub = f.read(16)
                    hh, w = struct.unpack_from('<HH', sub, 12)
            else:
                kind = 'STI16'
        elif ext == 'TGA':
            w, hh = struct.unpack_from('<HH', h, 12)
        elif ext == 'PCX':
            x0, y0, x1, y1 = struct.unpack_from('<HHHH', h, 4)
            w, hh = x1 - x0 + 1, y1 - y0 + 1
        rows.append((w, hh, kind, length, name))

rows = [r for r in rows if r[0] >= min_w]
rows.sort(key=lambda r: (-r[0] * r[1], r[4]))
for w, hh, kind, length, name in rows:
    print(f'{w:5}x{hh:<5} {kind:9} {length:9}  {name}')
print(f'-- {len(rows)} images')
