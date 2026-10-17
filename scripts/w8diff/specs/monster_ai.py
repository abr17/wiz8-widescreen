"""MonsterAI.cpp (decomp/src/wiz8/local_code/MonsterAI.cpp): the monster decision code.

How the cases are built (everything below is restored by the core after each case)
  * Fake monster world in scratch memory: W8MonsterInfo blocks in S0 (stride 0x430), their
    mon-to-mon visibility PLists in S0+0x8000; W8Monster stubs in S1 (stride 0x350: navigator
    position +0x118, alternate radius +0x18c, orders/patrol/move fields +0x280..+0x2c8) with
    W8MonsterRep stubs in S1+0x8000 (current_cycle +0xa4, pending_cycle +0xa7, per-cycle
    animation counts +0xb0+16*cycle) and patrol point arrays in S1+0xc000; W8MonsterRecord in
    S2 wired through gXStatus.monster_record_cache[species]; PList/IList/W8MonsterGroup stubs
    in S3 for gXStatus.plsMonsterList / plsMonsterGroupList (unborn and encounter lists are
    nulled in every case, so no lookup ever reaches a live monster); W8MonsterCombatState in
    S4 and a W8CombatState in S4+0x8000 (g_combat_state); a fake g_startup_world navigator,
    the combat-slot argument, the decision byte and a W8GrowableVector<W8CombatSlot> with a
    64-slot array (never grows) in S5.
  * Stubs that reach W8Monster::IsCycleSupported (a virtual call) get the real primary vtable
    pointer: retail 0x005ED22C, port '??_7W8Monster@@6BW8GrObject@@@' looked up in
    Wiz8Runtime.map at plan time; IsCycleSupported then reads the stub rep's animation count.
  * Camera position (g_gd_camera->m_position) is set in every case that measures a distance
    (GetDistanceToPlayer subtracts the 1000.0 world height). All coordinates are integers (or
    halves). Distances aimed at a threshold use an axis-aligned offset (one non-zero component:
    the only rounding is dz*dz, identical in both builds whatever the x87 precision and the
    summation order - retail adds z2+y2+x2, the port x2+y2+z2) or, below 4096, an integer
    Pythagorean quadruple (every square exact); so "exactly at the threshold" is meaningful.
    Free placements stay >= 12 units away from the aimed distance.
  * Party slots, where read: XChar.fOccupied plus W8Character+0xa01..0xb21 (uiCondition,
    enchantments, highest_condition, hp, stamina) cut from a corpus character and edited -
    whole for the spell-target checks, only uiCondition[13] and highest_condition..hp where
    just participation/Turncoat matter; SILENCE also writes skills[MUSIC/SPELLBOOK_ALCHEMY]
    .level and spell_learned[0..0x71]. No setb is used (adds no blobs to the plan header).
    Where a function only reaches the party through MonsterAttackReachesCharacter with the
    monster's party sight not SEEN, the live party is left alone (the result cannot depend
    on it; all dispositions are 0..2 so MonsterVsCharDisposition never asserts).
  * Scalars set explicitly where read: gXStatus.fCombatMode / hostile_monster_count,
    g_camera_sway_active, g_spell_cycle_error_reported, g_special_attack_cycle_error_reported
    (both also captured), g_mipe_active = 1 (IsMipeActive makes DispatchWorldCursorNodeCommand
    return before it settles a point to the level geometry / walks world cursor nodes).
  * Databases: SpellTables.dbs target type / realm / monster_castable / range and MONSTERS.DBS
    rows (tables below; same values as specs magic_a.py / combat_range.py); spell ids 0..149.
  * Every case stays within the core's 96 set-up ops (World.write merges the closest non-zero
    runs when needed; finish() raises otherwise); the plan is ~11 MB per process.
  * Random() is seeded per case by the core; every path that rolls is deterministic.

Tested (retail address, function, cases at --scale 1):
  0x00535150 IsMonsterActionUsable            300
  0x005327e0 MonsterSpellTargetOK             460  every switch arm, character and monster slots
  0x00532550 IsSpellUsableByMonster           300
  0x00534290 CanMonsterAimSpell               250  CONE/RADIUS (empty), needs_aim from camera
                                                   or a listed target monster
  0x00534cb0 AimFleeingMonster                150  summon rows and the (empty) special cone
  0x00534a40 CanMonsterFlee                   300  every early exit, unsigned stamina/10,
                                                   summon distance at 12500, error latch
  0x00534850 MonsterHasVisibleTarget          400  hostility 0..4, party + mon-to-mon scans,
                                                   reach exactly at/around its value
  0x005347a0 MonsterGroupHasVisibleTarget     250
  0x00534690 MonsterHasNoVisibleEnemy         250
  0x005324b0 GetGroupNearestDistance          200  incl. empty group, NaN/1e30 positions
  0x00534fc0 MonsterGroupHasReinforcement     300  hostile count 0/0xffffffff, 25000, 1.15 slack
  0x00535200 UpdateMonsterGroupEngagement     250  update count <= 2, settle_ticks unsigned,
                                                   ticks 254/255, special monster ids
  0x00531540 UpdateMonsterAI                  400  covers inlined MonsterAdvanceChance (NPC 33%,
                                                   hp*100 overflow, advancing vs 2000) and
                                                   ChooseMonsterSpell; 0.95 hp ratio edges;
                                                   ally/enemy spells, summon flee, rating 0/1/3
  0x005314f0 UpdateAllMonsterAI               150
  0x005308c0 ChooseMonsterRTAIMode            350  5000/1500 distances, yaw epsilon, latched
                                                   modes, patrol index wrap, empty patrol list
  0x00533320 CollectMonsterSpellTargets       300  covers inlined PartyHalfSpellTargetsValid
                                                   and MonsterGroupHalfSpellTargetsValid
  0x005326f0 AimMonsterAtSpellTarget          200
  0x005323f0 ChooseRandomMonsterAction        250  covers BuildMonsterActionQueue (bodyguard
                                                   sweep, wait, stealth rolls, locked target/
                                                   attack, DEX 0x4b) and inlined QueueMonsterAction
  0x00531920 MonsterGroupCanEngage            200  45% built to engage (seer within reach +
                                                   a member's attack reaching a hostile outsider)
  total 5260

Paths deliberately kept out of reach (live world state, object creation or crashes in both):
  * PopulateSpellTargetMarkers (via MonsterSpellTargetOK on non character/monster slots and
    MonsterSpellHasPartyTarget): area geometry against the live level. Slots are always
    character/monster ones; PARTY/ALL_ENEMIES/ITEM/LOCK spells are never collected; CONE/RADIUS
    collections (incl. the special-attack cone of CanMonsterFlee) are kept empty (no listed
    hostile monster reachable through a mon-to-mon row, caster spell-sight flag 0).
  * MonsterAttackReachesCharacter past its sight check (CloseFormationGap reads the formation
    and combat rows): callers that reach it run with player_visibility.sight_state != SEEN.
  * The heard-noise octree probe in ChooseMonsterRTAIMode (g_octree->TestNoiseLineOfSight):
    a positive noise radius only comes with ai_mode 4 and "stopped within 1500" or "walking".
  * The waypoint probe in MonsterGroupCanEngage (TestWaypointSpan): close-range members have
    a zero combat move range.
  * ENEMY_GROUP spells inside UpdateMonsterAI (PartyHalfSpellTargetsValid would read the live
    party) - tested in CollectMonsterSpellTargets with a set party instead.
  * Every monster that a function asks for its record has one wired (no record is loaded
    from MONSTERS.DBS into the live cache during a case).

Skipped:
  0x00530110 UpdateMonsterSight            - refreshes outward sight for every live monster
                                             (octree LOS) and starts combat (CheckMonsterGroupsEnterCombat)
  0x00530150 UpdateMonsterGroups           - per-frame world pass: loads/detaches groups, enters
                                             combat, runs DoMonsterRTAI on live monsters
  0x00530470 GetMonsterGroupPartySightState - not in Wiz8Runtime.map (inlined into DoMonsterRTAI)
  0x00530560 DoMonsterRTAI                 - commits movement through ApplyMonsterRTAIDecision
                                             (navigator path planning, group combat entry)
  0x00530f10 ApplyMonsterRTAIDecision      - navigator movement/patrol/aim commands, octree
                                             path planning, MoveMonsterGroupToPosition
  0x00532330 DestroyMonsterActionQueue     - frees the heap action list (PLDestroy)
  0x00531c00 MonsterAdvanceChance          - not in the port map (inlined); tested through
                                             UpdateMonsterAI
  0x00531ce0 BuildMonsterActionQueue       - fills a heap PList the harness cannot read back;
                                             tested through ChooseRandomMonsterAction
  0x00532360 QueueMonsterAction            - not in the port map (inlined); tested through
                                             ChooseRandomMonsterAction
  0x005330e0 SpellAreaHitsNeutralMonster   - every aimable spell runs PopulateSpellTargetMarkers
                                             (area geometry); the rest is a constant false
  0x00533260 ChooseMonsterSpell            - not in the port map (inlined); tested through
                                             UpdateMonsterAI (weights over usable ally/enemy
                                             spells, spell 60, blocked fillers)
  0x00534300 CheckMonsterGroupsLeaveCombat - refreshes live sight and ends combat for world groups
  0x00534d50 IsMonsterControlPointInRange  - moves/aims the monster at the lure visual
                                             (navigator commands); otherwise a constant 0
  0x00534dd0 MonsterGroupHalfSpellTargetsValid - not in the port map (inlined); tested through
                                             CollectMonsterSpellTargets (enemy-group spells)
  0x00534ef0 PartyHalfSpellTargetsValid    - not in the port map (inlined); same
  0x005353e0 MonsterSpellHasPartyTarget    - not in the port map; PopulateSpellTargetMarkers
  0x005354e0 CheckMonsterGroupsEnterCombat - RefreshAllSight + MonsterGroupEnterCombat on world groups
  0x005355d0 ShouldMonsterGroupEnterCombat - not in the port map (inlined into
                                             CheckMonsterGroupsEnterCombat)
"""
import math
import struct

from w8diff.api import Blob

MAX_OPS = 96          # W8D_MAX_OPS in w8diff_core.c (extra ops are silently dropped)

# ---------------------------------------------------------------- layouts (layout.ps1 / retail asm)
CHAR = 0x1862
C_BLOCK = 0xa01                 # uiCondition[20] .. stamina: one block per character
C_BLOCK_END = 0xb21
C_COND = 0xa01
C_ENCH = 0xa65                  # W8Enchantment[8], turns +8, stride 0xc
C_HIGHEST = 0xb01
C_HPMAX = 0xb0d
C_HP = 0xb11
C_STMAX = 0xb19
C_ST = 0xb1d
C_MUSIC = 0x36b                 # skills[W8_SKILL_MUSIC].level
C_ALCH = 0x57f                  # skills[W8_SKILL_SPELLBOOK_ALCHEMY].level
C_LEARNED = 0xbcd               # int spell_learned[136]; 0x72 read
XROW = 0x106                    # W8PartySlotRow, fOccupied +0

GS_EFFECTS = 0x17af             # g_status.effect_slots[12]
X_COMBAT = 0x8dc                # gXStatus.fCombatMode
X_HOSTILE = 0x8ed               # hostile_monster_count
X_MONLIST = 0x8f5               # plsMonsterList, plsMonsterGroupList (+4)
X_UNBORN = 0x901                # plsUnbornMonsterList, plsMonsterGroupEncounterList (+4)
X_RECCACHE = 0xa0f

CS_ROUND = 0x4
CS_EFF = 0x7c1                  # W8EffectSlot[9]
CS_EFF0 = 0x85a                 # W8EffectSlot[6]
CS_UPDATE = 0xa5c               # combat_update_count
ES = 0x11                       # W8EffectSlot stride, duration +0xd
ES_DUR = 0xd

MI_LOC, MI_GROUP, MI_SPECIES, MI_P3D, MI_PCOMBAT = 0x0, 0x4, 0x8, 0xc, 0x10
MI_ACTIVE, MI_INCOMBAT, MI_DISP = 0x14, 0x15, 0x16
MI_HPMAX, MI_HP, MI_STMAX, MI_ST = 0x27, 0x2b, 0x2f, 0x33
MI_NOISE_POS, MI_NOISE_RADIUS = 0x37, 0x43
MI_COND, MI_ENCH, MI_HIGHEST, MI_EFFECT = 0x57, 0xa7, 0x107, 0x10f
MI_OOF = 0x220                  # modifiers.out_of_formation
MI_PATHCD, MI_ATTR, MI_MOTIONLESS, MI_AIMODE = 0x246, 0x247, 0x24e, 0x255
MI_PT_SIGHT, MI_PT_LOS = 0x28a, 0x28b
MI_VISLIST, MI_TARGET, MI_SUMMONED = 0x2b6, 0x2ba, 0x2da
MI_ACTION, MI_DETAIL, MI_NOISE_MARGIN = 0x2e1, 0x2e5, 0x2f5
MI_PAUSE, MI_ELEMENTAL = 0x303, 0x344
MI_PV_SIGHT, MI_PV_LOS, MI_PV_CANSEE, MI_PV_LINE = 0x34c, 0x34d, 0x353, 0x370
MI_HASPROJ, MI_HASSPELL = 0x37a, 0x37c
MI_SIZE = 0x425
MI_BLOB = 0x37d
MI_FLOATS = [0x37, 0x3b, 0x3f, MI_TARGET + 0x10, MI_TARGET + 0x14, MI_TARGET + 0x18]
MI_PTRS = [MI_P3D, MI_PCOMBAT, MI_VISLIST]

VR_SIGHT, VR_LOS, VR_CANSEE, VR_LINE = 0x4, 0x5, 0xb, 0x28
VR_STRIDE = 0x34                # record is 0x31 bytes

MC_PHASE, MC_ACTIVE, MC_APR0, MC_APR, MC_ATTACK = 0x0, 0x4, 0x5, 0x9, 0x11
MC_BERSERK, MC_LIST, MC_EFF, MC_EFF2 = 0x15, 0x16, 0x3e, 0xd7
MC_COOLDOWN, MC_ADVANCING, MC_SETTLE, MC_RECONSIDER = 0x146, 0x14b, 0x14c, 0x152
MC_SIZE = 0x153

M3_STOPPED, M3_YAW, M3_TYAW = 0x3c, 0xec, 0xf0
M3_POS, M3_RADIUS, M3_HEIGHT = 0x118, 0x18c, 0x190
M3_REP = 0x1d8
M3_FORMATION, M3_ORDERS, M3_ORDER_MODE, M3_DEAF, M3_FACE = 0x280, 0x28d, 0x28e, 0x28f, 0x290
M3_PDIST, M3_PVAR = 0x294, 0x298
M3_VEC = 0x29c                  # W8GrowableVector<srVector3T<float>>: count +4, cap +8, data +0xc
M3_PINDEX, M3_DIR, M3_MOVEDIR = 0x2ac, 0x2b0, 0x2bc
M3_SIZE = 0x348
M3_BLOB = 0x2c8
M3_FLOATS = [M3_FORMATION, M3_FORMATION + 4, M3_FORMATION + 8,
             M3_MOVEDIR, M3_MOVEDIR + 4, M3_MOVEDIR + 8]

REP_CUR, REP_PEND, REP_ANIM = 0xa4, 0xa7, 0xb0
REP_BLOB = 0x260
CYC_SPECIAL = 0x12              # CanMonsterFlee
CYC_SPELL = 0x19
CYC_DIE = 0x15

MR_KIND, MR_FLAGS, MR_ATTR = 0xcb, 0xd0, 0xd1
MR_SC, MR_FC, MR_ADV, MR_SAK, MR_APR, MR_SPR = 0xe0, 0xe1, 0xe2, 0xe3, 0xe5, 0xe6
MR_ATK = 0xe7                   # W8MonsterAttack[3] stride 0x22: fHasAttack +0, range +3, modes +0x15
MR_SPELLS = 0x14d
MR_PREFER, MR_MOVE, MR_BEHAV, MR_MORALE = 0x1b9, 0x1ba, 0x1bf, 0x1c0
MR_CAMO1, MR_UNTARGET, MR_LEVEL = 0x249, 0x24a, 0x24f
MR_HRADIUS, MR_FACTION = 0x25b, 0x25f
MR_SIZE = 0x297

G_ID, G_COUNT, G_MONSTERS, G_MONID = 0x0, 0x4, 0x8, 0x18
G_ACTIVE, G_INCOMBAT, G_DISP = 0x28, 0x29, 0x2a
G_LEADER, G_LEADER_GROUP, G_ALLIES = 0x9f, 0xa3, 0xa7
G_ENGAGE, G_TICKS = 0xc8, 0xc9
G_SIZE = 0x12b
G_BLOB = 0xcc
G_IL = 0x30                     # member IList kept inside group_state[0x6e] (+0x2d..+0x9b)
G_IL_DATA = 0x3c
G_IL_MAX = 23

CAM_POS = 0x8c                  # GDCamera::m_position
NAV_POS = 0x100                 # W8Navigator movement.position
NAV_COLL = 0x170                # movement.collision_radius, alternate_radius (+4)

