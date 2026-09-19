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
