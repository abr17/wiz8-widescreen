"""Combat Attack.cpp, lines 1-2200 (decomp/src/wiz8/local_code/Combat Attack.cpp).

Tested (retail address, name, cases at --scale 1):
  0x00546a70 GetCharacterHandDamageDice       300
  0x00546b10 GetCharacterHandDamageBonus      150
  0x00543260 ClearAttackBlock                  10
  0x005430c0 NormalizeMonsterCycle             56  (every value -3..40 plus edge dwords)
  0x00542db0 ChooseAttackMode                 300
  0x00545b80 CanCharacterAttack               200
  0x00545bd0 CanMonsterProtect                200
  0x005459b0 ApplyDamageReduction             300
  0x0053d4b0 RateMonsterAttack                300
  0x0053d450 RateMonsterBestAttack            200
  0x0053d2a0 CanHandReachTarget               250
  0x0053d310 CanAnyHandReachTarget            200
  0x0053d7f0 GetHandAttackValue               200
  0x00545950 ApplyCharacterDamageReduction    300
  0x005458a0 CanCharacterBerserk              250
  0x00545c20 CharacterHasAttackOn             250
  0x00545cf0 CanMonsterProtectCombatant       250
  0x00545b20 CanMonsterProtectTarget          200
  0x00545e50 ResolveGuardianInterception      200
  0x00545aa0 CanCharacterAttackItsTarget      200
  0x0053d390 ChooseCharacterAttackHand        250
  0x0053d680 PrepareCharacterAttacks          250
  0x005468d0 GetTargetArmorClassModifier      300
  0x00542ca0 CharChooseHandAttackMode         250
  0x00546b40 SpellTargetString                250
  0x00542ee0 GetTargetArmorClass              250
  0x00542fc0 TargetArmorClassAtLocation       300
  0x00543110 BlockedForSpecialReason          250
  0x00545a00 CapAttackDamageByTargetHealth    250
  0x0053d590 CharacterNoticesAttacker         250
  total 6916

Partial coverage (deterministic paths only):
  RateMonsterAttack / RateMonsterBestAttack - MonsterAttackReachesAnyone always answers "nobody"
    (no LOS), so the ratings seen are 1 (not usable / data error) and 3 (out of reach).
  CharacterHasAttackOn / CanCharacterAttackItsTarget - monster targets only where they fail
    before CanPartyMemberAimAtMonster; character targets and odd target kinds fully.
  CanMonsterProtectCombatant / CanMonsterProtectTarget - every early exit, the self-target branch
    of MonsterAttackReachesMonster (level/hp/out-of-formation tail); never a true reach by distance.
  ResolveGuardianInterception - party guardians on a character target (scores, chance clamp,
    roll, target takeover, fatigue); monster bodyguards are walked but never reach (no LOS).
    The interposer branch posts one text-box notice (UI side effect, no window).
  BlockedForSpecialReason - a block plays the material impact sound (verbose notices off);
    the sound handle/flag in the combat state are ignored in the capture.
  CharacterNoticesAttacker - only action states that do not reach CharacterCanSwitchTo
    (row latched with any pending action, or unlatched with action DEFEND).

Skipped:
  0x00542e10 AttackModeMod - static, inlined into its callers (not in Wiz8Runtime.map);
             its only callers in range (ResolveMissileHit, ContinueMonsterAttack) are skipped.
  0x00544d30 ResolveSpellMissileHit - plays the spell sound, damages world monsters/party
             through a live W8Missile; world side effects.
  0x00545090 ResolveMissileHit - notices + hit sounds + damage application on a live missile.
  0x0053ffe0 StartMonsterAttackCycle - starts an animation cycle on the world monster (p3D).
  0x0053fb00 ReportCharacterAttackResult - main effect is UI notices; frees report entries.
  0x00540170 ContinueMonsterAttack - whole swing resolution: camera, sounds, animations,
             damage, character events, AI repick.
  0x005412b0 ReportMonsterAttackResult - main effect is UI notices.
  0x0053fea0 StartMonsterAttack - announcement + animation start on a world monster.

How the world is controlled:
  * Party: corpus characters (setb) plus field-level set edits; XChar rows (heap, g_status+8)
    are written per slot (fOccupied .. target_in_combat), the formation is synthesized.
  * Monsters: every monster/record/group is built in scratch. gXStatus.plsMonsterList (and the
    group list where needed) is pointed at a scratch W8PList; records are wired through
    gXStatus.monster_record_cache[species] (species 990..999 and 548 = neutral species), so
    GetMonsterDataForInfo never loads anything. p3D stays NULL and every path that would reach
    world geometry (CanPartyMemberAimAtMonster, distance checks) is cut earlier: party sight
    record UNSEEN or LOS flags clear, mon-to-mon visibility rows UNSEEN/LOS clear, targets
    inactive/untargetable.
  * g_combat_state -> scratch 4, gXStatus.fCombatMode, g_settings.verbose_combat_messages,
    g_level_data->flags (fast movement bit) are set explicitly where read.
  * Item ids only from the corpus (equipped + backpack); weapon ids for the attack-mode walk only
    from hands the corpus has in play with a weapon (uiHolds 1), so ChooseAttackMode never gets a
    mask without one of the nine low bits (that would loop forever in both exes).
"""
import struct

from w8diff.api import Blob

M32 = 0xffffffff
MAX_OPS = 96

# ---- W8Character (layout.ps1 -Header wiz8/layouts/character.h) ----
CHAR = 0x1862
C_NAME = 0x05
C_PROF = 0x69
C_RACE = 0x71
C_GENDER = 0x75
C_ATTR = 0xe5
ATTR_STEP = 0x14
ATTR_EFF = 4
A_SPEED = 5
A_SENSES = 6
C_SKILL = 0x19d
SKILL_STEP = 0x26
SK_POINTS = 0x2
SK_BASE = 0xa
SK_PRACTICE = 0xe
SKILL_IRON_SKIN = 0x25
C_COND = 0xa01
COND_BLIND = 12
COND_TURNCOAT = 13
C_HC = 0xb01
C_HPMAX = 0xb0d
C_HP = 0xb11
C_STMAX = 0xb19
C_STAM = 0xb1d
C_ACTOT = 0xe85
C_ACCOMP = 0xe8d          # int[13]; SPEED = 1, SHIELD = 3
C_ACLOC = 0xec1           # int[5]
C_DR = 0xed9
C_EQUIP = 0xf5d
EQ_STEP = 0xc
C_HAND = 0x1149
HAND_STEP = 0x5b
H_HOLDS = 0x0
H_PLAY = 0x4
H_WSKILL = 0x5
H_SCORE = 0x11
H_ATTACKS = 0x15
H_DBONUS = 0x1d
H_HBONUS = 0x21
H_DPCT = 0x29
H_DICE = 0x2d
H_FLAGS = 0x31
C_FATIGUE = 0x169e
C_BONUS = 0x1770
C_DEEPF = 0x185b

# ---- W8GameplayModifierBlock ----
MOD_HIT = 0x1
MOD_DPCT = 0x3
MOD_ARMOR_FLAT = 0x4
MOD_MATCHUP = 0x5
MOD_DR = 0x6
MOD_OOF = 0x45
MOD_ACADJ = 0x4b

# ---- W8PartySlotRow (g_status.buffers.XChar, heap) ----
XROW = 0x106
X_PENDING = 0x1
X_MODES = 0x5
X_TARGET_OOC = 0x1d
X_ACTION = 0x3d
X_TARGET_IC = 0x4d
XROW_SET = 0x6d           # fOccupied .. end of target_in_combat
XROW_PTRS = (0x19, 0x39, 0x49, 0x69)

# ---- W8CombatState (scratch 4) ----
CS_SIZE = 0xa64
CS_ROWS = 0x18
CROW = 0xd4
R_DEAD = 0x34
R_SAVED = 0x38
R_HANDVAL = 0x40
R_CURHAND = 0x6c
R_SPOT = 0x90
R_INTERCEPT = 0xa0
CS_HIT_SOUND = 0x7bc
CS_HIT_SOUND_ACTIVE = 0x7c0
CS_TARGET_HIT = 0x8c5
CS_NEXT_PARTY_ACTION = 0x90c
CS_CUR_PARTY_ACTION = 0x910
CS_PARTY_ACTION_STATUS = 0x918
CS_UNAWARE = 0x9a4
CS_NATURAL = 0x9a5
CS_IGNORE = (0x7b8, CS_HIT_SOUND, CS_HIT_SOUND_ACTIVE, 0x8c0, CS_TARGET_HIT + 0x1c, 0xa4c)

# ---- W8MonsterInfo (scratch 1) ----
MI_SIZE = 0x425
M_LOC = 0x0
M_GROUP = 0x4
M_SPECIES = 0x8
M_P3D = 0xc
M_PCOMBAT = 0x10
M_ACTIVE = 0x14
M_INCOMBAT = 0x15
M_DISP = 0x16
M_HPMAX = 0x27
M_HP = 0x2b
M_COND = 0x57
M_HC = 0x107
M_MODS = 0x1db
M_FATIGUE = 0x242
M_ATTR = 0x247            # u8[5]: STR, INT, DEX, SPEED, SENSES
M_MOTIONLESS = 0x24e
M_VISLIST = 0x2b6
M_TARGET = 0x2ba
M_ACTION_KIND = 0x2e1
M_ACTION_DETAIL = 0x2e5
M_PVIS = 0x348            # W8VisibilityRecord: sight_state +4, los_flags +5
M_PROJ_ORIGIN = 0x37a
M_SPELL_ORIGIN = 0x37c
MI_PTRS = (M_P3D, M_PCOMBAT, M_VISLIST, M_TARGET + 0x1c)

