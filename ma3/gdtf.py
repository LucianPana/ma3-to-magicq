"""Generate a GDTF fixture type from a MagicQ head definition.

A head read from a .shw carries channel names, MagicQ attribute numbers,
8/16-bit kinds, defaults and named ranges. That is enough for a plain GDTF
(DataVersion 1.2) that grandMA3 imports: exact channel layout, named channel
sets for the ranges, pan and tilt in degrees, generic physical values for
everything else. No wheels, no 3D model beyond the GDTF primitives.
"""
from __future__ import annotations

import io
import re
import uuid
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from model import HeadDef, Channel
from . import attributes

NS = uuid.UUID("3b4a7f0e-5c21-4d6a-9a4e-ma3tomagicq".replace("ma3tomagicq", "0a1b2c3d4e5f"))
IDENTITY = "{1.000000,0.000000,0.000000,0.000000}{0.000000,1.000000,0.000000,0.000000}{0.000000,0.000000,1.000000,0.000000}{0,0,0,1}"


@dataclass
class GChannel:
    """One GDTF DMX channel: a MagicQ channel plus, for 16-bit, its fine channel."""
    offset: int                 # MagicQ channel index of the coarse byte (0-based)
    fine: int | None            # index of the fine byte, or None
    attr: str                   # grandMA3 attribute name
    group: str                  # feature group
    source: Channel
    custom: bool = False        # name is not a standard attribute (duplicate in the head)

    @property
    def bytes(self) -> int:
        return 2 if self.fine is not None else 1

    @property
    def max(self) -> int:
        return 65535 if self.bytes == 2 else 255


@dataclass
class GHead:
    head: HeadDef
    channels: list[GChannel] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def is_mover(self) -> bool:
        return any(c.attr in ("Pan", "Tilt") for c in self.channels)

    def by_offset(self) -> dict[int, GChannel]:
        """MagicQ channel index -> GDTF channel owning it (coarse and fine both map)."""
        out = {}
        for c in self.channels:
            out[c.offset] = c
            if c.fine is not None:
                out[c.fine] = c
        return out


def plan(head: HeadDef) -> GHead:
    """Decide the GDTF channel list of a head: pair coarse and fine, map names, keep names unique."""
    gh = GHead(head)
    chans = head.channels
    used_fine: set[int] = set()
    names: dict[str, int] = {}
    for i, ch in enumerate(chans):
        if i in used_fine:
            continue
        if ch.kind.endswith("f") and ch.kind != "htp8":
            # a fine byte without a coarse one before it: keep it as an 8-bit channel of its own
            pass
        fine = None
        if ch.kind.endswith("c"):
            for j in range(i + 1, len(chans)):
                if chans[j].attr == ch.attr and chans[j].kind.endswith("f") and j not in used_fine:
                    fine = j
                    used_fine.add(j)
                    break
        name = attributes.ma3_name(ch.attr, ch.name)
        group = attributes.feature_group(name)
        custom = False
        if name in names:
            alt = next((s for s in attributes.SPARES.get(group, []) if s not in names), None)
            if alt is None:
                alt = f"{name}_{names[name] + 1}"
                custom = True
            gh.notes.append(f"{head.key}: channel {i + 1} '{ch.name}' also maps to {name}, written as {alt}")
            names[name] += 1
            name = alt
        names.setdefault(name, 0)
        gh.channels.append(GChannel(i, fine, name, group, ch, custom))
    return gh


def _frac(v: int, nbytes: int) -> str:
    return f"{v}/{nbytes}"


def _ranges(ch: Channel, nbytes: int):
    """Sorted, non-overlapping named ranges scaled to the channel's byte count."""
    scale = 256 if nbytes == 2 else 1
    out = []
    last_hi = -1
    for r in sorted(ch.ranges, key=lambda r: (r.lo, r.hi)):
        lo, hi = r.lo, r.hi
        if hi < lo or lo <= last_hi:
            continue
        out.append((lo * scale, hi * scale + (scale - 1), r.name))
        last_hi = hi
    return out


def _physical(gc: GChannel, head: HeadDef) -> tuple[float, float, str]:
    if gc.attr == "Pan":
        return -head.pan_deg / 2.0, head.pan_deg / 2.0, "Angle"
    if gc.attr == "Tilt":
        return -head.tilt_deg / 2.0, head.tilt_deg / 2.0, "Angle"
    if gc.group == "Dimmer":
        return 0.0, 1.0, "LuminousIntensity"
    return 0.0, 1.0, "None"


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9 _.\-]", "_", s).strip() or "X"


