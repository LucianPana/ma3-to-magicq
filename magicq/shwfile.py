"""Reader and writer for the MagicQ .shw text format (byte-exact round trip).

A show file is a comment header (lines starting with a backslash) followed by
records. A record starts with a line "<TAG>,<fields...>" where TAG is one or
more capital letters, optionally followed by digits (V, T, P, L, H, E1 ...),
and runs until the next such line. Inside a record there can be continuation
lines, blank lines and lowercase-tagged sub-records (j, m, u ...). Semicolons
end sub-blocks but are not reliable record terminators, so they are ignored
when splitting; the raw lines are kept so a parsed file can be written back
byte for byte.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

TAG_RE = re.compile(r"^([A-Z][A-Z0-9]*),")


def split_fields(line: str) -> list[str]:
    """Split a record line on commas outside double quotes.

    A trailing ';' is dropped, and so is the empty field left by a final comma,
    so '"a",1,;' gives ['"a"', '1'].
    """
    out, cur, inq = [], [], False
    for ch in line:
        if ch == '"':
            inq = not inq
            cur.append(ch)
        elif ch == "," and not inq:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    tail = "".join(cur).strip()
    if tail.endswith(";"):
        tail = tail[:-1].strip()
    if tail != "":
        out.append(tail)
    return out


def unquote(s: str) -> str:
    return s[1:-1] if len(s) >= 2 and s[0] == '"' and s[-1] == '"' else s


@dataclass
class Record:
    tag: str
    lines: list[str] = field(default_factory=list)  # raw lines; the first holds the tag

    @property
    def header(self) -> list[str]:
        return split_fields(self.lines[0])[1:]

    def body(self) -> list[list[str]]:
        return [split_fields(l) for l in self.lines[1:]]

    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def id(self) -> int | None:
        h = self.header
        try:
            return int(h[0], 16)
        except (IndexError, ValueError):
            return None

    @property
    def name(self) -> str:
        h = self.header
        for f in h[1:3]:
            if f.startswith('"'):
                return unquote(f)
        return ""


@dataclass
class ShowFile:
    comments: list[str]
    records: list[Record]
    newline: str = "\n"

    def by_tag(self, tag: str) -> list[Record]:
        return [r for r in self.records if r.tag == tag]

    def one(self, tag: str) -> Record:
        rs = self.by_tag(tag)
        if len(rs) != 1:
            raise KeyError(f"expected one {tag} record, found {len(rs)}")
        return rs[0]

    def text(self) -> str:
        parts = list(self.comments)
        for r in self.records:
            parts.extend(r.lines)
        return self.newline.join(parts)


def parse(text: str) -> ShowFile:
    newline = "\r\n" if "\r\n" in text else "\n"
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    comments: list[str] = []
    records: list[Record] = []
    cur: Record | None = None
    for line in raw:
        m = TAG_RE.match(line)
        if m:
            cur = Record(m.group(1), [line])
            records.append(cur)
        elif cur is None:
            comments.append(line)
        else:
            cur.lines.append(line)
    return ShowFile(comments, records, newline)


def load(path: str) -> ShowFile:
    with open(path, encoding="latin-1") as fh:
        return parse(fh.read())


def save(show: ShowFile, path: str) -> None:
    with open(path, "w", encoding="latin-1", newline="") as fh:
        fh.write(show.text())
