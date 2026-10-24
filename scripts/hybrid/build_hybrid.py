"""Build wiz8hy.dll: port functions transplanted into the original Wiz8.exe.

python -I build_hybrid.py [--config scripts\\hybrid\\transplant_wide.json] [--no-compile]
python -I build_hybrid.py --selftest   (the parsers and the guard's own logic only)
(run from PowerShell after . Tools\\msvcenv.ps1 - needs cl/link on PATH;
wrapper: scripts\\hybrid\\build_hybrid.ps1)

1. Port files listed in units are compiled with the same flags as the port.
2. In the object files, everything that exists in the original (FUNCTION/GLOBAL/VTABLE annotations), except
   the transplanted functions, becomes external references: functions become stubs
   "push address; ret" into the original, data become absolute symbols at the original address
   (no relocations: verified that link does not create base relocations for them).
3. Link the DLL and map into build\\hybrid\\staging; wiz8hy_hooks.txt: original address -> RVA in
   the DLL for the jmp patch.
4. Binding guard (check_object_names, check_bindings, check_owned_users): the build fails when a
   // GLOBAL-annotated variable got its own storage in the DLL instead of the retail address (a
   private copy the original code never sees: g_fade_callback hung the party-death screen in
   1.0.0-1.0.1), unless dll_owned_globals names it with a reason; and when a retail function that
   uses a DLL-owned array is still reachable. Every build writes build\\hybrid\\GUARD_FAILED when
   it starts; a pass moves the staged map, hooks and dll into build\\hybrid and removes it, any
   failure (guard, compile, link, trap) leaves it with the reason and the last good
   wiz8hy.dll + wiz8hy_hooks.txt in place.
"""
import argparse
import bisect
import collections
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'w8diff'))
from coff import Coff, write_bind_obj, IMAGE_SCN_LNK_COMDAT, CLASS_STATIC  # noqa: E402
from w8diff.symbols import (Symbols, ROOT, SRC, MAP_LINE, data_symbol, name_from_undecorated,  # noqa: E402
                            same_function, is_const_object, declarator_name, scan_lines, selftest)

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


def _stem(path):
    return os.path.basename(path).rsplit('.', 1)[0].lower()


class Names:
    """Binding by meaning: decorated name -> full function/variable name (variables: parsed from
    the decorated name itself, functions: undname) -> port annotation (original address). Also
    works for symbols that are missing from the Wiz8Runtime.exe map (the port dropped/inlined them)."""

    def __init__(self, syms, owned, vtables=None):
        self.cache = {}
        self.vtables = scan_vtables() if vtables is None else vtables
        self.ann = collections.defaultdict(list)    # name -> (addr, kind, file, text, func)
        self.globs = collections.defaultdict(list)  # name -> GLOBAL annotations, owned ones too
        self.by_last = collections.defaultdict(list)   # last name component -> GLOBAL annotations
        for f in syms.funcs:
            self.ann[f['name']].append((f['addr'], 'f', f['file'], f['text'], ''))
        for g in syms.globs:
            self.globs[g['name']].append(g)
            if g['name']:
                self.by_last[g['name'].split('::')[-1]].append(g)
            if g['name'] not in owned:
                self.ann[g['name']].append((g['addr'], 'd', g['file'], g['text'], g.get('func', '')))

    def data_candidates(self, ds, src_stem=None, owned_too=False, loose=False):
        """GLOBAL annotations that variable ds (symbols.data_symbol) can be: same (qualified)
        name; for a function-local static the same enclosing function; with src_stem, an
        annotation in that source file wins, and a variable without linkage (static, local
        static, anonymous namespace) matches only its own file (GLOBAL annotations are only in
        .c/.cpp files: check_annotations). loose (for the guard): the enclosing function is
        ignored (either side may have misread it), so a local static with the name of an
        annotated variable of its file fails loudly instead of being skipped."""
        if owned_too:
            cands = [(g['addr'], 'd', g['file'], g.get('text', ''), g.get('func', ''))
                     for g in self.globs.get(ds['name'], [])]
        else:
            cands = [c for c in self.ann.get(ds['name'], []) if c[1] == 'd']
        if not loose and ds['func']:
            cands = [c for c in cands if same_function(c[4], ds['func'])]
        elif not loose:
            cands = [c for c in cands if not c[4]]
        if src_stem is not None:
            same = [c for c in cands if _stem(c[2]) == src_stem]
            if same or ds['internal']:
                cands = same
        return cands

    def scope_mismatches(self, ds, src_stem):
        """GLOBAL annotations whose name ends like variable ds's but whose scope differs
        ('g_in_ns' read from 'namespace ns { int g_in_ns; }' vs the DLL's ns::g_in_ns, or the
        other way round): the same variable, which nothing could bind. Same source file first; a
        variable without linkage only there."""
        last = ds['name'].split('::')[-1]
        cands = [g for g in self.by_last.get(last, []) if g['name'] != ds['name']]
        same = [g for g in cands if _stem(g['file']) == src_stem]
        return same if same or ds['internal'] else cands

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
        ds = data_symbol(dec)
        if ds:
            # variable: the name comes from the decorated name ("?name@scope@@3..."), not from
            # undname's text, which is "void (__cdecl* name)(void)" for a function pointer and
            # "`func'::`2'::name" (or nothing at all) for a function-local static
            return ds['name'], dec
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
        if re.search(r"[()'`]", name) and 'operator' not in name:
            # a declarator in parentheses: "void (__cdecl* g_cb)(void)" gave "g_cb)"
            name = name_from_undecorated(d) or name
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
        ds = data_symbol(dec)
        if ds:
            cands = self.data_candidates(ds, _stem(src_path) if src_path else None)
            return (cands[0][0], 'd') if len(cands) == 1 else None
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


# --- binding guard ---------------------------------------------------------------------------------
# A game variable must exist once: at its retail address. A copy in the DLL that both the DLL and
# the original code use (each its own copy) is a silent bug: g_fade_callback (1.0.0-1.0.1) was
# written by the replaced BeginScreenFade into the DLL copy and read by the retail UpdateScreenFade
# from the retail address, so the party-death screen hung.
RETAIL_EXE_SHA256 = '18A74FF61C65B8A2D4CFA11FFCE82AD7FEF022A94EAF0C2F217E479E981420D2'
RETAIL_EXES = [os.path.join(ROOT, 'ghidra', 'bin', 'Wiz8.exe'),
               os.path.join(ROOT, 'games', 'reference', 'Wiz8.exe')]   # read only


