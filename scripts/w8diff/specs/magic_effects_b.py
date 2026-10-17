"""Magic Effects.cpp, second half (lines 1901-3804): the spell-effect bodies the
per-frame dispatcher routes to, the dispatcher itself and the enchantment /
direct damage helpers.

Every case runs on the party (8 corpus characters in Char[0..7]); the effects'
monster lists stay empty (live monsters cannot be captured or restored), so only
the character/party paths are exercised.  Common set-up per case (all restored
by the core):
  * XChar rows: canonical rows (fOccupied pattern, npc_index -1, party order =
    slot, reset combat slots) - setb blob, captured;
  * gXStatus.fSurprisePossible = 1: ApplyDamageToCharacter then skips the portrait
    damage splat (Random(2) depends on the animation state) and the damage-quote
    queueing;
  * the character event queue's 0xb1-byte mask array is filled with 0xff, so
    every HasEventCharacter() answers "already queued": QueueEntry drops every
    event and QueueDamageReactionEvents (DamageCharacter calls it ungated) no
    longer branches on the live queue;
  * g_text_box_mode = 0, verbose_combat_messages, difficulty, combat mode,
    lock/trap interact modes, world_suspended, skip_next_condition_reaction,
    sight_refresh_pending, the party effect slots (12x0x11) and the party
    modifier block, g_level_block->redraw_flags are all set explicitly;
  * g_status.selected_character = 0: AimAtTarget (a dying character's target
    re-pick) requests the monster-list redraw (0x20000) only for the selected
    slot, which was whatever the two processes happened to have selected;
  * g_combat_state is pointed at a scratch W8CombatState (0xa64) whenever the
    function (or a callee) needs it.
Captured: the 8 characters, the XChar rows, party effect slots + party
modifiers, sight_refresh_pending, redraw flags, the W8SpellEffectEntry (vector
data pointers ignored), the scratch combat state, party gold / party item pool
where touched.  The 16 float regeneration fields per character (0xb69..0xba8,
rebuilt by RecalculateCharacterDerivedStats) are ignored in the character cap:
the cap API has no float list, so x87 rounding noise would flood the report.

Tested (address, name, cases):
  0x0054cbf0 ApplyBeingEffectSlot             260
  0x0054dbe0 AttackThenInflictCondition       300
  0x0054cdd0 ApplyCombatEffectSlot            240
  0x0054d380 ApplyDefenseEffectSlot           220
  0x0054fa30 ResolveAfflictionAgainstTargets  260
  0x00550c10 DamageTargetsAndReport           260
  0x005510b0 DestroyConsumablesOnTargets      260
  0x0054d100 ReduceCombatEffectDurations      240
  0x0054c930 FinishSpellEffectTargets         160
  0x005526f0 TickCombatEffectSlots            280
  0x0054ba00 ProcessSpellEffectTargets        420
  0x00553350 ApplyDiceDamageToCharacter       240
  0x005535d0 ApplyDirectDamageToCharacter     240
  (0x005517c0 RevealItemBindingsToTarget is inlined in the port; it is covered
   through ProcessSpellEffectTargets kind 58 Remove Curse.)

Skipped:
  0x00551500 ApplyMonsterControlToNearbyMonsters - octree box query + line of
             sight around a world point, live monster AI/control state, leaks a
             0x400-byte buffer per call.
  0x005517c0 RevealItemBindingsToTarget - not in the port map (inlined); see above.
  0x00550a00 ApplyCharmToMonsterTarget - needs a live monster target; main effect
             is the NPC quote bubble and the monster spell icon (UI).
  0x005508e0 ResolveCharmRefusal - not in the port map; dialogue NPC refusal.
  0x00552ef0 TickRadiusBlastEffectSlots - collects monsters around the party in the
             live world (positions drift) and damages them; the inactive path has
             nothing observable.
  0x00553540 ApplyDiceDamageToMonster - damages a live monster (hit reaction,
             death, combat side effects that cannot be captured/restored).
  0x00553770 ApplyDirectDamageToMonster - same as above.
Not exercised inside the tested functions: the monster_ids loops, the reflection
re-cast of FinishSpellEffectTargets (best != 0 casts a spell), the recast path of
ProcessSpellEffectTargets (recast = 0), and dispatcher kinds that act on the
world/dialogs: 3 Charm, 30 Sonic Boom, 38 Hypnotic Lure, 41 Mindread,
60 Summon Elemental, 73 Return to Portal, 75 Set Portal (camera), 95 Earthquake,
123 Alarm.
Known static finding: ApplyCombatEffectSlot with kind 2 (Bless) - retail asserts
0x35f after its 9-entry scan (0x616db4..0x616dd8) and skips the slot; the port's
loop only stops once the pointer reaches g_combat_effect_slot_spells_and_cast_success
(one padding dword after the 9 entries in the port image) and then compares that
array's first entry (2), so it activates g_combat_state->effect_slots[10]
(cases applycombat.*.bless_edge; not reachable from the dispatcher, which routes
Bless to ApplyDefenseEffectSlot). The port now bounds the walk by the nine entries
like retail; the cases stay as a regression check."""
import struct

from w8diff.api import Blob

CHAR = 0x1862
NCHAR = 8
XROW = 0x106

# W8Character (layout.ps1, wiz8/layouts/character.h)
C_SKILLS = 0x19d
SKILL_STEP = 0x26
C_COND = 0xa01
C_ENCH = 0xa65
C_HIGHEST = 0xb01
C_ENCH_TOP = 0xb05
C_COND_ARG = 0xb09
C_HPMAX = 0xb0d
C_HP = 0xb11
C_HPADJ = 0xb15
C_STMAX = 0xb19
C_ST = 0xb1d
C_SPMAX = 0xb25
C_SPLEFT = 0xb45
C_DR = 0xed9
C_EQUIP = 0xf5d
C_PACK = 0x1029
SK_IRON_WILL = 0x24
SK_IRON_SKIN = 0x25

# W8GlobalStatus (game_status.h)
S_GOLD = 0x19
S_SELECTED = 0x1d          # selected_character
S_POOL = 0x21
S_POOL_COUNT = 0x1791
S_SLOTS = 0x17af
S_MODS = 0x22e3
S_WORLD_SUSPENDED = 0x2390
S_SKIP_REACTION = 0x2488

# W8XStatus (xstatus.h)
X_COMBAT = 0x8dc
X_LOCK_TRAP = 0x8e0         # fLockInteractMode, fTrapInteractMode
X_SURPRISE = 0x90d
X_EVENT_QUEUE = 0x91f
X_SIGHT_REFRESH = 0xa03

# W8GameSettings (Configuration.h)
G_DIFFICULTY = 0xd
G_VERBOSE = 0x44

# W8CombatState (combat_state.h)
CS_SIZE = 0xa64
CS_ACTION_CHAR = 0x7b4
CS_SLOTS = 0x7c1
CS_SLOTS0 = 0x85a
CS_REPORT = 0x9a6          # W8SpellEffectResult attack_report (0xa2)
CS_REPORT_DATA = 0xa0a     # attack_report.reports.data (heap pointer)

# W8SpellEffectEntry (local_code/SpellEffect.h)
E_SIZE = 0x1c8
E_MON_DATA = 0xec
E_TGT_DATA = 0xfc
E_PCITEM = 0xac
E_REPORTS_DATA = 0x18a
E_MON_LIST = 0x400         # scratch(0) offsets of the two int lists
E_TGT_LIST = 0x500

