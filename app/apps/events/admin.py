from django.contrib import admin

from .models import DataPoint, Event, Tag


class DataPointInline(admin.TabularInline):
    model = DataPoint
    extra = 0
    fields = ("key", "value_text", "value_num", "unit", "order")


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "color", "owner", "created_at")
    search_fields = ("name", "slug")
    list_filter = ("owner",)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "shape", "started_at", "ended_at", "is_ongoing", "owner")
    list_filter = ("is_ongoing", "tags", "owner")
    search_fields = ("title", "notes", "search_document")
    filter_horizontal = ("tags",)
    inlines = [DataPointInline]
