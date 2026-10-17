"""Local Code\\Conditions & Enchantments.cpp (port: local_code/ConditionsAndEnchantments.cpp).

Every function of the file is tested (case counts at --scale 1):
  0x005248a0 GetConditionRecordFlag ................ 120
  0x00522e80 NormalizeItemQuantityKind ............. 320
  0x00522ef0 SanitizeLoadedItems ................... 120
  0x005237e0 RecomputeCharacterHighestCondition .... 300  (50 of them in combat mode)
  0x00523940 ApplyCharacterCondition ............... 300
  0x005236a0 TickCharacterCondition ................ 300
  0x00523330 RemoveCharacterCondition .............. 400  (30 in combat mode)
  0x00522fe0 SetCharacterCondition ................. 400
  0x00523a80 ClearCharacterEnchantmentSlot ......... 150
  0x00523b30 TickCharacterEnchantmentSlot .......... 200
  0x005246c0 RemoveConditionFromParty .............. 150
  0x00524720 RemoveAllConditionsFromParty .......... 100
  0x00524250 CopyMonsterConditionsToCharacter ...... 200
  0x005248d0 ReleaseMonsterConditionBindings ....... 200
  0x00524780 BindMonsterToCharacterDependence ...... 150
  0x00523c00 SetMonsterCondition ................... 400
  0x00523f40 ClearMonsterCondition ................. 250
  0x00524110 TickMonsterCondition .................. 250
  0x005242b0 ApplyMonsterCondition ................. 250
  0x00524390 ClearMonsterEnchantmentSlot ........... 150
  0x00524400 TickMonsterEnchantmentSlot ............ 200
  0x005241e0 CopyCharacterConditionsToTarget ....... 200
  0x005244a0 RemoveConditionFromEveryone ........... 150
  0x00524540 RemoveAllEnchantments ................. 120
Skipped functions: none.

How the state is controlled
  * Party: slots 2..7 get corpus characters (setb) - the save has its six PCs
    there and the RPC slots 0/1 empty; fOccupied of all eight rows is set.
    Condition durations, enchantments, highest condition, poison strength,
    traits (profession 2/4/13, race 15), items and dependence records are
    synthesized with small `set`s on top of the corpus blob.
  * Globals every case sets: game_started=1, world_suspended, the one-shot
    skip_next_condition_reaction (random 0/1, captured), greeting_pending=1
    (W8CharacterEventQueue::QueueEntry then drops every queued speech event, so
    nothing is queued for later frames), item_in_cursor=0, party_modifiers
    zeroed (party spells may expire between the two runs), fCombatMode,
    fSurprisePossible, sight_refresh_pending=0, fEncumbranceDirty=0, and
    current_level where the function reads it.
  * Monster world: gXStatus.plsMonsterList / plsUnbornMonsterList /
    plsMonsterGroupList / plsMonsterGroupEncounterList are replaced for the
    call. Character-side cases get empty lists (no drifting real monster can be
    retargeted or looked up). Monster-side cases get a fake world in scratch:
    up to three W8MonsterInfo (S0), their PList (S1), fake groups with ILists
    (S2), fake W8MonsterRecords put in gXStatus.monster_record_cache[999/998]
    (S3), per-monster combat blocks (S4). Only p3D is real: it is copied from
    the first live monster of the level (setp through the real list before the
    list pointer is swapped), because SetMonsterSpellIcon(remove) and
    IsCycleInterruptable/StartMonsterCycle need an engine object (if the level
    had no live monster these cases stop at set-up with status X in both exes).
    fActive=0 and fMotionless=0 keep MonsterInfoSetMotionless and the cycle
    asserts out.
  * Party rows: where ApplyTarget/RepickActionTarget can run, the PC rows'
    target_out_of_combat/target_in_combat are pinned to character/monster/group/
    none targets in exactly the shape SetTargetToCharacter/-Monster builds.
  * Edge inputs worth knowing: highest_condition is sometimes preset to junk
    (0x14, 0x7fffffff, 0x80000000, 0xffffffff) - retail compares the old value
    unsigned (0x005238ad jae), while a W8Condition enum compares signed in MSVC,
    so 0x80000000.. took the other encumbrance branch until the port cast those
    compares (Recompute/RemoveCharacterCondition, RedistributePartyEncumbrance,
    CalcArmorClasses) to unsigned;
    durations/poison/percent/turns include 0, 9998/9999/10000 and 32-bit edges;
    bool arguments occasionally carry garbage above the low byte (0x100, 0x201).
  * Captures: whole characters (regen floats 0xb69..0xba5 marked floats=, so x87
    noise is tolerated), XChar rows (pointer words ignored), g_status.formation,
    the portrait pose fields, sight/encumbrance/skip flags, fake monsters (regen
    floats marked), fake groups, combat blocks, and
    'notice_posted': g_level_block->text_lines[8..11] preset to a
    sentinel - FormatNotice zeroes the entry of the box it writes and adds the
    wrapped line lengths, so a posted notice (and its wrapped length) shows up
    deterministically. The text-box line counters themselves are not captured
    (the game posts its own notices between cases, so their absolute values
    drift between the two runs) and notices accumulate in the log as in play.
    The wrapped length depends on the wrap width ShowNotice takes from the text
    box rectangle (right - left - 10). The port's wide-UI mod widens the main
    text box (MainGameLayout.cpp SetMainTextBoxRegionBounds), so every case pins
    g_level_block->text_box_left/top/right/bottom to retail's own 4:3 rectangle
    (0xa8, 0x16e, 0x1c4, 0x1ba); without it the same notice wrapped after ~40
    characters in retail and not at all (or after ~65) in the port.

Paths deliberately not reached (they create world objects, run a sight pass on a
fake monster or kill it), so the generators keep the inputs away from them:
  * SetMonsterCondition: a fresh (old duration 0) condition 1..0x12 (spell icon
    load = new world mesh), fresh HEXED/BLIND (sight pass), fresh TURNCOAT on a
    non-neutral monster (hostility + icon), handled DEAD/MISSING
    (MonsterStartsDying). Fresh condition 0 and fresh TURNCOAT on a neutral
    monster are tested.
  * ApplyMonsterCondition with previous turns 0 (icon load) and slot 6 applied
    (sight); Clear/TickMonsterEnchantmentSlot reaching slot 6; Clear/Tick
    MonsterCondition clearing HEXED/BLIND.
  * SetCharacterCondition(DEAD) really killing a character (CharacterDies plays
    CharacterDead.wav): only 4 cases; the others go through Cheat Death or an
    already running DEAD.
"""
import struct

# Monster cases take p3D of the level's first live monster: "Before Bayjin" has no live
# monsters (plsMonsterList->iNumUsed == 0, data[0] is heap garbage), here there are 14.
SAVE = 'Before Nessie'

# ---------------------------------------------------------------- layouts
CHAR = 0x1862
C_INPARTY, C_PROF, C_RACE, C_PROFLV = 0x04, 0x69, 0x71, 0x8d
C_COND, C_ENCH, C_HIGH = 0xa01, 0xa65, 0xb01      # C_HIGH: highest, enchantment_top, poison arg
C_HPMAX, C_HP, C_HPADJ, C_FATIGUE = 0xb0d, 0xb11, 0xb15, 0xb21
C_REGEN_LO, C_REGEN_HI = 0xb69, 0xba9
C_EQUIP, C_PACK, C_RECS = 0xf5d, 0x1029, 0x1817
# health/stamina regen rate + accumulator, spell_regen_rates[12]: x87 results
CHAR_FLOATS = list(range(C_REGEN_LO, C_REGEN_HI, 4))

ROW = 0x106
R_TOOC, R_TIC = 0x1d, 0x4d
ROW_PTRS = (0x19, 0x39, 0x49, 0x69, 0x7d, 0x9d, 0xa5, 0xc5, 0xed)
XCHAR_IGNORE = [s * ROW + p for s in range(8) for p in ROW_PTRS]
X_NPC = 0xfa                       # W8PartySlotRow::npc_index

GS_STARTED, GS_POOL, GS_POOLCNT, GS_LEVEL = 0x0c, 0x21, 0x1791, 0x1900
GS_PARTYMODS, GS_CURSOR, GS_INHAND, GS_SUSPENDED = 0x22e3, 0x235a, 0x235b, 0x2390
GS_FORM, GS_SKIP, GS_GREETING = 0x23a1, 0x2488, 0x2497
GS_FACTS = 0x3121
LB_NOTICE_CHARS = 0x1c8            # W8LevelRuntimeBlock::text_lines[8..11]
NOTICE_SENTINEL = 0x5a5a5a5a
LB_TEXT_BOX = 0x2cc                # W8LevelRuntimeBlock::text_box_left/top/right/bottom
TEXT_BOX_4X3 = (0xa8, 0x16e, 0x1c4, 0x1ba)   # retail SetTextBoxRegionBounds (port: wide-UI mod)

GX_ENTRY, GX_POSE = 0x118, 0x8d
GX_COMBAT, GX_ENCDIRTY, GX_HOSTILE = 0x8dc, 0x8e8, 0x8ed
GX_MONLIST, GX_GROUPS, GX_UNBORN, GX_ENCGROUPS = 0x8f5, 0x8f9, 0x901, 0x905
GX_SURPRISE, GX_EDITFORM, GX_SIGHT, GX_RECCACHE = 0x90d, 0x933, 0xa03, 0xa0f

CS_CHARS, CS_ROW, CS_BERSERK, CS_SAVEDFORM = 0x18, 0xd4, 0x80, 0x920

M_SET = 0x348                      # bytes of W8MonsterInfo the generator writes
M_SIZE = 0x425
M_LOC, M_GROUP, M_SPECIES, M_P3D, M_PCOMBAT = 0x00, 0x04, 0x08, 0x0c, 0x10
M_ACTIVE, M_INCOMBAT, M_DISP = 0x14, 0x15, 0x16
M_HPMAX, M_HP, M_STMAX, M_ST = 0x27, 0x2b, 0x2f, 0x33
M_REGEN_LO, M_REGEN_HI = 0x47, 0x57
M_COND, M_ENCH, M_HIGH, M_CARG, M_EFFECTS, M_MODS = 0x57, 0xa7, 0x107, 0x10b, 0x10f, 0x1db
M_FATIGUE, M_ATTRS, M_BIND, M_MOTIONLESS, M_SCALE = 0x242, 0x247, 0x24c, 0x24e, 0x24f
M_VISIBLE, M_TARGET, M_CONTROL, M_CTARGET, M_ELEMENTAL = 0x2ab, 0x2ba, 0x2fd, 0x304, 0x344
M_PTRS = (M_P3D, M_PCOMBAT, 0x2b6, M_TARGET + 0x1c)
MON_FLOATS = list(range(M_REGEN_LO, M_REGEN_HI, 4))   # RebuildMonsterRegenRates results
MC_HATE, MC_ADVANCING, MC_SIZE = 0x1a, 0x14b, 0x153

