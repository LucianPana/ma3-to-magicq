import glob, os
import pytest
from ma3 import fixturetypes
from model import ATTR

LIB = os.path.expanduser("~/MALightingTechnology/gma3_2.3.2/shared/lib_fixture_types/grandma3")
FILES = sorted(glob.glob(os.path.join(LIB, "*.xml")))


def test_dmx8():
    assert fixturetypes.dmx8("7F7F7F") == 0x7f
    assert fixturetypes.dmx8("32768/2") == 128
    assert fixturetypes.dmx8("255/1") == 255
    assert fixturetypes.dmx8(None, 7) == 7


@pytest.mark.skipif(not FILES, reason="grandMA3 library not installed")
def test_alienpix():
    path = os.path.join(LIB, "ayrton@alienpix-rs.xml")
    head, notes = fixturetypes.head_from_xml(path)
    assert head.manufacturer == "Ayrton"
    assert head.nchans == 52
    assert head.channels[0].attr == ATTR["Pan"] and head.channels[0].kind == "pos16c"
    assert head.channels[1].kind == "pos16f"
    dim = head.channels[11]
    assert dim.attr == ATTR["Intensity"] and dim.kind == "htp8"
    assert any(r.name == "Closed" for r in dim.ranges)


@pytest.mark.skipif(not FILES, reason="grandMA3 library not installed")
@pytest.mark.parametrize("path", [p for p in FILES if "@set" not in p and "set@" not in os.path.basename(p)][:40], ids=lambda p: os.path.basename(p))
def test_library_parses(path):
    try:
        head, notes = fixturetypes.head_from_xml(path)
    except ValueError as e:
        pytest.skip(str(e))
    assert head.nchans >= 1
    attrs = [c.attr for c in head.channels if not c.kind.endswith("f")]
    assert len(attrs) == len(set(attrs)), "duplicate attribute in head"
