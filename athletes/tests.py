"""Run with:  python manage.py test

Two groups:
  1. The stats functions — pure, so these run without a database, in milliseconds.
  2. The two-account test — athlete B must never see or change athlete A's data.
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from .models import Athlete, Highlight, Ranking, Workout, WorkoutSet
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
