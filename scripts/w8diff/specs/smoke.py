"""Self-test of the stand: Random() with different seeds, CalcAttacks on a party
character, a call with a null pointer (the exception must be caught in both exes)."""
from w8diff.api import F32


def cases(ctx):
    rnd = ctx.fn(0x0040efa0)          # Random(UINT32 range)
    for i in range(20):
        c = ctx.case('random.%d' % i, rnd, conv='c', ret='i')
        c.arg(100 + i * 37)
        c.seed = 1000 + i

    calc = ctx.fn(0x004ee220)          # CalcAttacks(W8Character*)
    for slot in range(6):
        c = ctx.case('calcattacks.slot%d' % slot, calc, conv='c', ret='v')
        c.arg(ctx.char(slot))
        c.cap(ctx.char(slot), 0x1862, 'char')

    c = ctx.case('calcattacks.null', calc, conv='c', ret='v')
    c.arg(0)

    # NaN: in the original the 'angle < 0' loop never ends with NaN (tests hang handling)
    norm = ctx.fn(0x00517c60)          # float NormalizeAngle(float)
    for i, v in enumerate([1.0, -1.0, 7.0, float('nan'), 3.0]):
        c = ctx.case('normalize.%d' % i, norm, conv='c', ret='f')
        c.arg(F32(v))
