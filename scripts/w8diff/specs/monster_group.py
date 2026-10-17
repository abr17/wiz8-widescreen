"""MonsterGroup.cpp (src/wiz8/local_code/MonsterGroup.cpp): every recovered function of the
file; the testable ones run on a fake monster world built in scratch memory.

World (nothing depends on the live monsters of the loaded save):
  S0  W8PList headers wired into gXStatus.plsMonsterGroupList / plsMonsterGroupEncounterList /
      plsMonsterList / plsUnbornMonsterList (+ their pointer arrays), group member W8ILists,
      g_active_groups data
  S1  W8MonsterGroup records (stride 0x130)
  S2  W8MonsterInfo records (stride per function: only the fields the function reads)
  S3  fake W8Monster objects (p3D; only plain fields - no virtual call is reached)
  S4  fake W8MonsterRep (m_pRep: location +4, current_cycle +0xa4, pending_cycle +0xa7, which is
      all IsDying / MonsterGetLocation read)
  S5  W8MonsterRecord wired through gXStatus.monster_record_cache[species]
  S6  misc (caller file string, formation/centre vectors, g_npc_states vector + W8NpcState +
      W8NpcDatabaseRecord)
  S7  W8CombatState (g_combat_state) for CombatAllowsLiveGroups
  Members are found through MonsterGetIndexByLocationID (location ids), some members sit in the
  unborn list (index + 10000 path), and decoy infos precede them in the list. All set/setp ops
  stay below the core's 96-op limit (checked per case: extra ops would be dropped silently).
  RequestRedrawParty: g_level_block->redraw_flags is zeroed before the call and captured.

Tested (retail address, name, cases):
  0x005101b0 GetMonsterGroupByListIndex          250  both lists, null entries (asserts 0x3dc/0x3d1),
                                                      10000/20000 bias bounds, 0xffffffff
  0x005100b0 GetMonsterGroupIndexByID            250  duplicates, id in both lists, absent ids
                                                      (assert 0x3b2), assert flag bytes 2/0x100
  0x00510180 MonsterGroupGetRecord               150  scratch records + real MONSTERS.DBS species
  0x00510350 RecountActiveMonsterGroupMembers    250  highest_condition around 0x0d and negative as
                                                      int (retail compares unsigned), control_state
  0x00510b30 IsMonsterGroupLive                  250  + CombatAllowsLiveGroups inputs (round_count
                                                      0xffffffff: retail compares unsigned)
  0x00510ac0 GetLiveMonsterGroupAtIndex          250  negative / past-the-end index
  0x00510830 ReapplyMonsterGroupFormations       150  shared leaders, NaN/SNaN/denormal floats
                                                      (retail copies through fld/fstp, which
                                                      quiets an SNaN; the monster formation
                                                      fields are cap floats, so NaN vs NaN
                                                      of another payload is fp-noise)
  0x0050ff40 SetMonsterGroupFormation            200  null group, IList count -1 (signed loop)
  0x00510a10 RetireMonsterGroupAndAllies         200  leader chains through both lists, allies,
                                                      g_active_groups in scratch, combat budget
  0x00510280 GetMonsterGroupName                 250  name sets, record 397 (Al-<party name>),
                                                      unterminated names, real records
  0x0050f630 LoadMonsterGroupMembers             100  all members already active (no activation)
  0x00511530 ResetMonsterGroupTurnState          120
  0x005117d0 SetMonsterGroupControlState         200  dying members skipped, recount of the
                                                      member's own group
  0x00511b40 MonsterGroupHasRenderableMember     250  sector_mesh 0, member at the camera position
                                                      (copied from g_startup_world) or far away,
                                                      IsRenderable flags, camouflage records
  0x00511d40 MonsterGroupHasIncapacitatedMember  250  allied DAG recursion, condition band 0x0e..0x11
  0x0050ffd0 GetMonsterGroupCentre               250  unloaded group, empty group (0/0), null out
  0x00510b60 FindFirstMonsterByID                200
  0x00510bf0 FindNextExistingMonsterByID         300  previous last / in encounter list / in no list,
                                                      empty group list
  0x005103e0 ElectGroupLeaderMember              250  leadership_rank unsigned (negative ranks),
                                                      REMOVE_NOW members, location 0 fallback
  0x005118e0 MarkMonsterGroupForRemoval          200  allied DAG, missing members (assert 0x626)
  0x00511be0 SetMonsterGroupEngagementState      250  special species 0x1b6/0x234, tick wrap,
                                                      self/duplicate allies, state bytes 2/0x100
  0x00511cb0 GetMonsterGroupEngagementState      120
  0x00511ce0 SetMonsterGroupNavigatorDirty       150  flag bytes stored raw (2/0xff)
  0x00511850 MonsterGroupAllMembersDying         200
  0x00511250 MonsterGroupCalcDefaultDisposition  300  NPC path (g_npc_states in scratch, charm /
                                                      turncoat adjust, signed char bands, missing
                                                      binding assert 0x75d), unaligned radius,
                                                      party faction, g_factions score bands,
                                                      faction ints whose low byte is the index
  0x005113a0 RefreshMonsterGroupHostility        250  live-member walk, intelligence^2*60 cooldown,
                                                      unsigned clock wrap, faction band clock; the
                                                      leader's p3D carries hostility_preserved so
                                                      SetMonsterGroupHostility returns at once
  Total 5590 cases (markremoval/controlstate cases reach exactly 96 ops; Regions.fit merges
  set runs to stay inside the limit, finish() raises if a case would exceed it).
  Labels: note(edge=...) marks non-canonical bool bytes ('bool_byte', 'bool_arg'), negative-as-int
  conditions ('cond_negative'), signalling NaNs ('snan') and unterminated strings - a difference
  only in those cases points at bool normalisation / signedness / x87 copy semantics.

Skipped:
  0x00510cc0 MoveMonsterGroupToPosition     - octree placement (FindScatterPositions /
                                              FindNavigatorPosition), RemoveMonster, world moves
  0x0050f5d0 RemoveAllGroupMembers          - RemoveMonster destroys world monsters
  0x0050f6a0 ActivateGroupMembers           - ActivateMonster brings monsters into the world
  0x00510590 RefreshMonsterGroup            - navigator linking + virtual GetAnimationRadius on
                                              live Monsters (animation state)
  0x005106d0 RefreshMonsterGroupAndAllies   - same, plus PropagateGroupPosition
  0x0050f700 DetachMonsterGroup             - main effect SetTargetToGroup/ApplyTarget walks party
                                              actions (Targeting); only a flag write here
  0x0050fba0 ApplyToMonsterGroupLeader      - ConfigureMovementToPosition (navigator path planning)
  0x0050fad0 MonsterGroupLeaveCombat        - combat end (MonsterInfoLeaveCombat for each member)
  0x00510930 DespawnMonsterGroup            - removes groups and monsters from the world
  0x005115b0 RebindMonsterGroupScripts      - script objects (SetScript, stScript::getName)
  0x00510740 RepairMonsterGroupLeaderLinks  - every leading group goes to RefreshMonsterGroup
  0x0050fc20 LinkMonsterGroupToLeader       - RefreshMonsterGroup (navigators), hostility change,
                                              encounter registry
  0x0050f1a0 CreateGroup                    - allocates a group and creates world monsters
  0x0050f4a0 DestroyMonsterGroup            - frees a group, list removal, leader election
  0x005108c0 ApplyDefaultMonsterGroupSounds - SetScript("Default.MSF") on live monsters
  0x0050fd40 ElectAlliedLeaderGroup         - LinkMonsterGroupToLeader -> RefreshMonsterGroup
  0x0050f720 MonsterGroupEnterCombat        - combat start (MonsterInfoEnterCombat, ambush event)
  0x00511050 PositionMonsterGroupNearCamera - camera yaw, Random scatter, MoveMonsterGroupToPosition
  0x00511670 ShowMonsterGroupInfoNotice     - UI notices only
  0x00511990 GiveBirthToMonster             - moves world monsters to the live list, sight refresh
  0x00511a40 ReplaceMonsterGroupSpecies     - CreateGroup, Activate/DeactivateMonster
"""
import struct

from w8diff.api import Blob

MAX_OPS = 96          # W8D_MAX_OPS in w8diff_core.c (extra ops are silently dropped)
MAX_ARGS = 16

# --- gXStatus (layout.ps1) ---
GX_COMBAT = 0x8dc
GX_MONLIST = 0x8f5
GX_GROUPS = 0x8f9
GX_UNBORN = 0x901
GX_ENC = 0x905
GX_RECCACHE = 0xa0f

# --- g_status ---
GS_CLOCK = 0x18d8
GS_NAMEBUF = 0x2453
GS_NAMEBUF_LEN = 0x2c
GS_SEDEXUS = 0x247f
C_NAME = 0x5          # W8Character.name, 0x14 bytes

# --- W8MonsterGroup (packed, 0x12b) ---
G_SIZE = 0x12b
G_STRIDE = 0x130
G_ID = 0x00
G_COUNT = 0x04
G_LIST = 0x08
G_VISIBLE = 0x0c
G_SELECT = 0x10
G_ACTIVE = 0x14
G_MONID = 0x18
G_CENTRE = 0x1c
G_LOADED = 0x28       # members_active
G_INCOMBAT = 0x29
G_DISP = 0x2a
G_ALTNAME = 0x2c
G_HILITE = 0x9b
G_LEADER_LOC = 0x9f
G_LEADER_GRP = 0xa3
G_ALLIES = 0xa7
G_FORMATION = 0xb7
G_ENC_REG = 0xc3
G_ENGAGE = 0xc8
G_TICKS = 0xc9
G_HOST_AT = 0xcb
G_SPAWN = 0xcf        # spawn_time (next to hostility_set_at; must survive the turn reset)
G_ENC_ENDED = 0xd3

# --- W8MonsterInfo (packed, 0x425) ---
I_LOC = 0x00
I_GROUP = 0x04
I_SPECIES = 0x08
I_P3D = 0x0c
I_ACTIVE = 0x14
I_NOISE_POS = 0x37
I_NOISE_RAD = 0x43
I_TURNCOAT = 0x8b     # uiCondition[13]
I_HCOND = 0x107
I_VIEW = 0x24d        # within_viewing_distance
I_LOS1 = 0x28c        # party_threat.los_flags[1]
I_DETECTED = 0x28d    # party_threat.party_detected
I_THREAT_SEEN = 0x28e  # party_threat.last_seen_clock
I_VISIBLE = 0x2ab     # party_threat.visible_to_player
I_CHARM = 0x2de
I_NPC = 0x2f1         # bound_npc_index
I_CONTROL = 0x2fd
I_PV_SEEN = 0x354     # player_visibility.last_seen_clock

