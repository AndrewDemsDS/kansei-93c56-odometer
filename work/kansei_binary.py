#!/usr/bin/env python3
"""
Kansei 93C56 odometer codec, BINARY variant (ANALYSIS.md section 24).

This is the encoding used by the configuration that drives this Navara D22
cluster correctly: gauges, tachometer and both trip meters. It is NOT the
encoding in work/kansei_codec.py, which describes the damaged configuration
this project started from and is kept for that historical purpose.

Derived 2026-09-18 from eight physical readings off the cluster's own LCD,
fitting exactly one free parameter. The model reproduces all eight.

STRUCTURE

    Three 16-bit words at 0x6A. Each word is a 5-bit number, 0..31.
    Each of those five bits is stored as a three-bit cell and read by
    MAJORITY VOTE, so two of three bits set means the bit is set. That
    redundancy is why partially-set cells behaved unpredictably under the
    older magnitude model.

    bit weight   cell   mask
         1        C3    0x0700   (bits 10, 9, 8)
         2        C2    0x3800   (bits 13, 12, 11)
         4        C1    0xC001   (bits 15, 14, 0)   <- carries value here
         8        C5    0x000E   (bits 3, 2, 1)
        16        C4    0x0070   (bits 6, 5, 4)

    0x0080 (bit 7) is the marker and is always set.

    Note C1 carries value in this encoding. The older model treats it as
    inert, which is correct for the other configuration and wrong here.

VALUE

    N  = value(w0) + 32*value(w1) + 1024*value(w2)        0 .. 32767
    km = round(52 + N * 53.68711) mod 1_000_000

    The step 53.68711 is Tachosoft's documented Kansei scale of 53.6866 to
    within the fit. The constant 52 was measured directly by clearing every
    cell, not inferred.

BYTE ORDER

    Images of this family store each word byte-swapped relative to this
    project's own dumps. store()/load() handle that; see ANALYSIS 22.1.
"""
import sys

C1, C2, C3, C4, C5, MARKER = 0xC001, 0x3800, 0x0700, 0x0070, 0x000E, 0x0080
BITS = [(C3, 1), (C2, 2), (C1, 4), (C5, 8), (C4, 16)]
STEP, CONST = 53.68711, 52
FIELD = 0x6A


def word_value(w):
    """The 5-bit number a word encodes, each bit majority-voted over its cell."""
    return sum(b for m, b in BITS
               if bin(w & m).count("1") * 2 > bin(m).count("1"))


def make_word(v):
    """Lowest-risk encoding of a 5-bit value: every cell fully set or fully clear."""
    w = MARKER
    for m, b in BITS:
        if v & b:
            w |= m
    assert word_value(w) == v
    return w


def load(six_bytes):
    """Stored bytes -> the three word values."""
    ws = [(six_bytes[i + 1] << 8) | six_bytes[i] for i in range(0, 6, 2)]
    return [word_value(w) for w in ws]


def store(values):
    """Three 5-bit values -> stored bytes."""
    return bytes(b for v in values for b in
                 (make_word(v) & 0xFF, make_word(v) >> 8))


def to_km(values):
    n = values[0] + 32 * values[1] + 1024 * values[2]
    return round(CONST + n * STEP) % 1_000_000


