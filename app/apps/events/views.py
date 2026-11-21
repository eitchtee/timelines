"""Views for Timelines: dashboard, search, quick-capture, overlay, and detail drawer."""

import json
from datetime import datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.formats import date_format, get_format, time_format
from django.utils.timesince import timesince
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from .dates import canonical, parse_loose, prefers_day_first, readings
from .models import DataPoint, Event, Tag
from .parser import parse_quick_input
from .search import parse_search_query, search_events
from .services import (
    create_event,
    get_calendar_month,
    get_lane_detail,
    get_suggested_fields,
    get_tag_combo_lanes,
    set_lane_archived,
    update_event,
)

RANGE_DELTAS = {
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
    "1y": timedelta(days=365),
}


def _parse_local_datetime(raw: str | None):
    if not raw or not raw.strip():
        return None
    dt = parse_datetime(raw.strip())
    if dt is None:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _parse_clock(raw: str | None) -> time | None:
    """"09:30" -> time(9, 30); blank or malformed -> None (no time: all day)."""
    try:
        h, m = (int(p) for p in (raw or "").strip().split(":"))
        return time(h, m)
    except ValueError:
        return None


def _at_local(day, time_of_day):
    return timezone.make_aware(
        datetime.combine(day, time_of_day), timezone.get_current_timezone()
    )


def _extract_data_points_from_post(post) -> list[tuple[str, str, str]]:
    keys = post.getlist("dp_key")
    vals = post.getlist("dp_val")
    units = post.getlist("dp_unit")
    items = []
    for idx, k in enumerate(keys):
        v = vals[idx] if idx < len(vals) else ""
        u = units[idx] if idx < len(units) else ""
        if k.strip() and v.strip():
            items.append((k.strip(), v.strip(), u.strip()))
    return items


def _build_workspace_context(request, view_mode: str | None = None) -> dict:
    """Shared by the Feed and Lanes pages and their htmx refreshes."""
    user = request.user
    q = (request.GET.get("q") or "").strip()
    view_mode = view_mode or request.GET.get("view", "feed")
    if view_mode not in {"feed", "timeline", "calendar"}:
        view_mode = "feed"
    range_key = request.GET.get("range", "all")
    after = (
        timezone.now() - RANGE_DELTAS[range_key] if range_key in RANGE_DELTAS else None
    )

    raw_tags = [t.strip() for t in request.GET.getlist("tag") if t.strip()]
    parsed_q = parse_search_query(q)
    active_tags = list(dict.fromkeys([*parsed_q.include_tags, *raw_tags]))

    base_qs = (
        Event._base_manager.filter(owner=user)
        .prefetch_related("tags", "data_points")
        .select_related("parent")
    )

    events = list(
        search_events(
            base_qs,
            q=q,
            extra_tags=raw_tags,
            after=after,
        )[:200]
    )

    ongoing_events = list(
        Event._base_manager.filter(owner=user, is_ongoing=True, ended_at__isnull=True)
        .prefetch_related("tags", "data_points")
        .order_by("-started_at")[:10]
    )

    user_tags = list(
        Tag._base_manager.filter(owner=user)
        .annotate(event_count=Count("events"), last_used=Max("events__started_at"))
        .order_by("-event_count", "name")[:40]
    )

    show_archived = request.GET.get("archived") == "1"
    lanes = (
        get_tag_combo_lanes(user, q=q, after=after, archived=show_archived)
        if view_mode == "timeline"
        else None
    )

    # the calendar pages by month (?month=2026-11) and ignores the range filter
    calendar = None
    month_key = ""
    if view_mode == "calendar":
        try:
            shown = datetime.strptime(request.GET.get("month") or "", "%Y-%m").date()
        except ValueError:
            shown = timezone.localdate().replace(day=1)
        month_key = f"{shown:%Y-%m}"
        calendar = get_calendar_month(
            user,
            year=shown.year,
            month=shown.month,
            q=q,
            first_weekday=int(get_format("FIRST_DAY_OF_WEEK")),
        )

    return {
        "q": q,
        "view_mode": view_mode,
        "range_key": range_key,
        "range_choices": [*((k, k) for k in RANGE_DELTAS), ("all", _("All"))],
        "active_tags": active_tags,
        "events": events,
        "ongoing_events": ongoing_events,
        "user_tags": user_tags,
        "lanes": lanes,
        "show_archived": show_archived,
        "calendar": calendar,
        "month_key": month_key,
    }


