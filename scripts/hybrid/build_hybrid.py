"""Build wiz8hy.dll: port functions transplanted into the original Wiz8.exe.

python -I build_hybrid.py [--config scripts\\hybrid\\transplant_wide.json]
(run from PowerShell after . Tools\\msvcenv.ps1 - needs cl/link on PATH;
wrapper: scripts\\hybrid\\build_hybrid.ps1)

1. Port files listed in units are compiled with the same flags as the port.
2. In the object files, everything that exists in the original (FUNCTION/GLOBAL/VTABLE annotations), except
   the transplanted functions, becomes external references: functions become stubs
   "push address; ret" into the original, data become absolute symbols at the original address
   (no relocations: verified that link does not create base relocations for them).
3. Link the DLL and map; wiz8hy_hooks.txt: original address -> RVA in the DLL for the jmp patch.
"""
import argparse
import collections
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'w8diff'))
from coff import Coff, write_bind_obj, IMAGE_SCN_LNK_COMDAT, CLASS_STATIC  # noqa: E402
from w8diff.symbols import Symbols, ROOT, SRC  # noqa: E402

OUT = os.path.join(ROOT, 'build', 'hybrid')
VC = os.path.join(ROOT, 'build', 'vc2022')
INC = os.path.join(SRC, 'include')
# the patch version (VERSION, one line) - shown in the main menu next to the game's v1.2.4
with open(os.path.join(ROOT, 'VERSION'), encoding='ascii') as _f:
    VERSION = _f.readline().strip()
CXXFLAGS = ['/nologo', '/c', '/DWIN32', '/D_WINDOWS', '/Ob2', '/O2', '/MT', '/GS-', '/arch:IA32',
            '/Zc:wchar_t-', '/Zc:threadSafeInit-', '/permissive', '/source-charset:utf-8',
            '/bigobj', '/wd4430', '/wd4996', '/wd4068', '/wd4530', '/GR-', '/Gy',
            '/DNDEBUG', '/DNOMINMAX', '/DWIN32_LEAN_AND_MEAN', '/D_CRT_NONSTDC_NO_DEPRECATE',
            '/D_CRT_NON_CONFORMING_SWPRINTFS', '/D_CRT_NON_CONFORMING_WCSTOK',
            '/D_CRT_SECURE_NO_DEPRECATE', '/D_CRT_SECURE_NO_WARNINGS', '/D_USE_32BIT_TIME_T',
            '/DWIZ8_HYBRID=1', '/DWIZ8WIDE_VERSION="%s"' % VERSION,
            '/FI' + os.path.join(INC, 'wiz8', 'compat', 'compiler.h'),
            '/FI' + os.path.join(INC, 'wiz8', 'compat', 'msvc2022.h'),
            '/I' + os.path.join(INC, 'wiz8', 'compat', 'modern_msvc'), '/I' + INC,
            '/I' + os.path.join(INC, 'wiz8'), '/I' + os.path.join(INC, 'wiz8', 'engine_code'),
            '/I' + os.path.join(SRC, 'src', 'sgp')]
COMPAT = ['src/msvc2022_compat/msvcrt_heap_bridge.cpp', 'src/msvc2022_compat/msvcrt_crt_bridge.c',
          'src/msvc2022_compat/sr_template_base_imports.cpp']
LIBS = [os.path.join(VC, x) for x in ('wiz8_sr.lib', 'sr-assert-import.lib', 'wiz8_mss32.lib',
                                       'wiz8_binkw32.lib', 'wiz8_msvcrt.lib', 'msvcrt-bridge-import.lib',
                                       'WIZ8_ZLIB_1_0_4.lib')] + [
    'kernel32.lib', 'user32.lib', 'gdi32.lib', 'winmm.lib', 'advapi32.lib', 'dxguid.lib', 'ddraw.lib']

VTABLE_ANN = re.compile(r'^\s*//\s*VTABLE:\s*WIZ8\s+(0x[0-9a-fA-F]+)\s*(\S+)?')


def run(cmd, cwd=None):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, errors='replace')
    return p.returncode, p.stdout + p.stderr


