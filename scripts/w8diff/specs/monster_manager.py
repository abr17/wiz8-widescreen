"""MonsterManager.cpp (src/wiz8/local_code/MonsterManager.cpp): monster-list lookups and
iterators, record accessors, attribute/scale/range math, names, health text and the party
helpers the file owns. Every recovered function of the file was reviewed.

How the cases are built (everything is restored by the core after each case)
  * Fake monster world in scratch: W8PList/W8IList stubs in S0 (gXStatus.plsMonsterList,
    plsUnbornMonsterList, plsMonsterGroupList and plsMonsterGroupEncounterList are always
    rewired: a list the function must not see is set to NULL), W8MonsterInfo blocks in S1
    (stride 0x430), W8MonsterRecord rows in S2 (stride 0x2a0) wired through
    gXStatus.monster_record_cache[species] so nothing is ever loaded from MONSTERS.DBS,
    W8Monster (p3D) stubs in S3 holding only the fields read (navigator +0x24..+0x78,
    movement.position +0x118, movement.flags +0x144, movement.attachment +0x184, m_pRep
    +0x1d8), W8MonsterRep stubs in S4 (current_cycle +0xa4, pending_cycle +0xa7, scale
    +0x5f0, minimum/maximum scale +0x5f4/+0x5f8), W8MonsterGroup records in S5, a
    W8CombatState and navigator attachments in S6, strings/out buffers in S7.
  * Record contents come from the real MONSTERS.DBS rows (table below: names with the '#'
    suffix cut like LoadMonsterDatabaseRecord does, hit-point dice, attributes, combat move
    range, experience/override - including the 0xcdcdcdcd overrides of rows 356..371 -,
    display level, flags, npc kind, model indices); species ids and rows are mixed freely.
  * PLGet reads data[index] with a signed index: data[-1..-4] (S0+0xf0..0xfc) stay zero
    unless a case puts a pointer there on purpose (labelled), and index 0x80000000 wraps to
    data[0]; both are deterministic in scratch.
  * Party data (levels, skills, hp, conditions, names) are written explicitly per slot, values
    drawn from the 49 corpus characters plus edges; the 'Al-%s' name path loads one corpus
    character into the Sedexus slot.
  * Edge labels (c.note(edge=...)): bool bytes 2/0x80/0xff, conditions >= 0x80000000 (retail
    compares unsigned), NaN/zero scale ranges, flat hit-point dice and uiHPMax below the dice
    minimum (retail subtracts in x87 as a signed 64-bit value), NaN maximum distance (retail
    FCOMP+TEST AH,0x40 takes an unordered compare as "== 0"), near-tie distances (retail keeps
    the distance in 80 bits), skill indices past W8_SKILL_COUNT, bearings exactly on a
    45-degree multiple (boundary_angle: the x87 product is truncated by _ftol) and party_facing
    outside 0..359, huge levels in the PC level average (huge_level_fp: retail sums in 80 bits).
    A difference that only shows in labelled cases is either a precision/compare-semantics
    deviation of the port or a spec edge; the unlabelled cases use in-range data only.

Tested (retail address, function, cases):
  0x004e5550 MonsterGetIndexByLocationID         250  both lists, duplicates, NULL lists,
                                                      truncated iNumUsed, assert flag 0/1/2/0x100
  0x004e5620 MonsterGetScriptPartByLocationIndex 200  unborn bias 10000..19999, past the end,
                                                      NULL entries, index -1..-4 / 0x80000000
  0x004e57c0 MonsterDBFromSpecies                100  species 0..999, 1000 with the slot after
                                                      the cache (gameplay_timer) pointed at scratch
  0x004e5720 GetMonsterDataForInfo               100
  0x004e5840 MonsterInfoFromID                   200
  0x004e58b0 GetMonsterDataByLocationID          150  not found: assert chain + data[-1] read
  0x004e5950 GetMonsterByLocationID              150  location -1, p3D NULL
  0x004e5990 GetMonsterCombatMoveRange           150  real ranges, 0/-0/denormal/huge/inf/NaN
  0x004e5aa0 GetNextMonsterInfo                  200  iterator -4..n+2, 0x7fffffff, 0x80000000
  0x004e5af0 GetMonsterQuadrant                  200  camera/party_facing set; bearings on the
                                                      45-degree boundaries, facing <0 and >360
  0x004e5b50 GetMonsterCycleFallbackValue        100  cycle names that are never registered,
                                                      render option 14 = 0/1/2/0xff
  0x004e5d00 ConvertMonsterAttributes            300  attributes 0..255, adjustments -128..127
  0x004e5e50 FindMonsterInfoBySpecies            150
  0x004e5ea0 ResetLivingMonstersAfterCombat      200  hp unsigned edges, ai_mode bytes with the
                                                      0x10/0x80 bits, g_combat_inactive 0/1
  0x004e6020 SetMonsterControlState              200  group recount over an IList of members
  0x004e61e0 FindNearestMonsterInfo              300  both lists, ties, maximum 0/-0/negative/
                                                      exact distance (+-1 ulp)/NaN/inf
  0x004e65d0 CalculateMonsterScale               300  real dice (incl. count 0 rows 440/573/592),
                                                      scale ranges, Random(1000) seeded
  0x004e6780 GetMonsterExperience                100
  0x004e68c0 AnyMonsterDying                     150  current/pending cycle 0x15, NULL entries
  0x004e6c10 TogglePartyCombatStance             200  screen id forced to 8 (no notice/redraw)
  0x004e5150 GetMonsterName                      250  record 397 'Al-%s', no group (IsDying),
                                                      alternate group names, forms 0..255
  0x004efb60 GetAveragePartyMemberLevel          200
  0x00554490 GetBestPartySkillLevel              300  ties, unsigned levels, out pointer NULL
  0x004e52c0 FormatMonsterHealth                 300  NPC suppression (live NPC states), summons,
                                                      knowledge thresholds, g_dev_mode
  Total 4750 cases.

Skipped (one line each):
  0x004e3930 CreateMonsterInfo              - creates a world monster (malloc, PLAdoptAppend on the
                                              live lists, octree registration, party redraw)
  0x004e3c70 ActivateMonsterInWorld         - loads cycles, adds the Monster to the world/octree,
                                              binds NPCs
  0x004e4050 ActivateMonster                - MonsterReadAllCycles loads model files
  0x004e4600 ClearMonsterPathAndResume      - path/movement reset of the live W8Monster and an
                                              animation cycle start
  0x004e4690 MonsterStartsDying             - death animation, deactivation, kill bookkeeping,
                                              RemoveMonster (world object deletion)
  0x004e46f0 RecordMonsterKill              - kill notices, ApplyFactionChange on the live groups,
                                              MonsterKilled facts, character event queue (voice)
  0x004e5a50 UpdateMonsterDamageAppearance  - walks the model instances of the live W8Monster
                                              (CollectModelInstances); render state only
  0x004e5c00 ProcessMonstersAtCombatEnd     - combat end: notices, MonsterStartsDying
  0x004e5f00 DestroyUngroupedMonsters       - deletes world monsters
  0x004e60b0 MonsterInfoSetMotionless       - animation state of the live W8Monster (real-time
                                              timer stamp, StartMonsterCycle)
  0x004e6130 MoveMonsterToLiveList          - moves a monster between the live lists + birth cycle
  0x004e6370 InitializeMonsterRuntimeStats  - re-rolls every world monster and pushes the scale
                                              into the engine representations
  0x004e67a0 TryStartMonsterCycle2          - not in the port map (inlined); animation start
  0x004e3720 InitializeMonsterManagerState  - clears the live monster/group lists
  0x004e3820 ShutdownMonsterManager         - destroys every monster and list
  0x004e3af0 RemoveMonster                  - world object removal / group destruction
  0x004e4280 DeactivateMonster              - world deactivation (engine flags, spell icons,
                                              sight refresh, mon-to-mon list release)
  0x004e4390 MonsterInfoEnterCombat         - combat entry (malloc pCombat, engine highlight, turn)
  0x004e4500 MonsterInfoLeaveCombat         - combat exit (effect slots, action queue, free)
  0x004e6a80 ToggleCombatMode               - starts/ends combat, notices
  0x004e4db0 StartMonsterCycle              - animation cycle on the live W8Monster
  0x004e4ee0 ProcessMonsterManagerFrame     - per-frame world update (removal, loot, death)
  0x004e4ab0 DetectMonsterGroups            - group visibility needs live W8Monster render checks
                                              (IsWithinWorldRange/IsRenderable) and a detection
                                              posts character/screen notices
  0x004e6ce0 EvaluateCombatDifficulty       - starts combat music (StartMusicResource playlist)
                                              and queues a voice event on a random character
"""
import math
import struct

from w8diff.api import Blob, F64

MAX_OPS = 96

# ---------------------------------------------------------------- layouts (layout.ps1 + retail asm)
CHAR = 0x1862
C_NAME = 0x05
C_LEVEL = 0x89               # uiExpLevel
C_HCOND = 0xb01              # highest_condition
C_HP = 0xb11                 # hp_current
C_SKILLS = 0x19d             # W8CharacterSkill[], 0x26 each, level +6
SKILL_STEP = 0x26
SK_LEVEL = 6
S_MYTHOLOGY = 0x15
SKILL_COUNT = 0x2c
XROW = 0x106                 # W8PartySlotRow, fOccupied +0

GS_CHARS = 0x4
GS_XCHAR = 0x8
GS_GAME_STARTED = 0xc
GS_FACING = 0x18d0           # party_facing (int degrees)
GS_NAME_BUFFER = 0x2453      # monster_name_buffer, wchar_t[22]
GS_SEDEXUS_SLOT = 0x247f

GX_COMBAT_MODE = 0x8dc
GX_MONLIST = 0x8f5
GX_GROUPLIST = 0x8f9
GX_UNBORN = 0x901
GX_ENCOUNTER = 0x905
GX_RECCACHE = 0xa0f          # W8MonsterRecord*[1000]; [1000] is gameplay_timer

SET_CONTINUOUS = 0xa         # W8GameSettings.continuous_combat
CS_EXEC = 0x0                # W8CombatState execution_active, round_active
CS_READY = 0xa62             # combat_ready
SCREEN_AUTOMAP = 8           # anything but the main game (7): no notice, no redraw
CAM_POS = 0x8c               # GDCamera::m_position
RO_STATES = 0x2              # W8RenderQuality.option_states
RO_ADDITIONAL_ANIMATIONS = 14

MI_LOC = 0x00
MI_GROUP = 0x04
MI_SPECIES = 0x08
MI_P3D = 0x0c
MI_DISP = 0x16
MI_HPMAX = 0x27
MI_HP = 0x2b
MI_HCOND = 0x107
MI_ADJ = 0x1e7               # modifiers.attribute_adjustments[7], signed char
MI_ATTRS = 0x247             # attributes[5]
MI_AI = 0x255
MI_SUMMONED = 0x2da
MI_CONTROL = 0x2fd
MI_SIZE = 0x425

MR_NAMES = 0x00              # name0..name3, wchar_t[24] each
MR_NPC_KIND = 0xcd
MR_FLAGS = 0xd0
MR_ATTRS = 0xd1
MR_HP = 0xd6                 # W8Dice {short base; uchar count; uchar sides}
MR_EXP = 0x181
MR_ID = 0x187
MR_CYCLE = 0x189
MR_CMR = 0x1ba
MR_ELEVEL = 0x24f
MR_DLEVEL = 0x251
MR_MODEL = 0x253             # model_index, alternate_model_index
MR_EXPO = 0x26b
MR_SIZE = 0x297
ALT_NAME_RECORD = 397

