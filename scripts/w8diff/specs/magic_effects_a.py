"""Magic Effects.cpp, lines 1-1900 (decomp/src/wiz8/local_code/Magic Effects.cpp).

Tested (retail address, name, cases at --scale 1):
  0x00551a20 RollEffectMagnitude              300
  0x005519c0 RollEffectDuration               300  (port symbol given explicitly: the name is
                                                   ambiguous with the static 4-int helper)
  0x00551900 GetConditionDisplaySlot          158  (every id -3..140 plus extremes)
  0x00551a60 RecalculateCharacterResistances  300
  0x00552250 ReduceMagnitudeByResistance      400  (characters + fake monsters)
  0x00552340 ApplyEffectAndAnnounce           160  (characters + fake monsters)
  0x005520d0 TargetResistsCondition           400  (characters + fake monsters)
  0x00551eb0 InflictConditionOnTarget         350  (characters; monsters only on safe paths)
  0x00551BA0 ResolveAttackOnTarget            400  (characters; monsters only on early-exit paths)
  0x0054e3f0 ApplyConditionToTargets          300  (character targets)
  0x0054f8c0 FatigueTargets                   300  (characters + fake monsters)
  0x0054f520 RestoreTargetsStamina            300  (characters; monsters only when no notice names them)
  0x0054f190 HealTargets                      300  (characters; monsters only when no notice names them)
  0x0054e950 ApplyDamageToTargets             300  (character targets)
  0x0054ec80 DrainTargetsLife                 300  (character targets; char/monster/no source)
  0x0054df00 TryCureConditionOnTargets        350  (characters; monsters only on the countdown path)
  0x0054d5c0 InflictConditionAttack           350  (characters; monsters only on early-exit paths)
  0x00554540 IsScreenBusy                     140
  0x005524e0 ClearEffectSlot                  150  (fake monster, inactive slot)

Skipped:
  0x005523d0 ClearMonsterCharm            - notice + monster spell-icon removal on the 3D object;
                                            the logic is a single flag clear
  0x00552410 MonsterResistsSpellEffect    - not in the port map (inlined/discarded)
  0x00552530 ResetCombatEffects           - combat-end cleanup; HUD invalidation and redraw
  0x005524b0 ResetPartyEffectBlock        - HUD strip invalidate/clear plus sky-node light change;
                                            the rebuild it wraps lives in Gameplay Mods.cpp
  0x00552070 AnnounceEffectResisted       - text notice only
  0x0054ff20 HeadingTowardNearestMonster  - depends on live monster positions and the camera
  0x005500c0 ApplySummonElementalEffect   - creates a monster group in the world
  0x005507d0 RecallCasterToSavedLocation  - not in the port map; teleport / level change
  0x0054e610 ApplyRandomAfflictionToTarget- not in the port map (inlined/discarded)
  0x0054e710 ReportSpellEffectResult      - text output; its flag writes run inside the
                                            non-verbose ApplyDamageToTargets/DrainTargetsLife cases
  0x00553910 GetTargetConditionTurns      - not in the port map (inlined/discarded)

How the inputs are controlled:
  * Characters: corpus characters in all 8 party slots (setb), mutated fields written as small
    `set` runs on top. XChar rows: fOccupied=1, npc_index=-1, npc_bound set explicitly.
  * Monsters are never the live ones: gXStatus.plsMonsterList and plsUnbornMonsterList are pointed
    at PLists built in scratch (empty for character-only cases), so every monster walk sees only
    fake W8MonsterInfo records (scratch 1) whose species point, through
    gXStatus.monster_record_cache, at fake W8MonsterRecords (scratch 2). p3D is null, so only paths
    that never touch the 3D object or GetMonsterName are used with monster targets.
  * Scalars set in every case: g_settings.difficulty / verbose_combat_messages, the six gXStatus
    mode flags (combat off), fSurprisePossible (=1 on damage paths: it skips the portrait splat
    and damage-reaction code whose Random() use depends on real-time UI/event-queue state),
    item_pick_pending (=1 where a skill can improve: blocks the skill-increase message box),
    g_status.world_suspended=0, skip_next_condition_reaction=0, screen id = main game,
    gXStatus.sight_refresh_pending=0 (a one-shot latch the game leaves set or clear; the
    HEXED/BLIND/Superman paths raise it), g_status.selected_character=0 (AimAtTarget and the
    combat row resets redraw differently for the selected slot).
  * The character voice/portrait-event machinery is frozen (all restored after the call): the
    event queue's 0xb1-byte mask array is filled with 0xff, so every QueueEntry drops its event
    (no dispatch, no preemption of the slot's active event), and the counts of its five event
    vectors are zeroed, so RemoveCharacterEvents (a dying character) completes / deletes nothing.
    Both were live state that differed between the two processes: an active event left on a
    portrait slot from the loaded game made retail assert (CharacterPointerToPartySlot, line 465)
    and diverged the Random() sequence. g_level_block->portrait_refresh_pending[0..7] = 1, so
    the splat / effect-icon / quote paths never run the hover-dependent auto portrait refresh.
  Total: 5558 cases.
  * Captured: the 8-character array (regen float fields ignored: the API cannot mark cap
    floats for fp-noise tolerance, and they are rebuilt by Gameplay Mods code), XChar rows,
    g_status (text-box line counters excluded), gXStatus portrait entries / flag bytes, the scratch
    effect entry and fake monsters.
"""
import struct

from w8diff.api import Blob

MAX_OPS = 96
MAX_ARGS = 16

# ---- W8Character (layout.ps1, wiz8/layouts/character.h) ----
CHAR = 0x1862
C_NAME = 0x5
C_PROF = 0x69
C_RACE = 0x71
C_LEVEL = 0x89
C_ATTR = 0xe5           # stride 0x14: base +0, effective +4
ATTR_STEP = 0x14
C_SKILL = 0x19d         # stride 0x26: active +0, points +2, level +6, base_level +0xa, practice +0xe
SKILL_STEP = 0x26
C_COND = 0xa01          # unsigned int[20]
C_ENCH = 0xa65          # stride 0xc: power +0, percent +4 (u16), magnitude +6 (u16), turns +8
ENCH_STEP = 0xc
C_HIGHEST = 0xb01
C_ENCH_TOP = 0xb05
C_COND_ARG = 0xb09
C_HPMAX = 0xb0d
C_HP = 0xb11
C_STMAX = 0xb19
C_ST = 0xb1d
C_SPMAX = 0xb25
C_SPLEFT = 0xb45
C_RES = 0xedd           # stride 0x10: base +0, total +4
RES_STEP = 0x10
C_BONUS_ALL = 0x1777    # signed char
C_BONUS_RES = 0x17ac    # signed char[6]
C_FATIGUE_BAND = 0x169e
C_DEEP_FATIGUE = 0x185b
C_FLOATS = [0xb69, 0xb6d, 0xb71, 0xb75] + [0xb79 + 4 * k for k in range(12)]

SK_FIRE = 0x1c
SK_IRON_WILL = 0x24
ATTR_INT, ATTR_PIETY, ATTR_VITALITY, ATTR_SENSES = 1, 2, 3, 6

# ---- party slot row (wiz8/layouts/combat_state.h) ----
XROW = 0x106
X_OCCUPIED = 0x0
X_NPC_INDEX = 0xfa      # int, followed by npc_bound (bool) at 0xfe

# ---- g_status (wiz8/layouts/game_status.h) ----
GS_SIZE = 0x49c2
GS_TEXT_A = 0x1795      # text_line_cursor + legacy_text_box_lines .. 0x17af
GS_TEXT_A_END = 0x17af
GS_TEXT_B = 0x4997      # text_box_lines_used/shown .. 0x49b7
GS_TEXT_B_END = 0x49b7
GS_WORLD_SUSPENDED = 0x2390
GS_SKIP_REACTION = 0x2488
GS_SELECTED = 0x1d      # selected_character

# ---- gXStatus (wiz8/xstatus.h) ----
XS_ENTRIES_END = 0x8c0
XS_ENTRY = 0x118
XS_MODES = 0x8dc        # fCombatMode .. fTrapInteractMode (6 bytes)
XS_FLAGS_END = 0x8f5
XS_MONSTER_LIST = 0x8f5
XS_UNBORN_LIST = 0x901
XS_SURPRISE = 0x90d
XS_SIGHT_REFRESH = 0xa03
XS_RECORD_CACHE = 0xa0f
XS_TAIL = 0x19b3        # save_notice .. scripted_scene
XS_PICK_PENDING = 0x19b6
XS_EVENT_QUEUE = 0x91f  # W8CharacterEventQueue*
# event ptr, TIMERs, vector data; 0x0d/0x11: mouth_gap head/cursor (heap pointers of a voice line)
ENTRY_IGNORE = [0x0d, 0x11, 0x71, 0x7d, 0x91, 0x95, 0xca, 0xd2, 0xe4]

