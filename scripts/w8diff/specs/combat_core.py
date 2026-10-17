"""Combat.cpp (Local Code): the self-contained combat calculations and decisions.

Every case builds its own combat state in scratch 0 (wired into g_combat_state with
setp), writes the whole party-slot block g_status.buffers.XChar (8 rows x 0x106),
puts corpus characters into the 8 character slots (setb + small field edits) and
sets the gXStatus / g_status / g_level_block scalars the code reads (combat and
overlay modes, targeting mode, selected character, pending selection, ...).
g_status.greeting_pending = 1 in every case: QueueEntry then deletes any character
event a path queues (panic quote, partner-item complaint), so no event leaks into
the live queue. Targets used in the rows are only kinds 0 (none), 1 (party
member) and 2 (party): monster/group/place targets would reach live monster
positions and the camera. Functions that walk the live monster list get it
emptied for the call in 3/4 of their cases (PList iNumUsed = 0, restored after;
note monsters='hidden'), the rest run against the live list (monsters='live';
outside combat no monster is fInCombat, so those loops only read static fields).
Random() is srand(seed)-driven in both exes; rand_seq() models it so a few
specs pick seeds that force a branch (TryPanicWoundedCharacter).

Tested (retail address, name, cases):
  0x004ECEB0 CatchUpCombatActor            300  row in scratch / inside the state
  0x004EBC80 CanCharReBreathe              250  trait (race, Dracon Breath enchant), stamina/5
  0x004ED2B0 GetEffectivePartyAction       100
  0x004E7E70 IsPartyEngaged                200
  0x004ECDD0 RecordCharacterDeath          100  incl. count 8/9 (array overrun)
  0x004E8290 SetSlotAction                 150
  0x004ECF00 BeginCombatRound              150
  0x004ECE00 TryPanicWoundedCharacter      250  seeds chosen so half the rolls pass
  0x004ED2D0 TryCharacterAction            300  commit 0/1 (-> SwitchCharacterTo)
  0x004ED390 SwitchCharacterTo             200  incl. non defend/protect (assert)
  0x004E77B0 ChooseCombatAction            300  contexts 0,1,3..8 + invalid
  0x004E79A0 CharacterCanSwitchTo          400  incl. equipment repair path
  0x004E7CA0 AnyCharacterEngaged           100
  0x004ED550 CombatHasContinuingEffects    200
  0x004E89D0 AssignCombatPhases            300  incl. party movement phase, Snakespeed practice
  0x004EC1E0 GetConditionInterrupt         300  character source only
  0x004EC610 GetCombatActionProgress       300  (covers inlined GetCharacterTurnValue)
  0x004ECF50 RollCombatSurprise            100
  0x004ED460 CombatMayAdvanceContinuously  200
  0x004EB8C0 SetUpMonsterTurn              200  fake monster info/combat/3D object in scratch,
                                                species copied from live monster list 0..1

Skipped:
  0x004E7090 StartCombat                   combat start (allocates the state, resets world/UI)
  0x004E7590 ResetPartyCombatRows          not in port map (inlined); targeting UI side effects
  0x004ED710 QueueNpcCombatScript          true path queues NPC script lines/UI; false paths
                                           depend only on in-combat monster groups (none here)
  0x004EA1F0 ApplyCombatEndEffects         not in port map (inlined into EndCombat)
  0x004E8370 BeginCombatExecution          round orchestration (UI, notices, AI, world noise)
  0x004ED260 CombatLog                     varargs into a local buffer + optional notice
  0x004E82E0 DropCharacterFromRound        target highlights/UI + SetCharacterCombatAction
  0x004ECAA0 NotifyNearbyMonsters          live monster distances
  0x004ED1C0 PartyAvoidsSurprise           not in port map (inlined into RollCombatSurprise,
                                           reached only with an in-combat hostile monster)
  0x004EC860 GetCharacterTurnValue         not in port map (inlined); via GetCombatActionProgress
  0x004E76F0 EndMonsterTurn                monster AI target choice / aiming (live monsters)
  0x004EB7F0 EndMonsterAttack              monster AI (ChooseRandomMonsterAction), navigator
  0x004EA310 EndCombat                     combat end
  0x004E7CC0 ChooseAction                  executes actions, breath cycle, events
  0x004E7EE0 ApplyPartyCombatAction        not in port map; party movement UI
  0x004E8000 SetCharacterCombatAction      targeting UI (AimByKind/Repick), camera, notices
  0x004EC900 OrientMonsterTowardTarget     live monster facing
  0x004E8C30 AnyCombatMonsterBusy          not in port map; animation state
  0x004E8DA0 AutoAdvanceSelectedCharacter  not in port map; UI selection
  0x004E99C0 PracticeCombatRoundSkills     not in port map (inlined into AdvanceCombatRound)
  0x004E9B20 AdvanceCombatRound            round orchestration (time, sound, groups, sight)
  0x004E9F90 CheckCombatEnd                ends combat, music
  0x004EA5C0 ExecuteCharacterAction        executes spells/attacks/items
  0x004EAC90 ComputeCharacterActionPhase   not in port map (inlined into UpdateCombat)
  0x004EAE20 ExecuteMonsterAction          monster AI / movement
  0x004EB980 MonsterFleeAction             monster animation / world
  0x004ECB40 AimMonsterBreathAtTarget      not in port map; camera/world positions
  0x004EBA70 ExecuteMonsterSpecialAttack   world spell effects
  0x004EBFE0 ExecuteCharacterSpecialAttack breath visual, group attack resolution
  0x004EBCE0 CreateCharacterBreathEffect   spell visual creation, camera
  0x004EB5A0 StepMonsterCombatAction       camera, monster AI, sight refresh
  0x004ECC80 PointCameraAtCombatTarget     camera
  0x004E8EA0 UpdateCombat                  per-frame orchestration
  0x004E9490 ScheduleCombatActor           scheduler (opens screens, advances rounds, clocks)
"""
import struct

# Monster kinds are taken from the level's live list: "Before Bayjin" has no live monsters
# (plsMonsterList->iNumUsed == 0, data[] is heap garbage), here there are 14.
SAVE = 'Before Nessie'

