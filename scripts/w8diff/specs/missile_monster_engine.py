"""Engine Code Missile.cpp (whole file) and Monster.cpp lines 1-1600: the self-contained
math/decision helpers. Every structure they read (AI record, W8Missile, W8MissileRep,
W8AnimObj, W8AniMesh, W8Monster, W8MonsterRep, growable vectors, strings) is built in
scratch memory, wired together with setp; the only live-game state touched is
g_world->octree (forced to null so no prop trigger can fire), g_world->missiles,
g_missile_iterator and the GDCamera yaw/pitch/position, all set explicitly per case.

Tested (retail address, name, cases):
  0x004a50a0 AdvanceMissileAI                  320  record S0, out S0+0x100, W8Missile S1,
                                                    W8MissileRep S2; g_world->octree = 0.
                                                    steps 0 (out = rep location), 1..250,
                                                    unsigned edges up to 0xffffffff
                                                    (unsigned->float); gravity byte 0/1/2/
                                                    0x80/0xff; dir.y = 0 and zero velocity
                                                    (no re-aim); 8 cases with rep location
                                                    exactly on the predicted point (zero
                                                    distance, no re-aim); 16 cases
                                                    note(edge='gravity_cancel'): fall_speed ~=
                                                    steps*0.0098, where retail multiplies by
                                                    the double 0.0098 and the port source by
                                                    (float)0.0098 - a real precision
                                                    difference shows up only there.
  0x004a57b0 GetCharacterProjectilePosition    260  GDCamera yaw/pitch/position set; index
                                                    0..7 + unsigned edges (0x80000000,
                                                    0xffffffff); yaw = g_monster_rotation_offset
                                                    and pitch = 0 (rotation skipped)
  0x004a2760 NextMissile                       180  g_world->missiles = scratch vector (S0,
                                                    data S0+0x400, elements S1) or null;
                                                    iterator -4..count+3, 0x80000000 and
                                                    -0x40000000 (address wrap to data[0]),
                                                    count 0..8/-1/0x80000000; restart byte
                                                    edges 2/0xff/0x100/0xff00 (retail tests
                                                    only the low byte)
  0x004a5790 W8Missile::BlocksEndingCombat     100  flight_done bytes 0/1/2/0x80/0xff,
                                                    current_cycle 0/1/2/-1/0x81/0x7f
  0x004a4590 W8Missile::GetTotalAnimationCount  48  emitters null / scratch pointer / raw
                                                    non-null garbage
  0x004a42b0 W8Missile::IsCycleSupported       160  signed char cycle -128..127 over a random
                                                    256-dword window around emitters[]
                                                    (cycle >= 2 asserts at line 0x4bf, still
                                                    indexes); upper arg bits garbage
  0x004a4570 W8Missile::GetCurrentAnimation     60  signed current_cycle; the unsigned
                                                    reading (cycle & 0xff) points elsewhere
  0x004a45c0 W8Missile::GetCurrentAnimationScale 60  same, float playback_scale incl. -0.0,
                                                    inf, denormal, NaN
  0x004a45f0 W8Missile::GetCurrentAniMesh       80  signed current_cycle and m_bLOD
                                                    (-128..127; the unsigned index points at a
                                                    different mesh), null entry
  0x004a2710 W8MissileRep::ApplyEmitterSetting 160  emitter -128..127 (+ upper garbage),
                                                    path_lists -> frame_count, else
                                                    AniMeshValue(entries[(signed)m_bLOD]):
                                                    null mesh (asserts 0x2be, returns 0xff),
                                                    mesh flag 0x02 always set (no
                                                    LoadAniMesh); entries[-1]/[-5] overlap
                                                    frame_count/path_lists, so no pointer is
                                                    stored there when that field is read
  0x004a5410 W8Missile::SetEffectDefinition    120  all 36 MissileTables rows (radius) x3 +
                                                    random rows; random 0x30-byte definition
  0x004c2e00 ChooseDifferentMonsterDirection   120  previous 0..3 (seeded Random(6) re-rolls),
                                                    upper 16 bits garbage (retail masks)
  0x004c2010 ParseMonsterCycleName             263  all 27 names + FLY/EXPLODE fallbacks,
                                                    digit suffixes 0..65536, atoi overflow
                                                    (2147483648, 4294967297, 20 digits ->
                                                    retail msvcrt atoi vs port CRT), non-digit
                                                    suffixes, prefix extensions, case
                                                    mismatch, unmatched MLS words, NULL
                                                    subcycle. note(edge='oob_read') (10 cases):
                                                    retail reads past the table
                                                    (g_cycle_names[-1].prefix_length = 12,
                                                    atoi offset g_cycle_names[27] = 73) for an
                                                    unmatched name longer than 12 with a digit
                                                    at [12], or FLY<2 chars><digit>; the buffer
                                                    holds digits at +73 so the retail result is
                                                    deterministic; the port's result depends on
                                                    its own data layout
  0x004c1d20 W8Monster::RandomizeAppearanceAndMotion 260  W8Monster S1, W8MonsterRep S2,
                                                    animations[1] pointers S3 -> W8AnimObj S4,
                                                    animation_scales[1] S3+0x800; seeded
                                                    Random; left_handed signed edges, scale
                                                    range (min > max asserts 0x2f5),
                                                    animation count low byte read as signed
                                                    char (0x80, 0xff, 0x100, 0x101, 0x103:
                                                    0x110 valid pointers so a port that uses
                                                    the whole count cannot crash), scale
                                                    vector shorter/longer; 17 cases
                                                    note(edge='nan'): VC6 '!=' and '<' on NaN
                                                    (retail treats a NaN min/max scale as zero
                                                    and a NaN monster scale as < 1); 14 cases
                                                    note(edge='count_byte')
  Total 2191 cases.
  Labelled edges (a difference only there is an edge-semantics question, not a mainline
  bug): gravity_cancel 16, oob_read 10, nan 17, count_byte 14, assert_cycle 30 (cycle >= 2,
  expected assert line 0x4bf in both), assert_null_mesh 10 (expected assert line 0x2be).

Skipped (Missile.cpp):
  0x004a53a0 CopyAIMissile          - returns a malloc block whose padding and +0x0c missile
                                      field are left uninitialised; ret='p' compares all 32
                                      bytes and cannot ignore offsets
  0x004a4cf0 UpdateMissileAI        - getMsTime half-tick clock, CheckNavigatorCollision
                                      against live monsters, virtual calls via the missile
                                      vtable (EnterImpactCycle), detonation/absorb side effects
  0x004a5600 LoadMissileDatabase    - file I/O, reallocates the global table
  0x004a5760 ReleaseMissileDatabase - frees the global table
  0x004a27c0 UpdateWorldMissiles    - updates/destroys world objects
  0x004a2d30 FireMissile            - creates a world missile (CreateMissile)
  0x004a5450 AllocateMissile        - not in Wiz8Runtime.map (inlined); world object creation
  0x004a3550 LoadMissileCycle       - file I/O, object creation, registry
  0x004a28d0 CreateMissile          - world object creation, octree trace, timer
  0x004a2db0 W8MissileRep::W8MissileRep(copy) - object creation (clones animations/lights)
  0x004a5d40 W8MissileRep::Clone    - object creation
  0x004a3300 W8MissileRep::ReadCycleData - file I/O
  0x004a3c10 / 0x004a3e50 W8Missile constructors - object creation (and the resolver maps
                                      both to ??0W8Missile@@QAE@XZ)
  0x004a4640 W8Missile::GetAnimationState - not in the port map (inlined); mode 6 is covered
                                      through BlocksEndingCombat
  0x004a3fc0 W8Missile::~W8Missile, 0x004a3230 W8MissileRep::~W8MissileRep - not in the
                                      port map; object deletion
  0x004a4050 W8Missile::StartIfHostActive - PathAI/animation tick (timers), detonation
  0x004a4180 W8Missile::DestroyMissile, 0x004a4210 DestroyAllMissiles - object deletion
  0x004a45e0 W8Missile::GetRepresentation - pure getter of m_pRep, cannot differ
  0x004a4100 W8Missile::UpdateRepresentation - rendering
  0x004a4110 W8Missile::GetNumSubCycles - calls GetCurrentAnimation through the vtable; the
                                      API cannot place a W8Missile vtable pointer (see needs_api)
  0x004a4300 W8Missile::SetCycle    - light attach/detach, particle events, timer read
  0x004a4140 W8Missile::AdvanceAnimationFrame - virtual GetNumSubCycles + timer-driven frame
  0x004a49e0 W8Missile::DetonateMissileSpell - casts a spell (CastSpellFromSource)
  0x004a4ac0 W8Missile::AnnounceCollisionTarget - notice box UI
  0x004a4c20 W8Missile::EnterImpactCycle - virtual IsCycleSupported through the vtable; else
                                      detonation / AbsorbMissileDamage
  0x004a4720 W8Missile::OnCollision - combat hit resolution, notices, Random target, virtual
Skipped (Monster.cpp 1-1600):
  0x004c0300 ReadOrCloneMonsterCycles - MLS file I/O, object creation
  0x004bea20 / 0x004bebd0 W8MonsterRep constructors - object creation (the resolver maps
                                      the default ctor to the copy ctor's port address)
  0x004bf520 W8MonsterRep::ReadCycleData - file I/O
  0x004bee50 W8MonsterRep::~W8MonsterRep - object deletion
  0x004bf0f0 W8MonsterRep::CopyCycle - clones animations and world lights
  0x004ca9e0 W8MonsterRep::Clone    - object creation
  0x004bfb00 / 0x004bfe00 W8Monster constructors - object creation; ambiguous in the map
  0x004c0170 W8Monster::~W8Monster  - object deletion
  0x004ca840 W8Monster::SetPosition - moves a world object (virtual representation calls)
  0x004c2100 W8Monster::Update      - per-frame world update: camera distance, sun line of
                                      sight, timers, scripts, GetTickCount
"""
import math
import struct