# Static tables (retail data 0x616d84.. ; spell DB from Data\Databases\SpellTables.dbs)
BEING = [0x20, 0x21, 0x11, 0x14, 0x08, 0x28, 0x1a, 0x2d, 0x40]
COMBAT_SLOTS = [0x31, 0x30, 0x4c, 0x51, 0x5d, 0x50]
DEFENSE_SLOTS = [2, 0x35, 0x3b, 0x3e]
DEFENSE_OVERFLOW = [0x1e, 0x28, 0x32]     # table entries 6..8 (past effect_slots0[6])
# kind -> (duration, duration_per_level, (dice base, count, sides), realm)
SPELLS = {
    0: (0, 0, (0, 0, 0), 0), 1: (0, 0, (0, 1, 7), 1), 2: (2, 0, (0, 0, 0), 5), 4: (0, 0, (0, 1, 7), 1),
    5: (0, 0, (0, 1, 7), 0), 6: (0, 0, (0, 4, 4), 5), 7: (1, 0, (0, 0, 0), 3), 8: (0, 720, (0, 0, 0), 0),
    9: (0, 0, (0, 2, 3), 5), 10: (1, 0, (1, 1, 7), 4), 11: (1, 0, (0, 0, 0), 1), 12: (1, 0, (0, 0, 0), 2),
    13: (0, 0, (0, 6, 6), 1), 14: (1, 1, (0, 0, 0), 4), 15: (1, 0, (0, 0, 0), 0), 16: (0, 0, (0, 0, 0), 1),
    17: (2, 1, (0, 0, 0), 4), 18: (0, 0, (0, 0, 0), 4), 19: (1, 0, (0, 0, 0), 1), 20: (30, 0, (0, 0, 0), 5),
    21: (2, 3, (4, 1, 6), 5), 22: (0, 0, (0, 2, 5), 1), 23: (0, 0, (0, 0, 0), 4), 24: (1, 0, (0, 0, 0), 4),
    25: (0, 0, (0, 1, 7), 5), 26: (30, 0, (0, 0, 0), 2), 27: (1, 0, (3, 1, 3), 3), 28: (0, 0, (0, 1, 5), 2),
    29: (1, 0, (0, 0, 0), 1), 31: (1, 0, (0, 0, 0), 3), 32: (30, 0, (0, 0, 0), 3), 33: (6, 0, (0, 0, 0), 3),
    34: (0, 0, (0, 0, 0), 1), 35: (0, 0, (0, 0, 0), 2), 36: (0, 0, (0, 2, 4), 0), 37: (1, 0, (0, 0, 0), 1),
    39: (0, 0, (0, 0, 0), 3), 40: (30, 0, (0, 0, 0), 5), 42: (0, 0, (0, 1, 6), 2), 43: (0, 0, (0, 2, 5), 0),
    44: (0, 0, (0, 6, 6), 1), 45: (120, 0, (0, 0, 0), 2), 46: (1, 0, (0, 0, 0), 2), 47: (0, 0, (0, 2, 5), 3),
    48: (1, 0, (0, 1, 6), 1), 49: (1, 0, (0, 0, 0), 3), 50: (0, 0, (0, 2, 15), 3), 51: (0, 0, (0, 0, 0), 1),
    52: (0, 0, (0, 2, 7), 4), 53: (1, 3, (0, 0, 0), 3), 54: (1, 1, (0, 0, 0), 5), 55: (0, 0, (0, 2, 5), 0),
    56: (1, 0, (0, 0, 0), 0), 57: (0, 0, (0, 2, 5), 1), 58: (0, 0, (0, 0, 0), 5), 59: (1, 3, (0, 0, 0), 5),
    61: (1, 0, (0, 0, 0), 1), 62: (1, 3, (0, 1, 6), 0), 63: (0, 0, (0, 2, 4), 2), 64: (12, 12, (0, 0, 0), 4),
    65: (1, 0, (0, 0, 0), 3), 66: (0, 0, (0, 2, 19), 1), 67: (1, 0, (0, 3, 10), 1), 68: (0, 0, (0, 4, 4), 5),
    69: (1, 0, (0, 0, 0), 4), 70: (0, 0, (0, 0, 0), 5), 71: (1, 0, (0, 2, 7), 4), 72: (0, 0, (0, 0, 0), 2),
    74: (0, 0, (0, 0, 0), 4), 76: (1, 0, (0, 1, 4), 2), 77: (0, 0, (0, 3, 9), 5), 78: (1, 0, (0, 2, 9), 1),
    79: (0, 0, (0, 2, 19), 0), 80: (1, 0, (0, 1, 5), 5), 81: (1, 0, (0, 2, 4), 0), 82: (0, 0, (0, 4, 4), 5),
    83: (0, 0, (0, 2, 8), 0), 84: (0, 0, (0, 3, 9), 5), 85: (1, 0, (0, 0, 0), 2), 86: (1, 0, (0, 2, 8), 0),
    87: (0, 0, (0, 0, 0), 3), 88: (0, 0, (0, 0, 0), 5), 89: (1, 2, (0, 0, 0), 4), 90: (0, 0, (0, 0, 0), 2),
    91: (1, 0, (0, 2, 24), 4), 92: (1, 0, (0, 2, 24), 4), 93: (1, 0, (0, 0, 0), 2), 94: (0, 0, (0, 0, 0), 5),
    96: (0, 0, (0, 2, 8), 3), 97: (0, 0, (0, 3, 7), 4), 98: (0, 0, (0, 3, 7), 0), 99: (1, 0, (0, 3, 9), 0),
    100: (0, 0, (0, 8, 8), 5), 101: (0, 0, (0, 3, 9), 1), 102: (0, 0, (0, 0, 0), 0),
    114: (0, 0, (0, 4, 4), 3), 115: (0, 0, (0, 4, 14), 5), 116: (0, 0, (0, 0, 0), 2),
    117: (1, 0, (0, 0, 0), 4), 118: (0, 0, (2, 1, 5), 0), 119: (0, 0, (0, 0, 0), 1),
    120: (0, 0, (0, 0, 0), 5), 121: (0, 0, (0, 1, 7), 3), 122: (0, 0, (0, 1, 4), 1),
    124: (0, 0, (60, 1, 7), 3), 125: (0, 0, (0, 1, 4), 1), 126: (0, 0, (0, 0, 0), 2),
    127: (0, 0, (0, 0, 0), 5), 128: (0, 0, (0, 0, 0), 4), 129: (1, 1, (0, 2, 5), 5),
    130: (1, 1, (0, 5, 5), 5), 131: (0, 0, (0, 3, 6), 0), 132: (0, 0, (0, 0, 0), 0),
    149: (0, 0, (0, 0, 0), 0),
}

# Items.dbs (PATCH.001), equip_class 16/19/20 are destroyed by Heatwave, 17/18/21/22 are not
POTIONS = [46, 47, 69, 260, 264, 317, 329, 334, 335, 336, 337, 338, 339, 341, 345, 346, 347, 348,
           488, 597, 598, 671, 712, 713]
BOMBS = [258, 306, 343, 349, 350, 351, 352, 353, 354, 356, 432]
POWDERS = [269, 282, 355, 357, 358, 359, 360, 361, 362, 363, 364, 573]
BOOKS = [368, 369, 370, 371, 372, 374, 375, 378, 379, 382, 426, 437, 438, 439, 440, 441, 442,
         443, 444, 445, 447, 448, 449, 475, 476, 477, 478, 479, 480, 481, 482, 483, 484, 515,
         516, 517, 518, 519, 520, 521, 522, 523, 524, 525, 526, 527, 528, 529, 530, 531, 532,
         533, 534, 535, 536, 537, 538, 539, 540, 541, 542, 543, 544, 545, 546, 547, 548, 549,
         550, 551, 552, 553, 554, 555, 556, 557, 558]
