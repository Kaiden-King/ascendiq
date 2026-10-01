"""All calculations. Pure functions: numbers in, numbers out, no database calls.

Keeping them pure means they're easy to test and easy to explain.
"""


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


def minutes_between(start, end):
    """Whole minutes from start to end, never less than 1."""
    return max(1, round((end - start).total_seconds() / 60))
