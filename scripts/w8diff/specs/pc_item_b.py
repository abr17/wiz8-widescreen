"""PC Item.cpp, lines 1401-2800 (w8diff spec pc_item_b).

Tested (retail address, function, cases at --scale 1):
  0x0051bf40 SpendPartyGold                     160
  0x0051bea0 AddPartyGold                       220  (announce off)
  0x00522180 FindCharacterItemAt                260  (ret 'p'; a few negative slots on purpose)
  0x005222d0 GetOriginOfCharacterItem           260
  0x0051f870 CountUsableCharacterItems          300
  0x005207c0 ItemClassNormalizesTarget          356  (256 scratch classes + 100 real records)
  0x00520f20 IsItemWornByCharacter              160
  0x00520f60 IsItemCarriedByCharacter           140
  0x0051c020 ReplaceOrCreateItem                380  (300 scratch items + 80 party-pool slots)
  0x0051d0d0 BindEquippedItem                   240
  0x00520880 GetItemSpell                       250
  0x005207e0 GetItemSpellRange                  250
  0x005209f0 PartyAttemptsToIdentifyItem        260
  0x005208f0 TryIdentifyItemFor                 320
  0x00520b40 ApplyIdentifyAttempt               350
  0x00520a70 CountIdentifyAttemptsNeeded        320
  0x00520bc0 RevealCharacterItemBindings        300
  0x00520750 ItemHasHiddenProperties            819  (every item record)
  0x0051e920 AddItemUses                        350
  0x0051e9f0 MergeItemUses                      260
  0x0051eb90 EquipMatchingPartnerItem           200
  0x00520f90 FindItemOnCharacter                320
  0x00521060 FindItemOnParty                    320
  0x005211a0 CountItemOnCharacter               300
  0x00521240 CountItemOnParty                   300
  0x00521360 EveryCharacterHasItem              250
  0x005213c0 FindCharacterItemByDatabaseKind    300
  0x00520600 CompareItemsForPool                400
  0x005205b0 SortPartyItemPool                  130
  0x0051f900 MergeItemStacks                    400  (also covers the inlined NormalizeItemStack)
  0x0051fe30 CopyItemInstance                   300
  0x0051c300 AddItemToCharacter                 300  (announce off)
  0x0051c280 StoreItemWithCharacterOrParty      260  (announce off)
  0x0051bc00 GiveItemToCharacterOrParty         150  (announces: text box lines excluded from caps)
  0x005223a0 StashDepartingCharacterItems       180  (pool never full, so nothing is dropped)
  0x0051d230 BindEveryPartyItem                 122  (110 out of combat + 12 refused in combat)

Skipped:
  0x0051b560 InitializeItemVideoObjects     - allocates the global item video-object vector (resource setup)
  0x0051b580 ReleaseGenericItemNames        - frees global name buffers and the video-object vector
  0x0051ba00 GiveHeldItemToCharacterOrParty - releases/changes the mouse cursor (ClearHeldItemDisplay) and
                                              opens a ShowNoticeLine dialog on refusal
  0x0051be50 DropItemInHand                 - drops the held item into the world or opens a dialog
  0x0051bf60 CreateItemIntoHandOrPool       - always resets the cursor display and puts the item in hand
  0x0051fb40 NormalizeItemStack             - inlined in the port (not in Wiz8Runtime.map); exercised
                                              through MergeItemStacks (dest stacks above the maximum)
  (DropUnstoredCharacterItem has no FUNCTION annotation; it is static and drops into the world.)

Notes:
  * Item ids come from the real Items.dbs (tables at the end, extracted from Data\\DATA.SLF):
    819 records. Plot items whose acquisition sets facts or queues reactions (0x1d2, 0x201,
    0x239, 0x242-0x244, 0x264, 0x27c) are never handed to functions that acquire items.
  * Out-pointer parameters (found**, first** ...) hold process-specific addresses; a small model of
    the retail search decides when such a dword holds a pointer (then it is ignored) and when it
    must hold 0 or stay untouched (then it is compared).
  * Functions that print notices get g_status capped in three parts that leave out the text-box
    line counters (0x1795..0x17ae, 0x4997..0x49b6).
  * Edge cases kept on purpose (the port was fixed to match retail):
    - FindCharacterItemByDatabaseKind: with include_backpack == 0 and no equipped match retail
      returns without touching *out (0x5213ff -> 0x521479).
    - FindCharacterItemAt: retail compares origin and slot as signed (origin 0x80..0xff gets only
      the 0x14fd assert, slot 0x8000..0xffff indexes backwards without 0x1505/0x1509/0x150d)
      (findat.0..15 are the edge cases; findat.14/15 point outside controlled memory, so only
      their asserts are compared).
  * gXStatus is capped without the volatile fields of the party portrait records (MM_VOLATILE:
    sound handle, mouth-gap pointers, event pointer, clock stamps) that a voice quote sets.
  * Differences expected from reading the retail code (cases kept on purpose):
    - SortPartyItemPool with ties (sortpool cases noted ties=True): retail calls msvcrt qsort,
      the port its own CRT qsort; equal-key entries may come out in a different order.
"""
import random
import struct

NITEMS = 819
CHAR = 0x1862
EQ = 0xf5d            # W8Character::EquippedItem[12]
BP = 0x1029           # W8Character::backpack[8]
IT = 12               # sizeof(W8ItemInstance)
XROW = 0x106          # sizeof(W8PartySlotRow)
REC = 0x10d           # sizeof(W8ItemDatabaseRecord)

# W8Character
C_COND = 0xa01
C_DEAD = C_COND + 0x12 * 4
C_HC = 0xb01
C_HP = 0xb11
SK = 0x19d + 0x14 * 0x26   # skills[W8_SKILL_ARTIFACTS]
SK_ACTIVE, SK_POINTS, SK_LEVEL, SK_BASE, SK_PRACTICE = 0x0, 0x2, 0x6, 0xa, 0xe

# W8GlobalStatus
S_STARTED = 0xc
S_GOLD = 0x19
S_POOL = 0x21
S_COUNT = 0x1791
S_TEXT_A = 0x1795
S_TEXT_A_END = 0x17af
S_LEVEL = 0x1900
S_PROGRESS = 0x1a04
S_PROGRESS_END = 0x2013
S_CURSOR = 0x235a
S_HAND = 0x235b
S_TEXT_B = 0x4997
S_TEXT_B_END = 0x49b7
S_SIZE = 0x49c2

# W8XStatus
X_ITEMS = 0x8c0
X_COMBAT = 0x8dc
X_MOVE = 0x916
X_SIZE = 0x1a0a

# W8PartySlotRow
R_OCC = 0x0
R_ITEM_PENDING = 0xf5

PLOT = {0x1d2, 0x201, 0x239, 0x242, 0x243, 0x244, 0x264, 0x27c}
SINGLED = {0x0b, 0x0c, 0x0d, 0x25, 0x83}
PARTNER_NAMES = {0x16, 0x53, 0x17, 0x71, 0x70, 0x15, 0x7e}
ICON_NONE_SLOTS = {8, 9}  # g_equip_slot_icons[slot] == -1 (retail 0x648c5c)


def u32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def val(iid):
    return struct.unpack_from('<I', VAL, 4 * iid)[0]


def item(iid, stack=0, uses=0, ident=0, hint=0, u8=0, eff=0, bann=0, bound=0):
    return struct.pack('<iBBBBBBBB', iid, int(stack) & 0xff, int(uses) & 0xff, int(bool(ident)),
                       int(bool(hint)), int(u8) & 0xff, int(eff) & 0xff, int(bool(bann)),
                       int(bool(bound)))


EMPTY = item(-1)
EMPTY_QUIET = item(-1, eff=1)  # empty slot; bit0 of 0x09 keeps DeliverExceptionalItemReaction quiet


def iid_of(it):
    return struct.unpack_from('<i', it, 0)[0]


def stack_of(it):
    return it[4]


class L:
    pass


def build_lists():
    L.all = list(range(NITEMS))
    L.safe = [i for i in L.all if i not in PLOT]
    L.stack = [i for i in L.safe if QK[i] == 1]
    L.charged = [i for i in L.safe if 2 <= QK[i] <= 4]
    L.plain = [i for i in L.safe if QK[i] == 0]
    L.bind = [i for i in L.safe if BIND[i]]
    L.spell = [i for i in L.safe if SPELL[i]]
    L.ranged = [i for i in L.safe if UNI[i] in SINGLED]
    L.partner = [i for i in L.safe if UNI[i] in PARTNER_NAMES or (EQC[i] == 2 and UNI[i] == 0)]
    L.hand = [i for i in L.safe if EQC[i] <= 5]
    L.group = {}
    for i in L.all:
        L.group.setdefault((EQC[i], UNI[i]), []).append(i)
    L.byclass = {}
    for i in L.all:
        L.byclass.setdefault(EQC[i], []).append(i)


def rand_qty(r, iid):
    qk = QK[iid]
    if qk == 1:
        m = max(1, QMAX[iid])
        return r.choice([1, 1, m, max(1, m - 1), r.randint(1, m)]), 0
    if 2 <= qk <= 4:
        m = DMAX[iid]
        return 0, r.choice([0, 1, m, r.randint(0, max(1, m))])
    return 0, 0


def rand_item(r, ids, eff=None, ident=None):
    iid = r.choice(ids)
    st, us = rand_qty(r, iid)
    idf = (r.random() < 0.7) if ident is None else ident
    return item(iid, st, us, idf, idf and r.random() < 0.5, int(idf), (r.random() < 0.3) if eff is None else eff,
                r.random() < 0.2, r.random() < 0.3)


class Env:
    def __init__(self, ctx):
        self.ctx = ctx
        self.G = ctx.g('g_status')
        self.X = ctx.g('gXStatus')
        self.XCH = (self.G + 8).deref()
        self.RECS = ctx.g('g_item_records').deref()

    def char(self, s):
        return self.ctx.char(s)

    def row(self, s):
        return self.XCH + s * XROW

    def pool(self, k):
        return self.G + S_POOL + k * IT

    def eq(self, s, k):
        return self.ctx.char(s) + EQ + k * IT

    def bp(self, s, k):
        return self.ctx.char(s) + BP + k * IT

    def rec(self, iid):
        return self.RECS + iid * REC


def setup_party(e, c, r, occ=None, combat=0):
    party = e.ctx.set_party(c, r)
    if occ is None:
        occ = [1] * 6 + [int(r.random() < 0.4), int(r.random() < 0.4)]
    for s in range(8):
        c.set(e.row(s) + R_OCC, bytes([occ[s]]))
    c.set(e.G + S_STARTED, b'\x01')
    c.set(e.G + S_CURSOR, b'\x00')
    c.set(e.X + X_COMBAT, bytes([combat]))
    c.set(e.X + X_ITEMS, u32(NITEMS))
    return party, occ


def items_of(blob):
    eq = [bytes(blob[EQ + k * IT:EQ + (k + 1) * IT]) for k in range(12)]
    bp = [bytes(blob[BP + k * IT:BP + (k + 1) * IT]) for k in range(8)]
    return eq, bp


def put_items(e, c, slot, blob, eq, bp):
    """Write the twenty item records of one party member (only the changed ones when few
    changed, else one set over the whole run with flags1 kept); blob is updated too."""
    old = bytes(blob[EQ:BP + 8 * IT])
    b = bytearray(old)
    for k in range(12):
        b[k * IT:(k + 1) * IT] = eq[k]
    for k in range(8):
        o = BP - EQ + k * IT
        b[o:o + IT] = bp[k]
    blob[EQ:BP + 8 * IT] = b
    offs = [k * IT for k in range(12)] + [BP - EQ + k * IT for k in range(8)]
    changed = [o for o in offs if b[o:o + IT] != old[o:o + IT]]
    if len(changed) <= 6:
        for o in changed:
            c.set(e.char(slot) + EQ + o, bytes(b[o:o + IT]))
    else:
        c.set(e.char(slot) + EQ, bytes(b))


def sanitize(r, its):
    """Replace plot items (fact side effects on acquisition) with ordinary ones."""
    out = []
    for it in its:
        if iid_of(it) in PLOT:
            it = rand_item(r, L.safe)
        out.append(it)
    return out


def set_pool(e, c, entries):
    if entries:
        c.set(e.pool(0), b''.join(entries))
    c.set(e.G + S_COUNT, u32(len(entries)))


