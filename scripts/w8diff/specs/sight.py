"""Sight.cpp (src/wiz8/local_code/Sight.cpp): sight thresholds, visibility records, group
sight queries and the monster-to-monster sight pass.

Everything the functions read is built in scratch memory and wired in for the call, so no
case depends on the live monsters of the loaded save:
  * g_world AND g_secondary_world -> scratch W8World (S0) whose srCamera (S0+0x100) holds
    the far clip WorldGetFarClip returns (near_clip +0x168, far_clip +0x170, doubles).
    g_secondary_world is pointed at it as well so the port's WorldGetRenderFarScale
    returns 1.0: the port's [Display] ViewDistance mod (k = 1.5 in games\\work) divides
    the camera far clip of every other world by k, retail has no such mod.
  * gXStatus.plsMonsterList / plsUnbornMonsterList -> scratch W8PLists (S1+0x8000/0x8100)
    of scratch W8MonsterInfo records (S1, stride 0x430);
  * W8MonsterInfo.p3D -> scratch W8Monster (S2, stride 0x350: yaw +0xec, position +0x118,
    alternate_radius +0x18c, height_offset +0x190, m_pRep +0x1d8, location_id +0x1e4);
    m_pRep -> W8MonsterRep stub (S2+0x8000, current_cycle +0xa4, pending_cycle +0xa7);
  * gXStatus.monster_record_cache[990..] -> scratch W8MonsterRecords (S3: kind +0xcb,
    camouflage0 +0x248, effective_level +0x24f), GetMonsterDataForInfo never loads;
  * mon-to-mon visibility PLists (headers, data, 0x31-byte records) in S4, monster groups
    and their ILists in S5, a stand-alone W8VisibilityRecord in S6.
Bytes of the scratch records that retail does not read are random filler (identical in
both processes), so a read at a wrong offset shows up as a difference.

Octree: UpdateMonsterSight, RefreshInwardSightForAllMonsters and MonsterGroupCanSeeGroup
reach HasLineOfSightToMonster / GetMonsterSightFlags (g_octree traces). Their scratch
monsters stand around x=-3e6, y=+3e6, z=-3e6 (relative layout realistic, +-1.1 far clip),
far outside any level: every traced cell is outside the leaf grid (no blockers), the packed
prop-registry cell key is negative (cannot alias a registered prop cell) and every location
id is <= -3, so TraceLineOfSight never runs ResolveTraceHit (no live monster, camera or
pathing probe is consulted). Lines of sight are therefore always clear and g_world is not
touched by the traces. has_projectile_origin / has_spell_origin stay 0 there
(GetProjectilePosition / GetSpellPosition need a real model and virtual calls).

Tested (retail address, name, cases):
  0x00505a40 ComputeSightThreshold               400  far clip incl. 0, -0, NaN, 1e-50/1e-300
                                                      (retail compares the double far clip,
                                                      before the float store), unsigned
                                                      perception - 2*penalty wrap, x87 _ftol
                                                      overflow, ranged/penalty overflow,
                                                      non-canonical bool/byte arguments with
                                                      high garbage, exact 100%/clamp paths
  0x005058a0 CanMonsterSeeMonster                300  scratch infos/p3D/records; kind 4
                                                      (8-bit level*5 wrap), kind 12, blind,
                                                      camouflage, hp 0 / condition >= 0xf
                                                      (unsigned) early outs; boundary cases
                                                      distance == far clip at 100%
                                                      (note edge='x87_threshold': retail
                                                      compares the unrounded x87 threshold)
  0x00505dd0 IsVisibleUnderConditions            250  kinds 0..6 + out of range (unsigned
                                                      jump table), NULL row, NULL monster for
                                                      kinds that do not read it, bool bytes
  0x00505e60 MonsterHasProjectileOrigin          100  incl. bool bytes 2/0x80/0xff (retail setne)
  0x00505e80 GetMonsterSpellSightIndex           100  same
  0x00504910 IsSightRangeOverridden              100  g_view_distance 12.0, neighbours, +-0,
                                                      inf, NaNs (retail: test ah,0x40 -> NaN
                                                      counts as "not overridden")
  0x00505d20 FindMonToMonVisibility              200  NULL entries (assert 1030, continue),
                                                      first of several matches, negative or
                                                      too large iNumUsed, NULL list, fActive
                                                      asserts 1020/1021
  0x00505ea0 MonsterGroupHasVisibleThreat        200  IList of location ids over main and
                                                      unborn lists, IsDying via rep stub,
                                                      NULL p3D behind fActive = 0
  0x00505f30 MonsterGroupCanSeeGroup             250  in combat: source list walk, asserts
                                                      0x3fc/0x3fd/0x406; out of combat:
                                                      distance vs far clip, CanMonsterSeeMonster
                                                      with sight_state 1, clear octree line
  0x005049c0 UpdateMonsterSight                  300  direction false (mon-to-mon pass) in
                                                      combat: record search/append (PList with
                                                      spare capacity; the appended heap pointer
                                                      is ignored), NULL entry early return,
                                                      sight state decay window 0xf0, clock wrap;
                                                      early returns (screen != 7, !fActive,
                                                      hp 0, combat mode off), far clip edges
  0x005057d0 RefreshInwardSightForAllMonsters    150  1..4 monsters, every one a source
  0x00504930 AgeAllMonsterSight                  120  only monsters with highest_condition >=
                                                      0x12 (unsigned, incl. 0x80000000..) so
                                                      AgeMonsterSight is never reached in
                                                      retail; every case has >= 1 step
                                                      (retail returns a leftover multiply
                                                      product when no step elapsed - the
                                                      original is void, the port returns 0)
  Total 2470 cases.

Skipped:
  0x005048e0 ResetSight                       - resets view distance, navigator link mode,
                                                the game-time duration scale and the monster
                                                generator timers (global world state)
  0x00505760 RefreshMonsterSight              - runs the player pass (direction true)
  0x00505780 RefreshOutwardSightForAllMonsters - player pass over the live list + combat UI
                                                refresh (RefreshFlaggedMainGameState,
                                                RefreshAllPartyTargets)
  0x00505810 RefreshAllSight                  - same as above plus the inward pass
  0x005060c0 ResetAndRefreshAllSight          - same as above
  0x00505ba0 ReleaseMonToMonVisibilityInfoAbout - inlined in the port (not in Wiz8Runtime.map);
                                                frees heap records anyway
  0x00505c80 ReleaseMonToMonVisibilityList    - free()s every record and PLDestroy()s the list
                                                (scratch pointers would corrupt the heap)
  UpdateMonsterSight direction = true (player pass) is not tested: live camera position and
  frustum, real-time g_game_time_accumulator ticks, notices, target markers, faction flags,
  character speech events, monster fade in/out, NPC events.
"""
import math
import struct

from w8diff.api import F32, Blob

MAX_OPS = 96          # W8D_MAX_OPS in w8diff_core.c (extra ops would be dropped)

# --- scratch buffers ---
S_WORLD = 0           # W8World at +0, srCamera at +0x100
S_MON = 1             # W8MonsterInfo (stride 0x430); monster PLists at +0x8000 / +0x8100
S_P3D = 2             # W8Monster (stride 0x350); W8MonsterRep stubs at +0x8000
S_REC = 3             # W8MonsterRecord (stride 0x2a0)
S_VIS = 4             # visibility PLists and records
S_GROUP = 5           # W8MonsterGroup source +0 / target +0x200, IList +0x400, ids +0x500
S_MISC = 6            # stand-alone W8VisibilityRecord

# --- W8World / srCamera ---
WORLD_CAMERA = 0x44
CAM_OFF = 0x100
CAM_NEAR = 0x168      # double near_clip; double far_clip at +0x170

# --- W8MonsterInfo (layout.ps1) ---
MI_STRIDE = 0x430     # sizeof 0x425
MI_LOC = 0x00
MI_GROUP = 0x04
MI_SPECIES = 0x08
MI_P3D = 0x0c
MI_ACTIVE = 0x14
MI_INCOMBAT = 0x15
MI_HP = 0x2b
MI_BLIND = 0x87       # uiCondition[12] (W8_CONDITION_BLIND)
MI_HCOND = 0x107
MI_SENSES = 0x24b     # attributes[4]
MI_THREAT = 0x28a     # party_threat.sight_state
MI_VISLIST = 0x2b6    # plsVisMonToMon
MI_HAS_PROJ = 0x37a
MI_HAS_SPELL = 0x37c

