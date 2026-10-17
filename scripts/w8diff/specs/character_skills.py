"""character_skills.cpp + learned_spells.cpp: profession/race traits, level scaling,
skill availability and training, attribute/skill recalculation, Cheat Death, alchemist
potions, revealing cursed items, skill increase notice text,
building the learned spell list.

Tested functions (original address, name, case count at --scale 1):
  0x00547940 CharacterHasTrait                          300
  0x005479b0 ScaleValueByProfessionLevel                250
  0x00547a00 ScaleValueByMonsterLevel                   200
  0x00553ee0 GetSkillQuarterValue                       200
  0x00553c90 InitializeSkillBaseLevels                  150
  0x00553d90 IsCharacterSkillAvailable                  400
  0x00553cd0 RefreshCharacterSkillAvailability          200
  0x005539e0 ResetCharacterAttributes                   200
  0x00553a60 ResetCharacterSkills                       200
  0x00553ad0 ApplyAttributeChange                       250
  0x00553c10 ApplySkillChange                           250
  0x00553f10 PracticeCharacterSkill                     400
  0x00558610 InvalidateAndRecalculateCharacterClassData 150
  0x004f9600 BuildLearnedSpellState                     200
  0x00554170 AppendSkillIncreaseNoticeText              150
  0x005542e0 FlushDeferredSkillNotices                   60  (safe inputs only, see below)
  0x00547a50 CheatDeathRevive                           200
  0x00548e20 RevealCharacterItemBindingsByProfession    250
  0x00548e60 BrewAlchemistPotion                        200
  total 4210

Skipped functions: none (all 19 annotated functions of both files are in the port map).
GetCharacterSkillNoticeValue / PostSkillIncreaseNotices / ScaleValueByLevel /
GetEffectiveSkillLevel have no FUNCTION annotation (inlined) - tested through
their callers.

Constraints and techniques (why the inputs are what they are):
* ApplyAttributeChange on screen 7 (MAIN_GAME), when an attribute crosses 100, calls
  ShowMainGameNoticeLine - a MODAL dialog (CreateDialogByKind) that would break
  the following cases. So most cases run with g_current_screen_state.id = 8
  (AUTOMAP: nothing in Local Code compares against it), and screen 7 (~1/4 of cases, without
  toggling) only when the flag cannot toggle. Screen 3 (CHARACTER) is not used anywhere: there
  character screen functions get called.
* PracticeCharacterSkill: the AddMessageBoxLine path (immediate message box) is not
  taken: suppress=1, or suppress=0 with item_pick_pending=1 or screen 8 -
  then the flags are deferred into gXStatus (which is what we compare).
* FlushDeferredSkillNotices creates message boxes (AddMessageBoxLine) - only the
  no-box branch is tested: deferred=0 (early exit) or deferred=1 with flags only on
  ineligible slots (fOccupied=0, hp=0, highest_condition 18..0x7fffffff).
  Negative highest_condition is not fed: the original compares unsigned (jae),
  the port uses a signed enum, and the port would create a message box.
* CheatDeathRevive: in 70% of cases g_status.world_suspended=1 - then
  SetCharacterCondition only prints a notice and returns, and the hp formula
  is tested; in 30% world_suspended=0 and the character is already unconscious (highest_condition=17), so
  QueueConditionChangeReaction (the reaction queue) is not called; the block
  gXStatus.monster_manager_entries is rolled back with keep (the portrait pose is UI).
  The combat state is a struct in scratch(1) substituted into g_combat_state.
* BrewAlchemistPotion: alchemist level >= 1 with profession 11 (at 0 there are no recipes, and
  the original reads past the end of the recipe table into unrelated data).
* Expected/edge-case mismatches are marked with note(edge=...):
  - reveal: negative profession level - the original does shr (unsigned),
    the port `int >> 2` (sar);
  - scale_prof: base 3e38 - intermediate float overflow if the port rounds
    the intermediate result to float;
  - cheat_death: hp/hpmax > 2^24 - the port passes hp as a float parameter (rounding),
    the original computes in x87 without rounding to float.
* The port's Russian mode (RussianOr: format "%s" instead of "%s's") in
  AppendSkillIncreaseNoticeText would give an expected text mismatch if the port were
  run with a Cyrillic font.
"""
import struct

from w8diff.api import Blob, F32

