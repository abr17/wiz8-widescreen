"""CharGeneration.cpp (decomp/src/wiz8/local_code/CharGeneration.cpp): the character
creation / level-up editing state (W8CharacterCreationState, 0x270 bytes) and its pools,
limits, profession/race tables, spell picks and starting equipment.

Tested (retail address, name, cases at --scale 1):
  0x00556dc0 InitializeCharacterCreation         40  output is input independent (memset);
                                                     garbage char/state/globals must vanish
  0x00556cc0 InitializeCharacterLevelUp         250  level 0 (-> 1, 60-point pool), attribute
                                                     debt (bases below profession minimums)
  0x00556eb0 ApplyRaceProfessionTables          400  race/profession/gender -1 (unset) paths,
                                                     level 1 vs > 1, attribute bonus incl. -60,
                                                     -61 and 0x7fffffff (pool overflow)
  0x00557060 RebuildLevelUpPoolsForProfession   300  Valkyrie gender lock, old profession -1,
                                                     level > 1 refunds; professions with a -1
                                                     skill slot write skills[-1] / baselines[-1]
                                                     in retail (same layout, so must match)
  0x005571c0 SetCharacterRace                   120
  0x005571e0 SetCharacterGender                 120
  0x00557200 PayDownAttributeDebt               300  tied deficits (qsort order, note ties=N), pool
                                                     = shortfall -1/0/+1, 0, huge, negative,
                                                     unsigned huge bases
  0x00557350 DetermineEligibleProfessions       300  pool + deficit = -1 / 0, limit - value + base
                                                     = minimum - 1 / minimum, iProfession with the
                                                     high word set (retail compares only the low
                                                     16 bits: note edge='prof_hiword'), pool
                                                     -0x80000000
  0x00557430 AddCharacterStartingEquipment      200  all 15 professions, faerie row, fighter /
                                                     priest weapon choice ties, game_started 0/1
  0x00557580 FinalizeCreatedCharacter           300  bishop / realm cost settlement, spell 0x49,
                                                     starting equipment flag incl. 0x100 / 0xff
                                                     (note edge='bool_arg'), magic bonus bytes
  0x00557730 RecomputeAttributeLimits           300  step thresholds (pool+baselines 0..6),
                                                     negative pool, bases > value + 100
  0x00557800 ClampAttributesToBudget            250  incl. 6 cases value-limit overflow
                                                     (retail: sub + jle; note edge='sub_overflow')
  0x00557890 ApplyProfessionMinimumAttributes   300  pay-down boundary (pool = shortfall - 1 / 0),
                                                     level 0 / 1 / > 1 / 0xffffffff, bases 0 /
                                                     0x80000000 / 0xffffffff
  0x005579e0 AdjustAllocatedAttribute           350  modifier at the pool / limit clamp +-1, assert
                                                     line 0x380 (value + modifier wraps)
  0x00557ae0 RefundAllocatedAttributes          200
  0x00557b20 RecomputeSkillLimits               300  covers the inlined ClampSkillsToBudget; skill
                                                     limit = step -1/0/+1; 6 crafted spent-limit
                                                     overflow cases (note edge='sub_overflow')
  0x00557bc0 InitializeLevelUpAttributePool     300  (the per-skill commit) clamp boundaries,
                                                     assert line 0x448
  0x00557c90 ResetSkillContribution             250  realm skills with profession level 5 for
                                                     offset -4 professions; skill -1 / 0x29
  0x00557d20 RefundSkillAllocation              200
  0x00557d80 RebuildSkillAllocations            300  all professions, pool debt incl. -0x80000000
  0x00557f90 RefundAllSkillPoints               200
  0x00557fd0 ComputeRealmSkillDebt              250  original (S1) + edited copy (S2), caster
                                                     level 0 / -1 / > 0 on either side
  0x00558070 FinalizeSpellPointPool             300  g_spell_point_bonus, trimming selected spells
  0x00558180 CountRemainingSpellPoints          300
  0x00558330 ComputeLevelUpSpellPointAward      300  level 0 / 1 (trial spells, qsort) / > 1
  0x005584e0 SelectCreationSpell                250  linked pair 0x49 / 0x4b
  0x00558560 DeselectCreationSpell              250
  0x005585d0 ResetSpellSelections               150
  0x00558640 ComputeStartingEquipmentCost       150  (note expected_cost from Items.dbs values)
  0x005586b0 CanAffordStartingEquipment         150  party gold = expected cost -1 / 0 / +1 (the
                                                     unsigned <= boundary), log-uniform, edges
  Total 7380 cases.

Skipped:
  0x00557eb0 ClampSkillsToBudget - not in Wiz8Runtime.map (inlined); covered through
             RecomputeSkillLimits (and every caller of it).

Set-up common to every case (all restored by the core afterwards):
  * the edited character is a corpus character put into scratch 1 (setb + one diffed set),
    with fInParty = 0, hp_current >= uiHPMax (RecalculateCharacterHitPoints can never reach
    its death path, which would look the scratch pointer up as a party slot),
    fatigue_penalty = 0 and inventory_weight = 0xffffffff (RecalculateCarriedWeight never
    sees an "old weight below capacity" and so never queues the overload event).  A
    scratch pointer also keeps UnequipUnusableItems (party pointers only) out of the
    derived-stat rebuilds, like the real creation screen's temporary character;
  * W8CharacterCreationState in scratch 0 (sparse sets; scratch is zeroed per case);
  * g_current_screen_state.id = 8 (AUTOMAP: no Character-screen row refresh, no main game
    redraw), gXStatus.fCombatMode = 0, g_status.greeting_pending = 1 (a stray character
    event would be deleted by QueueEntry), g_status.game_started set explicitly, and the
    four file statics g_attribute_point_bonus, g_skill_point_bonus, g_spell_point_bonus,
    g_gender_locked set and captured;
  * functions that reach RecalculateCharacterDerivedStats or AddItemToCharacter
    (FinalizeCreatedCharacter and the three starting-equipment functions) run with
    game_started 0 or 1; with 1 the 8 party slots get corpus characters, explicit
    XChar.fOccupied, and all 8 are captured together with gXStatus.fEncumbranceDirty
    (RedistributePartyEncumbrance rewrites them);
  * captured: the scratch character (regen-rate floats compared with tolerance), the
    state, the four statics, plus the function's own outputs (eligibility bytes in scratch
    3, second character in scratch 2).
  No starting item has a record value above 500, so DeliverExceptionalItemReaction never
  queues an event for the scratch character (its value / level test stays <= 500).
  Inputs avoided on purpose (retail reads outside its own tables, so both sides would
  differ by design): iProfession -1 wherever GetProfessionCasterLevel / skill-availability /
  starting-equipment tables are indexed with it, races >= 11, gender -1 together with item
  use checks (gender-mask shift by -1), uiExpLevel 0 where CalcXPGoal or the
  exceptional-item value / level division runs, attribute sums that would make the stamina
  ceiling 0, skill or attribute sums that wrap to positive with no positive entry (the
  round-robin refund loops would never end).
"""
import struct

from w8diff.api import Blob

CHAR = 0x1862
STATE = 0x270
NSK = 0x29          # skills
NSP = 0x72          # creation-relevant spell ids

# ---- W8Character (layout.ps1, wiz8/layouts/character.h) ----
C_IN_PARTY = 0x04
C_PROF = 0x69
C_ORIG = 0x6d
C_RACE = 0x71
C_GENDER = 0x75
C_PORTRAIT = 0x79
C_LEVEL = 0x89
C_PLEV = 0x8d        # int profession_levels[15]
C_BAND = 0xdd
C_BAND_BASE = 0xe1
C_ATTR = 0xe5        # W8CharacterAttribute[7]: base +0, effective +4
A_STEP = 0x14
C_DEFICIT = 0x199    # attribute_point_deficit
C_SKILL = 0x19d      # W8CharacterSkill[0x29]
SK_STEP = 0x26
SK_ACTIVE = 0x00
SK_POINTS = 0x02
SK_LEVEL = 0x06
C_GOAL = 0x9f1
C_HPMAX = 0xb0d
C_HP = 0xb11
C_FATIGUE_PEN = 0xb21
C_SPMAX = 0xb25      # int sp_max[6]
C_INV_W = 0xbb9
C_LEARNED = 0xbcd    # int spell_learned[136]
C_COSTS = 0x185c     # unsigned char skill_costs[4] (skills 0x18..0x1b)
C_POOL = 0x1860      # unsigned char magic_bonus_pool
# float health/stamina regen rate + accumulators and spell_regen_rates[12] (0xb69..0xba5)
C_FLOATS = [0xb69 + 4 * k for k in range(16)]

S_SWORD, S_AXE, S_MACE, S_STAFF = 0, 1, 3, 5
S_DUAL = 0x10
REALM_BOOKS = range(0x18, 0x1c)
REALM_MAGIC = range(0x1c, 0x22)

# ---- W8CharacterCreationState (wiz8/local_code/CharGeneration.h, layout.ps1) ----
ST_A_REM = 0x00
ST_A_TOT = 0x04
ST_A_VAL = 0x08
ST_A_STEP = 0x24
ST_A_LIM = 0x28
ST_A_DONE = 0x44
ST_A_BASE = 0x48
ST_S_REM = 0x64
ST_S_TOT = 0x68
ST_S_SPENT = 0x6c
ST_S_STEP = 0x110
ST_S_LIM = 0x114
ST_S_DONE = 0x1b8
ST_S_BASE = 0x1bc
ST_SP_REM = 0x260
ST_SP_TOT = 0x264
ST_SP_BONUS = 0x268
ST_SP_DONE = 0x26c
PADS = ((0x45, 3), (0x1b9, 3), (0x26d, 3))

# ---- globals ----
GS_GAME_STARTED = 0x0c
GS_PARTY_GOLD = 0x19
GS_GREETING = 0x2497
GX_COMBAT = 0x8dc
GX_ENC_DIRTY = 0x8e8
XROW = 0x106          # W8PartySlotRow, fOccupied at +0
SCREEN_AUTOMAP = 8

