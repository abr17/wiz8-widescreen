"""UtilityFunctions.cpp (src/wiz8/local_code/UtilityFunctions.cpp): every recovered
function of the file that is game logic or a pure helper.

Tested (retail address, name, cases):
  0x00517950 SetDice                          120  dice in S0 between 0xcc guards; count/sides
                                                   bytes and base short, 15% with garbage high
                                                   bits in the argument dwords (retail reads
                                                   only the low byte / word)
  0x00517970 RollDice                         250  seeded Random(sides); count 0..255, sides 0
                                                   (Random(0) = 0) .. 255, base -32768..32767
                                                   (port symbol given: RollDice is overloaded)
  0x005179b0 IntegerPower                     200  signed overflow, exponent up to 100000
  0x005179d0 ClampInteger                     200  signed, INT_MIN/INT_MAX, min > max
  0x005179f0 ClampUnsignedInteger             200  unsigned, 0/0xffffffff, min > max
  0x00517a10 CompareUnsignedDescending        150  same pointer twice in 5%
  0x00517a30 CompareSignedAscending           150
  0x00517a50 CompareSignedDescending          150
  0x00517a70 FormatString                     260  every narrow format string the port passes
                                                   to FormatString + generic printf specifiers
                                                   (%u %x %08X %#x %o %hd %*d %.*s %I64d %S %ls
                                                   %hs %C %c, a few non-tie %f); string args in
                                                   S1, g_format_string_buffer pre-filled 0xcc and
                                                   captured (200 bytes); outputs < 190 chars
  0x00517a90 FormatWideString                 260  every wide format string the port uses +
                                                   generic ones (%s wide, %S/%hs narrow, %c/%C);
                                                   g_wide_string_buffer pre-filled, 0x400 captured
  0x00517ab0 ConvertStringToWide              160  L"%hs": ASCII, empty, long, bytes 0x80..0xff
  0x00517ad0 ConvertWideStringToString        160  "%ls": ASCII, Latin-1, chars > 0xff (wctomb
                                                   fails in the C locale)
  0x00517af0 FormatUnsignedIntegerWithCommas  300  every group boundary 10^k-1/10^k/10^k+1,
                                                   zero middle groups, 2^31, 2^32-1
  0x00517bd0 TitleCaseString                  250  all separator characters of the switch,
                                                   digits, mixed case, 8% with bytes >= 0x80
                                                   (signed char passed to toupper/tolower)
  0x00517c60 NormalizeAngle                   300  |angle| <= ~1e4 only: NaN/inf/huge values
                                                   loop forever in retail; neighbours of 0 and
                                                   +-2pi (float constant 6.2831850)
  0x00517ce0 ShortestAngleDistance            300  pairs in [0,2pi), [-pi,pi), equal, pi apart
  0x00517e20 UnionScreenRects                 200  signed extremes; 12% result aliases an input
  0x00517e70 ScreenPointInRect                250  points on every edge, inverted rects, null
                                                   rect / point pointers
  0x00517ea0 StripMonsterNameSuffix           120  '#' first/last/several/none, non-ASCII
  0x00517ec0 CharacterPointerToPartySlot      150  party pointers 0..7, fInParty 0/1/2/0xff
                                                   (assert 0x1c8), interior pointers and a copy
                                                   in scratch (assert 0x1d1, returns 0)
  0x00517f30 IsPartyCharacterPointer          150  no dereference: also null, one-past-end,
                                                   before-start, unrelated globals
  0x00517f60 AdjustByteByPercent              250  percent -100..300 and 32-bit wrap values
  0x00517f90 AdjustIntegerByPercent           250  value*percent overflow (low 32 bits)
  0x00517fb0 GetRandomPartySlots              400  XChar fOccupied, hp_current,
                                                   highest_condition of 8 slots; requirement
                                                   relaxation (1 -> 2), count 0..8/9/100/-1,
                                                   excluded slot, skip_first_two; seeded Random;
                                                   selected[] in S0 pre-filled 0xee (0x40 bytes)
  0x00518150 GetRandomCharacter               350  + gender and excluded_gender (signed char,
                                                   -1 = any, 0x80, garbage high bits)
  0x00518230 GetNextCharacter                 300  previous_slot -1..15, -9, -17, 0x7fffffff
                                                   (only values whose (prev+1)%8 >= 0: a
                                                   negative start slot reads XChar[-n])
  0x00518310 RPCPtrToPCSlot                   120  gXStatus.monster_manager_entries[0..7] and
                                                   non-matching pointers (assert 0x385)
  0x00518900 MessageBoxAcceptClickCallback    120  GUI_BUTTON in S0 (uiFlags +0x60), reason
                                                   bits 4/8 and others; state/accepted captured
  0x00518970 MessageBoxCancelClickCallback    120  same
  0x005187e0 CloseMessageBox                   60  all six button/image handles set to -1, so
                                                   state 2 only flips the state latch (no
                                                   button/image calls)
  0x005189b0 RenderMessageBox                 100  states 0/1/3/other only (state 2 renders);
                                                   handles -1; callback = IsMessageBoxActive
                                                   (pure getter) or null; accepted 2/0xff edge
                                                   (retail compares accepted == 1)
  Total 6350 cases.

  Party state (GetRandomPartySlots / GetRandomCharacter / GetNextCharacter): retail
  compares highest_condition unsigned (jb 0x12 / jb 0x0f) and hp_current as unsigned
  non-zero; the port's W8Condition is a signed enum. At most one slot per case gets
  highest_condition 0x80000000/0xffffffff/0xfffffff0 (10% of the cases; note
  edge='cond_negative' only when that slot is occupied) and at most one a fOccupied byte
  2/0x80/0xff (edge='bool_byte').
  Modes all-unoccupied / all-dead / all-asleep / exactly-one-eligible exercise the
  require_* relaxation and the -1 result.

Skipped:
  0x005182e0 FormatDebugMessage           - formats into a local stack buffer and drops it:
                                            no observable effect
  0x005184b0 FreeStringTable              - frees the game's heap string table (deletion)
  0x00518510 CreateMessageBox             - creates buttons, loads images, invalidates the
                                            screen (UI)
  0x005188c0 MessageBoxAcceptMoveCallback - only effect is GetButtonArea + InvalidateRegion
                                            (UI redraw)
  0x00518930 MessageBoxCancelMoveCallback - same
  0x00518b20 IsMessageBoxActive           - trivial getter (state != 0); used as the
                                            callback in the RenderMessageBox cases
  0x00518b30 ProcessMessageBoxInput       - input queue (DequeueEvent, mouse hooks)
"""
import struct

from w8diff.api import F32, F64

# W8Character (layout.ps1 = retail asm)
C_IN_PARTY = 0x04
C_GENDER = 0x75
C_HCOND = 0xb01
C_HP = 0xb11
CHAR = 0x1862

# W8PartySlotRow (g_status.buffers.XChar, heap, 0x106 per slot)
XROW = 0x106
X_OCC = 0x00

# gXStatus.monster_manager_entries (offset 0, W8MonsterManagerEntry 0x118, 8 entries)
GX_ENTRY = 0x118

# GUI_BUTTON
BTN_FLAGS = 0x60
BUTTON_CLICKED_ON = 0x2

COND_ASLEEP = 0x0f
COND_DEAD = 0x12

FMT_BUF_LEN = 200       # g_format_string_buffer
WIDE_CAP = 0x400        # captured part of g_wide_string_buffer (4096 wchar_t)

INT_MIN = -0x80000000
INT_MAX = 0x7fffffff

TWO_PI_BITS = 0x40c90fda   # float 6.2831852f at retail 0x5ec014


def u32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def u8(v):
    return bytes([int(v) & 0xff])


def s32(v):
    v = int(v) & 0xffffffff
    return v - (1 << 32) if v >= (1 << 31) else v


def cstr(b):
    return bytes(b) + b'\0'


def wstr(s):
    return s.encode('utf-16-le') + b'\0\0'


def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


def f32_bits(bits):
    return struct.unpack('<f', struct.pack('<I', bits & 0xffffffff))[0]