def cap_status(e, c, text):
    if text:
        c.cap(e.G, S_TEXT_A, 'status_a')
        c.cap(e.G + S_TEXT_A_END, S_TEXT_B - S_TEXT_A_END, 'status_b')
        c.cap(e.G + S_TEXT_B_END, S_SIZE - S_TEXT_B_END, 'status_c')
    else:
        c.cap(e.G, S_SIZE, 'status')


# W8MonsterManagerEntry (0x118 bytes; eight of them lead gXStatus). A portrait voice quote
# (QuoteManager, queued by the item code for a party member) writes process-specific values
# there: the sound handle (+0x01), the mouth-gap range pointers (+0x0d head, +0x11 cursor), the
# active event pointer (+0x71) and the portrait clocks (+0x7d frame, +0x91 pose, +0x95 idle,
# +0xca fx, +0xd2 pulse) stamped from the running clock. They are not compared.
MM_ENTRY = 0x118
MM_VOLATILE = (0x01, 0x0d, 0x11, 0x71, 0x7d, 0x91, 0x95, 0xca, 0xd2)
X_IGNORE = [s * MM_ENTRY + o for s in range(8) for o in MM_VOLATILE]


def cap_world(e, c, text=False, xstatus=True, rows=True):
    c.cap(e.char(0), 8 * CHAR, 'chars')
    cap_status(e, c, text)
    if xstatus:
        c.cap(e.X, X_SIZE, 'xstatus', ignore=X_IGNORE)
    if rows:
        c.cap(e.XCH, 8 * XROW, 'xchar')
    # RefreshAfterItemRecordChange recomputes it when the feet slot changes
    c.cap(e.ctx.g('g_party_has_slope_override_item'), 1, 'slope_item')


def items_count_value(r, iid=None):
    """gXStatus.uiItemsInDatabase override: real count, or a value that moves the asserts."""
    cands = [0, 1, 100, 400, 818, 820, 0x7fffffff, 0x80000000, 0xffffffff]
    if iid is not None:
        cands += [iid, iid + 1, max(0, iid - 1)]
    return r.choice(cands)


# fixed blobs (one distinct setb each)
PATTERN_ITEMS = bytes(((k * 37 + 11) ^ (k >> 3)) & 0xff for k in range(BP + 8 * IT - EQ))
PATTERN_POOL = bytes(((k * 29) ^ ((k >> 8) * 7) ^ 0x5a) & 0xff for k in range(500 * IT + 4))


def full_pool():
    rr = random.Random(0x5ec7)
    out = []
    for k in range(500):
        iid = rr.choice([i for i in range(NITEMS) if QK[i] != 1 and i not in PLOT])
        out.append(item(iid, 0, rr.randint(0, 3), rr.random() < 0.6, 0, 1, 1, 0, rr.random() < 0.3))
    return b''.join(out) + u32(500)


# ----------------------------------------------------------------------------- gold

def t_spend(ctx, e):
    fn = ctx.fn(0x0051bf40)
    golds = [0, 1, 2, 99, 100, 1000, 123456, 0x7fffffff, 0x80000000, 0x80000001, 0xfffffffe, 0xffffffff]
    for i in range(ctx.n(160)):
        r = ctx.rng('spend', i)
        gold = r.choice(golds + [r.randrange(1 << 32), r.randrange(100000), r.randrange(100000)])
        amt = r.choice([0, 1, gold, gold - 1, gold + 1, r.randrange(0, gold + 2), 0xffffffff, 0x80000000,
                        0x7fffffff, r.randrange(1 << 32), r.randrange(5000)]) & 0xffffffff
        c = ctx.case('spend.%d' % i, fn, conv='c', ret='v')
        c.set(e.G + S_GOLD, u32(gold))
        c.arg(amt)
        c.cap(e.G + S_GOLD, 4, 'gold')
        c.note(gold=gold, amount=amt)


def t_addgold(ctx, e):
    fn = ctx.fn(0x0051bea0)
    for i in range(ctx.n(220)):
        r = ctx.rng('addgold', i)
        gold = r.choice([0, 1, 5000, 0x7fffffff, 0xffffffff, 0xfffffff0, r.randrange(1 << 32), r.randrange(200000)])
        lvl = r.choice([0, 1, 2, 5, 10, 20, 30, 40, 0x2d, 0x2e, 0x2f, 0x30, 0x31, 100, 0x7fffffff, -1, -2, -3,
                        r.randrange(0x2f), r.randrange(0x2f)])
        amt = r.choice([0, 1, -1, 7, 100, -100, 0x7fffffff, -0x80000000, r.randint(-100000, 100000),
                        r.randint(0, 5000)])
        c = ctx.case('addgold.%d' % i, fn, conv='c', ret='v')
        c.set(e.G + S_GOLD, u32(gold))
        c.set(e.G + S_LEVEL, u32(lvl))
        if -3 <= lvl < 0x2f:
            c.set(e.G + S_PROGRESS + lvl * 0x21 + 9,
                  u32(r.choice([0, 1, 0xffffffff, r.randrange(1 << 32), r.randrange(100000)])))
        c.arg(amt)
        c.arg(0)  # announce: notice + ChaChing sound, not tested
        c.cap(e.G + S_GOLD, 4, 'gold')
        c.cap(e.G + S_LEVEL, S_PROGRESS_END - S_LEVEL, 'progress')
        c.note(gold=gold, level=lvl, amount=amt)


# ----------------------------------------------------------------------------- locating items

def t_find_at(ctx, e):
    fn = ctx.fn(0x00522180)
    edges = [(0, 8), (1, 12), (2, 500), (3, 0), (3, 5), (0x7f, 0), (0x80, 0), (0xff, 0), (0xff, 3),
             (0xfe, 7), (0x100, 3), (0x101, 0x10005), (0x102, 0x30007), (0, 0xffff), (1, 0x8000), (2, 0xfff0)]
    # (1, 0x8000) -> EquippedItem[-32768] and (2, 0xfff0) -> party_item_pool[-16] point outside
    # anything the case controls (heap below the Char array, globals before g_status, laid out
    # differently in the two exes): only their asserts are compared, not the 32 bytes returned.
    wild = {(1, 0x8000), (2, 0xfff0)}
    for i in range(ctx.n(260)):
        r = ctx.rng('findat', i)
        if i < len(edges) and edges[i] in wild:
            c = ctx.case('findat.%d' % i, fn, conv='c', ret='v')
        else:
            c = ctx.case('findat.%d' % i, fn, conv='c', ret='p', out='p')
        ctx.set_party(c, r)
        slot = r.randrange(8)
        c.setb(e.char(slot) + EQ, PATTERN_ITEMS)
        c.setb(e.pool(0), PATTERN_POOL)
        c.set(e.G + S_TEXT_A, bytes(0x20))  # read by the 32-byte view of pool[499]/pool[500]
        k = r.random()
        if i < len(edges):
            origin, idx = edges[i]
        elif k < 0.3:
            origin, idx = 0, r.randrange(8)
        elif k < 0.6:
            origin, idx = 1, r.randrange(12)
        else:
            origin, idx = 2, r.choice([0, 1, 498, 499, r.randrange(500), r.randrange(500), r.randrange(500)])
        c.arg(slot)
        c.arg(origin)
        c.arg(idx)
        c.note(slot=slot, origin=origin, index=idx)


def t_origin(ctx, e):
    fn = ctx.fn(0x005222d0)
    for i in range(ctx.n(260)):
        r = ctx.rng('origin', i)
        c = ctx.case('origin.%d' % i, fn, conv='c', ret='v')
        count = r.choice([0, 1, 2, 5, 37, 100, 499, 500, 501, 777, 1000, r.randrange(500)])
        c.set(e.G + S_COUNT, u32(count))
        ci = r.choice(list(range(8)) * 3 + [-1, 8, 9, 12])
        cs = ci if r.random() < 0.8 else r.randrange(8)
        k = r.random()
        if k < 0.25:
            j = r.randrange(8)
            ptr, what = e.bp(cs, j), 'bp%d.%d' % (cs, j)
        elif k < 0.5:
            j = r.randrange(12)
            ptr, what = e.eq(cs, j), 'eq%d.%d' % (cs, j)
        elif k < 0.75:
            pk = r.choice([0, 1, count - 1, count, count + 1, r.randrange(max(1, count)), 499, 500, 600, 999])
            ptr, what = e.pool(pk), 'pool%d' % pk
        else:
            choices = [(e.char(cs) + BP - IT, 'bp-1'), (e.char(cs) + BP + 8 * IT, 'bp8'),
                       (e.char(cs) + EQ - IT, 'eq-1'), (e.eq(cs, 12), 'eq12'), (e.eq(cs, 0) + 1, 'eq0+1'),
                       (e.bp(cs, 3) + 6, 'bp3+6'), (e.G + S_HAND, 'hand'), (e.pool(0) - IT, 'pool-1'),
                       (e.pool(5) + 4, 'pool5+4'), (ctx.scratch(1), 'scratch'), (0, 'null')]
            ptr, what = r.choice(choices)
        c.fill(ctx.scratch(0), 16, 0xaa)
        c.arg(ci)
        c.arg(ptr)
        c.arg(ctx.scratch(0))
        c.arg(ctx.scratch(0) + 4)
        c.cap(ctx.scratch(0), 16, 'out')
        c.note(char_index=ci, item=what, count=count)


def t_worn_carried(ctx, e):
    for tag, addr, n in (('worn', 0x00520f20, 160), ('carried', 0x00520f60, 140)):
        fn = ctx.fn(addr)
        for i in range(ctx.n(n)):
            r = ctx.rng(tag, i)
            s = r.randrange(8)
            cptr, cwhat = r.choice([(e.char(s), 'char%d' % s)] * 8 + [(0, 'null'), (ctx.scratch(1), 'scratch')])
            k = r.random()
            if k < 0.45:
                j = r.randrange(-2, 14)
                ptr, what = e.eq(s, j), 'eq%d' % j
            elif k < 0.8:
                j = r.randrange(-2, 10)
                ptr, what = e.bp(s, j), 'bp%d' % j
            else:
                j = r.randrange(12)
                ptr, what = r.choice([(e.eq(s, j) + r.randrange(1, 12), 'eq%d+x' % j),
                                      (e.eq((s + 1) % 8, j), 'other.eq%d' % j),
                                      (e.bp((s + 1) % 8, j % 8), 'other.bp%d' % (j % 8)),
                                      (0, 'null'),
                                      (ctx.scratch(1) + EQ + IT * j, 'scratch.eq%d' % j),
                                      (ctx.scratch(1) + BP + IT * (j % 8), 'scratch.bp%d' % (j % 8))])
            c = ctx.case('%s.%d' % (tag, i), fn, conv='c', ret='b')
            c.arg(cptr)
            c.arg(ptr)
            c.note(char=cwhat, item=what)


# ----------------------------------------------------------------------------- record helpers

def t_count_usable(ctx, e):
    fn = ctx.fn(0x0051f870)

    def pick(r):
        k = r.random()
        if k < 0.15:
            return item(-1)
        if k < 0.2:
            iid = 0x29f
        elif k < 0.55:
            iid = r.choice(L.spell)
        elif k < 0.75:
            iid = r.choice(L.charged)
        else:
            iid = r.choice(L.all)
        st, us = rand_qty(r, iid)
        return item(iid, st, us, r.random() < 0.7, 0, 1, r.random() < 0.3)

    for i in range(ctx.n(300)):
        r = ctx.rng('usable', i)
        c = ctx.case('usable.%d' % i, fn, conv='c', ret='i')
        party = ctx.set_party(c, r)
        s = r.randrange(8)
        _, blob, name = party[s]
        eq, bp = items_of(blob)
        if r.random() < 0.85:
            eq = [pick(r) if r.random() < 0.6 else x for x in eq]
            bp = [pick(r) if r.random() < 0.6 else x for x in bp]
        put_items(e, c, s, blob, eq, bp)
        cnt = items_count_value(r) if r.random() < 0.15 else NITEMS
        c.set(e.X + X_ITEMS, u32(cnt))
        c.arg(e.char(s))
        c.cap(e.char(s), CHAR, 'char')
        c.note(char=name, slot=s, items_in_db=cnt)


