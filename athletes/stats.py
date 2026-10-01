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
