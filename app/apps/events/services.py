"""Domain services for creating/updating events, tag field recall, and analytics."""

from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from statistics import median

from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone
from django.utils.text import slugify

from .models import ArchivedLane, DataPoint, Event, Tag
from .search import search_events


@transaction.atomic
def create_event(
    user,
    title: str,
    *,
    notes: str = "",
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    is_ongoing: bool = False,
    all_day: bool = False,
    tag_names: Iterable[str] = (),
    data_points: Iterable[tuple[str, str] | dict] = (),
    parent: Event | None = None,
) -> Event:
    if all_day:
        started_at = _midnight(started_at or timezone.now())
        ended_at = _midnight(ended_at) if ended_at else None
    event = Event._base_manager.create(
        owner=user,
        parent=parent,
        title=title.strip(),
        notes=(notes or "").strip(),
        started_at=started_at or timezone.now(),
        ended_at=ended_at,
        is_ongoing=bool(is_ongoing and ended_at is None),
        all_day=all_day,
    )

    tags = []
    for raw_tag in tag_names:
        tag = Tag.get_or_create_for_user(raw_tag, user)
        if tag is not None:
            tags.append(tag)
    if tags:
        event.tags.set(tags)

    _replace_data_points(event, user, data_points)
    event.rebuild_search_document(save=True)
    return event


@transaction.atomic
def update_event(
    event: Event,
    *,
    title: str | None = None,
    notes: str | None = None,
    append_note: str | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = ...,
    is_ongoing: bool | None = None,
    all_day: bool | None = None,
    tag_names: Iterable[str] | None = None,
    data_points: Iterable[tuple[str, str] | dict] | None = None,
    parent: Event | None = ...,
) -> Event:
    if title is not None:
        event.title = title.strip()
    if notes is not None:
        event.notes = notes.strip()
    if append_note:
        stamp = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M")
        entry = (
            f"\n\n**[{stamp}]** {append_note.strip()}"
            if event.notes
            else f"**[{stamp}]** {append_note.strip()}"
        )
        event.notes = f"{event.notes}{entry}"
    if started_at is not None:
        event.started_at = started_at
    if ended_at is not ...:
        event.ended_at = ended_at
        if ended_at is not None:
            event.is_ongoing = False
    if is_ongoing is not None:
        event.is_ongoing = bool(is_ongoing and event.ended_at is None)
    if parent is not ...:
        event.parent = parent
    if all_day is not None:
        event.all_day = all_day
    if event.all_day:
        event.started_at = _midnight(event.started_at)
        event.ended_at = _midnight(event.ended_at) if event.ended_at else None

    event.save()

    if tag_names is not None:
        tags = []
        for raw_tag in tag_names:
            tag = Tag.get_or_create_for_user(raw_tag, event.owner)
            if tag is not None:
                tags.append(tag)
        event.tags.set(tags)

    if data_points is not None:
        _replace_data_points(event, event.owner, data_points)

    event.rebuild_search_document(save=True)
    return event


def _midnight(dt: datetime) -> datetime:
    """The local start of dt's day: where all-day events sit."""
    day = timezone.localtime(dt).date()
    return timezone.make_aware(datetime.combine(day, time.min))


def _replace_data_points(
    event: Event, user, items: Iterable[tuple[str, str] | dict]
) -> None:
    event.data_points.all().delete()
    for idx, item in enumerate(items):
        if isinstance(item, dict):
            key = str(item.get("key", "")).strip()
            value = str(item.get("value", item.get("value_text", ""))).strip()
            unit = str(item.get("unit", "")).strip()
        else:
            key, value = str(item[0]).strip(), str(item[1]).strip()
            unit = str(item[2]).strip() if len(item) > 2 else ""

        if not key or not value:
            continue

        DataPoint._base_manager.create(
            owner=user,
            event=event,
            key=key,
            value_text=value,
            unit=unit,
            order=idx,
        )


