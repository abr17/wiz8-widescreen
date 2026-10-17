"""magic_a: Local Code/Magic.cpp, functions annotated in lines 1-2000.

Tested (retail address, name, cases at --scale 1):
  0x004ff3b0 GetProfessionCasterLevel ............ 220
  0x004ff790 GetSpellDifficulty .................. 260
  0x00500010 CanCastFromItem ..................... 200
  0x004fae70 IsSpellBlockedForCharacter .......... 150
  0x004fb1d0 IsSpellBlockedForMonster ............ 150  (monster + record in scratch, record wired into
                                                         gXStatus.monster_record_cache[999])
  0x005001e0 SpellUsableNow ...................... 300
  0x005010f0 GetTargetNeededForSpellFriendly ..... 250
  0x005011c0 GetTargetNeededForSpellHostile ...... 150
  0x00501860 CanPartySlotReBreathe ............... 150
  0x00500e50 AllSpellEffectsStillRunning ......... 120  (g_spell_effects count/data -> scratch entries)
  0x00500f30 FindMonsterControlSpellEffect ....... 120
  0x00500e90 TickSpellEffects .................... 150  (monster list -> empty scratch PList)
  0x005008a0 AddSpellEffect ......................  60  (capacity >= count+2, never grows)
  0x005012b0 PartyHasCondition ................... 200
  0x00501250 CombatHasCondition .................. 200  (g_combat_state -> scratch / null)
  0x004f9aa0 SetPartySlotSpell ................... 120
  0x00500460 AbsorbMissileDamage ................. 150  (effects/missile/report lists in scratch,
                                                         report capacity big enough: no Grow)
  0x005019a0 DetachMissileReferences ............. 150
  0x00501a60 MissileSpellId ...................... 100
  0x00501d00 IsTeleportCastMissingAnchor ......... 100
  0x00501910 ScaleByCombatPace ................... 250
  0x004ff410 GetSpellFailureChance ............... 350
  0x004ffbd0 GetTotalCasterLevel ................. 250
  0x004f96a0 RecountLearnedSpellsByRealm ......... 150
  0x004f96f0 CharacterHasCastableSpell ........... 200
  0x004ffcb0 CanCharacterLearnSpell .............. 350
  0x004ffe70 LearnSpell (announce=false) ......... 200
  0x005012e0 CanPartySlotCastRecordedSpell ....... 300
  0x00501400 GetAffordableSpellPowerLevel ........ 300
  0x00501660 CanPartySlotUseRecordedItem ......... 250  (monster/group lists -> empty scratch PList)
  0x00500330 ChooseMonsterSpellPowerLevel ........ 250  (Random(4) after the per-case srand)
  0x004ff7f0 GetBestSpellbookSkillForSpell ....... 350
  0x004ff4b0 GetSpellCastRating .................. 300
  0x004fdf30 ChoosePowerLevelForDuration ......... 300
  0x004fe1c0 ChoosePowerLevelToRestore ........... 250
  0x004fe480 ChooseSpellPowerLevelForTarget ...... 300  (monster targets through a scratch monster list)
  0x004f97a0 SpellAimString ...................... 200  (wide string compared)
  total 7850 (37 functions)

Skipped:
  0x004fb0a0 MonsterOKToCastSpell - sets the monster's combat target and asks world range/LOS,
             cursor-node dispatch and neutral-monster area checks (live world positions).
  0x004f9a20 SetCharacterSpell - goes through ChooseAction (combat action state machine, redraws).
  0x00501530 PartySlotSpellTargetStillValid - not in Wiz8Runtime.map (inlined); its body is covered
             through IsSpellTargetStillValidIn in the out-of-combat paths of 0x005012e0/0x00501400.
  0x00501880 StartCharacterBreathAttack - starts an action (ChooseAction/AimAtTarget/StartBreathCycle).
  0x00500930 UpdateSpellEffects - spawns visuals, resolves targets in the world, deletes queue entries.
  0x00500f70 FinishSpellEffect - not in the port map (inlined); casts a spell into the world.
  0x00501590 StartCharacterSpellCast, 0x00501790 StartCharacterItemUse - start actions.
  0x00500060 LearnSpellFromItem - notice line UI, consumes the item, queues a sound event.
  0x004fb220 PointCastSpell - casts a spell into the world.
  0x004faec0 MonsterCastsSpell - notice lines + CastSpellFromSource.
  LearnSpell with announce=true - only the notice line differs (UI); not called.

Inputs never used on purpose (retail reads outside its own data, so both sides differ by design):
  iProfession == -1 together with GetProfessionCasterLevel(.., -1) (table[-1]); spell ids >= 150;
  item id -1 for item-record lookups; spell cost/level giving a cost band < -6 (cast table[6+band]);
  SpellAimString iChar == -1, monster/group targets the world list would have to resolve.
"""
import struct

from w8diff.api import Blob

CHAR = 0x1862
ROW = 0x106
SPELL_REC = 0x1bf
ITEM_REC = 0x10d
SK = 0x26                      # W8CharacterSkill stride

# W8Character
C_PROF, C_RACE, C_GENDER, C_PLEVELS = 0x69, 0x71, 0x75, 0x8d
C_SKILLS = 0x19d
C_COND = 0xa01                 # uiCondition[20]
C_ENCH1_TURNS = 0xa79          # enchantments[1].turns (Dracon breath)
C_HIGHEST = 0xb01
C_HPMAX, C_HP, C_STMAX, C_ST = 0xb0d, 0xb11, 0xb19, 0xb1d
C_SPMAX, C_SPLEFT = 0xb25, 0xb45
C_LEARNED, C_UNLOCKS = 0xbcd, 0xded
C_EQUIP, C_PACK = 0xf5d, 0x1029
C_DEPEND0 = 0x181f             # conditions[0].active (summon binding)
C_ANCHOR = 0x1861              # has_saved_location
# W8PartySlotRow
R_OCC, R_TGT_OOC, R_SPELL, R_POWER, R_SPELL_TGT = 0x0, 0x1d, 0x75, 0x79, 0x81
R_ITEM_DETAIL, R_ITEM_TGT, R_ITEM_ID, R_ITEM_ORIGIN, R_ITEM_SLOT = 0xa1, 0xa9, 0xc9, 0xcd, 0xce
# W8SpellRuntimeRecord
SR_ALCH, SR_COST, SR_DICE, SR_LEVEL = 0x48, 0x49, 0x51, 0x56
SR_PCLASS, SR_REALM, SR_TT, SR_USABLE = 0x12b, 0x133, 0x137, 0x13b
# W8XStatus (gXStatus)
X_COMBAT, X_SPELLCAST, X_ITEMSEL, X_CAMP, X_LOCK, X_TRAP = 0x8dc, 0x8dd, 0x8de, 0x8e3, 0x8e4, 0x8e5
X_MONLIST, X_GROUPLIST, X_RECCACHE = 0x8f5, 0x8f9, 0xa0f
# W8GameSettings
ST_DIFF, ST_AUTOTARGET = 0xd, 0x4e
# W8GlobalStatus
GS_SELECTED, GS_POOL, GS_EFFECTS, GS_MONNAME, GS_SEDEXUS = 0x1d, 0x21, 0x17af, 0x2453, 0x247f
# W8CombatState
CS_ROWS, CS_ROW, CS_PHASE, CS_EFF, CS_EFF0 = 0x18, 0xd4, 0x9c, 0x7c1, 0x85a
# W8MonsterInfo / W8MonsterRecord
MI_LOC, MI_SPECIES, MI_COND, MI_SP = 0x0, 0x8, 0x57, 0x2f9
MR_KIND, MR_NAMEGROUP, MR_RECID, MR_SPBUDGET = 0xcb, 0xcc, 0x187, 0x26f
SPECIES = 999                  # monster_record_cache slot used for the scratch record
# W8SpellEffectEntry / W8Missile
E_MIS_COUNT, E_MIS_CAP, E_MIS_DATA = 0x114, 0x118, 0x11c
E_RES, E_REP_COUNT, E_REP_CAP, E_REP_DATA = 0x126, 0x182, 0x186, 0x18a
M_RES, M_REP_COUNT, M_REP_CAP, M_REP_DATA = 0x280, 0x2dc, 0x2e0, 0x2e4

