"""Prepare per-spec mismatch triage files: build\\w8diff\\triage\\<spec>.txt.
python -I triage_prep.py [--runs build\\w8diff\\runs] [--prefer nessie_monsters] [--max 15]
For each function with mismatches: case count, examples (inputs, what differed).
Drops mismatches that are only in the low bytes of character regeneration float fields
(x87 noise that the old output format could not recognize)."""
import argparse
import collections
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from w8diff.symbols import ROOT  # noqa: E402

CHAR = 0x1862


def regen_noise(problems, caps):
    any_cap = False
    for kind, rv, pv in problems:
        if not kind.startswith('cap '):
            return False
        c = caps.get(kind[4:])
        if not c or c['len'] % CHAR:
            return False
        any_cap = True
        for side in (rv, pv):
            for t in side.split():
                if ':' not in t:
                    continue
                o = int(t.split(':')[0], 16) % CHAR
                if not (0xb69 <= o < 0xba9) or (o - 0xb69) % 4 > 1:
                    return False
    return any_cap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', default=os.path.join(ROOT, 'build', 'w8diff', 'runs'))
    ap.add_argument('--prefer', default='nessie_monsters')
    ap.add_argument('--max', type=int, default=15)
    ap.add_argument('--out', default=os.path.join(ROOT, 'build', 'w8diff', 'triage'))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    # spec -> run dir (the preferred run overrides the others)
    owner = {}
    dirs = sorted(glob.glob(os.path.join(a.runs, '*')))
    dirs.sort(key=lambda d: os.path.basename(d) == a.prefer)
    for d in dirs:
        if not os.path.exists(os.path.join(d, 'report.json')):
            continue
        meta = json.load(open(os.path.join(d, 'meta.json'), encoding='utf-8'))
        for m in meta.values():
            owner[m['spec']] = d
    summary = {}
    for spec, d in sorted(owner.items()):
        rep = json.load(open(os.path.join(d, 'report.json'), encoding='utf-8'))
        meta = json.load(open(os.path.join(d, 'meta.json'), encoding='utf-8'))
        save = 'Before Bayjin'
        if os.path.exists(os.path.join(d, 'save.txt')):
            save = open(os.path.join(d, 'save.txt'), encoding='utf-8-sig').read().strip()
        elif os.path.basename(d) == 'nessie_monsters':
            save = 'Before Nessie'
        per = collections.OrderedDict()
        noise = collections.Counter()
        for k, v in rep['per_fn'].items():
            if k.split(' ')[0] == spec:
                per[k] = {'cases': v['cases'], 'diffs': []}
        for x in rep['diffs']:
            if x['fn'] not in per:
                continue
            caps = {c['name']: c for c in meta[x['case']]['caps']}
            if regen_noise(x['problems'], caps):
                noise[x['fn']] += 1
                continue
            per[x['fn']]['diffs'].append(x)
        lines = ['spec %s; run dir %s; save "%s"' % (spec, os.path.relpath(d, ROOT), save),
                 'setup of a case: find the line "case <id>" in %s\\w8diff_plan_retail.txt '
                 '(ops until "end"); raw results: lines "R <id>" / "C <id>" in w8diff_out_*.txt' %
                 os.path.relpath(d, ROOT), '']
        bad = 0
        for k, v in per.items():
            n = len(v['diffs'])
            if not n and not noise[k]:
                continue
            bad += n
            lines.append('%-70s %5d cases %4d diffs (+%d x87 regen-float noise dropped)' % (
                k, v['cases'], n, noise[k]))
        lines.append('')
        for k, v in per.items():
            for x in v['diffs'][:a.max]:
                lines.append('== %s  [%s]' % (x['case'], k))
                lines.append('   args: %s %s' % (x['args'], json.dumps(x['info']) if x['info'] else ''))
                for kind, rv, pv in x['problems']:
                    lines.append('   %-14s retail: %s' % (kind, rv))
                    lines.append('   %-14s port:   %s' % ('', pv))
        open(os.path.join(a.out, spec + '.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
        summary[spec] = {'diffs': bad, 'noise': sum(noise.values()), 'run': os.path.relpath(d, ROOT),
                         'fns': [k for k, v in per.items() if v['diffs']]}
    json.dump(summary, open(os.path.join(a.out, 'summary.json'), 'w', encoding='utf-8'), indent=1)
    for s, v in sorted(summary.items(), key=lambda x: -x[1]['diffs']):
        print('%-26s %5d diffs, %4d noise, %2d fns  %s' % (s, v['diffs'], v['noise'], len(v['fns']), v['run']))


if __name__ == '__main__':
    main()
