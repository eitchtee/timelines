"""Base settings for Timelines.

Shared by every environment. ``dev`` and ``prod`` import ``*`` from here and
override what differs. Anything deployment-specific is read from the
environment so the same image can run anywhere.
"""

import os
import re
from pathlib import Path

# app/ -- holds manage.py, apps/, templates/, static/
BASE_DIR = Path(__file__).resolve().parent.parent.parent
# repository root -- holds app/, frontend/, docker/
ROOT_DIR = BASE_DIR.parent

SITE_TITLE = "Timelines"
TITLE_SEPARATOR = "::"

APP_VERSION = os.getenv("APP_VERSION", "0.1.0")


def env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------- core

SECRET_KEY = os.getenv("SECRET_KEY", "")

DEBUG = env_bool("DEBUG")

ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost 127.0.0.1").split()
CSRF_TRUSTED_ORIGINS = os.getenv("URL", "http://localhost http://127.0.0.1").split()

ROOT_URLCONF = "timelines.urls"
WSGI_APPLICATION = "timelines.wsgi.application"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------- apps

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.sites",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.postgres",
    "django.forms",
]

THIRD_PARTY_APPS = [
    "django_vite",
    "django_cotton",
    "crispy_forms",
    "crispy_bootstrap5",
    "django_filters",
    "hijack",
    "hijack.contrib.admin",
    "cachalot",
    "rest_framework",
    "drf_spectacular",
    "pwa",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.openid_connect",
]

LOCAL_APPS = [
    "apps.users.apps.UsersConfig",
    "apps.events.apps.EventsConfig",
    "apps.api.apps.ApiConfig",
    # The common app unregisters admin entries and registers system checks in
    # ``ready()``, so it stays last -- everything it touches is loaded by then.
    "apps.common.apps.CommonConfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

SITE_ID = 1

MIDDLEWARE = [
    "apps.common.middleware.thread_local.ThreadLocalMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.common.middleware.localization.LocalizationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "hijack.middleware.HijackUserMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------- database

# psycopg's pool is sized off the worker thread count: one connection per
# thread plus a spare.
THREADS = int(os.getenv("GUNICORN_THREADS", "1"))
MAX_POOL_SIZE = THREADS + 1

SQLITE_PATH = Path(os.getenv("SQLITE_PATH", BASE_DIR / "data" / "db.sqlite3"))

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("SQL_DATABASE"),
        "USER": os.getenv("SQL_USER", "user"),
        "PASSWORD": os.getenv("SQL_PASSWORD", "password"),
        "HOST": os.getenv("SQL_HOST", "localhost"),
        "PORT": os.getenv("SQL_PORT", "5432"),
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            "pool": {
                "min_size": 1,
                "max_size": MAX_POOL_SIZE,
                "timeout": 10,
                "max_lifetime": 600,
                "max_idle": 300,
            },
        },
    }
}

# No SQL_HOST means no PostgreSQL server: keep everything in one SQLite file.
if not os.getenv("SQL_HOST"):
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": SQLITE_PATH,
            "OPTIONS": {
                # WAL + IMMEDIATE lets several gunicorn workers write without
                # "database is locked" errors.
                "transaction_mode": "IMMEDIATE",
                "timeout": 20,
                "init_command": (
                    "PRAGMA journal_mode=WAL;"
                    "PRAGMA synchronous=NORMAL;"
                    "PRAGMA busy_timeout=20000;"
                ),
            },
        }
    }

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": os.getenv("CACHE_LOCATION", "/var/tmp/django_cache"),
    }
}

CACHALOT_UNCACHABLE_TABLES = ("django_migrations",)

# ---------------------------------------------------------------- auth

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_REDIRECT_URL = "/"
LOGIN_URL = "/login/"
LOGOUT_REDIRECT_URL = "/login/"

SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_AGE = int(os.getenv("SESSION_EXPIRY_TIME", "2678400"))  # 31 days

HTTPS_ENABLED = env_bool("HTTPS_ENABLED")
SESSION_COOKIE_SECURE = HTTPS_ENABLED
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if HTTPS_ENABLED else None

# ---------------------------------------------------------------- allauth

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_ADAPTER = "allauth.account.adapter.DefaultAccountAdapter"
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https" if HTTPS_ENABLED else "http"

SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_AUTO_SIGNUP = env_bool("OIDC_ALLOW_SIGNUP", True)
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_ADAPTER = "apps.users.adapters.AutoConnectSocialAccountAdapter"

