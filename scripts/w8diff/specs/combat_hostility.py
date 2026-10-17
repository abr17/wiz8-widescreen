"""Combat Hostility.cpp + Combat Party Movement.cpp.

Monster lists, monster records and the combat state are built in scratch
memory and wired in for the call (gXStatus.plsMonsterList / plsUnbornMonsterList
-> scratch W8PList, gXStatus.monster_record_cache[species] -> scratch
W8MonsterRecord, g_combat_state -> scratch W8CombatState), so nothing depends on
the live world of the loaded save. Characters come from the corpus unmodified
(setb) with small field overrides on top (set), so no new blobs are added.
Float results (GetPartyMovementSpeed, PartyMovementReachedPhaseLimit,
StartPartyMovementAction's move limit) assume both processes run with the same
native FPU control word (compare.py reports cw-native).

Tested (case counts at --scale 1):
  0x00546f80 MonsterHostility                    300
  0x00546f10 MonsterVsCharDisposition            200
  0x00547010 CharacterVsCharacterDisposition     200
  0x00547080 GetOppositeDisposition              260
  0x00547310 CharacterActionTargetsEnemies       400
  0x00547440 MonsterActionTargetsEnemies         200
  0x005474b0 MonsterCanAimSpell                  170
  0x00547510 CombatAllowsLiveGroups               72
  0x005477d0 SetMonsterHostility                 260
  0x00546e70 RecountCombatMonsters               200
  0x00547bf0 CanPartySlotTurnUndead              250
  0x00547f40 CanPartySlotPray                    250
  0x004f0480 RoundPhaseToStep                    400
  0x004f0500 GetPhaseStep                         20
  0x004f0520 SetPendingMoveKind                   40
  0x004f0800 CanPartyMove                        200
  0x004effa0 GetPartyMovementSpeed               300  (covers inlined GetPartyHasteSteps)
  0x004efe70 InitializePartyMovementPhase        300
  0x004f00c0 PartyMovementReachedPhaseLimit      400
  0x004f0af0 StartPartyMovementAction            250  (covers inlined AlignCombatantsToPartyMovementPhase;
                                                       g_level_data movement fields preset + captured)
  0x004efd30 EndPartyMovementPhase                24  (non-movement path only)
  0x004efda0 FinishPartyMovementAction            24  (non-movement path only)
  0x004efc00 BeginPartyMovementPhase              24  (non-movement path only)

Skipped:
  0x00547120 ProvokeListedMonsterGroups   - makes world groups hostile, MonsterGroupEnterCombat (combat start)
  0x005471d0 MakeTargetGroupHostile       - same: SetMonsterGroupHostility + MonsterGroupEnterCombat on world groups
  0x00547540 SetMonsterGroupHostilityByID - world group hostility: ShowNoticef, SetTargetToGroup, AI updates, allied recursion
  0x00547570 SetMonsterGroupHostility     - same as above (notices, targeting, UpdateMonsterAI of world monsters)
  0x005478a0 AlertSameFactionGroups       - walks the live group list, 3D sight checks, changes group hostility
  0x00547cb0 TurnUndead                   - casts Dispel Undead (visuals, monster removal), notices, text box
  0x00547fe0 CharacterPrayAction          - notices, spell casts, gold, 3D distances; port deliberately deviates on stale stack
  0x004efbe0 BeginPartyMovement           - MoveTimer(1) pauses the shared game timers (global timer state)
  0x004f01d0 UpdateActivePartyMovement    - HandlePartyMovement (real 3D movement), countdown clocks, panel UI
  0x004f0560 ClearPendingPartyMovement    - rebuilds 3D target highlights, UpdatePartyMovementControl (UI)
  0x004f0aa0 UpdatePartyMovementControl   - ReleasePartyMovement destroys UI controls / virtual Invalidate on panel
  0x004f0630 BeginFreeTurnPhase           - CheckMonsterGroupsEnterCombat / NotifyNearbyMonsters (world combat entry)
  0x004f0860 CancelPartyMovement          - every non-trivial path ends in UpdatePartyMovementControl (UI destruction)
  0x004f0010 GetPartyHasteSteps           - inlined in the port (not in map); tested through GetPartyMovementSpeed
  0x004f06b0 CompletePartyMovementTurns   - inlined in the port; only caller BeginFreeTurnPhase is untestable
  0x004f0c80 AlignCombatantsToPartyMovementPhase - inlined in the port; tested through StartPartyMovementAction
  0x004f0990 InterruptActivePartyMovement - inlined in the port (into CancelPartyMovement)
"""
import struct

from w8diff.api import Blob

MAX_OPS = 96          # W8D_MAX_OPS in w8diff_core.c (extra ops are silently dropped)
MAX_ARGS = 16

# --- W8Character (layout.ps1) ---
CHAR = 0x1862
C_PROF = 0x69
C_RACE = 0x71
C_COND = 0xa01
C_COND13 = 0xa35      # uiCondition[TURNCOAT]
C_COND19 = 0xa4d      # uiCondition[MISSING]
C_ENCH5 = 0xa65 + 5 * 0xc   # enchantments[HASTE]: power u32, percent u16, magnitude u16, turns u32
C_HP = 0xb11
C_INIT = 0xe81
C_EQUIP = 0xf5d       # W8ItemInstance[12]
C_PACK = 0x1029       # W8ItemInstance[8]
ITEM = 0xc
XROW = 0x106          # W8PartySlotRow, fOccupied at +0

# --- gXStatus ---
GX_COMBAT = 0x8dc
GX_HOSTILE = 0x8ed
GX_MONLIST = 0x8f5
GX_UNBORN = 0x901
GX_PMODE = 0x916
GX_PLIMIT = 0x917
GX_PDIST = 0x91b
GX_RECCACHE = 0xa0f
GX_GROUPS = 0x1a06

# --- W8CombatState ---
CS_SIZE = 0xa64
CS_ROUND_COUNT = 0x4
CS_ROUND_COUNTER = 0x8
CS_CHARS = 0x18
CS_ROW = 0xd4
ROW_PRAY = 0x98
ROW_TURN = 0x99
CS_ACT_STATUS = 0x7b0
CS_ACT_MON = 0x7b8
CS_NEXT = 0x90c
CS_CUR = 0x910
CS_PHASE = 0x914
CS_STATUS = 0x918
CS_ENGAGED = 0xa54
CS_PASSIVE = 0xa55

# --- W8MonsterInfo / records / 3D monster / monster combat state ---
MI_STRIDE = 0x430     # sizeof(W8MonsterInfo) = 0x425
MI_SPECIES = 0x8
MI_P3D = 0xc
MI_PCOMBAT = 0x10
MI_ACTIVE = 0x14
MI_INCOMBAT = 0x15
MI_DISP = 0x16
MI_HP = 0x2b
MI_COND = 0x57
MI_ACTION = 0x2e1
REC_KIND = 0xcb
REC_FLAGS = 0xd0
REC_FACTION = 0x25f
REC_STRIDE = 0x2a0    # sizeof(W8MonsterRecord) = 0x297
M3D_PRESERVED = 0x332  # sizeof(W8Monster) = 0x348
M3D_STRIDE = 0x350
MCS_ACTIVE = 0x4      # sizeof(W8MonsterCombatState) = 0x153
MCS_STRIDE = 0x160