def check_annotations(syms, cfg):
    """Before compiling: every GLOBAL annotation is in a .c/.cpp file (the catch-all,
    check_object_names, sees only compiled files) and names its variable, and dll_owned_globals
    maps each name to the reason it lives in the DLL. -> (owned names, error lines)."""
    errors = []
    for g in syms.globs:
        if not g['file'].lower().endswith(('.c', '.cpp')):
            errors.append('%s:%d: // GLOBAL: WIZ8 0x%08x - GLOBAL annotations belong in .c/.cpp files, '
                          'above the definition of the variable, not in a header or .inc file' % (
                              g['file'], g['line'], g['addr']))
            continue
        if g['name']:
            continue
        if g.get('in_class') is not None:
            errors.append('%s:%d: // GLOBAL: WIZ8 0x%08x - a declaration inside class %s is not the '
                          'variable\'s definition: annotate the definition outside the class '
                          '(\'int %s::%s;\') instead' % (
                              g['file'], g['line'], g['addr'], g['in_class'], g['in_class'],
                              declarator_name(g.get('decl', '')) or 'name'))
        elif g.get('comment_only'):
            errors.append('%s:%d: // GLOBAL: WIZ8 0x%08x - the comment-only form (%r) is only for a GUID '
                          'from a system header (IID_, CLSID_, GUID_); declare the variable below the '
                          'annotation' % (g['file'], g['line'], g['addr'], g.get('text', '')))
        else:
            errors.append('%s:%d: // GLOBAL: WIZ8 0x%08x - no certain variable name in the declaration '
                          'below it (%r: none, several declarators or a macro after the name); it could '
                          'not be bound' % (g['file'], g['line'], g['addr'], g.get('decl') or g.get('text', '')))
    owned = cfg.get('dll_owned_globals', {})
    if not isinstance(owned, dict):
        errors.append('dll_owned_globals must map each variable name to the reason it lives in the DLL')
        owned = {n: '' for n in owned}
    for name, reason in sorted(owned.items()):
        if not isinstance(reason, str) or not reason.strip():
            errors.append('dll_owned_globals: %s has no reason' % name)
        n = len(syms.glob_by_name.get(name, []))
        if n != 1:
            errors.append('dll_owned_globals: %s has %d // GLOBAL annotations, needs exactly one' % (name, n))
    return set(owned), errors


def _object_variables(raw):
    """Data symbols of an object file -> (defined, referenced): {qualified name: [enclosing
    function of a local static, or None]}; C names ('_x') read as 'x'. A C tentative definition
    ('int x;' in a .c file) is a common symbol: no section, its size as the value."""
    defined, referenced = collections.defaultdict(list), collections.defaultdict(list)
    for s in Coff(raw).symbols:
        if s.type & 0x20 or (s.sclass == CLASS_STATIC and s.naux > 0):
            continue   # a function, a section
        ds = data_symbol(s.name)
        if ds is None and re.match(r'^_[A-Za-z]\w*$', s.name):
            ds = {'name': s.name[1:], 'func': '', 'local': False}
        if ds:
            is_def = s.section > 0 or (s.section == 0 and s.value > 0)
            (defined if is_def else referenced)[ds['name']].append(ds['func'] if ds['local'] else None)
    return defined, referenced


def _binds(g, funcs):
    """Would an annotation g bind to one of these definitions (data_candidates' rule)? A local
    static of a known function needs an annotation of the same function, any other variable
    one with no enclosing function."""
    return any(same_function(g['func'], f) if f else not g['func'] for f in funcs)


def check_object_names(syms, compiled):
    """After compiling, the catch-all for a misread declaration: every non-const GLOBAL name of a
    compiled source file must be a variable that file's object file (as compiled, before the
    surgery) defines, with the same qualified name and scope (file scope, or a local static of
    the same function). Only the comment-only form (a GUID of a system header) is a reference.
    compiled: {source path: raw object path}. -> error lines."""
    errors = []
    by_file = collections.defaultdict(list)
    for g in syms.globs:
        by_file[os.path.normcase(g['file'])].append(g)
    for path, raw in sorted(compiled.items()):
        anns = by_file.get(os.path.normcase(os.path.relpath(path, SRC)), [])
        anns = [g for g in anns if g['name'] and not (g.get('decl') and is_const_object(g['decl']))]
        if not anns:
            continue
        defined, referenced = _object_variables(raw)
        obj = os.path.basename(raw)
        for g in anns:
            funcs = defined.get(g['name'], []) + (referenced.get(g['name'], []) if g.get('comment_only') else [])
            if _binds(g, funcs):
                continue
            where = '%s:%d: // GLOBAL: WIZ8 0x%08x names %r' % (g['file'], g['line'], g['addr'], g['name'])
            last = g['name'].split('::')[-1]
            other = sorted(n for n in defined if n != g['name'] and n.split('::')[-1] == last)
            if funcs:
                errors.append('%s%s, but %s defines it %s: the enclosing function was misread; it could '
                              'not be bound' % (where, ' (a local static of %s)' % g['func'] if g['func'] else '',
                                                obj, ', '.join('as a local static of %s' % (f or '?') if f is not None
                                                               else 'outside any function' for f in funcs)))
            elif other:
                errors.append('%s, but %s defines %s: a namespace or class scope is missing on one side '
                              '(annotate the definition outside the class or namespace, \'int %s;\'); '
                              'it could not be bound' % (where, obj, ', '.join(other), other[0]))
            else:
                errors.append('%s, but %s defines no variable of that name%s: the declaration was misread '
                              '(keep the annotation directly above a single plain definition); it could '
                              'not be bound' % (where, obj, ' (it only refers to one)' if g['name'] in referenced
                                                else ''))
    return errors


def map_data_symbols(mapf):
    """Data symbols of a link map -> [(decorated, va, obj, static, absolute)]."""
    out, section = [], None
    for line in open(mapf, encoding='ascii', errors='replace'):
        if 'Publics by Value' in line:
            section = 'pub'
            continue
        if 'Static symbols' in line:
            section = 'static'
            continue
        if section is None:
            continue
        m = MAP_LINE.match(line)
        if not m or m.group(4):   # 'f': a function
            continue
        out.append((m.group(2), int(m.group(3), 16), m.group(6).strip(), section == 'static',
                    m.group(1).startswith('0000:')))
    return out


