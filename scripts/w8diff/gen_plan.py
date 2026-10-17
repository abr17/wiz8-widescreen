"""Generate call plans for both exes from the specs.
python -I gen_plan.py [--specs a,b,...] [--scale 1.0] [--out games\\work]
  specs: module names from scripts/w8diff/specs (default: all except those starting with _)
Writes <out>\\w8diff_plan_retail.txt, <out>\\w8diff_plan_port.txt and build\\w8diff\\meta.json."""
import argparse
import glob
import importlib.util
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from w8diff.api import Ctx, Plan, Addr  # noqa: E402
from w8diff.symbols import Symbols, ROOT  # noqa: E402

CORPUS = os.path.join(ROOT, 'build', 'w8diff', 'corpus')


def load_corpus():
    out = []
    for path in sorted(glob.glob(os.path.join(CORPUS, '*.bin'))):
        data = open(path, 'rb').read()
        if len(data) == 0x1862:
            out.append((os.path.basename(path)[:-4], data))
    return out


def load_spec(name):
    path = os.path.join(HERE, 'specs', name + '.py')
    spec = importlib.util.spec_from_file_location('w8spec_' + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--specs', default='')
    ap.add_argument('--scale', type=float, default=1.0)
    ap.add_argument('--out', default=os.path.join(ROOT, 'games', 'work'))
    ap.add_argument('--no-ready', action='store_true')
    ap.add_argument('--meta', default=os.path.join(ROOT, 'build', 'w8diff', 'meta.json'))
    a = ap.parse_args()

    syms = Symbols()
    corpus = load_corpus()
    names = [s for s in a.specs.split(',') if s] or sorted(
        os.path.basename(p)[:-3] for p in glob.glob(os.path.join(HERE, 'specs', '*.py'))
        if not os.path.basename(p).startswith('_'))

    plan = Plan()
    screen = Addr(('sym', syms.global_('g_current_screen_state')))
    if not a.no_ready:
        for proc in ('retail', 'port'):
            # main game screen (W8_SCREEN_MAIN_GAME = 7) for 60 consecutive frames
            plan.header[proc].append('ready %s 7 3C' % screen.render(proc))
    status = syms.global_('g_status')
    for proc in ('retail', 'port'):
        plan.header[proc].append('region g_status %X 2500' % status[proc])

    meta = {}
    report = []
    for name in names:
        ctx = Ctx(syms, name, corpus, a.scale)
        try:
            mod = load_spec(name)
            mod.cases(ctx)
        except Exception as e:  # the spec failed to build - report it and continue
            report.append('%s: ERROR %s' % (name, e))
            traceback.print_exc()
            continue
        bad = 0
        for c in ctx.cases:
            # core limits (w8diff_core.c): 256 memory operations and 24 arguments per case
            text = c.render('retail', {d: 0 for d in [p for k, _, p, _ in c.ops if k == 'setb']})
            nops = sum(1 for line in text.split('\n')
                       if line.split(' ', 1)[0] in ('set', 'setb', 'setp', 'fill', 'keep', 'cap', 'dump'))
            nargs = sum(1 for line in text.split('\n') if line.startswith('arg '))
            if nops > 256 or nargs > 24:
                bad += 1
                continue
            plan.cases.append(c)
            meta[c.id] = c.meta()
        report.append('%s: %d cases%s' % (name, len(ctx.cases) - bad,
                                          (' (%d dropped: over core limits)' % bad) if bad else ''))

    os.makedirs(a.out, exist_ok=True)
    for proc in ('retail', 'port'):
        plan.write(proc, os.path.join(a.out, 'w8diff_plan_%s.txt' % proc))
    os.makedirs(os.path.dirname(a.meta), exist_ok=True)
    json.dump(meta, open(a.meta, 'w', encoding='utf-8'), indent=0)
    print('\n'.join(report))
    print('total cases: %d, corpus characters: %d' % (len(plan.cases), len(corpus)))


if __name__ == '__main__':
    main()
