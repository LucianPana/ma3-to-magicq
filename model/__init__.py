"""Console-neutral show model shared by the grandMA3 reader and the MagicQ writer."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# MagicQ attribute numbers (manual, Head Editor "Attrib No" table)
ATTR = {
    "Intensity": 0, "IntensityMode": 1, "Shutter": 2, "Iris": 3, "Pan": 4, "Tilt": 5,
    "Col1": 6, "Col2": 7, "Gobo1": 8, "Gobo2": 9, "Rotate1": 10, "Rotate2": 11,
    "Focus": 12, "Zoom": 13, "FX1": 14, "FX2": 15, "Red": 16, "Green": 17, "Blue": 18,
    "White": 19, "Cont1": 20, "Cont2": 21, "Macro": 22, "Macro2": 23, "CTC": 24, "CTO": 25,
    "ColSpeed": 26, "Amber": 27, "Gobo3": 28, "Gobo4": 29, "Rotate3": 30, "PrismRot": 31,
    "Frost1": 32, "Frost2": 33, "FX3": 34, "FX4": 35, "FX5": 36, "FX6": 37, "FX7": 38, "FX8": 39,
    "BeamSpeed": 40, "Cont4": 41, "Cont5": 42, "Cont6": 43, "Cont7": 44, "Cont8": 45,
    "Pos1": 46, "Pos2": 47, "Pos3": 48, "Pos4": 49, "Pos5": 50, "PosSpeed": 51,
    "Frame1": 52, "Frame2": 53, "Frame3": 54, "Frame4": 55, "Frame5": 56, "Frame6": 57,
    "Frame7": 58, "Frame8": 59, "LimeUV": 60, "Col5": 61, "Col6": 62,
}
ATTR_NAME = {v: k for k, v in ATTR.items()}

# attribute families, as MagicQ groups them for palettes and cue times
INTENSITY_ATTRS = {0, 1}
POSITION_ATTRS = {4, 5, 46, 47, 48, 49, 50, 51}
COLOUR_ATTRS = {6, 7, 16, 17, 18, 19, 24, 25, 26, 27, 60, 61, 62}


def family(attr: int) -> str:
    if attr in INTENSITY_ATTRS:
        return "int"
    if attr in POSITION_ATTRS:
        return "pos"
    if attr in COLOUR_ATTRS:
        return "col"
    return "beam"


# channel kinds -> MagicQ channel type word (see docs/shw-format.md)
KIND_TYPE_WORD = {
    "htp8": 0x00000001,      # dimmer, 8 bit
    "htp16c": 0x00000005,    # dimmer 16 bit coarse
    "htp16f": 0x00000009,    # dimmer 16 bit fine
    "ltp8": 0x00000012,      # fading 8 bit attribute
    "ltp8snap": 0x00000022,  # instant 8 bit attribute (wheels)
    "ltp8mix": 0x00002022,   # colour mixing component (RGB/CMY)
    "ltp16c": 0x00000016,    # fading 16 bit coarse (focus, zoom)
    "ltp16f": 0x0000001a,
    "pos16c": 0x00000036,    # pan/tilt coarse
    "pos16f": 0x0000003a,
    "ctrl": 0x00008012,      # control channels (reset, lamp)
}


@dataclass
class Range:
    lo: int
    hi: int
    name: str


@dataclass
class Channel:
    name: str
    attr: int
    kind: str = "ltp8"
    default: int = 0
    locate: Optional[int] = None
    ranges: list[Range] = field(default_factory=list)

    @property
    def type_word(self) -> int:
        return KIND_TYPE_WORD[self.kind]


@dataclass
class HeadDef:
    manufacturer: str
    model: str
    mode: str
    channels: list[Channel]
    pan_deg: int = 540
    tilt_deg: int = 270
    source: str = ""  # where it came from (GDTF file, MagicQ library name)

    @property
    def key(self) -> str:
        return f"{self.manufacturer}_{self.model}_{self.mode}".strip("_")

    @property
    def nchans(self) -> int:
        return len(self.channels)


@dataclass
class Fixture:
    fid: int                 # user id (MA3 FID), also the MagicQ head number
    name: str
    head: HeadDef
    universe: int            # 1-based
    address: int             # 1-based within the universe
    pos: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rot: tuple[float, float, float] = (0.0, 0.0, 0.0)
    color_rgb: int = 0xFFFFFF

    @property
    def abs_chan(self) -> int:
        """Absolute DMX channel of the first slot (MagicQ's key for everything)."""
        return (self.universe - 1) * 512 + self.address


@dataclass
class Group:
    name: str
    members: list[int]       # fixture ids in selection order


@dataclass
class Palette:
    kind: str                # int, pos, col, beam
    name: str
    values: dict[tuple[int, int], int] = field(default_factory=dict)  # (fid, chan offset) -> 0..255
    rgb: Optional[tuple[float, float, float]] = None                   # for colour palettes, 0..1


@dataclass
class Cue:
    number: float
    name: str
    values: dict[tuple[int, int], int] = field(default_factory=dict)
    fade: float = 3.0        # seconds, intensity in
    fade_out: Optional[float] = None
    delay: float = 0.0
    fade_pos: Optional[float] = None
    fade_col: Optional[float] = None
    fade_beam: Optional[float] = None
    follow: Optional[float] = None   # seconds after the previous cue, None = wait for Go
    timecode: Optional[float] = None  # seconds
    notes: list[str] = field(default_factory=list)


@dataclass
class CueStack:
    name: str
    cues: list[Cue]
    chase: bool = False
    chase_speed: float = 2.0  # seconds per step when chase


@dataclass
class Playback:
    page: int                # 1-based
    index: int               # 0-based playback on the page
    kind: str                # "stack", "group", "palette"
    ref: int                 # 0-based index into the target store
    legend: str = ""


@dataclass
class Show:
    name: str
    fixtures: list[Fixture] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)
    palettes: list[Palette] = field(default_factory=list)
    stacks: list[CueStack] = field(default_factory=list)
    playbacks: list[Playback] = field(default_factory=list)
    report: list[str] = field(default_factory=list)

    def heads(self) -> list[HeadDef]:
        seen: dict[str, HeadDef] = {}
        for f in self.fixtures:
            seen.setdefault(f.head.key, f.head)
        return list(seen.values())

    def fixture(self, fid: int) -> Fixture:
        for f in self.fixtures:
            if f.fid == fid:
                return f
        raise KeyError(fid)
