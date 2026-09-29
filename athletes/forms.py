from django import forms
from django.contrib.auth.forms import UserCreationForm


class SignupForm(UserCreationForm):
    """Django's built-in sign up form, plus the athlete's name."""

    full_name = forms.CharField(
        max_length=120,
        label="Your name",
        widget=forms.TextInput(attrs={"autocomplete": "name"}),
    )

    class Meta(UserCreationForm.Meta):
        fields = ["full_name", "username"]