def check_bindings(mapf, names, owned, own_objs):
    """After linking: a // GLOBAL-annotated variable with storage in the DLL (not in
    dll_owned_globals), or bound to an address other than its annotation's -> error lines.
    Returns (errors, {owned name: DLL address})."""
    errors, owned_storage = [], {}
    own = {o.lower() for o in own_objs}
    rows = map_data_symbols(mapf)
    # (name, retail address) of the variables bound to the exe: such an annotation is not split,
    # even if a patch-only variable elsewhere ends with the same name (PatchCache::count next to
    # an annotated RetailList::count)
    bound = set()
    for dec, va, obj, static, absolute in rows:
        ds = data_symbol(dec) if absolute else None
        if ds is not None:
            bound.add((ds['name'], va))
    for dec, va, obj, static, absolute in rows:
        ds = data_symbol(dec)
        if ds is None:
            if not re.match(r'^_[A-Za-z]\w*$', dec):   # C variable "_name"; skips __w8r_<address>
                continue
            ds = {'name': dec[1:], 'func': '', 'internal': False}
        if static:
            ds = dict(ds, internal=True)
        if absolute:
            cands = names.data_candidates(ds, None, owned_too=True)
            if cands and all(c[0] != va for c in cands):
                errors.append('%s is bound to 0x%08x, but its // GLOBAL annotation says %s' % (
                    dec, va, ', '.join('0x%08x (%s)' % (c[0], c[2]) for c in cands)))
            continue
        if obj.lower() not in own:
            continue   # a library's own data (CRT, zlib)
        cands = names.data_candidates(ds, _stem(obj), owned_too=True, loose=True)
        if not cands:
            # the same name in another scope: 'namespace ns { int g_x; }' annotated as g_x is
            # ns::g_x in the DLL (an in-class static member: Owner::s_member)
            for g in names.scope_mismatches(ds, _stem(obj)):
                if (g['name'], g['addr']) in bound:
                    continue
                errors.append('0x%08x %s (%s:%d) has its own storage in wiz8hy.dll: %s at 0x%08x in %s is '
                              '%s, the annotation reads %s (a namespace or class scope is missing on one '
                              'side) - the original code keeps using 0x%08x' % (
                                  g['addr'], g['name'], g['file'], g['line'], dec, va, obj, ds['name'],
                                  g['name'], g['addr']))
            continue   # not a retail variable: patch-only state
        if not ds['func'] and ds['name'] in owned:
            owned_storage[ds['name']] = va
            continue
        for c in cands:
            g = next(x for x in names.globs[ds['name']] if x['addr'] == c[0] and x['file'] == c[2])
            errors.append('0x%08x %s (%s:%d) has its own storage in wiz8hy.dll: %s at 0x%08x in %s '
                          '- the original code keeps using 0x%08x' % (
                              c[0], (ds['func'] + '::' if ds['func'] else '') + ds['name'], g['file'],
                              g['line'], dec, va, obj, c[0]))
    return errors, owned_storage