# --- W8AIMissile (0x20) ---
AI_SIZE = 0x20
AI_MISSILE = 0x0c
# --- W8Missile (0x328) ---
M_SIZE = 0x328
M_TARGET_YAW = 0xf0      # Navigator (+0x18) movement (+0xc0) target_yaw
M_TARGET_PITCH = 0xfc
M_VELOCITY = 0x10c       # movement.velocity, movement.position follows at +0x118
M_TABLE_INDEX = 0x1d8
M_REP = 0x1dc            # W8MissileRep* (GrCycle tail slot)
M_FLIGHT_DONE = 0x1e0
M_DEFINITION = 0x1fc     # W8SpellEffectDefinition (0x30), radius at +0
DEF_SIZE = 0x30
# --- W8MissileRep (0x108) ---
R_SIZE = 0x108
R_LOCATION = 0x04
R_ROTATION = 0x28
R_LOD = 0x98             # signed char m_bLOD
R_CURRENT_CYCLE = 0xa4   # signed char
R_EMITTERS = 0xd8        # W8AnimObj* emitters[2]
# --- W8AnimObj (0x4c) ---
A_PATH_LISTS = 0x05
A_PLAYBACK = 0x08
A_FRAME_COUNT = 0x16
A_ENTRIES = 0x18
# --- W8World ---
W_OCTREE = 0x50
W_MISSILES = 0xb8
# --- W8GrowableVector: vptr, count, capacity, data ---
V_COUNT = 0x04
V_DATA = 0x0c
# --- GDCamera ---
CAM_YAW = 0x04           # m_yaw, m_pitch follows
CAM_POS = 0x8c
# --- W8Monster (0x348) ---
MO_SIZE = 0x348
MO_VBASE = 0x154         # movement.vertical_base, _amplitude, _phase
MO_HEIGHT = 0x190        # movement.height_offset, secondary_height_offset, vertical_offset
MO_VOFFSET = 0x198
MO_MIRROR = 0x1be
MO_SCALE = 0x1cc
MO_REP = 0x1d8
MO_HOVER_MIN = 0x21c     # hover min/max, bob min/max
# --- W8MonsterRep (0x628) ---
MR_SIZE = 0x628
MR_INSTANCE_SCALE = 0x5c
MR_APPLY_INSTANCE = 0x61
MR_CUR_SUB = 0xa5
MR_ANIM1 = 0xbc          # animations[1]
MR_SCALES1 = 0x26c       # animation_scales[1]
MR_SCALE = 0x5f0         # scale, minimum_scale, maximum_scale
MR_RANDOM_IDLE = 0x600
MR_IDLE_PB = 0x604       # idle_playback_scale, random_idle_fps_min, _max
MR_LEFT = 0x610

MISSILE_ROWS = 36        # MissileTables.dbs rows
ROT_OFFSET = struct.unpack('<f', bytes.fromhex('da0f4940'))[0]   # g_monster_rotation_offset
TWO_PI = 2.0 * math.pi
NAN = float('nan')
INF = float('inf')


def u32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def u8(v):
    return bytes([int(v) & 0xff])


