"""Local Code\\Health Stamina Mana.cpp (decomp/src/wiz8/local_code/Health Stamina Mana.cpp):
hit points, stamina and spell-point pools of characters and monsters.

Tested (retail address, function, cases at --scale 1):
  0x0052a710 GetCharacterRealmSpellPoints          120
  0x0052a730 SumCharacterSpellPointsLeft           120
  0x0052a760 SumCharacterSpellPoints               100
  0x0052a7d0 FatigueArmorPenalty                   100
  0x0052b8e0 CompareSpellPointDeficits             150
  0x0052c320 SpellCastFatigueCost                  200
  0x0052c240 MonsterActionFatigueCost              220  (scratch W8MonsterInfo)
  0x0052b2f0 CharacterActionFatigueCost            300  (scratch W8CombatState wired into g_combat_state)
  0x0052a2f0 RecalculateCharacterHitPoints         300  (~10% reach the death path)
  0x0052a3e0 RecalculateCharacterStamina           300
  0x0052a500 RecalculateRealmSpellPoints           200
  0x0052a540 RebuildRealmSpellPointCeilings        350
  0x0052b480 SpendCharacterSpellPoints             200
  0x0052b4f0 RestoreCharacterRealmSpellPoints      200
  0x0052b6d0 DrainCharacterRealmSpellPoints        250
  0x0052b590 DrainCharacterSpellPoints             250
  0x0052b910 RestoreCharacterSpellPointsEvenly     350
  0x0052b550 DrainPartySpellPoints                 150
  0x0052ba00 RestorePartySpellPoints               150
  0x0052add0 HealCharacter                         250
  0x0052ad70 HealPartyByDice                       150
  0x0052b160 RestorePartyStaminaByDice             150
  0x0052b1c0 RestoreCharacterStamina               300
  0x0052af50 FatigueCharacter                      400
  0x0052b7e0 DamageCharacter                       250
  0x0052a890 ApplyDamageToCharacter                400
  0x0052a820 ApplyRolledHealthChangeToParty        150
  0x0052abf0 CharacterDies                         100
  0x0052c350 FindPartySlotWithLowestHitPoints      250
  0x0052c3b0 FindPartySlotWithLowestSpellPoints    250
  0x0052c480 FindPartyMemberWithLowestResistance4  200
  0x0052c500 ApplyQueuedFatigue                    150  (monster branch through a scratch
                                                         monster list wired into gXStatus.plsMonsterList)
  0x0052bfd0 HealMonster                           200  (scratch W8MonsterInfo, announce=0)
  0x0052c070 FatigueMonster                        250  (scratch W8MonsterInfo)
  0x0052c140 RestoreMonsterStamina                 250  (scratch W8MonsterInfo, announce=0)

Skipped:
  0x0052BA80 DamageMonstersInRadius - walks the live world monster list by 3D position
             (positions drift in real time) and damages/kills world monsters.
  0x0052BB60 ApplyDamageToMonster - points the camera, names the monster through its live
             group and 3D object (GetMonsterName), starts get-hit/death animation cycles and
             the death sequence of world monsters.
  0x0052beb0 MonsterReactsToBeingStruck - first thing it does is StartMonsterCycle on the
             live 3D monster (p3D), then changes world monster hostility.

Common set-up of the character cases (all restored by the core after each case):
  * party slots get corpus characters (setb), XChar[s].fOccupied is set explicitly;
  * g_status.world_suspended (mostly 0), g_status.skip_next_condition_reaction = 0,
    gXStatus.fCombatMode = 0, gXStatus.sight_refresh_pending = 0 (captured),
    g_combat_state = NULL (or a scratch state),
    gXStatus.fSurprisePossible = 1 unless a case says otherwise (with 0 the portrait
    damage splat and the damage-reaction quotes consume Random() depending on UI state,
    so those cases keep ASLEEP = 0: nothing captured depends on Random afterwards);
  * g_status.greeting_pending = 1: QueueEntry then deletes every new character event, so
    the quote queue (heap, not capturable) does not grow between cases;
  * death-capable cases set XChar[slot].npc_index = -1 (CharacterDies would mark a live
    NPC spawned), give the dying slot's two target blocks a fixed non-character value
    (CharacterDies resets them) and every other XChar[s].target_out_of_combat.iType =
    NONE (ApplyTarget would re-pick targets from the drifting world).  CharacterDies
    also has cases with a real npc_index whose NpcState.spawned word is captured.
  * captured: the 8 party characters (regen-rate floats with 4 ULP tolerance), the XChar
    rows (pointer fields ignored), g_status except the text-box counters (notices are
    left to scroll naturally), gXStatus.sight_refresh_pending, and any scratch struct
    the function writes.
  Cases with the character-side death path play CharacterDead.wav (sound is a side
  effect only).

Monster-side limits (scratch W8MonsterInfo: p3D = NULL, group 0, a location id no world
object has): announce stays 0 for HealMonster/RestoreMonsterStamina (the notice names the
monster through GetMonsterName, which needs a live group or 3D object); FatigueMonster and
the monster branch of ApplyQueuedFatigue never take the "stamina ran out" branch while
UNCONSCIOUS < 9999, and RestoreMonsterStamina never takes the "shake off exhaustion"
branch (SetMonsterCondition / ClearMonsterCondition look the monster up in the world
lists and refresh its group and 3D object), so their report_to counter is not exercised.
RestoreCharacterSpellPointsEvenly / RestorePartySpellPoints amounts are chosen so the
grant loop is bounded (a realm above its ceiling makes an unsigned deficit of ~4e9)."""
import struct

CHAR = 0x1862
ROW = 0x106

# W8Character (layout.ps1, wiz8/layouts/character.h)
C_VERSION = 0x0
C_PROF = 0x69
C_ORIG = 0x6d
C_LEVEL = 0x89
C_PLEV = 0x8d          # int profession_levels[15]
C_ATTR = 0xe5          # W8CharacterAttribute[7], stride 0x14, effective at +4
A_STR, A_PIE, A_VIT, A_SEN = 0, 2, 3, 6
C_SKILL = 0x19d        # W8CharacterSkill[0x29], stride 0x26, level at +6
SK_STEP = 0x26
SK_LEVEL = 6
C_DEATHS = 0x9fd
C_COND = 0xa01         # unsigned uiCondition[20]
C_ENCH = 0xa65         # W8Enchantment[8], stride 0xc: power, percent(u16), magnitude(u16), turns
C_HIGHEST = 0xb01
C_HPMAX = 0xb0d        # uiHPMax, hp_current, hp_adjustment, uiStaminaMax, stamina, fatigue_penalty
C_HP = 0xb11
C_STMAX = 0xb19
C_ST = 0xb1d
C_SPMAX = 0xb25        # int sp_max[6]
C_SPLEFT = 0xb45       # int iSPLeft[6]
C_LOAD = 0xbc9
C_LEARNED = 0xbcd      # int spell_learned[136]; 0x72 are scanned
C_RES4 = 0xf21         # resistances[4].total
C_EQUIP = 0xf5d        # W8ItemInstance[12], stride 0xc, iItemNo at +0
C_BAND = 0x169e
C_DEEP = 0x185b
# float fields the derived-stats rebuild rewrites: health/stamina regen rate and
# accumulator (0xb69..0xb75), spell_regen_rates[12] (0xb79)
CHAR_FLOATS = [0xb69, 0xb6d, 0xb71, 0xb75] + [0xb79 + 4 * k for k in range(12)]

DRAINED, DISEASED, SLOWED, POISONED, INFATUATED, INSANE = 1, 2, 5, 7, 10, 11
TURNCOAT, ASLEEP, UNCONSCIOUS, DEAD, MISSING = 13, 15, 17, 18, 19
INDEF = 9999
ENCH_GUARDIAN, ENCH_HASTE = 2, 5

# W8PartySlotRow (wiz8/layouts/combat_state.h)
X_OCC = 0x0
X_MODE = 0x5           # int attack_mode[4]
X_TOUT = 0x1d          # W8CombatSlot target_out_of_combat (iType first, 0x20 bytes)
X_TIN = 0x4d           # W8CombatSlot target_in_combat
X_NPC = 0xfa
X_PTRS = (0x19, 0x39, 0x49, 0x69, 0x7d, 0x9d, 0xa5, 0xc5, 0xed)  # item/pPCItem dwords

# W8GlobalStatus (wiz8/layouts/game_status.h)
S_SUSPENDED = 0x2390
S_GREETING = 0x2497
S_SKIPREACT = 0x2488
# everything after the buffer pointers except the text-box line counters
S_CAPS = ((0x0c, 0x1795), (0x17af, 0x4997), (0x49b7, 0x49c2))

# W8XStatus (wiz8/xstatus.h)
GX_COMBAT = 0x8dc
GX_MONLIST = 0x8f5
GX_SURPRISE = 0x90d
GX_SIGHT = 0xa03

# W8CombatState / W8CombatCharacterRow
CS_ROWS = 0x18
CS_ROW = 0xd4
CR_HAND = 0x6c         # current_hand, current_equip_slot follow

# W8MonsterInfo (wiz8/local_code/MonsterManager.h), 0x425 bytes
M_SIZE = 0x425
M_STRIDE = 0x430
M_LOC = 0x0
M_GROUP = 0x4
M_SPECIES = 0x8
M_HPMAX = 0x27         # uiHPMax, hp_current, stamina_max, stamina
M_COND = 0x57
M_HIGHEST = 0x107
M_BAND = 0x242
M_ACTION = 0x2e1       # action_kind, action_detail

# W8SpellEffectResult (wiz8/local_code/SpellEffect.h), 0xa2 bytes
R_SIZE = 0xa2
R_REP_CAP = 0x60       # reports vector: count 0x5c, capacity 0x60, data 0x64
R_REP_DATA = 0x64