# ---------------------------------------------------------------- layouts
CHAR = 0x1862
C_PROF = 0x69
C_RACE = 0x71
C_ATTR = 0xe5          # W8CharacterAttribute[7], 0x14 each, effective +4
C_SKILL = 0x19d        # W8CharacterSkill[0x29], 0x26 each
SK_STEP = 0x26
SK_ACTIVE, SK_POINTS, SK_LEVEL, SK_BASE, SK_PRACTICE = 0, 2, 6, 0xa, 0xe
C_COND = 0xa01         # unsigned uiCondition[20]
C_ENCH = 0xa65         # W8Enchantment[8], 0xc each: power +0, turns +8
C_HIGHEST = 0xb01
C_HPMAX, C_HP, C_STAMAX, C_STA = 0xb0d, 0xb11, 0xb19, 0xb1d
C_SPLEFT = 0xb45       # int iSPLeft[6]
C_SPELL_LEARNED = 0xbcd  # int spell_learned[136]
C_INIT = 0xe81
C_EQUIP = 0xf5d        # W8ItemInstance[12], 0xc each
C_BACKPACK = 0x1029    # W8ItemInstance[8]
ITEM = 0xc
CHAR_FLOATS = [0xb69, 0xb6d, 0xb71, 0xb75] + [0xb79 + 4 * k for k in range(12)]  # regen rates
C_HAND = 0x1149        # W8HandAttack[2], 0x5b each
H_STEP = 0x5b
H_HOLDS, H_INPLAY, H_ATTACKS, H_DMG = 0, 4, 0x15, 0x1d

ROW = 0x106            # W8PartySlotRow
R_OCC, R_PENDING, R_AMODE, R_PDET, R_TOUT = 0x0, 0x1, 0x5, 0x15, 0x1d
R_ACTION, R_DET0, R_DET1, R_TIN = 0x3d, 0x41, 0x45, 0x4d
R_AKIND, R_ADET, R_SPELL, R_SDET, R_STGT = 0x6d, 0x71, 0x75, 0x79, 0x81
R_IDET, R_ITGT, R_ITEMID, R_QUEUED, R_BTGT = 0xa1, 0xa9, 0xc9, 0xd0, 0xd1
R_ORDER, R_NPC, R_BERSERK = 0xf1, 0xfa, 0x104
XBLOCK = 8 * ROW

CS_SIZE = 0xa64        # W8CombatState
CS_EXEC, CS_RACTIVE, CS_RCOUNT, CS_RCOUNTER = 0x0, 0x1, 0x4, 0x8
CS_CHARS, CROW = 0x18, 0xd4
CS_EFF, CS_EFF0, EFF_STEP = 0x7c1, 0x85a, 0x11
CS_PDEATHS, CS_PDCOUNT = 0x8e8, 0x908
CS_NEXT, CS_CUR, CS_PPHASE, CS_STATUS = 0x90c, 0x910, 0x914, 0x918
CS_EQPHASE, CS_EQPEND, CS_PSURP, CS_MSURP, CS_ENGAGED = 0xa50, 0xa51, 0xa52, 0xa53, 0xa54
CS_NPCPEND = 0xa58
CR_PHASE, CR_DEAD, CR_SAVED, CR_HAV, CR_BERSERK, CR_STAMP = 0x0, 0x34, 0x38, 0x40, 0x80, 0x9c

GX_MODES = 0x8dc       # fCombatMode, fSpellCastMode, fItemSelectMode, fNpcDialogue, lock, trap
GX_HOSTILE = 0x8ed
GX_MONLIST = 0x8f5
GX_SURPRISE = 0x90d
GX_TARGETING = 0x92f
GX_DEFERRED = 0x19b5
MME, MME_NOTICE = 0x118, 0xea
GS_SELECTED = 0x1d
GS_POOL, GS_POOL_LEN = 0x21, 500 * ITEM + 4
GS_SIGHT_OVERRIDE = 0x22e3 + 0x4a
GS_SEARCH = 0x238f
GS_GREETING = 0x2497
LB_SEL = 0x2f0          # selection_kind, pending_action, selection_settled

MI_SPECIES, MI_P3D, MI_PCOMBAT = 0x8, 0xc, 0x10
MI_COND, MI_ENCH, MI_ACTION = 0x57, 0xa7, 0x2e1
MC_TURN_STARTED = 0x150
MON_SIZE = 0x348

SNAKESPEED = 0x27
W8_RACE_DRACON = 7
SPELLS = list(range(1, 0x72))
ACTIONS = [-1] * 3 + [0] * 6 + [1] * 2 + [2] * 2 + [3] + [4] * 4 + [5] * 3 + [6] + [7] * 4 + \
    [8] * 2 + [9] * 2 + [10, 11]
FREE = [0, 1, 2, 3, 5, 9, 10, 11, 19, 20, 49, 50, 51, 99, 100, 101, 255, 0x7fffffff,
        0x80000000, 0xfffffffe, 0xffffffff]


def p32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def p8(v):
    return bytes([int(v) & 0xff])


def slot_bytes(kind, ichar=-1, mon=-1, grp=-1):
    return struct.pack('<iiiifffI', kind, ichar, mon, grp, 0.0, 0.0, 0.0, 0)


def default_row(s, occupied=True):
    """A party-slot row with nothing chosen: no actions, empty targets."""
    b = bytearray(ROW)
    b[R_OCC] = 1 if occupied else 0
    struct.pack_into('<i', b, R_PENDING, -1)
    struct.pack_into('<4i', b, R_AMODE, -1, -1, -1, -1)
    for off in (R_TOUT, R_TIN, R_STGT, R_ITGT, R_BTGT):
        b[off:off + 0x20] = slot_bytes(0)
    struct.pack_into('<i', b, R_ACTION, -1)
    struct.pack_into('<i', b, R_AKIND, -1)
    struct.pack_into('<i', b, R_ITEMID, -1)
    b[R_QUEUED] = 0xff
    struct.pack_into('<i', b, R_ORDER, s)
    struct.pack_into('<i', b, R_NPC, -1)
    return b


BASE_XCHAR = b''.join(bytes(default_row(s, True)) for s in range(8))


def rand_target(r):
    kind = r.choice([0, 0, 1, 1, 1, 2])
    return slot_bytes(kind, r.randrange(8) if kind == 1 else -1)


