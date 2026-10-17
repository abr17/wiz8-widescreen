"""GameplayCode.cpp (src/wiz8/local_code/GameplayCode.cpp): every recovered function
of the file, tested on corpus characters with explicitly set fields.

Tested (retail address, name, cases):
  0x004ee220 CalcAttacks                  300  (original sample: corpus chars with
                                               random skills/attributes; unchanged)
  0x004eee20 AnyMonsterEngaged            200  monster list = W8PList built in scratch
                                               (S0 list, S1 W8MonsterInfo records with
                                               random filler around the four fields read)
  0x004eee80 CountActiveCharacters        150  XChar fOccupied, hp_current, highest_condition
  0x004eeec0 AnyCharacterActive           150  same inputs, ~30% all-inactive parties
  0x004ef010 AdvanceCharacterToLevel      200  level 0..255, invalid professions (asserts)
  0x004ef090 CalcXPGoal                   300  level 1..65535 (unsigned *12/10 overflow),
                                               previous goal near 2^32, invalid professions
  0x004ef1f0 RefreshLevelUpReadyNotices   200  message lines redirected into a scratch
                                               vector (S7), screen id = automap (no UI
                                               region/redraw calls); band-14 level and
                                               greeting_pending early returns
  0x004ef3c0 IsCharacterReadyToAdvance    250
  0x004ef460 FindFreePartySlot            200  first/last 0..8, first >= last, first = -1
  0x004eed80 CalcCharacterLevelBand       300  band thresholds, base > level (unsigned wrap)
  0x004ef950 CalcCharacterTableValue      360  all 330 sex/race/profession triples +
                                               races 11..15 (assert line 2359, still in table)
  0x004efa30 DeriveCharacterPersonality   340  all 330 triples + professions 15/16
  0x004efad0 EnsureUniquePartyVoice       200  forced clashes, Random() re-rolls (seeded),
                                               target in party or a copy in scratch (S2)
  0x004ef420 GetAveragePartyLevel         200  incl. unsigned sum overflow and 3 cases with
                                               no occupied slot (divide by zero in both)
  0x004ee000 CalcInitiative               300  incl. invalid load category (assert 380)
  0x004ee9d0 CalcArmorClasses             400  real armor/shield ids per slot from
                                               Items.dbs (819 records); 25% in combat mode
                                               with a scratch W8CombatState (S0): either
                                               characters[slot].dead = 1 (TryCharacterAction
                                               only compares XChar.pending_action) or dead = 0
                                               with XChar.action = DEFEND (returns before
                                               CharacterCanSwitchTo)
  0x004eef10 AwardPartyExperience         250  experience saturation, level_progress row
                                               (incl. current_level -1/-2/0x2f), message line
                                               redirected into scratch (S7)
  Total 4300 cases.
  Edge values outside the enums (highest_condition 0x80000000/0xffffffff/0xfffffff0,
  bool bytes 2/0x80/0xff) are at most one slot per case in ~10% of the cases and are
  labelled note(edge='cond_negative'|'bool_byte'): retail compares highest_condition
  unsigned and bool fields as bytes, so a difference only in those cases points at a
  signed enum compare or bool normalisation in the port.
  Message lines: AddMessageBoxLine/QueueNpcMessageLine append to a vector redirected
  into scratch; only the number of lines is compared (their text is on the heap).

Skipped:
  0x004ee130 CalcPhysCombatExperience  - inlined in the port (not in Wiz8Runtime.map);
                                         covered through CalcAttacks
  0x004ef9a0 HandleLevelOverride       - notice + fall-impact sound + rolled damage on the
                                         whole party (ApplyRolledHealthChangeToParty)
  0x004ef4a0 AddCharacterToParty       - party roster change: formation, marching order,
                                         notices, UI region refresh, full derived-stat rebuild
  0x004ef610 RemoveCharacterFromParty  - roster change, heap character event queue,
                                         SaveCharacter file I/O
  0x004ef7e0 RecruitCharacterIntoParty - roster change, items moved into the party pool,
                                         gold, starting equipment
"""
import struct

CHAR = 0x1862
ATTR = 0xe5          # W8CharacterAttribute[7], stride 0x14: base +0, effective +4
SKILL = 0x19d        # W8CharacterSkill[], stride 0x26: active +0, points +2, level +6
SKILL_STEP = 0x26
DUAL = 0x12b5        # unsigned char dual_wielding

# W8Character (layout.ps1, matches the retail asm)
C_IN_PARTY = 0x04
C_PROF = 0x69
C_ORIG_PROF = 0x6d
C_RACE = 0x71
C_GENDER = 0x75
C_PORTRAIT = 0x79
C_007D = 0x7d
C_PERSONALITY = 0x81
C_VOICE = 0x85
C_LEVEL = 0x89
C_PROF_LEVELS = 0x8d
C_LEVEL_BAND = 0xdd
C_LEVEL_BAND_BASE = 0xe1
C_EXP = 0x9ed        # experience, +4 goal, +8 previous goal
C_GOAL = 0x9f1
C_PREV_GOAL = 0x9f5
C_HCOND = 0xb01
C_HP = 0xb11
C_LOAD = 0xbc9
C_EQUIP = 0xf5d      # W8ItemInstance[12], 0xc each, iItemNo +0
C_FATIGUE_BAND = 0x169e
C_BONUS = 0x1770     # W8GameplayModifierBlock bonus
B_DAMAGE = 0x00      # signed char damage_bonus (initiative term)
B_ARMOR_FLAT = 0x04
B_ARMOR_MATCHUP = 0x05
B_OUT_OF_FORMATION = 0x45
B_AC_ADJUST = 0x4b

