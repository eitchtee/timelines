"""Structured + full-text search engine for Timelines.

Supported query syntax:
    - Free text:           puked chicken
    - Require tag:         #dog #puke
    - Exclude tag:         -#walk
    - Event shape:         is:ongoing | is:span | is:point
    - Has data point key:  has:battery
    - Data point text:     ate:chicken  or  ate:"chicken rice"
    - Data point numeric:  battery:<20  battery:<=20  battery:>80  battery:=50
    - Date windows:        last:30d | last:12h | last:2w | last:6m | last:1y
                           after:2026-10-01 | before:2026-11-01
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.db import connection
from django.db.models import F, Q, QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.text import slugify

from .dates import parse_loose, prefers_day_first, readings

_QUERY_TOKEN_RE = re.compile(
    r"""
    (?P<neg>-)?\#(?P<tag>[A-Za-z0-9][A-Za-z0-9_-]{0,62})
    |
    (?P<key>[A-Za-z][A-Za-z0-9_-]{0,62}):(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)'|(?P<val>[^\s]+))
    |
    "(?P<phrase>[^"]+)"
    |
    (?P<word>\S+)
    """,
    re.VERBOSE,
)

_NUM_OP_RE = re.compile(r"^(<=|>=|<|>|=)?\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))$")
_LAST_RE = re.compile(r"^(\d+)\s*([hdwmy])$", re.IGNORECASE)


@dataclass
class DataFilter:
    key: str
    op: str  # "icontains", "<", "<=", ">", ">=", "="
    value: str
    num_value: float | None = None


@dataclass
class ParsedSearchQuery:
    include_tags: list[str] = field(default_factory=list)
    exclude_tags: list[str] = field(default_factory=list)
    data_filters: list[DataFilter] = field(default_factory=list)
    has_keys: list[str] = field(default_factory=list)
    shapes: list[str] = field(default_factory=list)
    after: datetime | None = None
    before: datetime | None = None
    text_terms: list[str] = field(default_factory=list)


def _parse_date_bound(raw: str, *, end_of_day: bool = False) -> datetime | None:
    dt = parse_datetime(raw)
    if dt is not None:
        if timezone.is_naive(dt):
            return timezone.make_aware(dt, timezone.get_current_timezone())
        return dt
    d = parse_date(raw)
    if d is None:
        # 20/10, 10-08-24, 20/10,14:30... (an ambiguous one takes the locale's reading)
        today = timezone.localdate()
        loose = parse_loose(raw, today, day_first=prefers_day_first())
        if loose and loose.ends is None and not loose.open_ended:
            point = readings(loose, today)[0][0]
            if point.at:
                return timezone.make_aware(datetime.combine(point.day, point.at))
            d = point.day
    if d is not None:
        hour, minute, second = (23, 59, 59) if end_of_day else (0, 0, 0)
        return timezone.make_aware(
            datetime(d.year, d.month, d.day, hour, minute, second),
            timezone.get_current_timezone(),
        )
    return None


def _parse_relative_last(raw: str) -> datetime | None:
    match = _LAST_RE.match(raw.strip())
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    now = timezone.now()
    if unit == "h":
        return now - timedelta(hours=amount)
    if unit == "d":
        return now - timedelta(days=amount)
    if unit == "w":
        return now - timedelta(weeks=amount)
    if unit == "m":
        return now - timedelta(days=amount * 30)
    if unit == "y":
        return now - timedelta(days=amount * 365)
    return None


def parse_search_query(q: str) -> ParsedSearchQuery:
    parsed = ParsedSearchQuery()
    if not q or not q.strip():
        return parsed

    for match in _QUERY_TOKEN_RE.finditer(q.strip()):
        tag = match.group("tag")
        if tag:
            slug = slugify(tag) or tag.lower()
            if match.group("neg"):
                if slug not in parsed.exclude_tags:
                    parsed.exclude_tags.append(slug)
            else:
                if slug not in parsed.include_tags:
                    parsed.include_tags.append(slug)
            continue

        key = match.group("key")
        if key:
            key_l = key.lower()
            val = match.group("dq")
            if val is None:
                val = match.group("sq")
            if val is None:
                val = match.group("val")
            val = (val or "").strip()
            if not val:
                continue

            if key_l == "is":
                shape = val.lower()
                if shape in {"ongoing", "span", "point"} and shape not in parsed.shapes:
                    parsed.shapes.append(shape)
            elif key_l == "has":
                norm_k = val.lower().replace(" ", "_")
                if norm_k not in parsed.has_keys:
                    parsed.has_keys.append(norm_k)
            elif key_l == "tag":
                slug = slugify(val) or val.lower()
                if slug not in parsed.include_tags:
                    parsed.include_tags.append(slug)
            elif key_l == "after":
                dt = _parse_date_bound(val, end_of_day=False)
                if dt is not None:
                    parsed.after = dt
            elif key_l == "before":
                dt = _parse_date_bound(val, end_of_day=True)
                if dt is not None:
                    parsed.before = dt
            elif key_l == "last":
                dt = _parse_relative_last(val)
                if dt is not None:
                    parsed.after = dt
            else:
                num_match = _NUM_OP_RE.match(val)
                if num_match and num_match.group(1):
                    op = num_match.group(1)
                    num_val = float(num_match.group(2))
                    parsed.data_filters.append(
                        DataFilter(key=key_l, op=op, value=val, num_value=num_val)
                    )
                else:
                    parsed.data_filters.append(
                        DataFilter(key=key_l, op="icontains", value=val)
                    )
            continue

        phrase = match.group("phrase")
        if phrase:
            parsed.text_terms.append(phrase.strip())
            continue

        word = match.group("word")
        if word:
            parsed.text_terms.append(word.strip())

    return parsed


def _fts5_query(terms: list[str]) -> str:
    """Each term as a quoted FTS5 phrase with a prefix star, all required.

    Quoting keeps user input from being read as FTS5 syntax (AND, NEAR, -, ^);
    the star makes "chick" find "chicken".
    """
    return " ".join('"' + t.replace('"', '""') + '"*' for t in terms if t.strip())


def search_events(
    queryset: QuerySet,
    q: str = "",
    *,
    extra_tags: list[str] | None = None,
    tag_mode: str = "and",
    after: datetime | None = None,
    before: datetime | None = None,
) -> QuerySet:
    """Apply structured filters + PostgreSQL FTS/trigram (or SQLite fallback) search."""
    parsed = parse_search_query(q)

    include_tags = list(parsed.include_tags)
    for t in extra_tags or []:
        slug = slugify(t) or t.lower()
        if slug and slug not in include_tags:
            include_tags.append(slug)

    if include_tags:
        if tag_mode == "or":
            queryset = queryset.filter(tags__slug__in=include_tags)
        else:
            for slug in include_tags:
                queryset = queryset.filter(tags__slug=slug)

    for slug in parsed.exclude_tags:
        queryset = queryset.exclude(tags__slug=slug)

    if parsed.shapes:
        shape_q = Q()
        for shape in parsed.shapes:
            if shape == "ongoing":
                shape_q |= Q(is_ongoing=True, ended_at__isnull=True)
            elif shape == "span":
                shape_q |= Q(ended_at__isnull=False) | Q(is_ongoing=True)
            elif shape == "point":
                shape_q |= Q(is_ongoing=False, ended_at__isnull=True)
        queryset = queryset.filter(shape_q)

    for key in parsed.has_keys:
        queryset = queryset.filter(data_points__key=key)

    op_map = {
        "<": "lt",
        "<=": "lte",
        ">": "gt",
        ">=": "gte",
        "=": "exact",
    }
    for df in parsed.data_filters:
        if df.op in op_map and df.num_value is not None:
            lookup = f"data_points__value_num__{op_map[df.op]}"
            queryset = queryset.filter(
                data_points__key=df.key, **{lookup: df.num_value}
            )
        else:
            queryset = queryset.filter(
                data_points__key=df.key,
                data_points__value_text__icontains=df.value,
            )

    bound_after = after or parsed.after
    bound_before = before or parsed.before
    if bound_after is not None:
        # Include ongoing/spans that overlap the window as well as events starting after
        queryset = queryset.filter(
            Q(started_at__gte=bound_after)
            | Q(ended_at__gte=bound_after)
            | Q(is_ongoing=True)
        )
    if bound_before is not None:
        queryset = queryset.filter(started_at__lte=bound_before)

    if parsed.text_terms:
        joined = " ".join(parsed.text_terms)
        if connection.vendor == "postgresql":
            from django.contrib.postgres.search import (
                SearchQuery,
                SearchRank,
                SearchVector,
                TrigramSimilarity,
            )

            vector = SearchVector("search_document", config="english")
            sq = SearchQuery(joined, config="english", search_type="websearch")
            queryset = (
                queryset.annotate(
                    _search_rank=SearchRank(vector, sq),
                    _trigram_sim=TrigramSimilarity("search_document", joined),
                )
                .filter(
                    Q(_search_rank__gt=0.01)
                    | Q(_trigram_sim__gt=0.15)
                    | Q(search_document__icontains=joined)
                )
                .order_by("-_search_rank", "-_trigram_sim", "-started_at")
            )
        elif connection.vendor == "sqlite":
            # FTS5 (migration 0005) gives stemming, prefix matches and bm25
            # ranking; plain substring matching stays as a fallback so
            # nothing that used to match stops matching.
            from django.db.models.expressions import RawSQL

            fts_query = _fts5_query(parsed.text_terms)
            substring = Q()
            for term in parsed.text_terms:
                substring &= Q(search_document__icontains=term)
            fts_ids = RawSQL(
                "SELECT rowid FROM events_event_fts WHERE events_event_fts MATCH %s",
                (fts_query,),
            )
            rank = RawSQL(
                "SELECT bm25(events_event_fts) FROM events_event_fts"
                " WHERE events_event_fts MATCH %s"
                " AND events_event_fts.rowid = events_event.id",
                (fts_query,),
            )
            queryset = (
                queryset.filter(Q(id__in=fts_ids) | substring)
                .annotate(_search_rank=rank)
                # bm25 is lower-is-better; substring-only hits come last
                .order_by(F("_search_rank").asc(nulls_last=True), "-started_at")
            )
        else:
            for term in parsed.text_terms:
                queryset = queryset.filter(search_document__icontains=term)

    return queryset.distinct()
