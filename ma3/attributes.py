"""MagicQ attribute numbers back to grandMA3 attribute names.

The forward map (data/gdtf_to_magicq.csv) is many to one, so the way back
uses the MagicQ attribute number as the main key and the channel name to
break ties (MagicQ attr 16 is Red on an RGB head and Cyan on a CMY head).
Every name returned here exists in grandMA3's attribute_definitions.xml.
"""
from __future__ import annotations

import re

# MagicQ attribute number -> grandMA3 attribute name (default when the channel name says nothing more)
BY_NUMBER = {
    0: "Dimmer", 1: "DimmerMode", 2: "Shutter1", 3: "Iris", 4: "Pan", 5: "Tilt",
    6: "Color1", 7: "Color2", 8: "Gobo1", 9: "Gobo2", 10: "Gobo1PosRotate", 11: "Gobo2PosRotate",
    12: "Focus1", 13: "Zoom", 14: "Prism1", 15: "Prism2", 16: "ColorRGB_R", 17: "ColorRGB_G",
    18: "ColorRGB_B", 19: "ColorRGB_W", 20: "Control1", 21: "LampControl", 22: "ColorMacro",
    23: "ColorMacro2", 24: "CTC", 25: "CTO", 26: "ColorMixMSpeed", 27: "ColorRGB_RY",
    28: "Gobo3", 29: "AnimationWheel1", 30: "Gobo3PosRotate", 31: "Prism1PosRotate",
    32: "Frost1", 33: "Frost2", 34: "Effects1", 35: "Effects1Rate", 36: "Effects1Fade",
    37: "Effects1Adjust1", 38: "Effects2", 39: "Effects2Rate", 40: "GlobalMSpeed",
    41: "Function", 42: "Fans", 43: "DisplayIntensity", 44: "LEDFrequency", 45: "BlackoutMode",
    46: "PanRotate", 47: "TiltRotate", 48: "PositionEffect", 49: "PositionEffectRate",
    50: "PositionEffectFade", 51: "PositionMSpeed",
    52: "Blade1A", 53: "Blade1B", 54: "Blade2A", 55: "Blade2B", 56: "Blade3A", 57: "Blade3B",
    58: "Blade4A", 59: "Blade4B", 60: "ColorRGB_UV", 61: "Color3", 62: "Color4", 63: "NoFeature",
}

