"""PC Item.cpp, lines 1-1400: item record helpers, equipment-slot rules, item names,
stack weight/value, use/activate checks, pairing rules and equal-kind stack merging.

Item records come from the real Items.dbs (read here from games\\reference PATCH.001 /
DATA.SLF, the same data both executables load), so ids, classes, name indices and
masks are realistic; edge values are produced by overriding single record fields for
the duration of one case (c.set on g_item_records[id] + offset, restored afterwards).
Characters are corpus characters put into party slots with setb (unmodified blobs),
followed by small c.set patches of the fields a case varies.

Tested (retail address, function, cases at scale 1):
  0x0051b8b0 GetItemUnitWeight              120
  0x0051b9e0 GetItemInHand                   40
  0x0051bfd0 GetItemStackWeight             150
  0x0051b840 GetItemStackValue              300
  0x0051c4e0 GetItemDefaultEquipSlot        200
  0x0051c8b0 GetPairedEquipSlot              40
  0x0055ce80 W8ItemVideoObjectCache::GetOrCreateVideoObject  60  (early returns only, see below)
  0x0051b5c0 FormatItemDisplayName          200
  0x0051b8e0 GetItemEquipClass               60
  0x0051b910 GetItemUnidentifiedNameIndex    60
  0x0051b940 ItemsShareEquipClass           120
  0x0051b990 ItemsShareUnidentifiedName     120
  0x0051d180 IsItemBoundToWearer            100
  0x0051cf80 GetItemEquipSlotMask           320
  0x0051cea0 CanEquipItemInSlot             300
  0x0051e980 GetItemMergeKind               150
  0x0051c8f0 CompatiblePartnerItems         400
  0x0051cc40 CanHoldItemsTogether           300
  0x0051cde0 HeldItemFitsPairedSlot         250
  0x0051d610 CanCharacterUseItem            400
  0x0051d7a0 AnyPartyMemberCanUseItem       200
  0x0051d800 CanCharacterActivateItem       300
  0x0051f8d0 AreAllHandSlotsEmpty            80
  0x0051c850 GetItemEquipSlotGroup          150
  0x0051b7b0 GetItemDisplayName             150
  0x0051cce0 ItemHasSingledOutGenericName   120
  0x0051cdb0 ItemUsesShots                   80
  0x0051dcb0 GetItemSpellPresentation       150
  0x0051d1c0 CanUnequipSlotItem             200
  0x0051f2b0 CanItemLeaveItsSlot            150
  0x0051f2f0 MergeItems                     150  (equal-kind stacking path only, see below)
  total 5420

Partly tested:
  0x0055ce80 GetOrCreateVideoObject - only the cached-entry / full-cache / 1000-limit
             returns on a cache built in scratch; the load path opens Data\\Items\\*.sti.
  0x0051f2f0 MergeItems - only held and target of the same kind, both identified, kind
             that no recipe combines with itself (excludes 0 and 113): exercises the
             recipe scan + MergeItemStacks/NormalizeItemStack + emptying the held item
             (cursor kept at W8_CURSOR_NONE so no cursor graphics are touched). The recipe
             path calls SetItemCursor (loads the item image), RefreshAfterItemRecordChange
             (derived stats rebuild), QueueCharacterEvent (sound) and
             PracticeCharacterSkill, and every failure path opens ShowCampNoticeLine.

Skipped:
  0x0055cdb0 W8ItemVideoObjectEntry::W8ItemVideoObjectEntry - not in port map (inlined);
             trivial constructor.
  0x0055cdc0 W8ItemVideoObjectCache::Initialize - not in port map; allocates the cache
             with operator new (heap object creation).
  0x0055ce40 W8ItemVideoObjectCache::Clear - not in port map; frees the cache.
  0x0051dde0 UseItem - posts character notices, casts the item's spell (CastItemSpell),
             removes items, queues character events, aims targets and dispatches the
             world-cursor command: UI/world side effects that cannot be rolled back.
"""
import os
import struct

CHAR_SIZE = 0x1862
REC_SIZE = 0x10d           # W8ItemDatabaseRecord
ITEM_SIZE = 0xc            # W8ItemInstance
SPELL_COUNT = 150          # SpellTables.dbs record count (g_spell_records)

# W8Character (scripts/w8diff/layout.ps1, wiz8/layouts/character.h)
C_PROF = 0x69              # W8Profession iProfession
C_RACE = 0x71              # W8Race iRace
C_GENDER = 0x75            # W8Gender gender
C_PLEVEL = 0x8d            # int profession_levels[15]
C_ATTR = 0xe5              # W8CharacterAttribute[7], step 0x14, effective at +4
ATTR_STEP = 0x14
C_SKILL = 0x19d            # W8CharacterSkill[0x29], step 0x26, level at +6
SKILL_STEP = 0x26
C_COND = 0xa01             # unsigned uiCondition[20]
COND_DEAD = 18
C_HIGHEST = 0xb01          # highest_condition
C_HP = 0xb11               # hp_current
C_LEARNED = 0xbcd          # int spell_learned[136] (followed by skill_unlocks[0x25])
C_EQUIP = 0xf5d            # W8ItemInstance EquippedItem[12]
C_PACK = 0x1029            # W8ItemInstance backpack[8]

# W8ItemDatabaseRecord (wiz8/layouts/item_tables.h)
R_CLASS = 0x3e
R_UNI = 0x3f               # unsigned short unidentified_name_index
R_FLAGS = 0x41
R_CAT = 0x42
R_WSKILL = 0x46
R_RANGE = 0x47
R_SPELL = 0x63
R_QKIND = 0x66
R_QMAX = 0x6b
R_PROF = 0x76              # unsigned short profession_mask
R_RACE = 0x78              # unsigned int race_mask
R_GENDER = 0x7c
R_AREQ = 0x7d              # W8ItemRequirement[2] {stat_id, minimum}
R_SREQ = 0x81
R_VALUE = 0x86             # unsigned int
R_WEIGHT = 0x8a            # unsigned short
R_BINDS = 0x8c
R_MCA = 0xb9
R_MCB = 0xbd

# W8GlobalStatus (wiz8/layouts/game_status.h)
S_XCHAR = 0x8              # W8PartySlotRow* XChar (0x106 each, fOccupied at +0)
XCHAR_SIZE = 0x106
S_STARTED = 0xc            # bool game_started
S_POOL = 0x21              # W8ItemInstance party_item_pool[500]
S_POOL_COUNT = 0x1791
S_CURSOR = 0x235a          # bool item_in_cursor, immediately followed by item_in_hand
S_HAND = 0x235b

# W8XStatus (wiz8/xstatus.h)
X_CURSOR = 0x923           # iCurrentCursor, current_cursor_frame, current_cursor_time
X_HELD = 0xa08             # held_item_source (int), held_item_origin (u8), held_item_slot (u16)

NAME_BUFFER_LEN = 84       # g_item_display_name_buffer: wchar_t[42]

WEIGHTS = [0, 1, 2, 10, 0x7fff, 0x8000, 0x8001, 0xfffe, 0xffff]
VALUES = [0, 1, 2, 24, 25, 26, 49, 50, 99, 100, 250000, 0x0a3d70a3, 0x0a3d70a4, 0x0ccccccc,
          0x147ae147, 0x7fffffff, 0x80000000, 0x80000001, 0xfffffff0, 0xffffffff]
