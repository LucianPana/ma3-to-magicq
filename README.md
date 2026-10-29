# ma3-to-magicq

**Open a grandMA3 show on a ChamSys MagicQ.**

You programmed the show on a grandMA3. The venue has a MagicQ. Until now that meant one thing: start again from an empty desk. This tool takes the grandMA3 show and writes a real MagicQ show file (`.shw`) that the console opens like any other show, with the patch, the groups, the palettes and the cue lists already in it.

No manufacturer offers this. Both file formats are undocumented. This project figured out the MagicQ one and uses the grandMA3's own scripting to read the other.

> **Status: experimental.** It works on test shows against MagicQ PC. It has not yet been run on a real-world grandMA3 show, and it will need a few corrections when it is. If you try it, tell us what happened, good or bad.

## What comes across

| From the grandMA3 | On the MagicQ |
|---|---|
| Fixtures, DMX addresses, 3D positions | Patched heads, built from the fixture's GDTF so no library matching is needed |
| Groups | Groups |
| Presets (dimmer, position, colour, gobo, beam, focus) | Intensity, position, colour and beam palettes |
| Sequences and cues, with fade and delay times | Cue stacks and cues with the same values and times |
| Executors and pages | Playbacks and pages |

What does not come across, and is listed for you in a report after every conversion: effects and phasers (the cue keeps a still frame of them), recipes (resolved to plain values), macros, layouts, worlds, timecode triggers (flagged so you can set them by hand).

The result is a show you finish on the MagicQ in an hour, not one you rebuild in a day.

## How to use it

You need: the grandMA3 show (open in grandMA3 onPC, which is free, or on the console), Python 3 on your computer, and a MagicQ or MagicQ PC (also free).

**1. Dump the show on the grandMA3.** Load the show in onPC or on the console. In the command line type:

```
Lua "dofile('<path to this folder>/ma3/dump_show.lua')()"
```

(or import `ma3/dump_show.lua` into the Plugin pool and press it). It writes a folder `ma3dump` in your home directory. It plays each cue once silently to read what the cue really outputs, then switches everything off. It changes nothing in the show.

**2. Convert.** In a terminal, in this folder:

```
python3 convert.py ~/ma3dump myshow.shw
```

You get `myshow.shw` and `myshow-report.md`.

**3. Load on the MagicQ.** Copy `myshow.shw` to the console (USB stick, or `Documents/MagicQ/show` on MagicQ PC), then Setup, Load Show. Open the report next to it and check the things it points out.

## Why trust the file

The MagicQ format was worked out by writing records by hand and having MagicQ PC load them and write them back, over and over, until what came back matched what went in. Patch, groups, palettes, cues, times, stacks and playbacks all survive that round trip. The notes are in `docs/shw-format.md`, which is, as far as we know, the first public description of the MagicQ show file.

## Who this is for

Small venues, rental houses, schools, churches and freelancers who get a grandMA3 file and have a MagicQ in the room, or who are moving from one desk to the other and have a season of shows programmed. If you run a 300-fixture arena tour you will keep programming per console, and you should.

## Help wanted

- Run it on your show and open an issue with the report and what the MagicQ showed. The first real shows will teach the tool the most.
- Attribute mappings for fixture types that come out odd live in `data/gdtf_to_magicq.csv`, one line per attribute, easy to fix.
- The other direction (MagicQ to grandMA3) and other desks are possible on the same core. Say so if you want them.

Technical details, how the pieces fit and how to develop: `docs/development.md`. MIT licence.
