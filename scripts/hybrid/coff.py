"""Minimal reading/editing of MSVC x86 COFF object files (regular and /bigobj) and
writing of a simple object file with stubs. For the hybrid: port functions that are not
transplanted become external references (their addresses come from the original)."""
import struct

IMAGE_SCN_LNK_COMDAT = 0x00001000
IMAGE_SCN_LNK_REMOVE = 0x00000800
CLASS_EXTERNAL = 2
CLASS_STATIC = 3
BIGOBJ_CLASSID = bytes.fromhex('c7a1bad1eebaa94baf20faf66aa4dcb8')


class Symbol:
    __slots__ = ('index', 'name', 'value', 'section', 'type', 'sclass', 'naux', 'offset')


class Section:
    __slots__ = ('number', 'name', 'size', 'ptr_raw', 'ptr_reloc', 'nreloc', 'chars', 'offset')


class Coff:
    def __init__(self, path):
        self.path = path
        self.data = bytearray(open(path, 'rb').read())
        d = self.data
        sig1, sig2 = struct.unpack_from('<HH', d, 0)
        if sig1 == 0 and sig2 == 0xFFFF:
            self.big = True
            (_, _, version, machine, _, classid, _, _, _, _, nsec, symptr, nsym) = struct.unpack_from(
                '<HHHHI16sIIIIIII', d, 0)
            hdr = 56
            self.symsize = 20
        else:
            self.big = False
            machine, nsec, _, symptr, nsym, opt, _ = struct.unpack_from('<HHIIIHH', d, 0)
            hdr = 20 + opt
            self.symsize = 18
        self.nsec, self.symptr, self.nsym = nsec, symptr, nsym
        self.strtab = symptr + nsym * self.symsize
        self.sections = []
        for i in range(nsec):
            off = hdr + i * 40
            s = Section()
            name, _, _, size, ptr_raw, ptr_reloc, _, nreloc, _, chars = struct.unpack_from(
                '<8sIIIIIIHHI', d, off)
            s.number = i + 1
            s.name = self._name(name)
            s.size, s.ptr_raw, s.ptr_reloc, s.nreloc, s.chars, s.offset = (
                size, ptr_raw, ptr_reloc, nreloc, chars, off)
            self.sections.append(s)
        self.symbols = []
        i = 0
        while i < nsym:
            off = symptr + i * self.symsize
            sym = Symbol()
            raw = d[off:off + 8]
            if self.big:
                value, section, typ, sclass, naux = struct.unpack_from('<IiHBB', d, off + 8)
            else:
                value, section, typ, sclass, naux = struct.unpack_from('<IhHBB', d, off + 8)
            sym.index, sym.value, sym.section, sym.type, sym.sclass, sym.naux, sym.offset = (
                i, value, section, typ, sclass, naux, off)
            sym.name = self._symname(raw)
            self.symbols.append(sym)
            i += 1 + naux

    def _name(self, raw8):
        if raw8[:1] == b'/':
            return self._str(int(raw8[1:].rstrip(b'\0') or b'0'))
        return raw8.rstrip(b'\0').decode('latin-1')

    def _symname(self, raw8):
        if raw8[:4] == b'\0\0\0\0':
            return self._str(struct.unpack('<I', raw8[4:8])[0])
        return raw8.rstrip(b'\0').decode('latin-1')

    def _str(self, off):
        p = self.strtab + off
        e = self.data.index(b'\0', p)
        return self.data[p:e].decode('latin-1')

    def relocations(self, sec):
        out = []
        for k in range(sec.nreloc):
            va, symidx, typ = struct.unpack_from('<IIH', self.data, sec.ptr_reloc + k * 10)
            out.append((va, symidx, typ))
        return out

    # --- editing ---
    def undefine(self, sym):
        """Make the symbol an external reference (its definition in the object file is dropped)."""
        d = self.data
        if self.big:
            struct.pack_into('<IiHBB', d, sym.offset + 8, 0, 0, sym.type, CLASS_EXTERNAL, sym.naux)
        else:
            struct.pack_into('<IhHBB', d, sym.offset + 8, 0, 0, sym.type, CLASS_EXTERNAL, sym.naux)
        sym.value, sym.section, sym.sclass = 0, 0, CLASS_EXTERNAL

    def _add_string(self, s):
        if not hasattr(self, '_extra'):
            self._extra = bytearray()
            self._strsize = struct.unpack_from('<I', self.data, self.strtab)[0]
            if self.strtab + self._strsize != len(self.data):
                raise ValueError('string table is not at the end of %s' % self.path)
        off = self._strsize + len(self._extra)
        self._extra += s.encode('latin-1') + b'\0'
        return off

    def _name_field(self, name):
        nb = name.encode('latin-1')
        if len(nb) <= 8:
            return nb.ljust(8, b'\0')
        return struct.pack('<II', 0, self._add_string(name))

    def rename(self, sym, newname, sclass=None):
        """New name (and optionally storage class) for a symbol; the string goes to the end of the string table."""
        self.data[sym.offset:sym.offset + 8] = self._name_field(newname)
        sym.name = newname
        if sclass is not None:
            self.data[sym.offset + (18 if self.big else 16)] = sclass
            sym.sclass = sclass

    def append_extern(self, name, typ=0):
        """New undefined external symbol; returns its index."""
        if not hasattr(self, '_newsyms'):
            self._newsyms = bytearray()
        idx = self.nsym + len(self._newsyms) // self.symsize
        raw = self._name_field(name)
        if self.big:
            self._newsyms += raw + struct.pack('<IiHBB', 0, 0, typ, CLASS_EXTERNAL, 0)
        else:
            self._newsyms += raw + struct.pack('<IhHBB', 0, 0, typ, CLASS_EXTERNAL, 0)
        return idx

    def redirect(self, old_index, new_index):
        """All relocations to symbol old_index -> to new_index."""
        n = 0
        for sec in self.sections:
            for k in range(sec.nreloc):
                off = sec.ptr_reloc + k * 10 + 4
                if struct.unpack_from('<I', self.data, off)[0] == old_index:
                    struct.pack_into('<I', self.data, off, new_index)
                    n += 1
        return n

    def remove_section(self, sec):
        sec.chars |= IMAGE_SCN_LNK_REMOVE
        struct.pack_into('<I', self.data, sec.offset + 36, sec.chars)

    def save(self, path=None):
        d = self.data
        newsyms = getattr(self, '_newsyms', bytearray())
        extra = getattr(self, '_extra', bytearray())
        strsize = getattr(self, '_strsize', struct.unpack_from('<I', d, self.strtab)[0])
        if newsyms or extra:
            nsym = self.nsym + len(newsyms) // self.symsize
            head = bytearray(d[:self.strtab])
            if self.big:
                struct.pack_into('<I', head, 52, nsym)
            else:
                struct.pack_into('<I', head, 12, nsym)
            strtab = bytearray(d[self.strtab:self.strtab + strsize]) + extra
            struct.pack_into('<I', strtab, 0, len(strtab))
            d = head + newsyms + strtab
        open(path or self.path, 'wb').write(d)


