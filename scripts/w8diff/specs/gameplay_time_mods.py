"""GameplayTime.cpp, Gameplay Mods.cpp, party_encumbrance.cpp (src/wiz8/local_code): game clock,
aging/regeneration ticks, camp fatigue, modifier-block folding and the derived-stat /
encumbrance rebuild.

Tested (retail address, function, cases at --scale 1):
  Gameplay Mods.cpp
  0x0050f090 ApplyModifierBlock                     300  scratch blocks (S0 target, S1 source),
                                                         5% target == source
  0x0050edc0 ApplyPartyEffectSlots                  350  12 scratch slots, every handled id with
                                                         amount/percent edges (AdjustByteByPercent
                                                         unsigned overflow), unhandled ids
  0x0050ef50 ApplyCombatEffectSlots                 250  6 scratch slots, ids 2/0x35/0x3b + others
  0x0050ecc0 ApplyEnchantmentModifiers              250  8 scratch enchantments
  0x0050eac0 ApplyConditionModifiers                350  character = NULL or a party slot; blind with
                                                         Monk trait 7; condition 0x13 through a
                                                         scratch monster list (MonsterInfoFromID)
  0x0050e980 AccumulateEquipmentModifiers           300  real Items.dbs bonus items, +-125 clamp
  0x0050f030 RebuildCharacterModifierBlock          250
  0x0050e540 RebuildEquipmentAndDerivedStats        200  full derived-stat chain (see env below)
  0x0050e5c0 RebuildEquipmentAndDerivedStatsForSlot 120
  0x0050e650 RebuildConditionsAndDerivedStats       250  conditions, enchantments, npc_bound,
                                                         condition 0x13 with scratch monsters
  0x0050e700 RebuildPartyEffectBlock                200  party effect slots, combat slots (scratch
                                                         W8CombatState), Bard camp-recovery latch;
                                                         last case uses the save's own effect slots
                                                         so the camera light ends in its natural state
  0x0050e8c0 RebuildMonsterDerivedStats             200  scratch monster list + scratch monsters,
                                                         scratch pCombat
  GameplayTime.cpp
  0x00502b50 RebuildCharacterRegenRates             300  pool ceilings incl. negative (unsigned fild)
  0x00502c50 RebuildMonsterRegenRates               250  scratch W8MonsterInfo
  0x00502010 UpdateGameClock                        300  never reaches AdvanceTimedEffects (aging sum
                                                         kept < 120000 or item drag active out of
                                                         combat) nor BeginPartyCamping (surprise mode
                                                         on, or slot 0 kept eligible); hourly 0x266
                                                         recharge, camp fatigue and stamina ticks run
  0x00503100 GameTurnsPassedChar                    400  disease rolls, infatuation, Destinae Dominus
                                                         (0x243) / Helm of Serenity (0x239), regen
                                                         channels and accumulators, traits, condition /
                                                         enchantment countdowns, alchemist brew
  0x00503990 AgeMonsterSight                        250  scratch monster in a scratch monster list; in
                                                         combat (p3D = NULL, scratch pCombat, combat
                                                         slots idle) or out of combat with a scratch
                                                         p3D that skips the movement watch (look/pause
                                                         timers); no expiring condition/enchantment/
                                                         effect, no damage path
  0x005044d0 UpdateCampFatigue                      250
  0x00504670 UpdatePartyStamina                     300  also covers RegenCharacterStamina (inlined)
  0x005029e0 ResolveSurpriseWake                    150  scratch W8CombatState.party_surprised
  party_encumbrance.cpp
  0x004ed9d0 RecalculateCharacterDerivedStats       300  party slot or scratch character, early-out
                                                         gates, level clamps, traits, iron skin
  0x004edc10 RecalculateCarryingCapacity            200
  0x004edc60 RecalculateCarriedWeight               250  overload crossing (event deleted, see env)
  0x004edd20 RedistributePartyEncumbrance           300  scratch party pool contents, camp screen in
                                                         scratch (S6)

Skipped:
  0x00502460 RequestCamp              - starts camping: notices, region input, surprise fade,
                                        camping music (BeginPartyCamping)
  0x005025f0 BeginSurprise            - completes all live character events, portrait poses,
                                        disables the menu button banks (UI)
  0x00502650 UpdateSurpriseMode       - destroys ungrouped world monsters, view distance,
                                        navigator link mode, music, environment refresh
  0x00502790 AcknowledgeSurprise      - notice or ResolveSurpriseHold (sight reset, fade, music)
  0x00502810 ResolveSurpriseHold      - ResetSight, surprise fade, NPC bindings, level music
  0x00502860 EndSurprise              - surprise teardown: region input, notices, facts, wake pass
  0x005029a0 RestoreSurpriseView      - ResetSight + destroys the fade overlay
  0x00502d00 AdvanceTimedEffects      - ages every world monster, NPC timers/pending events,
                                        monster group detection, sounds
  0x00504730 RegenCharacterStamina    - inlined in the port (not in Wiz8Runtime.map); tested
                                        through UpdatePartyStamina

Common set-up (everything restored by the core after each case):
  * party slots get pristine corpus characters (setb), XChar.fOccupied set explicitly; character
    fields are changed with field-level set ops only (no modified blobs, so the plan keeps at most
    49 distinct blobs);
  * g_status.greeting_pending = 1 (QueueEntry deletes every new character event, so the heap quote
    queue does not grow), skip_next_condition_reaction = 0, world_suspended set (mostly 0),
    item_in_cursor = 0, gXStatus.fCombatMode / fSurprisePossible set per case, g_combat_state NULL
    or a scratch W8CombatState (characters[].dead = 1 so CalcArmorClasses' TryCharacterAction only
    compares pending_action);
  * with fSurprisePossible = 0 no case reaches ApplyDamageToCharacter (the portrait splat and the
    damage-reaction quotes consume Random() depending on UI/queue state);
  * death-capable slots get XChar.npc_index = -1 and every XChar.target_out_of_combat.iType = 0;
    no case gives a character a finite TURNCOAT (its removal re-picks targets from the world), and
    combat cases keep every character alive (CharacterDies books combat deaths) and capture the
    two formation copies RecomputeCharacterHighestCondition updates in combat;
  * side effects outside captured memory: notices in the text box, CharacterDead.wav, redraw
    flags, and RebuildPartyEffectBlock's camera light (SetSkyNodeVisible/SetCameraLightIntensity;
    its last case runs on the save's own effect slots to leave the light as the game set it);
  * captured: the party characters (float fields with ULP tolerance), the XChar rows (pointer
    fields ignored), g_status except the text-box line counters, gXStatus party entries (pointers
    and real-time timers ignored), fEncumbranceDirty, sight_refresh_pending, and every scratch
    struct a function writes;
  * scratch monster lists: gXStatus.plsMonsterList -> S0/S2 PList, plsUnbornMonsterList -> an
    empty zeroed PList, so location-id lookups never reach world monsters.
Edge values outside the domains (negative highest_condition, negative stamina / accumulators,
non-canonical bool bytes) are a minority of the cases and labelled note(edge=...): retail compares
highest_condition and monster stamina unsigned and converts accumulator remainders through an
unsigned qword, so a difference only in those cases points at a signed compare or int cast in the
port.
"""
import struct

from w8diff.api import Blob

CHAR = 0x1862
ROW = 0x106
MOD = 0x67
SLOT = 0x11
ENCH = 0xc
ITEM = 0xc

# W8Character (layout.ps1 wiz8/layouts/character.h)
C_INPARTY = 0x04
C_PROF = 0x69
C_ORIG = 0x6d
C_RACE = 0x71
C_GENDER = 0x75
C_LEVEL = 0x89
C_PLEV = 0x8d
C_ATTR = 0xe5
ATTR_STEP = 0x14
A_STR, A_INT, A_PIE, A_VIT, A_DEX, A_SPD, A_SEN = range(7)
C_SKILL = 0x19d
SK_STEP = 0x26
SK_IRON = 37
C_COND = 0xa01
C_ENCH = 0xa65
C_HIGHEST = 0xb01
C_CONDARG = 0xb09
C_HPMAX = 0xb0d
C_HP = 0xb11
C_HPADJ = 0xb15
C_STMAX = 0xb19
C_ST = 0xb1d
C_FATPEN = 0xb21
C_SPMAX = 0xb25
C_SPLEFT = 0xb45
C_BREW = 0xb65
C_HRATE = 0xb69
C_HACC = 0xb6d
C_SRATE = 0xb71
C_SACC = 0xb75
C_SPRATE = 0xb79
C_INVW = 0xbb9
C_SHARE = 0xbbd
C_TOTW = 0xbc1
C_CAP = 0xbc5
C_LOAD = 0xbc9
C_EQUIP = 0xf5d
C_PACK = 0x1029
C_FATBAND = 0x169e
C_CONDMOD = 0x16a2
C_EQBONUS = 0x1709
C_BONUS = 0x1770
C_CONDREC = 0x1817
CR_STEP = 0x11
CHAR_FLOATS = [C_HRATE, C_HACC, C_SRATE, C_SACC] + [C_SPRATE + 4 * k for k in range(12)]
PB_LO, PB_HI = C_HIGHEST, C_SPRATE + 48          # 0xb01..0xba9: conditions tail .. spell rates

# W8GameplayModifierBlock
B_DPM, B_HREG, B_SREG, B_SPREG = 0x08, 0x09, 0x0a, 0x0b
B_ATTR, B_SKILL, B_RES = 0x0c, 0x13, 0x3c
B_BOOST = 0x42
B_LIGHT = 0x47
B_DRA = 0x06

# conditions
DRAINED, DISEASED, IRRITATED, NAUSEATED, SLOWED, AFRAID, POISONED, SILENCED, HEXED = range(1, 10)
INFATUATED, INSANE, BLIND, TURNCOAT, WEBBED, ASLEEP, PARALYZED, UNCONSCIOUS, DEAD = range(10, 19)
MISSING = 19
INDEF = 9999

# W8GlobalStatus (layout.ps1 wiz8/layouts/game_status.h)
S_STARTED = 0x0c
S_POOL = 0x21
S_POOLN = 0x1791
S_EFFECTS = 0x17af
S_CLOCK = 0x18d8
S_LEVEL = 0x1900
S_PARTYMOD = 0x22e3
S_INCURSOR = 0x235a
S_INHAND = 0x235b
S_AGING = 0x238b          # aging, search_mode, world_suspended, real/frame elapsed, wait, recharge
S_SUSPENDED = 0x2390
S_WAIT = 0x2399
S_FATIGUED = 0x2433
S_CAMPTICK = 0x2436
S_STAMTICK = 0x2483
S_SKIPREACT = 0x2488
S_GREETING = 0x2497
S_CAMPCOUNT = 0x2498
S_CAPS = ((0x0c, 0x1795), (0x17af, 0x4997), (0x49b7, 0x49c2))

# W8PartySlotRow
X_OCC = 0x00
X_PENDING = 0x01
X_TOUT = 0x1d
X_NPC = 0xfa
X_BOUND = 0xfe
X_PTRS = (0x19, 0x39, 0x49, 0x69, 0x7d, 0x9d, 0xa5, 0xc5, 0xed)

# W8XStatus
GX_ENTRY = 0x118
GX_COMBAT = 0x8dc
GX_NPCDLG = 0x8df
GX_DIRTY = 0x8e8
GX_MONLIST = 0x8f5
GX_UNBORN = 0x901
GX_SURPRISE = 0x90d
GX_UNENGAGED = 0x90e
GX_PHASE = 0x913
GX_SIGHT = 0xa03
GX_DRAG = 0x19b9
GX_EDIT_FORMATION = 0x933
FORMATION = 0x84          # W8PartyFormationState
# W8MonsterManagerEntry: handles/pointers (voice, quote, active event, vector vptr/data) and the
# real-time TIMERs (frame/pose/idle/fx/pulse clocks; SetCountdownClock reads the frame clock)
E_IGNORE = (0x01, 0x19, 0x71, 0x7d, 0x91, 0x95, 0xca, 0xd2, 0xd8, 0xe4)

# W8CombatState
CS_SIZE = 0xa64
CS_CHARS = 0x18
CS_ROW = 0xd4
CS_DEAD = 0x34
CS_EFFECTS = 0x7c1        # 9 slots, then effect_slots0 (6) at 0x85a
CS_EFFECTS0 = 0x85a
CS_FORMATION = 0x920
CS_SURPRISED = 0xa52

# W8MonsterInfo (wiz8/local_code/MonsterManager.h)
M_SIZE = 0x425
M_STRIDE = 0x430
M_LOC = 0x00
M_GROUP = 0x04
M_SPECIES = 0x08
M_P3D = 0x0c
M_PCOMBAT = 0x10
M_ACTIVE = 0x14
M_INCOMBAT = 0x15
M_HPMAX = 0x27
M_HP = 0x2b
M_STMAX = 0x2f
M_ST = 0x33
M_HRATE = 0x47
M_HACC = 0x4b
M_SRATE = 0x4f
M_SACC = 0x53
M_COND = 0x57
M_ENCH = 0xa7
M_HIGHEST = 0x107
M_CONDARG = 0x10b
M_EFFECTS = 0x10f
M_MODS = 0x1db
M_ATTRS = 0x247
M_STALL = 0x254
M_LOOK = 0x302
M_PAUSE = 0x303
M_PTRS = (M_P3D, M_PCOMBAT, 0x2b6)
M_FLOATS = (M_HRATE, M_HACC, M_SRATE, M_SACC)
# W8MonsterCombatState
MC_SIZE = 0x153
MC_EFFECTS = 0x3e
MC_EFFECTS2 = 0xd7
# W8Monster (p3D) fields AgeMonsterSight reads before the timers
W_STOPPED = 0x3c
W_HALTED = 0x3d
W_NAVIGATOR = 0x74
W_STAY_HOME = 0x291
W_LOOK_FREQ = 0x2c8
W_LOOK_DUR = 0x2cc

