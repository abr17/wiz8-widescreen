"""Targeting.cpp lines 1701-3500 (src/wiz8/local_code/Targeting.cpp, retail 0x00536570..0x0053d2a0
part): targeting predicates, pickers and party/target bookkeeping.

How the cases are built (everything is restored by the core after each case)
  * Fake monster world in scratch, the scheme combat_range.py uses: W8MonsterInfo blocks in S0
    (stride 0x430: location id, group id, species, fActive, fInCombat, ubDisposition,
    hp_current, uiCondition[18], highest_condition, party_threat sight state and los_flags),
    W8Monster stubs in S1 (navigator radius +0x9c, navigator position +0x118, alternate radius
    +0x18c, height offset +0x190, m_pRep +0x1d8), minimal W8MonsterRecord blocks in S2 (only
    untargetable +0x24a; nothing else on the tested paths reads the record) wired through
    gXStatus.monster_record_cache[species] for EVERY species used (a missing entry would load
    the record from disk), PList/IList stubs in S3 for gXStatus.plsMonsterList,
    plsMonsterGroupList, a source monster's plsVisMonToMon and W8MonsterGroup blocks (stride
    0x200; the group's own IList sits inside its unused group_state bytes at +0x30, data at
    +0x40), plsUnbornMonsterList/plsMonsterGroupEncounterList nulled, W8CombatState in S4,
    item instances / target and source blocks / vectors in S5, W8MonsterRep stubs in S6
    (highlight_mask +0x5bc; icon_count, objects[], spell_icons, linked_runtime_objects zero so
    UpdateAttachedObjects returns at once), W8GrowableVector<int> stubs in S7 (capacity always
    large enough that Add never reallocates the scratch array).
  * Party slot: the acting character from the corpus (setb, unmodified), its XChar row 0..0xf1
    written whole (fOccupied, pending/in-combat action, attack_mode[0], spell id, the three
    detail blocks whose item pointers go to scratch items or the character's own non-empty
    equipment, the five target blocks), W8HandAttack heads + EquippedItem[6/7] kept valid,
    g_status.formation, party_facing, the camera position (g_gd_camera->m_position),
    g_startup_world collision/alternate/navigator radius, gXStatus fCombatMode/fSpellCastMode/
    fItemSelectMode/iTargetingMode/fCampMode, g_settings autotarget_spells/autoswap_weapons.
  * W8_TARGETING_CONTEXT_CURRENT is pinned in every case that resolves it: g_level_block
    selection_kind/pending_action/selection_settled, g_current_screen_state.id and
    g_status.selected_character, so it resolves to OUT_OF_COMBAT/IN_COMBAT/SPELL/ITEM only
    (SHARED reads UI selection state; DIALOGUE with USE_ITEM hands out a null detail block).
    The two pure context functions additionally get every screen/selection/bool-byte
    combination including DIALOGUE, SHARED and a null g_level_block.
  * Databases: Items.dbs spell ids (+0x63), equip classes 16/21/22 (ItemClassNormalizesTarget)
    and binds_on_equip from PATCH.001 (tables copied from pc_item_b.py), SpellTables target
    types (copied from combat_range.py), MONSTERS.DBS species 0..594.
  * Float angles: positions are put at mid-degree headings (k + 0.2..0.8 degrees) where the
    code truncates degrees, so 80-bit vs float rounding cannot move a bucket; a few cases
    with axis-aligned (dz == 0) or tied buckets are labelled note(axis=1)/note(tie=1).

Tested (retail address, function, cases):
  0x0053C270 CanPartySlotParticipate            200  fOccupied bytes 0/1/2/0x80/0xff, hp incl. 0x80000000/
                                                     0xffffffff, highest_condition around 0x12 incl. values
                                                     negative as int (retail JAE unsigned; port enum compare)
  0x0053C2C0 IsDeadCharacterTargetable          250  hp unsigned (incl. "negative"), uiCondition[18]/[19]
                                                     incl. 0x80000000/0xffffffff (retail SBB unsigned)
  0x0053bc90 GetCombatActionContext             250  every screen id / selection kind / settled byte /
                                                     selected slot / mode byte combination, NULL
                                                     g_level_block, bool bytes 2/0x80/0xff, slot ids -1/8/100
  0x0053ba20 GetValidatedTargetingContext       250  same + contexts 0..9, -1, 100, INT_MIN (asserts 0xc87)
  0x00539b70 TargetInRangeAndArcs               400  distance on the floor(d - bonus - radius) <= 12500 edge,
                                                     both pi/4 arc edges, 2*pi wraps, dz == 0 heading branch,
                                                     zero / huge (1e20) distance, NaN position or bonus,
                                                     negative bonus/radius
  0x00539ca0 CollectConeMonsterTargets          300  character / monster (mon-to-mon records, sight flags
                                                     0..7) / indirect / empty sources, the five filters
                                                     (fActive, hp, uiCondition[18], untargetable, disposition
                                                     incl. 3 and 0x103/0x201), range and arc edges, prefilled
                                                     found vector; iterator global captured
  0x0053a770 ItemUseNeedsTarget                 300  backpack / equipment / party-pool items (incl. asserting
                                                     slot indexes 8..13), every spell target type, normalizing
                                                     potions/food/drink, fCampMode and autotarget bytes
  0x00536ad0 CanTargetMonster                   400  live/dead/inactive monsters, camp-mode pick, every
                                                     action need (group need through IsSlotInRangeOfGroup),
                                                     untargetable records, allow_single_target 0/1
  0x00536d60 CanTargetMonsterGroup              300  incl. groups outside the group list and empty groups
  0x0053d010 SpellHasAnyValidTarget             400  enemy (autotarget bytes, monster sweep), group sweep
                                                     (members_active bytes), raise-dead party sweep, other types
  0x0053cdf0 SlotHasAnyValidTarget              300  attack / spell / item / protect / other actions, settled
                                                     byte 0/1/2/0xff, combat-state dead flags
  0x00536f60 TargetIsInPlay                     300  every target kind, hands 0..2, contexts 0..9 (8/9 assert
                                                     and resolve to IN_COMBAT, 7 = dialogue: null target)
  0x00537ed0 PickNextTargetableGroup            250  picked_group -1 / known / unknown (reset to -1 captured),
                                                     0..4 groups
  0x005383e0 SelectNextGroupMemberByAngle       250  0..6 candidates plus non-candidate monsters, current -1 /
                                                     listed / unlisted
  0x00538280 PickNextTargetableGroupMember      250  highlighted_member -1 / member / non-member
  0x0053c990 ChooseFallbackMonsterTarget        200  each gate failing first with weapons present, all gates
                                                     passing with an empty weapon set (-1 in both)
  0x0053cd60 ReconcilePartyEquipmentAfterCombat 200  per-slot gates incl. highest_condition 0x0c/0x0d/0x0e and
                                                     negative-as-int values, bool bytes; all 8 characters,
                                                     XChar rows and manager entries captured
  0x005387f0 AimAtTarget                        120  OUT_OF_COMBAT only: equal blocks, one field changed,
                                                     -0.0 vs +0.0 (copied), identical NaN bits (not copied)
  0x0053AEB0 ClearPartySlotMonsterHighlights    200  slots 0..7 and 8/9/31/32/33/39/0xffffffff/0x80000000,
                                                     null p3D, fActive bytes; rep masks captured
  total 5120
  Edge values outside the domains (bool bytes 2/0x80/0xff, conditions/hp negative as int) are labelled
  note(edge='bool_byte'|'cond_negative'|'hp_negative'): a difference only there points at a signed
  enum compare or bool normalisation in the port.

Skipped:
  0x0053AF40 SelectSpellCastingPartySlot   - UI: AimAtTarget(SHARED) redraw path, SetTargetingMode
                                             (cursor, target cone, world pause), marker refresh;
                                             its logic part ClearPartySlotMonsterHighlights is tested
  0x0053A830 CommitSelectedSpellTarget     - copies the shared target and restarts the portrait
                                             breathing animation (StartBreathCycle timers)
  0x0053A930 RefreshCombatTargetHighlights - render highlights: PopulateSpellTargetMarkers on live
                                             positions, SetMonsterHighlight/SetGroupHighlight attach
                                             TriRed marker items to the world
  0x0053B310 RefreshSpellTargetHighlightsAtRange - camera forward point + highlight colours
  0x0053B480 HighlightSpellTargetsAtCachedPosition - highlight colours via spell marker sweep
  0x0053B660 PopulateTargetMarkerForCurrentAction - not in the port map (inlined)
  0x0053B160 ClearTargetMarker             - clears a vector + party UI refresh request
  0x0053B170 RefreshTargetMarker           - world cursor position (input) + marker sweep
  0x00536570 RepickActionTarget            - AimAtTarget in combat contexts (redraw requests,
                                             highlight markers, targeting mode), PostCharacterNotice,
                                             ChooseMonsterTarget weapon swaps
  0x00538140 PickNextTargetableMonster     - not in the port map (inlined); its parts
                                             (CanTargetMonster + SelectNextGroupMemberByAngle) are tested
  0x00537b00 AimAtMonsterGroupMember       - highlight colours, PointCameraAtCombatTarget, breath cycle
  0x00537D20 CycleToNextTarget             - input handler: camera pointing, breath cycle, AimAtTarget
                                             UI path; pickers tested separately
  0x0053bf80 RefreshAllPartyTargets        - drives RefreshCombatTargetHighlights/RepickActionTarget/
                                             AimAtTarget(UI) for every slot
  0x005398D0 RefreshMonsterTargetCounts    - camera projection of animation bounds (ShowTargetMarker)
                                             + party redraw
  0x0053A060 IsMonsterVisibleWithinDistance - g_world->camera->project + animation-bounds virtual
  0x0053A1D0 AnyMonsterVisible             - same (far clip, camera projection)
  0x0053B1D0 UpdateTargetMarkerHighlight   - octree line of sight + highlight colour
  0x00538510 HighlightPickedGroupMember    - highlight colour only; its picker
                                             PickNextTargetableGroupMember is tested
  0x005392e0 ModifyGroupColor              - highlight colour (render) + debug message
  0x00539a30 SourceCanSeeMonster           - not in the port map (inlined); covered through
                                             CollectConeMonsterTargets (character and monster sources)
  0x0053a440 ConfigureSpellTargetFilter    - UI: cursor, target cone, world pause, camera
  0x0053b050 ClearSlotTargeting            - UI: cursor, target cone, world pause, highlights
  0x0053c130 UpdateSlotMonsterHighlights   - highlight colours + party redraw
  (the tail of 0x00537780 IsTargetSourceInRangeOfGroup at lines 1701-1719 belongs to the
   function annotated at line 1662, outside this range; it runs inside CanTargetMonsterGroup,
   CanTargetMonster and PickNextTargetableGroup here)

Paths deliberately not reached
  * AimAtTarget with any context but OUT_OF_COMBAT (ClearTargetHighlights on live monsters,
    RefreshCombatTargetHighlights, RequestPartySlotRedraw, SetTargetingMode cursor/cone).
  * ChooseFallbackMonsterTarget / ReconcilePartyEquipmentAfterCombat past SwapWeaponSetSlots:
    a slot that passes every gate has an empty weapon set (SwapWeaponSetSlots returns false
    with no side effect); slots that fail a gate keep real weapons, so a port that passes a
    gate retail refuses swaps weapons and shows up in the character capture.
  * notify_failure = 1 (CanTargetMonster): QueueCharacterEvent allocates in the live queue.
  * PLACE targets whose RADIUS/POINT spell is within range (TargetIsInPlay): octree trace;
    such points are put beyond 25000 units or the action is restricted to other spells.
  * CollectConeMonsterTargets with an indirect/empty source reaching SourceCanSeeMonster
    (HasLineOfSightFromPoint traces the live octree): every monster fails an earlier filter.
  * Non-finite or huge angles (NormalizeAngle loops forever in retail).
"""
import math
import struct

from w8diff.api import Blob, F32

MAX_OPS = 96

