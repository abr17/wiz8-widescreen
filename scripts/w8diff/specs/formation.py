"""FormationAndFacing.cpp + GroupAttacks.cpp (src/wiz8/local_code): party formation
bookkeeping, facing decisions, party/camera turning and the monster facing tests.

Tested (retail address, name, cases):
  0x005545d0 CopyPartyFormationState          100  random/real formations, dst == src
  0x005549e0 CanHoldFormationPlace            200  hp 0/1/2^31/2^32-1, conditions around
                                                   TURNCOAT (13), negative conditions
  0x00555e70 DecideFacingForPosition          300  all 36 source/target quadrant pairs
                                                   (-1..4) x3, position == target, bad
                                                   quadrants 5/6/0x7f/-2/-0x80
  0x005557e0 FacePositionAsDecided            250  same + facings 0..3/4/-1/-2/5/0x7f/0x80
  0x00555920 PositionFacesAsDecided           250
  0x00555c20 PositionFacesOppositeToDecided   250  (|decided - facing| == 2, signed bytes)
  0x00554bd0 SetFormationPosition             400  valid/taken seats, unseat (-1), corrupt
                                                   old seat/count (asserts), bad rows,
                                                   dirty upper bytes in char/bool args,
                                                   bool bytes 2/0x80/0xff/0x100
  0x00554dd0 CompactFormationRow              250  all 8 column layouts of a row, count
                                                   mismatch, row byte 5/6/0xff
  0x00554ae0 PlaceCharacterInFormation        250  rows 0/4/2 in every MakeRoom state
                                                   (0, lone leader, two, full, odd layouts)
  0x00554e70 UpdateFormationSlotState         350  dead/alive x seated/unseated x
                                                   bOldQuadrant -1/0..4/bad (signed vs
                                                   unsigned row index), negative conditions
  0x00555080 SeatFormationSlotInRow           250  every row state, full row (notice),
                                                   row with high bytes (0x100+row)
  0x00555160 SwapFormationSlots               300  b seated / b unseated with remembered
                                                   row, same slot (assert 0x296)
  0x00555fa0 RebuildPartyStatus               200  fOccupied 0/1/2/0x80/0xff, stale seats
  0x005545f0 ReconcilePartyFormation          350  edited vs live (moves/swaps/unseats),
                                                   ok/down/dead/empty members, a down
                                                   member's live row filled in edited
                                                   (fallback rows 4/2/3), aliased args,
                                                   negative conditions
  0x00554a20 SaveCombatFormation              100  g_combat_state = scratch S2
  0x00554a60 RestoreCombatFormation           150  equal / 1 byte / few bytes / all differ
  0x00555f30 GetQuadrantForPosition           400  camera position + party_facing set;
                                                   generic angles, integer quadrant edges,
                                                   dz == 0, party_facing out of range
  0x00555960 IsCharacterFacingMonster         250  fake W8MonsterInfo/W8Monster in S1
  0x00555820 TurnCharacterTowardMonster       250
  0x00555c60 IsMonsterBehindCharacter         250
  0x00555560 FaceCharacterTowardCombatTarget  300  target kinds 1/9 (character), 6 (place),
                                                   others; iChar -1 (assert 0x33a)
  0x005553c0 TurnPartyTo                      250  camera yaw set (GDCamera fields), return
                                                   compared only on the two paths where
                                                   retail leaves a defined eax
  0x00555420 TurnPartyToImmediate             250  snap bytes 0/1/2/0x100/...
  0x005554a0 FaceCameraToSelection            250  rotation mode/style, selection, facing
                                                   bytes up to 0xff
  0x005552f0 SyncPartyFacingFromCamera        250  combat mode x preserve flag x level
                                                   movement-stopped bit, negative yaw
  0x00555ba0 IsPartyLookingAt                 300  yaw around the 0.05 tolerance, wrap,
                                                   NaN/inf yaw
  0x00555a60 IsMonsterFacingParty             200  party position = g_startup_world nav
  0x00555b00 IsMonsterFacingMonster           200
  0x00555d60 IsPartyLookingAwayFrom           250  yaw around 3pi/4 (double tolerance)
  0x00555de0 IsMonsterLookingAwayFrom         300  (double tolerance as well; retail
                                                   0x00555e44 fcomp qword)
  0x00556050 MonsterSpecialAttackHonorsCastingBlock 133  kinds -16..99 + high-byte edges
  Total 7783 cases.

Set-up notes:
  * Formations in scratch sit at S<n>+0x400 and are captured over S<n>+0x200..+0x800, so
    out-of-range rows/columns (labelled edge=bad_row / bad_old_quadrant / row_high_bytes)
    stay inside the buffer and are compared. Otherwise g_status.formation is used (set +
    cap 0x84).
  * UI side effects are switched off per case and restored afterwards: screen id = automap
    (8) so ShowNotice / HighlightTextBoxRange / SetFormationPosition's refresh do nothing,
    g_status.selected_character = -1 and g_level_block->formation_board_visible = 0
    (RefreshFormationBoard returns), g_radar_map_enabled = 0 (RefreshRadarMap returns).
    gXStatus.fNpcDialogueMode is 0 wherever a notice can be posted (the dialogue text-box
    resolver dereferences g_npc_interaction_state).
  * Camera cases set the whole *g_gd_camera except the timer pointer (flags, yaw, pitch,
    the rest deterministic filler) and capture the 0xC0 object (floats with ULP
    tolerance, the timer pointer ignored); g_camera_transition_speed is set. The manual
    input timer is never polled: either fNpcDialogueMode = 1 or the MANUAL_INPUT flag is
    set (then the camera setters return early). formation_compass_sprite = 0 so
    UpdateFormationCompass only marks the renderer. Degrees that reach SetYaw stay below
    720 (at most one exact wrap); bigger values only with the guard.
  * Yaw/angle values sitting on an integer-degree truncation boundary are labelled
    edge=yaw_boundary / angle_boundary / tol_boundary: retail truncates the 80-bit x87
    product, so a difference only there is an FP-precision difference.
  * Edge inputs outside the enums are labelled: cond_negative (retail compares
    highest_condition unsigned), bool_byte (non-canonical bool bytes).

Skipped:
  0x005560a0 ResolveMonsterGroupAttack - damage/drain/fatigue/conditions on characters and
                                         monsters (deaths, monster removal), text lines;
                                         the two W8GrowableVector<int> arguments are passed
                                         by value and destroyed (freed) by the callee
  0x00556b10 SpawnSummonedMonsterGroup - creates a monster group in the world, positions
                                         it, starts its combat
  (MakeRoomInFormationRow is a port-only static helper without a FUNCTION annotation;
   covered through PlaceCharacterInFormation/UpdateFormationSlotState/Seat/Swap.)
  FaceCharacterTowardCombatTarget's monster kind (3) is not used: it looks the monster up
  by a live location id (GetMonsterByLocationID) whose position drifts.
"""
import math
import struct

from w8diff.api import F32

# W8PartyFormationState (party_formation.h, matches retail asm)
FORM = 0x84
CNT = 0x0f            # ubQuadrantOccupants[5]
POS = 0x14            # positions[8]
POS_STEP = 0x0c
P_ROW, P_OLD, P_COL, P_FACING = 0, 1, 2, 3
DEFAULT_FACING = [0, 1, 2, 3, 0]

# W8GlobalStatus
GS_GAME_STARTED = 0x0c
GS_SELECTED = 0x1d
GS_PARTY_FACING = 0x18d0
GS_PARTY_HEADING = 0x18d4
GS_FORMATION = 0x23a1

# W8XStatus
GX_COMBAT_MODE = 0x8dc
GX_NPC_DIALOGUE = 0x8df

# W8GameSettings
ST_CAM_ROT_MODE = 0x1d
ST_CAM_ROT_STYLE = 0x21

# W8LevelRuntimeBlock
LB_BOARD_VISIBLE = 0x156
LB_COMPASS_SPRITE = 0x2a4

# W8CombatState
CS_SAVED_FORMATION = 0x920

# GDCamera (0xC0)
CAM_FLAGS, CAM_YAW, CAM_PITCH = 0x00, 0x04, 0x08
CAM_POS = 0x8c
CAM_TIMER = 0xbc
CAM_SIZE = 0xc0
CAM_MANUAL_INPUT = 0x01
CAM_FLOATS = [o for o in range(0x04, 0xbc, 4) if o != 0x88]

# W8Navigator movement.position / movement.yaw; W8Monster's navigator base at +0x18
NAV_POS = 0x100
NAV_YAW = 0xd4
MON_NAV = 0x18
MI_P3D = 0x0c         # W8MonsterInfo::p3D

# W8Character / W8PartySlotRow
C_HCOND = 0xb01
C_HP = 0xb11
XROW = 0x106

