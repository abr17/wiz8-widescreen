"""database_facts: GameplayDatabase.cpp, fact_state.cpp, DifficultyScaling.cpp,
Game Difficulty.cpp, monster_fatigue.cpp (every "// FUNCTION: WIZ8" of the five files).

Tested (retail address, name, cases):
  0x005080f0 EvaluateFact                       2566
      * sweep: every fact id 0..999 once (1000 cases). Plain ids get a light world
        (g_fact_values from one of 8 random base arrays + random value at the id,
        fact-check log off, random fact_88_latch); the 37 ids retail dispatches
        through its three jump tables / direct compares (decoded from the retail
        tables at 0x508abc/0x508b04, 0x508ba4/0x508bcc, 0x508c84/0x508c98, plus
        0xcb, 0x194, 0x269, 0x295, 0x314, 0x31a) get the full world below.
      * 1566 steered cases on those 37 ids: faction facts (score bands 34/67, signed
        bytes), single-item facts, device count facts 0x2c/0x2e/0x103/0x5b, 0x81
        (facts 0x86/0x83 + items 0x271/0x272), 0x88 (fact_88_latch + CountItemOnParty
        0x1c4 >= 5 with stack counts incl. the backpack/equipped stack_count quirk),
        0x8f (0x1e5 equipped on every occupied member), 0x93, 0xb5 (Mook race +
        highest_condition < 15), NPC-lead facts 0xbd/0xbe/0x4f/0xc3/0xd1/0x19a,
        0x69 (NPC kind 0x2b spawned word, low byte returned raw), 0x216 (lead
        name style 0x18, NPC kind 0x18, Char[group_index].highest_condition >= 15),
        0x14c (rpc_active + sedexus_party_slot), and the GetFact chains 0x3d, 0x10c,
        0x265, 0x295, 0x31a (raw byte of fact 0x156) with all zero/non-zero combos.
      Full world: 8 corpus characters (special item ids scrubbed from their
      equipment/backpack unless planted), XChar fOccupied for all 8 slots,
      highest_condition for all 8, planted items in hand (with/without cursor flag),
      equipment/backpack of occupied and unoccupied members, party pool inside and
      beyond party_item_count (pool rebuilt from scratch, count <= ~45), all 21
      faction scores, rpc_active, sedexus_party_slot, fact_88_latch, log_fact_checks
      = 0 (GetFact's ShowNoticef stays off). NPC facts: g_npc_states replaced by a
      W8GrowableVector in scratch S0 (count, data -> S0+0x100; data[-1..-4] point at
      four extra states so negative XChar.npc_index values stay inside scratch),
      W8NpcState records in S1 (stride 0x140: spawned, record, group_index 0..7,
      name_style, binding_unavailable), W8NpcDatabaseRecord.kind in S2 (stride 0x60,
      incl. kinds with high bytes set). XChar[0/1].npc_index: in range, >= count
      (clamped to data[0]) or -1..-4. States a lead slot can reach always have
      binding_unavailable = 0 (otherwise both exes dereference null).
      Captured: fact_88_latch (written by 0x88) and the whole g_fact_values array.
      Not tested: ids >= 1000 and negative ids - the default path reads
      g_fact_values[id] outside the 1000-byte array (unrelated memory, different in
      the two exes). Retail inlines GetFact (recursive EvaluateFact + log check).
  0x0055cc00 ScaleValueForCharacterDifficulty    260  turncoat count (unsigned > 0),
      difficulty dword incl. 3/0xff/0x100/0x102/-1, values around rounding and the
      *60 / *140 signed overflow thresholds; *value captured
  0x0055ccb0 ScaleValueForMonsterDifficulty      260  W8MonsterInfo in scratch S1
      (ubDisposition 0/1/2 + 3/0x80/0x81/0xff, random neighbour bytes), same
      difficulty/value inputs; *value captured
  0x0052a780 CalculateMonsterFatigueBand         300  percentage-lost thresholds
      49/50, 69/70, 84/85, 94/95 (+-1 around each), current > maximum, negative
      current/maximum (unsigned divide), current*100 overflow, 2 cases maximum = 0
      (divide by zero in both)
  Total 3386 cases.
  Edge values outside the enums are labelled note(edge=...): 'cond_negative'
  (highest_condition 0x80000000/0xffffffff/0xfffffff0 - retail compares it unsigned,
  the port's W8Condition enum is signed), 'bool_byte' (fOccupied / rpc_active /
  latch bytes 2/0x80/0xff).

Skipped:
  0x0054a400 InitializeItemDatabase   - file I/O (Items.DBS) + malloc of g_item_records
  0x0054a510 InitializeItemTables     - file I/O (ItemTables.DBS) + heap allocations
  0x0054a8a0 LoadMonsterDatabaseRecord - file I/O (Monsters.DBS seek/read); the record
                                        lands in a caller buffer, so it would be testable
                                        read-only with a scratch buffer if file reads were
                                        allowed (also covers StripMonsterNameSuffix)
  0x0054a4f0 DestroyItemDatabase      - frees g_item_records (heap teardown)
  0x0054a880 FreeIfNotNull            - free(); trivial null guard, nothing to compare
  0x0054a6e0 DestroyItemTables        - heap teardown of the item tables
  0x0054a760 LoadMonsterDatabase      - file I/O (Monsters.DBS), heap allocation
  0x0054a9a0 LoadMonsterDatabaseRange - file I/O (Monsters.DBS seek/read), see 0x0054a8a0
  0x0054ac90 DestroyNpcDatabase       - heap teardown of the NPC database + PLists
  0x005063e0 PostNewGameLoad          - new-game setup: AddDialogueTranscriptKeyword
                                        appends to the heap transcript list (not
                                        restorable), SetFact with side effects
                                        (HandleFactChange world/journal effects)
  0x005064a0 LoadFactState            - file I/O (reads the fact array from a save handle),
                                        NPC script reloads
"""
import struct