STACKS = [0, 1, 2, 3, 9, 10, 24, 25, 26, 99, 100, 101, 127, 128, 254, 255]


# --------------------------------------------------------------------------- data

def _slf_read(path, suffix):
    """One file out of a Sir-Tech .SLF library (format as scripts/tools/slf_extract.py)."""
    with open(path, 'rb') as f:
        head = f.read(532)
        entries = struct.unpack_from('<i', head, 512)[0]
        f.seek(0, 2)
        size = f.tell()
        f.seek(size - entries * 280)
        table = f.read(entries * 280)
        for i in range(entries):
            row = table[i * 280:(i + 1) * 280]
            name = row[:256].split(b'\0')[0].decode('latin1').lower()
            off, length, state = struct.unpack_from('<IIB', row, 256)
            if state == 0 and name.endswith(suffix):
                f.seek(off)
                return f.read(length)
    return None


def _load_items():
    root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
    for game in ('reference', 'work'):
        for rel in (('Patches', 'PATCH.001'), ('Data', 'DATA.SLF')):
            path = os.path.join(root, 'games', game, *rel)
            if os.path.exists(path):
                data = _slf_read(path, 'databases\\items.dbs')
                if data:
                    return _parse_items(data)
    raise RuntimeError('Items.dbs not found under games\\reference or games\\work')


def _parse_items(data):
    count = struct.unpack_from('<I', data, 0)[0]
    out = []
    for i in range(count):
        b = data[4 + i * REC_SIZE:4 + (i + 1) * REC_SIZE]
        out.append({
            'id': i, 'cls': b[R_CLASS], 'uni': struct.unpack_from('<H', b, R_UNI)[0],
            'flags': b[R_FLAGS], 'cat': b[R_CAT], 'wskill': struct.unpack_from('<b', b, R_WSKILL)[0],
            'rng': b[R_RANGE], 'spell': b[R_SPELL], 'qk': b[R_QKIND], 'qmax': b[R_QMAX],
            'prof': struct.unpack_from('<H', b, R_PROF)[0], 'race': struct.unpack_from('<I', b, R_RACE)[0],
            'gender': b[R_GENDER], 'areq': b[R_AREQ:R_AREQ + 4], 'sreq': b[R_SREQ:R_SREQ + 4],
            'binds': b[R_BINDS], 'mca': struct.unpack_from('<i', b, R_MCA)[0],
            'mcb': struct.unpack_from('<i', b, R_MCB)[0],
        })
    return out


def item(iid, stack=0, uses=0, ident=1, hint=0, used=0, announced=0, bound=0):
    """W8ItemInstance bytes."""
    return struct.pack('<iBBBBBBBB', iid, stack & 0xff, uses & 0xff, ident, hint, 0, used,
                       announced, bound)


def wstr(text):
    return text.encode('utf-16le') + b'\0\0'


class _Env:
    def __init__(self, ctx, db):
        self.ctx = ctx
        self.db = db
        self.n = len(db)
        self.rec0 = ctx.g('g_item_records').deref()
        self.status = ctx.g('g_status')
        self.xstatus = ctx.g('gXStatus')
        self.gen_names = ctx.g('g_generic_item_names')
        self.name_buffer = ctx.g('g_item_display_name_buffer')

        def ids(pred):
            return [it['id'] for it in db if pred(it)]

        self.by_class = {}
        for it in db:
            self.by_class.setdefault(it['cls'], []).append(it['id'])
        self.weapons = ids(lambda it: it['cls'] <= 3)
        self.melee = ids(lambda it: it['cls'] <= 2)
        self.two_handed = ids(lambda it: it['cls'] <= 3 and it['flags'] & 4)
        self.one_handed = ids(lambda it: it['cls'] <= 2 and not it['flags'] & 4)
        self.ranged = ids(lambda it: it['cls'] == 3)
        self.ammo = ids(lambda it: it['cls'] == 4)
        self.shields = ids(lambda it: it['cls'] == 5)
        self.armor = ids(lambda it: 6 <= it['cls'] <= 12)
        self.nonweapons = ids(lambda it: it['cls'] > 3)
        self.stackable = ids(lambda it: it['qk'] == 1)
        self.binds = ids(lambda it: it['binds'])
        self.casters = ids(lambda it: it['cat'] in (3, 6, 8))
        self.restricted = ids(lambda it: it['gender'] != 3 or it['areq'][0] != 0xff or
                              it['sreq'][0] != 0xff or it['prof'] not in (0x7fff, 0xffff))
        self.special_ranged = ids(lambda it: it['uni'] in (0xb, 0x25, 0xc, 0xd, 0x68, 0x6e, 0x72, 0x83))
        self.partners = ids(lambda it: it['uni'] in (0x16, 0x17, 0x53, 0x70, 0x71, 0x7e, 0x84, 0x8f, 0x92)
                            or (it['cls'] == 2 and it['uni'] == 0))
        self.merge_keys = ids(lambda it: it['uni'] in (114, 110, 104, 144, 145))
        self.singled = ids(lambda it: it['uni'] in (0xb, 0xc, 0xd, 0x25, 0x83))
        self.shots = ids(lambda it: it['qk'] in (3, 4))
        self_merging = {it['mca'] for it in db if it['mca'] == it['mcb']}
        bad = {0, 113} | self_merging
        self.merge_stack = [i for i in self.stackable if i not in bad]
        self.merge_other = ids(lambda it: it['qk'] != 1 and it['id'] not in bad)

    # addresses
    def rec(self, iid, off=0):
        return self.rec0 + (iid * REC_SIZE + off)

    def xrow(self, slot):
        return (self.status + S_XCHAR).deref() + slot * XCHAR_SIZE

    # record overrides (restored after the case)
    def rset8(self, c, iid, off, v):
        c.set(self.rec(iid, off), bytes([v & 0xff]))

    def rset16(self, c, iid, off, v):
        c.set(self.rec(iid, off), struct.pack('<H', v & 0xffff))

    def rset32(self, c, iid, off, v):
        c.set(self.rec(iid, off), struct.pack('<I', v & 0xffffffff))

    def pick(self, r):
        return r.randrange(self.n)

    def put_char(self, c, r, slot=None):
        if slot is None:
            slot = r.randrange(8)
        blob, name = self.ctx.pick_char(r)
        c.setb(self.ctx.char(slot), bytes(blob))
        return slot, blob, name

    def set_started(self, c, r):
        v = r.randrange(2)
        c.set(self.status + S_STARTED, bytes([v]))
        return v

    def generic_name(self, c, r, uni, scratch):
        """Control g_generic_item_names[uni]: force the lazy build (malloc + swprintf)
        or point it at a known string in scratch."""
        if r.random() < 0.5:
            c.set(self.gen_names + uni * 4, b'\0\0\0\0')
            return 'build'
        alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 -\'()%'
        n = r.choice([0, 1, 5, 12, 20, 30, 33, 34, r.randrange(35)])
        text = ''.join(r.choice(alphabet) for _ in range(n))
        c.set(scratch, wstr(text))
        c.setp(self.gen_names + uni * 4, scratch)
        return 'cached'


