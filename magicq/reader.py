"""Read a MagicQ .shw into the console-neutral model.Show.

The record layouts are described in docs/shw-format.md. Everything in the
file is keyed by the absolute DMX channel; the reader turns that back into
fixtures (one per MagicQ head), groups, palettes, cue stacks and playbacks.
"""
from __future__ import annotations

import os
import re

from model import (Show, Fixture, HeadDef, Channel, Range, Group, Palette, Cue, CueStack,
                   Playback, KIND_TYPE_WORD)
from . import shwfile
from .shwfile import split_fields, unquote

TYPE_WORD_KIND = {v: k for k, v in KIND_TYPE_WORD.items()}
PALETTE_KIND = {0x9: "int", 0xa: "pos", 0xb: "col", 0xc: "beam"}
PLAYBACK_TYPES = {2: "stack", 5: "group", 6: "palette_col"}


def hx(s: str, default: int = 0) -> int:
    try:
        return int(s, 16)
    except (TypeError, ValueError):
        return default


def kind_of(type_word: int) -> str:
    """MagicQ channel type word -> model channel kind (extra flag bits ignored)."""
    tw = type_word & 0xFFFF
    if tw in TYPE_WORD_KIND:
        return TYPE_WORD_KIND[tw]
    low = tw & 0xFF
    if tw & 0x2000:
        return "ltp8mix"
    if tw & 0x8000:
        return "ctrl"
    return {0x01: "htp8", 0x05: "htp16c", 0x09: "htp16f", 0x02: "htp8", 0x12: "ltp8", 0x22: "ltp8snap",
            0x16: "ltp16c", 0x1a: "ltp16f", 0x36: "pos16c", 0x3a: "pos16f", 0x32: "ltp8"}.get(low, "ltp8")


def xy_to_rgb(x: float, y: float, Y: float = 1.0) -> tuple[float, float, float]:
    X = x * Y / y
    Z = (1 - x - y) * Y / y
    r = 3.2406 * X - 1.5372 * Y - 0.4986 * Z
    g = -0.9689 * X + 1.8758 * Y + 0.0415 * Z
    b = 0.0557 * X - 0.2040 * Y + 1.0570 * Z
    m = max(r, g, b, 1e-6)
    return tuple(max(0.0, min(1.0, v / m)) for v in (r, g, b))


def words(lines: list[str]) -> list[str]:
    out = []
    for l in lines:
        out.extend(split_fields(l))
    return out