CHAR = 0x1862
# W8Character (layout.ps1, wiz8/layouts/character.h)
O_INPARTY = 0x4
O_PROF = 0x69
O_RACE = 0x71
O_GENDER = 0x75
O_EXPLEVEL = 0x89
O_PLEVELS = 0x8d
O_ATTR = 0xe5            # W8CharacterAttribute[7], stride 0x14: base +0, effective +4
ATTR_STEP = 0x14
O_SKILL = 0x19d          # W8CharacterSkill[0x29], stride 0x26
SKILL_STEP = 0x26
SK_ACTIVE, SK_POINTS, SK_LEVEL, SK_BASE, SK_PRACTICE, SK_IMPROVED, SK_AVAILABLE = 0, 2, 6, 0xa, 0xe, 0x12, 0x13
O_COND = 0xa01           # uiCondition[20]
O_ENCH1_TURNS = 0xa79    # enchantments[1].turns (DRACON_BREATH)
O_HIGHEST = 0xb01
O_HPMAX = 0xb0d
O_HP = 0xb11
O_BREW_CD = 0xb65
O_SPELLS = 0xbcd         # spell_learned[136]
O_UNLOCKS = 0xded        # skill_unlocks[0x25]
O_EQUIP = 0xf5d          # W8ItemInstance[12]
O_BACKPACK = 0x1029      # W8ItemInstance[8]
ITEM = 0xc
# character float fields: health/stamina regen rate+accumulator (0xb69..0xb75),
# spell_regen_rates[12] (0xb79..0xba5) - compared with a 4 ULP tolerance
CHAR_FLOATS = [0xb69, 0xb6d, 0xb71, 0xb75] + [0xb79 + 4 * k for k in range(12)]
PARTY_FLOATS = [s * 0x1862 + o for s in range(8) for o in CHAR_FLOATS]
O_ATTR_ADJ = 0x177c     # bonus.attribute_adjustments[7] (signed char)
O_SKILL_BONUS = 0x1783   # bonus.skill_bonus[0x29] (signed char)
# W8GlobalStatus (wiz8/layouts/game_status.h)
GS_XCHAR_PTR = 8
GS_STARTED = 0xc
GS_POOL = 0x21
GS_POOL_LEN = 500 * ITEM + 4      # party_item_pool[500] + party_item_count
GS_WORLD_SUSPENDED = 0x2390
GS_FORMATION = 0x23a1
FORMATION_LEN = 0x84
# W8PartySlotRow
XCHAR = 0x106
X_OCCUPIED = 0
X_ORDER = 0xf1
# W8XStatus (wiz8/xstatus.h)
X_ENTRY = 0x118
X_ENTRIES_LEN = 8 * X_ENTRY
X_NOTICE = 0xea          # monster_manager_entries[slot].skill_notice_pending[0x29]
X_MODES = 0x8dc          # fCombatMode .. fEncumbranceDirty (13 bytes)
X_MODES_LEN = 0xd
X_DEFERRED = 0x19b5
X_PICK = 0x19b6
# W8CombatState (wiz8/layouts/combat_state.h)
CS_SIZE = 0xa64
CS_ROW = 0xd4
CS_CHEAT = 0xbe          # characters[0].cheat_death_used
# W8MonsterRecord.effective_level
MR_LEVEL = 0x24f
# W8LearnedSpellState
LSS_SIZE = 0x3dc

SKILLS = 0x29
SCREEN_CHARACTER, SCREEN_MAIN, SCREEN_NEUTRAL = 3, 7, 8

# Items.DBS (DATA.SLF, 819 records): items with binds_on_equip != 0
BIND_ITEMS = [4, 5, 15, 29, 33, 43, 48, 71, 73, 74, 85, 86, 89, 145, 149, 160, 168, 179, 195,
              205, 208, 217, 228, 234, 238, 245, 277, 291, 305, 313, 463, 469, 660, 674, 755,
              775, 781, 791, 798, 818]
ITEM_COUNT = 819
# ids from the alchemist recipe table (0x00616FE0), all stackable (quantity_kind 1)
BREW_ITEMS = [335, 346, 336, 264, 345, 337, 317, 269, 334, 347, 341, 342, 348, 339, 429, 598,
              46, 47, 69, 338, 260, 359, 358, 360, 364, 361, 363, 349, 353, 350, 357, 354,
              362, 355, 356, 343, 258]
# g_profession_magic_level_offsets: -255 / -4 / 0
MAGIC_OFFSET = [-255, -4, -4, -4, -4, -4, -4, -255, -255, -255, 0, 0, 0, 0, 0]

FLOAT_BASES = [5.0, 15.0, 0.5, 1.0, 0.0, -0.0, 2.5, 7.25, 100.0, -5.0, -123.75, 1e-3,
               3.3333333, 0.1, 1e6, 1e30, -1e30, 65.5, 250.0, 16777217.0]


def u32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def emit(c, base, orig, mod, gap=24, maxr=20):
    """Write the differences of mod from orig (already written by setb) with the minimal number of set calls."""
    ranges = []
    i, n = 0, len(mod)
    while i < n:
        if orig[i] == mod[i]:
            i += 1
            continue
        a = last = i
        j = i + 1
        while j < n and j - last <= gap:
            if orig[j] != mod[j]:
                last = j
            j += 1
        ranges.append((a, last + 1))
        i = last + 1
    if len(ranges) > maxr:
        ranges = [(ranges[0][0], ranges[-1][1])]
    for a, b in ranges:
        c.set(base + a, bytes(mod[a:b]))


def sk(skill, field):
    return O_SKILL + skill * SKILL_STEP + field


def attr(a, field=0):
    return O_ATTR + a * ATTR_STEP + field


def xrow(ctx, slot):
    return (ctx.g('g_status') + GS_XCHAR_PTR).deref() + slot * XCHAR


def scratch_char(ctx, c, r):
    blob, name = ctx.pick_char(r)
    c.setb(ctx.scratch(0), bytes(blob))
    return ctx.scratch(0), Blob(blob), bytes(blob), name


def env(ctx, c, screen=SCREEN_MAIN, world_suspended=0, combat_null=True):
    """Scalar state read by this spec's functions and by the recalculations they
    call: screen, gXStatus modes (combat, dialogue, ...), game_started,
    world_suspended, item_pick_pending, g_combat_state."""
    gs = ctx.g('g_status')
    gx = ctx.g('gXStatus')
    c.set(ctx.g('g_current_screen_state'), u32(screen))
    c.set(gx + X_MODES, bytes(X_MODES_LEN))
    c.set(gx + X_PICK, b'\0')
    c.set(gs + GS_STARTED, b'\x01')
    c.set(gs + GS_WORLD_SUSPENDED, bytes([world_suspended]))
    if combat_null:
        c.set(ctx.g('g_combat_state'), u32(0))


def actor(ctx, c, slot, occupied=True):
    """A slot the function prints notices about: occupied, line color = slot
    (party_order_index indexes a table of 8 colors)."""
    if occupied:
        c.set(xrow(ctx, slot) + X_OCCUPIED, b'\x01')
    c.set(xrow(ctx, slot) + X_ORDER, u32(slot))


def cap_chars(ctx, c):
    c.cap(ctx.char(0), 8 * CHAR, 'chars', floats=PARTY_FLOATS)


