"""Fast test settings.

Defaults to in-memory SQLite so ``uv run pytest`` runs anywhere without a
running PostgreSQL container. Set ``TEST_USE_POSTGRES=1`` to run against
PostgreSQL.
"""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("SQL_DATABASE", "timelines_test")

from .base import *  # noqa: F401,F403,E402
from .base import env_bool  # noqa: E402

DEBUG = False
SECRET_KEY = "test-secret-key"
DJANGO_VITE_DEV_MODE = False
DJANGO_VITE_MANIFEST_PATH = ROOT_DIR / "frontend" / "build" / "manifest.json"  # noqa: F405
CACHALOT_ENABLED = False

if not env_bool("TEST_USE_POSTGRES", False):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