# ---- W8CharacterEventQueue (wiz8/character_event_queue.h) ----
# count dwords of vector0, pending_events, vector1, npc_deferred_events, active_events
EQ_COUNTS = [0x04, 0x14, 0x24, 0x34, 0x44]
EQ_MASKS = 0x68         # unsigned char* event_character_masks (0xb1 bytes)
EQ_MASK_LEN = 0xb1

# ---- W8LevelRuntimeBlock (wiz8/layouts/main_game_screen.h) ----
LB_PORTRAIT_REFRESH = 0x109   # portrait_refresh_pending[8]

# ---- g_settings (wiz8/local_code/Configuration.h) ----
SET_DIFFICULTY = 0xd    # 4-byte enum
SET_VERBOSE = 0x44

# ---- W8MonsterInfo / W8MonsterRecord (MonsterManager.h, gameplay_databases.h) ----
MI_SIZE = 0x425
MI_STRIDE = 0x430
MI_LOC, MI_GROUP, MI_SPECIES = 0x0, 0x4, 0x8
MI_ACTIVE, MI_INCOMBAT, MI_DISP = 0x14, 0x15, 0x16
MI_HPMAX, MI_HP, MI_STMAX, MI_ST = 0x27, 0x2b, 0x2f, 0x33
MI_COND = 0x57
MI_ENCH = 0xa7
MI_HIGHEST = 0x107
MI_COND_ARG = 0x10b
MI_SLOTS = 0x10f        # W8EffectSlot[12], stride 0x11
MI_MODS = 0x1db
MI_RES_BONUS = 0x217
MI_SPELL_POINTS = 0x2f9
MI_ELEMENTAL = 0x344
MR_SIZE = 0x297
MR_STRIDE = 0x2a0
MR_KIND = 0xcb
MR_ATTRS = 0xd1
MR_RES = 0x176
MR_DEATH_IMMUNE = 0x1be
MR_LEVEL = 0x24f
FAKE_SPECIES = 990
FAKE_LOC = 0x7ead0010
FAKE_GROUP = 0x7ead1000
IMMUNE = {20: [2, 7, 17, 3, 6, 11, 15, 4], 22: [2, 7, 4, 3, 6, 15], 17: [11, 6, 4]}

# ---- W8SpellEffectEntry (wiz8/local_code/SpellEffect.h) ----
E_SIZE = 0x1c8
E_KIND = 0x0
E_SOURCE = 0x5c         # W8TargetSource: type +0, iChar +4, iMonsterID +8, fReflection +0x1b,
                        # fBackfire +0x1c, target_diverted +0x1e
E_TARGET = 0x90         # W8CombatSlot: type +0, iChar +4, iMonsterID +8, iGroupID +0xc
E_DEF = 0xb0
E_MONSTERS = 0xe0       # W8GrowableVector<int>: count +4, capacity +8, data +0xc
E_TARGETS = 0xf0
E_REPORTED = 0x124
E_APPLIED = 0x125
E_REPORTS_DATA = 0x18a  # result.reports.data (allocated by the damage path)
# W8SpellEffectDefinition
D_DICE = 0x4            # base i16 +0, count u8 +2, sides u8 +3
D_CHANCES = 0x8
D_POWER = 0x18
D_MAG_BASE = 0x1c
D_SCALE = 0x20
D_PERCENT = 0x24
D_DUR_BASE = 0x28
D_DUR_PER = 0x2c

# scratch 0 layout
S0_EFFECT = 0x0
S0_TARGET_DATA = 0x200
S0_MONSTER_DATA = 0x280
S0_SOURCE = 0x300
S0_SLOT = 0x340
S0_MAG = 0x380
S0_EFSLOT = 0x3a0

INDEF = 9999
SPELL_SLOW, SPELL_TERROR, SPELL_SONIC_BOOM = 29, 14, 30
SPELL_LIFESTEAL, SPELL_MIGHT_TO_MAGIC = 82, 84


def p8(v):
    return struct.pack('<B', int(v) & 0xff)


def p16(v):
    return struct.pack('<H', int(v) & 0xffff)


def p32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def u32(v):
    return int(v) & 0xffffffff


class Env:
    def __init__(self, ctx):
        self.ctx = ctx
        self.gs = ctx.g('g_status')
        self.xs = ctx.g('gXStatus')
        self.st = ctx.g('g_settings')
        self.screen = ctx.g('g_current_screen_state')
        self.modal = ctx.g('g_modal_owner')
        self.queue = (self.xs + XS_EVENT_QUEUE).deref()
        self.masks = (self.queue + EQ_MASKS).deref()
        self.level = ctx.g('g_level_block').deref()
        self.xchar = (self.gs + 8).deref()
        self.chars = ctx.char(0)
        self.s0 = ctx.scratch(0)
        self.s1 = ctx.scratch(1)
        self.s2 = ctx.scratch(2)
        self.s3 = ctx.scratch(3)


# --------------------------------------------------------------------------- helpers

def emit_diff(c, addr, old, new, gap=24):
    """set only the changed byte runs (runs closer than `gap` are merged)."""
    runs = []
    i, n = 0, len(new)
    while i < n:
        if old[i] == new[i]:
            i += 1
            continue
        j = i
        while j < n and old[j] != new[j]:
            j += 1
        if runs and i - runs[-1][1] <= gap:
            runs[-1][1] = j
        else:
            runs.append([i, j])
        i = j
    for a, b in runs:
        c.set(addr + a, bytes(new[a:b]))


def emit_struct(c, addr, data):
    """One set covering the non-zero part of a struct placed in (zeroed) scratch."""
    nz = [k for k, v in enumerate(data) if v]
    if nz:
        c.set(addr + nz[0], bytes(data[nz[0]:nz[-1] + 1]))


def finish(c):
    assert len(c.ops) <= MAX_OPS, '%s: %d ops' % (c.id, len(c.ops))
    assert len(c.args) <= MAX_ARGS, '%s: %d args' % (c.id, len(c.args))


def set_globals(c, e, difficulty=1, verbose=0, surprise=0, pick=0, combat=0):
    c.set(e.st + SET_DIFFICULTY, p32(difficulty))
    c.set(e.st + SET_VERBOSE, p8(verbose))
    c.set(e.xs + XS_MODES, bytes([combat & 1, 0, 0, 0, 0, 0]))
    c.set(e.xs + XS_SURPRISE, p8(surprise))
    c.set(e.xs + XS_PICK_PENDING, p8(pick))
    c.set(e.gs + GS_WORLD_SUSPENDED, b'\x00')
    c.set(e.gs + GS_SKIP_REACTION, b'\x00')
    c.set(e.screen, p32(7))
    c.set(e.xs + XS_SIGHT_REFRESH, b'\x00')
    c.set(e.gs + GS_SELECTED, p32(0))
    freeze_events(c, e)


def freeze_events(c, e):
    """Character voice/portrait events: drop every newly queued event (mask array 0xff), hide
    the queued/active ones (vector counts 0) and skip the auto portrait refresh. See the module
    docstring; everything is restored after the call."""
    c.fill(e.masks, EQ_MASK_LEN, 0xff)
    for off in EQ_COUNTS:
        c.set(e.queue + off, p32(0))
    c.set(e.level + LB_PORTRAIT_REFRESH, b'\x01' * 8)


def party(ctx, c, e, r, rows=True, npc_bound_chance=0.0):
    """8 corpus characters (setb) + XChar rows. Returns {slot: [base bytes, Blob, name]}."""
    out = {}
    for slot, blob, name in ctx.set_party(c, r):
        out[slot] = [bytes(blob), Blob(blob), name]
    if rows:
        for slot in range(8):
            row = e.xchar + slot * XROW
            c.set(row + X_OCCUPIED, b'\x01')
            bound = 1 if r.random() < npc_bound_chance else 0
            c.set(row + X_NPC_INDEX, struct.pack('<iB', -1, bound))
    return out


def commit_party(c, e, p):
    for slot, (base, blob, _) in sorted(p.items()):
        emit_diff(c, e.chars + slot * CHAR, base, bytes(blob), gap=64)


def fix_highest(b):
    hc = 0
    for k in range(19, -1, -1):
        if b.get_u32(C_COND + 4 * k) != 0:
            hc = k
            break
    b.u32(C_HIGHEST, hc)


def fix_ench_top(b):
    top = 0
    for k in range(7, -1, -1):
        if b.get_u32(C_ENCH + ENCH_STEP * k + 8) != 0:
            top = k
            break
    b.u32(C_ENCH_TOP, top)