def get_suggested_fields(user, tag_names: Iterable[str], limit: int = 8) -> list[dict]:
    """Return previously used DataPoint keys for events matching the given tags.

    Ranked by usage frequency, then recency. Includes the most common unit and
    most recent sample value so the UI can render helpful placeholders.
    """
    slugs = [
        slugify(t.lstrip("#")) or t.lstrip("#").lower()
        for t in tag_names
        if t and t.strip()
    ]
    if not slugs:
        return []

    matching_events = Event._base_manager.filter(
        owner=user, tags__slug__in=slugs
    ).distinct()

    key_stats = (
        DataPoint._base_manager.filter(owner=user, event__in=matching_events)
        .values("key")
        .annotate(count=Count("id"), last_used=Max("event__started_at"))
        .order_by("-count", "-last_used")[:limit]
    )

    suggestions = []
    for row in key_stats:
        key = row["key"]
        latest_dp = (
            DataPoint._base_manager.filter(
                owner=user, event__in=matching_events, key=key
            )
            .select_related("event")
            .order_by("-event__started_at", "-id")
            .first()
        )
        suggestions.append(
            {
                "key": key,
                "count": row["count"],
                "unit": latest_dp.unit if latest_dp else "",
                "sample_value": latest_dp.value_text if latest_dp else "",
                "is_numeric": latest_dp.value_num is not None if latest_dp else False,
            }
        )
    return suggestions


def get_tag_stats(user, tag_slug: str) -> dict | None:
    """Compute interval statistics and numeric data point series for a tag."""
    slug = slugify(tag_slug.lstrip("#")) or tag_slug.lstrip("#").lower()
    tag = Tag._base_manager.filter(owner=user, slug=slug).first()
    if tag is None:
        return None

    events = list(
        Event._base_manager.filter(owner=user, tags=tag)
        .prefetch_related("data_points")
        .order_by("started_at")
    )
    count = len(events)
    now = timezone.now()

    last_event_at = events[-1].started_at if events else None
    days_since_last = (
        round((now - last_event_at).total_seconds() / 86400, 1)
        if last_event_at is not None
        else None
    )

    intervals_days: list[float] = []
    for prev, curr in zip(events, events[1:], strict=False):
        delta_days = (curr.started_at - prev.started_at).total_seconds() / 86400
        if delta_days >= 0:
            intervals_days.append(round(delta_days, 2))

    numeric_series: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        for dp in ev.data_points.all():
            if dp.value_num is not None:
                numeric_series[dp.key].append(
                    {
                        "event_id": ev.id,
                        "title": ev.title,
                        "t": ev.started_at.isoformat(),
                        "v": dp.value_num,
                        "unit": dp.unit,
                    }
                )

    return {
        "tag": {
            "id": tag.id,
            "name": tag.name,
            "slug": tag.slug,
            "color": tag.color,
        },
        "count": count,
        "ongoing_count": sum(1 for e in events if e.shape == "ongoing"),
        "last_event_at": last_event_at.isoformat() if last_event_at else None,
        "days_since_last": days_since_last,
        "avg_interval_days": (
            round(sum(intervals_days) / len(intervals_days), 1)
            if intervals_days
            else None
        ),
        "min_interval_days": min(intervals_days) if intervals_days else None,
        "max_interval_days": max(intervals_days) if intervals_days else None,
        "numeric_series": dict(numeric_series),
    }


