# Nissan Navara D22 (1999) - odometer correction

**2026-09-19: CONFIRMED IN THE VEHICLE.** The cluster was refitted to the truck
and works as intended, with the senders connected and the engine running. That
is the validation a bench cannot provide.

**2026-09-18: COMPLETE.** `probes/FINAL-moutro-300100.bin` reads **300,110 km**
with the tachometer, fuel and temperature gauges working and **trip A and
trip B** both present, verified on the cluster.

The encoding is solved and is **binary**, not the magnitude scheme sections
1 to 21 describe. Each word is a 5-bit number whose bits are stored as
three-bit cells read by majority vote, with C1 carrying the value 4 rather
than being inert. See ANALYSIS.md section 24 and `work/kansei_binary.py`.

**Root cause, finally (ANALYSIS.md 25):** the EEPROM stores the cluster's
unit setting. The first write on 2026-08-23, a Tachosoft-derived patch, wrote
outside the odometer field and flipped the cluster from kilometres to miles,
which is what killed the gauges. The two configurations' scales differ by
1.60930 against 1.609344 km per mile. The 33.36053 constant this project
called "solved" was the MILE step all along. The same original bytes read
212,562 under the kilometre configuration and 764,857 under the mile one,
which explains the contradiction section 19 could not.

The original fault was never a checksum. The August image contained
malformed words and the firmware rejected it. Everything after that was
tested against a damaged baseline, so nothing learned from it was
informative.


**2026-09-18: the fault is solved in principle. See ANALYSIS.md section 21.**

The EEPROM carries the cluster's **configuration** as well as the reading.
Our own image has lost part of that configuration, which is why the cluster
ran with no gauges and no trip counter. Writing another owner's genuine
dump restores the tachometer, fuel and temperature gauges and the trip
button completely, and **changing the odometer field does not disturb that
working state**. The checksum theory behind sections 13 to 18 is withdrawn:
every image tested before 2026-09-18 was built on our own damaged baseline,
so every result was uninformative.

In the working image's configuration the display rule is measured exactly as

    km = V * 33.36053 + 93,157.5

confirmed on two independent readings. One caveat found the hard way: the
cell pattern `0x0490` reads as 0 units on this cluster rather than 6, so
fields must be generated from whole cells (ANALYSIS 21.5).

**2026-08-25: cluster reads 300,078 km, predicted to the kilometre.**

True vehicle distance is 300,100 km; the written value is **22 km under**,
which is less than one 33.4 km display quantum. The cluster was a
donor unit whose own mileage (212,562 km) was never this truck's, so this is a
cluster-swap correction to the vehicle's documented distance.

Final bytes at 0x6A: `00 9e 3e 8e 06 80`  (`dumps/near-300078.bin`)

    w0 = 0x009E =  3   (1 bit of C4 = 2, plus C5 = 1)
    w1 = 0x3E8E = 25   ->   32 * 25 =   800
    w2 = 0x0680 =  8   -> 1024 *  8 = 8192
                              V = 8995  ->  300,078 km

Per-bit weights are confirmed: a cell's value divides evenly across its three
bits, so C3 gives 4 per bit and C4 gives 2 per bit.

## The encoding, fully solved

Each 16-bit word is five 3-bit cells plus an always-set marker:

    C1 = 0xC001 (wraps the word: bits 15,14 and bit 0)   carries no value
    C2 = 0x3800   16 units      C3 = 0x0700   12 units
    C4 = 0x0070    6 units      C5 = 0x000E    1 unit
    marker = 0x0080

    V  = value(w0) + 32*value(w1) + 1024*value(w2)
    km = round(V * 33.36053)  mod 1,000,000

**Cells may be partially set and carry proportional value** - two of C3's three
bits give 8 units. This is what supplies the values the whole-cell table cannot
reach, and it is the piece that took longest to find. See ANALYSIS.md.

## Remaining

- **Do not refit the cluster yet.** The bench chip's content is unknown
  until read: ANALYSIS.md 14.7 says `dumps/mirror-test.bin`, 16.5 says
  `alimmo` attempt3 was written after that. Before any refit, write
  `dumps/near-300078.bin` and verify the hash matches `b10fcf9b...`.