# --------------------------------------------------------------------------- small getters

def t_unit_weight(ctx, E):
    f = ctx.fn(0x0051b8b0)  # unsigned GetItemUnitWeight(const W8ItemInstance*)
    s0 = ctx.scratch(0)
    for i in range(ctx.n(120)):
        r = ctx.rng('unitweight', i)
        c = ctx.case('unitweight.%d' % i, f, conv='c', ret='i')
        if i % 25 == 0:
            c.arg(0)
            c.note(item='null')
            continue
        iid = E.pick(r)
        c.set(s0, item(iid, stack=r.choice(STACKS)))
        if r.random() < 0.4:
            w = r.choice(WEIGHTS + [r.randrange(0x10000)])
            E.rset16(c, iid, R_WEIGHT, w)
            c.note(weight=w)
        c.arg(s0)
        c.note(item=iid)


def t_item_in_hand(ctx, E):
    f = ctx.fn(0x0051b9e0)  # int GetItemInHand(void)
    for i in range(ctx.n(40)):
        r = ctx.rng('iteminhand', i)
        c = ctx.case('iteminhand.%d' % i, f, conv='c', ret='i')
        flag = i % 2
        iid = r.choice([-1, 0, 1, E.pick(r), E.pick(r), E.n - 1, 0x7fffffff, -0x80000000, -2])
        c.set(E.status + S_CURSOR, bytes([flag]) + item(iid, stack=r.randrange(256)))
        c.note(in_cursor=flag, item=iid)


def t_stack_weight(ctx, E):
    f = ctx.fn(0x0051bfd0)  # unsigned GetItemStackWeight(const W8ItemInstance*)
    s0 = ctx.scratch(0)
    for i in range(ctx.n(150)):
        r = ctx.rng('stackweight', i)
        c = ctx.case('stackweight.%d' % i, f, conv='c', ret='i')
        iid = -1 if r.random() < 0.12 else E.pick(r)
        stack = r.choice(STACKS + [r.randrange(256)])
        c.set(s0, item(iid, stack=stack, uses=r.choice([0, r.randrange(256)])))
        if iid >= 0 and r.random() < 0.4:
            w = r.choice(WEIGHTS + [r.randrange(0x10000)])
            E.rset16(c, iid, R_WEIGHT, w)
            c.note(weight=w)
        c.arg(s0)
        c.note(item=iid, stack=stack)


def t_stack_value(ctx, E):
    f = ctx.fn(0x0051b840)  # unsigned GetItemStackValue(const W8ItemInstance*)
    s0 = ctx.scratch(0)
    for i in range(ctx.n(300)):
        r = ctx.rng('stackvalue', i)
        c = ctx.case('stackvalue.%d' % i, f, conv='c', ret='i')
        p = r.random()
        if p < 0.3:
            iid = r.choice(E.ammo)
        elif p < 0.6:
            iid = r.choice(E.stackable)
        else:
            iid = E.pick(r)
        stack = r.choice(STACKS + [r.randrange(256)])
        c.set(s0, item(iid, stack=stack, uses=r.choice([0, r.randrange(256)])))
        if r.random() < 0.35:
            cls = r.choice([4, 4, 3, 5, 0, 16, 25, 0xff])
            E.rset8(c, iid, R_CLASS, cls)
            c.note(cls=cls)
        if r.random() < 0.35:
            qk = r.choice([0, 1, 1, 2, 3, 4, 5, 0xff])
            E.rset8(c, iid, R_QKIND, qk)
            c.note(qk=qk)
        if r.random() < 0.5:
            v = r.choice(VALUES + [r.getrandbits(32), r.randrange(100000)])
            E.rset32(c, iid, R_VALUE, v)
            c.note(value=v)
        c.arg(s0)
        c.note(item=iid, stack=stack)


def t_default_slot(ctx, E, name, addr, count):
    f = ctx.fn(addr)  # W8EquipSlot GetItemDefaultEquipSlot(int) / group variant
    classes = sorted(E.by_class)
    for i in range(ctx.n(count)):
        r = ctx.rng(name, i)
        c = ctx.case('%s.%d' % (name, i), f, conv='c', ret='i')
        started = E.set_started(c, r)
        if r.random() < 0.6:
            cls = r.choice(classes)
            iid = r.choice(E.by_class[cls])
        else:
            iid = E.pick(r)
            cls = r.choice(list(range(32)) + [0x40, 0x7f, 0x80, 0xfe, 0xff])
            E.rset8(c, iid, R_CLASS, cls)
        c.arg(iid)
        c.note(item=iid, cls=cls, game_started=started)


def t_paired_slot(ctx, E):
    f = ctx.fn(0x0051c8b0)  # W8EquipSlot GetPairedEquipSlot(W8EquipSlot)
    values = list(range(-2, 14)) + [0x7fffffff, -0x80000000, 0x80000006, 0x80000007, 0x106, 0x107,
                                   0x108, 0x109, -6, -7, 0x10006, 0x10, 0xff, 0x100]
    r = ctx.rng('pairedslot', 'extra')
    while len(values) < ctx.n(40):
        values.append(r.getrandbits(32))
    for i, v in enumerate(values[:max(ctx.n(40), 1)]):
        c = ctx.case('pairedslot.%d' % i, f, conv='c', ret='i')
        c.arg(v)
        c.note(slot=v)


def t_video_object(ctx, E):
    f = ctx.fn(0x0055ce80)  # int W8ItemVideoObjectCache::GetOrCreateVideoObject(int), thiscall
    s0, s1 = ctx.scratch(0), ctx.scratch(1)
    for i in range(ctx.n(60)):
        r = ctx.rng('videoobject', i)
        c = ctx.case('videoobject.%d' % i, f, conv='t', ret='i')
        iid = E.pick(r)
        mode = i % 3
        vo = 0
        if mode == 0:      # cached entry: returned as is
            init = 1
            vo = r.choice([0, 1, 0x1ec, 0x1ec + r.randrange(1000), -1, 0x7fffffff, -0x80000000])
            cap = r.choice([0, 1, 5, 1000, r.randrange(2000)])
            loaded = r.choice([0, 1, cap, 1000, r.randrange(2000)])
        elif mode == 1:    # cache full
            init = 0
            cap = loaded = r.choice([0, 1, 5, 999, 1000, 1001, r.randrange(2000)])
        else:              # hard 1000-object limit
            init = 0
            loaded = 1000
            cap = r.choice([0, 1, 999, 1001, 5000, 0x7fffffff, -1])
        c.setp(s0, s1)
        c.set(s0 + 4, struct.pack('<ii', cap, loaded))
        c.set(s1 + iid * 8, struct.pack('<B3xi', init, vo))
        c.cap(s0, 12, 'cache', ignore=[0])
        c.cap(s1 + iid * 8, 8, 'entry')
        c.arg(s0)
        c.arg(iid)
        c.note(item=iid, initialized=init, capacity=cap, loaded=loaded)


# --------------------------------------------------------------------------- names

