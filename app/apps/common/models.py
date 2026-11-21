"""Abstract bases for per-user data ownership.

Both managers read the current user from thread-local storage, populated by
``apps.common.middleware.thread_local.ThreadLocalMiddleware``. That keeps
ownership filtering out of every view and queryset, at the cost of an implicit
dependency on the request cycle: in management commands and background tasks
there is no current user, so the manager falls back to the unowned rows. Use
``Model._base_manager`` when you deliberately want everything.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.common.middleware.thread_local import get_current_user


class SharedObjectManager(models.Manager):
    def get_queryset(self):
        user = get_current_user()
        base_qs = super().get_queryset()

        if user and user.is_authenticated:
            return base_qs.filter(
                Q(visibility=SharedObject.Visibility.public)
                | Q(owner=user)
                | Q(shared_with=user)
                | Q(owner=None)
            ).distinct()

        return base_qs.filter(visibility=SharedObject.Visibility.public)


class SharedObject(models.Model):
    """Owned by one user, optionally shared with others or made public.

    Subclasses must attach the manager themselves::

        class Note(SharedObject):
            objects = SharedObjectManager()
    """

    class Visibility(models.TextChoices):
        private = "private", _("Private")
        public = "public", _("Public")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(class)s_owned",
        null=True,
        blank=True,
        verbose_name=_("Owner"),
    )
    visibility = models.CharField(
        max_length=10,
        choices=Visibility.choices,
        default=Visibility.private,
        verbose_name=_("Visibility"),
    )
    shared_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="%(class)s_shared",
        blank=True,
        verbose_name=_("Shared with users"),
    )

    class Meta:
        abstract = True
        indexes = [models.Index(fields=["visibility"])]

    def is_accessible_by(self, user):
        return (
            self.visibility == self.Visibility.public
            or self.owner is None
            or self.owner == user
            or self.shared_with.filter(pk=user.pk).exists()
        )

    def save(self, *args, **kwargs):
        if not self.pk and not self.owner:
            self.owner = get_current_user()
        super().save(*args, **kwargs)


class OwnedObjectManager(models.Manager):
    def get_queryset(self):
        user = get_current_user()
        base_qs = super().get_queryset()

        if user and user.is_authenticated:
            return base_qs.filter(Q(owner=user) | Q(owner=None)).distinct()

        return base_qs


class OwnedObject(models.Model):
    """Belongs to exactly one user, with no sharing.

    Subclasses must attach the manager themselves::

        class Draft(OwnedObject):
            objects = OwnedObjectManager()
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(class)s_owned",
        null=True,
        blank=True,
        verbose_name=_("Owner"),
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.pk and not self.owner:
            self.owner = get_current_user()
        super().save(*args, **kwargs)
