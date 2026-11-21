from datetime import date, datetime, timedelta

import pytest
from apps.events.services import create_event, get_calendar_month
from apps.users.models import User
from django.urls import reverse
from django.utils import timezone


@pytest.fixture
def user(db):
    return User.objects.create_user(email="cal@example.com", password="pw123456")


def at(day, hour=12):
    return timezone.make_aware(
        datetime.combine(day, datetime.min.time()).replace(hour=hour)
    )


def test_month_grid_starts_on_the_locale_week_start(user):
    # November 2026 starts on a Sunday
    sunday_first = get_calendar_month(user, year=2026, month=11, first_weekday=0)
    assert sunday_first["weeks"][0]["days"][0]["date"] == date(2026, 11, 1)
    monday_first = get_calendar_month(user, year=2026, month=11, first_weekday=1)
    assert monday_first["weeks"][0]["days"][0]["date"] == date(2026, 10, 26)
    assert all(len(w["days"]) == 7 for w in monday_first["weeks"])
    assert (sunday_first["prev"], sunday_first["next"]) == ("2026-10", "2026-12")


def test_points_bars_and_stacking(user):
    create_event(user, "Walk", started_at=at(date(2026, 11, 4)), tag_names=["dog"])
    # Thu 5 -> Mon 9: crosses the Sunday-start week boundary
    create_event(
        user, "Trip", started_at=at(date(2026, 11, 5)), ended_at=at(date(2026, 11, 9))
    )
    create_event(
        user, "Guests", started_at=at(date(2026, 11, 6)), ended_at=at(date(2026, 11, 7))
    )

    cal = get_calendar_month(user, year=2026, month=11, first_weekday=0)
    week1, week2 = cal["weeks"][0], cal["weeks"][1]  # Nov 1-7, Nov 8-14

    assert [p["title"] for p in week1["days"][3]["points"]] == ["Walk"]  # Wed 4

    trip1 = next(b for b in week1["bars"] if b["title"] == "Trip")
    assert (trip1["col_start"], trip1["col_end"], trip1["cut_right"]) == (4, 6, True)
    trip2 = next(b for b in week2["bars"] if b["title"] == "Trip")
    assert (trip2["col_start"], trip2["col_end"], trip2["cut_left"]) == (0, 1, True)

    # overlapping bars get separate rows
    guests = next(b for b in week1["bars"] if b["title"] == "Guests")
    assert guests["row"] != trip1["row"]
    assert week1["rows"] == 2


def test_running_event_reaches_today_and_search_filters(user):
    today = timezone.localdate()
    create_event(
        user,
        "Meds",
        started_at=at(today - timedelta(days=3)),
        is_ongoing=True,
        tag_names=["meds"],
    )
    create_event(user, "Other", started_at=at(today), tag_names=["misc"])

    cal = get_calendar_month(user, year=today.year, month=today.month, q="#meds")
    bars = [b for w in cal["weeks"] for b in w["bars"]]
    assert bars and all(b["is_ongoing"] for b in bars)
    assert max(b["end"] for b in bars) == today
    points = [p for w in cal["weeks"] for d in w["days"] for p in d["points"]]
    assert not points  # "Other" is filtered out by the search
    assert cal["total_events"] == 1


def test_calendar_page_renders(client, user):
    client.force_login(user)
    create_event(user, "Walk", started_at=at(date(2026, 11, 4)), tag_names=["dog"])
    page = client.get(reverse("calendar"), {"month": "2026-11"})
    assert page.status_code == 200
    assert b"Walk" in page.content
    assert page.context["month_key"] == "2026-11"
    frag = client.get(reverse("events_results"), {"view": "calendar", "month": "bogus"})
    assert frag.status_code == 200  # falls back to the current month