LB_REFRESH = 0x2c0    # W8LevelRuntimeBlock refresh_combat_panel (+0), refresh_party_panel (+8)

# --- scratch buffers ---
SB_COMBAT = 0         # W8CombatState
SB_MISC = 1           # target source, detail block, phase word, loose item, lone monsters
SB_WORLD = 2          # fake monster lists + W8MonsterInfo records
SB_RECORDS = 3        # W8MonsterRecord
SB_OBJECTS = 4        # W8Monster (p3D) at 0, W8MonsterCombatState at 0x8000

W_MAIN = 0x0          # W8PList {data, capacity, iNumUsed}
W_UNBORN = 0x10
W_MAIN_DATA = 0x40    # up to 32 pointers
W_UNBORN_DATA = 0xc0  # up to 16 pointers
W_MON = 0x200

NEUTRAL_SPECIES = 0x224
MONSTER_RECORDS = 595  # MONSTERS.DBS
SPELLS = 150           # SpellTables.dbs records (0..0x95); larger ids read past the heap block
ITEMS = 819            # Items.dbs records

COND_VALUES = [0, 0, 0, 0, 1, 2, 7, 9999, 0x7fffffff, 0x80000000, 0xffffffff]

# Items.dbs ids whose record carries a spell (equip class in parentheses where it matters).
SPELL_ITEMS = [
    16, 19, 24, 27, 33, 34, 42, 43, 44, 46, 47, 60, 61, 68, 69, 74, 81, 85, 86, 87, 88, 100, 101,
    102, 107, 108, 109, 254, 255, 256, 257, 258, 259, 260, 262, 263, 264, 265, 269, 273, 276, 277,
    278, 280, 282, 285, 286, 287, 292, 304, 305, 306, 310, 317, 320, 321, 322, 323, 324, 325, 326,
    327, 328, 329, 330, 331, 332, 334, 335, 336, 337, 338, 339, 340, 341, 342, 343, 344, 345, 346,
    347, 348, 349, 350, 351, 352, 353, 354, 355, 356, 357, 358, 359, 360, 361, 362, 363, 364, 368,
    369, 370, 371, 372, 373, 374, 375, 376, 377, 378, 379, 380, 381, 382, 383, 384, 385, 386, 387,
    388, 389, 390, 391, 392, 393, 394, 395, 396, 397, 398, 399, 400, 401, 402, 403, 404, 405, 406,
    407, 408, 409, 410, 411, 412, 414, 416, 417, 418, 419, 425, 426, 428, 429, 432, 437, 438, 439,
    440, 441, 442, 443, 444, 445, 447, 448, 449, 464, 465, 466, 469, 474, 475, 476, 477, 478, 479,
    480, 481, 482, 483, 484, 488, 492, 496, 499, 501, 515, 516, 517, 518, 519, 520, 521, 522, 523,
    524, 525, 526, 527, 528, 529, 530, 531, 532, 533, 534, 535, 536, 537, 538, 539, 540, 541, 542,
    543, 544, 545, 546, 547, 548, 549, 550, 551, 552, 553, 554, 555, 556, 557, 558, 565, 584, 585,
    586, 587, 590, 591, 592, 593, 597, 598, 659, 669, 675, 682, 683, 684, 685, 686, 687, 688, 689,
    690, 691, 692, 693, 694, 695, 696, 697, 698, 699, 700, 701, 702, 709, 726, 738, 741, 742, 743,
    744, 753, 755, 770, 772, 789, 804, 812, 818]
# Items whose spell is Charm (3) or Mindread (0x29), and plain items without a spell.
CHARM_MINDREAD_ITEMS = [24, 87, 375, 586, 755, 265, 419, 526]
PLAIN_ITEMS = [0, 1, 7, 29, 49, 63, 79, 105, 125, 151, 169, 196, 235, 241, 249, 429, 485, 671, 818]


def u8(v):
    return struct.pack('<B', v & 0xff)


def u16(v):
    return struct.pack('<H', v & 0xffff)


def u32(v):
    return struct.pack('<I', v & 0xffffffff)


def f32(x):
    return struct.pack('<f', x)


def f32r(x):
    """Round a Python float to float32."""
    return struct.unpack('<f', struct.pack('<f', x))[0]


def trim(data):
    """Scratch is zeroed for every case: trailing zero bytes need not be written."""
    data = bytes(data)
    end = len(data)
    while end > 1 and data[end - 1] == 0:
        end -= 1
    return data[:end]


def pick(r, weighted):
    """weighted: list of (weight, value-or-callable)."""
    total = sum(w for w, _ in weighted)
    x = r.random() * total
    for w, v in weighted:
        x -= w
        if x < 0:
            return v() if callable(v) else v
    v = weighted[-1][1]
    return v() if callable(v) else v


def cond_value(r, p_zero=0.5):
    if r.random() < p_zero:
        return 0
    return r.choice(COND_VALUES[4:] + [r.randrange(1, 10000)])


def mon_bytes(loc=0, group=0, species=0, active=0, combat=0, disp=0, hp=0, cond=None):
    b = Blob(bytes(MI_COND + 4 * 20))
    b.u32(0, loc)
    b.u32(4, group)
    b.u32(MI_SPECIES, species)
    b.u8(MI_ACTIVE, active)
    b.u8(MI_INCOMBAT, combat)
    b.u8(MI_DISP, disp)
    b.u32(MI_HP, hp)
    for k, v in (cond or {}).items():
        b.u32(MI_COND + 4 * k, v)
    return trim(b)


class World:
    """Fake gXStatus monster lists in scratch SB_WORLD."""

    def __init__(self, ctx, c):
        self.ctx = ctx
        self.c = c
        self.W = ctx.scratch(SB_WORLD)
        self.gx = ctx.g('gXStatus')
        self.count = 0

    def monster(self, **kw):
        a = self.W + W_MON + self.count * MI_STRIDE
        self.count += 1
        self.c.set(a, mon_bytes(**kw))
        return a

    def plist(self, off, data_off, addrs):
        c, W = self.c, self.W
        for i, a in enumerate(addrs):
            c.setp(W + data_off + 4 * i, a)
        c.setp(W + off + 0, W + data_off)
        c.set(W + off + 4, struct.pack('<ii', max(10, len(addrs)), len(addrs)))

    def wire(self, main, unborn=None):
        self.plist(W_MAIN, W_MAIN_DATA, main)
        self.c.setp(self.gx + GX_MONLIST, self.W + W_MAIN)
        if unborn is not None:
            self.plist(W_UNBORN, W_UNBORN_DATA, unborn)
            self.c.setp(self.gx + GX_UNBORN, self.W + W_UNBORN)


class Records:
    """gXStatus.monster_record_cache[species] -> scratch W8MonsterRecord."""

    def __init__(self, ctx, c):
        self.ctx = ctx
        self.c = c
        self.R = ctx.scratch(SB_RECORDS)
        self.gx = ctx.g('gXStatus')
        self.by_species = {}

    def get(self, species, kind=None, faction=None, flags=None):
        if species in self.by_species:
            return self.by_species[species]
        a = self.R + len(self.by_species) * REC_STRIDE
        self.by_species[species] = a
        self.c.setp(self.gx + GX_RECCACHE + 4 * species, a)
        if kind is not None or flags is not None:
            blk = Blob(bytes(REC_FLAGS - REC_KIND + 1))
            blk.u8(0, kind or 0)
            blk.u8(REC_FLAGS - REC_KIND, flags or 0)
            self.c.set(a + REC_KIND, bytes(blk))
        if faction is not None:
            self.c.set(a + REC_FACTION, u32(faction))
        return a


