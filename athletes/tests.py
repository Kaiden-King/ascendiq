"""Run with:  python manage.py test

Two groups:
  1. The stats functions — pure, so these run without a database, in milliseconds.
  2. The two-account test — athlete B must never see or change athlete A's data.
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings

from .models import Athlete, Highlight, Workout, WorkoutSet
from .stats import (
    feet_and_inches, minutes_between, pct_change, shooting_pct, shooting_totals, weekly_series,
)

# ---------------------------------------------------------------------------
# 1. Stats
# ---------------------------------------------------------------------------


class ShootingPctTests(SimpleTestCase):
    def test_basic(self):
        self.assertEqual(shooting_pct(8, 10), 80)

    def test_rounds_to_whole_number(self):
        self.assertEqual(shooting_pct(1, 3), 33)  # 33.33…
        self.assertEqual(shooting_pct(2, 3), 67)  # 66.67…

    def test_no_attempts_is_none_not_zero(self):
        # "Didn't shoot" and "missed everything" are different things.
        self.assertIsNone(shooting_pct(0, 0))

    def test_missed_everything_is_zero(self):
        self.assertEqual(shooting_pct(0, 10), 0)


class ShootingTotalsTests(SimpleTestCase):
    def test_adds_up_drills(self):
        self.assertEqual(shooting_totals([(41, 50), (30, 40)]), (71, 90, 79))

    def test_no_drills(self):
        self.assertEqual(shooting_totals([]), (0, 0, None))


class PctChangeTests(SimpleTestCase):
    def test_up_and_down(self):
        self.assertEqual(pct_change(82, 76), 6)
        self.assertEqual(pct_change(70, 76), -6)

    def test_missing_either_side_is_none(self):
        self.assertIsNone(pct_change(None, 76))
        self.assertIsNone(pct_change(80, None))


class MinutesBetweenTests(SimpleTestCase):
    def test_rounds_to_nearest_minute(self):
        start = datetime.datetime(2026, 10, 1, 16, 0)
        self.assertEqual(minutes_between(start, start + datetime.timedelta(minutes=47, seconds=40)), 48)

    def test_never_less_than_one(self):
        start = datetime.datetime(2026, 10, 1, 16, 0)
        self.assertEqual(minutes_between(start, start + datetime.timedelta(seconds=5)), 1)


class WeeklySeriesTests(SimpleTestCase):
    today = datetime.date(2026, 10, 1)  # a Thursday

    def test_length_and_order(self):
        series = weekly_series([], self.today, weeks=12)
        self.assertEqual(len(series), 12)
        self.assertEqual(series[-1]["week_start"], datetime.date(2026, 9, 28))  # this week's Monday
        self.assertEqual(series[0]["week_start"], datetime.date(2026, 7, 13))   # 11 weeks earlier

    def test_groups_by_week_and_totals_shots(self):
        workouts = [
            (datetime.date(2026, 9, 24), 31, 50),  # Thu, last week
            (datetime.date(2026, 9, 26), 34, 50),  # Sat, last week
            (datetime.date(2026, 9, 29), 38, 50),  # Tue, this week
        ]
        last_week, this_week = weekly_series(workouts, self.today, weeks=2)
        self.assertEqual((last_week["workouts"], last_week["shooting_pct"]), (2, 65))
        self.assertEqual((this_week["workouts"], this_week["shooting_pct"]), (1, 76))

    def test_week_without_shots_is_none(self):
        # A ball-handling-only week must leave a gap on the chart, not plot 0%.
        (week,) = weekly_series([(datetime.date(2026, 9, 29), 0, 0)], self.today, weeks=1)
        self.assertEqual(week["workouts"], 1)
        self.assertIsNone(week["shooting_pct"])

    def test_ignores_workouts_outside_the_window(self):
        (week,) = weekly_series([(datetime.date(2025, 1, 1), 9, 10)], self.today, weeks=1)
        self.assertEqual(week["workouts"], 0)


# ---------------------------------------------------------------------------
# 2. The two-account test
# ---------------------------------------------------------------------------


# Tests always run with DEBUG off, which switches on the production static-file
# setting (needs `collectstatic` first). Pages in tests use the plain one instead.
PLAIN_STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=PLAIN_STATIC)
class TwoAccountTests(TestCase):
    """Athlete B, logged in, tries every workout URL that belongs to athlete A.

    Every attempt must be "not found" (404) — the same answer as for an ID that
    doesn't exist, so B can't even tell A's workout is there — and A's data
    must be unchanged afterwards.
    """

    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user("owner", password="unused-pw-123")
        self.other = User.objects.create_user("other", password="unused-pw-123")
        owner_athlete = Athlete.objects.create(user=self.owner, full_name="Owner A", slug="owner-a")
        Athlete.objects.create(user=self.other, full_name="Other B", slug="other-b")

        self.workout = Workout.objects.create(
            athlete=owner_athlete, date=datetime.date.today(), started_at=None
        )
        self.drill = WorkoutSet.objects.create(workout=self.workout, drill_name="Slides")
        self.shooting = WorkoutSet.objects.create(
            workout=self.workout, drill_name="Form shooting", made=8, attempted=10
        )
        self.client.force_login(self.other)

    def assert_not_found(self, response):
        self.assertEqual(response.status_code, 404)

    def test_cannot_open_workout(self):
        self.assert_not_found(self.client.get(f"/workout/{self.workout.id}/"))

    def test_cannot_open_summary(self):
        self.assert_not_found(self.client.get(f"/workout/{self.workout.id}/summary/"))

    def test_cannot_tick_drill(self):
        self.assert_not_found(self.client.post(f"/workout/set/{self.drill.id}/toggle/"))
        self.drill.refresh_from_db()
        self.assertFalse(self.drill.completed)

    def test_cannot_change_score(self):
        response = self.client.post(f"/workout/set/{self.shooting.id}/score/", {"made": "0", "attempted": "99"})
        self.assert_not_found(response)
        self.shooting.refresh_from_db()
        self.assertEqual((self.shooting.made, self.shooting.attempted), (8, 10))

    def test_cannot_count_shot(self):
        self.assert_not_found(self.client.post(f"/workout/set/{self.shooting.id}/shot/", {"result": "make"}))
        self.shooting.refresh_from_db()
        self.assertEqual((self.shooting.made, self.shooting.attempted), (8, 10))

    def test_cannot_finish(self):
        self.assert_not_found(self.client.post(f"/workout/{self.workout.id}/finish/"))
        self.workout.refresh_from_db()
        self.assertEqual(self.workout.status, "in_progress")

    def test_history_never_shows_others(self):
        response = self.client.get("/history/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page"].object_list), 0)

    def test_owner_still_can(self):
        # Guards against a "fix" that blocks everyone: A must still reach A's workout.
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(f"/workout/{self.workout.id}/").status_code, 200)


# ---------------------------------------------------------------------------
# 3. My profile
# ---------------------------------------------------------------------------


class FeetAndInchesTests(SimpleTestCase):
    def test_formats(self):
        self.assertEqual(feet_and_inches(74), "6′2″")
        self.assertEqual(feet_and_inches(72), "6′0″")

    def test_blank_stays_blank(self):
        self.assertIsNone(feet_and_inches(None))


@override_settings(STORAGES=PLAIN_STATIC)
class ProfileTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user("me", password="unused-pw-123")
        self.other_user = User.objects.create_user("them", password="unused-pw-123")
        self.athlete = Athlete.objects.create(user=self.user, full_name="Me Myself", slug="me")
        self.other = Athlete.objects.create(user=self.other_user, full_name="Them", slug="them")
        self.client.force_login(self.user)

    def edit(self, **changes):
        data = {"full_name": "Me Myself", "archetype": "", "position": "", "grad_year": "",
                "school": "", "weight_lb": "", "gpa": "", "height_ft": "", "height_extra": "",
                "wingspan_ft": "", "wingspan_extra": ""}
        data.update(changes)
        return self.client.post("/profile/edit/", data)

    def test_logged_out_goes_to_login(self):
        self.client.logout()
        self.assertRedirects(self.client.get("/profile/"), "/login/?next=/profile/")

    def test_shows_only_my_profile(self):
        page = self.client.get("/profile/").content.decode()
        self.assertIn("Me Myself", page)
        self.assertNotIn("Them", page)

    def test_feet_and_inches_saved_as_inches(self):
        self.edit(height_ft="6", height_extra="2", wingspan_ft="6", wingspan_extra="6", weight_lb="175")
        self.athlete.refresh_from_db()
        self.assertEqual((self.athlete.height_in, self.athlete.wingspan_in, self.athlete.weight_lb), (74, 78, 175))

    def test_inches_without_feet_is_an_error(self):
        response = self.edit(height_extra="2")
        self.assertEqual(response.status_code, 200)  # form shown again, nothing saved
        self.athlete.refresh_from_db()
        self.assertIsNone(self.athlete.height_in)

    def test_silly_numbers_rejected(self):
        self.edit(weight_lb="2000", gpa="9", grad_year="1990")
        self.athlete.refresh_from_db()
        self.assertEqual((self.athlete.weight_lb, self.athlete.gpa, self.athlete.grad_year), (None, None, None))

    def test_highlight_links_only_from_allowed_sites(self):
        self.client.post("/profile/highlights/add/", {"title": "Mix", "url": "https://youtu.be/abc123"})
        self.client.post("/profile/highlights/add/", {"title": "Bad", "url": "https://evil.example.com/x"})
        self.client.post("/profile/highlights/add/", {"title": "Plain http", "url": "http://youtube.com/watch?v=1"})
        self.assertEqual(list(self.athlete.highlight_set.values_list("title", flat=True)), ["Mix"])

    def test_highlight_limit(self):
        for i in range(9):
            self.client.post("/profile/highlights/add/", {"title": f"Clip {i}", "url": "https://youtu.be/x"})
        self.assertEqual(self.athlete.highlight_set.count(), 8)

    def test_cannot_delete_someone_elses_highlight(self):
        theirs = Highlight.objects.create(athlete=self.other, title="Theirs", url="https://youtu.be/t")
        response = self.client.post(f"/profile/highlights/{theirs.id}/delete/")
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Highlight.objects.filter(id=theirs.id).exists())

    def test_can_delete_my_highlight(self):
        mine = Highlight.objects.create(athlete=self.athlete, title="Mine", url="https://youtu.be/m")
        self.client.post(f"/profile/highlights/{mine.id}/delete/")
        self.assertFalse(Highlight.objects.filter(id=mine.id).exists())
