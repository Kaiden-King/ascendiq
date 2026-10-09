from django.http import Http404
from django.shortcuts import render
from django.utils import timezone

from athletes.models import Athlete

from .pages import PAGES, PAGES_BY_SLUG


def hub_context(request):
    """The Hub is public. Logged-in athletes get the app's header and nav around it."""
    athlete = None
    if request.user.is_authenticated:
        athlete = Athlete.objects.filter(user=request.user).first()
    return {"athlete": athlete, "active_tab": "hub", "base": "base.html" if athlete else "public_base.html"}


def hub_index(request):
    today = timezone.localdate()
    pages = [(page, page.is_due_for_review(today)) for page in PAGES]
    return render(request, "hub/index.html", {**hub_context(request), "pages": pages})


def hub_page(request, slug):
    page = PAGES_BY_SLUG.get(slug)
    if page is None:
        raise Http404
    return render(request, "hub/page.html", {
        **hub_context(request),
        "page": page,
        "due_for_review": page.is_due_for_review(timezone.localdate()),
    })