A_STRENGTH, A_DEXTERITY, A_SPEED, A_SENSES = 0, 4, 5, 6
S_SHIELD, S_STEALTH, S_REFLEXTION, S_SNAKESPEED = 6, 11, 38, 39

# W8PartySlotRow (g_status.buffers.XChar, heap, 0x106 per slot)
XROW = 0x106
X_OCC = 0x00
X_PENDING_ACTION = 0x01
X_ACTION = 0x3d
X_ORDER = 0xf1
X_PORTRAIT_ADV = 0x103

# gXStatus
GX_ENTRY = 0x118     # W8MonsterManagerEntry
GX_LEVEL_UP_READY = 0xe8
GX_COMBAT_MODE = 0x8dc
GX_LEVEL_UP_NOTICE = 0x8e7
GX_MONSTER_LIST = 0x8f5   # W8PList*

# g_status
GS_CURRENT_LEVEL = 0x1900
GS_LEVEL_PROGRESS = 0x1a04  # W8LevelProgressRow[0x2f], 0x21 each
GS_LP_ROW = 0x21
GS_LP_EXP = 0x05
GS_GREETING = 0x2497
LEVEL_COUNT = 0x2f

# g_npc_scripting.message_lines (W8GrowableVector: vptr, count, capacity, data)
NPC_MSG_COUNT = 0x90
NPC_MSG_CAPACITY = 0x94
NPC_MSG_DATA = 0x98

# W8CombatState
CS_CHARS = 0x18
CS_ROW = 0xd4
CS_DEAD = 0x34

# W8MonsterInfo fields read by AnyMonsterEngaged
M_IN_COMBAT = 0x15
M_DISPOSITION = 0x16
M_HP = 0x2b
M_HCOND = 0x107
M_STRIDE = 0x430     # > sizeof(W8MonsterInfo) 0x425

SCREEN_AUTOMAP = 8   # neither camp (6) nor main game (7)


def _ranges(*parts):
    out = []
    for p in parts:
        if isinstance(p, tuple):
            out.extend(range(p[0], p[1] + 1))
        else:
            out.append(p)
    return out


# Items.dbs (819 records, 0x10d bytes) grouped by equip_class (+0x3e)
ITEM_COUNT = 819
IT_SHORT = _ranges((0, 45), (48, 52), (54, 68), 70, 71, 415, 430, 465, 470, 489, 501, 511, 513,
                   591, 592, 646, 653, 660, 663, 665, 666, (673, 678), 681, 748, 749, 758, 768,
                   769, 772, 774, 780, 786, (795, 798))
IT_EXTENDED = _ranges(53, (72, 98), 466, 469, 504, 506, 562, 647, 654, 753, 770, 778, 803, 815)
IT_THROWN = _ranges(99, (103, 107), 762, 763, 764)
IT_RANGED = _ranges((110, 124), 424, 473, 512, (599, 610), 626, 680, 739, 767, 771, 794, 814)
IT_SHIELD = _ranges((142, 147), (789, 793), (799, 802))
IT_TORSO = _ranges((148, 180), 463, 500, 509, 559, 650, 651, 652, 779, 806, 811, 816)
IT_LEGS = _ranges((181, 209), 664, 759, 810, 817)
IT_HEAD = _ranges((210, 234), 419, 427, 458, 510, 569, 754, 775, 809)
IT_HANDS = _ranges((235, 242), 760)
IT_FEET = _ranges((243, 253), 596, 773, 807, 808)
IT_MISC = _ranges((254, 257), 259, (261, 263), (265, 268), (270, 281), (283, 305), (307, 312), 431,
                  485, (491, 496), 499, 561, 593, 661, 668, 755, 777, (781, 785), 788, 812, 818)
IT_CLOAK = _ranges((313, 316), 318, 319, 420, 574, 667, 679, 776, 805)
IT_WEAPON = IT_SHORT + IT_EXTENDED + IT_THROWN + IT_RANGED
SLOT_ITEMS = [IT_HEAD, IT_MISC, IT_MISC, IT_CLOAK, IT_TORSO, IT_HANDS,
              IT_WEAPON, IT_SHIELD + IT_SHORT, IT_WEAPON, IT_SHIELD + IT_SHORT, IT_LEGS, IT_FEET]


def u32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def u8(v):
    return bytes([int(v) & 0xff])


def _hp(r):
    x = r.random()
    if x < 0.72:
        return r.randrange(1, 400)
    if x < 0.9:
        return 0
    return r.choice([1, 0x7fffffff, 0x80000000, 0xffffffff])


COND_EDGE = [0x80000000, 0xffffffff, 0xfffffff0]   # negative as int; retail compares unsigned
BOOL_EDGE = [2, 0x80, 0xff]                         # non-canonical true bool bytes


def _cond(r, edge_p=0.0):
    """highest_condition: mostly none, enum values around the thresholds, rarely (edge_p)
    values retail compares unsigned (negative as int)."""
    x = r.random()
    if x < edge_p:
        return r.choice(COND_EDGE)
    if x < 0.55:
        return 0
    if x < 0.85:
        return r.randrange(1, 0x14)
    return r.choice([0x0e, 0x0f, 0x10, 0x11, 0x12, 0x13, 0x14])


def _bool_byte(r, p_true, edge_p=0.0):
    if r.random() < p_true:
        return r.choice(BOOL_EDGE) if r.random() < edge_p else 1
    return 0


def _edge_slots(r, p_cond=0.08, p_bool=0.06, count=8):
    """At most one slot per case gets an out-of-enum highest_condition and at most one a
    non-canonical bool byte, so most cases stay free of these edges."""
    ec = r.randrange(count) if r.random() < p_cond else -1
    eb = r.randrange(count) if r.random() < p_bool else -1
    return ec, eb


