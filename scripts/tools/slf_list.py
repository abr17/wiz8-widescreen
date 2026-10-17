"""List files in an .SLF archive (Sir-Tech SGP format, as in Jagged Alliance 2).
Read-only. Usage: python slf_list.py <file.SLF> [--summary]"""
import collections
import struct
import sys

path = sys.argv[1]
with open(path, 'rb') as f:
    head = f.read(532)
    lib, libpath = head[:256].split(b'\0')[0], head[256:512].split(b'\0')[0]
    entries, used = struct.unpack_from('<ii', head, 512)
    f.seek(0, 2)
    size = f.tell()
    rec = 280
    f.seek(size - entries * rec)
    table = f.read(entries * rec)

files = []
for i in range(entries):
    r = table[i * rec:(i + 1) * rec]
    name = r[:256].split(b'\0')[0].decode('latin1')
    off, length, state = struct.unpack_from('<IIB', r, 256)
    if state == 0:
        files.append((name, off, length))

print(f'lib={lib!r} path={libpath!r} entries={entries} used={used} live={len(files)}')
if '--summary' in sys.argv:
    by_ext = collections.Counter(n.rsplit('.', 1)[-1].upper() for n, _, _ in files)
    by_dir = collections.Counter(n.rsplit('\\', 1)[0] if '\\' in n else '.' for n, _, _ in files)
    print('ext:', by_ext.most_common())
    print('dirs:')
    for d, c in sorted(by_dir.items()):
        print(f'  {c:5}  {d}')
else:
    for n, o, l in files:
        print(f'{l:10}  {n}')