def f32(*xs):
    return b''.join(struct.pack('<f', float(x)) for x in xs)


def rf(x):
    """Round a Python float to float32."""
    return struct.unpack('<f', struct.pack('<f', float(x)))[0]


def _rand_bytes(r, n):
    return bytes(r.getrandbits(8) for _ in range(n))


def _rand_floats(r, n, lo=-4.0, hi=4.0):
    return f32(*[r.uniform(lo, hi) for _ in range(n)])


def _schar(v):
    v &= 0xff
    return v - 256 if v >= 128 else v


def cases(ctx):
    _advance_missile_ai(ctx)
    _projectile_position(ctx)
    _next_missile(ctx)
    _blocks_ending_combat(ctx)
    _total_animation_count(ctx)
    _is_cycle_supported(ctx)
    _current_animation(ctx)
    _current_animation_scale(ctx)
    _current_animesh(ctx)
    _apply_emitter_setting(ctx)
    _set_effect_definition(ctx)
    _choose_direction(ctx)
    _parse_cycle_name(ctx)
    _randomize_appearance(ctx)


# --------------------------------------------------------------------------------------
def _direction(r):
    x = r.random()
    if x < 0.12:
        return (0.0, 0.0, 0.0) if r.random() < 0.3 else (rf(math.sin(r.uniform(0, TWO_PI))), 0.0,
                                                          rf(math.cos(r.uniform(0, TWO_PI))))
    h = r.uniform(0, TWO_PI)
    p = r.uniform(-0.7, 0.7) if x < 0.9 else r.choice([-1.4, 1.4, 1e-4, -1e-4, math.pi / 2])
    d = (math.sin(h) * math.cos(p), math.sin(-p), math.cos(h) * math.cos(p))
    if r.random() < 0.08:   # not normalised
        k = r.choice([0.5, 2.0, 10.0])
        d = tuple(v * k for v in d)
    return tuple(rf(v) for v in d)


def _advance_missile_ai(ctx):
    """float AdvanceMissileAI(W8AIMissile*, srVector3T<float>* out, unsigned int steps)"""
    fn = ctx.fn(0x004a50a0)
    world = ctx.g('g_world').deref()
    rec = ctx.scratch(0)
    out = ctx.scratch(0) + 0x100
    mis = ctx.scratch(1)
    rep = ctx.scratch(2)
    exact_dirs = [(0.0, 0.5, 0.5), (0.5, -0.25, 0.0), (0.0, 1.0, 0.0), (-0.5, 0.5, 0.25),
                  (0.25, -0.5, -0.75)]
    for i in range(ctx.n(320)):
        r = ctx.rng('advanceai', i)
        c = ctx.case('advancemissileai.%d' % i, fn, conv='c', ret='f')
        c.set(world + W_OCTREE, u32(0))     # no prop trace: a hit would run a prop trigger
        kind = 'zero' if i < 12 else 'exact' if i < 20 else 'cancel' if i < 36 else 'normal'
        # steps
        if kind == 'zero':
            steps = 0
        elif kind == 'exact':
            steps = r.choice([1, 2, 4, 8])
        elif kind == 'cancel':
            steps = r.choice([1, 10, 50, 100, 125, 200, 250, r.randrange(1, 251)])
        else:
            x = r.random()
            if x < 0.62:
                steps = r.randrange(1, 251)
            elif x < 0.82:
                steps = r.choice([1, 2, 3, 0xf9, 0xfa, 0xfb, 0x100, 1000])
            else:
                steps = r.choice([0xffff, 0x10000, 0xffffff, 0x1000001, 0x7fffffff, 0x80000000,
                                  0x80000001, 0xfffffffe, 0xffffffff])
        # speed per step
        x = r.random()
        if kind == 'exact':
            speed = 2.0
        elif x < 0.6:
            speed = r.uniform(1.0, 60.0)
        elif x < 0.8:
            speed = r.uniform(0.01, 1.0)
        elif x < 0.95:
            speed = r.uniform(60.0, 8000.0)
        else:
            speed = r.choice([0.0, -5.0, 1e-6, 0.001, 7.5])
        speed = rf(speed)
        # velocity / position
        if kind == 'exact':
            d = r.choice(exact_dirs)
            pos = (float(r.randrange(-20000, 20000)), float(r.randrange(-2000, 2000)),
                   float(r.randrange(-20000, 20000)))
        else:
            d = _direction(r)
            pos = (rf(r.uniform(-2e5, 2e5)), rf(r.uniform(-3000, 3000)), rf(r.uniform(-2e5, 2e5)))
        # gravity
        x = r.random()
        if kind in ('exact', 'cancel'):
            grav = 1
        elif x < 0.4:
            grav = 0
        elif x < 0.95:
            grav = 1
        else:
            grav = r.choice([2, 0x80, 0xff])
        # fall speed
        if kind == 'cancel':
            fall = rf(rf(steps) * 0.0098)
        else:
            fall = rf(d[1] * speed) if r.random() < 0.7 else rf(r.uniform(-50, 50))
        # representation location
        x = r.random()
        if kind == 'exact':
            loc = tuple(pos[k] + d[k] * steps * speed for k in range(3))
            where = 'on_target'
        elif x < 0.6:
            loc, where = pos, 'same'
        elif x < 0.85:
            k = r.uniform(0.5, 3.0)
            loc, where = tuple(rf(pos[j] - d[j] * speed * k) for j in range(3)), 'lag'
        else:
            loc, where = tuple(rf(pos[j] + r.uniform(-1000, 1000)) for j in range(3)), 'offset'
        elapsed = rf(r.uniform(0, 5000))
        limit = rf(r.choice([-1.0, -1.0, 1.0, r.uniform(1, 20000)]))
        record = (u8(3) + u8(grav) + _rand_bytes(r, 2) + f32(speed, fall) + u32(0) +
                  u32(r.getrandbits(32)) + f32(elapsed, limit) + u8(r.getrandbits(1)) + bytes(3))
        c.set(rec, record)
        c.setp(rec + AI_MISSILE, mis)
        c.setp(mis + M_REP, rep)
        c.set(mis + M_VELOCITY, f32(*d) + f32(*pos))
        c.set(mis + M_TARGET_YAW, f32(r.uniform(-4, 4)))
        c.set(mis + M_TARGET_PITCH, f32(r.uniform(-4, 4)))
        c.set(rep + R_LOCATION, f32(*loc))
        c.set(rep + R_ROTATION, _rand_floats(r, 9, -1.0, 1.0))
        c.set(out, _rand_floats(r, 3, -100.0, 100.0))
        c.arg(rec)
        c.arg(out)
        c.arg(steps)
        c.cap(rec, AI_SIZE, 'record', ignore=[AI_MISSILE], floats=[4, 8, 0x14, 0x18])
        c.cap(out, 12, 'out', floats=[0, 4, 8])
        c.cap(mis, M_SIZE, 'missile', ignore=[M_REP], floats=[M_TARGET_YAW, M_TARGET_PITCH])
        c.cap(rep, R_SIZE, 'rep', floats=[R_LOCATION + 4 * k for k in range(3)] +
              [R_ROTATION + 4 * k for k in range(9)])
        c.note(steps=steps, speed=speed, gravity=grav, dir='%g,%g,%g' % d, rep=where,
               fall=fall)
        if kind == 'cancel':
            c.note(edge='gravity_cancel')