# (regex on the lower-case channel name, applies to these MagicQ attrs or None for any) -> name
BY_NAME = [
    (r"\bcyan\b|^c$", {16}, "ColorRGB_C"),
    (r"\bmagenta\b|^m$", {17}, "ColorRGB_M"),
    (r"\byellow\b|^y$", {18}, "ColorRGB_Y"),
    (r"\bamber\b", None, "ColorRGB_RY"),
    (r"\blime\b", None, "ColorRGB_GY"),
    (r"\buv\b|ultra ?violet", None, "ColorRGB_UV"),
    (r"warm ?white|\bww\b", {19, 24, 27, 60}, "ColorRGB_WW"),
    (r"cold ?white|cool ?white|\bcw\b", {19, 24, 27, 60}, "ColorRGB_CW"),
    (r"\bwhite\b", {19, 24, 27, 60, 61, 62}, "ColorRGB_W"),
    (r"\bcto\b", {24, 25, 26, 61, 62}, "CTO"),
    (r"\bctb\b", {24, 25, 26, 61, 62}, "CTB"),
    (r"\bctc\b|colou?r temp", {24, 25, 26, 61, 62}, "CTC"),
    (r"\bhue\b", {6, 7}, "HSB_Hue"),
    (r"saturation", {6, 7}, "HSB_Saturation"),
    (r"reset", {20, 21, 41, 42, 43, 44, 45}, "FixtureGlobalReset"),
    (r"\blamp\b", {20, 21, 41, 42, 43, 44, 45}, "LampControl"),
    (r"\bfan", {20, 21, 41, 42, 43, 44, 45}, "Fans"),
    (r"display", {20, 21, 41, 42, 43, 44, 45}, "DisplayIntensity"),
    (r"dim(mer)? ?(mode|curve)", {1, 20, 21, 41, 42, 43, 44, 45}, "DimmerCurve"),
    (r"\bfog\b|smoke", {0, 20, 21, 41, 42, 43, 44, 45}, "Fog1"),
    (r"\bhaze\b", {0, 20, 21, 41, 42, 43, 44, 45}, "Haze1"),
    (r"strobe", {2, 15, 34, 35, 36, 37, 38, 39, 41}, "Shutter1"),
    (r"shutter ?2|strobe ?2", {15, 34, 38}, "Shutter1StrobeEffect"),
    (r"prism ?rot|prism ?index|prism.*rot", {10, 11, 30, 31, 34, 35, 36, 37, 38, 39}, "Prism1PosRotate"),
    (r"prism ?2", {15, 34, 38}, "Prism2"),
    (r"prism", {14, 15, 34, 38}, "Prism1"),
    (r"frost ?2|wash", {32, 33, 34, 38}, "Frost2"),
    (r"frost", {14, 15, 32, 33, 34, 38}, "Frost1"),
    (r"iris", {3, 34, 38}, "Iris"),
    (r"zoom", {12, 13, 34, 38}, "Zoom"),
    (r"focus", {12, 13, 34, 38}, "Focus1"),
    (r"gobo ?1.*(rot|index)|rot(ate)? ?1", {10, 11, 30, 31}, "Gobo1PosRotate"),
    (r"gobo ?2.*(rot|index)|rot(ate)? ?2", {10, 11, 30, 31}, "Gobo2PosRotate"),
    (r"gobo ?1.*shake|shake ?1", {8, 9, 28, 29}, "Gobo1WheelShake"),
    (r"anim", {8, 9, 28, 29}, "AnimationWheel1"),
    (r"anim.*rot", {10, 11, 30, 31}, "AnimationWheel1PosRotate"),
    (r"colou?r ?macro|macro", {22, 23, 6, 7}, "ColorMacro"),
    (r"p/?t ?speed|pan ?/? ?tilt ?speed|mov(e|ement) ?speed|position ?speed", None, "PositionMSpeed"),
    (r"pan ?mode|tilt ?mode|p/?t ?mode", None, "PanTiltMode"),
    (r"blade ?1 ?a|frame ?1 ?a", {52, 53, 54, 55, 56, 57, 58, 59}, "Blade1A"),
    (r"blade ?1 ?b|frame ?1 ?b", {52, 53, 54, 55, 56, 57, 58, 59}, "Blade1B"),
    (r"blade ?2 ?a|frame ?2 ?a", {52, 53, 54, 55, 56, 57, 58, 59}, "Blade2A"),
    (r"blade ?2 ?b|frame ?2 ?b", {52, 53, 54, 55, 56, 57, 58, 59}, "Blade2B"),
    (r"blade ?3 ?a|frame ?3 ?a", {52, 53, 54, 55, 56, 57, 58, 59}, "Blade3A"),
    (r"blade ?3 ?b|frame ?3 ?b", {52, 53, 54, 55, 56, 57, 58, 59}, "Blade3B"),
    (r"blade ?4 ?a|frame ?4 ?a", {52, 53, 54, 55, 56, 57, 58, 59}, "Blade4A"),
    (r"blade ?4 ?b|frame ?4 ?b", {52, 53, 54, 55, 56, 57, 58, 59}, "Blade4B"),
    (r"frame ?rot|shaper ?rot|blade ?rot", None, "ShaperRot"),
    (r"\bfx ?speed|effect ?speed|fx ?rate", {34, 35, 36, 37, 38, 39}, "Effects1Rate"),
    (r"\bfx\b|effect|macro", {14, 15, 34, 35, 36, 37, 38, 39}, "Effects1"),
    (r"\bcolou?r ?(wheel)? ?2|col ?2", {6, 7, 61, 62}, "Color2"),
    (r"\bcolou?r ?(wheel)? ?3|col ?3", {6, 7, 61, 62}, "Color3"),
    (r"\bgobo ?2", {8, 9, 28, 29}, "Gobo2"),
    (r"\bgobo ?3", {8, 9, 28, 29}, "Gobo3"),
]

