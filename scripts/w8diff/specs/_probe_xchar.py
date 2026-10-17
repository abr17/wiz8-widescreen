"""Probe: XChar[0..7].npc_index and fOccupied in both exes, plus g_npc_states (no call)."""

ROW, X_NPC = 0x106, 0xfa


def cases(ctx):
    rows = (ctx.g('g_status') + 8).deref()
    for s in range(8):
        c = ctx.case('row%d' % s, None)
        c.dump(rows + s * ROW + X_NPC, 4, 'npc_index')
    c = ctx.case('npcstates', None)
    c.dump(ctx.g('g_npc_states').deref(), 0x10, 'plist')
