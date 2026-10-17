"""npc_items.cpp (src/wiz8/npc_items.cpp): NPC stock lists, trade acceptance, trade
prices, stock maintenance (rule restock, decay, restock) and delayed (crafted) stock.

Fixture (all in scratch, zeroed for every case):
  S0       W8NpcState; +0x200 its owned item W8PList, +0x400 the element array. The list
           capacity is 0x3f00, so PLAdoptAppend never reallocates (frees) the scratch array.
  S1       W8NpcItemEntry records (0x14 each) the list points at (one setp per slot; a
           slot left 0 is a null element).
  S2       scratch W8NpcDatabaseRecord; +0x400 stock-rule W8PList, +0x500 rule pointers,
           +0x1000 the 6-byte W8NpcItemStockRule records (stride 8). Some cases point the
           NPC at a real g_npc_records[k] instead (NPC.DBS is read here from
           games\\reference, so the real price factors, class masks and rule lists are known).
  S3       W8ItemInstance argument(s).
  S7       redirected g_fact_journal_entries element array (journal lines a SetFact adds;
           count 0 / capacity 64 set on the live vector, restored afterwards). Each line is
           compared on its first 9 bytes: retail fills the upper three bytes of the
           alternate_text dword from an uninitialised stack slot. Fact notices are
           suppressed (g_fact_notifications_suppressed = 1, log_fact_checks = 0); the facts
           Mature sets have no HandleFactChange work for the values it writes (checked in
           the retail compare tree: 0xb0..0xb4, 0x19d, 0x1ca..0x1cc default, 0x19e and
           0x1dc..0x1de return on value 0).
Items.dbs (819 records) is read from games\\reference too: ids, classes, quantity kinds,
flags, identify difficulties and values are real; single record fields are overridden for
one case with c.set on g_item_records[id] (restored afterwards). Party inputs are set per
slot with small c.set patches (XChar fOccupied, uiExpLevel, hp_current, highest_condition,
skills[COMMUNICATION].level) using corpus characters' values plus edges.
Entries/heap: entries the call creates (CreateNpcItemEntry, operator new) live on the
heap and only their count is visible (list iNumUsed); merges into scratch entries and
their fields are compared byte for byte.

Tested (retail address, function, cases at scale 1):
  0x0055aad0 RateItemIdentifyDifficulty     400  avg party level 0..1000 (char wrap of the
                                                 average and of level*100/30), identify
                                                 difficulty overrides 0..255 around the
                                                 lower/upper band edges
  0x0055b290 NpcAcceptsTradeItemClass       300  every equip class, class overrides
                                                 0x19/0x1a/0xff, masks single-bit/neighbour/
                                                 real NPC records
  0x0055b250 NpcAcceptsTradeItem            250  + NO_DISCARD items and flag overrides
  0x0055b5e0 CalculateTradeStackPrice       400  party COMMUNICATION best level, real and
                                                 edge price factors (incl. buy>sell, <=0,
                                                 inf/NaN), value/quantity-kind/class
                                                 overrides, stack 0..255, identified bytes,
                                                 price kind 0/1/2/0x100
  0x0055b5a0 CalculateNpcTradeStackPrice    300  item ids, stack_count/identified args
                                                 incl. high bytes, quantity kind 5 and dice
                                                 maximum >= 256 (asserts 599/578)
  0x0055ae00 ConsumeNpcItemQuantity         300  stack vs non-stack kinds, quantity around
                                                 stack/quantity, index out of range/negative/
                                                 null element
  0x0055ade0 GetNpcItemAt                   100  in range, == count, negative, null list
  0x0055b710 GetNpcItemCount                 60  null list, counts incl. 0x80000000
  0x0055baf0 CompareNpcItems                300  same id / same class+generic name / random
                                                 pairs, identified 0/1/2, stack/uses ties
  0x0055a7b0 AddNpcItem                     350  merge into existing entries, ammo repeats
                                                 (quantity 0 returns the id), null list,
                                                 null npc, quantity high bytes
  0x0055aa80 AddNpcItemWithDelay            250  + world clock / delay edges (wrap)
  0x0055BB10 MatureNpcDelayedItems          300  available_at vs world clock (unsigned),
                                                 kinds 3/0x39/0x49 (+0x103 etc.), the
                                                 crafted item ids; facts + journal captured
  0x0055afa0 MaintainNpcStock               400  covers the inlined RestockNpcItems,
                                                 DecayNpcInventory, FindNpcStockItem,
                                                 RemoveDepletedNpcStock (no-op here),
                                                 jitter; clock edges 0xa8c0/0x15180, force
                                                 high bytes, real merchant rule lists
  0x0055BCC0 RestockNpcInventory            200  MaintainNpcStock(false) + Mature
  0x0055B730 SellItemToNpc                  250  covers the inlined AddNpcItemFromInstance;
                                                 acceptance, price, party gold (wrap),
                                                 level_progress gold (current_level -1/-2/
                                                 0x2f), stock merge
  total 4160

MaintainNpcStock / RestockNpcInventory run in two modes:
  mode A (~65%): no maintenance pass (force low byte 0 and world_clock -
    maintenance_clock < 0x15180): first loop (NormalizeItemQuantityKind, stack fix-up)
    and the persistent-rule restock (when world_clock - restock_clock > 0xa8c0 or force);
    entries are unconstrained (quantity 0, null elements...).
  mode B (~35%, note mode='B'): the decay + restock + RemoveDepletedNpcStock pass.
    RemoveDepletedNpcStock would 'delete' scratch entries whose quantity reaches 0, so
    every scratch entry is built to survive in the original: protected from decay by
    available_at != 0, item flags 0x12 (real or overridden), the first matching rule
    persistent == 1, or a stack item whose stack stays above its quantity after the
    first loop (it decays partially - that is the decay check); merges cannot wrap a
    quantity to 0 (rule quantities <= 80). A port that zeroes such an entry deletes
    scratch memory and crashes - reported as a CRASH difference.

Skipped:
  0x0055a930 AddNpcItemFromInstance   - inlined in the port (not in Wiz8Runtime.map);
                                        covered through SellItemToNpc
  0x0055ab80 RestockNpcItems          - inlined in the port; covered through
                                        MaintainNpcStock / RestockNpcInventory mode B
  0x0055ae70 DecayNpcInventory        - inlined in the port; covered the same way
  0x0055a630 PopulateNpcStock         - ends in SortNpcItems: frees and rebuilds the list
                                        and every entry on the heap; the result is only
                                        reachable through a heap pointer written during
                                        the call (cap cannot follow it)
  0x0055b9c0 SortNpcItems             - same (delete every entry, PLDestroy, PLCreate)
  0x0055a5d0 ClearNpcItems            - frees the list and entries (heap deletion),
                                        otherwise a no-op
  0x0055B7E0 CompleteNpcItemPurchase  - adds items to the party or drops them into the
                                        world, NPC quote UI, sound, deletes depleted entries
"""
import os
import struct

M32 = 0xffffffff

# W8Character / party (layout.ps1: wiz8/layouts/character.h, game_status.h)
CHAR = 0x1862
XROW = 0x106               # W8PartySlotRow, fOccupied at +0
C_LEVEL = 0x89             # uiExpLevel
C_HCOND = 0xb01            # highest_condition
C_HP = 0xb11               # hp_current
C_COMM = 0x19d + 0x16 * 0x26 + 6   # skills[W8_SKILL_COMMUNICATION].level = 0x4e7
COND_TURNCOAT = 13

# W8GlobalStatus
GS_GOLD = 0x19
GS_CLOCK = 0x18d8
GS_LEVEL = 0x1900
GS_LP = 0x1a04             # W8LevelProgressRow[0x2f], 0x21 each, gold_collected +9
GS_LP_ROW = 0x21
LEVEL_COUNT = 0x2f
GS_LP_END = GS_LP + LEVEL_COUNT * GS_LP_ROW
GS_LOG_FACTS = 0x3120

