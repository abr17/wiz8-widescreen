"""API for test descriptions (scripts/w8diff/specs/*.py) and plan writing.

A spec is a module with a function cases(ctx) that creates cases through ctx:
    fn = ctx.fn(0x004ee4a0)                  # function by original address
    c = ctx.case('calcattacks.%d' % i, fn, conv='c', ret='v')
    c.set(ctx.party_char(0), blob)           # memory before the call (rolled back afterwards)
    c.arg(ctx.party_char(0))                 # arguments: int, Addr, F32(x), F64(x)
    c.cap(ctx.party_char(0), 0x1862, 'char') # what to compare after the call
An address (Addr) is computed separately in each exe: a global variable by name,
+/- offset, .deref() reads a dword at the address."""
import hashlib
import random
import struct

PROCS = ('retail', 'port')
CHAR_SIZE = 0x1862


class Addr:
    def __init__(self, base, ops=()):
        self.base = base  # ('sym', {'retail':..,'port':..}) | ('scratch', n)
        self.ops = tuple(ops)

    def __add__(self, k):
        k = int(k)
        if k == 0:
            return self
        return Addr(self.base, self.ops + ((('+', k) if k > 0 else ('-', -k)),))

    def __sub__(self, k):
        return self.__add__(-int(k))

    def deref(self):
        return Addr(self.base, self.ops + (('*', 0),))

    def render(self, proc):
        kind, val = self.base
        s = 'S%X' % val if kind == 'scratch' else '%X' % val[proc]
        for op, k in self.ops:
            s += '*' if op == '*' else '%s%X' % (op, k)
        return s

    def describe(self):
        kind, val = self.base
        s = 'S%d' % val if kind == 'scratch' else val.get('name', '?')
        for op, k in self.ops:
            s += '*' if op == '*' else '%s0x%x' % (op, k)
        return s


class F32:
    def __init__(self, x):
        self.x = float(x)

    def words(self):
        return [struct.unpack('<I', struct.pack('<f', self.x))[0]]


class F64:
    def __init__(self, x):
        self.x = float(x)

    def words(self):
        lo, hi = struct.unpack('<II', struct.pack('<d', self.x))
        return [lo, hi]


class Case:
    def __init__(self, cid, fn, conv, ret, out, spec):
        self.id = cid
        self.fn = fn
        self.conv = conv
        self.ret = ret
        self.out = out
        self.spec = spec
        self.args = []
        self.ops = []
        self.seed = int(hashlib.md5(cid.encode()).hexdigest()[:8], 16)
        self.info = {}

    # arguments
    def arg(self, v, label=None):
        self.args.append(v)
        if label:
            self.info.setdefault('args', []).append(label)
        return self

    def set(self, addr, data, label=None):
        self.ops.append(('set', addr, bytes(data), label))
        return self

    def setb(self, addr, data, label=None):
        """Like set, but the bytes are stored once in the plan header (blob) - for
        large repeated blocks such as characters from the corpus."""
        self.ops.append(('setb', addr, bytes(data), label))
        return self

    def setp(self, addr, value_addr):
        """Write the address value_addr (computed in
        each exe) into the dword at addr: e.g. substitute a struct from scratch into a global pointer."""
        self.ops.append(('setp', addr, value_addr, None))
        return self

    def fill(self, addr, length, byte=0):
        self.ops.append(('fill', addr, (int(length), int(byte)), None))
        return self

    def keep(self, addr, length):
        self.ops.append(('keep', addr, int(length), None))
        return self

    def cap(self, addr, length, name, ignore=(), floats=()):
        """ignore: offsets of dwords holding pointers (they differ between processes);
        floats: offsets of float fields (compared with a 4 ULP tolerance)."""
        self.ops.append(('cap', addr, int(length), {'name': name, 'ignore': sorted(set(ignore)),
                                                    'floats': sorted(set(floats))}))
        return self

    def dump(self, addr, length, name, ignore=(), floats=()):
        """All bytes after the call (no rollback: add keep to roll back)."""
        self.ops.append(('dump', addr, int(length), {'name': name, 'ignore': sorted(set(ignore)),
                                                     'floats': sorted(set(floats))}))
        return self

    def note(self, **kw):
        self.info.update(kw)
        return self

    def _arg_words(self, v, proc):
        if isinstance(v, Addr):
            return ['&' + v.render(proc)]
        if isinstance(v, (F32, F64)):
            return ['%X' % w for w in v.words()]
        if isinstance(v, bool):
            return ['%X' % int(v)]
        return ['%X' % (int(v) & 0xffffffff)]

    def render(self, proc, blobs=None):
        out = ['case %s' % self.id]
        # address -> bytes placed by setb: a full copy over such a block is written
        # only as the differing ranges (the plan becomes hundreds of times shorter).
        based = {}

        def prefix(s):
            i = s.rfind('*')
            return s[:i + 1] if i >= 0 else s.split('+')[0].split('-')[0]

        for kind, addr, payload, _ in self.ops:
            a = addr.render(proc)
            if kind == 'set' and a in based and len(based[a]) == len(payload):
                base = based[a]
                k, n = 0, len(payload)
                while k < n:
                    if payload[k] == base[k]:
                        k += 1
                        continue
                    s = k
                    while k < n and (payload[k] != base[k] or
                                     (k + 1 < n and payload[k + 1] != base[k + 1])):
                        k += 1
                    out.append('set %s %s' % ((addr + s).render(proc), payload[s:k].hex()))
                based[a] = payload
                continue
            if kind in ('set', 'fill', 'setp'):
                # another write through the same base pointer: the old copies
                # may have changed, so patches against them are no longer allowed
                p = prefix(a)
                based = {x: v for x, v in based.items() if prefix(x) != p}
            if kind == 'set':
                out.append('set %s %s' % (a, payload.hex()))
            elif kind == 'setb':
                out.append('setb %s %X' % (a, blobs[payload]))
                based[a] = payload
            elif kind == 'setp':
                out.append('setp %s %s' % (a, payload.render(proc)))
            elif kind == 'fill':
                out.append('fill %s %X %X' % (a, payload[0], payload[1]))
            elif kind == 'keep':
                out.append('keep %s %X' % (a, payload))
            elif kind == 'cap':
                out.append('cap %s %X' % (a, payload))
            elif kind == 'dump':
                out.append('dump %s %X' % (a, payload))
        if self.fn is not None:
            out.append('fn %s %X' % (self.conv, self.fn[proc]))
            for v in self.args:
                for w in self._arg_words(v, proc):
                    out.append('arg %s' % w)
            out.append('seed %X' % self.seed)
            if self.out:
                out.append('out %s' % self.out)
        out.append('end')
        return '\n'.join(out)

    def meta(self):
        caps, dumps = [], []
        for kind, addr, payload, extra in self.ops:
            if kind == 'cap':
                caps.append({'name': extra['name'], 'len': payload, 'ignore': extra['ignore'],
                             'floats': extra.get('floats', []), 'addr': addr.describe()})
            elif kind == 'dump':
                dumps.append({'name': extra['name'], 'len': payload,
                              'ignore': extra.get('ignore', []), 'floats': extra.get('floats', [])})
        return {'spec': self.spec, 'fn': self.fn['name'] if self.fn else None,
                'retail': '0x%08x' % self.fn['retail'] if self.fn else None,
                'ret': self.ret, 'caps': caps, 'dumps': dumps, 'info': self.info,
                'args': [a.describe() if isinstance(a, Addr) else
                         (a.x if isinstance(a, (F32, F64)) else a) for a in self.args]}


