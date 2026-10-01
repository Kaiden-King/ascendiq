from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.text import slugify

from .forms import SignupForm
from .models import Athlete


def unique_slug(full_name):
    """'Kaiden King' -> 'kaiden-king', or 'kaiden-king-2' if that's taken."""
    base = slugify(full_name) or "athlete"
    slug = base
    number = 2
    while Athlete.objects.filter(slug=slug).exists():
        slug = f"{base}-{number}"
        number += 1
    return slug


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            # Both rows or neither — never a login without an athlete profile.
            with transaction.atomic():
                user = form.save()
                Athlete.objects.create(
                    user=user,
                    full_name=form.cleaned_data["full_name"],
                    slug=unique_slug(form.cleaned_data["full_name"]),
                )
            login(request, user)
            return redirect("dashboard")
    else:
        form = SignupForm()

    return render(request, "registration/signup.html", {"form": form})


@login_required
def dashboard(request):
    # Only ever the logged-in user's own athlete. Admin logins have none.
    athlete = Athlete.objects.filter(user=request.user).first()
    return render(request, "dashboard.html", {"athlete": athlete, "active_tab": "record"})