# W8NpcState (pack 1)
N_RECORD = 0x06
N_ITEMS = 0x0a
N_RESTOCK = 0x0e
N_MAINT = 0x12
N_CAP = 0x16

# W8NpcDatabaseRecord
NPC_REC = 0x309
R_KIND = 0x58
R_RULES = 0x2ca
R_BUY = 0x2ce
R_SELL = 0x2d2
R_MASK = 0x2d6

# W8ItemDatabaseRecord
ITEM_REC = 0x10d
I_CLASS = 0x3e
I_UNI = 0x3f
I_FLAGS = 0x41
I_QKIND = 0x66
I_DICE = 0x67
I_QMAX = 0x6b
I_IDENT = 0x85
I_VALUE = 0x86

ENTRY = 0x14               # W8NpcItemEntry: available_at, W8ItemInstance item, quantity
E_QTY = 0x10

AMMO = 4
Q_STACK = 1

# scratch layout
S0_LIST = 0x200
S0_DATA = 0x400
ITEM_CAPACITY = 0x3f00
S2_RULE_LIST = 0x400
S2_RULE_DATA = 0x500
S2_RULES = 0x1000
RULE_STRIDE = 8

# W8GrowableVector<W8JournalEntry>: vptr, count, capacity, data
J_COUNT = 0x04
J_DATA = 0x0c
J_CAPACITY = 64
J_ENTRY = 0x0c

FACT_TEMPLAR = 0x15f
FACT_SPAN = (0xb0, 0x1e0)                  # cap over every fact Mature can set
FACT_RANGES = [(0xb0, 5), (0x19d, 2), (0x1ca, 3), (0x1dc, 3)]

KIND_ARMORER = 3           # 0x28a..0x28e -> facts 0xb0..0xb4
KIND_FERRO = 0x39          # 500/0x1f5/0x1f8 -> 0x1ca..0x1cc (+ clear 0x1dc..0x1de)
KIND_TRYNNIE = 0x49        # 0x1b0 -> 0x19d (+ clear 0x19e)
MATURE_IDS = {KIND_ARMORER: [0x28a, 0x28b, 0x28c, 0x28d, 0x28e],
              KIND_FERRO: [500, 0x1f5, 0x1f8], KIND_TRYNNIE: [0x1b0]}
MATURE_NEAR = [0x289, 0x28f, 0x1af, 0x1b1, 0x1f3, 0x1f6, 0x1f7, 0x1f9, 0x1fc]
OTHER_KINDS = [0, 2, 4, 0x38, 0x3a, 0x48, 0x4a, 0x103, 0x139, 0x149, 0x10003, -1]

LEVEL_EDGES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 17, 18, 20, 21, 23, 24,
               25, 26, 27, 28, 29, 30, 31, 35, 38, 39, 40, 41, 45, 50, 60, 77, 100, 127, 128,
               129, 150, 200, 254, 255, 256, 257, 300, 383, 384, 1000]
STACKS = [0, 1, 2, 3, 5, 9, 10, 24, 25, 26, 50, 99, 100, 127, 128, 200, 254, 255]
VALUE_EDGES = [0, 1, 3, 4, 24, 25, 26, 99, 100, 101, 999, 16777217, 0x0ccccccc, 0x7fffffff,
               0x80000000, 0xffffffff]


def u8(v):
    return bytes([int(v) & 0xff])


def u32(v):
    return struct.pack('<I', int(v) & M32)


def f32(v):
    return struct.pack('<f', v)


def entry(avail, iid, stack, uses, ident, qty, tail=(0, 0, 0, 0, 0)):
    """W8NpcItemEntry bytes (0x14)."""
    return (struct.pack('<IiBBB', avail & M32, iid, stack & 0xff, uses & 0xff, ident & 0xff) +
            bytes(t & 0xff for t in tail) + bytes([qty & 0xff, 0, 0, 0]))


def item(iid, stack=0, uses=0, ident=1, tail=(0, 0, 0, 0, 0)):
    """W8ItemInstance bytes (0x0c)."""
    return struct.pack('<iBBB', iid, stack & 0xff, uses & 0xff, ident & 0xff) + bytes(t & 0xff for t in tail)


def rule(iid, qty, persistent):
    return struct.pack('<iBBxx', iid, qty & 0xff, persistent & 0xff)


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


def _database(suffix):
    root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
    for game in ('reference', 'work'):
        for rel in (('Patches', 'PATCH.001'), ('Data', 'DATA.SLF')):
            path = os.path.join(root, 'games', game, *rel)
            if os.path.exists(path):
                data = _slf_read(path, suffix)
                if data:
                    return data
    raise RuntimeError('%s not found under games\\reference or games\\work' % suffix)


def _load_items():
    data = _database('databases\\items.dbs')
    count = struct.unpack_from('<I', data, 0)[0]
    out = []
    for i in range(count):
        b = data[4 + i * ITEM_REC:4 + (i + 1) * ITEM_REC]
        out.append({'id': i, 'cls': b[I_CLASS], 'uni': struct.unpack_from('<H', b, I_UNI)[0],
                    'flags': b[I_FLAGS], 'qk': b[I_QKIND], 'qmax': b[I_QMAX], 'ident': b[I_IDENT],
                    'value': struct.unpack_from('<I', b, I_VALUE)[0], 'dice': b[I_DICE:I_DICE + 4]})
    return out


def _load_npcs():
    """NPC.DBS: count, then 0x309-byte records, each followed by its stock rules when
    version > 1 and no_item_stock (0x9d) is clear (InitializeNpcDatabase)."""
    data = _database('databases\\npc.dbs')
    count = struct.unpack_from('<I', data, 0)[0]
    off = 4
    out = []
    for i in range(count):
        b = data[off:off + NPC_REC]
        off += NPC_REC
        version = struct.unpack_from('<H', b, 0)[0]
        rules = []
        if b[0x9d] == 0 and version > 1:
            n = struct.unpack_from('<I', data, off)[0]
            off += 4
            for _ in range(n):
                rules.append(struct.unpack_from('<iBB', data, off))
                off += 6
        buy, sell = struct.unpack_from('<ff', b, R_BUY)
        out.append({'index': i, 'kind': struct.unpack_from('<i', b, R_KIND)[0], 'buy': buy,
                    'sell': sell, 'mask': struct.unpack_from('<I', b, R_MASK)[0], 'rules': rules})
    return out


def _sc(v):
    v &= 0xff
    return v - 256 if v >= 128 else v


def _tdiv(a, b):
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def _rate_band(avg):
    level = _sc(avg)
    base = _sc(_tdiv(_sc(_tdiv(level * 100, 30)), 5))
    raw_upper = _sc(base + 4)
    lower = 16 if base > 16 else (1 if base < 1 else base)
    upper = 20 if raw_upper > 20 else (4 if raw_upper < 4 else raw_upper)
    return lower, upper


def _rate_model(diff, avg):
    lower, upper = _rate_band(avg)
    d = _sc(diff)
    if d > upper:
        return 0
    if d < lower:
        return 2 if d + 4 >= lower else 1
    return 3


def _first_loop_stack(s, u, q):
    """NormalizeItemQuantityKind (stack kind) + MaintainNpcStock's stack fix-up."""
    if u > 0:
        if s > 0:
            u = 0
        else:
            s, u = u, 0
    elif s == 0:
        s = 1
    if q > s:
        s, q = q, 1
    return s, u, q