# ---- retail tables (read from Wiz8.exe, identical in the port) ----
PROF_MIN = [[55, 0, 0, 50, 50, 0, 0], [55, 0, 55, 55, 50, 50, 0], [50, 0, 55, 55, 50, 50, 0],
            [50, 50, 0, 50, 55, 0, 55], [50, 55, 0, 50, 55, 55, 0], [50, 50, 0, 50, 55, 55, 50],
            [0, 50, 50, 0, 50, 55, 55], [0, 0, 0, 0, 55, 50, 50], [45, 55, 0, 0, 60, 0, 55],
            [45, 50, 0, 0, 55, 0, 55], [0, 0, 60, 55, 0, 0, 0], [0, 55, 0, 0, 60, 0, 0],
            [0, 55, 55, 0, 55, 0, 55], [0, 55, 0, 0, 0, 0, 60], [0, 60, 0, 0, 55, 0, 0]]
RACE_MIN = [[45, 45, 45, 45, 45, 45, 45], [35, 50, 50, 35, 50, 45, 40], [55, 30, 50, 60, 35, 35, 35],
            [35, 50, 40, 50, 50, 35, 45], [40, 40, 30, 45, 55, 50, 50], [25, 55, 35, 30, 50, 60, 45],
            [60, 25, 25, 70, 40, 50, 30], [55, 35, 30, 60, 50, 40, 30], [40, 40, 30, 35, 50, 60, 50],
            [40, 30, 55, 50, 40, 40, 50], [50, 50, 25, 50, 35, 35, 55]]
PROF_SKILLS = [[17, 0, 1, 6], [16, 0, 4, -1], [16, 21, 1, -1], [15, 8, 21, -1], [16, 18, 19, -1],
               [16, 14, 9, 11], [16, 19, 5, 11], [4, 18, 13, 11], [17, 23, 10, -1], [12, 21, 20, -1],
               [3, 5, 22, -1], [21, 9, -1, -1], [26, 24, 25, 27], [22, 21, 32, -1], [28, 29, 30, 32]]
BONUS_SKILL = [16, 18, 2, 17, 0, 19, 14, 10, 7, 22, 25, 26, 20, 27, 24]
MAGIC_OFF = [-255, -4, -4, -4, -4, -4, -4, -255, -255, -255, 0, 0, 0, 0, 0]
P_FIGHTER, P_VALKYRIE, P_GADGETEER, P_BARD, P_PRIEST, P_BISHOP = 0, 2, 8, 9, 10, 12
R_FAERIE = 5
START_EQ = [[143, 153, 203, 246, -1, -1], [35, 1, 158, 204, 247, 210], [75, 170, 197, 246, 215, -1],
            [110, 125, 157, 188, 247, -1], [38, 49, 165, 192, 246, -1], [105, 230, 180, 209, 253, -1],
            [79, 105, 165, 192, 246, -1], [0, 0, 99, 156, 187, 247], [132, 156, 187, 246, -1, -1],
            [769, 116, 132, 156, 187, -1], [165, 192, 246, 335, -1, -1], [28, 165, 192, 246, 350, -1],
            [82, 165, 192, 246, 223, -1], [0, 165, 192, 246, 347, -1], [28, 165, 192, 246, 385, -1],
            [63, 169, 196, 335, 358, 0]]
# GetItemStackValue of a freshly created (maximum quantity) stack, from Items.dbs: value,
# quantity kind / dice maximum and the ammunition bundle rule of the starting items.
STACK_VALUE = {0: 15, 1: 30, 7: 60, 18: 100, 22: 65, 28: 5, 35: 125, 38: 400, 49: 240, 63: 40,
               75: 20, 79: 12, 82: 10, 99: 22, 105: 30, 110: 250, 116: 35, 125: 16, 132: 2,
               143: 65, 153: 285, 156: 10, 157: 85, 158: 175, 165: 15, 169: 20, 170: 25, 180: 30,
               187: 10, 188: 60, 192: 15, 196: 20, 197: 25, 203: 165, 204: 190, 209: 30, 210: 300,
               215: 145, 223: 200, 230: 50, 246: 25, 247: 50, 253: 85, 324: 100, 335: 300, 347: 200,
               350: 500, 358: 175, 385: 250, 599: 0, 769: 30}


def expected_equipment_cost(prof, race, levels):
    """Sum the staged starting set the way ComputeStartingEquipmentCost does (every item
    fits the 12 + 8 slots, so nothing is dropped). levels: sword, axe, mace, staff."""
    row = START_EQ[15 if race == R_FAERIE else prof]
    total = sum(STACK_VALUE[x] for x in row if x >= 0)
    sword, axe, mace, staff = (v & 0xffffffff for v in levels)
    if prof == P_PRIEST:
        total += STACK_VALUE[0x16 if mace > staff else 0x52]
    elif prof == P_FIGHTER:
        total += STACK_VALUE[0x12 if axe > sword else 7]
    elif prof == P_GADGETEER:
        total += STACK_VALUE[599]
    elif prof == P_BARD:
        total += STACK_VALUE[0x144]
    return total


def u8(v):
    return bytes([int(v) & 0xff])


def u32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def s32(v):
    v = int(v) & 0xffffffff
    return v - (1 << 32) if v >= (1 << 31) else v


def pick(r, edges, lo, hi, pe=0.2):
    if r.random() < pe:
        return r.choice(edges)
    return r.randint(lo, hi)


def alloc(r, total, n):
    """Spread up to total points over n slots (totals stay small)."""
    out = [0] * n
    if total <= 0:
        return out
    used = total if r.random() < 0.4 else r.randint(0, total)
    for _ in range(used):
        out[r.randrange(n)] += 1
    return out


def set_sparse(c, addr, data, gap=8):
    """Scratch is zeroed before every case: write only the non-zero runs."""
    n = len(data)
    k = 0
    while k < n:
        if data[k] == 0:
            k += 1
            continue
        s = last = k
        while k < n and k - last <= gap:
            if data[k] != 0:
                last = k
            k += 1
        c.set(addr + s, bytes(data[s:last + 1]))
        k = last + 1


# --------------------------------------------------------------------------------------
# creation state

def new_state():
    return {'a_rem': 0, 'a_tot': 0, 'a_val': [0] * 7, 'a_step': 0, 'a_lim': [0] * 7, 'a_done': 0,
            'a_base': [0] * 7, 's_rem': 0, 's_tot': 0, 's_spent': [0] * NSK, 's_step': 0,
            's_lim': [0] * NSK, 's_done': 0, 's_base': [0] * NSK, 'sp_rem': 0, 'sp_tot': 0,
            'sp_bonus': 0, 'sp_done': 0, 'pad': False}


def pack_state(d):
    b = bytearray(STATE)

    def w(off, v):
        struct.pack_into('<I', b, off, int(v) & 0xffffffff)

    def arr(off, vals):
        for k, v in enumerate(vals):
            w(off + 4 * k, v)

    w(ST_A_REM, d['a_rem'])
    w(ST_A_TOT, d['a_tot'])
    arr(ST_A_VAL, d['a_val'])
    w(ST_A_STEP, d['a_step'])
    arr(ST_A_LIM, d['a_lim'])
    arr(ST_A_BASE, d['a_base'])
    w(ST_S_REM, d['s_rem'])
    w(ST_S_TOT, d['s_tot'])
    arr(ST_S_SPENT, d['s_spent'])
    w(ST_S_STEP, d['s_step'])
    arr(ST_S_LIM, d['s_lim'])
    arr(ST_S_BASE, d['s_base'])
    w(ST_SP_REM, d['sp_rem'])
    w(ST_SP_TOT, d['sp_tot'])
    w(ST_SP_BONUS, d['sp_bonus'])
    if d['pad']:   # garbage in the bool padding: a dword store would clear it
        for off, n in PADS:
            b[off:off + n] = b'\x5a' * n
    b[ST_A_DONE] = d['a_done'] & 0xff
    b[ST_S_DONE] = d['s_done'] & 0xff
    b[ST_SP_DONE] = d['sp_done'] & 0xff
    return bytes(b)


def gen_state(r, level1=True, a_total=None, s_total=None, sp_total=None):
    d = new_state()
    if a_total is None:
        a_total = (60 if level1 else 6) if r.random() < 0.45 else \
            pick(r, [0, 1, 2, 3, 4, 5, 7, -1, -6, -20, 100], -15, 70, 0.35)
    d['a_tot'] = a_total
    room = max(0, min(a_total, 90))
    if r.random() < 0.15:
        room += r.randint(1, 10)          # over-allocated
    vals = alloc(r, room, 7)
    if r.random() < 0.05:
        vals[r.randrange(7)] = -r.randint(1, 5)
    d['a_val'] = vals
    d['a_lim'] = [max(v, 0) + r.choice([0, 0, 1, 3, r.randint(0, 25)]) for v in vals]
    if r.random() < 0.1:
        k = r.randrange(7)
        d['a_lim'][k] = max(0, vals[k] - r.randint(1, 5))
    d['a_step'] = r.randint(0, 25)
    if level1 and r.random() < 0.8:
        d['a_base'] = [0] * 7
    else:
        d['a_base'] = [r.choice([0, 0, 0, 1, 2, 5, r.randint(0, 15)]) for _ in range(7)]
    if r.random() < 0.04:
        d['a_base'][r.randrange(7)] = -r.randint(1, 5)
    d['a_rem'] = a_total - sum(vals) if r.random() < 0.8 else pick(r, [0, 1, -1, 60], -5, 30, 0.3)
    d['a_done'] = r.choice([0, 1])

    if s_total is None:
        s_total = (15 if level1 else 9) if r.random() < 0.45 else \
            pick(r, [0, 1, 2, 3, 4, 5, -1, -2, -3, -4, 40, 75], -5, 40, 0.35)
    d['s_tot'] = s_total
    spent = [0] * NSK
    for k in r.sample(range(NSK), r.choice([0, 1, 2, 3, 4, 6, 8])):
        spent[k] = r.randint(1, 12)
    if r.random() < 0.04:
        spent[r.randrange(NSK)] = -r.randint(1, 5)
    d['s_spent'] = spent
    d['s_lim'] = [max(v, 0) + r.choice([0, 0, 1, 3, r.randint(0, 25)]) for v in spent]
    if r.random() < 0.1:
        k = r.randrange(NSK)
        d['s_lim'][k] = max(0, spent[k] - r.randint(1, 5))
    d['s_step'] = r.randint(0, 25)
    if level1 and r.random() < 0.8:
        d['s_base'] = [0] * NSK
    else:
        d['s_base'] = [r.choice([0, 0, 0, 0, 0, 0, 1, 2, 5]) for _ in range(NSK)]
    d['s_rem'] = s_total - sum(spent) if r.random() < 0.8 else pick(r, [0, 1, -1, 15], -5, 30, 0.3)
    d['s_done'] = r.choice([0, 1])

    if sp_total is None:
        sp_total = pick(r, [0, 0, 1, 2, 3, -1], 0, 8, 0.4)
    d['sp_tot'] = sp_total
    if r.random() < 0.85:
        d['sp_rem'] = r.randint(0, max(sp_total, 0))
    else:
        d['sp_rem'] = r.choice([-1, -2, sp_total + 1, sp_total + 3])
    d['sp_bonus'] = pick(r, [0, 1, 2, 3, 0xff, -1], 0, 3, 0.15)
    d['sp_done'] = r.choice([0, 1])
    d['pad'] = r.random() < 0.15
    return d