def f32_step(x, k):
    """Float k ULPs away from float(x) (towards +inf for k > 0)."""
    b = struct.unpack('<i', struct.pack('<f', x))[0]
    if b < 0:
        b = -0x80000000 - b          # map negative floats onto a monotonic integer line
    b += k
    if b < 0:
        b = -0x80000000 - b
    return struct.unpack('<f', struct.pack('<i', b))[0]


TWO_PI = f32_bits(TWO_PI_BITS)


# --------------------------------------------------------------------------------------
# string pools
NARROW_WORDS = [b'Sword', b'Long Sword', b'Bayjin Shallows', b'Rattkin', b'Vi Domina', b'RFS-81',
                b'Trynton', b"Marten's Bluff", b'Higardi', b'Umpani', b'Dane', b'Arnika',
                b'Lucky Coin', b'Swamp Tunnels', b'Northern Wilderness', b'cube001', b'a', b'',
                b'Data\\Monsters\\Rattkin.MON', b'Savant Trooper', b'IDLE', b'ATTACK1', b'x',
                b'Potion of Cure Lesser Cnd', b'Bayjin', b'Mount Gigas', b'Ghost Town',
                b'abcdefghijklmnopqrstuvwxyz0123', b'  spaced  out  ', b'50% off', b'tab\there']
NARROW_HIGH = [b'Caf\xe9', b'\xc0\xc1\xc2\xd0\xdf', b'\xd0\xe0\xf2\xea\xe8\xed',
               b'\x80\x81\x9f', b'\xff\xfe', b'\xa0\xa9\xae', b'M\xfcller', b'\xc4\xd6\xdc\xe4']
WIDE_WORDS = ['Sword', 'Long Sword', 'Bayjin Shallows', 'Rattkin', 'Vi Domina', 'RFS-81',
              'Trynton', "Marten's Bluff", 'Higardi', 'Umpani', 'Dane', 'Arnika', 'Lucky Coin',
              'Swamp Tunnels', 'Northern Wilderness', 'a', '', 'Savant Trooper', 'x',
              'Potion of Cure Lesser Cnd', 'Ghost Town', 'abcdefghijklmnopqrstuvwxyz0123',
              '100%', 'two  spaces']
WIDE_LATIN1 = ['Café', 'Müller', 'naïve', 'Àÿ ', '\u0080\u009f']
WIDE_OTHER = ['Раткин', '€100', 'ÿĀ',
              '日本', 'AЖB']


def _narrow(r, high_p=0.08, short=False):
    if r.random() < high_p:
        return r.choice(NARROW_HIGH), 'high_byte'
    pool = [w for w in NARROW_WORDS if len(w) <= 12] if short else NARROW_WORDS
    return r.choice(pool), None


def _wide(r, other_p=0.08, short=False):
    x = r.random()
    if x < other_p / 2:
        return r.choice(WIDE_LATIN1), 'latin1'
    if x < other_p:
        return r.choice(WIDE_OTHER), 'non_latin1'
    pool = [w for w in WIDE_WORDS if len(w) <= 12] if short else WIDE_WORDS
    return r.choice(pool), None


# --------------------------------------------------------------------------------------
def cases(ctx):
    _set_dice(ctx)
    _roll_dice(ctx)
    _integer_power(ctx)
    _clamp_integer(ctx)
    _clamp_unsigned(ctx)
    _compare(ctx)
    _format_string(ctx)
    _format_wide_string(ctx)
    _convert_to_wide(ctx)
    _convert_to_narrow(ctx)
    _format_commas(ctx)
    _title_case(ctx)
    _normalize_angle(ctx)
    _shortest_angle(ctx)
    _union_rects(ctx)
    _point_in_rect(ctx)
    _strip_suffix(ctx)
    _char_ptr_to_slot(ctx)
    _is_party_ptr(ctx)
    _adjust_byte(ctx)
    _adjust_int(ctx)
    _random_party_slots(ctx)
    _random_character(ctx)
    _next_character(ctx)
    _rpc_ptr_to_slot(ctx)
    _msgbox_click(ctx)
    _close_msgbox(ctx)
    _render_msgbox(ctx)


# --------------------------------------------------------------------------------------
def _set_dice(ctx):
    """void SetDice(W8Dice*, unsigned char count, unsigned char sides, short base)"""
    fn = ctx.fn(0x00517950)
    s0 = ctx.scratch(0)
    bytes_ = [0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 20, 100, 127, 128, 200, 255]
    bases = [-32768, -32767, -100, -1, 0, 1, 2, 5, 10, 100, 1000, 32766, 32767]
    for i in range(ctx.n(120)):
        r = ctx.rng('setdice', i)
        c = ctx.case('setdice.%d' % i, fn, conv='c', ret='v')
        count = r.choice(bytes_) if r.random() < 0.6 else r.randrange(256)
        sides = r.choice(bytes_) if r.random() < 0.6 else r.randrange(256)
        base = r.choice(bases) if r.random() < 0.5 else r.randrange(-200, 201)
        a_count, a_sides, a_base = count, sides, base & 0xffffffff
        high = r.random() < 0.15
        if high:
            a_count |= r.getrandbits(24) << 8
            a_sides |= r.getrandbits(24) << 8
            a_base = (base & 0xffff) | (r.getrandbits(16) << 16)
            c.note(edge='high_bits')
        c.fill(s0, 0x10, 0xcc)
        c.arg(s0 + 4)
        c.arg(a_count)
        c.arg(a_sides)
        c.arg(a_base)
        c.cap(s0, 0x10, 'dice')
        c.note(count=count, sides=sides, base=base)


def _roll_dice(ctx):
    """int RollDice(const W8Dice*): base + sum of count x (Random(sides) + 1)."""
    fn = ctx.fn(0x00517970, '?RollDice@@YAHPBUW8Dice@@@Z')
    s0 = ctx.scratch(0)
    for i in range(ctx.n(250)):
        r = ctx.rng('rolldice', i)
        c = ctx.case('rolldice.%d' % i, fn, conv='c', ret='i')
        count = r.choice([0, 1, 50, 100, 200, 255]) if r.random() < 0.15 else r.randrange(0, 11)
        sides = r.choice([0, 1, 100, 255]) if r.random() < 0.1 else \
            r.choice([2, 3, 4, 6, 8, 10, 12, 20, r.randrange(1, 30)])
        base = r.choice([-32768, -1, 32767, 1000, -1000]) if r.random() < 0.1 else r.randrange(-5, 21)
        c.set(s0, struct.pack('<hBB', base, count, sides))
        c.arg(s0)
        c.cap(s0, 8, 'dice')
        c.note(count=count, sides=sides, base=base)


def _integer_power(ctx):
    """int IntegerPower(int base, unsigned int exponent)"""
    fn = ctx.fn(0x005179b0)
    bases = [0, 1, -1, 2, -2, 3, -3, 10, -10, 7, 16, 1000, 65536, 46341, INT_MAX, INT_MIN]
    for i in range(ctx.n(200)):
        r = ctx.rng('intpow', i)
        c = ctx.case('integerpower.%d' % i, fn, conv='c', ret='i')
        base = r.choice(bases) if r.random() < 0.5 else r.randrange(-50, 51)
        x = r.random()
        if x < 0.05:
            exp = r.choice([1000, 4096, 65535, 100000])
        elif x < 0.3:
            exp = r.choice([0, 1, 2, 15, 16, 30, 31, 32, 33, 63, 64, 100])
        else:
            exp = r.randrange(0, 13)
        c.arg(base)
        c.arg(exp)
        c.note(base=base, exp=exp)


def _clamp_values(r, signed):
    if signed:
        edge = [INT_MIN, INT_MIN + 1, -1000, -1, 0, 1, 100, 1000, INT_MAX - 1, INT_MAX]
        rnd = lambda: r.randrange(-200, 201)   # noqa: E731
    else:
        edge = [0, 1, 2, 100, 1000, 0x7fffffff, 0x80000000, 0x80000001, 0xfffffffe, 0xffffffff]
        rnd = lambda: r.randrange(0, 301)      # noqa: E731
    lo = r.choice(edge) if r.random() < 0.2 else rnd()
    hi = r.choice(edge) if r.random() < 0.2 else rnd()
    if r.random() < 0.85 and (lo > hi):
        lo, hi = hi, lo                         # mostly ordered, 15% maybe inverted
    x = r.random()
    if x < 0.25:
        v = r.choice([lo, hi, lo - 1, hi + 1, lo + 1, hi - 1])
    elif x < 0.4:
        v = r.choice(edge)
    else:
        v = rnd()
    return v, lo, hi


