#!/usr/bin/env python3
"""
Kansei 93C56 odometer codec: the closed-form model, measured on THIS cluster
(Nissan Navara D22, Kansei MCU K29451VB200, donor unit 2001-2002).

This is the final model from ANALYSIS.md sections 10-11 and STATUS.md's
"fully solved" block, expressed as one self-tested implementation. The older
work/kansei_odo.py predates the partial-cell discovery and Tachosoft's scale;
it is kept as the Tachosoft-variant explorer. This file is the codec to use
for this cluster.

FIELD
    6 bytes at 0x6A, three consecutive 16-bit BIG-ENDIAN words, chip order
    (the order dump3.sh produces). The second field at 0x00-05 uses the same
    encoding (ANALYSIS 14.3: it decodes to 24,787 km in predonor).

WORD: five 3-bit cells plus one always-set marker bit.

    C1 = 0xC001   wraps the word (bits 15,14 and bit 0); INERT, carries no value
    C2 = 0x3800   16 units when fully set
    C3 = 0x0700   12 units
    C4 = 0x0070    6 units
    C5 = 0x000E    1 unit
    marker = 0x0080, always set

UNITS OF A WORD

    u = 16*[C2 fully set] + 4*popcount(C3) + 2*popcount(C4) + [C5 fully set]
    u -= 4 if C3 AND C4 are both fully set          (12u + 6u = 14u: the
                                                     padd-w0c2c3 probe read
                                                     467 km, not 600)

    Cells may be partially set and then carry proportional value: C3 is 4 per
    bit, C4 is 2 per bit (r-C3-1bit/2bits, and w0=0x009E = 2+1 in the final
    field). A partial C5 is worth 0 (q-b01/b02/b03 read 0 km); only the full
    C5 carries its 1. C2 is fully set or clear in every word ever observed;
    a partial C2 is rejected as unknown rather than guessed.

VALUE AND DISTANCE

    V  = u(w0) + 32*u(w1) + 1024*u(w2)
    km = round(V * 33.36053) mod 1_000_000

    Words compose by exact powers of 32 (one word is five cells wide). Cells
    within a word do NOT simply add: the -4 rule above is the one measured
    exception, and it is consistent with every whole-cell probe (t20-t29) and
    with the extrapolated t[1110]=30 / t[1111]=31 entries.

VERIFIED AGAINST (selftest runs all of these)

    p00-p05 single-cell probes         0 / 0 / 534 / 400 / 200 / 33 km
    t20-t29 whole-cell probes          7,13,15,17,22,23,28,29,30,31 units
    padd-w0c2c3 (C3+C4)                467 km  (the -4 rule)
    r-C3-1bit / r-C3-2bits             4 / 8 units (133 / 267 km)
    q-b01..b03 (C5 single bits)        0 km
    s-val25                            V=25   ->   834 km
    p07 (w1 C2 probe)                  V=512  -> 17,081 km
    near-300078.bin                    V=8995 -> 300,078 km  (on the cluster)
    predonor primary field             V=22927 -> 764,857 km (on the cluster;
                                       ANALYSIS 13.1's "764,858" is a rounding
                                       slip: 22927*33.36053 = 764,856.87)
    predonor second field 0x00-05      V=743  ->  24,787 km (ANALYSIS 14.3)
    f8ff3880ff8f                       V=30231 -> 1,008,522 -> 8,522 km after
                                       the 1,000,000 wraparound (sample 4)

NOT SOLVED HERE: the trip-counter / gauge validity gate (ANALYSIS 13-15).
That guard is bit-sensitive over at least 0x00-05 and 0x6A-0x6F and no
checksum form tried so far matches. This codec produces well-formed fields
the cluster displays correctly; it does not make the trip button work.

USAGE
    kansei_codec.py selftest
    kansei_codec.py decode <dump.bin | 6-byte hex>     # hex: 009e3e8e0680
    kansei_codec.py encode <km>
"""
import sys

# Cell masks. C1 wraps the word and carries no value; marker is always set.
C1 = 0xC001
C2 = 0x3800
C3 = 0x0700
C4 = 0x0070
C5 = 0x000E
MARKER = 0x0080
ALL_MASKS = (C1, C2, C3, C4, C5)

KM_PER_UNIT = 33.36053
MOD = 1_000_000
FIELD_OFFSET = 0x6A
SECOND_FIELD_OFFSET = 0x00