# --------------------------------------------------------------------------------------
# character edits (Blob of a corpus character)

def attr_base(blob, a):
    return blob.get_u32(C_ATTR + a * A_STEP)


def set_attr(blob, a, base, eff=None):
    blob.u32(C_ATTR + a * A_STEP, base)
    blob.u32(C_ATTR + a * A_STEP + 4, base if eff is None else eff)


def skill_off(k, field=0):
    return C_SKILL + k * SK_STEP + field


def identity(r, blob, prof=None, race=None, gender=None, level=None, multi_p=0.15):
    """Profession / race / sex / level with matching profession_levels (single or two
    professions). prof -1 keeps every profession level at 0."""
    if prof is None:
        prof = blob.get_i32(C_PROF) if r.random() < 0.5 else r.randrange(15)
    if race is None:
        race = blob.get_i32(C_RACE) if r.random() < 0.5 else r.randrange(11)
    if gender is None:
        gender = blob.get_i32(C_GENDER) if r.random() < 0.5 else r.choice([0, 1])
    if level is None:
        x = r.random()
        level = blob.get_u32(C_LEVEL) if x < 0.4 else (1 if x < 0.65 else r.randint(2, 40))
    levels = [0] * 15
    orig = prof
    if 0 <= prof < 15:
        if level > 1 and r.random() < multi_p:
            orig = r.randrange(15)
            if orig != prof:
                a = r.randint(1, level - 1)
                levels[orig] = a
                levels[prof] = level - a
            else:
                levels[prof] = level
        else:
            levels[prof] = level & 0xffffffff
    else:
        orig = r.randrange(15)
    blob.u32(C_PROF, prof)
    blob.u32(C_ORIG, orig)
    blob.u32(C_RACE, race)
    blob.u32(C_GENDER, gender)
    blob.u32(C_LEVEL, level)
    for k in range(15):
        blob.u32(C_PLEV + 4 * k, levels[k])
    return prof, race, gender, level


def safe(blob, inv=True):
    blob.u8(C_IN_PARTY, 0)
    hpmax = blob.get_i32(C_HPMAX)
    if hpmax < 0:
        hpmax = 0
        blob.u32(C_HPMAX, 0)
    if blob.get_u32(C_HP) < hpmax or blob.get_u32(C_HP) > 0x7fffffff:
        blob.u32(C_HP, hpmax)
    blob.u32(C_FATIGUE_PEN, 0)
    if inv:
        blob.u32(C_INV_W, 0xffffffff)


def realm(r, blob, p=0.5):
    """Spellbook skills active flags, their spell-point costs and the magic bonus pool."""
    if r.random() < p:
        for k in REALM_BOOKS:
            blob.u8(skill_off(k), 1 if r.random() < 0.35 else 0)
    if r.random() < p:
        for k in range(4):
            blob.u8(C_COSTS + k, pick(r, [0, 0xff, 1, 0x80], 0, 12, 0.08) if r.random() < 0.6 else 0)
    if r.random() < p:
        blob.u8(C_POOL, pick(r, [0, 0xff, 1, 0x80], 0, 6, 0.08))


def spells(r, blob, p=0.3, mode='mix', edge_p=0.01):
    """spell_learned states: 0 unknown, 1 learned, 2 picked in this session, -1 offered."""
    for k in range(NSP):
        if r.random() >= p:
            continue
        x = r.random()
        if x < edge_p:
            v = r.choice([3, -2, 0x80000000])
        elif mode == 'creation':
            v = 0 if x < 0.4 else (-1 if x < 0.75 else (2 if x < 0.93 else 1))
        else:
            v = r.choice([0, 0, 1, 1, 2, -1, -1])
        blob.u32(C_LEARNED + 4 * k, v)


def skills(r, blob, p=0.25):
    """Random active flags / invested points / levels on a fraction of the skills."""
    for k in range(NSK):
        if r.random() >= p:
            continue
        blob.u8(skill_off(k, SK_ACTIVE), 1 if r.random() < 0.6 else 0)
        pts = pick(r, [0, 1, 5, 75, 100, 125], 0, 60, 0.15)
        blob.u32(skill_off(k, SK_POINTS), pts)
        blob.u32(skill_off(k, SK_LEVEL), pts + r.choice([0, 0, 0, 1, 2, 5]))


def sync_attrs(blob, d, margin=20):
    """Allocated attribute points sit on top of the base, as in the creation flow."""
    for a in range(7):
        v = max(d['a_val'][a], 0)
        base = attr_base(blob, a)
        if base < v + margin or base > 0x7fffffff:
            set_attr(blob, a, v + margin + (base % 7 if base <= 0x7fffffff else 0))


def sync_skills(blob, d, margin=0):
    for k in range(NSK):
        s = d['s_spent'][k]
        if s > 0:
            pts = blob.get_u32(skill_off(k, SK_POINTS))
            if pts < s + margin or pts > 0x7fffffff:
                blob.u32(skill_off(k, SK_POINTS), s + margin)
                blob.u32(skill_off(k, SK_LEVEL), s + margin)


def prof_shortfall(blob, prof):
    """Sum of the positive (minimum - base) differences, as the retail sweeps compute it."""
    total = 0
    for a in range(7):
        diff = s32(PROF_MIN[prof][a] - attr_base(blob, a))
        if diff > 0:
            total += diff
    return total


def c_div(a, b):
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def caster_level_craft(r, blob, prof, p=0.3):
    """Make GetProfessionCasterLevel exactly 0 (offset -4 / 0 professions) sometimes."""
    if 0 <= prof < 15 and MAGIC_OFF[prof] != -255 and r.random() < p:
        blob.u32(C_PLEV + 4 * prof, -MAGIC_OFF[prof])
        return True
    return False


# --------------------------------------------------------------------------------------
class Env:
    def __init__(self, ctx):
        self.ctx = ctx
        self.gs = ctx.g('g_status')
        self.gx = ctx.g('gXStatus')
        self.screen = ctx.g('g_current_screen_state')
        self.bonus = [ctx.g('g_attribute_point_bonus'), ctx.g('g_skill_point_bonus'),
                      ctx.g('g_spell_point_bonus')]
        self.locked = ctx.g('g_gender_locked')
        self.S = ctx.scratch(0)     # W8CharacterCreationState
        self.C = ctx.scratch(1)     # edited character
        self.C2 = ctx.scratch(2)    # second character (ComputeRealmSkillDebt)
        self.E = ctx.scratch(3)     # eligibility bytes

    def xrow(self, s):
        return (self.gs + 8).deref() + s * XROW

    def globals(self, c, bonuses=(0, 0, 0), locked=0, game_started=1):
        c.set(self.screen, u32(SCREEN_AUTOMAP))
        c.set(self.gx + GX_COMBAT, b'\x00')
        c.set(self.gs + GS_GREETING, b'\x01')
        c.set(self.gs + GS_GAME_STARTED, u8(game_started))
        for a, v in zip(self.bonus, bonuses):
            c.set(a, u32(v))
        c.set(self.locked, u8(locked))

    def char(self, c, r, at=None):
        blob, name = self.ctx.pick_char(r)
        c.setb(at or self.C, bytes(blob))
        return blob, name

    def put(self, c, blob, at=None):
        c.set(at or self.C, bytes(blob))

    def put_state(self, c, d):
        set_sparse(c, self.S, pack_state(d))

    def party(self, c, r):
        self.ctx.set_party(c, r)
        occ = [1 if r.random() < 0.85 else 0 for _ in range(8)]
        if not any(occ):
            occ[r.randrange(8)] = 1
        for s in range(8):
            c.set(self.xrow(s), u8(occ[s]))
        return occ

    def caps(self, c, state=True, party=False):
        c.cap(self.C, CHAR, 'char', floats=C_FLOATS)
        if state:
            c.cap(self.S, STATE, 'state')
        for a, n in zip(self.bonus, ('attr_bonus', 'skill_bonus', 'spell_bonus')):
            c.cap(a, 4, n)
        c.cap(self.locked, 1, 'gender_locked')
        if party:
            for s in range(8):
                c.cap(self.ctx.char(s), CHAR, 'party%d' % s, floats=C_FLOATS)
            c.cap(self.gx + GX_ENC_DIRTY, 1, 'encumbrance_dirty')


