"""Create 3 test athletes with recent workouts, for building and demos.

    python manage.py seed_test_users            create any that are missing
    python manage.py seed_test_users --refresh  also rebuild their workouts around today

Every test user gets an @example.com email. That address is how
remove_test_users finds them again, so real accounts are never touched.
The password is typed in when the command runs — it's never stored in code.
All three are Class of 2027 and on the leaderboard, so with one real
12th grader the 12th grade board reaches the 4 it needs to open.
"""

import datetime
from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from athletes.models import Athlete, Workout, WorkoutSet

TEST_EMAIL_DOMAIN = "@example.com"

# workouts: (days ago, made, attempted) — invented numbers, test data only.
# Different records so the boards actually rank them.
TEST_ATHLETES = [
    {
        "username": "test_guard", "full_name": "Guard Tester", "position": "Point guard",
        "workouts": [(0, 41, 50), (1, 38, 50), (2, 36, 50), (3, 40, 50), (4, 35, 50)],  # 5-day streak
    },
    {
        "username": "test_wing", "full_name": "Wing Tester", "position": "Small forward",
        "workouts": [(1, 44, 50), (2, 43, 50), (6, 42, 50)],  # best shooter
    },
    {
        "username": "test_big", "full_name": "Big Tester", "position": "Center",
        "workouts": [(3, 22, 40), (9, 25, 40)],  # fewer sessions
    },
]
TEST_GRAD_YEAR = 2027


class Command(BaseCommand):
    help = "Create 3 test athletes (@example.com) on the 12th grade leaderboard."

    def add_arguments(self, parser):
        parser.add_argument(
            "--refresh", action="store_true",
            help="Delete the test athletes' workouts and rebuild them around today.",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        missing = [a for a in TEST_ATHLETES if not User.objects.filter(username=a["username"]).exists()]

        password = None
        if missing:
            password = getpass("Password for the new test users: ")
            if password != getpass("Same password again: "):
                raise CommandError("Passwords didn't match. Nothing was created.")
            try:
                validate_password(password)
            except ValidationError as error:
                raise CommandError(" ".join(error.messages))

        today = timezone.localdate()
        for info in TEST_ATHLETES:
            with transaction.atomic():
                user = User.objects.filter(username=info["username"]).first()
                created = user is None
                if created:
                    user = User.objects.create_user(
                        username=info["username"],
                        email=info["username"] + TEST_EMAIL_DOMAIN,
                        password=password,
                    )
                elif not user.email.endswith(TEST_EMAIL_DOMAIN):
                    # Safety: never touch a real account that happens to share a test username.
                    self.stdout.write(self.style.WARNING(f"{info['username']} isn't a test account, skipped"))
                    continue

                athlete, _ = Athlete.objects.update_or_create(
                    user=user,
                    defaults={
                        "full_name": info["full_name"],
                        "position": info["position"],
                        "grad_year": TEST_GRAD_YEAR,
                        "on_leaderboard": True,
                    },
                    create_defaults={
                        "full_name": info["full_name"],
                        "slug": info["username"].replace("_", "-"),
                        "position": info["position"],
                        "grad_year": TEST_GRAD_YEAR,
                        "on_leaderboard": True,
                    },
                )

                if created or options["refresh"]:
                    athlete.workout_set.all().delete()
                    for days_ago, made, attempted in info["workouts"]:
                        self.add_workout(athlete, today - datetime.timedelta(days=days_ago), made, attempted)

            action = "Created" if created else ("Refreshed" if options["refresh"] else "Updated")
            self.stdout.write(self.style.SUCCESS(f"{action} {info['username']} ({info['full_name']})"))

    def add_workout(self, athlete, day, made, attempted):
        workout = Workout.objects.create(
            athlete=athlete, date=day, focus="Guard · 60 min", duration_min=60, status="completed",
        )
        WorkoutSet.objects.create(
            workout=workout, drill_name="Form shooting 10ft", target="50 makes",
            completed=True, made=made, attempted=attempted,
        )
        WorkoutSet.objects.create(
            workout=workout, drill_name="Between-the-legs dribble", target="3 × 45s", completed=True,
        )