def combat_state(ctx, c, fields=()):
    """Wire g_combat_state -> scratch W8CombatState; fields: (offset, bytes)."""
    S = ctx.scratch(SB_COMBAT)
    c.setp(ctx.g('g_combat_state'), S)
    for off, data in fields:
        c.set(S + off, data)
    return S


def xrow(ctx, slot):
    return (ctx.g('g_status') + 8).deref() + slot * XROW


def refresh_flags(ctx, c):
    """Zero the two RequestRefreshPartyState flags so a write shows in the cap."""
    lb = ctx.g('g_level_block').deref() + LB_REFRESH
    c.set(lb, b'\0')        # refresh_combat_panel
    c.set(lb + 8, b'\0')    # refresh_party_panel (the TIMER between them is left alone)
    return lb


def species_pick(r, exclude=()):
    while True:
        s = pick(r, [(10, lambda: r.randrange(0, MONSTER_RECORDS)),
                     (1, lambda: r.choice([0, 1, NEUTRAL_SPECIES - 1, NEUTRAL_SPECIES + 1,
                                           MONSTER_RECORDS - 1, 999]))])
        if s != NEUTRAL_SPECIES and s not in exclude:
            return s


# ---------------------------------------------------------------- hostility

def gen_monster_hostility(ctx):
    fn = ctx.fn(0x00546f80)  # W8Disposition MonsterHostility(W8MonsterInfo*, W8MonsterInfo*)
    M = ctx.scratch(SB_MISC)
    for i in range(ctx.n(300)):
        r = ctx.rng('monster_hostility', i)
        c = ctx.case('monster_hostility.%d' % i, fn, conv='c', ret='u8')
        recs = Records(ctx, c)
        bad = [3, 4, 0x7f, 0x80, 0xfe, 0xff]

        def disp():
            return r.choice([1, 2]) if r.random() < 0.9 else r.choice(bad)

        mode = pick(r, [(12, 'neutral_species'), (15, 'same_disp'), (13, 'one_neutral'),
                        (60, 'faction')])
        s1 = species_pick(r)
        s2 = s1 if r.random() < 0.1 else species_pick(r, exclude=(s1,))
        d1 = disp()
        d2 = disp()
        while d2 == d1:
            d2 = disp()
        if mode == 'neutral_species':
            if r.random() < 0.5:
                s1 = NEUTRAL_SPECIES
            if r.random() < 0.5 or s1 != NEUTRAL_SPECIES:
                s2 = NEUTRAL_SPECIES
            if r.random() < 0.3:
                d2 = d1
        elif mode == 'same_disp':
            d1 = r.choice([0, 1, 2, 0xff])
            d2 = d1
        elif mode == 'one_neutral':
            if r.random() < 0.5:
                d1 = 0
            else:
                d2 = 0
        fmode = pick(r, [(12, 'first0'), (12, 'second0'), (50, 'equal'), (26, 'differ')])
        f1 = pick(r, [(9, lambda: r.randrange(1, 21)),
                      (1, lambda: r.choice([21, 255, 0x7fffffff, 0x80000000, 0xffffffff]))])
        f2 = f1
        if fmode == 'first0':
            f1 = 0
            f2 = r.randrange(0, 21)
        elif fmode == 'second0':
            f2 = 0
        elif fmode == 'differ':
            while f2 == f1:
                f2 = r.randrange(1, 21)
        if s2 == s1:
            f2 = f1
        t1 = cond_value(r)
        t2 = cond_value(r)
        a1 = M + 0x1000
        a2 = M + 0x1800
        c.set(a1, mon_bytes(loc=0x1001, species=s1, active=1, disp=d1, hp=40, cond={13: t1}))
        c.set(a2, mon_bytes(loc=0x1002, species=s2, active=1, disp=d2, hp=40, cond={13: t2}))
        recs.get(s1, faction=f1)
        if s2 != s1:
            recs.get(s2, faction=f2)
        c.arg(a1)
        c.arg(a2)
        c.note(mode=mode, species=(s1, s2), disp=(d1, d2), faction=(f1, f2), turncoat=(t1, t2))


def gen_monster_vs_char(ctx):
    fn = ctx.fn(0x00546f10)  # W8Disposition MonsterVsCharDisposition(int slot, W8MonsterInfo*)
    M = ctx.scratch(SB_MISC)
    for i in range(ctx.n(200)):
        r = ctx.rng('monster_vs_char', i)
        c = ctx.case('monster_vs_char.%d' % i, fn, conv='c', ret='u8')
        slot = r.randrange(8)
        cond = cond_value(r, 0.35)
        disp = r.choice([0, 1, 2]) if r.random() < 0.85 else r.choice([3, 4, 0x7f, 0x80, 0xff])
        c.set(ctx.char(slot) + C_COND13, u32(cond))
        c.set(M + 0x1000, mon_bytes(loc=0x2001, species=r.randrange(MONSTER_RECORDS), active=1,
                                    disp=disp, hp=10))
        c.arg(slot)
        c.arg(M + 0x1000)
        c.note(slot=slot, turncoat=cond, disp=disp)


def gen_char_vs_char(ctx):
    fn = ctx.fn(0x00547010)  # W8Disposition CharacterVsCharacterDisposition(int, int)
    for i in range(ctx.n(200)):
        r = ctx.rng('char_vs_char', i)
        c = ctx.case('char_vs_char.%d' % i, fn, conv='c', ret='u8')
        a = r.randrange(8)
        b = a if r.random() < 0.15 else r.randrange(8)
        ca = cond_value(r)
        cb = ca if a == b else cond_value(r)
        c.set(ctx.char(a) + C_COND13, u32(ca))
        if b != a:
            c.set(ctx.char(b) + C_COND13, u32(cb))
        c.arg(a)
        c.arg(b)
        c.note(slots=(a, b), turncoat=(ca, cb))