@login_required
@require_GET
def dashboard(request):
    # old links: /?view=timeline now lives at /lanes/
    if request.GET.get("view") == "timeline":
        params = request.GET.copy()
        params.pop("view")
        query = f"?{params.urlencode()}" if params else ""
        return redirect(f"{reverse('lanes')}{query}")
    ctx = _build_workspace_context(request, view_mode="feed")
    return render(request, "events/dashboard.html", ctx)


@login_required
@require_GET
def calendar(request):
    ctx = _build_workspace_context(request, view_mode="calendar")
    return render(request, "events/dashboard.html", ctx)


@login_required
@require_GET
def lanes(request):
    ctx = _build_workspace_context(request, view_mode="timeline")
    return render(request, "events/dashboard.html", ctx)


def _lane_slugs(key: str) -> list[str]:
    return [] if key == "~" else key.split("+")


@login_required
@require_GET
def lane_detail(request, key: str):
    lane = get_lane_detail(request.user, _lane_slugs(key))
    if lane is None:
        messages.info(request, _("Nothing is logged in that lane anymore."))
        return redirect("lanes")
    return render(request, "events/lane.html", {"lane": lane})


@login_required
@require_POST
def lane_archive(request, key: str):
    archive = request.POST.get("archived") == "1"
    set_lane_archived(request.user, " ".join(_lane_slugs(key)), archive)
    if archive:
        messages.success(
            request, _("Archived. It comes back on its own when you log to it again.")
        )
    else:
        messages.success(request, _("Back on the Lanes page."))
    return redirect("lane_detail", key=key)


@login_required
@require_GET
def workspace_results(request):
    ctx = _build_workspace_context(request)
    template = {
        "timeline": "events/fragments/timeline.html",
        "calendar": "events/fragments/calendar.html",
    }.get(ctx["view_mode"], "events/fragments/feed.html")
    return render(request, template, ctx)


@login_required
@require_POST
def quick_create(request):
    raw_input = (request.POST.get("quick_input") or "").strip()
    parsed = parse_quick_input(raw_input)

    title = (request.POST.get("title") or "").strip() or parsed.title
    if not title:
        messages.error(request, _("Please enter an event title or #tag."))
        return HttpResponse(status=400, headers={"HX-Trigger": "updated"})

    notes = request.POST.get("notes") or ""
    shape = request.POST.get("shape") or ("ongoing" if parsed.is_ongoing else "point")
    is_ongoing = shape == "ongoing" or parsed.is_ongoing

    all_day = False
    when_preset = request.POST.get("when_preset", "now")
    started_at = _parse_local_datetime(request.POST.get("started_at"))
    if started_at is None:
        now = timezone.now()
        if when_preset == "1h":
            started_at = now - timedelta(hours=1)
        elif when_preset == "yesterday":
            started_at = now - timedelta(days=1)
        else:
            started_at = now

    ended_at = (
        _parse_local_datetime(request.POST.get("ended_at"))
        if shape == "range"
        else None
    )
    # @date in the text: used unless the Details form set an exact time
    if parsed.when and not request.POST.get("started_at"):
        loose = parse_loose(
            parsed.when, timezone.localdate(), day_first=prefers_day_first()
        )
        options = readings(loose, timezone.localdate()) if loose else []
        if options:
            start, end = options[0]
            # a date without any time is an all-day event
            all_day = start.at is None and (end is None or end.at is None)
            started_at = _at_local(start.day, start.at or time.min)
            if end is not None:
                end_time = time.min if all_day else (end.at or start.at or time.min)
                ended_at, is_ongoing = _at_local(end.day, end_time), False
            elif loose.open_ended:
                ended_at, is_ongoing = None, True

    if ended_at is not None:
        is_ongoing = False

    extra_tags_raw = request.POST.get("extra_tags") or ""
    extra_tags = [t.strip().lstrip("#") for t in extra_tags_raw.split(",") if t.strip()]
    all_tags = list(dict.fromkeys([*parsed.tags, *extra_tags]))

    dp_items = [(k, v, "") for k, v in parsed.data_points]
    dp_items.extend(_extract_data_points_from_post(request.POST))

    parent = None
    parent_id = request.POST.get("parent_id")
    if parent_id and parent_id.isdigit():
        parent = Event._base_manager.filter(
            owner=request.user, pk=int(parent_id)
        ).first()

    event = create_event(
        request.user,
        title=title,
        notes=notes,
        started_at=started_at,
        ended_at=ended_at,
        is_ongoing=is_ongoing,
        all_day=all_day,
        tag_names=all_tags,
        data_points=dp_items,
        parent=parent,
    )

    messages.success(request, _("Logged: %(title)s") % {"title": event.title})

    # Re-render the current workspace view; the id lets the feed highlight the new row
    response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps(
        {"updated": True, "eventsChanged": {"id": event.id}}
    )
    return response


