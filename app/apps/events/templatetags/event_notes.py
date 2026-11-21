"""Split an event's notes into the free-text part and its time-stamped entries."""

import re
from datetime import datetime

from django import template
from django.utils import timezone

register = template.Library()

# written by update_event(append_note=...): "**[2026-11-21 01:41]** text"
_STAMP_RE = re.compile(r"\*\*\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]\*\*[ \t]*")


@register.filter
def note_entries(notes: str) -> dict:
    """{"body": text before the first stamp, "entries": [{"at": datetime, "text": str}]}.

    Stamps were written in the user's local time without an offset, so they are
    read back in the active timezone.
    """
    parts = _STAMP_RE.split(notes or "")
    entries = []
    for stamp, text in zip(parts[1::2], parts[2::2], strict=True):
        at = timezone.make_aware(datetime.strptime(stamp, "%Y-%m-%d %H:%M"))
        entries.append({"at": at, "text": text.strip()})
    return {"body": parts[0].strip(), "entries": entries}