# ---- W8MonsterCombatState (scratch 3) ----
MC_ATTACK_INDEX = 0x11
MC_BERSERK = 0x15
MC_INTERCEPT = 0x147

# ---- W8MonsterRecord (scratch 2) ----
REC_SIZE = 0x297
R_NAME0 = 0x0
R_NAME1 = 0x30
R_NAME2 = 0x60
R_NAME3 = 0x90
R_KIND = 0xcb
R_NAME_GROUP = 0xcc
R_DR = 0xcf
R_FLAGS = 0xd0
R_APR = 0xe5
R_SPR = 0xe6
R_ATTACKS = 0xe7
ATK_STEP = 0x22
ATK_VERB = 0x1
ATK_WTYPE = 0x2
ATK_RANGE = 0x3
ATK_SCORE = 0x4
ATK_MODES = 0x15
R_EVASION = 0x15d
R_CONSTITUTION = 0x15e
R_HITLOC = 0x15f
R_ACLOC = 0x166
R_ACMODE = 0x16d
R_RECORD_ID = 0x187
R_UNTARGETABLE = 0x24a
R_EFF_LEVEL = 0x24f
R_FACTION = 0x25f
FLAG_BEHIND = 0x02
FLAG_BODYGUARD = 0x04

# ---- W8MonsterGroup (scratch 5) ----
GROUP_SIZE = 0x12b
G_MEMBERS = 0x4
G_SPECIES = 0x18
G_ALTNAME = 0x2c

# ---- globals ----
GX_COMBAT_MODE = 0x8dc
GX_MONSTER_LIST = 0x8f5
GX_GROUP_LIST = 0x8f9
GX_ENCOUNTER_LIST = 0x905
GX_RECORD_CACHE = 0xa0f
GS_XCHAR = 0x8
GS_FORMATION = 0x23a1
GS_SEDEXUS = 0x247f
SET_VERBOSE = 0x44

# enums
ACT_NONE, ACT_ATTACK, ACT_BERSERK, ACT_BREATHE, ACT_TURN, ACT_DEFEND, ACT_PROTECT, ACT_PRAY = \
    -1, 0, 1, 2, 3, 4, 5, 6
LOW_FATIGUE_VERBS = [0x07, 0x0d, 0x0e, 0x0f, 0x15, 0x19, 0x21, 0x2b, 0x31,
                     0x32, 0x34, 0x35, 0x36, 0x38, 0x3b, 0x55, 0x56, 0x57]
SPECIES = [990, 991, 992, 993, 994, 995, 996, 997]
NEUTRAL_SPECIES = 0x224
WORDS = ['Rat', 'Goblin', 'Ghoul', 'Rapax', 'Wolf', 'Spider', 'Bat', 'Golem', 'Imp', 'Orc',
         'Lizard', 'Rogue', 'Ant', 'Bug', 'Warrior', 'Mage', 'Bishop', 'Thief']


def p32(v):
    return struct.pack('<I', int(v) & M32)


def p8(v):
    return bytes([int(v) & 0xff])


def slot_bytes(itype, ichar=-1, imon=-1, igroup=-1, point=(0.0, 0.0, 0.0)):
    """W8CombatSlot, 0x20 bytes, pPCItem = 0."""
    return struct.pack('<IIII3fI', itype & M32, ichar & M32, imon & M32, igroup & M32,
                       point[0], point[1], point[2], 0)


def source_bytes(itype, ichar=-1, imon=-1, name_known=0, reflection=0, backfire=0):
    """W8TargetSource, 0x34 bytes."""
    b = bytearray(0x34)
    struct.pack_into('<III', b, 0, itype & M32, ichar & M32, imon & M32)
    b[0x19] = name_known
    b[0x1b] = reflection
    b[0x1c] = backfire
    return bytes(b)


def xrow(occupied=1, pending=ACT_NONE, modes=(-1, -1, -1, -1), target_ooc=None,
         action=ACT_NONE, target_ic=None):
    b = bytearray(XROW_SET)
    b[0] = occupied
    struct.pack_into('<i', b, X_PENDING, pending)
    for k in range(4):
        struct.pack_into('<i', b, X_MODES + 4 * k, modes[k])
    b[X_TARGET_OOC:X_TARGET_OOC + 0x20] = target_ooc or slot_bytes(0)
    struct.pack_into('<i', b, X_ACTION, action)
    b[X_TARGET_IC:X_TARGET_IC + 0x20] = target_ic or slot_bytes(0)
    return bytes(b)


def pick(r, edges, lo, hi, p=0.4):
    if r.random() < p:
        return r.choice(edges)
    return r.randint(lo, hi)


def emit_sparse(c, addr, data, gap=128):
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


def wide(s, n):
    b = s.encode('utf-16le')[:2 * (n - 1)]
    return b + bytes(2 * n - len(b))


def put(c, ctx, slot, blob, ranges):
    for off, ln in ranges:
        c.set(ctx.char(slot) + off, bytes(blob[off:off + ln]))


HANDS = (C_HAND, 2 * HAND_STEP)
WEAPON_SLOTS = (C_EQUIP + 6 * EQ_STEP, 4 * EQ_STEP)


def fix_items(r, blob, items):
    """Hands that hold something make GetCharAttackRange / the damage-dice lookup read
    EquippedItem[6]/[7]; never let them read record -1 (heap garbage in both exes)."""
    h0 = blob.get_u32(C_HAND + H_HOLDS)
    h1 = blob.get_u32(C_HAND + HAND_STEP + H_HOLDS)
    for eslot, need in ((6, h0 != 0), (7, h0 != 0 or h1 != 0)):
        off = C_EQUIP + eslot * EQ_STEP
        if need and blob.get_i32(off) == -1:
            blob.u32(off, r.choice(items))


def mutate_hands(r, blob, items, p=0.6):
    for h in range(2):
        base = C_HAND + h * HAND_STEP
        if r.random() < p:
            blob.u8(base + H_PLAY, r.choice([0, 1, 1]))
        if r.random() < p * 0.7:
            blob.u32(base + H_HOLDS, r.choice([0, 1, 1, 2, 3]))
        if r.random() < p:
            blob.u32(base + H_ATTACKS, r.choice([0, 1, 1, 2, 2, 3, 4, r.randrange(10),
                                                 0x7fffffff, 0x80000000, M32]))
        if r.random() < p:
            blob.u32(base + H_DBONUS, r.choice([-999, -1000, -998, 0, 1, 2, 5, -5,
                                                r.randint(-50, 50)]))
        if r.random() < p * 0.5:
            blob.u32(C_EQUIP + (6 + h) * EQ_STEP, r.choice(items + [-1]))
    fix_items(r, blob, items)


def char_target_bytes(r, slot=None):
    t = r.randrange(8) if slot is None else slot
    pt = (r.choice([0.0, 1.5, -2.25]), 0.0, r.choice([0.0, 100.0]))
    return slot_bytes(1, t, -1, -1, pt), t


class World:
    """Monsters, records and groups built in scratch and wired into gXStatus."""

    def __init__(self, ctx, c):
        self.ctx = ctx
        self.c = c
        self.mons = []
        self.recs = []
        self.groups = []

    def mon_addr(self, i):
        return self.ctx.scratch(1) + i * 0x800

    def rec_addr(self, k):
        return self.ctx.scratch(2) + k * 0x400

    def cmb_addr(self, i):
        return self.ctx.scratch(3) + i * 0x200

    def grp_addr(self, k):
        return self.ctx.scratch(5) + k * 0x200

    def add_rec(self, species, blob):
        self.recs.append((species, blob))
        return len(self.recs) - 1

    def add_mon(self, blob, cblob=None, vis=()):
        self.mons.append((blob, cblob, list(vis)))
        return len(self.mons) - 1

    def add_group(self, blob):
        self.groups.append(blob)
        return len(self.groups) - 1

    def emit(self, monster_list=True, group_list=False, encounter_list=False):
        ctx, c = self.ctx, self.c
        gx = ctx.g('gXStatus')
        s0 = ctx.scratch(0)
        for k, (species, blob) in enumerate(self.recs):
            emit_sparse(c, self.rec_addr(k), blob)
            c.setp(gx + GX_RECORD_CACHE + species * 4, self.rec_addr(k))
        for i, (blob, cblob, vis) in enumerate(self.mons):
            a = self.mon_addr(i)
            emit_sparse(c, a, blob)
            if cblob is not None:
                emit_sparse(c, self.cmb_addr(i), cblob)
            c.setp(a + M_PCOMBAT, self.cmb_addr(i))
            vl = s0 + 0x200 + i * 0x10
            c.setp(a + M_VISLIST, vl)
            if vis:
                data = s0 + 0x300 + i * 0x40
                c.setp(vl, data)
                c.set(vl + 4, p32(len(vis)) + p32(len(vis)))
                for j, (about, state) in enumerate(vis):
                    va = ctx.scratch(6) + i * 0x400 + j * 0x40
                    c.set(va, p32(about) + bytes([state]) + bytes(4))   # LOS flags clear
                    c.setp(data + 4 * j, va)
        if monster_list:
            if self.mons:
                c.setp(s0, s0 + 0x40)
                c.set(s0 + 4, p32(len(self.mons)) + p32(len(self.mons)))
                for i in range(len(self.mons)):
                    c.setp(s0 + 0x40 + 4 * i, self.mon_addr(i))
            c.setp(gx + GX_MONSTER_LIST, s0)
        if group_list:
            gl = s0 + 0x100
            for k, blob in enumerate(self.groups):
                emit_sparse(c, self.grp_addr(k), blob)
            if self.groups:
                c.setp(gl, gl + 0x40)
                c.set(gl + 4, p32(len(self.groups)) + p32(len(self.groups)))
                for k in range(len(self.groups)):
                    c.setp(gl + 0x40 + 4 * k, self.grp_addr(k))
            c.setp(gx + GX_GROUP_LIST, gl)
        if encounter_list:
            c.setp(gx + GX_ENCOUNTER_LIST, s0 + 0x1f0)   # empty list