FACT_COUNT = 1000
FV_BASES = 8

# g_status (layout.ps1, matches retail EvaluateFact / FindItemOnParty asm)
GS_ITEM_POOL = 0x21          # W8ItemInstance[500], 0xc each: iItemNo +0, stack_count +4
GS_ITEM_COUNT = 0x1791
GS_CURSOR = 0x235a           # bool item_in_cursor, then W8ItemInstance item_in_hand
GS_SEDEXUS = 0x247f
GS_RPC_ACTIVE = 0x2489
GS_LOG_FACTS = 0x3120        # retail byte 0x688290
GS_LATCH = 0x40c1            # retail byte 0x689231

# W8Character
C_RACE = 0x71
C_COND = 0xa01               # uiCondition[], TURNCOAT = 13 -> +0xa35
C_TURNCOAT = C_COND + 13 * 4
C_HCOND = 0xb01
C_EQUIP = 0xf5d              # W8ItemInstance[12]
C_PACK = 0x1029              # W8ItemInstance[8]

# W8PartySlotRow (g_status.buffers.XChar)
XROW = 0x106
X_OCC = 0x00
X_NPC = 0xfa

FACTION_STRIDE = 0xe         # W8FactionRuntimeRecord, disposition_score +0
FACTION_COUNT = 21

# W8NpcState / W8NpcDatabaseRecord (scratch copies)
NS_SPAWNED = 0x04
NS_RECORD = 0x06
NS_GROUP = 0x2b
NS_BINDING = 0xc7
NS_STRIDE = 0x140            # > sizeof(W8NpcState) 0x13d
NR_KIND = 0x58
NR_STRIDE = 0x60
VEC_DATA = 0x100             # data array inside S0

SET_DIFFICULTY = 0xd         # W8GameSettings.difficulty (dword enum), retail 0x6850d5
MI_DISPOSITION = 0x16        # W8MonsterInfo.ubDisposition

RACE_MOOK = 10
COND_EDGE = [0x80000000, 0xffffffff, 0xfffffff0]
BOOL_EDGE = [2, 0x80, 0xff]

# items EvaluateFact looks for (FindItemOnParty/CountItemOnParty/EveryCharacterHasItem)
IT_BADGE, IT_NOAMMO1, IT_NOAMMO2, IT_COVERT, IT_WETSUIT = 0x27b, 0x271, 0x272, 0x1c4, 0x1e5
IT_IUFPASS, IT_DEV1, IT_DEV2, IT_DEV3, IT_HELM, IT_SWORD = 0x268, 0x242, 0x243, 0x244, 0x239, 0x294
SPECIAL_ITEMS = {IT_BADGE, IT_NOAMMO1, IT_NOAMMO2, IT_COVERT, IT_WETSUIT, IT_IUFPASS, IT_DEV1,
                 IT_DEV2, IT_DEV3, IT_HELM, IT_SWORD}
ITEM_COUNT = 819             # Items.dbs records
FILLER_ITEMS = [x for x in range(ITEM_COUNT) if x not in SPECIAL_ITEMS]

# NPC name styles / kinds
NPC_MYLES, NPC_DRAZIC, NPC_RODAN, NPC_VI, NPC_SPARKLE = 7, 0x10, 0x11, 0x18, 0x38
KIND_GLUMPH, KIND_VI = 0x2b, 0x18