# scratch layout
MI_STRIDE = 0x430
VIS_BASE = 0x8000
VIS_STRIDE = 0x400
P3D_STRIDE = 0x350
REP_BASE = 0x8000
REP_STRIDE = 0x260
PTS_BASE = 0xc000
PTS_STRIDE = 0x100
REC_STRIDE = 0x2a0
L_MON = 0x0                     # S3: monster PList header, data at +0x10
L_GRP = 0x100                   # S3: group PList header, data at +0x10
L_GROUPS = 0x400
GROUP_STRIDE = 0x130
MCS_STRIDE = 0x160
CS_BASE = 0x8000                # S4: W8CombatState
NAV = 0x0                       # S5
SLOT = 0x400
DECISION = 0x480
VEC = 0x500
VEC_DATA = 0x600
VEC_CAP = 64

RETAIL_MONSTER_VTABLE = 0x005ED22C
PORT_MONSTER_VTABLE = '??_7W8Monster@@6BW8GrObject@@@'

WORLD_HEIGHT = 1000.0
RANGE_DIST = {-1: 0.0, 0: 1000.0, 1: 2000.0, 2: 12500.0, 3: 25000.0}
ENGAGE_RANGE = 25000.0
ENGAGE_FLOOR = 7500.0
NEUTRAL_SPECIES = 0x224
N_MONSTERS = 595

