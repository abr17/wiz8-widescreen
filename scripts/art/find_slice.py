"""Finds an image slice for stretching by repetition (without an "accordion" look).
python find_slice.py <image.png> x_from x_to [y_from y_to] [min_len=16] [max_len=120]
Searches the strip [x_from, x_to) for a slice [a, a+L) that joins with itself
best when repeated: compares column a-1 with column a+L-1 and column a with column a+L
(what ends up adjacent at the joint), over all rows y_from..y_to. Prints the best
candidates: joint error (mean brightness difference per pixel) and length."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import artkit

p = sys.argv[1]
x0, x1 = int(sys.argv[2]), int(sys.argv[3])
y0 = int(sys.argv[4]) if len(sys.argv) > 5 else 0
w, h, rows = artkit.read_png(p)
y1 = int(sys.argv[5]) if len(sys.argv) > 5 else h
mn = int(sys.argv[6]) if len(sys.argv) > 6 else 16
mx = int(sys.argv[7]) if len(sys.argv) > 7 else 120
lum = [[sum(px[:3]) / 3.0 for px in row] for row in rows]


def coldiff(a, b):
    return sum(abs(lum[y][a] - lum[y][b]) for y in range(y0, y1)) / (y1 - y0)


res = []
for a in range(x0 + 1, x1):
    for L in range(mn, mx + 1):
        if a + L >= x1:
            break
        e = (coldiff(a - 1, a + L - 1) + coldiff(a, a + L)) / 2
        res.append((e, a, L))
res.sort()
seen = []
for e, a, L in res:
    if any(abs(a - a2) < 6 and abs(L - L2) < 6 for _, a2, L2 in seen):
        continue
    seen.append((e, a, L))
    print('err %.2f  slice [%d, %d)  len %d' % (e, a, a + L, L))
    if len(seen) >= 10:
        break