# --------------------------------------------------------------------------------------
def _projectile_position(ctx):
    """void GetCharacterProjectilePosition(unsigned int character_index, srVector3T<float>*)"""
    fn = ctx.fn(0x004a57b0)
    cam = ctx.g('g_gd_camera').deref()
    pos = ctx.scratch(0) + 0x200
    for i in range(ctx.n(260)):
        r = ctx.rng('projectilepos', i)
        c = ctx.case('projectileposition.%d' % i, fn, conv='c', ret='v')
        x = r.random()
        if x < 0.75:
            idx = r.randrange(8)
        elif x < 0.88:
            idx = r.randrange(8, 64)
        else:
            idx = r.choice([100, 1000, 0x7fffffff, 0x80000000, 0x80000001, 0xfffffffe, 0xffffffff])
        x = r.random()
        if x < 0.6:
            yaw = r.uniform(0, TWO_PI)
        elif x < 0.8:
            yaw = r.uniform(-math.pi, math.pi)
        else:
            yaw = r.choice([0.0, ROT_OFFSET, ROT_OFFSET, math.pi, TWO_PI, -ROT_OFFSET,
                            math.pi / 2, 3 * math.pi / 2])
        x = r.random()
        if x < 0.65:
            pitch = r.uniform(-0.7, 0.7)
        elif x < 0.85:
            pitch = 0.0
        else:
            pitch = r.choice([math.pi / 2, -math.pi / 2, 1e-6, -1e-6, 1.2, -1.2])
        if r.random() < 0.1:
            cp = (0.0, 0.0, 0.0)
        else:
            cp = (r.uniform(-2e5, 2e5), r.uniform(-5000, 5000), r.uniform(-2e5, 2e5))
        c.set(cam + CAM_YAW, f32(yaw, pitch))
        c.set(cam + CAM_POS, f32(*cp))
        c.set(pos, _rand_floats(r, 3, -1e4, 1e4))
        c.arg(idx)
        c.arg(pos)
        c.cap(pos, 12, 'position', floats=[0, 4, 8])
        c.note(index=idx, yaw=rf(yaw), pitch=rf(pitch))


# --------------------------------------------------------------------------------------
def _next_missile(ctx):
    """W8Missile* NextMissile(bool restart)"""
    fn = ctx.fn(0x004a2760)
    world = ctx.g('g_world').deref()
    it = ctx.g('g_missile_iterator')
    vec = ctx.scratch(0)
    data = ctx.scratch(0) + 0x400
    elems = ctx.scratch(1)
    for i in range(ctx.n(180)):
        r = ctx.rng('nextmissile', i)
        c = ctx.case('nextmissile.%d' % i, fn, conv='c', ret='p', out='p')
        null_list = i < 6 or r.random() < 0.05
        x = r.random()
        if x < 0.85:
            count = r.randrange(0, 9)
        else:
            count = r.choice([-1, -5, -0x80000000, 0x7fffffff])
        x = r.random()
        hi = max(count, 0) if count < 100 else 8
        if x < 0.8:
            iterator = r.randrange(-4, hi + 4)
        else:
            iterator = r.choice([0, -1, 0x7fffffff, -0x80000000, -0x40000000, hi, hi - 1])
        restart = r.choice([0, 0, 1]) if r.random() < 0.85 else r.choice([2, 0xff, 0x100, 0x101,
                                                                          0xff00, 0xffffff00])
        c.set(it, u32(iterator))
        if null_list:
            c.set(world + W_MISSILES, u32(0))
        else:
            c.setp(world + W_MISSILES, vec)
            c.set(vec + V_COUNT, u32(count) + u32(max(count, 0) + r.randrange(0, 4)))
            c.setp(vec + V_DATA, data)
            for k in range(-4, 13):
                if r.random() < 0.1 and k != 0:
                    continue      # null element
                c.setp(data + 4 * k, elems + 0x40 * (k + 8))
        c.arg(restart)
        c.cap(it, 4, 'iterator')
        c.note(count=count, iterator=iterator, restart=restart, null_list=int(null_list))


# --------------------------------------------------------------------------------------
def _missile_with_rep(ctx, c, rep_offset=0x400):
    mis = ctx.scratch(1)
    rep = ctx.scratch(2) + rep_offset
    c.setp(mis + M_REP, rep)
    return mis, rep


def _blocks_ending_combat(ctx):
    """bool W8Missile::BlocksEndingCombat()"""
    fn = ctx.fn(0x004a5790)
    for i in range(ctx.n(100)):
        r = ctx.rng('blocksending', i)
        c = ctx.case('blocksendingcombat.%d' % i, fn, conv='t', ret='b')
        mis, rep = _missile_with_rep(ctx, c)
        done = r.choice([0, 0, 1]) if r.random() < 0.85 else r.choice([2, 0x80, 0xff])
        cyc = r.choice([0, 1, 1]) if r.random() < 0.75 else r.choice([2, 0xff, 0x81, 0x7f, 0x80,
                                                                       r.getrandbits(8)])
        c.set(mis + M_FLIGHT_DONE, u8(done))
        c.set(rep + R_CURRENT_CYCLE, u8(cyc))
        c.arg(mis)
        c.note(flight_done=done, current_cycle=cyc)