# W8CombatSlot
SL_TYPE, SL_CHAR, SL_MONSTER, SL_POINT = 0x00, 0x04, 0x08, 0x10

SCREEN_AUTOMAP = 8    # not main game/camp/please-wait/character: notices are dropped

SCR_FORM = 0x400      # formation offset inside a scratch buffer
SCR_WIN = 0x200       # captured window around it
SCR_WIN_LEN = 0x600

YAW_SCALE = 57.295784          # GetCameraYawDegrees
TOL_LOOK = 0.05000000074505806  # g_facing_tolerance0 (float 0.05)
TOL_AWAY = 2.3561944500000003   # g_facing_tolerance1 (double)
TWO_PI = 2.0 * math.pi


def u8(v):
    return bytes([int(v) & 0xff])


def u32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def fb(x):
    return struct.pack('<f', x)


def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


def s8(v):
    v &= 0xff
    return v - 0x100 if v >= 0x80 else v


def _f2o(x):
    i = struct.unpack('<I', struct.pack('<f', x))[0]
    return i if i < 0x80000000 else -(i & 0x7fffffff)


def _o2f(o):
    i = o if o >= 0 else (0x80000000 | (-o))
    return struct.unpack('<f', struct.pack('<I', i & 0xffffffff))[0]


def _ulps(x, k):
    """float32 x moved by k units in the last place."""
    return _o2f(_f2o(f32(x)) + k)


FLAG_EDGE = [2, 0x80, 0xff, 0x100, 0x101, 0xffffff00]


def _flag(r, p_true=0.5, edge_p=0.12):
    """A bool argument (retail tests the low byte only)."""
    if r.random() < edge_p:
        return r.choice(FLAG_EDGE)
    return 1 if r.random() < p_true else 0


def _dirty(r, v, p=0.1):
    """A char argument, sometimes with garbage in the upper three bytes."""
    v = int(v) & 0xff
    if r.random() < p:
        v |= r.getrandbits(24) << 8
    return v


def _bool_byte(r, p_true, edge_p=0.0):
    if r.random() < p_true:
        return r.choice([2, 0x80, 0xff]) if r.random() < edge_p else 1
    return 0


COND_EDGE = [0x80000000, 0xffffffff, 0xfffffff0]


def _hp(r):
    x = r.random()
    if x < 0.2:
        return 0
    if x < 0.8:
        return r.randrange(1, 500)
    return r.choice([1, 0x7fffffff, 0x80000000, 0xffffffff])


def _cond(r, edge_p=0.0):
    x = r.random()
    if x < edge_p:
        return r.choice(COND_EDGE)
    if x < 0.4:
        return 0
    if x < 0.8:
        return r.randrange(1, 0x15)
    return r.choice([0x0c, 0x0d, 0x0e, 0x11, 0x12, 0x13])


# --------------------------------------------------------------------------------------
# formation builders
def _empty_form():
    """InitializePartyFormation: no occupants, every position unseated, facing 4."""
    b = bytearray(FORM)
    for k in range(15):
        b[k] = 0xff
    for s in range(8):
        o = POS + s * POS_STEP
        b[o + P_ROW] = b[o + P_OLD] = b[o + P_COL] = 0xff
        b[o + P_FACING] = 4
    return b


def _row_of(b, s):
    return s8(b[POS + s * POS_STEP + P_ROW])


def _col_of(b, s):
    return s8(b[POS + s * POS_STEP + P_COL])


def _seat(b, s, row, col):
    b[row * 3 + col] = s
    b[CNT + row] += 1
    o = POS + s * POS_STEP
    b[o + P_ROW] = row
    b[o + P_COL] = col


def _unseat(b, s):
    o = POS + s * POS_STEP
    row, col = _row_of(b, s), _col_of(b, s)
    if 0 <= row <= 4 and 0 <= col <= 2:
        if b[row * 3 + col] == s:
            b[row * 3 + col] = 0xff
        if b[CNT + row]:
            b[CNT + row] -= 1
    b[o + P_ROW] = b[o + P_COL] = 0xff


def _swap_seats(b, s1, s2):
    r1, c1, r2, c2 = _row_of(b, s1), _col_of(b, s1), _row_of(b, s2), _col_of(b, s2)
    _unseat(b, s1)
    _unseat(b, s2)
    if r2 != -1:
        _seat(b, s1, r2, c2)
    if r1 != -1:
        _seat(b, s2, r1, c1)


def _free_seats(b, rows=range(5)):
    return [(row, col) for row in rows for col in range(3) if b[row * 3 + col] == 0xff]


def _dress(b, r, noise_p=0.3):
    """Facings and remembered quadrants as the game leaves them, sometimes odd values;
    sometimes random bytes in the unknown parts (copied verbatim by some paths)."""
    for s in range(8):
        o = POS + s * POS_STEP
        row = s8(b[o + P_ROW])
        if 0 <= row <= 4:
            x = r.random()
            if x < 0.6:
                f = DEFAULT_FACING[row]
            elif x < 0.92:
                f = r.randrange(4)
            else:
                f = r.choice([4, 0xff, 5, 0x80, 0x7f, 0xfe])
            b[o + P_FACING] = f
            b[o + P_OLD] = 0xff if r.random() < 0.8 else r.randrange(5)
        else:
            b[o + P_FACING] = r.choice([0, 1, 2, 3, 4, 4])
            b[o + P_OLD] = 0xff if r.random() < 0.5 else r.randrange(5)
    if r.random() < noise_p:
        for s in range(8):
            o = POS + s * POS_STEP + 4
            b[o:o + 8] = bytes(r.getrandbits(8) for _ in range(8))
        b[0x74:0x84] = bytes(r.getrandbits(8) for _ in range(16))
    return b


CANON = {0: [], 1: [0], 2: [1, 2], 3: [0, 1, 2]}


def _random_form(r, seated=None, layout=None, dress=True):
    """A consistent formation. canonical: rows the way the game's own seating leaves them
    (one -> column 0, two -> columns 1,2); free: any seats (edited formations)."""
    b = _empty_form()
    if seated is None:
        k = r.choice([8, 8, 8, 7, 7, 6, 6, 5, 4, 3, 2, 1, 0])
        seated = r.sample(range(8), k)
    if layout is None:
        layout = 'canonical' if r.random() < 0.6 else 'free'
    if layout == 'canonical':
        rows = {}
        counts = [0] * 5
        for s in seated:
            row = r.choice([x for x in range(5) if counts[x] < 3])
            counts[row] += 1
            rows.setdefault(row, []).append(s)
        for row in sorted(rows):
            cols = list(CANON[len(rows[row])])
            r.shuffle(cols)
            for s, col in zip(rows[row], cols):
                _seat(b, s, row, col)
    else:
        for s, (row, col) in zip(seated, r.sample(_free_seats(b), len(seated))):
            _seat(b, s, row, col)
    if dress:
        _dress(b, r)
    return b


ROW_REAL = [[], [0], [1, 2], [0, 1, 2]]
ROW_ODD = [[1], [2], [0, 1], [0, 2]]


def _row_cols(r, odd_p=0.25):
    return list(r.choice(ROW_ODD if r.random() < odd_p else ROW_REAL))


def _form_rows(r, fixed, avoid=(), fill=None):
    """Rows of `fixed` ({row: [cols]}) seated with random slots (not in avoid); the other
    slots go to free seats of the other rows with probability `fill`. Not dressed."""
    b = _empty_form()
    pool = [s for s in range(8) if s not in avoid]
    r.shuffle(pool)
    for row in sorted(fixed):
        for col in fixed[row]:
            if pool:
                _seat(b, pool.pop(), row, col)
    if fill is None:
        fill = r.choice([0.0, 0.4, 0.8, 1.0])
    free = _free_seats(b, [x for x in range(5) if x not in fixed])
    r.shuffle(free)
    for s in pool:
        if free and r.random() < fill:
            row, col = free.pop()
            _seat(b, s, row, col)
    return b


# --------------------------------------------------------------------------------------
# common set-up
def _xrow(ctx, slot):
    return (ctx.g('g_status') + 8).deref() + slot * XROW


def _quiet_ui(ctx, c, npc=0, started=1):
    """Notices and formation/radar redraws become no-ops (restored after the case)."""
    gs = ctx.g('g_status')
    c.set(ctx.g('g_current_screen_state'), u32(SCREEN_AUTOMAP))
    c.set(gs + GS_SELECTED, u32(-1))
    c.set(ctx.g('g_level_block').deref() + LB_BOARD_VISIBLE, u8(0))
    c.set(ctx.g('g_radar_map_enabled'), u8(0))
    c.set(ctx.g('gXStatus') + GX_NPC_DIALOGUE, u8(npc))
    c.set(gs + GS_GAME_STARTED, u8(started))


