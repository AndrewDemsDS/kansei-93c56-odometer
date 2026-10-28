# Kansei 93C56 instrument cluster: odometer encoding, reverse engineered

Tooling and analysis for the Calsonic Kansei instrument cluster fitted to a
1999 Nissan Navara D22, and a full derivation of how it stores the odometer in
its 93C56 Microwire EEPROM.

## Why this exists

The encoding was not published anywhere. Searching English, Russian, Turkish
and Spanish language sources turned up no byte map and no algorithm for this
family, while turning up several threads where owners hit the same fault and
never resolved it. Every tool that can do this is proprietary, and two of them
were tested directly against this cluster and got it wrong.

## Scope and intent

This repository documents a repair. The cluster had been replaced with a donor
unit before the current owner acquired the vehicle, so the instrument read the
donor's distance rather than the vehicle's. The correction was made to the
vehicle's own documented distance, on the owner's own vehicle, and is recorded.

Correcting an instrument after a cluster replacement is a recognised repair
case. Misrepresenting a vehicle's distance is an offence in most jurisdictions.
Those are different things. If you correct a cluster, write down what you
changed and why, and disclose it when the vehicle changes hands. The law varies
and readers are responsible for their own: some countries regulate the act,
some regulate the sale, and at least one regulates the tools.

Published here: how the format works, and the measurements it was derived from.
Not published: the vehicle's own EEPROM images, and the reference dumps that
other people posted on forums in response to their own help requests.

## The encoding

The odometer is six bytes at offset `0x6A`, three 16-bit words.

**Each word encodes a 5-bit number. Each of those five bits is stored as a
three-bit cell and read by majority vote**, so two bits of three set means the
bit is set. The bit weights are:

    bit  1  = C3  mask 0x0700   (bits 10, 9, 8)
    bit  2  = C2  mask 0x3800   (bits 13, 12, 11)
    bit  4  = C1  mask 0xC001   (bits 15, 14, 0)
    bit  8  = C5  mask 0x000E   (bits 3, 2, 1)
    bit 16  = C4  mask 0x0070   (bits 6, 5, 4)

    0x0080 (bit 7) is a marker and is always set.

The three values compose positionally, and the reading is affine in the result:

    N  = value(w0) + 32 * value(w1) + 1024 * value(w2)        0 .. 32767
    reading = round(constant + N * step) mod 1,000,000

Implemented and self-testing in `work/kansei_binary.py`.

### Three things that make this easy to get wrong

**The cells are bits, not magnitudes.** Reading them as magnitude cells
produces a model that fits a surprising amount of data before failing, and the
majority voting makes partially-set cells look like they carry proportional
value. `work/kansei_codec.py` is that wrong model, kept deliberately because
`ANALYSIS.md` documents how it survived as long as it did.

**The step and the constant are configuration, not constants of the format.**
Two were observed on one physical cluster: 53.687 and 33.361 per count. Their
ratio is 1.60930 against 1.609344 kilometres per mile, so one configuration
counts kilometres and the other counts miles. A value computed under the wrong
one is wrong by a factor of 1.6. Establish which applies before trusting any
number.

**Dumps circulate in two byte orders.** Images of this family split cleanly
into two groups by whether the `0x0080` marker appears as stored or only after
byte-swapping each word, with nothing in between. A cluster accepts one group
and rejects the other. Check the marker before using any dump as a reference.

## What this repository contains, and what it does not

Included: the analysis, the derivation, the tooling, and the codec.

Not included: EEPROM images. The vehicle's own dumps are identifiable to it,
and the reference dumps collected during the work were posted by other people
on forums in response to their own help requests, so they are not this
project's to redistribute. Everything in `ANALYSIS.md` cites where each came
from.

## Tools

    make                            # build the C tools

    work/ch341_93cxx pinwalk        # identify CH341A socket pins with a meter
    work/ch341_93cxx diag           # is the chip responding, and repeatably?
    work/ch341_93cxx dump  out.bin
    work/ch341_93cxx write in.bin --yes-really-write
    work/dump3.sh <tag>             # read 3x, refuse unless byte-identical
    work/ch341_pulse <hz>           # square wave on MOSI, to bench-drive a VSS input

    work/kansei_binary.py selftest            # the solved encoding, with its measurements
    work/kansei_binary.py encode <reading>
    work/kansei_binary.py decode <dump|hex>
    work/kansei_binary.py patch <in.bin> <reading> <out.bin>
    work/kansei.py <a> [b]          # cell-level structure, and diff two dumps
    work/cksweep.py [samples...]    # checksum search, kept as a negative result

`patch` is the step from an encoded reading to a file you can write. It
copies a verified read of your own chip and changes only the six bytes at
`0x6A`, in the byte order the existing field already uses. It refuses a file
that is not 256 bytes, a near-uniform read, a field that decodes cleanly in
neither byte order, and an output path that already exists. It prints the
current field's reading: check that against the dash before writing, because
a mismatch means the cluster uses the other scale.

`work/mw93c56/` is the same Microwire protocol as an Arduino or ESP32 sketch,
for when a CH341A is not to hand.

## Wiring, 93C56 to a CH341A in the 25-series socket position

    93C56 1 CS  -> socket 1 (CS)      93C56 5 GND -> socket 4 (GND)
    93C56 2 SK  -> socket 6 (CLK)     93C56 6 ORG -> socket 8 (VCC)
    93C56 3 DI  -> socket 5 (MOSI)    93C56 8 VCC -> socket 8 (VCC)
    93C56 4 DO  -> socket 2 (MISO)    93C56 7 NC  -> floating

Only pins 1 and 8 line up between the two parts. Ground moves, and SK and DI
cross over. The chip must NOT sit in the socket directly.

## Dump discipline

Every read is taken three times and rejected unless all three are byte
identical, which `dump3.sh` enforces before locking the result read-only. An
all-`0xFF` read passes a self-consistency check while being pure garbage, so
near-uniform images are rejected as well. A write is never attempted unless
`diag` reports the chip answering when selected, returning the same value
twice, and staying silent when deselected. After any write, hash the read-back
against the source file: a success message from the write command is not
evidence the chip changed.

## Upstream tools, not vendored

    git clone https://gitlab.com/DavidGriffith/minipro.git tools/minipro
    # IMSProg (CH341A GUI with MicroWire support): AUR `imsprog`.
    # The chip type is listed as `93_EEPROM` rather than "MicroWire".