def cap_world(c, e, effect=False, monsters=0):
    ign = [s * CHAR + o for s in range(8) for o in C_FLOATS]
    c.cap(e.chars, 8 * CHAR, 'chars', ignore=ign)
    c.cap(e.xchar, 8 * XROW, 'xchar')
    c.cap(e.gs, GS_TEXT_A, 'gstat_a', ignore=[4, 8])
    c.cap(e.gs + GS_TEXT_A_END, GS_TEXT_B - GS_TEXT_A_END, 'gstat_b')
    c.cap(e.gs + GS_TEXT_B_END, GS_SIZE - GS_TEXT_B_END, 'gstat_c')
    c.cap(e.xs, XS_ENTRIES_END, 'xs_entries',
          ignore=[k * XS_ENTRY + o for k in range(8) for o in ENTRY_IGNORE])
    c.cap(e.xs + XS_ENTRIES_END, XS_FLAGS_END - XS_ENTRIES_END, 'xs_flags')
    c.cap(e.xs + XS_SIGHT_REFRESH, 1, 'xs_sight')
    c.cap(e.xs + XS_TAIL, 5, 'xs_tail')
    if effect:
        c.cap(e.s0 + S0_EFFECT, E_SIZE, 'effect', ignore=[E_REPORTS_DATA])
    if monsters:
        c.cap(e.s1, MI_STRIDE * (monsters - 1) + MI_SIZE, 'monsters')


def new_monster(r, over=None):
    """(info Blob, record Blob) with plausible random contents; over: {(blob, off, size): v}."""
    mi = Blob(MI_SIZE)
    mr = Blob(MR_SIZE)
    mi.u32(MI_GROUP, FAKE_GROUP)
    mi.u8(MI_ACTIVE, 1)
    mi.u8(MI_INCOMBAT, 0)
    mi.u8(MI_DISP, r.choice([0, 1, 1, 2]))
    hpmax = r.choice([5, 20, 60, 150, 400, r.randrange(1, 1000)])
    mi.u32(MI_HPMAX, hpmax)
    mi.u32(MI_HP, r.choice([hpmax, hpmax, r.randrange(1, hpmax + 1)]))
    stmax = r.choice([30, 80, 150, 300, r.randrange(1, 500)])
    mi.u32(MI_STMAX, stmax)
    mi.u32(MI_ST, r.choice([stmax, r.randrange(1, stmax + 1)]))
    for k in range(6):
        mi.u8(MI_RES_BONUS + k, r.choice([0, 0, 0, 5, 10, 25, -10, -50, 100, r.randrange(256)]))
    mi.u32(MI_ELEMENTAL, 0xffffffff)
    mr.u8(MR_KIND, r.choice([0, 1, 2, 4, 5, 9, 13, 16, 18, 19, 21, 23, r.randrange(30)]))
    for k in range(6):
        mr.u8(MR_RES + k, r.choice([0, 0, 10, 25, 40, 50, 75, 90, 100, r.randrange(256)]))
    mr.u8(MR_LEVEL, r.choice([1, 3, 5, 8, 10, 12, 15, 18, 20, 25, 30, 40, r.randrange(1, 60)]))
    for k in range(5):
        mr.u8(MR_ATTRS + k, r.choice([10, 30, 50, 70, 90, 110, 125, r.randrange(1, 130)]))
    for key, val in (over or {}).items():
        tgt, off, size = key
        b = mi if tgt == 'mi' else mr
        if size == 1:
            b.u8(off, val)
        elif size == 2:
            b.u16(off, val)
        else:
            b.u32(off, val)
    return mi, mr


def wire_monsters(c, e, mons):
    """Point gXStatus monster lists at scratch PLists holding the fake monsters."""
    for k, (mi, mr) in enumerate(mons):
        mi.u32(MI_LOC, FAKE_LOC + k)
        mi.u32(MI_SPECIES, FAKE_SPECIES + k)
        emit_struct(c, e.s1 + k * MI_STRIDE, bytes(mi))
        emit_struct(c, e.s2 + k * MR_STRIDE, bytes(mr))
        c.setp(e.s3 + 0x10 + 4 * k, e.s1 + k * MI_STRIDE)
        c.setp(e.xs + XS_RECORD_CACHE + 4 * (FAKE_SPECIES + k), e.s2 + k * MR_STRIDE)
    if mons:
        c.set(e.s3 + 4, struct.pack('<ii', 16, len(mons)))
        c.setp(e.s3, e.s3 + 0x10)
    c.setp(e.xs + XS_MONSTER_LIST, e.s3)
    c.setp(e.xs + XS_UNBORN_LIST, e.s3 + 0x100)   # zeroed: empty list


def mon_ptr(e, k):
    return e.s1 + k * MI_STRIDE


def write_effect(c, e, eff, targets, monster_ids):
    """eff: Blob(E_SIZE) without list pointers; lists go to scratch 0."""
    eff.u32(E_TARGETS + 4, len(targets))
    eff.u32(E_TARGETS + 8, max(len(targets), 1))
    eff.u32(E_MONSTERS + 4, len(monster_ids))
    eff.u32(E_MONSTERS + 8, max(len(monster_ids), 1))
    emit_struct(c, e.s0 + S0_EFFECT, bytes(eff))
    if targets:
        c.set(e.s0 + S0_TARGET_DATA, b''.join(struct.pack('<i', t) for t in targets))
    if monster_ids:
        c.set(e.s0 + S0_MONSTER_DATA, b''.join(struct.pack('<i', t) for t in monster_ids))
    c.setp(e.s0 + E_TARGETS + 0xc, e.s0 + S0_TARGET_DATA)
    c.setp(e.s0 + E_MONSTERS + 0xc, e.s0 + S0_MONSTER_DATA)


def rand_dice(r, small=False):
    pick = r.random()
    if pick < 0.6 or small:
        return (r.choice([0, 0, 1, 2, 5, 10, 20, r.randrange(-5, 40)]),
                r.choice([1, 1, 2, 3, 4, 6, 8, 10]), r.choice([2, 3, 4, 6, 8, 10, 12, 20]))
    if pick < 0.75:
        return (r.choice([0, 1, 50, 200, 9999, 9998]), 0, r.randrange(256))
    if pick < 0.9:
        return (r.randrange(-40, 300), r.randrange(0, 40), r.randrange(0, 50))
    return (r.choice([-32768, -1, 32767, 100]), r.choice([0, 255, 1]), r.choice([0, 1, 255]))


def rand_definition(r, small_dice=False):
    d = Blob(0x30)
    base, count, sides = rand_dice(r, small_dice)
    d.u16(D_DICE, base)
    d.u8(D_DICE + 2, count)
    d.u8(D_DICE + 3, sides)
    for k in range(16):
        if r.random() < 0.2:
            d.u8(D_CHANCES + k, r.randrange(101))
    d.u32(D_POWER, r.choice([1, 1, 2, 3, 4, 5, 6, 7, 0, 10, 20, r.randrange(1, 8)]))
    d.u32(D_SCALE, r.choice([1, 2, 3, 4, 5, 6, 7, 0, r.randrange(1, 8)]))
    d.u32(D_PERCENT, r.choice([0, 0, 0, 10, 25, 50, 100, r.randrange(0, 120)]))
    d.u32(D_DUR_BASE, r.choice([0, 1, 2, 3, 5, 10, 20, r.randrange(0, 40)]))
    d.u32(D_DUR_PER, r.choice([0, 1, 2, 3, 5, 8, r.randrange(0, 12)]))
    if r.random() < 0.05:
        d.u32(D_DUR_PER, 0)
        d.u32(D_DUR_BASE, INDEF)
    return d


