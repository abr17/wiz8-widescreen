"""Targeting.cpp, lines 1-1700 (decomp/src/wiz8/local_code/Targeting.cpp).

Tested (retail address, name, cases at --scale 1):
  0x0053be00 SetTargetSourceToCharacter          60  garbage-filled source block, slot edges
  0x0053be50 SetTargetSourceToMonster            60
  0x0053bea0 TargetSourceIsCharacter            200  kinds 0..4/-1/0x101, iChar -1, flags 0/1/2/0xff,
                                                     allow_indirect 1/0/2/-1/0x101 (asserts 0xce3/0xceb)
  0x0053bf10 TargetSourceIsMonster              200  (asserts 0xcf8/0xd00)
  0x0053c320 GetSourceNoticeColor               150
  0x0053c3f0 GetTargetNoticeColor               200  XChar party_order_index (only the low byte is returned)
  0x0053C490 ShouldClearAimForAppliedTarget     300  scratch monster/group lists, turncoat conditions,
                                                     in_combat/action bytes with high garbage, assert 0xdf9/0xe11
  0x005360b0 FindFactionByName                  150  case variants, near misses, empty/30-byte strings
  0x005360f0 GetFactionValue                     60  signed char argument with garbage in the high bytes
  0x00536110 SetFactionFlag                      60
  0x00536130 GetFactionFlag                      60
  0x00536150 ResetTargetSource                   30
  0x00536170 ResetCombatSlot                     30
  0x005369f0 ClearMonsterCombatSlot              40
  0x0053A2C0 SetMonsterCombatTarget              60
  0x00537160 TargetMatchesNeeded                400  every need (-1..9, 100, 0x80000000) x target kind, presence
                                                     world (party fields, scratch monsters/groups, items)
  0x00536190 IsTargetStillPresent               400  unsigned edges of hp/conditions (0x80000000, 0xffffffff),
                                                     non-canonical bool bytes, absent/-1 monster and group ids
  0x00536a20 GetTargetNeededForAction           300  actions -1..11/edges, all 150 spells, items (Items.dbs)
  0x00537330 GetTargetNeededForItem             250  null item, iItemNo -1, spell items, g_level_block null/set
  0x005372b0 IsItemTargetOfNeededKind           300  full CURRENT-context state, all five row target blocks +
                                                     the shared one, autotarget_spells
  0x00537270 IsSpellTargetOfNeededKind          300
  0x00537220 IsSpellTargetStillValidIn          250  explicit contexts 0..9/-1 (invalid ones assert in
                                                     GetTargetBlockForContext: retail line 0xc2f)
  0x00537380 GetTargetNeededForCurrentAction    300  every context incl. shared spell (gpSCSV) / shared item
                                                     (use-item globals) and dialogue selections
  0x0053bc10 GetCurrentTargetingContext         250
  0x0053b920 ResolveTargetingContext            250
  0x0053b7f0 GetTargetBlockForContext           250  XChar redirected into scratch: the returned pointer is
                                                     compared as scratch offset; shared block by contents
  0x0053A300 MonsterTargetMatchesSpell          300  all spells (types 9/10 assert 0x1319 in the hostile need)
  0x0053A3D0 GetTargetingCursorForState         150
  0x0053A700 ActionNeedsExplicitTarget          250
  0x0053A8D0 GetActionSpellLikeId               250  explicit contexts 0..8 (+ invalid), shared/dialogue paths
  0x0053c920 CompareMonsterTargetCandidates     300  state compared unsigned in retail (0x80000000/0xffffffff),
                                                     reach bytes, float distance incl. NaN (retail: NaN = less)
  0x00538620 AimByKind                           60  context OUT_OF_COMBAT only (pure block copy)
  0x00538670 AimAtCharacter                      60  "
  0x005386C0 AimAtCharacterIndirect              60  "
  0x00538E00 ApplyTarget                        250  character/group/other kinds (not monster): party rows whose
                                                     out-of-combat (and, outside combat mode, in-combat) target
                                                     matches, scratch monsters aiming at it; repick through
                                                     RepickActionTarget(slot, 0) stays a pure block write
  0x00538d10 SetTargetToCharacter               150  "
  0x00538db0 SetTargetToGroup                   150  "
  0x0053c630 ResolveTargetPoint                 200  monster kind (both modes) on scratch W8Monster objects, party/
                                                     character kind only with the sight probe (g_startup_world ->
                                                     scratch navigator), other kinds
  0x00539e70 CollectMonstersWithinRadius        220  scratch monsters/records/reps, highlighting always on (no
                                                     line-of-sight traces), exact integer distances on both sides
                                                     of the radius, radius 0/-0/NaN, side selector bytes
  0x00539480 TintHighlightedMonster              40  tints 0..2 on a scratch monster rep (dying cycle 0x15)
  0x00537780 IsTargetSourceInRangeOfGroup       200  monster source: range from its action (record attack 0 with
                                                     range bytes 0..3/0xff/4 -> CalcRangeDistance assert 1123,
                                                     spell table, special, protect), members on scratch W8Monster
                                                     objects at integer distances around the range (alternate
                                                     radii, overlap clamp to 0); character source with an empty
                                                     group only (members would be measured to the camera)
  Total: 7550 cases.

Skipped (one line each):
  0x00537950 AimAtMonsterLocation          CanTargetMonster (sight/geometry) + AimAtTarget in the CURRENT context
                                           (highlights, redraw requests, targeting mode) + StartBreathCycle voice
  0x00538710 AimAtPlace                    world cursor position, target marker
  0x00538770 AimAtGroundTarget             camera forward point, StartBreathCycle
  0x00538d60 SetTargetToMonster            NotifyMonsterHighlight -> world target-marker objects per party slot
  0x00539870 ShowMonsterTargetMarker       camera position + on-screen marker (UI)
  0x00536400 RepickInvalidCombatTargets    in-combat repick: CharacterCanSwitchTo, AimAtTarget UI path, monster
                                           choice by live distances
  0x00539630 SetMonsterHighlight           NotifyMonsterHighlight -> world target-marker objects
  0x005396d0 PickNearestMonsterUnderCursor model-instance hover test and camera distances (render state)
  0x00538c00 SetGroupHighlight             SetMonsterHighlight per member (marker objects)
  0x00539570 UpdateAllMonsterHighlights    HighlightMonsterAsTarget -> CharacterCanSwitchTo/CanTargetMonster,
                                           cursor changes
  0x0053c720 ChooseMonsterTarget           candidates need CanPartyMemberAimAtMonster (sight, band distances to the
                                           live party), quadrant/formation; its ordering is tested directly through
                                           CompareMonsterTargetCandidates
  0x00539110 HighlightMonsterAsTarget      cursor changes (SetTargetCursor/UpdateHeldItemCursor) and the
                                           CharacterCanSwitchTo/CanTargetMonster validity test
  0x0053ac30 ClearTargetHighlights         SetMonsterHighlight/SetGroupHighlight (marker objects)
  0x0053ae00 ClearAllMonsterHighlights     NotifyMonsterHighlight (marker objects)
  0x0053A320 SetTargetingMode              cursor change, target cone visual, pause/resume of the world
  0x00537540 RevalidateSelectedTarget      ends in SetTargetingMode (UI)

How the world is controlled:
  * Monsters/groups are never the live ones: gXStatus.plsMonsterList and plsMonsterGroupList point at scratch
    PLists (S0) of scratch W8MonsterInfo (S1, 0x430 apart) / W8MonsterGroup (S2) records; the unborn and
    encounter lists are nulled, so a lookup that misses never reaches live data. Location/group ids that a
    lookup with assert_on_failure=true uses are always present. Scratch W8Monster objects (S3) carry only the
    fields read (radius +0x9c, position +0x118, height +0x190, m_pRep +0x1d8 -> scratch rep in S4: colour +0x4c,
    cycle +0xa4); monster records for species 990..999 are wired through gXStatus.monster_record_cache (S5).
  * Party: XChar rows (heap) and Char[slot] condition/HP block 0xa35..0xb15 are written per referenced slot;
    the block content comes from a corpus character, then the tested fields are overwritten.
  * CURRENT-context state is always written: g_current_screen_state.id, g_level_block (null or a scratch block
    with selection_kind/pending_action/selection_settled), g_status.selected_character, gXStatus combat/spell/
    item mode bytes. An unsettled item selection is never combined with ChooseCombatAction callers (it hands out
    a null detail block: crash in both). gpSCSV and the use-item globals are wired whenever the shared context
    can be reached through ChooseCombatAction; gXStatus.shared_action_detail (written there) is kept.
  * Spell ids are always 0..149 where a record is read (larger/negative ids read outside the heap table), item
    ids -1 or 0..818 where Items.dbs is read (GetItemSpell never sees -1: it would read record -1).
  * Op budget: the core runs at most 96 set/cap/... ops per case; every case is checked here.

Port bugs found by the run targeting_a+4 (fixed in Targeting.cpp, kept here as what the cases guard):
  * GetTargetBlockForContext default case: retail asserts line 0xc2f, the port asserted 0xc37 (every invalid
    explicit context in targetblock/spellvalid cases).
  * CompareMonsterTargetCandidates: retail compares `state` unsigned (JAE/JBE) and takes an unordered (NaN)
    distance as "less" (FCOMP + TEST AH,1); the port compared the W8Condition enum (signed) and a NaN distance
    fell through to 0 (cases labelled edge=state_unsigned / nan_distance).
  * CanPartySlotParticipate (highest_condition unsigned in retail) behind IsTargetStillPresent,
    TargetMatchesNeeded, IsSpellTargetStillValidIn, ChooseCombatAction callers and the ApplyTarget family.
  * ShouldClearAimForAppliedTarget answers a literal 0/1 for action bytes 2/0xff.
  * CollectMonstersWithinRadius compares the side selector as a byte (side 0xff matches disposition 0xff).
  * Cases labelled edge=fp_boundary put a monster exactly on (or one float step off) a range boundary: retail
    keeps the squares and the root in 80-bit registers, so a difference there is a precision difference.
"""
import math
import struct

from w8diff.api import F32

M32 = 0xffffffff
MAX_OPS = 96

# ---- W8Character (retail asm: 0xa35 = uiCondition[13], 0xa49/0xa4d = [18]/[19]) ----
CHAR = 0x1862
C_BLOCK = 0xa35
C_BLOCK_END = 0xb15
C_TURNCOAT = 0xa35
C_COND18 = 0xa49
C_COND19 = 0xa4d
C_HCOND = 0xb01
C_HP = 0xb11

# ---- W8PartySlotRow (layout.ps1 -Header wiz8/layouts/combat_state.h) ----
XROW = 0x106
X_OCC = 0x00
X_PENDING = 0x01
X_MODES = 0x05
X_PENDING_DETAIL = 0x15
X_T_OOC = 0x1d
X_ACTION = 0x3d
X_ACTION_D0 = 0x41
X_ACTION_D1 = 0x45
X_T_IC = 0x4d
X_ACTION_KIND = 0x6d
X_SPELL_ID = 0x75
X_SPELL_DETAIL = 0x79
X_T_SPELL = 0x81
X_ITEM_DETAIL = 0xa1
X_T_ITEM = 0xa9
X_T_BREATH = 0xd1
X_ORDER = 0xf1
BLOCK_OFFS = {0: X_T_OOC, 1: X_T_IC, 3: X_T_SPELL, 4: X_T_ITEM, 5: X_T_BREATH}

# ---- gXStatus (xstatus.h) ----
GX_COMBAT = 0x8dc         # combat, spell-cast, item-select mode bytes are contiguous
GX_CAMP = 0x8e3
GX_MONLIST = 0x8f5
GX_GRPLIST = 0x8f9
GX_UNBORN = 0x901
GX_ENCLIST = 0x905
GX_TMODE = 0x92f
GX_SHARED_T = 0x9d3
GX_SHARED_D = 0x9f3
GX_RECCACHE = 0xa0f

# ---- g_status / g_settings / level block / spell casting view ----
GS_XCHAR = 0x8
GS_SELECTED = 0x1d
SET_AUTOTARGET = 0x4e
LB_SEL_KIND = 0x2f0       # selection_kind, pending_action (+4), selection_settled (+8)
SCSV_SPELL = 0x100        # uiSpellToCast, override_spell (+4)