def objname(path):
    return os.path.basename(path).rsplit('.', 1)[0].lower()


def build_tables(syms, owned=()):
    """(obj, dec) and dec -> (retail_va, 'f'|'d') for everything annotated that is in the port map."""
    by_obj, by_dec = {}, {}
    for f in syms.funcs:
        try:
            r = syms.function(f['addr'])
        except KeyError:
            continue
        dec = r.get('dec')
        if not dec:
            continue
        m = syms.map_by_dec.get(dec)
        obj = m['obj'] if m else ''
        key_obj = obj.lower().rsplit('.', 2)[0].split(':')[-1]
        by_obj[(key_obj, dec)] = (f['addr'], 'f')
        if m and not m['static']:
            by_dec[dec] = (f['addr'], 'f')
    for g in syms.globs:
        if g['name'] in owned:
            continue  # own storage in the DLL (the port's array is larger than the original's)
        src_obj = os.path.basename(g['file']).rsplit('.', 1)[0].lower()
        for m in syms.map_by_name.get(g['name'], []):
            if m['func']:
                continue
            key_obj = m['obj'].lower().rsplit('.', 2)[0].split(':')[-1]
            if key_obj != src_obj and len(syms.map_by_name.get(g['name'], [])) > 1:
                continue
            by_obj[(key_obj, m['dec'])] = (g['addr'], 'd')
            if not m['static']:
                by_dec[m['dec']] = (g['addr'], 'd')
    return by_obj, by_dec


UNDNAME = os.path.join(ROOT, 'Tools', 'msvc', 'VC', 'Tools', 'MSVC', '14.44.35207', 'bin', 'Hostx64', 'x86', 'undname.exe')


def _param_count(sig):
    i, j = sig.find('('), sig.rfind(')')
    if i < 0 or j < i:
        return -1
    inner = sig[i + 1:j].strip()
    if inner in ('', 'void'):
        return 0
    depth, n = 0, 1
    for ch in inner:
        if ch in '<(':
            depth += 1
        elif ch in '>)':
            depth -= 1
        elif ch == ',' and depth == 0:
            n += 1
    return n


def _norm_class(s):
    s = re.sub(r'\b(class|struct|enum|union)\s+', '', s)
    return s.replace(' ', '')


def scan_vtables():
    """'// VTABLE: WIZ8 0xADDR [Base]' before a class declaration (or '// class X'):
    (class, base or None) -> address. The base is for tables under multiple inheritance."""
    out = {}
    for base in ('src', 'include'):
        for dp, _, files in os.walk(os.path.join(SRC, base)):
            for fn in files:
                if not fn.endswith(('.cpp', '.h', '.hpp', '.c', '.inc')):
                    continue
                lines = open(os.path.join(dp, fn), encoding='utf-8', errors='replace').read().split('\n')
                for i, line in enumerate(lines):
                    m = VTABLE_ANN.match(line)
                    if not m:
                        continue
                    cls = None
                    for j in range(i + 1, min(i + 8, len(lines))):
                        s = lines[j].strip()
                        mm = re.match(r'^//\s*(?:class|struct)\s+(.+?)\s*$', s) or \
                            re.match(r'^(?:class|struct)\s+([A-Za-z_][A-Za-z0-9_:<>, ]*?)\s*(?::|\{|$)', s)
                        if mm:
                            cls = _norm_class(mm.group(1))
                            break
                    if cls:
                        b = m.group(2)
                        out[(cls, _norm_class(b) if b else None)] = int(m.group(1), 16)
    return out