def t_format_name(ctx, E):
    f = ctx.fn(0x0051b5c0)  # wchar_t* FormatItemDisplayName(const W8ItemInstance*, bool)
    s0, s2 = ctx.scratch(0), ctx.scratch(2)
    for i in range(ctx.n(200)):
        r = ctx.rng('formatname', i)
        c = ctx.case('formatname.%d' % i, f, conv='c', ret='w', out='w')
        iid = E.pick(r)
        ident = 1 if r.random() < 0.45 else 0
        stack = r.choice(STACKS + [r.randrange(256)])
        incl = r.randrange(2)
        c.set(s0, item(iid, stack=stack, uses=r.randrange(256), ident=ident))
        mode = 'identified'
        if not ident:
            mode = E.generic_name(c, r, E.db[iid]['uni'], s2)
        c.fill(E.name_buffer, NAME_BUFFER_LEN, 0xcc)
        c.cap(E.name_buffer, NAME_BUFFER_LEN, 'name_buffer')
        c.arg(s0)
        c.arg(incl)
        c.note(item=iid, stack=stack, include_quantity=incl, name=mode)


def t_display_name(ctx, E):
    f = ctx.fn(0x0051b7b0)  # wchar_t* GetItemDisplayName(const W8ItemInstance*)
    s0, s2 = ctx.scratch(0), ctx.scratch(2)
    for i in range(ctx.n(150)):
        r = ctx.rng('displayname', i)
        c = ctx.case('displayname.%d' % i, f, conv='c', ret='w', out='w')
        iid = E.pick(r)
        ident = 1 if r.random() < 0.4 else 0
        c.set(s0, item(iid, stack=r.randrange(256), ident=ident))
        mode = 'identified'
        if not ident:
            mode = E.generic_name(c, r, E.db[iid]['uni'], s2)
        c.arg(s0)
        c.note(item=iid, name=mode)


def t_equip_class(ctx, E):
    f = ctx.fn(0x0051b8e0)  # unsigned char GetItemEquipClass(const W8ItemInstance*)
    s0 = ctx.scratch(0)
    for i in range(ctx.n(60)):
        r = ctx.rng('equipclass', i)
        c = ctx.case('equipclass.%d' % i, f, conv='c', ret='u8')
        if i % 12 == 0:
            c.arg(0)
            c.note(item='null')
            continue
        iid = E.pick(r)
        c.set(s0, item(iid))
        if r.random() < 0.3:
            E.rset8(c, iid, R_CLASS, r.choice([0, 0x7f, 0x80, 0xff, r.randrange(256)]))
        c.arg(s0)
        c.note(item=iid)


def t_uni_index(ctx, E):
    f = ctx.fn(0x0051b910)  # unsigned short GetItemUnidentifiedNameIndex(const W8ItemInstance*)
    s0 = ctx.scratch(0)
    for i in range(ctx.n(60)):
        r = ctx.rng('uniindex', i)
        c = ctx.case('uniindex.%d' % i, f, conv='c', ret='u16')
        if i % 12 == 0:
            c.arg(0)
            c.note(item='null')
            continue
        iid = E.pick(r)
        c.set(s0, item(iid))
        if r.random() < 0.3:
            E.rset16(c, iid, R_UNI, r.choice([0, 0x7fff, 0x8000, 0xffff, 0x100, r.randrange(0x10000)]))
        c.arg(s0)
        c.note(item=iid)


def t_share(ctx, E, name, addr, field_off, width):
    f = ctx.fn(addr)  # bool ItemsShare...(const W8ItemInstance*, const W8ItemInstance*)
    s0 = ctx.scratch(0)
    a_addr, b_addr = s0, s0 + 0x10
    key = 'cls' if width == 1 else 'uni'
    for i in range(ctx.n(120)):
        r = ctx.rng(name, i)
        c = ctx.case('%s.%d' % (name, i), f, conv='c', ret='b')
        a = E.pick(r)
        p = r.random()
        if p < 0.35:   # different item, same field value
            same = [it['id'] for it in E.db if it[key] == E.db[a][key]]
            b = r.choice(same)
        else:
            b = E.pick(r)
        c.set(a_addr, item(a))
        c.set(b_addr, item(b))
        if r.random() < 0.25:
            if width == 1:
                v = r.choice([0, 0xff, 0x80, E.db[b]['cls']])
                E.rset8(c, a, field_off, v)
            else:
                base = E.db[b]['uni']
                v = r.choice([base, base ^ 0x100, base ^ 0x8000, base + 1, 0, 0xffff])
                E.rset16(c, a, field_off, v)
        nulls = r.random()
        pa, pb = a_addr, b_addr
        if nulls < 0.05:
            pa = 0
        elif nulls < 0.1:
            pb = 0
        elif nulls < 0.12:
            pa = pb = 0
        c.arg(pa)
        c.arg(pb)
        c.note(first=a if pa else 'null', second=b if pb else 'null')


def t_bound(ctx, E):
    f = ctx.fn(0x0051d180)  # bool IsItemBoundToWearer(const W8ItemInstance*)
    s0 = ctx.scratch(0)
    for i in range(ctx.n(100)):
        r = ctx.rng('bound', i)
        c = ctx.case('bound.%d' % i, f, conv='c', ret='b')
        p = r.random()
        iid = -1 if p < 0.12 else (r.choice(E.binds) if p < 0.5 else E.pick(r))
        bound = r.randrange(2)
        c.set(s0, item(iid, ident=r.randrange(2), announced=r.randrange(2), bound=bound))
        if iid >= 0 and r.random() < 0.3:
            v = r.choice([0, 1, 2, 0x80, 0xff])
            E.rset8(c, iid, R_BINDS, v)
            c.note(binds=v)
        c.arg(s0)
        c.note(item=iid, bound=bound)


# --------------------------------------------------------------------------- equipment slots

def t_slot_mask(ctx, E):
    f = ctx.fn(0x0051cf80)  # unsigned short GetItemEquipSlotMask(int, bool, bool, bool, bool)
    for i in range(ctx.n(320)):
        r = ctx.rng('slotmask', i)
        c = ctx.case('slotmask.%d' % i, f, conv='c', ret='u16')
        p = r.random()
        if p < 0.5:
            iid = r.choice(E.weapons)
        elif p < 0.8:
            iid = r.choice(E.nonweapons)
        else:
            iid = E.pick(r)
        if r.random() < 0.25:
            cls = r.choice(list(range(14)) + [25, 0x80, 0xff])
            E.rset8(c, iid, R_CLASS, cls)
            c.note(cls=cls)
        if r.random() < 0.3:
            fl = r.choice([0, 4, 8, 0xc, 0x44, 0x88, 0xf3, 0xff, r.randrange(256)])
            E.rset8(c, iid, R_FLAGS, fl)
            c.note(flags=fl)
        if r.random() < 0.08:
            ws = r.choice([0xff, 0xff, 0, 9, 0x7f, 0x80, 0xfe])
            E.rset8(c, iid, R_WSKILL, ws)
            c.note(weapon_skill=ws)
        bools = [r.randrange(2) for _ in range(4)]
        c.arg(iid)
        for b in bools:
            c.arg(b)
        c.note(item=iid, free=''.join(map(str, bools)))