def t_class_normalizes(ctx, e):
    fn = ctx.fn(0x005207c0)
    for cls in range(min(256, ctx.n(256))):
        c = ctx.case('normcls.%d' % cls, fn, conv='c', ret='b')
        c.set(ctx.scratch(0) + 0x3e, bytes([cls]))
        c.arg(ctx.scratch(0))
        c.note(equip_class=cls)
    for i in range(ctx.n(100)):
        r = ctx.rng('normrec', i)
        iid = r.choice(L.all)
        c = ctx.case('normrec.%d' % i, fn, conv='c', ret='b')
        c.arg(e.rec(iid))
        c.note(item=iid, equip_class=EQC[iid])


def t_hidden(ctx, e):
    fn = ctx.fn(0x00520750)
    for iid in range(min(NITEMS, ctx.n(NITEMS))):
        c = ctx.case('hidden.%d' % iid, fn, conv='c', ret='b')
        c.arg(iid)


def t_replace_create(ctx, e):
    fn = ctx.fn(0x0051c020)
    for i in range(ctx.n(300)):
        r = ctx.rng('create', i)
        c = ctx.case('create.%d' % i, fn, conv='c', ret='v')
        iid = r.choice(L.all + L.stack + L.charged + [0, NITEMS - 1])
        c.set(ctx.scratch(0), bytes(r.randrange(256) for _ in range(IT)))
        cnt = items_count_value(r, iid) if r.random() < 0.12 else NITEMS
        c.set(e.X + X_ITEMS, u32(cnt))
        flags = [r.choice([0, 1, 1, 0x100, 0x201]) if r.random() < 0.1 else r.randrange(2) for _ in range(3)]
        c.arg(ctx.scratch(0))
        c.arg(iid)
        for f in flags:
            c.arg(f)
        c.cap(ctx.scratch(0), IT, 'item')
        c.note(item=iid, qk=QK[iid], flags=flags, items_in_db=cnt)
    for i in range(ctx.n(80)):
        r = ctx.rng('create_pool', i)
        c = ctx.case('create_pool.%d' % i, fn, conv='c', ret='v')
        setup_party(e, c, r)
        n = r.choice([1, 2, 3, 5, 10, 30])
        set_pool(e, c, [rand_item(r, L.safe) for _ in range(n)])
        k = r.choice([0, n - 1, r.randrange(n), n])
        iid = r.choice(L.all)
        c.arg(e.pool(k))
        c.arg(iid)
        for _ in range(3):
            c.arg(r.randrange(2))
        cap_world(e, c, text=False, rows=False)
        c.note(pool=n, slot=k, item=iid)


def t_bind_equipped(ctx, e):
    fn = ctx.fn(0x0051d0d0)
    for i in range(ctx.n(240)):
        r = ctx.rng('bindeq', i)
        c = ctx.case('bindeq.%d' % i, fn, conv='c', ret='v')
        s = r.randrange(8)
        blob, name = ctx.pick_char(r)
        c.setb(e.char(s), bytes(blob))
        k = r.randrange(12)
        if r.random() < 0.12:
            it = item(-1, r.randrange(3), 0, r.randrange(2), 0, 0, 0, r.randrange(2), r.randrange(2))
        else:
            iid = r.choice(L.bind) if r.random() < 0.6 else r.choice(L.all)
            bann = r.random() < 0.4
            bound = r.random() < 0.4
            notice = BIND[iid] and not bann and not bound and k not in ICON_NONE_SLOTS
            if notice and r.random() < 0.6:  # keep the announcing path to a minority
                bann = True
            st, us = rand_qty(r, iid)
            it = item(iid, st, us, r.random() < 0.7, 0, 0, r.random() < 0.2, bann, bound)
        c.set(e.eq(s, k), it)
        c.arg(e.char(s))
        c.arg(k)
        c.cap(e.char(s), CHAR, 'char')
        c.note(char=name, slot=s, equip_slot=k, item=iid_of(it))


def t_item_spell(ctx, e):
    for tag, addr in (('spell', 0x00520880), ('range', 0x005207e0)):
        fn = ctx.fn(addr)
        for i in range(ctx.n(250)):
            r = ctx.rng(tag, i)
            c = ctx.case('%s.%d' % (tag, i), fn, conv='c', ret='i')
            if i < 2:
                c.arg(0)
                c.note(item='null')
                continue
            iid = r.choice(L.spell * 2 + L.all)
            st, us = rand_qty(r, iid)
            c.set(ctx.scratch(0), item(iid, st, us, r.randrange(2), r.randrange(2)))
            cnt = items_count_value(r, iid) if r.random() < 0.2 else NITEMS
            c.set(e.X + X_ITEMS, u32(cnt))
            c.arg(ctx.scratch(0))
            c.note(item=iid, spell=SPELL[iid], items_in_db=cnt)


# ----------------------------------------------------------------------------- identification

LEVELS = [0, 1, 5, 6, 11, 12, 17, 18, 23, 24, 29, 30, 35, 36, 41, 42, 47, 48, 53, 54, 59, 60, 66, 72, 78,
          90, 100, 108, 114, 120, 125]
STRENGTHS = [0, 1, 2, 3, 4, 5, 6, 7, 10, 20, 21, 100, 0x55555555, 0x55555556, 0x7fffffff, 0x80000000,
             0xffffffff]
PERCENTS = [0, 1, 9, 10, 33, 50, 99, 100, 101, 150, 200, 1000, 0x147ae14, 0x147ae15, 0x4444444,
            0x7fffffff, 0x80000000, 0xffffffff]


def tweak_identifier(e, c, r, s, weird):
    lvl = r.choice(LEVELS + [r.randrange(126)])
    if weird and r.random() < 0.25:
        lvl = r.choice([767, 768, 1535, 1536, 0x7fffffff, 0x80000000, 0xffffffff])
    c.set(e.char(s) + SK + SK_LEVEL, u32(lvl))
    if r.random() < 0.6:
        c.set(e.char(s) + SK + SK_PRACTICE, u32(r.choice([0, 6, 7, 7, 8])))
        c.set(e.char(s) + SK + SK_POINTS, u32(r.choice([0, 10, 50, 98, 99, 100, 101])))
        c.set(e.char(s) + SK + SK_BASE, u32(r.choice([0, 10, 30, 60, 100, 150])))
    if r.random() < 0.25:
        c.set(e.char(s) + SK + SK_ACTIVE, bytes([r.randrange(2)]))
    hp = None
    if r.random() < 0.12:
        hp = 0
        c.set(e.char(s) + C_HP, u32(0))
    hc = r.choice([0] * 8 + [1, 5, 10, 11, 12, 17, 18, 19])
    if weird and r.random() < 0.1:
        hc = r.choice([0xffffffff, 0x80000000, 0x7fffffff])
    c.set(e.char(s) + C_HC, u32(hc))
    return {'lvl': lvl, 'hc': hc, 'hp0': hp == 0}


def t_identify(ctx, e):
    fn_party = ctx.fn(0x005209f0)
    fn_try = ctx.fn(0x005208f0)
    for i in range(ctx.n(260)):
        r = ctx.rng('partyid', i)
        c = ctx.case('partyid.%d' % i, fn_party, conv='c', ret='b')
        party, occ = setup_party(e, c, r, occ=[int(r.random() < 0.85) for _ in range(8)])
        tw = [tweak_identifier(e, c, r, s, i % 5 == 0) for s in range(8)]
        iid = r.choice(L.all)
        ident = r.random() < 0.15
        c.set(ctx.scratch(0), item(iid, *rand_qty(r, iid), ident, r.randrange(2), 0, 0, r.randrange(2), r.randrange(2)))
        c.arg(ctx.scratch(0))
        c.arg(r.choice([0, 1, r.randrange(1 << 32)]))
        c.cap(ctx.scratch(0), IT, 'item')
        cap_world(e, c, text=True)
        c.note(item=iid, difficulty=IDD[iid], identified=ident, occ=occ, levels=[t['lvl'] for t in tw])
    for i in range(ctx.n(320)):
        r = ctx.rng('tryid', i)
        c = ctx.case('tryid.%d' % i, fn_try, conv='c', ret='b')
        party, occ = setup_party(e, c, r)
        s = r.randrange(8)
        tw = tweak_identifier(e, c, r, s, i % 4 == 0)
        iid = r.choice(L.all)
        c.set(ctx.scratch(0), item(iid, *rand_qty(r, iid), r.random() < 0.15, r.randrange(2), 0, 0, r.randrange(2),
                                   r.randrange(2)))
        c.arg(e.char(s))
        c.arg(ctx.scratch(0))
        c.cap(ctx.scratch(0), IT, 'item')
        cap_world(e, c, text=True)
        c.note(item=iid, difficulty=IDD[iid], slot=s, **tw)


def t_apply_identify(ctx, e):
    fn = ctx.fn(0x00520b40)
    for i in range(ctx.n(350)):
        r = ctx.rng('applyid', i)
        c = ctx.case('applyid.%d' % i, fn, conv='c', ret='v')
        iid = r.choice(L.all)
        c.set(ctx.scratch(0), item(iid, r.randrange(4), r.randrange(4), r.randrange(2), r.randrange(2),
                                   r.randrange(3), r.randrange(2), r.randrange(2), r.randrange(2)))
        strength = r.choice(STRENGTHS + [r.randrange(25), r.randrange(25), r.randrange(1 << 32)])
        pct = r.choice(PERCENTS + [r.randrange(300), r.randrange(1 << 32)])
        c.arg(ctx.scratch(0))
        c.arg(strength)
        c.arg(pct)
        c.cap(ctx.scratch(0), IT, 'item')
        c.note(item=iid, difficulty=IDD[iid], strength=strength, percent=pct)


def t_attempts_needed(ctx, e):
    fn = ctx.fn(0x00520a70)
    for i in range(ctx.n(320)):
        r = ctx.rng('attempts', i)
        c = ctx.case('attempts.%d' % i, fn, conv='c', ret='i')
        iid = r.choice(L.all + [-1] * 12)
        c.set(ctx.scratch(0), item(iid, r.randrange(3), r.randrange(3), r.randrange(2)))
        pct = r.choice(PERCENTS + [r.randrange(300), r.randrange(300), r.randrange(1 << 32)])
        c.arg(ctx.scratch(0))
        c.arg(pct)
        c.cap(ctx.scratch(0), IT, 'item')
        c.note(item=iid, difficulty=IDD[iid] if iid >= 0 else None, percent=pct)


def t_reveal_bindings(ctx, e):
    fn = ctx.fn(0x00520bc0)
    for i in range(ctx.n(300)):
        r = ctx.rng('reveal', i)
        c = ctx.case('reveal.%d' % i, fn, conv='c', ret='i')
        s = r.randrange(8)
        blob, name = ctx.pick_char(r)
        blob = type(blob)(blob)
        c.setb(e.char(s), bytes(blob))
        eq, bp = items_of(blob)
        pb = r.choice([0.0, 0.2, 0.5, 0.8])
        for k in range(12):
            x = r.random()
            if x < pb:
                eq[k] = item(r.choice(L.bind), 0, 0, r.randrange(2), 0, 0, 0, r.random() < 0.3, r.randrange(2))
            elif x < pb + 0.15:
                eq[k] = item(-1)
            elif x < pb + 0.4:
                eq[k] = rand_item(r, L.all)
        put_items(e, c, s, blob, eq, bp)
        strength = r.choice([0, 1, 2, 3, 4, 5, 7, 10, 20, -1, -2, 0x55555556, 0x7fffffff, -0x80000000,
                             r.randrange(25)])
        pct = r.choice(PERCENTS + [r.randrange(300)])
        c.arg(s)
        c.arg(strength)
        c.arg(pct)
        c.cap(e.char(s), CHAR, 'char')
        c.note(char=name, slot=s, strength=strength, percent=pct)


# ----------------------------------------------------------------------------- uses and stacks

def t_add_uses(ctx, e):
    fn = ctx.fn(0x0051e920)
    for i in range(ctx.n(350)):
        r = ctx.rng('adduses', i)
        c = ctx.case('adduses.%d' % i, fn, conv='c', ret='v')
        iid = r.choice(L.charged * 3 + L.all)
        m = DMAX[iid]
        cur = r.choice([0, 1, m - 1, m, m + 1, 0xff, 0x80, 0x7f, r.randrange(256)]) & 0xff
        uses = r.choice([0, 1, -1, 2, -2, 5, 127, -128, m - cur, r.randint(-128, 127)])
        arg = uses & 0xffffffff if uses < 0 else uses & 0xff
        if r.random() < 0.1:
            arg = (r.randrange(1 << 24) << 8) | (uses & 0xff)
        c.set(ctx.scratch(0), item(iid, r.randrange(4), cur, r.randrange(2)))
        c.arg(ctx.scratch(0))
        c.arg(arg)
        c.cap(ctx.scratch(0), IT, 'item')
        c.note(item=iid, max=m, uses=cur, add=uses)


