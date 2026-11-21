from django.contrib import admin
from django.utils.translation import gettext_lazy as _


@admin.action(description=_("Make public"))
def make_public(modeladmin, request, queryset):
    queryset.update(visibility="public")


@admin.action(description=_("Make private"))
def make_private(modeladmin, request, queryset):
    queryset.update(visibility="private")


class SharedObjectModelAdmin(admin.ModelAdmin):
    """Admin base for models inheriting ``apps.common.models.SharedObject``."""

    actions = [make_public, make_private]

    list_display = ("__str__", "visibility", "owner", "get_shared_with")
    list_filter = ("visibility",)

    @admin.display(description=_("Shared with users"))
    def get_shared_with(self, obj):
        return ", ".join(user.email for user in obj.shared_with.all())

    def get_queryset(self, request):
        # SharedObject's default manager filters by the current user; admins
        # need to see every row, so go through the unfiltered base manager.
        return self.model._base_manager.all()