def garbage_bonuses(r):
    return (pick(r, [0, 5, -100, 0x7fffffff, -0x80000000], -10, 10, 0.3),
            pick(r, [0, 5, -100, 0x7fffffff, -0x80000000], -10, 10, 0.3),
            pick(r, [0, 5, -100, 0x7fffffff, -0x80000000], -10, 10, 0.3))


# --------------------------------------------------------------------------------------
def cases(ctx):
    E = Env(ctx)
    t_init_creation(ctx, E)
    t_init_levelup(ctx, E)
    t_apply_tables(ctx, E)
    t_rebuild_pools(ctx, E)
    t_set_race_gender(ctx, E)
    t_paydown(ctx, E)
    t_eligible(ctx, E)
    t_starting_equipment(ctx, E)
    t_finalize_created(ctx, E)
    t_recompute_attr_limits(ctx, E)
    t_clamp_attrs(ctx, E)
    t_apply_prof_min(ctx, E)
    t_adjust_attr(ctx, E)
    t_refund_attrs(ctx, E)
    t_recompute_skill_limits(ctx, E)
    t_skill_commit(ctx, E)
    t_reset_skill(ctx, E)
    t_refund_skill(ctx, E)
    t_rebuild_skills(ctx, E)
    t_refund_all_skills(ctx, E)
    t_realm_debt(ctx, E)
    t_finalize_spell_pool(ctx, E)
    t_count_remaining(ctx, E)
    t_levelup_award(ctx, E)
    t_select_spells(ctx, E)
    t_reset_spells(ctx, E)


# --------------------------------------------------------------------------------------
def t_init_creation(ctx, E):
    """void InitializeCharacterCreation(W8Character*, W8CharacterCreationState*)"""
    fn = ctx.fn(0x00556dc0)
    for i in range(ctx.n(40)):
        r = ctx.rng('initcreation', i)
        c = ctx.case('initcreation.%d' % i, fn, conv='c', ret='v')
        E.globals(c, bonuses=garbage_bonuses(r), locked=r.choice([0, 1, 0xff]),
                  game_started=r.choice([0, 1]))
        blob, name = E.char(c, r)
        identity(r, blob)
        skills(r, blob, 0.2)
        spells(r, blob, 0.3)
        E.put(c, blob)
        E.put_state(c, gen_state(r, level1=r.random() < 0.5))
        c.arg(E.C)
        c.arg(E.S)
        E.caps(c)
        c.note(char=name)


def t_init_levelup(ctx, E):
    """void InitializeCharacterLevelUp(W8Character*, W8CharacterCreationState*)"""
    fn = ctx.fn(0x00556cc0)
    for i in range(ctx.n(250)):
        r = ctx.rng('initlevelup', i)
        c = ctx.case('initlevelup.%d' % i, fn, conv='c', ret='v')
        E.globals(c, bonuses=garbage_bonuses(r), locked=r.choice([0, 1]), game_started=1)
        blob, name = E.char(c, r)
        x = r.random()
        level = blob.get_u32(C_LEVEL) if x < 0.45 else (0 if x < 0.5 else r.randint(1, 45))
        prof, race, gender, level = identity(r, blob, level=level)
        debt = 0
        if r.random() < 0.35:
            for a in r.sample(range(7), r.randint(1, 4)):
                mn = PROF_MIN[prof][a]
                if mn > 0:
                    d = r.randint(1, min(mn, 25))
                    set_attr(blob, a, mn - d)
                    debt += d
        x = r.random()
        deficit = -debt if x < 0.6 else (0 if x < 0.8 else -r.randint(1, 30))
        blob.u32(C_DEFICIT, deficit)
        realm(r, blob, 0.3)
        spells(r, blob, 0.15)
        safe(blob)
        E.put(c, blob)
        E.put_state(c, gen_state(r, level1=False))      # cleared by the function
        c.arg(E.C)
        c.arg(E.S)
        E.caps(c)
        c.note(char=name, prof=prof, race=race, level=level, debt=debt, deficit=deficit)


# --------------------------------------------------------------------------------------
def tables_setup(ctx, E, c, r, race=None, prof=None, gender=None, level=None):
    """Character + state for the race/profession table application."""
    blob, name = E.char(c, r)
    if race is None:
        x = r.random()
        race = -1 if x < 0.12 else (None if x < 0.5 else r.randrange(11))
    if prof is None:
        x = r.random()
        prof = -1 if x < 0.12 else (None if x < 0.5 else r.randrange(15))
    if gender is None:
        x = r.random()
        gender = -1 if x < 0.08 else r.choice([0, 1])
    if level is None:
        level = 1 if r.random() < 0.55 else r.randint(2, 40)
    prof, race, gender, level = identity(r, blob, prof=prof, race=race, gender=gender, level=level)
    if r.random() < 0.3:
        for a in range(7):
            if r.random() < 0.5:
                set_attr(blob, a, r.randint(25, 100))
    skills(r, blob, 0.15)
    realm(r, blob, 0.4)
    spells(r, blob, 0.3, 'creation')
    d = gen_state(r, level1=(level == 1))
    sync_attrs(blob, d, margin=10)
    sync_skills(blob, d)
    safe(blob)
    E.put(c, blob)
    E.put_state(c, d)
    return blob, name, prof, race, gender, level


def table_bonuses(r):
    x = r.random()
    if x < 0.7:
        ab = 0
    elif x < 0.95:
        ab = r.choice([-60, -61, -100, 5, 10, -5, -1, 1])
    else:
        ab = r.choice([0x7fffffff, -0x80000000])
    return (ab, pick(r, [0, 3, -3], -2, 2, 0.2), pick(r, [0, 0, 1, 2, -1, -2, 5], 0, 0, 0.5))


def t_apply_tables(ctx, E):
    """void ApplyRaceProfessionTables(W8Character*, W8CharacterCreationState*)"""
    fn = ctx.fn(0x00556eb0)
    for i in range(ctx.n(400)):
        r = ctx.rng('applytables', i)
        c = ctx.case('applytables.%d' % i, fn, conv='c', ret='v')
        bon = table_bonuses(r)
        E.globals(c, bonuses=bon, locked=r.choice([0, 1]), game_started=r.choice([0, 1, 1]))
        blob, name, prof, race, gender, level = tables_setup(ctx, E, c, r)
        c.arg(E.C)
        c.arg(E.S)
        E.caps(c)
        c.note(char=name, prof=prof, race=race, gender=gender, level=level, attr_bonus=bon[0],
               spell_bonus=bon[2])
        if bon[0] in (0x7fffffff, -0x80000000):
            c.note(edge='bonus_overflow')


def t_set_race_gender(ctx, E):
    race_fn = ctx.fn(0x005571c0)    # void SetCharacterRace(W8Character*, State*, W8Race)
    gender_fn = ctx.fn(0x005571e0)  # void SetCharacterGender(W8Character*, State*, W8Gender)
    for i in range(ctx.n(120)):
        r = ctx.rng('setrace', i)
        c = ctx.case('setrace.%d' % i, race_fn, conv='c', ret='v')
        bon = table_bonuses(r)
        E.globals(c, bonuses=bon, game_started=1)
        blob, name, prof, race, gender, level = tables_setup(ctx, E, c, r)
        new = -1 if r.random() < 0.12 else r.randrange(11)
        c.arg(E.C)
        c.arg(E.S)
        c.arg(new)
        E.caps(c)
        c.note(char=name, prof=prof, old_race=race, race=new, gender=gender, level=level)
    for i in range(ctx.n(120)):
        r = ctx.rng('setgender', i)
        c = ctx.case('setgender.%d' % i, gender_fn, conv='c', ret='v')
        bon = table_bonuses(r)
        E.globals(c, bonuses=bon, game_started=1)
        blob, name, prof, race, gender, level = tables_setup(ctx, E, c, r)
        new = -1 if r.random() < 0.1 else r.choice([0, 1])
        c.arg(E.C)
        c.arg(E.S)
        c.arg(new)
        E.caps(c)
        c.note(char=name, prof=prof, race=race, old_gender=gender, gender=new, level=level)


def t_rebuild_pools(ctx, E):
    """void RebuildLevelUpPoolsForProfession(W8Character*, State*, W8Profession)"""
    fn = ctx.fn(0x00557060)
    for i in range(ctx.n(300)):
        r = ctx.rng('rebuildpools', i)
        c = ctx.case('rebuildpools.%d' % i, fn, conv='c', ret='v')
        locked = r.choice([0, 0, 1])
        bon = table_bonuses(r)
        E.globals(c, bonuses=bon, locked=locked, game_started=1)
        old = -1 if r.random() < 0.15 else None
        race = -1 if r.random() < 0.1 else None
        gender = r.choice([0, 0, 1, 1, -1]) if r.random() < 0.9 else r.choice([2, 0x100])
        level = 1 if r.random() < 0.4 else r.randint(2, 35)
        blob, name, prof, race, gender, level = tables_setup(ctx, E, c, r, race=race, prof=old,
                                                             gender=gender, level=level)
        new = P_VALKYRIE if r.random() < 0.25 else r.randrange(15)
        c.arg(E.C)
        c.arg(E.S)
        c.arg(new)
        E.caps(c)
        c.note(char=name, old_prof=prof, prof=new, race=race, gender=gender, level=level,
               locked=locked)
        if level > 1 and -1 in PROF_SKILLS[new]:
            c.note(edge='skill_minus_one')
        elif gender not in (-1, 0, 1):
            c.note(edge='gender_value')


