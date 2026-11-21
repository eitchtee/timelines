from datetime import date, time, timedelta

import pytest
from apps.events.models import Event
from apps.events.services import create_event, get_lane_detail
from apps.users.models import User
from django.urls import reverse
from django.utils import timezone


@pytest.fixture
def client_user(client, db):
    user = User.objects.create_user(email="allday@example.com", password="pw123456")
    client.force_login(user)
    return client, user


def local(dt):
    return timezone.localtime(dt)


def test_quick_log_date_without_time_is_all_day(client_user):
    client, user = client_user
    client.post(reverse("event_quick_create"), {"quick_input": "Vet #dog @20-10-2026"})
    client.post(reverse("event_quick_create"), {"quick_input": "Walk #dog @20-10-2026,9:15"})
    client.post(reverse("event_quick_create"), {"quick_input": "Trip @20-10-2026~22-10-2026"})

    vet = Event._base_manager.get(owner=user, title="Vet")
    assert vet.all_day and local(vet.started_at).time() == time.min
    assert local(vet.started_at).date() == date(2026, 10, 20)
    walk = Event._base_manager.get(owner=user, title="Walk")
    assert not walk.all_day and local(walk.started_at).time() == time(9, 15)
    trip = Event._base_manager.get(owner=user, title="Trip")
    # 20th through the 22nd, inclusive
    assert trip.all_day and trip.duration == timedelta(days=3)


def test_edit_form_blank_time_means_all_day(client_user):
    client, user = client_user
    ev = create_event(user, "Thing")
    url = reverse("event_edit", kwargs={"pk": ev.pk})

    client.post(url, {"title": "Thing", "start_date": "2026-11-02", "start_time": ""})
    ev.refresh_from_db()
    assert ev.all_day and local(ev.started_at).date() == date(2026, 11, 2)

    client.post(url, {
        "title": "Thing", "start_date": "2026-11-02", "start_time": "08:30",
        "end_date": "2026-11-02", "end_time": "",
    })
    ev.refresh_from_db()
    # an end without a time takes the start's
    assert not ev.all_day and local(ev.ended_at).time() == time(8, 30)


def test_all_day_events_stay_out_of_time_of_day(client_user):
    _, user = client_user
    create_event(user, "A", tag_names=["x"], all_day=True)
    create_event(user, "B", tag_names=["x"], all_day=True)
    lane = get_lane_detail(user, ["x"])
    assert not lane["has_times"]
