"""Create the bootstrap superuser from the environment.

Run on every container start (see ``docker/*/django/start``). It is idempotent:
an existing account with the same e-mail is left untouched, so the credentials
can be removed from ``.env`` after the first successful login.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import IntegrityError

User = get_user_model()


class Command(BaseCommand):
    help = "Creates a superuser from ADMIN_EMAIL / ADMIN_PASSWORD, if both are set."

    def handle(self, *args, **options):
        admin_email = os.environ.get("ADMIN_EMAIL")
        admin_password = os.environ.get("ADMIN_PASSWORD")

        if not (admin_email and admin_password):
            self.stdout.write(
                self.style.NOTICE(
                    "ADMIN_EMAIL / ADMIN_PASSWORD not set. Skipping superuser creation."
                )
            )
            return

        if User.objects.filter(email__iexact=admin_email).exists():
            self.stdout.write(
                self.style.WARNING(
                    f"Superuser '{admin_email}' already exists. Skipping."
                )
            )
            return

        try:
            User.objects.create_superuser(email=admin_email, password=admin_password)
        except IntegrityError as exc:
            self.stdout.write(
                self.style.ERROR(f"Failed to create superuser '{admin_email}': {exc}")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Superuser '{admin_email}' created successfully.")
            )