def get_tag_combo_lanes(
    user,
    *,
    q: str = "",
    after: datetime | None = None,
    tags: Iterable[str] = (),
    archived: bool = False,
) -> dict:
    """One lane per exact tag combination, so #dog and #dog #puke stay apart.

    Tag filters (in ``q`` or ``tags``) match events containing all of them: "dog"
    yields the #dog and #dog #puke lanes, "puke" only #dog #puke. Untagged events
    get a lane with no tags. Archived lanes are left out unless ``archived``; each
    lane says whether it is. Used by the dashboard, the REST API and MCP.
    """
    events = list(
        search_events(
            Event._base_manager.filter(owner=user).prefetch_related(
                "tags", "data_points"
            ),
            q=q,
            extra_tags=[t.lstrip("#") for t in tags if t and t.strip()],
            after=after,
        ).order_by("started_at")
    )
    now = timezone.now()

    lanes: dict[tuple[str, ...], dict] = {}
    for ev in events:
        tags = sorted(ev.tags.all(), key=lambda t: t.name)
        key = _combo(ev)
        lane = lanes.setdefault(
            key,
            {
                "key": " ".join(key),
                "url_key": lane_url_key(key),
                "tags": [
                    {"name": t.name, "slug": t.slug, "color": t.color} for t in tags
                ],
                "events": [],
                "numeric_series": defaultdict(list),
            },
        )
        end = ev.end_bound or (now if ev.is_ongoing else None)
        lane["events"].append(
            {
                "id": ev.id,
                "title": ev.title,
                "shape": ev.shape,
                "start": ev.started_at.isoformat(),
                # an ongoing event logged in the future still needs a visible bar
                "end": max(end, ev.started_at).isoformat() if end else None,
                "is_ongoing": ev.is_ongoing,
                "all_day": ev.all_day,
            }
        )
        for dp in ev.data_points.all():
            if dp.value_num is not None:
                lane["numeric_series"][dp.key].append(
                    {"t": ev.started_at.isoformat(), "v": dp.value_num, "unit": dp.unit}
                )

    for lane in lanes.values():
        starts = [datetime.fromisoformat(e["start"]) for e in lane["events"]]
        gaps = [(b - a).total_seconds() / 86400 for a, b in zip(starts, starts[1:])]
        lane["count"] = len(starts)
        lane["avg_interval_days"] = round(sum(gaps) / len(gaps), 1) if gaps else None
        lane["days_since_last"] = round((now - starts[-1]).total_seconds() / 86400, 1)
        lane["numeric_series"] = {
            k: v for k, v in lane["numeric_series"].items() if len(v) >= 2
        }

    shelved = archived_lane_keys(user)
    for lane in lanes.values():
        lane["archived"] = lane["key"] in shelved
    archived_count = sum(lane["archived"] for lane in lanes.values())
    if not archived:
        lanes = {k: v for k, v in lanes.items() if not v["archived"]}
        events = [e for e in events if _combo(e) in lanes]

    ordered = sorted(lanes.values(), key=lambda lane: (not lane["tags"], lane["key"]))
    if events:
        range_start = min(e.started_at for e in events)
        range_end = max(
            now, *(max(e.started_at, e.end_bound or e.started_at) for e in events)
        )
    else:
        range_start, range_end = now - timezone.timedelta(days=30), now
    return {
        "range_start": (after or range_start).isoformat(),
        "range_end": range_end.isoformat(),
        "now": now.isoformat(),
        "starts_at_filter": after is not None,  # a range filter is a hard left edge
        "total_events": len(events),
        "archived_count": archived_count,
        "lanes": ordered,
    }


def _combo(ev: Event) -> tuple[str, ...]:
    return tuple(t.slug for t in sorted(ev.tags.all(), key=lambda t: t.name))


def _hours(td: timedelta) -> float:
    return round(td.total_seconds() / 3600, 1)


def _due(next_at: datetime, now: datetime) -> dict:
    days = (next_at - now).total_seconds() / 86400
    state = "now" if abs(days) < 1 else "ahead" if days > 0 else "late"
    return {"state": state, "days": round(abs(days))}


def lane_url_key(slugs: Iterable[str]) -> str:
    """"dog puke" -> "dog+puke"; the untagged lane is "~" (never a slug)."""
    return "+".join(slugs) or "~"


def archived_lane_keys(user) -> set[str]:
    """Keys of lanes still archived: nothing with that exact combo logged since."""
    rows = dict(
        ArchivedLane._base_manager.filter(owner=user).values_list("key", "archived_at")
    )
    if not rows:
        return set()
    newer = Event._base_manager.filter(
        owner=user, created_at__gt=min(rows.values())
    ).prefetch_related("tags")
    revived = {
        key
        for ev in newer
        if (key := " ".join(_combo(ev))) in rows and ev.created_at > rows[key]
    }
    return set(rows) - revived