ML_MAIN = 0x8000      # main monster PList header (data at +0x10)
ML_UNBORN = 0x8100    # unborn monster PList header (data at +0x10)

# --- W8VisibilityRecord (0x31, packed) ---
VR_SIZE = 0x31
VR_ABOUT = 0x00
VR_STATE = 0x04
VR_CAN_SEE = 0x0b
VR_LAST = 0x0c
VR_LINE = 0x28
VR_FLOATS = (0x10, 0x14, 0x18, 0x1c, 0x20, 0x24)

VS_DATA = 0x100       # PList data of list slot k at VS_DATA + VS_DATA_STEP * k
VS_DATA_STEP = 0x80
VS_REC = 0x800        # record j of list slot k at VS_REC + VS_REC_STEP * (8 * k + j)
VS_REC_STEP = 0x40

# --- W8Monster (p3D) ---
M3_STRIDE = 0x350     # sizeof 0x348
M3_WIN = 0xec         # one set covers +0xec .. +0x1e8
M3_WIN_END = 0x1e8
M3_YAW = 0xec         # movement.yaw (GetYaw)
M3_POS = 0x118        # movement.position (GetPosition)
M3_RADIUS = 0x18c     # movement.alternate_radius
M3_HEIGHT = 0x190     # movement.height_offset
M3_REP = 0x1d8        # m_pRep
M3_LOC = 0x1e4        # location_id (TraceLineOfSight ids)
REP_BASE = 0x8000
REP_STEP = 0x100
REP_CYCLE = 0xa4      # current_cycle (Query(6), signed char); pending_cycle at +0xa7

# --- W8MonsterRecord ---
REC_STRIDE = 0x2a0    # sizeof 0x297
REC_WIN = 0xc0        # filler window written around the fields read
REC_WIN_END = 0x260
REC_KIND = 0xcb
REC_CAMO = 0x248
REC_LEVEL = 0x24f
SPECIES_BASE = 990    # monster_record_cache slots 990..999 are empty in the live game

# --- W8MonsterGroup ---
GR_SIZE = 0x12b
GR_MONSTERS = 0x08    # W8IList* of location ids
GR_LEADER = 0x9f      # leader_location_id
GR_TARGET = 0x200
GR_ILIST = 0x400
GR_IDATA = 0x500

# --- gXStatus ---
GX_COMBAT = 0x8dc
GX_MONLIST = 0x8f5
GX_UNBORN = 0x901
GX_RECCACHE = 0xa0f

# --- g_status ---
GS_CLOCK = 0x18d8     # world_clock
GS_LEVEL = 0x1900     # current_level
GS_LP = 0x1a04        # level_progress[0x2f], 0x21 each
GS_LP_ROW = 0x21
GS_LP_SIGHT = 0x0d    # sight_clock
LEVEL_COUNT = 0x2f

SCREEN_MAIN = 7
PI = math.pi
FARS = [6000.0, 8000.0, 10000.0, 12000.0, 12500.0, 15000.0, 16000.0, 20000.0, 25000.0, 30000.0]
BASE = (-3.0e6, 3.0e6, -3.0e6)     # outside every level (see docstring)
COND_EDGE = [0x80000000, 0xfffffff0, 0xffffffff, 0x7fffffff, 0x100]
BOOL_EDGE = [2, 0x80, 0xff]
NAN = float('nan')
INF = float('inf')

N_THRESHOLD = 400
N_CAN_SEE = 300
N_VISIBLE = 250
N_HAS_PROJ = 100
N_SPELL_INDEX = 100
N_VIEW = 100
N_FIND = 200
N_THREAT = 200
N_GROUP_SEE = 250
N_UPDATE = 300
N_INWARD = 150
N_AGE = 120


# ----------------------------------------------------------------------------- helpers
def u8(v):
    return struct.pack('<B', int(v) & 0xff)


def u32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def f64b(x):
    return struct.pack('<d', x)


def fr(x):
    """Round to float32 as x87 fst does (overflow -> inf)."""
    try:
        return struct.unpack('<f', struct.pack('<f', x))[0]
    except OverflowError:
        return math.copysign(INF, x)


def q(v):
    """Quarter units: exactly representable around 3e6."""
    return round(v * 4.0) / 4.0


def trim(data):
    """Scratch is zeroed for every case: trailing zero bytes need not be written."""
    data = bytes(data)
    end = len(data)
    while end > 1 and data[end - 1] == 0:
        end -= 1
    return data[:end]


def filler(r, n):
    return bytearray(r.getrandbits(8) for _ in range(n))


def pick(r, weighted):
    """weighted: list of (weight, value-or-callable)."""
    total = sum(w for w, _ in weighted)
    x = r.random() * total
    for w, v in weighted:
        x -= w
        if x < 0:
            return v() if callable(v) else v
    v = weighted[-1][1]
    return v() if callable(v) else v


def fnote(x):
    return repr(float(x))


def done(c):
    if len(c.ops) > MAX_OPS:
        raise ValueError('%s: %d ops > %d' % (c.id, len(c.ops), MAX_OPS))


def gen_bool(r, p_true, edge_p=0.0):
    x = r.random()
    if x < edge_p:
        return r.choice(BOOL_EDGE)
    return 1 if r.random() < p_true else 0


def gen_hp(r):
    return pick(r, [(80, lambda: r.randrange(1, 600)), (12, 0),
                    (8, lambda: r.choice([1, 0x7fffffff, 0x80000000, 0xffffffff]))])


def gen_hcond(r, threshold):
    """highest_condition around the function's (unsigned) threshold."""
    return pick(r, [(55, 0), (22, lambda: r.randrange(1, 0x15)),
                    (15, lambda: r.choice([threshold - 1, threshold, threshold + 1])),
                    (8, lambda: r.choice(COND_EDGE))])


def gen_senses(r):
    return pick(r, [(85, lambda: r.randrange(1, 126)),
                    (15, lambda: r.choice([0, 1, 2, 125, 126, 200, 255]))])


def gen_blind(r):
    return pick(r, [(85, 0), (10, lambda: r.randrange(1, 20)),
                    (5, lambda: r.choice([0x80000000, 0xffffffff, 0x100]))])


def gen_kind(r):
    return pick(r, [(40, 0), (25, 4), (20, 12),
                    (15, lambda: r.choice([1, 2, 3, 5, 6, 8, 11, 13, 0x84, 0x8c, 0xff]))])


def gen_level(r):
    return pick(r, [(70, lambda: r.randrange(1, 41)),
                    (30, lambda: r.choice([0, 1, 24, 25, 26, 27, 50, 51, 52, 53, 100, 127, 128,
                                           200, 255]))])


def gen_camo(r):
    return pick(r, [(55, 0), (30, lambda: r.randrange(1, 11)),
                    (15, lambda: r.choice([11, 15, 19, 20, 21, 50, 100, 255]))])


def gen_clock(r):
    return pick(r, [(75, lambda: r.randrange(1000, 20000000)),
                    (25, lambda: r.choice([0, 1, 0xf0, 0xf1, 0x7fffffff, 0x80000000,
                                           0xffffffff, 0xfffffff0]))])


def info_blob(r, loc=0, species=0, active=1, incombat=1, hp=100, hcond=0, senses=50, blind=0,
              threat=None, end=0x250):
    """W8MonsterInfo bytes 0..end: the fields below, random filler from +0x16 on, pointer
    fields (p3D +0xc, pCombat +0x10) zero - wired with setp when needed."""
    b = Blob(bytes(end))
    b[0x16:end] = filler(r, end - 0x16)
    b.u32(MI_LOC, loc)
    b.u32(MI_GROUP, r.getrandbits(12))
    b.u32(MI_SPECIES, species)
    b.u8(MI_ACTIVE, active)
    b.u8(MI_INCOMBAT, incombat)
    b.u32(MI_HP, hp)
    if end > MI_BLIND + 4:
        b.u32(MI_BLIND, blind)
    if end > MI_HCOND + 4:
        b.u32(MI_HCOND, hcond)
    if end > MI_SENSES:
        b.u8(MI_SENSES, senses)
    if threat is not None:
        b.u8(MI_THREAT, threat)
    return trim(b)


def p3d_blob(r, pos, yaw, radius, height, loc):
    """W8Monster window +0xec..+0x1e8, random filler around the fields read."""
    b = Blob(filler(r, M3_WIN_END - M3_WIN))
    b.f32(M3_YAW - M3_WIN, yaw)
    for k in range(3):
        b.f32(M3_POS - M3_WIN + 4 * k, pos[k])
    b.f32(M3_RADIUS - M3_WIN, radius)
    b.f32(M3_HEIGHT - M3_WIN, height)
    b.u32(M3_REP - M3_WIN, 0)
    b.u32(M3_LOC - M3_WIN, loc)
    return bytes(b)


