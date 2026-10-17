"""Combat Range.cpp (retail 0x00518e30..0x0051b560): range bands, reach and aim checks.

How the cases are built (everything below is restored by the core after each case)
  * Party: corpus characters (set_party / setb, unmodified blobs only) plus small
    explicit overrides of what these functions read: hp_current/highest_condition,
    the Turncoat duration (uiCondition[13]), bonus.out_of_formation, the two
    W8HandAttack heads (uiHolds/in_play) and EquippedItem[6/7].iItemNo (always a
    valid Items.dbs id whenever a hand holding kind 1/3 is in play - retail reads
    g_item_records[iItemNo] unguarded).
  * XChar rows: the acting slot's row 0x00..0xf1 is written whole (fOccupied,
    pending/combat action, attack_mode[0], spell id, the three detail blocks and the
    five target slots). The detail blocks' item pointers go to scratch item
    instances or to the character's own non-empty equipment, never to an empty item.
    Other slots get fOccupied.
  * g_status.formation (0x84 bytes, only -1/0..7 slot bytes), party_facing, the camera
    position (g_gd_camera->m_position), g_startup_world radii (collision/alternate
    radius, Navigator::radius), gXStatus fCombatMode/fSpellCastMode/fItemSelectMode,
    iTargetingMode and g_combat_state (wired to a scratch W8CombatState) are set in
    every case that reads them. W8_TARGETING_CONTEXT_CURRENT cases pin
    g_level_block->selection_kind/pending_action/selection_settled,
    g_current_screen_state.id and g_status.selected_character so the context resolves
    to OUT_OF_COMBAT/IN_COMBAT/SPELL/ITEM only (SHARED reads UI selection state,
    DIALOGUE hands out a null target block).
  * Fake monster world: W8MonsterInfo blocks in S0 (stride 0x430), W8Monster stubs in
    S1 holding only the navigator position (+0x118), alternate radius (+0x18c) and
    height offset (+0x190) - all GetPosition/GetDistanceTo* read - real MONSTERS.DBS
    attack/spell rows (plus mutations) as W8MonsterRecord in S2 wired through
    gXStatus.monster_record_cache[species]; PList/IList stubs in S3 for
    gXStatus.plsMonsterList, plsMonsterGroupList and the source monster's
    plsVisMonToMon (unborn and encounter lists set to null); W8MonsterCombatState in S4.
  * Databases (for choosing ids): Items.dbs 819 records, MONSTERS.DBS 595, SpellTables
    150 (tables below were extracted from DATA.SLF / Patches\\PATCH.001).

Tested (retail address, function, cases):
  0x00519ac0 GetCharAttackRange                      300
  0x00519ba0 GetBestHandRangeCategory                200
  0x00519be0 RangeCategoryUsesSightCondition         100
  0x0051a730 GetMonsterActionRangeCategory           300
  0x0051a800 GetBestMonsterAttackRange               300
  0x0051a840 GetMonsterBestRangeCategory             300
  0x0051a9a0 CalcRangeDistance(range)                 30  (one int argument, whole domain)
  0x0051aa30 CalcRangeDistance(range, source)        200
  0x0051ab50 CalcRangeDistanceFromParty               60  (one argument + one radius)
  0x0051ae60 AnyoneStandsAhead                       200
  0x0051aec0 CountRowsBetween                        300
  0x0051b000 FrontRankScreens                        300
  0x005197c0 CharacterActionReachesSlot              400
  0x005199f0 GetCharActionRange                      400
  0x0051b0a0 PickReachableSlotByDisposition          300
  0x00518e30 CanPartySlotAttackAnyTarget             400
  0x005194e0 CanPartyMemberAimAtMonster              400
  0x00519180 CharacterActionReachesTarget            400
  0x00519920 IsSlotInRangeOfGroup                    200
  0x00519c00 MonsterAttackReachesAnyone              300
  0x0051a2f0 MonsterAttackReachesCharacter           400
  0x0051a510 MonsterAttackReachesMonster             300
  0x0051ac30 MonsterChooseTarget                     300
  0x0051ad60 FindNearestVisibleGroupMonster          200
  0x00519f80 MonsterActionReachesTarget              300
  0x0051b4e0 SourceActionReachesTarget               200  (80 character sources, 120 monster/other)
  0x0051b420 InitializeMonsterRangeCapabilities      150  (only best attack band <= SHORT)
  0x0051b320 GetMonsterAttackSourceOffset             40  (only kinds other than 1/3)
  0x0051b3f0 TraceModeRejectsNoHit                    40
  0x0051b300 GetMonsterEngagementRange                 2
  0x0051b310 GetGroundTargetRange                      2
  total 7324 (largest case: 67 set-up ops)

Index edge values that stay inside memory the case writes: AnyoneStandsAhead positions
5..38 (and 0x104/0xff02, truncated to a byte) read past bOccupantChar into the formation
block written whole; FrontRankScreens/CharacterActionReachesSlot slots 8/9 read
positions[8/9] inside formation.unknown_74; GetMonsterActionRangeCategory attack 3..7 and
-1 read past attacks[] inside the scratch record.

Skipped:
  0x0051abe0 CloseFormationGap - not in the port map (inlined); its logic runs inside
      MonsterAttackReachesCharacter and MonsterActionReachesTarget, which are tested.

Paths deliberately not reached (would be non-deterministic or crash both identically):
  * notify_failure/notify = true (CanPartyMemberAimAtMonster, IsSlotInRangeOfGroup):
    QueueCharacterEvent allocates and queues a portrait/voice event in the live queue.
    IsSlotInRangeOfGroup uses notify=1 only with unknown group ids (returns before it).
  * CharacterActionReachesTarget with a PLACE target whose spell is RADIUS/POINT and
    the point within range: g_octree->TraceLineOfSight against the live level.
  * GetMonsterAttackSourceOffset kinds 1/3, InitializeMonsterRangeCapabilities with a
    LONG/EXTREME attack, CanMonsterFlee past its cycle check, IsSpellUsableByMonster
    (GetMonsterBestRangeCategory with skip=0, prefer_ranged=1, spell_chance>=80 only
    gets non-aimable spells): all call model/animation virtuals on the W8Monster.
  * Static finding (not testable with stubs): GetMonsterAttackSourceOffset kind 3 whose
    GetSpellPosition fails asserts at line 0x653 in retail (0x0051b38a) but 0x646 in
    the port (both kinds share the port's single srAssertFail).
"""
import math
import struct

from w8diff.api import Blob

MAX_OPS = 96

# ---------------------------------------------------------------- layouts
CHAR = 0x1862
C_IN_PARTY = 0x4
C_GENDER = 0x75
C_TURNCOAT = 0xa01 + 13 * 4         # uiCondition[W8_CONDITION_TURNCOAT]
C_HIGHEST = 0xb01
C_HP = 0xb11
C_EQUIP = 0xf5d                     # W8ItemInstance[12], iItemNo +0
ITEM = 0xc
C_PRIMARY = C_EQUIP + 6 * ITEM
C_HAND = 0x1149                     # W8HandAttack[2]: uiHolds +0, in_play +4
HAND_STEP = 0x5b
C_OOF = 0x17b5                      # bonus.out_of_formation

ST_XCHAR = 0x8
ST_SELECTED = 0x1d
ST_FACING = 0x18d0
ST_FORMATION = 0x23a1               # W8PartyFormationState
FORM_SIZE = 0x84
FORM_POS = 0x14                     # positions[8], stride 0xc

ROW = 0x106                         # W8PartySlotRow
R_PENDING = 0x01
R_MODE0 = 0x05
R_PDETAIL = 0x15
R_ACTION = 0x3d
R_ADETAIL0 = 0x41
R_ADETAIL1 = 0x45
R_SPELL = 0x75
R_SDETAIL = 0x79
R_IDETAIL = 0xa1
ROW_USED = 0xf1
ROW_TARGETS = (0x1d, 0x4d, 0x81, 0xa9, 0xd1)   # out of combat, in combat, spell, item, breath
ITEM_PTRS = (0x19, 0x49, 0xa5)                  # item_use.item of the three detail blocks

X_COMBAT = 0x8dc                    # fCombatMode, fSpellCastMode, fItemSelectMode
X_MONLIST = 0x8f5                   # plsMonsterList, plsMonsterGroupList
X_GROUPLIST = 0x8f9
X_UNBORN = 0x901                    # plsUnbornMonsterList, plsMonsterGroupEncounterList
X_TARGETING = 0x92f
X_RECCACHE = 0xa0f

CS_SIZE = 0xa64
CS_ROUND = 0x4
CS_CHARS = 0x18
CS_ROW = 0xd4
CS_BERSERK = 0x80
CS_ENGAGED = 0xa54

MI_LOC = 0x0
MI_GROUP = 0x4
MI_SPECIES = 0x8
MI_P3D = 0xc
MI_PCOMBAT = 0x10
MI_ACTIVE = 0x14
MI_INCOMBAT = 0x15
MI_DISP = 0x16
MI_HP = 0x2b
MI_TURNCOAT = 0x57 + 13 * 4
MI_HIGHEST = 0x107
MI_PT_SIGHT = 0x28a                 # party_threat.sight_state
MI_PT_LOS = 0x28b
MI_VISLIST = 0x2b6
MI_ACTION = 0x2e1
MI_DETAIL = 0x2e5
MI_PV = 0x348                       # player_visibility (W8VisibilityRecord)
MI_U379 = 0x379
MI_PROJ = 0x37a
MI_U37B = 0x37b
MI_SPELLORG = 0x37c
MI_SIZE = 0x425

VR_SIGHT = 0x4
VR_LOS = 0x5
VR_CANSEE = 0xb
VR_LINE = 0x28
VR_STRIDE = 0x34                    # record is 0x31 bytes

MC_BERSERK = 0x15
MC_COOLDOWN = 0x146
MC_RECONSIDER = 0x152

M3_POS = 0x118
M3_RADIUS = 0x18c
M3_HEIGHT = 0x190

MR_SC = 0xe0
MR_FC = 0xe1
MR_SAK = 0xe3
MR_ATK = 0xe7                       # 3 x 0x22: fHasAttack +0, range_category +3
MR_SPELLS = 0x14d
MR_PREFER = 0x1b9
MR_UNTARGETABLE = 0x24a
MR_FACTION = 0x25f
MR_SIZE = 0x297

CAM_POS = 0x8c                      # GDCamera::m_position
NAV_RADIUS = 0x84                   # W8Navigator::radius
NAV_COLL = 0x170                    # movement.collision_radius, alternate_radius
LVL_KIND = 0x2f0                    # selection_kind, pending_action, selection_settled

# scratch layout
MI_STRIDE = 0x430
P3D_STRIDE = 0x200
REC_STRIDE = 0x300
MCS_BASE = 0x1000
MCS_STRIDE = 0x180
L_MON = 0x0
L_VIS = 0x100
L_VISREC = 0x200
L_GROUP = 0x800
L_GROUPS = 0x900
GROUP_STRIDE = 0x80
S5_OUT = 0x200
S5_TARGET = 0x300
S5_SOURCE = 0x400

