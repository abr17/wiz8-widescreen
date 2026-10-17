"""Magic.cpp, second half (source lines 2001-4100): spell-target resolution.

Tested (retail address, function, cases at scale 1.0; 1820 in total):
  0x004F9AE0 SpellAffectedTarget            450  every switch arm: being/combat effect
             slots (float ratio <= 0.25, unsigned/signed divisor edges, duration 9999 and
             wrap-to-zero), enchantment turns on characters and fake monsters, Haste over
             the party (slot 5 vs 3), heal/stamina/rest/restoration/cure condition checks,
             Purify Air, Sonic Boom/Lure, the 14 cooldown clocks (guiCurrentTime set),
             Identify Item, Remove Curse with binds-on-equip gear, default spells
  0x004FE740 RedirectBackfiredSpellTarget   260  all target kinds (char/indirect char/
             party/monster/group/invalid) x source kinds, party participation edges
  0x004FEA50 PrepareSpellTarget             260  target types 1,2,3(+Charm/Mindread),4,6,7,
             10 and the asserting ones (0,8,9), point type with char/monster/indirect source
  0x004FEDC0 PickBackfireTarget             260  party/monster candidates, seeded Random,
             group spells (target type 4) vs single
  0x004FD030 PopulateSpellTargetMarkers     330  caster/ally/enemy, enemy group (fake groups),
             party, radius and all-enemies with a fake monster world and a fake party
             navigator; the inlined PruneSpellTargetMarkers (Holy Water/Banish/Dispel Undead)
  0x00501D20 TrackItemSpellSource           260  corpus characters with spell items in
             equipment/backpack, charges, spell id edges

World set-up used by several functions (all through scratch buffers, restored after the
case): gXStatus.plsMonsterList / plsMonsterGroupList are pointed at fake PLists of fake
W8MonsterInfo / W8MonsterGroup records (unborn and encounter lists nulled), the monster
record cache entries for the fake species point at fake records, g_startup_world is
pointed at a fake navigator, g_combat_state at a fake W8CombatState or null.

Skipped:
  0x004fb360 SpawnLureEffects            spawns spell visuals in the world (object creation)
  0x005005c0 ReportSpellResult           text box output only (UI)
  0x004fac40 ValidateSpellTarget         posts notices, queues character voice events and
                                         runs the world-cursor command; its target logic is
                                         PopulateSpellTargetMarkers (tested)
  0x004FA4D0 ExecuteCharacterSpellCast   performs the cast: notices, sounds, spell effect
                                         objects, SP spend
  0x004FB4C0 CastSpellFromSource         creates spell effect entries, visuals, missiles,
                                         sounds (object creation)
  0x004FEF90 ScatterSpellPointTarget     result comes from octree line-of-sight traces and
                                         ground settling against live level geometry
  0x004FF220 CheckSpellBackfire          not in the port map (inlined into
                                         CastSpellFromSource) - cannot be called
  0x00501B70 PruneSpellTargetMarkers     not in the port map (inlined into
                                         PopulateSpellTargetMarkers) - covered there
PopulateSpellTargetMarkers paths not exercised: cone targets (5) and the line-of-sight
traces (kept out of reach by distances, highlighting and the backfire/reflection flags
that skip SourceActionReachesTarget)."""
import math
import struct

CHAR = 0x1862
# W8Character
C_COND = 0xa01
C_ENCH = 0xa65
C_HIGH = 0xb01
C_HPMAX = 0xb0d
C_HP = 0xb11
C_STMAX = 0xb19
C_ST = 0xb1d
C_BLOCK0 = 0xa01            # uiCondition .. stamina, set as one block per character
C_BLOCK1 = 0xb21
C_EQUIP = 0xf5d
C_PACK = 0x1029
C_ITEMS1 = 0x1089           # end of backpack
# W8PartySlotRow
XROW = 0x106
# gXStatus
XS_COMBAT = 0x8dc
XS_HOSTILE = 0x8ed
XS_MONLIST = 0x8f5
XS_GRPLIST = 0x8f9
XS_UNBORN = 0x901
XS_ENCLIST = 0x905
XS_RECCACHE = 0xa0f
XS_CLOCKS = 0x19c0
# g_status
GS_XCHAR = 8
GS_EFFECT = 0x17af
GS_ITEMUSE = 0x24a0
# W8CombatState
CS_EFFECT = 0x7c1
CS_EFFECT0 = 0x85a
CS_ENGAGED = 0xa54
# W8MonsterInfo
M_P3D = 0xc
M_HPMAX = 0x27
M_COND = 0x57
M_ENCH = 0xa7
M_HEAD = 0x10b              # location_id .. highest_condition
M_SUMMONED = 0x2da
M_LOS = 0x34d
MSTRIDE = 0x430             # >= sizeof(W8MonsterInfo) 0x425: tails stay zero
# fake W8Monster (navigator base at +0x18): radius +0x9c, position +0x118,
# alternate_radius +0x18c, height_offset +0x190. The fake objects overlap 0x14 apart:
# for up to 6 of them those four fields never collide (only they are read).
P3D_STRIDE = 0x14
P3D_MAX = 6
P3D_LO = 0x9c
P3D_HI = 0x194
NAV = 0x8000                # fake g_startup_world navigator in scratch 4
# W8MonsterRecord: kind +0xcb, untargetable +0x24a; overlapping records 0x10 apart
REC_BASE = 0x2000
REC_STRIDE = 0x10
SPECIES_BASE = 990
# W8MonsterGroup (fields read: group_id +0, monsters +8, ubDisposition +0x2a,
# leader_location_id +0x9f); fake groups overlap 0x30 apart without field collisions
G_STRIDE = 0x30
G_ID = 0
G_MONSTERS = 8
G_DISP = 0x2a
G_LEADER = 0x9f
# scratch 0
AIM = 0x000                 # W8CombatSlot (target / aim)
SRC = 0x100                 # W8TargetSource
ITEM = 0x200                # W8ItemInstance for Identify Item
MVEC = 0x300                # W8GrowableVector<int> monster markers
PVEC = 0x310                # W8GrowableVector<int> party markers
MDATA = 0x400
PDATA = 0x500
# scratch 2
MPL = 0x000
MPL_DATA = 0x010
GPL = 0x100
GPL_DATA = 0x110
ILS = 0x200
IL_DATA = 0x400

MAX_OPS = 96

