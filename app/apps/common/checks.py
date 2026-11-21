"""System checks for the environment variables the project needs.

Django runs these before serving, so a missing ``SECRET_KEY`` surfaces as a
startup error rather than as a confusing failure much later.
"""

import os

from django.core.checks import Error, register

# (name, why it matters) -- these have no usable default.
REQUIRED_ENV_VARS = [
    ("SECRET_KEY", "Used for cryptographic signing."),
]
# Only needed once SQL_HOST switches the database to PostgreSQL.
if os.getenv("SQL_HOST"):
    REQUIRED_ENV_VARS.append(("SQL_DATABASE", "Name of the PostgreSQL database."))

# These may be unset, but must parse as an integer when present.
INT_ENV_VARS = [
    ("SESSION_EXPIRY_TIME", "Age of session cookies, in seconds."),
    ("INTERNAL_PORT", "Port the app listens on inside the container."),
    ("DJANGO_VITE_DEV_SERVER_PORT", "Port Vite's dev server runs on."),
]


@register()
def check_required_env_vars(app_configs, **kwargs):
    errors = []
    for var_name, description in REQUIRED_ENV_VARS:
        if not os.getenv(var_name):
            errors.append(
                Error(
                    f"Required environment variable '{var_name}' is not set.",
                    hint=f"{description} Set it in your .env file or environment.",
                    id="timelines.E001",
                )
            )
    return errors


@register()
def check_int_env_vars(app_configs, **kwargs):
    errors = []
    for var_name, description in INT_ENV_VARS:
        value = os.getenv(var_name)
        if value is None:
            continue
        try:
            int(value)
        except ValueError:
            errors.append(
                Error(
                    f"Environment variable '{var_name}' must be an integer, "
                    f"got '{value}'.",
                    hint=description,
                    id="timelines.E002",
                )
            )
    return errors