class PeImage:
    """Sections and base relocations of a PE32 file (read only)."""

    def __init__(self, data):
        self.data = data
        pe = struct.unpack_from('<I', data, 0x3c)[0]
        nsec, = struct.unpack_from('<H', data, pe + 6)
        opt, = struct.unpack_from('<H', data, pe + 20)
        o = pe + 24
        self.base, = struct.unpack_from('<I', data, o + 28)
        reloc_rva, reloc_size = struct.unpack_from('<II', data, o + 96 + 5 * 8)
        self.sections = []   # (va, size, raw offset, raw size, is code)
        for i in range(nsec):
            _, vsize, vaddr, rsize, raddr, _, _, _, _, chars = struct.unpack_from(
                '<8sIIIIIIHHI', data, o + opt + i * 40)
            self.sections.append((self.base + vaddr, max(vsize, rsize), raddr, rsize, bool(chars & 0x20)))
        self.reloc_sites = []   # every place in the image that holds an absolute address
        off = self.offset(self.base + reloc_rva)
        end = off + reloc_size
        while off + 8 <= end:
            page, size = struct.unpack_from('<II', data, off)
            if size < 8:
                break
            for k in range((size - 8) // 2):
                e, = struct.unpack_from('<H', data, off + 8 + 2 * k)
                if e >> 12 == 3:   # IMAGE_REL_BASED_HIGHLOW
                    self.reloc_sites.append(self.base + page + (e & 0xfff))
            off += size

    def offset(self, va):
        for sva, size, raddr, rsize, _ in self.sections:
            if sva <= va < sva + size:
                return raddr + va - sva if va - sva < rsize else None
        return None

    def dword(self, va):
        off = self.offset(va)
        return struct.unpack_from('<I', self.data, off)[0] if off is not None else None

    def byte(self, va):
        off = self.offset(va)
        return self.data[off] if off is not None else None

    def is_code(self, va):
        return any(sva <= va < sva + size for sva, size, _, _, code in self.sections if code)

    def code_end(self, va):
        return next((sva + size for sva, size, _, _, code in self.sections if code and sva <= va < sva + size), va)


OBJDUMP = os.path.join(ROOT, 'Tools', 'llvm-mingw', 'bin', 'llvm-objdump.exe')
# a 10-byte instruction fills the byte column: no space between its last byte and the tab
_OBJDUMP_LINE = re.compile(r'^\s*([0-9a-f]+):\s((?:[0-9a-f]{2} ?)+?)\s*\t([^\t]+?)(?:\t(.*))?$')
_OBJDUMP_ADDR = re.compile(r'^\s*[0-9a-f]+:\s')
_BRANCH_TARGET = re.compile(r'^0x([0-9a-f]+)\b')
_SWITCH_JUMP = re.compile(r'^dword ptr \[(?:4\*e[a-z]{2}|e[a-z]{2}\*4) \+ 0x([0-9a-f]+)\]$')


def objdump_decoder(exe):
    """(start, stop) -> {address: (end, mnemonic, operands)}: llvm-objdump's linear disassembly."""
    if not os.path.exists(OBJDUMP):
        raise FileNotFoundError('function extents need ' + OBJDUMP)

    def decode(start, stop):
        out = subprocess.run([OBJDUMP, '-d', '-M', 'intel', '--start-address=0x%x' % start,
                              '--stop-address=0x%x' % stop, exe],
                             capture_output=True, text=True, errors='replace').stdout
        insns = {}
        for line in out.splitlines():
            m = _OBJDUMP_LINE.match(line)
            if m:
                a = int(m.group(1), 16)
                insns[a] = (a + len(m.group(2).split()), m.group(3).strip(), (m.group(4) or '').strip())
            elif _OBJDUMP_ADDR.match(line):
                raise ValueError('cannot read llvm-objdump output: %r' % line)
        return insns
    return decode


class RetailCode:
    """Where each annotated retail function really ends. Its extent is the code reachable from its
    start by recursive descent (fall-through, conditional and unconditional jumps inside it, the
    targets of its switch jump tables), never past the next annotated start; nop/int3 padding ends
    a path, and a jump to a 16-byte aligned address right after padding is a tail call into another
    function. Code after the extent (compiler-generated dynamic initializers and atexit destructors
    such as 0x00482250/0x00482270, thunks, library functions without an annotation) belongs to no
    known function: owner() returns None for it.
    decode(start, stop) -> {address: (end, mnemonic, operands)}; byte(va), dword(va) read the
    image; relocs: the set of addresses that hold an absolute address; code_end(va): end of the
    code section of va."""

    def __init__(self, starts, decode, byte, dword, relocs, code_end):
        self.starts = sorted(set(starts))
        self.decode, self.byte, self.dword = decode, byte, dword
        self.relocs, self.code_end = relocs, code_end
        self.insns, self.extents = {}, {}

    def _limit(self, s):
        k = bisect.bisect_right(self.starts, s)
        end = self.code_end(s)
        return min(self.starts[k], end) if k < len(self.starts) else end

    def _insn(self, a, lim):
        if a not in self.insns:
            self.insns.update(self.decode(a, min(lim, a + 0x800)))   # resynchronize at a
        return self.insns.get(a)

    def _after_padding(self, t):
        p = self.insns.get(t - 1)
        return t % 16 == 0 and p is not None and p[0] == t and self.byte(t - 1) in (0x90, 0xcc)

    def _switch_targets(self, ops, s, lim):
        """'jmp dword ptr [4*eax + T]' with the table T inside the function -> [(case, table end)]."""
        m = _SWITCH_JUMP.match(ops)
        out = []
        if m:
            t = int(m.group(1), 16)
            while s <= t < lim and t in self.relocs and s <= (self.dword(t) or 0) < lim:
                out.append((self.dword(t), t + 4))
                t += 4
        return out

    def extent(self, s):
        """-> (start, end) of the function at annotated start s."""
        if s in self.extents:
            return self.extents[s]
        lim = self._limit(s)
        self.insns.update(self.decode(s, min(lim, s + 0x40000)))   # linear sweep for _after_padding
        work, seen, end = [s], set(), s
        while work:
            a = work.pop()
            while s <= a < lim and a not in seen:
                ins = self._insn(a, lim)
                if ins is None:
                    break
                seen.add(a)
                nxt, mn, ops = ins
                if (mn in ('nop', 'int3') and not ops) or mn == '<unknown>':
                    break                               # padding: the code before it has ended
                end = max(end, nxt)
                if mn.startswith('ret') or mn in ('hlt', 'ud2', 'iretd'):
                    break
                if mn.startswith('j') or mn.startswith('loop'):
                    m = _BRANCH_TARGET.match(ops)
                    if m:
                        t = int(m.group(1), 16)
                        if s <= t < lim and (t == s or not self._after_padding(t)):
                            work.append(t)
                    elif mn == 'jmp':
                        for t, table_end in self._switch_targets(ops, s, lim):
                            work.append(t)
                            end = max(end, table_end)
                    if mn == 'jmp':
                        break
                a = nxt
        self.extents[s] = (s, end)
        return self.extents[s]

    def owner(self, va):
        """-> the annotated start whose extent holds va, or None."""
        k = bisect.bisect_right(self.starts, va) - 1
        if k < 0:
            return None
        s = self.starts[k]
        return s if va < self.extent(s)[1] else None


def load_retail_exe():
    """-> (path, bytes) of the original Wiz8.exe 1.2.4, or (None, None)."""
    for p in RETAIL_EXES:
        if os.path.exists(p):
            blob = open(p, 'rb').read()
            if hashlib.sha256(blob).hexdigest().upper() == RETAIL_EXE_SHA256:
                return p, blob
    return None, None


def retail_code(path, img, starts):
    return RetailCode(starts, objdump_decoder(path), img.byte, img.dword, set(img.reloc_sites),
                      img.code_end)


# real code of the original: annotated start -> next annotated start -> the extent the guard must find
RETAIL_EXTENT_CASES = [
    # ret, nop padding, then two compiler-generated functions without annotations: a dynamic
    # initializer (0x00482250, registers 0x00482270 with atexit) and its atexit destructor
    ((0x00482140, 0x00482280), (0x00482140, 0x00482178), [0x00482252, 0x00482270, 0x00482180]),
    # WindowProcedure: two switch tables at its end; cases after the first ret are reached only
    # through them (0x0040150c), the tables end at 0x0040156c
    ((0x004011e0, 0x00401570), (0x004011e0, 0x0040156c), []),
    # InitializeRendererSceneObjects (Ghidra: 0x00423500..0x00423e41): a 10-byte instruction at
    # 0x00423c77; then unannotated scalar deleting destructors 0x00423e50..0x00423f20
    ((0x00423500, 0x00423f30), (0x00423500, 0x00423e42), [0x00423e50, 0x00423e80, 0x00423f00]),
]


def check_retail_code(path, img):
    """The extent finder on known pieces of the original (see RETAIL_EXTENT_CASES). -> errors"""
    errors = []
    for (s, nxt), want, outside in RETAIL_EXTENT_CASES:
        code = retail_code(path, img, [s, nxt])
        got = code.extent(s)
        if got != want:
            errors.append('function extent self-test: 0x%08x..0x%08x, want 0x%08x..0x%08x' % (got + want))
        for va in outside:
            if code.owner(va) is not None:
                errors.append('function extent self-test: 0x%08x is not part of 0x%08x' % (va, s))
    return errors


def check_owned_users(syms, owned, transplant, stub_addrs):
    """A dll_owned_globals array is a second copy of the retail one. The retail copy is only safe to
    abandon if every retail function that uses it is dead in the hybrid: transplanted, or never
    reached (the DLL has no stub for it, no pointer to it is stored anywhere in the original, and
    every direct call/jmp to it comes from a transplanted function). A use or a call in retail
    code outside every annotated function's extent (RetailCode) is an error: nothing says that
    code is dead. -> (report lines, errors)"""
    if not owned:
        return [], []
    path, data = load_retail_exe()
    if data is None:
        return [], ['dll_owned_globals check: the original Wiz8.exe 1.2.4 is not in ghidra\\bin or games\\reference']
    img = PeImage(data)
    try:
        errors = check_retail_code(path, img)
        if errors:
            return [], errors
        return _owned_users(syms, owned, transplant, stub_addrs, img, data,
                            retail_code(path, img, [f['addr'] for f in syms.funcs]))
    except (OSError, ValueError) as e:   # llvm-objdump is missing, or its output cannot be read
        return [], ['dll_owned_globals check: %s' % e]


def _owned_users(syms, owned, transplant, stub_addrs, img, data, code):
    targets = [(site, img.dword(site)) for site in img.reloc_sites]
    pointed_to = {t for _, t in targets}
    gaddrs = sorted({g['addr'] for g in syms.globs})

    def fname(addr):
        return syms.by_addr[addr][0]['name'] if addr in syms.by_addr else '?'

    def unknown(va):
        k = bisect.bisect_right(code.starts, va) - 1
        if k < 0:
            return 'retail code at 0x%08x before every annotated function' % va
        s = code.starts[k]
        return 'unknown retail code at 0x%08x (after %s 0x%08x, which ends at 0x%08x)' % (
            va, fname(s), s, code.extent(s)[1])

    users = {}
    for name in sorted(owned):
        lo = syms.glob_by_name[name][0]['addr']
        k = bisect.bisect_right(gaddrs, lo)
        hi = gaddrs[k] if k < len(gaddrs) else lo + 4   # up to the next annotated variable
        u, in_data, in_unknown = collections.defaultdict(list), [], []
        for site, t in targets:
            if t is None or not lo <= t < hi:
                continue
            if not img.is_code(site):
                in_data.append(site)
            elif code.owner(site) is None:
                in_unknown.append(site)
            else:
                u[code.owner(site)].append(site)
        users[name] = (lo, hi, u, in_data, in_unknown)
    suspects = {f for _, _, u, _, _ in users.values() for f in u if f not in transplant}
    calls = collections.defaultdict(list)   # direct E8/E9 rel32 calls and jumps to the suspects
    if suspects:
        for sva, size, raddr, rsize, is_code in img.sections:
            if not is_code:
                continue
            blob = data[raddr:raddr + rsize]
            for m in re.finditer(b'[\xe8\xe9]', blob):
                p = m.start()
                if p + 5 <= len(blob):
                    t = (sva + p + 5 + struct.unpack_from('<i', blob, p + 1)[0]) & 0xffffffff
                    if t in suspects:
                        calls[t].append(sva + p)
    report, errors = [], []
    for name, (lo, hi, u, in_data, in_unknown) in sorted(users.items()):
        if in_data:
            errors.append('dll_owned %s: the original stores pointers into the retail array at %s' % (
                name, ', '.join('0x%08x' % s for s in in_data)))
        for site in in_unknown:
            errors.append('dll_owned %s: unknown retail user at 0x%08x: %s uses the retail array '
                          '(0x%08x..0x%08x); annotate that function and transplant it' % (
                              name, site, unknown(site), lo, hi))
        replaced = sorted(f for f in u if f in transplant)
        dead = []
        for f, sites in sorted(u.items()):
            if f in transplant:
                continue
            why = []
            if f in stub_addrs:
                why.append('the DLL calls it')
            if f in pointed_to:
                why.append('its address is stored in the original (callback or vtable)')
            live = set()
            for s in calls.get(f, []):
                c = code.owner(s)
                if c is None:
                    live.add(unknown(s))
                elif c not in transplant:
                    live.add('the retail %s 0x%08x' % (fname(c), c))
            if live:
                why.append('called from %s' % ', '.join(sorted(live)))
            if why:
                errors.append('dll_owned %s: the retail %s 0x%08x still uses the retail array '
                              '(0x%08x..0x%08x) and is reachable: %s' % (
                                  name, fname(f), f, lo, hi, '; '.join(why)))
            else:
                dead.append('%s 0x%08x' % (fname(f), f))
        report.append('dll_owned %s (retail 0x%08x..0x%08x): %d retail users transplanted%s' % (
            name, lo, hi, len(replaced), ', dead in the hybrid: ' + ', '.join(dead) if dead else ''))
    return report, errors


# --- outputs: staged, published only after every check passed ------------------------------------
STAGE = os.path.join(OUT, 'staging')
GUARD_FAILED = os.path.join(OUT, 'GUARD_FAILED')
BUILD_STARTED = []   # the GUARD_FAILED marker of a build that has started (main)
PAIR = ('wiz8hy.map', 'wiz8hy_hooks.txt', 'wiz8hy.dll')   # moved in this order


def _write_text(path, text):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, path)


