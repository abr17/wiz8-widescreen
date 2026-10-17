"""Translate addresses from a report (WIZ8_RUNTIME_CANDIDATE ... address=XXXXXXXX) into function names via the .map.
python -I scripts\tools\port_symbolize.py <Wiz8Runtime.map> <report.txt>   (port only; for the hybrid use scripts\hybrid\symbolize.py)"""
import bisect
import re
import sys

syms = []
for line in open(sys.argv[1], encoding='latin1'):
    m = re.match(r'\s*[0-9a-f]{4}:[0-9a-f]{8}\s+(\S+)\s+([0-9a-f]{8})\s+(f\s+)?(\S+)?', line, re.I)
    if m:
        syms.append((int(m.group(2), 16), m.group(1), m.group(4) or ''))
syms.sort()
addrs = [s[0] for s in syms]
for line in open(sys.argv[2], encoding='latin1'):
    m = re.search(r'source=(\S+) address=([0-9a-f]{8})', line)
    if not m:
        continue
    a = int(m.group(2), 16)
    i = bisect.bisect_right(addrs, a) - 1
    if i >= 0:
        base, name, obj = syms[i]
        print(f'{m.group(1):12} {a:08x}  {name}+0x{a-base:x}  [{obj}]')
