import hashlib
import re
from datetime import timedelta

from apps.common.models import OwnedObject, OwnedObjectManager
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

TAG_PALETTE = [
    "#3b82f6",  # blue
    "#10b981",  # emerald
    "#f59e0b",  # amber
    "#ef4444",  # red
    "#8b5cf6",  # violet
    "#ec4899",  # pink
    "#06b6d4",  # cyan
    "#84cc16",  # lime
    "#f97316",  # orange
    "#14b8a6",  # teal
    "#6366f1",  # indigo
    "#eab308",  # yellow
]

_NUM_UNIT_RE = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*([a-zA-Z%°µ/][a-zA-Z0-9%°µ/_.-]{0,31})?\s*$"
)


def default_tag_color(slug: str) -> str:
    digest = hashlib.md5(slug.encode("utf-8"), usedforsecurity=False).digest()
    return TAG_PALETTE[digest[0] % len(TAG_PALETTE)]


def parse_value_and_unit(
    raw_value: str, explicit_unit: str = ""
) -> tuple[str, float | None, str]:
    """Parse a raw data point string into (display_text, numeric_value, unit).

    Examples:
        "14%" -> ("14", 14.0, "%")
        "400mg" -> ("400", 400.0, "mg")
        "38.5 C" -> ("38.5", 38.5, "C")
        "chicken" -> ("chicken", None, "")
    """
    cleaned = str(raw_value).strip()
    unit = explicit_unit.strip()
    match = _NUM_UNIT_RE.match(cleaned)
    if match:
        num_str, parsed_unit = match.groups()
        try:
            num_val = float(num_str)
        except ValueError:
            return cleaned, None, unit
        return num_str, num_val, unit or (parsed_unit or "")
    return cleaned, None, unit


class Tag(OwnedObject):
    name = models.CharField(max_length=64, verbose_name=_("Name"))
    slug = models.SlugField(max_length=80, verbose_name=_("Slug"))
    color = models.CharField(
        max_length=20, blank=True, default="", verbose_name=_("Color")
    )
    icon = models.CharField(
        max_length=64, blank=True, default="", verbose_name=_("Icon")
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = OwnedObjectManager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "slug"],
                name="unique_tag_slug_per_owner",
            )
        ]
        indexes = [
            models.Index(fields=["owner", "slug"]),
        ]

    def __str__(self) -> str:
        return f"#{self.name}"

    def save(self, *args, **kwargs):
        self.name = self.name.strip().lstrip("#")
        if not self.slug:
            self.slug = slugify(self.name) or self.name.lower()
        if not self.color:
            self.color = default_tag_color(self.slug)
        super().save(*args, **kwargs)

    @classmethod
    def get_or_create_for_user(cls, raw_name: str, user) -> "Tag | None":
        clean_name = raw_name.strip().lstrip("#")
        if not clean_name:
            return None
        slug = slugify(clean_name) or clean_name.lower()
        tag, _ = cls._base_manager.get_or_create(
            owner=user,
            slug=slug,
            defaults={"name": clean_name, "color": default_tag_color(slug)},
        )
        return tag


class Event(OwnedObject):
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
        verbose_name=_("Parent event"),
    )
    title = models.CharField(max_length=255, verbose_name=_("Title"))
    notes = models.TextField(blank=True, default="", verbose_name=_("Notes"))
    started_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        verbose_name=_("Started at"),
    )
    ended_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("Ended at"),
    )
    is_ongoing = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_("Ongoing"),
    )
    # the day matters, the time doesn't: started_at/ended_at sit at local midnight and
    # ended_at's day counts in full
    all_day = models.BooleanField(default=False, verbose_name=_("All day"))
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name="events",
        verbose_name=_("Tags"),
    )
    search_document = models.TextField(blank=True, default="", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OwnedObjectManager()

    class Meta:
        ordering = ["-started_at", "-created_at"]
        indexes = [
            models.Index(fields=["owner", "-started_at"]),
            models.Index(fields=["owner", "is_ongoing"]),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def shape(self) -> str:
        if self.is_ongoing and self.ended_at is None:
            return "ongoing"
        if self.ended_at is not None:
            return "span"
        return "point"

    @property
    def end_bound(self):
        """Where the event really stops: an all-day end covers its whole last day."""
        if self.ended_at is None:
            return None
        return self.ended_at + timedelta(days=1) if self.all_day else self.ended_at

    @property
    def duration(self) -> timedelta | None:
        if self.ended_at is not None:
            return max(self.end_bound - self.started_at, timedelta(0))
        if self.is_ongoing:
            return max(timezone.now() - self.started_at, timedelta(0))
        return None

    def stop(self, at=None, save: bool = True) -> "Event":
        self.ended_at = at or timezone.now()
        self.is_ongoing = False
        if save:
            self.save(update_fields=["ended_at", "is_ongoing", "updated_at"])
        return self

    def build_search_document(self) -> str:
        parts = [self.title or "", self.notes or ""]
        if self.pk:
            tag_names = list(self.tags.values_list("name", flat=True))
            parts.extend(tag_names)
            dp_parts = [
                f"{dp.key} {dp.value_text} {dp.unit}".strip()
                for dp in self.data_points.all()
            ]
            parts.extend(dp_parts)
        return " ".join(p for p in parts if p).strip()

    def rebuild_search_document(self, save: bool = True) -> str:
        self.search_document = self.build_search_document()
        if save and self.pk:
            Event._base_manager.filter(pk=self.pk).update(
                search_document=self.search_document
            )
        return self.search_document


class DataPoint(OwnedObject):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="data_points",
        verbose_name=_("Event"),
    )
    key = models.CharField(max_length=64, db_index=True, verbose_name=_("Key"))
    value_text = models.CharField(max_length=255, verbose_name=_("Value"))
    value_num = models.FloatField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("Numeric value"),
    )
    unit = models.CharField(
        max_length=32, blank=True, default="", verbose_name=_("Unit")
    )
    order = models.PositiveIntegerField(default=0)

    objects = OwnedObjectManager()

    class Meta:
        ordering = ["order", "id"]
        indexes = [
            models.Index(fields=["owner", "key"]),
            models.Index(fields=["event", "key"]),
        ]

    def __str__(self) -> str:
        suffix = f" {self.unit}" if self.unit else ""
        return f"{self.key}: {self.value_text}{suffix}"

    def save(self, *args, **kwargs):
        self.key = self.key.strip().lower().replace(" ", "_")
        parsed_text, parsed_num, parsed_unit = parse_value_and_unit(
            self.value_text, self.unit
        )
        self.value_text = parsed_text
        if self.value_num is None:
            self.value_num = parsed_num
        if not self.unit:
            self.unit = parsed_unit
        if not self.owner_id and self.event_id:
            self.owner_id = self.event.owner_id
        super().save(*args, **kwargs)


class ArchivedLane(OwnedObject):
    """A lane (exact tag combination) the user put away.

    It stays hidden from the Lanes page until an event with that exact combination
    is logged after ``archived_at``; then it shows up again on its own.
    """

    key = models.CharField(max_length=512, blank=True, verbose_name=_("Lane"))
    archived_at = models.DateTimeField(default=timezone.now)

    objects = OwnedObjectManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "key"], name="unique_archived_lane_per_owner"
            )
        ]

    def __str__(self) -> str:
        return self.key or "(untagged)"
