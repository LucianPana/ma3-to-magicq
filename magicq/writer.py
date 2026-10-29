"""Write a model.Show as a MagicQ .shw file.

The settings and window records (V, T, Y, Z, E1, Q) come from a template that
MagicQ PC 1.9.7.4 wrote itself (templates/empty-1.9.7.4.shw). Everything that
describes the show (P, L, H, F, G, S, C, M, N) is generated here following
docs/shw-format.md.
"""
from __future__ import annotations

import os
import time
from typing import Iterable

from model import (Show, HeadDef, Fixture, Palette, Cue, CueStack, family, ATTR_NAME)
from . import shwfile

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "templates", "empty-1.9.7.4.shw")

TIME_UNIT = 0.1     # seconds per unit in the cue time words (to be confirmed on a console)
PLAYBACKS_PER_PAGE = 10
PALETTE_TYPE = {"int": 0x9, "pos": 0xa, "col": 0xb, "beam": 0xc}
PLAYBACK_KIND = {"stack": 2, "group": 5, "palette_int": 4, "palette_pos": 5, "palette_col": 6, "palette_beam": 7}


def h(v: int, width: int = 4) -> str:
    return f"{v:0{width}x}"


def q(s: str) -> str:
    return '"' + s.replace('"', "'") + '"'


def tu(seconds: float | None, default: float = 0.0) -> int:
    s = default if seconds is None else seconds
    return max(0, min(0xFFFF, int(round(s / TIME_UNIT))))


def wrap(items: Iterable[str], per_line: int = 20) -> list[str]:
    items = list(items)
    lines = []
    for i in range(0, len(items), per_line):
        lines.append(",".join(items[i:i + per_line]) + ",")
    return lines


# ---------------------------------------------------------------------------
# P: personality
# ---------------------------------------------------------------------------
def _chan_locate_line(ch) -> str:
    """The per-channel 4-word line near the end of a P record (copied patterns)."""
    fam = family(ch.attr)
    loc = ch.locate if ch.locate is not None else ch.default
    if fam == "int":
        return "00000007,0100,01ff,01ff,"
    if fam == "pos":
        return "00000047,0180,0000,0000," if ch.kind.endswith("c") else "00000047,0100,0000,0000,"
    if ch.kind == "ctrl":
        return "000000da,0100,0000,0000,"
    return f"000000c0,{h(0x100 | (loc & 0xff))},0000,{h(0x100 | (loc & 0xff))},"


def p_record(idx: int, head: HeadDef) -> shwfile.Record:
    chans = head.channels
    nranges = sum(len(c.ranges) for c in chans)
    is_moving = any(family(c.attr) == "pos" for c in chans)
    flags = 0xC0000001 if is_moving else 0x80000001
    lines = [
        f"P,{h(idx)},{q(head.key)},{q(head.manufacturer)},{q(head.mode)},{q(head.model)},",
        f"{h(len(chans))},{h(nranges)},0000,0000,{h(head.pan_deg if is_moving else 0)},{h(head.tilt_deg if is_moving else 0)},0001,0001,0200,{h(flags, 8)},",
    ]
    for c in chans:
        lines.append(f"{q(c.name)},{h(c.type_word, 8)},{h(c.attr, 8)},")
    defaults = [h(len(chans))]
    for i, c in enumerate(chans):
        defaults += [h(i), h(c.default & 0xff)]
    lines += wrap(defaults, 41)
    for i, c in enumerate(chans):
        for r in c.ranges:
            lines.append(f"{h(i)},{q(r.name)},{h(r.lo & 0xff)},{h(r.hi & 0xff)},0000,00000000,")
    # no built-in palettes, no macros
    lines.append("00000000,")
    lines.append(",".join(["00000000"] * 21) + ",")
    lines.append('"",00000000,0000,0000,0000,0000,0000,')
    for c in chans:
        lines.append(_chan_locate_line(c))
    short = head.model[:15]
    lines += [
        q(short) + ",",
        f'0000,"",{q(head.manufacturer)},{q(head.model)},0000,0000,0000,0000,0000,00000000,',
        "00000026," if is_moving else "0000000e,",
        '"","","",',
        "0.000000,0.000000,0.000000,0.000000,0.000000,0.000000,",
        f'{q(head.manufacturer + " " + head.model + "_" + head.mode)},0000,',
        "3,149,194,78,b9,118,b8,1db,16.000000," if is_moving else "0,0,0,0,0,0,0,0,0.000000,",
        "3,5,1,0,1f0e,105,3,73,e6,0,0," if is_moving else "0,0,0,0,0,0,0,0,0,0,0,",
        "105,1,f," if is_moving else "0,0,0,",
        "0,",
        "00000001,00000001,0000,0000,0000,0000,0000,0000,0000,0000,0000,0000,0000,0000,0000,0000,0000,0000,0000,",
        f"0000,0000,0000,00000003,{h(int(time.time()), 8)},0,",
        q(short) + ",",
        "0,",
        '"{00000000-0000-0000-0000-000000000000}",',
        "1.000000,0000,0000,",
        "0000,",
        "0.800000,0.800000,0.000000,0.000000," if is_moving else "0.850000,0.850000,0.000000,0.000000,",
        "0.000000,0.000000,0.000000,0.000000,0,0,",
        "0," if is_moving else ";",
    ]
    if is_moving:
        lines.append(";")
    lines.append("")
    return shwfile.Record("P", lines)


