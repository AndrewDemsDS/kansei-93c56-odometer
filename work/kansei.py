#!/usr/bin/env python3
"""
Structural analysis of a Kansei 93C56 cluster dump.

Established from the Navara D22 dump (2026-08-23), all exact, no fitting:

  * Every one of the 128 words has popcount == 1 (mod 3).
  * Only six popcounts occur: 1, 4, 7, 10, 13, 16 -> "level" 0..5.
    An erased word is 0xffff (16 bits, level 5); each increment clears
    THREE bits. So level = (popcount - 1) // 3, and steps_used = 5 - level.
  * Capacity is therefore 128 words x 5 steps = 640 steps.

Not yet known: how steps map to kilometres, and whether the array is a
positional number, a distributed sum, or a pointer-walked log. Deriving that
needs reference data - see STATUS.md. Do not fit a constant to one approximate
reading; with one free parameter anything fits.

usage: kansei.py <dump.bin> [second-dump.bin]
       With two dumps taken a KNOWN distance apart, prints the step delta,
       which gives km-per-step directly without needing absolute calibration.
"""
import sys


def words(buf):
    return [int.from_bytes(buf[i:i + 2], "big") for i in range(0, len(buf), 2)]


def levels(buf):
    out = []
    for w in words(buf):
        pc = bin(w).count("1")
        if pc % 3 != 1:
            raise ValueError(f"word {w:#06x} popcount {pc} is not 1 mod 3 - "
                             "this dump does not match the Kansei structure")
        out.append((pc - 1) // 3)
    return out


def report(path, buf):
    lv = levels(buf)
    used = sum(5 - l for l in lv)
    print(f"{path}")
    print(f"  words in use (!= 0xffff): {sum(1 for w in words(buf) if w != 0xffff)}/128")
    print(f"  sum of levels           : {sum(lv)} / {5*len(lv)}")
    print(f"  steps consumed          : {used} / {5*len(lv)}")
    for r in range(0, len(lv), 16):
        print(f"    w{r:3d}: " + " ".join(str(l) for l in lv[r:r + 16]))
    return used, lv


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    a = open(sys.argv[1], "rb").read()
    used_a, lv_a = report(sys.argv[1], a)

    if len(sys.argv) == 3:
        b = open(sys.argv[2], "rb").read()
        print()
        used_b, lv_b = report(sys.argv[2], b)
        d = used_b - used_a
        changed = [i for i, (x, y) in enumerate(zip(lv_a, lv_b)) if x != y]
        print(f"\n  steps advanced: {d}")
        print(f"  words changed : {changed}")
        if d:
            print(f"\n  If the odometer moved D km between these dumps,")
            print(f"  km per step = D / {d}")


if __name__ == "__main__":
    main()