def qty_for(r, iid, room_hint=None):
    """(stack, uses) around the record's limits, including impossible ones."""
    if QK[iid] == 1:
        m = QMAX[iid]
        st = r.choice([0, 1, max(0, m - 1), m, m + 1, 2 * m, 255, r.randrange(256), r.randint(0, m)]) & 0xff
        us = r.choice([0] * 6 + [1, 3, 255])
        return st, us
    m = DMAX[iid]
    us = r.choice([0, 1, max(0, m - 1), m, m + 1, 255, r.randint(0, max(1, m))]) & 0xff
    st = r.choice([0] * 6 + [1, 4, 255])
    return st, us


def t_merge_uses(ctx, e):
    fn = ctx.fn(0x0051e9f0)
    for i in range(ctx.n(260)):
        r = ctx.rng('mergeuses', i)
        c = ctx.case('mergeuses.%d' % i, fn, conv='c', ret='v')
        party, occ = setup_party(e, c, r, occ=[1] * 8)
        s = r.randrange(8)
        k = r.random()
        into_id = r.choice(L.charged * 3 + L.stack + L.plain)
        from_id = into_id if r.random() < 0.5 else r.choice(L.charged + L.stack)
        a = item(into_id, *qty_for(r, into_id), r.randrange(2))
        b = item(from_id, *qty_for(r, from_id), r.randrange(2))
        pool = []
        if k < 0.6:
            into_p, from_p, mode = ctx.scratch(0), ctx.scratch(0) + IT, 'scratch'
            c.set(ctx.scratch(0), a + b)
        elif k < 0.85:
            _, blob, _ = party[s]
            eq, bp = items_of(blob)
            j1, j2 = r.sample(range(8), 2)
            if r.random() < 0.5:
                eq[j1] = a
                into_p = e.eq(s, j1)
            else:
                bp[j1] = a
                into_p = e.bp(s, j1)
            bp[j2] = b
            from_p, mode = e.bp(s, j2), 'char'
            put_items(e, c, s, blob, sanitize(r, eq), sanitize(r, bp))
        else:
            pool = [rand_item(r, L.safe) for _ in range(r.choice([2, 5, 12]))]
            pk = r.randrange(len(pool))
            pool[pk] = b
            into_p, from_p, mode = ctx.scratch(0), e.pool(pk), 'pool%d' % pk
            c.set(ctx.scratch(0), a)
        set_pool(e, c, pool)
        who = e.char(s) if r.random() < 0.9 else 0
        c.arg(who)
        c.arg(into_p)
        c.arg(from_p)
        c.cap(ctx.scratch(0), 2 * IT, 'items')
        cap_world(e, c, text=True)
        c.note(mode=mode, into=into_id, frm=from_id, slot=s, character=bool(who))


def t_merge_stacks(ctx, e):
    fn = ctx.fn(0x0051f900)
    full = full_pool()
    for i in range(ctx.n(400)):
        r = ctx.rng('mergestk', i)
        c = ctx.case('mergestk.%d' % i, fn, conv='c', ret='b')
        setup_party(e, c, r)
        x = r.random()
        if x < 0.06:
            c.setb(e.pool(0), full)
            npool = 500
        elif x < 0.1:
            c.setb(e.pool(0), full)
            c.set(e.G + S_COUNT, u32(499))
            npool = 499
        else:
            npool = r.choice([0, 0, 1, 3, 8, 20])
            set_pool(e, c, [rand_item(r, L.safe) for _ in range(npool)])
        y = r.random()
        if y < 0.75:
            did = r.choice(L.stack)
        elif y < 0.85:
            did = r.choice(L.charged)
        elif y < 0.95:
            did = r.choice(L.plain)
        else:
            did = -1
        dst, dus = qty_for(r, did) if did >= 0 else (r.randrange(3), 0)
        sid = did if (did >= 0 and r.random() < 0.75) else r.choice(L.stack)
        m = QMAX[did] if did >= 0 else 0
        room = max(0, m - dst)
        sst = r.choice([0, 1, m, room, room + 1, max(0, room - 1), 255, r.randrange(256)]) & 0xff
        dident = r.randrange(2)
        sident = dident if r.random() < 0.8 else 1 - dident
        d = item(did, dst, dus, dident, r.randrange(2), 0, r.randrange(2), r.randrange(2), r.randrange(2))
        s_ = item(sid, sst, r.choice([0, 0, 0, 2]), sident, r.randrange(2), 0, r.randrange(2), r.randrange(2),
                  r.randrange(2))
        z = r.random()
        if z < 0.8 or npool < 2 or npool >= 499:
            c.set(ctx.scratch(0), d + s_)
            dp, sp, mode = ctx.scratch(0), ctx.scratch(0) + IT, 'scratch'
        elif z < 0.9:
            pk = r.randrange(npool)
            c.set(ctx.scratch(0), d)
            c.set(e.pool(pk), s_)
            dp, sp, mode = ctx.scratch(0), e.pool(pk), 'src.pool%d' % pk
        else:
            pk = r.randrange(npool)
            c.set(ctx.scratch(0) + IT, s_)
            c.set(e.pool(pk), d)
            dp, sp, mode = e.pool(pk), ctx.scratch(0) + IT, 'dst.pool%d' % pk
        partial = ctx.scratch(0) + 0x20 if r.random() < 0.7 else 0
        c.arg(dp)
        c.arg(sp)
        c.arg(partial)
        c.cap(ctx.scratch(0), 0x24, 'items')
        cap_world(e, c, text=False)
        c.note(mode=mode, dst=did, dst_stack=dst, src=sid, src_stack=sst, max=m, pool=npool)


def t_copy_item(ctx, e):
    fn = ctx.fn(0x0051fe30)
    for i in range(ctx.n(300)):
        r = ctx.rng('copyitem', i)
        c = ctx.case('copyitem.%d' % i, fn, conv='c', ret='v')
        party, occ = setup_party(e, c, r)
        s = r.randrange(6)
        _, blob, _ = party[s]
        eq, bp = items_of(blob)
        eq, bp = sanitize(r, eq), sanitize(r, bp)
        npool = r.choice([0, 2, 6, 15])
        pool = [rand_item(r, L.safe) for _ in range(npool)]
        who = e.char(s)
        k = r.random()
        if k < 0.3:
            a = rand_item(r, L.safe) if r.random() < 0.1 else EMPTY
            b = rand_item(r, L.safe) if r.random() < 0.93 else EMPTY
            c.set(ctx.scratch(0), a + b)
            dp, sp, mode = ctx.scratch(0), ctx.scratch(0) + IT, 'scratch'
            who = r.choice([0, 0, e.char(s)])
        elif k < 0.65:
            j = r.randrange(12)
            jb = r.randrange(8)
            if r.random() < 0.5:
                bp[jb] = rand_item(r, L.hand if j in (6, 7) and r.random() < 0.7 else L.safe)
                eq[j] = EMPTY if r.random() < 0.95 else eq[j]
                dp, sp, mode = e.eq(s, j), e.bp(s, jb), 'bp%d->eq%d' % (jb, j)
            else:
                eq[j] = rand_item(r, L.safe) if eq[j] == EMPTY or r.random() < 0.5 else eq[j]
                bp[jb] = EMPTY if r.random() < 0.95 else bp[jb]
                dp, sp, mode = e.bp(s, jb), e.eq(s, j), 'eq%d->bp%d' % (j, jb)
            who = r.choice([e.char(s)] * 4 + [0, e.char((s + 1) % 6)])
        elif k < 0.8 and npool:
            pk = r.randrange(npool)
            jb = r.randrange(8)
            bp[jb] = EMPTY
            dp, sp, mode = e.bp(s, jb), e.pool(pk), 'pool%d->bp%d' % (pk, jb)
            who = r.choice([e.char(s), 0])
        elif k < 0.9:
            jb = r.randrange(8)
            bp[jb] = rand_item(r, L.safe)
            c.set(e.pool(npool), EMPTY)
            dp, sp, mode = e.pool(npool), e.bp(s, jb), 'bp%d->pool%d' % (jb, npool)
        else:
            z = r.randrange(3)
            if z == 0:
                c.set(ctx.scratch(0), rand_item(r, L.safe))
                dp, sp, mode = ctx.scratch(0), ctx.scratch(0), 'same'
            elif z == 1:
                c.set(ctx.scratch(0), rand_item(r, L.safe) + rand_item(r, L.safe))
                dp, sp, mode = ctx.scratch(0), ctx.scratch(0) + IT, 'dst.full'
            else:
                c.set(ctx.scratch(0), EMPTY + item(-1, 3, 1, 1, 0, 0, 0, 1, 1))
                dp, sp, mode = ctx.scratch(0), ctx.scratch(0) + IT, 'src.empty'
            who = 0
        put_items(e, c, s, blob, eq, bp)
        set_pool(e, c, pool)
        refresh = r.randrange(2)
        c.arg(dp)
        c.arg(sp)
        c.arg(who)
        c.arg(refresh)
        c.cap(ctx.scratch(0), 2 * IT, 'items')
        cap_world(e, c, text=True)
        c.note(mode=mode, slot=s, refresh=refresh, character=who != 0, pool=npool)


# ----------------------------------------------------------------------------- acquiring items

def target_char_items(r, blob, fill=None):
    eq, bp = items_of(blob)
    eq = sanitize(r, eq)
    for k in range(12):
        x = r.random()
        if x < 0.15:
            eq[k] = EMPTY_QUIET
        elif x < 0.3:
            eq[k] = rand_item(r, L.stack if r.random() < 0.6 else L.safe, eff=1)
    nfill = r.choice([0, 1, 3, 5, 7, 8, 8]) if fill is None else fill
    slots = r.sample(range(8), nfill)
    bp = [rand_item(r, L.safe if r.random() < 0.5 else L.stack, eff=1) if k in slots else EMPTY_QUIET
          for k in range(8)]
    return eq, bp


def new_item(r, eq, bp):
    present = [iid_of(x) for x in eq + bp if iid_of(x) >= 0 and iid_of(x) not in PLOT]
    x = r.random()
    if x < 0.4 and present:
        iid = r.choice(present)
    elif x < 0.7:
        iid = r.choice(L.stack)
    else:
        iid = r.choice(L.safe)
    st, us = rand_qty(r, iid)
    if QK[iid] == 1 and r.random() < 0.3:
        st = r.choice([0, QMAX[iid] + 1, 2 * QMAX[iid], 255]) & 0xff
    idf = r.random() < 0.7
    return item(iid, st, us, idf, idf and r.random() < 0.5, int(idf), 1 if r.random() < 0.75 else 0,
                r.random() < 0.15, r.random() < 0.2)


def t_add_to_character(ctx, e):
    fn = ctx.fn(0x0051c300)
    for i in range(ctx.n(300)):
        r = ctx.rng('addchar', i)
        c = ctx.case('addchar.%d' % i, fn, conv='c', ret='b')
        party, occ = setup_party(e, c, r)
        s = r.randrange(8)
        _, blob, name = party[s]
        eq, bp = target_char_items(r, blob)
        put_items(e, c, s, blob, eq, bp)
        npool = r.choice([0, 0, 2, 10])
        set_pool(e, c, [rand_item(r, L.safe) for _ in range(npool)])
        it = new_item(r, eq, bp)
        c.set(ctx.scratch(0), it)
        equip, skip = r.randrange(2), r.choice([0, 0, 1])
        c.arg(e.char(s))
        c.arg(ctx.scratch(0))
        c.arg(equip)
        c.arg(0)  # announce
        c.arg(skip)
        c.cap(ctx.scratch(0), IT, 'item')
        cap_world(e, c, text=True)
        c.note(char=name, slot=s, item=iid_of(it), equip=equip, skip_stacking=skip,
               backpack_free=sum(1 for x in bp if iid_of(x) == -1))


