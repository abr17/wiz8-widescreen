"""Combat Attack.cpp, lines 2201-4500: attack scores, damage resolution, the
condition pass and the missile scatter.

Tested functions (retail address, name, cases at scale 1.0):
  0x00541c00 GetTargetAttackAttributes        400  cdecl int(slot, hand, mode, char ignore)
  0x00541ec0 GetTargetHitAttackAttributes     400  cdecl int(slot, hand, mode, hit_location)
  0x005420b0 ResolveCharacterAttackDamage     400  cdecl int(slot, hand, mode, u32* dice, u8* hit)
  0x00542720 GetMonsterAttackScore            300  cdecl int(info*, attack*, mode, char ignore)
  0x00542960 ResolveMonsterAttackDamage       300  cdecl int(info*, attack*, u32* dice)
  0x00543270 ApplyEffectConditions            220  cdecl void(source*, target*, def*, announce, verbose, result*)
  0x005454c0 ScatterMissileAimPoint           400  cdecl void(const vec3* from, vec3* to, int accuracy, bool blind)
  0x0053d870 StartCharacterAttack             150  cdecl bool(slot, mode) - only the two early exits
                                                   (hand not in play / no attacks left), which return
                                                   before targeting, notices and missiles
  total 2570

Skipped (one line each):
  0x00541630 AnnounceMonsterAttack     - builds and shows a notice, highlights text, turns the monster (UI + 3D world)
  0x00543dc0 BuildCharacterTargetList  - not in the port map (inlined), cannot be called
  0x00544010 BuildMonsterTargetList    - not in the port map (inlined), cannot be called
  0x00544250 AnnounceAccidentalStrike  - notice text + ShowNotice/HighlightTextBoxRange (UI)
  0x00544530 QueueFumbleReaction       - not in the port map (inlined); only queues voice events
  0x00544630 FireMissileSourceToTarget - creates world missiles, camera, line-of-sight on live 3D state
  0x00544b60 FireCharacterItemMissile  - fires a world missile (FireMissileSourceToTarget)
  0x0053e250 ResolveCharacterAttack    - full swing: sounds, notices, animations, item consumption, missiles

How the state is controlled:
  * g_combat_state is pointed at a W8CombatState built in scratch 0 (setp); every field the
    functions read (unaware, natural_attack, TargetHit, party action, the rows' dead flag,
    equip slots, repick counts) is written explicitly.
  * Monster targets/attackers are fake: gXStatus.plsMonsterList (and plsMonsterGroupList) are
    pointed at a W8PList in scratch 2/6 whose entries are W8MonsterInfo records in scratch 3
    (combat states in scratch 4), and gXStatus.monster_record_cache[990+k] at W8MonsterRecords
    in scratch 5, so MonsterGetIndexByLocationID/GetMonsterDataForInfo resolve to them.
    No path used here touches the monster's p3D.
  * Difficulty (g_settings.difficulty), verbose combat messages, gXStatus.fCombatMode and the
    level fast-movement flag (g_level_data->flags) are set in every case.
  * TryCharacterAction(DEFEND/PROTECT, commit) is only reached with the target's combat row
    'dead' latch set, with XChar.action == DEFEND, or with an incapacitated target, so the
    complex CharacterCanSwitchTo path (screen/UI state) is never entered.
  * IRON_SKIN / IRON_WILL practice counters are zeroed so PracticeCharacterSkill can never level
    a skill (that path may open a message box).
  * Equipment consistency: a hand that holds something always has its weapon slot filled, and a
    character whose primary weapon may pair with an empty secondary slot fights unarmed, so
    g_item_records[-1] (heap garbage) is never read.

Side effects that are not captured (accepted): QueueCharacterEvent voice events (multi-dice hits,
condition reactions), text-box notices from ApplyEffectConditions, RequestRedraw flags.

Not reachable safely (noted, not tested): ApplyEffectConditions' KILL effect for a character that
fails the save (CharacterDies) and therefore the "killing blow" merge branch; SWALLOW/POSSESS with
a monster source; condition effects on monster targets (SetMonsterCondition needs the 3D monster)."""
import struct

CHAR = 0x1862
ROW = 0x106              # W8PartySlotRow (XChar)

# W8Character
C_NAME = 0x5
C_PROF = 0x69
C_RACE = 0x71
C_EXPLEVEL = 0x89
C_PROF_LEVELS = 0x8d
C_ATTR = 0xe5            # W8CharacterAttribute[7], stride 0x14, effective at +4
C_SKILL = 0x19d          # W8CharacterSkill[0x29], stride 0x26: active +0, practice_count +0xe
C_COND = 0xa01           # uiCondition[20]
C_HIGHEST = 0xb01
C_HPMAX = 0xb0d
C_HP = 0xb11
C_STAMINA = 0xb1d
C_SP_LEFT = 0xb45
C_AC_TOTAL = 0xe85
C_AC_COMP = 0xe8d        # armor_class_components[13]
C_AC_LOC = 0xec1         # armor_class_by_location[5]
C_DR = 0xed9
C_RESIST = 0xedd         # W8CharacterResistance[6], total at +4
C_EQ = 0xf5d             # W8ItemInstance[12], iItemNo at +0
C_HAND = 0x1149          # W8HandAttack[2], stride 0x5b
H_HOLDS, H_INPLAY, H_WSKILL, H_CSKILL = 0x0, 0x4, 0x5, 0x9
H_SCORE, H_SWINGS, H_HIT, H_ATK, H_DPCT, H_DICE, H_FLAGS = 0x11, 0x19, 0x21, 0x25, 0x29, 0x2d, 0x31
C_FATIGUE = 0x169e
C_BONUS = 0x1770         # W8GameplayModifierBlock: hit +1, attack +2, damage% +3, out_of_formation +0x45
SKILL_STEP = 0x26
SK_IRON_WILL = 0x24
SK_IRON_SKIN = 0x25
A_INT, A_VIT, A_DEX, A_SPEED, A_SENSES = 1, 3, 4, 5, 6
COND_BLIND, COND_TURNCOAT, COND_ASLEEP, COND_DEAD, COND_MISSING = 12, 13, 15, 18, 19

# W8PartySlotRow
X_OCC, X_PENDING, X_MODES, X_TARGET, X_ACTION = 0x0, 0x1, 0x5, 0x1d, 0x3d
X_PTR_FIELDS = [0x19, 0x39]          # item pointers inside the first 0x3d bytes

