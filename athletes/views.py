import datetime

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from .forms import POSITIONS, HighlightForm, ProfileForm, SignupForm
from .models import Athlete, Highlight, Workout, WorkoutSet
from .stats import (
    LEADERBOARD_GRADES, grad_year_for, grade_for, minutes_between, pct_change,
    shooting_pct, shooting_totals, short_name, streak, week_start,
)
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
        context["total"], context["last_date"] = history_numbers(athlete)
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


def workout_shooting(workout):
    """(made, attempted, pct) across all of a workout's shooting drills. One query."""
    totals = workout.workoutset_set.aggregate(made=Sum("made"), attempted=Sum("attempted"))
    made = totals["made"] or 0
    attempted = totals["attempted"] or 0
    return made, attempted, shooting_pct(made, attempted)


def workout_progress(workout):
    """Everything the progress bar at the top of the session screen shows."""
    drills = workout.workoutset_set
    done = drills.filter(completed=True).count()
    total = drills.count()
    made, attempted, pct = workout_shooting(workout)
    return {
        "done": done,
        "total": total,
        "bar_pct": round(done / total * 100) if total else 0,
        "made": made,
        "attempted": attempted,
        "pct": pct,
    }


def with_progress(request, template, context, workout):
    """Render a fragment, plus the progress bar as an HTMX out-of-band swap.

    One response updates two places: the thing you tapped, and the bar at the top.
    """
    fragment = render_to_string(template, context, request=request)
    progress = render_to_string(
        "partials/progress.html", {"progress": workout_progress(workout), "oob": True}, request=request
    )
    return HttpResponse(fragment + progress)


@login_required
def workout_session(request, workout_id):
    """The active session: one tappable row per drill."""
    # Access check in the query: someone else's workout ID is simply "not found".
    workout = get_object_or_404(Workout, id=workout_id, athlete__user=request.user)
    if workout.status == "completed":
        return redirect("workout_summary", workout_id=workout.id)
    context = {
        "athlete": workout.athlete,
        "active_tab": "record",
        "workout": workout,
        "sets": workout.workoutset_set.all(),
        "progress": workout_progress(workout),
    }
    return render(request, "workout_session.html", context)


@login_required
@require_POST
def set_toggle(request, set_id):
    """Tap a drill: flip done/not done, send back just that row."""
    # Access check in the query, through the workout to its athlete's login.
    # A finished workout is locked: its drills are "not found".
    workout_set = get_object_or_404(
        WorkoutSet, id=set_id, workout__athlete__user=request.user, workout__status="in_progress"
    )
    workout_set.completed = not workout_set.completed
    workout_set.save(update_fields=["completed"])

    if not request.htmx:
        # No HTMX (old browser, script blocked): fall back to reloading the page.
        return redirect("workout_session", workout_id=workout_set.workout_id)
    return with_progress(request, "partials/set_row.html", {"set": workout_set}, workout_set.workout)


MAX_SHOTS = 999  # a typo guard, not a real limit


def parse_shots(raw):
    """A box's value as a whole number 0–999, or None if it isn't one."""
    raw = (raw or "").strip()
    if not raw.isdigit():  # rejects "", "-3", "4.5", "abc"
        return None
    number = int(raw)
    return number if number <= MAX_SHOTS else None


