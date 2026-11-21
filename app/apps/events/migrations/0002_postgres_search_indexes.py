from django.db import migrations


def create_postgres_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS events_event_search_fts_gin
            ON events_event
            USING GIN (to_tsvector('english', search_document));
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS events_event_search_trgm_gin
            ON events_event
            USING GIN (search_document gin_trgm_ops);
            """
        )


def drop_postgres_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP INDEX IF EXISTS events_event_search_fts_gin;")
        cursor.execute("DROP INDEX IF EXISTS events_event_search_trgm_gin;")


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_postgres_indexes, drop_postgres_indexes),
    ]