class Names:
    """Binding by meaning: decorated name -> llvm-cxxfilt -> full function/
    variable name -> port annotation (original address). Also works for symbols that are
    missing from the Wiz8Runtime.exe map (the port dropped/inlined them)."""

    def __init__(self, syms, owned):
        self.cache = {}
        self.vtables = scan_vtables()
        self.ann = collections.defaultdict(list)
        for f in syms.funcs:
            self.ann[f['name']].append((f['addr'], 'f', f['file'], f['text']))
        for g in syms.globs:
            if g['name'] not in owned:
                self.ann[g['name']].append((g['addr'], 'd', g['file'], g['text']))

    def demangle(self, names):
        """undname.exe from MSVC (llvm-cxxfilt from llvm-mingw does not know the MSVC scheme)."""
        todo = [n for n in names if n not in self.cache]
        for n in todo:
            if not n.startswith('?'):
                self.cache[n] = n
        todo = [n for n in todo if n.startswith('?')]
        k = 0
        while k < len(todo):
            chunk, size = [], 0
            while k < len(todo) and size + len(todo[k]) + 3 < 24000:
                chunk.append(todo[k])
                size += len(todo[k]) + 3
                k += 1
            out = subprocess.run([UNDNAME] + chunk, capture_output=True, text=True,
                                 errors='replace').stdout
            pairs = re.findall(r'Undecoration of :- "(.*)"\s*\nis :- "(.*)"', out)
            got = dict(pairs)
            for n in chunk:
                self.cache[n] = got.get(n, n)

    def qname(self, dec):
        d = self.cache.get(dec)
        if d is None:
            self.demangle([dec])
            d = self.cache[dec]
        if d == dec:  # C name
            return dec[1:] if dec.startswith('_') else dec, d
        if d.endswith(')'):
            depth, k = 0, len(d) - 1
            while k >= 0:
                if d[k] == ')':
                    depth += 1
                elif d[k] == '(':
                    depth -= 1
                    if depth == 0:
                        break
                k -= 1
            head = d[:k].strip()
        else:
            head = d
        head = re.sub(r'\[[^\]]*\]', '', head).strip()
        name = head.split(' ')[-1].lstrip('*&')
        return name, d

    def resolve(self, dec, src_path=None):
        if dec.startswith('??_7'):
            d = self.cache.get(dec)
            if d is None:
                self.demangle([dec])
                d = self.cache[dec]
            m = re.match(r"^const (.+)::`vftable'(?:\{for `(.+)'\})?$", d)
            if not m:
                return None
            key = (_norm_class(m.group(1)), _norm_class(m.group(2)) if m.group(2) else None)
            addr = self.vtables.get(key)
            return (addr, 'd') if addr else None
        if dec.startswith('??_') or dec.startswith('__'):
            return None
        q, d = self.qname(dec)
        cands = self.ann.get(q, [])
        if not cands:
            return None
        if src_path:
            base = os.path.basename(src_path).lower()
            same = [c for c in cands if os.path.basename(c[2]).lower() == base]
            if len(same) == 1:
                return same[0][0], same[0][1]
            if same:
                cands = same
        if len(cands) == 1:
            return cands[0][0], cands[0][1]
        n = _param_count(d)
        cc = [c for c in cands if c[1] == 'f' and _param_count(c[3]) == n]
        if len(cc) == 1:
            return cc[0][0], cc[0][1]
        return None

_SRC_TEXT = {}


def find_definition(qname):
    """Port file where function/variable qname is defined (for symbols that are
    neither in the original nor in the port map)."""
    short = qname.split('::')[-1]
    cls = qname.split('::')[-2] if '::' in qname else None
    if not _SRC_TEXT:
        for dp, _, files in os.walk(os.path.join(SRC, 'src')):
            for fn in files:
                if fn.endswith(('.cpp', '.c')):
                    p = os.path.join(dp, fn)
                    _SRC_TEXT[p] = open(p, encoding='utf-8', errors='replace').read()
    pat = re.compile(r'^[A-Za-z_][^;\n]*\b%s%s\s*\([^;]*$' % (
        (re.escape(cls) + r'::') if cls else '', re.escape(short)), re.M)
    hits = [p for p, text in _SRC_TEXT.items() if pat.search(text)]
    return hits[0] if len(hits) == 1 else None


def source_index():
    idx = collections.defaultdict(list)
    for dp, _, files in os.walk(os.path.join(SRC, 'src')):
        for fn in files:
            if fn.endswith(('.cpp', '.c')):
                idx[fn.lower()].append(os.path.join(dp, fn))
    return idx