@login_required
@require_GET
def suggested_fields(request):
    raw_tags = request.GET.get("tags", "")
    tag_list = [t.strip().lstrip("#") for t in raw_tags.split(",") if t.strip()]
    suggestions = get_suggested_fields(request.user, tag_list)
    return render(
        request,
        "events/fragments/suggested_fields.html",
        {"suggestions": suggestions},
    )


@login_required
@require_GET
def event_detail(request, pk: int):
    event = get_object_or_404(
        Event._base_manager.filter(owner=request.user).prefetch_related(
            "tags", "data_points", "children__tags"
        ),
        pk=pk,
    )
    ongoing_parents = Event._base_manager.filter(
        owner=request.user, is_ongoing=True, ended_at__isnull=True
    ).exclude(pk=event.pk)
    return render(
        request,
        "events/fragments/detail_drawer.html",
        {
            "event": event,
            "ongoing_parents": ongoing_parents,
        },
    )


@login_required
@require_POST
def event_edit(request, pk: int):
    event = get_object_or_404(Event._base_manager.filter(owner=request.user), pk=pk)
    title = (request.POST.get("title") or "").strip() or event.title
    notes = request.POST.get("notes", event.notes)
    # a date with no time is all day; the end's time follows the start's
    start_day = parse_date(request.POST.get("start_date") or "")
    start_time = _parse_clock(request.POST.get("start_time"))
    if start_day:
        all_day = start_time is None
        started_at = _at_local(start_day, start_time or time.min)
    else:
        all_day, started_at = event.all_day, event.started_at
    end_day = parse_date(request.POST.get("end_date") or "")
    end_time = None if all_day else _parse_clock(request.POST.get("end_time"))
    ended_at = (
        _at_local(end_day, end_time or start_time or time.min) if end_day else None
    )
    is_ongoing = request.POST.get("is_ongoing") == "on" and ended_at is None

    # a multi-select posts one value per tag; older clients post one comma-separated string
    tag_names = [
        t.strip().lstrip("#")
        for raw in request.POST.getlist("tags")
        for t in raw.split(",")
        if t.strip()
    ]
    # fields are edited from the inspect view now; only replace them if this form sent some
    data_points = (
        _extract_data_points_from_post(request.POST)
        if "dp_key" in request.POST
        else None
    )

    update_event(
        event,
        title=title,
        notes=notes,
        started_at=started_at,
        ended_at=ended_at,
        is_ongoing=is_ongoing,
        all_day=all_day,
        tag_names=tag_names,
        data_points=data_points,
    )
    messages.success(request, _("Event updated."))

    response = render(
        request,
        "events/fragments/detail_drawer.html",
        {
            "event": event,
        },
    )
    response["HX-Trigger"] = json.dumps({"updated": True, "eventsChanged": True})
    return response


@login_required
@require_POST
def event_stop(request, pk: int):
    event = get_object_or_404(Event._base_manager.filter(owner=request.user), pk=pk)
    event.stop()
    messages.success(request, _("Ended: %(title)s") % {"title": event.title})

    if request.POST.get("from_drawer") == "1":
        response = render(
            request,
            "events/fragments/detail_drawer.html",
            {
                "event": event,
            },
        )
    else:
        response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps({"updated": True, "eventsChanged": True})
    return response


@login_required
@require_POST
def event_append_note(request, pk: int):
    event = get_object_or_404(Event._base_manager.filter(owner=request.user), pk=pk)
    note_text = (request.POST.get("note") or "").strip()
    if note_text:
        update_event(event, append_note=note_text)
        messages.success(request, _("Note added."))

    response = render(
        request,
        "events/fragments/detail_drawer.html",
        {
            "event": event,
        },
    )
    response["HX-Trigger"] = json.dumps({"updated": True, "eventsChanged": True})
    return response


def _field_changed_response(request, event):
    """Re-render the drawer after a field change and refresh the feed/lanes behind it."""
    event.rebuild_search_document(save=True)
    response = render(request, "events/fragments/detail_drawer.html", {"event": event})
    response["HX-Trigger"] = json.dumps({"eventsChanged": True})
    return response