def _clamp_integer(ctx):
    """void ClampInteger(int* value, int minimum, int maximum)"""
    fn = ctx.fn(0x005179d0)
    s0 = ctx.scratch(0)
    for i in range(ctx.n(200)):
        r = ctx.rng('clampint', i)
        c = ctx.case('clampinteger.%d' % i, fn, conv='c', ret='v')
        v, lo, hi = _clamp_values(r, True)
        c.set(s0, u32(0xa5a5a5a5) + u32(v) + u32(0x5a5a5a5a))
        c.arg(s0 + 4)
        c.arg(lo)
        c.arg(hi)
        c.cap(s0, 12, 'value')
        c.note(value=s32(v), min=s32(lo), max=s32(hi))


def _clamp_unsigned(ctx):
    """void ClampUnsignedInteger(unsigned int* value, unsigned int minimum, unsigned int maximum)"""
    fn = ctx.fn(0x005179f0)
    s0 = ctx.scratch(0)
    for i in range(ctx.n(200)):
        r = ctx.rng('clampuint', i)
        c = ctx.case('clampunsigned.%d' % i, fn, conv='c', ret='v')
        v, lo, hi = _clamp_values(r, False)
        c.set(s0, u32(0xa5a5a5a5) + u32(v) + u32(0x5a5a5a5a))
        c.arg(s0 + 4)
        c.arg(lo)
        c.arg(hi)
        c.cap(s0, 12, 'value')
        c.note(value=v & 0xffffffff, min=lo & 0xffffffff, max=hi & 0xffffffff)


def _compare(ctx):
    """qsort comparators: int (*)(const void*, const void*) on 32-bit values."""
    s0 = ctx.scratch(0)
    edge = [0, 1, 2, 0xffffffff, 0xfffffffe, 0x7fffffff, 0x80000000, 0x80000001, 100, 0xffffff9c]
    for addr, key in ((0x00517a10, 'cmpudesc'), (0x00517a30, 'cmpsasc'), (0x00517a50, 'cmpsdesc')):
        fn = ctx.fn(addr)
        for i in range(ctx.n(150)):
            r = ctx.rng(key, i)
            c = ctx.case('%s.%d' % (key, i), fn, conv='c', ret='i')
            a = r.choice(edge) if r.random() < 0.35 else r.randrange(0, 50)
            x = r.random()
            if x < 0.2:
                b = a
            elif x < 0.5:
                b = r.choice(edge)
            elif x < 0.7:
                b = (a + r.choice([1, -1])) & 0xffffffff
            else:
                b = r.getrandbits(32) if r.random() < 0.3 else r.randrange(0, 50)
            same = r.random() < 0.05
            c.set(s0, u32(a) + u32(b))
            c.arg(s0)
            c.arg(s0 if same else s0 + 4)
            c.note(a=a, b=a if same else b, same=int(same))


# --------------------------------------------------------------------------------------
# printf-family helpers
FS_TEMPLATES = [
    (b'v%d.%d.%d', 'ddd'),
    (b' (build %d)', 'd'),
    (b' %s', 's'),
    (b'%d', 'd'),
    (b'%s', 's'),
    (b'Data\\Missiles\\Sounds\\%s.wav', 's'),
    (b"CharChooseHandAttackMode: ERROR - %ls's weapon slot %d has no ", 'Sd'),
    (b'SpellTargetString: ERROR - Invalid target type %d', 'd'),
    (b'ItemInfo: ERROR - PLGet failed, index %d, pList %d', 'dd'),
    (b'Monster %S marked as NPC with no NPC data', 'S'),
    (b'MonsterOKToCastSpell: ERROR - spell not monster castable: %hs', 's'),
    (b'Failed on spell %ld, usability byte %ld', 'dd'),
    (b'GroupIndex: ID %d not found (%s line %d)', 'dsd'),
    (b'Cube%3.3d', 'd'),
    (b'*.%s', 's'),
    (b'StackItemsIfPossible: ERROR - slot holds %d when max is %d, item %d(%ls)', 'dddS'),
    (b'Monster %s: Missing CYCLE_%s, sub-cycle %d', 'ssd'),
    (b'PCPtrToPCSlot: ERROR - no match on ptr %d', 'd'),
    (b'DrawTextMessage: ERROR - String %ls, length %d, StopChar %d', 'Sdd'),
    (b'MonsterGroupCalcDefaultDisposition: Monster species %d(%ls) ', 'dS'),
    (b'%u', 'u'), (b'%x', 'u'), (b'%X', 'u'), (b'%08X', 'u'), (b'%#x', 'u'), (b'%o', 'u'),
    (b'%i', 'd'), (b'%5d|', 'd'), (b'%-5d|', 'd'), (b'%05d', 'd'), (b'%+d', 'd'), (b'% d', 'd'),
    (b'%.3d', 'd'), (b'%hd', 'u'), (b'%hu', 'u'), (b'%lu', 'u'), (b'%ld', 'd'),
    (b'%c', 'c'), (b'[%3c]', 'c'), (b'100%%', ''), (b'%%d', ''), (b'no format', ''), (b'', ''),
    (b'%.2s', 's'), (b'%10s|', 's'), (b'%-10s|', 's'), (b'%*d', 'wd'), (b'%-*s|', 'ws'),
    (b'%.*s', 'ps'), (b'%I64d', 'q'), (b'%I64u', 'q'), (b'%I64X', 'q'),
    (b'%.2f', 'f'), (b'%f', 'f'), (b'%5.1f', 'f'),
    (b'%C', 'C'), (b'%S', 'S'), (b'%ls', 'S'), (b'%hs', 's'), (b'%.3S', 'S'),
    (b'%d/%d (%d/%d) %s', 'dddds'),
]

FW_TEMPLATES = [
    (' %d', 'd'), ('%d - %d', 'dd'), ('%+d%%', 'd'), (' %d)', 'd'), ('%+d, %+d %s', 'ddW'),
    (' %ld', 'd'), ('%d/%d (%d/%d) %s', 'ddddW'), ('%d (%s)', 'dW'), ('<%S>', 's'),
    ('%s %s', 'WW'), (' %dx', 'd'), ('%ld %s', 'dW'), (' -- %s', 'W'), ('(%s) %s', 'WW'),
    ('%s%d', 'Wd'), ('%s (%s)', 'WW'), ('%s %d %s', 'WdW'), ('%s %s %s?', 'WWW'), (' %d, ', 'd'),
    (' %+d', 'd'), ('%s %S.%S', 'Wss'), ('%s %d %s.', 'WdW'), ('Region %d', 'd'),
    ('  Linking Time: %d Min, %d Sec  ', 'dd'),
    ('  Linking Time: %d Hours, %d Min, %d Sec  ', 'ddd'),
    (' %d Bad Region-Mesh Links!', 'd'), ('  Linking Aborted!  ', ''),
    ('%u', 'u'), ('%x', 'u'), ('%05d', 'd'), ('%-6s|', 'W'), ('%6s|', 'W'), ('%hs', 's'),
    ('%ls', 'W'), ('%c', 'c'), ('%C', 'C'), ('%.3s', 'W'), ('%*d', 'wd'), ('%I64d', 'q'),
    ('100%%', ''), ('', ''),
]

D_EDGE = [0, 1, -1, 7, 42, 100, -100, 999, 1000, 12345, -12345, 65535, 65536, INT_MAX, INT_MIN]
U_EDGE = [0, 1, 9, 10, 255, 256, 0x7fff, 0x8000, 0xffff, 0x10000, 0x12345, 0x7fffffff,
          0x80000000, 0xffffffff, 0xdeadbeef]