# fact id -> (category, parameters); retail dispatch decoded from its jump tables
SPECIAL = {
    0xca: ('faction', 12), 0xc9: ('faction', 11), 0xcb: ('faction', 10),
    0x183: ('faction', 4), 0x11e: ('faction', 5), 0xcc: ('faction', 9),
    0x194: ('faction', 13), 0x1a8: ('faction', 15), 0x314: ('faction', 16),
    0xab: ('item', IT_BADGE), 0xa0: ('item', IT_IUFPASS), 0xce: ('item', IT_SWORD),
    0x172: ('item', IT_HELM), 0x269: ('item', IT_HELM),
    0x2c: ('device',), 0x2e: ('device',), 0x103: ('device',), 0x5b: ('device',),
    0x81: ('noammo',),
    0x88: ('covert',),
    0x8f: ('wetsuit',),
    0x93: ('two',),
    0xb5: ('mook',),
    0xbd: ('lead', (NPC_DRAZIC,)), 0xbe: ('lead', (NPC_RODAN,)),
    0x4f: ('lead', (NPC_RODAN, NPC_DRAZIC)), 0xc3: ('lead', (NPC_VI,)),
    0xd1: ('lead', (NPC_MYLES,)), 0x19a: ('lead', (NPC_SPARKLE,)),
    0x69: ('glumph',),
    0x216: ('videad',),
    0x14c: ('father',),
    0x3d: ('rec', (0x3a, 0x3c)), 0x10c: ('rec', (0x22, 0x30, 0x31)),
    0x265: ('rec', (0x268, 0x323)), 0x295: ('rec', (0x7d, 0x3e)),
    0x31a: ('rec', (0x156,)),
}

# steered case count per category (per fact id)
PER_FACT = {'faction': 24, 'item': 30, 'device': 45, 'noammo': 80, 'covert': 100,
            'wetsuit': 60, 'two': 30, 'mook': 100, 'lead': 45, 'glumph': 50, 'videad': 100,
            'father': 70, 'rec': None}
PER_REC = {0x3d: 30, 0x10c: 40, 0x265: 30, 0x295: 30, 0x31a: 30}

FACTION_EDGE = [33, 34, 35, 66, 67, 68, 0, 1, 99, 100, 127, -1, -34, -67, -128, 0x50, 0x19,
                0x32, 0x37, 0x4b]
STYLE_POOL = [NPC_MYLES, NPC_DRAZIC, NPC_RODAN, NPC_VI, NPC_SPARKLE, 0, 1, 0x20, 0x2b, 0x85,
              0x86, 0xfa, 0xff]


def u8(v):
    return bytes([int(v) & 0xff])


def u16(v):
    return struct.pack('<H', int(v) & 0xffff)


def u32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def item_bytes(item, stack):
    return struct.pack('<IB', int(item) & 0xffffffff, int(stack) & 0xff)


def _fval(r, p_true=0.5, edge=0.12):
    """A fact byte: 0, 1, or a non-canonical true value."""
    if r.random() < p_true:
        return r.choice(BOOL_EDGE + [0x10, 0x7f]) if r.random() < edge else 1
    return 0


def _cond(r):
    x = r.random()
    if x < 0.5:
        return 0
    if x < 0.75:
        return r.randrange(1, 0x14)
    return r.choice([0x0d, 0x0e, 0x0f, 0x10, 0x11, 0x12, 0x13, 0x14])


def _fact_bases(ctx):
    out = []
    for k in range(FV_BASES):
        r = ctx.rng('factbase', k)
        p1 = [0.1, 0.3, 0.5, 0.7][k % 4]
        b = bytearray()
        for _ in range(FACT_COUNT):
            x = r.random()
            if x < 0.03:
                b.append(r.choice([2, 0x10, 0x80, 0xff]))
            elif x < 0.03 + p1:
                b.append(1)
            else:
                b.append(0)
        out.append(bytes(b))
    return out


