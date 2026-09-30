"""Delete every test user made by seed_test_users. Run before launch.

    python manage.py remove_test_users

Only accounts with an @example.com email are removed. Their athlete
profile, workouts and drills go with them (on_delete=CASCADE).
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from .seed_test_users import TEST_EMAIL_DOMAIN


class Command(BaseCommand):
    help = "Delete all @example.com test users and everything they logged."

    def handle(self, *args, **options):
        test_users = get_user_model().objects.filter(email__endswith=TEST_EMAIL_DOMAIN)

        if not test_users.exists():
            self.stdout.write("No test users found. Nothing to remove.")
            return

        self.stdout.write("These accounts will be deleted, with all their workouts:")
        for user in test_users:
            self.stdout.write(f"  {user.username}  ({user.email})")

        if input("Type yes to delete them: ").strip().lower() != "yes":
            self.stdout.write("Cancelled. Nothing was deleted.")
            return

        count = test_users.count()
        test_users.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {count} test users."))