def max_duration(d):
    """Upper bound of RollEffectDuration for the definition blob."""
    dur = u32(d.get_u32(D_DUR_PER) * d.get_u32(D_SCALE) + d.get_u32(D_DUR_BASE))
    if dur == INDEF:
        return INDEF
    dur = u32(dur + 2)
    pct = d.get_u32(D_PERCENT)
    return u32(dur + dur * pct // 100) if dur < 0x10000 and pct < 0x10000 else None


def new_effect(r, kind, d, source_type=None, source_char=None):
    eff = Blob(E_SIZE)
    eff.u32(E_KIND, kind)
    eff[E_DEF:E_DEF + 0x30] = d
    st = source_type if source_type is not None else r.choice([0, 1, 1, 2, 3])
    eff.u32(E_SOURCE, st)
    if st == 2:
        eff.u32(E_SOURCE + 4, 0xffffffff)
        eff.u32(E_SOURCE + 8, FAKE_LOC)
    else:
        eff.u32(E_SOURCE + 4, source_char if source_char is not None else r.randrange(8))
        eff.u32(E_SOURCE + 8, 0xffffffff)
    if st == 3:
        eff.u8(E_SOURCE + 0x1c, 1 if r.random() < 0.7 else 0)
    eff.u32(E_TARGET, 1)
    eff.u32(E_TARGET + 4, r.randrange(8))
    eff.u32(E_TARGET + 8, 0xffffffff)
    eff.u32(E_TARGET + 0xc, 0xffffffff)
    return eff


def pick_targets(r, n_max=6):
    n = r.choice([1, 1, 2, 3, 4, 6, r.randrange(1, n_max + 1)])
    return [r.randrange(8) for _ in range(n)]


def mutate_char_state(r, b, heavy=False):
    """hp/stamina/conditions/enchantments mutations shared by the effect functions."""
    hpmax = b.get_i32(C_HPMAX)
    if hpmax <= 0:
        hpmax = 50
        b.u32(C_HPMAX, hpmax)
    if r.random() < 0.6:
        b.u32(C_HP, r.choice([hpmax, 1, 2, max(1, hpmax // 2), max(1, hpmax // 10),
                              r.randrange(1, hpmax + 1), 0 if heavy else hpmax]))
    stmax = b.get_i32(C_STMAX)
    if stmax <= 0:
        stmax = 100
        b.u32(C_STMAX, stmax)
    if r.random() < 0.5:
        b.u32(C_ST, r.choice([stmax, 0, 1, 5, 9, 10, stmax // 2, r.randrange(0, stmax + 1)]))
    if r.random() < 0.4:
        for _ in range(r.randrange(1, 4)):
            k = r.choice([1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17])
            b.u32(C_COND + 4 * k, r.choice([1, 2, 3, 5, 10, 30, INDEF]))
            if k == 7:
                b.u32(C_COND_ARG, r.choice([1, 3, 10, 40]))
    if r.random() < 0.3:
        k = r.randrange(1, 8)
        b.u32(C_ENCH + ENCH_STEP * k, r.choice([1, 2, 3, 5, 7]))
        b.u16(C_ENCH + ENCH_STEP * k + 4, r.choice([0, 10, 50, 100]))
        b.u16(C_ENCH + ENCH_STEP * k + 6, r.choice([0, 5, 20, 100]))
        b.u32(C_ENCH + ENCH_STEP * k + 8, r.choice([1, 2, 5, 10, 30, 100]))
    if r.random() < 0.2:
        b.u32(C_PROF, r.choice([2, 4, 13, 6, 10, 0, 14]))
    if r.random() < 0.15:
        b.u32(C_RACE, r.choice([0, 1, 2, 5, 6, 7, 8, 9, 10]))
    fix_highest(b)
    fix_ench_top(b)


def char_resist_mutation(r, b, realm):
    if r.random() < 0.5:
        b.u32(C_LEVEL, r.choice([0, 1, 2, 5, 8, 10, 14, 16, 20, 25, 30, 50, 0xffffffff]))
    if r.random() < 0.5 and 0 <= realm < 6:
        b.u32(C_RES + RES_STEP * realm + 4,
              r.choice([0, 1, 5, 25, 50, 75, 95, 99, 100, 101, 150, 0xffffffff, 0xffffff9c,
                        0x7fffffff, 0x80000000]))


# --------------------------------------------------------------------------- pure helpers

def gen_roll_magnitude(ctx, e):
    fn = ctx.fn(0x00551a20)
    for i in range(ctx.n(300)):
        r = ctx.rng('rollmag', i)
        c = ctx.case('rollmag.%d' % i, fn, conv='c', ret='i')
        d = Blob(bytes(r.randrange(256) for _ in range(0x30)))
        m = i % 8
        if m < 3:
            base, count, sides = r.randrange(-10, 61), r.randrange(1, 13), r.choice([2, 3, 4, 6, 8, 10, 12, 20])
        elif m == 3:
            base, count, sides = r.choice([(9999, 0, 7), (9998, 1, 1), (9997, 1, 2), (10000, 0, 0),
                                           (9990, 3, 6), (9989, 10, 1), (0, 0, 0), (1, 0, 0)])
        elif m == 4:
            base, count, sides = r.randrange(-50, 50), r.randrange(0, 20), 0
        elif m == 5:
            base, count, sides = r.choice([-32768, -1, 32767, 0]), r.choice([255, 128, 1]), r.choice([255, 1, 100])
        elif m == 6:
            base, count, sides = r.choice([-1, -2, -100, -5000]), r.randrange(0, 3), r.randrange(1, 4)
        else:
            base, count, sides = r.randrange(-32768, 32768), r.randrange(256), r.randrange(256)
        pct = r.choice([0, 0, 5, 10, 25, 33, 50, 75, 100, 150, 200, 1000, 100000, 0x7fffffff,
                        0x80000000, 0xffffffff, r.randrange(0, 300)])
        d.u16(D_DICE, base)
        d.u8(D_DICE + 2, count)
        d.u8(D_DICE + 3, sides)
        d.u32(D_PERCENT, pct)
        c.set(e.s0, bytes(d))
        c.arg(e.s0)
        c.cap(e.s0, 0x30, 'def')
        c.note(base=base, count=count, sides=sides, percent=pct)
        finish(c)


def gen_roll_duration(ctx, e):
    fn = ctx.fn(0x005519c0, '?RollEffectDuration@@YAIPAUW8SpellEffectDefinition@@@Z')
    for i in range(ctx.n(300)):
        r = ctx.rng('rolldur', i)
        c = ctx.case('rolldur.%d' % i, fn, conv='c', ret='i')
        d = Blob(bytes(r.randrange(256) for _ in range(0x30)))
        m = i % 6
        if m < 3:
            per, scale, base = r.randrange(0, 13), r.randrange(1, 8), r.randrange(0, 41)
        elif m == 3:
            total = r.choice([9999, 9998, 10000, 0, 1, 2, 3, 0xffffffff, 0xfffffffe, 0x7fffffff,
                              0x80000000, 9997])
            per, scale = r.choice([(0, 0), (1, 0), (0, 5), (3, 2)])
            base = u32(total - per * scale)
        elif m == 4:
            per, scale, base = r.choice([-1, -5, 3, 100000]), r.choice([-1, 2, 7, 0x10000]), r.randrange(-20, 20)
        else:
            per, scale, base = r.randrange(1 << 32), r.randrange(1 << 32), r.randrange(1 << 32)
        pct = r.choice([0, 0, 0, 10, 25, 50, 100, 200, 0xffffffff, 0x80000000, r.randrange(0, 150)])
        d.u32(D_DUR_PER, per)
        d.u32(D_SCALE, scale)
        d.u32(D_DUR_BASE, base)
        d.u32(D_PERCENT, pct)
        c.set(e.s0, bytes(d))
        c.arg(e.s0)
        c.cap(e.s0, 0x30, 'def')
        c.note(per_power=per, scale=scale, base=base, percent=pct)
        finish(c)


def gen_display_slot(ctx, e):
    fn = ctx.fn(0x00551900)
    vals = list(range(-3, 141)) + [0x7fffffff, -0x80000000, 0x12, 0x13, 0x41, 0x42, 0x10000013,
                                   0x113, -0x13, 1000, 0xff13, 65, 56, 61]
    for i, v in enumerate(vals[:ctx.n(160)]):
        c = ctx.case('dispslot.%d' % i, fn, conv='c', ret='i')
        c.arg(v)
        c.note(spell_id=v)
        finish(c)


def gen_resistances(ctx, e):
    fn = ctx.fn(0x00551a60)
    for i in range(ctx.n(300)):
        r = ctx.rng('resist', i)
        c = ctx.case('resist.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        blob, name = ctx.pick_char(r)
        base = bytes(blob)
        c.setb(ctx.char(slot), base)
        b = Blob(blob)
        for s in range(6):
            if r.random() < 0.6:
                b.u32(C_SKILL + (28 + s) * SKILL_STEP + 6,
                      r.choice([0, 1, 9, 10, 11, 19, 20, 50, 99, 100, 101, 125, r.randrange(126),
                                0xffffffff, 0x80000000]))
        if r.random() < 0.5:
            b.u8(C_SKILL + SK_IRON_WILL * SKILL_STEP, r.choice([0, 1]))
            b.u32(C_SKILL + SK_IRON_WILL * SKILL_STEP + 6,
                  r.choice([0, 4, 5, 9, 10, 50, 100, 125, r.randrange(126), 0xfffffffb]))
        if r.random() < 0.4:
            b.u32(C_PROF, r.choice(list(range(15)) + [14, 14, 0xffffffff, 15]))
        if r.random() < 0.5:
            b.u32(C_RACE, r.choice(list(range(16)) + [0xffffffff, 0xffffffff, 2, 3, 4]))
        for a in (ATTR_VITALITY, 0, ATTR_INT, ATTR_PIETY):
            if r.random() < 0.35:
                b.u32(C_ATTR + a * ATTR_STEP, r.choice([0, 4, 5, 9, 10, 49, 50, 99, 100, 125,
                                                       0xffffffff]))
        for a in (ATTR_INT, ATTR_PIETY):
            if r.random() < 0.5:
                b.u32(C_ATTR + a * ATTR_STEP + 4, r.choice([0, 79, 80, 81, 82, 83, 90, 100, 125,
                                                           200, 0xffffffff, 0x80000050]))
        if r.random() < 0.5:
            b.u8(C_BONUS_ALL, r.choice([-128, -100, -50, -1, 0, 1, 35, 50, 100, 127]))
        for s in range(6):
            if r.random() < 0.3:
                b.u8(C_BONUS_RES + s, r.choice([-128, -75, -25, -1, 0, 5, 20, 50, 100, 120, 127]))
        if r.random() < 0.3:
            for s in range(6):
                b.u32(C_RES + RES_STEP * s, r.randrange(1 << 32))
                b.u32(C_RES + RES_STEP * s + 4, r.randrange(1 << 32))
        emit_diff(c, ctx.char(slot), base, bytes(b))
        c.arg(ctx.char(slot))
        c.cap(ctx.char(slot), CHAR, 'char')
        c.note(char=name, slot=slot)
        finish(c)


# --------------------------------------------------------------------------- resistance rolls

def resist_target(ctx, c, e, r, monster_ok=True, monster_share=0.35, over=None):
    """W8CombatSlot for S0_SLOT plus ('char', slot, None) or ('mon', k, mons)."""
    slot_blob = Blob(0x20)
    slot_blob.u32(0xc, 0xffffffff)
    if monster_ok and r.random() < monster_share:
        mons = [new_monster(r, over) for _ in range(r.choice([1, 1, 2, 3]))]
        k = r.randrange(len(mons))
        slot_blob.u32(0x0, 3)
        slot_blob.u32(0x4, r.choice([0xffffffff, 0, 3]))
        slot_blob.u32(0x8, FAKE_LOC + k)
        return slot_blob, ('mon', k, mons)
    t = r.randrange(8)
    slot_blob.u32(0x0, r.choice([1, 1, 1, 1, 1, 1, 0, 2, 4, 9]))
    slot_blob.u32(0x4, t)
    slot_blob.u32(0x8, r.choice([0xffffffff, FAKE_LOC]))
    return slot_blob, ('char', t, None)


def realm_power(r):
    realm = r.choice([0, 1, 2, 3, 4, 5, 0, 1, 2, 3, 4, 5, 6, 7]) if r.random() < 0.1 else r.randrange(6)
    power = r.choice([-50, -1, 0, 1, 2, 3, 4, 5, 7, 10, 15, 20, 30, 50, 100, 0x7fffffff,
                      -0x80000000, r.randrange(1, 40)])
    return realm, power


def gen_reduce(ctx, e, name, addr, count, announce):
    fn = ctx.fn(addr)
    for i in range(ctx.n(count)):
        r = ctx.rng(name, i)
        c = ctx.case('%s.%d' % (name, i), fn, conv='c', ret='v')
        realm, power = realm_power(r)
        verbose = 0
        slot_blob, (kind, idx, mons) = resist_target(ctx, c, e, r)
        if announce and kind == 'char' and r.random() < 0.4:
            verbose = 1
        set_globals(c, e, difficulty=r.choice([0, 1, 2]), verbose=verbose)
        if kind == 'char':
            p = party(ctx, c, e, r, rows=announce)
            char_resist_mutation(r, p[idx][1], realm)
            commit_party(c, e, p)
            wire_monsters(c, e, [])
        else:
            wire_monsters(c, e, mons)
        mag = r.choice([0, 1, 2, 3, 10, 50, 100, 250, 1000, 9998, 9999, 10000, 0x7fffffff,
                        0x80000000, 0xffffffff, 42949672, 42949673, r.randrange(1, 500)])
        c.set(e.s0 + S0_MAG, p32(mag))
        c.set(e.s0 + S0_SLOT, bytes(slot_blob))
        c.arg(e.s0 + S0_MAG).arg(e.s0 + S0_SLOT).arg(realm).arg(power)
        c.cap(e.s0 + S0_MAG, 4, 'magnitude')
        c.cap(e.s0 + S0_SLOT, 0x20, 'target')
        if kind == 'mon':
            c.cap(e.s1, MI_STRIDE * (len(mons) - 1) + MI_SIZE, 'monsters')
        c.note(target=kind, idx=idx, realm=realm, power=power, magnitude=mag, verbose=verbose)
        finish(c)


def gen_target_resists(ctx, e):
    fn = ctx.fn(0x005520d0)
    for i in range(ctx.n(400)):
        r = ctx.rng('tresist', i)
        c = ctx.case('tresist.%d' % i, fn, conv='c', ret='b')
        realm, power = realm_power(r)
        if realm > 5:
            realm = r.randrange(6)
        cond = r.randrange(20)
        diff = r.choice([0, 1, 2, 0, 1, 2, 3])
        slot_blob, (kind, idx, mons) = resist_target(ctx, c, e, r)
        set_globals(c, e, difficulty=diff, verbose=r.choice([0, 1]), pick=1,
                    surprise=r.choice([0, 1]))
        if kind == 'char':
            p = party(ctx, c, e, r)
            b = p[idx][1]
            char_resist_mutation(r, b, realm)
            if r.random() < 0.3:
                b.u32(C_COND + 4 * 13, r.choice([1, 5, INDEF]))
            if r.random() < 0.15:
                b.u32(C_COND + 4 * r.choice([18, 19]), INDEF)
            fix_highest(b)
            if r.random() < 0.1:
                b.u32(C_HIGHEST, r.choice([17, 18, 19, 20, 0xffffffff]))
            sk = C_SKILL + SK_IRON_WILL * SKILL_STEP
            if r.random() < 0.6:
                b.u8(sk, 1)
                b.u32(sk + 2, r.choice([0, 1, 10, 50, 98, 99, 100, 101, r.randrange(100)]))
                b.u32(sk + 0xa, r.choice([0, 10, 50, 75, 100, 125, r.randrange(126)]))
                b.u32(sk + 0xe, r.choice([0, 6, 7, 7, 7, r.randrange(8)]))
                if r.random() < 0.3:
                    b.u32(C_PROF, r.choice(list(range(15))))
            elif r.random() < 0.3:
                b.u8(sk, 0)
            commit_party(c, e, p)
            wire_monsters(c, e, [])
        else:
            mi, mr = mons[idx]
            if r.random() < 0.25:
                mi.u32(MI_HIGHEST, r.choice([17, 18, 19, 0xffffffff]))
            mi.u8(MI_DISP, r.choice([0, 1, 2, 3]))
            wire_monsters(c, e, mons)
        c.set(e.s0 + S0_SLOT, bytes(slot_blob))
        c.arg(e.s0 + S0_SLOT).arg(realm).arg(power).arg(cond)
        c.cap(e.s0 + S0_SLOT, 0x20, 'target')
        if kind == 'char':
            cap_world(c, e)
        else:
            c.cap(e.s1, MI_STRIDE * (len(mons) - 1) + MI_SIZE, 'monsters')
        c.note(target=kind, idx=idx, realm=realm, power=power, condition=cond, difficulty=diff)
        finish(c)


def condition_pick(r):
    return r.choice([1, 2, 3, 4, 5, 5, 6, 6, 7, 7, 8, 9, 10, 11, 11, 12, 13, 13, 14, 15, 16, 17,
                     0, 18, 19])


def gen_inflict(ctx, e):
    fn = ctx.fn(0x00551eb0)
    for i in range(ctx.n(350)):
        r = ctx.rng('inflict', i)
        c = ctx.case('inflict.%d' % i, fn, conv='c', ret='i8')
        realm, power = realm_power(r)
        if realm > 5:
            realm = r.randrange(6)
        cond = condition_pick(r)
        announce = r.choice([0, 1])
        mag = r.choice([0, 1, 1, 2, 3, 5, 10, 20, 50, 100, 9998, 9999, 10000, 0xffffffff,
                        r.randrange(1, 60)])
        arg = 0
        if cond == 7:
            arg = r.choice([0, 1, 5, 20, 60])
        elif r.random() < 0.05:
            arg = r.randrange(1, 10)
        set_globals(c, e, difficulty=r.choice([0, 1, 2]), verbose=r.choice([0, 1]),
                    surprise=r.choice([0, 1]), pick=1)
        monster = r.random() < 0.18
        slot_blob = Blob(0x20)
        slot_blob.u32(0xc, 0xffffffff)
        mons = []
        p = party(ctx, c, e, r)
        if monster:
            mons = [new_monster(r) for _ in range(r.choice([1, 2]))]
            k = r.randrange(len(mons))
            mi = mons[k][0]
            announce = 0
            if r.random() < 0.5:
                mag = 0
            else:
                cond = 5
                mag = r.choice([1, 2, 5, 20, 9999])
                mi.u32(MI_ENCH + ENCH_STEP * 5, r.choice([1, 3]))
                mi.u32(MI_ENCH + ENCH_STEP * 5 + 8, mag + r.choice([1, 2, 10, 500]))
            slot_blob.u32(0x0, 3)
            slot_blob.u32(0x8, FAKE_LOC + k)
            idx = k
        else:
            t = r.randrange(8)
            idx = t
            slot_blob.u32(0x0, 1)
            slot_blob.u32(0x4, t)
            b = p[t][1]
            mutate_char_state(r, b)
            char_resist_mutation(r, b, realm)
            if cond == 5 and r.random() < 0.7:
                b.u32(C_ENCH + ENCH_STEP * 5, r.choice([1, 3]))
                b.u32(C_ENCH + ENCH_STEP * 5 + 8, r.choice([1, 2, 3, mag, u32(mag + 1),
                                                           max(1, mag // 2), 100]))
            if r.random() < 0.3:
                b.u32(C_COND + 4 * cond, r.choice([1, 2, 5, 100, INDEF]))
            fix_highest(b)
            fix_ench_top(b)
        commit_party(c, e, p)
        wire_monsters(c, e, mons)
        c.set(e.s0 + S0_SLOT, bytes(slot_blob))
        src_char = r.choice([-1, 0, 2, 5, 7])
        dur = r.choice([0, 0, 1, 2, 0x100])
        c.arg(e.s0 + S0_SLOT).arg(cond).arg(realm).arg(power).arg(arg).arg(mag)
        c.arg(src_char).arg(dur).arg(announce)
        c.cap(e.s0 + S0_SLOT, 0x20, 'target')
        cap_world(c, e, monsters=len(mons))
        c.note(target='mon' if monster else 'char', idx=idx, condition=cond, realm=realm,
               power=power, argument=arg, magnitude=mag, announce=announce)
        finish(c)


def gen_resolve(ctx, e):
    fn = ctx.fn(0x00551BA0)
    for i in range(ctx.n(400)):
        r = ctx.rng('resolve', i)
        c = ctx.case('resolve.%d' % i, fn, conv='c', ret='b')
        realm, power = realm_power(r)
        if realm > 5:
            realm = r.randrange(6)
        cond = condition_pick(r)
        ann_res, ann_cond = r.choice([0, 1]), r.choice([0, 1])
        verbose = r.choice([0, 1])
        mag = r.choice([0, 1, 2, 3, 5, 10, 20, 50, 100, 9999, 10000, r.randrange(1, 60)])
        arg = r.choice([0, 1, 5, 20]) if cond == 7 else 0
        monster = r.random() < 0.25
        mons = []
        slot_blob = Blob(0x20)
        slot_blob.u32(0xc, 0xffffffff)
        p = party(ctx, c, e, r)
        if monster:
            mons = [new_monster(r) for _ in range(r.choice([1, 2]))]
            k = r.randrange(len(mons))
            mi, mr = mons[k]
            path = r.randrange(5)
            if path == 0:
                cond = 18
                mr.u8(MR_DEATH_IMMUNE, 1)
            elif path == 1:
                kk = r.choice([20, 22, 17])
                mr.u8(MR_KIND, kk)
                cond = r.choice(IMMUNE[kk])
            elif path == 2:
                mi.u32(MI_HIGHEST, r.choice([18, 19, 0xffffffff]))
            elif path == 3:
                cond = 19
            else:
                mag = 0
                if verbose:
                    ann_res = 0
            slot_blob.u32(0x0, 3)
            slot_blob.u32(0x8, FAKE_LOC + k)
            idx = k
        else:
            t = r.randrange(8)
            idx = t
            slot_blob.u32(0x0, 1)
            slot_blob.u32(0x4, t)
            b = p[t][1]
            mutate_char_state(r, b)
            char_resist_mutation(r, b, realm)
            if cond == 19 and r.random() < 0.5:
                b.u32(C_COND + 4 * 19, INDEF)
            if r.random() < 0.35:
                b.u32(C_PROF, r.choice([4, 13, 2, 0, 6]))
            if r.random() < 0.1:
                b.u32(C_COND + 4 * 18, INDEF)
            fix_highest(b)
        commit_party(c, e, p)
        set_globals(c, e, difficulty=r.choice([0, 1, 2]), verbose=verbose,
                    surprise=r.choice([0, 1]), pick=1)
        wire_monsters(c, e, mons)
        src = Blob(0x34)
        st = r.choice([0, 1, 1, 2, 3])
        src.u32(0, st)
        src.u32(4, r.randrange(8) if st in (1, 3) else 0xffffffff)
        src.u32(8, FAKE_LOC if st in (2, 3) else 0xffffffff)
        if st == 3:
            src.u8(0x1c, 1)
        c.set(e.s0 + S0_SOURCE, bytes(src))
        c.set(e.s0 + S0_SLOT, bytes(slot_blob))
        dur = r.choice([0, 0, 1, 5])
        c.arg(e.s0 + S0_SOURCE).arg(e.s0 + S0_SLOT).arg(cond).arg(realm).arg(power).arg(arg)
        c.arg(mag).arg(ann_res).arg(ann_cond).arg(dur)
        c.cap(e.s0 + S0_SLOT, 0x20, 'target')
        cap_world(c, e, monsters=len(mons))
        c.note(target='mon' if monster else 'char', idx=idx, condition=cond, realm=realm,
               power=power, magnitude=mag, ann_res=ann_res, ann_cond=ann_cond, verbose=verbose)
        finish(c)


# --------------------------------------------------------------------------- effect handlers

def gen_apply_condition(ctx, e):
    fn = ctx.fn(0x0054e3f0)
    for i in range(ctx.n(300)):
        r = ctx.rng('applycond', i)
        c = ctx.case('applycond.%d' % i, fn, conv='c', ret='v')
        slot = r.choice([5, 5, 5, 1, 2, 3, 4, 6, 7, 0])
        d = rand_definition(r)
        if r.random() < 0.3:
            d.u32(D_SCALE, r.choice([0, 1, 2, 5, 7, 10, 0xffffffff]))
        targets = pick_targets(r)
        set_globals(c, e, difficulty=1, verbose=r.choice([0, 1]), surprise=r.choice([0, 1]))
        p = party(ctx, c, e, r)
        for t in set(targets):
            b = p[t][1]
            mutate_char_state(r, b)
            if r.random() < 0.5:
                b.u32(C_ENCH + ENCH_STEP * slot, r.choice([0, 1, 2, 5, 7, 10]))
                b.u32(C_ENCH + ENCH_STEP * slot + 8, r.choice([0, 1, 5, 30]))
            if slot == 5 and r.random() < 0.6:
                b.u32(C_COND + 4 * 5, r.choice([1, 2, 3, 5, 10, 30, INDEF]))
            fix_highest(b)
            fix_ench_top(b)
        commit_party(c, e, p)
        wire_monsters(c, e, [])
        eff = new_effect(r, r.choice([56, 19, 21, 27, 54, 61, 65]), d)
        write_effect(c, e, eff, targets, [])
        c.arg(e.s0).arg(slot)
        cap_world(c, e, effect=True)
        c.note(slot=slot, targets=targets, scale=d.get_u32(D_SCALE))
        finish(c)


def gen_fatigue(ctx, e):
    fn = ctx.fn(0x0054f8c0)
    for i in range(ctx.n(300)):
        r = ctx.rng('fatigue', i)
        c = ctx.case('fatigue.%d' % i, fn, conv='c', ret='v')
        d = rand_definition(r)
        targets = pick_targets(r) if r.random() < 0.85 else []
        set_globals(c, e, difficulty=1, verbose=r.choice([0, 1]), surprise=r.choice([0, 1]))
        p = party(ctx, c, e, r)
        for t in set(targets):
            b = p[t][1]
            mutate_char_state(r, b)
            if r.random() < 0.3:
                b.u8(C_DEEP_FATIGUE, r.choice([0, 1]))
            if r.random() < 0.3:
                b.u32(C_FATIGUE_BAND, r.choice([0, 1, 2, 3, 4]))
            if r.random() < 0.2:
                b.u32(C_COND + 4 * 17, r.choice([0, 3, INDEF]))
                fix_highest(b)
        commit_party(c, e, p)
        mons = []
        if r.random() < 0.5 or not targets:
            mons = [new_monster(r) for _ in range(r.choice([1, 2, 3]))]
            for mi, mr in mons:
                stmax = mi.get_u32(MI_STMAX)
                mi.u32(MI_ST, r.choice([stmax, 1, 0, 5, 0xfffffff6, r.randrange(1, stmax + 1)]))
                mi.u32(MI_COND + 4 * 17, INDEF)
                mi.u32(MI_HIGHEST, 17)
                if r.random() < 0.15:
                    mi.u32(MI_HP, 0)
        wire_monsters(c, e, mons)
        mids = [FAKE_LOC + k for k in range(len(mons))]
        if len(mids) > 1 and r.random() < 0.3:
            mids.append(mids[0])
        eff = new_effect(r, r.choice([13, 42, 76, 80, 0]), d)
        write_effect(c, e, eff, targets, mids)
        c.arg(e.s0)
        cap_world(c, e, effect=True, monsters=len(mons))
        c.note(targets=targets, monsters=len(mids))
        finish(c)


def stamina_or_heal_case(ctx, e, name, addr, count, heal):
    fn = ctx.fn(addr)
    for i in range(ctx.n(count)):
        r = ctx.rng(name, i)
        c = ctx.case('%s.%d' % (name, i), fn, conv='c', ret='b')
        d = rand_definition(r, small_dice=True)
        if r.random() < 0.15:
            d.u16(D_DICE, r.choice([0, 9999, 500]))
            d.u8(D_DICE + 2, 0)
        targets = pick_targets(r) if r.random() < 0.9 else []
        verbose = r.choice([0, 1])
        set_globals(c, e, difficulty=1, verbose=verbose, surprise=r.choice([0, 1]))
        p = party(ctx, c, e, r)
        counted_chars = 0
        for t in set(targets):
            b = p[t][1]
            mutate_char_state(r, b, heavy=True)
            if heal and r.random() < 0.15:
                b.u32(C_HP, b.get_i32(C_HPMAX) + r.choice([1, 50]))
            if not heal and r.random() < 0.2:
                b.u32(C_COND + 4 * 17, INDEF)
                b.u32(C_ST, r.choice([0, 5, 9]))
                fix_highest(b)
        for t in targets:
            b = p[t][1]
            if heal:
                if u32(b.get_i32(C_HPMAX) - b.get_u32(C_HP)) != 0:
                    counted_chars += 1
            else:
                if b.get_i32(C_ST) != b.get_i32(C_STMAX):
                    counted_chars += 1
        commit_party(c, e, p)
        mons = []
        if r.random() < 0.45:
            for _ in range(r.choice([1, 2])):
                mi, mr = new_monster(r)
                if heal:
                    hpmax = mi.get_u32(MI_HPMAX)
                    if verbose or counted_chars == 0:
                        mi.u32(MI_HP, hpmax)             # not counted: no name lookup
                    else:
                        mi.u32(MI_HP, r.choice([hpmax, 0, 1, r.randrange(1, hpmax + 1)]))
                else:
                    stmax = mi.get_u32(MI_STMAX)
                    if not verbose or r.random() < 0.4:
                        # counted monsters would be named by the quiet summary
                        mi.u32(MI_ST, stmax)
                    else:
                        # RestoreMonsterStamina names the monster unless it is dead.
                        mi.u32(MI_ST, r.randrange(0, stmax))
                        if r.random() < 0.5:
                            mi.u32(MI_HP, 0)
                        else:
                            mi.u32(MI_COND + 4 * 18, INDEF)
                            mi.u32(MI_HIGHEST, 18)
                mons.append((mi, mr))
        wire_monsters(c, e, mons)
        mids = [FAKE_LOC + k for k in range(len(mons))]
        eff = new_effect(r, r.choice([6, 13, 68, 100, 114, 0]), d)
        write_effect(c, e, eff, targets, mids)
        c.arg(e.s0)
        cap_world(c, e, effect=True, monsters=len(mons))
        c.note(targets=targets, monsters=len(mids), verbose=verbose)
        finish(c)


def gen_damage(ctx, e):
    fn = ctx.fn(0x0054e950)
    for i in range(ctx.n(300)):
        r = ctx.rng('damage', i)
        c = ctx.case('damage.%d' % i, fn, conv='c', ret='v')
        d = rand_definition(r)
        targets = pick_targets(r)
        verbose = r.choice([0, 1])
        set_globals(c, e, difficulty=r.choice([0, 1, 2]), verbose=verbose, surprise=1)
        p = party(ctx, c, e, r)
        realm = r.randrange(6)
        for t in set(targets):
            b = p[t][1]
            mutate_char_state(r, b)
            char_resist_mutation(r, b, realm)
            if r.random() < 0.25:
                b.u32(C_ENCH + ENCH_STEP * 2, r.choice([1, 3]))
                b.u16(C_ENCH + ENCH_STEP * 2 + 6, r.choice([0, 1, 5, 20, 200]))
                b.u32(C_ENCH + ENCH_STEP * 2 + 8, r.choice([1, 5, 30]))
            if r.random() < 0.2:
                b.u32(C_COND + 4 * 15, r.choice([1, 5, INDEF]))
            fix_highest(b)
            fix_ench_top(b)
        commit_party(c, e, p)
        wire_monsters(c, e, [])
        kind = r.choice([1, 4, 5, 9, 25, 36, 43, 48, 57, 71, 78, 83, 98, r.randrange(1, 132)])
        eff = new_effect(r, kind, d)
        write_effect(c, e, eff, targets, [])
        c.arg(e.s0)
        cap_world(c, e, effect=True)
        c.note(kind=kind, targets=targets, verbose=verbose)
        finish(c)


def gen_drain(ctx, e):
    fn = ctx.fn(0x0054ec80)
    for i in range(ctx.n(300)):
        r = ctx.rng('drain', i)
        c = ctx.case('drain.%d' % i, fn, conv='c', ret='v')
        d = rand_definition(r)
        targets = pick_targets(r) if r.random() < 0.95 else []
        st = r.choice([1, 1, 1, 2, 2, 0, 3])
        verbose = 0 if st == 2 else r.choice([0, 1])
        set_globals(c, e, difficulty=r.choice([0, 1, 2]), verbose=verbose, surprise=1)
        p = party(ctx, c, e, r)
        for t in set(targets):
            b = p[t][1]
            mutate_char_state(r, b)
            char_resist_mutation(r, b, r.randrange(6))
            fix_highest(b)
        for s in range(8):
            other = p[s][1]
            hpmax = other.get_i32(C_HPMAX)
            if r.random() < 0.2 and hpmax > 0:
                other.u32(C_HP, r.randrange(1, hpmax + 1))
            if r.random() < 0.2:
                for k in range(6):
                    mx = other.get_i32(C_SPMAX + 4 * k)
                    if mx > 0:
                        other.u32(C_SPLEFT + 4 * k, r.randrange(0, mx + 1))
        commit_party(c, e, p)
        mons = []
        if st == 2:
            mi, mr = new_monster(r)
            if r.random() < 0.3:
                mi.u32(MI_HP, mi.get_u32(MI_HPMAX))
            mi.u32(MI_SPELL_POINTS, r.choice([0, 5, 100, 0xfffffff0]))
            mons = [(mi, mr)]
        wire_monsters(c, e, mons)
        kind = r.choice([SPELL_LIFESTEAL, SPELL_LIFESTEAL, SPELL_MIGHT_TO_MAGIC,
                         SPELL_MIGHT_TO_MAGIC, 80, 66, 91])
        eff = new_effect(r, kind, d, source_type=st)
        write_effect(c, e, eff, targets, [])
        c.arg(e.s0)
        cap_world(c, e, effect=True, monsters=len(mons))
        c.note(kind=kind, source=st, targets=targets, verbose=verbose)
        finish(c)


def cure_power(d):
    scale = d.get_u32(D_SCALE)
    power = u32(scale * scale)
    return u32(power + u32(power * d.get_u32(D_PERCENT)) // 100)


def gen_cure(ctx, e):
    fn = ctx.fn(0x0054df00)
    for i in range(ctx.n(350)):
        r = ctx.rng('cure', i)
        c = ctx.case('cure.%d' % i, fn, conv='c', ret='b')
        d = rand_definition(r)
        if r.random() < 0.3:
            d.u32(D_SCALE, r.choice([0, 1, 2, 6, 7, 10]))
        cond = r.choice([1, 2, 3, 4, 5, 6, 7, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 18,
                         18, 19, 0])
        force = 1 if r.random() < 0.25 else 0
        verbose = r.choice([0, 1])
        targets = pick_targets(r) if r.random() < 0.9 else []
        set_globals(c, e, difficulty=1, verbose=verbose, surprise=r.choice([0, 1]))
        p = party(ctx, c, e, r)
        for t in set(targets):
            b = p[t][1]
            mutate_char_state(r, b)
            if r.random() < 0.8:
                b.u32(C_COND + 4 * cond, r.choice([1, 2, 3, 4, 9, 16, 49, 50, 100, INDEF, INDEF]))
                if cond == 7:
                    b.u32(C_COND_ARG, r.choice([1, 5, 20, 100]))
                if cond == 18:
                    b.u32(C_HP, 0)
                    b.u32(C_ST, 0)
                    for a in (ATTR_PIETY, ATTR_VITALITY):
                        if r.random() < 0.5:
                            b.u32(C_ATTR + a * ATTR_STEP + 4, r.choice([0, 1, 4, 8, 50, 100, 125]))
                    if r.random() < 0.3:
                        b.u32(C_HPMAX, r.choice([1, 2, 7, 1000]))
                        b.u32(C_STMAX, r.choice([1, 3, 1000]))
            fix_highest(b)
        commit_party(c, e, p)
        mons = []
        power = cure_power(d)
        if r.random() < 0.4:
            for _ in range(r.choice([1, 2])):
                mi, mr = new_monster(r)
                if not force and power < INDEF - 2 and r.random() < 0.8:
                    turns = r.randrange(power + 1, min(INDEF, power + 200))
                    if turns == INDEF:
                        turns = INDEF - 1
                    if cond != 19:
                        mi.u32(MI_COND + 4 * cond, turns)
                mons.append((mi, mr))
        wire_monsters(c, e, mons)
        mids = [FAKE_LOC + k for k in range(len(mons))]
        eff = new_effect(r, r.choice([16, 34, 35, 51, 58, 74, 88, 100]), d)
        tt = r.choice([1, 1, 1, 0, 2])
        eff.u32(E_TARGET, tt)
        eff.u32(E_TARGET + 4, r.choice(targets) if (tt == 1 and targets) else r.randrange(8))
        if r.random() < 0.2:
            eff.u8(E_REPORTED, 1)
        write_effect(c, e, eff, targets, mids)
        c.arg(e.s0).arg(cond).arg(force)
        cap_world(c, e, effect=True, monsters=len(mons))
        c.note(condition=cond, force=force, power=power, targets=targets, monsters=len(mids),
               verbose=verbose)
        finish(c)


def gen_attack(ctx, e):
    fn = ctx.fn(0x0054d5c0)
    for i in range(ctx.n(350)):
        r = ctx.rng('attack', i)
        c = ctx.case('attack.%d' % i, fn, conv='c', ret='v')
        d = rand_definition(r)
        kind = r.choice([SPELL_SLOW, SPELL_SLOW, SPELL_TERROR, SPELL_TERROR, SPELL_SONIC_BOOM,
                         12, 11, 24, 15, 31, 46, 69, 3, 7, 42, 89, r.randrange(1, 132)])
        cond = condition_pick(r)
        if kind == SPELL_SLOW and r.random() < 0.7:
            cond = 5
        chance = r.choice([100, 100, 50, 0, 1, 99, 101, 200, -1, -100])
        arg = r.choice([0, 1, 5, 30]) if cond == 7 else 0
        verbose = r.choice([0, 1])
        targets = pick_targets(r) if r.random() < 0.9 else []
        set_globals(c, e, difficulty=r.choice([0, 1, 2]), verbose=verbose,
                    surprise=r.choice([0, 1]), pick=1)
        p = party(ctx, c, e, r)
        for t in set(targets):
            b = p[t][1]
            mutate_char_state(r, b)
            char_resist_mutation(r, b, r.randrange(6))
            if kind == SPELL_SLOW and r.random() < 0.5:
                b.u32(C_ENCH + ENCH_STEP * 5, r.choice([1, 3]))
                b.u32(C_ENCH + ENCH_STEP * 5 + 8, r.choice([1, 2, 3, 5, 10, 50, 1000]))
            fix_highest(b)
            fix_ench_top(b)
        commit_party(c, e, p)
        mons = []
        if r.random() < 0.35:
            bound = max_duration(d)
            for _ in range(r.choice([1, 2])):
                mi, mr = new_monster(r)
                path = r.randrange(3)
                if path == 0:
                    mi.u32(MI_HIGHEST, r.choice([18, 19]))
                elif path == 1 and cond in (11, 6, 4, 2, 7, 3, 15, 17):
                    kk = [k for k, v in IMMUNE.items() if cond in v][0]
                    mr.u8(MR_KIND, kk)
                elif path == 2 and cond == 18:
                    mr.u8(MR_DEATH_IMMUNE, 1)
                else:
                    mi.u32(MI_HIGHEST, 18)
                if kind == SPELL_SLOW and bound is not None and bound < 0x10000000 and r.random() < 0.5:
                    mi.u32(MI_ENCH + ENCH_STEP * 5, 2)
                    mi.u32(MI_ENCH + ENCH_STEP * 5 + 8, bound + r.choice([1, 5, 100]))
                mons.append((mi, mr))
        wire_monsters(c, e, mons)
        mids = [FAKE_LOC + k for k in range(len(mons))]
        eff = new_effect(r, kind, d)
        if r.random() < 0.2:
            eff.u8(E_REPORTED, 1)
        write_effect(c, e, eff, targets, mids)
        c.arg(e.s0).arg(cond).arg(chance).arg(arg)
        cap_world(c, e, effect=True, monsters=len(mons))
        c.note(kind=kind, condition=cond, chance=chance, targets=targets, monsters=len(mids),
               verbose=verbose)
        finish(c)


# --------------------------------------------------------------------------- misc

def gen_screen_busy(ctx, e):
    fn = ctx.fn(0x00554540)
    for i in range(ctx.n(140)):
        r = ctx.rng('busy', i)
        c = ctx.case('busy.%d' % i, fn, conv='c', ret='b')
        combo = i % 64
        combat = combo & 1
        modal = (combo >> 1) & 1
        pick = (combo >> 2) & 1
        screen = 7 if (combo >> 3) & 1 == 0 else r.choice([0, 1, 6, 8, 12, 0xffffffff])
        idle_flag = (combo >> 4) & 3
        modes = [combat, 0, 0, 0, 0, 0]
        if idle_flag:
            modes[r.randrange(1, 6)] = r.choice([1, 0x80])
        if i >= 64:
            modes = [r.choice([0, 0, 1]) for _ in range(6)]
            screen = r.choice([7, 7, 3, 9])
        c.set(e.xs + XS_MODES, bytes(modes))
        c.set(e.xs + XS_PICK_PENDING, p8(pick))
        c.set(e.screen, p32(screen))
        if modal:
            c.setp(e.modal, e.s0)
        else:
            c.set(e.modal, p32(0))
        c.note(modes=modes, modal=modal, pick=pick, screen=screen)
        finish(c)


def gen_clear_slot(ctx, e):
    fn = ctx.fn(0x005524e0)
    effect_ids = [0x14, 0x20, 0x28, 0x11, 8, 0x21, 0x1a, 0x2d, 0x31, 2, 5, 0]
    for i in range(ctx.n(150)):
        r = ctx.rng('clearslot', i)
        c = ctx.case('clearslot.%d' % i, fn, conv='c', ret='v')
        mons = []
        for _ in range(r.choice([1, 2])):
            mi, mr = new_monster(r)
            for k in range(19):
                if r.random() < 0.15:
                    mi.u32(MI_COND + 4 * k, r.choice([1, 5, INDEF]))
            mi.u32(MI_COND_ARG, r.choice([0, 3, 20]))
            for k in range(8):
                if r.random() < 0.2:
                    mi.u32(MI_ENCH + ENCH_STEP * k, r.choice([1, 2, 5, 30]))
                    mi.u16(MI_ENCH + ENCH_STEP * k + 4, r.choice([0, 50, 100, 255]))
                    mi.u32(MI_ENCH + ENCH_STEP * k + 8, r.choice([1, 10]))
            for k in range(12):
                if r.random() < 0.3:
                    o = MI_SLOTS + 0x11 * k
                    mi.u8(o, r.choice([0, 1, 1]))
                    mi.u32(o + 1, r.choice(effect_ids + [r.randrange(150)]))
                    mi.u32(o + 5, r.choice([0, 1, 3, 7, 30, 200, 0xffffffff]))
                    mi.u32(o + 9, r.choice([0, 10, 50, 100, 300]))
                    mi.u32(o + 0xd, r.choice([1, 10, 100]))
            for k in range(0x67):
                if r.random() < 0.2:
                    mi.u8(MI_MODS + k, r.randrange(256))
            mons.append((mi, mr))
        k = r.randrange(len(mons))
        own = r.random() < 0.6
        if own:
            j = r.randrange(12)
            o = MI_SLOTS + 0x11 * j
            mi = mons[k][0]
            mi.u8(o, 0)
            mi.u32(o + 1, r.choice(effect_ids))
            mi.u32(o + 5, r.randrange(1 << 32))
            mi.u32(o + 9, r.randrange(1 << 32))
            mi.u32(o + 0xd, r.randrange(1 << 32))
            slot_addr = mon_ptr(e, k) + o
        else:
            sb = Blob(bytes(r.randrange(256) for _ in range(0x11)))
            sb.u8(0, 0)
            c.set(e.s0 + S0_EFSLOT, bytes(sb))
            slot_addr = e.s0 + S0_EFSLOT
        wire_monsters(c, e, mons)
        c.arg(mon_ptr(e, k)).arg(slot_addr)
        c.cap(e.s1, MI_STRIDE * (len(mons) - 1) + MI_SIZE, 'monsters')
        c.cap(e.s0 + S0_EFSLOT, 0x11, 'slot')
        c.note(monster=k, own_slot=own)
        finish(c)


def cases(ctx):
    e = Env(ctx)
    gen_roll_magnitude(ctx, e)
    gen_roll_duration(ctx, e)
    gen_display_slot(ctx, e)
    gen_resistances(ctx, e)
    gen_reduce(ctx, e, 'reduce', 0x00552250, 400, announce=False)
    gen_reduce(ctx, e, 'applyann', 0x00552340, 160, announce=True)
    gen_target_resists(ctx, e)
    gen_inflict(ctx, e)
    gen_resolve(ctx, e)
    gen_apply_condition(ctx, e)
    gen_fatigue(ctx, e)
    stamina_or_heal_case(ctx, e, 'stamina', 0x0054f520, 300, heal=False)
    stamina_or_heal_case(ctx, e, 'heal', 0x0054f190, 300, heal=True)
    gen_damage(ctx, e)
    gen_drain(ctx, e)
    gen_cure(ctx, e)
    gen_attack(ctx, e)
    gen_screen_busy(ctx, e)
    gen_clear_slot(ctx, e)