# SpellTables.dbs (GOG 1.2.4): id: (cost, level, realm, target_type, usable_when, power_class,
#   book mask W1|D2|A4|P8, monster_castable, range, dice base, dice count, dice sides)
SPELLS = {
    0: (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0), 1: (2, 1, 1, 3, 1, 0, 4, 1, 2, 0, 1, 7),
    2: (4, 1, 5, 2, 1, 0, 2, 1, 0, 0, 0, 0), 3: (5, 1, 4, 3, 3, 0, 10, 0, 2, 0, 0, 0),
    4: (2, 1, 1, 3, 1, 0, 1, 1, 2, 0, 1, 7), 5: (2, 1, 0, 3, 1, 0, 1, 1, 2, 0, 1, 7),
    6: (3, 1, 5, 1, 0, 1, 14, 1, 2, 0, 4, 4), 7: (2, 1, 3, 5, 1, 0, 4, 1, 2, 0, 0, 0),
    8: (1, 1, 0, 2, 0, 0, 7, 0, 0, 0, 0, 0), 9: (2, 1, 5, 3, 1, 0, 2, 1, 2, 0, 2, 3),
    10: (3, 1, 4, 3, 1, 0, 8, 1, 2, 1, 1, 7), 11: (3, 1, 1, 3, 1, 0, 10, 1, 2, 0, 0, 0),
    12: (3, 1, 2, 4, 1, 0, 13, 1, 2, 0, 0, 0), 13: (2, 1, 1, 1, 0, 1, 6, 1, 2, 0, 6, 6),
    14: (3, 1, 4, 4, 1, 0, 9, 1, 3, 0, 0, 0), 15: (5, 2, 0, 6, 1, 0, 4, 1, 3, 0, 0, 0),
    16: (4, 2, 1, 1, 0, 1, 14, 1, 2, 0, 0, 0), 17: (5, 2, 4, 2, 2, 0, 9, 0, 0, 0, 0, 0),
    18: (4, 2, 4, 10, 4, 0, 10, 0, 0, 0, 0, 0), 19: (4, 2, 1, 1, 1, 0, 4, 0, 1, 0, 0, 0),
    20: (4, 2, 5, 2, 0, 0, 1, 1, 0, 0, 0, 0), 21: (4, 2, 5, 1, 1, 0, 2, 1, 1, 4, 1, 6),
    22: (5, 2, 1, 6, 1, 0, 2, 0, 2, 0, 2, 5), 23: (6, 2, 4, 9, 2, 2, 10, 0, 0, 0, 0, 0),
    24: (5, 2, 4, 4, 1, 0, 8, 1, 3, 0, 0, 0), 25: (4, 2, 5, 5, 1, 0, 1, 1, 2, 0, 1, 7),
    26: (5, 2, 2, 2, 0, 0, 1, 1, 0, 0, 0, 0), 27: (6, 2, 3, 1, 1, 0, 4, 1, 1, 3, 1, 3),
    28: (3, 2, 2, 5, 1, 0, 9, 1, 2, 0, 1, 5), 29: (4, 2, 1, 4, 1, 0, 8, 1, 3, 0, 0, 0),
    30: (6, 2, 2, 6, 0, 0, 5, 0, 3, 0, 0, 0), 31: (5, 2, 3, 5, 1, 0, 3, 1, 2, 0, 0, 0),
    32: (6, 3, 3, 2, 0, 0, 2, 1, 0, 0, 0, 0), 33: (6, 3, 3, 2, 2, 0, 12, 0, 0, 0, 0, 0),
    34: (6, 3, 1, 1, 0, 1, 6, 1, 2, 0, 0, 0), 35: (6, 3, 2, 1, 0, 1, 6, 1, 2, 0, 0, 0),
    36: (6, 3, 0, 6, 1, 0, 1, 1, 3, 0, 2, 4), 37: (6, 3, 1, 4, 1, 0, 1, 1, 3, 0, 0, 0),
    38: (5, 3, 0, 8, 0, 0, 8, 0, 3, 0, 0, 0), 39: (6, 3, 3, 10, 4, 0, 5, 0, 0, 0, 0, 0),
    40: (6, 3, 5, 2, 0, 0, 2, 1, 0, 0, 0, 0), 41: (8, 3, 4, 3, 3, 0, 8, 0, 2, 0, 0, 0),
    42: (5, 3, 2, 6, 1, 0, 5, 1, 3, 0, 1, 6), 43: (6, 3, 0, 5, 1, 0, 8, 1, 2, 0, 2, 5),
    44: (6, 3, 1, 2, 0, 1, 2, 1, 0, 0, 6, 6), 45: (5, 3, 2, 2, 2, 0, 1, 0, 0, 0, 0, 0),
    46: (4, 3, 2, 4, 1, 0, 10, 1, 3, 0, 0, 0), 47: (6, 3, 3, 5, 1, 0, 5, 1, 2, 0, 2, 5),
    48: (8, 4, 1, 6, 1, 0, 4, 1, 3, 0, 1, 6), 49: (8, 4, 3, 5, 1, 0, 9, 1, 2, 0, 0, 0),
    50: (8, 4, 3, 3, 1, 0, 5, 1, 3, 0, 2, 15), 51: (8, 4, 1, 1, 0, 1, 6, 0, 2, 0, 0, 0),
    52: (8, 4, 4, 5, 1, 0, 8, 1, 2, 0, 2, 7), 53: (8, 4, 3, 2, 1, 0, 5, 1, 0, 0, 0, 0),
    54: (7, 4, 5, 1, 1, 0, 8, 1, 1, 0, 0, 0), 55: (8, 4, 0, 6, 1, 0, 4, 1, 3, 0, 2, 5),
    56: (8, 4, 0, 2, 1, 0, 8, 1, 0, 0, 0, 0), 57: (8, 4, 1, 6, 1, 0, 1, 1, 3, 0, 2, 5),
    58: (8, 4, 5, 1, 0, 2, 3, 0, 1, 0, 0, 0), 59: (6, 4, 5, 2, 1, 0, 10, 1, 0, 0, 0, 0),
    60: (12, 5, 5, 8, 1, 0, 5, 1, 1, 0, 0, 0), 61: (7, 4, 1, 1, 1, 0, 2, 1, 1, 0, 0, 0),
    62: (10, 4, 0, 2, 1, 0, 4, 0, -1, 0, 1, 6), 63: (7, 4, 2, 5, 1, 0, 2, 1, 2, 0, 2, 4),
    64: (9, 4, 4, 2, 2, 0, 1, 0, 0, 0, 0, 0), 65: (8, 5, 3, 1, 1, 0, 4, 1, 1, 0, 0, 0),
    66: (10, 5, 1, 3, 1, 0, 1, 1, 3, 0, 2, 19), 67: (12, 5, 1, 7, 1, 0, 1, 1, 3, 0, 3, 10),
    68: (10, 5, 5, 2, 0, 1, 2, 1, 0, 0, 4, 4), 69: (10, 5, 4, 6, 1, 0, 9, 1, 3, 0, 0, 0),
    70: (10, 5, 5, 3, 1, 0, 10, 1, 3, 0, 0, 0), 71: (10, 5, 4, 4, 1, 0, 8, 1, 3, 0, 2, 7),
    72: (10, 5, 2, 2, 1, 0, 6, 1, 0, 0, 0, 0), 73: (50, 5, 2, 0, 2, 3, 15, 0, 0, 0, 0, 0),
    74: (12, 5, 4, 1, 0, 1, 10, 1, 2, 0, 0, 0), 75: (30, 5, 2, 0, 2, 3, 15, 0, 0, 0, 0, 0),
    76: (8, 5, 2, 6, 1, 0, 4, 1, 3, 0, 1, 4), 77: (10, 6, 5, 7, 1, 0, 3, 1, 3, 0, 3, 9),
    78: (12, 6, 1, 5, 1, 0, 1, 1, 2, 0, 2, 9), 79: (12, 6, 0, 3, 1, 0, 4, 1, 3, 0, 2, 19),
    80: (10, 6, 5, 6, 1, 0, 4, 1, 3, 0, 1, 5), 81: (12, 6, 0, 6, 1, 0, 1, 1, 3, 0, 2, 4),
    82: (12, 6, 5, 3, 1, 0, 2, 0, 2, 0, 4, 4), 83: (12, 6, 0, 5, 1, 0, 2, 1, 2, 0, 2, 8),
    84: (12, 6, 5, 3, 1, 0, 8, 1, 2, 0, 3, 9), 85: (12, 6, 2, 7, 1, 0, 8, 1, 3, 0, 0, 0),
    86: (10, 6, 0, 5, 1, 0, 8, 1, 2, 0, 2, 8), 87: (15, 6, 3, 6, 1, 0, 4, 1, 3, 0, 0, 0),
    88: (30, 6, 5, 1, 0, 3, 6, 0, 1, 0, 0, 0), 89: (12, 6, 4, 3, 1, 0, 9, 1, 2, 0, 0, 0),
    90: (20, 7, 2, 7, 1, 0, 1, 1, 3, 0, 0, 0), 91: (12, 7, 4, 3, 1, 0, 8, 1, 3, 0, 2, 24),
    92: (12, 7, 4, 3, 1, 0, 1, 1, 3, 0, 2, 24), 93: (20, 7, 2, 6, 1, 0, 4, 1, 3, 0, 0, 0),
    94: (20, 7, 5, 7, 1, 0, 2, 1, 3, 0, 0, 0), 95: (18, 7, 3, 7, 1, 0, 4, 1, 3, 0, 3, 7),
    96: (16, 7, 3, 7, 1, 0, 2, 1, 3, 0, 2, 8), 97: (18, 7, 4, 7, 1, 0, 8, 1, 3, 0, 3, 7),
    98: (18, 7, 0, 7, 1, 0, 1, 1, 3, 0, 3, 7), 99: (15, 7, 0, 7, 1, 0, 8, 1, 3, 0, 3, 9),
    100: (16, 7, 5, 1, 0, 1, 2, 0, 2, 0, 8, 8), 101: (15, 7, 1, 5, 1, 0, 4, 1, 2, 0, 3, 9),
    114: (0, 1, 3, 1, 0, 3, 0, 0, 1, 0, 4, 4), 115: (0, 1, 5, 1, 0, 3, 0, 0, 1, 0, 4, 14),
    116: (0, 1, 2, 1, 0, 3, 0, 0, 2, 0, 0, 0), 117: (3, 1, 4, 7, 1, 0, 0, 0, 3, 0, 0, 0),
    118: (0, 6, 0, 6, 1, 0, 0, 0, -1, 2, 1, 5), 119: (0, 0, 1, 5, 1, 3, 0, 1, 2, 0, 0, 0),
    120: (20, 7, 5, 1, 0, 3, 0, 0, 1, 0, 0, 0), 121: (2, 1, 3, 4, 0, 0, 0, 0, 2, 0, 1, 7),
    122: (2, 1, 1, 4, 0, 0, 0, 0, 2, 0, 1, 4), 123: (6, 2, 2, 8, 0, 0, 0, 0, 3, 0, 0, 0),
    124: (10, 5, 3, 4, 0, 0, 0, 0, 1, 60, 1, 7), 125: (10, 5, 1, 4, 0, 0, 0, 0, 0, 0, 1, 4),
    126: (12, 6, 2, 4, 0, 0, 0, 0, 1, 0, 0, 0), 127: (14, 7, 5, 4, 0, 3, 0, 0, 1, 0, 0, 0),
    128: (14, 7, 4, 4, 0, 0, 0, 0, 1, 0, 0, 0), 129: (5, 2, 5, 7, 1, 0, 0, 0, 2, 0, 2, 5),
    130: (20, 7, 5, 0, 0, 0, 0, 0, 0, 0, 5, 5), 131: (2, 1, 0, 6, 0, 0, 0, 0, 3, 0, 3, 6),
}
for _k in range(102, 114):
    SPELLS[_k] = (0,) * 12           # reserved records