@login_required
@require_POST
def event_field_add(request, pk: int):
    """Add fields with quick-log syntax (``weight:4.2kg ate:chicken``).

    A key the event already has gets its value replaced.
    """
    event = get_object_or_404(Event._base_manager.filter(owner=request.user), pk=pk)
    for key, value in parse_quick_input(request.POST.get("fields") or "").data_points:
        norm = key.strip().lower().replace(" ", "_")
        field = event.data_points.filter(key=norm).first()
        if field is None:
            field = DataPoint(
                owner=request.user,
                event=event,
                key=norm,
                order=event.data_points.count(),
            )
        # reset so save() re-reads number and unit from the new text
        field.value_text, field.value_num, field.unit = value, None, ""
        field.save()
    return _field_changed_response(request, event)


@login_required
@require_POST
def event_field_delete(request, pk: int, field_pk: int):
    event = get_object_or_404(Event._base_manager.filter(owner=request.user), pk=pk)
    event.data_points.filter(pk=field_pk).delete()
    return _field_changed_response(request, event)


@login_required
@require_POST
def event_delete(request, pk: int):
    event = get_object_or_404(Event._base_manager.filter(owner=request.user), pk=pk)
    title = event.title
    event.delete()
    messages.success(request, _("Deleted: %(title)s") % {"title": title})
    response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps(
        {"updated": True, "eventsChanged": True, "hide_offcanvas": True}
    )
    return response


@login_required
@require_GET
def tag_autocomplete(request):
    term = (request.GET.get("q") or "").strip().lstrip("#")
    qs = Tag._base_manager.filter(owner=request.user)
    if term:
        qs = qs.filter(name__icontains=term)
    tags = list(
        qs.annotate(event_count=Count("events"))
        .order_by("-event_count", "name")
        .values("id", "name", "slug", "color", "event_count")[:15]
    )
    return JsonResponse({"tags": tags})


@login_required
@require_GET
def date_interpret(request):
    """Readings of a loose date (``@`` in Quick log, ``after:``/``before:`` in search).

    More than one option means the input was ambiguous and the UI should ask.
    """
    raw = (request.GET.get("q") or "").strip()
    single = request.GET.get("single") == "1"  # after:/before: take one day only
    loose = parse_loose(raw, timezone.localdate(), day_first=prefers_day_first())
    if not loose or (single and (loose.ends is not None or loose.open_ended)):
        return JsonResponse({"options": []})

    today = timezone.localdate()

    def label(point):
        day = _("Today") if point.day == today else date_format(point.day, "D, j M Y")
        return f"{day}, {time_format(point.at)}" if point.at else day

    options = []
    for start, end in readings(loose, today)[:4]:
        if end is not None:
            text = f"{label(start)} → {label(end)}"
        elif loose.open_ended:
            text = _("%(date)s, still running") % {"date": label(start)}
        else:
            text = label(start)
        if not single and start.at is None and (end is None or end.at is None):
            text = _("%(date)s, all day") % {"date": text}
        options.append(
            {
                "value": canonical(start, end, open_ended=loose.open_ended),
                "label": text,
            }
        )
    return JsonResponse({"options": options})


@login_required
@require_GET
def field_keys(request):
    """Field names used so far, for ``has:`` and ``key:`` suggestions."""
    term = (request.GET.get("q") or "").strip().lower()
    qs = DataPoint._base_manager.filter(event__owner=request.user)
    if term:
        qs = qs.filter(key__istartswith=term)
    keys = list(
        qs.values("key")
        .annotate(uses=Count("id"))
        .order_by("-uses", "key")
        .values_list("key", flat=True)[:8]
    )
    return JsonResponse({"keys": keys})


@login_required
@require_GET
def ongoing_autocomplete(request):
    """Running events for Quick log's ``>`` (part of) menu."""
    term = (request.GET.get("q") or "").strip()
    qs = (
        Event._base_manager.filter(
            owner=request.user, is_ongoing=True, ended_at__isnull=True
        )
        .prefetch_related("tags")
        .order_by("-started_at")
    )
    if term:
        qs = qs.filter(title__icontains=term)
    events = [
        {
            "id": ev.id,
            "title": ev.title,
            "color": next((t.color for t in ev.tags.all()), None),
            "since": timesince(ev.started_at),
        }
        for ev in qs[:8]
    ]
    return JsonResponse({"events": events})