SOCIALACCOUNT_PROVIDERS = {"openid_connect": {"APPS": []}}

# The provider is only registered when fully configured, so a project without
# SSO falls back to the plain e-mail/password login form.
if all(
    os.getenv(var) for var in ("OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "OIDC_SERVER_URL")
):
    from django.utils.text import slugify

    SOCIALACCOUNT_PROVIDERS["openid_connect"]["APPS"].append(
        {
            "provider_id": slugify(os.getenv("OIDC_CLIENT_NAME", "OpenID Connect")),
            "name": os.getenv("OIDC_CLIENT_NAME", "OpenID Connect"),
            "client_id": os.getenv("OIDC_CLIENT_ID"),
            "secret": os.getenv("OIDC_CLIENT_SECRET"),
            "settings": {"server_url": os.getenv("OIDC_SERVER_URL")},
        }
    )

# ---------------------------------------------------------------- i18n

LANGUAGE_CODE = "en"
TIME_ZONE = os.getenv("TZ", "UTC")
USE_I18N = True
USE_TZ = True
LOCALE_PATHS = [BASE_DIR / "locale"]

# ---------------------------------------------------------------- static

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "static_files"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

STATICFILES_DIRS = [
    ROOT_DIR / "frontend" / "build",
    BASE_DIR / "static",
]

STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

WHITENOISE_MANIFEST_STRICT = False


def immutable_file_test(path, url):
    """Match vite (rollup)-generated hashes, e.g. ``some_file-CSliV9zW.js``."""
    return re.match(r"^.+[.-][0-9a-zA-Z_-]{8,12}\..+$", url)


WHITENOISE_IMMUTABLE_FILE_TEST = immutable_file_test

# ---------------------------------------------------------------- vite

DJANGO_VITE_ASSETS_PATH = STATIC_ROOT
DJANGO_VITE_MANIFEST_PATH = DJANGO_VITE_ASSETS_PATH / "manifest.json"
DJANGO_VITE_DEV_MODE = env_bool("DJANGO_VITE_DEV_MODE")
DJANGO_VITE_DEV_SERVER_PORT = int(os.getenv("DJANGO_VITE_DEV_SERVER_PORT", "5173"))
DJANGO_VITE_DEV_SERVER_HOST = os.getenv("DJANGO_VITE_DEV_SERVER_HOST", "localhost")

# ---------------------------------------------------------------- forms

CRISPY_ALLOWED_TEMPLATE_PACKS = ["crispy-daisyui", "bootstrap5"]
CRISPY_TEMPLATE_PACK = "crispy-daisyui"

# ---------------------------------------------------------------- api

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.DjangoModelPermissions",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.api.authentication.APITokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.api.pagination.DefaultPagination",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Timelines API",
    "DESCRIPTION": "Track and visualize minor life events on connected timelines.",
    "VERSION": APP_VERSION,
    "SERVE_INCLUDE_SCHEMA": False,
}

# Personal access tokens: ``last_used_at`` is rewritten at most once per
# interval so authenticated requests don't each cost a database write.
API_TOKEN_LAST_USED_UPDATE_INTERVAL = int(
    os.getenv("API_TOKEN_LAST_USED_UPDATE_INTERVAL", "600")
)

# ---------------------------------------------------------------- pwa

PWA_APP_NAME = SITE_TITLE
PWA_APP_DESCRIPTION = "Track and visualize minor life events on connected timelines."
PWA_APP_THEME_COLOR = "#b07526"
PWA_APP_BACKGROUND_COLOR = "#222222"
PWA_APP_DISPLAY = "standalone"
PWA_APP_SCOPE = "/"
PWA_APP_ORIENTATION = "any"
PWA_APP_START_URL = "/"
PWA_APP_STATUS_BAR_COLOR = "default"
PWA_APP_DIR = "ltr"
PWA_APP_LANG = "en-US"
# Placeholder mark -- swap for a real PNG icon set before shipping a PWA.
PWA_APP_ICONS = [
    {"src": "/static/img/favicon.svg", "sizes": "192x192", "type": "image/svg+xml"}
]
PWA_APP_ICONS_APPLE = [
    {"src": "/static/img/favicon.svg", "sizes": "180x180", "type": "image/svg+xml"}
]
PWA_SERVICE_WORKER_PATH = BASE_DIR / "templates" / "pwa" / "serviceworker.js"

# ---------------------------------------------------------------- logging

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "[%(asctime)s] - %(levelname)s - %(name)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "level": LOG_LEVEL,
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
}
