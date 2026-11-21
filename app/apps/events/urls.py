from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="index"),
    path("lanes/", views.lanes, name="lanes"),
    path("lanes/<str:key>/", views.lane_detail, name="lane_detail"),
    path("lanes/<str:key>/archive/", views.lane_archive, name="lane_archive"),
    path("calendar/", views.calendar, name="calendar"),
    path("events/results/", views.workspace_results, name="events_results"),
    path("events/quick-create/", views.quick_create, name="event_quick_create"),
    path(
        "events/suggested-fields/",
        views.suggested_fields,
        name="events_suggested_fields",
    ),
    path("events/tags/autocomplete/", views.tag_autocomplete, name="tag_autocomplete"),
    path("events/fields/", views.field_keys, name="field_keys"),
    path("events/ongoing/", views.ongoing_autocomplete, name="ongoing_autocomplete"),
    path("events/dates/interpret/", views.date_interpret, name="date_interpret"),
    path("events/<int:pk>/", views.event_detail, name="event_detail"),
    path("events/<int:pk>/edit/", views.event_edit, name="event_edit"),
    path("events/<int:pk>/stop/", views.event_stop, name="event_stop"),
    path("events/<int:pk>/note/", views.event_append_note, name="event_append_note"),
    path("events/<int:pk>/fields/", views.event_field_add, name="event_field_add"),
    path(
        "events/<int:pk>/fields/<int:field_pk>/delete/",
        views.event_field_delete,
        name="event_field_delete",
    ),
    path("events/<int:pk>/delete/", views.event_delete, name="event_delete"),
]