- **2026-09-16 (ANALYSIS.md 18): the `0x70-0x8d` blanking in 13.2 replays
  a pattern that first appeared in `dumps/trip-erased.bin` on 08-26, after
  the corrected chip had been in the truck, and whose origin (a read of the
  chip, or a constructed test image) was never recorded.** `posttrip`
  (09-01) is a copy of that file written back to the chip, so there is one
  candidate event, unconfirmed. If it was a read, the firmware writes to
  the EEPROM in fault mode and firmware-written images are obtainable on
  the bench, which is the ground truth this project has been missing;
  runbook steps 1-2 test that without needing the answer. A generalised checksum sweep
  (`work/cksweep.py`, 13,248 combinations, result searched anywhere in the
  image, decoded-cell views included) found nothing. **Next bench session:
  follow the runbook in ANALYSIS.md 18.6** (firmware-write probes on
  `predonor` and `near-300078`, the virgin-mode probes `u07`-`u09`, then a
  VSS drive on `predonor` through meter terminals 22/23 with
  `work/ch341_pulse`). Cheap external test: the ETP LAB "Datsun 1999 93c56
  KG-VJ216" dump (10 USD) is the same VJ2xx part family as this board.
- **Trip counter does not respond, and the fuel/temp needles sit at rest
  rather than tracking live senders, whenever any chip content other than
  the untouched original bytes is present.** This is a firmware-side fault
  on the cluster's own MCU rather than an EEPROM encoding problem,
  established in ANALYSIS.md sections 13-14. A second odometer-related
  field at `0x00-0x05` was found this session (14.3). **Confirmed this
  session: `0x00-0x05` alone gates the fault, down to a single flipped
  bit** (15.4, 15.7) - the gate is a real bit-sensitive checksum/validity
  compare, not a redundant counter or a coarse decoded-value check. A
  124-way sweep of standard named CRC-8/CRC-16 algorithms over four
  candidate regions found no match on any of the five real samples this
  project has (15.8), and simple sum/xor forms were already ruled out
  (15.5). The VSS-pulse diagnostic (`work/ch341_pulse`) would give ground
  truth instead of another guess, but needs a 1k resistor and VSS wiring
  not on hand this session. **Recommended next steps, neither tried yet:**
  check whether a commercial Kansei-aware mileage tool (CarProTool -
  already confirmed able to read this exact chip - Digiprog3, OBDStar,
  etc.) already computes this checksum correctly, or accept the tradeoff
  and refit with the odometer correct but trip/gauge-tracking broken. See
  ANALYSIS.md 15.9.
- A second, independent real unit's correction thread (`alimmo`/`brend`,
  Digital Kaos, 2018 - four dumps saved to
  `reference/community-93c56-93c46-dumps/dk-93c56-alimmo-*.bin`) reproduces
  this project's own "wider region gates validity" finding on different
  hardware, and includes an actual observed **999,999 fault** - the first
  directly-confirmed instance of that fault mode this project has. Notably,
  a **zeroed** wide region around that unit's field was tolerated (wrong
  number, no fault); this project's own wider-region test (13.2) only ever
  tried `0xFF`-blanking, which always faulted. See ANALYSIS.md 16 for the
  detail and the zero-vs-FF probe this motivates on our own chip.
- **Roadmap for restoring trip/gauges without reverting the mileage** (2026-09-11,
  ANALYSIS.md 17): in priority order, (1) source a second, unmodified
  Kansei 93c56 Navara/Frontier cluster already close to the target km -
  passes its own checksum by construction, no reverse engineering needed;
  (2) check whether Nissan CONSULT (or a clone) has a documented
  cluster-swap odometer-initialization function for this generation; (3)
  check whether any commercial Kansei-aware tool (CarProTool, Digiprog3,
  OBDStar, etc.) lists this exact board for *writing*, not just reading;
  (4) `probes/u06-1bit-primary-field.bin` - not yet run, CH341
  disconnected - tests whether the primary field has any single-bit
  tolerance the way `0x00-0x05` was shown not to (15.7). Also pending:
  `alimmo`'s attempt3 dump was written and verified on our chip but the
  physical reading was never reported (16.5).
- `dumps/navara-93c56-VERIFIED.bin`, `predonor-*`, and `postrestore-*` are
  all the same untouched original bytes. They were carried in this repo as
  "212,562 km, the donor's original reading" since 2026-08-23; that label
  is wrong (ANALYSIS.md 13.1). The correct decode is ~764,858 km, confirmed
  against the physical cluster 2026-09-07. The files themselves are still
  useful as the one confirmed-working baseline.
- Refit the cluster to the vehicle.
- The chip sits in a DIP-8 socket now, so any future change needs no soldering.

## Historical detail

## Hardware

**The cluster is NOT original to this vehicle** - it was swapped in previously by
the owner's uncle. This reframes everything:

- The 212,562 km found on it was the **donor vehicle's** mileage, never this
  truck's. There is no million-km rollover ambiguity; 300,100 km is the correct
  target, taken from this vehicle's own records.
- The cluster need not be a 1999 Navara unit at all, which is why Tachosoft's
  "Nissan Navara - 93c56 - 1999" entry produces values this cluster does not
  agree with. We were looking up the wrong vehicle.
- Board date codes point to a **2001-2002** unit: MCU `K29451VB200` coded
  `0114KA11` (week 14, 2001) and silkscreen `K29441VB200 0208` (week 8, 2002),
  two to three years newer than the truck.

Identifying the donor is now the shortest path to the right algorithm. The
cluster housing should carry a Nissan part number sticker (typically 24810-...).
Failing that, Tachosoft can be used as an oracle: ask each candidate entry for
212562 km and look for `FE078007F1F8`, which is what this chip actually held at
that reading.

Cluster reads **212,562 km** (exact, read off the bench-powered LCD 2026-08-23), true distance is **300,100 km**. Correcting the
value *upward* to match reality (cluster swap / corrupted EEPROM case).


- EEPROM: **93C56EN**, DIP-8, pulled from the instrument cluster board.
  Microwire (3-wire), **not I2C** - 2Kbit, 128 words x 16 bit = 256 bytes.
  Logo looks like Fairchild (pin 6 = NC) rather than ST (pin 6 = ORG).
  A plain 93C56 (no `L`) is a **4.5–5.5V** part: reads may work at 3.3V,
  **writes will not** - the charge pump browns out and corrupts silently.
- Cluster has a **digital LCD** odometer, so the value really is in this chip.

## Status: ODOMETER FIELD CONFIRMED AT 0x6A - calibration factor found

**2026-08-23: wrote 6 bytes at 0x6A and the display changed 212,562 -> 428,816 km.**
That proves 0x6A IS the odometer field and that the write path works end to end.

Two measurements from this cluster, same offset:

| bytes at 0x6A (chip order) | cluster displays |
|---|---|
| `07 fe 07 80 f8 f1` | 212,562 km  (original) |
| `f8 f1 f8 8f c7 81` | 428,816 km  (Tachosoft's answer for "300,100") |

Tachosoft's Navara 93c56 entry uses a different distance constant from this
cluster: 428816 / 300100 = **1.428910** (= 10/7 to within 0.024%), most likely
a tyre-size or final-drive difference between the 2.4 petrol it assumes and
this 2.5D. So Tachosoft's byte strings are correct in FORM but need the input
scaling: to make this cluster read X, ask Tachosoft for X / 1.428910.

To reach 300,100 km -> ask Tachosoft for **210,020 km**.
Pending falsifiable check: Tachosoft for 148,758 km should output
`FE078007F1F8`, which is the original 212,562 reading. If it does, the
multiplicative model holds.

Note the raw cell decode does NOT track the display monotonically here
(N=22585 for 212,562 but N=5590 for 428,816), so the km mapping for this
variant is still not solved from first principles. The calibration above is
empirical and sufficient for the job.


### Cluster calibration log (empirical, this cluster only)

Tachosoft's codec is confirmed exactly: three samples, one scale, spread 0.007 km.
`N = 3959 -> 212,562` / `5590 -> 300,100` / `2771 -> 148,758`, scale **53.6866**,
cells `(2,1,0,4,3)`, rev=1, words `(0,1,2)`, chip bytes = Tachosoft display order
pairwise-swapped. That part is settled.

This cluster does NOT use Tachosoft's constant. Measured points:

| N | bytes at 0x6A (chip order) | Tachosoft says | this cluster displays |
|---|---|---|---|
| 22585 | `07 fe 07 80 f8 f1` | 1,212,510 (out of range) | 212,562 |
| 5590  | `f8 f1 f8 8f c7 81` | 300,100 | 428,816 |
| 2771  | `3f f0 f8 f1 38 80` | 148,758 | 571,065 |

### Board repair (2026-08-23)
Two pads and one trace tore off during the third chip removal; the cluster then
displayed 999,999 km, which on these Kansei units means the MCU cannot read the
EEPROM, not that data is lost. The chip read back byte-identical to
`probe-N2771.bin` throughout, confirming the fault was purely the board.

After bridging the pads the cluster displays **571,065 km**, exactly matching
the N=2771 image on the chip. The repair is therefore verified against a known
value. Supply draw 12.20 V / 33 mA.

**The chip currently holds a calibration probe (571,065 km), which is wrong and
must be rewritten.** Fit a DIP-8 socket at IC2 during the next removal.

### SOLVED: this cluster's mapping

Three measurements settle it. The display rises as the stored value FALLS,
which is why every forward decode failed:

    km = -20.5322 * N + 630618.2

with word order `(1,0,2)`, cell order `(0,1,4,2,3)`, rev=1. Max residual over
all three points is **50 km**, inside one 53.7 km quantum:

| N | predicted | measured | error |
|---|---|---|---|
| 20360 | 212,582 | 212,562 | +20 |
|  9831 | 428,766 | 428,816 | -50 |
|  2899 | 571,095 | 571,065 | +30 |

Note this is a DIFFERENT bit ordering from Tachosoft's (`(0,1,2)` /
`(2,1,0,4,3)` / rev=1, scale +53.6866). Both orderings are self-consistent on
their own data, so Tachosoft's entry describes a related but distinct variant.
This model is empirical, fitted to this cluster only.