def _hand_item(E, r):
    return r.choice([-1, -1, r.choice(E.two_handed), r.choice(E.one_handed), r.choice(E.shields),
                     r.choice(E.ammo), r.choice(E.ranged), E.pick(r)])


def t_can_equip(ctx, E):
    f = ctx.fn(0x0051cea0)  # bool CanEquipItemInSlot(W8Character*, int, unsigned char, bool)
    for i in range(ctx.n(300)):
        r = ctx.rng('canequip', i)
        c = ctx.case('canequip.%d' % i, f, conv='c', ret='b')
        slot, blob, name = E.put_char(c, r)
        ch = ctx.char(slot)
        hands = {}
        for k in (6, 7, 8, 9):
            if r.random() < 0.5:
                hands[k] = _hand_item(E, r)
                c.set(ch + C_EQUIP + k * ITEM_SIZE, item(hands[k]))
        p = r.random()
        if p < 0.45:
            iid = r.choice(E.weapons)
        elif p < 0.6:
            iid = r.choice(E.shields + E.ammo)
        else:
            iid = E.pick(r)
        if r.random() < 0.15:
            fl = r.choice([0, 4, 8, 0xc])
            E.rset8(c, iid, R_FLAGS, fl)
        eslot = r.randrange(12) if r.random() < 0.85 else r.choice([12, 13, 15, 16, 17, 31, 32, 38,
                                                                   39, 0x80, 0xff])
        ignore = r.randrange(2)
        c.arg(ch)
        c.arg(iid)
        c.arg(eslot)
        c.arg(ignore)
        c.cap(ch, CHAR_SIZE, 'char')
        c.note(char=name, slot=slot, item=iid, equip_slot=eslot, ignore_worn=ignore, hands=hands)


def t_merge_kind(ctx, E):
    f = ctx.fn(0x0051e980)  # bool GetItemMergeKind(int, short*)
    s0 = ctx.scratch(0)
    keys = [114, 110, 104, 144, 145]
    for i in range(ctx.n(150)):
        r = ctx.rng('mergekind', i)
        c = ctx.case('mergekind.%d' % i, f, conv='c', ret='b')
        p = r.random()
        if p < 0.08:
            iid = -1
        elif p < 0.4:
            iid = r.choice(E.merge_keys)
        else:
            iid = E.pick(r)
        if iid >= 0 and r.random() < 0.3:
            v = r.choice(keys + [113, 132, 143, 146, 0, 1, 0x172, 0x7200, 0xff72, 0xffff, 0x8000])
            E.rset16(c, iid, R_UNI, v)
            c.note(uni=v)
        c.set(s0, b'\xa5\xa5\xa5\xa5')
        c.cap(s0, 4, 'related_kind')
        out = 0 if r.random() < 0.1 else s0
        c.arg(iid)
        c.arg(out)
        c.note(item=iid, out='null' if out == 0 else 'S0')


def t_compatible(ctx, E):
    f = ctx.fn(0x0051c8f0)  # bool CompatiblePartnerItems(int ranged, int other)
    for i in range(ctx.n(400)):
        r = ctx.rng('compatible', i)
        c = ctx.case('compatible.%d' % i, f, conv='c', ret='b')
        p = r.random()
        if p < 0.7:
            ranged = r.choice(E.special_ranged)
        elif p < 0.78:
            ranged = r.choice([597, 598, 611, 612, 613, 0x257, 0x262])
            E.rset16(c, ranged, R_UNI, 0x83)
            c.note(ranged_uni=0x83)
        else:
            ranged = E.pick(r)
        other = r.choice(E.partners) if r.random() < 0.55 else E.pick(r)
        if r.random() < 0.2:
            v = r.choice([0x15, 0x16, 0x17, 0x53, 0x70, 0x71, 0x7e, 0, 113, 132, 0x116, 0x8016, 0xffff])
            E.rset16(c, other, R_UNI, v)
            c.note(other_uni=v)
        if r.random() < 0.15:
            v = r.choice([0, 1, 2, 3, 4, 5, 6, 13, 25, 0xff])
            E.rset8(c, other, R_CLASS, v)
            c.note(other_cls=v)
        if r.random() < 0.15:
            v = r.choice([0, 1, 2, 3, 0xff])
            E.rset8(c, other, R_RANGE, v)
            c.note(other_range=v)
        if r.random() < 0.1:
            v = r.choice([0, 1, 2, 3])
            E.rset8(c, ranged, R_RANGE, v)
            c.note(ranged_range=v)
        if r.random() < 0.08:
            v = r.choice([0xb, 0xc, 0xd, 0x25, 0x68, 0x6e, 0x72, 0x83, 0x10b, 0x8083, 0x0e])
            E.rset16(c, ranged, R_UNI, v)
            c.note(ranged_uni=v)
        c.arg(ranged)
        c.arg(other)
        c.note(ranged=ranged, other=other)


def t_hold_together(ctx, E):
    f = ctx.fn(0x0051cc40)  # static bool CanHoldItemsTogether(int, int)

    def choose(r):
        p = r.random()
        if p < 0.08:
            return -1
        groups = [E.two_handed, E.ranged, E.ammo, E.shields, E.melee, E.melee, E.armor,
                  E.special_ranged, E.partners]
        if p < 0.85:
            return r.choice(r.choice(groups))
        return E.pick(r)

    for i in range(ctx.n(300)):
        r = ctx.rng('holdtogether', i)
        c = ctx.case('holdtogether.%d' % i, f, conv='c', ret='b')
        a, b = choose(r), choose(r)
        for iid, tag in ((a, 'a'), (b, 'b')):
            if iid < 0:
                continue
            if r.random() < 0.1:
                v = r.choice([0, 1, 2, 3, 4, 5, 6, 0xff])
                E.rset8(c, iid, R_CLASS, v)
                c.note(**{tag + '_cls': v})
            if r.random() < 0.08:
                v = r.choice([0, 4, 8, 0xfb, 0xff])
                E.rset8(c, iid, R_FLAGS, v)
                c.note(**{tag + '_flags': v})
            if r.random() < 0.1:
                v = r.choice([0, 1, 2, 3])
                E.rset8(c, iid, R_RANGE, v)
                c.note(**{tag + '_range': v})
        c.arg(a)
        c.arg(b)
        c.note(first=a, second=b)


def t_held_fits(ctx, E):
    f = ctx.fn(0x0051cde0)  # bool HeldItemFitsPairedSlot(int party_slot, W8EquipSlot)
    paired = {6: 7, 7: 6, 8: 9, 9: 8}
    total = ctx.n(250)
    for i in range(total):
        r = ctx.rng('heldfits', i)
        c = ctx.case('heldfits.%d' % i, f, conv='c', ret='b')
        if i < 6:   # iChar == -1 asserts; non-hand slots return before using it
            pslot = -1
            eslot = r.choice([0, 3, 5, 10, 11, 12, -1])
            E.put_char(c, r, slot=0)
        else:
            pslot = r.randrange(8)
            E.put_char(c, r, slot=pslot)
            eslot = r.choice([6, 7, 8, 9]) if r.random() < 0.7 else r.choice(
                [0, 1, 2, 3, 4, 5, 10, 11, 12, 13, -1, 255, 0x7fffffff, -0x80000000])
            ch = ctx.char(pslot)
            target = paired.get(eslot, r.choice([6, 7, 8, 9]))
            if r.random() < 0.7:
                other = _hand_item(E, r)
                c.set(ch + C_EQUIP + target * ITEM_SIZE, item(other))
                c.note(paired_item=other)
        held = _hand_item(E, r) if r.random() < 0.85 else r.choice(E.partners + E.special_ranged)
        c.set(E.status + S_CURSOR, bytes([1 if held != -1 else 0]) + item(held))
        c.arg(pslot)
        c.arg(eslot)
        c.note(party_slot=pslot, equip_slot=eslot, held=held)


