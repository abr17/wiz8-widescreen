"""Item.cpp (src/wiz8/engine_code/Item.cpp) and ItemManager.cpp
(src/wiz8/local_code/ItemManager.cpp): the 3D world-item representation helpers and the
world-item list / group bookkeeping, tested on structures built in scratch buffers.

Structures (scripts/w8diff/layout.ps1, checked against the retail asm):
  W8Item 0x20 (m_pRep +0x14, trigger +0x18, countdown +0x1c), W8ItemRep 0x94 (location +4,
  local +0x10, parent +0x1c, rotation +0x28, highlight colour +0x4c, mesh +0x64, bounds
  +0x68/+0x74, radius +0x80, pulse +0x88, flags +0x90), W8WorldItem 0xad (runtime_id +0,
  p3D +4, fActive +8, W8ItemInstance +9, position +0x15, entity_flags +0x25, flags +0x29,
  next +0x31), W8PList {data, capacity, iNumUsed}, W8GrowableVector {vptr, count, capacity,
  data}. gXStatus.plsItemList is redirected to a PList in scratch S0 (data array S0+0x400)
  whose entries point at world items in S1; W8Items live in S0/S2, reps in S0+0x100/S3.
  Names for the two lookups are the real Items.dbs / ItemTables.dbs strings (embedded below,
  extracted from games\\reference Patches\\PATCH.001 / Data\\DATA.SLF: 819 items, 114 tables).

Tested (retail address, function, cases at scale 1):
  Item.cpp
  0x0049f310 W8ItemRep::SetFlags              200  mask/flags edges, bool bytes 2/0x80/0xff
                                                   and garbage in the upper argument bytes
  0x0049f720 W8Item::SetLocation              120  W8AnimRepBase::SetLocation (parent + local);
                                                   NaN/inf/denormal/overflow components, source
                                                   vector = the rep's own location/local/parent
  0x0049f730 W8Item::UpdateAnimation          300  pulse levels reached by the real 0.05 steps
                                                   from Random(20)*0.05, threshold neighbours,
                                                   NaN/inf (15 forced NaN levels while
                                                   decreasing); ROTATE only with gfKeyState[VK_CONTROL]
                                                   pressed (the rotation path needs a live srNode)
  0x0049fba0 W8Item::GetSearchPosition        200
  0x0049fdb0 W8Item::SetHighlight             150
  0x004a00c0 GetItemWorldBounds               200  incl. null item and aliased lower/upper
  0x004a0050 W8Item::IsRadarBlipLit           150  guiCurrentTime set (only the WM_TIMER proc
                                                   writes it), unsigned wrap edges
  0x004a0030 W8Item::LightRadarBlip           100
  ItemManager.cpp
  0x004f69f0 InitializeItemManagerState       150  screen id edges, g_level_block null/scratch,
                                                   plsItemList scratch/null (PLCreate, leaks a
                                                   small PList per null case)
  0x004f8130 ItemHasFlags                     150
  0x004f8170 SetItemFlags                     150
  0x004f94a0 SetWorldItemFalling              100
  0x004f81c0 SetItemAndEntityFlags            200  p3D null or W8Item->rep in scratch
  0x004f8300 ItemInfoGetNumInGroup            120  chains of 1..79 nodes
  0x004f8340 ItemInfoAddToGroup               150  separate item / item already in the chain /
                                                   tail / head, group = a middle node
  0x004f83a0 ItemInfoRemoveFromGroup          200  head, middle, tail, not in chain, null head
  0x004f8440 ItemInfoMakeGroupList            150  growth from an empty vector (data 0),
                                                   negative / 0x7fffffff count
  0x004f88a0 FindItemTableByName              250  all 114 names, case variants, count edges
                                                   (incl. negative as int), heap name pointers
  0x004f8220 FindItemRecordByName             363  internal names, display names of records
                                                   with an empty internal name, "" (record 415),
                                                   count edges; g_wide_string_buffer (the last
                                                   ConvertWideStringToString result) compared
  0x004f82b0 GetNextWorldItem                 200  incl. negative cursor / negative iNumUsed and
                                                   a null list (retail compares signed: jge)
  0x004f91e0 ItemInfoIsWorldPersistent        200  real ids + overridden record flags byte
  0x004f7fe0 ItemInfo                         150  incl. out-of-range indexes (asserts 961/965,
                                                   PLGet with a negative int index)
  0x004f8060 ItemIndex                        150  duplicates, missing ids (assert 992)
  0x004f71e0 SetWorldItemHighlight            150
  0x004f94c0 RebuildAllWorldItemInstances     200  ReplaceOrCreateItem per list entry (seeded
                                                   RollDice), overridden quantity kind / dice /
                                                   auto-identify, uiItemsInDatabase below an id
  Total 4453 cases.

Pointer fields: every structure lives in scratch and is compared with dump (final bytes).
Dwords that end up holding a scratch address (next links, vector entries, p3D, m_pRep) differ
between the processes and are ignored; links that end up null are compared. Returned
pointers (ret 'p') are compared as S<n>+offset by the core.
Edge labels (note edge=...): bool_byte / bool_arg_upper (non-canonical bool bytes or garbage
above the low byte of a bool argument), nan_decreasing (UpdateAnimation: retail fcomp +
test ah,41h clamps an unordered pulse level to 0.25), negative_cursor / negative_count
(GetNextWorldItem: retail compares cursor and length signed), screen_id_edge,
count_edge, alias.

Skipped:
  Item.cpp
  0x0049f440 W8Item::~W8Item           - not in port map (inlined); deletes the rep
  0x0049f120 W8ItemRep::~W8ItemRep     - not in port map; releases the SurRender mesh
  0x0049f170 W8ItemRep::ReadFromFile   - not in port map; reads the .itm mesh file
  0x0049fa30 W8Item::DetachMesh        - SurRender scene graph (setFlag/setParent on a live srNode)
  0x0049faa0 W8Item::ApplyRepTransform - srNode setLocation/setRotation; needs a live srNode
  0x0049f900 W8Item::AttachMesh        - attaches the mesh to the world dynamic scene
  0x0049fb20 W8Item::GetMesh           - trivial getter
  0x0049f2b0 W8ItemRep::RefreshBounds  - needs a loaded srModelInstance/srModel (getBoundingBox)
  0x0049f350 W8Item::W8Item            - object creation (new rep, AllocateGrObjectId, Random)
  0x0049f4a0 LoadItemFromFile          - file I/O (Data\\Items3D\\*.itm)
  0x0049f5d0 ReadItemFromFile          - file I/O + object creation
  0x0049fb30 W8Item::GetCachedLocalBounds - trivial 6-dword copy; exercised through
                                         GetSearchPosition and GetItemWorldBounds
  0x0049fb80 W8Item::GetBoundsRadius   - trivial getter
  0x0049fbf0 W8Item::SetYaw            - srNode::setRotation on the mesh and its children
  0x0049ff40 W8Item::IsSelected        - GetPickedModelInstance (mouse picking)
  0x0049ffa0 W8Item::DistanceToCamera  - reads the live camera (world->camera->getLocation)
  0x004a0070 RunItemTrigger            - a non-null trigger runs a level script (Trigger::Run);
                                         the null paths are trivial
  ItemManager.cpp
  0x004f88f0 GenerateItemsFromTable    - creates world items through CreateWorldItem whose
                                         SettleWorldItem runs on an uninitialised stack position
                                         (retail too) and can AddItemToSector the leaked items
                                         into live octree sectors; depends on stack garbage
  0x004f6cc0 FreeWorldItemGroup        - free() of every node
  0x004f8410 ItemInfoGroupGetNext      - trivial getter (item->next)
  0x004f9210 CopyWorldItemInstance     - malloc'd 12-byte copy: ret 'p' would compare 20 bytes
                                         of heap beyond the block; the block leaks
  0x004f6cf0 ActivateItem              - loads the .ITM model, adds it to the world, octree sun
                                         line of sight
  0x004f70d0 DeactivateWorldItem       - detaches/deletes the 3D object (RemoveItemFromWorld)
  0x004f7370 PickNearestItemUnderCursor - mouse picking + live camera distance
  0x004f7480 UpdateNearbyWorldItems    - camera distance, activates/deactivates items (file loads)
  0x004f7610 DropHeldItem              - cursor, camera, octree trace, creates a world item, sound
  0x004f7c50 OnItemPickerDialogDestroyed - dialog destroy callback, removes world items
  0x004f7910 InteractWithWorldItem     - opens the item picker dialog / runs triggers / removes
                                         world items
  0x004f6a50 ReleaseItemLists          - frees the whole world item list
  0x004f8560 IsWorldItemWithinReach    - camera position + octree line of sight (ShowTargetMarker)
                                         whenever the item is in reach; the early-out is one
                                         float compare
  0x004f8650 AnyWorldItemVisible       - camera + line of sight
  0x004f9240 AdvanceFallingWorldItem   - octree SettleToGround, frame delta of the game-time
                                         accumulator, Add/RemoveItemFromSector on live sectors
  0x004f93d0 SettleWorldItem           - octree + live sector lists
  0x004f6b90 CreateWorldItem           - malloc + SettleWorldItem (sectors) + list append
  0x004f6c50 SpawnItem                 - same, through CreateWorldItem
  0x004f8cb0 DropMonsterLoot           - spawns world items, party gold notice and sound
"""
import math
import struct

from w8diff.api import Blob

# --------------------------------------------------------------------------- layouts
# W8ItemRep (wiz8/engine_code/Item.h, W8AnimRepBase in AnimRep.hpp)
REP_SIZE = 0x94
REP_STRIDE = 0xa0
R_LOCATION = 0x04
R_LOCAL = 0x10
R_PARENT = 0x1c
R_ROTATION = 0x28
R_COLOUR = 0x4c
R_SCALE = 0x5c
R_FLAG = 0x60
R_BMIN = 0x68
R_BMAX = 0x74
R_RADIUS = 0x80
R_PULSE = 0x88
R_FLAGS = 0x90
REP_FLOATS = list(range(0x04, 0x60, 4)) + list(range(0x68, 0x84, 4)) + [R_PULSE]

# W8Item
ITEM_SIZE = 0x20
ITEM_STRIDE = 0x20
I_REP = 0x14
I_TRIGGER = 0x18
I_COUNTDOWN = 0x1c

# W8ItemRep::flags / W8WorldItem::entity_flags
E_PULSE = 0x01
E_ROTATE = 0x02
E_NO_PICKUP = 0x04
E_RADAR = 0x08
E_GREEN = 0x10
E_INCREASING = 0x20
E_MESH = 0x40
E_BLUE = 0x80

# W8WorldItem (wiz8/item_spawning.h, pack 1)
WI_SIZE = 0xad
WI_STRIDE = 0xb0
W_ID = 0x00
W_P3D = 0x04
W_ACTIVE = 0x08
W_ITEM = 0x09
W_POS = 0x15
W_ENTITY = 0x25
W_FLAGS = 0x29
W_MARKER = 0x2d
W_NEXT = 0x31
W_VVEL = 0x35
W_SECTOR = 0x39
WF_FALLING = 0x02

# W8PList / W8GrowableVector
PL_DATA = 0x0
PL_CAP = 0x4
PL_USED = 0x8
PL_ARRAY = 0x400        # data array inside S0; data[-1..-4] stay inside S0
GV_COUNT = 0x4
GV_CAP = 0x8
GV_DATA = 0xc
GV_ARRAY = 0x100

# gXStatus / g_status / level block / misc
GX_ITEMS_COUNT = 0x8c0
GX_TABLES_COUNT = 0x8c4
GX_PENDING = 0x8f1
GX_ITEM_LIST = 0x8fd
GS_NEXT_WORLD_ITEM_ID = 0x2352
LB_SELECTED = 0x268
SCREEN_MAIN_GAME = 7
VK_CONTROL = 0x11
WIDE_BUF_LEN = 64

