"""Run with:  python manage.py test

Two groups:
  1. The stats functions — pure, so these run without a database, in milliseconds.
  2. The two-account test — athlete B must never see or change athlete A's data.
"""

import datetime

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from .models import Athlete, CoachMessage, Highlight, PublishConsent, Ranking, Workout, WorkoutSet
from .stats import (
    STALE_AFTER_DAYS, daily_series, feet_and_inches, grad_year_for, grade_for, is_stale, latest_change,
    minutes_between, pct_change, shooting_pct,
    shooting_totals, short_name, streak, weekly_series,
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
# Real password hashing is slow on purpose. Test passwords are throwaway, so tests
# use a fast hasher (as Django's docs recommend). The live site is unaffected.
FAST_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@override_settings(STORAGES=PLAIN_STATIC, PASSWORD_HASHERS=FAST_HASHERS)
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


@override_settings(STORAGES=PLAIN_STATIC, PASSWORD_HASHERS=FAST_HASHERS)
class ProfileTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user("me", password="unused-pw-123")
        self.other_user = User.objects.create_user("them", password="unused-pw-123")
        self.athlete = Athlete.objects.create(user=self.user, full_name="Me Myself", slug="me")
        self.other = Athlete.objects.create(user=self.other_user, full_name="Them", slug="them")
        self.client.force_login(self.user)

    def edit(self, **changes):
        data = {"full_name": "Me Myself", "position": "", "grad_year": "",
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


# ---------------------------------------------------------------------------
# 4. Leaderboards
# ---------------------------------------------------------------------------


class GradeAndStreakTests(SimpleTestCase):
    today = datetime.date(2026, 10, 2)  # 2026–27 school year

    def test_grade_from_class_year(self):
        self.assertEqual(grade_for(2027, self.today), 12)
        self.assertEqual(grade_for(2031, self.today), 8)
        self.assertEqual(grade_for(2032, self.today), 7)
        self.assertIsNone(grade_for(None, self.today))

    def test_school_year_rolls_over_in_july(self):
        self.assertEqual(grade_for(2027, datetime.date(2027, 6, 1)), 12)
        self.assertEqual(grade_for(2028, datetime.date(2027, 8, 1)), 12)

    def test_streak(self):
        day = datetime.timedelta(days=1)
        t = self.today
        self.assertEqual(streak([t, t - day, t - 2 * day], t), 3)
        self.assertEqual(streak([t - day, t - 2 * day], t), 2)  # nothing today yet: still alive
        self.assertEqual(streak([t - 3 * day], t), 0)
        self.assertEqual(streak([], t), 0)

    def test_short_name(self):
        self.assertEqual(short_name("Kaiden King"), "Kaiden K.")
        self.assertEqual(short_name("Mary Ann Smith"), "Mary S.")
        self.assertEqual(short_name("Cher"), "Cher")


@override_settings(STORAGES=PLAIN_STATIC, PASSWORD_HASHERS=FAST_HASHERS)
class LeaderboardTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.grade12 = grad_year_for(12, self.today)
        self.me = self.make("me", "Kaiden King", self.grade12, on=True, workouts=2)
        for i, count in enumerate([5, 3, 1]):
            self.make(f"p{i}", f"Player{i} Surname{i}", self.grade12, on=True, workouts=count)
        self.client.force_login(self.me.user)

    def make(self, username, name, grad_year, on, workouts=0, shots=(40, 50)):
        user = get_user_model().objects.create_user(username, password="unused-pw-123")
        athlete = Athlete.objects.create(user=user, full_name=name, slug=username,
                                         grad_year=grad_year, on_leaderboard=on)
        for i in range(workouts):
            w = Workout.objects.create(athlete=athlete, date=self.today - datetime.timedelta(days=i % 1),
                                       status="completed")
            WorkoutSet.objects.create(workout=w, drill_name="Shooting", made=shots[0], attempted=shots[1])
        return athlete

    def board(self, **params):
        response = self.client.get("/leaderboard/", params)
        self.assertEqual(response.status_code, 200)
        return response.context

    def test_ranked_by_workouts_this_week(self):
        rows = self.board(grade=12, stat="workouts")["rows"]
        self.assertEqual([r["value"] for r in rows], [5, 3, 2, 1])

    def test_short_names_only(self):
        page = self.client.get("/leaderboard/", {"grade": 12}).content.decode()
        self.assertIn("Kaiden K.", page)
        self.assertIn("Player0 S.", page)
        self.assertNotIn("Surname0", page)

    def test_opted_out_athlete_never_appears(self):
        self.make("hidden", "Hidden Person", self.grade12, on=False, workouts=9)
        names = [r["name"] for r in self.board(grade=12)["rows"]]
        self.assertNotIn("Hidden P.", names)

    def test_board_closed_under_four(self):
        Athlete.objects.filter(user__username="p2").update(on_leaderboard=False)
        context = self.board(grade=12)
        self.assertFalse(context["is_open"])
        self.assertEqual(context["rows"], [])

    def test_below_8th_grade_never_shown(self):
        seventh = grad_year_for(7, self.today)
        for i in range(5):
            self.make(f"young{i}", f"Young{i} Kid", seventh, on=True, workouts=3)
        context = self.board(grade=7)  # not a real board: falls back to 12th
        self.assertEqual(context["grade"], 12)
        names = [r["name"] for r in context["rows"]]
        self.assertFalse(any(n.startswith("Young") for n in names))

    def test_grades_are_separate_boards(self):
        eleventh = grad_year_for(11, self.today)
        for i in range(4):
            self.make(f"junior{i}", f"Junior{i} X", eleventh, on=True, workouts=1)
        names12 = [r["name"] for r in self.board(grade=12)["rows"]]
        names11 = [r["name"] for r in self.board(grade=11)["rows"]]
        self.assertFalse(any(n.startswith("Junior") for n in names12))
        self.assertTrue(all(n.startswith("Junior") for n in names11))

    def test_shooting_needs_50_shots(self):
        self.make("low", "Low Volume", self.grade12, on=True, workouts=1, shots=(5, 5))  # 100% on 5 shots
        names = [r["name"] for r in self.board(grade=12, stat="shooting")["rows"]]
        self.assertNotIn("Low V.", names)

    def test_toggle_only_changes_my_own(self):
        self.client.post("/leaderboard/toggle/", {"on": "0"})
        self.me.refresh_from_db()
        self.assertFalse(self.me.on_leaderboard)
        self.assertTrue(Athlete.objects.get(user__username="p0").on_leaderboard)

    def test_bad_query_values_dont_break_it(self):
        self.assertEqual(self.board(grade="abc", stat="nope")["stat"], "workouts")


# ---------------------------------------------------------------------------
# 5. Rankings from outlets
# ---------------------------------------------------------------------------


class StaleTests(SimpleTestCase):
    def test_stale_after_90_days(self):
        today = datetime.date(2026, 10, 4)
        self.assertFalse(is_stale(today - datetime.timedelta(days=90), today))
        self.assertTrue(is_stale(today - datetime.timedelta(days=91), today))


@override_settings(STORAGES=PLAIN_STATIC, PASSWORD_HASHERS=FAST_HASHERS)
class RankingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user("ranked", password="unused-pw-123")
        self.athlete = Athlete.objects.create(user=self.user, full_name="Ranked Player", slug="ranked")
        other_user = User.objects.create_user("rival", password="unused-pw-123")
        self.other = Athlete.objects.create(user=other_user, full_name="Other Player", slug="rival")
        self.client.force_login(self.user)
        self.today = timezone.localdate().isoformat()

    def add(self, **fields):
        data = {"outlet": "247sports", "stars": "4", "national_rank": "45", "position_rank": "",
                "state_rank": "", "checked_on": self.today, "url": "https://247sports.com/player/x-123/"}
        data.update(fields)
        return self.client.post("/profile/rankings/add/", data)

    def test_good_ranking_saved_and_shown(self):
        self.assertEqual(self.add().status_code, 302)
        page = self.client.get("/profile/").content.decode()
        self.assertIn("★★★★", page)
        self.assertIn("#45", page)
        self.assertIn("View on 247Sports", page)

    def test_link_must_be_on_the_chosen_outlet(self):
        self.add(url="https://www.on3.com/db/x/")                 # On3 link for a 247Sports ranking
        self.add(url="https://fake247sports.com/player/")          # lookalike domain
        self.add(url="http://247sports.com/player/")               # not https
        self.assertEqual(self.athlete.ranking_set.count(), 0)
        self.add(url="https://www.247sports.com/player/x-123/")    # www. is fine
        self.assertEqual(self.athlete.ranking_set.count(), 1)

    def test_needs_at_least_one_rank(self):
        self.add(stars="", national_rank="")
        self.assertEqual(self.athlete.ranking_set.count(), 0)

    def test_rejects_silly_values(self):
        self.add(stars="6")
        self.add(national_rank="0")
        self.add(checked_on=(timezone.localdate() + datetime.timedelta(days=3)).isoformat())
        self.assertEqual(self.athlete.ranking_set.count(), 0)

    def test_old_ranking_shows_stale_notice(self):
        old = (timezone.localdate() - datetime.timedelta(days=120)).isoformat()
        self.add(checked_on=old)
        self.assertIn("Checked over 3 months ago", self.client.get("/profile/").content.decode())

    def test_cannot_delete_someone_elses_ranking(self):
        theirs = Ranking.objects.create(athlete=self.other, outlet="espn", stars=5,
                                        url="https://espn.com/x", checked_on=timezone.localdate())
        self.assertEqual(self.client.post(f"/profile/rankings/{theirs.id}/delete/").status_code, 404)
        self.assertTrue(Ranking.objects.filter(id=theirs.id).exists())


# ---------------------------------------------------------------------------
# 6. Recruiting rankings board
# ---------------------------------------------------------------------------


@override_settings(STORAGES=PLAIN_STATIC, PASSWORD_HASHERS=FAST_HASHERS)
class RankingsBoardTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.grade12 = grad_year_for(12, self.today)
        self.me = self.make("me", "Kaiden King", national=45, stars=4)
        self.make("a", "Alpha Surname", national=12, stars=5)
        self.make("b", "Bravo Surname", national=None, stars=3, position=9)
        self.make("c", "Charlie Surname", national=200, stars=3)
        self.client.force_login(self.me.user)

    def make(self, username, name, national, stars, position=None, outlet="247sports",
             on=True, grad_year=None, checked_days_ago=0):
        user = get_user_model().objects.create_user(username, password="unused-pw-123")
        athlete = Athlete.objects.create(user=user, full_name=name, slug=username,
                                         grad_year=grad_year or self.grade12, on_leaderboard=on)
        Ranking.objects.create(athlete=athlete, outlet=outlet, stars=stars, national_rank=national,
                               position_rank=position, url="https://247sports.com/x",
                               checked_on=self.today - datetime.timedelta(days=checked_days_ago))
        return athlete

    def board(self, **params):
        response = self.client.get("/leaderboard/rankings/", params)
        self.assertEqual(response.status_code, 200)
        return response.context

    def test_ordered_by_national_rank_then_stars_only(self):
        rows = self.board(grade=12, outlet="247sports")["rows"]
        self.assertEqual([r["name"] for r in rows], ["Alpha S.", "Kaiden K.", "Charlie S.", "Bravo S."])

    def test_no_full_names_or_links_on_the_board(self):
        page = self.client.get("/leaderboard/rankings/", {"grade": 12}).content.decode()
        self.assertNotIn("Surname", page)
        self.assertNotIn("247sports.com/x", page)

    def test_outlets_are_separate_boards(self):
        self.assertFalse(self.board(grade=12, outlet="espn")["is_open"])

    def test_stale_rankings_left_off(self):
        Ranking.objects.filter(athlete__user__username="c").update(
            checked_on=self.today - datetime.timedelta(days=STALE_AFTER_DAYS + 1))
        self.assertFalse(self.board(grade=12)["is_open"])  # down to 3

    def test_opted_out_left_off(self):
        Athlete.objects.filter(user__username="a").update(on_leaderboard=False)
        self.assertFalse(self.board(grade=12)["is_open"])

    def test_below_8th_grade_never_shown(self):
        seventh = grad_year_for(7, self.today)
        for i in range(4):
            self.make(f"kid{i}", f"Kid{i} Young", national=5 + i, stars=5, grad_year=seventh)
        names = [r["name"] for r in self.board(grade=7)["rows"]]  # falls back to 12th
        self.assertFalse(any(n.startswith("Kid") for n in names))

    def test_training_board_unaffected(self):
        response = self.client.get("/leaderboard/")
        self.assertEqual(response.context["board"], "training")


# ---------------------------------------------------------------------------
# 7. Settings page and navigation
# ---------------------------------------------------------------------------


@override_settings(STORAGES=PLAIN_STATIC, PASSWORD_HASHERS=FAST_HASHERS)
class SettingsAndNavTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("navuser", password="unused-pw-123")
        self.athlete = Athlete.objects.create(user=self.user, full_name="Nav User", slug="nav")
        self.client.force_login(self.user)

    def test_settings_needs_login(self):
        self.client.logout()
        self.assertRedirects(self.client.get("/settings/"), "/login/?next=/settings/")

    def test_settings_has_log_out_and_leaderboard_switch(self):
        page = self.client.get("/settings/").content.decode()
        self.assertIn('action="/logout/"', page)
        self.assertIn('action="/leaderboard/toggle/"', page)

    def test_gear_in_header_and_rankings_tab_in_nav(self):
        page = self.client.get("/dashboard/").content.decode()
        self.assertIn('href="/settings/"', page)
        self.assertIn('href="/leaderboard/rankings/"', page)
        self.assertNotIn('action="/logout/"', page)  # log out lives in Settings now

    def test_switch_from_settings_returns_to_settings(self):
        response = self.client.post("/leaderboard/toggle/", {"on": "1", "next": "settings"})
        self.assertRedirects(response, "/settings/")
        self.athlete.refresh_from_db()
        self.assertTrue(self.athlete.on_leaderboard)


# ---------------------------------------------------------------------------
# 8. Dashboard charts
# ---------------------------------------------------------------------------


@override_settings(STORAGES=PLAIN_STATIC, PASSWORD_HASHERS=FAST_HASHERS)
class ChartTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("charter", password="unused-pw-123")
        self.athlete = Athlete.objects.create(user=self.user, full_name="Chart Person", slug="chart")
        self.client.force_login(self.user)
        self.today = timezone.localdate()

    def add(self, days_ago, made, attempted, status="completed"):
        w = Workout.objects.create(athlete=self.athlete, status=status,
                                   date=self.today - datetime.timedelta(days=days_ago))
        WorkoutSet.objects.create(workout=w, drill_name="Shots", made=made, attempted=attempted)
        WorkoutSet.objects.create(workout=w, drill_name="Slides")  # non-shooting drill

    def chart(self):
        return self.client.get("/dashboard/").context["chart_data"]

    def test_new_athlete_gets_friendly_message_not_empty_charts(self):
        response = self.client.get("/dashboard/")
        self.assertFalse(response.context["chart_data"]["has_data"])
        self.assertNotContains(response, 'id="shooting-chart"')
        self.assertContains(response, "after your first finished workout")

    def test_twelve_weeks_this_week_last(self):
        self.add(0, 8, 10)
        data = self.chart()["week"]
        self.assertEqual(len(data["labels"]), 12)
        self.assertEqual(data["workouts"][-1], 1)
        self.assertEqual(data["shooting"][-1], 80)

    def test_week_without_shots_is_a_gap(self):
        self.add(0, 0, 0)
        self.assertIsNone(self.chart()["week"]["shooting"][-1])

    def test_unfinished_workouts_not_counted(self):
        self.add(0, 8, 10, status="in_progress")
        self.assertFalse(self.chart()["has_data"])

    def test_only_my_workouts(self):
        other = get_user_model().objects.create_user("someone", password="unused-pw-123")
        theirs = Athlete.objects.create(user=other, full_name="Someone Else", slug="else")
        Workout.objects.create(athlete=theirs, status="completed", date=self.today)
        self.assertFalse(self.chart()["has_data"])

    def test_data_goes_in_through_json_script(self):
        self.add(0, 8, 10)
        self.assertContains(self.client.get("/dashboard/"), '<script id="chart-data" type="application/json">')

    def test_day_view_last_14_days(self):
        self.add(0, 8, 10)
        self.add(2, 6, 10)
        day = self.chart()["day"]
        self.assertEqual(len(day["labels"]), 14)
        self.assertEqual(day["shooting"][-3:], [60, None, 80])  # a gap for the day off
        self.assertEqual((day["latest"], day["change"]), (80, 20))

    def test_week_change_compares_with_last_week(self):
        self.add(0, 8, 10)   # this week: 80%
        self.add(7, 7, 10)   # last week: 70%
        week = self.chart()["week"]
        self.assertEqual((week["latest"], week["change"], week["compared_with"]), (80, 10, "last week"))


class DailyAndChangeTests(SimpleTestCase):
    today = datetime.date(2026, 10, 7)

    def test_daily_series(self):
        series = daily_series([(self.today, 8, 10), (self.today - datetime.timedelta(days=2), 6, 10)],
                              self.today, days=3)
        self.assertEqual([d["shooting_pct"] for d in series], [60, None, 80])
        self.assertEqual(series[-1]["day"], self.today)

    def test_latest_change_skips_gaps(self):
        self.assertEqual(latest_change([55, None, 58, None]), (58, 3))   # not a drop to 0

    def test_latest_change_down(self):
        self.assertEqual(latest_change([60, 56]), (56, -4))

    def test_nothing_to_compare(self):
        self.assertEqual(latest_change([None, 70]), (70, None))
        self.assertEqual(latest_change([None]), (None, None))


# ---------------------------------------------------------------------------
# 9. Deploy safety
# ---------------------------------------------------------------------------


class CollectStaticTests(SimpleTestCase):
    """Runs the same static-file step Render runs on every deploy.

    It once failed because Chart.js points at a source map that wasn't in the
    repo — Render's build stopped and kept the old site. This catches that locally.
    """

    def test_collectstatic_with_production_storage(self):
        import tempfile
        from django.core.management import call_command

        with tempfile.TemporaryDirectory() as folder, override_settings(
            STATIC_ROOT=folder,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
            },
        ):
            call_command("collectstatic", interactive=False, verbosity=0)


# ---------------------------------------------------------------------------
# 10. Public profile, consent, and hard rule #5
# ---------------------------------------------------------------------------


@override_settings(STORAGES=PLAIN_STATIC, PASSWORD_HASHERS=FAST_HASHERS)
class PublicProfileTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user("kid", password="unused-pw-123", email="kid-login@example.com")
        self.athlete = Athlete.objects.create(
            user=self.user, full_name="Kaiden King", slug="kaiden-king", position="Point guard",
            grad_year=2027, school="Churchill HS", gpa="3.60", height_in=74,
            coach_name="Coach Lee", coach_email="coach@school.example",
            contact_email="kaiden.own@example.com", show_contact_email=True,
        )
        Highlight.objects.create(athlete=self.athlete, title="Junior mix", url="https://youtu.be/abc")
        self.client.force_login(self.user)

    def publish(self, **fields):
        data = {"age": "under18", "parent_name": "Pat King", "parent_email": "pat@example.com", "agree": "on"}
        data.update(fields)
        return self.client.post("/profile/publish/", data)

    # --- Rule 5: private returns 404, never "this profile is private" ---

    def test_private_profile_is_404_for_strangers(self):
        self.client.logout()
        response = self.client.get("/a/kaiden-king/")
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, "private", status_code=404)

    def test_private_looks_exactly_like_missing(self):
        self.client.logout()
        private = self.client.get("/a/kaiden-king/")
        missing = self.client.get("/a/nobody-at-all/")
        self.assertEqual((private.status_code, missing.status_code), (404, 404))

    def test_private_is_404_even_for_another_logged_in_user(self):
        other = get_user_model().objects.create_user("other", password="unused-pw-123")
        self.client.force_login(other)
        self.assertEqual(self.client.get("/a/kaiden-king/").status_code, 404)

    # --- Consent ---

    def test_cannot_publish_without_agreeing(self):
        self.publish(agree="")
        self.athlete.refresh_from_db()
        self.assertFalse(self.athlete.is_public)

    def test_under_18_needs_parent_name_and_email(self):
        self.publish(parent_name="", parent_email="")
        self.athlete.refresh_from_db()
        self.assertFalse(self.athlete.is_public)

    def test_parent_email_cannot_be_the_athletes_own(self):
        self.publish(parent_email="Kaiden.Own@example.com")
        self.athlete.refresh_from_db()
        self.assertFalse(self.athlete.is_public)

    def test_publish_records_who_agreed_and_what_was_shown(self):
        self.publish()
        self.athlete.refresh_from_db()
        self.assertTrue(self.athlete.is_public)
        consent = PublishConsent.objects.get(athlete=self.athlete)
        self.assertEqual((consent.kind, consent.name, consent.email), ("parent", "Pat King", "pat@example.com"))
        self.assertIn("School: Churchill HS", consent.shown)

    def test_unpublish_makes_the_link_404_again(self):
        self.publish()
        self.client.post("/profile/unpublish/")
        self.client.logout()
        self.assertEqual(self.client.get("/a/kaiden-king/").status_code, 404)

    # --- What strangers see ---

    def test_public_page_works_logged_out(self):
        self.publish()
        self.client.logout()
        response = self.client.get("/a/kaiden-king/")
        self.assertContains(response, "Kaiden King")
        self.assertContains(response, "6′2″")
        self.assertContains(response, "Junior mix")
        self.assertContains(response, "mailto:coach@school.example")
        self.assertContains(response, '<meta name="robots" content="noindex, nofollow">')

    def test_never_shows_login_details(self):
        self.publish()
        self.client.logout()
        page = self.client.get("/a/kaiden-king/").content.decode()
        self.assertNotIn("kid-login@example.com", page)   # account email
        self.assertNotIn(">kid<", page)                     # username

    def test_switched_off_fields_are_hidden(self):
        Athlete.objects.filter(id=self.athlete.id).update(
            show_school=False, show_gpa=False, show_rankings_highlights=False, show_stats=False)
        self.publish()
        self.client.logout()
        page = self.client.get("/a/kaiden-king/").content.decode()
        for hidden in ["Churchill HS", "3.60", "Junior mix", "tile__l\">Workouts"]:
            self.assertNotIn(hidden, page)

    def test_own_email_hidden_until_confirmed_18_plus(self):
        self.publish()  # parent consent: athlete is under 18
        self.client.logout()
        self.assertNotContains(self.client.get("/a/kaiden-king/"), "kaiden.own@example.com")

    def test_own_email_shown_after_confirming_18_plus(self):
        self.publish(age="adult", parent_name="", parent_email="")
        self.assertEqual(PublishConsent.objects.get(athlete=self.athlete).kind, "self")
        self.client.logout()
        self.assertContains(self.client.get("/a/kaiden-king/"), "mailto:kaiden.own@example.com")

    def test_stale_rankings_left_off_the_public_page(self):
        Ranking.objects.create(athlete=self.athlete, outlet="espn", stars=4, national_rank=99,
                               url="https://espn.com/x",
                               checked_on=timezone.localdate() - datetime.timedelta(days=STALE_AFTER_DAYS + 5))
        self.publish()
        self.client.logout()
        self.assertNotContains(self.client.get("/a/kaiden-king/"), "#99")