# --- W8Monster (0x348) ---
M_LINKED = 0x74       # W8Navigator::linked_navigator
M_DIRTY = 0xb4        # W8Navigator::position_dirty
M_RANK = 0xe0         # movement.leadership_rank
M_POS = 0x118         # movement.position (W8Navigator::GetPosition)
M_REP = 0x1d8         # m_pRep
M_FLAGS = 0x1dc       # runtime_flags
M_LOC = 0x1e4
M_INACTIVE = 0x215
M_DISABLED = 0x217
M_SCRIPT = 0x238
M_FORMATION = 0x280
M_SECTOR = 0x308      # sector_mesh
M_FADE = 0x330
M_PRESERVED = 0x332   # hostility_preserved
REMOVE_AFTER_FADE = 0x100
REMOVE_NOW = 0x200

# --- W8MonsterRep ---
R_LOC = 0x04
R_CYCLE = 0xa4
R_PENDING = 0xa7
CYCLE_DIE = 0x15

# --- W8MonsterRecord (0x297) ---
REC_STRIDE = 0x2a0
REC_NAMES = (0x000, 0x030, 0x060, 0x090)
REC_NPC_KIND = 0xcd
REC_FLAGS = 0xd0
REC_INT = 0xd2        # attribute_values[1]
REC_ID = 0x187
REC_CAMO = 0x248
REC_RADIUS = 0x25b
REC_FACTION = 0x25f
FLAG_NPC = 0x01
MONSTER_RECORDS = 595  # MONSTERS.DBS
ALT_NAME_RECORD = 397

# --- W8CombatState ---
CS_ROUND_COUNT = 0x4
CS_ENGAGED = 0xa54

# --- g_factions (W8FactionRuntimeRecord, packed 0xe) ---
FAC_STRIDE = 0xe
FAC_SCORE = 0x0
FAC_CLOCK = 0x6
FACTION_COUNT = 21

# --- NPC binding ---
NPC_RECORD = 0x06
NPC_LOC = 0x16
NPC_HAS_MON = 0x1a
NPC_DISP = 0x1b
NPC_PRESENT = 0x25
NPC_UNAVAIL = 0xc7
NPCREC_FACTION = 0x5f
VEC_COUNT = 0x4       # W8GrowableVector: vptr, count, capacity, data
VEC_DATA = 0xc

LB_REDRAW = 0xf4      # g_level_block->redraw_flags
AG_COUNT = 0x4        # g_active_groups count / data
AG_DATA = 0xc

# --- scratch ---
SB_LISTS, SB_GROUPS, SB_INFOS, SB_MONS, SB_REPS, SB_RECORDS, SB_MISC, SB_COMBAT = range(8)
L_MAIN, L_ENC, L_MON, L_UNBORN = 0x00, 0x10, 0x20, 0x30
L_MAIN_DATA, L_ENC_DATA, L_MON_DATA, L_UNBORN_DATA = 0x100, 0x200, 0x300, 0x500
L_ACTIVE_DATA = 0x600
L_IL_HDR = 0x800
L_IL_DATA = 0x1000
IL_STRIDE = 0x80
MISC_FILE = 0x000
MISC_VEC = 0x100      # formation argument
MISC_OUT = 0x200      # centre out-parameter
MISC_NPCVEC = 0x400
MISC_NPCDATA = 0x480
MISC_NPC = 0x500      # W8NpcState records, stride 0x140
MISC_NPCREC = 0xa00
FILE_STR = b'C:\\Projects\\Wizardry 8\\Local Code\\W8Diff.cpp\0'

BOOL_EDGE = [2, 0x80, 0xff]
COND_EDGE = [0x80000000, 0xffffffff, 0xfffffff0, 0x7fffffff, 0x100]
FLOAT_SPECIAL = [0x00000000, 0x80000000, 0x3f800000, 0xbf800000, 0x7f7fffff, 0xff7fffff,
                 0x00000001, 0x80000001, 0x00800000, 0x7f800000, 0xff800000, 0x7fc00000,
                 0xffc00000, 0x4b800000, 0x4b800001, 0x501502f9, 0xd01502f9]
SNAN = [0x7f800001, 0x7fa00000, 0xffbfffff]
NAMES = ['Gazer', 'Rattkin Thief', 'Sea Wyrm', 'Higardi Guard', 'Ooze', 'Umpani Trooper',
         'Moss Beast', 'Phantasm', 'Ghoul', 'Crab', 'Trynnie', 'X', '', 'Sirène', 'Ваш Урод',
         'Kraken Lord of the Deep', 'Spirit of the Abyss!!', 'Ab#cd', 'Dark Savant']
PARTY_NAMES = ['', 'A', 'Vi', 'Sexton', 'Rodan', 'Myles', 'Saxx', 'Vi Domina', 'Glumph',
               'Sparkle', 'Ёжик', 'RFS-81', 'Madras', 'Tantris']


# ------------------------------------------------------------------ helpers

def u8(v):
    return struct.pack('<B', v & 0xff)


def u32(v):
    return struct.pack('<I', v & 0xffffffff)


def fbits(r, special_p=0.1, span=5000.0, snan_p=0.0):
    x = r.random()
    if x < snan_p:
        return r.choice(SNAN)
    if x < snan_p + special_p:
        return r.choice(FLOAT_SPECIAL)
    return struct.unpack('<I', struct.pack('<f', r.uniform(-span, span)))[0]


def wstr(s, size, terminate=True):
    data = s.encode('utf-16-le')
    if terminate:
        data += b'\0\0'
    return data[:size] + bytes(max(0, size - len(data)))


def trim(data):
    data = bytes(data)
    end = len(data)
    while end and data[end - 1] == 0:
        end -= 1
    return data[:end]


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


def bool_byte(r, p_true, edge_p=0.05):
    if r.random() < p_true:
        return r.choice(BOOL_EDGE) if r.random() < edge_p else 1
    return 0


def hcond(r, edge_p=0.05):
    """highest_condition: mostly none, the enum around the thresholds, rarely values that are
    negative as int (retail compares them unsigned)."""
    x = r.random()
    if x < edge_p:
        return r.choice(COND_EDGE)
    if x < 0.5:
        return 0
    if x < 0.75:
        return r.randrange(1, 0x15)
    return r.choice([0x0c, 0x0d, 0x0e, 0x0f, 0x10, 0x11, 0x12, 0x13, 0x14])


def ucmp_lt(a, b):
    return (a & 0xffffffff) < (b & 0xffffffff)


def runs(data, gap=32):
    out = []
    n = len(data)
    k = 0
    while k < n:
        if data[k] == 0:
            k += 1
            continue
        s = k
        while k < n and data[k] != 0:
            k += 1
        if out and s - out[-1][1] < gap:
            out[-1][1] = k
        else:
            out.append([s, k])
    return out


class Regions:
    """Byte regions written with as few 'set' lines as the op budget allows: runs of non-zero
    bytes, the closest ones merged until the count fits."""

    def __init__(self):
        self.items = []

    def add(self, base, data, gap=32):
        rr = runs(bytes(data), gap)
        if rr:
            self.items.append([base, bytes(data), rr])

    def count(self):
        return sum(len(it[2]) for it in self.items)

    def fit(self, budget):
        while self.count() > budget:
            best = None
            for j, it in enumerate(self.items):
                rr = it[2]
                for q in range(len(rr) - 1):
                    g = rr[q + 1][0] - rr[q][1]
                    if best is None or g < best[0]:
                        best = (g, j, q)
            if best is None:
                raise ValueError('set ops do not fit the %d-op budget' % MAX_OPS)
            _, j, q = best
            rr = self.items[j][2]
            rr[q][1] = rr[q + 1][1]
            del rr[q + 1]

    def emit(self, c):
        for base, data, rr in self.items:
            for s, e in rr:
                c.set(base + s, data[s:e])


def finish(c):
    if len(c.ops) > MAX_OPS:
        raise ValueError('%s: %d ops > %d' % (c.id, len(c.ops), MAX_OPS))
    if len(c.args) > MAX_ARGS:
        raise ValueError('%s: %d args' % (c.id, len(c.args)))


