"""NPC Manager.cpp (src/wiz8/local_code/NPC Manager.cpp): NPC state lookups, disposition,
trade / theft scoring, join rules, timers, binding release passes and the NPC character
expansion.

Tested (retail address, function, cases at --scale 1):
  0x0050aa00 NpcRecordHasTradePool          100
  0x0050a280 GetNpcDisposition              400  monster charm/turncoat (scratch monster list),
                                                 faction score, monster_bound, allied rule
                                                 (front rows + bound states), null vector
  0x0050a500 GetNpcDispositionBand          200
  0x0050a520 SetNpcDispositionBand          250  band bytes with high garbage (0x101, -1)
  0x0050ae40 ResumeNpc                      150  bound monster null (see below)
  0x0050c190 NpcHasTopic                    150  holes, topic -1 (matches an empty slot)
  0x0050c140 AddNpcTopic                    150
  0x0050dd50 TellNpcFact                    150  short argument with a garbage high half
  0x0050dd10 NpcKnowsFact                   150  fact values >= 0x8000 / sign-extended
  0x0050b800 GetNpcState                    150  null slots, clamp index, data[-1..-2], null vector
  0x0050b830 GetNpcStateByKind              150  duplicate / odd kinds, count 0 / -1
  0x0050dd80 FindNpcOfKind                  150  spawned 0x100 (low byte 0)
  0x0050ca30 MarkNpcOfKind                  150
  0x0050b8f0 NpcLeadHasNameStyle            200  highest_condition >= 0x80000000 (unsigned)
  0x0050a3c0 GetNpcMonsterInfo              100
  0x0050a400 GetNpcMonster                   80  p3D = scratch address or null
  0x0050b870 GetNpcGroupEntry               100  group 0..8 (known 32 bytes written there)
  0x0050b8b0 GetNpcGroupCharacter           100
  0x0050a9c0 WillNpcTradeForItem            300  item 0x29f, kind 0x14, value/class/qkind
                                                 overrides around 300 and >= 2^31
  0x0050b9b0 CountLeadingPartySlots          60
  0x0050dc50 NpcWantsItem                   300  wanted ids by id and by the 0x83 name kind,
                                                 copies on the group character
  0x0050c9e0 NpcOffersService               200
  0x0050c870 CanNpcJoinParty                400  level band services, Glumph/Sexus/Madras/
                                                 Drazic/Rodan facts, min party level average
  0x0050c770 GetNpcDisplayName              120  RFS-81 substitution (name buffer compared)
  0x0050ada0 FindNpcStateByName             200  case-insensitive, released bindings skipped
  0x0050c7d0 AdvanceNpcTimers               200  0x3c / 0xa8c0 thresholds, clock wrap
  0x005092f0 ChooseNewGameStartLocation     100  import facts, restores stamped on states
  0x00509750 SelectNewGameStartLevel         60
  0x0050aed0 InitializeNpcCharacter         250  the 13 RPC records (+ level / profession /
                                                 race / attribute / skill / spell / item
                                                 variants) expanded into scratch 5
  0x00509ea0 ReleaseNpcBinding              150  -1, negative, == count (clamp), > count
  0x0050a440 FindNpcBindingForMonster       120
  0x0050a4a0 GetNpcStateForMonsterInfo      150  NPC flag, npc_kind 0xfa, allow_unavailable
  0x0050c2e0 ReleaseNpcMonsterBindings      150  pending_release_level vs current_level >= 0x80
  0x0050c440 ReleaseNpcMonsterBinding       150
  0x0050c680 ReleaseNpcMonsterByKind        120
  0x0050c1c0 RestoreNamedNpcAtLevel         150  char level vs current_level, name lengths
                                                 up to 0x2c (overflow into the next fields)
  0x0050c270 ClearPendingNpcLevelFlags      150  pending_restore_level >= 0x80 (retail movsx)
  0x0050cf70 HandleMarkedNpcEvent           200  restricted, see below
  0x0050da00 ReleaseMarkedNpcBindings       150
  0x0050db50 ResetNpcBindingsForParty       150  incl. RebuildConditionsAndDerivedStats
  0x0050ca80 ProcessNpcPendingEvents        200  restricted, see below
  0x0050dec0 QueueNpcDepartureEvents        200  service bands of destination/current level,
                                                 Rodan/Drazic pairing on band 13
  0x0050dbf0 ApplyBoundNpcPenalty           150  own bonus block or scratch block, slot assert
  0x0050a570 ApplyNpcInteraction            400  talk / charm (party Communication, monster
                                                 level, party average), gold and item trade
                                                 pool debit + refill, direct shift, kinds
                                                 with high bits / negative
  0x0050baf0 ScoreNpcTheft                  400  rogue/dex, suspicion, level gap, weight and
                                                 value penalties, difficulty scaling
  0x0050bc90 AttemptNpcPickpocket           300  reseeded roll, candidates, purse
  0x0050c040 AttemptNpcItemTheft            300  count > 255 (retail passes count & 0xff)
  0x0050ba80 ClearNpcScheduledItem          200
  0x0050e4b0 ClearNpcItemId                 150
  total 9010

Skipped:
  0x0050b2d0 CanPlaceNpcNearParty       - camera position/yaw + octree navigator probe (live 3D)
  0x0050ddc0 ReturnDismissedNpcItems    - not in the port map (inlined)
  0x0050b590 DismissNpcFromParty        - roster removal, monster DB file I/O, CreateGroup, notices
  0x0050b3b0 UpdateNpcPartyMember       - notices, roster removal, placement probe, world action
  0x0050b160 RecruitNpcIntoParty        - AddCharacterToParty roster change, RemoveMonster,
                                          script file reload
  0x00509560 SelectStartNpcGreeting     - not in the port map (inlined); dialogue + camera
  0x00509890 InitializeNpcStates        - allocates the global state vector
  0x00509920 ResetNpcStates             - deletes and recreates every state (heap)
  0x005099d0 ReleaseNpcStates           - deletes every state and the vector
  0x00509f00 SaveNpcStates              - save-file chunk I/O
  0x0050aa10 SaveNpcItemLists           - not in the port map; file I/O
  0x00509aa0 CreateNpcRuntimeNode       - heap allocation + insertion into the global vector
  0x00509cd0 BindNpcToMonster           - monster binding + script resource reload (file I/O)
  0x0050b9e0 InitializeNpcItemTable     - not in the port map (inlined into CreateNpcRuntimeNode)
  0x00509fc0 LoadNpcStates              - save-file chunk I/O, recreates states
  0x0050aaf0 LoadNpcItemLists           - not in the port map; file I/O
  0x0050b2f0 ProbeNpcPlacementNearParty - camera + octree navigator queries
  0x0050d480 TriggerBelaVoice           - engine monster object (SetPosition) + dialogue notice
  0x0050d530 UpdateNpcEvents            - GetTickCount timers, monster dying/cycles, dialogue,
                                          endgame screen
  0x0050c560 RestoreNpcMonster          - monster DB file I/O + CreateGroup or p3D->SetPosition;
                                          its safe early returns run inside RestoreNamedNpcAtLevel,
                                          ClearPendingNpcLevelFlags and HandleMarkedNpcEvent
  0x0050abf0 NotifyNpcTriggerActivation - queues a dialogue script notice
  0x0050ac60 RebindNpcLevelTriggers     - trigger lookup + script resource reload (file I/O)
  0x0050e230 QueueNpcTravelRefusals     - every refusal runs BeginScriptedWorldAction
                                          (SetTargetCursor: cursor state cannot be rolled back);
                                          the no-refusal path only clears one level flag

How the state is controlled:
  * g_npc_states -> W8GrowableVector in scratch 0 (+4 count, +8 capacity, +0xc data ->
    S0+0x40; data[-1], data[-2] below it for negative indexes). NPC states (0x13d bytes)
    at S0+0x400+k*0x140, written field by field; the record pointer is set with setp to
    a real NPC.DBS record (g_npc_records + id*0x309, kind == id in the shipped table) or
    to a copy / variant in scratch 1. NPC.DBS and Items.dbs are read from
    games\\reference (DATA.SLF / PATCH.001) for realistic records and item ids.
  * Monsters: gXStatus.plsMonsterList -> W8PList in scratch 2 (infos S2+0x100+k*0x430,
    fake p3D S2+0x8000), plsUnbornMonsterList = null, monster_record_cache[990+k] ->
    W8MonsterRecord in scratch 3. A location missing from the list (or both lists null)
    gives the lookup asserts 0x5c1/0x5da/0x5de and a null monster: release passes never
    remove a monster, and the assert lines show whether RestoreNpcMonster /
    ReleaseNpcCompanionMonster looked the monster up (signed level compares).
  * QueueCharacterEvent is muted with g_status.greeting_pending = 1 (QueueEntry deletes the
    event); message lines go to a scratch vector (S7, count compared); g_level_data ->
    scratch 6 (flags compared).
  * PracticeCharacterSkill without a message box (as the character_skills spec): screen 8,
    modes clear, no item pick; skill notices / deferred flag / party characters compared.
  * Derived-stat rebuilds: combat off, game_started 0 (no party re-encumbrance), screen 8,
    uiCondition[0x13] cleared (it reaches the bound monster).
  * GetFact: g_fact_values entries set, log_fact_checks = 0. GetLevelBand: current_level and
    facts 0x5b/0x1ce (levels 16/38) set. Faction scores in g_factions set.
  * Restore targets always have has_monster set (RestoreNpcMonster never reaches the monster
    database); restores in the release passes are stamped (level != current).
  * Every case is checked against the core's 96-operation limit.

Restricted paths (not reachable safely, so never fed):
  * ResumeNpc with a found monster (SetMonsterGroupHostilityByID on live groups).
  * HandleMarkedNpcEvent: name styles 0x18 (SetFact -> journal), 0x29 on level 13 (location
    vars, triggers, teleport), 0x2b with fact 0x8b clear (spawns a world item); a found
    monster only with mode 0 and no restore on the current level.
  * ProcessNpcPendingEvents: the Al-Sedexus infatuation path (SetCharacterCondition +
    SetFact) - infatuation only with the flagged kind-0x42 NPC or on bands 9/10 - and the
    Rodan/Drazic scripted world action (unpaired Rodan/Drazic only on band 13).
  * Theft / charm cases always have the NPC's monster (GetMonsterDataForInfo(null) crashes).

Labelled edges: note(edge='level47') - current/destination level 47: retail reads its
test-level slot (band 0), the port's g_level_folders has 47 entries, so GetLevelBand reads
past the array; note(edge='count_over_byte') - AttemptNpcItemTheft count outside 0..255.
"""
import os
import struct

# ----------------------------------------------------------------------------- layouts
CHAR = 0x1862
XROW = 0x106                 # W8PartySlotRow (g_status.buffers.XChar)
# W8Character (scripts/w8diff/layout.ps1, wiz8/layouts/character.h)
C_INPARTY = 0x04
C_PROF = 0x69
C_RACE = 0x71
C_GENDER = 0x75
C_LEVEL = 0x89               # uiExpLevel
C_ATTR = 0xe5                # W8CharacterAttribute[7], stride 0x14, effective +4
ATTR_STEP = 0x14
C_SKILL = 0x19d              # W8CharacterSkill[0x29], stride 0x26, level +6
SKILL_STEP = 0x26
C_EXP = 0x9ed
C_COND = 0xa01               # uiCondition[20]
C_HCOND = 0xb01
C_HP = 0xb11
C_EQUIP = 0xf5d              # W8ItemInstance[12]
C_PACK = 0x1029              # W8ItemInstance[8]
C_BONUS = 0x1770             # W8GameplayModifierBlock bonus (0x67 bytes)
CHAR_FLOATS = [0xb69, 0xb6d, 0xb71, 0xb75] + [0xb79 + 4 * k for k in range(12)]
SK_COMM = 0x16
SK_PICK = 0x0d
A_DEX = 4
COND_TURNCOAT_OFF = C_COND + 13 * 4      # read by ScaleValueForCharacterDifficulty
COND_MISSING_OFF = C_COND + 19 * 4       # condition 0x13 reaches the bound monster in rebuilds
MODBLOCK = 0x67
# W8PartySlotRow
X_OCC = 0x00
X_NPC = 0xfa                 # int npc_index
X_BOUND = 0xfe               # bool npc_bound
# W8GlobalStatus (wiz8/layouts/game_status.h)
GS_STARTED = 0x0c
GS_GOLD = 0x19
GS_CLOCK = 0x18d8            # world_clock
GS_LEVEL = 0x1900            # current_level
GS_SUSPENDED = 0x2390
GS_BIND_CLOCK = 0x242a
GS_BIND_PENDING = 0x242e
GS_RESTORE_PENDING = 0x2430
GS_INFATUATION = 0x2446
GS_GREETING = 0x2497         # greeting_pending: QueueEntry deletes every queued event
GS_LOG_FACTS = 0x3120        # log_fact_checks (GetFact/SetFact debug notices)
# W8XStatus (wiz8/xstatus.h)
GX_ENTRY = 0x118
GX_NOTICE = 0xea             # monster_manager_entries[k].skill_notice_pending[0x29]
GX_MODES = 0x8dc             # fCombatMode .. (13 bytes)
GX_SURPRISE = 0x90d
GX_MLIST = 0x8f5             # plsMonsterList
GX_UNBORN = 0x901            # plsUnbornMonsterList
GX_CACHE = 0xa0f             # monster_record_cache[1000]
GX_DEFERRED = 0x19b5
GX_PICK = 0x19b6
# g_settings
SET_DIFFICULTY = 0x0d
# g_npc_scripting.message_lines (vptr, count, capacity, data)
MSG_COUNT = 0x90
MSG_DATA = 0x98
SCREEN_NEUTRAL = 8           # automap: neither camp, main game nor character screen
# W8MonsterInfo / W8MonsterRecord
MI_SIZE = 0x2f5              # bytes written per info (up to bound_npc_index)
MI_LOC, MI_SPECIES, MI_P3D = 0x00, 0x08, 0x0c
MI_TURNCOAT = 0x57 + 13 * 4
MI_HIGHEST = 0x107
MI_CHARM = 0x2de
MI_BOUND = 0x2f1
MR_NPC_KIND, MR_FLAGS, MR_LEVEL = 0xcd, 0xd0, 0x24f
SPECIES0 = 990               # fake species ids, cache slots 990..997
# W8NpcState (wiz8/layouts/npc_state.h, 0x13d bytes)
STATE_SIZE = 0x13d
ST = {
    'script_file': (0x00, '<I'), 'spawned': (0x04, '<H'), 'location_id': (0x16, '<I'),
    'has_monster': (0x1a, 'B'), 'disposition': (0x1b, 'B'), 'dismissed_flag': (0x1c, 'B'),
    'greeting_pending': (0x1d, 'B'), 'dismissed_timer': (0x1e, '<I'), 'level_band': (0x24, 'B'),
    'is_present': (0x25, 'B'), 'is_grouped': (0x26, 'B'), 'group_index': (0x2b, 'B'),
    'partner_index': (0x2c, 'B'), 'name_style': (0x2e, 'B'), 'bound_level': (0x2f, 'B'),
    'gold': (0x80, '<I'), 'suspicion': (0x84, 'B'), 'pending_restore': (0xc5, 'B'),
    'pending_restore_level': (0xc6, 'B'), 'binding_unavailable': (0xc7, 'B'),
    'talk_cd': (0xc8, 'B'), 'trade_cd': (0xc9, 'B'), 'trade_pool': (0xca, '<H'),
    'talk_clock': (0xcc, '<I'), 'trade_clock': (0xd0, '<I'), 'incapacitated': (0xe8, 'B'),
    'event_pending': (0xe9, 'B'), 'restored': (0xea, 'B'), 'event_clock': (0xeb, '<I'),
    'pending_release': (0x112, 'B'), 'pending_release_level': (0x113, 'B'),
    'restore_done': (0x114, 'B'),
}
ST_ITEM_IDS = 0x30           # short[40]
ST_TOPICS = 0x89             # int[5]
ST_RESTORE_NAME = 0x9d       # char[0x28]
ST_SERVICE = 0xd4            # unsigned char[0x14]
ST_FACTS = 0xf2              # short[14]
# W8NpcDatabaseRecord (0x309)
REC_SIZE = 0x309
REC_STRIDE = 0x310
RF = {
    'trade_pool': (0x02, '<H'), 'monster_bound': (0x54, 'B'), 'owns_stock': (0x55, 'B'),
    'merchant': (0x56, 'B'), 'has_group': (0x57, 'B'), 'kind': (0x58, '<I'),
    'disposition': (0x5c, 'B'), 'charm_scale': (0x5d, 'B'), 'talk_scale': (0x5e, 'B'),
    'faction': (0x5f, 'B'), 'service_flags': (0x68, '<I'), 'allied_faction': (0x6e, 'B'),
    'min_party_level': (0x6f, 'B'), 'restore_level': (0x70, 'B'),
}
R_RESTORE_NAME = 0x74        # char[0x29]
R_DISPLAY_NAME = 0x9e        # char[0x26]
R_STOCK_RULES = 0x2ca        # W8PList* (heap pointer in the loaded table)
TPL = 0xc4                   # W8NpcCharacterTemplate
T_PROF, T_RACE, T_TABLE, T_LEVEL = 0x64, 0x68, 0x6c, 0x70
T_ATTR, T_SKILLS, T_SPELLS = 0x74, 0x90, 0x134
T_EQ_PRESENT, T_EQ_IDS, T_BP_PRESENT, T_BP_IDS = 0x1a6, 0x1be, 0x1d6, 0x1e6
T_GENDER, T_WANTED = 0x1f6, 0x1f7
# W8ItemDatabaseRecord (0x10d)
IREC = 0x10d
I_CLASS, I_UNI, I_QKIND, I_VALUE, I_WEIGHT = 0x3e, 0x3f, 0x66, 0x86, 0x8a
# scratch layout
S_VEC_DATA = 0x40            # S0: vector data array (negative indexes below it)
S_STATE0 = 0x400             # S0: NPC states
STATE_STRIDE = 0x140
# retail 0x00619DF8 g_npc_services: (npc_id, service_id, bit)
SERVICES = [(0x46, 2, 0x1), (0x47, 3, 0x2), (0x50, 4, 0x400), (0x48, 5, 0x4), (0x49, 7, 0x8),
            (0x4d, 8, 0x80), (0x4c, 9, 0x40), (0x4b, 10, 0x20), (0x4a, 11, 0x10), (0x4e, 12, 0x100),
            (0x51, 13, 0x800), (0x4f, 14, 0x200), (0x4d, 15, 0x1000), (0x52, 6, 0x2000)]
