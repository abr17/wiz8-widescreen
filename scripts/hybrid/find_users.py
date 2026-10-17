"""Which original functions access an address range (search for dword constants in code).
python -I find_users.py 0x652ddc:0x12c0 0x654adc:0x4b00
Prints function addresses (from port annotations) and reference counts. False positives
are possible (accidental byte matches), misses are almost impossible (the address of a global
variable in x86 code is always stored whole)."""
import bisect
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'w8diff'))
from w8diff.symbols import Symbols, ROOT  # noqa: E402

EXE = os.path.join(ROOT, 'ghidra', 'bin', 'Wiz8.exe')


def text_section(data):
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    nsec = struct.unpack_from('<H', data, pe + 6)[0]
    opt = struct.unpack_from('<H', data, pe + 20)[0]
    base = struct.unpack_from('<I', data, pe + 24 + 28)[0]
    sec = pe + 24 + opt
    for i in range(nsec):
        name, vsize, vaddr, rsize, raddr = struct.unpack_from('<8sIIII', data, sec + i * 40)
        if name.rstrip(b'\0') == b'.text':
            return base + vaddr, data[raddr:raddr + min(vsize, rsize)]
    raise SystemExit('no .text')


def users(ranges):
    data = open(EXE, 'rb').read()
    start, code = text_section(data)
    syms = Symbols()
    addrs = sorted({f['addr'] for f in syms.funcs})
    names = {}
    for f in syms.funcs:
        names.setdefault(f['addr'], f['name'])
    hits = {}
    for off in range(len(code) - 3):
        v = struct.unpack_from('<I', code, off)[0]
        for lo, size in ranges:
            if lo <= v < lo + size:
                va = start + off
                k = bisect.bisect_right(addrs, va) - 1
                if k >= 0:
                    fa = addrs[k]
                    hits[fa] = hits.get(fa, 0) + 1
    return [(fa, names[fa], n) for fa, n in sorted(hits.items())]


if __name__ == '__main__':
    rs = []
    for arg in sys.argv[1:]:
        lo, size = arg.split(':')
        rs.append((int(lo, 16), int(size, 16)))
    for fa, name, n in users(rs):
        print('0x%08x %-50s %d' % (fa, name, n))
