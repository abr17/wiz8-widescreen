import sys, os, json, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sti8 import read_sti8
root = r'C:\dev\wiz8-ws\build\stretch\en'
def find(n):
    return [p for p in glob.glob(root + r'\**\*.STI', recursive=True) if os.path.basename(p).lower() == n.lower()][0]
main = [('S087_0_0','main_textbox_back.sti',0,384,152,249), ('S085_0_0','main_roof.sti',0,640,300,340),
        ('S07E_0_6','main_bottom_bar.sti',6,185,84,100),
        ('S1B7_0_1','journal_base.sti',1,640,248,345),
        ('S0F9_0_0','save_load_gamelists.sti',0,352,171,299), ('S0F9_0_1','save_load_gamelists.sti',1,352,171,299),
        ('S0F9_0_2','save_load_gamelists.sti',2,352,171,299), ('S0F9_0_3','save_load_gamelists.sti',3,352,171,299)]
sub = [('S1A9_0_1','Npc_bottompanel.sti',1,100,197), ('S097_0_1','item_bottompanel.sti',1,100,197),
       ('S190_0_1','MagicBottomNew.sti',1,61,141), ('S1B1_0_1','traps_bottompanel.sti',1,152,184),
       ('S0EE_0_1','options_base.sti',1,102,199), ('S0F7_0_0','save_load_back.sti',0,102,199),
       ('S0F3_0_0','options_pagingbase.sti',0,130,159)]
cfg = []
for k, n, i, w, a, b in main:
    p = find(n); sx, sy, iw, ih, _ = read_sti8(p)[1][i]
    print(k, 'sx', sx, 'sy', sy, 'w', iw, 'h', ih, 'call width', w)
    cfg.append(dict(key=k, sti=p, image=i, width=w, cut=[a, b]))
    if k == 'S085_0_0':
        cfg[-1]['src'] = [235, 455]  # the whole roof gutter without the dark left edge (x 177..230)
for k, n, i, a, b in sub:
    p = find(n); sx, sy, iw, ih, _ = read_sti8(p)[1][i]
    print(k, 'sx', sx, 'sy', sy, 'w', iw, 'h', ih)
    cfg.append(dict(key=k, sti=p, image=i, width=sx + iw, cut=[sx + a, sx + b]))
for c in cfg:
    if c['cut'][1] - c['cut'][0] == 97:
        c['period'] = 97  # the background pattern repeats exactly every 97 px (find_slice.py)
json.dump(cfg, open(r'C:\dev\wiz8-ws\build\stretch\config.json', 'w'), indent=1)



