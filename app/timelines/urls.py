"""URL configuration for Timelines.

App URLconfs are mounted at the root so each app owns its own path prefix.
Add new apps to the block at the bottom.
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.api.mcp import mcp_endpoint

urlpatterns = [
    path("admin/", admin.site.urls),
    path("hijack/", include("hijack.urls")),
    path("", include("pwa.urls")),
    path("api/", include("apps.api.urls")),
    path("mcp/", mcp_endpoint, name="mcp_endpoint"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("auth/", include("allauth.urls")),
    # Project apps.
    path("", include("apps.events.urls")),
    path("", include("apps.common.urls")),
    path("", include("apps.users.urls")),
]

if settings.DEBUG:
    urlpatterns += [
        path("__debug__/", include("debug_toolbar.urls")),
        path("__reload__/", include("django_browser_reload.urls")),
    ]