# Items.dbs record
REC_SIZE = 0x10d
REC_FLAGS = 0x41
REC_QKIND = 0x66
REC_QDICE = 0x67
REC_INTERNAL = 0x8d
ITEM_COUNT = 819
CONTAINER_ITEM = 572    # the only record with flag 0x20
TABLE_COUNT = 114


def _ranges(*parts):
    out = []
    for p in parts:
        if isinstance(p, tuple):
            out.extend(range(p[0], p[1] + 1))
        else:
            out.append(p)
    return out


# Items.dbs ids with quantity_kind != 0 (stack/charges/uses/shots)
QTY_ITEMS = _ranges(16, 19, 24, 27, (33, 34), (42, 44), (46, 47), (60, 61), (68, 69), 74, 81,
                    (85, 88), (99, 109), (120, 121), (123, 141), 208, (254, 260), (262, 265),
                    (269, 270), 273, (276, 278), 280, 282, (285, 287), 289, (291, 292), 294,
                    (304, 306), 310, 317, 329, (331, 332), (334, 364), (384, 386), (388, 396),
                    (402, 414), (416, 419), (424, 425), (428, 429), (431, 432), 446, 451,
                    (464, 467), 469, 488, 492, 496, 499, 502, 505, (590, 593), (597, 598), 614,
                    (625, 626), (638, 639), (641, 645), 649, 655, 662, 682, 687, 693, (743, 744),
                    753, 755, (762, 766), 770, 772, 787, 789, 804, (812, 813), 818)

# --------------------------------------------------------------------------- values


class Bits(int):
    """A raw float32 bit pattern (NaN payloads, infinities, denormals)."""


SPECIAL = [Bits(x) for x in (0x7fc00000, 0xffc00000, 0x7fc12345, 0x7f800000, 0xff800000,
                             0x00000001, 0x80000001, 0x007fffff, 0x7f7fffff, 0x80000000)]
NAN_BITS = (0x7fc00000, 0xffc00000, 0x7fc12345)
FEDGE = [0.0, 1.0, -1.0, 0.5, 1e-30, -1e-30, 1e30, -1e30, 123456.789, -98765.4321, 0.66]
COMBOS = [0, E_PULSE | E_ROTATE, E_PULSE | E_ROTATE | E_MESH, E_MESH | E_PULSE | E_INCREASING,
          E_MESH | E_GREEN, E_MESH | E_BLUE, E_MESH | E_GREEN | E_BLUE, E_NO_PICKUP | E_RADAR,
          0xff, E_PULSE | E_ROTATE | E_INCREASING | E_MESH | E_RADAR]
BOOL_EDGE = [2, 0x80, 0xff]
BOOL_UPPER = [0x100, 0xff00, 0xffffff00, 0x80000000, 0x101, 0x80000001]


def u8(v):
    return bytes([int(v) & 0xff])


def u32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def f32(x):
    """Round to float32 (overflow -> inf)."""
    try:
        return struct.unpack('<f', struct.pack('<f', x))[0]
    except OverflowError:
        return math.copysign(math.inf, x)


def fbytes(x):
    if isinstance(x, Bits):
        return struct.pack('<I', int(x) & 0xffffffff)
    return struct.pack('<f', f32(float(x)))


def put_f(b, off, x):
    b[off:off + 4] = fbytes(x)


def fdesc(x):
    return 'bits:%08x' % int(x) if isinstance(x, Bits) else repr(f32(float(x)))


def is_nan(x):
    if isinstance(x, Bits):
        v = int(x) & 0x7fffffff
        return v > 0x7f800000
    return x != x


def _fval(r, lo, hi, edge_p=0.1, special_p=0.03):
    x = r.random()
    if x < special_p:
        return r.choice(SPECIAL)
    if x < special_p + edge_p:
        return r.choice(FEDGE)
    return r.uniform(lo, hi)


def _world_pos(r):
    return (r.uniform(-20000, 20000), r.uniform(-3000, 3000), r.uniform(-20000, 20000))


def _entity_flags(r):
    x = r.random()
    if x < 0.55:
        return r.getrandbits(8)
    if x < 0.75:
        return r.choice(COMBOS)
    if x < 0.85:
        return 0
    if x < 0.95:
        return r.getrandbits(32)
    return 0xffffffff


def _mask(r):
    x = r.random()
    if x < 0.4:
        return 1 << r.randrange(8)
    if x < 0.6:
        return r.choice([3, 0x41, 0x90, 0x30, 0x11, 0x22, 0xff, 0x7f])
    if x < 0.7:
        return r.choice([0, 0xffffffff, 0x80000000, 0x100, 0xffffff00])
    if x < 0.85:
        return r.getrandbits(8)
    return r.getrandbits(32)


def _bool_arg(r, p_true=0.5):
    """bool argument: 0/1, non-canonical true bytes, garbage above the low byte."""
    x = r.random()
    if x < 0.85:
        return (1 if r.random() < p_true else 0), None
    if x < 0.94:
        return r.choice(BOOL_EDGE), 'bool_byte'
    return r.choice(BOOL_UPPER), 'bool_arg_upper'


def _pulse_states():
    """(pulse_level, increasing) pairs W8Item::UpdateAnimation really meets: the rep starts
    at float(Random(20) * 0.05) and steps by 0.05f between 0.25 and 1.0."""
    step = f32(0.05)
    seen = set()
    for k in range(20):
        p, inc = f32(k * 0.05), True
        for _ in range(48):
            seen.add((p, inc))
            if inc:
                p = f32(p + step)
                if p >= 1.0:
                    p, inc = 1.0, False
            else:
                p = f32(p - step)
                if p <= 0.25:
                    p, inc = 0.25, True
    return sorted(seen)


PULSE_STATES = _pulse_states()
PULSE_EDGES = [1.0, 0.95, f32(0.95) + 2 ** -25, f32(0.95) - 2 ** -25, 0.25, 0.3, 0.29999998,
               0.30000004, 0.2, 0.0, 1.05, 2.0, -1.0, 0.25000003, 0.24999999, 0.99999994,
               1.0000001, 0.9, 0.7, 0.275, Bits(0x80000000)]


# --------------------------------------------------------------------------- builders
def _rep_blob(r, flags, pulse=None):
    b = Blob(bytes(REP_SIZE))
    loc = _world_pos(r)
    parent = (0.0, 0.0, 0.0) if r.random() < 0.7 else _world_pos(r)
    for k in range(3):
        put_f(b, R_LOCATION + 4 * k, loc[k])
        put_f(b, R_LOCAL + 4 * k, loc[k] - parent[k])
        put_f(b, R_PARENT + 4 * k, parent[k])
    yaw = r.uniform(-math.pi, math.pi)
    cs, sn = math.cos(yaw), math.sin(yaw)
    for k, v in enumerate((cs, 0.0, -sn, 0.0, 1.0, 0.0, sn, 0.0, cs)):
        put_f(b, R_ROTATION + 4 * k, v)
    colour = r.choice([(0.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 1.0), (0.0, 0.0, 1.0, 1.0),
                       (r.random(), r.random(), r.random(), r.random())])
    for k in range(4):
        put_f(b, R_COLOUR + 4 * k, colour[k])
    put_f(b, R_SCALE, 1.0 if r.random() < 0.8 else r.uniform(0.5, 2.0))
    b[R_FLAG:R_FLAG + 4] = bytes([r.choice([0, 1]), r.choice([0, 1]), r.getrandbits(8),
                                  r.getrandbits(8)])
    bmin = (-r.uniform(2, 150), -r.uniform(0, 80), -r.uniform(2, 150))
    bmax = (r.uniform(2, 150), r.uniform(0, 200), r.uniform(2, 150))
    for k in range(3):
        put_f(b, R_BMIN + 4 * k, bmin[k])
        put_f(b, R_BMAX + 4 * k, bmax[k])
    put_f(b, R_RADIUS, 0.5 * math.sqrt(sum((bmax[k] - bmin[k]) ** 2 for k in range(3))))
    b[0x84:0x88] = bytes(r.getrandbits(8) for _ in range(4))
    put_f(b, R_PULSE, f32(r.randrange(20) * 0.05) if pulse is None else pulse)
    b[0x8c:0x90] = bytes(r.getrandbits(8) for _ in range(4))
    b.u32(R_FLAGS, flags)
    return b


def _item_blob(r, countdown=None):
    b = Blob(bytes(ITEM_SIZE))
    b.u8(4, 2)                                   # kind
    b.u32(8, r.randrange(1, 5000))               # id
    b.u32(I_COUNTDOWN, r.getrandbits(32) if countdown is None else countdown)
    return b


def _world_item(r, rid=None, item_no=None, flags=None, entity=None):
    b = Blob(bytes(WI_SIZE))
    b.u32(W_ID, r.randrange(1, 3000) if rid is None else rid)
    b.u8(W_ACTIVE, r.choice([0, 0, 1]))
    b.u32(W_ITEM, r.randrange(ITEM_COUNT) if item_no is None else item_no)
    b[W_ITEM + 4:W_ITEM + 12] = bytes([r.randrange(0, 20), r.randrange(0, 20), r.choice([0, 1]),
                                       r.choice([0, 0, 1]), 0, r.choice([0, 0, 1]), 0,
                                       r.choice([0, 0, 1])])
    pos = _world_pos(r)
    for k in range(3):
        put_f(b, W_POS + 4 * k, pos[k])
    b[0x21:0x25] = bytes(r.getrandbits(8) for _ in range(4))
    b.u32(W_ENTITY, r.choice([3, 3, 0x43, 0x0b, r.getrandbits(8)]) if entity is None else entity)
    b.u32(W_FLAGS, r.choice([0, 0, 1, 2, 4, 5, r.getrandbits(3)]) if flags is None else flags)
    b.u32(W_MARKER, r.choice([0, 1]))
    put_f(b, W_VVEL, 0.0 if r.random() < 0.7 else r.uniform(-500, 50))
    b.u32(W_SECTOR, -1 if r.random() < 0.3 else r.randrange(0, 400))
    b[0x3d:WI_SIZE] = bytes(r.getrandbits(8) for _ in range(WI_SIZE - 0x3d))
    return b


def _node(ctx, slot, buf=1):
    return ctx.scratch(buf) + slot * WI_STRIDE


def _build_chain(ctx, c, r, n, content=True):
    """n world items at random slots of S1 linked in random order; returns the slots in
    chain order and the length of the S1 region they occupy."""
    nslots = max(2 * n, n + 1)
    slots = r.sample(range(nslots), n)
    length = (max(slots) + 1) * WI_STRIDE
    if content:
        region = bytearray(length)
        for k, s in enumerate(slots):
            region[s * WI_STRIDE:s * WI_STRIDE + WI_SIZE] = _world_item(r, rid=100 + k)
        c.set(ctx.scratch(1), bytes(region))
    for k in range(n - 1):
        c.setp(_node(ctx, slots[k]) + W_NEXT, _node(ctx, slots[k + 1]))
    return slots, length


def _setup_list(ctx, c, slots, used=None, capacity=None):
    """gXStatus.plsItemList -> PList in S0 whose array (S0+0x400) points at world items
    S1 + slot*WI_STRIDE (None = null entry)."""
    gx = ctx.g('gXStatus')
    pl = ctx.scratch(0)
    n = len(slots)
    used = n if used is None else used
    capacity = n + 3 if capacity is None else capacity
    c.set(pl + PL_CAP, struct.pack('<II', capacity & 0xffffffff, used & 0xffffffff))
    c.setp(pl + PL_DATA, pl + PL_ARRAY)
    for k, s in enumerate(slots):
        if s is not None:
            c.setp(pl + PL_ARRAY + 4 * k, _node(ctx, s))
    c.setp(gx + GX_ITEM_LIST, pl)


