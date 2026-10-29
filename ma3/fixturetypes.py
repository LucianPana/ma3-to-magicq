"""Read fixture types (grandMA3 XML exports or GDTF description.xml) into model.HeadDef.

Both formats share the GDTF shape: DMXMode > DMXChannels > DMXChannel >
LogicalChannel > ChannelFunction > ChannelSet. They differ in how offsets and
DMX values are written:

- grandMA3 XML: DMXChannel Coarse="1" Fine="2", values as 24-bit hex ("7F7F7F").
- GDTF:         DMXChannel Offset="1,2", values as "value/bytes" ("32768/2").
"""
from __future__ import annotations

import csv
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from model import HeadDef, Channel, Range, ATTR, family, INTENSITY_ATTRS, POSITION_ATTRS, COLOUR_ATTRS

HERE = os.path.dirname(os.path.abspath(__file__))
MAP_CSV = os.path.join(HERE, "..", "data", "gdtf_to_magicq.csv")

SPARES = {
    "int": [1],
    "pos": [46, 47, 48, 49, 50, 51],
    "col": [61, 62, 26, 24, 25, 23],
    "beam": [34, 35, 36, 37, 38, 39, 41, 42, 43, 44, 45, 15, 30, 33, 29],
}


@dataclass
class AttrMap:
    attr: int
    kind: str


def load_map(path: str = MAP_CSV) -> dict[str, AttrMap]:
    out: dict[str, AttrMap] = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            out[row["gdtf_attribute"]] = AttrMap(int(row["magicq_attr"]), row["kind"])
    return out


_MAP: dict[str, AttrMap] | None = None


def attr_map() -> dict[str, AttrMap]:
    global _MAP
    if _MAP is None:
        _MAP = load_map()
    return _MAP


def guess_attr(name: str, notes: list[str]) -> AttrMap:
    """Map a GDTF attribute name to MagicQ, with family-based fallbacks."""
    m = attr_map()
    if name in m:
        return m[name]
    base = re.sub(r"\d+$", "", name)
    for cand in (base, base + "1", name.split("(")[0]):
        if cand in m:
            return m[cand]
    low = name.lower()
    if "dim" in low or "intens" in low:
        return AttrMap(0, "htp8")
    if low.startswith("pan"):
        return AttrMap(4, "pos16c")
    if low.startswith("tilt"):
        return AttrMap(5, "pos16c")
    if "color" in low or "colour" in low:
        notes.append(f"attribute {name}: no mapping, treated as a colour control")
        return AttrMap(61, "ltp8")
    if "gobo" in low:
        notes.append(f"attribute {name}: no mapping, treated as a gobo")
        return AttrMap(28, "ltp8snap")
    if any(k in low for k in ("reset", "lamp", "control", "mode", "macro", "fan", "display")):
        notes.append(f"attribute {name}: no mapping, treated as a control channel")
        return AttrMap(20, "ctrl")
    notes.append(f"attribute {name}: no mapping, treated as a generic beam control")
    return AttrMap(34, "ltp8")


# ---------------------------------------------------------------------------
# value parsing
# ---------------------------------------------------------------------------
def dmx8(value: str | None, default: int = 0) -> int:
    """Return the 8-bit (coarse) value of a GDTF or MA3 DMX value string."""
    if not value:
        return default
    value = value.strip()
    if "/" in value:
        n, b = value.split("/")
        n, b = int(float(n)), int(b)
        return max(0, min(255, n >> (8 * (b - 1)))) if b > 1 else max(0, min(255, n))
    if re.fullmatch(r"[0-9A-Fa-f]{6}", value) or re.fullmatch(r"[0-9A-Fa-f]{2}", value):
        return int(value[:2], 16)
    try:
        v = int(float(value))
        return max(0, min(255, v))
    except ValueError:
        return default


def strip_ns(tag: str) -> str:
    return tag.split("}")[-1]


def _children(el, name):
    return [c for c in el if strip_ns(c.tag) == name]


def _find(el, name):
    for c in el.iter():
        if strip_ns(c.tag) == name:
            return c
    return None


# ---------------------------------------------------------------------------
def parse_xml(path: str) -> ET.Element:
    if path.lower().endswith(".gdtf"):
        with zipfile.ZipFile(path) as z:
            with z.open("description.xml") as fh:
                return ET.fromstring(fh.read())
    with open(path, "rb") as fh:
        data = fh.read()
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    return ET.fromstring(data)


def head_from_xml(path: str, mode_name: str | None = None) -> tuple[HeadDef, list[str]]:
    root = parse_xml(path)
    ft = _find(root, "FixtureType")
    if ft is None:
        raise ValueError(f"no FixtureType in {path}")
    manufacturer = ft.get("Manufacturer", "") or "Unknown"
    model = ft.get("Name", "") or os.path.splitext(os.path.basename(path))[0]
    modes = _children(_find(ft, "DMXModes") or ft, "DMXMode")
    if not modes:
        raise ValueError(f"no DMXMode in {path}")
    mode = None
    if mode_name:
        for m in modes:
            if m.get("Name", "").strip().lower() == mode_name.strip().lower():
                mode = m
                break
    if mode is None:
        mode = modes[0]
    return head_from_mode(ft, mode, manufacturer, model, path)