def t_store(ctx, e):
    fn = ctx.fn(0x0051c280)
    full = full_pool()
    for i in range(ctx.n(260)):
        r = ctx.rng('store', i)
        c = ctx.case('store.%d' % i, fn, conv='c', ret='b')
        party, occ = setup_party(e, c, r)
        s = r.randrange(8)
        _, blob, name = party[s]
        eq, bp = target_char_items(r, blob, fill=r.choice([None, 8, 8]))
        put_items(e, c, s, blob, eq, bp)
        x = r.random()
        if x < 0.25:
            c.setb(e.pool(0), full)
            npool = 500
        else:
            npool = r.choice([0, 1, 5, 20])
            set_pool(e, c, [rand_item(r, L.safe) for _ in range(npool)])
        it = new_item(r, eq, bp)
        c.set(ctx.scratch(0), it)
        party_first, equip = r.randrange(2), r.randrange(2)
        c.arg(e.char(s))
        c.arg(ctx.scratch(0))
        c.arg(party_first)
        c.arg(0)  # announce
        c.arg(equip)
        c.cap(ctx.scratch(0), IT, 'item')
        cap_world(e, c, text=True)
        c.note(char=name, slot=s, item=iid_of(it), party_first=party_first, equip=equip, pool=npool)


def t_give(ctx, e):
    fn = ctx.fn(0x0051bc00)
    full = full_pool()
    for i in range(ctx.n(150)):
        r = ctx.rng('give', i)
        c = ctx.case('give.%d' % i, fn, conv='c', ret='b')
        party, occ = setup_party(e, c, r, occ=[int(r.random() < 0.8) for _ in range(8)])
        if r.random() < 0.05:
            c.set(e.G + S_STARTED, b'\x00')
        u = r.randrange(8)
        _, blob, name = party[u]
        eq, bp = target_char_items(r, blob, fill=r.choice([None, 8]))
        put_items(e, c, u, blob, eq, bp)
        if r.random() < 0.15:
            c.set(e.char(u) + C_HP, u32(0))
        hc = r.choice([0] * 6 + [5, 11, 15, 16, 17, 18])
        c.set(e.char(u) + C_HC, u32(hc))
        if r.random() < 0.2:
            c.setb(e.pool(0), full)
            npool = 500
        else:
            npool = r.choice([0, 3, 12])
            set_pool(e, c, [rand_item(r, L.safe) for _ in range(npool)])
        it = new_item(r, eq, bp)
        c.set(ctx.scratch(0), it)
        pf = r.randrange(2)
        c.arg(u)
        c.arg(ctx.scratch(0))
        c.arg(pf)
        c.cap(ctx.scratch(0), IT, 'item')
        cap_world(e, c, text=True)
        c.note(slot=u, occupied=occ[u], hc=hc, item=iid_of(it), party_first=pf, pool=npool)


def t_stash(ctx, e):
    fn = ctx.fn(0x005223a0)
    for i in range(ctx.n(180)):
        r = ctx.rng('stash', i)
        c = ctx.case('stash.%d' % i, fn, conv='c', ret='v')
        party, occ = setup_party(e, c, r)
        s = r.randrange(8)
        _, blob, name = party[s]
        dead = r.random() < 0.2
        c.set(e.char(s) + C_DEAD, u32(r.choice([1, 0xffffffff, 30]) if dead else 0))
        eq = []
        for k in range(12):
            x = r.random()
            if x < 0.2:
                eq.append(EMPTY)
            elif x < 0.5:
                eq.append(item(r.choice(L.bind), 0, 0, r.randrange(2), 0, 0, 1, r.random() < 0.4, r.randrange(2)))
            else:
                eq.append(rand_item(r, L.safe, eff=1))
        bp = [rand_item(r, L.safe, eff=1) if r.random() < 0.6 else EMPTY for _ in range(8)]
        for k in range(8):  # an equipment row that stays forces the backpack row through the pool
            iid = iid_of(eq[k])
            stays = iid != -1 and BIND[iid] and not eq[k][10] and k not in ICON_NONE_SLOTS and not dead
            if stays and iid_of(bp[k]) == -1:
                bp[k] = rand_item(r, L.safe, eff=1)
        put_items(e, c, s, blob, eq, bp)
        npool = r.choice([0, 0, 1, 4, 30, 470])
        set_pool(e, c, [rand_item(r, L.safe, eff=1) for _ in range(npool)])
        c.arg(e.char(s))
        cap_world(e, c, text=True)
        c.note(char=name, slot=s, dead=dead, pool=npool)


# ----------------------------------------------------------------------------- partner items, binding

def t_equip_partner(ctx, e):
    fn = ctx.fn(0x0051eb90)
    for i in range(ctx.n(200)):
        r = ctx.rng('partner', i)
        c = ctx.case('partner.%d' % i, fn, conv='c', ret='v')
        party, occ = setup_party(e, c, r)
        s = r.randrange(6)
        _, blob, name = party[s]
        eq, bp = items_of(blob)
        eq, bp = sanitize(r, eq), sanitize(r, bp)
        w = r.choice(L.ranged) if r.random() < 0.85 else r.choice(L.safe)
        wit = item(w, *rand_qty(r, w), 1, 0, 1, 1)
        place = r.random()
        if place < 0.8:
            eq[6] = wit
            ptr, where = e.eq(s, 6), 'eq6'
        elif place < 0.9:
            j = r.randrange(8)
            bp[j] = wit
            ptr, where = e.bp(s, j), 'bp%d' % j
        else:
            c.set(ctx.scratch(0), wit if r.random() < 0.8 else EMPTY)
            ptr, where = ctx.scratch(0), 'scratch'
        x = r.random()
        if x < 0.4:
            eq[9] = rand_item(r, L.partner, eff=1)
        elif x < 0.6:
            eq[9] = rand_item(r, L.safe, eff=1)
        else:
            eq[9] = EMPTY
        p = r.choice(L.partner)
        if r.random() < 0.6:
            bp[r.randrange(8)] = item(p, *rand_qty(r, p), 1, 0, 1, 1)
        if r.random() < 0.2:
            eq[r.choice([0, 1, 2, 3, 4, 5, 10, 11])] = item(p, *rand_qty(r, p), 1, 0, 1, 1)
        put_items(e, c, s, blob, eq, bp)
        y = r.random()
        pid = p if y < 0.5 else (-1 if y < 0.75 else r.choice(L.safe))
        slot = 7 if r.random() < 0.75 else r.randrange(12)
        c.arg(e.char(s))
        c.arg(ptr)
        c.arg(pid)
        c.arg(slot)
        c.cap(ctx.scratch(0), IT, 'item')
        cap_world(e, c, text=True)
        c.note(char=name, slot=s, weapon=w, where=where, partner=pid, equip_slot=slot)


def t_bind_every(ctx, e):
    fn = ctx.fn(0x0051d230)
    for i in range(ctx.n(110)):
        r = ctx.rng('bindall', i)
        c = ctx.case('bindall.%d' % i, fn, conv='c', ret='v')
        party, occ = setup_party(e, c, r)
        for s in range(8):
            c.set(e.row(s) + R_ITEM_PENDING, bytes([1 if r.random() < 0.15 else 0]))
            if r.random() < 0.5:
                _, blob, _ = party[s]
                eq, bp = items_of(blob)
                eq, bp = sanitize(r, eq), sanitize(r, bp)
                for k in (6, 7, 8, 9):
                    x = r.random()
                    if x < 0.3:
                        eq[k] = EMPTY
                    elif x < 0.45:
                        eq[k] = item(r.choice(L.bind), 0, 0, 1, 0, 1, 1, r.random() < 0.5, r.randrange(2))
                    elif x < 0.8:
                        eq[k] = rand_item(r, L.hand, eff=1)
                put_items(e, c, s, blob, eq, bp)
        cap_world(e, c, text=True)
        c.note(occ=occ)
    for i in range(ctx.n(12)):
        r = ctx.rng('bindall_combat', i)
        c = ctx.case('bindall_combat.%d' % i, fn, conv='c', ret='v')
        setup_party(e, c, r, combat=1)
        c.setp(ctx.g('g_combat_state'), ctx.scratch(3))  # round_active (+1) = 0
        c.set(e.X + X_MOVE, b'\x00')
        cap_world(e, c, text=True)


# ----------------------------------------------------------------------------- searching and counting

def m_find_char(eq_ids, bp_ids, iid, include, resume):
    """Retail FindItemOnCharacter: (result, what lands in *found: 'ptr'/'zero'/None)."""
    start = 0 if resume is None else (resume[1] + 1 if resume[0] == 'eq' else 12)
    for k in range(start, 12):
        if eq_ids[k] == iid:
            return True, 'ptr'
    if include & 0xffffffff == 0:
        return False, None
    start = 0 if resume is None else (resume[1] + 1 if resume[0] == 'bp' else 8)
    for k in range(start, 8):
        if bp_ids[k] == iid:
            return True, 'ptr'
    return False, 'zero'


def char_resume(e, ctx, r, s):
    x = r.random()
    if x < 0.5:
        return None, 0, 'none'
    if x < 0.7:
        k = r.randrange(12)
        return ('eq', k), e.eq(s, k), 'eq%d' % k
    if x < 0.9:
        k = r.randrange(8)
        return ('bp', k), e.bp(s, k), 'bp%d' % k
    p, w = r.choice([(ctx.scratch(1), 'scratch'), (e.eq(s, 0) + 1, 'eq0+1'), (e.bp(s, 8), 'bp8'),
                     (e.eq(s, 12), 'eq12'), (e.eq((s + 1) % 8, 2), 'other.eq2')])
    return ('x',), p, w


def inject(r, eq, bp, iid, times):
    eq, bp = list(eq), list(bp)
    for _ in range(times):
        st, us = rand_qty(r, iid)
        it = item(iid, st, us, r.randrange(2), 0, 0, r.randrange(2))
        if r.random() < 0.5:
            eq[r.randrange(12)] = it
        else:
            bp[r.randrange(8)] = it
    return eq, bp


def target_id(r, eq, bp):
    present = [iid_of(x) for x in eq + bp if iid_of(x) != -1]
    x = r.random()
    if x < 0.6 and present:
        return r.choice(present)
    if x < 0.7:
        return -1
    if x < 0.75:
        return -2
    return r.choice(L.all)


def t_find_on_char(ctx, e):
    fn = ctx.fn(0x00520f90)
    for i in range(ctx.n(320)):
        r = ctx.rng('findchar', i)
        c = ctx.case('findchar.%d' % i, fn, conv='c', ret='b')
        s = r.randrange(8)
        blob, name = ctx.pick_char(r)
        c.setb(e.char(s), bytes(blob))
        eq, bp = items_of(blob)
        if r.random() < 0.6:
            eq, bp = inject(r, eq, bp, r.choice(L.all), r.choice([1, 2, 3]))
            put_items(e, c, s, blob, eq, bp)
        iid = target_id(r, eq, bp)
        include = r.choice([0, 1, 1, 2, -1, 0x100])
        resume, rptr, rwhat = char_resume(e, ctx, r, s)
        use_found = r.random() < 0.8
        ok, w = m_find_char([iid_of(x) for x in eq], [iid_of(x) for x in bp], iid, include, resume)
        c.fill(ctx.scratch(0), 8, 0xaa)
        c.arg(e.char(s))
        c.arg(iid)
        c.arg(ctx.scratch(0) if use_found else 0)
        c.arg(include)
        c.arg(rptr)
        c.cap(ctx.scratch(0), 8, 'found', ignore=[0] if (use_found and w == 'ptr') else [])
        c.note(char=name, item=iid, include=include, resume=rwhat, expect=ok)