def write_guard_failed(marker, lines):
    """GUARD_FAILED next to the last good pair: make-hybrid-package.ps1 and try_hybrid.ps1 refuse
    to use build\\hybrid while it exists. Every build writes it when it starts (so a compile,
    link or trap error, or an interrupted build, leaves it too); only publish() removes it, and
    import-release.ps1 -Binaries when it installs a released pair."""
    os.makedirs(os.path.dirname(marker), exist_ok=True)
    _write_text(marker, 'The last hybrid build did not publish a new wiz8hy.dll + wiz8hy_hooks.txt: it failed or '
                'has not finished (docs\\hybrid.md, "How wiz8hy.dll is built").\n'
                'wiz8hy.dll and wiz8hy_hooks.txt here are the last good pair, older than the sources.\n\n' +
                '\n'.join(lines) + '\n')


def note_build_stopped(marker, reason):
    """Add why a build stopped to its GUARD_FAILED marker."""
    if os.path.exists(marker):
        with open(marker, 'a', encoding='utf-8') as f:
            f.write('\nThe build stopped: %s\n' % reason)


def fail_guard(lines, message):
    write_guard_failed(GUARD_FAILED, lines)
    print('\n'.join(lines))
    raise SystemExit('binding guard: %s, see docs\\hybrid.md "Game variables" (%s written)' % (
        message, os.path.relpath(GUARD_FAILED, ROOT)))