class World:
    """Fake monster world in scratch (see the module docstring)."""

    def __init__(self, ctx, c, istride=0x18, mstride=0x1e0, rstride=0xb0):
        self.ctx = ctx
        self.c = c
        self.L = ctx.scratch(SB_LISTS)
        self.G = ctx.scratch(SB_GROUPS)
        self.I = ctx.scratch(SB_INFOS)
        self.M = ctx.scratch(SB_MONS)
        self.R = ctx.scratch(SB_REPS)
        self.gx = ctx.g('gXStatus')
        self.istride, self.mstride, self.rstride = istride, mstride, rstride
        self.groups = []
        self.main = []      # group indexes / None (null entry) / Addr
        self.enc = []
        self.infos = []
        self.monlist = []   # info indexes
        self.unborn = []
        self.mons = []
        self.reps = []

    # groups
    def group(self, gid, members=None, used=None):
        b = Blob(G_SIZE)
        b.u32(G_ID, gid)
        self.groups.append({'b': b, 'members': members, 'used': used})
        return len(self.groups) - 1

    def gb(self, k):
        return self.groups[k]['b']

    def ga(self, k):
        return self.G + k * G_STRIDE

    # monster infos
    def info(self, loc, mon=None):
        b = Blob(self.istride)
        b.u32(I_LOC, loc)
        self.infos.append({'b': b, 'mon': mon})
        return len(self.infos) - 1

    def ib(self, k):
        return self.infos[k]['b']

    def ia(self, k):
        return self.I + k * self.istride

    # fake W8Monster / rep
    def mon(self, rep=None):
        self.mons.append({'b': Blob(self.mstride), 'rep': rep, 'copy': []})
        return len(self.mons) - 1

    def mb(self, k):
        return self.mons[k]['b']

    def ma(self, k):
        return self.M + k * self.mstride

    def rep(self, cycle=0, pending=0xff, loc=None):
        b = Blob(self.rstride)
        if self.rstride > R_PENDING:
            b.u8(R_CYCLE, cycle)
            b.u8(R_PENDING, pending)
        if loc is not None:
            for j in range(3):
                b.u32(R_LOC + 4 * j, loc[j])
        self.reps.append(b)
        return len(self.reps) - 1

    def ra(self, k):
        return self.R + k * self.rstride

    def place(self, r, keys, unborn_p=0.0):
        """Put infos into the monster list (shuffled) or, rarely, the unborn list."""
        keys = list(keys)
        r.shuffle(keys)
        for k in keys:
            (self.unborn if r.random() < unborn_p else self.monlist).append(k)

    def _entry(self, e):
        if isinstance(e, int):
            return self.ga(e)
        return e

    def wire(self, reserve=0, lists=True):
        c = self.c
        setps = []
        regs = Regions()
        if lists:
            hdr = Blob(0x40)
            for off, entries in ((L_MAIN, self.main), (L_ENC, self.enc),
                                 (L_MON, self.monlist), (L_UNBORN, self.unborn)):
                hdr.u32(off + 4, max(10, len(entries)))
                hdr.u32(off + 8, len(entries))
            regs.add(self.L, hdr)
            for off, doff, entries, info in ((L_MAIN, L_MAIN_DATA, self.main, False),
                                             (L_ENC, L_ENC_DATA, self.enc, False),
                                             (L_MON, L_MON_DATA, self.monlist, True),
                                             (L_UNBORN, L_UNBORN_DATA, self.unborn, True)):
                if entries:
                    setps.append((self.L + off, self.L + doff))
                for k, e in enumerate(entries):
                    if e is None:
                        continue
                    setps.append((self.L + doff + 4 * k, self.ia(e) if info else self._entry(e)))
            for goff, loff in ((GX_GROUPS, L_MAIN), (GX_ENC, L_ENC), (GX_MONLIST, L_MON),
                               (GX_UNBORN, L_UNBORN)):
                setps.append((self.gx + goff, self.L + loff))
        if self.groups:
            data = bytearray(len(self.groups) * G_STRIDE)
            for k, g in enumerate(self.groups):
                data[k * G_STRIDE:k * G_STRIDE + G_SIZE] = g['b']
            regs.add(self.G, data)
        il_hdr = bytearray()
        il_data = bytearray()
        h = 0
        for k, g in enumerate(self.groups):
            mem = g['members']
            if mem is None:
                continue
            used = g['used'] if g['used'] is not None else len(mem)
            il_hdr += struct.pack('<IiI', 0, max(10, len(mem)), used & 0xffffffff) + bytes(4)
            blk = bytearray(IL_STRIDE)
            for j, v in enumerate(mem):
                struct.pack_into('<I', blk, 4 * j, v & 0xffffffff)
            il_data += blk
            ha = self.L + L_IL_HDR + 0x10 * h
            setps.append((self.ga(k) + G_LIST, ha))
            if mem:
                setps.append((ha, self.L + L_IL_DATA + IL_STRIDE * h))
            h += 1
        regs.add(self.L + L_IL_HDR, il_hdr)
        regs.add(self.L + L_IL_DATA, il_data)
        if self.infos:
            data = bytearray(len(self.infos) * self.istride)
            for k, inf in enumerate(self.infos):
                data[k * self.istride:(k + 1) * self.istride] = inf['b']
                if inf['mon'] is not None:
                    setps.append((self.ia(k) + I_P3D, self.ma(inf['mon'])))
            regs.add(self.I, data)
        if self.mons:
            data = bytearray(len(self.mons) * self.mstride)
            for k, m in enumerate(self.mons):
                data[k * self.mstride:(k + 1) * self.mstride] = m['b']
                if m['rep'] is not None:
                    setps.append((self.ma(k) + M_REP, self.ra(m['rep'])))
                for off, src in m['copy']:
                    setps.append((self.ma(k) + off, src))
            regs.add(self.M, data)
        if self.reps:
            data = bytearray(len(self.reps) * self.rstride)
            for k, b in enumerate(self.reps):
                data[k * self.rstride:(k + 1) * self.rstride] = b
            regs.add(self.R, data)
        budget = MAX_OPS - reserve - len(c.ops) - len(setps)
        regs.fit(budget)
        regs.emit(c)
        for a, v in setps:
            c.setp(a, v)

    # captures
    def cap_groups(self, name='groups', floats=()):
        n = len(self.groups)
        fl = [k * G_STRIDE + f for k in range(n) for f in floats]
        self.c.cap(self.G, n * G_STRIDE, name, ignore=[k * G_STRIDE + G_LIST for k in range(n)],
                   floats=fl)

    def cap_infos(self, name='infos'):
        n = len(self.infos)
        self.c.cap(self.I, n * self.istride, name,
                   ignore=[k * self.istride + I_P3D for k in range(n)])

    def cap_mons(self, name='monsters', floats=()):
        n = len(self.mons)
        self.c.cap(self.M, n * self.mstride, name,
                   ignore=[k * self.mstride + M_REP for k in range(n)],
                   floats=[k * self.mstride + f for k in range(n) for f in floats])


class Records:
    """gXStatus.monster_record_cache[species] -> scratch W8MonsterRecord."""

    def __init__(self, ctx, c):
        self.c = c
        self.R = ctx.scratch(SB_RECORDS)
        self.gx = ctx.g('gXStatus')
        self.by_species = {}

    def get(self, species, blob):
        if species in self.by_species:
            return self.by_species[species]
        a = self.R + len(self.by_species) * REC_STRIDE
        self.by_species[species] = a
        regs = Regions()
        regs.add(a, blob, gap=48)
        regs.emit(self.c)
        self.c.setp(self.gx + GX_RECCACHE + 4 * species, a)
        return a


def record_blob(r, species, names=True):
    b = Blob(REC_STRIDE)
    if names:
        for off in REC_NAMES:
            b[off:off + 0x30] = wstr(r.choice(NAMES), 0x30)
    struct.pack_into('<h', b, REC_ID, species)
    return b


def redraw(ctx, c):
    lb = ctx.g('g_level_block').deref() + LB_REDRAW
    c.set(lb, u32(0))
    return lb


def combat(ctx, c, r):
    """gXStatus.fCombatMode + scratch g_combat_state (enemies_engaged, round_count)."""
    S = ctx.scratch(SB_COMBAT)
    c.setp(ctx.g('g_combat_state'), S)
    mode = pick(r, [(40, 0), (55, 1), (5, lambda: r.choice(BOOL_EDGE))])
    engaged = pick(r, [(70, 0), (25, 1), (5, lambda: r.choice(BOOL_EDGE))])
    rc = pick(r, [(30, 0), (30, 1), (25, lambda: r.randrange(2, 12)),
                  (15, lambda: r.choice([0xffffffff, 0x80000000, 0x7fffffff, 0x100000001 & 0xffffffff]))])
    c.set(ctx.g('gXStatus') + GX_COMBAT, u8(mode))
    if rc:
        c.set(S + CS_ROUND_COUNT, u32(rc))
    if engaged:
        c.set(S + CS_ENGAGED, u8(engaged))
    return mode, engaged, rc


def live_fields(r, b):
    """members_active / fInCombat / member_count / ubDisposition for IsMonsterGroupLive."""
    edges = []
    loaded = bool_byte(r, 0.8)
    inc = bool_byte(r, 0.75)
    count = pick(r, [(15, 0), (70, lambda: r.randrange(1, 10)),
                     (15, lambda: r.choice([0x80000000, 0xffffffff, 0x100, 0x7fffffff]))])
    disp = pick(r, [(30, 0), (35, 1), (25, 2), (10, lambda: r.choice([3, 0x80, 0xff]))])
    if loaded not in (0, 1) or inc not in (0, 1):
        edges.append('bool_byte')
    b.u8(G_LOADED, loaded)
    b.u8(G_INCOMBAT, inc)
    b.u32(G_COUNT, count)
    b.u8(G_DISP, disp)
    return edges


def ids_for(r, n, lo=1, hi=4000):
    return r.sample(range(lo, hi), n)


def dag_allies(r, w, gidx, ids, p=0.5):
    """Allies only point at later groups, so the recursion is a DAG and terminates."""
    for a, k in enumerate(gidx):
        later = gidx[a + 1:]
        for s in range(4):
            if later and r.random() < p:
                w.gb(k).u32(G_ALLIES + 4 * s, ids[r.choice(later)])


def rep_state(r, dying_p=0.25):
    """(current_cycle, pending_cycle, dying) for IsDying."""
    if r.random() < dying_p:
        if r.random() < 0.5:
            return CYCLE_DIE, r.choice([0xff, 0, 3, CYCLE_DIE]), True
        return r.choice([0, 1, 2, 7, 0x14, 0x16]), CYCLE_DIE, True
    cyc = r.choice([0, 1, 2, 3, 7, 13, 17, 0x14, 0x16, 0x19, 0x95, 0xff])
    pend = r.choice([0xff, 0xff, 0, 1, 0x14, 0x16, 0x95])
    return cyc, pend, False


# ------------------------------------------------------------------ list lookups

def gen_by_list_index(ctx):
    fn = ctx.fn(0x005101b0)  # W8MonsterGroup* GetMonsterGroupByListIndex(unsigned int)
    for i in range(ctx.n(250)):
        r = ctx.rng('bylistindex', i)
        c = ctx.case('bylistindex.%d' % i, fn, conv='c', ret='p', out='p')
        w = World(ctx, c)
        ng = pick(r, [(1, 0), (2, 1), (7, lambda: r.randrange(2, 10))])
        ne = pick(r, [(3, 0), (2, 1), (5, lambda: r.randrange(2, 8))])
        ids = ids_for(r, ng + ne)
        w.main = [w.group(ids[k]) for k in range(ng)]
        w.enc = [w.group(ids[ng + k]) for k in range(ne)]
        edge = []
        null_main = null_enc = None
        if ng and r.random() < 0.1:
            null_main = r.randrange(ng)
            w.main[null_main] = None
            edge.append('null_main')
        if ne and r.random() < 0.1:
            null_enc = r.randrange(ne)
            w.enc[null_enc] = None
            edge.append('null_enc')
        if null_main is not None and r.random() < 0.6:
            idx = null_main
        elif null_enc is not None and r.random() < 0.6:
            idx = 10000 + null_enc
        else:
            idx = pick(r, [
                (40, lambda: r.randrange(ng) if ng else 0),
                (25, lambda: 10000 + (r.randrange(ne) if ne else 0)),
                (35, lambda: r.choice([ng, ng + 1, 9999, 10000 + ne, 10001 + ne, 19999, 20000,
                                       20000 + r.randrange(max(ng, 1)), 0xffffffff, 0x80000000,
                                       0x7fffffff, 0, 10000, 0xffffd8f0]))])
        w.wire()
        c.arg(idx)
        c.note(main=ng, enc=ne, index=idx)
        if edge:
            c.note(edge=','.join(edge))
        finish(c)


def gen_index_by_id(ctx):
    fn = ctx.fn(0x005100b0)  # unsigned GetMonsterGroupIndexByID(int line, const char*, int id, bool)
    M = ctx.scratch(SB_MISC)
    special = [0, -1, 0x7fffffff, -0x80000000, -5]
    for i in range(ctx.n(250)):
        r = ctx.rng('indexbyid', i)
        c = ctx.case('indexbyid.%d' % i, fn, conv='c', ret='i')
        w = World(ctx, c)
        ng = pick(r, [(1, 0), (2, 1), (7, lambda: r.randrange(2, 10))])
        ne = pick(r, [(3, 0), (2, 1), (5, lambda: r.randrange(2, 8))])
        n = ng + ne
        ids = ids_for(r, n, 1, 3000)
        if n and r.random() < 0.15:
            ids[r.randrange(n)] = r.choice(special)
        if n >= 2 and r.random() < 0.25:
            a, b = r.sample(range(n), 2)
            ids[b] = ids[a]
        w.main = [w.group(ids[k]) for k in range(ng)]
        w.enc = [w.group(ids[ng + k]) for k in range(ne)]
        mode = pick(r, [(40, 'main'), (25, 'enc'), (25, 'absent'), (10, 'special')])
        if mode == 'main' and ng:
            gid = ids[r.randrange(ng)]
        elif mode == 'enc' and ne:
            gid = ids[ng + r.randrange(ne)]
        elif mode == 'special':
            gid = r.choice(special)
        else:
            gid = r.randrange(3000, 6000)
        flag = pick(r, [(60, 1), (30, 0), (10, lambda: r.choice([2, 0xff, 0x100, 0x101]))])
        line = r.choice([0x3b2, 0x75a, r.randrange(0, 0x1000), 0xffffffff])
        c.set(M + MISC_FILE, FILE_STR)
        w.wire()
        c.arg(line)
        c.arg(M + MISC_FILE)
        c.arg(gid)
        c.arg(flag)
        c.note(main=ng, enc=ne, mode=mode, id=gid, flag=flag)
        if flag not in (0, 1):
            c.note(edge='bool_arg')
        finish(c)


