#!/usr/bin/env python3
"""Round-trip a MagicQ show file through MagicQ PC without touching its GUI.

MagicQ PC loads the show named in show/status.dat at startup and writes that
show back (normalised) a second after loading. So: copy the file into the
MagicQ show folder, point status.dat at it, start MagicQ, wait, stop it, and
read the rewritten file.

usage: mq_roundtrip.py INPUT.shw OUTPUT.shw [--wait SECONDS]
"""
import os, shutil, signal, subprocess, sys, time

SHOW_DIR = os.path.expanduser("~/Documents/MagicQ/show")
STATUS = os.path.join(SHOW_DIR, "status.dat")
APP = "/Applications/MagicQ/MagicQ.app"


def magicq_pids():
    out = subprocess.run(["pgrep", "-x", "MagicQ"], capture_output=True, text=True).stdout.split()
    return [int(p) for p in out]


def stop_magicq():
    for pid in magicq_pids():
        os.kill(pid, signal.SIGKILL)  # MagicQ ignores SIGTERM
    for _ in range(20):
        if not magicq_pids():
            return
        time.sleep(0.25)


def point_status_at(show_path):
    data = open(STATUS, "rb").read().split(b"\n")
    for i, line in enumerate(data):
        if line.startswith(b'T,"'):
            rest = line.split(b'",', 1)[1]
            data[i] = b'T,"' + show_path.encode() + b'",' + rest
            break
    else:
        raise SystemExit("no T record in status.dat")
    open(STATUS, "wb").write(b"\n".join(data))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    wait = 15
    if "--wait" in sys.argv:
        wait = int(sys.argv[sys.argv.index("--wait") + 1])
        args = [a for a in args if a != str(wait)]
    src, dst = args[0], args[1]
    name = "rt_" + os.path.basename(src)
    target = os.path.join(SHOW_DIR, name)
    stop_magicq()
    shutil.copyfile(src, target)
    before = os.stat(target).st_mtime
    point_status_at(target)
    subprocess.run(["open", "-a", APP], check=True)
    t0 = time.time()
    while time.time() - t0 < wait:
        time.sleep(1)
        sbk = os.path.splitext(target)[0] + ".sbk"
        if os.path.exists(sbk) and os.stat(sbk).st_mtime > before + 0.5:
            time.sleep(3)  # let the write finish
            break
    stop_magicq()
    sbk = os.path.splitext(target)[0] + ".sbk"
    if os.path.exists(sbk) and os.stat(sbk).st_mtime > before:
        target = sbk  # MagicQ writes the loaded show back as <name>.sbk
    if not os.path.exists(target) or os.stat(target).st_mtime <= before + 0.5:
        print("MagicQ did not rewrite the show (not accepted, or loaded another file)")
        # status.dat tells which show it ended on
        for line in open(STATUS, "rb").read().split(b"\n"):
            if line.startswith(b'T,"'):
                print("status.dat show:", line[:120])
        sys.exit(2)
    shutil.copyfile(target, dst)
    print("rewritten:", dst, os.path.getsize(dst), "bytes")


if __name__ == "__main__":
    main()