Target: 300,100 km -> **N = 16098** -> bytes `f8 ff 38 80 ff 8f` at 0x6A
(`dumps/target-300100-v2.bin`). N=16098 lies between two measured points, so
this is interpolation, not extrapolation.

A two-point fit does not close: the same codec implies 9.41 km/unit from the
first point and 76.71 from the second. Hence the third probe.

Hypothesis worth noting: 22585 - 18626 = 3959 exactly, and 18626 * 53.6866 is
about 1,000,000. If the display rolls over at 1,000,000 km, the original
212,562 reading is a rolled-over 1,212,562 - which would change the target.

## Superseded: cluster runs on the bench - odometer read 212,562 km

## 93C56 READ SUCCESSFULLY - but the odometer is NOT in it

Read 2026-08-23 over the CH341A. Verified two ways: our `work/ch341_93cxx` and
IMSProg (independent implementation, GPIO bit-bang transport) produced
**byte-identical** contents, differing only in word byte order. The dump is
trustworthy: `dumps/navara-93c56-VERIFIED.bin`.

### ALGORITHM RECOVERED (2026-08-23) - see `work/kansei_odo.py`
Each 16-bit word is **five 3-bit cells + one always-set marker bit**:
C1=0xC001 (wraps: bits 15,14 and bit 0), C2=0x3800, C3=0x0700, C4=0x0070,
C5=0x000E, marker=0x0080. Masks sum to 0xFFFF exactly. Verified on 30/30
words across two independent clusters and on 128/128 words of our own dump.

Three consecutive words = 15 cell-bits = the odometer. Cell order (2,1,0,4,3),
bits read LSB-first, **km = N * 53.687**.

Scale solved from pman92's pcmhacking reference dumps (201149 km, and the
360082/318704 pair); residuals 64 km and 41 km, both inside one step.
Independently corroborated by UPA-USB documenting "54 km accuracy".

Encoder verified: 300,100 km -> N=5590 -> words `f8f1 f88f c781` (+10 km).

**Exact reading is 212,562 km** (confirmed on the bench-powered cluster).
No window decodes to it: not at scale 53.687 in 3 words, and no exact match
at 1 km/unit across 3, 4 or 5 consecutive words with any cell order or bit
direction. So this variant's field layout differs from pman92's 93C46. pman92's cluster was a 1997 2.4L petrol with a 93C46;
ours is a 1999 2.5D with a 93C56, so the scale may differ for this variant.
Candidates in a plausible range (offsets into the verified dump):
0x006=250,074 | 0x00a=242,450 | 0x012=373,608 | 0x018=347,623 |
0x01c=299,251 | 0x01e=394,170 | 0x02a=254,262 | 0x036=317,505 km.
**Need the EXACT dash reading to pick one. Do not write before that.**

### Earlier structural work (all still valid)
The mileage IS in this chip, stored as a **distributed thermometer/bit-count
counter**, not as an integer. That is why every integer search failed.

- Every one of the 128 words has popcount == 1 (mod 3). Only six states occur:
  1, 4, 7, 10, 13, 16 bits set -> levels 0..5. Each increment clears/sets
  **3 bits**, which is what produces the runs-of-3 bit patterns.
- 223/256 bytes are valid 8-bit thermometer codes; 90/128 words are valid
  16-bit thermometer codes.
