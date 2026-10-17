"""Traps.cpp, Search.cpp, Factions.cpp, Noise.cpp (src/wiz8/local_code): every recovered
function of the four files, tested where the result depends only on arguments and state
the plan sets (scalar globals, corpus characters, structs built in scratch).

Tested (retail address, name, cases):
  Traps.cpp
  0x005e3730 GetTable650434Entry          160  all 15x8 cells + 40 aliased (row, column)
                                               pairs whose row*8+column stays inside the table
  0x005e3740 SelectTrapType               200  scratch Trigger, lock difficulty 1..11 and
                                               <= 0 (floored to 1); Random(15) re-rolls (seeded).
                                               difficulty >= 12 loops forever in both - not
                                               tested. 2 cases pass trigger = -0x368 so that
                                               &trigger->lock_state == NULL: retail returns
                                               before touching memory (note edge=null_lock_state)
  0x005e3610 HandleRecordModeKey          260  InputAtom in scratch, gfKeyState ctrl/shift/caps,
                                               record line/length pre-state; ASCII, backspace,
                                               ENTER, keys with high bits (only the low word is
                                               compared), Latin-1/wide characters (sprintf "%ls"
                                               of the CRT, note edge=wide_char). ESC (0x1b) is
                                               not used: it resets the main-game text box line.
                                               '%' is never in the line (ShowNoticef format).
                                               Screen = automap so ShowNoticef is a no-op.
  Search.cpp
  0x00517080 W8Searchable::GetPosition    150  world item without p3D (raw x/z copy, y + octree
                                               cell scale; special floats incl. SNaN/denormal/inf),
                                               all-null record, trigger with m_pProp = 0 and
                                               m_bRepType 2 / other (GetProp assert line 0x3ed)
  0x00517560 W8Searchable::PickBestSearcher 350 corpus party with set occupancy/hp/condition/
                                               profession (3 = the only profession with the search
                                               trait)/Scouting record/Senses; search_mode,
                                               detect_secrets, level FAST_MOVEMENT flag; camera
                                               position (g_gd_camera->m_position) and searchable
                                               position set so the distance lies around
                                               best_score*100 (the range; ~56 cases have no
                                               qualified searcher). Equipment is emptied
                                               (PracticeCharacterSkill -> UnequipUnusableItems
                                               could otherwise move items). Random(2) for
                                               detect_secrets is predicted from the case seed
                                               only to aim the distances. At most one slot per
                                               case gets condition 0x80000000/0xffffffff
                                               (edge=cond_negative), occupancy 2/0x80/0xff
                                               (edge=bool_byte) or Senses/Scouting >= 0x1999999a
                                               (edge=huge_value, unsigned wrap of a*10-1000).
                                               Captured: all 8 characters, gXStatus[0..0x19c0]
                                               (deferred skill notices), g_status[0..0x2500].
  Factions.cpp
  0x00535920 ResetFactions                 30  both tables pre-filled with garbage
  0x00535ad0 GetFactionDisposition        204  every faction, scores around 34/67 incl. negative;
                                               high garbage bits in the signed char argument;
                                               4 cases faction 21/22 (assert line 0xb0, the byte
                                               read past the table is set explicitly)
  0x00535c50 GetFactionDispositionToward  300  relation cells 0/1/2/0x80/0xff..., other == party
  0x00535b40 SetFactionDispositionBand    250  bands 0..2 and out-of-range, world clock set
  0x00535ea0 AdjustFactionDisposition     300  score/delta around clamp bounds 0/99 and the band
                                               thresholds, out-of-range scores (-128..127)
  0x00535cf0 ApplyFactionChange           350  op/faction/mode filters (byte compares, signed
                                               mode), modes 1..3 (delta truncated to char) and
                                               mode 0 = RecordFactionOffense (inlined in the port):
                                               monster list built in scratch, fake monster records
                                               wired into gXStatus.monster_record_cache
                                               (record_id 0x146, NPC flag, offense tiers)
  Noise.cpp
  0x004f0e50 NoiseHearingMargin           250  int32 wrap-around edges
  0x004f0e80 AlertMonsterGroupsToNoise    350  monster groups/infos/Monster objects in scratch
                                               wired into gXStatus lists (unborn/encounter lists
                                               nulled); flags 0, 2, other, and 1 only in setups
                                               that can never reach MonsterGroupEnterCombat or the
                                               octree path (in-combat groups, deaf leaders, out of
                                               range, or every heard_noise_margin = INT_MAX).
                                               Distances near integer boundaries (x87 80-bit
                                               length vs float, edge=near_int) and Random(100)
                                               ties against remaining*0.001f + senses
                                               (edge=random_tie, predicted from the case seed)
  0x004f1150 AlertCombatNoise             150  same worlds, position = g_startup_world nav pos
  0x004f1100 AlertWorldNoise              100  same, flag 1 safe setups only
  Total 3404 cases.
  Every flag-1 world (AlertMonsterGroupsToNoise flag 1, AlertWorldNoise) is simulated at
  plan time (_assert_flag1_safe) to prove no group can reach the octree path or
  MonsterGroupEnterCombat, even if Random(100) passes.

Skipped:
  0x005e3280 WriteRecordModeEntry        - file I/O (appends to data\\notes.txt), camera state
  0x005e34b0 ApplyRecordModeLine         - file I/O (writes/deletes data\\notes.txt) + notices
  0x005e35a0 PromptRecordModeEntry       - UI only (status line reset + notice)
  0x005e35f0 ClearRecordModeValue        - trivial store of 0, cannot differ
  0x005e3600 IsRecordModeActive          - trivial getter
  0x005e3780 CompleteTrapDisarm          - trigger Run/CompleteItemInteraction (world), sound, ShowString
  0x005e3800 DischargeTrapSpell          - casts the trap spell on the party (CastSpellFromSource)
  0x005e3ab0 ResolveSprungTrap           - ShowString, prop animation, octree LOS, spell cast
  0x00517900 W8SearchableView ctor       - not in port map (inlined)
  0x00516ad0 W8Searchable::Reveal        - not in port map; reveals/deletes live registry records
  0x00516ba0 CollectSearchablesInView    - camera yaw/heading + octree line of sight over the live
                                           searchable registry
  0x00516e20 RegisterSearchableWorldItem - heap allocation into the live registry
  0x00516f00 RegisterSearchableTrigger   - heap allocation into the live registry
  0x00516fe0 UnregisterSearchableTrigger - frees live registry records
  0x005171b0 ClearSearchables            - empties the live registry
  0x005171c0 RunSearchPulse              - timer, notices, camera turn, character events, Reveal
  0x00517780 ToggleSearchMode            - notice + countdown timer + world cursor clearing
  0x00535d30 GetFactionDispositionScore  - trivial getter (the same field is read by the tested
                                           GetFactionDisposition/AdjustFactionDisposition)
  0x00535d50 RecordFactionOffense        - inlined in the port (not in Wiz8Runtime.map); covered
                                           through ApplyFactionChange mode 0
  0x00536030 SaveFactionState            - file I/O
  0x00536070 LoadFactionState            - file I/O

Notes:
  Notices (ShowNoticef/ShowNotice) are made no-ops by g_current_screen_state = 8 (automap):
  ShowNotice only draws on screens 3/4/6/7 and ShowNoticef never forces the dialog.
  x87 precision: the core runs with the game's native FPU control word; the near_int and
  random_tie cases only diverge when that word has more than 24-bit precision.
  Every case is checked against the core limit of 96 memory ops (W8D_MAX_OPS).
"""
import math
import struct

