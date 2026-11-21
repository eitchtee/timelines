from apps.api.serializers.events import EventSerializer, TagSerializer
from apps.events.models import Event, Tag
from apps.events.search import search_events
from apps.events.services import (
    get_suggested_fields,
    get_tag_stats,
    get_tag_combo_lanes,
    update_event,
)
from django.db.models import Count
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response


class EventViewSet(viewsets.ModelViewSet):
    serializer_class = EventSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = (
            Event._base_manager.filter(owner=self.request.user)
            .prefetch_related("tags", "data_points")
            .select_related("parent")
        )
        q = (self.request.query_params.get("q") or "").strip()
        tags = [
            t.strip() for t in self.request.query_params.getlist("tag") if t.strip()
        ]
        tag_mode = self.request.query_params.get("tag_mode", "and")
        if q or tags:
            qs = search_events(qs, q=q, extra_tags=tags, tag_mode=tag_mode)
        return qs

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        event = self.get_object()
        at_raw = request.data.get("ended_at")
        at_dt = parse_datetime(at_raw) if at_raw else None
        event.stop(at=at_dt)
        return Response(self.get_serializer(event).data)

    @action(detail=True, methods=["post"])
    def append_note(self, request, pk=None):
        event = self.get_object()
        note = (request.data.get("note") or "").strip()
        if not note:
            return Response(
                {"detail": "Field 'note' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        update_event(event, append_note=note)
        return Response(self.get_serializer(event).data)

    @action(detail=False, methods=["get"])
    def overlay(self, request):
        tags = [t.strip() for t in request.query_params.getlist("tag") if t.strip()]
        if not tags and request.query_params.get("tags"):
            tags = [
                t.strip() for t in request.query_params["tags"].split(",") if t.strip()
            ]
        q = (request.query_params.get("q") or "").strip()
        # lanes per exact tag combination; tags filter to events having all of them
        data = get_tag_combo_lanes(request.user, q=q, tags=tags, archived=True)
        return Response(data)


class TagViewSet(viewsets.ModelViewSet):
    serializer_class = TagSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "slug"

    def get_queryset(self):
        return (
            Tag._base_manager.filter(owner=self.request.user)
            .annotate(event_count=Count("events"))
            .order_by("-event_count", "name")
        )

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=["get"])
    def stats(self, request, slug=None):
        data = get_tag_stats(request.user, slug)
        if data is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(data)

    @action(detail=False, methods=["get"])
    def suggested_fields(self, request):
        raw = request.query_params.get("tags", "")
        tag_list = [t.strip() for t in raw.split(",") if t.strip()]
        return Response({"fields": get_suggested_fields(request.user, tag_list)})
