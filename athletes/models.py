from django.conf import settings
from django.db import models


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
    gpa = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    is_public = models.BooleanField(default=False)  # opt in, never out
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name

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

    def __str__(self):
        return self.drill_name


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