N_SPELLS = 150         # SpellTables.dbs record count
N_ITEMS = 819          # Items.dbs record count
SPECIES = (0, 1, 17, 42, 100, 250, 400, 594)   # Monsters.dbs has 595 records

E32 = (0, 1, 0xffffffff, 0x7fffffff, 0x80000000, 0xfffffffe, 2)


def u32(v):
    return struct.pack('<I', int(v) & 0xffffffff)


def u16(v):
    return struct.pack('<H', int(v) & 0xffff)


def arr32(vals):
    return b''.join(u32(v) for v in vals)


def s32(v):
    v &= 0xffffffff
    return v - (1 << 32) if v >= (1 << 31) else v


def pick(r, edges, lo, hi, pe=0.25):
    if r.random() < pe:
        return r.choice(edges)
    return r.randint(lo, hi)


class Env:
    def __init__(self, ctx):
        self.ctx = ctx
        self.gs = ctx.g('g_status')
        self.gx = ctx.g('gXStatus')
        self.gcs = ctx.g('g_combat_state')
        self.npcs = ctx.g('g_npc_states')

    def char(self, s):
        return self.ctx.char(s)

    def row(self, s):
        return (self.gs + 8).deref() + s * ROW

    def one(self, c, r, slot):
        blob, name = self.ctx.pick_char(r)
        c.setb(self.char(slot), bytes(blob))
        return blob, name

    def party(self, c, r, occ):
        p = self.ctx.set_party(c, r)
        for s in range(8):
            c.set(self.row(s) + X_OCC, bytes([occ[s]]))
        return p

    def globals(self, c, surprise=1, suspended=0):
        c.set(self.gs + S_SUSPENDED, bytes([suspended]))
        c.set(self.gs + S_GREETING, b'\x01')
        c.set(self.gs + S_SKIPREACT, b'\x00')
        c.set(self.gx + GX_COMBAT, b'\x00')
        c.set(self.gx + GX_SURPRISE, bytes([surprise]))
        c.set(self.gx + GX_SIGHT, b'\x00')
        c.set(self.gcs, u32(0))

    def death_guard(self, c, slots, set_npc=True):
        """Slots that may die: npc_index -1 and both target slots set to a fixed
        non-character block (CharacterDies resets them, so the change is visible and
        identical in both processes). Every other row only gets iType = NONE, so
        ApplyTarget finds nobody aiming at the dead character."""
        target = arr32([0, 3, 7, 2, 0, 0, 0, 0])
        for s in range(8):
            if s in slots:
                if set_npc:
                    c.set(self.row(s) + X_NPC, u32(0xffffffff))
                c.set(self.row(s) + X_TOUT, target)
                c.set(self.row(s) + X_TIN, target)
            else:
                c.set(self.row(s) + X_TOUT, u32(0))

    def caps(self, c, slots=range(8), rows=True, status=True):
        for s in slots:
            c.cap(self.char(s), CHAR, 'char%d' % s, floats=CHAR_FLOATS)
        if rows:
            c.cap(self.row(0), 8 * ROW, 'xchar',
                  ignore=[s * ROW + o for s in range(8) for o in X_PTRS])
        if status:
            for a, b in S_CAPS:
                c.cap(self.gs + a, b - a, 'gstatus_%x' % a)
            c.cap(self.gx + GX_SIGHT, 1, 'sight_refresh')

    def result(self, c):
        """W8SpellEffectResult in scratch 1; its reports vector stores into scratch 2
        (capacity 16, so Add never reallocates)."""
        res = self.ctx.scratch(1)
        c.set(res + R_REP_CAP, u32(16))
        c.setp(res + R_REP_DATA, self.ctx.scratch(2))
        return res

    def cap_result(self, c):
        c.cap(self.ctx.scratch(1), R_SIZE, 'result', ignore=[R_REP_DATA])


def occupancy(r, p=0.85):
    occ = [1 if r.random() < p else 0 for _ in range(8)]
    if not any(occ):
        occ[r.randrange(8)] = 1
    return occ


def conds_blob(conds):
    vals = [0] * 20
    for k, v in conds.items():
        vals[k] = v
    return arr32(vals)


def highest_of(conds):
    hi = 0
    for k, v in conds.items():
        if v and k > hi:
            hi = k
    return hi


# ---------------------------------------------------------------- pure helpers

def t_get_realm_sp(ctx, E):
    fn = ctx.fn(0x0052a710)  # int GetCharacterRealmSpellPoints(const W8Character*, W8SpellRealm)
    for i in range(ctx.n(120)):
        r = ctx.rng('getrealmsp', i)
        c = ctx.case('getrealmsp.%d' % i, fn, conv='c', ret='i')
        slot = r.randrange(8)
        blob, name = E.one(c, r, slot)
        realm = r.randrange(6) if r.random() < 0.92 else r.choice([6, 7, -1])
        v = None
        if 0 <= realm < 6 and r.random() < 0.8:
            v = pick(r, [0, 1, -1, 0x7fffffff, -0x80000000, -5, 1000], -50, 400, 0.45)
            c.set(E.char(slot) + C_SPLEFT + 4 * realm, u32(v))
        c.arg(E.char(slot))
        c.arg(realm)
        c.note(char=name, realm=realm, sp_left=v)


def sp_array(r, blob, base, p_edge):
    vals = []
    for k in range(6):
        if r.random() < 0.6:
            vals.append(pick(r, [0, 1, -1, 0x7fffffff, -0x80000000, 0x40000000, -1000],
                             -50, 400, p_edge))
        else:
            vals.append(blob.get_i32(base + 4 * k))
    return vals


def t_sum_sp_left(ctx, E):
    fn = ctx.fn(0x0052a730)  # int SumCharacterSpellPointsLeft(const W8Character*)
    for i in range(ctx.n(120)):
        r = ctx.rng('sumspleft', i)
        c = ctx.case('sumspleft.%d' % i, fn, conv='c', ret='i')
        slot = r.randrange(8)
        blob, name = E.one(c, r, slot)
        vals = None
        if r.random() < 0.8:
            vals = sp_array(r, blob, C_SPLEFT, 0.3)
            c.set(E.char(slot) + C_SPLEFT, arr32(vals))
        c.arg(E.char(slot))
        c.note(char=name, sp_left=vals)


def t_sum_sp(ctx, E):
    fn = ctx.fn(0x0052a760)  # int SumCharacterSpellPoints(const W8Character*)
    for i in range(ctx.n(100)):
        r = ctx.rng('sumsp', i)
        c = ctx.case('sumsp.%d' % i, fn, conv='c', ret='i')
        slot = r.randrange(8)
        blob, name = E.one(c, r, slot)
        vals = None
        if r.random() < 0.8:
            vals = sp_array(r, blob, C_SPMAX, 0.3)
            c.set(E.char(slot) + C_SPMAX, arr32(vals))
        c.arg(E.char(slot))
        c.note(char=name, sp_max=vals)


def t_fatigue_armor_penalty(ctx, E):
    fn = ctx.fn(0x0052a7d0)  # unsigned FatigueArmorPenalty(int band)
    fixed = list(range(-3, 10)) + [40, 100, 0x7fffffff, -0x80000000, -0x7ffffffc, 0xfffffffe,
                                   0x100000004, 0x80000004]
    n = ctx.n(100)
    for i in range(n):
        r = ctx.rng('fatiguearmor', i)
        c = ctx.case('fatiguearmor.%d' % i, fn, conv='c', ret='i')
        if i < len(fixed):
            v = fixed[i]
        else:
            v = r.choice([r.randint(-20, 20), r.randint(0, 5), r.getrandbits(32)])
        c.arg(v)
        c.note(band=s32(v))


def t_compare_deficits(ctx, E):
    fn = ctx.fn(0x0052b8e0)  # int __cdecl CompareSpellPointDeficits(const void*, const void*)
    S0 = ctx.scratch(0)
    for i in range(ctx.n(150)):
        r = ctx.rng('cmpdeficit', i)
        c = ctx.case('cmpdeficit.%d' % i, fn, conv='c', ret='i')
        a = pick(r, E32, 0, 300, 0.3)
        b = a if r.random() < 0.25 else pick(r, E32, 0, 300, 0.3)
        c.set(S0, arr32([r.randrange(6), a, r.randrange(6), b]))
        c.arg(S0)
        c.arg(S0 + 8)
        c.note(a=a, b=b)


def t_spell_cast_fatigue(ctx, E):
    fn = ctx.fn(0x0052c320)  # int SpellCastFatigueCost(int spell_id, int result)
    results = [0, 1, 2, 3, 4, 5, 6, 7, 8, 8, 8, 9, 10, -1, -8, 0x7fffffff, -0x80000000]
    for i in range(ctx.n(200)):
        r = ctx.rng('spellfatigue', i)
        c = ctx.case('spellfatigue.%d' % i, fn, conv='c', ret='i')
        spell = i % N_SPELLS if i < N_SPELLS else r.randrange(N_SPELLS)
        res = r.choice(results)
        c.arg(spell)
        c.arg(res)
        c.note(spell=spell, result=s32(res))


def t_monster_action_fatigue(ctx, E):
    fn = ctx.fn(0x0052c240)  # int MonsterActionFatigueCost(const W8MonsterInfo*)
    S0 = ctx.scratch(0)
    for i in range(ctx.n(220)):
        r = ctx.rng('monactfatigue', i)
        c = ctx.case('monactfatigue.%d' % i, fn, conv='c', ret='i')
        if i < 165:
            kind = i % 11 - 1
        else:
            kind = r.choice([-2, 10, 11, 100, 0x7fffffff, -0x80000000, 0, 0, 1, 4])
        detail = r.choice([0, 1, 2, 3, 3, 3, 4, -1, 0x103, 0x7fffffff])
        dis = r.choice([0, 0, 0, 1, 1, INDEF, 0x80000000])
        c.set(S0 + M_ACTION, arr32([kind, detail]))
        c.set(S0 + M_COND + 4 * DISEASED, u32(dis))
        c.arg(S0)
        c.note(kind=s32(kind), detail=s32(detail), diseased=dis)


