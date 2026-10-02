"""All calculations. Pure functions: numbers in, numbers out, no database calls.

Keeping them pure means they're easy to test and easy to explain.
"""

import datetime


def shooting_pct(made, attempted):
    """Whole-number percentage, or None when there's nothing to divide by.

    None, not 0 — "no attempts" and "missed every shot" are different things.
    """
    if not attempted:
        return None
    return round(made / attempted * 100)


def shooting_totals(scores):
    """Add up (made, attempted) pairs. Returns (made, attempted, pct or None)."""
    made = sum(m for m, a in scores)
    attempted = sum(a for m, a in scores)
    return made, attempted, shooting_pct(made, attempted)


def pct_change(current, previous):
    """Percentage points up or down from last time, or None if either is missing."""
    if current is None or previous is None:
        return None
    return current - previous


def minutes_between(start, end):
    """Whole minutes from start to end, never less than 1."""
    return max(1, round((end - start).total_seconds() / 60))


def week_start(day):
    """The Monday of the week that `day` falls in."""
    return day - datetime.timedelta(days=day.weekday())


def weekly_series(workouts, today, weeks=12):
    """One entry per week for the last `weeks` weeks, oldest first, ending this week.

    `workouts` is a list of (date, made, attempted) — one per finished workout.
    Each entry: {"week_start": date, "workouts": int, "shooting_pct": int or None}.
    A week with workouts but no shots gets shooting_pct None, so a chart shows a
    gap instead of a fake 0%. Workouts outside the window are ignored.
    """
    first_monday = week_start(today) - datetime.timedelta(weeks=weeks - 1)
    series = [
        {"week_start": first_monday + datetime.timedelta(weeks=i), "workouts": 0, "made": 0, "attempted": 0}
        for i in range(weeks)
    ]
    for day, made, attempted in workouts:
        index = (week_start(day) - first_monday).days // 7
        if 0 <= index < weeks:
            series[index]["workouts"] += 1
            series[index]["made"] += made or 0
            series[index]["attempted"] += attempted or 0

    return [
        {
            "week_start": week["week_start"],
            "workouts": week["workouts"],
            "shooting_pct": shooting_pct(week["made"], week["attempted"]),
        }
        for week in series
    ]


def feet_and_inches(total_inches):
    """74 -> 6′2″. None stays None (not entered yet)."""
    if total_inches is None:
        return None
    feet, inches = divmod(total_inches, 12)
    return f"{feet}′{inches}″"
