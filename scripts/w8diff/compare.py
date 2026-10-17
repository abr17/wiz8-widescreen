"""Compare w8diff_out_retail.txt and w8diff_out_port.txt.
python -I compare.py [--work games\\work] [--max 8]
Writes build\\w8diff\\report.txt (per function, first mismatches with their inputs) and report.json."""
import argparse
import collections
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from w8diff.symbols import ROOT  # noqa: E402


def parse(path):
    res = {'header': {}, 'regions': {}, 'cases': {}, 'end': None}
    if not os.path.exists(path):
        return res
    for line in open(path, encoding='ascii', errors='replace'):
        line = line.rstrip('\n')
        if not line:
            continue
        tag, _, rest = line.partition(' ')
        if tag == 'R':
            parts = rest.split(' ')
            cid, status = parts[0], parts[1]
            kv = {}
            for p in parts[2:]:
                k, _, v = p.partition('=')
                kv[k] = v
            res['cases'][cid] = {'status': status, 'kv': kv, 'caps': {}, 'dumps': {}}
        elif tag == 'C':
            parts = rest.split(' ')
            cid, idx = parts[0], int(parts[1])
            changes = {}
            olds = {}
            unreadable = False
            for p in parts[2:]:
                if p == 'unreadable':
                    unreadable = True
                    continue
                off, _, hx = p.partition(':')
                off = int(off, 16)
                hx, _, old = hx.partition('/')   # "new/old" (old = bytes before the call)
                data = bytes.fromhex(hx)
                for k, b in enumerate(data):
                    changes[off + k] = b
                for k, b in enumerate(bytes.fromhex(old)):
                    olds[off + k] = b
            c = res['cases'].get(cid)
            if c is not None:
                c['caps'][idx] = None if unreadable else changes
                c.setdefault('olds', {})[idx] = olds
        elif tag == 'D':
            parts = rest.split(' ')
            c = res['cases'].get(parts[0])
            if c is not None:
                c['dumps'][int(parts[1])] = parts[2] if len(parts) > 2 else ''
        elif tag == 'G':
            parts = rest.split(' ')
            res['regions'][parts[0]] = parts[1:]
        elif tag == 'END':
            res['end'] = rest
        else:
            res['header'][tag] = rest
    return res


def f32(bits_hex):
    d = struct.unpack('<d', bytes.fromhex(bits_hex))[0]
    try:
        return struct.unpack('<f', struct.pack('<f', d))[0]
    except OverflowError:
        return d


def ret_value(case, ret):
    kv = case['kv']
    eax = int(kv.get('eax', '0'), 16)
    edx = int(kv.get('edx', '0'), 16)
    if ret == 'v':
        return None
    if ret in ('b', 'u8'):
        return eax & 0xff
    if ret == 'i8':
        v = eax & 0xff
        return v - 256 if v >= 128 else v
    if ret == 'u16':
        return eax & 0xffff
    if ret == 'i16':
        v = eax & 0xffff
        return v - 65536 if v >= 32768 else v
    if ret == 'q':
        return (edx << 32) | eax
    if ret in ('f', 'd'):
        fp = kv.get('fp', '-')
        if fp == '-':
            return 'no-fp(fd=%s)' % kv.get('fd')
        return f32(fp) if ret == 'f' else struct.unpack('<d', bytes.fromhex(fp))[0]
    if ret == 'p':
        return kv.get('y')
    if ret in ('w', 'c'):
        return kv.get('s')
    v = eax
    return v - (1 << 32) if v >= (1 << 31) else v  # 'i'


def fp_close(rv, pv, ret):
    """Small floating-point difference: VC6 keeps intermediate values in 80-bit
    x87 registers, MSVC 2022 rounds to float on every assignment. Such
    differences in the last bits are not porting errors and are counted separately."""
    if not isinstance(rv, float) or not isinstance(pv, float):
        return False
    if rv != rv and pv != pv:
        return True
    if ret == 'f':
        a = struct.unpack('<i', struct.pack('<f', rv))[0]
        b = struct.unpack('<i', struct.pack('<f', pv))[0]
        if (a < 0) != (b < 0):
            return abs(rv - pv) < 1e-30
        return abs(a - b) <= 4
    return abs(rv - pv) <= 1e-9 * max(1.0, abs(rv), abs(pv))