def publish(stage, out, marker):
    """Move the checked map, hooks and dll from the staging folder over the last good ones. The
    marker covers the moment in between (a crash there would leave a mismatched pair). A move
    that fails (a target read-only or held open) puts back the files already replaced, from
    copies made first, so the last good pair stays whole."""
    _write_text(marker, 'A new wiz8hy.dll + wiz8hy_hooks.txt pair was being moved into place; if this file '
                'is still here, the move was interrupted: rebuild.\n')
    keep = os.path.join(stage, 'last-good')
    os.makedirs(keep, exist_ok=True)
    for n in PAIR:
        if os.path.exists(os.path.join(out, n)):
            shutil.copy2(os.path.join(out, n), os.path.join(keep, n))
        elif os.path.exists(os.path.join(keep, n)):
            os.remove(os.path.join(keep, n))
    done = []
    try:
        for n in PAIR:
            os.replace(os.path.join(stage, n), os.path.join(out, n))
            done.append(n)
    except OSError:
        for n in done:
            if os.path.exists(os.path.join(keep, n)):
                shutil.copy2(os.path.join(keep, n), os.path.join(out, n))
        raise
    os.remove(marker)


# --- self-test of the guard's own logic (main runs it before every build) --------------------------
def _fake_code(prog, starts, relocs=(), dwords=None):
    """RetailCode over a hand-written program {address: (end, mnemonic, operands)}."""
    def decode(start, stop):
        return {a: v for a, v in prog.items() if start <= a < stop}

    def byte(va):
        v = prog.get(va)
        return {'nop': 0x90, 'int3': 0xcc}.get(v[1], 0) if v and v[0] == va + 1 else 0
    return RetailCode(starts, decode, byte, (dwords or {}).get, set(relocs), lambda va: 0x10000)


def _nops(lo, hi):
    return {a: (a + 1, 'nop', '') for a in range(lo, hi)}


def _write_test_obj(path, defined, referenced=(), common=()):
    """A COFF object file with data symbols: defined ones in .data, external references and
    common symbols (C tentative definitions: no section, the size as the value)."""
    strtab, symtab = bytearray(b'\0\0\0\0'), bytearray()
    syms = [(n, 4 * k, 1) for k, n in enumerate(defined)] + [(n, 0, 0) for n in referenced] + \
        [(n, 4, 0) for n in common]
    for name, value, section in syms:
        nb = name.encode('latin-1')
        if len(nb) <= 8:
            raw = nb.ljust(8, b'\0')
        else:
            raw = struct.pack('<II', 0, len(strtab))
            strtab += nb + b'\0'
        symtab += raw + struct.pack('<IhHBB', value, section, 0, 2, 0)
    struct.pack_into('<I', strtab, 0, len(strtab))
    data = bytes(4 * len(defined))
    out = struct.pack('<HHIIIHH', 0x14c, 1, 0, 60 + len(data), len(syms), 0, 0)
    out += struct.pack('<8sIIIIIIHHI', b'.data', 0, 0, len(data), 60, 0, 0, 0, 0, 0xc0300040)
    with open(path, 'wb') as f:
        f.write(out + data + symtab + strtab)


class _TestSyms:
    """Symbols-like annotations for the self-test."""

    def __init__(self, globs):
        self.funcs, self.globs, self.glob_by_name = [], globs, collections.defaultdict(list)
        for g in globs:
            g.setdefault('func', '')
            g.setdefault('text', g.get('decl', ''))
            self.glob_by_name[g['name']].append(g)


