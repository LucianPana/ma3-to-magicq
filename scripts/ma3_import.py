#!/usr/bin/env python3
"""Run ma3/import_show.lua inside grandMA3 onPC over OSC and wait for its result.

usage: ma3_import.py PACKAGE_DIR [--timeout S] [--lua PATH]

Sends  Lua "dofile('<repo>/ma3/import_show.lua')('<PACKAGE_DIR>')"  to onPC through
scripts/ma3_osc.py, then polls PACKAGE_DIR/result.json. Exit 0 when the plugin
reports no failed commands, 1 otherwise, 3 when nothing came back in time.
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ma3_osc  # noqa: E402


def ping(timeout: float = 3.0) -> bool:
    """True when onPC executes our OSC commands (it writes a marker file)."""
    marker = os.path.expanduser("~/.ma3_osc_ping")
    if os.path.exists(marker):
        os.remove(marker)
    ma3_osc.send([f"Lua \"local f=io.open('{marker}','w') if f then f:write('ok') f:close() end\""])
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(marker):
            os.remove(marker)
            return True
        time.sleep(0.1)
    return False


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    pkg = os.path.abspath(args[0])
    timeout = float(argv[argv.index("--timeout") + 1]) if "--timeout" in argv else 600.0
    lua = argv[argv.index("--lua") + 1] if "--lua" in argv else os.path.join(os.path.dirname(HERE), "ma3", "import_show.lua")
    result = os.path.join(pkg, "result.json")
    if os.path.exists(result):
        os.remove(result)
    if not ping():
        print("onPC did not answer over OSC. Enable it: Menu > In & Out > OSC, Enable Input, port 8000 line with Receive Command = Yes.")
        return 3
    ma3_osc.send([f"Lua \"dofile('{lua}')('{pkg}')\""])
    t0 = time.time()
    last = ""
    while time.time() - t0 < timeout:
        prog = os.path.join(pkg, "progress.log")
        if os.path.exists(prog):
            with open(prog, encoding="utf-8", errors="replace") as fh:
                txt = fh.read()
            if txt != last:
                sys.stdout.write(txt[len(last):])
                sys.stdout.flush()
                last = txt
        if os.path.exists(result):
            time.sleep(0.3)
            with open(result, encoding="utf-8") as fh:
                data = json.load(fh)
            failed = data.get("failed", [])
            print(f"\nimport finished in {data.get('seconds', '?')} s: {data.get('counts')}")
            if failed:
                print(f"{len(failed)} failed commands, first ones:")
                for f in failed[:15]:
                    print("  ", f)
            return 1 if failed else 0
        time.sleep(0.5)
    print("timed out waiting for result.json")
    return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