CHAR_SIZE = 0x1862
# W8Character: health/stamina regeneration rates and accumulators and
# spell_regen_rates[12] - 16 consecutive floats (x87 results)
CHAR_REGEN_FLOATS = list(range(0xb69, 0xba9, 4))


def float_offsets(capm):
    """float fields of a region: those marked in the spec, plus the regeneration fields of
    party character arrays (g_status+0x4*...) where the spec did not mark them."""
    out = set(capm.get('floats', []))
    if capm['len'] % CHAR_SIZE == 0 and capm.get('addr', '').startswith('g_status+0x4*'):
        for n in range(capm['len'] // CHAR_SIZE):
            out.update(n * CHAR_SIZE + o for o in CHAR_REGEN_FLOATS)
    return sorted(out)


def describe_bytes(changes, offs):
    return ' '.join('%x:%s' % (o, '%02x' % changes[o] if o in changes else '..') for o in offs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', default=os.path.join(ROOT, 'games', 'work'))
    ap.add_argument('--max', type=int, default=8)
    ap.add_argument('--meta', default=os.path.join(ROOT, 'build', 'w8diff', 'meta.json'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'build', 'w8diff'))
    a = ap.parse_args()
    meta = json.load(open(a.meta, encoding='utf-8'))
    r = parse(os.path.join(a.work, 'w8diff_out_retail.txt'))
    p = parse(os.path.join(a.work, 'w8diff_out_port.txt'))

    per_fn = collections.OrderedDict()
    diffs = []
    for cid, m in meta.items():
        key = '%s %s (%s)' % (m['spec'], m['fn'] or '-', m['retail'] or '-')
        st = per_fn.setdefault(key, {'cases': 0, 'diff': 0, 'missing': 0, 'both_exc': 0,
                                     'fp_noise': 0, 'kinds': collections.Counter()})
        st['cases'] += 1
        rc, pc = r['cases'].get(cid), p['cases'].get(cid)
        if rc is None or pc is None:
            st['missing'] += 1
            continue
        problems = []
        rs, ps = rc['status'], pc['status']
        if rs.split('@')[0] != ps.split('@')[0]:
            problems.append(('status', rs, ps))
        elif rs.startswith('E'):
            st['both_exc'] += 1
        ra, pa = rc['kv'].get('a', '-'), pc['kv'].get('a', '-')
        if ra != pa:
            problems.append(('asserts', ra, pa))
        if rs == 'ok' and ps == 'ok':
            rv, pv = ret_value(rc, m['ret']), ret_value(pc, m['ret'])
            if rv != pv:
                if fp_close(rv, pv, m['ret']):
                    st['fp_noise'] += 1
                else:
                    problems.append(('return', rv, pv))
            for idx, capm in enumerate(m['caps']):
                rch, pch = rc['caps'].get(idx), pc['caps'].get(idx)
                if rch is None or pch is None:
                    if rch != pch:
                        problems.append(('cap ' + capm['name'], 'unreadable' if rch is None else 'ok',
                                         'unreadable' if pch is None else 'ok'))
                    continue
                ignore = set()
                for o in capm['ignore']:
                    ignore.update(range(o, o + 4))
                # float fields: values after the call are close (fp_close) - precision noise,
                # not a mismatch. A byte that a side did not change equals the byte before
                # the call (it is in the other side's record; if it did not change anywhere, it is
                # the same in both).
                rold = rc.get('olds', {}).get(idx, {})
                pold = pc.get('olds', {}).get(idx, {})
                for fo in float_offsets(capm):
                    if not any(fo + k in rch or fo + k in pch for k in range(4)):
                        continue
                    va, vb = bytearray(4), bytearray(4)
                    known = True
                    for k in range(4):
                        o = fo + k
                        old = rold.get(o, pold.get(o))
                        if o in rch or o in pch:
                            if old is None and (o not in rch or o not in pch):
                                known = False
                                break
                        va[k] = rch.get(o, old if old is not None else 0)
                        vb[k] = pch.get(o, old if old is not None else 0)
                    if not known:
                        continue
                    fa = struct.unpack('<f', bytes(va))[0]
                    fb = struct.unpack('<f', bytes(vb))[0]
                    if fa != fb and fp_close(fa, fb, 'f'):
                        ignore.update(range(fo, fo + 4))
                        st['fp_noise'] += 1
                offs = sorted(o for o in set(rch) | set(pch)
                              if o not in ignore and rch.get(o) != pch.get(o))
                if offs:
                    problems.append(('cap ' + capm['name'], describe_bytes(rch, offs[:24]),
                                     describe_bytes(pch, offs[:24]) + (' (+%d)' % (len(offs) - 24)
                                                                       if len(offs) > 24 else '')))
            for idx, dm in enumerate(m['dumps']):
                rd, pd = rc['dumps'].get(idx), pc['dumps'].get(idx)
                if rd == pd:
                    continue
                if not rd or not pd or rd == 'unreadable' or pd == 'unreadable' or len(rd) != len(pd):
                    problems.append(('dump ' + dm['name'], str(rd)[:64], str(pd)[:64]))
                    continue
                rb, pb = bytes.fromhex(rd), bytes.fromhex(pd)
                skip = set()
                for o in dm.get('ignore', []):
                    skip.update(range(o, o + 4))
                for fo in dm.get('floats', []):
                    fa = struct.unpack_from('<f', rb, fo)[0]
                    fb = struct.unpack_from('<f', pb, fo)[0]
                    if fa != fb and fp_close(fa, fb, 'f'):
                        skip.update(range(fo, fo + 4))
                        st['fp_noise'] += 1
                offs = [o for o in range(len(rb)) if rb[o] != pb[o] and o not in skip]
                if offs:
                    rmap = {o: rb[o] for o in offs}
                    pmap = {o: pb[o] for o in offs}
                    problems.append(('dump ' + dm['name'], describe_bytes(rmap, offs[:24]),
                                     describe_bytes(pmap, offs[:24]) + (' (+%d)' % (len(offs) - 24)
                                                                        if len(offs) > 24 else '')))
        if problems:
            st['diff'] += 1
            for pr in problems:
                st['kinds'][pr[0]] += 1
            diffs.append({'case': cid, 'fn': key, 'args': m['args'], 'info': m['info'],
                          'problems': [list(map(str, x)) for x in problems]})

    lines = []
    lines.append('retail: %s; port: %s' % (r['end'], p['end']))
    lines.append('cw-native retail=%s port=%s' % (r['header'].get('cw-native'), p['header'].get('cw-native')))
    total = sum(s['cases'] for s in per_fn.values())
    bad = sum(s['diff'] for s in per_fn.values())
    lines.append('cases: %d, with differences: %d' % (total, bad))
    lines.append('')
    for key, s in per_fn.items():
        flag = 'DIFF' if s['diff'] else ('MISS' if s['missing'] else 'ok  ')
        lines.append('%s %-70s %5d cases, %4d diff, %d missing, %d both-exception, %d fp-noise %s' % (
            flag, key, s['cases'], s['diff'], s['missing'], s['both_exc'], s['fp_noise'],
            dict(s['kinds']) if s['kinds'] else ''))
    lines.append('')
    shown = collections.Counter()
    for d in diffs:
        if shown[d['fn']] >= a.max:
            continue
        shown[d['fn']] += 1
        lines.append('== %s  [%s]' % (d['case'], d['fn']))
        lines.append('   args: %s %s' % (d['args'], d['info'] if d['info'] else ''))
        for kind, rv, pv in d['problems']:
            lines.append('   %-12s retail: %s' % (kind, rv))
            lines.append('   %-12s port:   %s' % ('', pv))
    text = '\n'.join(lines)
    out_dir = a.out
    open(os.path.join(out_dir, 'report.txt'), 'w', encoding='utf-8').write(text + '\n')
    json.dump({'per_fn': {k: {**v, 'kinds': dict(v['kinds'])} for k, v in per_fn.items()},
               'diffs': diffs}, open(os.path.join(out_dir, 'report.json'), 'w', encoding='utf-8'),
              indent=1)
    print('\n'.join(lines[:3 + len(per_fn) + 1]))
    print('report: build\\w8diff\\report.txt')


if __name__ == '__main__':
    main()