def _place_form(ctx, c, b, use_gs, n=0, name='formation'):
    """Put formation bytes in g_status.formation or in scratch n; capture them."""
    if use_gs:
        a = ctx.g('g_status') + GS_FORMATION
        c.set(a, bytes(b))
        c.cap(a, FORM, name)
    else:
        a = ctx.scratch(n) + SCR_FORM
        c.set(a, bytes(b))
        c.cap(ctx.scratch(n) + SCR_WIN, SCR_WIN_LEN, name)
    return a


def _edges(c, edges):
    if edges:
        c.note(edge=','.join(sorted(set(edges))))


def cases(ctx):
    _copy_state(ctx)
    _can_hold(ctx)
    _decide_family(ctx)
    _set_position(ctx)
    _compact_row(ctx)
    _place_character(ctx)
    _update_slot_state(ctx)
    _seat_in_row(ctx)
    _swap_slots(ctx)
    _rebuild_status(ctx)
    _reconcile(ctx)
    _save_combat(ctx)
    _restore_combat(ctx)
    _quadrant(ctx)
    _quadrant_monster(ctx)
    _face_combat_target(ctx)
    _turn_party_to(ctx)
    _turn_party_immediate(ctx)
    _face_camera_selection(ctx)
    _sync_facing(ctx)
    _looking_at(ctx)
    _looking_away(ctx)
    _casting_block(ctx)


# --------------------------------------------------------------------------------------
def _copy_state(ctx):
    """void CopyPartyFormationState(dst, src): 33 dwords."""
    fn = ctx.fn(0x005545d0)
    for i in range(ctx.n(100)):
        r = ctx.rng('copy', i)
        c = ctx.case('copyformation.%d' % i, fn, conv='c', ret='v')
        if r.random() < 0.7:
            src = _random_form(r)
        else:
            src = bytearray(r.getrandbits(8) for _ in range(FORM))
        same = i < 5
        dst = ctx.scratch(0) + SCR_FORM
        if same:
            c.set(dst, bytes(src))
            c.cap(ctx.scratch(0) + SCR_WIN, SCR_WIN_LEN, 'dst')
            c.arg(dst)
            c.arg(dst)
        else:
            old = bytearray(r.getrandbits(8) for _ in range(FORM)) if r.random() < 0.7 \
                else bytearray(FORM)
            sa = ctx.scratch(1) + SCR_FORM
            c.set(dst, bytes(old))
            c.set(sa, bytes(src))
            c.cap(ctx.scratch(0) + SCR_WIN, SCR_WIN_LEN, 'dst')
            c.cap(ctx.scratch(1) + SCR_WIN, SCR_WIN_LEN, 'src')
            c.arg(dst)
            c.arg(sa)
        c.note(same=int(same))


def _can_hold(ctx):
    """bool CanHoldFormationPlace(int slot): hp != 0 (unsigned) && condition < 13 (unsigned)."""
    fn = ctx.fn(0x005549e0)
    for i in range(ctx.n(200)):
        r = ctx.rng('canhold', i)
        c = ctx.case('canholdformationplace.%d' % i, fn, conv='c', ret='b')
        slot = r.randrange(8)
        hp = _hp(r)
        cond = _cond(r, edge_p=0.08)
        ch = ctx.char(slot)
        c.set(ch + C_HCOND, u32(cond))
        c.set(ch + C_HP, u32(hp))
        c.arg(slot)
        c.note(slot=slot, hp=hp, cond=cond)
        _edges(c, ['cond_negative'] if cond >= 0x80000000 else [])


# --------------------------------------------------------------------------------------
QUADS = [-1, 0, 1, 2, 3, 4]
BAD_QUADS = [5, 6, 0x7f, -2, -0x80]
FACINGS_ODD = [4, -1, -2, 5, 6, 0x7f, -0x80]
COMBOS = [(sq, tq) for sq in QUADS for tq in QUADS]


def _facing_form(ctx, c, r, i):
    """g_status.formation with chosen quadrants of (position, target) and a facing of
    position. Returns (position, target)."""
    b = _random_form(r)
    pos = r.randrange(8)
    others = [s for s in range(8) if s != pos]
    if i < 3 * len(COMBOS):
        sq, tq = COMBOS[i % len(COMBOS)]
        tgt = r.choice(others)
    else:
        tgt = pos if r.random() < 0.1 else r.choice(others)
        x = r.random()
        if x < 0.25:
            sq, tq = _row_of(b, pos), _row_of(b, tgt)
        elif x < 0.9:
            sq, tq = r.choice(QUADS), r.choice(QUADS)
        else:
            sq, tq = r.choice(QUADS + BAD_QUADS), r.choice(QUADS + BAD_QUADS)
    b[POS + pos * POS_STEP + P_ROW] = sq & 0xff
    if tgt != pos:
        b[POS + tgt * POS_STEP + P_ROW] = tq & 0xff
    else:
        tq = sq
    facing = r.randrange(4) if r.random() < 0.75 else r.choice(FACINGS_ODD)
    b[POS + pos * POS_STEP + P_FACING] = facing & 0xff
    c.set(ctx.g('g_status') + GS_FORMATION, bytes(b))
    c.note(pos=pos, tgt=tgt, sq=sq, tq=tq, facing=facing)
    _edges(c, ['bad_quadrant'] if (sq in BAD_QUADS or tq in BAD_QUADS) else [])
    return pos, tgt


def _decide_family(ctx):
    gs_form = ctx.g('g_status') + GS_FORMATION
    # signed char DecideFacingForPosition(int position, int target_position)
    fn = ctx.fn(0x00555e70)
    for i in range(ctx.n(300)):
        r = ctx.rng('decide', i)
        c = ctx.case('decidefacing.%d' % i, fn, conv='c', ret='i8')
        pos, tgt = _facing_form(ctx, c, r, i)
        c.arg(pos)
        c.arg(tgt)
    # void FacePositionAsDecided(int position, int target_position)
    fn = ctx.fn(0x005557e0)
    for i in range(ctx.n(250)):
        r = ctx.rng('faceposition', i)
        c = ctx.case('facepositionasdecided.%d' % i, fn, conv='c', ret='v')
        _quiet_ui(ctx, c, npc=0, started=r.choice([0, 1, 1]))
        pos, tgt = _facing_form(ctx, c, r, i)
        c.cap(gs_form, FORM, 'formation')
        c.arg(pos)
        c.arg(tgt)
    # bool PositionFacesAsDecided(int position, int target_position)
    fn = ctx.fn(0x00555920)
    for i in range(ctx.n(250)):
        r = ctx.rng('facesasdecided', i)
        c = ctx.case('positionfacesasdecided.%d' % i, fn, conv='c', ret='b')
        pos, tgt = _facing_form(ctx, c, r, i)
        c.arg(pos)
        c.arg(tgt)
    # bool PositionFacesOppositeToDecided(int target_position, int position)
    fn = ctx.fn(0x00555c20)
    for i in range(ctx.n(250)):
        r = ctx.rng('facesopposite', i)
        c = ctx.case('positionfacesopposite.%d' % i, fn, conv='c', ret='b')
        pos, tgt = _facing_form(ctx, c, r, i)
        c.arg(tgt)
        c.arg(pos)


# --------------------------------------------------------------------------------------
def _set_position(ctx):
    """void SetFormationPosition(formation, int slot, signed char row, signed char column,
    bool announce, bool detach, bool update_facing)"""
    fn = ctx.fn(0x00554bd0)
    for i in range(ctx.n(400)):
        r = ctx.rng('setposition', i)
        c = ctx.case('setformationposition.%d' % i, fn, conv='c', ret='v')
        use_gs = r.random() < 0.15
        b = _random_form(r)
        slot = r.randrange(8)
        o = POS + slot * POS_STEP
        edges = []
        old_row, old_col = _row_of(b, slot), _col_of(b, slot)
        x = r.random()
        if old_row != -1 and x < 0.05:
            b[old_row * 3 + old_col] = 0xff          # assert 0x18e
            edges.append('old_seat_empty')
        elif old_row != -1 and x < 0.09:
            b[CNT + old_row] = 0                     # assert 0x18f, count wraps
            edges.append('old_count_zero')
        if not use_gs and r.random() < 0.05:
            new_row = r.choice([5, 6, 0x7f, -2, -0x80])
            new_col = r.choice([-1, 0, 2, 3, 0x7f, -0x80])
            if r.random() < 0.5:
                b[o + P_ROW] = r.choice([5, 0x7f, 0xfe, 0x80])
                b[o + P_COL] = r.randrange(256)
            edges.append('bad_row')
        elif r.random() < 0.15:
            new_row, new_col = -1, r.choice([-1, -1, 0, 2])
        else:
            new_row = r.randrange(5)
            free = [col for col in range(3) if b[new_row * 3 + col] == 0xff]
            if _row_of(b, slot) == new_row and 0 <= _col_of(b, slot) <= 2:
                free.append(_col_of(b, slot))
            if free and r.random() < 0.88:
                new_col = r.choice(free)
            else:
                new_col = r.randrange(3)
                if new_col not in free:
                    edges.append('seat_taken')
        announce, detach, facing = _flag(r), _flag(r), _flag(r, 0.7)
        if any(v not in (0, 1) for v in (announce, detach, facing)):
            edges.append('bool_byte')
        _quiet_ui(ctx, c, npc=r.choice([0, 0, 1]), started=r.choice([0, 1, 1]))
        a = _place_form(ctx, c, b, use_gs)
        row_arg, col_arg = _dirty(r, new_row), _dirty(r, new_col)
        c.arg(a)
        c.arg(slot)
        c.arg(row_arg)
        c.arg(col_arg)
        c.arg(announce)
        c.arg(detach)
        c.arg(facing)
        c.note(gs=int(use_gs), slot=slot, old=(old_row, old_col), new=(new_row, new_col),
               flags=(announce, detach, facing), row_arg=row_arg, col_arg=col_arg)
        _edges(c, edges)


