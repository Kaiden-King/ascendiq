from django.conf import settings
from django.db import models

from .stats import feet_and_inches, shooting_pct


class Athlete(models.Model):
    """One per login account. Everything else hangs off this."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)  # public profile address: /a/<slug>/
    school = models.CharField(max_length=120, blank=True)
    grad_year = models.IntegerField(null=True, blank=True)
    position = models.CharField(max_length=40, blank=True)
    height_in = models.IntegerField(null=True, blank=True)
    weight_lb = models.IntegerField(null=True, blank=True)
    wingspan_in = models.IntegerField(null=True, blank=True)
    gpa = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    is_public = models.BooleanField(default=False)  # opt in, never out
    published_at = models.DateTimeField(null=True, blank=True)

    # --- Public profile: contact routes (each optional, each with its own switch) ---
    contact_email = models.EmailField(blank=True)   # the athlete's own; shown only if they've confirmed 18+
    parent_name = models.CharField(max_length=120, blank=True)
    parent_email = models.EmailField(blank=True)
    coach_name = models.CharField(max_length=120, blank=True)
    coach_email = models.EmailField(blank=True)

    # --- Public profile: what strangers can see (name, position, class, measurements always) ---
    show_rankings_highlights = models.BooleanField(default=True)
    show_stats = models.BooleanField(default=True)
    show_school = models.BooleanField(default=True)
    show_gpa = models.BooleanField(default=True)
    show_contact_email = models.BooleanField(default=False)
    show_parent_email = models.BooleanField(default=True)
    show_coach_email = models.BooleanField(default=True)
    on_leaderboard = models.BooleanField(default=False)  # opt in: "Kaiden K." shown to others in the same grade
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name

    @property
    def confirmed_adult(self):
        """True if the latest publish consent was the athlete agreeing as 18+."""
        latest = self.publishconsent_set.first()
        return latest is not None and latest.kind == "self"

    @property
    def height_display(self):
        return feet_and_inches(self.height_in)

    @property
    def wingspan_display(self):
        return feet_and_inches(self.wingspan_in)

    @property
    def initials(self):
        """'Kaiden King' -> 'KK'. Shown in the header instead of a photo."""
        parts = self.full_name.split()
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][0].upper()
        return (parts[0][0] + parts[-1][0]).upper()


class Workout(models.Model):
    """One training session on one day."""

    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE)
    date = models.DateField()
    focus = models.CharField(max_length=60, blank=True)
    duration_min = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, default="in_progress")
    started_at = models.DateTimeField(null=True, blank=True)  # set on Start; finish uses it for duration

    class Meta:
        ordering = ["-date"]  # newest first

    def __str__(self):
        return f"{self.athlete} · {self.date} · {self.focus or 'workout'}"


class WorkoutSet(models.Model):
    """One drill inside a workout. made/attempted only for shooting drills."""

    workout = models.ForeignKey(Workout, on_delete=models.CASCADE)
    drill_name = models.CharField(max_length=80)
    target = models.CharField(max_length=40, blank=True)
    completed = models.BooleanField(default=False)
    made = models.IntegerField(null=True, blank=True)
    attempted = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["id"]  # drills stay in the order the workout created them

    def __str__(self):
        return self.drill_name

    @property
    def pct(self):
        """Shooting % for this drill, or None. The maths lives in stats.py."""
        if self.made is None:
            return None
        return shooting_pct(self.made, self.attempted)


class Measurement(models.Model):
    """A tested number on a date: vertical, sprint time, and so on.

    `metric` is the multi-sport seam — a 40-yard dash is just another row,
    so football and soccer fit later without a redesign.
    """

    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE)
    date = models.DateField()
    metric = models.CharField(max_length=40)  # vertical_in, sprint_3_4 …
    value = models.DecimalField(max_digits=6, decimal_places=2)
    unit = models.CharField(max_length=12)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.athlete} · {self.metric} {self.value}{self.unit}"


class Highlight(models.Model):
    """A link to a highlight video on YouTube, Hudl or Vimeo. No uploads (yet)."""

    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE)
    title = models.CharField(max_length=80)
    url = models.URLField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]  # newest first

    def __str__(self):
        return self.title


class Ranking(models.Model):
    """A ranking an outlet has given this athlete, with the link to prove it.

    Entered by the athlete, never copied from the outlet's site: the link
    is the source, and checked_on is when they last confirmed it.
    """

    OUTLETS = [
        ("espn", "ESPN"),
        ("247sports", "247Sports"),
        ("on3", "On3"),
        ("rivals", "Rivals"),
        ("maxpreps", "MaxPreps"),
        ("usatoday", "USA Today"),
    ]

    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE)
    outlet = models.CharField(max_length=20, choices=OUTLETS)
    stars = models.PositiveSmallIntegerField(null=True, blank=True)
    national_rank = models.PositiveIntegerField(null=True, blank=True)
    position_rank = models.PositiveIntegerField(null=True, blank=True)
    state_rank = models.PositiveIntegerField(null=True, blank=True)
    url = models.URLField(max_length=300)
    checked_on = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["outlet", "-checked_on"]

    def __str__(self):
        return f"{self.get_outlet_display()} · {self.athlete}"

    @property
    def stars_display(self):
        """4 -> '★★★★'"""
        return "★" * (self.stars or 0)


class PublishConsent(models.Model):
    """A record of who agreed, and when, each time a profile was made public.

    Kept even if the profile goes private again — it's the audit trail.
    `shown` is a plain-text list of exactly what was visible at that moment.
    """

    KINDS = [
        ("parent", "Parent or guardian"),
        ("self", "Athlete, 18 or older"),
    ]

    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE)
    kind = models.CharField(max_length=10, choices=KINDS)
    name = models.CharField(max_length=120)       # the parent's name, or the athlete's own
    email = models.EmailField(blank=True)         # the parent's email (blank for self)
    shown = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.athlete} · {self.get_kind_display()} · {self.created_at:%Y-%m-%d}"


class CoachMessage(models.Model):
    """One message in an athlete's chat with the AI coach."""

    ROLES = [("athlete", "Athlete"), ("coach", "Coach")]

    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLES)
    content = models.TextField()
    # A question counts toward the weekly allowance only if it reached the AI
    # and got an answer. Hub redirects and failed calls don't use one up.
    counted = models.BooleanField(default=False)
    # The logged workout this question is about, if one was attached.
    workout = models.ForeignKey("Workout", null=True, blank=True, on_delete=models.SET_NULL)
    # A workout the coach planned: {"focus": "...", "drills": [{"name", "target", "tracks_makes"}]}.
    # Only ever saved after validate_plan() has checked it.
    plan = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.athlete} · {self.role} · {self.created_at:%Y-%m-%d %H:%M}"