G_SIZE, G_ID, G_MEMBERS, G_LIST, G_ACTIVE, G_DISP = 0x12b, 0x00, 0x04, 0x08, 0x14, 0x2a
G_LEADER, G_ALLIES, G_REG, G_ENDED = 0xa3, 0xa7, 0xc3, 0xd3

REC_KIND, REC_ATTRS, REC_LEVEL = 0xcb, 0xd1, 0x24f
SPECIES = (999, 998)               # fake record cache slots (MAX_MONSTERS_IN_DATABASE 1000)

MON_OFF = (0x000, 0x500, 0xa00)    # fake monsters in S0
GRP_OFF = (0x000, 0x200, 0x400)    # fake groups in S2
ILIST_OFF = (0x800, 0x880, 0x900)  # their ILists (data at +0x10)
GPLIST_OFF = 0xc00                 # fake group PList (data at +0x10)
REC_OFF = (0x000, 0x400)           # fake records in S3
MCOMBAT_OFF = (0x000, 0x200, 0x400)  # fake W8MonsterCombatState in S4

PCS = (2, 3, 4, 5, 6, 7)           # occupied party slots of the save
MAX_OPS, MAX_ARGS = 96, 16

# conditions
NONE, DRAINED, DISEASED, IRRITATED, NAUSEATED, SLOWED, AFRAID, POISONED = range(8)
SILENCED, HEXED, INFATUATED, INSANE, BLIND, TURNCOAT, WEBBED, ASLEEP = range(8, 16)
PARALYZED, UNCONSCIOUS, DEAD, MISSING = range(16, 20)
INDEFINITE = 9999
# g_condition_immunities: the 20-entry id lists are padded with NONE, and the retail walk
# compares all 20, so condition 0 is "immune" for these kinds too.
IMMUNE = {20: (2, 7, 17, 3, 6, 11, 15, 4, 0), 22: (2, 7, 4, 3, 6, 15, 0), 17: (11, 6, 4, 0)}

# items by Items.dbs quantity_kind (819 records)
ITEMS_QK = {
    1: [46, 47, 69, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 125, 126, 127, 128, 129,
        130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 258, 260, 264, 269, 282, 306,
        317, 329, 331, 334, 335, 336, 337, 338, 339, 340, 341, 342, 343, 344, 345, 346, 347, 348,
        349, 350, 351, 352, 353, 354, 355, 356, 357, 358, 359, 360, 361, 362, 363, 364, 384, 385,
        386, 388, 389, 390, 391, 392, 393, 394, 395, 396, 402, 403, 404, 405, 406, 407, 408, 409,
        410, 411, 412, 413, 425, 428, 429, 432, 446, 451, 488, 502, 505, 597, 598, 625, 638, 639,
        641, 642, 643, 644, 645, 649, 655, 662, 743, 744, 762, 763, 764, 765, 766, 787, 804, 813],
    2: [16, 19, 24, 27, 33, 34, 42, 43, 44, 60, 61, 68, 74, 81, 85, 86, 87, 88, 120, 121, 208, 254,
        255, 256, 257, 259, 262, 263, 265, 270, 273, 276, 277, 278, 280, 285, 286, 287, 289, 291,
        292, 294, 304, 305, 310, 332, 419, 431, 464, 465, 466, 467, 469, 492, 496, 499, 590, 591,
        592, 593, 614, 753, 755, 770, 772, 789, 812, 818],
    3: [414, 416, 417, 418, 682, 687, 693],
    4: [123, 124, 424, 626],
    0: [0, 12, 28, 45, 59, 76, 93, 116, 149, 161, 173, 185, 197, 210, 222, 234, 246, 271, 296, 312,
        325, 371, 383, 426, 442, 456, 473, 485, 501, 515, 527, 539, 551, 563, 575, 587, 605, 618,
        632, 652, 666, 678, 692, 705, 717, 729, 741, 757, 776, 790, 802, 817],
}
ITEM_DD, ITEM_HELM = 0x243, 0x239   # Destinae Dominus, Helm of Serenity
QTY = [0, 0, 1, 1, 2, 3, 5, 10, 50, 99, 100, 127, 128, 129, 200, 254, 255]

# value palettes
DUR_SMALL = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 30, 45, 60, 90, 120, 180, 240, 360, 500, 1000]
DUR_EDGE = [9998, 9999, 10000, 0xffff, 0x10000, 0x7fffffff, 0x80000000, 0xfffffffe, 0xffffffff]
MINUTES = [0, 1, 1, 2, 3, 5, 10, 15, 30, 60, 120, 240, 1440, 0x7fffffff, 0x80000000, 0xffffffff]
POWER = [1, 1, 2, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 50, 99, 100, 255, 256, 1000, 0x7fff, 0xffff,
         0x10000, 0x7fffffff, 0x80000000, 0xffffffff]
PERCENT = [0, 1, 10, 25, 50, 75, 99, 100, 101, 150, 200, 255, 1000, 0x7fff, 0x8000, 0xffff]
PERCENT_ARG = PERCENT + [0x10000, 0x10064, 0x7fffffff, 0xffffffff]
POISON = [0, 0, 1, 2, 3, 5, 7, 10, 15, 20, 30, 50, 75, 100, 255, 1000, 100000, 0x7fffffff,
          0x80000000, 0xfffffffe, 0xffffffff]
LEVELS = [0, 1, 2, 3, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 20, 22, 24, 26, 28, 30, 32,
          35, 38, 40, 44, 46, 0x2f, 0x30, -1, 100]
EFFECT_IDS = [0, 5, 8, 0x11, 0x14, 0x1a, 0x20, 0x21, 0x28, 0x2d, 0x31]
FACING = (0, 1, 2, 3, 0)


def u8(v):
    return struct.pack('<B', int(v) & 0xff)


def u16(v):
    return struct.pack('<H', int(v) & 0xffff)


def u32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def u32s(vals):
    return b''.join(u32(v) for v in vals)


def f32(v):
    return struct.pack('<f', float(v))


def unsigned(v):
    return int(v) & 0xffffffff


# ---------------------------------------------------------------- random state
def pick_dur(r, edge=0.12):
    return r.choice(DUR_EDGE) if r.random() < edge else r.choice(DUR_SMALL)


def pick_turns(r):
    return r.choice([1, 1, 2, 3, 5, 8, 10, 20, 50, 100, 1000, 0xffff, 0x7fffffff, 0xffffffff])


def gen_conds(r, density, edge=0.12):
    return [pick_dur(r, edge) if r.random() < density else 0 for _ in range(20)]


def highest_of(conds):
    for i in range(19, -1, -1):
        if conds[i]:
            return i
    return 0


def old_highest(r, conds):
    x = r.random()
    if x < 0.75:
        return highest_of(conds)
    if x < 0.95:
        return r.randrange(20)
    return r.choice([0x14, 0x7fffffff, 0x80000000, 0xffffffff])     # unsigned compares in retail


def gen_ench(r, density):
    out = []
    for _ in range(8):
        if r.random() < density:
            out.append([r.choice(POWER), r.choice(PERCENT),
                        r.choice([0, 1, 5, 100, 0x7fff, 0xffff, r.randrange(0x10000)]), pick_turns(r)])
        elif r.random() < 0.1:
            out.append([r.choice(POWER), r.choice(PERCENT), 0, 0])   # stale power, no turns
        else:
            out.append([0, 0, 0, 0])
    return out


def ench_bytes(ench):
    return b''.join(struct.pack('<IHHI', unsigned(p), pc & 0xffff, m & 0xffff, unsigned(t))
                    for p, pc, m, t in ench)


def ench_top(ench):
    for k in range(7, -1, -1):
        if ench[k][3]:
            return k
    return 0


def item_bytes(item_id, stack=1, uses=0, ident=1, extra=None):
    tail = bytes(extra) if extra is not None else bytes([0, 0, 0, 0, 0])
    return struct.pack('<iBBB', item_id, stack & 0xff, uses & 0xff, ident & 0xff) + tail[:5]


def gen_records(r, level=None, monster=None):
    """W8CharacterConditionRecord[4] (0x44 bytes)."""
    out = b''
    for _ in range(4):
        if r.random() < 0.5:
            lv = level if level is not None and r.random() < 0.6 else r.choice([0, 1, 7, 15, 30])
            mo = monster if monster is not None and r.random() < 0.6 else r.choice([0, 1, 500, -1])
            act = r.choice([0, 1, 1, 1]) if r.random() < 0.95 else r.choice([2, 0x80, 0xff])
            out += struct.pack('<iiB', lv, mo, act) + bytes(8)
        else:
            out += bytes(0x11)
    return out


def gen_formation(r, seated, unseated=()):
    rows = {q: [] for q in range(5)}
    order = list(seated)
    r.shuffle(order)
    for s in order:
        cands = [q for q in range(5) if len(rows[q]) < 3]
        rows[r.choice(cands)].append(s)
    occ = [[-1, -1, -1] for _ in range(5)]
    pos = {s: [-1, -1, -1, 0] for s in range(8)}
    for q in range(5):
        cols = {1: [0], 2: [1, 2], 3: [0, 1, 2]}.get(len(rows[q]), [])
        for s, col in zip(rows[q], cols):
            occ[q][col] = s
            pos[s] = [q, -1, col, FACING[q]]
    for s in unseated:
        pos[s] = [-1, r.choice([-1, 0, 1, 2, 3, 4]), -1, r.randrange(4)]
    out = bytearray()
    for q in range(5):
        out += bytes(x & 0xff for x in occ[q])
    out += bytes(len(rows[q]) for q in range(5))
    for s in range(8):
        out += bytes(x & 0xff for x in pos[s]) + bytes(8)
    out += bytes(16)
    assert len(out) == 0x84
    return bytes(out)


def gen_combat_slot(r, kind=None):
    k = kind if kind is not None else r.choice([0, 0, 1, 1, 3, 4, 6])
    return struct.pack('<Iiii', k, r.choice([-1, 2, 3, 5, 7]), r.choice([-1, 1, 77]),
                       r.choice([-1, 4, 9])) + f32(r.uniform(-50, 50)) * 3 + u32(0)


