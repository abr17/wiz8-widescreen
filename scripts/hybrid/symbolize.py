"""Map addresses (stdin, one hex per line) to functions: original Wiz8.exe via
port annotations, wiz8hy.dll via build\\hybrid\\wiz8hy.map. Argument: DLL base (hex)."""
import bisect
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'w8diff'))
from w8diff.symbols import Symbols, ROOT  # noqa: E402

dll_base = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0
syms = Symbols()
fa = sorted({f['addr']: f['name'] for f in syms.funcs}.items())
faddrs = [a for a, _ in fa]
dmap = []
mp = os.path.join(ROOT, 'build', 'hybrid', 'wiz8hy.map')
if dll_base and os.path.exists(mp):
    for line in open(mp, encoding='ascii', errors='replace'):
        m = re.match(r'^\s*[0-9a-f]{4}:[0-9a-f]{8}\s+(\S+)\s+([0-9a-f]{8})\s+f', line)
        if m:
            dmap.append((int(m.group(2), 16) - 0x10000000, m.group(1)))
    dmap.sort()
daddrs = [a for a, _ in dmap]
seen = 0
for line in sys.stdin:
    s = line.strip().lstrip('\ufeff')
    if not s:
        continue
    v = int(s, 16)
    if 0x401000 <= v < 0x5eb000:
        k = bisect.bisect_right(faddrs, v) - 1
        if k >= 0:
            print('%08x  retail %s+0x%x' % (v, fa[k][1], v - fa[k][0]))
            seen += 1
    elif dll_base and dll_base <= v < dll_base + 0x200000:
        r = v - dll_base
        k = bisect.bisect_right(daddrs, r) - 1
        if k >= 0:
            print('%08x  hybrid %s+0x%x' % (v, dmap[k][1], r - dmap[k][0]))
            seen += 1
    if seen > 60:
        break