# --------------------------------------------------------------------------- usability

def _caster_level_values():
    # thresholds of MinimumCasterLevelForSpellLevel: 1, 3, 5, 8, 11, 14, 18
    return [0, 1, 2, 3, 4, 5, 7, 8, 10, 11, 13, 14, 17, 18, 19, 25, -1]


def _patch_usability(c, r, E, ch, blob, iid, note):
    """Vary the inputs CanCharacterUseItem reads: character profession/race/gender,
    the record's masks and requirements, category/spell and the learned/caster data."""
    prof = blob.get_u32(C_PROF)
    race = blob.get_u32(C_RACE)
    if r.random() < 0.2:
        prof = r.choice(list(range(15)) + [15, 16, 31, 32])
        c.set(ch + C_PROF, struct.pack('<I', prof))
        note['prof'] = prof
    if r.random() < 0.15:
        race = r.choice(list(range(11)) + [11, 16, 31, 32])
        c.set(ch + C_RACE, struct.pack('<I', race))
        note['race'] = race
    if r.random() < 0.15:
        g = r.choice([0, 1, 0, 1, 2, 7, 8])
        c.set(ch + C_GENDER, struct.pack('<I', g))
        note['gender'] = g
    if r.random() < 0.3:
        bit = (1 << (prof & 31)) & 0xffff
        v = r.choice([0xffff, 0, bit, (~bit) & 0xffff, r.getrandbits(16), 0x7fff, 0x8000])
        E.rset16(c, iid, R_PROF, v)
        note['prof_mask'] = v
    if r.random() < 0.3:
        bit = 1 << (race & 31)
        v = r.choice([0xffffffff, 0, bit, (~bit) & 0xffffffff, r.getrandbits(32), 0xffdf])
        E.rset32(c, iid, R_RACE, v)
        note['race_mask'] = v
    if r.random() < 0.25:
        v = r.choice([0, 1, 2, 3, 3, 0xff, 4, 7])
        E.rset8(c, iid, R_GENDER, v)
        note['gender_mask'] = v
    if r.random() < 0.35:
        req = b''
        for _ in range(2):
            if r.random() < 0.3:
                req += b'\xff' + bytes([r.randrange(256)])
                continue
            stat = r.choice([0, 1, 2, 3, 4, 5, 6, 6, 7, 9])
            eff = blob.get_u32(C_ATTR + stat * ATTR_STEP + 4) if stat < 7 else 0
            m = r.choice([eff - 1, eff, eff + 1, eff + 10, 0, 255, r.randrange(256)])
            req += bytes([stat, max(0, min(255, m))])
        c.set(E.rec(iid, R_AREQ), req)
        note['attr_req'] = req.hex()
    if r.random() < 0.35:
        req = b''
        for _ in range(2):
            if r.random() < 0.3:
                req += b'\xff' + bytes([r.randrange(256)])
                continue
            stat = r.randrange(0x29) if r.random() < 0.9 else r.choice([0x29, 0x30, 0x3f])
            lvl = blob.get_u32(C_SKILL + stat * SKILL_STEP + 6) if stat < 0x29 else 0
            m = r.choice([lvl - 1, lvl, lvl + 1, lvl + 25, 0, 1, 255, r.randrange(256)])
            req += bytes([stat, max(0, min(255, m))])
        c.set(E.rec(iid, R_SREQ), req)
        note['skill_req'] = req.hex()
    cat = E.db[iid]['cat']
    spell = E.db[iid]['spell']
    if r.random() < 0.35:
        cat = r.choice([3, 3, 6, 6, 8, 8, 0, 1, 2, 4, 5, 7, 9])
        E.rset8(c, iid, R_CAT, cat)
        note['cat'] = cat
        if r.random() < 0.7 or spell == 0:
            spell = 0 if r.random() < 0.05 else r.randrange(1, SPELL_COUNT)
            E.rset8(c, iid, R_SPELL, spell)
            note['spell'] = spell
    if cat == 3 and r.random() < 0.8:
        v = r.choice([0, 1, 1, 2, 0xffffffff])
        c.set(ch + C_LEARNED + spell * 4, struct.pack('<I', v))
        note['learned'] = v
    if cat in (6, 8) and r.random() < 0.8:
        lv = r.choice(_caster_level_values())
        c.set(ch + C_PLEVEL + (9 if cat == 6 else 8) * 4, struct.pack('<i', lv))
        note['caster_level'] = lv


def t_can_use(ctx, E):
    f = ctx.fn(0x0051d610)  # bool CanCharacterUseItem(const W8Character*, int)
    for i in range(ctx.n(400)):
        r = ctx.rng('canuse', i)
        c = ctx.case('canuse.%d' % i, f, conv='c', ret='b')
        slot, blob, name = E.put_char(c, r)
        ch = ctx.char(slot)
        p = r.random()
        if p < 0.3:
            iid = E.pick(r)
        elif p < 0.5:
            iid = r.choice(E.restricted)
        elif p < 0.75:
            iid = r.choice(E.casters)
        else:
            iid = E.pick(r)
        note = {'char': name, 'slot': slot, 'item': iid}
        if p >= 0.3:
            _patch_usability(c, r, E, ch, blob, iid, note)
        c.arg(ch)
        c.arg(iid)
        c.cap(ch, CHAR_SIZE, 'char')
        c.note(**note)


def t_any_party(ctx, E):
    f = ctx.fn(0x0051d7a0)  # bool AnyPartyMemberCanUseItem(int)
    for i in range(ctx.n(200)):
        r = ctx.rng('anyparty', i)
        c = ctx.case('anyparty.%d' % i, f, conv='c', ret='b')
        party = ctx.set_party(c, r)
        occ = []
        for s in range(8):
            o = 1 if r.random() < 0.8 else 0
            occ.append(o)
            c.set(E.xrow(s), bytes([o]))
            if r.random() < 0.12:
                c.set(ctx.char(s) + C_HP, b'\0\0\0\0')
            if r.random() < 0.12:
                c.set(ctx.char(s) + C_HIGHEST, struct.pack('<I', r.choice([0, 1, 17, 18, 19, 20])))
        p = r.random()
        if p < 0.45:
            iid = E.pick(r)
        elif p < 0.75:
            iid = r.choice(E.restricted)
        else:
            iid = E.pick(r)
            target = party[r.randrange(8)][1]
            prof = target.get_u32(C_PROF)
            E.rset16(c, iid, R_PROF, (1 << (prof & 31)) & 0xffff)
            if r.random() < 0.5:
                E.rset8(c, iid, R_GENDER, 1 << (target.get_u32(C_GENDER) & 7))
            c.note(only_prof=prof)
        c.arg(iid)
        c.note(item=iid, occupied=''.join(map(str, occ)), party=[n for _, _, n in party])