SCROLLS = [384, 385, 386, 388, 389, 390, 391, 392, 393, 394, 395, 396, 402, 403, 404, 405, 406,
           407, 408, 409, 425, 428]
FOOD = [410, 411, 412, 413, 804, 340, 344, 414, 416, 417, 418, 474, 669, 743, 744]
OTHER_ITEMS = [0, 1, 7, 8, 9, 17, 64, 227, 2, 10, 3, 31, 6, 13, 11, 77, 44, 45, 89, 94, 14, 32,
               12, 36, 15, 24, 130, 131, 51, 59, 86, 25, 37, 16, 29, 34, 560]
# binds_on_equip items: (id, equip slot, identify_difficulty)
BINDING = [(4, 8, 4), (5, 8, 9), (15, 8, 10), (29, 8, 16), (33, 8, 8), (71, 8, 6), (73, 8, 10),
           (74, 8, 16), (145, 9, 9), (149, 4, 12), (160, 4, 7), (168, 4, 14), (195, 10, 14),
           (205, 10, 7), (217, 0, 5), (228, 0, 8), (238, 5, 8), (245, 11, 8), (277, 1, 12),
           (291, 2, 9), (305, 1, 8), (313, 3, 7), (463, 4, 0), (674, 9, 18), (775, 0, 2),
           (781, 2, 6), (791, 9, 9), (798, 8, 6), (818, 1, 8)]
CONSUMABLE_ANY = POTIONS + BOOKS + SCROLLS + BOMBS + POWDERS + FOOD

OCCUPANCY = {'all8': [1] * 8, 'six': [1] * 6 + [0, 0], 'seven': [1] * 7 + [0]}
MAX_OPS = 96


def p32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def i32list(vals):
    return b''.join(p32(v) for v in vals)


def xchar_blob(pattern):
    out = bytearray()
    for slot, occ in enumerate(OCCUPANCY[pattern]):
        row = bytearray(XROW)
        row[0] = occ
        for off in (0x1d, 0x4d, 0x81, 0xa9, 0xd1):      # W8CombatSlot targets: reset
            struct.pack_into('<Iiii', row, off, 0, -1, -1, -1)
        struct.pack_into('<i', row, 0x01, -1)           # pending_action NONE
        struct.pack_into('<i', row, 0x3d, -1)           # action NONE
        struct.pack_into('<i', row, 0x6d, -1)           # action_kind NONE
        struct.pack_into('<i', row, 0xc9, -1)           # item_id
        row[0xd0] = 0xff                                # queued_action -1
        struct.pack_into('<i', row, 0xf1, slot)         # party_order_index
        struct.pack_into('<i', row, 0xfa, -1)           # npc_index: not an NPC
        out += row
    return bytes(out)