Q_EDGE = [0, 1, (1 << 64) - 1, 1 << 32, (1 << 32) - 1, (1 << 63) - 1, 1 << 63, 1234567890123]
F_VALUES = [0.0, 1.0, -1.0, 3.14159, 2.71828, 100.3, 12345.678, -0.001, 0.1, 99.99, -42.42]


class _ArgBuilder:
    """Places string arguments in S1 (0x100 apart) and collects argument words."""

    def __init__(self, ctx, c, r):
        self.ctx, self.c, self.r = ctx, c, r
        self.slot = 0
        self.words = []          # (value, est_len)
        self.edges = set()
        self.desc = []

    def _place(self, data):
        a = self.ctx.scratch(1) + self.slot * 0x100
        self.slot += 1
        self.c.set(a, data)
        return a

    def add(self, kind, short=False):
        r = self.r
        if kind == 'd':
            v = r.choice(D_EDGE) if r.random() < 0.4 else r.randrange(-1000, 1001)
            self.words.append(v)
            self.desc.append(str(s32(v)))
            return 11
        if kind == 'u':
            v = r.choice(U_EDGE) if r.random() < 0.4 else r.getrandbits(r.choice([8, 16, 32]))
            self.words.append(v)
            self.desc.append('%#x' % (v & 0xffffffff))
            return 11
        if kind in ('w', 'p'):
            v = r.choice([0, 1, 3, 5, 12, 20, -5, -12]) if kind == 'w' else r.choice([0, 1, 3, 10, -1])
            self.words.append(v)
            self.desc.append(('w%d' if kind == 'w' else 'p%d') % v)
            return 20
        if kind == 'q':
            v = r.choice(Q_EDGE) if r.random() < 0.6 else r.getrandbits(64)
            self.words.append(v & 0xffffffff)
            self.words.append((v >> 32) & 0xffffffff)
            self.desc.append('q%#x' % v)
            return 22
        if kind == 'f':
            v = r.choice(F_VALUES)
            self.words.extend(F64(v).words())
            self.desc.append('f%r' % v)
            return 16
        if kind in ('s', 'S', 'W'):
            if r.random() < 0.03:
                self.words.append(0)
                self.edges.add('null_str')
                self.desc.append('null')
                return 8
            if kind == 's':
                s, e = _narrow(r, short=short)
                a = self._place(cstr(s))
                self.desc.append(repr(s))
                n = len(s)
            else:
                s, e = _wide(r, short=short)
                a = self._place(wstr(s))
                self.desc.append(repr(s))
                n = len(s)
            if e:
                self.edges.add(e)
            self.words.append(a)
            return n + 2
        if kind == 'c':        # char (narrow %c) / wchar_t (wide %c)
            x = r.random()
            if x < 0.75:
                v = r.randrange(0x20, 0x7f)
            else:
                v = r.choice([0, 0xe9, 0x141, 0x416, 0xff])
                self.edges.add('char_edge')
            self.words.append(v)
            self.desc.append('c%#x' % v)
            return 4
        if kind == 'C':        # the other width than the format
            x = r.random()
            if x < 0.7:
                v = r.randrange(0x20, 0x7f)
            else:
                v = r.choice([0, 0xe9, 0x416, 0xff, 0x141])
                self.edges.add('char_edge')
            self.words.append(v)
            self.desc.append('C%#x' % v)
            return 4
        raise ValueError(kind)


def _printf_case(ctx, c, r, fmt_bytes, kinds, limit):
    """Format string in S0, arguments after it. Retries with short strings when the
    estimated output would exceed the buffer."""
    for attempt in range(6):
        b = _ArgBuilder(ctx, c, r)
        est = len(fmt_bytes)
        for k in kinds:
            est += b.add(k, short=attempt > 0)
        if est < limit:
            break
        # drop the set-ups of the rejected attempt
        c.ops = [op for op in c.ops if not (op[0] == 'set' and op[1].base == ('scratch', 1))]
    c.set(ctx.scratch(0), fmt_bytes)
    c.arg(ctx.scratch(0))
    for w in b.words:
        c.arg(w)
    return b


def _format_string(ctx):
    """char* FormatString(const char* format, ...) -> g_format_string_buffer (200 bytes)"""
    fn = ctx.fn(0x00517a70)
    buf = ctx.g('g_format_string_buffer')
    total = ctx.n(260)
    for i in range(total):
        r = ctx.rng('formatstring', i)
        c = ctx.case('formatstring.%d' % i, fn, conv='c', ret='c', out='c')
        fmt, kinds = FS_TEMPLATES[i] if i < len(FS_TEMPLATES) else r.choice(FS_TEMPLATES)
        c.fill(buf, FMT_BUF_LEN, 0xcc)
        b = _printf_case(ctx, c, r, cstr(fmt), kinds, 190)
        c.cap(buf, FMT_BUF_LEN, 'buffer')
        c.note(fmt=fmt.decode('latin-1'), args='|'.join(b.desc))
        if b.edges:
            c.note(edge=','.join(sorted(b.edges)))


def _format_wide_string(ctx):
    """wchar_t* FormatWideString(const wchar_t* format, ...) -> g_wide_string_buffer"""
    fn = ctx.fn(0x00517a90)
    buf = ctx.g('g_wide_string_buffer')
    total = ctx.n(260)
    for i in range(total):
        r = ctx.rng('formatwide', i)
        c = ctx.case('formatwidestring.%d' % i, fn, conv='c', ret='w', out='w')
        fmt, kinds = FW_TEMPLATES[i] if i < len(FW_TEMPLATES) else r.choice(FW_TEMPLATES)
        c.fill(buf, WIDE_CAP, 0xcc)
        b = _printf_case(ctx, c, r, wstr(fmt), kinds, 240)
        c.cap(buf, WIDE_CAP, 'buffer')
        c.note(fmt=fmt, args='|'.join(b.desc))
        if b.edges:
            c.note(edge=','.join(sorted(b.edges)))


def _convert_to_wide(ctx):
    """wchar_t* ConvertStringToWide(const char*): swprintf(buf, L"%hs", s)"""
    fn = ctx.fn(0x00517ab0)
    buf = ctx.g('g_wide_string_buffer')
    s0 = ctx.scratch(0)
    for i in range(ctx.n(160)):
        r = ctx.rng('str2wide', i)
        c = ctx.case('convertstringtowide.%d' % i, fn, conv='c', ret='w', out='w')
        x = r.random()
        edge = None
        if x < 0.15:
            s = bytes(r.randrange(0x80, 0x100) for _ in range(r.randrange(1, 12)))
            edge = 'high_byte'
        elif x < 0.25:
            s = r.choice(NARROW_HIGH)
            edge = 'high_byte'
        elif x < 0.32:
            s = bytes(r.randrange(0x20, 0x7f) for _ in range(r.randrange(100, 200)))
        elif x < 0.37:
            s = r.choice([b'', b'\x01\x02\x1f', b'\x7f'])
        else:
            s = r.choice(NARROW_WORDS)
        c.fill(buf, WIDE_CAP, 0xcc)
        c.set(s0, cstr(s))
        c.arg(s0)
        c.cap(buf, WIDE_CAP, 'buffer')
        c.note(s=s.decode('latin-1'))
        if edge:
            c.note(edge=edge)


def _convert_to_narrow(ctx):
    """char* ConvertWideStringToString(const wchar_t*): sprintf(buf, "%ls", s)"""
    fn = ctx.fn(0x00517ad0)
    buf = ctx.g('g_wide_string_buffer')
    s0 = ctx.scratch(0)
    for i in range(ctx.n(160)):
        r = ctx.rng('wide2str', i)
        c = ctx.case('convertwidestringtostring.%d' % i, fn, conv='c', ret='c', out='c')
        x = r.random()
        edge = None
        if x < 0.12:
            s = ''.join(chr(r.randrange(0x80, 0x100)) for _ in range(r.randrange(1, 12)))
            edge = 'latin1'
        elif x < 0.2:
            s = r.choice(WIDE_LATIN1)
            edge = 'latin1'
        elif x < 0.3:
            s = r.choice(WIDE_OTHER)
            edge = 'non_latin1'
        elif x < 0.37:
            s = ''.join(chr(r.randrange(0x20, 0x7f)) for _ in range(r.randrange(100, 200)))
        elif x < 0.42:
            s = r.choice(['', '\u0001\u001f', '\u007f'])
        else:
            s = r.choice(WIDE_WORDS)
        c.fill(buf, WIDE_CAP, 0xcc)
        c.set(s0, wstr(s))
        c.arg(s0)
        c.cap(buf, WIDE_CAP, 'buffer')
        c.note(s=s.encode('unicode_escape').decode('ascii'))
        if edge:
            c.note(edge=edge)