# --------------------------------------------------------------------------------------
class World:
    """Everything EvaluateFact (and the helpers it calls) can read, decided in Python and
    written once per address in commit()."""

    def __init__(self, ctx, c, r, bases):
        self.ctx, self.c, self.r, self.bases = ctx, c, r, bases
        self.gs = ctx.g('g_status')
        self.fv_addr = ctx.g('g_fact_values')
        self.facts = {}
        self.latch = 0
        self.members = None
        self.occ = None
        self.cond = None
        self.race = [None] * 8
        self.slots = {}
        self.hand = None
        self.pool = []
        self.beyond = []
        self.factions = None
        self.faction_focus = None
        self.npc = None
        self.npc_index = None
        self.rpc = None
        self.sedexus = None
        self.both_styles_p = 0.0
        self.edges = set()
        self.notes = {}

    def xrow(self, s):
        return (self.gs + 8).deref() + s * XROW

    # --- decisions ---
    def light(self):
        r = self.r
        x = r.random()
        self.latch = 0 if x < 0.75 else (1 if x < 0.92 else r.choice(BOOL_EDGE))

    def party(self):
        r, ctx, c = self.r, self.ctx, self.c
        self.members = ctx.set_party(c, r)
        x = r.random()
        if x < 0.35:
            occ = [1] * 6 + [0, 0]
        elif x < 0.5:
            occ = [1] * 8
        elif x < 0.57:
            occ = [0] * 8
        else:
            p = r.choice([0.3, 0.6, 0.85])
            occ = [1 if r.random() < p else 0 for _ in range(8)]
        if r.random() < 0.08:
            s = r.randrange(8)
            occ[s] = r.choice(BOOL_EDGE)
            self.edges.add('bool_byte')
        self.occ = occ
        self.cond = [_cond(r) for _ in range(8)]
        if r.random() < 0.1:
            self.cond[r.randrange(8)] = r.choice(COND_EDGE)
        # pool filler (always rebuilt from scratch, count = len(self.pool))
        n0 = r.choice([0, 0, 2, 5, 10, 20, 35])
        self.pool = [(r.choice(FILLER_ITEMS), r.randrange(0, 6)) for _ in range(n0)]
        x = r.random()
        self.latch = 0 if x < 0.75 else (1 if x < 0.92 else r.choice(BOOL_EDGE))
        self.rpc = 1 if r.random() < 0.3 else 0
        self.sedexus = r.choice([0, 1, 2, 3, 4, 5, 6, 7, -1, 8])

    def occupied(self):
        return [s for s in range(8) if self.occ[s]]

    def unoccupied(self):
        return [s for s in range(8) if not self.occ[s]]

    def plant(self, item, stack=None, where=None, dead=False):
        """Put one instance of item somewhere FindItemOnParty(include_backpack=2) looks
        (or, dead=True, somewhere it must ignore)."""
        r = self.r
        if stack is None:
            stack = r.choice([0, 1, 1, 2, 5, 0xff])
        occupied, unocc = self.occupied(), self.unoccupied()
        if where is None:
            if dead:
                where = r.choice(['equip_unocc', 'pack_unocc', 'pool_beyond', 'hand_nocursor'])
            else:
                x = r.random()
                where = ('hand' if x < 0.1 else 'equip' if x < 0.4 else 'pack' if x < 0.65
                         else 'pool')
        if where in ('hand', 'hand_nocursor') and self.hand is not None:
            where = 'pool' if where == 'hand' else 'pool_beyond'
        if where in ('equip', 'pack') and not occupied:
            where = 'pool'
        if where in ('equip_unocc', 'pack_unocc') and not unocc:
            where = 'pool_beyond'
        if where == 'hand':
            self.hand = (1, item, stack)
        elif where == 'hand_nocursor':
            self.hand = (0, item, stack)
        elif where in ('equip', 'pack', 'equip_unocc', 'pack_unocc'):
            kind = 'equip' if where.startswith('equip') else 'pack'
            who = occupied if where in ('equip', 'pack') else unocc
            for _ in range(20):
                key = (r.choice(who), kind, r.randrange(12 if kind == 'equip' else 8))
                if key not in self.slots:
                    self.slots[key] = (item, stack)
                    break
            else:
                where = 'pool'
                self.pool.insert(r.randint(0, len(self.pool)), (item, stack))
        elif where == 'pool':
            self.pool.insert(r.randint(0, len(self.pool)), (item, stack))
        else:
            self.beyond.append((item, stack))
        return where

    def make_factions(self):
        r = self.r
        out = []
        for f in range(FACTION_COUNT):
            if f == self.faction_focus and r.random() < 0.7:
                v = r.choice(FACTION_EDGE)
            elif r.random() < 0.15:
                v = r.choice(FACTION_EDGE)
            else:
                v = r.choice([r.randrange(0, 100), r.randrange(0, 100), 25, 50, 75, 80, 0, 100])
            out.append(v)
        self.factions = out

    def npcs(self, style_bias=(), kinds_bias=()):
        r = self.r
        n = r.choice([1, 2, 3, 4, 5, 6, 8, 10, 14])
        states = []
        for _ in range(n + 4):
            kind = r.randrange(0x60)
            while kind in (KIND_VI, KIND_GLUMPH):
                kind = r.randrange(0x60)
            if r.random() < 0.05:   # high bytes set: GetNpcStateByKind compares the dword
                kind = r.choice([0x118, 0x12b, 0x10018, -0xe8, 0xffffff2b])
            states.append({
                'kind': kind,
                'style': r.choice(STYLE_POOL) if r.random() < 0.7 else r.randrange(256),
                'spawned': r.choice([0, 0, 1, 1, 2, 0xff, 0x100, 0x101, 0xffff]),
                'group': r.randrange(8),
                'binding': 0 if r.random() < 0.8 else r.choice([1, 0x80, 0xff]),
            })
        for k in kinds_bias:
            if r.random() < 0.75:
                states[r.randrange(n)]['kind'] = k
                if r.random() < 0.2:    # duplicate: the first match wins
                    states[r.randrange(n)]['kind'] = k
            elif r.random() < 0.3:      # only among the extra (uncounted) states
                states[n + r.randrange(4)]['kind'] = k
        idx = []
        for s in (0, 1):
            x = r.random()
            if x < 0.72:
                v = r.randrange(n)
            elif x < 0.84:
                v = r.choice([n, n + 1, n + 3, 0x7fffffff, 0x1000])   # clamped to data[0]
            else:
                v = -r.randrange(1, 5)                                 # data[-1..-4]
            idx.append(v)

        def target(v):
            if v >= n:
                return 0
            return v if v >= 0 else n + (-v) - 1
        both = len(style_bias) == 2 and r.random() < self.both_styles_p
        if both and target(idx[0]) == target(idx[1]):
            # two distinct states for the two leads: data[-1..-4] are the extra states
            idx[1] = r.choice([v for v in (-1, -2, -3, -4) if v != idx[0]])
        for s in (0, 1):
            t = states[target(idx[s])]
            t['binding'] = 0    # a released binding here dereferences null in both exes
            if style_bias and r.random() < 0.6:
                t['style'] = r.choice(style_bias)
        if both:
            # both styles on the two leads (fact 0x4f needs Rodan and Drazic)
            perm = list(style_bias)
            r.shuffle(perm)
            states[target(idx[0])]['style'] = perm[0]
            states[target(idx[1])]['style'] = perm[1]
        self.npc = (n, states)
        self.npc_index = idx
        self.notes['npc'] = '%d;idx=%d,%d;t=%d,%d' % (n, idx[0], idx[1], target(idx[0]),
                                                     target(idx[1]))

    # --- emit ---
    def commit(self, full=True):
        c, ctx, gs = self.c, self.ctx, self.gs
        c.set(gs + GS_LOG_FACTS, u8(0))
        c.set(gs + GS_LATCH, u8(self.latch))
        if self.latch not in (0, 1):
            self.edges.add('bool_byte')
        base = self.bases[self.r.randrange(len(self.bases))]
        fv = bytearray(base)
        for k, v in self.facts.items():
            fv[k] = v & 0xff
        c.setb(self.fv_addr, base)
        c.set(self.fv_addr, bytes(fv))
        if not full:
            return
        r = self.r
        for s in range(8):
            c.set(self.xrow(s) + X_OCC, u8(self.occ[s]))
            if self.occ[s] not in (0, 1):
                self.edges.add('bool_byte')
        if self.npc_index is not None:
            for s in (0, 1):
                c.set(self.xrow(s) + X_NPC, u32(self.npc_index[s]))
        for s, blob, name in self.members:
            ch = ctx.char(s)
            if self.race[s] is not None:
                c.set(ch + C_RACE, u32(self.race[s]))
            c.set(ch + C_HCOND, u32(self.cond[s]))
            if self.cond[s] >= 0x80000000:
                self.edges.add('cond_negative')
            for kind, base_off, cnt in (('equip', C_EQUIP, 12), ('pack', C_PACK, 8)):
                for k in range(cnt):
                    off = base_off + 12 * k
                    if (s, kind, k) in self.slots:
                        item, stack = self.slots[(s, kind, k)]
                        c.set(ch + off, item_bytes(item, stack))
                    elif blob.get_u32(off) in SPECIAL_ITEMS:
                        c.set(ch + off, u32(-1))
        if self.hand is None:
            cursor = 1 if r.random() < 0.25 else 0
            item = -1 if r.random() < 0.5 else r.choice(FILLER_ITEMS)
            hand = (cursor, item, r.randrange(0, 6))
        else:
            hand = self.hand
        c.set(gs + GS_CURSOR, struct.pack('<BIB', hand[0], hand[1] & 0xffffffff, hand[2]))
        entries = self.pool + self.beyond
        if entries:
            c.set(gs + GS_ITEM_POOL, b''.join(item_bytes(it, st) + bytes(7) for it, st in entries))
        c.set(gs + GS_ITEM_COUNT, u32(len(self.pool)))
        if self.factions is None:
            self.make_factions()
        fac = ctx.g('g_factions')
        for f, v in enumerate(self.factions):
            c.set(fac + f * FACTION_STRIDE, u8(v))
        c.set(gs + GS_SEDEXUS, u32(self.sedexus))
        c.set(gs + GS_RPC_ACTIVE, u8(self.rpc))
        if self.rpc not in (0, 1):
            self.edges.add('bool_byte')
        if self.npc is not None:
            self._commit_npcs()

    def _commit_npcs(self):
        c, ctx = self.c, self.ctx
        n, states = self.npc
        vec, st_base, rec_base = ctx.scratch(0), ctx.scratch(1), ctx.scratch(2)
        c.setp(ctx.g('g_npc_states'), vec)
        c.set(vec + 4, struct.pack('<ii', n, n + self.r.randrange(0, 8)))
        c.setp(vec + 0xc, vec + VEC_DATA)
        for i in range(n):
            c.setp(vec + (VEC_DATA + 4 * i), st_base + i * NS_STRIDE)
        for k in range(1, 5):
            c.setp(vec + (VEC_DATA - 4 * k), st_base + (n + k - 1) * NS_STRIDE)
        for j, st in enumerate(states):
            a = st_base + j * NS_STRIDE
            if st['spawned']:
                c.set(a + NS_SPAWNED, u16(st['spawned']))
            c.set(a + NS_GROUP, bytes([st['group'] & 0xff, 0, 0, st['style'] & 0xff]))
            c.setp(a + NS_RECORD, rec_base + j * NR_STRIDE)
            if st['binding']:
                c.set(a + NS_BINDING, u8(st['binding']))
            c.set(rec_base + j * NR_STRIDE + NR_KIND, u32(st['kind']))

    def caps(self):
        self.c.cap(self.gs + GS_LATCH, 1, 'fact_88_latch')
        self.c.cap(self.fv_addr, FACT_COUNT, 'fact_values')

    def finish_notes(self, fact):
        self.c.note(fact='0x%x' % fact, **self.notes)
        if self.edges:
            self.c.note(edge=','.join(sorted(self.edges)))