# ---- W8MonsterInfo (layout.ps1 -Header wiz8/local_code/MonsterManager.h) ----
M_LOC = 0x0
M_GROUP = 0x4
M_SPECIES = 0x8
M_P3D = 0xc
M_ACTIVE = 0x14
M_INCOMBAT = 0x15
M_DISP = 0x16
M_HPMAX = 0x27
M_HP = 0x2b
M_COND18 = 0x9f
M_HCOND = 0x107
M_SIGHT = 0x28a           # party_threat.sight_state (CanPartyMemberAimAtMonster wants 1)
M_TARGET = 0x2ba
M_ACTION_KIND = 0x2e1
M_ACTION_DETAIL = 0x2e5
M_SPELL_POWER = 0x2e9
MI_LEN = 0x2f0
MSTRIDE = 0x430

# ---- W8MonsterGroup ----
G_ID = 0x0
G_COUNT = 0x4
G_ACTIVE = 0x28
G_DISP = 0x2a
G_LEN = 0x30
GSTRIDE = 0x140

# ---- W8Monster / W8MonsterRep / W8Navigator ----
P_RADIUS = 0x9c
P_POS = 0x118
P_HEIGHT = 0x190
P_REP = 0x1d8
P_LEN = 0x1dc
PSTRIDE = 0x200
R_COLOUR = 0x4c
R_CYCLE = 0xa4
R_LEN = 0xa8
RSTRIDE = 0x600
NAV_POS = 0x100
CYCLE_DIE = 0x15

P_ALT_RADIUS = 0x18c      # movement.alternate_radius (GetDistanceToMonster)

# ---- W8MonsterRecord ----
REC_ATTACK0 = 0xe7        # attacks[0]: fHasAttack +0, range_category +3 (byte, zero-extended)
REC_UNTARGETABLE = 0x24a
RECSTRIDE = 0x300
SPECIES = list(range(990, 1000))
RANGE_STEPS = {-1: 0, 0: 2, 1: 4, 2: 25, 3: 50}
WORLD_SCALE = 500.0       # g_world_scale (const)

# ---- W8CombatState ----
CS_CHARS = 0x18
CS_ROW = 0xd4

# ---- scratch layout ----
# S0
ML = 0x000                # monster PList, data array at ML_DATA (16 entries)
ML_DATA = 0x040
GL = 0x0c0                # group PList, data at GL_DATA (8 entries)
GL_DATA = 0x0d0
TGT = 0x100               # W8CombatSlot
TGT2 = 0x140
SRC = 0x180               # W8TargetSource (+ guard bytes)
ITEMS = 0x200             # W8ItemInstance x 8, 0x10 apart
DETAIL = 0x300            # W8ActionDetailBlock
CENTRE = 0x340
EYE = 0x350
FOUND = 0x360             # W8GrowableVector<int>: vptr, count, capacity, data
STR = 0x400
CAND = 0x500              # two W8MonsterTargetCandidate records, 0x20 apart
# S6
LB = 0x0000
SCSV = 0x0400
CS = 0x1000
NAV = 0x2000