CHAR = 0x1862
XROW = 0x106                 # W8PartySlotRow (g_status.buffers.XChar), fOccupied at +0
SCREEN_AUTOMAP = 8
MAX_OPS = 96                 # W8D_MAX_OPS in w8diff_core.c
MAX_ARGS = 16

# W8GlobalStatus (layout.ps1)
GS_WORLD_CLOCK = 0x18d8
GS_DETECT_SECRETS = 0x2329   # party_modifiers.detect_secrets
GS_SEARCH_MODE = 0x238f
GS_WORLD_SUSPENDED = 0x2390
GS_CAP = 0x2500

# W8XStatus
GX_COMBAT_MODE = 0x8dc
GX_MONSTER_LIST = 0x8f5
GX_GROUP_LIST = 0x8f9
GX_UNBORN_LIST = 0x901
GX_ENCOUNTER_LIST = 0x905
GX_RECORD_CACHE = 0xa0f
GX_CAP = 0x19c0              # monster_manager_entries[8] .. deferred_skill_notices (0x19b5)

# W8Character
C_PROF = 0x69
C_SENSES = 0x161             # attributes[SENSES].effective
C_SCOUT = 0x3d7              # skills[SCOUTING]
SK_ACTIVE, SK_POINTS, SK_LEVEL, SK_BASE, SK_PRACTICE = 0x00, 0x02, 0x06, 0x0a, 0x0e
SK_LEN = 0x14
C_HCOND = 0xb01
C_HP = 0xb11
C_EQUIP = 0xf5d              # W8ItemInstance[12], 0xc each
PROF_SEARCH = 3              # profession trait table 0x61507c: only row 3 holds trait 0xc
COND_TURNCOAT = 0xd

# Trigger
TRIG_LOCK = 0x368            # W8LockState: lock_type, difficulty, device_state[9]+3, device_id..
TRIG_SIZE = 0x38c
TRIG_REP_TYPE = 0x10c
TRIG_PROP = 0x110

# W8WorldItem
WI_P3D = 0x04
WI_POS = 0x15

# W8FactionRuntimeRecord (14 bytes, packed)
FAC_REC = 14
FAC_COUNT = 21
FAC_SIZE = FAC_REC * FAC_COUNT       # 0x126
REL_SIZE = FAC_COUNT * FAC_COUNT     # 0x1b9
FR_OFFENSE = 0x01
SPECIAL_FACTIONS = (6, 8, 10, 11, 12)   # MOOK, RATTKIN_MAFIA, HIGARDI_BANK/HLL/COMMON

# monsters (scratch layouts; strides cover every field the code reads)
MI_STRIDE = 0x300            # W8MonsterInfo: fields used end at heard_noise_margin + 4
MI_SPECIES = 0x08
MI_P3D = 0x0c
MI_DISPOSITION = 0x16
MI_HEARD_POS = 0x37
MI_HEARD_RADIUS = 0x43
MI_HEAD = 0x47
MI_MARGIN = 0x2f5
MG_STRIDE = 0x100            # W8MonsterGroup
MG_IN_COMBAT = 0x29
MG_DISPOSITION = 0x2a
MG_LEADER_LOC = 0x9f
MG_LEADER_GROUP = 0xa3
MG_HEAD = 0xa7
MO_STRIDE = 0x300            # W8Monster (p3D): navigator at +0x18, position at nav + 0x100
MO_POS = 0x118
MO_DEAF = 0x28f
MO_RECORD = 0x4f             # fake W8MonsterRecord overlaid on the object:
REC_SENSES = 0xd5            #   record + 0xd5 (attribute_values[SENSES]) == object + 0x124
REC_FLAGS = 0xd0
REC_ID = 0x187
REC_STRIDE = 0x300
LIST_MON = 0x000             # W8PList {data, capacity, iNumUsed} in scratch 0
LIST_MON_DATA = 0x100
LIST_GRP = 0x040
LIST_GRP_DATA = 0x400

INT_MIN = -0x80000000
INT_MAX = 0x7fffffff


def u8(v):
    return bytes([int(v) & 0xff])


def u32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


def vec(x, y, z):
    return struct.pack('<fff', x, y, z)


def vbits(a, b, c):
    return struct.pack('<III', a, b, c)


