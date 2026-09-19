#!/usr/bin/env bash
# Write one probe image and verify it landed. usage: probe.sh p03-w0c2
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
P="${1:?usage: probe.sh <probe-name>   (see probes/)}"
D="$ROOT"
F="$D/probes/$P.bin"
[ -f "$F" ] || { echo "no such probe: $P" >&2; ls "$D/probes" | sed 's/\.bin$//' | column; exit 1; }

# Never write to a chip that is not talking: a failed write leaves the contents
# unknown, and we cannot tell a dead connection from a dead chip afterwards.
if ! "$D/work/ch341_93cxx" diag 2>&1 | grep -q "^verdict: GOOD"; then
	echo "REFUSING: chip is not responding. Fix seating/wiring first." >&2
	"$D/work/ch341_93cxx" diag 2>&1 | tail -3 >&2
	exit 2
fi
"$D/work/ch341_93cxx" write "$F" --yes-really-write >/dev/null 2>&1
"$D/work/ch341_93cxx" dump /tmp/vfy.bin >/dev/null 2>&1
if cmp -s /tmp/vfy.bin "$F"; then
	echo "$P written and verified -> 0x6A = $(python3 -c "print(open('$F','rb').read()[0x6A:0x70].hex(' '))")"
	echo "now power the cluster and read the odometer"
else
	echo "VERIFY FAILED - do not trust this cycle" >&2; exit 1
fi
