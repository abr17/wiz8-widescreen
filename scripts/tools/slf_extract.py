"""Extract file(s) from an .SLF by name (case-insensitive, a partial path is allowed).
python slf_extract.py <file.SLF> <name> <dest_dir>
Files are written preserving the archive's subfolders."""
import os
import struct
import sys

slf, needle, out_dir = sys.argv[1], sys.argv[2].lower(), sys.argv[3]
with open(slf, 'rb') as f:
    entries = struct.unpack_from('<i', f.read(532), 512)[0]
    f.seek(0, 2)
    size = f.tell()
    f.seek(size - entries * 280)
    table = f.read(entries * 280)
    n = 0
    for i in range(entries):
        r = table[i * 280:(i + 1) * 280]
        name = r[:256].split(b'\0')[0].decode('latin1')
        off, length, state = struct.unpack_from('<IIB', r, 256)
        if state or needle not in name.lower():
            continue
        f.seek(off)
        data = f.read(length)
        dst = os.path.join(out_dir, *name.split('\\'))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, 'wb').write(data)
        print(f'{length:9}  {dst}')
        n += 1
print(f'-- {n} file(s)')