# --------------------------------------------------------------------------------------
def cases(ctx):
    bases = _fact_bases(ctx)
    _evaluate_fact(ctx, bases)
    _scale_character(ctx)
    _scale_monster(ctx)
    _fatigue_band(ctx)


def _special_case(ctx, fn, bases, fact, i, tag):
    """One full-world EvaluateFact case steered toward the branches of `fact`."""
    r = ctx.rng('fact', tag, fact, i)
    c = ctx.case('evalfact.%s.%03x.%d' % (tag, fact, i), fn, conv='c', ret='u8')
    w = World(ctx, c, r, bases)
    cat = SPECIAL[fact]
    kind = cat[0]
    w.party()
    w.facts[fact] = _fval(r)
    if kind == 'faction':
        w.faction_focus = cat[1]
    elif kind == 'item':
        item = cat[1]
        if r.random() < 0.55:
            w.notes['at'] = w.plant(item)
            if r.random() < 0.15:
                w.plant(item)
        if r.random() < 0.25:
            w.notes['dead'] = w.plant(item, dead=True)
    elif kind == 'device':
        items = [IT_DEV1, IT_DEV2, IT_DEV3]
        weights = {0x103: [1, 3, 1, 1], 0x2e: [1, 1, 3, 1], 0x2c: [1, 1, 1, 3],
                   0x5b: [1, 2, 2, 2]}[fact]
        k = r.choices(range(4), weights=weights)[0]
        chosen = r.sample(items, k)
        for it in chosen:
            w.plant(it)
        rest = [it for it in items if it not in chosen]
        if rest and r.random() < 0.3:
            w.plant(r.choice(rest), dead=True)
        w.notes['devices'] = ','.join('%x' % x for x in sorted(chosen))
    elif kind == 'noammo':
        w.facts[0x86] = _fval(r, 0.3)
        w.facts[0x83] = _fval(r, 0.7)
        for it in (IT_NOAMMO1, IT_NOAMMO2):
            if r.random() < 0.3:
                w.plant(it)
            elif r.random() < 0.15:
                w.plant(it, dead=True)
        w.notes['deps'] = '%x,%x' % (w.facts[0x86], w.facts[0x83])
    elif kind == 'covert':
        x = r.random()
        w.latch = 0 if x < 0.7 else (1 if x < 0.88 else r.choice(BOOL_EDGE))
        n = r.choice([0, 1, 1, 2, 2, 3, 4])
        stacks = []
        for _ in range(n):
            st = r.choice([0, 1, 2, 3, 4, 5, 6, 0x80, 0xff])
            stacks.append(st)
            w.plant(IT_COVERT, stack=st)
        if r.random() < 0.2:
            w.plant(IT_COVERT, stack=r.choice([5, 10, 0xff]), dead=True)
        w.notes['covert'] = ','.join(str(s) for s in stacks)
    elif kind == 'wetsuit':
        mode = r.choice(['all', 'all', 'all', 'miss', 'none', 'pack'])
        occ = w.occupied()
        miss = r.choice(occ) if occ and mode == 'miss' else None
        for s in occ:
            if mode == 'none':
                continue
            if mode == 'pack' or s == miss:
                if r.random() < 0.6:
                    w.slots[(s, 'pack', r.randrange(8))] = (IT_WETSUIT, 1)
                continue
            w.slots[(s, 'equip', r.randrange(12))] = (IT_WETSUIT, r.choice([0, 1]))
        if r.random() < 0.3:
            w.plant(IT_WETSUIT, where=r.choice(['hand', 'pool']))
        w.notes['wetsuit'] = mode
    elif kind == 'two':
        for s in (0, 1):
            w.occ[s] = r.choice([0, 1, 1]) if r.random() < 0.9 else r.choice(BOOL_EDGE)
    elif kind == 'mook':
        for s in range(8):
            if r.random() < 0.35:
                w.race[s] = RACE_MOOK
            elif r.random() < 0.05:
                w.race[s] = r.choice([RACE_MOOK + 0x100, RACE_MOOK | 0x80000000])
            else:
                w.race[s] = r.randrange(11)
            if w.race[s] == RACE_MOOK and r.random() < 0.5:
                w.cond[s] = r.choice([0, 0x0e, 0x0f, 0x10, 0x14] +
                                     (COND_EDGE if r.random() < 0.2 else []))
    elif kind == 'lead':
        w.both_styles_p = 0.6
        w.npcs(style_bias=cat[1])
        if len(cat[1]) == 2 and r.random() < 0.6:
            w.occ[0], w.occ[1] = 1, 1
            w.cond[0], w.cond[1] = r.choice([0, 0, 0x0e, 5, 0x0f]), r.choice([0, 0, 0x0e, 3, 0x0f])
        else:
            for s in (0, 1):
                if r.random() < 0.5:
                    w.cond[s] = r.choice([0, 0x0e, 0x0f, 0x10] +
                                         (COND_EDGE if r.random() < 0.15 else []))
    elif kind == 'glumph':
        w.npcs(kinds_bias=(KIND_GLUMPH,))
    elif kind == 'videad':
        w.npcs(style_bias=(NPC_VI,), kinds_bias=(KIND_VI,))
        for s in (0, 1):
            if r.random() < 0.3:
                w.cond[s] = r.choice([0, 0x0e, 0x0f])
        for s in range(8):
            if r.random() < 0.4:
                w.cond[s] = r.choice([0x0e, 0x0f, 0x10, 0] +
                                     (COND_EDGE if r.random() < 0.1 else []))
    elif kind == 'father':
        x = r.random()
        w.rpc = 0 if x < 0.25 else (1 if x < 0.9 else r.choice(BOOL_EDGE))
        w.sedexus = r.choice([0, 1, 2, 3, 4, 5, 6, 7, 6, 7]) if r.random() < 0.8 else \
            r.choice([-1, 8, 9, 0x100, 0x106, 0x7fffffff, 0x80000000])
        if 0 <= w.sedexus < 8 and r.random() < 0.5:
            w.occ[w.sedexus] = 1 if r.random() < 0.7 else r.choice([0] + BOOL_EDGE)
        w.notes['sedexus'] = w.sedexus
    elif kind == 'rec':
        deps = cat[1]
        if fact == 0x31a:
            w.facts[0x156] = r.choice([0, 0, 1, 1, 2, 0x7f, 0x80, 0xff])
        else:
            bits = i % (1 << len(deps))
            for b, d in enumerate(deps):
                w.facts[d] = r.choice([1, 1, 1, 2, 0x80, 0xff]) if bits >> b & 1 else 0
        w.notes['deps'] = ','.join('%x' % w.facts[d] for d in deps)
    w.commit()
    c.arg(fact)
    w.caps()
    w.finish_notes(fact)