# ---------------------------------------------------------------- layouts (layout.ps1 + retail asm)
CHAR = 0x1862
C_IN_PARTY = 0x4
C_COND = 0xa01                       # uiCondition[20]
C_COND18 = C_COND + 18 * 4           # 0xa49 (reachable when down / DEAD)
C_COND19 = C_COND + 19 * 4           # 0xa4d (beyond reach / MISSING)
C_HIGHEST = 0xb01
C_HP = 0xb11
C_EQUIP = 0xf5d                      # W8ItemInstance[12], iItemNo +0, bind_announced +0xa, bound +0xb
ITEM = 0xc
C_PRIMARY = C_EQUIP + 6 * ITEM
C_BACKPACK = 0x1029                  # W8ItemInstance[8]
C_HAND = 0x1149                      # W8HandAttack[2]: uiHolds +0, in_play +4
HAND_STEP = 0x5b
C_OOF = 0x17b5                       # bonus.out_of_formation
IT_BOUND = 0xb

ST_XCHAR = 0x8
ST_SELECTED = 0x1d
ST_POOL = 0x21                       # party_item_pool[500]
ST_FACING = 0x18d0
ST_FORMATION = 0x23a1
FORM_SIZE = 0x84
FORM_POS = 0x14

ROW = 0x106                          # W8PartySlotRow
R_PENDING = 0x01
R_MODE0 = 0x05
R_PDETAIL = 0x15
R_TARGET_OOC = 0x1d
R_ACTION = 0x3d
R_ADETAIL0 = 0x41
R_ADETAIL1 = 0x45
R_SPELL = 0x75
R_SDETAIL = 0x79
R_IDETAIL = 0xa1
R_ITEM_ORIGIN = 0xcd                 # u8 origin, u16 slot
ROW_USED = 0xf1
R_ITEM_ACTION = 0xf5                 # item_action_pending
R_SWAP = 0x105                       # weapon_swap_pending
ROW_TARGETS = (0x1d, 0x4d, 0x81, 0xa9, 0xd1)   # out of combat, in combat, spell, item, breath
ITEM_PTRS = (0x19, 0x49, 0xa5)                  # item_use.item of the three detail blocks

X_ENTRY = 0x118                      # W8MonsterManagerEntry
X_SWAPPING = 0x113                   # item_swap_in_progress
X_COMBAT = 0x8dc                     # fCombatMode, fSpellCastMode, fItemSelectMode
X_CAMP = 0x8e3
X_MONLIST = 0x8f5                    # plsMonsterList, plsMonsterGroupList
X_GROUPLIST = 0x8f9
X_UNBORN = 0x901                     # plsUnbornMonsterList, plsMonsterGroupEncounterList (0x905)
X_TARGETING = 0x92f
X_PICKED_GROUP = 0x9ff
X_RECCACHE = 0xa0f

SET_AUTOSWAP = 0x4d
SET_AUTOTARGET = 0x4e

CS_SIZE = 0xa64
CS_EXEC = 0x0                        # execution_active (byte)
CS_ROUND = 0x4
CS_CHARS = 0x18
CS_ROW = 0xd4
CS_PHASE = 0x0
CS_DEAD = 0x34
CS_BERSERK = 0x80
CS_ENGAGED = 0xa54

MI_LOC = 0x0
MI_GROUP = 0x4
MI_SPECIES = 0x8
MI_P3D = 0xc
MI_ACTIVE = 0x14
MI_INCOMBAT = 0x15
MI_DISP = 0x16
MI_HP = 0x2b
MI_COND18 = 0x57 + 18 * 4            # 0x9f
MI_HIGHEST = 0x107
MI_PT_SIGHT = 0x28a
MI_PT_LOS = 0x28b                    # party_threat.los_flags[2]
MI_VISLIST = 0x2b6
MI_STRIDE = 0x430

VR_SIGHT = 0x4
VR_LOS = 0x5
VR_CANSEE = 0xb
VR_LINE = 0x28
VR_STRIDE = 0x34

M3_NAVRADIUS = 0x9c                  # W8Navigator::radius
M3_POS = 0x118
M3_RADIUS = 0x18c                    # movement.alternate_radius
M3_HEIGHT = 0x190
M3_REP = 0x1d8                       # W8Monster::m_pRep
P3D_STRIDE = 0x200
REP_MASK = 0x5bc                     # W8MonsterRep::highlight_mask
REP_STRIDE = 0x700                   # > sizeof(W8MonsterRep) 0x628 and objects[32..39]

MR_UNTARGETABLE = 0x24a
REC_STRIDE = 0x300

G_ID = 0x0
G_COUNT = 0x4
G_MONSTERS = 0x8                     # W8IList*
G_SPECIES = 0x18
G_ACTIVE = 0x28
G_ILIST = 0x30                       # IList header inside the unused group_state bytes
G_IDATA = 0x40
G_HIGHLIGHT = 0x9b
GROUP_STRIDE = 0x200                 # > sizeof(W8MonsterGroup) 0x12b

CAM_POS = 0x8c                       # GDCamera::m_position
NAV_RADIUS = 0x84                    # W8Navigator::radius of g_startup_world
NAV_COLL = 0x170                     # movement.collision_radius, alternate_radius
LVL_KIND = 0x2f0                     # selection_kind, pending_action, selection_settled
NPC_TARGET = 0xf8                    # W8NpcInteractionState::target_location_id

# scratch layout
L_MON = 0x0
L_VIS = 0x100
L_VISREC = 0x200
L_GROUP = 0x800
L_GROUPS = 0x1000
S5_ITEMS = 0x0
S5_TARGET = 0x300
S5_SOURCE = 0x400
S5_VEC_A = 0x500
S5_VEC_B = 0x510
S5_ITEMPTR = 0x600
VEC_DATA = 0x100

WORLD_HEIGHT = 1000.0
BANDS = (1000.0, 2000.0, 12500.0, 25000.0)
N_ITEMS = 819
N_MONSTERS = 595