- Words 0..70 are in use; words 71..127 are untouched 0xffff.
- Current totals: sum of levels = 455, set bits = 1493, cleared bits = 555.
- Corroboration: UPA-USB's "KANSEI 93xx" script is documented as using a
  "not very simple" algorithm with **54 km accuracy**, consistent with a
  bit-count counter rather than a stored integer.

Still needed: the exact Kansei level->km mapping. Do NOT fit a constant to a
single approximate reading; with one free parameter anything fits. Get the
EXACT dash reading first.

Earlier (superseded) negative results, still valid as evidence it is not a
plain integer:
- No encoding of 216000-218000 km matches, in either byte order, at any of the
  25 bit alignments swept from the raw Microwire frames.
- There is **no wear-levelled record structure at all** - no repeating
  multi-byte pattern at a regular stride. Nissan duplicates the odometer
  record; its complete absence is the strongest evidence.
- 149 of 256 bytes are 0xFF and only 15 distinct byte values appear. This
  reads like configuration/calibration data, not an odometer store.

**Next step: find the other memory device on the cluster board.** Candidates
are a second 8-pin serial EEPROM (93Cxx/24Cxx) or the cluster MCU's internal
EEPROM. Photograph the board and identify every IC before pulling anything.

## Superseded: CH341A bring-up
Reading over the CH341A was abandoned. Last known state, established from the
chip's own behaviour rather than assumption:

| Signal | Verified |
|---|---|
| VCC, GND | OK - chip actively drives a pin |
| CS  (pin 1 → socket 1) | OK, **active high**, non-inverted |
| DO  (pin 4 → socket 2) | OK - drives low when selected |
| SK  (pin 2 → socket 6) | **not working** |
| DI  (pin 3 → socket 5) | **not working** |

Then two pins snapped and were repaired by soldering on donor legs. The repair
is **unverified** - `diag` has not been run since.

## Tools built here
- `work/ch341_93cxx` - Microwire over CH341A (libusb). Bit-bangs active-high CS
  via the UIO stream since the CH341's SPI engine drives CS active-low.
  Subcommands: `pinwalk`, `diag`, `dump`, `write ... --yes-really-write`.
- `work/mw93c56/mw93c56.ino` - same protocol on ESP32 (3.3V, read-only) or a
  5V Arduino (read + write). Serial: `d` = diag, `r` = dump.
- `work/capture.py` - turns pasted sketch output into a 256-byte .bin.
- `work/dump3.sh` - reads 3x, refuses unless all three are byte-identical.
- `work/findodo.py` - brute-forces every plausible encoding of a displayed
  mileage. Self-tested. Accepts an exact value or a range (`216500-217500`).

## T76 toolchain (installed, Linux-only, no Windows)
`minipro` 0.7.4 built from source at `tools/minipro`, installed to `~/.local`.
Upstream calls T76 support **experimental** - worth knowing before trusting it.

- `~/.local/bin/minipro` - binary
- `~/.local/share/minipro/` - infoic.xml, logicic.xml, algorithm.xml
- `algorithm.xml` (49MB) was generated by `tools/minipro/dump-alg-minipro.bash`,
  which downloads the vendor Xgpro archives (SHA256-verified) and extracts the
  FPGA bitstreams. The T76 is FPGA-based and does **not** hold its own
  bitstreams, so this file is required, not optional.
- Part name: **`FM93C56`** (or generic `93C56(x16)`) - both report 128 words,
  DIP8, algorithm MW93ALG21.

### One-time, needs root - DONE 2026-08-19 (rule installed, syntax verified)
```
sudo install -m644 work/60-minipro.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger
```
(The shipped rule uses Debian's `plugdev`; `work/60-minipro.rules` is the
adapted copy using `users` + `uaccess`.)

### Runbook
```
minipro -k                              # programmer detected?
minipro -p 'FM93C56' -z                 # pin contact check
work/dump3-t76.sh FM93C56 navara        # 3 reads, must be identical
python3 work/findodo.py dumps/navara-*-GOOD.bin 216500-217500
# ... build patched.bin only after the record and its checksum are confirmed
minipro -p 'FM93C56' -w dumps/patched.bin
minipro -p 'FM93C56' -m dumps/patched.bin   # verify
```
93Cxx parts have no device ID, so use `-x` to skip the ID read (dump3-t76.sh
already does).

## Open questions
- Exact current reading (we only have "~217000"; `findodo.py` range mode covers
  this, but an exact number cuts false positives sharply).
- Whether the D22's ECU/BCM also mirrors the mileage. If it does and the copies
  disagree after the write, the dash can flag an inconsistency - worth reading
  with a scan tool before refitting.
