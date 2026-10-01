"""Today's drills, as a plain list.

The AI workout generator replaces this in week 4. The screens read workouts
from the database, never from this file, so swapping it out won't touch them.
"""

from django.db import transaction
from django.utils import timezone

from .models import Athlete, Workout, WorkoutSet

GUARD_60_FOCUS = "Guard · 60 min"

# (drill name, target, tracks makes and attempts?)
GUARD_60 = [
    ("Between-the-legs dribble", "3 × 45s", False),
    ("Figure-8 drill", "3 × 30s", False),
    ("Form shooting 10ft", "50 makes", True),
    ("Mid-range pull-up", "40 makes", True),
    ("Defensive slides", "4 × 30s", False),
]


def todays_workout(athlete):
    """The athlete's workout for today, or None if they haven't started one."""
    return Workout.objects.filter(athlete=athlete, date=timezone.localdate()).first()


def create_todays_workout(athlete):
    """Start today's workout from the template. Safe to call twice.

    Locking the athlete's row means a double-tap on Start waits for the first
    tap to finish, finds that workout, and returns it instead of making a second.
    """
    with transaction.atomic():
        Athlete.objects.select_for_update().get(pk=athlete.pk)

        existing = todays_workout(athlete)
        if existing:
            return existing

        workout = Workout.objects.create(
            athlete=athlete,
            date=timezone.localdate(),
            focus=GUARD_60_FOCUS,
            started_at=timezone.now(),
        )
        for name, target, tracks_shots in GUARD_60:
            WorkoutSet.objects.create(
                workout=workout,
                drill_name=name,
                target=target,
                # None means "not a shooting drill" — the screen hides the score boxes
                made=0 if tracks_shots else None,
                attempted=0 if tracks_shots else None,
            )
        return workout