def cap_world(ctx, c):
    cap_chars(ctx, c)
    c.cap(ctx.g('g_status') + GS_POOL, GS_POOL_LEN, 'party_pool')
    c.cap(ctx.g('gXStatus') + X_MODES, X_MODES_LEN, 'xmodes')


def pick_level(r):
    return r.choice(list(range(0, 22)) + [25, 30, 50, 100, 0x7fffffff, 0x80000000, 0xffffffff])


def pick_points(r, cur):
    return r.choice([0, 1, 3, 4, 5, 10, 25, 50, 75, 98, 99, 100, 101, 110, 124, 125, 126, 200,
                     cur, cur, r.randrange(0, 126), r.randrange(0, 126),
                     0x7fffffff, 0x80000000, 0xffffffff, 171798692])


def pick_attr_base(r, cur):
    return r.choice([1, 5, 15, 30, 50, 75, 90, 98, 99, 100, 101, 110, 124, 125, 126, 130, 0,
                     cur, cur, cur, r.randrange(1, 126), r.randrange(1, 126),
                     0xffffffff, 0x80000000])


def pick_adj(r):
    return r.choice([-128, -100, -50, -10, -1, 0, 0, 1, 5, 10, 20, 50, 100, 127])


def mutate_spells(r, blob, p):
    for s in range(0x72):
        if r.random() < p:
            blob.u32(O_SPELLS + 4 * s, r.choice([0, 0, 1, 1, 2, -1, 3, -2, 0x100]))


def mutate_flag(r, blob, off, p=0.3):
    """bool flag: usually 0/1, occasionally a non-0/1 value (tests reading the byte)."""
    if r.random() < p:
        blob.u8(off, r.choice([0, 1, 0, 1, 0, 1, 2, 0xff]) if r.random() < 0.1 else r.choice([0, 1]))


# --------------------------------------------------------------------------------
def gen_has_trait(ctx):
    fn = ctx.fn(0x00547940)  # bool CharacterHasTrait(const W8Character*, W8Trait)
    traits = list(range(-1, 0x22)) + [0x1c] * 4 + [0x1f] * 3 + [2, 0x12, 6, 0x1d] + \
        [0x7fffffff, 0x80000000, 0x100, -2]
    for i in range(ctx.n(300)):
        r = ctx.rng('trait', i)
        c = ctx.case('has_trait.%d' % i, fn, conv='c', ret='b')
        if i < 6:
            c.arg(0)
            c.arg(r.choice([2, 0x1c, 0x1f, -1, 0x12, 0]))
            c.note(char='null')
            continue
        base, blob, orig, name = scratch_char(ctx, c, r)
        prof = r.choice([-1] + list(range(15)) * 3)
        race = r.choice([-1] + list(range(16)) * 2 + [2, 5, 6, 7, 15] * 3)
        turns = r.choice([0, 0, 0, 1, 7, 0x80000000, 0xffffffff])
        blob.u32(O_PROF, prof).u32(O_RACE, race).u32(O_ENCH1_TURNS, turns)
        emit(c, base, orig, blob)
        trait = r.choice(traits)
        c.arg(base)
        c.arg(trait)
        c.note(char=name, prof=prof, race=race, trait=trait, turns=turns)


def gen_scale_prof(ctx):
    fn = ctx.fn(0x005479b0)  # float ScaleValueByProfessionLevel(W8Character*, W8Trait, float)
    for i in range(ctx.n(250)):
        r = ctx.rng('scale_prof', i)
        c = ctx.case('scale_prof.%d' % i, fn, conv='c', ret='f')
        base, blob, orig, name = scratch_char(ctx, c, r)
        prof = r.choice([-1] + list(range(15)) * 4)
        level = 20 if i < 2 else pick_level(r)
        blob.u32(O_PROF, prof)
        blob.u32(O_PLEVELS + 4 * prof, level)  # prof -1 -> uiExpLevel (0x89)
        emit(c, base, orig, blob)
        if i < 2:
            value = 3e38
            c.note(edge='float overflow of the intermediate (2*l+60)*base')
        elif r.random() < 0.3:
            value = r.randrange(1, 800) * 0.5
        elif r.random() < 0.3:
            value = r.uniform(-1000.0, 1000.0)
        else:
            value = r.choice(FLOAT_BASES)
        c.arg(base)
        c.arg(r.choice([2, 6, 0, -1, 0x1c]))
        c.arg(F32(value))
        c.note(char=name, prof=prof, level=level, base=value)


def gen_scale_monster(ctx):
    fn = ctx.fn(0x00547a00)  # float ScaleValueByMonsterLevel(W8MonsterRecord*, int, float)
    for i in range(ctx.n(200)):
        r = ctx.rng('scale_mon', i)
        c = ctx.case('scale_monster.%d' % i, fn, conv='c', ret='f')
        level = r.choice(list(range(0, 23)) * 2 + [25, 30, 50, 100, 127, 128, 200, 254, 255])
        c.set(ctx.scratch(0) + MR_LEVEL, bytes([level]))
        if r.random() < 0.3:
            value = r.uniform(-500.0, 500.0)
        else:
            value = r.choice(FLOAT_BASES[:-1])
        c.arg(ctx.scratch(0))
        c.arg(r.randrange(-3, 0x20))
        c.arg(F32(value))
        c.note(level=level, base=value)


def gen_quarter(ctx):
    fn = ctx.fn(0x00553ee0)  # unsigned GetSkillQuarterValue(W8Character*, W8Skill)
    for i in range(ctx.n(200)):
        r = ctx.rng('quarter', i)
        c = ctx.case('quarter.%d' % i, fn, conv='c', ret='i')
        base, blob, orig, name = scratch_char(ctx, c, r)
        s = r.randrange(SKILLS)
        cur = blob.get_u32(sk(s, SK_POINTS))
        pts = r.choice(list(range(0, 13)) + [cur, cur, r.randrange(0, 126), r.randrange(0, 126),
                                             99, 100, 101, 125, 126, 200, 1000, 171798691,
                                             171798692, 0x7fffffff, 0x80000000, 0xffffffff,
                                             0xfffffffc])
        blob.u32(sk(s, SK_POINTS), pts)
        emit(c, base, orig, blob)
        c.arg(base)
        c.arg(s)
        c.note(char=name, skill=s, points=pts)


