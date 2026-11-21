"""Production settings.

Everything here is either a hardening default or something that only makes
sense once the app is served behind a real web server.
"""

import os

from .base import *  # noqa: F401,F403
from .base import HTTPS_ENABLED, env_bool

DEBUG = env_bool("DEBUG", False)

# No fallback: refusing to boot without a key beats booting with a known one.
# ``apps.common.checks`` reports this as a system check error.
SECRET_KEY = os.getenv("SECRET_KEY", "")

DJANGO_VITE_DEV_MODE = False

SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0")) if HTTPS_ENABLED else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS")
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD")
SECURE_SSL_REDIRECT = HTTPS_ENABLED and env_bool("SECURE_SSL_REDIRECT", True)
CSRF_COOKIE_SECURE = HTTPS_ENABLED
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "webmaster@localhost")
