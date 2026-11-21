from datetime import datetime

import pytest
from apps.events.models import Event
from apps.events.services import update_event
from apps.events.templatetags.event_notes import note_entries
from apps.users.models import User
from django.urls import reverse
from django.utils import timezone


@pytest.fixture
def logged_in(client, db):
    user = User.objects.create_user(email="dana@example.com", password="pw123456")
    client.force_login(user)
    client.post(reverse("event_quick_create"), {"quick_input": "Weigh #dog weight:4kg"})
    return client, Event._base_manager.get(owner=user, title="Weigh")


def _fields(event):
    return {f.key: (f.value_text, f.value_num, f.unit) for f in event.data_points.all()}


def test_field_add_creates_and_replaces(logged_in):
    client, event = logged_in
    url = reverse("event_field_add", kwargs={"pk": event.pk})

    client.post(url, {"fields": "ate:chicken"})
    assert _fields(event) == {"weight": ("4", 4.0, "kg"), "ate": ("chicken", None, "")}

    client.post(url, {"fields": "weight:4.5kg"})  # same name: replaced, number re-read
    assert _fields(event)["weight"] == ("4.5", 4.5, "kg")
    assert event.data_points.count() == 2


def test_field_delete(logged_in):
    client, event = logged_in
    field = event.data_points.get(key="weight")
    client.post(
        reverse("event_field_delete", kwargs={"pk": event.pk, "field_pk": field.pk})
    )
    assert not event.data_points.exists()


def test_edit_form_without_fields_keeps_them(logged_in):
    client, event = logged_in
    client.post(
        reverse("event_edit", kwargs={"pk": event.pk}),
        {"title": "Weighed", "tags": ["dog"]},
    )
    event.refresh_from_db()
    assert event.title == "Weighed"
    assert _fields(event) == {"weight": ("4", 4.0, "kg")}


def test_note_entries_split_body_and_stamps(logged_in):
    _, event = logged_in
    update_event(event, notes="Usual vet")
    update_event(event, append_note="mild headache")
    update_event(event, append_note="**better** now")

    parsed = note_entries(event.notes)
    assert parsed["body"] == "Usual vet"
    assert [e["text"] for e in parsed["entries"]] == ["mild headache", "**better** now"]
    now = timezone.localtime()
    assert abs(parsed["entries"][0]["at"] - now).total_seconds() < 120

    only = note_entries("**[2026-11-21 01:41]** stamped note")
    assert only["body"] == ""
    assert timezone.localtime(only["entries"][0]["at"]).replace(
        tzinfo=None
    ) == datetime(2026, 11, 21, 1, 41)


def test_lanes_is_its_own_page_and_old_links_redirect(logged_in):
    client, _ = logged_in
    page = client.get(reverse("lanes"), {"q": "#dog", "range": "30d"})
    assert page.status_code == 200
    assert page.context["view_mode"] == "timeline"
    assert page.context["lanes"]["total_events"] == 1

    old = client.get(reverse("index"), {"view": "timeline", "q": "#dog"})
    assert old.status_code == 302
    assert old["Location"] == f"{reverse('lanes')}?q=%23dog"

    assert client.get(reverse("index")).context["view_mode"] == "feed"