class Env:
    """Addresses resolved once per spec."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.status = ctx.g('g_status')
        self.gx = ctx.g('gXStatus')
        self.settings = ctx.g('g_settings')
        self.combat_ptr = ctx.g('g_combat_state')
        self.text_mode = ctx.g('g_text_box_mode')
        self.redraw = ctx.g('g_level_block').deref() + 0xf4
        self.masks = ((self.gx + X_EVENT_QUEUE).deref() + 0x68).deref()
        self.xchar = (self.status + 8).deref()
        self.chars = ctx.char(0)
        self.S0 = ctx.scratch(0)
        self.S1 = ctx.scratch(1)
        self.S2 = ctx.scratch(2)
        self.xblobs = {k: xchar_blob(k) for k in OCCUPANCY}


# --------------------------------------------------------------------------- set-up


def party_slot_bytes(r, density=0.25, being_bias=None):
    """Party effect slots (12 x 0x11): (active, id, amount, percent, duration)."""
    slots = []
    for i in range(12):
        if i < 9 and r.random() < density:
            kind = BEING[i] if (being_bias is None or r.random() < 0.9) else r.choice(BEING)
            slots.append((i, struct.pack('<BiiII', 1, kind, r.choice([1, 2, 3, 4, 5, 6, 7, r.randint(1, 12)]),
                                         r.choice([0, 50, 100, 100, 125, 150, r.randint(0, 200)]),
                                         r.choice([1, 2, 10, 60, 600, 9999, r.randint(1, 5000)]))))
        elif r.random() < 0.05:
            slots.append((i, struct.pack('<BiiII', 0, r.choice(BEING), r.randint(0, 7), 100, 0)))
    return slots


def base(env, c, r, *, occupancy=None, combat_mode=0, verbose=None, combat_state=False,
         party_slots=None, surprise=1):
    """Common set-up; returns (party list, occupancy list)."""
    ctx = env.ctx
    party = ctx.set_party(c, r)
    occ_name = occupancy or r.choice(['all8', 'all8', 'all8', 'six', 'seven'])
    c.setb(env.xchar, env.xblobs[occ_name])
    c.set(env.gx + X_COMBAT, bytes([combat_mode]))
    c.set(env.gx + X_LOCK_TRAP, b'\0\0')
    c.set(env.gx + X_SURPRISE, bytes([surprise]))
    c.set(env.gx + X_SIGHT_REFRESH, b'\0')
    c.set(env.settings + G_DIFFICULTY, p32(r.choice([0, 1, 1, 2])))
    if verbose is None:
        verbose = r.choice([0, 0, 1])
    c.set(env.settings + G_VERBOSE, bytes([verbose]))
    c.set(env.text_mode, b'\0')
    c.set(env.status + S_WORLD_SUSPENDED, b'\0')
    c.set(env.status + S_SKIP_REACTION, b'\0')
    c.set(env.status + S_SELECTED, p32(0))
    c.fill(env.status + S_SLOTS, 12 * 0x11, 0)
    for i, data in (party_slots if party_slots is not None else party_slot_bytes(r)):
        c.set(env.status + S_SLOTS + i * 0x11, data)
    c.fill(env.status + S_MODS, 0x67, 0)
    c.set(env.redraw, p32(0))
    c.fill(env.masks, 0xb1, 0xff)
    if combat_state:
        c.setp(env.combat_ptr, env.S1)
        c.set(env.S1 + CS_ACTION_CHAR, p32(0xffffffff))
    c.note(occ=occ_name, verbose=verbose, combat=combat_mode)
    return party, OCCUPANCY[occ_name]


def combat_slots_bytes(r, density=0.3, n=9, ids=None):
    out = bytearray()
    for i in range(n):
        if r.random() < density:
            kind = r.choice(ids) if ids else r.randint(0, 0x60)
            out += struct.pack('<BiiII', 1, kind, r.choice([1, 2, 3, 5, 7, r.randint(0, 12)]),
                               r.choice([0, 100, 150, r.randint(0, 200)]),
                               r.choice([0, 1, 2, 3, 5, 10, 9999, r.randint(0, 40)]))
        else:
            out += bytes(0x11)
    return bytes(out)


# float regeneration fields RecalculateCharacterDerivedStats rebuilds (x87 80-bit vs
# MSVC float rounding noise; the API has no per-cap float list): health/stamina
# rates and accumulators 0xb69..0xb78, spell_regen_rates[12] 0xb79..0xba8
CHAR_FLOATS = [0xb69, 0xb6d, 0xb71, 0xb75] + [0xb79 + 4 * k for k in range(12)]
CHAR_FLOAT_IGNORE = [s * CHAR + o for s in range(NCHAR) for o in CHAR_FLOATS]


def caps(env, c, *, effect=True, combat=False, extra=()):
    c.cap(env.chars, NCHAR * CHAR, 'chars', ignore=CHAR_FLOAT_IGNORE)
    c.cap(env.xchar, NCHAR * XROW, 'xchar')
    c.cap(env.status + S_SLOTS, 12 * 0x11, 'party_slots')
    c.cap(env.status + S_MODS, 0x67, 'party_mods')
    c.cap(env.gx + X_SIGHT_REFRESH, 1, 'sight_refresh')
    c.cap(env.redraw, 4, 'redraw')
    if effect:
        c.cap(env.S0, E_SIZE, 'effect', ignore=[E_PCITEM, E_MON_DATA, E_TGT_DATA, E_REPORTS_DATA])
        c.cap(env.S0 + E_MON_LIST, 0x40, 'monster_ids')
    if combat:
        c.cap(env.S1, CS_SIZE, 'combat', ignore=[CS_REPORT_DATA])
    for item in extra:
        addr, length, name = item[:3]
        c.cap(addr, length, name, ignore=item[3] if len(item) > 3 else ())
    if len(c.ops) > MAX_OPS:
        raise ValueError('%s: %d ops > %d' % (c.id, len(c.ops), MAX_OPS))


def emit_char(env, c, slot, blob, orig):
    """set only the changed runs of a mutated character."""
    runs = []
    k = 0
    n = len(blob)
    while k < n:
        if blob[k] == orig[k]:
            k += 1
            continue
        start = k
        last = k
        while k < n and k - last < 0x60:
            if blob[k] != orig[k]:
                last = k
            k += 1
        runs.append((start, last + 1))
    for s, e in runs:
        c.set(env.ctx.char(slot) + s, bytes(blob[s:e]))


def recompute_highest(b):
    hi = 0
    for k in range(19, 0, -1):
        if struct.unpack_from('<I', b, C_COND + 4 * k)[0] != 0:
            hi = k
            break
    b.u32(C_HIGHEST, hi)
    top = 0
    for k in range(7, 0, -1):
        if any(b[C_ENCH + 12 * k: C_ENCH + 12 * k + 12]):
            top = k
            break
    b.u32(C_ENCH_TOP, top)


def mutate(env, c, r, party, slot, *, conds=0.35, hp=0.5, dead=0.06, ench=0.3, efe=False,
           sp=0.3, stamina=0.3, iron=0.2, guardian=0.15, haste=0.15):
    """Randomly perturb one party character (conditions, hp, stamina, spell points,
    enchantments) and emit the changes."""
    _, blob, name = party[slot]
    orig = bytes(blob)
    b = Blob(blob)
    hpmax = max(1, b.get_i32(C_HPMAX))
    stmax = max(1, b.get_i32(C_STMAX))
    if r.random() < hp:
        b.u32(C_HP, r.choice([1, 2, 3, max(1, hpmax // 10), max(1, hpmax // 4), hpmax // 2,
                              hpmax - 1, hpmax, r.randint(1, hpmax)]))
    if r.random() < stamina:
        b.u32(C_ST, r.choice([0, 1, 2, stmax // 10, stmax // 3, stmax - 1, stmax, r.randint(0, stmax)]))
    if r.random() < sp:
        for realm in range(6):
            mx = b.get_i32(C_SPMAX + 4 * realm)
            if mx > 0:
                b.u32(C_SPLEFT + 4 * realm, r.choice([0, 1, mx // 2, mx, r.randint(0, mx)]))
    if r.random() < conds:
        for _ in range(r.randint(1, 3)):
            k = r.choice([1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17])
            b.u32(C_COND + 4 * k, r.choice([1, 2, 3, 5, 10, 30, 9999, r.randint(1, 200)]))
            if k == 7:
                b.u32(C_COND_ARG, r.choice([1, 2, 5, 10, 25]))
    if r.random() < ench:
        for _ in range(r.randint(1, 2)):
            k = r.choice([1, 2, 3, 5, 6, 7] + ([4] if efe else []))
            struct.pack_into('<IHHI', b, C_ENCH + 12 * k, r.choice([1, 2, 3, 5, 8, r.randint(1, 20)]),
                             r.choice([0, 100, 125, r.randint(0, 200)]), r.randint(0, 80),
                             r.choice([1, 2, 5, 10, 9999, r.randint(1, 60)]))
    if r.random() < guardian:
        struct.pack_into('<IHHI', b, C_ENCH + 12 * 2, r.randint(1, 8), 100,
                         r.choice([1, 3, 5, 10, 20, 50, r.randint(0, 100)]), r.choice([1, 5, 20]))
    if r.random() < haste:
        struct.pack_into('<IHHI', b, C_ENCH + 12 * 5, r.randint(1, 8), 100, r.randint(0, 30),
                         r.choice([1, 2, 3, 5, 10, 30, 100]))
    if not efe:
        b[C_ENCH + 12 * 4: C_ENCH + 12 * 5] = bytes(12)
    if r.random() < iron:
        for sk in (SK_IRON_WILL, SK_IRON_SKIN):
            if r.random() < 0.5:
                b[C_SKILLS + sk * SKILL_STEP] = 1
                b.u32(C_SKILLS + sk * SKILL_STEP + 2, r.choice([0, 10, 50, 99, 100]))
                b.u32(C_SKILLS + sk * SKILL_STEP + 0xa, r.choice([10, 30, 60]))
    if r.random() < dead:
        b.u32(C_COND + 4 * 18, 9999)
        b.u32(C_HP, 0)
        b.u32(C_ST, 0)
    recompute_highest(b)
    blob[:] = b
    emit_char(env, c, slot, blob, orig)
    return b


def clear_efe(env, c, party):
    """Remove eye-for-an-eye from every character (no reflection re-cast)."""
    for slot, blob, _ in party:
        if any(blob[C_ENCH + 48: C_ENCH + 60]):
            orig = bytes(blob)
            blob[C_ENCH + 48: C_ENCH + 60] = bytes(12)
            b = Blob(blob)
            recompute_highest(b)
            blob[:] = b
            emit_char(env, c, slot, blob, orig)


def pick_targets(r, occ, kmin=1, kmax=4, allow_empty=0.04):
    occupied = [s for s in range(8) if occ[s]]
    pool = occupied if r.random() > allow_empty else list(range(8))
    k = r.randint(kmin, min(kmax, len(pool)))
    return r.sample(pool, k)


def definition(r, kind, *, power=None, scale=None, percent=None, dice=None):
    dur, dpl, sdice, _ = SPELLS.get(kind, (1, 0, (0, 1, 6), 0))
    p = power if power is not None else r.choice([1, 2, 3, 4, 5, 6, 7])
    sc = scale if scale is not None else p
    pct = percent if percent is not None else r.choice([0, 50, 90, 100, 100, 110, 125, 150, 200,
                                                        r.randint(0, 250)])
    if dice is None:
        b0, cnt, sides = sdice
        if cnt == 0 or r.random() < 0.3:
            b0, cnt, sides = r.choice([0, 0, 1, 5]), r.randint(1, 6), r.choice([2, 3, 4, 6, 8, 10, 20])
        dice = (b0, min(255, cnt * (p if r.random() < 0.6 else 1)), sides)
    return {
        'radius': r.choice([0.0, 0.0, 2500.0]),
        'dice': dice,
        'chances': bytes(16),
        'power_level': r.choice([1, 2, 4, 6, 8, 10, 12, 15, 20, 25, 30, r.randint(0, 40)]),
        'magnitude_base': 0,
        'duration_scale': sc,
        'percent': pct,
        'duration_base': r.choice([dur, dur, 0, 1, 2, r.randint(0, 30)]),
        'duration_per_power': r.choice([dpl, dpl, 0, 1, 2, r.randint(0, 12)]),
    }


def put_effect(env, c, kind, *, defn, targets=(), monsters=(), source=(1, 0, -1), sflags=None,
               target=(0, -1, -1, -1), recast=0, reported=0, applied=0, result_count=0,
               result_amount=0, turns=0):
    S0 = env.S0
    sflags = sflags or {}
    b = bytearray(E_SIZE)
    struct.pack_into('<ii', b, 0, kind, turns)
    struct.pack_into('<Iii', b, 0x5c, source[0], source[1], source[2])
    b[0x74] = sflags.get('auto_cast', 0)
    b[0x75] = sflags.get('name_known', 0)
    b[0x76] = sflags.get('aim_resolved', 0)
    b[0x77] = sflags.get('reflection', 0)
    b[0x78] = sflags.get('backfire', 0)
    struct.pack_into('<Iiii', b, 0x90, target[0], target[1], target[2], target[3])
    d = defn
    struct.pack_into('<fhBB', b, 0xb0, d['radius'], d['dice'][0], d['dice'][1], d['dice'][2])
    b[0xb8:0xc8] = d['chances']
    struct.pack_into('<iiiIii', b, 0xc8, d['power_level'], d['magnitude_base'], d['duration_scale'],
                     d['percent'] & 0xffffffff, d['duration_base'], d['duration_per_power'])
    struct.pack_into('<ii', b, 0xe4, len(monsters), max(5, len(monsters)))
    struct.pack_into('<ii', b, 0xf4, len(targets), max(5, len(targets)))
    b[0x120] = recast
    b[0x124] = reported
    b[0x125] = applied
    struct.pack_into('<II', b, 0x126, result_amount, result_count)
    c.set(S0, bytes(b[0:8]))
    c.set(S0 + 0x5c, bytes(b[0x5c:0x12e]))
    c.setp(S0 + E_MON_DATA, S0 + E_MON_LIST)
    c.setp(S0 + E_TGT_DATA, S0 + E_TGT_LIST)
    if monsters:
        c.set(S0 + E_MON_LIST, i32list(monsters))
    if targets:
        c.set(S0 + E_TGT_LIST, i32list(targets))
    c.note(kind=kind, targets=list(targets))


def random_source(r, occ, *, char_bias=0.7, monster=True):
    """Effect source: character, indirect (backfire/reflection), monster (a location
    id no live monster can have) or none."""
    x = r.random()
    if x < char_bias:
        return (1, r.choice([s for s in range(8) if occ[s]]), -1), {}
    if x < char_bias + 0.12:
        return (3, r.randint(0, 7), -1), {'backfire': 1} if r.random() < 0.5 else {'reflection': 1}
    if x < char_bias + 0.22 and monster:
        return (2, -1, 0x7fff0000 + r.randint(0, 0xff)), {}
    return (0, -1, -1), {}


# --------------------------------------------------------------------------- functions


def spec_being(env):
    ctx = env.ctx
    fn = ctx.fn(0x0054cbf0)  # void ApplyBeingEffectSlot(W8SpellEffectEntry*)
    for i in range(ctx.n(260)):
        r = ctx.rng('being', i)
        c = ctx.case('applybeing.%d' % i, fn, conv='c', ret='v')
        combat = 1 if r.random() < 0.2 else 0
        party, occ = base(env, c, r, combat_mode=combat, combat_state=bool(combat),
                          party_slots=party_slot_bytes(r, density=r.choice([0, 0.2, 0.5])))
        x = r.random()
        if x < 0.75:
            kind = r.choice(BEING)
        elif x < 0.83:
            kind = 0                                    # matches the empty entries 9..11
        else:
            kind = r.choice([1, 2, 0x30, 0x31, 0x4c, 23, 0x7f, 149, 0x41])  # not in table: assert
        d = definition(r, kind)
        y = r.random()
        if y < 0.1:
            d['duration_per_power'], d['duration_scale'], d['duration_base'] = 0, d['duration_scale'], 9999
        elif y < 0.18:
            d['duration_per_power'], d['duration_base'] = 0, r.choice([0, 1, 2, 3, 9998])
        elif y < 0.24:
            d['duration_scale'] = r.choice([0, 8, 255, -1, 0x7fffffff])
        targets = [] if r.random() < 0.2 else pick_targets(r, occ, 1, 8)
        for s in r.sample(range(8), r.randint(0, 3)):
            mutate(env, c, r, party, s, conds=0.3, dead=0.05)
        if combat:
            c.set(env.S1 + CS_SLOTS, combat_slots_bytes(r, ids=COMBAT_SLOTS))
            c.set(env.S1 + CS_SLOTS0, combat_slots_bytes(r, n=6, ids=DEFENSE_SLOTS))
        put_effect(env, c, kind, defn=d, targets=targets, applied=r.choice([0, 0, 1]))
        c.arg(env.S0)
        caps(env, c, combat=bool(combat))


def spec_attack_then_inflict(env):
    ctx = env.ctx
    fn = ctx.fn(0x0054dbe0)  # void AttackThenInflictCondition(effect, cond, cond, int, int, int)
    for i in range(ctx.n(300)):
        r = ctx.rng('attackinflict', i)
        c = ctx.case('attackinflict.%d' % i, fn, conv='c', ret='v')
        party, occ = base(env, c, r)
        kind = r.choice([85, 85, 85, 24, 14, 89, 71, 99, r.choice(list(SPELLS))])
        d = definition(r, kind)
        targets = pick_targets(r, occ, 1, 6)
        for s in set(targets + r.sample(range(8), 1)):
            mutate(env, c, r, party, s)
        src, sfl = random_source(r, occ)
        put_effect(env, c, kind, defn=d, targets=targets, source=src, sflags=sfl)
        if r.random() < 0.6:
            a_cond, cond = 11, 6                    # Pandemonium: insane then afraid
        else:
            a_cond = r.choice([3, 4, 5, 6, 7, 9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 0, 8])
            cond = r.choice([3, 4, 5, 6, 7, 9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 0, 8])
        chance = r.choice([100, 100, 100, 50, 25, 0, 1, 99, 101, -1, 0x7fffffff, r.randint(0, 100)])
        a_arg = r.choice([0, 0, 0, 3, 10]) if a_cond == 7 or r.random() < 0.1 else 0
        c_arg = r.choice([0, 0, 0, 3, 10]) if cond == 7 or r.random() < 0.1 else 0
        c.arg(env.S0).arg(a_cond).arg(cond).arg(chance).arg(a_arg).arg(c_arg)
        c.note(a_cond=a_cond, cond=cond, chance=chance)
        caps(env, c)


def spec_combat_slot(env, defense):
    ctx = env.ctx
    if defense:
        fn = ctx.fn(0x0054d380)  # void ApplyDefenseEffectSlot(W8SpellEffectEntry*)
        name, n = 'applydefense', 220
    else:
        fn = ctx.fn(0x0054cdd0)  # void ApplyCombatEffectSlot(W8SpellEffectEntry*)
        name, n = 'applycombat', 240
    for i in range(ctx.n(n)):
        r = ctx.rng(name, i)
        tag = ''
        x = r.random()
        if defense:
            if x < 0.72:
                kind = r.choice(DEFENSE_SLOTS)
            elif x < 0.8:
                kind = 0
            elif x < 0.9:
                kind, tag = r.choice(DEFENSE_OVERFLOW), '.overflow'
            else:
                kind = r.choice([1, 0x31, 0x30, 8, 0x5d, 100, 0x7f])
        else:
            if x < 0.72:
                kind = r.choice(COMBAT_SLOTS)
            elif x < 0.8:
                kind = 0
            elif x < 0.86:
                kind, tag = 2, '.bless_edge'
            else:
                kind = r.choice([1, 0x35, 0x3b, 0x3e, 8, 100, 0x7f])
        c = ctx.case('%s.%d%s' % (name, i, tag), fn, conv='c', ret='v')
        combat = 0 if r.random() < 0.1 else 1
        party, occ = base(env, c, r, combat_mode=combat, combat_state=True)
        for s in r.sample(range(8), r.randint(0, 3)):
            mutate(env, c, r, party, s, conds=0.3, dead=0.1)
        c.set(env.S1 + CS_SLOTS, combat_slots_bytes(r, ids=COMBAT_SLOTS + [0, 2, 0x30]))
        c.set(env.S1 + CS_SLOTS0, combat_slots_bytes(r, n=6, ids=DEFENSE_SLOTS + [0]))
        d = definition(r, kind)
        if r.random() < 0.15:
            d['duration_per_power'], d['duration_base'] = 0, r.choice([9999, 0, 1, 2])
        src, sfl = random_source(r, occ, char_bias=0.6)
        targets = [] if r.random() < 0.25 else pick_targets(r, occ, 1, 8)
        put_effect(env, c, kind, defn=d, targets=targets, source=src, sflags=sfl,
                   reported=r.choice([0, 0, 1]), result_count=r.choice([0, 0, 0, 1, 3, 7]),
                   applied=r.choice([0, 1]))
        c.arg(env.S0)
        caps(env, c, combat=True)


def spec_affliction(env):
    ctx = env.ctx
    fn = ctx.fn(0x0054fa30)  # void ResolveAfflictionAgainstTargets(W8SpellEffectEntry*)
    for i in range(ctx.n(260)):
        r = ctx.rng('affliction', i)
        c = ctx.case('affliction.%d' % i, fn, conv='c', ret='v')
        party, occ = base(env, c, r)
        kind = r.choice([86, 86, 99, 99, r.choice(list(SPELLS))])
        d = definition(r, kind)
        targets = pick_targets(r, occ, 1, 8)
        for s in set(targets):
            if r.random() < 0.8:
                mutate(env, c, r, party, s)
        src, sfl = random_source(r, occ)
        put_effect(env, c, kind, defn=d, targets=targets, source=src, sflags=sfl,
                   reported=r.choice([0, 0, 1]))
        c.arg(env.S0)
        caps(env, c)


def spec_damage_report(env):
    ctx = env.ctx
    fn = ctx.fn(0x00550c10)  # void DamageTargetsAndReport(W8SpellEffectEntry*)
    for i in range(ctx.n(260)):
        r = ctx.rng('dmgreport', i)
        c = ctx.case('dmgreport.%d' % i, fn, conv='c', ret='v')
        party, occ = base(env, c, r)
        kind = r.choice([125, 125, 125, r.choice(list(SPELLS))])
        d = definition(r, kind)
        if r.random() < 0.2:
            d['dice'] = r.choice([(0, 0, 0), (0, 1, 1), (100, 10, 20), (-5, 1, 4), (0, 255, 255)])
        targets = pick_targets(r, occ, 1, 8)
        for s in set(targets):
            if r.random() < 0.75:
                b = mutate(env, c, r, party, s, conds=0.3)
                if r.random() < 0.15:          # already drained / odd hp adjustment
                    orig = bytes(party[s][1])
                    b.u32(C_COND + 4 * 1, r.choice([0, 9999, 5]))
                    b.u32(C_HPADJ, r.choice([0, -10, 5, -1000]))
                    recompute_highest(b)
                    party[s][1][:] = b
                    emit_char(env, c, s, party[s][1], orig)
        src, sfl = random_source(r, occ)
        put_effect(env, c, kind, defn=d, targets=targets, source=src, sflags=sfl,
                   reported=r.choice([0, 0, 1]))
        c.arg(env.S0)
        caps(env, c)


def item_bytes(item, stack, r):
    return struct.pack('<iBBBBBBBB', item, stack & 0xff, r.choice([0, 0, 1, 5]),
                       r.choice([0, 1]), 0, 0, 0, 0, 0)


def fill_consumables(env, c, r, party, slot, density=0.5):
    """Put potions/books/scrolls/bombs/... into one character's backpack and misc slots."""
    _, blob, _ = party[slot]
    orig = bytes(blob)
    for k in range(8):
        if r.random() < density:
            item = r.choice(CONSUMABLE_ANY + POTIONS + SCROLLS + BOOKS)
            stack = r.choice([1, 1, 2, 3, 5, 0, 10, 255, r.randint(1, 9)])
            blob[C_PACK + 12 * k: C_PACK + 12 * k + 12] = item_bytes(item, stack, r)
        elif r.random() < 0.1:
            blob[C_PACK + 12 * k: C_PACK + 12 * k + 12] = struct.pack('<i8x', -1)
    for k in (1, 2, 8, 9):
        if r.random() < density * 0.3:
            item = r.choice(POTIONS + SCROLLS + BOOKS + BOMBS)
            blob[C_EQUIP + 12 * k: C_EQUIP + 12 * k + 12] = item_bytes(item, r.choice([1, 2, 3, 5]), r)
    emit_char(env, c, slot, blob, orig)