def _format_commas(ctx):
    """wchar_t* FormatUnsignedIntegerWithCommas(wchar_t* output, unsigned int value)"""
    fn = ctx.fn(0x00517af0)
    s0 = ctx.scratch(0)
    edge = [0, 1, 9, 10, 99, 100, 999, 1000, 1001, 1999, 9999, 10000, 99999, 100000, 999999,
            1000000, 1000001, 1000999, 1001000, 9999999, 10000000, 99999999, 100000000,
            999999999, 1000000000, 1000000001, 1000000999, 1000999000, 1000001000,
            2147483647, 2147483648, 4294967295, 4294967294, 4000000000, 1234567890,
            4294000000, 4000000001, 20000, 300, 5000000, 3000000000]
    for i in range(ctx.n(300)):
        r = ctx.rng('commas', i)
        c = ctx.case('formatcommas.%d' % i, fn, conv='c', ret='w', out='w')
        x = r.random()
        if i < len(edge):
            v = edge[i]
        elif x < 0.4:
            v = r.randrange(0, 10 ** r.randrange(1, 10))
        elif x < 0.6:
            v = r.choice([1, 2, 5, 7, 9]) * 10 ** r.randrange(0, 10) + r.choice([0, 0, 1, 999])
        else:
            v = r.getrandbits(32)
        v &= 0xffffffff
        c.fill(s0, 0x60, 0xcc)
        c.arg(s0)
        c.arg(v)
        c.cap(s0, 0x60, 'output')
        c.note(value=v)


TITLE_WORDS = [b'long sword', b'SWORD OF THE NIGHT', b'potion of cure  lesser', b"o'brien's ring",
               b'rfs-81', b'x2 bow', b'who? me.', b'(cursed) amulet', b'*star*', b'mook&dane',
               b'a-b-c', b'2nd place', b'abc2def', b'', b'a', b' ', b'...', b'hello world',
               b'mIxEd CaSe', b'the.end', b'a/b/c', b'one,two', b'q:r;s', b'[bracket]',
               b'ZZZ', b'trynton gate', b'lord of the 2 towers', b'a  b', b'-dash', b"'quote'"]
TITLE_ALPHA = b'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ' + b'0123456789' + \
    b" &'(*-.2?" * 3 + b'!"#$%)+,/:;<=>@[\\]^_`{|}~'


def _title_case(ctx):
    """char* TitleCaseString(char*)"""
    fn = ctx.fn(0x00517bd0)
    s0 = ctx.scratch(0)
    for i in range(ctx.n(250)):
        r = ctx.rng('titlecase', i)
        c = ctx.case('titlecase.%d' % i, fn, conv='c', ret='c', out='c')
        x = r.random()
        edge = None
        if x < 0.35:
            s = r.choice(TITLE_WORDS)
        elif x < 0.92:
            s = bytes(r.choice(TITLE_ALPHA) for _ in range(r.randrange(1, 40)))
        else:
            s = bytes(r.choice(list(TITLE_ALPHA[:30]) + list(range(0x80, 0x100)))
                      for _ in range(r.randrange(1, 20)))
            edge = 'high_byte'
        c.set(s0, cstr(s))
        c.arg(s0)
        c.cap(s0, 0x80, 'string')
        c.note(s=s.decode('latin-1'))
        if edge:
            c.note(edge=edge)


# --------------------------------------------------------------------------------------
def _angle_edges():
    tp = TWO_PI
    vals = [0.0, -0.0, 1.0, -1.0, tp, -tp, 2 * tp, -2 * tp, 3 * tp, 3.1415927, -3.1415927,
            1.5707964, 4.712389, -1.5707964, 1e-30, -1e-30, 1e-7, -1e-7, 2e-7, -2e-7,
            f32_step(tp, 1), f32_step(tp, -1), f32_step(tp, 2), f32_step(tp, -2),
            f32_step(-tp, 1), f32_step(-tp, -1), f32_step(0.0, 1), f32_step(0.0, -1),
            f32_step(2 * tp, 1), f32_step(2 * tp, -1), 6.2831852, 6.28318, 6.2831855,
            -6.2831855, 100.0, -100.0, 1000.0, -1000.0, 12345.678, -9999.5, 0.5, -0.5]
    return [f32(v) for v in vals]


def _normalize_angle(ctx):
    """float NormalizeAngle(float). Only finite |angle| <= ~1e4: NaN, inf and huge values
    loop forever in retail (angle -= 2pi stops changing)."""
    fn = ctx.fn(0x00517c60)
    edges = _angle_edges()
    for i in range(ctx.n(300)):
        r = ctx.rng('normangle', i)
        c = ctx.case('normalizeangle.%d' % i, fn, conv='c', ret='f')
        x = r.random()
        if i < len(edges):
            v, rng_name = edges[i], 'edge'
        elif x < 0.5:
            v, rng_name = r.uniform(-2 * TWO_PI, 2 * TWO_PI), '2pi'
        elif x < 0.75:
            v, rng_name = r.uniform(-20.0, 20.0), '20'
        elif x < 0.9:
            v, rng_name = r.uniform(-200.0, 200.0), '200'
        else:
            v, rng_name = r.uniform(-TWO_PI, TWO_PI) * 1e-3, 'small'
        v = f32(v)
        c.arg(F32(v))
        c.note(angle=v, range=rng_name)


def _shortest_angle(ctx):
    """float ShortestAngleDistance(float, float)"""
    fn = ctx.fn(0x00517ce0)
    pi = f32(3.1415927)
    edge_pairs = [(0.0, 0.0), (0.0, TWO_PI), (TWO_PI, 0.0), (0.0, -0.0), (1e-30, 0.0),
                  (0.0, pi), (pi, 0.0), (0.0, -pi), (1.0, 1.0 + pi), (TWO_PI, TWO_PI),
                  (-TWO_PI, TWO_PI), (0.1, 6.2), (6.2, 0.1), (3.0, 3.2831852), (100.0, -100.0)]
    for i in range(ctx.n(300)):
        r = ctx.rng('shortangle', i)
        c = ctx.case('shortestangle.%d' % i, fn, conv='c', ret='f')
        x = r.random()
        if i < len(edge_pairs):
            a, b = edge_pairs[i]
            kind = 'edge'
        elif x < 0.5:
            a, b = r.uniform(0, TWO_PI), r.uniform(0, TWO_PI)
            kind = '0..2pi'
        elif x < 0.65:
            a, b = r.uniform(-pi, pi), r.uniform(-pi, pi)
            kind = '-pi..pi'
        elif x < 0.75:
            a = r.uniform(0, TWO_PI)
            b = a
            kind = 'equal'
        elif x < 0.87:
            a = r.uniform(0, TWO_PI)
            b = a + pi * r.choice([1, -1])
            kind = 'pi_apart'
        else:
            a, b = r.uniform(-50, 50), r.uniform(-50, 50)
            kind = '50'
        a, b = f32(a), f32(b)
        c.arg(F32(a))
        c.arg(F32(b))
        c.note(a=a, b=b, kind=kind)


# --------------------------------------------------------------------------------------
def _rect(r):
    x = r.random()
    if x < 0.6:
        left = r.randrange(-50, 640)
        top = r.randrange(-50, 480)
        return [left, top, left + r.randrange(0, 300), top + r.randrange(0, 200)]
    if x < 0.8:
        return [r.randrange(-1000, 1000) for _ in range(4)]
    edge = [INT_MIN, INT_MIN + 1, -1, 0, 1, 639, 640, 479, 480, INT_MAX - 1, INT_MAX]
    return [r.choice(edge) if r.random() < 0.6 else r.randrange(-1000, 1000) for _ in range(4)]


