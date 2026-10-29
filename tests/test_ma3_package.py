"""MagicQ to grandMA3: the import package, the generated GDTF, the library matcher, the OSC encoder, the Lua dry run."""
import json
import os
import shutil
import subprocess
import sys
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from magicq import writer as mq_writer           # noqa: E402
from magicq.reader import read_shw               # noqa: E402
from ma3 import writer as ma3_writer, gdtf, libmatch, attributes, fixturetypes  # noqa: E402
import demo_show                                 # noqa: E402
import ma3_osc                                   # noqa: E402

GRANDMA2 = os.path.join(libmatch.SHARED, "grandma2")


@pytest.fixture(scope="module")
def package(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("pkg")
    shw = str(tmp / "demo.shw")
    mq_writer.write_show(demo_show.build(), shw)
    show = read_shw(shw)
    out = str(tmp / "ma3")
    data = ma3_writer.write_package(show, out, match_library=False)
    return show, out, data


def test_package_contents(package):
    show, out, data = package
    assert os.path.exists(os.path.join(out, "show.json")) and os.path.exists(os.path.join(out, "report.md"))
    assert {h["key"] for h in data["heads"]} == {"Generic_Dimmer", "Demo_Spot_10ch"}
    spot = next(h for h in data["heads"] if h["key"] == "Demo_Spot_10ch")
    pan = next(c for c in spot["channels"] if c["attr"] == "Pan")
    assert pan["bytes"] == 2 and pan["offset"] == 1 and pan["fine"] == 2
    assert [f["patch"] for f in data["fixtures"]] == ["1.001", "1.002", "2.001", "2.011"]
    assert data["groups"][0]["fids"] == [1, 2]
    pools = sorted(p["pool"] for p in data["presets"])
    assert pools == [1, 2, 3, 4]  # dimmer, position, gobo, colour
    pos = next(p for p in data["presets"] if p["pool"] == 2)
    assert pos["values"]["101"] == {"Pan": 32768, "Tilt": 32768}
    main = data["sequences"][0]
    assert main["cues"][0]["fade"] == 2.0 and main["cues"][1]["delay"] == 1.0
    assert main["cues"][0]["values"]["1"] == {"Dimmer": 128}
    assert main["cues"][0]["values"]["101"]["Pan"] == 16384
    assert data["executors"][0] == {"page": 1, "exec": 201, "sequence": 1, "legend": "Main"}


def test_gdtf_reloads_as_the_same_head(package):
    show, out, data = package
    for head in show.heads():
        path = os.path.join(out, "fixturetypes", gdtf.file_name(head))
        with zipfile.ZipFile(path) as z:
            assert "description.xml" in z.namelist()
        back, notes = fixturetypes.head_from_xml(path, head.mode or "Mode 1")
        assert back.nchans == head.nchans
        assert [c.attr for c in back.channels] == [c.attr for c in head.channels]
        assert [c.kind.endswith("f") for c in back.channels] == [c.kind.endswith("f") for c in head.channels]


def test_gdtf_ids_are_stable():
    a = demo_show.spot_head()
    assert gdtf.fixture_type_id(a) == gdtf.fixture_type_id(demo_show.spot_head())
    assert gdtf.fixture_type_id(a) != gdtf.fixture_type_id(demo_show.dimmer_head())


def test_attribute_names():
    assert attributes.ma3_name(16, "Red") == "ColorRGB_R"
    assert attributes.ma3_name(16, "Cyan") == "ColorRGB_C"
    assert attributes.ma3_name(20, "Reset") == "FixtureGlobalReset"
    assert attributes.ma3_name(21, "Lamp") == "LampControl"
    assert attributes.ma3_name(2, "Shutter") == "Shutter1"
    assert attributes.feature_group("ColorRGB_C") == "Color"
    assert attributes.feature_group("Gobo1PosRotate") == "Gobo"
    assert attributes.feature_group("Zoom") == "Focus"
    assert attributes.feature_group("LampControl") == "Control"


@pytest.mark.skipif(not os.path.isdir(GRANDMA2), reason="grandMA3 onPC library not installed")
def test_library_candidates():
    from model import HeadDef, Channel, ATTR
    sharpy = HeadDef("Clay Paky", "Sharpy", "Standard", [Channel("Dimmer", ATTR["Intensity"], "htp8")])
    assert "grandma2:clay paky@sharpy.pxml" in libmatch.candidates(sharpy)
    nothing = HeadDef("Nobody", "Zzzqqq 9000", "", [Channel("Dimmer", 0, "htp8")])
    assert libmatch.candidates(nothing) == []


def test_osc_encoding():
    msg = ma3_osc.osc_message("/cmd", "Fixture 1 At 75")
    assert msg.startswith(b"/cmd\0\0\0\0,s\0\0Fixture 1 At 75\0")
    assert len(msg) % 4 == 0


@pytest.mark.skipif(shutil.which("lua") is None, reason="lua interpreter not installed")
def test_lua_dry_run(package):
    show, out, data = package
    subprocess.run(["lua", os.path.join("scripts", "lua_dryrun.lua"), out], check=True, cwd=ROOT)
    with open(os.path.join(out, "result.json"), encoding="utf-8") as fh:
        res = json.load(fh)
    assert res["failed"] == []
    assert res["counts"] == {"cues": 3, "executors": 3, "fixture_types": 2, "fixtures": 4, "groups": 2, "presets": 4, "sequences": 2}
    with open(os.path.join(out, "dryrun_commands.txt"), encoding="utf-8") as fh:
        cmds = fh.read().splitlines()
    assert 'Fixture 101 + 102 Attribute "Pan" At Absolute Decimal16 32768' in cmds
    assert "Store Sequence 1 Cue 2 /NC" in cmds
    assert 'Set Sequence 1 Cue 1 Property "CueFade" 2' in cmds