def set_pool(env, c, r, k):
    """Party item pool: k valid entries, 16 entries written, count = k."""
    data = bytearray()
    for j in range(16):
        if j < k:
            item = r.choice(CONSUMABLE_ANY + OTHER_ITEMS) if r.random() < 0.8 else r.choice(OTHER_ITEMS)
            data += item_bytes(item, r.choice([1, 1, 2, 3, 5, 0, 255, r.randint(1, 9)]), r)
        else:
            data += struct.pack('<i8x', -1)
    c.set(env.status + S_POOL, bytes(data))
    c.set(env.status + S_POOL_COUNT, p32(k))
    return [(env.status + S_POOL, 16 * 12, 'pool'), (env.status + S_POOL_COUNT, 4, 'pool_count')]


def spec_destroy_consumables(env):
    ctx = env.ctx
    fn = ctx.fn(0x005510b0)  # void DestroyConsumablesOnTargets(W8SpellEffectEntry*)
    for i in range(ctx.n(260)):
        r = ctx.rng('heatwave', i)
        c = ctx.case('heatwave.%d' % i, fn, conv='c', ret='v')
        party, occ = base(env, c, r)
        kind = 126
        scale = r.choice([0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 255, 0x1999999a, -1, r.randint(1, 8)])
        d = definition(r, kind, scale=scale)
        targets = [] if r.random() < 0.12 else pick_targets(r, occ, 1, 4)
        for s in set(targets):
            fill_consumables(env, c, r, party, s, density=r.choice([0.3, 0.6, 1.0]))
        extra = set_pool(env, c, r, r.choice([0, 1, 2, 3, 5, 8, 12, 16]))
        put_effect(env, c, kind, defn=d, targets=targets, reported=r.choice([0, 0, 1]))
        c.arg(env.S0)
        c.note(scale=scale)
        caps(env, c, extra=extra)