# W8GameSettings
SET_VERBOSE = 0x44

SCREEN_CHARACTER, SCREEN_CAMP, SCREEN_MAIN, SCREEN_AUTOMAP = 3, 6, 7, 8
LEVEL_FAST, LEVEL_MOVED, LEVEL_WALK = 0x100, 0x200, 0x10

ITEM_COUNT = 819
SOLAR_PAK = 0x266
SCUBA = 0x1e5
DOMINUS = 0x243
SERENITY = 0x239

# Items.dbs (patched) records with nonzero modifier fields (db scan of the extracted file)
IT_DMG = [0, 1, 2, 3, 4, 5, 6, 9, 10, 15, 22, 34, 40, 53, 73, 85, 99, 110, 424, 465, 501, 591, 599,
          646, 660, 673, 748, 762, 770, 786, 814, 815]
IT_HIT = [2, 3, 5, 26, 48, 68, 89, 126, 130, 139, 489, 513, 666, 766, 787, 798, 803]
IT_REGEN = [15, 34, 48, 73, 74, 85, 96, 119, 149, 168, 179, 195, 208, 218, 228, 254, 270, 305, 313,
            430, 463, 469, 499, 509, 561, 661, 777, 779, 781, 788, 791, 798, 809, 810, 811, 812, 818]
IT_RES = [29, 45, 48, 71, 142, 146, 150, 163, 168, 169, 175, 195, 222, 234, 261, 267, 279, 290, 294,
          295, 309, 311, 458, 463, 500, 569, 740, 789, 792, 805, 806, 809, 816, 817, 818]
IT_RES_HIGH = [146, 168, 195, 789, 806, 267, 805, 818, 234, 279, 290, 293, 254, 276, 280, 292, 309,
               261, 142, 48]
IT_SKILLMOD = [5, 25, 97, 98, 142, 147, 217, 222, 268, 284, 290, 294, 312, 319, 419, 427, 458, 463,
               466, 469, 470, 491, 504, 510, 511, 574, 654, 660, 753, 755, 772, 774, 775, 776, 777,
               780, 781, 782, 789, 792, 808, 810, 814, 816, 818]
IT_ATTRMOD = [37, 59, 96, 119, 179, 208, 217, 219, 222, 228, 240, 251, 270, 271, 272, 273, 274, 275,
              277, 289, 291, 310, 315, 420, 463, 470, 491, 492, 510, 511, 561, 654, 754, 773, 775,
              776, 777, 778, 781, 790, 792, 793, 807, 808, 816, 817, 818]
IT_BONUS = sorted(set(IT_DMG + IT_HIT + IT_REGEN + IT_RES + IT_SKILLMOD + IT_ATTRMOD))
# stackable (quantity kind 1) items: (id, weight)
IT_STACK = [(46, 3), (47, 3), (69, 3), (99, 2), (100, 1), (101, 3), (102, 5), (107, 35), (125, 2),
            (131, 4), (132, 5), (258, 10), (260, 3), (306, 5), (331, 2), (343, 5)]
IT_HEAVY = [14, 34, 73, 148, 149, 150, 151, 160, 175, 183, 245, 497, 500, 559, 567, 778, 806, 810]

# Monsters.dbs species: (effective_level, hp_regeneration, stamina_regeneration)
SPECIES = {0: (3, 0, 1), 1: (3, 0, 0), 5: (20, 2, 0), 13: (8, 0, 1), 14: (8, 1, 0), 17: (5, 0, 0),
           32: (5, 1, 1), 42: (9, 0, 0), 100: (7, 0, 4), 142: (47, 0, 1), 159: (28, 4, 1),
           250: (9, 0, 0), 418: (5, 0, 5), 455: (15, 3, 2), 564: (38, 0, 90), 590: (14, 4, 4),
           594: (4, 0, 0)}
SPECIES_IDS = sorted(SPECIES)

E32 = [0, 1, 2, 0x7fffffff, 0x80000000, 0xfffffffe, 0xffffffff]
PERCENTS = [0, 0, 0, 0, 0, 0, 10, 25, 33, 50, 99, 100, 101, 155, 200, 255, 1000, 0xffffff9c,
            0xffffff9b, 0xffffffff, 0x7fffffff, 0x80000000, 16843009, 42949673]


def u8(v):
    return bytes([int(v) & 0xff])


def u16(v):
    return struct.pack('<H', int(v) & 0xffff)


def u32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def f32(v):
    return struct.pack('<f', float(v))


def arr32(vals):
    return b''.join(u32(v) for v in vals)


def s32(v):
    v &= 0xffffffff
    return v - (1 << 32) if v >= (1 << 31) else v


def pick(r, edges, lo, hi, pe=0.25):
    if r.random() < pe:
        return r.choice(edges)
    return r.randint(lo, hi)


def add_edge(note, name):
    edges = [e for e in note.get('edge', '').split(',') if e]
    if name not in edges:
        edges.append(name)
    note['edge'] = ','.join(edges)


def sbyte(r, p_zero=0.5):
    x = r.random()
    if x < p_zero:
        return 0
    if x < p_zero + (1.0 - p_zero) * 0.75:
        return r.randint(-10, 10) & 0xff
    return r.choice([0x7f, 0x80, 0x81, 0xff, 0x01, 0x7e, 0x40, 0xc0])


def rand_block(r, p_zero=0.5, tail=True):
    """A W8GameplayModifierBlock: summed byte runs, latches, max-combined bytes, opaque tail."""
    b = bytearray(MOD)
    for k in range(MOD):
        if k in (0x42, 0x43, 0x44, 0x45, 0x46, 0x4a):
            b[k] = r.choice([0, 0, 0, 1, 1, 2, 0x80, 0xff]) if r.random() < 0.5 else 0
        elif k in (0x47, 0x48, 0x49):
            b[k] = r.choice([0, 0, 1, 2, 5, 10, 50, 0x7f, 0x80, 0xfe, 0xff, r.randrange(256)])
        elif k >= 0x4c:
            b[k] = r.getrandbits(8) if tail and r.random() < 0.3 else 0
        else:
            b[k] = sbyte(r, p_zero)
    return b


def rand_floatv(r, lo=0.0, hi=1.0, edge=0.0):
    if r.random() < edge:
        return r.choice([-0.5, -3.7, -1.0, 0.99999994, 1.0, 2.5, 127.9, 1e6, 3.0e9, -3.0e9, 0.0])
    return r.uniform(lo, hi)


class Env:
    def __init__(self, ctx):
        self.ctx = ctx
        self.gs = ctx.g('g_status')
        self.gx = ctx.g('gXStatus')
        self.gcs = ctx.g('g_combat_state')
        self.screen = ctx.g('g_current_screen_state')
        self.settings = ctx.g('g_settings')
        self.level_data = ctx.g('g_level_data')
        self.sway = ctx.g('g_camera_sway_active')
        self.view = ctx.g('g_view_distance')
        self.camp = ctx.g('g_camp_screen')

    def char(self, s):
        return self.ctx.char(s)

    def row(self, s):
        return (self.gs + 8).deref() + s * ROW

    def entry(self, s):
        return self.gx + s * GX_ENTRY

    def party(self, c, r, occ):
        p = self.ctx.set_party(c, r)
        for s in range(8):
            c.set(self.row(s) + X_OCC, u8(occ[s]))
        return p

    def one(self, c, r, slot):
        blob, name = self.ctx.pick_char(r)
        c.setb(self.char(slot), bytes(blob))
        return blob, name

    def globals(self, c, surprise=1, combat=0, suspended=0, screen=None, started=None):
        c.set(self.gs + S_SUSPENDED, u8(suspended))
        c.set(self.gs + S_GREETING, b'\x01')
        c.set(self.gs + S_SKIPREACT, b'\x00')
        c.set(self.gs + S_INCURSOR, b'\x00')
        c.set(self.gx + GX_COMBAT, u8(combat))
        c.set(self.gx + GX_SURPRISE, u8(surprise))
        if not combat:
            c.set(self.gcs, u32(0))
        if screen is not None:
            c.set(self.screen, u32(screen))
        if started is not None:
            c.set(self.gs + S_STARTED, u8(started))

    def combat_state(self, c, dead_slots=range(8), scratch=7):
        """Scratch W8CombatState wired into g_combat_state; characters[s].dead = 1."""
        cs = self.ctx.scratch(scratch)
        c.setp(self.gcs, cs)
        for s in dead_slots:
            c.set(cs + CS_CHARS + s * CS_ROW + CS_DEAD, b'\x01')
        return cs

    def combat_caps(self, c, scratch=7):
        """In combat RecomputeCharacterHighestCondition also updates gXStatus.edited_formation
        and the combat state's saved formation: capture (and so restore) both."""
        c.cap(self.gx + GX_EDIT_FORMATION, FORMATION, 'edited_formation')
        c.cap(self.ctx.scratch(scratch) + CS_FORMATION, FORMATION, 'combat_formation')

    def death_guard(self, c, slots):
        for s in slots:
            c.set(self.row(s) + X_NPC, u32(0xffffffff))
        for s in range(8):
            c.set(self.row(s) + X_TOUT, u32(0))

    def android(self, c, s):
        """Note that slot s was made an Android (race 15). Androids are recruited NPCs
        only: CalcAttacks reads GetNpcState(XChar.npc_index), and a PC row's -1 reads
        the heap header before the NPC array (retail crashed at 0x0050b820 and left
        half-done state behind). caps() gives such a slot an in-range npc_index after
        every other set-up write (death_guard writes -1)."""
        c.__dict__.setdefault('w8_androids', set()).add(s)

    def caps(self, c, chars=range(8), rows=True, status=True, entries=True, flags=True):
        for s in sorted(c.__dict__.get('w8_androids', ())):
            c.set(self.row(s) + X_NPC, u32(0))
        for s in chars:
            c.cap(self.char(s), CHAR, 'char%d' % s, floats=CHAR_FLOATS)
        if rows:
            c.cap(self.row(0), 8 * ROW, 'xchar',
                  ignore=[s * ROW + o for s in range(8) for o in X_PTRS])
        if status:
            for a, b in S_CAPS:
                c.cap(self.gs + a, b - a, 'gstatus_%x' % a)
        if entries:
            c.cap(self.gx, 8 * GX_ENTRY, 'entries',
                  ignore=[s * GX_ENTRY + o for s in range(8) for o in E_IGNORE])
        if flags:
            c.cap(self.gx + GX_DIRTY, 1, 'encumbrance_dirty')
            c.cap(self.gx + GX_SIGHT, 1, 'sight_refresh')

    def wire_monsters(self, c, lst, mons):
        """lst: scratch Addr of a W8PList (data array at +0x100, empty unborn list at +0x40);
        mons: list of (scratch Addr, bytes) monster records."""
        n = len(mons)
        c.set(lst + 4, struct.pack('<ii', n + 2, n))
        c.setp(lst, lst + 0x100)
        for k, (addr, data) in enumerate(mons):
            c.set(addr, data)
            c.setp(lst + 0x100 + 4 * k, addr)
        c.setp(self.gx + GX_MONLIST, lst)
        c.setp(self.gx + GX_UNBORN, lst + 0x40)


def occupancy(r, p=0.85, force=()):
    occ = [1 if r.random() < p else 0 for _ in range(8)]
    for s in force:
        occ[s] = 1
    if not any(occ):
        occ[r.randrange(8)] = 1
    return occ


def cond_array(blob=None):
    if blob is None:
        return [0] * 20
    return [blob.get_u32(C_COND + 4 * k) for k in range(20)]


def highest_of(conds):
    for k in range(19, -1, -1):
        if conds[k]:
            return k
    return 0


def pblock(blob):
    """Mutable copy of the character block 0xb01..0xba9 (highest_condition .. spell rates)."""
    return Blob(bytes(blob[PB_LO:PB_HI]))


def pb_off(off):
    return off - PB_LO


def empty_items(n):
    return b''.join(struct.pack('<i', -1) + bytes(8) for _ in range(n))


def item_bytes(iid, count=0, uses=0, ident=1):
    return struct.pack('<IBBBB', iid & 0xffffffff, count & 0xff, uses & 0xff, ident, 0) + bytes(4)


def effect_slot(active, eid, amount, percent, duration):
    return struct.pack('<BIIII', active & 0xff, eid & 0xffffffff, amount & 0xffffffff,
                       percent & 0xffffffff, duration & 0xffffffff)


def ench_bytes(power, percent, magnitude, turns):
    return struct.pack('<IHHI', power & 0xffffffff, percent & 0xffff, magnitude & 0xffff,
                       turns & 0xffffffff)


def cases(ctx):
    E = Env(ctx)
    t_apply_modifier_block(ctx, E)
    t_apply_party_effect_slots(ctx, E)
    t_apply_combat_effect_slots(ctx, E)
    t_apply_enchantments(ctx, E)
    t_apply_conditions(ctx, E)
    t_accumulate_equipment(ctx, E)
    t_rebuild_char_modblock(ctx, E)
    t_rebuild_equipment_derived(ctx, E)
    t_rebuild_equipment_derived_slot(ctx, E)
    t_rebuild_conditions_derived(ctx, E)
    t_rebuild_party_effect_block(ctx, E)
    t_rebuild_monster_derived(ctx, E)
    t_char_regen_rates(ctx, E)
    t_monster_regen_rates(ctx, E)
    t_update_game_clock(ctx, E)
    t_game_turns_passed_char(ctx, E)
    t_age_monster_sight(ctx, E)
    t_update_camp_fatigue(ctx, E)
    t_update_party_stamina(ctx, E)
    t_resolve_surprise_wake(ctx, E)
    t_recalc_derived(ctx, E)
    t_carrying_capacity(ctx, E)
    t_carried_weight(ctx, E)
    t_redistribute(ctx, E)