@login_required
@require_POST
def set_score(request, set_id):
    """Save makes and attempts for one shooting drill. Never trust what the browser sends."""
    # Access check in the query. Only unfinished workouts, and only shooting drills
    # (made__isnull=False), can take scores.
    workout_set = get_object_or_404(
        WorkoutSet, id=set_id, workout__athlete__user=request.user,
        workout__status="in_progress", made__isnull=False,
    )
    raw_made = (request.POST.get("made") or "").strip()
    raw_attempted = (request.POST.get("attempted") or "").strip()
    made = parse_shots(raw_made)
    attempted = parse_shots(raw_attempted)

    # This runs while the athlete is still typing, so half-typed numbers are
    # normal: those get a calm hint and aren't saved. Red errors are only for
    # input that can never be right.
    error = None
    hint = None
    if not raw_made or not raw_attempted:
        hint = "Enter makes and attempts"
    elif made is None or attempted is None:
        error = "Use whole numbers from 0 to 999."
    elif made > 0 and attempted == 0:
        hint = "Now enter attempts"
    elif made > attempted:
        # e.g. attempts shows "5" on the way to "50"
        hint = f"Attempts need to be at least {made}"
    else:
        workout_set.made = made
        workout_set.attempted = attempted
        workout_set.save(update_fields=["made", "attempted"])

    if not request.htmx:
        return redirect("workout_session", workout_id=workout_set.workout_id)
    # 200 even on a validation error, so the message shows in place of the status line.
    return with_progress(request, "partials/score_status.html", {
        "set": workout_set,
        "pct": workout_set.pct,
        "saved": error is None and hint is None,
        "error": error,
        "hint": hint,
    }, workout_set.workout)


@login_required
@require_POST
def set_shot(request, set_id):
    """+MAKE or +MISS: count one shot. Built for fast, repeated taps."""
    result = request.POST.get("result")
    if result not in ("make", "miss"):
        return HttpResponseBadRequest("result must be make or miss")

    # Access check in the query, same rules as typing a score.
    workout_set = get_object_or_404(
        WorkoutSet, id=set_id, workout__athlete__user=request.user,
        workout__status="in_progress", made__isnull=False,
    )
    # F() does the +1 inside the database, so two quick taps can't both read
    # 40 and both write 41 — each tap really counts.
    WorkoutSet.objects.filter(id=workout_set.id, attempted__lt=MAX_SHOTS).update(
        made=F("made") + (1 if result == "make" else 0),
        attempted=F("attempted") + 1,
    )
    workout_set.refresh_from_db()

    if not request.htmx:
        return redirect("workout_session", workout_id=workout_set.workout_id)
    # Main swap: the two number boxes. Out of band: the status line and the progress bar.
    return with_progress(request, "partials/score_form.html", {
        "set": workout_set,
        "oob_status": True,
    }, workout_set.workout)


HISTORY_PER_PAGE = 10


def history_numbers(athlete):
    """Total finished workouts and the date of the last one. One query each."""
    finished = Workout.objects.filter(athlete=athlete, status="completed")
    last = finished.order_by("-date").values_list("date", flat=True).first()
    return finished.count(), last


@login_required
def history(request):
    """Past workouts, newest first, 10 to a page."""
    athlete = get_object_or_404(Athlete, user=request.user)
    # Only this athlete's workouts. Sum each workout's makes/attempts in the same query.
    workouts = (
        Workout.objects.filter(athlete=athlete)
        .annotate(made_total=Sum("workoutset__made"), attempted_total=Sum("workoutset__attempted"))
        .order_by("-date", "-id")
    )
    page = Paginator(workouts, HISTORY_PER_PAGE).get_page(request.GET.get("page"))
    for workout in page:
        workout.pct = shooting_pct(workout.made_total or 0, workout.attempted_total)

    total, last_date = history_numbers(athlete)
    return render(request, "history.html", {
        "athlete": athlete,
        "active_tab": "record",
        "page": page,
        "total": total,
        "last_date": last_date,
    })


@login_required
@require_POST
def workout_finish(request, workout_id):
    """Mark the workout completed and record how long it took. Only ever once."""
    workout = get_object_or_404(Workout, id=workout_id, athlete__user=request.user)

    if workout.status != "completed":
        now = timezone.now()
        duration = minutes_between(workout.started_at, now) if workout.started_at else None
        # The status check is inside the UPDATE itself, so two quick taps on
        # Finish can't both succeed — the second one updates nothing.
        Workout.objects.filter(id=workout.id, status="in_progress").update(
            status="completed", duration_min=duration
        )
    return redirect("workout_summary", workout_id=workout.id)