def t_can_activate(ctx, E):
    f = ctx.fn(0x0051d800)  # bool CanCharacterActivateItem(W8Character*, const W8ItemInstance*)
    s0 = ctx.scratch(0)
    for i in range(ctx.n(300)):
        r = ctx.rng('canactivate', i)
        c = ctx.case('canactivate.%d' % i, f, conv='c', ret='b')
        slot, blob, name = E.put_char(c, r)
        ch = ctx.char(slot)
        loc = r.random()
        if loc < 0.6:
            k = r.randrange(12)
            iaddr, where = ch + C_EQUIP + k * ITEM_SIZE, 'equip%d' % k
        elif loc < 0.8:
            k = r.randrange(8)
            iaddr, where = ch + C_PACK + k * ITEM_SIZE, 'pack%d' % k
        else:
            iaddr, where = s0, 'scratch'
        p = r.random()
        if p < 0.08:
            iid = -1
        elif p < 0.16:
            iid = 0x29f
        elif p < 0.45:
            iid = r.choice(E.casters)
        else:
            iid = E.pick(r)
        uses = r.choice([0, 0, 1, 2, r.randrange(256)])
        c.set(iaddr, item(iid, stack=r.choice([0, 1, 5]), uses=uses, ident=1))
        note = {'char': name, 'slot': slot, 'item': iid, 'where': where, 'uses': uses}
        if iid >= 0:
            it = E.db[iid]
            if r.random() < 0.7:   # let CanCharacterUseItem pass most of the time
                E.rset16(c, iid, R_PROF, 0xffff)
                E.rset32(c, iid, R_RACE, 0xffffffff)
                E.rset8(c, iid, R_GENDER, 3)
                c.set(E.rec(iid, R_AREQ), b'\xff\x00\xff\x00\xff\x00\xff\x00')
                note['permissive'] = 1
            if r.random() < 0.4:
                fl = (it['flags'] | 0x40) if r.random() < 0.5 else (it['flags'] & ~0x40)
                E.rset8(c, iid, R_FLAGS, fl)
                note['flags'] = fl
            if r.random() < 0.4:
                cls = r.randrange(26)
                E.rset8(c, iid, R_CLASS, cls)
                note['cls'] = cls
            cat = it['cat']
            if r.random() < 0.5:
                cat = r.randrange(10)
                E.rset8(c, iid, R_CAT, cat)
                note['cat'] = cat
            spell = it['spell']
            if r.random() < 0.4 or (cat in (3, 6, 8) and spell == 0 and r.random() < 0.8):
                spell = 0 if r.random() < 0.2 else r.randrange(1, SPELL_COUNT)
                E.rset8(c, iid, R_SPELL, spell)
                note['spell'] = spell
            if r.random() < 0.4:
                qk = r.randrange(5)
                E.rset8(c, iid, R_QKIND, qk)
                note['qk'] = qk
            if cat == 3:
                c.set(ch + C_LEARNED + spell * 4, struct.pack('<I', r.choice([0, 0, 1])))
            if cat in (6, 8) and r.random() < 0.7:
                lv = r.choice(_caster_level_values())
                c.set(ch + C_PLEVEL + (9 if cat == 6 else 8) * 4, struct.pack('<i', lv))
                note['caster_level'] = lv
        c.arg(ch)
        c.arg(iaddr)
        c.cap(ch, CHAR_SIZE, 'char')
        c.note(**note)


def t_hands_empty(ctx, E):
    f = ctx.fn(0x0051f8d0)  # bool AreAllHandSlotsEmpty(const W8Character*)
    for i in range(ctx.n(80)):
        r = ctx.rng('handsempty', i)
        c = ctx.case('handsempty.%d' % i, f, conv='c', ret='b')
        slot, blob, name = E.put_char(c, r)
        ch = ctx.char(slot)
        ids = []
        for k in (6, 7, 8, 9):
            v = -1 if r.random() < 0.7 else r.choice([0, -2, 0x7fffffff, E.pick(r)])
            ids.append(v)
            c.set(ch + C_EQUIP + k * ITEM_SIZE, item(v))
        c.arg(ch)
        c.cap(ch, CHAR_SIZE, 'char')
        c.note(char=name, hands=ids)


def t_singled_out(ctx, E):
    f = ctx.fn(0x0051cce0)  # bool ItemHasSingledOutGenericName(int)
    for i in range(ctx.n(120)):
        r = ctx.rng('singledout', i)
        c = ctx.case('singledout.%d' % i, f, conv='c', ret='b')
        p = r.random()
        if p < 0.05:
            iid = -1
        elif p < 0.35:
            iid = r.choice(E.singled)
        else:
            iid = E.pick(r)
        if iid >= 0 and r.random() < 0.35:
            v = r.choice([0xa, 0xb, 0xc, 0xd, 0xe, 0x24, 0x25, 0x26, 0x82, 0x83, 0x84, 0x10b, 0x183,
                          0x8083, 0xffff, 0x83 + 0x10000 - 0x100, 0])
            E.rset16(c, iid, R_UNI, v)
            c.note(uni=v)
        c.arg(iid)
        c.note(item=iid)


def t_uses_shots(ctx, E):
    f = ctx.fn(0x0051cdb0)  # bool ItemUsesShots(int)
    for i in range(ctx.n(80)):
        r = ctx.rng('usesshots', i)
        c = ctx.case('usesshots.%d' % i, f, conv='c', ret='b')
        p = r.random()
        if p < 0.06:
            iid = -1
        elif p < 0.3:
            iid = r.choice(E.shots)
        else:
            iid = E.pick(r)
        if iid >= 0 and r.random() < 0.35:
            v = r.choice([0, 1, 2, 3, 4, 5, 0x84, 0xff])
            E.rset8(c, iid, R_QKIND, v)
            c.note(qk=v)
        c.arg(iid)
        c.note(item=iid)


def t_spell_presentation(ctx, E):
    f = ctx.fn(0x0051dcb0)  # W8Skill GetItemSpellPresentation(const W8ItemDatabaseRecord*)
    s0 = ctx.scratch(0)
    for i in range(ctx.n(150)):
        r = ctx.rng('spellpresent', i)
        c = ctx.case('spellpresent.%d' % i, f, conv='c', ret='i')
        if r.random() < 0.5:
            iid = r.choice(E.casters) if r.random() < 0.5 else E.pick(r)
            c.arg(E.rec(iid))
            c.note(record=iid)
        else:
            spell = r.choice([0x58, 0x74, 0, 0x57, 0x59, 0x73, 0x75, 0xd8, 0xf4, r.randrange(256)])
            cat = r.randrange(11)   # table has 11 entries; real records use 0..9
            rec = bytearray(REC_SIZE)
            rec[R_SPELL] = spell
            rec[R_CAT] = cat
            c.set(s0, bytes(rec))
            c.arg(s0)
            c.note(spell=spell, cat=cat)


