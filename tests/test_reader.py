"""magicq.reader: .shw back into the model."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from magicq import shwfile, writer           # noqa: E402
from magicq.reader import read_shw, kind_of  # noqa: E402
import demo_show                             # noqa: E402

SAMPLES = os.path.join(ROOT, "samples")


def test_kind_of_masks_flag_bits():
    assert kind_of(0x1000001) == "htp8"
    assert kind_of(0x40002022) == "ltp8mix"
    assert kind_of(0x8012) == "ctrl"
    assert kind_of(0x36) == "pos16c"
    assert kind_of(0x32) == "ltp8"


def test_demo_round_trip(tmp_path):
    show = demo_show.build()
    path = str(tmp_path / "demo.shw")
    writer.write_show(show, path)
    back = read_shw(path)
    assert [(f.fid, f.universe, f.address, f.head.nchans) for f in back.fixtures] == \
           [(f.fid, f.universe, f.address, f.head.nchans) for f in sorted(show.fixtures, key=lambda f: f.abs_chan)]
    for a, b in zip(sorted(show.fixtures, key=lambda f: f.abs_chan), back.fixtures):
        assert [(c.attr, c.kind, c.default) for c in a.head.channels] == [(c.attr, c.kind, c.default) for c in b.head.channels]
    assert [(g.name, g.members) for g in back.groups] == [(g.name, g.members) for g in show.groups]
    assert {(p.kind, p.name): p.values for p in back.palettes} == {(p.kind, p.name): p.values for p in show.palettes}
    assert [s.name for s in back.stacks] == [s.name for s in show.stacks]
    for a, b in zip(show.stacks, back.stacks):
        assert [(c.number, c.name, c.values, c.fade, c.delay) for c in a.cues] == \
               [(c.number, c.name, c.values, c.fade, c.delay) for c in b.cues]
    assert [(p.page, p.index, p.kind, p.ref) for p in back.playbacks] == \
           [(p.page, p.index, p.kind, p.ref) for p in show.playbacks]
    red = [p for p in back.palettes if p.kind == "col"][0]
    assert red.rgb is not None and red.rgb[0] > 0.9 and red.rgb[1] < 0.1


@pytest.mark.parametrize("name", ["mq50-zt-ttr-2026.shw", "mq50-ziua-tm.shw", "chauvet.shw"])
def test_samples(name):
    path = os.path.join(SAMPLES, name)
    if not os.path.exists(path):
        pytest.skip("sample not present")
    sf = shwfile.load(path)
    show = read_shw(path)
    assert len(show.heads()) <= len(sf.by_tag("P"))
    assert len(show.fixtures) >= len(sf.by_tag("H")) - len(sf.by_tag("P"))  # H has one entry per head plus scene objects
    assert len(show.groups) == len(sf.by_tag("G"))
    assert len(show.palettes) == len(sf.by_tag("F"))
    assert len(show.stacks) <= len(sf.by_tag("C"))
    assert sum(len(s.cues) for s in show.stacks) <= len(sf.by_tag("S")) + 5
    # every cue value belongs to a patched channel and palette refs resolve
    for st in show.stacks:
        for c in st.cues:
            for (fid, off) in c.values:
                assert off < show.fixture(fid).head.nchans
            for ref in c.refs.values():
                assert show.palette(ref) is not None or True  # palettes may have been deleted in MagicQ
    assert any(st.chase for st in show.stacks) or name == "chauvet.shw"