def t_char_action_fatigue(ctx, E):
    fn = ctx.fn(0x0052b2f0)  # unsigned CharacterActionFatigueCost(int slot, W8ActionKind)
    S0 = ctx.scratch(0)
    kinds = [0, 0, 0, 1, 1, 1, 2, 3, 3, 4, 5, 6, 6, 7, 8, 8, 9, 9, -1]
    for i in range(ctx.n(300)):
        r = ctx.rng('charactfatigue', i)
        c = ctx.case('charactfatigue.%d' % i, fn, conv='c', ret='i')
        slot = r.randrange(8)
        blob, name = E.one(c, r, slot)
        kind = r.choice(kinds) if r.random() < 0.95 else r.choice([10, 11, -2, 0x7fffffff])
        hand = r.choice([0, 0, 1, 1, 2, 3])
        eq = r.choice([6, 7, 8, 9, 6, 7, r.randrange(12)])
        mode = r.choice([0, 1, 2, 3, 4, 5, 5, 6, 6, 7, 8, -1])
        c.setp(E.gcs, S0)
        c.set(S0 + CS_ROWS + slot * CS_ROW + CR_HAND, arr32([hand, eq]))
        c.set(E.row(slot) + X_MODE + 4 * hand, u32(mode))
        item = None
        x = r.random()
        if x < 0.2:
            item = -1
        elif x < 0.85:
            item = r.randrange(N_ITEMS)
        if item is not None:
            c.set(E.char(slot) + C_EQUIP + 12 * eq, u32(item))
        stmax = None
        if r.random() < 0.5:
            stmax = pick(r, [0, 1, 99, 100, 101, 104, 105, 0x7fffffff, -1, -500], 50, 400, 0.4)
            c.set(E.char(slot) + C_STMAX, u32(stmax))
        dis = r.choice([0, 0, 0, 1, INDEF])
        c.set(E.char(slot) + C_COND + 4 * DISEASED, u32(dis))
        c.arg(slot)
        c.arg(kind)
        c.note(char=name, slot=slot, kind=s32(kind), hand=hand, equip=eq, mode=mode, item=item,
               stamina_max=stmax, diseased=dis)


# ---------------------------------------------------------------- stat recalcs

