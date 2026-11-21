from datetime import timedelta

import pytest
from apps.events.models import Event, Tag, parse_value_and_unit
from apps.events.parser import parse_quick_input
from apps.events.search import search_events
from apps.events.services import (
    create_event,
    get_suggested_fields,
    get_tag_combo_lanes,
    get_tag_stats,
    update_event,
)
from apps.users.models import User
from django.utils import timezone


@pytest.fixture
def user(db):
    return User.objects.create_user(email="alice@example.com", password="password123")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(email="bob@example.com", password="password123")


def test_parse_value_and_unit():
    assert parse_value_and_unit("14%") == ("14", 14.0, "%")
    assert parse_value_and_unit("400mg") == ("400", 400.0, "mg")
    assert parse_value_and_unit("38.5 C") == ("38.5", 38.5, "C")
    assert parse_value_and_unit("chicken") == ("chicken", None, "")


def test_parse_quick_input():
    parsed = parse_quick_input(
        'Charged watch #smartwatch #charge battery:14% note:"fast charger"'
    )
    assert parsed.title == "Charged watch"
    assert parsed.tags == ["smartwatch", "charge"]
    assert parsed.data_points == [("battery", "14%"), ("note", "fast charger")]
    assert parsed.is_ongoing is False

    ongoing = parse_quick_input("Started ibuprofen #health #meds dose:400mg !ongoing")
    assert ongoing.title == "Started ibuprofen"
    assert ongoing.is_ongoing is True
    assert ongoing.tags == ["health", "meds"]
    assert ongoing.data_points == [("dose", "400mg")]

    tag_only = parse_quick_input("#dog #puke")
    assert tag_only.title == "#dog #puke"
    assert tag_only.tags == ["dog", "puke"]


@pytest.mark.django_db
def test_event_lifecycle_and_field_recall(user):
    now = timezone.now()
    e1 = create_event(
        user,
        "Charged watch",
        started_at=now - timedelta(days=6),
        tag_names=["smartwatch", "charge"],
        data_points=[("battery", "18%"), ("charger", "desk")],
    )
    e2 = create_event(
        user,
        "Charged watch again",
        started_at=now - timedelta(days=3),
        tag_names=["smartwatch", "charge"],
        data_points=[("battery", "12%")],
    )
    assert e1.shape == "point"
    assert e2.data_points.get(key="battery").value_num == 12.0
    assert e2.data_points.get(key="battery").unit == "%"

    suggested = get_suggested_fields(user, ["smartwatch"])
    keys = [s["key"] for s in suggested]
    assert keys[0] == "battery"
    assert "charger" in keys
    assert suggested[0]["unit"] == "%"
    assert suggested[0]["count"] == 2

    # Ongoing span -> stop -> append note
    meds = create_event(
        user,
        "Started Ibuprofen",
        started_at=now - timedelta(days=2),
        is_ongoing=True,
        tag_names=["health", "ibuprofen"],
        data_points=[("dose", "400mg")],
    )
    assert meds.shape == "ongoing"
    update_event(meds, append_note="Mild headache in afternoon")
    assert "Mild headache in afternoon" in meds.notes
    meds.stop(at=now)
    assert meds.shape == "span"
    assert meds.duration == timedelta(days=2)


@pytest.mark.django_db
def test_structured_search_and_owner_isolation(user, other_user):
    now = timezone.now()
    create_event(
        user,
        "Dog puked on rug",
        notes="Looked yellow",
        started_at=now - timedelta(days=1),
        tag_names=["dog", "puke"],
        data_points=[("ate", "chicken")],
    )
    create_event(
        user,
        "Dog walk in park",
        started_at=now - timedelta(days=1),
        tag_names=["dog", "walk"],
    )
    create_event(
        user,
        "Charged smartwatch",
        started_at=now - timedelta(days=10),
        tag_names=["smartwatch", "charge"],
        data_points=[("battery", "15%")],
    )
    create_event(
        user,
        "Charged smartwatch high",
        started_at=now - timedelta(days=2),
        tag_names=["smartwatch", "charge"],
        data_points=[("battery", "45%")],
    )
    create_event(
        user,
        "Taking antibiotics",
        started_at=now - timedelta(days=3),
        is_ongoing=True,
        tag_names=["health", "meds"],
    )
    create_event(
        other_user,
        "Bob's dog puked",
        tag_names=["dog", "puke"],
    )

    qs = Event._base_manager.filter(owner=user)

    assert search_events(qs, "#dog #puke").count() == 1
    assert search_events(qs, "#dog -#walk").count() == 1
    assert search_events(qs, "ate:chicken").count() == 1
    assert search_events(qs, "battery:<20").count() == 1
    assert search_events(qs, "battery:>=20").count() == 1
    assert search_events(qs, "has:battery").count() == 2
    assert search_events(qs, "is:ongoing").count() == 1
    assert search_events(qs, "last:5d #smartwatch").count() == 1
    assert search_events(qs, "yellow").count() == 1


