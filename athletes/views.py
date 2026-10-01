from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from .forms import SignupForm
from .models import Athlete
from .workout_templates import GUARD_60, GUARD_60_FOCUS, create_todays_workout, todays_workout


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
    context = {"athlete": athlete, "active_tab": "record"}
    if athlete:
        context["workout"] = todays_workout(athlete)
        context["plan_focus"] = GUARD_60_FOCUS
        context["plan_drills"] = len(GUARD_60)
        context["plan_tracked"] = sum(1 for _, _, tracks in GUARD_60 if tracks)
    return render(request, "dashboard.html", context)


@login_required
def workout_today(request):
    """Today's drills. Shows the plan until Start is tapped, then the real workout."""
    athlete = get_object_or_404(Athlete, user=request.user)
    workout = todays_workout(athlete)
    context = {
        "athlete": athlete,
        "active_tab": "record",
        "workout": workout,
        "plan": GUARD_60,
        "plan_focus": GUARD_60_FOCUS,
    }
    return render(request, "workout_today.html", context)


@login_required
@require_POST
def workout_start(request):
    """Create today's workout. POST only, so just visiting a page never creates rows."""
    athlete = get_object_or_404(Athlete, user=request.user)
    create_todays_workout(athlete)
    # Step 16 sends this to the active session screen instead.
    return redirect("workout_today")