def _total_animation_count(ctx):
    """signed char W8Missile::GetTotalAnimationCount()"""
    fn = ctx.fn(0x004a4590)
    for i in range(ctx.n(48)):
        r = ctx.rng('totalanim', i)
        c = ctx.case('totalanimationcount.%d' % i, fn, conv='t', ret='i8')
        mis, rep = _missile_with_rep(ctx, c)
        kinds = []
        for e in range(2):
            k = (i >> e) & 1 if i < 4 else r.choice([0, 1, 2])
            if k == 1:
                c.setp(rep + R_EMITTERS + 4 * e, ctx.scratch(3) + 0x100 * e)
            elif k == 2:
                c.set(rep + R_EMITTERS + 4 * e, u32(r.choice([1, 0x80000000, 0xffffffff,
                                                               r.getrandbits(32) | 1])))
            kinds.append(k)
        c.arg(mis)
        c.note(emitters=kinds)


def _emitter_window(r, p_null=0.5):
    """256 dwords covering emitters[-128..127]: zero or random non-zero."""
    out = bytearray()
    for _ in range(256):
        out += u32(0 if r.random() < p_null else (r.getrandbits(32) | 1))
    return bytes(out)


def _cycle_arg(r, p_garbage=0.15):
    x = r.random()
    if x < 0.55:
        v = r.choice([0, 1])
    elif x < 0.75:
        v = r.choice([2, 3, 0x7f, 0x80, 0xff, 0xfe, 0x81])
    else:
        v = r.getrandbits(8)
    word = v
    if r.random() < p_garbage:
        word = r.choice([0x100, 0xffffff00, 0x12345600, 0x8000ff00]) | v
    return v, word


def _is_cycle_supported(ctx):
    """bool W8Missile::IsCycleSupported(signed char cycle)"""
    fn = ctx.fn(0x004a42b0)
    for i in range(ctx.n(160)):
        r = ctx.rng('iscyclesupported', i)
        c = ctx.case('iscyclesupported.%d' % i, fn, conv='t', ret='b')
        mis, rep = _missile_with_rep(ctx, c)
        c.set(rep + R_EMITTERS - 0x200, _emitter_window(r, r.choice([0.3, 0.5, 0.7])))
        v, word = _cycle_arg(r)
        c.arg(mis)
        c.arg(word)
        c.note(cycle=_schar(v), arg=word)
        if _schar(v) >= 2:
            c.note(edge='assert_cycle')


def _place_emitter(c, rep, cyc, target):
    """emitters[(signed char)cyc] = target; returns the signed index."""
    s = _schar(cyc)
    c.setp(rep + R_EMITTERS + 4 * s, target)
    return s


def _current_animation(ctx):
    """W8AnimObj* W8Missile::GetCurrentAnimation()"""
    fn = ctx.fn(0x004a4570)
    for i in range(ctx.n(60)):
        r = ctx.rng('curanim', i)
        c = ctx.case('currentanimation.%d' % i, fn, conv='t', ret='p', out='p')
        mis, rep = _missile_with_rep(ctx, c)
        cyc = r.choice([0, 1]) if r.random() < 0.6 else r.choice([0xff, 0x80, 0x81, 0x7f, 2,
                                                                  r.getrandbits(8)])
        c.set(rep + R_CURRENT_CYCLE, u8(cyc))
        if r.random() < 0.9:
            _place_emitter(c, rep, cyc, ctx.scratch(3) + 0x100 + 0x10 * (cyc & 0x7f))
        if _schar(cyc) < 0:      # the unsigned reading would land here
            c.setp(rep + R_EMITTERS + 4 * (cyc & 0xff), ctx.scratch(3) + 0x2000)
        c.arg(mis)
        c.note(current_cycle=_schar(cyc))


def _current_animation_scale(ctx):
    """float W8Missile::GetCurrentAnimationScale()"""
    fn = ctx.fn(0x004a45c0)
    specials = [-0.0, INF, -INF, 1e-40, -1e-42, NAN, 3.4e38, 1.0]
    for i in range(ctx.n(60)):
        r = ctx.rng('curanimscale', i)
        c = ctx.case('currentanimationscale.%d' % i, fn, conv='t', ret='f')
        mis, rep = _missile_with_rep(ctx, c)
        cyc = r.choice([0, 1]) if r.random() < 0.6 else r.choice([0xff, 0x80, 0x81, 0x7f, 2,
                                                                  r.getrandbits(8)])
        anim = ctx.scratch(3) + 0x400
        c.set(rep + R_CURRENT_CYCLE, u8(cyc))
        _place_emitter(c, rep, cyc, anim)
        val = r.choice(specials) if r.random() < 0.2 else r.uniform(0.1, 60.0)
        c.set(anim + A_PLAYBACK, f32(val))
        if _schar(cyc) < 0:
            other = ctx.scratch(3) + 0x800
            c.setp(rep + R_EMITTERS + 4 * (cyc & 0xff), other)
            c.set(other + A_PLAYBACK, f32(-12345.0))
        c.arg(mis)
        c.note(current_cycle=_schar(cyc), scale=val)


def _lod_value(r):
    x = r.random()
    if x < 0.65:
        return r.choice([0, 1, 2])
    if x < 0.85:
        return r.choice([3, 4, 5, 0xff, 0xfe, 0xfa])
    return r.choice([0x7f, 0x80, 0x81, r.getrandbits(8)])


def _current_animesh(ctx):
    """W8AniMesh* W8Missile::GetCurrentAniMesh()"""
    fn = ctx.fn(0x004a45f0)
    for i in range(ctx.n(80)):
        r = ctx.rng('curanimesh', i)
        c = ctx.case('currentanimesh.%d' % i, fn, conv='t', ret='p', out='p')
        mis, rep = _missile_with_rep(ctx, c)
        cyc = r.choice([0, 1]) if r.random() < 0.7 else r.choice([0xff, 0x80, 2, 0x7f])
        lod = _lod_value(r)
        anim = ctx.scratch(3) + 0x400
        c.set(rep + R_CURRENT_CYCLE, u8(cyc))
        c.set(rep + R_LOD, u8(lod))
        _place_emitter(c, rep, cyc, anim)
        sl = _schar(lod)
        null_entry = r.random() < 0.1
        if not null_entry:
            c.setp(anim + A_ENTRIES + 4 * sl, ctx.scratch(4) + 0x40 * (lod & 0x7f))
        if sl < 0:
            c.setp(anim + A_ENTRIES + 4 * (lod & 0xff), ctx.scratch(4) + 0x3000)
        if _schar(cyc) < 0:
            c.setp(rep + R_EMITTERS + 4 * (cyc & 0xff), ctx.scratch(3) + 0x2000)
        c.arg(mis)
        c.note(current_cycle=_schar(cyc), lod=sl, null_entry=int(null_entry))