class Ctx:
    def __init__(self, syms, spec_name, corpus, scale=1.0):
        self.syms = syms
        self.spec = spec_name
        self.corpus = corpus  # list of (name, bytes) of W8Character characters
        self.scale = scale
        self.cases = []
        self.errors = []

    # --- symbols ---
    def fn(self, retail_addr, port_symbol=None):
        f = self.syms.function(retail_addr, port_symbol)
        return f

    def g(self, name, retail_addr=None):
        s = self.syms.global_(name, retail_addr)
        return Addr(('sym', s))

    def absolute(self, retail, port, name='abs'):
        return Addr(('sym', {'retail': retail, 'port': port, 'name': name}))

    def scratch(self, n):
        return Addr(('scratch', n))

    def char(self, slot):
        """W8Character g_status.buffers.Char[slot]: a heap array, pointer at
        offset 4 in g_status (include/wiz8/layouts/game_status.h)."""
        return (self.g('g_status') + 4).deref() + slot * CHAR_SIZE

    # --- characters ---
    def pick_char(self, rng):
        """A random character from the corpus (player saves) as a Blob."""
        name, data = self.corpus[rng.randrange(len(self.corpus))]
        return Blob(data), name

    def set_party(self, case, rng, slots=range(8)):
        """Put random corpus characters into the party slots (setb).
        Returns a list of (slot, Blob, name) - the Blob can be modified and written with set."""
        out = []
        for s in slots:
            blob, name = self.pick_char(rng)
            case.setb(self.char(s), bytes(blob))
            out.append((s, blob, name))
        return out

    # --- randomness ---
    def rng(self, *key):
        h = hashlib.md5(('%s|' % self.spec + '|'.join(map(str, key))).encode()).hexdigest()
        return random.Random(int(h[:16], 16))

    def n(self, count):
        return max(1, int(count * self.scale))

    def case(self, cid, fn, conv='c', ret='i', out=None):
        c = Case('%s.%s' % (self.spec, cid), fn, conv, ret, out, self.spec)
        self.cases.append(c)
        return c


class Blob(bytearray):
    """Mutable copy of a struct (e.g. a character) with field writes."""

    def u8(self, off, v):
        self[off] = int(v) & 0xff
        return self

    def u16(self, off, v):
        struct.pack_into('<H', self, off, int(v) & 0xffff)
        return self

    def u32(self, off, v):
        struct.pack_into('<I', self, off, int(v) & 0xffffffff)
        return self

    def f32(self, off, v):
        struct.pack_into('<f', self, off, float(v))
        return self

    def get_u32(self, off):
        return struct.unpack_from('<I', self, off)[0]

    def get_i32(self, off):
        return struct.unpack_from('<i', self, off)[0]

    def get_u16(self, off):
        return struct.unpack_from('<H', self, off)[0]


class Plan:
    MAX_BLOBS = 256

    def __init__(self):
        self.header = {p: [] for p in PROCS}
        self.cases = []

    def _blobs(self):
        ids = {}
        for c in self.cases:
            for kind, _, payload, _ in c.ops:
                if kind == 'setb' and payload not in ids:
                    ids[payload] = len(ids)
        if len(ids) > self.MAX_BLOBS:
            raise ValueError('too many distinct setb blobs: %d > %d' % (len(ids), self.MAX_BLOBS))
        return ids

    def write(self, proc, path):
        blobs = self._blobs()
        with open(path, 'w', encoding='ascii', newline='\n') as f:
            f.write('W8DIFF 1\n')
            for line in self.header[proc]:
                f.write(line + '\n')
            for data, i in blobs.items():
                f.write('blob %X %s\n' % (i, data.hex()))
            for c in self.cases:
                f.write(c.render(proc, blobs) + '\n')