# --------------------------------------------------------------------------------------
def t_paydown(ctx, E):
    """void PayDownAttributeDebt(W8Character*, W8CharacterCreationState*)"""
    fn = ctx.fn(0x00557200)
    for i in range(ctx.n(300)):
        r = ctx.rng('paydown', i)
        c = ctx.case('paydown.%d' % i, fn, conv='c', ret='v')
        E.globals(c)
        blob, name = E.char(c, r)
        prof, race, gender, level = identity(r, blob, level=r.randint(1, 40))
        defs = []
        ties = 0
        for a in range(7):
            mn = PROF_MIN[prof][a]
            x = r.random()
            if x < 0.4 or mn == 0:
                base = mn + r.randint(0, 40)
            elif x < 0.6 and any(0 < v <= mn for v in defs):
                dd = r.choice([v for v in defs if 0 < v <= mn])
                base = mn - dd          # same deficit as an earlier attribute
                ties += 1
            elif x < 0.95:
                base = mn - r.randint(1, min(mn, 20))
            elif x < 0.98:
                base = 0
            else:
                base = r.choice([0x80000000, 0xffffffff, 0x7fffffff])
            d = mn - base if base < mn else 0
            defs.append(d)
            set_attr(blob, a, base, base + r.choice([0, 0, 0, 5]))
        blob.u32(C_DEFICIT, r.choice([0, -sum(defs), -sum(defs), -r.randint(1, 50), r.randint(1, 9)]))
        blob.u32(C_BAND_BASE, r.getrandbits(32))
        if r.random() < 0.2:
            total = sum(defs) + r.choice([-1, 0, 0, 1])   # pool exactly (not) enough
        else:
            total = pick(r, [0, 1, 2, 3, 5, 6, 10, 20, 60, -1, -5, 0x7fffffff], 0, sum(defs) + 10, 0.4)
        d = gen_state(r, level1=False, a_total=total)
        d['a_rem'] = pick(r, [0, 1, 6, 60, -1, 0x7fffffff, -0x80000000], -5, 70, 0.3)
        E.put(c, blob)
        E.put_state(c, d)
        c.arg(E.C)
        c.arg(E.S)
        E.caps(c)
        c.note(char=name, prof=prof, deficits=defs, total=d['a_tot'], remaining=d['a_rem'],
               ties=ties)


def t_eligible(ctx, E):
    """void DetermineEligibleProfessions(W8Character*, State*, unsigned char* eligibility)"""
    fn = ctx.fn(0x00557350)
    for i in range(ctx.n(300)):
        r = ctx.rng('eligible', i)
        c = ctx.case('eligible.%d' % i, fn, conv='c', ret='v')
        E.globals(c)
        blob, name = E.char(c, r)
        prof, race, gender, level = identity(r, blob)
        x = r.random()
        edge = None
        if x < 0.05:
            prof = 0x10000 | r.randrange(15)
            edge = 'prof_hiword'
        elif x < 0.08:
            prof = r.choice([-1, 15, 0xffff])
        blob.u32(C_PROF, prof)
        x = r.random()
        if x < 0.92:
            gender = r.choice([0, 1])
        else:
            gender = r.choice([-1, 2, 0x101])
        blob.u32(C_GENDER, gender)
        # the profession the inputs are built around (for the high-word edge: the low word,
        # which retail treats as the character's own profession and so always eligible)
        target = prof & 0xffff if edge == 'prof_hiword' else r.randrange(15)
        for a in range(7):
            if r.random() < 0.6:
                base = max(0, PROF_MIN[target][a] + r.randint(-12, 12))
            else:
                base = r.randint(20, 100)
            set_attr(blob, a, base)
        vals = [r.randint(0, 15) for _ in range(7)]
        lims = [v + r.randint(0, 20) if r.random() < 0.85 else max(0, v - r.randint(1, 5))
                for v in vals]
        if r.random() < 0.25:
            # limit - value + base exactly at (or one below) the target profession's minimum
            a = r.choice([k for k in range(7) if PROF_MIN[target][k] > 0])
            vals[a] = r.randint(0, 10)
            lims[a] = vals[a] + r.randint(0, 20)
            set_attr(blob, a, max(0, PROF_MIN[target][a] - (lims[a] - vals[a]) + r.choice([-1, 0])))
        x = r.random()
        if edge == 'prof_hiword' and x < 0.7:
            total = prof_shortfall(blob, target) - 1     # not reachable by the deficit sweep
        elif x < 0.03:
            total = -0x80000000
            edge = edge or 'sum_overflow'
        elif x < 0.05:
            total = 0x7fffffff
        elif x < 0.25:
            total = prof_shortfall(blob, target) + r.choice([-1, 0])   # pool + deficit = -1 / 0
        else:
            total = pick(r, [0, 1, 5, 10, 20, 30, 60, -1, -10], -10, 60, 0.5)
        d = gen_state(r, level1=True, a_total=total)
        d['a_val'] = vals
        d['a_lim'] = lims
        E.put(c, blob)
        E.put_state(c, d)
        c.fill(E.E, 16, 0xaa)
        c.arg(E.C)
        c.arg(E.S)
        c.arg(E.E)
        c.cap(E.E, 16, 'eligibility')
        E.caps(c)
        c.note(char=name, prof=prof, gender=gender, target=target, total=total)
        if edge:
            c.note(edge=edge)


# --------------------------------------------------------------------------------------
def equipment_setup(ctx, E, c, r, level_max=20):
    """Character with a weapon-skill pattern for the profession switch; game_started 0/1."""
    started = 1 if r.random() < 0.5 else 0
    E.globals(c, game_started=started)
    if started:
        E.party(c, r)
    blob, name = E.char(c, r)
    x = r.random()
    if x < 0.4:
        prof = r.choice([P_FIGHTER, P_PRIEST, P_GADGETEER, P_BARD])
    else:
        prof = r.randrange(15)
    race = R_FAERIE if r.random() < 0.25 else r.randrange(11)
    level = 1 if r.random() < 0.7 else r.randint(2, level_max)
    prof, race, gender, level = identity(r, blob, prof=prof, race=race, level=level)
    for a_sk, b_sk in ((S_AXE, S_SWORD), (S_MACE, S_STAFF)):
        if r.random() < 0.8:
            av = pick(r, [0, 1, 100, 0x80000000], 0, 30, 0.1)
            bv = av if r.random() < 0.2 else pick(r, [0, 1, 100, 0x80000000], 0, 30, 0.1)
            blob.u32(skill_off(a_sk, SK_LEVEL), av)
            blob.u32(skill_off(b_sk, SK_LEVEL), bv)
    if r.random() < 0.3:
        blob.u32(skill_off(S_DUAL, SK_POINTS), r.choice([0, 1, 10]))
    safe(blob)
    E.put(c, blob)
    levels = tuple(blob.get_u32(skill_off(k, SK_LEVEL)) for k in (S_SWORD, S_AXE, S_MACE, S_STAFF))
    return blob, name, prof, race, gender, level, started, levels


def t_starting_equipment(ctx, E):
    add_fn = ctx.fn(0x00557430)     # void AddCharacterStartingEquipment(W8Character*)
    cost_fn = ctx.fn(0x00558640)    # int ComputeStartingEquipmentCost(W8Character*)
    afford_fn = ctx.fn(0x005586b0)  # bool CanAffordStartingEquipment(W8Character*)
    for i in range(ctx.n(200)):
        r = ctx.rng('startequip', i)
        c = ctx.case('startequip.%d' % i, add_fn, conv='c', ret='v')
        blob, name, prof, race, gender, level, started, pair = equipment_setup(ctx, E, c, r)
        c.arg(E.C)
        E.caps(c, state=False, party=bool(started))
        c.note(char=name, prof=prof, race=race, gender=gender, level=level, started=started,
               weapon_levels=pair)
    for i in range(ctx.n(150)):
        r = ctx.rng('equipcost', i)
        c = ctx.case('equipcost.%d' % i, cost_fn, conv='c', ret='i')
        blob, name, prof, race, gender, level, started, pair = equipment_setup(ctx, E, c, r)
        c.arg(E.C)
        E.caps(c, state=False, party=bool(started))
        c.note(char=name, prof=prof, race=race, gender=gender, level=level, started=started,
               weapon_levels=pair, expected_cost=expected_equipment_cost(prof, race, pair))
    for i in range(ctx.n(150)):
        r = ctx.rng('canafford', i)
        c = ctx.case('canafford.%d' % i, afford_fn, conv='c', ret='b')
        blob, name, prof, race, gender, level, started, pair = equipment_setup(ctx, E, c, r)
        cost = expected_equipment_cost(prof, race, pair)
        x = r.random()
        if x < 0.12:
            gold = r.choice([0, 1, 0xffffffff, 0x7fffffff, 0x80000000])
        elif x < 0.6:
            gold = cost + r.choice([-1, 0, 0, 1])     # the unsigned <= boundary
        else:
            gold = int(10 ** r.uniform(0, 4.3))
        c.set(E.gs + GS_PARTY_GOLD, u32(gold))
        c.arg(E.C)
        E.caps(c, state=False, party=bool(started))
        c.note(char=name, prof=prof, race=race, level=level, started=started, gold=gold,
               expected_cost=cost)


def t_finalize_created(ctx, E):
    """void FinalizeCreatedCharacter(W8Character*, State*, bool give_starting_equipment)"""
    fn = ctx.fn(0x00557580)
    for i in range(ctx.n(300)):
        r = ctx.rng('finalizecreated', i)
        c = ctx.case('finalizecreated.%d' % i, fn, conv='c', ret='v')
        started = 1 if r.random() < 0.5 else 0
        E.globals(c, game_started=started)
        if started:
            E.party(c, r)
        blob, name = E.char(c, r)
        prof = P_BISHOP if r.random() < 0.25 else None
        gender = -1 if r.random() < 0.03 else r.choice([0, 1])
        level = 1 if r.random() < 0.8 else r.randint(2, 20)
        prof, race, gender, level = identity(r, blob, prof=prof, gender=gender, level=level)
        realm(r, blob, 0.8)
        spells(r, blob, 0.25, 'creation')
        if r.random() < 0.3:
            blob.u32(C_LEARNED + 4 * 0x49, 2)
        if r.random() < 0.2:
            blob.u32(C_LEARNED + 4 * 0x4b, 2)
        blob.u32(C_GOAL, r.getrandbits(32) if r.random() < 0.2 else r.randint(0, 5000))
        d = gen_state(r, level1=(level == 1))
        d['sp_bonus'] = pick(r, [0xff, 0x100, -1, 0x7f, 0x80, 0x1ff], 0, 3, 0.15)
        safe(blob)
        E.put(c, blob)
        E.put_state(c, d)
        x = r.random()
        give = 0 if x < 0.5 else (1 if x < 0.9 else r.choice([2, 0xff, 0x100, 0xffffff00]))
        if gender == -1:
            give = 0     # CanCharacterUseItem would shift the gender mask by -1
        c.arg(E.C)
        c.arg(E.S)
        c.arg(give)
        E.caps(c, party=bool(started))
        n2 = sum(1 for k in range(NSP) if blob.get_i32(C_LEARNED + 4 * k) == 2)
        c.note(char=name, prof=prof, race=race, gender=gender, level=level, started=started,
               give=give, magic_bonus=d['sp_bonus'], picked=n2,
               costs=list(blob[C_COSTS:C_COSTS + 4]), pool=blob[C_POOL])
        if give not in (0, 1):
            c.note(edge='bool_arg')


