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
ANY_ANN = re.compile(r'^\s*//\s*[A-Z_]+:\s*WIZ8\b')   # FUNCTION, GLOBAL, VTABLE, STRING, ...
# annotations of another entity (a STRING annotation describes the initializer of the same declaration)
OTHER_ANN = re.compile(r'^\s*//\s*(?:FUNCTION|GLOBAL|VTABLE):\s*WIZ8\b')
FUNCTION_ANN = re.compile(r'^\s*//\s*FUNCTION:\s*WIZ8\b')
IDENT_BEFORE_PAREN = re.compile(r'([A-Za-z_~][A-Za-z0-9_:~<>]*)\s*\(')
# the comment-only form of a GLOBAL annotation is for variables that a system header defines
GUID_NAME = re.compile(r'^(?:IID|CLSID|GUID)_\w+$')
MAP_LINE = re.compile(r'^\s*([0-9a-fA-F]{4}:[0-9a-fA-F]{8})\s+(\S+)\s+([0-9a-fA-F]{8})\s+(f\s+)?(i\s+)?(.*)$')


def _source_files():
    for base in ('src', 'include'):
        for dirpath, _, files in os.walk(os.path.join(SRC, base)):
            for fn in files:
                if fn.endswith(('.cpp', '.c', '.h', '.hpp', '.inc')):
                    yield os.path.join(dirpath, fn)


# --- the name declared by a C/C++ variable declaration -------------------------------------------
# The hybrid build binds a game variable to its retail address by this name; an empty or wrong
# name silently left a private copy in wiz8hy.dll (g_fade_callback: party death hung, 1.0.0-1.0.1).
_CALLCONV = r'(?:__cdecl|__stdcall|__fastcall|__thiscall|_cdecl|_stdcall|WINAPI|CALLBACK|APIENTRY|PASCAL|FAR|NEAR)'
_DECL_GROUP = re.compile(r'^(?:%s\s*)*[*&]' % _CALLCONV)      # "(*name" / "(__cdecl* name"
_TRAILING_NAME = re.compile(r'([A-Za-z_]\w*(?:\s*::\s*[A-Za-z_]\w*)*)\s*$')
_NOT_A_NAME = {'void', 'char', 'short', 'int', 'long', 'float', 'double', 'signed', 'unsigned', 'bool',
               'const', 'volatile', 'static', 'extern', 'struct', 'class', 'union', 'enum', 'register'}
_PAIRS = {')': '(', ']': '[', '>': '<', '}': '{'}
_MACRO_LIKE = re.compile(r'^(?:[A-Z][A-Z0-9]*_[A-Z0-9_]*|__\w*)$')   # WIZ8_ALIGN, __attribute__
_TRAILING_IDENT = re.compile(r'([A-Za-z_]\w*)\s*$')
_LITERALS = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
# a type defined in the declaration itself: 'struct W8Stats { int a; } g_stats;' (left of the '{')
_TYPE_BODY = re.compile(r'\b(?:struct|class|union|enum)\b(?:\s+(?:class|struct))?'
                        r'(?:\s+[A-Za-z_]\w*(?:\s*::\s*[A-Za-z_]\w*)*)?\s*(?::[^;]*)?$')
_ALL_CAPS = re.compile(r'^[A-Z][A-Z0-9_]*$')
_BUILTIN_TYPES = {'void', 'char', 'short', 'int', 'long', 'float', 'double', 'signed', 'unsigned', 'bool',
                  'wchar_t', '__int8', '__int16', '__int32', '__int64'}
_QUALIFIERS = {'static', 'extern', 'const', 'volatile', 'register', 'mutable', 'inline', 'typename',
               'struct', 'class', 'union', 'enum', 'constexpr', 'thread_local', 'alignas', 'CONST'}


def _bracket_step(stack, ch, angle=True):
    """Follow the brackets through one character: an opening one is pushed on stack, a closing
    one pops its partner. With angle, '<' and '>' are template brackets, except inside
    parentheses or square brackets within template arguments, where they compare
    ('Foo<(1 < 2)>'); a '<' still open when its group closes was a comparison as well."""
    if ch in '([{':
        stack.append(ch)
    elif ch in ')]}':
        while stack and stack[-1] == '<':
            stack.pop()
        if stack and stack[-1] == _PAIRS[ch]:
            stack.pop()
    elif angle and ch == '<' and (stack[-1:] == ['<'] or '<' not in stack):
        stack.append(ch)
    elif angle and ch == '>' and stack[-1:] == ['<']:
        stack.pop()


def _has_top_level_comma(decl):
    """'int a, b;' declares two variables: a comma outside brackets (and outside string and
    character literals) before the end of the declaration. '<' and '>' count as brackets only
    left of the initializer (template arguments), not inside it (comparisons, shifts)."""
    s = _LITERALS.sub('""', decl)
    stack, init = [], False
    for ch in s:
        if not stack:
            if ch == ';':
                return False
            if ch == ',':
                return True
            if ch in '={':
                init = True
        _bracket_step(stack, ch, angle=not init)
    return False


def _open_index(s, close_at):
    """Index of the bracket that opens the group closed at s[close_at] (-1 if unbalanced)."""
    want = []
    for k in range(close_at, -1, -1):
        ch = s[k]
        if ch in _PAIRS:
            want.append(_PAIRS[ch])
        elif want and ch == want[-1]:
            want.pop()
            if not want:
                return k
    return -1


def _cut_top_level(s):
    """The declaration without its initializer: cut at the first '=', '{' or ';' outside brackets."""
    stack = []
    for k, ch in enumerate(s):
        if not stack and ch in '={;':
            return s[:k]
        _bracket_step(stack, ch)
    return s


def _drop_templates(s):
    """s without template arguments: 'W8Vector<T*> x' -> 'W8Vector x', 'Foo<(1 < 2)> x' -> 'Foo x'."""
    out, stack = [], []
    for ch in s:
        inside = '<' in stack
        _bracket_step(stack, ch)
        if not inside and '<' not in stack:
            out.append(ch)
    return ''.join(out)