def _prof(r, invalid_p=0.04):
    if r.random() < invalid_p:
        return r.choice([15, 16, 100, -1, -100, 0x7fffffff, -0x80000000])
    return r.randrange(15)


def cases(ctx):
    _calc_attacks(ctx)
    _any_monster_engaged(ctx)
    _count_active(ctx)
    _advance_to_level(ctx)
    _calc_xp_goal(ctx)
    _refresh_level_up_notices(ctx)
    _ready_to_advance(ctx)
    _find_free_slot(ctx)
    _level_band(ctx)
    _table_value(ctx)
    _personality(ctx)
    _unique_voice(ctx)
    _average_level(ctx)
    _initiative(ctx)
    _armor_classes(ctx)
    _award_experience(ctx)


# --------------------------------------------------------------------------------------
def _calc_attacks(ctx):
    calc = ctx.fn(0x004ee220)  # void CalcAttacks(W8Character*)
    for i in range(ctx.n(300)):
        r = ctx.rng('calc', i)
        c = ctx.case('calcattacks.%d' % i, calc, conv='c', ret='v')
        party = ctx.set_party(c, r)
        slot, blob, name = party[r.randrange(6)]
        for a in range(7):
            if r.random() < 0.5:
                blob.u32(ATTR + a * 0x14 + 4, r.choice([1, 5, 15, 30, 50, 75, 90, 100, 110, 125, r.randrange(1, 126)]))
        for s in range(0x2c):
            if r.random() < 0.3:
                blob.u32(SKILL + s * SKILL_STEP + 6, r.choice([0, 1, 10, 25, 50, 75, 99, 100, 101, 110, 125, r.randrange(0, 126)]))
        if r.random() < 0.3:
            blob.u8(DUAL, r.choice([0, 1]))
        c.set(ctx.char(slot), bytes(blob))
        c.arg(ctx.char(slot))
        c.cap(ctx.char(slot), CHAR, 'char')
        c.note(char=name, slot=slot)


# --------------------------------------------------------------------------------------
def _xrow(ctx, slot):
    return (ctx.g('g_status') + 8).deref() + slot * XROW


def _any_monster_engaged(ctx):
    """bool AnyMonsterEngaged(void): walks gXStatus.plsMonsterList."""
    fn = ctx.fn(0x004eee20)
    gx = ctx.g('gXStatus')
    lst = ctx.scratch(0)
    mons = ctx.scratch(1)
    for i in range(ctx.n(200)):
        r = ctx.rng('engaged', i)
        c = ctx.case('anymonsterengaged.%d' % i, fn, conv='c', ret='b')
        n = 0 if i < 4 else r.choice([1, 1, 2, 2, 3, 4, 5, 6, 8, 10, 12])
        c.set(lst + 4, struct.pack('<ii', n + r.randrange(0, 4), n))  # capacity, iNumUsed
        c.setp(lst, lst + 0x100)                                       # data
        q = 1.0 - 0.5 ** (1.0 / n) if n else 0.0
        edges = []
        ec, eb = _edge_slots(r, 0.08, 0.08, max(n, 1))
        for m in range(n):
            info = mons + m * M_STRIDE
            c.setp(lst + 0x100 + 4 * m, info)
            engaged = r.random() < q
            in_combat, disp = 1, 1
            hp = r.randrange(1, 500)
            cond = r.randrange(0, 0x0e)
            if m == eb:
                in_combat = r.choice(BOOL_EDGE)
                edges.append('bool_byte')
            if r.random() < 0.08:
                hp = r.choice([1, 0x7fffffff, 0x80000000, 0xffffffff])
            if r.random() < 0.15:
                cond = r.choice([0, 0x0c, 0x0d])
            if not engaged:
                which = r.choice(['combat', 'disp', 'hp', 'cond', 'cond', 'multi'])
                if which in ('combat', 'multi'):
                    in_combat = 0
                if which in ('disp', 'multi'):
                    disp = r.choice([0, 2, 3, 0xff])
                if which == 'hp':
                    hp = 0
                if which in ('cond', 'multi'):
                    cond = r.choice([0x0e, 0x0f, 0x10, 0x11, 0x12, 0x13, 0x14, 0x100])
            if m == ec:
                cond = r.choice(COND_EDGE)
                edges.append('cond_negative')
            # random filler: retail reads only the four fields below
            blob = bytearray(r.getrandbits(8) for _ in range(M_HCOND + 4 - M_IN_COMBAT))
            blob[0] = in_combat
            blob[M_DISPOSITION - M_IN_COMBAT] = disp
            struct.pack_into('<I', blob, M_HP - M_IN_COMBAT, hp)
            struct.pack_into('<I', blob, M_HCOND - M_IN_COMBAT, cond)
            c.set(info + M_IN_COMBAT, bytes(blob))
        c.setp(gx + GX_MONSTER_LIST, lst)
        c.note(monsters=n)
        if edges:
            c.note(edge=','.join(sorted(set(edges))))


# --------------------------------------------------------------------------------------
def _participation_setup(ctx, c, r, all_inactive):
    """XChar fOccupied, hp_current, highest_condition of all 8 slots."""
    ctx.set_party(c, r)
    edges = []
    ec, eb = _edge_slots(r)
    for s in range(8):
        occ = _bool_byte(r, 0.75, 1.0 if s == eb else 0.0)
        hp = _hp(r)
        cond = _cond(r, 1.0 if s == ec else 0.0)
        if all_inactive:
            which = r.choice(['occ', 'hp', 'cond'])
            if which == 'occ':
                occ = 0
            elif which == 'hp':
                hp = 0
            elif s != ec:
                cond = r.choice([0x12, 0x13, 0x14])
        if occ not in (0, 1):
            edges.append('bool_byte')
        if cond >= 0x80000000:
            edges.append('cond_negative')
        c.set(_xrow(ctx, s) + X_OCC, u8(occ))
        c.set(ctx.char(s) + C_HP, u32(hp))
        c.set(ctx.char(s) + C_HCOND, u32(cond))
    if edges:
        c.note(edge=','.join(sorted(set(edges))))