COMPACT_STATES = [[], [0], [1], [2], [0, 1], [0, 2], [1, 2], [0, 1, 2]]


def _compact_row(ctx):
    """void CompactFormationRow(formation, unsigned char row)"""
    fn = ctx.fn(0x00554dd0)
    for i in range(ctx.n(250)):
        r = ctx.rng('compact', i)
        c = ctx.case('compactformationrow.%d' % i, fn, conv='c', ret='v')
        use_gs = r.random() < 0.15
        row = r.randrange(5)
        cols = list(COMPACT_STATES[i % 8]) if i < 80 else list(r.choice(COMPACT_STATES))
        b = _form_rows(r, {row: cols})
        _dress(b, r)
        edges = []
        if r.random() < 0.08:
            b[CNT + row] = r.choice([v for v in (0, 1, 2, 3, 4, 0xff) if v != len(cols)])
            edges.append('count_mismatch')
        arg = row
        if not use_gs and r.random() < 0.04:
            arg = r.choice([5, 6, 0xff])     # bytes of the formation itself / beyond
            edges.append('bad_row')
        arg = _dirty(r, arg, 0.12)
        _quiet_ui(ctx, c, npc=r.choice([0, 1]), started=r.choice([0, 1, 1]))
        a = _place_form(ctx, c, b, use_gs)
        c.arg(a)
        c.arg(arg)
        c.note(gs=int(use_gs), row=row, cols=cols, count=b[CNT + row], arg=arg)
        _edges(c, edges)


ORDER = [0, 4, 2]
TARGET_ROW_STATES = [[], [0], [1, 2], [], [0], [1, 2], [1], [2], [0, 1], [0, 2]]


def _place_character(ctx):
    """void PlaceCharacterInFormation(formation, int slot): rows 0, 4, 2."""
    fn = ctx.fn(0x00554ae0)
    for i in range(ctx.n(250)):
        r = ctx.rng('place', i)
        c = ctx.case('placecharacterinformation.%d' % i, fn, conv='c', ret='v')
        use_gs = r.random() < 0.2
        slot = r.randrange(8)
        target = r.choice([0, 0, 0, 4, 4, 2, 2, None])
        fixed = {}
        for k, row in enumerate(ORDER):
            if target is None or k < ORDER.index(target):
                fixed[row] = [0, 1, 2]
            elif row == target:
                fixed[row] = list(r.choice(TARGET_ROW_STATES))
            else:
                fixed[row] = _row_cols(r)
        stale = r.random() < 0.15
        b = _form_rows(r, fixed, avoid=() if stale else (slot,))
        edges = []
        if stale:
            if _row_of(b, slot) == -1:
                free = _free_seats(b)
                if free:
                    row, col = r.choice(free)
                    _seat(b, slot, row, col)
            edges.append('joiner_seated')
        if target is None:
            for row in ORDER:
                if b[CNT + row] < 3:
                    b[CNT + row] = 3
                    edges.append('no_room')
        _dress(b, r)
        _quiet_ui(ctx, c, npc=r.choice([0, 1]), started=r.choice([0, 1, 1]))
        a = _place_form(ctx, c, b, use_gs)
        c.arg(a)
        c.arg(slot)
        c.note(gs=int(use_gs), slot=slot, target=target,
               rows=';'.join('%d:%s' % (row, ''.join(str(x) for x in fixed[row])) for row in ORDER))
        _edges(c, edges)


def _update_slot_state(ctx):
    """void UpdateFormationSlotState(formation, int slot)"""
    fn = ctx.fn(0x00554e70)
    for i in range(ctx.n(350)):
        r = ctx.rng('updateslot', i)
        c = ctx.case('updateformationslotstate.%d' % i, fn, conv='c', ret='v')
        use_gs = r.random() < 0.25
        slot = r.randrange(8)
        dead = r.random() < 0.4
        edges = []
        if r.random() < 0.05:
            cond = r.choice(COND_EDGE)
            edges.append('cond_negative')
        elif dead:
            cond = r.choice([0x12, 0x12, 0x13, 0x14, 0x15, 0x100])
        else:
            cond = r.choice([0, 0, 0, 0, r.randrange(1, 0x12), 0x11, 0x0d])
        seated = r.random() < (0.7 if dead else 0.3)
        others = [s for s in range(8) if s != slot]
        seat_list = r.sample(others, r.randrange(0, 8)) + ([slot] if seated else [])
        r.shuffle(seat_list)
        b = _random_form(r, seated=seat_list)
        o = POS + slot * POS_STEP
        old = s8(b[o + P_OLD])
        if not seated:
            x = r.random()
            if x < 0.3:
                old = -1
            elif not use_gs and x < 0.38:
                old = r.choice([5, 0x7f, -0x80, -2, -3])
                edges.append('bad_old_quadrant')
            else:
                old = r.randrange(5)
            b[o + P_OLD] = old & 0xff
        _quiet_ui(ctx, c, npc=r.choice([0, 1]), started=r.choice([0, 1, 1]))
        c.set(ctx.char(slot) + C_HCOND, u32(cond))
        a = _place_form(ctx, c, b, use_gs)
        c.arg(a)
        c.arg(slot)
        c.note(gs=int(use_gs), slot=slot, cond=cond, seated=int(seated), old=old,
               old_count=b[CNT + old] if 0 <= old <= 4 else None)
        _edges(c, edges)


def _seat_in_row(ctx):
    """void SeatFormationSlotInRow(formation, int slot, int row)"""
    fn = ctx.fn(0x00555080)
    for i in range(ctx.n(250)):
        r = ctx.rng('seatrow', i)
        c = ctx.case('seatformationslotinrow.%d' % i, fn, conv='c', ret='v')
        use_gs = r.random() < 0.2
        row = r.randrange(5)
        cols = _row_cols(r, 0.25)
        slot = r.randrange(8)
        b = _form_rows(r, {row: cols}, avoid=(slot,))
        moved = False
        if r.random() < 0.3:
            free = _free_seats(b, [x for x in range(5) if x != row])
            if free:
                rr, cc = r.choice(free)
                _seat(b, slot, rr, cc)
                moved = True
        _dress(b, r)
        edges = []
        arg = row
        if not use_gs and r.random() < 0.07:
            # retail indexes the row tables with the low byte of the row (0x0055508d)
            arg = r.choice([0x100 + row, 0x200 + row])
            edges.append('row_high_bytes')
        _quiet_ui(ctx, c, npc=0, started=r.choice([0, 1, 1]))
        a = _place_form(ctx, c, b, use_gs)
        c.arg(a)
        c.arg(slot)
        c.arg(arg)
        c.note(gs=int(use_gs), slot=slot, row=row, cols=cols, moved=int(moved), arg=arg)
        _edges(c, edges)


def _swap_slots(ctx):
    """void SwapFormationSlots(formation, int slot_a, int slot_b)"""
    fn = ctx.fn(0x00555160)
    for i in range(ctx.n(300)):
        r = ctx.rng('swap', i)
        c = ctx.case('swapformationslots.%d' % i, fn, conv='c', ret='v')
        use_gs = r.random() < 0.2
        a = r.randrange(8)
        sb = a if r.random() < 0.03 else r.choice([s for s in range(8) if s != a])
        b_seated = r.random() < 0.6
        a_seated = r.random() < 0.7
        edges = ['same_slot'] if a == sb else []
        old = None
        if b_seated:
            others = [s for s in range(8) if s not in (a, sb)]
            seat_list = r.sample(others, r.randrange(0, len(others) + 1)) + [sb]
            if a_seated and a != sb:
                seat_list.append(a)
            r.shuffle(seat_list)
            f = _random_form(r, seated=seat_list)
        else:
            row = r.randrange(5)
            avoid = (sb,) if a_seated and a != sb else (sb, a)
            f = _form_rows(r, {row: _row_cols(r, 0.25)}, avoid=avoid)
            if a_seated and a != sb and _row_of(f, a) == -1:
                free = _free_seats(f)
                if free:
                    rr, cc = r.choice(free)
                    _seat(f, a, rr, cc)
            _dress(f, r)
            x = r.random()
            if x < 0.2:
                old = -1
            elif not use_gs and x < 0.27:
                old = r.choice([5, 0x7f, -0x80, -2])
                edges.append('bad_old_quadrant')
            else:
                old = row
            f[POS + sb * POS_STEP + P_OLD] = old & 0xff
        _quiet_ui(ctx, c, npc=0, started=r.choice([0, 1, 1]))
        fa = _place_form(ctx, c, f, use_gs)
        c.arg(fa)
        c.arg(a)
        c.arg(sb)
        c.note(gs=int(use_gs), a=a, b=sb, a_seat=(_row_of(f, a), _col_of(f, a)),
               b_seat=(_row_of(f, sb), _col_of(f, sb)), b_old=old,
               old_count=f[CNT + old] if old is not None and 0 <= old <= 4 else None)
        _edges(c, edges)


