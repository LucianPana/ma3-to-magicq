"""Write a model.Show as a grandMA3 import package.

The package is a folder with show.json, one generated GDTF per head and a
report; ma3/import_show.lua reads it inside grandMA3 and builds the show with
ordinary commands. Nothing here needs onPC, so the package is testable alone.
"""
from __future__ import annotations

import json
import os
from collections import OrderedDict

from model import Show, Palette, family
from . import gdtf, libmatch, attributes

EXEC_FADER_BASE = 200   # MagicQ playback 1 -> executor 201 (first fader row)
EXEC_KEY_BASE = 100     # groups and palettes on playbacks -> 101..


def fixture_patch(fx) -> str:
    return f"{fx.universe}.{fx.address:03d}"


class Package:
    def __init__(self, show: Show, out_dir: str, match_library: bool = True):
        self.show = show
        self.out = out_dir
        self.notes = list(show.report)
        self.match = match_library
        self.gheads: dict[str, gdtf.GHead] = {}
        self.preset_map: dict[tuple[str, int], list[dict]] = {}   # palette ref -> presets built from it
        self.fid_head: dict[int, gdtf.GHead] = {}

    # ----------------------------------------------------------------- heads
    def build_heads(self) -> list[dict]:
        os.makedirs(os.path.join(self.out, "fixturetypes"), exist_ok=True)
        out = []
        for head in self.show.heads():
            fname = gdtf.file_name(head)
            gh = gdtf.write_gdtf(head, os.path.join(self.out, "fixturetypes", fname))
            self.notes.extend(gh.notes)
            self.gheads[head.key] = gh
            cands = libmatch.candidates(head) if self.match else []
            head.candidates = cands
            out.append({
                "key": head.key, "manufacturer": head.manufacturer, "model": head.model, "mode": head.mode,
                "gdtf": fname, "gdtf_name": gdtf._safe(head.model)[:32] or "Head", "mode_name": head.mode or "Mode 1",
                "footprint": head.nchans, "candidates": cands,
                "channels": [{"offset": c.offset + 1, "fine": (c.fine + 1) if c.fine is not None else None,
                              "name": c.source.name, "attr": c.attr, "group": c.group, "bytes": c.bytes,
                              "default": c.source.default} for c in gh.channels],
            })
        for fx in self.show.fixtures:
            self.fid_head[fx.fid] = self.gheads[fx.head.key]
        return out

    # -------------------------------------------------------------- fixtures
    def build_fixtures(self) -> list[dict]:
        return [{"fid": fx.fid, "name": fx.name, "head": fx.head.key, "patch": fixture_patch(fx),
                 "pos": list(fx.pos), "rot": list(fx.rot)} for fx in self.show.fixtures]

    # ---------------------------------------------------------------- values
    def _attr_values(self, fid: int, raw: dict[tuple[int, int], int]) -> dict[str, int]:
        """(fid, offset) -> 8-bit values of one fixture into {MA3 attr: dmx (8 or 16 bit)}."""
        gh = self.fid_head[fid]
        by_off = gh.by_offset()
        out: dict[str, int] = {}
        offs = {off: v for (f, off), v in raw.items() if f == fid}
        for off, v in offs.items():
            gc = by_off.get(off)
            if gc is None:
                continue
            if gc.bytes == 2:
                coarse = offs.get(gc.offset)
                fine = offs.get(gc.fine, 0)
                if coarse is None:
                    continue  # only the fine byte: not a value we can place
                out[gc.attr] = (coarse << 8) | fine
            else:
                out[gc.attr] = v
        return out

    # --------------------------------------------------------------- presets
    def build_presets(self) -> list[dict]:
        counters = {pool: 0 for pool in attributes.GROUP_POOL.values()}
        presets = []
        for pal in self.show.palettes:
            per_pool: dict[int, dict[int, dict[str, int]]] = {}
            fids = sorted({fid for (fid, _) in pal.values})
            for fid in fids:
                if fid not in self.fid_head:
                    continue
                vals = self._attr_values(fid, pal.values)
                for attr, v in vals.items():
                    pool = attributes.GROUP_POOL[attributes.feature_group(attr)]
                    per_pool.setdefault(pool, {}).setdefault(fid, {})[attr] = v
            built = []
            for pool in sorted(per_pool):
                counters[pool] += 1
                p = {"pool": pool, "no": counters[pool], "name": pal.name or f"{pal.kind} {pal.ref[1] if pal.ref else ''}".strip(),
                     "source": list(pal.ref) if pal.ref else None,
                     "values": {str(fid): vals for fid, vals in per_pool[pool].items()}}
                if pal.kind == "col" and pal.rgb:
                    p["rgb"] = [round(c, 4) for c in pal.rgb]
                presets.append(p)
                built.append(p)
            if pal.ref:
                self.preset_map[pal.ref] = built
            if not built:
                self.notes.append(f"palette {pal.kind} {pal.name}: no values for patched fixtures, not written")
        return presets

    # ------------------------------------------------------------- sequences
    def build_sequences(self) -> list[dict]:
        seqs = []
        for si, stack in enumerate(self.show.stacks, start=1):
            cues = []
            for cue in stack.cues:
                fids = sorted({fid for (fid, _) in cue.values})
                values: dict[str, dict[str, int]] = {}
                presets: dict[str, list[str]] = {}
                for fid in fids:
                    if fid not in self.fid_head:
                        continue
                    hard = self._attr_values(fid, cue.values)
                    gh = self.fid_head[fid]
                    by_off = gh.by_offset()
                    # palette references: use the preset when it holds the same value for this fixture
                    used: set[str] = set()
                    for (f, off), ref in cue.refs.items():
                        if f != fid or off not in by_off:
                            continue
                        gc = by_off[off]
                        if gc.attr in used or gc.attr not in hard:
                            continue
                        for p in self.preset_map.get(ref, []):
                            pv = p["values"].get(str(fid), {})
                            if pv.get(gc.attr) == hard[gc.attr]:
                                key = f"{p['pool']}.{p['no']}"
                                presets.setdefault(str(fid), [])
                                if key not in presets[str(fid)]:
                                    presets[str(fid)].append(key)
                                used.add(gc.attr)
                                break
                    rest = {a: v for a, v in hard.items() if a not in used}
                    if rest:
                        values[str(fid)] = rest
                c = {"no": cue.number, "name": cue.name, "fade": cue.fade, "delay": cue.delay,
                     "fade_out": cue.fade_out, "fade_pos": cue.fade_pos, "fade_col": cue.fade_col, "fade_beam": cue.fade_beam,
                     "values": values, "presets": presets}
                if cue.follow is not None:
                    c["follow"] = cue.follow
                if cue.timecode is not None:
                    c["timecode"] = cue.timecode
                if cue.fx:
                    c["fx_dropped"] = cue.fx
                cues.append(c)
            seqs.append({"no": si, "name": stack.name, "chase": stack.chase, "chase_speed": stack.chase_speed,
                         "tracking": stack.tracking, "cues": cues})
        return seqs

    # ------------------------------------------------------------- executors
    def build_executors(self) -> list[dict]:
        out = []
        used: set[tuple[int, int]] = set()
        skipped = 0
        for pb in self.show.playbacks:
            if pb.kind == "stack":
                ex = EXEC_FADER_BASE + pb.index + 1
                if pb.index >= 15 or (pb.page, ex) in used:
                    skipped += 1
                    continue
                used.add((pb.page, ex))
                out.append({"page": pb.page, "exec": ex, "sequence": pb.ref + 1, "legend": pb.legend})
            else:
                ex = EXEC_KEY_BASE + pb.index + 1
                if pb.index >= 15 or (pb.page, ex) in used:
                    skipped += 1
                    continue
                used.add((pb.page, ex))
                if pb.kind == "group":
                    out.append({"page": pb.page, "exec": ex, "group": pb.ref + 1, "legend": pb.legend})
                else:
                    pal = self.show.palettes[pb.ref]
                    built = self.preset_map.get(pal.ref or ("", -1), [])
                    if built:
                        out.append({"page": pb.page, "exec": ex, "preset": f"{built[0]['pool']}.{built[0]['no']}", "legend": pb.legend})
        if skipped:
            self.notes.append(f"{skipped} playbacks beyond executor 15 of a page or on taken slots not assigned")
        return out

    # ------------------------------------------------------------------
    def write(self) -> dict:
        os.makedirs(self.out, exist_ok=True)
        data = OrderedDict()
        data["name"] = self.show.name
        data["generator"] = "ma3-to-magicq (MagicQ to grandMA3)"
        data["heads"] = self.build_heads()
        data["fixtures"] = self.build_fixtures()
        data["groups"] = [{"no": i + 1, "name": g.name, "fids": g.members} for i, g in enumerate(self.show.groups)]
        data["presets"] = self.build_presets()
        data["sequences"] = self.build_sequences()
        data["executors"] = self.build_executors()
        data["notes"] = self.notes
        with open(os.path.join(self.out, "show.json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
        self.write_report(data)
        return data

    def write_report(self, data: dict):
        lines = [f"# Conversion report: {self.show.name} (MagicQ to grandMA3)", "",
                 f"Import package written to `{os.path.abspath(self.out)}`.", "",
                 "## What was converted", "",
                 f"- {len(data['fixtures'])} fixtures, {len(data['heads'])} fixture types "
                 f"({sum(1 for h in data['heads'] if h['candidates'])} with grandMA3 library candidates, checked at import)",
                 f"- {len(data['groups'])} groups",
                 f"- {len(data['presets'])} presets from {len(self.show.palettes)} MagicQ palettes "
                 "(a palette becomes one preset per grandMA3 feature group it touches)",
                 f"- {len(data['sequences'])} sequences with {sum(len(s['cues']) for s in data['sequences'])} cues",
                 f"- {len(data['executors'])} executor assignments", "",
                 "## How to import", "",
                 "1. Start grandMA3 onPC with a new, empty show.",
                 "2. In the command line type (or run `scripts/ma3_import.py` with OSC enabled):", "",
                 f"       Lua \"dofile('<this repository>/ma3/import_show.lua')('{os.path.abspath(self.out)}')\"", "",
                 "3. Save the show. Read the notes below and check what they point at.", "",
                 "## Check in grandMA3", "",
                 "- Fixture types: a library match replaced the generated type only when every channel lined up; "
                 "the rest use generated types with named ranges but no wheel images or physical values.",
                 "- Cue values are stored as exact DMX values (Decimal readout), so looks match the MagicQ output; "
                 "presets are selective and referenced from cues where MagicQ referenced the palette.",
                 "- MagicQ FX, macros and timecode triggers were not converted.", ""]
        if self.notes:
            lines += ["## Notes", ""] + [f"- {n}" for n in self.notes] + [""]
        with open(os.path.join(self.out, "report.md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))


def write_package(show: Show, out_dir: str, match_library: bool = True) -> dict:
    return Package(show, out_dir, match_library).write()