G_ID = 0x00
G_COUNT = 0x04
G_MONSTERS = 0x08
G_ACTIVE = 0x14
G_MONSTER_ID = 0x18
G_ALTNAME = 0x2c
G_SIZE = 0x12b

M3_FLAGS = 0x24              # navigator (+0x18) flags, collision_margin, movement_target
M3_TARGET_NAV = 0x64
M3_LINKED = 0x74
M3_POS = 0x118               # movement.position (GetPosition)
M3_MFLAGS = 0x144            # movement.flags
M3_ATTACH = 0x184            # movement.attachment (flags dword at +0)
M3_REP = 0x1d8
P3D_CAP = 0x1e0
REP_CYCLE = 0xa4
REP_PENDING = 0xa7
REP_SCALE = 0x5f0
REP_MIN = 0x5f4
REP_MAX = 0x5f8

# ---------------------------------------------------------------- scratch layout
S_LISTS, S_MONS, S_RECS, S_P3D, S_REPS, S_GROUPS, S_COMBAT, S_MISC = range(8)
L_MAIN, L_UNBORN, L_GROUPS = 0x00, 0x10, 0x20
L_ILIST = 0x40               # W8IList per group (0x10 each, 8 groups)
L_MAIN_DATA = 0x100          # data[-1..-4] = 0xfc..0xf0 (kept zero unless labelled)
L_UNBORN_DATA = 0x200
L_GROUP_DATA = 0x300
L_ILIST_DATA = 0x400         # 0x80 per group
MI_STRIDE = 0x430
REC_STRIDE = 0x2a0
P3D_STRIDE = 0x220
REP_STRIDE = 0x600
GROUP_STRIDE = 0x130
ATTACH_BASE = 0x1000         # navigator attachments in S6
M_FILE = 0x000               # caller file string in S7
M_POS = 0x100
M_TEXT = 0x200
M_SLOT = 0x300

# ---------------------------------------------------------------- MONSTERS.DBS rows
MONSTERS = [
    # (record, name0, name1, name2, name3, hp dice (base, count, sides), attribute_values,
    #  combat_move_range bits, experience, experience_override, display_level, flags, npc_kind,
    #  model_index, alternate_model_index)
    (0, 'Lay Brother', 'Lay Brother', 'Person', 'Persons', (70, 6, 8), (65, 65, 70, 80, 70), 0x3f800000, 3619, 0x0, 7, 0x01, 26, 765952, 786432),
    (1, 'Pustulant Slime', 'Pustulant Slimes', 'Slime', 'Slimes', (10, 15, 3), (40, 10, 60, 45, 40), 0x3f4ccccd, 2670, 0x0, 5, 0x00, 250, 217088, 229376),
    (2, 'Saxx', 'Saxx', 'Umpani', 'Umpani', (110, 6, 12), (90, 60, 80, 75, 70), 0x3f800000, 12330, 0x0, 5, 0x01, 1, 1052672, 1077248),
    (3, 'Wolf Spider', 'Wolf Spiders', 'Bug', 'Bugs', (5, 3, 8), (10, 10, 50, 50, 50), 0x3f99999a, 2050, 0x0, 4, 0x00, 250, 0, 0),
    (4, 'Swarming Roach', 'Swarming Roaches', 'Bug', 'Bugs', (2, 3, 6), (10, 10, 50, 80, 80), 0x3f99999a, 390, 0x0, 3, 0x00, 250, 0, 0),
    (5, 'Nebdar', 'Nebdar', 'Sorceress', 'Sorceresses', (410, 10, 20), (80, 99, 80, 80, 99), 0x3fa66666, 466290, 0x0, 28, 0x10, 250, 0, 0),
    (6, 'Antone Rapax', 'Antone Rapax', 'Rapax', 'Rapax', (165, 6, 12), (99, 60, 80, 65, 60), 0x3f8ccccd, 13471, 0x0, 6, 0x11, 3, 0, 0),
    (7, 'Lorrac', 'Lorrac', 'Person', 'Persons', (90, 8, 8), (100, 80, 120, 120, 80), 0x3f800000, 11512, 0x0, 5, 0x11, 5, 0, 0),
    (8, "He'Li", "He'Li", 'person', 'persons', (92, 8, 8), (100, 80, 120, 120, 80), 0x3f800000, 27360, 0x0, 7, 0x11, 4, 0, 0),
    (9, 'Sgt. Balbrak', 'Sgt. Balbrak', 'Umpani', 'Umpani', (225, 20, 20), (85, 70, 75, 85, 70), 0x3f99999a, 31986, 0x0, 8, 0x11, 12, 0, 0),
    (10, 'Urq', 'Urq ', 'Mook', 'Mooks', (312, 9, 12), (80, 75, 70, 70, 70), 0x3f800000, 47766, 0x0, 9, 0x01, 104, -842150451, -842150451),
    (11, 'Hologram', 'Hologram', 'Hologram', 'Hologram', (100, 10, 20), (0, 0, 0, 0, 0), 0x00000000, 0, 0x64, 0, 0x11, 23, -842150451, -842150451),
    (12, 'Bank guard', 'Bank guards', 'Man', 'Men', (32, 7, 10), (90, 80, 70, 70, 50), 0x3f800000, 5720, 0x0, 7, 0x11, 13, 0, 0),
    (13, 'Rodan Lewarx', 'Rodan Lewarx ', 'Umpani', 'Umpani', (340, 10, 20), (95, 60, 79, 75, 99), 0x3fa66666, 31165, 0x0, 8, 0x01, 17, 0, 0),
    (14, 'Giant Bat', 'Giant Bats', 'Bat', 'Bats', (225, 10, 30), (80, 50, 90, 100, 95), 0x40000000, 35388, 0x0, 8, 0x00, 250, 0, 0),
    (15, 'Rapax Archer', 'Rapax Archers', 'Rapax', 'Rapax', (170, 10, 10), (88, 67, 99, 78, 80), 0x3f8ccccd, 33555, 0x0, 14, 0x00, 250, 0, 0),
    (16, 'Seeker', 'Seekers', 'Beast', 'Beasts', (10, 6, 6), (65, 20, 65, 55, 40), 0x3f8ccccd, 1212, 0x0, 3, 0x10, 250, 0, 0),
    (17, 'Screaming Head', 'Screaming Heads', 'Apparition', 'Apparitions', (50, 4, 8), (10, 80, 60, 60, 50), 0x3fa66666, 9939, 0x0, 7, 0x00, 250, 0, 0),
    (18, 'Shrieker Bat', 'Shrieker Bats', 'Bat', 'Bats', (12, 4, 13), (30, 30, 90, 90, 90), 0x3fb33333, 2800, 0x0, 7, 0x00, 250, 0, 0),
    (19, 'Savant Guard', 'Savant Guards', 'Android', 'Androids', (30, 3, 4), (60, 60, 65, 65, 60), 0x3f933333, 2782, 0x0, 6, 0x04, 250, 0, 0),
    (50, 'Rapax Warlock', 'Rapax Warlocks', 'Rapax', 'Rapax', (204, 5, 10), (80, 95, 80, 80, 80), 0x3f99999a, 147310, 0x0, 22, 0x01, 38, 0, 0),
    (51, 'RFS-81', 'RFS-81', 'Android', 'Androids', (328, 10, 4), (60, 60, 65, 90, 60), 0x3f933333, 10739, 0x0, 5, 0x01, 32, 0, 0),
    (52, 'RFS-81', 'RFS-81', 'Android', 'Androids', (328, 10, 4), (90, 60, 65, 95, 95), 0x3fa66666, 35429, 0x0, 8, 0x01, 33, 0, 0),
    (53, "Sadok T'Rang", "Sadok T'Rang", "T'Rang", "T'Rang", (103, 8, 8), (70, 90, 75, 75, 75), 0x3fc00000, 157393, 0x0, 14, 0x11, 34, 0, 0),
    (54, "Tantris T'Rang", "Tantris T'Rang", "T'Rang", "T'Rang", (143, 7, 4), (80, 75, 75, 90, 80), 0x3fc00000, 120057, 0x0, 13, 0x11, 35, 0, 0),
    (55, 'Millipede', 'Millipedes', 'Bug', 'Bugs', (20, 3, 10), (50, 10, 90, 80, 50), 0x40000000, 5414, 0x0, 9, 0x00, 250, 0, 0),
    (56, "T'Rang Guarder", "T'Rang Guarders", "T'Rang", "T'Rang", (30, 9, 9), (50, 40, 70, 70, 65), 0x3f8ccccd, 3190, 0x0, 5, 0x01, 31, 0, 0),
    (57, "T'Rang Stalker", "T'Rang Stalkers", "T'Rang", "T'Rang", (20, 3, 7), (60, 65, 70, 70, 90), 0x3fb33333, 12226, 0x0, 8, 0x00, 31, 0, 0),
    (58, "T'Rang Sniper", "T'Rang Sniper", "T'Rang", "T'Rang", (122, 6, 4), (65, 70, 70, 90, 70), 0x3fb33333, 41093, 0x0, 12, 0x01, 39, 0, 0),
    (59, "T'Rang Keeper", "T'Rang Keepers", "T'Rang", "T'Rang", (92, 8, 8), (65, 70, 70, 90, 85), 0x3fb33333, 42227, 0x0, 12, 0x01, 39, 0, 0),
    (78, 'Rapax Samurai', 'Rapax Samurais', 'Rapax', 'Rapax', (245, 6, 12), (90, 85, 80, 90, 70), 0x3f99999a, 47687, 0x0, 19, 0x05, 38, 0, 0),
    (104, 'Amit', 'Amit', 'Trynnie', 'Trynnies', (100, 8, 12), (70, 95, 90, 90, 70), 0x3f800000, 94399, 0x0, 12, 0x11, 48, 0, 0),
    (131, 'Sgt. Rubble', 'Sgt. Rubble', 'Umpani', 'Umpani', (290, 8, 20), (90, 50, 85, 75, 85), 0x3f99999a, 26344, 0x0, 7, 0x11, 41, 0, 0),
    (174, 'Aletheides', 'Aletheides', 'Being', 'Beings', (451, 1, 6), (100, 100, 100, 100, 100), 0x3f800000, 349611, 0x0, 18, 0x11, 46, 0, 0),
    (175, 'Aletheides', 'Aletheides', 'Being', 'Beings', (451, 1, 6), (100, 100, 100, 100, 100), 0x3f800000, 193267, 0x0, 15, 0x11, 45, 0, 0),
    (176, 'Aletheides', 'Aletheides', 'Being', 'Beings', (451, 1, 6), (100, 100, 100, 100, 100), 0x3f800000, 318992, 0x0, 17, 0x11, 47, 0, 0),
    (177, 'Rapax Patrol', 'Rapax Patrols', 'Rapax', 'Rapax', (74, 12, 20), (90, 70, 80, 90, 80), 0x3fa66666, 14613, 0x0, 11, 0x05, 54, 0, 0),
    (178, 'Rapax Prince', 'Rapax Prince', 'Rapax', 'Rapax', (428, 12, 15), (100, 85, 80, 100, 80), 0x3fb33333, 323245, 0x0, 18, 0x11, 49, 0, 0),
    (194, 'Dark Savant', 'Dark Savants', 'Dread Lord', 'Dread Lord', (750, 10, 20), (110, 110, 100, 100, 100), 0x40000000, 983240, 0x0, 25, 0x11, 51, 0, 0),
    (205, 'Shaman Das', 'Shaman Das', 'Trynnie', 'Trynnies', (45, 5, 12), (80, 95, 70, 65, 99), 0x3f800000, 14682, 0x0, 6, 0x11, 115, 0, 0),
    (210, "T'Rang Guarder", "T'Rang Guarders", "T'Rang", "T'Rang", (42, 4, 9), (60, 60, 80, 80, 80), 0x3fb33333, 8241, 0x0, 12, 0x01, 40, 0, 0),
    (211, 'Al-Adryian', 'Al-Adryian', 'Rapax', 'Rapax', (430, 5, 14), (65, 99, 90, 85, 90), 0x00000000, 220882, 0x0, 15, 0x11, 59, 0, 0),
    (212, 'Saydin', 'Saydin', 'Rapax', 'Rapax', (412, 8, 15), (100, 80, 80, 100, 70), 0x3fb33333, 479209, 0x0, 21, 0x11, 60, 0, 0),
    (213, 'Al-Asaiz', 'Al-Asaiz', 'Rapax', 'Rapax', (329, 7, 4), (60, 75, 115, 115, 95), 0x3f800000, 75454, 0x0, 11, 0x01, 61, 0, 0),
    (214, 'Al-Madeus', 'Al-Madeus', 'Rapax', 'Rapax', (329, 7, 4), (60, 75, 115, 115, 95), 0x3f800000, 73803, 0x0, 11, 0x01, 62, 0, 0),
    (215, 'Al-Lure', 'Al-Lure', 'Rapax', 'Rapax', (329, 7, 4), (60, 75, 115, 115, 95), 0x3f800000, 75042, 0x0, 11, 0x01, 63, 0, 0),
    (216, 'Al-Adryian', 'Al-Adryian', 'Rapax', 'Rapax', (180, 5, 14), (65, 99, 90, 85, 90), 0x00000000, 112638, 0x0, 12, 0x11, 65, 0, 0),
    (217, 'Al-Sedexus', 'Al-Sedexus', 'Demon', 'Demons', (500, 12, 12), (120, 90, 78, 89, 94), 0x3fb33333, 633636, 0x0, 22, 0x11, 66, 0, 0),
    (218, 'Burz', 'Burz', 'Trynnie', 'Trynnies', (214, 20, 10), (70, 60, 90, 85, 95), 0x3f99999a, 8221, 0x0, 5, 0x11, 80, 0, 0),
    (219, 'Rattus Rattus', 'Rattus Rattus', 'Rattkin', 'Rattkins', (182, 5, 30), (75, 60, 90, 80, 83), 0x3f99999a, 23296, 0x0, 7, 0x11, 82, 0, 0),
    (220, 'Savant Henchman', 'Savant Henchmen', 'Humanoid', 'Humanoids', (90, 5, 4), (65, 55, 50, 60, 60), 0x3f866666, 11410, 0x0, 8, 0x05, 83, 0, 0),
    (236, 'Shaman Das', 'Shaman Das', 'Trynnie', 'Trynnies', (40, 10, 4), (50, 75, 70, 65, 70), 0x3f800000, 4529, 0x0, 3, 0x11, 77, 0, 0),
    (249, 'Fuzzfas', 'Fuzzfas', 'Trynnie', 'Trynnie', (95, 8, 12), (75, 80, 50, 50, 50), 0x3f800000, 18929, 0x0, 7, 0x11, 73, 0, 0),
    (263, 'Screg ', 'Screg', 'Mook', 'Mooks', (64, 6, 4), (70, 80, 50, 40, 50), 0x3f800000, 3702, 0x0, 3, 0x01, 23, 0, 0),
    (274, 'Aletheides', 'Aletheides', 'Being', 'Beings', (451, 1, 6), (100, 100, 100, 100, 100), 0x3f800000, 318992, 0x0, 17, 0x11, 6, 0, 0),
    (292, 'Al-Sedexus', 'Al-Sedexus', 'Demon', 'Demons', (500, 12, 12), (120, 90, 78, 89, 94), 0x3fb33333, 463568, 0x0, 20, 0x11, 64, 0, 0),
    (298, 'Rafe', 'Rafes', 'Rapax', 'Rapax', (468, 12, 12), (80, 55, 60, 60, 45), 0x3f8ccccd, 5681, 0x0, 5, 0x11, 68, 0, 0),
    (306, 'Trynnie Guard', 'Trynnie Guards', 'Trynnie', 'Trynnies', (24, 9, 9), (50, 55, 90, 85, 65), 0x3f800000, 2019, 0x0, 5, 0x01, 112, 0, 0),
    (307, 'Mook', 'Mooks', 'Mook', 'Mooks', (62, 6, 8), (90, 90, 50, 60, 90), 0x3fb33333, 17596, 0x0, 12, 0x01, 105, 0, 0),
    (314, 'Prisoner', 'Prisoners', 'Rapax', 'Rapax', (468, 7, 8), (80, 55, 60, 60, 45), 0x3f8ccccd, 4550, 0x0, 5, 0x11, 97, 0, 0),
    (329, 'Rapax Warlock', 'Rapax Warlocks', 'Rapax', 'Rapax', (204, 5, 10), (80, 95, 80, 80, 80), 0x3f99999a, 147310, 0x0, 20, 0x01, 38, 0, 0),
    (356, 'Death01', 'Deaths', 'Death', 'Deaths', (0, 10, 10), (10, 10, 10, 10, 10), 0x00000000, 470, 0xcdcdcdcd, 0, 0x00, 250, -842150451, -842150451),
    (381, 'Jan-Ette', 'Jan-Ette', 'Helazoid', 'Helazoid', (164, 16, 4), (100, 80, 120, 120, 80), 0x3f4ccccd, 11117, 0x1, 5, 0x01, 98, 0, 0),
    (397, 'Al-Saxx', 'Saxx', 'Demon', 'Demons', (750, 12, 12), (75, 99, 99, 99, 99), 0x3fb33333, 283370, 0x0, 17, 0x11, 50, 0, 0),
    (440, 'Savant Orb', 'Savant Orbs', 'Orb', 'Orbs', (37, 0, 50), (30, 80, 80, 70, 70), 0x3f99999a, 5416, 0x0, 9, 0x11, 108, 0, 0),
    (548, 'Target Dummy', 'Target Dummies', 'Android', 'Androids', (100, 8, 8), (60, 10, 60, 74, 40), 0x3a83126f, 3531, 0x1, 6, 0x10, 250, 0, 0),
    (550, 'Intoxicated Rapax', 'Intoxicated Rapax', 'Rapax', 'Rapax', (225, 6, 12), (90, 70, 80, 90, 50), 0x3f99999a, 44533, 0x4e20, 14, 0x04, 250, 0, 0),
    (573, 'Savant Orb', 'Savant Orbs', 'Orb', 'Orbs', (37, 0, 50), (30, 80, 80, 70, 70), 0x3f99999a, 5416, 0x0, 11, 0x11, 108, 0, 0),
    (592, 'Savant Orb', 'Savant Orbs', 'Orb', 'Orbs', (37, 0, 50), (30, 80, 80, 70, 70), 0x3f99999a, 5416, 0x0, 17, 0x11, 108, 0, 0),
    (594, 'Baruta Fish', 'Baruta Fish', 'Fish', 'Fish', (60, 6, 14), (10, 10, 80, 99, 80), 0x3fa66666, 7068, 0x0, 11, 0x00, 250, 0, 0),
]
ROW = {m[0]: m for m in MONSTERS}
ROW_IDS = sorted(ROW)
N_MONSTER_RECORDS = 595
NPC_KINDS = sorted({m[12] for m in MONSTERS if m[12] != 250})