def vis_record(r, about, clock, state=None):
    b = Blob(filler(r, VR_SIZE))
    b.u32(VR_ABOUT, about)
    if state is None:
        state = pick(r, [(35, 0), (30, 1), (25, 2), (10, lambda: r.choice([3, 0x80, 0xff]))])
    b.u8(VR_STATE, state)
    last = pick(r, [(30, 0),
                    (45, lambda: (clock - r.choice([0, 1, 0x77, 0x78, 0x79, 0xef, 0xf0, 0xf1,
                                                    0x100, r.randrange(0, 5000)])) & 0xffffffff),
                    (25, lambda: r.getrandbits(32))])
    b.u32(VR_LAST, last)
    return bytes(b)


def wire_world(ctx, c, far):
    """g_world and g_secondary_world -> scratch world whose camera far clip is `far`."""
    W = ctx.scratch(S_WORLD)
    c.setp(W + WORLD_CAMERA, W + CAM_OFF)
    c.set(W + CAM_OFF + CAM_NEAR, f64b(62.5) + f64b(far))
    c.setp(ctx.g('g_world'), W)
    c.setp(ctx.g('g_secondary_world'), W)


def plist(c, hdr, data, entries, count=None, capacity=None):
    """W8PList {data, capacity, iNumUsed}; entries: Addr or None (NULL slot)."""
    for k, a in enumerate(entries):
        if a is not None:
            c.setp(data + 4 * k, a)
    if count is None:
        count = len(entries)
    if capacity is None:
        capacity = len(entries) + 8
    c.setp(hdr, data)
    c.set(hdr + 4, struct.pack('<ii', capacity, count))


def wire_monster_lists(ctx, c, main, unborn=None):
    M = ctx.scratch(S_MON)
    gx = ctx.g('gXStatus')
    plist(c, M + ML_MAIN, M + ML_MAIN + 0x10, main)
    c.setp(gx + GX_MONLIST, M + ML_MAIN)
    if unborn is not None:
        plist(c, M + ML_UNBORN, M + ML_UNBORN + 0x10, unborn)
        c.setp(gx + GX_UNBORN, M + ML_UNBORN)


class Records:
    """gXStatus.monster_record_cache[990 + k] -> scratch W8MonsterRecord k."""

    def __init__(self, ctx, c, r):
        self.c = c
        self.r = r
        self.R = ctx.scratch(S_REC)
        self.gx = ctx.g('gXStatus')
        self.n = 0

    def add(self, kind, camo, level):
        species = SPECIES_BASE + self.n
        a = self.R + self.n * REC_STRIDE
        self.n += 1
        b = Blob(filler(self.r, REC_WIN_END - REC_WIN))
        b.u8(REC_KIND - REC_WIN, kind)
        b.u8(REC_CAMO - REC_WIN, camo)
        b.u8(REC_LEVEL - REC_WIN, level)
        self.c.set(a + REC_WIN, bytes(b))
        self.c.setp(self.gx + GX_RECCACHE + 4 * species, a)
        return species


def heading(obs, tgt):
    """GetHeadingAngle: atan2(dx, dz)."""
    return math.atan2(tgt[0] - obs[0], tgt[2] - obs[2])


# ----------------------------------------------------------------------------- spec
def cases(ctx):
    _threshold(ctx)
    _can_see(ctx)
    _visible_under(ctx)
    _has_projectile_origin(ctx)
    _spell_sight_index(ctx)
    _sight_range_overridden(ctx)
    _find_m2m(ctx)
    _group_threat(ctx)
    _group_can_see(ctx)
    _update_sight(ctx)
    _refresh_inward(ctx)
    _age_all(ctx)


# ----------------------------------------------------------------------------- ComputeSightThreshold
FAR_EDGE = [0.0, -0.0, -1.0, -12000.0, 1e-50, 1e-300, -1e-50, 1e-3, 0.5, 1.0, 3.0e38, 1e39,
            1e300, INF, NAN]
PERC_EDGE = [0, 1, 2, 125, 126, 255, 256, 0x7fffffff, 0x80000000, 0x80000001, 0xfffffffe,
             0xffffffff]
PSRC_EDGE = [0, -1, -2, 9999, 255, 1000000, 0x3fffffff, 0x40000000, 0x7fffffff, -0x80000000]
PMOD_EDGE = [-1, -10, 255, 0x0ccccccd, 0x1999999a, 0x33333334, 0x7fffffff, -0x80000000,
             0x80000001]
RB_EDGE = [0x7e, 0x80, 0xfe, 0xff, 0x100, 0x17d, 0xabcd0010, 0xffffff01]
FOV_EDGE = [3, 0xff, 0x100, -1, 0x80000000]
OVR_EDGE = [2, 0xff, 0x100, 0xffffff00, 0x12340001]
BOOL_ARG_EDGE = [2, 0x80, 0xff, 0x100, 0xffff0000]
FACTORS = [0, 1, 2, 3, 33, 34, 49, 50, 51, 99, 100, 101, 1000, 0x7fffffff, 0x80000000,
           0x80000001, 0xfffffffe, 0xffffffff]


def _threshold_real(r, vd_real):
    obs = (r.uniform(-20000, 20000), r.uniform(-600, 600), r.uniform(-20000, 20000))
    reach = vd_real * r.uniform(0.0, 1.4)
    ang = r.uniform(-PI, PI)
    tgt = (obs[0] + reach * math.sin(ang), obs[1] + r.uniform(-400, 400),
           obs[2] + reach * math.cos(ang))
    yaw = ang + (r.uniform(-PI / 2, PI / 2) if r.random() < 0.35 else r.uniform(-PI, PI))
    geo = math.sqrt(sum((a - b) ** 2 for a, b in zip(obs, tgt)))
    dist = max(0.0, geo - r.uniform(0, 200)) if r.random() < 0.7 else r.uniform(0, 1.4 * vd_real)
    return {
        'obs': obs, 'tgt': tgt, 'yaw': yaw, 'dist': dist,
        'perc': pick(r, [(90, lambda: r.randrange(1, 126)), (10, lambda: r.randrange(0, 256))]),
        'rb': pick(r, [(50, 0), (40, lambda: r.randrange(1, 0x7e)),
                       (10, lambda: r.randrange(0x7e, 0x100))]),
        'blind': 1 if r.random() < 0.12 else 0,
        'ext': 1 if r.random() < 0.15 else 0,
        'psrc': pick(r, [(85, lambda: r.randrange(1, 51)), (10, 9999),
                         (5, lambda: r.randrange(51, 256))]),
        'pmod': pick(r, [(50, 0), (30, lambda: r.randrange(1, 11)),
                         (20, lambda: r.randrange(11, 256))]),
        'fov': pick(r, [(80, 0), (12, 1), (8, 2)]),
        'ovr': 1 if r.random() < 0.08 else 0,
    }


def _threshold_edge(r, p, vd):
    key = r.choice(['perc', 'perc', 'rb', 'blind', 'ext', 'psrc', 'psrc', 'pmod', 'pmod', 'fov',
                    'ovr', 'dist', 'dist', 'dist', 'yaw', 'pos'])
    if key == 'perc':
        p['perc'] = r.choice(PERC_EDGE + [(2 * p['psrc'] + d) & 0xffffffff for d in (-1, 0, 1)])
    elif key == 'rb':
        p['rb'] = r.choice(RB_EDGE)
    elif key == 'blind':
        p['blind'] = r.choice(BOOL_ARG_EDGE)
    elif key == 'ext':
        p['ext'] = r.choice(BOOL_ARG_EDGE)
        p['blind'] = r.choice([0, 1])
    elif key == 'psrc':
        p['psrc'] = r.choice(PSRC_EDGE)
    elif key == 'pmod':
        p['pmod'] = r.choice(PMOD_EDGE)
    elif key == 'fov':
        p['fov'] = r.choice(FOV_EDGE)
    elif key == 'ovr':
        p['ovr'] = r.choice(OVR_EDGE)
    elif key == 'dist':
        cand = [0.0, -0.0, 1e-40, 1e-30, 1e-6, 0.5, -1.0, -5000.0, 3.0e38, INF]
        if math.isfinite(vd) and abs(vd) < 1e30:
            cand += [vd, vd * 0.5, vd * 2.0, fr(vd) + 1.0, vd * 1e-9]
        p['dist'] = r.choice(cand)
    elif key == 'yaw':
        p['yaw'] = r.choice([0.0, PI, -PI, 2 * PI, -2 * PI, 20.0, -20.0, 7.0])
    else:
        mode = r.choice(['same', 'dz0', 'dx0'])
        o = p['obs']
        if mode == 'same':
            p['tgt'] = (o[0], o[1] + r.choice([0.0, 100.0]), o[2])
        elif mode == 'dz0':
            p['tgt'] = (o[0] + r.choice([-3000.0, 3000.0, 1e-3]), o[1], o[2])
        else:
            p['tgt'] = (o[0], o[1], o[2] + r.choice([-3000.0, 3000.0]))
    return key