# ---------------------------------------------------------------------------
# 11. Speed: database lookups per page (step 29)
# ---------------------------------------------------------------------------


@override_settings(STORAGES=PLAIN_STATIC, PASSWORD_HASHERS=FAST_HASHERS)
class QueryCountTests(TestCase):
    """A page's lookup count must not grow with the amount of data (no N+1)."""

    def setUp(self):
        self.user = get_user_model().objects.create_user("speedy", password="unused-pw-123")
        self.athlete = Athlete.objects.create(user=self.user, full_name="Speedy Player", slug="speedy",
                                              is_public=True)
        self.today = timezone.localdate()

    def add_data(self, count):
        for i in range(count):
            Ranking.objects.create(athlete=self.athlete, outlet="espn", stars=4, national_rank=i + 1,
                                   url="https://espn.com/x", checked_on=self.today)
            Highlight.objects.create(athlete=self.athlete, title=f"Clip {i}", url="https://youtu.be/x")
            w = Workout.objects.create(athlete=self.athlete, status="completed",
                                       date=self.today - datetime.timedelta(days=i))
            WorkoutSet.objects.create(workout=w, drill_name="Shots", made=5, attempted=10)

    def count(self, url, logged_in=False):
        if logged_in:
            self.client.force_login(self.user)
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.client.get(url).status_code, 200)
        return len(queries)

    def test_public_profile_lookups_dont_grow_with_data(self):
        self.add_data(1)
        few = self.count("/a/speedy/")
        self.add_data(10)
        self.assertEqual(self.count("/a/speedy/"), few)
        self.assertLessEqual(few, 9)

    def test_profile_and_dashboard_lookups_dont_grow_with_data(self):
        self.add_data(1)
        few = (self.count("/profile/", logged_in=True), self.count("/dashboard/", logged_in=True))
        self.add_data(10)
        many = (self.count("/profile/", logged_in=True), self.count("/dashboard/", logged_in=True))
        self.assertEqual(few, many)