def _name_before(head):
    """True when head, the declaration left of its last identifier, already holds a type and a
    name ('int g_x ', 'W8Stats g_x '): that last identifier is then a macro, not the name."""
    words = re.findall(r'[A-Za-z_]\w*(?:\s*::\s*[A-Za-z_]\w*)*', _LITERALS.sub(' ', head))
    words = [w for w in words if w in _BUILTIN_TYPES or not (
        w in _QUALIFIERS or w.startswith('__') or re.match(r'^%s$' % _CALLCONV, w))]
    builtin = [w for w in words if w in _BUILTIN_TYPES]
    return len(words) - len(builtin) >= (1 if builtin else 2)


def declarator_name(decl):
    """Name of the variable that one declaration declares, or '' when there is none or it is
    not certain (the build then fails instead of binding a wrong name).
    Handles 'T x', 'T x = v', 'T x[N][M] = {..}', 'T (*x)(args)', 'T (__cdecl* x)(args)',
    'T (*x[N])(args) = {..}', 'T (*x)[N]', 'T x(ctor args)', 'T x{..}', templates (also with
    comparisons in their arguments: 'Foo<(1 < 2)> x'), 'A::x', an all-caps name after a type
    ('static INT32 MAX_X'). '' for several declarators ('int a, b;'), for a type defined in the
    declaration ('struct S { .. } x;', also enum and union) and for a macro after the name: an
    all-caps identifier after a type and a name ('int x WIZ8_ALIGNED;', 'int x ALIGN(16);') or
    any macro with arguments that looks like one ('int x WIZ8_ALIGN(16);')."""
    s = re.sub(r'/\*.*?\*/', ' ', decl, flags=re.S)
    s = re.sub(r'__declspec\s*\((?:[^()]|\([^()]*\))*\)', ' ', s)
    if _has_top_level_comma(s):
        return ''
    head = _cut_top_level(s)
    if s[len(head):len(head) + 1] == '{' and _TYPE_BODY.search(head):
        return ''   # 'struct W8Stats { int a; } g_stats;': not 'W8Stats'
    s = _drop_templates(head)
    suffix = False  # an array bound or a parameter list was seen to the right of the name
    while True:
        s = s.rstrip()
        if s.endswith(']') or s.endswith(')'):
            k = _open_index(s, len(s) - 1)
            if k < 0:
                return ''
            if s.endswith(']'):
                s, suffix = s[:k], True
                continue
            inner, before = s[k + 1:-1].strip(), s[:k].rstrip()
            if before.endswith(')'):
                s, suffix = before, True          # parameter list of a function pointer
            elif suffix and _DECL_GROUP.match(inner):
                s, suffix = inner, False          # "(*name)" of "T (*name)(args)" / "T (*name)[N]"
            else:
                mm = _TRAILING_IDENT.search(before)
                if mm and _MACRO_LIKE.match(mm.group(1)):
                    return ''                     # "T name MACRO(args)": not constructor arguments
                s = before                        # constructor arguments: "T name(args)"
            continue
        break
    m = _TRAILING_NAME.search(s)
    if not m:
        return ''
    name = re.sub(r'\s+', '', m.group(1))
    if name in _NOT_A_NAME or name.split('::')[-1].startswith('__'):
        return ''
    if _ALL_CAPS.match(name) and _name_before(s[:m.start()]):
        return ''   # 'int g_x WIZ8_ALIGNED': a macro after the name
    return name


def is_const_object(decl):
    """True when the declared object itself is const ('const int x', 'const char* const x[]',
    'static const float X'), not for a pointer to const ('const char* x'). A const object may be
    folded into its users and need no symbol at all."""
    name = declarator_name(decl)
    if not name:
        return False
    s = re.sub(r'/\*.*?\*/', ' ', decl, flags=re.S)
    s = _drop_templates(_cut_top_level(_LITERALS.sub('""', s)))
    hits = list(re.finditer(r'\b%s\b' % re.escape(name.split('::')[-1]), s))
    head = re.sub(r'[\s(]+$', '', s[:hits[-1].start()] if hits else s)
    if re.search(r'\bconstexpr\b', head) or re.search(r'\bconst$', head):
        return True                       # "constexpr T x", "T* const x", "int const x"
    return not re.search(r'[*&(]', head) and re.search(r'\bconst\b', head) is not None


def name_from_undecorated(text):
    """Variable name from undname output ('void (__cdecl* g_cb)(void)',
    'public: static int A::x', 'class W8Vector<class stLight *> g_v')."""
    text = re.sub(r'^(?:(?:public|protected|private):\s*)?(?:static\s+)?', '', text.strip())
    return declarator_name(text)


# --- MSVC decorated names of variables ------------------------------------------------------------
# Only as much of the scheme as variable names need: the qualified name ('?x@Scope@@'), template
# scopes ('?$Tmpl@<argument types>@'), anonymous namespaces ('?A0x1234abcd@') and the scope marker
# of a function-local static ('?x@?1??<the function's decorated name>@4HA').
_IDENT = re.compile(r'[A-Za-z_]\w*')
_LOCAL_SCOPE = re.compile(r'\?(?:[0-9]|[A-P]+@)\?(?=\?)')   # "?1?" / "?BA@?" before the function's name
# '??<code>': constructor, destructor and the operators, spelled as _function_name reads them
# from a header ('Owner& Owner::operator=(...)' -> 'Owner::operator='); others (conversion
# operators) read as plain 'operator'
_OPERATOR = dict({'0': '{c}', '1': '~{c}', '2': 'operator new', '3': 'operator delete',
                  'A': 'operator[]', 'R': 'operator()', '_U': 'operator new[]', '_V': 'operator delete[]'},
                 **{c: 'operator' + op for c, op in zip(
                     '456789CDEFGHIJKLMNOPQSTUVWXYZ',
                     ['=', '>>', '<<', '!', '==', '!=', '->', '*', '++', '--', '-', '+', '&', '->*', '/', '%',
                      '<', '<=', '>', '>=', ',', '~', '^', '|', '&&', '||', '*=', '+=', '-='])},
                 **{'_' + c: 'operator' + op for c, op in zip(
                     '0123456', ['/=', '%=', '>>=', '<<=', '&=', '|=', '^='])})


