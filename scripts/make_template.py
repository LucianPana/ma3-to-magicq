#!/usr/bin/env python3
"""Build templates/empty-1.9.7.4.shw from a show MagicQ PC wrote back:
keep only the settings and window records."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from magicq import shwfile

src = sys.argv[1] if len(sys.argv) > 1 else "out/rt_48chandesk.shw"
show = shwfile.load(src)
show.records = [r for r in show.records if r.tag in ("V", "T", "Y", "Z", "E1", "Q")]
show.comments = [c for c in show.comments]
os.makedirs("templates", exist_ok=True)
shwfile.save(show, "templates/empty-1.9.7.4.shw")
print("template records:", [r.tag for r in show.records])