class _Env:
    def __init__(self, ctx):
        self.ctx = ctx
        self.items = _load_items()
        self.npcs = _load_npcs()
        self.n_items = len(self.items)
        self.gs = ctx.g('g_status')
        self.rec0 = ctx.g('g_item_records').deref()
        self.npc0 = ctx.g('g_npc_records').deref()
        self.facts = ctx.g('g_fact_values')
        self.suppress = ctx.g('g_fact_notifications_suppressed')
        self.journal = ctx.g('g_fact_journal_entries').deref()
        self.S = [ctx.scratch(k) for k in range(8)]
        it = self.items
        self.stack_ids = [x['id'] for x in it if x['qk'] == Q_STACK]
        self.ammo_ids = [x['id'] for x in it if x['cls'] == AMMO]
        self.nonammo_ids = [x['id'] for x in it if x['cls'] != AMMO]
        self.nonammo_stack = [x['id'] for x in it if x['cls'] != AMMO and x['qk'] == Q_STACK]
        self.nonstack_ids = [x['id'] for x in it if x['qk'] != Q_STACK]
        self.flagged_ids = [x['id'] for x in it if x['flags'] & 0x12]
        self.nodiscard_ids = [x['id'] for x in it if x['flags'] & 0x02]
        self.by_class = {}
        groups = {}
        for x in it:
            self.by_class.setdefault(x['cls'], []).append(x['id'])
            groups.setdefault((x['cls'], x['uni']), []).append(x['id'])
        self.classes = sorted(self.by_class)
        self.uni_groups = [g for g in groups.values() if len(g) >= 2]
        self.merchants = [n for n in self.npcs if n['rules']]
        self.factors = [(n['buy'], n['sell']) for n in self.npcs]
        self.masks = sorted({n['mask'] for n in self.npcs})
        corpus = ctx.corpus or []
        # (uiExpLevel, COMMUNICATION level, hp_current, highest_condition) per corpus char
        self.cvals = [(struct.unpack_from('<I', d, C_LEVEL)[0], struct.unpack_from('<I', d, C_COMM)[0],
                       struct.unpack_from('<I', d, C_HP)[0], struct.unpack_from('<I', d, C_HCOND)[0])
                      for _, d in corpus] or [(1, 0, 10, 0), (8, 10, 60, 0), (16, 30, 120, 0), (23, 50, 200, 0)]

    # --- addresses ---
    def rec(self, iid):
        return self.rec0 + iid * ITEM_REC

    def npc_rec(self, k):
        return self.npc0 + k * NPC_REC

    def xrow(self, slot):
        return (self.gs + 8).deref() + slot * XROW

    # --- fixture ---
    def wire_items(self, c, entries, null_slots=(), capacity=ITEM_CAPACITY):
        S0, S1 = self.S[0], self.S[1]
        if entries:
            c.set(S1, b''.join(entries))
        for k in range(len(entries)):
            if k not in null_slots:
                c.setp(S0 + S0_DATA + 4 * k, S1 + ENTRY * k)
        c.set(S0 + S0_LIST + 4, struct.pack('<ii', capacity, len(entries)))
        c.setp(S0 + S0_LIST, S0 + S0_DATA)
        c.setp(S0 + N_ITEMS, S0 + S0_LIST)

    def wire_rules(self, c, rules):
        """rules None: record without a list; []: empty list."""
        S2 = self.S[2]
        if rules is None:
            return
        if rules:
            c.set(S2 + S2_RULES, b''.join(rule(*x) for x in rules))
        for k in range(len(rules)):
            c.setp(S2 + S2_RULE_DATA + 4 * k, S2 + S2_RULES + RULE_STRIDE * k)
        c.set(S2 + S2_RULE_LIST + 4, struct.pack('<ii', len(rules) + 4, len(rules)))
        c.setp(S2 + S2_RULE_LIST, S2 + S2_RULE_DATA)
        c.setp(S2 + R_RULES, S2 + S2_RULE_LIST)

    def wire_record(self, c, kind=None, factors=None, mask=None, rules=None):
        S0, S2 = self.S[0], self.S[2]
        if kind:
            c.set(S2 + R_KIND, u32(kind))
        if factors is not None or mask is not None:
            buy, sell = factors if factors is not None else (0.0, 0.0)
            c.set(S2 + R_BUY, f32(buy) + f32(sell) + u32(mask or 0))
        self.wire_rules(c, rules)
        c.setp(S0 + N_RECORD, S2)

    def wire_real_record(self, c, k):
        c.setp(self.S[0] + N_RECORD, self.npc_rec(k))

    def npc_caps(self, c, n_entries):
        S0 = self.S[0]
        c.cap(S0, N_CAP, 'npc', ignore=[N_RECORD, N_ITEMS])
        c.cap(S0 + S0_LIST + 4, 8, 'item_list')
        if n_entries:
            c.cap(self.S[1], n_entries * ENTRY, 'entries')

    # --- party ---
    def corpus_val(self, r):
        return self.cvals[r.randrange(len(self.cvals))]

    def party_levels(self, c, r, target=None, levels=None, edge_p=0.03):
        """XChar fOccupied + uiExpLevel; at least one occupied slot (GetAveragePartyLevel
        divides by the count). Returns the unsigned average."""
        k = r.choice([1, 2, 3, 4, 5, 6, 6, 7, 8, 8, 8])
        slots = sorted(r.sample(range(8), k))
        if levels is None:
            if target is None:
                levels = [self.corpus_val(r)[0] for _ in slots]
            else:
                levels = [target] * k
                for _ in range(k // 2):
                    a, b = r.sample(range(k), 2)
                    d = r.randrange(0, min(levels[b], 6) + 1)
                    levels[a] += d
                    levels[b] -= d
        else:
            levels = levels[:k] + [levels[-1]] * (k - len(levels))
        lv = dict(zip(slots, levels))
        for s in range(8):
            occ = 0
            if s in lv:
                occ = 1 if r.random() >= edge_p else r.choice([2, 0x80, 0xff])
            c.set(self.xrow(s), u8(occ))
            if occ:
                c.set(self.ctx.char(s) + C_LEVEL, u32(lv[s]))
        return (sum(levels) & M32) // k

    def party_comm(self, c, r, edge_p=0.05):
        """XChar fOccupied, hp_current, highest_condition, COMMUNICATION level of every
        slot (GetBestPartySkillLevel). Returns the expected best level."""
        k = 0 if r.random() < 0.03 else r.choice([1, 2, 3, 4, 5, 6, 6, 6, 7, 8])
        slots = set(r.sample(range(8), k))
        best, best_slot = 0, -1
        for s in range(8):
            if s not in slots:
                c.set(self.xrow(s), u8(0))
                continue
            _, comm, hp, cond = self.corpus_val(r)
            x = r.random()
            if x < edge_p:
                comm = r.choice([0, 1, 124, 125, 126, 250, 500, 1000, 0x7fffffff, 0x80000000, M32])
            elif x < 0.45:
                comm = r.randrange(0, 126)
            if r.random() < 0.1:
                hp = r.choice([0, 0, 1, 0x80000000, M32])
            y = r.random()
            if y < 0.12:
                cond = r.choice([1, 5, 11, 12, 13, 14, 18, 19])
            elif y < 0.14:
                cond = r.choice([0x80000000, M32])
            c.set(self.xrow(s), u8(1))
            c.set(self.ctx.char(s) + C_HP, u32(hp))
            c.set(self.ctx.char(s) + C_HCOND, u32(cond))
            c.set(self.ctx.char(s) + C_COMM, u32(comm))
            if hp != 0 and cond < COND_TURNCOAT and (comm > best or best_slot == -1):
                best, best_slot = comm, s
        return best

    # --- facts / journal ---
    def mature_globals(self, c, r):
        """Facts Mature can set (random 0/1), journal vector redirected into S7, notices
        suppressed, fact-check log off, current_level set (journal line level)."""
        for base, n in FACT_RANGES:
            c.set(self.facts + base, bytes(r.choice([0, 0, 1]) for _ in range(n)))
        c.set(self.facts + FACT_TEMPLAR, u8(r.choice([0, 1])))
        c.set(self.journal + J_COUNT, struct.pack('<ii', 0, J_CAPACITY))
        c.setp(self.journal + J_DATA, self.S[7])
        c.set(self.suppress, u8(1))
        c.set(self.gs + GS_LOG_FACTS, u8(0))
        c.set(self.gs + GS_LEVEL, u32(r.choice([2, 3, 5, r.randrange(LEVEL_COUNT)])))

    def mature_caps(self, c):
        """Retail RecordFactChangeForJournal stores GetFact's byte into the low byte of
        the line's alternate_text dword and copies the other three bytes from an
        uninitialised stack slot, so each line is compared on its first 9 bytes only
        (level, fact, value byte). Mature adds at most five lines (kind 3)."""
        c.cap(self.facts + FACT_SPAN[0], FACT_SPAN[1] - FACT_SPAN[0], 'facts')
        c.cap(self.journal + J_COUNT, 4, 'journal_count')
        for k in range(6):
            c.cap(self.S[7] + k * J_ENTRY, 9, 'journal%d' % k)

    def world_clock(self, r):
        x = r.random()
        if x < 0.75:
            return r.randrange(0x20000, 0x4000000)
        return r.choice([0, 1, 0x15180, 0xa8c0, 0x7fffffff, 0x80000000, 0x80000001, M32,
                         r.getrandbits(32)])

    def pick_item(self, r, stack_p=0.35, ammo_p=0.1):
        x = r.random()
        if x < ammo_p:
            return r.choice(self.ammo_ids)
        if x < ammo_p + stack_p:
            return r.choice(self.stack_ids)
        return r.randrange(self.n_items)


def cases(ctx):
    env = _Env(ctx)
    _rate(env)
    _accepts_class(env)
    _accepts(env)
    _price(env)
    _npc_price(env)
    _consume(env)
    _get_at(env)
    _count(env)
    _compare(env)
    _add(env)
    _add_delay(env)
    _mature(env)
    _maintain(env)
    _restock_inventory(env)
    _sell(env)


# --------------------------------------------------------------------------------------
def _rate(env):
    """char RateItemIdentifyDifficulty(W8NpcState* unused, int item_id)"""
    ctx = env.ctx
    fn = ctx.fn(0x0055aad0)
    diff_edges = list(range(0, 22)) + [24, 25, 30, 100, 126, 127, 128, 129, 200, 235, 236, 251,
                                       252, 255]
    for i in range(ctx.n(400)):
        r = ctx.rng('rate', i)
        c = ctx.case('rate.%d' % i, fn, conv='c', ret='i8')
        x = r.random()
        if x < 0.3:
            avg = env.party_levels(c, r)
        elif x < 0.9:
            t = r.choice(LEVEL_EDGES) if r.random() < 0.75 else r.randrange(0, 61)
            avg = env.party_levels(c, r, target=t)
        else:
            avg = env.party_levels(c, r, levels=[r.choice([r.getrandbits(32), 0x7fffffff, 0x80000000,
                                                           M32, r.randrange(0, 300)])
                                                 for _ in range(8)])
        iid = r.randrange(env.n_items)
        diff = env.items[iid]['ident']
        if r.random() < 0.45:
            lower, upper = _rate_band(avg)
            if r.random() < 0.6:
                diff = r.choice([upper, upper + 1, upper - 1, lower, lower - 1, lower - 3, lower - 4,
                                 lower - 5, lower + 1]) & 0xff
            else:
                diff = r.choice(diff_edges)
            c.set(env.rec(iid) + I_IDENT, u8(diff))
        c.arg(env.S[0] if r.random() < 0.8 else 0)
        c.arg(iid)
        c.note(item=iid, difficulty=diff, avg=avg, expect=_rate_model(diff, avg))


# --------------------------------------------------------------------------------------
def _accept_setup(env, c, r, flags_test):
    """NPC in S0 with a scratch record (mask) or a real one; item instance in S3."""
    if flags_test and r.random() < 0.25:
        iid = r.choice(env.nodiscard_ids)
    else:
        iid = r.choice(env.by_class[r.choice(env.classes)])
    rec = env.items[iid]
    cls, flags = rec['cls'], rec['flags']
    edge = None
    if r.random() < 0.2:
        cls = r.choice([r.randrange(26), 0x18, 0x19, 0x1a, 0x1b, 0x1f, 0x20, 0x7f, 0x80, 0xff])
        c.set(env.rec(iid) + I_CLASS, u8(cls))
        edge = 'class'
    if flags_test and r.random() < 0.2:
        flags = r.choice([0, 2, 3, 0xfd, 0xff, 0x10, 0x12, 0x80])
        c.set(env.rec(iid) + I_FLAGS, u8(flags))
        edge = 'flags'
    if r.random() < 0.25:
        k = r.choice(env.merchants)['index'] if r.random() < 0.5 else r.randrange(len(env.npcs))
        env.wire_real_record(c, k)
        mask = env.npcs[k]['mask']
        rec_note = 'real%d' % k
    else:
        bit = (1 << cls) if cls < 32 else 0
        mask = r.choice([0, M32, 0x3ffffff, bit, ~bit & M32, (bit << 1 | bit >> 1) & M32,
                         r.getrandbits(32), r.choice(env.masks), 0xfc000000, bit | r.getrandbits(32),
                         r.getrandbits(32) & ~bit])
        env.wire_record(c, mask=mask)
        rec_note = 'scratch'
    c.set(env.S[3], item(iid, r.randrange(256), r.randrange(256), r.choice([0, 1])))
    c.arg(env.S[0])
    c.arg(env.S[3])
    c.note(item=iid, cls=cls, flags=flags, mask='%08x' % mask, record=rec_note)
    if edge:
        c.note(edge=edge)


def _accepts_class(env):
    """bool NpcAcceptsTradeItemClass(W8NpcState*, W8ItemInstance*)"""
    ctx = env.ctx
    fn = ctx.fn(0x0055b290)
    for i in range(ctx.n(300)):
        r = ctx.rng('acceptsclass', i)
        c = ctx.case('acceptsclass.%d' % i, fn, conv='c', ret='b')
        _accept_setup(env, c, r, False)


def _accepts(env):
    """bool NpcAcceptsTradeItem(W8NpcState*, W8ItemInstance*)"""
    ctx = env.ctx
    fn = ctx.fn(0x0055b250)
    for i in range(ctx.n(250)):
        r = ctx.rng('accepts', i)
        c = ctx.case('accepts.%d' % i, fn, conv='c', ret='b')
        _accept_setup(env, c, r, True)


# --------------------------------------------------------------------------------------
def _factors(env, r):
    x = r.random()
    if x < 0.45:
        return r.choice(env.factors), 'real'
    if x < 0.75:
        return (round(r.uniform(0.3, 1.2), 3), round(r.uniform(0.8, 2.0), 3)), 'random'
    if x < 0.94:
        edges = [0.0, -0.0, 0.1, -0.5, -1.0, 1e-8, 0.5, 0.75, 1.0, 1.25, 2.0, 100.0, 1e6, 3e9]
        buy = r.choice(edges)
        sell = buy if r.random() < 0.2 else r.choice(edges)
        return (buy, sell), 'edge'
    inf, nan = float('inf'), float('nan')
    return r.choice([(inf, 1.2), (0.8, inf), (-inf, 1.0), (nan, 1.2), (0.8, nan), (nan, nan),
                     (inf, inf)]), 'nonfinite'


def _price_item_overrides(env, c, r, iid):
    """One record field of the priced item, 25% of the cases."""
    if r.random() >= 0.25:
        return None
    what = r.choice(['value', 'value', 'qk', 'class'])
    if what == 'value':
        v = r.choice(VALUE_EDGES)
        c.set(env.rec(iid) + I_VALUE, u32(v))
        return 'value=%x' % v
    if what == 'qk':
        v = r.choice([0, 1, 2, 3, 4])
        c.set(env.rec(iid) + I_QKIND, u8(v))
        return 'qk=%d' % v
    v = r.choice([AMMO, 0, 11, 6])
    c.set(env.rec(iid) + I_CLASS, u8(v))
    return 'class=%d' % v


def _price_record(env, c, r):
    if r.random() < 0.25:
        k = r.choice(env.merchants)['index'] if r.random() < 0.6 else r.randrange(len(env.npcs))
        env.wire_real_record(c, k)
        return 'real%d' % k, (env.npcs[k]['buy'], env.npcs[k]['sell'])
    fac, kind = _factors(env, r)
    env.wire_record(c, factors=fac, mask=r.getrandbits(32))
    return kind, fac


def _ident(r):
    x = r.random()
    if x < 0.65:
        return 1
    if x < 0.95:
        return 0
    return r.choice([2, 0x80, 0xff])


def _price(env):
    """int CalculateTradeStackPrice(W8NpcState*, W8ItemInstance*, char price_kind)"""
    ctx = env.ctx
    fn = ctx.fn(0x0055b5e0)
    for i in range(ctx.n(400)):
        r = ctx.rng('price', i)
        c = ctx.case('price.%d' % i, fn, conv='c', ret='i')
        best = env.party_comm(c, r)
        rec_note, fac = _price_record(env, c, r)
        iid = env.pick_item(r, stack_p=0.35, ammo_p=0.15)
        stack = r.choice(STACKS) if r.random() < 0.7 else r.randrange(256)
        ident = _ident(r)
        c.set(env.S[3], item(iid, stack, r.randrange(256) if r.random() < 0.3 else 0, ident))
        ov = _price_item_overrides(env, c, r, iid)
        kind = r.choice([0, 1]) if r.random() < 0.85 else r.choice([2, 0x7f, 0x80, 0xff, 0x100, 0x101, M32])
        c.arg(env.S[0])
        c.arg(env.S[3])
        c.arg(kind)
        c.note(item=iid, stack=stack, ident=ident, kind=kind, best_comm=best, record=rec_note,
               factors='%r/%r' % fac)
        edges = []
        if ov:
            c.note(override=ov)
        if ident not in (0, 1):
            edges.append('bool_byte')
        if rec_note == 'nonfinite':
            edges.append('nonfinite')
        if edges:
            c.note(edge=','.join(edges))


def _npc_price(env):
    """int CalculateNpcTradeStackPrice(W8NpcState*, int item_id, W8TradePriceKind,
    unsigned char stack_count, bool identified)"""
    ctx = env.ctx
    fn = ctx.fn(0x0055b5a0)
    for i in range(ctx.n(300)):
        r = ctx.rng('npcprice', i)
        c = ctx.case('npcprice.%d' % i, fn, conv='c', ret='i')
        best = env.party_comm(c, r)
        rec_note, fac = _price_record(env, c, r)
        iid = env.pick_item(r, stack_p=0.35, ammo_p=0.15)
        ov = _price_item_overrides(env, c, r, iid)
        x = r.random()
        if ov is None and x < 0.04:
            c.set(env.rec(iid) + I_QKIND, u8(5))          # "Invalid multi code" assert
            ov = 'qk=5'
        elif ov is None and x < 0.07 and env.items[iid]['qk']:
            c.set(env.rec(iid) + I_DICE, struct.pack('<hBB', 0, 0x20, 0x10))   # max 512
            ov = 'dice_max_512'
        stack = r.choice(STACKS) if r.random() < 0.8 else r.choice([0x100, 0x1ff, 0x180, M32])
        ident = r.choice([0, 1]) if r.random() < 0.9 else r.choice([2, 0xff, 0x100, 0x101])
        kind = r.choice([0, 1]) if r.random() < 0.88 else r.choice([2, 0xff, 0x100, M32])
        c.arg(env.S[0])
        c.arg(iid)
        c.arg(kind)
        c.arg(stack)
        c.arg(ident)
        c.note(item=iid, stack=stack, ident=ident, kind=kind, best_comm=best, record=rec_note,
               factors='%r/%r' % fac)
        if ov:
            c.note(override=ov)


# --------------------------------------------------------------------------------------
def _random_entry(env, r, iid=None, avail_p=0.2):
    if iid is None:
        iid = env.pick_item(r)
    avail = 0 if r.random() >= avail_p else r.choice([1, r.getrandbits(32), 0x80000000, M32])
    stack = r.choice(STACKS) if r.random() < 0.6 else r.randrange(256)
    uses = 0 if r.random() < 0.6 else r.choice([1, 5, 255, r.randrange(256)])
    qty = r.choice([0, 1, 1, 2, 3, 5, 10, 50, 127, 128, 254, 255, r.randrange(256)])
    tail = tuple(r.choice([0, 0, 0, 1]) for _ in range(5))
    return [avail, iid, stack, uses, r.choice([0, 1, 1]), qty, tail]


def _pack_entries(rows):
    return [entry(a, iid, s, u, idn, q, t) for a, iid, s, u, idn, q, t in rows]


def _consume(env):
    """unsigned char ConsumeNpcItemQuantity(W8NpcState*, int index, unsigned char quantity)"""
    ctx = env.ctx
    fn = ctx.fn(0x0055ae00)
    for i in range(ctx.n(300)):
        r = ctx.rng('consume', i)
        c = ctx.case('consume.%d' % i, fn, conv='c', ret='b')
        n = r.randrange(1, 11)
        rows = [_random_entry(env, r, env.pick_item(r, stack_p=0.5)) for _ in range(n)]
        nulls = {r.randrange(n)} if r.random() < 0.08 else set()
        env.wire_items(c, _pack_entries(rows), null_slots=nulls)
        x = r.random()
        if x < 0.82:
            index = r.randrange(n)
        elif x < 0.92:
            index = r.choice([n, n + 1, 100, 0x7fffffff])
        else:
            index = r.choice([-1, -2, -7])
        target = rows[index] if 0 <= index < n else None
        ov = None
        if target is not None and r.random() < 0.15:
            ov = r.choice([0, 1, 2, 3, 4, 5])
            c.set(env.rec(target[1]) + I_QKIND, u8(ov))
        y = r.random()
        if y < 0.05:
            q = 0
        elif y < 0.6 and target is not None:
            s, qq = target[2], target[5]
            q = r.choice([s - 1, s, s + 1, qq - 1, qq, qq + 1, 1]) & 0xff
        elif y < 0.95:
            q = r.randrange(1, 256)
        else:
            q = r.choice([0x100, 0x101, 0x1ff, 0xffffff05])
        c.arg(env.S[0])
        c.arg(index)
        c.arg(q)
        env.npc_caps(c, n)
        c.note(index=index, quantity=q, n=n, nulls=','.join(map(str, sorted(nulls))))
        if target is not None:
            c.note(target='%d:s%d/q%d' % (target[1], target[2], target[5]))
        if ov is not None:
            c.note(override='qk=%d' % ov)


def _get_at(env):
    """W8NpcItemEntry* GetNpcItemAt(W8NpcState*, int index)"""
    ctx = env.ctx
    fn = ctx.fn(0x0055ade0)
    for i in range(ctx.n(100)):
        r = ctx.rng('getat', i)
        c = ctx.case('getat.%d' % i, fn, conv='c', ret='p')
        n = r.randrange(0, 9)
        if r.random() < 0.1:
            index = r.randrange(-2, 3)
            c.note(list='null')
        else:
            rows = [_random_entry(env, r) for _ in range(n)]
            nulls = {r.randrange(n)} if n and r.random() < 0.1 else set()
            env.wire_items(c, _pack_entries(rows), null_slots=nulls)
            x = r.random()
            index = r.randrange(n) if (n and x < 0.6) else r.choice([n, n + 1, -1, -2, -16, -100,
                                                                    0x7fffffff, 0, 1])
            c.note(n=n, nulls=','.join(map(str, sorted(nulls))))
        c.arg(env.S[0])
        c.arg(index)
        c.note(index=index)


def _count(env):
    """unsigned int GetNpcItemCount(W8NpcState*)"""
    ctx = env.ctx
    fn = ctx.fn(0x0055b710)
    S0 = env.S[0]
    for i in range(ctx.n(60)):
        r = ctx.rng('count', i)
        c = ctx.case('count.%d' % i, fn, conv='c', ret='i')
        if r.random() < 0.2:
            c.note(list='null')
        else:
            n = r.choice([0, 1, 2, 5, 10, 40, 0x7fffffff, 0x80000000, M32, r.getrandbits(32)])
            c.set(S0 + S0_LIST + 4, struct.pack('<iI', 10, n))
            c.setp(S0 + S0_LIST, S0 + S0_DATA)
            c.setp(S0 + N_ITEMS, S0 + S0_LIST)
            c.note(n=n)
        c.arg(S0)


# --------------------------------------------------------------------------------------
def _compare(env):
    """int CompareNpcItems(const void*, const void*) - qsort predicate of SortNpcItems:
    CompareItemsForPool on the embedded items."""
    ctx = env.ctx
    fn = ctx.fn(0x0055baf0)
    S1 = env.S[1]
    small = [0, 1, 2, 5, 100, 255]
    for i in range(ctx.n(300)):
        r = ctx.rng('compare', i)
        c = ctx.case('compare.%d' % i, fn, conv='c', ret='i')
        x = r.random()
        if x < 0.35:
            a = b = r.randrange(env.n_items)
            how = 'same_id'
        elif x < 0.6:
            a, b = r.sample(r.choice(env.uni_groups), 2)
            how = 'same_name'
        elif x < 0.75:
            ids = env.by_class[r.choice(env.classes)]
            a, b = r.choice(ids), r.choice(ids)
            how = 'same_class'
        else:
            a, b = r.randrange(env.n_items), r.randrange(env.n_items)
            how = 'random'

        def ident():
            return r.choice([0, 1, 1]) if r.random() < 0.95 else r.choice([2, 0x80, 0xff])

        ia, ib = ident(), ident()
        sa, sb = r.choice(small), r.choice(small)
        ua, ub = r.choice(small), r.choice(small)
        if r.random() < 0.3:
            sb = sa
        if r.random() < 0.3:
            ub = ua
        if r.random() < 0.2:
            ib = ia
        c.set(S1, entry(r.getrandbits(32), a, sa, ua, ia, r.randrange(256)) +
              entry(r.getrandbits(32), b, sb, ub, ib, r.randrange(256)))
        c.arg(S1)
        c.arg(S1 + ENTRY)
        c.note(how=how, a='%d/s%d/u%d/i%d' % (a, sa, ua, ia), b='%d/s%d/u%d/i%d' % (b, sb, ub, ib))
        if ia not in (0, 1) or ib not in (0, 1):
            c.note(edge='bool_byte')


# --------------------------------------------------------------------------------------
Q_EDGES = [0, 1, 2, 3, 5, 10, 25, 100, 127, 128, 200, 255, 256, 257, 0x1ff, 0x7fffffff, M32]


def _add_setup(env, c, r, allow_ammo_zero):
    """Entries + target item for AddNpcItem/AddNpcItemWithDelay. Returns (iid, quantity,
    n_entries, notes) or None for the null-npc case."""
    x = r.random()
    items_null = x < 0.1
    y = r.random()
    if y < 0.2:
        iid = r.choice(env.ammo_ids)
        q = r.choice([0, 1, 1, 2, 3, 5, 10, 25, 60] if allow_ammo_zero else [1, 1, 2, 3, 5, 10, 25, 60])
        how = 'ammo'
    else:
        iid = r.choice(env.nonammo_stack) if r.random() < 0.4 else r.choice(env.nonammo_ids)
        q = r.choice(Q_EDGES) if r.random() < 0.5 else r.randrange(1, 30)
        how = 'present' if r.random() < 0.6 else 'absent'
    ammo = env.items[iid]['cls'] == AMMO
    ov = None
    if r.random() < 0.15:
        if not ammo and q <= 60 and (q or allow_ammo_zero) and r.random() < 0.3:
            c.set(env.rec(iid) + I_CLASS, u8(AMMO))
            ov, ammo = 'class=4', True
        elif ammo and r.random() < 0.3:
            c.set(env.rec(iid) + I_CLASS, u8(0))
            ov, ammo = 'class=0', False
        else:
            v = r.choice([0, 1, 2, 3, 4])
            c.set(env.rec(iid) + I_QKIND, u8(v))
            ov = 'qk=%d' % v
    n = 0
    if not items_null:
        n = r.randrange(0, 13)
        rows = []
        for _ in range(n):
            other = env.pick_item(r)
            while other == iid:
                other = env.pick_item(r)
            rows.append(_random_entry(env, r, other))
        if how == 'present' and n:
            for _ in range(1 if r.random() < 0.8 else 2):
                rows[r.randrange(n)][1] = iid
        elif how == 'ammo' and n and r.random() < 0.5:
            rows[r.randrange(n)][1] = iid
        nulls = {r.randrange(n)} if n and r.random() < 0.08 else set()
        env.wire_items(c, _pack_entries(rows), null_slots=nulls)
        first = next((k for k, row in enumerate(rows) if row[1] == iid and k not in nulls), None)
        c.note(n=n, first_match=first, nulls=','.join(map(str, sorted(nulls))))
    else:
        c.note(list='null')
    c.note(item=iid, quantity=q, how=how)
    if ov:
        c.note(override=ov)
    return iid, q, n


def _add(env):
    """int AddNpcItem(W8NpcState*, int item_id, unsigned int quantity)"""
    ctx = env.ctx
    fn = ctx.fn(0x0055a7b0)
    for i in range(ctx.n(350)):
        r = ctx.rng('add', i)
        c = ctx.case('add.%d' % i, fn, conv='c', ret='i')
        if r.random() < 0.03:
            c.arg(0)
            c.arg(r.randrange(env.n_items))
            c.arg(r.randrange(1, 5))
            c.note(npc='null')
            continue
        iid, q, n = _add_setup(env, c, r, True)
        c.arg(env.S[0])
        c.arg(iid)
        c.arg(q)
        env.npc_caps(c, n)


def _add_delay(env):
    """int AddNpcItemWithDelay(W8NpcState*, int item_id, unsigned int quantity, int delay)"""
    ctx = env.ctx
    fn = ctx.fn(0x0055aa80)
    for i in range(ctx.n(250)):
        r = ctx.rng('adddelay', i)
        c = ctx.case('adddelay.%d' % i, fn, conv='c', ret='i')
        wc = env.world_clock(r)
        c.set(env.gs + GS_CLOCK, u32(wc))
        delay = r.choice([0, 1, 0x15180, 0x15180, -1, -0x15180, 0x7fffffff, -0x80000000,
                          r.randrange(-10 ** 6, 10 ** 7)])
        if r.random() < 0.03:
            c.arg(0)
            c.arg(r.randrange(env.n_items))
            c.arg(1)
            c.arg(delay)
            c.note(npc='null')
            continue
        # a quantity-0 ammo add returns the item id as an index: PLGet would hand back
        # null and both executables would write to address 0, so it is not used here
        iid, q, n = _add_setup(env, c, r, False)
        c.arg(env.S[0])
        c.arg(iid)
        c.arg(q)
        c.arg(delay)
        env.npc_caps(c, n)
        c.note(world_clock=wc, delay=delay)


# --------------------------------------------------------------------------------------
def _mature_kind(env, r):
    x = r.random()
    if x < 0.3:
        return KIND_ARMORER
    if x < 0.55:
        return KIND_FERRO
    if x < 0.75:
        return KIND_TRYNNIE
    return r.choice(OTHER_KINDS)


def _mature_item(env, r, kind):
    x = r.random()
    if x < 0.45 and kind in MATURE_IDS:
        return r.choice(MATURE_IDS[kind])
    if x < 0.6:
        return r.choice(MATURE_IDS[r.choice(list(MATURE_IDS))])
    if x < 0.7:
        return r.choice(MATURE_NEAR)
    return r.randrange(env.n_items)


def _mature_avail(r, wc):
    x = r.random()
    if x < 0.25:
        return 0
    return r.choice([1, wc - 1, wc, wc + 1, wc - r.randrange(1, 0x15180), wc + r.randrange(1, 0x15180),
                     r.getrandbits(32), 0x80000000, 0x7fffffff, M32]) & M32


def _mature(env):
    """void MatureNpcDelayedItems(W8NpcState*)"""
    ctx = env.ctx
    fn = ctx.fn(0x0055BB10)
    for i in range(ctx.n(300)):
        r = ctx.rng('mature', i)
        c = ctx.case('mature.%d' % i, fn, conv='c', ret='v')
        wc = env.world_clock(r)
        c.set(env.gs + GS_CLOCK, u32(wc))
        kind = _mature_kind(env, r)
        if kind in MATURE_IDS and r.random() < 0.2:
            env.wire_real_record(c, kind)          # g_npc_records[k].kind == k
            rec_note = 'real%d' % kind
        else:
            env.wire_record(c, kind=kind)
            rec_note = 'scratch'
        env.mature_globals(c, r)
        n = 0
        if r.random() < 0.04:
            c.note(list='null')
        else:
            n = r.randrange(0, 15)
            rows = []
            for _ in range(n):
                row = _random_entry(env, r, _mature_item(env, r, kind))
                row[0] = _mature_avail(r, wc)
                rows.append(row)
            env.wire_items(c, _pack_entries(rows))      # no null elements: not checked
            c.note(n=n, entries=';'.join('%x@%x' % (row[1], row[0]) for row in rows))
        c.arg(env.S[0])
        env.npc_caps(c, n)
        env.mature_caps(c)
        c.note(kind=kind, world_clock=wc, record=rec_note)


# --------------------------------------------------------------------------------------
def _synth_rules(env, r, safe):
    x = r.random()
    if x < 0.05:
        return None
    if x < 0.1:
        return []
    rules = []
    for _ in range(r.randrange(1, 9)):
        y = r.random()
        if y < 0.1:
            iid = 0x1fc                          # gated behind fact 0x15f (TEMPLAR)
        elif y < 0.25:
            iid = r.choice(env.ammo_ids)
        elif y < 0.6:
            iid = r.choice(env.stack_ids)
        else:
            iid = r.randrange(env.n_items)
        if safe:
            q = r.choice([0, 1, 2, 3, 4, 5, 6, 8, 10, 15, 20, 40, 80])
        else:
            q = r.choice([0, 1, 2, 3, 4, 5, 8, 10, 15, 100, 127, 128, 200, 255])
        p = r.choice([0, 0, 0, 1, 1]) if r.random() > 0.1 else r.choice([2, 0x80, 0xff])
        rules.append((iid, q, p))
    if len(rules) > 1 and r.random() < 0.15:
        iid = r.choice(rules)[0]
        rules.insert(r.randrange(len(rules) + 1), (iid, r.choice([0, 1, 3, 8]), r.choice([0, 1])))
    return rules


def _stock_setup(env, c, r, safe, allow_null, kind=None, mature=False, wc=0):
    """Record, stock rules and entries for MaintainNpcStock / RestockNpcInventory.
    safe: every scratch entry survives decay + restock (see the module docstring)."""
    use_real = r.random() < 0.3
    if mature and kind in MATURE_IDS and r.random() < 0.5:
        use_real = True
        k = kind
    elif use_real:
        k = r.choice(env.merchants)['index']
    if use_real:
        rules = env.npcs[k]['rules']
        env.wire_real_record(c, k)
        rec_note = 'real%d' % k
    else:
        rules = _synth_rules(env, r, safe)
        env.wire_record(c, kind=kind, rules=rules)
        rec_note = 'scratch'
    rules_list = rules or []
    rule_items = [x[0] for x in rules_list]
    persistent_ids = {x[0] for x in rules_list if x[2] != 0}

    def first_rule(iid):
        return next((x for x in rules_list if x[0] == iid), None)

    n = r.randrange(0, 13)
    rows = []
    prot = []
    flag_override = {}
    for _ in range(n):
        if mature and r.random() < 0.4:
            iid = _mature_item(env, r, kind)
        elif rule_items and r.random() < 0.6:
            iid = r.choice(rule_items)
        else:
            iid = env.pick_item(r)
        row = _random_entry(env, r, iid, avail_p=0.0)
        if mature:
            row[0] = _mature_avail(r, wc)
        elif r.random() < 0.25:
            row[0] = r.choice([1, r.getrandbits(32), 0x80000000, M32])
        if safe:
            it = env.items[iid]
            fr = first_rule(iid)
            opts = ['avail', 'flags']
            if fr is not None and fr[2] == 1:
                opts += ['rule', 'rule']
            if it['qk'] == Q_STACK and iid not in flag_override and iid not in persistent_ids:
                opts += ['stack', 'stack', 'stack']
            how = r.choice(opts)
            if row[0] != 0 and how not in ('stack',):
                how = 'avail'
            if how == 'stack':
                row[0] = 0 if not mature or r.random() < 0.5 else row[0]
                for _ in range(20):
                    s = r.randrange(0, 256)
                    u = 0 if r.random() < 0.7 else r.randrange(0, 256)
                    q = r.randrange(1, 256) if r.random() < 0.2 else r.randrange(1, max(2, s))
                    s2, u2, q2 = _first_loop_stack(s, u, q)
                    if s2 > q2 and q >= 1:
                        break
                else:
                    s, u, q = 10, 0, 3
                row[2], row[3], row[5] = s, u, q
                if row[0] == 0 and (it['flags'] & 0x12) == 0 and not (fr is not None and fr[2] == 1):
                    how = 'stack(decays)'
            else:
                if how == 'avail' and row[0] == 0:
                    row[0] = r.choice([1, 2, 0x15180, r.getrandbits(32) | 1, 0x80000000, M32])
                if how == 'flags' and not (it['flags'] & 0x12):
                    flag_override[iid] = it['flags'] | r.choice([0x10, 0x02, 0x12])
                row[5] = r.randrange(1, 41)
            prot.append(how)
        rows.append(row)
    nulls = set()
    if allow_null and n and r.random() < 0.06:
        nulls = {r.randrange(n)}
    for iid, fl in flag_override.items():
        c.set(env.rec(iid) + I_FLAGS, u8(fl))
    env.wire_items(c, _pack_entries(rows), null_slots=nulls)
    c.note(record=rec_note, rules=len(rules_list) if rules is not None else 'none', n=n,
           entries=';'.join('%d@%x:s%d/u%d/q%d' % (row[1], row[0], row[2], row[3], row[5]) for row in rows))
    if not use_real and rules_list:
        c.note(rule_list=';'.join('%d/%d/%d' % x for x in rules_list))
    if prot:
        c.note(protect=','.join(prot))
    if nulls:
        c.note(nulls=','.join(map(str, sorted(nulls))))
    return n


def _stock_clocks(env, c, r, safe):
    """World clock, restock/maintenance stamps and the force argument; mode B (safe) runs
    the maintenance pass, mode A never does."""
    wc = env.world_clock(r)
    d_rest = r.choice([0, 1, 0xa8bf, 0xa8c0, 0xa8c1, r.randrange(0, 0xa8c0), r.randrange(0xa8c1, 0x15180),
                       r.getrandbits(32), M32])
    if not safe:
        force = r.choice([0, 0, 0, 0, 0x100, 0xff00])
        d_maint = r.choice([0, 1, 0x1517f, r.randrange(0, 0x15180), r.randrange(0, 0x15180)])
    else:
        force = r.choice([1, 1, 2, 0xff, 0x101, 0, 0])
        if force & 0xff:
            d_maint = r.choice([0, r.randrange(0, 0x15180), r.getrandbits(32)])
        else:
            d_maint = r.choice([0x15180, 0x15181, r.randrange(0x15180, 1 << 32), M32])
    c.set(env.gs + GS_CLOCK, u32(wc))
    c.set(env.S[0] + N_RESTOCK, u32(wc - d_rest) + u32(wc - d_maint))
    c.note(world_clock=wc, restock_age=d_rest, maintenance_age=d_maint, force=force)
    return wc, force


def _maintain(env):
    """unsigned char MaintainNpcStock(W8NpcState*, bool force)"""
    ctx = env.ctx
    fn = ctx.fn(0x0055afa0)
    for i in range(ctx.n(400)):
        r = ctx.rng('maintain', i)
        safe = r.random() < 0.35
        c = ctx.case('maintain.%d' % i, fn, conv='c', ret='b')
        wc, force = _stock_clocks(env, c, r, safe)
        if safe:
            # RestockNpcItems: RateItemIdentifyDifficulty (average party level) and the
            # TEMPLAR fact for item 0x1fc
            avg = env.party_levels(c, r, target=r.choice(LEVEL_EDGES) if r.random() < 0.3 else None)
            c.set(env.facts + FACT_TEMPLAR, u8(r.choice([0, 1])))
            c.set(env.gs + GS_LOG_FACTS, u8(0))
            c.note(mode='B', avg_level=avg)
        else:
            c.note(mode='A')
        n = _stock_setup(env, c, r, safe, allow_null=True)
        c.arg(env.S[0])
        c.arg(force)
        env.npc_caps(c, n)


def _restock_inventory(env):
    """void RestockNpcInventory(W8NpcState*): MaintainNpcStock(npc, false), then
    MatureNpcDelayedItems(npc)."""
    ctx = env.ctx
    fn = ctx.fn(0x0055BCC0)
    for i in range(ctx.n(200)):
        r = ctx.rng('restockinv', i)
        safe = r.random() < 0.3
        c = ctx.case('restockinv.%d' % i, fn, conv='c', ret='v')
        wc = env.world_clock(r)
        d_rest = r.choice([0, 0xa8c0, 0xa8c1, r.randrange(0, 0xa8c0), r.randrange(0xa8c1, 0x15180),
                           r.getrandbits(32)])
        if safe:
            d_maint = r.choice([0x15180, 0x15181, r.randrange(0x15180, 1 << 32), M32])
            avg = env.party_levels(c, r)
            c.note(mode='B', avg_level=avg)
        else:
            d_maint = r.choice([0, 1, 0x1517f, r.randrange(0, 0x15180)])
            c.note(mode='A')
        c.set(env.gs + GS_CLOCK, u32(wc))
        c.set(env.S[0] + N_RESTOCK, u32(wc - d_rest) + u32(wc - d_maint))
        kind = _mature_kind(env, r)
        env.mature_globals(c, r)                    # also sets TEMPLAR and the fact log
        n = _stock_setup(env, c, r, safe, allow_null=False, kind=kind, mature=True, wc=wc)
        c.arg(env.S[0])
        env.npc_caps(c, n)
        env.mature_caps(c)
        c.note(kind=kind, world_clock=wc, restock_age=d_rest, maintenance_age=d_maint)


# --------------------------------------------------------------------------------------
def _sell(env):
    """unsigned char SellItemToNpc(W8NpcState*, W8ItemInstance*, unsigned char quantity,
    bool suppress_payment)"""
    ctx = env.ctx
    fn = ctx.fn(0x0055B730)
    gs = env.gs
    for i in range(ctx.n(250)):
        r = ctx.rng('sell', i)
        c = ctx.case('sell.%d' % i, fn, conv='c', ret='b')
        best = env.party_comm(c, r)
        x = r.random()
        if x < 0.1:
            iid = r.choice(env.nodiscard_ids)
        else:
            iid = env.pick_item(r, stack_p=0.35, ammo_p=0.15)
        cls = env.items[iid]['cls']
        ov = None
        if r.random() < 0.15:
            what = r.choice(['qk', 'class', 'value'])
            if what == 'qk':
                v = r.choice([0, 1, 2, 3])
                c.set(env.rec(iid) + I_QKIND, u8(v))
            elif what == 'class':
                v = 0 if cls == AMMO else AMMO
                c.set(env.rec(iid) + I_CLASS, u8(v))
                cls = v
            else:
                v = r.choice(VALUE_EDGES)
                c.set(env.rec(iid) + I_VALUE, u32(v))
            ov = '%s=%x' % (what, v)
        if r.random() < 0.3:
            k = r.choice(env.merchants)['index'] if r.random() < 0.7 else r.randrange(len(env.npcs))
            env.wire_real_record(c, k)
            rec_note = 'real%d' % k
            mask = env.npcs[k]['mask']
        else:
            fac, rec_note = _factors(env, r) if r.random() < 0.9 else ((0.8, 1.2), 'real')
            bit = 1 << cls if cls < 32 else 0
            mask = (r.getrandbits(32) | bit) if r.random() < 0.8 else (r.getrandbits(32) & ~bit)
            env.wire_record(c, factors=fac, mask=mask)
        stack = r.choice(STACKS)
        ident = _ident(r)
        c.set(env.S[3], item(iid, stack, r.randrange(256) if r.random() < 0.3 else 0, ident))
        n = 0
        if r.random() < 0.15:
            c.note(list='null')
        else:
            n = r.randrange(0, 9)
            rows = [_random_entry(env, r) for _ in range(n)]
            if n and r.random() < 0.5:
                rows[r.randrange(n)][1] = iid
            env.wire_items(c, _pack_entries(rows))
            c.note(n=n, entries=';'.join('%d:s%d/q%d' % (row[1], row[2], row[5]) for row in rows))
        gold = r.choice([r.randrange(0, 2000000), r.randrange(0, 2000000), 0, 0xffffff00,
                         0x7fffff00, M32, r.getrandbits(32)])
        level = r.choice([2, 3, 5, r.randrange(LEVEL_COUNT)]) if r.random() < 0.85 else \
            r.choice([0x2e, 0x2f, 0x30, 0x7fffffff, -1, -2])
        c.set(gs + GS_GOLD, u32(gold))
        c.set(gs + GS_LEVEL, u32(level))
        q = r.choice([1, 1, 2, 3, 5, 10, 25, 100, 255, 0, r.randrange(1, 50)]) if r.random() < 0.93 \
            else r.choice([0x100, 0x101, 0x1ff])
        suppress = r.choice([0, 0, 0, 1]) if r.random() < 0.95 else r.choice([2, 0x100])
        c.arg(env.S[0])
        c.arg(env.S[3])
        c.arg(q)
        c.arg(suppress)
        c.cap(env.S[3], 12, 'item')
        c.cap(gs + GS_GOLD, 4, 'party_gold')
        c.cap(gs + GS_LEVEL, GS_LP_END - GS_LEVEL, 'level_progress')
        env.npc_caps(c, n)
        c.note(item=iid, stack=stack, ident=ident, quantity=q, suppress=suppress, best_comm=best,
               record=rec_note, mask='%08x' % mask, gold=gold, level=level)
        if ov:
            c.note(override=ov)
        if ident not in (0, 1):
            c.note(edge='bool_byte')
