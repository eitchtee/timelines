import hashlib
import hmac
import secrets

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.users.managers import UserManager


class User(AbstractUser):
    """E-mail is the login identifier; ``username`` is removed entirely."""

    username = None
    email = models.EmailField(_("E-mail"), unique=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email


class UserSettings(models.Model):
    """Per-user presentation preferences.

    Read by ``apps.common.middleware.localization`` on every request. The
    choice lists live on the form rather than the model: they are derived from
    ``settings.LANGUAGES`` and the tz database, both of which change between
    releases, and baking them into the field would mean a migration each time.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="settings"
    )

    language = models.CharField(max_length=10, default="auto", verbose_name=_("Language"))
    timezone = models.CharField(max_length=64, default="auto", verbose_name=_("Time zone"))

    date_format = models.CharField(
        max_length=100, default="SHORT_DATE_FORMAT", verbose_name=_("Date format")
    )
    datetime_format = models.CharField(
        max_length=100,
        default="SHORT_DATETIME_FORMAT",
        verbose_name=_("Datetime format"),
    )
    number_format = models.CharField(
        max_length=2, default="AA", verbose_name=_("Number format")
    )

    class Meta:
        verbose_name = _("User settings")
        verbose_name_plural = _("User settings")

    def __str__(self):
        return f"{self.user.email}'s settings"



class APITokenManager(models.Manager):
    def create_token(self, *, user, name: str, expires_at=None):
        token_secret = secrets.token_urlsafe(32)
        token_hash = self.model.hash_secret(token_secret)

        # token_key is unique; the pre-check in generate_token_key still leaves
        # a tiny race window under concurrency, so retry on the
        # unique-constraint violation with a fresh key instead of failing the
        # request.
        last_error = None
        for _attempt in range(5):
            token = self.model(
                user=user,
                name=name,
                token_key=self.model.generate_token_key(),
                token_hash=token_hash,
                expires_at=expires_at,
            )
            token.full_clean()
            try:
                with transaction.atomic():
                    token.save()
            except IntegrityError as exc:
                last_error = exc
                continue
            return token, token.build_raw_token(token_secret)

        raise last_error


class APIToken(models.Model):
    """Personal access token.

    Only the hash of the secret is stored. The raw token is returned once, at
    creation time, and never recoverable afterwards.
    """

    TOKEN_PREFIX = "pat_"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="api_tokens",
        verbose_name=_("User"),
    )
    name = models.CharField(max_length=255, verbose_name=_("Name"))
    token_key = models.CharField(
        max_length=16, unique=True, db_index=True, verbose_name=_("Token key")
    )
    token_hash = models.CharField(max_length=255, verbose_name=_("Token hash"))
    last_used_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Last used at")
    )
    expires_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Expires at")
    )
    revoked_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Revoked at")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))

    objects = APITokenManager()

    class Meta:
        indexes = [
            models.Index(fields=["user", "revoked_at"]),
            models.Index(fields=["expires_at"]),
        ]
        ordering = ["-created_at"]
        verbose_name = _("API token")
        verbose_name_plural = _("API tokens")

    def __str__(self):
        return f"{self.user} / {self.name}"

    @classmethod
    def generate_token_key(cls) -> str:
        while True:
            candidate = secrets.token_hex(8)
            if not cls.objects.filter(token_key=candidate).exists():
                return candidate

    @classmethod
    def parse_raw_token(cls, raw_token: str):
        if not raw_token.startswith(cls.TOKEN_PREFIX):
            raise ValueError("Token is missing the expected prefix.")

        payload = raw_token.removeprefix(cls.TOKEN_PREFIX)
        token_key, separator, token_secret = payload.partition(".")
        if not separator or not token_key or not token_secret:
            raise ValueError("Token is malformed.")
        return token_key, token_secret

    def build_raw_token(self, token_secret: str) -> str:
        return f"{self.TOKEN_PREFIX}{self.token_key}.{token_secret}"

    @staticmethod
    def hash_secret(token_secret: str) -> str:
        # The secret is a 256-bit random value (secrets.token_urlsafe(32)), so a
        # single SHA-256 is sufficient and avoids a slow KDF on every request.
        return hashlib.sha256(token_secret.encode("utf-8")).hexdigest()

    def check_secret(self, raw_secret: str) -> bool:
        return hmac.compare_digest(self.token_hash, self.hash_secret(raw_secret))

    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= timezone.now()

