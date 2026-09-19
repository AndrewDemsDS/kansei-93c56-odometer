#!/usr/bin/env python3
"""
Locate the odometer record in a 93C56 dump by confirmation, not assumption.

Brute-force every plausible encoding of the displayed mileage across the image.
The real record is duplicated across pages for wear levelling, so the encoding
yielding SEVERAL hits at a REGULAR stride is the one. A lone hit in 256 bytes
is coincidence, not a discovery.

usage:
  findodo.py <dump.bin> 217043           exact reading
  findodo.py <dump.bin> 216800-217200    approximate reading (range)
"""
import sys
from collections import defaultdict

# stored = displayed / divisor. Clusters of this era often keep the odometer
# in half- or sixteenth-unit steps rather than whole km.
DIVISORS = [("raw", 1), ("/2", 2), ("/4", 4), ("/5", 5), ("/8", 8),
            ("/10", 10), ("/16", 16), ("/100", 100), ("x10", 0.1)]


def swap16(b):
    """Byte-swap within each 16-bit word (93C56 is x16; MCU word order varies)."""
    out = bytearray(b)
    out[0::2], out[1::2] = b[1::2], b[0::2]
    return bytes(out)


def bcd(n, width):
    s = str(n).rjust(width * 2, "0")
    return None if len(s) > width * 2 else bytes(int(s[i:i+2], 16) for i in range(0, len(s), 2))


def patterns(v):
    """Yield (label, bytes) for every encoding of displayed value v."""
    for dname, div in DIVISORS:
        raw = v / div
        if abs(raw - round(raw)) > 1e-9:
            continue
        raw = int(round(raw))
        if raw < 0:
            continue
        for width in (2, 3, 4):
            if raw < (1 << (8 * width)):
                be = raw.to_bytes(width, "big")
                yield (f"{dname} {width}B BE", be)
                yield (f"{dname} {width}B LE", be[::-1])
            p = bcd(raw, width)
            if p:
                yield (f"{dname} {width}B BCD BE", p)
                yield (f"{dname} {width}B BCD LE", p[::-1])


def find_all(hay, needle):
    out, i = [], hay.find(needle)
    while i != -1:
        out.append(i)
        i = hay.find(needle, i + 1)
    return out


def search(img, v):
    """Return [(encoding, value, offsets, stride|None)] for one display value."""
    res = []
    for name, pat in patterns(v):
        if len(pat) < 2:
            continue
        offs = find_all(img, pat)
        if len(offs) < 2:
            continue
        strides = {offs[i+1] - offs[i] for i in range(len(offs) - 1)}
        res.append((name, v, offs, strides.pop() if len(strides) == 1 else None))
    return res


def report(img, order, results):
    if not results:
        return
    # regular stride first, then most copies
    results.sort(key=lambda r: (r[3] is None, -len(r[2])))
    print(f"\n  --- {order} byte order ---")
    for name, v, offs, stride in results[:8]:
        s = f"regular stride {stride}" if stride else "IRREGULAR - weak"
        print(f"  {name:20s} value {v:<8} {len(offs)} copies at "
              f"{[hex(o) for o in offs]}  ({s})")
        for o in offs[:4]:
            lo, hi = max(0, o - 4), min(len(img), o + 12)
            print(f"      {o:#05x}: {' '.join(f'{b:02x}' for b in img[lo:hi])}")


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    img = open(sys.argv[1], "rb").read()
    spec = sys.argv[2].replace(",", "").replace("_", "")
    if "-" in spec:
        lo, hi = (int(x) for x in spec.split("-", 1))
    else:
        lo = int(spec)
        hi = lo + 3          # display truncates; stored may sit slightly above

    print(f"image: {len(img)} bytes   searching displayed value {lo}..{hi}\n")
    for i in range(0, len(img), 16):
        row = img[i:i+16]
        a = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
        print(f"  {i:#05x}  {' '.join(f'{b:02x}' for b in row):<47}  {a}")

    total = 0
    for order, buf in (("normal", img), ("wordswap", swap16(img))):
        res = []
        for v in range(lo, hi + 1):
            res.extend(search(buf, v))
        total += len(res)
        report(buf, order, res)

    if not total:
        print("\n  NO multi-copy match in either byte order.")
        print("  The reading may be wrong, the value may not be in this chip,")
        print("  or the record is checksummed/obfuscated. DO NOT WRITE.")


if __name__ == "__main__":
    main()