def gen_opposite_disposition(ctx):
    fn = ctx.fn(0x00547080)  # W8Disposition GetOppositeDisposition(W8TargetSource*)
    M = ctx.scratch(SB_MISC)
    for i in range(ctx.n(260)):
        r = ctx.rng('opposite_disposition', i)
        c = ctx.case('opposite_disposition.%d' % i, fn, conv='c', ret='u8')
        kind = pick(r, [(35, 1), (45, 2), (7, 0), (8, 3), (5, lambda: r.choice([4, 5, 0xffffffff]))])
        src = Blob(bytes(0x34))
        src.u32(0, kind)
        src.u32(4, 0xffffffff)
        src.u32(8, 0xffffffff)
        note = {'type': kind}
        if kind == 1:
            slot = r.randrange(8)
            cond = cond_value(r, 0.45)
            src.u32(4, slot)
            c.set(ctx.char(slot) + C_COND13, u32(cond))
            note.update(slot=slot, turncoat=cond)
        elif kind == 2:
            w = World(ctx, c)
            n = r.randrange(0, 7)
            m = r.randrange(0, 4)
            base = r.choice([1, 100, 5000, 0x7a000000])
            ids = []
            for k in range(n + m):
                ids.append(base + k * r.choice([1, 1, 3, 17]))
            if n + m >= 2 and r.random() < 0.2:      # duplicate id: first match wins
                ids[r.randrange(1, n + m)] = ids[0]
            main, unborn = [], []
            states = []
            for k in range(n + m):
                disp = r.choice([0, 1, 2, 2]) if r.random() < 0.9 else r.choice([3, 0x80, 0xff])
                t = cond_value(r, 0.6)
                states.append((ids[k], disp, t))
                a = w.monster(loc=ids[k], species=r.randrange(MONSTER_RECORDS), active=1,
                              combat=r.choice([0, 1]), disp=disp, hp=r.randrange(1, 300),
                              cond={13: t})
                (main if k < n else unborn).append(a)
            w.wire(main, unborn)
            how = pick(r, [(50, 'main'), (20, 'unborn'), (25, 'absent'), (5, 'bad')])
            if how == 'main' and n:
                target = ids[r.randrange(n)]
            elif how == 'unborn' and m:
                target = ids[n + r.randrange(m)]
            elif how == 'bad':
                target = 0xffffffff
            else:
                target = r.choice([0, 2, 0x7a0000ff, 99999, 0x80000000])
                while target in ids:
                    target += 1
            src.u32(8, target)
            note.update(monsters=states, unborn=m, target=target, how=how)
        elif kind == 3:
            src.u32(4, r.choice([0xffffffff, r.randrange(8)]))
            src.u32(8, r.choice([0xffffffff, 1234]))
            src.u8(0x1b, r.choice([0, 1]))
            src.u8(0x1c, r.choice([0, 1]))
        else:
            src.u32(4, r.randrange(8))
            src.u32(8, r.randrange(1, 5000))
        c.set(M, bytes(src))
        c.arg(M)
        c.note(**note)


def gen_char_action_targets_enemies(ctx):
    fn = ctx.fn(0x00547310)  # bool CharacterActionTargetsEnemies(W8Character*, W8ActionKind, int, W8ActionDetailBlock*)
    M = ctx.scratch(SB_MISC)
    gstat = ctx.g('g_status')
    for i in range(ctx.n(400)):
        r = ctx.rng('char_action_enemies', i)
        c = ctx.case('char_action_enemies.%d' % i, fn, conv='c', ret='b')
        slot = r.randrange(8)
        blob, name = ctx.pick_char(r)
        ch = ctx.char(slot)
        c.setb(ch, bytes(blob))
        c.set(gstat + 0xc, b'\x01')  # g_status.game_started (GetItemDefaultEquipSlot)
        kind = pick(r, [(35, 7), (40, 8),
                        (25, lambda: r.choice([-1, 0, 1, 2, 3, 4, 5, 6, 9, 10, 11, 12,
                                               0x80000000, 0x7fffffff, 100, 0x107]))])
        note = {'char': name, 'slot': slot, 'kind': kind}
        detail = r.randrange(-5, 300)
        block = Blob(bytes(8))
        block.u32(0, r.randrange(0, 4))
        if kind == 7:
            detail = pick(r, [(80, lambda: r.randrange(SPELLS)), (5, 3), (5, 0x29),
                              (5, 0), (5, SPELLS - 1)])
            note['spell'] = detail
        c.set(M, bytes(block))
        if kind == 8:
            mode = pick(r, [(35, 'existing'), (45, 'inject'), (20, 'loose')])
            if mode == 'existing':
                if r.random() < 0.6:
                    k = r.randrange(12)
                    item = ch + C_EQUIP + k * ITEM
                    note['item'] = ('equip', k, blob.get_i32(C_EQUIP + k * ITEM))
                else:
                    k = r.randrange(8)
                    item = ch + C_PACK + k * ITEM
                    note['item'] = ('pack', k, blob.get_i32(C_PACK + k * ITEM))
            else:
                item_id = pick(r, [(75, lambda: r.choice(SPELL_ITEMS)),
                                   (8, lambda: r.choice(CHARM_MINDREAD_ITEMS)),
                                   (12, lambda: r.choice(PLAIN_ITEMS)), (5, -1)])
                charges = 0 if r.random() < 0.2 else r.choice([1, 2, 5, 20, 255])
                inst = struct.pack('<iBBB', item_id, r.choice([1, 1, 3]), charges, r.choice([0, 1]))
                if mode == 'inject':
                    if r.random() < 0.6:
                        k = r.randrange(12)
                        item = ch + C_EQUIP + k * ITEM
                    else:
                        k = r.randrange(8)
                        item = ch + C_PACK + k * ITEM
                    c.set(item, inst)
                    note['item'] = (mode, k, item_id, charges)
                else:
                    item = M + 0x40
                    c.set(item, inst)
                    note['item'] = (mode, item_id, charges)
            c.setp(M + 4, item)
        c.arg(ch)
        c.arg(kind)
        c.arg(detail)
        c.arg(M)
        c.note(**note)


def gen_monster_action_targets_enemies(ctx):
    fn = ctx.fn(0x00547440)  # bool MonsterActionTargetsEnemies(W8MonsterActionKind, int, unsigned*)
    M = ctx.scratch(SB_MISC)
    for i in range(ctx.n(200)):
        r = ctx.rng('monster_action_enemies', i)
        c = ctx.case('monster_action_enemies.%d' % i, fn, conv='c', ret='b')
        kind = pick(r, [(50, 2), (50, lambda: r.choice([-1, 0, 1, 3, 4, 5, 6, 7, 8, 9, 10,
                                                        0x80000000, 0x7fffffff, 0x102]))])
        if kind == 2:
            detail = pick(r, [(85, lambda: r.randrange(SPELLS)), (5, 3), (5, 0x29), (5, 0)])
        else:
            detail = r.randrange(-3, 400)
        c.set(M, u32(r.randrange(0, 8)))
        c.arg(kind)
        c.arg(detail)
        c.arg(M if r.random() < 0.7 else 0)
        c.note(kind=kind, detail=detail)


def gen_monster_can_aim_spell(ctx):
    fn = ctx.fn(0x005474b0)  # bool MonsterCanAimSpell(int)
    ids = list(range(SPELLS))
    r = ctx.rng('monster_can_aim', 'extra')
    ids += [3, 0x29, 0, 1, SPELLS - 1] + [r.randrange(SPELLS) for _ in range(15)]
    for i, spell in enumerate(ids):
        c = ctx.case('monster_can_aim.%d' % i, fn, conv='c', ret='b')
        c.arg(spell)
        c.note(spell=spell)