def _union_rects(ctx):
    """void UnionScreenRects(const W8ScreenRect* first, const W8ScreenRect* second, W8ScreenRect* result)"""
    fn = ctx.fn(0x00517e20)
    s0 = ctx.scratch(0)
    for i in range(ctx.n(200)):
        r = ctx.rng('unionrects', i)
        c = ctx.case('unionrects.%d' % i, fn, conv='c', ret='v')
        a = _rect(r)
        b = _rect(r) if r.random() < 0.9 else list(a)
        c.set(s0, struct.pack('<8i', *(a + b)))
        c.fill(s0 + 0x20, 0x10, 0xcc)
        x = r.random()
        if x < 0.06:
            out, alias = s0, 'first'
        elif x < 0.12:
            out, alias = s0 + 0x10, 'second'
        else:
            out, alias = s0 + 0x20, 'none'
        c.arg(s0)
        c.arg(s0 + 0x10)
        c.arg(out)
        c.cap(s0, 0x30, 'rects')
        c.note(first=a, second=b, alias=alias)


def _point_in_rect(ctx):
    """bool ScreenPointInRect(const W8ScreenRect*, const POINT*)"""
    fn = ctx.fn(0x00517e70)
    s0 = ctx.scratch(0)
    for i in range(ctx.n(250)):
        r = ctx.rng('pointinrect', i)
        c = ctx.case('pointinrect.%d' % i, fn, conv='c', ret='b')
        rc = _rect(r)
        left, top, right, bottom = rc
        x = r.random()
        if x < 0.5:
            px = r.choice([left, left - 1, left + 1, right, right - 1, right + 1,
                           r.randrange(min(left, right) - 5, max(left, right) + 6)])
            py = r.choice([top, top - 1, top + 1, bottom, bottom - 1, bottom + 1,
                           r.randrange(min(top, bottom) - 5, max(top, bottom) + 6)])
        elif x < 0.85:
            px, py = r.randrange(-100, 740), r.randrange(-100, 580)
        else:
            px = r.choice([INT_MIN, -1, 0, INT_MAX])
            py = r.choice([INT_MIN, -1, 0, INT_MAX])
        px = s32(px)
        py = s32(py)
        c.set(s0, struct.pack('<4i', *[s32(v) for v in rc]) + struct.pack('<2i', px, py))
        nul = r.random()
        if nul < 0.03:
            c.arg(0)
            c.arg(s0 + 0x10)
            c.note(edge='null_rect')
        elif nul < 0.06:
            c.arg(s0)
            c.arg(0)
            c.note(edge='null_point')
        else:
            c.arg(s0)
            c.arg(s0 + 0x10)
        c.note(rect=rc, point=[px, py])


def _strip_suffix(ctx):
    """void StripMonsterNameSuffix(wchar_t*): cut at the first '#'."""
    fn = ctx.fn(0x00517ea0)
    s0 = ctx.scratch(0)
    fixed = ['Rattkin#2', 'Savant Trooper#12', '#', '##', 'no suffix', '', 'a#b#c', 'Café#9',
             '#leading', 'trailing#', 'Рат#1', 'Higardi Patrol', 'x#€']
    for i in range(ctx.n(120)):
        r = ctx.rng('stripsuffix', i)
        c = ctx.case('stripsuffix.%d' % i, fn, conv='c', ret='v')
        if i < len(fixed):
            s = fixed[i]
        else:
            base = r.choice(WIDE_WORDS + WIDE_LATIN1)
            x = r.random()
            if x < 0.6:
                s = base + '#' + str(r.randrange(0, 100))
            elif x < 0.75:
                k = r.randrange(0, len(base) + 1)
                s = base[:k] + '#' + base[k:]
            elif x < 0.85:
                s = base + '#' + base + '#'
            else:
                s = base
        c.set(s0, wstr(s))
        c.arg(s0)
        c.cap(s0, 0x100, 'name')
        c.note(name=s.encode('unicode_escape').decode('ascii'))


# --------------------------------------------------------------------------------------
BOOL_EDGE = [2, 0x80, 0xff]
COND_EDGE = [0x80000000, 0xffffffff, 0xfffffff0]


def _char_ptr_to_slot(ctx):
    """unsigned int CharacterPointerToPartySlot(const W8Character*): reads fInParty (+4),
    asserts 0x1c8 when clear and 0x1d1 (after FormatString) when no slot matches."""
    fn = ctx.fn(0x00517ec0)
    buf = ctx.g('g_format_string_buffer')
    for i in range(ctx.n(150)):
        r = ctx.rng('charptr2slot', i)
        c = ctx.case('charptrtoslot.%d' % i, fn, conv='c', ret='i')
        x = r.random()
        fin = 1 if r.random() < 0.8 else r.choice([0, 0, 2, 0x80, 0xff])
        if x < 0.7:
            slot = r.randrange(8)
            ptr = ctx.char(slot)
            where = 'slot%d' % slot
        elif x < 0.85:
            slot = r.randrange(8)
            off = r.choice([1, 2, 4, 0x10, 0x100, 0x1000, CHAR - 8])
            ptr = ctx.char(slot) + off
            where = 'slot%d+%#x' % (slot, off)
        else:
            ptr = ctx.scratch(2)
            where = 'scratch'
        c.set(ptr + C_IN_PARTY, u8(fin))
        c.keep(buf, FMT_BUF_LEN)
        c.arg(ptr)
        c.note(ptr=where, fInParty=fin)


def _is_party_ptr(ctx):
    """bool IsPartyCharacterPointer(const W8Character*): pointer compare only."""
    fn = ctx.fn(0x00517f30)
    for i in range(ctx.n(150)):
        r = ctx.rng('ispartyptr', i)
        c = ctx.case('ispartyptr.%d' % i, fn, conv='c', ret='b')
        x = r.random()
        if x < 0.5:
            slot = r.randrange(8)
            ptr, where = ctx.char(slot), 'slot%d' % slot
        elif x < 0.65:
            slot = r.randrange(8)
            off = r.choice([1, 4, 0x100, CHAR - 1])
            ptr, where = ctx.char(slot) + off, 'slot%d+%#x' % (slot, off)
        elif x < 0.72:
            ptr, where = ctx.char(8), 'one_past_end'
        elif x < 0.78:
            ptr, where = ctx.char(0) - CHAR, 'before_start'
        elif x < 0.84:
            ptr, where = ctx.scratch(2), 'scratch'
        elif x < 0.9:
            ptr, where = r.choice([(ctx.g('g_status'), 'g_status'), (ctx.g('gXStatus'), 'gXStatus')])
        else:
            ptr = r.choice([0, 1, 0xffffffff, 0x1862])
            where = 'int%#x' % ptr
        c.arg(ptr)
        c.note(ptr=where)


def _adjust_byte(ctx):
    """void AdjustByteByPercent(unsigned char*, unsigned int percent):
    v = ((percent + 100) * v + 50) / 100 (unsigned 32-bit)"""
    fn = ctx.fn(0x00517f60)
    s0 = ctx.scratch(0)
    pedge = [0, 1, 10, 25, 50, 99, 100, 150, 200, 255, 1000, 0x7fffffff, 0x80000000, 0xffffffff,
             -1, -10, -50, -99, -100, -101, -200, 42949672]
    for i in range(ctx.n(250)):
        r = ctx.rng('adjbyte', i)
        c = ctx.case('adjustbyte.%d' % i, fn, conv='c', ret='v')
        v = r.choice([0, 1, 2, 50, 99, 100, 127, 128, 200, 254, 255]) if r.random() < 0.4 \
            else r.randrange(256)
        x = r.random()
        if x < 0.35:
            p = r.choice(pedge)
        elif x < 0.75:
            p = r.randrange(0, 301)
        else:
            p = r.randrange(-100, 1)
        c.set(s0, bytes([0xa5, v, 0x5a, 0xc3]))
        c.arg(s0 + 1)
        c.arg(p)
        c.cap(s0, 4, 'value')
        c.note(value=v, percent=s32(p))