# ===================================================================== Gameplay Mods.cpp
def t_apply_modifier_block(ctx, E):
    fn = ctx.fn(0x0050f090)  # void ApplyModifierBlock(W8GameplayModifierBlock*, const W8GameplayModifierBlock*)
    S0, S1 = ctx.scratch(0), ctx.scratch(1)
    for i in range(ctx.n(300)):
        r = ctx.rng('applymodblock', i)
        c = ctx.case('applymodblock.%d' % i, fn, conv='c', ret='v')
        tgt = rand_block(r, r.choice([0.3, 0.5, 0.8]))
        alias = r.random() < 0.05
        c.set(S0, bytes(tgt))
        if alias:
            c.arg(S0)
            c.arg(S0)
            c.note(alias=1)
        else:
            src = rand_block(r, r.choice([0.3, 0.5, 0.8]))
            if r.random() < 0.3:                  # ties on the max-combined bytes
                for k in (0x47, 0x48, 0x49):
                    if r.random() < 0.6:
                        src[k] = tgt[k]
            c.set(S1, bytes(src))
            c.arg(S0)
            c.arg(S1)
            c.cap(S1, MOD, 'source')
        c.cap(S0, MOD, 'target')


def rand_effect_slots(r, n, ids, other_ids, p_active):
    out = b''
    desc = []
    for k in range(n):
        x = r.random()
        active = 0
        if x < p_active:
            active = 1 if r.random() < 0.94 else r.choice([2, 0x80, 0xff])
        eid = r.choice(ids) if r.random() < 0.8 else r.choice(other_ids)
        amount = pick(r, [0, 1, 2, 0x7f, 0x80, 0xff, 0x100, 0x101, 51, 52, 63, 64, -1, -5,
                          0x7fffffff, -0x80000000], 0, 12, 0.3)
        percent = r.choice(PERCENTS)
        duration = r.choice([0, 1, 5, 100, INDEF, 0xffffffff, r.getrandbits(32)])
        out += effect_slot(active, eid, amount, percent, duration)
        if active:
            desc.append('%x:%x/%x/%x' % (k, eid & 0xffffffff, amount & 0xffffffff, percent))
    return out, desc


PARTY_IDS = [8, 0x11, 0x14, 0x1a, 0x20, 0x21, 0x28, 0x2d]
PARTY_OTHER = [0, 1, 7, 9, 0x10, 0x12, 0x13, 0x15, 0x1f, 0x22, 0x27, 0x29, 0x2c, 0x2e, 0x2f, 0x30,
               0x31, 0x35, 0x3b, 0x40, -1, 0x7fffffff, -0x80000000, 0x108]
COMBAT_IDS = [2, 0x35, 0x3b]
COMBAT_OTHER = [0, 1, 3, 0x31, 0x34, 0x36, 0x37, 0x3a, 0x3c, 0x14, 0x28, 8, -1, 0x7fffffff, 0x102]


def t_apply_party_effect_slots(ctx, E):
    fn = ctx.fn(0x0050edc0)  # void ApplyPartyEffectSlots(const W8EffectSlot*, W8GameplayModifierBlock*)
    S0, S1 = ctx.scratch(0), ctx.scratch(1)
    fixed = [(eid, amt, pct) for eid in PARTY_IDS
             for amt, pct in ((0, 0), (1, 0), (3, 50), (0xff, 0), (0x80, 100), (51, 0), (52, 155),
                              (-1, 0xffffff9c), (0x101, 0xffffffff))]
    for i in range(ctx.n(350)):
        r = ctx.rng('partyeffects', i)
        c = ctx.case('partyeffects.%d' % i, fn, conv='c', ret='v')
        if i < len(fixed):
            eid, amt, pct = fixed[i]
            slots = effect_slot(1, eid, amt, pct, 10) + bytes(11 * SLOT)
            desc = ['0:%x/%x/%x' % (eid, amt & 0xffffffff, pct)]
        else:
            slots, desc = rand_effect_slots(r, 12, PARTY_IDS, PARTY_OTHER,
                                            r.choice([0.2, 0.5, 0.8, 1.0]))
        c.set(S0, slots)
        c.set(S1, bytes(rand_block(r, r.choice([0.5, 0.9]))))
        c.arg(S0)
        c.arg(S1)
        c.cap(S1, MOD, 'target')
        c.cap(S0, 12 * SLOT, 'slots')
        c.note(slots=' '.join(desc))


def t_apply_combat_effect_slots(ctx, E):
    fn = ctx.fn(0x0050ef50)  # void ApplyCombatEffectSlots(const W8EffectSlot*, W8GameplayModifierBlock*)
    S0, S1 = ctx.scratch(0), ctx.scratch(1)
    fixed = [(eid, amt, pct) for eid in COMBAT_IDS
             for amt, pct in ((0, 0), (1, 0), (2, 50), (36, 0), (37, 0), (25, 100), (26, 0),
                              (0xff, 155), (-1, 0xffffffff))]
    for i in range(ctx.n(250)):
        r = ctx.rng('combateffects', i)
        c = ctx.case('combateffects.%d' % i, fn, conv='c', ret='v')
        if i < len(fixed):
            eid, amt, pct = fixed[i]
            slots = effect_slot(1, eid, amt, pct, 3) + bytes(5 * SLOT)
            desc = ['0:%x/%x/%x' % (eid, amt & 0xffffffff, pct)]
        else:
            slots, desc = rand_effect_slots(r, 6, COMBAT_IDS, COMBAT_OTHER,
                                            r.choice([0.3, 0.6, 1.0]))
        c.set(S0, slots)
        c.set(S1, bytes(rand_block(r, r.choice([0.5, 0.9]))))
        c.arg(S0)
        c.arg(S1)
        c.cap(S1, MOD, 'target')
        c.cap(S0, 6 * SLOT, 'slots')
        c.note(slots=' '.join(desc))


def t_apply_enchantments(ctx, E):
    fn = ctx.fn(0x0050ecc0)  # void ApplyEnchantmentModifiers(const W8Enchantment*, W8GameplayModifierBlock*)
    S0, S1 = ctx.scratch(0), ctx.scratch(1)
    for i in range(ctx.n(250)):
        r = ctx.rng('enchantmods', i)
        c = ctx.case('enchantmods.%d' % i, fn, conv='c', ret='v')
        data = b''
        desc = []
        p = r.choice([0.3, 0.6, 1.0])
        for k in range(8):
            turns = 0
            if r.random() < p or (i < 24 and k == 5 + i % 3):
                turns = r.choice([1, 2, 10, 100, INDEF, 0xffffffff, 0x80000000, r.getrandbits(32)])
            power = pick(r, [0, 1, 25, 26, 31, 32, 51, 52, 0x7f, 0x80, 0xff, 0x100, 0x101,
                             0xffffffff, 0x80000005], 0, 10, 0.35)
            pct = r.choice([0, 0, 0, 10, 50, 100, 155, 200, 255, 1000, 0xffff, 0x8000, 0xff9c])
            data += ench_bytes(power, pct, r.getrandbits(16), turns)
            if turns:
                desc.append('%d:%x/%x' % (k, power, pct))
        c.set(S0, data)
        c.set(S1, bytes(rand_block(r, r.choice([0.5, 0.9]))))
        c.arg(S0)
        c.arg(S1)
        c.cap(S1, MOD, 'target')
        c.note(ench=' '.join(desc))


def monster_record(loc, species, group=0x7a0001, **kw):
    """Bytes of a scratch W8MonsterInfo: identity plus the fields named in kw."""
    b = Blob(bytes(M_SIZE))
    b.u32(M_LOC, loc)
    b.u32(M_GROUP, group)
    b.u32(M_SPECIES, species)
    for off, val in kw.get('u32', {}).items():
        b.u32(off, val)
    for off, val in kw.get('u8', {}).items():
        b.u8(off, val)
    for off, val in kw.get('f32', {}).items():
        b.f32(off, val)
    for off, data in kw.get('raw', {}).items():
        b[off:off + len(data)] = data
    return bytes(b)


def wire_bound_monsters(E, c, r, lst_scratch=2, mon_scratch=3):
    """Scratch monster list for MonsterInfoFromID: 1..3 monsters with ids 0x5A000000+k*7."""
    ctx = E.ctx
    lst = ctx.scratch(lst_scratch)
    mons = []
    ids = []
    for k in range(r.randint(1, 3)):
        loc = 0x5A000000 + k * 7 + r.randrange(3)
        sp = r.choice(SPECIES_IDS)
        mons.append((ctx.scratch(mon_scratch) + k * M_STRIDE, monster_record(loc, sp)))
        ids.append((loc, sp))
    E.wire_monsters(c, lst, mons)
    return ids


def t_apply_conditions(ctx, E):
    """void ApplyConditionModifiers(W8Character*, const unsigned*, int, W8GameplayModifierBlock*)"""
    fn = ctx.fn(0x0050eac0)
    S0, S1 = ctx.scratch(0), ctx.scratch(1)
    for i in range(ctx.n(350)):
        r = ctx.rng('condmods', i)
        c = ctx.case('condmods.%d' % i, fn, conv='c', ret='v')
        with_char = r.random() < 0.75
        conds = [0] * 20
        p = r.choice([0.1, 0.25, 0.5, 0.8])
        for k in range(20):
            if r.random() < p:
                conds[k] = r.choice([1, 2, 5, 30, INDEF, 0xffffffff, 0x80000000])
        if i < 40:                                    # each handled condition alone
            conds = [0] * 20
            conds[i % 20] = r.choice([1, INDEF])
        note = {}
        if not with_char:
            conds[0x13] = 0                           # CharacterPointerToPartySlot(NULL) crashes
            c.arg(0)
            arg_turns = S0
            c.set(S0, arr32(conds))
        else:
            slot = r.randrange(8)
            blob, name = E.one(c, r, slot)
            ch = E.char(slot)
            note.update(char=name, slot=slot)
            inparty = 1 if r.random() < 0.95 else 0
            c.set(ch + C_INPARTY, u8(inparty))
            if r.random() < 0.4 or conds[BLIND]:
                prof = 6 if r.random() < 0.6 else r.randrange(15)    # Monk: trait 7
                lv = pick(r, [0, 1, 20, 21, 50, 0xffffffff, 0x80000000], 0, 30, 0.35)
                c.set(ch + C_PROF, u32(prof))
                c.set(ch + C_PLEV + 4 * prof, u32(lv))
                note.update(prof=prof, prof_level=lv)
            if conds[0x13] or r.random() < 0.1:
                if not conds[0x13]:
                    conds[0x13] = r.choice([1, INDEF])
                ids = wire_bound_monsters(E, c, r)
                level = r.choice([2, 3, 17, 21, 0])
                acquired = level if r.random() < 0.7 else r.choice([level + 1, -1, 0x2e])
                x = r.random()
                if x < 0.65:
                    src = r.choice(ids)[0]
                elif x < 0.85:
                    src = 0x5A0000FF                       # not found: assert + -5
                else:
                    src = r.choice([0, -1])
                active = 1 if r.random() < 0.85 else r.choice([0, 2, 0xff])
                c.set(E.gs + S_LEVEL, u32(level))
                c.set(ch + C_CONDREC + CR_STEP, struct.pack('<iiB', acquired, src, active))
                note.update(level=level, acquired=acquired, src='%x' % (src & 0xffffffff),
                            active=active, monsters=';'.join('%x:%d' % m for m in ids))
            c.arg(ch)
            if r.random() < 0.3:
                c.set(ch + C_COND, arr32(conds))
                arg_turns = ch + C_COND
                note['turns'] = 'char'
            else:
                c.set(S0, arr32(conds))
                arg_turns = S0
            if inparty == 0:
                note['edge'] = 'not_in_party'
        arg = pick(r, [0, 1, 0x7f, 0x80, 0xff, 0x100, 0x7fffffff, -1, -0x80000000], 0, 20, 0.3)
        c.arg(arg_turns)
        c.arg(arg)
        c.set(S1, bytes(rand_block(r, r.choice([0.5, 0.9]))))
        c.arg(S1)
        c.cap(S1, MOD, 'target')
        note.update(conds=''.join('%x,' % k for k in range(20) if conds[k]), arg=s32(arg))
        c.note(**note)


def equip_choice(r):
    x = r.random()
    if x < 0.25:
        return -1
    if x < 0.65:
        return r.choice(IT_BONUS)
    return r.randrange(ITEM_COUNT)