SERVICE_BIT = {}
for _row in SERVICES:
    SERVICE_BIT.setdefault(_row[1], _row[2])
SERVICE_BITS = [b for _, _, b in SERVICES]
# level -> level band (retail table 0x006044E2, stride 0x6b; 47 = test slot, 0 in retail)
BANDS = [2, 12, 8, 8, 14, 5, 5, 6, 1, 1, 15, 11, 11, 11, 11, 11, 13, 9, 9, 9, 9, 10, 7, 7, 4, 3, 3,
         16, 0, 17, 0, 0, 0, 0, 0, 0, 2, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
LEVELS_BY_BAND = {}
for _lv, _b in enumerate(BANDS[:47]):
    if _lv not in (0x10, 0x26):
        LEVELS_BY_BAND.setdefault(_b, []).append(_lv)
SERVICE_BANDS = sorted(b for b in SERVICE_BIT if b in LEVELS_BY_BAND)

NPC_DRAZIC, NPC_RODAN, NPC_RFS81A, NPC_GLUMPH, NPC_MADRAS, NPC_SEXUS, NPC_MYLES = (
    0x10, 0x11, 0x20, 0x2b, 0x4a, 0x4f, 0x07)
F_RFS81_FIXED, F_IMPORT_TRANG, F_IMPORT_UMPANI, F_VIRGIN = 0x44, 0x4b, 0x4c, 0x4e
F_SCUBA, F_PEACE, F_MADRAS, F_SEXUS, F_MYLES_JAIL = 0x8b, 0xbf, 0x1a7, 0x20d, 0x1f
F_LEVEL16A, F_LEVEL16B = 0x5b, 0x1ce

DISP_EDGES = [0, 1, 0x20, 0x21, 0x22, 0x31, 0x32, 0x41, 0x42, 0x43, 0x63, 0x64, 0x7f, 0x80, 0x81,
              0xc0, 0xfe, 0xff]
SCORE_EDGES = [0, 0x21, 0x22, 0x32, 0x42, 0x43, 0x64, 0x7f, 0x80, 0xff]
CHARM_EDGES = [0, 1, -1, 10, -10, 0x40, 0x7f, -0x80]
BOOL_EDGES = [2, 0x80, 0xff]


# ----------------------------------------------------------------------------- data files
def _slf_read(path, suffix):
    """One file out of a Sir-Tech .SLF library (format as scripts/tools/slf_extract.py)."""
    with open(path, 'rb') as f:
        head = f.read(532)
        entries = struct.unpack_from('<i', head, 512)[0]
        f.seek(0, 2)
        size = f.tell()
        f.seek(size - entries * 280)
        table = f.read(entries * 280)
        for i in range(entries):
            row = table[i * 280:(i + 1) * 280]
            name = row[:256].split(b'\0')[0].decode('latin1').lower()
            off, length, state = struct.unpack_from('<IIB', row, 256)
            if state == 0 and name.endswith(suffix):
                f.seek(off)
                return f.read(length)
    return None


def _find_db(suffix):
    root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
    for game in ('reference', 'work'):
        for rel in (('Patches', 'PATCH.001'), ('Data', 'DATA.SLF')):
            path = os.path.join(root, 'games', game, *rel)
            if os.path.exists(path):
                data = _slf_read(path, suffix)
                if data:
                    return data
    raise RuntimeError('%s not found under games\\reference or games\\work' % suffix)


def _load_items():
    data = _find_db('databases\\items.dbs')
    count = struct.unpack_from('<I', data, 0)[0]
    out = []
    for i in range(count):
        b = data[4 + i * IREC:4 + (i + 1) * IREC]
        out.append({'id': i, 'cls': b[I_CLASS], 'uni': struct.unpack_from('<H', b, I_UNI)[0],
                    'qk': b[I_QKIND], 'value': struct.unpack_from('<I', b, I_VALUE)[0],
                    'weight': struct.unpack_from('<H', b, I_WEIGHT)[0]})
    return out


def _load_npcs():
    """NPC.DBS records (InitializeNpcDatabase: a record, then its stock-rule tail when
    version > 1 and no_item_stock is clear)."""
    data = _find_db('databases\\npc.dbs')
    count = struct.unpack_from('<I', data, 0)[0]
    pos = 4
    out = []
    for _ in range(count):
        b = bytearray(data[pos:pos + REC_SIZE])
        pos += REC_SIZE
        if b[0x9d] == 0 and struct.unpack_from('<H', b, 0)[0] > 1:
            n = struct.unpack_from('<I', data, pos)[0]
            pos += 4 + 6 * n
        struct.pack_into('<I', b, R_STOCK_RULES, 0)
        out.append(bytes(b))
    return out


# ----------------------------------------------------------------------------- helpers
def p8(v):
    return bytes([int(v) & 0xff])


def p16(v):
    return struct.pack('<H', int(v) & 0xffff)


def p32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def _pack(buf, off, fmt, v):
    mask = {'B': 0xff, '<H': 0xffff, '<I': 0xffffffff}[fmt]
    struct.pack_into(fmt, buf, off, int(v) & mask)


def emit(c, addr, data, gap=0x40):
    """Write only the non-zero runs of data (scratch is zeroed for every case), merging
    runs closer than gap bytes."""
    n = len(data)
    i = 0
    while i < n:
        if data[i] == 0:
            i += 1
            continue
        a = last = i
        j = i + 1
        while j < n and j - last <= gap:
            if data[j]:
                last = j
            j += 1
        c.set(addr + a, bytes(data[a:last + 1]))
        i = last + 1


def bbyte(r, p_true, edge=0.05):
    """bool byte: mostly 0/1, rarely a non-canonical true value."""
    if r.random() < p_true:
        return r.choice(BOOL_EDGES) if r.random() < edge else 1
    return 0


def hpv(r, zero_p=0.15):
    x = r.random()
    if x < zero_p:
        return 0
    if x < zero_p + 0.06:
        return r.choice([1, 0x7fffffff, 0x80000000, 0xffffffff])
    return r.randrange(1, 400)


def condv(r, edge=0.04):
    """highest_condition; retail compares it unsigned."""
    x = r.random()
    if x < edge:
        return r.choice([0x80000000, 0xffffffff, 0x7fffffff])
    if x < 0.55:
        return 0
    if x < 0.8:
        return r.randrange(1, 0x15)
    return r.choice([0xc, 0xd, 0xe, 0xf, 0x10, 0x11, 0x12, 0x13, 0x14])


def pick_level(r):
    x = r.random()
    if x < 0.86:
        return r.randrange(0, 47)
    if x < 0.89:
        return 47                      # retail table slot 47 (port array has 47 entries)
    return r.choice([-1, 48, 60, 100, 0x7fffffff, -0x80000000, 0x10, 0x26])


def band_of(level, f5b, f1ce):
    lv = level
    if lv in (0x10, 0x26):
        lv = 0x10 if (f5b or f1ce) else 0x26
    if 0 <= lv <= 0x2f:
        return BANDS[lv]
    return 0


def level_for_band(r, band):
    return r.choice(LEVELS_BY_BAND[band])


class St:
    """One W8NpcState image; rec is the Addr its record pointer is wired to (or None)."""

    def __init__(self, rec=None, **kw):
        self.b = bytearray(STATE_SIZE)
        self.rec = rec
        for k, v in kw.items():
            self[k] = v

    def __setitem__(self, k, v):
        off, fmt = ST[k]
        _pack(self.b, off, fmt, v)

    def __getitem__(self, k):
        off, fmt = ST[k]
        return struct.unpack_from(fmt, self.b, off)[0]

    def item_ids(self, ids):
        for k, v in enumerate(ids):
            struct.pack_into('<h', self.b, ST_ITEM_IDS + 2 * k, v)

    def topics(self, vals):
        for k, v in enumerate(vals):
            struct.pack_into('<I', self.b, ST_TOPICS + 4 * k, v & 0xffffffff)

    def facts(self, vals):
        for k, v in enumerate(vals):
            struct.pack_into('<H', self.b, ST_FACTS + 2 * k, v & 0xffff)


def recdata(E, rid=None, **kw):
    """A record image: a copy of NPC.DBS record rid (or zeros) with fields overridden."""
    b = bytearray(E.NPCS[rid]) if rid is not None else bytearray(REC_SIZE)
    for k, v in kw.items():
        off, fmt = RF[k]
        _pack(b, off, fmt, v)
    return b


def put_cstr(b, off, text, limit):
    raw = text.encode('latin1')[:limit - 1]
    b[off:off + limit] = raw + bytes(limit - len(raw))


class Env:
    def __init__(self, ctx):
        self.ctx = ctx
        self.gs = ctx.g('g_status')
        self.gx = ctx.g('gXStatus')
        self.vec_ptr = ctx.g('g_npc_states')
        self.recs = ctx.g('g_npc_records').deref()
        self.items = ctx.g('g_item_records').deref()
        self.factions = ctx.g('g_factions')
        self.facts = ctx.g('g_fact_values')
        self.settings = ctx.g('g_settings')
        self.screen = ctx.g('g_current_screen_state')
        self.scripting = ctx.g('g_npc_scripting')
        self.combat = ctx.g('g_combat_state')
        self.name_buf = ctx.g('g_npc_name_buffer')
        self.level_data = ctx.g('g_level_data')
        self.xbase = (self.gs + 8).deref()
        self.S = [ctx.scratch(k) for k in range(8)]
        self.ITEMS = _load_items()
        self.NPCS = _load_npcs()
        self.nitems = len(self.ITEMS)
        self.nrec = len(self.NPCS)
        self.group_rids = [i for i, b in enumerate(self.NPCS) if b[0x57]]
        self.uni83 = [it['id'] for it in self.ITEMS if it['uni'] == 0x83]
        self.ammo = [it['id'] for it in self.ITEMS if it['cls'] == 4]
        self.stackable = [it['id'] for it in self.ITEMS if it['qk'] == 1]
        self.names = [bytes(b[R_DISPLAY_NAME:R_DISPLAY_NAME + 0x26]).split(b'\0')[0].decode('latin1')
                      for b in self.NPCS]

    def xrow(self, s):
        return self.xbase + s * XROW

    def char(self, s):
        return self.ctx.char(s)

    def irec(self, iid, off=0):
        return self.items + (iid * IREC + off)

    def real(self, rid):
        return self.recs + rid * REC_SIZE

    def item(self, r):
        return r.randrange(self.nitems)

    # ----- global state shared by many functions
    def facts_set(self, c, facts):
        for fid, v in facts.items():
            c.set(self.facts + fid, p8(v))

    def nolog(self, c):
        c.set(self.gs + GS_LOG_FACTS, b'\0')

    def level(self, c, r, level=None, f5b=None, f1ce=None):
        """current_level plus the two facts GetLevelBand reads for levels 16/38."""
        if level is None:
            level = pick_level(r)
        f5b = r.choice([0, 0, 1]) if f5b is None else f5b
        f1ce = r.choice([0, 0, 1]) if f1ce is None else f1ce
        c.set(self.gs + GS_LEVEL, p32(level))
        c.set(self.facts + F_LEVEL16A, p8(f5b))
        c.set(self.facts + F_LEVEL16B, p8(f1ce))
        return level, band_of(level, f5b, f1ce), f5b, f1ce

    def mute_events(self, c):
        c.set(self.gs + GS_GREETING, b'\x01')

    def practice_env(self, c):
        """PracticeCharacterSkill without a message box (character_skills spec): screen 8,
        modes clear, no item pick, deferred flag captured."""
        c.set(self.screen, p32(SCREEN_NEUTRAL))
        c.set(self.gx + GX_MODES, bytes(13))
        c.set(self.gx + GX_PICK, b'\0')
        c.set(self.gs + GS_STARTED, b'\x01')
        c.set(self.gs + GS_SUSPENDED, b'\0')
        c.set(self.combat, p32(0))
        c.set(self.gx + GX_DEFERRED, b'\0')
        self.mute_events(c)

    def practice_caps(self, c):
        c.cap(self.gx + GX_NOTICE, 7 * GX_ENTRY + 0x29, 'skill_notices')
        c.cap(self.gx + GX_DEFERRED, 1, 'deferred')

    def rebuild_env(self, c, slots):
        """RebuildConditionsAndDerivedStats / RecalculateCharacterDerivedStats: no combat,
        no party re-encumbrance (game_started 0), screen 8 (no portrait redraw),
        condition 0x13 cleared (it would reach the bound monster), events muted."""
        c.set(self.screen, p32(SCREEN_NEUTRAL))
        c.set(self.gx + GX_MODES, bytes(13))
        c.set(self.gs + GS_STARTED, b'\0')
        c.set(self.combat, p32(0))
        self.mute_events(c)
        for s in slots:
            c.set(self.char(s) + COND_MISSING_OFF, p32(0))

    def redirect_messages(self, c, capacity=32):
        c.set(self.scripting + MSG_COUNT, struct.pack('<ii', 0, capacity))
        c.setp(self.scripting + MSG_DATA, self.S[7])
        return self.scripting + MSG_COUNT

    def no_monsters(self, c):
        """Both monster lists null: any lookup asserts (0x5c1, 0x5da, 0x5de) and yields null."""
        c.set(self.gx + GX_MLIST, p32(0))
        c.set(self.gx + GX_UNBORN, p32(0))


class Mon:
    def __init__(self, loc, charm=0, turncoat=0, highest=0, bound=0, p3d=False, rec=None):
        self.loc, self.charm, self.turncoat, self.highest = loc, charm, turncoat, highest
        self.bound, self.p3d, self.rec = bound, p3d, rec   # rec: (flags, npc_kind, level)


def put_monsters(c, E, mons):
    lst = E.S[2]
    n = len(mons)
    c.set(lst + 4, struct.pack('<ii', n, n))
    c.setp(lst, lst + 0x10)
    for k, m in enumerate(mons):
        info = E.S[2] + 0x100 + k * 0x430
        c.setp(lst + 0x10 + 4 * k, info)
        b = bytearray(MI_SIZE)
        struct.pack_into('<I', b, MI_LOC, m.loc & 0xffffffff)
        struct.pack_into('<I', b, MI_SPECIES, SPECIES0 + k)
        struct.pack_into('<I', b, MI_TURNCOAT, m.turncoat & 0xffffffff)
        struct.pack_into('<I', b, MI_HIGHEST, m.highest & 0xffffffff)
        b[MI_CHARM] = m.charm & 0xff
        struct.pack_into('<I', b, MI_BOUND, m.bound & 0xffffffff)
        emit(c, info, b, gap=0x80)
        if m.p3d:
            c.setp(info + MI_P3D, E.S[2] + 0x8000 + k * 0x40)
        if m.rec is not None:
            flags, kind, level = m.rec
            rb = bytearray(0x297)
            rb[MR_FLAGS] = flags & 0xff
            rb[MR_NPC_KIND] = kind & 0xff
            rb[MR_LEVEL] = level & 0xff
            raddr = E.S[3] + k * 0x2a0
            emit(c, raddr, rb, gap=0x200)
            c.setp(E.gx + GX_CACHE + (SPECIES0 + k) * 4, raddr)
    c.setp(E.gx + GX_MLIST, lst)
    c.set(E.gx + GX_UNBORN, p32(0))


def mon_locs(r, n):
    return [0x10000 + 0x101 * x for x in r.sample(range(1, 1 << 20), n + 1)]


class World:
    """NPC states / records / vector of one case in scratch 0 and 1."""

    def __init__(self, ctx, E, c):
        self.ctx, self.E, self.c = ctx, E, c
        self.nstate = 0
        self.nrec = 0

    def rec(self, data, gap=0x100):
        addr = self.E.S[1] + self.nrec * REC_STRIDE
        self.nrec += 1
        emit(self.c, addr, data, gap)
        return addr

    def real(self, rid):
        return self.E.real(rid)

    def put(self, st):
        addr = self.E.S[0] + S_STATE0 + self.nstate * STATE_STRIDE
        self.nstate += 1
        emit(self.c, addr, st.b)
        if st.rec is not None:
            self.c.setp(addr + 6, st.rec)
        return addr

    def vector(self, addrs, count=None, capacity=None, neg=None):
        s0 = self.E.S[0]
        n = len(addrs) if count is None else count
        cap = max(len(addrs), n if n > 0 else 0) + 2 if capacity is None else capacity
        self.c.set(s0 + 4, struct.pack('<ii', n, cap))
        self.c.setp(s0 + 0xc, s0 + S_VEC_DATA)
        for i, a in enumerate(addrs):
            if a is not None:
                self.c.setp(s0 + S_VEC_DATA + 4 * i, a)
        for k, a in (neg or {}).items():
            if a is not None:
                self.c.setp(s0 + S_VEC_DATA - 4 * k, a)
        self.c.setp(self.E.vec_ptr, s0)

    def cap_states(self, n=None, name='states'):
        n = self.nstate if n is None else n
        if n:
            self.c.cap(self.E.S[0] + S_STATE0, (n - 1) * STATE_STRIDE + STATE_SIZE, name,
                       ignore=[k * STATE_STRIDE + 6 for k in range(n)])


# ----------------------------------------------------------------------------- disposition world
def disp_world(ctx, E, c, r, W, monster='maybe', notfound_p=0.08, faction_p=0.5, allied=True,
               st=None, mon_rec=None, max_monsters=3, scales=None):
    """NPC state whose GetNpcDisposition inputs are all set: state byte, bound monster
    (scratch list) with charm/turncoat, record faction / monster_bound / allied faction,
    the faction score and - for the allied rule - the two front party rows and the bound
    states they name. Returns (state, info)."""
    st = st if st is not None else St()
    d = r.choice(DISP_EDGES) if r.random() < 0.3 else r.randrange(0, 101)
    st['disposition'] = d
    info = {'disp': d}
    want = monster == 'always' or (monster == 'maybe' and r.random() < 0.45)
    if want:
        st['has_monster'] = bbyte(r, 1.0, 0.03)
        st['is_present'] = bbyte(r, 1.0, 0.03)
        n = min(max_monsters, r.choice([1, 1, 1, 2, 3]))
        locs = mon_locs(r, n)
        j = r.randrange(n)
        mons = []
        for k in range(n):
            charm = r.choice(CHARM_EDGES) if r.random() < 0.3 else r.randrange(-15, 16)
            turn = r.choice([0, 0, 0, 0, 1, 7, 0x80000000, 0xffffffff])
            rec = mon_rec(r) if mon_rec else None
            mons.append(Mon(locs[k], charm=charm, turncoat=turn, rec=rec,
                            highest=r.choice([0, 0, 3, 0xe, 0xf, 0x12])))
        put_monsters(c, E, mons)
        if monster != 'always' and r.random() < notfound_p:
            st['location_id'] = locs[n]
            info['monster'] = 'notfound'
        else:
            st['location_id'] = locs[j]
            info['monster'] = 'charm=%d,turncoat=%x' % (mons[j].charm, mons[j].turncoat)
            info['mon_level'] = mons[j].rec[2] if mons[j].rec else None
    else:
        hm, ip = r.choice([(0, 0), (1, 0), (0, 1), (0, 0)])
        st['has_monster'] = hm
        st['is_present'] = ip
        st['location_id'] = r.getrandbits(32)
    fac = r.randrange(1, 21) if r.random() < faction_p else 0
    mb = r.choice([0] * 6 + [1, 2, 0x80, 0xff])
    ally = 0
    if fac and allied and r.random() < 0.75:
        ally = r.choice([-1, 0x7f, -0x80] + list(range(1, 21)))
    rid = r.randrange(E.nrec) if r.random() < 0.5 else None
    extra = {}
    if scales is not None:
        extra = {'charm_scale': scales[0], 'talk_scale': scales[1]}
    st.rec = W.rec(recdata(E, rid, faction=fac, monster_bound=mb, allied_faction=ally, **extra))
    info.update(faction=fac, monster_bound=mb, ally=ally, record=rid)
    if fac:
        score = r.choice(SCORE_EDGES) if r.random() < 0.4 else r.randrange(0, 101)
        c.set(E.factions + fac * 14, p8(score))
        info['score'] = score
        if allied:
            B = r.randrange(1, 5)
            addrs = []
            for k in range(B):
                bf = r.choice([ally & 0xff, ally & 0xff, ally & 0xff, r.randrange(0, 21), 0xff, 0x80, 0])
                bst = St(W.rec(recdata(E, None, faction=bf)))
                bst['binding_unavailable'] = r.choice([0, 0, 0, 0, 1, 0x80])
                addrs.append(W.put(bst))
            if r.random() < 0.04:
                c.set(E.vec_ptr, p32(0))
                info['vector'] = 'null'
            else:
                W.vector(addrs, neg={1: addrs[0] if r.random() < 0.5 else None})
            rows = []
            for s in (0, 1):
                occ = bbyte(r, 0.75, 0.06)
                idx = r.choice(list(range(B)) * 3 + [B, B + 3, -1, -2, 0x7fffffff, -0x80000000])
                hp = hpv(r)
                c.set(E.xrow(s) + X_OCC, p8(occ))
                c.set(E.xrow(s) + X_NPC, p32(idx))
                c.set(E.char(s) + C_HP, p32(hp))
                rows.append('%x/%d/%x' % (occ, idx, hp))
            info['rows'] = ' '.join(rows)
    return st, info


# ----------------------------------------------------------------------------- small state functions
def t_trade_pool(ctx, E):
    fn = ctx.fn(0x0050aa00)  # bool NpcRecordHasTradePool(W8NpcState*)
    for i in range(ctx.n(100)):
        r = ctx.rng('tradepool', i)
        c = ctx.case('tradepool.%d' % i, fn, conv='c', ret='b')
        W = World(ctx, E, c)
        if r.random() < 0.4:
            rid = r.randrange(E.nrec)
            rec = W.real(rid)
            c.note(record=rid)
        else:
            tp = r.choice([0, 0, 1, 0xffff, 0x8000, 0x7fff, 0x100, 0xff00, 0xff, r.randrange(0x10000)])
            rec = W.rec(recdata(E, None, trade_pool=tp, kind=r.randrange(146)))
            c.note(trade_pool=tp)
        c.arg(W.put(St(rec, name_style=r.randrange(146))))


def t_disposition(ctx, E):
    fn = ctx.fn(0x0050a280)  # char GetNpcDisposition(W8NpcState*)
    for i in range(ctx.n(400)):
        r = ctx.rng('disposition', i)
        c = ctx.case('disposition.%d' % i, fn, conv='c', ret='i8')
        W = World(ctx, E, c)
        st, info = disp_world(ctx, E, c, r, W)
        c.arg(W.put(st))
        c.note(**info)


def t_disposition_band(ctx, E):
    fn = ctx.fn(0x0050a500)  # unsigned char GetNpcDispositionBand(W8NpcState*)
    for i in range(ctx.n(200)):
        r = ctx.rng('dispband', i)
        c = ctx.case('dispband.%d' % i, fn, conv='c', ret='u8')
        W = World(ctx, E, c)
        st, info = disp_world(ctx, E, c, r, W)
        c.arg(W.put(st))
        c.note(**info)


def t_set_band(ctx, E):
    fn = ctx.fn(0x0050a520)  # void SetNpcDispositionBand(W8NpcState*, char band)
    for i in range(ctx.n(250)):
        r = ctx.rng('setband', i)
        c = ctx.case('setband.%d' % i, fn, conv='c', ret='v')
        W = World(ctx, E, c)
        st, info = disp_world(ctx, E, c, r, W)
        a = W.put(st)
        band = r.choice([0, 1, 2, 0, 1, 2, 3, 0xff, 0x80, 0x100, 0x101, 0x102, -1, 0x7fffff01])
        c.arg(a)
        c.arg(band)
        W.cap_states()
        c.note(band=band, **info)


def t_resume(ctx, E):
    fn = ctx.fn(0x0050ae40)  # void ResumeNpc(W8NpcState*, int enabled); bound monster kept null
    for i in range(ctx.n(150)):
        r = ctx.rng('resume', i)
        c = ctx.case('resume.%d' % i, fn, conv='c', ret='v')
        W = World(ctx, E, c)
        # a found monster would reach SetMonsterGroupHostilityByID (world groups)
        st, info = disp_world(ctx, E, c, r, W, monster='never' if r.random() < 0.85 else 'maybe',
                              notfound_p=1.0)
        a = W.put(st)
        en = r.choice([0, 1, 1, 0x100, 0xff, 0x80000000, 2])
        c.arg(a)
        c.arg(en)
        W.cap_states()
        c.note(enabled=en, **info)


def t_topics(ctx, E):
    has = ctx.fn(0x0050c190)   # bool NpcHasTopic(W8NpcState*, int)
    add = ctx.fn(0x0050c140)   # void AddNpcTopic(W8NpcState*, int)
    for kind, fn, count in (('hastopic', has, 150), ('addtopic', add, 150)):
        for i in range(ctx.n(count)):
            r = ctx.rng(kind, i)
            c = ctx.case('%s.%d' % (kind, i), fn, conv='c', ret='b' if kind == 'hastopic' else 'v')
            W = World(ctx, E, c)
            st = St()
            nfill = r.choice([0, 1, 2, 3, 4, 5, 5, 5])
            vals = []
            for k in range(5):
                if k < nfill:
                    vals.append(r.choice([r.randrange(1, 300), 1, 0x80000000, 0xffffffff, 0x7fffffff]))
                else:
                    vals.append(0)
            if r.random() < 0.2:                    # hole in the list
                vals[r.randrange(5)] = 0
            st.topics(vals)
            a = W.put(st)
            x = r.random()
            if x < 0.4 and any(vals):
                topic = (r.choice([v for v in vals if v]) - 1) & 0xffffffff
            elif x < 0.55:
                topic = 0xffffffff                  # topic + 1 == 0 matches an empty slot
            else:
                topic = r.choice([0, 1, 5, r.randrange(300), 0x7fffffff, 0xfffffffe, 0x80000000])
            c.arg(a)
            c.arg(topic)
            if kind == 'addtopic':
                W.cap_states()
            c.note(topics=','.join('%x' % v for v in vals), topic=topic)


def t_facts(ctx, E):
    tell = ctx.fn(0x0050dd50)   # void TellNpcFact(W8NpcState*, short)
    knows = ctx.fn(0x0050dd10)  # bool NpcKnowsFact(W8NpcState*, W8FactId)
    for kind, fn, count in (('tellfact', tell, 150), ('knowsfact', knows, 150)):
        for i in range(ctx.n(count)):
            r = ctx.rng(kind, i)
            c = ctx.case('%s.%d' % (kind, i), fn, conv='c', ret='v' if kind == 'tellfact' else 'b')
            W = World(ctx, E, c)
            st = St()
            nfill = r.choice([0, 1, 5, 10, 13, 14, 14, r.randrange(15)])
            vals = [r.choice([r.randrange(1, 1001), 0x8000, 0xffff, 0x7fff, 0x8001]) if k < nfill else 0
                    for k in range(14)]
            if r.random() < 0.25 and nfill:
                vals[r.randrange(14)] = 0
            st.facts(vals)
            a = W.put(st)
            x = r.random()
            if x < 0.45 and any(vals):
                fact = r.choice([v for v in vals if v])
                if r.random() < 0.3 and fact >= 0x8000:
                    fact -= 0x10000                     # the slot value sign-extended
            else:
                fact = r.choice([0, 1, r.randrange(1, 1001), 0x10000 + r.randrange(1, 1000),
                                 0xffff, -1, 0x7fffffff, -0x8000])
            if kind == 'tellfact' and r.random() < 0.2:
                fact = (fact & 0xffff) | (r.getrandbits(16) << 16)   # garbage high half
            c.arg(a)
            c.arg(fact & 0xffffffff)
            if kind == 'tellfact':
                W.cap_states()
            c.note(facts=','.join('%x' % v for v in vals), fact=fact)


# ----------------------------------------------------------------------------- vector lookups
def kind_world(ctx, E, c, r, W, n=None, dup_p=0.2, odd_p=0.1, null_ok=False):
    """n states whose records are real NPC.DBS records (kind == id) or scratch records
    with duplicate / unusual kinds. Returns (addrs, kinds, states)."""
    n = r.choice([1, 2, 3, 4, 5, 6, 8, 10]) if n is None else n
    rids = r.sample(range(E.nrec), n)
    addrs, kinds, sts = [], [], []
    for k in range(n):
        x = r.random()
        if x < dup_p and kinds:
            kd = r.choice(kinds)
            rec = W.rec(recdata(E, None, kind=kd))
        elif x < dup_p + odd_p:
            kd = r.choice([-1, 0x100, 0x80000000, 0x7fffffff, 0x14 + 0x100])
            rec = W.rec(recdata(E, None, kind=kd))
        else:
            kd = rids[k]
            rec = W.real(kd)
        st = St(rec)
        st['spawned'] = r.choice([0, 0, 1, 0x100, 0xffff, 0xff, 0x1ff])
        st['binding_unavailable'] = r.choice([0, 0, 0, 1])
        st['name_style'] = r.randrange(146)
        sts.append(st)
        addrs.append(W.put(st))
        kinds.append(kd & 0xffffffff if kd >= 0 else kd)
    return addrs, kinds, sts


def pick_kind(r, kinds):
    if r.random() < 0.7:
        return r.choice(kinds)
    return r.choice([0, 145, 146, 0x14, -1, 0x100, 0x80000000, r.randrange(146)])


def t_get_state(ctx, E):
    fn = ctx.fn(0x0050b800)  # W8NpcState* GetNpcState(int index)
    for i in range(ctx.n(150)):
        r = ctx.rng('getstate', i)
        c = ctx.case('getstate.%d' % i, fn, conv='c', ret='p', out='p')
        W = World(ctx, E, c)
        n = r.choice([1, 2, 3, 5, 8])
        addrs = []
        for k in range(n):
            st = St(None, binding_unavailable=r.choice([0, 0, 0, 1, 0x80]), name_style=k)
            addrs.append(W.put(st) if r.random() > 0.1 else None)
        if r.random() < 0.05:
            c.set(E.vec_ptr, p32(0))
            note = 'null'
        else:
            neg = {1: addrs[0] if r.random() < 0.5 else None, 2: addrs[-1]}
            W.vector(addrs, count=n if r.random() > 0.1 else r.choice([0, n - 1, -1]), neg=neg)
            note = 'vector'
        idx = r.choice(list(range(n)) * 2 + [n, n + 1, 1000, -1, -2, -3, 0x7fffffff, -0x80000000])
        c.arg(idx)
        c.note(n=n, index=idx, vec=note, null_slots=[k for k, a in enumerate(addrs) if a is None])


def t_by_kind(ctx, E):
    byk = ctx.fn(0x0050b830)   # W8NpcState* GetNpcStateByKind(int)
    find = ctx.fn(0x0050dd80)  # unsigned char FindNpcOfKind(int)
    mark = ctx.fn(0x0050ca30)  # void MarkNpcOfKind(int)
    for kind, fn, ret, count in (('bykind', byk, 'p', 150), ('findkind', find, 'u8', 150),
                                 ('markkind', mark, 'v', 150)):
        for i in range(ctx.n(count)):
            r = ctx.rng(kind, i)
            c = ctx.case('%s.%d' % (kind, i), fn, conv='c', ret=ret, out='p' if ret == 'p' else None)
            W = World(ctx, E, c)
            addrs, kinds, sts = kind_world(ctx, E, c, r, W)
            cnt = len(addrs) if r.random() > 0.08 else r.choice([0, -1, len(addrs) - 1])
            W.vector(addrs, count=cnt)
            k = pick_kind(r, kinds)
            c.arg(k)
            if kind == 'markkind':
                W.cap_states()
            c.note(kinds=','.join(str(x) for x in kinds), kind=k, count=cnt)


def t_lead_name_style(ctx, E):
    fn = ctx.fn(0x0050b8f0)  # bool NpcLeadHasNameStyle(W8NpcId)
    for i in range(ctx.n(200)):
        r = ctx.rng('leadname', i)
        c = ctx.case('leadname.%d' % i, fn, conv='c', ret='b')
        W = World(ctx, E, c)
        names = []
        addrs = []
        n = r.choice([2, 3, 4])
        for k in range(n):
            nm = r.choice([NPC_DRAZIC, NPC_RODAN, 0x18, 0x07, 0x38, r.randrange(256)])
            names.append(nm)
            addrs.append(W.put(St(None, name_style=nm)))
        W.vector(addrs)
        rows = []
        for s in (0, 1):
            occ = bbyte(r, 0.75, 0.08)
            idx = r.choice(list(range(n)) + [n])    # n clamps to data[0]
            hc = condv(r, edge=0.08)
            c.set(E.xrow(s) + X_OCC, p8(occ))
            c.set(E.xrow(s) + X_NPC, p32(idx))
            c.set(E.char(s) + C_HCOND, p32(hc))
            rows.append('%x/%d/%x' % (occ, idx, hc))
        kd = r.choice(names) if r.random() < 0.6 else r.choice([0, NPC_DRAZIC, NPC_RODAN, 0x110, 0x10010,
                                                                -1, r.randrange(256)])
        c.arg(kd)
        c.note(names=','.join('%x' % x for x in names), rows=' '.join(rows), kind=kd)


def t_monster_info(ctx, E):
    info_fn = ctx.fn(0x0050a3c0)  # W8MonsterInfo* GetNpcMonsterInfo(W8NpcState*)
    mon_fn = ctx.fn(0x0050a400)   # W8Monster* GetNpcMonster(W8NpcState*)
    for kind, fn, count in (('monsterinfo', info_fn, 100), ('monster', mon_fn, 80)):
        for i in range(ctx.n(count)):
            r = ctx.rng(kind, i)
            c = ctx.case('%s.%d' % (kind, i), fn, conv='c', ret='p', out='p')
            W = World(ctx, E, c)
            n = r.choice([0, 1, 1, 2, 3, 4])
            locs = mon_locs(r, n)
            mons = [Mon(locs[k], p3d=r.random() < 0.85) for k in range(n)]
            put_monsters(c, E, mons)
            st = St(None, has_monster=bbyte(r, 0.85, 0.05), is_present=bbyte(r, 0.85, 0.05))
            j = r.randrange(n + 1)
            st['location_id'] = locs[j]
            c.arg(W.put(st))
            c.note(monsters=n, found=j < n, has_monster=st['has_monster'], present=st['is_present'])


def t_group_lookup(ctx, E):
    entry_fn = ctx.fn(0x0050b870)  # W8MonsterManagerEntry* GetNpcGroupEntry(W8NpcState*)
    char_fn = ctx.fn(0x0050b8b0)   # W8Character* GetNpcGroupCharacter(W8NpcState*)
    for kind, fn, count in (('groupentry', entry_fn, 100), ('groupchar', char_fn, 100)):
        for i in range(ctx.n(count)):
            r = ctx.rng(kind, i)
            c = ctx.case('%s.%d' % (kind, i), fn, conv='c', ret='p', out='p')
            W = World(ctx, E, c)
            hg = r.choice([0, 1, 1, 1, 2, 0x80])
            if r.random() < 0.4:
                rid = r.choice(E.group_rids) if hg else r.randrange(E.nrec)
                rec = W.real(rid)
                hg = E.NPCS[rid][0x57]
            else:
                rec = W.rec(recdata(E, None, has_group=hg))
            gi = r.randrange(9 if kind == 'groupentry' else 8)
            st = St(rec, is_grouped=bbyte(r, 0.8, 0.05), group_index=gi)
            a = W.put(st)
            # the 32 bytes the harness reads behind a non-scratch pointer must be known
            if kind == 'groupentry':
                c.set(E.gx + gi * GX_ENTRY, bytes(r.getrandbits(8) for _ in range(32)))
            else:
                ctx.set_party(c, r, slots=[gi])
            c.arg(a)
            c.note(has_group=hg, grouped=st['is_grouped'], group_index=gi)


# ----------------------------------------------------------------------------- trade
def put_item(c, addr, iid, stack=0, uses=0, ident=1):
    c.set(addr, struct.pack('<iBBBBBBBB', iid, stack & 0xff, uses & 0xff, ident, 0, 0, 0, 0, 0))


def item_value_edges(c, E, r, iid):
    """Override the item record fields GetItemStackValue reads (restored after)."""
    notes = {}
    if r.random() < 0.4:
        v = r.choice([0, 1, 12, 13, 299, 300, 301, 3000, 7500, 0x7fffffff, 0x80000000, 0xffffffff,
                      r.randrange(100000)])
        c.set(E.irec(iid, I_VALUE), p32(v))
        notes['item_value'] = v
    if r.random() < 0.2:
        cls = r.choice([4, 4, 0, 3, 5])
        c.set(E.irec(iid, I_CLASS), p8(cls))
        notes['item_class'] = cls
    if r.random() < 0.2:
        qk = r.choice([0, 1, 1, 2, 3])
        c.set(E.irec(iid, I_QKIND), p8(qk))
        notes['item_qkind'] = qk
    return notes


def t_will_trade(ctx, E):
    fn = ctx.fn(0x0050a9c0)  # bool WillNpcTradeForItem(W8NpcState*, W8ItemInstance*)
    for i in range(ctx.n(300)):
        r = ctx.rng('willtrade', i)
        c = ctx.case('willtrade.%d' % i, fn, conv='c', ret='b')
        W = World(ctx, E, c)
        x = r.random()
        if x < 0.15:
            kd = 0x14
        elif x < 0.25:
            kd = r.choice([0x114, -1, 0x80000014, 0x15, 0x13])
        else:
            kd = r.randrange(146)
        rec = W.real(kd) if (0 <= kd < E.nrec and r.random() < 0.5) else W.rec(recdata(E, None, kind=kd))
        a = W.put(St(rec))
        x = r.random()
        if x < 0.12:
            iid = 0x29f
        elif x < 0.35:
            iid = r.choice(E.ammo)
        elif x < 0.55:
            iid = r.choice(E.stackable)
        else:
            iid = E.item(r)
        stack = r.choice([0, 1, 2, 5, 10, 24, 25, 99, 100, 128, 255, r.randrange(256)])
        put_item(c, E.S[4], iid, stack=stack, uses=r.randrange(256))
        notes = item_value_edges(c, E, r, iid)
        c.arg(a)
        c.arg(E.S[4])
        c.note(kind=kd, item=iid, stack=stack, **notes)


def t_count_leading(ctx, E):
    fn = ctx.fn(0x0050b9b0)  # unsigned char CountLeadingPartySlots(void)
    for i in range(ctx.n(60)):
        r = ctx.rng('countleading', i)
        c = ctx.case('countleading.%d' % i, fn, conv='c', ret='u8')
        o0 = r.choice([0, 1, 0, 1, 2, 0x80, 0xff])
        o1 = r.choice([0, 1, 0, 1, 2, 0x80, 0xff])
        c.set(E.xrow(0) + X_OCC, p8(o0))
        c.set(E.xrow(1) + X_OCC, p8(o1))
        c.note(occ='%x,%x' % (o0, o1))


def t_wants_item(ctx, E):
    fn = ctx.fn(0x0050dc50)  # bool NpcWantsItem(W8NpcState*, W8ItemInstance*)
    for i in range(ctx.n(300)):
        r = ctx.rng('wantsitem', i)
        c = ctx.case('wantsitem.%d' % i, fn, conv='c', ret='b')
        W = World(ctx, E, c)
        rid = r.choice(E.group_rids) if r.random() < 0.7 else r.randrange(E.nrec)
        data = recdata(E, rid)
        target = E.item(r)
        # wanted ids are one-based; every positive one stays inside Items.dbs because
        # g_item_records[wanted - 1] is read
        wanted = []
        for k in range(3):
            x = r.random()
            if x < 0.3:
                w = 0
            elif x < 0.5:
                w = target + 1
            elif x < 0.65:
                w = r.choice(E.uni83) + 1
            elif x < 0.85:
                w = E.item(r) + 1
            else:
                w = r.choice([-1, -0x8000, -2, 1, E.nitems])
            wanted.append(w)
        if r.random() < 0.15:
            wanted = list(struct.unpack_from('<hhh', E.NPCS[rid], TPL + T_WANTED))
        for k, w in enumerate(wanted):
            struct.pack_into('<h', data, TPL + T_WANTED + 2 * k, w)
        rec = W.rec(data)
        x = r.random()
        if x < 0.4:
            iid = target
        elif x < 0.65:
            iid = r.choice(E.uni83)
        else:
            iid = E.item(r)
        grouped = bbyte(r, 0.6, 0.05)
        gi = r.randrange(8)
        st = St(rec, is_grouped=grouped, group_index=gi)
        a = W.put(st)
        put_item(c, E.S[4], iid, stack=r.choice([0, 1, 3]))
        copies = []
        if grouped:
            ctx.set_party(c, r, slots=[gi])
            for k in range(r.choice([0, 0, 1, 1, 2, 3])):
                if r.random() < 0.6:
                    slot = r.randrange(12)
                    base = E.char(gi) + C_EQUIP + slot * 0xc
                else:
                    slot = 12 + r.randrange(8)
                    base = E.char(gi) + C_PACK + (slot - 12) * 0xc
                stack = r.choice([0, 1, 1, 2, 3, 255])
                put_item(c, base, iid, stack=stack)
                copies.append('%d:%d' % (slot, stack))
        c.arg(a)
        c.arg(E.S[4])
        c.note(record=rid, wanted=wanted, item=iid, grouped=grouped, group_index=gi,
               copies=','.join(copies))


def t_offers_service(ctx, E):
    fn = ctx.fn(0x0050c9e0)  # bool NpcOffersService(W8NpcState*, unsigned int service_id)
    for i in range(ctx.n(200)):
        r = ctx.rng('offers', i)
        c = ctx.case('offers.%d' % i, fn, conv='c', ret='b')
        W = World(ctx, E, c)
        if r.random() < 0.4:
            rid = r.choice(E.group_rids) if r.random() < 0.7 else r.randrange(E.nrec)
            rec = W.real(rid)
            flags = struct.unpack_from('<I', E.NPCS[rid], 0x68)[0]
        else:
            flags = r.choice([0, 0xffffffff, r.getrandbits(14), r.choice(SERVICE_BITS),
                              r.getrandbits(32), 0x1000 | 0x80])
            rec = W.rec(recdata(E, None, service_flags=flags))
        sid = r.choice(list(range(0, 18)) + [0xffffffff, 0x100, 0x102, 0x80000008])
        c.arg(W.put(St(rec)))
        c.arg(sid)
        c.note(service_flags=flags, service=sid)


def t_can_join(ctx, E):
    fn = ctx.fn(0x0050c870)  # bool CanNpcJoinParty(W8NpcState*)
    special = [NPC_GLUMPH, NPC_SEXUS, NPC_MADRAS, NPC_DRAZIC, NPC_RODAN]
    for i in range(ctx.n(400)):
        r = ctx.rng('canjoin', i)
        c = ctx.case('canjoin.%d' % i, fn, conv='c', ret='b')
        W = World(ctx, E, c)
        level, band, _, _ = E.level(c, r)
        hg = r.choice([1, 1, 1, 1, 1, 0, 2, 0x80])
        rid = r.choice(E.group_rids)
        x = r.random()
        if x < 0.3:
            flags = struct.unpack_from('<I', E.NPCS[rid], 0x68)[0]
        elif x < 0.5 and band in SERVICE_BIT:
            flags = SERVICE_BIT[band] | r.getrandbits(14)
        else:
            flags = r.getrandbits(14) & ~(SERVICE_BIT.get(band, 0)) if r.random() < 0.6 else r.getrandbits(32)
        mpl = r.choice([0, 0, 0, 1, 5, 8, 10, 12, 15, 20, 30, 0x80, 0xff, r.randrange(1, 25)])
        rec = W.rec(recdata(E, rid, has_group=hg, service_flags=flags, min_party_level=mpl))
        ns = r.choice(special) if r.random() < 0.45 else r.choice([rid, r.randrange(256)])
        a = W.put(St(rec, name_style=ns))
        facts = {f: r.choice([0, 1, 1, 0, 2, 0xff]) for f in (F_SCUBA, F_SEXUS, F_MADRAS, F_PEACE)}
        E.facts_set(c, facts)
        E.nolog(c)
        party = ctx.set_party(c, r)
        lv = []
        for s in range(8):
            c.set(E.xrow(s) + X_OCC, p8(bbyte(r, 0.8, 0.04)))
            c.set(E.char(s) + C_HP, p32(hpv(r, 0.1)))
            c.set(E.char(s) + C_HCOND, p32(condv(r)))
            if r.random() < 0.3:
                v = r.choice([0, 1, 2, 9, 10, 11, 20, 50, 0x7fffffff, 0x80000000, 0xffffffff, r.randrange(1, 30)])
                c.set(E.char(s) + C_LEVEL, p32(v))
                lv.append(v)
        c.arg(a)
        c.note(level=level, band=band, has_group=hg, service_flags=flags, min_level=mpl,
               name_style=ns, facts=facts, levels=lv)
        if level == 47:
            c.note(edge='level47')


def t_display_name(ctx, E):
    fn = ctx.fn(0x0050c770)  # const char* GetNpcDisplayName(W8NpcState*)
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 _-.\''
    for i in range(ctx.n(120)):
        r = ctx.rng('displayname', i)
        c = ctx.case('displayname.%d' % i, fn, conv='c', ret='c', out='c')
        W = World(ctx, E, c)
        if r.random() < 0.5:
            rid = r.randrange(E.nrec)
            rec = W.real(rid)
            text = E.names[rid]
        else:
            n = r.choice([0, 1, 6, 20, 37])
            text = ''.join(r.choice(alphabet) for _ in range(n))
            data = recdata(E, None)
            put_cstr(data, R_DISPLAY_NAME, text, 0x26)
            rec = W.rec(data)
        ns = r.choice([NPC_RFS81A, NPC_RFS81A, 0x21, 0x120 & 0xff, r.randrange(256)])
        fact = r.choice([0, 1, 2, 0xff])
        E.facts_set(c, {F_RFS81_FIXED: fact})
        E.nolog(c)
        c.fill(E.name_buf, 52, 0x5a)
        c.arg(W.put(St(rec, name_style=ns)))
        c.cap(E.name_buf, 52, 'name_buffer')
        c.note(name_style=ns, fact=fact, text=text)


def t_find_by_name(ctx, E):
    fn = ctx.fn(0x0050ada0)  # W8NpcState* FindNpcStateByName(const char*)
    for i in range(ctx.n(200)):
        r = ctx.rng('findname', i)
        c = ctx.case('findname.%d' % i, fn, conv='c', ret='p', out='p')
        W = World(ctx, E, c)
        n = r.choice([1, 2, 3, 4, 6, 8])
        rids = r.sample(range(E.nrec), n)
        texts, addrs = [], []
        for k in range(n):
            if r.random() < 0.7:
                rec = W.real(rids[k])
                text = E.names[rids[k]]
            else:
                text = r.choice(['RFS81B', 'rfs81b', 'Vi', 'SAXX', 'GUARD', '', 'Rattus Rattus'])
                data = recdata(E, None)
                put_cstr(data, R_DISPLAY_NAME, text, 0x26)
                rec = W.rec(data)
            ns = NPC_RFS81A if r.random() < 0.2 else rids[k]
            st = St(rec, name_style=ns, binding_unavailable=r.choice([0, 0, 0, 1, 0x40]))
            addrs.append(W.put(st))
            texts.append(text)
        W.vector(addrs)
        x = r.random()
        if x < 0.55:
            q = r.choice(texts)
            q = r.choice([q, q.lower(), q.upper(), q.swapcase()])
        elif x < 0.7:
            q = r.choice(['RFS81B', 'rfs81b', 'Rfs81B'])
        else:
            q = r.choice(['', 'X', 'NOBODY', r.choice(texts) + ' ', r.choice(texts)[:-1] if texts else ''])
        c.set(E.S[4] + 0x300, q.encode('latin1') + b'\0')
        fact = r.choice([0, 1, 2])
        E.facts_set(c, {F_RFS81_FIXED: fact})
        E.nolog(c)
        c.fill(E.name_buf, 52, 0)
        c.arg(E.S[4] + 0x300)
        c.cap(E.name_buf, 52, 'name_buffer')
        c.note(names='|'.join(texts), query=q, fact=fact)


def t_timers(ctx, E):
    fn = ctx.fn(0x0050c7d0)  # void AdvanceNpcTimers(unsigned int elapsed)
    for i in range(ctx.n(200)):
        r = ctx.rng('timers', i)
        c = ctx.case('timers.%d' % i, fn, conv='c', ret='v')
        W = World(ctx, E, c)
        clock = r.choice([0, 1, 0xa8c0, 0xa8c1, 0x7fffffff, 0x80000000, 0xffffffff, r.getrandbits(32),
                          r.randrange(0x1000000)])
        c.set(E.gs + GS_CLOCK, p32(clock))
        n = r.choice([1, 2, 3, 5, 8])
        addrs = []
        for k in range(n):
            st = St(None, binding_unavailable=r.choice([0, 0, 0, 1]))
            st['dismissed_flag'] = bbyte(r, 0.6, 0.05)
            st['dismissed_timer'] = r.choice([0, 1, 0x3b, 0x3c, 0x3d, 0xffffffff, 0xfffffff0, r.randrange(100)])
            for flag, stamp in (('talk_cd', 'talk_clock'), ('trade_cd', 'trade_clock')):
                st[flag] = bbyte(r, 0.6, 0.05)
                d = r.choice([0, 1, 0xa8bf, 0xa8c0, 0xa8c1, 0xa8c2, -1, -0xa8c1, 0x80000000, r.randrange(0x20000)])
                st[stamp] = (clock - d) & 0xffffffff
            addrs.append(W.put(st))
        cnt = n if r.random() > 0.1 else r.choice([0, n - 1])
        W.vector(addrs, count=cnt)
        el = r.choice([0, 1, 10, 0x3c, 0x3d, 600, 0xffffffff, 0x80000000, r.randrange(200)])
        c.arg(el)
        W.cap_states()
        c.note(clock=clock, elapsed=el, count=cnt)


# ----------------------------------------------------------------------------- start location
def start_world(ctx, E, c, r, W, start_level):
    """States for kinds 0x18, 0x0c and 0x8c (+ others); a state whose restore runs on the
    current level has has_monster set and is not present (RestoreNpcMonster returns
    false without touching the monster database)."""
    rids = [0x18, 0x0c, 0x8c] + r.sample([x for x in range(E.nrec) if x not in (0x18, 0x0c, 0x8c)],
                                         r.choice([0, 1, 2, 3]))
    r.shuffle(rids)
    addrs = []
    for rid in rids:
        rec = W.real(rid) if r.random() < 0.8 else W.rec(recdata(E, rid))
        st = St(rec, name_style=rid, has_monster=1, is_present=0)
        if r.random() < 0.3:
            st['pending_restore'] = r.choice([0, 1])
            st['pending_restore_level'] = r.randrange(256)
            st.b[ST_RESTORE_NAME:ST_RESTORE_NAME + 8] = b'OLDNAME\0'
        addrs.append(W.put(st))
    W.vector(addrs)
    return rids


def t_start_location(ctx, E):
    fn = ctx.fn(0x005092f0)  # void ChooseNewGameStartLocation(int* level, int* entrance)
    for i in range(ctx.n(100)):
        r = ctx.rng('startloc', i)
        c = ctx.case('startloc.%d' % i, fn, conv='c', ret='v')
        W = World(ctx, E, c)
        facts = {f: r.choice([0, 0, 1, 2, 0xff]) for f in (F_VIRGIN, F_IMPORT_UMPANI, F_IMPORT_TRANG)}
        E.facts_set(c, facts)
        E.nolog(c)
        cur = r.choice([6, 8, 0xe, 1, 2, 3, 5, 0x26, r.randrange(47), -1, 0x106, 0x10e])
        c.set(E.gs + GS_LEVEL, p32(cur))
        c.set(E.gs + GS_GREETING, b'\0')
        rids = start_world(ctx, E, c, r, W, None)
        c.set(E.S[4] + 0x10, struct.pack('<II', r.getrandbits(32), r.getrandbits(32)))
        c.arg(E.S[4] + 0x10)
        c.arg(E.S[4] + 0x14)
        c.cap(E.S[4] + 0x10, 8, 'level_entrance')
        c.cap(E.gs + GS_GREETING, 1, 'greeting_pending')
        W.cap_states()
        c.note(facts=facts, current_level=cur, kinds=rids)


def t_start_level(ctx, E):
    fn = ctx.fn(0x00509750)  # int SelectNewGameStartLevel(void)
    combos = [(a, b, d) for a in (0, 1) for b in (0, 1) for d in (0, 1)]
    for i in range(ctx.n(60)):
        r = ctx.rng('startlevel', i)
        c = ctx.case('startlevel.%d' % i, fn, conv='c', ret='i')
        a, b, d = combos[i % 8]
        vals = [x * r.choice([1, 1, 2, 0x80, 0xff]) for x in (a, b, d)]
        E.facts_set(c, {F_VIRGIN: vals[0], F_IMPORT_UMPANI: vals[1], F_IMPORT_TRANG: vals[2]})
        E.nolog(c)
        c.note(virgin=vals[0], umpani=vals[1], trang=vals[2])


# ----------------------------------------------------------------------------- NPC character
def t_init_character(ctx, E):
    fn = ctx.fn(0x0050aed0)  # bool InitializeNpcCharacter(W8NpcState*, W8Character*)
    for i in range(ctx.n(250)):
        r = ctx.rng('initchar', i)
        c = ctx.case('initchar.%d' % i, fn, conv='c', ret='b')
        W = World(ctx, E, c)
        rid = r.choice(E.group_rids)
        data = recdata(E, rid)
        notes = {'record': rid}
        t = TPL
        if r.random() < 0.05:
            data[0x57] = r.choice([0, 0])
            notes['has_group'] = 0
        if r.random() < 0.4:
            lvl = r.choice([1, 2, 3, 5, 8, 10, 12, 15, 20, 25, 30, 40, 49, 50, 51, 60, 255, 0]
                           if r.random() < 0.6 else [r.randrange(1, 31)])
            struct.pack_into('<I', data, t + T_LEVEL, lvl)
            notes['level'] = lvl
        if r.random() < 0.25:
            prof = r.randrange(15) if r.random() < 0.92 else r.choice([15, 16])
            struct.pack_into('<i', data, t + T_PROF, prof)
            notes['prof'] = prof
        if r.random() < 0.2:
            race = r.randrange(11)
            struct.pack_into('<i', data, t + T_RACE, race)
            notes['race'] = race
        if r.random() < 0.1:
            g = r.choice([0, 1, 0, 1, -1])
            data[t + T_GENDER] = g & 0xff
            notes['gender'] = g
        if r.random() < 0.3:
            for a in range(7):
                if r.random() < 0.5:
                    v = r.choice([30, 40, 50, 60, 75, 90, 99, 100, 101, 110, 125, r.randrange(30, 126)])
                    struct.pack_into('<i', data, t + T_ATTR + 4 * a, v)
            notes['attrs'] = 1
        if r.random() < 0.3:
            for s in range(0x29):
                if r.random() < 0.25:
                    v = r.choice([0, 1, 5, 10, 25, 50, 75, 99, 100, 101, 125, r.randrange(0, 101)])
                    struct.pack_into('<i', data, t + T_SKILLS + 4 * s, v)
            notes['skills'] = 1
        if r.random() < 0.35:
            for s in range(0x72):
                if r.random() < 0.2:
                    data[t + T_SPELLS + s] = r.choice([0, 1, 1, 2, 0xff])
            notes['spells'] = 1
        if r.random() < 0.25:
            for k in range(r.randrange(1, 4)):
                if r.random() < 0.6:
                    e = r.randrange(12)
                    pres, ids = T_EQ_PRESENT + 2 * e, T_EQ_IDS + 2 * e
                else:
                    e = r.randrange(8)
                    pres, ids = T_BP_PRESENT + 2 * e, T_BP_IDS + 2 * e
                x = r.random()
                if x < 0.6:
                    struct.pack_into('<HH', data, t + pres, 1, 0)
                    struct.pack_into('<H', data, t + ids, E.item(r))
                elif x < 0.8:
                    struct.pack_into('<H', data, t + pres, 0)
                else:
                    struct.pack_into('<H', data, t + ids, 0xffff)
            notes['items'] = 1
        if r.random() < 0.15:
            struct.pack_into('<i', data, t + T_TABLE, r.choice([0, 1, 59, 75, 100, -1]))
        rec = W.rec(data)
        a = W.put(St(rec, name_style=rid))
        out = E.S[5]
        if r.random() < 0.7:
            blob, name = ctx.pick_char(r)
            c.setb(out, bytes(blob))
            notes['prefill'] = name
        E.rebuild_env(c, [])
        c.arg(a)
        c.arg(out)
        c.cap(out, CHAR, 'character', floats=CHAR_FLOATS)
        c.note(**notes)


# ----------------------------------------------------------------------------- bindings
def all_kinds_world(ctx, E, c, r, W, n=None, real_p=0.8, avoid=(), force=None):
    """n states with distinct real records (kind == id) whose name_style always names a
    kind present in the vector (so every companion / restore target lookup succeeds)."""
    n = r.choice([2, 3, 4, 5, 6]) if n is None else n
    pool = [x for x in range(E.nrec) if x not in avoid and x != force]
    rids = r.sample(pool, n)
    if force is not None:
        rids[r.randrange(n)] = force
    sts = []
    for k in range(n):
        rec = W.real(rids[k]) if r.random() < real_p else W.rec(recdata(E, rids[k]))
        st = St(rec, name_style=r.choice(rids) if r.random() < 0.5 else rids[k])
        sts.append(st)
    return rids, sts


def t_release_binding(ctx, E):
    fn = ctx.fn(0x00509ea0)  # void ReleaseNpcBinding(int value)
    for i in range(ctx.n(150)):
        r = ctx.rng('releasebinding', i)
        c = ctx.case('releasebinding.%d' % i, fn, conv='c', ret='v')
        W = World(ctx, E, c)
        n = r.choice([1, 2, 3, 5, 8])
        addrs = []
        mbs = []
        for k in range(n):
            mb = r.choice([0, 0, 1, 2, 0x80])
            st = St(W.rec(recdata(E, None, monster_bound=mb, kind=k)),
                    has_monster=bbyte(r, 0.7), binding_unavailable=r.choice([0, 0, 1]))
            mbs.append(mb)
            addrs.append(W.put(st))
        W.vector(addrs)
        v = r.choice(list(range(n)) * 2 + [n, n + 1, -1, -2, 1000, 0x7fffffff, -0x80000000])
        c.arg(v)
        W.cap_states()
        c.note(n=n, value=v, monster_bound=mbs)


def t_monster_binding_lookup(ctx, E):
    find = ctx.fn(0x0050a440)  # W8NpcState* FindNpcBindingForMonster(unsigned int)
    get = ctx.fn(0x0050a4a0)   # W8NpcState* GetNpcStateForMonsterInfo(W8MonsterInfo*, bool)
    for kind, fn, count in (('bindformonster', find, 120), ('stateformonster', get, 150)):
        for i in range(ctx.n(count)):
            r = ctx.rng(kind, i)
            c = ctx.case('%s.%d' % (kind, i), fn, conv='c', ret='p', out='p')
            W = World(ctx, E, c)
            ns = r.choice([1, 2, 3, 5])
            addrs = []
            for k in range(ns):
                st = St(None, binding_unavailable=r.choice([0, 0, 0, 1, 0x20]), name_style=k)
                addrs.append(W.put(st))
            W.vector(addrs, neg={1: addrs[-1]})
            nm = r.choice([1, 2, 3, 4])
            locs = mon_locs(r, nm)
            mons = []
            for k in range(nm):
                flags = r.choice([1, 1, 1, 3, 0x11, 0, 2, 0xfe, 0xff])
                nk = r.choice([0, 1, 5, 0xfa, 0xfa, 0xf9, 0xfb, r.randrange(256)])
                bound = r.choice(list(range(ns)) * 2 + [ns, ns + 2, -1, 0x7fffffff])
                mons.append(Mon(locs[k], bound=bound, rec=(flags, nk, 5)))
            put_monsters(c, E, mons)
            k = r.randrange(nm)
            if kind == 'bindformonster':
                c.arg(k)
            else:
                allow = r.choice([0, 1, 0, 1, 0x100, 0xff, 2])
                c.arg(E.S[2] + 0x100 + k * 0x430)
                c.arg(allow)
                c.note(allow=allow)
            m = mons[k]
            c.note(monster=k, flags=m.rec[0], npc_kind=m.rec[1], bound=m.bound, states=ns)


def companion_world(ctx, E, c, r, W, n=None, avoid=()):
    """Release-pass world: every state has a companion (kind == its name_style), monsters
    are never found (both lists null: a present companion only produces the lookup
    asserts), partner indexes point inside, at the clamp index or past the vector."""
    rids, sts = all_kinds_world(ctx, E, c, r, W, n, avoid=avoid)
    n = len(sts)
    for st in sts:
        st['has_monster'] = bbyte(r, 0.75, 0.04)
        st['is_present'] = bbyte(r, 0.5, 0.04)
        st['location_id'] = r.getrandbits(32)
        st['partner_index'] = r.choice(list(range(n)) * 3 + [n, n + 1, 0xff])
        st['binding_unavailable'] = r.choice([0] * 6 + [1, 0x10])
    E.no_monsters(c)
    return rids, sts


def t_release_monster_bindings(ctx, E):
    fn = ctx.fn(0x0050c2e0)  # void ReleaseNpcMonsterBindings(void)
    for i in range(ctx.n(150)):
        r = ctx.rng('releaseall', i)
        c = ctx.case('releaseall.%d' % i, fn, conv='c', ret='v')
        W = World(ctx, E, c)
        cur = r.choice([r.randrange(47), 0x80, 0xc8, 0xff, -1, -0x38, 0x17f, 0x100])
        c.set(E.gs + GS_LEVEL, p32(cur))
        rids, sts = companion_world(ctx, E, c, r, W)
        for st in sts:
            st['pending_release'] = bbyte(r, 0.6, 0.05)
            st['pending_release_level'] = r.choice([cur & 0xff, cur & 0xff, r.randrange(256), (cur + 1) & 0xff])
        W.vector([W.put(st) for st in sts])
        W.cap_states()
        c.note(current_level=cur, kinds=rids,
               release=['%x@%x' % (st['pending_release'], st['pending_release_level']) for st in sts])


def t_release_monster_binding(ctx, E):
    fn = ctx.fn(0x0050c440)  # void ReleaseNpcMonsterBinding(W8NpcState*, char level)
    for i in range(ctx.n(150)):
        r = ctx.rng('releaseone', i)
        c = ctx.case('releaseone.%d' % i, fn, conv='c', ret='v')
        W = World(ctx, E, c)
        cur = r.choice([r.randrange(47), 0x80, 0xc8, 0xff, -1, -0x38, 0x100])
        c.set(E.gs + GS_LEVEL, p32(cur))
        rids, sts = companion_world(ctx, E, c, r, W)
        addrs = [W.put(st) for st in sts]
        W.vector(addrs)
        k = r.randrange(len(sts))
        lv = r.choice([cur, cur, cur & 0xff, (cur & 0xff) | 0x100, r.randrange(256), cur + 1, 0xffffff00 | (cur & 0xff)])
        c.arg(addrs[k])
        c.arg(lv & 0xffffffff)
        W.cap_states()
        c.note(current_level=cur, level=lv, npc=k, kinds=rids)


def t_release_by_kind(ctx, E):
    fn = ctx.fn(0x0050c680)  # void ReleaseNpcMonsterByKind(int kind)
    for i in range(ctx.n(120)):
        r = ctx.rng('releasekind', i)
        c = ctx.case('releasekind.%d' % i, fn, conv='c', ret='v')
        W = World(ctx, E, c)
        rids, sts = companion_world(ctx, E, c, r, W)
        W.vector([W.put(st) for st in sts])
        kd = r.choice(rids)
        c.arg(kd)
        W.cap_states()
        c.note(kind=kd, kinds=rids)


def restore_targets(st, r, cur):
    st['has_monster'] = 1                    # RestoreNpcMonster never reaches the monster DB
    st['is_present'] = bbyte(r, 0.4, 0.0)
    st['location_id'] = r.getrandbits(32)


def t_restore_named(ctx, E):
    fn = ctx.fn(0x0050c1c0)  # void RestoreNamedNpcAtLevel(int kind, char level, const char* name)
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz0123456789'
    for i in range(ctx.n(150)):
        r = ctx.rng('restorenamed', i)
        c = ctx.case('restorenamed.%d' % i, fn, conv='c', ret='v')
        W = World(ctx, E, c)
        cur = r.choice([r.randrange(47), 0x80, 0xc8, 0xff, -1, -0x38, 0x100])
        c.set(E.gs + GS_LEVEL, p32(cur))
        E.no_monsters(c)
        rids, sts = all_kinds_world(ctx, E, c, r, W)
        for st in sts:
            restore_targets(st, r, cur)
            st['pending_restore'] = r.choice([0, 0, 1])
            st['restored'] = r.choice([0, 1])
        W.vector([W.put(st) for st in sts])
        kd = r.choice(rids)
        lv = r.choice([cur, cur, cur & 0xff, (cur & 0xff) | 0x7f00, r.randrange(256), cur + 1])
        n = r.choice([0, 1, 8, 20, 0x26, 0x27, r.randrange(40)] + ([0x28, 0x2c] if r.random() < 0.1 else []))
        text = ''.join(r.choice(alphabet) for _ in range(n))
        c.set(E.S[4] + 0x300, text.encode('latin1') + b'\0')
        c.arg(kd)
        c.arg(lv & 0xffffffff)
        c.arg(E.S[4] + 0x300)
        W.cap_states()
        c.note(kind=kd, level=lv, current_level=cur, name_len=n)


def t_clear_pending_levels(ctx, E):
    fn = ctx.fn(0x0050c270)  # void ClearPendingNpcLevelFlags(void)
    for i in range(ctx.n(150)):
        r = ctx.rng('clearpending', i)
        c = ctx.case('clearpending.%d' % i, fn, conv='c', ret='v')
        W = World(ctx, E, c)
        cur = r.choice([r.randrange(47), 0x80, 0xc8, 0xff, -1, -0x38, 0x100, 0x17f])
        c.set(E.gs + GS_LEVEL, p32(cur))
        E.no_monsters(c)
        n = r.choice([1, 2, 3, 4, 6])
        addrs = []
        desc = []
        for k in range(n):
            st = St(None)
            restore_targets(st, r, cur)
            st['pending_restore'] = bbyte(r, 0.7, 0.05)
            st['binding_unavailable'] = r.choice([0, 0, 0, 1])
            st['pending_restore_level'] = r.choice([cur & 0xff, cur & 0xff, r.randrange(256)])
            st.b[ST_RESTORE_NAME:ST_RESTORE_NAME + 12] = b'W8D_NO_SUCH\0'
            addrs.append(W.put(st))
            desc.append('%x/%x/%x/%x' % (st['pending_restore'], st['binding_unavailable'],
                                         st['pending_restore_level'], st['is_present']))
        W.vector(addrs)
        W.cap_states()
        c.note(current_level=cur, states=desc)


# ----------------------------------------------------------------------------- marked NPC events
MARK_AVOID = (0x18, 0x29, 0x2b)              # SetFact / location vars + teleport / item spawn


def marked_world(ctx, E, c, r, W, n=None):
    """Kinds present for every name_style; restore levels of every involved record differ
    from the current level unless the case says otherwise."""
    rids, sts = all_kinds_world(ctx, E, c, r, W, n, real_p=1.0, avoid=MARK_AVOID,
                                force=NPC_MYLES if r.random() < 0.3 else None)
    n = len(sts)
    for st in sts:
        st['has_monster'] = 1
        st['is_present'] = bbyte(r, 0.3, 0.0)
        st['location_id'] = r.getrandbits(32)
        st['partner_index'] = r.choice(list(range(n)) * 3 + [n, n + 1, 0xff])
        st['binding_unavailable'] = r.choice([0] * 7 + [1])
        st['event_pending'] = bbyte(r, 0.5, 0.05)
        st['restore_done'] = r.choice([0, 0, 1])
        st['pending_restore'] = r.choice([0, 0, 1])
    levels = {struct.unpack_from('<b', E.NPCS[x], 0x70)[0] for x in rids} | {0x11}
    safe = [lv for lv in list(range(1, 47)) + [0x80, -1] if lv not in levels and lv != 0xd]
    return rids, sts, safe, levels


def t_marked_event(ctx, E):
    fn = ctx.fn(0x0050cf70)  # void HandleMarkedNpcEvent(W8NpcState*, char mode)
    for i in range(ctx.n(200)):
        r = ctx.rng('markedevent', i)
        c = ctx.case('markedevent.%d' % i, fn, conv='c', ret='v')
        W = World(ctx, E, c)
        rids, sts, safe, levels = marked_world(ctx, E, c, r, W)
        k = r.randrange(len(sts))
        npc = sts[k]
        x = r.random()
        if x < 0.1:
            npc['name_style'] = r.choice([0x20, 0x21])
        mode = r.choice([0, 1, 1, 0x100, 0xff])
        fact_jail = r.choice([0, 1])
        E.facts_set(c, {F_MYLES_JAIL: fact_jail, F_SCUBA: 1})
        E.nolog(c)
        # the NPC's own monster: none / not found (asserts) / found in scratch
        mon = r.choice(['none', 'none', 'notfound', 'found'])
        if mon == 'found':
            # found: mode 0 only (a companion release could remove it) and no restore on
            # the current level (the restore would move the found monster)
            mode = 0
            hc = r.choice([0, 3, 0xe, 0xf, 0x10, 0x12, 0x80000000, 0xffffffff])
            locs = mon_locs(r, 1)
            put_monsters(c, E, [Mon(locs[0], highest=hc)])
            npc['is_present'] = 1
            npc['location_id'] = locs[0]
            for st in sts:
                if st is not npc:
                    st['is_present'] = 0
            cur = r.choice(safe)
            c.note(monster_highest=hc)
        else:
            if mon == 'notfound':
                npc['is_present'] = 1
            E.no_monsters(c)
            cur = r.choice(safe) if (mode & 0xff) or r.random() < 0.5 else r.choice(list(levels))
        c.set(E.gs + GS_LEVEL, p32(cur))
        c.set(E.gs + GS_RESTORE_PENDING, b'\0')
        addrs = [W.put(st) for st in sts]
        W.vector(addrs)
        c.arg(addrs[k])
        c.arg(mode)
        W.cap_states()
        c.cap(E.gs + GS_RESTORE_PENDING, 1, 'npc_restore_pending')
        c.note(npc=k, name_style=npc['name_style'], mode=mode, monster=mon, current_level=cur,
               kinds=rids, myles_jail=fact_jail)


def t_release_marked(ctx, E):
    fn = ctx.fn(0x0050da00)  # void ReleaseMarkedNpcBindings(void)
    for i in range(ctx.n(150)):
        r = ctx.rng('releasemarked', i)
        c = ctx.case('releasemarked.%d' % i, fn, conv='c', ret='v')
        W = World(ctx, E, c)
        rids, sts, safe, levels = marked_world(ctx, E, c, r, W)
        E.no_monsters(c)
        E.facts_set(c, {F_MYLES_JAIL: r.choice([0, 1]), F_SCUBA: 1})
        E.nolog(c)
        cur = r.choice(safe)
        c.set(E.gs + GS_LEVEL, p32(cur))
        W.vector([W.put(st) for st in sts])
        W.cap_states()
        c.note(current_level=cur, kinds=rids,
               marks=['%x/%x/%x' % (st['event_pending'], st['pending_restore'], st['binding_unavailable'])
                      for st in sts])


# ----------------------------------------------------------------------------- party bound NPCs
def bound_rows(ctx, E, c, r, W, names=None, cond_fn=None, flags_fn=None):
    """Front rows 0/1 with bound NPC states (always valid, available) in the vector."""
    sts = []
    n = r.choice([2, 3, 4])
    for k in range(n):
        nm = names[k] if names and k < len(names) else r.choice([0x07, 0x18, 0x23, 0x2b, 0x38, 0x4a, 0x4f,
                                                                0x01, 0x68])
        if flags_fn is not None:
            flags = flags_fn(r)
        else:
            flags = r.choice([0, r.getrandbits(14), r.choice(SERVICE_BITS), 0x3fff])
        rec = W.rec(recdata(E, None, service_flags=flags, kind=nm))
        st = St(rec, name_style=nm)
        sts.append(st)
    rows = []
    for s in (0, 1):
        occ = bbyte(r, 0.8, 0.05)
        hp = hpv(r, 0.12)
        hc = cond_fn(r) if cond_fn else condv(r)
        idx = s if r.random() < 0.8 else r.randrange(n)
        rows.append({'occ': occ, 'hp': hp, 'cond': hc, 'idx': idx})
    return sts, rows


def set_rows(c, E, rows):
    """Rows 0/1; fInParty = 1 so a queued (and deleted) character event resolves its slot
    without an assert."""
    for s, row in enumerate(rows):
        c.set(E.char(s) + C_INPARTY, b'\x01')
        c.set(E.xrow(s) + X_OCC, p8(row['occ']))
        c.set(E.xrow(s) + X_NPC, p32(row['idx']))
        c.set(E.char(s) + C_HP, p32(row['hp']))
        c.set(E.char(s) + C_HCOND, p32(row['cond']))


def t_reset_bindings(ctx, E):
    fn = ctx.fn(0x0050db50)  # void ResetNpcBindingsForParty(void)
    for i in range(ctx.n(150)):
        r = ctx.rng('resetbindings', i)
        c = ctx.case('resetbindings.%d' % i, fn, conv='c', ret='v')
        W = World(ctx, E, c)
        ctx.set_party(c, r, slots=[0, 1])
        sts, rows = bound_rows(ctx, E, c, r, W)
        for st in sts:
            st['incapacitated'] = r.choice([0, 1, 1])
        W.vector([W.put(st) for st in sts])
        set_rows(c, E, rows)
        for s in (0, 1):
            c.set(E.xrow(s) + X_BOUND, p8(r.choice([0, 1, 1])))
        clock = r.getrandbits(32)
        c.set(E.gs + GS_CLOCK, p32(clock))
        c.set(E.gs + GS_BIND_CLOCK, p32(r.getrandbits(32)) + b'\0')
        E.rebuild_env(c, [0, 1])
        c.cap(E.gs + GS_BIND_CLOCK, 5, 'binding_reset')
        W.cap_states()
        c.cap(E.xbase, 2 * XROW, 'xchar01', ignore=[0x19, 0x39, XROW + 0x19, XROW + 0x39])
        c.cap(E.char(0), 2 * CHAR, 'chars01', floats=CHAR_FLOATS + [CHAR + o for o in CHAR_FLOATS])
        c.note(rows=rows)


def t_pending_events(ctx, E):
    fn = ctx.fn(0x0050ca80)  # void ProcessNpcPendingEvents(void)
    for i in range(ctx.n(200)):
        r = ctx.rng('pendingevents', i)
        c = ctx.case('pendingevents.%d' % i, fn, conv='c', ret='v')
        W = World(ctx, E, c)
        ctx.set_party(c, r, slots=[0, 1])
        combat = 1 if r.random() < 0.06 else 0
        surprise = 1 if r.random() < 0.06 else 0
        infat = r.choice([0, 0, 1])
        flagged = r.random() < 0.5
        pend = r.choice([0, 1, 1, 1])
        # level: infatuation without the flagged kind-0x42 NPC only on bands 9/10 (else the
        # Al-Sedexus condition + fact path would run)
        if infat and not flagged:
            level = level_for_band(r, r.choice([9, 10]))
            level, band, _, _ = E.level(c, r, level=level)
        elif r.random() < 0.6:
            level = level_for_band(r, r.choice(SERVICE_BANDS))
            level, band, _, _ = E.level(c, r, level=level)
        elif r.random() < 0.25:
            level, band, _, _ = E.level(c, r, level=0x10, f5b=1)        # band 13
        else:
            level, band, _, _ = E.level(c, r)
        pair = band != 0xd and r.random() < 0.12
        names = [NPC_RODAN, NPC_DRAZIC] if pair else None
        if band == 0xd and r.random() < 0.5:
            names = [r.choice([NPC_RODAN, NPC_DRAZIC]), r.choice([NPC_RODAN, NPC_DRAZIC, 0x07])]

        def cond_fn(rr):
            return rr.choice([0, 0, 3, 0xe, 0xf, 0x10, 0x11, 0x12, 0x13, 0x80000000])
        sts, rows = bound_rows(ctx, E, c, r, W, names=names, cond_fn=cond_fn)
        if pair:
            for s in (0, 1):
                rows[s].update(occ=1, idx=s, cond=r.choice([0, 3, 0xe]))
        if not pair and band != 0xd:
            for st in sts:          # Rodan/Drazic without partner start a scripted world action
                if st['name_style'] in (NPC_RODAN, NPC_DRAZIC):
                    st['name_style'] = 0x07
        sid_rows = [row for row in SERVICES if row[1] == band]
        for st in sts:
            for k in range(14):
                st.b[ST_SERVICE + k] = r.choice([0, 0, 1])
            st['incapacitated'] = r.choice([0, 1])
        k42 = None
        if infat or r.random() < 0.3:
            k42 = St(W.rec(recdata(E, None, kind=0x42)))
            k42['spawned'] = r.choice([1, 0xff, 0x101]) if flagged else r.choice([0, 0x100, 0x200])
            sts.append(k42)
        addrs = [W.put(st) for st in sts]
        W.vector(addrs)
        set_rows(c, E, rows)
        clock = r.getrandbits(32)
        d = r.choice([0, 0x3c, 0x3d, 0x3e, 100, 5000, -1, -0x3d, 0x7fffffff, -0x80000000])
        c.set(E.gs + GS_CLOCK, p32(clock))
        c.set(E.gs + GS_BIND_CLOCK, p32(clock - d) + p8(pend))
        c.set(E.gs + GS_INFATUATION, p8(infat))
        c.set(E.gx + GX_SURPRISE, p8(surprise))
        E.rebuild_env(c, [0, 1])
        c.set(E.gx + GX_MODES, p8(combat))
        E.nolog(c)
        for s in (0, 1):
            c.set(E.xrow(s) + X_BOUND, p8(0))
        c.cap(E.gs + GS_BIND_CLOCK, GS_INFATUATION + 1 - GS_BIND_CLOCK, 'status_flags')
        W.cap_states()
        c.cap(E.xbase, 2 * XROW, 'xchar01', ignore=[0x19, 0x39, XROW + 0x19, XROW + 0x39])
        c.cap(E.char(0), 2 * CHAR, 'chars01', floats=CHAR_FLOATS + [CHAR + o for o in CHAR_FLOATS])
        c.note(level=level, band=band, combat=combat, surprise=surprise, infatuation=infat,
               flagged=flagged, pending=pend, clock_delta=d, rows=rows,
               names=[st['name_style'] for st in sts], services=[x[0] for x in sid_rows])
        if level == 47:
            c.note(edge='level47')


def t_departure(ctx, E):
    fn = ctx.fn(0x0050dec0)  # bool QueueNpcDepartureEvents(int destination_level)
    for i in range(ctx.n(200)):
        r = ctx.rng('departure', i)
        c = ctx.case('departure.%d' % i, fn, conv='c', ret='b')
        W = World(ctx, E, c)
        x = r.random()
        if x < 0.15:
            level, band, f5b, f1ce = E.level(c, r, level=0x10, f5b=1)      # band 13
        elif x < 0.65:
            level, band, f5b, f1ce = E.level(c, r, level=level_for_band(r, r.choice(SERVICE_BANDS)))
        else:
            level, band, f5b, f1ce = E.level(c, r)
        dest = level_for_band(r, r.choice(SERVICE_BANDS)) if r.random() < 0.7 else pick_level(r)
        dband = band_of(dest, f5b, f1ce)
        names = None
        if band == 0xd and r.random() < 0.6:
            names = [r.choice([NPC_RODAN, NPC_DRAZIC, 0x07]), r.choice([NPC_RODAN, NPC_DRAZIC, 0x07])]

        def flags_fn(rr):
            """service flags tuned to the destination and current bands"""
            fl = 0
            if dband in SERVICE_BIT and rr.random() < 0.6:
                fl |= SERVICE_BIT[dband]
            if band in SERVICE_BIT and rr.random() < 0.4:
                fl |= SERVICE_BIT[band]
            if rr.random() < 0.3:
                fl |= rr.getrandbits(14)
            return fl
        sts, rows = bound_rows(ctx, E, c, r, W, names=names, flags_fn=flags_fn)
        W.vector([W.put(st) for st in sts])
        set_rows(c, E, rows)
        E.mute_events(c)
        count = E.redirect_messages(c)
        c.setp(E.level_data, E.S[6])
        flags = r.choice([0, 1, 0x40, 0x100, 0x141, 0x3ff, r.getrandbits(10)])
        c.set(E.S[6], p32(flags))
        c.arg(dest)
        c.cap(count, 4, 'message_count')
        c.cap(E.S[6], 0xf4, 'level_data')
        c.note(level=level, band=band, dest=dest, dest_band=dband, rows=rows,
               names=[st['name_style'] for st in sts], level_flags=flags)
        if level == 47 or dest == 47:
            c.note(edge='level47')


def t_bound_penalty(ctx, E):
    fn = ctx.fn(0x0050dbf0)  # void ApplyBoundNpcPenalty(W8Character*, W8GameplayModifierBlock*)
    for i in range(ctx.n(150)):
        r = ctx.rng('boundpenalty', i)
        c = ctx.case('boundpenalty.%d' % i, fn, conv='c', ret='v')
        s = r.randrange(8)
        ctx.set_party(c, r, slots=[s])
        inparty = 1 if r.random() < 0.92 else 0
        c.set(E.char(s) + C_INPARTY, p8(inparty))
        target_char = r.random() < 0.05
        ch = E.char(s)
        if target_char:
            blob, _ = ctx.pick_char(r)
            c.setb(E.S[5], bytes(blob))
            ch = E.S[5]
            c.set(ch + C_INPARTY, b'\x01')
        bound = r.choice([0, 1, 1, 1, 2, 0x80])
        bound0 = r.choice([0, 1])
        c.set(E.xrow(s) + X_BOUND, p8(bound))
        if s != 0:
            c.set(E.xrow(0) + X_BOUND, p8(bound0))
        if r.random() < 0.6:
            target = E.S[4] + 0x400
            c.set(target, bytes(r.getrandbits(8) for _ in range(MODBLOCK)))
            tname = 'scratch'
        else:
            target = ch + C_BONUS
            tname = 'own_bonus'
        c.arg(ch)
        c.arg(target)
        c.cap(target, MODBLOCK, 'target')
        c.note(slot=s, in_party=inparty, scratch_char=target_char, bound=bound, target=tname)


# ----------------------------------------------------------------------------- interaction / theft
def party_basic(ctx, E, c, r, slots=range(8), ensure_eligible=True):
    """occupancy / hp / highest condition of party rows; returns eligibility list."""
    elig = []
    rows = []
    for s in slots:
        occ = bbyte(r, 0.8, 0.04)
        hp = hpv(r, 0.1)
        hc = condv(r, edge=0.03)
        rows.append([s, occ, hp, hc])
    if ensure_eligible and not any(o and h and (h & 0xffffffff) and c_ < 0xd for _, o, h, c_ in rows):
        rows[r.randrange(len(rows))][1:] = [1, r.randrange(1, 300), 0]
    for s, occ, hp, hc in rows:
        c.set(E.xrow(s) + X_OCC, p8(occ))
        c.set(E.char(s) + C_HP, p32(hp))
        c.set(E.char(s) + C_HCOND, p32(hc))
        elig.append(bool(occ and hp and hc < 0xd))
    return rows


def skill_level_edges(r):
    return r.choice([0, 1, 4, 5, 9, 10, 25, 50, 75, 99, 100, 101, 125, 0x7fffffff, 0x80000000,
                     0xffffffff, r.randrange(0, 101)])


def mon_rec_npc(r):
    return (1, r.randrange(146), r.choice([0, 1, 2, 5, 8, 10, 15, 20, 30, 50, 255]))


def t_interaction(ctx, E):
    fn = ctx.fn(0x0050a570)  # void ApplyNpcInteraction(W8NpcState*, int kind, int value, W8ItemInstance*, unsigned gold)
    for i in range(ctx.n(400)):
        r = ctx.rng('interaction', i)
        c = ctx.case('interaction.%d' % i, fn, conv='c', ret='v')
        W = World(ctx, E, c)
        base = r.choice([0] * 5 + [1] * 6 + [2] * 5 + [3] * 5 + [4] * 3 + ['other'])
        if base == 'other':
            kind = r.choice([5, 6, 7, 0x7f, -1, -0x80, 0x80, 0xff])
        else:
            kind = base
            if r.random() < 0.1:
                kind = base | r.choice([0x100, 0x7fffff00, 0xffffff00])
        k8 = kind & 0xff
        ctx.set_party(c, r)
        rows = party_basic(ctx, E, c, r)
        for s in r.sample(range(8), r.choice([1, 2, 3])):
            c.set(E.char(s) + C_SKILL + SK_COMM * SKILL_STEP + 6, p32(skill_level_edges(r)))
        E.practice_env(c)
        E.nolog(c)
        clock = r.getrandbits(32)
        c.set(E.gs + GS_CLOCK, p32(clock))
        st = St()
        scale_t = r.choice([0, 1, -1, 4, 5, -5, 10, -10, 25, 99, -100, 127, -128, r.randrange(-20, 21)])
        scale_c = r.choice([0, 1, -1, 4, 5, -5, 10, -10, 25, 99, -100, 127, -128, r.randrange(-20, 21)])
        ns = r.randrange(E.nrec)       # g_npc_records[name_style].trade_pool refills the pool
        st['name_style'] = ns
        st['trade_pool'] = r.choice([0, 1, 2, 50, 100, 300, 1000, 0x7fff, 0x8000, 0xffff, r.randrange(3000)])
        need_mon = k8 == 1             # the charm path reads the monster record unconditionally
        st, info = disp_world(ctx, E, c, r, W, monster='always' if need_mon else 'maybe',
                              allied=False, st=st, mon_rec=mon_rec_npc, max_monsters=2,
                              notfound_p=0.0 if need_mon else 0.05, scales=(scale_c, scale_t))
        a = W.put(st)
        value = r.randrange(8) if k8 == 1 else r.choice([0, 3, 7, -1, 100])
        gold = r.choice([0, 1, 5, 50, 299, 300, 1000, 0xffff, 0x10000, 0x12345, 0x7fffffff,
                         0xffffffff, r.randrange(5000), 0x7f, 0x80, 0xff, 0x9c, 0x1e])
        pg = r.choice([0, gold, gold - 1 if gold else 0, gold + 1, r.getrandbits(32), 1000000])
        c.set(E.gs + GS_GOLD, p32(pg))
        iid = E.item(r)
        stack = r.choice([0, 1, 2, 10, 99, 255])
        put_item(c, E.S[4], iid, stack=stack)
        notes = item_value_edges(c, E, r, iid) if k8 == 3 else {}
        c.arg(a)
        c.arg(kind & 0xffffffff)
        c.arg(value & 0xffffffff)
        c.arg(E.S[4] if r.random() < 0.9 or k8 == 3 else 0)
        c.arg(gold & 0xffffffff)
        W.cap_states()
        c.cap(E.gs + GS_GOLD, 4, 'party_gold')
        c.cap(E.char(0), 8 * CHAR, 'chars', floats=[s * CHAR + o for s in range(8) for o in CHAR_FLOATS])
        E.practice_caps(c)
        c.note(kind=kind, value=value, gold=gold, party_gold=pg, talk_scale=scale_t,
               charm_scale=scale_c, name_style=ns, trade_pool=st['trade_pool'], item=iid,
               rows=rows, **dict(info, **notes))


def theft_world(ctx, E, c, r, W, slot, need_monster=True):
    """Thief in party slot `slot`; NPC with a found monster (record level) and the
    disposition inputs; difficulty set."""
    ch = E.char(slot)
    c.set(ch + C_INPARTY, b'\x01')
    prof = 7 if r.random() < 0.4 else r.randrange(15)
    c.set(ch + C_PROF, p32(prof))
    pick = skill_level_edges(r) if r.random() < 0.3 else r.randrange(0, 101)
    c.set(ch + C_SKILL + SK_PICK * SKILL_STEP + 6, p32(pick))
    dex = r.choice([0, 1, 9, 10, 19, 20, 50, 99, 100, 125, 0xffffffff]) if r.random() < 0.3 else r.randrange(1, 126)
    c.set(ch + C_ATTR + A_DEX * ATTR_STEP + 4, p32(dex))
    lvl = r.choice([0, 1, 2, 5, 50, 255, 0x80000000, 0xffffffff]) if r.random() < 0.15 else r.randrange(1, 31)
    c.set(ch + C_LEVEL, p32(lvl))
    turn = r.choice([0, 0, 0, 1, 3])
    c.set(ch + COND_TURNCOAT_OFF, p32(turn))
    diff = r.choice([0, 1, 2, 3, 1, 2])
    c.set(E.settings + SET_DIFFICULTY, p32(diff))
    st = St()
    susp = r.choice([0, 0, 1, 2, 5, 10, 50, 99, 100, 101, 0x7f]) if r.random() < 0.9 else r.choice([0x80, 0xff, 0xc0])
    st['suspicion'] = susp
    st, info = disp_world(ctx, E, c, r, W, monster='always', allied=False, st=st, mon_rec=mon_rec_npc,
                          notfound_p=0.0, faction_p=0.3)
    info.update(prof=prof, pickpocket=pick, dex=dex, level=lvl, turncoat=turn, difficulty=diff,
                suspicion=susp)
    return st, info


def theft_item(r, E):
    x = r.random()
    if x < 0.2:
        return -1, 0
    iid = E.item(r)
    count = r.choice([0, 1, 1, 2, 5, 10, 50, 100, 255]) if r.random() < 0.85 else r.choice([256, 257, 300, 1000, -1])
    return iid, count


def t_score_theft(ctx, E):
    fn = ctx.fn(0x0050baf0)  # char ScoreNpcTheft(W8Character*, W8NpcState*, int item_id, int count)
    for i in range(ctx.n(400)):
        r = ctx.rng('scoretheft', i)
        c = ctx.case('scoretheft.%d' % i, fn, conv='c', ret='u8')
        W = World(ctx, E, c)
        slot = r.randrange(8)
        ctx.set_party(c, r, slots=[slot])
        st, info = theft_world(ctx, E, c, r, W, slot)
        E.nolog(c)
        a = W.put(st)
        iid, count = theft_item(r, E)
        notes = {}
        if iid >= 0:
            if r.random() < 0.3:
                w = r.choice([0, 1, 10, 100, 1000, 0x7fff, 0xffff])
                c.set(E.irec(iid, I_WEIGHT), p16(w))
                notes['weight'] = w
            notes.update(item_value_edges(c, E, r, iid))
        c.arg(E.char(slot))
        c.arg(a)
        c.arg(iid & 0xffffffff)
        c.arg(count & 0xffffffff)
        c.note(slot=slot, item=iid, count=count, **dict(info, **notes))


def seed_party(ctx, E, c, r):
    """Slots 2..7 occupancy feeds SeedNpcTheftRoll (sum of their experience)."""
    for s in range(2, 8):
        c.set(E.xrow(s) + X_OCC, p8(bbyte(r, 0.75, 0.04)))


def theft_spins_ok(slot, st):
    susp = st['suspicion']
    susp = susp - 256 if susp >= 128 else susp
    return slot + st['name_style'] * 11 + susp * 7 >= 0


def t_pickpocket(ctx, E):
    fn = ctx.fn(0x0050bc90)  # W8NpcPickpocketResult AttemptNpcPickpocket(W8Character*, W8NpcState*, W8ItemInstance*, unsigned*)
    for i in range(ctx.n(300)):
        r = ctx.rng('pickpocket', i)
        c = ctx.case('pickpocket.%d' % i, fn, conv='c', ret='u8')
        W = World(ctx, E, c)
        slot = r.randrange(8)
        ctx.set_party(c, r)
        seed_party(ctx, E, c, r)
        st, info = theft_world(ctx, E, c, r, W, slot)
        st['name_style'] = r.randrange(146)
        if not theft_spins_ok(slot, st):
            st['name_style'] = 0x60
        x = r.random()
        ids = []
        for k in range(40):
            y = r.random()
            if x < 0.15:
                ids.append(-1)
            elif y < 0.5:
                ids.append(-1)
            elif y < 0.6:
                ids.append(r.choice([0x242, 0x243, 0x244]))
            else:
                ids.append(E.item(r))
        st.item_ids(ids)
        st['gold'] = r.choice([0, 0, 1, 50, 100, 693, 694, 700, 10000, 0x7fffffff, 0x80000000, 0xffffffff])
        E.practice_env(c)
        E.nolog(c)
        a = W.put(st)
        out = E.S[4] + 0x100 if r.random() < 0.85 else 0
        c.set(E.S[4] + 0x200, p32(0xdeadbeef))
        c.arg(E.char(slot))
        c.arg(a)
        c.arg(out)
        c.arg(E.S[4] + 0x200)
        W.cap_states()
        c.cap(E.S[4] + 0x100, 0xc, 'item_out')
        c.cap(E.S[4] + 0x200, 4, 'gold_out')
        c.cap(E.char(0), 8 * CHAR, 'chars', floats=[s * CHAR + o for s in range(8) for o in CHAR_FLOATS])
        E.practice_caps(c)
        c.note(slot=slot, name_style=st['name_style'], gold=st['gold'],
               candidates=sum(1 for v in ids if v != -1 and v not in (0x242, 0x243, 0x244)),
               item_out=bool(out), **info)


def t_item_theft(ctx, E):
    fn = ctx.fn(0x0050c040)  # char AttemptNpcItemTheft(W8Character*, W8NpcState*, int item_id, int count)
    for i in range(ctx.n(300)):
        r = ctx.rng('itemtheft', i)
        c = ctx.case('itemtheft.%d' % i, fn, conv='c', ret='u8')
        W = World(ctx, E, c)
        slot = r.randrange(8)
        ctx.set_party(c, r)
        seed_party(ctx, E, c, r)
        st, info = theft_world(ctx, E, c, r, W, slot)
        st['name_style'] = r.randrange(146)
        if not theft_spins_ok(slot, st):
            st['name_style'] = 0x60
        E.practice_env(c)
        E.nolog(c)
        a = W.put(st)
        iid, count = theft_item(r, E)
        if r.random() < 0.25:
            count = r.choice([256, 257, 300, 511, 1000, 0x10001, -1, -255])   # retail passes count & 0xff
        c.arg(E.char(slot))
        c.arg(a)
        c.arg(iid & 0xffffffff)
        c.arg(count & 0xffffffff)
        W.cap_states()
        c.cap(E.char(0), 8 * CHAR, 'chars', floats=[s * CHAR + o for s in range(8) for o in CHAR_FLOATS])
        E.practice_caps(c)
        c.note(slot=slot, item=iid, count=count, name_style=st['name_style'], **info)
        if count > 255 or count < 0:
            c.note(edge='count_over_byte')


# ----------------------------------------------------------------------------- item id lists
def t_scheduled_item(ctx, E):
    clr = ctx.fn(0x0050ba80)   # bool ClearNpcScheduledItem(W8NpcState*, int item_id, W8ItemInstance* out)
    clr2 = ctx.fn(0x0050e4b0)  # void ClearNpcItemId(W8NpcState*, int item_id)
    for kind, fn, count in (('clearscheduled', clr, 200), ('clearitemid', clr2, 150)):
        for i in range(ctx.n(count)):
            r = ctx.rng(kind, i)
            c = ctx.case('%s.%d' % (kind, i), fn, conv='c', ret='b' if kind == 'clearscheduled' else 'v')
            W = World(ctx, E, c)
            pool = [E.item(r) for _ in range(r.choice([1, 2, 3, 6]))]
            ids = [r.choice(pool) if r.random() < 0.5 else -1 for _ in range(40)]
            if r.random() < 0.1:
                ids = [-1] * 40
            st = St()
            st.item_ids(ids)
            a = W.put(st)
            out = 0
            if kind == 'clearscheduled' and r.random() < 0.7:
                out = E.S[4] + 0x100
                c.set(out, bytes(r.getrandbits(8) for _ in range(12)))
            x = r.random()
            if x < 0.6:
                iid = r.choice(pool)
            elif x < 0.75 and not out:
                iid = -1
            else:
                iid = r.choice([E.item(r), 0x10000 + pool[0], 0xffff, -0x10000 + pool[0]])
                if out and (iid < 0 or iid >= E.nitems) and (iid & 0xffff) in [v & 0xffff for v in ids]:
                    iid = pool[0]
            c.arg(a)
            c.arg(iid & 0xffffffff)
            if kind == 'clearscheduled':
                c.arg(out)
            W.cap_states()
            if out:
                c.cap(out, 12, 'out')
            c.note(item=iid, out=bool(out), matches=sum(1 for v in ids if v == iid))


# ----------------------------------------------------------------------------- driver
GENERATORS = [
    t_trade_pool, t_disposition, t_disposition_band, t_set_band, t_resume, t_topics, t_facts,
    t_get_state, t_by_kind, t_lead_name_style, t_monster_info, t_group_lookup, t_will_trade,
    t_count_leading, t_wants_item, t_offers_service, t_can_join, t_display_name, t_find_by_name,
    t_timers, t_start_location, t_start_level, t_init_character, t_release_binding,
    t_monster_binding_lookup, t_release_monster_bindings, t_release_monster_binding,
    t_release_by_kind, t_restore_named, t_clear_pending_levels, t_marked_event, t_release_marked,
    t_reset_bindings, t_pending_events, t_departure, t_bound_penalty, t_interaction,
    t_score_theft, t_pickpocket, t_item_theft, t_scheduled_item,
]

MAX_OPS = 96                  # W8D_MAX_OPS in w8diff_core.c


class _AnyBlob(dict):
    def __getitem__(self, k):
        return 0


def _check_ops(cases):
    """Every case must fit the core's per-case operation table (extra lines are dropped
    silently by the core)."""
    blobs = _AnyBlob()
    for c in cases:
        text = c.render('retail', blobs)
        n = sum(1 for line in text.split('\n')
                if line.split(' ', 1)[0] in ('set', 'setb', 'setp', 'fill', 'keep', 'cap', 'dump'))
        if n > MAX_OPS:
            raise ValueError('%s: %d operations > %d' % (c.id, n, MAX_OPS))


def cases(ctx):
    E = Env(ctx)
    first = len(ctx.cases)
    for g in GENERATORS:
        g(ctx, E)
    _check_ops(ctx.cases[first:])
