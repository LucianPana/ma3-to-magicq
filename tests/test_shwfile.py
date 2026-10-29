import glob, os
import pytest
from magicq import shwfile

HERE = os.path.dirname(__file__)
SAMPLES = sorted(glob.glob(os.path.join(HERE, "..", "samples", "*.shw")) + glob.glob(os.path.join(HERE, "..", "out", "rt_*.shw")))


@pytest.mark.parametrize("path", SAMPLES, ids=[os.path.basename(p) for p in SAMPLES])
def test_roundtrip_bytes(path):
    text = open(path, encoding="latin-1").read()
    show = shwfile.parse(text)
    assert show.records and show.records[0].tag == "V"
    assert show.text() == text


def test_split_fields():
    assert shwfile.split_fields('C,0002,"a,b",0000,;') == ["C", "0002", '"a,b"', "0000"]
    assert shwfile.split_fields("0000,0000,") == ["0000", "0000"]
    assert shwfile.split_fields("0,0,0,0,;") == ["0", "0", "0", "0"]


def test_record_accessors():
    show = shwfile.parse('\\ x\n\nV,0091,"MagicQ 1",01090704,0000,0002,;\n\nS,0002,"backstage",c,0,0,\n0000,\n')
    s = show.one("S")
    assert s.id == 2 and s.name == "backstage" and s.header[2] == "c"