def _threshold(ctx):
    """float ComputeSightThreshold(vec3 observer, vec3 target, float yaw, unsigned perception,
    unsigned char ranged_bonus, bool blinded, bool extended, int penalty_source,
    int penalty_modifier, int skip_fov, unsigned char sight_override, float distance)"""
    fn = ctx.fn(0x00505a40)
    for i in range(ctx.n(N_THRESHOLD)):
        r = ctx.rng('threshold', i)
        c = ctx.case('threshold.%d' % i, fn, conv='c', ret='f')
        mode = pick(r, [(45, 'real'), (40, 'edge'), (15, 'exact')])
        far = r.choice(FARS)
        edges = []
        if mode == 'edge' and r.random() < 0.2:
            far = r.choice(FAR_EDGE)
            edges.append('far')
        vd = fr(far)
        p = _threshold_real(r, far if math.isfinite(far) and 1.0 < far < 1e6 else 12000.0)
        if mode == 'edge':
            for _ in range(pick(r, [(60, 1), (30, 2), (10, 3)])):
                edges.append(_threshold_edge(r, p, vd))
        elif mode == 'exact':
            # target straight along an axis, distance an exact fraction of the far clip:
            # (vd - d) / d is exact, so the sight percent is factor * ratio exactly
            o = (r.choice([0.0, 1000.0, -2500.0, 12288.0]), r.choice([0.0, 64.0, -300.0]),
                 r.choice([0.0, -7000.0, 4096.0]))
            axis = r.choice(['z+', 'z-', 'x+', 'x-', 'same'])
            dd = vd * r.choice([0.5, 0.25, 1.0])
            off = {'z+': (0.0, 0.0, dd), 'z-': (0.0, 0.0, -dd), 'x+': (dd, 0.0, 0.0),
                   'x-': (-dd, 0.0, 0.0), 'same': (0.0, 0.0, 0.0)}[axis]
            p['obs'] = o
            p['tgt'] = (o[0] + off[0], o[1] + r.choice([0.0, 150.0]), o[2] + off[2])
            head = {'z+': 0.0, 'z-': PI, 'x+': PI / 2, 'x-': -PI / 2, 'same': -PI / 2}[axis]
            p['yaw'] = head + r.choice([0.0, 0.5, -0.5, 0.785398, fr(PI / 4), 0.79, 1.0, PI,
                                        PI, -PI / 2, 2.0])
            p['dist'] = vd * r.choice([0.5, 0.25, 0.125, 1.0, 2.0, 0.5])
            factor = r.choice(FACTORS)
            p['psrc'] = r.randrange(0, 60)
            p['perc'] = (factor + 2 * p['psrc']) & 0xffffffff
            p['fov'] = 0 if r.random() < 0.8 else 1
            p['ovr'] = 0 if r.random() < 0.9 else 1
            p['blind'] = 0 if r.random() < 0.9 else 1
            if r.random() < 0.3:
                p['rb'] = r.choice([0, 1, 0x7d, 0xff, 0x80])
            if r.random() < 0.3:
                p['pmod'] = r.choice([0, 1, 9, 10, 11, 20, -1, 0x7fffffff])
            edges.append('exact_factor=%d' % factor)
        wire_world(ctx, c, far)
        for v in p['obs']:
            c.arg(F32(v))
        for v in p['tgt']:
            c.arg(F32(v))
        c.arg(F32(p['yaw']))
        c.arg(p['perc'])
        c.arg(p['rb'])
        c.arg(p['blind'])
        c.arg(p['ext'])
        c.arg(p['psrc'])
        c.arg(p['pmod'])
        c.arg(p['fov'])
        c.arg(p['ovr'])
        c.arg(F32(p['dist']))
        c.note(far=fnote(far), mode=mode, perc=p['perc'], rb=p['rb'], blind=p['blind'],
               ext=p['ext'], psrc=p['psrc'], pmod=p['pmod'], fov=p['fov'], ovr=p['ovr'],
               yaw=fnote(fr(p['yaw'])), dist=fnote(fr(p['dist'])))
        if edges:
            c.note(edge=','.join(edges))
        done(c)


# ----------------------------------------------------------------------------- CanMonsterSeeMonster
def _pair_geometry(r, far, mode, base=(0.0, 0.0, 0.0), spread=20000.0, sp=100):
    """-> (pos_s, pos_t, yaw_s, yaw_t, radius_s, radius_t, height_s, height_t, info)."""
    hs, ht = q(r.uniform(0, 250)), q(r.uniform(0, 250))
    if mode == 'boundary':
        # target straight along +x: heading +pi/2 (dz == 0 branch), radii 0, so the
        # distance is exactly D; D = sp * vd / 100 is the float the x87 threshold
        # sp * vd * 0.01f (53-bit, slightly below D) rounds to
        d = sp * far / 100.0
        d = r.choice([d, d, d, d - 1.0, d + 1.0])
        o = (base[0] + q(r.uniform(-spread, spread) / 8), base[1] + q(r.uniform(-200, 200)),
             base[2] + q(r.uniform(-spread, spread) / 8))
        t = (o[0] + d, o[1] + q(r.uniform(-200, 200)), o[2])
        return o, t, fr(PI / 2), r.uniform(-PI, PI), 0.0, 0.0, hs, ht, 'boundary_d=%r_sp=%d' % (d, sp)
    o = (base[0] + q(r.uniform(-spread, spread)), base[1] + q(r.uniform(-300, 300)),
         base[2] + q(r.uniform(-spread, spread)))
    if mode == 'same':
        t = o
    else:
        reach = far * pick(r, [(60, lambda: r.uniform(0.0, 1.05)), (30, lambda: r.uniform(1.05, 1.6)),
                               (10, lambda: r.uniform(0.0, 0.1))])
        ang = r.uniform(-PI, PI)
        t = (q(o[0] + reach * math.sin(ang)), q(o[1] + r.uniform(-300, 300)),
             q(o[2] + reach * math.cos(ang)))
    head = heading(o, t)
    yaw_s = head + r.uniform(-0.7, 0.7) if r.random() < 0.5 else r.uniform(-PI, PI)
    yaw_t = r.uniform(-PI, PI)
    rs = 0.0 if r.random() < 0.1 else q(r.uniform(0, 150))
    rt = 0.0 if r.random() < 0.1 else q(r.uniform(0, 150))
    return o, t, yaw_s, yaw_t, rs, rt, hs, ht, mode