def _evaluate_fact(ctx, bases):
    """unsigned char EvaluateFact(W8FactId)"""
    fn = ctx.fn(0x005080f0)
    # sweep: every id once
    step = max(1, int(round(1.0 / ctx.scale))) if ctx.scale < 1 else 1
    for fid in range(0, FACT_COUNT, step):
        if fid in SPECIAL:
            _special_case(ctx, fn, bases, fid, 0, 'sweep')
            continue
        r = ctx.rng('sweep', fid)
        c = ctx.case('evalfact.sweep.%03x.0' % fid, fn, conv='c', ret='u8')
        w = World(ctx, c, r, bases)
        w.light()
        w.facts[fid] = r.choice([0, 0, 1, 1, 2, 0x10, 0x80, 0xff])
        w.commit(full=False)
        c.arg(fid)
        w.caps()
        w.finish_notes(fid)
    # steered cases per special id
    for fact in sorted(SPECIAL):
        kind = SPECIAL[fact][0]
        count = PER_REC[fact] if kind == 'rec' else PER_FACT[kind]
        for i in range(ctx.n(count)):
            _special_case(ctx, fn, bases, fact, i, 'steer')


# --------------------------------------------------------------------------------------
SCALE_VALUES = [0, 1, -1, 2, 3, 4, 5, 7, 9, 10, 11, 13, 17, 33, 50, 99, 100, 101, 142, 333, -2, -3,
                -5, -7, -13, -99, -100, -101, 999, 1000, 12345, -12345,
                15339168, 15339169, -15339168, -15339169,        # *140 overflow
                35791394, 35791395, -35791394, -35791395,        # *60 overflow
                0x7fffffff, -0x80000000, 0x40000000, -0x40000000, 0x7ffffff0]
