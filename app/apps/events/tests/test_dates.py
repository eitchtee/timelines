from datetime import date, datetime, time

import pytest
from apps.events.dates import (
    When,
    canonical,
    date_candidates,
    parse_loose,
    parse_time,
    readings,
)
from apps.events.models import Event
from apps.events.parser import parse_quick_input
from apps.events.search import parse_search_query
from apps.users.models import User
from django.urls import reverse
from django.utils import timezone

TODAY = date(2026, 11, 21)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("20/10", [date(2026, 10, 20)]),  # only one valid reading
        ("20-10", [date(2026, 10, 20)]),
        ("20.10.24", [date(2024, 10, 20)]),
        ("20-10-2024", [date(2024, 10, 20)]),
        ("1/2/2025", [date(2025, 2, 1), date(2025, 1, 2)]),  # ambiguous, day first
        ("10-08", [date(2026, 8, 10), date(2026, 10, 8)]),
        ("10/31/2026", [date(2026, 10, 31)]),  # month-first, unambiguous
        ("2026/10/20", [date(2026, 10, 20)]),
        ("2026-1-5", [date(2026, 1, 5)]),
        ("5/5", [date(2026, 5, 5)]),  # both readings equal: not ambiguous
        ("32/10", []),
        ("2026-10", []),
    ],
)
def test_date_candidates(raw, expected):
    assert date_candidates(raw, TODAY) == expected


def test_month_first_locale_flips_preference():
    assert date_candidates("10-08", TODAY, day_first=False) == [
        date(2026, 10, 8),
        date(2026, 8, 10),
    ]


def W(day, at=None):  # noqa: N802 - reads like the dataclass it builds
    return When(day, at)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("14:30", time(14, 30)),
        ("9:05", time(9, 5)),
        ("14h", time(14, 0)),
        ("14h30", time(14, 30)),
        ("2pm", time(14, 0)),
        ("2:30PM", time(14, 30)),
        ("12am", time(0, 0)),
        ("14", None),  # a bare number is not a time
        ("25:00", None),
        ("13pm", None),
    ],
)
def test_parse_time(raw, expected):
    assert parse_time(raw) == expected


def test_points_with_times():
    assert readings(parse_loose("20/10,14:30", TODAY), TODAY) == [
        (W(date(2026, 10, 20), time(14, 30)), None)
    ]
    assert readings(parse_loose("2026-10-20T09:00", TODAY), TODAY) == [
        (W(date(2026, 10, 20), time(9, 0)), None)
    ]
    # a time alone is today
    assert readings(parse_loose("2pm", TODAY), TODAY) == [(W(TODAY, time(14, 0)), None)]


def test_ranges_and_open_end():
    span = parse_loose("20-10-2026~22-10-2026", TODAY)
    assert readings(span, TODAY) == [(W(date(2026, 10, 20)), W(date(2026, 10, 22)))]

    dots = parse_loose("20/10..22/10", TODAY)
    assert readings(dots, TODAY) == [(W(date(2026, 10, 20)), W(date(2026, 10, 22)))]

    # an end with only a time stays on the start's day
    hours = parse_loose("20/10,9:00~11:30", TODAY)
    assert readings(hours, TODAY) == [
        (W(date(2026, 10, 20), time(9, 0)), W(date(2026, 10, 20), time(11, 30)))
    ]

    running = parse_loose("20/10~", TODAY)
    assert running.open_ended and running.starts == [W(date(2026, 10, 20))]

    # backwards ranges are not a reading
    assert readings(parse_loose("22/10~20/10", TODAY), TODAY) == []

    assert parse_loose("10-08", TODAY).ambiguous
    assert not parse_loose("20/10", TODAY).ambiguous
    assert parse_loose("someday", TODAY) is None


def test_canonical_round_trips():
    for start, end, open_ended in [
        (W(date(2026, 8, 10)), None, False),
        (W(date(2026, 8, 10), time(7, 5)), None, False),
        (W(date(2026, 10, 20)), W(date(2026, 10, 22), time(18, 0)), False),
        (W(date(2026, 10, 20), time(9, 0)), None, True),
    ]:
        text = canonical(start, end, open_ended=open_ended)
        parsed = parse_loose(text, TODAY)
        assert readings(parsed, TODAY)[0] == (start, end)
        assert not parsed.ambiguous
        assert parsed.open_ended == open_ended


def test_quick_input_extracts_at_date():
    parsed = parse_quick_input("Changed filter #filter @20/10 note:x")
    assert parsed.when == "20/10"
    assert parsed.title == "Changed filter"
    assert parse_quick_input("email me@example.com").when is None
    assert parse_quick_input("Call @14:30").when == "14:30"
    # not a date: stays in the title
    unread = parse_quick_input("Bought @99 bottles")
    assert unread.when is None and unread.title == "Bought @99 bottles"


def test_search_after_before_accept_loose_dates():
    parsed = parse_search_query("after:20/10/2026 before:22-10-26")
    assert timezone.localtime(parsed.after).date() == date(2026, 10, 20)
    assert timezone.localtime(parsed.before).date() == date(2026, 10, 22)

    timed = parse_search_query("after:20/10/2026,14:30")
    assert timezone.localtime(timed.after).replace(tzinfo=None) == datetime(
        2026, 10, 20, 14, 30
    )


@pytest.fixture
def client_user(client, db):
    user = User.objects.create_user(email="carol@example.com", password="pw123456")
    client.force_login(user)
    return client, user


def test_quick_create_uses_at_range(client_user):
    client, user = client_user
    res = client.post(
        reverse("event_quick_create"),
        {"quick_input": "Away #trip @20-10-2026,9:00~22-10-2026", "shape": "point"},
    )
    assert res.status_code == 204
    ev = Event._base_manager.get(owner=user, title="Away")
    start, end = timezone.localtime(ev.started_at), timezone.localtime(ev.ended_at)
    assert (start.date(), start.time()) == (date(2026, 10, 20), time(9, 0))
    assert (end.date(), end.time()) == (date(2026, 10, 22), time(9, 0))
    assert not ev.is_ongoing


def test_date_interpret_lists_ambiguous_readings(client_user):
    client, _ = client_user
    data = client.get(reverse("date_interpret"), {"q": "10-08-2026"}).json()
    # both readings offered; their order follows the request locale
    assert sorted(o["value"] for o in data["options"]) == ["2026-08-10", "2026-10-08"]
    single = client.get(
        reverse("date_interpret"), {"q": "20/10~", "single": "1"}
    ).json()
    assert single["options"] == []


def test_event_edit_accepts_tag_list_and_csv(client_user):
    client, user = client_user
    client.post(reverse("event_quick_create"), {"quick_input": "Walk #dog"})
    ev = Event._base_manager.get(owner=user, title="Walk")
    url = reverse("event_edit", kwargs={"pk": ev.pk})

    client.post(url, {"title": "Walk", "tags": ["dog", "park"]})  # multi-select
    assert sorted(t.name for t in ev.tags.all()) == ["dog", "park"]

    client.post(url, {"title": "Walk", "tags": "dog, #rain"})  # old comma field
    assert sorted(t.name for t in ev.tags.all()) == ["dog", "rain"]