def t_accumulate_equipment(ctx, E):
    """void AccumulateEquipmentModifiers(W8Character*, W8GameplayModifierBlock*)"""
    fn = ctx.fn(0x0050e980)
    S0 = ctx.scratch(0)
    for i in range(ctx.n(300)):
        r = ctx.rng('accumequip', i)
        c = ctx.case('accumequip.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        blob, name = E.one(c, r, slot)
        ch = E.char(slot)
        x = r.random()
        if x < 0.15:
            equip = [r.choice(IT_RES_HIGH) for _ in range(12)]        # resistance clamp
        elif x < 0.2:
            equip = [-1] * 12
        else:
            equip = [equip_choice(r) for _ in range(12)]
        data = b''.join(item_bytes(e, r.randrange(3), r.randrange(4)) for e in equip)
        c.set(ch + C_EQUIP, data)
        blk = rand_block(r, r.choice([0.6, 0.95, 1.0]))
        c.set(S0, bytes(blk))
        c.arg(ch)
        c.arg(S0)
        c.cap(S0, MOD, 'block')
        c.cap(ch, CHAR, 'char', floats=CHAR_FLOATS)
        c.note(char=name, equip=','.join(str(e) for e in equip))


def t_rebuild_char_modblock(ctx, E):
    """void RebuildCharacterModifierBlock(W8Character*)"""
    fn = ctx.fn(0x0050f030)
    for i in range(ctx.n(250)):
        r = ctx.rng('rebuildmodblock', i)
        c = ctx.case('rebuildmodblock.%d' % i, fn, conv='c', ret='v')
        scratch = r.random() < 0.1
        if scratch:
            blob, name = ctx.pick_char(r)
            ch = ctx.scratch(5)
            c.set(ch, bytes(blob))
        else:
            slot = r.randrange(8)
            blob, name = E.one(c, r, slot)
            ch = E.char(slot)
        inparty = r.choice([1, 1, 1, 0]) if r.random() < 0.95 else r.choice([2, 0x80, 0xff])
        c.set(ch + C_INPARTY, u8(inparty))
        c.set(ch + C_CONDMOD, bytes(rand_block(r, r.choice([0.6, 0.9]))))
        c.set(ch + C_EQBONUS, bytes(rand_block(r, r.choice([0.5, 0.8]))))
        c.set(ch + C_BONUS, bytes(r.getrandbits(8) for _ in range(MOD)))
        c.set(E.gs + S_PARTYMOD, bytes(rand_block(r, r.choice([0.7, 0.95]))))
        c.arg(ch)
        c.cap(ch, CHAR, 'char', floats=CHAR_FLOATS)
        c.cap(E.gs + S_PARTYMOD, MOD, 'party_modifiers')
        c.note(char=name, in_party=inparty, scratch=int(scratch))
        if inparty not in (0, 1):
            c.note(edge='bool_byte')


# ----------------------------------------------------------------- derived-stat chain
def mutate_for_derived(c, r, E, ch, blob, note, rebuild_bonus):
    """Field changes the derived chain reads (equipment, levels, attributes base, iron skin,
    capacity/inventory, load, bonus blocks)."""
    edge = r.random() < 0.12
    if r.random() < 0.6:                                  # equipment
        n = r.randint(1, 4)
        for _ in range(n):
            e = r.randrange(12)
            iid = equip_choice(r) if r.random() < 0.7 else r.choice(IT_HEAVY)
            c.set(ch + C_EQUIP + ITEM * e, item_bytes(iid, r.randrange(3)))
        note['equip_changes'] = n
    if r.random() < 0.3:                                  # backpack stacks
        k = r.randrange(8)
        iid, w = r.choice(IT_STACK)
        cnt = r.choice([0, 1, 5, 20, 100, 255])
        c.set(ch + C_PACK + ITEM * k, item_bytes(iid, cnt))
        note['pack'] = '%d:%dx%d' % (k, iid, cnt)
    if r.random() < 0.35:
        lvl = pick(r, [0, 1, 49, 50, 51, 0xffffffff, 0x80000000] if edge else [1, 50, 51],
                   1, 30, 0.3)
        c.set(ch + C_LEVEL, u32(lvl))
        note['level'] = lvl
    if r.random() < 0.35:
        levels = [blob.get_u32(C_PLEV + 4 * k) for k in range(15)]
        for _ in range(r.randint(1, 3)):
            levels[r.randrange(15)] = r.choice([0, 1, 20, 21, 50, 51, 100, 0xffffffff] if edge
                                               else [0, 1, r.randint(1, 30)])
        c.set(ch + C_PLEV, arr32(levels))
        note['prof_levels'] = levels
    if r.random() < 0.3:
        a = r.choice([A_STR, A_VIT, A_SPD, A_SEN, A_DEX])
        v = pick(r, [0, 1, 125, 126, 255, 0xffffffff] if edge else [1, 125], 1, 125, 0.25)
        c.set(ch + C_ATTR + a * ATTR_STEP, u32(v))
        note['attr_base'] = (a, v)
    if r.random() < 0.3:
        active = 1 if r.random() < 0.7 else r.choice([0, 2, 0xff])
        lvl = pick(r, [0, 3, 4, 125, 0xffffffff], 0, 100, 0.25)
        c.set(ch + C_SKILL + SK_IRON * SK_STEP, u8(active))
        c.set(ch + C_SKILL + SK_IRON * SK_STEP + 6, u32(lvl))
        note['iron_skin'] = (active, lvl)
    if r.random() < 0.35:
        cap = pick(r, [1, 12, 0x7fffffff, 0xffffffff, blob.get_u32(C_CAP)], 100, 4000, 0.3)
        inv = pick(r, [0, cap, cap + 1, 0x80000000], 0, 3000, 0.25)
        share = r.choice([0, blob.get_u32(C_SHARE), r.randint(0, 2000)])
        c.set(ch + C_INVW, arr32([inv, share, r.getrandbits(16), cap]))
        note.update(capacity=cap, inventory=inv, share=share)
    if r.random() < 0.25:
        c.set(ch + C_LOAD, u32(r.choice([0, 1, 2, 3, 4])))
    if r.random() < 0.15:
        c.set(ch + C_FATBAND, u32(r.choice([0, 1, 2, 3, 4])))
    if rebuild_bonus:
        if r.random() < 0.5:
            c.set(ch + C_CONDMOD, bytes(rand_block(r, 0.85, tail=False)))
        if r.random() < 0.4:
            c.set(E.gs + S_PARTYMOD, bytes(rand_block(r, 0.9, tail=False)))
    else:
        if r.random() < 0.6:
            c.set(ch + C_BONUS, bytes(rand_block(r, 0.85, tail=False)))
    if edge:
        note['edge_values'] = 1


def derived_env(ctx, E, c, r, target_slots, note):
    """Party + globals for the derived-stat chain; returns (party, combat)."""
    occ = occupancy(r, 0.9, force=target_slots)
    party = E.party(c, r, occ)
    combat = r.random() < 0.12
    screen = r.choice([SCREEN_MAIN] * 7 + [SCREEN_CHARACTER] * 2 + [SCREEN_CAMP, SCREEN_AUTOMAP])
    started = 1 if r.random() < 0.88 else 0
    E.globals(c, surprise=1, combat=int(combat), screen=screen, started=started)
    if combat:
        E.combat_state(c, dead_slots=[s for s in range(8) if occ[s]])
        E.combat_caps(c)
    if screen == SCREEN_CAMP:
        c.setp(E.camp, ctx.scratch(6))
        c.cap(ctx.scratch(6), 0x100, 'camp_screen')
    c.set(E.gx + GX_NPCDLG, u8(1 if r.random() < 0.1 else 0))
    E.death_guard(c, target_slots)
    note.update(occ=''.join(map(str, occ)), combat=int(combat), screen=screen, started=started)
    return party, combat


def t_rebuild_equipment_derived(ctx, E):
    """void RebuildEquipmentAndDerivedStats(W8Character*)"""
    fn = ctx.fn(0x0050e540)
    for i in range(ctx.n(200)):
        r = ctx.rng('rebuildequip', i)
        c = ctx.case('rebuildequip.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        note = {'slot': slot}
        party, combat = derived_env(ctx, E, c, r, [slot], note)
        blob = party[slot][1]
        ch = E.char(slot)
        note['char'] = party[slot][2]
        mutate_for_derived(c, r, E, ch, blob, note, rebuild_bonus=True)
        c.set(ch + C_EQBONUS, bytes(r.getrandbits(8) for _ in range(MOD)))   # rebuilt
        c.arg(ch)
        E.caps(c)
        c.note(**note)


def t_rebuild_equipment_derived_slot(ctx, E):
    """void RebuildEquipmentAndDerivedStatsForSlot(int party_slot)"""
    fn = ctx.fn(0x0050e5c0)
    for i in range(ctx.n(120)):
        r = ctx.rng('rebuildequipslot', i)
        c = ctx.case('rebuildequipslot.%d' % i, fn, conv='c', ret='v')
        slot = i % 8 if i < 16 else r.randrange(8)
        note = {'slot': slot}
        party, combat = derived_env(ctx, E, c, r, [slot], note)
        blob = party[slot][1]
        ch = E.char(slot)
        note['char'] = party[slot][2]
        mutate_for_derived(c, r, E, ch, blob, note, rebuild_bonus=True)
        c.arg(slot)
        E.caps(c)
        c.note(**note)


def t_rebuild_conditions_derived(ctx, E):
    """void RebuildConditionsAndDerivedStats(int party_slot)"""
    fn = ctx.fn(0x0050e650)
    for i in range(ctx.n(250)):
        r = ctx.rng('rebuildconds', i)
        c = ctx.case('rebuildconds.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        note = {'slot': slot}
        party, combat = derived_env(ctx, E, c, r, [slot], note)
        blob = party[slot][1]
        ch = E.char(slot)
        note['char'] = party[slot][2]
        conds = cond_array(blob)
        p = r.choice([0.05, 0.15, 0.3])
        for k in range(1, 20):
            if k in (DEAD, MISSING):
                continue
            if r.random() < p:
                conds[k] = r.choice([1, 3, 20, INDEF])
        if r.random() < 0.08:
            conds[DEAD] = INDEF
        if r.random() < 0.15:
            conds[0x13] = INDEF
            ids = wire_bound_monsters(E, c, r)
            level = r.choice([2, 3, 17])
            acquired = level if r.random() < 0.7 else level + 1
            src = r.choice(ids)[0] if r.random() < 0.8 else 0x5A0000FF
            c.set(E.gs + S_LEVEL, u32(level))
            c.set(ch + C_CONDREC + CR_STEP, struct.pack('<iiB', acquired, src, 1))
            note.update(bound='%x' % src, level=level, acquired=acquired)
        ench = b''
        for k in range(8):
            turns = r.choice([0, 0, 0, 5, INDEF]) if r.random() < 0.5 else 0
            if k in (5, 6, 7) and r.random() < 0.3:
                turns = r.choice([3, INDEF])
            ench += ench_bytes(pick(r, [0, 1, 25, 26, 51, 52, 32, 0xff], 0, 8, 0.3),
                               r.choice([0, 0, 50, 100, 155, 0xffff]), r.getrandbits(16), turns)
        c.set(ch + C_COND, arr32(conds) + bytes(blob[C_COND + 80:C_ENCH]) + ench)
        hc = highest_of(conds)
        c.set(ch + C_HIGHEST, u32(hc))
        c.set(ch + C_CONDARG, u32(pick(r, [0, 1, 0xff, 0x100, 0x7fffffff], 0, 20, 0.3)))
        bound = 1 if r.random() < 0.2 else 0
        c.set(E.row(slot) + X_BOUND, u8(bound))
        if r.random() < 0.3:
            prof = r.choice([6, 6, 2, 13, r.randrange(15)])
            c.set(ch + C_PROF, u32(prof))
            note['prof'] = prof
        mutate_for_derived(c, r, E, ch, blob, note, rebuild_bonus=False)
        c.set(ch + C_CONDMOD, bytes(r.getrandbits(8) for _ in range(MOD)))   # rebuilt
        c.arg(slot)
        E.caps(c)
        note.update(conds=''.join('%x,' % k for k in range(20) if conds[k]), npc_bound=bound)
        c.note(**note)


def t_rebuild_party_effect_block(ctx, E):
    """void RebuildPartyEffectBlock(void)"""
    fn = ctx.fn(0x0050e700)
    n = ctx.n(200)
    for i in range(n):
        r = ctx.rng('partyeffectblock', i)
        c = ctx.case('partyeffectblock.%d' % i, fn, conv='c', ret='v')
        natural = i == n - 1
        occ = occupancy(r, 0.85)
        party = E.party(c, r, occ)
        combat = (not natural) and r.random() < 0.25
        screen = r.choice([SCREEN_MAIN] * 8 + [SCREEN_CHARACTER, SCREEN_AUTOMAP])
        E.globals(c, surprise=1, combat=int(combat), screen=screen, started=1)
        note = {'occ': ''.join(map(str, occ)), 'combat': int(combat)}
        if not natural:
            slots, desc = rand_effect_slots(r, 12, PARTY_IDS, PARTY_OTHER,
                                            r.choice([0.1, 0.3, 0.6]))
            c.set(E.gs + S_EFFECTS, slots)
            note['party_slots'] = ' '.join(desc)
        else:
            note['natural'] = 1
        if combat:
            cs = E.combat_state(c, dead_slots=[s for s in range(8) if occ[s]])
            E.combat_caps(c)
            cslots, cdesc = rand_effect_slots(r, 9, [0x31, 0x31, 2, 0x35], COMBAT_OTHER,
                                              r.choice([0.2, 0.5]))
            c2, c2desc = rand_effect_slots(r, 6, COMBAT_IDS, COMBAT_OTHER, r.choice([0.2, 0.5]))
            c.set(cs + CS_EFFECTS, cslots + c2)
            note['combat_slots'] = ' '.join(cdesc + ['|'] + c2desc)
        if r.random() < 0.45:                       # Bard (camp recovery latch)
            s = r.randrange(8)
            c.set(E.char(s) + C_PROF, u32(9))
            x = r.random()
            hp = 0 if x < 0.15 else party[s][1].get_u32(C_HP) or 1
            hc = r.choice([1, 2, 15, 0x80000000]) if 0.15 <= x < 0.3 else 0
            c.set(E.char(s) + C_HIGHEST, u32(hc))
            c.set(E.char(s) + C_HP, u32(hp))
            note.update(bard=s, bard_hp=hp, bard_cond=hc)
            if hc >= 0x80000000:
                note['edge'] = 'cond_negative'
        E.death_guard(c, [s for s in range(8) if occ[s]])
        E.caps(c)
        c.note(**note)


def monster_fields(r, loc, species, in_combat, edge):
    """A W8MonsterInfo for the modifier rebuild: conditions (no 0x13), enchantments, effect
    slots, garbage in the rebuilt modifier block and attributes."""
    b = Blob(bytes(M_SIZE))
    b.u32(M_LOC, loc)
    b.u32(M_GROUP, 0x7a0001)
    b.u32(M_SPECIES, species)
    b.u8(M_ACTIVE, 1)
    b.u8(M_INCOMBAT, in_combat)
    hpmax = pick(r, [0, 1, 0x7fffffff, 0xffffffff] if edge else [1, 2000], 5, 600, 0.2)
    b.u32(M_HPMAX, hpmax)
    b.u32(M_HP, r.randint(0, max(1, hpmax & 0xffff)))
    stmax = pick(r, [0, 1, 0x80000000, 0xffffffff] if edge else [1, 2000], 10, 400, 0.2)
    b.u32(M_STMAX, stmax)
    b.u32(M_ST, r.randint(0, max(1, stmax & 0xffff)))
    p = r.choice([0.05, 0.2, 0.4])
    conds = [0] * 20
    for k in range(1, 19):
        if r.random() < p:
            conds[k] = r.choice([1, 5, 30, INDEF])
    for k in range(20):
        b.u32(M_COND + 4 * k, conds[k])
    b.u32(M_HIGHEST, highest_of(conds))
    b.u32(M_CONDARG, pick(r, [0, 1, 0xff, 0x100, 0xffffffff], 0, 30, 0.3))
    for k in range(8):
        turns = r.choice([0, 0, 0, 3, INDEF]) if r.random() < 0.6 else 0
        if k in (5, 6, 7) and r.random() < 0.35:
            turns = r.choice([3, INDEF])
        b[M_ENCH + ENCH * k:M_ENCH + ENCH * (k + 1)] = ench_bytes(
            pick(r, [0, 1, 25, 26, 51, 52, 32, 0xff], 0, 8, 0.3),
            r.choice([0, 0, 50, 100, 155, 0xffff]), r.getrandbits(16), turns)
    slots, desc = rand_effect_slots(r, 12, PARTY_IDS, PARTY_OTHER, r.choice([0.1, 0.3, 0.6]))
    b[M_EFFECTS:M_EFFECTS + 12 * SLOT] = slots
    b[M_MODS:M_MODS + MOD] = bytes(r.getrandbits(8) for _ in range(MOD))
    b[M_ATTRS:M_ATTRS + 5] = bytes(r.getrandbits(8) for _ in range(5))
    b.f32(M_HRATE, r.uniform(-5, 5))
    b.f32(M_SRATE, r.uniform(-5, 5))
    return b, conds, desc


def t_rebuild_monster_derived(ctx, E):
    """void RebuildMonsterDerivedStats(int location_id)"""
    fn = ctx.fn(0x0050e8c0)
    lst = ctx.scratch(0)
    mons = ctx.scratch(1)
    pc = ctx.scratch(2)
    for i in range(ctx.n(200)):
        r = ctx.rng('monsterderived', i)
        c = ctx.case('monsterderived.%d' % i, fn, conv='c', ret='v')
        n = r.randint(1, 3)
        target = r.randrange(n)
        records = []
        note = {}
        for k in range(n):
            loc = 0x5B000000 + 0x10 * k + r.randrange(16)
            sp = r.choice(SPECIES_IDS)
            if k == target:
                in_combat = 1 if r.random() < 0.4 else 0
                if r.random() < 0.04:
                    in_combat = r.choice([2, 0xff])
                b, conds, desc = monster_fields(r, loc, sp, in_combat, r.random() < 0.1)
                note.update(loc='%x' % loc, species=sp, in_combat=in_combat,
                            conds=''.join('%x,' % q for q in range(20) if conds[q]),
                            slots=' '.join(desc))
                tloc = loc
            else:
                b = Blob(monster_record(loc, sp))
            records.append((mons + k * M_STRIDE, bytes(b)))
        E.wire_monsters(c, lst, records)
        taddr = mons + target * M_STRIDE
        if note['in_combat']:
            cslots, cdesc = rand_effect_slots(r, 9, [0x31, 0x31, 2, 0x35], COMBAT_OTHER,
                                              r.choice([0.2, 0.5]))
            c2, c2desc = rand_effect_slots(r, 6, COMBAT_IDS, COMBAT_OTHER, r.choice([0.2, 0.5]))
            c.set(pc + MC_EFFECTS, cslots + c2)
            c.setp(taddr + M_PCOMBAT, pc)
            note['combat_slots'] = ' '.join(cdesc + ['|'] + c2desc)
        c.arg(tloc)
        c.cap(taddr, M_SIZE, 'monster', ignore=M_PTRS, floats=M_FLOATS)
        c.cap(pc, MC_SIZE, 'monster_combat')
        c.note(**note)


# ===================================================================== GameplayTime.cpp
def t_char_regen_rates(ctx, E):
    """void RebuildCharacterRegenRates(W8Character*)"""
    fn = ctx.fn(0x00502b50)
    for i in range(ctx.n(300)):
        r = ctx.rng('charregen', i)
        c = ctx.case('charregen.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        blob, name = E.one(c, r, slot)
        ch = E.char(slot)
        edge = r.random() < 0.2
        hpmax = blob.get_u32(C_HPMAX)
        stmax = blob.get_u32(C_STMAX)
        if r.random() < 0.6:
            hpmax = pick(r, [0, 1, 0x7fffffff, 0x80000000, 0xffffffff, 0x01000001] if edge
                         else [0, 1, 999], 1, 600, 0.3)
        if r.random() < 0.6:
            stmax = pick(r, [0, 1, 0x7fffffff, 0x80000000, 0xffffffff, 0x00ffffff] if edge
                         else [0, 1, 999], 1, 600, 0.3)
        c.set(ch + C_HPMAX, u32(hpmax))
        c.set(ch + C_STMAX, u32(stmax))
        sp = [blob.get_u32(C_SPMAX + 4 * k) for k in range(6)]
        if r.random() < 0.6:
            sp = [r.choice([0, 0, r.randint(1, 400), 0xffffffff if edge else 7,
                            0x80000000 if edge else 50]) for _ in range(6)]
        c.set(ch + C_SPMAX, arr32(sp))
        boosts = [r.choice([0, 0, 1]) if r.random() < 0.9 else r.choice([2, 0x80, 0xff])
                  for _ in range(3)]
        c.set(ch + C_BONUS + B_BOOST, bytes(boosts))
        c.set(ch + C_HRATE, bytes(r.getrandbits(8) for _ in range(0x40)))   # rebuilt/kept
        c.arg(ch)
        c.cap(ch, CHAR, 'char', floats=CHAR_FLOATS)
        c.note(char=name, hpmax=hpmax, stmax=stmax, sp_max=sp, boosts=boosts)


def t_monster_regen_rates(ctx, E):
    """void RebuildMonsterRegenRates(W8MonsterInfo*)"""
    fn = ctx.fn(0x00502c50)
    S0 = ctx.scratch(0)
    for i in range(ctx.n(250)):
        r = ctx.rng('monsterregen', i)
        c = ctx.case('monsterregen.%d' % i, fn, conv='c', ret='v')
        edge = r.random() < 0.2
        hpmax = pick(r, [0, 1, 0x7fffffff, 0x80000000, 0xffffffff, 0x01000001] if edge
                     else [0, 1, 5000], 1, 800, 0.25)
        stmax = pick(r, [0, 1, 0x7fffffff, 0x80000000, 0xffffffff] if edge else [0, 1, 5000],
                     1, 500, 0.25)
        hadj = sbyte(r, 0.5)
        sadj = sbyte(r, 0.5)
        boosts = [r.choice([0, 0, 1]) if r.random() < 0.9 else r.choice([2, 0xff])
                  for _ in range(2)]
        b = Blob(bytes(r.getrandbits(8) for _ in range(M_SIZE)))
        b.u32(M_HPMAX, hpmax)
        b.u32(M_STMAX, stmax)
        b.u8(M_MODS + B_HREG, hadj)
        b.u8(M_MODS + B_SREG, sadj)
        b.u8(M_MODS + B_BOOST, boosts[0])
        b.u8(M_MODS + B_BOOST + 1, boosts[1])
        for o in M_FLOATS:
            b.f32(o, r.uniform(-10, 10))
        c.set(S0, bytes(b))
        c.arg(S0)
        c.cap(S0, M_SIZE, 'monster', floats=M_FLOATS)
        c.note(hpmax=hpmax, stmax=stmax, hadj=s32(hadj if hadj < 128 else hadj - 256),
               sadj=sadj if sadj < 128 else sadj - 256, boosts=boosts)


def place_item(c, E, r, slot, blob, iid, uses=0, count=0):
    """Put iid into an equipment or backpack slot of party slot `slot`."""
    if r.random() < 0.5:
        k = r.randrange(12)
        c.set(E.char(slot) + C_EQUIP + ITEM * k, item_bytes(iid, count, uses))
        return 'e%d' % k
    k = r.randrange(8)
    c.set(E.char(slot) + C_PACK + ITEM * k, item_bytes(iid, count, uses))
    return 'b%d' % k


def scuba_slots(blob):
    return [k for k in range(12) if struct.unpack_from('<i', blob, C_EQUIP + ITEM * k)[0] == SCUBA]


def has_item(blob, iid, backpack=True):
    for k in range(12):
        if struct.unpack_from('<i', blob, C_EQUIP + ITEM * k)[0] == iid:
            return True
    if backpack:
        for k in range(8):
            if struct.unpack_from('<i', blob, C_PACK + ITEM * k)[0] == iid:
                return True
    return False


def set_scuba(c, E, r, slot, blob, want):
    """Make FindItemOnCharacter(slot, 0x1e5, equipment only) answer `want`."""
    eq = scuba_slots(blob)
    if want and not eq:
        k = r.choice([1, 2])
        c.set(E.char(slot) + C_EQUIP + ITEM * k, item_bytes(SCUBA))
    elif not want:
        for k in eq:
            c.set(E.char(slot) + C_EQUIP + ITEM * k, empty_items(1))


def t_update_game_clock(ctx, E):
    """void UpdateGameClock(int elapsed)"""
    fn = ctx.fn(0x00502010)
    elapsed_edges = [0, 1, 16, 17, 33, 50, 100, 250, 999, 1000, 1001, 1399, 1400, 1401, 2499,
                     2500, 2501, 5000, 10000, 60000]
    for i in range(ctx.n(300)):
        r = ctx.rng('gameclock', i)
        c = ctx.case('gameclock.%d' % i, fn, conv='c', ret='v')
        combat = r.random() < 0.2
        surprise = 1 if r.random() < 0.7 else 0
        drag = (not combat) and r.random() < 0.15
        sway = 1 if r.random() < 0.6 else 0
        elapsed = r.choice(elapsed_edges) if r.random() < 0.4 else r.randint(1, 200)
        if surprise and r.random() < 0.06:
            elapsed = r.choice([-1, -1000, -0x80000000])
            if not combat:
                drag = True
        if surprise == 0:                        # no camp damage: keep the ticks small
            elapsed = min(elapsed, 5000)
        occ = occupancy(r, 0.85, force=[0] if surprise == 0 else ())
        party = E.party(c, r, occ)
        E.globals(c, surprise=surprise, combat=int(combat), screen=SCREEN_MAIN)
        note = {'elapsed': elapsed, 'combat': int(combat), 'surprise': surprise,
                'drag': int(drag), 'sway': sway, 'occ': ''.join(map(str, occ))}
        # clocks
        wc = pick(r, [0, 0x7fffffff, 0x7ffffffe, 0xffffffff, 0x80000000], 0, 50000000, 0.15)
        wms = pick(r, [0, 999, 1000, 0xffffffff, 0x7fffffff], 0, 999, 0.1)
        c.set(E.gs + S_CLOCK, arr32([wc, wms]))
        e32 = elapsed & 0xffffffff
        if drag:
            aging = pick(r, [0, 119999, 120000, 0xffffffff, 5000000], 0, 119999, 0.4)
        else:
            room = (120000 - e32 - 1) & 0xffffffff
            if room >= 120000:
                aging = (r.randrange(1, 120000) - e32) & 0xffffffff   # wraps below 120000
            else:
                aging = r.randint(0, room)
        x = r.random()
        if x < 0.25:
            recharge = (3600000 - e32 + r.choice([0, 0, 1, -1, 5000])) & 0xffffffff
        elif x < 0.32:
            recharge = r.choice([3600000 * 130, 3600000 * 255, 0xffffffff - e32, 3600000 * 3 - e32])
        else:
            recharge = r.randint(0, 3599999)
        wait = r.choice([0, 1, 2, 3, 3, 3])
        c.set(E.gs + S_AGING, arr32([aging]) + b'\x00' + u8(0) + f32(0) + f32(0) +
              arr32([wait, recharge]))
        note.update(clock=wc, clock_ms=wms, aging=aging, recharge=recharge)
        fatigued = 1 if r.random() < 0.3 else 0
        count = pick(r, [0, 5, 6, 11, 12, 0x5f9, 0xffffffff], 0, 40, 0.15)
        camptick = pick(r, [0, 2499, 2500, 0xffffffff], 0, 2499, 0.15)
        stamtick = pick(r, [0, 1399, 1400, 0xffffffff], 0, 1399, 0.15)
        if surprise == 0:
            count = min(count, 30)
            camptick = min(camptick, 2499)
        c.set(E.gs + S_FATIGUED, u8(fatigued))
        c.set(E.gs + S_CAMPTICK, u32(camptick))
        c.set(E.gs + S_STAMTICK, u32(stamtick))
        c.set(E.gs + S_CAMPCOUNT, u32(count))
        c.set(E.sway, u8(sway))
        c.set(E.gx + GX_DRAG, u8(1 if drag else 0))
        unengaged = 0
        if surprise and r.random() < 0.1:
            unengaged = 1
            c.set(E.gx + GX_PHASE, u16(r.choice([0, 2, 3])))
        c.set(E.gx + GX_UNENGAGED, u8(unengaged))
        flags = LEVEL_WALK | (LEVEL_FAST if r.random() < 0.2 else 0) | \
            (LEVEL_MOVED if r.random() < 0.3 else 0)
        c.set(E.level_data.deref(), u32(flags))
        note.update(count=count, camptick=camptick, stamtick=stamtick, fatigued=fatigued,
                    unengaged=unengaged, level_flags='%x' % flags)
        # Solar Powerpaks (0x266): recharged hourly on occupied characters and in the pool
        paks = []
        for _ in range(r.choice([0, 1, 2, 3])):
            s = r.randrange(8)
            uses = r.choice([0, 1, 5, 9, 10, 0x7f, 0x80, 0xff, r.randrange(256)])
            paks.append('%d%s:%d' % (s, place_item(c, E, r, s, party[s][1], SOLAR_PAK, uses), uses))
        k = r.choice([0, 0, 1, 2, 4])
        pool = b''
        for q in range(k):
            iid = SOLAR_PAK if r.random() < 0.6 else r.choice([100, 300, 614, 580])
            pool += item_bytes(iid, 0, r.choice([0, 3, 0xfe, r.randrange(256)]))
        c.set(E.gs + S_POOLN, u32(k))
        if pool:
            c.set(E.gs + S_POOL, pool)
        note.update(paks=' '.join(paks), pool=k)
        # stamina inputs
        for s in range(8):
            if not occ[s] or r.random() < 0.5:
                continue
            blob = party[s][1]
            pb = pblock(blob)
            stmax = pb.get_u32(pb_off(C_STMAX))
            st = r.choice([0, 1, stmax, max(0, stmax - r.randint(1, 50)), r.randint(0, 400)])
            if surprise == 0 or s == 0:
                st = max(st, 150)
                stmax = max(stmax, st)
            pb.u32(pb_off(C_STMAX), stmax)
            pb.u32(pb_off(C_ST), st)
            pb.f32(pb_off(C_SACC), rand_floatv(r, 0, 1))
            c.set(E.char(s) + PB_LO, bytes(pb))
            if r.random() < 0.3:
                c.set(E.char(s) + C_BONUS + B_SREG, u8(r.choice([0, 1, 2, -1, -3]) if s else 0))
        if surprise == 0:                       # slot 0 must stay eligible (no BeginPartyCamping)
            c.set(E.char(0) + C_HP, u32(500))
            c.set(E.char(0) + C_HPMAX, u32(500))
            c.set(E.char(0) + C_HIGHEST, u32(0))
            c.set(E.char(0) + C_BONUS + B_SREG, u8(0))
        if sway and not combat and surprise:
            E.death_guard(c, [s for s in range(8) if occ[s]])
        E.caps(c)
        c.note(**note)


def t_game_turns_passed_char(ctx, E):
    """void GameTurnsPassedChar(int party_slot, unsigned int minutes)"""
    fn = ctx.fn(0x00503100)
    minutes_edges = [0, 1, 1, 1, 2, 2, 3, 5, 10, 30, 60, 120, 1000]
    for i in range(ctx.n(400)):
        r = ctx.rng('turnspassed', i)
        c = ctx.case('turnspassed.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        combat = r.random() < 0.12
        surprise = 1 if r.random() < 0.6 else 0
        suspended = 1 if r.random() < 0.05 else 0
        nodmg = surprise == 0                     # ApplyDamageToCharacter never reached
        occ = occupancy(r, 0.85, force=[slot])
        party = E.party(c, r, occ)
        E.globals(c, surprise=surprise, combat=int(combat), suspended=suspended,
                  screen=SCREEN_MAIN, started=1)
        if combat:
            E.combat_state(c, dead_slots=[slot])
        minutes = r.choice(minutes_edges)
        if r.random() < 0.03:
            minutes = r.choice([65536, 0x00ffffff])
        wait = r.choice([0, 1, 2, 3, 3, 3, 4])
        c.set(E.gs + S_WAIT, u32(wait))
        level = r.choice([2, 3, 17, 18, 19, 20, 21, 0, 5])
        c.set(E.gs + S_LEVEL, u32(level))
        E.death_guard(c, [slot])
        blob = party[slot][1]
        ch = E.char(slot)
        note = {'slot': slot, 'char': party[slot][2], 'minutes': minutes, 'combat': int(combat),
                'surprise': surprise, 'suspended': suspended, 'wait': wait, 'level': level}
        # profession / race (traits: Fighter 0 stamina, Lord 1 health, Alchemist potions,
        # Faerie 0x1a, Lizardman 0x1b, Android immunities, Valkyrie cheat death)
        prof = blob.get_i32(C_PROF)
        race = blob.get_i32(C_RACE)
        if r.random() < 0.5:
            prof = r.choice([0, 1, 11, 11, 2, 6, 13, prof])
            race = r.choice([race, race, 5, 6, 15, 2])
            c.set(ch + C_PROF, struct.pack('<iii', prof, blob.get_i32(C_ORIG), race))
            if race == 15:
                E.android(c, slot)
        note.update(prof=prof, race=race)
        if r.random() < 0.4:
            levels = [blob.get_u32(C_PLEV + 4 * k) for k in range(15)]
            if 0 <= prof < 15:
                levels[prof] = r.choice([0, 1, 10, 20, 21, 30, 0xffffffff])
            levels[11] = r.choice([0, 1, 4, 9, 13, 18, levels[11]])
            c.set(ch + C_PLEV, arr32(levels))
            note['prof_level'] = levels[prof] if 0 <= prof < 15 else None
        # attributes: vitality (disease roll) and bases (disease attribute loss)
        if r.random() < 0.5:
            attrs = bytearray(blob[C_ATTR:C_ATTR + 7 * ATTR_STEP])
            vit = r.choice([0, 1, 2, 5, 10, 50, 0x80000000, 0x1999999a])
            struct.pack_into('<I', attrs, A_VIT * ATTR_STEP + 4, vit)
            for a in range(7):
                if r.random() < 0.3:
                    struct.pack_into('<I', attrs, a * ATTR_STEP, r.choice([0, 1, 2, 3, 0xffffffff]))
            c.set(ch + C_ATTR, bytes(attrs))
            note['vit'] = vit
        # conditions and enchantments
        conds = [0] * 20
        if r.random() < 0.3:
            conds[DISEASED] = r.choice([1, 5, INDEF])
        if r.random() < 0.18 and not (nodmg and level not in (17, 18, 19, 20, 21)):
            conds[INFATUATED] = INDEF             # band 9/10 levels (17..21) only lift HEXED
            conds[HEXED] = r.choice([0, 0, INDEF, 5])
            if minutes > 2000:
                minutes = r.choice([1, 10])
                note['minutes'] = minutes
        # combat: no finite condition >= TURNCOAT (its removal re-targets in combat)
        finite = (DRAINED, IRRITATED, NAUSEATED, SLOWED, AFRAID, POISONED, SILENCED, INSANE,
                  BLIND) + (() if combat else (WEBBED, ASLEEP, PARALYZED, UNCONSCIOUS))
        for k in finite:
            if r.random() < 0.1:
                conds[k] = r.choice([1, minutes, minutes + 1, minutes + 20, INDEF,
                                     0xffffffff]) or 1
        if combat:
            for k in (WEBBED, ASLEEP, PARALYZED):
                if r.random() < 0.05:
                    conds[k] = INDEF
        if conds[INSANE] == 0 and r.random() < 0.1:
            conds[INSANE] = r.choice([INDEF, 3])
        ench = b''
        for k in range(8):
            turns = 0
            if r.random() < 0.25:
                turns = r.choice([1, minutes, minutes + 1, minutes + 30, INDEF, 0xfffffff0]) or 1
            ench += ench_bytes(r.randint(0, 6), r.choice([0, 50, 100]), r.randint(0, 50), turns)
        c.set(ch + C_COND, arr32(conds) + bytes(blob[C_COND + 80:C_ENCH]) + ench)
        # pools, rates, accumulators (one block 0xb01..0xba9)
        pb = pblock(blob)
        pb.u32(pb_off(C_HIGHEST), highest_of(conds))
        pb.u32(pb_off(C_CONDARG), pick(r, [0, 1, 50, 0x7fffffff, 0xffffffff], 1, 40, 0.3))
        hpmax = pb.get_u32(pb_off(C_HPMAX))
        if r.random() < 0.3:
            hpmax = r.choice([4, 5, 6, 50, 300, 1000])
        hp = r.choice([hpmax, hpmax, max(1, hpmax - r.randint(1, 30)), 1, 2,
                       min(hpmax, r.randint(1, 300))])
        if combat:                                # no death in combat (CharacterDies)
            hpmax = 1000000
            hp = r.choice([hpmax, hpmax - 7, 900000])
        pb.u32(pb_off(C_HPMAX), hpmax)
        pb.u32(pb_off(C_HP), hp)
        stmax = pb.get_i32(pb_off(C_STMAX))
        if r.random() < 0.3:
            stmax = r.choice([4, 5, 6, 100, 300])
        st = r.choice([stmax, stmax, max(0, stmax - r.randint(1, 40)), 1, 2, 0])
        if r.random() < 0.04:
            st = r.choice([-5, -0x80000000])
            add_edge(note, 'negative_stamina')
        if combat:
            stmax = 1000000
            st = r.choice([stmax, 500000, 999990]) if st >= 0 else st
        pb.u32(pb_off(C_STMAX), stmax)
        pb.u32(pb_off(C_ST), st)
        for k in range(6):
            spm = r.choice([0, 0, 20, 100, pb.get_i32(pb_off(C_SPMAX) + 4 * k)])
            spl = r.choice([spm, spm, max(0, spm - r.randint(1, 30)), 0, -3])
            pb.u32(pb_off(C_SPMAX) + 4 * k, spm)
            pb.u32(pb_off(C_SPLEFT) + 4 * k, spl)
        pb.u32(pb_off(C_BREW), r.choice([0, 0, 1, minutes, minutes + 1, 0x168, 0xffffffff]))
        edge_acc = r.random() < 0.06
        pb.f32(pb_off(C_HRATE), rand_floatv(r, 0.05, 2.0, 0.05))
        pb.f32(pb_off(C_HACC), rand_floatv(r, 0, 1, 0.5 if edge_acc else 0.0))
        pb.f32(pb_off(C_SRATE), rand_floatv(r, 0.05, 2.0, 0.05))
        pb.f32(pb_off(C_SACC), rand_floatv(r, 0, 1, 0.5 if edge_acc else 0.0))
        for k in range(6):
            pb.f32(pb_off(C_SPRATE) + 8 * k, rand_floatv(r, 0.0, 1.5, 0.05))
            pb.f32(pb_off(C_SPRATE) + 8 * k + 4, rand_floatv(r, 0, 1, 0.5 if edge_acc else 0.0))
        c.set(ch + PB_LO, bytes(pb))
        if edge_acc:
            add_edge(note, 'accumulator')
        # bonus: damage per minute and the three regen channels
        dpm = r.choice([0, 0, 0, 1, 3, 0xff]) if r.random() < 0.5 else 0
        hreg = r.choice([0, 0, 0, 1, 2, 5, 127, -1, -3, -128])
        sreg = r.choice([0, 0, 0, 1, 2, 5, 127, -1, -3, -128])
        spreg = r.choice([0, 0, 0, 1, 2, 5, 127, -1, -3, -128])
        if nodmg:
            dpm = 0
            hreg = 127 if hreg == -128 else abs(hreg)
        c.set(ch + C_BONUS + B_DPM, bytes([dpm & 0xff, hreg & 0xff, sreg & 0xff, spreg & 0xff]))
        note.update(dpm=dpm, hreg=hreg, sreg=sreg, spreg=spreg, hp='%d/%d' % (hp, hpmax),
                    st='%d/%d' % (st, stmax),
                    conds=''.join('%x,' % k for k in range(20) if conds[k]))
        # Destinae Dominus / Helm of Serenity, item in hand, party pool
        pool_n = r.choice([0, 0, 1, 3])
        pool = b''
        holder = None
        dom = r.random() < 0.25
        for s in range(8):
            if occ[s] and (has_item(party[s][1], DOMINUS) or has_item(party[s][1], SERENITY)):
                if not dom or r.random() < 0.5:
                    for k in range(12):
                        if struct.unpack_from('<i', party[s][1], C_EQUIP + ITEM * k)[0] in (DOMINUS, SERENITY):
                            c.set(E.char(s) + C_EQUIP + ITEM * k, empty_items(1))
                    for k in range(8):
                        if struct.unpack_from('<i', party[s][1], C_PACK + ITEM * k)[0] in (DOMINUS, SERENITY):
                            c.set(E.char(s) + C_PACK + ITEM * k, empty_items(1))
        if dom:
            x = r.random()
            if x < 0.6:
                holder = r.choice([s for s in range(8) if occ[s]])
                place_item(c, E, r, holder, party[holder][1], DOMINUS)
                if r.random() < 0.5:
                    k = r.randrange(12)
                    c.set(E.char(holder) + C_EQUIP + ITEM * k, item_bytes(SERENITY))
                    note['serenity'] = holder
                note['dominus'] = holder
            elif x < 0.85:
                pool += item_bytes(DOMINUS)
                pool_n = max(pool_n, 1)
                note['dominus'] = 'pool'
            else:
                c.set(E.gs + S_INCURSOR, b'\x01')
                c.set(E.gs + S_INHAND, item_bytes(DOMINUS))
                note['dominus'] = 'hand'
        while len(pool) < pool_n * ITEM:
            pool += item_bytes(r.choice([100, 300, 5, 614]))
        c.set(E.gs + S_POOLN, u32(pool_n))
        if pool:
            c.set(E.gs + S_POOL, pool)
        c.arg(slot)
        c.arg(minutes)
        E.caps(c)
        if combat:
            E.combat_caps(c)
        c.note(**note)


def t_age_monster_sight(ctx, E):
    """void AgeMonsterSight(W8MonsterInfo*, unsigned int minutes, unsigned char full_regen)"""
    fn = ctx.fn(0x00503990)
    lst = ctx.scratch(0)
    mons = ctx.scratch(1)
    pc = ctx.scratch(2)
    p3d = ctx.scratch(3)
    for i in range(ctx.n(250)):
        r = ctx.rng('agemonster', i)
        c = ctx.case('agemonster.%d' % i, fn, conv='c', ret='v')
        in_combat = r.random() < 0.5
        surprise = 1 if r.random() < 0.3 else 0
        full = r.choice([0, 0, 0, 1]) if r.random() < 0.95 else r.choice([2, 0xff])
        minutes = r.choice([0, 1, 1, 1, 2, 3, 5, 10, 60, 255, 256, 1000])
        sp = r.choice(SPECIES_IDS)
        lvl, hreg_rec, sreg_rec = SPECIES[sp]
        loc = 0x5C000000 + r.randrange(0x1000)
        note = {'species': sp, 'minutes': minutes, 'combat': int(in_combat),
                'surprise': surprise, 'full': full}
        b = Blob(bytes(M_SIZE))
        b.u32(M_LOC, loc)
        b.u32(M_GROUP, 0x7a0002)
        b.u32(M_SPECIES, sp)
        b.u8(M_ACTIVE, 1)
        b.u8(M_INCOMBAT, 1 if in_combat else 0)
        if in_combat and r.random() < 0.05:
            b.u8(M_INCOMBAT, r.choice([2, 0xff]))
            add_edge(note, 'bool_byte')
        hpmax = r.choice([10, 50, 200, 1000, 0x7fffffff])
        if in_combat:
            hp = r.choice([0, 1, hpmax, hpmax - 1, r.randint(1, hpmax if hpmax < 5000 else 5000)])
        else:
            hp = r.choice([hpmax, hpmax, hpmax + 3, 0])          # HealMonster never reaches p3D
        b.u32(M_HPMAX, hpmax)
        b.u32(M_HP, hp)
        hadj = r.choice([0, 0, 1, 2, 5, 127])
        if r.random() < 0.3:
            hadj = -r.randint(0, hreg_rec)                        # never below zero in total
        sadj = r.choice([0, 0, 1, 3, -1, -2, -5])
        samount = (sadj + sreg_rec) * minutes
        stmax = r.choice([20, 100, 300, 0x7fffffff])
        st = r.choice([stmax, stmax - 1, 1, stmax // 2, 0])
        if samount < 0:
            st = max(st, -samount + 50)                           # FatigueMonster keeps stamina
            stmax = max(stmax, st)
        if r.random() < 0.05:
            st = r.choice([-5, -0x7fffffff])
            stmax = 100
            add_edge(note, 'negative_stamina')
        b.u32(M_STMAX, stmax)
        b.u32(M_ST, st)
        b.u8(M_MODS + B_HREG, hadj)
        b.u8(M_MODS + B_SREG, sadj)
        edge_acc = r.random() < 0.08
        b.f32(M_HRATE, rand_floatv(r, 0.0, 3.0, 0.05))
        b.f32(M_HACC, rand_floatv(r, 0, 1, 0.6 if edge_acc else 0.0))
        b.f32(M_SRATE, rand_floatv(r, 0.0, 3.0, 0.05))
        b.f32(M_SACC, rand_floatv(r, 0, 1, 0.6 if edge_acc else 0.0))
        if edge_acc:
            add_edge(note, 'accumulator')
        conds = [0] * 20
        for k in range(1, 17):
            if r.random() < 0.12:
                conds[k] = r.choice([minutes + 1, minutes + 30, INDEF, 0xffffffff])
        if r.random() < 0.25:
            conds[DISEASED] = r.choice([INDEF, minutes + 5])
        for k in range(20):
            b.u32(M_COND + 4 * k, conds[k])
        b.u32(M_HIGHEST, highest_of(conds))
        b.u32(M_CONDARG, pick(r, [0, 1, 0xff], 1, 60, 0.3))
        for k in range(8):
            turns = r.choice([0, 0, minutes + 1, minutes + 40, INDEF, 0xfffffff0])
            b[M_ENCH + ENCH * k:M_ENCH + ENCH * (k + 1)] = ench_bytes(r.randint(0, 5), 0, 0, turns)
        for k in range(12):
            active = 1 if r.random() < 0.25 else 0
            dur = r.choice([minutes + 1, minutes + 100, 0xffffffff]) if active else r.getrandbits(8)
            b[M_EFFECTS + SLOT * k:M_EFFECTS + SLOT * (k + 1)] = effect_slot(
                active, r.choice(PARTY_IDS), r.randint(0, 5), 0, dur)
        look = r.choice([0, 0, 1, 2, 5, 0xff]) if r.random() < 0.7 else 0
        pause = r.choice([0, 1, 3, 0xff])
        if minutes and r.random() < 0.3:
            look = r.choice([minutes & 0xff, (minutes + 1) & 0xff])
        b.u8(M_LOOK, look)
        b.u8(M_PAUSE, pause)
        note.update(look=look, pause=pause, hp='%d/%d' % (hp, hpmax), st='%d/%d' % (st, stmax),
                    hadj=hadj, sadj=sadj,
                    conds=''.join('%x,' % k for k in range(20) if conds[k]))
        variant = None
        if not in_combat:
            # the scratch p3D skips the movement watch: a linked navigator, halted, or
            # stopped with movement_stall_ticks <= 1
            variant = r.choice(['navigator', 'halted', 'stopped'])
            stall = r.choice([0, 1]) if variant == 'stopped' else r.choice([0, 1, 1, 2, 5, -1])
            b.u8(M_STALL, stall)
        E.wire_monsters(c, lst, [(mons, bytes(b))])
        if in_combat:
            c.setp(mons + M_PCOMBAT, pc)
            c.cap(pc, MC_SIZE, 'monster_combat')
        else:
            w = Blob(bytes(0x2d0))
            if variant == 'navigator':
                w.u32(W_NAVIGATOR, 1)
            elif variant == 'halted':
                w.u8(W_HALTED, 1)
            else:
                w.u8(W_STOPPED, 1)
            freq = r.choice([0, 1, 2, 3, 10, 30, 100, 255, 256, 511, -1, -10])
            dur = r.choice([0, 1, 2, 3, 10, 30, 100, 255, 256, 511, -1, -10])
            w.u32(W_LOOK_FREQ, freq)
            w.u32(W_LOOK_DUR, dur)
            c.set(p3d, bytes(w))
            c.setp(mons + M_P3D, p3d)
            view = 12.0 if r.random() < 0.75 else r.choice([2880.0, 11.999, 0.0])
            c.set(E.view, f32(view))
            note.update(variant=variant, freq=freq, dur=dur, view=view)
        c.set(E.gx + GX_SURPRISE, u8(surprise))
        c.set(E.gx + GX_COMBAT, u8(0))
        c.arg(mons)
        c.arg(minutes)
        c.arg(full)
        c.cap(mons, M_SIZE, 'monster', ignore=M_PTRS, floats=M_FLOATS)
        c.note(**note)


def t_update_camp_fatigue(ctx, E):
    """void UpdateCampFatigue(int ticks)"""
    fn = ctx.fn(0x005044d0)
    for i in range(ctx.n(250)):
        r = ctx.rng('campfatigue', i)
        c = ctx.case('campfatigue.%d' % i, fn, conv='c', ret='v')
        surprise = 1 if r.random() < 0.8 else 0
        combat = r.random() < 0.15
        suspended = 1 if r.random() < 0.05 else 0
        occ = occupancy(r, 0.85)
        party = E.party(c, r, occ)
        E.globals(c, surprise=surprise, combat=int(combat), suspended=suspended,
                  screen=SCREEN_MAIN, started=1)
        if combat:
            E.combat_state(c, dead_slots=[s for s in range(8) if occ[s]])
            E.combat_caps(c)
            c.set(E.settings + SET_VERBOSE, u8(r.choice([0, 1])))
        ticks = r.choice([1, 1, 2, 3, 4, 6, 10]) if r.random() < 0.85 else \
            r.choice([0, 255, 256, 257, -1, 0x7fffffff])
        count = pick(r, [0, 5, 6, 11, 12, 1529, 1530, 0xffffffff, 0x7ffffffe], 0, 80, 0.2)
        sides = ((count & 0xffffffff) // 6 + 2) & 0xff
        maxamt = (ticks & 0xff) * max(sides, 1)
        fatigued = 1 if r.random() < 0.4 else 0
        c.set(E.gs + S_CAMPCOUNT, u32(count))
        c.set(E.gs + S_FATIGUED, u8(fatigued))
        c.set(E.gs + S_CAMPTICK, u32(r.randint(0, 2499)))
        note = {'ticks': s32(ticks), 'count': count, 'fatigued': fatigued, 'surprise': surprise,
                'combat': int(combat), 'suspended': suspended, 'occ': ''.join(map(str, occ))}
        guard = []
        desc = []
        edges = []
        for s in range(8):
            blob = party[s][1]
            pb = Blob(bytes(blob[C_HIGHEST:C_ST + 4]))   # highest .. stamina
            hc = 0
            x = r.random()
            if x < 0.1:
                hc = r.choice([17, 18, 19, 1, 5])
            elif x < 0.13:
                hc = r.choice([0x80000000, 0xffffffff])
                edges.append('cond_negative')
            hp = pb.get_u32(C_HP - C_HIGHEST)
            if r.random() < 0.1:
                hp = 0
            st = pb.get_i32(C_ST - C_HIGHEST)
            y = r.random()
            if y < 0.3:
                st = r.choice([0, 1, 2, 5, r.randint(0, 40)])
            elif y < 0.35:
                st = r.choice([-1, -50, -0x80000000])
                edges.append('negative_stamina')
            if surprise == 0 and st < maxamt + 1:
                st = maxamt + 1 + r.randint(0, 20)      # FatigueCharacter only, no damage
            if combat and hp:
                hp = max(hp, maxamt + 1)                # no death in combat (CharacterDies)
            pb.u32(0, hc)
            pb.u32(C_HP - C_HIGHEST, hp)
            pb.u32(C_ST - C_HIGHEST, st)
            if occ[s]:
                c.set(E.char(s) + C_HIGHEST, bytes(pb))
            if occ[s] and r.random() < 0.08:
                c.set(E.char(s) + C_RACE, u32(15))      # Android: never fatigued
                E.android(c, s)
                desc.append('%d:android' % s)
            if occ[s]:
                want = r.random() < 0.25
                set_scuba(c, E, r, s, blob, want)
                if want:
                    desc.append('%d:scuba' % s)
            if occ[s] and hp and hp <= maxamt and surprise:
                guard.append(s)
        if guard:
            E.death_guard(c, guard)
        E.caps(c)
        note.update(items=' '.join(desc), guard=guard)
        if edges:
            note['edge'] = ','.join(sorted(set(edges)))
        c.arg(ticks)
        c.note(**note)


def t_update_party_stamina(ctx, E):
    """void UpdatePartyStamina(int ticks) + inlined RegenCharacterStamina"""
    fn = ctx.fn(0x00504670)
    for i in range(ctx.n(300)):
        r = ctx.rng('partystamina', i)
        c = ctx.case('partystamina.%d' % i, fn, conv='c', ret='v')
        surprise = 1 if r.random() < 0.35 else 0
        combat = r.random() < 0.2
        occ = occupancy(r, 0.85)
        party = E.party(c, r, occ)
        E.globals(c, surprise=surprise, combat=int(combat), screen=SCREEN_MAIN, started=1)
        if combat:
            E.combat_state(c, dead_slots=[s for s in range(8) if occ[s]])
            E.combat_caps(c)
        ticks = r.choice([1, 1, 1, 2, 3, 5]) if r.random() < 0.85 else \
            r.choice([0, 10, 100, 0x01000000, 0x7fffffff, -1])
        fast = r.random() < 0.25
        moved = r.random() < 0.35
        flags = LEVEL_WALK | (LEVEL_FAST if fast else 0) | (LEVEL_MOVED if moved else 0)
        c.set(E.level_data.deref(), u32(flags))
        fatigued = 1 if r.random() < 0.3 else 0
        c.set(E.gs + S_FATIGUED, u8(fatigued))
        c.set(E.gs + S_WAIT, u32(r.choice([0, 1, 2, 3])))
        note = {'ticks': s32(ticks), 'surprise': surprise, 'combat': int(combat),
                'flags': '%x' % flags, 'fatigued': fatigued, 'occ': ''.join(map(str, occ))}
        desc = []
        edges = []
        for s in range(8):
            if not occ[s]:
                continue
            blob = party[s][1]
            ch = E.char(s)
            if r.random() < 0.35:
                prof = r.choice([0, 0, 1, 6, blob.get_i32(C_PROF)])
                c.set(ch + C_PROF, u32(prof))
                if prof == 0 and r.random() < 0.6:
                    c.set(ch + C_PLEV, u32(r.choice([0, 1, 10, 20, 21, 50, 0xffffffff])))
                desc.append('%d:p%d' % (s, prof))
            conds = cond_array(blob)
            hc = highest_of(conds)
            x = r.random()
            if x < 0.25:
                conds[DISEASED] = r.choice([1, INDEF])
            if x > 0.9:
                conds[DEAD] = r.choice([0, INDEF])
                hc = r.choice([DEAD, MISSING, UNCONSCIOUS])
                c.set(ch + C_CONDREC + CR_STEP + 8, u8(r.choice([0, 1])))   # swallowed flag
                desc.append('%d:hc%d/d%d' % (s, hc, conds[DEAD]))
            elif 0.85 < x <= 0.9:
                hc = r.choice([0x80000000, 0xffffffff])
                edges.append('cond_negative')
            else:
                hc = highest_of(conds)
            if conds != cond_array(blob):
                c.set(ch + C_COND, arr32(conds))
            pb = Blob(bytes(blob[C_HIGHEST:C_SACC + 4]))
            pb.u32(0, hc)
            stmax = pb.get_i32(C_STMAX - C_HIGHEST)
            if r.random() < 0.2:
                stmax = r.choice([1, 20, 300, 0x7fffffff])
            st = r.choice([stmax, stmax - 1, stmax // 2, 0, 1, r.randint(0, max(1, stmax))])
            if r.random() < 0.04:
                st = r.choice([-5, -0x80000000])
                edges.append('negative_stamina')
            pb.u32(C_STMAX - C_HIGHEST, stmax)
            pb.u32(C_ST - C_HIGHEST, st)
            pb.f32(C_SRATE - C_HIGHEST, rand_floatv(r, 0.1, 2.0, 0.05))
            acc = rand_floatv(r, 0, 1, 0.08)
            if acc < 0 or acc >= 2.0 ** 31:
                edges.append('accumulator')
            pb.f32(C_SACC - C_HIGHEST, acc)
            c.set(ch + C_HIGHEST, bytes(pb))
            sreg = r.choice([0, 0, 0, 1, 2, 10, 127, -1, -2, -128])
            c.set(ch + C_BONUS + B_SREG, u8(sreg))
            if fatigued or r.random() < 0.2:
                set_scuba(c, E, r, s, blob, r.random() < 0.4)
        note['party'] = ' '.join(desc)
        if edges:
            note['edge'] = ','.join(sorted(set(edges)))
        c.arg(ticks)
        E.caps(c)
        c.note(**note)


def t_resolve_surprise_wake(ctx, E):
    """void ResolveSurpriseWake(void)"""
    fn = ctx.fn(0x005029e0)
    for i in range(ctx.n(150)):
        r = ctx.rng('surprisewake', i)
        c = ctx.case('surprisewake.%d' % i, fn, conv='c', ret='v')
        occ = occupancy(r, 0.85)
        party = E.party(c, r, occ)
        surprise = 1 if r.random() < 0.25 else 0
        suspended = 1 if r.random() < 0.05 else 0
        E.globals(c, surprise=surprise, combat=0, suspended=suspended, screen=SCREEN_MAIN,
                  started=1)
        mode = r.choice(['null', 'surprised', 'surprised', 'surprised', 'calm'])
        if mode != 'null':
            cs = ctx.scratch(7)
            c.setp(E.gcs, cs)
            flag = 1 if mode == 'surprised' else 0
            if mode == 'surprised' and r.random() < 0.05:
                flag = r.choice([2, 0xff])
            c.set(cs + CS_SURPRISED, u8(flag))
        note = {'mode': mode, 'surprise': surprise, 'suspended': suspended,
                'occ': ''.join(map(str, occ))}
        desc = []
        for s in range(8):
            if not occ[s]:
                continue
            ch = E.char(s)
            if r.random() < 0.6:
                sen = pick(r, [0, 1, 28, 29, 100, 125, 0xffffffff, 0x80000000, 61356676], 1, 125,
                           0.3)
                c.set(ch + C_ATTR + A_SEN * ATTR_STEP + 4, u32(sen))
                desc.append('%d:s%d' % (s, sen))
            x = r.random()
            if x < 0.15:
                hc = r.choice([17, 18, 19, 15, 13])
                c.set(ch + C_HIGHEST, u32(hc))
                desc.append('%d:hc%d' % (s, hc))
            elif x < 0.18:
                c.set(ch + C_HIGHEST, u32(0x80000000))
                note['edge'] = 'cond_negative'
            if r.random() < 0.1:
                c.set(ch + C_RACE, u32(15))                 # Android: asleep immunity
                E.android(c, s)
                desc.append('%d:android' % s)
            if r.random() < 0.15:
                c.set(ch + C_COND + 4 * ASLEEP, u32(r.choice([1, 5, INDEF])))
        note['party'] = ' '.join(desc)
        E.caps(c)
        c.note(**note)


# ===================================================================== party_encumbrance.cpp
def t_recalc_derived(ctx, E):
    """void RecalculateCharacterDerivedStats(W8Character*)"""
    fn = ctx.fn(0x004ed9d0)
    for i in range(ctx.n(300)):
        r = ctx.rng('recalcderived', i)
        c = ctx.case('recalcderived.%d' % i, fn, conv='c', ret='v')
        scratch = r.random() < 0.1
        slot = 0 if scratch else r.randrange(8)
        note = {}
        party, combat = derived_env(ctx, E, c, r, [slot], note)
        if scratch:
            blob, name = ctx.pick_char(r)
            ch = ctx.scratch(5)
            c.set(ch, bytes(blob))
            c.set(ch + C_INPARTY, b'\x00')
            if combat:                         # CalcArmorClasses needs a party pointer in combat
                c.set(E.gx + GX_COMBAT, b'\x00')
                note['combat'] = 0
            c.cap(ch, CHAR, 'scratch_char', floats=CHAR_FLOATS)
            note.update(char=name, scratch=1)
        else:
            blob = party[slot][1]
            ch = E.char(slot)
            note.update(char=party[slot][2], slot=slot)
            if r.random() < 0.05:
                c.set(ch + C_INPARTY, b'\x00')
                note['in_party'] = 0
        x = r.random()
        if x < 0.04:
            c.set(ch + C_PROF, u32(r.choice([15, 16, 0x7fffffff])))
            note['gate'] = 'profession'
        elif x < 0.08:
            c.set(ch + C_RACE, u32(r.choice([16, 17, 0x7fffffff])))
            note['gate'] = 'race'
        elif x < 0.11:
            c.set(ch + C_GENDER, u32(0xffffffff))
            note['gate'] = 'gender'
        elif x < 0.4:
            prof = r.choice([6, 6, 0, 1, 11, r.randrange(15)])
            race = r.choice([2, 2, 5, 5, 6, 15, r.randrange(11)])
            c.set(ch + C_PROF, struct.pack('<iii', prof, blob.get_i32(C_ORIG), race))
            note.update(prof=prof, race=race)
            if race == 15 and not scratch:
                E.android(c, slot)
        mutate_for_derived(c, r, E, ch, blob, note, rebuild_bonus=False)
        c.arg(ch)
        E.caps(c)
        c.note(**note)


def t_carrying_capacity(ctx, E):
    """bool RecalculateCarryingCapacity(W8Character*)"""
    fn = ctx.fn(0x004edc10)
    for i in range(ctx.n(200)):
        r = ctx.rng('carrycap', i)
        c = ctx.case('carrycap.%d' % i, fn, conv='c', ret='b')
        slot = r.randrange(8)
        blob, name = E.one(c, r, slot)
        ch = E.char(slot)
        edge = r.random() < 0.15
        st = pick(r, [0, 1, 125, 0x7fffffff, 0x80000000, 0xffffffff, 0x15555556] if edge
                  else [1, 125], 1, 125, 0.2)
        vit = pick(r, [0, 1, 125, 0x7fffffff, 0x80000000, 0xffffffff] if edge else [1, 125],
                   1, 125, 0.2)
        c.set(ch + C_ATTR + A_STR * ATTR_STEP + 4, u32(st))
        c.set(ch + C_ATTR + A_VIT * ATTR_STEP + 4, u32(vit))
        race = r.choice([5, 5, 5, 0, 2, 6, 15, blob.get_i32(C_RACE)])
        prof = r.choice([blob.get_i32(C_PROF), -1, r.randrange(15)])
        c.set(ch + C_PROF, struct.pack('<iii', prof, blob.get_i32(C_ORIG), race))
        base = (vit + 2 * st) & 0xffffffff
        cap = (base * 12) & 0xffffffff
        if race == 5:
            cap = ((base * 24) & 0xffffffff) // 3
        prev = r.choice([cap, cap, cap + 1, 0, blob.get_u32(C_CAP), r.getrandbits(32)])
        c.set(ch + C_CAP, u32(prev))
        c.arg(ch)
        c.cap(ch, CHAR, 'char', floats=CHAR_FLOATS)
        c.note(char=name, strength=st, vitality=vit, race=race, prof=prof, previous=prev)


def t_carried_weight(ctx, E):
    """bool RecalculateCarriedWeight(W8Character*)"""
    fn = ctx.fn(0x004edc60)
    for i in range(ctx.n(250)):
        r = ctx.rng('carriedweight', i)
        c = ctx.case('carriedweight.%d' % i, fn, conv='c', ret='b')
        occ = occupancy(r, 0.9)
        slot = r.choice([s for s in range(8) if occ[s]])
        blob, name = E.one(c, r, slot)
        c.set(E.row(slot) + X_OCC, b'\x01')
        screen = r.choice([SCREEN_MAIN, SCREEN_MAIN, SCREEN_CAMP, SCREEN_CHARACTER])
        E.globals(c, surprise=1, combat=0, screen=screen, started=1)
        ch = E.char(slot)
        note = {'char': name, 'slot': slot, 'screen': screen}
        x = r.random()
        if x < 0.5:
            for _ in range(r.randint(1, 5)):
                k = r.randrange(20)
                y = r.random()
                if y < 0.4:
                    iid, w = r.choice(IT_STACK)
                    item = item_bytes(iid, r.choice([0, 1, 2, 10, 99, 100, 255]))
                elif y < 0.6:
                    item = item_bytes(r.choice(IT_HEAVY), r.choice([0, 0, 3]))
                elif y < 0.8:
                    item = empty_items(1)
                else:
                    item = item_bytes(r.randrange(ITEM_COUNT), r.choice([0, 0, 1, 7]))
                if k < 12:
                    c.set(ch + C_EQUIP + ITEM * k, item)
                else:
                    c.set(ch + C_PACK + ITEM * (k - 12), item)
            note['items_changed'] = 1
        elif x < 0.6:
            c.set(ch + C_EQUIP, empty_items(12))
            c.set(ch + C_PACK, empty_items(8))
            note['empty'] = 1
        prev = pick(r, [0, 1, blob.get_u32(C_INVW), 0xffffffff, 0x80000000], 0, 3000, 0.4)
        cap = pick(r, [0, 1, prev, prev + 1, 0xffffffff, blob.get_u32(C_CAP)], 50, 3000, 0.4)
        c.set(ch + C_INVW, u32(prev))
        c.set(ch + C_CAP, u32(cap))
        inparty = 1 if r.random() < 0.97 else 0
        c.set(ch + C_INPARTY, u8(inparty))
        c.arg(ch)
        c.cap(ch, CHAR, 'char', floats=CHAR_FLOATS)
        note.update(previous=prev, capacity=cap, in_party=inparty)
        c.note(**note)


def t_redistribute(ctx, E):
    """void RedistributePartyEncumbrance(void)"""
    fn = ctx.fn(0x004edd20)
    camp = ctx.scratch(6)
    for i in range(ctx.n(300)):
        r = ctx.rng('redistribute', i)
        c = ctx.case('redistribute.%d' % i, fn, conv='c', ret='v')
        occ = occupancy(r, 0.85)
        party = E.party(c, r, occ)
        started = 1 if r.random() < 0.94 else 0
        combat = r.random() < 0.08
        screen = r.choice([SCREEN_MAIN] * 6 + [SCREEN_CAMP] * 2 + [SCREEN_CHARACTER, SCREEN_AUTOMAP])
        E.globals(c, surprise=1, combat=int(combat), screen=screen, started=started)
        if combat:
            E.combat_state(c)
        dlg = 1 if r.random() < 0.15 else 0
        c.set(E.gx + GX_NPCDLG, u8(dlg))
        c.set(E.gx + GX_DIRTY, u8(r.choice([0, 1])))
        if screen == SCREEN_CAMP:
            c.setp(E.camp, camp)
            c.set(camp + 0xf8, u32(r.choice([0, 0x100, 0x2000, 0x80000001])))
            c.cap(camp, 0x100, 'camp_screen')
        note = {'occ': ''.join(map(str, occ)), 'started': started, 'combat': int(combat),
                'screen': screen, 'npc_dialogue': dlg}
        desc = []
        edges = []
        for s in range(8):
            if not occ[s] and r.random() < 0.7:
                continue
            blob = party[s][1]
            cap = blob.get_u32(C_CAP)
            inv = blob.get_u32(C_INVW)
            x = r.random()
            if x < 0.3:
                cap = r.choice([1, 10, 100, 640, 1200, 3900])
                inv = r.choice([0, cap // 2, cap, cap + 5, r.randint(0, 2 * cap)])
            elif x < 0.34:
                inv = r.choice([0x80000000, 0xffffffff, 0x7fffffff])
                edges.append('big_weight')
            share = r.getrandbits(16)
            load = r.choice([0, 1, 2, 3, 4, blob.get_u32(C_LOAD)])
            c.set(E.char(s) + C_INVW, arr32([inv, share, r.getrandbits(16), cap, load]))
            hc = 0
            y = r.random()
            if y < 0.12:
                hc = r.choice([17, 18, 19])
            elif y < 0.15:
                hc = r.choice([0x80000000, 0xffffffff])
                edges.append('cond_negative')
            if hc or r.random() < 0.3:
                c.set(E.char(s) + C_HIGHEST, u32(hc))
            desc.append('%d:%d/%d/%d/hc%x' % (s, inv, cap, load, hc))
        n = r.choice([0, 0, 1, 2, 5, 10, 20])
        pool = b''
        weight = 0
        for q in range(n):
            y = r.random()
            if y < 0.4:
                iid, w = r.choice(IT_STACK)
                cnt = r.choice([0, 1, 5, 20, 100])
                weight += w * max(cnt, 1)
            elif y < 0.7:
                iid, cnt = r.choice(IT_HEAVY), 0
            elif y < 0.8:
                iid, cnt = -1, 0
            else:
                iid, cnt = r.randrange(ITEM_COUNT), r.choice([0, 1])
            pool += item_bytes(iid, cnt)
        c.set(E.gs + S_POOLN, u32(n))
        if pool:
            c.set(E.gs + S_POOL, pool)
        note.update(party=' '.join(desc), pool=n)
        if edges:
            note['edge'] = ','.join(sorted(set(edges)))
        E.caps(c)
        c.note(**note)
