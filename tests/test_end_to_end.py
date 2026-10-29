import os, subprocess, sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.expanduser("~/MALightingTechnology/gma3_2.3.2/shared/lib_fixture_types/grandma3/ayrton@alienpix-rs.xml")


@pytest.mark.skipif(not os.path.exists(LIB), reason="grandMA3 library not installed")
def test_fake_dump_converts(tmp_path):
    dump = tmp_path / "dump"
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "fake_dump.py"), str(dump)], check=True, cwd=ROOT)
    out = tmp_path / "fake.shw"
    subprocess.run([sys.executable, os.path.join(ROOT, "convert.py"), str(dump), str(out)], check=True, cwd=ROOT)
    sys.path.insert(0, ROOT)
    from magicq import shwfile
    show = shwfile.load(str(out))
    counts = {t: len(show.by_tag(t)) for t in ("P", "L", "H", "F", "G", "S", "C", "M", "N")}
    assert counts == {"P": 2, "L": 2 + 2 * 52, "H": 4, "F": 3, "G": 2, "S": 4, "C": 2, "M": 1, "N": 2}
    # the first cue carries the dimmer at 50% on absolute channel 1
    s1 = show.by_tag("S")[0]
    assert s1.lines[2].startswith("1,80,2,ff,")
    assert (tmp_path / "fake-report.md").exists()