def head_from_mode(ft, mode, manufacturer: str, model: str, source: str) -> tuple[HeadDef, list[str]]:
    notes: list[str] = []
    slots: dict[int, Channel] = {}
    used_attrs: set[int] = set()
    pan_deg, tilt_deg = 540, 270

    for dch in _children(_find(mode, "DMXChannels") or mode, "DMXChannel"):
        if dch.get("Offset"):
            offsets = [int(x) for x in dch.get("Offset").split(",") if x.strip()]
        else:
            offsets = [int(dch.get(k)) for k in ("Coarse", "Fine", "Ultra") if dch.get(k) not in (None, "", "None")]
        if not offsets:
            continue  # virtual channel
        lch = _children(dch, "LogicalChannel")
        if not lch:
            continue
        lchan = lch[0]
        funcs = _children(lchan, "ChannelFunction")
        attr_name = (funcs[0].get("Attribute") if funcs else None) or lchan.get("Attribute") or "NoFeature"
        attr_name = attr_name.split(".")[-1]  # MA3 may write "Attributes.Dimmer"
        am = guess_attr(attr_name, notes)
        attr = am.attr
        if attr in used_attrs:
            fam = family(attr)
            spare = next((s for s in SPARES[fam] if s not in used_attrs), None)
            if spare is None:
                notes.append(f"{model}: no free MagicQ attribute for {attr_name}, channel dropped")
                continue
            notes.append(f"{model}: {attr_name} mapped to MagicQ attribute {spare} ({fam} spare)")
            attr = spare
        used_attrs.add(attr)

        default = dmx8(dch.get("Default") or (funcs[0].get("Default") if funcs else None))
        ranges: list[Range] = []
        for fn in funcs:
            sets = _children(fn, "ChannelSet")
            named = [(dmx8(s.get("DMXFrom") or fn.get("DMXFrom") or "0"), s.get("Name", "")) for s in sets]
            for i, (lo, name) in enumerate(named):
                if not name:
                    continue
                hi = (named[i + 1][0] - 1) if i + 1 < len(named) else dmx8(fn.get("DMXTo"), 255)
                if hi < lo:
                    hi = lo
                ranges.append(Range(lo, hi, name[:15]))
            if attr_name in ("Pan", "Tilt"):
                try:
                    span = abs(float(fn.get("PhysicalTo", "0")) - float(fn.get("PhysicalFrom", "0")))
                    if span > 0:
                        if attr_name == "Pan":
                            pan_deg = int(round(span))
                        else:
                            tilt_deg = int(round(span))
                except ValueError:
                    pass
        if not ranges and funcs and len(funcs) > 1:
            for fn in funcs:
                if fn.get("Name"):
                    ranges.append(Range(dmx8(fn.get("DMXFrom")), dmx8(fn.get("DMXTo"), 255), fn.get("Name")[:15]))

        kind = am.kind
        if len(offsets) >= 2:
            if kind.startswith("htp"):
                kind = "htp16c"
            elif kind.startswith("pos") or attr in (4, 5):
                kind = "pos16c"
            else:
                kind = "ltp16c"
        else:
            # a single DMX slot can never be a 16-bit coarse channel
            kind = {"pos16c": "ltp8", "ltp16c": "ltp8", "htp16c": "htp8"}.get(kind, kind)
            if attr in (4, 5):
                kind = "ltp8"
        pretty = (funcs[0].get("Name") if funcs and funcs[0].get("Name") else attr_name)[:15]
        slots[offsets[0]] = Channel(pretty, attr, kind, default, ranges=ranges[:60])
        if len(offsets) >= 2:
            fine_kind = {"htp16c": "htp16f", "pos16c": "pos16f", "ltp16c": "ltp16f"}[kind]
            slots[offsets[1]] = Channel((pretty[:13] + " F"), attr, fine_kind, 0)
        for extra in offsets[2:]:
            slots[extra] = Channel((pretty[:12] + " UF"), attr, fine_kind, 0)

    if not slots:
        raise ValueError(f"{model}: mode {mode.get('Name')} has no DMX channels")
    nch = max(slots)
    channels = []
    gaps = 0
    for i in range(1, nch + 1):
        ch = slots.get(i)
        if ch is None:
            gaps += 1
            ch = Channel(f"Unused {i}", -1, "ltp8", 0)
        channels.append(ch)
    if gaps:
        notes.append(f"{model} ({mode.get('Name')}): {gaps} DMX slots are not described at mode level "
                     f"(pixel cells or geometry references); they are patched as placeholders")
    # placeholders get the attribute numbers still free, then the reserved number 63
    free = [a for a in range(63, -1, -1) if a not in used_attrs and a not in (0, 4, 5)]
    for ch in channels:
        if ch.attr == -1:
            ch.attr = free.pop() if free else 63
    head = HeadDef(manufacturer, model, mode.get("Name", "") or "", channels, pan_deg, tilt_deg, source=source)
    return head, notes


def find_fixture_file(folder: str, name: str) -> str | None:
    """Find the exported fixture type file whose name matches an MA3 fixture type name."""
    if not os.path.isdir(folder):
        return None
    want = re.sub(r"[^a-z0-9]", "", name.lower())
    best = None
    for fn in os.listdir(folder):
        stem = re.sub(r"[^a-z0-9]", "", os.path.splitext(fn)[0].lower())
        if stem == want or stem.endswith(want) or want.endswith(stem):
            if fn.lower().endswith((".xml", ".gdtf")):
                if best is None or fn.lower().endswith(".xml"):
                    best = os.path.join(folder, fn)
    return best