def _apply_emitter_setting(ctx):
    """unsigned int W8MissileRep::ApplyEmitterSetting(signed char emitter)"""
    fn = ctx.fn(0x004a2710)
    rep = ctx.scratch(2) + 0x400
    anim = ctx.scratch(3) + 0x400
    anim_u = ctx.scratch(3) + 0x2000     # what an unsigned emitter index would reach
    for i in range(ctx.n(160)):
        r = ctx.rng('applyemitter', i)
        c = ctx.case('applyemittersetting.%d' % i, fn, conv='t', ret='i')
        v, word = _cycle_arg(r, 0.12)
        s = _place_emitter(c, rep, v, anim)
        lod = _lod_value(r)
        sl = _schar(lod)
        c.set(rep + R_LOD, u8(lod))
        path_lists = 0 if r.random() < 0.7 else r.choice([1, 2, 0x80, 0xff])
        frames = r.choice([0, 1, 7, 0x7f, 0x80, 0xff, r.getrandbits(8)])
        c.set(anim + A_PATH_LISTS, u8(path_lists))
        c.set(anim + A_FRAME_COUNT, u8(frames))
        null_mesh = r.random() < 0.1
        mesh_frames = r.getrandbits(8)
        # entries[] starts at +0x18: entries[-1] covers frame_count (+0x16) and entries[-5]
        # covers path_lists (+0x05). A pointer stored there puts address bytes (different
        # in the two processes) into the field the function reads, so that slot stays
        # empty: lod -1 with path_lists set returns the frame_count written above, lod -5
        # reads a NULL entry (assert 0x2be) or returns frame_count.
        clash = (sl == -1 and path_lists != 0) or sl == -5
        if clash:
            null_mesh = True
        if not null_mesh:
            mesh = ctx.scratch(4) + 0x40 * (lod & 0x7f)
            c.setp(anim + A_ENTRIES + 4 * sl, mesh)
            c.set(mesh, u8(0x02 | (r.getrandbits(8) & 0xfd)) + u8(mesh_frames))
        if sl < 0:
            mesh2 = ctx.scratch(4) + 0x3000
            c.setp(anim + A_ENTRIES + 4 * (lod & 0xff), mesh2)
            c.set(mesh2, u8(0x02) + u8(mesh_frames ^ 0x5a))
        if s < 0:
            c.setp(rep + R_EMITTERS + 4 * (v & 0xff), anim_u)
            c.set(anim_u + A_PATH_LISTS, u8(1))
            c.set(anim_u + A_FRAME_COUNT, u8(frames ^ 0xa5))
        c.arg(rep)
        c.arg(word)
        c.note(emitter=s, arg=word, lod=sl, path_lists=path_lists, frames=frames,
               null_mesh=int(null_mesh), mesh_frames=mesh_frames)
        if null_mesh and not path_lists:
            c.note(edge='assert_null_mesh')


def _set_effect_definition(ctx):
    """void W8Missile::SetEffectDefinition(const W8SpellEffectDefinition*)"""
    fn = ctx.fn(0x004a5410)
    mis = ctx.scratch(1)
    src = ctx.scratch(0) + 0x80
    rows = list(range(MISSILE_ROWS)) * 3
    for i in range(ctx.n(120)):
        r = ctx.rng('seteffectdef', i)
        c = ctx.case('seteffectdefinition.%d' % i, fn, conv='t', ret='v')
        row = rows[i] if i < len(rows) else r.randrange(MISSILE_ROWS)
        c.set(mis + M_TABLE_INDEX, u32(row))
        c.set(mis + M_DEFINITION - 4, _rand_bytes(r, DEF_SIZE + 8))   # neighbours too
        d = bytearray(_rand_bytes(r, DEF_SIZE))
        d[0:4] = f32(r.uniform(-1000, 1000))
        c.set(src, bytes(d))
        c.arg(mis)
        c.arg(src)
        c.cap(mis, M_SIZE, 'missile')
        c.note(row=row)


# --------------------------------------------------------------------------------------
def _choose_direction(ctx):
    """unsigned short ChooseDifferentMonsterDirection(unsigned short previous). Only the
    low 16 bits matter (retail: and esi, 0xffff); a low word > 3 loops forever."""
    fn = ctx.fn(0x004c2e00)
    for i in range(ctx.n(120)):
        r = ctx.rng('choosedir', i)
        c = ctx.case('choosedirection.%d' % i, fn, conv='c', ret='u16')
        prev = i % 4 if i < 80 else r.randrange(4)
        word = prev
        if r.random() < 0.15:
            word |= r.choice([0x10000, 0xffff0000, 0x7fff0000, 0x12340000])
        c.arg(word)
        c.note(previous=prev, arg=word)


# --------------------------------------------------------------------------------------
CYCLE_NAMES = ['BIRTH', 'IDLE', 'SPICE', 'TRANSITION', 'WALK', 'DRAW', 'ATTACK_CLOSE',
               'ATTACK_RANGED', 'unused', 'ATTACK_SWING', 'ATTACK_THRUST', 'ATTACK_BASH',
               'ATTACK_MELEE', 'ATTACK_THROW', 'ATTACK_PUNCH', 'ATTACK_KICK', 'ATTACK_LASH',
               'ATTACK_SHOOT', 'ATTACK_SPECIAL', 'DODGE', 'GET_HIT', 'DIE', 'TURN', 'TALK_SPICE',
               'TALK', 'SPELL', 'SPECIAL']
DIGIT_SUFFIXES = ['0', '1', '2', '3', '5', '9', '10', '12', '99', '127', '128', '200', '255',
                  '256', '1000', '65535', '65536', '007', '2x', '3abc', '4 ', '01']
OVERFLOW_SUFFIXES = ['2147483647', '2147483648', '2147483649', '4294967295', '4294967296',
                     '4294967297', '4294967424', '99999999999', '12345678901234567890',
                     '00000000000000000003']
NONDIGIT_SUFFIXES = ['-1', '-5', ' 3', '+4', '_2', 'A', '.5', '\t7', 'x9']
PREFIX_EXT = ['BIRTHDAY', 'IDLE_LOOP', 'WALKING', 'TALK_SPICE2', 'TALKER', 'TALK_', 'TALK_SPIC',
              'ATTACK_CLOSE_2', 'ATTACK_CLOSER', 'DIEHARD', 'SPELLCAST3', 'SPECIAL_2',
              'SPICEY', 'TURNAROUND', 'DRAWN', 'GET_HITS', 'DODGEBALL', 'TRANSITIONAL',
              'unused7', 'DIE9', 'IDLE12', 'TURN1']