class Reader:
    def __init__(self, path: str):
        self.path = path
        self.sf = shwfile.load(path)
        self.show = Show(self._show_name())
        self.notes = self.show.report
        self.heads: dict[int, HeadDef] = {}
        self.chan_owner: dict[int, tuple[int, int]] = {}
        self.stack_index: dict[int, int] = {}   # C id -> index in show.stacks
        self.group_index: dict[int, int] = {}   # G id -> index in show.groups

    def _show_name(self) -> str:
        for c in self.sf.comments:
            m = re.search(r"Show saved as '([^']+)'", c)
            if m:
                return os.path.splitext(os.path.basename(m.group(1).replace("\\", "/")))[0]
        return os.path.splitext(os.path.basename(self.path))[0]

    # ------------------------------------------------------------------ P
    def read_heads(self):
        for rec in self.sf.by_tag("P"):
            try:
                idx, head = self._parse_head(rec)
            except Exception as e:  # noqa: BLE001
                self.notes.append(f"head {rec.header[:2]}: cannot parse personality ({e}), fixtures of this type skipped")
                continue
            self.heads[idx] = head

    def _parse_head(self, rec: shwfile.Record) -> tuple[int, HeadDef]:
        h = rec.header
        idx = hx(h[0])
        manufacturer, mode, model = unquote(h[2]), unquote(h[3]), unquote(h[4])
        body = rec.body()
        meta = body[0]
        nchans, nranges = hx(meta[0]), hx(meta[1])
        pan_deg, tilt_deg = hx(meta[4]), hx(meta[5])
        chans: list[Channel] = []
        li = 1
        for i in range(nchans):
            f = body[li + i]
            chans.append(Channel(unquote(f[0]), hx(f[2]), kind_of(hx(f[1]))))
        li += nchans
        # defaults: a count followed by (chan, value) pairs, possibly wrapped
        need = 1 + 2 * nchans
        got: list[str] = []
        while len(got) < need and li < len(body):
            got.extend(body[li])
            li += 1
        for k in range(nchans):
            ci, val = hx(got[1 + 2 * k]), hx(got[2 + 2 * k])
            if 0 <= ci < nchans:
                chans[ci].default = val & 0xff
        # ranges
        for _ in range(nranges):
            if li >= len(body):
                break
            f = body[li]
            li += 1
            if len(f) < 4:
                continue
            ci = hx(f[0])
            if 0 <= ci < nchans:
                chans[ci].ranges.append(Range(hx(f[2]), hx(f[3]), unquote(f[1])))
        # locate values: the block after the '"",00000000,0000,...' line, one 4-word line per channel
        for j in range(li, len(body)):
            f = body[j]
            if len(f) >= 7 and f[0] == '""' and f[1] == "00000000":
                for k in range(nchans):
                    if j + 1 + k < len(body):
                        g = body[j + 1 + k]
                        if len(g) >= 3:
                            w = hx(g[2])
                            if w & 0x100:
                                chans[k].locate = w & 0xff
                break
        head = HeadDef(manufacturer, model, mode, chans, pan_deg or 540, tilt_deg or 270, source=f"shw P {idx}")
        return idx, head

    # ------------------------------------------------------------------ L
    def read_patch(self):
        by_head: dict[int, list[tuple[int, list[str]]]] = {}
        for rec in self.sf.by_tag("L"):
            h = rec.header
            if len(h) < 11:
                continue
            by_head.setdefault(hx(h[9]), []).append((hx(h[0]), h))
        seen_fids: set[int] = set()
        for hn, rows in sorted(by_head.items()):
            rows.sort()
            firsts = [r for r in rows if hx(r[1][4]) == 0]
            if not firsts:
                self.notes.append(f"head {hn}: no channel with offset 0 in the patch, skipped")
                continue
            if len(firsts) > 1:
                self.notes.append(f"head {hn} {unquote(firsts[0][1][1])}: {len(firsts)} elements share this head number, "
                                  f"patched as separate fixtures {hn}, {hn + 100000}, ...")
            for k, (abs0, h) in enumerate(firsts):
                pidx = hx(h[3])
                head = self.heads.get(pidx)
                if head is None:
                    self.notes.append(f"head {hn} {unquote(h[1])}: personality {pidx} missing, skipped")
                    continue
                fid = hn + 100000 * k
                while fid in seen_fids:
                    fid += 100000
                uni, addr = (abs0 - 1) // 512 + 1, (abs0 - 1) % 512 + 1
                rgb = hx(h[22]) if len(h) > 22 else 0xFFFFFF
                name = unquote(h[1]) or f"Head {hn}"
                if k:
                    name = f"{name} {k + 1}"
                fx = Fixture(fid, name, head, uni, addr, color_rgb=rgb)
                for off in range(head.nchans):
                    self.chan_owner.setdefault(abs0 + off, (fid, off))
                self.show.fixtures.append(fx)
                seen_fids.add(fid)
            if len(rows) != len(firsts) * head.nchans:
                self.notes.append(f"head {hn} {unquote(firsts[0][1][1])}: {len(rows)} patched channels, "
                                  f"personality has {head.nchans} x {len(firsts)}")
        self.show.fixtures.sort(key=lambda f: f.abs_chan)

    # ------------------------------------------------------------------ G
    def read_groups(self):
        for rec in self.sf.by_tag("G"):
            h = rec.header
            n = hx(h[2])
            members = []
            for w in h[3:3 + n]:
                owner = self.chan_owner.get(hx(w))
                if owner and owner[0] not in members:
                    members.append(owner[0])
            if not members:
                self.notes.append(f"group {h[0]} {unquote(h[1])}: no known heads, skipped")
                continue
            self.group_index[hx(h[0])] = len(self.show.groups)
            self.show.groups.append(Group(unquote(h[1]) or f"Group {hx(h[0])}", members))

    # ------------------------------------------------------------------ F
    def read_palettes(self):
        for rec in self.sf.by_tag("F"):
            h = rec.header
            fid_word = hx(h[0])
            kind = PALETTE_KIND.get(fid_word >> 12)
            if kind is None:
                self.notes.append(f"palette {h[0]}: unknown type, skipped")
                continue
            n = hx(h[2])
            body = rec.body()
            flat = words(rec.lines[1:])
            vals: dict[tuple[int, int], int] = {}
            for k in range(n):
                if 3 * k + 2 >= len(flat):
                    break
                ch, v = hx(flat[3 * k]), hx(flat[3 * k + 1])
                owner = self.chan_owner.get(ch)
                if owner:
                    vals[owner] = v & 0xff
            pal = Palette(kind, unquote(h[1]), vals, ref=(kind, fid_word & 0xfff))
            if kind == "col":
                pal.rgb = self._palette_rgb(body)
            if not vals:
                self.notes.append(f"palette {kind} {fid_word & 0xfff} {pal.name}: no values for known heads, kept empty")
            self.show.palettes.append(pal)

    @staticmethod
    def _palette_rgb(body: list[list[str]]):
        """Colour palettes carry CIE x,y on the float line of the tail; convert to sRGB."""
        for f in body:
            if len(f) >= 8 and "." in f[0] and "." in f[1]:
                try:
                    x, y = float(f[0]), float(f[1])
                except ValueError:
                    return None
                if y <= 0:
                    return None
                return xy_to_rgb(x, y)
        return None

    # ------------------------------------------------------------------ S
    def read_cues(self) -> dict[int, Cue]:
        cues: dict[int, Cue] = {}
        for rec in self.sf.by_tag("S"):
            h = rec.header
            sid = hx(h[0])
            n, nfx = hx(h[2]), hx(h[3])
            body = rec.body()
            flat = words(rec.lines[2:])  # skip the 10-word line
            cue = Cue(0.0, unquote(h[1]), fx=nfx)
            for k in range(n):
                if 2 * k + 1 >= len(flat):
                    break
                ch, v = hx(flat[2 * k]), hx(flat[2 * k + 1])
                owner = self.chan_owner.get(ch)
                if owner is None:
                    continue
                cue.values[owner] = v & 0xff
                ref = v >> 8
                if ref:
                    kind = PALETTE_KIND.get((ref >> 12) & 0xf)
                    if kind:
                        cue.refs[owner] = (kind, ref & 0xfff)
            self._cue_times(cue, body)
            cues[sid] = cue
        return cues

    @staticmethod
    def _cue_times(cue: Cue, body: list[list[str]]):
        for f in reversed(body):
            if len(f) == 14 and all(len(w) == 8 for w in f):
                ms = [hx(w) - 1 if hx(w) % 30 == 1 else hx(w) for w in f]
                fades, delays = ms[0:5], ms[5:10]
                cue.fade = fades[0] / 1000.0
                cue.fade_out = fades[1] / 1000.0 if fades[1] != fades[0] else None
                cue.fade_pos = fades[2] / 1000.0 if fades[2] != fades[0] else None
                cue.fade_col = fades[3] / 1000.0 if fades[3] != fades[0] else None
                cue.fade_beam = fades[4] / 1000.0 if fades[4] != fades[0] else None
                cue.delay = delays[0] / 1000.0
                return
        cue.notes.append("no time table found, console defaults used")

    # ------------------------------------------------------------------ C
    def read_stacks(self, cues: dict[int, Cue]):
        for rec in self.sf.by_tag("C"):
            h = rec.header
            cid = hx(h[0])
            n, flags = hx(h[3]), hx(h[4])
            body = rec.body()
            options = body[0] if body else []
            speed_ms = hx(options[0]) if options else 2000
            lines = []
            for f in body[1:1 + n]:
                if len(f) < 7:
                    continue
                lines.append((hx(f[0]), hx(f[1]), hx(f[2]), hx(f[4]), f[5], unquote(f[6])))
            if not lines:
                self.notes.append(f"stack {cid} {unquote(h[1])}: no cues, skipped")
                continue
            # linked list order, starting at the smallest cue number
            def num(f):
                try:
                    return float(f[4])
                except ValueError:
                    return 0.0
            start = min(range(len(lines)), key=lambda i: num(lines[i]))
            order, i = [], start
            while i not in order and 0 <= i < len(lines) and len(order) < len(lines):
                order.append(i)
                i = lines[i][0]
            for i in range(len(lines)):
                if i not in order:
                    order.append(i)
            chase = any(l[3] & 0x1000 for l in lines) or (n > 1 and not (flags & 0x8))
            stack = CueStack(unquote(h[1]) or f"Stack {cid}", [], chase=chase, chase_speed=max(speed_ms, 1) / 1000.0)
            for i in order:
                nxt, prv, sid, cflags, number, cname = lines[i]
                src = cues.get(sid)
                if src is None:
                    self.notes.append(f"stack {cid} {stack.name}: cue store {sid} missing, cue {number} skipped")
                    continue
                cue = Cue(num(lines[i]), cname or src.name, dict(src.values), src.fade, src.fade_out, src.delay,
                          src.fade_pos, src.fade_col, src.fade_beam, notes=list(src.notes), refs=dict(src.refs), fx=src.fx)
                if src.fx:
                    cue.notes.append(f"{src.fx} FX attached in MagicQ, not converted (values are the base look)")
                stack.cues.append(cue)
            if not stack.cues:
                continue
            self.stack_index[cid] = len(self.show.stacks)
            self.show.stacks.append(stack)
            for cue in stack.cues:
                for note in cue.notes:
                    self.notes.append(f"stack {stack.name} cue {cue.number:g}: {note}")

    # ------------------------------------------------------------------ M, N
    def read_playbacks(self):
        skipped: dict[int, int] = {}
        col_pals = [i for i, p in enumerate(self.show.palettes) if p.kind == "col"]
        for rec in self.sf.by_tag("N"):
            h = rec.header
            page, idx, ptype, item = hx(h[0]), hx(h[1]), hx(h[3]), hx(h[4])
            legend = unquote(h[7]) if len(h) > 7 else ""
            kind = PLAYBACK_TYPES.get(ptype)
            ref = None
            if kind == "stack":
                ref = self.stack_index.get(item + 1)
            elif kind == "group":
                ref = self.group_index.get(item + 1, self.group_index.get(item))
            elif kind == "palette_col":
                ref = col_pals[item] if item < len(col_pals) else None
            if kind is None or ref is None:
                skipped[ptype] = skipped.get(ptype, 0) + 1
                continue
            self.show.playbacks.append(Playback(page, idx, kind, ref, legend))
        if skipped:
            self.notes.append("playbacks not converted (type: count): " +
                              ", ".join(f"{t:#x}: {c}" for t, c in sorted(skipped.items())))

    # ------------------------------------------------------------------
    def read(self) -> Show:
        self.read_heads()
        self.read_patch()
        if not self.show.fixtures:
            self.notes.append("no patched heads found")
        self.read_groups()
        self.read_palettes()
        self.read_stacks(self.read_cues())
        self.read_playbacks()
        nfx = len(self.sf.by_tag("W"))
        if nfx:
            self.notes.append(f"{nfx} FX library entries (W) not converted")
        return self.show


def read_shw(path: str) -> Show:
    return Reader(path).read()