# --------------------------------------------------------------------------------------
def attr_setup(ctx, E, c, r, level=None):
    blob, name = E.char(c, r)
    prof, race, gender, level = identity(r, blob, level=level)
    return blob, name, prof, race, gender, level


def t_recompute_attr_limits(ctx, E):
    """void RecomputeAttributeLimits(W8Character*, W8CharacterCreationState*)"""
    fn = ctx.fn(0x00557730)
    for i in range(ctx.n(300)):
        r = ctx.rng('attrlimits', i)
        c = ctx.case('attrlimits.%d' % i, fn, conv='c', ret='v')
        E.globals(c)
        blob, name, prof, race, gender, level = attr_setup(ctx, E, c, r)
        total = pick(r, [-1, -100, -0x80000000, 0, 1, 2, 3, 4, 5, 6, 7, 8, 6, 60, 61],
                     -10, 70, 0.45)
        d = gen_state(r, level1=(level == 1), a_total=total)
        if r.random() < 0.3:
            d['a_base'] = [r.choice([0, 0, 1, 2, 3, r.randint(0, 10)]) for _ in range(7)]
        d['a_val'] = [min(max(v, -50), 200) for v in d['a_val']]
        for a in range(7):
            x = r.random()
            if x < 0.15:
                set_attr(blob, a, max(d['a_val'][a], 0) + r.choice([100, 101, 99, 125, 150]))
            elif x < 0.18:
                set_attr(blob, a, r.choice([0, 1, 0x80000000, 0xffffffff]))
            elif x < 0.5:
                set_attr(blob, a, r.randint(20, 100))
        E.put(c, blob)
        E.put_state(c, d)
        c.arg(E.C)
        c.arg(E.S)
        E.caps(c)
        c.note(char=name, total=total, baselines=d['a_base'], values=d['a_val'])


def t_clamp_attrs(ctx, E):
    """void ClampAttributesToBudget(W8Character*, W8CharacterCreationState*)"""
    fn = ctx.fn(0x00557800)
    for i in range(ctx.n(250)):
        r = ctx.rng('clampattrs', i)
        c = ctx.case('clampattrs.%d' % i, fn, conv='c', ret='v')
        E.globals(c)
        blob, name, prof, race, gender, level = attr_setup(ctx, E, c, r)
        d = gen_state(r, a_total=pick(r, [0, 1, 5, 10, 30, 60, -1, -10], -5, 70, 0.4))
        d['a_val'] = [r.choice([0, 0, r.randint(0, 40), r.randint(-5, 40)]) for _ in range(7)]
        d['a_lim'] = [r.choice([v, v, v + r.randint(0, 10), max(0, v - r.randint(1, 10)),
                                r.randint(-5, 40)]) for v in d['a_val']]
        edge = None
        if i < 6:
            # value - limit overflows: retail (sub + jle) clamps, a "value > limit" does not
            k = r.randrange(7)
            d['a_val'][k] = -0x7ffffff0 + r.randint(0, 0x0f)
            d['a_lim'][k] = r.choice([0x20, 0x40, 0x100])
            d['a_tot'] = r.choice([5, 10, 60])
            edge = 'sub_overflow'
        d['a_rem'] = r.getrandbits(32)
        E.put(c, blob)
        E.put_state(c, d)
        c.arg(E.C)
        c.arg(E.S)
        E.caps(c)
        c.note(char=name, total=d['a_tot'], values=d['a_val'], limits=d['a_lim'])
        if edge:
            c.note(edge=edge)


def t_apply_prof_min(ctx, E):
    """void ApplyProfessionMinimumAttributes(W8Character*, W8CharacterCreationState*)"""
    fn = ctx.fn(0x00557890)
    for i in range(ctx.n(300)):
        r = ctx.rng('applyprofmin', i)
        c = ctx.case('applyprofmin.%d' % i, fn, conv='c', ret='v')
        E.globals(c)
        x = r.random()
        level = 1 if x < 0.45 else (r.choice([0, 0xffffffff]) if x < 0.5 else r.randint(2, 30))
        blob, name, prof, race, gender, level = attr_setup(ctx, E, c, r, level=level)
        for a in range(7):
            mn = PROF_MIN[prof][a]
            x = r.random()
            if x < 0.45:
                base = max(0, mn + r.randint(-20, 20))
            elif x < 0.55:
                base = mn
            elif x < 0.58:
                base = r.choice([0x80000000, 0xffffffff, 0])
            else:
                continue
            set_attr(blob, a, base, base + r.choice([0, 0, 3]))
        blob.u32(C_DEFICIT, r.getrandbits(32))
        blob.u32(C_BAND_BASE, r.choice([0, 7, r.getrandbits(32)]))
        if r.random() < 0.2:
            total = prof_shortfall(blob, prof) + r.choice([-1, 0])   # pay-down boundary
        else:
            total = pick(r, [60, 6, 0, 1, -1, -20, 3], -30, 70, 0.4)
        d = gen_state(r, level1=(level == 1), a_total=total)
        d['a_val'] = [r.choice([0, 0, r.randint(0, 15)]) for _ in range(7)]
        E.put(c, blob)
        E.put_state(c, d)
        c.arg(E.C)
        c.arg(E.S)
        E.caps(c)
        c.note(char=name, prof=prof, level=level, total=d['a_tot'], values=d['a_val'])


def t_adjust_attr(ctx, E):
    """void AdjustAllocatedAttribute(W8Character*, State*, W8Attribute, int modifier)"""
    fn = ctx.fn(0x005579e0)
    for i in range(ctx.n(350)):
        r = ctx.rng('adjustattr', i)
        c = ctx.case('adjustattr.%d' % i, fn, conv='c', ret='v')
        E.globals(c)
        blob, name, prof, race, gender, level = attr_setup(
            ctx, E, c, r, level=1 if r.random() < 0.5 else None)
        realm(r, blob, 0.3)
        spells(r, blob, 0.2, 'creation')
        d = gen_state(r, level1=(level == 1))
        if d['a_rem'] < -5:
            d['a_rem'] = -r.randint(0, 5)
        attr = r.randrange(7)
        v = d['a_val'][attr]
        x = r.random()
        edge = None
        if x < 0.05:
            if v < 1:
                v = d['a_val'][attr] = r.randint(1, 15)
                d['a_lim'][attr] = max(d['a_lim'][attr], v)
            mod = 0x7fffffff       # value + modifier wraps negative: assert line 0x380
            edge = 'assert_wrap'
        elif x < 0.12:
            mod = r.choice([-0x80000000, 0x7fffffff, 100, -100, 1, -1])
        elif x < 0.17:
            mod = 0
        elif x < 0.24:
            mod = d['a_rem'] + r.choice([-1, 0, 0, 1])          # remaining-pool clamp boundary
        elif x < 0.31:
            mod = d['a_lim'][attr] - v + r.choice([-1, 0, 0, 1])  # limit clamp boundary
        elif x < 0.65:
            mod = r.randint(1, 20)
        else:
            mod = -r.randint(1, max(1, v + 5))
        sync_attrs(blob, d)
        sync_skills(blob, d)
        safe(blob)
        E.put(c, blob)
        E.put_state(c, d)
        c.arg(E.C)
        c.arg(E.S)
        c.arg(attr)
        c.arg(mod)
        E.caps(c)
        c.note(char=name, prof=prof, level=level, attr=attr, modifier=s32(mod), value=v,
               limit=d['a_lim'][attr], remaining=d['a_rem'], spell_total=d['sp_tot'])
        if edge:
            c.note(edge=edge)


def t_refund_attrs(ctx, E):
    """void RefundAllocatedAttributes(W8Character*, W8CharacterCreationState*)"""
    fn = ctx.fn(0x00557ae0)
    for i in range(ctx.n(200)):
        r = ctx.rng('refundattrs', i)
        c = ctx.case('refundattrs.%d' % i, fn, conv='c', ret='v')
        E.globals(c)
        blob, name, prof, race, gender, level = attr_setup(
            ctx, E, c, r, level=1 if r.random() < 0.5 else None)
        realm(r, blob, 0.3)
        spells(r, blob, 0.2, 'creation')
        d = gen_state(r, level1=(level == 1))
        if r.random() < 0.7:
            d['a_val'] = [r.choice([0, 0, r.randint(1, 15)]) for _ in range(7)]
        d['a_lim'] = [max(v, 0) + r.choice([0, 0, 2, r.randint(0, 10)]) if r.random() < 0.92
                      else r.choice([-1, -5]) for v in d['a_val']]
        if d['a_rem'] < 0 and r.random() < 0.8:
            d['a_rem'] = r.randint(0, 10)
        sync_attrs(blob, d)
        sync_skills(blob, d)
        safe(blob)
        E.put(c, blob)
        E.put_state(c, d)
        c.arg(E.C)
        c.arg(E.S)
        E.caps(c)
        c.note(char=name, prof=prof, level=level, values=d['a_val'], limits=d['a_lim'],
               remaining=d['a_rem'])