def gen_combat_allows_live_groups(ctx):
    fn = ctx.fn(0x00547510)  # bool CombatAllowsLiveGroups(void)
    gx = ctx.g('gXStatus')
    i = 0
    rounds = [0, 1, 2, 3, 10, 0x7fffffff, 0x80000000, 0xffffffff]
    for mode in (0, 1):
        for engaged in (0, 1):
            for rc in rounds:
                for extra in range(2):
                    c = ctx.case('combat_live_groups.%d' % i, fn, conv='c', ret='b')
                    i += 1
                    c.set(gx + GX_COMBAT, u8(mode))
                    combat_state(ctx, c, [(CS_ROUND_COUNT, u32(rc)), (CS_ENGAGED, u8(engaged)),
                                          (CS_ROUND_COUNTER, u32(extra * 37 + 1)),
                                          (CS_PASSIVE, u8(extra))])
                    c.note(combat=mode, engaged=engaged, round_count=rc)
    # combat mode off: g_combat_state is not read (null pointer)
    while i < 72:
        c = ctx.case('combat_live_groups.%d' % i, fn, conv='c', ret='b')
        i += 1
        c.set(gx + GX_COMBAT, u8(0))
        c.set(ctx.g('g_combat_state'), u32(0))
        c.note(combat=0, combat_state='null')


def gen_set_monster_hostility(ctx):
    fn = ctx.fn(0x005477d0)  # void SetMonsterHostility(W8MonsterInfo*, W8Disposition)
    gx = ctx.g('gXStatus')
    O = ctx.scratch(SB_OBJECTS)
    for i in range(ctx.n(260)):
        r = ctx.rng('set_monster_hostility', i)
        c = ctx.case('set_monster_hostility.%d' % i, fn, conv='c', ret='v')
        w = World(ctx, c)
        n = r.randrange(1, 7)
        t = r.randrange(n)
        hostility = pick(r, [(15, 0), (35, 1), (35, 2), (15, lambda: r.choice([3, 4, 0x80, 0xff]))])
        arg = hostility
        if r.random() < 0.15:  # only the low byte is the argument
            arg = hostility | (r.randrange(1, 0x1000000) << 8)
        preserved = 1 if r.random() < 0.15 else 0
        if preserved:
            previous = r.choice([0, 1, 2, 3])
        elif r.random() < 0.2:
            previous = hostility  # unchanged: early out
        else:
            previous = 0  # non-neutral previous would retarget through the 3D layer
        in_combat = 1 if r.random() < 0.65 else 0
        hp = pick(r, [(20, 0), (60, lambda: r.randrange(1, 400)), (20, lambda: r.choice([1, 0x80000000, 0xffffffff]))])
        addrs = []
        states = []
        for k in range(n):
            if k == t:
                a = w.monster(loc=0x7b000000 + k, group=7, species=r.randrange(MONSTER_RECORDS),
                              active=1, combat=in_combat, disp=previous, hp=hp,
                              cond={13: cond_value(r, 0.8)})
            else:
                st = (r.choice([0, 1, 1]), r.choice([0, 1, 1]), r.choice([0, 1, 1, 2]), cond_value(r, 0.7))
                states.append(st)
                a = w.monster(loc=0x7b000000 + k, group=7, species=r.randrange(MONSTER_RECORDS),
                              active=st[0], combat=st[1], disp=st[2], hp=r.randrange(0, 100),
                              cond={13: st[3]})
            addrs.append(a)
        w.wire(addrs)
        target = addrs[t]
        p3d = O + 0
        pcombat = O + 0x8000
        c.setp(target + MI_P3D, p3d)
        c.setp(target + MI_PCOMBAT, pcombat)
        c.set(p3d + M3D_PRESERVED, u8(preserved))
        active = 1
        if not in_combat or hp == 0:
            active = r.choice([0, 1])  # AI dispatch not reached
        c.set(pcombat, u32(r.randrange(1, 101)) + u8(active))
        c.set(target + MI_ACTION, u32(r.choice([0, 1, 2, 3, 0xffffffff])))
        mode = r.choice([0, 1])
        c.set(gx + GX_COMBAT, u8(mode))
        S = combat_state(ctx, c, [(CS_ACT_STATUS, u32(r.choice([0, 1, 2]))),
                                  (CS_ENGAGED, u8(int(r.random() < 0.2)))])
        if n > 1 and r.random() < 0.5:  # another monster is acting, never the target
            other = r.choice([k for k in range(n) if k != t])
            c.setp(S + CS_ACT_MON, addrs[other])
        c.set(gx + GX_HOSTILE, u32(0x11))
        c.set(gx + GX_GROUPS, u32(0x22))
        lb = refresh_flags(ctx, c)
        c.arg(target)
        c.arg(arg)
        c.cap(target, MI_ACTION + 4, 'monster', ignore=[MI_P3D, MI_PCOMBAT])
        c.cap(pcombat, 8, 'pcombat')
        c.cap(S, CS_SIZE, 'combat', ignore=[CS_ACT_MON])
        c.cap(gx + GX_HOSTILE, 4, 'hostile_count')
        c.cap(gx + GX_GROUPS, 4, 'hostile_groups')
        c.cap(lb, 9, 'refresh')
        c.note(hostility=arg, previous=previous, preserved=preserved, in_combat=in_combat, hp=hp,
               combat_mode=mode, others=states)


def gen_recount_combat_monsters(ctx):
    fn = ctx.fn(0x00546e70)  # void RecountCombatMonsters(void)
    gx = ctx.g('gXStatus')
    for i in range(ctx.n(200)):
        r = ctx.rng('recount', i)
        c = ctx.case('recount.%d' % i, fn, conv='c', ret='v')
        w = World(ctx, c)
        n = pick(r, [(5, 0), (60, lambda: r.randrange(1, 7)), (35, lambda: r.randrange(7, 13))])
        addrs = []
        states = []
        for k in range(n):
            st = (1 if r.random() < 0.8 else 0, 1 if r.random() < 0.7 else 0,
                  r.choice([0, 1, 1, 2]) if r.random() < 0.95 else r.choice([3, 0xff]),
                  cond_value(r, 0.7))
            states.append(st)
            addrs.append(w.monster(loc=500 + k, species=r.randrange(MONSTER_RECORDS),
                                   active=st[0], combat=st[1], disp=st[2],
                                   hp=r.randrange(0, 200), cond={13: st[3]}))
        w.wire(addrs)
        mode = r.choice([0, 1])
        c.set(gx + GX_COMBAT, u8(mode))
        S = combat_state(ctx, c, [(CS_ENGAGED, u8(int(r.random() < 0.2)))])
        c.set(gx + GX_HOSTILE, u32(r.choice([0, 1, 0x33, 0xffffffff])))
        c.set(gx + GX_GROUPS, u32(r.choice([0, 2, 0x44, 0xffffffff])))
        lb = refresh_flags(ctx, c)
        c.cap(S, CS_SIZE, 'combat')
        c.cap(gx + GX_HOSTILE, 4, 'hostile_count')
        c.cap(gx + GX_GROUPS, 4, 'hostile_groups')
        c.cap(lb, 9, 'refresh')
        c.note(combat_mode=mode, monsters=states)