def _ident_at(s, i):
    m = _IDENT.match(s, i)
    if not m or s[m.end():m.end() + 1] != '@':
        raise ValueError
    return m.group(0), m.end() + 1


def _number_at(s, i):
    """MSVC encoded number: one digit (value + 1) or hex digits A-P up to '@'."""
    if s[i].isdigit():
        return int(s[i]) + 1, i + 1
    j = s.index('@', i)
    if any(not 'A' <= c <= 'P' for c in s[i:j]):
        raise ValueError
    return int(''.join('%x' % (ord(c) - 65) for c in s[i:j]) or '0', 16), j + 1


def _skip_type(s, i, depth=0):
    """Index after one encoded type (template arguments only need to be skipped)."""
    if depth > 30:
        raise ValueError
    c = s[i]
    if c in 'CDEFGHIJKMNOXZ' or c.isdigit():   # built-in type, back reference
        return i + 1
    if c == '_':
        return i + 2
    if c in 'PQRSAB':                          # pointer, reference
        if s[i + 1] == '6':
            return _skip_function_type(s, i + 2, depth)
        j = i + 1
        while s[j] in 'EFI':                   # __ptr64, __unaligned, __restrict
            j += 1
        if s[j] not in 'ABCD':
            raise ValueError
        return _skip_type(s, j + 1, depth + 1)
    if c in 'TUV':                             # union, struct, class
        return _skip_qualified(s, i + 1, depth)
    if c == 'W':                               # enum
        return _skip_qualified(s, i + 2, depth)
    if c == 'Y':                               # array
        n, j = _number_at(s, i + 1)
        for _ in range(n):
            _, j = _number_at(s, j)
        return _skip_type(s, j, depth + 1)
    if c == '?' and s[i + 1] in 'ABCD':        # cv-qualified class by value
        return _skip_type(s, i + 2, depth + 1)
    if s.startswith('$0', i):                  # integer template argument
        return _number_at(s, i + 3 if s[i + 2] == '?' else i + 2)[1]
    if s.startswith('$$C', i) or s.startswith('$$Q', i):
        return _skip_type(s, i + 4, depth + 1)
    if s.startswith('$$T', i) or s.startswith('$$V', i):
        return i + 3
    raise ValueError


def _skip_function_type(s, i, depth):
    """After 'P6': calling convention, return type, parameters, throw specification."""
    i += 1
    if s[i] == '?':
        i += 2
    i = _skip_type(s, i, depth + 1)
    if s[i] == 'X':
        i += 1
    else:
        while s[i] not in '@Z':
            i = _skip_type(s, i, depth + 1)
        i += 1
    if s[i] != 'Z':
        raise ValueError
    return i + 1


def _fragment(s, i, depth=0):
    """One part of a qualified name -> (text, index after it); text is None for a back
    reference and '' for an anonymous namespace."""
    if s[i].isdigit():
        return None, i + 1
    if s.startswith('?$', i):                  # template: the name, then its argument types
        name, j = _ident_at(s, i + 2)
        while s[j] != '@':
            j = _skip_type(s, j, depth + 1)
        return name, j + 1
    if s.startswith('?A0x', i):
        return '', s.index('@', i) + 1
    if s[i] == '?':
        raise ValueError
    return _ident_at(s, i)


def _qualified(s, i, names):
    """Scope parts up to the closing '@' -> (innermost first, anonymous namespace seen, index after)."""
    scope, anon = [], False
    while s[i] != '@':
        text, i = _fragment(s, i)
        if text is None:                       # back reference to an earlier name
            k = int(s[i - 1])
            if k < len(names):
                scope.append(names[k])
        elif text == '':
            anon = True
        else:
            scope.append(text)
            names.append(text)
    return scope, anon, i + 1


def _skip_qualified(s, i, depth):
    while s[i] != '@':
        i = _fragment(s, i, depth)[1]
    return i + 1


def _function_of_local(s, i):
    """The function of a local static from its decorated name at s[i] ('?Tick@Owner@@QAEXXZ',
    '??0Owner@@QAE@XZ', '??$Tmpl@H@@YAXXZ', ...) -> 'Owner::Tick', 'Owner::Owner', 'Tmpl';
    the leading identifier when the rest cannot be read; '' when there is none."""
    try:
        if s.startswith('??$', i):
            name, j = _fragment(s, i + 1)
            fmt = name
        elif s.startswith('??', i):
            code = s[i + 2:i + 4] if s[i + 2] == '_' else s[i + 2]
            if code not in _OPERATOR and code[0] == '_':
                raise ValueError                 # vector deleting destructor and friends
            fmt, j, name = _OPERATOR.get(code, 'operator'), i + 2 + len(code), ''
        else:
            name, j = _ident_at(s, i + 1)
            fmt = name
        scope, _, _ = _qualified(s, j, [name] if name else [])
        if '{c}' in fmt:
            if not scope:
                raise ValueError
            fmt = fmt.format(c=scope[0])
        return '::'.join(list(reversed(scope)) + [fmt])
    except (ValueError, IndexError):
        # '?Func', '??$Tmpl', '??0Class' (constructor); nothing for other operators ('??R<lambda_1>')
        m = re.match(r'\?(?:\?\$|\?[01])?([A-Za-z_]\w*)', s[i:])
        return m.group(1) if m else ''