def gen_get_record(ctx):
    fn = ctx.fn(0x00510180)  # W8MonsterRecord* MonsterGroupGetRecord(W8MonsterGroup*)
    for i in range(ctx.n(150)):
        r = ctx.rng('getrecord', i)
        c = ctx.case('getrecord.%d' % i, fn, conv='c', ret='p', out='p')
        w = World(ctx, c)
        k = w.group(r.randrange(1, 3000))
        if r.random() < 0.65:
            species = pick(r, [(8, lambda: r.randrange(0, MONSTER_RECORDS)),
                               (2, lambda: r.randrange(MONSTER_RECORDS, 1000)),
                               (1, lambda: r.choice([0, 999, 594, 595]))])
            Records(ctx, c).get(species, record_blob(r, species))
            mode = 'scratch'
        else:
            species = r.choice([0, 1, ALT_NAME_RECORD, 594, r.randrange(MONSTER_RECORDS),
                                r.randrange(MONSTER_RECORDS)])
            mode = 'real'
        w.gb(k).u32(G_MONID, species)
        w.gb(k).u32(G_COUNT, r.randrange(1, 9))
        w.wire(lists=False)
        c.arg(w.ga(k))
        c.note(species=species, mode=mode)
        finish(c)


# ------------------------------------------------------------------ member walks

def gen_recount(ctx):
    fn = ctx.fn(0x00510350)  # void RecountActiveMonsterGroupMembers(W8MonsterGroup*)
    for i in range(ctx.n(250)):
        r = ctx.rng('recount', i)
        c = ctx.case('recount.%d' % i, fn, conv='c', ret='v')
        w = World(ctx, c, istride=0x308)
        n = pick(r, [(1, 0), (2, 1), (10, lambda: r.randrange(2, 11))])
        locs = ids_for(r, n + 4, 1, 9000)
        members = locs[:n]
        if n >= 2 and r.random() < 0.06:
            members[r.randrange(1, n)] = members[0]
        edges = []
        state = {}
        keys = []
        for loc in members:
            if loc in state:
                continue
            k = w.info(loc)
            hc = hcond(r, 0.06)
            cs = pick(r, [(50, 0), (25, 1), (15, 2),
                          (10, lambda: r.choice([3, 0xffffffff, 0x101, 0x80000000]))])
            w.ib(k).u32(I_HCOND, hc)
            w.ib(k).u32(I_CONTROL, cs)
            if hc >= 0x80000000:
                edges.append('cond_negative')
            state[loc] = (hc, cs)
            keys.append(k)
        for j in range(r.randrange(0, 4)):
            k = w.info(locs[n + j])
            w.ib(k).u32(I_HCOND, hcond(r))
            w.ib(k).u32(I_CONTROL, r.choice([0, 1, 2]))
            keys.append(k)
        w.place(r, keys, unborn_p=0.1)
        expected = sum(1 for loc in members if ucmp_lt(state[loc][0], 0x0d) and state[loc][1] != 1)
        init = pick(r, [(40, expected), (40, lambda: r.randrange(0, 11)),
                        (20, lambda: r.choice([0xffffffff, 0x7fffffff, expected + 1]))])
        g = w.group(r.randrange(1, 3000), members=members)
        w.gb(g).u32(G_COUNT, n)
        w.gb(g).u32(G_ACTIVE, init)
        lb = redraw(ctx, c)
        w.wire(reserve=2)
        w.cap_groups()
        c.cap(lb, 4, 'redraw_flags')
        c.arg(w.ga(g))
        c.note(members=n, expected=expected, init=init)
        if edges:
            c.note(edge=','.join(sorted(set(edges))))
        finish(c)


def gen_is_live(ctx):
    fn = ctx.fn(0x00510b30)  # bool IsMonsterGroupLive(W8MonsterGroup*)
    for i in range(ctx.n(250)):
        r = ctx.rng('islive', i)
        c = ctx.case('islive.%d' % i, fn, conv='c', ret='b')
        G = ctx.scratch(SB_GROUPS)
        b = Blob(G_SIZE)
        b.u32(G_ID, r.randrange(1, 3000))
        edges = live_fields(r, b)
        c.set(G, trim(b))
        mode, engaged, rc = combat(ctx, c, r)
        if mode not in (0, 1) or engaged not in (0, 1):
            edges.append('bool_byte')
        c.arg(G)
        c.note(loaded=b[G_LOADED], in_combat=b[G_INCOMBAT], count=b.get_u32(G_COUNT),
               disp=b[G_DISP], combat_mode=mode, engaged=engaged, round_count=rc)
        if edges:
            c.note(edge=','.join(sorted(set(edges))))
        finish(c)


def gen_live_at_index(ctx):
    fn = ctx.fn(0x00510ac0)  # W8MonsterGroup* GetLiveMonsterGroupAtIndex(int)
    for i in range(ctx.n(250)):
        r = ctx.rng('liveatindex', i)
        c = ctx.case('liveatindex.%d' % i, fn, conv='c', ret='p', out='p')
        w = World(ctx, c)
        ng = pick(r, [(1, 0), (2, 1), (8, lambda: r.randrange(2, 10))])
        ids = ids_for(r, ng)
        edges = []
        for k in range(ng):
            g = w.group(ids[k])
            edges += live_fields(r, w.gb(g))
            w.main.append(g)
        mode, engaged, rc = combat(ctx, c, r)
        idx = pick(r, [(25, 0), (45, lambda: r.randrange(0, ng + 1)),
                       (15, lambda: r.choice([-1, -2, -0x80000000])),
                       (15, lambda: r.choice([ng + 1, 100, 0x7fffffff]))])
        w.wire()
        c.arg(idx)
        c.note(groups=ng, index=idx, combat_mode=mode, engaged=engaged, round_count=rc)
        if edges:
            c.note(edge=','.join(sorted(set(edges))))
        finish(c)


def gen_reapply(ctx):
    fn = ctx.fn(0x00510830)  # void ReapplyMonsterGroupFormations(void)
    for i in range(ctx.n(150)):
        r = ctx.rng('reapply', i)
        c = ctx.case('reapply.%d' % i, fn, conv='c', ret='v')
        w = World(ctx, c, istride=0x18, mstride=0x290)
        ng = pick(r, [(1, 0), (1, 1), (8, lambda: r.randrange(2, 8))])
        nl = max(1, ng - (r.randrange(0, 3) if ng > 3 else 0))
        locs = ids_for(r, nl + 3, 1, 9000)
        keys = []
        for j in range(nl):
            m = w.mon()
            for q in range(3):
                w.mb(m).u32(M_FORMATION + 4 * q, r.getrandbits(32))
            keys.append(w.info(locs[j], mon=m))
        for j in range(r.randrange(0, 3)):
            keys.append(w.info(locs[nl + j]))
        w.place(r, keys, unborn_p=0.08)
        snan = False
        ids = ids_for(r, ng)
        for k in range(ng):
            g = w.group(ids[k])
            w.gb(g).u32(G_LEADER_LOC, locs[r.randrange(nl)])
            for q in range(3):
                v = fbits(r, special_p=0.12, snan_p=0.03)
                snan = snan or v in SNAN
                w.gb(g).u32(G_FORMATION + 4 * q, v)
            w.main.append(g)
        w.wire(reserve=2)
        # Retail copies each formation float through fld/fstp, which quiets a signalling
        # NaN (sets bit 22); the port copies the bits. The formation fields are declared as
        # floats so the compare treats NaN against NaN (any payload) as fp-noise.
        w.cap_mons(floats=[M_FORMATION + 4 * q for q in range(3)])
        w.cap_groups()
        c.note(groups=ng, leaders=nl)
        if snan:
            c.note(edge='snan')
        finish(c)


def gen_set_formation(ctx):
    fn = ctx.fn(0x0050ff40)  # void SetMonsterGroupFormation(W8MonsterGroup*, const srVector3T<float>*)
    MISC = ctx.scratch(SB_MISC)
    for i in range(ctx.n(200)):
        r = ctx.rng('setformation', i)
        c = ctx.case('setformation.%d' % i, fn, conv='c', ret='v')
        w = World(ctx, c, istride=0x18, mstride=0x290)
        n = pick(r, [(1, 0), (2, 1), (10, lambda: r.randrange(2, 11))])
        locs = ids_for(r, n + 2, 1, 9000)
        keys = []
        for j in range(n):
            if j and r.random() < 0.15:
                m = w.infos[keys[r.randrange(len(keys))]]['mon']
            else:
                m = w.mon()
                for q in range(3):
                    w.mb(m).u32(M_FORMATION + 4 * q, r.getrandbits(32))
            keys.append(w.info(locs[j], mon=m))
        for j in range(r.randrange(0, 3)):
            keys.append(w.info(locs[n + j]))
        w.place(r, keys, unborn_p=0.08)
        used = 0xffffffff if r.random() < 0.03 else None
        g = w.group(r.randrange(1, 3000), members=locs[:n], used=used)
        for q in range(3):
            w.gb(g).u32(G_FORMATION + 4 * q, r.getrandbits(32))
        vec = b''.join(u32(fbits(r, special_p=0.12)) for _ in range(3))
        c.set(MISC + MISC_VEC, vec)
        null = r.random() < 0.03
        w.wire(reserve=2)
        w.cap_groups()
        w.cap_mons()
        c.arg(0 if null else w.ga(g))
        c.arg(MISC + MISC_VEC)
        c.note(members=n, null_group=int(null), ilist_used=used)
        finish(c)


