#!/usr/bin/env python3
"""Re-derive word alignment from raw Microwire frames instead of assuming it.

Each frame is 40 bits: 16 command bits, then a dummy 0, then 16 data bits.
That puts data at offset 17 - but if the chip emits a different number of
dummy bits, every word is individually wrong. Sweep every offset and search.
"""
import sys, collections
sys.path.insert(0, 'work')
from findodo import search, swap16

raw = open('dumps/raw-frames.bin', 'rb').read()
frames = [raw[i*5:(i+1)*5] for i in range(128)]
bits = [''.join(f'{b:08b}' for b in fr) for fr in frames]
LO, HI = 216500, 217500

print(f"{'off':>4} {'distinct':>9} {'0xff':>5}  verdict")
for off in range(0, 25):
    words = []
    for b in bits:
        chunk = b[off:off+16]
        if len(chunk) < 16:
            chunk = chunk.ljust(16, '0')
        words.append(int(chunk, 2))
    img = b"".join(w.to_bytes(2, 'big') for w in words)
    c = collections.Counter(img)
    hits = []
    for buf, order in ((img, 'normal'), (swap16(img), 'wordswap')):
        for v in range(LO, HI + 1):
            for name, val, offs, stride in search(buf, v):
                hits.append((name, val, offs, stride, order))
    mark = ' <-- current decode' if off == 17 else ''
    verdict = f"{len(hits)} candidate(s)" if hits else "-"
    print(f"{off:>4} {len(c):>9} {c[0xff]:>5}  {verdict}{mark}")
    for name, val, offs, stride, order in hits[:4]:
        s = f"stride {stride}" if stride else "irregular"
        print(f"       {order:8s} {name:20s} value {val} at {[hex(o) for o in offs]} ({s})")