def gen_target_source(r):
    """W8TargetSource for SetMonsterCondition: kinds 0..3, flags that gate the copy."""
    k = r.choice([0, 1, 1, 1, 2, 2, 3, 5])
    ichar = r.choice([0, 1, 2, 3, 4, 5, 6, 7, 8, 2, 3, 4, -1, 9, 12]) if k in (1, 3) else -1
    imon = r.choice([5, 77, 1234]) if k in (2, 3) else -1
    b = bytearray(0x34)
    struct.pack_into('<Iii', b, 0, k, ichar, imon)
    struct.pack_into('<fff', b, 0xc, r.uniform(-9, 9), r.uniform(-9, 9), r.uniform(-9, 9))
    for off in (0x18, 0x19, 0x1a, 0x1d, 0x1f, 0x21):
        b[off] = r.choice([0, 0, 1])
    b[0x1b] = 1 if r.random() < 0.15 else 0      # fReflection
    b[0x1c] = 1 if r.random() < 0.15 else 0      # fBackfire
    b[0x1e] = 1 if r.random() < 0.15 else 0      # target_diverted
    return bytes(b), ichar


def pick_slot(r, rpc=0.05):
    return r.choice((0, 1)) if r.random() < rpc else r.choice(PCS)


def would_be_immune(kind, cond):
    return cond in IMMUNE.get(kind, ())


# ---------------------------------------------------------------- harness wrapper
class W:
    def __init__(self, ctx):
        self.ctx = ctx
        self.GS = ctx.g('g_status')
        self.GX = ctx.g('gXStatus')
        self.GCS = ctx.g('g_combat_state')
        self.S = [ctx.scratch(i) for i in range(8)]
        # value of p3D of the first live monster of the level, read through the real list:
        # &plsMonsterList -> PList* -> data -> data[0] (W8MonsterInfo*) -> +p3D -> value
        self.real_p3d = ((self.GX + GX_MONLIST).deref().deref().deref() + M_P3D).deref()
        # g_level_block->text_lines[8..11]: FormatNotice zeroes the entry of the box it writes
        # (then adds wrapped lengths); a sentinel there turns "a notice was posted, this long"
        # into a deterministic capture, unlike the text-box line counters, which drift with
        # notices the game itself posts between cases.
        self.notice_marker = ctx.g('g_level_block').deref() + LB_NOTICE_CHARS
        # ...and the wrap width behind that length comes from the text box rectangle,
        # which the port's wide-UI mod widens: pin retail's 4:3 one in both exes.
        self.text_box = ctx.g('g_level_block').deref() + LB_TEXT_BOX

    def ch(self, slot):
        return self.ctx.char(slot)

    def xr(self, slot):
        return (self.GS + 8).deref() + slot * ROW

    def case(self, name, i, fn, ret='v'):
        return self.ctx.case('%s.%d' % (name, i), fn, conv='c', ret=ret)

    @staticmethod
    def check(c):
        if len(c.ops) > MAX_OPS or len(c.args) > MAX_ARGS:
            raise ValueError('%s: %d ops / %d args exceed the core limits' % (c.id, len(c.ops), len(c.args)))

    # --- party and globals
    def party(self, c, r, slots=PCS, occupied=PCS):
        names = {}
        for s in slots:
            blob, name = self.ctx.pick_char(r)
            c.setb(self.ch(s), bytes(blob))
            names[s] = name
        for s in range(8):
            c.set(self.xr(s), u8(1 if s in occupied else 0))
        return names

    def base(self, c, r, combat=0, suspended=0, skip=None, level=None, surprise=0, isolate=True):
        GS, GX = self.GS, self.GX
        if skip is None:
            skip = 1 if r.random() < 0.5 else 0
        c.set(GS + GS_STARTED, b'\x01')
        c.set(GS + GS_SUSPENDED, u8(suspended))
        c.set(GS + GS_SKIP, u8(skip))
        c.set(GS + GS_GREETING, b'\x01')
        c.set(GS + GS_CURSOR, b'\x00')
        c.fill(GS + GS_PARTYMODS, 0x67, 0)
        if level is not None:
            c.set(GS + GS_LEVEL, u32(level))
        c.set(GX + GX_COMBAT, u8(combat))
        c.set(GX + GX_SURPRISE, u8(surprise))
        c.set(GX + GX_SIGHT, b'\x00')
        c.set(GX + GX_ENCDIRTY, b'\x00')
        c.set(self.notice_marker, u32s([NOTICE_SENTINEL] * 4))
        c.set(self.text_box, u32s(TEXT_BOX_4X3))
        if isolate:
            self.lists(c, self.S[7], self.S[7])
        return skip

    def lists(self, c, monlist, grouplist):
        S7 = self.S[7]          # zeroed PList: no entries
        c.setp(self.GX + GX_MONLIST, monlist)
        c.setp(self.GX + GX_UNBORN, S7)
        c.setp(self.GX + GX_GROUPS, grouplist)
        c.setp(self.GX + GX_ENCGROUPS, S7)

    def put(self, c, slot, conds=None, ench=None, high=None, hp=None, hpadj=None, fatigue=None,
            recs=None, prof=None, race=None, inparty=None, equip=None, pack=None):
        b = self.ch(slot)
        if inparty is not None:
            c.set(b + C_INPARTY, u8(inparty))
        if prof is not None:
            c.set(b + C_PROF, u32(prof))
        if race is not None:
            c.set(b + C_RACE, u32(race))
            if race == 15:
                # Androids are recruited NPCs only: CalcAttacks reads
                # GetNpcState(XChar.npc_index), and a PC row's -1 reads the heap
                # header before the NPC array (retail crashed on it at 0x0050b820).
                # Any in-range index keeps it deterministic.
                c.set(self.xr(slot) + X_NPC, u32(0))
        if conds is not None:
            c.set(b + C_COND, u32s(conds))
        if ench is not None:
            c.set(b + C_ENCH, ench_bytes(ench))
        if high is not None:
            c.set(b + C_HIGH, u32s(high))
        if hp is not None:
            c.set(b + C_HP, u32(hp))
        if hpadj is not None:
            c.set(b + C_HPADJ, u32(hpadj))
        if fatigue is not None:
            c.set(b + C_FATIGUE, u32(fatigue))
        if recs is not None:
            c.set(b + C_RECS, recs)
        for k, data in (equip or {}).items():
            c.set(b + C_EQUIP + 12 * k, data)
        for k, data in (pack or {}).items():
            c.set(b + C_PACK + 12 * k, data)

    # --- captures
    def cap_char(self, c, slot):
        c.cap(self.ch(slot), CHAR, 'char%d' % slot, floats=CHAR_FLOATS)

    def cap_party(self, c, slots):
        for s in slots:
            self.cap_char(c, s)

    def cap_rows(self, c):
        c.cap(self.xr(0), 8 * ROW, 'xchar', ignore=XCHAR_IGNORE)

    def cap_formation(self, c):
        c.cap(self.GS + GS_FORM, 0x84, 'formation')

    def cap_portrait(self, c, slot):
        c.cap(self.GX + slot * GX_ENTRY + GX_POSE, 0x0f, 'portrait%d' % slot)

    def cap_globals(self, c, text=True):
        c.cap(self.GX + GX_SIGHT, 1, 'sight_refresh')
        c.cap(self.GX + GX_ENCDIRTY, 1, 'enc_dirty')
        c.cap(self.GS + GS_SKIP, 1, 'skip_reaction')
        if text:
            c.cap(self.notice_marker, 0x10, 'notice_posted')

    def row_targets(self, c, r, monster_ids=(77,)):
        """Pin target_out_of_combat / target_in_combat of the PC rows. Character and monster
        targets have the exact shape SetTargetToCharacter/-Monster builds, so ApplyTarget's
        memcmp can match them and the repick path runs."""
        for s in PCS:
            for off in (R_TOOC, R_TIC):
                x = r.random()
                if x < 0.35:
                    t = struct.pack('<Iiii', 1, r.choice(PCS), -1, -1)          # character
                elif x < 0.55:
                    t = struct.pack('<Iiii', 3, -1, r.choice(monster_ids), -1)  # monster
                elif x < 0.6:
                    t = struct.pack('<Iiii', 4, -1, -1, 11)                     # group
                else:
                    t = struct.pack('<Iiii', 0, -1, -1, -1)                     # none
                c.set(self.xr(s) + off, t + bytes(16))

    def portrait_state(self, c, r, slot):
        c.set(self.GX + slot * GX_ENTRY + GX_POSE, u32(r.choice([0, 1, 2, 2, 3])))
        c.set(self.GX + slot * GX_ENTRY + 0x99, u8(r.choice([0, 1])))

    # --- fake monster world
    def mon_addr(self, k):
        return self.S[0] + MON_OFF[k]

    def grp_addr(self, k):
        return self.S[2] + GRP_OFF[k]

    def world(self, c, mons, groups=(), records=(), in_list=None, p3d=True):
        """mons: list of bytes (M_SET each) for S0 slots; groups: list of (bytes, [member ids]);
        records: list of (kind, attrs5, level) for SPECIES[i]. in_list: monster indexes in the PList."""
        S = self.S
        for k, blob in enumerate(mons):
            a = self.mon_addr(k)
            c.set(a, blob)
            if p3d:
                c.setp(a + M_P3D, self.real_p3d)
            if blob[M_INCOMBAT]:
                c.setp(a + M_PCOMBAT, S[4] + MCOMBAT_OFF[k])
        idx = list(range(len(mons))) if in_list is None else list(in_list)
        c.setp(S[1], S[1] + 0x10)
        c.set(S[1] + 4, u32s([16, len(idx)]))
        for j, k in enumerate(idx):
            c.setp(S[1] + 0x10 + 4 * j, self.mon_addr(k))
        for k, (gblob, members) in enumerate(groups):
            g = self.grp_addr(k)
            il = S[2] + ILIST_OFF[k]
            c.set(g, gblob)
            c.setp(g + G_LIST, il)
            c.setp(il, il + 0x10)
            c.set(il + 4, u32s([16, len(members), 0]) + u32s(members))
        if groups:
            gp = S[2] + GPLIST_OFF
            c.setp(gp, gp + 0x10)
            c.set(gp + 4, u32s([16, len(groups)]))
            for k in range(len(groups)):
                c.setp(gp + 0x10 + 4 * k, self.grp_addr(k))
        for k, (kind, attrs, level) in enumerate(records):
            rec = S[3] + REC_OFF[k]
            c.set(rec + REC_KIND, u8(kind))
            c.set(rec + REC_ATTRS, bytes(attrs))
            c.set(rec + REC_LEVEL, u8(level))
            c.setp(self.GX + GX_RECCACHE + 4 * SPECIES[k], rec)
        self.lists(c, S[1], (S[2] + GPLIST_OFF) if groups else S[7])

    def cap_mon(self, c, k):
        c.cap(self.mon_addr(k), M_SIZE, 'mon%d' % k, ignore=list(M_PTRS), floats=MON_FLOATS)

    def cap_group(self, c, k):
        c.cap(self.grp_addr(k), G_SIZE, 'group%d' % k, ignore=[G_LIST])

    def cap_mcombat(self, c, k):
        c.cap(self.S[4] + MCOMBAT_OFF[k], MC_SIZE, 'mcombat%d' % k, ignore=[0x16])