def set_lane_archived(user, key: str, archived: bool) -> None:
    if archived:
        ArchivedLane._base_manager.update_or_create(
            owner=user, key=key, defaults={"archived_at": timezone.now()}
        )
    else:
        ArchivedLane._base_manager.filter(owner=user, key=key).delete()


def get_lane_detail(user, slugs: list[str]) -> dict | None:
    """Everything the lane page shows for one exact tag combination."""
    key = " ".join(slugs)
    data = get_tag_combo_lanes(user, tags=slugs, archived=True)
    lane = next((x for x in data["lanes"] if x["key"] == key), None)
    if lane is None:
        return None

    tz = timezone.get_current_timezone()
    now = timezone.now()
    evs = lane["events"]
    starts = [datetime.fromisoformat(e["start"]) for e in evs]
    gaps = [
        {"t": b.isoformat(), "days": round((b - a).total_seconds() / 86400, 2)}
        for a, b in zip(starts, starts[1:])
    ]
    avg = lane["avg_interval_days"]
    next_at = starts[-1] + timedelta(days=avg) if avg else None

    weekdays = [0] * 7  # Monday first
    for s in starts:
        weekdays[s.astimezone(tz).weekday()] += 1

    hours = [0] * 24  # all-day events have no time of day
    for e, s in zip(evs, starts):
        if not e["all_day"]:
            hours[s.astimezone(tz).hour] += 1

    durations = [
        datetime.fromisoformat(e["end"]) - datetime.fromisoformat(e["start"])
        for e in evs
        if e["end"]
    ]
    running = sum(durations, timedelta())
    avg_duration = running / len(durations) if durations else None

    last_30 = sum(1 for s in starts if s > now - timedelta(days=30))
    prev_30 = sum(1 for s in starts if now - timedelta(days=60) < s <= now - timedelta(days=30))

    fields = [
        {
            "key": k,
            "points": pts,
            "unit": pts[-1]["unit"],
            "min": min(p["v"] for p in pts),
            "max": max(p["v"] for p in pts),
            "avg": sum(p["v"] for p in pts) / len(pts),
        }
        for k, pts in lane["numeric_series"].items()
    ]
    text_values = defaultdict(Counter)
    for k, v in DataPoint._base_manager.filter(
        owner=user, event_id__in=[e["id"] for e in evs], value_num__isnull=True
    ).values_list("key", "value_text"):
        text_values[k][v] += 1
    text_fields = [
        {"key": k, "top": c.most_common(5), "max": c.most_common(1)[0][1]}
        for k, c in sorted(text_values.items())
    ]

    return {
        **lane,
        "first_at": starts[0],
        "last_at": starts[-1],
        "hours_since_last": max(_hours(now - starts[-1]), 0),
        "gaps": gaps,
        "longest_gap": max((g["days"] for g in gaps), default=None),
        "shortest_gap": min((g["days"] for g in gaps), default=None),
        "next_at": next_at,
        # "ahead" (due in N days), "now" (within a day) or "late" (N days past its pace)
        "due": _due(next_at, now) if next_at else None,
        # how far into its usual gap it is, on a track 1.5 gaps long (due sits at 2/3)
        "pace_pct": (
            round(max(min(lane["days_since_last"] / avg, 1.5), 0) / 1.5 * 100, 1)
            if avg
            else None
        ),
        # 2024-01-01 was a Monday; the template formats these as weekday names
        "weekdays": [
            {"day": date(2024, 1, 1 + i), "n": n, "pct": round(100 * n / max(weekdays))}
            for i, n in enumerate(weekdays)
        ],
        "has_times": any(hours),
        "hours": [
            {"hour": h, "n": n, "pct": round(100 * n / max(*hours, 1))}
            for h, n in enumerate(hours)
        ],
        "median_gap": round(median(g["days"] for g in gaps), 1) if gaps else None,
        "last_30": last_30,
        "trend_30": last_30 - prev_30,
        "running_hours": _hours(running),
        "avg_duration_hours": _hours(avg_duration) if avg_duration else None,
        "fields": fields,
        "text_fields": text_fields,
        "recent": [
            {**e, "at": datetime.fromisoformat(e["start"])} for e in reversed(evs[-15:])
        ],
    }


