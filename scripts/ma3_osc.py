#!/usr/bin/env python3
"""Send grandMA3 command lines over OSC (the /cmd address, one string argument).

usage: ma3_osc.py "Fixture 1 At 50" ["next command" ...]
env:   MA3_OSC_HOST (default 127.0.0.1), MA3_OSC_PORT (default 8000), MA3_OSC_PREFIX (default empty)

onPC must have OSC input enabled: Menu > In & Out > OSC, Enable Input on, and in
the configuration line for port 8000 "Receive Command" set to Yes.
"""
from __future__ import annotations

import os
import socket
import sys
import time


def osc_string(s: str) -> bytes:
    b = s.encode("utf-8") + b"\0"
    return b + b"\0" * (-len(b) % 4)


def osc_message(address: str, *args: str) -> bytes:
    tags = "," + "s" * len(args)
    out = osc_string(address) + osc_string(tags)
    for a in args:
        out += osc_string(a)
    return out


def send(commands: list[str], host: str | None = None, port: int | None = None, prefix: str | None = None, gap: float = 0.02):
    host = host or os.environ.get("MA3_OSC_HOST", "127.0.0.1")
    port = int(port or os.environ.get("MA3_OSC_PORT", "8000"))
    prefix = prefix if prefix is not None else os.environ.get("MA3_OSC_PREFIX", "")
    address = f"/{prefix.strip('/')}/cmd" if prefix else "/cmd"
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for c in commands:
            sock.sendto(osc_message(address, c), (host, port))
            time.sleep(gap)
    finally:
        sock.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    send(sys.argv[1:])