def t_find_on_party(ctx, e):
    fn = ctx.fn(0x00521060)
    for i in range(ctx.n(320)):
        r = ctx.rng('findparty', i)
        c = ctx.case('findparty.%d' % i, fn, conv='c', ret='b')
        party, occ = setup_party(e, c, r, occ=[int(r.random() < 0.75) for _ in range(8)])
        tgt = r.choice(L.all)
        chars = []
        for s in range(8):
            _, blob, _ = party[s]
            eq, bp = items_of(blob)
            if r.random() < 0.3:
                eq, bp = inject(r, eq, bp, tgt, r.choice([1, 2]))
                put_items(e, c, s, blob, eq, bp)
            chars.append(([iid_of(x) for x in eq], [iid_of(x) for x in bp]))
        cursor = int(r.random() < 0.4)
        hand_id = tgt if r.random() < 0.5 else r.choice(L.all)
        c.set(e.G + S_CURSOR, bytes([cursor]))
        c.set(e.G + S_HAND, item(hand_id, r.randrange(5), 0, 1))
        npool = r.choice([0, 1, 3, 10, 40])
        pool = [rand_item(r, L.all) for _ in range(npool)]
        for _ in range(r.choice([0, 1, 2])):
            if npool:
                pool[r.randrange(npool)] = item(tgt, 1, 0, 1)
        set_pool(e, c, pool)
        pool_ids = [iid_of(x) for x in pool]
        iid = tgt if r.random() < 0.8 else r.choice([-1, hand_id, r.choice(L.all)])
        include = r.choice([0, 1, 2, 2, 3, -1])
        x = r.random()
        if x < 0.45:
            resume, rptr, rw = None, 0, 'none'
        elif x < 0.55:
            resume, rptr, rw = ('hand',), e.G + S_HAND, 'hand'
        elif x < 0.7:
            s, k = r.randrange(8), r.randrange(12)
            resume, rptr, rw = ('eq', s, k), e.eq(s, k), 'eq%d.%d' % (s, k)
        elif x < 0.8:
            s, k = r.randrange(8), r.randrange(8)
            resume, rptr, rw = ('bp', s, k), e.bp(s, k), 'bp%d.%d' % (s, k)
        elif x < 0.95:
            k = r.choice([0, max(0, npool - 1), npool, r.randrange(max(1, npool))])
            resume, rptr, rw = ('pool', k), e.pool(k), 'pool%d' % k
        else:
            resume, rptr, rw = ('x',), ctx.scratch(1), 'scratch'
        ok, fw, cw = m_find_party(chars, occ, cursor, hand_id, pool_ids, iid, include, resume)
        use_f, use_c = r.random() < 0.8, r.random() < 0.7
        c.fill(ctx.scratch(0), 8, 0xaa)
        c.arg(iid)
        c.arg(ctx.scratch(0) if use_f else 0)
        c.arg(ctx.scratch(0) + 4 if use_c else 0)
        c.arg(include)
        c.arg(rptr)
        ign = ([0] if use_f and fw == 'ptr' else []) + ([4] if use_c and cw == 'ptr' else [])
        c.cap(ctx.scratch(0), 8, 'found', ignore=ign)
        c.note(item=iid, include=include, resume=rw, cursor=cursor, pool=npool, occ=occ, expect=ok)


def m_find_party(chars, occ, cursor, hand_id, pool_ids, iid, include, resume):
    """Retail FindItemOnParty: (result, *found kind, *found_character kind)."""
    if (resume is None or resume[0] == 'hand') and cursor and hand_id == iid:
        return True, 'ptr', 'zero'
    for s in range(8):
        if not occ[s]:
            continue
        if resume is None:
            rs = None
        elif resume[0] in ('eq', 'bp') and resume[1] == s:
            rs = (resume[0], resume[2])
        else:
            rs = ('x',)
        ok, _ = m_find_char(chars[s][0], chars[s][1], iid, include, rs)
        if ok:
            return True, 'ptr', 'ptr'
    if include & 0xffffffff == 2:
        n = len(pool_ids)
        if resume is None:
            start = 0
        elif resume[0] == 'pool' and resume[1] < n:
            start = resume[1] + 1
        else:
            start = n
        for k in range(start, n):
            if pool_ids[k] == iid:
                return True, 'ptr', 'zero'
    return False, 'zero', 'zero'


def char_count(eq, bp, iid, include):
    total, hit = 0, False
    for k in range(12):
        if iid_of(eq[k]) == iid:
            total += stack_of(eq[k]) or 1
            hit = True
    if include & 0xffffffff:
        for k in range(8):
            if iid_of(bp[k]) == iid:
                total += stack_of(eq[k]) or 1  # retail counts the equipped row of the same index
                hit = True
    return total, hit


def t_count_on_char(ctx, e):
    fn = ctx.fn(0x005211a0)
    for i in range(ctx.n(300)):
        r = ctx.rng('countchar', i)
        c = ctx.case('countchar.%d' % i, fn, conv='c', ret='i')
        s = r.randrange(8)
        blob, name = ctx.pick_char(r)
        c.setb(e.char(s), bytes(blob))
        eq, bp = items_of(blob)
        if r.random() < 0.7:
            eq, bp = inject(r, eq, bp, r.choice(L.stack + L.all), r.choice([1, 2, 3, 4]))
            put_items(e, c, s, blob, eq, bp)
        iid = target_id(r, eq, bp)
        include = r.choice([0, 1, 1, 2, -1])
        total, hit = char_count(eq, bp, iid, include)
        mode = r.choice(['null', 'zero', 'zero', 'set', 'set'])
        preset = 0 if mode != 'set' else r.choice([1, 0x11111111, 0xffffffff])
        c.set(ctx.scratch(0), u32(preset))
        c.arg(e.char(s))
        c.arg(iid)
        c.arg(0 if mode == 'null' else ctx.scratch(0))
        c.arg(include)
        c.cap(ctx.scratch(0), 8, 'first', ignore=[0] if (mode == 'zero' and hit) else [])
        c.note(char=name, item=iid, include=include, first=mode, expect=total)


def t_count_on_party(ctx, e):
    fn = ctx.fn(0x00521240)
    for i in range(ctx.n(300)):
        r = ctx.rng('countparty', i)
        c = ctx.case('countparty.%d' % i, fn, conv='c', ret='i')
        party, occ = setup_party(e, c, r, occ=[int(r.random() < 0.75) for _ in range(8)])
        tgt = r.choice(L.stack + L.all)
        any_char = False
        for s in range(8):
            _, blob, _ = party[s]
            eq, bp = items_of(blob)
            if r.random() < 0.35:
                eq, bp = inject(r, eq, bp, tgt, r.choice([1, 2, 3]))
                put_items(e, c, s, blob, eq, bp)
            if occ[s] and char_count(eq, bp, tgt, 1)[1]:
                any_char = True
        cursor = int(r.random() < 0.4)
        hand_id = tgt if r.random() < 0.5 else r.choice(L.all)
        c.set(e.G + S_CURSOR, bytes([cursor]))
        c.set(e.G + S_HAND, item(hand_id, r.choice([0, 1, 5, 100]), 0, 1))
        npool = r.choice([0, 1, 4, 12, 40])
        pool = [rand_item(r, L.all) for _ in range(npool)]
        for _ in range(r.choice([0, 1, 2, 3])):
            if npool:
                pool[r.randrange(npool)] = item(tgt, r.choice([0, 1, 7]), 0, 1)
        set_pool(e, c, pool)
        include = r.choice([0, 1, 2, 2, 3, -1])
        iid = tgt if r.random() < 0.85 else r.choice([-1, hand_id])
        # which out-pointers end up holding addresses
        chars_hit = False
        for s in range(8):
            _, blob, _ = party[s]
            eq, bp = items_of(blob)
            if occ[s] and char_count(eq, bp, iid, include)[1]:
                chars_hit = True
        hand_hit = bool(cursor) and hand_id == iid
        pool_hit = include & 0xffffffff == 2 and any(iid_of(x) == iid for x in pool)
        use_f, use_h = r.random() < 0.8, r.random() < 0.7
        c.fill(ctx.scratch(0), 8, 0xaa)
        c.arg(iid)
        c.arg(ctx.scratch(0) if use_f else 0)
        c.arg(ctx.scratch(0) + 4 if use_h else 0)
        c.arg(include)
        ign = ([0] if use_f and (hand_hit or chars_hit or pool_hit) else []) + ([4] if use_h and chars_hit else [])
        c.cap(ctx.scratch(0), 8, 'found', ignore=ign)
        c.note(item=iid, include=include, cursor=cursor, pool=npool, occ=occ)


def t_every_has(ctx, e):
    fn = ctx.fn(0x00521360)
    for i in range(ctx.n(250)):
        r = ctx.rng('everyhas', i)
        c = ctx.case('everyhas.%d' % i, fn, conv='c', ret='b')
        party, occ = setup_party(e, c, r, occ=[int(r.random() < 0.8) for _ in range(8)])
        tgt = r.choice(L.all)
        p = r.choice([0.5, 0.9, 1.0])
        for s in range(8):
            _, blob, _ = party[s]
            eq, bp = items_of(blob)
            if r.random() < p:
                eq, bp = inject(r, eq, bp, tgt, 1)
                put_items(e, c, s, blob, eq, bp)
        iid = tgt if r.random() < 0.9 else -1
        include = r.choice([0, 1, 1, 2, -1])
        c.arg(iid)
        c.arg(include)
        c.note(item=iid, include=include, occ=occ)


def t_find_kind(ctx, e):
    fn = ctx.fn(0x005213c0)
    for i in range(ctx.n(300)):
        r = ctx.rng('findkind', i)
        c = ctx.case('findkind.%d' % i, fn, conv='c', ret='b')
        s = r.randrange(8)
        blob, name = ctx.pick_char(r)
        c.setb(e.char(s), bytes(blob))
        eq, bp = items_of(blob)
        if r.random() < 0.5:
            eq, bp = inject(r, eq, bp, r.choice(L.all), r.choice([1, 2]))
            put_items(e, c, s, blob, eq, bp)
        present = [UNI[iid_of(x)] for x in eq + bp if iid_of(x) != -1]
        x = r.random()
        if x < 0.6 and present:
            kind = r.choice(present)
        elif x < 0.85:
            kind = r.randrange(147)
        else:
            kind = r.choice([-1, -2, 0x7fff, 0x8000, 0xffff, 147, 255, 256])
        arg = kind & 0xffff if kind >= 0 else kind & 0xffffffff
        if r.random() < 0.1:
            arg = (r.randrange(1, 1 << 16) << 16) | (kind & 0xffff)
        k16 = arg & 0xffff
        include = r.choice([0, 0, 1, 2, -1])
        use_out = r.random() < 0.8
        hit_eq = any(iid_of(x) != -1 and UNI[iid_of(x)] == k16 for x in eq)
        hit_bp = include != 0 and any(iid_of(x) != -1 and UNI[iid_of(x)] == k16 for x in bp)
        c.fill(ctx.scratch(0), 8, 0xaa)
        c.arg(e.char(s))
        c.arg(arg)
        c.arg(ctx.scratch(0) if use_out else 0)
        c.arg(include)
        c.cap(ctx.scratch(0), 8, 'found', ignore=[0] if (use_out and (hit_eq or hit_bp)) else [])
        c.note(char=name, kind=arg, include=include, expect=hit_eq or hit_bp)


# ----------------------------------------------------------------------------- pool ordering

def t_compare(ctx, e):
    fn = ctx.fn(0x00520600)
    for i in range(ctx.n(400)):
        r = ctx.rng('compare', i)
        c = ctx.case('compare.%d' % i, fn, conv='c', ret='i')
        a = r.choice(L.all)
        k = r.random()
        if k < 0.35:
            b, mode = a, 'same'
        elif k < 0.6:
            b, mode = r.choice(L.group[(EQC[a], UNI[a])]), 'group'
        elif k < 0.8:
            b, mode = r.choice(L.byclass[EQC[a]]), 'class'
        else:
            b, mode = r.choice(L.all), 'any'
        small = [0, 0, 1, 2, 5, 255]
        ia = item(a, r.choice(small), r.choice(small), r.randrange(2), r.randrange(2), 0, r.randrange(2),
                  r.randrange(2), r.randrange(2))
        ib = item(b, r.choice(small), r.choice(small), r.randrange(2), r.randrange(2), 0, r.randrange(2),
                  r.randrange(2), r.randrange(2))
        if r.random() < 0.3:
            ib = ia[:4] + ib[4:6] + ia[6:]
        c.set(ctx.scratch(0), ia + ib)
        c.arg(ctx.scratch(0))
        c.arg(ctx.scratch(0) + IT)
        c.note(a=a, b=b, mode=mode)


def cmp_key(it):
    iid = iid_of(it)
    # retail order: eqc, uni, identified, value (reversed), stack (reversed), uses (reversed)
    return (EQC[iid], UNI[iid], it[6], -val(iid), -it[4], -it[5])