COND_EDGE = [0x80000000, 0xffffffff, 0xfffffff0]
BOOL_EDGE = [2, 0x80, 0xff]
LOC_EDGE = [0, 1, -1, 9999, 10000, 0xffff, 0x10000, 0x7fffffff, -0x80000000]


# ---------------------------------------------------------------- helpers
def u8(v):
    return struct.pack('<B', int(v) & 0xff)


def u32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def f32b(x):
    return struct.pack('<f', x)


def f32r(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


def fbits(b):
    return struct.unpack('<f', struct.pack('<I', b & 0xffffffff))[0]


def wname(s):
    b = s.encode('utf-16-le')[:48]
    return b + bytes(48 - len(b))


def emit(c, addr, data, gap=40):
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


def pick(r, weighted):
    total = sum(w for w, _ in weighted)
    x = r.random() * total
    for w, v in weighted:
        x -= w
        if x < 0:
            return v() if callable(v) else v
    v = weighted[-1][1]
    return v() if callable(v) else v


def bool_byte(r, p_true, edge_p=0.0):
    if r.random() < p_true:
        return r.choice(BOOL_EDGE) if r.random() < edge_p else 1
    return 0


def edge_slots(r, p_cond=0.08, p_bool=0.06, count=8):
    """At most one slot per case gets an out-of-enum condition and at most one a
    non-canonical bool byte, so most cases stay free of these edges."""
    ec = r.randrange(count) if r.random() < p_cond else -1
    eb = r.randrange(count) if r.random() < p_bool else -1
    return ec, eb


def hp_value(r):
    x = r.random()
    if x < 0.72:
        return r.randrange(1, 400)
    if x < 0.9:
        return 0
    return r.choice([1, 0x7fffffff, 0x80000000, 0xffffffff])


def char_cond(r, edge_p=0.0):
    x = r.random()
    if x < edge_p:
        return r.choice(COND_EDGE)
    if x < 0.55:
        return 0
    if x < 0.85:
        return r.randrange(1, 0x14)
    return r.choice([0x0b, 0x0c, 0x0d, 0x0e, 0x12, 0x13, 0x14])


def species_pick(r):
    x = r.random()
    if x < 0.8:
        return r.choice(ROW_IDS)
    if x < 0.95:
        return r.randrange(0, N_MONSTER_RECORDS)
    return r.choice([0, N_MONSTER_RECORDS - 1, N_MONSTER_RECORDS, 777, 998, 999])


def row_for(r, species):
    return ROW.get(species) or r.choice(MONSTERS)


def record_blob(row, fields, over=None):
    b = Blob(bytes(MR_SIZE))
    (rid, n0, n1, n2, n3, hp, attrs, cmr, exp, expo, dlevel, flags, npck, mi, ami) = row
    if 'names' in fields:
        for k, s in enumerate((n0, n1, n2, n3)):
            b[MR_NAMES + 0x30 * k:MR_NAMES + 0x30 * (k + 1)] = wname(s)
    if 'npc' in fields:
        b.u8(MR_NPC_KIND, npck)
        b.u8(MR_FLAGS, flags)
    if 'attrs' in fields:
        b[MR_ATTRS:MR_ATTRS + 5] = bytes(attrs)
    if 'hp' in fields:
        struct.pack_into('<hBB', b, MR_HP, hp[0], hp[1], hp[2])
    if 'exp' in fields:
        b.u32(MR_EXP, exp)
        b.u32(MR_EXPO, expo)
    if 'id' in fields:
        b.u16(MR_ID, rid)
    if 'cmr' in fields:
        b.u32(MR_CMR, cmr)
    if 'level' in fields:
        b.u8(MR_DLEVEL, dlevel)
        b.u8(MR_ELEVEL, dlevel)
    if 'model' in fields:
        b.u32(MR_MODEL, mi)
        b.u32(MR_MODEL + 4, ami)
    for off, data in (over or {}).items():
        b[off:off + len(data)] = data
    return b


class World:
    """Fake monster world in scratch, wired into gXStatus for the call."""

    def __init__(self, ctx, c):
        self.ctx = ctx
        self.c = c
        self.S = [ctx.scratch(i) for i in range(8)]
        self.gx = ctx.g('gXStatus')
        self.nmon = self.np3d = self.nrep = self.ngroup = self.nrec = 0
        self.recs = {}

    def info(self, blob=None):
        a = self.S[S_MONS] + self.nmon * MI_STRIDE
        self.nmon += 1
        if blob is not None:
            emit(self.c, a, blob)
        return a

    def p3d(self, info=None, blob=None):
        p = self.S[S_P3D] + self.np3d * P3D_STRIDE
        self.np3d += 1
        if info is not None:
            self.c.setp(info + MI_P3D, p)
        if blob is not None:
            emit(self.c, p, blob)
        return p

    def rep(self, p3d, blob):
        a = self.S[S_REPS] + self.nrep * REP_STRIDE
        self.nrep += 1
        self.c.setp(p3d + M3_REP, a)
        emit(self.c, a, blob)
        return a

    def loose_record(self, blob):
        a = self.S[S_RECS] + self.nrec * REC_STRIDE
        self.nrec += 1
        emit(self.c, a, blob)
        return a

    def record(self, species, blob):
        """gXStatus.monster_record_cache[species] -> a scratch record (once per species)."""
        if species in self.recs:
            return self.recs[species]
        a = self.loose_record(blob)
        self.recs[species] = a
        self.c.setp(self.gx + GX_RECCACHE + 4 * species, a)
        return a

    def group(self, blob, members=None):
        """W8MonsterGroup in S5; members = IList of location ids (S0)."""
        k = self.ngroup
        self.ngroup += 1
        g = self.S[S_GROUPS] + k * GROUP_STRIDE
        emit(self.c, g, blob)
        if members is not None:
            L = self.S[S_LISTS]
            il = L + L_ILIST + 0x10 * k
            if members:
                self.c.set(L + L_ILIST_DATA + 0x80 * k, b''.join(u32(m) for m in members))
            self.c.setp(il, L + L_ILIST_DATA + 0x80 * k)
            self.c.set(il + 4, struct.pack('<ii', max(10, len(members)), len(members)))
            self.c.setp(g + G_MONSTERS, il)
        return g

    def plist(self, off, data_off, addrs, count=None):
        c, L = self.c, self.S[S_LISTS]
        for i, a in enumerate(addrs):
            if a is not None:
                c.setp(L + data_off + 4 * i, a)
        c.setp(L + off, L + data_off)
        n = len(addrs) if count is None else count
        c.set(L + off + 4, struct.pack('<ii', max(10, len(addrs)), n))
        return L + off

    def wire(self, slot, off, data_off, addrs, count=None):
        """addrs None -> the gXStatus list pointer is NULL for the call."""
        if addrs is None:
            self.c.set(self.gx + slot, u32(0))
        else:
            self.c.setp(self.gx + slot, self.plist(off, data_off, addrs, count))

    def wire_main(self, addrs, count=None):
        self.wire(GX_MONLIST, L_MAIN, L_MAIN_DATA, addrs, count)

    def wire_unborn(self, addrs, count=None):
        self.wire(GX_UNBORN, L_UNBORN, L_UNBORN_DATA, addrs, count)

    def wire_groups(self, addrs):
        self.wire(GX_GROUPLIST, L_GROUPS, L_GROUP_DATA, addrs)
        self.c.set(self.gx + GX_ENCOUNTER, u32(0))

    def data_minus(self, k, addr):
        """Pointer at main data[-k] (PLGet with a negative index)."""
        self.c.setp(self.S[S_LISTS] + L_MAIN_DATA - 4 * k, addr)


def xrow(ctx, slot):
    return (ctx.g('g_status') + GS_XCHAR).deref() + slot * XROW


def caller_file(ctx, c):
    s = ctx.scratch(S_MISC) + M_FILE
    c.set(s, b'C:\\w8diff\\monster_manager.cpp\0')
    return s


def mon_blob(loc=0, group=0, species=0):
    b = Blob(bytes(MI_SPECIES + 4))
    b.u32(MI_LOC, loc)
    b.u32(MI_GROUP, group)
    b.u32(MI_SPECIES, species)
    return b


def gen_locs(r, n):
    out = []
    for _ in range(n):
        x = r.random()
        if x < 0.06 and out:
            out.append(r.choice(out))
        elif x < 0.12:
            out.append(r.choice(LOC_EDGE))
        else:
            out.append(r.randrange(1, 4000))
    return out


def cases(ctx):
    _get_index(ctx)
    _script_part(ctx)
    _db_from_species(ctx)
    _data_for_info(ctx)
    _info_from_id(ctx)
    _data_by_location(ctx)
    _monster_by_location(ctx)
    _combat_move_range(ctx)
    _next_monster_info(ctx)
    _quadrant(ctx)
    _cycle_fallback(ctx)
    _convert_attributes(ctx)
    _find_by_species(ctx)
    _reset_living(ctx)
    _control_state(ctx)
    _find_nearest(ctx)
    _calc_scale(ctx)
    _experience(ctx)
    _any_dying(ctx)
    _toggle_stance(ctx)
    _monster_name(ctx)
    _avg_party_level(ctx)
    _best_skill(ctx)
    _format_health(ctx)


# ---------------------------------------------------------------- location lookups
def _lookup_world(ctx, c, r, species=False, p3d=False):
    """Both monster lists with location ids (duplicates, edges); optional species records
    (content irrelevant: callers compare the record pointer) and p3D stubs."""
    w = World(ctx, c)
    nm = r.choice([0, 1, 2, 3, 4, 6, 8, 12, 16])
    nu = r.choice([0, 0, 0, 1, 2, 3, 5])
    locs = gen_locs(r, nm + nu)
    main, unborn = [], []
    for k in range(nm + nu):
        sp = species_pick(r) if species else 0
        a = w.info(mon_blob(loc=locs[k], species=sp))
        pp = None
        if p3d and r.random() < 0.85:
            pp = w.p3d(a)
        if species:
            w.record(sp, record_blob(row_for(r, sp), ()))   # only the pointer is compared
        (main if k < nm else unborn).append({'addr': a, 'loc': locs[k], 'p3d': pp})
    main_count = unborn_count = None
    if main and r.random() < 0.08:
        main_count = r.randrange(0, len(main))
    if unborn and r.random() < 0.08:
        unborn_count = r.randrange(0, len(unborn))
    null_main = r.random() < 0.05
    null_unborn = r.random() < 0.08
    w.wire_main(None if null_main else [m['addr'] for m in main], main_count)
    w.wire_unborn(None if null_unborn else [m['addr'] for m in unborn], unborn_count)
    vis_main = [] if null_main else main[:len(main) if main_count is None else main_count]
    vis_unborn = [] if null_unborn else unborn[:len(unborn) if unborn_count is None else unborn_count]
    return w, main, unborn, vis_main, vis_unborn, {'main': len(main), 'unborn': len(unborn),
                                                   'main_count': main_count,
                                                   'unborn_count': unborn_count,
                                                   'null_main': int(null_main),
                                                   'null_unborn': int(null_unborn)}


def _target_loc(r, main, unborn):
    x = r.random()
    if x < 0.4 and main:
        return r.choice(main)['loc'], 'main'
    if x < 0.6 and unborn:
        return r.choice(unborn)['loc'], 'unborn'
    if x < 0.9:
        known = {m['loc'] for m in main + unborn}
        v = r.randrange(1, 4000)
        while v in known:
            v = r.randrange(1, 4000)
        return v, 'missing'
    return r.choice(LOC_EDGE), 'edge'


def _assert_flag(r):
    return r.choice([0, 1]) if r.random() < 0.9 else r.choice([2, 0xff, 0x100, 0x101])


def _get_index(ctx):
    """unsigned int MonsterGetIndexByLocationID(int line, const char* file, int id, bool assert)"""
    fn = ctx.fn(0x004e5550)
    for i in range(ctx.n(250)):
        r = ctx.rng('getindex', i)
        c = ctx.case('getindex.%d' % i, fn, conv='c', ret='i')
        w, main, unborn, vm, vu, info = _lookup_world(ctx, c, r)
        loc, kind = _target_loc(r, main, unborn)
        flag = _assert_flag(r)
        c.arg(r.choice([0, 0x412, 0x8e6, r.randrange(0, 0x10000), -1]))
        c.arg(caller_file(ctx, c))
        c.arg(loc)
        c.arg(flag)
        c.note(loc=loc, kind=kind, flag=flag, **info)
        finish(c)


def _info_from_id(ctx):
    """W8MonsterInfo* MonsterInfoFromID(int line, const char* file, int id, bool assert)"""
    fn = ctx.fn(0x004e5840)
    for i in range(ctx.n(200)):
        r = ctx.rng('infofromid', i)
        c = ctx.case('infofromid.%d' % i, fn, conv='c', ret='p')
        w, main, unborn, vm, vu, info = _lookup_world(ctx, c, r)
        loc, kind = _target_loc(r, main, unborn)
        flag = _assert_flag(r)
        c.arg(r.randrange(0, 0x1000))
        c.arg(caller_file(ctx, c))
        c.arg(loc)
        c.arg(flag)
        c.note(loc=loc, kind=kind, flag=flag, **info)
        finish(c)


def _data_by_location(ctx):
    """W8MonsterRecord* GetMonsterDataByLocationID(int id). Not found: assert 0x5c1, then
    MonsterGetScriptPartByLocationIndex(0xffffffff) asserts 0x5da and reads data[-1]."""
    fn = ctx.fn(0x004e58b0)
    for i in range(ctx.n(150)):
        r = ctx.rng('databylocation', i)
        c = ctx.case('databylocation.%d' % i, fn, conv='c', ret='p')
        w, main, unborn, vm, vu, info = _lookup_world(ctx, c, r, species=True)
        loc, kind = _target_loc(r, main, unborn)
        if kind in ('missing', 'edge') and main and r.random() < 0.2:
            w.data_minus(1, r.choice(main)['addr'])
            c.note(edge='data_minus_1')
        c.arg(loc)
        c.note(loc=loc, kind=kind, **info)
        finish(c)


def _monster_by_location(ctx):
    """W8Monster* GetMonsterByLocationID(int id)"""
    fn = ctx.fn(0x004e5950)
    for i in range(ctx.n(150)):
        r = ctx.rng('monsterbylocation', i)
        c = ctx.case('monsterbylocation.%d' % i, fn, conv='c', ret='p')
        w, main, unborn, vm, vu, info = _lookup_world(ctx, c, r, p3d=True)
        loc, kind = _target_loc(r, main, unborn)
        if r.random() < 0.06:
            loc, kind = -1, 'minus_one'
        c.arg(loc)
        c.note(loc=loc, kind=kind, **info)
        finish(c)


def _script_part(ctx):
    """W8MonsterInfo* MonsterGetScriptPartByLocationIndex(unsigned int index)"""
    fn = ctx.fn(0x004e5620)
    for i in range(ctx.n(200)):
        r = ctx.rng('scriptpart', i)
        c = ctx.case('scriptpart.%d' % i, fn, conv='c', ret='p')
        w = World(ctx, c)
        nm = r.choice([0, 1, 2, 3, 5, 8, 10])
        nu = r.choice([0, 0, 1, 2, 3, 5])
        main = [None if r.random() < 0.08 else w.info(mon_blob(loc=r.randrange(1, 4000)))
                for _ in range(nm)]
        unborn = [None if r.random() < 0.08 else w.info(mon_blob(loc=r.randrange(1, 4000)))
                  for _ in range(nu)]
        null_main = r.random() < 0.04
        null_unborn = r.random() < 0.06
        w.wire_main(None if null_main else main)
        w.wire_unborn(None if null_unborn else unborn)
        if r.random() < 0.1:
            k = r.randrange(1, 5)
            w.data_minus(k, w.info(mon_blob(loc=r.randrange(1, 4000))))
            c.note(edge='data_minus_%d' % k)
        idx = pick(r, [
            (35, lambda: r.randrange(nm) if nm else 0),
            (25, lambda: 10000 + (r.randrange(nu) if nu else 0)),
            (10, lambda: nm + r.choice([0, 0, 1, 5])),
            (10, lambda: 10000 + nu + r.choice([0, 0, 1, 7])),
            (12, lambda: r.choice([9999, 19999, 20000, 20001, 0x7fffffff])),
            (8, lambda: r.choice([0xffffffff, 0xfffffffe, 0xfffffffc, 0x80000000])),
        ])
        c.arg(idx)
        c.note(index=idx, main=nm, unborn=nu, null_main=int(null_main),
               null_unborn=int(null_unborn),
               null_entries=sum(1 for x in main + unborn if x is None))
        finish(c)


# ---------------------------------------------------------------- record accessors
def _db_from_species(ctx):
    """W8MonsterRecord* MonsterDBFromSpecies(unsigned int species). The cache slot is always
    set (no file load). Species 1000 asserts (0x5f3) and reads the dword after the cache
    (gXStatus.gameplay_timer), which is pointed at scratch for the call."""
    fn = ctx.fn(0x004e57c0)
    for i in range(ctx.n(100)):
        r = ctx.rng('dbfromspecies', i)
        c = ctx.case('dbfromspecies.%d' % i, fn, conv='c', ret='p')
        w = World(ctx, c)
        sp = 1000 if i < 4 else species_pick(r)
        for d in (-2, -1, 1, 2):
            if 0 <= sp + d < 1000 and r.random() < 0.5:
                w.record(sp + d, record_blob(row_for(r, sp + d), ('id',)))
        w.record(sp, record_blob(row_for(r, sp), ('id',)))
        c.arg(sp)
        c.note(species=sp)
        if sp >= 1000:
            c.note(edge='species_1000')
        finish(c)


def _data_for_info(ctx):
    """W8MonsterRecord* GetMonsterDataForInfo(W8MonsterInfo*)"""
    fn = ctx.fn(0x004e5720)
    for i in range(ctx.n(100)):
        r = ctx.rng('dataforinfo', i)
        c = ctx.case('dataforinfo.%d' % i, fn, conv='c', ret='p')
        w = World(ctx, c)
        sp = species_pick(r)
        for d in (-1, 1):
            if 0 <= sp + d < 1000 and r.random() < 0.5:
                w.record(sp + d, record_blob(row_for(r, sp + d), ('id',)))
        w.record(sp, record_blob(row_for(r, sp), ('id',)))
        info = w.info(mon_blob(loc=r.randrange(1, 4000), group=r.randrange(0, 50), species=sp))
        c.arg(info)
        c.note(species=sp)
        finish(c)


def _combat_move_range(ctx):
    """float GetMonsterCombatMoveRange(W8MonsterInfo*): record +0x1ba * 20.0f"""
    fn = ctx.fn(0x004e5990)
    edges = [0.0, -0.0, 1.0, -1.0, 0.001, 1e-40, 1.4e-45, 1.7e37, -1.7e37, 123456.789, 0.05,
             3.0e-39]
    rare = [float('inf'), float('-inf'), float('nan')]
    for i in range(ctx.n(150)):
        r = ctx.rng('combatmoverange', i)
        c = ctx.case('combatmoverange.%d' % i, fn, conv='c', ret='f')
        w = World(ctx, c)
        sp = species_pick(r)
        row = row_for(r, sp)
        x = r.random()
        if x < 0.6:
            bits = row[7]
        elif x < 0.95:
            bits = struct.unpack('<I', f32b(r.choice(edges)))[0]
        else:
            bits = struct.unpack('<I', f32b(r.choice(rare)))[0]
        w.record(sp, record_blob(row, ('id',), {MR_CMR: u32(bits)}))
        info = w.info(mon_blob(loc=r.randrange(1, 4000), species=sp))
        c.arg(info)
        c.note(species=sp, range=fbits(bits))
        finish(c)


def _experience(ctx):
    """unsigned int GetMonsterExperience(const W8MonsterRecord*): override if > 0 (unsigned)"""
    fn = ctx.fn(0x004e6780)
    edges = [0, 1, 2, 100, 0x7fffffff, 0x80000000, 0xcdcdcdcd, 0xfffffffe, 0xffffffff]
    for i in range(ctx.n(100)):
        r = ctx.rng('experience', i)
        c = ctx.case('experience.%d' % i, fn, conv='c', ret='i')
        w = World(ctx, c)
        row = r.choice(MONSTERS)
        exp, expo = row[8], row[9]
        if r.random() < 0.5:
            expo = r.choice(edges)
        if r.random() < 0.3:
            exp = r.choice(edges)
        rec = w.loose_record(record_blob(row, ('names', 'id'), {MR_EXP: u32(exp),
                                                               MR_EXPO: u32(expo)}))
        c.arg(rec)
        c.note(record=row[0], experience=exp, override=expo)
        finish(c)


def _cycle_fallback(ctx):
    """int GetMonsterCycleFallbackValue(unsigned int species). The record's cycle name is never
    a registered GrCycle, so the result is model_index or alternate_model_index by render
    option 14 (g_render_options->option_states[14], set for the call)."""
    fn = ctx.fn(0x004e5b50)
    opt = ctx.g('g_render_options').deref() + RO_STATES + RO_ADDITIONAL_ANIMATIONS
    for i in range(ctx.n(100)):
        r = ctx.rng('cyclefallback', i)
        c = ctx.case('cyclefallback.%d' % i, fn, conv='c', ret='i')
        w = World(ctx, c)
        sp = species_pick(r)
        row = row_for(r, sp)
        mi, ami = row[13], row[14]
        if r.random() < 0.5:
            mi = r.choice([0, 1, -1, r.randrange(0, 0x200000), -0x80000000, 0x7fffffff])
            ami = r.choice([0, 2, -1, r.randrange(0, 0x200000), 0x12345678])
        name = ('w8diff_nocycle_%04d' % i).encode('ascii') + b'\0'
        w.record(sp, record_blob(row, ('id',), {MR_MODEL: u32(mi), MR_MODEL + 4: u32(ami),
                                                MR_CYCLE: name}))
        state = r.choice([0, 1]) if r.random() < 0.9 else r.choice(BOOL_EDGE)
        c.set(opt, u8(state))
        c.arg(sp)
        c.note(species=sp, option=state, model=mi, alternate=ami)
        finish(c)


# ---------------------------------------------------------------- list walkers
def _next_monster_info(ctx):
    """W8MonsterInfo* GetNextMonsterInfo(bool reset): signed iterator vs PLLength"""
    fn = ctx.fn(0x004e5aa0)
    it = ctx.g('g_monster_info_iterator_index')
    for i in range(ctx.n(200)):
        r = ctx.rng('nextmonsterinfo', i)
        c = ctx.case('nextmonsterinfo.%d' % i, fn, conv='c', ret='p')
        w = World(ctx, c)
        n = r.choice([0, 1, 2, 3, 5, 8])
        main = [None if r.random() < 0.08 else w.info(mon_blob(loc=r.randrange(1, 4000)))
                for _ in range(n)]
        null_list = r.random() < 0.05
        w.wire_main(None if null_list else main)
        it_value = pick(r, [(50, lambda: r.randrange(0, n + 1) if n else 0),
                            (15, lambda: n + r.choice([1, 2])),
                            (15, lambda: r.choice([-1, -2, -4])),
                            (10, lambda: r.choice([0x7fffffff, 0x80000000, 0x40000000])),
                            (10, lambda: r.randrange(-4, 100))])
        if r.random() < 0.12:
            w.data_minus(1, w.info(mon_blob(loc=r.randrange(1, 4000))))
            c.note(edge='data_minus_1')
        reset = r.choice([0, 1]) if r.random() < 0.9 else r.choice([2, 0xff, 0x100])
        c.set(it, u32(it_value))
        c.cap(it, 4, 'iterator')
        c.arg(reset)
        c.note(count=n, iterator=it_value, reset=reset, null_list=int(null_list))
        finish(c)


def _find_by_species(ctx):
    """W8MonsterInfo* FindMonsterInfoBySpecies(unsigned int species)"""
    fn = ctx.fn(0x004e5e50)
    for i in range(ctx.n(150)):
        r = ctx.rng('findbyspecies', i)
        c = ctx.case('findbyspecies.%d' % i, fn, conv='c', ret='p')
        w = World(ctx, c)
        n = r.choice([0, 1, 2, 3, 5, 8, 12])
        sps = []
        for _ in range(n):
            sps.append(r.choice(sps) if sps and r.random() < 0.25 else species_pick(r))
        main = [w.info(mon_blob(loc=r.randrange(1, 4000), species=s)) for s in sps]
        count = None
        if main and r.random() < 0.08:
            count = r.randrange(0, len(main))
        w.wire_main(None if r.random() < 0.04 else main, count)
        x = r.random()
        if x < 0.6 and sps:
            target = r.choice(sps)
        elif x < 0.9:
            target = species_pick(r)
        else:
            target = r.choice([0, 999, 1000, 0xffffffff, 0x80000000])
        c.arg(target)
        c.note(species=target, list=','.join(map(str, sps)), count=count)
        finish(c)


def _any_dying(ctx):
    """bool AnyMonsterDying(void): W8Monster::IsDying = current cycle 0x15 or pending 0x15"""
    fn = ctx.fn(0x004e68c0)
    for i in range(ctx.n(150)):
        r = ctx.rng('anydying', i)
        c = ctx.case('anydying.%d' % i, fn, conv='c', ret='b')
        w = World(ctx, c)
        n = 0 if i < 3 else r.choice([1, 1, 2, 3, 4, 6, 8])
        q = 1.0 - 0.5 ** (1.0 / n) if n else 0.0
        main, desc = [], []
        for k in range(n):
            if r.random() < 0.04:
                main.append(None)
                desc.append('null')
                continue
            a = w.info(mon_blob(loc=r.randrange(1, 4000)))
            p = w.p3d(a)
            cyc = r.choice([0, 1, 2, 3, 6, 0x13, 0x14, 0x16, 0x17, 0x95, 0xff])
            pend = r.choice([0xff, 0xff, 0x14, 1, 2, 0x16, 0x95])
            if r.random() < q:
                if r.random() < 0.5:
                    cyc = 0x15
                else:
                    pend = 0x15
            rb = Blob(bytes(REP_PENDING + 1))
            rb.u8(REP_CYCLE, cyc)
            rb.u8(REP_PENDING, pend)
            w.rep(p, rb)
            main.append(a)
            desc.append('%x/%x' % (cyc, pend))
        w.wire_main(main)
        c.note(monsters=';'.join(desc))
        finish(c)


# ---------------------------------------------------------------- attributes
def _convert_attributes(ctx):
    """void ConvertMonsterAttributes(W8MonsterInfo*): record attribute byte + signed
    adjustment of STR/INT/DEX/SPD/SNS, clamped to 1..125"""
    fn = ctx.fn(0x004e5d00)
    attr_edge = [0, 1, 2, 124, 125, 126, 127, 128, 129, 200, 254, 255]
    adj_edge = [-128, -127, -126, -125, -124, -1, 1, 124, 125, 126, 127]
    for i in range(ctx.n(300)):
        r = ctx.rng('convertattributes', i)
        c = ctx.case('convertattributes.%d' % i, fn, conv='c', ret='v')
        w = World(ctx, c)
        sp = species_pick(r)
        row = row_for(r, sp)
        attrs = list(row[6])
        if r.random() < 0.4:
            for k in range(5):
                if r.random() < 0.5:
                    attrs[k] = r.choice(attr_edge) if r.random() < 0.6 else r.randrange(256)
        w.record(sp, record_blob(row, ('id',), {MR_ATTRS: bytes(attrs)}))
        adj = []
        for k in range(7):
            x = r.random()
            if x < 0.5:
                adj.append(0)
            elif x < 0.8:
                adj.append(r.randrange(-10, 11))
            else:
                adj.append(r.choice(adj_edge))
        b = mon_blob(loc=r.randrange(1, 4000), group=r.randrange(0, 50), species=sp)
        b = Blob(bytes(b) + bytes(MI_ATTRS + 5 - len(b)))
        b[MI_ADJ:MI_ADJ + 7] = struct.pack('<7b', *adj)
        b[MI_ATTRS:MI_ATTRS + 5] = bytes(r.randrange(256) for _ in range(5))
        info = w.info(b)
        c.arg(info)
        c.cap(info, MI_SIZE, 'info')
        c.note(species=sp, attrs=','.join(map(str, attrs)), adj=','.join(map(str, adj)))
        finish(c)


# ---------------------------------------------------------------- reset after combat
def _reset_living(ctx):
    """void ResetLivingMonstersAfterCombat(void): hp_current > 0 (unsigned) -> navigator
    ResetMovementAndGroupState and ai_mode 1..3 -> 0. With g_combat_inactive set every living
    monster has a linked navigator (the unlinked branch walks the live navigator groups)."""
    fn = ctx.fn(0x004e5ea0)
    inactive_g = ctx.g('g_combat_inactive')
    for i in range(ctx.n(200)):
        r = ctx.rng('resetliving', i)
        c = ctx.case('resetliving.%d' % i, fn, conv='c', ret='v')
        w = World(ctx, c)
        inactive = 1 if r.random() < 0.5 else 0
        if inactive and r.random() < 0.1:
            inactive = r.choice(BOOL_EDGE)
        c.set(inactive_g, u8(inactive))
        n = 0 if i < 2 else r.choice([1, 2, 3, 4, 5, 6])
        main, caps, desc = [], [], []
        attach = w.S[S_COMBAT] + ATTACH_BASE
        for k in range(n):
            hp = r.choice([0, 0, 1, 2, r.randrange(1, 500), r.randrange(1, 500), 0x7fffffff,
                           0x80000000, 0xffffffff])
            ai = r.choice([0, 1, 2, 3, 4, 5, 8]) if r.random() < 0.8 else \
                r.choice([0x10, 0x11, 0x13, 0x14, 0x81, 0x83, 0x90, 0xff])
            b = Blob(bytes(MI_AI + 1))
            b.u32(MI_LOC, r.randrange(1, 4000))
            b.u32(MI_HP, hp)
            b.u8(MI_AI, ai)
            a = w.info(b)
            main.append(a)
            caps.append((a, None))
            if hp == 0 and r.random() < 0.5:
                desc.append('hp0/nop3d')
                continue
            linked = 0 if (not inactive and r.random() < 0.5) else r.choice([0x1000, 0x5a5a5a5a, 1])
            pb = Blob(bytes(M3_LINKED + 4))
            pb.u32(M3_FLAGS, r.choice([0, 0x201, 0x200, 1, 0x80000000, r.getrandbits(32)]))
            struct.pack_into('<d', pb, M3_FLAGS + 4, r.uniform(-5.0, 500.0))
            struct.pack_into('<3f', pb, M3_FLAGS + 0xc, r.uniform(-1e4, 1e4), r.uniform(-1e3, 1e3),
                             r.uniform(-1e4, 1e4))
            pb.u32(M3_TARGET_NAV, r.choice([0, 0x12345678, r.getrandbits(32)]))
            pb.u32(M3_LINKED, linked)
            p = w.p3d(a, pb)
            c.set(p + M3_MFLAGS, u32(r.choice([0, 2, 1, 0xfffffffd, r.getrandbits(32)])))
            if inactive and linked:
                c.setp(p + M3_ATTACH, attach + 0x10 * k)
                c.set(attach + 0x10 * k, u32(r.choice([0x10000, 0xffffffff, 0x810000, 1,
                                                       r.getrandbits(32)])))
            caps[-1] = (a, p)
            desc.append('%x/%x/%s' % (hp, ai, 'L' if linked else '-'))
        w.wire_main(main)
        for k, (a, p) in enumerate(caps):
            c.cap(a, MI_SIZE, 'info%d' % k)
            if p is not None:
                c.cap(p, P3D_CAP, 'p3d%d' % k, ignore=[M3_ATTACH, M3_REP])
        if n:
            c.cap(attach, 0x10 * n, 'attachments')
        c.note(combat_inactive=inactive, monsters=';'.join(desc))
        if inactive not in (0, 1):
            c.note(edge='bool_byte')
        finish(c)


# ---------------------------------------------------------------- control state
def _control_state(ctx):
    """void SetMonsterControlState(W8MonsterInfo*, W8MonsterControlState). The navigator
    ClearMovement branch (old state LURED, new NONE/RESISTED, no linked navigator) touches the
    live octree, so those cases always carry a linked navigator."""
    fn = ctx.fn(0x004e6020)
    hcond_vals = [0, 0, 0, 1, 0x0c, 0x0d, 0x0e, 0x12]
    ctl_vals = [0, 0, 1, 1, 2, 3]
    for i in range(ctx.n(200)):
        r = ctx.rng('controlstate', i)
        c = ctx.case('controlstate.%d' % i, fn, conv='c', ret='v')
        w = World(ctx, c)
        ng = r.choice([1, 1, 2, 3])
        gids = r.sample(range(1, 600), ng)
        tg = r.randrange(ng)
        n = r.choice([1, 2, 3, 4, 6, 8])
        ec, eb = edge_slots(r, 0.12, 0.1, n)
        mons = []
        for k in range(n):
            g = gids[tg] if (k == 0 or r.random() < 0.6) else r.choice(gids)
            hc = r.choice(COND_EDGE) if k == ec else r.choice(hcond_vals)
            ctl = r.choice([0xff, 0xffffffff, 0x101]) if k == eb else r.choice(ctl_vals)
            b = Blob(bytes(MI_CONTROL + 4))
            b.u32(MI_LOC, 100 + k * 7 + r.randrange(7))
            b.u32(MI_GROUP, g)
            b.u32(MI_HCOND, hc)
            b.u32(MI_CONTROL, ctl)
            mons.append({'g': g, 'blob': b, 'loc': b.get_u32(MI_LOC), 'hc': hc, 'ctl': ctl})
        in_list = r.random() < 0.8
        tk = 0
        target = mons[tk]
        new = r.choice([0, 0, 1, 1, 2, 2, 3]) if r.random() < 0.9 else \
            r.choice([0xffffffff, 0x100, 0x102, 5])
        needs_link = new in (0, 2) and target['ctl'] == 1
        infos = [w.info(m['blob']) for m in mons]
        tinfo = infos[tk]
        if needs_link or r.random() < 0.3:
            pb = Blob(bytes(M3_LINKED + 4))
            pb.u32(M3_LINKED, r.choice([0x1000, 0x7777, 1]))
            w.p3d(tinfo, pb)
        listed = [a for k, a in enumerate(infos) if k != tk or in_list]
        w.wire_main(listed)
        w.wire_unborn([])
        # groups: members are the listed monsters of the group
        groups = []
        for gi, gid in enumerate(gids):
            members = [m['loc'] for k, m in enumerate(mons) if m['g'] == gid and (k != tk or in_list)]
            gb = Blob(bytes(G_ALTNAME + 1))
            gb.u32(G_ID, gid)
            gb.u32(G_COUNT, len(members))
            gb.u32(G_ACTIVE, r.choice([0, len(members), r.randrange(0, 9), 0xffffffff]))
            gb.u32(G_MONSTER_ID, r.randrange(0, 595))
            gb.u8(G_ALTNAME - 4, 1)   # members_active
            groups.append(w.group(gb, members))
        w.wire_groups(groups)
        c.arg(tinfo)
        c.arg(new)
        c.cap(tinfo, MI_SIZE, 'target', ignore=[MI_P3D])
        for gi, g in enumerate(groups):
            c.cap(g, G_SIZE, 'group%d' % gi, ignore=[G_MONSTERS])
        c.note(new=new, old=target['ctl'], in_list=int(in_list), groups=ng,
               members=';'.join('%d:%x/%x' % (m['g'], m['hc'], m['ctl']) for m in mons))
        edges = []
        if any(m['hc'] >= 0x80000000 for m in mons):
            edges.append('cond_negative')
        if any(m['ctl'] > 3 for m in mons):
            edges.append('control_out_of_enum')
        if new > 3:
            edges.append('new_out_of_enum')
        if edges:
            c.note(edge=','.join(edges))
        finish(c)


# ---------------------------------------------------------------- geometry
def _rand_angle(r):
    """-> (degrees, exactly on a 45-degree multiple)"""
    if r.random() < 0.4:
        base = r.choice([0, 45, 90, 135, 180, 225, 270, 315, 360, -45])
        off = r.choice([0.0, 1e-4, -1e-4, 0.01, -0.01, 0.5, -0.5])
        return base + off, off == 0.0
    return r.uniform(0.0, 360.0), False


def _quadrant(ctx):
    """int GetMonsterQuadrant(W8MonsterInfo*): bearing camera -> p3D->GetPosition() minus
    g_status.party_facing, in 90-degree quadrants"""
    fn = ctx.fn(0x004e5af0)
    cam = ctx.g('g_gd_camera').deref() + CAM_POS
    gs = ctx.g('g_status')
    for i in range(ctx.n(200)):
        r = ctx.rng('quadrant', i)
        c = ctx.case('quadrant.%d' % i, fn, conv='c', ret='i')
        w = World(ctx, c)
        cx, cy, cz = (round(r.uniform(-80000.0, 80000.0), 2), round(r.uniform(-2000.0, 8000.0), 2),
                      round(r.uniform(-80000.0, 80000.0), 2))
        x = r.random()
        boundary = False
        if x < 0.05:
            pos = (cx, cy, cz)
            ang = None
        elif x < 0.12:
            d = r.choice([500.0, -500.0, 1.0, -1.0])
            pos = (cx + d, cy, cz) if r.random() < 0.6 else (cx, cy, cz + d)
            ang = 'axis'
        else:
            ang, boundary = _rand_angle(r)
            rad = r.choice([r.uniform(100.0, 30000.0), r.uniform(1.0, 50.0), 200000.0])
            a = math.radians(ang)
            pos = (cx + rad * math.sin(a), cy + r.uniform(-500.0, 500.0), cz + rad * math.cos(a))
        facing = pick(r, [(60, lambda: r.randrange(0, 360)),
                          (20, lambda: r.choice([0, 45, 90, 180, 270, 315, 359])),
                          (20, lambda: r.choice([-1, -45, -90, -359, 360, 405, 720, -720,
                                                 0x7fffffff, -0x80000000, 100000]))])
        c.set(cam, struct.pack('<3f', cx, cy, cz))
        c.set(gs + GS_FACING, u32(facing))
        info = w.info(mon_blob(loc=r.randrange(1, 4000)))
        pb = Blob(bytes(M3_POS + 12))
        struct.pack_into('<3f', pb, M3_POS, *pos)
        w.p3d(info, pb)
        c.arg(info)
        c.note(angle=ang, facing=facing, camera=(cx, cy, cz), pos=tuple(round(v, 3) for v in pos))
        edges = []
        if boundary:
            edges.append('boundary_angle')   # bearing truncation right at a 45-degree multiple
        if not 0 <= facing < 360:
            edges.append('facing_out_of_range')
        if edges:
            c.note(edge=','.join(edges))
        finish(c)


def _dist(a, b):
    """Distance of two float32 positions (exact float differences, double math)."""
    return math.sqrt(sum((f32r(a[k]) - f32r(b[k])) ** 2 for k in range(3)))


def _find_nearest(ctx):
    """W8MonsterInfo* FindNearestMonsterInfo(const srVector3T<float>*, double maximum)"""
    fn = ctx.fn(0x004e61e0)
    pos_a = ctx.scratch(S_MISC) + M_POS
    for i in range(ctx.n(300)):
        r = ctx.rng('findnearest', i)
        c = ctx.case('findnearest.%d' % i, fn, conv='c', ret='p')
        w = World(ctx, c)
        center = (r.uniform(-50000.0, 50000.0), r.uniform(-1000.0, 5000.0),
                  r.uniform(-50000.0, 50000.0))
        nm = r.choice([0, 1, 2, 3, 4, 6, 8])
        nu = r.choice([0, 0, 1, 2, 4])
        nan_case = r.random() < 0.05
        far_case = r.random() < 0.03
        positions, edges = [], []
        for k in range(nm + nu):
            if positions and r.random() < 0.12:
                p = r.choice(positions)
                edges.append('tie')
            elif far_case and r.random() < 0.7:
                p = (center[0] + r.choice([1.2e11, -2e11]), center[1], center[2])
                edges.append('far')
            else:
                rad = r.choice([r.uniform(0.0, 3000.0), r.uniform(0.0, 30000.0), 0.0])
                a = r.uniform(0.0, 2.0 * math.pi)
                p = (center[0] + rad * math.cos(a), center[1] + r.uniform(-300.0, 300.0),
                     center[2] + rad * math.sin(a))
            if nan_case and r.random() < 0.3:
                p = (float('nan'), p[1], p[2])
                edges.append('nan_pos')
            positions.append(tuple(f32r(v) for v in p))
        infos = []
        for k in range(nm + nu):
            a = w.info(mon_blob(loc=r.randrange(1, 4000)))
            pb = Blob(bytes(M3_POS + 12))
            struct.pack_into('<3f', pb, M3_POS, *positions[k])
            w.p3d(a, pb)
            infos.append(a)
        w.wire_main(infos[:nm])
        w.wire_unborn(infos[nm:])
        finite = [_dist(center, p) for p in positions if not any(v != v for v in p)]
        x = r.random()
        if x < 0.28:
            maxd = 0.0
        elif x < 0.32:
            maxd = -0.0
            edges.append('minus_zero')
        elif x < 0.62 and finite:
            d = r.choice(finite)
            maxd = r.choice([d, f32r(d), d * (1 + 1e-12), d * (1 - 1e-12), d * (1 + 2e-7),
                             d * (1 - 2e-7), d + 1.0, d - 1.0])
            edges.append('near_max')
        elif x < 0.75:
            maxd = r.uniform(0.0, 30000.0)
        elif x < 0.8:
            maxd = r.choice([-1.0, -1e-9, -30000.0])
        elif x < 0.84:
            maxd = float('nan')
            edges.append('nan_max')
        elif x < 0.87:
            maxd = r.choice([float('inf'), float('-inf')])
        else:
            maxd = r.choice([1e12, 1e11, 9.99e10, 1e300])
        c.set(pos_a, struct.pack('<3f', *center))
        c.arg(pos_a)
        c.arg(F64(maxd))
        c.note(main=nm, unborn=nu, maximum=maxd,
               dists=','.join('%.6g' % _dist(center, p) for p in positions))
        if edges:
            c.note(edge=','.join(sorted(set(edges))))
        finish(c)


# ---------------------------------------------------------------- scale
SCALE_RANGES = [(0.9, 1.1), (0.8, 1.2), (0.75, 1.25), (0.5, 1.5), (1.0, 1.0), (0.95, 1.05),
                (0.85, 1.3), (0.6, 1.0)]


def _calc_scale(ctx):
    """float CalculateMonsterScale(W8MonsterInfo*): HP-proportional scale within the rep's
    range plus (Random(1000)*0.0004 - 0.2) of the range (seeded), clamped."""
    fn = ctx.fn(0x004e65d0)
    for i in range(ctx.n(300)):
        r = ctx.rng('calcscale', i)
        c = ctx.case('calcscale.%d' % i, fn, conv='c', ret='f')
        w = World(ctx, c)
        sp = species_pick(r)
        row = row_for(r, sp)
        edges = []
        base, count, sides = row[5]
        if r.random() < 0.15:
            base = r.choice([0, -10, 1, 37, 500, -32768, 32767])
            count = r.choice([0, 1, 2, 10, 255])
            sides = r.choice([0, 1, 2, 6, 255])
        lo = base + count
        hi = base + count * sides
        if lo == hi:
            edges.append('dice_flat')
        x = r.random()
        if x < 0.7:
            hpmax = r.randint(min(lo, hi), max(lo, hi))
        elif x < 0.8:
            hpmax = r.choice([lo, hi])
        else:
            hpmax = r.choice([lo - 1, hi + 1, 0, -1, 0x7fffffff, -0x80000000, lo - 1000, 1])
        if hpmax < lo or hpmax < 0:
            edges.append('hp_below_min')
        mn, mx = r.choice(SCALE_RANGES)
        y = r.random()
        if y < 0.06:
            mn = 0.0
            edges.append('zero_range')
        elif y < 0.12:
            mx = 0.0
            edges.append('zero_range')
        elif y < 0.17:
            mn, mx = mx, mn
            edges.append('inverted')
        elif y < 0.21:
            mn, mx = r.choice([(-1.0, 1.0), (1e-30, 1e-29), (1e5, 1e6), (-0.5, -0.1)])
        elif y < 0.24:
            if r.random() < 0.5:
                mn = float('nan')
            else:
                mx = float('nan')
            edges.append('nan_range')
        scale = r.choice([1.0, r.uniform(0.5, 2.0), 0.0, -1.0])
        w.record(sp, record_blob(row, ('id',), {MR_HP: struct.pack('<hBB', base, count, sides)}))
        b = Blob(bytes(MI_HP))
        b.u32(MI_LOC, r.randrange(1, 4000))
        b.u32(MI_SPECIES, sp)
        b.u32(MI_HPMAX, hpmax)
        info = w.info(b)
        p = w.p3d(info)
        rb = Blob(bytes(REP_MAX + 4))
        struct.pack_into('<3f', rb, REP_SCALE, scale, mn, mx)
        w.rep(p, rb)
        c.arg(info)
        c.note(species=sp, dice=(base, count, sides), hpmax=hpmax, range=(mn, mx), scale=scale)
        if edges:
            c.note(edge=','.join(sorted(set(edges))))
        finish(c)


# ---------------------------------------------------------------- combat stance
def _toggle_stance(ctx):
    """void TogglePartyCombatStance(void). g_current_screen_state.id is forced to 8 so the
    notice/redraw tail never runs."""
    fn = ctx.fn(0x004e6c10)
    gs = ctx.g('g_status')
    gx = ctx.g('gXStatus')
    st = ctx.g('g_settings')
    screen = ctx.g('g_current_screen_state')
    gcs = ctx.g('g_combat_state')
    cs = ctx.scratch(S_COMBAT)
    for i in range(ctx.n(200)):
        r = ctx.rng('togglestance', i)
        c = ctx.case('togglestance.%d' % i, fn, conv='c', ret='v')

        eb = r.randrange(6) if r.random() < 0.15 else -1

        def bb(k, p_true):
            return bool_byte(r, p_true, 1.0 if k == eb else 0.0)

        started = bb(0, 0.85)
        cont = bb(1, 0.5)
        combat = bb(2, 0.5)
        exe = bb(3, 0.5)
        rnd = bb(4, 0.5)
        ready = bb(5, 0.5)
        c.set(screen, u32(SCREEN_AUTOMAP))
        c.set(gs + GS_GAME_STARTED, u8(started))
        c.set(st + SET_CONTINUOUS, u8(cont))
        c.set(gx + GX_COMBAT_MODE, u8(combat))
        c.setp(gcs, cs)
        emit(c, cs + CS_EXEC, bytes([exe, rnd]))
        emit(c, cs + CS_READY, bytes([ready]))
        c.cap(st + SET_CONTINUOUS, 4, 'settings')
        c.cap(cs, 4, 'combat_head')
        c.cap(cs + CS_READY - 2, 4, 'combat_ready')
        c.note(started=started, continuous=cont, combat=combat, exec_=exe, round=rnd, ready=ready)
        if any(v not in (0, 1) for v in (started, cont, combat, exe, rnd, ready)):
            c.note(edge='bool_byte')
        finish(c)


# ---------------------------------------------------------------- names
def _monster_name(ctx):
    """wchar_t* GetMonsterName(W8MonsterInfo*, W8MonsterRecord*, unsigned char form)"""
    fn = ctx.fn(0x004e5150)
    gs = ctx.g('g_status')
    for i in range(ctx.n(250)):
        r = ctx.rng('monstername', i)
        c = ctx.case('monstername.%d' % i, fn, conv='c', ret='w')
        w = World(ctx, c)
        mode = pick(r, [(12, 'alt'), (25, 'nogroup'), (63, 'group')])
        sp = species_pick(r)
        row = row_for(r, sp)
        if mode == 'alt':
            row = ROW[ALT_NAME_RECORD] if r.random() < 0.6 else row
            over = {MR_ID: struct.pack('<h', ALT_NAME_RECORD)}
        else:
            over = {}
            if row[0] == ALT_NAME_RECORD:
                row = ROW[0]
        if r.random() < 0.06:
            # a full 24-character name0/name2 without terminator runs into the next array
            over[MR_NAMES] = ('ABCDEFGHIJKLMNOPQRSTUVWX').encode('utf-16-le')
            over[MR_NAMES + 0x60] = ('abcdefghijklmnopqrstuvwx').encode('utf-16-le')
        explicit = r.random() < 0.5
        blob = record_blob(row, ('names', 'id'), over)
        if explicit:
            # the info's own species record differs from the one passed in
            w.record(sp, record_blob(r.choice(MONSTERS), ('names',)))
            rec = w.loose_record(blob)
        else:
            rec = w.record(sp, blob)
        gid = 0
        groups = []
        alt = None
        if mode == 'group' or (mode == 'alt' and r.random() < 0.5):
            ng = r.choice([1, 1, 2, 3])
            gids = r.sample(range(1, 600), ng)
            gid = r.choice(gids)
            for g in gids:
                gb = Blob(bytes(G_ALTNAME + 1))
                gb.u32(G_ID, g)
                gb.u32(G_COUNT, r.randrange(1, 6))
                a = r.choice([0, 1]) if r.random() < 0.9 else r.choice(BOOL_EDGE)
                if g == gid:
                    alt = a
                gb.u8(G_ALTNAME, a)
                groups.append(w.group(gb))
            w.wire_groups(groups)
        b = mon_blob(loc=r.randrange(1, 4000), group=gid, species=sp)
        info = w.info(b)
        dying = None
        if gid == 0:
            p = w.p3d(info)
            cyc = r.choice([0, 1, 2, 0x15, 0x14])
            pend = r.choice([0xff, 0xff, 0x15, 1])
            rb = Blob(bytes(REP_PENDING + 1))
            rb.u8(REP_CYCLE, cyc)
            rb.u8(REP_PENDING, pend)
            w.rep(p, rb)
            dying = int(cyc == 0x15 or pend == 0x15)
        if mode == 'alt':
            slot = r.randrange(8)
            ctx.set_party(c, r, slots=[slot])
            c.set(gs + GS_SEDEXUS_SLOT, u32(slot))
            c.cap(gs + GS_NAME_BUFFER, 44, 'name_buffer')
        form = pick(r, [(80, lambda: r.randrange(4)), (10, lambda: r.randrange(4, 11)),
                        (6, lambda: r.randrange(11, 256)), (4, lambda: r.choice([0x100, 0x101,
                                                                                  0x1ff]))])
        c.arg(info)
        c.arg(rec if explicit else 0)
        c.arg(form)
        c.note(mode=mode, record=row[0], explicit=int(explicit), group=gid, alternate=alt,
               dying=dying, form=form)
        if alt is not None and alt not in (0, 1):
            c.note(edge='bool_byte')
        finish(c)


# ---------------------------------------------------------------- party helpers
def _corpus_level(ctx, r):
    blob, _ = ctx.pick_char(r)
    return blob.get_u32(C_LEVEL)


def _corpus_skill(ctx, r, skill):
    blob, _ = ctx.pick_char(r)
    off = C_SKILLS + skill * SKILL_STEP + SK_LEVEL
    if off + 4 > CHAR:
        return r.randrange(0, 126)
    return blob.get_u32(off)


def _avg_party_level(ctx):
    """float GetAveragePartyMemberLevel(void): occupied PC slots 2..7 only, 1.0 when none"""
    fn = ctx.fn(0x004efb60)
    level_edge = [0, 1, 0xffffffff, 0x80000000, 0x7fffffff, 1000000, 0x1000001]
    for i in range(ctx.n(200)):
        r = ctx.rng('avgpartylevel', i)
        c = ctx.case('avgpartylevel.%d' % i, fn, conv='c', ret='f')
        edge_case = r.random() < 0.1
        p = r.choice([0.3, 0.7, 1.0]) if i >= 4 else 0.0
        eb = edge_slots(r, 0.0, 0.08)[1]
        occ, lv = [], []
        for s in range(8):
            o = bool_byte(r, p, 1.0 if s == eb else 0.0)
            v = r.choice(level_edge) if edge_case and r.random() < 0.5 else \
                (_corpus_level(ctx, r) if r.random() < 0.7 else r.randrange(1, 51))
            occ.append(o)
            lv.append(v)
            c.set(xrow(ctx, s), u8(o))
            c.set(ctx.char(s) + C_LEVEL, u32(v))
        c.note(occ='.'.join('%x' % o for o in occ), levels=','.join('%x' % v for v in lv))
        edges = []
        if edge_case:
            edges.append('huge_level_fp')
        if any(o not in (0, 1) for o in occ):
            edges.append('bool_byte')
        if edges:
            c.note(edge=','.join(edges))
        finish(c)


def _best_skill(ctx):
    """unsigned int GetBestPartySkillLevel(W8Skill, int* party_slot)"""
    fn = ctx.fn(0x00554490)
    out = ctx.scratch(S_MISC) + M_SLOT
    lvl_edge = [0, 1, 50, 100, 125, 0x7fffffff, 0x80000000, 0xffffffff]
    for i in range(ctx.n(300)):
        r = ctx.rng('bestskill', i)
        c = ctx.case('bestskill.%d' % i, fn, conv='c', ret='i')
        skill = r.randrange(SKILL_COUNT) if r.random() < 0.9 else r.randrange(SKILL_COUNT, 120)
        if r.random() < 0.15:
            skill = S_MYTHOLOGY
        edges = []
        levels, desc = [], []
        tie = r.random() < 0.2
        ec, eb = edge_slots(r)
        for s in range(8):
            occ = bool_byte(r, 0.8, 1.0 if s == eb else 0.0)
            hp = hp_value(r)
            cond = char_cond(r, 1.0 if s == ec else 0.0)
            x = r.random()
            if tie and levels and x < 0.5:
                lv = r.choice(levels)
            elif x < 0.7:
                lv = _corpus_skill(ctx, r, skill)
            elif x < 0.85:
                lv = r.randrange(0, 126)
            else:
                lv = r.choice(lvl_edge)
            levels.append(lv)
            ch = ctx.char(s)
            c.set(xrow(ctx, s), u8(occ))
            c.set(ch + C_HCOND, u32(cond))
            c.set(ch + C_HP, u32(hp))
            c.set(ch + C_SKILLS + skill * SKILL_STEP + SK_LEVEL, u32(lv))
            desc.append('%x/%x/%x/%x' % (occ, hp, cond, lv))
            if occ not in (0, 1):
                edges.append('bool_byte')
            if cond >= 0x80000000:
                edges.append('cond_negative')
        c.arg(skill)
        if r.random() < 0.8:
            c.set(out, u32(0x5a5a5a5a))
            c.arg(out)
            c.cap(out, 4, 'party_slot')
            ptr = 'S7'
        else:
            c.arg(0)
            ptr = 'NULL'
        c.note(skill=skill, out=ptr, slots=';'.join(desc))
        if skill >= SKILL_COUNT:
            edges.append('skill_past_count')
        if edges:
            c.note(edge=','.join(sorted(set(edges))))
        finish(c)


def _format_health(ctx):
    """void FormatMonsterHealth(W8MonsterInfo*, wchar_t*): health knowledge from the party's
    best Mythology and the level gap to the average PC level; NPC-backed non-hostile records
    hide exact values (GetNpcStateByKind over the live NPC states)."""
    fn = ctx.fn(0x004e52c0)
    dev = ctx.g('g_dev_mode')
    text = ctx.scratch(S_MISC) + M_TEXT
    hp_edge = [0, 1, 0x7fffffff, 0x80000000, 0xffffffff, 99999]
    for i in range(ctx.n(300)):
        r = ctx.rng('formathealth', i)
        c = ctx.case('formathealth.%d' % i, fn, conv='c', ret='v')
        w = World(ctx, c)
        sp = species_pick(r)
        row = row_for(r, sp)
        flags, npck, dlevel = row[11], row[12], row[10]
        if r.random() < 0.3:
            flags = r.choice([0, 1, 0x10, 0x11, 0xff])
        if r.random() < 0.3:
            npck = r.choice(NPC_KINDS + [250, 0, r.randrange(0, 130)])
        if r.random() < 0.3:
            dlevel = r.choice([0, 1, 5, 10, 20, 30, 50, 100, 200, 255])
        w.record(sp, record_blob(row, ('id',), {MR_NPC_KIND: u8(npck), MR_FLAGS: u8(flags),
                                                MR_DLEVEL: u8(dlevel)}))
        disp = r.choice([0, 1, 1, 2]) if r.random() < 0.92 else r.choice([3, 0xff])
        summoned = r.choice([0, 0, 0, 1, 2]) if r.random() < 0.95 else r.choice([0xffffffff, 3])
        hpmax = r.randrange(1, 2000) if r.random() < 0.85 else r.choice(hp_edge)
        hp = r.randrange(0, hpmax + 1) if r.random() < 0.85 and hpmax < 0x7fffffff else \
            r.choice(hp_edge)
        b = Blob(bytes(MI_SUMMONED + 4))
        b.u32(MI_LOC, r.randrange(1, 4000))
        b.u32(MI_SPECIES, sp)
        b.u8(MI_DISP, disp)
        b.u32(MI_HPMAX, hpmax)
        b.u32(MI_HP, hp)
        b.u32(MI_SUMMONED, summoned)
        info = w.info(b)
        # party: occupancy, level (average of slots 2..7), hp/condition and Mythology
        edges = []
        p_occ = r.choice([0.5, 0.8, 1.0]) if r.random() < 0.95 else 0.0
        myth_case = r.random()
        ec, eb = edge_slots(r, 0.06, 0.05)
        for s in range(8):
            ch = ctx.char(s)
            occ = bool_byte(r, p_occ, 1.0 if s == eb else 0.0)
            lv = _corpus_level(ctx, r) if r.random() < 0.7 else r.randrange(1, 40)
            if myth_case < 0.2:
                myth = r.choice([0, 4, 5, 9, 10, 11, 125, 0xffffffff, 0x80000000])
            else:
                myth = _corpus_skill(ctx, r, S_MYTHOLOGY) if r.random() < 0.7 else r.randrange(0, 126)
            cond = char_cond(r, 1.0 if s == ec else 0.0)
            c.set(xrow(ctx, s), u8(occ))
            c.set(ch + C_LEVEL, u32(lv))
            c.set(ch + C_HCOND, u32(cond))
            c.set(ch + C_HP, u32(hp_value(r)))
            c.set(ch + C_SKILLS + S_MYTHOLOGY * SKILL_STEP + SK_LEVEL, u32(myth))
            if occ not in (0, 1):
                edges.append('bool_byte')
            if cond >= 0x80000000:
                edges.append('cond_negative')
        devmode = 1 if r.random() < 0.08 else 0
        c.set(dev, u8(devmode))
        c.set(text, b'\x41\x00' * 0x40)
        c.arg(info)
        c.arg(text)
        c.cap(text, 0x80, 'text')
        c.note(species=sp, disp=disp, summoned=summoned, flags=flags, npc_kind=npck,
               display_level=dlevel, hp=hp, hpmax=hpmax, dev=devmode)
        if edges:
            c.note(edge=','.join(sorted(set(edges))))
        finish(c)
