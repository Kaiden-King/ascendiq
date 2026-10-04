from urllib.parse import urlsplit

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone

from .models import Athlete, Highlight, Ranking


class SignupForm(UserCreationForm):
    """Django's built-in sign up form, plus the athlete's name."""

    full_name = forms.CharField(
        max_length=120,
        label="Your name",
        widget=forms.TextInput(attrs={"autocomplete": "name"}),
    )

    class Meta(UserCreationForm.Meta):
        fields = ["full_name", "username"]


POSITIONS = ["Point guard", "Shooting guard", "Small forward", "Power forward", "Center"]

# Only these sites are allowed in highlight links — a minor's profile shouldn't
# send coaches (or anyone) to an arbitrary website.
HIGHLIGHT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
                   "hudl.com", "www.hudl.com", "vimeo.com", "www.vimeo.com"}


def number_widget(placeholder=""):
    return forms.NumberInput(attrs={"inputmode": "numeric", "placeholder": placeholder})


class ProfileForm(forms.ModelForm):
    """Profile details. Height and wingspan are typed as feet + inches, stored as inches."""

    height_ft = forms.IntegerField(label="Feet", required=False, min_value=4, max_value=7, widget=number_widget("6"))
    height_extra = forms.IntegerField(label="Inches", required=False, min_value=0, max_value=11, widget=number_widget("2"))
    wingspan_ft = forms.IntegerField(label="Feet", required=False, min_value=4, max_value=8, widget=number_widget("6"))
    wingspan_extra = forms.IntegerField(label="Inches", required=False, min_value=0, max_value=11, widget=number_widget("6"))

    field_order = [
        "full_name", "position", "grad_year", "school",
        "height_ft", "height_extra", "weight_lb", "wingspan_ft", "wingspan_extra", "gpa",
    ]

    class Meta:
        model = Athlete
        fields = ["full_name", "position", "grad_year", "school", "weight_lb", "gpa"]
        labels = {
            "full_name": "Your name",
            "grad_year": "Class of",
            "weight_lb": "Weight (lb)",
            "gpa": "GPA",
        }
        widgets = {
            "position": forms.TextInput(attrs={"list": "positions", "placeholder": "e.g. Point guard"}),
            "grad_year": number_widget("2027"),
            "weight_lb": number_widget("175"),
            "gpa": forms.NumberInput(attrs={"inputmode": "decimal", "step": "0.01", "placeholder": "3.60"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Show stored inches back as feet + inches.
        for field, stored in (("height", self.instance.height_in), ("wingspan", self.instance.wingspan_in)):
            if stored is not None:
                self.initial[f"{field}_ft"], self.initial[f"{field}_extra"] = divmod(stored, 12)

    def clean_grad_year(self):
        year = self.cleaned_data["grad_year"]
        if year is not None and not 2024 <= year <= 2035:
            raise forms.ValidationError("Enter a class year between 2024 and 2035.")
        return year

    def clean_weight_lb(self):
        weight = self.cleaned_data["weight_lb"]
        if weight is not None and not 80 <= weight <= 400:
            raise forms.ValidationError("Enter a weight between 80 and 400 lb.")
        return weight

    def clean_gpa(self):
        gpa = self.cleaned_data["gpa"]
        if gpa is not None and not 0 <= gpa <= 5:
            raise forms.ValidationError("GPA is between 0.00 and 5.00.")
        return gpa

    def combine(self, name):
        """Feet + inches boxes -> total inches. Both blank -> None. One blank -> error."""
        feet = self.cleaned_data.get(f"{name}_ft")
        extra = self.cleaned_data.get(f"{name}_extra")
        if feet is None and extra is None:
            return None
        if feet is None:
            self.add_error(f"{name}_ft", "Add the feet too.")
            return None
        return feet * 12 + (extra or 0)

    def clean(self):
        cleaned = super().clean()
        self.instance.height_in = self.combine("height")
        self.instance.wingspan_in = self.combine("wingspan")
        return cleaned


class HighlightForm(forms.ModelForm):
    class Meta:
        model = Highlight
        fields = ["title", "url"]
        labels = {"title": "Title", "url": "Link"}
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "e.g. Junior season mix"}),
            "url": forms.URLInput(attrs={"placeholder": "https://youtu.be/…", "inputmode": "url"}),
        }

    def clean_url(self):
        url = self.cleaned_data["url"]
        parts = urlsplit(url)
        if parts.scheme != "https" or (parts.hostname or "").lower() not in HIGHLIGHT_HOSTS:
            raise forms.ValidationError("Use an https link from YouTube, Hudl or Vimeo.")
        return url


# Each outlet's own website. A ranking's link must be on the outlet you picked,
# so "247Sports #45" can only point at 247sports.com — a coach lands on the source.
OUTLET_DOMAINS = {
    "espn": "espn.com",
    "247sports": "247sports.com",
    "on3": "on3.com",
    "rivals": "rivals.com",
    "maxpreps": "maxpreps.com",
    "usatoday": "usatoday.com",
}


def on_domain(host, domain):
    """'www.247sports.com' is on '247sports.com'; 'fake247sports.com' is not."""
    host = (host or "").lower()
    return host == domain or host.endswith("." + domain)


class RankingForm(forms.ModelForm):
    class Meta:
        model = Ranking
        fields = ["outlet", "stars", "national_rank", "position_rank", "state_rank", "checked_on", "url"]
        labels = {
            "outlet": "Outlet",
            "stars": "Stars (1–5)",
            "national_rank": "National rank",
            "position_rank": "Position rank",
            "state_rank": "State rank",
            "checked_on": "Date you checked it",
            "url": "Link to your ranking",
        }
        widgets = {
            "stars": number_widget("4"),
            "national_rank": number_widget("45"),
            "position_rank": number_widget("8"),
            "state_rank": number_widget("3"),
            "checked_on": forms.DateInput(attrs={"type": "date"}),
            "url": forms.URLInput(attrs={"placeholder": "https://247sports.com/…", "inputmode": "url"}),
        }

    def clean_stars(self):
        stars = self.cleaned_data["stars"]
        if stars is not None and not 1 <= stars <= 5:
            raise forms.ValidationError("Stars are 1 to 5.")
        return stars

    def clean_checked_on(self):
        checked_on = self.cleaned_data["checked_on"]
        if checked_on > timezone.localdate():
            raise forms.ValidationError("That date is in the future.")
        return checked_on

    def clean(self):
        cleaned = super().clean()
        ranks = ["stars", "national_rank", "position_rank", "state_rank"]
        if not any(cleaned.get(field) for field in ranks):
            raise forms.ValidationError("Add at least one: stars, or a national, position or state rank.")
        for field in ["national_rank", "position_rank", "state_rank"]:
            value = cleaned.get(field)
            if value is not None and not 1 <= value <= 3000:
                self.add_error(field, "Ranks run from 1 to 3000.")

        outlet, url = cleaned.get("outlet"), cleaned.get("url")
        if outlet and url:
            parts = urlsplit(url)
            domain = OUTLET_DOMAINS[outlet]
            if parts.scheme != "https" or not on_domain(parts.hostname, domain):
                self.add_error("url", f"Use an https link on {domain}, the outlet you picked.")
        return cleaned