DIFF_EDGE = [3, 4, 0xff, 0x100, 0x102, -1, -2, 0x80000000, 0x80000002]


def _scale_value(r):
    x = r.random()
    if x < 0.4:
        return r.randrange(0, 400)
    if x < 0.55:
        return -r.randrange(1, 400)
    if x < 0.65:
        return r.randrange(-10 ** 6, 10 ** 6)
    if x < 0.72:
        return r.randrange(-2 ** 31, 2 ** 31)
    return r.choice(SCALE_VALUES)


def _difficulty(r):
    return r.choice([0, 1, 2]) if r.random() < 0.85 else r.choice(DIFF_EDGE)


def _scale_character(ctx):
    """void ScaleValueForCharacterDifficulty(int party_slot, int* value)"""
    fn = ctx.fn(0x0055cc00)
    settings = ctx.g('g_settings')
    val = ctx.scratch(0)
    for i in range(ctx.n(260)):
        r = ctx.rng('scalechar', i)
        c = ctx.case('scalechar.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        x = r.random()
        if x < 0.45:
            turn = 0
        elif x < 0.75:
            turn = r.randrange(1, 100)
        else:
            turn = r.choice([1, 2, 0xff, 0x100, 0x7fffffff, 0x80000000, 0xffffffff])
        diff = _difficulty(r)
        value = _scale_value(r)
        c.set(ctx.char(slot) + C_TURNCOAT, u32(turn))
        c.set(settings + SET_DIFFICULTY, u32(diff))
        c.set(val, u32(value))
        c.arg(slot)
        c.arg(val)
        c.cap(val, 4, 'value')
        c.note(slot=slot, turncoat=turn, difficulty=diff & 0xffffffff, value=value)


def _scale_monster(ctx):
    """void ScaleValueForMonsterDifficulty(W8MonsterInfo*, int* value)"""
    fn = ctx.fn(0x0055ccb0)
    settings = ctx.g('g_settings')
    val = ctx.scratch(0)
    mon = ctx.scratch(1)
    for i in range(ctx.n(260)):
        r = ctx.rng('scalemonster', i)
        c = ctx.case('scalemonster.%d' % i, fn, conv='c', ret='v')
        disp = r.choice([0, 1, 1, 2, 2]) if r.random() < 0.85 else r.choice([3, 4, 0x80, 0x81,
                                                                              0x82, 0xff])
        around = bytearray(r.getrandbits(8) for _ in range(5)) if r.random() < 0.6 else bytearray(5)
        around[MI_DISPOSITION - 0x14] = disp
        diff = _difficulty(r)
        value = _scale_value(r)
        c.set(mon + 0x14, bytes(around))
        c.set(settings + SET_DIFFICULTY, u32(diff))
        c.set(val, u32(value))
        c.arg(mon)
        c.arg(val)
        c.cap(val, 4, 'value')
        c.note(disposition=disp, difficulty=diff & 0xffffffff, value=value,
               around=bytes(around).hex())


def _fatigue_band(ctx):
    """int CalculateMonsterFatigueBand(int current, int maximum):
    100 - current*100 / (unsigned)maximum, bands at 50/70/85/95."""
    fn = ctx.fn(0x0052a780)
    n = ctx.n(300)
    for i in range(n):
        r = ctx.rng('fatigue', i)
        c = ctx.case('fatigueband.%d' % i, fn, conv='c', ret='i')
        if i < 2:
            cur, mx = r.choice([0, 50, -5]), 0           # divide by zero in both
        else:
            x = r.random()
            if x < 0.3:
                mx = r.choice([r.randrange(1, 200), r.randrange(1, 3000)])
                cur = r.randrange(0, mx + 1)
            elif x < 0.65:
                mx = r.choice([1, 2, 3, 7, 10, 20, 33, 100, 101, 150, 999, 1000, r.randrange(1, 5000)])
                loss = r.choice([49, 50, 51, 69, 70, 71, 84, 85, 86, 94, 95, 96, 0, 1, 99, 100])
                cur = mx * (100 - loss) // 100 + r.choice([-1, 0, 0, 1])
            elif x < 0.75:
                mx = r.randrange(1, 1000)
                cur = mx + r.choice([1, 2, mx, 10 * mx, r.randrange(1, 100000)])   # negative loss
            elif x < 0.85:
                mx = r.randrange(1, 1000)
                cur = r.choice([-1, -2, -mx, -100, -0x80000000, r.randrange(-10 ** 6, 0)])
            elif x < 0.93:
                mx = r.choice([r.randrange(1, 1000), -1, -2, -100, -0x80000000, 0x7fffffff])
                cur = r.randrange(0, 1000)
            else:
                mx = r.choice([1, 100, 1000, 42949672, r.randrange(1, 2 ** 31)])
                cur = r.choice([21474836, 21474837, 42949672, 42949673, 0x7fffffff, 0x40000000,
                                r.randrange(2 ** 24, 2 ** 31)])          # current*100 overflow
        c.arg(cur)
        c.arg(mx)
        c.note(current=cur, maximum=mx)
