"""Disassembles one function of the original Wiz8.exe (GOG 1.2.4) by address.
python -I retail_asm.py 0x00536570 [--bytes N]
Function end = the next address from the annotations `// FUNCTION: WIZ8 0x...` in
decomp (the list is cached in scripts\\__pycache__\\func_addrs.txt), but no
more than 0x3000 bytes. Needs llvm-objdump from Tools (env.ps1 puts it on PATH;
the script also looks for it itself). Read-only."""
import os
import re
import subprocess
import sys

ROOT = r'C:\dev\wiz8-ws'
EXE = os.path.join(ROOT, 'ghidra', 'bin', 'Wiz8.exe')
SRC = os.path.join(ROOT, 'decomp', 'src')
CACHE = os.path.join(ROOT, 'scripts', '__pycache__', 'func_addrs.txt')


def find_objdump():
    for base, _dirs, files in os.walk(os.path.join(ROOT, 'Tools')):
        if 'llvm-objdump.exe' in files:
            return os.path.join(base, 'llvm-objdump.exe')
    return 'llvm-objdump'


def addresses():
    if os.path.exists(CACHE):
        return [int(x, 16) for x in open(CACHE).read().split()]
    pat = re.compile(r'//\s*(?:FUNCTION|STUB|LIBRARY|TEMPLATE|SYNTHETIC):\s*WIZ8\s+(0x[0-9a-fA-F]+)')
    found = set()
    for base, _dirs, files in os.walk(SRC):
        for name in files:
            if name.endswith(('.cpp', '.c', '.h', '.hpp')):
                with open(os.path.join(base, name), encoding='utf-8', errors='replace') as f:
                    for line in f:
                        m = pat.search(line)
                        if m:
                            found.add(int(m.group(1), 16))
    out = sorted(found)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, 'w') as f:
        f.write('\n'.join('%x' % a for a in out))
    return out


def main():
    start = int(sys.argv[1], 16)
    limit = 0x3000
    if '--bytes' in sys.argv:
        limit = int(sys.argv[sys.argv.index('--bytes') + 1], 0)
    addrs = addresses()
    end = start + limit
    for a in addrs:
        if a > start:
            end = min(end, a)
            break
    cmd = [find_objdump(), '-d', '--no-show-raw-insn', '-M', 'intel',
           '--start-address=0x%x' % start, '--stop-address=0x%x' % end, EXE]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    lines = out.splitlines()
    # skip the objdump header
    body = [l for l in lines if re.match(r'^\s+[0-9a-f]+:', l)]
    print('; retail 0x%x .. 0x%x (%d bytes)' % (start, end, end - start))
    print('\n'.join(body))


main()