def gen_retire(ctx):
    fn = ctx.fn(0x00510a10)  # void RetireMonsterGroupAndAllies(W8MonsterGroup*)
    gag = ctx.g('g_active_groups')
    budget_g = ctx.g('g_random_encounter_budget')
    limit_g = ctx.g('g_random_encounter_limit')
    for i in range(ctx.n(200)):
        r = ctx.rng('retire', i)
        c = ctx.case('retire.%d' % i, fn, conv='c', ret='v')
        w = World(ctx, c)
        ng = r.randrange(1, 9)
        ids = ids_for(r, ng, 1, 3000)
        gs = [w.group(ids[k]) for k in range(ng)]
        edges = []
        for k in gs:
            (w.enc if r.random() < 0.2 else w.main).append(k)
            reg = bool_byte(r, 0.6)
            if reg not in (0, 1):
                edges.append('bool_byte')
            w.gb(k).u8(G_ENC_REG, reg)
            w.gb(k).u8(G_ENC_ENDED, r.choice([0, 0, 1]))
            w.gb(k).u32(G_LEADER_GRP, 0)
        chain_len = min(ng - 1, pick(r, [(40, 0), (30, 1), (20, 2), (10, 3)]))
        chain = r.sample(gs, chain_len + 1)
        for a, b in zip(chain, chain[1:]):
            w.gb(a).u32(G_LEADER_GRP, ids[b])
        final = chain[-1]
        for s in range(4):
            if r.random() < 0.6:
                w.gb(final).u32(G_ALLIES + 4 * s, ids[r.choice(gs)])
        active = [k for k in gs if r.random() < 0.6]
        r.shuffle(active)
        mode = pick(r, [(70, 0), (30, 1)])
        budget = r.choice([20, 0, 1, 5, 10, 40, -3, r.randrange(-5, 60)])
        limit = r.choice([10, 0, 3, r.randrange(0, 20)])
        c.set(ctx.g('gXStatus') + GX_COMBAT, u8(mode))
        c.set(budget_g, u32(budget))
        c.set(limit_g, u32(limit))
        c.set(gag + AG_COUNT, u32(len(active)))
        w.wire(reserve=len(active) + 1 + 4)
        L = ctx.scratch(SB_LISTS)
        for j, k in enumerate(active):
            c.setp(L + L_ACTIVE_DATA + 4 * j, w.ga(k))
        c.setp(gag + AG_DATA, L + L_ACTIVE_DATA)
        w.cap_groups()
        c.cap(gag + AG_COUNT, 4, 'active_count')
        c.cap(budget_g, 4, 'encounter_budget')
        c.cap(limit_g, 4, 'encounter_limit')
        c.arg(w.ga(chain[0]))
        c.note(groups=ng, chain=chain_len, active=len(active), combat_mode=mode, budget=budget,
               limit=limit)
        if edges:
            c.note(edge='bool_byte')
        finish(c)


def gen_group_name(ctx):
    fn = ctx.fn(0x00510280)  # wchar_t* GetMonsterGroupName(W8MonsterGroup*)
    gs = ctx.g('g_status')
    for i in range(ctx.n(250)):
        r = ctx.rng('groupname', i)
        c = ctx.case('groupname.%d' % i, fn, conv='c', ret='w', out='w')
        w = World(ctx, c)
        edges = []
        if r.random() < 0.85:
            species = r.randrange(0, 1000)
            b = Blob(REC_STRIDE)
            for off in REC_NAMES:
                if r.random() < 0.04:
                    b[off:off + 0x30] = wstr('Unterminated name of 24!', 0x30, terminate=False)
                    edges.append('name_unterminated')
                else:
                    b[off:off + 0x30] = wstr(r.choice(NAMES), 0x30)
            rid = pick(r, [(25, ALT_NAME_RECORD), (50, species),
                           (25, lambda: r.choice([-ALT_NAME_RECORD, ALT_NAME_RECORD + 1,
                                                  ALT_NAME_RECORD - 1, 0, -1, 0x7fff]))])
            struct.pack_into('<h', b, REC_ID, rid)
            Records(ctx, c).get(species, b)
            mode = 'scratch'
        else:
            species = r.choice([0, 1, ALT_NAME_RECORD, ALT_NAME_RECORD, 594,
                                r.randrange(MONSTER_RECORDS), r.randrange(MONSTER_RECORDS)])
            rid = None
            mode = 'real'
        k = w.group(r.randrange(1, 3000))
        count = pick(r, [(35, 1), (10, 0), (40, lambda: r.randrange(2, 10)),
                         (15, lambda: r.choice([0xffffffff, 0x80000001, 0x101, 0x100000001 & 0xffffffff]))])
        alt = bool_byte(r, 0.5, 0.06)
        if alt not in (0, 1):
            edges.append('bool_byte')
        w.gb(k).u32(G_MONID, species)
        w.gb(k).u32(G_COUNT, count)
        w.gb(k).u8(G_ALTNAME, alt)
        slot = r.randrange(8)
        if r.random() < 0.06:
            nm = wstr('Abcdefghij', 0x14, terminate=False) + wstr('Zy', 6)
            edges.append('name_unterminated')
        else:
            nm = wstr(r.choice(PARTY_NAMES), 0x14) + bytes(6)
        c.fill(gs + GS_NAMEBUF, GS_NAMEBUF_LEN, 0)
        c.set(gs + GS_SEDEXUS, u32(slot))
        c.set(ctx.char(slot) + C_NAME, nm)
        w.wire(lists=False, reserve=1)
        c.cap(gs + GS_NAMEBUF, GS_NAMEBUF_LEN + 4, 'monster_name_buffer')
        c.arg(w.ga(k))
        c.note(species=species, mode=mode, record_id=rid, count=count, alt=alt, slot=slot)
        if edges:
            c.note(edge=','.join(sorted(set(edges))))
        finish(c)


def gen_load_members(ctx):
    fn = ctx.fn(0x0050f630)  # void LoadMonsterGroupMembers(W8MonsterGroup*)
    for i in range(ctx.n(100)):
        r = ctx.rng('loadmembers', i)
        c = ctx.case('loadmembers.%d' % i, fn, conv='c', ret='v')
        w = World(ctx, c, istride=0x18)
        n = pick(r, [(1, 0), (2, 1), (8, lambda: r.randrange(2, 11))])
        locs = ids_for(r, n + 3, 1, 9000)
        keys = []
        edges = []
        for j in range(n):
            k = w.info(locs[j])
            a = r.choice(BOOL_EDGE) if r.random() < 0.15 else 1
            if a != 1:
                edges.append('bool_byte')
            w.ib(k).u8(I_ACTIVE, a)
            keys.append(k)
        for j in range(r.randrange(0, 3)):
            k = w.info(locs[n + j])
            w.ib(k).u8(I_ACTIVE, r.choice([0, 1]))
            keys.append(k)
        w.place(r, keys, unborn_p=0.08)
        g = w.group(r.randrange(1, 3000), members=locs[:n])
        w.gb(g).u32(G_HILITE, r.choice([0, -1, 5, locs[0] if n else 7, 0x7fffffff]))
        w.gb(g).u8(G_LOADED, r.choice([0, 1, 2]))
        w.gb(g).u32(G_COUNT, n)
        w.wire(reserve=1)
        w.cap_groups()
        c.arg(w.ga(g))
        c.note(members=n)
        if edges:
            c.note(edge='bool_byte')
        finish(c)


def gen_reset_turn(ctx):
    fn = ctx.fn(0x00511530)  # void ResetMonsterGroupTurnState(void)
    for i in range(ctx.n(120)):
        r = ctx.rng('resetturn', i)
        c = ctx.case('resetturn.%d' % i, fn, conv='c', ret='v')
        w = World(ctx, c, istride=0x358)
        ng = pick(r, [(1, 0), (1, 1), (8, lambda: r.randrange(2, 9))])
        nm = pick(r, [(1, 0), (1, 1), (8, lambda: r.randrange(2, 15))])
        ids = ids_for(r, ng)
        for k in range(ng):
            g = w.group(ids[k])
            w.gb(g).u32(G_HOST_AT, r.getrandbits(32) | 1)
            w.gb(g).u32(G_SPAWN, r.getrandbits(32))
            w.gb(g).u8(G_ENC_REG, 1)
            w.main.append(g)
        locs = ids_for(r, nm, 1, 9000)
        keys = []
        for j in range(nm):
            k = w.info(locs[j])
            b = w.ib(k)
            for off in range(I_THREAT_SEEN - 4, I_THREAT_SEEN + 8):
                b.u8(off, r.randrange(1, 256))
            for off in range(I_PV_SEEN - 4, I_PV_SEEN + 4):
                b.u8(off, r.randrange(1, 256))
            keys.append(k)
        w.place(r, keys, unborn_p=0.1)
        w.wire(reserve=2)
        w.cap_groups()
        w.cap_infos()
        c.note(groups=ng, monsters=nm, unborn=len(w.unborn))
        finish(c)


def gen_control_state(ctx):
    fn = ctx.fn(0x005117d0)  # void SetMonsterGroupControlState(W8MonsterGroup*, W8MonsterControlState)
    for i in range(ctx.n(200)):
        r = ctx.rng('controlstate', i)
        c = ctx.case('controlstate.%d' % i, fn, conv='c', ret='v')
        w = World(ctx, c, istride=0x308, mstride=0x1e0, rstride=0xb0)
        ng = r.randrange(1, 4)
        ids = ids_for(r, ng, 1, 3000)
        sizes = [pick(r, [(1, 1), (8, lambda: r.randrange(2, 7))])] + \
            [r.randrange(0, 3) for _ in range(ng - 1)]
        locs = ids_for(r, sum(sizes) + 2, 1, 9000)
        keys = []
        pos = 0
        edges = []
        gidx = []
        for gi in range(ng):
            members = locs[pos:pos + sizes[gi]]
            pos += sizes[gi]
            g = w.group(ids[gi], members=members)
            w.gb(g).u32(G_COUNT, len(members))
            w.gb(g).u32(G_ACTIVE, r.randrange(0, 5))
            w.main.append(g)
            gidx.append(g)
            for loc in members:
                cyc, pend, dying = rep_state(r, 0.2)
                m = w.mon(rep=w.rep(cyc, pend))
                w.mb(m).u32(M_LINKED, 0x1000 + len(w.mons))   # never 0: no ClearMovement
                k = w.info(loc, mon=m)
                own = gi if r.random() < 0.8 else r.randrange(ng)
                w.ib(k).u32(I_GROUP, ids[own])
                hc = hcond(r, 0.04)
                if hc >= 0x80000000:
                    edges.append('cond_negative')
                w.ib(k).u32(I_HCOND, hc)
                w.ib(k).u32(I_CONTROL, pick(r, [(45, 0), (30, 1), (20, 2), (5, 7)]))
                keys.append(k)
        for j in range(r.randrange(0, 2)):
            keys.append(w.info(locs[pos + j]))
        w.place(r, keys, unborn_p=0.06)
        state = pick(r, [(30, 0), (35, 1), (25, 2), (10, lambda: r.choice([3, 0xffffffff, 0x100]))])
        lb = redraw(ctx, c)
        w.wire(reserve=3)
        w.cap_groups()
        w.cap_infos()
        c.cap(lb, 4, 'redraw_flags')
        c.arg(w.ga(gidx[0]))
        c.arg(state)
        c.note(groups=ng, sizes=sizes, state=state)
        if edges:
            c.note(edge='cond_negative')
        finish(c)


