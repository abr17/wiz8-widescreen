"""Split the annotated functions of files into chunks for comparison with the original.
python -I audit_chunks.py <max_lines> <file> [file ...]  (paths relative to decomp\\src\\wiz8)
Prints JSON: [{"file", "first_line", "last_line", "functions": [{"addr","line","name"}]}]."""
import json
import os
import re
import sys

BASE = r'C:\dev\wiz8-ws\decomp\src\wiz8'
pat = re.compile(r'^//\s*FUNCTION:\s*WIZ8\s+(0x[0-9a-fA-F]+)')
max_lines = int(sys.argv[1])
chunks = []
for rel in sys.argv[2:]:
    path = os.path.join(BASE, rel)
    lines = open(path, encoding='utf-8', errors='replace').read().split('\n')
    funcs = []
    for i, line in enumerate(lines):
        m = pat.match(line)
        if m:
            name = ''
            for j in range(i + 1, min(i + 6, len(lines))):
                if '(' in lines[j] and not lines[j].lstrip().startswith('//'):
                    name = lines[j].strip()
                    break
            funcs.append({'addr': m.group(1).lower(), 'line': i + 1, 'name': name[:120]})
    for k, f in enumerate(funcs):
        f['end'] = funcs[k + 1]['line'] - 1 if k + 1 < len(funcs) else len(lines)
    cur = None
    for f in funcs:
        size = f['end'] - f['line'] + 1
        if cur is None or (cur['size'] + size > max_lines and cur['functions']):
            cur = {'file': rel, 'functions': [], 'size': 0}
            chunks.append(cur)
        cur['functions'].append({'addr': f['addr'], 'line': f['line'], 'name': f['name']})
        cur['size'] += size
        cur['last_line'] = f['end']
    for c in chunks:
        if c['file'] == rel and 'first_line' not in c:
            c['first_line'] = c['functions'][0]['line']
print(json.dumps(chunks, ensure_ascii=False))