def t_sort_pool(ctx, e):
    fn = ctx.fn(0x005205b0)
    for i in range(ctx.n(130)):
        r = ctx.rng('sortpool', i)
        c = ctx.case('sortpool.%d' % i, fn, conv='c', ret='v')
        n = r.choice([0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 16, 25, 50, 100, 200, 499, 500])
        ties = r.random() < 0.4
        entries, keys = [], set()
        tries = 0
        while len(entries) < n:
            tries += 1
            if ties:
                if entries and r.random() < 0.3:
                    base = r.choice(entries)
                    it = base[:4] + bytes([base[4], base[5], base[6]]) + bytes(r.randrange(2) for _ in range(5))
                else:
                    iid = r.choice(L.all)
                    it = item(iid, r.choice([0, 1, 3]), r.choice([0, 1]), r.random() < 0.4, r.randrange(2), 0,
                              r.randrange(2), r.randrange(2), r.randrange(2))
                entries.append(it)
                continue
            iid = r.choice(L.all)
            it = item(iid, r.randrange(256) if tries > 3 * n else r.choice([0, 1, 2, 3, 10]),
                      r.randrange(256) if tries > 3 * n else r.choice([0, 1, 2]), 1, r.randrange(2), 0,
                      r.randrange(2), r.randrange(2), r.randrange(2))
            key = cmp_key(it)
            if key in keys:
                continue
            keys.add(key)
            entries.append(it)
        started = 0 if r.random() < 0.05 else 1
        set_pool(e, c, entries)
        c.set(e.G + S_STARTED, bytes([started]))
        c.cap(e.pool(0), 500 * IT + 4, 'pool')
        c.note(n=n, ties=ties, started=started)


ALL_TESTS = [t_spend, t_addgold, t_find_at, t_origin, t_worn_carried, t_count_usable, t_class_normalizes,
             t_hidden, t_replace_create, t_bind_equipped, t_item_spell, t_identify, t_apply_identify,
             t_attempts_needed, t_reveal_bindings, t_add_uses, t_merge_uses, t_merge_stacks, t_copy_item,
             t_add_to_character, t_store, t_give, t_stash, t_equip_partner, t_bind_every, t_find_on_char,
             t_find_on_party, t_count_on_char, t_count_on_party, t_every_has, t_find_kind, t_compare,
             t_sort_pool]


def cases(ctx):
    build_lists()
    e = Env(ctx)
    for t in ALL_TESTS:
        t(ctx, e)