def data_symbol(dec):
    """MSVC decorated C++ variable -> {'name', 'func', 'internal', 'local'} or None if dec is not
    one (functions, string literals, vftables, init guards, dynamic initializers).
    name: 'x', 'ns::x', 'A::x' or 'Tmpl::x' (template arguments dropped, as in the annotations);
    func: the enclosing function of a function-local static ('ShutdownStandardGamingPlatform' for
    ?Reenter@?1??ShutdownStandardGamingPlatform@@9@4EA, 'Owner::Owner' in a constructor), its
    leading identifier when the rest cannot be read, '' otherwise. Every local static is a
    variable here (local: True), even when func is ''. internal: local static or anonymous
    namespace (no linkage across files)."""
    if not dec.startswith('?'):
        return None
    try:
        name, i = _ident_at(dec, 1)
    except ValueError:
        return None
    m = _LOCAL_SCOPE.match(dec, i)
    if m:
        return {'name': name, 'func': _function_of_local(dec, m.end()), 'internal': True, 'local': True}
    try:
        scope, anon, i = _qualified(dec, i, [name])
    except (ValueError, IndexError):
        return None
    if dec[i:i + 1] not in ('0', '1', '2', '3', '4'):   # storage class of a variable
        return None
    return {'name': '::'.join(list(reversed(scope)) + [name]), 'func': '', 'internal': anon, 'local': False}


def same_function(a, b):
    """'Class::Method' vs 'Method': equal last components (full names when both are qualified)."""
    if not a or not b:
        return False
    if '::' in a and '::' in b:
        return a == b
    return a.split('::')[-1] == b.split('::')[-1]


# --- annotations ----------------------------------------------------------------------------------
_NOT_A_FUNCTION = {'if', 'while', 'for', 'switch', 'return', 'sizeof', 'catch', 'defined', 'decltype',
                   'alignof', 'static_assert', 'throw', 'typeid', '__pragma', '_Pragma'}
_CONTROL_LINE = re.compile(r'^(?:if|else|while|for|do|switch|case|default|return|try|catch)\b')


_OPERATOR_BEFORE_PAREN = re.compile(
    r'\b((?:[A-Za-z_]\w*(?:<[^()]*?>)?\s*::\s*)*)operator\s*'
    r'(\(\s*\)|\[\s*\]|(?:new|delete)\b(?:\s*\[\s*\])?|[^\s\w(]{1,3})\s*\(')


def _strip_template_head(s):
    """'template <class T> void F(T x)' -> 'void F(T x)' (unchanged when the head goes on past s)."""
    m = re.match(r'\s*template\s*<', s)
    if not m:
        return s
    depth = 0
    for k in range(m.end() - 1, len(s)):
        if s[k] == '<':
            depth += 1
        elif s[k] == '>':
            depth -= 1
            if depth == 0:
                return s[k + 1:].lstrip()
    return s


def _function_name(text):
    """Name of the function a signature declares: the first identifier before '(' that is not
    a keyword ('__declspec(naked) void F(int)' -> 'F', 'INT32 FAR PASCAL WndProc(...)' -> 'WndProc',
    'template <class T> void Tmpl(T x)' -> 'Tmpl'), or an operator ('Owner& Owner::operator=(...)'
    -> 'Owner::operator=', 'operator new'); template arguments of the scope are dropped
    ('Foo<T>::Get' -> 'Foo::Get'), as in data_symbol's names."""
    text = _strip_template_head(text)
    text = re.sub(r'__declspec\s*\((?:[^()]|\([^()]*\))*\)', ' ', text)
    text = re.sub(r'__attribute__\s*\(\((?:[^()]|\([^()]*\))*\)\)', ' ', text)
    found = None
    for m in IDENT_BEFORE_PAREN.finditer(text):
        if m.group(1).split('::')[-1] not in _NOT_A_FUNCTION:
            found = m
            break
    op = _OPERATOR_BEFORE_PAREN.search(text)
    if op and (found is None or op.start() <= found.start()):
        sym = re.sub(r'\s+', '', op.group(2))
        return _drop_templates(re.sub(r'\s+', '', op.group(1))) + 'operator' + (
            ' ' + sym if sym[:1].isalpha() else sym)
    return _drop_templates(found.group(1)) if found else ''


def _signature_after(lines, k):
    """The signature below a // FUNCTION annotation at line k (comments skipped, up to ')')."""
    parts = []
    for j in range(k + 1, min(k + 12, len(lines))):
        s = lines[j].strip()
        if not s or s.startswith(('//', '/*', '*')):
            if parts:
                break
            continue
        parts.append(s.split('//')[0].strip())
        joined = ' '.join(parts)
        if ')' in joined or '{' in joined or ';' in joined:
            break
    return ' '.join(parts)


def _enclosing_function(lines, i):
    """Function whose body holds line i (the annotation of a function-local static), or ''.
    The nearest // FUNCTION annotation above the function's header wins (its signature may span
    lines); otherwise the header line itself, skipping keywords ('if (', '__declspec(') and a
    template head on the same line ('template <class T> void Tmpl(T x)')."""
    header = None
    for j in range(i - 1, max(-1, i - 3000), -1):
        raw = lines[j]
        if not raw.strip() or raw[0] in ' \t':
            continue
        s = _strip_template_head(raw.strip()) or raw.strip()   # a bare 'template <..>' line stays
        if s.startswith(('//', '/*', '*', '#', '{')) or _CONTROL_LINE.match(s):
            continue   # comments, braces, preprocessor, unindented statements of the body
        if s.startswith('}') or s.endswith(';') or \
                re.match(r'^(?:namespace|class|struct|union|enum|extern|typedef|template)\b', s):
            return ''
        header = j
        break
    if header is None:
        return ''
    for k in range(header, max(-1, header - 12), -1):
        if FUNCTION_ANN.match(lines[k]):
            name = _function_name(_signature_after(lines, k))
            if name:
                return name
            break
        s = lines[k].strip()
        if k < header and (s.endswith(';') or s.endswith('}') or s.startswith('}')) and \
                not s.startswith(('//', '/*', '*')):
            break      # the end of the previous declaration: no annotation for this function
    return _function_name(lines[header].strip())


_NAMESPACE_HEAD = re.compile(r'\bnamespace(?:\s+([A-Za-z_]\w*))?\s*$')
_EXTERN_HEAD = re.compile(r'\bextern\s*""\s*$')                     # extern "C" { (literals blanked)
_CLASS_HEAD = re.compile(r'.*\b(?:class|struct|union)\b([^(){}=;]*)$', re.S)