# ---------------------------------------------------------------------------
# 12. AI coach (Claude is replaced by a stand-in: no key, no cost)
# ---------------------------------------------------------------------------

import json as _json
import os as _os
from types import SimpleNamespace
from unittest import mock as _mock

import anthropic
import httpx2

from . import coach


def fake_reply(text="Your shooting is up to 80% this week.", stop_reason="end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
    )


@override_settings(STORAGES=PLAIN_STATIC, PASSWORD_HASHERS=FAST_HASHERS,
                   COACH_QUESTIONS_PER_WEEK=3, COACH_QUESTIONS_PER_DAY=3, COACH_APP_WIDE_PER_DAY=200)
@_mock.patch.dict(_os.environ, {"ANTHROPIC_API_KEY": "test-key-not-real"})
class CoachTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("coached", password="unused-pw-123",
                                                         email="coached-login@example.com")
        self.athlete = Athlete.objects.create(
            user=self.user, full_name="Kaiden King", slug="kaiden-king", position="Point guard",
            school="Churchill HS", grad_year=2027, gpa="3.60", contact_email="own@example.com",
            parent_name="Pat King", parent_email="pat@example.com",
        )
        today = timezone.localdate()
        for days_ago, made in [(1, 8), (3, 7), (40, 5)]:
            w = Workout.objects.create(athlete=self.athlete, status="completed", duration_min=60,
                                       date=today - datetime.timedelta(days=days_ago), focus="Shooting")
            WorkoutSet.objects.create(workout=w, drill_name="Form shooting", made=made, attempted=10, completed=True)
        self.client.force_login(self.user)
        self.fake = _mock.MagicMock()
        self.fake.beta.messages.create.return_value = fake_reply()
        patcher = _mock.patch("athletes.coach._client", return_value=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def ask(self, question):
        return self.client.post("/coach/ask/", {"question": question}, HTTP_HX_REQUEST="true")

    def sent(self):
        """Everything that went to Claude on the last call, as one string."""
        kwargs = self.fake.beta.messages.create.call_args.kwargs
        return _json.dumps(kwargs, default=str)

    # --- Hard rule 6: only numbers and a position leave the server ---

    def test_context_has_no_identifying_details(self):
        context = coach.build_context(self.athlete, timezone.localdate())
        text = _json.dumps(context).lower()
        for private in ["kaiden", "king", "churchill", "3.60", "2027", "own@example.com",
                        "pat", "coached", "kaiden-king"]:
            self.assertNotIn(private, text)
        self.assertEqual(set(context), {"today", "position", "last_28_days", "previous_28_days", "recent_sessions"})

    def test_nothing_identifying_in_the_actual_request(self):
        self.ask("How is my shooting?")
        sent = self.sent().lower()
        for private in ["kaiden", "churchill", "own@example.com", "pat@example.com", "coached-login"]:
            self.assertNotIn(private, sent)

    def test_context_numbers_are_right(self):
        context = coach.build_context(self.athlete, timezone.localdate())
        self.assertEqual(context["last_28_days"]["sessions"], 2)
        self.assertEqual(context["last_28_days"]["shooting_pct"], 75)      # 15 of 20
        self.assertEqual(context["previous_28_days"]["shooting_pct"], 50)  # 5 of 10
        self.assertEqual(len(context["recent_sessions"]), 2)

    # --- Hard rule 4: refusals ---

    def test_hub_topics_never_reach_the_model(self):
        for question in ["Can I get NIL money?", "Will I have to sit out if I transfer?",
                         "Am I eligible for D1?", "How do I get a scholarship?",
                         "what do I do to get offers"]:
            with self.subTest(question=question):
                response = self.ask(question)
                self.assertContains(response, "Recruiting Hub")
        self.fake.beta.messages.create.assert_not_called()
        self.assertFalse(CoachMessage.objects.filter(counted=True).exists())  # none used up

    def test_ordinary_questions_are_not_caught(self):
        for question in ["How do I stay committed to training?", "Is my form shooting improving?"]:
            self.assertFalse(coach.is_hub_question(question))

    def test_system_prompt_carries_the_refusals(self):
        self.ask("How is my shooting?")
        system = self.fake.beta.messages.create.call_args.kwargs["system"]
        for rule in ["video", "biomechanical", "eligibility", "NIL", "scholarships",
                     "predict offers", "medical", "Recruiting Hub"]:
            self.assertIn(rule, system)

    # --- Caps ---

    def test_fourth_question_in_a_week_is_refused(self):
        for _ in range(3):
            self.ask("How is my shooting?")
        response = self.ask("And now?")
        self.assertContains(response, "used your 3 questions for this week")
        self.assertEqual(self.fake.beta.messages.create.call_count, 3)
        self.assertContains(response, "0 of 3 questions left")

    def test_app_wide_ceiling(self):
        with override_settings(COACH_APP_WIDE_PER_DAY=1):
            self.ask("How is my shooting?")
            self.assertContains(self.ask("Again?"), "very busy today")
        self.assertEqual(self.fake.beta.messages.create.call_count, 1)

    def test_request_is_capped_and_uses_the_model_setting(self):
        with override_settings(COACH_MODEL="claude-haiku-5-5"):
            self.ask("How is my shooting?")
        kwargs = self.fake.beta.messages.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "claude-haiku-5-5")
        self.assertLessEqual(kwargs["max_tokens"], 1500)
        self.assertEqual(kwargs["fallbacks"], "default")

    # --- Failure handling: visible, and doesn't use up a question ---

    def test_network_failure_shows_a_message_and_isnt_counted(self):
        self.fake.beta.messages.create.side_effect = anthropic.APIConnectionError(
            request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
        response = self.ask("How is my shooting?")
        self.assertContains(response, "answer right now")
        self.assertFalse(CoachMessage.objects.filter(counted=True).exists())

    def test_refusal_isnt_counted(self):
        self.fake.beta.messages.create.return_value = fake_reply(text="", stop_reason="refusal")
        self.assertContains(self.ask("How is my shooting?"), "answer that one")
        self.assertFalse(CoachMessage.objects.filter(counted=True).exists())

    def test_answer_is_saved_and_counted(self):
        response = self.ask("How is my shooting?")
        self.assertContains(response, "up to 80% this week")
        self.assertEqual(CoachMessage.objects.filter(athlete=self.athlete, counted=True).count(), 1)

    def test_not_configured_means_no_call(self):
        with _mock.patch.dict(_os.environ, {"ANTHROPIC_API_KEY": ""}):
            self.assertContains(self.ask("How is my shooting?"), "set up yet")
        self.fake.beta.messages.create.assert_not_called()

    # --- Two-account test ---

    def test_only_my_own_chat_is_shown(self):
        other_user = get_user_model().objects.create_user("other-chat", password="unused-pw-123")
        other = Athlete.objects.create(user=other_user, full_name="Other Person", slug="other-chat")
        CoachMessage.objects.create(athlete=other, role="athlete", content="SECRET question from someone else")
        self.assertNotContains(self.client.get("/coach/"), "SECRET question")

    def test_hub_answer_works_even_without_a_key(self):
        with _mock.patch.dict(_os.environ, {"ANTHROPIC_API_KEY": ""}):
            self.assertContains(self.ask("Can I get NIL money?"), "Recruiting Hub")
        self.fake.beta.messages.create.assert_not_called()


# ---------------------------------------------------------------------------
# 13. Coach: attached workouts, described workouts, planned workouts
# ---------------------------------------------------------------------------

GOOD_PLAN = {
    "focus": "Catch and shoot",
    "drills": [
        {"name": "Form shooting", "target": "50 makes", "tracks_makes": True},
        {"name": "Pound dribble", "target": "3 x 45s", "tracks_makes": False},
        {"name": "Mid-range pull-up", "target": "40 makes", "tracks_makes": True},
    ],
}


def fake_plan_reply(payload):
    text = payload if isinstance(payload, str) else _json.dumps(payload)
    return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])