def gen_can_party_slot(ctx, name, addr, trait_profs, flag_off, need_kind):
    fn = ctx.fn(addr)
    for i in range(ctx.n(250)):
        r = ctx.rng(name, i)
        c = ctx.case('%s.%d' % (name, i), fn, conv='c', ret='b')
        slot = r.randrange(8)
        blob, cname = ctx.pick_char(r)
        ch = ctx.char(slot)
        c.setb(ch, bytes(blob))
        note = {'char': cname, 'slot': slot}
        if r.random() < 0.45:
            prof = r.choice(trait_profs + trait_profs + [-1, r.randrange(15)])
            c.set(ch + C_PROF, u32(prof))
            note['prof'] = prof
        if r.random() < 0.1:
            race = r.choice([-1, r.randrange(16)])
            c.set(ch + C_RACE, u32(race))
            note['race'] = race
        if r.random() < 0.1:
            c.set(ctx.g('g_combat_state'), u32(0))
            note['combat_state'] = 'null'
        else:
            flags = []
            if r.random() < 0.3:
                flags.append((CS_CHARS + slot * CS_ROW + flag_off, u8(1)))
                note['used'] = 1
            if r.random() < 0.3:  # neighbour slot used: indexing check
                other = (slot + r.randrange(1, 8)) % 8
                flags.append((CS_CHARS + other * CS_ROW + flag_off, u8(1)))
            if r.random() < 0.2:  # the other once-per-combat flag of the same slot
                flags.append((CS_CHARS + slot * CS_ROW + (ROW_PRAY + ROW_TURN - flag_off), u8(1)))
            combat_state(ctx, c, flags)
        w = World(ctx, c)
        recs = Records(ctx, c)
        kinds = {}
        n = pick(r, [(10, 0), (90, lambda: r.randrange(1, 8))])
        addrs = []
        states = []
        for k in range(n):
            species = r.randrange(MONSTER_RECORDS)
            if kinds and r.random() < 0.15:  # two members of one species share the record
                species = r.choice(sorted(kinds))
            st = (1 if r.random() < 0.85 else 0, 1 if r.random() < 0.75 else 0,
                  1 if r.random() < 0.65 else r.choice([0, 2, 3]),
                  pick(r, [(20, 0), (60, lambda: r.randrange(1, 300)),
                           (20, lambda: r.choice([1, 0x80000000, 0xffffffff]))]))
            kind = None
            if need_kind:
                if species not in kinds:
                    kinds[species] = 0x14 if r.random() < 0.45 else r.choice(
                        [0, 1, 4, 0x13, 0x15, 0x94, 0xff])
                    recs.get(species, kind=kinds[species])
                kind = kinds[species]
            states.append(st + (kind,))
            addrs.append(w.monster(loc=900 + k, species=species, active=st[0], combat=st[1],
                                   disp=st[2], hp=st[3]))
        w.wire(addrs)
        c.arg(slot)
        note['monsters'] = states
        c.note(**note)


# ---------------------------------------------------------------- party movement

def gen_round_phase_to_step(ctx):
    fn = ctx.fn(0x004f0480)  # void RoundPhaseToStep(unsigned* phase, unsigned base)
    M = ctx.scratch(SB_MISC)
    edges_phase = [0, 1, 4, 5, 6, 9, 10, 11, 14, 15, 16, 85, 94, 95, 96, 99, 100, 101, 104, 105,
                   106, 110, 0xfffffffa, 0xfffffffb, 0xfffffffc, 0xffffffff, 0x7ffffffb, 0x80000000]
    edges_base = [0, 1, 5, 9, 10, 11, 19, 20, 21, 89, 90, 91, 95, 99, 100, 101, 105, 110,
                  0xfffffff5, 0xfffffff6, 0xfffffffb, 0xffffffff, 0x80000000]
    for i in range(ctx.n(400)):
        r = ctx.rng('round_phase', i)
        c = ctx.case('round_phase.%d' % i, fn, conv='c', ret='v')
        action = pick(r, [(25, 0), (30, 1), (30, 2), (15, lambda: r.choice([3, 0xffffffff, 0x100]))])
        phase = pick(r, [(60, lambda: r.randrange(0, 111)), (25, lambda: r.choice(edges_phase)),
                         (15, lambda: r.getrandbits(32))])
        base = pick(r, [(60, lambda: r.randrange(0, 101)), (25, lambda: r.choice(edges_base)),
                        (15, lambda: r.getrandbits(32))])
        combat_state(ctx, c, [(CS_CUR, u32(action))])
        c.set(M + 0x10, u32(phase))
        c.arg(M + 0x10)
        c.arg(base)
        c.cap(M + 0x10, 4, 'phase')
        c.note(action=action, phase=phase, base=base)


def gen_get_phase_step(ctx):
    fn = ctx.fn(0x004f0500)  # int GetPhaseStep(void)
    values = [0, 1, 2, 3, 4, 0x100, 0x7fffffff, 0x80000000, 0xffffffff, 0xfffffffe]
    for i in range(ctx.n(20)):
        c = ctx.case('phase_step.%d' % i, fn, conv='c', ret='i')
        action = values[i % len(values)]
        combat_state(ctx, c, [(CS_CUR, u32(action)), (CS_NEXT, u32(i % 3)), (CS_STATUS, u32(i % 4))])
        c.note(action=action)


def gen_set_pending_move_kind(ctx):
    fn = ctx.fn(0x004f0520)  # void SetPendingMoveKind(W8ActionKind)
    gx = ctx.g('gXStatus')
    kinds = [-1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 0x8000000a, 0x10a, 0x7fffffff,
             0xfffffff6, 0x0a0a, 100]
    i = 0
    for mode in (1, 0):
        for kind in kinds:
            c = ctx.case('pending_move_kind.%d' % i, fn, conv='c', ret='v')
            i += 1
            c.set(gx + GX_COMBAT, u8(mode))
            S = combat_state(ctx, c, [(CS_NEXT, u32(0x77777777)), (CS_CUR, u32(i % 3))])
            c.arg(kind)
            c.cap(S, CS_SIZE, 'combat')
            c.note(combat_mode=mode, kind=kind)


def gen_can_party_move(ctx):
    fn = ctx.fn(0x004f0800)  # bool CanPartyMove(void)
    gx = ctx.g('gXStatus')
    curs = [0, 1, 2, 3, 0xffffffff]
    stats = [0, 1, 2, 3, 4, 0xffffffff]
    nexts = [0, 1, 2, 3, 0xffffffff]
    i = 0
    for cur in curs:
        for st in stats:
            for nx in nexts:
                c = ctx.case('can_party_move.%d' % i, fn, conv='c', ret='b')
                i += 1
                c.set(gx + GX_COMBAT, u8(1))
                combat_state(ctx, c, [(CS_NEXT, u32(nx)), (CS_CUR, u32(cur)), (CS_STATUS, u32(st))])
                c.note(cur=cur, status=st, next=nx)
    r = ctx.rng('can_party_move', 'off')
    while i < 200:
        c = ctx.case('can_party_move.%d' % i, fn, conv='c', ret='b')
        i += 1
        cur, st, nx = r.choice(curs), r.choice(stats), r.choice(nexts)
        c.set(gx + GX_COMBAT, u8(0))  # assert line 613, then the same logic
        combat_state(ctx, c, [(CS_NEXT, u32(nx)), (CS_CUR, u32(cur)), (CS_STATUS, u32(st))])
        c.note(combat_mode=0, cur=cur, status=st, next=nx)