# ---------------------------------------------------------------- databases
# SpellTables.dbs (GOG 1.2.4), indexes 0..149: target type, realm, monster_castable, range category
SPELL_TT = [0, 3, 2, 3, 3, 3, 1, 5, 2, 3, 3, 3, 4, 1, 4, 6, 1, 2, 10, 1, 2, 1, 6, 9, 4, 5, 2, 1, 5, 4,
            6, 5, 2, 2, 1, 1, 6, 4, 8, 10, 2, 3, 6, 5, 2, 2, 4, 5, 6, 5, 3, 1, 5, 2, 1, 6, 2, 6, 1, 2,
            8, 1, 2, 5, 2, 1, 3, 7, 2, 6, 3, 4, 2, 0, 1, 0, 6, 7, 5, 3, 6, 6, 3, 5, 3, 7, 5, 6, 1, 3,
            7, 3, 3, 6, 7, 7, 7, 7, 7, 7, 1, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 7, 6, 5,
            1, 4, 4, 8, 4, 4, 4, 4, 4, 7, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
SPELL_REALM = [0, 1, 5, 4, 1, 0, 5, 3, 0, 5, 4, 1, 2, 1, 4, 0, 1, 4, 4, 1, 5, 5, 1, 4, 4, 5, 2, 3, 2, 1,
               2, 3, 3, 3, 1, 2, 0, 1, 0, 3, 5, 4, 2, 0, 1, 2, 2, 3, 1, 3, 3, 1, 4, 3, 5, 0, 0, 1, 5, 5,
               5, 1, 0, 2, 4, 3, 1, 1, 5, 4, 5, 4, 2, 2, 4, 2, 2, 5, 1, 0, 5, 0, 5, 0, 5, 2, 0, 3, 5, 4,
               2, 4, 4, 2, 5, 3, 3, 4, 0, 0, 5, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 5, 2, 4, 0, 1,
               5, 3, 1, 2, 3, 1, 2, 5, 4, 5, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
SPELL_CAST = [0, 1, 1, 0, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1,
              0, 1, 1, 0, 1, 1, 1, 1, 0, 0, 1, 0, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 0, 1,
              1, 1, 0, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 0, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 1,
              1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1,
              0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
SPELL_RANGE = [0, 2, 0, 2, 2, 2, 2, 2, 0, 2, 2, 2, 2, 2, 3, 3, 2, 0, 0, 1, 0, 1, 2, 0, 3, 2, 0, 1, 2, 3,
               3, 2, 0, 0, 2, 2, 3, 3, 3, 0, 0, 2, 3, 2, 0, 0, 3, 2, 3, 2, 3, 2, 2, 0, 1, 3, 0, 3, 1, 0,
               1, 1, -1, 2, 0, 1, 3, 3, 0, 3, 3, 3, 0, 0, 2, 0, 3, 3, 2, 3, 3, 3, 2, 2, 2, 3, 2, 3, 1, 2,
               3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 2, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 2, 3, -1, 2,
               1, 2, 2, 3, 1, 0, 1, 1, 1, 2, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
SPELLS = list(range(150))
AIMABLE = [s for s in SPELLS if 3 <= SPELL_TT[s] <= 7 and s not in (3, 41)]
NON_AIMABLE = [s for s in SPELLS if s not in AIMABLE]
NON_CASTABLE = [s for s in SPELLS if not SPELL_CAST[s]]
FIRE_CASTABLE = [s for s in SPELLS if SPELL_CAST[s] and SPELL_REALM[s] == 0]
CASTER_SPELLS = [s for s in SPELLS if SPELL_TT[s] == 0]
ALLY_SPELLS = [s for s in SPELLS if SPELL_TT[s] == 1]
ENEMY_SPELLS = [s for s in SPELLS if SPELL_TT[s] == 3]
GROUP_SPELLS = [s for s in SPELLS if SPELL_TT[s] == 4]
AREA_SPELLS = [s for s in SPELLS if SPELL_TT[s] in (5, 6)]
POINT_SPELLS = [s for s in SPELLS if SPELL_TT[s] == 8]
SUMMON_ELEMENTAL = 60
SPECIAL_CONE = 0x77

# g_special_attack_table[k][0] == 6 marks a summoning special attack
SUMMON_KINDS = [24, 25, 26, 27, 28, 29, 31]
NONSUMMON_KINDS = [k for k in range(1, 32) if k not in SUMMON_KINDS]
CAST_BLOCK_KINDS = [5, 6, 7, 0x19, 0x1a, 0x1c, 0x1d]

# MONSTERS.DBS rows (record, attacks 'has,range' x3, spell_chance, flee_chance, special_attack_kind,
#                    prefer_ranged_actions, untargetable, faction_id, spells[10])
MON_ROWS = [
    (0, '101000', 0, 0, 0, 0, 0, 9, [24, 43, 59, 46, 14, 52, 29, 28, 11, 11]),
    (1, '100000', 0, 80, 15, 0, 0, 0, [0] * 10),
    (2, '101000', 30, 0, 0, 1, 0, 4, [59] * 10),
    (5, '100003', 85, 0, 0, 1, 0, 0, [69, 68, 53, 28, 66, 49, 47, 89, 98, 98]),
    (6, '100000', 0, 99, 25, 0, 0, 0, [0] * 10),
    (7, '100000', 0, 80, 31, 1, 0, 10, [0] * 10),
    (10, '110003', 70, 0, 0, 0, 0, 6, [29, 6, 12, 28, 10, 14, 24, 12, 10, 10]),
    (12, '100303', 0, 0, 0, 0, 0, 10, [0] * 10),
    (13, '100003', 0, 0, 0, 0, 1, 0, [6, 21, 32, 11, 11, 11, 11, 31, 31, 31]),
    (14, '100000', 0, 50, 7, 0, 0, 0, [0] * 10),
    (17, '100000', 80, 0, 5, 1, 0, 0, [5, 5, 46, 15, 24, 10, 10, 11, 37, 37]),
    (50, '110003', 90, 0, 0, 1, 0, 15, [20, 40, 69, 31, 66, 28, 50, 67, 36, 36]),
    (53, '111003', 80, 0, 0, 0, 0, 5, [1, 53, 27, 15, 50, 1, 79, 42, 7, 7]),
    (57, '111013', 0, 0, 0, 1, 0, 5, [24, 71, 37, 37, 43, 43, 43, 10, 10, 10]),
    (68, '000003', 80, 20, 6, 1, 0, 0, [54, 32, 46, 43, 5, 36, 36, 24, 14, 14]),
    (76, '100000', 95, 0, 0, 1, 0, 0, [80, 29, 27, 11, 76, 1, 57, 42, 48, 48]),
    (96, '100200', 0, 70, 18, 0, 0, 0, [0] * 10),
    (104, '110103', 85, 0, 0, 1, 0, 1, [77, 68, 2, 46, 63, 70, 31, 83, 9, 9]),
    (110, '110012', 50, 0, 0, 1, 0, 0, [49, 6, 46, 15, 50, 14, 4, 28, 5, 5]),
    (116, '110012', 50, 50, 17, 1, 0, 0, [54, 14, 24, 10, 85, 52, 89, 71, 86, 86]),
    (118, '110013', 20, 30, 12, 1, 0, 0, [24, 99, 72, 81, 89, 54, 80, 94, 97, 97]),
    (136, '100012', 0, 90, 20, 1, 0, 0, [1] * 10),
    (165, '101200', 0, 50, 14, 1, 0, 0, [0] * 10),
    (180, '100300', 70, 20, 9, 1, 0, 0, [49, 56, 77, 87, 71, 52, 36, 81, 79, 79]),
    (194, '101313', 50, 40, 28, 1, 1, 0, [99, 86, 54, 81, 95, 85, 92, 98, 97, 97]),
    (205, '110103', 85, 0, 29, 1, 0, 1, [15, 1, 1, 6, 32, 6, 11, 28, 9, 9]),
    (211, '110000', 80, 10, 26, 1, 0, 1, [89, 76, 98, 81, 54, 50, 46, 36, 25, 25]),
    (212, '100000', 8, 90, 26, 1, 1, 1, [20, 20, 31, 31, 31, 31, 31, 25, 25, 25]),
    (217, '100003', 40, 50, 27, 1, 0, 1, [69, 68, 53, 98, 89, 15, 79, 81, 36, 36]),
    (249, '100003', 80, 0, 29, 1, 0, 13, [15, 53, 6, 42, 50, 48, 12, 7, 1, 1]),
    (255, '101212', 0, 60, 2, 1, 0, 0, [0] * 10),
    (263, '011103', 40, 0, 0, 1, 0, 6, [2, 15, 9, 90, 29, 90, 37, 4, 13, 4]),
    (305, '111103', 0, 60, 19, 0, 0, 0, [0] * 10),
    (325, '110103', 0, 90, 9, 1, 0, 0, [0] * 10),
    (373, '110003', 0, 40, 24, 0, 1, 0, [13, 14, 2, 6, 18, 12, 7, 10, 129, 18]),
    (378, '111003', 80, 0, 6, 0, 0, 5, [89, 86, 56, 54, 43, 71, 28, 46, 29, 29]),
    (394, '100303', 20, 20, 25, 1, 0, 0, [57, 15, 4, 37, 28, 32, 86, 86, 48, 48]),
    (409, '111103', 50, 70, 8, 1, 0, 0, [65, 49, 53, 69, 78, 92, 80, 48, 95, 95]),
    (442, '101010', 0, 0, 26, 0, 0, 15, [0] * 10),
    (465, '101202', 0, 60, 13, 0, 0, 0, [0] * 10),
    (500, '100003', 0, 50, 4, 0, 0, 0, [0] * 10),
    (546, '110003', 0, 90, 24, 0, 0, 0, [13, 14, 2, 6, 18, 12, 7, 10, 129, 18]),
    (564, '101313', 70, 75, 28, 1, 0, 0, [99, 68, 54, 81, 95, 85, 92, 98, 97, 97]),
]

# Pythagorean quadruples (a, b, c, d): a^2 + b^2 + c^2 = d^2
QUADS = [(0, 0, 1, 1), (0, 3, 4, 5), (1, 2, 2, 3), (2, 3, 6, 7), (1, 4, 8, 9), (4, 4, 7, 9),
         (2, 6, 9, 11), (6, 6, 7, 11), (3, 4, 12, 13), (2, 5, 14, 15), (2, 10, 11, 15),
         (1, 12, 12, 17), (8, 9, 12, 17), (1, 6, 18, 19), (6, 6, 17, 19), (6, 10, 15, 19),
         (4, 5, 20, 21), (4, 8, 19, 21), (4, 13, 16, 21), (8, 11, 16, 21), (0, 5, 12, 13),
         (0, 8, 15, 17), (0, 7, 24, 25)]


# ---------------------------------------------------------------- small helpers
def p8(v):
    return struct.pack('<B', int(v) & 0xff)


def p32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def pf(v):
    return struct.pack('<f', float(v))


def f32r(x):
    return struct.unpack('<f', struct.pack('<f', float(x)))[0]


def rb(r, p=0.5):
    return 1 if r.random() < p else 0


def pick(r, weighted):
    total = sum(w for w, _ in weighted)
    x = r.random() * total
    for w, v in weighted:
        x -= w
        if x < 0:
            return v() if callable(v) else v
    v = weighted[-1][1]
    return v() if callable(v) else v


def nz_runs(data, gap=12):
    """[start, end) runs of non-zero bytes, merging gaps up to `gap` zero bytes (a separate
    'set' line costs about as much plan text as a dozen zero bytes)."""
    runs = []
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
        runs.append([start, last + 1])
        i = last + 1
    return runs


def emit(c, addr, data, gap=12):
    """Write only the non-zero runs of data (scratch is zeroed for every case)."""
    data = bytes(data)
    for s, e in nz_runs(data, gap):
        c.set(addr + s, data[s:e])


OP_BUDGET = MAX_OPS - 1


def finish(c):
    if len(c.ops) > MAX_OPS:
        raise ValueError('%s: %d set-up ops > %d' % (c.id, len(c.ops), MAX_OPS))


def cond_val(r, p_zero=0.5):
    if r.random() < p_zero:
        return 0
    return r.choice([1, 2, 5, 30, 9999, 0x7fffffff, 0x80000000, 0xffffffff, r.randrange(1, 200)])


def turns_val(r, p_zero=0.5):
    if r.random() < p_zero:
        return 0
    return r.choice([1, 3, 10, 9999, 0x80000000, 0xffffffff, r.randrange(1, 100)])


# ---------------------------------------------------------------- geometry
def rand_cam(r):
    return (float(r.randrange(-60000, 60001)), float(r.randrange(-1500, 6001)),
            float(r.randrange(-60000, 60001)))


def player_ref(cam):
    """The point W8Monster::GetDistanceToPlayer measures from (camera minus world height)."""
    return (cam[0], cam[1] - WORLD_HEIGHT, cam[2])


def offset(r, length, exact=True):
    """A vector of the given length.
    exact: axis-aligned (one non-zero component: dx*dx is the only rounding, the same in both
    builds whatever the x87 precision and summation order), or for integer lengths < 4096 an
    integer Pythagorean quadruple (every square and sum exact even at 24-bit precision).
    Otherwise a free direction with integer components (callers keep a wide margin)."""
    if length <= 0:
        return (0.0, 0.0, 0.0)
    if exact:
        li = int(length)
        v = [0, 0, length]
        if li == length and 0 < li < 4096 and r.random() < 0.6:
            cands = [q for q in QUADS if li % q[3] == 0]
            q = r.choice(cands)
            k = li // q[3]
            v = [q[0] * k, q[1] * k, q[2] * k]
        r.shuffle(v)
        return tuple(float(x * r.choice([1, -1])) for x in v)
    a = r.uniform(0.0, 2.0 * math.pi)
    e = r.uniform(-0.3, 0.3)
    return (float(round(length * math.cos(a) * math.cos(e))), float(round(length * math.sin(e))),
            float(round(length * math.sin(a) * math.cos(e))))


def add3(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def near(r, thresholds, spread=40000.0):
    """A distance value: around one of the thresholds (exact steps) or anywhere."""
    k = r.random()
    if k < 0.55 and thresholds:
        t = r.choice(thresholds)
        return t + r.choice([-3.0, -1.0, -0.5, 0.0, 0.0, 0.5, 1.0, 3.0, -250.0, 250.0])
    if k < 0.65:
        return 0.0
    return float(r.randrange(0, int(spread)))


def place_from(r, ref, dist, mr, sr, exact=None):
    """Position whose distance to ref minus both radii is dist (ref and radii integers, so
    every coordinate difference is exact). Free placements are moved at least ~10 units
    away from the requested distance (they only probe "clearly inside/outside")."""
    if exact is None:
        exact = r.random() < 0.8
    if dist <= 0:
        exact = True
        total = float(int(r.uniform(0.0, mr + sr))) if mr + sr > 0 else 0.0
    else:
        total = dist + mr + sr
    if not exact and total > 40:
        total = total + r.choice([-31.0, -12.0, 12.0, 31.0])
    return add3(ref, offset(r, total, exact))


def rand_radius(r):
    return float(r.choice([0, 0, 150, 300, 500, 750, r.randrange(1, 1500)]))


# ---------------------------------------------------------------- records
def new_rec(**kw):
    d = {'kind': 0, 'flags': 0, 'attrs': (40, 40, 40, 40, 40), 'sc': 0, 'fc': 0, 'adv': 0, 'sak': 0,
         'apr': 1, 'spr': 1, 'attacks': [(1, 0, 1), (0, 0, 0), (0, 0, 0)], 'spells': [0] * 10,
         'prefer': 0, 'move': 0.0, 'behavior': 0, 'morale': 1, 'camo1': 0, 'untarget': 0,
         'level': 5, 'hradius': 0, 'faction': 0}
    d.update(kw)
    return d


def rec_from_row(r, row):
    _, atk, sc, fc, sak, pra, unt, fac, spells = row
    attacks = []
    for a in range(3):
        has = int(atk[2 * a])
        rng = int(atk[2 * a + 1])
        modes = r.choice([1, 2, 3, 0x11, 0x105, 0x1ff]) if has else 0
        attacks.append((has, rng, modes))
    return new_rec(kind=r.choice([0, 1, 2, 3, 4, 5, 6, 0xc, 0xd, 0x14, 0x15, 0x1c]),
                   flags=r.choice([0, 0, 0, 1, 4, 5]),
                   attrs=tuple(r.randrange(1, 126) for _ in range(5)),
                   sc=sc, fc=fc, adv=r.choice([0, 0, 0, 10, 50, 100]), sak=sak,
                   apr=r.choice([1, 1, 2, 3]), spr=r.choice([1, 1, 2]), attacks=attacks,
                   spells=list(spells), prefer=pra,
                   move=r.choice([0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 12.5]),
                   behavior=r.choice([0, 1, 2, 3]), morale=r.choice([0, 1, 2, 3]),
                   camo1=r.choice([0, 0, 0, 10, 50]), untarget=unt,
                   level=r.randrange(1, 40), hradius=r.choice([0, 0, -1, 5, 20]), faction=fac)


def rand_rec(r):
    return rec_from_row(r, r.choice(MON_ROWS))


def rec_blob(d):
    b = Blob(MR_SIZE)
    b.u8(MR_KIND, d['kind'])
    b.u8(MR_FLAGS, d['flags'])
    for i, v in enumerate(d['attrs']):
        b.u8(MR_ATTR + i, v)
    b.u8(MR_SC, d['sc'])
    b.u8(MR_FC, d['fc'])
    b.u8(MR_ADV, d['adv'])
    b.u8(MR_SAK, d['sak'])
    b.u8(MR_APR, d['apr'])
    b.u8(MR_SPR, d['spr'])
    for a, (has, rng, modes) in enumerate(d['attacks']):
        o = MR_ATK + a * 0x22
        b.u8(o, has)
        b.u8(o + 3, rng)
        b.u16(o + 0x15, modes)
    for i, s in enumerate(d['spells']):
        b.u8(MR_SPELLS + i, s)
    b.u8(MR_PREFER, d['prefer'])
    b.f32(MR_MOVE, d['move'])
    b.u8(MR_BEHAV, d['behavior'])
    b.u8(MR_MORALE, d['morale'])
    b.u8(MR_CAMO1, d['camo1'])
    b.u8(MR_UNTARGET, d['untarget'])
    b.u8(MR_LEVEL, d['level'])
    b.u32(MR_HRADIUS, d['hradius'])
    b.u32(MR_FACTION, d['faction'])
    return b


# ---------------------------------------------------------------- monsters
def new_mon(loc, species, group=1, **kw):
    m = {'loc': loc, 'group': group, 'species': species, 'active': 1, 'incombat': 1, 'disp': 1,
         'hpmax': 100, 'hp': 100, 'stmax': 60, 'st': 60, 'noise_pos': (0.0, 0.0, 0.0),
         'noise_radius': 0, 'cond': {}, 'ench': {}, 'highest': 0, 'effects': {}, 'pathcd': 0,
         'attrs': (50, 50, 50, 50, 50), 'motionless': 0, 'oof': 0, 'ai_mode': 0, 'pt_sight': 0,
         'pt_los': (0, 0), 'target': (0, -1, -1, -1, (0.0, 0.0, 0.0)), 'summoned': 0,
         'action': -1, 'detail': 0, 'noise_margin': 0, 'pause': 0, 'elemental': -1,
         'pv_sight': 0, 'pv_los': (0, 0, 0, 0), 'pv_cansee': 0, 'pv_line': 0, 'has_proj': 0,
         'has_spell': 0, 'p3d': None, 'pcombat': None, 'vis': None}
    m.update(kw)
    return m


def mon_blob(m):
    b = Blob(MI_BLOB)
    b.u32(MI_LOC, m['loc'])
    b.u32(MI_GROUP, m['group'])
    b.u32(MI_SPECIES, m['species'])
    b.u8(MI_ACTIVE, m['active'])
    b.u8(MI_INCOMBAT, m['incombat'])
    b.u8(MI_DISP, m['disp'])
    b.u32(MI_HPMAX, m['hpmax'])
    b.u32(MI_HP, m['hp'])
    b.u32(MI_STMAX, m['stmax'])
    b.u32(MI_ST, m['st'])
    for i, v in enumerate(m['noise_pos']):
        b.f32(MI_NOISE_POS + 4 * i, v)
    b.u32(MI_NOISE_RADIUS, m['noise_radius'])
    for i, v in m['cond'].items():
        b.u32(MI_COND + 4 * i, v)
    for i, v in m['ench'].items():
        b.u32(MI_ENCH + 12 * i + 8, v)
    b.u32(MI_HIGHEST, m['highest'])
    for i, v in m['effects'].items():
        b.u32(MI_EFFECT + ES * i + ES_DUR, v)
    b.u8(MI_OOF, m['oof'])
    b.u8(MI_PATHCD, m['pathcd'])
    for i, v in enumerate(m['attrs']):
        b.u8(MI_ATTR + i, v)
    b.u8(MI_MOTIONLESS, m['motionless'])
    b.u8(MI_AIMODE, m['ai_mode'])
    b.u8(MI_PT_SIGHT, m['pt_sight'])
    b.u8(MI_PT_LOS, m['pt_los'][0])
    b.u8(MI_PT_LOS + 1, m['pt_los'][1])
    t = m['target']
    b.u32(MI_TARGET, t[0])
    b.u32(MI_TARGET + 4, t[1])
    b.u32(MI_TARGET + 8, t[2])
    b.u32(MI_TARGET + 0xc, t[3])
    for i, v in enumerate(t[4]):
        b.f32(MI_TARGET + 0x10 + 4 * i, v)
    b.u32(MI_SUMMONED, m['summoned'])
    b.u32(MI_ACTION, m['action'])
    b.u32(MI_DETAIL, m['detail'])
    b.u32(MI_NOISE_MARGIN, m['noise_margin'])
    b.u8(MI_PAUSE, m['pause'])
    b.u32(MI_ELEMENTAL, m['elemental'])
    b.u8(MI_PV_SIGHT, m['pv_sight'])
    for i, v in enumerate(m['pv_los']):
        b.u8(MI_PV_LOS + i, v)
    b.u8(MI_PV_CANSEE, m['pv_cansee'])
    b.u8(MI_PV_LINE, m['pv_line'])
    b.u8(MI_HASPROJ, m['has_proj'])
    b.u8(MI_HASSPELL, m['has_spell'])
    return b


def p3d_blob(p):
    b = Blob(M3_BLOB)
    b.u8(M3_STOPPED, p.get('stopped', 0))
    b.f32(M3_YAW, p.get('yaw', 0.0))
    b.f32(M3_TYAW, p.get('tyaw', 0.0))
    for i, v in enumerate(p.get('pos', (0.0, 0.0, 0.0))):
        b.f32(M3_POS + 4 * i, v)
    b.f32(M3_RADIUS, p.get('radius', 0.0))
    b.f32(M3_HEIGHT, p.get('height', 0.0))
    for i, v in enumerate(p.get('formation', (0.0, 0.0, 0.0))):
        b.f32(M3_FORMATION + 4 * i, v)
    b.u8(M3_ORDERS, p.get('orders', 0))
    b.u8(M3_ORDER_MODE, p.get('order_mode', 0))
    b.u8(M3_FACE, p.get('face', 0))
    b.f32(M3_PDIST, p.get('pdist', 0.0))
    b.f32(M3_PVAR, p.get('pvar', 0.0))
    pts = p.get('points')
    if pts is not None:
        cap = p.get('vec_cap', len(pts))
        b.u32(M3_VEC + 4, len(pts))
        b.u32(M3_VEC + 8, cap)
    b.u8(M3_PINDEX, p.get('pindex', 0))
    for i, v in enumerate(p.get('dir', (0.0, 0.0, 0.0))):
        b.f32(M3_DIR + 4 * i, v)
    for i, v in enumerate(p.get('movedir', (0.0, 0.0, 0.0))):
        b.f32(M3_MOVEDIR + 4 * i, v)
    return b


def rep_blob(rp):
    b = Blob(REP_BLOB)
    b.u8(REP_CUR, rp.get('cur', 1))
    b.u8(REP_PEND, rp.get('pend', 0))
    for cyc, n in rp.get('anims', {}).items():
        b.u32(REP_ANIM + 0x10 * cyc, n)
    return b


def mcs_blob(pc):
    b = Blob(MC_SIZE)
    b.u32(MC_PHASE, pc.get('phase', 0))
    b.u8(MC_ACTIVE, pc.get('active', 0))
    b.u32(MC_APR0, pc.get('apr0', 0))
    b.u32(MC_APR, pc.get('apr', 0))
    b.u32(MC_ATTACK, pc.get('attack', 0))
    b.u8(MC_BERSERK, pc.get('berserk', 0))
    for i, v in pc.get('eff', {}).items():
        b.u32(MC_EFF + ES * i + ES_DUR, v)
    for i, v in pc.get('eff2', {}).items():
        b.u32(MC_EFF2 + ES * i + ES_DUR, v)
    b.u8(MC_COOLDOWN, pc.get('cooldown', 0))
    b.u8(MC_ADVANCING, pc.get('advancing', 0))
    b.u32(MC_SETTLE, pc.get('settle', 0))
    b.u8(MC_RECONSIDER, pc.get('reconsider', 0))
    return b


def new_group(gid, members, **kw):
    g = {'gid': gid, 'members': list(members), 'count': len(members), 'monster_id': 1,
         'active': 1, 'incombat': 1, 'disp': 1, 'leader': members[0] if members else -1,
         'leader_group': 0, 'allies': [0, 0, 0, 0], 'engage': 0, 'ticks': 0}
    g.update(kw)
    return g


def group_blob(g):
    """The group record plus its member IList, kept inside the unused group_state bytes
    (header at +0x30, ids from +0x3c; group_state is not read by the code under test)."""
    b = Blob(G_BLOB)
    b.u32(G_ID, g['gid'])
    b.u32(G_COUNT, g['count'])
    b.u32(G_MONID, g['monster_id'])
    b.u8(G_ACTIVE, g['active'])
    b.u8(G_INCOMBAT, g['incombat'])
    b.u8(G_DISP, g['disp'])
    ids = g['members']
    b.u32(G_IL + 4, len(ids) + 2)
    b.u32(G_IL + 8, len(ids))
    for t, mid in enumerate(ids):
        b.u32(G_IL_DATA + 4 * t, mid)
    b.u32(G_LEADER, g['leader'])
    b.u32(G_LEADER_GROUP, g['leader_group'])
    for i, v in enumerate(g['allies']):
        b.u32(G_ALLIES + 4 * i, v)
    b.u8(G_ENGAGE, g['engage'])
    b.u8(G_TICKS, g['ticks'])
    return b


class Env:
    def __init__(self, ctx):
        self.ctx = ctx
        self.S = [ctx.scratch(i) for i in range(8)]
        self.gx = ctx.g('gXStatus')
        self.st = ctx.g('g_status')
        self.rows = (self.st + 8).deref()
        self.cs_ptr = ctx.g('g_combat_state')
        self.cam = ctx.g('g_gd_camera').deref() + CAM_POS
        self.nav_ptr = ctx.g('g_startup_world')
        self.mipe = ctx.g('g_mipe_active')
        self.sway = ctx.g('g_camera_sway_active')
        self.spell_flag = ctx.g('g_spell_cycle_error_reported')
        self.flee_flag = ctx.g('g_special_attack_cycle_error_reported')
        entry = ctx.syms.map_by_dec.get(PORT_MONSTER_VTABLE)
        if entry is None:
            raise KeyError('port map has no %s' % PORT_MONSTER_VTABLE)
        self.vtable = ctx.absolute(RETAIL_MONSTER_VTABLE, entry['va'], 'W8Monster::vftable')
        self.corpus = ctx.corpus

    def mon(self, k):
        return self.S[0] + k * MI_STRIDE

    def vis(self, k):
        return self.S[0] + VIS_BASE + k * VIS_STRIDE

    def p3d(self, k):
        return self.S[1] + k * P3D_STRIDE

    def rep(self, i):
        return self.S[1] + REP_BASE + i * REP_STRIDE

    def pts(self, k):
        return self.S[1] + PTS_BASE + k * PTS_STRIDE

    def rec(self, j):
        return self.S[2] + j * REC_STRIDE

    def grp(self, g):
        return self.S[3] + L_GROUPS + g * GROUP_STRIDE

    def mcs(self, k):
        return self.S[4] + k * MCS_STRIDE

    def cs(self):
        return self.S[4] + CS_BASE

    def nav(self):
        return self.S[5] + NAV

    def char(self, slot):
        return self.ctx.char(slot)

    def row(self, slot):
        return self.rows + slot * XROW


class World:
    """Fake monsters, records, groups, party slots and globals for one case."""

    def __init__(self, env, c):
        self.env = env
        self.c = c
        self.mons = []
        self.reps = []
        self.recs = []
        self.groups = []
        self.party = {}
        self.in_list = None
        self.sets = []
        self.setps = []
        self.cam = None
        self.nav = None

    def add(self, m):
        self.mons.append(m)
        return len(self.mons) - 1

    def add_rep(self, **kw):
        self.reps.append(kw)
        return len(self.reps) - 1

    def add_rec(self, species, d):
        for i, (s, _) in enumerate(self.recs):
            if s == species:
                self.recs[i] = (species, d)
                return self.env.rec(i)
        self.recs.append((species, d))
        return self.env.rec(len(self.recs) - 1)

    def add_group(self, g):
        self.groups.append(g)
        return len(self.groups) - 1

    def slot(self, slot, occ=None, blk=None, extra=(), sight_only=False):
        """Party slot: XChar.fOccupied, the W8Character block (whole, or with sight_only just
        uiCondition[13] and highest_condition..hp_current) and extra (offset, bytes)."""
        self.party[slot] = {'occ': occ, 'blk': blk, 'extra': list(extra), 'sight': sight_only}

    def setg(self, addr, data):
        self.sets.append((addr, bytes(data)))

    def write(self, reserve=4):
        """Emit the world. Scratch objects go out as non-zero runs; when the case would exceed
        the core's op limit, the closest runs are merged (more zero bytes, fewer lines).
        `reserve`: ops the caller adds afterwards (captures)."""
        env, c = self.env, self.c
        pend = []

        def E(addr, data):
            pend.append(['emit', addr, bytes(data), None])

        def S(addr, data):
            pend.append(['set', addr, bytes(data)])

        def P(addr, value):
            pend.append(['setp', addr, value])

        for j, (species, d) in enumerate(self.recs):
            E(env.rec(j), rec_blob(d))
            P(env.gx + X_RECCACHE + 4 * species, env.rec(j))
        for i, rp in enumerate(self.reps):
            E(env.rep(i), rep_blob(rp))
        for k, m in enumerate(self.mons):
            E(env.mon(k), mon_blob(m))
            p = m['p3d']
            if p is not None:
                E(env.p3d(k), p3d_blob(p))
                P(env.mon(k) + MI_P3D, env.p3d(k))
                if p.get('rep') is not None:
                    P(env.p3d(k) + M3_REP, env.rep(p['rep']))
                if p.get('vtable'):
                    P(env.p3d(k), env.vtable)
                pts = p.get('points')
                if pts:
                    pb = Blob(12 * len(pts))
                    for i, q in enumerate(pts):
                        for a in range(3):
                            pb.f32(12 * i + 4 * a, q[a])
                    E(env.pts(k), pb)
                    P(env.p3d(k) + M3_VEC + 0xc, env.pts(k))
            pc = m['pcombat']
            if pc is not None:
                E(env.mcs(k), mcs_blob(pc))
                P(env.mon(k) + MI_PCOMBAT, env.mcs(k))
            vis = m['vis']
            if vis is not None:
                base = env.vis(k)
                n = len(vis)
                vb = Blob(max(n, 1) * VR_STRIDE)
                for j, e in enumerate(vis):
                    if e is None:
                        continue
                    o = j * VR_STRIDE
                    vb.u32(o, e['about'])
                    vb.u8(o + VR_SIGHT, e['sight'])
                    for t in range(4):
                        vb.u8(o + VR_LOS + t, e['los'][t])
                    vb.u8(o + VR_CANSEE, e.get('cansee', 0))
                    vb.u8(o + VR_LINE, e.get('line', 0))
                E(base + 0x80, vb)
                S(base + 4, p32(n + 2) + p32(n))
                if n:
                    P(base, base + 0x10)
                for j, e in enumerate(vis):
                    if e is not None:
                        P(base + 0x10 + 4 * j, base + 0x80 + j * VR_STRIDE)
                P(env.mon(k) + MI_VISLIST, base)
        ks = list(range(len(self.mons))) if self.in_list is None else list(self.in_list)
        hdr = env.S[3] + L_MON
        ghdr = env.S[3] + L_GRP
        if ks or self.groups:
            if ks:
                S(hdr + 4, p32(len(ks) + 2) + p32(len(ks)))
                P(hdr, hdr + 0x10)
                for i, k in enumerate(ks):
                    P(hdr + 0x10 + 4 * i, env.mon(k))
                P(env.gx + X_MONLIST, hdr)
            else:
                S(env.gx + X_MONLIST, p32(0))
            if self.groups:
                S(ghdr + 4, p32(len(self.groups) + 2) + p32(len(self.groups)))
                P(ghdr, ghdr + 0x10)
                for gi, g in enumerate(self.groups):
                    G = env.grp(gi)
                    if len(g['members']) > G_IL_MAX:
                        raise ValueError('group with %d members' % len(g['members']))
                    E(G, group_blob(g))
                    if g['members']:
                        P(G + G_IL, G + G_IL_DATA)
                    P(G + G_MONSTERS, G + G_IL)
                    P(ghdr + 0x10 + 4 * gi, G)
                P(env.gx + X_MONLIST + 4, ghdr)
            else:
                S(env.gx + X_MONLIST + 4, p32(0))
        else:
            S(env.gx + X_MONLIST, bytes(8))
        S(env.gx + X_UNBORN, bytes(8))
        for slot in sorted(self.party):
            d = self.party[slot]
            if d['occ'] is not None:
                S(env.row(slot), p8(d['occ']))
            blk = d['blk']
            if blk is not None:
                ch = env.char(slot)
                if d['sight']:
                    o13 = C_COND + 4 * 13 - C_BLOCK
                    S(ch + C_COND + 4 * 13, bytes(blk[o13:o13 + 4]))
                    S(ch + C_HIGHEST, bytes(blk[C_HIGHEST - C_BLOCK:C_HP + 4 - C_BLOCK]))
                else:
                    S(ch + C_BLOCK, bytes(blk))
            for off, data in d['extra']:
                S(env.char(slot) + off, data)
        if self.cam is not None:
            S(env.cam, pf(self.cam[0]) + pf(self.cam[1]) + pf(self.cam[2]))
        if self.nav is not None:
            pos, coll, alt = self.nav
            nb = Blob(NAV_COLL + 8)
            for i, v in enumerate(pos):
                nb.f32(NAV_POS + 4 * i, v)
            nb.f32(NAV_COLL, coll)
            nb.f32(NAV_COLL + 4, alt)
            E(env.nav(), nb)
            P(env.nav_ptr, env.nav())
        for addr, data in self.sets:
            S(addr, data)
        for addr, value in self.setps:
            P(addr, value)

        # op budget: merge the closest non-zero runs until the case fits
        for p in pend:
            if p[0] == 'emit':
                p[3] = nz_runs(p[2])
        total = len(c.ops) + reserve + sum(len(p[3]) if p[0] == 'emit' else 1 for p in pend)
        while total > OP_BUDGET:
            best = None
            for p in pend:
                if p[0] != 'emit':
                    continue
                runs = p[3]
                for j in range(len(runs) - 1):
                    g = runs[j + 1][0] - runs[j][1]
                    if best is None or g < best[0]:
                        best = (g, p, j)
            if best is None:
                break
            _, p, j = best
            p[3][j][1] = p[3][j + 1][1]
            del p[3][j + 1]
            total -= 1
        for p in pend:
            if p[0] == 'emit':
                for s, e in p[3]:
                    c.set(p[1] + s, p[2][s:e])
            elif p[0] == 'set':
                c.set(p[1], p[2])
            else:
                c.setp(p[1], p[2])

    # captures
    def cap_mon(self, k, name=None):
        self.c.cap(self.env.mon(k), MI_SIZE, name or 'mon%d' % k, ignore=MI_PTRS, floats=MI_FLOATS)

    def cap_mcs(self, k, name=None):
        self.c.cap(self.env.mcs(k), MC_SIZE, name or 'mcs%d' % k, ignore=[MC_LIST])

    def cap_p3d(self, k, name=None):
        self.c.cap(self.env.p3d(k), M3_SIZE, name or 'p3d%d' % k, ignore=[0, M3_REP, M3_VEC + 0xc],
                   floats=M3_FLOATS)

    def cap_group(self, g, name=None):
        self.c.cap(self.env.grp(g), G_SIZE, name or 'group%d' % g, ignore=[G_MONSTERS, G_IL])


def char_block(env, r, with_data=False):
    """W8Character+0xa01..0xb21 from a random corpus character (Blob, name[, data])."""
    name, data = env.corpus[r.randrange(len(env.corpus))]
    if with_data:
        return Blob(data[C_BLOCK:C_BLOCK_END]), name, data
    return Blob(data[C_BLOCK:C_BLOCK_END]), name


def silence_extras(r, data):
    """skills[MUSIC/ALCHEMY].level and spell_learned[0..0x71] for the SILENCE character arm,
    starting from the corpus character's own values."""
    music = struct.unpack_from('<I', data, C_MUSIC)[0]
    alch = struct.unpack_from('<I', data, C_ALCH)[0]
    learned = list(struct.unpack_from('<%dI' % 0x72, data, C_LEARNED))
    if r.random() < 0.6:
        music = 0 if r.random() < 0.8 else r.choice([1, 50, 0x80000000])
    if r.random() < 0.5:
        alch = 0 if r.random() < 0.5 else r.choice([1, 75])
    k = r.random()
    if k < 0.25:
        learned = [0] * 0x72
    elif k < 0.5:
        learned = [0] * 0x72
        learned[r.randrange(0x72)] = 1
    elif k < 0.65:
        learned = [0] * 0x72
        for _ in range(3):
            learned[r.randrange(0x72)] = r.choice([2, 0xffffffff, 0x101])
        if r.random() < 0.5:
            learned[0x71] = 1
    return [(C_MUSIC, p32(music)), (C_ALCH, p32(alch)),
            (C_LEARNED, b''.join(p32(v) for v in learned))]


def blk_u32(blk, off, v):
    blk.u32(off - C_BLOCK, v)


def blk_get(blk, off):
    return blk.get_u32(off - C_BLOCK)


def party_member(env, r, p_part=0.75, p_turncoat=0.12, with_data=False):
    """Block for one party slot with participation state chosen: returns (occ, blk, name)
    (plus the corpus character's bytes with with_data)."""
    blk, name, data = char_block(env, r, with_data=True)
    occ = 1 if r.random() < 0.9 else 0
    hp = blk_get(blk, C_HP)
    if r.random() > p_part:
        k = r.choice(['hp', 'dead', 'occ'])
        if k == 'hp':
            hp = 0
        elif k == 'dead':
            blk_u32(blk, C_HIGHEST, r.choice([0x12, 0x13, 0x80000000, 0xffffffff]))
        else:
            occ = 0
    elif hp == 0:
        hp = r.choice([1, 20, 150])
    if blk_get(blk, C_HIGHEST) >= 0x12 and r.random() < 0.7 and occ and hp:
        blk_u32(blk, C_HIGHEST, r.choice([0, 0, 3, 0xc, 0x11]))
    blk_u32(blk, C_HP, hp)
    if r.random() < p_turncoat:
        blk_u32(blk, C_COND + 4 * 13, r.choice([1, 5, 9999, 0xffffffff]))
    else:
        blk_u32(blk, C_COND + 4 * 13, 0)
    if with_data:
        return occ, blk, name, data
    return occ, blk, name


def full_party(w, env, r, sight_only=False, **kw):
    names = []
    for s in range(8):
        occ, blk, name = party_member(env, r, **kw)
        w.slot(s, occ=occ, blk=blk, sight_only=sight_only)
        names.append(name)
    return names


def cap_flags(c, env):
    c.cap(env.spell_flag, 1, 'spell_cycle_reported')
    c.cap(env.flee_flag, 1, 'special_cycle_reported')


def rand_target(r, kinds=None, char=None, mon=None, point=None):
    kind = r.choice(kinds) if kinds else r.choice([0, 1, 2, 3, 4, 5, 6])
    ch = char if char is not None else r.choice([-1, 0, 1, 2, 3, 4, 5, 6, 7])
    mo = mon if mon is not None else r.choice([-1, 1, 2, 77, 4000])
    gr = r.choice([-1, 1, 2, 3])
    pt = point if point is not None else (float(r.randrange(-5000, 5000)), float(r.randrange(-500, 500)),
                                          float(r.randrange(-5000, 5000)))
    return (kind, ch, mo, gr, pt)


def distinct_locs(r, n):
    return r.sample(range(1, 4000), n)


def distinct_species(r, n, allow_neutral=0.0):
    out = []
    while len(out) < n:
        s = r.randrange(N_MONSTERS)
        if s == NEUTRAL_SPECIES and r.random() >= allow_neutral:
            continue
        if s not in out:
            out.append(s)
    return out


def cases(ctx):
    env = Env(ctx)
    gen_action_usable(ctx, env)
    gen_spell_target_ok(ctx, env)
    gen_spell_usable(ctx, env)
    gen_can_aim(ctx, env)
    gen_aim_fleeing(ctx, env)
    gen_can_flee(ctx, env)
    gen_has_visible_target(ctx, env)
    gen_group_visible_target(ctx, env)
    gen_no_visible_enemy(ctx, env)
    gen_nearest_distance(ctx, env)
    gen_reinforcement(ctx, env)
    gen_group_engagement(ctx, env)
    gen_update_ai(ctx, env)
    gen_update_all_ai(ctx, env)
    gen_rtai_mode(ctx, env)
    gen_collect(ctx, env, aim=False)
    gen_collect(ctx, env, aim=True)
    gen_random_action(ctx, env)
    gen_group_can_engage(ctx, env)


# ================================================================ IsMonsterActionUsable
def gen_action_usable(ctx, env):
    """bool IsMonsterActionUsable(W8MonsterInfo*). MonsterSpellHasPartyTarget is never reached:
    aimable spells never carry ALL_ENEMIES/PLACE targets and special attacks are summon rows."""
    fn = ctx.fn(0x00535150)
    for i in range(ctx.n(300)):
        r = ctx.rng('action_usable', i)
        c = ctx.case('IsMonsterActionUsable.%d' % i, fn, conv='c', ret='b')
        w = World(env, c)
        species = r.randrange(N_MONSTERS)
        sak = r.choice(SUMMON_KINDS) if r.random() < 0.8 else r.choice(NONSUMMON_KINDS + [0])
        kind = pick(r, [(25, 0), (35, 2), (20, 3), (20, 'other')])
        if kind == 'other':
            kind = r.choice([-1, 1, 4, 5, 6, 7, 8, 9, 10, -2, 0x100, 0x7fffffff])
        detail = r.choice([0, 1, 3, 77])
        iType = r.choice([0, 1, 1, 2, 3, 4, 5, 6, 7, 8, 9, -1, 0x101, 0x7fffffff])
        if kind == 2:
            detail = r.choice(AIMABLE) if r.random() < 0.5 else r.choice(NON_AIMABLE)
            if detail in AIMABLE and iType in (5, 6):
                iType = r.choice([0, 1, 2, 3, 4, 7, 8, 9, -1, 10])
        if kind == 3 and sak not in SUMMON_KINDS:
            sak = r.choice(SUMMON_KINDS)
        rec = new_rec(sak=sak)
        w.add_rec(species, rec)
        w.add(new_mon(r.randrange(1, 4000), species, action=kind, detail=detail,
                      target=rand_target(r, kinds=[iType])))
        w.write()
        w.cap_mon(0)
        finish(c)
        c.arg(env.mon(0))
        c.note(action=kind, detail=detail, target_type=iType, special_kind=sak)


# ================================================================ MonsterSpellTargetOK
ARM_SPELLS = {
    'damage': [1, 4, 5, 9, 10, 25, 28, 36, 42, 43, 47, 50, 52, 55, 57, 63, 66, 70, 71, 78, 79, 83, 86,
               87, 90, 91, 92, 94, 95, 96, 97, 98, 99, 101, 119],
    'bless': [2, 53, 59], 'heal': [6, 68], 'itch': [7], 'para': [11, 37, 67], 'sleep': [12],
    'stamina': [13, 44], 'terror': [14], 'blind': [15], 'cure_lesser': [16], 'being': [20, 26, 32, 40],
    'guardian': [21], 'razor': [27], 'slow': [29], 'web': [31], 'cure_para': [34], 'cure_poison': [35],
    'silence': [46], 'acid': [48, 49, 76, 80, 81, 93], 'eye': [54], 'haste': [56], 'superman': [61],
    'stone': [65], 'hex': [69], 'purify': [72], 'sane': [74], 'banish': [77], 'pandemonium': [85],
    'insanity': [24], 'turncoat': [89], 'point': [38, 60, 123],
    'default': [0, 3, 8, 17, 18, 19, 22, 23, 30, 33, 39, 41, 45, 51, 58, 62, 64, 73, 75, 82, 84, 88,
                100, 102, 110, 113, 114, 115, 116, 117, 118, 120, 125, 131, 140, 149],
}
ARM_COND = {'itch': [3], 'para': [16], 'sleep': [15], 'terror': [6], 'blind': [12],
            'cure_lesser': [3, 4, 6, 15, 12], 'slow': [5], 'web': [14], 'cure_para': [16],
            'cure_poison': [7], 'silence': [8], 'hex': [9], 'sane': [11, 13], 'pandemonium': [6, 11],
            'insanity': [11], 'turncoat': [13]}
ARM_ENCH = {'guardian': 2, 'razor': 3, 'eye': 4, 'haste': 5, 'superman': 6, 'stone': 7}


def gen_spell_target_ok(ctx, env):
    """bool MonsterSpellTargetOK(W8MonsterInfo* caster, int spell, W8CombatSlot*): character
    slots (block + party effect slots + combat-state effect slots) and monster slots (fake
    target monster, its record, combat effects, SILENCE through IsSpellUsableByMonster)."""
    fn = ctx.fn(0x005327E0)
    arms = list(ARM_SPELLS)
    for i in range(ctx.n(460)):
        r = ctx.rng('spell_target_ok', i)
        c = ctx.case('MonsterSpellTargetOK.%d' % i, fn, conv='c', ret='b')
        w = World(env, c)
        arm = arms[i % len(arms)] if i < 3 * len(arms) else r.choice(arms)
        spell = r.choice(ARM_SPELLS[arm])
        combat = rb(r, 0.6)
        w.setg(env.gx + X_COMBAT, p8(combat))
        w.setg(env.mipe, p8(1))
        w.setg(env.sway, p8(rb(r, 0.2)))
        flag = rb(r, 0.3)
        w.setg(env.spell_flag, p8(flag))
        # combat state: both effect-slot arrays (the character side of BLESS/ACID/PURIFY)
        csb = Blob(CS_EFF0 + 6 * ES)
        for s in range(9):
            if r.random() < 0.3:
                csb.u32(CS_EFF + ES * s + ES_DUR, turns_val(r, 0.0))
        for s in range(6):
            if r.random() < 0.3:
                csb.u32(CS_EFF0 + ES * s + ES_DUR, turns_val(r, 0.0))
        emit(c, env.cs(), csb, gap=0x30)
        w.setps.append((env.cs_ptr, env.cs()))
        sp_caster = r.randrange(N_MONSTERS)
        caster_disp = r.choice([0, 1, 1, 2])
        caster_incombat = rb(r, 0.7)
        cm = new_mon(r.randrange(1, 2000), sp_caster, disp=caster_disp, incombat=caster_incombat,
                     pcombat={'reconsider': rb(r)} if caster_incombat else None)
        w.add_rec(sp_caster, rand_rec(r))
        k_caster = w.add(cm)
        is_char = r.random() < 0.5
        slot_blob = Blob(0x20)
        info = {}
        if is_char:
            slot = r.randrange(8)
            blk, name, cdata = char_block(env, r, with_data=True)
            if r.random() < 0.4:
                blk_u32(blk, C_HP, blk_get(blk, C_HPMAX))
            else:
                blk_u32(blk, C_HP, r.choice([0, 1, blk_get(blk, C_HPMAX) // 2, r.randrange(1, 300)]))
            if r.random() < 0.4:
                blk_u32(blk, C_ST, blk_get(blk, C_STMAX))
            else:
                blk_u32(blk, C_ST, r.choice([0, 1, r.randrange(1, 200), 0xffffffff]))
            for ci in ARM_COND.get(arm, []) + [r.randrange(20)]:
                blk_u32(blk, C_COND + 4 * ci, cond_val(r))
            if arm in ARM_ENCH:
                blk_u32(blk, C_ENCH + 12 * ARM_ENCH[arm] + 8, turns_val(r))
            extra = silence_extras(r, cdata) if arm == 'silence' else []
            w.slot(slot, blk=blk, extra=extra)
            if arm == 'being' or r.random() < 0.15:
                eb = Blob(12 * ES)
                for s in range(12):
                    if r.random() < 0.35:
                        eb.u32(ES * s + ES_DUR, turns_val(r, 0.0))
                w.setg(env.st + GS_EFFECTS, eb)
            slot_blob.u32(0, 1)
            slot_blob.u32(4, slot)
            slot_blob.u32(8, -1)
            slot_blob.u32(0xc, -1)
            info = {'slot': 'char%d' % slot, 'char': name}
        else:
            self_target = r.random() < 0.12
            if self_target:
                k_t = k_caster
                tm = cm
            else:
                sp_t = r.randrange(N_MONSTERS)
                tm = new_mon(r.randrange(2000, 4000), sp_t, disp=r.choice([0, 1, 2, 2]),
                             incombat=rb(r, 0.7))
                k_t = None
            trec = rand_rec(r)
            trec['kind'] = r.choice([0, 3, 4, 5, 6, 0xc, 0xd, 0x14, 0x15, 0x1c, r.randrange(0x20)])
            trec['sc'] = r.choice([0, 0, 10, 0x3b, 0x3c, 0x3d, 80, 255])
            if arm == 'silence':
                trec['spells'] = [r.choice(SPELLS) if r.random() < 0.6 else 0 for _ in range(10)]
            tm['hp'] = r.choice([0, 1, 50, 100, 0xffffffff])
            tm['hpmax'] = tm['hp'] if r.random() < 0.4 else r.choice([100, 1, 0, 0x80000000])
            tm['st'] = r.choice([0, 30, 60])
            tm['stmax'] = tm['st'] if r.random() < 0.4 else r.choice([60, 1, 0])
            for ci in ARM_COND.get(arm, []) + [r.randrange(20)]:
                tm['cond'][ci] = cond_val(r)
            if arm in ARM_ENCH:
                tm['ench'][ARM_ENCH[arm]] = turns_val(r)
            for s in range(12):
                if r.random() < 0.25:
                    tm['effects'][s] = turns_val(r, 0.0)
            tm['summoned'] = r.choice([0, 0, 0, 1, 2, 0xffffffff])
            tm['elemental'] = r.choice([-1, -1, 0, 5])
            if tm['incombat']:
                pc = tm['pcombat'] or {}
                pc['eff'] = {s: turns_val(r, 0.0) for s in range(9) if r.random() < 0.3}
                pc['eff2'] = {s: turns_val(r, 0.0) for s in range(6) if r.random() < 0.3}
                pc.setdefault('reconsider', rb(r))
                tm['pcombat'] = pc
            if arm == 'silence' and trec['sc'] and tm['cond'].get(8, 0) == 0:
                rep = w.add_rep(anims={CYC_SPELL: r.choice([0, 1, 3])})
                tm['p3d'] = {'rep': rep, 'vtable': True}
            if self_target:
                w.add_rec(sp_caster, trec)
            else:
                w.add_rec(tm['species'], trec)
                k_t = w.add(tm)
            slot_blob.u32(0, 3)
            slot_blob.u32(4, -1)
            slot_blob.u32(8, tm['loc'])
            slot_blob.u32(0xc, -1)
            info = {'slot': 'self' if self_target else 'monster', 'target_kind': trec['kind'],
                    'target_disp': tm['disp']}
        emit(c, env.S[5] + SLOT, slot_blob)
        w.write()
        for k in range(len(w.mons)):
            w.cap_mon(k)
        c.cap(env.spell_flag, 1, 'spell_cycle_reported')
        finish(c)
        c.arg(env.mon(k_caster))
        c.arg(spell)
        c.arg(env.S[5] + SLOT)
        c.note(arm=arm, spell=spell, combat=combat, caster_disp=caster_disp, **info)


# ================================================================ IsSpellUsableByMonster
def gen_spell_usable(ctx, env):
    """bool IsSpellUsableByMonster(W8MonsterInfo*, int spell, bool needs_target). needs_target
    only where the spell fails before CollectMonsterSpellTargets or is the POINT spell 60."""
    fn = ctx.fn(0x00532550)
    for i in range(ctx.n(300)):
        r = ctx.rng('spell_usable', i)
        c = ctx.case('IsSpellUsableByMonster.%d' % i, fn, conv='c', ret='b')
        w = World(env, c)
        sway = rb(r, 0.3)
        w.setg(env.mipe, p8(1))
        w.setg(env.sway, p8(sway))
        spell = pick(r, [(10, SUMMON_ELEMENTAL), (25, lambda: r.choice(FIRE_CASTABLE)),
                         (30, lambda: r.randrange(150)), (10, lambda: r.choice(NON_CASTABLE)),
                         (5, 0)])
        silenced = r.random() < 0.3
        species = r.randrange(N_MONSTERS)
        rec = new_rec(kind=r.choice([0, 3, 4, 5, 6, 0xc, 0xd, 0xe, 0x14]))
        w.add_rec(species, rec)
        m = new_mon(r.randrange(1, 4000), species,
                    cond={8: r.choice([1, 9999, 0x80000000, 0xffffffff])} if silenced else {},
                    elemental=r.choice([-1, -1, -1, 0, 7, 0x7fffffff]))
        # needs_target only where the call fails before collecting targets, or for the
        # POINT spell 60 whose collection just takes the monster's position
        safe_needs = (spell == 0 or not SPELL_CAST[spell] or
                      (SPELL_REALM[spell] == 0 and sway) or spell == SUMMON_ELEMENTAL)
        needs = rb(r, 0.6) if safe_needs else 0
        if spell == SUMMON_ELEMENTAL or r.random() < 0.3:
            m['p3d'] = {'pos': (float(r.randrange(-9000, 9000)), float(r.randrange(-900, 900)),
                                float(r.randrange(-9000, 9000)))}
        w.add(m)
        w.write()
        w.cap_mon(0)
        finish(c)
        c.arg(env.mon(0))
        c.arg(spell)
        c.arg(needs)
        c.note(spell=spell, needs_target=needs, silenced=int(silenced), sway=sway,
               elemental=m['elemental'], kind=rec['kind'])


# ================================================================ CanMonsterAimSpell
def gen_can_aim(ctx, env):
    """bool CanMonsterAimSpell(W8MonsterInfo*, int spell): CONE/RADIUS spells collect an empty
    target list (the caster's spell-sight flag is 0 and nothing else is listed);
    needs_aim spells resolve Target.point from the camera or a listed target monster."""
    fn = ctx.fn(0x00534290)
    for i in range(ctx.n(250)):
        r = ctx.rng('can_aim', i)
        c = ctx.case('CanMonsterAimSpell.%d' % i, fn, conv='c', ret='b')
        w = World(env, c)
        w.cam = rand_cam(r)
        spell = r.randrange(150) if r.random() < 0.7 else r.choice(AREA_SPELLS)
        species = r.randrange(N_MONSTERS)
        w.add_rec(species, rand_rec(r))
        tloc = r.randrange(2000, 4000)
        iType = r.choice([0, 1, 1, 2, 2, 3, 3, 4, 5, 6, 7, 9])
        m = new_mon(r.randrange(1, 2000), species, has_spell=rb(r, 0.3),
                    target=rand_target(r, kinds=[iType], mon=tloc))
        w.add(m)
        if iType == 3:
            sp2 = r.randrange(N_MONSTERS)
            w.add_rec(sp2, rand_rec(r))
            t = new_mon(tloc, sp2, disp=m['disp'],
                        p3d={'pos': (float(r.randrange(-20000, 20000)), float(r.randrange(-2000, 2000)),
                                     float(r.randrange(-20000, 20000)) + 0.25),
                             'height': float(r.choice([0, 150, 900, 1775]))})
            w.add(t)
        w.write()
        w.cap_mon(0)
        finish(c)
        c.arg(env.mon(0))
        c.arg(spell)
        c.note(spell=spell, target_type=iType, spell_tt=SPELL_TT[spell])


# ================================================================ AimFleeingMonster
def gen_aim_fleeing(ctx, env):
    """bool AimFleeingMonster(W8MonsterInfo*, const W8MonsterRecord*): summon rows aim at the
    monster's own position; other rows collect the special-attack cone (kept empty)."""
    fn = ctx.fn(0x00534cb0)
    for i in range(ctx.n(150)):
        r = ctx.rng('aim_fleeing', i)
        c = ctx.case('AimFleeingMonster.%d' % i, fn, conv='c', ret='b')
        w = World(env, c)
        species = r.randrange(N_MONSTERS)
        sak = r.choice(SUMMON_KINDS) if r.random() < 0.6 else r.choice(NONSUMMON_KINDS + [0])
        rec = rand_rec(r)
        rec['sak'] = sak
        raddr = w.add_rec(species, rec)
        pos = (float(r.randrange(-30000, 30000)) + r.choice([0.0, 0.5, 0.125]),
               float(r.randrange(-3000, 3000)), float(r.randrange(-30000, 30000)))
        m = new_mon(r.randrange(1, 2000), species, disp=r.choice([1, 2]),
                    target=rand_target(r), p3d={'pos': pos})
        w.add(m)
        for _ in range(r.choice([0, 0, 1, 2])):
            sp2 = r.randrange(N_MONSTERS)
            w.add_rec(sp2, rand_rec(r))
            w.add(new_mon(r.randrange(2000, 4000), sp2, disp=m['disp'],
                          active=rb(r, 0.8), hp=r.choice([0, 40])))
        w.write()
        w.cap_mon(0)
        finish(c)
        c.arg(env.mon(0))
        c.arg(raddr)
        c.note(special_kind=sak, summon=int(sak in SUMMON_KINDS))


# ================================================================ CanMonsterFlee
def gen_can_flee(ctx, env):
    """bool CanMonsterFlee(W8MonsterInfo*, W8MonsterRecord*, bool exclude_special)."""
    fn = ctx.fn(0x00534A40)
    for i in range(ctx.n(300)):
        r = ctx.rng('can_flee', i)
        c = ctx.case('CanMonsterFlee.%d' % i, fn, conv='c', ret='b')
        w = World(env, c)
        combat = rb(r, 0.6)
        w.setg(env.gx + X_COMBAT, p8(combat))
        flee_flag = rb(r, 0.3)
        w.setg(env.flee_flag, p8(flee_flag))
        species = r.randrange(N_MONSTERS)
        rec = rand_rec(r)
        rec['fc'] = r.choice([1, 20, 50, 99, 100, 255]) if r.random() < 0.92 else 0
        rec['sak'] = pick(r, [(55, lambda: r.choice(SUMMON_KINDS)),
                              (40, lambda: r.choice(NONSUMMON_KINDS)), (5, 0)])
        raddr = w.add_rec(species, rec)
        rep = w.add_rep(anims={CYC_SPECIAL: 0 if r.random() < 0.08 else r.choice([1, 2])})
        w.cam = rand_cam(r)
        sr = rand_radius(r)
        w.nav = ((0.0, 0.0, 0.0), sr, sr)
        mr = rand_radius(r)
        dist = near(r, [12500.0], 30000.0)
        pos = place_from(r, player_ref(w.cam), dist, mr, sr)
        stmax = r.choice([0, 9, 10, 11, 60, 100, 0xffffffff, r.randrange(1, 500)])
        st = r.choice([0, stmax // 10, stmax // 10 - 1, stmax // 10 + 1, stmax, r.randrange(0, 500),
                       0xffffffff])
        m = new_mon(r.randrange(1, 4000), species, disp=r.choice([0, 1, 1, 2]),
                    stmax=stmax, st=st & 0xffffffff,
                    cond={8: cond_val(r, 0.6)},
                    pv_los=(rb(r), rb(r), 0, rb(r)),
                    p3d={'pos': pos, 'radius': mr, 'rep': rep, 'vtable': True},
                    pcombat={'cooldown': 0 if r.random() < 0.8 else r.choice([1, 3, 0xff])})
        w.add(m)
        exclude = rb(r, 0.35)
        w.write()
        w.cap_mon(0)
        c.cap(env.flee_flag, 1, 'special_cycle_reported')
        finish(c)
        c.arg(env.mon(0))
        c.arg(raddr)
        c.arg(exclude)
        c.note(flee_chance=rec['fc'], special_kind=rec['sak'], combat=combat, dist=dist,
               stamina='%d/%d' % (m['st'], m['stmax']), exclude=exclude, reported=flee_flag)


# ================================================================ sight helpers
def sight_monster(r, loc, species, disp=None):
    return new_mon(loc, species, disp=r.choice([0, 1, 1, 2]) if disp is None else disp,
                   active=rb(r, 0.9), hp=0 if r.random() < 0.1 else r.choice([1, 40, 400]),
                   highest=0 if r.random() < 0.8 else r.choice([0x11, 0x12, 0x13, 0xffffffff]),
                   incombat=rb(r, 0.8),
                   cond={13: r.choice([0, 0, 0, 0, 1, 50])},
                   pv_sight=r.choice([0, 1, 1, 1, 2]),
                   pv_los=(rb(r, 0.7), rb(r, 0.7), rb(r, 0.7), rb(r, 0.7)),
                   pt_sight=r.choice([0, 0, 1, 2]), pt_los=(rb(r), rb(r)),
                   has_proj=rb(r, 0.3), has_spell=rb(r, 0.3))


def sight_record(r):
    rec = rand_rec(r)
    rec['faction'] = r.choice([0, 0, 1, 5, 9, 15])
    return rec


def monster_reach(rec):
    """MonsterHasVisibleTarget's reach: CalcRangeDistance(GetMonsterBestRangeCategory(skip=1))
    + combat_move_range * 20 * 1000, floored at engagement range + 7500."""
    best = -1
    for has, rng, _ in rec['attacks']:
        if has and rng > best:
            best = rng
    if rec['sak'] != 0 and rec['sak'] not in SUMMON_KINDS and best < 2:
        best = 2
    for s in rec['spells']:
        if s in AIMABLE and SPELL_RANGE[s] > best:
            best = SPELL_RANGE[s]
    reach = RANGE_DIST.get(best, 0.0) + f32r(rec['move'] * 20.0) * 1000.0
    return max(reach, ENGAGE_RANGE + ENGAGE_FLOOR)


def place_reach(r, w, k0=0):
    """Camera, party navigator and p3D stubs for every monster: monster k0 around its own
    reach from the player, the others around that reach from monster k0."""
    w.cam = rand_cam(r)
    sr = rand_radius(r)
    w.nav = ((0.0, 0.0, 0.0), sr, sr)
    rec0 = dict(w.recs)[w.mons[k0]['species']]
    reach = monster_reach(rec0)
    thresholds = [reach, ENGAGE_RANGE + ENGAGE_FLOOR]
    ref = player_ref(w.cam)
    mr0 = rand_radius(r)
    p0 = place_from(r, ref, near(r, thresholds, reach + 30000.0), mr0, sr)
    w.mons[k0]['p3d'] = {'pos': p0, 'radius': mr0}
    for k in range(len(w.mons)):
        if k != k0:
            mr = rand_radius(r)
            pk = place_from(r, p0, near(r, thresholds, reach + 30000.0), mr, mr0)
            w.mons[k]['p3d'] = {'pos': pk, 'radius': mr}
    return reach


def build_sight_world(r, env, w, n_others, reach=False, caster_disp=None, vis_p=0.85):
    """Caster (index 0) and n_others listed monsters with records, mon-to-mon rows, and
    p3D stubs when distances are measured."""
    locs = distinct_locs(r, n_others + 1)
    species = distinct_species(r, n_others + 1, allow_neutral=0.15)
    for k in range(n_others + 1):
        m = sight_monster(r, locs[k], species[k], disp=caster_disp if k == 0 else None)
        if k == 0:
            m['active'] = 1 if r.random() < 0.95 else 0
        w.add(m)
        w.add_rec(species[k], sight_record(r))
    caster = w.mons[0]
    entries = []
    for k in range(1, n_others + 1):
        if r.random() < vis_p:
            entries.append({'about': locs[k], 'sight': r.choice([0, 1, 1, 1, 2]),
                            'los': tuple(rb(r, 0.7) for _ in range(4))})
    if r.random() < 0.15:
        entries.append({'about': r.randrange(5000, 6000), 'sight': 1, 'los': (1, 1, 1, 1)})
    r.shuffle(entries)
    caster['vis'] = entries
    if reach:
        w.recs[0][1]['move'] = r.choice([0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0])
    return caster


# ================================================================ MonsterHasVisibleTarget
def gen_has_visible_target(ctx, env):
    """bool MonsterHasVisibleTarget(W8MonsterInfo*, bool party_only, int hostility,
    bool within_reach): party scan (8 slots), monster scan through mon-to-mon rows, reach =
    CalcRangeDistance(GetMonsterBestRangeCategory(skip=1)) + move range, floored at 32500."""
    fn = ctx.fn(0x00534850)
    for i in range(ctx.n(400)):
        r = ctx.rng('has_visible_target', i)
        c = ctx.case('MonsterHasVisibleTarget.%d' % i, fn, conv='c', ret='b')
        w = World(env, c)
        within = rb(r, 0.4)
        n_others = r.choice([0, 1, 2, 3, 4])
        caster = build_sight_world(r, env, w, n_others, reach=bool(within))
        rec0 = w.recs[0][1]
        if within and r.random() < 0.5:
            rec0['sak'] = r.choice(NONSUMMON_KINDS + SUMMON_KINDS + [0])
        rec0['spells'] = [r.randrange(150) if r.random() < 0.4 else 0 for _ in range(10)]
        reach = place_reach(r, w) if within else None
        full_party(w, env, r, sight_only=True)
        party_only = rb(r, 0.4)
        hostility = r.choice([0, 1, 1, 2, 3, 4, 4])
        w.write(reserve=len(w.mons))
        for k in range(len(w.mons)):
            w.cap_mon(k)
        finish(c)
        c.arg(env.mon(0))
        c.arg(party_only)
        c.arg(hostility)
        c.arg(within)
        c.note(party_only=party_only, hostility=hostility, within_reach=within, others=n_others,
               pv_sight=caster['pv_sight'], disp=caster['disp'], reach=reach)


# ================================================================ MonsterGroupHasVisibleTarget
def gen_group_visible_target(ctx, env):
    """bool MonsterGroupHasVisibleTarget(W8MonsterGroup*, bool party_only, int hostility,
    bool within_reach): every live member is asked MonsterHasVisibleTarget."""
    fn = ctx.fn(0x005347A0)
    for i in range(ctx.n(250)):
        r = ctx.rng('group_visible_target', i)
        c = ctx.case('MonsterGroupHasVisibleTarget.%d' % i, fn, conv='c', ret='b')
        w = World(env, c)
        within = rb(r, 0.25)
        n = r.choice([1, 2, 2, 3, 4])
        locs = distinct_locs(r, n + 1)
        species = distinct_species(r, n + 1, allow_neutral=0.1)
        if within:
            w.cam = rand_cam(r)
            sr = rand_radius(r)
            w.nav = ((0.0, 0.0, 0.0), sr, sr)
        for k in range(n + 1):
            m = sight_monster(r, locs[k], species[k])
            rec = sight_record(r)
            rec['spells'] = [r.randrange(150) if r.random() < 0.3 else 0 for _ in range(10)]
            w.add(m)
            w.add_rec(species[k], rec)
            if within:
                mr = rand_radius(r)
                th = [monster_reach(rec), ENGAGE_RANGE + ENGAGE_FLOOR]
                m['p3d'] = {'pos': place_from(r, player_ref(w.cam), near(r, th, th[0] + 30000.0), mr, sr),
                            'radius': mr}
        # member rows: some members see the last monster (a non-member)
        for k in range(n):
            if r.random() < 0.4:
                w.mons[k]['vis'] = [{'about': locs[n], 'sight': r.choice([0, 1, 1, 2]),
                                     'los': tuple(rb(r, 0.7) for _ in range(4))}]
        members = locs[:n]
        if r.random() < 0.1:
            members = []
        w.add_group(new_group(r.randrange(1, 50), members))
        full_party(w, env, r, sight_only=True)
        party_only = rb(r, 0.4)
        hostility = r.choice([0, 1, 1, 2, 3, 4, 4])
        w.write()
        w.cap_group(0)
        finish(c)
        c.arg(env.grp(0))
        c.arg(party_only)
        c.arg(hostility)
        c.arg(within)
        c.note(party_only=party_only, hostility=hostility, within_reach=within, members=len(members))


# ================================================================ MonsterHasNoVisibleEnemy
def gen_no_visible_enemy(ctx, env):
    """bool MonsterHasNoVisibleEnemy(W8MonsterInfo*, bool party_only)."""
    fn = ctx.fn(0x00534690)
    for i in range(ctx.n(250)):
        r = ctx.rng('no_visible_enemy', i)
        c = ctx.case('MonsterHasNoVisibleEnemy.%d' % i, fn, conv='c', ret='b')
        w = World(env, c)
        n_others = r.choice([0, 1, 2, 3, 4])
        caster = build_sight_world(r, env, w, n_others)
        caster['pt_sight'] = r.choice([0, 0, 0, 1, 2])
        full_party(w, env, r, sight_only=True)
        party_only = rb(r, 0.4)
        w.write()
        w.cap_mon(0)
        finish(c)
        c.arg(env.mon(0))
        c.arg(party_only)
        c.note(party_only=party_only, pt_sight=caster['pt_sight'], pv_sight=caster['pv_sight'],
               disp=caster['disp'], others=n_others)


# ================================================================ GetGroupNearestDistance
def gen_nearest_distance(ctx, env):
    """float GetGroupNearestDistance(W8MonsterGroup*): smallest member distance to the
    player, starting from 999999 (distances clamp to 0 inside the radii)."""
    fn = ctx.fn(0x005324b0)
    for i in range(ctx.n(200)):
        r = ctx.rng('nearest_distance', i)
        c = ctx.case('GetGroupNearestDistance.%d' % i, fn, conv='c', ret='f')
        w = World(env, c)
        w.cam = rand_cam(r)
        sr = rand_radius(r)
        w.nav = ((0.0, 0.0, 0.0), r.choice([sr, 0.0]), sr)
        n = r.choice([0, 1, 1, 2, 3, 4, 5]) if i > 2 else 0
        locs = distinct_locs(r, max(n, 1))
        ref = player_ref(w.cam)
        dists = []
        for k in range(n):
            mr = rand_radius(r)
            d = near(r, [999999.0, 1000.0, 2000.0, 12500.0], 1200000.0)
            if r.random() < 0.03:
                pos = (float('nan'), 0.0, 0.0)
            elif r.random() < 0.03:
                pos = (1e30, 0.0, 0.0)
            else:
                pos = place_from(r, ref, d, mr, sr)
            dists.append(d)
            w.add(new_mon(locs[k], r.randrange(N_MONSTERS), p3d={'pos': pos, 'radius': mr}))
        w.add_group(new_group(r.randrange(1, 50), locs[:n]))
        w.write()
        finish(c)
        c.arg(env.grp(0))
        c.note(members=n, dists=','.join('%g' % d for d in dists))


# ================================================================ MonsterGroupHasReinforcement
def gen_reinforcement(ctx, env):
    """bool MonsterGroupHasReinforcement(W8MonsterGroup*): a hostile fighting monster with
    party-threat flag 1 that is nearer to a member than 1.15x its own party distance."""
    fn = ctx.fn(0x00534FC0)
    for i in range(ctx.n(300)):
        r = ctx.rng('reinforcement', i)
        c = ctx.case('MonsterGroupHasReinforcement.%d' % i, fn, conv='c', ret='b')
        w = World(env, c)
        hostile_count = r.choice([0, 1, 1, 3, 3, 0xffffffff]) if i % 10 else 0
        w.setg(env.gx + X_HOSTILE, p32(hostile_count))
        w.cam = rand_cam(r)
        sr = float(r.choice([0, 0, 250, 500]))
        w.nav = ((0.0, 0.0, 0.0), sr, sr)
        ref = player_ref(w.cam)
        n_mem = r.choice([1, 1, 2, 3])
        n_oth = r.choice([0, 1, 2, 3])
        locs = distinct_locs(r, n_mem + n_oth)
        species = distinct_species(r, n_mem + n_oth)
        mem_pos = []
        for k in range(n_mem):
            mr = float(r.choice([0, 0, 100, 300]))
            d = near(r, [ENGAGE_RANGE], 40000.0)
            pos = place_from(r, ref, d, mr, sr)
            mem_pos.append((pos, mr))
            rec = sight_record(r)
            rec['camo1'] = r.choice([0, 0, 1, 50])
            w.add_rec(species[k], rec)
            w.add(new_mon(locs[k], species[k], disp=r.choice([0, 0, 1, 2]),
                          pt_los=(rb(r), rb(r, 0.8)), p3d={'pos': pos, 'radius': mr}))
        for k in range(n_mem, n_mem + n_oth):
            mr = float(r.choice([0, 0, 100, 300]))
            if mem_pos and r.random() < 0.7:
                base, br = r.choice(mem_pos)
                # other monster at distance a from a member: probe the 1.15 slack region
                a = float(r.choice([0, 100, 1000, 5000, 9000, r.randrange(0, 30000)]))
                pos = place_from(r, base, a, mr, br)
            else:
                pos = place_from(r, ref, near(r, [ENGAGE_RANGE], 40000.0), mr, sr)
            w.add_rec(species[k], sight_record(r))
            w.add(new_mon(locs[k], species[k], disp=r.choice([1, 1, 1, 0, 2]),
                          active=rb(r, 0.9), incombat=rb(r, 0.85),
                          hp=0 if r.random() < 0.1 else 50, pt_los=(rb(r), rb(r, 0.85)),
                          p3d={'pos': pos, 'radius': mr}))
        w.add_group(new_group(r.randrange(1, 50), locs[:n_mem], disp=0))
        w.write()
        finish(c)
        c.arg(env.grp(0))
        c.note(hostile_count=hostile_count, members=n_mem, others=n_oth)


# ================================================================ UpdateMonsterGroupEngagement
def gen_group_engagement(ctx, env):
    """void UpdateMonsterGroupEngagement(void): per unled hostile fighting group, engagement =
    no settling member (settle_ticks < 3, unsigned) in the group or its allies and the
    group's own engagement_ticks < 3; written through SetMonsterGroupEngagementState."""
    fn = ctx.fn(0x00535200)
    for i in range(ctx.n(250)):
        r = ctx.rng('group_engagement', i)
        c = ctx.case('UpdateMonsterGroupEngagement.%d' % i, fn, conv='c', ret='v')
        w = World(env, c)
        cb = Blob(CS_UPDATE + 4)
        upd = r.choice([0, 1, 2, 3, 3, 4, 10, 100, 0xffffffff]) if r.random() < 0.3 else r.choice([3, 5, 20])
        cb.u32(CS_UPDATE, upd)
        emit(c, env.cs(), cb)
        w.setps.append((env.cs_ptr, env.cs()))
        n_groups = r.choice([1, 2, 3, 4])
        gids = r.sample(range(1, 60), n_groups)
        loc_pool = iter(distinct_locs(r, 4 * n_groups))
        for gi in range(n_groups):
            n_mem = r.choice([0, 1, 2, 3]) if r.random() < 0.9 else 0
            mem = []
            for _ in range(n_mem):
                loc = next(loc_pool)
                settle = r.choice([0, 1, 2, 3, 3, 4, 10, -1, 0x80000000])
                m = new_mon(loc, r.randrange(N_MONSTERS), active=rb(r, 0.9), incombat=rb(r, 0.85))
                if m['active'] and m['incombat']:
                    m['pcombat'] = {'settle': settle}
                w.add(m)
                mem.append(loc)
            allies = [0, 0, 0, 0]
            for a in range(4):
                if r.random() < 0.3:
                    allies[a] = r.choice(gids)
            g = new_group(gids[gi], mem, active=rb(r, 0.9), incombat=rb(r, 0.85),
                          disp=r.choice([1, 1, 1, 0, 2]),
                          leader_group=0 if r.random() < 0.85 else r.choice(gids),
                          allies=allies, monster_id=r.choice([1, 77, 0x1b6, 0x234]) if r.random() < 0.3 else 1,
                          engage=rb(r), ticks=r.choice([0, 1, 2, 3, 4, 254, 255]))
            w.add_group(g)
        w.write()
        for gi in range(n_groups):
            w.cap_group(gi)
        finish(c)
        c.note(update_count=upd, groups=n_groups)


# ================================================================ UpdateMonsterAI
def ai_monster(r, w, env, loc, species, group_id, scenario, in_list_monsters=()):
    """One monster set up for UpdateMonsterAI along a path that never reaches
    ChooseRandomMonsterAction, markers or the formation code. Returns (index, info)."""
    rec = rand_rec(r)
    rec['kind'] = r.choice([0, 1, 3, 0xc, 0xd])
    rec['fc'] = 0
    rec['sc'] = 0
    rec['adv'] = 0
    rec['morale'] = r.choice([1, 2, 3])
    rec['sak'] = 0
    rec['prefer'] = 1
    m = new_mon(loc, species, group=group_id, disp=r.choice([1, 1, 2]),
                hpmax=r.choice([20, 40, 100, 300]), highest=r.choice([0, 0, 0, 3, 0xc, 0xe]),
                pv_sight=r.choice([0, 2]), pv_los=(rb(r), rb(r), rb(r), rb(r)),
                action=r.choice([-1, 0, 1, 6]), detail=r.choice([0, 3]),
                cond={12: r.choice([0, 0, 0, 3])},
                pcombat={'phase': r.choice([0, 2, 7]), 'active': rb(r), 'advancing': 0,
                         'reconsider': rb(r)})
    m['hp'] = r.randrange(0, m['hpmax'] + 1)
    rep = w.add_rep(cur=1, anims={CYC_SPECIAL: r.choice([0, 1]), CYC_SPELL: r.choice([0, 1, 1])})
    mr = rand_radius(r)
    m['p3d'] = {'rep': rep, 'vtable': True, 'radius': mr, 'pos': (0.0, 0.0, 0.0)}
    info = {'scenario': scenario}
    ref = player_ref(w.cam)
    sr = w.nav[2]
    if scenario == 'asleep':
        m['highest'] = r.choice([0xf, 0x10, 0x11, 0x12, 0x13, 0x14, 0x80000000, 0xffffffff])
    elif scenario == 'species224':
        species = NEUTRAL_SPECIES
        m['species'] = species
    elif scenario == 'advance':
        k = r.choice(['npc', 'advancing', 'chance', 'morale0', 'npc'])
        info['advance'] = k
        if k == 'npc':
            rec['flags'] |= 1
            m['disp'] = r.choice([0, 2, 1])
            m['hpmax'] = r.choice([100, 3, 300])
            m['hp'] = r.choice([0, 33, 34, m['hpmax'] // 3, m['hpmax'] // 3 + 1, m['hpmax']]) & 0xffffffff
            if r.random() < 0.1:
                m['hp'] = r.choice([0x7fffffff, 0x2000000])
            rec['adv'] = r.choice([0, 0, 100, 255])
            rec['morale'] = r.choice([0, 1])
        elif k == 'advancing':
            m['pcombat']['advancing'] = 1
            m['disp'] = 1
            m['pv_los'] = (rb(r, 0.7), m['pv_los'][1], m['pv_los'][2], m['pv_los'][3])
            d = near(r, [2000.0], 20000.0)
            m['p3d']['pos'] = place_from(r, ref, d, mr, sr)
            info['dist'] = d
            rec['adv'] = 100
        elif k == 'chance':
            rec['adv'] = r.choice([1, 50, 99, 100, 101, 255])
        else:
            rec['adv'] = 0
            rec['morale'] = 0
        if m['disp'] != 0 and rec['adv'] < 100 and k != 'npc':
            rec['adv'] = 100
    elif scenario == 'neutral':
        m['disp'] = 0
        rec['adv'] = r.choice([0, 30, 70])
        rec['morale'] = 1 if rec['adv'] == 0 else rec['morale']
        rec['camo1'] = r.choice([0, 0, 1, 40])
    elif scenario in ('ranged', 'rating'):
        m['disp'] = r.choice([1, 1, 2])
        rec['adv'] = r.choice([0, 0, 20])
        rec['morale'] = 1 if rec['adv'] == 0 else rec['morale']
        if scenario == 'ranged':
            rec['prefer'] = 0
            rec['attacks'] = [(1, r.choice([0, 1]), 1), (r.choice([0, 1]), r.choice([0, 1, 2, 3]), 3),
                              (0, 0, 0)]
            d = near(r, [1000.0, 2000.0, 999999.0], 30000.0)
            m['pv_los'] = (rb(r, 0.8), 0, 0, 0)
            m['p3d']['pos'] = place_from(r, ref, d, mr, sr)
            m['hpmax'] = r.choice([20, 100, 40, 1000])
            m['hp'] = r.choice([19, 20, 95, 94, 96, 38, 950, 951, 949, 0, m['hpmax']])
            if r.random() < 0.08:
                m['hpmax'] = r.choice([-1, -20, 0x80000000])
            info['dist'] = d
            info['hp'] = '%d/%d' % (m['hp'], m['hpmax'])
        else:
            rec['prefer'] = r.choice([0, 1])
            how = r.choice(['motionless', 'noattacks', 'reach'])
            info['rating'] = how
            if how == 'motionless':
                m['motionless'] = 1
                rec['prefer'] = 1
            elif how == 'noattacks':
                # every attack rates "not usable": no attack, 0 attack modes, 0 attacks or
                # 0 swings per round
                variant = r.choice(['nohas', 'nomodes', 'apr0', 'spr0'])
                info['variant'] = variant
                if variant == 'nohas':
                    rec['attacks'] = [(0, 0, 1), (0, 1, 3), (0, 0, 0)]
                elif variant == 'nomodes':
                    rec['attacks'] = [(1, r.choice([0, 1, 2]), 0), (r.choice([0, 1]), 1, 0), (0, 0, 0)]
                else:
                    rec['attacks'] = [(1, r.choice([0, 1, 2]), 1), (r.choice([0, 1]), 1, 3), (0, 0, 0)]
                    rec['apr'] = 0 if variant == 'apr0' else max(rec['apr'], 1)
                    rec['spr'] = 0 if variant == 'spr0' else max(rec['spr'], 1)
                rec['prefer'] = 1
            else:
                # usable attacks, nothing reachable: party side stops at the sight check and
                # no hostile monster is listed -> rating 3 (out of reach)
                rec['attacks'] = [(1, r.choice([0, 1, 2, 3]), 1), (r.choice([0, 1]), 1, 2), (0, 0, 0)]
                rec['prefer'] = 1
                m['hpmax'] = r.choice([20, 100, 1000])
                m['hp'] = r.choice([19, 20, 95, 96, 950, 951, m['hpmax']])
                m['cond'][12] = r.choice([0, 0, 2])
                info['hp'] = '%d/%d' % (m['hp'], m['hpmax'])
            # flee: summon rows (distance to player) or rows that stop before collecting
            if r.random() < 0.6:
                rec['fc'] = r.choice([10, 50, 100])
                if r.random() < 0.6:
                    rec['sak'] = r.choice(SUMMON_KINDS)
                    d = near(r, [12500.0], 30000.0)
                    m['p3d']['pos'] = place_from(r, ref, d, mr, sr)
                    info['flee_dist'] = d
                else:
                    rec['sak'] = r.choice(NONSUMMON_KINDS)
                    m['pv_los'] = (m['pv_los'][0], m['pv_los'][1], 0, m['pv_los'][3])
                m['st'] = r.choice([60, 5, 0])
                m['stmax'] = 60
                m['pcombat']['cooldown'] = r.choice([0, 0, 2])
            # spells: only spell 60 (POINT) can be usable; others fail before collecting
            if r.random() < 0.6:
                rec['sc'] = r.choice([5, 50, 100, 255])
                pool = NON_CASTABLE + [0, 0]
                if w.sway_value:
                    pool = pool + FIRE_CASTABLE
                spells = [r.choice(pool) for _ in range(10)]
                if r.random() < 0.6:
                    for _ in range(r.choice([1, 2, 3])):
                        spells[r.randrange(10)] = SUMMON_ELEMENTAL
                rec['spells'] = spells
                m['elemental'] = -1 if r.random() < 0.8 else 3
                if m['p3d']['pos'] == (0.0, 0.0, 0.0):
                    m['p3d']['pos'] = (float(r.randrange(-9000, 9000)), 0.0, float(r.randrange(-9000, 9000)))
    elif scenario == 'spells':
        # ally/enemy spells (collected from listed monsters through mon-to-mon rows; the
        # party side stops at the sight check), the POINT spell 60 and non-castable fillers;
        # usable attacks may reach a listed enemy (rating 0 -> ChooseRandomMonsterAction).
        # No flee except summon rows: the special-attack cone could reach listed enemies.
        m['disp'] = r.choice([1, 1, 2])
        rec['adv'] = 0
        rec['morale'] = r.choice([1, 2, 2, 3])
        rec['behavior'] = r.choice([0, 1, 3])
        rec['flags'] = r.choice([0, 0, 4])
        rec['prefer'] = r.choice([0, 1, 1])
        rec['sc'] = r.choice([20, 60, 100, 255])
        rec['attacks'] = [(1, r.choice([0, 1, 2, 3]), r.choice([1, 3, 0x101])),
                          (r.choice([0, 1]), r.choice([1, 2]), 2), (0, 0, 0)]
        rec['level'] = r.randrange(1, 30)
        if r.random() < 0.3:
            rec['fc'] = r.choice([20, 100])
            rec['sak'] = r.choice(SUMMON_KINDS)
        pool = [s for s in ALLY_SPELLS + ENEMY_SPELLS if SPELL_CAST[s]]
        rec['spells'] = [pick(r, [(60, lambda: r.choice(pool)), (10, SUMMON_ELEMENTAL),
                                  (30, lambda: r.choice(NON_CASTABLE))]) for _ in range(10)]
        m['attrs'] = (50, r.choice([0, 30, 99, 125]), r.choice([10, 80]), 50, 50)
        m['has_spell'] = rb(r, 0.3)
        m['has_proj'] = rb(r, 0.3)
        m['elemental'] = -1 if r.random() < 0.8 else 3
        m['hp'] = r.choice([m['hpmax'], m['hpmax'] // 2, 1])
        m['p3d']['pos'] = (float(r.randrange(-20000, 20000)), 0.0, float(r.randrange(-20000, 20000)))
        info['spells'] = ','.join(str(s) for s in rec['spells'])
    w.add_rec(m['species'], rec)
    k = w.add(m)
    return k, info


def ai_spell_targets(r, w, k, locs, species):
    """Listed allies/enemies for monster k's 'spells' scenario, with mon-to-mon rows and
    distances around the spell/attack range bands."""
    m = w.mons[k]
    cpos = m['p3d']['pos']
    entries = []
    for j in range(r.choice([1, 2, 3])):
        mr = float(r.choice([0, 100, 300]))
        d = near(r, [1000.0, 2000.0, 12500.0, 25000.0], 30000.0)
        o = new_mon(locs[j], species[j], group=m['group'], disp=r.choice([1, 2, 2, 0]),
                    active=rb(r, 0.92), incombat=rb(r, 0.9),
                    hp=0 if r.random() < 0.08 else r.choice([10, 39, 40, 100]), hpmax=100,
                    highest=0 if r.random() < 0.85 else r.choice([0x11, 0x12]),
                    cond={ci: cond_val(r, 0.7) for ci in (3, 4, 6, 7, 11, 13, 15, 16)},
                    ench={e: turns_val(r, 0.7) for e in (2, 3, 4, 5, 6, 7)},
                    st=r.choice([10, 60]), stmax=60,
                    p3d={'pos': place_from(r, cpos, d, mr, m['p3d']['radius']), 'radius': mr})
        orec = sight_record(r)
        orec['untarget'] = 1 if r.random() < 0.1 else 0
        orec['level'] = r.randrange(1, 30)
        w.add_rec(species[j], orec)
        w.add(o)
        if r.random() < 0.85:
            entries.append({'about': locs[j], 'sight': r.choice([1, 1, 1, 0, 2]),
                            'los': tuple(rb(r, 0.75) for _ in range(4))})
    m['vis'] = entries


def ai_world(r, env, c, n_monsters, scenarios):
    w = World(env, c)
    w.cam = rand_cam(r)
    sr = float(r.choice([0, 250, 500]))
    w.nav = ((0.0, 0.0, 0.0), sr, sr)
    w.setg(env.gx + X_COMBAT, p8(rb(r, 0.7)))
    w.setg(env.mipe, p8(1))
    w.sway_value = rb(r, 0.4)
    w.setg(env.sway, p8(w.sway_value))
    w.setg(env.spell_flag, p8(rb(r, 0.3)))
    w.setg(env.flee_flag, p8(rb(r, 0.3)))
    n_extra = 3 * sum(1 for s in scenarios if s == 'spells')
    locs = distinct_locs(r, n_monsters + 2 + n_extra)
    species = distinct_species(r, n_monsters + 2 + n_extra)
    gid = r.randrange(1, 50)
    infos = []
    ks = []
    for k in range(n_monsters):
        kk, info = ai_monster(r, w, env, locs[k], species[k], gid, scenarios[k])
        infos.append(info)
        ks.append(kk)
    base = n_monsters + 2
    for k, s in zip(ks, scenarios):
        if s == 'spells':
            ai_spell_targets(r, w, k, locs[base:base + 3], species[base:base + 3])
            base += 3
    # a listed friendly bystander (same disposition as monster 0: never hostile to it)
    if r.random() < 0.4 and 'spells' not in scenarios:
        b = new_mon(locs[n_monsters + 1], species[n_monsters + 1], group=gid,
                    disp=w.mons[0]['disp'], incombat=rb(r), hp=40)
        w.add_rec(species[n_monsters + 1], sight_record(r))
        w.add(b)
    w.add_group(new_group(gid, [m['loc'] for m in w.mons], engage=rb(r)))
    return w, infos


AI_SCENARIOS = [(10, 'asleep'), (5, 'species224'), (20, 'advance'), (10, 'neutral'), (13, 'ranged'),
                (24, 'rating'), (24, 'spells')]


def gen_update_ai(ctx, env):
    """void UpdateMonsterAI(W8MonsterInfo*) including the inlined MonsterAdvanceChance and
    ChooseMonsterSpell."""
    fn = ctx.fn(0x00531540)
    for i in range(ctx.n(400)):
        r = ctx.rng('update_ai', i)
        c = ctx.case('UpdateMonsterAI.%d' % i, fn, conv='c', ret='v')
        scen = pick(r, AI_SCENARIOS)
        w, infos = ai_world(r, env, c, 1, [scen])
        w.write()
        w.cap_mon(0)
        w.cap_mcs(0)
        cap_flags(c, env)
        finish(c)
        c.arg(env.mon(0))
        c.note(**infos[0])


def gen_update_all_ai(ctx, env):
    """void UpdateAllMonsterAI(void): every listed in-combat monster with hit points."""
    fn = ctx.fn(0x005314f0)
    for i in range(ctx.n(150)):
        r = ctx.rng('update_all_ai', i)
        c = ctx.case('UpdateAllMonsterAI.%d' % i, fn, conv='c', ret='v')
        n = r.choice([1, 2, 3, 3])
        scen = [pick(r, [(20, 'asleep'), (10, 'species224'), (30, 'advance'), (20, 'neutral'),
                         (20, 'rating')]) for _ in range(n)]
        w, infos = ai_world(r, env, c, n, scen)
        for k in range(n):
            m = w.mons[k]
            if r.random() < 0.15:
                m['incombat'] = 0
            elif r.random() < 0.1:
                m['hp'] = 0
        w.write(reserve=2 * n + 2)
        for k in range(n):
            w.cap_mon(k)
            w.cap_mcs(k)
        cap_flags(c, env)
        finish(c)
        c.note(scenarios=','.join(s['scenario'] for s in infos))


# ================================================================ ChooseMonsterRTAIMode
def gen_rtai_mode(ctx, env):
    """bool ChooseMonsterRTAIMode(W8MonsterInfo*, unsigned char* decision): face-party
    proximity, incapacitated groups (allied groups form a chain, no cycles), latched modes,
    pathing cooldown, face-noise yaw test, heard noise reached/being walked to, look-around
    roll and the four order modes with their patrol-point updates."""
    fn = ctx.fn(0x005308C0)
    for i in range(ctx.n(350)):
        r = ctx.rng('rtai_mode', i)
        c = ctx.case('ChooseMonsterRTAIMode.%d' % i, fn, conv='c', ret='b')
        w = World(env, c)
        w.cam = rand_cam(r)
        navpos = (float(r.randrange(-50000, 50000)), float(r.randrange(-2000, 4000)),
                  float(r.randrange(-50000, 50000)))
        w.nav = (navpos, 0.0, 0.0)
        gid = r.randrange(1, 40)
        loc = r.randrange(1, 2000)
        species = r.randrange(N_MONSTERS)
        stage = pick(r, [(12, 'face'), (8, 'incap'), (12, 'latched'), (10, 'cooldown'),
                         (10, 'facenoise'), (12, 'noise'), (10, 'pause'), (26, 'orders')])
        face = rb(r, 0.3)
        pathcd = 0
        line = rb(r, 0.5)
        if stage == 'face':
            face = 1
            pathcd = r.choice([0, 0, 0, 1])
            line = rb(r, 0.85)
        elif stage == 'cooldown':
            pathcd = r.choice([1, 1, 2, 30, 255])
        elif face and line:
            pathcd = r.choice([1, 2]) if stage != 'face' and r.random() < 0.5 else pathcd
        ai_mode = r.choice([0, 1, 4, 6, 7, 8, 10, 0x10, 0x87, 0x86, 0x84, 0x8a, 0x97])
        orders = r.choice([0, 1, 2, 2, 3, 3, 4, -1])
        if stage == 'latched':
            ai_mode = r.choice([0x80, 0x84, 0x86, 0x87, 0x88, 0x8a, 0x97])
        elif ai_mode & 0x80 and stage not in ('latched',):
            ai_mode &= 0x7f
        mpos_from_nav = rb(r, 0.5)
        mr = 0.0
        if mpos_from_nav:
            pos = place_from(r, navpos, near(r, [5000.0], 20000.0), 0.0, 0.0)
        else:
            pos = (float(r.randrange(-50000, 50000)), float(r.randrange(-2000, 4000)),
                   float(r.randrange(-50000, 50000)))
        npts = r.choice([1, 2, 3, 4, 6])
        pts = []
        for _ in range(npts):
            if r.random() < 0.5:
                pts.append(place_from(r, pos, near(r, [1500.0], 6000.0), 0.0, 0.0))
            else:
                pts.append((float(r.randrange(-50000, 50000)), 0.0, float(r.randrange(-50000, 50000))))
        pindex = r.choice([0, 0, 1, 2, npts - 1, npts, 5]) % 128
        vec_cap = npts
        if r.random() < 0.05:
            pts = []
            vec_cap = 0
        noise_radius = 0
        noise_pos = (0.0, 0.0, 0.0)
        stopped = rb(r)
        yaw = f32r(r.uniform(-3.2, 3.2))
        tyaw = yaw
        pause = 0
        if stage == 'facenoise':
            ai_mode = 8
            tyaw = f32r(yaw + r.choice([0.0, 0.0005, 0.000999, 0.001, 0.0011, 0.002, 0.5, -0.0011,
                                        -0.001, float('nan')]))
        # A positive heard-noise radius is only set together with ai_mode == 4 and either
        # "stopped within 1500 of the noise" (the radius is cleared) or "still walking to it":
        # every other combination runs g_octree->TestNoiseLineOfSight against the level.
        if stage == 'noise' or (stage in ('orders', 'pause') and r.random() < 0.15):
            noise_radius = r.choice([1, 100, 5000, 125000, 200000, 0x7fffffff])
            ai_mode = 4
            if r.random() < 0.5:
                stopped = 1
                noise_pos = place_from(r, pos, r.choice([0.0, 100.0, 1499.0, 1499.5, 1000.0]),
                                       0.0, 0.0, exact=True)
            else:
                stopped = 0
                noise_pos = place_from(r, pos, near(r, [1500.0], 5000.0), 0.0, 0.0)
        elif r.random() < 0.15:
            noise_radius = r.choice([0, -1, -5000, -0x80000000])
            noise_pos = place_from(r, pos, near(r, [1500.0], 5000.0), 0.0, 0.0)
        if stage == 'pause' or (noise_radius <= 0 and r.random() < 0.3):
            pause = r.choice([1, 2, 30, 255])
        if stage == 'orders':
            pause = 0
        # incapacitated groups: chain of allies g0 -> g1 -> g2
        n_groups = r.choice([1, 1, 2, 3])
        gids = [gid] + r.sample([g for g in range(40, 80)], n_groups - 1)
        locs = distinct_locs(r, 2 * n_groups + 1)
        mon = new_mon(loc, species, group=gid, pathcd=pathcd, pv_line=line, ai_mode=ai_mode,
                      noise_pos=noise_pos, noise_radius=noise_radius, pause=pause,
                      noise_margin=r.choice([0, 7, 25000]),
                      highest=r.choice([0, 0, 0, 0xd, 0xe, 0x11, 0x12]) if stage == 'incap' else 0,
                      p3d={'pos': pos, 'radius': mr, 'face': face, 'stopped': stopped, 'yaw': yaw,
                           'tyaw': tyaw, 'orders': 1, 'order_mode': orders & 0xff,
                           'points': pts, 'vec_cap': vec_cap, 'pindex': pindex,
                           'dir': (float(r.randrange(-500, 500)), 0.0, float(r.randrange(-500, 500))),
                           'movedir': (1.0, 2.0, 3.0),
                           'formation': (0.0, 0.0, 0.0) if r.random() < 0.5 else pos})
        w.add(mon)
        w.add_rec(species, rand_rec(r))
        li = 0
        for gi in range(n_groups):
            members = [loc] if gi == 0 else []
            for _ in range(r.choice([0, 1, 2])):
                ml = locs[li]
                li += 1
                hc = r.choice([0, 0, 0xd, 0xe, 0x11, 0x12, 0x13]) if stage == 'incap' else 0
                w.add(new_mon(ml, r.randrange(N_MONSTERS), group=gids[gi], highest=hc))
                members.append(ml)
            allies = [0, 0, 0, 0]
            if gi + 1 < n_groups:
                allies[r.randrange(4)] = gids[gi + 1]
            w.add_group(new_group(gids[gi], members, allies=allies))
        w.setg(env.S[5] + DECISION, p8(0xaa))
        w.write()
        w.cap_mon(0)
        w.cap_p3d(0)
        c.cap(env.S[5] + DECISION, 1, 'decision')
        finish(c)
        c.arg(env.mon(0))
        c.arg(env.S[5] + DECISION)
        c.note(stage=stage, ai_mode=ai_mode, order_mode=orders, face=face, pathcd=pathcd,
               noise_radius=noise_radius, stopped=stopped, pause=pause, points=len(pts), pindex=pindex)


# ================================================================ CollectMonsterSpellTargets / AimMonsterAtSpellTarget
def collect_world(r, env, c):
    """World for CollectMonsterSpellTargets: caster 0 casting at allies/enemies/groups/self/
    point; reachable listed monsters through mon-to-mon rows; party slots for enemy-group
    spells (PartyHalfSpellTargetsValid); the caster's party sight is never SEEN."""
    w = World(env, c)
    w.setg(env.gx + X_COMBAT, p8(rb(r, 0.5)))
    w.setg(env.mipe, p8(1))
    w.setg(env.sway, p8(rb(r, 0.2)))
    w.setg(env.spell_flag, p8(rb(r, 0.5)))
    kind = pick(r, [(12, 'caster'), (22, 'ally'), (22, 'enemy'), (22, 'group'), (10, 'area'),
                    (12, 'point')])
    pool = {'caster': CASTER_SPELLS, 'ally': ALLY_SPELLS, 'enemy': ENEMY_SPELLS,
            'group': GROUP_SPELLS, 'area': AREA_SPELLS, 'point': POINT_SPELLS}[kind]
    spell = r.choice(pool)
    if kind == 'group' and r.random() < 0.25:
        spell = 46
    caster_disp = r.choice([1, 1, 2, 0])
    gid0 = r.randrange(1, 30)
    if kind == 'caster':
        n_others = r.choice([0, 1])
    elif kind == 'group':
        n_others = r.choice([1, 2, 2, 3])
    else:
        n_others = r.choice([0, 1, 2, 3, 4])
    locs = distinct_locs(r, n_others + 1)
    species = distinct_species(r, n_others + 1)
    has_spell = rb(r, 0.3)
    caster = new_mon(locs[0], species[0], group=gid0, disp=caster_disp, has_spell=has_spell,
                     pv_sight=r.choice([0, 2]), pv_los=(rb(r), rb(r), rb(r), rb(r)),
                     action=r.choice([-1, 0, 6]), detail=r.choice([0, 9]),
                     pcombat={'reconsider': rb(r)},
                     p3d={'pos': (float(r.randrange(-20000, 20000)), 0.0, float(r.randrange(-20000, 20000)))})
    rec0 = rand_rec(r)
    rec0['untarget'] = 1 if r.random() < 0.1 else 0
    w.add_rec(species[0], rec0)
    w.add(caster)
    if kind == 'area':
        caster['pv_los'] = (caster['pv_los'][0], caster['pv_los'][1], 0, 0)
    sight_idx = 2 + has_spell
    rng = SPELL_RANGE[spell]
    rdist = RANGE_DIST.get(rng, 0.0)
    cpos = caster['p3d']['pos']
    entries = []
    other_groups = {}
    for k in range(1, n_others + 1):
        mr = float(r.choice([0, 100, 300]))
        d = near(r, [rdist], 30000.0)
        pos = place_from(r, cpos, d, mr, 0.0)
        if kind == 'area':
            disp = caster_disp if r.random() < 0.7 else r.choice([0, caster_disp])
        else:
            disp = r.choice([0, 1, 2])
        g = gid0 if r.random() < 0.3 else r.choice([31, 32])
        # (no target-side combat effects: none of the collected spell kinds reads them)
        m = new_mon(locs[k], species[k], group=g, disp=disp, active=rb(r, 0.92),
                    hp=0 if r.random() < 0.08 else r.choice([1, 50, 100]),
                    hpmax=100, highest=0 if r.random() < 0.85 else r.choice([0x11, 0x12, 0x13]),
                    incombat=rb(r, 0.85),
                    cond={ci: cond_val(r, 0.7) for ci in (3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16)},
                    ench={e: turns_val(r, 0.7) for e in (2, 3, 4, 5, 6, 7)},
                    st=r.choice([10, 60]), stmax=60, summoned=r.choice([0, 0, 1]),
                    elemental=r.choice([-1, -1, 2]),
                    p3d={'pos': pos, 'radius': mr})
        rec = sight_record(r)
        rec['faction'] = r.choice([0, 0, rec0['faction']])
        rec['spells'] = [r.randrange(150) if r.random() < 0.5 else 0 for _ in range(10)]
        w.add_rec(species[k], rec)
        w.add(m)
        other_groups.setdefault(g, []).append(locs[k])
        if kind in ('ally', 'enemy') and r.random() < 0.85:
            los = [rb(r, 0.5) for _ in range(4)]
            los[sight_idx] = rb(r, 0.8)
            entries.append({'about': locs[k], 'sight': r.choice([1, 1, 1, 0, 2]), 'los': tuple(los)})
    caster['vis'] = entries if entries else None
    info = {'kind': kind, 'spell': spell, 'others': n_others}
    if kind == 'group':
        # rep stubs for MonsterGroupAllMembersDying; SILENCE asks MonsterIsCycleSupported
        # (virtual) of every eligible member, so those stubs carry the vtable
        rep_alive = w.add_rep(cur=1, anims={CYC_SPELL: r.choice([0, 1, 1])})
        rep_dead = w.add_rep(cur=CYC_DIE)
        for k in range(1, n_others + 1):
            p = w.mons[k]['p3d']
            p['rep'] = rep_dead if r.random() < 0.15 else rep_alive
            if spell == 46:
                p['vtable'] = True
        caster['p3d']['rep'] = rep_alive
        w.add_group(new_group(gid0, [locs[0]] + other_groups.get(gid0, []), disp=caster_disp))
        for g, mem in sorted(other_groups.items()):
            if g == gid0:
                continue
            w.add_group(new_group(g, mem, active=rb(r, 0.9), incombat=rb(r, 0.85)))
        if r.random() < 0.2:
            w.add_group(new_group(36, [], active=1, incombat=1))
        # party for PartyHalfSpellTargetsValid / GetRandomCharacter
        for s in range(8):
            occ, blk, name, cdata = party_member(env, r, p_part=0.7, with_data=True)
            for ci in (3, 4, 5, 6, 8, 9, 11, 12, 14, 15, 16):
                if r.random() < 0.15:
                    blk_u32(blk, C_COND + 4 * ci, cond_val(r, 0.3))
            extra = []
            if spell == 46:
                if s < 2:
                    extra = silence_extras(r, cdata)
                else:
                    occ = 0
            w.slot(s, occ=occ, blk=blk, extra=extra)
    return w, caster, info


def gen_collect(ctx, env, aim):
    if aim:
        fn = ctx.fn(0x005326F0)
        name, n, key = 'AimMonsterAtSpellTarget', 200, 'aim_spell_target'
    else:
        fn = ctx.fn(0x00533320)
        name, n, key = 'CollectMonsterSpellTargets', 300, 'collect_targets'
    for i in range(ctx.n(n)):
        r = ctx.rng(key, i)
        c = ctx.case('%s.%d' % (name, i), fn, conv='c', ret='b' if aim else 'v')
        w, caster, info = collect_world(r, env, c)
        if not aim:
            pre = r.choice([0, 0, 0, 1, 2])
            vb = Blob(0x10)
            vb.u32(4, pre)
            vb.u32(8, VEC_CAP)
            emit(c, env.S[5] + VEC, vb)
            c.setp(env.S[5] + VEC + 0xc, env.S[5] + VEC_DATA)
            if pre:
                junk = Blob(0x20 * pre)
                for t in range(pre):
                    junk.u32(0x20 * t, 7)
                    junk.u32(0x20 * t + 4, t)
                c.set(env.S[5] + VEC_DATA, bytes(junk))
            info['preexisting'] = pre
        w.write()
        w.cap_mon(0)
        if not aim:
            c.cap(env.S[5] + VEC, 0xc, 'targets_hdr')
            c.cap(env.S[5] + VEC_DATA, VEC_CAP * 0x20, 'targets',
                  floats=[0x20 * t + o for t in range(VEC_CAP) for o in (0x10, 0x14, 0x18)])
        finish(c)
        c.arg(env.mon(0))
        c.arg(info['spell'])
        if not aim:
            c.arg(env.S[5] + VEC)
        c.note(**info)


# ================================================================ ChooseRandomMonsterAction
def gen_random_action(ctx, env):
    """bool ChooseRandomMonsterAction(W8MonsterInfo*, bool target_locked, bool attack_locked,
    bool set_attack_rate): BuildMonsterActionQueue (bodyguard protect sweep, wait action,
    stealth rolls, attack candidates against listed monsters) then a random pick. The
    caster's party sight is never SEEN, so no character becomes a candidate."""
    fn = ctx.fn(0x005323F0)
    for i in range(ctx.n(250)):
        r = ctx.rng('random_action', i)
        c = ctx.case('ChooseRandomMonsterAction.%d' % i, fn, conv='c', ret='b')
        w = World(env, c)
        n_others = r.choice([0, 1, 2, 3, 4])
        locs = distinct_locs(r, n_others + 1)
        species = distinct_species(r, n_others + 1, allow_neutral=0.1)
        tl = rb(r, 0.35)
        al = rb(r, 0.3)
        rate = rb(r)
        rec0 = rand_rec(r)
        rec0['flags'] = r.choice([0, 4, 4, 5, 1])
        rec0['morale'] = r.choice([2, 2, 1, 0])
        rec0['behavior'] = r.choice([0, 1, 3])
        rec0['untarget'] = 0
        rec0['attacks'] = [(r.choice([1, 1, 0]), r.choice([0, 1, 2, 3]), r.choice([1, 3, 0x101, 0x1ff, 0])),
                           (r.choice([0, 1]), r.choice([0, 1, 2]), r.choice([1, 6, 0x80])),
                           (r.choice([0, 0, 1]), r.choice([1, 3]), r.choice([2, 0x100]))]
        rec0['apr'] = r.choice([1, 2, 3, 0]) if r.random() < 0.9 else 7
        rec0['spr'] = r.choice([1, 2, 0]) if r.random() < 0.9 else 1
        rec0['level'] = r.randrange(1, 30)
        caster = new_mon(locs[0], species[0], disp=r.choice([1, 1, 2]), active=rb(r, 0.95),
                         incombat=rb(r, 0.9), hp=r.choice([0, 30, 100]) if r.random() < 0.1 else 60,
                         highest=r.choice([0, 0, 0, 3, 0xc]),
                         attrs=(50, r.choice([0, 1, 50, 99, 100, 125]), r.choice([10, 74, 75, 76, 125]),
                                50, 50),
                         pv_sight=r.choice([0, 2]), pv_los=(rb(r), rb(r), rb(r), rb(r)),
                         has_proj=rb(r, 0.3), action=r.choice([-1, 0, 2]), detail=r.choice([0, 7]),
                         oof=rb(r, 0.3),
                         pcombat={'berserk': rb(r, 0.2),
                                  'attack': r.choice([0, 0, 1, 2]) if r.random() < 0.95 else 3,
                                  'apr0': 9, 'apr': 9})
        if tl and not al:
            tk = r.choice(['char', 'monster', 'monster', 'missing', 'other'])
            if tk == 'char':
                slot = r.randrange(8)
                caster['target'] = (1, slot, -1, -1, (0.0, 0.0, 0.0))
                # IsTargetStillPresent -> CanPartySlotParticipate(slot)
                occ, blk, _ = party_member(env, r, p_part=0.7)
                w.slot(slot, occ=occ, blk=blk)
            elif tk == 'monster' and n_others:
                caster['target'] = (3, -1, r.choice(locs[1:]), -1, (0.0, 0.0, 0.0))
            elif tk == 'missing':
                caster['target'] = (3, -1, 4999, -1, (0.0, 0.0, 0.0))
            else:
                caster['target'] = (r.choice([0, 2, 4, 5, 6]), -1, -1, 3, (0.0, 0.0, 0.0))
        cpos = (float(r.randrange(-20000, 20000)), 0.0, float(r.randrange(-20000, 20000)))
        caster['p3d'] = {'pos': cpos, 'radius': 0.0}
        w.add_rec(species[0], rec0)
        w.add(caster)
        entries = []
        for k in range(1, n_others + 1):
            mr = float(r.choice([0, 100, 250]))
            d = near(r, [1000.0, 2000.0, 12500.0, 25000.0], 30000.0)
            pos = place_from(r, cpos, d, mr, 0.0)
            m = new_mon(locs[k], species[k], disp=r.choice([1, 2, 2, 0]), active=rb(r, 0.92),
                        incombat=rb(r, 0.9), hp=0 if r.random() < 0.08 else r.choice([10, 39, 40, 41, 100]),
                        hpmax=100, p3d={'pos': pos, 'radius': mr})
            rec = sight_record(r)
            rec['untarget'] = 1 if r.random() < 0.1 else 0
            rec['level'] = r.randrange(1, 30)
            w.add_rec(species[k], rec)
            w.add(m)
            if r.random() < 0.85:
                entries.append({'about': locs[k], 'sight': r.choice([1, 1, 1, 0, 2]),
                                'los': tuple(rb(r, 0.75) for _ in range(4))})
        caster['vis'] = entries if entries else None
        w.write()
        w.cap_mon(0)
        w.cap_mcs(0)
        finish(c)
        c.arg(env.mon(0))
        c.arg(tl)
        c.arg(al)
        c.arg(rate)
        c.note(target_locked=tl, attack_locked=al, set_rate=rate, others=n_others,
               target_kind=caster['target'][0], bodyguard=int(bool(rec0['flags'] & 4)))


# ================================================================ MonsterGroupCanEngage
def gen_group_can_engage(ctx, env):
    """bool MonsterGroupCanEngage(W8MonsterGroup*): hostile group, a live member with a
    visible hostile party member within reach, then the per-member capability sweep. Members
    that see the party are motionless (skipped by the sweep: their own rating would reach
    the formation code); the waypoint probe is avoided by the move range (0 for close-range
    members) and the special-attack cone collections stay empty."""
    fn = ctx.fn(0x00531920)
    for i in range(ctx.n(200)):
        r = ctx.rng('group_can_engage', i)
        c = ctx.case('MonsterGroupCanEngage.%d' % i, fn, conv='c', ret='b')
        w = World(env, c)
        w.cam = rand_cam(r)
        sr = float(r.choice([0, 250, 500]))
        w.nav = ((0.0, 0.0, 0.0), sr, sr)
        w.setg(env.gx + X_COMBAT, p8(rb(r, 0.6)))
        w.setg(env.mipe, p8(1))
        w.setg(env.sway, p8(rb(r, 0.3)))
        w.setg(env.spell_flag, p8(rb(r, 0.3)))
        w.setg(env.flee_flag, p8(rb(r, 0.3)))
        gid = r.randrange(1, 40)
        # 'designed': member 0 sees a hostile party member within reach and member 1's long
        # attack reaches a hostile outsider (true unless an edge value is hit); otherwise
        # every field is random
        designed = r.random() < 0.45
        n = r.choice([2, 2, 3]) if designed else r.choice([1, 2, 2, 3])
        n_out = 1 if designed or r.random() < 0.8 else 0
        locs = distinct_locs(r, n + n_out)
        species = distinct_species(r, n + n_out)
        ref = player_ref(w.cam)
        rep_alive = w.add_rep(cur=1, anims={CYC_SPELL: 1, CYC_SPECIAL: 1})
        rep_spellless = w.add_rep(cur=1, anims={CYC_SPELL: 0, CYC_SPECIAL: 0})
        rep_dying = w.add_rep(cur=1, pend=CYC_DIE)
        disp = 1 if designed else r.choice([1, 1, 1, 1, 0, 2])
        out_disp = {1: 2, 2: 1}.get(disp, 1) if designed or r.random() < 0.8 else r.choice([0, 1, 2])
        seers = 0
        for k in range(n + n_out):
            rec = sight_record(r)
            rec['untarget'] = 0
            if designed or r.random() < 0.6:
                rec['faction'] = 0
            mr = float(r.choice([0, 100, 300]))
            if designed:
                sees = k == 0 or (k >= 2 and k < n and rb(r, 0.5))
            else:
                sees = r.random() < 0.6 and k < n - 1 or (k == n - 1 and seers == 0 and r.random() < 0.6)
            sure = designed and k <= 1
            m = new_mon(locs[k], species[k], group=gid, disp=disp if k < n else out_disp,
                        active=1 if sure else rb(r, 0.92),
                        hp=80 if sure or r.random() >= 0.08 else 0,
                        highest=0 if sure or r.random() < 0.85 else r.choice([0xc, 0x11, 0x12]),
                        pv_sight=1 if sees else r.choice([0, 2]),
                        pv_los=(rb(r), rb(r), 1 if sees else 0, 0), incombat=1,
                        st=60, stmax=60, pcombat={'cooldown': r.choice([0, 0, 1])},
                        has_proj=rb(r, 0.3))
            rec['sc'] = r.choice([0, 0, 50])
            rec['spells'] = [r.choice(NON_AIMABLE) for _ in range(10)]
            rec['fc'] = r.choice([0, 0, 40])
            rec['sak'] = r.choice(SUMMON_KINDS + NONSUMMON_KINDS)
            if sees:
                # motionless: the capability sweep skips it; its reach decides the first loop
                seers += 1
                m['motionless'] = 1
                rec['fc'] = 0
                th = [monster_reach(rec), ENGAGE_RANGE + ENGAGE_FLOOR]
                if sure:
                    d = th[0] - r.choice([0.0, 0.0, 1.0, 0.5, 300.0, 5000.0, th[0]])
                else:
                    d = near(r, th, th[0] + 30000.0)
                pos = place_from(r, ref, d, mr, sr)
            else:
                m['motionless'] = 0 if sure else rb(r, 0.2)
                if sure or r.random() >= 0.5:
                    rec['attacks'] = [(1, r.choice([2, 3]), r.choice([1, 0x40, 0x1ff])),
                                      (0, 0, 0), (0, 0, 0)]
                    rec['apr'] = max(rec['apr'], 1)
                    rec['spr'] = max(rec['spr'], 1)
                else:
                    rec['attacks'] = [(0, 0, 0), (0, 0, 0), (0, 0, 0)]
                # close-range (or no) attacks probe the waypoint span when the move range
                # times 333.33 exceeds the party distance: a zero move range never does
                if max([-1] + [a[1] for a in rec['attacks'] if a[0]]) <= 1:
                    rec['move'] = 0.0
                pos = place_from(r, ref, near(r, [12500.0, 32500.0], 60000.0), mr, sr)
            if sure:
                rep = rep_alive
            else:
                rep = rep_alive if r.random() < 0.7 else (rep_spellless if r.random() < 0.6 else rep_dying)
            m['p3d'] = {'pos': pos, 'radius': mr, 'rep': rep, 'vtable': True}
            w.add_rec(species[k], rec)
            w.add(m)
        # an outsider (other disposition) that a non-seer member's long attack may reach:
        # RateMonsterBestAttack == 0 makes the group able to engage
        anchors = [k for k in range(n) if not w.mons[k]['motionless'] and
                   dict(w.recs)[w.mons[k]['species']]['attacks'][0][0]]
        reachable = 0
        if n_out and anchors:
            a = 1 if designed else r.choice(anchors)
            arec = dict(w.recs)[w.mons[a]['species']]
            # with a mon-to-mon row its special-attack cone could reach the outsider too
            # (PopulateSpellTargetMarkers): no flee for the anchor
            arec['fc'] = 0
            rng = arec['attacks'][0][1]
            out = w.mons[n]
            if designed:
                out.update(active=1, hp=80, highest=0)
                d = RANGE_DIST[rng] - r.choice([0.0, 0.0, 1.0, 0.5, 2000.0, RANGE_DIST[rng]])
            else:
                d = near(r, [RANGE_DIST[rng]], RANGE_DIST[rng] + 8000.0)
            out['p3d']['pos'] = place_from(r, w.mons[a]['p3d']['pos'], d,
                                           out['p3d']['radius'], w.mons[a]['p3d']['radius'])
            idx = w.mons[a]['has_proj']
            los = [rb(r, 0.4) for _ in range(4)]
            los[idx] = 1 if designed else rb(r, 0.85)
            w.mons[a]['vis'] = [{'about': out['loc'],
                                 'sight': 1 if designed else r.choice([1, 1, 1, 0, 2]),
                                 'los': tuple(los)}]
            reachable = 1
        w.add_group(new_group(gid, locs[:n], disp=disp))
        full_party(w, env, r, sight_only=True, p_part=0.85 if designed else 0.75)
        w.write(reserve=0)
        finish(c)
        c.arg(env.grp(0))
        c.note(designed=int(designed), disp=disp, members=n, seers=seers, outsider_probe=reachable)