def _adjust_int(ctx):
    """void AdjustIntegerByPercent(unsigned int*, unsigned int percent):
    v += v * percent / 100 (unsigned, product truncated to 32 bits)"""
    fn = ctx.fn(0x00517f90)
    s0 = ctx.scratch(0)
    pedge = [0, 1, 10, 25, 50, 100, 150, 200, 1000, 0x7fffffff, 0x80000000, 0xffffffff,
             -1, -10, -50, -100, -200]
    vedge = [0, 1, 99, 100, 101, 1000, 42949672, 42949673, 0x7fffffff, 0x80000000, 0xffffffff]
    for i in range(ctx.n(250)):
        r = ctx.rng('adjint', i)
        c = ctx.case('adjustint.%d' % i, fn, conv='c', ret='v')
        x = r.random()
        if x < 0.3:
            v = r.choice(vedge)
        elif x < 0.7:
            v = r.randrange(0, 100000)
        else:
            v = r.getrandbits(32)
        x = r.random()
        if x < 0.35:
            p = r.choice(pedge)
        elif x < 0.75:
            p = r.randrange(0, 301)
        else:
            p = r.randrange(-100, 1)
        c.set(s0, u32(0xa5a5a5a5) + u32(v) + u32(0x5a5a5a5a))
        c.arg(s0 + 4)
        c.arg(p)
        c.cap(s0, 12, 'value')
        c.note(value=v & 0xffffffff, percent=s32(p))


# --------------------------------------------------------------------------------------
def _xrow(ctx, slot):
    return (ctx.g('g_status') + 8).deref() + slot * XROW


def _hp(r):
    x = r.random()
    if x < 0.72:
        return r.randrange(1, 400)
    if x < 0.9:
        return 0
    return r.choice([1, 0x7fffffff, 0x80000000, 0xffffffff])


def _cond(r):
    x = r.random()
    if x < 0.5:
        return 0
    if x < 0.8:
        return r.randrange(1, 0x14)
    return r.choice([0x0e, 0x0f, 0x10, 0x11, 0x12, 0x13, 0x14])


def _party_state(ctx, c, r, with_gender=False, p_cond_edge=0.1, p_bool_edge=0.06):
    """XChar fOccupied, hp_current, highest_condition (and gender) of all 8 slots.
    Returns (mode, edges, summary)."""
    x = r.random()
    if x < 0.06:
        mode = 'none_occupied'
    elif x < 0.14:
        mode = 'all_dead'
    elif x < 0.22:
        mode = 'all_asleep'
    elif x < 0.32:
        mode = 'one_eligible'
    else:
        mode = 'mixed'
    ec = r.randrange(8) if r.random() < p_cond_edge else -1
    eb = r.randrange(8) if r.random() < p_bool_edge else -1
    one = r.randrange(8)
    p_occ = r.choice([0.6, 0.85, 1.0])
    edges = set()
    summary = []
    for s in range(8):
        occ = 1 if r.random() < p_occ else 0
        hp = _hp(r)
        cond = _cond(r)
        if mode == 'none_occupied':
            occ = 0
        elif mode == 'all_dead':
            if r.random() < 0.5:
                hp = 0
            else:
                cond = r.choice([0x12, 0x13, 0x14])
        elif mode == 'all_asleep':
            hp = r.randrange(1, 300)
            cond = r.choice([0x0f, 0x10, 0x11])
        elif mode == 'one_eligible':
            if s == one:
                occ, hp, cond = 1, r.randrange(1, 300), r.randrange(0, 0x0f)
            else:
                which = r.choice(['occ', 'hp', 'dead', 'asleep'])
                if which == 'occ':
                    occ = 0
                elif which == 'hp':
                    hp = 0
                elif which == 'dead':
                    cond = r.choice([0x12, 0x13])
                else:
                    cond = r.choice([0x0f, 0x10, 0x11])
        if s == eb and occ:
            occ = r.choice(BOOL_EDGE)
            edges.add('bool_byte')
        if s == ec:
            cond = r.choice(COND_EDGE)
            if occ:
                edges.add('cond_negative')
        ch = ctx.char(s)
        c.set(_xrow(ctx, s) + X_OCC, u8(occ))
        c.set(ch + C_HP, u32(hp))
        c.set(ch + C_HCOND, u32(cond))
        item = '%x/%x/%x' % (occ, hp, cond)
        if with_gender:
            g = r.choice([0, 1]) if r.random() < 0.95 else r.choice([2, 0x80, 0xff, 0xffffff80,
                                                                    0xffffffff])
            c.set(ch + C_GENDER, u32(g))
            item += '/g%x' % g
        summary.append(item)
    return mode, edges, ' '.join(summary)


def _require(r):
    return r.choice([0, 1, 1, 2, 2]) if r.random() < 0.93 else r.choice([3, -1, 0x7fffffff])


def _random_party_slots(ctx):
    """unsigned int GetRandomPartySlots(int require_primary, int require_secondary,
    unsigned int excluded_slot, unsigned int* selected, unsigned int count, bool skip_first_two)"""
    fn = ctx.fn(0x00517fb0)
    sel = ctx.scratch(0)
    for i in range(ctx.n(400)):
        r = ctx.rng('randomslots', i)
        c = ctx.case('randompartyslots.%d' % i, fn, conv='c', ret='i')
        mode, edges, summary = _party_state(ctx, c, r)
        rp, rs = _require(r), _require(r)
        excl = r.randrange(8) if r.random() < 0.5 else r.choice([8, 0xffffffff, 100, 0])
        x = r.random()
        if x < 0.85:
            count = r.choice([1, 1, 2, 2, 3, 4, 5, 6, 7, 8])
        else:
            count = r.choice([0, 9, 100, 0xffffffff])
        skip = r.choice([0, 0, 1])
        if r.random() < 0.06:
            skip = r.choice([2, 0x80, 0xff, 0x100, 0x101])
            edges.add('bool_byte' if (skip & 0xff) not in (0, 1) else 'high_bits')
        c.fill(sel, 0x40, 0xee)
        c.arg(rp)
        c.arg(rs)
        c.arg(excl)
        c.arg(sel)
        c.arg(count)
        c.arg(skip)
        c.cap(sel, 0x40, 'selected')
        c.note(mode=mode, party=summary, req=(s32(rp), s32(rs)), excluded=excl & 0xffffffff,
               count=count & 0xffffffff, skip=skip)
        if edges:
            c.note(edge=','.join(sorted(edges)))


def _random_character(ctx):
    """int GetRandomCharacter(int require_primary, int require_secondary, int excluded_slot,
    signed char excluded_gender)"""
    fn = ctx.fn(0x00518150)
    for i in range(ctx.n(350)):
        r = ctx.rng('randomchar', i)
        c = ctx.case('randomcharacter.%d' % i, fn, conv='c', ret='i')
        mode, edges, summary = _party_state(ctx, c, r, with_gender=True)
        rp, rs = _require(r), _require(r)
        excl = r.choice([-1, -1, r.randrange(8), r.randrange(8)]) if r.random() < 0.93 \
            else r.choice([8, 100, INT_MIN])
        x = r.random()
        if x < 0.5:
            gender = -1
        elif x < 0.9:
            gender = r.choice([0, 1])
        else:
            gender = r.choice([0x80, 2, 0x7f, 0x1ff, 0x100, 0x101, -2])
            edges.add('gender_arg')
        c.arg(rp)
        c.arg(rs)
        c.arg(excl)
        c.arg(gender)
        c.note(mode=mode, party=summary, req=(s32(rp), s32(rs)), excluded=s32(excl),
               gender=s32(gender))
        if edges:
            c.note(edge=','.join(sorted(edges)))


