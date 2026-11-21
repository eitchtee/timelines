from cachalot.api import invalidate
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
from apps.common.decorators.user import htmx_login_required, is_superuser


@login_required
@require_http_methods(["GET"])
def home(request):
    """Landing page. Replace this with whatever your project opens on."""
    return render(request, "pages/home.html")


@only_htmx
@htmx_login_required
@require_http_methods(["GET"])
def toasts(request):
    """Drain the message queue.

    The base layout polls this on load and whenever a view fires an ``updated``
    event, so a view can queue a message and return 204 without rendering.
    """
    return render(request, "common/fragments/toasts.html")


@only_htmx
@login_required
@is_superuser
@require_http_methods(["GET"])
def invalidate_cache(request):
    invalidate()
    messages.success(request, _("Cache cleared successfully"))
    return HttpResponse(status=204, headers={"HX-Trigger": "updated"})