def guard_selftest():
    """-> failure strings: function extents, publishing and the GUARD_FAILED marker, the
    catch-all, check_bindings on scope mismatches, binding local statics of an operator and a
    template function, check_annotations on in-class declarations and headers."""
    bad = []
    # a function, its padding, then a compiler-generated initializer without an annotation
    prog = {0x1000: (0x1005, 'mov', 'ecx, 0x65b998'), 0x1005: (0x1006, 'ret', ''),
            0x1010: (0x1015, 'push', '0x1030'), 0x1015: (0x1016, 'ret', '')}
    prog.update(_nops(0x1006, 0x1010))
    prog.update(_nops(0x1016, 0x1020))
    code = _fake_code(prog, [0x1000, 0x1020])
    if code.extent(0x1000) != (0x1000, 0x1006) or code.owner(0x1003) != 0x1000 or code.owner(0x1012):
        bad.append('extent: initializer after the padding counted as part of the function: '
                   '0x%x..0x%x' % code.extent(0x1000))
    # internal jumps backward and forward; a tail jump to an aligned function after padding
    prog = {0x2000: (0x2002, 'je', '0x2009 <.text>'), 0x2002: (0x2007, 'mov', 'eax, 1'),
            0x2007: (0x2009, 'jmp', '0x2030 <.text>'), 0x2009: (0x200e, 'mov', 'eax, 2'),
            0x200e: (0x2010, 'jmp', '0x2002 <.text>'),
            0x2030: (0x2035, 'mov', 'ecx, 3'), 0x2035: (0x2036, 'ret', '')}
    prog.update(_nops(0x2010, 0x2030))
    prog.update(_nops(0x2036, 0x2040))
    code = _fake_code(prog, [0x2000, 0x2040])
    if code.extent(0x2000) != (0x2000, 0x2010) or code.owner(0x2031):
        bad.append('extent: tail jump target counted as part of the function: 0x%x..0x%x' % code.extent(0x2000))
    # a switch: cases after the first ret are reached only through the jump table at the end
    prog = {0x3000: (0x3003, 'cmp', 'eax, 2'), 0x3003: (0x3005, 'ja', '0x3020 <.text>'),
            0x3005: (0x300c, 'jmp', 'dword ptr [4*eax + 0x3024]'),
            0x300c: (0x3011, 'mov', 'eax, 1'), 0x3011: (0x3012, 'ret', ''),
            0x3012: (0x3017, 'mov', 'eax, 2'), 0x3017: (0x3018, 'ret', ''),
            0x3018: (0x3020, 'mov', 'dword ptr [0x600000], 3'), 0x3020: (0x3021, 'ret', '')}
    prog.update(_nops(0x3021, 0x3024))
    code = _fake_code(prog, [0x3000, 0x3030], relocs=[0x3024, 0x3028, 0x302c],
                      dwords={0x3024: 0x300c, 0x3028: 0x3012, 0x302c: 0x3018})
    if code.extent(0x3000) != (0x3000, 0x3030) or code.owner(0x301a) != 0x3000:
        bad.append('extent: switch cases or table missed: 0x%x..0x%x' % code.extent(0x3000))
    # padding right after a call that does not return
    prog = {0x4000: (0x4005, 'call', '0x9000 <.text>'), 0x4010: (0x4015, 'mov', 'eax, 4'),
            0x4015: (0x4016, 'ret', '')}
    prog.update(_nops(0x4005, 0x4010))
    code = _fake_code(prog, [0x4000, 0x4020])
    if code.extent(0x4000) != (0x4000, 0x4005) or code.owner(0x4011):
        bad.append('extent: ran through the padding after a call: 0x%x..0x%x' % code.extent(0x4000))
    # publishing: a failed guard leaves the last good pair; a pass replaces it and the marker goes
    tmp = os.path.join(OUT, 'selftest')
    try:
        shutil.rmtree(tmp, ignore_errors=True)
        out, stage = tmp, os.path.join(tmp, 'staging')
        os.makedirs(stage)
        marker = os.path.join(out, 'GUARD_FAILED')
        for n in PAIR:
            _write_text(os.path.join(out, n), 'old')
            _write_text(os.path.join(stage, n), 'new')
        write_guard_failed(marker, ['an error'])
        if not os.path.exists(marker) or any(open(os.path.join(out, n)).read() != 'old' for n in PAIR):
            bad.append('publish: a failed guard touched the last good pair or wrote no marker')
        publish(stage, out, marker)
        if os.path.exists(marker) or any(open(os.path.join(out, n)).read() != 'new' for n in PAIR):
            bad.append('publish: the new pair was not moved into place or the marker stayed')
        # a build writes the marker when it starts; a compile/link error leaves it with the reason
        write_guard_failed(marker, ['A build started'])
        note_build_stopped(marker, 'link failed')
        if 'The build stopped: link failed' not in open(marker, encoding='utf-8').read():
            bad.append('marker: the reason a build stopped was not recorded')

        # the catch-all: every non-const annotation must be a variable the object defines, with the
        # same qualified name and scope (a misread name: 'int g_x WIZ8_ALIGNED;' read as WIZ8_ALIGNED)
        src = os.path.join('src', 'selftest.cpp')
        obj = os.path.join(tmp, 'selftest.obj')
        _write_test_obj(obj, ['?g_present@@3HA', '_g_c_var', '?g_in_ns@ns@@3HA', '?s_member@Owner@@2HA',
                              '?g_x@@3HA', '?s_op@?1???4Owner@@QAEAAV0@ABV0@@Z@4HA',
                              '?s_tmpl@?1???$Tmpl@H@@YAXH@Z@4HA', '?s_other@?1??Other@@YAXXZ@4HA'],
                        ['?g_other@@3HA', '_IID_IDirectDraw2'], ['_g_c_common'])
        syms = _TestSyms([dict(file=src, line=n + 1, addr=0x600000 + 4 * n, **g) for n, g in enumerate([
            dict(name='g_present', decl='int g_present;'), dict(name='g_c_var', decl='int g_c_var;'),
            dict(name='g_c_common', decl='int g_c_common;'),                     # a common symbol
            dict(name='WIZ8_ALIGNED', decl='int g_x WIZ8_ALIGNED;'),             # misread
            dict(name='g_folded', decl='const int g_folded = 1;'),               # const: skipped
            dict(name='g_in_ns', decl='int g_in_ns;'),                           # ns::g_in_ns
            dict(name='s_member', decl='static int s_member;'),                  # Owner::s_member
            dict(name='g_other', decl='extern int g_other; int g_x;'),           # only referenced
            dict(name='IID_IDirectDraw2', decl='', comment_only=True),          # a reference is right
            dict(name='s_op', decl='static int s_op;', func='Owner::operator='),
            dict(name='s_tmpl', decl='static int s_tmpl;', func='Tmpl'),
            dict(name='s_other', decl='static int s_other;', func='Mine')])])   # another function's
        errs = check_object_names(syms, {os.path.join(SRC, src): obj})
        want = ['WIZ8_ALIGNED', 'g_in_ns', 's_member', 'g_other', 's_other']
        if len(errs) != len(want) or any("names '%s'" % n not in e for n, e in zip(want, errs)):
            bad.append('check_object_names: %r, want errors for %s' % (errs, ', '.join(want)))

        # after linking: DLL storage for a variable annotated without (or with another) scope
        mapf = os.path.join(tmp, 'selftest.map')
        _write_text(mapf, '  Address         Publics by Value              Rva+Base       Lib:Object\n\n' + ''.join(
            ' %s       %-26s %08x %s\n' % x for x in [
                ('0003:00000000', '?g_in_ns@ns@@3HA', 0x10003000, '    selftest.obj'),
                ('0003:00000004', '?s_member@Owner@@2HA', 0x10003004, '    selftest.obj'),
                ('0003:00000008', '?g_patch_only@@3HA', 0x10003008, '    selftest.obj'),
                ('0000:00000000', '?g_present@@3HA', 0x00600000, '    <absolute>')]))
        names = Names(syms, set(), vtables={})
        errs, _ = check_bindings(mapf, names, set(), ['selftest.obj'])
        if len(errs) != 2 or 'ns::g_in_ns' not in errs[0] or 'Owner::s_member' not in errs[1]:
            bad.append('check_bindings: %r, want errors for ns::g_in_ns, Owner::s_member' % errs)

        # the scanner side: a namespace variable binds by its qualified name; local statics in an
        # operator and in a template function bind; an in-class declaration and an annotation in
        # a header are errors before compiling
        _, globs = scan_lines(['namespace ns {', '// GLOBAL: WIZ8 0x00600100', 'int g_in_ns;', '}',
                               'Owner& Owner::operator=(const Owner& o)', '{', '    // GLOBAL: WIZ8 0x00600104',
                               '    static int s_op;', '}', 'template <class T> void Tmpl(T x)', '{',
                               '    // GLOBAL: WIZ8 0x00600108', '    static int s_tmpl;', '}',
                               'class Owner', '{', '    // GLOBAL: WIZ8 0x0060010c', '    static int s_member;',
                               '};'], src)
        names = Names(_TestSyms(globs), set(), vtables={})
        for dec, addr in [('?g_in_ns@ns@@3HA', 0x600100), ('?s_op@?1???4Owner@@QAEAAV0@ABV0@@Z@4HA', 0x600104),
                          ('?s_tmpl@?1???$Tmpl@H@@YAXH@Z@4HA', 0x600108)]:
            if names.resolve(dec, os.path.join(SRC, src)) != (addr, 'd'):
                bad.append('binding: %s -> %r, want 0x%08x' % (dec, names.resolve(dec, os.path.join(SRC, src)), addr))
        _, errs = check_annotations(_TestSyms(globs + [dict(
            file=os.path.join('include', 'wiz8', 'selftest.h'), line=1, addr=0x600110, name='g_in_header',
            decl='int g_in_header;')]), {'dll_owned_globals': {}})
        if len(errs) != 2 or 'inside class Owner' not in errs[0] or '.c/.cpp' not in errs[1]:
            bad.append('check_annotations: %r, want errors for the in-class declaration and the header' % errs)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return bad