# ---------------------------------------------------------------- fake monster builders
def mon_blob(r, loc, group_id, species=SPECIES[0], conds=None, ench=None, arg=0, hp=None,
             disp=None, in_combat=0, visible=0, control=0, elemental=-1, binding=None):
    b = bytearray(M_SET)
    struct.pack_into('<iiI', b, 0, loc, group_id, species)
    b[M_ACTIVE] = 0
    b[M_INCOMBAT] = in_combat
    b[M_DISP] = disp if disp is not None else r.choice([0, 1, 1, 2])
    struct.pack_into('<ffff', b, 0x17, r.uniform(-500, 500), r.uniform(-50, 50), r.uniform(-500, 500),
                     r.uniform(0, 6.28))
    hpmax = r.choice([5, 20, 45, 80, 150, 400, 1200])
    if hp is None:
        hp = r.randrange(1, hpmax + 1)
    stmax = r.choice([10, 50, 120, 300])
    struct.pack_into('<iIii', b, M_HPMAX, hpmax, unsigned(hp), stmax, r.randrange(stmax + 1))
    struct.pack_into('<ffff', b, M_REGEN_LO, r.uniform(0, 1), r.uniform(0, 1), r.uniform(0, 1),
                     r.uniform(0, 1))
    conds = conds if conds is not None else [0] * 20
    b[M_COND:M_COND + 80] = u32s(conds)
    ench = ench if ench is not None else [[0, 0, 0, 0]] * 8
    b[M_ENCH:M_ENCH + 96] = ench_bytes(ench)
    struct.pack_into('<II', b, M_HIGH, highest_of(conds) if r.random() < 0.8 else r.randrange(20),
                     unsigned(arg))
    for k in range(12):
        if r.random() < 0.08:
            struct.pack_into('<BiiII', b, M_EFFECTS + 0x11 * k, 1, r.choice(EFFECT_IDS),
                             r.randrange(0, 30), r.choice([0, 50, 100, 150]), r.randrange(1, 60))
    for k in range(0x67):
        b[M_MODS + k] = r.randrange(256)
    struct.pack_into('<i', b, M_FATIGUE, r.randrange(5))
    for k in range(5):
        b[M_ATTRS + k] = r.randrange(1, 126)
    b[M_BIND] = binding if binding is not None else (r.randrange(4) if r.random() < 0.3 else 0)
    b[M_MOTIONLESS] = 0
    struct.pack_into('<f', b, M_SCALE, 1.0)
    b[M_VISIBLE] = visible
    b[M_TARGET:M_TARGET + 0x20] = gen_combat_slot(r)
    struct.pack_into('<I', b, M_CONTROL, control)
    for k in range(0x34):
        b[M_CTARGET + k] = r.randrange(256) if r.random() < 0.3 else 0
    struct.pack_into('<i', b, M_ELEMENTAL, elemental)
    return bytes(b)


def group_blob(r, gid, members, disp=None, leader=0, allies=(0, 0, 0, 0), registered=0):
    b = bytearray(G_SIZE)
    struct.pack_into('<iI', b, 0, gid, len(members))
    struct.pack_into('<iii', b, 0x0c, len(members), len(members), r.choice([0, 1, len(members), 9]))
    b[0x29] = 0
    b[G_DISP] = disp if disp is not None else r.choice([0, 1, 2])
    struct.pack_into('<i', b, 0x9b, -1)
    struct.pack_into('<ii', b, 0x9f, members[0] if members else 0, leader)
    struct.pack_into('<4i', b, G_ALLIES, *allies)
    b[G_REG] = registered
    return bytes(b)


def gen_record(r, kind=None):
    if kind is None:
        kind = r.choice([20, 20, 22, 22, 17, 17, 0, 4, 5, 13, 1, 9])
    return (kind, [r.randrange(1, 126) for _ in range(5)], r.choice([1, 3, 7, 12, 20, 33, 50, 99, 255]))


def mon_ids(r, n):
    pool = [1, 2, 3, 7, 42, 100, 255, 256, 1000, 4096, 31337, 65535, 0x12345, 0x7fffffff, -2, 0]
    out = []
    while len(out) < n:
        v = r.choice(pool)
        if v not in out:
            out.append(v)
    return out


def safe_set_monster(cond, duration, poison, old, arg, kind, hp, disp):
    """Mirror of SetMonsterCondition's entry checks: True when the call stays clear of the
    icon/sight/dying paths (see module docstring)."""
    if cond == POISONED and poison == 0:
        return True
    if cond in (DISEASED, INFATUATED, DEAD, MISSING):
        duration = INDEFINITE
    elif duration == 0:
        return True
    if hp == 0 or would_be_immune(kind, cond):
        return True
    handled = unsigned(old) < unsigned(duration)
    if handled and old == 0:
        if cond == TURNCOAT:
            return disp == 0
        if cond != NONE:
            return False
    if unsigned(poison) > unsigned(arg):
        handled = True
    if handled and cond >= DEAD:
        return False
    return True


# ---------------------------------------------------------------- generators
def gen_flag(ctx, w):
    fn = ctx.fn(0x005248a0)    # bool GetConditionRecordFlag(int slot, W8CharacterDependence dep)
    for i in range(ctx.n(120)):
        r = ctx.rng('flag', i)
        c = w.case('GetConditionRecordFlag', i, fn, ret='b')
        slot = r.randrange(8)
        slots = PCS + ((slot,) if slot < 2 else ())
        w.party(c, r, slots)
        recs = gen_records(r, level=r.choice([3, 9]), monster=500)
        w.put(c, slot, recs=recs)
        dep = r.randrange(4)
        c.arg(slot).arg(dep)
        c.note(slot=slot, dep=dep, active=recs[0x11 * dep + 8])
        w.check(c)


def gen_normalize(ctx, w):
    fn = ctx.fn(0x00522e80)    # void NormalizeItemQuantityKind(W8ItemInstance*)
    combos = [(k, s, u) for k in (0, 1, 2, 3, 4) for s in (0, 1, 200) for u in (0, 1, 200)]
    item = w.S[5] + 0x200
    for i in range(ctx.n(320)):
        r = ctx.rng('normalize', i)
        c = w.case('NormalizeItemQuantityKind', i, fn)
        if i < len(combos):
            kind, stack, uses = combos[i]
        else:
            kind = r.choice([0, 1, 1, 2, 2, 3, 4, -1])
            stack, uses = r.choice(QTY), r.choice(QTY)
        item_id = -1 if kind == -1 else r.choice(ITEMS_QK[kind])
        blob = item_bytes(item_id, stack, uses, r.choice([0, 1]),
                          [r.randrange(256) for _ in range(5)])
        c.set(item, blob)
        c.arg(item)
        c.cap(item, 12, 'item')
        c.note(item=item_id, qk=kind, stack=stack, uses=uses)
        w.check(c)


def gen_sanitize(ctx, w):
    fn = ctx.fn(0x00522ef0)    # void SanitizeLoadedItems(void)
    for i in range(ctx.n(120)):
        r = ctx.rng('sanitize', i)
        c = w.case('SanitizeLoadedItems', i, fn)
        occupied = [s for s in PCS if r.random() < 0.9]
        w.base(c, r)
        w.party(c, r, PCS, occupied)
        mods = {}
        for s in r.sample(PCS, r.choice([1, 2, 3])):
            equip = {}
            for _ in range(r.choice([1, 2, 3])):
                k = r.randrange(12)
                qk = r.choice([1, 2, 3, 4, 0])
                equip[k] = item_bytes(r.choice(ITEMS_QK[qk]), r.choice(QTY), r.choice(QTY))
            prof = r.randrange(15) if r.random() < 0.12 else None   # some gear becomes unusable
            pack = None
            if prof is not None or r.random() < 0.5:                 # whole synthetic backpack
                pack = b''
                for _ in range(8):
                    qk = r.choice([1, 2, 3, 4, 0, -1, -1, -1] if prof is None else [-1, -1, 1, 2])
                    pack += item_bytes(-1 if qk == -1 else r.choice(ITEMS_QK[qk]), r.choice(QTY),
                                       r.choice(QTY))
                c.set(w.ch(s) + C_PACK, pack)
            w.put(c, s, equip=equip, prof=prof)
            mods[s] = (sorted(equip), pack is not None, prof)
        n = r.choice([0, 1, 3, 6, 10, 12])
        pool = b''
        for _ in range(n):
            qk = r.choice([1, 1, 2, 2, 3, 4, 0, -1])
            pool += item_bytes(-1 if qk == -1 else r.choice(ITEMS_QK[qk]), r.choice(QTY), r.choice(QTY))
        c.set(w.GS + GS_POOLCNT, u32(n))
        if pool:
            c.set(w.GS + GS_POOL, pool)
        w.cap_party(c, PCS)
        w.cap_rows(c)
        c.cap(w.GS + GS_POOL, 500 * 12, 'party_pool')
        c.cap(w.GS + GS_POOLCNT, 4, 'party_pool_count')
        c.cap(w.GS + GS_FACTS, 4000, 'facts')
        w.cap_globals(c)
        c.note(occupied=occupied, pool=n, mods=str(mods))
        w.check(c)


