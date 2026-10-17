"""Address -> function from the Wiz8Runtime MSVC .map file. Read-only.
python map_lookup.py <Wiz8Runtime.map> <addr> [addr ...]"""
import bisect
import re
import sys

path = sys.argv[1]
syms = []
pat = re.compile(r'^\s*[0-9a-fA-F]{4}:[0-9a-fA-F]{8}\s+(\S+)\s+([0-9a-fA-F]{8})\s')
for line in open(path, encoding='latin1'):
    m = pat.match(line)
    if m:
        syms.append((int(m.group(2), 16), m.group(1)))
syms.sort()
addrs = [a for a, _ in syms]
for arg in sys.argv[2:]:
    a = int(arg, 16)
    i = bisect.bisect_right(addrs, a) - 1
    if i >= 0:
        print('%08x  %s+0x%x' % (a, syms[i][1], a - syms[i][0]))
    else:
        print('%08x  ?' % a)