def _negative_slots(ctx, c, r, base_slot):
    """data[-1..-4] of the scratch PList -> world items (PLGet with a negative int index)."""
    pl = ctx.scratch(0)
    for k in range(1, 5):
        if r.random() < 0.8:
            c.setp(pl + PL_ARRAY - 4 * k, _node(ctx, base_slot + k))


def cases(ctx):
    _rep_set_flags(ctx)
    _item_set_location(ctx)
    _item_update_animation(ctx)
    _item_search_position(ctx)
    _item_set_highlight(ctx)
    _item_world_bounds(ctx)
    _item_radar_blip_lit(ctx)
    _item_light_radar_blip(ctx)
    _init_item_manager(ctx)
    _item_has_flags(ctx)
    _set_item_flags(ctx)
    _set_world_item_falling(ctx)
    _set_item_entity_flags(ctx)
    _group_count(ctx)
    _group_add(ctx)
    _group_remove(ctx)
    _group_make_list(ctx)
    _find_item_table(ctx)
    _find_item_record(ctx)
    _next_world_item(ctx)
    _item_is_world_persistent(ctx)
    _item_info(ctx)
    _item_index(ctx)
    _set_world_item_highlight(ctx)
    _rebuild_world_item_instances(ctx)


# =========================================================================== Item.cpp
def _rep_set_flags(ctx):
    """unsigned W8ItemRep::SetFlags(unsigned mask, bool enabled): thiscall, ret 8; tests al."""
    fn = ctx.fn(0x0049F310)
    rep = ctx.scratch(0) + 0x100
    for i in range(ctx.n(200)):
        r = ctx.rng('repsetflags', i)
        c = ctx.case('repsetflags.%d' % i, fn, conv='t', ret='i')
        flags = _entity_flags(r)
        mask = _mask(r)
        en, edge = _bool_arg(r)
        c.set(rep, bytes(_rep_blob(r, flags)))
        c.arg(rep).arg(mask).arg(en)
        c.dump(rep, REP_SIZE, 'rep', floats=REP_FLOATS)
        c.note(flags='%x' % flags, mask='%x' % mask, enabled='%x' % en)
        if edge:
            c.note(edge=edge)


def _item_set_location(ctx):
    """void W8Item::SetLocation(const srVector3T<float>*): m_pRep->local = *v,
    location = parent + local (retail 0x004B8850 reads all three inputs first)."""
    fn = ctx.fn(0x0049F720)
    item = ctx.scratch(0)
    rep = item + 0x100
    vec = ctx.scratch(1)
    for i in range(ctx.n(120)):
        r = ctx.rng('setlocation', i)
        c = ctx.case('setlocation.%d' % i, fn, conv='t', ret='v')
        blob = _rep_blob(r, _entity_flags(r))
        for k in range(3):
            if r.random() < 0.1:
                put_f(blob, R_PARENT + 4 * k, _fval(r, -1e4, 1e4, 0.5, 0.35))
        alias = None
        if r.random() < 0.12:
            alias = r.choice(['location', 'local', 'parent'])
            src = rep + {'location': R_LOCATION, 'local': R_LOCAL, 'parent': R_PARENT}[alias]
        else:
            src = vec
            v = [_fval(r, -25000, 25000, 0.12, 0.06) for _ in range(3)]
            c.set(vec, b''.join(fbytes(x) for x in v) + bytes(r.getrandbits(8) for _ in range(4)))
            c.note(v=','.join(fdesc(x) for x in v))
        c.set(item, bytes(_item_blob(r)))
        c.setp(item + I_REP, rep)
        c.set(rep, bytes(blob))
        c.arg(item).arg(src)
        c.dump(rep, REP_SIZE, 'rep', floats=REP_FLOATS)
        if alias:
            c.note(alias=alias, edge='alias')


def _item_update_animation(ctx):
    """void W8Item::UpdateAnimation(): pulse 0.05 steps between 0.25 and 1.0, then
    SetHighlight(true). ROTATE is only set together with VK_CONTROL pressed (else it rotates
    the live srNode mesh)."""
    fn = ctx.fn(0x0049F730)
    keys = ctx.g('gfKeyState')
    item = ctx.scratch(0)
    rep = item + 0x100
    for i in range(ctx.n(300)):
        r = ctx.rng('updateanimation', i)
        c = ctx.case('updateanimation.%d' % i, fn, conv='t', ret='v')
        x = r.random()
        forced_nan = i % 20 == 7     # 15 cases: NaN level while decreasing
        if forced_nan:
            pulse, inc = Bits(r.choice(NAN_BITS)), False
            kind = 'special'
        elif x < 0.65:
            pulse, inc = r.choice(PULSE_STATES)
            if r.random() < 0.1:
                inc = not inc
            kind = 'sequence'
        elif x < 0.9:
            pulse, inc = r.choice(PULSE_EDGES), r.random() < 0.5
            kind = 'edge'
        else:
            pulse, inc = r.choice(SPECIAL), r.random() < 0.5
            kind = 'special'
        flags = 0
        if forced_nan or r.random() < 0.9:
            flags |= E_MESH
        if forced_nan or r.random() < 0.8:
            flags |= E_PULSE
        if inc:
            flags |= E_INCREASING
        rotate = r.random() < 0.3
        if rotate:
            flags |= E_ROTATE
        for bit, p in ((E_GREEN, 0.3), (E_BLUE, 0.2), (E_NO_PICKUP, 0.2), (E_RADAR, 0.2)):
            if r.random() < p:
                flags |= bit
        if r.random() < 0.08:
            flags |= r.getrandbits(32) & ~0xff
        ctrl = r.choice([1, 1, 1, 0x80, 0xff]) if rotate else r.choice([0, 0, 1])
        c.set(keys + VK_CONTROL, u8(ctrl))
        c.set(item, bytes(_item_blob(r)))
        c.setp(item + I_REP, rep)
        c.set(rep, bytes(_rep_blob(r, flags, pulse)))
        c.arg(item)
        c.dump(rep, REP_SIZE, 'rep', floats=REP_FLOATS)
        c.note(flags='%x' % flags, pulse=fdesc(pulse), ctrl=ctrl, kind=kind)
        if is_nan(pulse) and not inc and (flags & (E_MESH | E_PULSE)) == E_MESH | E_PULSE:
            c.note(edge='nan_decreasing')


def _item_search_position(ctx):
    """unsigned char W8Item::GetSearchPosition(srVector3T<float>*): location with
    y += (max.y - min.y) * 0.66f."""
    fn = ctx.fn(0x0049FBA0)
    item = ctx.scratch(0)
    rep = item + 0x100
    out = ctx.scratch(1)
    for i in range(ctx.n(200)):
        r = ctx.rng('searchposition', i)
        c = ctx.case('searchposition.%d' % i, fn, conv='t', ret='b')
        blob = _rep_blob(r, _entity_flags(r))
        if r.random() < 0.1:   # inverted extent
            lo, hi = blob[R_BMIN + 4:R_BMIN + 8], blob[R_BMAX + 4:R_BMAX + 8]
            blob[R_BMIN + 4:R_BMIN + 8], blob[R_BMAX + 4:R_BMAX + 8] = hi, lo
        for off, lo, hi in ((R_BMIN + 4, -100, 0), (R_BMAX + 4, 0, 250), (R_LOCATION + 4, -3000, 3000)):
            if r.random() < 0.12:
                put_f(blob, off, _fval(r, lo, hi, 0.5, 0.35))
        c.set(out, bytes(r.getrandbits(8) for _ in range(16)))
        c.set(item, bytes(_item_blob(r)))
        c.setp(item + I_REP, rep)
        c.set(rep, bytes(blob))
        c.arg(item).arg(out)
        c.dump(out, 16, 'location', floats=[0, 4, 8])
        c.dump(rep, REP_SIZE, 'rep', floats=REP_FLOATS)


def _item_set_highlight(ctx):
    """void W8Item::SetHighlight(bool): colour (0,0,1,1) for BLUE, (0,1,0,1) for GREEN."""
    fn = ctx.fn(0x0049FDB0)
    item = ctx.scratch(0)
    rep = item + 0x100
    for i in range(ctx.n(150)):
        r = ctx.rng('sethighlight', i)
        c = ctx.case('sethighlight.%d' % i, fn, conv='t', ret='v')
        flags = _entity_flags(r)
        en, edge = _bool_arg(r, 0.7)
        c.set(item, bytes(_item_blob(r)))
        c.setp(item + I_REP, rep)
        c.set(rep, bytes(_rep_blob(r, flags)))
        c.arg(item).arg(en)
        c.dump(rep, REP_SIZE, 'rep', floats=REP_FLOATS)
        c.note(flags='%x' % flags, enabled='%x' % en)
        if edge:
            c.note(edge=edge)


def _item_world_bounds(ctx):
    """bool GetItemWorldBounds(W8Item*, srVector3T<float>* lower, srVector3T<float>* upper):
    cached local bounds translated by the rep location (lower written first, then upper,
    then lower += loc, upper += loc - aliased outputs keep that order)."""
    fn = ctx.fn(0x004A00C0)
    item = ctx.scratch(0)
    rep = item + 0x100
    out = ctx.scratch(1)
    modes = ['none'] * 16 + ['same', 'upper+4', 'upper+8', 'lower+4']
    for i in range(ctx.n(200)):
        r = ctx.rng('worldbounds', i)
        c = ctx.case('worldbounds.%d' % i, fn, conv='c', ret='b')
        mode = r.choice(modes)
        lower, upper = 0x00, 0x40
        if mode == 'same':
            upper = lower
        elif mode == 'upper+4':
            upper = lower + 4
        elif mode == 'upper+8':
            upper = lower + 8
        elif mode == 'lower+4':
            lower, upper = 0x44, 0x40
        c.set(out, b''.join(fbytes(r.uniform(-1000, 1000)) for _ in range(0x20)))
        null = i < 8
        if not null:
            blob = _rep_blob(r, _entity_flags(r))
            for off in list(range(R_BMIN, R_BMIN + 24, 4)) + [R_LOCATION, R_LOCATION + 4, R_LOCATION + 8]:
                if r.random() < 0.06:
                    put_f(blob, off, _fval(r, -200, 200, 0.4, 0.5))
            c.set(item, bytes(_item_blob(r)))
            c.setp(item + I_REP, rep)
            c.set(rep, bytes(blob))
            c.arg(item)
        else:
            c.arg(0)
        c.arg(out + lower).arg(out + upper)
        c.dump(out, 0x80, 'bounds', floats=list(range(0, 0x80, 4)))
        c.note(mode=mode, null=int(null))
        if mode != 'none':
            c.note(edge='alias')


TIME_EDGES = [0, 1, 2, 9999, 10000, 0x7fffffff, 0x80000000, 0xfffffff0, 0xffffd8f0, 0xffffd8ef,
              0xffffffff]


def _clock_time(r):
    return r.choice(TIME_EDGES) if r.random() < 0.3 else r.randrange(0, 200000000)


def _item_radar_blip_lit(ctx):
    """bool W8Item::IsRadarBlipLit(): ClockIsTicking(countdown) != 0, i.e. countdown >
    guiCurrentTime (unsigned)."""
    fn = ctx.fn(0x004A0050)
    now = ctx.g('guiCurrentTime')
    item = ctx.scratch(0)
    for i in range(ctx.n(150)):
        r = ctx.rng('radarbliplit', i)
        c = ctx.case('radarbliplit.%d' % i, fn, conv='t', ret='b')
        t = _clock_time(r)
        x = r.random()
        if x < 0.5:
            cd = t + r.randrange(-20000, 20001)
        elif x < 0.8:
            cd = t + r.choice([0, 1, -1, 2, -2, 10000, 10001, 9999, -10000])
        else:
            cd = r.choice([0, 1, 0x7fffffff, 0x80000000, 0xffffffff, 0x80000001])
        cd &= 0xffffffff
        c.set(now, u32(t))
        c.set(item, bytes(_item_blob(r, countdown=cd)))
        c.arg(item)
        c.note(time='%x' % t, countdown='%x' % cd)