SPELLS[149] = (0,) * 12              # Retired Spell
ALL_SPELLS = sorted(SPELLS)          # every valid record index used (0..131, 149)
REAL_SPELLS = [k for k in range(1, 132) if SPELLS[k][1] or SPELLS[k][0]]
BOOK_SPELLS = [k for k in range(1, 102) if SPELLS[k][6]]
MONSTER_SPELLS = [k for k in ALL_SPELLS if SPELLS[k][7]]
RESTORE_SPELLS = [6, 13, 100]
DURATION_SPELLS = [16, 34, 35, 51, 74, 58]

ITEM_COUNT = 819
# Items.dbs: spell-source (category 3) items -> taught spell
SOURCE_ITEMS = {
    368: 44, 369: 26, 370: 39, 371: 17, 372: 56, 374: 2, 375: 3, 378: 58, 379: 77, 382: 23, 426: 18,
    437: 8, 438: 16, 439: 1, 440: 6, 441: 7, 442: 12, 443: 13, 444: 5, 445: 4, 447: 14, 448: 9,
    449: 11, 475: 15, 476: 10, 477: 19, 478: 20, 479: 21, 480: 22, 481: 24, 482: 25, 483: 27,
    484: 28, 515: 29, 516: 30, 517: 31, 518: 32, 519: 33, 520: 34, 521: 35, 522: 36, 523: 37,
    524: 38, 525: 40, 526: 41, 527: 42, 528: 43, 529: 45, 530: 46, 531: 47, 532: 48, 533: 49,
    534: 50, 535: 51, 536: 52, 537: 53, 538: 54, 539: 55, 540: 57, 541: 59, 542: 60, 543: 61,
    544: 62, 545: 63, 546: 64, 547: 65, 548: 66, 549: 67, 550: 68, 551: 69, 552: 70, 553: 71,
    554: 72, 555: 73, 556: 74, 557: 75, 558: 76,
}
# items carrying a spell outside category 0/3 (wands, potions, scrolls of use, ...)
USABLE_ITEMS = [
    16, 19, 24, 27, 33, 34, 42, 43, 44, 46, 47, 60, 61, 68, 69, 74, 81, 85, 86, 87, 88, 100, 101,
    102, 107, 108, 109, 254, 255, 256, 257, 258, 259, 260, 262, 263, 264, 265, 269, 273, 276, 277,
    278, 280, 282, 285, 286, 287, 292, 304, 305, 306, 310, 317, 320, 321, 322, 323, 324, 325, 326,
    327, 328, 329, 330, 331, 332, 334, 335, 336, 337, 338, 339, 340, 341, 342, 343, 344, 345, 346,
    347, 348, 349, 350, 351, 352, 353, 354, 355, 356, 357, 358, 359, 360, 361, 362, 363, 364, 373,
    376, 377, 380, 381, 383, 384, 385, 386, 387, 388, 389, 390, 391, 392, 393, 394, 395, 396, 397,
    398, 399, 400, 401, 402, 403, 404, 405, 406, 407, 408, 409, 410, 411, 412, 414, 416, 417, 418,
    419, 425, 428, 429, 432, 464, 465, 466, 469, 474, 488, 492, 496, 499, 501, 565, 584, 585, 586,
    587, 590, 591, 592, 593, 597, 598, 659, 669, 675, 682, 683, 684, 685, 686, 687, 688, 689, 690,
    691, 692, 693, 694, 695, 696, 697, 698, 699, 700, 701, 702, 709, 726, 738, 741, 742, 743, 744,
    753, 755, 770, 772, 789, 804, 812, 818,
]
# binds-on-equip items (with their identify difficulty spread 0..18)
BIND_ITEMS = [4, 5, 15, 29, 33, 43, 48, 71, 73, 74, 85, 86, 89, 145, 149, 160, 168, 179, 195, 205,
              208, 217, 228, 234, 238, 245, 277, 291, 305, 313, 463, 469, 660, 674, 755, 775, 781,
              791, 798, 818]
MONSTER_BUDGETS = [14, 18, 20, 22, 24, 25, 28, 30, 32, 36, 40, 45, 50, 60, 70, 75, 80, 84, 90,
                   100, 120, 150, 200, 300, 1, 2, -842150451, -5]
CONDITION_IDS = [2, 4, 6, 7, 9, 11, 12, 13, 15, 16]


def u32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def u16(v):
    return struct.pack('<H', int(v) & 0xffff)


def u8(v):
    return bytes([int(v) & 0xff])


def rd(data, off):
    return struct.unpack_from('<i', data, off)[0]


def sk(sid, field):
    return C_SKILLS + SK * sid + {'active': 0, 'points': 2, 'level': 6}[field]


def slot_bytes(kind, ichar=-1, mon=-1, grp=-1, pt=(0.0, 0.0, 0.0), item=0):
    return struct.pack('<iiiifffI', kind, ichar, mon, grp, pt[0], pt[1], pt[2], item & 0xffffffff)


def item_bytes(item_id, stack=1, charges=0, identified=1, bind_announced=0):
    return struct.pack('<iBBBBBBBB', item_id, stack, charges, identified, 0, 0, 0, bind_announced, 0)


def effslot(active, eid, amount=0, pct=0, dur=0):
    return struct.pack('<BIIII', active & 0xff, eid & 0xffffffff, amount & 0xffffffff,
                       pct & 0xffffffff, dur & 0xffffffff)


def ctrunc_half(v):
    return int(v / 2)


class G:
    """Addresses resolved in each exe."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.gx = ctx.g('gXStatus')
        self.st = ctx.g('g_status')
        self.settings = ctx.g('g_settings')
        self.screen = ctx.g('g_current_screen_state')
        self.level_block = ctx.g('g_level_block')
        self.combat = ctx.g('g_combat_state')
        self.effects = ctx.g('g_spell_effects')
        self.spells = ctx.g('g_spell_records').deref()
        self.items = ctx.g('g_item_records').deref()
        self.S = [ctx.scratch(k) for k in range(8)]

    def char(self, s):
        return self.ctx.char(s)

    def row(self, s):
        return (self.st + 8).deref() + s * ROW

    def spell(self, sid):
        return self.spells + sid * SPELL_REC

    def item(self, iid):
        return self.items + iid * ITEM_REC


def learned_spells(data):
    return [k for k in range(1, 0x72) if rd(data, C_LEARNED + 4 * k) == 1]


def party(ctx, c, r, focus=None, pool=None):
    """8 party slots from the corpus (setb); the focus slot from pool when given."""
    out = []
    for s in range(8):
        src = pool if (s == focus and pool) else ctx.corpus
        name, data = src[r.randrange(len(src))]
        c.setb(ctx.char(s), data)
        out.append((name, Blob(data)))
    return out


def set_modes(c, g, r, combat=None, camp=None, lock=None, trap=None, screen=None):
    combat = (r.random() < 0.45) if combat is None else combat
    camp = (r.random() < 0.2) if camp is None else camp
    lock = (r.random() < 0.15) if lock is None else lock
    trap = (r.random() < 0.15) if trap is None else trap
    screen = r.choice([7, 7, 7, 6, 3]) if screen is None else screen
    c.set(g.gx + X_COMBAT, u8(combat))
    c.set(g.gx + X_CAMP, u8(camp))
    c.set(g.gx + X_LOCK, u8(lock) + u8(trap))
    c.set(g.screen, u32(screen))
    return dict(combat=int(combat), camp=int(camp), lock=int(lock), trap=int(trap), screen=screen)


def pace_value(r):
    return r.choice([0, 1, 39, 40, 41, 59, 60, 61, 79, 80, 81, 100, 150, 255, 1000, 0x7fffffff,
                     0xffffffff] + [r.randrange(0, 200)] * 6)


def set_pace(c, g, r, slot, combat=None):
    """fCombatMode, difficulty and a scratch combat state carrying the slot's pace."""
    combat = (r.random() < 0.5) if combat is None else combat
    diff = r.choice([0, 1, 2] * 10 + [3, -1])
    phase = pace_value(r)
    c.set(g.gx + X_COMBAT, u8(combat))
    c.set(g.settings + ST_DIFF, u32(diff))
    c.set(g.S[6] + CS_ROWS + slot * CS_ROW + CS_PHASE, u32(phase))
    c.setp(g.combat, g.S[6])
    return dict(combat=int(combat), diff=diff, phase=phase)


def mutate_spell(c, g, r, sp, p, fields=('cost', 'level')):
    """Change the spell record (restored after the case)."""
    out = {}
    if r.random() >= p:
        return out
    if 'cost' in fields and r.random() < 0.7:
        v = r.choice([0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 30, 50, 99, -1, -2, -3])
        c.set(g.spell(sp) + SR_COST, u32(v))
        out['cost'] = v
    if 'level' in fields and r.random() < 0.7:
        v = r.choice([0, 1, 2, 3, 4, 5, 6, 7, 8, 10, -1])
        c.set(g.spell(sp) + SR_LEVEL, u32(v))
        out['level'] = v
    if 'tt' in fields and r.random() < 0.5:
        v = r.choice(list(range(11)) + [7, 7, 9, 10])
        c.set(g.spell(sp) + SR_TT, u32(v))
        out['tt'] = v
    return out


def modify_magic_skills(c, ch, r, p=0.6):
    """Random changes to the spellbook (0x18..0x1b) and realm (0x1c..0x21) skills."""
    if r.random() >= p:
        return
    for _ in range(r.randint(1, 6)):
        sid = r.randrange(0x18, 0x22)
        field = r.choice(['points', 'level', 'level', 'active'])
        if field == 'active':
            c.set(ch + sk(sid, field), u8(r.randrange(2)))
        else:
            v = r.choice([0, 0, 1, 5, 10, 15, 20, 30, 45, 50, 60, 75, 90, 99, 100, 110, 125] +
                         [r.randrange(0, 126)] * 4 + ([0xffffffff, 0x80000000] if r.random() < 0.1 else []))
            c.set(ch + sk(sid, field), u32(v))