def gen_renderable(ctx):
    fn = ctx.fn(0x00511b40)  # bool MonsterGroupHasRenderableMember(W8MonsterGroup*, bool)
    cam = ctx.g('g_startup_world').deref() + 0x100   # W8Navigator::GetPosition (movement.position)
    for i in range(ctx.n(250)):
        r = ctx.rng('renderable', i)
        c = ctx.case('renderable.%d' % i, fn, conv='c', ret='b')
        w = World(ctx, c, istride=0x2b0, mstride=0x338)
        recs = Records(ctx, c)
        species = r.sample(range(0, MONSTER_RECORDS), r.choice([1, 1, 2]))
        for s in species:
            b = record_blob(r, s, names=False)
            b.u8(REC_CAMO, pick(r, [(60, 0), (30, lambda: r.randrange(1, 100)), (10, 0xff)]))
            recs.get(s, b)
        n = pick(r, [(1, 0), (2, 1), (8, lambda: r.randrange(2, 7))])
        locs = ids_for(r, n + 2, 1, 9000)
        keys = []
        edges = []
        near_count = 0
        for j in range(n):
            m = w.mon()
            mb = w.mb(m)
            near = r.random() < 0.6
            if near:
                near_count += 1
                for q in range(3):
                    w.mons[m]['copy'].append((M_POS + 4 * q, (cam + 4 * q).deref()))
            else:
                for q in range(3):
                    mb.f32(M_POS + 4 * q, r.choice([1e18, -1e18, 3e17]))
            mloc = pick(r, [(85, locs[j]), (5, -1), (10, lambda: locs[r.randrange(n)])])
            mb.u32(M_LOC, mloc)
            dis = bool_byte(r, 0.12, 0.2)
            ina = bool_byte(r, 0.12, 0.2)
            if dis not in (0, 1) or ina not in (0, 1):
                edges.append('bool_byte')
            mb.u8(M_DISABLED, dis)
            mb.u8(M_INACTIVE, ina)
            mb.u32(M_FLAGS, r.choice([0, 0, 0, REMOVE_AFTER_FADE, REMOVE_NOW, 0xfeff, 0x20]))
            mb.u8(M_FADE, pick(r, [(85, 0), (15, lambda: r.choice([1, 2, 3, 0xff]))]))
            k = w.info(locs[j], mon=m)
            ib = w.ib(k)
            ib.u32(I_SPECIES, r.choice(species))
            ib.u8(I_VIEW, bool_byte(r, 0.5, 0.0))
            ib.u8(I_LOS1, bool_byte(r, 0.5, 0.1))
            ib.u8(I_DETECTED, bool_byte(r, 0.5, 0.1))
            ib.u8(I_VISIBLE, bool_byte(r, 0.5, 0.1))
            keys.append(k)
        for j in range(r.randrange(0, 3)):
            keys.append(w.info(locs[n + j]))
        w.place(r, keys, unborn_p=0.06)
        g = w.group(r.randrange(1, 3000), members=locs[:n])
        loaded = bool_byte(r, 0.85)
        w.gb(g).u8(G_LOADED, loaded)
        w.gb(g).u32(G_COUNT, n)
        req = pick(r, [(45, 0), (45, 1), (10, lambda: r.choice([2, 0xff, 0x100]))])
        if loaded not in (0, 1) or req not in (0, 1):
            edges.append('bool_arg' if req not in (0, 1) else 'bool_byte')
        w.wire()
        c.arg(w.ga(g))
        c.arg(req)
        c.note(members=n, near=near_count, loaded=loaded, require_threat=req)
        if edges:
            c.note(edge=','.join(sorted(set(edges))))
        finish(c)


def gen_incapacitated(ctx):
    fn = ctx.fn(0x00511d40)  # bool MonsterGroupHasIncapacitatedMember(int group_id)
    for i in range(ctx.n(250)):
        r = ctx.rng('incapacitated', i)
        c = ctx.case('incapacitated.%d' % i, fn, conv='c', ret='b')
        w = World(ctx, c, istride=0x110)
        ng = pick(r, [(3, 1), (7, lambda: r.randrange(2, 7))])
        ids = ids_for(r, ng, 1, 3000)
        sizes = [r.randrange(0, 5) for _ in range(ng)]
        locs = ids_for(r, sum(sizes) + 2, 1, 9000)
        keys = []
        pos = 0
        gidx = []
        edges = []
        p_incap = r.choice([0.0, 0.05, 0.15, 0.3])
        for gi in range(ng):
            members = locs[pos:pos + sizes[gi]]
            pos += sizes[gi]
            g = w.group(ids[gi], members=members)
            (w.enc if gi and r.random() < 0.15 else w.main).append(g)
            gidx.append(g)
            for loc in members:
                k = w.info(loc)
                if r.random() < p_incap:
                    hc = r.choice([0x0e, 0x0f, 0x10, 0x11])
                else:
                    hc = pick(r, [(60, 0), (25, lambda: r.choice([0x0c, 0x0d, 0x12, 0x13, 0x14])),
                                  (10, lambda: r.randrange(1, 0x0d)),
                                  (5, lambda: r.choice(COND_EDGE))])
                if hc >= 0x80000000:
                    edges.append('cond_negative')
                w.ib(k).u32(I_HCOND, hc)
                keys.append(k)
        dag_allies(r, w, gidx, ids, p=r.choice([0.2, 0.4, 0.6]))
        for j in range(r.randrange(0, 3)):
            keys.append(w.info(locs[pos + j]))
        w.place(r, keys, unborn_p=0.06)
        w.wire()
        c.arg(ids[0])
        c.note(groups=ng, sizes=sizes, p_incap=p_incap)
        if edges:
            c.note(edge='cond_negative')
        finish(c)


def gen_centre(ctx):
    fn = ctx.fn(0x0050ffd0)  # void GetMonsterGroupCentre(W8MonsterGroup*, srVector3T<float>*)
    MISC = ctx.scratch(SB_MISC)
    for i in range(ctx.n(250)):
        r = ctx.rng('centre', i)
        c = ctx.case('centre.%d' % i, fn, conv='c', ret='v')
        w = World(ctx, c, istride=0x18, mstride=0x1e0, rstride=0x10)
        n = pick(r, [(1, 0), (2, 1), (10, lambda: r.randrange(2, 10))])
        locs = ids_for(r, n + 2, 1, 9000)
        keys = []
        special = r.random() < 0.15
        span = r.choice([10.0, 5000.0, 1e6])
        for j in range(n):
            if j and r.random() < 0.12:
                m = w.infos[keys[r.randrange(len(keys))]]['mon']
            else:
                loc3 = [fbits(r, special_p=0.15 if special else 0.0, span=span) for _ in range(3)]
                m = w.mon(rep=w.rep(loc=loc3))
            keys.append(w.info(locs[j], mon=m))
        for j in range(r.randrange(0, 3)):
            keys.append(w.info(locs[n + j]))
        w.place(r, keys, unborn_p=0.06)
        g = w.group(r.randrange(1, 3000), members=locs[:n])
        loaded = pick(r, [(80, 1), (15, 0), (5, lambda: r.choice(BOOL_EDGE))])
        w.gb(g).u8(G_LOADED, loaded)
        w.gb(g).u32(G_COUNT, n)
        for q in range(3):
            w.gb(g).u32(G_CENTRE + 4 * q, fbits(r, special_p=0.05))
        out = r.random() < 0.7
        null = r.random() < 0.03
        w.wire(reserve=2)
        w.cap_groups(floats=(G_CENTRE, G_CENTRE + 4, G_CENTRE + 8))
        c.cap(MISC + MISC_OUT, 12, 'centre', floats=[0, 4, 8])
        c.arg(0 if null else w.ga(g))
        c.arg(MISC + MISC_OUT if out else 0)
        c.note(members=n, loaded=loaded, out=int(out), null_group=int(null), special=int(special))
        if loaded not in (0, 1):
            c.note(edge='bool_byte')
        finish(c)


def gen_find_first(ctx):
    fn = ctx.fn(0x00510b60)  # W8MonsterGroup* FindFirstMonsterByID(int)
    for i in range(ctx.n(200)):
        r = ctx.rng('findfirst', i)
        c = ctx.case('findfirst.%d' % i, fn, conv='c', ret='p', out='p')
        w = World(ctx, c)
        ng = pick(r, [(1, 0), (2, 1), (7, lambda: r.randrange(2, 10))])
        ne = pick(r, [(3, 0), (2, 1), (5, lambda: r.randrange(2, 7))])
        pool = r.sample(range(0, MONSTER_RECORDS), 4)
        if r.random() < 0.1:
            pool[r.randrange(4)] = r.choice([-1, 0x7fffffff, -0x80000000, 0x10000 + pool[0]])
        ids = ids_for(r, ng + ne)
        for k in range(ng + ne):
            g = w.group(ids[k])
            w.gb(g).u32(G_MONID, r.choice(pool))
            (w.main if k < ng else w.enc).append(g)
        q = pick(r, [(75, lambda: r.choice(pool)), (15, lambda: r.randrange(0, MONSTER_RECORDS)),
                     (10, lambda: r.choice([0, -1, 0x7fffffff, -0x80000000]))])
        w.wire()
        c.arg(q)
        c.note(main=ng, enc=ne, monster_id=q)
        finish(c)


def gen_find_next(ctx):
    fn = ctx.fn(0x00510bf0)  # W8MonsterGroup* FindNextExistingMonsterByID(int, W8MonsterGroup*)
    for i in range(ctx.n(300)):
        r = ctx.rng('findnext', i)
        c = ctx.case('findnext.%d' % i, fn, conv='c', ret='p', out='p')
        w = World(ctx, c)
        ng = pick(r, [(1, 0), (2, 1), (7, lambda: r.randrange(2, 10))])
        ne = pick(r, [(2, 0), (2, 1), (6, lambda: r.randrange(2, 7))])
        pool = r.sample(range(0, MONSTER_RECORDS), 3)
        ids = ids_for(r, ng + ne + 1)
        for k in range(ng + ne):
            g = w.group(ids[k])
            w.gb(g).u32(G_MONID, r.choice(pool))
            (w.main if k < ng else w.enc).append(g)
        stray = w.group(ids[-1])
        w.gb(stray).u32(G_MONID, r.choice(pool))
        mode = pick(r, [(20, 'null'), (30, 'main'), (10, 'last'), (25, 'enc'), (15, 'stray')])
        if mode == 'main' and ng:
            prev = w.ga(r.randrange(ng))
        elif mode == 'last' and ng:
            prev = w.ga(ng - 1)
        elif mode == 'enc' and ne:
            prev = w.ga(ng + r.randrange(ne))
        elif mode == 'stray':
            prev = w.ga(stray)
        else:
            mode = 'null'
            prev = 0
        q = pick(r, [(85, lambda: r.choice(pool)), (15, lambda: r.randrange(0, MONSTER_RECORDS))])
        w.wire()
        c.arg(q)
        c.arg(prev)
        c.note(main=ng, enc=ne, previous=mode, monster_id=q)
        finish(c)