def gen_base_levels(ctx):
    fn = ctx.fn(0x00553c90)  # void InitializeSkillBaseLevels(W8Character*)
    for i in range(ctx.n(150)):
        r = ctx.rng('base_levels', i)
        c = ctx.case('base_levels.%d' % i, fn, conv='c', ret='v')
        base, blob, orig, name = scratch_char(ctx, c, r)
        for a in range(7):
            if r.random() < 0.5:
                blob.u32(attr(a), pick_attr_base(r, blob.get_u32(attr(a))))
        if r.random() < 0.1:
            for a in range(7):
                blob.u32(attr(a), r.choice([0xffffffff, 0x80000000, 0x7fffffff, 0xfffffffe]))
        emit(c, base, orig, blob)
        c.arg(base)
        c.cap(base, CHAR, 'char', floats=CHAR_FLOATS)
        c.note(char=name)


def gen_available(ctx):
    fn = ctx.fn(0x00553d90)  # bool IsCharacterSkillAvailable(W8Character*, W8Skill, const bool*)
    skills = list(range(SKILLS)) + list(range(0x18, 0x29)) * 2
    for i in range(ctx.n(400)):
        r = ctx.rng('available', i)
        c = ctx.case('available.%d' % i, fn, conv='c', ret='b')
        base, blob, orig, name = scratch_char(ctx, c, r)
        prof = r.randrange(15)
        blob.u32(O_PROF, prof)
        x = r.random()
        if x < 0.3:
            blob.u32(O_RACE, 15)  # trait CANNOT_LEARN (0x1f)
        elif x < 0.4:
            blob.u32(O_RACE, r.randrange(16))
        elif x < 0.45:
            blob.u32(O_RACE, -1)
        if r.random() < 0.4:
            for s in range(0x18, 0x1c):
                blob.u8(sk(s, SK_ACTIVE), 0)
        else:
            for s in range(0x18, 0x1c):
                mutate_flag(r, blob, sk(s, SK_ACTIVE), 0.6)
        for s in range(0x1c, 0x22):
            if r.random() < 0.5:
                blob.u32(O_UNLOCKS + 4 * s, r.choice([0, 0, 0, 1, 3, 0x80000000, 0xffffffff]))
        for a in range(7):
            if r.random() < 0.4:
                blob.u32(attr(a), r.choice([98, 99, 100, 101, 125, 0, 0xffffffff, 0x80000000,
                                            blob.get_u32(attr(a))]))
        lvl = r.choice([0, 1, 2, 3, 4, 5, 6, 10, 20, 50, -1, -5, -100, 0x7fffffff,
                        0x80000000, blob.get_u32(O_PLEVELS + 4 * prof)])
        blob.u32(O_PLEVELS + 4 * prof, lvl)
        emit(c, base, orig, blob)
        s = r.choice(skills)
        c.arg(base)
        c.arg(s)
        if r.random() < 0.5:
            c.arg(0)
            flags = None
        else:
            flags = bytes(r.choice([0, 0, 1, 1, 2, 0x80, 0xff]) for _ in range(8))
            c.set(ctx.scratch(1), flags)
            c.arg(ctx.scratch(1))
        c.note(char=name, skill=s, prof=prof, plevel=lvl, flags=flags.hex() if flags else None)


def gen_refresh(ctx):
    fn = ctx.fn(0x00553cd0)  # void RefreshCharacterSkillAvailability(W8Character*)
    for i in range(ctx.n(200)):
        r = ctx.rng('refresh', i)
        c = ctx.case('refresh.%d' % i, fn, conv='c', ret='v')
        base, blob, orig, name = scratch_char(ctx, c, r)
        if r.random() < 0.5:
            blob.u32(O_PROF, r.randrange(15))
        if r.random() < 0.2:
            blob.u32(O_RACE, 15)
        for s in range(SKILLS):
            mutate_flag(r, blob, sk(s, SK_ACTIVE), 0.25)
        mutate_spells(r, blob, r.choice([0.0, 0.05, 0.15, 0.5]))
        for s in range(0x1c, 0x22):
            if r.random() < 0.3:
                blob.u32(O_UNLOCKS + 4 * s, r.choice([0, 1, 4, 0xffffffff]))
        for a in range(7):
            if r.random() < 0.3:
                blob.u32(attr(a), r.choice([99, 100, 101, 50]))
        prof = blob.get_i32(O_PROF)
        if 0 <= prof < 15 and r.random() < 0.3:
            blob.u32(O_PLEVELS + 4 * prof, r.choice([3, 4, 5, 8, -2]))
        emit(c, base, orig, blob)
        c.set(ctx.g('g_current_screen_state'), u32(r.choice([SCREEN_MAIN, SCREEN_NEUTRAL])))
        c.arg(base)
        c.cap(base, CHAR, 'char', floats=CHAR_FLOATS)
        c.note(char=name)