def modify_professions(c, ch, r, p=0.3):
    if r.random() >= p:
        return None
    prof = r.randrange(15)
    c.set(ch + C_PROF, u32(prof))
    levels = [0] * 15
    levels[prof] = r.choice([0, 1, 2, 3, 5, 8, 10, 12, 14, 16, 20, 25, 30])
    for _ in range(r.randint(0, 3)):
        levels[r.randrange(15)] = r.choice([0, 1, 3, 5, 8, 12, 20])
    c.set(ch + C_PLEVELS, b''.join(u32(v) for v in levels))
    return prof


# --------------------------------------------------------------------------------------------

def gen_prof_caster_level(ctx, g):
    fn = ctx.fn(0x004ff3b0)
    for i in range(ctx.n(220)):
        r = ctx.rng('pcl', i)
        c = ctx.case('prof_caster_level.%d' % i, fn, conv='c', ret='i')
        ps = party(ctx, c, r)
        s = r.randrange(8)
        ch = g.char(s)
        arg = r.choice([-1, -1, -1, -1] + list(range(15)))
        prof = rd(ps[s][1], C_PROF)
        if r.random() < 0.5:
            prof = r.randrange(15)
            if arg != -1 and r.random() < 0.15:
                prof = -1
            c.set(ch + C_PROF, u32(prof))
        if prof == -1 and arg == -1:
            arg = r.randrange(15)
        if r.random() < 0.6:
            levels = [r.choice([0, 0, 0, 0, 1, 2, 5, 8, 10, 14, 16, 20, 25, 30, 50, -1, -4, -100,
                                0x7fffffff, 0x80000000]) for _ in range(15)]
            c.set(ch + C_PLEVELS, b''.join(u32(v) for v in levels))
        c.arg(ch)
        c.arg(arg)
        c.note(char=ps[s][0], slot=s, prof=prof, arg=arg)


def gen_spell_difficulty(ctx, g):
    fn = ctx.fn(0x004ff790)
    for i in range(ctx.n(260)):
        r = ctx.rng('sdiff', i)
        c = ctx.case('spell_difficulty.%d' % i, fn, conv='c', ret='i')
        sp = r.choice(ALL_SPELLS)
        mut = mutate_spell(c, g, r, sp, 0.35, ('cost', 'level', 'tt'))
        figure = r.choice([0, 1, 2, 3, 4, 5, 10, 25, 50, 75, 100, 125, 200, 0x7ffffffe, 0xffffffff,
                           0x80000000] + [r.randrange(0, 250)] * 5)
        bonus = r.choice([-1000, -100, -10, -5, -4, -3, -2, -1, 0, 0, 0, 1, 2, 3, 5, 10, 100,
                          0x7fffffff, -0x80000000] + [r.randrange(-30, 31)] * 5)
        c.arg(figure)
        c.arg(sp)
        c.arg(bonus)
        c.note(spell=sp, figure=figure, bonus=bonus, **mut)


def gen_can_cast_from_item(ctx, g):
    fn = ctx.fn(0x00500010)
    src = sorted(SOURCE_ITEMS)
    for i in range(ctx.n(200)):
        r = ctx.rng('ccfi', i)
        c = ctx.case('can_cast_from_item.%d' % i, fn, conv='c', ret='b')
        ps = party(ctx, c, r)
        s = r.randrange(8)
        ch = g.char(s)
        item_id = r.choice(src) if r.random() < 0.75 else r.randrange(ITEM_COUNT)
        ident = 1 if r.random() < 0.8 else 0
        c.set(g.S[0], item_bytes(item_id, r.choice([1, 1, 2]), r.choice([0, 1]), ident))
        if item_id in SOURCE_ITEMS and r.random() < 0.6:
            c.set(ch + C_LEARNED + 4 * SOURCE_ITEMS[item_id], u32(r.choice([0, 0, 1, -1, 2])))
        if r.random() < 0.3:
            c.set(ch + C_PROF, u32(r.randrange(15)))
        if r.random() < 0.2:
            c.set(ch + C_RACE, u32(r.randrange(11)) + u32(r.randrange(2)))
        c.arg(ch)
        c.arg(g.S[0])
        c.note(char=ps[s][0], item=item_id, identified=ident)


def gen_blocked_for_character(ctx, g):
    fn = ctx.fn(0x004fae70)
    for i in range(ctx.n(150)):
        r = ctx.rng('sbc', i)
        c = ctx.case('blocked_for_character.%d' % i, fn, conv='c', ret='b')
        ps = party(ctx, c, r)
        s = r.randrange(8)
        ch = g.char(s)
        silence = r.choice([0, 0, 1, 2, 5, 9999, 0x80000000, r.randrange(1, 40)])
        c.set(ch + C_COND + 4 * 8, u32(silence))
        if r.random() < 0.7:
            c.set(ch + sk(0x1a, 'level'), u32(r.choice([0, 0, 1, 10, 50, 0x80000000])))
        sp = r.choice(ALL_SPELLS)
        if r.random() < 0.2:
            c.set(g.spell(sp) + SR_ALCH, u8(r.choice([0, 1, 2, 0xff])))
        c.arg(ch)
        c.arg(sp)
        c.note(char=ps[s][0], spell=sp, silenced=silence)


def wire_record(c, g, rec):
    c.setp(g.gx + X_RECCACHE + 4 * SPECIES, rec)


def wire_monster_list(c, g, monsters):
    """gXStatus.plsMonsterList -> scratch PList (S5) holding the given monster infos."""
    pl = g.S[5]
    arr = g.S[5] + 0x40
    for k, m in enumerate(monsters):
        c.setp(arr + 4 * k, m)
    if monsters:
        c.set(pl + 4, u32(len(monsters)) + u32(len(monsters)))
        c.setp(pl, arr)
    c.setp(g.gx + X_MONLIST, pl)


def gen_blocked_for_monster(ctx, g):
    fn = ctx.fn(0x004fb1d0)
    for i in range(ctx.n(150)):
        r = ctx.rng('sbm', i)
        c = ctx.case('blocked_for_monster.%d' % i, fn, conv='c', ret='b')
        mi, rec = g.S[1], g.S[2]
        silence = r.choice([0, 0, 1, 3, 9999, 0x80000000, r.randrange(1, 20)])
        kind = r.choice(list(range(32)) + [4, 5, 13] * 5 + [3, 6, 12, 14, 255])
        c.set(mi + MI_SPECIES, u32(SPECIES))
        c.set(mi + MI_COND + 4 * 8, u32(silence))
        c.set(rec + MR_KIND, u8(kind))
        wire_record(c, g, rec)
        sp = r.choice(ALL_SPELLS)
        if r.random() < 0.2:
            c.set(g.spell(sp) + SR_ALCH, u8(r.choice([0, 1, 2, 0xff])))
        c.arg(mi)
        c.arg(sp)
        c.note(spell=sp, silenced=silence, kind=kind)


def gen_spell_usable_now(ctx, g):
    fn = ctx.fn(0x005001e0)
    for i in range(ctx.n(300)):
        r = ctx.rng('sun', i)
        c = ctx.case('spell_usable_now.%d' % i, fn, conv='c', ret='b')
        modes = set_modes(c, g, r, screen=r.choice([6, 6, 7, 7, 7, 3, 0, 8]))
        sp = r.choice(ALL_SPELLS + [23, 58, 39, 18] * 6)
        allow = r.randrange(2)
        uw = None
        if r.random() < 0.15:
            uw = r.choice([0, 1, 2, 3, 4, 5, 6, -1, 0x100])
            c.set(g.spell(sp) + SR_USABLE, u32(uw))
        c.arg(sp)
        c.arg(allow)
        c.note(spell=sp, allow=allow, usable_when=uw, **modes)


def gen_target_needed_friendly(ctx, g):
    fn = ctx.fn(0x005010f0)
    for i in range(ctx.n(250)):
        r = ctx.rng('tnf', i)
        c = ctx.case('target_needed_friendly.%d' % i, fn, conv='c', ret='i')
        sp = r.choice(ALL_SPELLS + [88, 23, 6, 13] * 4)
        lb = r.random() < 0.6
        if lb:
            c.setp(g.level_block, g.S[7])
        else:
            c.set(g.level_block, u32(0))
        tt = None
        if r.random() < 0.25:
            tt = r.choice(list(range(11)) + [9, 9, 11, 12, -1, 0x7fffffff])
            c.set(g.spell(sp) + SR_TT, u32(tt))
        normalize = r.randrange(2)
        context = r.choice(list(range(9)) + [3, 4, 3, 4])
        c.arg(sp)
        c.arg(normalize)
        c.arg(context)
        c.note(spell=sp, normalize=normalize, context=context, level_block=int(lb), tt=tt)


def gen_target_needed_hostile(ctx, g):
    fn = ctx.fn(0x005011c0)
    for i in range(ctx.n(150)):
        r = ctx.rng('tnh', i)
        c = ctx.case('target_needed_hostile.%d' % i, fn, conv='c', ret='i')
        sp = r.choice([k for k in ALL_SPELLS if SPELLS[k][3] <= 8] + [88] * 3)
        tt = None
        if r.random() < 0.25:
            tt = r.choice(list(range(11)) + [11, -1])
            c.set(g.spell(sp) + SR_TT, u32(tt))
        c.arg(sp)
        c.note(spell=sp, tt=tt)