@login_required
def workout_summary(request, workout_id):
    """What you did: drills done, shooting %, time taken."""
    workout = get_object_or_404(Workout, id=workout_id, athlete__user=request.user)
    if workout.status != "completed":
        return redirect("workout_session", workout_id=workout.id)

    sets = list(workout.workoutset_set.all())
    shooting_sets = [s for s in sets if s.made is not None]
    made, attempted, pct = shooting_totals([(s.made, s.attempted) for s in shooting_sets])

    # Compare with the finished workout just before this one (same athlete only).
    previous = (
        Workout.objects.filter(athlete=workout.athlete, status="completed")
        .filter(Q(date__lt=workout.date) | Q(date=workout.date, id__lt=workout.id))
        .order_by("-date", "-id")
        .first()
    )
    previous_pct = workout_shooting(previous)[2] if previous else None
    change = pct_change(pct, previous_pct)

    return render(request, "workout_summary.html", {
        "change": change,
        "previous": previous,
        "athlete": workout.athlete,
        "active_tab": "record",
        "workout": workout,
        "sets": sets,
        "drills_done": sum(1 for s in sets if s.completed),
        "drills_total": len(sets),
        "made": made,
        "attempted": attempted,
        "pct": pct,
    })


MAX_HIGHLIGHTS = 8


def profile_context(athlete, highlight_form):
    """Everything the profile page shows. Shared by the page and a failed highlight add."""
    total, _ = history_numbers(athlete)
    finished = Workout.objects.filter(athlete=athlete, status="completed").aggregate(
        made=Sum("workoutset__made"), attempted=Sum("workoutset__attempted")
    )
    highlights = list(athlete.highlight_set.all())
    return {
        "athlete": athlete,
        "active_tab": "profile",
        "highlights": highlights,
        "total": total,
        "season_pct": shooting_pct(finished["made"] or 0, finished["attempted"]),
        "highlight_form": highlight_form,
        "can_add_highlight": len(highlights) < MAX_HIGHLIGHTS,
        "my_short_name": short_name(athlete.full_name),
    }


@login_required
def profile(request):
    """Your own profile. Only you can see this page — public profiles are separate."""
    athlete = get_object_or_404(Athlete, user=request.user)
    return render(request, "profile.html", profile_context(athlete, HighlightForm()))


@login_required
def profile_edit(request):
    athlete = get_object_or_404(Athlete, user=request.user)
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=athlete)
        if form.is_valid():
            form.save()
            return redirect("profile")
    else:
        form = ProfileForm(instance=athlete)
    return render(request, "profile_edit.html", {
        "athlete": athlete,
        "active_tab": "profile",
        "form": form,
        "positions": POSITIONS,
    })


@login_required
@require_POST
def highlight_add(request):
    athlete = get_object_or_404(Athlete, user=request.user)
    form = HighlightForm(request.POST)
    if athlete.highlight_set.count() >= MAX_HIGHLIGHTS:
        form.add_error(None, f"You can have up to {MAX_HIGHLIGHTS} highlights. Remove one first.")
    if form.is_valid():
        highlight = form.save(commit=False)
        highlight.athlete = athlete
        highlight.save()
        return redirect("profile")
    # Show the profile again, with the add form open and its error messages.
    context = profile_context(athlete, form)
    context["open_highlight_form"] = True
    return render(request, "profile.html", context, status=400)


@login_required
@require_POST
def highlight_delete(request, highlight_id):
    # Access check in the query: only your own highlights can be removed.
    highlight = get_object_or_404(Highlight, id=highlight_id, athlete__user=request.user)
    highlight.delete()
    return redirect("profile")


# --- Leaderboards -----------------------------------------------------------

LEADERBOARD_MIN_ATHLETES = 4  # fewer than this and a board would point at specific kids
# key: (chip label, what the board is ranking — shown under the chips)
LEADERBOARD_STATS = {
    "workouts": ("This week", "Finished workouts since Monday"),
    "streak": ("Streak", "Days in a row with a finished workout"),
    "shooting": ("Shooting %", "Last 30 days · 50+ shots to rank"),
}
SHOOTING_MIN_ATTEMPTS = 50  # so one 5-for-5 day can't top the board