def spec_reduce_durations(env):
    ctx = env.ctx
    fn = ctx.fn(0x0054d100)  # void ReduceCombatEffectDurations(W8SpellEffectEntry*)
    for i in range(ctx.n(240)):
        r = ctx.rng('purify', i)
        c = ctx.case('purify.%d' % i, fn, conv='c', ret='v')
        combat = 0 if r.random() < 0.08 else 1
        party, occ = base(env, c, r, combat_mode=combat, combat_state=True)
        for s in r.sample(range(8), r.randint(0, 2)):
            mutate(env, c, r, party, s, conds=0.2)
        # slots: active flags and durations around reduce = 5 - level + duration (+1 jitter)
        slots = bytearray()
        for j in range(9):
            if r.random() < 0.6:
                slots += struct.pack('<BiiII', 1, r.choice(COMBAT_SLOTS + [0, 0x31]),
                                     r.randint(0, 7), r.choice([0, 100, 150]),
                                     r.choice([0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 15, 9999, r.randint(0, 30)]))
            else:
                slots += struct.pack('<BiiII', 0, 0, 0, 0, r.choice([0, 0, 5]))
        c.set(env.S1 + CS_SLOTS, bytes(slots))
        c.set(env.S1 + CS_SLOTS0, combat_slots_bytes(r, n=6, ids=DEFENSE_SLOTS))
        scale = r.choice([0, 1, 2, 3, 4, 5, 6, 7, 10, 20, 9999, 9998, -3, r.randint(0, 12)])
        d = definition(r, 72, scale=scale)
        targets = [] if r.random() < 0.3 else pick_targets(r, occ, 1, 8)
        put_effect(env, c, 72, defn=d, targets=targets, applied=r.choice([0, 1]))
        c.arg(env.S0)
        c.note(scale=scale)
        caps(env, c, combat=True)