def _masked_lines(lines):
    """The lines without comments, preprocessor directives and the contents of string and
    character literals ('"x{"' -> '""'): what is left to follow braces with."""
    out, in_block, in_pp = [], False, False
    for raw in lines:
        if not in_block and (in_pp or raw.lstrip().startswith('#')):
            in_pp = raw.rstrip().endswith('\\')
            out.append('')
            continue
        buf, k = [], 0
        while k < len(raw):
            if in_block:
                e = raw.find('*/', k)
                if e < 0:
                    break
                in_block, k = False, e + 2
                buf.append(' ')
            elif raw.startswith('//', k):
                break
            elif raw.startswith('/*', k):
                in_block, k = True, k + 2
                buf.append(' ')
            elif raw[k] in '"\'':
                q, e = raw[k], k + 1
                while e < len(raw) and raw[e] != q:
                    e += 2 if raw[e] == '\\' else 1
                buf.append(q + q)
                k = e + 1
            else:
                buf.append(raw[k])
                k += 1
        out.append(''.join(buf))
    return out


def _scopes(lines):
    """The braces open at the start of each line, outermost first: ('namespace', name; '' for an
    anonymous one), ('class', name) for a class, struct or union body, ('body', '') for anything
    else (a function body, an initializer, an enum, a block), ('extern', '') for extern "C" {.
    None for every line when the braces of the file do not balance (a preprocessor branch with
    braces of its own): then nothing is known."""
    stack, head, out, ok = [], [], [], True
    for line in _masked_lines(lines):
        out.append(tuple(stack))
        for ch in line + '\n':
            if ch == '{':
                h = ''.join(head)
                m = _NAMESPACE_HEAD.search(h)
                c = None if m or re.search(r'\benum\b', h) else _CLASS_HEAD.match(h)
                if m:
                    stack.append(('namespace', m.group(1) or ''))
                elif _EXTERN_HEAD.search(h):
                    stack.append(('extern', ''))
                elif c:
                    name = re.findall(r'[A-Za-z_]\w*', re.split(r'(?<!:):(?!:)', c.group(1))[0])
                    stack.append(('class', name[-1] if name else ''))
                else:
                    stack.append(('body', ''))
                head = []
            elif ch == '}':
                ok = ok and bool(stack)
                stack[-1:] = []
                head = []
            elif ch == ';':
                head = []
            else:
                head.append(ch)
    return out if ok and not stack else [None] * len(lines)


def _global_entry(lines, i, entry, scope=None):
    """Fill name/decl/func of a // GLOBAL annotation at line i. scope: _scopes() of that line.
    Inside a named namespace the name is qualified ('ns::g_x', as the DLL's decorated name
    reads); a declaration in a class body gets no name and 'in_class' (it is not the definition:
    the annotation belongs on 'int Owner::s_member;')."""
    # comment-only form: the variable comes from a system header (a GUID: IID_, CLSID_, GUID_)
    #   // GLOBAL: WIZ8 0x005ebb78
    #   // IID_IDirectDraw2
    # any other one-word comment in that shape is an error (empty name), not a variable name
    nxt = lines[i + 1].strip() if i + 1 < len(lines) else ''
    after = lines[i + 2].strip() if i + 2 < len(lines) else ''
    mm = re.match(r'^//\s*([A-Za-z_]\w*)\s*$', nxt)
    if mm and not ANY_ANN.match(nxt) and (not after or ANY_ANN.match(after)):
        name = mm.group(1) if GUID_NAME.match(mm.group(1)) else ''
        entry.update(text=nxt, decl='', name=name, func='', comment_only=True)
        return
    # the declaration: the following lines up to ';', '=' or '{' (it may span lines);
    # comments are skipped; another FUNCTION/GLOBAL/VTABLE annotation first means there is none
    parts, in_block = [], False
    for j in range(i + 1, min(i + 30, len(lines))):
        raw = lines[j]
        if not parts and not in_block and OTHER_ANN.match(raw):
            break
        s = raw.strip()
        if in_block:
            if '*/' not in s:
                continue
            in_block = False
            s = s.split('*/', 1)[1].strip()
        s = re.sub(r'/\*.*?\*/', ' ', s).strip()
        if '/*' in s:
            s, in_block = s.split('/*', 1)[0].strip(), True
        if s.startswith('//') or s.startswith('*'):
            s = ''
        s = s.split('//')[0].strip()
        if not s:
            continue
        parts.append(s)
        joined = ' '.join(parts)
        if _cut_top_level(joined) != joined or len(parts) >= 8:
            break
    decl = ' '.join(parts)
    entry['text'] = parts[0] if parts else ''
    entry['decl'] = decl
    entry['name'] = declarator_name(decl) if decl else ''
    indented = lines[i][:1] in (' ', '\t')
    entry['func'] = _enclosing_function(lines, i) if indented and re.search(r'\bstatic\b', decl) else ''
    if scope and not any(kind == 'body' for kind, _ in scope):
        classes = [n or '<anonymous>' for kind, n in scope if kind == 'class']
        spaces = [n for kind, n in scope if kind == 'namespace' and n]
        if classes:
            entry.update(name='', func='', in_class='::'.join(spaces + classes))
        elif spaces and entry['name']:
            entry['name'] = '::'.join(spaces + [entry['name']])


def scan_lines(lines, rel):
    """Annotations of one source file (list of lines) -> (functions, globals)."""
    funcs, globs, scopes = [], [], None
    for i, line in enumerate(lines):
        m = ANN.match(line)
        if not m:
            continue
        kind, addr = m.group(1), int(m.group(2), 16)
        entry = {'addr': addr, 'file': rel, 'line': i + 1}
        if kind == 'GLOBAL':
            if scopes is None:
                scopes = _scopes(lines)
            _global_entry(lines, i, entry, scopes[i])
            globs.append(entry)
            continue
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
            while '(' in text and ')' not in text and k + 1 < len(lines):
                k += 1
                text += ' ' + lines[k].strip()
            break
        entry['text'] = text
        mm = IDENT_BEFORE_PAREN.search(text)
        entry['name'] = mm.group(1) if mm else ''
        funcs.append(entry)
    return funcs, globs