# --------------------------------------------------------------------------------------
def skill_setup(ctx, E, c, r, level=None):
    blob, name = E.char(c, r)
    prof, race, gender, level = identity(r, blob, level=level)
    skills(r, blob, 0.25)
    return blob, name, prof, race, gender, level


def t_recompute_skill_limits(ctx, E):
    """void RecomputeSkillLimits(W8Character*, State*) (+ inlined ClampSkillsToBudget)"""
    fn = ctx.fn(0x00557b20)
    for i in range(ctx.n(300)):
        r = ctx.rng('skilllimits', i)
        c = ctx.case('skilllimits.%d' % i, fn, conv='c', ret='v')
        E.globals(c)
        blob, name, prof, race, gender, level = skill_setup(ctx, E, c, r)
        total = pick(r, [15, 9, 0, 1, 2, 3, 4, -1, -2, -3, -4, -5, 30, 60, 0x7ffffffd], -6, 45, 0.5)
        d = gen_state(r, s_total=total)
        d['s_spent'] = [0] * NSK
        for k in r.sample(range(NSK), r.choice([0, 1, 2, 4, 6, 10])):
            d['s_spent'][k] = r.choice([r.randint(1, 15), r.randint(1, 15), -r.randint(1, 3)])
        sync_skills(blob, d, margin=r.choice([0, 0, 2, 10]))
        if r.random() < 0.25:
            # spent - points + 0x4b exactly at step - 1 / step / step + 1 for one active skill
            k = r.randrange(NSK)
            step = c_div(s32(d['s_tot']) + 2, 3)
            pts = d['s_spent'][k] + 0x4b - step - r.choice([-1, 0, 1])
            blob.u8(skill_off(k, SK_ACTIVE), 1)
            blob.u32(skill_off(k, SK_POINTS), pts)
            blob.u32(skill_off(k, SK_LEVEL), pts + r.choice([0, 1]))
        edge = None
        if i < 6:
            # spent - limit overflows: retail clamps the spent points down to the limit
            k = r.randrange(NSK)
            blob.u8(skill_off(k, SK_ACTIVE), 1)
            blob.u32(skill_off(k, SK_POINTS), 0x80000000)
            blob.u32(skill_off(k, SK_LEVEL), 0x80000005)
            d['s_spent'] = [0] * NSK
            d['s_spent'][k] = 0x80000010
            d['s_tot'] = 60
            edge = 'sub_overflow'
        d['s_rem'] = r.getrandbits(32)
        E.put(c, blob)
        E.put_state(c, d)
        c.arg(E.C)
        c.arg(E.S)
        E.caps(c)
        c.note(char=name, total=d['s_tot'],
               spent={k: v for k, v in enumerate(d['s_spent']) if v})
        if edge:
            c.note(edge=edge)


def t_skill_commit(ctx, E):
    """void InitializeLevelUpAttributePool(W8Character*, State*, unsigned skill, int modifier)
    (the per-skill point commit)"""
    fn = ctx.fn(0x00557bc0)
    for i in range(ctx.n(300)):
        r = ctx.rng('skillcommit', i)
        c = ctx.case('skillcommit.%d' % i, fn, conv='c', ret='v')
        E.globals(c)
        blob, name, prof, race, gender, level = skill_setup(ctx, E, c, r)
        realm(r, blob, 0.3)
        spells(r, blob, 0.25, 'creation')
        d = gen_state(r, level1=(level == 1))
        if d['s_rem'] < -5:
            d['s_rem'] = -r.randint(0, 5)
        skill = r.choice(list(REALM_BOOKS) + list(REALM_MAGIC)) if r.random() < 0.3 \
            else r.randrange(NSK)
        v = d['s_spent'][skill]
        x = r.random()
        edge = None
        if x < 0.05:
            if v < 1:
                v = d['s_spent'][skill] = r.randint(1, 10)
                d['s_lim'][skill] = max(d['s_lim'][skill], v)
            mod = 0x7fffffff       # spent + modifier wraps negative: assert line 0x448
            edge = 'assert_wrap'
        elif x < 0.12:
            mod = r.choice([-0x80000000, 0x7fffffff, 100, -100, 1, -1])
        elif x < 0.17:
            mod = 0
        elif x < 0.24:
            mod = d['s_rem'] + r.choice([-1, 0, 0, 1])
        elif x < 0.31:
            mod = d['s_lim'][skill] - v + r.choice([-1, 0, 0, 1])
        elif x < 0.65:
            mod = r.randint(1, 15)
        else:
            mod = -r.randint(1, max(1, v + 4))
        sync_skills(blob, d, margin=10)
        safe(blob)
        E.put(c, blob)
        E.put_state(c, d)
        c.arg(E.C)
        c.arg(E.S)
        c.arg(skill)
        c.arg(mod)
        E.caps(c)
        c.note(char=name, prof=prof, skill=skill, modifier=s32(mod), spent=v,
               limit=d['s_lim'][skill], remaining=d['s_rem'], spell_total=d['sp_tot'])
        if edge:
            c.note(edge=edge)


def t_reset_skill(ctx, E):
    """void ResetSkillContribution(W8Character*, State*, W8Skill)"""
    fn = ctx.fn(0x00557c90)
    for i in range(ctx.n(250)):
        r = ctx.rng('resetskill', i)
        c = ctx.case('resetskill.%d' % i, fn, conv='c', ret='v')
        E.globals(c)
        prof = r.randint(1, 6) if r.random() < 0.6 else r.choice([0, 7, 8, 9, 10, 11, 12, 13, 14])
        blob, name = E.char(c, r)
        prof, race, gender, level = identity(r, blob, prof=prof)
        if 1 <= prof <= 6:
            plev = 5 if r.random() < 0.55 else r.choice([4, 6, 0, 1, 10])
        else:
            plev = r.choice([1, 5, r.randint(0, 20)])
        blob.u32(C_PLEV + 4 * prof, plev)
        x = r.random()
        edge = None
        if x < 0.5:
            skill = r.choice(list(REALM_BOOKS))
        elif x < 0.97:
            skill = r.randrange(NSK)
        else:
            skill = r.choice([-1, NSK])
            edge = 'skill_oob'
        if 0 <= skill < NSK:
            pts = pick(r, [0xfffffffe, 0x80000000, 0x7fffffff], 0, 10, 0.08)
            blob.u32(skill_off(skill, SK_POINTS), pts)
            blob.u32(skill_off(skill, SK_LEVEL), pts + r.choice([0, 0, 2]))
            blob.u8(skill_off(skill, 1), r.choice([0, 0, 1]))
        d = gen_state(r, level1=r.random() < 0.5)
        if 0 <= skill < NSK and r.random() < 0.5:
            d['s_spent'][skill] = r.randint(-2, 10)
            d['s_base'][skill] = r.randint(-2, 6)
        E.put(c, blob)
        E.put_state(c, d)
        c.arg(E.C)
        c.arg(E.S)
        c.arg(skill)
        E.caps(c)
        c.note(char=name, prof=prof, prof_level=plev, skill=skill)
        if edge:
            c.note(edge=edge)


def t_refund_skill(ctx, E):
    """void RefundSkillAllocation(W8Character*, State*, W8Skill)"""
    fn = ctx.fn(0x00557d20)
    for i in range(ctx.n(200)):
        r = ctx.rng('refundskill', i)
        c = ctx.case('refundskill.%d' % i, fn, conv='c', ret='v')
        E.globals(c)
        blob, name, prof, race, gender, level = skill_setup(ctx, E, c, r)
        d = gen_state(r)
        skill = r.randrange(NSK)
        spent = pick(r, [0, 1, -1, 0x7fffffff, -0x80000000], -5, 15, 0.15)
        d['s_spent'][skill] = spent
        d['s_rem'] = pick(r, [0, -1, 0x7fffffff], -5, 30, 0.15)
        pts = pick(r, [0, 1, 0xffffffff, 0x80000000], 0, 60, 0.1)
        blob.u32(skill_off(skill, SK_POINTS), pts)
        blob.u32(skill_off(skill, SK_LEVEL), r.getrandbits(32) if r.random() < 0.3 else pts + 3)
        E.put(c, blob)
        E.put_state(c, d)
        c.arg(E.C)
        c.arg(E.S)
        c.arg(skill)
        E.caps(c)
        c.note(char=name, skill=skill, spent=spent, points=pts, remaining=d['s_rem'])


def t_rebuild_skills(ctx, E):
    """void RebuildSkillAllocations(W8Character*, W8CharacterCreationState*)"""
    fn = ctx.fn(0x00557d80)
    for i in range(ctx.n(300)):
        r = ctx.rng('rebuildskills', i)
        c = ctx.case('rebuildskills.%d' % i, fn, conv='c', ret='v')
        E.globals(c)
        blob, name = E.char(c, r)
        prof, race, gender, level = identity(r, blob, prof=i % 15 if i < 60 else None)
        skills(r, blob, 0.2)
        for a in range(7):
            if r.random() < 0.3:
                set_attr(blob, a, pick(r, [0, 1, 125, 255, 0xffffffff], 20, 100, 0.08))
        total = pick(r, [60, 6, 0, -1, -10, -30, -54, -60, -100, -0x80000000, 0x7fffffff, -0x2000000],
                     -60, 70, 0.5)
        d = gen_state(r, a_total=total)
        E.put(c, blob)
        E.put_state(c, d)
        c.arg(E.C)
        c.arg(E.S)
        E.caps(c)
        c.note(char=name, prof=prof, total=total,
               spent={k: v for k, v in enumerate(d['s_spent']) if v})