def gen_reset_attributes(ctx):
    fn = ctx.fn(0x005539e0)  # void ResetCharacterAttributes(W8Character*)
    for i in range(ctx.n(200)):
        r = ctx.rng('reset_attr', i)
        c = ctx.case('reset_attributes.%d' % i, fn, conv='c', ret='v')
        party = r.random() < 0.7
        if party:
            slot, blob, name = ctx.set_party(c, r)[r.randrange(8)]
            orig = bytes(blob)
            base = ctx.char(slot)
        else:
            slot = None
            base, blob, orig, name = scratch_char(ctx, c, r)
        for a in range(7):
            if r.random() < 0.5:
                blob.u32(attr(a), pick_attr_base(r, blob.get_u32(attr(a))))
            if r.random() < 0.4:
                blob.u8(O_ATTR_ADJ + a, pick_adj(r))
        emit(c, base, orig, blob)
        env(ctx, c)
        if party:
            actor(ctx, c, slot, occupied=False)
        c.arg(base)
        if party:
            cap_world(ctx, c)
        else:
            c.cap(base, CHAR, 'char', floats=CHAR_FLOATS)
        c.note(char=name, slot=slot)


def gen_reset_skills(ctx):
    fn = ctx.fn(0x00553a60)  # void ResetCharacterSkills(W8Character*)
    for i in range(ctx.n(200)):
        r = ctx.rng('reset_skills', i)
        c = ctx.case('reset_skills.%d' % i, fn, conv='c', ret='v')
        party = r.random() < 0.7
        if party:
            slot, blob, name = ctx.set_party(c, r)[r.randrange(8)]
            orig = bytes(blob)
            base = ctx.char(slot)
        else:
            slot = None
            base, blob, orig, name = scratch_char(ctx, c, r)
        if r.random() < 0.3:
            blob.u32(O_PROF, r.randrange(15))
        for s in range(SKILLS):
            if r.random() < 0.25:
                blob.u32(sk(s, SK_POINTS), pick_points(r, blob.get_u32(sk(s, SK_POINTS))))
            if r.random() < 0.25:
                blob.u8(O_SKILL_BONUS + s, r.choice([-128, -50, -10, -1, 0, 1, 5, 10, 20, 50, 127]))
        emit(c, base, orig, blob)
        env(ctx, c)
        if party:
            actor(ctx, c, slot, occupied=False)
        c.arg(base)
        if party:
            cap_world(ctx, c)
        else:
            c.cap(base, CHAR, 'char', floats=CHAR_FLOATS)
        c.note(char=name, slot=slot)


def gen_apply_attribute(ctx):
    fn = ctx.fn(0x00553ad0)  # void ApplyAttributeChange(W8Character*, W8Attribute)
    for i in range(ctx.n(250)):
        r = ctx.rng('apply_attr', i)
        c = ctx.case('apply_attribute.%d' % i, fn, conv='c', ret='v')
        slot, blob, name = ctx.set_party(c, r)[r.randrange(8)]
        orig = bytes(blob)
        a = r.randrange(7)
        b = r.choice([0, 1, 50, 98, 99, 100, 100, 101, 110, 125, 126, 0xffffffff,
                      blob.get_u32(attr(a))])
        blob.u32(attr(a), b)
        active = r.choice([0, 1])
        blob.u8(sk(a + 0x22, SK_ACTIVE), active)
        if r.random() < 0.5:
            blob.u8(O_ATTR_ADJ + a, pick_adj(r))
        for o in range(7):
            if o != a and r.random() < 0.2:
                blob.u32(attr(o), pick_attr_base(r, blob.get_u32(attr(o))))
        emit(c, ctx.char(slot), orig, blob)
        # screen 7 only if the flag will not switch to 1 (otherwise a modal dialog)
        no_flip = b < 100 or active
        screen = SCREEN_MAIN if (no_flip and r.random() < 0.25) else SCREEN_NEUTRAL
        env(ctx, c, screen=screen)
        actor(ctx, c, slot, occupied=False)
        c.arg(ctx.char(slot))
        c.arg(a)
        cap_world(ctx, c)
        c.note(char=name, slot=slot, attr=a, base=b, active=active, screen=screen)


def gen_apply_skill(ctx):
    fn = ctx.fn(0x00553c10)  # void ApplySkillChange(W8Character*, W8Skill)
    for i in range(ctx.n(250)):
        r = ctx.rng('apply_skill', i)
        c = ctx.case('apply_skill.%d' % i, fn, conv='c', ret='v')
        slot, blob, name = ctx.set_party(c, r)[r.randrange(8)]
        orig = bytes(blob)
        s = r.randrange(SKILLS)
        if r.random() < 0.2:
            blob.u32(O_PROF, r.randrange(15))
        blob.u32(sk(s, SK_POINTS), pick_points(r, blob.get_u32(sk(s, SK_POINTS))))
        if r.random() < 0.5:
            blob.u8(O_SKILL_BONUS + s, r.choice([-128, -50, -10, -1, 0, 1, 5, 10, 20, 50, 127]))
        for o in range(SKILLS):
            mutate_flag(r, blob, sk(o, SK_ACTIVE), 0.15)
        mutate_spells(r, blob, r.choice([0.0, 0.0, 0.1]))
        if s >= 0x22:
            blob.u32(attr(s - 0x22), r.choice([99, 100, 101, blob.get_u32(attr(s - 0x22))]))
        emit(c, ctx.char(slot), orig, blob)
        env(ctx, c, screen=r.choice([SCREEN_MAIN, SCREEN_NEUTRAL]))
        actor(ctx, c, slot, occupied=False)
        c.arg(ctx.char(slot))
        c.arg(s)
        cap_world(ctx, c)
        c.note(char=name, slot=slot, skill=s)