# W8CombatState (0xa64)
CS_SIZE = 0xa64
CS_ROWS, CS_ROW = 0x18, 0xd4
R_DEAD, R_SAVED, R_HANDVAL, R_HAND, R_EQUIP, R_PAIRED, R_SPOT, R_REPICK = (
    0x34, 0x38, 0x40, 0x6c, 0x70, 0x74, 0x90, 0x94)
CS_TARGETHIT = 0x8c5
CS_NEXT_PA, CS_CUR_PA, CS_PA_STATUS = 0x90c, 0x910, 0x918
CS_UNAWARE, CS_NATURAL, CS_REPORT = 0x9a4, 0x9a5, 0x9a6
REPORT_SIZE = 0xa2

# W8MonsterInfo (0x425) / W8MonsterCombatState (0x153) / W8MonsterRecord (0x297)
MI_SIZE = 0x425
M_LOC, M_GROUP, M_SPECIES, M_COMBAT = 0x0, 0x4, 0x8, 0x10
M_ACTIVE, M_INCOMBAT, M_DISP, M_HP, M_STAMINA = 0x14, 0x15, 0x16, 0x2b, 0x33
M_COND, M_HIGHEST, M_MODS, M_FATIGUE, M_ATTR = 0x57, 0x107, 0x1db, 0x242, 0x247
M_TARGET, M_ACTION, M_DETAIL = 0x2ba, 0x2e1, 0x2e5
MC_SIZE = 0x153
MC_SWINGS, MC_ATTACK, MC_SPOT, MC_REPICK = 0xd, 0x11, 0x13d, 0x141
MR_SIZE = 0x297
R_KIND, R_DRED, R_FLAGS, R_ATTACKS = 0xcb, 0xcf, 0xd0, 0xe7
R_EVASION, R_AC_LOC, R_AC_MODE, R_RES, R_IDI, R_LEVEL = 0x15d, 0x166, 0x16d, 0x176, 0x1be, 0x24f
ATTACK_SIZE = 0x22       # W8MonsterAttack: name idx +1, type +2, range +3, score +4, dice +0x17
SPECIES0 = 990           # fake species ids (cache slots 990..997)

# W8SpellEffectDefinition (0x30) / W8SpellEffectResult (0xa2)
DEF_SIZE = 0x30
RES_SIZE = 0xa2
RES_PTR_FIELDS = [0x58, 0x5c, 0x60, 0x64]   # the reports vector

# globals
S_DIFFICULTY, S_VERBOSE = 0xd, 0x44                     # g_settings
XS_COMBAT_MODE, XS_MLIST, XS_GLIST = 0x8dc, 0x8f5, 0x8f9  # gXStatus
XS_SIGHT, XS_CACHE, XS_ENTRIES, XS_ENTRY = 0xa03, 0xa0f, 0x0, 0x118
ST_SELECTED, ST_SUSPENDED, ST_FORMATION, ST_SKIP_REACT = 0x1d, 0x2390, 0x23a1, 0x2488  # g_status

# 18 natural attack verbs whose fatigue penalty is halved (retail 0x0061d284)
LOW_FATIGUE_VERBS = [0x07, 0x0d, 0x0e, 0x0f, 0x15, 0x19, 0x21, 0x2b, 0x31, 0x32, 0x34, 0x35,
                     0x36, 0x38, 0x3b, 0x55, 0x56, 0x57]

MODES = list(range(9))
# occupied party slots in the 'Before Bayjin' save (the corpus file suffix is the slot; slots 0/1
# are the RPC slots and are empty there)
PCS = [2, 3, 4, 5, 6, 7]


def u32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def i32(v):
    return struct.pack('<i', int(v))


def slot_bytes(kind, ichar=-1, imon=-1, igroup=-1):
    """W8CombatSlot head: iType, iChar, iMonsterID, iGroupID."""
    return struct.pack('<iiii', kind, ichar, imon, igroup)


def emit_diff(c, addr, orig, new, gap=48):
    """set only the changed byte runs of new over orig (merging close runs)."""
    n = len(new)
    i = 0
    while i < n:
        if orig[i] == new[i]:
            i += 1
            continue
        last = i
        j = i + 1
        while j < n and j - last <= gap:
            if orig[j] != new[j]:
                last = j
            j += 1
        c.set(addr + i, bytes(new[i:last + 1]))
        i = last + 1


def emit_struct(c, addr, data, gap=0x400):
    """scratch buffers are zeroed per case: write only the non-zero runs."""
    emit_diff(c, addr, bytes(len(data)), data, gap)


