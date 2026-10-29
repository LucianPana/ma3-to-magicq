#!/usr/bin/env python3
"""Compare what grandMA3 outputs per cue with the cue values of the source MagicQ show.

usage: ma3_compare.py PACKAGE_DIR SHOW.shw [--timeout S]

Asks onPC (OSC or web remote, like ma3_import.py) to run every cue of every imported
sequence with zero fade and read back the DMX of all patched channels, then compares
with the values the MagicQ .shw stores for that cue. Channels a cue does not set are
not compared (MagicQ cues are deltas; tracking and defaults fill the rest).
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import ma3_import                      # noqa: E402
from magicq.reader import read_shw     # noqa: E402

SNAP_LUA = """
return function(dir)
  local function wait(s) local t0 = os.clock() while os.clock() - t0 < s do end end
  local f = io.open(dir .. "/snapshot.json", "w")
  f:write("{")
  local first = true
  local spec = dofile(dir .. "/snapshot_spec.lua")
  for _, seq in ipairs(spec.sequences) do
    for _, cue in ipairs(seq.cues) do
      Cmd(string.format("Goto Sequence %d Cue %s Fade 0", seq.no, cue))
      wait(0.6)
      local vals = {}
      for _, a in ipairs(spec.channels) do vals[#vals + 1] = tostring(GetDMXValue(a) or -1) end
      if not first then f:write(",") end
      first = false
      f:write(string.format('"%d/%s":[%s]', seq.no, cue, table.concat(vals, ",")))
      f:flush()
    end
    Cmd(string.format("Off Sequence %d", seq.no))
    wait(0.3)
  end
  f:write("}")
  f:close()
end
"""


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        return 2
    pkg, shw = os.path.abspath(args[0]), args[1]
    timeout = float(argv[argv.index("--timeout") + 1]) if "--timeout" in argv else 900.0
    show = read_shw(shw)
    with open(os.path.join(pkg, "show.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    shift = 512 * int(data.get("universe_offset", 0))   # the package may be patched a universe higher
    channels = sorted({f.abs_chan + off + shift for f in show.fixtures for off in range(f.head.nchans)})
    seqs = [{"no": s["no"], "cues": [f"{c['no']:g}" for c in s["cues"]]} for s in data["sequences"]]
    with open(os.path.join(pkg, "snapshot_spec.lua"), "w") as fh:
        fh.write("return {channels={" + ",".join(str(c) for c in channels) + "},sequences={" +
                 ",".join("{no=%d,cues={%s}}" % (s["no"], ",".join('"%s"' % c for c in s["cues"])) for s in seqs) + "}}\n")
    lua = os.path.join(pkg, "snapshot.lua")
    with open(lua, "w") as fh:
        fh.write(SNAP_LUA)
    snap = os.path.join(pkg, "snapshot.json")
    if os.path.exists(snap):
        os.remove(snap)
    transport = ma3_import.connect()
    if transport is None:
        print("onPC not reachable")
        return 3
    ma3_import.send([f"Lua \"dofile('{lua}')('{pkg}')\""], transport)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(snap):
            try:
                with open(snap, encoding="utf-8") as fh:
                    got = json.load(fh)
                break
            except json.JSONDecodeError:
                pass
        time.sleep(0.5)
    else:
        print("timed out waiting for the snapshot")
        return 3
    idx = {c: i for i, c in enumerate(channels)}
    total = ok = 0
    bad = []
    for si, stack in enumerate(show.stacks, start=1):
        for cue in stack.cues:
            key = f"{si}/{cue.number:g}"
            row = got.get(key)
            if row is None:
                bad.append((key, "no snapshot"))
                continue
            for (fid, off), v in cue.values.items():
                ch = show.fixture(fid).abs_chan + off + shift
                total += 1
                g = row[idx[ch]]
                if g == v:
                    ok += 1
                else:
                    bad.append((key, f"chan {ch - shift} ({show.fixture(fid).name} +{off}) MagicQ {v} grandMA3 {g}"))
    print(f"{ok} of {total} cue values match")
    for b in bad[:40]:
        print("  ", b[0], b[1])
    if len(bad) > 40:
        print(f"   ... {len(bad) - 40} more")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