def gen_practice(ctx):
    fn = ctx.fn(0x00553f10)  # void PracticeCharacterSkill(W8Character*, W8Skill, int, bool)
    gx = ctx.g('gXStatus')
    for i in range(ctx.n(400)):
        r = ctx.rng('practice', i)
        c = ctx.case('practice.%d' % i, fn, conv='c', ret='v')
        slot, blob, name = ctx.set_party(c, r)[r.randrange(8)]
        orig = bytes(blob)
        if r.random() < 0.25:
            blob.u32(O_PROF, r.randrange(15))
        prof = blob.get_i32(O_PROF)
        s = r.randrange(SKILLS)
        pts = r.choice([0, 1, 5, 10, 25, 50, 75, 90, 98, 99, 100, 101, 125, 0xffffffff,
                        blob.get_u32(sk(s, SK_POINTS)), blob.get_u32(sk(s, SK_POINTS))])
        blob.u32(sk(s, SK_POINTS), pts)
        pc = r.choice([0, 1, 6, 7, 7, 8, 9, 100, 0xffffffff, blob.get_u32(sk(s, SK_PRACTICE))])
        blob.u32(sk(s, SK_PRACTICE), pc)
        bl = r.choice([0, 1, 10, 30, 50, 60, 70, 90, 100, 125, 200, 1000,
                       blob.get_u32(sk(s, SK_BASE)), blob.get_u32(sk(s, SK_BASE))])
        blob.u32(sk(s, SK_BASE), bl)
        mutate_flag(r, blob, sk(s, SK_ACTIVE), 0.3)
        if s >= 0x22:
            blob.u32(attr(s - 0x22), r.choice([99, 100, 101, blob.get_u32(attr(s - 0x22))]))
        if 0x1c <= s <= 0x21:
            if r.random() < 0.5:
                blob.u8(sk(r.randrange(0x18, 0x1c), SK_ACTIVE), 1)
            if r.random() < 0.5:
                blob.u32(O_UNLOCKS + 4 * s, r.choice([0, 1, 5]))
        if 0x18 <= s <= 0x1b and 0 <= prof < 15 and r.random() < 0.5:
            blob.u32(O_PLEVELS + 4 * prof, r.choice([1, 3, 4, 5, 6, 10]))
        emit(c, ctx.char(slot), orig, blob)
        usage = r.choice([0, 1, 1, 2, 3, 5, 8, 10, 16, 20, 40, 64, 100, 200])
        suppress = 1 if r.random() < 0.75 else 0
        screen = SCREEN_MAIN
        pick = 0
        if not suppress:
            if r.random() < 0.5:
                pick = 1
            else:
                screen = SCREEN_NEUTRAL
        elif r.random() < 0.2:
            screen = SCREEN_NEUTRAL
        env(ctx, c, screen=screen)
        actor(ctx, c, slot, occupied=False)
        if pick:
            c.set(gx + X_PICK, b'\x01')
        for k in range(8):
            c.fill(gx + k * X_ENTRY + X_NOTICE, SKILLS, 0)
        c.set(gx + X_DEFERRED, b'\0')
        c.arg(ctx.char(slot))
        c.arg(s)
        c.arg(usage)
        c.arg(suppress)
        cap_world(ctx, c)
        for k in range(8):
            c.cap(gx + k * X_ENTRY + X_NOTICE, SKILLS, 'notice%d' % k)
        c.cap(gx + X_DEFERRED, 1, 'deferred')
        c.note(char=name, slot=slot, skill=s, points=pts, practice=pc, base_level=bl,
               usage=usage, suppress=suppress, screen=screen, item_pick=pick)


def gen_class_data(ctx):
    fn = ctx.fn(0x00558610)  # void InvalidateAndRecalculateCharacterClassData(W8Character*)
    for i in range(ctx.n(150)):
        r = ctx.rng('class_data', i)
        c = ctx.case('class_data.%d' % i, fn, conv='c', ret='v')
        base, blob, orig, name = scratch_char(ctx, c, r)
        gender = r.choice([0, 1])
        race = r.randrange(11) if r.random() < 0.92 else r.randrange(11, 16)  # 11..15: assert
        prof = r.randrange(15)
        blob.u32(O_GENDER, gender).u32(O_RACE, race).u32(O_PROF, prof)
        emit(c, base, orig, blob)
        c.arg(base)
        c.cap(base, CHAR, 'char', floats=CHAR_FLOATS)
        c.note(char=name, gender=gender, race=race, prof=prof)


def gen_learned_spells(ctx):
    fn = ctx.fn(0x004f9600)  # void BuildLearnedSpellState(W8LearnedSpellState*, W8Character*)
    for i in range(ctx.n(200)):
        r = ctx.rng('learned', i)
        c = ctx.case('learned_spells.%d' % i, fn, conv='c', ret='v')
        base, blob, orig, name = scratch_char(ctx, c, r)
        mode = r.choice(['corpus', 'random', 'random', 'all', 'few', 'values'])
        if mode == 'random':
            mutate_spells(r, blob, r.choice([0.2, 0.5, 1.0]))
        elif mode == 'all':
            v = r.choice([1, 2])
            for s in range(0x72):
                blob.u32(O_SPELLS + 4 * s, v)
        elif mode == 'few':
            for s in range(0x72):
                blob.u32(O_SPELLS + 4 * s, 0)
            for _ in range(r.randrange(0, 6)):
                blob.u32(O_SPELLS + 4 * r.randrange(0, 0x72), r.choice([1, 2]))
        elif mode == 'values':
            for s in range(0x72):
                blob.u32(O_SPELLS + 4 * s, r.choice([0, 1, 2, 3, -1, 0x101, 0x80000001]))
        for s in range(0x1c, 0x22):
            blob.u32(O_UNLOCKS + 4 * s, r.choice([0, 1, 7, 40, 0xffffffff]))
        emit(c, base, orig, blob)
        c.fill(ctx.scratch(1), LSS_SIZE, 0xcc)
        c.arg(ctx.scratch(1))
        c.arg(base)
        c.cap(ctx.scratch(1), LSS_SIZE, 'state')
        c.cap(base, CHAR, 'char', floats=CHAR_FLOATS)
        c.note(char=name, mode=mode)