# ---------------------------------------------------------------------------
# L and H: patch
# ---------------------------------------------------------------------------
def l_records(fx: Fixture, pidx: int) -> list[shwfile.Record]:
    recs = []
    multi = fx.head.nchans > 1
    for i, c in enumerate(fx.head.channels):
        tw = c.type_word
        if not multi and c.kind == "htp8":
            tw |= 0x1000000  # what 1.9.7.4 writes for plain dimmers
        n = 2 if multi else 0
        line = (f"L,{fx.abs_chan + i:x},{q(fx.name)},{tw:x},{pidx:x},{i:x},0,ffff,0,0,{fx.fid:x},{n},"
                f'"",0,0,0,0,0,0,0,0,0,0,0,{fx.color_rgb:x},;')
        recs.append(shwfile.Record("L", [line]))
    return recs


def h_record(fx: Fixture, dimmer: bool) -> shwfile.Record:
    # vis entry per head; the string line is copied from a MagicQ-written file
    ref = "00000036" if dimmer else "00000003"
    strings = '"[VXVk","_SXWT","[RX]\\","[_X]\\","XY^]","XY^]","XY^]",' if dimmer else \
              '"[^XP\\","__X]\\","[SX]\\","XY^]","XY^]","XY^]","_QX]\\",'
    return shwfile.Record("H", [
        f'H,{h(fx.fid, 8)},1,0,5,0,0,0,31,0,0,"",{ref},',
        strings,
        "1,1,1,0,0,;" if dimmer else "1,1,2,0,0,;",
    ])


# ---------------------------------------------------------------------------
# G, F
# ---------------------------------------------------------------------------
def g_record(idx: int, name: str, chans: list[int]) -> shwfile.Record:
    return shwfile.Record("G", [
        f"G,{h(idx)},{q(name)},{len(chans):x}," + ",".join(f"{c:x}" for c in chans) + ",21000024,",
        "00000001,0,",
        "",
        "00000000,0,",
        "0,",
        "00000000,0000,0000,0000,0000,0000,0000,0000,00000000,00000000,",
        ";",
        "",
    ])


def _rgb_to_xy(rgb: tuple[float, float, float]) -> tuple[float, float]:
    r, g, b = rgb
    X = 0.4124 * r + 0.3576 * g + 0.1805 * b
    Y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    Z = 0.0193 * r + 0.1192 * g + 0.9505 * b
    s = X + Y + Z
    if s <= 0:
        return 0.3127, 0.3290
    return X / s, Y / s


