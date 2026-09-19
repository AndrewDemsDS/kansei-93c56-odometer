#!/usr/bin/env bash
# Read the 93C56 three times and require all three to be byte-identical.
# A cluster EEPROM read over hand-jumpered wiring WILL give silent garbage;
# never trust a single dump, and never write back from an unverified one.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAG="${1:-nissan}"
TOOL="$ROOT/work/ch341_93cxx"
OUT="$ROOT/dumps"
STAMP=$(date +%Y%m%d-%H%M%S)

# Three identical reads are not enough on their own. A chip that is absent,
# unpowered or fully erased answers with the same uniform image every time, so
# 3/3 agreement is exactly what an empty socket looks like. Screen the image
# for that before blessing it as GOOD. A real dump of this part runs about 58%
# 0xff, so a 95% ceiling leaves plenty of headroom.
#
# A freshly erased chip is a legitimate state that this check rejects. That is
# the intended trade: write first, then verify. See README.md.
sane() {
  local f="$1" sz top
  sz=$(stat -c %s "$f")
  if [ "$sz" -ne 256 ]; then
    echo "REJECTED: $f is $sz bytes, expected 256." >&2
    return 1
  fi
  top=$(xxd -p -c1 "$f" | sort | uniq -c | sort -rn | head -1 | awk '{print $1}')
  if [ "$top" -gt 243 ]; then
    echo "REJECTED: $f is ${top}/256 a single repeated byte value." >&2
    echo "          An absent, unpowered or blank chip reads uniform." >&2
    return 1
  fi
  return 0
}

for i in 1 2 3; do
  echo "--- read $i/3 ---"
  "$TOOL" dump "$OUT/${TAG}-${STAMP}-$i.bin"
done

if cmp -s "$OUT/${TAG}-${STAMP}-1.bin" "$OUT/${TAG}-${STAMP}-2.bin" \
   && cmp -s "$OUT/${TAG}-${STAMP}-2.bin" "$OUT/${TAG}-${STAMP}-3.bin"; then
  if ! sane "$OUT/${TAG}-${STAMP}-1.bin"; then
    echo "3/3 reads agreed, but the image is not real. Do NOT write." >&2
    exit 1
  fi
  cp "$OUT/${TAG}-${STAMP}-1.bin" "$OUT/${TAG}-${STAMP}-GOOD.bin"
  chmod 444 "$OUT/${TAG}-${STAMP}-GOOD.bin"
  echo "OK: 3/3 identical -> ${TAG}-${STAMP}-GOOD.bin (locked read-only)"
  sha256sum "$OUT/${TAG}-${STAMP}-GOOD.bin"
else
  echo "MISMATCH - reads differ. Reseat the wiring and retry. Do NOT write." >&2
  for i in 1 2 3; do sha256sum "$OUT/${TAG}-${STAMP}-$i.bin"; done
  exit 1
fi
