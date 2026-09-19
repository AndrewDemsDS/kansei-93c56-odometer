#!/usr/bin/env python3
"""Capture a dump from the MCU sketch and write a 256-byte .bin.
usage: capture.py /dev/ttyUSB0 out.bin     (paste-from-stdin: capture.py - out.bin)"""
import sys

def parse(text, path):
    if "BEGIN" not in text or "END" not in text:
        sys.exit("no BEGIN/END block found - did the read fail? run 'd' for diagnostics")
    body = text.split("BEGIN", 1)[1].split("END", 1)[0]
    words = [int(t, 16) for t in body.split()]
    if len(words) != 128:
        sys.exit(f"expected 128 words, got {len(words)}")
    data = b"".join(w.to_bytes(2, "big") for w in words)
    open(path, "wb").write(data)
    print(f"wrote {len(data)} bytes to {path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, out = sys.argv[1], sys.argv[2]
    if src == "-":
        parse(sys.stdin.read(), out)
    else:
        import serial          # pyserial
        with serial.Serial(src, 115200, timeout=2) as s:
            s.write(b"r")
            buf = b""
            while b"END" not in buf:
                chunk = s.read(256)
                if not chunk:
                    break
                buf += chunk
            parse(buf.decode(errors="replace"), out)