def new_monster(r, loc, species, group=0, live=True):
    m = Blob(MI_SIZE)
    m.u32(M_LOC, loc)
    m.u32(M_GROUP, group)
    m.u32(M_SPECIES, species)
    if live:
        m.u8(M_ACTIVE, 1)
        m.u8(M_INCOMBAT, 1)
        hpmax = r.choice([1, 5, 30, 100, 250, r.randrange(1, 400)])
        m.u32(M_HPMAX, hpmax)
        m.u32(M_HP, r.randint(1, hpmax))
    m.u8(M_DISP, r.choice([0, 1, 1, 2, 2]))
    m.u32(M_ACTION_KIND, r.choice([-1, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9]))
    for k in range(5):
        m.u8(M_ATTR + k, r.choice([1, 25, 50, 75, 100, 125, r.randrange(1, 126)]))
    return m


def new_record(r, rid=None):
    d = Blob(REC_SIZE)
    base = r.choice(WORDS)
    d[R_NAME0:R_NAME0 + 0x30] = wide(base, 24)
    d[R_NAME1:R_NAME1 + 0x30] = wide(base + 's', 24)
    d[R_NAME2:R_NAME2 + 0x30] = wide('Big ' + base, 24)
    d[R_NAME3:R_NAME3 + 0x30] = wide('Big ' + base + 's', 24)
    d.u8(R_KIND, r.randrange(14))
    d.u8(R_NAME_GROUP, r.randrange(4))
    d.u8(R_APR, r.choice([1, 1, 2, 3]))
    d.u8(R_SPR, r.choice([1, 1, 2, 3]))
    for a in range(3):
        o = R_ATTACKS + a * ATK_STEP
        d.u8(o, 1 if a == 0 or r.random() < 0.4 else 0)
        d.u8(o + ATK_VERB, r.choice(LOW_FATIGUE_VERBS + [1, 2, 3, 0x10, 0x40, r.randrange(0x60)]))
        d.u8(o + ATK_WTYPE, r.randrange(0x12))
        d.u8(o + ATK_RANGE, r.choice([0, 0, 1, 2, 3]))
        d.u8(o + ATK_SCORE, r.choice([0, 10, 50, 90, 120, 200, 255, r.randrange(256)]))
        d.u16(o + ATK_MODES, r.choice([1, 2, 4, 0x100, 0x1ff, r.randrange(1, 0x200)]))
    d.u8(R_EVASION, r.randint(-10, 20))
    d.u8(R_CONSTITUTION, r.randrange(6))
    d.u8(R_EFF_LEVEL, r.choice([1, 5, 10, 14, 15, 16, 20, 30, r.randrange(1, 40)]))
    d.u32(R_FACTION, r.choice([0, 0, 1, 2, 3, r.randrange(21)]))
    d.u16(R_RECORD_ID, rid if rid is not None else r.randrange(10, 390))
    return d


def corpus_tables(ctx):
    items, weapons = set(), set()
    for _, data in ctx.corpus:
        b = Blob(data)
        for s in range(12):
            v = b.get_i32(C_EQUIP + s * EQ_STEP)
            if v != -1:
                items.add(v)
        for s in range(8):
            v = b.get_i32(0x1029 + s * EQ_STEP)
            if v != -1:
                items.add(v)
        for h in range(2):
            base = C_HAND + h * HAND_STEP
            if b.get_u32(base + H_HOLDS) == 1 and b[base + H_PLAY]:
                v = b.get_i32(C_EQUIP + (6 + h) * EQ_STEP)
                if v != -1:
                    weapons.add(v)
    return sorted(items), sorted(weapons)


def set_cstate(c, ctx):
    c.setp(ctx.g('g_combat_state'), ctx.scratch(4))
    return ctx.scratch(4)


def tgt_addr(ctx):
    """The W8CombatSlot argument (scratch 7, away from the world's lists)."""
    return ctx.scratch(7)


def src_addr(ctx):
    """The W8TargetSource argument."""
    return ctx.scratch(7) + 0x100


def xchar(ctx, slot):
    return (ctx.g('g_status') + GS_XCHAR).deref() + slot * XROW


def formation_bytes(r):
    b = bytearray(0x84)
    for row in range(5):
        for k in range(3):
            b[row * 3 + k] = r.choice([-1, -1, -1] + list(range(8))) & 0xff
    for i in range(8):
        b[0x14 + 12 * i] = r.choice([0, 0, 1, 1, 2, 2, 3, 3, 4, -1]) & 0xff
        b[0x14 + 12 * i + 1] = 0xff
        b[0x14 + 12 * i + 2] = r.randrange(3)
    return bytes(b)


def set_formation(c, ctx, r):
    c.set(ctx.g('g_status') + GS_FORMATION, formation_bytes(r))


def set_verbose(c, ctx, v=0):
    c.set(ctx.g('g_settings') + SET_VERBOSE, p8(v))


def set_combat_mode(c, ctx, v):
    c.set(ctx.g('gXStatus') + GX_COMBAT_MODE, p8(v))


def cap_xchar(c, ctx, slots=range(8)):
    slots = list(slots)
    lo, hi = min(slots), max(slots) + 1
    ign = [s * XROW + o - lo * XROW for s in range(lo, hi) for o in XROW_PTRS]
    c.cap(xchar(ctx, lo), (hi - lo) * XROW, 'xchar', ignore=ign)


def cap_cstate(c, ctx):
    c.cap(ctx.scratch(4), CS_SIZE, 'cstate', ignore=list(CS_IGNORE))


# ------------------------------------------------------------------ simple helpers