def scan_annotations():
    """-> functions: list of dicts(addr, name, file, line, text);
    globals: dicts(addr, name, file, line, text, decl, func[, comment_only]).
    A global's func is the enclosing function of a function-local static."""
    funcs, globs = [], []
    for path in _source_files():
        try:
            lines = open(path, encoding='utf-8', errors='replace').read().split('\n')
        except OSError:
            continue
        f, g = scan_lines(lines, os.path.relpath(path, SRC))
        funcs += f
        globs += g
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


# --- self-test: one example per declaration form (build_hybrid.py runs it before every build) ----
_DECL_CASES = [
    ('int g_plain;', 'g_plain'),
    ('static BOOLEAN Reenter = FALSE;', 'Reenter'),
    ('unsigned char g_flag = 1; // comment', 'g_flag'),
    ('int g_table[16] = {0, 1, 2};', 'g_table'),
    ('char g_grid[4][8];', 'g_grid'),
    ('const char* const g_names[] = {"a", "b"};', 'g_names'),
    ('static srMeshModel::TriMesh* g_shadow_mesh;', 'g_shadow_mesh'),
    ('void (*g_fade_callback)(void);', 'g_fade_callback'),
    ('void (__cdecl *g_cdecl_cb)(int, char*);', 'g_cdecl_cb'),
    ('void (*g_automap_button_callbacks[16])(void) = {', 'g_automap_button_callbacks'),
    ('int (*g_row)[4];', 'g_row'),
    ('int (WINAPI *g_api)(HWND, int (*)(void));', 'g_api'),
    ('W8Vector<stLight*> g_environment_lights(5);', 'g_environment_lights'),
    ('static W8GrowableVector<srTextureIFace*> g_retained_textures(5);', 'g_retained_textures'),
    ('W8GrowableVector<srClipPlane::ClientType*> g_automap_layers;', 'g_automap_layers'),
    ('Foo g_by_pointer(&g_other);', 'g_by_pointer'),
    ('srVector2i g_offsets[5] = {{0, 0}, {8, 7}};', 'g_offsets'),
    ('Point g_braced{1, 2};', 'g_braced'),
    ('W8FadeCallback g_typedefd;', 'g_typedefd'),
    ('int Owner::s_member = 3;', 'Owner::s_member'),
    ('__declspec(selectany) int g_selectany = 1;', 'g_selectany'),
    ('static const char*', ''),    # incomplete: no name, never 'char'
    ('W8HashTable<unsigned int, int>* g_cell_index;', 'g_cell_index'),   # comma inside <>
    ('char* g_csv = "a, b";', 'g_csv'),                                  # comma inside a literal
    ("char g_sep = ',';", 'g_sep'),
    ('int g_shift = 1 << 2;', 'g_shift'),
    ('static float LIFT_TOP_Y = 5228.6f;', 'LIFT_TOP_Y'),                # caps, but a plain name
    ('static INT32 MAX_PARTY;', 'MAX_PARTY'),                            # caps after a caps type
    ('Foo BAR(5);', 'BAR'),
    ('extern "C" int g_c_linkage;', 'g_c_linkage'),
    ('struct W8Stats g_elaborated{1};', 'g_elaborated'),                 # not a type body
    ('Foo<(1 < 2)> g_cmp;', 'g_cmp'),                                    # comparisons in template arguments
    ('Foo<(1 > 0)> g_cmp2 = {};', 'g_cmp2'),
    ('void (*g_cb_tmpl)(W8Vector<int>*);', 'g_cb_tmpl'),
    # several declarators, a type defined in the declaration or a macro after the name: no
    # certain name, the build fails
    ('int g_a, g_b;', ''),
    ('static INT32 giX, giY = 0;', ''),
    ('int g_one = 1, g_two = 2;', ''),
    ('Point g_p{1, 2}, g_q;', ''),
    ('Foo<(1 > 0)> g_x, g_y;', ''),
    ('int g_x WIZ8_ALIGN(16);', ''),
    ('int g_y __attribute__((aligned(16)));', ''),
    ('struct W8Stats { int a; } g_stats;', ''),     # not 'W8Stats'
    ('enum Mode { MODE_A } g_mode;', ''),            # not 'Mode'
    ('union U { int a; float b; } g_u;', ''),        # not 'U'
    ('class Derived : public Base { int a; } g_derived;', ''),
    ('int g_x WIZ8_ALIGNED;', ''),                   # not 'WIZ8_ALIGNED'
    ('int g_x ALIGN(16);', ''),                      # not 'ALIGN'
    ('W8Stats g_x ALIGNED;', ''),
]
_FUNCTION_NAME_CASES = [
    ('__declspec(naked) void NakedHelper(void)', 'NakedHelper'),
    ('INT32 FAR PASCAL WindowProcedure(HWND hWindow, UINT16 Message,', 'WindowProcedure'),
    ('Owner& Owner::operator=(const Owner& o)', 'Owner::operator='),
    ('bool Owner::operator()(int a) const', 'Owner::operator()'),
    ('Vec Vec::operator + (const Vec& v) const', 'Vec::operator+'),
    ('void* Pool::operator new[](size_t n)', 'Pool::operator new[]'),
    ('template <class T> void Tmpl(T x)', 'Tmpl'),
    ('template <class T> int W8Vector<T>::Find(T x)', 'W8Vector::Find'),
    ('if (x) {', ''),
]
_CONST_CASES = [
    ('const float g_scale = 1.0f;', True),
    ('static const float NAVIGATOR_MAXIMUM_DROP = 1500.0f;', True),
    ('int const g_ic = 1;', True),
    ('const char* const g_names[] = {"a"};', True),
    ('void (* const g_fixed_cb)(void) = f;', True),
    ('constexpr int g_ce = 2;', True),
    ('const char* g_text = "x";', False),    # a pointer to const: the pointer itself is a variable
    ('int g_plain;', False),
    ('void (*g_cb)(void);', False),
    ('static float LIFT_TOP_Y = 5228.6f;', False),
]
_UNDNAME_CASES = [
    ('void (__cdecl* g_message_box_callback)(void)', 'g_message_box_callback'),
    ('void (__cdecl** g_automap_button_callbacks)(void)', 'g_automap_button_callbacks'),
    ('class W8Vector<class stLight *> g_environment_lights', 'g_environment_lights'),
    ('public: static int Owner::s_member', 'Owner::s_member'),
    ('unsigned char * g_bytes', 'g_bytes'),
]
_DATA_SYMBOL_CASES = [
    ('?g_fade_callback@@3P6AXXZA', ('g_fade_callback', '', False)),
    ('?g_automap_button_callbacks@@3PAP6AXXZA', ('g_automap_button_callbacks', '', False)),
    ('?g_environment_lights@@3V?$W8Vector@PAVstLight@@@@A', ('g_environment_lights', '', False)),
    ('?g_registered_navigators@?A0x4f50d3b4@@3V?$W8GrowableVector@PAVW8Navigator@@@@A',
     ('g_registered_navigators', '', True)),
    ('?Reenter@?1??ShutdownStandardGamingPlatform@@9@4EA', ('Reenter', 'ShutdownStandardGamingPlatform', True)),
    ('?fResizing@?1??MouseHandler@@YGJHIJ@Z@4EA', ('fResizing', 'MouseHandler', True)),
    ('?fRestore@?1??WindowProcedure@@9@16@4HA', ('fRestore', 'WindowProcedure', True)),
    ('?s_count@?1??Tick@Owner@@QAEXXZ@4HA', ('s_count', 'Owner::Tick', True)),
    ('?s_member@Owner@@2HA', ('Owner::s_member', '', False)),
    ('?g_x@ns@@3HA', ('ns::g_x', '', False)),
    # local statics in a constructor, destructor, operator, template function, anonymous
    # namespace, a function the parser cannot read (still a local static, func '')
    ('?x@?1???0Owner@@QAE@XZ@4HA', ('x', 'Owner::Owner', True)),
    ('?x@?1???1Owner@@QAE@XZ@4HA', ('x', 'Owner::~Owner', True)),
    ('?x@?1???4Owner@@QAEAAV0@ABV0@@Z@4HA', ('x', 'Owner::operator=', True)),
    ('?x@?1???$Tmpl@H@@YAXXZ@4HA', ('x', 'Tmpl', True)),
    ('?x@?1???$Get@PAVstLight@@@Owner@@QAEHXZ@4HA', ('x', 'Owner::Get', True)),
    ('?x@?1??Func@?A0x12345678@@YAXXZ@4HA', ('x', 'Func', True)),
    ('?x@?BA@??Func@@YAXXZ@4HA', ('x', 'Func', True)),
    ('?x@?1??<lambda_0>@@YAXXZ@4HA', ('x', '', True)),
    ('?done@?1???R<lambda_6e4b09c4>@@QBE@XZ@4_NA', ('done', '', True)),
    # the other operators, spelled as _function_name reads them from the header
    ('?x@?1???HVec@@QBE?AV0@ABV0@@Z@4HA', ('x', 'Vec::operator+', True)),
    ('?x@?1???ROwner@@QBE_NH@Z@4HA', ('x', 'Owner::operator()', True)),
    ('?x@?1???_UPool@@SAPAXI@Z@4HA', ('x', 'Pool::operator new[]', True)),
    ('?x@?1???_EOwner@@UAEPAXI@Z@4HA', ('x', '', True)),            # vector deleting destructor
    # static members of class templates (template arguments dropped, as in the annotations)
    ('?s@?$Tmpl@H@@2HA', ('Tmpl::s', '', False)),
    ('?s@?$W8Vector@PAVstLight@@@@2HA', ('W8Vector::s', '', False)),
    ('?s@?$Pair@H$0BA@@ns@@2HA', ('ns::Pair::s', '', False)),
    ('?s@?$Cb@P6AXH@Z@@2HA', ('Cb::s', '', False)),
    ('?BeginScreenFade@@YAXP6AXXZ@Z', None),                       # a function
    ('?g_environment_lights$initializer$@@3P6AXXZA', None),         # dynamic initializer pointer
    ('?$S1@?1??Tick@@YAXXZ@4IA', None),                             # init guard of a local static
    ('??_C@_05ABCDEF@hello?$AA@', None),                            # string literal
    ('_g_c_name', None),                                            # C name: handled by the caller
]
_SCAN_SOURCE = '''\
// GLOBAL: WIZ8 0x00600000
void (*g_fade_callback)(void);
// GLOBAL: WIZ8 0x00600004
/* a block comment
   over two lines */
W8Vector<stLight*>
    g_split_over_lines(5);
// GLOBAL: WIZ8 0x00600010
// IID_IDirectDraw2

// GLOBAL: WIZ8 0x00600020
// IID_IDirectDrawSurface2

// FUNCTION: WIZ8 0x00401000
INT32 FAR PASCAL WindowProcedure(HWND hWindow, UINT16 Message,
                                 WPARAM wParam, LPARAM lParam)
{
    // GLOBAL: WIZ8 0x00600030
    static int fRestore = FALSE;
    return 0;
}

void ShutdownStandardGamingPlatform(void)
{
    if (x) {
        // GLOBAL: WIZ8 0x00600034
        static BOOLEAN Reenter = FALSE;
    }
}
// GLOBAL: WIZ8 0x00600040
// FUNCTION: WIZ8 0x00402000
void NoDeclarationAbove(void)
{
}
// GLOBAL: WIZ8 0x00600050
// STRING: WIZ8 0x00600060
char* g_with_string = "Data\\\\Dialogs\\\\popup.sti";
// GLOBAL: WIZ8 0x00600070
// TODO

// FUNCTION: WIZ8 0x00403000
__declspec(naked) void NakedHelper(void)
{
    // GLOBAL: WIZ8 0x00600080
    static int s_naked;
}
// FUNCTION: WIZ8 0x00404000
static void SplitSignature(int a,
int b)
{
    // GLOBAL: WIZ8 0x00600090
    static int s_split;
}
void BadIndent(void)
{
if (x) {
    // GLOBAL: WIZ8 0x006000a0
    static int s_bad;
}
}
// GLOBAL: WIZ8 0x006000b0
static INT32 giX,
             giY = 0;
namespace ns {
// GLOBAL: WIZ8 0x006000c0
int g_in_ns;
namespace {
// GLOBAL: WIZ8 0x006000c4
int g_in_anon;
}
}
class Owner
{
public:
    // GLOBAL: WIZ8 0x006000d0
    static int s_member;
    Owner& operator=(const Owner& o);
    const char* Name() { return "}"; }
};
// GLOBAL: WIZ8 0x006000d8
int Owner::s_member;
Owner& Owner::operator=(const Owner& o)
{
    // GLOBAL: WIZ8 0x006000e0
    static int s_op;
    return *this;
}
template <class T> void Tmpl(T x)
{
    // GLOBAL: WIZ8 0x006000e4
    static int s_tmpl;
}
extern "C" {
// GLOBAL: WIZ8 0x006000e8
int g_in_extern_c;
}
'''
_SCAN_EXPECT = [
    (0x600000, 'g_fade_callback', ''),
    (0x600004, 'g_split_over_lines', ''),
    (0x600010, 'IID_IDirectDraw2', ''),
    (0x600020, 'IID_IDirectDrawSurface2', ''),
    (0x600030, 'fRestore', 'WindowProcedure'),
    (0x600034, 'Reenter', 'ShutdownStandardGamingPlatform'),
    (0x600040, '', ''),          # an annotation with no declaration: empty name (a build error)
    (0x600050, 'g_with_string', ''),
    (0x600070, '', ''),          # comment-only form with a word that is not a GUID name: error
    (0x600080, 's_naked', 'NakedHelper'),          # not '__declspec'
    (0x600090, 's_split', 'SplitSignature'),       # from the // FUNCTION annotation's signature
    (0x6000a0, 's_bad', 'BadIndent'),              # not 'if'
    (0x6000b0, '', ''),          # two variables in one declaration: error
    (0x6000c0, 'ns::g_in_ns', ''),                 # as the DLL's ?g_in_ns@ns@@3HA reads
    (0x6000c4, 'ns::g_in_anon', ''),               # the anonymous namespace has no name
    (0x6000d0, '', ''),          # the in-class declaration: error (in_class), not 's_member'
    (0x6000d8, 'Owner::s_member', ''),             # its definition: here the annotation belongs
    (0x6000e0, 's_op', 'Owner::operator='),
    (0x6000e4, 's_tmpl', 'Tmpl'),                  # the template head on the header's line
    (0x6000e8, 'g_in_extern_c', ''),
]
# a preprocessor branch with braces of its own: the scopes of the file are unknown
_UNBALANCED_SOURCE = ['#if A', 'void F(int a) {', '#else', 'void F() {', '#endif', '}', '// GLOBAL: WIZ8 0x00600000']


