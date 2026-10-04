"""Create 7 fake test athletes with measurements and recent workouts, for demos.

    python manage.py seed_test_users            create any that are missing
    python manage.py seed_test_users --refresh  also rebuild their workouts and sample rankings

Every test user gets an @example.com email. That address is how
remove_test_users finds them again, so real accounts are never touched.
The password is typed in when the command runs — it's never stored in code.
Three are Class of 2027 (12th) and four Class of 2028 (11th), all on the
leaderboard: the 11th grade board opens on its own; 12th opens with one real athlete.
"""

import datetime
from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from athletes.forms import OUTLET_DOMAINS
from athletes.models import Athlete, Ranking, Workout, WorkoutSet

TEST_EMAIL_DOMAIN = "@example.com"

# All invented, test data only. Measurements in inches / lb.
# workouts: (days ago, made, attempted). Different records so the boards rank them.
# Four in each of two grades, counting the real athlete in 12th, so both boards open.
TEST_SCHOOL = "Test High School"
TEST_ATHLETES = [
    # --- Class of 2027 (12th grade) ---
    {
        "username": "test_guard", "full_name": "Guard Tester", "position": "Point guard", "grad_year": 2027,
        "height_in": 73, "weight_lb": 172, "wingspan_in": 76,
        "workouts": [(0, 41, 50), (1, 38, 50), (2, 36, 50), (3, 40, 50), (4, 35, 50)],  # 5-day streak
        "rankings": [("247sports", 4, 88, 14), ("espn", 4, 95, None)],
    },
    {
        "username": "test_wing", "full_name": "Wing Tester", "position": "Small forward", "grad_year": 2027,
        "height_in": 78, "weight_lb": 195, "wingspan_in": 82,
        "workouts": [(1, 44, 50), (2, 43, 50), (6, 42, 50)],  # best shooter
        "rankings": [("247sports", 4, 61, 9), ("on3", 4, 70, 11)],
    },
    {
        "username": "test_big", "full_name": "Big Tester", "position": "Center", "grad_year": 2027,
        "height_in": 82, "weight_lb": 235, "wingspan_in": 86,
        "workouts": [(3, 22, 40), (9, 25, 40)],  # fewer sessions
        "rankings": [("247sports", 3, None, 22), ("espn", 4, 120, None)],
    },
    # --- Class of 2028 (11th grade) ---
    {
        "username": "test_swing", "full_name": "Swing Tester", "position": "Shooting guard", "grad_year": 2028,
        "height_in": 75, "weight_lb": 180, "wingspan_in": 79,
        "workouts": [(0, 39, 50), (1, 41, 50), (2, 37, 50), (5, 40, 50)],
        "rankings": [("247sports", 4, 42, 7), ("rivals", 4, 55, None)],
    },
    {
        "username": "test_combo", "full_name": "Combo Tester", "position": "Point guard", "grad_year": 2028,
        "height_in": 71, "weight_lb": 165, "wingspan_in": 73,
        "workouts": [(0, 33, 50), (1, 35, 50), (2, 31, 50), (3, 36, 50), (4, 34, 50), (5, 30, 50)],  # 6-day streak
        "rankings": [("247sports", 3, 140, 25)],
    },
    {
        "username": "test_stretch", "full_name": "Stretch Tester", "position": "Power forward", "grad_year": 2028,
        "height_in": 80, "weight_lb": 210, "wingspan_in": 83,
        "workouts": [(2, 46, 60), (4, 44, 60)],  # few sessions, sharp shooter
        "rankings": [("247sports", 5, 18, 4), ("espn", 5, 22, None), ("on3", 4, 30, None)],
    },
    {
        "username": "test_post", "full_name": "Post Tester", "position": "Center", "grad_year": 2028,
        "height_in": 81, "weight_lb": 240, "wingspan_in": 84,
        "workouts": [(1, 28, 45), (3, 26, 45), (8, 30, 45)],
        "rankings": [("247sports", 3, None, 31)],
    },
]
PROFILE_FIELDS = ["full_name", "position", "grad_year", "height_in", "weight_lb", "wingspan_in"]


class Command(BaseCommand):
    help = "Create 7 fake test athletes (@example.com) across the 11th and 12th grade boards."

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

                profile = {field: info[field] for field in PROFILE_FIELDS}
                profile.update(school=TEST_SCHOOL, on_leaderboard=True)
                athlete, _ = Athlete.objects.update_or_create(
                    user=user,
                    defaults=profile,
                    create_defaults={**profile, "slug": info["username"].replace("_", "-")},
                )

                if created or options["refresh"]:
                    athlete.workout_set.all().delete()
                    for days_ago, made, attempted in info["workouts"]:
                        self.add_workout(athlete, today - datetime.timedelta(days=days_ago), made, attempted)
                    # Sample rankings: invented numbers, linked to the outlet's home page
                    # (there's no real player page for a fake athlete).
                    athlete.ranking_set.all().delete()
                    for outlet, stars, national, position in info["rankings"]:
                        Ranking.objects.create(
                            athlete=athlete, outlet=outlet, stars=stars, national_rank=national,
                            position_rank=position, url=f"https://{OUTLET_DOMAINS[outlet]}/", checked_on=today,
                        )

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
