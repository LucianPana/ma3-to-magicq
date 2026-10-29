"""Turn a folder written by ma3/dump_show.lua into a model.Show."""
from __future__ import annotations

import json
import os
import re

from model import Show, Fixture, Group, Palette, Cue, CueStack, Playback, HeadDef, family
from . import fixturetypes

POOL_KIND = {"dimmer": "int", "position": "pos", "color": "col", "colour": "col"}
SKIP_TYPES = ("grouping", "universal", "marker", "bitmap control", "bitmap_control")


def parse_patch(s: str | None) -> tuple[int, int] | None:
    """'1.001', '1.1', '2.513'(abs) or '513' -> (universe, address)."""
    if not s:
        return None
    s = str(s).strip()
    m = re.match(r"^(\d+)\.(\d+)$", s)
    if m:
        u, a = int(m.group(1)), int(m.group(2))
        if 1 <= a <= 512 and u >= 1:
            return u, a
        n = (u - 1) * 512 + a
        return (n - 1) // 512 + 1, (n - 1) % 512 + 1
    if s.isdigit():
        n = int(s)
        if n < 1:
            return None
        return (n - 1) // 512 + 1, (n - 1) % 512 + 1
    return None


def _num(v, default=None):
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


class Reader:
    def __init__(self, folder: str):
        self.folder = folder
        with open(os.path.join(folder, "dump.json"), encoding="utf-8") as fh:
            self.d = json.load(fh)
        self.show = Show(self.d.get("show") or os.path.basename(folder.rstrip("/")))
        self.notes = self.show.report
        self.heads: dict[str, HeadDef] = {}
        self.chan_owner: dict[int, tuple[int, int]] = {}  # abs chan -> (fid, offset)
        self.baseline: dict[int, int] = {}

    # ---------------------------------------------------------------- heads
    def head_for(self, ftname: str, mode: str) -> HeadDef | None:
        key = f"{ftname}|{mode}"
        if key in self.heads:
            return self.heads[key]
        folder = os.path.join(self.folder, "fixturetypes")
        path = fixturetypes.find_fixture_file(folder, ftname)
        if path is None:
            self.notes.append(f"fixture type {ftname}: no exported file in {folder}, fixtures skipped")
            self.heads[key] = None
            return None
        try:
            head, notes = fixturetypes.head_from_xml(path, mode)
        except Exception as e:  # noqa: BLE001
            self.notes.append(f"fixture type {ftname}: cannot read {os.path.basename(path)}: {e}")
            self.heads[key] = None
            return None
        self.notes.extend(notes)
        self.heads[key] = head
        return head

    # -------------------------------------------------------------- fixtures
    def read_fixtures(self):
        seen_fids: set[int] = set()
        for row in self.d.get("fixtures", []):
            ft = str(row.get("fixturetype") or "")
            if not ft or any(s in ft.lower() for s in SKIP_TYPES):
                continue
            pa = parse_patch(row.get("patch") or row.get("address"))
            if pa is None:
                continue  # unpatched or a child cell
            fid = row.get("fid")
            if fid in (None, "", 0) or int(fid) in seen_fids:
                continue  # sub fixtures share the parent's id or have none
            head = self.head_for(ft, str(row.get("mode") or ""))
            if head is None:
                continue
            fid = int(fid)
            fx = Fixture(fid, str(row.get("name") or f"Fix {fid}"), head, pa[0], pa[1],
                         pos=(_num(row.get("posx"), 0.0), _num(row.get("posy"), 0.0), _num(row.get("posz"), 0.0)),
                         rot=(_num(row.get("rotx"), 0.0), _num(row.get("roty"), 0.0), _num(row.get("rotz"), 0.0)))
            base = fx.abs_chan
            clash = [c for c in range(base, base + head.nchans) if c in self.chan_owner]
            if clash:
                self.notes.append(f"fixture {fid} {fx.name}: DMX {pa[0]}.{pa[1]} overlaps an already patched head, skipped")
                continue
            for off in range(head.nchans):
                self.chan_owner[base + off] = (fid, off)
            self.show.fixtures.append(fx)
            seen_fids.add(fid)
        self.show.fixtures.sort(key=lambda f: f.abs_chan)

    # ------------------------------------------------------------- snapshots
    def _snapshot(self, snap: dict | None) -> dict[int, int]:
        """{'1': [512 values], ...} -> {abs chan: value} for patched channels only."""
        out: dict[int, int] = {}
        if not snap:
            return out
        for u, row in snap.items():
            try:
                uni = int(u)
            except ValueError:
                continue
            for i, v in enumerate(row or []):
                ch = (uni - 1) * 512 + i + 1
                if ch in self.chan_owner:
                    out[ch] = int(v) & 0xff
        return out

    def _values(self, snap: dict[int, int], ref: dict[int, int] | None = None) -> dict[tuple[int, int], int]:
        out: dict[tuple[int, int], int] = {}
        for ch, v in snap.items():
            b = self.baseline.get(ch)
            p = ref.get(ch) if ref is not None else None
            if v != b or (p is not None and v != p):
                out[self.chan_owner[ch]] = v
        return out

    def read_baseline(self):
        self.baseline = self._snapshot(self.d.get("baseline"))
        if not self.baseline:
            self.notes.append("no baseline DMX snapshot in the dump: cues and palettes carry every channel")

    # ---------------------------------------------------------------- groups
    def read_groups(self):
        known = {f.fid for f in self.show.fixtures}
        for g in self.d.get("groups", []):
            members = [int(m) for m in (g.get("members") or []) if str(m).lstrip("-").isdigit() and int(m) in known]
            if not members:
                self.notes.append(f"group {g.get('no')} {g.get('name')}: no patched members found, skipped")
                continue
            self.show.groups.append(Group(str(g.get("name") or f"Group {g.get('no')}"), members))

    # -------------------------------------------------------------- palettes
    def read_presets(self):
        for pool in self.d.get("presetpools", []):
            pname = str(pool.get("name") or "").lower()
            kind = POOL_KIND.get(pname, "beam")
            for p in pool.get("presets", []):
                snap = self._snapshot(p.get("dmx"))
                if not snap:
                    self.notes.append(f"preset {pool.get('name')} {p.get('no')} {p.get('name')}: no DMX snapshot, skipped")
                    continue
                vals = self._values(snap)
                # keep only the channels of this palette's family
                fam_vals = {}
                for (fid, off), v in vals.items():
                    ch = self.show.fixture(fid).head.channels[off]
                    if family(ch.attr) == kind or (kind == "beam" and family(ch.attr) not in ("int", "pos", "col")):
                        fam_vals[(fid, off)] = v
                if not fam_vals:
                    continue
                pal = Palette(kind, str(p.get("name") or f"{pool.get('name')} {p.get('no')}"), fam_vals)
                if kind == "col":
                    pal.rgb = self._guess_rgb(fam_vals)
                self.show.palettes.append(pal)

    def _guess_rgb(self, vals) -> tuple[float, float, float] | None:
        acc = {16: [], 17: [], 18: []}
        for (fid, off), v in vals.items():
            ch = self.show.fixture(fid).head.channels[off]
            if ch.attr in acc and not ch.kind.endswith("f"):
                acc[ch.attr].append(v / 255.0)
        if any(acc.values()):
            avg = lambda l: sum(l) / len(l) if l else 0.0
            r, g, b = avg(acc[16]), avg(acc[17]), avg(acc[18])
            # CMY heads invert
            if any(self.show.fixture(fid).head.channels[off].name.lower().startswith(("cyan", "magenta", "yellow")) for (fid, off) in vals):
                r, g, b = 1 - r, 1 - g, 1 - b
            return (r, g, b)
        return None

    # ------------------------------------------------------------- sequences
    def read_sequences(self):
        for s in self.d.get("sequences", []):
            cues = []
            prev: dict[int, int] | None = None
            for c in s.get("cues", []):
                snap = self._snapshot(c.get("dmx"))
                if not snap:
                    self.notes.append(f"sequence {s.get('no')} cue {c.get('no')}: no DMX snapshot, cue written empty")
                vals = self._values(snap, prev) if snap else {}
                prev = snap or prev
                part0 = (c.get("parts") or [{}])[0]
                fade = _num(c.get("fadein"), None)
                if fade is None:
                    fade = _num(part0.get("fadein"), 0.0)
                delay = _num(c.get("delayin"), None)
                if delay is None:
                    delay = _num(part0.get("delayin"), 0.0)
                fade_out = _num(c.get("fadeout"), None)
                cue = Cue(_num(c.get("no"), len(cues) + 1.0), str(c.get("name") or ""), vals, fade=fade or 0.0,
                          fade_out=fade_out, delay=delay or 0.0)
                trig = str(c.get("trigtype") or "").lower()
                if trig in ("follow", "time"):
                    cue.follow = _num(c.get("trigtime"), 0.0)
                    cue.notes.append(f"trigger {trig} {cue.follow}s: set the Wait/Follow by hand")
                elif trig == "timecode":
                    cue.timecode = _num(c.get("trigtime"), None)
                    cue.notes.append("timecode trigger: set the TC time by hand")
                cues.append(cue)
            if not cues:
                continue
            self.show.stacks.append(CueStack(str(s.get("name") or f"Seq {s.get('no')}"), cues))
            for cue in cues:
                for n in cue.notes:
                    self.notes.append(f"stack {s.get('name')} cue {cue.number:g}: {n}")

    # ------------------------------------------------------------- playbacks
    def read_pages(self):
        seq_index = {str(s.get("no")): i for i, s in enumerate(self.d.get("sequences", []))}
        stack_index = {}
        for i, s in enumerate(self.d.get("sequences", [])):
            if s.get("cues"):
                stack_index[str(s.get("no"))] = len(stack_index)
        pages = self.d.get("pages") or []
        used: set[tuple[int, int]] = set()
        for pg in pages:
            try:
                page = int(pg.get("no") or 1)
            except ValueError:
                page = 1
            execs = sorted((e for e in pg.get("executors", []) if e.get("seq") is not None), key=lambda e: int(e.get("no") or 0))
            slot = 0
            for e in execs:
                si = stack_index.get(str(e.get("seq")))
                if si is None:
                    continue
                mq_page = page + slot // 10
                idx = slot % 10
                if (mq_page, idx) in used:
                    slot += 1
                    continue
                used.add((mq_page, idx))
                self.show.playbacks.append(Playback(mq_page, idx, "stack", si, str(e.get("name") or self.show.stacks[si].name)[:12]))
                slot += 1
        if not self.show.playbacks:
            # no page information: lay the stacks out ten per page
            for i, st in enumerate(self.show.stacks):
                self.show.playbacks.append(Playback(i // 10 + 1, i % 10, "stack", i, st.name[:12]))

    def read(self) -> Show:
        self.read_fixtures()
        if not self.show.fixtures:
            self.notes.append("no patched fixtures could be converted")
        self.read_baseline()
        self.read_groups()
        self.read_presets()
        self.read_sequences()
        self.read_pages()
        return self.show


def read_dump(folder: str) -> Show:
    return Reader(folder).read()