def gen_recompute(ctx, w):
    fn = ctx.fn(0x005237e0)    # void RecomputeCharacterHighestCondition(int slot)
    for i in range(ctx.n(300)):
        r = ctx.rng('recompute', i)
        c = w.case('RecomputeCharacterHighestCondition', i, fn)
        combat = 1 if i % 6 == 5 else 0
        slot = pick_slot(r, 0.06)
        slots = PCS + ((slot,) if slot < 2 else ())
        w.base(c, r, combat=combat, surprise=1 if r.random() < 0.15 else 0)
        w.party(c, r, slots)
        conds = gen_conds(r, r.choice([0.0, 0.05, 0.15, 0.3, 0.6]))
        hi_old = old_highest(r, conds)
        hp = 0 if r.random() < 0.05 else None
        w.put(c, slot, conds=conds, high=(hi_old, 0, 0), hp=hp)
        others = {}
        for s in PCS:
            if s != slot and r.random() < 0.3:
                others[s] = r.choice([0, 0, 5, 15, 17, 18, 19])
                w.put(c, s, high=(others[s], 0, 0))
        w.portrait_state(c, r, slot)
        alive = [s for s in PCS if (others.get(s, 0) < DEAD if s != slot else hi_old < DEAD)]
        dead = [s for s in PCS if s not in alive]
        synth = r.random() < 0.5
        if synth:
            c.set(w.GS + GS_FORM, gen_formation(r, alive if r.random() < 0.85 else PCS, dead))
        if combat:
            c.setp(w.GCS, w.S[6])
            c.set(w.S[6] + CS_SAVEDFORM, gen_formation(r, alive, dead))
            c.set(w.GX + GX_EDITFORM, gen_formation(r, PCS if r.random() < 0.3 else alive, dead))
        c.arg(slot)
        w.cap_party(c, slots)
        w.cap_formation(c)
        w.cap_portrait(c, slot)
        w.cap_globals(c)
        if combat:
            c.cap(w.S[6] + CS_SAVEDFORM, 0x84, 'combat_saved_formation')
            c.cap(w.GX + GX_EDITFORM, 0x84, 'edited_formation')
        c.note(slot=slot, combat=combat, old_highest=hi_old, new_highest=highest_of(conds),
               synth_formation=synth)
        w.check(c)


def gen_apply_char(ctx, w):
    fn = ctx.fn(0x00523940)    # void ApplyCharacterCondition(int, W8EnchantmentSlot, int, UINT, UINT)
    for i in range(ctx.n(300)):
        r = ctx.rng('apply_char', i)
        c = w.case('ApplyCharacterCondition', i, fn)
        slot = pick_slot(r, 0.04)
        slots = PCS + ((slot,) if slot < 2 else ())
        w.base(c, r)
        w.party(c, r, slots)
        ench = gen_ench(r, r.choice([0.0, 0.2, 0.5]))
        top = ench_top(ench) if r.random() < 0.85 else r.randrange(8)
        conds = gen_conds(r, 0.1) if r.random() < 0.3 else None
        w.put(c, slot, ench=ench, conds=conds,
              high=(highest_of(conds) if conds else 0, top, r.choice(POISON)))
        x = r.random()
        eslot = 2 if x < 0.3 else (6 if x < 0.45 else r.randrange(8))
        power = ench[eslot][0]
        argument = r.choice([power - 1, power, power + 1, power + 1, 0, 1, 2, 5, 10, 50, 100,
                             0xffffffff, 0x80000000, 0x7fffffff, r.randrange(1, 30)])
        duration = r.choice([0, 1, 5, 10, 60, 0xffff, 0x10000, 0xffffffff, r.randrange(1, 200)])
        percent = r.choice(PERCENT_ARG)
        c.arg(slot).arg(eslot).arg(argument).arg(duration).arg(percent)
        w.cap_party(c, slots)
        w.cap_globals(c, text=False)
        c.note(slot=slot, eslot=eslot, power=unsigned(power), argument=unsigned(argument))
        w.check(c)


def setup_hexed(c, w, r, conds):
    """HEXED removal is refused while INFATUATED runs, outside level bands 9/10."""
    if r.random() < 0.5:
        conds[INFATUATED] = pick_dur(r)
    level = r.choice(LEVELS)
    c.set(w.GS + GS_LEVEL, u32(level))
    return level


def setup_insane(c, w, r, slot):
    """Destinae Dominus on the party keeps INSANE on its holder unless the Helm of Serenity
    is worn. Returns a description of the placement."""
    where = r.choice(['none', 'equip', 'equip', 'pack', 'other', 'pool', 'hand'])
    holder = slot
    if where in ('equip', 'pack'):
        k = r.randrange(12 if where == 'equip' else 8)
        if where == 'equip':
            w.put(c, slot, equip={k: item_bytes(ITEM_DD)})
        else:
            w.put(c, slot, pack={k: item_bytes(ITEM_DD)})
    elif where == 'other':
        holder = r.choice([s for s in PCS if s != slot] or [slot])
        w.put(c, holder, equip={r.randrange(12): item_bytes(ITEM_DD)})
    elif where == 'pool':
        c.set(w.GS + GS_POOLCNT, u32(r.choice([1, 2])))
        c.set(w.GS + GS_POOL, item_bytes(r.choice([ITEM_DD, 46])) + item_bytes(ITEM_DD))
    elif where == 'hand':
        c.set(w.GS + GS_CURSOR, b'\x01')
        c.set(w.GS + GS_INHAND, item_bytes(ITEM_DD))
    helm = r.random() < 0.5 and where != 'none'
    if helm:
        w.put(c, holder, equip={r.choice([0, 1, 2, 3, 4, 5, 10, 11]): item_bytes(ITEM_HELM)})
    return '%s/helm=%d/holder=%d' % (where, helm, holder)


def char_scenario(c, w, r, slot, cond, present=0.85, edge=0.12):
    """Random condition state on the target with the tested condition running (or not)."""
    conds = gen_conds(r, r.choice([0.0, 0.05, 0.15, 0.3]), edge)
    conds[cond] = pick_dur(r, edge) if r.random() < present else 0
    extra = {}
    if cond == HEXED:
        extra['level'] = setup_hexed(c, w, r, conds)
    if cond == INSANE:
        extra['dd'] = setup_insane(c, w, r, slot)
    return conds, extra


