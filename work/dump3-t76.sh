#!/usr/bin/env bash
# Read the 93C56 three times via minipro/T76; require all three identical.
# 93Cxx parts carry no device ID, so -x skips the ID read.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PART="${1:-FM93C56}"
TAG="${2:-navara}"
OUT="$ROOT/dumps"
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$OUT"

for i in 1 2 3; do
  echo "--- read $i/3 ($PART) ---"
  minipro -p "$PART" -x -r "$OUT/${TAG}-${STAMP}-$i.bin"
done

if cmp -s "$OUT/${TAG}-${STAMP}-1.bin" "$OUT/${TAG}-${STAMP}-2.bin" \
   && cmp -s "$OUT/${TAG}-${STAMP}-2.bin" "$OUT/${TAG}-${STAMP}-3.bin"; then
  cp "$OUT/${TAG}-${STAMP}-1.bin" "$OUT/${TAG}-${STAMP}-GOOD.bin"
  chmod 444 "$OUT/${TAG}-${STAMP}-GOOD.bin"
  echo "OK: 3/3 identical -> ${TAG}-${STAMP}-GOOD.bin (locked read-only)"
  sha256sum "$OUT/${TAG}-${STAMP}-GOOD.bin"
  python3 -c "
import sys,collections
d=open('$OUT/${TAG}-${STAMP}-GOOD.bin','rb').read()
c=collections.Counter(d)
print(f'size {len(d)} bytes, {len(c)} distinct values')
sys.exit(0 if len(c)>2 else 1)" || echo "WARNING: near-uniform image - suspect a bad read, not real data"
else
  echo "MISMATCH - reads differ. Reseat the chip and retry. Do NOT write." >&2
  exit 1
fi