SGP_FLAGS = ['/nologo', '/c', '/DWIN32', '/D_WINDOWS', '/O2', '/Ob2', '/MT', '/GS-', '/arch:IA32',
             '/Zc:wchar_t-', '/Zc:threadSafeInit-', '/permissive', '/source-charset:utf-8', '/bigobj',
             '/wd4430', '/wd4996', '/wd4068', '/wd4530', '/Gy', '/DCINTERFACE', '/DCOBJMACROS',
             '/D_CRT_NONSTDC_NO_DEPRECATE', '/D_CRT_NON_CONFORMING_SWPRINTFS',
             '/D_CRT_NON_CONFORMING_WCSTOK', '/D_CRT_SECURE_NO_DEPRECATE', '/D_CRT_SECURE_NO_WARNINGS',
             '/D_USE_32BIT_TIME_T', '/DWIZ8_HYBRID=1',
             '/FI' + os.path.join(INC, 'wiz8', 'compat', 'compiler.h'),
             '/FI' + os.path.join(INC, 'wiz8', 'compat', 'msvc2022.h'),
             '/I' + os.path.join(INC, 'wiz8', 'compat', 'modern_msvc'), '/I' + os.path.join(SRC, 'src', 'sgp'),
             '/I' + INC, '/I' + os.path.join(INC, 'wiz8'), '/I' + os.path.join(INC, 'wiz8', 'engine_code')]


def compile_one(path, obj, glue):
    # the port's SGP library is built with its own flags (COBJMACROS etc.)
    sgp = os.path.normcase(os.path.join(SRC, 'src', 'sgp')) in os.path.normcase(path)
    flags = list(SGP_FLAGS if sgp else CXXFLAGS)
    if glue:
        flags += ['/I' + os.path.join(ROOT, 'src', 'hybrid'), '/I' + os.path.join(SRC, 'src', 'w8diff')]
    code, out = run(['cl'] + flags + ['/Fo' + obj, path])
    if code != 0:
        print(out)
        raise SystemExit('compile failed: %s' % path)


def surgery(path, obj, by_obj, by_dec, names, transplant, want, bind, kept, stats):
    """Everything annotated (except transplanted code) -> external references to the original."""
    c = Coff(obj)
    key_obj = objname(path)
    first_in_sec = {}
    for s in c.symbols:
        if s.section > 0 and not (s.sclass == CLASS_STATIC and s.naux > 0):
            first_in_sec.setdefault(s.section, s)
    names.demangle([s.name for s in c.symbols if s.section > 0])
    for s in c.symbols:
        if s.section <= 0 or (s.sclass == CLASS_STATIC and s.naux > 0):
            continue
        hit = by_obj.get((key_obj, s.name)) or (by_dec.get(s.name) if s.sclass != CLASS_STATIC else None)
        if not hit and s.name.startswith('??_7'):
            hit = names.resolve(s.name)  # the original's virtual function table
        if not hit:
            # not in the port map: by name meaning, but only an annotation from this same
            # file or from a header (otherwise same-named helpers could be confused)
            r = names.resolve(s.name, path) if not s.name.startswith('??_') else None
            if r:
                ann_file = next((x[2] for x in names.ann[names.qname(s.name)[0]] if x[0] == r[0]), '')
                if os.path.basename(ann_file).lower() == os.path.basename(path).lower() or \
                        ann_file.startswith('include'):
                    hit = r
                    stats['bound-by-name'] += 1
        if not hit:
            continue
        addr, kind = hit
        if kind == 'f' and addr in transplant:
            if s.sclass == CLASS_STATIC:
                # static: unique external name so that /INCLUDE keeps the function
                c.rename(s, '__w8t_%08x' % addr, sclass=2)
            want[s.name] = addr
            kept[s.name] = addr
            continue
        sec = c.sections[s.section - 1]
        is_func = (s.type & 0x20) != 0
        bindname = '__w8r_%08x' % addr if s.sclass == CLASS_STATIC else s.name
        if (sec.chars & IMAGE_SCN_LNK_COMDAT) and first_in_sec.get(sec.number) is s:
            # COMDAT must have its own symbol: the definition stays under a dead
            # local name (/OPT:REF will discard it), references go to the new external one
            new_idx = c.append_extern(bindname, s.type)
            c.redirect(s.index, new_idx)
            c.rename(s, '__w8dead_%x' % s.index, sclass=CLASS_STATIC)
            stats['dead-comdat'] += 1
        else:
            if s.sclass == CLASS_STATIC:
                c.rename(s, bindname)
            c.undefine(s)
        bind[bindname] = (addr, 'f' if is_func else 'd')
        stats['bound-' + ('func' if is_func else 'data')] += 1
    # the port's dynamic initialization of globals (.CRT$XC*) would overwrite
    # the original's globals - remove it
    for sec in c.sections:
        if sec.name.startswith('.CRT$XC') or sec.name.startswith('.CRT$XI'):
            c.remove_section(sec)
            stats['removed-crt-init'] += 1
    c.save()


