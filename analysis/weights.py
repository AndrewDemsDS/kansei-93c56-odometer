"""Measured cell weights for THIS cluster's odometer field at 0x6A.

Method: write a field with exactly one cell set, read the LCD. Because the
all-clear baseline displays 0 km, there is no offset term and each reading IS
that cell's weight directly. No fitting, no model selection.

    km = sum(weight[word][cell] * cell_bit)

Cell masks (see ANALYSIS.md): C0=0xC001 (wraps), C1=0x3800, C2=0x0700,
C3=0x0070, C4=0x000E; marker 0x0080 always set.
"""

BASELINE = 0        # p00-base: 00 80 00 80 00 80  -> displays 0 km

WEIGHTS = {
    # (word, cell): km   -- filled in as each probe is measured
    (0, 0): 0,      # p01  c0 81 00 80 00 80 -> 0 km
    (0, 1): 534,    # p02  38 80 00 80 00 80 -> 534 km
    (0, 2): 400,    # p03  07 80 00 80 00 80 -> 400 km
    (0, 3): 200,    # p04  00 f0 00 80 00 80 -> 200 km
    (0, 4): 33,     # p05  00 8e 00 80 00 80 -> 33 km
    (1, 0): None, (1, 1): None, (1, 2): None, (1, 3): None, (1, 4): None,
    (2, 0): None, (2, 1): None, (2, 2): None, (2, 3): None, (2, 4): None,
}

# ---- table t[index], index = cells c1c2c3c4 (c0 is INERT: confirmed 3x) ----
#   V  = t[w0] + 32*t[w1] + 1024*t[w2]        word 2 verified: 546,579 km measured
#   km = round(V * 33.36053) mod 1_000_000    wraparound confirmed by sample 4
TABLE = {
    0b0000: 0,    # 0 km        measured
    0b0001: 1,    # 33 km       measured
    0b0010: 6,    # 200 km      measured
    0b0011: 7,    # 234 km      measured
    0b0100: 12,   # 400 km      measured
    0b0101: 13,   # 434 km      measured
    0b0110: 14,   # 467 km      measured   <- not 18, so cells do not add
    0b0111: 15,   # 500 km      measured
    0b1000: 16,   # 534 km      measured   (17,081 km in word 1 -> x32 scale)
    0b1001: 17,   # 567 km      measured
    0b1010: 22,   # 734 km      measured   <- breaks the "index+8" rule
    0b1011: 23,   # 767 km      measured
    0b1100: 28,   # 934 km      measured
    0b1101: 29,   # EXTRAPOLATED
    0b1110: 30,   # EXTRAPOLATED (corroborated by back-solving full-field sample 3)
    0b1111: 31,   # EXTRAPOLATED
}

# UNRESOLVED. The table supplies only 16 of the 32 values 0..31; missing are
# 2,3,4,5,8,9,10,11,18,19,20,21,24,25,26,27. Cell c0 was the obvious candidate
# to supply them but measures inert three separate ways (alone, with c4, with
# c1). Consequently V cannot take values 8192..12287, so the model says the
# display jumps 273,256 -> 409,934 km. No real odometer does that, and
# 300,100 km falls inside that gap.
#
# Full-field sample 1 (07fe0780f8f1 -> 212,562 km) also cannot be explained:
# it needs V ~ 6371, which the table cannot produce, under any of the six
# word-order permutations.
#
# So the model fits all 14 probes and 3 of 4 full-field samples exactly while
# still being incomplete. Something structural remains unidentified.