# SpellTables.dbs (version 1, 150 records): duration, duration_per_level, target_type,
# range_category, effect_radius.
SPELL_DUR = [0, 0, 2, 0, 0, 0, 0, 1, 0, 0, 1, 1, 1, 0, 1, 1, 0, 2, 0, 1, 30, 2, 0, 0, 1, 0, 30, 1, 0, 1,
             0, 1, 30, 6, 0, 0, 0, 1, 0, 0, 30, 0, 0, 0, 0, 120, 1, 0, 1, 1, 0, 0, 0, 1, 1, 0, 1, 0, 0, 1,
             0, 1, 1, 0, 12, 1, 0, 1, 0, 1, 0, 1, 0, 0, 0, 0, 1, 0, 1, 0, 1, 1, 0, 0, 0, 1, 1, 0, 0, 1,
             0, 1, 1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
SPELL_DPL = [0, 0, 0, 0, 0, 0, 0, 0, 720, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0,
             0, 0, 0, 0, 0, 0, 0, 0, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 1, 0, 0, 0, 0, 3,
             0, 0, 3, 0, 12, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
             0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
SPELL_TT = [0, 3, 2, 3, 3, 3, 1, 5, 2, 3, 3, 3, 4, 1, 4, 6, 1, 2, 10, 1, 2, 1, 6, 9, 4, 5, 2, 1, 5, 4,
            6, 5, 2, 2, 1, 1, 6, 4, 8, 10, 2, 3, 6, 5, 2, 2, 4, 5, 6, 5, 3, 1, 5, 2, 1, 6, 2, 6, 1, 2,
            8, 1, 2, 5, 2, 1, 3, 7, 2, 6, 3, 4, 2, 0, 1, 0, 6, 7, 5, 3, 6, 6, 3, 5, 3, 7, 5, 6, 1, 3,
            7, 3, 3, 6, 7, 7, 7, 7, 7, 7, 1, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 7, 6, 5,
            1, 4, 4, 8, 4, 4, 4, 4, 4, 7, 0, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
SPELL_RNG = [0, 2, 0, 2, 2, 2, 2, 2, 0, 2, 2, 2, 2, 2, 3, 3, 2, 0, 0, 1, 0, 1, 2, 0, 3, 2, 0, 1, 2, 3,
             3, 2, 0, 0, 2, 2, 3, 3, 3, 0, 0, 2, 3, 2, 0, 0, 3, 2, 3, 2, 3, 2, 2, 0, 1, 3, 0, 3, 1, 0,
             1, 1, -1, 2, 0, 1, 3, 3, 0, 3, 3, 3, 0, 0, 2, 0, 3, 3, 2, 3, 3, 3, 2, 2, 2, 3, 2, 3, 1, 2,
             3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 2, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 2, 3, -1, 2,
             1, 2, 2, 3, 1, 0, 1, 1, 1, 2, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
SPELL_RAD = [0, 0, 15, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 15, 0, 0, 0, 0, 15, 0, 15, 0, 0, 0, 15, 0, 0, 0,
             50, 0, 15, 0, 0, 0, 15, 0, 50, 0, 15, 0, 15, 0, 15, 0, 0, 0, 15, 0, 0, 0, 0, 15, 0, 15, 15, 15, 0, 15,
             0, 0, 0, 0, 0, 0, 0, 0, 15, 15, 0, 0, 15, 0, 0, 0, 15, 0, 0, 0, 15, 15, 0, 0, 0, 0, 0, 15, 0, 0,
             0, 0, 0, 15, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 15, 0,
             0, 0, 0, 50, 0, 0, 0, 0, 0, 0, 0, 10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
RANGE_STEPS = {-1: 0, 0: 2, 1: 4, 2: 25, 3: 50}
WORLD_SCALE = 500.0


def spells_with_tt(*tts):
    return [s for s in range(150) if SPELL_TT[s] in tts]


# Items.dbs (819 records): records with a spell, binds-on-equip records.
ITEM_COUNT = 819
SPELL_ITEMS = [16, 19, 24, 27, 33, 34, 42, 43, 44, 46, 47, 60, 61, 68, 69, 74, 81, 85, 86, 87, 88, 100, 101,
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
CHARGE_ITEMS = [16, 19, 24, 27, 33, 34, 42, 43, 44, 60, 61, 68, 74, 81, 85, 86, 87, 88, 254, 255, 256, 257, 259,
                262, 263, 265, 273, 276, 277, 278, 280, 285, 286, 287, 292, 304, 305, 310, 332, 419, 464, 465,
                466, 469, 492, 496, 499, 590, 591, 592, 593, 753, 755, 770, 772, 789, 812, 818]
BOE_ITEMS = [4, 5, 15, 29, 33, 43, 48, 71, 73, 74, 85, 86, 89, 145, 149, 160, 168, 179, 195, 205, 208, 217,
             228, 234, 238, 245, 277, 291, 305, 313, 463, 469, 660, 674, 755, 775, 781, 791, 798, 818]

# retail tables (0x00616D84, 0x00616DD8, 0x00616E34)
BEING_IDX = {32: 0, 33: 1, 17: 2, 20: 3, 8: 4, 40: 5, 26: 6, 45: 7, 64: 8}
CSLOT_IDX = {2: 0, 53: 1, 59: 2, 62: 3, 30: 6, 40: 7, 50: 8}
COOL_IDX = {30: 0, 38: 1, 75: 2, 73: 3, 32: 4, 33: 5, 17: 6, 20: 7, 8: 8, 40: 9, 26: 10, 45: 11, 64: 12, 58: 13}
ENCH_SLOT = {19: 1, 21: 2, 27: 3, 54: 4, 56: 5, 61: 6, 65: 7}


def U(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def F(v):
    return struct.pack('<f', float(v))


def m32(v):
    return int(v) & 0xffffffff


def check_ops(c):
    if len(c.ops) > MAX_OPS:
        raise ValueError('%s: %d ops > %d' % (c.id, len(c.ops), MAX_OPS))


# --- set-up helpers -------------------------------------------------------------------

class PartyEdit:
    """Field edits on the corpus characters put by set_party: one contiguous
    uiCondition..stamina block per edited character."""

    def __init__(self, party):
        self.blobs = {s: b for s, b, _ in party}
        self.names = {s: n for s, _, n in party}
        self.blocks = {}
        self.touched = {}

    def blk(self, slot):
        if slot not in self.blocks:
            self.blocks[slot] = bytearray(self.blobs[slot][C_BLOCK0:C_BLOCK1])
        return self.blocks[slot]

    def put(self, slot, off, v):
        struct.pack_into('<I', self.blk(slot), off - C_BLOCK0, m32(v))
        self.touched.setdefault(slot, set()).add(off)

    def get(self, slot, off):
        if slot in self.blocks:
            return struct.unpack_from('<I', self.blocks[slot], off - C_BLOCK0)[0]
        return struct.unpack_from('<I', self.blobs[slot], off)[0]

    def flush(self, ctx, c, gap=12):
        """Only the touched dwords (merged into runs when closer than `gap`; the rest is
        the corpus value already)."""
        for slot in sorted(self.blocks):
            runs = []
            for off in sorted(self.touched[slot]):
                if runs and off - runs[-1][1] <= gap:
                    runs[-1][1] = max(runs[-1][1], off + 4)
                else:
                    runs.append([off, off + 4])
            for lo, hi in runs:
                c.set(ctx.char(slot) + lo, bytes(self.blocks[slot][lo - C_BLOCK0:hi - C_BLOCK0]))


def xchar(ctx):
    return (ctx.g('g_status') + GS_XCHAR).deref()


def set_occupied(ctx, c, occ):
    """fOccupied of the 8 XChar rows (the only XChar field these functions read): the
    whole array is filled with the majority byte, then the minority slots are set."""
    major = 1 if sum(occ) >= 4 else 0
    base = xchar(ctx)
    c.fill(base, 8 * XROW, major)
    for s in range(8):
        if occ[s] != major:
            c.set(base + s * XROW, bytes([occ[s]]))


def source_bytes(itype, ichar=-1, imon=-1, point=(0.0, 0.0, 0.0), refl=0, backfire=0, tail=None):
    b = bytearray(0x34)
    struct.pack_into('<III', b, 0, m32(itype), m32(ichar), m32(imon))
    struct.pack_into('<fff', b, 0xc, *point)
    if tail is not None:
        b[0x18:0x34] = tail
    b[0x1b] = refl
    b[0x1c] = backfire
    return bytes(b)


def slot_bytes(itype, ichar=-1, imon=-1, igroup=-1, point=(0.0, 0.0, 0.0)):
    b = bytearray(0x20)
    struct.pack_into('<IIII', b, 0, m32(itype), m32(ichar), m32(imon), m32(igroup))
    struct.pack_into('<fff', b, 0x10, *point)
    return bytes(b)


def rand_point(r, span=20000.0):
    return (r.uniform(-span, span), r.uniform(-span, span), r.uniform(-span, span))


def effect_slots_blob(r, n, special=None):
    """n W8EffectSlot records (0x11 each): active, effect_id, amount, percent, duration."""
    b = bytearray(n * 0x11)
    for k in range(n):
        if r.random() < 0.4:
            struct.pack_into('<BiiII', b, k * 0x11, 1, r.randrange(0, 40), r.randrange(0, 100),
                             r.randrange(0, 100), r.randrange(0, 200))
    if special:
        for k, (active, duration) in special.items():
            b[k * 0x11] = active
            struct.pack_into('<I', b, k * 0x11 + 0xd, m32(duration))
    return bytes(b)


def put_combat_state(ctx, c, present, effect=None, effect0=None, engaged=0):
    g = ctx.g('g_combat_state')
    if not present:
        c.set(g, U(0))
        return
    S1 = ctx.scratch(1)
    blob = bytearray(9 * 0x11 + 6 * 0x11)
    if effect:
        blob[0:9 * 0x11] = effect
    if effect0:
        blob[9 * 0x11:] = effect0
    c.set(S1 + CS_EFFECT, bytes(blob))
    if engaged:
        c.set(S1 + CS_ENGAGED, b'\x01')
    c.setp(g, S1)


def new_monster(r, loc, species=SPECIES_BASE, live=0.9):
    hpmax = r.choice([10, 55, 120, 400, 1000, 1, 0x7fffffff])
    alive = r.random() < live
    m = {
        'loc': loc, 'group': r.choice([0, 1, 2, 7, 100, r.randrange(1, 5000)]), 'species': species,
        'active': 1 if r.random() < 0.88 else 0, 'incombat': 1 if r.random() < 0.6 else 0,
        'disp': r.choice([1, 1, 1, 2, 2, 0]),
        'hpmax': hpmax, 'hp': r.choice([hpmax, max(hpmax - 1, 1), r.randrange(1, 60), 0x80000000]) if alive else 0,
        'stmax': r.choice([50, 200, 0]), 'st': 0, 'cond': {}, 'ench': {}, 'high': 0,
        'pos': (0.0, 0.0, 0.0), 'mrad': r.choice([0.0, 0.0, 50.0, 250.0]), 'altrad': r.choice([0.0, 500.0, 1000.0]),
        'height': r.choice([0.0, 300.0, 750.0]), 'summoned': 0, 'los': 0,
    }
    m['st'] = r.choice([m['stmax'], 0, m['stmax'] // 2])
    if r.random() < 0.08:
        m['cond'][18] = r.choice([1, 9999])
    if r.random() < 0.3:
        m['high'] = r.choice([0, 5, 12, 13, 14, 17, 18])
    return m


def monster_head(m):
    b = bytearray(M_HEAD)
    struct.pack_into('<III', b, 0, m32(m['loc']), m32(m['group']), m32(m['species']))
    b[0x14] = m['active']
    b[0x15] = m['incombat']
    b[0x16] = m['disp']
    struct.pack_into('<IIII', b, M_HPMAX, m32(m['hpmax']), m32(m['hp']), m32(m['stmax']), m32(m['st']))
    for k, v in m['cond'].items():
        struct.pack_into('<I', b, M_COND + 4 * k, m32(v))
    for k, v in m['ench'].items():
        struct.pack_into('<I', b, M_ENCH + 12 * k + 8, m32(v))
    struct.pack_into('<I', b, 0x107, m32(m['high']))
    return bytes(b).rstrip(b'\0') or b'\0'   # scratch is zeroed: trailing zeros need no write


def put_monsters(ctx, c, mons, with_p3d=False):
    S2, S3, S4 = ctx.scratch(2), ctx.scratch(3), ctx.scratch(4)
    X = ctx.g('gXStatus')
    c.set(S2 + MPL + 4, struct.pack('<ii', 16, len(mons)))
    c.setp(S2 + MPL, S2 + MPL_DATA)
    c.setp(X + XS_MONLIST, S2 + MPL)
    c.set(X + XS_UNBORN, U(0))
    if with_p3d and mons:
        if len(mons) > P3D_MAX:
            raise ValueError('too many fake monsters with a navigator: %d' % len(mons))
        blob = bytearray((len(mons) - 1) * P3D_STRIDE + (P3D_HI - P3D_LO))
        for i, m in enumerate(mons):
            o = i * P3D_STRIDE - P3D_LO
            struct.pack_into('<f', blob, o + 0x9c, m['mrad'])
            struct.pack_into('<fff', blob, o + 0x118, *m['pos'])
            struct.pack_into('<ff', blob, o + 0x18c, m['altrad'], m['height'])
        c.set(S4 + P3D_LO, bytes(blob))
    for i, m in enumerate(mons):
        info = S3 + i * MSTRIDE
        c.set(info, monster_head(m))
        c.setp(S2 + MPL_DATA + 4 * i, info)
        if with_p3d:
            c.setp(info + M_P3D, S4 + i * P3D_STRIDE)
        if m['summoned']:
            c.set(info + M_SUMMONED, U(m['summoned']))
        if m['los']:
            c.set(info + M_LOS, bytes(m['los']))


def put_records(ctx, c, recs):
    """recs: list of (kind, untargetable) for species SPECIES_BASE + k."""
    S5 = ctx.scratch(5)
    X = ctx.g('gXStatus')
    n = len(recs)
    kinds = bytearray((n - 1) * REC_STRIDE + 1)
    untargs = bytearray((n - 1) * REC_STRIDE + 1)
    for k, (kind, untarg) in enumerate(recs):
        kinds[k * REC_STRIDE] = kind
        untargs[k * REC_STRIDE] = untarg
    c.set(S5 + REC_BASE + 0xcb, bytes(kinds))
    if any(untargs):
        c.set(S5 + REC_BASE + 0x24a, bytes(untargs).rstrip(b'\0'))
    for k in range(len(recs)):
        c.setp(X + XS_RECCACHE + 4 * (SPECIES_BASE + k), S5 + REC_BASE + k * REC_STRIDE)


def put_groups(ctx, c, groups):
    """groups: list of dict(id, disp, leader, members)."""
    S2, S5 = ctx.scratch(2), ctx.scratch(5)
    X = ctx.g('gXStatus')
    n = len(groups)
    c.set(X + XS_ENCLIST, U(0))
    c.setp(X + XS_GRPLIST, S2 + GPL)
    c.set(S2 + GPL + 4, struct.pack('<ii', 8, n))
    c.setp(S2 + GPL, S2 + GPL_DATA)
    if not n:
        return
    gb = bytearray((n - 1) * G_STRIDE + G_LEADER + 4)
    hdr = bytearray(n * 0x10)
    data = bytearray(n * 0x40)
    for g, G in enumerate(groups):
        struct.pack_into('<i', gb, g * G_STRIDE + G_ID, G['id'])
        gb[g * G_STRIDE + G_DISP] = G['disp']
        struct.pack_into('<i', gb, g * G_STRIDE + G_LEADER, G['leader'])
        struct.pack_into('<ii', hdr, g * 0x10 + 4, 16, len(G['members']))
        for j, mid in enumerate(G['members']):
            struct.pack_into('<i', data, g * 0x40 + 4 * j, mid)
    c.set(S5, bytes(gb))
    c.set(S2 + ILS, bytes(hdr).rstrip(b'\0'))
    c.set(S2 + IL_DATA, bytes(data).rstrip(b'\0') or b'\0')
    for g in range(n):
        c.setp(S2 + ILS + g * 0x10, S2 + IL_DATA + g * 0x40)
        c.setp(S5 + g * G_STRIDE + G_MONSTERS, S2 + ILS + g * 0x10)
        c.setp(S2 + GPL_DATA + 4 * g, S5 + g * G_STRIDE)


def put_startup(ctx, c, pos, radius, altrad):
    S4 = ctx.scratch(4)
    c.set(S4 + NAV + 0x84, F(radius))           # W8Navigator::radius
    c.set(S4 + NAV + 0x100, struct.pack('<fff', *pos))  # movement.position
    c.set(S4 + NAV + 0x174, F(altrad))          # movement.alternate_radius
    c.setp(ctx.g('g_startup_world'), S4 + NAV)


def distinct_ids(r, n):
    pool = set()
    while len(pool) < n:
        pool.add(r.choice([r.randrange(1, 3000), r.randrange(3000, 60000), 0x7ffffff0 + r.randrange(0, 15),
                           -2 - r.randrange(0, 50)]))
    ids = list(pool)
    r.shuffle(ids)
    return ids


def party_participation(r, pe, p_hp=0.25, p_high=0.3, p_turncoat=0.0):
    for s in range(8):
        if r.random() < p_hp:
            pe.put(s, C_HP, r.choice([0, 0, 1, 37, 0x80000000]))
        if r.random() < p_high:
            pe.put(s, C_HIGH, r.choice([0, 3, 12, 13, 16, 17, 18, 19, 0x80000000, 0xffffffff]))
        if p_turncoat and r.random() < p_turncoat:
            pe.put(s, C_COND + 4 * 13, r.choice([1, 9999, 0x80000000]))


# --- SpellAffectedTarget ----------------------------------------------------------------

SA_GROUPS = [
    ('being', [20, 26, 32, 40], 40),
    ('cslot', [2, 53, 59, 62], 40),
    ('ench', [19, 21, 27, 54, 61, 65], 60),
    ('haste', [56], 30),
    ('heal', [6], 22),
    ('healall', [68], 28),
    ('stamina', [13], 22),
    ('restall', [44], 24),
    ('resto', [100], 26),
    ('cure', [34, 35, 51, 74, 120, 88, 16], 48),
    ('purify', [72], 14),
    ('sonic', [30, 38], 18),
    ('cool', [8, 17, 33, 45, 64, 73, 75], 24),
    ('ident', [23], 10),
    ('curse', [58], 30),
    ('default', [0, 1, 3, 4, 5, 9, 10, 25, 36, 60, 99, 101, 114, 117, 118, 119, 121, 130, 131, 149], 14),
]
CURE_CONDS = {34: [16], 35: [7], 51: [2], 74: [11, 13], 120: [1], 88: [18], 16: [3, 4, 6, 15, 12]}


def sa_duration(spell, power):
    d = m32(SPELL_DUR[spell] * power + SPELL_DPL[spell])
    if d != 9999:
        d = m32(d + 1)
    return d


def pick_power(r, spell):
    dur, dpl = SPELL_DUR[spell], SPELL_DPL[spell]
    cands = list(range(1, 8)) * 3 + [0, 8, 9, 100, 0x7fffffff, 0x80000000, 0xffffffff]
    if dur:
        if (9999 - dpl) % dur == 0:
            cands += [(9999 - dpl) // dur] * 3
        if (0xffffffff - dpl) % dur == 0:
            cands += [(0xffffffff - dpl) // dur] * 2
    return r.choice(cands)


def pick_turns(r, d):
    cands = [0, 1, 2, 3, d // 4, d // 4 + 1, max(d // 4 - 1, 0), (d + 3) // 4, d, d + 1, 9999,
             0x7fffffff, 0x80000000, 0xffffffff, 16777217, 33554431,
             r.randrange(0, 50), r.randrange(0, 5000)]
    return m32(r.choice(cands))


def gen_affected(ctx):
    fn = ctx.fn(0x004F9AE0)  # bool SpellAffectedTarget(W8Character*, int, W8CombatSlot*, unsigned)
    X = ctx.g('gXStatus')
    GS = ctx.g('g_status')
    T = ctx.g('guiCurrentTime')
    S0 = ctx.scratch(0)
    for group, spells, count in SA_GROUPS:
        for i in range(ctx.n(count)):
            r = ctx.rng('affected', group, i)
            spell = r.choice(spells)
            c = ctx.case('affected.%s.%d' % (group, i), fn, conv='c', ret='b')
            party = ctx.set_party(c, r)
            pe = PartyEdit(party)
            occ = [1 if r.random() < 0.8 else 0 for _ in range(8)]
            set_occupied(ctx, c, occ)
            power = pick_power(r, spell)
            d = sa_duration(spell, power)
            needs_fight = group in ('being', 'cslot', 'ench', 'haste', 'stamina', 'restall')
            combat = 1 if r.random() < (0.75 if needs_fight else 0.4) else 0
            hostile = r.choice([0, 1, 1, 2, 5, 0x80000000, 0xffffffff]) if r.random() < (
                0.9 if needs_fight else 0.7) else 0
            cs_present = r.random() < 0.6
            if group in ('cslot', 'ench', 'haste') and combat and hostile:
                cs_present = True
            if group == 'cslot' and combat and hostile:
                cs_present = True
            c.set(X + XS_COMBAT, bytes([combat]))
            c.set(X + XS_HOSTILE, U(hostile))

            # combat state (effect_slots0 durations for Bless & co, effect_slots for Purify Air)
            eff = effect0 = None
            if group == 'cslot':
                effect0 = effect_slots_blob(r, 6, {CSLOT_IDX[spell]: (r.choice([0, 1]), pick_turns(r, d))})
            elif group == 'purify':
                eff = effect_slots_blob(r, 9)
                if r.random() < 0.5:
                    eff = bytes(9 * 0x11)
            else:
                effect0 = effect_slots_blob(r, 6)
                eff = effect_slots_blob(r, 9)
            put_combat_state(ctx, c, cs_present, eff, effect0)

            # party effect slots (Enchanted Blade & co in combat)
            special = {BEING_IDX[spell]: (r.choice([0, 1]), pick_turns(r, d))} if group == 'being' else None
            c.set(GS + GS_EFFECT, effect_slots_blob(r, 12, special))

            # cooldown clocks against a fixed current time
            now = r.choice([r.randrange(1000, 10 ** 8), r.randrange(10 ** 8, 0x7fffffff), 0,
                            0xffffffff - r.randrange(0, 200000), 0x7fffffff])
            clocks = []
            for k in range(14):
                clocks.append(m32(r.choice([0, 0, now - 1, now, now + 1, now + r.randrange(1, 200000),
                                            now + 180000, 0xffffffff, r.randrange(0, 1 << 32)])))
            c.set(T, U(now))
            c.set(X + XS_CLOCKS, struct.pack('<14I', *clocks))

            # aim: character, party or a fake monster
            char_kind = 9 if spell == 88 else 1
            mons = []
            ids = []
            aim_kind = char_kind
            aim_slot = r.randrange(8)
            aim_mon = -1
            want_monster = group in ('ench', 'heal', 'stamina', 'resto', 'cure', 'curse') and r.random() < 0.4
            if group == 'haste':
                aim_kind = 2 if r.random() < 0.75 else r.choice([1, 3, 0])
            elif want_monster:
                nm = r.randrange(1, 4)
                ids = distinct_ids(r, nm)
                for k in range(nm):
                    mons.append(new_monster(r, ids[k]))
                aim_kind = r.choice([3, 3, 3, 2, 4, 0, 5] + ([1] if char_kind == 9 else [9]))
                aim_mon = r.choice(ids)
            elif group in ('purify', 'sonic', 'cool', 'being', 'cslot', 'default', 'healall',
                           'restall', 'ident'):
                aim_kind = r.choice([1, 2, 3, 0, 9])
            aim_target = None
            for m in mons:
                if m['loc'] == aim_mon:
                    aim_target = m

            # the aimed / affected characters and monsters
            if group == 'ench':
                slot = ENCH_SLOT[spell]
                for s in range(8):
                    if r.random() < 0.5:
                        pe.put(s, C_ENCH + 12 * slot + 8, pick_turns(r, d))
                if aim_target is not None:
                    aim_target['ench'][slot] = pick_turns(r, d)
                    if r.random() < 0.5:
                        aim_target['ench'][r.randrange(8)] = pick_turns(r, d)
            elif group == 'haste':
                for s in range(8):
                    pe.put(s, C_ENCH + 12 * 5 + 8, pick_turns(r, d))
                    pe.put(s, C_ENCH + 12 * 3 + 8, pick_turns(r, d))
            elif group in ('heal', 'healall', 'stamina', 'restall', 'resto'):
                for s in range(8):
                    if group in ('healall', 'restall') or s == aim_slot or r.random() < 0.3:
                        hpmax = r.choice([pe.get(s, C_HPMAX), 1, 0, 0x7fffffff, 0xffffffff, 0x80000000])
                        hp = r.choice([hpmax, hpmax, m32(hpmax - 1), 0, m32(hpmax + 1), 1])
                        stmax = r.choice([pe.get(s, C_STMAX), 0, 0xffffffff, 0x80000000, 100])
                        st = r.choice([stmax, stmax, m32(stmax - 1), 0, m32(stmax + 1), 0xffffffff])
                        pe.put(s, C_HPMAX, hpmax)
                        pe.put(s, C_HP, hp)
                        pe.put(s, C_STMAX, stmax)
                        pe.put(s, C_ST, st)
                    if group in ('healall', 'restall') and r.random() < 0.5:
                        pe.put(s, C_HIGH, r.choice([0, 5, 12, 17, 18, 19, 0x80000000, 0xffffffff]))
                    if group == 'resto' and s == aim_slot:
                        for k in range(20):
                            pe.put(s, C_COND + 4 * k, 0)
                        if r.random() < 0.6:
                            pe.put(s, C_COND + 4 * r.choice([0, 1, 2, 9, 16, 17, 18, 19]),
                                   r.choice([1, 9999, 0x80000000]))
                if aim_target is not None:
                    hpmax = aim_target['hpmax']
                    aim_target['hp'] = r.choice([hpmax, m32(hpmax - 1), 0, m32(hpmax + 1)])
                    aim_target['stmax'] = r.choice([0, 100, 0xffffffff])
                    aim_target['st'] = r.choice([aim_target['stmax'], 0, m32(aim_target['stmax'] - 1),
                                                 m32(aim_target['stmax'] + 1)])
                    if group == 'resto' and r.random() < 0.6:
                        aim_target['cond'][r.choice([0, 1, 2, 9, 16, 17, 18, 19])] = r.choice([1, 9999])
            elif group in ('cure', 'curse'):
                conds = CURE_CONDS.get(spell, [9])
                s = aim_slot
                for k in list(conds) + [r.randrange(20)]:
                    pe.put(s, C_COND + 4 * k, r.choice([0, 0, 1, 9999, 0x80000000]))
                if aim_target is not None:
                    for k in list(conds) + [r.randrange(20)]:
                        aim_target['cond'][k] = r.choice([0, 0, 1, 9999])
                if group == 'curse' and r.random() < 0.7:
                    # binds-on-equip gear in the aimed character's equipment
                    blob = party[aim_slot][1]
                    eq = bytearray(blob[C_EQUIP:C_EQUIP + 12 * 12])
                    for k in range(12):
                        if r.random() < 0.3:
                            struct.pack_into('<i', eq, k * 12, r.choice(BOE_ITEMS + [-1, 0, 1, 2]))
                            eq[k * 12 + 10] = r.choice([0, 0, 1])
                    c.set(ctx.char(aim_slot) + C_EQUIP, bytes(eq))
            pe.flush(ctx, c)

            aim = slot_bytes(aim_kind, aim_slot, aim_mon, r.choice([-1, 0, 3]), rand_point(r))
            c.set(S0 + AIM, aim)
            if group == 'ident' or r.random() < 0.1:
                item = bytearray(0xc)
                struct.pack_into('<i', item, 0, r.choice(SPELL_ITEMS))
                item[6] = r.choice([0, 0, 1, 2, 0xff])
                c.set(S0 + ITEM, bytes(item))
                c.setp(S0 + AIM + 0x1c, S0 + ITEM)
            if mons:
                put_monsters(ctx, c, mons)

            c.cap(X + XS_CLOCKS, 0x38, 'cooldown_clocks')
            c.arg(ctx.char(aim_slot))
            c.arg(spell)
            c.arg(S0 + AIM)
            c.arg(power)
            c.note(spell=spell, group=group, power=power, duration=d, combat=combat, hostile=hostile,
                   combat_state=int(cs_present), aim_kind=aim_kind, aim_slot=aim_slot, now=now)
            check_ops(c)


# --- RedirectBackfiredSpellTarget / PrepareSpellTarget / PickBackfireTarget -----------------

def target_world(ctx, c, r, nmon, ngroups, with_p3d=False):
    """Fake monsters (+ groups led by them). Returns (monsters, ids, groups)."""
    ids = distinct_ids(r, nmon) if nmon else []
    mons = [new_monster(r, ids[k], SPECIES_BASE) for k in range(nmon)]
    for m in mons:
        m['pos'] = rand_point(r)
    groups = []
    if ngroups and mons:
        gids = distinct_ids(r, ngroups)
        for g in range(ngroups):
            members = r.sample(ids, r.randrange(1, len(ids) + 1))
            groups.append({'id': gids[g], 'disp': r.choice([0, 1, 2]), 'leader': r.choice(members),
                           'members': members})
    if mons:
        put_monsters(ctx, c, mons, with_p3d)
    if groups:
        put_groups(ctx, c, groups)
    return mons, ids, groups


def random_tail(r):
    return bytes(r.choice([0, 0, 1, 0xff, r.randrange(256)]) for _ in range(0x1c))


def gen_redirect_like(ctx, kind):
    """kind 'redirect' (0x004FE740) or 'prepare' (0x004FEA50)."""
    if kind == 'redirect':
        fn = ctx.fn(0x004FE740)  # void RedirectBackfiredSpellTarget(W8TargetSource*, W8CombatSlot*)
        count = 260
    else:
        fn = ctx.fn(0x004FEA50)  # void PrepareSpellTarget(int, W8TargetSource*, W8CombatSlot*)
        count = 260
    S0 = ctx.scratch(0)
    prep_groups = [
        ('t1', spells_with_tt(1), 20), ('t3', spells_with_tt(3) + [3, 41, 3, 41], 20),
        ('t4', spells_with_tt(4), 14), ('t6', spells_with_tt(6), 26), ('t2', spells_with_tt(2), 5),
        ('t7', spells_with_tt(7), 5), ('t10', spells_with_tt(10), 3), ('bad', spells_with_tt(0, 8, 9), 7),
    ]
    total_w = sum(w for _, _, w in prep_groups)
    for i in range(ctx.n(count)):
        r = ctx.rng(kind, i)
        spell = None
        tt = None
        if kind == 'prepare':
            x = r.uniform(0, total_w)
            for name, spells, w in prep_groups:
                if x < w:
                    spell = r.choice(spells)
                    break
                x -= w
            if spell is None:
                spell = r.choice(prep_groups[0][1])
            tt = SPELL_TT[spell]
        c = ctx.case('%s.%d' % (kind, i), fn, conv='c', ret='v')
        party = ctx.set_party(c, r)
        pe = PartyEdit(party)
        occ = [1 if r.random() < 0.75 else 0 for _ in range(8)]
        if r.random() < 0.05:
            occ = [0] * 8
        set_occupied(ctx, c, occ)
        party_participation(r, pe, 0.3, 0.35)
        if r.random() < 0.06:
            for s in range(8):
                pe.put(s, C_HP, 0)
        pe.flush(ctx, c)

        nmon = r.randrange(1, 6)
        ngroups = r.randrange(0, 3)
        # only the point type (6) reads the monster navigator in PrepareSpellTarget
        mons, ids, groups = target_world(ctx, c, r, nmon, ngroups, with_p3d=(tt == 6))
        if kind == 'prepare':
            put_startup(ctx, c, rand_point(r), r.choice([500.0, 0.0, 120.0]), r.choice([500.0, 0.0]))

        # source
        sk = r.choice([1, 1, 1, 2, 2, 2, 3, 3, 0, 4, 0xffffffff])
        ichar = r.choice([r.randrange(8), r.randrange(8), r.randrange(8), -1, 8, 1000])
        imon = r.choice(ids) if (sk == 2 or r.random() < 0.5) else r.choice([-1, 12345])
        if sk == 2 and ichar not in (-1,) and r.random() < 0.5:
            ichar = -1
        backfire = 1 if r.random() < 0.1 else 0
        refl = 1 if r.random() < 0.3 else 0
        src = source_bytes(sk, ichar, imon, rand_point(r), refl, backfire, random_tail(r))

        # target
        tk = r.choice([1, 1, 9, 2, 2, 2, 3, 3, 4, 4, 0, 5, 6, 7, 8, 10, 0xffffffff])
        if tk == 4 and not groups:
            tk = 2
        tchar = r.choice([r.randrange(8), r.randrange(8), -1, 77])
        tmon = r.choice(ids)
        tgroup = r.choice(groups)['id'] if groups else r.choice([-1, 5])
        tgt = slot_bytes(tk, tchar, tmon, tgroup, rand_point(r))
        tgt = tgt[:0x1c] + bytes(4)
        c.set(S0 + SRC, src)
        c.set(S0 + AIM, tgt)
        c.cap(S0 + SRC, 0x34, 'source')
        c.cap(S0 + AIM, 0x20, 'target')
        if kind == 'prepare':
            c.arg(spell)
        c.arg(S0 + SRC)
        c.arg(S0 + AIM)
        c.note(spell=spell, target_type=tt, source_kind=m32(sk), source_char=ichar, source_mon=imon,
               backfire=backfire, target_kind=m32(tk), target_char=tchar, occupied=''.join(map(str, occ)),
               monsters=len(mons), groups=len(groups))
        check_ops(c)


def gen_pick(ctx):
    fn = ctx.fn(0x004FEDC0)  # bool PickBackfireTarget(int, W8TargetSource*, W8CombatSlot*)
    S0 = ctx.scratch(0)
    group_spells = spells_with_tt(4)
    for i in range(ctx.n(260)):
        r = ctx.rng('pick', i)
        spell = r.choice(group_spells) if r.random() < 0.4 else r.randrange(150)
        c = ctx.case('pick.%d' % i, fn, conv='c', ret='b')
        ctx.set_party(c, r)
        occ = [1 if r.random() < 0.7 else 0 for _ in range(8)]
        if r.random() < 0.1:
            occ = [0] * 8
        set_occupied(ctx, c, occ)
        nmon = r.choice([0, 0, 1, 2, 3, 4, 5, 6, 8])
        ids = distinct_ids(r, nmon) if nmon else []
        mons = []
        for k in range(nmon):
            m = new_monster(r, ids[k])
            m['incombat'] = 1 if r.random() < 0.7 else 0
            mons.append(m)
        if mons:
            put_monsters(ctx, c, mons)
        else:
            X = ctx.g('gXStatus')
            if r.random() < 0.5:
                c.set(X + XS_MONLIST, U(0))
            else:
                put_monsters(ctx, c, [])
        sk = r.choice([1, 1, 1, 2, 2, 3, 0])
        ichar = r.choice([r.randrange(8), r.randrange(8), 9, -5]) if sk == 1 else r.choice([-1, r.randrange(8)])
        if sk == 1 and r.random() < 0.03:
            ichar = -1
        imon = r.choice(ids) if (ids and r.random() < 0.7) else r.choice([-1, 4242])
        src = source_bytes(sk, ichar, imon, rand_point(r), r.choice([0, 1]), r.choice([0, 0, 1]),
                           random_tail(r))
        tgt = bytes(r.randrange(256) for _ in range(0x1c)) + bytes(4)
        c.set(S0 + SRC, src)
        c.set(S0 + AIM, tgt)
        c.cap(S0 + AIM, 0x20, 'target')
        c.cap(S0 + SRC, 0x34, 'source')
        c.arg(spell)
        c.arg(S0 + SRC)
        c.arg(S0 + AIM)
        c.note(spell=spell, target_type=SPELL_TT[spell], source_kind=sk, source_char=ichar,
               occupied=''.join(map(str, occ)), monsters=nmon)
        check_ops(c)


# --- PopulateSpellTargetMarkers ---------------------------------------------------------

def place(r, centre, radius, inside):
    th = r.uniform(0, 2 * math.pi)
    ph = r.uniform(-0.6, 0.6)
    if inside:
        dist = r.uniform(0, 0.4) * radius
    else:
        dist = 2 * radius + 2000 + r.uniform(0, 5000)
    return (centre[0] + dist * math.cos(th) * math.cos(ph), centre[1] + dist * math.sin(ph),
            centre[2] + dist * math.sin(th) * math.cos(ph))


def far_from(r, p0, radius):
    return place(r, p0, radius, False)


def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


POP_SCEN = [('single', 90), ('group', 50), ('party', 60), ('radius', 60), ('all', 45), ('none', 25)]


def gen_populate(ctx):
    fn = ctx.fn(0x004FD030)  # void PopulateSpellTargetMarkers(int, int, W8TargetSource*, W8CombatSlot*,
    #                          W8GrowableVector<int>*, W8GrowableVector<int>*, int)
    S0 = ctx.scratch(0)
    scen_spells = {
        'single': spells_with_tt(0, 1, 3),
        'group': spells_with_tt(4),
        'party': spells_with_tt(2),
        'radius': spells_with_tt(6),
        'all': spells_with_tt(7),
        'none': spells_with_tt(8, 9, 10),
    }
    for scen, count in POP_SCEN:
        for i in range(ctx.n(count)):
            r = ctx.rng('populate', scen, i)
            spell = r.choice(scen_spells[scen])
            if scen == 'radius' and r.random() < 0.3:
                spell = 22
            if scen == 'all' and r.random() < 0.45:
                spell = r.choice([77, 129])
            power = r.choice(list(range(1, 8)) * 3 + [0, 8, -1, 0x7fffffff])
            c = ctx.case('populate.%s.%d' % (scen, i), fn, conv='c', ret='v')
            party = ctx.set_party(c, r)
            pe = PartyEdit(party)
            occ = [1 if r.random() < 0.8 else 0 for _ in range(8)]
            set_occupied(ctx, c, occ)
            if scen in ('group', 'party'):
                party_participation(r, pe, 0.2, 0.3, 0.3)
                pe.flush(ctx, c, gap=0x200)
            put_combat_state(ctx, c, False)

            # fake world
            p0 = rand_point(r)
            nav_radius = r.choice([500.0, 500.0, 0.0, 120.0])
            nav_alt = r.choice([500.0, 0.0, 250.0])
            put_startup(ctx, c, p0, nav_radius, nav_alt)
            nmon = r.randrange(1, 7) if scen != 'none' else r.randrange(0, 4)
            nrec = r.randrange(1, 4)
            ids = distinct_ids(r, nmon) if nmon else []
            mons = [new_monster(r, ids[k], SPECIES_BASE + r.randrange(nrec)) for k in range(nmon)]
            for m in mons:
                if spell == 77:
                    m['summoned'] = r.choice([0, 0, 1, 2])
            recs = [(r.choice([0x14, 0x15, 0x1c, 0x14, r.randrange(0, 40)]), 1 if r.random() < 0.12 else 0)
                    for _ in range(nrec)]

            # source
            if scen in ('single', 'group', 'none'):
                sk = r.choice(['ind', 'ind', 'char', 'mon'] if mons else ['ind', 'char'])
            elif scen in ('party', 'radius'):
                sk = r.choice(['char', 'char', 'mon', 'ind'] if mons else ['char', 'ind'])
            else:
                sk = r.choice(['ind', 'ind', 'mon'] if mons else ['ind'])
            flags = r.choice([(1, 0), (0, 1), (1, 1)])
            m0 = None
            if sk == 'char':
                itype, ichar, imon = 1, r.randrange(8), r.choice([-1, -1, 77])
                backfire, refl = flags
            elif sk == 'mon':
                m0 = r.choice(mons)
                itype, ichar, imon = 2, r.choice([-1, -1, r.randrange(8)]), m0['loc']
                backfire, refl = flags
                if scen in ('all',):
                    m0['disp'] = r.choice([1, 2, 0])
            else:
                itype = r.choice([3, 3, 3, 0])
                ichar = r.choice([-1, -1, r.randrange(8)])
                imon = -1
                if mons and r.random() < 0.2:
                    imon = r.choice(ids)
                backfire, refl = (flags if r.random() < 0.6 else (0, 0))
            spoint = rand_point(r)

            base = f32(f32(SPELL_RAD[spell] * 1.0) * WORLD_SCALE)
            tpoint = rand_point(r)
            inside = r.random() < 0.6
            if sk == 'mon':
                inside = True
            centre = None
            radius = 0.0
            if scen == 'party':
                if sk == 'char':
                    centre = p0
                    radius = base + (nav_radius if base > 0 else 0.0)
                elif sk == 'mon':
                    m0['pos'] = rand_point(r)
                    centre = m0['pos']
                    radius = base + m0['mrad']
                    if r.random() < 0.6:
                        m0['los'] = [r.choice([0, 1]) for _ in range(4)]
                        m0['los'][2] = r.choice([0, 1, 1])
                else:
                    spoint = far_from(r, p0, base + 1000)
                    centre = spoint
                    radius = base
            elif scen == 'radius':
                tpoint = far_from(r, p0, base + 1000)
                tpoint = (tpoint[0], tpoint[1] + 1000.0, tpoint[2])
                centre = (tpoint[0], tpoint[1] - 1000.0, tpoint[2])
                radius = base
            elif scen == 'all':
                steps = RANGE_STEPS[SPELL_RNG[spell]] * WORLD_SCALE
                if sk == 'mon':
                    m0['pos'] = far_from(r, p0, steps + m0['altrad'] + 1000)
                    centre = m0['pos']
                    radius = steps + m0['altrad']
                else:
                    spoint = far_from(r, p0, steps + 1000)
                    centre = spoint
                    radius = steps
            if centre is not None:
                for m in mons:
                    if m is m0 and scen in ('party', 'all'):
                        continue
                    m['pos'] = place(r, centre, radius, inside)
            else:
                for m in mons:
                    m['pos'] = rand_point(r)
            if centre is not None:
                hl = r.choice([1, 1, 0x101, 0x7f, 0xff, 0xffffffff]) if inside else r.choice([0, 0, 0x100, 0x10000])
            else:
                hl = r.choice([0, 1, 0x100])

            # target
            groups = []
            if scen == 'single':
                tk = r.choice([1, 1, 1, 3, 3, 3, 9, 9, 0, 2, 4, 5, 6, 7, 8, 10])
            elif scen == 'group':
                tk = r.choice([4, 4, 4, 4, 2, 2, 1, 3, 0])
                ng = r.randrange(1, 4)
                gids = distinct_ids(r, ng)
                for g in range(ng):
                    members = r.sample(ids, r.randrange(1, len(ids) + 1))
                    groups.append({'id': gids[g], 'disp': r.choice([0, 1, 2]), 'leader': members[0],
                                   'members': members})
            else:
                tk = r.choice([0, 1, 2, 3, 4, 6, 9])
            tchar = r.choice([r.randrange(8), r.randrange(8), -1, 0x55, -100])
            tmon = r.choice(ids) if ids else -1
            if groups and r.random() < 0.85:
                tgroup = r.choice(groups)['id']
            else:
                tgroup = r.choice([-1, 31337])
            if tk == 3 and not ids:
                tk = 1

            c.set(S0 + SRC, source_bytes(itype, ichar, imon, spoint, refl, backfire))
            c.set(S0 + AIM, slot_bytes(tk, tchar, tmon, tgroup, tpoint))
            # marker vectors with room for 64 entries (no reallocation), partly pre-filled
            pre_m = [r.choice(ids) for _ in range(r.choice([0, 0, 1, 2, 3]))] if ids else []
            pre_p = [r.choice([r.randrange(8), 99, -1]) for _ in range(r.choice([0, 0, 1, 2]))]
            hdr = bytearray(0x20)
            struct.pack_into('<ii', hdr, 0x04, len(pre_m), 64)
            struct.pack_into('<ii', hdr, 0x14, len(pre_p), 64)
            c.set(S0 + MVEC, bytes(hdr))
            c.setp(S0 + MVEC + 0xc, S0 + MDATA)
            c.setp(S0 + PVEC + 0xc, S0 + PDATA)
            if pre_m:
                c.set(S0 + MDATA, struct.pack('<%di' % len(pre_m), *pre_m))
            if pre_p:
                c.set(S0 + PDATA, struct.pack('<%di' % len(pre_p), *pre_p))

            put_records(ctx, c, recs)
            put_monsters(ctx, c, mons, with_p3d=True)
            if groups:
                put_groups(ctx, c, groups)

            c.cap(S0 + MVEC, 0x20, 'vectors', ignore=[0xc, 0x1c])
            c.cap(S0 + MDATA, 0x100, 'monster_markers')
            c.cap(S0 + PDATA, 0x100, 'party_markers')
            c.cap(S0 + AIM, 0x20, 'target')
            c.cap(S0 + SRC, 0x34, 'source')
            c.arg(spell)
            c.arg(power)
            c.arg(S0 + SRC)
            c.arg(S0 + AIM)
            c.arg(S0 + MVEC)
            c.arg(S0 + PVEC)
            c.arg(hl)
            c.note(spell=spell, target_type=SPELL_TT[spell], source=sk, flags='%d%d' % (backfire, refl),
                   target_kind=tk, monsters=nmon, groups=len(groups), inside=int(inside), highlighting=hl,
                   occupied=''.join(map(str, occ)))
            check_ops(c)


# --- TrackItemSpellSource ---------------------------------------------------------------

def gen_track(ctx):
    fn = ctx.fn(0x00501D20)  # void TrackItemSpellSource(W8Character*, int)
    GS = ctx.g('g_status')
    lo = GS_ITEMUSE - 0x10
    length = 0x10 + 0x100 * 0x10
    for i in range(ctx.n(260)):
        r = ctx.rng('track', i)
        c = ctx.case('track.%d' % i, fn, conv='c', ret='v')
        party = ctx.set_party(c, r)
        slot = r.randrange(8)
        blob = party[slot][1]
        items = bytearray(blob[C_EQUIP:C_ITEMS1])
        pr = r.choice([0.0, 0.3, 0.6, 1.0])
        offsets = [k * 12 for k in range(12)] + [C_PACK - C_EQUIP + k * 12 for k in range(8)]
        for o in offsets:
            if r.random() < pr:
                x = r.random()
                if x < 0.45:
                    item = r.choice(SPELL_ITEMS)
                elif x < 0.7:
                    item = r.choice(CHARGE_ITEMS)
                elif x < 0.85:
                    item = r.randrange(ITEM_COUNT)
                else:
                    item = -1
                struct.pack_into('<i', items, o, item)
                items[o + 4] = r.choice([0, 1, 5])
                items[o + 5] = r.choice([0, 0, 1, 2, 9, 255])
                items[o + 6] = r.choice([0, 1])
        c.set(ctx.char(slot) + C_EQUIP, bytes(items))
        fillb = r.choice([0, 0, 0, 0xff, 0x7f, 0x80])
        c.fill(GS + lo, length, fillb)
        spell = r.choice([r.randrange(150)] * 8 + [r.randrange(150, 200), 0, 149, 199, 255, -1])
        c.cap(GS + lo, length, 'item_spell_usage')
        c.arg(ctx.char(slot))
        c.arg(spell)
        c.note(slot=slot, char=party[slot][2], spell=spell, fill=fillb, replace_prob=pr)
        check_ops(c)


def cases(ctx):
    gen_affected(ctx)
    gen_redirect_like(ctx, 'redirect')
    gen_redirect_like(ctx, 'prepare')
    gen_pick(ctx)
    gen_populate(ctx)
    gen_track(ctx)