def gen_party_movement_speed(ctx):
    fn = ctx.fn(0x004effa0)  # float GetPartyMovementSpeed(void)
    for i in range(ctx.n(300)):
        r = ctx.rng('movement_speed', i)
        c = ctx.case('movement_speed.%d' % i, fn, conv='c', ret='f')
        party = ctx.set_party(c, r)
        action = pick(r, [(40, 0), (20, 1), (30, 2), (10, lambda: r.choice([3, 0xffffffff]))])
        mode = pick(r, [(45, 'hasted'), (35, 'mixed'), (15, 'none'), (5, 'empty')])
        slots = []
        for slot, blob, name in party:
            occ = 0 if mode == 'empty' else (1 if r.random() < 0.8 else 0)
            missing = 0
            if mode == 'empty':
                missing = 0
            elif r.random() < 0.12:
                missing = r.choice([1, 9999, 0x80000000, 0xffffffff])
            hasted = mode == 'hasted' or (mode == 'mixed' and r.random() < 0.7)
            turns = r.choice([1, 2, 3, 5, 10, 50, 9999, 0x80000000, 0xffffffff]) if hasted else 0
            power = r.choice([0, 1, 2, 3, 4, 5, 6, 7, 10, 15, 20, 25, 26, 30, 100, 255, 256, 0x101,
                              r.randrange(0, 40)])
            percent = r.choice([0, 0, 0, 5, 10, 25, 33, 50, 100, 150, 200, 1000, 0xffff,
                                r.randrange(0, 300)])
            magnitude = r.randrange(0, 0x10000)
            c.set(xrow(ctx, slot), u8(occ))
            c.set(ctx.char(slot) + C_ENCH5, struct.pack('<IHHI', power, percent, magnitude, turns))
            c.set(ctx.char(slot) + C_COND19, u32(missing))
            slots.append((occ, missing, power, percent, turns))
        combat_state(ctx, c, [(CS_CUR, u32(action))])
        c.note(action=action, mode=mode, slots=slots)


def gen_initialize_party_movement_phase(ctx):
    fn = ctx.fn(0x004efe70)  # void InitializePartyMovementPhase(void)
    inits = [-1000, -100, -20, -11, -10, -9, -1, 0, 1, 5, 10, 20, 30, 40, 50, 60, 70, 80, 85, 86,
             87, 88, 89, 90, 91, 100, 1000, 0x7fffffff, 0x7ffffffd, -0x80000000]
    for i in range(ctx.n(300)):
        r = ctx.rng('init_movement_phase', i)
        c = ctx.case('init_movement_phase.%d' % i, fn, conv='c', ret='v')
        party = ctx.set_party(c, r)
        action = pick(r, [(25, 0), (35, 1), (35, 2), (5, 3)])
        slots = []
        for slot, blob, name in party:
            occ = 1 if r.random() < 0.75 else 0
            c.set(xrow(ctx, slot), u8(occ))
            hp = None
            if r.random() < 0.2:
                hp = r.choice([0, 0, 0, 1, 0x80000000])
                c.set(ctx.char(slot) + C_HP, u32(hp))
            ini = blob.get_i32(C_INIT)
            if r.random() < 0.4:
                ini = r.choice(inits)
                c.set(ctx.char(slot) + C_INIT, u32(ini))
            slots.append((occ, hp, ini))
        S = combat_state(ctx, c, [(CS_CUR, u32(action)), (CS_PHASE, u32(0xdeadbeef)),
                                  (CS_ROUND_COUNTER, u32(r.randrange(1, 101)))])
        c.cap(S, CS_SIZE, 'combat')
        c.note(action=action, slots=slots)


def gen_phase_limit(ctx):
    fn = ctx.fn(0x004f00c0)  # bool PartyMovementReachedPhaseLimit(void)
    gx = ctx.g('gXStatus')
    nan = float('nan')
    inf = float('inf')
    for i in range(ctx.n(400)):
        r = ctx.rng('phase_limit', i)
        c = ctx.case('phase_limit.%d' % i, fn, conv='c', ret='b')
        status = 1 if r.random() < 0.9 else r.choice([0, 2, 3, 4])
        pmode = 1 if r.random() < 0.92 else 0
        action = r.choice([0, 1, 2, 2, 3])
        phase = pick(r, [(80, lambda: r.randrange(1, 101)),
                         (20, lambda: r.choice([0, 1, 99, 100, 101, 102, 150, 0xffffffff, 0x80000000]))])
        rc = pick(r, [(60, lambda: r.randrange(1, 101)),
                      (25, lambda: (phase + r.choice([-12, -11, -10, -2, -1, 0, 1, 5])) & 0xffffffff),
                      (15, lambda: r.choice([0, 100, 101, 0xffffffff, r.getrandbits(32)]))])
        elapsed = (rc - phase + (11 if action else 2)) & 0xffffffff
        remaining = (101 - phase) & 0xffffffff
        if remaining >= 0x80000000:
            remaining -= 0x100000000
        ratio = elapsed / remaining if remaining else inf
        limit = pick(r, [(85, lambda: r.choice([10000.0, 15000.0, 12345.678, 1.0, 0.5, 3.0,
                                                1e-30, 3.0e38, r.uniform(100.0, 30000.0)])),
                         (15, lambda: r.choice([0.0, -0.0, -1.0, -10000.0, nan, inf, -inf, 1e-45]))])
        how = pick(r, [(30, 'ratio'), (20, 'near'), (40, 'random'), (10, 'edge')])
        if how == 'ratio' and remaining and abs(ratio) < 3e38:
            limit = 1.0
            dist = f32r(ratio)
        elif how == 'near' and remaining and abs(ratio) < 1e30 and limit == limit and abs(limit) < 1e30:
            dist = limit * ratio * (1.0 + r.choice([-1e-7, -6e-8, 0.0, 6e-8, 1e-7]))
        elif how == 'edge':
            dist = r.choice([0.0, -0.0, -5.0, nan, inf, -inf, limit, limit * 2.0])
        else:
            lim = limit if (limit == limit and abs(limit) < 1e30) else 15000.0
            dist = r.uniform(0.0, 1.3 * abs(lim))
        if dist == dist and abs(dist) > 3.4e38:
            dist = inf if dist > 0 else -inf
        c.set(gx + GX_PMODE, u8(pmode) + f32(limit) + f32(dist))
        combat_state(ctx, c, [(CS_ROUND_COUNTER, u32(rc)), (CS_CUR, u32(action)),
                              (CS_PHASE, u32(phase)), (CS_STATUS, u32(status))])
        c.note(status=status, pmode=pmode, action=action, phase=phase, round_counter=rc,
               limit=limit, dist=dist, how=how)


