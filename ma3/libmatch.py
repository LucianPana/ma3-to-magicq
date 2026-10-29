"""Find grandMA3 library fixture types that may correspond to a MagicQ head.

grandMA3 onPC ships the converted grandMA2 library as encrypted .pxml files
named "manufacturer@model.pxml" (10,507 of them in 2.3.2) and reads GDTF files
from gma3_library/fixturetypes. Only the names are readable from here, so this
module proposes candidates by name; the import plugin checks the channel
layout inside onPC and keeps a candidate only when every channel lines up.
"""
from __future__ import annotations

import difflib
import glob
import os
import re

from model import HeadDef

SHARED = os.path.expanduser("~/MALightingTechnology/gma3_2.3.2/shared/lib_fixture_types")
USER_FT = os.path.expanduser("~/MALightingTechnology/gma3_library/fixturetypes")
NOISE = {"pro", "led", "mk", "the", "professional", "lighting", "light", "lights", "fixture", "inc", "ltd", "gmbh", "and", "co"}


def norm(s: str) -> str:
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    toks = [t for t in s.split() if t not in NOISE]
    return " ".join(toks)


def squash(s: str) -> str:
    return norm(s).replace(" ", "")


class Library:
    def __init__(self, shared: str = SHARED, user: str = USER_FT):
        self.entries: list[tuple[str, str, str, str]] = []  # (source, manufacturer, model, file)
        for src, folder, pat in (("grandma2", os.path.join(shared, "grandma2"), "*.pxml"),
                                 ("grandma3", os.path.join(shared, "grandma3"), "*.xml"),
                                 ("user", user, "*.gdtf"),
                                 ("user", user, "*.xml")):
            for p in glob.glob(os.path.join(folder, pat)):
                base = os.path.basename(p)
                stem = os.path.splitext(base)[0]
                if "@" in stem:
                    man, mod = stem.split("@", 1)
                else:
                    man, mod = "", stem
                if man.strip().lower() == "set":
                    continue
                self.entries.append((src, man, mod, base))

    def candidates(self, head: HeadDef, limit: int = 3) -> list[str]:
        man, mod = norm(head.manufacturer), norm(head.model)
        if not mod:
            return []
        scored = []
        for src, lman, lmod, fname in self.entries:
            nman, nmod = norm(lman), norm(lmod)
            if man and nman and not (man == nman or man in nman or nman in man or
                                     difflib.SequenceMatcher(None, man, nman).ratio() > 0.85):
                continue
            r = difflib.SequenceMatcher(None, squash(mod), squash(nmod)).ratio()
            if squash(mod) == squash(nmod):
                r = 1.0
            elif squash(mod) and squash(mod) in squash(nmod):
                r = max(r, 0.9)
            if r >= 0.72:
                bonus = 0.05 if src == "user" else 0.0
                scored.append((r + bonus, src, fname))
        scored.sort(key=lambda t: -t[0])
        out, seen = [], set()
        for r, src, fname in scored:
            if fname in seen:
                continue
            seen.add(fname)
            out.append(f"{src}:{fname}")
            if len(out) >= limit:
                break
        return out


_LIB: Library | None = None


def candidates(head: HeadDef, limit: int = 3) -> list[str]:
    global _LIB
    if _LIB is None:
        _LIB = Library()
    return _LIB.candidates(head, limit)
