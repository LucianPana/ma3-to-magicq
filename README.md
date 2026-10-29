# ma3-to-magicq

Converts a grandMA3 show into a native ChamSys MagicQ show file (`.shw`) that a MagicQ console or MagicQ PC opens directly. Patch, groups, palettes, cue stacks with values and times, pages and playbacks come across. Effects, recipes, phasers, macros and layouts do not (see `docs/shw-format.md` and the conversion report).

Nothing like this exists from either vendor: MagicQ only imports MVR patches and USITT dimmer cues, and the `.shw` format is undocumented. The format notes in `docs/shw-format.md` were reverse-engineered from sample shows and confirmed by writing records by hand and letting MagicQ PC load and rewrite them.

## Workflow

1. **Dump the show in grandMA3 onPC** (2.x, this Mac has 2.3.2). Load the show, then in the command line type

       Lua "dofile('/Users/lucianpana/Personal/ma3-to-magicq/ma3/dump_show.lua')()"

   or import `ma3/dump_show.lua` into the Plugin pool and run it. It writes `~/ma3dump/` (`dump.json`, `fixturetypes/*.xml`, the XML exports). It plays every cue once with zero fade to read the DMX output, switches all sequences off at the end and changes nothing in the show. Do not save the show afterwards if you want to be sure.

2. **Convert**

       python3 convert.py ~/ma3dump out/myshow.shw

   writes the show and `out/myshow-report.md` with everything that was approximated or dropped.

3. **Load on MagicQ**: copy the `.shw` into the console's show folder (or `~/Documents/MagicQ/show` for MagicQ PC) and Setup > Load Show. Read the report, check one cue's times, the heads' attribute wheels, and the playback layout.

## How it works

- `ma3/dump_show.lua` reads the patch, groups (through the selection), presets and cues (through DMX snapshots: the MA3 output is what the cue really does, with tracking, presets and recipes resolved) and exports the fixture types as XML.
- `ma3/fixturetypes.py` turns a grandMA3 fixture type XML or a GDTF into a MagicQ head: channel kinds, attribute numbers (`data/gdtf_to_magicq.csv`), defaults and named ranges. Attributes MagicQ cannot hold twice in one head go to spare attribute numbers; pixel cells beyond the first are patched as placeholders.
- `ma3/reader.py` builds the console-neutral `model`, `magicq/writer.py` emits the `.shw` on top of a template MagicQ PC 1.9.7.4 wrote itself (`templates/empty-1.9.7.4.shw`).
- `scripts/mq_roundtrip.py` loads a file into MagicQ PC without touching its GUI (MagicQ loads the show named in `status.dat` at start and writes it back as `.sbk`) and returns MagicQ's rewrite; `scripts/demo_show.py` and `scripts/fake_dump.py` build synthetic shows for it.

## Status (2026-10-29)

Verified with MagicQ PC 1.9.7.4 on this Mac: generated shows with generated heads (1 and 52 channels), patch on two universes, groups, the four palette kinds, cues with values and millisecond fade and delay times, multi-cue stacks, a page and playbacks all load and come back from MagicQ unchanged apart from fields it derives itself.

Not yet run against a real grandMA3 show: `dump_show.lua` is written against the documented Lua API and syntax-checked, but the first real run in onPC will show which property names differ. Driving onPC from this machine needs the Terminal app granted Accessibility (System Settings > Privacy & Security > Accessibility); without it a person has to start the plugin.

To confirm by eye on MagicQ (not readable from the file): the fade unit on a cue (written as milliseconds, expected to show as seconds), the cue-timing versus chase mode of multi-cue stacks (flag `0000801f`), and the vis entries of generated heads.

## Development

    python3 -m venv .venv && .venv/bin/pip install pytest
    .venv/bin/python -m pytest -q
    python3 scripts/demo_show.py out/demo.shw --roundtrip      # needs MagicQ PC installed

Sample shows (third-party MQ50 shows, ChamSys demos, the grandMA3 demo shows) live in `samples/`, which is not committed.
