import json
import secrets

import pytest
from apps.events.models import Event
from apps.users.models import APIToken, User
from django.urls import reverse


@pytest.fixture
def user(db):
    return User.objects.create_user(email="alice@example.com", password="password123")


@pytest.fixture
def api_token(user):
    secret = secrets.token_urlsafe(32)
    token = APIToken.objects.create(
        user=user,
        name="test-agent",
        token_key=APIToken.generate_token_key(),
        token_hash=APIToken.hash_secret(secret),
    )
    return token.build_raw_token(secret)


@pytest.mark.django_db
def test_web_views_quick_capture_and_overlay(client, user):
    client.force_login(user)

    # Dashboard renders cleanly
    resp = client.get(reverse("index"))
    assert resp.status_code == 200

    # Quick-create with inline #tags, key:value, and !ongoing
    resp = client.post(
        reverse("event_quick_create"),
        {"quick_input": "Started ibuprofen #health #meds dose:400mg !ongoing"},
    )
    assert resp.status_code == 204
    ev = Event._base_manager.get(owner=user)
    assert ev.title == "Started ibuprofen"
    assert ev.is_ongoing is True
    assert set(ev.tags.values_list("slug", flat=True)) == {"health", "meds"}
    assert ev.data_points.get(key="dose").value_num == 400.0
    assert ev.data_points.get(key="dose").unit == "mg"

    # Suggested fields recall 'dose' when typing #meds
    resp = client.get(reverse("events_suggested_fields"), {"tags": "meds"})
    assert resp.status_code == 200
    assert b"dose" in resp.content

    # Feed & Timeline overlay HTMX fragments render cleanly
    resp_feed = client.get(reverse("events_results"), {"q": "#meds", "view": "feed"})
    assert resp_feed.status_code == 200
    assert b"Started ibuprofen" in resp_feed.content

    resp_tl = client.get(reverse("events_results"), {"q": "#meds", "view": "timeline"})
    assert resp_tl.status_code == 200
    assert b"Started ibuprofen" in resp_tl.content

    # Detail drawer, append note, stop span, delete
    assert client.get(reverse("event_detail", args=[ev.id])).status_code == 200
    assert (
        client.post(
            reverse("event_append_note", args=[ev.id]),
            {"note": "Mild headache"},
        ).status_code
        == 200
    )
    ev.refresh_from_db()
    assert "Mild headache" in ev.notes

    assert client.post(reverse("event_stop", args=[ev.id])).status_code == 204
    ev.refresh_from_db()
    assert ev.is_ongoing is False
    assert ev.ended_at is not None

    assert client.post(reverse("event_delete", args=[ev.id])).status_code == 204
    assert Event._base_manager.filter(owner=user).count() == 0


@pytest.mark.django_db
def test_rest_api_crud_search_and_stats(client, api_token):
    headers = {"HTTP_AUTHORIZATION": f"Token {api_token}"}

    # Create event with tags and data points
    resp = client.post(
        "/api/events/",
        data=json.dumps(
            {
                "title": "Charged smartwatch",
                "tag_names": ["smartwatch", "charge"],
                "data_points": [{"key": "battery", "value": "14%"}],
            }
        ),
        content_type="application/json",
        **headers,
    )
    assert resp.status_code == 201
    created = resp.json()
    assert created["title"] == "Charged smartwatch"
    assert created["data_points"][0]["value_num"] == 14.0
    assert created["data_points"][0]["unit"] == "%"

    # Search via ?q=
    resp = client.get("/api/events/?q=%23smartwatch+battery:<20", **headers)
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 1

    # Tag stats & suggested fields
    resp = client.get("/api/tags/smartwatch/stats/", **headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 1

    resp = client.get("/api/tags/suggested_fields/?tags=smartwatch", **headers)
    assert resp.status_code == 200
    assert resp.json()["fields"][0]["key"] == "battery"

    # Overlay endpoint
    resp = client.get("/api/events/overlay/?tags=smartwatch", **headers)
    assert resp.status_code == 200
    assert resp.json()["total_events"] == 1


@pytest.mark.django_db
def test_mcp_server_end_to_end(client, api_token):
    # Unauthenticated fails with 401
    resp = client.post(
        "/mcp/",
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
        content_type="application/json",
    )
    assert resp.status_code == 401

    headers = {"HTTP_AUTHORIZATION": f"Bearer {api_token}"}

    def rpc(method, params=None, req_id=1):
        return client.post(
            "/mcp/",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "method": method,
                    "params": params or {},
                }
            ),
            content_type="application/json",
            **headers,
        )

    # initialize + tools/list
    init_resp = rpc("initialize")
    assert init_resp.status_code == 200
    assert init_resp.json()["result"]["serverInfo"]["name"] == "timelines"

    tools_resp = rpc("tools/list", req_id=2)
    tool_names = {t["name"] for t in tools_resp.json()["result"]["tools"]}
    assert {
        "log_event",
        "stop_event",
        "update_event",
        "search_events",
        "list_tags",
        "get_tag_stats",
        "get_timeline_overlay",
    }.issubset(tool_names)

    # log_event -> search_events -> stop_event -> get_tag_stats -> get_timeline_overlay
    log_resp = rpc(
        "tools/call",
        {
            "name": "log_event",
            "arguments": {
                "title": "Dog puked",
                "tags": ["dog", "puke"],
                "data_points": [{"key": "ate", "value": "chicken"}],
            },
        },
        req_id=3,
    )
    logged = json.loads(log_resp.json()["result"]["content"][0]["text"])
    assert logged["title"] == "Dog puked"
    assert logged["tags"] == ["dog", "puke"]

    search_resp = rpc(
        "tools/call",
        {"name": "search_events", "arguments": {"q": "#dog ate:chicken"}},
        req_id=4,
    )
    searched = json.loads(search_resp.json()["result"]["content"][0]["text"])
    assert searched["count"] == 1

    overlay_resp = rpc(
        "tools/call",
        {"name": "get_timeline_overlay", "arguments": {"tags": ["dog", "puke"]}},
        req_id=5,
    )
    overlay = json.loads(overlay_resp.json()["result"]["content"][0]["text"])
    # one event tagged dog+puke: a single combination lane
    assert [lane["key"] for lane in overlay["lanes"]] == ["dog puke"]
    assert overlay["lanes"][0]["count"] == 1