def _count_active(ctx):
    count = ctx.fn(0x004eee80)   # int CountActiveCharacters(void)
    anyc = ctx.fn(0x004eeec0)    # bool AnyCharacterActive(void)
    for i in range(ctx.n(150)):
        r = ctx.rng('countactive', i)
        c = ctx.case('countactive.%d' % i, count, conv='c', ret='i')
        _participation_setup(ctx, c, r, all_inactive=r.random() < 0.15)
    for i in range(ctx.n(150)):
        r = ctx.rng('anyactive', i)
        c = ctx.case('anyactive.%d' % i, anyc, conv='c', ret='b')
        _participation_setup(ctx, c, r, all_inactive=r.random() < 0.3)


# --------------------------------------------------------------------------------------
def _advance_to_level(ctx):
    """void AdvanceCharacterToLevel(W8Character*, unsigned int level)"""
    fn = ctx.fn(0x004ef010)
    levels = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 15, 16, 20, 23, 25, 30, 35, 40,
              45, 47, 48, 50, 60, 75, 100, 150, 255]
    for i in range(ctx.n(200)):
        r = ctx.rng('advance', i)
        c = ctx.case('advancetolevel.%d' % i, fn, conv='c', ret='v')
        party = ctx.set_party(c, r)
        slot, blob, name = party[r.randrange(8)]
        prof = _prof(r)
        ch = ctx.char(slot)
        c.set(ch + C_PROF, u32(prof))
        c.set(ch + C_LEVEL, u32(r.choice([0, 1, r.randrange(1, 40), 0xffffffff])))
        c.set(ch + C_EXP, struct.pack('<III', r.getrandbits(32), r.getrandbits(32), r.getrandbits(32)))
        level = r.choice(levels) if r.random() < 0.6 else r.randrange(1, 61)
        c.arg(ch)
        c.arg(level)
        c.cap(ch, CHAR, 'char')
        c.note(char=name, prof=prof, level=level)


def _calc_xp_goal(ctx):
    """void CalcXPGoal(W8Character*). Level 0 is not tested: IntegerPower(2, 0xfffffffe)
    loops 4e9 times in both."""
    fn = ctx.fn(0x004ef090)
    edge_levels = [1, 2, 3, 9, 10, 11, 12, 30, 47, 48, 49, 50, 64, 100, 128, 255, 256, 1000,
                   4096, 65535]
    for i in range(ctx.n(300)):
        r = ctx.rng('xpgoal', i)
        c = ctx.case('calcxpgoal.%d' % i, fn, conv='c', ret='v')
        party = ctx.set_party(c, r)
        slot, blob, name = party[r.randrange(8)]
        ch = ctx.char(slot)
        prof = _prof(r)
        level = r.choice(edge_levels) if r.random() < 0.35 else r.randrange(1, 61)
        prev = r.choice([0, 0, r.randrange(0, 20000000), r.getrandbits(32), 0xffffffff,
                         0xfffffc18, 0x80000000, 0x7fffffff, blob.get_u32(C_PREV_GOAL)])
        c.set(ch + C_PROF, u32(prof))
        c.set(ch + C_LEVEL, u32(level))
        c.set(ch + C_GOAL, struct.pack('<II', r.getrandbits(32), prev))
        c.arg(ch)
        c.cap(ch, CHAR, 'char')
        c.note(char=name, prof=prof, level=level, prev=prev)


# --------------------------------------------------------------------------------------
def _redirect_messages(ctx, c, capacity=32):
    """g_npc_scripting.message_lines -> empty vector whose array is scratch S7. The lines
    the call adds land there; the original count/capacity/data come back after the case."""
    npc = ctx.g('g_npc_scripting')
    c.set(npc + NPC_MSG_COUNT, struct.pack('<ii', 0, capacity))
    c.setp(npc + NPC_MSG_DATA, ctx.scratch(7))
    return npc + NPC_MSG_COUNT