def gen_can_rebreathe(ctx, g):
    fn = ctx.fn(0x00501860)
    for i in range(ctx.n(150)):
        r = ctx.rng('crb', i)
        c = ctx.case('can_rebreathe.%d' % i, fn, conv='c', ret='b')
        ps = party(ctx, c, r)
        s = r.randrange(8)
        ch = g.char(s)
        if r.random() < 0.4:
            c.set(ch + C_RACE, u32(7))           # Dracon
        if r.random() < 0.3:
            c.set(ch + C_ENCH1_TURNS, u32(r.choice([0, 1, 5, 0xffffffff])))
        if r.random() < 0.8:
            smax = r.choice([0, 1, 4, 5, 6, 9, 10, 99, 100, 101, 250, 500, -1, -5, 0x7fffffff,
                             0x80000000])
            st = r.choice([0, 1, smax // 5 if smax > 0 else 0, smax // 5 - 1 if smax > 0 else -1,
                           smax // 5 + 1 if smax > 0 else 1, smax, -1, -100, 0x7fffffff])
            c.set(ch + C_STMAX, u32(smax))
            c.set(ch + C_ST, u32(st))
        c.arg(s)
        c.note(char=ps[s][0], slot=s)


def wire_effect_entries(c, g, entries, count=None):
    eff, arr = g.S[3], g.S[4]
    for k, (kind, turns) in enumerate(entries):
        c.set(eff + 0x200 * k, u32(kind) + u32(turns))
        c.setp(arr + 4 * k, eff + 0x200 * k)
    c.set(g.effects + 4, u32(len(entries) if count is None else count))
    c.setp(g.effects + 0xc, arr)


def gen_all_effects_running(ctx, g):
    fn = ctx.fn(0x00500e50)
    for i in range(ctx.n(120)):
        r = ctx.rng('aser', i)
        c = ctx.case('all_effects_running.%d' % i, fn, conv='c', ret='b')
        n = r.choice([0, 1, 1, 2, 3, 4, 5, 6, 8, 10, 12])
        pz = r.choice([0.0, 0.05, 0.15, 0.4])
        entries = [(r.choice([38, 2, 60, 79, 6, r.randrange(150)]),
                    0 if r.random() < pz else r.choice([1, 2, 3, 10, 0xffffffff, 0x80000000]))
                   for _ in range(n)]
        count = None
        if n == 0 and r.random() < 0.5:
            count = r.choice([-1, -5])
        wire_effect_entries(c, g, entries, count)
        c.note(entries=entries, count=count)


def gen_find_control_effect(ctx, g):
    fn = ctx.fn(0x00500f30)
    for i in range(ctx.n(120)):
        r = ctx.rng('fmce', i)
        c = ctx.case('find_control_effect.%d' % i, fn, conv='c', ret='p', out='p')
        n = r.choice([0, 1, 2, 3, 4, 6, 9])
        p38 = r.choice([0.0, 0.2, 0.5])
        entries = [(38 if r.random() < p38 else r.choice([37, 39, 0x126, 2, r.randrange(150)]),
                    r.choice([0, 1, 5])) for _ in range(n)]
        count = None
        if n == 0 and r.random() < 0.4:
            count = -1
        wire_effect_entries(c, g, entries, count)
        c.note(entries=entries, count=count)


def gen_tick_effects(ctx, g):
    fn = ctx.fn(0x00500e90)
    for i in range(ctx.n(150)):
        r = ctx.rng('tse', i)
        c = ctx.case('tick_effects.%d' % i, fn, conv='c', ret='v')
        n = r.choice([0, 1, 1, 2, 3, 4, 5, 7, 10])
        entries = [(r.choice([38, 38, 2, 60, 79, r.randrange(150)]),
                    r.choice([0, 1, 1, 2, 3, 10, 0xffffffff, 0x80000000])) for _ in range(n)]
        wire_effect_entries(c, g, entries)
        c.setp(g.gx + X_MONLIST, g.S[5])     # empty monster list for the lure expiry loop
        c.cap(g.S[3], 0x200 * max(n, 1), 'effects')
        c.note(entries=entries)


def gen_add_spell_effect(ctx, g):
    fn = ctx.fn(0x005008a0)
    for i in range(ctx.n(60)):
        r = ctx.rng('ase', i)
        c = ctx.case('add_spell_effect.%d' % i, fn, conv='c', ret='v')
        n = r.choice([0, 1, 2, 3, 5, 8])
        cap = n + r.randint(2, 5)
        data = b''.join(u32(0x5e000000 + k) for k in range(n))
        if data:
            c.set(g.S[4], data)
        c.set(g.effects + 4, u32(n) + u32(cap))
        c.setp(g.effects + 0xc, g.S[4])
        value = r.choice([0, 1, 0x5e5e5e5e, 0xffffffff, r.randrange(1, 1 << 31)])
        c.cap(g.S[4], 4 * cap, 'data')
        c.cap(g.effects + 4, 8, 'count_capacity')
        c.arg(value)
        c.note(count=n, capacity=cap, value=value)


def effect_slots_blob(r, n, ids):
    out = b''
    for _ in range(n):
        out += effslot(r.choice([0, 0, 1, 1, 1, 2, 0xff]), r.choice(ids),
                       r.randrange(0, 50), r.randrange(0, 101), r.randrange(0, 100))
    return out


def gen_party_has_condition(ctx, g):
    fn = ctx.fn(0x005012b0)
    for i in range(ctx.n(200)):
        r = ctx.rng('phc', i)
        c = ctx.case('party_has_condition.%d' % i, fn, conv='c', ret='b')
        ids = [r.choice(list(range(0, 25)) + [-1, 0x100, 0x10003]) for _ in range(6)]
        c.set(g.st + GS_EFFECTS, effect_slots_blob(r, 12, ids))
        eid = r.choice(ids) if r.random() < 0.7 else r.choice([0, 1, 5, 12, 24, -1, 0x100, 3])
        c.arg(eid)
        c.note(ids=ids, effect=eid)


def gen_combat_has_condition(ctx, g):
    fn = ctx.fn(0x00501250)
    for i in range(ctx.n(200)):
        r = ctx.rng('chc', i)
        c = ctx.case('combat_has_condition.%d' % i, fn, conv='c', ret='b')
        ids = [r.choice(list(range(0, 25)) + [-1, 0x100]) for _ in range(6)]
        null = r.random() < 0.1
        if null:
            c.set(g.combat, u32(0))
        else:
            c.set(g.S[6] + CS_EFF, effect_slots_blob(r, 9, ids))
            c.set(g.S[6] + CS_EFF0, effect_slots_blob(r, 9, ids))
            c.setp(g.combat, g.S[6])
        eid = r.choice(ids) if r.random() < 0.7 else r.choice([0, 1, 7, 24, -1, 0x100])
        c.arg(eid)
        c.note(ids=ids, effect=eid, null=int(null))


def gen_set_party_slot_spell(ctx, g):
    fn = ctx.fn(0x004f9aa0)
    for i in range(ctx.n(120)):
        r = ctx.rng('spss', i)
        c = ctx.case('set_party_slot_spell.%d' % i, fn, conv='c', ret='v')
        s = r.randrange(8)
        sp = r.choice(ALL_SPELLS + [-1, 0x7fffffff, 1000])
        power = r.choice([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, -1, 0x12345678])
        c.set(g.S[0], bytes(r.randrange(256) for _ in range(0x20)))
        row = g.row(s)
        c.cap(row, ROW, 'xrow')
        c.arg(s)
        c.arg(sp)
        c.arg(power)
        c.arg(g.S[0])
        c.note(slot=s, spell=sp, power=power)


def gen_absorb_missile_damage(ctx, g):
    fn = ctx.fn(0x00500460)
    for i in range(ctx.n(150)):
        r = ctx.rng('amd', i)
        c = ctx.case('absorb_missile_damage.%d' % i, fn, conv='c', ret='v')
        eff, arr, mis, rep = g.S[3], g.S[4], g.S[1], g.S[5]
        n_eff = r.randint(1, 5)
        owners = []
        if r.random() < 0.85:
            owners.append(r.randrange(n_eff))
            if r.random() < 0.15:
                owners.append(r.randrange(n_eff))
        n_rep = r.choice([0, 0, 1, 2, 3, 5])
        # the missile: result block at +0x280, its report list at +0x2d8
        mres = u32(r.choice([0, 1, 7, 100, 0xffffffff, r.randrange(1 << 32)]))
        mres += u32(r.choice([0, 1, 2, 5, 0xffffffff]))
        mres += b''.join(u32(r.choice([0, 0, 0, 1, 2, 7, 0xffffffff])) for _ in range(20))
        c.set(mis + M_RES, mres)
        c.set(mis + M_REP_COUNT, u32(n_rep) + u32(n_rep + r.randint(0, 2)))
        if n_rep:
            c.set(rep, b''.join(u32(0x7e000000 + k) for k in range(n_rep)))
        c.setp(mis + M_REP_DATA, rep)
        for k in range(n_eff):
            base = eff + 0x400 * k
            nm = r.randint(0, 5)
            pos = None
            if k in owners:
                nm = max(nm, 1)
                pos = r.randrange(nm)
            rc = r.choice([0, 0, 1, 2, 4])
            body = bytearray(0x1c8)
            struct.pack_into('<ii', body, 0, r.choice([1, 36, 38, 79, 25]), r.randrange(0, 5))
            struct.pack_into('<ii', body, E_MIS_COUNT, nm, nm)
            struct.pack_into('<II', body, E_RES, r.choice([0, 3, 50, 0xfffffff0, r.randrange(1 << 32)]),
                             r.choice([0, 1, 4, 0xffffffff]))
            for cnd in range(20):
                struct.pack_into('<I', body, E_RES + 8 + 4 * cnd, r.choice([0, 0, 1, 3, 0xffffffff]))
            struct.pack_into('<ii', body, E_REP_COUNT, rc, rc + n_rep + r.randint(0, 3))
            c.set(base, bytes(body))
            if nm:
                c.set(arr + 0x100 * k, b''.join(u32(0x6d000000 + 0x100 * k + j) for j in range(nm)))
            c.setp(base + E_MIS_DATA, arr + 0x100 * k)
            if rc:
                c.set(rep + 0x400 + 0x100 * k, b''.join(u32(0x7d000000 + 0x100 * k + j) for j in range(rc)))
            c.setp(base + E_REP_DATA, rep + 0x400 + 0x100 * k)
            if pos is not None:
                c.setp(arr + 0x100 * k + 4 * pos, mis)
            c.setp(arr + 0x800 + 4 * k, base)
        c.set(g.effects + 4, u32(n_eff))
        c.setp(g.effects + 0xc, arr + 0x800)
        c.cap(eff, 0x400 * n_eff, 'effects')
        c.cap(mis + M_RES, 0x70, 'missile')
        c.cap(rep, 0x400 + 0x100 * n_eff, 'reports')
        c.arg(mis)
        c.note(effects=n_eff, owners=owners, reports=n_rep)


def gen_detach_missile(ctx, g):
    fn = ctx.fn(0x005019a0)
    for i in range(ctx.n(150)):
        r = ctx.rng('dmr', i)
        c = ctx.case('detach_missile.%d' % i, fn, conv='c', ret='v')
        eff, arr = g.S[3], g.S[4]
        n_eff = r.randint(0, 5)
        target = 0x6c000000 + r.randrange(1, 1000)
        holders = []
        for k in range(n_eff):
            base = eff + 0x400 * k
            nm = r.randint(0, 6)
            vals = [0x6d000000 + 0x100 * k + j for j in range(nm)]
            if nm and r.random() < 0.4:
                for _ in range(r.randint(1, 2)):
                    vals[r.randrange(nm)] = target
                holders.append(k)
            body = bytearray(0x120)
            struct.pack_into('<ii', body, 0, r.randrange(150), r.randrange(5))
            struct.pack_into('<ii', body, E_MIS_COUNT, nm, nm)
            c.set(base, bytes(body))
            if nm:
                c.set(arr + 0x100 * k, b''.join(u32(v) for v in vals))
            c.setp(base + E_MIS_DATA, arr + 0x100 * k)
            c.setp(arr + 0x800 + 4 * k, base)
        c.set(g.effects + 4, u32(n_eff))
        c.setp(g.effects + 0xc, arr + 0x800)
        c.cap(eff, 0x400 * max(n_eff, 1), 'effects')
        c.cap(arr, 0x100 * max(n_eff, 1), 'missile_lists')
        c.arg(target)
        c.note(effects=n_eff, holders=holders)


def gen_missile_spell_id(ctx, g):
    fn = ctx.fn(0x00501a60)
    values = list(range(-3, 41)) + [64, 100, 255, 256, 0x7fffffff, -0x80000000, 0x10001, 0x100 + 3]
    r = ctx.rng('msi')
    while len(values) < ctx.n(100):
        values.append(r.randrange(-50, 400))
    for i, t in enumerate(values[:ctx.n(100)]):
        c = ctx.case('missile_spell_id.%d' % i, fn, conv='c', ret='i')
        c.arg(t)
        c.note(type=t)


def gen_teleport_anchor(ctx, g):
    fn = ctx.fn(0x00501d00)
    for i in range(ctx.n(100)):
        r = ctx.rng('tma', i)
        c = ctx.case('teleport_missing_anchor.%d' % i, fn, conv='c', ret='b')
        ps = party(ctx, c, r)
        s = r.randrange(8)
        ch = g.char(s)
        anchor = None
        if r.random() < 0.7:
            anchor = r.choice([0, 1, 2, 0xff])
            c.set(ch + C_ANCHOR, u8(anchor))
        sp = r.choice([73] * 8 + [0, 72, 74, 75, 1, 149, -1, 0x149, 0x10049])
        c.arg(ch)
        c.arg(sp)
        c.note(char=ps[s][0], spell=sp, anchor=anchor)


def gen_scale_by_pace(ctx, g):
    fn = ctx.fn(0x00501910)
    for i in range(ctx.n(250)):
        r = ctx.rng('sbcp', i)
        c = ctx.case('scale_by_pace.%d' % i, fn, conv='c', ret='v')
        s = r.randrange(8)
        pace = set_pace(c, g, r, s, combat=r.random() < 0.8)
        value = r.choice([0, 1, 2, 5, 10, 15, 40, 50, 99, 100, 101, 1000, 0x7fffffff, 0xffffffff,
                          0x80000000] + [r.randrange(0, 120)] * 6)
        cell = g.S[0] + 0x10
        c.set(cell, u32(value))
        c.cap(cell, 4, 'value')
        c.arg(s)
        c.arg(cell)
        c.note(slot=s, value=value, **pace)


def gen_failure_chance(ctx, g):
    fn = ctx.fn(0x004ff410)
    for i in range(ctx.n(350)):
        r = ctx.rng('sfc', i)
        c = ctx.case('failure_chance.%d' % i, fn, conv='c', ret='i')
        sp = r.choice(ALL_SPELLS)
        mut = mutate_spell(c, g, r, sp, 0.3)
        skill = r.choice([0, 1, 2, 4, 5, 7, 10, 14, 15, 20, 30, 40, 50, 60, 75, 90, 100, 110, 125,
                          200, 0x7fffffff, 0xffffffff, 0x80000000] + [r.randrange(0, 130)] * 8)
        factor = r.choice([1, 2, 3, 4, 5, 6, 7, 8] * 4 + [0, 9, 10, 14, 20, 100, -1, -7, 0x7fffffff,
                                                           r.randrange(0, 300)])
        c.arg(skill)
        c.arg(sp)
        c.arg(factor)
        c.note(spell=sp, skill=skill, factor=factor, **mut)


def gen_total_caster_level(ctx, g):
    fn = ctx.fn(0x004ffbd0)
    for i in range(ctx.n(250)):
        r = ctx.rng('tcl', i)
        c = ctx.case('total_caster_level.%d' % i, fn, conv='c', ret='i')
        ps = party(ctx, c, r)
        s = r.randrange(8)
        ch = g.char(s)
        prof = rd(ps[s][1], C_PROF)
        if r.random() < 0.6:
            prof = r.randrange(15)
            c.set(ch + C_PROF, u32(prof))
        if r.random() < 0.7:
            levels = [r.choice([0, 0, 0, 1, 2, 3, 4, 5, 6, 8, 10, 14, 16, 20, 25, -3, 0x7fffffff])
                      for _ in range(15)]
            c.set(ch + C_PLEVELS, b''.join(u32(v) for v in levels))
        book = r.choice([1, 2, 4, 8, 3, 5, 6, 9, 10, 12, 15, 0, 0x10, 0xff, 0x101, -1])
        include_all = r.randrange(2)
        c.arg(ch)
        c.arg(book)
        c.arg(include_all)
        c.note(char=ps[s][0], prof=prof, book=book, include_all=include_all)


def learned_array(r, data, p):
    vals = [rd(data, C_LEARNED + 4 * k) for k in range(0x72)]
    for k in range(0x72):
        if r.random() < p:
            vals[k] = r.choice([-1, 0, 0, 1, 1, 1, 2, 3])
    return b''.join(u32(v) for v in vals)


def gen_recount_learned(ctx, g):
    fn = ctx.fn(0x004f96a0)
    for i in range(ctx.n(150)):
        r = ctx.rng('rls', i)
        c = ctx.case('recount_learned.%d' % i, fn, conv='c', ret='v')
        ps = party(ctx, c, r)
        s = r.randrange(8)
        ch = g.char(s)
        if r.random() < 0.7:
            c.set(ch + C_LEARNED, learned_array(r, ps[s][1], r.choice([0.05, 0.2, 0.5])))
        if r.random() < 0.5:
            c.set(ch + C_UNLOCKS + 4 * 0x1c, b''.join(u32(r.randrange(0, 1 << 32)) for _ in range(6)))
        c.cap(ch, CHAR, 'char')
        c.arg(ch)
        c.note(char=ps[s][0], slot=s)


def gen_has_castable_spell(ctx, g):
    fn = ctx.fn(0x004f96f0)
    for i in range(ctx.n(200)):
        r = ctx.rng('hcs', i)
        c = ctx.case('has_castable_spell.%d' % i, fn, conv='c', ret='b')
        ps = party(ctx, c, r)
        s = r.randrange(8)
        ch = g.char(s)
        if r.random() < 0.6:
            c.set(ch + C_LEARNED, learned_array(r, ps[s][1], r.choice([0.02, 0.1, 0.3])))
        if r.random() < 0.7:
            sp_left = [r.choice([0, 0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 50, -1, -10,
                                 0x7fffffff, 0x80000000]) for _ in range(6)]
            c.set(ch + C_SPLEFT, b''.join(u32(v) for v in sp_left))
        c.arg(ch)
        c.note(char=ps[s][0], slot=s)


def gen_can_learn_spell(ctx, g):
    fn = ctx.fn(0x004ffcb0)
    for i in range(ctx.n(350)):
        r = ctx.rng('cls', i)
        c = ctx.case('can_learn_spell.%d' % i, fn, conv='c', ret='b')
        ps = party(ctx, c, r)
        s = r.randrange(8)
        ch = g.char(s)
        prof = modify_professions(c, ch, r, 0.35)
        modify_magic_skills(c, ch, r, 0.6)
        if r.random() < 0.15:
            c.set(ch + C_RACE, u32(r.randrange(16)))
        sp = r.choice(BOOK_SPELLS * 3 + ALL_SPELLS)
        mut = mutate_spell(c, g, r, sp, 0.1, ('level',))
        c.arg(ch)
        c.arg(sp)
        c.note(char=ps[s][0], spell=sp, prof=prof, **mut)


def gen_learn_spell(ctx, g):
    fn = ctx.fn(0x004ffe70)
    for i in range(ctx.n(200)):
        r = ctx.rng('lsp', i)
        c = ctx.case('learn_spell.%d' % i, fn, conv='c', ret='v')
        ps = party(ctx, c, r)
        s = r.randrange(8)
        ch = g.char(s)
        modify_magic_skills(c, ch, r, 0.4)
        if r.random() < 0.3:
            c.set(ch + C_LEARNED, learned_array(r, ps[s][1], 0.1))
        if r.random() < 0.2:
            c.set(ch + C_SPLEFT, b''.join(u32(r.randrange(-5, 200)) for _ in range(6)))
        sp = r.choice(REAL_SPELLS + [0, 102, 113])
        c.cap(ch, CHAR, 'char')
        c.arg(ch)
        c.arg(sp)
        c.arg(0)
        c.note(char=ps[s][0], spell=sp)


def recorded_spell_setup(ctx, c, r, g, casters):
    s = r.randrange(8)
    ps = party(ctx, c, r, focus=s, pool=casters)
    ch, row = g.char(s), g.row(s)
    data = ps[s][1]
    known = learned_spells(data)
    pick = r.random()
    if pick < 0.55 and known:
        sp = r.choice(known)
    elif pick < 0.65:
        sp = 60
    else:
        sp = r.choice(ALL_SPELLS)
    power = r.choice([1, 1, 2, 3, 4, 5, 6, 7, 8, 8, 8, 0, 9, -1])
    c.set(row + R_SPELL, u32(sp))
    c.set(row + R_POWER, u32(power))
    if r.random() < 0.3:
        c.set(ch + C_LEARNED + 4 * sp, u32(r.choice([0, 1, 1, -1, 2])))
    cost, realm = SPELLS[sp][0], SPELLS[sp][2]
    if r.random() < 0.7:
        p = 1 if power in (8, 0, -1, 9) else power
        left = r.choice([0, cost - 1, cost, cost * p - 1, cost * p, cost * p + 1, cost * 3, 999, -5,
                         r.randrange(0, 120)])
        c.set(ch + C_SPLEFT + 4 * realm, u32(left))
    if sp == 60 or r.random() < 0.2:
        c.set(ch + C_DEPEND0, u8(r.randrange(2)))
    if r.random() < 0.2:
        c.set(g.spell(sp) + SR_PCLASS, u32(r.choice([0, 1, 1, 2, 3])))
    modes = set_modes(c, g, r, combat=r.random() < 0.5)
    c.set(g.st + GS_SELECTED, u32(r.randrange(8)))
    c.set(g.gx + X_SPELLCAST, u8(0) + u8(0))
    kind = r.choice([0, 2, 1, 1, 1, 9])
    t = s if r.random() < 0.5 else r.randrange(8)
    c.set(row + R_SPELL_TGT, slot_bytes(kind, t if kind in (1, 9) else -1))
    return s, ps, sp, power, kind, t, modes


def gen_can_cast_recorded(ctx, g, casters):
    fn = ctx.fn(0x005012e0)
    for i in range(ctx.n(300)):
        r = ctx.rng('ccrs', i)
        c = ctx.case('can_cast_recorded.%d' % i, fn, conv='c', ret='b')
        s, ps, sp, power, kind, t, modes = recorded_spell_setup(ctx, c, r, g, casters)
        c.arg(s)
        c.note(char=ps[s][0], slot=s, spell=sp, power=power, target=(kind, t), **modes)


def gen_affordable_power(ctx, g, casters):
    fn = ctx.fn(0x00501400)
    for i in range(ctx.n(300)):
        r = ctx.rng('aspl', i)
        c = ctx.case('affordable_power.%d' % i, fn, conv='c', ret='i')
        s, ps, sp, power, kind, t, modes = recorded_spell_setup(ctx, c, r, g, casters)
        c.arg(s)
        c.note(char=ps[s][0], slot=s, spell=sp, power=power, target=(kind, t), **modes)


def gen_can_use_recorded_item(ctx, g):
    fn = ctx.fn(0x00501660)
    for i in range(ctx.n(250)):
        r = ctx.rng('curi', i)
        c = ctx.case('can_use_recorded_item.%d' % i, fn, conv='c', ret='b')
        ps = party(ctx, c, r)
        s = r.randrange(8)
        ch, row = g.char(s), g.row(s)
        origin = r.choice([0, 0, 0, 0, 1, 1, 1, 2, 2, 3, 0x80, 0xff])
        if origin == 0:
            islot = r.randrange(8)
        elif origin == 1:
            islot = r.randrange(12)
        else:
            islot = r.randrange(500)
        if r.random() < 0.05:
            islot = r.choice([0x8000, 0xffff])
        item_id = r.choice(USABLE_ITEMS) if r.random() < 0.8 else r.choice(sorted(SOURCE_ITEMS) + [r.randrange(ITEM_COUNT)])
        stored = item_id
        q = r.random()
        if q < 0.08:
            stored = -1
        elif q < 0.16:
            stored = r.choice(USABLE_ITEMS)
        if origin in (0, 1, 2) and islot < 0x8000:
            if origin == 0:
                where = ch + C_PACK + 12 * islot
            elif origin == 1:
                where = ch + C_EQUIP + 12 * islot
            else:
                where = g.st + GS_POOL + 12 * islot
            c.set(where, item_bytes(stored, 1, r.choice([0, 1, 3, 10]), 1 if r.random() < 0.85 else 0))
        c.set(row + R_ITEM_ID, u32(item_id) + u8(origin) + u16(islot))
        kind = r.choice([0, 1, 1, 2, 9])
        t = s if r.random() < 0.6 else r.randrange(8)
        c.set(row + R_ITEM_TGT, slot_bytes(kind, t if kind in (1, 9) else -1))
        modes = set_modes(c, g, r, combat=r.random() < 0.4)
        c.set(g.settings + ST_AUTOTARGET, u8(r.randrange(2)))
        c.set(g.st + GS_SELECTED, u32(r.randrange(8)))
        c.set(g.gx + X_SPELLCAST, u8(0) + u8(0))
        c.setp(g.gx + X_MONLIST, g.S[5])
        c.setp(g.gx + X_GROUPLIST, g.S[5])
        c.cap(row, ROW, 'xrow', ignore=[R_ITEM_DETAIL + 4])
        c.arg(s)
        c.note(char=ps[s][0], slot=s, origin=origin, islot=islot, item=item_id, stored=stored,
               target=(kind, t), **modes)


def gen_monster_power_level(ctx, g):
    fn = ctx.fn(0x00500330)
    for i in range(ctx.n(250)):
        r = ctx.rng('cmspl', i)
        c = ctx.case('monster_power_level.%d' % i, fn, conv='c', ret='i')
        mi, rec = g.S[1], g.S[2]
        sp_points = r.choice([0, 0, 0, 5, 10, 25, 50, 100, -10, -100, 0x7fffffff, -0x80000000] +
                             [r.randrange(-50, 300)] * 3)
        budget = r.choice(MONSTER_BUDGETS)
        c.set(mi + MI_SPECIES, u32(SPECIES))
        c.set(mi + MI_SP, u32(sp_points))
        c.set(rec + MR_SPBUDGET, u32(budget))
        wire_record(c, g, rec)
        sp = r.choice(MONSTER_SPELLS * 3 + [119] * 4 + ALL_SPELLS)
        mut = mutate_spell(c, g, r, sp, 0.2)
        c.arg(mi)
        c.arg(rec)
        c.arg(sp)
        c.note(spell=sp, sp_points=sp_points, budget=budget, **mut)


def magic_char_setup(ctx, c, r, g, casters):
    s = r.randrange(8)
    ps = party(ctx, c, r, focus=s, pool=casters if r.random() < 0.85 else None)
    ch = g.char(s)
    modify_magic_skills(c, ch, r, 0.5)
    prof = modify_professions(c, ch, r, 0.25)
    if r.random() < 0.15:
        c.set(ch + C_COND + 4 * 8, u32(r.choice([1, 5, 9999])))
    pace = set_pace(c, g, r, s)
    return s, ps, ch, prof, pace


def gen_best_spellbook_skill(ctx, g, casters):
    fn = ctx.fn(0x004ff7f0)
    for i in range(ctx.n(350)):
        r = ctx.rng('bsss', i)
        c = ctx.case('best_spellbook_skill.%d' % i, fn, conv='c', ret='i')
        s, ps, ch, prof, pace = magic_char_setup(ctx, c, r, g, casters)
        sp = r.choice(BOOK_SPELLS * 4 + ALL_SPELLS)
        mut = mutate_spell(c, g, r, sp, 0.15)
        pricing, prefer = r.randrange(2), r.randrange(2)
        power = r.choice([1, 2, 3, 4, 5, 6, 7, 8, 0, 9])
        c.arg(ch)
        c.arg(sp)
        c.arg(pricing)
        c.arg(prefer)
        c.arg(power)
        c.note(char=ps[s][0], slot=s, spell=sp, pricing=pricing, prefer=prefer, power=power,
               prof=prof, **dict(pace, **mut))


def gen_cast_rating(ctx, g, casters):
    fn = ctx.fn(0x004ff4b0)
    for i in range(ctx.n(300)):
        r = ctx.rng('scr', i)
        c = ctx.case('cast_rating.%d' % i, fn, conv='c', ret='i')
        s, ps, ch, prof, pace = magic_char_setup(ctx, c, r, g, casters)
        known = learned_spells(ps[s][1])
        sp = r.choice(known) if known and r.random() < 0.6 else r.choice(BOOK_SPELLS + ALL_SPELLS)
        mut = mutate_spell(c, g, r, sp, 0.15)
        power = r.choice([1, 2, 3, 4, 5, 6, 7] * 3 + [8, 8, 0, 9, 100])
        c.arg(ch)
        c.arg(sp)
        c.arg(power)
        c.note(char=ps[s][0], slot=s, spell=sp, power=power, prof=prof, **dict(pace, **mut))


def gen_power_for_duration(ctx, g, casters):
    fn = ctx.fn(0x004fdf30)
    for i in range(ctx.n(300)):
        r = ctx.rng('plfd', i)
        c = ctx.case('power_for_duration.%d' % i, fn, conv='c', ret='i')
        s, ps, ch, prof, pace = magic_char_setup(ctx, c, r, g, casters)
        sp = r.choice(DURATION_SPELLS * 4 + BOOK_SPELLS)
        mut = mutate_spell(c, g, r, sp, 0.1, ('cost',))
        cost, realm = mut.get('cost', SPELLS[sp][0]), SPELLS[sp][2]
        if r.random() < 0.8:
            left = r.choice([0, cost - 1, cost, cost * 2, cost * 3 + 1, cost * 5, cost * 7, cost * 7 - 1,
                             500, -1] + [r.randrange(0, 120)] * 3)
            c.set(ch + C_SPLEFT + 4 * realm, u32(left))
        turns = r.choice([9999, 9999, 0, 1, 2, 3, 4, 5, 8, 10, 15, 20, 30, 49, 50, 64, 100, 255, 1000,
                          0xffffffff] + [r.randrange(1, 80)] * 6)
        c.arg(ch)
        c.arg(sp)
        c.arg(turns)
        c.note(char=ps[s][0], slot=s, spell=sp, turns=turns, prof=prof, **dict(pace, **mut))


def gen_power_to_restore(ctx, g, casters):
    fn = ctx.fn(0x004fe1c0)
    for i in range(ctx.n(250)):
        r = ctx.rng('plr', i)
        c = ctx.case('power_to_restore.%d' % i, fn, conv='c', ret='i')
        s, ps, ch, prof, pace = magic_char_setup(ctx, c, r, g, casters)
        sp = r.choice(RESTORE_SPELLS * 6 + [16, 44, 68, 1, 0, 34])
        dice = None
        if r.random() < 0.15:
            dice = (r.choice([0, 0, 2, 10, -5, 300]), r.choice([1, 4, 8, 40, 64, 100, 200, 255]),
                    r.choice([1, 4, 6, 8, 20, 255]))
            c.set(g.spell(sp) + SR_DICE, struct.pack('<hBB', *dice))
        t = None
        if r.random() < 0.9:
            t = r.randrange(8)
            tch = g.char(t)
            if r.random() < 0.8:
                hpmax = r.choice([0, 1, 10, 50, 100, 250, 400, -1, 0x7fffffff])
                hp = r.choice([0, 1, hpmax, hpmax - 1, hpmax // 2, hpmax - 10, hpmax + 5])
                c.set(tch + C_HPMAX, u32(hpmax) + u32(hp))
            if r.random() < 0.6:
                smax = r.choice([0, 10, 100, 200, 300, -1])
                st = r.choice([0, smax, smax - 1, smax // 3, smax + 2, -50])
                c.set(tch + C_STMAX, u32(smax) + u32(st))
            target = tch
        else:
            target = 0
        c.arg(ch)
        c.arg(sp)
        c.arg(target)
        c.note(char=ps[s][0], slot=s, spell=sp, target=t, dice=dice, **pace)


def gen_power_for_target(ctx, g, casters):
    fn = ctx.fn(0x004fe480)
    for i in range(ctx.n(300)):
        r = ctx.rng('splt', i)
        c = ctx.case('power_for_target.%d' % i, fn, conv='c', ret='i')
        s, ps, ch, prof, pace = magic_char_setup(ctx, c, r, g, casters)
        row = g.row(s)
        kind = r.choice([1] * 6 + [3] * 2 + [0, 2, 7])
        safe = RESTORE_SPELLS + [44, 68, 23] + [k for k in REAL_SPELLS if SPELLS[k][3] != 1]
        if kind in (1, 3):
            sp = r.choice(RESTORE_SPELLS * 2 + DURATION_SPELLS * 3 + [44, 68, 23] * 2 + REAL_SPELLS)
        else:
            sp = r.choice(RESTORE_SPELLS * 2 + [44, 68, 23] * 2 + safe)
        conds = [r.choice([0, 0, 0, 1, 2, 3, 5, 8, 12, 20, 30, 64, 9999, 10000, 0x80000000])
                 if k in CONDITION_IDS else 0 for k in range(20)]
        t = None
        if kind == 1:
            t = r.randrange(8)
            tch = g.char(t)
            if r.random() < 0.85:
                c.set(tch + C_COND, b''.join(u32(v) for v in conds))
            if sp == 58 and r.random() < 0.6:
                eslot = r.randrange(12)
                c.set(tch + C_EQUIP + 12 * eslot,
                      item_bytes(r.choice(BIND_ITEMS), 1, 0, 1, r.choice([0, 0, 1])))
            if sp in RESTORE_SPELLS and r.random() < 0.6:
                hpmax = r.choice([10, 50, 100, 250])
                c.set(tch + C_HPMAX, u32(hpmax) + u32(r.choice([0, 1, hpmax, hpmax // 2, hpmax - 3])))
            c.set(row + R_TGT_OOC, slot_bytes(1, t))
        elif kind == 3:
            mi, rec = g.S[1], g.S[2]
            loc = r.choice([1, 77, 1234, 40000])
            c.set(mi + MI_LOC, u32(loc))
            c.set(mi + MI_SPECIES, u32(SPECIES))
            c.set(mi + MI_COND, b''.join(u32(v) for v in conds))
            wire_record(c, g, rec)
            wire_monster_list(c, g, [mi])
            c.set(row + R_TGT_OOC, slot_bytes(3, -1, loc))
        else:
            c.set(row + R_TGT_OOC, slot_bytes(kind))
        if sp == 23:
            item_id = r.choice([r.randrange(ITEM_COUNT), r.choice(BIND_ITEMS), -1])
            c.set(g.S[0], item_bytes(item_id, 1, 0, r.randrange(2)))
            c.setp(row + R_TGT_OOC + 0x1c, g.S[0])
        ident = r.choice([0, 0, 10, 25, 50, 100, 200, 0xffffffff])
        c.arg(s)
        c.arg(sp)
        c.arg(ident)
        c.note(char=ps[s][0], slot=s, spell=sp, kind=kind, target=t, ident=ident, **pace)


def gen_spell_aim_string(ctx, g):
    fn = ctx.fn(0x004f97a0)
    for i in range(ctx.n(200)):
        r = ctx.rng('sas', i)
        c = ctx.case('spell_aim_string.%d' % i, fn, conv='c', ret='w', out='w')
        ps = party(ctx, c, r)
        src, tgt = g.S[0], g.S[0] + 0x40
        kind = r.choice([0, 1, 1, 1, 2, 3, 3, 5, 6, 7, 7, 8, 9, 9, 10, 11, -1])
        sbody = bytearray(0x34)
        tbody = bytearray(0x20)
        info = {}
        if kind in (1, 9):
            t = r.randrange(8)
            struct.pack_into('<iiii', tbody, 0, kind, t, -1, -1)
            skind = r.choice([1, 1, 1, 0, 2, 3])
            schar = t if r.random() < 0.6 else r.randrange(8)
            struct.pack_into('<iii', sbody, 0, skind, schar, -1)
            sbody[0x19] = r.choice([0, 0, 1])
            if r.random() < 0.3:
                c.set(g.char(t) + C_GENDER, u32(r.choice([0, 1, 2, 3])))
            info = dict(t=t, skind=skind, schar=schar, name_known=sbody[0x19])
        elif kind == 3:
            mi, rec = g.S[1], g.S[2]
            loc = r.choice([5, 300, 4242])
            c.set(mi + MI_LOC, u32(loc))
            c.set(mi + MI_SPECIES, u32(SPECIES))
            wire_record(c, g, rec)
            wire_monster_list(c, g, [mi])
            struct.pack_into('<iiii', tbody, 0, 3, -1, loc, -1)
            same = r.random() < 0.6
            if same:
                struct.pack_into('<iii', sbody, 0, 2, -1, loc)
                c.set(rec + MR_NAMEGROUP, u8(r.choice([0, 1, 2, 3])))
            else:
                struct.pack_into('<iii', sbody, 0, r.choice([2, 1, 0]), r.randrange(8), loc + 1)
                c.set(rec + MR_RECID, u16(397))          # the alternate-name monster
                c.set(g.st + GS_SEDEXUS, u32(r.randrange(8)))
                c.cap(g.st + GS_MONNAME, 44, 'monster_name')
            info = dict(loc=loc, same=int(same))
        elif kind == 7:
            item_id = r.randrange(ITEM_COUNT)
            ident = r.randrange(2)
            c.set(g.S[0] + 0x80, item_bytes(item_id, r.choice([1, 3]), 0, ident))
            struct.pack_into('<i', tbody, 0, 7)
            info = dict(item=item_id, identified=ident)
        else:
            struct.pack_into('<iiii', tbody, 0, kind, -1, -1, -1)
        c.set(src, bytes(sbody))
        c.set(tgt, bytes(tbody))
        if kind == 7:
            c.setp(tgt + 0x1c, g.S[0] + 0x80)
        c.arg(src)
        c.arg(tgt)
        c.note(kind=kind, **info)


def cases(ctx):
    g = G(ctx)
    casters = [(n, d) for n, d in ctx.corpus if learned_spells(d)] or ctx.corpus
    gen_prof_caster_level(ctx, g)
    gen_spell_difficulty(ctx, g)
    gen_can_cast_from_item(ctx, g)
    gen_blocked_for_character(ctx, g)
    gen_blocked_for_monster(ctx, g)
    gen_spell_usable_now(ctx, g)
    gen_target_needed_friendly(ctx, g)
    gen_target_needed_hostile(ctx, g)
    gen_can_rebreathe(ctx, g)
    gen_all_effects_running(ctx, g)
    gen_find_control_effect(ctx, g)
    gen_tick_effects(ctx, g)
    gen_add_spell_effect(ctx, g)
    gen_party_has_condition(ctx, g)
    gen_combat_has_condition(ctx, g)
    gen_set_party_slot_spell(ctx, g)
    gen_absorb_missile_damage(ctx, g)
    gen_detach_missile(ctx, g)
    gen_missile_spell_id(ctx, g)
    gen_teleport_anchor(ctx, g)
    gen_scale_by_pace(ctx, g)
    gen_failure_chance(ctx, g)
    gen_total_caster_level(ctx, g)
    gen_recount_learned(ctx, g)
    gen_has_castable_spell(ctx, g)
    gen_can_learn_spell(ctx, g)
    gen_learn_spell(ctx, g)
    gen_can_cast_recorded(ctx, g, casters)
    gen_affordable_power(ctx, g, casters)
    gen_can_use_recorded_item(ctx, g)
    gen_monster_power_level(ctx, g)
    gen_best_spellbook_skill(ctx, g, casters)
    gen_cast_rating(ctx, g, casters)
    gen_power_for_duration(ctx, g, casters)
    gen_power_to_restore(ctx, g, casters)
    gen_power_for_target(ctx, g, casters)
    gen_spell_aim_string(ctx, g)