# Whole-cell word patterns, measured or trivially additive away from the
# C3+C4 coexistence. Provenance in comments: measured probe / measured field /
# additive (same cell classes as a measurement, no C3-C4 coexistence) /
# extrapolated (the pattern's C3+C4 coexistence at partial depth is unmeasured).
UNITS_TO_WORD = {
    0:  ("0080", "measured p00"),
    1:  ("008E", "measured p05"),
    2:  ("0090", "per-bit C4 (2/bit, from 0x009E = 2+1)"),
    3:  ("009E", "measured near-300078 w0"),
    4:  ("0480", "measured r-C3-1bit"),
    5:  ("048E", "additive (C3 1bit + C5)"),
    6:  ("00F0", "measured p04"),
    7:  ("00FE", "measured t20"),
    8:  ("0680", "measured r-C3-2bits"),
    9:  ("068E", "additive (C3 2bits + C5)"),
    10: ("0690", "extrapolated (C3 2bits + C4 1bit)"),
    11: ("069E", "extrapolated (C3 2bits + C4 1bit + C5)"),
    12: ("0780", "measured p03"),
    13: ("078E", "measured t21"),
    14: ("07F0", "measured padd-w0c2c3 (the -4 rule)"),
    15: ("07FE", "measured t22 / predonor w0"),
    16: ("3880", "measured p02"),
    17: ("388E", "measured t23"),
    18: ("3890", "additive (C2 + C4 1bit, no C3)"),
    19: ("389E", "additive (C2 + C4 1bit + C5)"),
    20: ("3980", "additive (C2 + C3 1bit, class measured via s-val25)"),
    21: ("398E", "additive (C2 + C3 1bit + C5)"),
    22: ("38F0", "measured t24 / predonor w2"),
    23: ("38FE", "measured t25 / predonor 0x00-05 w1"),
    24: ("3E80", "additive (C2 + C3 2bits)"),
    25: ("3E8E", "measured s-val25 / near-300078 w1"),
    26: ("3E90", "extrapolated (C2 + C3 2bits + C4 1bit)"),
    27: ("3E9E", "extrapolated (C2 + C3 2bits + C4 1bit + C5)"),
    28: ("3F80", "measured t26"),
    29: ("3F8E", "measured t27"),
    30: ("3FF0", "measured bytes t28 / rule (-4) value"),
    31: ("3FFE", "measured t29"),
}
WORD_TO_UNITS = {int(b, 16): (u, prov) for u, (b, prov) in UNITS_TO_WORD.items()}


def full(mask, w):
    return (w & mask) == mask


def word_units(w):
    """Units carried by one 16-bit word, or None if it does not fit the model."""
    if not w & MARKER:
        return None
    if not full(C1, w) and w & C1:
        pass  # C1 is inert in any state: full, partial (predonor w0), or clear
    if w & C2 and not full(C2, w):
        return None  # partial C2 never observed; refuse to guess
    u = (16 if full(C2, w) else 0) \
        + 4 * bin(w & C3).count("1") \
        + 2 * bin(w & C4).count("1") \
        + (1 if full(C5, w) else 0)
    if full(C3, w) and full(C4, w):
        u -= 4
    if w & ~(C1 | C2 | C3 | C4 | C5 | MARKER):
        return None  # stray bits outside the known masks
    return u


def decode_field(six_bytes):
    """(V, km) for a 6-byte field in chip order, or None if ill-formed."""
    if len(six_bytes) != 6:
        return None
    words = [int.from_bytes(six_bytes[i:i + 2], "big") for i in (0, 2, 4)]
    us = [word_units(w) for w in words]
    if any(u is None for u in us):
        return None
    v = us[0] + 32 * us[1] + 1024 * us[2]
    return v, round(v * KM_PER_UNIT) % MOD


def encode(km):
    """Nearest displayable field for km, as (bytes, V, provs, actual, delta).

    The display advances in ~33.36 km steps, so most targets are not exactly
    reachable (STATUS.md: 300,100 requested, 300,078 written, 22 km under,
    under one quantum). Patterns whose C3+C4 partial coexistence is
    unmeasured rank last, then by distance from the request.
    """
    if not 0 <= km < MOD:
        return None
    best = None
    for dv in range(-16, 17):
        v = round(km / KM_PER_UNIT) + dv
        if not 0 <= v < (1 << 15):
            continue
        digits = (v % 32, (v >> 5) % 32, v >> 10)
        if any(d not in UNITS_TO_WORD for d in digits):
            continue
        provs = [UNITS_TO_WORD[d][1] for d in digits]
        n_extrap = sum(1 for p in provs if p.startswith("extrapolated"))
        actual = round(v * KM_PER_UNIT) % MOD
        # Prefer under-reading the request: this tool corrects to a vehicle's
        # true distance, and overshooting it is never the wanted default.
        key = (n_extrap, 0 if actual <= km else 1, abs(actual - km))
        if best is None or key < best[0]:
            best = (key, v, digits, provs, actual)
    if best is None:
        return None
    _, v, digits, provs, actual = best
    b = bytes.fromhex("".join(UNITS_TO_WORD[d][0] for d in digits))
    return b, v, provs, actual, actual - km


def parse_field_arg(arg):
    if arg.lower().endswith(".bin") or arg.lower().endswith(".dump"):
        d = open(arg, "rb").read()
        return d[FIELD_OFFSET:FIELD_OFFSET + 6]
    h = arg.replace(" ", "").lower()
    if len(h) == 12:
        try:
            return bytes.fromhex(h)
        except ValueError:
            pass
    return None