def _rebuild_status(ctx):
    """void RebuildPartyStatus(formation): unseat positions of unoccupied party rows."""
    fn = ctx.fn(0x00555fa0)
    for i in range(ctx.n(200)):
        r = ctx.rng('rebuild', i)
        c = ctx.case('rebuildpartystatus.%d' % i, fn, conv='c', ret='v')
        use_gs = r.random() < 0.3
        b = _random_form(r)
        edges = []
        for s in range(8):
            o = POS + s * POS_STEP
            if _row_of(b, s) != -1 and r.random() < 0.06:
                b[o + P_COL] = 0xff
                edges.append('no_column')
            elif _row_of(b, s) == -1 and r.random() < 0.1:
                b[o + P_COL] = r.randrange(3)
        p = r.choice([0.5, 0.8, 1.0])
        occ = [_bool_byte(r, p, 0.05) for _ in range(8)]
        if any(v not in (0, 1) for v in occ):
            edges.append('bool_byte')
        _quiet_ui(ctx, c, npc=r.choice([0, 1]), started=r.choice([0, 1, 1]))
        for s in range(8):
            c.set(_xrow(ctx, s), u8(occ[s]))
        a = _place_form(ctx, c, b, use_gs)
        c.arg(a)
        c.note(gs=int(use_gs), occ='.'.join('%x' % v for v in occ),
               rows=''.join('%x' % (_row_of(b, s) & 0xf) for s in range(8)))
        _edges(c, edges)


def _reconcile(ctx):
    """void ReconcilePartyFormation(edited, live)"""
    fn = ctx.fn(0x005545f0)
    for i in range(ctx.n(350)):
        r = ctx.rng('reconcile', i)
        c = ctx.case('reconcilepartyformation.%d' % i, fn, conv='c', ret='v')
        edges = []
        state = []
        for s in range(8):
            x = r.random()
            state.append('empty' if x < 0.1 else 'ok' if x < 0.68 else 'down' if x < 0.84
                         else 'dead')
        live_seats = [s for s in range(8) if state[s] in ('ok', 'down') or
                      (state[s] == 'dead' and r.random() < 0.15) or
                      (state[s] == 'empty' and r.random() < 0.05)]
        r.shuffle(live_seats)
        live = _random_form(r, seated=live_seats)
        edited = bytearray(live)
        oks = [s for s in range(8) if state[s] == 'ok']
        for _ in range(r.choice([0, 1, 1, 2, 2, 3, 4, 6])):
            x = r.random()
            if x < 0.45 and oks:
                s = r.choice(oks)
                free = _free_seats(edited)
                if free:
                    row, col = r.choice(free)
                    _unseat(edited, s)
                    _seat(edited, s, row, col)
            elif x < 0.8:
                seated_e = [s for s in range(8) if _row_of(edited, s) != -1]
                if len(seated_e) >= 2:
                    s1, s2 = r.sample(seated_e, 2)
                    _swap_seats(edited, s1, s2)
            elif oks:
                _unseat(edited, r.choice(oks))
        downs = [s for s in range(8) if state[s] == 'down']
        if downs and oks and r.random() < 0.3:
            # fill a down member's live row with holdable members in the edited formation
            x_slot = r.choice(downs)
            row = _row_of(live, x_slot)
            if _row_of(edited, x_slot) == row:
                _unseat(edited, x_slot)
                free = _free_seats(edited, [q for q in range(5) if q != row])
                if free and r.random() < 0.7:
                    rr, cc = r.choice(free)
                    _seat(edited, x_slot, rr, cc)
            for col in range(3):
                occ = edited[row * 3 + col]
                if occ != 0xff and state[occ] == 'ok':
                    continue
                if occ != 0xff:
                    _unseat(edited, occ)
                cands = [s for s in oks if _row_of(edited, s) != row]
                if not cands:
                    break
                s = r.choice(cands)
                _unseat(edited, s)
                _seat(edited, s, row, col)
            edges.append('full_row')
        if r.random() < 0.3:
            for s in range(8):
                edited[POS + s * POS_STEP + P_FACING] = r.choice([0, 1, 2, 3, 4])
        # party fields
        occ, hp, cond = [], [], []
        for s in range(8):
            st = state[s]
            o = 0 if st == 'empty' else (r.choice([2, 0x80]) if r.random() < 0.03 else 1)
            if o not in (0, 1):
                edges.append('bool_byte')
            if st == 'empty':
                h, k = _hp(r), _cond(r)
            elif st == 'ok':
                h = r.randrange(1, 500) if r.random() < 0.95 else r.choice([0x80000000, 0xffffffff])
                k = 0 if r.random() < 0.7 else r.randrange(1, 0x0d)
            elif st == 'down':
                if r.random() < 0.5:
                    h, k = 0, r.choice([0, 0, r.randrange(1, 0x12)])
                else:
                    h, k = r.randrange(1, 500), r.randrange(0x0d, 0x12)
            else:
                h, k = r.choice([0, 0, r.randrange(1, 300)]), r.choice([0x12, 0x12, 0x13, 0x14, 0x20])
            occ.append(o)
            hp.append(h)
            cond.append(k)
        if oks and r.random() < 0.05:
            s = r.choice(oks)
            cond[s] = r.choice(COND_EDGE)
            edges.append('cond_negative')
        aliased = r.random() < 0.03
        _quiet_ui(ctx, c, npc=0, started=r.choice([0, 1, 1]))
        for s in range(8):
            c.set(_xrow(ctx, s), u8(occ[s]))
            c.set(ctx.char(s) + C_HCOND, u32(cond[s]))
            c.set(ctx.char(s) + C_HP, u32(hp[s]))
        if aliased:
            la = _place_form(ctx, c, live, False, 1, 'live')
            ea = la
            edges.append('aliased')
        else:
            ea = _place_form(ctx, c, edited, False, 0, 'edited')
            la = _place_form(ctx, c, live, False, 1, 'live')
        c.arg(ea)
        c.arg(la)
        c.note(state=''.join(x[0] for x in state),
               live=''.join('%x' % (_row_of(live, s) & 0xf) for s in range(8)),
               edited=''.join('%x' % (_row_of(edited, s) & 0xf) for s in range(8)))
        _edges(c, edges)


def _save_combat(ctx):
    """void SaveCombatFormation(void): g_combat_state->saved_formation = g_status.formation"""
    fn = ctx.fn(0x00554a20)
    gs_form = ctx.g('g_status') + GS_FORMATION
    cs = ctx.scratch(2)
    for i in range(ctx.n(100)):
        r = ctx.rng('savecombat', i)
        c = ctx.case('savecombatformation.%d' % i, fn, conv='c', ret='v')
        combat = 1 if r.random() < 0.9 else r.choice([0, 0, 2])
        form = _random_form(r) if r.random() < 0.8 else bytearray(r.getrandbits(8) for _ in range(FORM))
        old = bytearray(r.getrandbits(8) for _ in range(FORM)) if r.random() < 0.6 else bytearray(FORM)
        c.set(ctx.g('gXStatus') + GX_COMBAT_MODE, u8(combat))
        c.set(gs_form, bytes(form))
        c.setp(ctx.g('g_combat_state'), cs)
        c.set(cs + CS_SAVED_FORMATION, bytes(old))
        c.cap(cs + CS_SAVED_FORMATION - 0x20, FORM + 0x40, 'saved_formation')
        c.cap(gs_form, FORM, 'formation')
        c.note(combat=combat)


