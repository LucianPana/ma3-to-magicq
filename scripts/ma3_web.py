#!/usr/bin/env python3
"""Send grandMA3 command lines through the onPC web remote (http://127.0.0.1:8080).

usage: ma3_web.py "Fixture 1 At 50" ["next command" ...]
env:   MA3_WEB_URL (default http://127.0.0.1:8080/)

The web remote is on when onPC's Network settings have Web Remote enabled (it was on
by default here). This drives it with dev-browser (headless Chrome): click the command
line, type the command, press Enter. Slower than OSC (about a second per command) but
needs no setting inside the show.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

URL = os.environ.get("MA3_WEB_URL", "http://127.0.0.1:8080/")
PAGE = "ma3web"

SCRIPT = """
const page = await browser.getPage(%(page)s);
let connected = false;
if (page.url().startsWith(%(url)s)) {
  const txt = await page.evaluate(() => document.body.innerText).catch(() => "");
  connected = !/Disconnected|Connecting/.test(txt) && txt.length > 0;
}
if (!connected) {
  await page.setViewport({ width: 1280, height: 720 });
  await page.goto(%(url)s, { waitUntil: "networkidle2" });
  await new Promise(r => setTimeout(r, 3000));
}
const cmds = %(cmds)s;
for (const c of cmds) {
  await page.mouse.click(500, 451);
  await new Promise(r => setTimeout(r, 150));
  await page.keyboard.down("Control"); await page.keyboard.press("a"); await page.keyboard.up("Control");
  await page.keyboard.type(c, { delay: 2 });
  await new Promise(r => setTimeout(r, 100));
  await page.keyboard.press("Enter");
  await new Promise(r => setTimeout(r, %(gap)d));
}
"sent " + cmds.length
"""


def available() -> bool:
    return shutil.which("dev-browser") is not None


def send(commands: list[str], gap_ms: int = 400) -> str:
    if not available():
        raise RuntimeError("dev-browser is not installed (npm install -g dev-browser)")
    script = SCRIPT % {"page": json.dumps(PAGE), "url": json.dumps(URL), "cmds": json.dumps(commands), "gap": gap_ms}
    proc = subprocess.run(["dev-browser", "--headless"], input=script, capture_output=True, text=True, timeout=120 + len(commands) * 2)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return proc.stdout.strip()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    print(send(sys.argv[1:]))