def show_field(name, b):
    dec = decode_field(b)
    print(f"  {name}  {b.hex(' ')}")
    if dec is None:
        print("      ill-formed under the model")
        return
    v, km = dec
    words = [int.from_bytes(b[i:i + 2], "big") for i in (0, 2, 4)]
    for i, w in enumerate(words):
        u = word_units(w)
        print(f"      w{i} = 0x{w:04X}  u = {u}")
    print(f"      V = {v}   ->  {km:,} km")


def selftest():
    cases = [
        # (field hex, expected km, note)
        ("008000800080", 0, "p00 baseline"),
        ("c08100800080", 0, "p01 C1 inert"),
        ("388000800080", 534, "p02 C2"),
        ("078000800080", 400, "p03 C3"),
        ("00f000800080", 200, "p04 C4"),
        ("008e00800080", 33, "p05 C5"),
        ("008000803880", None, None),  # placeholder replaced below
        ("008038800080", 17081, "p07 w1 C2, V=512"),
        ("048000800080", 133, "r-C3-1bit, 4 units"),
        ("068000800080", 267, "r-C3-2bits, 8 units"),
        ("008400800080", 0, "q-b02 C5 single bit"),
        ("07f000800080", 467, "padd-w0c2c3, the -4 rule"),
        ("3e8e00800080", 834, "s-val25, V=25"),
        ("009e3e8e0680", 300078, "near-300078, on the cluster"),
        ("07fe0780f8f1", 764857, "predonor primary, on the cluster"),
        ("00fef8ff0080", 24787, "predonor 0x00-05 second field"),
        ("f8ff3880ff8f", 8522, "sample 4, wraps 1,000,000"),
    ]
    # whole-cell table probes t20..t29 (values in units from weights.py)
    unit_cases = [
        ("00fe", 7), ("078e", 13), ("07fe", 15), ("388e", 17), ("38f0", 22),
        ("38fe", 23), ("3f80", 28), ("3f8e", 29), ("3ff0", 30), ("3ffe", 31),
    ]
    failures = 0
    for hexpair, units in unit_cases:
        w = int(hexpair, 16)
        u = word_units(w)
        ok = u == units
        failures += 0 if ok else 1
        print(f"  {'ok ' if ok else 'FAIL'} word 0x{w:04X} -> {u} units (expect {units})")
    for hexstr, want_km, note in cases:
        if note is None:
            continue
        b = bytes.fromhex(hexstr)
        dec = decode_field(b)
        ok = dec is not None and dec[1] == want_km
        failures += 0 if ok else 1
        got = "ill-formed" if dec is None else f"{dec[1]:,} km (V={dec[0]})"
        print(f"  {'ok ' if ok else 'FAIL'} {hexstr} -> {got}   [{note}]")
    # encoder round trip on the final target
    enc = encode(300100)
    ok = enc is not None and enc[0] == bytes.fromhex("009e3e8e0680") \
        and enc[3] == 300078 and enc[4] == -22
    failures += 0 if ok else 1
    print(f"  {'ok ' if ok else 'FAIL'} encode(300100) -> {enc[0].hex(' ')} "
          f"(V={enc[1]}, shows {enc[3]:,} km, {enc[4]:+d}; STATUS recorded "
          f"009e3e8e0680 / 22 km under target)")
    # every table pattern decodes back to its own unit count
    for u, (b, prov) in sorted(UNITS_TO_WORD.items()):
        w = int(b, 16)
        ok = word_units(w) == u
        failures += 0 if ok else 1
        if not ok:
            print(f"  FAIL table {u} ({b}) decodes to {word_units(w)}")
    print(f"  {'ALL PASS' if failures == 0 else f'{failures} FAILURES'}")
    return failures


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "selftest":
        return 1 if selftest() else 0
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    cmd, arg = sys.argv[1], sys.argv[2]
    if cmd == "selftest":
        return 1 if selftest() else 0
    if cmd == "decode":
        b = parse_field_arg(arg)
        if b is None:
            print("need a .bin/.dump file or 12 hex digits", file=sys.stderr)
            return 2
        show_field(f"0x{FIELD_OFFSET:02X}:", b)
        if len(b) == 6:
            try:
                d = open(arg, "rb").read() if arg.lower().endswith((".bin", ".dump")) else None
            except OSError:
                d = None
            if d and len(d) >= 0x70:
                show_field(f"0x{SECOND_FIELD_OFFSET:02X}:", d[0:6])
        return 0
    if cmd == "encode":
        km = int(arg)
        enc = encode(km)
        if enc is None:
            print(f"no well-formed field displays {km:,} km", file=sys.stderr)
            return 1
        b, v, provs, actual, delta = enc
        print(f"target {km:,} km -> V={v}, will show {actual:,} km ({delta:+d})")
        for i, (d, p) in enumerate(zip((v % 32, (v >> 5) % 32, v >> 10), provs)):
            print(f"  w{i}: {UNITS_TO_WORD[d][0]}  u={d}  [{p}]")
        print(f"  bytes: {b.hex(' ')}")
        for p in provs:
            if p.startswith("extrapolated"):
                print("  NOTE: uses a pattern whose C3+C4 partial coexistence has "
                      "not been bench-measured; consider a V one step away.")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