def _refresh_level_up_notices(ctx):
    """void RefreshLevelUpReadyNotices(void)"""
    fn = ctx.fn(0x004ef1f0)
    gs = ctx.g('g_status')
    gx = ctx.g('gXStatus')
    screen = ctx.g('g_current_screen_state')
    for i in range(ctx.n(200)):
        r = ctx.rng('levelupnotices', i)
        c = ctx.case('refreshlevelupnotices.%d' % i, fn, conv='c', ret='v')
        ctx.set_party(c, r)
        greeting = 1 if r.random() < 0.08 else 0
        level = r.choice([2, 2, 3, 0, 5, 7, 4]) if r.random() < 0.7 else r.randrange(0, LEVEL_COUNT)
        c.set(gs + GS_GREETING, u8(greeting))
        c.set(gs + GS_CURRENT_LEVEL, u32(level))
        c.set(screen, u32(SCREEN_AUTOMAP))
        c.set(gx + GX_LEVEL_UP_NOTICE, u8(r.choice([0, 1])))
        count = _redirect_messages(ctx, c)
        edges = []
        ec, eb = _edge_slots(r)
        for s in range(8):
            ch = ctx.char(s)
            row = _xrow(ctx, s)
            occ = _bool_byte(r, 0.8, 1.0 if s == eb else 0.0)
            hp = 0 if r.random() < 0.15 else r.randrange(1, 300)
            cond = _cond(r, 1.0 if s == ec else 0.0)
            goal = r.randrange(1000, 20000000)
            x = r.random()
            if x < 0.45:
                exp = goal + r.choice([0, 0, 1, r.randrange(0, 1000000)])
            elif x < 0.9:
                exp = goal - r.randrange(1, goal + 1)
            else:
                exp, goal = r.choice([(0xffffffff, 0xffffffff), (0, 0), (0xffffffff, 0), (0, 0xffffffff),
                                      (0x80000000, 0x7fffffff)])
            ready = _bool_byte(r, 0.4, 0.5 if s == eb else 0.0)
            adv = r.choice([0, 0, 1, 1, 2, 0xff])
            if occ not in (0, 1) or ready not in (0, 1):
                edges.append('bool_byte')
            if cond >= 0x80000000:
                edges.append('cond_negative')
            c.set(row + X_OCC, u8(occ))
            c.set(row + X_ORDER, u32(s))
            c.set(row + X_PORTRAIT_ADV, u8(adv))
            c.set(gx + s * GX_ENTRY + GX_LEVEL_UP_READY, u8(ready))
            c.set(ch + C_HP, u32(hp))
            c.set(ch + C_HCOND, u32(cond))
            c.set(ch + C_EXP, struct.pack('<II', exp & 0xffffffff, goal & 0xffffffff))
        c.cap(gx + GX_LEVEL_UP_NOTICE, 1, 'level_up_notice')
        c.cap(gx + GX_LEVEL_UP_READY, 7 * GX_ENTRY + 1, 'level_up_ready')
        c.cap(_xrow(ctx, 0), 8 * XROW, 'xchar')
        c.cap(count, 4, 'message_count')
        c.note(level=level, greeting=greeting)
        if edges:
            c.note(edge=','.join(sorted(set(edges))))


def _ready_to_advance(ctx):
    """bool IsCharacterReadyToAdvance(int party_slot)"""
    fn = ctx.fn(0x004ef3c0)
    for i in range(ctx.n(250)):
        r = ctx.rng('readytoadvance', i)
        c = ctx.case('readytoadvance.%d' % i, fn, conv='c', ret='b')
        ctx.set_party(c, r)
        slot = r.randrange(8)
        ch = ctx.char(slot)
        occ = _bool_byte(r, 0.85, 0.04)
        hp = _hp(r)
        cond = _cond(r, edge_p=0.06)
        goal = r.randrange(1000, 20000000)
        x = r.random()
        if x < 0.45:
            exp = goal + r.choice([0, 0, 1, r.randrange(0, 1000000)])
        elif x < 0.85:
            exp = goal - r.choice([1, r.randrange(1, goal + 1)])
        else:
            exp, goal = r.choice([(0xffffffff, 0xffffffff), (0, 0), (0xffffffff, 0), (0, 0xffffffff),
                                  (0x80000000, 0x7fffffff), (0x7fffffff, 0x80000000)])
        c.set(_xrow(ctx, slot) + X_OCC, u8(occ))
        c.set(ch + C_HP, u32(hp))
        c.set(ch + C_HCOND, u32(cond))
        c.set(ch + C_EXP, struct.pack('<II', exp, goal))
        c.arg(slot)
        c.note(slot=slot, occ=occ, hp=hp, cond=cond, exp=exp, goal=goal)
        edges = (['cond_negative'] if cond >= 0x80000000 else []) + \
            (['bool_byte'] if occ not in (0, 1) else [])
        if edges:
            c.note(edge=','.join(edges))


def _find_free_slot(ctx):
    """unsigned int FindFreePartySlot(unsigned int first, unsigned int last)"""
    fn = ctx.fn(0x004ef460)
    for i in range(ctx.n(200)):
        r = ctx.rng('freeslot', i)
        c = ctx.case('findfreepartyslot.%d' % i, fn, conv='c', ret='i')
        x = r.random()
        if x < 0.1:
            occ = [1] * 8
        elif x < 0.15:
            occ = [0] * 8
        else:
            p = r.choice([0.5, 0.7, 0.9])
            occ = [1 if r.random() < p else 0 for _ in range(8)]
        for s in range(8):
            c.set(_xrow(ctx, s) + X_OCC, u8(occ[s]))
        x = r.random()
        if x < 0.06:
            first, last = 0xffffffff, r.randrange(0, 9)
        elif x < 0.2:
            first = r.randrange(0, 9)
            last = r.randrange(0, first + 1)
        else:
            first = r.choice([0, 0, 2, r.randrange(0, 8)])
            last = r.choice([8, 8, 2, r.randrange(first, 9)])
            if last < first:
                last = 8
        c.arg(first)
        c.arg(last)
        c.note(occ=''.join(map(str, occ)), first=first, last=last)


# --------------------------------------------------------------------------------------
def _level_band(ctx):
    """void CalcCharacterLevelBand(W8Character*)"""
    fn = ctx.fn(0x004eed80)
    levels = [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 15, 16, 17, 21, 22, 23, 27, 28, 29, 30, 40,
              50, 100]
    for i in range(ctx.n(300)):
        r = ctx.rng('levelband', i)
        c = ctx.case('levelband.%d' % i, fn, conv='c', ret='v')
        party = ctx.set_party(c, r)
        slot, blob, name = party[r.randrange(8)]
        ch = ctx.char(slot)
        prof = r.randrange(15)
        orig = prof if r.random() < 0.6 else r.randrange(15)
        x = r.random()
        if x < 0.05:
            lvl = r.choice([-1, -5, -0x80000000, 0x7fffffff])
        elif x < 0.6:
            lvl = r.choice(levels)
        else:
            lvl = r.randrange(0, 41)
        x = r.random()
        if x < 0.5 or lvl <= 0:
            base = 0 if r.random() < 0.8 else r.randrange(0, 30)
        elif x < 0.9:
            base = r.randrange(0, lvl + 1)
        else:
            base = lvl + r.randrange(1, 10)
        for p in range(15):
            if p != prof and r.random() < 0.2:
                blob.u32(C_PROF_LEVELS + 4 * p, r.randrange(0, 30))
        blob.u32(C_PROF_LEVELS + 4 * prof, lvl)
        c.set(ch + C_PROF, struct.pack('<ii', prof, orig))
        c.set(ch + C_PROF_LEVELS, bytes(blob[C_PROF_LEVELS:C_PROF_LEVELS + 60]))
        c.set(ch + C_LEVEL_BAND, u32(r.getrandbits(32)) + u32(base))
        c.arg(ch)
        c.cap(ch, CHAR, 'char')
        c.note(char=name, prof=prof, orig=orig, level=lvl, base=base)