def f_record(kind: str, idx: int, pal: Palette, show: Show) -> shwfile.Record:
    triples = []
    for (fid, off), val in sorted(pal.values.items(), key=lambda kv: (show.fixture(kv[0][0]).abs_chan, kv[0][1])):
        triples += [f"{show.fixture(fid).abs_chan + off:x}", f"{val & 0xff:x}", "0"]
    lines = [f"F,{PALETTE_TYPE[kind]:x}{h(idx, 3)},{q(pal.name)},{len(triples) // 3:x},"]
    body = wrap(triples, 60)
    if kind == "pos":
        tail_head, tail_n, tail_w = "05000001", "00000007", "0000"
    elif kind == "col":
        tail_head, tail_n, tail_w = "06000026", "00000025", "0100"
    elif kind == "beam":
        tail_head, tail_n, tail_w = "0200006d", "00000003", "0000"
    else:
        tail_head, tail_n, tail_w = "0000006b", "00000000", "0000"
    if body:
        body[-1] = body[-1] + tail_head + ","
    else:
        body = [tail_head + ","]
    lines += body
    lines.append(tail_n + ",")
    lines.append(tail_w + ",")
    if kind == "col":
        x, y = _rgb_to_xy(pal.rgb or (1.0, 1.0, 1.0))
        lines.append(f"{x:.6f},{y:.6f},1.000000,0.000000,0.000000,0.000000,0000,00000000,")
        rows = ["0,0,0,"] * 64
        rows[0] = "1,40,0,"
        if pal.rgb:
            r, g, b = pal.rgb
            rows[16] = f"{int(r * 255):x},0,1,"
            rows[17] = f"{int(g * 255):x},0,1,"
            rows[18] = f"{int(b * 255):x},0,1,"
            rows[19] = "600,0,1,"
        rows[-1] = rows[-1][:-1] + ";"
        lines += rows
    else:
        lines.append("0.000000,0.000000,0.000000,0.000000,0.000000,0.000000,0000,00000000,")
        lines.append("0,0,;")
    lines.append("")
    return shwfile.Record("F", lines)


# ---------------------------------------------------------------------------
# S, C, M, N
# ---------------------------------------------------------------------------
def s_record(idx: int, cue: Cue, show: Show) -> shwfile.Record:
    pairs = []
    for (fid, off), val in sorted(cue.values.items(), key=lambda kv: (show.fixture(kv[0][0]).abs_chan, kv[0][1])):
        pairs += [f"{show.fixture(fid).abs_chan + off:x}", f"{val & 0xff:x}"]
    fi = tu(cue.fade)
    fo = tu(cue.fade_out, cue.fade)
    fp = tu(cue.fade_pos, cue.fade)
    fc = tu(cue.fade_col, cue.fade)
    fb = tu(cue.fade_beam, cue.fade)
    d = tu(cue.delay)
    times = f"{h(fi)},{h(fo)},{h(fp)},{h(fc)},{h(fb)},{h(d)},{h(d)},{h(d)},{h(d)},{h(d)},"
    lines = [f"S,{h(idx)},{q(cue.name)},{len(pairs) // 2:x},0,0,", times]
    lines += wrap(pairs, 60) or [""]
    lines += [
        "",
        "00000000,",
        "00000000,",
        "00000004,",
        "0000,0000,0000,0000,",
        ",".join(["00000000"] * 14) + ",",
        "",
        "00000000,;",
        "",
    ]
    return shwfile.Record("S", lines)


def c_record(idx: int, stack: CueStack, first_s: int, show: Show) -> shwfile.Record:
    n = len(stack.cues)
    flags = 0x0000a01f if n == 1 else 0x0000801f
    speed = max(1, int(round(stack.chase_speed * 1000)))
    lines = [
        f"C,{h(idx)},{q(stack.name)},0000,{h(n)},{h(flags, 8)},",
        f"{h(speed, 8)},0042,003c,003c,003c,003c,003c,0000,0000,0000,0000,0000,0100,0000,0001,0001,00000000,",
    ]
    for i, cue in enumerate(stack.cues):
        nxt = (i + 1) % n
        prv = (i - 1) % n
        cflags = 0x00007200 if stack.chase else 0x00006000
        lines.append(f"{h(nxt)},{h(prv)},{h(first_s + i)},0000,{h(cflags, 8)},{cue.number:.6f},{q(cue.name)},")
    lines += [
        "00000000,",
        "00000000,0000,0000,0000,0000,",
        "00000000,",
        "0000,00000000,0100,0100,00000000,",
        f"{h(idx - 1, 8)},00000f00,0000,0000,",
        "0000,0000,000a,",
        "0000,0000,0000,0000,0000,0000,0000,0000,0000,0000,",
        '00000000,00000000,0,"",',
        "00000000,00000000,00000000,00000000,",
        '00000000,00000000,00000000,"",0000,0000,0000,0000,00000000,0000000000000000,00000000,00000000,;',
        "",
    ]
    return shwfile.Record("C", lines)


