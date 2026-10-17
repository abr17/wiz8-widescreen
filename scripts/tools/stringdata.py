"""Game strings from StringData.DAT (gppStringList). Read-only.
python stringdata.py <StringData.DAT> <index|0xindex> [more ...]
python stringdata.py <StringData.DAT> --find <text>
Format: int32 string count, then for each string an int32 byte length and UTF-16,
each character encoded as ~c + 0x9697 (DecodeLocalizedText)."""
import struct
import sys


def load(path):
    data = open(path, 'rb').read()
    count = struct.unpack_from('<i', data, 0)[0]
    pos = 4
    out = []
    for _ in range(count):
        n = struct.unpack_from('<i', data, pos)[0]
        pos += 4
        chars = struct.unpack_from('<%dH' % (n // 2), data, pos)
        pos += n
        out.append(''.join(chr((~c + 0x9697) & 0xFFFF) for c in chars).rstrip('\0'))
    return out


strings = load(sys.argv[1])
sys.stdout.reconfigure(encoding='utf-8')
if len(sys.argv) > 3 and sys.argv[2] == '--find':
    needle = sys.argv[3].lower()
    for i, s in enumerate(strings):
        if needle in s.lower():
            print('0x%x %d: %s' % (i, i, s))
else:
    for arg in sys.argv[2:]:
        i = int(arg, 0)
        print('0x%x %d: %s' % (i, i, strings[i]))