# grandMA3 feature groups and preset pools
GROUP_POOL = {"Dimmer": 1, "Position": 2, "Gobo": 3, "Color": 4, "Beam": 5, "Focus": 6, "Control": 7, "Shapers": 8, "Video": 9}

# alternatives when one head maps two channels to the same MA3 attribute
SPARES = {
    "Dimmer": ["Dimmer", "HSB_Brightness", "VideoBrightness"],
    "Position": ["PositionEffect", "PositionEffectRate", "PositionEffectFade", "XYZ_X", "XYZ_Y", "XYZ_Z"],
    "Gobo": ["Gobo1WheelSpin", "Gobo2WheelSpin", "Gobo1WheelShake", "Gobo2WheelShake", "Gobo3WheelSpin", "Gobo3PosRotate"],
    "Color": ["Color3", "Color4", "ColorRGB_GC", "ColorRGB_BC", "ColorRGB_BM", "ColorRGB_RM", "Tint", "ColorMacro2"],
    "Beam": ["Effects1", "Effects2", "Effects1Rate", "Effects2Rate", "Effects1Fade", "Effects2Fade", "Effects1Adjust1", "Effects2Adjust1",
             "Prism2", "Prism2PosRotate", "Frost2", "IrisStrobe", "BeamShaper"],
    "Focus": ["Focus2", "Focus1Adjust", "Focus2Adjust", "ZoomMode"],
    "Control": ["Control1", "Function", "Fans", "DisplayIntensity", "LEDFrequency", "BlackoutMode", "PixelMode", "DMXInput", "Dummy", "NoFeature",
                "StrobeMode", "IrisMode", "FanMode", "ZoomMode", "FocusMode"],
    "Shapers": ["ShaperRot", "ShaperMacros", "ShaperMacrosSpeed", "BladeSoft1A", "BladeSoft1B", "BladeSoft2A", "BladeSoft2B"],
}


def feature_group(name: str) -> str:
    n = name
    if n.startswith(("Dimmer", "HSB_Brightness")) and n not in ("DimmerMode", "DimmerCurve"):
        return "Dimmer"
    if n in ("Pan", "Tilt", "PanRotate", "TiltRotate", "PositionMSpeed") or n.startswith(("Position", "XYZ", "PanTilt")):
        return "Position"
    if n.startswith(("Gobo", "AnimationWheel", "AnimationSystem")) and not n.endswith("Mode"):
        return "Gobo"
    if n.startswith(("Color", "CTO", "CTC", "CTB", "Tint", "HSB_", "CIE_")) and not n.endswith(("Mode", "Reset")):
        return "Color"
    if n.startswith(("Shutter", "Strobe", "Iris", "Frost", "Prism", "Effects", "BeamShaper", "Fog", "Haze", "Blower")) and not n.endswith("Mode"):
        return "Beam"
    if n.startswith(("Focus", "Zoom")) and not n.endswith("Mode"):
        return "Focus"
    if n.startswith(("Blade", "Shaper", "KeyStone")):
        return "Shapers"
    if n.startswith("Video"):
        return "Video"
    return "Control"


def ma3_name(attr: int, channel_name: str) -> str:
    low = (channel_name or "").lower().strip()
    for pattern, attrs, name in BY_NAME:
        if (attrs is None or attr in attrs) and re.search(pattern, low):
            return name
    return BY_NUMBER.get(attr, "NoFeature")


def feature(name: str, group: str) -> str:
    """The GDTF Feature a channel belongs to (Group.Feature)."""
    if group == "Position":
        return "Position.PanTilt" if name in ("Pan", "Tilt", "PanRotate", "TiltRotate", "PositionMSpeed") else "Position.XYZ"
    if group == "Color":
        return "Color.RGB" if name.startswith(("ColorRGB", "HSB", "CIE")) else "Color.Color"
    return f"{group}.{group}"