def t_refund_all_skills(ctx, E):
    """void RefundAllSkillPoints(W8Character*, W8CharacterCreationState*)"""
    fn = ctx.fn(0x00557f90)
    for i in range(ctx.n(200)):
        r = ctx.rng('refundallskills', i)
        c = ctx.case('refundallskills.%d' % i, fn, conv='c', ret='v')
        E.globals(c)
        blob, name, prof, race, gender, level = skill_setup(ctx, E, c, r)
        realm(r, blob, 0.3)
        spells(r, blob, 0.2, 'creation')
        d = gen_state(r, level1=(level == 1))
        d['s_spent'] = [0] * NSK
        for k in r.sample(range(NSK), r.choice([0, 1, 2, 3, 5, 8])):
            d['s_spent'][k] = r.randint(1, 12) if r.random() < 0.92 else -r.randint(1, 3)
        d['s_lim'] = [max(v, 0) + r.choice([0, 0, 3, r.randint(0, 15)]) if r.random() < 0.95
                      else -1 for v in d['s_spent']]
        if d['s_rem'] < 0 and r.random() < 0.8:
            d['s_rem'] = r.randint(0, 10)
        sync_skills(blob, d, margin=r.choice([0, 5]))
        safe(blob)
        E.put(c, blob)
        E.put_state(c, d)
        c.arg(E.C)
        c.arg(E.S)
        E.caps(c)
        c.note(char=name, prof=prof, spent={k: v for k, v in enumerate(d['s_spent']) if v},
               remaining=d['s_rem'], spell_total=d['sp_tot'])


# --------------------------------------------------------------------------------------
def t_realm_debt(ctx, E):
    """int ComputeRealmSkillDebt(W8Character* original, W8Character* edited)"""
    fn = ctx.fn(0x00557fd0)
    for i in range(ctx.n(250)):
        r = ctx.rng('realmdebt', i)
        c = ctx.case('realmdebt.%d' % i, fn, conv='c', ret='i')
        E.globals(c)
        blob, name = E.char(c, r)
        # the edited copy starts from the same corpus character (same blob, deduplicated)
        edited = Blob(bytes(blob))
        c.setb(E.C2, bytes(edited))
        prof, race, gender, level = identity(r, blob)
        realm(r, blob, 0.9)
        zero_o = caster_level_craft(r, blob, prof, 0.25)
        edited[:] = blob
        prof_e = prof if r.random() < 0.4 else r.randrange(15)
        if prof_e != prof:
            edited.u32(C_PROF, prof_e)
            edited.u32(C_PLEV + 4 * prof_e, r.choice([1, 4, 5, level & 0xffff, 0]))
        zero_e = caster_level_craft(r, edited, prof_e, 0.3)
        for k in REALM_BOOKS:
            if r.random() < 0.4:
                edited.u8(skill_off(k), r.choice([0, 1]))
        if r.random() < 0.3:
            for k in range(4):
                edited.u8(C_COSTS + k, r.randint(0, 9))
        E.put(c, blob)
        E.put(c, edited, at=E.C2)
        c.arg(E.C)
        c.arg(E.C2)
        c.cap(E.C, CHAR, 'original')
        c.cap(E.C2, CHAR, 'edited')
        c.note(char=name, prof=prof, prof_edited=prof_e, caster0_original=zero_o,
               caster0_edited=zero_e, costs=list(blob[C_COSTS:C_COSTS + 4]), pool=blob[C_POOL],
               costs_edited=list(edited[C_COSTS:C_COSTS + 4]))


def t_finalize_spell_pool(ctx, E):
    """void FinalizeSpellPointPool(W8Character*, W8CharacterCreationState*)"""
    fn = ctx.fn(0x00558070)
    for i in range(ctx.n(300)):
        r = ctx.rng('finalizesp', i)
        c = ctx.case('finalizesp.%d' % i, fn, conv='c', ret='v')
        sp_bonus = pick(r, [0, 0, 0, 1, 2, -1, -2, 5, 0x7fffffff], 0, 0, 0.5)
        E.globals(c, bonuses=(0, 0, sp_bonus))
        blob, name = E.char(c, r)
        x = r.random()
        level = 1 if x < 0.5 else (0 if x < 0.53 else r.randint(2, 30))
        prof, race, gender, level = identity(r, blob, level=level)
        zero = caster_level_craft(r, blob, prof, 0.25)
        realm(r, blob, 0.8)
        spells(r, blob, 0.3, 'creation')
        n2 = sum(1 for k in range(NSP) if blob.get_i32(C_LEARNED + 4 * k) == 2)
        d = gen_state(r, level1=(level == 1), sp_total=pick(r, [0, 1, 2, -1, 20], 0, 8, 0.3))
        spent = pick(r, [0, n2, n2 + 1, n2 + 5, -1, -3], 0, n2 + 2, 0.5)
        d['sp_rem'] = d['sp_tot'] - spent
        E.put(c, blob)
        E.put_state(c, d)
        c.arg(E.C)
        c.arg(E.S)
        E.caps(c)
        c.note(char=name, prof=prof, level=level, caster0=zero, spell_bonus=sp_bonus,
               total=d['sp_tot'], spent=spent, picked=n2)


def t_count_remaining(ctx, E):
    """int CountRemainingSpellPoints(W8Character*, W8CharacterCreationState*)"""
    fn = ctx.fn(0x00558180)
    for i in range(ctx.n(300)):
        r = ctx.rng('countremaining', i)
        c = ctx.case('countremaining.%d' % i, fn, conv='c', ret='i')
        E.globals(c)
        blob, name, prof, race, gender, level = skill_setup(ctx, E, c, r)
        realm(r, blob, 0.5)
        spells(r, blob, 0.4, 'mix', edge_p=0.02)
        total = r.choice([0, -1, -5]) if r.random() < 0.3 else pick(r, [1, 2, 20, 0x7fffffff], 1, 8, 0.2)
        d = gen_state(r, sp_total=total)
        d['sp_rem'] = pick(r, [0, -1, total + 1, total + 4], 0, max(total, 0), 0.25)
        for k in list(REALM_BOOKS) + list(REALM_MAGIC):
            if r.random() < 0.3:
                d['s_spent'][k] = r.randint(0, 10) if r.random() < 0.95 else -r.randint(1, 3)
        sync_skills(blob, d)
        E.put(c, blob)
        E.put_state(c, d)
        c.arg(E.C)
        c.arg(E.S)
        E.caps(c)
        c.note(char=name, prof=prof, total=total, remaining=d['sp_rem'])


def t_levelup_award(ctx, E):
    """int ComputeLevelUpSpellPointAward(W8Character*, W8CharacterCreationState*)"""
    fn = ctx.fn(0x00558330)
    for i in range(ctx.n(300)):
        r = ctx.rng('levelupaward', i)
        c = ctx.case('levelupaward.%d' % i, fn, conv='c', ret='i')
        E.globals(c)
        x = r.random()
        level = 1 if x < 0.55 else (0 if x < 0.6 else r.randint(2, 40))
        blob, name, prof, race, gender, level = skill_setup(ctx, E, c, r, level=level)
        realm(r, blob, 0.5)
        spells(r, blob, 0.35, 'creation' if level <= 1 else 'mix')
        if level > 1 and r.random() < 0.4:
            for k in range(6):
                blob.u32(C_SPMAX + 4 * k, pick(r, [0, -1, 0x7fffffff, -0x80000000], 0, 60, 0.15))
        total = pick(r, [0, -1, 1, 6, 7, 8, 30], 1, 8, 0.4)
        d = gen_state(r, sp_total=total)
        d['sp_rem'] = pick(r, [0, -1, 1, total], 0, max(total, 0), 0.3)
        E.put(c, blob)
        E.put_state(c, d)
        c.arg(E.C)
        c.arg(E.S)
        E.caps(c)
        c.note(char=name, prof=prof, level=level, total=total, remaining=d['sp_rem'])


def t_select_spells(ctx, E):
    sel_fn = ctx.fn(0x005584e0)    # void SelectCreationSpell(W8Character*, State*, unsigned)
    desel_fn = ctx.fn(0x00558560)  # void DeselectCreationSpell(W8Character*, State*, unsigned)
    for which, fn, count in (('select', sel_fn, 250), ('deselect', desel_fn, 250)):
        for i in range(ctx.n(count)):
            r = ctx.rng(which, i)
            c = ctx.case('%sspell.%d' % (which, i), fn, conv='c', ret='v')
            E.globals(c)
            blob, name, prof, race, gender, level = skill_setup(ctx, E, c, r)
            spells(r, blob, 0.3, 'creation')
            x = r.random()
            if x < 0.2:
                spell = 0x49
            elif x < 0.4:
                spell = 0x4b
            elif x < 0.95:
                spell = r.randrange(NSP)
            else:
                spell = r.choice([0, 0x72, 0x87])
            states = {}
            for k in (spell, 0x49, 0x4b):
                if r.random() < 0.8:
                    states[k] = r.choice([0, 1, 2, -1]) if r.random() < 0.97 else 3
                    blob.u32(C_LEARNED + 4 * k, states[k])
            d = gen_state(r)
            d['sp_rem'] = pick(r, [0, 1, 2, 5, -1, -5, 0x7fffffff], 0, 4, 0.4)
            E.put(c, blob)
            E.put_state(c, d)
            c.arg(E.C)
            c.arg(E.S)
            c.arg(spell)
            E.caps(c)
            c.note(char=name, spell=spell, states=states, remaining=d['sp_rem'])


def t_reset_spells(ctx, E):
    """void ResetSpellSelections(W8Character*, W8CharacterCreationState*)"""
    fn = ctx.fn(0x005585d0)
    for i in range(ctx.n(150)):
        r = ctx.rng('resetspells', i)
        c = ctx.case('resetspells.%d' % i, fn, conv='c', ret='v')
        E.globals(c)
        blob, name = E.char(c, r)
        spells(r, blob, r.choice([0.1, 0.3, 0.6]), 'mix', edge_p=0.03)
        if r.random() < 0.3:      # entries 0x72.. are outside the scan
            for k in range(NSP, NSP + 4):
                blob.u32(C_LEARNED + 4 * k, 2)
        d = gen_state(r, sp_total=pick(r, [0, -1, 0x7fffffff], 0, 8, 0.2))
        E.put(c, blob)
        E.put_state(c, d)
        c.arg(E.C)
        c.arg(E.S)
        E.caps(c)
        c.note(char=name, total=d['sp_tot'], remaining=d['sp_rem'])
