from django.db import migrations

# FTS5 index over events_event.search_document, kept in sync by triggers.
# "porter" stems words (puke/puked/puking match each other); the index only
# stores tokens and reads the text from events_event (external content).
CREATE = [
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS events_event_fts USING fts5(
        search_document,
        content='events_event',
        content_rowid='id',
        tokenize='porter unicode61 remove_diacritics 2'
    );
    """,
    """
    CREATE TRIGGER IF NOT EXISTS events_event_fts_ai AFTER INSERT ON events_event BEGIN
        INSERT INTO events_event_fts(rowid, search_document)
        VALUES (new.id, new.search_document);
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS events_event_fts_ad AFTER DELETE ON events_event BEGIN
        INSERT INTO events_event_fts(events_event_fts, rowid, search_document)
        VALUES ('delete', old.id, old.search_document);
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS events_event_fts_au
    AFTER UPDATE OF search_document ON events_event BEGIN
        INSERT INTO events_event_fts(events_event_fts, rowid, search_document)
        VALUES ('delete', old.id, old.search_document);
        INSERT INTO events_event_fts(rowid, search_document)
        VALUES (new.id, new.search_document);
    END;
    """,
    "INSERT INTO events_event_fts(events_event_fts) VALUES ('rebuild');",
]

DROP = [
    "DROP TRIGGER IF EXISTS events_event_fts_ai;",
    "DROP TRIGGER IF EXISTS events_event_fts_ad;",
    "DROP TRIGGER IF EXISTS events_event_fts_au;",
    "DROP TABLE IF EXISTS events_event_fts;",
]


def _run(statements):
    def apply(apps, schema_editor):
        if schema_editor.connection.vendor != "sqlite":
            return
        with schema_editor.connection.cursor() as cursor:
            for sql in statements:
                cursor.execute(sql)

    return apply


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0004_event_all_day"),
    ]

    operations = [
        migrations.RunPython(_run(CREATE), _run(DROP)),
    ]
