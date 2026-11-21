import zoneinfo
from datetime import timedelta
from functools import lru_cache

from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Column, Div, Field, Layout, Row, Submit
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    UserCreationForm,
    UsernameField,
)
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.middleware.thread_local import get_current_user
from apps.common.widgets.crispy.submit import NoClassSubmit
from apps.common.widgets.tom_select import TomSelect
from apps.users.models import APIToken, UserSettings



@lru_cache(maxsize=1)
def timezone_choices():
    return [("auto", _("Auto"))] + [
        (name, name) for name in sorted(zoneinfo.available_timezones())
    ]


def language_choices():
    return [("auto", _("Auto"))] + list(settings.LANGUAGES)


class LoginForm(AuthenticationForm):
    username = UsernameField(
        label=_("E-mail"),
        widget=forms.EmailInput(
            attrs={
                "class": "input",
                "placeholder": _("E-mail"),
                "name": "email",
                "autocomplete": "email",
            }
        ),
    )
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "input",
                "placeholder": _("Password"),
                "autocomplete": "current-password",
            }
        ),
    )

    error_messages = {
        "invalid_login": _("Invalid e-mail or password"),
        "inactive": _("This account is deactivated"),
    }

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)

        self.helper = FormHelper()
        self.helper.layout = Layout(
            "username",
            "password",
            Submit("Submit", _("Login"), css_class="w-full mt-3"),
        )


class UserSettingsForm(forms.ModelForm):
    DATE_FORMAT_CHOICES = [
        ("SHORT_DATE_FORMAT", _("Default")),
        ("d-m-Y", "20-01-2025"),
        ("m-d-Y", "01-20-2025"),
        ("Y-m-d", "2025-01-20"),
        ("d/m/Y", "20/01/2025"),
        ("m/d/Y", "01/20/2025"),
        ("Y/m/d", "2025/01/20"),
        ("d.m.Y", "20.01.2025"),
        ("m.d.Y", "01.20.2025"),
        ("Y.m.d", "2025.01.20"),
    ]

    DATETIME_FORMAT_CHOICES = [
        ("SHORT_DATETIME_FORMAT", _("Default")),
        ("d-m-Y H:i", "20-01-2025 15:30"),
        ("m-d-Y H:i", "01-20-2025 15:30"),
        ("Y-m-d H:i", "2025-01-20 15:30"),
        ("d-m-Y h:i A", "20-01-2025 03:30 PM"),
        ("m-d-Y h:i A", "01-20-2025 03:30 PM"),
        ("Y-m-d h:i A", "2025-01-20 03:30 PM"),
        ("d/m/Y H:i", "20/01/2025 15:30"),
        ("m/d/Y H:i", "01/20/2025 15:30"),
        ("Y/m/d H:i", "2025/01/20 15:30"),
        ("d/m/Y h:i A", "20/01/2025 03:30 PM"),
        ("m/d/Y h:i A", "01/20/2025 03:30 PM"),
        ("Y/m/d h:i A", "2025/01/20 03:30 PM"),
        ("d.m.Y H:i", "20.01.2025 15:30"),
        ("m.d.Y H:i", "01.20.2025 15:30"),
        ("Y.m.d H:i", "2025.01.20 15:30"),
        ("d.m.Y h:i A", "20.01.2025 03:30 PM"),
        ("m.d.Y h:i A", "01.20.2025 03:30 PM"),
        ("Y.m.d h:i A", "2025.01.20 03:30 PM"),
    ]

    NUMBER_FORMAT_CHOICES = [
        ("AA", _("Default")),
        ("DC", "1.234,50"),
        ("CD", "1,234.50"),
        ("SD", "1 234.50"),
        ("SC", "1 234,50"),
    ]

    language = forms.ChoiceField(label=_("Language"), widget=TomSelect(clear_button=False))
    timezone = forms.ChoiceField(
        label=_("Time zone"), widget=TomSelect(clear_button=False)
    )
    date_format = forms.ChoiceField(
        choices=DATE_FORMAT_CHOICES, initial="SHORT_DATE_FORMAT", label=_("Date format")
    )
    datetime_format = forms.ChoiceField(
        choices=DATETIME_FORMAT_CHOICES,
        initial="SHORT_DATETIME_FORMAT",
        label=_("Datetime format"),
    )
    number_format = forms.ChoiceField(
        choices=NUMBER_FORMAT_CHOICES, initial="AA", label=_("Number format")
    )

    class Meta:
        model = UserSettings
        fields = [
            "language",
            "timezone",
            "date_format",
            "datetime_format",
            "number_format",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Resolved at instantiation, not import: the tz database and the
        # configured languages are runtime facts.
        self.fields["language"].choices = language_choices()
        self.fields["timezone"].choices = timezone_choices()

        self.fields["language"].help_text = _(
            "Changes the interface language (when a translation exists) and how "
            "numbers and dates are displayed."
        )

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            "language",
            "timezone",
            HTML('<hr class="hr my-3" />'),
            "date_format",
            "datetime_format",
            "number_format",
            FormActions(
                NoClassSubmit("submit", _("Save"), css_class="btn btn-primary"),
            ),
        )