def t_recalc_hp(ctx, E):
    fn = ctx.fn(0x0052a2f0)  # void RecalculateCharacterHitPoints(W8Character*)
    for i in range(ctx.n(300)):
        r = ctx.rng('recalchp', i)
        c = ctx.case('recalchp.%d' % i, fn, conv='c', ret='v')
        party = E.party(c, r, [1] * 8)
        E.globals(c, surprise=1, suspended=1 if r.random() < 0.06 else 0)
        slot = r.randrange(8)
        _, blob, name = party[slot]
        ch = E.char(slot)
        edge = r.random() < 0.12
        note = {'char': name, 'slot': slot}
        x = r.random()
        if x < 0.05:
            c.set(ch + C_PROF, u32(0xffffffff))
            note['prof'] = -1
        elif x < 0.25:
            prof = r.randrange(15)
            c.set(ch + C_PROF, u32(prof))
            note['prof'] = prof
        if r.random() < 0.35:
            orig = r.choice([r.randrange(15), r.randrange(15), -1, 15, 100])
            c.set(ch + C_ORIG, u32(orig))
            note['orig'] = orig
        if r.random() < 0.6:
            levels = [blob.get_i32(C_PLEV + 4 * k) for k in range(15)]
            for _ in range(r.randint(1, 4)):
                k = r.randrange(15)
                if edge:
                    levels[k] = r.choice([0, 1, -1, 0x7fffffff, -0x80000000, 1000])
                else:
                    levels[k] = r.choice([0, 0, 1, r.randint(1, 30), r.randint(1, 15)])
            c.set(ch + C_PLEV, arr32(levels))
            note['levels'] = levels
        if r.random() < 0.5:
            vit = pick(r, [0, 1, 0x80000000, 0xffffffff, 0x7fffffff, 1000] if edge else [0, 1, 125, 200],
                       1, 125, 0.3)
            c.set(ch + C_ATTR + 0x14 * A_VIT + 4, u32(vit))
            note['vit'] = vit
        hpmax = blob.get_i32(C_HPMAX)
        hp = blob.get_u32(C_HP)
        adj = 0
        death = r.random() < 0.1
        if death:
            hpmax = 9000
            hp = r.randint(0, 50)
        else:
            if r.random() < 0.5:
                adj = pick(r, [-1000000, 1000000, -0x80000000, 0x7fffffff, -1, 1], -60, 60, 0.2)
            if r.random() < 0.3:
                hpmax = pick(r, [0, 1, -1, -100, 0x7fffffff], 1, 400, 0.3)
            if r.random() < 0.4:
                hp = r.choice([0, 1, max(1, hpmax // 2), hpmax + 5, r.randint(0, 400)]) & 0xffffffff
        c.set(ch + C_HPMAX, arr32([hpmax, hp, adj]))
        note.update(hpmax=hpmax, hp=hp, adj=s32(adj), death=death, edge=edge)
        E.death_guard(c, [slot])
        E.caps(c)
        c.arg(ch)
        c.note(**note)


def t_recalc_stamina(ctx, E):
    fn = ctx.fn(0x0052a3e0)  # void RecalculateCharacterStamina(W8Character*)
    for i in range(ctx.n(300)):
        r = ctx.rng('recalcst', i)
        c = ctx.case('recalcst.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        blob, name = E.one(c, r, slot)
        ch = E.char(slot)
        edge = r.random() < 0.12
        note = {'char': name, 'edge': edge}
        for a in (A_STR, A_PIE, A_VIT):
            if r.random() < 0.5:
                v = pick(r, [0, 0x7fffffff, 0xffffffff, 0x80000000, 1000000] if edge else [0, 1, 125, 126],
                         1, 125, 0.3)
                c.set(ch + C_ATTR + 0x14 * a + 4, u32(v))
                note['attr%d' % a] = v
        if r.random() < 0.4:
            lvl = pick(r, [0, 1, 50, 0x7fffffff, 0xffffffff] if edge else [0, 1, 30, 31], 1, 30, 0.3)
            c.set(ch + C_LEVEL, u32(lvl))
            note['level'] = lvl
        stmax = blob.get_i32(C_STMAX)
        st = blob.get_i32(C_ST)
        pen = blob.get_u32(C_STMAX + 8)
        if r.random() < 0.3:
            stmax = r.randint(0, 400)
        x = r.random()
        if x < 0.05:
            pen = r.choice([10000, 0xffffffff, 0x80000000])  # ceiling 0: divide by zero in both
        elif x < 0.4:
            pen = r.choice([0, 0, 1, r.randint(1, 60), r.randint(60, 300)])
        if r.random() < 0.6:
            st = r.choice([0, 1, -1, stmax, stmax + 1, r.randint(-60, 400), -0x80000000 if edge else 5,
                           0x7fffffff if edge else 9])
        c.set(ch + C_STMAX, arr32([stmax, st, pen]))
        if r.random() < 0.3:
            c.set(ch + C_BAND, u32(r.randrange(5)))
        note.update(stmax=stmax, st=s32(st), pen=pen)
        c.cap(ch, CHAR, 'char', floats=CHAR_FLOATS)
        c.arg(ch)
        c.note(**note)


def mutate_spellbook(c, r, ch, blob, edge, note):
    big = [0x7fffffff, 0x80000000, 0xffffffff, 0x40000000, 1000000]
    x = r.random()
    if x < 0.5:
        learned = [blob.get_i32(C_LEARNED + 4 * k) for k in range(0x72)]
        y = r.random()
        if y < 0.15:
            learned = [0] * 0x72
        elif y < 0.3:
            learned = [r.choice([1, 2]) for _ in range(0x72)]
        else:
            for _ in range(r.randint(1, 20)):
                learned[r.randrange(0x72)] = r.choice([0, 1, 2, 3, -1, 1, 2])
        c.set(ch + C_LEARNED, arr32(learned))
        note['learned'] = sum(1 for v in learned if v in (1, 2))
    for k in range(24, 28):
        if r.random() < 0.45:
            v = pick(r, big if edge else [0, 1, 125, 200], 0, 125, 0.25)
            c.set(ch + C_SKILL + SK_STEP * k + SK_LEVEL, u32(v))
            note['book%d' % k] = v
    for k in range(28, 34):
        if r.random() < 0.35:
            v = pick(r, big if edge else [0, 1, 125, 200], 0, 125, 0.25)
            c.set(ch + C_SKILL + SK_STEP * k + SK_LEVEL, u32(v))
            note['realm%d' % k] = v
    if r.random() < 0.4:
        v = pick(r, big if edge else [0, 1, 125, 200], 1, 125, 0.25)
        c.set(ch + C_ATTR + 0x14 * A_PIE + 4, u32(v))
        note['piety'] = v
    if r.random() < 0.4:
        v = pick(r, big if edge else [0, 1, 30, 50], 1, 30, 0.25)
        c.set(ch + C_LEVEL, u32(v))
        note['level'] = v
    if r.random() < 0.5:
        vals = [r.choice([0, r.randint(0, 400), blob.get_i32(C_SPMAX + 4 * k), -5]) for k in range(6)]
        c.set(ch + C_SPMAX, arr32(vals))
        note['sp_max'] = vals
    if r.random() < 0.5:
        vals = [r.choice([0, r.randint(-20, 400), blob.get_i32(C_SPLEFT + 4 * k)]) for k in range(6)]
        c.set(ch + C_SPLEFT, arr32(vals))
        note['sp_left'] = vals


def t_recalc_realm_sp(ctx, E):
    fn = ctx.fn(0x0052a500)  # void RecalculateRealmSpellPoints(W8Character*)
    profs = list(range(-1, 15)) + [15, 100, -5]
    for i in range(ctx.n(200)):
        r = ctx.rng('recalcrealmsp', i)
        c = ctx.case('recalcrealmsp.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        blob, name = E.one(c, r, slot)
        ch = E.char(slot)
        note = {'char': name}
        if i < len(profs) * 2:
            prof = profs[i % len(profs)]
        else:
            prof = r.choice(profs) if r.random() < 0.6 else None
        if prof is not None:
            c.set(ch + C_PROF, u32(prof))
        note['prof'] = prof
        mutate_spellbook(c, r, ch, blob, r.random() < 0.1, note)
        c.cap(ch, CHAR, 'char', floats=CHAR_FLOATS)
        c.arg(ch)
        c.note(**note)


def t_rebuild_ceilings(ctx, E):
    fn = ctx.fn(0x0052a540)  # int RebuildRealmSpellPointCeilings(W8Character*)
    for i in range(ctx.n(350)):
        r = ctx.rng('rebuildceil', i)
        c = ctx.case('rebuildceil.%d' % i, fn, conv='c', ret='i')
        slot = r.randrange(8)
        blob, name = E.one(c, r, slot)
        ch = E.char(slot)
        edge = r.random() < 0.15
        note = {'char': name, 'edge': edge}
        mutate_spellbook(c, r, ch, blob, edge, note)
        c.cap(ch, CHAR, 'char', floats=CHAR_FLOATS)
        c.arg(ch)
        c.note(**note)


# ---------------------------------------------------------------- spell points by slot

def sp_amount(r, left):
    x = r.random()
    if x < 0.1:
        return 0
    if x < 0.25:
        return left
    if x < 0.55:
        return r.randint(1, max(1, left)) if left > 0 else r.randint(1, 10)
    if x < 0.75:
        return left + r.randint(1, 50)
    if x < 0.85:
        return -r.randint(1, 50)
    return r.choice([0x7fffffff, -0x80000000, 0xffffffff, 1])


def t_spend_sp(ctx, E):
    fn = ctx.fn(0x0052b480)  # void SpendCharacterSpellPoints(int slot, W8SpellRealm, int amount)
    for i in range(ctx.n(200)):
        r = ctx.rng('spendsp', i)
        c = ctx.case('spendsp.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        blob, name = E.one(c, r, slot)
        ch = E.char(slot)
        realm = r.randrange(6)
        left = blob.get_i32(C_SPLEFT + 4 * realm)
        if r.random() < 0.7:
            left = pick(r, [0, 1, -1, 0x7fffffff, -0x80000000, 5], -20, 300, 0.25)
            c.set(ch + C_SPLEFT + 4 * realm, u32(left))
        amount = sp_amount(r, s32(left))
        c.cap(ch, CHAR, 'char', floats=CHAR_FLOATS)
        c.arg(slot)
        c.arg(realm)
        c.arg(amount)
        c.note(char=name, slot=slot, realm=realm, left=s32(left), amount=s32(amount))


def t_restore_realm_sp(ctx, E):
    fn = ctx.fn(0x0052b4f0)  # void RestoreCharacterRealmSpellPoints(int slot, W8SpellRealm, int)
    for i in range(ctx.n(200)):
        r = ctx.rng('restorerealmsp', i)
        c = ctx.case('restorerealmsp.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        blob, name = E.one(c, r, slot)
        ch = E.char(slot)
        realm = r.randrange(6)
        mx = blob.get_i32(C_SPMAX + 4 * realm)
        left = blob.get_i32(C_SPLEFT + 4 * realm)
        if r.random() < 0.6:
            mx = pick(r, [0, 1, -1, 0x7fffffff, -0x80000000], 0, 400, 0.2)
            c.set(ch + C_SPMAX + 4 * realm, u32(mx))
        if r.random() < 0.6:
            left = pick(r, [0, -1, 0x7ffffff0, -0x80000000, s32(mx), s32(mx) + 1], -20, 400, 0.3)
            c.set(ch + C_SPLEFT + 4 * realm, u32(left))
        x = r.random()
        if x < 0.1:
            amount = 0
        elif x < 0.6:
            amount = r.randint(1, 80)
        elif x < 0.75:
            amount = s32(mx) - s32(left) + r.randint(-2, 2)
        elif x < 0.88:
            amount = -r.randint(1, 80)
        else:
            amount = r.choice([0x7fffffff, -0x80000000, 0x20, 0xfffffff0])
        c.cap(ch, CHAR, 'char', floats=CHAR_FLOATS)
        c.arg(slot)
        c.arg(realm)
        c.arg(amount)
        c.note(char=name, slot=slot, realm=realm, sp_max=s32(mx), left=s32(left), amount=s32(amount))


def t_drain_realm_sp(ctx, E):
    fn = ctx.fn(0x0052b6d0)  # void DrainCharacterRealmSpellPoints(int, W8SpellRealm, unsigned, bool)
    for i in range(ctx.n(250)):
        r = ctx.rng('drainrealmsp', i)
        c = ctx.case('drainrealmsp.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        blob, name = E.one(c, r, slot)
        ch = E.char(slot)
        suspended = 1 if r.random() < 0.1 else 0
        c.set(E.gs + S_SUSPENDED, bytes([suspended]))
        realm = r.randrange(6)
        left = blob.get_i32(C_SPLEFT + 4 * realm)
        if r.random() < 0.7:
            left = pick(r, [0, 1, -1, 0x7fffffff, -0x80000000, 2], -20, 300, 0.3)
            c.set(ch + C_SPLEFT + 4 * realm, u32(left))
        hp0 = r.random() < 0.08
        if hp0:
            c.set(ch + C_HP, u32(0))
        amount = sp_amount(r, s32(left))
        announce = r.randrange(2)
        c.cap(ch, CHAR, 'char', floats=CHAR_FLOATS)
        c.arg(slot)
        c.arg(realm)
        c.arg(amount)
        c.arg(announce)
        c.note(char=name, slot=slot, realm=realm, left=s32(left), amount=amount & 0xffffffff,
               announce=announce, suspended=suspended, hp0=hp0)


def t_drain_char_sp(ctx, E):
    fn = ctx.fn(0x0052b590)  # void DrainCharacterSpellPoints(int slot, unsigned amount, bool)
    for i in range(ctx.n(250)):
        r = ctx.rng('draincharsp', i)
        c = ctx.case('draincharsp.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        blob, name = E.one(c, r, slot)
        ch = E.char(slot)
        suspended = 1 if r.random() < 0.08 else 0
        c.set(E.gs + S_SUSPENDED, bytes([suspended]))
        vals = [blob.get_i32(C_SPLEFT + 4 * k) for k in range(6)]
        if r.random() < 0.7:
            vals = [r.choice([0, 0, r.randint(1, 40), r.randint(1, 300), -r.randint(1, 20), vals[k],
                              0x7fffffff if r.random() < 0.1 else 3]) for k in range(6)]
            c.set(ch + C_SPLEFT, arr32(vals))
        hp0 = r.random() < 0.06
        if hp0:
            c.set(ch + C_HP, u32(0))
        total = sum(v for v in vals if v > 0)
        x = r.random()
        if x < 0.08:
            amount = 0
        elif x < 0.5:
            amount = r.randint(1, 30)
        elif x < 0.7:
            amount = total
        elif x < 0.85:
            amount = total + r.randint(1, 100)
        else:
            amount = r.choice([0xffffffff, 0x80000000, 0x7fffffff, 1])
        announce = r.randrange(2)
        c.cap(ch, CHAR, 'char', floats=CHAR_FLOATS)
        c.arg(slot)
        c.arg(amount)
        c.arg(announce)
        c.note(char=name, slot=slot, sp_left=vals, amount=amount & 0xffffffff, announce=announce,
               suspended=suspended, hp0=hp0)


def bounded_amount(r, deficits, allow_negative=True):
    """Amount for RestoreCharacterSpellPointsEvenly that cannot loop billions of times:
    the loop runs until the amount is used up or every (unsigned) deficit is zero."""
    total = sum(d & 0xffffffff for d in deficits)
    if total > 0x10000:
        return r.choice([0, 1, 2, 3, 7, r.randint(1, 3000)])
    x = r.random()
    if x < 0.08:
        return 0
    if x < 0.4:
        return r.randint(1, 12)
    if x < 0.65:
        return r.randint(1, max(1, total))
    if x < 0.8:
        return total + r.randint(0, 20)
    if allow_negative and x < 0.92:
        return r.choice([-1, -2, -100])
    return r.choice([0x7fffffff, total, total + 1, 6])


def sp_pools(r, blob):
    x = r.random()
    if x < 0.25:
        mx = [blob.get_i32(C_SPMAX + 4 * k) for k in range(6)]
        left = [blob.get_i32(C_SPLEFT + 4 * k) for k in range(6)]
    elif x < 0.6:
        mx = [r.choice([0, r.randint(0, 60), r.randint(0, 300)]) for _ in range(6)]
        left = [max(0, m - r.choice([0, 0, 1, 2, 5, r.randint(0, 40)])) for m in mx]
    elif x < 0.85:
        # deliberate ties in the deficits
        d = [r.choice([0, 1, 3, 5, 5, 8]) for _ in range(6)]
        mx = [r.randint(10, 200) for _ in range(6)]
        left = [m - dd for m, dd in zip(mx, d)]
    else:
        mx = [r.randint(0, 100) for _ in range(6)]
        left = [m + r.choice([0, 0, 1, 5, -3, -30]) for m in mx]  # some realms above the ceiling
    return mx, left


def t_restore_evenly(ctx, E):
    fn = ctx.fn(0x0052b910)  # void RestoreCharacterSpellPointsEvenly(int slot, int amount)
    for i in range(ctx.n(350)):
        r = ctx.rng('restoreevenly', i)
        c = ctx.case('restoreevenly.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        blob, name = E.one(c, r, slot)
        ch = E.char(slot)
        mx, left = sp_pools(r, blob)
        c.set(ch + C_SPMAX, arr32(mx))
        c.set(ch + C_SPLEFT, arr32(left))
        deficits = [(m - l) & 0xffffffff for m, l in zip(mx, left)]
        amount = bounded_amount(r, deficits)
        c.cap(ch, CHAR, 'char', floats=CHAR_FLOATS)
        c.arg(slot)
        c.arg(amount)
        c.note(char=name, slot=slot, sp_max=mx, sp_left=left, amount=s32(amount))


def t_drain_party_sp(ctx, E):
    fn = ctx.fn(0x0052b550)  # void DrainPartySpellPoints(int amount, bool announce)
    for i in range(ctx.n(150)):
        r = ctx.rng('drainpartysp', i)
        c = ctx.case('drainpartysp.%d' % i, fn, conv='c', ret='v')
        occ = occupancy(r)
        party = E.party(c, r, occ)
        E.globals(c, suspended=1 if r.random() < 0.08 else 0)
        for s in r.sample(range(8), r.randint(0, 3)):
            vals = [r.choice([0, r.randint(1, 50), r.randint(1, 300), -r.randint(1, 20)]) for _ in range(6)]
            c.set(E.char(s) + C_SPLEFT, arr32(vals))
        if r.random() < 0.2:
            c.set(E.char(r.randrange(8)) + C_HP, u32(0))
        amount = r.choice([0, 1, r.randint(1, 30), r.randint(30, 400), -1, 0x7fffffff, -0x80000000])
        announce = r.randrange(2)
        E.caps(c, rows=False, status=False)
        c.arg(amount)
        c.arg(announce)
        c.note(occ=occ, amount=s32(amount), announce=announce, party=[p[2] for p in party])


def t_restore_party_sp(ctx, E):
    fn = ctx.fn(0x0052ba00)  # void RestorePartySpellPoints(int amount)
    for i in range(ctx.n(150)):
        r = ctx.rng('restorepartysp', i)
        c = ctx.case('restorepartysp.%d' % i, fn, conv='c', ret='v')
        occ = occupancy(r)
        party = E.party(c, r, occ)
        E.globals(c)
        for s in r.sample(range(8), r.randint(0, 3)):
            # ceilings stay >= 0 and pools below them: the deficits (and the "everything"
            # amount, the sum of the ceilings) stay small
            mx = [r.choice([0, r.randint(0, 60), r.randint(0, 400)]) for _ in range(6)]
            left = [m - r.choice([0, 0, 1, 3, 3, r.randint(0, 60), m + 5]) for m in mx]
            c.set(E.char(s) + C_SPMAX, arr32(mx))
            c.set(E.char(s) + C_SPLEFT, arr32(left))
        for s in r.sample(range(8), r.randint(0, 2)):
            hc = r.choice([0, 15, 17, 18, 19, 18])
            c.set(E.char(s) + C_HIGHEST, u32(hc))
        if r.random() < 0.2:
            c.set(E.char(r.randrange(8)) + C_HP, u32(0))
        amount = r.choice([-1, -1, -5, 0, 1, r.randint(1, 20), r.randint(20, 500), 0x7fffffff,
                           -0x80000000])
        E.caps(c, rows=False, status=False)
        c.arg(amount)
        c.note(occ=occ, amount=s32(amount), party=[p[2] for p in party])


# ---------------------------------------------------------------- hit points and stamina

def t_heal_char(ctx, E):
    fn = ctx.fn(0x0052add0)  # void HealCharacter(int slot, int amount, bool announce)
    for i in range(ctx.n(250)):
        r = ctx.rng('healchar', i)
        c = ctx.case('healchar.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        occ = [1] * 8
        if r.random() < 0.04:
            occ[slot] = 0
        party = E.party(c, r, occ)
        E.globals(c)
        _, blob, name = party[slot]
        ch = E.char(slot)
        mx = blob.get_i32(C_HPMAX)
        if r.random() < 0.3:
            mx = pick(r, [1, 2, 100, 0x7fffffff], 1, 400, 0.2)
        x = r.random()
        if x < 0.1:
            hp = 0
        elif x < 0.2:
            hp = mx
        elif x < 0.25:
            hp = mx + r.randint(1, 50)
        else:
            hp = r.randint(1, max(1, mx - 1))
        c.set(ch + C_HPMAX, arr32([mx, hp]))
        x = r.random()
        if x < 0.06:
            amount = 0
        elif x < 0.55:
            amount = r.randint(1, 60)
        elif x < 0.75:
            amount = mx - hp + r.randint(-2, 2)
        elif x < 0.9:
            amount = -r.randint(1, 80)
        else:
            amount = r.choice([0x7fffffff, -0x80000000, 1000000, -1])
        announce = r.randrange(2)
        c.cap(ch, CHAR, 'char', floats=CHAR_FLOATS)
        c.arg(slot)
        c.arg(amount)
        c.arg(announce)
        c.note(char=name, slot=slot, occupied=occ[slot], hpmax=mx, hp=hp, amount=s32(amount),
               announce=announce)


def lower_pools(c, r, E, party, kind):
    """Lower hit points (kind 'hp') or stamina ('st') of random party members."""
    for s, blob, _ in party:
        if r.random() < 0.6:
            ch = E.char(s)
            if kind == 'hp':
                mx = blob.get_i32(C_HPMAX)
                hp = r.choice([0, 1, mx, r.randint(1, max(1, mx)), r.randint(1, max(1, mx))])
                c.set(ch + C_HP, u32(hp))
            else:
                mx = blob.get_i32(C_STMAX)
                st = r.choice([0, 1, 9, 10, mx, r.randint(0, max(1, mx)), r.randint(0, max(1, mx))])
                c.set(ch + C_ST, u32(st))


def dice_args(r):
    count = r.choice([0, 1, 1, 2, 3, 4, 6, 10, 255])
    sides = r.choice([0, 1, 2, 4, 6, 8, 10, 20, 255])
    base = r.choice([0, 0, 1, 5, 10, 50, -5, -50, 32767, -32768, r.randint(-20, 100)])
    return count, sides, base


def t_heal_party_dice(ctx, E):
    fn = ctx.fn(0x0052ad70)  # void HealPartyByDice(unsigned char count, unsigned char sides, short base)
    for i in range(ctx.n(150)):
        r = ctx.rng('healpartydice', i)
        c = ctx.case('healpartydice.%d' % i, fn, conv='c', ret='v')
        occ = occupancy(r)
        party = E.party(c, r, occ)
        E.globals(c)
        lower_pools(c, r, E, party, 'hp')
        count, sides, base = dice_args(r)
        E.caps(c, rows=False)
        c.arg(count)
        c.arg(sides)
        c.arg(base)
        c.note(occ=occ, dice='%dd%d%+d' % (count, sides, base))


def t_restore_party_stamina_dice(ctx, E):
    fn = ctx.fn(0x0052b160)  # void RestorePartyStaminaByDice(unsigned char, unsigned char, short)
    for i in range(ctx.n(150)):
        r = ctx.rng('stpartydice', i)
        c = ctx.case('stpartydice.%d' % i, fn, conv='c', ret='v')
        occ = occupancy(r)
        party = E.party(c, r, occ)
        E.globals(c)
        lower_pools(c, r, E, party, 'st')
        for s in r.sample(range(8), r.randint(0, 3)):
            cond = r.choice([UNCONSCIOUS, UNCONSCIOUS, DEAD, ASLEEP])
            conds = {cond: INDEF if cond != ASLEEP else 5}
            c.set(E.char(s) + C_COND, conds_blob(conds))
            c.set(E.char(s) + C_HIGHEST, u32(highest_of(conds)))
            if cond == UNCONSCIOUS:
                c.set(E.char(s) + C_ST, u32(r.choice([0, 1, 5, 9])))
        count, sides, base = dice_args(r)
        E.death_guard(c, [])
        E.caps(c)
        c.arg(count)
        c.arg(sides)
        c.arg(base)
        c.note(occ=occ, dice='%dd%d%+d' % (count, sides, base))


def t_restore_stamina(ctx, E):
    fn = ctx.fn(0x0052b1c0)  # void RestoreCharacterStamina(int slot, int amount, bool announce)
    for i in range(ctx.n(300)):
        r = ctx.rng('restorest', i)
        c = ctx.case('restorest.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        party = E.party(c, r, [1] * 8)
        E.globals(c)
        _, blob, name = party[slot]
        ch = E.char(slot)
        note = {'char': name, 'slot': slot}
        conds = {}
        if r.random() < 0.35:
            conds[UNCONSCIOUS] = r.choice([INDEF, INDEF, 5, 9998])
        x = r.random()
        if x < 0.06:
            conds[DEAD] = INDEF
        elif x < 0.09:
            conds[MISSING] = INDEF
        if conds:
            c.set(ch + C_COND, conds_blob(conds))
        hc = highest_of(conds)
        if r.random() < 0.05:
            hc = r.choice([0x12, 0x80000000, 0xffffffff])  # compared unsigned against DEAD
        c.set(ch + C_HIGHEST, u32(hc))
        mx = blob.get_i32(C_STMAX)
        if r.random() < 0.3:
            mx = pick(r, [0, 1, 0x7fffffff, -1], 10, 400, 0.15)
        x = r.random()
        if x < 0.1:
            st = mx
        elif x < 0.2:
            st = r.choice([0, 1, 5, 9])
        elif x < 0.25:
            st = r.choice([-1, -50, mx + 10])
        else:
            st = r.randint(0, max(0, mx))
        hp = blob.get_u32(C_HP)
        if r.random() < 0.05:
            hp = 0
        c.set(ch + C_HP, u32(hp))
        c.set(ch + C_STMAX, arr32([mx, st]))
        if r.random() < 0.6:
            c.set(ch + C_BAND, u32(r.choice([0, 0, 1, 2, 3, 4, 7])))
        x = r.random()
        if x < 0.06:
            amount = 0
        elif x < 0.5:
            amount = r.randint(1, 40)
        elif x < 0.65:
            amount = mx - st + r.randint(-2, 2)
        elif x < 0.75:
            amount = r.choice([10 - st, 9 - st, 11 - st])
        elif x < 0.88:
            amount = -r.randint(1, 100)
        else:
            amount = r.choice([0x7fffffff, -0x80000000, 1000000])
        announce = r.randrange(2)
        E.death_guard(c, [])
        E.caps(c)
        c.arg(slot)
        c.arg(amount)
        c.arg(announce)
        note.update(conds=conds, hc=hc, stmax=s32(mx), st=s32(st), hp=hp, amount=s32(amount),
                    announce=announce)
        c.note(**note)


def t_fatigue_char(ctx, E):
    fn = ctx.fn(0x0052af50)  # void FatigueCharacter(int slot, int amount, bool scale, W8SpellEffectResult*)
    for i in range(ctx.n(400)):
        r = ctx.rng('fatiguechar', i)
        c = ctx.case('fatiguechar.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        party = E.party(c, r, [1] * 8)
        E.globals(c, suspended=1 if r.random() < 0.06 else 0)
        _, blob, name = party[slot]
        ch = E.char(slot)
        note = {'char': name, 'slot': slot}
        conds = {}
        if r.random() < 0.25:
            conds[SLOWED] = r.choice([1, 30, INDEF])
        if r.random() < 0.2:
            conds[UNCONSCIOUS] = r.choice([INDEF, 5, 9998, 10000])
        if conds:
            c.set(ch + C_COND, conds_blob(conds))
            c.set(ch + C_HIGHEST, u32(highest_of(conds)))
        if r.random() < 0.25:
            c.set(ch + C_ENCH + 0xc * ENCH_HASTE + 8, u32(r.choice([1, 5, 100])))
            note['haste'] = 1
        load = None
        if r.random() < 0.7:
            load = r.choice([0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 5, -1]) if r.random() < 0.97 else 100
            c.set(ch + C_LOAD, u32(load))
        mx = blob.get_i32(C_STMAX)
        if r.random() < 0.2:
            mx = pick(r, [1, 2, 0x7fffffff], 10, 400, 0.15)
        x = r.random()
        if x < 0.06:
            st = r.choice([0, -1, -100])
        elif x < 0.2:
            st = r.choice([1, 2, 5])
        else:
            st = r.randint(1, max(1, mx))
        hp = blob.get_u32(C_HP)
        if r.random() < 0.05:
            hp = 0
        c.set(ch + C_HP, u32(hp))
        c.set(ch + C_STMAX, arr32([mx, st]))
        if r.random() < 0.6:
            c.set(ch + C_BAND, u32(r.choice([0, 0, 1, 2, 3, 4])))
        if r.random() < 0.4:
            c.set(ch + C_DEEP, bytes([r.randrange(2)]))
        x = r.random()
        if x < 0.06:
            amount = 0
        elif x < 0.5:
            amount = r.randint(1, 30)
        elif x < 0.7:
            amount = st + r.randint(-3, 3)
        elif x < 0.82:
            amount = r.randint(st // 3 if st > 0 else 1, max(2, st))
        elif x < 0.92:
            amount = -r.randint(1, 50)
        else:
            amount = r.choice([0x7fffffff, -0x80000000, 0x2000000, 1000000])
        scale = r.randrange(2)
        res = None
        if r.random() < 0.4:
            res = E.result(c)
        E.death_guard(c, [])
        E.caps(c)
        if res is not None:
            E.cap_result(c)
        c.arg(slot)
        c.arg(amount)
        c.arg(scale)
        c.arg(res if res is not None else 0)
        note.update(conds=conds, load=load, stmax=s32(mx), st=s32(st), hp=hp, amount=s32(amount),
                    scale=scale, report=res is not None)
        c.note(**note)


def t_damage_char(ctx, E):
    fn = ctx.fn(0x0052b7e0)  # void DamageCharacter(int slot, unsigned damage, bool announce)
    for i in range(ctx.n(250)):
        r = ctx.rng('damagechar', i)
        c = ctx.case('damagechar.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        occ = [1] * 8
        if r.random() < 0.03:
            occ[slot] = 0
        party = E.party(c, r, occ)
        E.globals(c, suspended=1 if r.random() < 0.06 else 0)
        _, blob, name = party[slot]
        ch = E.char(slot)
        note = {'char': name, 'slot': slot, 'occupied': occ[slot]}
        mx = blob.get_i32(C_HPMAX)
        hp = blob.get_u32(C_HP)
        adj = blob.get_i32(C_HPMAX + 8)
        x = r.random()
        if x < 0.05:
            mx = 0
        elif x < 0.1:
            hp = 0
        elif x < 0.4:
            hp = r.randint(1, max(1, mx))
        if r.random() < 0.2:
            adj = r.choice([-5, -50, 10, -0x7ffffff0])
        c.set(ch + C_HPMAX, arr32([mx, hp, adj]))
        if r.random() < 0.3:
            conds = {DRAINED: r.choice([INDEF, 5])}
            c.set(ch + C_COND, conds_blob(conds))
            c.set(ch + C_HIGHEST, u32(highest_of(conds)))
            note['drained'] = conds[DRAINED]
        if r.random() < 0.3:
            c.set(ch + C_ST, u32(r.choice([1, 3, 10, r.randint(1, 200)])))
        x = r.random()
        if x < 0.05:
            dmg = 0
        elif x < 0.6:
            dmg = r.randint(1, 20)
        elif x < 0.85:
            dmg = r.randint(1, max(1, hp // 2 + 1))
        elif x < 0.95:
            dmg = hp + r.randint(0, 40)          # takes the death path
        else:
            dmg = r.choice([0x7fffffff, 0x80000000, 0xffffffff])
        announce = r.randrange(2)
        E.death_guard(c, [slot])
        E.caps(c)
        c.arg(slot)
        c.arg(dmg)
        c.arg(announce)
        note.update(hpmax=mx, hp=hp, adj=adj, damage=dmg, announce=announce)
        c.note(**note)


def t_apply_damage_char(ctx, E):
    fn = ctx.fn(0x0052a890)  # unsigned ApplyDamageToCharacter(int, unsigned, bool quiet, bool announce,
    #                                bool short_notice, W8SpellEffectResult*, bool detailed)
    for i in range(ctx.n(400)):
        r = ctx.rng('applydmgchar', i)
        c = ctx.case('applydmgchar.%d' % i, fn, conv='c', ret='i')
        slot = r.randrange(8)
        occ = [1] * 8
        if r.random() < 0.02:
            occ[slot] = 0
        party = E.party(c, r, occ)
        surprise = 1 if r.random() < 0.85 else 0
        suspended = 1 if r.random() < 0.05 else 0
        E.globals(c, surprise=surprise, suspended=suspended)
        _, blob, name = party[slot]
        ch = E.char(slot)
        note = {'char': name, 'slot': slot, 'surprise': surprise, 'suspended': suspended,
                'occupied': occ[slot]}
        hp = blob.get_u32(C_HP)
        mx = blob.get_i32(C_HPMAX)
        x = r.random()
        if x < 0.05:
            hp = 0
        elif x < 0.35:
            hp = r.randint(1, max(1, mx))
        c.set(ch + C_HP, u32(hp))
        conds = {}
        if r.random() < 0.15:
            c.set(ch + C_PROF, u32(2))           # Valkyrie: cheat death
            note['valkyrie'] = 1
            if r.random() < 0.7:
                conds[UNCONSCIOUS] = r.choice([3, 6, 7, 8, INDEF])
        if surprise and r.random() < 0.25:
            conds[ASLEEP] = r.choice([1, 5, INDEF])
            if r.random() < 0.5:
                c.set(ch + C_ATTR + 0x14 * A_SEN + 4, u32(r.choice([0, 1, 50, 100, 125, 200])))
        if conds:
            c.set(ch + C_COND, conds_blob(conds))
            c.set(ch + C_HIGHEST, u32(highest_of(conds)))
        note['conds'] = conds
        x = r.random()
        if x < 0.06:
            amount = 0
        elif x < 0.5:
            amount = r.randint(1, 30)
        elif x < 0.7:
            amount = r.randint(1, max(1, hp))
        elif x < 0.92:
            amount = hp + r.randint(0, 30)     # lethal unless absorbed or cheated
        else:
            amount = r.choice([0x7fffffff, 0x80000000, 0xffffffff, 0x10000])
        if r.random() < 0.35:
            turns = r.choice([1, 3, 100])
            mag = r.choice([0, 1, amount & 0xffff, (amount - 1) & 0xffff, (amount + 1) & 0xffff,
                            r.randint(0, 200), 0xffff])
            ench = struct.pack('<IHHI', r.randint(1, 10), r.choice([0, 50]), mag, turns)
            c.set(ch + C_ENCH + 0xc * ENCH_GUARDIAN, ench)
            note['guardian'] = (mag, turns)
        quiet, announce, short, detailed = (r.randrange(2) for _ in range(4))
        res = None
        if r.random() < 0.6:
            res = E.result(c)
        E.death_guard(c, [slot])
        E.caps(c)
        if res is not None:
            E.cap_result(c)
        for v in (slot, amount, quiet, announce, short):
            c.arg(v)
        c.arg(res if res is not None else 0)
        c.arg(detailed)
        note.update(hp=hp, amount=amount & 0xffffffff, quiet=quiet, announce=announce,
                    short=short, detailed=detailed, report=res is not None)
        c.note(**note)


def t_apply_rolled_party(ctx, E):
    fn = ctx.fn(0x0052a820)  # void ApplyRolledHealthChangeToParty(const W8Dice*, W8SpellEffectResult*, int)
    S3 = ctx.scratch(3)
    for i in range(ctx.n(150)):
        r = ctx.rng('rolledparty', i)
        c = ctx.case('rolledparty.%d' % i, fn, conv='c', ret='v')
        occ = occupancy(r)
        party = E.party(c, r, occ)
        E.globals(c, surprise=1, suspended=1 if r.random() < 0.05 else 0)
        lower_pools(c, r, E, party, 'hp')
        dead = r.sample(range(8), r.randint(0, 2))
        for s in dead:
            cond = r.choice([DEAD, MISSING, UNCONSCIOUS])
            conds = {cond: INDEF}
            c.set(E.char(s) + C_COND, conds_blob(conds))
            c.set(E.char(s) + C_HIGHEST, u32(highest_of(conds)))
        count = r.choice([0, 1, 1, 2, 3, 5])
        sides = r.choice([0, 1, 4, 6, 8, 20])
        base = r.choice([0, 0, 1, 5, -3, 30, 200, r.randint(-10, 40)])
        c.set(S3, struct.pack('<hBB', base, count, sides))
        res = None
        if r.random() < 0.5:
            res = E.result(c)
        announce = r.randrange(2)
        E.death_guard(c, range(8))
        E.caps(c)
        if res is not None:
            E.cap_result(c)
        c.arg(S3)
        c.arg(res if res is not None else 0)
        c.arg(announce)
        c.note(occ=occ, dice='%dd%d%+d' % (count, sides, base), out=dead, report=res is not None,
               announce=announce)


def t_character_dies(ctx, E):
    fn = ctx.fn(0x0052abf0)  # void CharacterDies(int slot)
    # TURNCOAT is left out: lifting it re-picks the slot's targets from the live world
    clearable = [k for k in range(1, 18) if k != TURNCOAT]
    for i in range(ctx.n(100)):
        r = ctx.rng('chardies', i)
        c = ctx.case('chardies.%d' % i, fn, conv='c', ret='v')
        slot = r.randrange(8)
        occ = [1] * 8
        if r.random() < 0.03:
            occ[slot] = 0
        party = E.party(c, r, occ)
        E.globals(c)
        _, blob, name = party[slot]
        ch = E.char(slot)
        conds = {}
        for cond in r.sample(clearable, r.randint(0, 5)):
            conds[cond] = r.choice([1, 5, 60, INDEF])
        if r.random() < 0.2:
            conds[INFATUATED] = INDEF
        if conds:
            c.set(ch + C_COND, conds_blob(conds))
            c.set(ch + C_HIGHEST, u32(highest_of(conds)))
        if POISONED in conds:
            c.set(ch + 0xb09, u32(r.randint(1, 30)))  # condition_argument
        if r.random() < 0.3:
            c.set(ch + C_DEATHS, u32(r.choice([0, 5, 0x7fffffff, 0xffffffff])))
        if r.random() < 0.3:
            c.set(ch + C_HP, u32(r.randint(0, 100)))
        npc = None
        E.death_guard(c, [slot], set_npc=False)
        if r.random() < 0.15:
            npc = r.randrange(4)
            c.set(E.row(slot) + X_NPC, u32(npc))
            state = ((E.npcs.deref() + 0xc).deref() + 4 * npc).deref()
            c.cap(state + 4, 2, 'npc_spawned')
        else:
            c.set(E.row(slot) + X_NPC, u32(0xffffffff))
        E.caps(c)
        c.arg(slot)
        c.note(char=name, slot=slot, occupied=occ[slot], conds=conds, npc=npc)


# ---------------------------------------------------------------- party queries

def t_lowest_hp(ctx, E):
    fn = ctx.fn(0x0052c350)  # unsigned FindPartySlotWithLowestHitPoints(void)
    for i in range(ctx.n(250)):
        r = ctx.rng('lowesthp', i)
        c = ctx.case('lowesthp.%d' % i, fn, conv='c', ret='i')
        occ = occupancy(r)
        party = E.party(c, r, occ)
        zero_max = r.random() < 0.03
        share = r.choice([None, None, r.randint(0, 100)])
        info = []
        for s, blob, _ in party:
            ch = E.char(s)
            mx = blob.get_i32(C_HPMAX)
            if r.random() < 0.6:
                if share is not None:
                    hp = mx * share // 100
                else:
                    hp = r.choice([0, 1, mx, r.randint(0, max(1, mx)), r.randint(0, max(1, mx)),
                                   mx + 10])
                c.set(ch + C_HP, u32(hp))
                info.append(hp * 100 // mx if mx else None)
            else:
                info.append(None)
            if r.random() < 0.2:
                c.set(ch + C_HIGHEST, u32(r.choice([0, 5, 15, 17, 18, 19, 0x80000000])))
        if zero_max:
            c.set(E.char(r.randrange(8)) + C_HPMAX, u32(0))
        c.note(occ=occ, percents=info, zero_max=zero_max)


def t_lowest_sp(ctx, E):
    fn = ctx.fn(0x0052c3b0)  # unsigned FindPartySlotWithLowestSpellPoints(void)
    for i in range(ctx.n(250)):
        r = ctx.rng('lowestsp', i)
        c = ctx.case('lowestsp.%d' % i, fn, conv='c', ret='i')
        occ = occupancy(r)
        party = E.party(c, r, occ)
        for s, blob, _ in party:
            ch = E.char(s)
            if r.random() < 0.45:
                mx = [r.choice([0, 0, r.randint(1, 60), r.randint(1, 400)]) for _ in range(6)]
                if r.random() < 0.05:
                    mx[r.randrange(6)] = r.choice([-1000, 0x7fffffff, -0x80000000])
                left = [r.choice([m, 0, -r.randint(1, 30), r.randint(0, max(1, m)), m + 3]) for m in mx]
                c.set(ch + C_SPMAX, arr32(mx))
                c.set(ch + C_SPLEFT, arr32(left))
            elif r.random() < 0.3:
                left = [r.choice([0, -5, blob.get_i32(C_SPLEFT + 4 * k)]) for k in range(6)]
                c.set(ch + C_SPLEFT, arr32(left))
            if r.random() < 0.2:
                c.set(ch + C_HIGHEST, u32(r.choice([0, 5, 15, 17, 18, 19])))
        c.note(occ=occ)


def t_lowest_res4(ctx, E):
    fn = ctx.fn(0x0052c480)  # W8Character* FindPartyMemberWithLowestResistance4(void)
    for i in range(ctx.n(200)):
        r = ctx.rng('lowestres4', i)
        c = ctx.case('lowestres4.%d' % i, fn, conv='c', ret='p')
        occ = occupancy(r)
        party = E.party(c, r, occ)
        common = r.choice([None, None, r.choice([0, 50, 100, 998, 999])])
        res = []
        for s, blob, _ in party:
            ch = E.char(s)
            # marks the slot in the first dword so the returned pointer (compared as the
            # 32 bytes it points at) identifies the slot in both processes
            c.set(ch + C_VERSION, u32(0x57530000 + s))
            v = blob.get_u32(C_RES4)
            if common is not None and r.random() < 0.6:
                v = common
            elif r.random() < 0.5:
                v = r.choice([0, 1, r.randint(0, 100), r.randint(0, 100), 998, 999, 1000, 0xffffffff])
            c.set(ch + C_RES4, u32(v))
            res.append(v)
            if r.random() < 0.2:
                c.set(ch + C_HIGHEST, u32(r.choice([0, 15, 17, 18, 19])))
        c.note(occ=occ, res4=res)


def put_monster_list(c, E, ctx, monsters):
    """Scratch 5: a W8PList whose entries point at the monsters in scratch 6, wired into
    gXStatus.plsMonsterList for the duration of the call."""
    S5 = ctx.scratch(5)
    S6 = ctx.scratch(6)
    c.setp(S5, S5 + 0x10)
    c.set(S5 + 4, arr32([8, len(monsters)]))
    for k in range(len(monsters)):
        c.setp(S5 + 0x10 + 4 * k, S6 + k * M_STRIDE)
    c.setp(E.gx + GX_MONLIST, S5)


def fatigue_monster_final(hp, st, amount):
    if hp == 0:
        return None
    if amount != 0:
        st = (st - amount) & 0xffffffff if (amount & 0xffffffff) < (st & 0xffffffff) else 0
    return st & 0xffffffff


def set_monster(c, r, base, loc, hpmax, hp, stmax, st, conds, highest=None, band=None):
    c.set(base + M_LOC, arr32([loc, 0, r.choice(SPECIES)]))
    c.set(base + M_HPMAX, arr32([hpmax, hp, stmax, st]))
    if conds:
        c.set(base + M_COND, conds_blob(conds))
    if highest is not None:
        c.set(base + M_HIGHEST, u32(highest))
    if band is not None:
        c.set(base + M_BAND, u32(band))


def t_apply_queued_fatigue(ctx, E):
    fn = ctx.fn(0x0052c500)  # void ApplyQueuedFatigue(W8CombatSlot* op, unsigned amount, int)
    S4 = ctx.scratch(4)
    S6 = ctx.scratch(6)
    for i in range(ctx.n(150)):
        r = ctx.rng('queuedfatigue', i)
        c = ctx.case('queuedfatigue.%d' % i, fn, conv='c', ret='v')
        x = r.random()
        amount = r.choice([0, 1, 5, r.randint(1, 40), r.randint(40, 300), 0x7fffffff, 0xffffffff])
        if x < 0.6:
            slot = r.randrange(8)
            party = E.party(c, r, [1] * 8)
            E.globals(c)
            _, blob, name = party[slot]
            ch = E.char(slot)
            if r.random() < 0.5:
                c.set(ch + C_ST, u32(r.choice([0, 1, 5, r.randint(1, 200)])))
            c.set(S4, arr32([1, slot, 0xffffffff, 0xffffffff]))
            E.death_guard(c, [])
            E.caps(c)
            c.note(kind='character', char=name, slot=slot, amount=amount)
        elif x < 0.9:
            n = r.randint(1, 3)
            locs = [0x7ff00000 + i * 4 + k for k in range(n)]
            target = r.randrange(n)
            mons = []
            for k in range(n):
                stmax = r.choice([r.randint(10, 300), 1])
                st = r.randint(0, stmax)
                hp = r.choice([0, 1, 50, 200]) if r.random() < 0.2 else r.randint(1, 300)
                conds = {}
                if k == target:
                    fin = fatigue_monster_final(hp, st, amount)
                    if fin == 0:
                        conds[UNCONSCIOUS] = r.choice([INDEF, 10000, 0xffffffff])
                set_monster(c, r, S6 + k * M_STRIDE, locs[k], r.randint(1, 300), hp, stmax, st, conds,
                            band=r.randrange(5))
                mons.append((hp, stmax, st))
            put_monster_list(c, E, ctx, mons)
            c.set(S4, arr32([3, 0xffffffff, locs[target], 0xffffffff]))
            c.cap(S6, n * M_STRIDE, 'monsters')
            c.note(kind='monster', target=target, monsters=mons, amount=amount)
        else:
            kind = r.choice([0, 2, 4, 5, 6, 7, 8, 9, 0x80000001])
            party = E.party(c, r, [1] * 8)
            E.globals(c)
            c.set(S4, arr32([kind, r.randrange(8), 0xffffffff, 0xffffffff]))
            E.caps(c, rows=False, status=False)
            c.note(kind=kind, amount=amount)
        c.arg(S4)
        c.arg(amount)
        c.arg(r.choice([0, 1, 0xffffffff]))


# ---------------------------------------------------------------- monsters (scratch W8MonsterInfo)

def t_heal_monster(ctx, E):
    fn = ctx.fn(0x0052bfd0)  # void HealMonster(W8MonsterInfo*, unsigned amount, bool announce)
    S6 = ctx.scratch(6)
    for i in range(ctx.n(200)):
        r = ctx.rng('healmonster', i)
        c = ctx.case('healmonster.%d' % i, fn, conv='c', ret='v')
        mx = pick(r, [0, 1, -1, -100, 0x7fffffff], 1, 500, 0.15)
        x = r.random()
        if x < 0.1:
            hp = 0
        elif x < 0.2:
            hp = mx
        elif x < 0.25:
            hp = (mx + r.randint(1, 50)) & 0xffffffff
        else:
            hp = r.randint(1, max(1, mx - 1)) if mx > 1 else r.randint(1, 100)
        x = r.random()
        if x < 0.06:
            amount = 0
        elif x < 0.55:
            amount = r.randint(1, 80)
        elif x < 0.75:
            amount = (mx - hp + r.randint(-2, 2)) & 0xffffffff
        else:
            amount = r.choice([0xffffffff, 0x80000000, 0xffffff00, 0x7fffffff, 1000000])
        set_monster(c, r, S6, 0x7fe00000 + i, mx, hp, 100, 100, {})
        c.cap(S6, M_SIZE, 'monster')
        c.arg(S6)
        c.arg(amount)
        c.arg(0)
        c.note(hpmax=s32(mx), hp=hp & 0xffffffff, amount=amount & 0xffffffff)


def t_fatigue_monster(ctx, E):
    fn = ctx.fn(0x0052c070)  # void FatigueMonster(W8MonsterInfo*, unsigned amount, W8SpellEffectResult*)
    S6 = ctx.scratch(6)
    for i in range(ctx.n(250)):
        r = ctx.rng('fatiguemonster', i)
        c = ctx.case('fatiguemonster.%d' % i, fn, conv='c', ret='v')
        hp = 0 if r.random() < 0.08 else r.randint(1, 400)
        stmax = 0 if r.random() < 0.02 else pick(r, [1, 2, 0x7fffffff, -1], 10, 400, 0.1)
        x = r.random()
        if x < 0.1:
            st = 0
        elif x < 0.15:
            st = r.choice([-1, -50, stmax + 20])
        else:
            st = r.randint(1, max(1, stmax)) if stmax > 0 else r.randint(1, 50)
        x = r.random()
        if x < 0.08:
            amount = 0
        elif x < 0.55:
            amount = r.randint(1, 40)
        elif x < 0.75:
            amount = (st + r.randint(-3, 3)) & 0xffffffff
        else:
            amount = r.choice([0xffffffff, 0x80000000, 0x7fffffff, r.randint(1, 400)])
        conds = {}
        if r.random() < 0.3:
            conds[UNCONSCIOUS] = r.choice([5, 9998, INDEF, 10000])
        fin = fatigue_monster_final(hp, st, amount)
        if fin == 0 and (conds.get(UNCONSCIOUS, 0) & 0xffffffff) < INDEF:
            # SetMonsterCondition would look the scratch monster up in the world list
            conds[UNCONSCIOUS] = r.choice([INDEF, 10000, 0xffffffff])
        set_monster(c, r, S6, 0x7fd00000 + i, r.randint(1, 400), hp, stmax, st, conds,
                    band=r.randrange(6))
        res = None
        if r.random() < 0.4:
            res = E.result(c)
            E.cap_result(c)
        c.cap(S6, M_SIZE, 'monster')
        c.arg(S6)
        c.arg(amount)
        c.arg(res if res is not None else 0)
        c.note(hp=hp, stmax=s32(stmax), st=s32(st), amount=amount & 0xffffffff, conds=conds,
               report=res is not None)


def restore_monster_tail(hc, hp, stmax, st, amount):
    """None when RestoreMonsterStamina returns before the band pass, else the final
    stamina (unsigned)."""
    if (hc & 0xffffffff) >= DEAD or hp == 0:
        return None
    if (st & 0xffffffff) == (stmax & 0xffffffff):
        return None
    st = (st + amount) & 0xffffffff
    if st > (stmax & 0xffffffff):
        st = stmax & 0xffffffff
    return st


def t_restore_monster_stamina(ctx, E):
    fn = ctx.fn(0x0052c140)  # void RestoreMonsterStamina(W8MonsterInfo*, int amount, bool announce)
    S6 = ctx.scratch(6)
    for i in range(ctx.n(250)):
        r = ctx.rng('restmonst', i)
        c = ctx.case('restmonst.%d' % i, fn, conv='c', ret='v')
        hp = 0 if r.random() < 0.06 else r.randint(1, 400)
        stmax = 0 if r.random() < 0.02 else pick(r, [1, 9, 10, 11, 0x7fffffff, -1], 10, 400, 0.15)
        x = r.random()
        if x < 0.1:
            st = stmax
        elif x < 0.25:
            st = r.choice([0, 1, 5, 9])
        elif x < 0.3:
            st = r.choice([-1, -50, stmax + 20])
        else:
            st = r.randint(0, max(0, stmax)) if stmax > 0 else r.randint(0, 20)
        x = r.random()
        if x < 0.06:
            amount = 0
        elif x < 0.5:
            amount = r.randint(1, 40)
        elif x < 0.62:
            amount = stmax - st + r.randint(-2, 2)
        elif x < 0.75:
            amount = r.choice([10 - st, 9 - st, 11 - st])
        elif x < 0.88:
            amount = -r.randint(1, 100)
        else:
            amount = r.choice([0x7fffffff, -0x80000000, 1000000])
        conds = {}
        if r.random() < 0.35:
            conds[UNCONSCIOUS] = r.choice([INDEF, INDEF, 5, 9998])
        hc = highest_of(conds)
        y = r.random()
        if y < 0.06:
            hc = r.choice([DEAD, MISSING, 0x80000000])
        tail = restore_monster_tail(hc, hp, stmax, st, amount)
        if tail is not None and conds.get(UNCONSCIOUS) == INDEF and tail >= 10:
            # ClearMonsterCondition would look the scratch monster up in the world list
            conds[UNCONSCIOUS] = r.choice([0, 9998, 10000])
        set_monster(c, r, S6, 0x7fc00000 + i, r.randint(1, 400), hp, stmax, st, conds, highest=hc,
                    band=r.randrange(6))
        c.cap(S6, M_SIZE, 'monster')
        c.arg(S6)
        c.arg(amount)
        c.arg(0)
        c.note(hc=hc, hp=hp, stmax=s32(stmax), st=s32(st), amount=s32(amount), conds=conds)


def cases(ctx):
    E = Env(ctx)
    for t in (t_get_realm_sp, t_sum_sp_left, t_sum_sp, t_fatigue_armor_penalty, t_compare_deficits,
              t_spell_cast_fatigue, t_monster_action_fatigue, t_char_action_fatigue,
              t_recalc_hp, t_recalc_stamina, t_recalc_realm_sp, t_rebuild_ceilings,
              t_spend_sp, t_restore_realm_sp, t_drain_realm_sp, t_drain_char_sp, t_restore_evenly,
              t_drain_party_sp, t_restore_party_sp,
              t_heal_char, t_heal_party_dice, t_restore_party_stamina_dice, t_restore_stamina,
              t_fatigue_char, t_damage_char, t_apply_damage_char, t_apply_rolled_party,
              t_character_dies,
              t_lowest_hp, t_lowest_sp, t_lowest_res4, t_apply_queued_fatigue,
              t_heal_monster, t_fatigue_monster, t_restore_monster_stamina):
        t(ctx, E)