CASE_MISMATCH = ['idle', 'Idle2', 'walk', 'Walk3', 'die', 'Talk', 'birth1', 'UNUSED', 'spell']
UNMATCHED = ['SOUND_FRAME', 'SOUND_CYCLE', 'SOUND_FOOTSTEP', 'SHAKE_FRAME', 'ATTACK', 'ATTACK_',
             'TAL', 'SPEC', 'SPE', '', 'X', 'movementrate', 'flies', 'skin', 'skinswap',
             'glow', 'addlight', 'CYCLE_IDLE', 'FL', 'EXPLOD', 'GET', 'D', 'IDL', 'WAL',
             'TRANSITIO', '1', '12', 'ABCDEFGHIJKL', 'ABCDEFGHIJK5']
FALLBACK = ['FLY', 'FLY1', 'FLY12', 'FLYING', 'FLY_', 'FLY9', 'EXPLODE', 'EXPLODE3',
            'EXPLODED', 'EXPLODE_BIG', 'EXPLODE12345678']


def _retail_parse(name):
    """Retail 0x004C2010 on bytes `name` (without NUL) -> (cycle, reads_outside_table).
    Every g_cycle_names prefix_length equals its name length, so strncmp == startswith.
    No match: suffix = g_cycle_names[-1].prefix_length (byte 0x0c at 0x0060EA04); the atoi
    offset always comes from the search index (27 after a full miss: byte 0x49 = 73)."""
    index = 27
    cycle = -1
    for k, n in enumerate(CYCLE_NAMES):
        if name.startswith(n.encode()):
            cycle = index = k
            break
    if cycle < 0:
        if name.startswith(b'FLY'):
            cycle = 0
        elif name.startswith(b'EXPLODE'):
            cycle = 1
    suffix = 12 if cycle < 0 else len(CYCLE_NAMES[cycle])
    digit = len(name) > suffix and 0x30 <= name[suffix] <= 0x39
    return cycle, bool(digit and index == 27)


def _parse_names(ctx):
    """-> list of (bytes buffer, label, edge or None)."""
    r = ctx.rng('parsecycle', 'names')
    out = []
    for n in CYCLE_NAMES + ['FLY', 'EXPLODE']:
        out.append((n.encode(), 'exact', None))
    for n in CYCLE_NAMES:
        for s in r.sample(DIGIT_SUFFIXES, 2):
            out.append(((n + s).encode(), 'digits', None))
    for s in OVERFLOW_SUFFIXES:
        for n in r.sample(CYCLE_NAMES, 2):
            out.append(((n + s).encode(), 'overflow', None))
    for s in NONDIGIT_SUFFIXES:
        n = r.choice(CYCLE_NAMES)
        out.append(((n + s).encode(), 'nondigit', None))
    for n in PREFIX_EXT:
        out.append((n.encode(), 'prefix', None))
    for n in CASE_MISMATCH:
        out.append((n.encode(), 'case', None))
    for n in UNMATCHED:
        out.append((n.encode(), 'unmatched', None))
    for n in FALLBACK:
        out.append((n.encode(), 'fallback', None))
    # retail out-of-table reads (see docstring): suffix 12 / atoi at name+73
    oob = ['ABCDEFGHIJKL5', 'SOUND_FRAMES7', 'XXXXXXXXXXXX0XYZ', 'abcdefghijkl99',
           'SHAKE_FRAME_3', 'FLYAB7', 'FLY__3_', 'FLYxx12345', 'SOUND_CYCLE_8x', 'MOVEMENTRATE4']
    for k, n in enumerate(oob):
        buf = bytearray(n.encode() + b'\0')
        buf += b'\0' * (73 - len(buf)) if len(buf) < 73 else b''
        if len(buf) > 73:
            buf = buf[:73]
        buf += str(10 + 37 * k).encode() + b'\0'
        out.append((bytes(buf), 'oob', 'oob_read'))
    # random compositions
    for _ in range(70):
        x = r.random()
        n = r.choice(CYCLE_NAMES)
        if x < 0.4:
            s = str(r.randrange(0, 400))
        elif x < 0.6:
            s = str(r.getrandbits(r.choice([16, 31, 32, 40])))
        elif x < 0.8:
            s = ''.join(r.choice('0123456789_-ABx ') for _ in range(r.randrange(1, 6)))
        else:
            n = n[:r.randrange(1, len(n) + 1)]
            s = r.choice(['', '1', '_', 'Z'])
        out.append(((n + s).encode(), 'random', None))
    labelled = []
    for buf, label, edge in out:
        oob = _retail_parse(buf.split(b'\0')[0])[1]
        if label == 'oob' and not oob:
            raise ValueError('oob name %r does not reach the out-of-table read' % buf)
        labelled.append((buf, label, 'oob_read' if oob else edge))
    return labelled


def _parse_cycle_name(ctx):
    """W8MonsterCycle ParseMonsterCycleName(const char* name, signed char* subcycle)"""
    fn = ctx.fn(0x004c2010)
    name = ctx.scratch(0)
    sub = ctx.scratch(0) + 0x400
    entries = _parse_names(ctx)
    for i, (buf, label, edge) in enumerate(entries[:ctx.n(len(entries))]):
        r = ctx.rng('parsecycle', i)
        c = ctx.case('parsecyclename.%d' % i, fn, conv='c', ret='i')
        data = buf if b'\0' in buf else buf + b'\0'
        c.set(name, data)
        with_sub = edge is not None or r.random() < 0.85
        c.arg(name)
        if with_sub:
            c.set(sub, u8(r.getrandbits(8)))
            c.arg(sub)
            c.cap(sub, 1, 'subcycle')
        else:
            c.arg(0)
        text = buf.split(b'\0')[0]
        c.note(name=text.decode('latin-1'), kind=label, subcycle=int(with_sub),
               retail_cycle=_retail_parse(text)[0])
        if edge:
            c.note(edge=edge)