def encode(km):
    """Closest reachable reading to km, as (stored bytes, values, actual km)."""
    best = min(range(32768),
               key=lambda n: abs((CONST + n * STEP) % 1_000_000 - km))
    v2, r = best // 1024, best % 1024
    vals = [r % 32, r // 32, v2]
    return store(vals), vals, to_km(vals)


def swap(six_bytes):
    """Swap the two bytes of each word: the other byte-order family (ANALYSIS 22.1)."""
    return bytes(six_bytes[i ^ 1] for i in range(6))


def partial_cells(six_bytes):
    """How many cells are neither fully set nor fully clear."""
    ws = [(six_bytes[i + 1] << 8) | six_bytes[i] for i in range(0, 6, 2)]
    return sum(1 for w in ws for m, _ in BITS if w & m not in (0, m))


def has_marker(six_bytes):
    return all(six_bytes[i] & MARKER for i in range(0, 6, 2))


def field_order(six_bytes):
    """'native', 'swapped', or None when the field does not say which.

    An order qualifies when every word carries the marker. When both do (a
    field heavy in 0xFF bytes), the one with no partially-set cells wins.
    """
    ok = {o: f for o, f in (("native", six_bytes), ("swapped", swap(six_bytes)))
          if has_marker(f)}
    if len(ok) == 2:
        ok = {o: f for o, f in ok.items() if partial_cells(f) == 0}
    return next(iter(ok)) if len(ok) == 1 else None


def patch(src, km, dst, order=None):
    """Copy src to dst with the odometer field set to the reading closest to km.

    Only the six bytes at FIELD change, written in the byte order the existing
    field already uses. Refuses anything it cannot verify.
    """
    import os
    if os.path.exists(dst):
        sys.exit(f"refusing: {dst} exists, and patches never overwrite a file")
    img = bytearray(open(src, "rb").read())
    if len(img) != 256:
        sys.exit(f"refusing: {src} is {len(img)} bytes, a 93C56 image is 256")
    if max(img.count(b) for b in set(img)) > 240:
        sys.exit(f"refusing: {src} is near-uniform, which is what a bad read looks like")
    old = bytes(img[FIELD:FIELD + 6])
    found = field_order(old)
    if order is None:
        order = found
    if order is None:
        sys.exit(f"refusing: the field at 0x{FIELD:02X} ({old.hex()}) does not decode "
                 "cleanly in either byte order. Re-read the chip, and check the "
                 "dump is from a Kansei 93C56 cluster")
    cur = old if order == "native" else swap(old)
    if not has_marker(cur):
        sys.exit(f"refusing: the field ({old.hex()}) has no marker in {order} order")
    new, vals, got = encode(km)
    img[FIELD:FIELD + 6] = new if order == "native" else swap(new)
    print(f"current field  {old.hex()}  {order} order  reads {to_km(load(cur)):,} km")
    if partial_cells(cur):
        print(f"  note: {partial_cells(cur)} partially-set cells, read by majority vote")
    if order == "swapped":
        print("  note: the swapped family is not validated against this scale")
    print(f"new field      {bytes(img[FIELD:FIELD + 6]).hex()}  values={vals}  reads {got:,} km")
    print("Check the current reading against the dash before writing. If it does")
    print("not match, the cluster uses another scale (km vs miles), so do not write.")
    with open(dst, "xb") as f:
        f.write(img)
    print(f"wrote {dst}")


# Every physical reading this was derived from: stored field -> LCD reading.
MEASURED = [
    ("800080008000", 52), ("803880008000", 160), ("800080008038", 110004),
    ("800080008007", 55028), ("800080008e00", 439857), ("80008000f000", 879662),
    ("fe008fc0f1f8", 231419), ("93388e00813b", 178830), ("f1c78ff881c7", 300110),
]


def selftest():
    bad = 0
    for hexs, km in MEASURED:
        got = to_km(load(bytes.fromhex(hexs)))
        err = got - km
        if abs(err) > 2:
            bad += 1
        print(f"  {hexs}  predicted {got:>7,}  measured {km:>7,}  {err:+d}")
    print("FAIL" if bad else "all readings reproduced")
    return bad == 0


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "selftest":
        sys.exit(0 if selftest() else 1)
    if sys.argv[1] == "encode":
        b, v, km = encode(int(sys.argv[2]))
        print(f"{b.hex()}  values={v}  reads {km:,} km")
    elif sys.argv[1] == "decode":
        a = sys.argv[2]
        raw = open(a, "rb").read()[FIELD:FIELD + 6] if a.endswith(".bin") else bytes.fromhex(a)
        v = load(raw)
        print(f"{raw.hex()}  values={v}  reads {to_km(v):,} km")
    elif sys.argv[1] == "patch" and len(sys.argv) in (5, 6):
        opt = sys.argv[5] if len(sys.argv) == 6 else None
        if opt not in (None, "--native", "--swapped"):
            sys.exit("order override is --native or --swapped")
        patch(sys.argv[2], int(sys.argv[3]), sys.argv[4], opt and opt[2:])
    else:
        sys.exit("usage: kansei_binary.py selftest | encode <km> | decode <dump|hex>\n"
                 "       kansei_binary.py patch <in.bin> <km> <out.bin> [--native|--swapped]")