def bits_of(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def ulp32(x):
    x = abs(x)
    if x < 1.1754943508222875e-38:
        return 2.0 ** -149
    return 2.0 ** (math.floor(math.log2(x)) - 23)


def s32(v):
    v &= 0xffffffff
    return v - (1 << 32) if v & 0x80000000 else v


def junk(r, n):
    return bytes(r.getrandbits(8) for _ in range(n))


class _Rand:
    """MSVC rand() after the core's srand(case seed) (VC6 and UCRT use the same LCG);
    Random(n) as in sgp Random.cpp."""

    def __init__(self, seed):
        self.state = seed & 0xffffffff

    def rand(self):
        self.state = (self.state * 214013 + 2531011) & 0xffffffff
        return (self.state >> 16) & 0x7fff

    def random(self, n):
        if n == 0:
            return 0
        return (self.rand() * n // 0x7fff) % n


def _xrow(ctx, slot):
    return (ctx.g('g_status') + 8).deref() + slot * XROW


def cases(ctx):
    _table_entry(ctx)
    _select_trap_type(ctx)
    _record_mode_key(ctx)
    _searchable_position(ctx)
    _pick_best_searcher(ctx)
    _reset_factions(ctx)
    _faction_disposition(ctx)
    _faction_toward(ctx)
    _faction_band(ctx)
    _faction_adjust(ctx)
    _faction_apply(ctx)
    _noise_margin(ctx)
    _alert_groups(ctx)
    _alert_combat(ctx)
    _alert_world(ctx)
    _check_limits(ctx)


class _AnyBlob(dict):
    def __missing__(self, key):
        return 0


def _check_limits(ctx):
    """The core keeps at most 96 memory ops and 16 argument words per case."""
    for c in ctx.cases:
        text = c.render('retail', _AnyBlob())
        ops = args = 0
        for ln in text.split('\n'):
            w = ln.split(' ', 1)[0]
            if w in ('set', 'setb', 'setp', 'fill', 'keep', 'cap', 'dump'):
                ops += 1
            elif w == 'arg':
                args += 1
        if ops > MAX_OPS or args > MAX_ARGS:
            raise ValueError('%s: %d memory ops / %d args exceed the core limits' % (c.id, ops, args))


# ======================================================================================
# Traps.cpp
# ======================================================================================
def _table_entry(ctx):
    """unsigned char GetTable650434Entry(int row, int column): g_table1[15][8]"""
    fn = ctx.fn(0x005e3730)
    combos = [(row, col) for row in range(15) for col in range(8)]
    r = ctx.rng('table1', 'alias')
    alias = []
    while len(alias) < 40:
        idx = r.randrange(120)
        col = r.choice([-1, -2, -7, -8, -9, 8, 9, 15, 16, 31, -15, -56, r.randrange(-119, 120)])
        if (idx - col) % 8:
            continue
        alias.append(((idx - col) // 8, col))
    for i, (row, col) in enumerate(combos + alias):
        c = ctx.case('tableentry.%d' % i, fn, conv='c', ret='u8')
        c.arg(row)
        c.arg(col)
        c.note(row=row, col=col, index=row * 8 + col)
        if not (0 <= col < 8):
            c.note(edge='aliased_index')


def _select_trap_type(ctx):
    """void SelectTrapType(Trigger*): rejection sampling of Random(15) until
    difficulty[type] <= max(lock difficulty, 1) <= difficulty[type] + 4."""
    fn = ctx.fn(0x005e3740)
    trig = ctx.scratch(0)
    for i in range(ctx.n(200)):
        r = ctx.rng('traptype', i)
        c = ctx.case('selecttraptype.%d' % i, fn, conv='c', ret='v')
        if i < 2:
            # &trigger->lock_state == NULL: retail tests the pointer and returns
            c.arg(0x100000000 - TRIG_LOCK)
            c.note(edge='null_lock_state')
            continue
        x = r.random()
        if x < 0.7:
            diff = r.randrange(1, 12)
        elif x < 0.85:
            diff = r.choice([1, 2, 6, 7, 11, 11])
        else:
            diff = r.choice([0, -1, -2, -7, -100, INT_MIN])
        lock = struct.pack('<ii', r.choice([0, 1, 2, 2, 3]), diff) + junk(r, 12) + \
            u32(r.choice([-1, -1, r.randrange(15), r.getrandbits(32)])) + \
            u32(r.choice([-1, r.randrange(100)])) + u32(r.randrange(0, 40)) + \
            u32(r.choice([-1, r.getrandbits(31)]))
        if r.random() < 0.3:
            c.set(trig, junk(r, TRIG_LOCK))      # rest of the trigger: never read
        c.set(trig + TRIG_LOCK, lock)
        c.arg(trig)
        c.cap(trig, TRIG_SIZE, 'trigger')
        c.note(difficulty=diff)


REC_PRINTABLE = [ch for ch in range(0x20, 0x7f) if ch != 0x25]   # no '%': ShowNoticef format


def _rec_text(r, n):
    return bytes(r.choice(REC_PRINTABLE) for _ in range(n))


def _record_mode_key(ctx):
    """char HandleRecordModeKey(const InputAtom*, void (*prompt)(void))"""
    fn = ctx.fn(0x005e3610)
    line = ctx.g('g_record_mode_line')
    length = ctx.g('g_record_mode_length')
    active = ctx.g('g_record_mode_active')
    keys = ctx.g('gfKeyState')
    screen = ctx.g('g_current_screen_state')
    atom = ctx.scratch(0)
    for i in range(ctx.n(260)):
        r = ctx.rng('recordkey', i)
        c = ctx.case('recordmodekey.%d' % i, fn, conv='c', ret='i8')
        x = r.random()
        if x < 0.24:
            key, kind = r.randrange(0x61, 0x7b), 'lower'
        elif x < 0.38:
            key, kind = r.randrange(0x41, 0x5b), 'upper'
        elif x < 0.50:
            key, kind = r.choice(REC_PRINTABLE), 'printable'
        elif x < 0.62:
            key, kind = 8, 'backspace'
        elif x < 0.72:
            key, kind = 0xd, 'enter'
        elif x < 0.83:
            key, kind = r.choice([0x10008, 0x1000d, 0x10041, 0x10061, 0xffff0041, 0xffff007a,
                                  0x20030, 0x80000061, 0x7fff0020]), 'high_bits'
        elif x < 0.95:
            key, kind = r.choice([0x80, 0xa0, 0xc0, 0xc9, 0xe9, 0xff, 0x100, 0x108, 0x10d,
                                  0x141, 0x416, 0x2603]), 'wide_char'
        else:
            key, kind = 0, 'nul'
        assert (key & 0xffff) not in (0x1b, 0x25)
        event = 2 if r.random() < 0.85 else r.choice([0, 1, 4, 0x102, 0x8002, 0xffff])
        ctrl = 0 if r.random() < 0.9 else r.choice([1, 0x80, 0xff])
        shift = r.choice([0, 0, 1, 0x80])
        caps = r.choice([0, 0, 0, 1, 0xff])
        y = r.random()
        if y < 0.15:
            n = 0
        elif y < 0.85:
            n = r.randrange(1, 61)
        elif y < 0.95:
            n = r.randrange(100, 201)
        else:
            n = r.choice([0xffe, 0xff0, 0x800])
        if kind == 'backspace' and r.random() < 0.3:
            n = 0
        if n <= 200:
            k = n
            if r.random() < 0.1:
                k = max(0, n + r.choice([-3, -1, 2, 5]))   # strlen != recorded length
            text = _rec_text(r, k) + b'\0'
            if r.random() < 0.2:
                text += _rec_text(r, r.randrange(1, 8)) + b'\0'
            text += b'\0' * max(0, n + 2 - len(text))
            c.set(line, text)
        else:
            c.set(line, b'\0')                 # empty string, byte appended far out
            c.set(line + n - 2, b'\0' * 4)
        c.set(length, u32(n))
        c.set(active, u8(r.choice([0, 1, 1, 2])))
        c.set(keys + 0x10, bytes([shift, ctrl]))   # VK_SHIFT, VK_CONTROL
        c.set(keys + 0x14, u8(caps))               # VK_CAPITAL
        c.set(screen, u32(SCREEN_AUTOMAP))
        c.set(atom, struct.pack('<IHHII', r.getrandbits(32), r.getrandbits(16), event, key,
                                r.getrandbits(32)))
        c.arg(atom)
        c.arg(0)
        c.cap(line, 0x1000, 'line')
        c.cap(length, 4, 'length')
        c.cap(active, 1, 'active')
        c.note(key='%#x' % key, kind=kind, event=event, ctrl=ctrl, shift=shift, caps=caps, length=n)
        if kind == 'wide_char':
            c.note(edge='wide_char')


# ======================================================================================
# Search.cpp
# ======================================================================================
F_SPECIAL = [0x00000000, 0x80000000, 0x00000001, 0x807fffff, 0x00800000, 0x7f7fffff, 0xff7fffff,
             0x7f800000, 0xff800000, 0x7fc00000, 0xffc00000, 0x7f800001, 0x7fa00000, 0x3f800000,
             0xc2c80000, 0xc2c80001, 0x42c80000, 0x4b800000, 0x4b7fffff, 0x7149f2ca, 0xf149f2ca]
F_SNAN = (0x7f800001, 0x7fa00000)


def _coord_bits(r, lo, hi, p_special):
    if r.random() < p_special:
        return r.choice(F_SPECIAL)
    return bits_of(f32(r.uniform(lo, hi)))


def _searchable_position(ctx):
    """void W8Searchable::GetPosition(srVector3T<float>*) (thiscall)"""
    fn = ctx.fn(0x00517080)
    srch, obj, out = ctx.scratch(0), ctx.scratch(1), ctx.scratch(2)
    for i in range(ctx.n(150)):
        r = ctx.rng('searchpos', i)
        c = ctx.case('searchablepos.%d' % i, fn, conv='t', ret='v')
        c.set(out, junk(r, 12))
        x = r.random()
        if x < 0.6:
            kind = 'item'
            p = [_coord_bits(r, -60000, 60000, 0.2), _coord_bits(r, -2000, 5000, 0.2),
                 _coord_bits(r, -60000, 60000, 0.2)]
            if i % 16 == 0:
                p[r.choice([0, 2])] = r.choice(F_SNAN)    # retail copies x/z as raw dwords
            c.set(obj, junk(r, WI_P3D) + u32(0) + junk(r, WI_POS - 8) + vbits(*p) + junk(r, 0x20))
            c.setp(srch, obj)
            c.note(pos=','.join('%08x' % b for b in p))
            if p[0] in F_SNAN or p[2] in F_SNAN:
                c.note(edge='snan_copy')
        elif x < 0.75:
            kind = 'null'
        else:
            kind = 'trigger'
            rep = 2 if r.random() < 0.7 else r.choice([0, 1, 3, 0xff])
            c.set(obj + TRIG_REP_TYPE, u8(rep) + junk(r, 3) + u32(0))
            c.setp(srch + 8, obj)
            c.note(rep_type=rep)
        c.arg(srch)
        c.arg(out)
        c.cap(out, 12, 'position', floats=[4])
        c.cap(srch, 12, 'searchable')
        c.cap(obj, 0x120, 'object')
        c.note(kind=kind)


SENSES_EDGE = [0, 1, 4, 5, 9, 49, 50, 51, 52, 53, 54, 79, 80, 81, 82, 83, 89, 90, 91, 92, 98, 99,
               100, 101, 102, 103, 124, 125, 126, 200, 255]
SENSES_HUGE = [0x1999999a, 0x7fffffff, 0x80000000, 0xffffffff]   # (a*10 - 1000) wraps
SCOUT_EDGE = [0, 1, 2, 3, 4, 5, 7, 8, 9, 99, 100, 125, 126, 199, 200]
SCOUT_HUGE = [0xffffffff, 0x80000000, 0x7fffffff]
COND_EDGE = [0x80000000, 0xffffffff]     # negative as int; retail compares unsigned
BOOL_EDGE = [2, 0x80, 0xff]


def _search_score(level, senses, fast, search_mode):
    m = 0xffffffff
    base = (level >> 2) if fast else (level >> 1)
    score = 0
    if base != 0 or (search_mode and not fast):
        a = senses
        if a < 0x33:
            score = base + a // 5
        elif a < 0x51:
            score = base + 10 + (a - 0x32) // 3
        elif a < 0x5b:
            score = base - 0x3c + a
        elif a < 100:
            score = base - 0x96 + a * 2
        elif a < 0x65:
            score = base + 0x32
        else:
            score = base + 0x32 + ((a * 10 - 1000) & m) // 0x19
        score &= m
    return 100 if score > 99 else score


def _unit(r, axis_p=0.3):
    if r.random() < axis_p:
        v = [0.0, 0.0, 0.0]
        v[r.randrange(3)] = r.choice([1.0, -1.0])
        return v
    while True:
        v = [r.uniform(-1, 1) for _ in range(3)]
        n = math.sqrt(sum(t * t for t in v))
        if 0.1 < n <= 1:
            return [t / n for t in v]


def _pick_best_searcher(ctx):
    """int W8Searchable::PickBestSearcher(void) (thiscall)"""
    fn = ctx.fn(0x00517560)
    gs = ctx.g('g_status')
    gx = ctx.g('gXStatus')
    cam = ctx.g('g_gd_camera').deref() + 0x8c
    lvl = ctx.g('g_level_data').deref()
    screen = ctx.g('g_current_screen_state')
    srch, item = ctx.scratch(0), ctx.scratch(1)
    for i in range(ctx.n(350)):
        r = ctx.rng('bestsearcher', i)
        c = ctx.case('pickbestsearcher.%d' % i, fn, conv='t', ret='i')
        party = ctx.set_party(c, r)
        sm = 0 if r.random() < 0.5 else r.choice([1, 1, 1, 1, 2, 0x80, 0xff])
        detect = 0 if r.random() < 0.75 else r.choice([1, 1, 1, 2, 0xff])
        fast = r.random() < 0.3
        flags = 0x100 if fast else 0
        if r.random() < 0.2:
            flags |= r.getrandbits(32) & ~0x100
        c.set(lvl, u32(flags))
        c.set(gs + GS_SEARCH_MODE, u8(sm))
        c.set(gs + GS_DETECT_SECRETS, u8(detect))
        c.set(screen, u32(SCREEN_AUTOMAP))
        c.set(gx + GX_COMBAT_MODE, u8(0))
        slots = []
        edges = []
        # at most one slot per case with an out-of-enum condition, a non-canonical bool byte
        # or a huge Senses/Scouting value
        e_cond = r.randrange(8) if r.random() < 0.1 else -1
        e_bool = r.randrange(8) if r.random() < 0.1 else -1
        e_huge = r.randrange(8) if r.random() < 0.12 else -1
        p_trait = r.choice([0.0, 0.15, 0.3, 0.6])
        for s in range(8):
            slot, blob, name = party[s]
            ch = ctx.char(slot)
            occ = 1 if r.random() < 0.85 else 0
            if s == e_bool:
                occ = r.choice(BOOL_EDGE)
                edges.append('bool_byte')
            hp = r.randrange(1, 400) if r.random() < 0.88 else r.choice([0, 0, 1, 0xffffffff])
            cond = 0 if r.random() < 0.7 else r.choice([1, 5, 0xb, 0xc, 0xd, 0xd, 0xe, 0x12])
            if s == e_cond:
                cond = r.choice(COND_EDGE)
                edges.append('cond_negative')
            prof = blob.get_u32(C_PROF)
            y = r.random()
            if y < p_trait:
                prof = PROF_SEARCH
            elif prof == PROF_SEARCH or y > 0.85:
                prof = r.choice([p for p in range(15) if p != PROF_SEARCH])
            level = r.choice(SCOUT_EDGE) if r.random() < 0.25 else r.randrange(0, 126)
            senses = r.choice(SENSES_EDGE) if r.random() < 0.35 else r.randrange(1, 126)
            if s == e_huge:
                if r.random() < 0.6:
                    senses = r.choice(SENSES_HUGE)
                else:
                    level = r.choice(SCOUT_HUGE)
                edges.append('huge_value')
            sk = bytearray(blob[C_SCOUT:C_SCOUT + SK_LEN])
            sk[SK_ACTIVE] = r.choice([0, 1, 1, 1])
            struct.pack_into('<I', sk, SK_POINTS, r.choice([0, 1, 50, 98, 99, 100, r.randrange(0, 100)]))
            struct.pack_into('<I', sk, SK_LEVEL, level)
            struct.pack_into('<I', sk, SK_PRACTICE, r.choice([7, 7, 7, 6, 0, r.randrange(0, 8)]))
            if r.random() < 0.15:
                struct.pack_into('<I', sk, SK_BASE, r.choice([0, 1, 100, 125]))
            eq = bytearray(blob[C_EQUIP:C_EQUIP + 12 * 0xc])
            for e in range(12):
                struct.pack_into('<i', eq, e * 0xc, -1)
            c.set(_xrow(ctx, slot), u8(occ))
            c.set(ch + C_PROF, u32(prof))
            c.set(ch + C_SENSES, u32(senses))
            c.set(ch + C_SCOUT, bytes(sk))
            c.set(ch + C_HCOND, u32(cond) + bytes(blob[C_HCOND + 4:C_HP]) + u32(hp))
            c.set(ch + C_EQUIP, bytes(eq))
            slots.append((occ, hp, cond, prof, level, senses))
        # expected pick (only to aim the distance)
        rnd = _Rand(c.seed)
        best, best_slot = 0, -1
        for s, (occ, hp, cond, prof, level, senses) in enumerate(slots):
            if not occ or hp == 0 or cond >= COND_TURNCOAT:
                continue
            if prof == PROF_SEARCH or sm:
                sc = _search_score(level, senses, fast, sm)
                if best < sc:
                    best, best_slot = sc, s
            if detect:
                if best_slot != -1 and rnd.random(2) == 0:
                    continue
                best, best_slot = 100, s
        rng_ = best * 100.0
        x = r.random()
        if x < 0.3:
            dist, dk = r.uniform(0, rng_ * 1.2 + 50), 'uniform'
        elif x < 0.62:
            dist = rng_ * (1 + r.choice([-1e-7, 1e-7, -3e-7, 3e-7, -1e-6, 1e-6, -1e-4, 1e-4,
                                         -0.01, 0.01, 0.0]))
            dk = 'boundary'
        elif x < 0.77:
            kk = r.randrange(0, 101)
            dist, dk = kk * 100.0 * (1 + r.choice([-2e-7, 0.0, 2e-7, -0.001, 0.001])), 'other_boundary'
        elif x < 0.87:
            dist, dk = 0.0, 'zero'
        else:
            dist, dk = r.choice([r.uniform(1e5, 1e7), 1e30]), 'far'
        cx, cy, cz = f32(r.uniform(-40000, 40000)), f32(r.uniform(0, 3000)), f32(r.uniform(-40000, 40000))
        u = _unit(r)
        px, py, pz = f32(cx - u[0] * dist), f32(cy - u[1] * dist - 100.0), f32(cz - u[2] * dist)
        pos = vec(px, py, pz)
        if r.random() < 0.03:
            pos = vbits(0x7fc00000, bits_of(py), bits_of(pz))
            dk = 'nan'
        c.set(cam, vec(cx, cy, cz))
        c.set(item + WI_P3D, u32(0) + junk(r, WI_POS - 8) + pos)
        c.setp(srch, item)
        c.arg(srch)
        for s in range(8):
            c.cap(ctx.char(s), CHAR, 'char%d' % s)
        c.cap(gx, GX_CAP, 'gxstatus')
        c.cap(gs, GS_CAP, 'g_status')
        c.note(search_mode=sm, detect=detect, fast=int(fast), expect_best=best,
               expect_slot=best_slot, dist=dk,
               party=';'.join('%x/%x/%x/%d/%x/%x' % t for t in slots))
        if edges:
            c.note(edge=','.join(sorted(set(edges))))


# ======================================================================================
# Factions.cpp
# ======================================================================================
def _score(r):
    x = r.random()
    if x < 0.35:
        return r.choice([33, 34, 35, 66, 67, 68, 0, 99, 25, 55, 75, 80, 50, 70, 100])
    if x < 0.85:
        return r.randrange(0, 100)
    return r.choice([-1, -2, -34, -128, 101, 120, 127])


def _fac_record(r, score):
    return struct.pack('<b', score) + struct.pack('<i', r.choice([0, 0, 3, r.randrange(0, 300)])) + \
        u8(r.getrandbits(8)) + u32(r.getrandbits(32)) + u8(r.choice([0, 1])) + junk(r, 3)


def _byte_arg(r, v, p=0.15):
    """signed char / char argument: low byte only, sometimes garbage in the upper bytes."""
    v &= 0xff
    if r.random() < p:
        return v | (r.getrandbits(24) << 8)
    return v


def _reset_factions(ctx):
    """void ResetFactions(void)"""
    fn = ctx.fn(0x00535920)
    fac = ctx.g('g_factions')
    rel = ctx.g('g_faction_relations')
    for i in range(ctx.n(30)):
        r = ctx.rng('resetfactions', i)
        c = ctx.case('resetfactions.%d' % i, fn, conv='c', ret='v')
        if i < 20:
            b1 = [0, 0xff, 1, 0x55, 0xaa][i % 5] if i < 10 else r.getrandbits(8)
            b2 = [0, 0xff, 1, 0x55, 0xaa][(i + 2) % 5] if i < 10 else r.getrandbits(8)
            c.fill(fac, FAC_SIZE, b1)
            c.fill(rel, REL_SIZE, b2)
            c.note(fill_factions=b1, fill_relations=b2)
        else:
            c.set(fac, junk(r, FAC_SIZE))
            c.set(rel, junk(r, REL_SIZE))
            c.note(fill='random')
        c.cap(rel, REL_SIZE, 'relations')
        c.cap(fac, FAC_SIZE, 'factions')


def _faction_disposition(ctx):
    """W8FactionDisposition GetFactionDisposition(signed char)"""
    fn = ctx.fn(0x00535ad0)
    fac = ctx.g('g_factions')
    for i in range(ctx.n(200)):
        r = ctx.rng('facdisp', i)
        c = ctx.case('factiondisposition.%d' % i, fn, conv='c', ret='u8')
        f = i % FAC_COUNT if i < 63 else r.randrange(FAC_COUNT)
        score = _score(r)
        c.set(fac + f * FAC_REC, struct.pack('<b', score))
        c.arg(_byte_arg(r, f))
        c.cap(fac, FAC_SIZE, 'factions')
        c.note(faction=f, score=score)
    # past the end of the table: assert line 0xb0, then the byte is read anyway
    for j, (f, score) in enumerate([(21, 10), (21, 50), (22, 90), (22, -5)]):
        c = ctx.case('factiondisposition.oob%d' % j, fn, conv='c', ret='u8')
        c.set(fac + f * FAC_REC, struct.pack('<b', score))
        c.arg(f)
        c.note(faction=f, score=score, edge='faction_out_of_range')


def _faction_toward(ctx):
    """W8FactionDisposition GetFactionDispositionToward(signed char faction, signed char other)"""
    fn = ctx.fn(0x00535c50)
    fac = ctx.g('g_factions')
    rel = ctx.g('g_faction_relations')
    for i in range(ctx.n(300)):
        r = ctx.rng('factoward', i)
        c = ctx.case('factiontoward.%d' % i, fn, conv='c', ret='u8')
        f = r.randrange(FAC_COUNT)
        o = 1 if r.random() < 0.25 else r.randrange(FAC_COUNT)
        rv = r.choice([0, 1, 1, 2, 0xff, 0x80, 0x81, 0x11, r.getrandbits(8)])
        score = _score(r)
        c.set(rel + f * FAC_COUNT + o, u8(rv))
        c.set(fac + f * FAC_REC, struct.pack('<b', score))
        c.arg(_byte_arg(r, f))
        c.arg(_byte_arg(r, o))
        c.note(faction=f, other=o, relation=rv, score=score)


def _faction_band(ctx):
    """void SetFactionDispositionBand(signed char faction, signed char band)"""
    fn = ctx.fn(0x00535b40)
    fac = ctx.g('g_factions')
    gs = ctx.g('g_status')
    screen = ctx.g('g_current_screen_state')
    for i in range(ctx.n(250)):
        r = ctx.rng('facband', i)
        c = ctx.case('factionband.%d' % i, fn, conv='c', ret='v')
        f = r.randrange(FAC_COUNT)
        score = _score(r)
        band = r.choice([0, 1, 2] * 5 + [-1, 3, 4, 0x7f, -128, -2])
        clock = r.choice([0, 1, r.getrandbits(31), 0xffffffff, 0x80000000])
        c.set(fac + f * FAC_REC, _fac_record(r, score))
        c.set(gs + GS_WORLD_CLOCK, u32(clock))
        c.set(screen, u32(SCREEN_AUTOMAP))
        c.arg(_byte_arg(r, f))
        c.arg(_byte_arg(r, band))
        c.cap(fac, FAC_SIZE, 'factions')
        c.note(faction=f, score=score, band=band)


def _delta(r, score):
    x = r.random()
    if x < 0.35:
        return r.choice([-40, -20, -10, -6, -2, -1, 1, 2, 5, 10, 20, 40])
    if x < 0.65:
        # land on/around a clamp bound or band threshold
        target = r.choice([-1, 0, 1, 33, 34, 66, 67, 98, 99, 100])
        d = target - score
        return max(-128, min(127, d))
    if x < 0.9:
        return r.randrange(-128, 128)
    return r.choice([0, 127, -128, 0x80, 0xff])


def _faction_adjust(ctx):
    """void AdjustFactionDisposition(signed char faction, char delta)"""
    fn = ctx.fn(0x00535ea0)
    fac = ctx.g('g_factions')
    gs = ctx.g('g_status')
    screen = ctx.g('g_current_screen_state')
    for i in range(ctx.n(300)):
        r = ctx.rng('facadjust', i)
        c = ctx.case('factionadjust.%d' % i, fn, conv='c', ret='v')
        f = r.randrange(2, FAC_COUNT) if r.random() < 0.9 else r.choice([0, 1])
        score = _score(r)
        delta = _delta(r, score)
        c.set(fac + f * FAC_REC, _fac_record(r, score))
        c.set(gs + GS_WORLD_CLOCK, u32(r.getrandbits(32)))
        c.set(screen, u32(SCREEN_AUTOMAP))
        c.arg(_byte_arg(r, f))
        c.arg(_byte_arg(r, delta))
        c.cap(fac, FAC_SIZE, 'factions')
        c.note(faction=f, score=score, delta=delta)


OFFENSE_EDGE = [0, 1, 0x13, 0x14, 0x15, 0x16, 0x27, 0x28, 0x29, 0x2a, 0xf9, 0xfa, 0xfb, 0xffffffff,
                0x80000000, 0x7fffffff]


def _faction_apply(ctx):
    """void ApplyFactionChange(char mode, char op, signed char faction, int value);
    mode 0 runs RecordFactionOffense(faction, value = monster list index)."""
    fn = ctx.fn(0x00535cf0)
    fac = ctx.g('g_factions')
    rel = ctx.g('g_faction_relations')
    gs = ctx.g('g_status')
    gx = ctx.g('gXStatus')
    screen = ctx.g('g_current_screen_state')
    lists, infos, recs = ctx.scratch(0), ctx.scratch(1), ctx.scratch(2)
    for i in range(ctx.n(350)):
        r = ctx.rng('facapply', i)
        c = ctx.case('factionapply.%d' % i, fn, conv='c', ret='v')
        x = r.random()
        if x < 0.5:
            mode = 0
        elif x < 0.78:
            mode = r.choice([1, 2, 3])
        else:
            mode = r.choice([4, 5, 0x7f, -1, -128, 0x80 | 3, 0xfd])
        op = 1 if r.random() < 0.8 else r.choice([0, 2, 0xff, 0x101, 0x7f01, 0x100])
        y = r.random()
        if y < 0.55:
            f = r.randrange(2, FAC_COUNT)
        elif y < 0.85:
            f = r.choice(SPECIAL_FACTIONS)
        else:
            f = r.choice([0, 1, 0x100, 0x101, 0x102 + r.randrange(19)])
        fi = f & 0xff
        # monster list for the offense path
        n = r.randrange(1, 5)
        species = r.sample(range(1000), n)
        c.set(lists + 4, struct.pack('<ii', n + r.randrange(0, 3), n))
        c.setp(lists, lists + LIST_MON_DATA)
        kinds = []
        for m in range(n):
            info = infos + m * MI_STRIDE
            rec = recs + m * REC_STRIDE
            c.set(info, struct.pack('<iiI', r.randrange(1, 100000), r.randrange(0, 1000), species[m]))
            c.setp(lists + LIST_MON_DATA + 4 * m, info)
            z = r.random()
            rid = 0x146 if z < 0.25 else r.choice([0x145, 0x147, 0x46, 0x1146, r.randrange(0, 0x2a8)])
            flg = r.getrandbits(8) & 0xfe
            if r.random() < 0.3:
                flg |= 1
            c.set(rec + REC_FLAGS, u8(flg))
            c.set(rec + REC_ID, struct.pack('<H', rid))
            c.setp(gx + GX_RECORD_CACHE + 4 * species[m], rec)
            kinds.append('%x/%x' % (rid, flg & 1))
        c.setp(gx + GX_MONSTER_LIST, lists)
        if mode == 0 or r.random() < 0.5:
            value = r.randrange(n)
        else:
            value = r.choice([-40, -20, -6, -2, -1, 0, 1, 2, 10, 50, 127, 128, 200, 255, 256,
                              -129, -300, 0x7fffffff, INT_MIN, r.randrange(-128, 128)])
        score = _score(r)
        rec_bytes = bytearray(_fac_record(r, score))
        offense = r.choice(OFFENSE_EDGE) if r.random() < 0.5 else r.randrange(0, 60)
        struct.pack_into('<I', rec_bytes, FR_OFFENSE, offense)
        if 0 <= fi < FAC_COUNT:
            c.set(fac + fi * FAC_REC, bytes(rec_bytes))
        c.set(gs + GS_WORLD_CLOCK, u32(r.getrandbits(32)))
        c.set(screen, u32(SCREEN_AUTOMAP))
        c.arg(mode & 0xffffffff if r.random() < 0.85 else (mode & 0xff) | (r.getrandbits(24) << 8))
        c.arg(op)
        c.arg(f)
        c.arg(value)
        c.cap(fac, FAC_SIZE, 'factions')
        c.cap(rel, REL_SIZE, 'relations')
        c.cap(infos, n * MI_STRIDE, 'infos')
        c.cap(recs, n * REC_STRIDE, 'records')
        c.note(mode=mode, op=op, faction=f, value=value, score=score, offense=offense,
               records=','.join(kinds))


# ======================================================================================
# Noise.cpp
# ======================================================================================
def _noise_margin(ctx):
    """int NoiseHearingMargin(int radius, int range, int hops) = radius - hops*25000 - range"""
    fn = ctx.fn(0x004f0e50)
    edge = [0, 1, -1, 25000, 24999, 25001, 50000, 0x927c, INT_MAX, INT_MIN, 85899, 85900, -85900,
            1000, -25000]
    for i in range(ctx.n(250)):
        r = ctx.rng('noisemargin', i)
        c = ctx.case('noisemargin.%d' % i, fn, conv='c', ret='i')
        x = r.random()
        if x < 0.5:
            radius = r.choice([25000, 0x927c, 50000, r.randrange(0, 100000)])
            rng_ = r.randrange(0, 60000)
            hops = r.randrange(0, 4)
        elif x < 0.8:
            radius, rng_, hops = r.choice(edge), r.choice(edge), r.choice(edge + [2, 3, 10, -2])
        else:
            radius, rng_, hops = s32(r.getrandbits(32)), s32(r.getrandbits(32)), s32(r.getrandbits(32))
        c.arg(radius)
        c.arg(rng_)
        c.arg(hops)
        c.note(radius=radius, range=rng_, hops=hops)


def _near_int_delta(r, n):
    """(a, b) float32 with sqrt(a*a + b*b) just below the integer n, closer than half a float
    ulp: x87 extended truncates to n - 1, a float-rounded length truncates to n."""
    for _ in range(200):
        t = r.uniform(0.15, 1.42)
        a, b = f32(n * math.cos(t)), f32(n * math.sin(t))
        d = math.sqrt(a * a + b * b)
        if d < n and n - d < 0.5 * ulp32(n):
            return a, b
    return None


def _noise_radius(r):
    x = r.random()
    if x < 0.4:
        return r.choice([25000, 0x927c, 50000])
    if x < 0.8:
        return r.randrange(1, 100000)
    return r.choice([0, 1, -1, -25000, 999, 1000, INT_MAX, INT_MIN])


def _noise_world(ctx, c, r, flag, combat, radius, N, pos_addr):
    """Groups, monster infos and Monster objects in scratch, wired into gXStatus.
    N: noise position (floats); pos_addr: where the noise position is set (scratch or the
    startup world navigator). Returns notes."""
    gx = ctx.g('gXStatus')
    lists, infos, groups, objs = ctx.scratch(0), ctx.scratch(1), ctx.scratch(2), ctx.scratch(3)
    rnd = _Rand(c.seed)
    G = r.choice([0, 1, 1, 2, 2, 3, 3, 3, 4, 5]) if r.random() < 0.97 else 0
    extra = r.choice([0, 0, 1, 2])
    I = G + extra
    locs = r.sample(range(1, 300000), max(I, 1))
    species = r.sample(range(1000), max(I, 1))
    gids = r.sample(range(1, 60000), max(G, 1))
    order = list(range(I))
    r.shuffle(order)                      # monster list position -> info index
    margin_all = INT_MAX if (flag == 1 and not combat) else None
    nice_n = all(float(int(t)) == t for t in N)

    # info m < G leads group m
    info_dist = {}
    group_notes = []
    group_state = []
    info_state = []
    for k in range(G):
        deaf = r.random() < 0.12
        in_combat = r.random() < 0.4
        disp = 1 if r.random() < 0.7 else r.choice([0, 2, 3, 0xff])
        senses = r.randrange(0, 126) if r.random() < 0.85 else r.choice([0, 125, 126, 200, 255])
        margin = None
        dk = None
        delta = None
        x = r.random()
        # Random(100) tie for the first group: remaining = 1000*k exactly
        want_tie = (k == 0 and not deaf and radius > 1000 and r.random() < 0.3 and
                    not (flag == 1 and combat) and (flag != 0 or disp == 1))
        if want_tie:
            r0 = rnd.random(100)
            kk = min(r0, radius // 1000, r.choice([1, 2, 3, 5, 6, 7, 9, 10, 20, 37]))
            if kk >= 1:
                dist = float(radius - 1000 * kk) + r.choice([0.25, 0.5, 0.75])
                delta = [0.0, 0.0, 0.0]
                delta[r.randrange(3)] = dist * r.choice([1, -1])
                senses = r0 - kk
                dk = 'random_tie'
                margin = r.choice([INT_MIN, -1, 0, 1000 * kk - 1])
        if delta is None:
            if x < 0.15 and radius < INT_MAX - 1000:
                # >= radius + 1 even after the float32 rounding of the positions
                dist = float(max(radius, 0)) + r.choice([1.0, 2.0, 10.5, 1000.0, 1.0 + r.uniform(0, 50000)])
                dk = 'out_of_range'
            elif x < 0.32 and nice_n and 2 <= radius < INT_MAX:
                n = r.randrange(1, min(radius, 60000) + 1)
                if r.random() < 0.2:
                    n = min(radius, 60000)          # remaining 0 (float) vs 1 (extended)
                ab = _near_int_delta(r, n)
                ax = r.sample(range(3), 2)
                if ab is not None and all(f32(N[a_] + v) - N[a_] == v for a_, v in zip(ax, ab)):
                    delta = [0.0, 0.0, 0.0]
                    delta[ax[0]], delta[ax[1]] = ab
                    dk = 'near_int'
                    senses = r.choice([125, 200, 255])   # pass Random so the margin gets written
                    margin = r.choice([INT_MIN, -1, 0])
                else:
                    dk = 'near_int_miss'
                dist = float(n)
            elif x < 0.45 and 0 < radius < INT_MAX:
                dist = float(radius - r.randrange(0, min(radius, 100000) + 1)) + r.choice([0.0, 0.3, 0.999])
                dk = 'near_radius'
            elif x < 0.48:
                dist = float('nan')
                dk = 'nan'
            else:
                dist = r.uniform(0, max(radius, 1) * 1.1) if radius < INT_MAX else r.uniform(0, 1e6)
                dk = 'uniform'
            if delta is None:
                u = _unit(r)
                delta = [t * dist for t in u] if dist == dist else [float('nan'), 0.0, 0.0]
        # flag 1 safety: never reach MonsterGroupEnterCombat / the octree path
        if flag == 1 and combat and not in_combat and not deaf and dk != 'out_of_range':
            if radius >= INT_MAX - 1000 or radius < 0:
                deaf = True
            else:
                dist = float(max(radius, 0)) + r.choice([2.0, 10.0, 500.0])
                u = _unit(r)
                delta = [t * dist for t in u]
                dk = 'out_of_range'
        if dk == 'nan' and flag == 1:
            deaf = True
        lg = 0 if r.random() < 0.65 else gids[r.randrange(G)]
        info_dist[k] = (delta, deaf, disp, senses, margin)
        group_state.append((in_combat, lg))
        group_notes.append('%s%s%s' % (dk, '/deaf' if deaf else '', '/lead' if lg else ''))
        blob = bytearray(junk(r, MG_HEAD))
        struct.pack_into('<i', blob, 0, gids[k])
        blob[MG_IN_COMBAT] = (r.choice([1, 1, 2, 0x80]) if in_combat else 0)
        blob[MG_DISPOSITION] = r.getrandbits(8)
        struct.pack_into('<ii', blob, MG_LEADER_LOC, locs[k], lg)
        c.set(groups + k * MG_STRIDE, bytes(blob))
        c.setp(lists + LIST_GRP_DATA + 4 * k, groups + k * MG_STRIDE)
    for m in range(G, I):
        u = _unit(r)
        dist = r.uniform(0, 60000)
        info_dist[m] = ([t * dist for t in u], r.random() < 0.15, r.choice([0, 1, 1, 2]),
                        r.randrange(0, 126), None)
    for m in range(I):
        delta, deaf, disp, senses, margin = info_dist[m]
        if margin is None:
            margin = r.choice([INT_MIN, -1, 0, 0, 1, 100, 1000, 5000, 20000, 30000, INT_MAX,
                               r.randrange(-1000, 50000)])
        if margin_all is not None:
            margin = margin_all
        info = infos + m * MI_STRIDE
        obj = objs + m * MO_STRIDE
        head = bytearray(junk(r, MI_HEAD))
        struct.pack_into('<iiI', head, 0, locs[m], r.randrange(0, 60000), species[m])
        struct.pack_into('<I', head, MI_P3D, 0)
        head[MI_DISPOSITION] = disp
        c.set(info, bytes(head))
        c.set(info + MI_MARGIN, u32(margin))
        c.setp(info + MI_P3D, obj)
        c.setp(lists + LIST_MON_DATA + 4 * order.index(m), info)
        c.setp(gx + GX_RECORD_CACHE + 4 * species[m], obj + MO_RECORD)
        if any(t != t for t in delta):
            mvals = None
            mpos = vbits(0x7fc00000, bits_of(N[1]), bits_of(N[2]))
        else:
            mvals = (f32(N[0] + delta[0]), f32(N[1] + delta[1]), f32(N[2] + delta[2]))
            mpos = vec(*mvals)
        c.set(obj + MO_POS, mpos + u8(senses))
        c.set(obj + MO_DEAF, u8(r.choice([1, 1, 2, 0xff]) if deaf else 0))
        info_state.append((mvals, deaf, margin))
    if flag == 1:
        _assert_flag1_safe(c, G, gids, group_state, info_state, combat, radius, N)
    c.set(lists + LIST_MON + 4, struct.pack('<ii', I + r.randrange(0, 3), I))
    c.setp(lists + LIST_MON, lists + LIST_MON_DATA)
    c.set(lists + LIST_GRP + 4, struct.pack('<ii', G + r.randrange(0, 3), G))
    c.setp(lists + LIST_GRP, lists + LIST_GRP_DATA)
    c.setp(gx + GX_MONSTER_LIST, lists + LIST_MON)
    c.setp(gx + GX_GROUP_LIST, lists + LIST_GRP)
    c.set(gx + GX_UNBORN_LIST, u32(0))
    c.set(gx + GX_ENCOUNTER_LIST, u32(0))
    c.set(gx + GX_COMBAT_MODE, u8(1 if combat else 0))
    c.set(pos_addr, vec(*N))
    notes = {'groups': G, 'infos': I, 'group_kinds': ';'.join(group_notes)}
    edges = sorted({g.split('/')[0] for g in group_notes} & {'near_int', 'random_tie', 'nan'})
    if edges:
        notes['edge'] = ','.join(edges)
    if I:
        c.cap(infos, I * MI_STRIDE, 'infos')
        c.cap(objs, I * MO_STRIDE, 'monsters')
    if G:
        c.cap(groups, G * MG_STRIDE, 'groups')
    return notes


def _assert_flag1_safe(c, G, gids, group_state, info_state, combat, radius, N):
    """Plan-time proof that a flag-1 call cannot reach the octree path or
    MonsterGroupEnterCombat (both would change world state): every group must be skipped
    by in-combat, a deaf leader, remaining <= 0 (with slack for rounding), or the
    heard_noise_margin = INT_MAX check. Random(100) is assumed to pass."""
    for k in range(G):
        in_combat, lg = group_state[k]
        mvals, deaf, _ = info_state[k]
        if deaf or (combat and in_combat):
            continue
        if mvals is None:
            t = INT_MIN
        else:
            d = math.sqrt(sum((a - b) ** 2 for a, b in zip(mvals, N)))
            t = int(max(d - 0.01, 0.0)) if d - 0.01 < 2 ** 31 else INT_MIN
        if s32(radius - t) <= 0:
            continue
        li = gids.index(lg) if lg else k
        _, ldeaf, lmargin = info_state[li]
        if ldeaf:
            continue
        if combat or lmargin != INT_MAX:
            raise ValueError('%s: flag-1 setup could reach combat entry (group %d)' % (c.id, k))


def _noise_pos(r):
    if r.random() < 0.5:
        return (float(r.randrange(-3000, 3000)), float(r.randrange(0, 600)), float(r.randrange(-3000, 3000)))
    return (f32(r.uniform(-40000, 40000)), f32(r.uniform(-500, 3000)), f32(r.uniform(-40000, 40000)))


def _suspended(ctx, c, r):
    v = 0 if r.random() < 0.93 else r.choice([1, 2, 0xff])
    c.set(ctx.g('g_status') + GS_WORLD_SUSPENDED, u8(v))
    return v


def _alert_groups(ctx):
    """void AlertMonsterGroupsToNoise(const srVector3T<float>* position, int radius, int flag)"""
    fn = ctx.fn(0x004f0e80)
    pos = ctx.scratch(5)
    for i in range(ctx.n(350)):
        r = ctx.rng('alertgroups', i)
        c = ctx.case('alertgroups.%d' % i, fn, conv='c', ret='v')
        x = r.random()
        if x < 0.35:
            flag = 0
        elif x < 0.6:
            flag = 2
        elif x < 0.85:
            flag = 1
        else:
            flag = r.choice([3, -1, 0x100, 0x101, INT_MIN])
        combat = r.random() < 0.4
        radius = _noise_radius(r)
        if flag == 1 and not (0 <= radius < INT_MAX - 1000):
            radius = r.choice([25000, 50000, 0x927c])
        N = _noise_pos(r)
        susp = _suspended(ctx, c, r)
        notes = _noise_world(ctx, c, r, flag, combat, radius, N, pos)
        c.arg(pos)
        c.arg(radius)
        c.arg(flag)
        c.note(flag=flag, combat=int(combat), radius=radius, suspended=susp, **notes)


def _alert_combat(ctx):
    """void AlertCombatNoise(bool large_radius): startup world position, flag 0"""
    fn = ctx.fn(0x004f1150)
    nav = ctx.g('g_startup_world').deref() + 0x100
    for i in range(ctx.n(150)):
        r = ctx.rng('alertcombat', i)
        c = ctx.case('alertcombat.%d' % i, fn, conv='c', ret='v')
        arg = r.choice([0, 1, 0, 1, 2, 0xff, 0x100, 0x101, 0xffffff00])
        radius = 0x927c if arg & 0xff else 25000
        combat = r.random() < 0.4
        N = _noise_pos(r)
        susp = _suspended(ctx, c, r)
        notes = _noise_world(ctx, c, r, 0, combat, radius, N, nav)
        c.arg(arg)
        c.note(large_radius=arg, combat=int(combat), suspended=susp, **notes)


def _alert_world(ctx):
    """void AlertWorldNoise(void): startup world position, radius 50000, flag 1"""
    fn = ctx.fn(0x004f1100)
    nav = ctx.g('g_startup_world').deref() + 0x100
    for i in range(ctx.n(100)):
        r = ctx.rng('alertworld', i)
        c = ctx.case('alertworld.%d' % i, fn, conv='c', ret='v')
        combat = r.random() < 0.5
        N = _noise_pos(r)
        susp = _suspended(ctx, c, r)
        notes = _noise_world(ctx, c, r, 1, combat, 50000, N, nav)
        c.note(combat=int(combat), suspended=susp, **notes)
