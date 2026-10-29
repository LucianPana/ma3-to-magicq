#!/usr/bin/env python3
"""ma3-to-magicq: convert a grandMA3 dump folder (made by ma3/dump_show.lua) into a MagicQ .shw.

usage: convert.py DUMP_DIR OUT.shw [--report REPORT.md]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ma3.reader import read_dump      # noqa: E402
from magicq import writer              # noqa: E402


def write_report(show, path, out_shw):
    lines = [f"# Conversion report: {show.name}", "", f"MagicQ show written to `{out_shw}`.", ""]
    lines += ["## What was converted", ""]
    lines.append(f"- {len(show.fixtures)} fixtures, {len(show.heads())} head types")
    lines.append(f"- {len(show.groups)} groups")
    by = {}
    for p in show.palettes:
        by[p.kind] = by.get(p.kind, 0) + 1
    lines.append("- palettes: " + ", ".join(f"{v} {k}" for k, v in sorted(by.items())) if by else "- no palettes")
    lines.append(f"- {len(show.stacks)} cue stacks with {sum(len(s.cues) for s in show.stacks)} cues")
    lines.append(f"- {len(show.playbacks)} playback assignments")
    lines += ["", "## Check on the console", "",
              "- Cue fade and delay times (MagicQ rounds to 30 ms steps).",
              "- Cue stacks are written in cue timing mode, non-tracking, with the full state of every cue.",
              "- Effects, recipes, phasers, macros and layouts were not converted.",
              "- Heads were generated from the GDTF channel layout: check the attribute wheels for each head type.",
              ""]
    if show.report:
        lines += ["## Notes", ""] + [f"- {n}" for n in show.report] + [""]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        return 2
    dump_dir, out = args[0], args[1]
    report = None
    if "--report" in argv:
        report = argv[argv.index("--report") + 1]
    show = read_dump(dump_dir)
    writer.write_show(show, out)
    rep = report or os.path.splitext(out)[0] + "-report.md"
    write_report(show, rep, out)
    print(f"wrote {out} ({os.path.getsize(out)} bytes) and {rep}")
    print(f"{len(show.fixtures)} fixtures, {len(show.groups)} groups, {len(show.palettes)} palettes, "
          f"{len(show.stacks)} stacks, {len(show.report)} notes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