# ---- databases ----
SPELL_COUNT = 150
ITEM_COUNT = 819
# SpellTables.dbs target types (GOG 1.2.4, as used by the magic specs); only used to spread the spell ids.
SPELL_TT = [0, 3, 2, 3, 3, 3, 1, 5, 2, 3, 3, 3, 4, 1, 4, 6, 1, 2, 10, 1, 2, 1, 6, 9, 4, 5, 2, 1, 5, 4,
            6, 5, 2, 2, 1, 1, 6, 4, 8, 10, 2, 3, 6, 5, 2, 2, 4, 5, 6, 5, 3, 1, 5, 2, 1, 6, 2, 6, 1, 2,
            8, 1, 2, 5, 2, 1, 3, 7, 2, 6, 3, 4, 2, 0, 1, 0, 6, 7, 5, 3, 6, 6, 3, 5, 3, 7, 5, 6, 1, 3,
            7, 3, 3, 6, 7, 7, 7, 7, 7, 7, 1, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 7, 6, 5,
            1, 4, 4, 8, 4, 4, 4, 4, 4, 7, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
# SpellTables.dbs range categories (same source); used to place monsters around the range.
SPELL_RNG = [0, 2, 0, 2, 2, 2, 2, 2, 0, 2, 2, 2, 2, 2, 3, 3, 2, 0, 0, 1, 0, 1, 2, 0, 3, 2, 0, 1, 2, 3,
             3, 2, 0, 0, 2, 2, 3, 3, 3, 0, 0, 2, 3, 2, 0, 0, 3, 2, 3, 2, 3, 2, 2, 0, 1, 3, 0, 3, 1, 0,
             1, 1, -1, 2, 0, 1, 3, 3, 0, 3, 3, 3, 0, 0, 2, 0, 3, 3, 2, 3, 3, 3, 2, 2, 2, 3, 2, 3, 1, 2,
             3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 2, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 2, 3, -1, 2,
             1, 2, 2, 3, 1, 0, 1, 1, 1, 2, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
SPELLS_BY_TT = {}
for _s, _t in enumerate(SPELL_TT):
    SPELLS_BY_TT.setdefault(_t, []).append(_s)
SPECIAL_SPELLS = [0, 3, 0x29, 0x58, 0x77, 149]   # none, charm, mindread, resurrection, breath id
# Items.dbs ids whose record carries a spell (shared with the other specs).
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

FACTION_NAMES = [
    "UNALIGNED", "FACTION_PARTY", "FACTION_DARK_SAVANT", "FACTION_COSMIC_LORDS", "FACTION_UMPANI",
    "FACTION_TRANG", "FACTION_MOOK", "FACTION_RATTKIN_COMMON", "FACTION_RATTKIN_MAFIA",
    "FACTION_BROTHERHOOD", "FACTION_HIGARDI_BANK", "FACTION_HIGARDI_HLL", "FACTION_HIGARDI_COMMON",
    "FACTION_TRYNNIE", "FACTION_MAD_MARTEN", "FACTION_RAPAX_COMMON", "FACTION_RAPAX_TEMPLAR",
    "FACTION_RAPAX_ARMY", "FACTION_KINGS_ASSASINS", "FACTION_filler3", "FACTION_filler4"]
FACTION_REC = 0xe
FACTION_COUNT = 21


# --------------------------------------------------------------------------------------
# packing helpers
def p8(v):
    return bytes([int(v) & 0xff])


def p32(v):
    return struct.pack('<I', int(v) & M32)


def pf(v):
    return struct.pack('<f', v)


def f32r(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


def s32(v):
    v &= M32
    return v - (1 << 32) if v >= (1 << 31) else v


def slot_bytes(kind, ichar=-1, imon=-1, igroup=-1, pt=(0.0, 0.0, 0.0), item=0):
    """W8CombatSlot, 0x20 bytes."""
    return struct.pack('<IIIIfffI', kind & M32, ichar & M32, imon & M32, igroup & M32,
                       pt[0], pt[1], pt[2], item & M32)


def rand_bytes(r, n):
    return bytes(r.getrandbits(8) for _ in range(n))


def wpick(r, table):
    """table: list of (value, weight)."""
    tot = sum(w for _, w in table)
    x = r.random() * tot
    for v, w in table:
        x -= w
        if x < 0:
            return v
    return table[-1][0]


def emit_sparse(c, addr, data, gap=24):
    """Scratch is zero for every case: write only the runs that are not zero."""
    n = len(data)
    i = 0
    while i < n:
        if data[i] == 0:
            i += 1
            continue
        last = i
        j = i
        while j < n:
            if data[j] != 0:
                last = j
            elif j - last > gap:
                break
            j += 1
        c.set(addr + i, bytes(data[i:last + 1]))
        i = last + 1


def check_ops(c):
    if len(c.ops) > MAX_OPS:
        raise ValueError('%s: %d ops > %d' % (c.id, len(c.ops), MAX_OPS))


class Blob(bytearray):
    def u8(self, off, v):
        self[off] = int(v) & 0xff
        return self

    def u32(self, off, v):
        struct.pack_into('<I', self, off, int(v) & M32)
        return self

    def f32(self, off, v):
        struct.pack_into('<f', self, off, v)
        return self

    def put(self, off, data):
        self[off:off + len(data)] = data
        return self

    def get_u32(self, off):
        return struct.unpack_from('<I', self, off)[0]


# --------------------------------------------------------------------------------------
# value pickers
def g_occ(r, edge=0.05):
    x = r.random()
    if x < 0.15:
        return 0
    if x < 1.0 - edge:
        return 1
    return r.choice([2, 0x80, 0xff])


def g_hp(r, edge=0.08):
    x = r.random()
    if x < 0.18:
        return 0
    if x < 1.0 - edge:
        return r.randint(1, 400)
    return r.choice([1, 0x7fffffff, 0x80000000, M32])


def g_hcond(r, edge=0.06):
    x = r.random()
    if x < 0.5:
        return 0
    if x < 0.75:
        return r.randint(1, 0x11)
    if x < 1.0 - edge:
        return r.choice([0x11, 0x12, 0x12, 0x13, 0x14])
    return r.choice([0x80000000, M32, 0xfffffff0, 0x7fffffff])


def g_cond(r, p_set=0.3, edge=0.06):
    x = r.random()
    if x < 1.0 - p_set:
        return 0
    if x < 1.0 - edge:
        return r.choice([1, 2, 3, 5, 10, 99, 9999, r.randint(1, 300)])
    return r.choice([0x80000000, M32, 0x7fffffff])


def g_bool(r, p_true=0.5, edge=0.05):
    if r.random() < p_true:
        return r.choice([2, 0x80, 0xff]) if r.random() < edge else 1
    return 0


def g_spell(r):
    x = r.random()
    if x < 0.12:
        return r.choice(SPECIAL_SPELLS)
    if x < 0.7:
        tt = r.choice(sorted(SPELLS_BY_TT))
        return r.choice(SPELLS_BY_TT[tt])
    return r.randrange(SPELL_COUNT)


def g_item_id(r, p_none=0.1, p_spell=0.6):
    x = r.random()
    if x < p_none:
        return -1
    if x < p_none + p_spell:
        return r.choice(SPELL_ITEMS)
    return r.randrange(ITEM_COUNT)


def g_float(r):
    x = r.random()
    if x < 0.3:
        return float(r.randint(-3000, 3000))
    if x < 0.6:
        return f32r(r.uniform(-5000.0, 5000.0))
    if x < 0.8:
        return f32r(r.uniform(-2.0, 2.0))
    return r.choice([0.0, -0.0, 1.0, 0.5, 1000.0, -1000.0, 1e-30, 3.0e38, -2.5])


def g_loc(r):
    return r.choice([r.randint(1, 4000), r.randint(1, 4000), r.randint(10000, 70000), 0])


# --------------------------------------------------------------------------------------
class Env:
    def __init__(self, ctx):
        self.ctx = ctx
        self.gx = ctx.g('gXStatus')
        self.gs = ctx.g('g_status')
        self.lb = ctx.g('g_level_block')
        self.screen = ctx.g('g_current_screen_state')
        self.settings = ctx.g('g_settings')
        self.factions = ctx.g('g_factions')
        self.scsv = ctx.g('gpSCSV')
        self.use_sel = ctx.g('g_use_item_selected')
        self.use_ovr = ctx.g('g_use_item_select_override_item')
        self.world = ctx.g('g_startup_world')
        self.combat = ctx.g('g_combat_state')
        self.S = [ctx.scratch(k) for k in range(8)]

    def char(self, s):
        return self.ctx.char(s)

    def row(self, s):
        return (self.gs + GS_XCHAR).deref() + s * XROW

    def item(self, k):
        return self.S[0] + ITEMS + k * 0x10

    def mon(self, i):
        return self.S[1] + i * MSTRIDE

    def grp(self, k):
        return self.S[2] + k * GSTRIDE

    def p3d(self, i):
        return self.S[3] + i * PSTRIDE

    def rep(self, i):
        return self.S[4] + i * RSTRIDE

    def rec(self, k):
        return self.S[5] + k * RECSTRIDE


def put_char(env, c, r, slot, occ=None, hp=None, hcond=None, c18=None, c19=None, turncoat=None):
    """Char[slot] block 0xa35..0xb15 from a corpus character with the given fields
    overwritten, and XChar[slot].fOccupied."""
    ctx = env.ctx
    name, data = ctx.corpus[r.randrange(len(ctx.corpus))]
    blk = Blob(data[C_BLOCK:C_BLOCK_END])
    for off, v in ((C_TURNCOAT, turncoat), (C_COND18, c18), (C_COND19, c19), (C_HCOND, hcond),
                   (C_HP, hp)):
        if v is not None:
            blk.u32(off - C_BLOCK, v)
    c.set(env.char(slot) + C_BLOCK, bytes(blk))
    if occ is not None:
        c.set(env.row(slot) + X_OCC, p8(occ))
    return name


def put_participant(env, c, r, slot, active_p=0.75):
    """A slot that participates (occupied, alive, below DEAD) with probability active_p."""
    if r.random() < active_p:
        occ, hp, hcond = 1 if r.random() < 0.95 else r.choice([2, 0xff]), r.randint(1, 400), \
            r.choice([0, 0, 0, 1, 5, 0x0e, 0x11])
    else:
        which = r.choice(['occ', 'hp', 'cond', 'cond'])
        occ = 0 if which == 'occ' else 1
        hp = 0 if which == 'hp' else r.randint(1, 300)
        hcond = r.choice([0x12, 0x13, 0x14, M32, 0x80000000]) if which == 'cond' else 0
    return occ, hp, hcond


class World:
    """Scratch monsters, groups, records wired into gXStatus."""

    def __init__(self, env, c):
        self.env = env
        self.c = c
        self.mons = []        # Blob(MI_LEN)
        self.p3d = {}         # index -> (Blob(P_LEN), Blob(R_LEN) or None)
        self.groups = []      # Blob(G_LEN)
        self.records = {}     # species -> untargetable byte

    def add_mon(self, loc, group=0, species=None, active=1, in_combat=1, disp=1, hpmax=50, hp=30,
                cond18=0, hcond=0, sight=0):
        m = Blob(MI_LEN)
        m.u32(M_LOC, loc)
        m.u32(M_GROUP, group)
        if species is not None:
            m.u32(M_SPECIES, species)
        m.u8(M_ACTIVE, active)
        m.u8(M_INCOMBAT, in_combat)
        m.u8(M_DISP, disp)
        m.u32(M_HPMAX, hpmax)
        m.u32(M_HP, hp)
        m.u32(M_COND18, cond18)
        m.u32(M_HCOND, hcond)
        m.u8(M_SIGHT, sight)
        self.mons.append(m)
        return len(self.mons) - 1, m

    def set_p3d(self, i, radius=0.0, pos=(0.0, 0.0, 0.0), height=0.0, rep=None, alt_radius=0.0):
        p = Blob(P_LEN)
        p.f32(P_RADIUS, radius)
        for k in range(3):
            p.f32(P_POS + 4 * k, pos[k])
        p.f32(P_ALT_RADIUS, alt_radius)
        p.f32(P_HEIGHT, height)
        self.p3d[i] = (p, rep)

    def add_group(self, gid, count=1, active=1, disp=1):
        g = Blob(G_LEN)
        g.u32(G_ID, gid)
        g.u32(G_COUNT, count)
        g.u8(G_ACTIVE, active)
        g.u8(G_DISP, disp)
        self.groups.append(g)
        return len(self.groups) - 1

    def emit(self, monster_list=True, group_list=True, mon_gap=24):
        env, c = self.env, self.c
        S0 = env.S[0]
        for i, m in enumerate(self.mons):
            emit_sparse(c, env.mon(i), m, mon_gap)
            if i in self.p3d:
                p, rep = self.p3d[i]
                c.setp(env.mon(i) + M_P3D, env.p3d(i))
                emit_sparse(c, env.p3d(i), p, 16)
                if rep is not None:
                    c.setp(env.p3d(i) + P_REP, env.rep(i))
                    emit_sparse(c, env.rep(i), rep, 16)
        for k, sp in enumerate(sorted(self.records)):
            c.setp(env.gx + GX_RECCACHE + sp * 4, env.rec(k))
            if self.records[sp]:
                c.set(env.rec(k) + REC_UNTARGETABLE, p8(self.records[sp]))
        if monster_list:
            n = len(self.mons)
            c.setp(S0 + ML, S0 + ML_DATA)
            c.set(S0 + ML + 4, p32(max(n, 10)) + p32(n))
            for i in range(n):
                c.setp(S0 + ML_DATA + 4 * i, env.mon(i))
            c.setp(env.gx + GX_MONLIST, S0 + ML)
            c.set(env.gx + GX_UNBORN, p32(0))
        if group_list:
            n = len(self.groups)
            for k, g in enumerate(self.groups):
                emit_sparse(c, env.grp(k), g, 48)
            c.setp(S0 + GL, S0 + GL_DATA)
            c.set(S0 + GL + 4, p32(max(n, 10)) + p32(n))
            for k in range(n):
                c.setp(S0 + GL_DATA + 4 * k, env.grp(k))
            c.setp(env.gx + GX_GRPLIST, S0 + GL)
            c.set(env.gx + GX_ENCLIST, p32(0))


def distinct_ids(r, n, gen):
    out = []
    while len(out) < n:
        v = gen(r)
        if v not in out:
            out.append(v)
    return out


def put_level_block(env, c, r, null_p=0.2, sel=None, settled=None, pending=None):
    """g_level_block: null or a scratch block (S6) with selection_kind/pending_action/settled."""
    if r.random() < null_p:
        c.set(env.lb, p32(0))
        return None
    c.setp(env.lb, env.S[6] + LB)
    if sel is None:
        sel = r.choice([-1, -1, -1, 7, 7, 8, 8, 0, 1, 2, 3, 4, 5, 6, 9, 10, 11, -2])
    if settled is None:
        settled = r.choice([0, 1, 1, 2, 0xff])
    if pending is None:
        pending = g_spell(r) if r.random() < 0.7 else r.choice([-1, 0, 200, r.randint(-5, 5)])
    c.set(env.S[6] + LB + LB_SEL_KIND, p32(sel) + p32(pending) + p8(settled))
    return (sel, settled, pending)


def put_context(env, c, r, slot, choose_safe=False, lb_null_p=0.2):
    """Writes everything GetCurrentTargetingContext reads. choose_safe: the case calls
    ChooseCombatAction (no unsettled item selection; shared context wired).
    Returns (resolved context as the retail code computes it, note dict)."""
    screen = 7 if r.random() < 0.65 else r.choice([0, 1, 6, 8, 9, 0x7fffffff])
    c.set(env.screen, p32(screen))
    lbv = None
    if r.random() < lb_null_p:
        c.set(env.lb, p32(0))
    else:
        sel = r.choice([-1, -1, -1, 7, 7, 8, 8, 0, 1, 2, 3, 4, 5, 6, 9, 10, 11, -2])
        settled = r.choice([0, 1, 1, 2, 0xff])
        pending = None
        if choose_safe:
            if sel == 8 and settled == 0:
                settled = 1
            pending = g_spell(r)      # a dialogue cast hands pending_action to the spell table
        lbv = put_level_block(env, c, r, null_p=0.0, sel=sel, settled=settled, pending=pending)
    x = r.random()
    if x < 0.45:
        selected = slot
    else:
        selected = r.choice([s for s in range(8) if s != slot] + [-1, 8])
    c.set(env.gs + GS_SELECTED, p32(selected))
    combat = g_bool(r, 0.4, 0.05)
    spell_mode = g_bool(r, 0.3, 0.05)
    item_mode = g_bool(r, 0.3, 0.05)
    c.set(env.gx + GX_COMBAT, p8(combat) + p8(spell_mode) + p8(item_mode))
    if screen == 7 and lbv is not None and lbv[0] != -1:
        sel, settled, _ = lbv
        ctxv = 3 if (sel == 7 and settled) else (4 if (sel == 8 and settled) else 7)
    elif slot == selected and (spell_mode or item_mode):
        ctxv = 2
    else:
        ctxv = 1 if combat else 0
    if choose_safe and ctxv == 2:
        put_shared_sources(env, c, r, spell_mode)
    return ctxv, {'screen': s32(screen), 'lb': 'null' if lbv is None else '%d/%d' % (lbv[0], lbv[1]),
                  'selected': selected, 'combat': combat, 'spell_mode': spell_mode,
                  'item_mode': item_mode, 'ctx': ctxv}


def put_shared_sources(env, c, r, spell_mode):
    """What ChooseCombatAction reads for the shared context."""
    S6 = env.S[6]
    if spell_mode:
        c.setp(env.scsv, S6 + SCSV)
        override = 0 if r.random() < 0.5 else g_spell(r)
        c.set(S6 + SCSV + SCSV_SPELL, p32(g_spell(r)) + p32(override))
    else:
        for g in (env.use_ovr, env.use_sel):
            if r.random() < 0.5:
                c.set(g, p32(0))
            else:
                k = r.randrange(6, 8)
                c.set(env.item(k), p32(g_item_id(r, p_none=0.0)))
                c.setp(g, env.item(k))
        c.keep(env.gx + GX_SHARED_D, 8)


def put_item(env, c, r, k, item_no):
    c.set(env.item(k), p32(item_no) + rand_bytes(r, 8))


TARGET_KINDS = [(0, 1.0), (1, 4.0), (2, 2.0), (3, 4.0), (4, 3.0), (5, 1.0), (6, 2.0), (7, 2.0),
                (8, 1.0), (9, 3.0), (10, 0.4), (-1, 0.3), (0x101, 0.3)]


def rand_target(r, mon_locs, grp_ids, allow_char_neg=True, allow_null_item=True, no_place=False,
                self_slot=None, kinds=TARGET_KINDS):
    """-> (kind, ichar, imon, igroup, item_wanted) for a presence world."""
    while True:
        kind = wpick(r, kinds)
        if not (no_place and kind == 6):
            break
    ichar = r.choice([-1, -1, r.randrange(8), r.randint(0, 0x7fffffff)])
    imon = r.choice([-1, r.randint(1, 4000)])
    igroup = r.choice([-1, r.randint(1, 400)])
    item = False
    if kind in (1, 9):
        if self_slot is not None and kind == 1:
            ichar = self_slot
        elif allow_char_neg and r.random() < 0.12:
            ichar = -1
        else:
            ichar = r.randrange(8)
    if kind == 3:
        x = r.random()
        if mon_locs and x < 0.72:
            imon = r.choice(mon_locs)
        elif x < 0.9:
            imon = r.randint(4001, 9000)
        else:
            imon = -1
    if kind == 4:
        x = r.random()
        if grp_ids and x < 0.72:
            igroup = r.choice(grp_ids)
        elif x < 0.9:
            igroup = r.randint(401, 900)
        else:
            igroup = -1
    if kind == 7:
        item = (not allow_null_item) or r.random() < 0.85
    return kind, ichar, imon, igroup, item


def presence_world(env, c, r, w, max_mon=5, max_grp=3, sight=0, species=False):
    """Monsters/groups with mixed presence fields. Returns (mon_locs, grp_ids)."""
    nm = r.choice([0, 1, 2, 3, 3, 4, 5][:max_mon + 2])
    locs = distinct_ids(r, nm, g_loc)
    if nm and r.random() < 0.05:
        locs[r.randrange(nm)] = M32
    for loc in locs:
        sp = r.choice(SPECIES[:3]) if species else None
        w.add_mon(loc, group=r.randint(1, 400), species=sp, active=g_bool(r, 0.8, 0.08),
                  hp=0 if r.random() < 0.15 else r.choice([1, 50, r.randint(1, 900), 0x80000000, M32]),
                  cond18=g_cond(r, 0.25), hcond=g_hcond(r), sight=sight)
        if species:
            w.records.setdefault(sp, 0)
    ng = r.choice([0, 1, 2, 3][:max_grp + 1])
    gids = distinct_ids(r, ng, lambda rr: rr.choice([rr.randint(1, 400), rr.randint(1, 400), 0]))
    for gid in gids:
        w.add_group(gid, count=r.choice([0, 1, 2, 5, r.randint(1, 30), 0x80000000, M32]),
                    active=g_bool(r, 0.75, 0.1), disp=r.choice([0, 1, 2]))
    return [s32(x) for x in locs], gids


def write_target(env, c, r, addr, t, item_k=0, item_id=None, pt=None):
    """Write a W8CombatSlot (kind, ichar, imon, igroup, item_wanted) at addr; returns its bytes."""
    kind, ichar, imon, igroup, item = t
    if pt is None:
        pt = (g_float(r), g_float(r), g_float(r))
    data = slot_bytes(kind, ichar, imon, igroup, pt, 0)
    c.set(addr, data)
    if item:
        put_item(env, c, r, item_k, g_item_id(r, p_none=0.35) if item_id is None else item_id)
        c.setp(addr + 0x1c, env.item(item_k))
    return data


def put_presence_chars(env, c, r, slots):
    for s in sorted(set(slots)):
        put_char(env, c, r, s, occ=g_occ(r), hp=g_hp(r), hcond=g_hcond(r), c18=g_cond(r, 0.4),
                 c19=g_cond(r, 0.3))


def target_char_slots(*targets):
    out = []
    for t in targets:
        if t[0] in (1, 9) and 0 <= t[1] < 8:
            out.append(t[1])
    return out


def cases(ctx):
    env = Env(ctx)
    t_source_builders(ctx, env)
    t_source_predicates(ctx, env)
    t_target_notice(ctx, env)
    t_should_clear(ctx, env)
    t_factions(ctx, env)
    t_resets(ctx, env)
    t_matches_needed(ctx, env)
    t_still_present(ctx, env)
    t_needed_for_action(ctx, env)
    t_needed_for_item(ctx, env)
    t_target_of_needed_kind(ctx, env)
    t_spell_target_valid(ctx, env)
    t_needed_current(ctx, env)
    t_contexts(ctx, env)
    t_target_block(ctx, env)
    t_monster_matches_spell(ctx, env)
    t_cursor_for_state(ctx, env)
    t_needs_explicit(ctx, env)
    t_spell_like_id(ctx, env)
    t_compare_candidates(ctx, env)
    t_aim_wrappers(ctx, env)
    t_apply_target(ctx, env)
    t_resolve_point(ctx, env)
    t_collect_radius(ctx, env)
    t_tint(ctx, env)
    t_source_in_range(ctx, env)
    for c in ctx.cases:
        check_ops(c)


# --------------------------------------------------------------------------------------
def t_source_builders(ctx, env):
    S0 = env.S[0]
    fc = ctx.fn(0x0053be00)   # void SetTargetSourceToCharacter(int, W8TargetSource*)
    fm = ctx.fn(0x0053be50)   # void SetTargetSourceToMonster(const W8MonsterInfo*, W8TargetSource*)
    slots = [0, 1, 2, 3, 4, 5, 6, 7, -1, 8, 0x7fffffff, -0x80000000, 0x100]
    for i in range(ctx.n(60)):
        r = ctx.rng('srcchar', i)
        c = ctx.case('srcchar.%d' % i, fc, conv='c', ret='v')
        c.set(S0 + SRC, rand_bytes(r, 0x40))
        slot = r.choice(slots) if r.random() < 0.4 else r.randrange(8)
        c.arg(slot)
        c.arg(S0 + SRC)
        c.cap(S0 + SRC, 0x40, 'source')
        c.note(slot=slot)
    for i in range(ctx.n(60)):
        r = ctx.rng('srcmon', i)
        c = ctx.case('srcmon.%d' % i, fm, conv='c', ret='v')
        c.set(S0 + SRC, rand_bytes(r, 0x40))
        loc = r.choice([g_loc(r), -1, 0, 0x7fffffff, -0x80000000, r.getrandbits(32)])
        c.set(env.mon(0), p32(loc) + rand_bytes(r, 0x20))
        c.arg(env.mon(0))
        c.arg(S0 + SRC)
        c.cap(S0 + SRC, 0x40, 'source')
        c.note(loc=loc)


def source_bytes(r, kind, ichar, imon, refl, back):
    b = Blob(rand_bytes(r, 0x34))
    b.u32(0, kind)
    b.u32(4, ichar)
    b.u32(8, imon)
    b.u8(0x1b, refl)
    b.u8(0x1c, back)
    return bytes(b)


SOURCE_KINDS = [(1, 4.0), (2, 4.0), (3, 5.0), (0, 1.5), (4, 0.6), (-1, 0.4), (0x101, 0.4),
                (0x80000003, 0.3)]


def rand_source(r):
    kind = wpick(r, SOURCE_KINDS)
    ichar = r.choice([-1, -1, r.randrange(8), r.randrange(8), 8, 0x7fffffff])
    imon = r.choice([-1, -1, g_loc(r), g_loc(r), 0])
    refl = r.choice([0, 0, 0, 1, 1, 2, 0xff])
    back = r.choice([0, 0, 0, 1, 1, 0x80, 0xff])
    return kind, ichar, imon, refl, back


def t_source_predicates(ctx, env):
    S0 = env.S[0]
    fic = ctx.fn(0x0053bea0)   # bool TargetSourceIsCharacter(const W8TargetSource*, int)
    fim = ctx.fn(0x0053bf10)   # bool TargetSourceIsMonster(const W8TargetSource*, int)
    fnc = ctx.fn(0x0053c320)   # char GetSourceNoticeColor(const W8TargetSource*)
    allow = [1, 1, 1, 1, 0, 0, 2, -1, 0x101, 0x7fffffff]
    for tag, fn, count in (('srcischar', fic, 200), ('srcismon', fim, 200)):
        for i in range(ctx.n(count)):
            r = ctx.rng(tag, i)
            c = ctx.case('%s.%d' % (tag, i), fn, conv='c', ret='b')
            src = rand_source(r)
            c.set(S0 + SRC, source_bytes(r, *src))
            a = r.choice(allow)
            c.arg(S0 + SRC)
            c.arg(a)
            c.note(kind=src[0], ichar=s32(src[1]), imon=s32(src[2]), refl=src[3], back=src[4], allow=a)
    for i in range(ctx.n(150)):
        r = ctx.rng('srccolor', i)
        c = ctx.case('srccolor.%d' % i, fnc, conv='c', ret='u8')
        src = rand_source(r)
        c.set(S0 + SRC, source_bytes(r, *src))
        c.arg(S0 + SRC)
        c.note(kind=src[0], ichar=s32(src[1]), imon=s32(src[2]), refl=src[3], back=src[4])


def t_target_notice(ctx, env):
    """char GetTargetNoticeColor(const W8TargetSource*, const W8CombatSlot*)"""
    S0 = env.S[0]
    fn = ctx.fn(0x0053c3f0)
    for i in range(ctx.n(200)):
        r = ctx.rng('tgtcolor', i)
        c = ctx.case('tgtcolor.%d' % i, fn, conv='c', ret='u8')
        src = rand_source(r)
        c.set(S0 + SRC, source_bytes(r, *src))
        kind = wpick(r, [(1, 5.0), (3, 3.0), (0, 1.0), (2, 1.0), (4, 1.0), (6, 0.5), (9, 1.0),
                         (7, 0.5), (-1, 0.3), (0x101, 0.3), (0x103, 0.3)])
        ichar = r.randrange(8) if kind == 1 else r.choice([-1, r.randrange(8), 99])
        c.set(S0 + TGT, slot_bytes(kind, ichar, g_loc(r), r.randint(-1, 50)))
        order = None
        if kind == 1:
            order = r.choice([0, 1, 2, 3, 4, 5, 6, 7]) if r.random() < 0.8 else \
                r.choice([-1, 0x108, 0x7fffffff, 0xffffff05])
            c.set(env.row(ichar) + X_ORDER, p32(order))
        c.arg(S0 + SRC)
        c.arg(S0 + TGT)
        c.note(src_kind=src[0], src_char=s32(src[1]), kind=kind, ichar=ichar,
               order=None if order is None else s32(order))


# --------------------------------------------------------------------------------------
def t_should_clear(ctx, env):
    """bool ShouldClearAimForAppliedTarget(W8TargetSource*, W8CombatSlot*, bool in_combat,
    bool action_targets_enemies)"""
    S0 = env.S[0]
    fn = ctx.fn(0x0053C490)
    for i in range(ctx.n(300)):
        r = ctx.rng('shouldclear', i)
        c = ctx.case('shouldclear.%d' % i, fn, conv='c', ret='b')
        w = World(env, c)
        nm = r.randint(1, 6)
        locs = distinct_ids(r, nm, g_loc)
        if r.random() < 0.06:
            locs[r.randrange(nm)] = M32           # a monster whose id is BAD_INDEX
        for loc in locs:
            w.add_mon(loc, disp=r.choice([0, 1, 1, 2, 3, 0xff]))
        ng = r.randint(1, 3)
        gids = distinct_ids(r, ng, lambda rr: rr.randint(0, 400))
        for gid in gids:
            w.add_group(gid, disp=r.choice([0, 1, 1, 2, 0xff]))
        w.emit(mon_gap=8)
        # source
        skind = wpick(r, [(1, 5.0), (2, 5.0), (0, 0.5), (3, 0.6), (4, 0.3), (-1, 0.3)])
        sch = r.randrange(8)
        smon = r.choice(locs)
        c.set(S0 + SRC, source_bytes(r, skind, sch if skind == 1 else r.choice([-1, sch]),
                                     smon if skind == 2 else r.choice([-1, smon]), 0, 0))
        # target
        tkind = wpick(r, [(1, 5.0), (3, 5.0), (4, 4.0), (0, 0.4), (2, 0.4), (5, 0.3), (6, 0.3),
                          (7, 0.2), (9, 0.4), (-1, 0.2)])
        tch = r.randrange(8)
        tmon = r.choice(locs)
        tgrp = r.choice(gids)
        c.set(S0 + TGT, slot_bytes(tkind, tch if tkind == 1 else r.choice([-1, tch]),
                                   tmon if tkind == 3 else r.choice([-1, tmon]),
                                   tgrp if tkind == 4 else r.choice([-1, tgrp]),
                                   (g_float(r), g_float(r), g_float(r))))
        tc = {}
        for s in {sch, tch}:
            tc[s] = g_cond(r, 0.45, 0.15)
            c.set(env.char(s) + C_TURNCOAT, p32(tc[s]))
        in_combat = r.choice([1, 1, 1, 1, 0, 0, 0x100, 2, 0xff])
        ate = r.choice([0, 0, 1, 1, 2, 0x100, 0xff])
        c.arg(S0 + SRC)
        c.arg(S0 + TGT)
        c.arg(in_combat)
        c.arg(ate)
        c.note(src='%d:%d/%d' % (skind, sch, s32(smon)), tgt='%d:%d/%d/%d' % (tkind, tch, s32(tmon), tgrp),
               in_combat=in_combat, ate=ate, turncoat=';'.join('%d=%x' % kv for kv in sorted(tc.items())))


# --------------------------------------------------------------------------------------
def t_factions(ctx, env):
    S0 = env.S[0]
    ffind = ctx.fn(0x005360b0)   # signed char FindFactionByName(const char*)
    fval = ctx.fn(0x005360f0)    # int GetFactionValue(signed char)
    fset = ctx.fn(0x00536110)    # void SetFactionFlag(signed char, bool)
    fget = ctx.fn(0x00536130)    # unsigned char GetFactionFlag(signed char)
    for i in range(ctx.n(150)):
        r = ctx.rng('findfaction', i)
        c = ctx.case('findfaction.%d' % i, ffind, conv='c', ret='i8')
        base = r.choice(FACTION_NAMES)
        x = r.random()
        if x < 0.25:
            s = base
        elif x < 0.4:
            s = base.lower()
        elif x < 0.55:
            s = ''.join(ch.upper() if r.random() < 0.5 else ch.lower() for ch in base)
        elif x < 0.65:
            s = base + r.choice([' ', 'X', '_', '1', 's'])
        elif x < 0.72:
            s = base[:-1]
        elif x < 0.78:
            s = base[1:]
        elif x < 0.82:
            s = r.choice(['', ' ', 'FACTION_', 'faction', 'UNALIGNE', 'FACTION_FILLER5', 'NONE'])
        elif x < 0.86:
            s = ''.join(r.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ_') for _ in range(29))
        elif x < 0.9:
            s = base.replace('_', r.choice(['-', ' ', '`', '\x7f']), 1)
        elif x < 0.94:
            # '[' ']' '^' '_' '`' sit between the upper- and lower-case letters
            s = base.replace('_', '^').lower()
        else:
            s = base + '\x00GARBAGE'
        data = s.encode('latin-1') + b'\x00'
        if r.random() < 0.05:
            data = s.encode('latin-1')[:-1] + bytes([r.choice([0xc0, 0xe9, 0xff])]) + b'\x00'
        c.set(S0 + STR, data)
        c.arg(S0 + STR)
        c.note(name=s.replace('\x00', '\\0'))
    for tag, fn, ret, count in (('factionvalue', fval, 'i', 60), ('setfactionflag', fset, 'v', 60),
                                ('factionflag', fget, 'u8', 60)):
        for i in range(ctx.n(count)):
            r = ctx.rng(tag, i)
            c = ctx.case('%s.%d' % (tag, i), fn, conv='c', ret=ret)
            table = Blob(rand_bytes(r, FACTION_REC * FACTION_COUNT))
            for f in range(FACTION_COUNT):
                if r.random() < 0.5:
                    table.u8(f * FACTION_REC + 0xa, r.choice([0, 1]))
            c.set(env.factions, bytes(table))
            f = i % FACTION_COUNT if i < FACTION_COUNT else r.randrange(FACTION_COUNT)
            hi = 0 if r.random() < 0.4 else r.choice([r.getrandbits(24), 0xffffff, 0x000001, 0x800000])
            arg = f | (hi << 8)
            c.arg(arg)
            if tag == 'setfactionflag':
                flag = r.choice([0, 1]) if r.random() < 0.7 else r.choice([2, 0xff, 0x80])
                fhi = 0 if r.random() < 0.5 else r.getrandbits(24)
                c.arg(flag | (fhi << 8))
                c.cap(env.factions, FACTION_REC * FACTION_COUNT, 'factions')
                c.note(faction=f, arg=arg, flag=flag | (fhi << 8))
            else:
                c.note(faction=f, arg=arg)


# --------------------------------------------------------------------------------------
def t_resets(ctx, env):
    S0 = env.S[0]
    frs = ctx.fn(0x00536150)    # void ResetTargetSource(W8TargetSource*)
    frc = ctx.fn(0x00536170)    # void ResetCombatSlot(W8CombatSlot*)
    fcm = ctx.fn(0x005369f0)    # bool ClearMonsterCombatSlot(W8MonsterInfo*)
    fst = ctx.fn(0x0053A2C0)    # void SetMonsterCombatTarget(W8MonsterInfo*, int)
    for i in range(ctx.n(30)):
        r = ctx.rng('resetsource', i)
        c = ctx.case('resetsource.%d' % i, frs, conv='c', ret='v')
        c.set(S0 + SRC, rand_bytes(r, 0x40))
        c.arg(S0 + SRC)
        c.cap(S0 + SRC, 0x40, 'source')
    for i in range(ctx.n(30)):
        r = ctx.rng('resetslot', i)
        c = ctx.case('resetslot.%d' % i, frc, conv='c', ret='v')
        c.set(S0 + TGT, rand_bytes(r, 0x30))
        c.arg(S0 + TGT)
        c.cap(S0 + TGT, 0x30, 'slot')
    for i in range(ctx.n(40)):
        r = ctx.rng('clearmonslot', i)
        c = ctx.case('clearmonslot.%d' % i, fcm, conv='c', ret='b')
        c.set(env.mon(0) + M_TARGET - 0x10, rand_bytes(r, 0x50))
        c.arg(env.mon(0))
        c.cap(env.mon(0) + M_TARGET - 0x10, 0x50, 'info')
    for i in range(ctx.n(60)):
        r = ctx.rng('setmontarget', i)
        c = ctx.case('setmontarget.%d' % i, fst, conv='c', ret='v')
        c.set(env.mon(0) + M_TARGET - 0x10, rand_bytes(r, 0x50))
        loc = r.choice([g_loc(r), g_loc(r), -1, 0, 0x7fffffff, -0x80000000])
        c.arg(env.mon(0))
        c.arg(loc)
        c.cap(env.mon(0) + M_TARGET - 0x10, 0x50, 'info')
        c.note(loc=loc)


# --------------------------------------------------------------------------------------
NEEDS = [(-1, 0.6), (0, 1.0), (1, 3.0), (2, 3.0), (3, 1.5), (4, 1.5), (5, 2.5), (6, 1.5), (7, 2.0),
         (8, 2.0), (9, 0.4), (100, 0.2), (0x80000000, 0.2)]


def t_matches_needed(ctx, env):
    """bool TargetMatchesNeeded(W8CombatSlot*, W8TargetNeed)"""
    S0 = env.S[0]
    fn = ctx.fn(0x00537160)
    for i in range(ctx.n(400)):
        r = ctx.rng('matchesneeded', i)
        c = ctx.case('matchesneeded.%d' % i, fn, conv='c', ret='b')
        w = World(env, c)
        locs, gids = presence_world(env, c, r, w)
        w.emit()
        t = rand_target(r, locs, gids, allow_char_neg=True, allow_null_item=True)
        need = wpick(r, NEEDS)
        put_presence_chars(env, c, r, target_char_slots(t))
        null = r.random() < 0.03
        write_target(env, c, r, S0 + TGT, t)
        c.arg(0 if null else S0 + TGT)
        c.arg(need)
        c.note(need=s32(need), kind=s32(t[0]), ichar=s32(t[1]), imon=s32(t[2]), igroup=s32(t[3]),
               item=int(t[4]), null=int(null), monsters=len(locs), groups=len(gids))


def t_still_present(ctx, env):
    """bool IsTargetStillPresent(const W8CombatSlot*)"""
    S0 = env.S[0]
    fn = ctx.fn(0x00536190)
    for i in range(ctx.n(400)):
        r = ctx.rng('stillpresent', i)
        c = ctx.case('stillpresent.%d' % i, fn, conv='c', ret='b')
        w = World(env, c)
        locs, gids = presence_world(env, c, r, w)
        w.emit()
        t = rand_target(r, locs, gids, allow_char_neg=False, allow_null_item=False)
        put_presence_chars(env, c, r, target_char_slots(t))
        null = r.random() < 0.02
        write_target(env, c, r, S0 + TGT, t, item_id=g_item_id(r, p_none=0.3) if r.random() < 0.9
                     else r.choice([-2, 0x7fffffff, 900]))
        c.arg(0 if null else S0 + TGT)
        c.note(kind=s32(t[0]), ichar=s32(t[1]), imon=s32(t[2]), igroup=s32(t[3]), null=int(null))


# --------------------------------------------------------------------------------------
ACTIONS = [(-1, 1.0), (0, 2.0), (1, 1.0), (2, 1.5), (3, 0.7), (4, 0.7), (5, 1.5), (6, 0.7),
           (7, 4.0), (8, 4.0), (9, 0.5), (10, 0.4), (11, 0.4), (12, 0.2), (-2, 0.2),
           (0x80000000, 0.1)]


def t_needed_for_action(ctx, env):
    """W8TargetNeed GetTargetNeededForAction(W8ActionKind, int spell_id, const W8ActionDetailBlock*)"""
    S0 = env.S[0]
    fn = ctx.fn(0x00536a20)
    for i in range(ctx.n(300)):
        r = ctx.rng('needaction', i)
        c = ctx.case('needaction.%d' % i, fn, conv='c', ret='i')
        put_level_block(env, c, r, null_p=0.5)
        action = wpick(r, ACTIONS)
        spell = g_spell(r) if action == 7 or r.random() < 0.5 else r.choice([-1, 200, 0x7fffffff])
        item_no = None
        c.set(S0 + DETAIL, p32(r.choice([0, 1, 2, r.randint(0, 9), -1])))
        if r.random() < 0.88:
            item_no = g_item_id(r, p_none=0.12)
            put_item(env, c, r, 0, item_no)
            c.setp(S0 + DETAIL + 4, env.item(0))
        c.arg(action)
        c.arg(spell)
        c.arg(S0 + DETAIL)
        c.note(action=s32(action), spell=s32(spell), item=item_no)


def t_needed_for_item(ctx, env):
    """W8TargetNeed GetTargetNeededForItem(const W8ItemInstance*)"""
    fn = ctx.fn(0x00537330)
    for i in range(ctx.n(250)):
        r = ctx.rng('needitem', i)
        c = ctx.case('needitem.%d' % i, fn, conv='c', ret='i')
        put_level_block(env, c, r, null_p=0.5)
        null = r.random() < 0.04
        item_no = g_item_id(r, p_none=0.1)
        put_item(env, c, r, 0, item_no)
        c.arg(0 if null else env.item(0))
        c.note(item=item_no, null=int(null))


# --------------------------------------------------------------------------------------
def put_target_blocks(env, c, r, slot, w_locs, w_gids, allow_char_neg=True, allow_null_item=True,
                      no_place=False, self_only=False):
    """The slot's five row target blocks + the shared one, each a different random target.
    Row bytes 0x1d..0xf1 are written as one block (pointer fields zero), item pointers by setp.
    Returns {context: target tuple}."""
    row = Blob(rand_bytes(r, 0xf1 - X_T_OOC))
    targets = {}
    setps = []
    for k, (ctxv, off) in enumerate(sorted(BLOCK_OFFS.items())):
        t = rand_target(r, w_locs, w_gids, allow_char_neg, allow_null_item, no_place,
                        self_slot=slot if self_only else None)
        targets[ctxv] = t
        kind, ichar, imon, igroup, item = t
        row.put(off - X_T_OOC, slot_bytes(kind, ichar, imon, igroup, (g_float(r), 0.0, g_float(r)), 0))
        if item:
            setps.append((off + 0x1c, k))
    # pointer fields of the action detail blocks inside the written range
    for off in (X_ACTION_D1 + 4, X_SPELL_DETAIL + 4, X_ITEM_DETAIL + 4):
        row.u32(off - X_T_OOC, 0)
    c.set(env.row(slot) + X_T_OOC, bytes(row))
    for off, k in setps:
        put_item(env, c, r, k, g_item_id(r, p_none=0.35))
        c.setp(env.row(slot) + off, env.item(k))
    t = rand_target(r, w_locs, w_gids, allow_char_neg, allow_null_item, no_place,
                    self_slot=slot if self_only else None)
    targets[2] = t
    write_target(env, c, r, env.gx + GX_SHARED_T, t, item_k=5)
    return targets


def t_target_of_needed_kind(ctx, env):
    """bool IsItemTargetOfNeededKind(int, const W8ItemInstance*) /
    bool IsSpellTargetOfNeededKind(int, int spell_id)"""
    fi = ctx.fn(0x005372b0)
    fs = ctx.fn(0x00537270)
    for tag, fn in (('itemtargetkind', fi), ('spelltargetkind', fs)):
        for i in range(ctx.n(300)):
            r = ctx.rng(tag, i)
            c = ctx.case('%s.%d' % (tag, i), fn, conv='c', ret='b')
            slot = r.randrange(8)
            ctxv, info = put_context(env, c, r, slot)
            w = World(env, c)
            locs, gids = presence_world(env, c, r, w, max_mon=4, max_grp=2)
            w.emit()
            targets = put_target_blocks(env, c, r, slot, locs, gids)
            put_presence_chars(env, c, r, target_char_slots(*targets.values())[:4])
            auto = r.choice([0, 0, 1, 1, 2, 0xff])
            c.set(env.settings + SET_AUTOTARGET, p8(auto))
            c.arg(slot)
            if tag == 'itemtargetkind':
                null = r.random() < 0.05
                item_no = g_item_id(r, p_none=0.1)
                put_item(env, c, r, 7, item_no)
                c.arg(0 if null else env.item(7))
                c.note(item=item_no, null=int(null))
            else:
                spell = g_spell(r)
                c.arg(spell)
                c.note(spell=spell, tt=SPELL_TT[spell])
            sel = targets.get(ctxv)
            c.note(slot=slot, auto=auto, target=None if sel is None else '%d:%d/%d/%d' % (
                s32(sel[0]), s32(sel[1]), s32(sel[2]), s32(sel[3])), **info)


def t_spell_target_valid(ctx, env):
    """bool IsSpellTargetStillValidIn(int, int spell_id, W8TargetingContext). The range half
    (CharacterActionReachesTarget) is kept to its pure answers: no place targets, a character
    target only the caster itself, monsters unseen (CanPartyMemberAimAtMonster refuses at once),
    groups absent from the (empty) group list."""
    fn = ctx.fn(0x00537220)
    contexts = [(0, 2.0), (1, 2.0), (2, 1.0), (3, 1.0), (4, 1.0), (5, 1.0), (6, 3.0), (7, 0.5),
                (8, 0.3), (9, 0.2), (-1, 0.2)]
    for i in range(ctx.n(250)):
        r = ctx.rng('spellvalid', i)
        c = ctx.case('spellvalid.%d' % i, fn, conv='c', ret='b')
        slot = r.randrange(8)
        context = wpick(r, contexts)
        ctxv, info = put_context(env, c, r, slot)
        w = World(env, c)
        nm = r.choice([0, 1, 2, 3])
        locs = distinct_ids(r, nm, g_loc)
        for loc in locs:
            sp = r.choice(SPECIES[:2])
            w.add_mon(loc, species=sp, active=g_bool(r, 0.8), hp=r.choice([0, 5, 40]),
                      cond18=g_cond(r, 0.2), sight=r.choice([0, 0, 2]))
            w.records[sp] = 0
        w.emit(group_list=False)
        c.set(env.gx + GX_GRPLIST, p32(0))
        c.set(env.gx + GX_ENCLIST, p32(0))
        locs = [s32(x) for x in locs]
        targets = put_target_blocks(env, c, r, slot, locs, [], allow_char_neg=False,
                                    allow_null_item=False, no_place=True, self_only=True)
        put_presence_chars(env, c, r, target_char_slots(*targets.values())[:4])
        spell = g_spell(r)
        c.arg(slot)
        c.arg(spell)
        c.arg(context)
        eff = ctxv if context == 6 else context
        sel = targets.get(eff)
        c.note(slot=slot, spell=spell, tt=SPELL_TT[spell], context=context,
               target=None if sel is None else '%d:%d/%d/%d' % (s32(sel[0]), s32(sel[1]),
                                                                s32(sel[2]), s32(sel[3])), **info)


# --------------------------------------------------------------------------------------
def put_action_row(env, c, r, slot, spell_ids_valid=True):
    """Row bytes 0x00..0xd0 (fOccupied .. queued_action) with random actions; the three
    detail-block item pointers set by setp to scratch items (valid ids) or left null."""
    b = Blob(rand_bytes(r, 0xd1))

    def spellish():
        return g_spell(r) if spell_ids_valid or r.random() < 0.8 else \
            r.choice([-1, 150, 0x7fffffff, r.randint(-100, 1000)])

    occ, hp, hcond = put_participant(env, c, r, slot, 0.85)
    b.u8(X_OCC, occ)
    pending = wpick(r, ACTIONS)
    b.u32(X_PENDING, pending)
    b.u32(X_MODES, spellish() if pending == 7 else r.choice([-1, 0, 1, 2, r.randint(0, 200)]))
    action = wpick(r, ACTIONS)
    b.u32(X_ACTION, action)
    b.u32(X_ACTION_D0, spellish() if action == 7 or r.random() < 0.5 else r.choice([-1, 0, 300]))
    b.u32(X_SPELL_ID, spellish())
    for off in (X_PENDING_DETAIL + 4, X_ACTION_D1 + 4, X_SPELL_DETAIL + 4, X_ITEM_DETAIL + 4,
                X_T_OOC + 0x1c, X_T_IC + 0x1c, X_T_SPELL + 0x1c, X_T_ITEM + 0x1c):
        b.u32(off, 0)
    c.set(env.row(slot), bytes(b))
    items = {}
    for k, off in enumerate((X_PENDING_DETAIL + 4, X_ACTION_D1 + 4, X_ITEM_DETAIL + 4)):
        if r.random() < 0.75:
            item_no = g_item_id(r, p_none=0.0)
            put_item(env, c, r, k, item_no)
            c.setp(env.row(slot) + off, env.item(k))
            items[off] = item_no
    put_char(env, c, r, slot, hp=hp, hcond=hcond)
    return {'occ': occ, 'hp': hp, 'hcond': hcond, 'pending': s32(pending), 'action': s32(action)}


def t_needed_current(ctx, env):
    """W8TargetNeed GetTargetNeededForCurrentAction(int)"""
    fn = ctx.fn(0x00537380)
    for i in range(ctx.n(300)):
        r = ctx.rng('needcurrent', i)
        c = ctx.case('needcurrent.%d' % i, fn, conv='c', ret='i')
        slot = r.randrange(8)
        ctxv, info = put_context(env, c, r, slot, choose_safe=True)
        rowinfo = put_action_row(env, c, r, slot)
        c.arg(slot)
        c.note(slot=slot, **info)
        c.note(**rowinfo)


def t_contexts(ctx, env):
    """GetCurrentTargetingContext(int) / ResolveTargetingContext(int, W8TargetingContext)"""
    fcur = ctx.fn(0x0053bc10)
    fres = ctx.fn(0x0053b920)
    for i in range(ctx.n(250)):
        r = ctx.rng('curcontext', i)
        c = ctx.case('curcontext.%d' % i, fcur, conv='c', ret='i')
        slot = r.randrange(8) if r.random() < 0.95 else r.choice([-1, 8])
        ctxv, info = put_context(env, c, r, slot)
        c.arg(slot)
        c.note(slot=slot, **info)
    contexts = [(6, 5.0), (0, 1.0), (1, 1.0), (2, 1.0), (3, 1.0), (4, 1.0), (5, 1.0), (7, 1.0),
                (8, 0.6), (9, 0.4), (-1, 0.4), (0x80000000, 0.2), (0x106, 0.2)]
    for i in range(ctx.n(250)):
        r = ctx.rng('rescontext', i)
        c = ctx.case('rescontext.%d' % i, fres, conv='c', ret='i')
        slot = r.randrange(8)
        context = wpick(r, contexts)
        ctxv, info = put_context(env, c, r, slot)
        c.arg(slot)
        c.arg(context)
        c.note(slot=slot, context=s32(context), **info)


def t_target_block(ctx, env):
    """W8CombatSlot* GetTargetBlockForContext(int, W8TargetingContext): XChar is redirected into
    scratch 7, so a row block comes back as an S7 offset; the shared block (gXStatus) is compared
    by its 32 bytes."""
    fn = ctx.fn(0x0053b7f0)
    contexts = [(6, 4.0), (0, 1.0), (1, 1.0), (2, 1.0), (3, 1.0), (4, 1.0), (5, 1.0), (7, 1.0),
                (8, 0.6), (9, 0.4), (-1, 0.4), (0x80000000, 0.2)]
    for i in range(ctx.n(250)):
        r = ctx.rng('targetblock', i)
        c = ctx.case('targetblock.%d' % i, fn, conv='c', ret='p', out='p')
        slot = r.randrange(8) if r.random() < 0.94 else r.choice([-1, 8, 20])
        context = wpick(r, contexts)
        ctxv, info = put_context(env, c, r, slot)
        c.setp(env.gs + GS_XCHAR, env.S[7])
        c.set(env.gx + GX_SHARED_T, slot_bytes(r.randint(0, 9), r.randrange(8), g_loc(r),
                                               r.randint(1, 400), (g_float(r), g_float(r),
                                                                   g_float(r)), r.getrandbits(32)))
        c.arg(slot)
        c.arg(context)
        c.note(slot=slot, context=s32(context), **info)


# --------------------------------------------------------------------------------------
def t_monster_matches_spell(ctx, env):
    """bool MonsterTargetMatchesSpell(W8MonsterInfo*, int spell_id)"""
    fn = ctx.fn(0x0053A300)
    for i in range(ctx.n(300)):
        r = ctx.rng('monmatchspell', i)
        c = ctx.case('monmatchspell.%d' % i, fn, conv='c', ret='b')
        w = World(env, c)
        locs, gids = presence_world(env, c, r, w, max_mon=4, max_grp=3)
        if not w.mons:
            w.add_mon(g_loc(r))
            locs = [s32(w.mons[0].get_u32(M_LOC))]
        t = rand_target(r, locs, gids, allow_char_neg=True, allow_null_item=True)
        caster = r.randrange(len(w.mons))
        kind, ichar, imon, igroup, item = t
        w.mons[caster].put(M_TARGET, slot_bytes(kind, ichar, imon, igroup,
                                                 (g_float(r), g_float(r), g_float(r)), 0))
        w.mons[caster].u32(M_ACTION_KIND, r.choice([-1, 0, 2, 3]))
        w.mons[caster].u32(M_ACTION_DETAIL, g_spell(r))
        w.emit(mon_gap=40)
        if item:
            put_item(env, c, r, 0, g_item_id(r, p_none=0.35))
            c.setp(env.mon(caster) + M_TARGET + 0x1c, env.item(0))
        put_presence_chars(env, c, r, target_char_slots(t))
        spell = g_spell(r)
        c.arg(env.mon(caster))
        c.arg(spell)
        c.note(spell=spell, tt=SPELL_TT[spell], kind=s32(kind), ichar=s32(ichar), imon=s32(imon),
               igroup=s32(igroup), item=int(item))


def t_cursor_for_state(ctx, env):
    """int GetTargetingCursorForState(int alternate)"""
    fn = ctx.fn(0x0053A3D0)
    modes = [-1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 100, 0x80000000, 0x7fffffff, 0x101]
    for i in range(ctx.n(150)):
        r = ctx.rng('cursorstate', i)
        c = ctx.case('cursorstate.%d' % i, fn, conv='c', ret='i')
        mode = modes[i % len(modes)] if i < 2 * len(modes) else r.choice(modes)
        alt = r.choice([0, 0, 1, 1, 2, -1, 0x100, 0x80000000])
        c.set(env.gx + GX_TMODE, p32(mode))
        c.arg(alt)
        c.note(mode=s32(mode), alternate=s32(alt))


def t_needs_explicit(ctx, env):
    """bool ActionNeedsExplicitTarget(int)"""
    fn = ctx.fn(0x0053A700)
    for i in range(ctx.n(250)):
        r = ctx.rng('explicittarget', i)
        c = ctx.case('explicittarget.%d' % i, fn, conv='c', ret='b')
        slot = r.randrange(8)
        spell = i % SPELL_COUNT if i < SPELL_COUNT else g_spell(r)
        camp = r.choice([0, 0, 1, 2, 0xff])
        auto = r.choice([0, 0, 1, 2, 0xff])
        c.set(env.row(slot) + X_SPELL_ID, p32(spell))
        c.set(env.gx + GX_CAMP, p8(camp))
        c.set(env.settings + SET_AUTOTARGET, p8(auto))
        c.arg(slot)
        c.note(slot=slot, spell=spell, tt=SPELL_TT[spell], camp=camp, auto=auto)


def t_spell_like_id(ctx, env):
    """unsigned int GetActionSpellLikeId(int, W8TargetingContext)"""
    fn = ctx.fn(0x0053A8D0)
    contexts = [(6, 4.0), (0, 1.5), (1, 1.5), (2, 1.0), (3, 1.0), (4, 1.0), (5, 0.6), (7, 1.0),
                (8, 0.6), (9, 0.3), (-1, 0.3)]
    for i in range(ctx.n(250)):
        r = ctx.rng('spelllikeid', i)
        c = ctx.case('spelllikeid.%d' % i, fn, conv='c', ret='i')
        slot = r.randrange(8)
        context = wpick(r, contexts)
        ctxv, info = put_context(env, c, r, slot, choose_safe=True, lb_null_p=0.0 if context == 7
                                 else 0.2)
        if context == 7:
            # an explicit dialogue context hands out the level block's selection_kind with a
            # null detail block: an item use there would dereference it (crash in both)
            sel = r.choice([-1, 0, 1, 2, 3, 4, 5, 6, 7, 7, 9, 10, 11])
            put_level_block(env, c, r, null_p=0.0, sel=sel)
            info['lb'] = 'dlg%d' % sel
        if context == 2 and ctxv != 2:
            put_shared_sources(env, c, r, info['spell_mode'])
        rowinfo = put_action_row(env, c, r, slot, spell_ids_valid=False)
        c.arg(slot)
        c.arg(context)
        c.note(slot=slot, context=context, **info)
        c.note(**rowinfo)


# --------------------------------------------------------------------------------------
def cand_bytes(r, state, reach, dist):
    b = Blob(rand_bytes(r, 0x1c))
    b.u32(0, g_loc(r))
    b.u32(4, state)
    b.u8(8, reach)
    b.f32(0x18, dist)
    return bytes(b)


def t_compare_candidates(ctx, env):
    """int CompareMonsterTargetCandidates(const void*, const void*) (qsort comparator)"""
    S0 = env.S[0]
    fn = ctx.fn(0x0053c920)
    states = [0, 0, 1, 2, 5, 0x0e, 0x11, 0x12, 0x13, 0x7fffffff, 0x80000000, M32, 0xfffffff0]
    dists = [0.0, -0.0, 1.0, 1.5, 250.0, 1e-45, 3.0e38, float('inf'), float('-inf'), -3.0]
    for i in range(ctx.n(300)):
        r = ctx.rng('comparecand', i)
        c = ctx.case('comparecand.%d' % i, fn, conv='c', ret='i')
        sa = r.choice(states) if r.random() < 0.6 else r.randint(0, 0x14)
        sb = sa if r.random() < 0.55 else (r.choice(states) if r.random() < 0.6 else r.randint(0, 0x14))
        ra = r.choice([0, 0, 1, 1, 2, 0xff])
        rb = ra if r.random() < 0.4 else r.choice([0, 0, 1, 1, 2, 0x80])
        da = r.choice(dists) if r.random() < 0.35 else f32r(r.uniform(0.0, 5000.0))
        x = r.random()
        if x < 0.3:
            db = da
        elif x < 0.38:
            db = float('nan')
        else:
            db = r.choice(dists) if r.random() < 0.35 else f32r(r.uniform(0.0, 5000.0))
        if r.random() < 0.06:
            da = float('nan')
        same = r.random() < 0.03
        c.set(S0 + CAND, cand_bytes(r, sa, ra, da) + bytes(4) + cand_bytes(r, sb, rb, db))
        c.arg(S0 + CAND)
        c.arg(S0 + CAND if same else S0 + CAND + 0x20)
        c.note(a='%x/%x/%r' % (sa, ra, da), b='%x/%x/%r' % (sb, rb, db), same=int(same))
        edges = []
        if sa >= 0x80000000 or sb >= 0x80000000:
            edges.append('state_unsigned')
        if math.isnan(da) or math.isnan(db):
            edges.append('nan_distance')
        if edges:
            c.note(edge=','.join(edges))


# --------------------------------------------------------------------------------------
def t_aim_wrappers(ctx, env):
    """AimByKind / AimAtCharacter / AimAtCharacterIndirect with context OUT_OF_COMBAT: AimAtTarget
    only copies the block into XChar[actor].target_out_of_combat (no highlight/redraw/mode path)."""
    fk = ctx.fn(0x00538620)   # void AimByKind(int actor, W8TargetKind, W8TargetingContext)
    fc = ctx.fn(0x00538670)   # void AimAtCharacter(int actor, int slot, W8TargetingContext)
    fi = ctx.fn(0x005386C0)   # void AimAtCharacterIndirect(int actor, int slot, W8TargetingContext)
    for tag, fn in (('aimbykind', fk), ('aimatchar', fc), ('aimatcharind', fi)):
        for i in range(ctx.n(60)):
            r = ctx.rng(tag, i)
            c = ctx.case('%s.%d' % (tag, i), fn, conv='c', ret='v')
            actor = r.randrange(8)
            if tag == 'aimbykind':
                val = r.choice([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, -1, 0x101])
                new = slot_bytes(val, -1, -1, -1)
            else:
                val = r.choice([0, 1, 2, 3, 4, 5, 6, 7, -1, 8, 100, 0x7fffffff])
                new = slot_bytes(1 if tag == 'aimatchar' else 9, val, -1, -1)
            if r.random() < 0.3:
                old = new
            else:
                old = slot_bytes(r.randint(0, 9), r.randint(-1, 7), r.choice([-1, g_loc(r)]),
                                 r.randint(-1, 50), (g_float(r), g_float(r), g_float(r)),
                                 r.choice([0, 0, r.getrandbits(32)]))
            c.set(env.row(actor) + X_T_OOC, old)
            c.arg(actor)
            c.arg(val)
            c.arg(0)
            c.cap(env.row(actor), XROW, 'row')
            c.note(actor=actor, value=s32(val), unchanged=int(old == new))


# --------------------------------------------------------------------------------------
SAFE_PENDING = [-1, 0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11]       # never USE_ITEM (item activation)
SAFE_PENDING_COMBAT = [-1, 2, 3, 4, 5, 6, 9, 10, 11]         # no enemy-needing repick


def t_apply_target(ctx, env):
    """ApplyTarget(W8CombatSlot*, bool) and the SetTargetToCharacter/SetTargetToGroup wrappers."""
    S0 = env.S[0]
    fa = ctx.fn(0x00538E00)
    fc = ctx.fn(0x00538d10)
    fg = ctx.fn(0x00538db0)
    for tag, fn, count in (('applytarget', fa, 250), ('settargetchar', fc, 150),
                           ('settargetgroup', fg, 150)):
        for i in range(ctx.n(count)):
            r = ctx.rng(tag, i)
            c = ctx.case('%s.%d' % (tag, i), fn, conv='c', ret='v')
            w = World(env, c)
            ng = r.choice([1, 2, 2, 3])
            gids = distinct_ids(r, ng, lambda rr: rr.choice([rr.randint(1, 400), rr.randint(1, 400), 0]))
            for gid in gids:
                w.add_group(gid, disp=r.choice([0, 1, 1, 2, 0xff]))
            # the target as the function sees it
            item = False
            if tag == 'settargetchar':
                kind = 1
                arg = r.randrange(8)
                tb = slot_bytes(1, arg, -1, -1)
            elif tag == 'settargetgroup':
                kind = 4
                arg = r.choice(gids) if r.random() < 0.9 else r.randint(401, 900)
                tb = slot_bytes(4, -1, -1, arg)
            else:
                kind = wpick(r, [(1, 4.0), (4, 4.0), (2, 1.0), (0, 1.0), (5, 0.7), (6, 1.0), (7, 0.8),
                                 (8, 0.4), (9, 1.0)])
                ichar = r.randrange(8) if kind in (1, 9) else r.choice([-1, r.randrange(8)])
                igroup = r.choice(gids) if kind == 4 else r.choice([-1, r.randint(1, 400)])
                pt = (g_float(r), g_float(r), g_float(r)) if kind == 6 else (0.0, 0.0, 0.0)
                tb = slot_bytes(kind, ichar, r.choice([-1, -1, g_loc(r)]), igroup, pt)
                item = kind == 7 and r.random() < 0.8
                arg = None
            group_absent = kind == 4 and tag == 'settargetgroup' and arg not in gids
            combat = r.random() < 0.25
            c.set(env.gx + GX_COMBAT, p8(r.choice([1, 1, 2]) if combat else 0))
            if combat:
                c.setp(env.combat, env.S[6] + CS)
            put_level_block(env, c, r, null_p=0.5)
            if item:
                put_item(env, c, r, 0, g_item_id(r, p_none=0.2))
                c.set(S0 + TGT, tb)
                c.setp(S0 + TGT + 0x1c, env.item(0))
            elif arg is None:
                c.set(S0 + TGT, tb)
            # party
            matches = []
            for s in range(8):
                occ, hp, hcond = put_participant(env, c, r, s, 0.75)
                match = (not group_absent) and r.random() < 0.45
                pending = r.choice(SAFE_PENDING_COMBAT if combat else SAFE_PENDING)
                b = Blob(rand_bytes(r, X_ACTION_KIND))
                b.u8(X_OCC, occ)
                b.u32(X_PENDING, pending)
                b.u32(X_MODES, g_spell(r) if pending == 7 or r.random() < 0.5 else r.randint(-1, 300))
                b.u32(X_PENDING_DETAIL + 4, 0)
                b.u32(X_ACTION_D1 + 4, 0)
                other = slot_bytes(r.choice([0, 1, 2, 3, 4, 6, 9]), r.randint(-1, 7),
                                   r.choice([-1, g_loc(r)]), r.choice([-1] + gids),
                                   (g_float(r), 0.0, 0.0))
                if other == tb:
                    other = slot_bytes(0, 99, 99, 99)
                b.put(X_T_OOC, tb if match else other)
                # the in-combat block is only compared in combat mode
                ic_match = (not combat) and (not group_absent) and r.random() < 0.3
                b.put(X_T_IC, tb if ic_match else slot_bytes(r.choice([0, 1, 3, 4]), r.randint(-1, 7),
                                                              -1, r.choice([-1] + gids)))
                if b[X_T_IC:X_T_IC + 0x20] == tb and not ic_match:
                    b.put(X_T_IC, slot_bytes(0, 98, 98, 98))
                b.u32(X_ACTION, r.choice([-1, 0, 1, 4, 5, 7]))
                b.u32(X_ACTION_D0, g_spell(r))
                c.set(env.row(s), bytes(b))
                if item and match:
                    c.setp(env.row(s) + X_T_OOC + 0x1c, env.item(0))
                if item and ic_match:
                    c.setp(env.row(s) + X_T_IC + 0x1c, env.item(0))
                put_char(env, c, r, s, hp=hp, hcond=hcond, turncoat=g_cond(r, 0.35, 0.15))
                if match:
                    matches.append(s)
            # monsters
            nm = 0 if r.random() < 0.08 else r.randint(1, 6)
            locs = distinct_ids(r, nm, g_loc)
            mon_match = []
            for k, loc in enumerate(locs):
                mi, m = w.add_mon(loc, disp=r.choice([0, 1, 1, 2, 0xff]))
                mm = (not group_absent) and (not item) and r.random() < 0.4
                m.put(M_TARGET, tb if mm else slot_bytes(r.choice([0, 1, 3, 4]), r.randint(-1, 7),
                                                         r.choice([-1, loc]), r.choice([-1] + gids)))
                if bytes(m[M_TARGET:M_TARGET + 0x20]) == tb and not mm:
                    m.put(M_TARGET, slot_bytes(0, 97, 97, 97))
                ak = r.choice([-1, 0, 0, 1, 2, 2, 3, 4, 5, 8, 9])
                m.u32(M_ACTION_KIND, ak)
                m.u32(M_ACTION_DETAIL, g_spell(r) if ak == 2 or r.random() < 0.5 else r.randint(-5, 400))
                if mm:
                    mon_match.append(k)
            w.emit(mon_gap=24)
            in_combat = r.choice([0, 0, 1, 1, 1, 0x100, 2, 0xff])
            if arg is None:
                c.arg(S0 + TGT)
            else:
                c.arg(arg)
            c.arg(in_combat)
            ign = []
            for s in range(8):
                ign += [s * XROW + X_PENDING_DETAIL + 4, s * XROW + X_T_OOC + 0x1c,
                        s * XROW + X_ACTION_D1 + 4, s * XROW + X_T_IC + 0x1c]
            c.cap(env.row(0), 8 * XROW, 'xchar', ignore=ign)
            if nm:
                c.cap(env.S[1], nm * MSTRIDE, 'monsters',
                      ignore=[k * MSTRIDE + M_TARGET + 0x1c for k in range(nm)])
            if combat:
                c.cap(env.S[6] + CS + CS_CHARS, 8 * CS_ROW, 'combat_rows')
            c.note(kind=kind, arg=arg, combat=int(combat), in_combat=in_combat,
                   matches=''.join(map(str, matches)), mon_matches=''.join(map(str, mon_match)),
                   monsters=nm, groups=len(gids))


# --------------------------------------------------------------------------------------
def t_resolve_point(ctx, env):
    """bool ResolveTargetPoint(W8CombatSlot*, bool sight_probe)"""
    S0 = env.S[0]
    S6 = env.S[6]
    fn = ctx.fn(0x0053c630)
    for i in range(ctx.n(200)):
        r = ctx.rng('resolvepoint', i)
        c = ctx.case('resolvepoint.%d' % i, fn, conv='c', ret='b')
        kind = wpick(r, [(3, 5.5), (1, 1.5), (2, 1.0), (0, 0.5), (4, 0.4), (5, 0.3), (6, 0.5),
                         (7, 0.3), (9, 0.4), (-1, 0.2)])
        if kind in (1, 2):
            sight = r.choice([1, 1, 2, 0xff, 0x101])     # camera path (probe off) is not tested
        else:
            sight = r.choice([0, 0, 1, 1, 0x100, 2])
        w = World(env, c)
        nm = r.randint(1, 4)
        locs = distinct_ids(r, nm, g_loc)
        for k, loc in enumerate(locs):
            w.add_mon(loc)
            h = r.choice([0.0, 1.5, -2.25, 100.0, f32r(r.uniform(-500.0, 500.0))])
            if r.random() < 0.03:
                h = float('nan')
            w.set_p3d(k, radius=g_float(r), pos=(g_float(r), g_float(r), g_float(r)), height=h)
        w.emit(group_list=False, mon_gap=8)
        nav = (g_float(r), g_float(r), g_float(r))
        c.setp(env.world, S6 + NAV)
        c.set(S6 + NAV + NAV_POS, pf(nav[0]) + pf(nav[1]) + pf(nav[2]))
        imon = r.choice([s32(x) for x in locs]) if kind == 3 else r.choice([-1, g_loc(r)])
        c.set(S0 + TGT, slot_bytes(kind, r.randint(-1, 7), imon, r.randint(-1, 50),
                                   (g_float(r), g_float(r), g_float(r)), 0))
        c.arg(S0 + TGT)
        c.arg(sight)
        c.cap(S0 + TGT, 0x20, 'target', floats=[0x10, 0x14, 0x18])
        c.note(kind=kind, sight=sight, imon=imon)


def pyth_offsets(r, scale):
    """Integer offset vectors with an integer length."""
    base = r.choice([((3, 4, 0), 5), ((0, 0, 1), 1), ((2, 3, 6), 7), ((1, 4, 8), 9), ((2, 6, 9), 11),
                     ((4, 4, 7), 9), ((6, 6, 7), 11), ((0, 5, 12), 13), ((8, 0, 15), 17)])
    (x, y, z), d = base
    v = [x * scale, y * scale, z * scale]
    perm = r.choice([(0, 1, 2), (1, 2, 0), (2, 0, 1), (0, 2, 1)])
    v = [v[p] for p in perm]
    v = [-a if r.random() < 0.5 else a for a in v]
    return v, d * scale


def t_collect_radius(ctx, env):
    """void CollectMonstersWithinRadius(const vec3*, const vec3*, W8GrowableVector<int>*, float radius,
    char side, char highlighting). Highlighting is always on (its low byte nonzero), so no
    line-of-sight trace runs; out-of-range monsters get their rep colour cleared."""
    S0 = env.S[0]
    S7 = env.S[7]
    fn = ctx.fn(0x00539e70)
    for i in range(ctx.n(220)):
        r = ctx.rng('collectradius', i)
        c = ctx.case('collectradius.%d' % i, fn, conv='c', ret='v')
        w = World(env, c)
        centre = [float(r.randint(-4000, 4000)) for _ in range(3)]
        n = r.choice([0, 1, 2, 3, 4, 4, 5, 6])
        x = r.random()
        if x < 0.06:
            radius = r.choice([0.0, -0.0])
        elif x < 0.09:
            radius = float('nan')
        elif x < 0.13:
            radius = r.choice([-5.0, float('inf'), 1e-30])
        else:
            radius = float(r.choice([10, 25, 50, 100, 250, 500, 1000, r.randint(1, 3000)]))
        side = r.choice([0, 1, 2, 3, 3, 3, 3, 0xff, 0x103, 0x101])
        hl = r.choice([1, 1, 1, 2, 0xff, 0x101])
        edges = []
        species_used = r.sample(SPECIES[:4], 2)
        for sp in species_used:
            w.records[sp] = r.choice([0, 0, 0, 1, 2])
        finite = math.isfinite(radius) and radius > 0
        for k in range(n):
            mr = float(r.choice([0, 0, 5, 10, 32, 50, r.randint(0, 100)]))
            mode = r.random()
            if finite and mode < 0.05:
                # on the x axis exactly at radius + monster radius, or one float step off it:
                # retail squares/roots in 80-bit registers (exact here), the port may round
                bound = f32r(radius + mr)
                step = r.choice([0, 0, -1, 1])
                bits = struct.unpack('<I', struct.pack('<f', bound))[0] + step
                dx = struct.unpack('<f', struct.pack('<I', bits))[0]
                off = [dx if r.random() < 0.5 else -dx, 0.0, 0.0]
                edges.append('fp_boundary')
            elif finite and mode < 0.6:
                # integer vector with an integer length right on / just inside / outside the
                # radius: every intermediate value is exact in float and in 80 bits
                want = radius + mr + r.choice([0, 0, 0, -1, 1, -7, 9, -50, 80])
                unit, ud = pyth_offsets(r, 1)
                s = max(1, int(round(want / ud)))
                if ud * s > 4000:
                    s = max(1, 4000 // ud)
                off = [float(a * s) for a in unit]
            else:
                off, _ = pyth_offsets(r, r.randint(1, 120))
                off = [float(a) for a in off]
            pos = [centre[j] + off[j] for j in range(3)]
            rep = Blob(R_LEN)
            rep.u8(R_CYCLE, r.choice([0, 0, 1, 3, 7, CYCLE_DIE, 0x14, 0x16, 0xff]))
            for j in range(4):
                rep.f32(R_COLOUR + 4 * j, r.choice([1.0, 0.5, 0.25, 2.0]))
            sp = r.choice(species_used)
            loc = g_loc(r)
            w.add_mon(loc, species=sp, active=g_bool(r, 0.85, 0.05),
                      hp=r.choice([0, 1, 30, 200, 0x80000000]) if r.random() < 0.2 else r.randint(1, 300),
                      cond18=g_cond(r, 0.15), disp=r.choice([0, 1, 1, 2, 3, 0xff]))
            w.set_p3d(k, radius=mr, pos=pos, rep=rep)
        w.emit(group_list=False)
        pre = r.choice([0, 0, 0, 1, 3])
        c.set(S0 + CENTRE, pf(centre[0]) + pf(centre[1]) + pf(centre[2]))
        c.set(S0 + EYE, pf(g_float(r)) + pf(g_float(r)) + pf(g_float(r)))
        c.set(S0 + FOUND + 4, p32(pre) + p32(32))
        c.setp(S0 + FOUND + 0xc, S7)
        if pre:
            c.set(S7, b''.join(p32(r.randint(1, 5000)) for _ in range(pre)))
        c.arg(S0 + CENTRE)
        c.arg(S0 + EYE)
        c.arg(S0 + FOUND)
        c.arg(F32(radius))
        c.arg(side)
        c.arg(hl)
        c.cap(S0 + FOUND, 0x10, 'found', ignore=[0xc])
        c.cap(S7, 0x80, 'found_data')
        if n:
            c.cap(env.S[4], n * RSTRIDE, 'reps',
                  floats=[k * RSTRIDE + R_COLOUR + 4 * j for k in range(n) for j in range(4)])
        c.note(radius=radius, side=side, hl=hl, monsters=n, pre=pre)
        if edges:
            c.note(edge=','.join(sorted(set(edges))))


def t_tint(ctx, env):
    """void TintHighlightedMonster(W8Monster*, W8TargetHighlight) - tints 0..2 only (others leave the
    colour uninitialised in retail)."""
    fn = ctx.fn(0x00539480)
    for i in range(ctx.n(40)):
        r = ctx.rng('tint', i)
        c = ctx.case('tint.%d' % i, fn, conv='c', ret='v')
        cycle = r.choice([0, 0, 1, 5, 0x14, CYCLE_DIE, 0x16, 0xff, 0x7f])
        tint = i % 3
        null = r.random() < 0.06
        c.setp(env.p3d(0) + P_REP, env.rep(0))
        c.set(env.rep(0) + R_COLOUR, b''.join(pf(r.choice([0.5, 2.0, -1.0, 0.125])) for _ in range(4)))
        c.set(env.rep(0) + R_CYCLE, p8(cycle))
        c.arg(0 if null else env.p3d(0))
        c.arg(tint)
        c.cap(env.rep(0) + R_COLOUR, 0x10, 'colour', floats=[0, 4, 8, 12])
        c.note(tint=tint, cycle=cycle, null=int(null))


# --------------------------------------------------------------------------------------
def t_source_in_range(ctx, env):
    """bool IsTargetSourceInRangeOfGroup(const W8TargetSource*, W8MonsterGroup*, W8TargetingContext).
    Monster source: range from its pending action (attack 0 of its record, spell table, special,
    protect), members measured monster-to-monster on scratch W8Monster objects (positions and
    alternate radii, integer distances placed around the range). A character source measures
    members to the camera, so it only runs with an empty group (range lookup + loop exit)."""
    S0 = env.S[0]
    S2 = env.S[2]
    fn = ctx.fn(0x00537780)
    il = S2 + 0x1000
    il_data = S2 + 0x1100
    for i in range(ctx.n(200)):
        r = ctx.rng('srcinrange', i)
        c = ctx.case('srcinrange.%d' % i, fn, conv='c', ret='b')
        w = World(env, c)
        x = r.random()
        skind = 2 if x < 0.84 else (1 if x < 0.93 else r.choice([0, 3, 4, -1]))
        edges = []
        # source monster (always present: the char/other kinds just ignore it)
        ak = r.choice([0, 0, 0, 0, 2, 2, 2, 3, 8, 1, 4, 9, -1])
        spell = g_spell(r)
        has_attack = 1 if r.random() < 0.93 else 0
        rng_byte = r.choice([0, 1, 2, 3, 0, 1, 2, 3, 0xff, 4])
        if ak == 0:
            rc = rng_byte if rng_byte <= 3 else None
        elif ak == 2:
            rc = SPELL_RNG[spell]
        elif ak == 3:
            rc = 2
        elif ak == 8:
            rc = 0
        else:
            rc = -1
        maxd = RANGE_STEPS.get(rc, 0) * WORLD_SCALE if rc is not None else 0.0
        src_loc = g_loc(r)
        sp = SPECIES[0]
        si, sm = w.add_mon(src_loc, species=sp)
        sm.u32(M_ACTION_KIND, ak)
        sm.u32(M_ACTION_DETAIL, spell)
        w.records[sp] = 0
        src_pos = [float(r.randint(-4000, 4000)) for _ in range(3)]
        src_ar = float(r.choice([0, 0, 10, 25, 50, 100]))
        w.set_p3d(si, pos=src_pos, alt_radius=src_ar)
        # members
        n = 0 if (skind != 2 or r.random() < 0.08) else r.randint(1, 5)
        member_locs = []
        used = {src_loc}
        for k in range(n):
            if r.random() < 0.08:
                member_locs.append(src_loc)        # the source itself is in the group
                continue
            loc = g_loc(r)
            while loc in used:
                loc = g_loc(r)
            used.add(loc)
            mi, mm = w.add_mon(loc)
            m_ar = float(r.choice([0, 0, 10, 25, 50, 100]))
            delta = r.choice([0, 0, -1, 1, -5, 5, -64, 64, -1000, 3000, None])
            if delta is None:
                want = r.randint(0, int(src_ar + m_ar) + 1)  # overlapping: clamped to 0
            else:
                want = maxd + src_ar + m_ar + delta
            if want <= 0:
                want = 0
            if r.random() < 0.5:
                unit, ud = [1, 0, 0], 1
                perm = r.choice([(0, 1, 2), (1, 2, 0), (2, 0, 1)])
                unit = [unit[p] for p in perm]
            else:
                unit, ud = pyth_offsets(r, 1)
            s = int(round(want / ud))
            off = [float(a * s) for a in unit]
            length = ud * s
            if length > 4096 and abs(length - (maxd + src_ar + m_ar)) <= 1:
                edges.append('fp_boundary')
            w.set_p3d(mi, pos=[src_pos[j] + off[j] for j in range(3)], alt_radius=m_ar)
            member_locs.append(loc)
        w.emit(group_list=False, mon_gap=24)
        c.set(env.rec(0) + REC_ATTACK0, p8(has_attack) + bytes(2) + p8(rng_byte))
        # group with the member IList
        g = Blob(G_LEN)
        g.u32(G_ID, r.randint(1, 400))
        g.u32(G_COUNT, n)
        g.u8(G_ACTIVE, 1)
        emit_sparse(c, env.grp(0), g, 48)
        c.setp(env.grp(0) + 8, il)
        c.setp(il, il_data)
        c.set(il + 4, p32(max(n, 10)) + p32(n))
        if n:
            c.set(il_data, b''.join(p32(v) for v in member_locs))
        # source
        context = r.choice([0, 1, 1, 6, 3])
        if skind == 1:
            slot = r.randrange(8)
            context = 1
            action = r.choice([-1, 0, 0, 2, 4, 5, 6, 7, 7])
            c.set(env.row(slot) + X_ACTION, p32(action) + p32(g_spell(r)))
            occ, hp, hcond = put_participant(env, c, r, slot, 0.85)
            put_char(env, c, r, slot, occ=occ, hp=hp, hcond=hcond)
            src = source_bytes(r, 1, slot, r.choice([-1, src_loc]), 0, 0)
        else:
            src = source_bytes(r, skind, r.choice([-1, r.randrange(8)]),
                               src_loc if skind == 2 else r.choice([-1, src_loc]), 0, 0)
        c.set(S0 + SRC, src)
        c.arg(S0 + SRC)
        c.arg(env.grp(0))
        c.arg(context)
        c.note(src_kind=skind, action=ak, range=rc, maxd=maxd, members=n, has_attack=has_attack,
               rng_byte=rng_byte, src_ar=src_ar)
        if edges:
            c.note(edge=','.join(sorted(set(edges))))