# ----------------------------------------------------------------------------- Items.dbs tables
# Per record id (0..818): quantity kind (0x066), maximum_quantity (0x06b), initial_quantity dice
# maximum (0x067), identify_difficulty (0x085), binds_on_equip (0x08c), unidentified_name_index
# (0x03f, all < 256), equip_class (0x03e), flags (0x041), spell_id (0x063), category (0x042) and
# value (0x086, u32 little-endian).
VAL = bytes.fromhex(
    '0f0000001e000000a4010000e8030000c201000034210000230000003c000000550000007800000091000000b80b0000'
    '88130000b20c0000401f000064190000007d00003200000064000000ee020000780500004b0000004100000064000000'
    '461e0000007d00000f000000983a0000050000008038010058020000a00f000070170000204e0000400d03007d000000'
    'a00f0000409c000090010000a00f00004c1d0000a0860100401f0000204e000088130000881300002c010000fa000000'
    '50c30000f0000000bc020000204e000046000000a7030000b80b0000e2040000200300005e1a0000983a0000a8610000'
    '204e000050c3000090d003002800000000000000000000002800000032000000401f0000e8030000a8610000ac0d0000'
    '870000005c440000a86100001400000087000000c4090000b80b00000c000000d6060000a08601000a000000c2010000'
    'e02e0000a8610000b8220000c4090000dc050000b80b0000b9000000d0070000c409000096000000204e0000c2010000'
    '409c0000f00a0000c20100000200000050000000c80000005e010000010000000a0000000200000096000000204e0000'
    '0f00000064000000fa00000058020000d007000077010000e2040000401f00002300000060090000ac0d0000a00f0000'
    '084c010050c3000094110000401f0000204e0000040000000e000000240000004800000096000000c8000000c4090000'
    '0200000028000000870000007d000000fa000000060000005a000000e204000064000000140000002823000041000000'
    '5e0100005e01000050c30000ee0200003a070000ac0d0000881300002823000050c300001d010000e8030000e2040000'
    '0a00000055000000af000000c201000020030000b6030000d007000094110000b20c00000f000000f401000010270000'
    'b82200001400000019000000d00700005802000058020000b80b0000204e000090010000e2040000b80b000010270000'
    '1e00000040060000701700002823000050c300008a020000aa0500000a0000003c000000f00000008403000094110000'
    '0f000000f401000010270000b82200001400000019000000d6060000c4090000f4010000b80b0000204e0000a5000000'
    'be000000c20100007e040000ac0d0000102700001e0000002c01000052030000ee02000053070000db01000091000000'
    '1e0000005e010000a8610000c80000004b0000006b03000088130000c8000000a00f0000bc020000ca0800005e010000'
    '10270000581b000032000000d430000050c30000e204000028230000dc0500008813000054010000580200002c010000'
    '204e0000c20100008403000072060000881300003903000019000000320000004100000045010000581b0000204e0000'
    'e50100005500000010270000a00f00008813000088130000d0070000c409000014050000a086010088130000b80b0000'
    'f401000088130000a00f000088130000e02e00003200000030750000a00f000088130000881300008813000088130000'
    '4c1d00004c1d000068420000401f0000204e0000f4010000fa0000009001000078050000102700001027000010270000'
    '4c1d0000581b0000b03600004c1d0000a8610000a00f000088130000280a000094110000ee020000ee020000ee020000'
    'ee020000e2040000e2040000c4090000d4300000401f0000c800000096000000c80000008813000010270000581b0000'
    '28230000dc050000a00f0000983a00004c1d00009001000090010000c4090000c40900002c0100008813000050c30000'
    '64000000dc050000f4010000a00f0000a861000020030000f401000090010000f4010000000000009600000064000000'
    'fa0000008a02000020030000e8030000460000002c0100009001000020030000c80000009600000046000000c8000000'
    'dc050000fa000000f4010000b0040000200300005e010000bc02000058020000080700005a0000002300000005000000'
    '4b00000026020000c2010000b80b000020030000000000000000000000000000b80b0000dc050000b80b0000dc050000'
    '401f0000a00f0000e8030000e803000010270000409c000010270000007d0000581b0000c8af0000c409000094110000'
    '84030000fa000000c800000026020000c8000000f4010000f4010000900100005e010000f4010000f4010000f4010000'
    'e8030000983a0000204e000010270000983a0000c8af0000c4090000e8030000dc05000058020000ee020000f4010000'
    'dc050000e80300000f0000001900000014000000320000005000000000000000b00400000f0000005e010000b80b0000'
    'fe010000000000000000000000000000d0070000fa000000d00700005e010000fa000000d00700000f000000581b0000'
    'dc05000000000000000000000000000000000000e8030000d0070000e8030000e8030000e8030000e8030000e8030000'
    'e8030000e803000000000000e8030000e8030000e803000000000000e803000000000000000000000000000001000000'
    '000000000100000050c30000000000000000000000000000000000007d00000088130000000000009209000090010000'
    '96000000a8610000e3080000000000005e0100007c1500005a000000c4090000e8030000d0070000d0070000d0070000'
    'd0070000d0070000d0070000d0070000d00700000000000000000000000000008813000001000000e600000028230000'
    '581b0000d6060000d6060000d6060000d6060000409c0000b6030000280a000060ea0000a0860100c2010000ee020000'
    'a086010014000000b900000014000000ee020000401f0000ca080000401f0000ac0d00007017000000000000d0070000'
    'd0070000d0070000a00f0000ac0d0000ac0d0000ac0d000094110000a00f0000a00f0000ac0d0000b80b0000a00f0000'
    'a00f0000ac0d000088130000401f0000401f0000401f000028230000581b0000401f0000401f00002823000028230000'
    '401f0000401f000010270000401f0000581b0000401f0000581b0000803e0000803e00005046000068420000803e0000'
    '803e0000803e0000b0360000581b0000803e0000581b0000803e00009209000000000000684200009001000001000000'
    '000000005802000001000000900100000a000000e803000001000000010000000000000096000000983a000002000000'
    '00000000000000008038010000000000000000000000000000000000000000005802000020030000130100008a020000'
    '0000000000000000fa000000401f0000401f0000fa0000000000000000000000aa03000020030000bc02000000000000'
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000064000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000000009001000088130000000000000000000000000000000000000000000000000000000000000000000000000000'
    '10270000000000000200000002000000020000000f000000100000001400000078000000060000002800000040060000'
    '14050000c2010000ee020000800c0000e01500004006000098080000780000003200000032000000000000008a020000'
    '52030000e80300002800000052030000f00000006c0700004605000066080000e80300000a0000000300000000000000'
    '000000002d0000006419000022240000b60300005500000046050000800c00005f0500006400000050000000b0040000'
    'b00400000807000060090000960000006009000068010000c0120000c0120000282300004c1d0000983a000050460000'
    '30750000b888000050c30000400d030020bf0200f0490200400d0300050000000a0000000a0000001e00000032000000'
    '32000000d00700004600000028000000a0000000c800000078000000780000000100000005000000fa0000005e010000'
    '05000000d20000008a0200001400000078000000e80300000a0000006e0000001e00000032000000c2010000ee020000'
    '0a00000078000000bc0200006400000064000000650000001800000047090000c80000000a0000000a000000f4010000'
    'f401000000000000a0000000000000009001000090010000000000000000000000000000f00a0000d43000003a070000'
    '00000000000000008813000040060000580200000000000015000000b00400004b0000006e0000000a000000eb000000'
    '8c0000001e000000a861000064190000581b00005e010000710200009001000020030000a00f000028230000b80b0000'
    'c4090000ac0d0000d0070000d0070000d0070000d007000078050000c409000010270000e02e000029040000a60e0000'
    '2e09000011080000280a0000ec040000f1040000c00300001a040000ca080000ca080000ca080000ca08000098030000'
    '0500000060ea0000905f01002d050000409c0000f0490200204e0000a086010050c3000000000000eca90000e4570000'
    '420e000072060000204e0000'
)
QK = bytes.fromhex(
    '000000000000000000000000000000000200000200000000020000020000000000020200000000000000020202000101'
    '000000000000000000000000020200000000000002010000000002000000000000020000000202020200000000000000'
    '000000010101010101010101010100000000000000000000020200040401010101010101010101010101010101010000'
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000000200000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000002020202010201000202010200000001020000020000020202000200010000020202'
    '000200020200020000000000000000000202010000000200000000000001000000000000000000000001000102000101'
    '010101010101010101010101010101010101010101010101010101010100000000000000000000000000000000000000'
    '010101000101010101010101010000000000010101010101010101010101030003030302000000000401000001010002'
    '010000000000000000000000000001000000000100000000000000000000000002020202000200000000000000000000'
    '000000000000000001000000020000000200000200000100000100000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000002020202000000010100000000000000000000000000000002000000000000000000'
    '000104000000000000000000000001010001010101010000000100000000000100000000000001000000000000000000'
    '000000000000000000000300000000030000000000030000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000000000000001010000000000000000020002000000000000010101010100'
    '000002000200000000000000000000000000000100020000000000000000000000000000010000000000000002010000'
    '000002'
)
QMAX = bytes.fromhex(
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000505'
    '000000000000000000000000000000000000000000050000000000000000000000000000000000000000000000000000'
    '000000646464646464646405646400000000000000000000000000000064646464646464646464646464646464640000'
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000050005000000050000000005000000000000000000000000050000000000'
    '000000000000000000000000000000000000050000000000000000000005000000000000000000000005001900000505'
    '050505050505050505050505050505050505050505050505050505050500000000000000000000000000000000000000'
    '03030300030303030303030303000000000003030303030303030a0a0a0a000000000000000000000003000003050000'
    '05000000000000000000000000000a000000000500000000000000000000000000000014000000000000000000000000'
    '000000000000000005000000000000000000000000000a00000a00000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000000000050500000000000000000000000000000000000000000000000000'
    '00140000000000000000000000000a0a000a0a0a0a0a0000000a00000000000a0000000000000a000000000000000000'
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000000000000005050000000000000000000000000000000000640164646400'
    '0000000000000000000000000000000000000064000000000000000000000000000000000a00000000000000000a0000'
    '000000'
)
DMAX = bytes.fromhex(
    '0000000000000000000000000000000010000008000000000c00000b0001000000041900000000000000070c06000101'
    '0000000000000000000000000c0c00000000000007020000000014000000000000640000000305050500000000000000'
    '0000000b1009090f0c0f0601190900000000000000000000141900010264321919141405191409140964190814190000'
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000'
    '000000000000000000000000000005090905010402000709030600000005000000030000040309000300050000070707'
    '000000000700000000000000000000000a03010000000300000000000002000000000000220000000001000303000103'
    '030401040302040101030301010101010101010301050505050303030100000000000000002200002222000000000000'
    '010101000101010101010101010000000000010101010101010105030106050003030408000000000101000001030000'
    '01000000000000000000000000000100000000010000000000000000000000000a07080c000300000000010000000000'
    '0000000000000000010000000800000006000006000c0100000100000000000100000000000000000000000000000000'
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000022051109000000010100000000000000000000000000000014000000000000000000'
    '000506000000000000000000000001010001010101010000000100000000000100000000000001000000000000010000'
    '000000090000000000000a00000000010000000000120000000000000000000000000000000000000000000000000000'
    '0000000000000600000000000000000000000600000708010100000000000000001300090000000000000c0108166400'
    '00001e001200000000000000000000000000001200070000000000000000000000000000050000000000000004010000'
    '000009'
)
IDD = bytes.fromhex(
    '0000020304090400000002050904080a10000000040000000a0f000a0010000308081100090f00040810090806060202'
    '0800020c0004020204080a0c0a1000030103000009020906000a100000050a0008100000050f0e040307000303000700'
    '0f0508000206070002000809020400000600040a0009070f000008070900060709080b0b000608090b00070a00040800'
    '00090000000c080b10000506000000000705070b0600050c0e00000800050710040006080000080b100305000000050b'
    '00050c0e000007080507100000070006080000000508000000050b00000607000b070801080a00071008080008000805'
    '1000030008080000000007100000080606080c00050707050207070709020007070707070c0c0c000000050307090909'
    '000900090c07080c00040404040404040b080400000707070707040c0902040707050910050703090c02000107000401'
    '020306050102030802020102070102050403080c0b0501010209090d03030303030505020b0503030a110c110c130506'
    '0502020b0203030303030303050f0a0f0f1301050503070406050101010003000801050803000004050304010202000a'
    '0c00000000010501010202010303090301030006000f090c0a050f09090909000c0b0503000f00000007000603050505'
    '05050505050003000d00040a0a030303030101030b1006010c010001000c080907080005050808080808080805080508'
    '0505080b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b1010100b1010100b0b0b10100a141000010604020401140f0f00021001'
    '0506140f100505050500030c0300010e09010002070707000000000000000000000000020802000405060708090b0002'
    '0e020c00000000000609030306000401070101040402010a0405060a0b090a030101010b050302040007050403000600'
    '0000120b030103050000000000000000000000000000000000000000000000000002020000060404000006060000080a'
    '00060802080a000b0d080f0f020513030605000008000006060000000000000000050808090c0500050d020607060504'
    '00000f0e0e040002070810070b06060606060409000a0409080505070504060909090907010b100000100b0c09000a05'
    '000308'
)
BIND = bytes.fromhex(
    '000000000101000000000000000000010000000000000000000000000001000000010000000000000000000100000000'
    '010000000000000000000000000000000000000000000001000101000000000000000000000101000001000000000000'
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000100000001000000000000000000000100000000000000010000000000000000000001000000000000000000000000'
    '000000010000000000000000000100000100000000000000000100000000000000000000010000000000010000000100'
    '000000000001000000000000000000000000000000000000000000000000000000000000000100000000000000000000'
    '000000010000000000000000000000000001000000000000000100000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000000000000000000000000000000100000000000100000000000000000000'
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000000000000000000000000000000000000000010000000000000000000000'
    '000001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000'
    '000000000000000100000000000100000000000000000001000000000000010000000000000000000000000000000000'
    '000001'
)
UNI = bytes.fromhex(
    '0000000000000101010101010102020202030304040505050505060607070e0e0e0e0e0f0f0f10101010121313136666'
    '133333333434353738353a3a3b3b6c757575767680668080080808090909090a0a0a1111111111111111363939394d5a'
    '5a6969008e8e8e70707e7e7f8e8e0b0b0b0c0c0c0d0d2525686e6e727216161616161616171717171753535384711826'
    '262626821a1a1a1a1a2a292a2a2a2a2a2a2a2a2a2a3c3c3c3c3c3e3e43454545565656565d1b1b1b1b2b2b2c2c2c2c2c'
    '3d3d3d3d3d3f3f3f4646464848485757575e191919192728404040404141414242444755555b5c606061611c1c2d2d2d'
    '4a586a1d1d1d2e2f2f30304b595f1e1e1e1e641e661f1f1f201f1f1f1f222432323232323232324c4c4e224e5252521e'
    '1e52525252525263626363636363636363638c636374747d7d49494949664949787979797a7a7b7b7b667b1274636620'
    '202020648166228c816781818120648c658c8c228c222222222222222286868614141414147a14147a7a14147b7b1489'
    '21212189212121212121212121897878797921212121212121216363636365006681812849232123722114412122001f'
    '8c2386868614141414141414141423141414866686232323238641212121213c91120992861105866325811414141414'
    '1414141414866f866601867d1f1f1f1f1f8686521a01868636863686663c470025012114141414141414141414141414'
    '141414141414141414141414141414141414141414141414141414141414141a231f1123747886068660232363634986'
    '86868686866f6f6f8a88898b23237b12121e2386308181838383838383838383838383238623846f6f6f6f6f6f6f6f86'
    '238f90212121212186866f6f86218686868686868686031186862a2a2a0311868686868a015286052c050f491f818666'
    '21030302000302490c078787878787878787878787878787876e87878787878686868686868786866486868686868686'
    '86868686868681866e868686868686868686860c8681812020866486101021212169471e2386011b2d23707e0053160d'
    '04761125042e0f40491f0e43001f1f1f1f1f1017621826822626250105017626262626096349293030601b3c1f232509'
    '2a2b1e'
)
EQC = bytes.fromhex(
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001010'
    '000000000001000000000000000000000000000000100000010101010101010101010101010101010101010101010101'
    '010101020f0f0f02020202020f0f03030303030303030303030303030304040404040404040404040404040404040505'
    '050505050606060606060606060606060606060606060606060606060606060606060606060707070707070707070707'
    '070707070707070707070707070707070707080808080808080808080808080808080808080808080808080909090909'
    '0909090a0a0a0a0a0a0a0a0a0a0a0b0b0b0b110b100b0b0b100b0b0b0b120b0b0b0b0b0b0b0b0b0b0b0b120b0b0b0b0b'
    '0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b110b0b0b0b0b0b0c0c0c0c100c0c0d0d0d0d0d0d0d0d0d100d0f0f191010'
    '1010101016100f1116101010101111111111111211121212121212121219191913131313130d13130d0d13130d0d130d'
    '1414140d1414141414141414140d0d0d0d0d1414141414141414151515151600161616080c17191703141308140f000b'
    '11171919191313131313131313131713131319191917171717190819191919060f000104190100191903161313131313'
    '13131313130b19171000190b0b0b0b0b0b19190b06001919011901191906080003001913131313131313131313131313'
    '1313131313131313131313131313131313131313131313131313131313131306170b0117190d19191908171719120c19'
    '19191919191717170d0d0d0d17170d00000b17190a101003030303030303030303030317191704171717171717171719'
    '17040319191919191919191919191919191919191919000119190606060001191919190d000b19000700000c0b161910'
    '190000000000000c03000e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e10100e0e0e0e0e0e'
    '190e0e0e0e0e160e0e0e0e0e0e0e0e0e0e0e19030e16161616191919000019191901080b171900070917020202040403'
    '00000103000a00080c0b0106000b0b0b0b0b00040b050505050503000000000505050501150c060a0a0807060b170301'
    '06070b'
)
FLAGS = bytes.fromhex(
    '080808080808000000000000000404040408000000000000000808000001040404050400000000040000080100000800'
    '030808080000040808000000040401080a0a080008000809040404040404040404040404040404040407000404070004'
    '040404080008080808080808080800000000000000000000010100000008080808080808080808080808080801000000'
    '000001000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000'
    '000000000000000000000000000000000100000000000000000000010000000000000001010000000000020000000000'
    '000000000000000001000000000001000000080000010000000000000100000000000000000000010001080000000000'
    '010001000000000000000000000000000000080101000000000000000000000000000000000000000000010000000008'
    '000000000000000800000000000808080808080808080808080808080803030300000000000000000000000000000000'
    '000000000000000000000000000000000000000000000000000001010101000000000000000300020000000100000801'
    '1801030300010000000000000000020000000103000202030102000000000000010a040001040c010100010000000000'
    '000000000000030300000100010000000010110011111111111100131103030b00000000000000000000000000000000'
    '000000000000000000000000000000000000000000000000000000000000000001010703030003030303030221010011'
    '030303030301010100010000030000080801000303000000000000000000000000000002030101030303030303030303'
    '000005030303030303030303110111111111111111111105111111111111151113030300000011000000000000010301'
    '030000040800040001080101010101010101010101010101010101010101010101010101010101011111010101010101'
    '010101010101010101010101010101010101010101010100000313010000010101040001000000000002088808080800'
    '000004000000000000000400080000000000000800000000000000000000000000000004010000000000000000030004'
    '010001'
)
SPELL = bytes.fromhex(
    '0000000000000000000000000000000039000002000000000300005100000000005a53000000000000003f732e00131b'
    '0000000000000000000000002453000000000000393600000000520000000000000f000000535d030200000000000000'
    '000000000419190000000062050500000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '0000000000000000000000000000441f0b483c5841004a1c7329000000740000003800005846060064004200005a2856'
    '00000000470000000000000000000000065d1e000000580000000000007200000e072e440c1d021824384d2773002306'
    '06063d648223223e100d0d1033162451302a39465d3f0c070f594d555c0000002c1a27113828020344643a4d31621725'
    '28190e431d27252f1a20143824594555525b583132183a2c443472737200730073828229000000000017120023580000'
    '5f0000000008100106070c0d0504000e090b0000000000000000000000000000514e3e00005c00000000820f0a131415'
    '1618191b1c000000780000003d000000480000360038000000000000000000000000001d1e1f2021222324252628292a'
    '2b2d2e2f3031323334353637393b3c3d3e3f404142434445464748494a4b4c0000000000001c00000000000000000000'
    '00000000000000001d3b033f00000e5f0505000000021500000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000000000000000000000000000000000000038000000000000000000820000'
    '000000460000000000000b050e11151e2d2620403d364647444f5658655a5f0000000000002a00000000000000000000'
    '00000000000082000000000000000000000008000082823d210000000000000000620003000000000000000000000000'
    '000051003200000000000000000000000000000000560000000000000000000000000000720000000000000073000000'
    '000045'
)
CAT = bytes.fromhex(
    '000000000000000000000000000000000100000100000000010000010000000000010100000000000000010101000505'
    '000000000000000000000000010100000000000001050000000001000000000000010000000101010100000000000000'
    '000000000101010000000001010100000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    '000000000000000000000000000001010101070105000101050100000007000000010000010101000100070000010101'
    '000000000100000000000000000000000101070000000100000000000005000006060606060606060605060101000505'
    '050505050505010705050505050707070707070707070707070707070700000003030303030603030606030306060306'
    '020202060202020202020202020606060606020202020202020204040404050005050501000000000002030002010000'
    '070000000003030303030303030300030303000000000000000000000000000009010100000100000000050303030303'
    '030303030300000005000000010000000100000100010000000000000000000000000003030303030303030303030303'
    '030303030303030303030303030303030303030303030303030303030303030000000000000600000000000000070000'
    '000000000000000006060606000006010101000000050500000000000000000000000000000000000000000000000000'
    '000000000000000000000000000000000000000000000000000000000000000000000006000000000000000000050005'
    '000000010000000000000808080808080808080808080808080808080808080000000000000800000505000000000000'
    '000000000000050000000000000000000000010000050505050000000000000000010001000000000000000000000000'
    '000001000100000000000000000000000000000000010000000000000000000000000000040000000000000001000000'
    '000001'
)