def _restore_combat(ctx):
    """void RestoreCombatFormation(void)"""
    fn = ctx.fn(0x00554a60)
    gs_form = ctx.g('g_status') + GS_FORMATION
    cs = ctx.scratch(2)
    for i in range(ctx.n(150)):
        r = ctx.rng('restorecombat', i)
        c = ctx.case('restorecombatformation.%d' % i, fn, conv='c', ret='v')
        combat = 1 if r.random() < 0.9 else r.choice([0, 0, 2])
        saved = _random_form(r)
        live = bytearray(saved)
        x = r.random()
        if x < 0.35:
            kind = 'equal'
        elif x < 0.6:
            kind = 'one_byte'
            k = r.randrange(FORM)
            live[k] ^= 1 << r.randrange(8)
        elif x < 0.85:
            kind = 'few_bytes'
            for _ in range(r.randrange(2, 8)):
                live[r.randrange(FORM)] = r.getrandbits(8)
        else:
            kind = 'other'
            live = _random_form(r)
        _quiet_ui(ctx, c, npc=0, started=r.choice([0, 1, 1]))
        c.set(ctx.g('gXStatus') + GX_COMBAT_MODE, u8(combat))
        c.set(gs_form, bytes(live))
        c.setp(ctx.g('g_combat_state'), cs)
        c.set(cs + CS_SAVED_FORMATION, bytes(saved))
        c.cap(gs_form, FORM, 'formation')
        c.cap(cs + CS_SAVED_FORMATION - 0x20, FORM + 0x40, 'saved_formation')
        c.note(combat=combat, kind=kind)


# --------------------------------------------------------------------------------------
# quadrants: camera position + party_facing
def _party_facing(r):
    x = r.random()
    if x < 0.7:
        return r.randrange(360)
    if x < 0.85:
        return r.choice([0, 45, 90, 135, 180, 225, 270, 315, 359])
    return r.choice([360, 405, 719, 720, 1000, -1, -45, -90, -359, -360, -361, -1000,
                     0x7fffffff, -0x80000000, 0x7fffffd2])


def _facing_edge(facing):
    """party_facing whose subtraction from the bearing overflows int32."""
    return ['facing_overflow'] if abs(facing) >= 0x7fff0000 else []


def _world_pos(r, spread=30000.0):
    return (f32(r.uniform(-spread, spread)), f32(r.uniform(-500, 500)), f32(r.uniform(-spread, spread)))


def _quadrant_point(r, origin, facing):
    """A point around origin whose bearing (degrees, 0 = +z, 90 = +x) is generic (away from
    integer degrees), on a quadrant edge at integer level, exactly integer, or dz == 0."""
    x = r.random()
    near = r.random() < 0.05
    d = r.uniform(2, 50) if near else r.choice([r.uniform(50, 3000), r.uniform(3000, 40000)])
    y = f32(origin[1] + r.uniform(-300, 300))
    label = 'near' if near else None
    if x < 0.05:
        dx = r.choice([d, -d, 0.0])
        return (f32(origin[0] + dx), y, origin[2]), 'dz0', None
    if x < 0.15:
        deg = float(r.randrange(360))
        label = 'angle_boundary'
    elif x < 0.4:
        k = (facing % 360 + 45 + 90 * r.randrange(4) + r.choice([0, 0, -1])) % 360
        deg = k + r.uniform(0.05, 0.95)
    else:
        deg = r.randrange(360) + r.uniform(0.05, 0.95)
    th = math.radians(deg)
    return (f32(origin[0] + d * math.sin(th)), y, f32(origin[2] + d * math.cos(th))), label, deg


def _set_camera_pos(ctx, c, cam):
    c.set(ctx.g('g_gd_camera').deref() + CAM_POS, struct.pack('<3f', *cam))


def _quadrant(ctx):
    """int GetQuadrantForPosition(srVector3T<float> position)"""
    fn = ctx.fn(0x00555f30)
    gs = ctx.g('g_status')
    for i in range(ctx.n(400)):
        r = ctx.rng('quadrant', i)
        c = ctx.case('getquadrantforposition.%d' % i, fn, conv='c', ret='i')
        cam = _world_pos(r)
        facing = _party_facing(r)
        pt, label, deg = _quadrant_point(r, cam, facing)
        _set_camera_pos(ctx, c, cam)
        c.set(gs + GS_PARTY_FACING, u32(facing))
        c.arg(F32(pt[0]))
        c.arg(F32(pt[1]))
        c.arg(F32(pt[2]))
        c.note(facing=facing, deg=deg)
        _edges(c, ([label] if label else []) + _facing_edge(facing))


def _fake_monster(ctx, c, k, pos, yaw):
    """Fake W8MonsterInfo k (0/1) in S1; p3D -> fake W8Monster in S1 (navigator base +0x18:
    position at +0x100, yaw at +0xd4)."""
    s1 = ctx.scratch(1)
    info = s1 + k * 0x800
    mon = s1 + 0x1000 + k * 0x2000
    c.setp(info + MI_P3D, mon)
    c.set(mon + MON_NAV + NAV_YAW, fb(yaw))
    c.set(mon + MON_NAV + NAV_POS, struct.pack('<3f', *pos))
    return info


def _slot_facing(r):
    return r.randrange(4) if r.random() < 0.8 else r.choice(FACINGS_ODD)


def _quadrant_monster(ctx):
    gs = ctx.g('g_status')
    gs_form = gs + GS_FORMATION
    specs = [('ischaracterfacingmonster', 0x00555960, 'b'),     # (slot, info)
             ('turncharactertowardmonster', 0x00555820, 'v'),   # (slot, info)
             ('ismonsterbehindcharacter', 0x00555c60, 'b')]     # (info, slot)
    for name, addr, ret in specs:
        fn = ctx.fn(addr)
        for i in range(ctx.n(250)):
            r = ctx.rng(name, i)
            c = ctx.case('%s.%d' % (name, i), fn, conv='c', ret=ret)
            cam = _world_pos(r)
            facing = _party_facing(r)
            pt, label, deg = _quadrant_point(r, cam, facing)
            slot = r.randrange(8)
            b = _random_form(r)
            sf = _slot_facing(r)
            b[POS + slot * POS_STEP + P_FACING] = sf & 0xff
            if ret == 'v':
                _quiet_ui(ctx, c, npc=0, started=r.choice([0, 1, 1]))
            _set_camera_pos(ctx, c, cam)
            c.set(gs + GS_PARTY_FACING, u32(facing))
            c.set(gs_form, bytes(b))
            info = _fake_monster(ctx, c, 0, pt, f32(r.uniform(-7, 7)))
            if ret == 'v':
                c.cap(gs_form, FORM, 'formation')
            if name == 'ismonsterbehindcharacter':
                c.arg(info)
                c.arg(slot)
            else:
                c.arg(slot)
                c.arg(info)
            c.note(facing=facing, deg=deg, slot=slot, slot_facing=sf)
            _edges(c, ([label] if label else []) + _facing_edge(facing))


