"""All measured data for the Navara D22 Kansei 93C56 odometer field at 0x6A.

Bytes are always given in CHIP ORDER (as they sit in the dump at 0x6A..0x6F).
Tachosoft displays them pairwise-swapped; that conversion is already applied.
"""

# Measured on THIS cluster: bytes written -> value shown on the LCD.
CLUSTER = [
    ("07fe0780f8f1", 212562),   # original contents, as found
    ("f8f1f88fc781", 428816),   # = Tachosoft's answer for "300,100 km"
    ("3ff0f8f13880", 571065),   # = Tachosoft's answer for "148,758 km"
    ("f8ff3880ff8f",   8522),   # = my 3-point model's prediction for 300,100
]

# Tachosoft 23.1, "Nissan Navara - 93c56 - 1999 year": km -> bytes.
TACHOSOFT = [
    (212562, "fff13ffe3f80"),
    (300100, "f8f1f88fc781"),
    (148758, "3ff0f8f13880"),
]

# Tachosoft's own model, solved and confirmed: three samples, ONE scale,
# spread 0.007 km. words=(0,1,2) cells=(2,1,0,4,3) rev=1, km = N * 53.6866.
TACHO_SCALE = 53.6866
TACHO_ORDER = ((0, 1, 2), (2, 1, 0, 4, 3), 1)

# Word format, verified on 128/128 words of this chip and 30/30 across sources.
CELLS = [0xC001, 0x3800, 0x0700, 0x0070, 0x000E]   # C1 wraps the word
MARKER = 0x0080
