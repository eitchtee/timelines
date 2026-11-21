from apps.events.models import DataPoint, Event, Tag
from apps.events.services import create_event, update_event
from rest_framework import serializers


class TagSerializer(serializers.ModelSerializer):
    event_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Tag
        fields = ("id", "name", "slug", "color", "icon", "event_count", "created_at")
        read_only_fields = ("id", "slug", "created_at")


class DataPointSerializer(serializers.ModelSerializer):
    value = serializers.CharField(source="value_text")

    class Meta:
        model = DataPoint
        fields = ("id", "key", "value", "value_num", "unit", "order")
        read_only_fields = ("id", "value_num")


class EventSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True, read_only=True)
    tag_names = serializers.ListField(
        child=serializers.CharField(max_length=64),
        write_only=True,
        required=False,
    )
    data_points = DataPointSerializer(many=True, required=False)
    shape = serializers.CharField(read_only=True)

    class Meta:
        model = Event
        fields = (
            "id",
            "parent",
            "title",
            "notes",
            "started_at",
            "ended_at",
            "is_ongoing",
            "all_day",
            "shape",
            "tags",
            "tag_names",
            "data_points",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "shape", "created_at", "updated_at")

    def create(self, validated_data):
        tag_names = validated_data.pop("tag_names", [])
        raw_dps = validated_data.pop("data_points", [])
        dp_items = [(dp["key"], dp["value_text"], dp.get("unit", "")) for dp in raw_dps]
        user = self.context["request"].user
        return create_event(
            user,
            title=validated_data["title"],
            notes=validated_data.get("notes", ""),
            started_at=validated_data.get("started_at"),
            ended_at=validated_data.get("ended_at"),
            is_ongoing=validated_data.get("is_ongoing", False),
            all_day=validated_data.get("all_day", False),
            tag_names=tag_names,
            data_points=dp_items,
            parent=validated_data.get("parent"),
        )

    def update(self, instance, validated_data):
        tag_names = validated_data.pop("tag_names", None)
        raw_dps = validated_data.pop("data_points", None)
        dp_items = (
            [(dp["key"], dp["value_text"], dp.get("unit", "")) for dp in raw_dps]
            if raw_dps is not None
            else None
        )
        return update_event(
            instance,
            title=validated_data.get("title"),
            notes=validated_data.get("notes"),
            started_at=validated_data.get("started_at"),
            ended_at=validated_data.get("ended_at", ...),
            is_ongoing=validated_data.get("is_ongoing"),
            all_day=validated_data.get("all_day"),
            tag_names=tag_names,
            data_points=dp_items,
            parent=validated_data.get("parent", ...),
        )
