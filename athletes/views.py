from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from .forms import SignupForm
from .models import Athlete, Workout, WorkoutSet
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
    """Today's plan and the Start button. Once started, go straight to the session."""
    athlete = get_object_or_404(Athlete, user=request.user)
    workout = todays_workout(athlete)
    if workout:
        return redirect("workout_session", workout_id=workout.id)
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
    workout = create_todays_workout(athlete)
    return redirect("workout_session", workout_id=workout.id)


@login_required
def workout_session(request, workout_id):
    """The active session: one tappable row per drill."""
    # Access check in the query: someone else's workout ID is simply "not found".
    workout = get_object_or_404(Workout, id=workout_id, athlete__user=request.user)
    context = {
        "athlete": workout.athlete,
        "active_tab": "record",
        "workout": workout,
        "sets": workout.workoutset_set.all(),
    }
    return render(request, "workout_session.html", context)


@login_required
@require_POST
def set_toggle(request, set_id):
    """Tap a drill: flip done/not done, send back just that row."""
    # Access check in the query, through the workout to its athlete's login.
    workout_set = get_object_or_404(WorkoutSet, id=set_id, workout__athlete__user=request.user)
    workout_set.completed = not workout_set.completed
    workout_set.save(update_fields=["completed"])

    if not request.htmx:
        # No HTMX (old browser, script blocked): fall back to reloading the page.
        return redirect("workout_session", workout_id=workout_set.workout_id)
    return render(request, "partials/set_row.html", {"set": workout_set})
