from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
from apps.common.decorators.user import htmx_login_required, is_superuser
from apps.users.forms import (
    APITokenCreateForm,
    LoginForm,
    UserAddForm,
    UserSettingsForm,
    UserUpdateForm,
)
from apps.users.models import APIToken


User = get_user_model()


class UserLoginView(LoginView):
    form_class = LoginForm
    template_name = "users/login.html"
    redirect_authenticated_user = True


def logout_view(request):
    logout(request)
    return redirect(reverse("login"))


@only_htmx
@htmx_login_required
@require_http_methods(["GET"])
def toggle_theme(request):
    """Flip the stored theme. The class swap already happened client-side."""
    current = request.session.get("theme", "dark")
    request.session["theme"] = "light" if current == "dark" else "dark"
    return HttpResponse(status=204)


@only_htmx
@htmx_login_required
@require_http_methods(["GET"])
def toggle_sidebar_status(request):
    current = request.session.get("sidebar_status", "floating")
    request.session["sidebar_status"] = "fixed" if current == "floating" else "floating"
    return HttpResponse(status=204)


@only_htmx
@htmx_login_required
def update_settings(request):
    user_settings = request.user.settings

    if request.method == "POST":
        form = UserSettingsForm(request.POST, instance=user_settings)
        if form.is_valid():
            form.save()
            messages.success(request, _("Your settings have been updated"))
            # The language and time zone affect every rendered string, so the
            # whole page is reloaded rather than swapped.
            return HttpResponse(status=204, headers={"HX-Refresh": "true"})
    else:
        form = UserSettingsForm(instance=user_settings)

    context = {"form": form}
    context["api_token_form"] = APITokenCreateForm()
    context["api_tokens"] = request.user.api_tokens.all()
    return render(request, "users/fragments/user_settings.html", context)


# a full page (opened by URL or reload), unlike the htmx-only fragments below
@htmx_login_required
@is_superuser
@require_http_methods(["GET"])
def users_index(request):
    return render(request, "users/pages/index.html")


@only_htmx
@htmx_login_required
@is_superuser
@require_http_methods(["GET"])
def users_list(request):
    return render(
        request,
        "users/fragments/list.html",
        {"users": User.objects.all().order_by("email")},
    )


@only_htmx
@htmx_login_required
@is_superuser
@require_http_methods(["GET", "POST"])
def user_add(request):
    if request.method == "POST":
        form = UserAddForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("User added successfully"))
            return HttpResponse(status=204, headers={"HX-Trigger": "updated, hide_offcanvas"})
    else:
        form = UserAddForm()

    return render(request, "users/fragments/add.html", {"form": form})


@only_htmx
@htmx_login_required
@require_http_methods(["GET", "POST"])
def user_edit(request, pk):
    # A user may always edit themselves; editing anyone else is an admin action.
    if request.user.pk != pk and not request.user.is_superuser:
        raise PermissionDenied

    user = get_object_or_404(User, pk=pk)

    if request.method == "POST":
        form = UserUpdateForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, _("User updated successfully"))
            return HttpResponse(status=204, headers={"HX-Trigger": "updated, hide_offcanvas"})
    else:
        form = UserUpdateForm(instance=user)

    return render(request, "users/fragments/edit.html", {"form": form, "object": user})


def _render_api_tokens(request, *, form=None, raw_token=None):
    return render(
        request,
        "users/fragments/api_tokens.html",
        {
            "api_token_form": form or APITokenCreateForm(),
            "api_tokens": request.user.api_tokens.all(),
            # Shown once, then gone: only the hash is stored.
            "raw_token": raw_token,
        },
    )


@only_htmx
@htmx_login_required
@require_http_methods(["POST"])
def api_token_add(request):
    form = APITokenCreateForm(request.POST)
    if form.is_valid():
        _token, raw_token = form.save(user=request.user)
        messages.success(request, _("API token created successfully"))
        return _render_api_tokens(
            request, form=APITokenCreateForm(), raw_token=raw_token
        )

    return _render_api_tokens(request, form=form)


@only_htmx
@htmx_login_required
@require_http_methods(["DELETE"])
def api_token_revoke(request, token_id):
    token = get_object_or_404(APIToken, id=token_id, user=request.user)
    if token.revoked_at is None:
        token.revoked_at = timezone.now()
        token.save(update_fields=["revoked_at"])
    messages.success(request, _("API token revoked successfully"))
    return _render_api_tokens(request)


@only_htmx
@htmx_login_required
@require_http_methods(["DELETE"])
def api_token_delete(request, token_id):
    token = get_object_or_404(APIToken, id=token_id, user=request.user)
    token.delete()
    messages.success(request, _("API token deleted successfully"))
    return _render_api_tokens(request)
