from django.contrib import admin

from .models import Athlete, Measurement, Workout, WorkoutSet


class WorkoutSetInline(admin.TabularInline):
    """Edit a workout's drills on the same page as the workout."""

    model = WorkoutSet
    extra = 1


@admin.register(Athlete)
class AthleteAdmin(admin.ModelAdmin):
    list_display = ["full_name", "user", "school", "grad_year", "is_public"]
    prepopulated_fields = {"slug": ["full_name"]}


@admin.register(Workout)
class WorkoutAdmin(admin.ModelAdmin):
    list_display = ["athlete", "date", "focus", "status"]
    list_filter = ["athlete"]
    inlines = [WorkoutSetInline]


@admin.register(Measurement)
class MeasurementAdmin(admin.ModelAdmin):
    list_display = ["athlete", "date", "metric", "value", "unit"]