def spec_finish(env):
    ctx = env.ctx
    fn = ctx.fn(0x0054c930)  # void FinishSpellEffectTargets(W8SpellEffectEntry*)
    kinds = sorted(SPELLS) + list(range(0, 150))
    for i in range(ctx.n(160)):
        r = ctx.rng('finish', i)
        c = ctx.case('finish.%d' % i, fn, conv='c', ret='v')
        party, occ = base(env, c, r)
        kind = r.choice(kinds)
        targets = [] if r.random() < 0.2 else pick_targets(r, occ, 1, 8)
        # Eye for an Eye only where it cannot win (dead, zero power or no turns):
        # a positive best would re-cast the spell.
        for s, blob, _ in party:
            orig = bytes(blob)
            b = Blob(blob)
            mode = r.choice(['none', 'none', 'dead', 'nopower', 'noturns'])
            if mode == 'none':
                b[C_ENCH + 48: C_ENCH + 60] = bytes(12)
            elif mode == 'dead':
                struct.pack_into('<IHHI', b, C_ENCH + 48, r.randint(1, 9), 100, 0, r.randint(1, 9))
                b.u32(C_COND + 4 * 18, 9999)
                b.u32(C_HP, 0)
            elif mode == 'nopower':
                struct.pack_into('<IHHI', b, C_ENCH + 48, 0, 100, 0, r.randint(1, 9))
            else:
                struct.pack_into('<IHHI', b, C_ENCH + 48, r.randint(1, 9), 100, 0, 0)
            recompute_highest(b)
            blob[:] = b
            emit_char(env, c, s, blob, orig)
        nmon = r.choice([0, 0, 1, 2, 3, 5, 8])
        monsters = [r.choice([0x00100000 + r.randint(0, 0xffff), 0x7fff0000 + r.randint(0, 99),
                              -2, -0x1000, 0x40000000]) for _ in range(nmon)]
        if nmon > 1 and r.random() < 0.3:
            monsters[-1] = monsters[0]
        flags = {}
        x = r.random()
        if x < 0.15:
            flags['aim_resolved'] = 1
        elif x < 0.3:
            flags['backfire'] = 1
        elif x < 0.4:
            flags['reflection'] = 1
        src, _ = random_source(r, occ)
        d = definition(r, kind)
        put_effect(env, c, kind, defn=d, targets=targets, monsters=monsters, source=src, sflags=flags)
        c.arg(env.S0)
        c.note(monsters=monsters, flags=flags)
        caps(env, c)


def spec_tick_combat(env):
    ctx = env.ctx
    fn = ctx.fn(0x005526f0)  # void TickCombatEffectSlots(W8EffectSlot*, W8CombatSlot*)
    damage_ids = [48, 76, 80, 81, 93]
    for i in range(ctx.n(280)):
        r = ctx.rng('tickcombat', i)
        c = ctx.case('tickcombat.%d' % i, fn, conv='c', ret='v')
        party, occ = base(env, c, r)
        for s in r.sample(range(8), r.randint(0, 5)):
            mutate(env, c, r, party, s, conds=0.3, dead=0.08)
        slots = bytearray()
        nact = 0
        for j in range(9):
            if r.random() < r.choice([0.2, 0.4, 0.7]):
                kind = r.choice(damage_ids + damage_ids + [49, 0, 2, 0x3e, 8])
                power = r.choice([1, 2, 3, 4, 5, 6, 7, 0, 8, 255, 256, r.randint(1, 12)])
                pct = r.choice([0, 50, 100, 100, 150, 200, r.randint(0, 255)])
                slots += struct.pack('<BiiII', 1, kind, power, pct, r.randint(0, 20))
                nact += 1
            else:
                slots += struct.pack('<BiiII', 0, r.choice(damage_ids), r.randint(0, 7), 100, 0)
        c.set(env.S2, bytes(slots))
        x = r.random()
        if x < 0.9:
            ttype = 2                       # party
        else:
            ttype = r.choice([0, 1, 4])     # neither party nor monster: assert per active slot
        tchar = r.randint(0, 7)
        c.set(env.S2 + 0x100, struct.pack('<Iiii', ttype, tchar, -1, -1))
        c.arg(env.S2).arg(env.S2 + 0x100)
        c.note(active=nact, ttype=ttype, tchar=tchar)
        caps(env, c, effect=False, extra=[(env.S2, 9 * 0x11, 'slots'), (env.S2 + 0x100, 0x20, 'target')])


# dispatcher whitelist: kinds whose handlers stay on the party / effect / scratch state
DISPATCH = {
    'early': [1, 5, 10, 11, 25, 47, 79, 121, 122],
    'default': [0, 102, 119, 128, 132, 149],
    'defense': [2, 53, 59, 62],
    'combatslot': [48, 49, 76, 80, 81, 93],
    'purify': [72],
    'damage': [4, 9, 22, 28, 36, 43, 50, 52, 55, 57, 63, 66, 77, 83, 96, 97, 98, 101, 118, 131],
    'heal': [6, 68],
    'inflict': [7, 12, 14, 15, 24, 29, 31, 37, 46, 67, 69, 70, 87, 89, 90, 94, 117],
    'being': [8, 17, 20, 26, 32, 33, 40, 45, 64],
    'stamina': [13, 44],
    'cures': [16, 34, 35, 51, 74, 88, 100, 116, 120],
    'trap': [18, 39],
    'enchant': [19, 21, 27, 54, 56, 61, 65],
    'identify': [23],
    'dmgcond': [42, 71, 78, 91, 92, 129],
    'removecurse': [58],
    'drain': [82, 84],
    'pandemonium': [85],
    'prismic': [86, 99],
    'restore': [114, 115],
    'bane': [124],
    'vortex': [125],
    'heatwave': [126],
    'antimagic': [127],
    'booze': [130],
}
DISPATCH_WEIGHT = {'early': 1, 'default': 1, 'trap': 1, 'identify': 2, 'bane': 2, 'antimagic': 2,
                   'removecurse': 2, 'booze': 2, 'heatwave': 2, 'vortex': 2, 'purify': 2}