def _can_see(ctx):
    """bool CanMonsterSeeMonster(W8MonsterInfo* source, W8MonsterInfo* target,
    W8VisibilityRecord* record)"""
    fn = ctx.fn(0x005058a0)
    M = ctx.scratch(S_MON)
    P = ctx.scratch(S_P3D)
    vis = ctx.scratch(S_MISC)
    for i in range(ctx.n(N_CAN_SEE)):
        r = ctx.rng('canmonsterseemonster', i)
        c = ctx.case('canmonsterseemonster.%d' % i, fn, conv='c', ret='b')
        mode = pick(r, [(72, 'real'), (12, 'boundary'), (6, 'same'), (10, 'early')])
        far = r.choice(FARS)
        if mode != 'boundary' and r.random() < 0.03:
            far = r.choice([0.0, 1e-50, NAN])
        wire_world(ctx, c, far)
        recs = Records(ctx, c, r)
        kind_s, level_s, camo_s = gen_kind(r), gen_level(r), gen_camo(r)
        kind_t, level_t, camo_t = gen_kind(r), gen_level(r), gen_camo(r)
        hp_s = gen_hp(r)
        hcond_s = gen_hcond(r, 0xf)
        blind_s = gen_blind(r)
        senses_s = gen_senses(r)
        incombat_t = gen_bool(r, 0.5, 0.03)
        state = pick(r, [(50, 0), (25, 1), (15, 2), (10, lambda: r.choice([3, 0x80, 0xff]))])
        share = r.random() < 0.15
        sp = 100
        if mode == 'early':
            if r.random() < 0.5:
                hp_s = 0
            else:
                hcond_s = r.choice([0xf, 0x10, 0x12, 0x14] + COND_EDGE)
        elif mode == 'boundary':
            # 100% before the penalty (facing yaw, or skip_fov = sight_state 1); no ranged
            # bonus; penalty camouflage0 * -10 / -5 only when the target is not in combat
            share = False
            hp_s = r.randrange(1, 300)
            hcond_s = r.randrange(0, 0xf)
            kind_s = r.choice([0, 0, 12, 1, 3])
            blind_s = 0 if r.random() < 0.8 else 1
            if blind_s:
                kind_s = 12
            incombat_t = 1 if r.random() < 0.5 else 0
            camo_t = 0 if incombat_t else r.choice([0, 1, 2, 5])
            state = r.choice([0, 1])
            sp = max(2, min(100, 100 - camo_t * (10 if state == 0 else 5)))
        sp_s = recs.add(kind_s, camo_s, level_s)
        if share:
            sp_t, kind_t, level_t, camo_t = sp_s, kind_s, level_s, camo_s
        else:
            sp_t = recs.add(kind_t, camo_t, level_t)
        geo = _pair_geometry(r, far if math.isfinite(far) and far > 1.0 else 12000.0,
                             'real' if mode == 'early' else mode, sp=sp)
        pos_s, pos_t, yaw_s, yaw_t, rad_s, rad_t, h_s, h_t, ginfo = geo
        loc_s, loc_t = r.randrange(1, 4000), r.randrange(1, 4000)
        S, T = M, M + MI_STRIDE
        c.set(S, info_blob(r, loc=loc_s, species=sp_s, active=gen_bool(r, 0.9), incombat=gen_bool(r, 0.7),
                           hp=hp_s, hcond=hcond_s, senses=senses_s, blind=blind_s))
        c.set(T, info_blob(r, loc=loc_t, species=sp_t, active=gen_bool(r, 0.9), incombat=incombat_t,
                           hp=gen_hp(r), hcond=gen_hcond(r, 0xf), senses=gen_senses(r),
                           blind=gen_blind(r)))
        c.setp(S + MI_P3D, P)
        c.setp(T + MI_P3D, P + M3_STRIDE)
        c.set(P + M3_WIN, p3d_blob(r, pos_s, yaw_s, rad_s, h_s, loc_s))
        c.set(P + M3_STRIDE + M3_WIN, p3d_blob(r, pos_t, yaw_t, rad_t, h_t, loc_t))
        rec = Blob(filler(r, VR_SIZE))
        rec.u8(VR_STATE, state)
        c.set(vis, bytes(rec))
        c.arg(S)
        c.arg(T)
        c.arg(vis)
        c.cap(M, 2 * MI_STRIDE, 'infos')
        c.cap(P, 2 * M3_STRIDE, 'p3d')
        c.cap(vis, VR_SIZE, 'record')
        c.note(far=fnote(far), mode=ginfo, kind_s=kind_s, level_s=level_s, camo_t=camo_t,
               level_t=level_t, hp_s=hp_s, hcond_s=hcond_s, blind_s=blind_s, senses_s=senses_s,
               incombat_t=incombat_t, state=state)
        edges = []
        if hcond_s >= 0x80000000:
            edges.append('cond_negative')
        if mode == 'boundary':
            edges.append('x87_threshold')
        if far in (0.0, 1e-50) or far != far:
            edges.append('far')
        if incombat_t not in (0, 1):
            edges.append('bool_byte')
        if edges:
            c.note(edge=','.join(edges))
        done(c)


# ----------------------------------------------------------------------------- small helpers
def _row_byte(r):
    return pick(r, [(45, 0), (40, 1), (15, lambda: r.choice(BOOL_EDGE))])


def _visible_under(ctx):
    """bool IsVisibleUnderConditions(const W8MonsterInfo*, const W8VisibilityRecord*, int kind)"""
    fn = ctx.fn(0x00505dd0)
    M = ctx.scratch(S_MON)
    row = ctx.scratch(S_MISC)
    for i in range(ctx.n(N_VISIBLE)):
        r = ctx.rng('visibleunder', i)
        c = ctx.case('visibleunder.%d' % i, fn, conv='c', ret='b')
        if r.random() < 0.85:
            kind = i % 7
        else:
            kind = r.choice([-1, -2, 7, 8, 100, 0x7fffffff, -0x80000000, 0x80000004, 0xffffff00])
            kind &= 0xffffffff
        proj = gen_bool(r, 0.5, 0.15)
        spell = gen_bool(r, 0.5, 0.15)
        rb = Blob(filler(r, VR_SIZE))
        rb.u8(VR_STATE, pick(r, [(40, 0), (30, 1), (20, 2), (10, lambda: r.choice([3, 0x80, 0xff]))]))
        for off in (5, 6, 7, 8, VR_CAN_SEE, VR_LINE):
            rb.u8(off, _row_byte(r))
        c.set(row, bytes(rb))
        c.set(M + MI_HAS_PROJ - 1, bytes([r.getrandbits(8), proj, r.getrandbits(8), spell,
                                          r.getrandbits(8)]))
        null_row = r.random() < 0.06
        null_mon = kind not in (4, 5) and r.random() < 0.2
        c.arg(0 if null_mon else M)
        c.arg(0 if null_row else row)
        c.arg(kind)
        c.cap(row, VR_SIZE, 'row')
        c.note(kind=kind, proj=proj, spell=spell, null_row=int(null_row), null_mon=int(null_mon))
        if proj not in (0, 1) or spell not in (0, 1):
            c.note(edge='bool_byte')
        done(c)


def _has_projectile_origin(ctx):
    """bool MonsterHasProjectileOrigin(const W8MonsterInfo*)"""
    fn = ctx.fn(0x00505e60)
    M = ctx.scratch(S_MON)
    for i in range(ctx.n(N_HAS_PROJ)):
        r = ctx.rng('hasprojectileorigin', i)
        c = ctx.case('hasprojectileorigin.%d' % i, fn, conv='c', ret='b')
        v = pick(r, [(40, 0), (40, 1), (20, lambda: r.choice(BOOL_EDGE + [0x40, 0xfe]))])
        c.set(M + MI_HAS_PROJ - 2, bytes([r.getrandbits(8), r.getrandbits(8), v,
                                          r.getrandbits(8), r.getrandbits(8)]))
        c.arg(M)
        c.note(value=v)
        if v not in (0, 1):
            c.note(edge='bool_byte')
        done(c)


def _spell_sight_index(ctx):
    """char GetMonsterSpellSightIndex(const W8MonsterInfo*)"""
    fn = ctx.fn(0x00505e80)
    M = ctx.scratch(S_MON)
    for i in range(ctx.n(N_SPELL_INDEX)):
        r = ctx.rng('spellsightindex', i)
        c = ctx.case('spellsightindex.%d' % i, fn, conv='c', ret='i8')
        v = pick(r, [(40, 0), (40, 1), (20, lambda: r.choice(BOOL_EDGE + [0x7e, 0xfe]))])
        c.set(M + MI_HAS_SPELL - 2, bytes([r.getrandbits(8), r.getrandbits(8), v,
                                           r.getrandbits(8), r.getrandbits(8)]))
        c.arg(M)
        c.note(value=v)
        if v not in (0, 1):
            c.note(edge='bool_byte')
        done(c)


def _sight_range_overridden(ctx):
    """bool IsSightRangeOverridden(void): g_view_distance != 12.0f"""
    fn = ctx.fn(0x00504910)
    view = ctx.g('g_view_distance')
    raw = {'qnan': 0x7fc00000, 'neg_qnan': 0xffc00000, 'snan': 0x7fa00000, 'inf': 0x7f800000,
           'neg_inf': 0xff800000, 'max': 0x7f7fffff, 'denorm': 0x00000001, 'neg0': 0x80000000,
           'above': 0x41400001, 'below': 0x413fffff}
    for i in range(ctx.n(N_VIEW)):
        r = ctx.rng('sightrangeoverridden', i)
        c = ctx.case('sightrangeoverridden.%d' % i, fn, conv='c', ret='b')
        x = r.random()
        if x < 0.35:
            bits, label = 0x41400000, '12.0'
        elif x < 0.7:
            v = r.choice([1.0, 4.0, 6.0, 8.0, 10.0, 11.5, 12.5, 16.0, 24.0, 100.0, 0.0,
                          r.uniform(0.0, 40.0), -12.0])
            bits, label = struct.unpack('<I', struct.pack('<f', v))[0], fnote(fr(v))
        else:
            label = r.choice(sorted(raw))
            bits = raw[label]
        c.set(view, u32(bits))
        c.note(view=label, bits='%08x' % bits)
        if label in ('qnan', 'neg_qnan', 'snan'):
            c.note(edge='nan')
        done(c)


