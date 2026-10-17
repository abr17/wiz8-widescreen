"""Dump the characters of the loaded save (retail only): 8 slots
g_status.buffers.Char -> build\\w8diff\\corpus\\<save>_<slot>.bin (via collect_corpus.py)."""


def cases(ctx):
    for slot in range(8):
        c = ctx.case('char%d' % slot, None)
        c.dump(ctx.char(slot), 0x1862, 'char%d' % slot)