UNRESOLVED = re.compile(r'unresolved external symbol (?:"[^"]*" \((\S+?)\)|(\S+))')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default=os.path.join(HERE, 'transplant_wide.json'))
    ap.add_argument('--no-compile', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        failures = ['symbols.py: ' + x for x in selftest()] + \
            ['build_hybrid.py: ' + x for x in guard_selftest()]
        path, data = load_retail_exe()
        if data is not None:
            try:
                failures += check_retail_code(path, PeImage(data))
            except (OSError, ValueError) as e:
                failures.append(str(e))
        print('\n'.join(failures) or 'self-test OK%s' % (
            '' if data is not None else ' (original Wiz8.exe not found: function extents on it skipped)'))
        sys.exit(1 if failures else 0)
    # from here until publish() build\hybrid holds a pair older than the sources: the marker says
    # so whatever stops this build (a guard, compile, link or trap error, an interruption)
    write_guard_failed(GUARD_FAILED, ['A build started; if it stopped, its reason is below or in its output.'])
    BUILD_STARTED.append(GUARD_FAILED)
    cfg = json.load(open(a.config, encoding='utf-8'))
    transplant = {int(k, 16): v for k, v in cfg['transplant'].items()}
    os.makedirs(os.path.join(OUT, 'obj'), exist_ok=True)

    # the annotation/decorated-name parsers the binding depends on, and the guard's own logic
    failures = ['symbols.py: ' + x for x in selftest()] + ['build_hybrid.py: ' + x for x in guard_selftest()]
    if failures:
        fail_guard(failures, 'self-test failed')
    syms = Symbols(use_cache=False)
    owned, ann_errors = check_annotations(syms, cfg)
    if ann_errors:
        fail_guard(ann_errors, '%d annotation error(s)' % len(ann_errors))
    for n in PAIR:   # stale staged files from an earlier run that failed
        if os.path.exists(os.path.join(STAGE, n)):
            os.remove(os.path.join(STAGE, n))
    os.makedirs(STAGE, exist_ok=True)
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

    dll = os.path.join(STAGE, 'wiz8hy.dll')    # same file names as the published ones (the map
    mapf = os.path.join(STAGE, 'wiz8hy.map')   # and the export table name the module)
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
        added_now = set()  # units added in this pass: their other symbols resolve on the next link
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
                    added_now.add(cands[0])
                    progress = True
                    continue
                if len(cands) == 1 and cands[0] in added_now:
                    continue
                if len(cands) == 1 and cands[0] in objs:
                    errors.append('%s defined in %s but still unresolved' % (name, fn))
                    continue
            if not m:
                src = find_definition(names.qname(name)[0])
                if src and src not in objs:
                    auto_units.append(src)
                    add(src, True)
                    added_now.add(src)
                    progress = True
                    continue
                if src in added_now:
                    # A new unit that defines several of the unresolved symbols: only the
                    # first one adds it; the rest must not become traps (a trap is an
                    # error once the real definition is linked).
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
    with open(os.path.join(STAGE, 'wiz8hy_hooks.txt'), 'w', encoding='ascii') as f:
        for dec, addr in sorted(want.items(), key=lambda x: x[1]):
            if dec not in rva:
                raise SystemExit('no RVA for %s' % dec)
            f.write('%08x %08x %s\n' % (addr, rva[dec], dec))
    print('linked %s (%d bytes), %d hooks, %d stubs, %d data, %d dead-only traps' % (
        os.path.relpath(dll, ROOT), os.path.getsize(dll), len(want), len(stubs), len(absol), len(traps)))

    # binding guard, on the staged files: only a pair that passes replaces the last good one
    errors = check_object_names(syms, {p: os.path.join(OUT, 'obj', 'raw', os.path.basename(o))
                                       for p, o in objs.items()})
    bind_errors, owned_storage = check_bindings(mapf, names, owned,
                                                [os.path.basename(o) for o in objs.values()])
    errors += bind_errors
    live_stubs = set()   # retail functions the DLL really calls: stubs kept by /OPT:REF
    for line in open(mapf, encoding='ascii', errors='replace'):
        m = MAP_LINE.match(line)
        if m and m.group(4) and m.group(6).strip().lower() == 'w8bind.obj' and m.group(2) in bind:
            live_stubs.add(bind[m.group(2)][0])
    report, owned_errors = check_owned_users(syms, owned, transplant, live_stubs)
    print('\n'.join(report))
    errors += owned_errors
    if errors:
        fail_guard(errors, '%d error(s): a game variable would exist twice (DLL copy and retail '
                           'address); the last good wiz8hy.dll + wiz8hy_hooks.txt stay in place' % len(errors))
    print('binding guard: OK - no annotated game variable has DLL storage except dll_owned_globals (%s)'
          % ', '.join('%s 0x%08x' % kv for kv in sorted(owned_storage.items())))
    publish(STAGE, OUT, GUARD_FAILED)
    print('published %s' % ', '.join(os.path.relpath(os.path.join(OUT, n), ROOT) for n in PAIR))


if __name__ == '__main__':
    try:
        main()
    except BaseException as e:
        if BUILD_STARTED and not (isinstance(e, SystemExit) and e.code in (None, 0)):
            note_build_stopped(BUILD_STARTED[0], e.code if isinstance(e, SystemExit) else
                               '%s: %s' % (type(e).__name__, e))
        raise