def gen_notice_text(ctx):
    fn = ctx.fn(0x00554170)  # void AppendSkillIncreaseNoticeText(wchar_t*, unsigned*, int, bool, W8Skill)
    for i in range(ctx.n(150)):
        r = ctx.rng('notice_text', i)
        c = ctx.case('notice_text.%d' % i, fn, conv='c', ret='v')
        slot, blob, name = ctx.set_party(c, r)[r.randrange(8)]
        orig = bytes(blob)
        s = r.randrange(SKILLS)
        if r.random() < 0.3:
            blob.u32(O_PROF, r.randrange(15))
        if r.random() < 0.5:
            blob.u32(sk(s, SK_POINTS), r.choice([0, 1, 4, 5, 50, 99, 100, 125, 1000,
                                                  0x7fffffff, 0xffffffff, 34359739]))
        emit(c, ctx.char(slot), orig, blob)
        order = r.randrange(8)
        c.set(xrow(ctx, slot) + X_ORDER, u32(order))
        length = r.choice([0, 0, 0, 1, 5, 20, 60, 120])
        if length:
            c.set(ctx.scratch(0), b''.join(struct.pack('<H', 0x61 + k % 26) for k in range(length)))
        c.set(ctx.scratch(1), u32(length))
        cont = r.choice([0, 1, 1, 0, 1, 2, 0x100])
        c.arg(ctx.scratch(0))
        c.arg(ctx.scratch(1))
        c.arg(slot)
        c.arg(cont)
        c.arg(s)
        c.cap(ctx.scratch(0), 0x400, 'text')
        c.cap(ctx.scratch(1), 4, 'length')
        c.note(char=name, slot=slot, skill=s, length=length, cont=cont, order=order)


def gen_flush(ctx):
    fn = ctx.fn(0x005542e0)  # void FlushDeferredSkillNotices(void)
    gx = ctx.g('gXStatus')
    for i in range(ctx.n(60)):
        r = ctx.rng('flush', i)
        c = ctx.case('flush.%d' % i, fn, conv='c', ret='v')
        party = ctx.set_party(c, r)
        deferred = 0 if r.random() < 0.15 else 1
        kinds = []
        for slot, blob, name in party:
            orig = bytes(blob)
            kind = r.choice(['eligible', 'unocc', 'hp0', 'dead'])
            occupied = 0 if kind == 'unocc' else 1
            if kind == 'hp0':
                blob.u32(O_HP, 0)
            elif kind == 'dead':
                blob.u32(O_HIGHEST, r.choice([18, 19, 20, 25, 0x7fffffff]))
            elif kind == 'eligible':
                blob.u32(O_HP, max(1, blob.get_u32(O_HP)))
                blob.u32(O_HIGHEST, r.choice([0, 0, 0, 1, 5, 12, 16, 17]))
            emit(c, ctx.char(slot), orig, blob)
            c.set(xrow(ctx, slot) + X_OCCUPIED, bytes([occupied]))
            if kind == 'eligible' and deferred:
                pend = bytes(SKILLS)
            else:
                pend = bytes(1 if r.random() < 0.2 else 0 for _ in range(SKILLS))
            c.set(gx + slot * X_ENTRY + X_NOTICE, pend)
            kinds.append(kind)
        c.set(gx + X_DEFERRED, bytes([deferred]))
        for k in range(8):
            c.cap(gx + k * X_ENTRY + X_NOTICE, SKILLS, 'notice%d' % k)
        c.cap(gx + X_DEFERRED, 1, 'deferred')
        c.note(deferred=deferred, kinds=','.join(kinds))


def gen_cheat_death(ctx):
    fn = ctx.fn(0x00547a50)  # void CheatDeathRevive(int party_slot)
    gx = ctx.g('gXStatus')
    for i in range(ctx.n(200)):
        r = ctx.rng('cheat_death', i)
        c = ctx.case('cheat_death.%d' % i, fn, conv='c', ret='v')
        party = ctx.set_party(c, r)
        slot, blob, name = party[r.randrange(8)]
        orig = bytes(blob)
        x = r.random()
        mode = 'suspended' if x < 0.45 else ('combat' if x < 0.7 else 'live')
        prof = 2 if r.random() < 0.6 else r.randrange(15)
        blob.u32(O_PROF, prof)
        level = r.choice(list(range(0, 25)) + [30, 50, 0xffffffff, 0x80000000])
        blob.u32(O_PLEVELS + 4 * prof, level)
        hpmax = r.choice([1, 2, 10, 50, 99, 100, 150, 200, 333, 500, 1000, 0,
                          blob.get_i32(O_HPMAX), blob.get_i32(O_HPMAX)])
        hp = r.choice([0, 0, 1, 2, 5, 10, 50, hpmax & 0xffffffff, r.randrange(0, 300)])
        edge = None
        if i in (3, 4):
            hp, edge = 16777217 + i, 'hp > 2^24 passed as float'
        elif i in (5, 6):
            hpmax, edge = r.choice([-1, 33554433]), 'hpmax*0.5 > 2^24 / negative hpmax'
        blob.u32(O_HPMAX, hpmax)
        blob.u32(O_HP, hp)
        if mode == 'live':
            blob.u32(O_COND + 4 * 17, r.randrange(1, 7))
            blob.u32(O_COND + 4 * 18, 0)
            blob.u32(O_COND + 4 * 19, 0)
            blob.u32(O_HIGHEST, 17)
        else:
            blob.u32(O_COND + 4 * 17, r.choice([0, 0, 1, 3, 6, 7, 100, 0xffffffff]))
        emit(c, ctx.char(slot), orig, blob)
        actor(ctx, c, slot)
        env(ctx, c, screen=r.choice([SCREEN_MAIN, SCREEN_NEUTRAL]),
            world_suspended=0 if mode == 'live' else 1, combat_null=(mode != 'combat'))
        used = None
        if mode == 'combat':
            c.setp(ctx.g('g_combat_state'), ctx.scratch(1))
            flags = [r.choice([0, 1]) for _ in range(8)]
            used = flags[slot]
            for k in range(8):
                if flags[k]:
                    c.set(ctx.scratch(1) + CS_CHEAT + k * CS_ROW, b'\x01')
        if mode == 'live':
            c.keep(gx, X_ENTRIES_LEN)
            c.cap(ctx.g('g_status') + GS_FORMATION, FORMATION_LEN, 'formation')
        c.arg(slot)
        cap_chars(ctx, c)
        c.cap(gx + X_MODES, X_MODES_LEN, 'xmodes')
        if mode == 'combat':
            c.cap(ctx.scratch(1), CS_SIZE, 'combat_state')
        c.note(char=name, slot=slot, mode=mode, prof=prof, level=level, hpmax=hpmax, hp=hp,
               cheat_used=used)
        if edge:
            c.note(edge=edge)