def write_bind_obj(path, stubs, absolutes, traps=()):
    """stubs: [(decorated, retail_va)] -> stubs push va; ret (each in its own COMDAT).
    absolutes: [(decorated, retail_va)] -> absolute symbols (original data).
    traps: [decorated] -> int3 (COMDAT; if a reference is live, the symbol stays in the map)."""
    sections = []  # (name, bytes)
    syms = []      # (name, value, section, type, sclass, aux_bytes or None)

    def comdat(code, name, typ=0x20):
        secnum = len(sections) + 1
        sections.append(code)
        aux = struct.pack('<IHHIHBBH', len(code), 0, 0, 0, 0, 2, 0, 0)[:18]  # selection ANY
        syms.append(('.text$w8', 0, secnum, 0, CLASS_STATIC, aux))
        syms.append((name, 0, secnum, typ, CLASS_EXTERNAL, None))

    for name, va in stubs:
        comdat(b'\x68' + struct.pack('<I', va) + b'\xc3', name)
    for name in traps:
        comdat(b'\xcc\xcc\xcc\xcc', name)
    for name, va in absolutes:
        syms.append((name, va, -1, 0, CLASS_EXTERNAL, None))

    strtab = bytearray(b'\0\0\0\0')
    symbytes = bytearray()
    nsym = 0
    for name, value, section, typ, sclass, aux in syms:
        nb = name.encode('latin-1')
        if len(nb) <= 8:
            rawname = nb.ljust(8, b'\0')
        else:
            rawname = b'\0\0\0\0' + struct.pack('<I', len(strtab))
            strtab += nb + b'\0'
        symbytes += rawname + struct.pack('<IhHBB', value, section, typ, sclass, 1 if aux else 0)
        nsym += 1
        if aux:
            symbytes += aux.ljust(18, b'\0')
            nsym += 1
    struct.pack_into('<I', strtab, 0, len(strtab))
    hdr = 20 + 40 * len(sections)
    raw = bytearray()
    headers = bytearray()
    for code in sections:
        headers += struct.pack('<8sIIIIIIHHI', b'.text$w8', 0, 0, len(code), hdr + len(raw), 0, 0,
                               0, 0, 0x60301020)  # CODE|EXEC|READ|ALIGN_4|COMDAT
        raw += code
    sym_off = hdr + len(raw)
    out = bytearray(struct.pack('<HHIIIHH', 0x14c, len(sections), 0, sym_off, nsym, 0, 0))
    out += headers + raw + symbytes + strtab
    open(path, 'wb').write(out)
