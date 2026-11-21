from datetime import timedelta

import pytest
from apps.events.services import create_event, get_tag_combo_lanes
from apps.users.models import User
from django.urls import reverse
from django.utils import timezone


@pytest.fixture
def user(db):
    return User.objects.create_user(email="lanes@example.com", password="pw123456")


def keys(user, **kw):
    return [lane["key"] for lane in get_tag_combo_lanes(user, **kw)["lanes"]]


def test_archived_lane_hides_until_logged_to_again(client, user):
    now = timezone.now()
    for d in (9, 6, 3):
        create_event(user, "Puke", started_at=now - timedelta(days=d), tag_names=["dog", "puke"])
    create_event(user, "Walk", tag_names=["dog"])
    client.force_login(user)

    client.post(reverse("lane_archive", kwargs={"key": "dog+puke"}), {"archived": "1"})
    assert keys(user) == ["dog"]
    shown = get_tag_combo_lanes(user, archived=True)
    assert shown["archived_count"] == 1
    assert [x["archived"] for x in shown["lanes"]] == [False, True]

    # logging to it (even backdated) brings it back
    create_event(user, "Again", started_at=now - timedelta(days=30), tag_names=["puke", "dog"])
    assert keys(user) == ["dog", "dog puke"]

    client.post(reverse("lane_archive", kwargs={"key": "dog"}), {"archived": "1"})
    client.post(reverse("lane_archive", kwargs={"key": "dog"}), {"archived": "0"})
    assert "dog" in keys(user)


def test_lane_page(client, user):
    now = timezone.now()
    for d in (12, 8, 4):
        create_event(user, "Puke", started_at=now - timedelta(days=d), tag_names=["dog", "puke"])
    create_event(user, "Untagged thing")
    client.force_login(user)

    page = client.get(reverse("lane_detail", kwargs={"key": "dog+puke"}))
    assert page.status_code == 200
    lane = page.context["lane"]
    assert lane["count"] == 3
    assert lane["avg_interval_days"] == 4
    assert lane["due"] == {"state": "now", "days": 0}
    assert client.get(reverse("lane_detail", kwargs={"key": "~"})).status_code == 200
    # #dog alone is not a lane here
    assert client.get(reverse("lane_detail", kwargs={"key": "dog"})).status_code == 302

    lanes_page = client.get(reverse("lanes"))
    assert reverse("lane_detail", kwargs={"key": "dog+puke"}) in lanes_page.content.decode()
