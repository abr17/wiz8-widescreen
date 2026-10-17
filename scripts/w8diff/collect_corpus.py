"""Save characters from w8diff_out_retail.txt (plan _corpus_dump) to
build\\w8diff\\corpus\\<save>_<slot>.bin. Empty slots (zero name) are skipped.
python -I collect_corpus.py --save "Before Bayjin" """
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from w8diff.symbols import ROOT  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--save', required=True)
a = ap.parse_args()
out_dir = os.path.join(ROOT, 'build', 'w8diff', 'corpus')
os.makedirs(out_dir, exist_ok=True)
tag = re.sub(r'[^A-Za-z0-9]+', '_', a.save).strip('_')
n = 0
for line in open(os.path.join(ROOT, 'games', 'work', 'w8diff_out_retail.txt'), encoding='ascii'):
    if not line.startswith('D '):
        continue
    parts = line.split()
    if len(parts) < 4 or parts[3] == 'unreadable':
        continue
    data = bytes.fromhex(parts[3])
    if len(data) != 0x1862 or data[5:7] == b'\0\0':
        continue
    slot = parts[1].rsplit('char', 1)[-1]
    open(os.path.join(out_dir, '%s_%s.bin' % (tag, slot)), 'wb').write(data)
    n += 1
print('saved %d characters from %s' % (n, a.save))
