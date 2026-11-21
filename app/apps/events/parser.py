"""Quick-capture inline syntax parser.

Parses fast single-line input such as:
    "Charged watch #smartwatch #charge battery:14%"
    "Started ibuprofen #health #meds dose:400mg !ongoing"
    'Dog puked #dog #puke ate:"chicken and rice"'
"""

import re
from dataclasses import dataclass, field
from datetime import date

from .dates import parse_loose

# Matches:
#   #tag-name
#   key:"quoted value" or key:'quoted value' or key:value
#   !ongoing / !start
#   @20/10, @20/10,14:30, @14:30, @20/10~22/10, @20/10~ (kept raw; see dates.py)
_TOKEN_RE = re.compile(
    r"""
    (?P<ongoing>!(?:ongoing|start)\b)
    |
    (?<!\w)@(?P<when>\d[\w/.\-:,~]*)
    |
    (?<!\w)\#(?P<tag>[A-Za-z0-9][A-Za-z0-9_-]{0,62})
    |
    (?<!\w)(?P<key>[A-Za-z][A-Za-z0-9_-]{0,62}):(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)'|(?P<val>[^\s]+))
    """,
    re.VERBOSE,
)


@dataclass
class ParsedQuickInput:
    title: str
    tags: list[str] = field(default_factory=list)
    data_points: list[tuple[str, str]] = field(default_factory=list)
    is_ongoing: bool = False
    when: str | None = None  # raw @date text; interpreted by dates.parse_loose


def parse_quick_input(raw_text: str) -> ParsedQuickInput:
    text = (raw_text or "").strip()
    if not text:
        return ParsedQuickInput(title="")

    tags: list[str] = []
    seen_tags: set[str] = set()
    data_points: list[tuple[str, str]] = []
    is_ongoing = False
    when = None

    def _collect(match: re.Match) -> str:
        nonlocal is_ongoing, when
        if match.group("when"):
            # only a readable date leaves the title; "@99 bottles" stays text
            if parse_loose(match.group("when"), date.today()) is None:
                return match.group(0)
            when = match.group("when")
            return ""
        if match.group("ongoing"):
            is_ongoing = True
            return ""
        tag = match.group("tag")
        if tag:
            norm = tag.lower()
            if norm not in seen_tags:
                seen_tags.add(norm)
                tags.append(tag)
            return ""
        key = match.group("key")
        if key:
            val = match.group("dq")
            if val is None:
                val = match.group("sq")
            if val is None:
                val = match.group("val")
            if val is not None and val.strip():
                data_points.append((key.lower(), val.strip()))
                return ""
        return match.group(0)

    remaining = _TOKEN_RE.sub(_collect, text)
    title = re.sub(r"\s+", " ", remaining).strip()

    if not title and tags:
        title = " ".join(f"#{t}" for t in tags)

    return ParsedQuickInput(
        title=title,
        tags=tags,
        data_points=data_points,
        is_ongoing=is_ongoing,
        when=when,
    )