class UserUpdateForm(forms.ModelForm):
    new_password1 = forms.CharField(
        label=_("New password"),
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        required=False,
        help_text=_("Leave blank to keep the current password."),
    )
    new_password2 = forms.CharField(
        label=_("Confirm new password"),
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        required=False,
    )

    class Meta:
        model = get_user_model()
        fields = ["first_name", "last_name", "email", "is_active", "is_superuser"]
        help_texts = {
            "is_active": _(
                "Designates whether this user should be treated as active. "
                "Unselect this instead of deleting accounts."
            ),
            "is_superuser": _(
                "Designates that this user has all permissions without "
                "explicitly assigning them."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.requesting_user = get_current_user()

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            Row(Column("first_name"), Column("last_name"), css_class="row"),
            Field("email"),
            Div(
                Field("new_password1"),
                Field("new_password2"),
                css_class="border p-3 rounded mb-3",
            ),
            Div(
                Field("is_active"),
                Field("is_superuser"),
                css_class="border p-3 rounded mb-3",
            ),
            FormActions(
                NoClassSubmit("submit", _("Update"), css_class="btn btn-primary"),
            ),
        )

        # Nobody edits their own privileges here, and non-superusers never do.
        if (
            self.requesting_user == self.instance
            or not getattr(self.requesting_user, "is_superuser", False)
        ):
            self.fields["is_superuser"].disabled = True
            self.fields["is_active"].disabled = True

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if (
            self.instance
            and get_user_model()
            .objects.filter(email__iexact=email)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError(
                _("This e-mail address is already in use by another account.")
            )
        return email

    def clean_new_password2(self):
        new_password1 = self.cleaned_data.get("new_password1")
        new_password2 = self.cleaned_data.get("new_password2")
        if new_password1 and new_password1 != new_password2:
            raise forms.ValidationError(_("The two password fields didn't match."))
        if new_password1 and not new_password2:
            raise forms.ValidationError(_("Please confirm your new password."))
        if new_password2 and not new_password1:
            raise forms.ValidationError(_("Please enter the new password first."))
        return new_password2

    def clean(self):
        cleaned_data = super().clean()

        # Guard against an admin locking themselves out, and against the last
        # superuser being demoted, which would leave nobody able to fix it.
        if (
            self.requesting_user
            and self.instance
            and self.requesting_user.pk == self.instance.pk
        ):
            if cleaned_data.get("is_active") is False:
                self.add_error(
                    "is_active",
                    _("You cannot deactivate your own account using this form."),
                )

            if self.instance.is_superuser and cleaned_data.get("is_superuser") is False:
                if get_user_model().objects.filter(is_superuser=True).count() <= 1:
                    self.add_error(
                        "is_superuser",
                        _("Cannot remove status from the last superuser."),
                    )
                else:
                    self.add_error(
                        "is_superuser",
                        _("You cannot remove your own superuser status here."),
                    )

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        new_password = self.cleaned_data.get("new_password1")
        if new_password:
            user.set_password(new_password)
        if commit:
            user.save()
        return user


class UserAddForm(UserCreationForm):
    """Administrator-facing form for provisioning a new account."""

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("email", "first_name", "last_name", "is_active", "is_superuser")
        field_classes = {"email": forms.EmailField}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["is_active"].initial = True

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            Field("email"),
            Row(Column("first_name"), Column("last_name"), css_class="row"),
            Div(
                Field("password1", autocomplete="new-password"),
                Field("password2", autocomplete="new-password"),
                css_class="border p-3 rounded mb-3",
            ),
            Div(
                Field("is_active"),
                Field("is_superuser"),
                css_class="border p-3 rounded mb-3",
            ),
            FormActions(
                NoClassSubmit("submit", _("Add"), css_class="btn btn-primary"),
            ),
        )

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email and get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                _("A user with this e-mail address already exists.")
            )
        return email

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
        return user


class APITokenCreateForm(forms.Form):
    name = forms.CharField(
        max_length=255,
        label=_("Token name"),
        help_text=_("Use a descriptive name, e.g. the tool that will use it."),
    )
    expires_in_days = forms.IntegerField(
        required=False,
        min_value=1,
        label=_("Expires in days"),
        help_text=_("Leave empty for a non-expiring token."),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            "name",
            "expires_in_days",
            FormActions(
                NoClassSubmit("submit", _("Create token"), css_class="btn btn-primary"),
            ),
        )

    def save(self, user):
        expires_in_days = self.cleaned_data.get("expires_in_days")
        expires_at = None
        if expires_in_days:
            expires_at = timezone.now() + timedelta(days=expires_in_days)

        return APIToken.objects.create_token(
            user=user,
            name=self.cleaned_data["name"],
            expires_at=expires_at,
        )
