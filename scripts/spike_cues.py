"""Spike: add a cue, a cue stack and a playback to the 48-dimmer show by hand,
round-trip it through MagicQ PC and report what survived."""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from magicq import shwfile

base = shwfile.load("out/rt_48chandesk.shw")

S = shwfile.Record("S", '''S,0001,"spike cue",3,0,0,
0000,0000,0000,0000,0000,0000,0000,0000,0000,0000,
1,80,2,ff,3,40,

00000000,
00000000,
00000004,
0000,0000,0000,0000,
00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,

00000000,;
'''.split("\n"))

C = shwfile.Record("C", '''C,0001,"spike stack",0000,0001,0000a01f,
000007d0,0042,003c,003c,003c,003c,003c,0000,0000,0000,0000,0000,0100,0000,0001,0001,00000000,
0000,0000,0001,0000,00006000,1.000000,"",
00000000,
00000000,0000,0000,0000,0000,
00000000,
0000,00000000,0100,0100,00000000,
00000000,00000f00,0000,0000,
0000,0000,000a,
0000,0000,0000,0000,0000,0000,0000,0000,0000,0000,
00000000,00000000,0,"",
00000000,00000000,00000000,00000000,
00000000,00000000,00000000,"",0000,0000,0000,0000,00000000,0000000000000000,00000000,00000000,;
'''.split("\n"))

N = shwfile.Record("N", '''N,0001,0000,00000000,0002,00000000,00000000,0000,"spike pb","",00000000,00000000,;
'''.split("\n"))

recs = base.records
# insert S and C after the G record, N at the end
gi = max(i for i, r in enumerate(recs) if r.tag == "G")
recs[gi + 1:gi + 1] = [S, C]
recs.append(N)
shwfile.save(base, "out/spike_cues_in.shw")
r = subprocess.run([sys.executable, "scripts/mq_roundtrip.py", "out/spike_cues_in.shw", "out/spike_cues_out.shw", "--wait", "30"])
if r.returncode:
    sys.exit(r.returncode)
out = shwfile.load("out/spike_cues_out.shw")
for tag in ("S", "C", "N", "G"):
    for rec in out.by_tag(tag):
        print("\n".join(rec.lines[:4]))
        print("...")