def fixture_type_id(head: HeadDef) -> str:
    return str(uuid.uuid5(NS, "ma3-to-magicq:" + head.key)).upper()


def file_name(head: HeadDef) -> str:
    return _safe(f"{head.manufacturer}@{head.model}_{head.mode}".strip("_")) + ".gdtf"


def description_xml(gh: GHead) -> str:
    head = gh.head
    mover = gh.is_mover
    root = ET.Element("GDTF", DataVersion="1.2")
    ft = ET.SubElement(root, "FixtureType", Name=_safe(head.model)[:32] or "Head", ShortName=_safe(head.model)[:8],
                       LongName=f"{head.manufacturer} {head.model}".strip(), Manufacturer=head.manufacturer or "Generic",
                       Description=f"Generated by ma3-to-magicq from the MagicQ head {head.key}",
                       FixtureTypeID=fixture_type_id(head), Thumbnail="", RefFT="", CanHaveChildren="No")
    ad = ET.SubElement(ft, "AttributeDefinitions")
    ag = ET.SubElement(ad, "ActivationGroups")
    groups_used = {}
    for gc in gh.channels:
        groups_used.setdefault(gc.group, set()).add(attributes.feature(gc.attr, gc.group).split(".")[1])
    if mover:
        ET.SubElement(ag, "ActivationGroup", Name="PanTilt")
    if any(gc.attr.startswith("ColorRGB") for gc in gh.channels):
        ET.SubElement(ag, "ActivationGroup", Name="ColorRGB")
    fgs = ET.SubElement(ad, "FeatureGroups")
    for g, feats in groups_used.items():
        fg = ET.SubElement(fgs, "FeatureGroup", Name=g, Pretty=g)
        for f in sorted(feats):
            ET.SubElement(fg, "Feature", Name=f)
    attrs = ET.SubElement(ad, "Attributes")
    seen = set()
    for gc in gh.channels:
        if gc.attr in seen:
            continue
        seen.add(gc.attr)
        lo, hi, unit = _physical(gc, head)
        a = ET.SubElement(attrs, "Attribute", Name=gc.attr, Pretty=gc.source.name[:16] or gc.attr,
                          Feature=attributes.feature(gc.attr, gc.group), PhysicalUnit=unit)
        if gc.attr in ("Pan", "Tilt"):
            a.set("ActivationGroup", "PanTilt")
        elif gc.attr.startswith("ColorRGB"):
            a.set("ActivationGroup", "ColorRGB")
            a.set("Color", {"R": "0.640000,0.330000,21.260000", "G": "0.300000,0.600000,71.520000", "B": "0.150000,0.060000,7.220000"}
                  .get(gc.attr[-1], "0.312700,0.329000,100.000000"))
    ET.SubElement(ft, "Wheels")
    pd = ET.SubElement(ft, "PhysicalDescriptions")
    ET.SubElement(pd, "Emitters")
    ET.SubElement(pd, "Filters")
    ET.SubElement(pd, "ColorSpace", Name="Default", Mode="sRGB")
    ET.SubElement(pd, "DMXProfiles")
    ET.SubElement(pd, "CRIs")
    ET.SubElement(pd, "Connectors")
    ET.SubElement(pd, "Properties")
    models = ET.SubElement(ft, "Models")
    geos = ET.SubElement(ft, "Geometries")
    if mover:
        for name, prim, l, w, h in (("BASE", "Base1_1", 0.3, 0.3, 0.1), ("YOKE", "Yoke", 0.3, 0.3, 0.3), ("HEAD", "Head", 0.2, 0.2, 0.3),
                                    ("BEAM", "Cylinder", 0.1, 0.1, 0.02)):
            ET.SubElement(models, "Model", Name=name, Length=f"{l:.6f}", Width=f"{w:.6f}", Height=f"{h:.6f}", PrimitiveType=prim, File="")
        base = ET.SubElement(geos, "Geometry", Name="Base", Position=IDENTITY, Model="BASE")
        yoke = ET.SubElement(base, "Axis", Name="Yoke", Position=IDENTITY, Model="YOKE")
        headg = ET.SubElement(yoke, "Axis", Name="Head", Position=IDENTITY, Model="HEAD")
        ET.SubElement(headg, "Beam", Name="Beam", Position=IDENTITY, Model="BEAM", LampType="Discharge", PowerConsumption="500.000000",
                      LuminousFlux="10000.000000", ColorTemperature="6500.000000", BeamAngle="15.000000", FieldAngle="20.000000",
                      BeamRadius="0.050000", BeamType="Wash", ColorRenderingIndex="80")
        chan_geo = {"Pan": "Yoke", "Tilt": "Head"}
        default_geo = "Head"
    else:
        ET.SubElement(models, "Model", Name="BODY", Length="0.300000", Width="0.300000", Height="0.200000", PrimitiveType="Cube", File="")
        ET.SubElement(models, "Model", Name="BEAM", Length="0.100000", Width="0.100000", Height="0.020000", PrimitiveType="Cylinder", File="")
        base = ET.SubElement(geos, "Geometry", Name="Base", Position=IDENTITY, Model="BODY")
        ET.SubElement(base, "Beam", Name="Beam", Position=IDENTITY, Model="BEAM", LampType="LED", PowerConsumption="100.000000",
                      LuminousFlux="2000.000000", ColorTemperature="6500.000000", BeamAngle="25.000000", FieldAngle="30.000000",
                      BeamRadius="0.050000", BeamType="Wash", ColorRenderingIndex="80")
        chan_geo = {}
        default_geo = "Base"
    modes = ET.SubElement(ft, "DMXModes")
    mode = ET.SubElement(modes, "DMXMode", Name=head.mode or "Mode 1", Description="", Geometry="Base")
    dchs = ET.SubElement(mode, "DMXChannels")
    for gc in gh.channels:
        nb = gc.bytes
        geo = chan_geo.get(gc.attr, default_geo)
        offs = str(gc.offset + 1) if gc.fine is None else f"{gc.offset + 1},{gc.fine + 1}"
        default = gc.source.default & 0xff
        if gc.fine is not None:
            default = (default << 8) | (head.channels[gc.fine].default & 0xff)
        ch_el = ET.SubElement(dchs, "DMXChannel", DMXBreak="1", Offset=offs, Highlight="None", Geometry=geo,
                              InitialFunction=f"{geo}_{gc.attr}.{gc.attr}.{_safe(gc.source.name) or gc.attr}")
        lc = ET.SubElement(ch_el, "LogicalChannel", Attribute=gc.attr, Snap="Yes" if gc.source.kind in ("ltp8snap",) else "No",
                           Master="None", MibFade="0.000000", DMXChangeTimeLimit="0.000000")
        lo, hi, _ = _physical(gc, head)
        cf = ET.SubElement(lc, "ChannelFunction", Name=_safe(gc.source.name) or gc.attr, Attribute=gc.attr, OriginalAttribute="", DMXFrom=_frac(0, nb),
                           Default=_frac(default, nb), PhysicalFrom=f"{lo:.6f}", PhysicalTo=f"{hi:.6f}", RealFade="0.000000",
                           RealAcceleration="0.000000", Min=f"{lo:.6f}", Max=f"{hi:.6f}", CustomName="")
        for rlo, rhi, rname in _ranges(gc.source, nb):
            ET.SubElement(cf, "ChannelSet", Name=rname[:32], DMXFrom=_frac(rlo, nb), WheelSlotIndex="0")
        if gc.source.locate is not None and gc.source.locate != default:
            ch_el.set("Highlight", _frac(gc.source.locate * (256 if nb == 2 else 1), nb))
    ET.SubElement(mode, "Relations")
    ET.SubElement(mode, "FTMacros")
    ET.SubElement(ft, "Revisions").append(ET.Element("Revision", Text="ma3-to-magicq", Date="2026-10-29T00:00:00", UserID="0", ModifiedBy="ma3-to-magicq"))
    ET.SubElement(ft, "FTPresets")
    ET.SubElement(ft, "Protocols")
    ET.indent(root, space="    ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


def gdtf_bytes(gh: GHead) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("description.xml", description_xml(gh))
    return buf.getvalue()


def write_gdtf(head: HeadDef, path: str) -> GHead:
    gh = plan(head)
    with open(path, "wb") as fh:
        fh.write(gdtf_bytes(gh))
    return gh