def gen_elect_leader(ctx):
    fn = ctx.fn(0x005103e0)  # void ElectGroupLeaderMember(W8MonsterGroup*)
    for i in range(ctx.n(250)):
        r = ctx.rng('electleader', i)
        c = ctx.case('electleader.%d' % i, fn, conv='c', ret='v')
        w = World(ctx, c, istride=0x110, mstride=0x240)
        n = pick(r, [(2, 1), (8, lambda: r.randrange(2, 9))])
        locs = ids_for(r, n + 3, 1, 9000)
        if r.random() < 0.06:
            locs[r.randrange(n)] = 0
        keys = []
        edges = []
        rank_mode = r.choice(['random', 'dups', 'edge', 'zero'])
        for j in range(n):
            m = w.mon()
            mb = w.mb(m)
            if rank_mode == 'random':
                rank = r.randrange(0, 200)
            elif rank_mode == 'dups':
                rank = r.choice([0, 5, 5, 10])
            elif rank_mode == 'zero':
                rank = 0
            else:
                rank = r.choice([0, 1, 0xffffffff, 0x80000000, 0x7fffffff, 100])
            mb.u32(M_RANK, rank)
            mb.u32(M_FLAGS, pick(r, [(80, 0), (15, REMOVE_NOW), (5, lambda: r.choice([0x1ff, 0x400, 0xfffffdff]))]))
            k = w.info(locs[j], mon=m)
            hc = hcond(r, 0.05)
            if hc >= 0x80000000:
                edges.append('cond_negative')
            ib = w.ib(k)
            ib.u32(I_HCOND, hc)
            for q in range(3):
                ib.u32(I_NOISE_POS + 4 * q, fbits(r, special_p=0.05))
            ib.u32(I_NOISE_RAD, r.choice([0, -1, r.randrange(1, 5000)]))
            keys.append(k)
        decoy = None
        for j in range(r.randrange(0, 3)):
            m = w.mon()
            k = w.info(locs[n + j], mon=m)
            ib = w.ib(k)
            for q in range(3):
                ib.u32(I_NOISE_POS + 4 * q, fbits(r))
            ib.u32(I_NOISE_RAD, r.randrange(1, 5000))
            keys.append(k)
            decoy = locs[n + j]
        w.place(r, keys, unborn_p=0.06)
        g = w.group(r.randrange(1, 3000), members=locs[:n])
        old = decoy if decoy is not None and r.random() < 0.15 else locs[r.randrange(n)]
        w.gb(g).u32(G_LEADER_LOC, old)
        w.gb(g).u32(G_COUNT, n)
        w.wire(reserve=2)
        w.cap_groups()
        w.cap_infos()
        c.arg(w.ga(g))
        c.note(members=n, ranks=rank_mode, old_leader=old)
        if edges:
            c.note(edge='cond_negative')
        finish(c)


def gen_mark_removal(ctx):
    fn = ctx.fn(0x005118e0)  # void MarkMonsterGroupForRemoval(int group_id)
    for i in range(ctx.n(200)):
        r = ctx.rng('markremoval', i)
        c = ctx.case('markremoval.%d' % i, fn, conv='c', ret='v')
        w = World(ctx, c, istride=0x18, mstride=0x1e0, rstride=0xb0)
        ng = pick(r, [(3, 1), (7, lambda: r.randrange(2, 5))])
        ids = ids_for(r, ng, 1, 3000)
        sizes = [r.randrange(0, 5) for _ in range(ng)]
        locs = ids_for(r, sum(sizes) + 2, 1, 9000)
        keys = []
        pos = 0
        gidx = []
        missing = 0
        for gi in range(ng):
            members = locs[pos:pos + sizes[gi]]
            pos += sizes[gi]
            g = w.group(ids[gi], members=members)
            (w.enc if gi and r.random() < 0.15 else w.main).append(g)
            gidx.append(g)
            for loc in members:
                if r.random() < 0.08:
                    missing += 1          # not in any list: MonsterInfoFromID asserts, skipped
                    continue
                cyc, pend, dying = rep_state(r, 0.25)
                m = w.mon(rep=w.rep(cyc, pend))
                w.mb(m).u32(M_FLAGS, r.choice([0, 0, REMOVE_NOW, 0x20, 0xfffffdff, 0x40 | REMOVE_AFTER_FADE]))
                keys.append(w.info(loc, mon=m))
        dag_allies(r, w, gidx, ids, p=r.choice([0.2, 0.4]))
        for j in range(r.randrange(0, 2)):
            keys.append(w.info(locs[pos + j]))
        w.place(r, keys, unborn_p=0.06)
        w.wire(reserve=1)
        w.cap_mons()
        c.arg(ids[0])
        c.note(groups=ng, sizes=sizes, missing=missing)
        finish(c)


def gen_engagement_set(ctx):
    fn = ctx.fn(0x00511be0)  # void SetMonsterGroupEngagementState(int group_id, bool state)
    for i in range(ctx.n(250)):
        r = ctx.rng('engageset', i)
        c = ctx.case('engageset.%d' % i, fn, conv='c', ret='v')
        w = World(ctx, c)
        ng = r.randrange(1, 7)
        ids = ids_for(r, ng, 1, 3000)
        edges = []
        for k in range(ng):
            g = w.group(ids[k])
            (w.enc if k and r.random() < 0.15 else w.main).append(g)
            e = pick(r, [(45, 0), (45, 1), (10, lambda: r.choice(BOOL_EDGE))])
            if e not in (0, 1):
                edges.append('bool_byte')
            w.gb(g).u8(G_ENGAGE, e)
            w.gb(g).u8(G_TICKS, pick(r, [(50, lambda: r.randrange(0, 8)), (30, lambda: r.randrange(0, 256)),
                                         (20, lambda: r.choice([0xfe, 0xff]))]))
            w.gb(g).u32(G_MONID, r.randrange(0, MONSTER_RECORDS))
        root = 0
        w.gb(root).u32(G_MONID, pick(r, [(20, 0x1b6), (20, 0x234), (60, lambda: r.randrange(0, MONSTER_RECORDS))]))
        for s in range(4):
            if r.random() < 0.55:
                w.gb(root).u32(G_ALLIES + 4 * s, ids[r.randrange(ng)])
        state = pick(r, [(45, 0), (45, 1), (10, lambda: r.choice([2, 0xff, 0x100, 0x101]))])
        if state not in (0, 1):
            edges.append('bool_arg')
        w.wire(reserve=1)
        w.cap_groups()
        c.arg(ids[root])
        c.arg(state)
        c.note(groups=ng, monster_id=w.gb(root).get_u32(G_MONID), state=state)
        if edges:
            c.note(edge=','.join(sorted(set(edges))))
        finish(c)


def gen_engagement_get(ctx):
    fn = ctx.fn(0x00511cb0)  # bool GetMonsterGroupEngagementState(int group_id)
    for i in range(ctx.n(120)):
        r = ctx.rng('engageget', i)
        c = ctx.case('engageget.%d' % i, fn, conv='c', ret='b')
        w = World(ctx, c)
        ng = r.randrange(1, 8)
        ids = ids_for(r, ng, 1, 3000)
        for k in range(ng):
            g = w.group(ids[k])
            (w.enc if r.random() < 0.2 else w.main).append(g)
            w.gb(g).u8(G_ENGAGE, pick(r, [(45, 0), (45, 1), (10, lambda: r.choice(BOOL_EDGE))]))
            w.gb(g).u8(G_TICKS, r.randrange(256))
        q = ids[r.randrange(ng)]
        w.wire()
        c.arg(q)
        c.note(groups=ng, id=q)
        finish(c)


def gen_nav_dirty(ctx):
    fn = ctx.fn(0x00511ce0)  # void SetMonsterGroupNavigatorDirty(W8MonsterGroup*, bool)
    for i in range(ctx.n(150)):
        r = ctx.rng('navdirty', i)
        c = ctx.case('navdirty.%d' % i, fn, conv='c', ret='v')
        w = World(ctx, c, istride=0x18, mstride=0xb8)
        n = pick(r, [(1, 0), (2, 1), (8, lambda: r.randrange(2, 11))])
        locs = ids_for(r, n + 2, 1, 9000)
        keys = []
        for j in range(n):
            if j and r.random() < 0.12:
                m = w.infos[keys[r.randrange(len(keys))]]['mon']
            else:
                m = w.mon()
                w.mb(m).u8(M_DIRTY, r.choice([0, 1, 2, 0xff]))
                w.mb(m).u8(M_DIRTY + 1, r.choice([0, 1]))
            keys.append(w.info(locs[j], mon=m))
        for j in range(r.randrange(0, 3)):
            keys.append(w.info(locs[n + j]))
        w.place(r, keys, unborn_p=0.06)
        g = w.group(r.randrange(1, 3000), members=locs[:n])
        flag = pick(r, [(45, 0), (45, 1), (10, lambda: r.choice([2, 0xff, 0x100, 0x101]))])
        w.wire(reserve=1)
        w.cap_mons()
        c.arg(w.ga(g))
        c.arg(flag)
        c.note(members=n, flag=flag)
        if flag not in (0, 1):
            c.note(edge='bool_arg')
        finish(c)


def gen_all_dying(ctx):
    fn = ctx.fn(0x00511850)  # bool MonsterGroupAllMembersDying(W8MonsterGroup*)
    for i in range(ctx.n(200)):
        r = ctx.rng('alldying', i)
        c = ctx.case('alldying.%d' % i, fn, conv='c', ret='b')
        w = World(ctx, c, istride=0x18, mstride=0x1e0, rstride=0xb0)
        n = pick(r, [(1, 0), (2, 1), (10, lambda: r.randrange(2, 11))])
        locs = ids_for(r, n + 2, 1, 9000)
        dying_p = r.choice([0.0, 0.5, 0.85, 1.0])
        shared = r.random() < 0.3
        pool = []
        if shared:
            for _ in range(4):
                cyc, pend, _d = rep_state(r, dying_p)
                pool.append(w.mon(rep=w.rep(cyc, pend)))
        keys = []
        for j in range(n):
            if shared:
                m = r.choice(pool)
            else:
                cyc, pend, _d = rep_state(r, dying_p)
                m = w.mon(rep=w.rep(cyc, pend))
            keys.append(w.info(locs[j], mon=m))
        for j in range(r.randrange(0, 3)):
            keys.append(w.info(locs[n + j]))
        w.place(r, keys, unborn_p=0.06)
        g = w.group(r.randrange(1, 3000), members=locs[:n])
        w.wire()
        c.arg(w.ga(g))
        c.note(members=n, dying_p=dying_p, shared=int(shared))
        finish(c)


# ------------------------------------------------------------------ dispositions

def faction_setup(ctx, c, r, faction):
    """g_factions[low byte]: score (band thresholds 34/67, signed char) and band clock."""
    f = faction & 0xff
    if faction in (0, 1) or f >= FACTION_COUNT:
        return None
    score = pick(r, [(40, lambda: r.choice([33, 34, 66, 67, 0, 100, -1, -128, 127])),
                     (60, lambda: r.randrange(-128, 128))])
    c.set(ctx.g('g_factions') + f * FAC_STRIDE + FAC_SCORE, struct.pack('<b', score))
    return score