def _next_character(ctx):
    """int GetNextCharacter(int require_primary, int require_secondary, int previous_slot).
    previous_slot is limited to values with (prev + 1) % 8 >= 0 (signed remainder): a
    negative start slot reads XChar[-n] outside the array."""
    fn = ctx.fn(0x00518230)
    prevs_edge = [-1, 7, 8, 15, -9, -17, INT_MAX, INT_MAX - 1, INT_MAX - 8]
    for i in range(ctx.n(300)):
        r = ctx.rng('nextchar', i)
        c = ctx.case('nextcharacter.%d' % i, fn, conv='c', ret='i')
        mode, edges, summary = _party_state(ctx, c, r)
        rp, rs = _require(r), _require(r)
        prev = r.randrange(-1, 8) if r.random() < 0.85 else r.choice(prevs_edge)
        start = s32(prev + 1)                       # 32-bit wrap like the retail inc
        start = -(abs(start) % 8) if start < 0 else start % 8   # C remainder (toward zero)
        assert 0 <= start < 8, prev
        c.arg(rp)
        c.arg(rs)
        c.arg(prev)
        c.note(mode=mode, party=summary, req=(s32(rp), s32(rs)), previous=prev)
        if edges:
            c.note(edge=','.join(sorted(edges)))


def _rpc_ptr_to_slot(ctx):
    """int RPCPtrToPCSlot(const W8MonsterManagerEntry*): pointer compare against
    gXStatus.monster_manager_entries[0..7]; no match -> FormatString + assert 0x385."""
    fn = ctx.fn(0x00518310)
    gx = ctx.g('gXStatus')
    buf = ctx.g('g_format_string_buffer')
    for i in range(ctx.n(120)):
        r = ctx.rng('rpcptr', i)
        c = ctx.case('rpcptrtoslot.%d' % i, fn, conv='c', ret='i')
        x = r.random()
        if x < 0.6:
            k = r.randrange(8)
            ptr, where = gx + k * GX_ENTRY, 'entry%d' % k
        elif x < 0.75:
            k = r.randrange(8)
            off = r.choice([1, 4, 0x80, GX_ENTRY - 1])
            ptr, where = gx + k * GX_ENTRY + off, 'entry%d+%#x' % (k, off)
        elif x < 0.9:
            ptr, where = r.choice([(gx - GX_ENTRY, 'entry-1'), (gx + 8 * GX_ENTRY, 'entry8'),
                                   (gx + 0x900, 'gx+0x900')])
        else:
            ptr, where = r.choice([(0, 'null'), (ctx.scratch(2), 'scratch')])
        c.keep(buf, FMT_BUF_LEN)
        c.arg(ptr)
        c.note(ptr=where)


# --------------------------------------------------------------------------------------
def _msgbox_globals(ctx):
    return {
        'state': ctx.g('g_message_box_state'),
        'accepted': ctx.g('g_message_box_accepted'),
        'callback': ctx.g('g_message_box_callback', 0x0068c0a0),
        'bg_image': ctx.g('g_message_box_background_image'),
        'bg_button': ctx.g('g_message_box_background_button'),
        'accept_button': ctx.g('g_message_box_accept_button'),
        'cancel_button': ctx.g('g_message_box_cancel_button'),
        'accept_image': ctx.g('g_message_box_accept_image'),
        'cancel_image': ctx.g('g_message_box_cancel_image'),
    }


def _msgbox_no_controls(c, g):
    """All handles -1: ReleaseMessageBoxControls then calls no button/image function."""
    c.set(g['bg_image'], b'\xff\xff')
    for k in ('bg_button', 'accept_button', 'cancel_button', 'accept_image', 'cancel_image'):
        c.set(g[k], u32(0xffffffff))


def _msgbox_click(ctx):
    """void MessageBox{Accept,Cancel}ClickCallback(GUI_BUTTON*, INT32 reason):
    reason & 4 -> uiFlags |= CLICKED_ON; else reason & 8 and CLICKED_ON -> state 1,
    accepted = true (accept) / false (cancel)."""
    g = _msgbox_globals(ctx)
    btn = ctx.scratch(0)
    reasons = [0, 4, 8, 0xc, 0x10, 0x40, 0x80, 0xc0, 0x104, 0x108, 0x400, 0x800, 0x5, 0x9, 0xffffffff,
               0x80000008, 0x80000004]
    for addr, key in ((0x00518900, 'msgacceptclick'), (0x00518970, 'msgcancelclick')):
        fn = ctx.fn(addr)
        for i in range(ctx.n(120)):
            r = ctx.rng(key, i)
            c = ctx.case('%s.%d' % (key, i), fn, conv='c', ret='v')
            flags = r.getrandbits(32) if r.random() < 0.3 else r.choice([0, 1, 2, 3, 0x10, 0x12])
            if r.random() < 0.5:
                flags |= BUTTON_CLICKED_ON
            else:
                flags &= ~BUTTON_CLICKED_ON & 0xffffffff
            reason = r.choice(reasons) if r.random() < 0.6 else r.getrandbits(r.choice([4, 8, 32]))
            state = r.choice([0, 1, 2, 3, 2, 2])
            accepted = r.choice([0, 1])
            c.set(btn + BTN_FLAGS, u32(flags))
            c.set(g['state'], u32(state))
            c.set(g['accepted'], u8(accepted))
            c.arg(btn)
            c.arg(reason)
            c.cap(btn, 0xb0, 'button')
            c.cap(g['state'], 4, 'state')
            c.cap(g['accepted'], 1, 'accepted')
            c.note(flags='%#x' % flags, reason='%#x' % reason, state=state, accepted=accepted)


def _close_msgbox(ctx):
    """void CloseMessageBox(void): state 2 -> release controls, state 3, accepted = false."""
    fn = ctx.fn(0x005187e0)
    g = _msgbox_globals(ctx)
    for i in range(ctx.n(60)):
        r = ctx.rng('closemsgbox', i)
        c = ctx.case('closemessagebox.%d' % i, fn, conv='c', ret='v')
        state = r.choice([2, 2, 2, 0, 1, 3, 4, 0xffffffff, 0x102])
        accepted = r.choice([0, 1, 1]) if r.random() < 0.9 else r.choice([2, 0xff])
        _msgbox_no_controls(c, g)
        c.set(g['state'], u32(state))
        c.set(g['accepted'], u8(accepted))
        c.cap(g['state'], 4, 'state')
        c.cap(g['accepted'], 1, 'accepted')
        c.cap(g['bg_image'], 2, 'bg_image')
        c.note(state='%#x' % state, accepted=accepted)
        if accepted not in (0, 1):
            c.note(edge='bool_byte')


def _render_msgbox(ctx):
    """void RenderMessageBox(void) on the non-drawing states: 1 -> release controls and
    state 3; 3 -> state 0 and, when accepted == 1 (retail compares the byte with 1) and a
    callback is set, clear it and call it. State 2 (drawing) is never used."""
    fn = ctx.fn(0x005189b0)
    g = _msgbox_globals(ctx)
    cb = ctx.fn(0x00518b20)       # IsMessageBoxActive: no arguments, no side effects
    cb_addr = ctx.absolute(cb['retail'], cb['port'], 'IsMessageBoxActive')
    # the cap reports the bytes of the callback dword that change to 0 when it is cleared;
    # they match only if both addresses have the same zero bytes
    mask = [(cb['retail'] >> (8 * k)) & 0xff != 0 for k in range(4)]
    pmask = [(cb['port'] >> (8 * k)) & 0xff != 0 for k in range(4)]
    cb_ignore = [] if mask == pmask else [0]
    for i in range(ctx.n(100)):
        r = ctx.rng('rendermsgbox', i)
        c = ctx.case('rendermessagebox.%d' % i, fn, conv='c', ret='v')
        state = r.choice([3, 3, 3, 1, 1, 0]) if r.random() < 0.9 else r.choice([4, 0xffffffff, 0x103])
        accepted = r.choice([0, 1, 1]) if r.random() < 0.88 else r.choice([2, 0xff])
        has_cb = r.random() < 0.7
        _msgbox_no_controls(c, g)
        c.set(g['state'], u32(state))
        c.set(g['accepted'], u8(accepted))
        if has_cb:
            c.setp(g['callback'], cb_addr)
        else:
            c.set(g['callback'], u32(0))
        c.cap(g['state'], 4, 'state')
        c.cap(g['accepted'], 1, 'accepted')
        c.cap(g['callback'], 4, 'callback', ignore=cb_ignore)
        c.cap(g['bg_image'], 2, 'bg_image')
        c.note(state='%#x' % state, accepted=accepted, callback=int(has_cb))
        if accepted not in (0, 1):
            c.note(edge='bool_byte')