def _table_value(ctx):
    """void CalcCharacterTableValue(W8Character*): g_character_table[(sex*16+race)*15+prof]"""
    fn = ctx.fn(0x004ef950)
    combos = [(g, race, p) for g in (0, 1) for race in range(11) for p in range(15)]
    r0 = ctx.rng('tablevalue', 'extra')
    combos += [(r0.choice([0, 1]), r0.randrange(11, 16), r0.randrange(15)) for _ in range(30)]
    for i, (g, race, p) in enumerate(combos[:ctx.n(len(combos))]):
        r = ctx.rng('tablevalue', i)
        c = ctx.case('tablevalue.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        ctx.set_party(c, r, slots=[slot])
        ch = ctx.char(slot)
        c.set(ch + C_PROF, u32(p))
        c.set(ch + C_RACE, struct.pack('<ii', race, g))
        c.set(ch + C_PORTRAIT, u32(r.getrandbits(32)))
        c.arg(ch)
        c.cap(ch, CHAR, 'char')
        c.note(gender=g, race=race, prof=p)


def _personality(ctx):
    """void DeriveCharacterPersonality(W8Character*)"""
    fn = ctx.fn(0x004efa30)
    combos = [(g, p, race) for g in (0, 1) for p in range(15) for race in range(11)]
    r0 = ctx.rng('personality', 'extra')
    combos += [(r0.choice([0, 1]), r0.choice([15, 16]), r0.randrange(11)) for _ in range(10)]
    for i, (g, p, race) in enumerate(combos[:ctx.n(len(combos))]):
        r = ctx.rng('personality', i)
        c = ctx.case('personality.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        ctx.set_party(c, r, slots=[slot])
        ch = ctx.char(slot)
        c.set(ch + C_PROF, u32(p))
        c.set(ch + C_RACE, struct.pack('<ii', race, g))
        c.set(ch + C_007D, struct.pack('<III', r.getrandbits(32), r.getrandbits(32), r.getrandbits(32)))
        c.arg(ch)
        c.cap(ch, CHAR, 'char')
        c.note(gender=g, prof=p, race=race)


def _unique_voice(ctx):
    """void EnsureUniquePartyVoice(W8Character*): Random(9)/Random(2) re-rolls (seeded)."""
    fn = ctx.fn(0x004efad0)
    for i in range(ctx.n(200)):
        r = ctx.rng('uniquevoice', i)
        c = ctx.case('uniquevoice.%d' % i, fn, conv='c', ret='v')
        party = ctx.set_party(c, r)
        trip = []
        eb = _edge_slots(r, 0.0, 0.08)[1]
        for s in range(8):
            inp = _bool_byte(r, 0.85, 1.0 if s == eb else 0.0)
            g = r.choice([0, 1])
            pers = r.randrange(3) if r.random() < 0.7 else r.randrange(9)
            voice = r.choice([0, 1])
            trip.append([inp, g, pers, voice])
        use_scratch = r.random() < 0.2
        t = r.randrange(8)
        if use_scratch:
            blob, name = ctx.pick_char(r)
            g, pers, voice = r.choice([0, 1]), r.randrange(3), r.choice([0, 1])
        else:
            name = party[t][2]
            g, pers, voice = trip[t][1], trip[t][2], trip[t][3]
        if r.random() < 0.5:   # force a clash with another in-party member
            o = r.choice([s for s in range(8) if use_scratch or s != t])
            trip[o] = [1, g, pers, voice]
            if r.random() < 0.4:  # and a second one with the flipped voice
                o2 = r.choice([s for s in range(8) if s != o and (use_scratch or s != t)])
                trip[o2] = [1, g, pers, 1 - voice]
        for s in range(8):
            inp, gg, pp, vv = trip[s]
            ch = ctx.char(s)
            c.set(ch + C_IN_PARTY, u8(inp))
            c.set(ch + C_GENDER, u32(gg))
            c.set(ch + C_PERSONALITY, struct.pack('<ii', pp, vv))
        if use_scratch:
            blob.u8(C_IN_PARTY, 1)
            blob.u32(C_GENDER, g)
            blob.u32(C_PERSONALITY, pers)
            blob.u32(C_VOICE, voice)
            target = ctx.scratch(2)
            c.set(target, bytes(blob))
        else:
            target = ctx.char(t)
        c.arg(target)
        for s in range(8):
            c.cap(ctx.char(s), CHAR, 'char%d' % s)
        if use_scratch:
            c.cap(target, CHAR, 'target')
        c.note(target='scratch' if use_scratch else 'slot%d' % t, char=name,
               triples=';'.join('%x%d%d%d' % tuple(x) for x in trip))
        if any(x[0] not in (0, 1) for x in trip):
            c.note(edge='bool_byte')


def _average_level(ctx):
    """unsigned int GetAveragePartyLevel(void)"""
    fn = ctx.fn(0x004ef420)
    for i in range(ctx.n(200)):
        r = ctx.rng('averagelevel', i)
        c = ctx.case('averagelevel.%d' % i, fn, conv='c', ret='i')
        if i < 3:
            occ = [0] * 8          # divide by zero in both
        else:
            eb = _edge_slots(r, 0.0, 0.06)[1]
            p = r.choice([0.5, 0.75, 1.0])
            occ = [_bool_byte(r, p, 1.0 if s == eb else 0.0) for s in range(8)]
            if not any(occ):
                occ[r.randrange(8)] = 1
        x = r.random()
        for s in range(8):
            if x < 0.1:
                lvl = r.choice([0x40000000, 0x7fffffff, 0x80000000, 0xffffffff, r.getrandbits(32)])
            elif x < 0.2:
                lvl = r.choice([0, 1, 0xffffffff])
            else:
                lvl = r.randrange(1, 31)
            c.set(_xrow(ctx, s) + X_OCC, u8(occ[s]))
            c.set(ctx.char(s) + C_LEVEL, u32(lvl))
        c.note(occ='.'.join('%x' % o for o in occ))
        if any(o not in (0, 1) for o in occ):
            c.note(edge='bool_byte')


# --------------------------------------------------------------------------------------
def _initiative(ctx):
    """void CalcInitiative(W8Character*)"""
    fn = ctx.fn(0x004ee000)
    attr_edge = [0, 4, 5, 9, 10, 49, 50, 51, 100, 125, 126, 255, 0x7fffffff, 0xffffffff]
    for i in range(ctx.n(300)):
        r = ctx.rng('initiative', i)
        c = ctx.case('initiative.%d' % i, fn, conv='c', ret='v')
        party = ctx.set_party(c, r)
        slot, blob, name = party[r.randrange(8)]
        ch = ctx.char(slot)
        level = r.choice([0, 1, 2, 3, 0x7fffffff, 0xfffffffe, 0xffffffff]) if r.random() < 0.1 \
            else r.randrange(1, 31)
        c.set(ch + C_LEVEL, u32(level))
        for a in (A_SPEED, A_SENSES):
            if r.random() < 0.8:
                v = r.choice(attr_edge) if r.random() < 0.15 else r.randrange(1, 126)
                c.set(ch + ATTR + a * 0x14 + 4, u32(v))
        sk = ch + SKILL + S_SNAKESPEED * SKILL_STEP
        active = None
        if r.random() < 0.7:
            active = _bool_byte(r, 0.5, 0.06)
            c.set(sk, u8(active))
        if r.random() < 0.7:
            c.set(sk + 6, u32(r.choice([0, 9, 10, 19, 20, 99, 100, 125, 0xffffffff])
                              if r.random() < 0.2 else r.randrange(0, 126)))
        dmg = r.choice([-128, -1, 0, 127]) if r.random() < 0.1 else r.randrange(-10, 11)
        c.set(ch + C_BONUS + B_DAMAGE, u8(dmg))
        load = r.choice([5, 100, 0xffffffff]) if r.random() < 0.06 else r.randrange(5)
        c.set(ch + C_LOAD, u32(load))
        c.arg(ch)
        c.cap(ch, CHAR, 'char')
        c.note(char=name, level=level, load=load, damage_bonus=dmg)
        if active not in (None, 0, 1):
            c.note(edge='bool_byte')


def _armor_classes(ctx):
    """void CalcArmorClasses(W8Character*)"""
    fn = ctx.fn(0x004ee9d0)
    gx = ctx.g('gXStatus')
    gcs = ctx.g('g_combat_state')
    cs = ctx.scratch(0)
    for i in range(ctx.n(400)):
        r = ctx.rng('armorclasses', i)
        c = ctx.case('armorclasses.%d' % i, fn, conv='c', ret='v')
        party = ctx.set_party(c, r)
        slot, blob, name = party[r.randrange(8)]
        ch = ctx.char(slot)
        # equipment: real items for the slot, sometimes empty or any item id
        p_equip = r.choice([0.4, 0.75, 0.95])
        equip = []
        for e in range(12):
            x = r.random()
            if x < 0.05:
                item = r.randrange(ITEM_COUNT)
            elif x < p_equip:
                item = r.choice(SLOT_ITEMS[e])
            else:
                item = -1
            equip.append(item)
            blob.u32(C_EQUIP + e * 0xc, item)
        c.set(ch + C_EQUIP, bytes(blob[C_EQUIP:C_EQUIP + 12 * 0xc]))
        cond = _cond(r, edge_p=0.03)
        c.set(ch + C_HCOND, u32(cond))
        hp = _hp(r)
        c.set(ch + C_HP, u32(hp))
        race = 5 if r.random() < 0.3 else r.randrange(11)
        prof = -1 if r.random() < 0.03 else r.randrange(15)
        c.set(ch + C_PROF, u32(prof))
        c.set(ch + C_RACE, u32(race))
        speed = r.choice([0, 1, 9, 10, 11, 19, 20, 21, 79, 80, 81, 89, 90, 91, 125, 0xffffffff]) \
            if r.random() < 0.5 else r.randrange(1, 126)
        c.set(ch + ATTR + A_SPEED * 0x14 + 4, u32(speed))
        for s, lv_edge in ((S_STEALTH, [0, 9, 10, 99, 100, 125]),
                           (S_REFLEXTION, [0, 19, 20, 39, 40, 100, 125]),
                           (S_SHIELD, [0, 14, 15, 24, 25, 30, 45, 50, 75, 100, 125, 0xffffffff])):
            base = ch + SKILL + s * SKILL_STEP
            if r.random() < 0.8:
                c.set(base + 6, u32(r.choice(lv_edge) if r.random() < 0.4 else r.randrange(0, 126)))
        reflextion = _bool_byte(r, 0.5, 0.05)
        c.set(ch + SKILL + S_REFLEXTION * SKILL_STEP, u8(reflextion))
        bonus = ch + C_BONUS
        c.set(bonus + B_ARMOR_FLAT, struct.pack('<bb', r.choice([0, 0, r.randrange(-10, 11), -128, 127]),
                                                 r.choice([0, 0, r.randrange(-10, 11), -128, 127])))
        c.set(bonus + B_OUT_OF_FORMATION, u8(_bool_byte(r, 0.2, 0.2)))  # unsigned char flag
        c.set(bonus + B_AC_ADJUST, struct.pack('<b', r.choice([0, 0, r.randrange(-10, 11), -128, 127])))
        load = r.choice([5, 0xffffffff]) if r.random() < 0.05 else r.randrange(5)
        c.set(ch + C_LOAD, u32(load))
        band = r.choice([5, 7, 39, 41, 100, 0xffffffff, 0x80000000]) if r.random() < 0.1 else r.randrange(5)
        c.set(ch + C_FATIGUE_BAND, u32(band))
        combat = r.random() < 0.25
        c.set(gx + GX_COMBAT_MODE, u8(1 if combat else 0))
        action = None
        if combat:
            # CharacterPointerToPartySlot needs fInParty. TryCharacterAction(slot, DEFEND=4)
            # then (slot, PROTECT=5): with characters[slot].dead = 1 it only compares
            # XChar.pending_action; with dead = 0 and XChar.action = DEFEND it returns true
            # before CharacterCanSwitchTo (never reached here).
            c.set(ch + C_IN_PARTY, u8(1))
            c.setp(gcs, cs)
            row = _xrow(ctx, slot)
            if r.random() < 0.7:
                c.set(cs + CS_CHARS + slot * CS_ROW + CS_DEAD, u8(1))
                action = r.choice([4, 4, 5, 5, 0, 1, 3, 6])
                c.set(row + X_PENDING_ACTION, u32(action))
            else:
                action = 'action=4'
                c.set(row + X_ACTION, u32(4))
        c.arg(ch)
        c.cap(ch, CHAR, 'char')
        c.note(char=name, slot=slot, cond=cond, hp=hp, race=race, prof=prof, speed=speed,
               load=load, fatigue_band=band, combat=int(combat), action=action,
               equip=','.join(str(e) for e in equip))
        edges = (['cond_negative'] if cond >= 0x80000000 else []) + \
            (['bool_byte'] if reflextion not in (0, 1) else [])
        if edges:
            c.note(edge=','.join(edges))


def _award_experience(ctx):
    """void AwardPartyExperience(int amount, int alternate_message)"""
    fn = ctx.fn(0x004eef10)
    gs = ctx.g('g_status')
    gx = ctx.g('gXStatus')
    for i in range(ctx.n(250)):
        r = ctx.rng('awardexp', i)
        c = ctx.case('awardexperience.%d' % i, fn, conv='c', ret='v')
        party = ctx.set_party(c, r)
        edges = []
        ec, eb = _edge_slots(r)
        for s in range(8):
            ch = ctx.char(s)
            occ = _bool_byte(r, 0.8, 1.0 if s == eb else 0.0)
            hp = _hp(r)
            cond = _cond(r, 1.0 if s == ec else 0.0)
            x = r.random()
            if x < 0.4:
                exp = party[s][1].get_u32(C_EXP)
            elif x < 0.6:
                exp = r.getrandbits(32)
            elif x < 0.85:
                exp = 0xffffffff - r.choice([0, 1, 2, 100, r.randrange(0, 2000000)])
            else:
                exp = r.choice([0, 1, 0x7fffffff, 0x80000000])
            if occ not in (0, 1):
                edges.append('bool_byte')
            if cond >= 0x80000000:
                edges.append('cond_negative')
            c.set(_xrow(ctx, s) + X_OCC, u8(occ))
            c.set(ch + C_HP, u32(hp))
            c.set(ch + C_HCOND, u32(cond))
            c.set(ch + C_EXP, u32(exp))
        x = r.random()
        if x < 0.75:
            level = r.choice([2, 2, 3, r.randrange(0, LEVEL_COUNT)])
        else:
            level = r.choice([0, 0x2e, 0x2f, 0x30, 100, 0x7fffffff, -1, -2])
        c.set(gs + GS_CURRENT_LEVEL, u32(level))
        if -2 <= level < LEVEL_COUNT:
            gained = r.choice([0, r.randrange(0, 10 ** 7), r.getrandbits(32),
                               0xffffffff - r.randrange(0, 1000000), 0xffffffff])
            c.set(gs + GS_LEVEL_PROGRESS + level * GS_LP_ROW + GS_LP_EXP, u32(gained))
        c.set(gx + GX_LEVEL_UP_NOTICE, u8(0))
        count = _redirect_messages(ctx, c)
        amount = r.choice([0, 1, 100, 1000, 12345, r.randrange(1, 10 ** 6), r.randrange(1, 2 ** 31),
                           0x7fffffff, -0x80000000, -1, -1000, r.randrange(-10 ** 6, 0)])
        alt = r.choice([0, 1]) if r.random() < 0.95 else r.choice([2, 0xff])
        c.arg(amount)
        c.arg(alt)
        for s in range(8):
            c.cap(ctx.char(s), CHAR, 'char%d' % s)
        c.cap(gs + GS_CURRENT_LEVEL, GS_LEVEL_PROGRESS + LEVEL_COUNT * GS_LP_ROW - GS_CURRENT_LEVEL,
              'level_progress')
        c.cap(gx + GX_LEVEL_UP_NOTICE, 1, 'level_up_notice')
        c.cap(count, 4, 'message_count')
        c.note(amount=amount, alt=alt, level=level)
        if edges:
            c.note(edge=','.join(sorted(set(edges))))