# --------------------------------------------------------------------------------------
def _randomize_appearance(ctx):
    """void W8Monster::RandomizeAppearanceAndMotion()"""
    fn = ctx.fn(0x004c1d20)
    mon = ctx.scratch(1)
    rep = ctx.scratch(2)
    ptrs = ctx.scratch(3)
    scales = ctx.scratch(3) + 0x800
    anims = ctx.scratch(4)
    big_counts = [0x80, 0xff, 0x100, 0x101, 0x103, 0x80000000, 0xffffffff]
    for i in range(ctx.n(260)):
        r = ctx.rng('randomizeappearance', i)
        c = ctx.case('randomizeappearance.%d' % i, fn, conv='t', ret='v')
        c.setp(mon + MO_REP, rep)
        edges = []
        # LEFTHANDED percent: signed compare with Random(100)
        x = r.random()
        if x < 0.5:
            lh = 45
        elif x < 0.85:
            lh = r.randrange(0, 101)
        else:
            lh = r.choice([0, 1, 99, 100, 101, -1, -100, 0x7fffffff, -0x80000000])
        c.set(rep + MR_LEFT, u32(lh))
        # scale range
        x = r.random()
        if x < 0.45:
            mn, mx, sk = 0.0, 0.0, 'none'
        elif x < 0.8:
            mn = r.uniform(0.4, 1.2)
            mx, sk = mn + r.uniform(0.0, 0.8), 'range'
        elif x < 0.86:
            mn = mx = r.choice([0.5, 1.0, 1.5])
            sk = 'equal'
        elif x < 0.92:
            mn, mx = r.choice([(0.0, 1.3), (0.9, 0.0), (-0.0, 1.0)])
            sk = 'one_zero'
        elif x < 0.97:
            mx = r.uniform(0.4, 1.0)
            mn, sk = mx + r.uniform(0.01, 0.5), 'min_gt_max'
        else:
            mn, mx = r.choice([(NAN, 1.2), (0.8, NAN), (NAN, NAN)])
            sk = 'nan'
            edges.append('nan')
        c.set(rep + MR_SCALE, f32(r.uniform(0.5, 1.5), mn, mx))
        # random idle playback
        ri = 1 if r.random() < 0.7 else 0
        if r.random() < 0.05:
            ri = r.choice([2, 0x80, 0xff])
        x = r.random()
        if x < 0.5:
            fmin, fmax = -3.0, 3.0
        elif x < 0.9:
            fmin = r.uniform(-12, 2)
            fmax = fmin + r.uniform(0, 14)
        else:
            fmin, fmax = r.choice([(0.0, 0.0), (5.0, -5.0), (-30.0, -20.0), (-10.0, -10.0)])
        idle_pb = r.choice([10.0, 15.0, 20.0, 30.0]) if r.random() < 0.5 else r.uniform(-5, 40)
        c.set(rep + MR_RANDOM_IDLE, u8(ri))
        c.set(rep + MR_IDLE_PB, f32(idle_pb, fmin, fmax))
        c.set(rep + MR_CUR_SUB, u8(r.getrandbits(8)))
        # animations[1]
        if i < len(big_counts) * 2:
            count = big_counts[i % len(big_counts)]
            ri = 1
            c.set(rep + MR_RANDOM_IDLE, u8(ri))
            edges.append('count_byte')
        else:
            x = r.random()
            count = r.randrange(1, 5) if x < 0.85 else r.choice([0, 5, 8, 12, 0x7f])
        nptr = min(count, 0x110) if count < 0x80000000 else 0x10
        if count in big_counts:
            nptr = 0x110
        c.set(rep + MR_ANIM1 + V_COUNT, u32(count) + u32(max(nptr, 1)))
        c.setp(rep + MR_ANIM1 + V_DATA, ptrs)
        for k in range(nptr):
            a = anims + 0x50 * k
            c.setp(ptrs + 4 * k, a)
            if k < 16:
                c.set(a + A_PLAYBACK, f32(r.uniform(0.5, 30.0)))
        # animation_scales[1]
        x = r.random()
        if x < 0.7:
            scount = count if count < 0x80000000 else 0
        elif x < 0.85:
            scount = max(0, min(count, 0x110) - r.randrange(1, 3))
        elif x < 0.95:
            scount = min(count, 0x110) + r.randrange(1, 3)
        else:
            scount = r.choice([0, -1, -0x80000000])
        nsc = max(0, min(scount, 0x110)) if scount < 0x80000000 else 0
        c.set(rep + MR_SCALES1 + V_COUNT, u32(scount) + u32(max(nsc, 1)))
        c.setp(rep + MR_SCALES1 + V_DATA, scales)
        if nsc:
            c.set(scales, f32(*[r.uniform(0.5, 30.0) for _ in range(min(nsc, 16))]))
        # monster fields
        x = r.random()
        if x < 0.5:
            hover = (0.0, 0.0)
        elif x < 0.9:
            h0 = r.uniform(0, 1.0)
            hover = (h0, h0 + r.uniform(0, 1.0))
        else:
            hover = r.choice([(1.0, 0.0), (-0.5, 0.5), (2.0, 2.0)])
        x = r.random()
        bob = (0.0, 0.0) if x < 0.5 else (r.uniform(0, 0.2), r.uniform(0, 0.6))
        c.set(mon + MO_HOVER_MIN, f32(hover[0], hover[1], bob[0], bob[1]))
        c.set(mon + MO_VBASE, _rand_floats(r, 3, -100.0, 100.0))
        c.set(mon + MO_HEIGHT, f32(r.uniform(250, 1500), r.uniform(0, 1500), r.uniform(-50, 50)))
        c.set(mon + MO_MIRROR, u8(r.getrandbits(8)))
        x = r.random()
        if x < 0.7:
            mscale = 1.0
        elif x < 0.95:
            mscale = r.choice([0.25, 0.5, 0.75, 0.99999, 1.00001, 2.0, r.uniform(0.1, 1.0)])
        else:
            mscale = r.choice([NAN, 0.0, -1.0])
            if mscale != mscale:
                edges.append('nan')
        c.set(mon + MO_SCALE, f32(mscale))
        c.set(rep + MR_INSTANCE_SCALE, f32(r.uniform(0, 2)))
        c.arg(mon)
        c.cap(mon, MO_SIZE, 'monster', ignore=[MO_REP],
              floats=[MO_VBASE, MO_VBASE + 4, MO_VBASE + 8, MO_HEIGHT, MO_HEIGHT + 4, MO_VOFFSET])
        c.cap(rep, MR_SIZE, 'rep', ignore=[MR_ANIM1 + V_DATA, MR_SCALES1 + V_DATA],
              floats=[MR_SCALE, MR_INSTANCE_SCALE])
        if nptr:
            c.cap(anims, 0x50 * nptr, 'anims', floats=[0x50 * k + A_PLAYBACK for k in range(nptr)])
        if nsc:
            c.cap(scales, 4 * nsc, 'scales', floats=[4 * k for k in range(nsc)])
        c.note(left_handed=lh, scale_range=sk, random_idle=ri, count=count, scales=scount,
               fps='%g..%g' % (rf(fmin), rf(fmax)), monster_scale=mscale)
        if edges:
            c.note(edge=','.join(sorted(set(edges))))