def _face_combat_target(ctx):
    """void FaceCharacterTowardCombatTarget(int slot, W8CombatSlot* target)"""
    fn = ctx.fn(0x00555560)
    gs = ctx.g('g_status')
    gs_form = gs + GS_FORMATION
    t = ctx.scratch(3)
    for i in range(ctx.n(300)):
        r = ctx.rng('facetarget', i)
        c = ctx.case('facecharactertowardcombattarget.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        x = r.random()
        if x < 0.3:
            kind = 1
        elif x < 0.45:
            kind = 9
        elif x < 0.8:
            kind = 6
        else:
            kind = r.choice([0, 2, 4, 5, 7, 8, 10, -1, 0x7fffffff, -0x80000000])
        b = _random_form(r)
        edges = []
        ichar = r.randrange(8)
        if kind in (1, 9):
            if r.random() < 0.04:
                ichar = -1
                edges.append('bad_index')
            else:
                for s in (slot, ichar):
                    if r.random() < 0.5:
                        b[POS + s * POS_STEP + P_ROW] = r.choice(QUADS) & 0xff
        sf = _slot_facing(r)
        b[POS + slot * POS_STEP + P_FACING] = sf & 0xff
        cam = _world_pos(r)
        facing = _party_facing(r)
        pt, label, deg = _quadrant_point(r, cam, facing)
        if kind == 6 and label:
            edges.append(label)
        if kind == 6:
            edges += _facing_edge(facing)
        _quiet_ui(ctx, c, npc=0, started=r.choice([0, 1, 1]))
        _set_camera_pos(ctx, c, cam)
        c.set(gs + GS_PARTY_FACING, u32(facing))
        c.set(gs_form, bytes(b))
        c.set(t, struct.pack('<iiiI3f', kind, ichar, r.randrange(-1, 2000), r.getrandbits(32), *pt))
        c.cap(gs_form, FORM, 'formation')
        c.arg(slot)
        c.arg(t)
        c.note(kind=kind, slot=slot, ichar=ichar, slot_quadrant=_row_of(b, slot),
               target_quadrant=_row_of(b, ichar) if ichar >= 0 else None, slot_facing=sf,
               party_facing=facing, deg=deg if kind == 6 else None)
        _edges(c, edges)


# --------------------------------------------------------------------------------------
# camera: GetCameraYawDegrees = (int)(m_yaw * 57.295784f), then unsigned % 360
def _camera_params(r, guard):
    """m_yaw and the degrees GetCameraYawDegrees truncates it to (None on a truncation
    boundary, where the path is not predictable)."""
    p = {'guard': guard}
    x = r.random()
    label = None
    if x < 0.62:
        deg = r.randrange(360) + r.uniform(0.05, 0.95)
        yaw = f32(deg / YAW_SCALE)
        trunc = int(deg)
    elif x < 0.74:
        if r.random() < 0.5:
            deg = r.randrange(360, 720) + r.uniform(0.05, 0.95)
        else:
            deg = -(r.randrange(0, 360) + r.uniform(0.05, 0.95))
        yaw = f32(deg / YAW_SCALE)
        trunc = int(deg)
        label = 'yaw_out_of_turn'
    elif x < 0.88:
        k = r.randrange(360)
        yaw = _ulps(k / YAW_SCALE, r.randint(-2, 2))
        trunc = None
        label = 'yaw_boundary'
    else:
        yaw = r.choice([0.0, -0.0, 1e-30, -1e-30, f32(TWO_PI), 6.2831852, f32(-TWO_PI)])
        trunc = 0 if abs(yaw) < 1.0 else None
        label = None if trunc is not None else 'yaw_boundary'
    p['yaw'] = f32(yaw)
    p['trunc'] = trunc
    p['mod'] = ((trunc & 0xffffffff) % 360) if trunc is not None else None
    p['label'] = label
    if guard:
        p['flags'] = CAM_MANUAL_INPUT | r.choice([0, 0x20, 0x80])
    else:
        p['flags'] = r.choice([0, 0, 0, 0x20, 0x40, 0x80])
    p['pitch'] = 0.0 if r.random() < 0.5 else f32(r.uniform(-0.6, 0.6))
    # the rest of the camera (matrices, direction, transition state, position, targets,
    # velocities, distances, duration) gets deterministic values too: the setters write
    # many of these fields and the capture compares changed bytes against the old ones
    blob = bytearray(CAM_TIMER)
    struct.pack_into('<Iff', blob, 0, p['flags'], p['yaw'], p['pitch'])
    for o in range(0x0c, 0x84, 4):
        struct.pack_into('<f', blob, o, r.uniform(-1.0, 1.0))
    struct.pack_into('<f', blob, 0x84, r.uniform(0.0, 0.1))
    blob[0x88] = r.choice([0, 1])
    blob[0x89] = r.choice([0, 0, 1])
    struct.pack_into('<3f', blob, CAM_POS, *_world_pos(r))
    for o in range(0x98, CAM_TIMER, 4):
        struct.pack_into('<f', blob, o, r.uniform(-7.0, 7.0))
    p['blob'] = bytes(blob)
    return p


CAM_SPEED = 0.31415927410125732    # g_camera_transition_speed = half period / 10


def _camera_apply(ctx, c, p):
    c.set(ctx.g('g_gd_camera').deref(), p['blob'])
    c.set(ctx.g('g_camera_transition_speed'), fb(CAM_SPEED))
    # dialogue mode skips the manual-input timer poll; the guard returns before it
    c.set(ctx.g('gXStatus') + GX_NPC_DIALOGUE, u8(0 if p['guard'] else 1))
    c.set(ctx.g('g_level_block').deref() + LB_COMPASS_SPRITE, u32(0))


def _camera_caps(ctx, c):
    c.cap(ctx.g('g_gd_camera').deref(), CAM_SIZE, 'camera', ignore=[CAM_TIMER], floats=CAM_FLOATS)
    c.cap(ctx.g('g_status') + GS_PARTY_FACING, 8, 'party_facing_heading')


def _camera_note(c, p, edges=()):
    c.note(yaw=p['yaw'], yaw_deg=p['trunc'], guard=int(p['guard']), cam_flags=p['flags'])
    _edges(c, list(edges) + ([p['label']] if p['label'] else []))


def _turn_party_to(ctx):
    """unsigned int TurnPartyTo(unsigned int degrees). eax is defined only when degrees ==
    party_heading (old heading) or the camera already looks that way (camera yaw / 360);
    after SetCameraYawDegrees retail leaves whatever the callee left - void there."""
    fn = ctx.fn(0x005553c0)
    gs = ctx.g('g_status')
    for i in range(ctx.n(250)):
        r = ctx.rng('turnpartyto', i)
        p = _camera_params(r, r.random() < 0.2)
        heading = r.randrange(360) if r.random() < 0.85 else r.choice([360, 1000, 0xffffffff])
        x = r.random()
        if x < 0.25:
            degrees = heading
        elif x < 0.45 and p['mod'] is not None:
            degrees = p['mod']
        elif p['guard']:
            degrees = r.choice([r.randrange(720), 0xffffffff, 0x80000000, 0x7fffffff, 360000, 1000000])
        else:
            degrees = r.randrange(720)
        ret = 'i' if degrees == heading or (p['mod'] is not None and p['mod'] == degrees) else 'v'
        c = ctx.case('turnpartyto.%d' % i, fn, conv='c', ret=ret)
        _camera_apply(ctx, c, p)
        c.set(gs + GS_PARTY_FACING, struct.pack('<iI', r.randrange(360), heading))
        _camera_caps(ctx, c)
        c.arg(degrees)
        c.note(degrees=degrees, heading=heading)
        _camera_note(c, p)


def _turn_party_immediate(ctx):
    """void TurnPartyToImmediate(unsigned int degrees, char snap)"""
    fn = ctx.fn(0x00555420)
    gs = ctx.g('g_status')
    for i in range(ctx.n(250)):
        r = ctx.rng('turnimmediate', i)
        p = _camera_params(r, r.random() < 0.2)
        heading = r.randrange(360) if r.random() < 0.85 else r.choice([360, 1000, 0xffffffff])
        x = r.random()
        if x < 0.2:
            degrees = heading
        elif x < 0.4 and p['mod'] is not None:
            degrees = p['mod']
        elif p['guard']:
            degrees = r.choice([r.randrange(720), 0xffffffff, 0x80000000, 360000])
        else:
            degrees = r.randrange(720)
        snap = _flag(r, 0.5, 0.15)
        c = ctx.case('turnpartytoimmediate.%d' % i, fn, conv='c', ret='v')
        _camera_apply(ctx, c, p)
        c.set(gs + GS_PARTY_FACING, struct.pack('<iI', r.randrange(360), heading))
        _camera_caps(ctx, c)
        c.arg(degrees)
        c.arg(snap)
        c.note(degrees=degrees, heading=heading, snap=snap)
        _camera_note(c, p, ['bool_byte'] if snap not in (0, 1) else [])


def _face_camera_selection(ctx):
    """void FaceCameraToSelection(int party_slot)"""
    fn = ctx.fn(0x005554a0)
    gs = ctx.g('g_status')
    st = ctx.g('g_settings')
    for i in range(ctx.n(250)):
        r = ctx.rng('facecamera', i)
        p = _camera_params(r, r.random() < 0.25)
        slot = r.randrange(8)
        mode = 0 if r.random() < 0.75 else r.choice([1, 2, 0x100, 0xffffffff])
        sel = slot if r.random() < 0.75 else r.choice([-1] + [s for s in range(8) if s != slot])
        if r.random() < 0.8:
            fbyte = r.randrange(4)
        else:
            fbyte = r.choice([4, 0xff, 0x80, 0x7f]) if p['guard'] else 4
        pf = _party_facing(r) if p['guard'] else r.randrange(360)
        target = (pf + fbyte * 90) & 0xffffffff
        heading = target if r.random() < 0.2 else r.randrange(360)
        style = r.choice([0, 1]) if r.random() < 0.85 else r.choice([2, 0x100, 0x101, 0xff])
        c = ctx.case('facecameratoselection.%d' % i, fn, conv='c', ret='v')
        _camera_apply(ctx, c, p)
        c.set(st + ST_CAM_ROT_MODE, u32(mode))
        c.set(st + ST_CAM_ROT_STYLE, u32(style))
        c.set(gs + GS_SELECTED, u32(sel))
        c.set(gs + GS_FORMATION + POS + slot * POS_STEP + P_FACING, u8(fbyte))
        c.set(gs + GS_PARTY_FACING, struct.pack('<iI', pf, heading))
        _camera_caps(ctx, c)
        c.arg(slot)
        c.note(slot=slot, mode=mode, selected=sel, facing_byte=fbyte, party_facing=pf,
               heading=heading, style=style)
        _camera_note(c, p)


def _sync_facing(ctx):
    """void SyncPartyFacingFromCamera(void)"""
    fn = ctx.fn(0x005552f0)
    gs = ctx.g('g_status')
    for i in range(ctx.n(250)):
        r = ctx.rng('syncfacing', i)
        p = _camera_params(r, r.random() < 0.2)
        combat = r.choice([0, 1])
        preserve = _bool_byte(r, 0.5, 0.06)
        stopped = r.random() < 0.3
        lvl = (r.getrandbits(8) & ~0x40) | (0x40 if stopped else 0)
        if p['mod'] is not None and r.random() < 0.25:
            heading = p['mod']
        else:
            heading = r.randrange(360) if r.random() < 0.9 else r.choice([360, 0xffffffff])
        c = ctx.case('syncpartyfacingfromcamera.%d' % i, fn, conv='c', ret='v')
        _camera_apply(ctx, c, p)
        c.set(ctx.g('gXStatus') + GX_COMBAT_MODE, u8(combat))
        c.set(ctx.g('g_combat_preserve_party_facing'), u8(preserve))
        c.set(ctx.g('g_level_data').deref(), u8(lvl))
        c.set(gs + GS_PARTY_FACING, struct.pack('<iI', r.randrange(360), heading))
        _camera_caps(ctx, c)
        c.note(combat=combat, preserve=preserve, stopped=int(stopped), heading=heading)
        _camera_note(c, p, ['bool_byte'] if preserve not in (0, 1) else [])


# --------------------------------------------------------------------------------------
# monster facing: bearing = NormalizeAngle(GetHeadingAngle(source, target))
def _bearing(src, dst):
    dx = dst[0] - src[0]
    dz = dst[2] - src[2]
    if dz == 0.0:
        h = math.pi / 2 if dx > 0 else -math.pi / 2
    else:
        h = math.atan2(dx, dz)
    if h < 0:
        h += TWO_PI
    return h


def _near_point(r, origin):
    x = r.random()
    d = r.choice([r.uniform(30, 3000), r.uniform(3000, 30000)])
    y = f32(origin[1] + r.uniform(-200, 200))
    if x < 0.05:
        return (f32(origin[0] + r.choice([d, -d])), y, origin[2]), 'dz0'
    if x < 0.07:
        return tuple(origin), 'same_point'
    th = r.uniform(0, TWO_PI)
    label = None
    if r.random() < 0.1:
        th = r.choice([0.0, math.pi / 2, math.pi, 1.5 * math.pi]) + r.choice([0.0, 1e-7, -1e-7])
        label = 'axis'
    return (f32(origin[0] + d * math.sin(th)), y, f32(origin[2] + d * math.cos(th))), label


def _look_yaw(r, bearing, tol, wild):
    """Facing yaw around the tolerance boundary(ies) of `bearing`. wild: NaN/inf/huge too
    (only where the yaw is never passed to NormalizeAngle, which loops on them)."""
    x = r.random()
    if x < 0.3:
        return f32(bearing + r.uniform(-2 * tol, 2 * tol)), None
    if x < 0.52:
        off = tol if r.random() < 0.6 or tol < 1.0 else TWO_PI - tol
        return _ulps(bearing + r.choice([-1, 1]) * off, r.randint(-6, 6)), 'tol_boundary'
    if x < 0.64:
        return f32(bearing + r.choice([-1, 1]) * (TWO_PI + r.uniform(-2 * tol, 2 * tol))), None
    if x < 0.9:
        return f32(r.uniform(-7.0, 13.0)), None
    if wild:
        return r.choice([float('nan'), float('inf'), float('-inf'), 1e6, -1e6, 0.0, -0.0,
                         3.0e38]), 'wild_yaw'
    return f32(r.choice([0.0, -0.0, 1000.0, -1000.0, r.uniform(-1e4, 1e4), 1e6])), None


def _party_pos(ctx, c, pos):
    c.set(ctx.g('g_startup_world').deref() + NAV_POS, struct.pack('<3f', *pos))


def _looking_at(ctx):
    # bool IsPartyLookingAt(W8MonsterInfo*, srVector3T<float> point)
    fn = ctx.fn(0x00555ba0)
    for i in range(ctx.n(300)):
        r = ctx.rng('lookingat', i)
        c = ctx.case('ispartylookingat.%d' % i, fn, conv='c', ret='b')
        m = _world_pos(r)
        pt, plabel = _near_point(r, m)
        yaw, ylabel = _look_yaw(r, _bearing(m, pt), TOL_LOOK, True)
        info = _fake_monster(ctx, c, 0, m, yaw)
        c.arg(info)
        c.arg(F32(pt[0]))
        c.arg(F32(pt[1]))
        c.arg(F32(pt[2]))
        c.note(bearing=_bearing(m, pt), yaw=repr(yaw))
        _edges(c, [e for e in (plabel, ylabel) if e])
    # int IsMonsterFacingParty(W8MonsterInfo*)
    fn = ctx.fn(0x00555a60)
    for i in range(ctx.n(200)):
        r = ctx.rng('facingparty', i)
        c = ctx.case('ismonsterfacingparty.%d' % i, fn, conv='c', ret='i')
        m = _world_pos(r)
        party, plabel = _near_point(r, m)
        yaw, ylabel = _look_yaw(r, _bearing(m, party), TOL_LOOK, True)
        info = _fake_monster(ctx, c, 0, m, yaw)
        _party_pos(ctx, c, party)
        c.arg(info)
        c.note(bearing=_bearing(m, party), yaw=repr(yaw))
        _edges(c, [e for e in (plabel, ylabel) if e])
    # int IsMonsterFacingMonster(W8MonsterInfo* first, W8MonsterInfo* second)
    fn = ctx.fn(0x00555b00)
    for i in range(ctx.n(200)):
        r = ctx.rng('facingmonster', i)
        c = ctx.case('ismonsterfacingmonster.%d' % i, fn, conv='c', ret='i')
        m1 = _world_pos(r)
        m2, plabel = _near_point(r, m1)
        yaw, ylabel = _look_yaw(r, _bearing(m1, m2), TOL_LOOK, True)
        first = _fake_monster(ctx, c, 0, m1, yaw)
        second = _fake_monster(ctx, c, 1, m2, f32(r.uniform(-7, 7)))
        c.arg(first)
        c.arg(second)
        c.note(bearing=_bearing(m1, m2), yaw=repr(yaw))
        _edges(c, [e for e in (plabel, ylabel) if e])


def _looking_away(ctx):
    # bool IsPartyLookingAwayFrom(int, W8MonsterInfo*): ShortestAngleDistance >= double tol
    fn = ctx.fn(0x00555d60)
    for i in range(ctx.n(250)):
        r = ctx.rng('lookingaway', i)
        c = ctx.case('ispartylookingawayfrom.%d' % i, fn, conv='c', ret='b')
        m = _world_pos(r)
        party, plabel = _near_point(r, m)
        yaw, ylabel = _look_yaw(r, _bearing(m, party), TOL_AWAY, False)
        info = _fake_monster(ctx, c, 0, m, yaw)
        _party_pos(ctx, c, party)
        c.arg(r.randrange(-1, 8))
        c.arg(info)
        c.note(bearing=_bearing(m, party), yaw=repr(yaw))
        _edges(c, [e for e in (plabel, ylabel) if e])
    # int IsMonsterLookingAwayFrom(W8MonsterInfo* first, W8MonsterInfo* second)
    fn = ctx.fn(0x00555de0)
    for i in range(ctx.n(300)):
        r = ctx.rng('monsterlookingaway', i)
        c = ctx.case('ismonsterlookingawayfrom.%d' % i, fn, conv='c', ret='i')
        m1 = _world_pos(r)
        m2, plabel = _near_point(r, m1)
        yaw, ylabel = _look_yaw(r, _bearing(m2, m1), TOL_AWAY, False)
        first = _fake_monster(ctx, c, 0, m1, f32(r.uniform(-7, 7)))
        second = _fake_monster(ctx, c, 1, m2, yaw)
        c.arg(first)
        c.arg(second)
        c.note(bearing=_bearing(m2, m1), yaw=repr(yaw))
        _edges(c, [e for e in (plabel, ylabel) if e])


# --------------------------------------------------------------------------------------
def _casting_block(ctx):
    """bool MonsterSpecialAttackHonorsCastingBlock(int kind): 5-7, 0x19, 0x1a, 0x1c, 0x1d."""
    fn = ctx.fn(0x00556050)
    kinds = list(range(-16, 100)) + [0x7f, 0x80, 0xff, 0x100, 0x105, 0x119, 0x11d, 0x10005,
                                     0x80000005, 0xffffff05, 0xffffff19, 0x7fffffff,
                                     -0x80000000, -0x100, 0x1000001d, 0xfffffffb, 0x7fffff1c]
    for i, k in enumerate(kinds[:ctx.n(len(kinds))]):
        c = ctx.case('honorscastingblock.%d' % i, fn, conv='c', ret='b')
        c.arg(k)
        c.note(kind=k)
