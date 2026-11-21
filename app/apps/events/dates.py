"""Loose, human date input: ``@20/10`` in Quick log and ``after:``/``before:`` in search.

A point is a date, a time, or both joined by ``,`` or ``T``:
    20/10   20-10-2024   2026.10.20   14:30   2pm   14h30   20/10,14:30   2026-10-20T14:30
Dates may be day-first, month-first or year-first, padded or not, with 2- or 4-digit
years (no year: this year). A time on its own means today.

Two points joined by ``~`` (or ``..``) make a range; an end with only a time stays
on the start's day. A trailing ``~`` leaves the range open (still running).

When a date reads validly more than one way (``10-08``) every reading is kept, the
locale's preferred one first, so the UI can ask which was meant.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from itertools import product

from django.utils.formats import get_format

_DATE_RE = re.compile(r"^(\d{1,4})[/.\-](\d{1,2})(?:[/.\-](\d{1,4}))?$")
# 14:30, 9:05, 14h, 14h30, 2pm, 2:30pm, 2 pm. A bare number is not a time.
_TIME_RE = re.compile(
    r"^(\d{1,2})(?:(?::(\d{2}))|(?:h(\d{2})?))?\s*([ap]m)?$", re.IGNORECASE
)
_RANGE_SEPS = ("~", "..")


@dataclass(frozen=True)
class When:
    day: date | None  # None: only a time was given (resolved later)
    at: time | None = None  # not "time": that would shadow the type in annotations


@dataclass
class LooseDate:
    starts: list[When]  # every valid reading, preferred first
    ends: list[When] | None = None  # None: a single point
    open_ended: bool = False  # "@20/10~": started then, still running

    @property
    def ambiguous(self) -> bool:
        return len(self.starts) > 1 or len(self.ends or []) > 1


def prefers_day_first() -> bool:
    """Read the active locale's first input format: %d/%m/%Y vs %m/%d/%Y."""
    fmt = get_format("DATE_INPUT_FORMATS")[0]
    d, m = fmt.find("%d"), fmt.find("%m")
    return d == -1 or m == -1 or d < m


def _full_year(raw: str, today: date) -> int:
    year = int(raw)
    if len(raw) > 2:
        return year
    # two digits: this century, unless that lands more than 10 years ahead
    return 2000 + year if 2000 + year <= today.year + 10 else 1900 + year


def date_candidates(token: str, today: date, *, day_first: bool = True) -> list[date]:
    """Every valid reading of one loose date, the preferred one first."""
    match = _DATE_RE.match(token.strip())
    if not match:
        return []
    a, b, c = match.groups()
    if len(a) == 4:
        if c is None:
            return []
        readings_ = [(int(a), int(b), int(c))]
    elif len(a) > 2:
        return []
    else:
        year = _full_year(c, today) if c else today.year
        dmy = (year, int(b), int(a))
        mdy = (year, int(a), int(b))
        readings_ = [dmy, mdy] if day_first else [mdy, dmy]

    out: list[date] = []
    for y, m, d in readings_:
        try:
            value = date(y, m, d)
        except ValueError:
            continue
        if value not in out:
            out.append(value)
    return out


def parse_time(token: str) -> time | None:
    match = _TIME_RE.match(token.strip())
    if not match:
        return None
    hour_s, colon_min, h_min, meridiem = match.groups()
    if (
        colon_min is None
        and h_min is None
        and meridiem is None
        and "h" not in token.lower()
    ):
        return None  # "14" alone is too vague to be a time
    hour, minute = int(hour_s), int(colon_min or h_min or 0)
    if meridiem:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if meridiem.lower() == "pm" else 0)
    try:
        return time(hour, minute)
    except ValueError:
        return None


def point_candidates(token: str, today: date, *, day_first: bool = True) -> list[When]:
    """Readings of one point: a date, a time, or "date,time" / "dateTtime"."""
    token = token.strip()
    split = re.match(r"^([^,Tt]+)[,Tt](.+)$", token)
    if split:
        at = parse_time(split.group(2))
        days = date_candidates(split.group(1), today, day_first=day_first)
        return [When(d, at) for d in days] if at else []
    days = date_candidates(token, today, day_first=day_first)
    if days:
        return [When(d) for d in days]
    at = parse_time(token)
    return [When(None, at)] if at else []


def parse_loose(token: str, today: date, *, day_first: bool = True) -> LooseDate | None:
    """Parse a point, a ``start~end`` range or an open ``start~``."""
    token = token.strip()
    for sep in _RANGE_SEPS:
        if sep not in token:
            continue
        left, right = token.split(sep, 1)
        starts = point_candidates(left, today, day_first=day_first)
        if not starts:
            return None
        if not right.strip():
            return LooseDate(starts=starts, open_ended=True)
        ends = point_candidates(right, today, day_first=day_first)
        return LooseDate(starts=starts, ends=ends) if ends else None
    starts = point_candidates(token, today, day_first=day_first)
    return LooseDate(starts=starts) if starts else None


def _resolve(point: When, day: date) -> When:
    return point if point.day else When(day, point.at)


def readings(parsed: LooseDate, today: date) -> list[tuple[When, When | None]]:
    """All (start, end) combinations that make sense, preferred first.

    A time-only start means today; a time-only end means the start's day.
    """
    starts = [_resolve(s, today) for s in parsed.starts]
    if parsed.ends is None:
        return [(s, None) for s in starts]

    def key(point: When) -> datetime:
        return datetime.combine(point.day, point.at or time.min)

    out = []
    for s, e in product(starts, parsed.ends):
        e = _resolve(e, s.day)
        if key(e) >= key(s):
            out.append((s, e))
    return out


def _point_text(point: When) -> str:
    text = point.day.isoformat()
    return f"{text}T{point.at:%H:%M}" if point.at else text


def canonical(start: When, end: When | None = None, *, open_ended: bool = False) -> str:
    """Unambiguous text for a reading: ``2026-10-20T14:30~2026-10-22`` and the like."""
    text = _point_text(start)
    if end is not None:
        return f"{text}~{_point_text(end)}"
    return f"{text}~" if open_ended else text