def selftest():
    """-> list of failure strings (empty: all good)."""
    bad = []
    for decl, want in _DECL_CASES:
        got = declarator_name(decl)
        if got != want:
            bad.append('declarator_name(%r) = %r, want %r' % (decl, got, want))
    for decl, want in _CONST_CASES:
        got = is_const_object(decl)
        if got != want:
            bad.append('is_const_object(%r) = %r, want %r' % (decl, got, want))
    for text, want in _UNDNAME_CASES:
        got = name_from_undecorated(text)
        if got != want:
            bad.append('name_from_undecorated(%r) = %r, want %r' % (text, got, want))
    for text, want in _FUNCTION_NAME_CASES:
        got = _function_name(text)
        if got != want:
            bad.append('_function_name(%r) = %r, want %r' % (text, got, want))
    for dec, want in _DATA_SYMBOL_CASES:
        d = data_symbol(dec)
        got = (d['name'], d['func'], d['internal']) if d else None
        if got != want:
            bad.append('data_symbol(%r) = %r, want %r' % (dec, got, want))
        elif d and d['local'] != bool(_LOCAL_SCOPE.match(dec, dec.index('@') + 1)):
            bad.append('data_symbol(%r): local = %r' % (dec, d['local']))
    _, globs = scan_lines(_SCAN_SOURCE.split('\n'), 'selftest.cpp')
    got = [(g['addr'], g['name'], g['func']) for g in globs]
    if got != _SCAN_EXPECT:
        bad.append('scan_lines: %r, want %r' % (got, _SCAN_EXPECT))
    in_class = [(g['addr'], g['in_class']) for g in globs if 'in_class' in g]
    if in_class != [(0x6000d0, 'Owner')]:
        bad.append('scan_lines: in-class declarations %r, want [(0x6000d0, \'Owner\')]' % in_class)
    if _scopes(_UNBALANCED_SOURCE)[-1] is not None:
        bad.append('_scopes: unbalanced braces not noticed')
    if not same_function('Owner::Tick', 'Tick') or same_function('A::Tick', 'B::Tick'):
        bad.append('same_function')
    return bad


if __name__ == '__main__':
    import sys
    if sys.argv[1:] == ['--selftest']:
        failures = selftest()
        print('\n'.join(failures) or 'symbols.py self-test: %d cases OK' % (
            len(_DECL_CASES) + len(_CONST_CASES) + len(_UNDNAME_CASES) + len(_FUNCTION_NAME_CASES) +
            len(_DATA_SYMBOL_CASES) + len(_SCAN_EXPECT) + 3))  # + in_class, _scopes, same_function
        sys.exit(1 if failures else 0)
    print('python -I symbols.py --selftest')