class World:
    """Addresses and per-case helpers shared by all functions."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.cs_ptr = ctx.g('g_combat_state')
        self.settings = ctx.g('g_settings')
        self.xs = ctx.g('gXStatus')
        self.st = ctx.g('g_status')
        self.level = ctx.g('g_level_data')

    def xchar(self, slot):
        return (self.st + 8).deref() + slot * ROW

    def globals(self, c, r, combat_mode=None, difficulty=None, verbose=0):
        d = r.choice([0, 0, 1, 1, 1, 2, 2, 3]) if difficulty is None else difficulty
        cm = r.choice([0, 1]) if combat_mode is None else combat_mode
        c.set(self.settings + S_DIFFICULTY, u32(d))
        c.set(self.settings + S_VERBOSE, bytes([verbose]))
        c.set(self.xs + XS_COMBAT_MODE, bytes([cm]))
        fast = r.choice([0, 0x100])
        c.set(self.level.deref(), u32(fast))
        c.note(difficulty=d, combat_mode=cm, fast_move=fast >> 8)
        return d, cm

    def combat_state(self, c, cs):
        emit_struct(c, self.ctx.scratch(0), cs, gap=0x40)
        c.setp(self.cs_ptr, self.ctx.scratch(0))

    def monsters(self, c, mons, groups=()):
        """mons: list of (info bytes, combat bytes or None, record bytes, species)."""
        ctx = self.ctx
        lst = ctx.scratch(2)
        n = len(mons)
        c.set(lst + 4, struct.pack('<ii', n, n))
        c.setp(lst, lst + 0x10)
        for k, (mi, mc, rec, species) in enumerate(mons):
            base = ctx.scratch(3) + k * 0x500
            c.setp(lst + 0x10 + 4 * k, base)
            emit_struct(c, base, mi, gap=0x80)
            if mc is not None:
                cbase = ctx.scratch(4) + k * 0x200
                emit_struct(c, cbase, mc)
                c.setp(base + M_COMBAT, cbase)
            rbase = ctx.scratch(5) + k * 0x300
            emit_struct(c, rbase, rec, gap=0x80)
            c.setp(self.xs + XS_CACHE + species * 4, rbase)
        c.setp(self.xs + XS_MLIST, lst)
        if groups:
            gl = ctx.scratch(6)
            c.set(gl + 4, struct.pack('<ii', len(groups), len(groups)))
            c.setp(gl, gl + 0x10)
            for k, gid in enumerate(groups):
                gbase = gl + 0x100 + k * 0x40
                c.setp(gl + 0x10 + 4 * k, gbase)
                c.set(gbase, i32(gid))
            c.setp(self.xs + XS_GLIST, gl)

    def monster_info(self, k):
        return self.ctx.scratch(3) + k * 0x500

    def monster_record(self, k):
        return self.ctx.scratch(5) + k * 0x300


def new_cs():
    return bytearray(CS_SIZE)


def cs_row(cs, slot, off, fmt, *vals):
    struct.pack_into(fmt, cs, CS_ROWS + slot * CS_ROW + off, *vals)


def party_action(cs, r):
    struct.pack_into('<i', cs, CS_NEXT_PA, r.choice([0, 0, 1, 2]))
    struct.pack_into('<i', cs, CS_CUR_PA, r.choice([0, 0, 1, 2]))
    struct.pack_into('<i', cs, CS_PA_STATUS, r.choice([0, 0, 1, 3]))


def make_monster(r, loc_id, species, group_id=0):
    mi = bytearray(MI_SIZE)
    struct.pack_into('<iiI', mi, M_LOC, loc_id, group_id, species)
    mi[M_ACTIVE] = 1
    mi[M_INCOMBAT] = 1
    mi[M_DISP] = r.choice([0, 1, 1, 1, 2, 2])
    struct.pack_into('<I', mi, M_HP, r.choice([0, 1, 12, 40, 150, 600]) if r.random() < 0.1 else r.randrange(5, 400))
    struct.pack_into('<i', mi, M_STAMINA, r.randrange(0, 300))
    if r.random() < 0.25:
        struct.pack_into('<I', mi, M_COND + COND_BLIND * 4, r.choice([1, 3, 9999]))
    struct.pack_into('<i', mi, M_HIGHEST, r.choice([0, 0, 0, 0, 4, 12, 15]))
    mods = M_MODS
    mi[mods + 1] = r.choice([0, 0, 1, 3, 5, 10, -3, 127, -128]) & 0xff    # hit_bonus
    mi[mods + 4] = r.choice([0, 0, 1, 2, -2, 5]) & 0xff                    # armor_flat
    mi[mods + 5] = r.choice([0, 0, 1, 3, -3]) & 0xff                       # armor_matchup
    mi[mods + 6] = r.choice([0, 0, 0, 5, 10, 25, -10, 50, 100, -100]) & 0xff  # damage reduction adj
    mi[mods + 0x45] = r.choice([0, 0, 0, 1])                               # out_of_formation
    mi[mods + 0x4b] = r.choice([0, 0, 1, 2, -1, -4, 6]) & 0xff             # armor_class_adjustment
    struct.pack_into('<i', mi, M_FATIGUE, r.choice([0, 0, 1, 2, 3, 4, 5, -1]))
    for a in range(5):
        mi[M_ATTR + a] = r.choice([1, 10, 30, 50, 75, 100, 125, r.randrange(1, 126)])
    struct.pack_into('<i', mi, M_ACTION, r.choice([-1, 0, 0, 1, 1, 2, 3, 4, 4, 5, 6, 7, 8, 8, 9]))
    struct.pack_into('<i', mi, M_DETAIL, r.choice(MODES))
    return mi


def make_monster_combat(r):
    mc = bytearray(MC_SIZE)
    struct.pack_into('<I', mc, MC_SWINGS, r.randrange(1, 4))
    struct.pack_into('<i', mc, MC_SPOT, r.randrange(0, 4))
    struct.pack_into('<I', mc, MC_REPICK, r.choice([0, 0, 0, 1, 2, 3, 5, 0x80000000, 0xffffffff]))
    return mc


def make_record(r):
    rec = bytearray(MR_SIZE)
    rec[R_KIND] = r.choice([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 20, 0xff])
    rec[R_DRED] = r.choice([0, 0, 0, 5, 10, 25, 50, 75, 100, 150, 255])
    rec[R_FLAGS] = r.choice([0, 0, 2, 2, 4, 6, 0x12, 0xff])
    rec[R_EVASION] = r.choice([-10, -5, 0, 0, 2, 5, 8, 12, 15, 30]) & 0xff
    for k in range(7):
        rec[R_AC_LOC + k] = r.choice([-5, -1, 0, 0, 1, 2, 4, 8, 12]) & 0xff
    for k in range(9):
        rec[R_AC_MODE + k] = r.choice([-5, -2, 0, 0, 0, 1, 3, 6]) & 0xff
    for k in range(6):
        rec[R_RES + k] = r.choice([0, 0, 10, 25, 50, 75, 100])
    rec[R_LEVEL] = r.choice([0, 1, 5, 10, 15, 20, 21, 25, 30, 40, 255])
    for j in range(3):
        a = R_ATTACKS + j * ATTACK_SIZE
        rec[a] = 1
        rec[a + 1] = r.choice(LOW_FATIGUE_VERBS + [0, 1, 2, 3, 0x10, 0x20, 0x40, 0x58, 0x5f])
        rec[a + 2] = r.choice([0, 1, 2, 3])
        rec[a + 3] = r.choice([0, 0, 1, 2, 3])
        rec[a + 4] = r.choice([0, 1, 20, 50, 80, 99, 100, 150, 200, 255])
        struct.pack_into('<hBB', rec, a + 0x17, r.choice([-3, 0, 0, 1, 2, 5, 10]),
                         r.choice([0, 1, 1, 2, 3, 4, 6, 10]), r.choice([0, 1, 2, 4, 6, 8, 10, 20]))
    return rec


class Party:
    """Corpus characters placed with setb; field edits are emitted as diffs."""

    def __init__(self, ctx, world, c, r, slots=range(8)):
        self.ctx = ctx
        self.world = world
        self.c = c
        self.members = {}
        for slot, blob, name in ctx.set_party(c, r, slots):
            self.members[slot] = (bytes(blob), blob, name)

    def blob(self, slot):
        return self.members[slot][1]

    def name(self, slot):
        return self.members[slot][2]

    def commit(self):
        for slot, (orig, blob, _) in self.members.items():
            emit_diff(self.c, self.ctx.char(slot), orig, blob)


def get_i32(b, off):
    return struct.unpack_from('<i', b, off)[0]


def get_u32(b, off):
    return struct.unpack_from('<I', b, off)[0]


def fix_holds(b):
    """A hand that holds something must have its weapon slot filled; a filled primary slot
    with an empty secondary slot might be a 'paired' weapon whose partner lookup would read
    g_item_records[-1], so that character fights unarmed with the primary hand."""
    for h in range(2):
        if get_i32(b, C_HAND + h * 0x5b + H_HOLDS) != 0 and get_i32(b, C_EQ + (6 + h) * 12) == -1:
            b.u32(C_HAND + h * 0x5b + H_HOLDS, 0)
    if get_i32(b, C_EQ + 6 * 12) != -1 and get_i32(b, C_EQ + 7 * 12) == -1:
        b.u32(C_HAND + H_HOLDS, 0)


def tweak_attacker(b, r, hand):
    """Edge and realistic values for the hand attack terms, attributes and fatigue."""
    h = C_HAND + hand * 0x5b
    if r.random() < 0.5:
        b.u32(h + H_SCORE, r.choice([-50, 0, 1, 40, 75, 99, 100, 101, 150, 200, 255, r.randrange(30, 180)]))
    if r.random() < 0.4:
        b.u32(h + H_HIT, r.choice([-10, -3, 0, 1, 5, 10, 17, 25]))
    if r.random() < 0.3:
        b.u32(h + H_ATK, r.choice([-5, 0, 1, 3, 8]))
    if r.random() < 0.2:
        b.u32(h + H_WSKILL, r.choice([0, 4, 5, 7, 7, 8, 9, 14, -1]))
    if r.random() < 0.3:
        b.u8(C_BONUS + 1, r.choice([0, 1, 3, 4, 10, -5, 127, -128]))
    if r.random() < 0.3:
        b.u8(C_BONUS + 2, r.choice([0, 1, 2, -3, 20]))
    if r.random() < 0.4:
        b.u32(C_FATIGUE, r.choice([0, 0, 1, 2, 3, 4, 5, -1, 40]))
    for a in (A_INT, A_DEX, A_SPEED, A_SENSES):
        if r.random() < 0.3:
            b.u32(C_ATTR + a * 0x14 + 4, r.choice([0, 1, 15, 50, 75, 100, 125, 126, r.randrange(1, 126)]))
    if r.random() < 0.2:
        b.u32(C_COND + COND_BLIND * 4, r.choice([1, 2, 9999]))
    if r.random() < 0.12:
        b.u32(C_COND + COND_TURNCOAT * 4, r.choice([1, 5]))
    if r.random() < 0.25:
        b.u32(C_PROF, r.choice([6, 6, 7, 7, 0, 3, 5, 14]))   # monk (blind trait), rogue (backstab)
    if r.random() < 0.3:
        prof = get_i32(b, C_PROF)
        if 0 <= prof < 15:
            b.u32(C_PROF_LEVELS + prof * 4, r.choice([0, 1, 5, 10, 19, 20, 21, 30]))


def tweak_defender(b, r):
    """Armour-class terms of a character target."""
    if r.random() < 0.5:
        b.u32(C_AC_TOTAL, r.choice([-10, -1, 0, 1, 3, 5, 8, 12, 18, 30]))
    if r.random() < 0.4:
        b.u32(C_AC_COMP + 1 * 4, r.choice([-3, 0, 1, 2, 5]))
    if r.random() < 0.4:
        b.u32(C_AC_COMP + 3 * 4, r.choice([-3, 0, 1, 2, 4, 7]))
    for k in range(5):
        if r.random() < 0.2:
            b.u32(C_AC_LOC + k * 4, r.choice([-4, 0, 2, 5, 9, 15]))
    if r.random() < 0.25:
        b.u8(C_BONUS + 0x45, r.choice([0, 1, 2]))
    for a in (A_INT, A_DEX, A_SPEED, A_SENSES):
        if r.random() < 0.3:
            b.u32(C_ATTR + a * 0x14 + 4, r.choice([1, 20, 50, 75, 100, 125, r.randrange(1, 126)]))


def target_action_state(r, c, world, party, cs, t, allow_protect_commit=False):
    """The XChar action fields and the combat-row latch TryCharacterAction reads, chosen so
    that CharacterCanSwitchTo is never reached (see module docstring)."""
    b = party.blob(t)
    st = r.choice(['dead_row', 'dead_row', 'defend', 'incap', 'none'])
    if st == 'dead_row':
        cs_row(cs, t, R_DEAD, '<B', 1)
        pending = r.choice([0, 4, 5, 6, 7, -1])
        action = r.choice([0, 4, 5, 6])
    elif st == 'defend':
        pending = r.choice([0, 4, 5])
        action = 4
    elif st == 'incap':
        if r.random() < 0.5:
            b.u32(C_HP, 0)
        else:
            b.u32(C_HIGHEST, r.choice([15, 16, 17, 18]))
        pending = r.choice([4, 5])
        action = r.choice([4, 5])
    else:
        # neither DEFEND nor PROTECT can succeed without the switch check: incapacitate
        b.u32(C_HIGHEST, COND_ASLEEP)
        pending = 0
        action = 0
    c.set(world.xchar(t) + X_PENDING, i32(pending))
    c.set(world.xchar(t) + X_ACTION, i32(action))
    return st


def pray_state(r, c, world, cs, t):
    """XChar fields for TryCharacterAction(t, PRAY, false) (never commits, never switches)."""
    if r.random() < 0.3:
        cs_row(cs, t, R_DEAD, '<B', 1)
    c.set(world.xchar(t) + X_PENDING, i32(r.choice([0, 4, 6, 6, 7])))
    c.set(world.xchar(t) + X_ACTION, i32(r.choice([0, 4, 5, 6, 6, 7])))


def fake_monsters(r, n, groups=False):
    mons = []
    for k in range(n):
        gid = 7000 + k if groups else 0
        mi = make_monster(r, 50000 + k * 17, SPECIES0 + k, gid)
        mons.append((mi, make_monster_combat(r), make_record(r), SPECIES0 + k))
    return mons


def pick_mode(r):
    v = r.random()
    if v < 0.03:
        return r.choice([-1, 9])
    return r.choice(MODES)


# --------------------------------------------------------------------------------------
def cases_target_attack(ctx, w):
    fn = ctx.fn(0x00541c00)
    # surprise = speed - 25*repick - 50 + score hitting perfect 4th powers (pow(s, 0.75) exact)
    exact = [0, 1, 16, 81, 256, 625]
    for i in range(ctx.n(400)):
        r = ctx.rng('gtaa', i)
        c = ctx.case('get_target_attack_attributes.%d' % i, fn, conv='c', ret='i')
        party = Party(ctx, w, c, r)
        a = r.choice(PCS + PCS + [0, 1])
        hand = r.choice([0, 0, 1])
        mode = pick_mode(r)
        _, cm = w.globals(c, r)
        b = party.blob(a)
        tweak_attacker(b, r, hand)
        cs = new_cs()
        cs[CS_UNAWARE] = r.choice([0, 0, 1, 2])
        cs[CS_NATURAL] = r.choice([0, 0, 1])
        repick = r.choice([0, 0, 0, 1, 2, 3, 10, 0x7fffffff, 0xffffffff])
        if repick in (1, 2) and r.random() < 0.5:
            speed = r.randrange(20, 126)
            b.u32(C_ATTR + A_SPEED * 0x14 + 4, speed)
            b.u32(C_HAND + hand * 0x5b + H_SCORE, r.choice(exact) - speed + 25 * repick + 50)
        cs_row(cs, a, R_REPICK, '<I', repick)
        party_action(cs, r)
        ignore = r.choice([0, 0, 0, 1, 1, 0x100, 0xff00])
        kind = r.choice(['char', 'char', 'char', 'char', 'mon', 'mon', 'mon', 'self'])
        if (ignore & 0xff) and r.random() < 0.3:
            kind = 'junk'
        if kind in ('char', 'self'):
            t = a if kind == 'self' else r.choice([s for s in range(8) if s != a])
            tweak_defender(party.blob(t), r)
            pray_state(r, c, w, cs, t)
            c.set(w.xchar(a) + X_TARGET, slot_bytes(1, t))
            c.note(target='char%d' % t)
        elif kind == 'mon':
            mons = fake_monsters(r, r.randrange(1, 4))
            k = r.randrange(len(mons))
            w.monsters(c, mons)
            c.set(w.xchar(a) + X_TARGET, slot_bytes(3, -1, get_i32(mons[k][0], M_LOC)))
            c.note(target='monster%d' % k)
        else:
            c.set(w.xchar(a) + X_TARGET, slot_bytes(r.choice([0, 2, 6]), r.randrange(8), 12345))
            c.note(target='other-type (ignored)')
        party.commit()
        w.combat_state(c, cs)
        c.arg(a).arg(hand).arg(mode).arg(ignore)
        c.cap(ctx.scratch(0), CS_SIZE, 'combat')
        c.note(char=party.name(a), slot=a, hand=hand, mode=mode, ignore=ignore, repick=repick)


def cases_target_hit(ctx, w):
    fn = ctx.fn(0x00541ec0)
    for i in range(ctx.n(400)):
        r = ctx.rng('gthaa', i)
        c = ctx.case('get_target_hit_attack_attributes.%d' % i, fn, conv='c', ret='i')
        party = Party(ctx, w, c, r)
        a = r.choice(PCS + PCS + [0, 1])
        hand = r.choice([0, 0, 1])
        mode = pick_mode(r)
        w.globals(c, r)
        b = party.blob(a)
        tweak_attacker(b, r, hand)
        cs = new_cs()
        cs[CS_UNAWARE] = r.choice([0, 0, 1])
        cs[CS_NATURAL] = r.choice([0, 0, 1])
        party_action(cs, r)
        if r.random() < 0.55:
            t = r.choice(range(8))
            tweak_defender(party.blob(t), r)
            pray_state(r, c, w, cs, t)
            cs[CS_TARGETHIT:CS_TARGETHIT + 16] = slot_bytes(1, t)
            loc = r.choice([0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 5, 6, -1]) if r.random() < 0.1 else r.randrange(5)
            c.note(target='char%d' % t)
        else:
            mons = fake_monsters(r, r.randrange(1, 4))
            k = r.randrange(len(mons))
            w.monsters(c, mons)
            cs[CS_TARGETHIT:CS_TARGETHIT + 16] = slot_bytes(3, -1, get_i32(mons[k][0], M_LOC))
            loc = r.choice([7, 8]) if r.random() < 0.05 else r.randrange(7)
            c.note(target='monster%d' % k)
        party.commit()
        w.combat_state(c, cs)
        c.arg(a).arg(hand).arg(mode).arg(loc)
        c.cap(ctx.scratch(0), CS_SIZE, 'combat')
        c.note(char=party.name(a), slot=a, hand=hand, mode=mode, hit_location=loc)


def random_dice(r):
    return struct.pack('<hBB', r.choice([-3, 0, 0, 1, 2, 5, 20]), r.choice([0, 1, 1, 2, 3, 5, 10, 40]),
                       r.choice([0, 1, 2, 3, 4, 6, 8, 10, 20, 255]))


def cases_char_damage(ctx, w):
    fn = ctx.fn(0x005420b0)
    for i in range(ctx.n(400)):
        r = ctx.rng('rcad', i)
        c = ctx.case('resolve_character_attack_damage.%d' % i, fn, conv='c', ret='i')
        party = Party(ctx, w, c, r)
        a = r.choice(PCS)          # multi-dice hits queue a voice event: occupied slots only
        hand = r.choice([0, 0, 1])
        mode = pick_mode(r)
        w.globals(c, r)
        b = party.blob(a)
        fix_holds(b)
        h = C_HAND + hand * 0x5b
        if r.random() < 0.25:
            b.u32(h + H_HOLDS, 0)
        for hh in range(2):
            if r.random() < 0.5:
                b[C_HAND + hh * 0x5b + H_DICE:C_HAND + hh * 0x5b + H_DICE + 4] = random_dice(r)
        if r.random() < 0.5:
            b.u32(h + H_DPCT, r.choice([-100, -50, -25, 0, 10, 50, 100, 150, 300]))
        if r.random() < 0.3:
            b.u8(C_BONUS + 3, r.choice([0, 5, 20, -20, 127, -128]))
        if r.random() < 0.3:
            b.u32(C_PROF, r.choice([7, 7, 0, 5, 6]))
        if r.random() < 0.3:
            prof = get_i32(b, C_PROF)
            if 0 <= prof < 15:
                b.u32(C_PROF_LEVELS + prof * 4, r.choice([0, 1, 5, 10, 20, 21, 30]))
        cs = new_cs()
        cs[CS_UNAWARE] = r.choice([0, 0, 1])
        cs[CS_NATURAL] = r.choice([0, 0, 0, 1])
        party_action(cs, r)
        cs_row(cs, a, R_EQUIP, '<i', 6 + hand)
        paired = -1
        if hand == 0 and get_i32(b, C_EQ + 7 * 12) != -1 and r.random() < 0.3:
            paired = 7
        cs_row(cs, a, R_PAIRED, '<i', paired)
        caps = []
        if r.random() < 0.5:
            t = r.choice([s for s in range(8) if s != a] + [a])
            tb = party.blob(t)
            tb.u32(C_SKILL + SK_IRON_SKIN * SKILL_STEP + 0xe, 0)
            if r.random() < 0.4:
                tb.u8(C_SKILL + SK_IRON_SKIN * SKILL_STEP, r.choice([0, 1]))
            if r.random() < 0.5:
                tb.u32(C_DR, r.choice([0, 0, 5, 10, 25, 50, 99, 100, 101, 150, -20]))
            if r.random() < 0.3:
                tb.u8(C_BONUS + 0x45, r.choice([0, 1]))
            st = target_action_state(r, c, w, party, cs, t)
            cs[CS_TARGETHIT:CS_TARGETHIT + 16] = slot_bytes(1, t)
            caps.append(('char', t))
            c.note(target='char%d' % t, target_state=st)
        else:
            mons = fake_monsters(r, r.randrange(1, 4))
            k = r.randrange(len(mons))
            w.monsters(c, mons)
            cs[CS_TARGETHIT:CS_TARGETHIT + 16] = slot_bytes(3, -1, get_i32(mons[k][0], M_LOC))
            c.note(target='monster%d' % k)
        party.commit()
        w.combat_state(c, cs)
        out = ctx.scratch(1)
        c.arg(a).arg(hand).arg(mode).arg(out).arg(out + 4)
        c.cap(out, 8, 'out_dice_hit')
        c.cap(ctx.scratch(0), CS_SIZE, 'combat')
        c.cap(ctx.char(a), CHAR, 'attacker')
        for _, t in caps:
            if t != a:
                c.cap(ctx.char(t), CHAR, 'target')
            c.cap(w.xchar(t), X_ACTION, 'target_row', ignore=X_PTR_FIELDS)
        c.note(char=party.name(a), slot=a, hand=hand, mode=mode, paired=paired)


def cases_monster_score(ctx, w):
    fn = ctx.fn(0x00542720)
    exact = [0, 1, 16, 81, 256]
    for i in range(ctx.n(300)):
        r = ctx.rng('gmas', i)
        c = ctx.case('get_monster_attack_score.%d' % i, fn, conv='c', ret='i')
        party = Party(ctx, w, c, r)
        null_cs = r.random() < 0.15
        _, cm = w.globals(c, r, combat_mode=0 if null_cs else None)
        mons = fake_monsters(r, r.randrange(1, 4))
        mi, mc, rec, _ = mons[0]
        j = r.randrange(3)
        attack_off = R_ATTACKS + j * ATTACK_SIZE
        repick = get_u32(mc, MC_REPICK)
        if repick in (1, 2) and r.random() < 0.6:
            speed = r.randrange(20, 126)
            mi[M_ATTR + 3] = speed
            rec[attack_off + 4] = max(0, min(255, r.choice(exact) - speed + (repick * 5 + 10) * 5))
        ignore = r.choice([0, 0, 0, 1, 0x100])
        cs = new_cs()
        cs[CS_UNAWARE] = r.choice([0, 0, 1])
        cs[CS_NATURAL] = r.choice([0, 0, 1])
        party_action(cs, r)
        kind = r.choice(['char', 'char', 'mon', 'self'])
        if kind == 'char':
            t = r.randrange(8)
            tweak_defender(party.blob(t), r)
            pray_state(r, c, w, cs, t)
            mi[M_TARGET:M_TARGET + 16] = slot_bytes(1, t)
        else:
            k = 0 if kind == 'self' or len(mons) == 1 else r.randrange(1, len(mons))
            mi[M_TARGET:M_TARGET + 16] = slot_bytes(3, -1, get_i32(mons[k][0], M_LOC))
        w.monsters(c, mons)
        party.commit()
        if null_cs:
            c.set(w.cs_ptr, u32(0))
        else:
            w.combat_state(c, cs)
            c.cap(ctx.scratch(0), CS_SIZE, 'combat')
        mode = pick_mode(r)
        c.arg(w.monster_info(0)).arg(w.monster_record(0) + attack_off).arg(mode).arg(ignore)
        c.cap(w.monster_info(0), MI_SIZE, 'monster', ignore=[M_COMBAT])
        c.note(target=kind, mode=mode, ignore=ignore, null_combat_state=null_cs, attack=j,
               repick=repick)


def cases_monster_damage(ctx, w):
    fn = ctx.fn(0x00542960)
    for i in range(ctx.n(300)):
        r = ctx.rng('rmad', i)
        c = ctx.case('resolve_monster_attack_damage.%d' % i, fn, conv='c', ret='i')
        party = Party(ctx, w, c, r)
        w.globals(c, r)
        n = r.randrange(1, 4) if r.random() < 0.5 else 2
        mons = fake_monsters(r, n, groups=True)
        mi = mons[0][0]
        struct.pack_into('<i', mi, M_DETAIL, pick_mode(r))
        j = r.randrange(3)
        attack_off = R_ATTACKS + j * ATTACK_SIZE
        cs = new_cs()
        cs[CS_UNAWARE] = r.choice([0, 0, 1])
        cs[CS_NATURAL] = r.choice([0, 0, 0, 1])
        party_action(cs, r)
        caps = []
        if r.random() < 0.55:
            t = r.randrange(8)
            tb = party.blob(t)
            tb.u32(C_SKILL + SK_IRON_SKIN * SKILL_STEP + 0xe, 0)
            if r.random() < 0.4:
                tb.u8(C_SKILL + SK_IRON_SKIN * SKILL_STEP, r.choice([0, 1]))
            if r.random() < 0.5:
                tb.u32(C_DR, r.choice([0, 0, 5, 10, 25, 50, 99, 100, 101, 150, -20]))
            if r.random() < 0.3:
                tb.u8(C_BONUS + 0x45, r.choice([0, 1]))
            st = target_action_state(r, c, w, party, cs, t)
            cs[CS_TARGETHIT:CS_TARGETHIT + 16] = slot_bytes(1, t)
            caps.append(t)
            c.note(target='char%d' % t, target_state=st)
        else:
            k = r.randrange(len(mons))
            cs[CS_TARGETHIT:CS_TARGETHIT + 16] = slot_bytes(3, -1, get_i32(mons[k][0], M_LOC))
            c.note(target='monster%d' % k)
        w.monsters(c, mons, groups=[7000 + k for k in range(len(mons))])
        party.commit()
        w.combat_state(c, cs)
        out = ctx.scratch(1)
        c.arg(w.monster_info(0)).arg(w.monster_record(0) + attack_off).arg(out)
        c.cap(out, 4, 'out_dice')
        c.cap(ctx.scratch(0), CS_SIZE, 'combat')
        for t in caps:
            c.cap(ctx.char(t), CHAR, 'target')
            c.cap(w.xchar(t), X_ACTION, 'target_row', ignore=X_PTR_FIELDS)
        c.note(attack=j, mode=get_i32(mi, M_DETAIL))


# allowed condition-effect indexes for a character target hit by a character source:
# everything except KILL (5); SWALLOW (9) / POSSESS (10) only roll (monster source required)
EFFECTS_SAFE = [0, 1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]


def cases_effect_conditions(ctx, w):
    fn = ctx.fn(0x00543270)
    for i in range(ctx.n(220)):
        r = ctx.rng('aec', i)
        c = ctx.case('apply_effect_conditions.%d' % i, fn, conv='c', ret='v')
        party = Party(ctx, w, c, r, slots=PCS)
        w.globals(c, r, combat_mode=0)
        # strong targets only (drain HP must not kill: RecalculateCharacterHitPoints)
        strong = [s for s in PCS if get_u32(party.blob(s), C_HP) >= 60 and
                  get_i32(party.blob(s), C_HIGHEST) < COND_DEAD]
        early = r.random() < 0.12 or not strong
        t = r.choice(PCS) if early else r.choice(strong)
        s = r.choice(PCS)
        tb = party.blob(t)
        tb.u32(C_SKILL + SK_IRON_WILL * SKILL_STEP + 0xe, 0)
        if early:
            hc = r.choice([COND_DEAD, COND_MISSING])
            tb.u32(C_HIGHEST, hc)
            tb.u32(C_COND + hc * 4, 9999)
        elif r.random() < 0.25:
            tb.u32(C_COND + r.choice([2, 4, 6, 7, 9, 12]) * 4, r.choice([1, 3, 20]))
        if r.random() < 0.3:
            for k in range(6):
                tb.u32(C_RESIST + k * 0x10 + 4, r.choice([0, 10, 25, 50, 75, 100]))
        c.set(w.xchar(t) + X_OCC, b'\x01')
        c.set(w.st + ST_SUSPENDED, b'\x00')
        c.set(w.st + ST_SELECTED, i32(r.choice(PCS + [t])))
        c.set(w.st + ST_SKIP_REACT, b'\x00')
        cs = new_cs()
        w.combat_state(c, cs)
        # source / target / definition / result in scratch 1
        sc = ctx.scratch(1)
        src = bytearray(0x34)
        struct.pack_into('<iii', src, 0, r.choice([1, 1, 1, 0]), s, -1)
        emit_struct(c, sc + 0x100, src)
        c.set(sc + 0x200, slot_bytes(1, t))
        d = bytearray(DEF_SIZE)
        struct.pack_into('<hBB', d, 4, r.choice([0, 1, 3]), r.choice([0, 1, 2, 4]), r.choice([0, 2, 6]))
        negative = r.random() < 0.05
        effects = r.sample(EFFECTS_SAFE, r.choice([1, 1, 2, 3, 5, 8, 15]))
        if negative and 11 in effects:
            effects.remove(11)
        for e in effects:
            d[8 + e] = r.choice([1, 10, 25, 50, 75, 99, 100, 100, 255])
        power = r.choice([-3, -1, -100]) if negative else r.choice([0, 1, 2, 3, 5, 8, 12, 17, 24, 30, 36, 45])
        struct.pack_into('<i', d, 0x18, power)
        struct.pack_into('<i', d, 0x1c, r.choice([0, 0, 1, 5, 10, 30]))      # magnitude_base
        struct.pack_into('<i', d, 0x20, r.choice([0, 0, 1, 2]))              # duration_scale
        struct.pack_into('<I', d, 0x24, r.choice([0, 0, 0, 25, 50]))         # percent
        struct.pack_into('<i', d, 0x28, r.choice([0, 0, 1, 2, 3, 5]))        # duration_base
        struct.pack_into('<i', d, 0x2c, r.choice([0, 0, 0, 1, 2]))           # duration_per_power
        emit_struct(c, sc + 0x300, d)
        with_result = r.random() < 0.8
        if with_result:
            res = bytearray(RES_SIZE)
            if r.random() < 0.5:
                struct.pack_into('<II', res, 0, r.randrange(0, 50), r.randrange(0, 4))
                for k in range(20):
                    if r.random() < 0.3:
                        struct.pack_into('<I', res, 8 + 4 * k, r.randrange(0, 3))
                for k in range(6):
                    if r.random() < 0.3:
                        struct.pack_into('<I', res, 0x68 + 4 * k, r.randrange(0, 40))
            emit_struct(c, sc + 0x400, res)
        party.commit()
        announce = r.choice([0, 1])
        verbose = r.choice([0, 1])
        c.arg(sc + 0x100).arg(sc + 0x200).arg(sc + 0x300).arg(announce).arg(verbose)
        c.arg(sc + 0x400 if with_result else 0)
        c.cap(ctx.char(t), CHAR, 'target')
        c.cap(sc + 0x300, DEF_SIZE, 'definition')
        if with_result:
            c.cap(sc + 0x400, RES_SIZE, 'result', ignore=RES_PTR_FIELDS)
        c.cap(w.xchar(t), X_ACTION, 'target_row', ignore=X_PTR_FIELDS)
        c.cap(w.st + ST_FORMATION, 0x84, 'formation')
        c.cap(w.xs + XS_SIGHT, 1, 'sight_refresh')
        c.cap(w.st + ST_SKIP_REACT, 1, 'skip_reaction')
        c.keep(w.xs + XS_ENTRIES + t * XS_ENTRY, XS_ENTRY)
        c.note(target=party.name(t), slot=t, source=s, effects=sorted(effects), power=power,
               early_exit=early, result=with_result, announce=announce, verbose=verbose)


def cases_scatter(ctx, w):
    fn = ctx.fn(0x005454c0)
    for i in range(ctx.n(400)):
        r = ctx.rng('scatter', i)
        c = ctx.case('scatter_missile_aim_point.%d' % i, fn, conv='c', ret='v')
        fx, fy, fz = (r.uniform(-4000, 4000), r.uniform(-200, 600), r.uniform(-4000, 4000))
        kind = r.choice(['normal'] * 6 + ['near', 'vertical', 'flat', 'same', 'far', 'unit'])
        if kind == 'normal':
            dist = r.choice([2.0, 10.0, 50.0, 120.0, 400.0, 1000.0, 2500.0, r.uniform(1, 3000)])
            dx, dy, dz = r.gauss(0, 1), r.gauss(0, 0.3), r.gauss(0, 1)
        elif kind == 'near':
            dist = r.choice([0.5, 0.9999, 0.99999994, 1.0, 1.0000001, 1.5])
            dx, dy, dz = r.gauss(0, 1), r.gauss(0, 1), r.gauss(0, 1)
        elif kind == 'vertical':
            dist = r.uniform(1, 500)
            dx, dy, dz = 0.0, r.choice([1.0, -1.0]), 0.0
        elif kind == 'flat':
            dist = r.uniform(1, 2000)
            dx, dy, dz = r.gauss(0, 1), 0.0, r.gauss(0, 1)
        elif kind == 'same':
            dist = 0.0
            dx, dy, dz = 1.0, 0.0, 0.0
        elif kind == 'far':
            dist = r.choice([25000.0, 49999.0, 50000.0, 60000.0, 120000.0])
            dx, dy, dz = r.gauss(0, 1), r.gauss(0, 0.1), r.gauss(0, 1)
        else:
            dist = r.choice([1.0, 2.0, 3.0])
            dx, dy, dz = r.choice([(1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.6, 0.0, 0.8)])
        norm = (dx * dx + dy * dy + dz * dz) ** 0.5 or 1.0
        tx, ty, tz = fx + dx / norm * dist, fy + dy / norm * dist, fz + dz / norm * dist
        sc = ctx.scratch(1)
        c.set(sc, struct.pack('<fff', fx, fy, fz))
        c.set(sc + 0x10, struct.pack('<fff', tx, ty, tz))
        acc = r.choice([-1000, -50, -1, 0, 1, 5, 20, 50, 94, 95, 96, 100, 150, 299, 300, 301, 500, 9999,
                        r.randrange(-100, 400), r.randrange(0, 200)])
        if r.random() < 0.02:
            acc = r.choice([0x7fffffff, -0x80000000])
        blind = r.choice([0, 0, 1, 1, 0x100])
        c.arg(sc).arg(sc + 0x10).arg(acc).arg(blind)
        c.cap(sc, 0x1c, 'from_to', floats=[0x0, 0x4, 0x8, 0x10, 0x14, 0x18])
        c.note(kind=kind, dist=dist, accuracy=acc, blind=blind)


def cases_start_attack(ctx, w):
    fn = ctx.fn(0x0053d870)
    for i in range(ctx.n(150)):
        r = ctx.rng('sca', i)
        c = ctx.case('start_character_attack.%d' % i, fn, conv='c', ret='b')
        party = Party(ctx, w, c, r)
        w.globals(c, r)
        a = r.choice([0, 1, 2, 3, 4, 5, 6, 7])
        hand = r.choice([0, 0, 1])
        b = party.blob(a)
        fix_holds(b)
        h = C_HAND + hand * 0x5b
        holds = get_i32(b, h + H_HOLDS)
        in_play = b[h + H_INPLAY]
        path = 'not_in_play'
        if in_play and r.random() < 0.3:
            b.u8(h + H_INPLAY, 0)
        elif not in_play and holds == 0 and r.random() < 0.5:
            b.u8(h + H_INPLAY, 1)
        if b[h + H_INPLAY]:
            path = 'no_attacks_left'
            if holds == 0:
                b.u16(h + H_FLAGS, r.choice([1, 2, 0x20, 0x60, 0x1ff, 0x100, 0x91, r.randrange(1, 0x200)]))
        # NONE picks a mode from the hand's/weapon's mode bits; only for bare hands (bits set
        # above) and wielded weapons - a held shield/ammo might have no mode bits, and
        # ChooseAttackMode then never terminates
        can_choose = get_i32(b, h + H_HOLDS) in (0, 1)
        mode = -1 if can_choose and r.random() < 0.5 else r.choice(MODES + [9, 100])
        cs = new_cs()
        cs_row(cs, a, R_HAND, '<i', hand)
        cs_row(cs, a, R_HANDVAL + hand * 4, '<i', 0)
        cs_row(cs, a, R_HANDVAL + (1 - hand) * 4, '<i', r.randrange(0, 3))
        cs_row(cs, a, R_SAVED, '<ii', r.randrange(0, 4), r.randrange(0, 4))
        for k in range(REPORT_SIZE):
            if r.random() < 0.3:
                cs[CS_REPORT + k] = r.randrange(1, 256)
        cs[CS_UNAWARE] = r.choice([0, 1])
        cs[CS_NATURAL] = r.choice([0, 1])
        c.set(w.xchar(a) + X_MODES, struct.pack('<iiii', r.choice([-1, 0, 3]), r.choice([-1, 2]), 0, 0))
        party.commit()
        w.combat_state(c, cs)
        c.arg(a).arg(mode)
        c.cap(ctx.scratch(0), CS_SIZE, 'combat')
        c.cap(w.xchar(a), X_TARGET, 'row')
        c.cap(ctx.char(a), CHAR, 'char')
        c.note(char=party.name(a), slot=a, hand=hand, mode=mode, path=path, holds=holds)


def cases(ctx):
    w = World(ctx)
    cases_target_attack(ctx, w)
    cases_target_hit(ctx, w)
    cases_char_damage(ctx, w)
    cases_monster_score(ctx, w)
    cases_monster_damage(ctx, w)
    cases_effect_conditions(ctx, w)
    cases_scatter(ctx, w)
    cases_start_attack(ctx, w)
