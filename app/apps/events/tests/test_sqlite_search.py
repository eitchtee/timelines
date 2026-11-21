from datetime import timedelta

import pytest
from apps.events.models import Event
from apps.events.search import search_events
from apps.events.services import create_event, update_event
from apps.users.models import User
from django.db import connection
from django.utils import timezone

pytestmark = pytest.mark.skipif(
    connection.vendor != "sqlite", reason="FTS5 search is the SQLite path"
)


@pytest.fixture
def user(db):
    return User.objects.create_user(email="fts@example.com", password="pw123456")


def titles(user, q):
    return [e.title for e in search_events(Event.objects.filter(owner=user), q)]


def test_fts_matches_word_forms_and_prefixes(user):
    now = timezone.now()
    create_event(user, "Dog puked on the rug", started_at=now - timedelta(days=3))
    create_event(user, "Rug cleaned", started_at=now - timedelta(days=1))
    create_event(user, "Ate chicken and rice", started_at=now - timedelta(days=2))

    assert titles(user, "puking") == ["Dog puked on the rug"]  # stemmed
    assert titles(user, "chick") == ["Ate chicken and rice"]  # prefix
    assert titles(user, "icken") == ["Ate chicken and rice"]  # substring fallback
    # every word is required
    assert titles(user, "dog rug") == ["Dog puked on the rug"]
    assert set(titles(user, "rug")) == {"Dog puked on the rug", "Rug cleaned"}
    # FTS5 syntax in the query is treated as text, not an error
    assert titles(user, 'rug AND "NEAR( -^*') == []
    assert titles(user, "???") == []


def test_fts_index_follows_edits_and_deletes(user):
    ev = create_event(user, "Headache")
    assert titles(user, "headache") == ["Headache"]

    update_event(ev, title="Migraine")
    assert titles(user, "headache") == []
    assert titles(user, "migraine") == ["Migraine"]

    ev.delete()
    assert titles(user, "migraine") == []
