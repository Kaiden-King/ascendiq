"""Every Recruiting Hub page, with the facts the sourcing standard requires.

A page can't exist without a title, a checked-on date and a review date, and
its content must carry its own numbered source list (a test checks this).
The shared layout shows the dates at the top and a red "due for review" banner
once a page is past its review date.
"""

import datetime
from dataclasses import dataclass

STALE_AFTER_DAYS = 90  # pages without a scheduled review are due after this


@dataclass(frozen=True)
class HubPage:
    slug: str
    title: str
    summary: str
    checked_on: datetime.date
    next_review: datetime.date
    disclaimer: str

    @property
    def template(self):
        return f"hub/pages/{self.slug}.html"

    def is_due_for_review(self, today):
        return today >= self.next_review or (today - self.checked_on).days > STALE_AFTER_DAYS


PAGES = [
    HubPage(
        slug="transfer-and-nil",
        title="Transfer eligibility and NIL across the DMV",
        summary="Maryland, DC and Virginia: what each association, league and school system "
                "says about sitting out after a transfer, and about NIL.",
        checked_on=datetime.date(2026, 9, 19),
        next_review=datetime.date(2027, 8, 1),
        disclaimer="Summary for families, compiled from the sources listed above. Not legal advice. "
                   "Eligibility is determined by your school, local school system, and athletic association.",
    ),
    HubPage(
        slug="events-and-camps",
        title="When coaches can watch, and what that means for camps",
        summary="The NCAA recruiting calendar, certified events and BBCS registration, "
                "and how to judge a camp before paying for it.",
        checked_on=datetime.date(2026, 9, 20),
        next_review=datetime.date(2027, 8, 1),
        disclaimer="Summary for families, compiled from the sources listed above. Not legal or compliance "
                   "advice. Confirm eligibility and certification questions with your school, club and the "
                   "NCAA directly.",
    ),
]

PAGES_BY_SLUG = {page.slug: page for page in PAGES}