def gen_start_party_movement(ctx):
    """StartPartyMovementAction: GetPartyMovementSpeed, ResetLevelMovement (only
    writes g_level_data fields, preset here and captured), InitializePartyMovementPhase,
    the inlined AlignCombatantsToPartyMovementPhase over party rows and fake monsters,
    the final round_counter rounding and RequestRedraw."""
    fn = ctx.fn(0x004f0af0)  # void StartPartyMovementAction(W8PartyAction)
    gx = ctx.g('gXStatus')
    ld = ctx.g('g_level_data').deref()
    lb = ctx.g('g_level_block').deref()
    O = ctx.scratch(SB_OBJECTS)
    rc_edges = [0, 1, 5, 9, 10, 11, 15, 89, 90, 91, 95, 99, 100, 101, 0xffffffff]
    phase_edges = [0, 1, 9, 10, 11, 50, 89, 90, 94, 95, 96, 99, 100, 101, 110, 0xfffffffb]
    for i in range(ctx.n(250)):
        r = ctx.rng('start_movement', i)
        c = ctx.case('start_movement.%d' % i, fn, conv='c', ret='v')
        kind = pick(r, [(45, 1), (40, 2), (15, lambda: r.choice([0, 3, 0xffffffff]))])
        current = pick(r, [(80, 0), (10, kind), (10, lambda: r.choice([1, 2, 3]))])
        rc = pick(r, [(70, lambda: r.randrange(1, 101)), (30, lambda: r.choice(rc_edges))])
        party = ctx.set_party(c, r)
        occs = [1 if r.random() < 0.75 else 0 for _ in range(8)]
        if not any(occs):
            occs[r.randrange(8)] = 1   # no occupied slot divides by zero in GetPartyHasteSteps
        hasted = r.random() < 0.4
        slots = []
        for (slot, blob, name), occ in zip(party, occs):
            c.set(xrow(ctx, slot), u8(occ))
            turns = r.choice([1, 3, 9999]) if hasted and r.random() < 0.9 else 0
            power = r.choice([1, 2, 3, 5, 7, 10, 25, 26])
            percent = r.choice([0, 0, 10, 50, 100, 200])
            c.set(ctx.char(slot) + C_ENCH5, struct.pack('<IHHI', power, percent, 0, turns))
            ini = blob.get_i32(C_INIT)
            if r.random() < 0.3:
                ini = r.choice([-20, -10, 0, 5, 40, 80, 88, 89, 90, 95])
                c.set(ctx.char(slot) + C_INIT, u32(ini))
            slots.append((occ, turns, power, percent, ini))
        fields = [(CS_ROUND_COUNTER, u32(rc)), (CS_CUR, u32(current)),
                  (CS_PHASE, u32(r.choice([0, 50, 0xdeadbeef]))),
                  (CS_STATUS, u32(r.choice([0, 1, 2, 3])))]
        rows = []
        for slot in range(8):
            ph = pick(r, [(50, lambda: r.randrange(0, 101)), (30, lambda: r.choice(phase_edges)),
                          (20, lambda: (rc + r.choice([-1, 0, 1, 4, 5, 6])) & 0xffffffff)])
            dead = 1 if r.random() < 0.2 else 0
            row = Blob(bytes(0x35))
            row.u32(0, ph)
            row.u8(0x34, dead)
            fields.append((CS_CHARS + slot * CS_ROW, trim(row)))
            rows.append((ph, dead))
        S = combat_state(ctx, c, fields)
        w = World(ctx, c)
        n = r.randrange(0, 6)
        mons = []
        addrs = []
        for k in range(n):
            in_combat = 1 if r.random() < 0.8 else 0
            mph = pick(r, [(50, lambda: r.randrange(0, 101)), (30, lambda: r.choice(phase_edges)),
                           (20, lambda: (rc + r.choice([-1, 0, 1, 5])) & 0xffffffff)])
            active = 1 if r.random() < 0.25 else 0
            a = w.monster(loc=0x7c000000 + k, species=r.randrange(MONSTER_RECORDS), active=1,
                          combat=in_combat, disp=r.choice([1, 2]), hp=r.randrange(1, 200))
            pc = O + 0x8000 + k * MCS_STRIDE
            c.setp(a + MI_PCOMBAT, pc)
            c.set(pc, u32(mph) + u8(active))
            addrs.append(a)
            mons.append((in_combat, mph, active))
        w.wire(addrs)
        flags = r.choice([0, 0x20, 0x40, 0x80, 0x100, 0x1e0, 0x3ff, 0x11])
        c.set(ld, u32(flags))
        c.set(ld + 0x24, f32(r.uniform(0, 50)) + f32(r.uniform(0, 50)) + f32(12345.0) + f32(0.25))
        c.set(ld + 0x4c, f32(0.5) + f32(-1.0) + f32(2.0))
        c.set(ld + 0x7c, f32(3.0) + f32(0.0) + f32(-7.5))
        c.set(lb + 0xf4, u32(r.choice([0, 0, 0x1, 0x100000])))
        c.set(gx + GX_PLIMIT, f32(-1.0))
        c.arg(kind)
        c.cap(S, CS_SIZE, 'combat')
        if n:
            c.cap(O + 0x8000, n * MCS_STRIDE, 'monster_combat')
        c.cap(gx + GX_PLIMIT, 4, 'move_limit')
        c.cap(ld, 0x88, 'level_data')
        c.cap(lb + 0xf4, 4, 'redraw_flags')
        c.note(kind=kind, current=current, round_counter=rc, slots=slots, rows=rows, monsters=mons,
               level_flags=flags)


def gen_movement_phase_stores(ctx):
    """The three phase-transition entry points, restricted to party actions other
    than walk/run (the walk/run path posts notices and drives the 3D level)."""
    actions = [0, 3, 4, 0xffffffff, 0x80000001, 0x7fffffff, 0x101, 0x102]
    for name, addr in (('end_movement_phase', 0x004efd30), ('finish_movement_action', 0x004efda0),
                       ('begin_movement_phase', 0x004efc00)):
        fn = ctx.fn(addr)
        r = ctx.rng(name, 'x')
        for i in range(ctx.n(24)):
            c = ctx.case('%s.%d' % (name, i), fn, conv='c', ret='v')
            action = actions[i % len(actions)]
            S = combat_state(ctx, c, [(CS_CUR, u32(action)),
                                      (CS_STATUS, u32(r.choice([0, 1, 2, 3, 0x55]))),
                                      (CS_NEXT, u32(r.choice([0, 1, 2]))),
                                      (CS_PASSIVE, u8(r.randrange(1, 6)))])
            c.cap(S, CS_SIZE, 'combat')
            c.note(action=action)


def cases(ctx):
    gen_monster_hostility(ctx)
    gen_monster_vs_char(ctx)
    gen_char_vs_char(ctx)
    gen_opposite_disposition(ctx)
    gen_char_action_targets_enemies(ctx)
    gen_monster_action_targets_enemies(ctx)
    gen_monster_can_aim_spell(ctx)
    gen_combat_allows_live_groups(ctx)
    gen_set_monster_hostility(ctx)
    gen_recount_combat_monsters(ctx)
    # bool CanPartySlotTurnUndead(int): trait 0x11 (Priest, Bishop), flag +0x99, record kind 0x14
    gen_can_party_slot(ctx, 'can_turn_undead', 0x00547bf0, [10, 12], ROW_TURN, True)
    # bool CanPartySlotPray(int): trait 0x0b (Priest), flag +0x98
    gen_can_party_slot(ctx, 'can_pray', 0x00547f40, [10], ROW_PRAY, False)
    gen_round_phase_to_step(ctx)
    gen_get_phase_step(ctx)
    gen_set_pending_move_kind(ctx)
    gen_can_party_move(ctx)
    gen_party_movement_speed(ctx)
    gen_initialize_party_movement_phase(ctx)
    gen_phase_limit(ctx)
    gen_start_party_movement(ctx)
    gen_movement_phase_stores(ctx)
    for c in ctx.cases:
        if len(c.ops) > MAX_OPS:
            raise ValueError('%s: %d ops > %d' % (c.id, len(c.ops), MAX_OPS))
        if len(c.args) > MAX_ARGS:
            raise ValueError('%s: %d args > %d' % (c.id, len(c.args), MAX_ARGS))
