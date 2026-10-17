"""Probe: live monsters of the level in both exes (gXStatus.plsMonsterList and adjacent lists).
No function call - only a memory dump along a pointer chain."""

GX_MONLIST, GX_GROUPS, GX_UNBORN, GX_ENCGROUPS = 0x8f5, 0x8f9, 0x901, 0x905


def cases(ctx):
    gx = ctx.g('gXStatus')
    for name, off in (('mon', GX_MONLIST), ('grp', GX_GROUPS), ('unborn', GX_UNBORN),
                      ('enc', GX_ENCGROUPS)):
        a = gx + off
        c = ctx.case('%s.ptr' % name, None)
        c.dump(a, 4, 'ptr')
        c = ctx.case('%s.list' % name, None)
        c.dump(a.deref(), 0x20, 'list')
        c = ctx.case('%s.data' % name, None)
        c.dump(a.deref().deref(), 0x20, 'data')
        c = ctx.case('%s.first' % name, None)
        c.dump(a.deref().deref().deref(), 0x40, 'first')
    c = ctx.case('gx.head', None)
    c.dump(gx + 0x8dc, 0x40, 'gx8dc')