WORLD_HEIGHT = 1000.0
BANDS = (1000.0, 2000.0, 12500.0, 25000.0)
N_ITEMS = 819
N_MONSTERS = 595

# ---------------------------------------------------------------- databases
SPELL_RANGE = [0, 2, 0, 2, 2, 2, 2, 2, 0, 2, 2, 2, 2, 2, 3, 3, 2, 0, 0, 1, 0, 1, 2, 0, 3, 2, 0, 1, 2, 3,
               3, 2, 0, 0, 2, 2, 3, 3, 3, 0, 0, 2, 3, 2, 0, 0, 3, 2, 3, 2, 3, 2, 2, 0, 1, 3, 0, 3, 1, 0,
               1, 1, -1, 2, 0, 1, 3, 3, 0, 3, 3, 3, 0, 0, 2, 0, 3, 3, 2, 3, 3, 3, 2, 2, 2, 3, 2, 3, 1, 2,
               3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 2, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 2, 3, -1, 2,
               1, 2, 2, 3, 1, 0, 1, 1, 1, 2, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
SPELL_TARGET = [0, 3, 2, 3, 3, 3, 1, 5, 2, 3, 3, 3, 4, 1, 4, 6, 1, 2, 10, 1, 2, 1, 6, 9, 4, 5, 2, 1, 5, 4,
                6, 5, 2, 2, 1, 1, 6, 4, 8, 10, 2, 3, 6, 5, 2, 2, 4, 5, 6, 5, 3, 1, 5, 2, 1, 6, 2, 6, 1, 2,
                8, 1, 2, 5, 2, 1, 3, 7, 2, 6, 3, 4, 2, 0, 1, 0, 6, 7, 5, 3, 6, 6, 3, 5, 3, 7, 5, 6, 1, 3,
                7, 3, 3, 6, 7, 7, 7, 7, 7, 7, 1, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 7, 6, 5,
                1, 4, 4, 8, 4, 4, 4, 4, 4, 7, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
# item id -> (spell_id, range_category)
ITEM_INFO = {0: (0, 0), 10: (0, 0), 16: (57, 0), 20: (0, 0), 27: (81, 0), 30: (0, 0), 40: (0, 0), 42: (63, 0),
             46: (19, 2), 52: (0, 0), 53: (0, 1), 61: (83, 0), 63: (0, 0), 74: (82, 1), 75: (0, 1),
             79: (0, 1), 83: (0, 1), 86: (93, 1), 87: (3, 1), 91: (0, 1), 95: (0, 1), 99: (0, 2),
             100: (4, 2), 103: (0, 2), 104: (0, 2), 105: (0, 2), 106: (0, 2), 107: (98, 2), 110: (0, 3),
             113: (0, 3), 116: (0, 3), 119: (0, 3), 122: (0, 3), 125: (0, 3), 126: (0, 3), 127: (0, 3),
             128: (0, 3), 129: (0, 3), 130: (0, 3), 131: (0, 3), 132: (0, 3), 133: (0, 3), 134: (0, 3),
             140: (0, 0), 141: (0, 0), 142: (0, 0), 148: (0, 0), 181: (0, 0), 210: (0, 0), 235: (0, 0),
             243: (0, 0), 254: (68, 0), 257: (72, 0), 258: (60, 2), 260: (65, 0), 264: (115, 2),
             269: (116, 2), 273: (56, 0), 278: (6, 0), 285: (90, 0), 292: (71, 0), 306: (30, 2), 313: (0, 0),
             320: (14, 0), 323: (68, 0), 326: (2, 0), 329: (56, 0), 331: (39, 0), 332: (115, 0), 333: (0, 0),
             336: (6, 0), 339: (100, 0), 340: (130, 0), 342: (34, 0), 345: (13, 0), 348: (51, 0),
             351: (81, 2), 354: (57, 2), 357: (63, 2), 360: (15, 2), 363: (85, 2), 368: (44, 0),
             369: (26, 0), 372: (56, 0), 375: (3, 0), 378: (58, 0), 381: (98, 0), 384: (40, 0), 387: (67, 0),
             390: (37, 0), 393: (32, 0), 396: (36, 0), 399: (85, 0), 402: (88, 0), 405: (24, 0), 408: (68, 0),
             410: (114, 0), 411: (115, 0), 416: (115, 0), 419: (41, 0), 421: (0, 0), 424: (0, 3), 428: (35, 0),
             437: (8, 0), 440: (6, 0), 443: (13, 0), 447: (14, 0), 464: (81, 2), 465: (78, 0), 466: (62, 1),
             467: (0, 0), 469: (92, 1), 476: (10, 0), 479: (21, 0), 482: (25, 0), 488: (120, 0), 499: (54, 0),
             516: (30, 0), 519: (33, 0), 522: (36, 0), 525: (40, 0), 528: (43, 0), 531: (47, 0), 534: (50, 0),
             537: (53, 0), 540: (57, 0), 543: (61, 0), 546: (64, 0), 549: (67, 0), 552: (70, 0), 555: (73, 0),
             558: (76, 0), 562: (0, 1), 566: (0, 1), 573: (0, 0), 585: (59, 0), 590: (14, 0), 593: (5, 0),
             599: (0, 3), 602: (0, 3), 605: (0, 3), 608: (0, 3), 614: (0, 0), 625: (0, 0), 659: (56, 0),
             660: (0, 0), 681: (0, 0), 682: (11, 0), 685: (17, 0), 688: (45, 0), 691: (64, 0), 694: (70, 0),
             697: (79, 0), 700: (101, 0), 709: (42, 0), 741: (130, 0), 744: (33, 0), 762: (0, 2), 763: (0, 2),
             764: (0, 2), 770: (81, 1), 804: (114, 0), 818: (69, 0)}
WEAPON_IDS = [0, 10, 20, 30, 40, 52, 63, 465, 660, 681,          # short weapons, band 0
              53, 75, 79, 83, 87, 91, 95, 466, 562, 770,          # extended, band 1
              99, 103, 104, 105, 106, 107, 762, 763, 764,         # thrown, band 2
              110, 113, 116, 119, 122, 424, 599, 602, 605, 608,   # ranged, band 3
              140, 141, 467, 614, 625, 125, 126, 127, 128, 129]   # ammunition, 0/3
OTHER_ITEMS = [142, 148, 181, 210, 235, 243, 254, 313, 320, 682, 331, 100, 260, 46, 258, 573, 269, 368,
               410, 340, 421, 333, 566, 818]
SPELL_ITEMS = sorted(k for k, v in ITEM_INFO.items() if v[0])
PLAIN_ITEMS = sorted(k for k, v in ITEM_INFO.items() if not v[0])
# PLACE targets: the line-of-sight trace runs for RADIUS (6) and POINT (8) spells
SAFE_PLACE_SPELLS = [s for s in range(150) if SPELL_TARGET[s] not in (6, 8)]
SAFE_PLACE_ITEMS = [k for k in ITEM_INFO if SPELL_TARGET[ITEM_INFO[k][0]] not in (6, 8)]
REAL_SPELLS = list(range(1, 102)) + list(range(114, 132))
AIMABLE = [s for s in range(150) if 3 <= SPELL_TARGET[s] <= 7 and s not in (3, 41)]
NON_AIMABLE = [s for s in range(150) if s not in AIMABLE]

# MONSTERS.DBS rows: (record, attacks 'hr'x3, spell_chance, flee_chance, special_attack_kind,
#                     prefer_ranged_actions, untargetable, faction_id, spells[10])
MONSTERS = [
    (0, '101000', 0, 0, 0, 0, 0, 9, [24, 43, 59, 46, 14, 52, 29, 28, 11, 11]),
    (1, '100000', 0, 80, 15, 0, 0, 0, [0] * 10),
    (2, '101000', 30, 0, 0, 1, 0, 4, [59] * 10),
    (3, '101200', 0, 0, 0, 1, 0, 0, [0] * 10),
    (4, '100000', 0, 0, 0, 0, 0, 0, [0] * 10),
    (5, '100003', 85, 0, 0, 1, 0, 0, [69, 68, 53, 28, 66, 49, 47, 89, 98, 98]),
    (6, '100000', 0, 99, 25, 0, 0, 0, [0] * 10),
    (7, '100000', 0, 80, 31, 1, 0, 10, [0] * 10),
    (8, '100000', 0, 80, 25, 1, 0, 0, [0] * 10),
    (9, '101013', 0, 0, 0, 1, 0, 4, [0] * 10),
    (10, '110003', 70, 0, 0, 0, 0, 6, [29, 6, 12, 28, 10, 14, 24, 12, 10, 10]),
    (11, '000000', 0, 0, 0, 1, 1, 1, [0] * 10),
    (12, '100303', 0, 0, 0, 0, 0, 10, [0] * 10),
    (13, '100003', 0, 0, 0, 0, 1, 0, [6, 21, 32, 11, 11, 11, 11, 31, 31, 31]),
    (14, '100000', 0, 50, 7, 0, 0, 0, [0] * 10),
    (15, '100013', 0, 0, 0, 1, 0, 15, [0] * 10),
    (16, '100012', 0, 0, 0, 1, 0, 0, [0] * 10),
    (17, '100000', 80, 0, 5, 1, 0, 0, [5, 5, 46, 15, 24, 10, 10, 11, 37, 37]),
    (18, '100000', 0, 30, 7, 0, 0, 0, [0] * 10),
    (22, '110000', 0, 0, 0, 0, 0, 0, [0] * 10),
    (33, '100000', 0, 0, 0, 0, 0, 0, [63] * 10),
    (36, '100000', 0, 0, 0, 0, 0, 0, [36] * 10),
    (49, '100002', 0, 0, 0, 0, 0, 0, [0] * 10),
    (50, '110003', 90, 0, 0, 1, 0, 15, [20, 40, 69, 31, 66, 28, 50, 67, 36, 36]),
    (53, '111003', 80, 0, 0, 0, 0, 5, [1, 53, 27, 15, 50, 1, 79, 42, 7, 7]),
    (55, '101200', 0, 0, 0, 1, 0, 0, [0] * 10),
    (57, '111013', 0, 0, 0, 1, 0, 5, [24, 71, 37, 37, 43, 43, 43, 10, 10, 10]),
    (58, '131013', 25, 0, 0, 1, 0, 5, [24, 71, 37, 37, 43, 43, 43, 10, 10, 10]),
    (60, '101002', 0, 0, 0, 0, 0, 0, [0] * 10),
    (65, '100212', 0, 0, 0, 1, 0, 0, [0] * 10),
    (66, '101003', 0, 0, 0, 0, 0, 0, [0] * 10),
    (68, '000003', 80, 20, 6, 1, 0, 0, [54, 32, 46, 43, 5, 36, 36, 24, 14, 14]),
    (71, '101212', 0, 0, 0, 1, 0, 0, [0] * 10),
    (76, '100000', 95, 0, 0, 1, 0, 0, [80, 29, 27, 11, 76, 1, 57, 42, 48, 48]),
    (78, '100000', 20, 0, 0, 1, 0, 15, [26, 50, 36, 47, 31, 5, 42, 28, 25, 25]),
    (79, '000013', 80, 20, 6, 1, 0, 0, [54, 69, 14, 24, 46, 24, 89, 24, 24, 24]),
    (85, '000003', 80, 20, 6, 1, 0, 0, [32, 37, 54, 57, 63, 66, 24, 52, 47, 47]),
    (86, '100000', 98, 0, 0, 1, 0, 0, [83, 81, 80, 87, 78, 67, 76, 36, 95, 95]),
    (96, '100200', 0, 70, 18, 0, 0, 0, [0] * 10),
    (99, '101000', 25, 0, 0, 1, 0, 0, [14, 29, 24, 14, 12, 11, 29, 14, 12, 12]),
    (103, '100312', 20, 0, 0, 1, 0, 15, [2, 68, 32, 9, 69, 83, 46, 70, 31, 31]),
    (104, '110103', 85, 0, 0, 1, 0, 1, [77, 68, 2, 46, 63, 70, 31, 83, 9, 9]),
    (105, '110000', 75, 0, 0, 1, 0, 0, [68, 56, 2, 46, 31, 83, 60, 78, 96, 96]),
    (108, '100000', 0, 99, 0, 0, 0, 0, [0] * 10),
    (110, '110012', 50, 0, 0, 1, 0, 0, [49, 6, 46, 15, 50, 14, 4, 28, 5, 5]),
    (111, '110000', 0, 70, 9, 1, 0, 0, [0] * 10),
    (116, '110012', 50, 50, 17, 1, 0, 0, [54, 14, 24, 10, 85, 52, 89, 71, 86, 86]),
    (118, '110013', 20, 30, 12, 1, 0, 0, [24, 99, 72, 81, 89, 54, 80, 94, 97, 97]),
    (125, '100000', 50, 0, 0, 1, 0, 0, [15, 81, 53, 36, 36, 36, 81, 81, 81, 81]),
    (132, '000013', 0, 0, 0, 1, 0, 4, [0] * 10),
    (136, '100012', 0, 90, 20, 1, 0, 0, [1] * 10),
    (151, '110003', 90, 0, 0, 1, 0, 16, [20, 40, 69, 31, 66, 28, 50, 81, 25, 25]),
    (152, '111113', 0, 0, 0, 1, 0, 0, [0] * 10),
    (165, '101200', 0, 50, 14, 1, 0, 0, [0] * 10),
    (167, '101312', 0, 35, 16, 1, 0, 0, [0] * 10),
    (174, '100000', 30, 0, 0, 1, 1, 3, [99, 70, 91, 69, 96, 85, 80, 46, 95, 95]),
    (176, '100000', 80, 0, 0, 1, 1, 3, [97, 94, 91, 89, 54, 86, 71, 24, 97, 97]),
    (178, '100003', 20, 0, 0, 1, 0, 17, [72, 68, 40, 31, 63, 63, 70, 70, 83, 83]),
    (179, '100300', 0, 70, 9, 1, 0, 0, [0] * 10),
    (180, '100300', 70, 20, 9, 1, 0, 0, [49, 56, 77, 87, 71, 52, 36, 81, 79, 79]),
    (187, '100000', 95, 0, 0, 0, 0, 0, [59, 20, 54, 14, 52, 63, 66, 46, 86, 86]),
    (188, '000013', 80, 20, 6, 1, 0, 0, [65, 40, 68, 87, 53, 55, 67, 83, 92, 92]),
    (194, '101313', 50, 40, 28, 1, 1, 0, [99, 86, 54, 81, 95, 85, 92, 98, 97, 97]),
    (205, '110103', 85, 0, 29, 1, 0, 1, [15, 1, 1, 6, 32, 6, 11, 28, 9, 9]),
    (211, '110000', 80, 10, 26, 1, 0, 1, [89, 76, 98, 81, 54, 50, 46, 36, 25, 25]),
    (212, '100000', 8, 90, 26, 1, 1, 1, [20, 20, 31, 31, 31, 31, 31, 25, 25, 25]),
    (213, '100012', 5, 0, 0, 1, 1, 1, [60] * 10),
    (217, '100003', 40, 50, 27, 1, 0, 1, [69, 68, 53, 98, 89, 15, 79, 81, 36, 36]),
    (218, '100000', 0, 30, 29, 1, 0, 1, [0] * 10),
    (220, '111113', 0, 0, 0, 0, 0, 1, [0] * 10),
    (230, '100003', 85, 0, 0, 1, 0, 0, [28, 12, 20, 31, 28, 37, 14, 47, 4, 4]),
    (236, '110103', 85, 0, 0, 0, 1, 1, [15, 1, 1, 6, 32, 6, 11, 28, 9, 9]),
    (245, '100000', 95, 0, 5, 1, 0, 0, [54, 29, 49, 14, 48, 36, 24, 28, 10, 10]),
    (249, '100003', 80, 0, 29, 1, 0, 13, [15, 53, 6, 42, 50, 48, 12, 7, 1, 1]),
    (254, '101313', 0, 35, 0, 1, 0, 0, [0] * 10),
    (255, '101212', 0, 60, 2, 1, 0, 0, [0] * 10),
    (263, '011103', 40, 0, 0, 1, 0, 6, [2, 15, 9, 90, 29, 90, 37, 4, 13, 4]),
    (276, '130000', 0, 0, 0, 1, 0, 0, [0] * 10),
    (277, '110000', 95, 0, 0, 1, 0, 15, [2, 21, 40, 6, 63, 63, 46, 69, 9, 9]),
    (288, '101003', 90, 0, 0, 1, 0, 0, [29, 49, 24, 4, 47, 46, 36, 14, 25, 25]),
    (292, '100003', 40, 50, 27, 1, 1, 1, [69, 68, 53, 98, 89, 15, 79, 81, 36, 36]),
    (305, '111103', 0, 60, 19, 0, 0, 0, [0] * 10),
    (307, '011103', 70, 0, 0, 1, 0, 6, [37, 15, 9, 90, 29, 90, 37, 4, 36, 36]),
    (325, '110103', 0, 90, 9, 1, 0, 0, [0] * 10),
    (333, '111103', 0, 80, 11, 0, 0, 0, [1] * 10),
    (342, '111100', 40, 0, 0, 1, 0, 0, [14, 69, 94, 93, 80, 24, 25, 76, 83, 83]),
    (348, '101200', 95, 0, 0, 1, 0, 15, [2, 21, 6, 46, 31, 68, 63, 63, 9, 9]),
    (350, '100010', 0, 0, 0, 0, 0, 0, [0, 0, 0, 0, 13, 0, 0, 0, 0, 0]),
    (354, '100303', 20, 0, 29, 1, 0, 13, [6, 40, 44, 61, 46, 46, 63, 31, 9, 9]),
    (356, '100000', 0, 0, 0, 0, 205, 0, [0] * 10),
    (373, '110003', 0, 40, 24, 0, 1, 0, [13, 14, 2, 6, 18, 12, 7, 10, 129, 18]),
    (378, '111003', 80, 0, 6, 0, 0, 5, [89, 86, 56, 54, 43, 71, 28, 46, 29, 29]),
    (382, '101012', 0, 0, 0, 0, 0, 0, [1] * 10),
    (394, '100303', 20, 20, 25, 1, 0, 0, [57, 15, 4, 37, 28, 32, 86, 86, 48, 48]),
    (396, '100001', 50, 50, 20, 1, 1, 1, [20, 56, 61, 36, 48, 83, 55, 79, 1, 1]),
    (397, '110003', 40, 80, 27, 1, 0, 17, [89, 68, 69, 50, 55, 66, 76, 90, 81, 81]),
    (406, '101000', 100, 0, 0, 0, 1, 1, [1] * 10),
    (409, '111103', 50, 70, 8, 1, 0, 0, [65, 49, 53, 69, 78, 92, 80, 48, 95, 95]),
    (419, '110100', 30, 0, 0, 1, 0, 9, [11, 89, 91, 46, 24, 46, 29, 43, 10, 10]),
    (428, '100000', 20, 0, 26, 1, 0, 16, [26, 40, 29, 47, 27, 80, 69, 15, 55, 55]),
    (436, '100001', 50, 50, 20, 1, 0, 1, [68, 56, 61, 55, 76, 83, 55, 79, 50, 50]),
    (438, '101313', 50, 40, 28, 1, 0, 0, [99, 86, 54, 81, 95, 85, 92, 98, 97, 97]),
    (440, '130000', 0, 0, 0, 1, 0, 2, [0] * 10),
    (442, '101010', 0, 0, 26, 0, 0, 15, [0] * 10),
    (465, '101202', 0, 60, 13, 0, 0, 0, [0] * 10),
    (475, '101003', 30, 0, 0, 0, 0, 0, [129, 129, 129, 13, 13, 13, 13, 13, 13, 13]),
    (477, '101100', 90, 0, 0, 1, 0, 0, [6, 46, 56, 99, 97, 69, 70, 86, 71, 71]),
    (486, '130000', 50, 0, 0, 1, 0, 0, [80, 85, 53, 42, 80, 76, 57, 57, 50, 50]),
    (500, '100003', 0, 50, 4, 0, 0, 0, [0] * 10),
    (528, '101003', 90, 0, 0, 0, 0, 0, [29, 49, 24, 7, 1, 46, 48, 14, 42, 42]),
    (538, '000010', 0, 0, 0, 0, 0, 15, [0] * 10),
    (546, '110003', 0, 90, 24, 0, 0, 0, [13, 14, 2, 6, 18, 12, 7, 10, 129, 18]),
    (555, '100003', 30, 70, 27, 1, 0, 1, [69, 68, 53, 98, 89, 15, 79, 81, 36, 36]),
    (564, '101313', 70, 75, 28, 1, 0, 0, [99, 68, 54, 81, 95, 85, 92, 98, 97, 97]),
    (583, '110100', 30, 0, 0, 1, 0, 0, [68, 2, 32, 46, 31, 61, 70, 63, 9, 9]),
    (594, '100000', 0, 0, 0, 0, 1, 0, [0] * 10),
]
NEUTRAL_SPECIES = 0x224             # MonsterHostility answers neutral for it


# ---------------------------------------------------------------- helpers
def p32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def pf(v):
    return struct.pack('<f', float(v))


def rb(r, p=0.5):
    return 1 if r.random() < p else 0


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
        self.lvl = ctx.g('g_level_block').deref()
        self.screen = ctx.g('g_current_screen_state')
        self.flee_flag = ctx.g('g_special_attack_cycle_error_reported')

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

    def mcs(self, k):
        return self.S[4] + MCS_BASE + k * MCS_STRIDE


ACTION_KINDS = [-1, 0, 0, 0, 1, 1, 2, 3, 4, 5, 5, 6, 7, 7, 7, 7, 8, 8, 8, 9, 10, 11, 12]
MON_ACTIONS = [-1, 0, 0, 0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9, 10]
HOLDS = [0, 0, 1, 1, 1, 2, 3, 3, 4, 5, -1]
RANGE_ARGS = [-1, 0, 1, 2, 3]
RANGE_EDGES = [-3, -2, 4, 5, 100, 0x7fffffff, -0x80000000]


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
    k = r.random()
    if k < 0.7:
        return r.choice(SPELL_ITEMS)
    if k < 0.9:
        return r.choice(PLAIN_ITEMS)
    return r.randrange(N_ITEMS)


def rand_cam(r):
    return (round(r.uniform(-80000.0, 80000.0), 2), round(r.uniform(-2000.0, 8000.0), 2),
            round(r.uniform(-80000.0, 80000.0), 2))


def place(r, cam, mr, sr):
    """A monster navigator position whose GetDistanceToPlayer often sits near a band edge."""
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
    a = r.uniform(0.0, 2.0 * math.pi)
    return (cam[0] + h * math.cos(a), cam[1] - WORLD_HEIGHT + dy, cam[2] + h * math.sin(a))


def rand_mon(r, loc, species, cam, sr):
    mr = r.choice([0.0, 150.0, 300.0, 500.0, 750.0, round(r.uniform(50.0, 1500.0), 2)])
    m = {
        'loc': loc, 'group': r.choice([0, 1, 7]), 'species': species,
        'active': rb(r, 0.92), 'incombat': rb(r, 0.65),
        'disp': 3 if r.random() < 0.03 else r.choice([0, 1, 1, 1, 2, 2]),
        'hp': 0 if r.random() < 0.08 else r.choice([1, 9, 60, 400]),
        'highest': 0 if r.random() < 0.8 else r.choice([1, 8, 0x11, 0x12, 0x13]),
        'turncoat': 0 if r.random() < 0.85 else r.choice([1, 30, 0xffffffff]),
        'pt_sight': r.choice([0, 1, 1, 1, 1, 2]), 'pt_los': (rb(r, 0.75), rb(r, 0.75)),
        'action': r.choice(MON_ACTIONS), 'detail': 0,
        'pv_sight': r.choice([0, 1, 1, 1, 1, 2]), 'pv_los': tuple(rb(r, 0.75) for _ in range(4)),
        'cansee': rb(r, 0.7), 'line': rb(r, 0.7), 'proj': rb(r), 'spellorg': rb(r),
        'pos': place(r, cam, mr, sr), 'radius': mr, 'height': round(r.uniform(0.0, 1800.0), 1),
        'berserk': rb(r, 0.15), 'reconsider': rb(r, 0.5), 'cooldown': 0,
    }
    m['detail'] = rand_spell(r) if m['action'] == 2 else r.choice([0, 1, 2, 3])
    return m


def mblob(m):
    b = Blob(0x37d)
    b.u32(MI_LOC, m.get('loc', 0))
    b.u32(MI_GROUP, m.get('group', 0))
    b.u32(MI_SPECIES, m.get('species', 0))
    b.u8(MI_ACTIVE, m.get('active', 1))
    b.u8(MI_INCOMBAT, m.get('incombat', 0))
    b.u8(MI_DISP, m.get('disp', 1))
    b.u32(MI_HP, m.get('hp', 10))
    b.u32(MI_TURNCOAT, m.get('turncoat', 0))
    b.u32(MI_HIGHEST, m.get('highest', 0))
    b.u8(MI_PT_SIGHT, m.get('pt_sight', 1))
    los = m.get('pt_los', (1, 1))
    b.u8(MI_PT_LOS, los[0])
    b.u8(MI_PT_LOS + 1, los[1])
    b.u32(MI_ACTION, m.get('action', 0))
    b.u32(MI_DETAIL, m.get('detail', 0))
    b.u8(MI_PV + VR_SIGHT, m.get('pv_sight', 1))
    for j, v in enumerate(m.get('pv_los', (1, 1, 1, 1))):
        b.u8(MI_PV + VR_LOS + j, v)
    b.u8(MI_PV + VR_CANSEE, m.get('cansee', 1))
    b.u8(MI_PV + VR_LINE, m.get('line', 1))
    b.u8(MI_U379, m.get('u379', 0))
    b.u8(MI_PROJ, m.get('proj', 0))
    b.u8(MI_U37B, m.get('u37b', 0))
    b.u8(MI_SPELLORG, m.get('spellorg', 0))
    return b


def p3dblob(m):
    b = Blob(M3_HEIGHT + 4)
    x, y, z = m.get('pos', (0.0, 0.0, 0.0))
    b.f32(M3_POS, x)
    b.f32(M3_POS + 4, y)
    b.f32(M3_POS + 8, z)
    b.f32(M3_RADIUS, m.get('radius', 0.0))
    b.f32(M3_HEIGHT, m.get('height', 0.0))
    return b


def mcsblob(m):
    b = Blob(MC_RECONSIDER + 1)
    b.u8(MC_BERSERK, m.get('berserk', 0))
    b.u8(MC_COOLDOWN, m.get('cooldown', 0))
    b.u8(MC_RECONSIDER, m.get('reconsider', 0))
    return b


def rec_blob(row):
    _, atk, sc, fc, sak, pra, unt, fac, spells = row
    b = Blob(MR_SIZE)
    b.u8(MR_SC, sc)
    b.u8(MR_FC, fc)
    b.u8(MR_SAK, sak)
    for a in range(3):
        b.u8(MR_ATK + a * 0x22, int(atk[2 * a]))
        b.u8(MR_ATK + a * 0x22 + 3, int(atk[2 * a + 1]))
    b[MR_SPELLS:MR_SPELLS + 10] = bytes(spells)
    b.u8(MR_PREFER, pra)
    b.u8(MR_UNTARGETABLE, unt)
    b.u32(MR_FACTION, fac)
    return b


def mutate_rec(r, b, p=0.35):
    """Random edits around the comparisons the range code makes."""
    if r.random() < p:
        a = r.randrange(3)
        b.u8(MR_ATK + a * 0x22, r.choice([0, 1, 1, 2, 0xff]))
    if r.random() < p:
        a = r.randrange(3)
        b.u8(MR_ATK + a * 0x22 + 3, r.choice([0, 1, 2, 3, 3, 4, 0x7f, 0x80, 0xff]))
    if r.random() < p * 0.5:
        b.u8(MR_UNTARGETABLE, r.choice([0, 1, 2, 0xff]))
    if r.random() < p * 0.5:
        b.u32(MR_FACTION, r.choice([0, 1, 5, 9, 15]))
    return b


def rand_rec(r, p=0.35):
    return mutate_rec(r, rec_blob(r.choice(MONSTERS)), p)


def best_attack_index(r, rec):
    have = [a for a in range(3) if rec[MR_ATK + a * 0x22]]
    if have and r.random() < 0.85:
        return r.choice(have)
    return r.choice([0, 1, 2, 3, 0xffffffff])


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


def party_state(c, env, r, party, skip_rows=(), change_p=0.3, turncoat_p=0.12, occupied_p=0.9):
    for slot, blob, _ in party:
        if slot not in skip_rows:
            c.set(env.row(slot), b'\x01' if r.random() < occupied_p else b'\x00')
        if r.random() < change_p:
            hp = 0 if r.random() < 0.35 else r.choice([1, 7, 120])
            hi = 0 if r.random() < 0.5 else r.choice([1, 0x0c, 0x0d, 0x11, 0x12, 0x13])
            set_vitals(c, env.char(slot), blob, hp, hi)
        if r.random() < turncoat_p:
            c.set(env.char(slot) + C_TURNCOAT, p32(r.choice([1, 12, 0xffffffff])))


def rand_formation(r):
    occ = [[-1] * 3 for _ in range(5)]
    pos = []
    for s in range(8):
        free = [(q, i) for q in range(5) for i in range(3) if occ[q][i] == -1]
        if free and r.random() < 0.88:
            q, i = r.choice(free)
            if r.random() < 0.3:  # bias towards the front rank (row 4) and the 0/2, 1/3 pairs
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


def formation_state(c, env, r, oof_p=0.15, all_slots=False):
    c.set(env.st + ST_FORMATION, bytes(rand_formation(r)))
    for s in range(8):
        if all_slots or r.random() < oof_p:
            c.set(env.char(s) + C_OOF, b'\x01' if r.random() < (0.3 if all_slots else 0.6) else b'\x00')


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


def combat_state(c, env, r):
    c.setp(env.cs, env.S[4])
    b = Blob(CS_SIZE)
    b.u32(CS_ROUND, r.choice([0, 1, 1, 2, 5]))
    for s in range(8):
        if r.random() < 0.12:
            b.u8(CS_CHARS + s * CS_ROW + CS_BERSERK, 1)
    b.u8(CS_ENGAGED, rb(r, 0.5))
    emit(c, env.S[4], b)


def current_ctx(c, env, r, slot, spell, item):
    """Pin W8_TARGETING_CONTEXT_CURRENT to OUT/IN_COMBAT, SPELL or ITEM (never SHARED/DIALOGUE)."""
    k = r.random()
    if k < 0.6:
        c.set(env.lvl + LVL_KIND, p32(-1))
        if not spell and not item and r.random() < 0.5:
            sel = slot
        else:
            sel = r.choice([-1, (slot + 1) % 8, 9])
    else:
        c.set(env.screen, p32(7))
        c.set(env.lvl + LVL_KIND, p32(7 if k < 0.8 else 8) + p32(rand_spell(r)) + b'\x01')
        sel = r.choice([-1, slot])
    c.set(env.st + ST_SELECTED, p32(sel))


def dialogue_ctx(c, env, r):
    """W8_TARGETING_CONTEXT_DIALOGUE: kind/value from the level block (never USE_ITEM: null detail)."""
    c.set(env.lvl + LVL_KIND, p32(r.choice([-1, 0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11])) + p32(rand_spell(r)))


def context_setup(c, env, r, context, slot, spell=0, item=0):
    if context == 6:
        current_ctx(c, env, r, slot, spell, item)
    elif context == 7:
        dialogue_ctx(c, env, r)


def acting_row(c, env, r, slot, blob, targets=None, occupied=1, spells=None, items=None, own=True):
    b = Blob(ROW_USED)
    b.u8(0, occupied)
    b.u32(R_PENDING, r.choice(ACTION_KINDS))
    b.u32(R_MODE0, rand_spell(r, spells))
    b.u32(R_PDETAIL, r.randrange(4))
    b.u32(R_ACTION, r.choice(ACTION_KINDS))
    b.u32(R_ADETAIL0, rand_spell(r, spells))
    b.u32(R_ADETAIL1, r.randrange(4))
    b.u32(R_SPELL, rand_spell(r, spells))
    b.u32(R_SDETAIL, r.randrange(1, 8))
    b.u32(R_IDETAIL, r.randrange(4))
    for off in ROW_TARGETS:
        if targets is not None:
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
            c.setp(env.row(slot) + off, env.S[5] + j * 0x10)
    emit(c, env.S[5], ib)


class World:
    """Fake monsters, records and lists in scratch for one case."""

    def __init__(self, env, c):
        self.env = env
        self.c = c
        self.mons = []
        self.recs = []

    def add(self, m):
        self.mons.append(m)
        return len(self.mons) - 1

    def record(self, species, blob):
        self.recs.append((species, blob))
        return self.env.rec(len(self.recs) - 1)

    def write(self, list_ks=(), p3d=True, pcombat=()):
        env, c = self.env, self.c
        for k, m in enumerate(self.mons):
            emit(c, env.mon(k), mblob(m), gap=112)
            if p3d and m.get('p3d', True):
                emit(c, env.p3d(k), p3dblob(m), gap=128)
                c.setp(env.mon(k) + MI_P3D, env.p3d(k))
            if k in pcombat:
                emit(c, env.mcs(k), mcsblob(m))
                c.setp(env.mon(k) + MI_PCOMBAT, env.mcs(k))
        for j, (species, blob) in enumerate(self.recs):
            emit(c, env.rec(j), blob, gap=0x70)
            if species is not None:
                c.setp(env.gx + X_RECCACHE + 4 * species, env.rec(j))
        c.set(env.gx + X_MONLIST, bytes(8))
        c.set(env.gx + X_UNBORN, bytes(8))
        if list_ks:
            hdr = env.S[3] + L_MON
            c.set(hdr + 4, p32(len(list_ks) + 4) + p32(len(list_ks)))
            c.setp(hdr, hdr + 0x10)
            for i, k in enumerate(list_ks):
                c.setp(hdr + 0x10 + 4 * i, env.mon(k))
            c.setp(env.gx + X_MONLIST, hdr)

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

    def groups(self, groups):
        env, c = self.env, self.c
        hdr = env.S[3] + L_GROUP
        c.set(hdr + 4, p32(len(groups) + 2) + p32(len(groups)))
        if groups:
            c.setp(hdr, hdr + 0x10)
        for g, (gid, members) in enumerate(groups):
            G = env.S[3] + L_GROUPS + g * GROUP_STRIDE
            b = Blob(0x1c + 4 * len(members))
            b.u32(0, gid)
            b.u32(4, len(members))
            b.u32(0x14, len(members) + 2)
            b.u32(0x18, len(members))
            for t, mid in enumerate(members):
                b.u32(0x1c + 4 * t, mid)
            c.set(G, bytes(b))
            c.setp(G + 8, G + 0x10)
            if members:
                c.setp(G + 0x10, G + 0x1c)
            c.setp(hdr + 0x10 + 4 * g, G)
        c.setp(env.gx + X_GROUPLIST, hdr)


def rand_vis(r, about):
    return {'about': about, 'sight': r.choice([0, 1, 1, 1, 2]), 'los': tuple(rb(r, 0.75) for _ in range(4)),
            'cansee': rb(r, 0.7), 'line': rb(r, 0.7)}


def vis_entries(r, world, source_k, others):
    """The source monster's mon-to-mon records: most others, some strangers, a null entry."""
    entries = []
    for k in others:
        if r.random() < 0.85:
            entries.append(rand_vis(r, world.mons[k]['loc']))
    if r.random() < 0.3:
        entries.append(rand_vis(r, r.randrange(5000, 6000)))
    if r.random() < 0.08:
        entries.append(None)
    r.shuffle(entries)
    return entries


def mon_world(r, env, c, cam, sr, n, species_pool=None, records=True, mutate=0.35):
    """n monsters with distinct location ids and species, each with its own record."""
    w = World(env, c)
    locs = r.sample(range(1, 4000), n)
    pool = species_pool or list(range(N_MONSTERS))
    species = r.sample(pool, n)
    if n >= 2 and r.random() < 0.08:
        species[1] = NEUTRAL_SPECIES
        if species[0] == NEUTRAL_SPECIES:
            species[0] = 1
    for k in range(n):
        w.add(rand_mon(r, locs[k], species[k], cam, sr))
        if records:
            w.record(species[k], rand_rec(r, mutate))
    return w


# ---------------------------------------------------------------- simple functions
def gen_char_attack_range(ctx, env):
    for fname, addr, n, with_hand in (('GetCharAttackRange', 0x00519ac0, 300, True),
                                      ('GetBestHandRangeCategory', 0x00519ba0, 200, False)):
        fn = ctx.fn(addr)
        for i in range(ctx.n(n)):
            r = ctx.rng(fname, i)
            c = ctx.case('%s.%d' % (fname, i), fn, conv='c', ret='i')
            blob, name = ctx.pick_char(r)
            if r.random() < 0.1:
                # a character outside the party array (CharacterPointerToPartySlot asserts)
                ch = Blob(CHAR)
                ch.u8(C_IN_PARTY, 1)
                hb = bytearray(blob[C_HAND:C_HAND + 2 * HAND_STEP])
                for h in (0, 1):
                    struct.pack_into('<i', hb, h * HAND_STEP, r.choice(HOLDS))
                    hb[h * HAND_STEP + 4] = rb(r, 0.6)
                ch[C_HAND:C_HAND + 2 * HAND_STEP] = bytes(hb)
                ch.u32(C_PRIMARY, rand_weapon(r))
                ch.u32(C_PRIMARY + ITEM, rand_weapon(r))
                emit(c, env.S[6], ch)
                target = env.S[6]
                slot = -1
            else:
                slot = r.randrange(8)
                c.setb(env.char(slot), bytes(blob))
                set_hands(c, env.char(slot), r, blob, p=0.8)
                if r.random() < 0.08:
                    c.set(env.char(slot) + C_IN_PARTY, b'\x00')
                target = env.char(slot)
            c.arg(target)
            if with_hand:
                hand = r.choice([0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 7, 0xffffffff])
                c.arg(hand)
                c.note(char=name, slot=slot, hand=hand)
            else:
                c.note(char=name, slot=slot)
            finish(c)


def gen_sight_condition(ctx, env):
    fn = ctx.fn(0x00519be0)
    values = [-2, -1, 0, 1, 2, 3, 4, 5, 255, 0x7fffffff, -0x80000000]
    i = 0
    for rng in values:
        for proj in (0, 1):
            r = ctx.rng('sight', i)
            c = ctx.case('RangeCategoryUsesSightCondition.%d' % i, fn, conv='c', ret='b')
            emit(c, env.mon(0), mblob({'proj': proj, 'spellorg': rb(r), 'u379': rb(r), 'u37b': rb(r),
                                       'active': rb(r), 'hp': r.randrange(3)}), gap=112)
            c.arg(env.mon(0))
            c.arg(rng)
            c.note(range=rng, proj=proj)
            i += 1
    while i < ctx.n(100):
        r = ctx.rng('sight', i)
        c = ctx.case('RangeCategoryUsesSightCondition.%d' % i, fn, conv='c', ret='b')
        proj = rb(r)
        emit(c, env.mon(0), mblob({'proj': proj, 'spellorg': rb(r), 'hp': r.randrange(3)}), gap=112)
        rng = r.choice([-1, 0, 1, 2, 3, r.randrange(-10, 300)])
        c.arg(env.mon(0))
        c.arg(rng)
        c.note(range=rng, proj=proj)
        i += 1


def gen_action_range(ctx, env):
    fn = ctx.fn(0x0051a730)
    for i in range(ctx.n(300)):
        r = ctx.rng('actrange', i)
        c = ctx.case('GetMonsterActionRangeCategory.%d' % i, fn, conv='c', ret='i')
        action = r.choice(MON_ACTIONS + [0, 0, 2, 3, 8, 100, -0x80000000])
        detail = rand_spell(r) if action == 2 else r.choice([0, 1, 2, 5, 0xffffffff])
        emit(c, env.mon(0), mblob({'action': action, 'detail': detail, 'proj': rb(r)}), gap=112)
        rec = rand_rec(r, 0.5)
        emit(c, env.rec(0), rec, gap=0x70)
        attack = best_attack_index(r, rec) if r.random() < 0.85 else r.choice([3, 4, 5, 7, 0xffffffff])
        c.arg(env.mon(0))
        c.arg(env.rec(0))
        c.arg(attack)
        c.note(action=action, detail=detail, attack=attack)
        finish(c)


def gen_best_attack_range(ctx, env):
    fn = ctx.fn(0x0051a800)
    for i in range(ctx.n(300)):
        r = ctx.rng('bestatk', i)
        c = ctx.case('GetBestMonsterAttackRange.%d' % i, fn, conv='c', ret='i')
        if r.random() < 0.6:
            rec = rand_rec(r, 0.4)
        else:
            rec = Blob(MR_SIZE)
            for a in range(3):
                rec.u8(MR_ATK + a * 0x22, r.choice([0, 1, 1, 1, 2, 0xff]))
                rec.u8(MR_ATK + a * 0x22 + 3, r.choice([0, 1, 1, 2, 2, 3, 4, 0x7f, 0x80, 0xff]))
        emit(c, env.rec(0), rec, gap=0x70)
        close = rb(r)
        c.arg(env.rec(0))
        c.arg(close)
        c.note(close=close, attacks=rec[MR_ATK:MR_ATK + 0x66:0x22].hex() + '/' +
               bytes(rec[MR_ATK + 3 + a * 0x22] for a in range(3)).hex())
        finish(c)


def gen_monster_best_range(ctx, env):
    fn = ctx.fn(0x0051a840)
    for i in range(ctx.n(300)):
        r = ctx.rng('monbest', i)
        c = ctx.case('GetMonsterBestRangeCategory.%d' % i, fn, conv='c', ret='i')
        skip = rb(r)
        row = r.choice(MONSTERS)
        rec = mutate_rec(r, rec_blob(row), 0.4)
        if r.random() < 0.3:
            rec.u8(MR_PREFER, r.choice([0, 1, 1, 2]))
        if r.random() < 0.3:
            rec.u8(MR_FC, r.choice([0, 0x4f, 0x50, 0x51, 0xff]))
        if r.random() < 0.3:
            rec.u8(MR_SC, r.choice([0, 0x4f, 0x50, 0x51, 0xff]))
        if r.random() < 0.25:
            rec.u8(MR_SAK, r.choice([0, 1, 3, 8, 23, 24, 29, 30, 31]))
        if r.random() < 0.25:
            for t in range(10):
                rec.u8(MR_SPELLS + t, r.choice(AIMABLE + NON_AIMABLE))
        if not skip and rec[MR_PREFER] == 1 and rec[MR_SC] >= 0x50:
            # IsSpellUsableByMonster (CollectMonsterSpellTargets, cursor-node dispatch) stays out
            for t in range(10):
                if rec[MR_SPELLS + t] in AIMABLE:
                    rec.u8(MR_SPELLS + t, r.choice(NON_AIMABLE))
        species = r.randrange(N_MONSTERS)
        emit(c, env.mon(0), mblob({'species': species, 'proj': rb(r), 'spellorg': rb(r),
                                   'hp': r.choice([0, 10]), 'incombat': rb(r)}), gap=112)
        emit(c, env.rec(0), rec, gap=0x70)
        c.setp(env.gx + X_RECCACHE + 4 * species, env.rec(0))
        modes_state(c, env, rb(r))
        c.keep(env.flee_flag, 1)
        out = env.S[5] + S5_OUT
        c.set(out, p32(0xa5a5a5a5))
        c.cap(out, 4, 'out_sight')
        c.arg(env.mon(0))
        c.arg(skip)
        c.arg(out)
        c.note(record=row[0], skip=skip, prefer=rec[MR_PREFER], sc=rec[MR_SC], fc=rec[MR_FC], sak=rec[MR_SAK])
        finish(c)


def gen_calc_range(ctx, env):
    fn = ctx.fn(0x0051a9a0, '?CalcRangeDistance@@YAMW4W8RangeCategory@@@Z')
    values = RANGE_ARGS + RANGE_EDGES + [6, 7, 8, 16, 255, 256, -100, 0x40000000]
    i = 0
    for rep in range(2):
        for v in values:
            if i >= ctx.n(30):
                break
            c = ctx.case('CalcRangeDistance.%d' % i, fn, conv='c', ret='f')
            c.arg(v)
            c.note(range=v)
            i += 1


def gen_calc_range_source(ctx, env):
    fn = ctx.fn(0x0051aa30, '?CalcRangeDistance@@YAMW4W8RangeCategory@@PAUW8TargetSource@@@Z')
    for i in range(ctx.n(200)):
        r = ctx.rng('calcsrc', i)
        c = ctx.case('CalcRangeDistanceSource.%d' % i, fn, conv='c', ret='f')
        kind = r.choice([0, 1, 1, 1, 2, 2, 2, 2, 3, 3, 4])
        rng = r.choice(RANGE_ARGS * 4 + [-2, 4, 7])
        src = Blob(0x34)
        src.u32(0, kind)
        src.u32(4, r.choice([0, 3, 7]) if kind != 3 or r.random() < 0.5 else -1)
        src.u32(8, -1)
        src.u8(0x1b, rb(r, 0.3))
        src.u8(0x1c, rb(r, 0.3))
        if kind == 1 and r.random() < 0.1:
            src.u32(4, -1)
        cam = rand_cam(r)
        sr = r.choice([0.0, 300.0, 500.0, round(r.uniform(1.0, 1200.0), 3)])
        c.set(env.nav + NAV_COLL, pf(r.uniform(0.0, 900.0)) + pf(sr))
        if kind in (2, 3):
            n = r.choice([1, 2, 3])
            w = mon_world(r, env, c, cam, sr, n, records=False)
            pick = r.randrange(n)
            src.u32(8, w.mons[pick]['loc'] if kind == 2 or r.random() < 0.5 else -1)
            order = list(range(n))
            r.shuffle(order)
            w.write(list_ks=order)
        emit(c, env.S[5] + S5_SOURCE, src)
        c.arg(rng)
        c.arg(env.S[5] + S5_SOURCE)
        c.note(kind=kind, range=rng, nav_radius=sr)
        finish(c)


def gen_calc_range_party(ctx, env):
    fn = ctx.fn(0x0051ab50)
    for i in range(ctx.n(60)):
        r = ctx.rng('calcparty', i)
        c = ctx.case('CalcRangeDistanceFromParty.%d' % i, fn, conv='c', ret='f')
        rng = r.choice(RANGE_ARGS * 3 + RANGE_EDGES)
        coll = r.choice([0.0, 500.0, 250.5, round(r.uniform(0.0, 5000.0), 3), -100.0])
        c.set(env.nav + NAV_COLL, pf(coll))
        c.arg(rng)
        c.note(range=rng, collision_radius=coll)


def gen_anyone_ahead(ctx, env):
    fn = ctx.fn(0x0051ae60)
    for i in range(ctx.n(200)):
        r = ctx.rng('ahead', i)
        c = ctx.case('AnyoneStandsAhead.%d' % i, fn, conv='c', ret='b')
        formation_state(c, env, r, all_slots=True)
        pos = r.choice([0, 1, 2, 3, 4] * 5 + [5, 6, 7, 8, 12, 20, 38, 0x104, 0xff02])
        c.arg(pos)
        c.note(position=pos)
        finish(c)


def gen_count_rows(ctx, env):
    fn = ctx.fn(0x0051aec0)
    for i in range(ctx.n(300)):
        r = ctx.rng('rows', i)
        c = ctx.case('CountRowsBetween.%d' % i, fn, conv='c', ret='i8')
        formation_state(c, env, r, all_slots=True)
        cam, sr = view_state(c, env, r)
        m = rand_mon(r, 1, 1, cam, sr)
        if r.random() < 0.5:
            d = r.uniform(300.0, 20000.0)
            a = r.uniform(0.0, 2.0 * math.pi)
            m['pos'] = (cam[0] + d * math.cos(a), cam[1] - WORLD_HEIGHT + r.uniform(-500, 500),
                        cam[2] + d * math.sin(a))
        w = World(env, c)
        w.add(m)
        w.write()
        slot = r.randrange(8)
        c.arg(slot)
        c.arg(env.mon(0))
        c.note(slot=slot)
        finish(c)


def gen_front_rank(ctx, env):
    fn = ctx.fn(0x0051b000)
    for i in range(ctx.n(300)):
        r = ctx.rng('front', i)
        c = ctx.case('FrontRankScreens.%d' % i, fn, conv='c', ret='b')
        formation_state(c, env, r, all_slots=True)
        a = r.choice(list(range(8)) * 6 + [8, 9])
        b = r.choice(list(range(8)) * 6 + [8, 9])
        c.arg(a)
        c.arg(b)
        c.note(source=a, target=b)
        finish(c)


# ---------------------------------------------------------------- party action functions
CONTEXTS = [0, 0, 0, 1, 1, 1, 3, 4, 5, 8, 8, 6, 6, 7, 9]


def party_action_case(ctx, env, c, r, context, slot=None, others=False):
    party = ctx.set_party(c, r)
    slot = r.randrange(8) if slot is None else slot
    blob = party[slot][1]
    combat = rb(r)
    spell = rb(r, 0.2)
    item = rb(r, 0.15)
    modes_state(c, env, combat, spell, item)
    if others:
        party_state(c, env, r, party, skip_rows=(slot,))
    elif r.random() < 0.3:
        set_vitals(c, env.char(slot), blob, 0 if r.random() < 0.4 else r.choice([1, 50]),
                   r.choice([0, 0x0d, 0x11, 0x12, 0x13]))
    acting_row(c, env, r, slot, blob, occupied=1 if r.random() < 0.93 else 0)
    set_hands(c, env.char(slot), r, blob)
    formation_state(c, env, r)
    context_setup(c, env, r, context, slot, spell, item)
    return party, slot, blob, combat, spell, item


def gen_action_reaches_slot(ctx, env):
    fn = ctx.fn(0x005197c0)
    for i in range(ctx.n(400)):
        r = ctx.rng('reachslot', i)
        c = ctx.case('CharacterActionReachesSlot.%d' % i, fn, conv='c', ret='b')
        context = r.choice(CONTEXTS)
        party, slot, blob, combat, spell, item = party_action_case(ctx, env, c, r, context)
        hand = r.choice([0, 0, 1, 1, 2, 2, 3])
        tslot = slot if r.random() < 0.1 else r.choice(list(range(8)) * 8 + [8, 9])
        c.arg(slot)
        c.arg(hand)
        c.arg(tslot)
        c.arg(context)
        c.note(slot=slot, hand=hand, target=tslot, context=context, combat=combat)
        finish(c)


def gen_char_action_range(ctx, env):
    fn = ctx.fn(0x005199f0)
    for i in range(ctx.n(400)):
        r = ctx.rng('actionrange', i)
        c = ctx.case('GetCharActionRange.%d' % i, fn, conv='c', ret='i')
        context = r.choice(CONTEXTS)
        party, slot, blob, combat, spell, item = party_action_case(ctx, env, c, r, context)
        hand = r.choice([0, 0, 1, 1, 2, 2, 3])
        c.arg(slot)
        c.arg(hand)
        c.arg(context)
        c.note(slot=slot, hand=hand, context=context, combat=combat)
        finish(c)


def gen_pick_reachable(ctx, env):
    fn = ctx.fn(0x0051b0a0)
    for i in range(ctx.n(300)):
        r = ctx.rng('pick', i)
        c = ctx.case('PickReachableSlotByDisposition.%d' % i, fn, conv='c', ret='i')
        party, slot, blob, combat, spell, item = party_action_case(ctx, env, c, r, 0, others=True)
        rel = r.choice([1, 1, 2, 2, 2, 0, 3, 0x102])
        c.arg(slot)
        c.arg(rel)
        c.note(slot=slot, relationship=rel)
        finish(c)


def gen_attack_any(ctx, env):
    fn = ctx.fn(0x00518e30)
    for i in range(ctx.n(400)):
        r = ctx.rng('attackany', i)
        c = ctx.case('CanPartySlotAttackAnyTarget.%d' % i, fn, conv='c', ret='b')
        category = r.choice([0, 0, 0, 8, 8, 8, 1, 3, 4, 5, 6, 7, 9])
        party, slot, blob, combat, spell, item = party_action_case(ctx, env, c, r, category, others=True)
        c.set(env.gx + X_TARGETING, p32(r.choice([0, 0, 0, 1, 2, 3, 5, -1])))
        combat_state(c, env, r)
        cam, sr = view_state(c, env, r)
        flag = r.choice([0, 0, 1, 1, 2, -1])
        hand = rb(r)
        nm = r.choice([0, 1, 1, 2, 2, 3]) if flag != 1 else r.choice([0, 1])
        w = mon_world(r, env, c, cam, sr, nm, records=False)
        w.write(list_ks=list(range(nm)))
        c.arg(slot)
        c.arg(category)
        c.arg(flag)
        c.arg(hand)
        c.note(slot=slot, category=category, flag=flag, hand=hand, monsters=nm, combat=combat)
        finish(c)


def gen_aim(ctx, env):
    fn = ctx.fn(0x005194e0)
    for i in range(ctx.n(400)):
        r = ctx.rng('aim', i)
        c = ctx.case('CanPartyMemberAimAtMonster.%d' % i, fn, conv='c', ret='b')
        context = r.choice(CONTEXTS)
        party, slot, blob, combat, spell, item = party_action_case(ctx, env, c, r, context)
        if r.random() < 0.35:   # the plain-sighting path
            modes_state(c, env, 0, 0, 0, 0)
        else:
            c.set(env.gx + X_TARGETING, p32(r.choice([0, 0, 1, 2, 3, 4, 5, 8, -1])))
        cam, sr = view_state(c, env, r)
        w = World(env, c)
        w.add(rand_mon(r, r.randrange(1, 4000), r.randrange(N_MONSTERS), cam, sr))
        w.write()
        hand = r.choice([0, 0, 1, 1, 2, 2, 3])
        c.arg(slot)
        c.arg(hand)
        c.arg(env.mon(0))
        c.arg(context)
        c.arg(0)
        c.note(slot=slot, hand=hand, context=context, combat=combat, sight=w.mons[0]['pt_sight'])
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


def gen_action_reaches_target(ctx, env, fname='CharacterActionReachesTarget', n=400, source_mode=False):
    fn = ctx.fn(0x0051b4e0 if source_mode else 0x00519180)
    for i in range(ctx.n(n)):
        r = ctx.rng(fname, i)
        c = ctx.case('%s.%d' % (fname, i), fn, conv='c', ret='b')
        party = ctx.set_party(c, r)
        slot = r.randrange(8)
        blob = party[slot][1]
        context = 6 if source_mode else r.choice([0, 0, 1, 1, 3, 4, 5, 6, 6, 9])
        combat = rb(r)
        spell = rb(r, 0.2)
        item = rb(r, 0.15)
        modes_state(c, env, combat, spell, item, targeting=r.choice([0, 0, 1, 2, 3, -1]))
        cam, sr = view_state(c, env, r)
        nav_radius = r.choice([0.0, 500.0, 1000.0, round(r.uniform(0.0, 1500.0), 2)])
        c.set(env.nav + NAV_RADIUS, pf(nav_radius))
        kind = r.choice([3, 3, 3, 1, 1, 6, 6, 6, 4, 4, 0, 2, 5, 7, 8, 9])
        spells = items = None
        own = True
        tb = None
        w = World(env, c)
        nm = 0
        if kind in (3, 4):
            nm = r.choice([1, 2, 3])
            w = mon_world(r, env, c, cam, sr, nm, mutate=0.2)
        if kind == 3:
            mid = w.mons[r.randrange(nm)]['loc'] if r.random() < 0.85 else 4500
            tb = target_blob(3, mon=mid)
        elif kind == 1:
            tb = target_blob(1, char=slot if r.random() < 0.15 else r.randrange(8))
        elif kind == 6:
            point, safe = place_target_case(r, cam, nav_radius)
            if safe:
                spells, items, own = SAFE_PLACE_SPELLS, SAFE_PLACE_ITEMS, False
            tb = target_blob(6, point=point)
        elif kind == 4:
            ids = [m['loc'] for m in w.mons]
            groups = []
            gids = r.sample(range(100, 400), 2)
            for g in range(r.choice([1, 2])):
                groups.append((gids[g], r.sample(ids, r.randint(0 if r.random() < 0.1 else 1, len(ids)))))
            gid = r.choice(groups)[0] if r.random() < 0.85 else 999
            tb = target_blob(4, group=gid)
        else:
            tb = target_blob(kind, char=r.randrange(8), mon=r.randrange(1, 100), group=r.randrange(100))
        acting_row(c, env, r, slot, blob, targets=tb, occupied=1 if r.random() < 0.95 else 0,
                   spells=spells, items=items, own=own)
        set_hands(c, env.char(slot), r, blob)
        if r.random() < 0.25:
            set_vitals(c, env.char(slot), blob, r.choice([0, 30]), r.choice([0, 0x12]))
        formation_state(c, env, r)
        context_setup(c, env, r, context, slot, spell, item)
        if kind in (3, 4):
            order = list(range(nm))
            r.shuffle(order)
            w.write(list_ks=order)
            if kind == 4:
                w.groups(groups)
        hand = r.choice([0, 0, 1, 1, 2])
        if source_mode:
            src = Blob(0x34)
            src.u32(0, 1)
            src.u32(4, slot)
            src.u32(8, -1)
            emit(c, env.S[5] + S5_SOURCE, src)
            c.arg(env.S[5] + S5_SOURCE)
            c.arg(env.S[5] + S5_TARGET)
        else:
            c.arg(slot)
            c.arg(hand)
            c.arg(context)
        c.note(slot=slot, hand=hand, context=context, kind=kind, monsters=nm, combat=combat)
        finish(c)


def gen_slot_in_range_of_group(ctx, env):
    fn = ctx.fn(0x00519920)
    for i in range(ctx.n(200)):
        r = ctx.rng('groupslot', i)
        c = ctx.case('IsSlotInRangeOfGroup.%d' % i, fn, conv='c', ret='b')
        context = r.choice(CONTEXTS)
        party, slot, blob, combat, spell, item = party_action_case(ctx, env, c, r, context)
        cam, sr = view_state(c, env, r)
        nm = r.choice([1, 2, 3])
        w = mon_world(r, env, c, cam, sr, nm, records=False)
        w.write(list_ks=list(range(nm)))
        ids = [m['loc'] for m in w.mons]
        gids = r.sample(range(100, 400), 2)
        groups = [(gids[g], r.sample(ids, r.randint(0 if r.random() < 0.1 else 1, len(ids))))
                  for g in range(r.choice([1, 2]))]
        w.groups(groups)
        known = r.random() < 0.85
        gid = r.choice(groups)[0] if known else 999
        notify = 0 if known else rb(r)
        c.arg(slot)
        c.arg(gid)
        c.arg(context)
        c.arg(notify)
        c.note(slot=slot, group=gid, context=context, known=known, monsters=nm)
        finish(c)


# ---------------------------------------------------------------- monster functions
def gen_reaches_anyone(ctx, env):
    fn = ctx.fn(0x00519c00)
    for i in range(ctx.n(300)):
        r = ctx.rng('anyone', i)
        c = ctx.case('MonsterAttackReachesAnyone.%d' % i, fn, conv='c', ret='b')
        party = ctx.set_party(c, r)
        party_state(c, env, r, party, change_p=0.25, turncoat_p=0.15)
        formation_state(c, env, r)
        cam, sr = view_state(c, env, r)
        combat = rb(r)
        modes_state(c, env, combat)
        n = r.choice([1, 1, 2, 2, 3])
        w = mon_world(r, env, c, cam, sr, n, mutate=0.25)
        order = list(range(n))
        r.shuffle(order)
        w.write(list_ks=order, pcombat=(0,))
        w.vis(0, vis_entries(r, w, 0, range(1, n)))
        attack = best_attack_index(r, w.recs[0][1])
        friendly = rb(r)
        c.arg(env.mon(0))
        c.arg(attack)
        c.arg(friendly)
        c.note(monsters=n, attack=attack, friendly=friendly, combat=combat, action=w.mons[0]['action'])
        finish(c)


def gen_reaches_character(ctx, env):
    fn = ctx.fn(0x0051a2f0)
    for i in range(ctx.n(400)):
        r = ctx.rng('reachchar', i)
        c = ctx.case('MonsterAttackReachesCharacter.%d' % i, fn, conv='c', ret='b')
        formation_state(c, env, r, all_slots=True)
        cam, sr = view_state(c, env, r)
        combat = rb(r, 0.6)
        modes_state(c, env, combat)
        w = World(env, c)
        species = r.randrange(N_MONSTERS)
        m = rand_mon(r, r.randrange(1, 4000), species, cam, sr)
        if r.random() < 0.3:
            m['pv_sight'] = 1
            m['pv_los'] = (1, 1, 1, 1)
        w.add(m)
        rec = rand_rec(r, 0.3)
        same = r.random() < 0.7
        w.record(species if same else None, rec)
        if not same:
            w.record(species, rand_rec(r, 0.3))
        w.write()
        attack = best_attack_index(r, rec)
        slot = r.randrange(8)
        c.arg(env.mon(0))
        c.arg(env.rec(0))
        c.arg(attack)
        c.arg(slot)
        c.note(slot=slot, attack=attack, action=m['action'], combat=combat, same_record=same)
        finish(c)


def gen_reaches_monster(ctx, env):
    fn = ctx.fn(0x0051a510)
    for i in range(ctx.n(300)):
        r = ctx.rng('reachmon', i)
        c = ctx.case('MonsterAttackReachesMonster.%d' % i, fn, conv='c', ret='b')
        cam = rand_cam(r)
        sr = 0.0
        n = r.choice([2, 2, 3])
        w = mon_world(r, env, c, cam, sr, n, records=False)
        for m in w.mons[1:]:
            if r.random() < 0.5:   # near the source rather than near the party
                src = w.mons[0]['pos']
                d = r.choice(BANDS) + w.mons[0]['radius'] + m['radius'] + r.choice([-50.0, -1.0, 1.0, 50.0])
                a = r.uniform(0.0, 2.0 * math.pi)
                m['pos'] = (src[0] + d * math.cos(a), src[1], src[2] + d * math.sin(a))
        rec = rand_rec(r, 0.3)
        if r.random() < 0.15:
            rec.u8(MR_UNTARGETABLE, r.choice([1, 2, 0xff]))
        same = r.random() < 0.7
        w.record(w.mons[0]['species'] if same else None, rec)
        if not same:
            w.record(w.mons[0]['species'], rand_rec(r, 0.3))
        w.write()
        w.vis(0, vis_entries(r, w, 0, range(1, n)))
        tk = 0 if r.random() < 0.1 else r.randrange(1, n)
        attack = best_attack_index(r, rec)
        c.arg(env.mon(0))
        c.arg(env.rec(0))
        c.arg(attack)
        c.arg(env.mon(tk))
        c.note(target=tk, attack=attack, action=w.mons[0]['action'], same_record=same)
        finish(c)


def gen_choose_target(ctx, env):
    fn = ctx.fn(0x0051ac30)
    for i in range(ctx.n(300)):
        r = ctx.rng('choose', i)
        c = ctx.case('MonsterChooseTarget.%d' % i, fn, conv='c', ret='f')
        cam, sr = view_state(c, env, r)
        n = r.choice([1, 2, 3, 3])
        w = mon_world(r, env, c, cam, sr, n, mutate=0.2)
        for m in w.mons[1:]:
            if r.random() < 0.5:
                src = w.mons[0]['pos']
                d = r.uniform(0.0, 30000.0)
                a = r.uniform(0.0, 2.0 * math.pi)
                m['pos'] = (src[0] + d * math.cos(a), src[1] + r.uniform(-300, 300), src[2] + d * math.sin(a))
        if r.random() < 0.08:   # beyond 999999: the party is not taken
            w.mons[0]['pos'] = (cam[0] + 1.2e6, cam[1], cam[2])
        order = list(range(n))
        r.shuffle(order)
        w.write(list_ks=order, pcombat=(0,))
        w.vis(0, vis_entries(r, w, 0, range(1, n)))
        out = env.S[5] + S5_TARGET
        c.set(out, bytes([0x5a]) * 0x20)
        c.cap(out, 0x20, 'out')
        kind = r.choice([0, 1, 2, 3, 4, 5, 6, 7, 8, -1])
        c.arg(env.mon(0))
        c.arg(out)
        c.arg(kind)
        c.note(monsters=n, kind=kind, disp=w.mons[0]['disp'])
        finish(c)


def gen_nearest_group_monster(ctx, env):
    fn = ctx.fn(0x0051ad60)
    for i in range(ctx.n(200)):
        r = ctx.rng('nearest', i)
        c = ctx.case('FindNearestVisibleGroupMonster.%d' % i, fn, conv='c', ret='i')
        cam = rand_cam(r)
        n = r.choice([2, 3, 4])
        w = mon_world(r, env, c, cam, 0.0, n, records=False)
        for m in w.mons[1:]:
            src = w.mons[0]['pos']
            d = r.uniform(0.0, 30000.0)
            a = r.uniform(0.0, 2.0 * math.pi)
            m['pos'] = (src[0] + d * math.cos(a), src[1], src[2] + d * math.sin(a))
        if n >= 3 and r.random() < 0.2:   # equal distances: the first one found stays
            w.mons[2]['pos'] = w.mons[1]['pos']
            w.mons[2]['radius'] = w.mons[1]['radius']
        order = list(range(n))
        r.shuffle(order)
        w.write(list_ks=order)
        w.vis(0, vis_entries(r, w, 0, range(1, n)))
        ids = [m['loc'] for m in w.mons]
        gids = r.sample(range(100, 400), 2)
        groups = []
        for g in range(r.choice([1, 2])):
            members = r.sample(ids[1:], r.randint(0 if r.random() < 0.1 else 1, len(ids) - 1))
            if r.random() < 0.2:
                members.append(ids[0])
            groups.append((gids[g], members))
        w.groups(groups)
        gid = r.choice(groups)[0]
        kind = r.choice([0, 1, 2, 3, 4, 5, 6, 7])
        c.arg(env.mon(0))
        c.arg(gid)
        c.arg(kind)
        c.note(monsters=n, group=gid, kind=kind)
        finish(c)


def monster_target_case(ctx, env, c, r, with_source=False):
    """Shared set-up of MonsterActionReachesTarget / SourceActionReachesTarget (monster source)."""
    party = ctx.set_party(c, r)
    party_state(c, env, r, party, change_p=0.25, turncoat_p=0.0)
    formation_state(c, env, r)
    cam, sr = view_state(c, env, r)
    combat = rb(r, 0.6)
    modes_state(c, env, combat)
    kind = r.choice([1, 1, 1, 3, 3, 3, 2, 2, 2, 4, 4, 0, 5, 6, 7, 9])
    n = r.choice([1, 2, 3]) if kind not in (3,) else r.choice([2, 2, 3])
    w = mon_world(r, env, c, cam, sr, n, mutate=0.25)
    for m in w.mons[1:]:
        if r.random() < 0.5:
            src = w.mons[0]['pos']
            d = r.choice(BANDS) + w.mons[0]['radius'] + m['radius'] + r.choice([-50.0, -1.0, 1.0, 50.0])
            a = r.uniform(0.0, 2.0 * math.pi)
            m['pos'] = (src[0] + d * math.cos(a), src[1], src[2] + d * math.sin(a))
    if r.random() < 0.3:
        w.mons[0]['pv_sight'] = 1
        w.mons[0]['pv_los'] = (1, 1, 1, 1)
    order = list(range(n))
    r.shuffle(order)
    w.write(list_ks=order)
    groups = None
    if kind == 3:
        w.vis(0, vis_entries(r, w, 0, range(1, n)))
        tb = target_blob(3, mon=w.mons[r.randrange(1, n)]['loc'])
    elif kind == 1:
        tb = target_blob(1, char=r.randrange(8))
    elif kind == 4:
        ids = [m['loc'] for m in w.mons]
        gids = r.sample(range(100, 400), 2)
        groups = [(gids[g], r.sample(ids, r.randint(0 if r.random() < 0.1 else 1, len(ids))))
                  for g in range(r.choice([1, 2]))]
        w.groups(groups)
        tb = target_blob(4, group=r.choice(groups)[0])
    else:
        tb = target_blob(kind, char=r.randrange(8), mon=r.randrange(1, 100), group=r.randrange(100))
    emit(c, env.S[5] + S5_TARGET, tb)
    return w, kind, combat


def gen_monster_action_reaches_target(ctx, env):
    fn = ctx.fn(0x00519f80)
    for i in range(ctx.n(300)):
        r = ctx.rng('monaction', i)
        c = ctx.case('MonsterActionReachesTarget.%d' % i, fn, conv='c', ret='b')
        w, kind, combat = monster_target_case(ctx, env, c, r)
        rec_k = 0 if r.random() < 0.8 else r.randrange(len(w.recs))
        attack = best_attack_index(r, w.recs[rec_k][1])
        c.arg(env.mon(0))
        c.arg(env.rec(rec_k))
        c.arg(attack)
        c.arg(env.S[5] + S5_TARGET)
        c.note(kind=kind, attack=attack, action=w.mons[0]['action'], combat=combat, record=rec_k)
        finish(c)


def gen_source_action_reaches_target(ctx, env):
    fn = ctx.fn(0x0051b4e0)
    n_total = ctx.n(200)
    n_char = n_total * 2 // 5
    gen_action_reaches_target(ctx, env, fname='SourceActionReachesTarget.char', n=n_char, source_mode=True)
    for i in range(n_total - n_char):
        r = ctx.rng('srcaction', i)
        c = ctx.case('SourceActionReachesTarget.mon.%d' % i, fn, conv='c', ret='b')
        skind = r.choice([2, 2, 2, 2, 0, 3, 4])
        src = Blob(0x34)
        src.u32(0, skind)
        src.u32(4, r.choice([-1, 2]))
        src.u32(8, -1)
        src.u8(0x1c, rb(r, 0.3))
        if skind == 2:
            w, kind, combat = monster_target_case(ctx, env, c, r)
            src.u32(8, w.mons[0]['loc'])
            src.u32(4, -1)
        else:
            kind = combat = None
        emit(c, env.S[5] + S5_SOURCE, src)
        c.arg(env.S[5] + S5_SOURCE)
        c.arg(env.S[5] + S5_TARGET)
        c.note(source=skind, kind=kind, combat=combat)
        finish(c)


def gen_init_capabilities(ctx, env):
    fn = ctx.fn(0x0051b420)
    for i in range(ctx.n(150)):
        r = ctx.rng('initcap', i)
        c = ctx.case('InitializeMonsterRangeCapabilities.%d' % i, fn, conv='c', ret='v')
        rec = Blob(MR_SIZE)
        for a in range(3):
            has = r.choice([0, 0, 1, 1, 1, 2, 0xff])
            rec.u8(MR_ATK + a * 0x22, has)
            rng = r.choice([0, 0, 1, 1]) if has else r.choice([0, 1, 2, 3, 0x7f, 0xff])
            rec.u8(MR_ATK + a * 0x22 + 3, rng)
        rec.u8(MR_SC, r.choice([0, 0, 1, 0x50, 0xff]))
        m = {'species': r.randrange(N_MONSTERS), 'proj': r.choice([0, 1, 0xff]),
             'spellorg': r.choice([0, 1, 0xff]), 'u379': r.choice([0, 1, 7]), 'u37b': r.choice([0, 1, 7]),
             'hp': 10}
        emit(c, env.mon(0), mblob(m), gap=112)
        emit(c, env.rec(0), rec, gap=0x70)
        c.cap(env.mon(0), MI_SIZE, 'monster')
        c.arg(env.mon(0))
        c.arg(env.rec(0))
        c.note(spell_chance=rec[MR_SC])
        finish(c)


def gen_attack_source_offset(ctx, env):
    fn = ctx.fn(0x0051b320)
    for i in range(ctx.n(40)):
        r = ctx.rng('srcoffset', i)
        c = ctx.case('GetMonsterAttackSourceOffset.%d' % i, fn, conv='c', ret='v')
        m = {'pos': (r.uniform(-9e4, 9e4), r.uniform(-3e3, 3e3), r.uniform(-9e4, 9e4)),
             'radius': r.uniform(0.0, 900.0), 'height': r.choice([0.0, 750.0, -1.5, r.uniform(0.0, 3000.0)])}
        emit(c, env.p3d(0), p3dblob(m), gap=128)
        out = env.S[5] + S5_OUT
        c.set(out, bytes([0x77]) * 12)
        c.cap(out, 12, 'out')
        kind = r.choice([0, 2, 4, 5, -1, 100, 0x7fffffff, -0x80000000])
        c.arg(env.p3d(0))
        c.arg(kind)
        c.arg(out)
        c.note(kind=kind, height=m['height'])
        finish(c)


def gen_trace_mode(ctx, env):
    fn = ctx.fn(0x0051b3f0)
    values = list(range(-5, 11)) + [0x7f, 0x80, 0xff, 0x100, 0x101, 0x102, 0x103, 0x104, 0x1ff,
                                    0x7fffffff, -0x80000000, 0x12345678, -0x100, -0xfe, 0x10000, 0x10003,
                                    0x80000003, 1000, 65535, 3 + 0x200, 2 + 0x400, 0xfffffffd, 0xfffffffc,
                                    0x80000002]
    for i, v in enumerate(values[:ctx.n(40)]):
        c = ctx.case('TraceModeRejectsNoHit.%d' % i, fn, conv='c', ret='u8')
        c.arg(v)
        c.note(mode=v)


def gen_constants(ctx, env):
    for fname, addr in (('GetMonsterEngagementRange', 0x0051b300), ('GetGroundTargetRange', 0x0051b310)):
        fn = ctx.fn(addr)
        for i in range(2):
            c = ctx.case('%s.%d' % (fname, i), fn, conv='c', ret='f')
            c.note(rep=i)


def cases(ctx):
    env = Env(ctx)
    gen_char_attack_range(ctx, env)
    gen_sight_condition(ctx, env)
    gen_action_range(ctx, env)
    gen_best_attack_range(ctx, env)
    gen_monster_best_range(ctx, env)
    gen_calc_range(ctx, env)
    gen_calc_range_source(ctx, env)
    gen_calc_range_party(ctx, env)
    gen_anyone_ahead(ctx, env)
    gen_count_rows(ctx, env)
    gen_front_rank(ctx, env)
    gen_action_reaches_slot(ctx, env)
    gen_char_action_range(ctx, env)
    gen_pick_reachable(ctx, env)
    gen_attack_any(ctx, env)
    gen_aim(ctx, env)
    gen_action_reaches_target(ctx, env)
    gen_slot_in_range_of_group(ctx, env)
    gen_reaches_anyone(ctx, env)
    gen_reaches_character(ctx, env)
    gen_reaches_monster(ctx, env)
    gen_choose_target(ctx, env)
    gen_nearest_group_monster(ctx, env)
    gen_monster_action_reaches_target(ctx, env)
    gen_source_action_reaches_target(ctx, env)
    gen_init_capabilities(ctx, env)
    gen_attack_source_offset(ctx, env)
    gen_trace_mode(ctx, env)
    gen_constants(ctx, env)
