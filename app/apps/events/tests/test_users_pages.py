import pytest
from apps.users.models import User
from django.urls import reverse


@pytest.mark.django_db
def test_users_page_opens_directly_for_admins(client):
    admin = User.objects.create_superuser(email="root@example.com", password="pw123456")
    client.force_login(admin)
    # a plain page load (no HX-Request header), e.g. reload or typed URL
    assert client.get(reverse("users_index")).status_code == 200

    plain = User.objects.create_user(email="joe@example.com", password="pw123456")
    client.force_login(plain)
    assert client.get(reverse("users_index")).status_code == 403