def _item_light_radar_blip(ctx):
    """void W8Item::LightRadarBlip(): countdown = guiCurrentTime + 10000 (wraps)."""
    fn = ctx.fn(0x004A0030)
    now = ctx.g('guiCurrentTime')
    item = ctx.scratch(0)
    for i in range(ctx.n(100)):
        r = ctx.rng('lightradarblip', i)
        c = ctx.case('lightradarblip.%d' % i, fn, conv='t', ret='v')
        t = _clock_time(r)
        c.set(now, u32(t))
        c.set(item, bytes(_item_blob(r)))
        c.arg(item)
        c.dump(item, ITEM_SIZE, 'item')
        c.note(time='%x' % t)


# ==================================================================== ItemManager.cpp
def _init_item_manager(ctx):
    """bool InitializeItemManagerState(): next_world_item_id = 1, item_manager_pending = 0,
    selected_item = -1 on the main game screen, PListClear / PLCreate."""
    fn = ctx.fn(0x004f69f0)
    gs = ctx.g('g_status')
    gx = ctx.g('gXStatus')
    screen = ctx.g('g_current_screen_state')
    lb = ctx.g('g_level_block')
    pl = ctx.scratch(0)
    block = ctx.scratch(1)
    for i in range(ctx.n(150)):
        r = ctx.rng('inititemmanager', i)
        c = ctx.case('inititemmanager.%d' % i, fn, conv='c', ret='b')
        x = r.random()
        if x < 0.6:
            sid = SCREEN_MAIN_GAME
        elif x < 0.85:
            sid = r.choice([0, 1, 6, 8, 9])
        else:
            sid = r.choice([0x107, 0x80000007, 0xffffffff, 0x10007])
            c.note(edge='screen_id_edge')
        c.set(screen, u32(sid))
        c.set(gs + GS_NEXT_WORLD_ITEM_ID, u32(r.choice([1, 0, 2, r.randrange(1, 5000), 0x7fffffff, 0xffffffff])))
        c.set(gx + GX_PENDING, u32(r.choice([0, 1, r.randrange(0, 40), 0xffffffff, 0x80000000])))
        scratch_block = r.random() < 0.75
        if scratch_block:
            c.set(block + LB_SELECTED - 8, bytes(r.getrandbits(8) for _ in range(8)) +
                  u32(r.choice([-1, 0, 1, r.randrange(1, 3000)])) + bytes(r.getrandbits(8) for _ in range(4)))
            c.setp(lb, block)
        else:
            c.set(lb, u32(0))
        scratch_list = r.random() < 0.75
        if scratch_list:
            c.set(pl + PL_CAP, struct.pack('<ii', r.choice([10, 20, 64]), r.choice([0, 1, 5, 17, 60])))
            c.setp(pl + PL_DATA, pl + PL_ARRAY)
            c.setp(gx + GX_ITEM_LIST, pl)
        else:
            c.set(gx + GX_ITEM_LIST, u32(0))
        c.cap(gs + GS_NEXT_WORLD_ITEM_ID, 4, 'next_world_item_id')
        c.cap(gx + GX_PENDING, 4, 'item_manager_pending')
        c.cap(gx + GX_ITEM_LIST, 4, 'plsItemList', ignore=[0])
        c.dump(pl, 12, 'plist', ignore=[0])
        c.dump(block + LB_SELECTED - 8, 16, 'level_block')
        c.note(screen='%x' % sid, block='scratch' if scratch_block else 'null',
               list='scratch' if scratch_list else 'null')


def _item_has_flags(ctx):
    """bool ItemHasFlags(W8WorldItem*, unsigned mask): (flags & mask) != 0."""
    fn = ctx.fn(0x004f8130)
    item = ctx.scratch(1)
    for i in range(ctx.n(150)):
        r = ctx.rng('itemhasflags', i)
        c = ctx.case('itemhasflags.%d' % i, fn, conv='c', ret='b')
        flags = r.choice([0, 1, 2, 3, 4, 5, 6, 7]) if r.random() < 0.6 else r.getrandbits(32)
        mask = r.choice([1, 2, 4, 3, 5, 7, 0, 0xffffffff, 0x80000000, 0x100]) if r.random() < 0.7 \
            else r.getrandbits(32)
        c.set(item, bytes(_world_item(r, flags=flags)))
        c.arg(item).arg(mask)
        c.note(flags='%x' % flags, mask='%x' % mask)


def _set_item_flags(ctx):
    """void SetItemFlags(W8WorldItem*, unsigned mask, bool enabled)."""
    fn = ctx.fn(0x004f8170)
    item = ctx.scratch(1)
    for i in range(ctx.n(150)):
        r = ctx.rng('setitemflags', i)
        c = ctx.case('setitemflags.%d' % i, fn, conv='c', ret='v')
        flags = r.choice([0, 1, 2, 3, 4, 5, 6, 7]) if r.random() < 0.6 else r.getrandbits(32)
        mask = _mask(r)
        en, edge = _bool_arg(r)
        c.set(item, bytes(_world_item(r, flags=flags)))
        c.arg(item).arg(mask).arg(en)
        c.dump(item, WI_SIZE, 'item')
        c.note(flags='%x' % flags, mask='%x' % mask, enabled='%x' % en)
        if edge:
            c.note(edge=edge)


def _set_world_item_falling(ctx):
    """void SetWorldItemFalling(W8WorldItem*, bool): flag 2."""
    fn = ctx.fn(0x004f94a0)
    item = ctx.scratch(1)
    for i in range(ctx.n(100)):
        r = ctx.rng('setfalling', i)
        c = ctx.case('setfalling.%d' % i, fn, conv='c', ret='v')
        flags = r.choice([0, 1, 2, 3, 4, 6, 7]) if r.random() < 0.6 else r.getrandbits(32)
        en, edge = _bool_arg(r)
        c.set(item, bytes(_world_item(r, flags=flags)))
        c.arg(item).arg(en)
        c.dump(item, WI_SIZE, 'item')
        c.note(flags='%x' % flags, enabled='%x' % en)
        if edge:
            c.note(edge=edge)


def _set_item_entity_flags(ctx):
    """void SetItemAndEntityFlags(W8WorldItem*, unsigned mask, bool): entity_flags and, with a
    3D object, W8ItemRep::SetFlags on its rep."""
    fn = ctx.fn(0x004f81c0)
    item = ctx.scratch(1)
    obj = ctx.scratch(2)
    rep = ctx.scratch(3)
    for i in range(ctx.n(200)):
        r = ctx.rng('setentityflags', i)
        c = ctx.case('setentityflags.%d' % i, fn, conv='c', ret='v')
        entity = _entity_flags(r)
        mask = _mask(r)
        en, edge = _bool_arg(r)
        has3d = r.random() < 0.65
        c.set(item, bytes(_world_item(r, entity=entity)))
        if has3d:
            rflags = entity if r.random() < 0.6 else _entity_flags(r)
            c.set(obj, bytes(_item_blob(r)))
            c.setp(obj + I_REP, rep)
            c.set(rep, bytes(_rep_blob(r, rflags)))
            c.setp(item + W_P3D, obj)
        c.arg(item).arg(mask).arg(en)
        c.dump(item, WI_SIZE, 'item', ignore=[W_P3D] if has3d else [])
        c.dump(rep, REP_SIZE, 'rep', floats=REP_FLOATS)
        c.note(entity='%x' % entity, mask='%x' % mask, enabled='%x' % en, p3d=int(has3d))
        if edge:
            c.note(edge=edge)


def _group_count(ctx):
    """int ItemInfoGetNumInGroup(W8WorldItem*): 1 + nodes reachable through next."""
    fn = ctx.fn(0x004f8300)
    for i in range(ctx.n(120)):
        r = ctx.rng('groupcount', i)
        c = ctx.case('groupcount.%d' % i, fn, conv='c', ret='i')
        x = r.random()
        if x < 0.15:
            n = 1
        elif x < 0.65:
            n = r.randrange(2, 9)
        elif x < 0.9:
            n = r.randrange(9, 31)
        else:
            n = r.randrange(31, 80)
        slots, _ = _build_chain(ctx, c, r, n, content=False)
        k = 0 if r.random() < 0.8 else r.randrange(n)
        c.arg(_node(ctx, slots[k]))
        c.note(chain=n, start=k)


def _walk_tail(nexts, start):
    s = start
    while nexts[s] is not None:
        s = nexts[s]
    return s


def _separate_item(ctx, c, r, slots):
    """World item in S2 that is not in the chain; its next is 0, a garbage word or a link
    into the chain."""
    sep = ctx.scratch(2)
    blob = _world_item(r, rid=9000)
    x = r.random()
    if x < 0.3:
        blob.u32(W_NEXT, r.choice([0x12345678, 0xfffffffe, 0x00000001]))
        kind = 'garbage'
    else:
        kind = 'null'
    c.set(sep, bytes(blob))
    if 0.3 <= x < 0.6:
        c.setp(sep + W_NEXT, _node(ctx, r.choice(slots)))
        kind = 'link'
    return sep, kind


def _group_add(ctx):
    """void ItemInfoAddToGroup(W8WorldItem* group, W8WorldItem* item): tail(group)->next =
    item, item->next = 0."""
    fn = ctx.fn(0x004f8340)
    for i in range(ctx.n(150)):
        r = ctx.rng('groupadd', i)
        c = ctx.case('groupadd.%d' % i, fn, conv='c', ret='v')
        n = r.choice([1, 1, 2, 3, 4, 5, 6, 8, 10, 15, 20])
        slots, length = _build_chain(ctx, c, r, n)
        nexts = {slots[k]: (slots[k + 1] if k + 1 < n else None) for k in range(n)}
        gk = 0 if r.random() < 0.85 else r.randrange(n)
        x = r.random()
        if x < 0.7:
            target = 'X'
        elif x < 0.85 and n > 1:
            target = slots[r.randrange(n - 1)]
        elif x < 0.93:
            target = slots[-1]
        else:
            target = slots[0]
        sep_kind = None
        if target == 'X':
            item, sep_kind = _separate_item(ctx, c, r, slots)
        else:
            item = _node(ctx, target)
        tail = _walk_tail(nexts, slots[gk])
        nexts[tail] = target
        if target != 'X':
            nexts[target] = None
        c.arg(_node(ctx, slots[gk])).arg(item)
        ignore = [s * WI_STRIDE + W_NEXT for s in slots if nexts[s] is not None]
        c.dump(ctx.scratch(1), length, 'chain', ignore=ignore)
        if target == 'X':
            c.dump(item, WI_SIZE, 'item')
        c.note(chain=n, group=gk, item='separate:%s' % sep_kind if target == 'X'
               else 'chain%d' % slots.index(target))