def spec_dispatch(env):
    ctx = env.ctx
    fn = ctx.fn(0x0054ba00)  # void ProcessSpellEffectTargets(W8SpellEffectEntry*)
    groups = []
    every = []                       # every whitelisted kind once, then weighted by group
    for g, ks in DISPATCH.items():
        groups += [g] * DISPATCH_WEIGHT.get(g, 3)
        every += [(g, k) for k in ks]
    for i in range(ctx.n(420)):
        r = ctx.rng('dispatch', i)
        if i < len(every):
            g, kind = every[i]
        else:
            g = r.choice(groups)
            kind = r.choice(DISPATCH[g])
        c = ctx.case('dispatch.%d.%s.k%d' % (i, g, kind), fn, conv='c', ret='v')
        need_combat = g in ('defense', 'combatslot', 'purify')
        combat = 1 if need_combat and r.random() < 0.92 else 0
        party, occ = base(env, c, r, combat_mode=combat, combat_state=need_combat)
        extra = []
        for s in r.sample(range(8), r.randint(0, 4)):
            mutate(env, c, r, party, s)
        clear_efe(env, c, party)
        if need_combat:
            c.set(env.S1 + CS_SLOTS, combat_slots_bytes(r, ids=COMBAT_SLOTS))
            c.set(env.S1 + CS_SLOTS0, combat_slots_bytes(r, n=6, ids=DEFENSE_SLOTS))
        d = definition(r, kind)
        targets = pick_targets(r, occ, 1, 8) if r.random() < 0.9 else []
        tslot = targets[0] if targets else r.choice([s for s in range(8) if occ[s]])
        target = (r.choice([1, 2]), tslot, -1, -1)
        # Lifesteal / Might to Magic heal a monster source through MonsterInfoFromID
        src, sfl = random_source(r, occ, monster=(g != 'drain'))
        if r.random() < 0.3:
            sfl = dict(sfl, backfire=1)
        if r.random() < 0.15:
            sfl = dict(sfl, auto_cast=1)
        if r.random() < 0.2:
            sfl = dict(sfl, name_known=1)
        if g == 'identify':
            src, sfl = (1, tslot, -1), {'backfire': sfl.get('backfire', 0)}
            _, blob, _ = party[tslot]
            orig = bytes(blob)
            k = r.randint(0, 7)
            item = r.choice(OTHER_ITEMS + [b[0] for b in BINDING] + POTIONS)
            blob[C_PACK + 12 * k: C_PACK + 12 * k + 12] = struct.pack('<iBB6x', item, 1, r.choice([0, 1]))
            emit_char(env, c, tslot, blob, orig)
            target = (7, -1, -1, -1)
            d['duration_scale'] = r.choice([0, 1, 2, 3, 4, 5, 6, 7, 10, 255])
        elif g == 'removecurse':
            target = (r.choice([1, 1, 1, 2]), tslot, -1, -1)
            _, blob, _ = party[tslot]
            orig = bytes(blob)
            for _ in range(r.randint(0, 3)):
                item, eslot, _diff = r.choice(BINDING)
                blob[C_EQUIP + 12 * eslot: C_EQUIP + 12 * eslot + 12] = struct.pack(
                    '<iBBBBBBBB', item, 1, 0, r.choice([0, 1]), 0, 0, 0, r.choice([0, 1]), r.choice([0, 1]))
            emit_char(env, c, tslot, blob, orig)
            d['duration_scale'] = r.choice([0, 1, 2, 3, 4, 5, 6, 7])
        elif g in ('cures', 'booze'):
            target = (1, tslot, -1, -1)
            if g == 'booze':
                targets = [tslot]
        elif g == 'bane':
            gold = r.choice([0, 1, 99, 100, 101, 1000, 123456, 0x7fffffff, 0xffffffff, r.randint(0, 50000)])
            c.set(env.status + S_GOLD, p32(gold))
            extra.append((env.status + S_GOLD, 4, 'gold'))
            if r.random() < 0.3:
                d['dice'] = r.choice([(60, 1, 7), (100, 0, 0), (99, 1, 1), (0, 1, 100), (200, 2, 50)])
            c.note(gold=gold)
        elif g == 'heatwave':
            targets = targets[:4]
            for s in set(targets):
                fill_consumables(env, c, r, party, s, density=0.6)
            extra += set_pool(env, c, r, r.choice([0, 2, 5, 9]))
        put_effect(env, c, kind, defn=d, targets=targets, source=src, sflags=sfl, target=target,
                   reported=r.choice([0, 0, 1]), applied=r.choice([0, 0, 1]))
        if g == 'identify':
            # target.pPCItem -> the backpack item (captured with the characters)
            c.setp(env.S0 + E_PCITEM, env.ctx.char(tslot) + C_PACK + 12 * k)
        c.arg(env.S0)
        c.note(group=g, sflags=sfl)
        caps(env, c, combat=need_combat, extra=extra)


def spec_char_damage(env, dice):
    ctx = env.ctx
    if dice:
        fn = ctx.fn(0x00553350)  # void ApplyDiceDamageToCharacter(int, W8TargetSource*, W8Enchantment*)
        name = 'dicedamage'
    else:
        fn = ctx.fn(0x005535D0)  # void ApplyDirectDamageToCharacter(int, W8TargetSource*, int)
        name = 'directdamage'
    for i in range(ctx.n(240)):
        r = ctx.rng(name, i)
        c = ctx.case('%s.%d' % (name, i), fn, conv='c', ret='v')
        party, occ = base(env, c, r, combat_state=True)
        slot = r.choice([s for s in range(8) if occ[s]]) if r.random() < 0.95 else r.randint(0, 7)
        b = mutate(env, c, r, party, slot, conds=0.25, dead=0.05, guardian=0.3, iron=0.3)
        if r.random() < 0.4:
            orig = bytes(party[slot][1])
            b.u32(C_DR, r.choice([0, 0, 5, 10, 25, 50, 75, 99, 100, 120, -10]))
            party[slot][1][:] = b
            emit_char(env, c, slot, party[slot][1], orig)
        report = bytearray(0xa2)
        struct.pack_into('<II', report, 0, r.choice([0, 0, 10]), r.choice([0, 0, 2]))
        struct.pack_into('<6I', report, 0x68, *[r.choice([0, 0, 5, 100]) for _ in range(6)])
        c.set(env.S1 + CS_REPORT, bytes(report))
        c.set(env.S2 + 0x200, struct.pack('<Iii', r.choice([0, 1, 2]), r.randint(-1, 7), -1))
        c.arg(slot).arg(env.S2 + 0x200)
        if dice:
            power = r.choice([0, 1, 1, 2, 3, 4, 5, 6, 7, 8, 10, 85, 255, 256, 257, 0xffffffff,
                              r.randint(1, 12)])
            c.set(env.S2 + 0x100, struct.pack('<IHHI', power, r.choice([0, 100]), r.randint(0, 40),
                                              r.choice([0, 1, 5])))
            c.arg(env.S2 + 0x100)
            c.note(slot=slot, power=power)
        else:
            hp = b.get_u32(C_HP)
            damage = r.choice([-100, -1, 0, 1, 2, 5, 10, 50, hp - 1, hp, hp + 1, hp * 2, 1000,
                               0x7fffffff, -0x80000000, 0x01000000, r.randint(1, 200)])
            c.arg(damage)
            c.note(slot=slot, damage=damage)
        # the reports vector data pointer lives inside attack_report: ignored
        caps(env, c, effect=False,
             extra=[(env.S1 + CS_REPORT, 0xa2, 'attack_report', [CS_REPORT_DATA - CS_REPORT])])


def cases(ctx):
    env = Env(ctx)
    spec_being(env)
    spec_attack_then_inflict(env)
    spec_combat_slot(env, defense=False)
    spec_combat_slot(env, defense=True)
    spec_affliction(env)
    spec_damage_report(env)
    spec_destroy_consumables(env)
    spec_reduce_durations(env)
    spec_finish(env)
    spec_tick_combat(env)
    spec_dispatch(env)
    spec_char_damage(env, dice=True)
    spec_char_damage(env, dice=False)
