"""Create 3 test athletes with a few workouts each.

    python manage.py seed_test_users

Every test user gets an @example.com email. That address is how
remove_test_users finds them again, so real accounts are never touched.
The password is typed in when the command runs — it's never stored in code.
"""

import datetime
from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from athletes.models import Athlete, Workout, WorkoutSet

TEST_EMAIL_DOMAIN = "@example.com"

TEST_ATHLETES = [
    {"username": "test_guard", "full_name": "Test Guard One", "position": "Guard", "grad_year": 2027},
    {"username": "test_wing", "full_name": "Test Wing Two", "position": "Wing", "grad_year": 2028},
    {"username": "test_big", "full_name": "Test Big Three", "position": "Center", "grad_year": 2027},
]

# (days ago, focus, shots made, shots attempted) — invented numbers, test data only
TEST_WORKOUTS = [
    (6, "Shooting", 31, 50),
    (4, "Ball handling & shooting", 34, 50),
    (1, "Shooting", 38, 50),
]


class Command(BaseCommand):
    help = "Create 3 test athletes (@example.com) with sample workouts."

    def handle(self, *args, **options):
        password = getpass("Password for all 3 test users: ")
        if password != getpass("Same password again: "):
            raise CommandError("Passwords didn't match. Nothing was created.")
        try:
            validate_password(password)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages))

        User = get_user_model()
        today = datetime.date.today()

        for info in TEST_ATHLETES:
            if User.objects.filter(username=info["username"]).exists():
                self.stdout.write(f"{info['username']} already exists, skipped")
                continue

            with transaction.atomic():
                user = User.objects.create_user(
                    username=info["username"],
                    email=info["username"] + TEST_EMAIL_DOMAIN,
                    password=password,
                )
                athlete = Athlete.objects.create(
                    user=user,
                    full_name=info["full_name"],
                    slug=info["username"].replace("_", "-"),
                    position=info["position"],
                    grad_year=info["grad_year"],
                )
                for days_ago, focus, made, attempted in TEST_WORKOUTS:
                    workout = Workout.objects.create(
                        athlete=athlete,
                        date=today - datetime.timedelta(days=days_ago),
                        focus=focus,
                        duration_min=60,
                        status="complete",
                    )
                    WorkoutSet.objects.create(
                        workout=workout, drill_name="Form shooting",
                        completed=True, made=made, attempted=attempted,
                    )
                    WorkoutSet.objects.create(
                        workout=workout, drill_name="Two-ball dribbling",
                        target="3 x 60s", completed=True,
                    )

            self.stdout.write(self.style.SUCCESS(f"Created {info['username']} ({info['full_name']})"))