def _group_remove(ctx):
    """W8WorldItem* ItemInfoRemoveFromGroup(W8WorldItem* head, W8WorldItem* item)."""
    fn = ctx.fn(0x004f83a0)
    for i in range(ctx.n(200)):
        r = ctx.rng('groupremove', i)
        c = ctx.case('groupremove.%d' % i, fn, conv='c', ret='p')
        n = r.choice([1, 1, 2, 2, 3, 4, 5, 6, 8, 10, 15, 20])
        slots, length = _build_chain(ctx, c, r, n)
        nexts = {slots[k]: (slots[k + 1] if k + 1 < n else None) for k in range(n)}
        null_head = i < 4
        hk = 0 if r.random() < 0.85 else r.randrange(n)
        x = r.random()
        if null_head or x < 0.2:
            target = 'X'
        elif x < 0.35:
            target = slots[hk]
        elif x < 0.55:
            target = slots[-1]
        else:
            target = r.choice(slots)
        sep_kind = None
        if target == 'X':
            item, sep_kind = _separate_item(ctx, c, r, slots)
        else:
            item = _node(ctx, target)
        # expected links (retail 0x004F83A0)
        if not null_head and target != slots[hk]:
            scan, prev = slots[hk], None
            while True:
                prev = scan
                scan = nexts[prev]
                if scan is None or scan == target:
                    break
            if scan == target and target != 'X':
                if nexts[target] is not None:
                    nexts[prev] = nexts[target]
                else:
                    nexts[prev] = None
            if target != 'X':
                nexts[target] = None
        c.arg(0 if null_head else _node(ctx, slots[hk])).arg(item)
        ignore = [s * WI_STRIDE + W_NEXT for s in slots if nexts[s] is not None]
        c.dump(ctx.scratch(1), length, 'chain', ignore=ignore)
        if target == 'X':
            c.dump(item, WI_SIZE, 'item')
        c.note(chain=n, head='null' if null_head else hk,
               item='separate:%s' % sep_kind if target == 'X' else 'chain%d' % slots.index(target))


def _group_make_list(ctx):
    """int ItemInfoMakeGroupList(W8WorldItem*, W8GrowableVector<W8WorldItem*>*): Add (inline
    grow by one) of the item and every node after it; returns the vector count."""
    fn = ctx.fn(0x004f8440)
    vec = ctx.scratch(0)
    arr = vec + GV_ARRAY
    for i in range(ctx.n(150)):
        r = ctx.rng('makegrouplist', i)
        c = ctx.case('makegrouplist.%d' % i, fn, conv='c', ret='i')
        n = r.choice([1, 1, 2, 3, 4, 5, 6, 8, 12, 20])
        slots, _ = _build_chain(ctx, c, r, n, content=r.random() < 0.3)
        k = 0 if r.random() < 0.8 else r.randrange(n)
        m = n - k
        x = r.random()
        vptr = r.getrandbits(32)
        if x < 0.8:
            mode = 'normal'
            c0 = r.choice([0, 0, 0, 1, 2, 5])
            cap = c0 + m + r.choice([0, 0, 1, 3, 10])
        elif x < 0.92:
            mode = 'grow'
            c0, cap = 0, 0
        else:
            mode = 'negative_count'
            c0 = r.choice([-1, -2, -3, -3, 0x7fffffff])
            cap = 25
        if mode == 'grow':
            c.set(vec, u32(vptr))                    # count, capacity, data stay 0
        else:
            c.set(vec, u32(vptr) + struct.pack('<ii', c0, cap))
            c.setp(vec + GV_DATA, arr)
            pre = max(c0, 0) if c0 != 0x7fffffff else 0
            c.set(arr - 0x10, bytes(r.getrandbits(8) for _ in range(0x10)) +
                  b''.join(u32(r.getrandbits(31)) for _ in range(pre + m + 4)))
        written = []
        for j in range(m):
            off = ((c0 + j) * 4) & 0xffffffff
            if off >= 0x80000000:
                off -= 1 << 32
            written.append(off)
        c.arg(_node(ctx, slots[k])).arg(vec)
        c.dump(vec, 16, 'vector', ignore=[GV_DATA])
        if mode != 'grow':
            span = max(max(written), max(c0, 0) * 4 if c0 != 0x7fffffff else 0) + 0x14
            c.dump(arr - 0x10, span + 0x10, 'array', ignore=[w + 0x10 for w in written])
        c.note(chain=n, start=k, mode=mode, count='%x' % (c0 & 0xffffffff), capacity=cap)
        if mode == 'negative_count':
            c.note(edge='count_edge')


# --------------------------------------------------------------------------- lookups
def _case_variant(r, s):
    v = r.choice(['upper', 'lower', 'swap', 'random'])
    if v == 'upper':
        return s.upper()
    if v == 'lower':
        return s.lower()
    if v == 'swap':
        return s.swapcase()
    return ''.join(ch.upper() if r.random() < 0.5 else ch.lower() for ch in s)


GARBAGE_NAMES = ['', ' ', 'x', 'questionmark', 'UNDEFINED', 'Dagger ', ' Dagger', 'Dagge',
                 'Daggerx', 'D\xe4gger', '\xff\xfe', 'a' * 300, 'stix\t', 'Ale.', 'musket_',
                 '*', '%s%s%n', 'Bayjin Good ', 'Swamp_Good', 'Rapax', 'umpani', 'Drop']


def _str(s):
    return s.encode('latin1') + b'\0'


def _first_table(name, count):
    if count >= 0x80000000:
        return -1
    q = name.lower()
    for k in range(min(count, TABLE_COUNT)):
        if TABLE_NAMES[k].lower() == q:
            return k
    return -1


def _find_item_table(ctx):
    """int FindItemTableByName(const char*): _stricmp over g_item_tables[0..count) (signed
    loop bound)."""
    fn = ctx.fn(0x004f88a0)
    gx = ctx.g('gXStatus')
    buf = ctx.scratch(0)
    tables = ctx.g('g_item_tables').deref()
    plan = []
    for k in range(TABLE_COUNT):
        plan.append(('exact', k))
    plan += [('variant', None)] * 50 + [('count', None)] * 40 + [('garbage', None)] * 30 + \
        [('pointer', None)] * 16
    for i, (kind, k) in enumerate(plan[:ctx.n(len(plan))]):
        r = ctx.rng('finditemtable', i)
        c = ctx.case('finditemtable.%d' % i, fn, conv='c', ret='i')
        count = TABLE_COUNT
        if kind == 'exact':
            name = TABLE_NAMES[k]
        elif kind == 'variant':
            k = r.randrange(TABLE_COUNT)
            name = _case_variant(r, TABLE_NAMES[k])
        elif kind == 'count':
            k = r.randrange(TABLE_COUNT)
            name = TABLE_NAMES[k] if r.random() < 0.7 else _case_variant(r, TABLE_NAMES[k])
            count = r.choice([k, k + 1, k + 1, 0, 1, 0x80000000, 0xffffffff, 0x80000072, 113, 57])
            c.note(edge='count_edge')
        elif kind == 'garbage':
            name = r.choice(GARBAGE_NAMES) if r.random() < 0.7 else \
                r.choice(TABLE_NAMES)[:r.randrange(1, 6)]
        else:
            k = r.randrange(TABLE_COUNT)
            name = None
        c.set(gx + GX_TABLES_COUNT, u32(count))
        if name is None:
            c.arg((tables + 4 * k).deref())      # the table's own name field
            c.note(name='&table[%d].name' % k, expect=_first_table(TABLE_NAMES[k], count))
        else:
            c.set(buf, _str(name))
            c.arg(buf)
            c.note(name=name[:40], expect=_first_table(name, count))
        c.note(kind=kind, count='%x' % count)


def _first_record(name, count):
    if count >= 0x80000000:
        return -1
    q = name.lower()
    for k in range(min(count, ITEM_COUNT)):
        if (ITEM_INTERNAL[k] or ITEM_DISPLAY[k]).lower() == q:
            return k
    return -1


def _find_item_record(ctx):
    """int FindItemRecordByName(const char*): internal_name, or the display name converted
    with ConvertWideStringToString (sprintf "%ls" into g_wide_string_buffer) when the
    internal name is empty."""
    fn = ctx.fn(0x004f8220)
    gx = ctx.g('gXStatus')
    wbuf = ctx.g('g_wide_string_buffer')
    rec0 = ctx.g('g_item_records').deref()
    buf = ctx.scratch(0)
    with_internal = [k for k in range(ITEM_COUNT) if ITEM_INTERNAL[k]]
    without = [k for k in range(ITEM_COUNT) if not ITEM_INTERNAL[k] and ITEM_DISPLAY[k]]
    r0 = ctx.rng('finditemrecord', 'plan')
    plan = [('internal', k) for k in r0.sample(with_internal, 100)]
    plan += [('display', k) for k in r0.sample(without, 120)]
    plan += [('display_of_internal', k) for k in r0.sample(with_internal, 30)]
    plan += [('variant', None)] * 40
    plan += [('empty', 819), ('empty', 415), ('empty', 416)]
    plan += [('count', None)] * 35 + [('garbage', None)] * 20 + [('pointer', None)] * 15
    for i, (kind, k) in enumerate(plan[:ctx.n(len(plan))]):
        r = ctx.rng('finditemrecord', i)
        c = ctx.case('finditemrecord.%d' % i, fn, conv='c', ret='i')
        count = ITEM_COUNT
        name = None
        if kind == 'internal':
            name = ITEM_INTERNAL[k]
        elif kind == 'display':
            name = ITEM_DISPLAY[k]
        elif kind == 'display_of_internal':
            name = ITEM_DISPLAY[k]
        elif kind == 'variant':
            k = r.randrange(ITEM_COUNT)
            name = _case_variant(r, ITEM_INTERNAL[k] or ITEM_DISPLAY[k])
        elif kind == 'empty':
            name, count = '', k
        elif kind == 'count':
            k = r.choice(with_internal + without)
            name = ITEM_INTERNAL[k] or ITEM_DISPLAY[k]
            first = _first_record(name, ITEM_COUNT)
            count = r.choice([first, first + 1, first + 1, 0, 1, 0x80000000, 0xffffffff, 0x80000333,
                              818, 415])
            c.note(edge='count_edge')
        elif kind == 'garbage':
            name = r.choice(GARBAGE_NAMES) if r.random() < 0.7 else \
                r.choice(ITEM_DISPLAY)[:r.randrange(1, 6)]
        else:
            k = r.choice(with_internal)
        c.set(gx + GX_ITEMS_COUNT, u32(count))
        c.fill(wbuf, WIDE_BUF_LEN, 0xcc)
        c.cap(wbuf, WIDE_BUF_LEN, 'wide_string_buffer')
        if name is None:
            c.arg(rec0 + k * REC_SIZE + REC_INTERNAL)   # the record's own internal name
            c.note(name='&record[%d].internal_name' % k, expect=_first_record(ITEM_INTERNAL[k], count))
        else:
            c.set(buf, _str(name))
            c.arg(buf)
            c.note(name=name[:40], expect=_first_record(name, count))
        c.note(kind=kind, count='%x' % count)


# --------------------------------------------------------------------------- world item list
def _next_world_item(ctx):
    """W8WorldItem* GetNextWorldItem(bool restart): retail compares the cursor with
    PLLength signed (jge); PLGet indexes data[] with the int cursor."""
    fn = ctx.fn(0x004f82b0)
    gx = ctx.g('gXStatus')
    cursor = ctx.g('g_world_item_cursor')
    for i in range(ctx.n(200)):
        r = ctx.rng('nextworlditem', i)
        c = ctx.case('nextworlditem.%d' % i, fn, conv='c', ret='p')
        n = r.choice([0, 1, 2, 3, 5, 8, 10])
        null_list = r.random() < 0.05
        used = n
        edges = []
        if not null_list and r.random() < 0.07:
            used = r.choice([-1, -5, -0x80000000])
            edges.append('negative_count')
        x = r.random()
        if x < 0.65:
            cur = r.randrange(0, n + 3)
        elif x < 0.8:
            cur = r.choice([n, n + 1, 0x7fffffff])
        else:
            cur = r.choice([-1, -2, -3, -4, -0x80000000])
        restart, bedge = _bool_arg(r, 0.25)
        if bedge:
            edges.append(bedge)
        if cur < 0 and not (restart & 0xff):
            edges.append('negative_cursor')
        if null_list:
            c.set(gx + GX_ITEM_LIST, u32(0))
        else:
            _setup_list(ctx, c, list(range(n)), used=used)
            if cur < 0 and r.random() < 0.8:
                _negative_slots(ctx, c, r, n)
        c.set(cursor, u32(cur))
        c.arg(restart)
        c.cap(cursor, 4, 'cursor')
        c.note(items=n, used=used, cursor=cur, restart='%x' % restart, null_list=int(null_list))
        if edges:
            c.note(edge=','.join(edges))


