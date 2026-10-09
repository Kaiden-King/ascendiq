"""Run with:  python manage.py test hub

The sourcing standard, enforced: every Hub page renders a numbered source list
of https links, shows when it was checked, and warns when it's due for review.
"""

import datetime
import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from athletes.models import Athlete

from .pages import PAGES

PLAIN_STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=PLAIN_STATIC)
class HubTests(TestCase):
    def test_index_is_public_and_lists_every_page(self):
        response = self.client.get("/hub/")
        self.assertEqual(response.status_code, 200)
        for page in PAGES:
            self.assertContains(response, page.title)

    def test_every_page_has_dated_sources(self):
        for page in PAGES:
            with self.subTest(page=page.slug):
                self.assertLess(page.checked_on, page.next_review)
                html = self.client.get(f"/hub/{page.slug}/").content.decode()
                self.assertIn("Checked on", html)
                sources = re.search(r'<ol class="sources">(.*?)</ol>', html, re.S)
                self.assertIsNotNone(sources, "every Hub page needs a source list")
                links = re.findall(r'href="(https?://[^"]+)"', sources.group(1))
                self.assertGreater(len(links), 0)
                self.assertTrue(all(link.startswith("https://") for link in links))

    def test_external_links_cant_reach_back(self):
        for page in PAGES:
            html = self.client.get(f"/hub/{page.slug}/").content.decode()
            for tag in re.findall(r'<a href="https://[^>]*>', html):
                self.assertIn('rel="noopener noreferrer"', tag)

    def test_due_for_review_banner(self):
        page = PAGES[0]
        url = f"/hub/{page.slug}/"
        self.assertNotContains(self.client.get(url), "due for review")
        later = page.next_review + datetime.timedelta(days=1)
        with mock.patch("hub.views.timezone.localdate", return_value=later):
            self.assertContains(self.client.get(url), "This page is due for review")

    def test_unknown_page_is_404(self):
        self.assertEqual(self.client.get("/hub/not-a-page/").status_code, 404)

    def test_logged_in_athlete_gets_the_app_nav(self):
        user = get_user_model().objects.create_user("reader", password="unused-pw-123")
        Athlete.objects.create(user=user, full_name="Reader Person", slug="reader")
        self.client.force_login(user)
        html = self.client.get("/hub/").content.decode()
        self.assertIn('class="nav"', html)
        self.assertRegex(html, r'href="/hub/" class="nav__item"\s+aria-current="page"')

    def test_no_personal_details_on_public_hub_pages(self):
        # The original scholarship guide named one family's college list and finances.
        # Nothing like that may appear on a public page.
        for page in PAGES:
            html = self.client.get(f"/hub/{page.slug}/").content.decode().lower()
            for private in ["kaiden", "morehouse", "georgia tech", "churchill"]:
                self.assertNotIn(private, html, f"{private!r} found on {page.slug}")