# ----------------------------------------------------------------------------- FindMonToMonVisibility
def _find_m2m(ctx):
    """W8VisibilityRecord* FindMonToMonVisibility(W8MonsterInfo* source, W8MonsterInfo* target)"""
    fn = ctx.fn(0x00505d20)
    M = ctx.scratch(S_MON)
    V = ctx.scratch(S_VIS)
    S, T = M, M + MI_STRIDE
    for i in range(ctx.n(N_FIND)):
        r = ctx.rng('findm2m', i)
        c = ctx.case('findm2m.%d' % i, fn, conv='c', ret='p', out='p')
        tloc = pick(r, [(85, lambda: r.randrange(1, 5000)),
                        (15, lambda: r.choice([0, -1, -3, 0x7fffffff, -0x80000000]))])
        sloc = r.randrange(1, 5000)
        s_act = gen_bool(r, 0.92, 0.03)
        t_act = gen_bool(r, 0.92, 0.03)
        c.set(S, info_blob(r, loc=sloc, active=s_act, end=0x30))
        c.set(T, info_blob(r, loc=tloc, active=t_act, end=0x30))
        n = r.randrange(0, 11)
        nmatch = pick(r, [(30, 0), (50, 1), (20, 2)]) if n else 0
        match_at = set(r.sample(range(n), min(nmatch, n)))
        entries = []
        for j in range(n):
            if j not in match_at and r.random() < 0.1:
                entries.append(None)
                continue
            if j in match_at:
                about = tloc
            else:
                about = pick(r, [(70, lambda: r.randrange(1, 5000)),
                                 (30, lambda: r.choice([tloc + 1, tloc - 1, tloc ^ 0x80000000,
                                                        ~tloc, tloc + 0x100000000, 0]))])
                if (about - tloc) % 0x100000000 == 0:
                    about = tloc + 7
            a = V + VS_REC + VS_REC_STEP * j
            c.set(a, vis_record(r, about & 0xffffffff, 1000000))
            entries.append(a)
        lmode = pick(r, [(85, 'normal'), (5, 'null'), (10, 'count')])
        count = None
        if lmode == 'count':
            count = r.choice([-1, -5, -0x80000000, n + 3, 0])
        if lmode != 'null':
            plist(c, V, V + VS_DATA, entries, count=count)
            c.setp(S + MI_VISLIST, V)
        c.arg(S)
        c.arg(T)
        c.cap(V, 0x1000, 'vis')
        c.cap(M, 2 * MI_STRIDE, 'infos')
        c.note(n=n, matches=','.join(str(j) for j in sorted(match_at)),
               nulls=sum(1 for e in entries if e is None), list=lmode, count=count,
               s_active=s_act, t_active=t_act)
        if s_act not in (0, 1) or t_act not in (0, 1):
            c.note(edge='bool_byte')
        done(c)


# ----------------------------------------------------------------------------- groups
def _group_threat(ctx):
    """bool MonsterGroupHasVisibleThreat(W8MonsterGroup*)"""
    fn = ctx.fn(0x00505ea0)
    M = ctx.scratch(S_MON)
    P = ctx.scratch(S_P3D)
    G = ctx.scratch(S_GROUP)
    for i in range(ctx.n(N_THREAT)):
        r = ctx.rng('groupthreat', i)
        c = ctx.case('groupthreat.%d' % i, fn, conv='c', ret='b')
        n_main = r.randrange(1, 6)
        n_unb = min(pick(r, [(70, 0), (20, 1), (10, 2)]), 6 - n_main)
        total = n_main + n_unb
        locs = r.sample(range(1, 4000), total)
        desc = []
        edges = []
        for k in range(total):
            info = M + k * MI_STRIDE
            good = r.random() < 0.3
            active = 1 if good else gen_bool(r, 0.8, 0.04)
            hp = r.randrange(1, 600) if good else gen_hp(r)
            hcond = r.randrange(0, 0xc) if good else gen_hcond(r, 0xc)
            threat = 1 if good else pick(r, [(45, 1), (25, 0), (20, 2),
                                             (10, lambda: r.choice([3, 0x81, 0xff]))])
            cycle = r.choice([0, 1, 2, 5, 7, 0x14, 0x16, 0x95]) if good or r.random() < 0.85 \
                else 0x15
            pending = r.choice([0, 0xff, 3, 0x14, 0x16, 0x95]) if good or r.random() < 0.88 \
                else 0x15
            c.set(info, info_blob(r, loc=locs[k], active=active, incombat=gen_bool(r, 0.5),
                                  hp=hp, hcond=hcond, senses=gen_senses(r), blind=gen_blind(r),
                                  threat=threat, end=MI_VISLIST))
            has_p3d = active != 0 or r.random() < 0.5
            if has_p3d:
                p3d = P + k * M3_STRIDE
                rep = P + REP_BASE + k * REP_STEP
                c.setp(info + MI_P3D, p3d)
                c.setp(p3d + M3_REP, rep)
                c.set(rep + REP_CYCLE, bytes([cycle, r.getrandbits(8), r.getrandbits(8), pending]))
            desc.append('%d:a%x,h%x,c%x,t%x,cy%x,p%x%s%s' % (
                locs[k], active, hp, hcond, threat, cycle, pending, '' if has_p3d else ',nop3d',
                ',unborn' if k >= n_main else ''))
            if hcond >= 0x80000000:
                edges.append('cond_negative')
            if active not in (0, 1):
                edges.append('bool_byte')
        wire_monster_lists(ctx, c, [M + k * MI_STRIDE for k in range(n_main)],
                           [M + k * MI_STRIDE for k in range(n_main, total)])
        gb = Blob(filler(r, GR_SIZE))
        gb.u32(GR_MONSTERS, 0)
        c.set(G, bytes(gb))
        nids = pick(r, [(5, 0), (95, lambda: r.randrange(1, 7))])
        ids = [locs[r.randrange(total)] for _ in range(nids)]
        no_list = r.random() < 0.04
        if not no_list:
            c.setp(G + GR_MONSTERS, G + GR_ILIST)
            if ids:
                c.set(G + GR_IDATA, b''.join(struct.pack('<i', v) for v in ids))
            c.setp(G + GR_ILIST, G + GR_IDATA)
            c.set(G + GR_ILIST + 4, struct.pack('<ii', nids + 4, nids))
        c.arg(G)
        c.cap(M, total * MI_STRIDE, 'infos')
        c.cap(G, 0x600, 'group')
        c.note(monsters=';'.join(desc), ids=','.join(map(str, ids)), no_list=int(no_list))
        if edges:
            c.note(edge=','.join(sorted(set(edges))))
        done(c)


