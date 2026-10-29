"""Bisect which hand-made record MagicQ rejects: S only, S+C, S+C+M+N."""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from magicq import shwfile

def rec(text):
    lines = text.strip("\n").split("\n")
    return shwfile.Record(lines[0].split(",")[0], lines)

S = rec('''S,0001,"spike cue",3,0,0,
0000,0000,0000,0000,0000,0000,0000,0000,0000,0000,
1,80,2,ff,3,40,

00000000,
00000000,
00000004,
0000,0000,0000,0000,
00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,00000000,

00000000,;
''')
C = rec('''C,0001,"spike stack",0000,0001,0000a01f,
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
''')
M = rec('''M,0001,"",00000001,0400,0300,0002,000a,"",0000006b,0000,0000;
''')
N = rec('''N,0001,0000,00000000,0002,00000000,00000000,0000,"spike pb","",00000000,00000000,;
''')

def run(label, extra_after_g, extra_end):
    base = shwfile.load("out/rt_48chandesk.shw")
    recs = base.records
    gi = max(i for i, r in enumerate(recs) if r.tag == "G")
    recs[gi + 1:gi + 1] = extra_after_g
    recs.extend(extra_end)
    inp = f"out/bisect_{label}_in.shw"; outp = f"out/bisect_{label}_out.shw"
    shwfile.save(base, inp)
    r = subprocess.run([sys.executable, "scripts/mq_roundtrip.py", inp, outp, "--wait", "30"], capture_output=True, text=True)
    ok = r.returncode == 0
    print(f"### {label}: {'ACCEPTED' if ok else 'REJECTED'}", r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "")
    if ok:
        out = shwfile.load(outp)
        for tag in ("S", "C", "M", "N"):
            for x in out.by_tag(tag):
                print("   " + x.lines[0][:100]); print("   " + " | ".join(x.lines[1:4])[:160])
    return ok

which = sys.argv[1:] or ["s", "sc", "scmn"]
if "s" in which: run("s", [S], [])
if "sc" in which: run("sc", [S, C], [])
if "scmn" in which: run("scmn", [S, C], [M, N])
