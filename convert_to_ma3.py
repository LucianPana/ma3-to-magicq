#!/usr/bin/env python3
"""MagicQ to grandMA3: turn a MagicQ .shw into a grandMA3 import package.

usage: convert_to_ma3.py SHOW.shw OUT_DIR [--no-library] [--install]

OUT_DIR gets show.json, fixturetypes/*.gdtf and report.md. Then, in grandMA3
onPC with a new empty show:

    Lua "dofile('<this folder>/ma3/import_show.lua')('OUT_DIR')"

--no-library           do not look for grandMA3 library fixture types, always use the generated GDTFs
--install              also copy the GDTF files into ~/MALightingTechnology/gma3_library/fixturetypes
--universe-offset N    patch everything N universes higher (grandMA3 onPC 2.3.2 stops answering
                       GetDMXValue once anything is patched on universe 1, so the DMX comparison
                       in scripts/ma3_compare.py needs the show shifted up by one)
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from magicq.reader import read_shw   # noqa: E402
from ma3 import writer               # noqa: E402

USER_FT = os.path.expanduser("~/MALightingTechnology/gma3_library/fixturetypes")


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        return 2
    shw, out = args[0], args[1]
    show = read_shw(shw)
    offset = int(argv[argv.index("--universe-offset") + 1]) if "--universe-offset" in argv else 0
    data = writer.write_package(show, out, match_library="--no-library" not in argv, universe_offset=offset)
    if "--install" in argv:
        os.makedirs(USER_FT, exist_ok=True)
        for h in data["heads"]:
            shutil.copy(os.path.join(out, "fixturetypes", h["gdtf"]), USER_FT)
        print(f"copied {len(data['heads'])} GDTF files to {USER_FT}")
    print(f"wrote {os.path.join(out, 'show.json')} and report.md")
    print(f"{len(data['fixtures'])} fixtures, {len(data['heads'])} fixture types, {len(data['groups'])} groups, "
          f"{len(data['presets'])} presets, {len(data['sequences'])} sequences, "
          f"{sum(len(s['cues']) for s in data['sequences'])} cues, {len(data['executors'])} executors, {len(data['notes'])} notes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
