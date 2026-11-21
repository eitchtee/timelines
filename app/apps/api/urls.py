from apps.api.views.events import EventViewSet, TagViewSet
from django.urls import include, path
from rest_framework import routers

router = routers.DefaultRouter()
router.register(r"events", EventViewSet, basename="api-events")
router.register(r"tags", TagViewSet, basename="api-tags")

urlpatterns = [
    path("", include(router.urls)),
]