def _item_is_world_persistent(ctx):
    """bool ItemInfoIsWorldPersistent(const W8WorldItem*): record flag 0x20 (container)."""
    fn = ctx.fn(0x004f91e0)
    rec0 = ctx.g('g_item_records').deref()
    item = ctx.scratch(1)
    for i in range(ctx.n(200)):
        r = ctx.rng('worldpersistent', i)
        c = ctx.case('worldpersistent.%d' % i, fn, conv='c', ret='b')
        if i < 6:
            c.arg(0)
            c.note(item='null')
            continue
        x = r.random()
        if x < 0.2:
            iid = CONTAINER_ITEM
        elif x < 0.27:
            iid = r.choice([0, 571, 573, 818])
        else:
            iid = r.randrange(ITEM_COUNT)
        c.set(item, bytes(_world_item(r, item_no=iid)))
        if r.random() < 0.4:
            fl = r.choice([0x20, 0xdf, 0xff, 0x00, 0x21, 0x1f, r.getrandbits(8)])
            c.set(rec0 + iid * REC_SIZE + REC_FLAGS, u8(fl))
            c.note(record_flags='%x' % fl)
        c.arg(item)
        c.note(item=iid)


def _item_info(ctx):
    """W8WorldItem* ItemInfo(unsigned index): unsigned bound (assert 961), PLGet with the
    index as int (data[-k] for >= 0x80000000), null result asserts 965."""
    fn = ctx.fn(0x004f7fe0)
    gx = ctx.g('gXStatus')
    for i in range(ctx.n(150)):
        r = ctx.rng('iteminfo', i)
        c = ctx.case('iteminfo.%d' % i, fn, conv='c', ret='p')
        n = r.choice([0, 1, 2, 3, 4, 6, 8, 12])
        null_list = r.random() < 0.04
        used = n
        if not null_list and r.random() < 0.06:
            used = r.choice([-1, -0x80000000])
            c.note(edge='negative_count')
        x = r.random()
        if x < 0.7 and n:
            index = r.randrange(n)
        elif x < 0.85:
            index = r.choice([n, n + 1, 0x7fffffff])
        else:
            index = r.choice([0xffffffff, 0xfffffffe, 0xfffffffc, 0x80000000])
        slots = list(range(n))
        if n and r.random() < 0.06:
            slots[r.randrange(n)] = None
        if null_list:
            c.set(gx + GX_ITEM_LIST, u32(0))
        else:
            _setup_list(ctx, c, slots, used=used)
            if index >= 0x80000000 and r.random() < 0.8:
                _negative_slots(ctx, c, r, n)
        c.arg(index)
        c.note(items=n, used=used, index='%x' % index, null_list=int(null_list),
               null_entry=int(None in slots))


def _unique_ids(r, n):
    ids = r.sample(range(1, 3000), n)
    if n > 1 and r.random() < 0.1:
        ids[r.randrange(1, n)] = ids[0]
    if n and r.random() < 0.08:
        ids[r.randrange(n)] = r.choice([0, -1, -100, 0x7fffffff, -0x80000000])
    return ids


def _item_index(ctx):
    """unsigned ItemIndex(int runtime_id): first list position with that runtime id, else
    assert 992 and 0."""
    fn = ctx.fn(0x004f8060)
    for i in range(ctx.n(150)):
        r = ctx.rng('itemindex', i)
        c = ctx.case('itemindex.%d' % i, fn, conv='c', ret='i')
        n = 0 if r.random() < 0.04 else r.choice([1, 2, 3, 5, 8, 12, 15])
        ids = _unique_ids(r, n)
        _setup_list(ctx, c, list(range(n)))
        for k in range(n):
            c.set(_node(ctx, k) + W_ID, u32(ids[k]))
        if n and r.random() < 0.78:
            q = ids[r.randrange(n)]
            kind = 'present'
        else:
            q = r.choice([r.randrange(3000, 6000), 0, -1, 0x7fffffff])
            kind = 'missing' if q not in ids else 'present'
        c.arg(q)
        c.note(items=n, query=q, kind=kind)


def _set_world_item_highlight(ctx):
    """void SetWorldItemHighlight(int runtime_id, bool on): GREEN bit of the item's rep +
    W8Item::SetHighlight."""
    fn = ctx.fn(0x004F71E0)
    obj = ctx.scratch(2)
    reps = ctx.scratch(3)
    for i in range(ctx.n(150)):
        r = ctx.rng('worlditemhighlight', i)
        c = ctx.case('worlditemhighlight.%d' % i, fn, conv='c', ret='v')
        n = r.choice([1, 1, 2, 3, 4, 6, 8, 10])
        ids = r.sample(range(1, 3000), n)
        _setup_list(ctx, c, list(range(n)))
        region = bytearray()
        for k in range(n):
            region += _rep_blob(r, _entity_flags(r)) + bytes(REP_STRIDE - REP_SIZE)
            c.set(_node(ctx, k) + W_ID, u32(ids[k]))
            c.setp(_node(ctx, k) + W_P3D, obj + k * ITEM_STRIDE)
            c.setp(obj + k * ITEM_STRIDE + I_REP, reps + k * REP_STRIDE)
        c.set(reps, bytes(region))
        if r.random() < 0.9:
            t = r.randrange(n)
            q = ids[t]
        else:
            t, q = 'missing', r.randrange(3000, 6000)
        on, edge = _bool_arg(r)
        c.arg(q).arg(on)
        c.dump(reps, n * REP_STRIDE, 'reps',
               floats=[k * REP_STRIDE + f for k in range(n) for f in REP_FLOATS])
        c.note(items=n, target=t, on='%x' % on)
        if edge:
            c.note(edge=edge)


def _rebuild_world_item_instances(ctx):
    """void RebuildAllWorldItemInstances(): ReplaceOrCreateItem(&item->item, iItemNo, 0, 0, 0)
    for every list entry (seeded RollDice of the record's initial quantity)."""
    fn = ctx.fn(0x004f94c0)
    gx = ctx.g('gXStatus')
    rec0 = ctx.g('g_item_records').deref()
    for i in range(ctx.n(200)):
        r = ctx.rng('rebuildinstances', i)
        c = ctx.case('rebuildinstances.%d' % i, fn, conv='c', ret='v')
        n = r.choice([0, 1, 1, 2, 3, 4, 5, 6, 8, 10, 12])
        null_list = r.random() < 0.03
        ids = [r.choice(QTY_ITEMS) if r.random() < 0.6 else r.randrange(ITEM_COUNT) for _ in range(n)]
        region = bytearray(n * WI_STRIDE)
        for k in range(n):
            region[k * WI_STRIDE:k * WI_STRIDE + WI_SIZE] = _world_item(r, item_no=ids[k])
        if n:
            c.set(ctx.scratch(1), bytes(region))
        count = ITEM_COUNT
        if n and r.random() < 0.08:
            count = r.randrange(0, max(ids) + 1)
            c.note(edge='count_edge')
        c.set(gx + GX_ITEMS_COUNT, u32(count))
        overrides = []
        if n and r.random() < 0.25:
            for iid in sorted(set(r.sample(ids, min(len(ids), r.choice([1, 2]))))):
                qk = r.choice([0, 1, 1, 2, 3, 4, 5, 6, 0xff])
                base = r.choice([0, 1, -1, -5, 100, 250, 255, 256, 300, -300, 0x7fff, -0x8000])
                cnt = r.choice([0, 1, 2, 5, 10, 20, 255])
                sides = r.choice([0, 1, 2, 6, 10, 20, 255])
                c.set(rec0 + iid * REC_SIZE + REC_QKIND, u8(qk) + struct.pack('<hBB', base, cnt, sides))
                if r.random() < 0.5:
                    fl = r.getrandbits(8)
                    c.set(rec0 + iid * REC_SIZE + REC_FLAGS, u8(fl))
                overrides.append('%d:qk%d,%d+%dd%d' % (iid, qk, base, cnt, sides))
        if null_list:
            c.set(gx + GX_ITEM_LIST, u32(0))
        else:
            _setup_list(ctx, c, list(range(n)))
        if n:
            c.dump(ctx.scratch(1), n * WI_STRIDE, 'items')
        c.note(items=','.join(map(str, ids)), count=count, null_list=int(null_list))
        if overrides:
            c.note(overrides=';'.join(overrides))