def t_can_unequip(ctx, E):
    f = ctx.fn(0x0051d1c0)  # bool CanUnequipSlotItem(const W8Character*, W8EquipSlot)
    for i in range(ctx.n(200)):
        r = ctx.rng('canunequip', i)
        c = ctx.case('canunequip.%d' % i, f, conv='c', ret='b')
        slot, blob, name = E.put_char(c, r)
        ch = ctx.char(slot)
        es = r.randrange(12)
        p = r.random()
        iid = -1 if p < 0.12 else (r.choice(E.binds) if p < 0.55 else E.pick(r))
        announced = r.randrange(2)
        c.set(ch + C_EQUIP + es * ITEM_SIZE, item(iid, announced=announced, bound=r.randrange(2)))
        note = {'char': name, 'equip_slot': es, 'item': iid, 'announced': announced}
        if iid >= 0 and r.random() < 0.3:
            v = r.choice([0, 1, 2, 0xff])
            E.rset8(c, iid, R_BINDS, v)
            note['binds'] = v
        if r.random() < 0.35:
            v = r.choice([0, 1, 2, 0xffffffff, r.getrandbits(32)])
            c.set(ch + C_COND + COND_DEAD * 4, struct.pack('<I', v))
            note['dead'] = v
        c.arg(ch)
        c.arg(es)
        c.cap(ch, CHAR_SIZE, 'char')
        c.note(**note)


def t_can_leave(ctx, E):
    f = ctx.fn(0x0051f2b0)  # bool CanItemLeaveItsSlot(const W8ItemInstance*)
    s0 = ctx.scratch(0)
    for i in range(ctx.n(150)):
        r = ctx.rng('canleave', i)
        c = ctx.case('canleave.%d' % i, f, conv='c', ret='b')
        started = E.set_started(c, r)
        iid = -1 if r.random() < 0.1 else E.pick(r)
        ident, bound = r.randrange(2), r.randrange(2)
        c.set(s0, item(iid, ident=ident, bound=bound, announced=r.randrange(2)))
        if iid >= 0 and r.random() < 0.3:
            v = r.choice([3, 4, 12, 13, 16, 25, 0xff])
            E.rset8(c, iid, R_CLASS, v)
            c.note(cls=v)
        c.arg(s0)
        c.note(item=iid, identified=ident, bound=bound, game_started=started)


# --------------------------------------------------------------------------- merging

def t_merge_items(ctx, E):
    f = ctx.fn(0x0051f2f0)  # bool MergeItems(W8Character*, W8ItemInstance* destination)
    for i in range(ctx.n(150)):
        r = ctx.rng('mergeitems', i)
        c = ctx.case('mergeitems.%d' % i, f, conv='c', ret='b')
        slot, blob, name = E.put_char(c, r)
        ch = ctx.char(slot)
        iid = r.choice(E.merge_stack) if r.random() < 0.75 else r.choice(E.merge_other)
        it = E.db[iid]
        qmax = it['qmax']
        if it['qk'] == 1:
            # the target stays within maximum_quantity: NormalizeItemStack would otherwise
            # split the overflow into the party pool
            dstack = r.choice([0, 1, qmax // 2, max(qmax - 1, 0), qmax, r.randint(0, qmax)])
            duses = 0 if dstack or r.random() < 0.7 else r.randint(0, qmax)
            room = qmax - max(dstack, duses if dstack == 0 else 0)
            hstack = r.choice([0, 1, 2, room, room + 1, max(room - 1, 0), r.randrange(256), 255])
        else:
            dstack = r.choice([0, 1, 5, r.randrange(256)])
            duses = r.choice([0, 1, r.randrange(256)])
            hstack = r.choice([0, 1, r.randrange(256)])
        hstack = max(0, min(255, hstack))
        huses = r.choice([0, 0, r.randrange(256)])
        loc = r.random()
        if loc < 0.6:
            k = r.randrange(8)
            dest, where = ch + C_PACK + k * ITEM_SIZE, 'pack%d' % k
        elif loc < 0.8:
            k = r.randrange(12)
            dest, where = ch + C_EQUIP + k * ITEM_SIZE, 'equip%d' % k
        else:
            k = r.randrange(500)
            dest, where = E.status + S_POOL + k * ITEM_SIZE, 'pool%d' % k
        c.set(dest, item(iid, stack=dstack, uses=duses, ident=1, hint=r.randrange(2)))
        c.set(E.status + S_CURSOR, b'\x01' + item(iid, stack=hstack, uses=huses, ident=1,
                                                 hint=r.randrange(2)))
        c.set(E.xstatus + X_CURSOR, struct.pack('<iII', -1, 0, 0))   # W8_CURSOR_NONE
        c.set(E.xstatus + X_HELD, struct.pack('<iBH', r.choice([slot, -1]), r.choice([0, 1, 2, 0xff]),
                                              r.choice([k, 0xffff])))
        c.cap(E.status + S_CURSOR, 1 + ITEM_SIZE, 'held')
        c.cap(dest, ITEM_SIZE, 'destination')
        c.cap(E.xstatus + X_HELD, 7, 'held_origin')
        c.cap(E.xstatus + X_CURSOR, 12, 'cursor')
        c.cap(E.status + S_POOL_COUNT, 4, 'pool_count')
        c.cap(ch, CHAR_SIZE, 'char')
        c.arg(ch)
        c.arg(dest)
        c.note(char=name, item=iid, qk=it['qk'], qmax=qmax, dest=where, dest_stack=dstack,
               dest_uses=duses, held_stack=hstack, held_uses=huses)


# --------------------------------------------------------------------------- entry

def cases(ctx):
    E = _Env(ctx, _load_items())
    t_unit_weight(ctx, E)
    t_item_in_hand(ctx, E)
    t_stack_weight(ctx, E)
    t_stack_value(ctx, E)
    t_default_slot(ctx, E, 'defaultslot', 0x0051c4e0, 200)
    t_paired_slot(ctx, E)
    t_video_object(ctx, E)
    t_format_name(ctx, E)
    t_equip_class(ctx, E)
    t_uni_index(ctx, E)
    t_share(ctx, E, 'shareclass', 0x0051b940, R_CLASS, 1)
    t_share(ctx, E, 'shareuni', 0x0051b990, R_UNI, 2)
    t_bound(ctx, E)
    t_slot_mask(ctx, E)
    t_can_equip(ctx, E)
    t_merge_kind(ctx, E)
    t_compatible(ctx, E)
    t_hold_together(ctx, E)
    t_held_fits(ctx, E)
    t_can_use(ctx, E)
    t_any_party(ctx, E)
    t_can_activate(ctx, E)
    t_hands_empty(ctx, E)
    t_default_slot(ctx, E, 'slotgroup', 0x0051c850, 150)
    t_display_name(ctx, E)
    t_singled_out(ctx, E)
    t_uses_shots(ctx, E)
    t_spell_presentation(ctx, E)
    t_can_unequip(ctx, E)
    t_can_leave(ctx, E)
    t_merge_items(ctx, E)
