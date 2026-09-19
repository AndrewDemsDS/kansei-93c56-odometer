#!/usr/bin/env python3
"""
Kansei cluster odometer codec (Nissan D22 and relatives), derived 2026-08-23.

WORD FORMAT — verified on 30/30 words from two independent clusters
(our 93C56, and pman92's 93C46 dumps posted on pcmhacking in 2019):

  Each 16-bit word is five 3-bit CELLS plus one always-set marker bit.
  A cell is all-set or all-clear; nothing partial ever occurs.

      C1 = 0xC001   <-- WRAPS the word: bits 15,14 and bit 0
      C2 = 0x3800
      C3 = 0x0700
      C4 = 0x0070
      C5 = 0x000E
      marker = 0x0080 (always 1)

  The masks sum to 0xFFFF exactly. This is why every word's popcount is
  3*(cells set) + 1, i.e. always 1 mod 3, and why values like 0x81 and 0xC7
  look like broken thermometers: they are the wrapping C1 cell.

FIELD FORMAT: three consecutive words = 15 cell-bits = the odometer.
  Cell order within a word is (2,1,0,4,3); the 15 bits are read LSB-first.

  km = N * 53.687

SCALE: solved from three of pman92's reference dumps (201149 km, and the
pair 360082/318704). Residuals were 64 km and 41 km, both inside one step.
Independently corroborated: UPA-USB documents its Kansei tool as having
"54 km accuracy". Bounds from requiring 0 <= remainder < step on all three
references: 53.6827 < scale <= 53.6875. The step granularity is presumably
why a separate fine counter exists elsewhere in the image.

UNVERIFIED ON OUR CHIP: the scale above comes from a 1997 2.4L petrol
cluster with a 93C46. Ours is a 1999 2.5D with a 93C56 - a different
variant. No window in our dump decodes near the reported ~217,000 km, so
either that reading is imprecise or this variant uses a different constant.
Do not write until a known reading pins down the right window.
"""
import sys

CELLS = [0xC001, 0x3800, 0x0700, 0x0070, 0x000E]
MARKER = 0x0080
CORDER = (2, 1, 0, 4, 3)
SCALE = 53.687


def word_cells(w):
    """Five cell bits, or None if the word does not fit the model."""
    if not w & MARKER:
        return None
    bits, acc = [], MARKER
    for m in CELLS:
        v = w & m
        if v == m:
            bits.append(1); acc |= m
        elif v == 0:
            bits.append(0)
        else:
            return None
    return bits if acc == w else None


def cells_word(bits):
    w = MARKER
    for bit, m in zip(bits, CELLS):
        if bit:
            w |= m
    return w


def decode(three_words):
    cs = [word_cells(w) for w in three_words]
    if any(c is None for c in cs):
        return None
    bits = [c[i] for c in cs for i in CORDER]
    n = 0
    for b in reversed(bits):
        n = n * 2 + b
    return n


def encode(n):
    """Inverse of decode: 15-bit N -> three 16-bit words."""
    if not 0 <= n < (1 << 15):
        raise ValueError(f"N={n} does not fit in 15 bits")
    bits = [(n >> i) & 1 for i in range(15)]        # LSB-first
    out = []
    for wi in range(3):
        chunk = bits[wi * 5:(wi + 1) * 5]
        cell = [0] * 5
        for slot, ci in enumerate(CORDER):
            cell[ci] = chunk[slot]
        out.append(cells_word(cell))
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: kansei_odo.py <dump.bin> [target_km]")
    d = open(sys.argv[1], "rb").read()
    W = [int.from_bytes(d[i:i + 2], "big") for i in range(0, len(d), 2)]

    bad = [i for i, w in enumerate(W) if word_cells(w) is None]
    print(f"words fitting the cell model: {len(W) - len(bad)}/{len(W)}")
    if bad:
        print(f"  NOT fitting at word indices {bad[:12]} - wrong byte order?")

    print("\ncandidate odometer windows (any 3 consecutive valid words):")
    for i in range(len(W) - 2):
        n = decode(W[i:i + 3])
        if n and 50000 <= n * SCALE <= 500000:
            print(f"  offset {i*2:#05x}  {d[i*2:i*2+6].hex(' ')}  N={n:5d}  {n*SCALE:>9,.0f} km")

    if len(sys.argv) == 3:
        km = float(sys.argv[2])
        n = round(km / SCALE)
        ws = encode(n)
        print(f"\nto write {km:,.0f} km:  N={n}  -> {n*SCALE:,.0f} km actual "
              f"(error {n*SCALE-km:+.0f} km, step is {SCALE:.1f} km)")
        print("  bytes: " + " ".join(f"{w:04x}" for w in ws))
        assert decode(ws) == n, "round-trip failed"
        print("  round-trip decode OK")


if __name__ == "__main__":
    main()