def m_record(page: int, name: str = "") -> shwfile.Record:
    return shwfile.Record("M", [f'M,{h(page)},{q(name)},00000001,0400,0300,0002,000a,"",0000006b,0000,0000;', ""])


def n_record(pb) -> shwfile.Record:
    kind = PLAYBACK_KIND[pb.kind]
    return shwfile.Record("N", [
        f'N,{h(pb.page)},{h(pb.index)},00000000,{h(kind)},{h(pb.ref, 8)},00000000,0000,{q(pb.legend)},"",00000000,00000000,;',
        "",
    ])


# ---------------------------------------------------------------------------
def write_show(show: Show, path: str, template: str = TEMPLATE) -> None:
    tpl = shwfile.load(template)
    keep = [r for r in tpl.records if r.tag in ("V", "T", "Y", "Z", "E1", "Q")]
    out = shwfile.ShowFile(list(tpl.comments), [], "\n")
    out.comments = [
        "\\ MagicQ Show File. Chamsys Ltd.  www.chamsys.co.uk",
        f"\\ Show saved as '{os.path.abspath(path)}'",
        f"\\ Time: {time.strftime('%d %b %Y %H:%M:%S')}, generated by ma3-to-magicq",
        "\\ PC",
        "\\ Serial: ''",
        "",
    ]
    recs: list[shwfile.Record] = []
    for r in keep:
        if r.tag == "T":
            r = shwfile.Record("T", list(r.lines))
            first = r.lines[0]
            rest = first.split('",', 1)[1]
            r.lines[0] = f'T,{q(os.path.abspath(path))},' + rest
        if r.tag == "Q":
            continue  # goes after G, as MagicQ orders it
        recs.append(r)

    heads = show.heads()
    pidx = {hd.key: i + 1 for i, hd in enumerate(heads)}
    for hd in heads:
        recs.append(p_record(pidx[hd.key], hd))
    fixtures = sorted(show.fixtures, key=lambda f: f.abs_chan)
    for fx in fixtures:
        recs.extend(l_records(fx, pidx[fx.head.key]))
    for fx in fixtures:
        recs.append(h_record(fx, fx.head.nchans == 1))

    by_kind: dict[str, list[Palette]] = {"int": [], "pos": [], "col": [], "beam": []}
    for p in show.palettes:
        by_kind[p.kind].append(p)
    for kind in ("int", "pos", "col", "beam"):
        for i, p in enumerate(by_kind[kind]):
            recs.append(f_record(kind, i, p, show))

    for i, g in enumerate(show.groups):
        chans = [show.fixture(fid).abs_chan for fid in g.members if _has(show, fid)]
        recs.append(g_record(i + 1, g.name, chans))

    s_idx = 1
    c_recs = []
    for ci, stack in enumerate(show.stacks):
        for cue in stack.cues:
            recs.append(s_record(s_idx + stack.cues.index(cue), cue, show))
        c_recs.append(c_record(ci + 1, stack, s_idx, show))
        s_idx += len(stack.cues)
    recs.extend(c_recs)

    for r in keep:
        if r.tag == "Q":
            recs.append(r)

    pages = sorted({pb.page for pb in show.playbacks})
    for page in pages:
        recs.append(m_record(page))
        for pb in sorted((p for p in show.playbacks if p.page == page), key=lambda p: p.index):
            recs.append(n_record(pb))

    out.records = recs
    shwfile.save(out, path)


def _has(show: Show, fid: int) -> bool:
    try:
        show.fixture(fid)
        return True
    except KeyError:
        return False