def _group_can_see(ctx):
    """bool MonsterGroupCanSeeGroup(W8MonsterGroup* source, W8MonsterGroup* target)"""
    fn = ctx.fn(0x00505f30)
    M = ctx.scratch(S_MON)
    P = ctx.scratch(S_P3D)
    V = ctx.scratch(S_VIS)
    G = ctx.scratch(S_GROUP)
    for i in range(ctx.n(N_GROUP_SEE)):
        r = ctx.rng('groupcansee', i)
        c = ctx.case('groupcansee.%d' % i, fn, conv='c', ret='b')
        combat = r.random() < 0.55
        n = r.randrange(2, 6)
        locs = r.sample(range(-600, -2), n)
        si = r.randrange(n)
        ti = si if r.random() < 0.05 else r.choice([k for k in range(n) if k != si])
        order = list(range(n))
        unborn = []
        if ti != si and r.random() < 0.1:
            order.remove(ti)
            unborn = [ti]
        for gaddr, leader in ((G, locs[si]), (G + GR_TARGET, locs[ti])):
            gb = Blob(filler(r, GR_SIZE))
            gb.u32(GR_MONSTERS, 0)
            gb.u32(GR_LEADER, leader)
            c.set(gaddr, bytes(gb))
        edges = []
        note = {}
        if combat:
            for k in range(n):
                act = gen_bool(r, 0.9, 0.03) if k in (si, ti) else gen_bool(r, 0.9)
                inc = gen_bool(r, 0.8)
                if k == ti:
                    inc = r.choice([1, 1, 1, 1, 2, 0xff])
                c.set(M + k * MI_STRIDE, info_blob(r, loc=locs[k], active=act, incombat=inc,
                                                   hp=gen_hp(r), end=0x110))
                if k in (si, ti):
                    note['active_%s' % ('s' if k == si else 't')] = act
                    if act not in (0, 1) or (k == ti and inc not in (0, 1)):
                        edges.append('bool_byte')
            nrec = r.randrange(0, 9)
            nmatch = pick(r, [(25, 0), (60, 1), (15, 2)]) if nrec else 0
            match_at = set(r.sample(range(nrec), min(nmatch, nrec)))
            entries, states = [], []
            for j in range(nrec):
                if j not in match_at and r.random() < 0.1:
                    entries.append(None)
                    continue
                about = locs[ti] if j in match_at else r.choice(
                    [loc for loc in locs if loc != locs[ti]] + [r.randrange(1, 3000), 0])
                a = V + VS_REC + VS_REC_STEP * j
                st = pick(r, [(45, 1), (25, 0), (20, 2), (10, lambda: r.choice([3, 0x81, 0xff]))])
                c.set(a, vis_record(r, about, 500000, state=st))
                entries.append(a)
                if j in match_at:
                    states.append(st)
            lmode = pick(r, [(90, 'normal'), (5, 'null'), (5, 'count')])
            if lmode != 'null':
                plist(c, V, V + VS_DATA, entries,
                      count=r.choice([-1, nrec + 2]) if lmode == 'count' else None)
                c.setp(M + si * MI_STRIDE + MI_VISLIST, V)
            c.cap(V, 0x1000, 'vis')
            note.update(nrec=nrec, matches=','.join(str(j) for j in sorted(match_at)),
                        match_states=','.join('%x' % s for s in states), list=lmode,
                        nulls=sum(1 for e in entries if e is None))
        else:
            far = r.choice(FARS)
            wire_world(ctx, c, far)
            recs = Records(ctx, c, r)
            gmode = pick(r, [(80, 'real'), (14, 'boundary'), (6, 'same')])
            if ti == si:
                gmode = 'same'
            kind_s, level_s, camo_s = gen_kind(r), gen_level(r), gen_camo(r)
            kind_t, level_t, camo_t = gen_kind(r), gen_level(r), gen_camo(r)
            hp_s = gen_hp(r)
            hcond_s = gen_hcond(r, 0xf)
            blind_s = gen_blind(r)
            if gmode == 'boundary':
                # sight_state 1 -> 100%; camouflage 0 -> no penalty; threshold vs D = far
                camo_t = 0
                hp_s = r.randrange(1, 300)
                hcond_s = r.randrange(0, 0xf)
                blind_s = 0
            sp_s = recs.add(kind_s, camo_s, level_s)
            sp_t = sp_s if ti == si else recs.add(kind_t, camo_t, level_t)
            geo = _pair_geometry(r, far, gmode, base=BASE, spread=far * 0.5, sp=100)
            pos_s, pos_t, yaw_s, yaw_t, rad_s, rad_t, h_s, h_t, ginfo = geo
            for k in range(n):
                if k == si:
                    blob = info_blob(r, loc=locs[k], species=sp_s, active=gen_bool(r, 0.9),
                                     incombat=gen_bool(r, 0.5), hp=hp_s, hcond=hcond_s,
                                     senses=gen_senses(r), blind=blind_s)
                elif k == ti:
                    blob = info_blob(r, loc=locs[k], species=sp_t, active=gen_bool(r, 0.9),
                                     incombat=0, hp=gen_hp(r), hcond=gen_hcond(r, 0xf),
                                     senses=gen_senses(r), blind=gen_blind(r))
                else:
                    blob = info_blob(r, loc=locs[k], active=gen_bool(r, 0.9),
                                     incombat=gen_bool(r, 0.5), end=0x30)
                c.set(M + k * MI_STRIDE, blob)
            c.setp(M + si * MI_STRIDE + MI_P3D, P)
            c.set(P + M3_WIN, p3d_blob(r, pos_s, yaw_s, rad_s, h_s, locs[si]))
            if ti != si:
                c.setp(M + ti * MI_STRIDE + MI_P3D, P + M3_STRIDE)
                c.set(P + M3_STRIDE + M3_WIN, p3d_blob(r, pos_t, yaw_t, rad_t, h_t, locs[ti]))
            c.cap(P, 2 * M3_STRIDE, 'p3d')
            note.update(far=fnote(far), geo=ginfo, kind_s=kind_s, level_s=level_s, camo_t=camo_t,
                        hp_s=hp_s, hcond_s=hcond_s)
            if hcond_s >= 0x80000000:
                edges.append('cond_negative')
            if gmode == 'boundary':
                edges.append('x87_threshold')
        wire_monster_lists(ctx, c, [M + k * MI_STRIDE for k in order],
                           [M + k * MI_STRIDE for k in unborn])
        c.arg(G)
        c.arg(G + GR_TARGET)
        c.cap(M, n * MI_STRIDE, 'infos')
        c.note(combat=int(combat), n=n, si=si, ti=ti, unborn_target=int(bool(unborn)), **note)
        if edges:
            c.note(edge=','.join(sorted(set(edges))))
        done(c)


# ----------------------------------------------------------------------------- mon-to-mon pass
def _m2m_setup(ctx, c, r, n, sources, combat, screen=SCREEN_MAIN, far=None, src_override=None,
               in_list=True):
    """n scratch monsters around BASE, wired as gXStatus.plsMonsterList; every monster in
    `sources` gets a populated visibility list (list slot = position in `sources`).
    Returns (cap ignore offsets for S4, description)."""
    M = ctx.scratch(S_MON)
    P = ctx.scratch(S_P3D)
    V = ctx.scratch(S_VIS)
    gx = ctx.g('gXStatus')
    gs = ctx.g('g_status')
    if far is None:
        far = r.choice(FARS)
    wire_world(ctx, c, far)
    c.set(ctx.g('g_current_screen_state'), u32(screen))
    c.set(gx + GX_COMBAT, u8(combat))
    clock = gen_clock(r)
    c.set(gs + GS_CLOCK, u32(clock))
    recs = Records(ctx, c, r)
    species = [recs.add(gen_kind(r), gen_camo(r), gen_level(r))
               for _ in range(r.randrange(1, 4))]
    total = n + (0 if in_list else 1)
    locs = r.sample(range(-600, -2), total)
    if total >= 3 and r.random() < 0.04:
        locs[2] = locs[1]
    vd = far if math.isfinite(far) and far > 1.0 else 12000.0
    spread = vd * r.choice([0.4, 0.6, 0.8, 1.1])
    pos = [(BASE[0] + q(r.uniform(-spread, spread)), BASE[1] + q(r.uniform(-300, 300)),
            BASE[2] + q(r.uniform(-spread, spread))) for _ in range(total)]
    radius = [0.0 if r.random() < 0.1 else q(r.uniform(0, 120)) for _ in range(total)]
    boundary = total >= 2 and r.random() < 0.08
    if boundary:
        # monster 1 exactly vd (or vd +- 1) from monster 0 along +x, radii 0
        d = vd + r.choice([0.0, 0.0, -1.0, 1.0])
        pos[1] = (pos[0][0] + d, pos[1][1], pos[0][2])
        radius[0] = radius[1] = 0.0
    desc = []
    for k in range(total):
        info = M + k * MI_STRIDE
        p3d = P + k * M3_STRIDE
        f = {'active': gen_bool(r, 0.9, 0.02), 'incombat': gen_bool(r, 0.85, 0.02),
             'hp': gen_hp(r), 'hcond': gen_hcond(r, 0xf), 'senses': gen_senses(r),
             'blind': gen_blind(r)}
        if src_override and k == sources[0]:
            f.update(src_override)
        if total > 1 and r.random() < 0.5:
            other = r.choice([j for j in range(total) if j != k])
            yaw = heading(pos[k], pos[other]) + r.uniform(-0.6, 0.6)
        else:
            yaw = r.uniform(-PI, PI)
        if boundary and k == 0:
            yaw = fr(PI / 2)
        c.set(info, info_blob(r, loc=locs[k], species=r.choice(species), active=f['active'],
                              incombat=f['incombat'], hp=f['hp'], hcond=f['hcond'],
                              senses=f['senses'], blind=f['blind']))
        c.setp(info + MI_P3D, p3d)
        c.set(p3d + M3_WIN, p3d_blob(r, pos[k], yaw, radius[k], q(r.uniform(0, 250)), locs[k]))
        desc.append('%d:a%x,c%x,h%x,k%x,s%d,b%x' % (locs[k], f['active'], f['incombat'], f['hp'],
                                                   f['hcond'], f['senses'], f['blind']))
    wire_monster_lists(ctx, c, [M + k * MI_STRIDE for k in range(n)])
    ignore = []
    for slot, s in enumerate(sources):
        hdr = V + 0x10 * slot
        data = V + VS_DATA + VS_DATA_STEP * slot
        abouts = [locs[k] for k in range(total) if k != s and r.random() < 0.85]
        if r.random() < 0.25:
            abouts.append(r.choice([r.randrange(1, 3000), -1, 0, -9999]))
        r.shuffle(abouts)
        entries = []
        for j, about in enumerate(abouts):
            a = V + VS_REC + VS_REC_STEP * (8 * slot + j)
            c.set(a, vis_record(r, about, clock))
            entries.append(a)
        if entries and r.random() < 0.04:
            entries.insert(r.randrange(len(entries) + 1), None)
        plist(c, hdr, data, entries, capacity=len(entries) + 8)
        c.setp(M + s * MI_STRIDE + MI_VISLIST, hdr)
        ignore += [VS_DATA + VS_DATA_STEP * slot + 4 * j
                   for j in range(len(entries), len(entries) + 8)]
    info = {'far': fnote(far), 'clock': clock, 'monsters': ';'.join(desc),
            'boundary': int(boundary)}
    return ignore, info