def gen_tick_char(ctx, w):
    fn = ctx.fn(0x005236a0)    # void TickCharacterCondition(UINT slot, W8Condition, UINT minutes)
    for i in range(ctx.n(300)):
        r = ctx.rng('tick_char', i)
        c = w.case('TickCharacterCondition', i, fn)
        slot = pick_slot(r, 0.04)
        slots = PCS + ((slot,) if slot < 2 else ())
        w.base(c, r, suspended=1 if r.random() < 0.1 else 0)
        w.party(c, r, slots)
        w.row_targets(c, r)
        cond = POISONED if r.random() < 0.35 else r.randrange(20)
        conds, extra = char_scenario(c, w, r, slot, cond, present=0.93)
        dur = conds[cond]
        if slot < 2 and dur == 0:
            conds[cond] = dur = r.choice(DUR_SMALL)
        arg = r.choice(POISON)
        if dur:
            minutes = r.choice(MINUTES + [dur - 1, dur, dur + 1, dur // 2, dur // 3])
        else:
            minutes = r.choice(MINUTES)
        if slot < 2:                  # keep the RPC slot away from the notice-posting removal
            minutes = r.randrange(0, max(1, dur))
        w.put(c, slot, conds=conds, high=(old_highest(r, conds), 0, arg),
              hp=0 if r.random() < 0.04 else None)
        if r.random() < 0.3:
            c.set(w.GS + GS_FORM, gen_formation(r, PCS))
        c.arg(slot).arg(cond).arg(minutes)
        w.cap_party(c, slots)
        w.cap_rows(c)
        w.cap_formation(c)
        w.cap_portrait(c, slot)
        w.cap_globals(c)
        c.note(slot=slot, cond=cond, dur=unsigned(dur), minutes=unsigned(minutes),
               poison=unsigned(arg), **extra)
        w.check(c)


def gen_remove_char(ctx, w):
    fn = ctx.fn(0x00523330)    # void RemoveCharacterCondition(int slot, W8Condition, bool announce)
    weights = list(range(20)) + [HEXED] * 4 + [INSANE] * 5 + [TURNCOAT] * 2 + [DRAINED, POISONED,
                                                                              BLIND, MISSING]
    for i in range(ctx.n(400)):
        r = ctx.rng('remove_char', i)
        c = w.case('RemoveCharacterCondition', i, fn)
        combat = 1 if i % 13 == 12 else 0
        slot = pick_slot(r, 0.04)
        slots = PCS + ((slot,) if slot < 2 else ())
        suspended = 1 if r.random() < 0.15 else 0
        w.base(c, r, combat=combat, suspended=suspended)
        w.party(c, r, slots)
        w.row_targets(c, r)
        cond = r.choice(weights)
        conds, extra = char_scenario(c, w, r, slot, cond)
        hpadj = r.choice([0, -5, 10, -100]) if cond == DRAINED else None
        fatigue = r.choice([0, 3, 50, 0xffffffff]) if cond == DRAINED else None
        arg = r.choice(POISON)
        hp = 0 if r.random() < 0.05 else None
        w.put(c, slot, conds=conds, high=(old_highest(r, conds), 0, arg), hp=hp, hpadj=hpadj,
              fatigue=fatigue)
        for s in PCS:
            if s != slot and r.random() < 0.2:
                oc = gen_conds(r, 0.15)
                w.put(c, s, conds=oc, high=(highest_of(oc), 0, 0))
        w.portrait_state(c, r, slot)
        if r.random() < 0.3:
            c.set(w.GS + GS_FORM, gen_formation(r, PCS))
        if combat:
            c.setp(w.GCS, w.S[6])
            c.set(w.S[6] + CS_CHARS + slot * CS_ROW + CS_BERSERK, u8(r.choice([0, 1, 1])))
            c.set(w.xr(slot) + R_TIC, gen_combat_slot(r, r.choice([0, 1])))
            c.set(w.xr(slot) + R_TOOC, gen_combat_slot(r, r.choice([0, 1])))
            c.set(w.S[6] + CS_SAVEDFORM, gen_formation(r, PCS))
            c.set(w.GX + GX_EDITFORM, gen_formation(r, PCS))
        announce = r.choice([0, 0, 0, 1, 1, 1]) if r.random() < 0.95 else r.choice([0x100, 0x201])
        c.arg(slot).arg(cond).arg(announce)
        w.cap_party(c, slots)
        w.cap_rows(c)
        w.cap_formation(c)
        w.cap_portrait(c, slot)
        w.cap_globals(c)
        if combat:
            c.cap(w.S[6], 0xa64, 'combat_state', ignore=[0x7b8, 0x8c0, 0xa4c])
            c.cap(w.GX + GX_EDITFORM, 0x84, 'edited_formation')
        c.note(slot=slot, cond=cond, running=unsigned(conds[cond]), announce=announce,
               suspended=suspended, combat=combat, **extra)
        w.check(c)


def gen_set_char(ctx, w):
    fn = ctx.fn(0x00522fe0)    # UINT8 SetCharacterCondition(int, W8Condition, int dur, int poison, char, char)
    weights = list(range(20)) + [AFRAID] * 3 + [INSANE] * 3 + [TURNCOAT] * 3 + [POISONED] * 3 + \
        [DEAD] * 3 + [MISSING, ASLEEP, IRRITATED, HEXED, BLIND]
    real_deaths = 0
    for i in range(ctx.n(400)):
        r = ctx.rng('set_char', i)
        c = w.case('SetCharacterCondition', i, fn, ret='b')
        slot = pick_slot(r, 0.04)
        slots = PCS + ((slot,) if slot < 2 else ())
        suspended = 1 if (r.random() < 0.1 and slot >= 2) else 0
        w.base(c, r, suspended=suspended)
        w.party(c, r, slots)
        w.row_targets(c, r)
        cond = r.choice(weights)
        conds = gen_conds(r, r.choice([0.0, 0.05, 0.15, 0.3]))
        old = conds[cond] = pick_dur(r) if r.random() < 0.4 else 0
        duration = r.choice([0, 1, 2, 5, 30, 100, 9998, 9999, 10000, -1, -100, 0x7fffffff,
                             0x80000000, unsigned(old) - 1, old, old + 1, r.randrange(1, 300)])
        if cond == POISONED:
            poison = r.choice(POISON)
        else:
            poison = 0 if r.random() < 0.75 else r.choice(POISON)
        prof = race = None
        trait = r.random()
        if trait < 0.12:
            prof = 2                         # Valkyrie: Cheat Death
        elif trait < 0.22:
            prof = r.choice([4, 13])         # FEARLESS (13 also mental immunity)
        elif trait < 0.30:
            race = 15                        # trait 0x1e
        if slot < 2:                         # RPC slot: no notice-posting branches
            suspended = 0
            prof = race = None
        death = ''
        if cond == DEAD:
            x = r.random()
            if x < 0.55 or (slot < 2 and x < 0.8):
                prof = 2
                conds[UNCONSCIOUS] = r.choice([0, 1, 3, 6, 6, 7, 8, 30])
                death = 'cheat'
            elif real_deaths < 4 and slot >= 2 and x > 0.9:
                real_deaths += 1
                death = 'real'
            else:
                conds[DEAD] = r.choice([9999, 10000, 0xffffffff])
                death = 'running'
        w.put(c, slot, conds=conds, high=(old_highest(r, conds), 0, r.choice(POISON)), prof=prof,
              race=race, hp=0 if r.random() < 0.04 else None)
        for s in PCS:
            if s != slot and r.random() < 0.15:
                oc = gen_conds(r, 0.15)
                w.put(c, s, conds=oc, high=(highest_of(oc), 0, 0))
        w.portrait_state(c, r, slot)
        if r.random() < 0.3:
            c.set(w.GS + GS_FORM, gen_formation(r, PCS))
        alt = r.choice([0, 1])
        announce = r.choice([0, 1]) if slot >= 2 else 0
        c.arg(slot).arg(cond).arg(duration).arg(poison).arg(alt).arg(announce)
        w.cap_party(c, slots)
        w.cap_rows(c)
        w.cap_formation(c)
        w.cap_portrait(c, slot)
        w.cap_globals(c)
        c.note(slot=slot, cond=cond, old=unsigned(old), duration=unsigned(duration),
               poison=unsigned(poison), prof=prof, race=race, suspended=suspended, death=death)
        w.check(c)


def gen_clear_ench_char(ctx, w):
    fn = ctx.fn(0x00523a80)    # void ClearCharacterEnchantmentSlot(int slot, W8EnchantmentSlot)
    for i in range(ctx.n(150)):
        r = ctx.rng('clear_ench_char', i)
        c = w.case('ClearCharacterEnchantmentSlot', i, fn)
        slot = pick_slot(r, 0.04)
        slots = PCS + ((slot,) if slot < 2 else ())
        w.base(c, r)
        w.party(c, r, slots)
        ench = gen_ench(r, r.choice([0.1, 0.3, 0.6, 0.9]))
        eslot = 6 if r.random() < 0.2 else r.randrange(8)
        top = ench_top(ench) if r.random() < 0.85 else r.randrange(8)
        w.put(c, slot, ench=ench, high=(0, top, 0))
        c.arg(slot).arg(eslot)
        w.cap_party(c, slots)
        w.cap_globals(c, text=False)
        c.note(slot=slot, eslot=eslot, turns=[e[3] for e in ench])
        w.check(c)


def gen_tick_ench_char(ctx, w):
    fn = ctx.fn(0x00523b30)    # void TickCharacterEnchantmentSlot(int slot, W8EnchantmentSlot, UINT turns)
    for i in range(ctx.n(200)):
        r = ctx.rng('tick_ench_char', i)
        c = w.case('TickCharacterEnchantmentSlot', i, fn)
        slot = pick_slot(r, 0.04)
        slots = PCS + ((slot,) if slot < 2 else ())
        w.base(c, r)
        w.party(c, r, slots)
        ench = gen_ench(r, r.choice([0.2, 0.5, 0.9]))
        eslot = 6 if r.random() < 0.2 else r.randrange(8)
        rem = ench[eslot][3]
        turns = r.choice([0, 1, 2, 5, rem - 1, rem, rem + 1, 0xffffffff, 0x80000000, rem // 2])
        w.put(c, slot, ench=ench, high=(0, ench_top(ench) if r.random() < 0.85 else r.randrange(8), 0))
        c.arg(slot).arg(eslot).arg(turns)
        w.cap_party(c, slots)
        w.cap_globals(c, text=False)
        c.note(slot=slot, eslot=eslot, remaining=unsigned(rem), turns=unsigned(turns))
        w.check(c)


def party_states(c, w, r, conds_for, occupied):
    """conds_for(slot) -> list of 20 durations; writes each occupied character's state."""
    out = {}
    for s in PCS:
        conds = conds_for(s)
        w.put(c, s, conds=conds, high=(old_highest(r, conds), 0, r.choice(POISON)))
        out[s] = conds
    return out


def gen_remove_party(ctx, w):
    fn = ctx.fn(0x005246c0)    # void RemoveConditionFromParty(W8Condition)
    for i in range(ctx.n(150)):
        r = ctx.rng('remove_party', i)
        c = w.case('RemoveConditionFromParty', i, fn)
        cond = r.randrange(20)
        occupied = [s for s in PCS if r.random() < 0.85]
        w.base(c, r, level=r.choice(LEVELS))
        w.party(c, r, PCS, occupied)
        w.row_targets(c, r)

        def conds_for(s):
            conds = gen_conds(r, 0.1)
            conds[cond] = pick_dur(r) if r.random() < 0.5 else 0
            if cond == HEXED and r.random() < 0.4:
                conds[INFATUATED] = pick_dur(r)
            return conds
        states = party_states(c, w, r, conds_for, occupied)
        if cond == INSANE:
            setup_insane(c, w, r, r.choice(PCS))
        c.arg(cond)
        w.cap_party(c, PCS)
        w.cap_rows(c)
        w.cap_formation(c)
        w.cap_globals(c)
        c.note(cond=cond, occupied=occupied,
               with_cond=[s for s in PCS if states[s][cond]])
        w.check(c)


def gen_remove_all_party(ctx, w):
    fn = ctx.fn(0x00524720)    # void RemoveAllConditionsFromParty(void)
    for i in range(ctx.n(100)):
        r = ctx.rng('remove_all_party', i)
        c = w.case('RemoveAllConditionsFromParty', i, fn)
        occupied = [s for s in PCS if r.random() < 0.85]
        w.base(c, r, level=r.choice(LEVELS))
        w.party(c, r, PCS, occupied)
        w.row_targets(c, r)
        density = r.choice([0.05, 0.15, 0.3, 0.6])
        states = party_states(c, w, r, lambda s: gen_conds(r, density), occupied)
        if r.random() < 0.3:
            setup_insane(c, w, r, r.choice(PCS))
        w.cap_party(c, PCS)
        w.cap_rows(c)
        w.cap_formation(c)
        w.cap_globals(c)
        c.note(occupied=occupied, conds={s: [k for k in range(20) if states[s][k]] for s in PCS})
        w.check(c)


def gen_copy_mon_to_char(ctx, w):
    fn = ctx.fn(0x00524250)    # void CopyMonsterConditionsToCharacter(W8Character*, const W8MonsterInfo*)
    for i in range(ctx.n(200)):
        r = ctx.rng('copy_mon_to_char', i)
        c = w.case('CopyMonsterConditionsToCharacter', i, fn)
        slot = r.choice(PCS)
        w.base(c, r)
        w.party(c, r, PCS)
        w.row_targets(c, r)
        mconds = gen_conds(r, r.choice([0.05, 0.15, 0.3, 0.5]))
        marg = r.choice(POISON)
        conds = gen_conds(r, r.choice([0.0, 0.1, 0.3]))
        prof = r.choice([None, None, None, 2, 4, 13]) if r.random() < 0.4 else None
        race = 15 if r.random() < 0.08 else None
        if mconds[DEAD]:
            if r.random() < 0.5:
                prof = 2
                conds[UNCONSCIOUS] = r.choice([0, 2, 6, 7])
            else:
                conds[DEAD] = r.choice([9999, 0xffffffff])
        w.put(c, slot, conds=conds, high=(old_highest(r, conds), 0, r.choice(POISON)), prof=prof,
              race=race)
        mon = w.S[0]
        c.set(mon, mon_blob(r, 77, 5, conds=mconds, arg=marg))
        c.arg(w.ch(slot)).arg(mon)
        w.cap_party(c, PCS)
        w.cap_rows(c)
        w.cap_formation(c)
        w.cap_portrait(c, slot)
        w.cap_globals(c)
        c.cap(mon, M_SET, 'monster_arg')
        c.note(slot=slot, mon_conds=[k for k in range(20) if mconds[k]], mon_arg=unsigned(marg),
               prof=prof, race=race)
        w.check(c)


def gen_release(ctx, w):
    fn = ctx.fn(0x005248d0)    # void ReleaseMonsterConditionBindings(W8MonsterInfo*)
    for i in range(ctx.n(200)):
        r = ctx.rng('release', i)
        c = w.case('ReleaseMonsterConditionBindings', i, fn)
        level = r.choice([1, 9, 17, 30])
        w.base(c, r, level=level, isolate=False)
        w.party(c, r, PCS)
        ida, idb, idc = mon_ids(r, 3)
        mask = r.choice([0, 1, 2, 3, 3, 3, r.randrange(16)])
        a = mon_blob(r, ida, 5, binding=mask)
        b = mon_blob(r, idb, 5, elemental=ida if r.random() < 0.5 else r.choice([-1, idc]))
        m3 = mon_blob(r, idc, 5, elemental=ida if r.random() < 0.3 else -1)
        in_list = r.choice([[1, 2], [0, 1, 2], [2, 1], [1]])
        w.world(c, [a, b, m3], in_list=in_list, records=[gen_record(r)], p3d=False)
        bound = []
        for s in r.sample(PCS, r.choice([0, 1, 2, 3])):
            recs = bytearray(gen_records(r, level=level, monster=ida))
            for dep in (0, 1):
                if r.random() < 0.6:
                    struct.pack_into('<iiB', recs, 0x11 * dep,
                                     level if r.random() < 0.85 else level + 1,
                                     ida if r.random() < 0.85 else idb, r.choice([0, 1, 1]))
            conds = gen_conds(r, 0.1)
            conds[MISSING] = pick_dur(r) if r.random() < 0.7 else 0
            w.put(c, s, recs=bytes(recs), conds=conds, high=(highest_of(conds), 0, 0),
                  inparty=0 if r.random() < 0.1 else None)
            bound.append(s)
        c.arg(w.mon_addr(0))
        w.cap_party(c, PCS)
        w.cap_rows(c)
        w.cap_formation(c)
        w.cap_globals(c)
        for k in range(3):
            w.cap_mon(c, k)
        c.note(mask=mask, ids=[ida, idb, idc], in_list=in_list, bound=bound, level=level)
        w.check(c)


def gen_bind(ctx, w):
    fn = ctx.fn(0x00524780)    # void BindMonsterToCharacterDependence(UINT slot, UINT dep, int monster_id)
    for i in range(ctx.n(150)):
        r = ctx.rng('bind', i)
        c = w.case('BindMonsterToCharacterDependence', i, fn)
        level = r.choice([0, 3, 9, 17, 30, -1])
        w.base(c, r, level=level, isolate=False)
        slot = r.randrange(8) if r.random() < 0.1 else r.choice(PCS)
        slots = PCS + ((slot,) if slot < 2 else ())
        w.party(c, r, slots)
        ida, idb = mon_ids(r, 2)
        if r.random() < 0.05:
            ida = -1
        g0, g1, g2 = 11, 22, 33
        leader = g1 if r.random() < 0.3 else 0
        allies = [r.choice([0, 0, g1, g2]) for _ in range(4)]
        groups = [
            (group_blob(r, g0, [ida, idb], leader=leader, allies=allies,
                        registered=r.choice([0, 1])), [ida, idb]),
            (group_blob(r, g1, [idb], allies=[r.choice([0, g2]), 0, 0, 0],
                        registered=r.choice([0, 1])), [idb]),
            (group_blob(r, g2, [], registered=r.choice([0, 1])), []),
        ]
        a = mon_blob(r, ida, g0, binding=r.choice([0, 0, 1, 2, 3]))
        b = mon_blob(r, idb, g1 if r.random() < 0.3 else g0)
        w.world(c, [a, b], groups=groups, records=[gen_record(r)], p3d=False)
        w.put(c, slot, recs=gen_records(r, level=level, monster=ida))
        dep = r.choice([0, 1, 1, 0, 2, 3]) if r.random() < 0.15 else r.choice([0, 1])
        mid = r.choice([ida, ida, ida, idb])
        c.arg(slot).arg(dep).arg(mid)
        w.cap_char(c, slot)
        w.cap_mon(c, 0)
        w.cap_mon(c, 1)
        for k in range(3):
            w.cap_group(c, k)
        w.cap_globals(c, text=False)
        c.note(slot=slot, dep=dep, monster=mid, ids=[ida, idb], leader=leader, allies=allies,
               level=level)
        w.check(c)


def monster_case(c, w, r, cond_density=0.15, ench_density=0.0, visible_p=0.0, combat_p=0.25,
                 hp_zero=0.08):
    """Fake world with target A (+B in the same group): returns (ids, monster states)."""
    ida, idb = mon_ids(r, 2)
    rec_a, rec_b = gen_record(r), gen_record(r)
    in_combat = 1 if r.random() < combat_p else 0
    a_conds = gen_conds(r, cond_density)
    a_ench = gen_ench(r, ench_density)
    a_arg = r.choice(POISON)
    a_disp = r.choice([0, 0, 1, 1, 2])
    a_hp = 0 if r.random() < hp_zero else None
    visible = 1 if r.random() < visible_p else 0
    state = dict(id=ida, conds=a_conds, ench=a_ench, arg=a_arg, disp=a_disp, hp=a_hp,
                 in_combat=in_combat, visible=visible, kind=rec_a[0], level=rec_a[2],
                 control=r.choice([0, 0, 0, 1, 2]))
    return state, (idb, rec_a, rec_b)


def finish_monster_world(c, w, r, st, extra, groups_disp=None, one_record=False):
    idb, rec_a, rec_b = extra
    a = mon_blob(r, st['id'], 11, SPECIES[0], st['conds'], st['ench'], st['arg'], st['hp'],
                 st['disp'], st['in_combat'], st['visible'], st['control'])
    b_conds = gen_conds(r, 0.15)
    b = mon_blob(r, idb, 11, SPECIES[0] if one_record else SPECIES[1], b_conds, gen_ench(r, 0.1),
                 r.choice(POISON), disp=st['disp'], control=r.choice([0, 0, 1]))
    members = [st['id'], idb]
    groups = [(group_blob(r, 11, members, disp=groups_disp), members)]
    w.world(c, [a, b], groups=groups, records=[rec_a] if one_record else [rec_a, rec_b])
    if st['in_combat']:
        hate = u32s([r.randrange(0, 200) for _ in range(9)])
        c.set(w.S[4] + MCOMBAT_OFF[0] + MC_HATE, hate)
        c.set(w.S[4] + MCOMBAT_OFF[0] + MC_ADVANCING, u8(r.choice([0, 1])))


def cap_monster_world(c, w, st, rows=False):
    w.cap_mon(c, 0)
    w.cap_mon(c, 1)
    w.cap_group(c, 0)
    if st['in_combat']:
        w.cap_mcombat(c, 0)
    if rows:
        w.cap_rows(c)
    c.cap(w.GX + GX_HOSTILE, 4, 'hostile_monster_count')
    w.cap_globals(c)


def gen_set_mon(ctx, w):
    fn = ctx.fn(0x00523c00)    # void SetMonsterCondition(int id, W8Condition, int dur, int poison, W8TargetSource*, bool)
    for i in range(ctx.n(400)):
        r = ctx.rng('set_mon', i)
        c = w.case('SetMonsterCondition', i, fn)
        w.base(c, r, isolate=False)
        st, extra = monster_case(c, w, r, visible_p=0.06)
        for _ in range(60):
            cond = r.choice(list(range(20)) + [POISONED, TURNCOAT, TURNCOAT, NONE, HEXED, BLIND])
            old = st['conds'][cond]
            if r.random() < 0.7 and cond != NONE and not (cond == TURNCOAT and st['disp'] == 0):
                old = st['conds'][cond] = pick_dur(r) if old == 0 else old
            duration = r.choice([0, 1, 2, 5, 30, 100, 9998, 9999, 10000, -1, 0x80000000,
                                 unsigned(old) - 1, old, old + 1, old + 1, r.randrange(1, 500)])
            poison = r.choice(POISON) if cond == POISONED else (0 if r.random() < 0.8 else r.choice(POISON))
            if cond in (DEAD, MISSING) and r.random() < 0.7:
                st['conds'][cond] = old = r.choice([9999, 10000, 0xffffffff])
            hp = st['hp'] if st['hp'] is not None else 1
            if safe_set_monster(cond, duration, poison, old, st['arg'], st['kind'], hp, st['disp']):
                break
        else:
            cond, duration, poison = NONE, 0, 0
        finish_monster_world(c, w, r, st, extra)
        tsrc, ichar = gen_target_source(r)
        c.set(w.S[5], tsrc)
        announce = r.choice([0, 0, 1]) if st['visible'] else r.choice([0, 1])
        c.arg(st['id']).arg(cond).arg(duration).arg(poison).arg(w.S[5]).arg(announce)
        cap_monster_world(c, w, st)
        c.note(cond=cond, old=unsigned(st['conds'][cond]), duration=unsigned(duration),
               poison=unsigned(poison), kind=st['kind'], disp=st['disp'], hp0=st['hp'] == 0,
               in_combat=st['in_combat'], src_char=ichar, announce=announce)
        w.check(c)


def gen_clear_mon(ctx, w):
    fn = ctx.fn(0x00523f40)    # void ClearMonsterCondition(int id, W8Condition)
    conds_ok = [k for k in range(20) if k not in (HEXED, BLIND)]
    for i in range(ctx.n(250)):
        r = ctx.rng('clear_mon', i)
        c = w.case('ClearMonsterCondition', i, fn)
        w.base(c, r, isolate=False)
        w.party(c, r, PCS)
        cond = r.choice(conds_ok + [TURNCOAT, TURNCOAT, AFRAID, AFRAID, POISONED])
        st, extra = monster_case(c, w, r, visible_p=0.06,
                                 combat_p=0.0 if cond == TURNCOAT else 0.3)
        st['conds'][cond] = pick_dur(r) if r.random() < 0.92 else 0
        st['conds'][HEXED] = st['conds'][BLIND] = 0 if r.random() < 0.5 else pick_dur(r)
        finish_monster_world(c, w, r, st, extra, groups_disp=r.choice([0, 1, 2]))
        w.row_targets(c, r, (st['id'], extra[0], 77))
        c.arg(st['id']).arg(cond)
        cap_monster_world(c, w, st, rows=True)
        c.note(cond=cond, running=unsigned(st['conds'][cond]), disp=st['disp'], hp0=st['hp'] == 0,
               in_combat=st['in_combat'], visible=st['visible'])
        w.check(c)


def gen_tick_mon(ctx, w):
    fn = ctx.fn(0x00524110)    # void TickMonsterCondition(int id, W8Condition, UINT minutes)
    for i in range(ctx.n(250)):
        r = ctx.rng('tick_mon', i)
        c = w.case('TickMonsterCondition', i, fn)
        w.base(c, r, isolate=False)
        w.party(c, r, PCS)
        cond = POISONED if r.random() < 0.35 else r.randrange(20)
        st, extra = monster_case(c, w, r, combat_p=0.0 if cond == TURNCOAT else 0.25)
        dur = st['conds'][cond] = pick_dur(r) if r.random() < 0.93 else 0
        minutes = r.choice(MINUTES + [dur - 1, dur, dur + 1, dur // 2]) if dur else r.choice(MINUTES)
        if cond in (HEXED, BLIND) and st['hp'] != 0:     # clearing would run a sight pass
            dur = st['conds'][cond] = max(dur, 2)
            minutes = r.randrange(0, dur)
        finish_monster_world(c, w, r, st, extra, groups_disp=r.choice([0, 1, 2]))
        w.row_targets(c, r, (st['id'], extra[0], 77))
        c.arg(st['id']).arg(cond).arg(minutes)
        cap_monster_world(c, w, st, rows=True)
        c.note(cond=cond, dur=unsigned(dur), minutes=unsigned(minutes), poison=unsigned(st['arg']),
               hp0=st['hp'] == 0)
        w.check(c)


def gen_apply_mon(ctx, w):
    fn = ctx.fn(0x005242b0)    # void ApplyMonsterCondition(int id, W8EnchantmentSlot, int, UINT, UINT)
    for i in range(ctx.n(250)):
        r = ctx.rng('apply_mon', i)
        c = w.case('ApplyMonsterCondition', i, fn)
        w.base(c, r, isolate=False)
        st, extra = monster_case(c, w, r, ench_density=0.4, hp_zero=0.05)
        x = r.random()
        eslot = 2 if x < 0.3 else (6 if x < 0.4 else r.randrange(8))
        e = st['ench'][eslot]
        power = e[0]
        argument = r.choice([power - 1, power, power + 1, 0, 1, 2, 5, 10, 100, 0xffffffff,
                             0x80000000, r.randrange(1, 30)])
        if unsigned(power) <= unsigned(argument):
            if eslot == 6:                   # applied slot 6 runs a sight pass
                e[0] = power = max(unsigned(power), 2)
                argument = r.randrange(0, power) if power < 0x10000 else power - 1
            elif e[3] == 0:                  # first application loads a spell icon
                e[3] = pick_turns(r)
        duration = r.choice([0, 1, 5, 10, 60, 0xffff, 0xffffffff, r.randrange(1, 200)])
        percent = r.choice(PERCENT_ARG)
        finish_monster_world(c, w, r, st, extra)
        c.arg(st['id']).arg(eslot).arg(argument).arg(duration).arg(percent)
        cap_monster_world(c, w, st)
        c.note(eslot=eslot, power=unsigned(power), argument=unsigned(argument),
               prev_turns=unsigned(e[3]))
        w.check(c)


def gen_clear_ench_mon(ctx, w):
    fn = ctx.fn(0x00524390)    # void ClearMonsterEnchantmentSlot(int id, W8EnchantmentSlot)
    for i in range(ctx.n(150)):
        r = ctx.rng('clear_ench_mon', i)
        c = w.case('ClearMonsterEnchantmentSlot', i, fn)
        w.base(c, r, isolate=False)
        st, extra = monster_case(c, w, r, ench_density=0.5)
        eslot = r.choice([0, 1, 2, 3, 4, 5, 7])
        finish_monster_world(c, w, r, st, extra)
        c.arg(st['id']).arg(eslot)
        cap_monster_world(c, w, st)
        c.note(eslot=eslot, turns=unsigned(st['ench'][eslot][3]))
        w.check(c)


def gen_tick_ench_mon(ctx, w):
    fn = ctx.fn(0x00524400)    # void TickMonsterEnchantmentSlot(int id, W8EnchantmentSlot, UINT turns)
    for i in range(ctx.n(200)):
        r = ctx.rng('tick_ench_mon', i)
        c = w.case('TickMonsterEnchantmentSlot', i, fn)
        w.base(c, r, isolate=False)
        st, extra = monster_case(c, w, r, ench_density=0.6)
        eslot = r.randrange(8)
        rem = st['ench'][eslot][3]
        turns = r.choice([0, 1, 2, 5, rem - 1, rem, rem + 1, 0xffffffff, 0x80000000, rem // 2])
        if eslot == 6:                       # clearing slot 6 runs a sight pass
            rem = st['ench'][6][3] = max(unsigned(rem), 2)
            turns = r.randrange(0, min(rem, 0x10000))
        finish_monster_world(c, w, r, st, extra)
        c.arg(st['id']).arg(eslot).arg(turns)
        cap_monster_world(c, w, st)
        c.note(eslot=eslot, remaining=unsigned(rem), turns=unsigned(turns))
        w.check(c)


def gen_copy_char_to_target(ctx, w):
    fn = ctx.fn(0x005241e0)    # void CopyCharacterConditionsToTarget(const W8Character*, const int* id)
    for i in range(ctx.n(200)):
        r = ctx.rng('copy_char_to_target', i)
        c = w.case('CopyCharacterConditionsToTarget', i, fn)
        w.base(c, r, isolate=False)
        slot = r.choice(PCS)
        w.party(c, r, PCS)
        st, extra = monster_case(c, w, r, cond_density=0.1, visible_p=0.0)
        conds = gen_conds(r, r.choice([0.05, 0.15, 0.3, 0.5]))
        arg = r.choice(POISON)
        hp = st['hp'] if st['hp'] is not None else 1
        for k in range(20):                  # keep every forwarded condition on a safe path
            if not conds[k]:
                continue
            poison = arg if k == POISONED else 0
            if safe_set_monster(k, conds[k], poison, st['conds'][k], st['arg'], st['kind'], hp,
                                st['disp']):
                continue
            st['conds'][k] = r.choice([9999, 10000, 0xffffffff]) if k >= DEAD else pick_dur(r)
            if not safe_set_monster(k, conds[k], poison, st['conds'][k], st['arg'], st['kind'], hp,
                                    st['disp']):
                conds[k] = 0
        w.put(c, slot, conds=conds, high=(highest_of(conds), 0, arg))
        finish_monster_world(c, w, r, st, extra)
        target = w.mon_addr(0) + M_LOC
        c.arg(w.ch(slot)).arg(target)
        cap_monster_world(c, w, st)
        c.note(slot=slot, char_conds=[k for k in range(20) if conds[k]], poison=unsigned(arg),
               kind=st['kind'], hp0=st['hp'] == 0)
        w.check(c)


def gen_remove_everyone(ctx, w):
    fn = ctx.fn(0x005244a0)    # void RemoveConditionFromEveryone(W8Condition)
    for i in range(ctx.n(150)):
        r = ctx.rng('remove_everyone', i)
        c = w.case('RemoveConditionFromEveryone', i, fn)
        cond = r.randrange(20)
        occupied = [s for s in PCS if r.random() < 0.85]
        w.base(c, r, level=r.choice(LEVELS), isolate=False)
        w.party(c, r, PCS, occupied)

        def conds_for(s):
            conds = gen_conds(r, 0.1)
            conds[cond] = pick_dur(r) if r.random() < 0.5 else 0
            return conds
        party_states(c, w, r, conds_for, occupied)
        st, extra = monster_case(c, w, r, combat_p=0.0 if cond == TURNCOAT else 0.25)
        st['conds'][cond] = pick_dur(r) if (r.random() < 0.6 and cond not in (HEXED, BLIND)) else 0
        finish_monster_world(c, w, r, st, extra, groups_disp=r.choice([0, 1, 2]), one_record=True)
        if cond in (HEXED, BLIND):           # monster B must not carry it either (sight pass)
            c.set(w.mon_addr(1) + M_COND + 4 * cond, u32(0))
        elif cond != TURNCOAT and r.random() < 0.5:
            c.set(w.mon_addr(1) + M_COND + 4 * cond, u32(pick_dur(r)))
        w.row_targets(c, r, (st['id'], extra[0], 77))
        c.arg(cond)
        w.cap_party(c, PCS)
        w.cap_rows(c)
        w.cap_formation(c)
        w.cap_globals(c)
        w.cap_mon(c, 0)
        w.cap_mon(c, 1)
        w.cap_group(c, 0)
        c.note(cond=cond, occupied=occupied, mon_running=unsigned(st['conds'][cond]))
        w.check(c)


def gen_remove_all_ench(ctx, w):
    fn = ctx.fn(0x00524540)    # void RemoveAllEnchantments(void)
    for i in range(ctx.n(120)):
        r = ctx.rng('remove_all_ench', i)
        c = w.case('RemoveAllEnchantments', i, fn)
        occupied = [s for s in PCS if r.random() < 0.85]
        w.base(c, r, isolate=False)
        w.party(c, r, PCS, occupied)
        density = r.choice([0.1, 0.3, 0.6])
        for s in PCS:
            ench = gen_ench(r, density)
            w.put(c, s, ench=ench, high=(0, ench_top(ench) if r.random() < 0.85 else r.randrange(8), 0))
        st, extra = monster_case(c, w, r, ench_density=density)
        st['ench'][6] = [st['ench'][6][0], 0, 0, 0]       # slot 6 would run a sight pass
        finish_monster_world(c, w, r, st, extra, one_record=True)
        b_ench = gen_ench(r, density)
        b_ench[6] = [0, 0, 0, 0]
        c.set(w.mon_addr(1) + M_ENCH, ench_bytes(b_ench))
        w.cap_party(c, PCS)
        w.cap_globals(c, text=False)
        w.cap_mon(c, 0)
        w.cap_mon(c, 1)
        c.note(occupied=occupied, density=density)
        w.check(c)


def cases(ctx):
    w = W(ctx)
    gen_flag(ctx, w)
    gen_normalize(ctx, w)
    gen_sanitize(ctx, w)
    gen_recompute(ctx, w)
    gen_apply_char(ctx, w)
    gen_tick_char(ctx, w)
    gen_remove_char(ctx, w)
    gen_set_char(ctx, w)
    gen_clear_ench_char(ctx, w)
    gen_tick_ench_char(ctx, w)
    gen_remove_party(ctx, w)
    gen_remove_all_party(ctx, w)
    gen_copy_mon_to_char(ctx, w)
    gen_release(ctx, w)
    gen_bind(ctx, w)
    gen_set_mon(ctx, w)
    gen_clear_mon(ctx, w)
    gen_tick_mon(ctx, w)
    gen_apply_mon(ctx, w)
    gen_clear_ench_mon(ctx, w)
    gen_tick_ench_mon(ctx, w)
    gen_copy_char_to_target(ctx, w)
    gen_remove_everyone(ctx, w)
    gen_remove_all_ench(ctx, w)