class ValidatePlanTests(SimpleTestCase):
    def test_good_plan_passes(self):
        self.assertEqual(coach.validate_plan(GOOD_PLAN)["drills"][0]["name"], "Form shooting")

    def test_collapses_newlines_and_spaces(self):
        plan = _json.loads(_json.dumps(GOOD_PLAN))
        plan["drills"][0]["name"] = "Form\n   shooting"
        self.assertEqual(coach.validate_plan(plan)["drills"][0]["name"], "Form shooting")

    def test_rejects_bad_plans(self):
        too_few = {"focus": "x", "drills": GOOD_PLAN["drills"][:2]}
        too_many = {"focus": "x", "drills": GOOD_PLAN["drills"] * 3}
        long_name = {"focus": "x", "drills": [dict(d, name="x" * 61) for d in GOOD_PLAN["drills"]]}
        not_bool = {"focus": "x", "drills": [dict(d, tracks_makes="yes") for d in GOOD_PLAN["drills"]]}
        blank = {"focus": "  ", "drills": GOOD_PLAN["drills"]}
        for bad in [too_few, too_many, long_name, not_bool, blank, [], "plan", None]:
            with self.subTest(bad=str(bad)[:40]):
                with self.assertRaises(ValueError):
                    coach.validate_plan(bad)


