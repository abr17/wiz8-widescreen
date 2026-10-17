"""Addresses of functions and global variables in both exes.

retail: from the port's source annotations (// FUNCTION: WIZ8 0x..., // GLOBAL: WIZ8 0x...).
port:   from build\\vc2022\\Wiz8Runtime.map (Publics by Value + Static symbols),
        the name is recovered from the decorated one (llvm-cxxfilt for the signature).
Reads files only."""
import json
import os
import re
import subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
SRC = os.path.join(ROOT, 'decomp')
MAP = os.path.join(ROOT, 'build', 'vc2022', 'Wiz8Runtime.map')
CXXFILT = os.path.join(ROOT, 'Tools', 'llvm-mingw', 'bin', 'llvm-cxxfilt.exe')
CACHE = os.path.join(ROOT, 'build', 'w8diff', 'symbols_cache.json')

ANN = re.compile(r'^\s*//\s*(FUNCTION|GLOBAL):\s*WIZ8\s+(0x[0-9a-fA-F]+)')
IDENT_BEFORE_PAREN = re.compile(r'([A-Za-z_~][A-Za-z0-9_:~<>]*)\s*\(')
MAP_LINE = re.compile(r'^\s*([0-9a-fA-F]{4}:[0-9a-fA-F]{8})\s+(\S+)\s+([0-9a-fA-F]{8})\s+(f\s+)?(i\s+)?(.*)$')
GLOBAL_NAME = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)\s*(\[[^\]]*\]\s*)*(=|;|\{|$)')


def _source_files():
    for base in ('src', 'include'):
        for dirpath, _, files in os.walk(os.path.join(SRC, base)):
            for fn in files:
                if fn.endswith(('.cpp', '.c', '.h', '.hpp', '.inc')):
                    yield os.path.join(dirpath, fn)


def scan_annotations():
    """-> functions: list of dicts(addr, name, file, line, sig); globals: same."""
    funcs, globs = [], []
    for path in _source_files():
        try:
            lines = open(path, encoding='utf-8', errors='replace').read().split('\n')
        except OSError:
            continue
        rel = os.path.relpath(path, SRC)
        for i, line in enumerate(lines):
            m = ANN.match(line)
            if not m:
                continue
            kind, addr = m.group(1), int(m.group(2), 16)
            # first meaningful line after the annotation (skipping comments)
            text = ''
            in_block = False
            for j in range(i + 1, min(i + 30, len(lines))):
                s = lines[j].strip()
                if in_block:
                    if '*/' in s:
                        in_block = False
                        s = s.split('*/', 1)[1].strip()
                        if not s:
                            continue
                    else:
                        continue
                if s.startswith('/*'):
                    if '*/' not in s[2:]:
                        in_block = True
                        continue
                    s = s[s.index('*/', 2) + 2:].strip()
                if not s or s.startswith('//') or s.startswith('*'):
                    continue
                text = s
                # the signature may span several lines
                k = j
                while kind == 'FUNCTION' and '(' in text and ')' not in text and k + 1 < len(lines):
                    k += 1
                    text += ' ' + lines[k].strip()
                break
            entry = {'addr': addr, 'file': rel, 'line': i + 1, 'text': text}
            if kind == 'FUNCTION':
                mm = IDENT_BEFORE_PAREN.search(text)
                entry['name'] = mm.group(1) if mm else ''
                funcs.append(entry)
            else:
                decl = re.sub(r'/\*.*?\*/', '', text.split('//')[0])
                decl = decl.split('=')[0].strip().rstrip(';').strip()
                decl = re.sub(r'\[[^\]]*\]', '', decl).strip()
                mm = re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s*$', decl)
                entry['name'] = mm.group(1) if mm else ''
                globs.append(entry)
    return funcs, globs


def _name_from_decorated(dec):
    if dec.startswith('?'):
        special = {'??0': '{c}', '??1': '~{c}', '??4': 'operator='}
        for pre, fmt in special.items():
            if dec.startswith(pre):
                parts = dec[3:].split('@@')[0].split('@')
                if any(not p or p[0].isdigit() or p.startswith('?') for p in parts):
                    return None
                cls = parts[0]
                return '::'.join(list(reversed(parts)) + [fmt.format(c=cls)])
        if dec.startswith('??') or dec.startswith('?$'):
            return None  # other operators/templates - by explicit name
        head = dec[1:].split('@@')[0]
        parts = head.split('@')
        if any(not p or p[0].isdigit() or p.startswith('?') for p in parts):
            return None
        return '::'.join(reversed(parts))
    if dec.startswith('_'):
        return dec[1:].split('@')[0]
    return dec.split('@')[0]


def scan_map(path=MAP):
    """-> list of dict(dec, name, va, obj, static)"""
    out = []
    section = None
    for line in open(path, encoding='ascii', errors='replace'):
        if 'Publics by Value' in line:
            section = 'pub'
            continue
        if 'Static symbols' in line:
            section = 'static'
            continue
        if section is None:
            continue
        m = MAP_LINE.match(line)
        if not m:
            continue
        dec = m.group(2)
        va = int(m.group(3), 16)
        obj = m.group(6).strip()
        out.append({'dec': dec, 'name': _name_from_decorated(dec), 'va': va, 'obj': obj,
                    'static': section == 'static', 'func': bool(m.group(4))})
    return out


def demangle(names):
    if not names:
        return {}
    p = subprocess.run([CXXFILT], input='\n'.join(names), capture_output=True, text=True)
    return dict(zip(names, p.stdout.split('\n')))


class Symbols:
    def __init__(self, use_cache=True):
        map_mtime = os.path.getmtime(MAP)
        if use_cache and os.path.exists(CACHE):
            data = json.load(open(CACHE, encoding='utf-8'))
            if data.get('map_mtime') == map_mtime:
                self._load(data)
                return
        funcs, globs = scan_annotations()
        mp = scan_map()
        data = {'map_mtime': map_mtime, 'funcs': funcs, 'globs': globs, 'map': mp}
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        tmp = CACHE + '.%d.tmp' % os.getpid()
        json.dump(data, open(tmp, 'w', encoding='utf-8'))
        os.replace(tmp, CACHE)
        self._load(data)

    def _load(self, data):
        self.funcs = data['funcs']
        self.globs = data['globs']
        self.map = data['map']
        self.by_addr = {}
        for f in self.funcs:
            self.by_addr.setdefault(f['addr'], []).append(f)
        self.glob_by_name = {}
        for g in self.globs:
            self.glob_by_name.setdefault(g['name'], []).append(g)
        self.map_by_name = {}
        for m in self.map:
            if m['name']:
                self.map_by_name.setdefault(m['name'], []).append(m)
        self.map_by_dec = {m['dec']: m for m in self.map}

    # --- functions ---
    def function(self, retail_addr, port_symbol=None):
        """-> dict(name, retail, port, file) or an exception with an explanation."""
        anns = self.by_addr.get(retail_addr, [])
        if port_symbol:
            m = self.map_by_dec.get(port_symbol) or next(
                (x for x in self.map if x['name'] == port_symbol), None)
            if not m:
                raise KeyError('port symbol %s not in map' % port_symbol)
            return {'name': port_symbol, 'retail': retail_addr, 'port': m['va'],
                    'file': anns[0]['file'] if anns else '?'}
        if not anns:
            raise KeyError('no // FUNCTION annotation for 0x%08x' % retail_addr)
        ann = anns[0]
        name = ann['name']
        short = name.split('::')[-1]
        cands = self.map_by_name.get(name, [])
        if not cands and '::' not in name:
            # method declared inside the class: look up by short name
            cands = [m for m in self.map if m['name'] and m['name'].split('::')[-1] == short]
        cands = [c for c in cands if c['func']]
        src_obj = os.path.basename(ann['file']).rsplit('.', 1)[0].lower()
        same = [c for c in cands if c['obj'].lower().rsplit('.', 2)[0].split(':')[-1] == src_obj]
        if len(same) >= 1:
            cands = same
        if len(cands) == 1:
            return {'name': name, 'retail': retail_addr, 'port': cands[0]['va'],
                    'file': ann['file'], 'dec': cands[0]['dec']}
        if not cands:
            raise KeyError('0x%08x %s (%s): not found in port map (inlined or renamed?)'
                           % (retail_addr, name, ann['file']))
        raise KeyError('0x%08x %s: ambiguous in port map: %s'
                       % (retail_addr, name, ', '.join(c['dec'] for c in cands)))

    # --- globals ---
    def global_(self, name, retail_addr=None):
        anns = self.glob_by_name.get(name, [])
        if retail_addr is None:
            if not anns:
                raise KeyError('no // GLOBAL annotation for %s' % name)
            addrs = sorted({a['addr'] for a in anns})
            if len(addrs) > 1:
                raise KeyError('global %s annotated at several addresses: %s'
                               % (name, ', '.join('0x%x' % a for a in addrs)))
            retail_addr = addrs[0]
        cands = [m for m in self.map_by_name.get(name, []) if not m['func']]
        if len(cands) != 1:
            cands2 = [m for m in self.map if m['dec'].startswith('?%s@' % name) and not m['func']]
            if len(cands2) == 1:
                cands = cands2
        if len(cands) != 1:
            raise KeyError('global %s: %d candidates in port map' % (name, len(cands)))
        return {'name': name, 'retail': retail_addr, 'port': cands[0]['va']}