# ---------------------------------------------------------------- databases
# SpellTables target types (W8SpellTargetType) of spells 0..149 (combat_range.py)
SPELL_TARGET = [0, 3, 2, 3, 3, 3, 1, 5, 2, 3, 3, 3, 4, 1, 4, 6, 1, 2, 10, 1, 2, 1, 6, 9, 4, 5, 2, 1, 5, 4,
                6, 5, 2, 2, 1, 1, 6, 4, 8, 10, 2, 3, 6, 5, 2, 2, 4, 5, 6, 5, 3, 1, 5, 2, 1, 6, 2, 6, 1, 2,
                8, 1, 2, 5, 2, 1, 3, 7, 2, 6, 3, 4, 2, 0, 1, 0, 6, 7, 5, 3, 6, 6, 3, 5, 3, 7, 5, 6, 1, 3,
                7, 3, 3, 6, 7, 7, 7, 7, 7, 7, 1, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 7, 6, 5,
                1, 4, 4, 8, 4, 4, 4, 4, 4, 7, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
TYPE = {t: [s for s in range(150) if SPELL_TARGET[s] == t] for t in range(11)}
SPELL_RESURRECTION = 88              # ALLY spell answered as CHARACTER_INDIRECT

# Items.dbs (PATCH.001) spell_id (+0x063) per record, from pc_item_b.py
ITEM_SPELL = bytes.fromhex(
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
# equip_class 16/21/22 (ItemClassNormalizesTarget: ALLY spells become CASTER)
NORMALIZING_ITEMS = frozenset([46, 47, 69, 260, 264, 317, 329, 334, 335, 336, 337, 338, 339, 340, 341,
                               344, 345, 346, 347, 348, 410, 411, 412, 413, 414, 416, 417, 418, 474, 488,
                               597, 598, 669, 671, 712, 713, 726, 741, 742, 743, 744, 804])
# binds_on_equip (+0x08c) != 0
BINDING_ITEMS = frozenset([4, 5, 15, 29, 33, 43, 48, 71, 73, 74, 85, 86, 89, 145, 149, 160, 168, 179,
                           195, 205, 208, 217, 228, 234, 238, 245, 277, 291, 305, 313, 463, 469, 660,
                           674, 755, 775, 781, 791, 798, 818])

SPELL_ITEMS = [i for i in range(N_ITEMS) if ITEM_SPELL[i]]
PLAIN_ITEMS = [i for i in range(N_ITEMS) if not ITEM_SPELL[i]]
ITEMS_BY_TYPE = {t: [i for i in SPELL_ITEMS if SPELL_TARGET[ITEM_SPELL[i]] == t] for t in range(11)}
ALLY_NORM_ITEMS = [i for i in ITEMS_BY_TYPE[1] if i in NORMALIZING_ITEMS]
ALLY_PLAIN_ITEMS = [i for i in ITEMS_BY_TYPE[1] if i not in NORMALIZING_ITEMS]
USE_ITEMS = SPELL_ITEMS + SPELL_ITEMS + PLAIN_ITEMS[:60] + sorted(NORMALIZING_ITEMS)
# PLACE targets: the line-of-sight trace runs for RADIUS (6) and POINT (8) spells
SAFE_PLACE_SPELLS = [s for s in range(150) if SPELL_TARGET[s] not in (6, 8)] + TYPE[5] * 3
SAFE_PLACE_ITEMS = [i for i in range(N_ITEMS) if not ITEM_SPELL[i] or
                    SPELL_TARGET[ITEM_SPELL[i]] not in (6, 8)]
REAL_SPELLS = list(range(1, 102)) + list(range(114, 132))

WEAPON_IDS = [0, 10, 20, 30, 40, 52, 63, 465, 660, 681,          # short weapons, band 0
              53, 75, 79, 83, 87, 91, 95, 466, 562, 770,          # extended, band 1
              99, 103, 104, 105, 106, 107, 762, 763, 764,         # thrown, band 2
              110, 113, 116, 119, 122, 424, 599, 602, 605, 608,   # ranged, band 3
              140, 141, 467, 614, 625, 125, 126, 127, 128, 129]   # ammunition, 0/3
PLAIN_WEAPONS = [w for w in WEAPON_IDS if w not in BINDING_ITEMS]
BINDING_WEAPONS = sorted(BINDING_ITEMS)
OTHER_ITEMS = [142, 148, 181, 210, 235, 243, 254, 313, 320, 682, 331, 100, 260, 46, 258, 573, 269, 368,
               410, 340, 421, 333, 566, 818]

ACTION_KINDS = [-1, 0, 0, 0, 1, 1, 2, 3, 4, 5, 5, 6, 7, 7, 7, 7, 8, 8, 8, 9, 10, 11, 12]
HOLDS = [0, 0, 1, 1, 1, 2, 3, 3, 4, 5, -1]
BOOL_EDGE = [2, 0x80, 0xff]
COND_EDGE = [0x80000000, 0xffffffff, 0xfffffff0]


# ---------------------------------------------------------------- helpers
def p32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def p16(v):
    return struct.pack('<H', int(v) & 0xffff)


def u8(v):
    return bytes([int(v) & 0xff])


def pf(v):
    return struct.pack('<f', float(v))


def f32r(v):
    """v rounded to float32 (as the game sees it)."""
    return struct.unpack('<f', struct.pack('<f', float(v)))[0]


def rb(r, p=0.5):
    return 1 if r.random() < p else 0


def bool_byte(r, p_true, edge_p=0.0):
    if r.random() < p_true:
        return r.choice(BOOL_EDGE) if r.random() < edge_p else 1
    return 0


def rand_hp(r, zero_p=0.18):
    x = r.random()
    if x < zero_p:
        return 0
    if x < 0.9:
        return r.randrange(1, 400)
    return r.choice([1, 0x7fffffff, 0x80000000, 0xffffffff])


def rand_cond(r, edge_p=0.0):
    """highest_condition: mostly none, values around the 0x0d/0x12 thresholds, rarely values
    retail compares unsigned (negative as int)."""
    x = r.random()
    if x < edge_p:
        return r.choice(COND_EDGE)
    if x < 0.5:
        return 0
    if x < 0.8:
        return r.randrange(1, 0x14)
    return r.choice([0x0c, 0x0d, 0x0e, 0x11, 0x12, 0x13, 0x14])


def emit(c, addr, data, gap=48):
    """Write only the non-zero runs of data (scratch is zeroed for every case)."""
    data = bytes(data)
    n = len(data)
    i = 0
    while i < n:
        if data[i] == 0:
            i += 1
            continue
        start = last = i
        j = i + 1
        while j < n and j - last <= gap:
            if data[j]:
                last = j
            j += 1
        c.set(addr + start, data[start:last + 1])
        i = last + 1


def finish(c):
    if len(c.ops) > MAX_OPS:
        raise ValueError('%s: %d ops > %d' % (c.id, len(c.ops), MAX_OPS))


def edge_note(c, edges):
    if edges:
        c.note(edge=','.join(sorted(set(edges))))


class Env:
    def __init__(self, ctx):
        self.ctx = ctx
        self.S = [ctx.scratch(i) for i in range(8)]
        self.gx = ctx.g('gXStatus')
        self.st = ctx.g('g_status')
        self.rows = (self.st + ST_XCHAR).deref()
        self.cs = ctx.g('g_combat_state')
        self.cam = ctx.g('g_gd_camera').deref() + CAM_POS
        self.nav = ctx.g('g_startup_world').deref()
        self.lvl_ptr = ctx.g('g_level_block')
        self.lvl = self.lvl_ptr.deref()
        self.screen = ctx.g('g_current_screen_state')
        self.settings = ctx.g('g_settings')
        self.npc = ctx.g('g_npc_interaction_state').deref()
        self.iter = ctx.g('g_monster_info_iterator_index')

    def char(self, slot):
        return self.ctx.char(slot)

    def row(self, slot):
        return self.rows + slot * ROW

    def mon(self, k):
        return self.S[0] + k * MI_STRIDE

    def p3d(self, k):
        return self.S[1] + k * P3D_STRIDE

    def rec(self, j):
        return self.S[2] + j * REC_STRIDE

    def rep(self, k):
        return self.S[6] + k * REP_STRIDE

    def group(self, g):
        return self.S[3] + L_GROUPS + g * GROUP_STRIDE


def rand_spell(r, pool=None):
    if pool is not None:
        return r.choice(pool)
    k = r.random()
    if k < 0.08:
        return 0
    if k < 0.15:
        return r.choice([62, 118, 102, 113, 130, 149, 19, 119])
    return r.choice(REAL_SPELLS)


def rand_weapon(r):
    k = r.random()
    if k < 0.75:
        return r.choice(WEAPON_IDS)
    if k < 0.9:
        return r.choice(OTHER_ITEMS)
    return r.randrange(N_ITEMS)


def rand_use_item(r):
    return r.choice(USE_ITEMS) if r.random() < 0.92 else r.randrange(N_ITEMS)


def rand_cam(r):
    return (round(r.uniform(-80000.0, 80000.0), 2), round(r.uniform(-2000.0, 8000.0), 2),
            round(r.uniform(-80000.0, 80000.0), 2))


def rand_untargetable(r):
    return 0 if r.random() < 0.85 else r.choice([1, 2, 0xff, 205, 0x80])


def place(r, cam, mr, sr, theta=None):
    """A monster navigator position whose GetDistanceToPlayer often sits near a band edge.
    theta: the GetHeadingAngle(camera, position) to use (atan2(dx, dz))."""
    k = r.random()
    if k < 0.45:
        total = r.choice(BANDS) + mr + sr + r.choice([-300.0, -40.0, -2.0, -0.5, 0.5, 2.0, 40.0, 300.0])
    elif k < 0.6:
        total = r.uniform(0.0, mr + sr + 10.0)
    else:
        total = r.uniform(0.0, 32000.0)
    dy = r.uniform(-400.0, 400.0) if r.random() < 0.7 else 0.0
    if abs(dy) > total:
        dy = 0.0
    h = math.sqrt(max(total * total - dy * dy, 0.0))
    if theta is None:
        a = r.uniform(0.0, 2.0 * math.pi)
        return (cam[0] + h * math.cos(a), cam[1] - WORLD_HEIGHT + dy, cam[2] + h * math.sin(a))
    h = max(h, 200.0 + r.uniform(0.0, 100.0))   # keep the heading exact in float32
    return (cam[0] + h * math.sin(theta), cam[1] - WORLD_HEIGHT + dy, cam[2] + h * math.cos(theta))


def rand_mon(r, loc, species, cam, sr, theta=None):
    mr = r.choice([0.0, 150.0, 300.0, 500.0, 750.0, round(r.uniform(50.0, 1500.0), 2)])
    hp = 0 if r.random() < 0.08 else r.choice([1, 9, 60, 400] * 6 + [0x80000000, 0xffffffff])
    return {
        'loc': loc, 'group': 999, 'species': species,
        'active': bool_byte(r, 0.92, 0.05), 'incombat': bool_byte(r, 0.7, 0.05),
        'disp': 3 if r.random() < 0.03 else r.choice([0, 1, 1, 1, 2, 2]),
        'hp': hp,
        'dead18': 0 if r.random() < 0.9 else r.choice([1, 5, 0x80000000, 0xffffffff]),
        'highest': 0 if r.random() < 0.8 else r.choice([1, 8, 0x11, 0x12, 0x13]),
        'pt_sight': r.choice([0, 1, 1, 1, 1, 2]), 'pt_los': (rb(r, 0.75), rb(r, 0.75)),
        'pos': place(r, cam, mr, sr, theta), 'radius': mr, 'height': round(r.uniform(0.0, 1800.0), 1),
        'navr': r.choice([0.0, 0.0, 120.0, 450.5]),
    }


MFIELDS = (('group', MI_GROUP, 4), ('species', MI_SPECIES, 4), ('active', MI_ACTIVE, 1),
           ('incombat', MI_INCOMBAT, 1), ('disp', MI_DISP, 1), ('hp', MI_HP, 4),
           ('dead18', MI_COND18, 4), ('highest', MI_HIGHEST, 4), ('pt_sight', MI_PT_SIGHT, 1))


def mblob(m):
    b = Blob(MI_PT_LOS + 2)
    b.u32(MI_LOC, m['loc'])
    for key, off, size in MFIELDS:
        if key in m:
            if size == 4:
                b.u32(off, m[key])
            else:
                b.u8(off, m[key])
    if 'pt_los' in m:
        b.u8(MI_PT_LOS, m['pt_los'][0])
        b.u8(MI_PT_LOS + 1, m['pt_los'][1])
    return b


def p3dblob(m):
    b = Blob(M3_HEIGHT + 4)
    if 'navr' in m:
        b.f32(M3_NAVRADIUS, m['navr'])
    if 'pos' in m:
        x, y, z = m['pos']
        b.f32(M3_POS, x)
        b.f32(M3_POS + 4, y)
        b.f32(M3_POS + 8, z)
    if 'radius' in m:
        b.f32(M3_RADIUS, m['radius'])
    if 'height' in m:
        b.f32(M3_HEIGHT, m['height'])
    return b


def target_blob(kind, char=-1, mon=-1, group=-1, point=(0.0, 0.0, 0.0)):
    b = Blob(0x20)
    b.u32(0, kind)
    b.u32(4, char)
    b.u32(8, mon)
    b.u32(0xc, group)
    b.f32(0x10, point[0])
    b.f32(0x14, point[1])
    b.f32(0x18, point[2])
    return b


class World:
    """Fake monsters, records, groups and lists in scratch for one case."""

    def __init__(self, env, c):
        self.env = env
        self.c = c
        self.mons = []
        self.recs = []
        self.species = set()

    def add(self, m):
        self.mons.append(m)
        return len(self.mons) - 1

    def record(self, species, untargetable=0):
        if species in self.species:
            return
        self.species.add(species)
        self.recs.append((species, untargetable))

    def write(self, list_ks=None, reps=False):
        env, c = self.env, self.c
        for k, m in enumerate(self.mons):
            emit(c, env.mon(k), mblob(m), gap=128)
            if m.get('p3d', True):
                emit(c, env.p3d(k), p3dblob(m), gap=128)
                c.setp(env.mon(k) + MI_P3D, env.p3d(k))
                if reps:
                    c.setp(env.p3d(k) + M3_REP, env.rep(k))
                    if m.get('mask'):
                        c.set(env.rep(k) + REP_MASK, u8(m['mask']))
        for j, (species, unt) in enumerate(self.recs):
            if unt:
                c.set(env.rec(j) + MR_UNTARGETABLE, u8(unt))
            c.setp(env.gx + X_RECCACHE + 4 * species, env.rec(j))
        c.set(env.gx + X_MONLIST, bytes(8))      # monster and group lists
        c.set(env.gx + X_UNBORN, bytes(8))       # unborn and group encounter lists
        ks = list(range(len(self.mons)) if list_ks is None else list_ks)
        if ks:
            hdr = env.S[3] + L_MON
            c.set(hdr + 4, p32(len(ks) + 4) + p32(len(ks)))
            c.setp(hdr, hdr + 0x10)
            for i, k in enumerate(ks):
                c.setp(hdr + 0x10 + 4 * i, env.mon(k))
            c.setp(env.gx + X_MONLIST, hdr)

    def groups(self, groups):
        """groups: dicts gid, members, species, active, count, hl, listed (after write())."""
        env, c = self.env, self.c
        hdr = env.S[3] + L_GROUP
        listed = [gi for gi, g in enumerate(groups) if g.get('listed', True)]
        for gi, g in enumerate(groups):
            G = env.group(gi)
            b = Blob(G_HIGHLIGHT + 4)
            b.u32(G_ID, g['gid'])
            b.u32(G_COUNT, g['count'])
            b.u32(G_SPECIES, g['species'])
            b.u8(G_ACTIVE, g['active'])
            b.u32(G_ILIST + 4, len(g['members']) + 2)
            b.u32(G_ILIST + 8, len(g['members']))
            for t, mid in enumerate(g['members']):
                b.u32(G_IDATA + 4 * t, mid)
            b.u32(G_HIGHLIGHT, g.get('hl', -1))
            emit(c, G, b, gap=96)
            c.setp(G + G_MONSTERS, G + G_ILIST)
            if g['members']:
                c.setp(G + G_ILIST, G + G_IDATA)
        if listed:
            c.set(hdr + 4, p32(len(listed) + 2) + p32(len(listed)))
            c.setp(hdr, hdr + 0x10)
            for li, gi in enumerate(listed):
                c.setp(hdr + 0x10 + 4 * li, env.group(gi))
            c.setp(env.gx + X_GROUPLIST, hdr)

    def vis(self, k, entries):
        env, c = self.env, self.c
        n = len(entries)
        blob = Blob(max(n, 1) * VR_STRIDE)
        for j, e in enumerate(entries):
            if e is None:
                continue
            o = j * VR_STRIDE
            blob.u32(o, e['about'])
            blob.u8(o + VR_SIGHT, e['sight'])
            for t in range(4):
                blob.u8(o + VR_LOS + t, e['los'][t])
            blob.u8(o + VR_CANSEE, e['cansee'])
            blob.u8(o + VR_LINE, e['line'])
        base = env.S[3] + L_VISREC
        emit(c, base, blob, gap=64)
        hdr = env.S[3] + L_VIS
        c.set(hdr + 4, p32(n + 2) + p32(n))
        if n:
            c.setp(hdr, hdr + 0x10)
        for j, e in enumerate(entries):
            if e is not None:
                c.setp(hdr + 0x10 + 4 * j, base + j * VR_STRIDE)
        c.setp(env.mon(k) + MI_VISLIST, hdr)


def rand_vis(r, about):
    return {'about': about, 'sight': r.choice([0, 1, 1, 1, 2]), 'los': tuple(rb(r, 0.7) for _ in range(4)),
            'cansee': rb(r, 0.7), 'line': rb(r, 0.7)}


def vis_entries(r, world, others):
    """A source monster's mon-to-mon records: most others, some strangers, a null entry."""
    entries = []
    for k in others:
        if r.random() < 0.85:
            entries.append(rand_vis(r, world.mons[k]['loc']))
    if r.random() < 0.3:
        entries.append(rand_vis(r, r.randrange(5000, 6000)))
    if r.random() < 0.06:
        entries.append(None)
    r.shuffle(entries)
    return entries


def mon_world(r, env, c, cam, sr, n, headings=False, shared=0.0):
    """n monsters with distinct location ids; distinct species (or one shared species)."""
    w = World(env, c)
    locs = r.sample(range(1, 4000), max(n, 1))
    species = r.sample(range(N_MONSTERS), max(n, 1))
    if n >= 2 and r.random() < shared:
        species = [species[0]] * n
    degs = r.sample(range(360), max(n, 1))
    for k in range(n):
        theta = math.radians(degs[k] + r.uniform(0.2, 0.8)) if headings else None
        w.add(rand_mon(r, locs[k], species[k], cam, sr, theta))
    for k in range(n):
        w.record(species[k], rand_untargetable(r))
    return w


def rand_groups(r, w, nmin=0, nmax=2, empty_p=0.1):
    """Groups over the world's monsters; group species get a record. Call before write()."""
    ids = [m['loc'] for m in w.mons]
    ng = r.randint(nmin, nmax)
    gids = r.sample(range(100, 400), max(ng, 1))
    groups = []
    for g in range(ng):
        if ids and r.random() >= empty_p:
            members = r.sample(ids, r.randint(1, len(ids)))
        else:
            members = []
        if w.mons and r.random() < 0.4:
            sp = r.choice([m['species'] for m in w.mons])
        else:
            sp = r.randrange(N_MONSTERS)
        w.record(sp, rand_untargetable(r))
        groups.append({'gid': gids[g], 'members': members, 'species': sp,
                       'active': bool_byte(r, 0.85, 0.08),
                       'count': len(members) if r.random() < 0.85 else r.choice([0, 1, 5]),
                       'hl': -1, 'listed': True})
    for m in w.mons:
        if groups and r.random() < 0.8:
            m['group'] = r.choice([g['gid'] for g in groups])
        else:
            m['group'] = r.choice([999, 0])
    return groups


# ---------------------------------------------------------------- party/state setup
def hands_safe(blob):
    for h in (0, 1):
        o = C_HAND + h * HAND_STEP
        holds = blob.get_i32(o)
        item = blob.get_i32(C_EQUIP + (6 + h) * ITEM)
        if blob[o + 4] and holds in (1, 3) and not (0 <= item < N_ITEMS):
            return False
    return True


def set_hands(c, base, r, blob, p=0.75):
    """Override both hands' uiHolds/in_play and items 6/7 (always valid ids)."""
    if hands_safe(blob) and r.random() >= p:
        return False
    hb = bytearray(blob[C_HAND:C_HAND + HAND_STEP + 5])
    for h in (0, 1):
        o = h * HAND_STEP
        struct.pack_into('<i', hb, o, r.choice(HOLDS))
        hb[o + 4] = 1 if r.random() < 0.8 else 0
    ib = bytearray(blob[C_PRIMARY:C_PRIMARY + ITEM + 4])
    struct.pack_into('<i', ib, 0, rand_weapon(r))
    struct.pack_into('<i', ib, ITEM, rand_weapon(r))
    c.set(base + C_HAND, bytes(hb))
    c.set(base + C_PRIMARY, bytes(ib))
    return True


def set_vitals(c, base, blob, hp, highest):
    b = bytearray(blob[C_HIGHEST:C_HP + 4])
    struct.pack_into('<I', b, 0, highest)
    struct.pack_into('<I', b, C_HP - C_HIGHEST, hp)
    c.set(base + C_HIGHEST, bytes(b))


def rand_formation(r):
    occ = [[-1] * 3 for _ in range(5)]
    pos = []
    for s in range(8):
        free = [(q, i) for q in range(5) for i in range(3) if occ[q][i] == -1]
        if free and r.random() < 0.88:
            q, i = r.choice(free)
            if r.random() < 0.3:
                pref = [(qq, ii) for qq, ii in free if qq == r.choice([4, 4, 0, 2])]
                if pref:
                    q, i = r.choice(pref)
            occ[q][i] = s
            pos.append((q, r.choice([-1, q]), i, r.randrange(4)))
        else:
            pos.append((-1, r.choice([-1, 0, 1, 2, 3, 4]), 0, r.randrange(4)))
    b = Blob(FORM_SIZE)
    for q in range(5):
        for i in range(3):
            b.u8(q * 3 + i, occ[q][i])
        b.u8(15 + q, sum(1 for x in occ[q] if x != -1))
    for s, (q, oq, qs, f) in enumerate(pos):
        o = FORM_POS + s * 12
        b.u8(o, q)
        b.u8(o + 1, oq)
        b.u8(o + 2, qs)
        b.u8(o + 3, f)
    return b


def formation_state(c, env, r, oof_p=0.12):
    c.set(env.st + ST_FORMATION, bytes(rand_formation(r)))
    for s in range(8):
        if r.random() < oof_p:
            c.set(env.char(s) + C_OOF, b'\x01' if r.random() < 0.6 else b'\x00')


def view_state(c, env, r, cam=None):
    cam = cam or rand_cam(r)
    c.set(env.cam, pf(cam[0]) + pf(cam[1]) + pf(cam[2]))
    c.set(env.st + ST_FACING, p32(r.randrange(360)))
    sr = r.choice([0.0, 250.0, 400.0, 500.0, 800.0, round(r.uniform(10.0, 1200.0), 2)])
    coll = r.choice([sr, 500.0, round(r.uniform(0.0, 1500.0), 2)])
    c.set(env.nav + NAV_COLL, pf(coll) + pf(sr))
    return cam, sr


def modes_state(c, env, combat, spell=0, item=0, targeting=None):
    c.set(env.gx + X_COMBAT, bytes([combat, spell, item]))
    if targeting is not None:
        c.set(env.gx + X_TARGETING, p32(targeting))


def combat_state(c, env, r, dead_p=0.25):
    c.setp(env.cs, env.S[4])
    b = Blob(CS_SIZE)
    b.u32(CS_ROUND, r.choice([0, 1, 1, 2, 5]))
    for s in range(8):
        if r.random() < 0.12:
            b.u8(CS_CHARS + s * CS_ROW + CS_BERSERK, 1)
        if r.random() < dead_p:
            b.u8(CS_CHARS + s * CS_ROW + CS_DEAD, 1)
    b.u8(CS_ENGAGED, rb(r, 0.5))
    emit(c, env.S[4], b, gap=0x100)


def current_ctx(c, env, r, slot, spell, item, settled=None):
    """Pin W8_TARGETING_CONTEXT_CURRENT to OUT/IN_COMBAT, SPELL or ITEM (never SHARED/DIALOGUE)."""
    k = r.random()
    if k < 0.6:
        st = r.choice([0, 0, 1, 1, 2]) if settled is None else settled
        c.set(env.lvl + LVL_KIND, p32(-1) + p32(rand_spell(r)) + u8(st))
        if not spell and not item and r.random() < 0.5:
            sel = slot
        else:
            sel = r.choice([-1, (slot + 1) % 8, 9])
        cur = 'base'
    else:
        c.set(env.screen, p32(7))
        kind = 7 if k < 0.8 else 8
        c.set(env.lvl + LVL_KIND, p32(kind) + p32(rand_spell(r)) + u8(r.choice([1, 1, 1, 2, 0xff])))
        sel = r.choice([-1, slot])
        cur = 'spell' if kind == 7 else 'item'
    c.set(env.st + ST_SELECTED, p32(sel))
    return cur


def dialogue_ctx(c, env, r):
    """W8_TARGETING_CONTEXT_DIALOGUE: kind/value from the level block (never USE_ITEM: null detail)."""
    c.set(env.lvl + LVL_KIND, p32(r.choice([-1, 0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11])) + p32(rand_spell(r)))


def acting_row(c, env, r, slot, blob, targets=None, occupied=1, spells=None, items=None, own=True,
               kinds=None):
    ks = kinds or ACTION_KINDS
    b = Blob(ROW_USED)
    b.u8(0, occupied)
    b.u32(R_PENDING, r.choice(ks))
    b.u32(R_MODE0, rand_spell(r, spells))
    b.u32(R_PDETAIL, r.randrange(4))
    b.u32(R_ACTION, r.choice(ks))
    b.u32(R_ADETAIL0, rand_spell(r, spells))
    b.u32(R_ADETAIL1, r.randrange(4))
    b.u32(R_SPELL, rand_spell(r, spells))
    b.u32(R_SDETAIL, r.randrange(1, 8))
    b.u32(R_IDETAIL, r.randrange(4))
    if targets is not None:
        for off in ROW_TARGETS:
            b[off:off + 0x20] = bytes(targets)
    c.set(env.row(slot), bytes(b))
    owned = [k for k in range(12) if k not in (6, 7) and 0 <= blob.get_i32(C_EQUIP + k * ITEM) < N_ITEMS]
    ib = Blob(0x30)
    for j, off in enumerate(ITEM_PTRS):
        x = r.random()
        if x < 0.12:
            continue
        if x < 0.3 and owned and own:
            c.setp(env.row(slot) + off, env.char(slot) + C_EQUIP + r.choice(owned) * ITEM)
        else:
            ib.u32(j * 0x10, r.choice(items) if items else rand_use_item(r))
            c.setp(env.row(slot) + off, env.S[5] + S5_ITEMS + j * 0x10)
    emit(c, env.S[5] + S5_ITEMS, ib)


def aim_env(ctx, env, c, r, slot, kinds=None, spells=None, items=None, own=True, targets=None,
            settled=None):
    """The acting slot, modes, view, formation and the CURRENT-context pin."""
    party = ctx.set_party(c, r, slots=[slot])
    blob = party[0][1]
    combat = bool_byte(r, 0.5, 0.05)
    spell = rb(r, 0.2)
    item = rb(r, 0.15)
    modes_state(c, env, combat, spell, item, targeting=r.choice([0, 0, 0, 1, 2, 3, 5, -1]))
    if r.random() < 0.25:
        set_vitals(c, env.char(slot), blob, 0 if r.random() < 0.4 else r.choice([1, 50]),
                   r.choice([0, 0x0d, 0x11, 0x12, 0x13]))
    acting_row(c, env, r, slot, blob, targets=targets, occupied=1 if r.random() < 0.93 else 0,
               spells=spells, items=items, own=own, kinds=kinds)
    set_hands(c, env.char(slot), r, blob)
    formation_state(c, env, r)
    cam, sr = view_state(c, env, r)
    cur = current_ctx(c, env, r, slot, spell, item, settled)
    return blob, combat, cam, sr, cur


def camp_state(c, env, r, loc, p=0.12):
    camp = bool_byte(r, p, 0.2)
    c.set(env.gx + X_CAMP, u8(camp))
    if camp:
        c.set(env.npc + NPC_TARGET, p32(loc if r.random() < 0.6 else r.choice([loc + 1, -1, 0])))
    return camp


# ---------------------------------------------------------------- simple party predicates
def gen_participate(ctx, env):
    """bool CanPartySlotParticipate(int party_slot): fOccupied && hp != 0 && highest < 0x12
    (retail: unsigned JAE)."""
    fn = ctx.fn(0x0053C270)
    for i in range(ctx.n(200)):
        r = ctx.rng('participate', i)
        c = ctx.case('CanPartySlotParticipate.%d' % i, fn, conv='c', ret='b')
        slot = r.randrange(8)
        party = ctx.set_party(c, r, slots=[slot])
        occ = bool_byte(r, 0.8, 0.08)
        hp = rand_hp(r)
        hi = rand_cond(r, 0.1)
        c.set(env.row(slot), u8(occ))
        set_vitals(c, env.char(slot), party[0][1], hp, hi)
        c.arg(slot)
        c.note(slot=slot, occ=occ, hp=hp, highest=hi)
        edge_note(c, (['bool_byte'] if occ not in (0, 1) else []) +
                  (['cond_negative'] if hi >= 0x80000000 else []) + (['hp_negative'] if hp >= 0x80000000 else []))
        finish(c)


def gen_dead_targetable(ctx, env):
    """bool IsDeadCharacterTargetable(int party_slot): occupied, hp unsigned 0, uiCondition[18]
    != 0, uiCondition[19] == 0 (retail: unsigned compares)."""
    fn = ctx.fn(0x0053C2C0)
    for i in range(ctx.n(250)):
        r = ctx.rng('deadtarget', i)
        c = ctx.case('IsDeadCharacterTargetable.%d' % i, fn, conv='c', ret='b')
        slot = r.randrange(8)
        ctx.set_party(c, r, slots=[slot])
        occ = bool_byte(r, 0.85, 0.08)
        hp = 0 if r.random() < 0.55 else rand_hp(r, 0.0)
        c18 = r.choice([0, 0, 1, 1, 3, 9999, 0x80000000, 0xffffffff, r.randrange(1, 100)])
        c19 = 0 if r.random() < 0.6 else r.choice([1, 2, 0x7fffffff, 0x80000000, 0xffffffff])
        c.set(env.row(slot), u8(occ))
        c.set(env.char(slot) + C_COND18, p32(c18) + p32(c19))
        c.set(env.char(slot) + C_HP, p32(hp))
        c.arg(slot)
        c.note(slot=slot, occ=occ, hp=hp, cond18=c18, cond19=c19)
        edge_note(c, (['bool_byte'] if occ not in (0, 1) else []) +
                  (['hp_negative'] if hp >= 0x80000000 else []) +
                  (['cond_negative'] if c18 >= 0x80000000 or c19 >= 0x80000000 else []))
        finish(c)


# ---------------------------------------------------------------- targeting contexts
def context_state(c, env, r):
    screen = r.choice([7] * 7 + [6, 8, 0, 3, 0x10])
    c.set(env.screen, p32(screen))
    kind = settled = None
    if r.random() < 0.08:
        c.set(env.lvl_ptr, p32(0))        # g_level_block = NULL (restored after the case)
    else:
        kind = r.choice([-1] * 5 + [7, 7, 7, 8, 8, 8, 0, 1, 2, 5, 9, 10, 0x7fffffff, -2, 0x107])
        settled = r.choice([0, 0, 1, 1, 1, 2, 0xff])
        c.set(env.lvl + LVL_KIND, p32(kind) + p32(r.randrange(150)) + u8(settled))
    combat = bool_byte(r, 0.5, 0.15)
    spell = bool_byte(r, 0.25, 0.15)
    item = bool_byte(r, 0.2, 0.15)
    c.set(env.gx + X_COMBAT, bytes([combat, spell, item]))
    sel = r.choice(list(range(8)) + [-1, 9])
    c.set(env.st + ST_SELECTED, p32(sel))
    if r.random() < 0.5:
        slot = sel
    else:
        slot = r.choice(list(range(8)) * 3 + [-1, 8, 100, 0x7fffffff, -0x80000000])
    c.note(screen=screen, kind=kind, settled=settled, combat=combat, spell=spell, item=item,
           selected=sel, slot=slot)
    edge_note(c, ['bool_byte'] if any(v not in (0, 1, None) for v in (combat, spell, item, settled)) else [])
    return slot


def gen_contexts(ctx, env):
    """W8TargetingContext GetCombatActionContext(int) and GetValidatedTargetingContext(int, ctx):
    pure functions of the screen id, g_level_block selection (incl. NULL block), the selected
    character and the three mode bytes."""
    fn = ctx.fn(0x0053bc90)
    for i in range(ctx.n(250)):
        r = ctx.rng('combatctx', i)
        c = ctx.case('GetCombatActionContext.%d' % i, fn, conv='c', ret='i')
        slot = context_state(c, env, r)
        c.arg(slot)
        finish(c)
    fn = ctx.fn(0x0053ba20)
    for i in range(ctx.n(250)):
        r = ctx.rng('validctx', i)
        c = ctx.case('GetValidatedTargetingContext.%d' % i, fn, conv='c', ret='i')
        slot = context_state(c, env, r)
        context = r.choice([6] * 6 + [0, 1, 2, 3, 4, 5, 7, 8, 9, -1, 100, -0x80000000])
        c.arg(slot)
        c.arg(context)
        c.note(context=context)
        finish(c)


# ---------------------------------------------------------------- aim cone geometry
def heading_of(dx, dz):
    if dz == 0.0:
        return math.pi / 2 if dx > 0.0 else -math.pi / 2
    return math.atan2(dx, dz)


def direction(theta, elev):
    """Unit vector whose GetHeadingAngle is theta and GetElevationAngle is elev
    (GetElevationAngle = acos(dy / len) - pi/2, so dy = -len * sin(elev))."""
    h = math.cos(elev)
    return (h * math.sin(theta), -math.sin(elev), h * math.cos(theta))


# pi/4 = 0.785398: offsets keep >= 1e-4 from the arc edge (angles come from float32 positions)
ARC_OFFSETS = [0.0, 0.3, -0.3, 0.78, -0.78, 0.7853, -0.7853, 0.7855, -0.7855, 0.786, -0.786,
               0.79, -0.79, 1.5, -1.5, 3.0, math.pi]


def gen_arcs(ctx, env):
    """bool TargetInRangeAndArcs(target*, float bonus, eye*, float eye_radius, float heading,
    float elevation): floor(|target-eye| - bonus - eye_radius) <= 12500 (retail compares the
    double floor result, unordered = false), then both arcs < pi/4 (NormalizeAngle)."""
    fn = ctx.fn(0x00539b70)
    tgt = env.S[5] + S5_VEC_A
    eyea = env.S[5] + S5_VEC_B
    for i in range(ctx.n(400)):
        r = ctx.rng('arcs', i)
        c = ctx.case('TargetInRangeAndArcs.%d' % i, fn, conv='c', ret='b')
        eye = (round(r.uniform(-60000.0, 60000.0), 2), round(r.uniform(-3000.0, 6000.0), 2),
               round(r.uniform(-60000.0, 60000.0), 2))
        bonus = r.choice([0.0, 0.0, 50.0, 150.5, 500.0, 1500.0, -100.0, round(r.uniform(0.0, 2000.0), 3)])
        erad = r.choice([0.0, 0.0, 500.0, 250.0, round(r.uniform(0.0, 1500.0), 3), -50.0])
        k = r.random()
        special = None
        if k < 0.45:
            # floor() keeps an excess below 12501 in range; stay >= 0.05 off the integer edges so
            # float32 position rounding / 80-bit vs float arithmetic cannot pick the side
            dist = 12500.0 + bonus + erad + r.choice([-3.0, -1.0, -0.5, -0.05, 0.3, 0.5, 0.9, 0.95,
                                                       1.05, 1.1, 1.5, 3.0, 50.0])
            special = 'edge'
        elif k < 0.8:
            dist = r.uniform(0.0, 30000.0)
        elif k < 0.85:
            dist = 0.0
            special = 'zero'
        elif k < 0.9:
            dist = r.choice([1e6, 3e7, 1e9, 1e20])
            special = 'huge'
        else:
            dist = r.uniform(100.0, 14000.0)
            special = r.choice(['axis', 'axis', 'nan_target', 'nan_bonus'])
        theta = r.uniform(-math.pi, math.pi)
        elev = r.uniform(-1.2, 1.2)
        dx, dy, dz = (v * max(dist, 0.0) for v in direction(theta, elev))
        if special == 'axis':
            dz = 0.0
            dx = r.choice([1.0, -1.0, 0.0]) * math.sqrt(max(dist * dist - dy * dy, 0.0))
        target = [eye[0] + dx, eye[1] + dy, eye[2] + dz]
        if special == 'axis':
            target[2] = eye[2]
        if special == 'nan_target':
            target[r.randrange(3)] = float('nan')
        if special == 'nan_bonus':
            bonus = float('nan')
        # the angles the game will compute come from the float32 positions
        target = [f32r(v) for v in target]
        eye = tuple(f32r(v) for v in eye)
        dx, dy, dz = target[0] - eye[0], target[1] - eye[1], target[2] - eye[2]
        h_t = heading_of(dx, dz) if special not in ('nan_target',) else 0.0
        ln = math.sqrt(dx * dx + dy * dy + dz * dz) if special not in ('nan_target',) else 0.0
        e_t = (math.acos(max(-1.0, min(1.0, dy / ln))) - math.pi / 2) if ln > 0 else 0.0
        heading = h_t + r.choice(ARC_OFFSETS) * (1 if r.random() < 0.7 else r.choice([0.0, 0.5]))
        heading += 2.0 * math.pi * r.choice([0, 0, 0, 0, 1, -1, 2])
        elevation = e_t + r.choice(ARC_OFFSETS) * (1 if r.random() < 0.6 else 0.0)
        elevation += 2.0 * math.pi * r.choice([0, 0, 0, 0, 1, -1])
        c.set(tgt, pf(target[0]) + pf(target[1]) + pf(target[2]))
        c.set(eyea, pf(eye[0]) + pf(eye[1]) + pf(eye[2]))
        c.arg(tgt)
        c.arg(F32(bonus))
        c.arg(eyea)
        c.arg(F32(erad))
        c.arg(F32(heading))
        c.arg(F32(elevation))
        c.note(dist=round(dist, 3), bonus=bonus if bonus == bonus else 'nan', eye_radius=erad,
               heading=round(heading, 5), elevation=round(elevation, 5), special=special)
        if special == 'axis':
            c.note(axis=1)
        finish(c)


def gen_cone(ctx, env):
    """int CollectConeMonsterTargets(source*, eye*, float heading, float elevation,
    W8GrowableVector<int>* found, unsigned char disposition, int sight_flag)."""
    fn = ctx.fn(0x00539ca0)
    src = env.S[5] + S5_SOURCE
    eyea = env.S[5] + S5_VEC_B
    vec = env.S[7]
    for i in range(ctx.n(300)):
        r = ctx.rng('cone', i)
        c = ctx.case('CollectConeMonsterTargets.%d' % i, fn, conv='c', ret='i')
        kind = r.choice([1] * 9 + [2] * 8 + [0, 3, 3])
        eye = (round(r.uniform(-60000.0, 60000.0), 2), round(r.uniform(-2000.0, 6000.0), 2),
               round(r.uniform(-60000.0, 60000.0), 2))
        heading = round(r.uniform(-math.pi, math.pi), 4)
        elevation = round(r.uniform(-0.6, 0.6), 4)
        disp = r.choice([0, 1, 1, 2, 3, 3]) if r.random() < 0.94 else r.choice([0x103, 0x201, 4, 0xff])
        sight = r.choice([0, 1, 2, 3]) if r.random() < 0.9 else r.choice([4, 6, 7])
        navr = r.choice([0.0, 500.0, 250.5, round(r.uniform(0.0, 1500.0), 2)])
        c.set(env.nav + NAV_RADIUS, pf(navr))
        n = r.choice([1, 2, 2, 3, 3, 4, 5])
        w = World(env, c)
        species = r.sample(range(N_MONSTERS), r.choice([1, 2, 2, 3]))
        for s in species:
            w.record(s, rand_untargetable(r))
        locs = r.sample(range(1, 4000), n)
        mons = []
        for m in range(n):
            mons.append({'loc': locs[m], 'species': r.choice(species), 'active': bool_byte(r, 0.9, 0.05),
                         'disp': r.choice([0, 1, 1, 2, 3]) if r.random() >= 0.6 else (disp & 0xff),
                         'hp': 0 if r.random() < 0.08 else r.choice([1, 50, 400, 0x80000000]),
                         'dead18': 0 if r.random() < 0.9 else r.choice([1, 0x80000000]),
                         'pt_los': (rb(r, 0.7), rb(r, 0.7)),
                         'navr': r.choice([0.0, 0.0, 150.0, 400.0, round(r.uniform(10.0, 1200.0), 2)]),
                         'height': round(r.uniform(0.0, 1800.0), 1)})
        src_k = r.randrange(n) if kind == 2 else None
        srcr = navr if kind == 1 else (mons[src_k]['navr'] if kind == 2 else 0.0)
        for m, mon in enumerate(mons):
            fail = None
            if kind in (0, 3):   # never reach SourceCanSeeMonster (octree trace)
                fail = r.choice(['far', 'far', 'inactive', 'hp', 'dead'])
                if fail == 'inactive':
                    mon['active'] = 0
                elif fail == 'hp':
                    mon['hp'] = 0
                elif fail == 'dead':
                    mon['dead18'] = 1
            x = r.random()
            th = heading + r.uniform(-0.7, 0.7)
            el = elevation + r.uniform(-0.7, 0.7)
            reach = 12500.0 + mon['navr'] + srcr
            if fail == 'far':
                dist = r.uniform(40000.0, 90000.0) + mon['navr']
                th = r.uniform(-math.pi, math.pi)
            elif x < 0.5:
                dist = r.uniform(0.0, max(reach - 1.5, 0.0))
            elif x < 0.7:
                dist = max(reach + r.choice([-2.0, -0.5, 0.3, 0.9, 1.2, 3.0]), 0.0)
            elif x < 0.85:
                th = heading + r.choice([1, -1]) * (math.pi / 4 + r.choice([-0.01, 0.01, 0.002]))
                if r.random() < 0.4:
                    el = elevation + r.choice([1, -1]) * (math.pi / 4 + r.choice([-0.01, 0.01]))
                dist = r.uniform(100.0, 9000.0)
            else:
                th = r.uniform(-math.pi, math.pi)
                el = r.uniform(-1.3, 1.3)
                dist = r.uniform(0.0, 30000.0)
            el = max(-1.4, min(1.4, el))
            d = direction(th, el)
            point = (eye[0] + d[0] * dist, eye[1] + d[1] * dist, eye[2] + d[2] * dist)
            mon['pos'] = (point[0], point[1] - mon['height'], point[2])
            w.add(mon)
        order = list(range(n))
        r.shuffle(order)
        w.write(list_ks=order)
        sb = Blob(0x34)
        sb.u32(0, kind)
        if kind == 1:
            sb.u32(4, r.randrange(8) if r.random() < 0.95 else -1)
            sb.u32(8, -1)
        elif kind == 2:
            sb.u32(4, -1)
            sb.u32(8, mons[src_k]['loc'])
            w.vis(src_k, vis_entries(r, w, [k for k in range(n) if k != src_k]))
        else:
            sb.u32(4, r.choice([-1, 2]))
            sb.u32(8, r.choice([-1, locs[0]]))
            for o in (0xc, 0x10, 0x14):
                sb.f32(o, r.uniform(-50000.0, 50000.0))
            sb.u8(0x1b, rb(r, 0.5))
            sb.u8(0x1c, rb(r, 0.5))
        emit(c, src, sb)
        c.set(eyea, pf(eye[0]) + pf(eye[1]) + pf(eye[2]))
        c0 = r.choice([0, 0, 0, 1, 2])
        cap = c0 + n + 2 + r.randrange(3)
        c.set(vec + 4, p32(c0) + p32(cap))
        c.setp(vec + 0xc, vec + VEC_DATA)
        if c0:
            c.set(vec + VEC_DATA, b''.join(p32(r.randrange(1, 4000)) for _ in range(c0)))
        c.set(env.iter, p32(r.randrange(0, 9)))
        c.cap(env.iter, 4, 'iterator')
        c.cap(vec, 0x10, 'found_header', ignore=[0xc])
        c.cap(vec + VEC_DATA, 4 * cap, 'found_data')
        c.arg(src)
        c.arg(eyea)
        c.arg(F32(heading))
        c.arg(F32(elevation))
        c.arg(vec)
        c.arg(disp)
        c.arg(sight)
        c.note(kind=kind, monsters=n, disposition=disp, sight_flag=sight, heading=heading,
               elevation=elevation, start_count=c0)
        finish(c)


# ---------------------------------------------------------------- item use
def gen_item_use(ctx, env):
    """bool ItemUseNeedsTarget(int party_slot): the row's (origin, slot) item, its spell's target
    type (normalized for potions/food/drink); type 3 needs a pick unless camped or autotarget."""
    fn = ctx.fn(0x0053a770)
    cats = (['enemy'] * 6 + ['ally'] * 3 + ['ally_norm'] * 3 + ['plain'] * 2 + ['false_types'] * 3 +
            ['true_types'] * 3)
    for i in range(ctx.n(300)):
        r = ctx.rng('itemuse', i)
        c = ctx.case('ItemUseNeedsTarget.%d' % i, fn, conv='c', ret='b')
        slot = r.randrange(8)
        ctx.set_party(c, r, slots=[slot])
        cat = r.choice(cats)
        if cat == 'enemy':
            item = r.choice(ITEMS_BY_TYPE[3])
        elif cat == 'ally':
            item = r.choice(ALLY_PLAIN_ITEMS)
        elif cat == 'ally_norm':
            item = r.choice(ALLY_NORM_ITEMS + sorted(NORMALIZING_ITEMS))
        elif cat == 'plain':
            item = r.choice(PLAIN_ITEMS)
        elif cat == 'false_types':
            item = r.choice(ITEMS_BY_TYPE[0] + ITEMS_BY_TYPE[2] + ITEMS_BY_TYPE[7] + ITEMS_BY_TYPE[10])
        else:
            item = r.choice(ITEMS_BY_TYPE[4] + ITEMS_BY_TYPE[5] + ITEMS_BY_TYPE[6] + ITEMS_BY_TYPE[8] +
                            ITEMS_BY_TYPE[9])
        origin = r.choice([0] * 4 + [1] * 3 + [2] * 3)
        if origin == 0:
            islot = r.randrange(8) if r.random() < 0.95 else r.choice([8, 9, 10])
            base = env.char(slot) + C_BACKPACK + islot * ITEM
        elif origin == 1:
            islot = r.randrange(12) if r.random() < 0.95 else r.choice([12, 13])
            base = env.char(slot) + C_EQUIP + islot * ITEM
        else:
            islot = r.choice([0, 1, 2, 499, r.randrange(500), r.randrange(500)])
            base = env.st + ST_POOL + islot * ITEM
        c.set(base, p32(item))
        c.set(env.row(slot) + R_ITEM_ORIGIN, u8(origin) + p16(islot))
        at = r.choice([0, 0, 0, 1, 1, 2, 0xff])
        camp = r.choice([0, 0, 0, 1, 2])
        c.set(env.settings + SET_AUTOTARGET, u8(at))
        c.set(env.gx + X_CAMP, u8(camp))
        c.arg(slot)
        c.note(slot=slot, item=item, spell=ITEM_SPELL[item], category=cat, origin=origin,
               item_slot=islot, autotarget=at, camp=camp)
        edge_note(c, ['bool_byte'] if at not in (0, 1) or camp not in (0, 1) else [])
        finish(c)


# ---------------------------------------------------------------- monster predicates
def gen_can_target_monster(ctx, env):
    """bool CanTargetMonster(int slot, int location_id, bool allow_single, bool notify=0)."""
    fn = ctx.fn(0x00536ad0)
    for i in range(ctx.n(400)):
        r = ctx.rng('cantargetmon', i)
        c = ctx.case('CanTargetMonster.%d' % i, fn, conv='c', ret='b')
        slot = r.randrange(8)
        blob, combat, cam, sr, cur = aim_env(ctx, env, c, r, slot)
        n = r.choice([1, 1, 2, 2, 3])
        w = mon_world(r, env, c, cam, sr, n)
        groups = rand_groups(r, w, 0, 2)
        order = list(range(n))
        r.shuffle(order)
        w.write(list_ks=order)
        w.groups(groups)
        t = r.randrange(n)
        loc = w.mons[t]['loc']
        camp = camp_state(c, env, r, loc)
        allow = rb(r)
        c.arg(slot)
        c.arg(loc)
        c.arg(allow)
        c.arg(0)
        m = w.mons[t]
        c.note(slot=slot, monsters=n, groups=len(groups), allow=allow, camp=camp, combat=combat,
               context=cur, active=m['active'], hp=m['hp'], dead18=m['dead18'], sight=m['pt_sight'])
        finish(c)


def gen_can_target_group(ctx, env):
    """bool CanTargetMonsterGroup(int slot, W8MonsterGroup* group)."""
    fn = ctx.fn(0x00536d60)
    for i in range(ctx.n(300)):
        r = ctx.rng('cantargetgroup', i)
        c = ctx.case('CanTargetMonsterGroup.%d' % i, fn, conv='c', ret='b')
        slot = r.randrange(8)
        blob, combat, cam, sr, cur = aim_env(ctx, env, c, r, slot)
        n = r.choice([1, 2, 2, 3])
        w = mon_world(r, env, c, cam, sr, n)
        groups = rand_groups(r, w, 1, 2, empty_p=0.08)
        g = r.randrange(len(groups))
        if r.random() < 0.15:
            groups[g]['listed'] = False
        w.write()
        w.groups(groups)
        c.arg(slot)
        c.arg(env.group(g))
        c.note(slot=slot, monsters=n, group_members=len(groups[g]['members']), combat=combat,
               context=cur, listed=groups[g]['listed'])
        finish(c)


def party_occupancy(c, env, r, skip, vitals_p=0.25):
    """Other slots' fOccupied (+ a few hp/highest overrides on the real characters)."""
    for s in range(8):
        if s == skip:
            continue
        c.set(env.row(s), u8(bool_byte(r, 0.85, 0.05)))
        if r.random() < vitals_p:
            c.set(env.char(s) + C_HIGHEST, p32(rand_cond(r, 0.05)))
            c.set(env.char(s) + C_HP, p32(rand_hp(r, 0.3)))


def indirect_party(c, env, r):
    """All 8 slots: fOccupied, hp_current, uiCondition[18/19] (raise-the-dead sweep)."""
    good = 0
    for s in range(8):
        occ = bool_byte(r, 0.85, 0.05)
        hp = 0 if r.random() < 0.5 else rand_hp(r, 0.0)
        c18 = 0 if r.random() < 0.5 else r.choice([1, 2, 0x80000000])
        c19 = 0 if r.random() < 0.7 else r.choice([1, 0xffffffff])
        if occ and hp == 0 and c18 and not c19:
            good += 1
        c.set(env.row(s), u8(occ))
        c.set(env.char(s) + C_COND18, p32(c18) + p32(c19))
        c.set(env.char(s) + C_HP, p32(hp))
    return good


def gen_spell_any(ctx, env):
    """bool SpellHasAnyValidTarget(int slot, int spell_id, bool normalize)."""
    fn = ctx.fn(0x0053d010)
    for i in range(ctx.n(400)):
        r = ctx.rng('spellany', i)
        c = ctx.case('SpellHasAnyValidTarget.%d' % i, fn, conv='c', ret='b')
        mode = r.choice(['enemy'] * 8 + ['group'] * 5 + ['indirect'] * 4 + ['other'] * 3)
        slot = r.randrange(8)
        normalize = rb(r, 0.3)
        if mode == 'enemy':
            spell = r.choice(TYPE[3])
        elif mode == 'group':
            spell = r.choice(TYPE[4])
        elif mode == 'indirect':
            spell = SPELL_RESURRECTION
            normalize = 0 if r.random() < 0.85 else 1
        else:
            spell = r.choice(TYPE[0] + TYPE[1] + TYPE[2] + TYPE[5] + TYPE[6] + TYPE[7] + TYPE[8] +
                             TYPE[9] + TYPE[10])
        at = 0 if r.random() < 0.7 else r.choice([1, 1, 2])
        c.set(env.settings + SET_AUTOTARGET, u8(at))
        info = {}
        if mode in ('enemy', 'group'):
            blob, combat, cam, sr, cur = aim_env(ctx, env, c, r, slot)
            n = r.choice([0, 1, 1, 2, 2, 3])
            w = mon_world(r, env, c, cam, sr, n)
            groups = rand_groups(r, w, 0 if mode == 'enemy' else 1, 2 if mode == 'enemy' else 3)
            w.write()
            w.groups(groups)
            camp_state(c, env, r, w.mons[0]['loc'] if n else 1, p=0.08)
            info = dict(monsters=n, groups=len(groups), combat=combat, context=cur)
        elif mode == 'indirect':
            info = dict(qualifying=indirect_party(c, env, r))
        c.arg(slot)
        c.arg(spell)
        c.arg(normalize)
        c.note(slot=slot, mode=mode, spell=spell, normalize=normalize, autotarget=at, **info)
        finish(c)


def gen_slot_any(ctx, env):
    """bool SlotHasAnyValidTarget(int slot): per action kind (attack sweep, spell/item asks the
    spell once the selection settled, protect sweeps party members then monsters)."""
    fn = ctx.fn(0x0053cdf0)
    kinds_by = {'attack': [0, 0, 1], 'spell': [7], 'item': [8], 'protect': [5],
                'other': [-1, 2, 3, 4, 6, 9, 10, 11, 12]}
    for i in range(ctx.n(300)):
        r = ctx.rng('slotany', i)
        c = ctx.case('SlotHasAnyValidTarget.%d' % i, fn, conv='c', ret='b')
        slot = r.randrange(8)
        want = r.choice(['attack'] * 3 + ['spell'] * 2 + ['item'] * 2 + ['protect'] * 2 + ['other'])
        spells = TYPE[3] * 3 + TYPE[4] * 2 + [SPELL_RESURRECTION] * 2 + TYPE[1] + TYPE[5] + [0]
        blob, combat, cam, sr, cur = aim_env(ctx, env, c, r, slot, kinds=kinds_by[want], spells=spells)
        combat_state(c, env, r)
        party_occupancy(c, env, r, slot, vitals_p=0.15)
        at = 0 if r.random() < 0.8 else 1
        c.set(env.settings + SET_AUTOTARGET, u8(at))
        n = r.choice([0, 1, 1, 2, 2, 3])
        w = mon_world(r, env, c, cam, sr, n)
        groups = rand_groups(r, w, 0, 2)
        w.write()
        w.groups(groups)
        c.arg(slot)
        c.note(slot=slot, want=want, context=cur, combat=combat, monsters=n, groups=len(groups),
               autotarget=at)
        finish(c)


def place_target_case(r, cam, nav_radius):
    """(point, safe): point for a PLACE target. Far points keep RADIUS/POINT spells off the trace."""
    safe = r.random() < 0.7
    if safe:
        d = r.choice([r.uniform(0.0, 14000.0), 12500.0 + nav_radius + r.choice([-3.0, -0.5, 1.5, 3.0]),
                      r.uniform(12000.0, 30000.0)])
    else:
        d = 25000.0 + 1.0 + nav_radius + r.uniform(500.0, 20000.0)
    a = r.uniform(0.0, 2.0 * math.pi)
    dy = r.uniform(-1500.0, 600.0)
    if abs(dy) > d:
        dy = 0.0
    h = math.sqrt(max(d * d - dy * dy, 0.0))
    return (cam[0] + h * math.cos(a), cam[1] + dy, cam[2] + h * math.sin(a)), safe


def gen_in_play(ctx, env):
    """bool TargetIsInPlay(int slot, int hand, W8TargetingContext context): the stored target
    matches what the chosen action needs (IsTargetStillPresent) and is still in reach."""
    fn = ctx.fn(0x00536f60)
    for i in range(ctx.n(300)):
        r = ctx.rng('inplay', i)
        c = ctx.case('TargetIsInPlay.%d' % i, fn, conv='c', ret='b')
        slot = r.randrange(8)
        party = ctx.set_party(c, r, slots=[slot])
        blob = party[0][1]
        context = r.choice([0, 0, 1, 1, 3, 4, 5, 6, 6, 6, 8, 9, 7])
        combat = rb(r)
        spell = rb(r, 0.2)
        item = rb(r, 0.15)
        modes_state(c, env, combat, spell, item, targeting=r.choice([0, 0, 1, 2, 3, -1]))
        cam, sr = view_state(c, env, r)
        nav_radius = r.choice([0.0, 500.0, 1000.0, round(r.uniform(0.0, 1500.0), 2)])
        c.set(env.nav + NAV_RADIUS, pf(nav_radius))
        kind = r.choice([3, 3, 3, 1, 1, 6, 6, 6, 4, 4, 0, 2, 5, 7, 8, 9, 9])
        spells = items = None
        own = True
        nm = 0
        groups = []
        w = World(env, c)
        if kind in (3, 4):
            nm = r.choice([1, 2, 3])
            w = mon_world(r, env, c, cam, sr, nm)
        if kind == 3:
            mid = w.mons[r.randrange(nm)]['loc'] if r.random() < 0.85 else r.choice([4500, -1])
            tb = target_blob(3, mon=mid)
            spells = TYPE[3] * 3 + TYPE[1] + TYPE[0] + TYPE[4]
        elif kind == 1:
            tchar = r.randrange(8) if r.random() < 0.9 else -1
            tb = target_blob(1, char=tchar)
            spells = TYPE[1] * 2 + TYPE[3] + TYPE[0]
            if tchar >= 0 and tchar != slot and r.random() < 0.4:
                c.set(env.row(tchar), u8(bool_byte(r, 0.8)))
                c.set(env.char(tchar) + C_HP, p32(rand_hp(r, 0.3)))
        elif kind == 9:
            tchar = r.randrange(8) if r.random() < 0.9 else -1
            tb = target_blob(9, char=tchar)
            spells = [SPELL_RESURRECTION] * 4 + TYPE[1]
            if tchar >= 0 and tchar != slot:
                c.set(env.row(tchar), u8(bool_byte(r, 0.85)))
                c.set(env.char(tchar) + C_COND18, p32(r.choice([0, 1, 1, 0x80000000])) +
                      p32(r.choice([0, 0, 0, 1])))
                c.set(env.char(tchar) + C_HP, p32(0 if r.random() < 0.6 else rand_hp(r, 0.0)))
        elif kind == 6:
            point, safe = place_target_case(r, cam, nav_radius)
            if safe:
                spells, items, own = SAFE_PLACE_SPELLS, SAFE_PLACE_ITEMS, False
            else:
                spells = TYPE[6] + TYPE[8] + TYPE[5]
            tb = target_blob(6, point=point)
        elif kind == 4:
            groups = rand_groups(r, w, 1, 2, empty_p=0.1)
            gid = r.choice(groups)['gid'] if r.random() < 0.85 else 999
            tb = target_blob(4, group=gid)
            spells = TYPE[4] * 3 + TYPE[3]
        elif kind == 2:
            tb = target_blob(2, char=r.randrange(8), mon=r.randrange(1, 100), group=r.randrange(100))
            spells = TYPE[4] * 3 + TYPE[3]
        else:
            tb = target_blob(kind, char=r.randrange(8), mon=r.randrange(1, 100), group=r.randrange(100))
        acting_row(c, env, r, slot, blob, targets=tb, occupied=1 if r.random() < 0.95 else 0,
                   spells=spells, items=items, own=own)
        set_hands(c, env.char(slot), r, blob)
        if r.random() < 0.25:
            set_vitals(c, env.char(slot), blob, r.choice([0, 30]), r.choice([0, 0x12]))
        formation_state(c, env, r)
        if context == 6:
            current_ctx(c, env, r, slot, spell, item)
        elif context == 7:
            dialogue_ctx(c, env, r)
        order = list(range(nm))
        r.shuffle(order)
        w.write(list_ks=order)
        if groups:
            w.groups(groups)
        hand = r.choice([0, 0, 1, 1, 2])
        c.arg(slot)
        c.arg(hand)
        c.arg(context)
        c.note(slot=slot, hand=hand, context=context, kind=kind, monsters=nm, combat=combat)
        finish(c)


# ---------------------------------------------------------------- pickers
def gen_pick_group(ctx, env):
    """int PickNextTargetableGroup(int slot): sweep the group list after gXStatus.picked_group
    (an unknown pick resets it to -1)."""
    fn = ctx.fn(0x00537ed0)
    for i in range(ctx.n(250)):
        r = ctx.rng('pickgroup', i)
        c = ctx.case('PickNextTargetableGroup.%d' % i, fn, conv='c', ret='i')
        slot = r.randrange(8)
        blob, combat, cam, sr, cur = aim_env(ctx, env, c, r, slot)
        n = r.choice([1, 2, 2, 3])
        w = mon_world(r, env, c, cam, sr, n)
        groups = rand_groups(r, w, 0 if r.random() < 0.06 else 1, 4, empty_p=0.15)
        w.write()
        w.groups(groups)
        x = r.random()
        if x < 0.35 or not groups:
            picked = r.choice([-1, -1, 999]) if groups else r.choice([-1, 150])
        elif x < 0.8:
            picked = r.choice(groups)['gid']
        else:
            picked = 999
        c.set(env.gx + X_PICKED_GROUP, p32(picked))
        c.cap(env.gx + X_PICKED_GROUP, 4, 'picked_group')
        c.arg(slot)
        c.note(slot=slot, monsters=n, groups=len(groups), picked=picked, combat=combat, context=cur)
        finish(c)


def gen_select_angle(ctx, env):
    """static int SelectNextGroupMemberByAngle(const W8GrowableVector<int>* candidates, int current):
    candidates sorted by whole-degree heading from the camera, the one after `current`."""
    fn = ctx.fn(0x005383e0)
    vec = env.S[7]
    for i in range(ctx.n(250)):
        r = ctx.rng('angle', i)
        c = ctx.case('SelectNextGroupMemberByAngle.%d' % i, fn, conv='c', ret='i')
        cam = rand_cam(r)
        c.set(env.cam, pf(cam[0]) + pf(cam[1]) + pf(cam[2]))
        k = 0 if i < 6 else r.choice([1, 1, 2, 2, 3, 3, 4, 5, 6])
        extra = r.choice([0, 0, 1, 2])
        n = k + extra
        locs = r.sample(range(1, 4000), n + 1)
        degs = r.sample(range(360), n + 1)
        tie = k >= 2 and r.random() < 0.06
        axis = n >= 1 and r.random() < 0.06
        fr = [r.uniform(0.2, 0.8) for _ in range(n + 1)]
        w = World(env, c)
        for m in range(n):
            deg = degs[m] + fr[m]
            if tie and m == 1:
                deg = degs[0] + (fr[0] + 0.15 if fr[0] < 0.5 else fr[0] - 0.15)
            theta = math.radians(deg)
            h = r.uniform(300.0, 30000.0)
            dx, dz = h * math.sin(theta), h * math.cos(theta)
            if axis and m == 0:
                dx, dz = r.choice([h, -h]), 0.0
            pos = (cam[0] + dx, cam[1] + r.uniform(-2000.0, 500.0), cam[2] + dz)
            if axis and m == 0:
                pos = (pos[0], pos[1], cam[2])
            w.add({'loc': locs[m], 'pos': pos})
        order = list(range(n))
        r.shuffle(order)
        w.write(list_ks=order)
        cand = list(range(k))
        r.shuffle(cand)
        cap = k + r.randrange(0, 4)
        c.set(vec + 4, p32(k) + p32(cap))
        c.setp(vec + 0xc, vec + VEC_DATA)
        if k:
            c.set(vec + VEC_DATA, b''.join(p32(locs[j]) for j in cand))
        x = r.random()
        if k == 0 or x < 0.25:
            cur = -1
        elif x < 0.85:
            cur = locs[r.choice(cand)]
        else:
            cur = r.choice([locs[k] if extra else 4500, 4500, 0])
        c.arg(vec)
        c.arg(cur)
        c.note(candidates=k, monsters=n, current=cur)
        if tie:
            c.note(tie=1)
        if axis:
            c.note(axis=1)
        finish(c)


def gen_pick_member(ctx, env):
    """static int PickNextTargetableGroupMember(int slot, W8MonsterGroup* group): members the
    slot can target (CanTargetMonster, single target allowed), stepped from highlighted_member."""
    fn = ctx.fn(0x00538280)
    for i in range(ctx.n(250)):
        r = ctx.rng('pickmember', i)
        c = ctx.case('PickNextTargetableGroupMember.%d' % i, fn, conv='c', ret='i')
        slot = r.randrange(8)
        blob, combat, cam, sr, cur = aim_env(ctx, env, c, r, slot)
        n = r.choice([1, 2, 3, 3, 4])
        w = mon_world(r, env, c, cam, sr, n, headings=True)
        groups = rand_groups(r, w, 1, 2, empty_p=0.08)
        g = r.randrange(len(groups))
        members = groups[g]['members']
        x = r.random()
        if x < 0.3 or not members:
            hl = -1
        elif x < 0.8:
            hl = r.choice(members)
        else:
            others = [m['loc'] for m in w.mons if m['loc'] not in members]
            hl = r.choice(others) if others else 4500
        groups[g]['hl'] = hl
        w.write()
        w.groups(groups)
        camp_state(c, env, r, r.choice(members) if members else 1, p=0.06)
        c.arg(slot)
        c.arg(env.group(g))
        c.note(slot=slot, monsters=n, members=len(members), highlighted=hl, combat=combat, context=cur)
        finish(c)


# ---------------------------------------------------------------- weapon swap gates
def weapon_block(blob, items, bound=None):
    """EquippedItem[6..9] from the corpus blob with iItemNo (and bound byte) overrides."""
    b = bytearray(blob[C_EQUIP + 6 * ITEM:C_EQUIP + 10 * ITEM])
    for j, it in enumerate(items):
        struct.pack_into('<i', b, j * ITEM, it)
        if bound is not None and bound[j] is not None:
            b[j * ITEM + IT_BOUND] = bound[j]
    return bytes(b)


def gen_fallback(ctx, env):
    """int ChooseFallbackMonsterTarget(int slot, int group_id, W8TargetingContext context):
    the gates in front of the weapon-set swap (autoswap, swap in progress, camp item action,
    executing combat row dead with a phase, bound alternate weapons, SwapWeaponSetSlots)."""
    fn = ctx.fn(0x0053c990)
    gates = ['autoswap', 'swapping', 'pending', 'combat', 'bound8', 'bound9']
    for i in range(ctx.n(200)):
        r = ctx.rng('fallback', i)
        c = ctx.case('ChooseFallbackMonsterTarget.%d' % i, fn, conv='c', ret='i')
        slot = r.randrange(8)
        party = ctx.set_party(c, r, slots=[slot])
        blob = party[0][1]
        fail = r.choice(gates + ['none'] * 3)
        fi = gates.index(fail) if fail in gates else len(gates)

        def gate_true(r):
            return 1 if r.random() < 0.85 else r.choice(BOOL_EDGE)

        autoswap = 0 if fail == 'autoswap' else gate_true(r)
        swapping = gate_true(r) if fail == 'swapping' else (0 if fi > 1 else rb(r))
        pending = gate_true(r) if fail == 'pending' else (0 if fi > 2 else rb(r))
        if fail == 'combat' or (fi < 3 and r.random() < 0.3):
            exe, dead = gate_true(r), gate_true(r)
            phase = r.choice([1, 5, 0x80000000, 0xffffffff])
        else:
            which = r.choice(['exe', 'dead', 'phase'])
            exe = 0 if which == 'exe' else rb(r)
            dead = 0 if which == 'dead' else rb(r)
            phase = 0 if which == 'phase' else r.choice([0, 1, 7])
        if fail == 'none':
            items = [-1, -1, -1, -1]
            bound = [None, None, None, None]
        else:
            items = [r.choice(PLAIN_WEAPONS + [-1]) for _ in range(4)]
            bound = [None, None, rb(r, 0.3), rb(r, 0.3)]
            for j, gname in ((2, 'bound8'), (3, 'bound9')):
                if fail == gname:
                    items[j] = r.choice(BINDING_WEAPONS)
                    bound[j] = gate_true(r)
                elif fi > gates.index(gname):     # this gate must pass
                    if r.random() < 0.4:
                        items[j] = r.choice(BINDING_WEAPONS)
                        bound[j] = 0
                    else:
                        items[j] = r.choice(PLAIN_WEAPONS + [-1])
                        bound[j] = r.choice([0, 1, 2])
        c.set(env.settings + SET_AUTOSWAP, u8(autoswap))
        c.set(env.gx + slot * X_ENTRY + X_SWAPPING, u8(swapping))
        c.set(env.row(slot) + R_ITEM_ACTION, u8(pending))
        c.setp(env.cs, env.S[4])
        c.set(env.S[4] + CS_EXEC, u8(exe))
        crow = env.S[4] + CS_CHARS + slot * CS_ROW
        if phase:
            c.set(crow + CS_PHASE, p32(phase))
        if dead:
            c.set(crow + CS_DEAD, u8(dead))
        c.set(env.char(slot) + C_EQUIP + 6 * ITEM, weapon_block(blob, items, bound))
        c.cap(env.char(slot), CHAR, 'char')
        c.cap(env.row(slot), ROW, 'row')
        c.cap(env.gx + slot * X_ENTRY + X_SWAPPING, 1, 'swap_in_progress')
        group_id = r.choice([-1, 0, 5, 150])
        context = r.choice([0, 1, 6])
        c.arg(slot)
        c.arg(group_id)
        c.arg(context)
        c.note(slot=slot, fail=fail, autoswap=autoswap, swapping=swapping, pending=pending,
               exe=exe, dead=dead, phase=phase, weapons=','.join(str(x) for x in items))
        edge_note(c, ['bool_byte'] if any(v not in (0, 1) for v in (autoswap, swapping, pending, exe, dead))
                  else [])
        finish(c)


def gen_reconcile(ctx, env):
    """void ReconcilePartyEquipmentAfterCombat(void): every occupied, living (hp != 0 or
    highest < 13, retail unsigned) slot with weapon_swap_pending, autoswap on and no camp item
    action swaps back and clears the flag. Swapping slots have an empty weapon set."""
    fn = ctx.fn(0x0053cd60)
    for i in range(ctx.n(200)):
        r = ctx.rng('reconcile', i)
        c = ctx.case('ReconcilePartyEquipmentAfterCombat.%d' % i, fn, conv='c', ret='v')
        party = ctx.set_party(c, r)
        autoswap = r.choice([1] * 6 + [0, 0, 2, 0xff])
        c.set(env.settings + SET_AUTOSWAP, u8(autoswap))
        edges = []
        swapping = 0
        for s, blob, _ in party:
            occ = bool_byte(r, 0.85, 0.06)
            hp = 0 if r.random() < 0.3 else r.choice([1, 40, 300, 0x80000000])
            hi = rand_cond(r, 0.06)
            if r.random() < 0.25:
                hi = r.choice([0x0c, 0x0d, 0x0e])
            pend = bool_byte(r, 0.55, 0.1)
            ap = bool_byte(r, 0.15, 0.1)
            gate = occ and (hp != 0 or hi < 13) and pend and autoswap and not ap
            c.set(env.row(s), u8(occ))
            c.set(env.row(s) + R_ITEM_ACTION, u8(ap))
            c.set(env.row(s) + R_SWAP, u8(pend))
            set_vitals(c, env.char(s), blob, hp, hi)
            if gate:
                swapping += 1
                c.set(env.char(s) + C_EQUIP + 6 * ITEM, weapon_block(blob, [-1, -1, -1, -1]))
            if occ not in (0, 1) or pend not in (0, 1) or ap not in (0, 1):
                edges.append('bool_byte')
            if hi >= 0x80000000:
                edges.append('cond_negative')
        for s in range(8):
            c.cap(env.char(s), CHAR, 'char%d' % s)
        c.cap(env.row(0), 8 * ROW, 'xchar')
        c.cap(env.gx, 8 * X_ENTRY, 'entries')
        c.note(autoswap=autoswap, swapping_slots=swapping)
        if autoswap not in (0, 1):
            edges.append('bool_byte')
        edge_note(c, edges)
        finish(c)


# ---------------------------------------------------------------- aim / highlights
def rand_target(r):
    b = target_blob(r.choice([0, 1, 2, 3, 3, 4, 5, 6, 7, 8, 9]), char=r.choice([-1, r.randrange(8)]),
                    mon=r.choice([-1, r.randrange(1, 4000)]), group=r.choice([-1, r.randrange(100, 400)]),
                    point=(r.uniform(-9e4, 9e4), r.uniform(-3e3, 3e3), r.uniform(-9e4, 9e4))
                    if r.random() < 0.6 else (0.0, 0.0, 0.0))
    return b


def gen_aim_target(ctx, env):
    """void AimAtTarget(int actor, W8CombatSlot* target, OUT_OF_COMBAT): bitwise compare
    (REP CMPSD) and copy into the row's out-of-combat block; the other contexts are UI."""
    fn = ctx.fn(0x005387f0)
    tgt = env.S[5] + S5_TARGET
    itp = env.S[5] + S5_ITEMPTR
    for i in range(ctx.n(120)):
        r = ctx.rng('aimooc', i)
        c = ctx.case('AimAtTarget.ooc.%d' % i, fn, conv='c', ret='v')
        actor = r.randrange(8)
        old = rand_target(r)
        x = r.random()
        how = 'random'
        if x < 0.25:
            new = Blob(old)
            how = 'equal'
        elif x < 0.65:
            new = Blob(old)
            f = r.choice(['kind', 'char', 'mon', 'group', 'zero_sign', 'nan_same', 'point'])
            how = f
            if f == 'kind':
                new.u32(0, (old.get_u32(0) + r.choice([1, 2])) % 10)
            elif f == 'char':
                new.u32(4, old.get_u32(4) ^ 1)
            elif f == 'mon':
                new.u32(8, old.get_u32(8) + 1)
            elif f == 'group':
                new.u32(0xc, -1 if old.get_i32(0xc) != -1 else 7)
            elif f == 'zero_sign':        # -0.0 vs +0.0: bits differ, so the block is copied
                old.f32(0x14, 0.0)
                new = Blob(old)
                new.u32(0x14, 0x80000000)
            elif f == 'nan_same':         # identical NaN bits: no change
                old.u32(0x10, 0x7fc00000)
                new = Blob(old)
            else:
                new.f32(0x18, struct.unpack('<f', bytes(old[0x18:0x1c]))[0] + 1.0)
        else:
            new = rand_target(r)
        item_old = rb(r, 0.2)
        item_new = item_old if r.random() < 0.7 else 1 - item_old
        row = env.row(actor)
        c.set(row + R_TARGET_OOC, bytes(old))
        if item_old:
            c.setp(row + R_TARGET_OOC + 0x1c, itp)
        c.set(tgt, bytes(new))
        if item_new:
            c.setp(tgt + 0x1c, itp)
        c.cap(row, ROW, 'row', ignore=[R_TARGET_OOC + 0x1c])
        c.arg(actor)
        c.arg(tgt)
        c.arg(0)
        c.note(actor=actor, change=how, item_old=item_old, item_new=item_new)
        finish(c)


def gen_clear_highlights(ctx, env):
    """void ClearPartySlotMonsterHighlights(unsigned int party_slot): clear the slot's bit in
    every active monster's rep highlight_mask and detach its (absent) marker item."""
    fn = ctx.fn(0x0053AEB0)
    for i in range(ctx.n(200)):
        r = ctx.rng('clearhl', i)
        c = ctx.case('ClearPartySlotMonsterHighlights.%d' % i, fn, conv='c', ret='v')
        slot = r.choice(list(range(8)) * 4 + [8, 9, 31, 32, 33, 39, 0xffffffff, 0x80000000])
        n = r.choice([0, 1, 2, 3, 4, 5, 6])
        locs = r.sample(range(1, 4000), max(n, 1))
        bit = (1 << (slot & 31)) & 0xff
        w = World(env, c)
        for k in range(n):
            mask = r.getrandbits(8)
            if bit and r.random() < 0.6:
                mask |= bit
            elif bit:
                mask &= ~bit & 0xff
            w.add({'loc': locs[k], 'active': bool_byte(r, 0.85, 0.1), 'p3d': r.random() < 0.9,
                   'mask': mask})
        order = list(range(n))
        r.shuffle(order)
        w.write(list_ks=order, reps=True)
        if n:
            c.cap(env.S[6], n * REP_STRIDE, 'reps')
            c.cap(env.S[1], n * P3D_STRIDE, 'p3d')
        c.arg(slot)
        c.note(slot=slot, monsters=n, masks=','.join('%02x' % m['mask'] for m in w.mons))
        finish(c)


def cases(ctx):
    env = Env(ctx)
    gen_participate(ctx, env)
    gen_dead_targetable(ctx, env)
    gen_contexts(ctx, env)
    gen_arcs(ctx, env)
    gen_cone(ctx, env)
    gen_item_use(ctx, env)
    gen_can_target_monster(ctx, env)
    gen_can_target_group(ctx, env)
    gen_spell_any(ctx, env)
    gen_slot_any(ctx, env)
    gen_in_play(ctx, env)
    gen_pick_group(ctx, env)
    gen_select_angle(ctx, env)
    gen_pick_member(ctx, env)
    gen_fallback(ctx, env)
    gen_reconcile(ctx, env)
    gen_aim_target(ctx, env)
    gen_clear_highlights(ctx, env)
