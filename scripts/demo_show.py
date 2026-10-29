#!/usr/bin/env python3
"""Build a small synthetic show (2 dimmers, 2 generated moving heads, a group,
palettes, a two-cue stack, playbacks), write it and optionally round-trip it
through MagicQ PC.

usage: demo_show.py OUT.shw [--roundtrip]
"""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from model import *
from magicq import writer, shwfile


def dimmer_head():
    return HeadDef("Generic", "Dimmer", "", [Channel("Dimmer", ATTR["Intensity"], "htp8", 0)])


def spot_head():
    ch = [
        Channel("Pan", ATTR["Pan"], "pos16c", 0x80),
        Channel("Pan F", ATTR["Pan"], "pos16f", 0),
        Channel("Tilt", ATTR["Tilt"], "pos16c", 0x80),
        Channel("Tilt F", ATTR["Tilt"], "pos16f", 0),
        Channel("Dimmer", ATTR["Intensity"], "htp8", 0),
        Channel("Shutter", ATTR["Shutter"], "ltp8", 0x20, ranges=[Range(0, 0x1f, "Closed"), Range(0x20, 0xff, "Open")]),
        Channel("Col Wheel", ATTR["Col1"], "ltp8snap", 0, ranges=[Range(0, 9, "White"), Range(10, 19, "Red"), Range(20, 29, "Blue")]),
        Channel("Gobo", ATTR["Gobo1"], "ltp8snap", 0, ranges=[Range(0, 9, "Open"), Range(10, 19, "Gobo 1")]),
        Channel("Focus", ATTR["Focus"], "ltp8", 0x80),
        Channel("Zoom", ATTR["Zoom"], "ltp8", 0x80),
    ]
    return HeadDef("Demo", "Spot", "10ch", ch)


def build():
    dim, spot = dimmer_head(), spot_head()
    show = Show("ma3 demo")
    show.fixtures = [
        Fixture(1, "Dim 1", dim, 1, 1),
        Fixture(2, "Dim 2", dim, 1, 2),
        Fixture(101, "Spot 1", spot, 2, 1, pos=(-1.0, 4.0, 0.0)),
        Fixture(102, "Spot 2", spot, 2, 11, pos=(1.0, 4.0, 0.0)),
    ]
    show.groups = [Group("Dimmers", [1, 2]), Group("Spots", [101, 102])]
    show.palettes = [
        Palette("pos", "Centre", {(101, 0): 0x80, (101, 1): 0, (101, 2): 0x80, (101, 3): 0, (102, 0): 0x80, (102, 1): 0, (102, 2): 0x80, (102, 3): 0}),
        Palette("col", "Red", {(101, 6): 12, (102, 6): 12}, rgb=(1.0, 0.0, 0.0)),
        Palette("beam", "Gobo 1", {(101, 7): 12, (102, 7): 12}),
        Palette("int", "Full", {(1, 0): 255, (2, 0): 255, (101, 4): 255, (102, 4): 255}),
    ]
    cue1 = Cue(1.0, "Look 1", {(1, 0): 0x80, (2, 0): 0xff, (101, 4): 0xff, (101, 0): 0x40, (101, 2): 0xc0, (101, 6): 12}, fade=2.0)
    cue2 = Cue(2.0, "Look 2", {(1, 0): 0, (2, 0): 0x40, (101, 4): 0x80, (102, 4): 0xff, (102, 7): 12}, fade=5.0, delay=1.0)
    show.stacks = [CueStack("Main", [cue1, cue2]), CueStack("Blinder", [Cue(1.0, "Blind", {(1, 0): 255, (2, 0): 255}, fade=0.0)])]
    show.playbacks = [Playback(1, 0, "stack", 0, "Main"), Playback(1, 1, "stack", 1, "Blinder"), Playback(1, 9, "group", 1, "Spots")]
    return show


if __name__ == "__main__":
    out = sys.argv[1]
    show = build()
    writer.write_show(show, out)
    print("wrote", out, os.path.getsize(out), "bytes")
    if "--roundtrip" in sys.argv:
        rt = os.path.splitext(out)[0] + "_rt.shw"
        r = subprocess.run([sys.executable, "scripts/mq_roundtrip.py", out, rt, "--wait", "30"])
        if r.returncode:
            sys.exit(r.returncode)
        a, b = shwfile.load(out), shwfile.load(rt)
        for tag in ("P", "L", "H", "F", "G", "S", "C", "M", "N"):
            print(f"{tag}: wrote {len(a.by_tag(tag))}, got back {len(b.by_tag(tag))}")