UNRESOLVED = re.compile(r'unresolved external symbol (?:"[^"]*" \((\S+?)\)|(\S+))')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default=os.path.join(HERE, 'transplant_wide.json'))
    ap.add_argument('--no-compile', action='store_true')
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding='utf-8'))
    transplant = {int(k, 16): v for k, v in cfg['transplant'].items()}
    os.makedirs(os.path.join(OUT, 'obj'), exist_ok=True)

    syms = Symbols(use_cache=False)
    owned = set(cfg.get('dll_owned_globals', []))
    by_obj, by_dec = build_tables(syms, owned)
    want = {}  # dec -> retail addr (transplanted ones; filled in by the surgery)
    names = Names(syms, owned)
    srcs = source_index()

    units = [os.path.join(SRC, u.replace('/', os.sep)) for u in cfg['units']]
    if cfg.get('auto_units'):
        # files of the transplanted functions
        for addr in transplant:
            ann = syms.by_addr.get(addr)
            if ann:
                p = os.path.join(SRC, ann[0]['file'])
                if p not in units:
                    units.append(p)
    compat = [os.path.join(SRC, u.replace('/', os.sep)) for u in COMPAT]
    glue = [os.path.join(ROOT, u.replace('/', os.sep)) for u in cfg.get('glue', [])]
    objs = {}
    bind, kept, stats = {}, {}, collections.Counter()
    traps = set()
    auto_units = []

    os.makedirs(os.path.join(OUT, 'obj', 'raw'), exist_ok=True)

    def add(path, is_unit, is_glue=False):
        base = os.path.basename(path).rsplit('.', 1)[0] + '.obj'
        raw = os.path.join(OUT, 'obj', 'raw', base)   # as compiled
        obj = os.path.join(OUT, 'obj', base)          # after surgery
        objs[path] = obj
        if not (a.no_compile and os.path.exists(raw)):
            compile_one(path, raw, is_glue)
        shutil.copyfile(raw, obj)
        if is_unit:
            surgery(path, obj, by_obj, by_dec, names, transplant, want, bind, kept, stats)

    for p in units:
        add(p, True)
    for p in compat:
        add(p, False)
    for p in glue:
        add(p, False, True)

    dll = os.path.join(OUT, 'wiz8hy.dll')
    mapf = os.path.join(OUT, 'wiz8hy.map')
    bind_obj = os.path.join(OUT, 'obj', 'w8bind.obj')
    for attempt in range(12):
        defined, undefined = set(), set()
        for path, obj in objs.items():
            for s in Coff(obj).symbols:
                if s.sclass == CLASS_STATIC:
                    continue
                if s.section > 0 or (s.section == 0 and s.value > 0):
                    defined.add(s.name)
                elif s.section == 0:
                    undefined.add(s.name)
        names.demangle(sorted(undefined - defined))
        for name in undefined - defined:
            if name in bind:
                continue
            hit = by_dec.get(name) or names.resolve(name)
            if hit and not (hit[1] == 'f' and hit[0] in transplant):
                bind[name] = hit
                stats['bound-external'] += 1
        stubs = sorted((n, v[0]) for n, v in bind.items() if v[1] == 'f' and n not in defined)
        absol = sorted((n, v[0]) for n, v in bind.items() if v[1] == 'd' and n not in defined)
        write_bind_obj(bind_obj, stubs, absol, sorted(traps - defined))
        cmd = ['link', '/nologo', '/DLL', '/OUT:' + dll, '/MAP:' + mapf, '/OPT:REF', '/OPT:NOICF',
               '/BASE:0x10000000', '/NODEFAULTLIB:msvcrt.lib', '/IGNORE:4049,4217,4078'] + \
            ['/INCLUDE:' + d for d in want] + list(objs.values()) + [bind_obj] + LIBS
        code, out = run(cmd)
        if code == 0:
            break
        unresolved = set()
        for m in UNRESOLVED.finditer(out):
            unresolved.add(m.group(1) or m.group(2))
        if not unresolved:
            print(out[-4000:])
            raise SystemExit('link failed')
        progress = False
        errors = []
        for name in sorted(unresolved):
            hit = names.resolve(name)
            if hit and name not in bind and not (hit[1] == 'f' and hit[0] in transplant):
                bind[name] = hit
                progress = True
                continue
            m = syms.map_by_dec.get(name)
            if m and m['func'] is not None:
                fn = m['obj'].split(':')[-1]
                fn = fn[:-4] if fn.lower().endswith('.obj') else fn
                cands = srcs.get(fn.lower(), []) or srcs.get(fn.lower().replace('_', ' '), [])
                if len(cands) != 1:
                    src = find_definition(names.qname(name)[0])
                    cands = [src] if src else cands
                if len(cands) == 1 and cands[0] not in objs:
                    auto_units.append(cands[0])
                    add(cands[0], True)
                    progress = True
                    continue
                if len(cands) == 1 and cands[0] in objs:
                    errors.append('%s defined in %s but still unresolved' % (name, fn))
                    continue
            if not m:
                src = find_definition(names.qname(name)[0])
                if src and src not in objs:
                    auto_units.append(src)
                    add(src, True)
                    progress = True
                    continue
            is_data = re.match(r'^\?[^@]+(@[^@]+)*@@[23]', name) is not None
            if is_data or (name.startswith('_') and not (m and m['func'])):
                errors.append('data symbol without retail address or port definition: ' + name)
            elif name not in traps:
                traps.add(name)
                progress = True
        if errors:
            print('\n'.join(errors))
        if not progress:
            print(out[-3000:])
            raise SystemExit('link failed: no progress')
        print('link attempt %d: %d unresolved, units now %d, traps %d' % (
            attempt + 1, len(unresolved), len(units) + len(auto_units), len(traps)))
    else:
        raise SystemExit('link failed after retries')
    if auto_units:
        print('auto-added units: ' + ', '.join(os.path.relpath(u, SRC) for u in auto_units))
    missing = sorted(set(transplant) - set(kept.values()))
    if missing:
        raise SystemExit('transplant functions not found in compiled units: %s' % ', '.join('0x%08x' % m for m in missing))
    print(dict(stats))

    # traps that still have live references ended up in the map - that is an error
    rva = {}
    live_traps = []
    for line in open(mapf, encoding='ascii', errors='replace'):
        parts = line.split()
        if len(parts) >= 3 and ':' in parts[0]:
            if parts[1] in want:
                try:
                    rva[parts[1]] = int(parts[2], 16) - 0x10000000
                except ValueError:
                    pass
            if parts[1] in traps:
                live_traps.append(parts[1])
    if live_traps:
        raise SystemExit('live references to symbols without definition: %s' % live_traps)
    with open(os.path.join(OUT, 'wiz8hy_hooks.txt'), 'w', encoding='ascii') as f:
        for dec, addr in sorted(want.items(), key=lambda x: x[1]):
            if dec not in rva:
                raise SystemExit('no RVA for %s' % dec)
            f.write('%08x %08x %s\n' % (addr, rva[dec], dec))
    print('linked %s (%d bytes), %d hooks, %d stubs, %d data, %d dead-only traps' % (
        dll, os.path.getsize(dll), len(want), len(stubs), len(absol), len(traps)))


if __name__ == '__main__':
    main()