def get_calendar_month(
    user, *, year: int, month: int, q: str = "", first_weekday: int = 1
) -> dict:
    """A month as weeks for the calendar page.

    ``first_weekday`` uses Django's FIRST_DAY_OF_WEEK numbering (0 = Sunday). Each
    week holds its 7 days with their single-day events ("points"), plus "bars" for
    events covering more than one day (spans, and running events up to today),
    clipped to the week and stacked into rows so they never overlap.
    """
    tz = timezone.get_current_timezone()
    today = timezone.localdate()
    now = timezone.now()

    first = date(year, month, 1)
    next_month = date(year + (month == 12), month % 12 + 1, 1)
    py_first = (first_weekday - 1) % 7  # Django: Sun=0..Sat=6; Python: Mon=0..Sun=6
    grid_start = first - timedelta(days=(first.weekday() - py_first) % 7)
    weeks_n = -(-((next_month - grid_start).days) // 7)
    grid_end = grid_start + timedelta(days=weeks_n * 7)  # exclusive

    def at(day):
        return timezone.make_aware(datetime.combine(day, time.min), tz)

    events = list(
        search_events(
            Event._base_manager.filter(owner=user).prefetch_related("tags"), q=q
        )
        .filter(started_at__lt=at(grid_end))
        .filter(
            Q(started_at__gte=at(grid_start))
            | Q(ended_at__gte=at(grid_start))
            | Q(is_ongoing=True, ended_at__isnull=True)
        )
        .order_by("started_at")
    )

    def payload(ev, start_day, end_day):
        tag = next(iter(ev.tags.all()), None)
        return {
            "id": ev.id,
            "title": ev.title,
            "color": tag.color if tag else None,
            "time": ""
            if ev.all_day
            else timezone.localtime(ev.started_at).strftime("%H:%M"),
            "is_ongoing": ev.is_ongoing and ev.ended_at is None,
            "start": start_day,
            "end": end_day,
        }

    items = []
    for ev in events:
        start_day = timezone.localtime(ev.started_at).date()
        end_dt = ev.ended_at or (now if ev.is_ongoing else None)
        end_day = (
            timezone.localtime(max(end_dt, ev.started_at)).date()
            if end_dt
            else start_day
        )
        items.append(payload(ev, start_day, end_day))

    weeks = []
    for w in range(weeks_n):
        week_start = grid_start + timedelta(days=7 * w)
        week_end = week_start + timedelta(days=6)
        days = [
            {
                "date": week_start + timedelta(days=i),
                "in_month": (week_start + timedelta(days=i)).month == month,
                "is_today": week_start + timedelta(days=i) == today,
                "points": [],
            }
            for i in range(7)
        ]
        bars, row_ends = [], []  # row_ends[r]: last column used in row r
        for item in items:
            if item["end"] > item["start"]:
                if item["start"] > week_end or item["end"] < week_start:
                    continue
                col_start = (max(item["start"], week_start) - week_start).days
                col_end = (min(item["end"], week_end) - week_start).days
                row = next(
                    (r for r, last in enumerate(row_ends) if last < col_start), None
                )
                if row is None:
                    row = len(row_ends)
                    row_ends.append(col_end)
                else:
                    row_ends[row] = col_end
                bars.append(
                    {
                        **item,
                        "col_start": col_start,
                        "col_end": col_end,
                        "row": row,
                        "cut_left": item["start"] < week_start,
                        "cut_right": item["end"] > week_end,
                    }
                )
            elif week_start <= item["start"] <= week_end:
                days[(item["start"] - week_start).days]["points"].append(item)
        weeks.append({"days": days, "bars": bars, "rows": len(row_ends)})

    prev_month = first - timedelta(days=1)
    return {
        "month": first,
        "prev": f"{prev_month:%Y-%m}",
        "next": f"{next_month:%Y-%m}",
        "weekdays": [day["date"] for day in weeks[0]["days"]] if weeks else [],
        "weeks": weeks,
        "total_events": len(items),
    }