def gen_reveal(ctx):
    fn = ctx.fn(0x00548e20)  # int RevealCharacterItemBindingsByProfession(int, unsigned)
    for i in range(ctx.n(250)):
        r = ctx.rng('reveal', i)
        c = ctx.case('reveal.%d' % i, fn, conv='c', ret='i')
        party = ctx.set_party(c, r)
        caster = r.randrange(8)
        target = caster if r.random() < 0.3 else r.randrange(8)
        blobs = {s: (b, bytes(b), n) for s, b, n in party}
        cb = blobs[caster][0]
        if r.random() < 0.5:
            cb.u32(O_PROF, r.randrange(15))
        prof = cb.get_i32(O_PROF)
        edge = None
        if r.random() < 0.04:
            level = r.choice([0xffffffff, 0xfffffffc, 0x80000000, 0xfffffff0])
            edge = 'negative profession level: retail shr, port int >> 2'
        else:
            level = r.choice(list(range(0, 31)) + [40, 50, 0x7fffffff, cb.get_u32(O_PLEVELS + 4 * prof)])
        cb.u32(O_PLEVELS + 4 * prof, level)
        tb = blobs[target][0]
        for k in range(12):
            off = O_EQUIP + k * ITEM
            x = r.random()
            if x < 0.3:
                tb.u32(off, r.choice(BIND_ITEMS))
            elif x < 0.4:
                tb.u32(off, r.randrange(ITEM_COUNT))
            elif x < 0.6:
                tb.u32(off, -1)
            if r.random() < 0.3:
                tb.u8(off + 0xa, r.choice([0, 1]))
        for s in {caster, target}:
            b, o, n = blobs[s]
            emit(c, ctx.char(s), o, b)
        c.arg(caster)
        c.arg(target)
        cap_chars(ctx, c)
        c.note(caster=blobs[caster][2], target=blobs[target][2], caster_slot=caster,
               target_slot=target, prof=prof, level=level)
        if edge:
            c.note(edge=edge)


def gen_brew(ctx):
    fn = ctx.fn(0x00548e60)  # void BrewAlchemistPotion(W8Character*)
    for i in range(ctx.n(200)):
        r = ctx.rng('brew', i)
        c = ctx.case('brew.%d' % i, fn, conv='c', ret='v')
        slot, blob, name = ctx.set_party(c, r)[r.randrange(8)]
        orig = bytes(blob)
        prof = 11 if r.random() < 0.7 else r.randrange(15)
        blob.u32(O_PROF, prof)
        alch = r.choice(list(range(1, 21)) * 2 + [25, 30, 50])
        blob.u32(O_PLEVELS + 4 * 11, alch)
        hc = r.choice([0] * 6 + [1, 5, 10, 16, 17, 18, 19])
        blob.u32(O_HIGHEST, hc)
        if blob.get_u32(O_EXPLEVEL) < 7 and r.random() < 0.9:
            blob.u32(O_EXPLEVEL, r.randrange(7, 20))  # without the DeliverExceptionalItemReaction remark
        bp = r.choice(['corpus', 'corpus', 'corpus', 'full', 'empty', 'stack'])
        if bp != 'corpus':
            for k in range(8):
                off = O_BACKPACK + k * ITEM
                if bp == 'empty':
                    item = struct.pack('<i', -1) + bytes(8)
                elif bp == 'full':
                    item = struct.pack('<iBBB', r.choice(BREW_ITEMS + [r.randrange(ITEM_COUNT)]),
                                       r.randrange(1, 6), 0, 1) + bytes(5)
                else:  # stack: the same ids as in the recipes, with and without free space
                    item = struct.pack('<iBBB', r.choice(BREW_ITEMS[:8]), r.choice([1, 4, 5]), 0,
                                       1) + bytes(5)
                blob[off:off + ITEM] = item
        blob.u32(O_BREW_CD, r.choice([0, 1, 0x168, 1000]))
        emit(c, ctx.char(slot), orig, blob)
        occupied = 0 if r.random() < 0.1 else 1
        c.set(xrow(ctx, slot) + X_OCCUPIED, bytes([occupied]))
        env(ctx, c, screen=r.choice([SCREEN_MAIN, SCREEN_NEUTRAL]))
        c.arg(ctx.char(slot))
        cap_world(ctx, c)
        c.note(char=name, slot=slot, prof=prof, alchemy=alch, highest=hc, backpack=bp,
               occupied=occupied)


def cases(ctx):
    gen_has_trait(ctx)
    gen_scale_prof(ctx)
    gen_scale_monster(ctx)
    gen_quarter(ctx)
    gen_base_levels(ctx)
    gen_available(ctx)
    gen_refresh(ctx)
    gen_reset_attributes(ctx)
    gen_reset_skills(ctx)
    gen_apply_attribute(ctx)
    gen_apply_skill(ctx)
    gen_practice(ctx)
    gen_class_data(ctx)
    gen_learned_spells(ctx)
    gen_notice_text(ctx)
    gen_cheat_death(ctx)
    gen_reveal(ctx)
    gen_brew(ctx)
    gen_flush(ctx)