# ---------------------------------------------------------------- Random() model
def rand_seq(seed, ranges):
    """Random(range) values the game produces after srand(seed) (MSVC rand LCG,
    Random = rand()*range/RAND_MAX % range, Random(0) does not call rand)."""
    s = seed & 0xffffffff
    out = []
    for rg in ranges:
        if rg == 0:
            out.append(0)
            continue
        s = (s * 214013 + 2531011) & 0xffffffff
        v = (s >> 16) & 0x7fff
        out.append(((v * rg) & 0xffffffff) // 0x7fff % rg)
    return out


def seed_where(r, ranges, pred, tries=4000):
    for _ in range(tries):
        sd = r.getrandbits(32)
        if pred(rand_seq(sd, ranges)):
            return sd
    return r.getrandbits(32)


def merge_ranges(rs, gap=24):
    out = []
    for lo, hi in sorted(rs):
        if out and lo <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return out


# ---------------------------------------------------------------- per-case builder
class Env:
    def __init__(self, ctx, c, r):
        self.ctx, self.c, self.r = ctx, c, r
        self.gx = ctx.g('gXStatus')
        self.gs = ctx.g('g_status')
        self.cs = ctx.scratch(0)
        self.xbase = (self.gs + 8).deref()
        self.party = {}
        self.rows = None
        self.state = None
        self.post = []
        self.globals_ops = []

    # -- characters
    def pick_party(self):
        for s in range(8):
            blob, name = self.ctx.pick_char(self.r)
            self.party[s] = [blob, bytes(blob), name, []]

    def ch(self, s):
        return self.party[s][0]

    def cput(self, s, off, data):
        blob = self.party[s][0]
        blob[off:off + len(data)] = data
        self.party[s][3].append((off, off + len(data)))

    def cu32(self, s, off, v):
        self.cput(s, off, p32(v))

    def cu8(self, s, off, v):
        self.cput(s, off, p8(v))

    def cget(self, s, off):
        return struct.unpack_from('<i', self.party[s][0], off)[0]

    def set_conditions(self, s, conds, keep_other=False):
        """conds: {index: turns}; rewrites uiCondition and a consistent highest_condition."""
        blob = self.ch(s)
        arr = [0] * 20 if not keep_other else [struct.unpack_from('<I', blob, C_COND + 4 * i)[0]
                                               for i in range(20)]
        for k, v in conds.items():
            arr[k] = v
        self.cput(s, C_COND, struct.pack('<20I', *[a & 0xffffffff for a in arr]))
        hi = max([i for i in range(20) if arr[i]] or [0])
        self.cu32(s, C_HIGHEST, hi)
        return hi

    def can_play(self, s, h):
        holds = self.cget(s, C_HAND + h * H_STEP + H_HOLDS)
        item = self.cget(s, C_EQUIP + (6 + h) * ITEM)
        return holds not in (1, 3) or item >= 0

    def tweak_hands(self, s, p=0.3):
        r = self.r
        for h in range(2):
            base = C_HAND + h * H_STEP
            if r.random() < p:
                if self.can_play(s, h):
                    self.cu8(s, base + H_INPLAY, r.choice([0, 1, 1]))
                else:
                    self.cu8(s, base + H_INPLAY, 0)
            if r.random() < p:
                self.cu32(s, base + H_ATTACKS, r.choice([0, 1, 1, 2, 2, 3, 4, 5, 8, 10]))
            if r.random() < p:
                self.cu32(s, base + H_DMG, r.choice([-10, -5, -1, 0, 1, 2, 3, 5, 7, 10, 25]))

    def tweak_health(self, s, p_dead=0.1, p_cond=0.25, cond_pool=None):
        r = self.r
        if r.random() < p_dead:
            self.cu32(s, C_HP, 0)
        elif r.random() < 0.2:
            mx = self.cget(s, C_HPMAX)
            self.cu32(s, C_HP, r.randrange(1, max(2, mx + 1)))
        if r.random() < p_cond:
            pool = cond_pool or list(range(1, 20))
            k = r.choice(pool)
            self.set_conditions(s, {k: r.choice([1, 3, 10, 9999])})

    # -- rows
    def new_row(self, s, occupied=True):
        return default_row(s, occupied)

    def detail_for(self, act):
        r = self.r
        if act == 7:
            return r.choice(SPELLS + [0])
        if act in (0, 1):
            return r.choice([-1, 0, 1, 2, 3, 4, 5, 6, 7, 8])
        return r.choice([-1, 0])

    def random_row(self, s, occupied=None, level='full'):
        """light: occupancy only; medium: + both chosen actions, their details and
        the two combat targets; full: every action/target block of the row."""
        r = self.r
        if occupied is None:
            occupied = r.random() < 0.85
        b = self.new_row(s, occupied)
        if level == 'light':
            return b
        if level == 'medium':
            pend = r.choice(ACTIONS)
            struct.pack_into('<i', b, R_PENDING, pend)
            struct.pack_into('<i', b, R_AMODE, self.detail_for(pend))
            act = r.choice(ACTIONS)
            struct.pack_into('<i', b, R_ACTION, act)
            struct.pack_into('<i', b, R_DET0, self.detail_for(act))
            if r.random() < 0.3:
                struct.pack_into('<i', b, R_DET1, r.choice([1, 2, 3, 4, 5, 6, 7, 8]))
            for off, p in ((R_TOUT, 0.5), (R_TIN, 0.6)):
                if r.random() < p:
                    b[off:off + 0x20] = rand_target(r)
            return b
        pend = r.choice(ACTIONS)
        struct.pack_into('<i', b, R_PENDING, pend)
        struct.pack_into('<i', b, R_AMODE, self.detail_for(pend))
        act = r.choice(ACTIONS)
        struct.pack_into('<i', b, R_ACTION, act)
        struct.pack_into('<i', b, R_DET0, self.detail_for(act))
        if r.random() < 0.5:
            struct.pack_into('<i', b, R_DET1, r.choice([1, 2, 3, 4, 5, 6, 7, 8]))
        if r.random() < 0.3:
            struct.pack_into('<i', b, R_PDET, r.choice([1, 2, 4, 7, 8]))
        for off, p in ((R_TOUT, 0.6), (R_TIN, 0.7), (R_STGT, 0.3), (R_ITGT, 0.3), (R_BTGT, 0.3)):
            if r.random() < p:
                b[off:off + 0x20] = rand_target(r)
        if r.random() < 0.3:
            akind = r.choice(ACTIONS)
            struct.pack_into('<i', b, R_AKIND, akind)
            struct.pack_into('<i', b, R_ADET, self.detail_for(akind))
            b[R_BERSERK] = 1 if akind == 1 else 0
        if r.random() < 0.5:
            struct.pack_into('<i', b, R_SPELL, r.choice(SPELLS))
            struct.pack_into('<i', b, R_SDET, r.choice([1, 2, 3, 4, 5, 6, 7]))
        return b

    def make_rows(self, occupied=None, level='medium', focus=None):
        self.rows = [self.random_row(s, None if occupied is None else occupied[s],
                                     'full' if s == focus else level) for s in range(8)]
        return self.rows

    def row_i32(self, s, off, v):
        struct.pack_into('<i', self.rows[s], off, int(v))

    def row_u8(self, s, off, v):
        self.rows[s][off] = int(v) & 0xff

    def item_ptr(self, s, field_off, owner):
        """Point a row's detail block item member at one of owner's own items."""
        r = self.r
        if r.random() < 0.6:
            addr = self.ctx.char(owner) + C_EQUIP + r.randrange(12) * ITEM
        else:
            addr = self.ctx.char(owner) + C_BACKPACK + r.randrange(8) * ITEM
        self.post.append(('setp', self.xbase + s * ROW + field_off, addr))

    def row(self, s):
        return self.xbase + s * ROW

    # -- combat state
    def new_state(self):
        self.state = bytearray(CS_SIZE)
        return self.state

    def st32(self, off, v):
        struct.pack_into('<I', self.state, off, int(v) & 0xffffffff)

    def st8(self, off, v):
        self.state[off] = int(v) & 0xff

    def crow(self, s):
        return CS_CHARS + s * CROW

    # -- globals
    def modes(self, combat=1, spell=0, item=0, npc=0, lock=0, trap=0, targeting=0, selected=None,
              sel=(-1, 0, 0), hostile=None, surprise=None):
        g = self.globals_ops
        g.append((self.gx + GX_MODES, bytes([combat, spell, item, npc, lock, trap])))
        g.append((self.gx + GX_TARGETING, p32(targeting)))
        if selected is None:
            selected = self.r.randrange(8)
        g.append((self.gs + GS_SELECTED, p32(selected)))
        g.append((self.gs + GS_GREETING, p8(1)))
        lb = self.ctx.g('g_level_block').deref() + LB_SEL
        g.append((lb, p32(sel[0]) + p32(sel[1]) + p8(sel[2])))
        if hostile is not None:
            g.append((self.gx + GX_HOSTILE, p32(hostile)))
        if surprise is not None:
            g.append((self.gx + GX_SURPRISE, p8(surprise)))

    def raw(self, addr, data):
        self.globals_ops.append((addr, data))

    def hide_monsters(self, p=0.75):
        """With probability p empty the live monster list for the call (its PList
        iNumUsed = 0, restored afterwards): the monster loops then cannot see
        anything that drifts in real time. Returns 'hidden' or 'live'."""
        if self.r.random() < p:
            self.raw((self.gx + GX_MONLIST).deref() + 8, p32(0))
            return 'hidden'
        return 'live'

    # -- emit everything (before args / caps)
    def emit(self):
        c, ctx = self.c, self.ctx
        for s in sorted(self.party):
            blob, orig, name, dirty = self.party[s]
            c.setb(ctx.char(s), orig)
            changed = [(k, k + 1) for lo, hi in dirty for k in range(lo, hi) if blob[k] != orig[k]]
            for lo, hi in merge_ranges(changed):
                c.set(ctx.char(s) + lo, bytes(blob[lo:hi]))
        if self.rows is not None:
            # the whole block, as a shared baseline blob plus the bytes that differ
            cur = b''.join(bytes(x) for x in self.rows)
            diff = [(k, k + 1) for k in range(XBLOCK) if cur[k] != BASE_XCHAR[k]]
            rngs = merge_ranges(diff, gap=40)
            if len(rngs) > 14:
                c.set(self.xbase, cur)
            else:
                c.setb(self.xbase, BASE_XCHAR)
                for lo, hi in rngs:
                    c.set(self.xbase + lo, cur[lo:hi])
        if self.state is not None:
            c.setp(ctx.g('g_combat_state'), self.cs)
            nz = [(i, i + 1) for i, v in enumerate(self.state) if v]
            for lo, hi in merge_ranges(nz, gap=12):
                c.set(self.cs + lo, bytes(self.state[lo:hi]))
        for addr, data in self.globals_ops:
            c.set(addr, data)
        for op in self.post:
            if op[0] == 'setp':
                c.setp(op[1], op[2])

    def cap_party(self, slots=range(8)):
        for s in slots:
            self.c.cap(self.ctx.char(s), CHAR, 'char%d' % s, floats=CHAR_FLOATS)

    def cap_rows(self):
        self.c.cap(self.xbase, XBLOCK, 'xchar', floats=[s * ROW + 0xf6 for s in range(8)])

    def cap_state(self):
        self.c.cap(self.cs, CS_SIZE, 'combat')


def pick_value(r, realistic, edges, p_edge=0.15):
    return r.choice(edges) if r.random() < p_edge else realistic()


# ---------------------------------------------------------------- cases
def cases_catchup(ctx):
    fn = ctx.fn(0x004eceb0)  # void CatchUpCombatActor(W8CombatCharacterRow*)
    for i in range(ctx.n(300)):
        r = ctx.rng('catchup', i)
        c = ctx.case('catchup.%d' % i, fn, conv='c', ret='v')
        e = Env(ctx, c, r)
        e.new_state()
        rc = pick_value(r, lambda: r.randrange(1, 101),
                        [0, 1, 2, 9, 10, 11, 90, 99, 100, 101, 150, 0x7fffffff, 0xffffffff], 0.2)
        action = r.choice([0, 0, 0, 1, 2])
        e.st32(CS_RCOUNTER, rc)
        e.st32(CS_CUR, action)
        stamp = pick_value(r, lambda: r.randrange(0, (rc if 0 < rc <= 100 else 100) + 1),
                           [0, 1, rc, rc + 1, 100, 101, 0xffffffff], 0.2)
        phase = pick_value(r, lambda: r.randrange(0, 101), FREE, 0.2)
        inside = r.random() < 0.4
        if inside:
            k = r.randrange(8)
            off = e.crow(k)
            e.st32(off + CR_PHASE, phase)
            e.st32(off + CR_STAMP, stamp)
            e.st8(off + CR_DEAD, r.choice([0, 1]))
            row = e.cs + off
        else:
            row = ctx.scratch(1)
        e.emit()
        if not inside:
            c.set(row + CR_PHASE, p32(phase))
            c.set(row + CR_STAMP, p32(stamp))
            c.set(row + CR_DEAD, p8(r.choice([0, 1])))
        c.arg(row)
        c.cap(ctx.scratch(1), CROW, 'row')
        e.cap_state()
        c.note(round_counter=rc, party_action=action, phase=phase, stamp=stamp, inside=inside)


def cases_rebreathe(ctx):
    fn = ctx.fn(0x004ebc80)  # bool CanCharReBreathe(int party_slot)
    for i in range(ctx.n(250)):
        r = ctx.rng('rebreathe', i)
        c = ctx.case('rebreathe.%d' % i, fn, conv='c', ret='b')
        e = Env(ctx, c, r)
        e.pick_party()
        s = r.randrange(8)
        race = r.choice([W8_RACE_DRACON] * 4 + list(range(0, 16)) + [-1])
        e.cu32(s, C_RACE, race)
        if r.random() < 0.3:
            e.cu32(s, C_PROF, r.choice(list(range(15)) + [-1]))
        ench = r.choice([0, 0, 0, 1, 5, 0x80000000])
        e.cu32(s, C_ENCH + 1 * 0xc + 8, ench)
        mx = pick_value(r, lambda: r.randrange(20, 400),
                        [0, 1, 4, 5, 6, 9, 10, 0x7fffffff, -1, -5, -100, 0x80000000], 0.25)
        q = (mx & 0xffffffff) // 5
        q = q - (1 << 32) if q >= (1 << 31) else q
        sta = r.choice([q - 1, q, q + 1, 0, -1, q * 2, r.randrange(-10, 400), -0x80000000,
                        0x7fffffff])
        e.cu32(s, C_STAMAX, mx)
        e.cu32(s, C_STA, sta)
        e.emit()
        c.arg(s)
        e.cap_party([s])
        c.note(slot=s, race=race, breath_turns=ench, stamina_max=mx, stamina=sta)


def cases_effective_party_action(ctx):
    fn = ctx.fn(0x004ed2b0)  # W8PartyAction GetEffectivePartyAction(void)
    vals = [0, 1, 2, 3, -1, 4, 0x80000000]
    for i in range(ctx.n(100)):
        r = ctx.rng('effaction', i)
        c = ctx.case('effaction.%d' % i, fn, conv='c', ret='i')
        e = Env(ctx, c, r)
        e.new_state()
        st, nx, cu = r.choice(vals[:4] * 3 + vals), r.choice(vals), r.choice(vals)
        e.st32(CS_STATUS, st)
        e.st32(CS_NEXT, nx)
        e.st32(CS_CUR, cu)
        e.emit()
        e.cap_state()
        c.note(status=st, next=nx, current=cu)


def party_health(e, r, p_dead=0.15, p_cond=0.3, pool=None):
    for s in range(8):
        e.tweak_health(s, p_dead, p_cond, pool)


def cases_is_party_engaged(ctx):
    fn = ctx.fn(0x004e7e70)  # int IsPartyEngaged(void)
    for i in range(ctx.n(200)):
        r = ctx.rng('engaged', i)
        c = ctx.case('engaged.%d' % i, fn, conv='c', ret='i')
        e = Env(ctx, c, r)
        e.pick_party()
        party_health(e, r, 0.15, 0.35, [5, 10, 13, 14, 14, 15, 15, 16, 17, 18, 19])
        edge = None
        if r.random() < 0.06:  # out-of-domain highest_condition: retail compares unsigned
            edge = r.choice([20, 0xffffffff, 0x80000000])
            e.cu32(r.randrange(8), C_HIGHEST, edge)
        e.make_rows(level='light')
        e.new_state()
        st = r.choice([0] * 6 + [1, 2, 3])
        cu = r.choice([0] * 5 + [1, 2])
        e.st32(CS_STATUS, st)
        e.st32(CS_CUR, cu)
        for s in range(8):
            e.st8(e.crow(s) + CR_DEAD, 1 if r.random() < 0.2 else 0)
        e.emit()
        e.cap_state()
        c.note(status=st, current=cu, invalid_highest_condition=edge)


def cases_record_death(ctx):
    fn = ctx.fn(0x004ecdd0)  # void RecordCharacterDeath(int party_slot)
    for i in range(ctx.n(100)):
        r = ctx.rng('death', i)
        c = ctx.case('death.%d' % i, fn, conv='c', ret='v')
        e = Env(ctx, c, r)
        e.new_state()
        count = r.choice(list(range(8)) * 4 + [8, 9])
        e.st32(CS_PDCOUNT, count)
        for k in range(min(count, 8)):
            e.st32(CS_PDEATHS + 4 * k, r.randrange(8))
        combat = 0 if r.random() < 0.15 else 1
        e.modes(combat=combat)
        slot = r.choice(list(range(8)) * 3 + [-1, 8, 0x7fffffff])
        e.emit()
        c.arg(slot)
        e.cap_state()
        c.note(count=count, slot=slot, combat=combat)


def cases_set_slot_action(ctx):
    fn = ctx.fn(0x004e8290)  # void SetSlotAction(int, W8ActionKind, int)
    for i in range(ctx.n(150)):
        r = ctx.rng('setslot', i)
        c = ctx.case('setslot.%d' % i, fn, conv='c', ret='v')
        e = Env(ctx, c, r)
        e.make_rows(level='light')
        e.emit()
        s = r.randrange(8)
        kind = r.choice(list(range(-1, 12)) * 2 + [12, -2, 0x7fffffff, 0x101])
        detail = r.choice([-1, 0, 1, 2, 5, 8, 0x71, 0x7fffffff, r.randrange(-100, 100)])
        c.arg(s).arg(kind).arg(detail)
        e.cap_rows()
        c.note(slot=s, kind=kind, detail=detail)


def cases_begin_round(ctx):
    fn = ctx.fn(0x004ecf00)  # void BeginCombatRound(void)
    for i in range(ctx.n(150)):
        r = ctx.rng('beginround', i)
        c = ctx.case('beginround.%d' % i, fn, conv='c', ret='v')
        e = Env(ctx, c, r)
        e.make_rows(level='light')
        for s in range(8):
            e.row_i32(s, R_PENDING, 9 if r.random() < 0.4 else r.choice(ACTIONS))
        e.new_state()
        e.st8(CS_EQPHASE, r.choice([0, 1, 2, 0xff]))
        e.st8(CS_EQPEND, r.choice([0, 1, 3, 8]))
        e.st8(CS_PSURP, 1)
        combat = 0 if r.random() < 0.2 else 1
        e.modes(combat=combat)
        e.emit()
        e.cap_rows()
        e.cap_state()
        c.note(combat=combat)


def cases_panic(ctx):
    fn = ctx.fn(0x004ece00)  # bool TryPanicWoundedCharacter(const W8CombatSlot*)
    for i in range(ctx.n(250)):
        r = ctx.rng('panic', i)
        c = ctx.case('panic.%d' % i, fn, conv='c', ret='b')
        e = Env(ctx, c, r)
        e.pick_party()
        s = r.randrange(8)
        kind = r.choice([1] * 12 + [0, 2, 3, 9])
        mx = pick_value(r, lambda: r.randrange(5, 400),
                        [1, 2, 3, 50, 99, 100, 101, 200, 0x7fffffff, 0xffffffff, 0x10000000], 0.25)
        m = mx & 0xffffffff
        k = r.choice([0, 1, 10, 30, 48, 49, 50, 51, 52, 70, 100, 101])
        hp = r.choice([m * k // 100, m * k // 100 + 1, max(0, m * k // 100 - 1), 0,
                       42949672, 42949673, 0x7fffffff, r.randrange(0, m + 2)])
        e.cu32(s, C_HPMAX, mx)
        e.cu32(s, C_HP, hp)
        e.modes(combat=0)
        e.emit()
        tgt = ctx.scratch(1)
        c.set(tgt, slot_bytes(kind, s if kind in (1, 9) else r.choice([-1, s])))
        forced = r.random() < 0.5
        if forced:
            limit = r.choice([15, 15, 15, 16])  # 15 = g_flee_chance; 16 also hits roll 15
            c.seed = seed_where(r, [100], lambda v: v[0] < limit)
        c.arg(tgt)
        c.cap(tgt, 0x20, 'target')
        e.cap_party([s])
        c.note(slot=s, kind=kind, hp=hp, hp_max=mx, roll=rand_seq(c.seed, [100])[0])


def combat_party(e, r, combat=None, targeting=None, rows=True, focus=None):
    """Common setup for the action-choice functions: party, rows (the focus slot's
    row fully random, the others medium), state, modes."""
    e.pick_party()
    party_health(e, r, 0.1, 0.3, [1, 4, 5, 6, 10, 11, 12, 13, 13, 14, 15, 16, 17, 18])
    for s in range(8):
        e.tweak_hands(s, 0.2)
        if r.random() < 0.15:
            e.cu32(s, C_ENCH + 0xc + 8, r.choice([1, 3]))
        if r.random() < 0.15:
            mx = e.cget(s, C_STAMAX)
            e.cu32(s, C_STA, r.choice([0, mx // 5 - 1, mx // 5, mx // 5 + 1, mx]))
    if rows:
        e.make_rows(level='medium', focus=focus)
    e.new_state()
    for s in range(8):
        e.st8(e.crow(s) + CR_DEAD, 1 if r.random() < 0.3 else 0)
    if combat is None:
        combat = 0 if r.random() < 0.15 else 1
    if targeting is None:
        targeting = r.choice([0, 0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8])
    sel = (-1, 0, 0)
    roll = r.random()
    if roll < 0.06:
        sel = (7, r.choice(SPELLS), 1)
    elif roll < 0.10:
        sel = (8, -1, 1)
    elif roll < 0.15:
        sel = (r.choice(ACTIONS), r.choice([-1, 0, 5]), r.choice([0, 1]))
    e.modes(combat=combat, targeting=targeting, sel=sel, hostile=r.choice([0, 1, 3]))
    return combat, targeting, sel


def cases_try_action(ctx):
    fn = ctx.fn(0x004ed2d0)  # bool TryCharacterAction(int, W8ActionKind, bool commit)
    for i in range(ctx.n(300)):
        r = ctx.rng('tryaction', i)
        c = ctx.case('tryaction.%d' % i, fn, conv='c', ret='b')
        e = Env(ctx, c, r)
        s = r.randrange(8)
        combat, targeting, sel = combat_party(e, r, focus=s)
        action = r.choice([4] * 5 + [5] * 3 + [-1] * 2 + ACTIONS)
        if r.random() < 0.4:
            e.row_i32(s, R_ACTION, action)
        if r.random() < 0.4:
            e.row_i32(s, R_PENDING, action)
        commit = r.choice([0, 1])
        e.emit()
        c.arg(s).arg(action).arg(commit)
        e.cap_rows()
        e.cap_state()
        c.note(slot=s, action=action, commit=commit, combat=combat, targeting=targeting)


def cases_switch_to(ctx):
    fn = ctx.fn(0x004ed390)  # void SwitchCharacterTo(int, W8ActionKind)
    for i in range(ctx.n(200)):
        r = ctx.rng('switchto', i)
        c = ctx.case('switchto.%d' % i, fn, conv='c', ret='v')
        e = Env(ctx, c, r)
        s = r.randrange(8)
        e.make_rows(level='medium', focus=s)
        e.new_state()
        for k in range(8):
            e.st8(e.crow(k) + CR_DEAD, r.choice([0, 1]))
            e.st8(e.crow(k) + 0xa4, r.choice([0, 0, 1]))
        action = r.choice([4] * 9 + [5] * 9 + [-1, 0, 1, 7, 9, 11])
        if r.random() < 0.4:
            e.row_i32(s, R_ACTION, r.choice([4, 5, action]))
        e.modes(combat=1)
        e.emit()
        c.arg(s).arg(action)
        e.cap_rows()
        e.cap_state()
        c.note(slot=s, action=action)


def cases_choose_action(ctx):
    fn = ctx.fn(0x004e77b0)  # void ChooseCombatAction(int, ctx, kind*, int*, slot**, detail**)
    for i in range(ctx.n(300)):
        r = ctx.rng('chooseact', i)
        c = ctx.case('chooseact.%d' % i, fn, conv='c', ret='v')
        e = Env(ctx, c, r)
        s = r.randrange(8)
        combat, targeting, sel = combat_party(e, r, focus=s)
        context = r.choice([0, 0, 1, 1, 1, 3, 4, 5, 6, 6, 7, 8] * 3 + [9, -1, 0x7fffffff])
        valid = context in (0, 1, 3, 4, 5, 6, 7, 8)
        e.emit()
        out = ctx.scratch(1)
        c.set(out, p32(0xdeadbeef) * 4)
        c.arg(s).arg(context)
        c.arg(out if r.random() < 0.9 else 0)
        c.arg(out + 4 if r.random() < 0.9 else 0)
        c.arg(out + 8 if r.random() < 0.5 else 0)
        c.arg(out + 12 if r.random() < 0.5 else 0)
        c.cap(out, 0x10, 'out', ignore=[8, 12] if valid else [])
        c.note(slot=s, context=context, combat=combat, selection=list(sel))


def cases_can_switch(ctx):
    fn = ctx.fn(0x004e79a0)  # bool CharacterCanSwitchTo(int, ctx, bool, bool)
    for i in range(ctx.n(400)):
        r = ctx.rng('canswitch', i)
        c = ctx.case('canswitch.%d' % i, fn, conv='c', ret='b')
        e = Env(ctx, c, r)
        s = r.randrange(8)
        combat, targeting, sel = combat_party(e, r, focus=s)
        context = r.choice([0, 0, 1, 1, 1, 1, 3, 4, 5, 6, 6, 7, 8])
        allow_missing = r.choice([1, 1, 0])
        allow_equip = r.choice([0, 0, 1])
        # make the row's actions interesting for this slot
        act = r.choice([0, 0, 1, 2, 4, 5, 7, 7, 8, 8, 3, 6, 9, -1])
        learned = [k for k in SPELLS if e.cget(s, C_SPELL_LEARNED + 4 * k) == 1]
        for off_k, off_d in ((R_ACTION, R_DET0), (R_PENDING, R_AMODE)):
            if r.random() < 0.7:
                e.row_i32(s, off_k, act)
                detail = e.detail_for(act)
                if act == 7 and learned and r.random() < 0.7:
                    detail = r.choice(learned)
                e.row_i32(s, off_d, detail)
        if learned and r.random() < 0.4:
            e.row_i32(s, R_SPELL, r.choice(learned))
        if r.random() < 0.3:
            realm = r.randrange(6)
            sp = e.cget(s, C_SPLEFT + 4 * realm)
            e.cu32(s, C_SPLEFT + 4 * realm, r.choice([0, 1, 2, 3, 5, sp // 2, sp]))
        if r.random() < 0.5:
            e.item_ptr(s, R_DET1 + 4, s)
        if r.random() < 0.3:
            e.item_ptr(s, R_PDET + 4, s)
        if r.random() < 0.3:
            e.item_ptr(s, R_IDET + 4, s)
        if r.random() < 0.3:
            e.cu32(s, C_RACE, W8_RACE_DRACON)
        e.emit()
        c.arg(s).arg(context).arg(allow_missing).arg(allow_equip)
        e.cap_party([s])
        e.cap_rows()
        c.note(slot=s, context=context, allow_missing=allow_missing, allow_equip=allow_equip,
               action=act, combat=combat, targeting=targeting, selection=list(sel))


def cases_any_engaged(ctx):
    fn = ctx.fn(0x004e7ca0)  # bool AnyCharacterEngaged(void)
    for i in range(ctx.n(100)):
        r = ctx.rng('anyengaged', i)
        c = ctx.case('anyengaged.%d' % i, fn, conv='c', ret='b')
        e = Env(ctx, c, r)
        e.pick_party()
        p_ok = r.choice([0.0, 0.1, 0.3, 0.6])
        occ = []
        for s in range(8):
            good = r.random() < p_ok
            occ.append(good or r.random() < 0.5)
            if not good:
                if r.random() < 0.5:
                    e.cu32(s, C_HP, 0)
                else:
                    e.set_conditions(s, {r.choice([13, 14, 15, 18, 19]): 5})
            elif r.random() < 0.3:
                e.set_conditions(s, {r.choice([1, 6, 11, 12]): 5})
        e.make_rows(occupied=occ, level='light')
        e.emit()
        c.note(p_ok=p_ok)


def cases_continuing_effects(ctx):
    fn = ctx.fn(0x004ed550)  # bool CombatHasContinuingEffects(void)
    for i in range(ctx.n(200)):
        r = ctx.rng('conteff', i)
        c = ctx.case('conteff.%d' % i, fn, conv='c', ret='b')
        e = Env(ctx, c, r)
        e.pick_party()
        for s in range(8):
            e.cput(s, C_ENCH, bytes(8 * 0xc))
        e.make_rows(level='light')
        e.new_state()
        what = r.choice(['none', 'none', 'char', 'char', 'eff', 'eff0', 'many'])
        if what in ('char', 'many'):
            s = r.randrange(8)
            k = r.randrange(8)
            e.cput(s, C_ENCH + k * 0xc, p32(r.choice([1, 5])) + p32(0) + p32(
                r.choice([1, 2, 10, 0x80000000, 0xffffffff])))
        if what in ('eff', 'many'):
            e.st8(CS_EFF + r.randrange(9) * EFF_STEP, r.choice([1, 0xff]))
        if what in ('eff0', 'many'):
            e.st8(CS_EFF0 + r.randrange(6) * EFF_STEP, r.choice([1, 0x80]))
        mons = e.hide_monsters()
        e.emit()
        c.note(what=what, monsters=mons)


def cases_assign_phases(ctx):
    fn = ctx.fn(0x004e89d0)  # void AssignCombatPhases(void)
    for i in range(ctx.n(300)):
        r = ctx.rng('phases', i)
        c = ctx.case('phases.%d' % i, fn, conv='c', ret='v')
        e = Env(ctx, c, r)
        e.pick_party()
        party_health(e, r, 0.1, 0.3, [1, 5, 10, 13, 14, 14, 15, 15, 16, 17, 18])
        for s in range(8):
            e.tweak_hands(s, 0.4)
            if r.random() < 0.4:
                e.cu32(s, C_INIT, pick_value(r, lambda: r.randrange(-5, 60),
                                             [-100, -11, -10, -9, 85, 86, 87, 89, 90, 200,
                                              0x7fffffff, -0x80000000], 0.25))
            if r.random() < 0.5:
                sk = C_SKILL + SNAKESPEED * SK_STEP
                e.cu8(s, sk + SK_ACTIVE, r.choice([0, 1, 1]))
                e.cu32(s, sk + SK_POINTS, r.choice([0, 1, 10, 50, 99, 100]))
                e.cu32(s, sk + SK_BASE, r.choice([0, 1, 20, 50, 100]))
                e.cu32(s, sk + SK_PRACTICE, r.choice([0, 6, 7, 7]))
        e.make_rows()
        for s in range(8):
            if r.random() < 0.5:
                e.row_i32(s, R_ACTION, r.choice([0, 1]))
        e.new_state()
        e.st8(CS_PSURP, 1 if r.random() < 0.1 else 0)
        e.st8(CS_MSURP, 1 if r.random() < 0.1 else 0)
        mv = r.choice([0] * 6 + [1, 2])
        e.st32(CS_CUR, mv)
        e.st32(CS_RCOUNTER, r.choice([1, 10, 50]))
        hostile = r.choice([0, 1, 1, 3])
        e.modes(combat=1, hostile=hostile)
        mons = e.hide_monsters()
        e.emit()
        e.cap_party()
        e.cap_rows()
        e.cap_state()
        c.cap(e.gs + GS_POOL, GS_POOL_LEN, 'party_pool')
        c.cap(e.gx + GX_DEFERRED, 1, 'deferred_skill_notices')
        for s in range(8):
            c.cap(e.gx + s * MME + MME_NOTICE + SNAKESPEED, 1, 'snake_notice%d' % s)
        c.note(party_action=mv, hostile=hostile, monsters=mons)


def cases_condition_interrupt(ctx):
    fn = ctx.fn(0x004ec1e0)  # int GetConditionInterrupt(W8TargetSource*)
    for i in range(ctx.n(300)):
        r = ctx.rng('interrupt', i)
        c = ctx.case('interrupt.%d' % i, fn, conv='c', ret='i')
        e = Env(ctx, c, r)
        s = r.randrange(8)
        combat_party(e, r, combat=1, focus=s)
        conds = {}
        for k, p in ((4, 0.3), (6, 0.3), (11, 0.3), (12, 0.3), (13, 0.3), (14, 0.2)):
            if r.random() < p:
                conds[k] = r.choice([1, 2, 5, 9999])
        hi = e.set_conditions(s, conds)
        if r.random() < 0.5:
            e.cu32(s, C_ATTR + 4, pick_value(r, lambda: r.randrange(1, 126),
                                             [0, 1, 2, 3, 5, 6, 299, 300, 301, 0xffffffff], 0.2))
        if r.random() < 0.3:
            e.cu32(s, C_PROF, r.randrange(15))
        if 13 in conds and r.random() < 0.5:
            other = r.randrange(8)
            e.set_conditions(other, {13: 5}, keep_other=True)
        if r.random() < 0.3:
            e.row_i32(s, R_PENDING, 11)
        e.st8(e.crow(s) + CR_BERSERK, 1 if r.random() < 0.3 else 0)
        e.st8(CS_ENGAGED, r.choice([0, 1]))
        e.st32(CS_RCOUNT, r.choice([0, 1, 2, 5]))
        e.emit()
        src = ctx.scratch(1)
        c.set(src, p32(1) + p32(s) + p32(-1))
        c.arg(src)
        e.cap_party([s])
        c.cap(e.gs + GS_POOL, GS_POOL_LEN, 'party_pool')
        c.note(slot=s, conditions=sorted(conds), highest=hi)


def cases_action_progress(ctx):
    fn = ctx.fn(0x004ec610)  # short GetCombatActionProgress(int* out_total)
    for i in range(ctx.n(300)):
        r = ctx.rng('progress', i)
        c = ctx.case('progress.%d' % i, fn, conv='c', ret='i16')
        e = Env(ctx, c, r)
        combat, targeting, sel = combat_party(e, r, combat=1 if r.random() < 0.95 else 0)
        mv = r.choice([0] * 6 + [1, 2])
        e.st32(CS_CUR, mv)
        e.st32(CS_STATUS, r.choice([0, 0, 1, 2, 3, 3]))
        for s in range(8):
            off = e.crow(s)
            e.st32(off + CR_PHASE, r.choice([0, 10, 50, 99, 100, 100, 101]))
            sav = [r.choice([0, 1, 2, 3, 5]) for _ in range(2)]
            hav = [min(sav[h], r.choice([0, 1, 2, 5])) for h in range(2)]
            if r.random() < 0.05:
                hav[0] = sav[0] + r.choice([1, 7])
            e.st32(off + CR_SAVED, sav[0])
            e.st32(off + CR_SAVED + 4, sav[1])
            e.st32(off + CR_HAV, hav[0])
            e.st32(off + CR_HAV + 4, hav[1])
        mons = e.hide_monsters()
        e.emit()
        out = ctx.scratch(1)
        with_out = r.random() < 0.85
        c.arg(out if with_out else 0)
        c.cap(out, 4, 'total')
        c.note(party_action=mv, combat=combat, targeting=targeting, monsters=mons)


def cases_roll_surprise(ctx):
    fn = ctx.fn(0x004ecf50)  # void RollCombatSurprise(char party_cannot_be_surprised)
    for i in range(ctx.n(100)):
        r = ctx.rng('surprise', i)
        c = ctx.case('surprise.%d' % i, fn, conv='c', ret='v')
        e = Env(ctx, c, r)
        e.new_state()
        e.st8(CS_RACTIVE, 1)
        combat = 0 if r.random() < 0.05 else 1
        surprise = r.choice([0, 1])
        e.modes(combat=combat, surprise=surprise)
        sight = r.choice([0, 0, 1])
        search = r.choice([0, 0, 1])
        e.raw(e.gs + GS_SIGHT_OVERRIDE, p8(sight))
        e.raw(e.gs + GS_SEARCH, p8(search))
        arg = r.choice([0, 0, 1, 1, 0x100, 0xff, 0x101])
        mons = e.hide_monsters()
        e.emit()
        c.arg(arg)
        e.cap_state()
        c.note(arg=arg, sight_override=sight, search=search, surprise_possible=surprise,
               combat=combat, monsters=mons)


def cases_may_advance(ctx):
    fn = ctx.fn(0x004ed460)  # bool CombatMayAdvanceContinuously(void)
    for i in range(ctx.n(200)):
        r = ctx.rng('advance', i)
        c = ctx.case('advance.%d' % i, fn, conv='c', ret='b')
        e = Env(ctx, c, r)
        combat, targeting, sel = combat_party(e, r, combat=r.choice([0, 1, 1]))
        for s in range(8):
            if r.random() < 0.3:
                act = r.choice([0, 1, 2, 3, 7, 7, 8])
                e.row_i32(s, R_ACTION, act)
                e.row_i32(s, R_DET0, e.detail_for(act))
        # CharacterActionTargetsEnemies dereferences a use-item action's item without
        # a null check once the eligibility shortcut passed: give every such row one.
        for s in range(8):
            if struct.unpack_from('<i', e.rows[s], R_ACTION)[0] == 8:
                e.item_ptr(s, R_DET1 + 4, s)
        e.st8(CS_NPCPEND, 1 if r.random() < 0.2 else 0)
        e.st8(CS_NPCPEND + 1, 1 if r.random() < 0.2 else 0)
        mons = e.hide_monsters()
        e.emit()
        c.note(combat=combat, targeting=targeting, monsters=mons)


def cases_monster_turn(ctx):
    fn = ctx.fn(0x004eb8c0)  # void SetUpMonsterTurn(W8MonsterInfo*)
    gx = ctx.g('gXStatus')
    for i in range(ctx.n(200)):
        r = ctx.rng('monturn', i)
        c = ctx.case('monturn.%d' % i, fn, conv='c', ret='v')
        mi, p3d, pc = ctx.scratch(2), ctx.scratch(3), ctx.scratch(4)
        k = r.choice([0, 0, 1])
        species = (((gx + GX_MONLIST).deref().deref() + 4 * k).deref() + MI_SPECIES).deref()
        c.setp(mi + MI_SPECIES, species)
        c.setp(mi + MI_P3D, p3d)
        c.setp(mi + MI_PCOMBAT, pc)
        action = r.choice([9, 9, 7, 7, 0, 1, 2, 3, 4, 5, 6, 8, -1])
        c.set(mi + MI_ACTION, p32(action))
        haste_turns = r.choice([0, 0, 0, 1, 3, 0x80000000])
        haste_power = r.choice([0, 1, 2, 5, 10, 25, 0x7fffffff, 0x1999999a])
        c.set(mi + MI_ENCH + 5 * 0xc, p32(haste_power))
        c.set(mi + MI_ENCH + 5 * 0xc + 8, p32(haste_turns))
        slowed = r.choice([0, 0, 1, 5, 9999])
        c.set(mi + MI_COND + 5 * 4, p32(slowed))
        started = 1 if r.random() < 0.15 else 0
        c.set(pc + MC_TURN_STARTED, p8(started))
        prog = r.choice([0.0, 0.5, 1234.5])
        c.set(p3d + 0x134, struct.pack('<f', prog))
        c.set(p3d + 0x3e, p8(1))
        c.arg(mi)
        c.cap(p3d, MON_SIZE, 'monster3d', floats=[0x130, 0x134])  # movement callback threshold/progress
        c.cap(pc, 0x153, 'monster_combat')
        c.cap(mi, 0x425, 'monster_info')
        c.note(list_index=k, action=action, haste_turns=haste_turns, haste_power=haste_power,
               slowed=slowed, turn_started=started)


def cases(ctx):
    cases_catchup(ctx)
    cases_rebreathe(ctx)
    cases_effective_party_action(ctx)
    cases_is_party_engaged(ctx)
    cases_record_death(ctx)
    cases_set_slot_action(ctx)
    cases_begin_round(ctx)
    cases_panic(ctx)
    cases_try_action(ctx)
    cases_switch_to(ctx)
    cases_choose_action(ctx)
    cases_can_switch(ctx)
    cases_any_engaged(ctx)
    cases_continuing_effects(ctx)
    cases_assign_phases(ctx)
    cases_condition_interrupt(ctx)
    cases_action_progress(ctx)
    cases_roll_surprise(ctx)
    cases_may_advance(ctx)
    cases_monster_turn(ctx)
    # the core takes at most 96 set-up/cap operations and 16 argument words per case
    for c in ctx.cases:
        if len(c.ops) > 92 or len(c.args) > 16:
            raise ValueError('%s: %d ops, %d args' % (c.id, len(c.ops), len(c.args)))