@override_settings(STORAGES=PLAIN_STATIC, PASSWORD_HASHERS=FAST_HASHERS,
                   COACH_QUESTIONS_PER_WEEK=3, COACH_QUESTIONS_PER_DAY=3, COACH_APP_WIDE_PER_DAY=200)
@_mock.patch.dict(_os.environ, {"ANTHROPIC_API_KEY": "test-key-not-real"})
class CoachWorkoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("planner", password="unused-pw-123")
        self.athlete = Athlete.objects.create(user=self.user, full_name="Kaiden King", slug="planner",
                                              position="Point guard", school="Churchill HS")
        self.today = timezone.localdate()
        self.workout = Workout.objects.create(athlete=self.athlete, status="completed", duration_min=55,
                                              date=self.today - datetime.timedelta(days=2), focus="Guard · 60 min")
        WorkoutSet.objects.create(workout=self.workout, drill_name="Mid-range pull-up", target="40 makes",
                                  made=18, attempted=40, completed=True)
        WorkoutSet.objects.create(workout=self.workout, drill_name="Defensive slides", target="4 x 30s", completed=True)
        other_user = get_user_model().objects.create_user("someone", password="unused-pw-123")
        other = Athlete.objects.create(user=other_user, full_name="Someone Else", slug="someone")
        self.others = Workout.objects.create(athlete=other, status="completed", date=self.today)
        self.client.force_login(self.user)
        self.fake = _mock.MagicMock()
        self.fake.beta.messages.create.return_value = fake_reply()
        patcher = _mock.patch("athletes.coach._client", return_value=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def sent_kwargs(self):
        return self.fake.beta.messages.create.call_args.kwargs

    # --- 1. Ask about a logged workout ---

    def test_attached_workout_goes_in_the_context(self):
        response = self.client.post("/coach/ask/", {"question": "Why was my mid-range low?",
                                                    "workout_id": self.workout.id}, HTTP_HX_REQUEST="true")
        self.assertContains(response, "About your")
        content = self.sent_kwargs()["messages"][0]["content"]
        self.assertIn('"workout_in_question"', content)
        self.assertIn('"Mid-range pull-up"', content)
        self.assertIn('"shooting_pct": 45', content)  # 18 of 40
        self.assertNotIn("Kaiden", content)
        self.assertNotIn("Churchill", content)
        self.assertEqual(CoachMessage.objects.get(role="athlete").workout, self.workout)

    def test_cannot_attach_someone_elses_workout(self):
        self.assertEqual(self.client.get(f"/coach/?workout={self.others.id}").status_code, 404)
        response = self.client.post("/coach/ask/", {"question": "How was it?", "workout_id": self.others.id},
                                    HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 404)
        self.fake.beta.messages.create.assert_not_called()

    def test_bad_workout_id_is_404_not_a_crash(self):
        self.assertEqual(self.client.get("/coach/?workout=abc").status_code, 404)

    def test_summary_page_links_to_the_coach(self):
        self.assertContains(self.client.get(f"/workout/{self.workout.id}/summary/"),
                            f"/coach/?workout={self.workout.id}")

    # --- 2. Describe a workout in the chat ---

    def test_prompt_handles_described_workouts(self):
        self.client.post("/coach/ask/", {"question": "I shot 40/50 free throws yesterday, is that good?"},
                         HTTP_HX_REQUEST="true")
        system = self.sent_kwargs()["system"]
        self.assertIn("describe a workout they did but didn't log", system)
        self.assertIn("what they told you", system)

    # --- 3. Plan a workout ---

    def plan(self, **fields):
        data = {"minutes": "45", "focus": "Shooting", "note": ""}
        data.update(fields)
        return self.client.post("/coach/plan/", data, HTTP_HX_REQUEST="true")

    def test_plan_uses_structured_output_and_is_saved(self):
        self.fake.beta.messages.create.return_value = fake_plan_reply(GOOD_PLAN)
        response = self.plan()
        self.assertContains(response, "Catch and shoot")
        self.assertContains(response, "Start this workout")
        kwargs = self.sent_kwargs()
        self.assertEqual(kwargs["output_config"]["format"]["type"], "json_schema")
        self.assertNotIn("Kaiden", kwargs["messages"][0]["content"])
        answer = CoachMessage.objects.get(role="coach")
        self.assertEqual(answer.plan["focus"], "Catch and shoot")
        self.assertTrue(CoachMessage.objects.get(role="athlete").counted)

    def test_broken_plan_falls_back_to_the_standard_workout(self):
        for broken in ['{"focus": "x", "drills": []}', "not json at all", {"focus": "x"}]:
            with self.subTest(broken=str(broken)[:30]):
                CoachMessage.objects.all().delete()
                self.fake.beta.messages.create.return_value = fake_plan_reply(broken)
                with self.assertLogs("athletes.coach", level="WARNING"):
                    response = self.plan()
                self.assertContains(response, "standard workout")
                plan = CoachMessage.objects.get(role="coach").plan
                self.assertEqual(plan["focus"], "Guard · 60 min")
                self.assertFalse(CoachMessage.objects.get(role="athlete").counted)

    def test_plan_rejects_unknown_choices(self):
        self.assertEqual(self.plan(minutes="500").status_code, 400)
        self.assertEqual(self.plan(focus="Weights").status_code, 400)
        self.fake.beta.messages.create.assert_not_called()

    def test_plan_counts_toward_the_weekly_limit(self):
        self.fake.beta.messages.create.return_value = fake_plan_reply(GOOD_PLAN)
        for _ in range(3):
            self.plan()
        self.assertContains(self.plan(), "used your 3 questions")

    def test_start_a_planned_workout(self):
        self.fake.beta.messages.create.return_value = fake_plan_reply(GOOD_PLAN)
        self.plan()
        answer = CoachMessage.objects.get(role="coach")
        response = self.client.post(f"/coach/plan/{answer.id}/start/")
        workout = Workout.objects.get(athlete=self.athlete, date=self.today)
        self.assertRedirects(response, f"/workout/{workout.id}/")
        self.assertEqual(workout.focus, "Catch and shoot")
        drills = list(workout.workoutset_set.values_list("drill_name", "made"))
        self.assertEqual(drills, [("Form shooting", 0), ("Pound dribble", None), ("Mid-range pull-up", 0)])
        # Tapping Start again doesn't make a second workout.
        self.client.post(f"/coach/plan/{answer.id}/start/")
        self.assertEqual(Workout.objects.filter(athlete=self.athlete, date=self.today).count(), 1)

    def test_cannot_start_someone_elses_plan(self):
        other = Athlete.objects.get(slug="someone")
        theirs = CoachMessage.objects.create(athlete=other, role="coach", content="plan", plan=GOOD_PLAN)
        self.assertEqual(self.client.post(f"/coach/plan/{theirs.id}/start/").status_code, 404)
        self.assertFalse(Workout.objects.filter(athlete=self.athlete, date=self.today).exists())