# --------------------------------------------------------------------------- data
# Items.dbs internal_name / display_name and ItemTables.dbs names, index = record id
# (extracted from games\reference Patches\PATCH.001 = Data\DATA.SLF).
ITEM_INTERNAL = (
    "|||||||||||||||||||||||||||||||||cursedrapaxsword||||||||||||||||||||||||||||||||||||||t'ran"
    'garm|||||||||||||||||||||||||||||||||||||stix|stix|||||||||||Power Glove|phaserpistol|phaser'
    'pistol||||||||||||||||||powerPack||||||||||||||cuirasse||||||||||||||||||cuirasse|||||||||||'
    '|||||||||||||||||||||||||||||||||||||||||||||||||||||||||gloves||||||||||boots|boots||||||||'
    '|||||||||||||||||||||||||||||||||||||||||||||||stix||||||||||||||bagpipes|||||||||||||helazo'
    'idBanner||||||||||stix||||||||stix||stix|stix||stix|||||||||GoodaVines|GoodaVines|GoodaVines'
    '||||||||||||||||violin||||violin||||||||||violin|bagpipes|bagpipes|||||||||||||||||||||||fan'
    'cywriting||||||||||stix||bluemarble|zuzupetals|rottedmeat||||||||||||||rottedmeat||specialop'
    'sflag|key|key|key||ornateMetalRod||fancywriting|fancywriting|fancywriting|fancywriting||flam'
    'ethrower|||flameThrowerFuelTank|book|||deadfrog||||||||||||||scubgear|umpanidogtags|initiate'
    'badge|||blueFeather|||||||hunkofsilver|obsidianfromrift|locketfromsorceress||ivoryblade|hoga'
    'rtusk|pieceofcoral|prisonerChain|vampirebatwing|prisonerchain|heartofhigholyman|darknectar|c'
    'anezourobe|canezouhelm|canezoudagger|demonstingbow|demonsbanesword||||||||||||||||||||||||||'
    '|||||||||||||||||||||||StaffOfAsh|riftkey|BeckoningStone|bagpipes|driftwood||hookandline|hel'
    'mofserenity|key|key||||Skull|HLLTracking|blackbox|astralDominae|destinaeDomina|calistoDevice'
    '|vaultCard|vaultCard|vaultCard|drum|saxophone|violin|bullroarer|wheelkey|||||||blackbox|spik'
    'edboots|||musket|musket|musket|musket|musket|musket|musket|musket|musket|musket|musket|muske'
    't||astralDominae||powerPack|securitycard|securitycard|securitycard|securitycard|securitycard'
    "|securitycard|securitycard|securitycard|t'rangarm||rocket|RocketLauncher|fancywriting|fancyw"
    "riting|fancywriting|fancywriting|fancywriting|doorjammerdevice|scanner|umpanidogtags|marten'"
    'sbadge|diamond|fancywriting|crabshell|spidersilk|crocodilehide|venomsac|acidvinethorn|giantw'
    'aspwings|featherfromserpent|whozitClaw|butcherCleaver|spiritstaff|ebongem|mummydust|faeriear'
    'mourupper|||beastkilleraxe||greaterwhatzitegg|umpaniFlag|stoneidol|headofravenrapax|drum|||d'
    'jinneye||||||||giantFrogLeg||fancywriting|||||||||stick|ducttape|LightningRod|jackinthebox|s'
    'earchlight|holograph|firecracker|WatchdogAlarm|lavalamp|forcefieldgenerator|x-rayscanner|inv'
    'igoratorbelt|magicmirror|vaporizer|demoninabox|regeneratingstone|phaserpistol|strobelight|el'
    'ectroShocker|watercannon|negat-Air|jackhammer|hingedbox|doll|magnifyingglass|largeprism|lase'
    'rpointer|gunpowder|portapotty|ElectricEye|Loudspeaker|glowingGoo|orangeGoo|voltageamplifier|'
    'giantmagnet|porthole|potwhinge|x-raychip|scanner|emptyBottle|electrodes|magicpolish|shinychr'
    'omeplate|demondoll|LazuriteStone||x-raychip|phaserpistol|electriclamp|oscillatator|highvolta'
    'getransformer|hose|bellow|vacuumPump|longmetaltube|chisel|pendulum|umpaniptorch||MetalBelt||'
    '|||redandyellowires|eauDrapaxPerfume|blueflower|||fancywriting|fancywriting|fancywriting||||'
    'key|jarredTrynnie||||key||||||||||||||||||cuirasse|whozitClaw||||||||||||||||||||||||||cuira'
    'sse||||||||||||'
).split('|')
ITEM_DISPLAY = (
    'Dagger|Main Gauche|Poignard|Stiletto|Poison Dagger|Thieves Dagger|Tarnished '
    'Sword|Longsword|Broadsword|Bastard Sword|Walriblade|Enchanted Broadsword|Saint '
    "Bastard|Bipennis|Crusader's 2H Axe +1|Axe of Many Runes|Blades of Aesir|Bearded War "
    'Axe|Battle Axe|Anointed Flail|Zizka Star|War Scepter|Mace|Morning Star|Maiden Head|Diamond '
    'Eyes|Hammer|Vulcan Hammer|Short Staff|Cane of Corpus|Claymore|Zweihander|Dragon Slayer|Sword'
    ' of 4 Winds|Excaliber|Rapier|Sword of Hearts|Estoc De Olivia|Katana|No-Dachi|Bushido '
    'Blade|Muramasa Blade|Wand of Winds|Stave of 12 Stars|Stave of Silence|Staff Pro '
    'Paralysis|Potion of Dracon Breath|Potion of Razor Cloak|Coil of The '
    'Serpent|Wakizashi|Ninjato|Enchanted Wakizashi|War Hammer|Bec De '
    'Corbin|Flamberge|Sai|Nunchaka|Vorpal Blade|Blade Cuisinart|Fang|Sword of Fire|The '
    'Avenger|*Light* *Sword*|Faerie Stick|Wooden Dowel|Notched '
    "Shaft|Baselard|Cutlass|Winterwand|Eye for an Eye Potion|Rod of Sprites|Ymmu's "
    "Paw|Halberd|Raven's Bill|Faust Halberd|Spear|Awl Pike|Mystic Spear|Spear of Death|Bo|Hayai "
    'Bo|Zatoichi Bo|Quarter Staff|Monstrance|Holy Basher|Rammbus Staff|Staff of Doom|Staff of '
    "Charming|Staff of Blessing|Crux of Crossing|Bullwhip|Fauchard|Naginata|Longstem Spade|Cat'o "
    "Nine Tails|Lance|Maenad's Lance|Stun Rod|Shock Rod|Throwing Knife|Icicle Stix|Fire "
    'Stix|Rocket Stix|Feather Darts|Poison Dart|Shuriken|Death Star|Thermal Pineapple|Sparkle '
    'Stix|Cracker Stix|Short Bow|Long Bow|Enchanted Bow|Light Crossbow|Heavy Crossbow|Seige '
    'Arbalest|Sling|Wrist Rocket|Great Bow|Elven Bow|Cobaltine Powerglove|Frontier Phaser|Mystery'
    ' Ray|Musket|Blunder Buss|Bundle of Arrows|Bundle of Shrike Arrows|Bundle of Barbed '
    'Arrows|Bundle of Armor Piercers|Bundle of Viper Arrows|Bundle of Mystic Arrows|Bundle of '
    'Peacemakers|Bullet Stones|Spike Stones|Impaling Stones|Ta-Li Stones|Medusa Stones|Bundle of '
    'Quarrels|Bundle of Hunter Quarrels|Bundle of Lightning Bolts|Powerpaks|Musket Balls|Dragon '
    'Kite|Buckler Shield|Round Shield|Shield of Soaring|*Light* *Shield*|Heater Shield|Plate Mail'
    ' (U)|Deathmail|Plate Mail+2 (U)|Plate Mail+3 (U)|Ebony Plate (U)|Leather Cuirass|Bronze '
    'Cuirass|Flak Vest|Cloth Shirt|Suede Doublet|Quilt Tunic|Leather Hauberk|Oliveskin '
    'Doublet|Studded Hauberk|Jazeraint Tunic|Chamail Doublet+2|Flak Jacket|Robes (U)|Robes (U) '
    '+1|Robes of Enchant(U)|Black Gown of Death(U)|Gossamer Gown (U)|Fur Halter|Stud-Cuir '
    'Bra+2|Breast Plate|Do-Maru (U)|Tosei-Do (U)|Hi-Kane-Do (U)|Tarnished Mail|Chain '
    'Hauberk|Chain Mail+1 (U)|Gown(U) of Divinemail|Ninja Garb (U)|Plate Mail (L)|Plate Mail+2 '
    '(L)|Plate Mail+3 (L)|Ebony Plate (L)|Leather Greaves|Bronze Greaves|Cloth Pants|Suede '
    'Pants|Leather Legging|Stud Chausses|Chamail Pants+2|Robes (L)|Robes (L) +1|Robes of '
    'Enchant(L)|Black Gown of Death(L)|Gossamer Gown (L)|Chamois Skirt|Jazeraint Skirt|Stud-Cuir '
    'Skirt+2|Do-Maru (L)|Tosei-Do (L)|Hi-Kane-Do (L)|Fur Legging|Quilt Legging|Oliveskin '
    'Leggings|Chain Chausses|Chain Mail+1 (L)|Gown(L) of Divinemail|Ninja Garb (L)|Steel '
    "Helm|Bascinet|Helm & Coif|Bascinet & Camail|Wizard's Cone|Leather Helm|Skullcap|Cap of "
    "Wiles|Faerie Cap|Beanie|Feathered Hat|Phrygian Cap|Flynn's Cap|Mitre|Mitre De "
    'Sanct|Kabuto|Burgonet Helm|Mail Coif|Coif of Divinemail|Armet|Ninja Cowl|Heaume|Ebony '
    'Heaume|Crusader Helm|Necromatic Helm|Steel Gauntlets|Silver Gloves|Cuir Gauntlets|Silken '
    'Gloves|Chamois Gloves|Mantis Gloves|Mail Mittens|Copper Gloves|Sollerets|Silver '
    'Sollerets|Magnetic Boots|Sandals|Buskins|Rubber Shoe (1)|Leather Boots|Goatfoot Boots|Mantis'
    ' Boots|Chain Hosen|Tabi Boots|Amulet of Healing|Amulet of Spiders|Amulet of Stillness|Amulet'
    ' of Airs|Canned Elemental|Amulet of Life|Granite Potion|Ring of Stars|Ring of Sanity|Ring of'
    " Resounding|Magic Nectar|Mystic's Ring|Ring Pro Frost|Ring Pro Magic|Ring of "
    'Reflextion|Smelling Salts|Cameo Locket|Ankh of Might|Ankh of Youth|Ankh of Speed|Ankh of '
    'Dexterity|Ankh of Sanctity|Ankh of Life|Ankh of Death|Ankh of Healing|Blackbelt of 5 '
    'Flowers|Garland of Roses|Silver Cross|Dust of Dessication|Cross of Protection|Valentine '
    'Necklace|Amulet of Asphyxiate|Amulet Pro Magic|Amulet of Rainbows|Golden Medallion|Emerald '
    'Talisman|Helazoid Pendant|Scarab Necklace|Pk Crystal|Bat Necklace|Gem of Power|Vitriolic '
    "Warder|Diamond Ring|Rock Crystals|Brimstone Nuggets|Aromatic Salts|Manta Roots|Lion's "
    "Claws|Ju-Ju Stones|Dragon's Teeth|Medicine Bag|Bag of Death|Boom Bomb|Skull Bones|Deadman's "
    "Hair|Stone Pro Airs|Stone of New Life|Bracers of Defense|Filcher's Band|Death "
    'Shroud|Anointed Cloak|Cloak of Perception|Forest Cape|Pickmeup Potion|Shadow Cloak|Midnight '
    "Cloak|Pipes of Doom|Chromatic Lyre|Silent Lyre|Lyre of Cakes|Poet's Lute|Lute of "
    "Sloth|Angel's Tongue|Siren's Wail|Horn of Prometheus|Potion of Haste|Cornu of "
    'Demonspawn|Knock Picks|Mana Stone|Helazoid Banner|Potion of Poison Reduction|Potion of Light'
    ' Heal|Potion of Mod. Heal|Potion of Hv. Heal|Potion of Superman|Potion of '
    "Restoration|Fuzzfas Fizzer|Potion of Cure Poison|Cure Paralysis Powder|Napalm Bomb|Chief's "
    'Swamp Malt|Potion of Hv. Stamina|Potion of Mod. Stamina|Potion of Cure Light '
    'Condition|Potion of Cure Disease|Holy Water|Cherry Bomb|Fire Bomb|Acid Bomb|Stink Bomb|Ice '
    'Bomb|Skeleton Powder|Death Bomb|Devil Dust|Faerie Dust|Sneeze Powder|Flash Powder|Dust of '
    'Defection|Dust of Banishment|Pandemonium Powder|Concussion Powder|Short Gooda Vine|Short '
    'Gooda Vine|Gooda Vine Rope|Book of Resting|Book of Barriers|Book of Knocks|Book of '
    'Detection|Book of Haste|Mandolin of the Magus|Book of Blessings|Book of Charming|Dulcimer of'
    ' Mending|Renaissance Lute|Book of Removal|Book of Banishing|Jericho Horn|Infernal Horn|Book '
    'of Relics|Frigid Fiddle|Scroll of Magic Screen|Scroll of Magic Missiles|Scroll of '
    'Terror|Arresting Aria|Scroll of Slow|Scroll of Knock Knock|Scroll of Freeze Flesh|Scroll of '
    'Whipping Rocks|Scroll of Missile Shield|Scroll of Armorplate|Scroll of Enchanted '
    "Blade|Scroll of Haste|Scroll of Fireball|Strings of Seduction|Banshee's Howl|Chaos "
    'Drone|Succubus Song|Hades Harp|Scroll of Resurrect|Scroll of Armormelt|Scroll of '
    'Crush|Scroll of Insanity|Scroll of Remove Curse|Scroll of Rest All|Scroll of Heal All|Scroll'
    " of Ego Whip|Bread Rolls|Golden Apples|Bunch of Bananas|Salted Munkmeat|Moser's Mojo "
    "Tea||Milk of Magmanasia|Dungore's Malt Ale|Bottle of Old Jake's|Helm of Insight|Hunter's "
    'Cape|Key of Serenity|Fellowship Pass|Ratt Key|Zip Gun|Scroll of Identify|Book of '
    "Traps|Poseur's Cap|Scroll of Cure Poison|Resurrection Powder|Sprite's Dagger|Ring of "
    'Felix|Earthshaker Bomb|Tarnished Brass Key|Blue Marble|Zuzu Petals|Rotten Meat|Book of '
    'Light|Book of Lesser Cures|Book of Corrosion|Book of Healing|Book of Itching|Book of '
    'Sleep|Book of Stamina|Book of Energy|Book of Frost|Storage Key|Book of Terror|Book of '
    "Wounding|Book of Holding|Drugged Meat|Mystery Potion|Covert Flag|King's Apartment "
    "Key|Portcullis Key|Queen's Key|Constable's Key|Ornate Metal Rod|Assassin's Cap|Queen's "
    'Deposit Slip|Ragged Deposit Slip|Folded Deposit Slip|Smudged Deposit Slip|Red Silk '
    'Gown|Flamethrower|FlameQuencher Wand|Burning Spear|Fuel Tank|Sacred Tome|Bonebasher '
    "Staff|Chieftan's Sceptre|Dead Frog|Incense|Hunter's Bow|Bonecrusher Brew|Book of "
    'Blinding|Book of Mind Stab|Book of Breath|Book of Enchantment|Book of Angels|Book of Holy '
    "Water|Book of Insanity|Book of Missiles|Book of Razors|Book of Sound|Scuba Gear|Glumph's "
    "Identity Tag|Initiate's Badge|Renewal Potion|Instakiller|Blue Feather|Tinker's Carryall "
    'Bracers|Ring of the Road|Aqua Ring|Brimstone Ring|Granite Ring|Ring of Breezes|Giant Silver '
    'Nugget|Piece of Obsidian|Locket of Reflection|Mirror Armor|Ivory Blade|Hogar Tusk|Piece of '
    'Coral|Vampire Chain|Vampire Bat Wing|Chain|Heart of the Sorceress|Dark Nectar|Canezou '
    'Robe|Canezou Helm|Canezou Dagger|Demonsting|Demonsbane|Tattered Note|Book of Slowness|Book '
    'of Booms|Book of Webs|Book of Armorplate|Book of Chameleons|Book of Paralysis Cures|Book of '
    'Poison Cures|Book of Fireballs|Book of Freezing|Book of Lures|Book of Screens|Book of '
    'Mindread|Book of Fumes|Book of Burning Thoughts|Book of the Dark Hound|Book of Silence|Book '
    'of Rocks|Book of Acid|Book of Armormelt|Book of Crushing|Book of Disease Cures|Book of Ego '
    'Whip|Book of Elements|Book of Retaliation|Book of Fire|Book of Ice|Book of Souls|Book of '
    'Summoning|Book of Superman|Book of Fiery Rings|Book of Whirlwinds|Book of Insight|Book of '
    'Statues|Book of Dessication|Book of Freeze All|Book of Heal All|Book of Hexes|Book of '
    'Death|Book of Psionic Blast|Book of Purification|Book of Return|Book of Sanity|Book of '
    "Portals|Book of Toxic Cloud|Rapax Breastplate|Kunar's Key|Ring of Life|Staff of Ash|Rift "
    'Key|Beckoning Stone|Piercing Pipes|Wooden Plank|Sledgehammer|Hook and Line|Helm of '
    "Serenity|Key to Marten's Tomb|Sea Cave Gate Key|Bag of Items|Bela Powder #trynton|Cape of "
    'Stealth|Skull|Shiny Metal Ball|Damaged Black Box|Astral Dominae|Destinae Dominus|Chaos '
    "Moliri|Anna's Keycard|Antone's Keycard|He'Li's Keycard|Snare of Delay|Soulful Sax|Viola "
    "D'Amore|Bullroarer|Wheel Key|Safe Key|Horn of Fear|Thunder Stick|Wand of Static|Amulet of "
    'Static|Crude Iron Key|Black Box|Spiked Boots|Potion of Bless|Potion of Guardian '
    'Angel|Omnigun Mk 1|Omnigun Mk 2|Omnigun Mk 3|Omnigun Mk 4|Omnigun Mk 5|Omnigun Mk 6|Omnigun '
    'Mk 7|Omnigun Mk 8|Omnigun Mk 9|Omnigun Mk 10|Omnigun Mk 11|Omnigun Mk 12|Sanctum Key|Astral '
    "Dominae (fake)|Screg's Key|Solar Powerpaks|IUF Level 1 Security Pass|IUF Level 2 Security "
    'Pass|IUF Level 3 Security Pass|IUF Level 4 Security Pass|IUF Level 5 Security Pass|IUF Level'
    " 6 Security Pass|IUF Top Security Pass|IUF Top Security Pass (fake)|T'Rang Arm|Armory "
    "Key|Rockets|Rocket Launcher|Z'Ant Alliance|Yamir Alliance|Z'Ant Reciprocal Alliance|Mook "
    "Alliance Offer|Mook Alliance Acceptance|Pulse Pick|T'Rang Tracking Device|IUF Identity "
    'Tags|Marten ID Tag|Diamond|Rattus Note|Venom Crab Shell|Spider Silk|Steelhide Skin|Venom '
    'Sac|Iron Weed Thorns|Wasp Wings|Plumed Serpent Feather|Piercer Modai Claw|Cleaver|Spirit '
    'Staff|Ebon Gem|Mummy Dust|Zynaryx Plate|Steelhide Breastplate|Featherweight '
    'Armor|Beastslayer|Ebon Staff|Giant Picus Egg|Umpani Flag|Stone Idol|Head of Raven '
    'Rapax|Rousing Drums|Bloodlust|Necklace of Endurance|Djinn Eye|Stun Mace|Mesh '
    "Leggings|Disruptor Mace|Diamond Epee|Oilskin Cloak|Ring of Protection|Ale|Giant Frog's "
    "Leg|NAS-81|T'Rang-Mook Letter|Hatchet|Plague Axe|The Ripper|Doublestrike Dagger|Hand "
    "Axe|Woodsman's Axe|Dragonhide Cloak|Doubleshot Crossbow|Shillelah|Duct Tape|Lightning "
    'Rod|Jack in the Box|Searchlight|Holograph Projector|Noisemaker|Watchdog Alarm|Lava '
    'Lamp|Forcefield Generator|X-Ray Scanner|Invigorator Belt|Magic Mirror|VapoRizer|Demon in the'
    ' Box|Regenerating Stone|Microwave Ray|Strobe Light|Electroshocker|Water '
    'Cannon|NegatAir|Jackhammer|Hinged Box|Doll|Magnifying Glass|Large Prism|Laser '
    'Pointer|Gunpowder|Port-O-Potty|Electric Eye|Loudspeaker|Glowing Goo|Orange Goo|Voltage '
    'Amplifier|Giant Magnet|Porthole|Pot with Hinge|X-ray Chip|Scanner|Empty '
    'Bottle|Electrodes|Magic Polish|Shiny Chrome Plate|Demon Doll|Lazurite Stone|Ale|Microwave '
    'Chip|Broken Blaster|Electric Lamp|Oscillator|High Voltage Transformer|Hose|Bellows|Vacuum '
    'Pump|Long Metal Tube|Chisel|Pendulum|PTorch|Tripleshot Crossbow|Metal Belt|Ale|Ale|Doubleman'
    " Draught|Tincture of Shadows|Red and Yellow Wires|Eau D'Rapax Perfume|Blue "
    'Flower|Stinger|Stinger|Paper reading "7--"|Paper reading "-4-"|Paper reading "--0"|Mindblast'
    " Rod|Brilliant Helm|Blarneystone Amulet|Zoo Shed Key|Pickled Trynnie|Rapax Mageblade|Doll's "
    "Armor (L)|Doll's Gloves|King's Cave Key|Doom Darts|Boomerang Shuriken|Throwing "
    'Stiletto|Bundle of Fear Bolts|Bundle of Precision Arrows|Doubleshot Sling|Flail|Short '
    "Sword|Flame Staff|Strong Bow|The Mauler|Ariel's Slippers|Mercucio's Blade|Puck's "
    "Cap|Prospero's Cloak|Ring of Beasts|Giant's Sword|Trynnie Breastplate|Serpent's Tooth|Fey "
    "Ring|Geomancer's Ring|Aeromancer's Ring|Pyromancer's Ring|Hydromancer's Ring|Enchanted "
    'Katana|Gold Nuggets|Ring of Regeneration|Rainbow Shield|Lithe Buckler|Shield of '
    "Sacrifice|Philosopher's Shield|Thieves Buckler|Greenwood Bow|Enchanted Longsword|Enchanted "
    'Mace|Gleaming Sword|Cutlass of the Damned|Granite Shield|Brimstone Shield|Aqua Shield|Shield'
    ' of Winds|Spiked Spear|Crab Cakes|Cloak of Many Colors|Golden Breastplate|Winged '
    'Boots|Snakeskin Boots|Infinity Helm|Platinum Greaves|Robes of Rejuvenation|Ring of '
    "Power|Stockade Key|Eagle Eye Bow|Dread Spear|Caliban's Cuirass|Oberon's Greaves|Amulet of "
    'Nebdar'
).split('|')
TABLE_NAMES = (
    "TestChest|Starter Chest|Monestary Treasure|Anna's Chest|He'Li's Chest|Antone's Chest|Anna's "
    "Vault|He'Li's Vault|Arnika Regular Treasure|Arnika Good Treasure|Marten's Locker|Jail "
    'Locker|HLL Locker|Statue|umpani locker|umpani cash|umpani booze|Test Steal Drop|Raven '
    'Rapax|Life Chest|Chaos Chest|Knowledge Chest|Body Chest|Amit Chest|Monastery coffins|Demon '
    'Weapons|Monastery Tomb chests|Monastery Assistant|Helm of Serenity Chest|Monastery Road '
    'Chest|Slime drops|Arnika Trynton Chest|Graveyard Chest|Rapax King Chest|Rapax Queen '
    'Chest|Rapax Servant Chest|Castle Chest|umpani regular|umpani good|Rapax Castle Regular|Rapax'
    ' Castle Good|Rapax Castle Concubine|Trynton Good|Trynton Regular|Trang good|Trang '
    'regular|Swamp Good|Swamp Regular|Bayjin Good|Bayjin Regular|Bayjin Nessie Chest|Sea Caves '
    'Good|Sea Caves Regular|Rift Good|Rift Regular|Higardi A|Higardi B|Marten Chest|Antone '
    "drop|He'Li drop|Anna drop|Vi drop|Myles drop|Urq drop|Madras drop|Burz Drop|Trynnie Chief "
    'drop|Trynnie Shaman drop|Fuzzfas drop|Braffit drop|Dragon Head Chest|Don Barlone Drop|Rattus'
    ' drop|Higardi C|Swamp House|Crock drop|Marten Drop|Generic High Level Treasure|Kunar '
    'drop|Constable drop|Jailer drop|Ferro drop|Rapax King Drop|Glumf Drop|Yamir Drop|Zant '
    'Drop|TRang Guarder Drop|Anselm Drop|Bela Drop|Drazic Drop|Higardi Drop Good|Higardi Drop '
    'Regular|Jan-Ette Drop|Rapax Drop Regular|Rapax Drop Good|Rapax Drop Archer|Milano '
    'Drop|Rattkin Drop Regular|Rattkin Drop Archer|Rodan Drop|Sadok Drop|Savant Drop|Saxx '
    'Drop|Sexus Drop|Sparkle Drop|Tantris Drop|Trang Drop Good|Trang Drop Regular|Umpani Drop '
    'Good|Umpani Drop Regular|Trynnie Drop Regular|umpani rocket|Higardi Bandit Drop|Rapax Female'
    ' Drop'
).split('|')
assert len(ITEM_INTERNAL) == ITEM_COUNT and len(ITEM_DISPLAY) == ITEM_COUNT
assert len(TABLE_NAMES) == TABLE_COUNT
