# Kansei 93C56 odometer encoding: analysis record

Nissan Navara D22 (1999), Kansei cluster, MCU `K29451VB200`, EEPROM 93C56EN.
Everything below is either measured or explicitly flagged as unproven.

---

## How to read this

A working record kept across seven sessions, in chronological order. It
contains conclusions that were later withdrawn, and those are left in on
purpose, because how a wrong model survived seven sessions is the useful part.

If you want only the result:

- **Section 24** is the solved encoding.
- **Section 25** is the root cause of the fault that started all of this.
- **Sections 1 to 21** describe a magnitude model that is **wrong**. Section 24
  explains why it fit so much data before it failed.
- `work/kansei_binary.py` implements the solved encoding and self-tests against
  every physical reading it was derived from.

## 1. Established beyond doubt: the word format

Each 16-bit word is **five 3-bit cells plus one always-set marker bit**. A cell
is entirely set or entirely clear; a partial cell never occurs.

    C1 = 0xC001   <-- WRAPS the word: bits 15,14 and bit 0
    C2 = 0x3800
    C3 = 0x0700
    C4 = 0x0070
    C5 = 0x000E
    marker = 0x0080   (always 1)

The masks sum to `0xFFFF` exactly, so every word's popcount is
`3*(cells set) + 1`, i.e. always 1 mod 3.

**Evidence.** Holds for 128/128 words of this chip, and 30/30 distinct words
across this chip plus five independent reference dumps posted by pcmhacking
user pman92 in 2019 (a different cluster, a 93C46, read on a different
programmer). Values such as `0x81` and `0xC7` are not corrupt thermometer codes;
they are the wrapping C1 cell, which is what made the format look broken.

## 2. Field location: 6 bytes at 0x6A

From Tachosoft 23.1's database, entry "Nissan Navara - 93c56 - 1999 year":

    0060: 00 00 00 00 00 00 00 00 00 00 81 F8 FE 38 80 07

The field is right-aligned and ends at 0x6F, padded before with 0x00/0xFF.

**Confirmed experimentally**: writing 6 bytes at 0x6A changed the display from
212,562 to 428,816 km. The location is not in doubt.

## 3. Tachosoft's mapping: SOLVED, high confidence

    N = 15 cell-bits, words (0,1,2), cells (2,1,0,4,3), read LSB-first
    km = N * 53.6866

| km | N | bytes (chip order) |
|---|---|---|
| 148,758 | 2771 | `3f f0 f8 f1 38 80` |
| 212,562 | 3959 | `ff f1 3f fe 3f 80` |
| 300,100 | 5590 | `f8 f1 f8 8f c7 81` |

**Why this is trustworthy**: a *one*-parameter model fitted to three points
(2 degrees of freedom) with a spread of **0.007 km**. Independently corroborated
by SoftDump documenting the UPA-USB Kansei script as having "54 km accuracy",
and by the same ordering falling out of pman92's unrelated reference dumps.

## 4. THIS cluster does not use Tachosoft's mapping

Four measurements, each written to the chip and read off the LCD:

| bytes at 0x6A | N (Tachosoft's reading) | Tachosoft says | THIS cluster displays |
|---|---|---|---|
| `07 fe 07 80 f8 f1` | 22585 | 1,212,506 | **212,562** |
| `f8 f1 f8 8f c7 81` |  5590 |   300,100 | **428,816** |
| `3f f0 f8 f1 38 80` |  2771 |   148,758 | **571,065** |
| `f8ff 3880 ff8f`    | 15454 |   829,687 |   **8,522** |

Sorted by N the displayed values run 571k, 429k, 8.5k, 213k: **non-monotonic**.

## 5. Models tested and RULED OUT

All searched exhaustively over 3!*5!*2 = 1440 orderings (word order, cell order,
bit direction), scored on **all four** points:

| Model | Best max error | Verdict |
|---|---|---|
| `km = N * s` (proportional) | 111% relative spread | ruled out |
| `km = a*N + b` (affine) | 11,823 km | ruled out |
| `km = (a*N + b) mod 1e6` | 1,458 km, absurd params | ruled out |
| Gray-decoded N, affine | 2,069 km | ruled out |
| Bit-inverted N, affine | 11,823 km | ruled out |

Also ruled out earlier: the value is **positional, not count-based** - two
samples share 7 set cells yet display 212,562 and 571,065.

## 6. Methodological note (the mistake worth not repeating)

An earlier 3-point affine model fitted with max residual 50 km and was used to
predict bytes for 300,100 km. The cluster displayed **8,522**.

The fit was meaningless: **the best of 1440 candidate orderings, fitted with two
free parameters to three points** - one degree of freedom. A good-looking fit was
essentially guaranteed by selection. The 50 km residual was not evidence, and
the fourth measurement is what actually tested it.

**The counting argument that governs everything here:** 15 cell weights plus an
offset is **16 unknowns**. Four measurements is underdetermined by a factor of
four. No search can recover the model; it can only produce spurious fits, which
is what every attempt above did.

## 7. External research

- pman92 (pcmhacking, 2019): the algorithm is "a common Denso one", all 6 bytes
  are the odometer, and Tachosoft v23.1 computes it. He also documents 999,999
  as the display when the cluster cannot read the EEPROM.
- Denso encodings are commonly **table-driven** rather than formulaic: "you look
  up a Denso conversion table and take bytes and swap then convert". One
  documented variant is `mileage * 6002 -> hex -> XOR FFFFFFFF`. If this variant
  is table-driven, no closed-form fit will ever work, which is consistent with
  every negative result in section 5.
- Kansei clusters use at least **two distinct byte alphabets** across variants
  (ours plus an `AF F6 5F ED BF DA` family seen on Almera/Pressage 93c56).
- In-circuit programming is possible: 6 pads wired to the EEPROM plus MCU reset.
  CarProTool succeeds "with an extra ground connection" where UPA without "the
  extra pin" fails - consistent with the reset pad needing to be grounded to
  stop the MCU contending on the shared Microwire bus.

## 8. The only sound way forward: measure each cell

Set exactly one cell from an all-clear baseline and read the display. Each
measurement yields one cell's weight directly. No ordering assumption, no model
selection, no possibility of overfitting.

    weight[i] = display(only cell i set) - display(baseline)

16 measurements (baseline + 15 cells). Images are pre-generated in `probes/`,
and `work/probe.sh <name>` writes and verifies one.

If the weights come out as a doubling series the remaining cells can be inferred
and spot-checked, so in practice ~6 cycles may settle it. The resulting model is
then **testable against the four measurements already in section 4** - which is
the check every fitted model so far has failed.

If `p00-base` displays 999,999, the cluster rejects an all-clear field and the
baseline must instead be a known-good pattern with single cells cleared rather
than set.

## 9. MEASURED: the encoding is table-driven, not additive

Probe sweep run 2026-08-25 on this cluster. Baseline `00 80 00 80 00 80`
(all cells clear) displays **0 km**, so there is no offset term.

Single cells of word 0, everything else clear:

| cells (c0..c4) | displayed | units of 33.4 |
|---|---|---|
| `00000` |   0 km |  0 |
| `10000` |   0 km |  0 |
| `01000` | 534 km | 16 |
| `00100` | 400 km | 12 |
| `00010` | 200 km |  6 |
| `00001` |  33 km |  1 |
| `00110` | **467 km** | **14** |

The base unit is tightly constrained: every reading equals `floor(m * u)` for
u in [33.375, 33.417), so **u ~ 33.4 km**.

**The last row disproves additivity.** Cells c2 and c3 measure 12u and 6u
alone; set together they give **14u**, not 18u. The cells are not independent,
so per-cell weights do not compose and `km = sum(weight_i * cell_i)` is dead.

This matches the external research exactly: Denso encodings are commonly
**table-driven** ("look up a Denso conversion table and take bytes and swap then
convert"). A 5-cell word has 32 patterns; mapping one word's table needs 32
measurements, and that is only useful if the three words themselves combine
additively - which is untested and may equally fail. If words also interact the
space is 32^3 = 32,768 and is not measurable at all.

Note also `10000` displays 0, identical to `00000`: the wrapping C1 cell appears
to carry no value in word 0, or its weight is a multiple of the display modulus.

## 10. SOLVED: the structure (2026-08-25)

Cells within a word do not add. Words do, and they scale by 32:

    value = t[w0] + 32*t[w1] + 1024*t[w2]
    km    = round(value * 33.36133)

where `t` is a shared lookup table indexed by the word's cell pattern. The
scale of 32 is exactly 2^5, one word being five cells wide.

Every measurement fits to the exact kilometre:

| pattern / value | measured km | predicted |
|---|---|---|
| all clear, V=0 | 0 | 0 |
| w0 `00001`, V=1 | 33 | 33 |
| w0 `00010`, V=6 | 200 | 200 |
| w0 `00100`, V=12 | 400 | 400 |
| w0 `00110`, V=14 | 467 | 467 |
| w0 `01000`, V=16 | 534 | 534 |
| **w1 `01000`, V=16*32=512** | **17,081** | **17,081** |

The unit is tightly pinned by the V=512 point: u in [33.360352, 33.362305].

`t[10000] == t[00000] == 0`, so the wrapping C1 cell carries no value. Only
c1..c4 matter, which collapses the table from 32 entries to **16**.

Known so far (index = c1c2c3c4):

    t[0000]=0  t[0001]=1  t[0010]=6  t[0100]=12  t[0110]=14  t[1000]=16

Ten remain, generated as `probes/t20-*` .. `probes/t29-*`. Once complete the
codec is closed-form and can be checked against the four full-field
measurements in section 4.

## 11. THE MISSING MECHANISM: partial cells (2026-08-25)

Cells do not have to be fully set. A **partially set cell carries a
proportional value**, and that supplies every value the whole-cell table was
missing.

| written | cell state | measured | units |
|---|---|---|---|
| `0x0780` | C3 all 3 bits | 400 km | 12 |
| `0x0680` | C3 **2 bits** | **267 km** | **8** |
| `0x0084` | C5 1 bit | 0 km | 0 |

C3 is worth 12 units so each of its bits is 4; two bits give 8, which is one of
the sixteen values absent from the whole-cell table. The earlier "partial cells
are inert" conclusion came from testing a single bit of **C5**, the lowest cell,
worth 1 unit in total - so one bit is a third of a unit and rounds to zero on
the display. It was below the display's resolution, not inert.

This also resolves the long-standing sample 1 anomaly: 212,562 km required a V
the whole-cell table could not produce, because the real encoding uses partial
cells.

Combinations compose additively across cells here: `0x3E8E` = C2(16) +
C3 2 bits(8) + C5(1) measured **834 km = 25 units**, exactly the sum.

### Result

    w0 = 0x0080 =  0
    w1 = 0x3E8E = 25   ->   32 * 25 =   800
    w2 = 0x0680 =  8   -> 1024 *  8 = 8192
                              V = 8992  ->  299,978 km

Written to the chip 2026-08-25. Every component value was measured directly.

## 12. Alternative that needs none of this

Restore the golden dump and drive the odometer up with a pulse train on the
VSS input (`work/ch341_pulse`). The cluster then increments using its own
firmware, so the encoding, checksums and redundancy are correct by
construction and no EEPROM write is needed. Slower, but it cannot produce a
wrong stored value. See section 13: this is now the leading candidate for
actually solving the trip-counter fault below, used as a small, controlled
diagnostic step rather than a full drive-up.

## 13. The "predonor" mislabel, a wider field, and a trip-counter fault (2026-09-07/08)

A new replacement 93C56 was programmed with `dumps/near-300078.bin` (the
section 11 result) and refit. The odometer displayed correctly, but the fuel
and temperature needles sat at rest and **the trip-counter button stopped
responding**. This section records everything learned chasing that fault in
one long session. No fix was found; the fault is now well characterized and
several concrete next steps are queued.

### 13.1 "212,562 km / original donor" was always a mislabel

Every file in `dumps/` ever labeled "original", "donor", or "predonor"
(`predonor-*`, `navara-93c56-VERIFIED.bin`, `postrestore-*`) is byte-identical:
field `07 fe 07 80 f8 f1`. STATUS.md has carried this as "212,562 km" since
2026-08-23. Running the section 11 formula against these exact bytes:

    w0 = 0x07FE -> TABLE[0111] = 15
    w1 = 0x0780 -> TABLE[0100] = 12
    w2 = 0xF8F1 -> TABLE[1010] = 22
    V  = 15 + 32*12 + 1024*22 = 22,927
    km = round(22,927 * 33.36053) = 764,858

Written to a bench chip and read on the actual cluster: **764,857 km**,
against the model's 764,858. `weights.py`'s own comment already flagged
this discrepancy in 2026-08 ("Full-field sample 1 ... needs V ~6371, which
the table cannot produce, under any of the six word-order permutations"),
and the project moved on without resolving it. It is now resolved:
**764,858 km is the correct decode of these bytes**, and "212,562 km" was
never a real measurement of this field on this cluster, at any point. A
full scan of all 122 files in `dumps/` found nothing that decodes near
212,562 km either, so there is no mislabeled-but-recoverable golden image
to go find. The name `predonor` etc. is kept in this repo for continuity,
but should be read as "the untouched, working, ~764,858 km baseline"
rather than as a 212,562 km reference.

### 13.2 The value spans more than the 3-word field this project assumed

With the primary field at `predonor`'s original (working) value, blanking the
30 bytes at `0x70-0x8d` to `0xFF` (a region STATUS.md's model never
touches) shifted the reading from 764,858 to **858,014 km**, with 0x6a-0x6f
byte-for-byte unchanged. The three-word model in section 1-11 is therefore
incomplete: whatever the cluster actually computes draws on more than the
narrow field this project reverse-engineered. This also explains why the
Aug 2026 "300,078 km" result could be correct at the time: every test up to
that point left the region beyond 0x6f untouched at its original value, so
the unmodeled contribution was a constant the fitted probes absorbed without
anyone needing to know it was there.

### 13.3 What the trip-counter fault does and does not correlate with

Six real hardware tests, same physical chip and cluster throughout:

| Field written | Cells | Trip button |
|---|---|---|
| `predonor` original (`07fe0780f8f1`) | all whole, no partial bits | **works** |
| `near-300078.bin` (section 11 target) | partial cells in every word | fails |
| wrap bits (0xC001) added to w2 only, same km | partial cells, wrap set | fails |
| whole-cell-only field, no partial bits anywhere (273,256 km) | all whole | fails |
| `predonor` field unchanged, region 0x70-0x8d blanked to FF | n/a (region test) | fails |
| chip fully removed | n/a | works, though the cluster falls back to a self-test sweep rather than normal-mode gauge behaviour |

This rules out both structural theories that were cheap to test: the
whole-cell-only test still failed, so partial cells are cleared as a
trigger; setting the `0xC001` wrap bits to match `predonor`'s own w2
pattern also did nothing, clearing that theory too. The fault correlates
with **any deviation from predonor's exact original bytes**, regardless of
whether the result is well-formed by this project's model, Tachosoft's
model, or any other model tried. That is the signature of a checksum or
validity guard computed over the original data, rather than a decode-format
problem.

### 13.4 Three Tachosoft entries tried, all wrong on this specific hardware

Tachosoft 23.1 (`work/tachosoft-wine-setup.sh`, installed via Wine this
session) was tried against three Nissan/Kansei/93c56 entries for a 300,100 km
target, each written to the bench chip and read on the real cluster:

| Tachosoft entry | Predicted | Actual on this cluster | Trip button |
|---|---|---|---|
| Nissan Navara - 93c56 - 1999 year | 300,100 | (not re-tested; superseded) | - |
| Nissan Frontier Kansei - 93c56 - 2001-2006 years | 300,100 | 22,301 km | fails |
| Nissan Double Cab - 93c56 - 2001 year | 300,100 | 489,132 km | fails |

Both tested entries missed by a wide margin far beyond any plausible
rounding error, meaning neither is this cluster's actual algorithm despite
matching chip and era on paper. Tachosoft's own "All v/s Miles - 93c56"
generic entry uses a 14-byte field starting near 0x69, structurally
consistent with 13.2's wider-field finding; it lacks a Kansei cell
structure match, though, and was not pursued further.

### 13.5 Community precedent: this is a known, unsolved class of fault

- `mhhauto.com/Thread-Nissan-navara-odo-correction-help` (2019, 2012 Navara
  D40, Calsonic Kansei 93c56): after a Tachosoft-based correction, "fuel,
  temperature and rotation is up... not in the position", i.e. the same
  class of gauge fault, on a different cluster generation. An attached
  reference file (`70000.rar`, saved to
  `reference/forum-dumps-d40-navara-different-unit/70000.bin`) turned out on
  inspection to be a **pure byte-swap** of the original poster's own dump
  (`nissannavara.rar`, `.../nissannavara.bin`) - every 16-bit word's two
  bytes exactly swapped, confirmed by script, across all 256 bytes. It reads
  as a tool/endianness mishap in that thread rather than a calculated
  value, and is not usable as a reference. Writing `nissannavara.bin`
  (someone else's D40 cluster's own dump) to this project's D22 cluster
  produced a third, distinct fault mode: fuel and temp needles pinned **up**
  rather than down, resembling the chip-absent self-test sweep rather than
  the narrower fault in 13.3. The trip button still failed there too.

- `pcmhacking.net/forums/viewtopic.php?f=33&t=6558` ("Japanese Kansei
  Cluster EEPROM odometer value", 2019): this is the source thread behind
  `reference/kansei-pman92.py`, read in full this session. Two details not
  previously captured in this repo:
  - A partial hand-drawn schematic (saved to `reference/pman92-schematic/`)
    for a closely related Kansei MCU (`K2945...`, same family as this
    project's `K29451VB200`) shows **TRIP wired to a single dedicated pin
    (pin 54) directly on the main MCU**, through a plain switch and
    resistor, bypassing the EEPROM and the separate LCD-driver chip
    (`K29453...`, also visible on the schematic) entirely. Combined with
    13.3, this confirms the fault is the **MCU's firmware choosing not to
    act on that pin** - a firmware-side gate, unreachable by rewiring
    anything or by rearranging EEPROM bytes differently.
  - Forum member `yoda69` independently proposed the same checksum theory
    in 2019, unprompted: "I wouldn't be surprised if one of the values is a
    checksum and if invalid displays 999,999km."
  - pman92's own conclusion: Tachosoft's algorithm ("apparently... a common
    Denso one") gets "within a few KM" on a real cluster, short of exact,
    matching this session's own Tachosoft results.

### 13.6 Recommended next steps, in priority order (superseded by 14.6)

1. **VSS-pulse diagnostic.** Restore `predonor`'s exact working bytes, then
   drive a *small* distance increment with `work/ch341_pulse` on the VSS
   input rather than an EEPROM write. The cluster's own firmware would then
   update the primary field, the section 13.2 wider region, and any
   checksum correctly by construction. Diffing the resulting dump against
   `predonor` would show directly which bytes the firmware itself touches
   and how, which is real ground truth instead of another guess. This is
   the highest-value, lowest-risk experiment queued and has not been tried
   yet.
2. **Post to MHH Auto / Digital Kaos** (registered this session) with the
   exact chip markings (`K29451VB200`, `VJ513`, `K11631 VJ210`) and the
   13.3 symptom table. Existing threads found by searching did not have
   this exact chip; a targeted post might reach someone who does.
3. **MCU boot-mode identification**, only after 1 and 2: `K29451VB200` is
   very likely a Kansei-masked Hitachi/Renesas H8/300-family core (common
   for this class of part). H8 parts often expose a non-destructive,
   factory-designed serial boot mode. The schematic in 13.5 gives one
   concrete target (the MCU's reset pin, and pin 54 for TRIP) but the board
   photos this session also showed candidate test points (`J9`, `J10`,
   `J13`, `J15`) near the MCU whose function is unconfirmed. This needs
   non-invasive continuity tracing against a confirmed H8 pinout before
   touching anything; whether read-protection is set on this specific part
   is unknown either way. Do not attempt anything destructive (decapping)
   for a trip-counter fault; this is the only board this project has.

## 14. Real community dumps tested directly on this cluster (2026-09-08)

Continuation of section 13's session, using MHH Auto and Digital Kaos
accounts registered specifically for this. Files saved to
`reference/community-93c56-93c46-dumps/`.

### 14.1 A 93C46 reference: needle behaviour shifts, trip still fails

`mhhauto.com/Thread-please-need-dump-dash-nissan-navara-D22-1998`: dash
number `K11631 3S401`, matching this project's own board part number almost
exactly. A 128-byte 93C46 dump attached there (`konop11138`, "Try, 115000km
i think so") was independently confirmed working, including tacho, by two
later replies over 2023-2024. Since this project's chip is a 93C56 (256
bytes), the 128 bytes were placed in the low half of the address space with
this project's own high half left untouched, written, and tested. Result:
odometer far from any guessed value, fuel and temp needles moved to
mid-scale rather than resting at empty (this project's own patches) or
pinned high (the unrelated D40 dump in 13.5), and the trip button still did
not respond. Comparing this dump against `predonor` at the same offsets: 51
of 128 bytes identical, concentrated in `0x51-0x61` and `0x64-0x6a` -
candidate shared-calibration ranges, though the amount of variation
elsewhere suggests most of this region carries real per-unit state rather
than fixed constants.

### 14.2 Two independent 93C56 dumps: the first trip response of the entire session

`digital-kaos.co.uk` thread "Nissan Navara odometer with 93c56" (2011):
several posters tried to build a 130,000 km dump for a different Navara
93C56 unit, mostly failing (values like 99999999 and 404,000 km reported).
Two results from that thread were written to this project's actual chip and
tested:

- `mattydr67`'s `130_000.rar`, which he confirmed showed 129,984 km on his
  own bench. On this cluster: 671,162 km, fuel and temp needles moved
  upward, and **pressing the trip button switched the display to a "TRIP"
  page showing 0** - registering the press and changing display mode for
  the first time all session, even without cycling to trip A/B properly.
- `sanjaycip`'s `navara_c56_130000kms.rar`, containing two candidate files,
  `1a` and `1b`. `1a` reproduced the same partial trip response as
  mattydr67's file (odometer 413,385 km). `1b` did not respond to the trip
  button at all.

Every prior test this session, on data this project constructed itself, produced
zero trip response. Two independently-sourced real dumps from a different
unit both produced this same partial response; a third (`1b`) did not. That
split is the most useful clue of the night.

### 14.3 The 1a/1b pair reveals a second odometer-related field

`1a` and `1b` differ in 194 of 256 bytes. Checking whether `1b` is simply
`1a` with every word's bytes swapped (the same transform found in section
13.5's D40 pair):

    swapped = byte-swap each word of 1a
    swapped == 1b  except at exactly 12 positions: 0x00-0x05 and 0x6a-0x6f

Every other byte in the file is a pure mechanical byte-swap between `1a`
and `1b`. Only two 6-byte ranges were independently recalculated per
byte-order guess: this project's known field at `0x6a-0x6f`, and a
previously untouched field at **`0x00-0x05`**. This matches pman92's own
note in the pcmhacking thread (section 13.5) about some Kansei clusters
storing the odometer value redundantly in multiple locations, and gives a
concrete second field this project never wrote to, in over a dozen attempts
across sections 11-14.

`1a` (partial trip response) uses this project's own established byte
order; `1b` (no response) is the swapped version. That is independent
confirmation the big-endian word convention documented in section 1 is the
one this cluster actually expects.

Checked against this project's own real data: field `0x00-0x05` decodes to
24,787 km under the section 1-11 model, and is byte-identical between
`predonor` (trip works) and `near-300078.bin` (trip fails) - this project
never wrote to it. A literal duplicate-value theory is therefore ruled out
on its own, since the field stayed constant while the outcome flipped. A
derived-value theory (a checksum or hash of the primary field, stale after
this project's edits, correct in `predonor` only because `predonor`'s
primary field was never changed) remains open and untested beyond the
simple case in 14.4.

### 14.4 Mirror test: simple duplication is not the relationship

Built from `predonor`'s working baseline: `0x6a-0x6f` set to the section 11
target field, and `0x00-0x05` set to the *same* 6 bytes (a literal mirror,
the simplest possible version of 14.3's theory) rather than left stale.
Written and verified against source hash. Result: odometer wrong, fuel
needle at empty rather than pinned down, temp needle mid-scale, **trip
still did not respond**. A literal copy into `0x00-0x05` is not the right
relationship; whatever function maps the primary field to this second field
is not the identity function.

### 14.5 A recurring hardware-reliability trap this session

Several times this session, `ch341_93cxx write` reported success
("wrote 128 words") after `diag` reported GOOD, but the chip's actual
contents did not change. This was caught only by explicitly hashing the
read-back against the intended source file. `dump3.sh`'s own 3-way
self-consistency check is insufficient here: it confirms three reads agree
with each other, which is a different claim from confirming they match what
was meant to be written. The write tool's own internal CS check caught the
same marginal connection on immediate retries when the standalone `diag`
command did not. Always diff or hash the post-write dump against the source
file before treating a write as real; a "wrote N words" message alone is
not sufficient evidence.

### 14.6 Updated recommended next steps, in priority order

1. **Characterize the `0x00-0x05` field properly.** This is now a confirmed,
   concrete second field rather than a hypothesis. Measure it the way
   section 4's probes measured the primary field, by writing controlled
   single-cell changes to `0x00-0x05` alone (primary field and rest of chip
   held at `predonor`'s working values) and reading the result. A literal
   copy (14.4) did not work; a systematic probe series would.
2. **VSS-pulse diagnostic**, unchanged from 13.6: drive a small distance
   increment on `predonor`'s working baseline with `work/ch341_pulse`
   rather than an EEPROM write, and diff the result. This would show
   directly how the firmware itself updates both odometer fields and the
   section 13.2 wider region together, and remains untried.
3. **Post to MHH Auto / Digital Kaos**, unchanged from 13.6, now with a much
   sharper question to ask: does anyone know the relationship between the
   fields at `0x00-0x05` and `0x6a-0x6f` on a Kansei 93C56 Navara cluster.
4. **MCU boot-mode identification**, unchanged from 13.6, lowest priority
   and not to be attempted destructively.

### 14.7 Chip state at end of session

**Not restored.** The bench chip currently holds `dumps/mirror-test.bin`
(the 14.4 negative result: predonor's baseline with `0x6a-0x6f` set to the
section 11 target and `0x00-0x05` mirrored to the same 6 bytes), verified
3x via `dump3.sh` and hash-checked against source at write time. The CH341
programmer was unplugged before the restore to `dumps/near-300078.bin`
could run. **Before refitting this cluster to the vehicle, write
`dumps/near-300078.bin` and verify the hash matches `b10fcf9b...`** - do
not refit with `mirror-test.bin` still on the chip.

## 15. Characterizing `0x00-0x05`: research, a coincidence that doesn't hold up, and the next isolating probe (2026-09-08, continued)

### 15.1 Forum research: no new offset data, but the checksum theory is now the community's own leading guess too

Re-read pman92's pcmhacking thread in full (browser, logged in) rather than
relying on the excerpt already in 13.5 - no additional detail on a second
field or its offset. `yoda69`'s "I wouldn't be surprised if one of the
values is a checksum and if invalid displays 999,999km" (already quoted in
13.5) is the closest anyone in that thread comes to naming this mechanism,
and nobody there identifies which bytes.

A new MHH Auto thread not previously found, `Thread-Nissan-Navara-kansei-
dashboard-eeprom-read` (2017), was downloaded and checked
(`~/Downloads/Nissan Navara kansei 93C56 read.zip` - not committed to this
repo, since it contains no dump, only two JPEGs of a CarProTool wiring
adapter on a **different** Kansei board revision, MCU marked differently
from this project's `K29451VB200`). No checksum or offset information.
Re-checked the Digital Kaos D40 thread (13.5) directly too - it dead-ends at
3 posts, nothing beyond what 13.5 already recorded.

Net result: forum research adds no new lead. Priority reverts to direct
measurement, per the methodological warning in section 6.

### 15.2 A tempting cross-dump byte-sum coincidence, checked against all data and rejected

Before spending another bench cycle, checked whether a trivial checksum
form - the 8-bit sum of the 6 bytes at `0x00-0x05` equalling the 8-bit sum
of the 6 bytes at `0x6a-0x6f` - separates working from failing images, using
every real dump this project has actually tested on this cluster (not just
the two most convenient ones):

| dump | byte-sum(0x00-05) | byte-sum(0x6a-6f) | match? | trip on this cluster |
|---|---|---|---|---|
| `predonor` | 0x75 | 0x75 | yes | **works** |
| `near-300078.bin` | 0x75 | 0xf0 | no | fails |
| `mattydr67` 130k | 0x3d | 0x3d | yes | partial (TRIP page, no A/B) |
| `sanjaycip` 1a | 0x3d | 0x36 | **no** | partial (same as mattydr67) |
| `sanjaycip` 1b | 0x3d | 0x3d | **yes** | none |
| D40 `nissannavara.bin` | 0xbf | 0x13 | no | fails (13.5, different fault mode) |

The first two rows (this project's own controlled before/after, same
physical chip and cluster) looked like a clean hit. Adding the three
community dumps this project already tested directly on this cluster kills
it: `sanjaycip` 1a and 1b get the *opposite* result from what the theory
predicts (1a mismatches but partially works, 1b matches but doesn't work at
all). Note 1a and 1b share an identical `0x00-0x05` by construction (14.3 -
1b never recalculated that field, only mechanically inherited it), so this
isn't six independent measurements of the checksum hypothesis, it's four -
still enough to reject a same-byte-sum theory outright. Recorded here
specifically so this coincidence doesn't get rediscovered and mistaken for
a finding later; see section 6.

This also doesn't rule out a checksum that spans a wider region than either
6-byte field - 13.2 already showed the value feeding the display draws on
bytes past `0x6f`, so any real checksum likely does too, which a 12-byte
same-sum comparison can't detect either way.

### 15.3 The next isolating probe: change `0x00-0x05` alone

Every test to date that touched `0x00-0x05` also changed `0x6a-0x6f` in the
same write (14.4's mirror test) or came from a foreign dump where both
fields differ from this cluster's own values simultaneously (14.2, 14.3).
No test has ever changed `0x00-0x05` **by itself** against an otherwise
known-good baseline. That is the cleanest next measurement: it directly
answers whether `0x00-0x05` alone gates the fault, independent of any
change to the primary field.

`probes/u01-clear0005-predonor-baseline.bin`: `predonor`'s exact 256 bytes,
with `0x00-0x05` set to the all-clear pattern `00 80 00 80 00 80` (same
well-formed baseline pattern used for the primary-field sweep in section 9)
and every other byte, including `0x6a-0x6f`, left at `predonor`'s original
working values. `predonor`'s own `0x00-0x05` (`00 fe f8 ff 00 80`) is
itself a fully well-formed field under this project's cell model (marker
set, C1/C2/C3 clear, C4 and C5 full in w0; C1/C2/C4/C5 full in w1; w2
all-clear) - confirmation that whatever `0x00-0x05` is, it uses the same
5-cell/word structure as the primary field, consistent with 14.3.

Run `work/probe.sh u01-clear0005-predonor-baseline`, refit/power the
cluster, and check trip button + fuel/temp needle behaviour against the
`predonor` baseline (works) and `near-300078.bin` (fails):

- **Still works** -> `0x00-0x05` is not itself part of the gate in this
  simple cleared-to-zero form; the 14.4 mirror-test failure was driven by
  the `0x6a-0x6f` change, not the `0x00-0x05` change, and priority should
  shift to the wider `0x70-0x8d` region (13.2) or elsewhere as the gate's
  real carrier.
- **Fails** -> `0x00-0x05` is sufficient on its own to trip the fault when
  changed, even with `0x6a-0x6f` untouched. Follow with a single-cell sweep
  on `0x00-0x05` (mirroring section 8's method, probes `u02`-`u0n`) to
  localize which byte(s)/cell(s) within it matter, rather than the whole
  field.

Not yet run this session - the CH341 programmer is unplugged (`diag`
reports "not found, or no permission").

### 15.4 Run: `0x00-0x05` alone gates the fault, and needs BOTH its words exact

CH341 reconnected and `u01` run on the real bench chip and cluster. Result:
**fails** - trip button did not respond, fuel needle at empty, temp needle
mid-scale, tach and speedo also off their normal rest position. Odometer
still read 764,857 km (matches `predonor`, confirming `0x6a-0x6f` was
correctly untouched and still drives the display independently of
`0x00-0x05`).

This resolves the 15.3 branch: `0x00-0x05` is sufficient on its own to
trigger the fault, with the primary field completely unmodified. Followed
with the planned 2x2 localization (`0x00-0x05` has only two words that
actually differ from `predonor` in `u01` - `w2` was already `0x0080` in
both, so it was already excluded as insufficient alone):

| w0 (`0x00-0x01`) | w1 (`0x02-0x03`) | trip / needles |
|---|---|---|
| cleared | cleared | fails (`u01`) |
| **predonor original** | cleared | **fails** (`u02`) |
| cleared | **predonor original** | **fails** (`u03`) |
| predonor original | predonor original | **works** (`predonor` itself) |

Neither word alone is sufficient restored; only the exact original pair
passes. Combined with 13.3 (changing `0x6a-0x6f` alone, `0x00-0x05`
untouched, also fails) and 14.4 (changing both together, to a value that is
not their original pairing, also fails), the full pattern across every test
this project has run is: **the gate passes only when every field involved
sits at its one original, factory-written value; changing any single field
alone, in isolation, is sufficient to fail it.** That is the signature of a
checksum or validity value computed over data that includes both
`0x00-0x05` and `0x6a-0x6f` (at minimum), recomputed and compared at boot,
rather than of `0x00-0x05` being an independent redundant odometer copy or
fine counter that could be right or wrong on its own terms.

One physical-reliability note from this run: the CH341 lost contact with
the chip mid-session (`u03`'s first write attempt got `NO RESPONSE - line
stuck at 0x00/0xFF`) and recovered after reseating - `diag` caught it
correctly before any write was attempted, exactly as designed. No data was
at risk; recorded here only as a reminder the socket connection is still
marginal.

### 15.5 Simple whole-image checksum forms ruled out; algorithm still unidentified

Computed `sum(bytes)`, `sum(bytes) mod 256`, and `xor(bytes)` over "every
byte except `0x00-0x05`" for all five real, unmodified reference images this
project has (this project's own `predonor`, plus `mattydr67`, `sanjaycip`
1a and 1b, and the D40 `nissannavara.bin`) and compared against each image's
own actual `0x00-0x05` bytes. **No match, on any sample, under any of these
forms.** This rules out the simplest checksum shapes cheaply, without fitting
a formula to the single confirmed-good sample this project actually has on
its own cluster (which would repeat the section 6 mistake - one degree of
freedom, no held-out data). A real CRC (Denso's algorithm is table-driven
for the odometer encoding itself, so a table-driven checksum here would be
consistent) or a narrower/differently-scoped input than "the whole image"
both remain open and were not pursued further by guessing.

### 15.6 Recommended next step: VSS-pulse diagnostic, not further guessing

With simple checksum forms ruled out and no forum source naming an
algorithm (15.1), continuing to guess candidate checksum functions has a
large hypothesis space and only one confirmed-good same-cluster data point
- exactly the shape of search that produced the section 6 mistake. The
sound next step is still the one queued since 13.6 and never run: restore
`predonor`'s exact bytes, drive a small real distance increment through the
cluster's own firmware with `work/ch341_pulse` on the VSS input, then dump
and diff against `predonor`. This shows directly which bytes the firmware
itself recomputes for a real increment - `0x00-0x05`, `0x6a-0x6f`, and the
13.2 wider region together - which is ground truth rather than another
guess, and could hand back the actual algorithm in one step instead of a
long probe sweep.

Wiring, from `work/ch341_pulse.c`'s own header comment: CH341A socket pin 5
(MOSI) through a 1k series resistor to the cluster's VSS input, socket pin 4
(GND) common with cluster ground. The chip must be seated and the cluster
powered normally (not just bench-read) for this to do anything. Pulse count
needed per km is unknown for this cluster - start with a short burst and
check whether the odometer or trip distance moved at all before committing
to a long run.

**Not available this session - no 1k resistor / VSS wiring on hand.**

### 15.7 Run: a single flipped bit in `0x00-0x05` is enough to fail, with the primary field untouched

`probes/u04-1bit-w0-c5.bin`: `predonor`'s exact bytes with exactly one bit
changed - byte `0x01`, bit 1 (`0xfe -> 0xfc`, part of `w0`'s `C5` cell,
previously fully set, now 2 of 3 bits). Every other byte in the 256-byte
image, including all of `0x6a-0x6f`, identical to `predonor`. Result:
**fails**, same as `u01`-`u03`.

This rules out any theory involving tolerance - a coarse decoded-value
comparison, a check that only cares about which cells are fully-vs-partially
set, or anything that would absorb a change this small. The gate is
sensitive at the single-bit level, which is the signature of a real
checksum/CRC byte-for-byte compare, not a value-level plausibility check.

### 15.8 Standard CRC-8/CRC-16 sweep against all real samples: no match

With bit-level sensitivity confirmed and no forum source naming the
algorithm, swept 10 named CRC-8 and 20 named CRC-16 variants (the common
catalogued parameter sets - ARC, MODBUS, X-25, CCITT-FALSE, MAXIM, DNP,
GENIBUS, etc., not invented ones) over four candidate input regions
(everything except the field itself, just the primary field, the region
between the two fields, and the whole image with the field included) against
all five real, unmodified samples (`predonor` plus the four community
dumps), requiring a match in **every** sample under the same algorithm and
region before counting it as a hit - the cross-validation this project's own
section 6 mistake was missing. 124 combinations tried. **Zero hits.**

This doesn't rule out a checksum - only these specific standard forms over
these specific regions and byte-orderings. A Denso-proprietary table-driven
algorithm (plausible - the odometer encoding itself is table-driven), a
different scope (e.g. keyed by VIN or unit-specific data not present in
these dumps), or a region this sweep didn't try, all remain possible.
Continuing to guess from here has a large hypothesis space and only one
same-cluster confirmed-good data point - exactly the shape of search that
produced the section 6 mistake, so this was not pursued further blindly.

### 15.9 Where this leaves the trip-counter fault, end of session

`0x00-0x05` is now a confirmed, bit-sensitive component of whatever gates
the fault (15.4, 15.7), the fault is definitely a real checksum/validity
guard rather than a decode-format problem (13.3, 15.7), simple checksum
forms are ruled out including a 124-way standard CRC sweep (15.5, 15.8),
and the one remaining ground-truth method - watching the firmware compute
its own update via a VSS pulse - is not available this session (no 1k
resistor / wiring on hand). Recommended paths, neither pursued yet:

1. **A commercial mileage-correction tool with native Kansei/93C56 support**
   (CarProTool - already confirmed able to **read** this exact chip type in
   14.1's MHH Auto source; also Digiprog3, OBDStar, Yanhua Mileage Master,
   and others commonly claim Kansei coverage) may already implement the
   correct checksum internally without needing it reverse-engineered here.
   Worth checking whether any tool already on hand, or cheaply available,
   lists this cluster/board specifically before writing anything with it.
2. **Accept the tradeoff and refit anyway.** The odometer value itself is
   solved and correct (`near-300078.bin`). The fault costs the trip counter
   and live fuel/temp gauge tracking - real functionality, not merely
   cosmetic, so this is a genuine tradeoff to weigh, not a formality.
3. Continue probing `0x00-0x05` / `0x6a-0x6f` bit-by-bit to map the
   checksum's dependency structure without knowing the algorithm - low
   value per bench cycle at this resolution, not recommended as a next
   step on its own.

Chip restored to `predonor`'s exact bytes and verified before ending the
session (full read-back compare, not just a write-success message).

## 16. A second independent unit's real correction attempts, including an actual 999,999 fault (2026-09-08, continued)

`digital-kaos.co.uk/forums/showthread.php/639994` ("Nissan Navara pickup
1999 with Kansei 93c56", 2018): a different physical unit, same vehicle
generation and chip. Original poster `alimmo` attached their own working
dump (160,274 mi); a helper, `brend`, posted three correction attempts
across the thread trying to reach 64,250 mi. All four files downloaded and
saved to `reference/community-93c56-93c46-dumps/dk-93c56-alimmo-*.bin`.

Diffing each attempt against the original:

| file | bytes changed vs. original | reported outcome |
|---|---|---|
| `attempt1-wrong-notfaulted.bin` | `0x50-0x69` zeroed, `0x6a-0x6d` set to target bytes | wrong value (160,388 mi), not faulted |
| `attempt2-999999fault.bin` | scattered `0x56`, `0x59`, `0x5b`, plus `0x68-0x75` corrupted | **"dash now gone to 999999"** |
| `attempt3-onlyfield.bin` | only `0x6a-0x6d` (the narrow field itself) | still wrong, thread ends "no joy" |

Two things worth recording precisely:

- **This unit's value-bearing field is only 4 bytes (`0x6a-0x6d`), not 6.**
  `0x6e-0x6f` (`07 80`) is identical across the original and all three
  attempts - untouched by every edit, including the ones that changed the
  surrounding region. Firmware sub-variants really do differ in field width,
  not just scale constant, so this doesn't transfer byte-for-byte to this
  project's own cluster.
- **The mechanism transfers even though the byte layout doesn't.** This is
  an independent, different physical unit, and it reproduces this project's
  own §13.2 finding exactly: something wider than the narrow odometer field
  gates validity. Zeroing a 26-byte span (`0x50-0x69`) around the field was
  tolerated - wrong number, no fault. Leaving scattered garbage bytes in
  roughly that same region (attempt 2) produced the **exact 999,999 fault**
  this project has only ever inferred indirectly until now (13.5's `yoda69`
  quote, this project's own Tachosoft mismatches). Two independent units
  now show the same shape: a wide region matters, clean/zeroed data in it
  is tolerated, and corrupted data in it is what actually triggers the hard
  fault - not merely "the primary field is wrong."

Nothing in this thread touches an offset resembling this project's own
`0x00-0x05` at all (bytes `0x00-0x1f` are identical across the original and
all three attempts), which is itself informative: on this unit, a correctly
isolated edit of only the narrow primary field (attempt 3) still didn't
work, with zero involvement of anything resembling `0x00-0x05`. That's
consistent with this project's own emerging picture - the gate is a wider
region than either single narrow field - rather than being specific
evidence about `0x00-0x05` itself, which may simply not exist in this form
on this particular firmware sub-variant.

Not yet done: writing any of these four files to this project's own bench
chip. They're from a different unit, so a direct write would show a wrong
number rather than new information about our own field boundaries - the
more useful test would be reproducing the "clean zero region = no fault,
garbage region = 999,999" split on our *own* chip and field boundaries,
which is a concrete, cheap next probe using tools already on hand.

### 16.1 Run: zero-blanking `0x70-0x8d` on our own chip - still fails

`probes/u05-zero70-8d-predonor.bin`: `predonor`'s exact bytes with
`0x70-0x8d` zeroed instead of `0xFF` (13.2 only ever tried `0xFF`), both
`0x00-0x05` and `0x6a-0x6f` left untouched. Result: **fails**, same fault
pattern as every other deviation tested. The zero-vs-`0xFF` distinction that
appeared to matter on `alimmo`'s unit (16) does not transfer to this
cluster - whatever is actually being checked here is more specific than
"is this region blank," on this firmware at least.

### 16.2 Run: a genuine, working, unmodified dump from a different real unit still faults

`dk-93c56-alimmo-original-160274mi.bin` written directly (not one of this
project's own probes - `alimmo`'s own real, unmodified, working dump).
Result: odometer showed a different (wrong, expected) number - this
cluster doesn't share `alimmo`'s scale/field-width either - and **trip and
needles still faulted**, same pattern as every other deviation tested.

This is worth being precise about: this is not corrupted, not garbage, not
a probe - it is a completely valid, currently-working EEPROM image on its
own real hardware. That it still fails here confirms the gate is not a
generic "is this well-formed Kansei/93c56 data" check - it is specific to
*this* chip's own original bytes, consistent with a per-unit checksum or
comparison value rather than a format/plausibility check anything genuine
Kansei data would pass.

### 16.3 Run: `alimmo`'s real 999,999-fault dump does not show 999,999 here

`dk-93c56-alimmo-attempt2-999999fault.bin` - the file that produced the
literal `999999` fault code on `alimmo`'s own cluster - written directly to
this project's chip. Result: odometer showed a different, computed number
(not `999999`), trip/needles faulted as usual.

This cluster's firmware never falls back to a fixed sentinel display for
invalid data, in any test run so far - it always decodes and shows
*something*. That means the checksum/validity gate on this firmware
controls the trip-counter and gauge subsystems specifically, and does not
gate the odometer decode/display path at all. `999999` is therefore a
firmware-specific fault behaviour, not a universal Kansei/93c56 constant -
useful to know before assuming any future match to "999999" generalizes
across units.

### 16.4 Broader forum sweep: one more directly-relevant thread, one dump confirmed as already-known reference data, one false lead

Widened the search (board part numbers, the `24810` cluster part-number
prefix, Russian-language forums, and searching for the fault itself rather
than the checksum) and followed up the most relevant new hits:

- **`digital-kaos.co.uk/.../349186-dump-dash-nissan-navara-d22-1998`**
  (2017-2023, same board part number `K11631 3S401` as this project's own
  chip markings, 93C46). Contains a widely-reshared reference dump,
  `dk-93c46-rastus86-201149km.bin` (saved to
  `reference/community-93c56-93c46-dumps/`) - confirmed byte-for-byte to
  contain the exact `38 80 c7 f1 3f 80` sequence pman92 cited in the
  pcmhacking thread (13.5) as "advertised online" at 201,149 km, at offset
  0x6a. This is the same underlying reference data pman92 already used, not
  new independent evidence - recorded here so it isn't mistaken for a fresh
  data point later.

  Far more valuable: **post #9 in that thread (`Gateox`, 2022) describes
  this project's own exact symptom on independent hardware.** After writing
  this same reference dump, the `999999` fault code cleared and "test
  method in the dash work[ed] correctly" - but after refitting to the
  vehicle, **fuel, temp, and other gauges still did not react**, and the
  thread ends unresolved with no fix posted. One caveat: `Gateox`'s cluster
  had been physically resoldered for an unrelated fault beforehand, so a
  residual hardware/sensor cause can't be ruled out there the way it can on
  this project's own bench-tested chip. Still, this is the first
  independent report of a checksum-cleared image that *still* leaves gauges
  dead after refitting - consistent with this project's own finding that
  the gate is per-unit-specific (16.2) rather than a generic
  format/plausibility check any correct-shaped Kansei data satisfies.

- **`digital-kaos.co.uk/.../288301-navara-93c56`** ("navara 93c56", 2015) -
  matched on chip size and vehicle name but is a **2006 Navara with a
  Visteon dash (Motorola HC912-based)**, not a Kansei cluster at all.
  Different manufacturer, almost certainly a different checksum mechanism
  if any. Not pursued past confirming the mismatch.

- Searches on the exact board part numbers (`K29451VB200`, `K11631`), the
  `24810` Nissan cluster part-number prefix, and Russian-language forums
  (`drive2.ru`, `drom.ru`) turned up general 93xx EEPROM background but no
  further Kansei-specific Navara dumps or checksum detail beyond what
  sections 13-16 already have.

### 16.5 `alimmo` attempt3 written to our own chip - result unreported

`dk-93c56-alimmo-attempt3-onlyfield.bin` (only `0x6a-0x6d` changed from that
unit's own original, per 16) written and verified on this project's chip.
The physical read (odometer/trip/needles) was never reported back before
the session moved on to section 17 - **pending**, not a negative result.
Check it whenever the bench is next connected; expected to fail like every
other foreign image (16.2), but not yet confirmed on this specific file.

## 17. Roadmap: restoring full functionality without giving up the corrected mileage (2026-09-11)

Explicit goal at this point: get trip counter and gauge tracking working
again *without* reverting the odometer to `predonor`'s original value. Four
options, ordered by how likely each is to actually succeed given everything
sections 13-16 have established - not by how much this project would enjoy
doing them:

1. **Donor cluster, not donor bytes.** Source a second same-generation
   Kansei 93c56 Navara/Frontier cluster already reading close to the
   ~300,000 km target, completely untouched. An unmodified chip passes its
   own checksum by construction - guaranteed working trip/gauges, at the
   cost of exact-km precision this project already tolerates (the current
   fix is 22 km under target, inside one display quantum). This is the only
   option on this list with no dependency on solving the checksum at all.
2. **Nissan CONSULT / factory dealer tool.** Cluster-swap odometer
   correction is a documented, manufacturer-supported service procedure on
   many platforms, not purely a hobbyist hack. Worth checking whether
   CONSULT-III (or a clone) has an instrument-cluster-initialization
   function for this generation before assuming only reverse engineering
   can solve it - not yet checked.
3. **A commercial Kansei-aware tool that *writes*, not just reads.**
   CarProTool already reads this exact chip (14.1). Digiprog3, OBDStar,
   Yanhua Mileage Master and similar commonly claim Kansei/93c56 write
   support; if one lists this specific board it likely already computes the
   correct checksum internally. Not yet checked whether any tool on hand,
   or cheaply available, names this board specifically.
4. **Map the primary field's actual bit-sensitivity.** Every single-bit
   test this project has run (15.7) was on `0x00-0x05`; the primary field
   `0x6a-0x6f` has only ever been changed by whole words or whole targets,
   never a single bit against an otherwise-untouched `predonor` baseline.
   `probes/u06-1bit-primary-field.bin` (byte `0x6b` bit 1 flipped, `0x00-05`
   and the rest of the image left at `predonor`'s exact bytes) tests this
   directly. If the primary field turns out to have *any* tolerance the
   `0x00-0x05` field doesn't, that's a real lever for nudging the encoded
   value while staying inside whatever the checksum accepts - if it's
   equally zero-tolerance, that door closes for good. **Not yet run - CH341
   not connected this session (`diag`: not found).**

Option 4 is the cheapest per-attempt and the only one this project can act
on unilaterally, but it's realistically a long, bit-by-bit mapping exercise
even in the best case, and sections 13-16 already show two independent real
units hitting this exact fault class with nobody solving it via EEPROM
bytes alone. Options 1-3 don't require cracking the checksum at all and are
more likely to actually restore full functionality; they haven't been
pursued yet only because they need parts sourcing or new tool access this
session didn't have. Recommended order for whoever picks this up next:
try 2 and 3 (cheap to just check) before committing more bench time to 4.

### 17.1 Options 2 and 3 checked - inconclusive, no direct evidence either way

Searched for a documented Nissan CONSULT cluster-swap
odometer-initialization procedure for this generation, and for any
commercial mileage tool (CarProTool, Digiprog3, OBDSTAR, Yanhua) that lists
this specific board for *writing*. Neither turned up confirming evidence:
CONSULT-III cluster programming is documented for VIN/NATS sync on newer
platforms but nothing specific to a D22-era odometer-initialization
function was found; tool vehicle-support lists mention 93c56 generically
and other Nissan models by name, but none of the searched sources name this
Navara/Kansei combination for writing specifically (13.4/14.1 already
showed **reading** works fine with CarProTool). This is an absence of
evidence, not evidence of absence - would need direct access to a tool
demo/trial or its full supported-vehicle database to actually settle it,
which wasn't available this session.

Also found: `mhhauto.com/Thread-Nissan-navara-mileage-correction--228404` -
same poster (`raheem1983`) and same car (2012 Navara 3.2, Calsonic Kansei
93c56) as the Digital Kaos thread already in 13.5 that ended with a gauge
fault. A reply here ("here you are...") carries no attachment, just an
emoji - a dead end, not a solved case.

## 18. Provenance of the region erase, a wider checksum sweep, external leads, and the ground-truth plan (2026-09-16)

No programmer was connected this session (`diag`: not found), so this is
analysis, research and preparation. The bench runbook in 18.6 is what the
next hardware session should execute, in that order.

### 18.1 One erased-region image exists, and its origin was never recorded

Sections 13.2 and 16.1 treat blanking `0x70-0x8d` as a test this project
chose. The dump timeline says the pattern predates that test:

- `dumps/restore300078-20260826-133423-GOOD.bin` (08-26 13:34, dump3,
  verified): the chip held `near-300078.bin` exactly, `0x70-0x8d` intact.
- `dumps/trip-erased.bin` (08-26 16:21, no timestamp suffix, no probe
  file, no analysis note): the same image with `0x70-0x8d` at `0xFF`, 30
  bytes, nothing else changed. Fifteen minutes later a dump3 tagged
  `triperased` failed on a garbled read
  (`triperased-20260826-163633-1.bin`, first read only).
- 09-01: the chip read as `predonor` at 18:45, as the `trip-erased.bin`
  image at 18:53 (`posttrip`, byte-identical) and at 19:17
  (`prerestore`), then as `predonor` again at 19:17 (`postrestore`). With
  one chip on hand at the time, that sequence is the saved file being
  written and read back during the 09-01 write-path work (the two commits
  of that day). `posttrip` is a copy of the file, and the 09-07 session's
  reading of it as a second in-truck erase, which is where 13.2 came from,
  was wrong.

That leaves exactly one candidate event, on 08-26 between 13:34 and 16:21,
after the corrected chip had been fitted to the truck. Two readings fit
the record:

- (a) `trip-erased.bin` was a single `ch341_93cxx dump` of the chip after
  the truck, in which case the firmware erased words 56-70 itself (an
  ERASE sets a 93C56 word to `0xFFFF`) and left the odometer field alone.
- (b) it was a constructed test image named for a hypothesis about the
  trip counter, like `near-300078.bin`, `step-273k.bin` and
  `wholecell-test.bin`, which also sit in `dumps/` without timestamps.

No transcript for 08-26 survives, and the 09-07 session never confirmed a
drive with the user. The name and the failed dump3 that followed lean
towards (a); nothing proves it. **The user is the only source: was
`trip-erased.bin` read off the chip after the truck, or built?**

Why it matters, under (a): the firmware writes to the EEPROM in fault mode,
and whatever it writes is ground truth about which words it manages.
Runbook steps 1 and 2 (18.6) test this on the bench, so the plan does not
depend on the answer; a firmware erase reproduced on the bench settles it.
Under (a), `0x70-0x8d` is firmware-managed state the firmware is willing to
erase, so trip meters, a fine counter or a journal fit it better than a
checksum store, which would be rewritten. The `predonor` values there
(units 0,12,7,12,12,12,0,12 then seven zeros) do not look like a monotone
fine counter.

### 18.2 What the bench symptoms do and do not mean

From the 09-07 transcript: on the bench the cluster gets power and ground
only, no senders. With open sender circuits a healthy cluster shows fuel
below E and a static temperature needle, and the user reported exactly that
for `predonor` as well ("the same symptoms with the predonor"). Needle
positions on the bench therefore carry little information on their own. The
discriminating bench symptom is the **trip button** (cycles trip A/B on
`predonor`, dead on every other image), and in the truck the fault is
tachometer, fuel and temperature dead with speedometer and odometer alive
(09-07 17:31). Needle observations in 13-16 remain useful as *changes*
between images, never as pass/fail on their own.

### 18.3 Generalised checksum sweep: still nothing

`work/cksweep.py` extends 15.8 in three ways: the computed value is searched
for anywhere in the image (every byte, every 16-bit word in both byte
orders, every decoded per-word unit value, every 3-word decoded V), the
inputs include the decoded cell views (units 0-31 per word, thermometer
level 0-5 per word) because the whole image is cell-coded, and
sum-to-constant schemes are tested by requiring the same value across
samples on differing inputs. 23 CRC-8 and 31 CRC-16 parameter sets from the
standard catalogue plus sums, XORs, Fletcher-16 and bit counts, over 39 byte
regions, in four views: 13,248 combinations per sample family.

Family `predonor` + `mattydr67` + `sanjaycip 1a` (three genuine km images):
zero non-trivial same-location hits, zero non-trivial constants. Two-sample
families produce hits at the chance rate expected for 8-bit values searched
at about 200 positions across 13k trials, and `mattydr67` and `sanjaycip 1a`
share most of their bytes, so their agreements are content overlap. Recorded
so this is not redone; the section 6 warning applies to every one of those
pair hits.

A firmware-variant-specific check would never agree across units, so this
sweep cannot rule a checksum out. It rules out the cheap standard forms on
the only data available.

### 18.4 External leads checked this session

- **SoftDump "NISSAN OLD KANSEI 93xx"** (UPA-USB script, 10 USD, SKU 65):
  lists NAVARA 93C46 and 93C56, DATSUN 93C56, FRONTIER 93C56, PICKUP 93C46,
  "covers most of NISSAN flaps 1996-2005", "complicated algorithm", stated
  accuracy **3 km**. Tachosoft's variant has a 33 km quantum; 3 km accuracy
  means their model writes more than the three coarse words, consistent
  with 13.2's finding that the displayed value draws on `0x70-0x8d`. Caveat
  from their FAQ: scripts run only with a genuine UPA-S programmer attached;
  clones and the old UPA-USB are unsupported. Their separate "KANSEI 93xx"
  script (newer 9356/9366/9376/9386 dashboards, 54 km accuracy) is the
  coarse one, and the wrong one for this cluster.
- **ETP LAB dump database** (etpvn.com, 10 USD per file): "Nissan | Datsun |
  1999 | 93c56 | KG-VJ216" and "Nissan | Frontier | 2002 | 93c56 | 6S005S0".
  This board is marked `K11631 VJ210`, so KG-VJ216 is the same VJ2xx part
  family. A genuine same-family image is the cheapest test of whether the
  gate is a pure function of EEPROM content: if it passes the trip test
  here, the gate is content-only and two same-variant valid images exist to
  diff; if it fails like `alimmo`'s (16.2), the per-unit theory gains
  weight. The displayed value will be wrong either way; that is beside the
  point of the test.
- **Digital Kaos 382520** (1998 Frontier D22, km, 93C46): a chip that went
  blank showed **999999**; a donated full dump (Intel HEX in post #4) showed
  411,768 km on that cluster, and editing the six bytes at `0x6a-0x6f`
  alone gave 289,602 km with no gauge or trip complaint. Same picture as
  14.1 and pman92: the 93C46 firmware tolerates a bare field edit, this
  93C56 firmware does not.
- **D22 (2001) service manual, EL-35, EL-39, EL-40** (`jdmfsm.info`,
  1997-2008 D22 Navara, SM3E-D22GG2): the speed input is a two-wire
  variable-reluctance sensor on combination-meter terminals **22 (W) and 23
  (R)**, ground 24 (B), battery 18 (R/G), ignition 17 (W/B), all on the white
  24-pin connector N4; tachometer input 21 (W), water temperature 19 (Y/R),
  fuel 20 (Y/G); speed output to the ECM on 57 (W/L, connector N6). The
  pman92 schematic (13.5) is an older single-ended variant ("SPEED 7pin"
  through 8.2k and 6.8k with a 1 uF filter), so the FSM pinout is the one
  to use for this 2001-2002 board.
- Forum sweep on the sister platforms (Patrol Y61, X-Trail T30, Terrano) and
  Russian sources: no published checksum for old Kansei; the Russian hits
  were correction-service adverts or unrelated clusters. Nothing beyond
  15.1, 16.4 and 17.1.

### 18.5 Where this leaves the model

Every fact still fits one description: the firmware validates the image
against something derived from more than the six-byte field, at single-bit
sensitivity, and only images the firmware wrote itself (or exact copies)
pass. Two sub-cases remain open and they lead to different fixes:

- **content-only, variant-specific**: any genuine same-variant image
  passes; the rule can be learned from a few firmware-written images.
- **per-unit**: the compare involves something outside the 93C56. The MCU
  is a 2001 mask-ROM Kansei part with the external EEPROM as its only
  obvious non-volatile store, which argues against this, though it is
  not excluded.

Both sub-cases are settled by the same experiment: make the firmware
write. The runbook below is ordered by information per bench minute.

### 18.6 Bench runbook for the next hardware session

Preconditions: `diag` GOOD; hash every post-write read against the source
file (14.5). Chip content is unknown until read: 14.7 says
`mirror-test.bin`, 16.5 says `alimmo` attempt3 was written after that. Read
first.

0. `work/dump3.sh statecheck` to learn what the chip holds. If it is
   `alimmo` attempt3, report its physical reading (16.5 pending).
1. **Firmware-write probe on the known-good image, no extra wiring.** Write
   `predonor`, verify, fit, power up. Cycle trip A/B, hold reset to zero a
   trip, power-cycle twice, leave it powered five minutes. `dump3.sh` and
   diff against `predonor`. Any changed byte is firmware-managed state: it
   shows where the trip meters live and whether every write touches a
   check value.
2. **Reproduce the in-truck erase on the bench.** Write `near-300078.bin`,
   power up, press trip, power-cycle, wait, dump. If `0x70-0x8d` goes to
   `0xFF` on the bench, the erase trigger is reproducible without driving
   and can be bracketed (before/after the trip press, before/after the
   power cycle).
3. **Virgin-mode axis, three probes, five minutes each.** Chip-absent is
   the only state in which 999999 shows and everything works (13.3, 09-07
   17:07). Nobody has recorded what a *present* blank chip does.
   - `probes/u09-blank-ff.bin` (all `0xFF`): does it show 999999 with a
     working trip button and gauges? Dump afterwards: any write means the
     firmware initialises a blank part, which would be a firmware-written
     valid image at low mileage. `dump3.sh` rejects a near-uniform image by
     design, so read a blank or nearly blank chip with `work/ch341_93cxx
     dump` directly, twice, and compare the two files.
   - `probes/u07-ffprimary-predonor.bin` (`predonor` with only `0x6a-0x6f`
     erased): does the 999999 path key on the primary field alone, and does
     trip work in that state?
   - `probes/u08-ff0005-near300078.bin` (`near-300078` with `0x00-0x05`
     erased): is an erased secondary field treated as absent rather than
     wrong?
4. **VSS drive on `predonor`** (needs one 1k resistor and two wires to N4).
   `work/ch341_pulse <hz>` on CH341 socket pin 5 (MOSI) through 1k to meter
   terminal 22; CH341 ground to terminal 23 and to the cluster ground on 24.
   EL-41 (LHD diesel with tachometer) uses the same terminals 22/23/24/21
   as EL-39 (petrol), so the pinout holds for either engine; still confirm
   22 and 23 by continuity from the connector to the speed-input
   conditioning parts on the board before wiring. The CH341 gives a
   unipolar 0 to 5 V square wave, and a variable-reluctance input may need
   it AC-coupled (a 1 uF series capacitor after the 1k) or driven
   differentially (pulse on 22, ground or the inverse on 23); try both
   before concluding the input rejects pulses.
   Start at 20 Hz and confirm the speedometer needle moves; note the needle
   reading at a known frequency to get pulses per km
   (`pulses/km = 3600 * f / v`). With `predonor` in, trip A resolves 0.1 km,
   so a short run calibrates the count directly. Then run until the odometer
   has stepped at least three times (three quanta, about 100 km of pulses)
   and `dump3.sh` after each step. The diffs between consecutive
   firmware-written images are the algorithm, or at least its dependency
   structure, measured rather than guessed. Also record the highest
   frequency at which the odometer still advances; that number decides
   whether a roll-up (18.7) is a usable fallback.
5. **Only then** fit: with three or more consecutive firmware-written
   images, hold one out (section 6) and encode 300,078 with whatever rule
   the diffs support. If `0x00-0x05` never changes across increments, it is
   not a running check value and the search moves elsewhere.
6. `probes/u06-1bit-primary-field.bin` (17, option 4) if time remains.

Off the bench, in parallel: buy the ETP LAB KG-VJ216 dump (10 USD) for the
content-only test in 18.5. Consider the SoftDump script only if a genuine
UPA-S is reachable.

### 18.7 Roll-up as the fallback, with numbers

If step 4 shows the firmware counts pulses far above real road speeds, the
odometer can be advanced through the firmware, which keeps every check value
consistent by construction. From `predonor` (764,857) the display must pass
999,999 and reach 300,078, i.e. 535,221 km of pulses. At 637 revolutions
per km and one pulse per revolution that is 3.4e8 pulses: 19 hours at
5 kHz, 95 hours at 1 kHz, and proportionally more if the sensor gives
several pulses per revolution. Two unknowns keep this a fallback: what the
firmware does when V passes the three-word range (about 1,093,000 km under
the section 11 model; 13.2 already shows the real counter is wider), and
whether the input filter and the speed logic accept kHz-range pulses. Step
4 answers the second cheaply; the first is answered only by doing it. A
firmware-initialised blank chip (step 3) would shorten the distance to
300,078 km.

## 19. The chip is not the variable, and the same bytes once displayed a different number (2026-09-18)

Bench session with the CH341 connected. Two owner-reported facts and one
record check between them overturn the premise sections 13-18 were built on.

### 19.1 Run: the exact original bytes leave the trip dead

`predonor`'s 256 bytes written to the bench chip and verified by read-back
(`2a535ada`), fitted, cluster powered with **both** 12V feeds present
(terminal 18 constant and terminal 17 ignition, confirmed by the owner, so
the cluster is in full run mode). Result: odometer displayed 764,857,
matching the decode, so the read path is sound. **The trip button did not
cycle A/B and would not reset.**

Read back afterwards: byte-identical to what was written, 0 bytes changed.
The firmware wrote nothing. That write result is confounded, since the trip
reset never happened, so it is not evidence either way about whether the
firmware writes on a real reset.

Section 13.3's table lists `predonor` original as "trip works". That row is
now contradicted by a controlled run on verified bytes. It came from an
ambiguous dictated reply on 2026-09-07 (17:41), in the same conversation
where the owner also said "I have the same symptoms with the predonor, like
the original chip" (17:28). **Treat 13.3's "works" row as withdrawn.**

### 19.2 The owner has tested the original physical chip: same fault

Reported directly this session: the original chip, the one pulled from this
cluster, produces the same fault. The replacement 93C56 is therefore not the
variable, and every chip-level theory (part variant, ORG pin, write timing,
marginal socket joint) is ruled out by that one observation. Reads work on
both, the odometer displays on both, the trip is dead on both.

Combined with 19.1: **no EEPROM content and no EEPROM part restores the trip
counter.** Fifteen distinct images across six sessions, including two
genuine unmodified dumps from other real units and this cluster's own
original chip, all fail. That is not the signature of a content checksum
with one passing value. It is the signature of the gate living somewhere
other than the 93C56.

### 19.3 Chip absent is a different code path, and it is the only working state

With no chip fitted: odometer shows 999999, both needles rise, and the trip
button **works, including reset**. The button hardware and the MCU input are
therefore sound, and the firmware is choosing to ignore the button whenever
a readable chip is present. A hardware break in the button circuit is
excluded.

Note also that the bench has no senders connected. With an open fuel sender
and an open temperature sender, needles resting low is the correct
behaviour, and needles rising with no chip is the abnormal one. The needle
positions recorded through sections 13-16 are therefore weak evidence and
should not be read as pass/fail. The real gauge evidence is the in-truck
observation from 2026-09-07 (17:31), where tachometer, fuel and temperature
were dead **with** senders connected, while speedometer and odometer ran.

### 19.4 The contradiction in the record: one byte string, two displayed values

`analysis/data.py` line 9, the project's own measurement log:

    CLUSTER = [
        ("07fe0780f8f1", 212562),   # original contents, as found
        ...

Those are `predonor`'s exact odometer bytes, and the log records the cluster
displaying **212,562 km** for them on 2026-08-23. STATUS.md carried the same
number as "exact, read off the bench-powered LCD". The `TACHOSOFT` table
directly below it contains `(212562, "fff13ffe3f80")`, which only makes
sense if 212,562 was a number already in hand and being looked up.

On 2026-09-07 the same bytes on the same cluster displayed **764,857**,
confirmed against the LCD and matching the cell model exactly.

Section 13.1 resolved this by declaring that 212,562 "was never a real
measurement of this field on this cluster, at any point". That conclusion
rescued the model by discarding a recorded measurement, which is the failure
mode section 6 exists to warn about. The alternative reading, never tested,
is that both measurements are real:

**The displayed odometer is not a pure function of the 93C56's contents.**
Something in the cluster outside the 93C56 contributes, and it changed
between 2026-08-23 and 2026-09-07, which is the same window in which the
trip and gauge fault appeared.

The first dump of all (`navara-20260823-113045`, field `fe078007f1f8`) is a
pure byte-swap of `predonor` and is an early CH341 byte-order artifact, not
a content change, so it does not account for the discrepancy.

### 19.5 What this leaves, and what it rules out

The gate is not EEPROM content (19.1, 19.2) and not the EEPROM part (19.2)
and not the button circuit (19.3) and not the bench harness (19.1, both
feeds present). The leading explanation is state held by the cluster MCU
itself, either an internal redundant odometer copy that no longer agrees
with the external one, or a latched tamper/fault flag set during the
project. Either fits every observation, including the one thing no EEPROM
theory has ever explained: why the cluster's own original chip fails.

This was in fact the project's first instinct, in the superseded section at
the end of STATUS.md ("find the other memory device on the cluster board...
the cluster MCU's internal EEPROM"), and it was dropped once `0x6A` was
confirmed as the odometer field.

**Confirmed with the owner, 2026-09-18:** the cluster did display 212,562
before the chip was first removed. Both measurements in 19.4 are real.

### 19.6 Therefore the changed state is not in the 93C56, by elimination

With the 212,562 reading confirmed, no inference is needed for this part:

1. Before any write, content C in the chip produced display 212,562.
2. Content C was dumped and is preserved as `predonor` (the 11:45 read of
   2026-08-23; the 11:30 read is the same content byte-swapped).
3. `predonor` was written back to a chip and verified byte-identical, twice,
   most recently this session.
4. The same content C now produces display 764,857 and a dead trip button.

A pure function of the chip's contents cannot return two different values
for the same contents. **Something outside the 93C56 changed between those
two readings and has not changed back.** No sequence of writes to this chip
can restore it, which is precisely what fifteen images across six sessions
have demonstrated without the reason being understood.

What that also means for the model: the scale constant 33.36053 in
`work/kansei_codec.py` was fitted entirely to measurements taken after the
change (2026-08-23 13:29 onward, plus the 08-25 probe series). The one
measurement from before the change is the one `analysis/weights.py` has
always flagged as unexplainable ("needs V ~6371, which the table cannot
produce"). The codec is an accurate description of the cluster in its
current state and should not be assumed to describe it in its original
state.

The most likely trigger, untested: the cluster was powered with no EEPROM
fitted at some point on 2026-08-23 between 11:45 and 13:29. A firmware that
finds no EEPROM may write a default or a fault marker into its own internal
store, and that would be both permanent and invisible to every experiment
this project has run. This has since been repeated many times, most recently
this session, so if it is the cause it has been reinforced repeatedly.

**Cheapest untried action, zero cost and zero risk:** Nissan clusters of
this era commonly enter a diagnostic or segment-test mode when the trip
reset button is held down while power is applied. That mode may report a
fault code, and on some variants it offers a reset. This has never been
attempted on this cluster. It should be the first thing tried next session,
before any further EEPROM work.

## 20. The upper half of the chip, and a correction to section 19.6 (2026-09-18)

### 20.1 Correction: 19.6's elimination rested on an unchecked assumption

Section 19.6 argued that because content C displayed 212,562 and the
preserved copy of C now displays 764,857, the changed state must be outside
the 93C56. That argument assumes the dump taken on 2026-08-23 at 11:45 is
in fact C. The owner challenged exactly this assumption, and it was never
checked. The chip was desoldered from the board before that first read.
EEPROM data retention degrades under soldering heat, and the failure mode is
cells drifting toward the erased state, which reads as `0xFF`. If the chip
lost content during removal, then C was never captured, every later
comparison is against a damaged baseline, and no cluster-internal state is
needed to explain anything. **19.6 is withdrawn as an elimination and stands
only as one of two live explanations.**

Also corrected: sections 19.2 and 19.5 state that no EEPROM content affects
the trip counter. That is too strong. Section 14.2 records two community
images that produced a partial trip response, which is more than this
cluster's own baseline has ever produced. EEPROM content does modulate the
fault.

### 20.2 The upper half of the chip has been blank since before the first write

Scanning every 256-byte image this project has ever held, by word, for data
in words 71-127 (bytes `0x8E-0xFF`):

| image | words 71-127 in use | trip response |
|---|---|---|
| every dump ever read from our chip, from 08-23 11:30 onward | 0 | none |
| `predonor` / `navara-93c56-VERIFIED` | 0 | none |
| `alimmo` original (other unit, working) | 0 | n/a |
| `mattydr67` 130k | 38 | **partial** |
| `sanjaycip` 1a | 38 | **partial** |
| `sanjaycip` 1b (byte-swapped copy of 1a) | 38 | none |
| D40 `nissannavara` (different generation) | 38 | none |

Our chip's upper half was already blank in the first read of all, on
2026-08-23 at 11:30, before any write this project made. So this project did
not erase it. Either it is legitimately blank on this variant, which
`alimmo`'s working dump makes possible, or it was lost before the first
read, which desoldering heat would account for.

The correlation is the strongest this project has found: every image with
that region populated and in the right byte order produced a trip response,
and every image with it blank produced none. The two exceptions both have
an explanation, since `sanjaycip` 1b is a mechanical byte-swap of 1a and the
D40 file is a different cluster generation entirely.

`mattydr67`'s and `sanjaycip` 1a's upper halves are **byte-identical to each
other**, despite being posted by different people in different years. That
is shared reference data rather than per-unit state, which makes grafting it
onto our own image a reasonable thing to try rather than a wild guess.

One caveat worth recording: read in this project's own word convention, that
upper-half data is malformed, since words such as `8000` carry no marker
bit. Byte-swapped it becomes well formed (`8000` to `0080`, `f1f8` to
`f8f1`, `803f` to `3f80`). So the region as it sits in those forum files may
itself be byte-swapped. Both forms are prepared as probes.

### 20.3 The single-variable probe

`probes/u11-predonor-plus-upper-verbatim.bin`: `predonor`'s exact 256 bytes
with only words 71-127 replaced by `mattydr67`'s, verbatim. 70 bytes differ
from `predonor`, the odometer field at `0x6a-0x6f` is untouched, and the
entire lower half is this cluster's own. This isolates the one variable that
has ever correlated with a trip response.

`probes/u12-predonor-plus-upper-swapped.bin`: the same graft with that
region byte-swapped into this project's convention, to be run second.

Written and verified (`f228c3dc`). Awaiting the physical read.

## 21. Breakthrough: the EEPROM carries configuration, and the odometer field is not gated (2026-09-18)

Same bench session as 19 and 20, continued. This section supersedes the
central claim of sections 13 through 18.

### 21.1 A foreign image fully restores the cluster

`dk-93c56-mattydr67-130000km.bin` written to our chip and fitted, with both
12V feeds present. Reported by the owner:

- odometer 671,162 km, reproducing the 2026-09-08 reading exactly
- **tachometer, fuel and temperature needles all alive**
- **trip button cycles, and the reset works**

The fault is therefore not merely reduced by that image, it is cleared. One
difference remains: the display offers a single `TRIP` where this cluster
should offer `TRIP A` and `TRIP B`.

### 21.2 The odometer field is not part of the validation

Two images were then written whose only difference from the working image
was the six bytes at `0x6a-0x6f`. Both kept the gauges and the trip button
working. **Changing the odometer value does not disturb the cluster's
working state.**

This falsifies the checksum theory that sections 13 through 18 were built
on. The correct account of those sessions is that every image tested before
today was built on our own damaged baseline, so every test returned "fails"
and carried no information about the field at all.

### 21.3 What the EEPROM actually holds

The working image configures this cluster as a different variant: one trip
meter instead of two, and a different odometer constant. So the EEPROM
carries the cluster's configuration alongside the reading. That accounts for
the whole history at last. Our own image is missing or has lost part of that
configuration, so the firmware runs a stripped mode with no gauges and no
trip counter, while still decoding and displaying the odometer.

It also explains 19.4's contradiction without needing any state outside the
93C56. The same bytes displayed 212,562 and later 764,857 because the
constant applied to them changed, and that constant lives in the chip.

### 21.4 Measured: the display rule in this configuration

Three field values were written into the working image and read off the LCD:

| field V | displayed | predicted by the rule below |
|---|---|---|
| 17,326 | 671,162 | 671,162 |
| 10,161 | 432,134 | 432,134 |
| 6,203 | 95,126 | 300,093 |

The first two give, exactly:

    km = V * 33.36053 + 93,157.5

The scale is this project's own original constant. The additive term comes
from the rest of the working image and is the same 93,156 km step section
13.2 saw when the region past the field was altered. Two independent exact
hits, so this is measured rather than fitted.

### 21.5 Measured: one cell pattern reads as zero

The third row above is not a failure of the rule. 95,126 km is exactly what
V = 59 produces, and 59 is 27 + 32 * 1, which is the intended value with the
**third word contributing nothing**. That word was `0x0490`, being one bit of
C3 (nominally 4) plus one bit of C4 (nominally 2).

**`0x0490` reads as 0 units on this cluster, not 6.** The first two words of
the same image read correctly, which is what makes the arithmetic
unambiguous. This contradicts the partial-cell rule in section 11, which
holds that C3 gives 4 per bit and C4 gives 2 per bit. That rule was measured
for those cells individually; the mixed single-bit combination was never
tested and does not behave as the rule predicts.

Practical consequence, and a trap for anyone generating fields
programmatically: prefer whole cells. `work/kansei_codec.py` will emit the
mixed pattern for some values, and `probes/t01` is what happens when it does.

### 21.6 Measured: the firmware does not write on a trip reset

With the working image fitted, the owner cycled the trip and performed a
reset. The chip was then read three times. **Zero bytes changed.** This
cluster does not persist trip state to the EEPROM, which closes the
ground-truth avenue queued since 13.6 and removes the firmware as an
explanation for the erased region in `trip-erased.bin`.

### 21.7 Measured: the upper half is inert

`probes/u11`, our image with words 71 to 127 grafted verbatim from the
working image, changed neither the trip behaviour nor the displayed number.
The correlation noted in 20.2 is therefore not causal, and words 71 to 127
feed neither the trip logic nor the odometer computation.

### 21.8 Where this leaves the job

`probes/t04-mattydr67-base-300100-v3.bin` is the working image with only the
odometer field retargeted, using cell patterns this cluster has been
observed to honour, predicting 300,093 km against a target of 300,100.

Outstanding after that: the single trip instead of A and B, which is a
configuration difference, and confirmation of the units marker on the LCD.
`probes/t03-ours-plus-missing-words.bin` is the route back to our own
configuration. It is our image with only the three lower-half words that are
blank in ours and populated in the working image, being words 38, 39 and 51.
If our chip's damage was erasure, those three words are the damage, and t03
restores our own variant with our own scale and no borrowed settings. If t03
does not do it, the 60 differing lower-half words bisect in about six cycles
against a positive control that is now known to reproduce.

### 21.9 SOLVED: the cluster requires legal thermometer words, and that is the whole fault

Two further probes finished the picture. `probes/t05`, our own repaired
configuration with the odometer retargeted, displayed 299,978 and killed the
gauges and trip. 299,978 is V = 8992, which is the intended 8996 with the
first word contributing zero. That word was `0x0480`, one bit of C3.

So a single bit of C3 reads as **0**, not 4. Section 11's claim that C3 gives
4 per bit is wrong, and `analysis/weights.py`'s `r-C3-1bit` measurement should
be treated as unreliable. Two bits of C3 do read as 8.

The rule that covers every observation is the **bit count** of the word. The
superseded section at the end of STATUS.md recorded it in the very first
session and it was then forgotten: every word of a genuine dump has a
popcount in {1, 4, 7, 10, 13, 16}. Checking every word this cluster has been
observed to accept or reject:

| word | bits | legal | result |
|---|---|---|---|
| `07fe` `0780` `f8f1` | 10, 4, 10 | yes | predonor, reads correctly |
| `3e9e` `008e` `00f0` | 10, 4, 4 | yes | t04, reads correctly, gauges fine |
| `0480` | 2 | no | read as 0, gauges killed |
| `0490` | 3 | no | read as 0 |
| `009e` `3e8e` `0680` | 5, 9, 3 | no | **this is `near-300078`** |

`near-300078.bin`, the image this project shipped as its answer in August and
refitted in September, has three illegal words. That is what caused the
original trip and gauge fault. There was never a checksum, never a second
field, and never any cluster-internal state. The image was malformed and the
firmware rejected it.

One qualification: this holds for our own configuration. Mattydr67's
configuration is more tolerant, since t02 carried the illegal word `068e`
(6 bits) and worked. That tolerance is a reason to prefer it.

### 21.10 Why the delivered image uses the donor configuration

Reaching 300,100 km in our own configuration is not possible with whole
cells alone. With whole cells the reachable values step from 273,254 to
409,894, so our configuration forces a partial-cell word, and partial cells
are where every failure has occurred. The donor configuration reaches the
target with three legal, whole-cell-friendly words and tolerates partials
besides.

`probes/t04-mattydr67-base-300100-v3.bin` is therefore the delivered image:
300,093 km, tachometer, fuel and temperature alive, trip button cycling and
resetting, verified on the physical cluster. The scale per count is 33.36053
in both configurations, differing only by an additive constant, so the
odometer will continue to count at the correct rate as the vehicle is driven.

### 21.11 Our own configuration rejects every odometer value but its original

Three field changes have now been made against our own configuration, each
with a different class of encoding, and all three killed the trip counter:

| image | field | encoding quality | result |
|---|---|---|---|
| `step-273k` | `3ffe 3ffe 00fe` | legal bit counts, whole cells, valid thermometer order, markers present | trip dead |
| `probes/t05` | `0480 3e8e 0680` | one illegal word (`0480`, 2 bits) | trip dead, read as V=8992 |
| `probes/t06` | `00b2 3b8f 0382` | legal bit counts and markers, but C3 filled at bits 9 and 8 rather than from bit 10 | trip dead, displayed 167,670 |
| `predonor`, `t03` | `07fe 0780 f8f1` | the original | **trip works** |

`step-273k` is the decisive row. It is a perfectly well formed field, whole
cells throughout, correct thermometer ordering, marker on every word, and it
differs from our own image in the odometer field alone. It still faulted.

So the legality rule of 21.9 explains which words the cluster *reads* as
zero, and it explains nothing about the gauge fault. Our configuration
validates the odometer value itself against something we have not found, and
accepts only the value it shipped with. Mattydr67's configuration does not.

`t06` also exposed a third encoding constraint worth recording: the cells
are thermometer coded and fill in a fixed direction, C3 from bit 10 downward
and C4 from bit 4 upward. `0x0300`, being C3's lower two bits without bit 10,
is not a reachable state and is not counted. Any generator must pick cell
patterns from the reachable set, not from arbitrary bit combinations of the
right population count.

### 21.12 Delivered

`probes/t04-mattydr67-base-300100-v3.bin`, sha256 beginning `c87cb976`.

- odometer 300,093 km against a true 300,100, which is 7 under and inside
  one display step
- tachometer, fuel and temperature gauges all working
- trip button cycles and resets
- verified on the physical cluster on 2026-09-18

Known limitations, both accepted knowingly:

1. A single `TRIP` rather than `TRIP A` and `TRIP B`. Our own repaired
   configuration produces a single trip as well, so this is a property of
   this donor cluster and not of the image.
2. The base image is structurally unlike a genuine dump. Only 44 of its 94
   used words carry the `0x0080` marker, where our own image and `alimmo`'s
   genuine dump carry it on all of theirs. It nevertheless drives this
   cluster correctly in every observable respect. The per-count scale is
   33.36053 in both configurations, differing only by an additive constant,
   so the odometer should continue to count at the correct rate.

Recommended validation once refitted: drive a known distance, twenty
kilometres or more against a GPS or a marked route, and confirm the odometer
advances by the same amount. That is the one property the bench cannot test.

## 22. Two byte-order families, and the cluster identified (2026-09-18)

### 22.1 Every dump belongs to one of two byte-order families, and this cluster wants one of them

With 24 further community dumps collected, testing each image for the
`0x0080` marker as stored and byte-swapped splits them cleanly in two, with
nothing in between:

- **Family A**, well formed as stored: ours, `alimmo`, `sanjaycip` 1b,
  `afitijuana`, the 2004 Navara set, the `claudio35` 2004 files.
- **Family B**, well formed only once byte-swapped: `mattydr67`,
  `sanjaycip` 1a, `MOUTRO`, `knok`, `fcarocha`, `przemkis`, the
  `claudio35` labelled Frontier files.

Cross-referencing against every physical test this project has run:

| image | family | result on this cluster |
|---|---|---|
| `mattydr67` | B | full function |
| `sanjaycip` 1a | B | partial trip response |
| `sanjaycip` 1b | A | nothing |
| `alimmo` original, genuine and working on its own truck | A | faulted |
| ours | A | rejects any odometer change |

Family membership predicts the outcome in every case tested. This reframes
20.2 and 21.12: `mattydr67`'s image is not structurally anomalous, it is
simply stored in the other byte order, and this cluster wants that order.
Whether our own tooling reads and writes in the opposite convention, or the
two families are genuinely different firmware generations, is not resolved
here and matters less than the fact that the split predicts behaviour.

### 22.2 The cluster identified from its markings

The board carries two Nissan part numbers and they come from different
blocks of the catalogue, which is consistent with the owner's account that
the cluster is a donor.

- **`VJ513` is `24820-VJ513`**, the speedometer assembly. Catalogue
  applicability is **King Cab D22, Europe and Europe RHD, 02.1998 to
  11.2001, TD25 and TD25TI diesel, DX trim, manual**. That is the correct
  family for a Cyprus D22.
- **`K11631 VJ210` is `24814-VJ210`**, the printed circuit plate only, whose
  listed applicability is JDM and GCC rather than Europe.

The European D22 meters of 1998 to 2001 are the `24820-VJ5xx` block, Kansei
built. JDM D22 meters are `VJ2xx` and Denso built. European 2001 to 2005
units are `VK4xx`. So this unit pairs a European diesel speedometer assembly
with a JDM or GCC circuit board, and the board date codes of 2001 to 2002
sit at the tail of the `VJ5xx` window.

Not documented anywhere the research reached: any catalogue distinction
between kilometre and mile variants, any coding procedure or strap for
units, and any separate tachometer part number for the European D22.

### 22.3 Trip A and B is documented for this generation after all

Section 21.12 concluded the single `TRIP` is a property of this donor
cluster, on the grounds that two independent configurations both produce it.
That conclusion is weakened by the research: owner documentation for the D22
Navara states that a **momentary** press of the odometer and trip switch
toggles between Trip A and Trip B. So the function exists on this
generation, and the single `TRIP` seen here may be a configuration state
rather than a hardware variant. Worth retesting with a short press
specifically, since a long press is the reset.

### 22.4 Donor sourcing, if it comes to that

Search on `24820-VJ513`, `24820-VJ512`, `24820-VJ519`, `VJ513`, `K11631`,
`NKVJ519`. Two warnings recorded from the research. The large right-hand
drive used pool is the United Kingdom and those units are almost certainly
miles, mapping to the RHD-only `VJ5xx` numbers. And engine family governs
the tachometer, since TD25 is mechanically injected while the KA24E petrol
units expect ignition pulses, so a donor must match engine family and not
merely the part number block. Demand a photo of the dial face, a photo of
the stamped `VJ5xx` number on the speedometer body, and the odometer
reading. A repair service, tachopix.de, advertises this exact fault family
on `K11631-3S401` boards from 256 euro.

## 23. The MOUTRO configuration restores trip A and B but uses a different encoding (2026-09-18)

### 23.1 Trip A and B recovered

`dk-93c56-MOUTRO-pickup-d22-donor-unknownkm.bin`, a D22 Pickup 2000 donor
image and a member of the byte-order family this cluster accepts (22.1),
written and fitted. Result: gauges working **and trip A and trip B both
present**. This overturns 21.12's conclusion that the single trip is a
hardware property of this donor board. It is configuration, held in the
EEPROM, and the right configuration restores it. It also confirms the
navaraforum documentation cited in 22.3.

Odometer on that image: 231,419 km, which is unrelated to this vehicle since
the donor's mileage is unknown.

### 23.2 Its odometer encoding is not the one this project solved

Four controlled readings were taken on that configuration, varying only the
six bytes at `0x6a-0x6f` and reading the LCD:

| field units (w0, w1, w2) | displayed |
|---|---|
| 0, 0, 0 | 52 |
| 0, 0, 1 | 439,857 |
| 7, 1, 22 | 231,419 |
| 18, 1, 24 | 178,830 |

The constant is 52 km, measured directly rather than fitted. One unit of the
third word is then 439,805 km, against 34,161 km in the configuration this
project solved, a ratio of 12.87 and not a clean multiple. Solving the
remaining pair puts the first word's weight at 278,891 km per unit, which is
larger than the third word's. A first word outweighing the third is not a
positional encoding at all, so `V = u0 + 32*u1 + 1024*u2` does not describe
this configuration, and neither does any rescaling of it.

Note also that the second reading is lower than the third despite a larger
nominal V, so the display wraps within the range these fields reach.

This configuration therefore needs its own derivation, by the single-cell
probe method of sections 8 to 11. That is a session of bench work, not an
arithmetic step, and it was not attempted.

### 23.3 Tachosoft checked against a known reading and rejected for the third time

Using 231,419 km, a value this cluster was physically observed to display,
as an oracle, six Tachosoft 23.1 entries were asked to encode it:

- Nissan Pick Up 93c56, Frontier Kansei 93c56, Double Cab 93c56 all return a
  24-byte structure of "String #1" of 16 bytes plus "String #2" of 8 bytes.
  That is not this cluster's six-byte field and those entries describe a
  different cluster family.
- Nissan Navara 93c56 1999 and Nissan Datsun 93c56 both return
  `F1 FF 81 F8 81 C0` for 231,419 km. The cluster produces that reading from
  `FE 00 8F C0 F1 F8`. Decoded under this project's model the Tachosoft
  answer is V = 542 against the real field's V = 22,567.
- Nissan King Cab 93c56: no entry.

No entry reproduces the observed bytes. Combined with 13.4, Tachosoft has now
been wrong on this hardware three separate times, which is consistent with
the forum report in 21.9's sources that its Kansei coverage is both
inaccurate and destructive of the surrounding bytes.

### 23.4 Remaining route to a complete result

`MOUTRO` and the delivered image's base differ in 96 of 128 words. Bisecting
between them to find which words carry the trip A and B behaviour needs about
seven write-and-fit cycles. Those words could then be grafted into the
delivered image, which already has a solved and verified odometer
calibration, giving the correct mileage and both trip meters together. That
is the recommended next session, and it is a much smaller job than deriving
the MOUTRO encoding from scratch.

## 24. SOLVED: the encoding is binary with majority-voted cells (2026-09-18)

### 24.1 The derivation

Working configuration established (section 23.1), the odometer field alone
was varied and the LCD read, clearing every cell to establish the constant
and then setting one cell at a time in the high word:

| stored field | LCD | what it isolates |
|---|---|---|
| `800080008000` | 52 | the constant, measured directly |
| `803880008000` | 160 | low word, C2 |
| `800080008007` | 55,028 | high word, C3 |
| `800080008038` | 110,004 | high word, C2 |
| `800080008e00` | 439,857 | high word, C5 |
| `80008000f000` | 879,662 | high word, C4 |

The cell weights come out as 1, 2, 8 and 16 relative to C3, with the value 4
missing. The missing value is **C1**, the cell every earlier section of this
document calls inert. It is inert in the other configuration and carries
value here.

So the cells are not magnitudes at all. **Each word is a 5-bit number, and
each bit is stored as a three-bit cell read by majority vote:**

    bit 1 = C3 (0x0700)   bit 2 = C2 (0x3800)   bit 4 = C1 (0xC001)
    bit 8 = C5 (0x000E)   bit 16 = C4 (0x0070)   marker 0x0080 always set

    N  = value(w0) + 32*value(w1) + 1024*value(w2)
    km = round(52 + N * 53.68711) mod 1,000,000

Majority voting explains every partial-cell anomaly this project chased for
six sessions. Two bits of three reads as set, one bit of three reads as
clear. Section 21.5's "a single bit of C3 reads as 0" is exactly that, and
section 11's "cells carry proportional value" was an artifact of fitting a
magnitude model to a redundancy scheme.

### 24.2 Validation

One free parameter, the step, fitted against **eight** independent physical
readings including two taken before the model existed. It reproduces all
eight, six exactly and two within one kilometre of rounding. A ninth
reading, the delivered image, was predicted at 300,109 before it was written
and measured 300,110.

That is the standard section 6 demands and which the two earlier failed
models did not meet.

The step of 53.68711 is Tachosoft's documented Kansei constant of 53.6866 to
within the fit, so this configuration runs the standard Kansei encoding.
This cluster's own damaged configuration, at 33.36053, was the outlier
throughout.

Implemented and self-testing in `work/kansei_binary.py`. The older
`work/kansei_codec.py` describes the damaged configuration and is kept for
that purpose only.

### 24.3 DELIVERED

`probes/FINAL-moutro-300100.bin`, sha256 beginning `6d123e6f`.

- **odometer 300,110 km** against a true 300,100, which is 10 over and the
  closest this encoding can reach, the next value down being 44 short
- **tachometer, fuel and temperature gauges working**
- **trip A and trip B, both present, cycling and resetting**
- verified on the physical cluster, 2026-09-18

It is the D22 Pickup 2000 donor image with three words changed, the odometer
field and nothing else.

## 25. ROOT CAUSE: the first write flipped the cluster from kilometres to miles (2026-09-18)

### 25.1 The two configurations differ by exactly the mile factor

Fitting each configuration from readings taken on this cluster:

| configuration | step per count | constant |
|---|---|---|
| mattydr67 base | 33.36051 | 93,158 |
| MOUTRO base | 53.68711 | 52 |

The ratio of the steps is **1.60930**, against 1.609344 kilometres per mile.
A difference of 0.003 percent. The two configurations are the same encoding
counting the same physical distance, one in miles and one in kilometres.

The step this project called its "solved" constant since section 11, the
33.36053, is therefore the **mile** step. It was never a kilometre scale.

### 25.2 This resolves section 19's contradiction with no hidden state

`predonor`'s own field decodes under section 24's binary model to N = 22,585.
Evaluated both ways:

| configuration | predicted | actually displayed |
|---|---|---|
| kilometres, step 53.68711 | 212,575 | **212,562**, on 2026-08-23 before any write |
| miles, step 33.36053 | 764,856 | **764,857**, on 2026-09-07 after the first write |

The kilometre prediction is within a quarter of one display step. The mile
prediction is exact to one kilometre.

Section 19.4 recorded that the same bytes displayed two different numbers
six weeks apart and could not explain it. Section 19.6 concluded by
elimination that state outside the 93C56 must have changed, and section 20.1
withdrew that as one of two possibilities. **The answer is neither.** The
bytes never changed and nothing outside the chip changed. The cluster's unit
configuration changed, and that configuration lives in the EEPROM outside
the odometer field.

### 25.3 The causal chain, end to end

1. The cluster was a donor unit, configured for **kilometres**, reading
   212,562 km, everything working.
2. On 2026-08-23 at 13:29 the first write was applied, a patch derived from
   Tachosoft. Section 21.9's sources document that Tachosoft rewrites more
   bytes than it should on Kansei clusters, and a Russian forum thread
   records that as the direct cause of dead gauges on a Kansei Patrol.
3. That write destroyed the configuration outside the odometer field. The
   cluster flipped to the **mile** interpretation and shut down its gauges
   and trip counter.
4. Every subsequent measurement was taken on a mile-configured, damaged
   baseline. The cell weights of sections 9 to 11 and the 33.36053 constant
   were all fitted to that state, which is why they described it accurately
   and predicted nothing about a healthy cluster.
5. Six sessions of checksum and second-field theories followed, all of them
   explaining a fault that was a wrecked configuration.

### 25.4 The near miss

`probes/t04-mattydr67-base-300100-v3.bin` was written, verified, and about to
be delivered as the finished answer at 300,093. That configuration is in
miles. It would have set the odometer to 300,093 **miles**, which is 482,953
km, wrong by 183,000 km, on a vehicle whose true distance is 300,100 km.

It was avoided only because the owner pressed for trip A and B, which moved
the work onto the MOUTRO configuration, and that configuration is in
kilometres.

The lesson for this repository: **a reading is not a number, it is a number
and a unit, and on this hardware the unit is a property of the EEPROM image
being read.** Any future correction must establish which configuration the
image carries before trusting any value computed from it.

## 26. Confirmed in the vehicle (2026-09-19)

The cluster was refitted to the truck with
`probes/FINAL-moutro-300100.bin` and reported working as intended.

This is the only test that exercises the parts a bench cannot: the fuel and
temperature senders are connected, the engine is running so the tachometer
has a real signal, and the vehicle speed sensor drives the speedometer and
the odometer. Every gauge fault this project chased was observed in the
vehicle originally, so the vehicle is where the fix has to be confirmed.

Delivered and confirmed:

- odometer 300,110 km against a true 300,100
- tachometer, fuel and temperature gauges working
- trip A and trip B
- sha256 beginning `6d123e6f`

Still open, and the only item left: drive a known distance of twenty
kilometres or more against GPS and confirm the odometer advances by the same
amount. That tests the calibration rather than the unit, and nothing done so
far constrains it.

### 26.1 Two explanations of the root cause that the evidence refuted

Recorded because both were stated with more confidence than they deserved,
and because section 6 exists for exactly this.

**"The first write clobbered bytes outside the odometer field."** Refuted.
Diffing `dumps/dump.bin`, the 2026-08-23 11:45 read, against
`dumps/patched-300100.bin`, the 13:29 first write, shows **six bytes changed
and all six are the odometer field**. Words 53, 54 and 55, nothing else. The
Tachosoft-overwrites-too-much finding from the forums is real in general and
did not happen here.

**"Desoldering heat erased the configuration."** Refuted. This project's own
first read holds 71 blank words and `MOUTRO`'s image, which drives the
cluster correctly, also holds 71. Our image is not missing data relative to
one that works. The 58 differing populated words carry different values, not
absent ones.

### 26.2 What the evidence does support

The chip content that read 212,562 on 2026-08-23 is byte-identical to the
content that read 764,857 on 2026-09-07 and again on 2026-09-18. No write
between them touched anything but the odometer field. Yet a different image,
`MOUTRO`'s, produces kilometre readings on the same cluster where
`mattydr67`'s produces mile readings.

Content constant with the reading changed means the unit rule is not carried
by our image. An image changing the unit means an image can set it. Both
together mean **the cluster holds the unit and calibration state itself, and
some images rewrite it.** Section 19.6's elimination, withdrawn in 20.1, is
supported again on this evidence, with the addition that the state is
writable from the EEPROM rather than sealed inside the MCU.

The most likely trigger remains the one named in 19.6: the cluster being
powered with no EEPROM fitted, which happened repeatedly and early.

**Untested, one write and one reading:** write `predonor` now, after
`MOUTRO`'s image has been in the cluster. If the unit state is cluster-held
and was set to kilometres by that image, those same bytes should read about
212,575 rather than the 764,857 they have always shown. A third reading of
one unchanged byte string, differing from both previous ones, would settle
the mechanism outright. The vehicle is assembled, so this costs a strip-down
and is recorded for whenever the cluster is next out.

## 27. Prior art check before publication (2026-09-19)

Searched for any existing public description of this encoding, across code
hosts and the general web, in addition to the forum sweeps of sections 15.1,
16.4, 17.1 and 18.4.

**No public description exists.** No repository, byte map, specification or
algorithm for Kansei odometer storage was found in any language. The nearest
Nissan repositories on GitHub are `RiLights/Nissan_skyline_eng_lcd`, which
changes the display language on a 93C66 Skyline cluster, and
`balrog-kun/nissan-qashqai-can-info`, which decodes CAN frames. Neither
concerns this format.

**All existing capability is proprietary.** Tachosoft, SoftDump's UPA-USB
Kansei scripts, iProg, STool, CarProTool and Digiprog all claim coverage and
none documents the format. Two of them were tested directly against this
cluster during this project and were wrong: Tachosoft on three separate
occasions (13.4, 23.3), and its Kansei byte range is reported by other
owners to destroy gauge configuration (21.9 sources).

**The most complete public discussion remains pcmhacking thread 6558**,
which ends with its author accepting "within a few km" and never obtaining
the algorithm.

**Publication in this genre is established.** `gmenounos/vwcluster`
documents Volkswagen cluster checksums openly and
`gerchanovsky/m35080_odometer_fix` publishes an Arduino tool for the BMW
M35080 odometer EEPROM. Comparable work for other manufacturers is public
and uncontroversial.

**One near-miss, recorded so it is not mistaken for prior art.** A Toyota
cluster is documented as storing its odometer three times in inverted hex.
That is whole-value triplication for redundancy. It is not the same
mechanism as a five-bit number whose individual bits are each stored as a
three-bit cell and resolved by majority vote, and it does not overlap with
section 24.
