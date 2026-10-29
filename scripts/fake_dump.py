#!/usr/bin/env python3
"""Build a synthetic grandMA3 dump folder (the shape ma3/dump_show.lua writes) to
exercise the reader and writer without onPC: 2 dimmers and 2 Ayrton Alienpix."""
import json, os, shutil, sys
LIB = os.path.expanduser("~/MALightingTechnology/gma3_2.3.2/shared/lib_fixture_types/grandma3")
out = sys.argv[1] if len(sys.argv) > 1 else "out/fakedump"
os.makedirs(os.path.join(out, "fixturetypes"), exist_ok=True)
shutil.copy(os.path.join(LIB, "ayrton@alienpix-rs.xml"), os.path.join(out, "fixturetypes", "Alienpix-RS.xml"))
open(os.path.join(out, "fixturetypes", "Dimmer.xml"), "w").write('''<?xml version="1.0" encoding="UTF-8"?>
<GMA3 DataVersion="2.3.2.0">
 <FixtureType Name="Dimmer" Manufacturer="Generic" ShortName="Dim">
  <DMXModes><DMXMode Name="00" Geometry="Base"><DMXChannels>
   <DMXChannel Coarse="1" Default="000000" Geometry="Base"><LogicalChannel Attribute="Dimmer"><ChannelFunction Attribute="Dimmer">
    <ChannelSet Name="Closed" PhysicalTo="0"/><ChannelSet DMXFrom="010101"/><ChannelSet Name="Open" DMXFrom="FFFFFF"/>
   </ChannelFunction></LogicalChannel></DMXChannel>
  </DMXChannels></DMXMode></DMXModes>
 </FixtureType>
</GMA3>''')

def uni(fill=None):
    return [0] * 512

def snap(**chg):
    """chg: {'u.a': value}"""
    s = {"1": uni(), "2": uni()}
    # Alienpix defaults: pan/tilt 128 at 2.1+ and 2.53+, RGB 255
    for base in (1, 53):
        for off in (0, 2, 4, 16):
            s["2"][base - 1 + off] = 128
        for off in (12, 13, 14, 47, 48, 49):
            s["2"][base - 1 + off] = 255
        s["2"][base - 1 + 10] = 50
    for k, v in chg.items():
        u, a = k.split(".")
        s[u][int(a) - 1] = v
    return s

fixtures = [
    {"fid": 1, "name": "Dim 1", "fixturetype": "Dimmer", "mode": "00", "patch": "1.001"},
    {"fid": 2, "name": "Dim 2", "fixturetype": "Dimmer", "mode": "00", "patch": "1.002"},
    {"fid": 101, "name": "Pix 1", "fixturetype": "Alienpix-RS", "mode": "Ex 16 Bit (52 ch)", "patch": "2.001", "posx": -1.0, "posy": 4.0},
    {"fid": 102, "name": "Pix 2", "fixturetype": "Alienpix-RS", "mode": "Ex 16 Bit (52 ch)", "patch": "2.053", "posx": 1.0, "posy": 4.0},
    {"fid": 500, "name": "Grouping", "fixturetype": "Grouping", "mode": "", "patch": None},
]
dump = {
    "generator": "fake", "show": "fake show", "universes": [1, 2],
    "fixtures": fixtures,
    "baseline": snap(),
    "groups": [{"no": 1, "name": "Dimmers", "members": [1, 2]}, {"no": 2, "name": "Pix", "members": [101, 102]}],
    "presetpools": [
        {"index": 1, "name": "Dimmer", "presets": [{"no": 1, "name": "Full", "dmx": snap(**{"1.1": 255, "1.2": 255, "2.12": 255, "2.64": 255})}]},
        {"index": 2, "name": "Position", "presets": [{"no": 1, "name": "Centre", "dmx": snap(**{"2.1": 100, "2.3": 140, "2.53": 156, "2.55": 140})}]},
        {"index": 4, "name": "Color", "presets": [{"no": 1, "name": "Red", "dmx": snap(**{"2.14": 0, "2.15": 0, "2.66": 0, "2.67": 0})}]},
    ],
    "sequences": [
        {"no": 1, "name": "Main", "cues": [
            {"no": 1, "name": "Look 1", "fadein": 2.0, "delayin": 0, "trigtype": "Go", "dmx": snap(**{"1.1": 128, "1.2": 255, "2.12": 255, "2.1": 100})},
            {"no": 2, "name": "Look 2", "fadein": 5.0, "delayin": 1.0, "trigtype": "Go", "dmx": snap(**{"1.1": 0, "1.2": 64, "2.12": 128, "2.64": 255, "2.66": 0})},
            {"no": 3, "name": "Out", "fadein": 3.0, "delayin": 0, "trigtype": "Follow", "trigtime": 2.0, "dmx": snap()},
        ]},
        {"no": 2, "name": "Blinder", "cues": [{"no": 1, "name": "Blind", "fadein": 0.0, "delayin": 0, "dmx": snap(**{"1.1": 255, "1.2": 255})}]},
    ],
    "pages": [{"no": 1, "name": "Page 1", "executors": [{"no": 201, "name": "", "seq": 1, "seqname": "Main"}, {"no": 202, "name": "", "seq": 2, "seqname": "Blinder"}]}],
}
json.dump(dump, open(os.path.join(out, "dump.json"), "w"), indent=1)
print("fake dump in", out)