def cases_hand_dice(ctx, items):
    fn = ctx.fn(0x00546a70)   # void GetCharacterHandDamageDice(const W8Character*, int, W8Dice*)
    for i in range(ctx.n(300)):
        r = ctx.rng('handdice', i)
        c = ctx.case('handdice.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        (_, blob, name), = ctx.set_party(c, r, slots=[slot])
        hand = r.randrange(2)
        base = C_HAND + hand * HAND_STEP
        if r.random() < 0.5:
            blob.u32(base + H_HOLDS, r.choice([0, 0, 1, 2, 3, 5]))
        if r.random() < 0.6:
            blob[base + H_DICE:base + H_DICE + 4] = bytes(r.randrange(256) for _ in range(4))
        for eslot in (6, 7):
            if r.random() < 0.5:
                blob.u32(C_EQUIP + eslot * EQ_STEP, r.choice(items + [-1]))
        fix_items(r, blob, items)
        put(c, ctx, slot, blob, [HANDS, WEAPON_SLOTS])
        out = ctx.scratch(7) + 0x200
        c.set(out, b'\xcd' * 8)
        c.arg(ctx.char(slot)).arg(hand).arg(out)
        c.cap(out, 8, 'dice')
        c.note(char=name, slot=slot, hand=hand, holds=blob.get_u32(base + H_HOLDS),
               eq6=blob.get_i32(C_EQUIP + 6 * EQ_STEP), eq7=blob.get_i32(C_EQUIP + 7 * EQ_STEP))


def cases_hand_damage_bonus(ctx):
    fn = ctx.fn(0x00546b10)   # int GetCharacterHandDamageBonus(const W8Character*, int)
    for i in range(ctx.n(150)):
        r = ctx.rng('dmgbonus', i)
        c = ctx.case('dmgbonus.%d' % i, fn, conv='c', ret='i')
        slot = r.randrange(8)
        (_, blob, name), = ctx.set_party(c, r, slots=[slot])
        hand = r.randrange(2)
        if r.random() < 0.7:
            dp = pick(r, [0, 1, -1, 100, -100, 0x7fffffff, -0x80000000, 255, -129], -300, 300)
            c.set(ctx.char(slot) + C_HAND + hand * HAND_STEP + H_DPCT, p32(dp))
        if r.random() < 0.7:
            c.set(ctx.char(slot) + C_BONUS + MOD_DPCT, p8(pick(r, [0, 127, -128, -1, 1], -128, 127)))
        c.arg(ctx.char(slot)).arg(hand)
        c.note(char=name, slot=slot, hand=hand)


def cases_clear_block(ctx):
    fn = ctx.fn(0x00543260)   # void ClearAttackBlock(W8SpellEffectDefinition*)
    for i in range(ctx.n(10)):
        r = ctx.rng('clearblock', i)
        c = ctx.case('clearblock.%d' % i, fn, conv='c', ret='v')
        blk = ctx.scratch(0) + 0x100
        c.set(blk - 0x10, bytes(r.randrange(1, 256) for _ in range(0x50)))
        c.arg(blk)
        c.cap(blk - 0x10, 0x50, 'block')


def cases_normalize_cycle(ctx):
    fn = ctx.fn(0x005430c0)   # W8MonsterCycle NormalizeMonsterCycle(W8MonsterCycle)
    values = list(range(-3, 41)) + [0x7fffffff, -0x80000000, 0x109, 0x10a, 0x111, 0x112,
                                     0xffffff09, 0xffffff11, 0x10009, 0x80000009, 255, 256]
    for i, v in enumerate(values[:ctx.n(len(values))]):
        c = ctx.case('normcycle.%d' % i, fn, conv='c', ret='i')
        c.arg(v)
        c.note(cycle=v)


def attack_mask(r):
    k = r.random()
    if k < 0.25:
        m = 1 << r.randrange(9)
    elif k < 0.55:
        m = r.randrange(1, 0x200)
    elif k < 0.8:
        m = r.randrange(0x10000)
        if m & 0x1ff == 0:
            m |= 1 << r.randrange(9)
    else:
        m = r.choice([0x1ff, 0x100, 0x101, 0x180, 0x003, 0xfe01, 0xff00 | 0x80, 0x8001])
    if r.random() < 0.25:
        m |= r.randrange(1, 0x10000) << 16
    return m


def cases_choose_attack_mode(ctx):
    fn = ctx.fn(0x00542db0)   # W8AttackMode ChooseAttackMode(unsigned int)
    for i in range(ctx.n(300)):
        r = ctx.rng('choosemode', i)
        c = ctx.case('choosemode.%d' % i, fn, conv='c', ret='i')
        m = attack_mask(r)
        c.arg(m)
        c.note(mask='0x%x' % m)


# ------------------------------------------------------------------ party helpers

def cases_can_character_attack(ctx):
    fn = ctx.fn(0x00545b80)   # bool CanCharacterAttack(int)
    for i in range(ctx.n(200)):
        r = ctx.rng('canattack', i)
        c = ctx.case('canattack.%d' % i, fn, conv='c', ret='b')
        ctx.set_party(c, r)
        slot = r.choice(list(range(8)) * 6 + [-1, 8, 9, 100, -100, 0x7fffffff, -0x80000000])
        for s in range(8):
            c.set(xchar(ctx, s), p8(1 if r.random() < 0.85 else 0))
        if 0 <= slot < 8:
            if r.random() < 0.15:
                c.set(ctx.char(slot) + C_HP, p32(0))
            if r.random() < 0.6:
                c.set(ctx.char(slot) + C_HC, p32(r.choice([0, 0, 1, 7, 10, 11, 12, 13, 14, 18, 19])))
            if r.random() < 0.5:
                c.set(ctx.char(slot) + C_HAND + H_PLAY, p8(r.randrange(2)))
        c.arg(slot)
        c.note(slot=slot)


def cases_hand_reach(ctx, items):
    reach = ctx.fn(0x0053d2a0)   # bool CanHandReachTarget(int, unsigned)
    anyr = ctx.fn(0x0053d310)    # bool CanAnyHandReachTarget(int)
    value = ctx.fn(0x0053d7f0)   # int GetHandAttackValue(int, unsigned)
    for name, fn, count, with_hand in (('handreach', reach, 250, True),
                                       ('anyreach', anyr, 200, False),
                                       ('handvalue', value, 200, True)):
        for i in range(ctx.n(count)):
            r = ctx.rng(name, i)
            c = ctx.case('%s.%d' % (name, i), fn, conv='c', ret='b' if fn is not value else 'i')
            slot = r.randrange(8)
            (_, blob, cname), = ctx.set_party(c, r, slots=[slot])
            mutate_hands(r, blob, items)
            ranges = [HANDS, WEAPON_SLOTS]
            hand = r.randrange(2)
            if with_hand and r.random() < 0.06:
                hand = r.choice([2, 3])   # retail asserts, then reads Hand[2]/[3] inside the record
                for h in (2, 3):
                    blob.u8(C_HAND + h * HAND_STEP + H_PLAY, r.randrange(2))
                ranges.append((C_HAND + 2 * HAND_STEP, 2 * HAND_STEP))
            put(c, ctx, slot, blob, ranges)
            c.arg(slot)
            if with_hand:
                c.arg(hand)
            c.note(char=cname, slot=slot, hand=hand if with_hand else None)


def cases_char_damage_reduction(ctx):
    fn = ctx.fn(0x00545950)   # int ApplyCharacterDamageReduction(W8Character*, int)
    for i in range(ctx.n(300)):
        r = ctx.rng('chardr', i)
        c = ctx.case('chardr.%d' % i, fn, conv='c', ret='i')
        slot = r.randrange(8)
        (_, blob, name), = ctx.set_party(c, r, slots=[slot])
        set_combat_mode(c, ctx, 1)   # a level-up notice would open a message box out of combat
        set_cstate(c, ctx)
        dr = pick(r, [0, 0, 1, 50, 99, 100, 101, 150, -1, -50, -100, 200], -200, 200, 0.5)
        dmg = pick(r, [0, 1, -1, 2, 49, 50, 51, 99, 100, 101, 1000, -1000, 21474836, -21474836,
                       0x7fffffff, -0x80000000], -500, 5000, 0.4)
        c.set(ctx.char(slot) + C_DR, p32(dr))
        sk = C_SKILL + SKILL_IRON_SKIN * SKILL_STEP
        if r.random() < 0.8:
            blob.u8(sk, 1 if r.random() < 0.75 else 0)
            blob.u32(sk + SK_POINTS, pick(r, [0, 1, 50, 98, 99, 100, 101, 120], 0, 120))
            blob.u32(sk + SK_BASE, pick(r, [0, 1, 25, 50, 100, 125], 0, 125))
            blob.u32(sk + SK_PRACTICE, r.randrange(7))   # < 7: never levels (no derived-stat pass)
            put(c, ctx, slot, blob, [(sk, SKILL_STEP)])
        if r.random() < 0.3:
            c.set(ctx.char(slot) + C_PROF, p32(r.randrange(15)))
        c.arg(ctx.char(slot)).arg(dmg)
        c.cap(ctx.char(slot), CHAR, 'char')
        c.note(char=name, slot=slot, dr=dr, damage=dmg)


def cases_berserk(ctx, items):
    fn = ctx.fn(0x005458a0)   # bool CanCharacterBerserk(int)
    for i in range(ctx.n(250)):
        r = ctx.rng('berserk', i)
        c = ctx.case('berserk.%d' % i, fn, conv='c', ret='b')
        slot = r.randrange(8)
        (_, blob, name), = ctx.set_party(c, r, slots=[slot])
        mutate_hands(r, blob, items)
        ranges = [HANDS, WEAPON_SLOTS]
        if r.random() < 0.6:
            blob.u32(C_PROF, r.choice([0, 0, 1, 2, 4, 5, 6, 9, -1] + list(range(15))))
            blob.u32(C_RACE, r.choice([-1] + list(range(16))))
            ranges.append((C_PROF, 12))
        put(c, ctx, slot, blob, ranges)
        c.arg(slot)
        c.note(char=name, slot=slot, prof=blob.get_i32(C_PROF), race=blob.get_i32(C_RACE))


def party_state(c, ctx, r, p_dead=0.1):
    """Corpus party + fOccupied rows + a few dead/out-of-formation members."""
    party = ctx.set_party(c, r)
    occ = [1 if r.random() < 0.85 else 0 for _ in range(8)]
    for s in range(8):
        if r.random() < p_dead:
            c.set(ctx.char(s) + C_HP, p32(0))
        if r.random() < 0.08:
            c.set(ctx.char(s) + C_HC, p32(r.choice([12, 13, 17, 18, 19])))
        if r.random() < 0.15:
            c.set(ctx.char(s) + C_BONUS + MOD_OOF, p8(1))
    return party, occ


def cases_has_attack_on(ctx):
    fn = ctx.fn(0x00545c20)   # bool CharacterHasAttackOn(int, W8CombatSlot*)
    for i in range(ctx.n(250)):
        r = ctx.rng('hasattackon', i)
        c = ctx.case('hasattackon.%d' % i, fn, conv='c', ret='b')
        party, occ = party_state(c, ctx, r)
        for s in range(8):
            c.set(xchar(ctx, s), p8(occ[s]))
        set_formation(c, ctx, r)
        set_cstate(c, ctx)
        slot = r.randrange(8)
        tgt = tgt_addr(ctx)
        k = r.random()
        if k < 0.7:
            tb, t = char_target_bytes(r)
            c.set(tgt, tb)
            c.note(slot=slot, target='char%d' % t)
        elif k < 0.85:
            w = World(ctx, c)
            rec = new_record(r)
            w.add_rec(SPECIES[0], rec)
            m = new_monster(r, 0x7a001, SPECIES[0])
            fail = r.randrange(4)    # never reach CanPartyMemberAimAtMonster (world geometry)
            if fail == 0:
                m.u8(M_ACTIVE, 0)
            elif fail == 1:
                m.u32(M_HP, 0)
            elif fail == 2:
                m.u8(M_INCOMBAT, 0)
            else:
                rec.u8(R_UNTARGETABLE, r.choice([1, 2, 255]))
            w.add_mon(m)
            w.emit()
            c.set(tgt, slot_bytes(3, -1, 0x7a001))
            c.note(slot=slot, target='monster', fail=fail)
        else:
            ty = r.choice([0, 2, 4, 5, 6, 7, 8, 9, 10, -1])
            c.set(tgt, slot_bytes(ty, r.randrange(8), 0x7a001, 5))
            c.note(slot=slot, target='type%d' % ty)
        c.arg(slot).arg(tgt)


# ------------------------------------------------------------------ monster helpers

def cases_monster_protect(ctx):
    fn = ctx.fn(0x00545bd0)   # bool CanMonsterProtect(W8MonsterInfo*)
    for i in range(ctx.n(200)):
        r = ctx.rng('monprotect', i)
        c = ctx.case('monprotect.%d' % i, fn, conv='c', ret='b')
        w = World(ctx, c)
        rec = new_record(r)
        rec.u8(R_FLAGS, r.choice([0, FLAG_BODYGUARD, FLAG_BODYGUARD, 0xff, 0xfb, 0x06, r.randrange(256)]))
        rec.u8(R_ATTACKS, r.choice([0, 1, 1, 2, 0x80, 0xff]))
        w.add_rec(SPECIES[1], rec)
        m = new_monster(r, 0x7a010, SPECIES[1])
        if r.random() < 0.15:
            m.u8(M_ACTIVE, 0)
        if r.random() < 0.15:
            m.u8(M_INCOMBAT, 0)
        if r.random() < 0.15:
            m.u32(M_HP, r.choice([0, 0, 0x80000000, M32]))
        m.u32(M_HC, r.choice([0, 0, 0, 5, 11, 12, 13, 18, 19, 0x80000000]))
        w.add_mon(m)
        w.emit(monster_list=False)
        c.arg(w.mon_addr(0))
        c.note(flags=rec[R_FLAGS], has_attack=rec[R_ATTACKS], hc=m.get_u32(M_HC))


def cases_apply_damage_reduction(ctx):
    fn = ctx.fn(0x005459b0)   # int ApplyDamageReduction(const W8MonsterInfo*, const W8MonsterRecord*, int)
    for i in range(ctx.n(300)):
        r = ctx.rng('applydr', i)
        c = ctx.case('applydr.%d' % i, fn, conv='c', ret='i')
        w = World(ctx, c)
        rec = new_record(r)
        rdr = pick(r, [0, 1, 25, 50, 99, 100, 101, 200, 255], 0, 255, 0.5)
        rec.u8(R_DR, rdr)
        w.add_rec(SPECIES[2], rec)
        m = new_monster(r, 0x7a020, SPECIES[2])
        adj = pick(r, [0, 0, 1, -1, 50, -50, 100, -100, 127, -128], -128, 127, 0.5)
        m.u8(M_MODS + MOD_DR, adj)
        w.add_mon(m)
        w.emit(monster_list=False)
        dmg = pick(r, [0, 1, -1, 2, 49, 50, 51, 99, 100, 101, 1000, -1000, 5000000, -5000000,
                       0x7fffffff, -0x80000000], -300, 3000, 0.4)
        c.arg(w.mon_addr(0)).arg(w.rec_addr(0)).arg(dmg)
        c.note(record_dr=rdr, adjust=adj, damage=dmg)


def rate_world(ctx, c, r):
    """A main monster (index 0, record 0) plus 0..2 others, none of which can be reached."""
    party, occ = party_state(c, ctx, r)
    for s in range(8):
        c.set(xchar(ctx, s), p8(occ[s]))
        if r.random() < 0.1:
            c.set(ctx.char(s) + C_COND + COND_TURNCOAT * 4, p32(r.choice([1, 9999])))
    w = World(ctx, c)
    rec = new_record(r)
    for a in range(3):
        o = R_ATTACKS + a * ATK_STEP
        if r.random() < 0.5:
            rec.u8(o, r.choice([0, 0, 1, 1, 2, 0xff]))
        if r.random() < 0.25:
            rec.u16(o + ATK_MODES, r.choice([0, 0, 1, 0x200, 0x8000]))
        if r.random() < 0.3:
            rec.u8(o + ATK_RANGE, r.choice([0, 1, 2, 3, 4, 0xff]))
    if r.random() < 0.15:
        rec.u8(R_APR, 0)
    if r.random() < 0.15:
        rec.u8(R_SPR, 0)
    if r.random() < 0.3:
        rec.u8(R_UNTARGETABLE, 1)
    # attacks[3] (out of range) lands on spells[]; make it look like an attack sometimes
    if r.random() < 0.5:
        rec[R_ATTACKS + 3 * ATK_STEP:R_ATTACKS + 3 * ATK_STEP + 10] = bytes(
            [1, 5, 2, r.randrange(4), 50, 1, 0, 0, 0, 0])
    w.add_rec(SPECIES[3], rec)
    rec2 = new_record(r)
    w.add_rec(r.choice([SPECIES[4], NEUTRAL_SPECIES]), rec2)
    others = r.randrange(3)
    vis = []
    for k in range(others):
        loc = 0x7a031 + k
        if r.random() < 0.6:
            vis.append((loc, r.choice([0, 1, 2])))
    m = new_monster(r, 0x7a030, SPECIES[3])
    if r.random() < 0.3:
        m.u8(M_INCOMBAT, 0)
    m.u8(M_DISP, r.choice([0, 1, 2, 3]))
    m.u8(M_PVIS + 4, r.choice([0, 1, 1, 2]))     # party sight; LOS flags stay clear
    m.u8(M_PROJ_ORIGIN, r.randrange(2))
    m.u8(M_SPELL_ORIGIN, r.randrange(2))
    cb = Blob(0x153)
    cb.u8(MC_BERSERK, 1 if r.random() < 0.3 else 0)
    w.add_mon(m, cb, vis)
    for k in range(others):
        o = new_monster(r, 0x7a031 + k, w.recs[r.randrange(2)][0])
        if r.random() < 0.2:
            o.u8(M_ACTIVE, 0)
        if r.random() < 0.2:
            o.u8(M_INCOMBAT, 0)
        if r.random() < 0.15:
            o.u32(M_HP, 0)
        if r.random() < 0.15:
            o.u32(M_HC, r.choice([17, 18, 19]))
        if r.random() < 0.2:
            o.u32(M_COND + COND_TURNCOAT * 4, 5)
        w.add_mon(o)
    w.emit()
    return w, rec


def cases_rate_monster_attack(ctx):
    fn = ctx.fn(0x0053d4b0)   # u8 RateMonsterAttack(W8MonsterInfo*, W8MonsterRecord*, unsigned, int, bool)
    for i in range(ctx.n(300)):
        r = ctx.rng('rateattack', i)
        c = ctx.case('rateattack.%d' % i, fn, conv='c', ret='u8')
        w, rec = rate_world(ctx, c, r)
        attack = r.choice([0, 0, 0, 1, 1, 2, 2]) if r.random() < 0.95 else 3
        friendly = r.randrange(2)
        c.arg(w.mon_addr(0)).arg(w.rec_addr(0)).arg(attack).arg(r.randrange(2)).arg(friendly)
        c.cap(w.mon_addr(0), MI_SIZE, 'monster', ignore=list(MI_PTRS))
        c.note(attack=attack, friendly=friendly, monsters=len(w.mons))


def cases_rate_best_attack(ctx):
    fn = ctx.fn(0x0053d450)   # u8 RateMonsterBestAttack(W8MonsterInfo*, W8MonsterRecord*, bool)
    for i in range(ctx.n(200)):
        r = ctx.rng('ratebest', i)
        c = ctx.case('ratebest.%d' % i, fn, conv='c', ret='u8')
        w, rec = rate_world(ctx, c, r)
        if r.random() < 0.2:
            c.set(w.mon_addr(0) + M_MOTIONLESS, p8(r.choice([1, 2, 0xff])))
        friendly = r.randrange(2)
        c.arg(w.mon_addr(0)).arg(w.rec_addr(0)).arg(friendly)
        c.cap(w.mon_addr(0), MI_SIZE, 'monster', ignore=list(MI_PTRS))
        c.note(friendly=friendly)


def protect_world(ctx, c, r, inline_target):
    """Protector m0 (record 0) and a possible target monster m1 (record 1); the target slot is
    either m0's own Target (inline_target) or scratch 0 + 0x400. Geometry is never reached:
    m0's party sight is unseen or LOS-less and mon-to-mon rows carry no LOS flag."""
    party, occ = party_state(c, ctx, r)
    for s in range(8):
        c.set(xchar(ctx, s), p8(occ[s]))
        if r.random() < 0.15:
            c.set(ctx.char(s) + C_COND + COND_TURNCOAT * 4, p32(r.choice([1, 9999])))
    w = World(ctx, c)
    rec0 = new_record(r)
    rec0.u8(R_FLAGS, r.choice([FLAG_BODYGUARD, FLAG_BODYGUARD, 0, 0xff, 0x06]))
    if r.random() < 0.15:
        rec0.u8(R_UNTARGETABLE, 1)
    if r.random() < 0.15:
        rec0.u8(R_ATTACKS, 0)
    rec1 = new_record(r)
    if r.random() < 0.2:
        rec1.u8(R_UNTARGETABLE, r.choice([1, 0x80]))
    sp0 = SPECIES[5]
    sp1 = r.choice([SPECIES[6], SPECIES[6], NEUTRAL_SPECIES])
    w.add_rec(sp0, rec0)
    w.add_rec(sp1, rec1)
    m0 = new_monster(r, 0x7a040, sp0)
    m1 = new_monster(r, 0x7a041, sp1)
    for m in (m0, m1):
        if r.random() < 0.1:
            m.u8(M_ACTIVE, 0)
        if r.random() < 0.1:
            m.u8(M_INCOMBAT, 0)
        if r.random() < 0.1:
            m.u32(M_HP, 0)
        if r.random() < 0.15:
            m.u32(M_HC, r.choice([5, 11, 12, 13, 19]))
        if r.random() < 0.15:
            m.u32(M_COND + COND_TURNCOAT * 4, 3)
        m.u8(M_DISP, r.choice([0, 1, 2, 2, 2, 3]))
        m.u8(M_MODS + MOD_OOF, r.choice([0, 0, 1]))
    m1.u8(M_DISP, m0[M_DISP] if r.random() < 0.6 else m1[M_DISP])
    m0.u8(M_PVIS + 4, r.choice([0, 1, 2]))
    vis = []
    if r.random() < 0.6:
        vis.append((0x7a041, r.choice([0, 1, 2])))
    if r.random() < 0.2:
        vis.append((0x7a099, 1))
    k = r.random()
    if k < 0.35:
        tb, t = char_target_bytes(r)
        desc = 'char%d' % t
    elif k < 0.75:
        tb = slot_bytes(3, -1, 0x7a041)
        desc = 'monster'
    elif k < 0.9:
        tb = slot_bytes(3, -1, 0x7a040)
        desc = 'self'
    else:
        ty = r.choice([0, 2, 4, 5, 7, 9])
        tb = slot_bytes(ty, r.randrange(8), 0x7a041, 3)
        desc = 'type%d' % ty
    if inline_target:
        m0[M_TARGET:M_TARGET + 0x20] = tb
    cb = Blob(0x153)
    cb.u8(MC_BERSERK, r.randrange(2))
    w.add_mon(m0, cb, vis)
    w.add_mon(m1)
    w.emit()
    return w, tb, desc


def cases_protect_combatant(ctx):
    fn = ctx.fn(0x00545cf0)   # bool CanMonsterProtectCombatant(W8MonsterInfo*, W8CombatSlot*)
    for i in range(ctx.n(250)):
        r = ctx.rng('protectcomb', i)
        c = ctx.case('protectcomb.%d' % i, fn, conv='c', ret='b')
        w, tb, desc = protect_world(ctx, c, r, False)
        tgt = tgt_addr(ctx)
        c.set(tgt, tb)
        c.arg(w.mon_addr(0)).arg(tgt)
        c.note(target=desc)


def cases_protect_target(ctx):
    fn = ctx.fn(0x00545b20)   # bool CanMonsterProtectTarget(W8MonsterInfo*)
    for i in range(ctx.n(200)):
        r = ctx.rng('protecttgt', i)
        c = ctx.case('protecttgt.%d' % i, fn, conv='c', ret='b')
        w, tb, desc = protect_world(ctx, c, r, True)
        c.arg(w.mon_addr(0))
        c.note(target=desc)


def cases_guardian(ctx, items):
    fn = ctx.fn(0x00545e50)   # int ResolveGuardianInterception(W8TargetSource*, W8CombatSlot*)
    for i in range(ctx.n(200)):
        r = ctx.rng('guardian', i)
        c = ctx.case('guardian.%d' % i, fn, conv='c', ret='i')
        party = ctx.set_party(c, r)
        cs = set_cstate(c, ctx)
        set_verbose(c, ctx, 0)
        set_formation(c, ctx, r)
        if r.random() < 0.3:
            c.set(cs + CS_UNAWARE, p8(1) + p8(r.randrange(2)))
        elif r.random() < 0.2:
            c.set(cs + CS_NATURAL, p8(1))
        # world: a source monster and a would-be bodyguard monster
        w = World(ctx, c)
        rec = new_record(r)
        rec.u8(R_FLAGS, r.choice([FLAG_BODYGUARD, 0]))
        w.add_rec(SPECIES[7], rec)
        msrc = new_monster(r, 0x7a050, SPECIES[7])
        msrc.u32(M_FATIGUE, r.choice([0, 0, 1, 2, 3, 4, 7, 50]))
        msrc.u8(M_MODS + MOD_HIT, r.randint(-10, 10))
        mbg = new_monster(r, 0x7a051, SPECIES[7])
        mbg.u32(M_ACTION_KIND, 8)
        cbg = Blob(0x153)
        cbg.u32(MC_INTERCEPT, r.randrange(3))
        target_monster = r.random() < 0.15
        if target_monster:
            mt = new_monster(r, 0x7a052, SPECIES[7])
            mt.u8(M_INCOMBAT, 0)      # cannot be aimed at: no geometry
            tb = slot_bytes(3, -1, 0x7a052)
        else:
            tb, tslot = char_target_bytes(r)
        mbg[M_TARGET:M_TARGET + 0x20] = tb
        w.add_mon(msrc)
        w.add_mon(mbg, cbg)
        if target_monster:
            w.add_mon(mt)
        w.emit()
        # party rows
        rows = bytearray(8 * CROW)
        for s in range(8):
            dead = 1 if r.random() < 0.35 else 0
            protector = r.random() < 0.55
            rows[s * CROW + R_DEAD] = dead
            struct.pack_into('<I', rows, s * CROW + R_INTERCEPT, r.choice([0, 0, 0, 1, 2]))
            other = slot_bytes(1, r.randrange(8)) if r.random() < 0.5 else slot_bytes(0)
            if protector:
                if dead:
                    row = xrow(1, ACT_PROTECT, target_ooc=tb, action=r.choice([ACT_ATTACK, ACT_PROTECT]),
                               target_ic=other)
                else:
                    row = xrow(1, r.choice([ACT_NONE, ACT_ATTACK]), target_ooc=other,
                               action=ACT_PROTECT, target_ic=tb)
            else:
                row = xrow(1 if r.random() < 0.9 else 0, r.choice([ACT_NONE, ACT_ATTACK, ACT_DEFEND]),
                           target_ooc=tb if r.random() < 0.3 else other,
                           action=r.choice([ACT_ATTACK, ACT_DEFEND, ACT_PRAY]),
                           target_ic=tb if r.random() < 0.3 else other)
            c.set(xchar(ctx, s), row)
        c.set(cs + CS_ROWS, bytes(rows))
        for s, blob, _ in party:
            # keep fatigue away from unconsciousness / the deep-fatigue voice event:
            # one write over highest_condition .. stamina, one for the deep-fatigue latch
            stmax = max(blob.get_i32(C_STMAX), 150)
            blob.u32(C_STMAX, stmax)
            blob.u32(C_STAM, stmax)
            if r.random() < 0.08:
                blob.u32(C_HC, r.choice([12, 15, 18]))
            put(c, ctx, s, blob, [(C_HC, C_STAM + 4 - C_HC)])
            c.set(ctx.char(s) + C_DEEPF, p8(1))
            fix = r.random()
            if blob.get_i32(C_EQUIP + 6 * EQ_STEP) == -1 or fix < 0.2:
                c.set(ctx.char(s) + C_EQUIP + 6 * EQ_STEP, p32(r.choice(items)))
            if fix > 0.8:
                c.set(ctx.char(s) + C_HAND + H_ATTACKS, p32(r.choice([0, 1, 2, 3])))
        k = r.random()
        if k < 0.55:
            src = source_bytes(2, -1, 0x7a050)
            desc = 'monster'
        else:
            src = source_bytes(1, r.randrange(8))
            desc = 'char'
        sa = src_addr(ctx)
        tgt = tgt_addr(ctx)
        c.set(sa, src)
        c.set(tgt, tb)
        c.arg(sa).arg(tgt)
        c.cap(tgt, 0x20, 'target')
        cap_cstate(c, ctx)
        cap_xchar(c, ctx)
        c.cap(ctx.char(0), 8 * CHAR, 'party')
        c.note(source=desc, target_monster=target_monster)


def cases_attack_its_target(ctx, items):
    fn = ctx.fn(0x00545aa0)   # bool CanCharacterAttackItsTarget(int)
    for i in range(ctx.n(200)):
        r = ctx.rng('attackits', i)
        c = ctx.case('attackits.%d' % i, fn, conv='c', ret='b')
        party, occ = party_state(c, ctx, r)
        set_formation(c, ctx, r)
        set_cstate(c, ctx)
        slot = r.randrange(8)
        blob = party[slot][1]
        mutate_hands(r, blob, items, 0.4)
        put(c, ctx, slot, blob, [HANDS, WEAPON_SLOTS])
        # empty scratch monster / group lists: monster and group targets are never found
        w = World(ctx, c)
        w.emit(monster_list=True, group_list=True, encounter_list=True)
        k = r.random()
        if k < 0.75:
            tb, t = char_target_bytes(r)
            desc = 'char%d' % t
        else:
            ty = r.choice([0, 2, 3, 4, 5, 7, 8])
            tb = slot_bytes(ty, r.randrange(8), 0x7a0ff, 0x7a0ff)
            desc = 'type%d' % ty
        pending = r.choice([ACT_ATTACK, ACT_ATTACK, ACT_ATTACK, ACT_BERSERK, ACT_PROTECT, ACT_NONE,
                            ACT_BREATHE, ACT_TURN, ACT_DEFEND, ACT_PRAY, 9, 10, 11])
        for s in range(8):
            if s == slot:
                c.set(xchar(ctx, s), xrow(occ[s], pending, target_ooc=tb, action=ACT_ATTACK))
            else:
                c.set(xchar(ctx, s), p8(occ[s]))
        c.arg(slot)
        c.note(slot=slot, pending=pending, target=desc)


def cases_choose_hand(ctx, items):
    choose = ctx.fn(0x0053d390)    # int ChooseCharacterAttackHand(int)
    prepare = ctx.fn(0x0053d680)   # void PrepareCharacterAttacks(int)
    for name, fn, count in (('choosehand', choose, 250), ('prepare', prepare, 250)):
        for i in range(ctx.n(count)):
            r = ctx.rng(name, i)
            c = ctx.case('%s.%d' % (name, i), fn, conv='c', ret='i' if fn is choose else 'v')
            slot = r.randrange(8)
            (_, blob, cname), = ctx.set_party(c, r, slots=[slot])
            mutate_hands(r, blob, items, 0.7)
            put(c, ctx, slot, blob, [HANDS, WEAPON_SLOTS])
            if fn is prepare:
                cs = set_cstate(c, ctx)
                c.set(cs + CS_ROWS + slot * CROW + R_SAVED, b'\x77' * 0x10)
                c.set(cs + CS_ROWS + slot * CROW + R_CURHAND, p32(0x55))
                cap_cstate(c, ctx)
            c.arg(slot)
            c.note(char=cname, slot=slot)


# ------------------------------------------------------------------ armour class family

def ac_target(ctx, c, r, kinds=('monster', 'char', 'other')):
    """Builds the target in scratch 0 + 0x400 and the state the AC functions read."""
    tgt = tgt_addr(ctx)
    cs = set_cstate(c, ctx)
    combat = r.randrange(2)
    set_combat_mode(c, ctx, combat)
    if r.random() < 0.5:
        c.set(cs + CS_UNAWARE, p8(r.randrange(2)) + p8(r.randrange(2)))
    kind = r.choice(kinds)
    info = {'kind': kind, 'combat': combat}
    if kind == 'monster':
        w = World(ctx, c)
        rec = new_record(r)
        rec.u8(R_FLAGS, r.choice([0, FLAG_BEHIND, FLAG_BEHIND | FLAG_BODYGUARD, 0xff, r.randrange(256)]))
        rec.u8(R_EVASION, pick(r, [0, 14, 15, 16, -128, 127, -5, 10, 20], -20, 30))
        for k in range(7):
            rec.u8(R_ACLOC + k, r.randint(-20, 30))
            rec.u8(R_HITLOC + k, r.randrange(101))
        for k in range(9):
            rec.u8(R_ACMODE + k, r.randint(-20, 30))
        w.add_rec(SPECIES[0], rec)
        m = new_monster(r, 0x7a060, SPECIES[0])
        m.u8(M_MODS + MOD_ACADJ, pick(r, [0, 127, -128, 1, -1], -20, 20))
        m.u8(M_MODS + MOD_ARMOR_FLAT, pick(r, [0, 127, -128, 1, -1], -20, 20))
        m.u8(M_MODS + MOD_MATCHUP, pick(r, [0, 127, -128], -20, 20))
        m.u8(M_MODS + MOD_OOF, r.choice([0, 0, 1, 2]))
        m.u32(M_FATIGUE, r.choice([0, 1, 2, 3, 4, 4, 5, 9, 10, 37, 100, -1, -10, 0x7fffffff]))
        m.u32(M_ACTION_KIND, r.choice([-1, 0, 1, 1, 2, 3, 4, 4, 5, 8, 9]))
        w.add_mon(m)
        w.emit()
        c.set(tgt, slot_bytes(3, -1, 0x7a060))
        info.update(evasion=rec.get_u16(R_EVASION) & 0xff, oof=m[M_MODS + MOD_OOF])
    elif kind == 'char':
        t = r.randrange(8)
        (_, blob, name), = ctx.set_party(c, r, slots=[t])
        if r.random() < 0.6:
            c.set(ctx.char(t) + C_ACCOMP + 4, p32(pick(r, [0, 1, -1, 5, -5], -10, 15)))
        if r.random() < 0.6:
            c.set(ctx.char(t) + C_ACCOMP + 12, p32(pick(r, [0, 1, -1, 5, -5], -10, 15)))
        if r.random() < 0.5:
            c.set(ctx.char(t) + C_ACTOT, p32(pick(r, [0, -10, 10, 50, -50], -20, 40)))
        if r.random() < 0.5:
            c.set(ctx.char(t) + C_ACLOC, b''.join(p32(r.randint(-15, 40)) for _ in range(5)))
        if r.random() < 0.3:
            c.set(ctx.char(t) + C_BONUS + MOD_OOF, p8(1))
        if r.random() < 0.1:
            c.set(ctx.char(t) + C_HP, p32(0))
        if r.random() < 0.15:
            c.set(ctx.char(t) + C_HC, p32(r.choice([14, 15, 16])))
        dead = r.randrange(2)
        c.set(cs + CS_ROWS + t * CROW + R_DEAD, p8(dead))
        act = r.choice([ACT_PRAY, ACT_PRAY, ACT_ATTACK, ACT_DEFEND, ACT_NONE])
        c.set(xchar(ctx, t), xrow(1, act if dead else ACT_ATTACK, action=act if not dead else ACT_DEFEND))
        c.set(cs + CS_NEXT_PARTY_ACTION, p32(r.choice([0, 1, 2, 2])) + p32(r.choice([0, 0, 1, 2])))
        c.set(cs + CS_PARTY_ACTION_STATUS, p32(r.choice([0, 0, 1, 2, 3])))
        c.set((ctx.g('g_level_data')).deref() + 1, p8(r.randrange(2)))   # fast-movement bit 0x100
        c.set(tgt, slot_bytes(1, t))
        info.update(char=name, slot=t, act=act, dead=dead)
    else:
        ty = r.choice([0, 2, 4, 5, 6, 7, 8, 9, 10, -1])
        c.set(tgt, slot_bytes(ty, r.randrange(8), 0x7a060))
        info.update(type=ty)
    return tgt, info


def cases_ac_modifier(ctx):
    fn = ctx.fn(0x005468d0)   # int GetTargetArmorClassModifier(W8CombatSlot*, W8AttackMode)
    for i in range(ctx.n(300)):
        r = ctx.rng('acmod', i)
        c = ctx.case('acmod.%d' % i, fn, conv='c', ret='i')
        tgt, info = ac_target(ctx, c, r, ('monster', 'monster', 'char', 'char', 'other'))
        mode = r.choice(list(range(-1, 10)) + [100, 0x7fffffff])
        c.arg(tgt).arg(mode)
        c.note(mode=mode, **info)


def cases_target_ac(ctx):
    fn = ctx.fn(0x00542ee0)   # int GetTargetArmorClass(W8CombatSlot*, W8AttackMode)
    for i in range(ctx.n(250)):
        r = ctx.rng('targetac', i)
        c = ctx.case('targetac.%d' % i, fn, conv='c', ret='i')
        tgt, info = ac_target(ctx, c, r, ('monster', 'monster', 'char'))
        mode = r.choice(list(range(-1, 10)))
        c.arg(tgt).arg(mode)
        c.note(mode=mode, **info)


def cases_target_ac_location(ctx):
    fn = ctx.fn(0x00542fc0)   # int TargetArmorClassAtLocation(W8CombatSlot*, W8AttackMode, int)
    for i in range(ctx.n(300)):
        r = ctx.rng('targetacloc', i)
        c = ctx.case('targetacloc.%d' % i, fn, conv='c', ret='i')
        tgt, info = ac_target(ctx, c, r, ('monster', 'monster', 'char'))
        mode = r.randrange(9)
        loc = r.randrange(7) if info['kind'] == 'monster' else r.randrange(5)
        c.arg(tgt).arg(mode).arg(loc)
        c.note(mode=mode, location=loc, **info)


def cases_blocked(ctx, items):
    fn = ctx.fn(0x00543110)   # bool BlockedForSpecialReason(int, W8CombatSlot*, int, int, unsigned)
    for i in range(ctx.n(250)):
        r = ctx.rng('blocked', i)
        c = ctx.case('blocked.%d' % i, fn, conv='c', ret='b')
        cs = set_cstate(c, ctx)
        set_verbose(c, ctx, 0)
        if r.random() < 0.4:
            c.set(cs + CS_UNAWARE, p8(r.randrange(2)) + p8(r.randrange(2)))
        tgt = tgt_addr(ctx)
        k = r.random()
        armor = r.randint(-20, 60)
        if k < 0.6:
            t = r.randrange(8)
            (_, blob, name), = ctx.set_party(c, r, slots=[t])
            shield = pick(r, [0, 0, 1, 2, 3, -1, 10], -3, 12)
            c.set(ctx.char(t) + C_ACCOMP + 12, p32(shield))
            if r.random() < 0.5:
                c.set(ctx.char(t) + C_EQUIP + 7 * EQ_STEP, p32(r.choice(items + [-1, -1])))
            margin = shield * 5 + r.choice([-6, -1, 0, 0, 1, 2, 10, r.randint(-30, 30)])
            c.set(tgt, slot_bytes(1, t))
            desc = 'char%d' % t
        elif k < 0.95:
            w = World(ctx, c)
            rec = new_record(r)
            rec.u8(R_FLAGS, r.choice([0, FLAG_BEHIND, FLAG_BEHIND, 0xff, 0xfd, r.randrange(256)]))
            w.add_rec(SPECIES[1], rec)
            w.add_mon(new_monster(r, 0x7a070, SPECIES[1]))
            w.emit()
            margin = r.choice([9, 10, 10, 11, -5, 0, 30, r.randint(-30, 30)])
            c.set(tgt, slot_bytes(3, -1, 0x7a070))
            desc = 'monster'
        else:
            ty = r.choice([0, 2, 4, 9])
            margin = 0
            c.set(tgt, slot_bytes(ty, 0, 0x7a070))
            desc = 'type%d' % ty
        attack = armor + margin
        wclass = r.choice([0, 1, 5, 10, 27, 28, -1, r.randrange(28)])
        palette = r.choice([0, 9, 12])
        c.arg(wclass).arg(tgt).arg(attack).arg(armor).arg(palette)
        cap_cstate(c, ctx)
        c.note(target=desc, attack=attack, armor=armor, weapon_class=wclass)


def cases_cap_damage(ctx):
    fn = ctx.fn(0x00545a00)   # unsigned CapAttackDamageByTargetHealth(unsigned)
    for i in range(ctx.n(250)):
        r = ctx.rng('capdmg', i)
        c = ctx.case('capdmg.%d' % i, fn, conv='c', ret='i')
        cs = set_cstate(c, ctx)
        k = r.random()
        hp = pick(r, [0, 1, 4, 5, 9, 10, 11, 14, 15, 1000, -1, -5, 0x7fffffff, -0x80000000], 1, 600, 0.5)
        if k < 0.5:
            t = r.randrange(8)
            ctx.set_party(c, r, slots=[t])
            c.set(ctx.char(t) + C_HPMAX, p32(hp))
            c.set(cs + CS_TARGET_HIT, slot_bytes(1, t))
            desc = 'char%d' % t
        elif k < 0.9:
            w = World(ctx, c)
            w.add_rec(SPECIES[2], new_record(r))
            m = new_monster(r, 0x7a080, SPECIES[2])
            m.u32(M_HPMAX, hp)
            w.add_mon(m)
            w.emit()
            c.set(cs + CS_TARGET_HIT, slot_bytes(3, -1, 0x7a080))
            desc = 'monster'
        else:
            ty = r.choice([0, 2, 4, 9])
            c.set(cs + CS_TARGET_HIT, slot_bytes(ty, 0, 0x7a080))
            desc = 'type%d' % ty
        lim = (hp & M32) // 5
        dmg = pick(r, [0, 1, 2, lim, lim + 1, max(lim - 1, 0), 0x7fffffff, 0x80000000, M32], 0, 300, 0.6)
        c.arg(dmg)
        c.note(target=desc, max_hp=hp, damage=dmg)


def cases_hand_attack_mode(ctx, weapons):
    fn = ctx.fn(0x00542ca0)   # W8AttackMode CharChooseHandAttackMode(W8Character*, int)
    for i in range(ctx.n(250)):
        r = ctx.rng('handmode', i)
        c = ctx.case('handmode.%d' % i, fn, conv='c', ret='i')
        slot = r.randrange(8)
        (_, blob, name), = ctx.set_party(c, r, slots=[slot])
        hand = r.randrange(2)
        base = C_HAND + hand * HAND_STEP
        if r.random() < 0.5:
            blob.u32(base + H_HOLDS, 0)
            m = attack_mask(r) & 0xffff
            blob.u16(base + H_FLAGS, m)
            desc = 'unarmed 0x%x' % m
        else:
            blob.u32(base + H_HOLDS, r.choice([1, 1, 2, 3]))
            wid = r.choice(weapons)
            blob.u32(C_EQUIP + (6 + hand) * EQ_STEP, wid)
            desc = 'item %d' % wid
        put(c, ctx, slot, blob, [HANDS, WEAPON_SLOTS])
        c.arg(ctx.char(slot)).arg(hand)
        c.note(char=name, slot=slot, hand=hand, modes=desc)


def cases_spell_target_string(ctx):
    fn = ctx.fn(0x00546b40)   # wchar_t* SpellTargetString(W8TargetSource*, W8CombatSlot*)
    for i in range(ctx.n(250)):
        r = ctx.rng('targetstr', i)
        c = ctx.case('targetstr.%d' % i, fn, conv='c', ret='w', out='w')
        party = ctx.set_party(c, r)
        for s, blob, _ in party:
            if r.random() < 0.1:
                c.set(ctx.char(s) + C_GENDER, p32(r.randrange(4)))
        w = World(ctx, c)
        rid0 = 397 if r.random() < 0.1 else None
        recs = [new_record(r, rid0), new_record(r)]
        if rid0 == 397:
            c.set(ctx.g('g_status') + GS_SEDEXUS, p32(r.randrange(8)))
        w.add_rec(SPECIES[3], recs[0])
        w.add_rec(SPECIES[4], recs[1])
        for k in range(2):
            g = Blob(GROUP_SIZE)
            g.u32(0, 0x7b000 + k)
            g.u32(G_MEMBERS, r.choice([1, 1, 2, 5, 0]))
            g.u32(G_SPECIES, SPECIES[3 + r.randrange(2)])
            g.u8(G_ALTNAME, r.randrange(2))
            w.add_group(g)
        for k in range(2):
            m = new_monster(r, 0x7a090 + k, SPECIES[3 + k], group=0x7b000 + r.randrange(2))
            w.add_mon(m)
        w.emit(monster_list=True, group_list=True)
        tgt = tgt_addr(ctx)
        sa = src_addr(ctx)
        ty = r.choice([1, 1, 1, 1, 9, 3, 3, 3, 3, 4, 4, 4, 7, 7, 0, 6, 2, 5, 8, 10, 11, -1])
        if ty in (1, 9):
            tb = slot_bytes(ty, r.randrange(8))
        elif ty == 3:
            tb = slot_bytes(3, -1, 0x7a090 + r.randrange(2))
        elif ty == 4:
            tb = slot_bytes(4, -1, -1, 0x7b000 + r.randrange(2))
        else:
            tb = slot_bytes(ty, r.randrange(8), 0x7a090, 0x7b000)
        c.set(tgt, tb)
        if ty == 7:
            s = r.randrange(8)
            eq = [k for k in range(12) if party[s][1].get_i32(C_EQUIP + k * EQ_STEP) != -1]
            k = r.choice(eq) if eq else None
            if k is None:
                c.set(ctx.char(s) + C_EQUIP + 4 * EQ_STEP, p32(1))
                k = 4
            item = ctx.char(s) + C_EQUIP + k * EQ_STEP
            c.set(item + 6, p8(r.randrange(2)))       # identified / generic name
            c.setp(tgt + 0x1c, item)
        sk = r.random()
        tchar = struct.unpack_from('<i', tb, 4)[0]
        tmon = struct.unpack_from('<i', tb, 8)[0]
        if sk < 0.4:
            src = source_bytes(1, tchar if r.random() < 0.5 else r.randrange(8),
                               name_known=r.choice([0, 0, 1]))
        elif sk < 0.75:
            src = source_bytes(2, -1, tmon if r.random() < 0.5 else 0x7a090 + r.randrange(2))
        elif sk < 0.9:
            src = source_bytes(3, tchar, tmon, reflection=1)
        else:
            src = source_bytes(0)
        c.set(sa, src)
        c.arg(sa).arg(tgt)
        c.note(target_type=ty, source_type=struct.unpack_from('<i', src, 0)[0])


def cases_notices_attacker(ctx):
    fn = ctx.fn(0x0053d590)   # bool CharacterNoticesAttacker(int)
    for i in range(ctx.n(250)):
        r = ctx.rng('notices', i)
        c = ctx.case('notices.%d' % i, fn, conv='c', ret='b')
        cs = set_cstate(c, ctx)
        slot = r.randrange(8)
        (_, blob, name), = ctx.set_party(c, r, slots=[slot])
        ch = ctx.char(slot)
        if r.random() < 0.08:
            c.set(ch + C_HP, p32(0))
        if r.random() < 0.08:
            c.set(ch + C_STAM, p32(r.choice([0, 0, -1, -50])))
        if r.random() < 0.3:
            c.set(ch + C_HC, p32(r.choice([0, 1, 12, 13, 13, 14, 15, 18])))
        if r.random() < 0.1:
            c.set(ch + C_COND + COND_BLIND * 4, p32(r.choice([1, 9999, 0x80000000])))
        senses = pick(r, [0, 1, 24, 25, 26, 49, 50, 51, 75, 100, 125, 200], 0, 130)
        c.set(ch + C_ATTR + A_SENSES * ATTR_STEP + ATTR_EFF, p32(senses))
        spot = pick(r, [0, 0, 0, 1, 1, 2, 3, 4, 5, -1, -4, 100, 0x7fffffff], 0, 6, 0.7)
        dead = 1 if r.random() < 0.5 else 0
        rowb = bytearray(CROW)
        rowb[R_DEAD] = dead
        struct.pack_into('<i', rowb, R_SPOT, spot)
        c.set(cs + CS_ROWS + slot * CROW, bytes(rowb))
        if dead:
            pending = r.choice([ACT_DEFEND, ACT_PROTECT, ACT_ATTACK, ACT_NONE, ACT_PRAY])
            row = xrow(1, pending, action=r.choice([ACT_ATTACK, ACT_DEFEND, ACT_PROTECT]))
        else:
            # only DEFEND: any other action would ask CharacterCanSwitchTo (UI targeting state)
            pending = ACT_DEFEND
            row = xrow(1, r.choice([ACT_NONE, ACT_ATTACK, ACT_DEFEND]), action=ACT_DEFEND,
                       target_ic=slot_bytes(1, r.randrange(8)))
        c.set(xchar(ctx, slot), row)
        c.arg(slot)
        cap_cstate(c, ctx)
        cap_xchar(c, ctx, [slot])
        c.note(char=name, slot=slot, dead=dead, senses=senses, spot=spot, pending=pending)


def cases(ctx):
    items, weapons = corpus_tables(ctx)
    cases_hand_dice(ctx, items)
    cases_hand_damage_bonus(ctx)
    cases_clear_block(ctx)
    cases_normalize_cycle(ctx)
    cases_choose_attack_mode(ctx)
    cases_can_character_attack(ctx)
    cases_monster_protect(ctx)
    cases_apply_damage_reduction(ctx)
    cases_rate_monster_attack(ctx)
    cases_rate_best_attack(ctx)
    cases_hand_reach(ctx, items)
    cases_char_damage_reduction(ctx)
    cases_berserk(ctx, items)
    cases_has_attack_on(ctx)
    cases_protect_combatant(ctx)
    cases_protect_target(ctx)
    cases_guardian(ctx, items)
    cases_attack_its_target(ctx, items)
    cases_choose_hand(ctx, items)
    cases_ac_modifier(ctx)
    cases_hand_attack_mode(ctx, weapons)
    cases_spell_target_string(ctx)
    cases_target_ac(ctx)
    cases_target_ac_location(ctx)
    cases_blocked(ctx, items)
    cases_cap_damage(ctx)
    cases_notices_attacker(ctx)
    for c in ctx.cases:
        if len(c.ops) > MAX_OPS:
            raise ValueError('%s: %d ops > %d' % (c.id, len(c.ops), MAX_OPS))
        if len(c.args) > 16:
            raise ValueError('%s: too many args' % c.id)