def leaderboard_rows(grade, stat, today):
    """Ranked rows for one grade and one stat. Only opted-in athletes, 8th grade and up.

    Each row holds only what the board shows: a short name, initials, the number,
    and the athlete id (to highlight "you"). No school, no full name, no photo.
    """
    athletes = list(
        Athlete.objects.filter(on_leaderboard=True, grad_year=grad_year_for(grade, today))
    )
    if not athletes:
        return []

    week_from = week_start(today)
    month_from = today - datetime.timedelta(days=29)
    finished = Workout.objects.filter(athlete__in=athletes, status="completed")

    # One query per stat for the whole board, not one per athlete.
    workouts_this_week = dict(
        finished.filter(date__gte=week_from).values("athlete").annotate(n=Count("id")).values_list("athlete", "n")
    )
    shots = {
        row["athlete"]: (row["made"] or 0, row["attempted"] or 0)
        for row in finished.filter(date__gte=month_from).values("athlete").annotate(
            made=Sum("workoutset__made"), attempted=Sum("workoutset__attempted")
        )
    }
    recent_dates = {}
    for athlete_id, day in finished.filter(date__gte=today - datetime.timedelta(days=366)).values_list("athlete", "date"):
        recent_dates.setdefault(athlete_id, []).append(day)

    rows = []
    for athlete in athletes:
        made, attempted = shots.get(athlete.id, (0, 0))
        if stat == "workouts":
            value = workouts_this_week.get(athlete.id, 0)
            label = f"{value} workout{'s' if value != 1 else ''}"
        elif stat == "streak":
            value = streak(recent_dates.get(athlete.id, []), today)
            label = f"{value} day{'s' if value != 1 else ''}"
        else:  # shooting
            if attempted < SHOOTING_MIN_ATTEMPTS:
                continue  # not enough shots to rank fairly
            value = shooting_pct(made, attempted)
            label = f"{value}% · {made}/{attempted}"
        rows.append({
            "athlete_id": athlete.id,
            "name": short_name(athlete.full_name),
            "initials": athlete.initials,
            "value": value,
            "label": label,
        })

    rows.sort(key=lambda row: (-row["value"], row["name"]))
    for position, row in enumerate(rows, start=1):
        row["rank"] = position
    return rows


@login_required
def leaderboard(request):
    athlete = get_object_or_404(Athlete, user=request.user)
    today = timezone.localdate()
    my_grade = grade_for(athlete.grad_year, today)

    try:
        grade = int(request.GET.get("grade", my_grade or 12))
    except ValueError:
        grade = 12
    if grade not in LEADERBOARD_GRADES:
        grade = 12
    stat = request.GET.get("stat", "workouts")
    if stat not in LEADERBOARD_STATS:
        stat = "workouts"

    opted_in = Athlete.objects.filter(on_leaderboard=True, grad_year=grad_year_for(grade, today)).count()
    is_open = opted_in >= LEADERBOARD_MIN_ATHLETES
    rows = leaderboard_rows(grade, stat, today) if is_open else []

    return render(request, "leaderboard.html", {
        "athlete": athlete,
        "active_tab": "record",
        "grades": LEADERBOARD_GRADES,
        "grade": grade,
        "stats": LEADERBOARD_STATS,
        "stat": stat,
        "stat_note": LEADERBOARD_STATS[stat][1],
        "rows": rows,
        "is_open": is_open,
        "opted_in": opted_in,
        "needed": LEADERBOARD_MIN_ATHLETES - opted_in,
        "my_grade": my_grade,
        "my_short_name": short_name(athlete.full_name),
        "shooting_min": SHOOTING_MIN_ATTEMPTS,
    })


@login_required
@require_POST
def leaderboard_toggle(request):
    """Switch "Show me on leaderboards" on or off. Only ever your own."""
    athlete = get_object_or_404(Athlete, user=request.user)
    athlete.on_leaderboard = request.POST.get("on") == "1"
    athlete.save(update_fields=["on_leaderboard"])
    # Go back to whichever page the switch was on.
    if request.POST.get("next") == "leaderboard":
        return redirect("leaderboard")
    return redirect("profile")