def faction_pick(r):
    return pick(r, [(30, 0), (15, 1), (45, lambda: r.randrange(2, FACTION_COUNT)),
                    (10, lambda: r.choice([0x100, 0x101, 0x100 + r.randrange(2, FACTION_COUNT),
                                           0x80000005, 0xffffff03, 0x10014]))])


def gen_default_disposition(ctx):
    fn = ctx.fn(0x00511250)  # unsigned char MonsterGroupCalcDefaultDisposition(W8MonsterGroup*)
    MISC = ctx.scratch(SB_MISC)
    for i in range(ctx.n(300)):
        r = ctx.rng('defaultdisp', i)
        c = ctx.case('defaultdisp.%d' % i, fn, conv='c', ret='u8')
        w = World(ctx, c, istride=0x2f8)
        recs = Records(ctx, c)
        species = r.randrange(0, 1000)
        rec = record_blob(r, species, names=False)
        notes = {}
        npc = r.random() < 0.35
        if npc:
            rec.u8(REC_FLAGS, FLAG_NPC | r.choice([0, 0, 0x02, 0x10, 0xfe]))
            rec.u8(REC_NPC_KIND, r.choice([0, 3, 0x40, 0xfa if r.random() < 0.1 else 7]))
            rec.u32(REC_FACTION, faction_pick(r))
            n = r.randrange(1, 5)
            locs = ids_for(r, n + 2, 1, 9000)
            keys = [w.info(loc) for loc in locs[:n]]
            first = keys[0]
            if r.random() < 0.75:
                w.ib(first).u32(I_SPECIES, species)
                mode = 'same_species'
            else:
                s2 = (species + r.randrange(1, 1000)) % 1000
                rec2 = record_blob(r, s2, names=False)
                rec2.u8(REC_FLAGS, r.choice([0, FLAG_NPC, FLAG_NPC]))
                rec2.u8(REC_NPC_KIND, r.choice([0xfa, 5]))
                recs.get(s2, rec2)
                w.ib(first).u32(I_SPECIES, s2)
                mode = 'other_species(flags=%d,kind=%d)' % (rec2[REC_FLAGS], rec2[REC_NPC_KIND])
            # g_npc_states -> scratch vector of nstates W8NpcState records
            nstates = r.randrange(1, 4)
            bound = pick(r, [(85, lambda: r.randrange(nstates)), (15, lambda: r.choice([nstates, 50]))])
            w.ib(first).u32(I_NPC, bound)
            target = bound if bound < nstates else 0
            c.set(MISC + MISC_NPCVEC + VEC_COUNT, struct.pack('<ii', nstates, nstates))
            c.setp(ctx.g('g_npc_states'), MISC + MISC_NPCVEC)
            c.setp(MISC + MISC_NPCVEC + VEC_DATA, MISC + MISC_NPCDATA)
            disp_at = None
            for s in range(nstates):
                st = Blob(0xc8)
                disp = pick(r, [(50, lambda: r.choice([0x20, 0x21, 0x41, 0x42, 0x00, 0x64, 0x7f, 0x80, 0xff])),
                                (50, lambda: r.randrange(256))])
                st.u8(NPC_DISP, disp)
                st.u8(NPC_UNAVAIL, pick(r, [(85, 0), (15, lambda: r.choice([1, 2, 0xff]))]))
                if s == target and r.random() < 0.3:
                    st.u8(NPC_HAS_MON, 1)
                    st.u8(NPC_PRESENT, 1)
                    st.u32(NPC_LOC, locs[r.randrange(n)])
                    notes['npc_monster'] = 1
                else:
                    st.u8(NPC_HAS_MON, r.choice([0, 1]))
                    st.u8(NPC_PRESENT, 0)
                if s == target:
                    disp_at = (disp, st[NPC_UNAVAIL])
                a = MISC + MISC_NPC + 0x140 * s
                c.set(a, trim(st))
                c.setp(a + NPC_RECORD, MISC + MISC_NPCREC)
                c.setp(MISC + MISC_NPCDATA + 4 * s, a)
            # MISC_NPCREC stays zero: W8NpcDatabaseRecord.faction (+0x5f) = 0, so
            # GetNpcDisposition answers the (adjusted) stored disposition
            for k in keys:
                w.ib(k).u8(I_CHARM, pick(r, [(60, 0), (40, lambda: r.choice([1, -1, 10, -10, 0x7f, -0x80, 50]))]))
                w.ib(k).u32(I_TURNCOAT, pick(r, [(75, 0), (25, lambda: r.choice([1, 3, 0x80000000]))]))
            for j in range(r.randrange(0, 2)):
                keys.append(w.info(locs[n + j]))
            w.place(r, keys, unborn_p=0.06)
            g = w.group(r.randrange(1, 3000), members=locs[:n])
            notes.update(path='npc', mode=mode, states=nstates, bound=bound, npc=disp_at)
        else:
            rec.u8(REC_FLAGS, r.choice([0, 0, 0x02, 0x04, 0x10, 0xfe]))
            faction = faction_pick(r)
            rec.u32(REC_FACTION, faction)
            radius = pick(r, [(30, -1), (30, 0), (40, lambda: r.choice([1, 500, 0x7fffffff, -2, 0x80000000, r.randrange(1, 5000)]))])
            rec.u32(REC_RADIUS, radius)
            score = faction_setup(ctx, c, r, faction)
            g = w.group(r.randrange(1, 3000), members=[] if r.random() < 0.5 else None)
            notes.update(path='faction', faction=faction, radius=radius, score=score)
        recs.get(species, rec)
        w.gb(g).u32(G_MONID, species)
        w.gb(g).u8(G_DISP, r.choice([0, 1, 2]))
        w.wire()
        c.arg(w.ga(g))
        c.note(**notes)
        finish(c)


def gen_refresh_hostility(ctx):
    fn = ctx.fn(0x005113a0)  # void RefreshMonsterGroupHostility(W8MonsterGroup*)
    gs = ctx.g('g_status')
    fac = ctx.g('g_factions')
    for i in range(ctx.n(250)):
        r = ctx.rng('refreshhost', i)
        c = ctx.case('refreshhost.%d' % i, fn, conv='c', ret='v')
        w = World(ctx, c, istride=0x110, mstride=0x338, rstride=0xb0)
        recs = Records(ctx, c)
        species = r.randrange(0, 1000)
        rec = record_blob(r, species, names=False)
        npc = r.random() < 0.15
        rec.u8(REC_FLAGS, (FLAG_NPC if npc else 0) | r.choice([0, 0, 0x02, 0x10]))
        rec.u8(REC_NPC_KIND, 0xfa)            # NPC path: no binding (assert 0x75d), returns 0
        faction = pick(r, [(40, 0), (10, 1), (45, lambda: r.randrange(2, FACTION_COUNT)),
                           (5, lambda: r.choice([0x100, 0x101, 0x105]))])
        rec.u32(REC_FACTION, faction)
        radius = pick(r, [(30, -1), (30, 0), (40, lambda: r.choice([1, 500, r.randrange(1, 5000), 0x7fffffff]))])
        rec.u32(REC_RADIUS, radius)
        intel = pick(r, [(40, lambda: r.choice([0, 1, 2, 10, 15, 18, 125, 255])), (60, lambda: r.randrange(256))])
        rec.u8(REC_INT, intel)
        cooldown = intel * intel * 60
        recs.get(species, rec)
        n = pick(r, [(1, 0), (2, 1), (8, lambda: r.randrange(2, 7))])
        locs = ids_for(r, n + 2, 1, 9000)
        dying_p = r.choice([0.0, 0.3, 0.7, 1.0])
        keys = []
        live = 0
        for j in range(n):
            cyc, pend, dying = rep_state(r, dying_p)
            live += 0 if dying else 1
            m = w.mon(rep=w.rep(cyc, pend))
            w.mb(m).u8(M_PRESERVED, 1)     # SetMonsterGroupHostility returns before any effect
            k = w.info(locs[j], mon=m)
            w.ib(k).u32(I_SPECIES, species)
            keys.append(k)
        for j in range(r.randrange(0, 2)):
            keys.append(w.info(locs[n + j]))
        w.place(r, keys, unborn_p=0.06)
        g = w.group(r.randrange(1, 3000), members=locs[:n])
        disp = pick(r, [(35, 0), (35, 1), (25, 2), (5, 0xff)])
        if not npc and faction == 0 and radius not in (0, -1):
            disp = 1                      # keeps GetGroupNearestDistance / sight out of the call
        clock = pick(r, [(60, lambda: r.randrange(1000, 50000000)), (20, lambda: r.randrange(0, 5000)),
                         (20, lambda: r.choice([0, 0xffffffff, 0x80000000, 0x7fffffff]))])
        stamp = pick(r, [(20, 0),
                         (45, lambda: (clock - r.choice([0, 1, cooldown, cooldown + 1, max(cooldown - 1, 0),
                                                         r.randrange(0, cooldown + 2)])) & 0xffffffff),
                         (35, lambda: r.getrandbits(32))])
        w.gb(g).u32(G_MONID, species)
        w.gb(g).u8(G_DISP, disp)
        w.gb(g).u32(G_HOST_AT, stamp)
        w.gb(g).u32(G_LEADER_LOC, locs[r.randrange(n)] if n else 0)
        w.gb(g).u32(G_COUNT, n)
        c.set(gs + GS_CLOCK, u32(clock))
        band = None
        f = faction & 0xff
        if faction != 0 and f < FACTION_COUNT:
            band = pick(r, [(40, stamp), (20, (stamp + 1) & 0xffffffff), (20, (stamp - 1) & 0xffffffff),
                            (20, lambda: r.getrandbits(32))])
            c.set(fac + f * FAC_STRIDE + FAC_CLOCK, u32(band))
            faction_setup(ctx, c, r, faction)
        w.wire(reserve=1)
        w.cap_groups()
        c.arg(w.ga(g))
        c.note(members=n, live=live, faction=faction, radius=radius, intel=intel, disp=disp,
               clock=clock, stamp=stamp, band_clock=band, npc=int(npc))
        finish(c)


# ------------------------------------------------------------------

def cases(ctx):
    gen_by_list_index(ctx)
    gen_index_by_id(ctx)
    gen_get_record(ctx)
    gen_recount(ctx)
    gen_is_live(ctx)
    gen_live_at_index(ctx)
    gen_reapply(ctx)
    gen_set_formation(ctx)
    gen_retire(ctx)
    gen_group_name(ctx)
    gen_load_members(ctx)
    gen_reset_turn(ctx)
    gen_control_state(ctx)
    gen_renderable(ctx)
    gen_incapacitated(ctx)
    gen_centre(ctx)
    gen_find_first(ctx)
    gen_find_next(ctx)
    gen_elect_leader(ctx)
    gen_mark_removal(ctx)
    gen_engagement_set(ctx)
    gen_engagement_get(ctx)
    gen_nav_dirty(ctx)
    gen_all_dying(ctx)
    gen_default_disposition(ctx)
    gen_refresh_hostility(ctx)