@pytest.mark.django_db
def test_tag_stats_and_timeline_overlay(user):
    now = timezone.now()
    for days_ago, pct in [(10, "20%"), (6, "15%"), (2, "10%")]:
        create_event(
            user,
            f"Charge at {pct}",
            started_at=now - timedelta(days=days_ago),
            tag_names=["smartwatch"],
            data_points=[("battery", pct)],
        )
    create_event(
        user,
        "Changed water filter",
        started_at=now - timedelta(days=5),
        tag_names=["water-filter"],
    )

    stats = get_tag_stats(user, "smartwatch")
    assert stats is not None
    assert stats["count"] == 3
    assert stats["avg_interval_days"] == 4.0
    assert len(stats["numeric_series"]["battery"]) == 3

    overlay = get_tag_combo_lanes(user)
    assert overlay["total_events"] == 4
    assert [lane["key"] for lane in overlay["lanes"]] == ["smartwatch", "water-filter"]
    assert len(overlay["lanes"][0]["events"]) == 3
    assert len(overlay["lanes"][1]["events"]) == 1
    assert len(overlay["lanes"][0]["numeric_series"]["battery"]) == 3

    # tags= keeps events that have all of them, like #tag in a query
    only = get_tag_combo_lanes(user, tags=["smartwatch"])
    assert only["total_events"] == 3
    assert Tag._base_manager.filter(owner=user).count() == 2


def test_combo_lanes_keep_future_ongoing_span_in_range(user):
    now = timezone.now()
    create_event(
        user, "Earlier", started_at=now - timedelta(days=10), tag_names=["meds"]
    )
    create_event(
        user,
        "Starts later",
        started_at=now + timedelta(days=5),
        is_ongoing=True,
        tag_names=["meds"],
    )

    lanes = get_tag_combo_lanes(user, tags=["meds"])

    assert lanes["range_end"] >= (now + timedelta(days=5)).isoformat()
    later = next(e for e in lanes["lanes"][0]["events"] if e["title"] == "Starts later")
    assert (
        later["end"] >= later["start"]
    )  # running from the future: never a negative bar


def test_combo_lanes_keep_tag_combinations_apart(user):
    now = timezone.now()
    create_event(user, "Walk", started_at=now - timedelta(days=3), tag_names=["dog"])
    create_event(
        user, "Sick", started_at=now - timedelta(days=2), tag_names=["dog", "puke"]
    )
    create_event(
        user,
        "Sick again",
        started_at=now - timedelta(days=1),
        tag_names=["puke", "dog"],
    )
    create_event(user, "Untagged", started_at=now - timedelta(days=1))

    def keys(q=""):
        return [lane["key"] for lane in get_tag_combo_lanes(user, q=q)["lanes"]]

    assert keys() == ["dog", "dog puke", ""]
    assert keys("#dog") == ["dog", "dog puke"]
    assert keys("#puke") == ["dog puke"]

    combo = get_tag_combo_lanes(user, q="#puke")["lanes"][0]
    assert combo["count"] == 2
    assert combo["avg_interval_days"] == 1.0


def test_accented_tags_and_fields(user):
    parsed = parse_quick_input("Consulta #saúde #pós-operatório pressão:12")
    assert parsed.title == "Consulta"
    assert parsed.tags == ["saúde", "pós-operatório"]
    assert parsed.data_points == [("pressão", "12")]

    create_event(user, parsed.title, tag_names=parsed.tags, data_points=parsed.data_points)
    tag = Tag.objects.get(owner=user, name="saúde")
    assert tag.slug == "saude"
    for q in ("#saúde", "#saude", "pressão:12"):
        assert [e.title for e in search_events(Event.objects.filter(owner=user), q)] == ["Consulta"]