def _vis_floats(slots):
    out = []
    for slot in range(slots):
        for j in range(8):
            base = VS_REC + VS_REC_STEP * (8 * slot + j)
            out += [base + o for o in VR_FLOATS]
    return out


def _update_sight(ctx):
    """void UpdateMonsterSight(W8MonsterInfo*, bool direction, bool use_bounds): the
    monster-to-monster pass (direction false) and the early returns."""
    fn = ctx.fn(0x005049c0)
    M = ctx.scratch(S_MON)
    P = ctx.scratch(S_P3D)
    V = ctx.scratch(S_VIS)
    for i in range(ctx.n(N_UPDATE)):
        r = ctx.rng('updatemonstersight', i)
        c = ctx.case('updatemonstersight.%d' % i, fn, conv='c', ret='v')
        mode = pick(r, [(80, 'm2m'), (8, 'nocombat'), (12, 'early')])
        n = r.choice([1, 2, 2, 3, 3, 4, 4, 5, 6])
        in_list = not (mode == 'm2m' and r.random() < 0.05)
        s = r.randrange(n) if in_list else n
        combat = 1 if r.random() < 0.97 else r.choice([2, 0xff])
        screen = SCREEN_MAIN
        far = None
        override = None
        direction = 0
        edges = []
        if mode == 'nocombat':
            combat = 0
            if r.random() < 0.35:
                far = r.choice([0.0, 1e-50, 1e-300, NAN, -5.0])
                edges.append('far')
        elif mode == 'early':
            which = r.choice(['screen', 'inactive', 'hp0'])
            direction = r.choice([0, 1])
            if which == 'screen':
                screen = r.choice([0, 3, 6, 8, 0x107])
            elif which == 'inactive':
                override = {'active': 0}
            else:
                override = {'hp': 0}
            edges.append('early_' + which)
        elif r.random() < 0.04:
            far = r.choice([0.0, 1e-50])
            edges.append('far')
        ignore, info = _m2m_setup(ctx, c, r, n, [s], combat, screen=screen, far=far,
                                  src_override=override, in_list=in_list)
        c.arg(M + s * MI_STRIDE)
        c.arg(direction)
        c.arg(r.choice([0, 1]))
        c.cap(V, VS_REC + 8 * VS_REC_STEP, 'vis', ignore=ignore, floats=_vis_floats(1))
        c.cap(M, (n + 1) * MI_STRIDE, 'infos')
        c.cap(P, (n + 1) * M3_STRIDE, 'p3d')
        c.note(mode=mode, n=n, source=s, in_list=int(in_list), combat=combat, screen=screen,
               direction=direction, **info)
        if combat not in (0, 1):
            edges.append('bool_byte')
        if edges:
            c.note(edge=','.join(edges))
        done(c)


def _refresh_inward(ctx):
    """void RefreshInwardSightForAllMonsters(void)"""
    fn = ctx.fn(0x005057d0)
    M = ctx.scratch(S_MON)
    P = ctx.scratch(S_P3D)
    V = ctx.scratch(S_VIS)
    for i in range(ctx.n(N_INWARD)):
        r = ctx.rng('refreshinward', i)
        c = ctx.case('refreshinward.%d' % i, fn, conv='c', ret='v')
        n = r.choice([1, 2, 3, 3, 4, 4])
        combat = 1 if r.random() < 0.85 else 0
        ignore, info = _m2m_setup(ctx, c, r, n, list(range(n)), combat)
        c.cap(V, VS_REC + 8 * n * VS_REC_STEP, 'vis', ignore=ignore, floats=_vis_floats(n))
        c.cap(M, n * MI_STRIDE, 'infos')
        c.cap(P, n * M3_STRIDE, 'p3d')
        c.note(n=n, combat=combat, **info)
        done(c)


# ----------------------------------------------------------------------------- AgeAllMonsterSight
DEAD_CONDS = [0x12, 0x12, 0x13, 0x14, 0x15, 0x20, 0xff, 0x100, 0x7fffffff, 0x80000000,
              0xfffffffe, 0xffffffff]


def _age_steps(clock, sight):
    return (((clock * 1000) - (sight * 1000)) & 0xffffffff) // 120000


def _age_clock_pair(r):
    while True:
        x = r.random()
        if x < 0.5:
            clock = r.randrange(200, 30000000)
            sight = clock - r.choice([120, 121, 239, 240, 241, 600, 3600, r.randrange(120, 100000)])
        elif x < 0.7:
            clock, sight = r.getrandbits(32), r.getrandbits(32)
        elif x < 0.85:
            # around the 32-bit wrap of clock * 1000 (2^32 / 1000 = 4294967.296)
            clock = r.choice([4294967, 4294968, 4295087, 8589934, 8590054]) + r.randrange(-200, 200)
            sight = clock - r.randrange(0, 400)
        else:
            clock = r.randrange(0, 1000)
            sight = clock + r.randrange(1, 1000)       # sight clock ahead: unsigned wrap
        clock &= 0xffffffff
        sight &= 0xffffffff
        steps = _age_steps(clock, sight)
        if steps >= 1:
            return clock, sight, steps


def _age_all(ctx):
    """unsigned AgeAllMonsterSight(void) - only dead monsters (no AgeMonsterSight call)."""
    fn = ctx.fn(0x00504930)
    M = ctx.scratch(S_MON)
    gx = ctx.g('gXStatus')
    gs = ctx.g('g_status')
    for i in range(ctx.n(N_AGE)):
        r = ctx.rng('ageallmonstersight', i)
        c = ctx.case('ageallmonstersight.%d' % i, fn, conv='c', ret='i')
        n = r.choice([0, 1, 2, 3, 4, 5, 6])
        conds = [r.choice(DEAD_CONDS) for _ in range(n)]
        for k, cond in enumerate(conds):
            c.set(M + k * MI_STRIDE, info_blob(r, loc=r.randrange(1, 4000), active=gen_bool(r, 0.5),
                                               incombat=gen_bool(r, 0.5), hp=gen_hp(r),
                                               hcond=cond, end=0x110))
        null_list = n == 0 and r.random() < 0.3
        if null_list:
            c.set(gx + GX_MONLIST, u32(0))
        else:
            wire_monster_lists(ctx, c, [M + k * MI_STRIDE for k in range(n)])
        level = r.randrange(LEVEL_COUNT)
        clock, sight, steps = _age_clock_pair(r)
        c.set(gs + GS_LEVEL, u32(level))
        c.set(gs + GS_CLOCK, u32(clock))
        c.set(gs + GS_LP + level * GS_LP_ROW + GS_LP_SIGHT, u32(sight))
        c.cap(M, max(n, 1) * MI_STRIDE, 'infos')
        c.note(n=n, conds=','.join('%x' % v for v in conds), level=level, clock=clock,
               sight=sight, steps=steps, null_list=int(null_list))
        if any(v >= 0x80000000 for v in conds):
            c.note(edge='cond_negative')
        done(c)
