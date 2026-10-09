"""The AI coach: what it's told, what it's sent, and the one call to Claude.

Three rules shape everything here (CLAUDE.md hard rules 4 and 6):
  1. It only talks about logged training data.
  2. Only numbers and a position leave this server. Never a name, school,
     city, date of birth, email, or anything else that identifies a minor.
  3. Eligibility, transfer, NIL and scholarship questions go to the Hub,
     never to the model.
"""

import datetime
import json
import logging
import os
import re

import anthropic
from django.conf import settings
from django.db.models import Sum

from .stats import shooting_pct

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# The system prompt. Every "must NOT" line is a product and safety decision
# about what the app may tell a teenager. Read it before changing it.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the training assistant inside AscendIQ, an app where high school \
basketball players log their workouts.

You may ONLY discuss the training data provided in the athlete's message, between the \
<training_data> tags. Talk about volume, consistency, shooting percentages and trends, and \
suggest what to work on next based on those numbers.

You must NOT:
- claim to have watched video, or comment on footwork, shooting form or mechanics
- state joint angles, release times, or any biomechanical measurement
- answer questions about NCAA or high school eligibility, transfers, NIL, or scholarships. \
Say you can't help with that and point them to the Recruiting Hub in the app and to their \
school's athletic director
- predict offers, rankings, playing time, or recruiting outcomes
- give medical, injury, nutrition-prescription or weight-loss advice. For pain or injury, \
tell them to stop and talk to a parent, coach or athletic trainer
- invent numbers or workouts that aren't in the data

If <training_data> contains "workout_in_question", the athlete is asking about that one \
logged session: answer about it, comparing it with their recent numbers where useful.

The athlete may also describe a workout they did but didn't log. You may discuss it, but say \
clearly that it's what they told you rather than logged data, don't mix its numbers into their \
logged totals, and suggest logging it in the app next time.

If the data is too thin to answer, say so plainly and suggest logging a few more workouts.
Be encouraging but honest. Cite the specific numbers and dates you were given.
Keep every answer under 120 words, in plain sentences, no headings."""

HUB_REPLY = (
    "I can't help with eligibility, transfers, NIL or scholarships. A wrong answer there "
    "could cost you a season. The Recruiting Hub in the app has sourced guides on these, "
    "and your school's athletic director can give you an answer in writing."
)

FAILED_REPLY = "The coach couldn't answer right now. Check your signal and try again — this didn't use up a question."

DECLINED_REPLY = "The coach can't answer that one. Try asking about your workouts, shooting or consistency."

STARTER_QUESTIONS = [
    "How has my shooting changed this month?",
    "Am I training consistently enough?",
    "What should I focus on in my next workout?",
]

# Starter questions when a logged workout is attached.
ATTACHED_STARTERS = [
    "How did this session compare to my recent ones?",
    "What should I work on after this workout?",
]

# Questions that must never reach the model. Matching here is a safety net on
# top of the system prompt: it's guaranteed, and it costs nothing.
_HUB_TOPICS = re.compile(
    r"\bnil\b|name,? image|likeness|\btransfer|eligib|scholarship|\bncaa\b|sit out|"
    r"\boffers?\b|recruit(ing|ed|er)? rules?",
    re.IGNORECASE,
)


def is_hub_question(question):
    """True if the question is about eligibility, transfers, NIL, scholarships or the like."""
    return bool(_HUB_TOPICS.search(question))


def is_configured():
    """The coach only runs once an API key is set (in .env or Render's Environment page)."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


# ---------------------------------------------------------------------------
# Context: aggregates only. This dict is the ONLY athlete data sent to Claude.
# ---------------------------------------------------------------------------

def _period_summary(workouts):
    """Sessions, minutes and shooting for a set of finished workouts."""
    totals = workouts.aggregate(
        made=Sum("workoutset__made"), attempted=Sum("workoutset__attempted")
    )
    made, attempted = totals["made"] or 0, totals["attempted"] or 0
    return {
        "sessions": workouts.count(),
        "total_minutes": workouts.aggregate(m=Sum("duration_min"))["m"] or 0,
        "shots_made": made,
        "shots_attempted": attempted,
        "shooting_pct": shooting_pct(made, attempted),
    }


def build_context(athlete, today):
    """What the coach knows: numbers, dates and a position. Nothing that identifies anyone."""
    finished = athlete.workout_set.filter(status="completed")
    last_28 = finished.filter(date__gt=today - datetime.timedelta(days=28))
    prior_28 = finished.filter(
        date__gt=today - datetime.timedelta(days=56),
        date__lte=today - datetime.timedelta(days=28),
    )

    recent_sessions = []
    for workout in last_28.order_by("-date", "-id").prefetch_related("workoutset_set")[:6]:
        drills = list(workout.workoutset_set.all())
        made = sum(d.made or 0 for d in drills)
        attempted = sum(d.attempted or 0 for d in drills)
        recent_sessions.append({
            "date": workout.date.isoformat(),
            "focus": workout.focus,
            "minutes": workout.duration_min,
            "drills_done": f"{sum(1 for d in drills if d.completed)} of {len(drills)}",
            "shooting_pct": shooting_pct(made, attempted),
            "shots": f"{made}/{attempted}",
        })

    return {
        "today": today.isoformat(),
        "position": athlete.position or "not given",
        "last_28_days": _period_summary(last_28),
        "previous_28_days": _period_summary(prior_28),
        "recent_sessions": recent_sessions,
    }


# ---------------------------------------------------------------------------
# The call to Claude.
# ---------------------------------------------------------------------------

def _client():
    # The SDK reads ANTHROPIC_API_KEY from the environment itself.
    # 20s timeout and one retry: a gym's wifi shouldn't leave the screen hanging.
    return anthropic.Anthropic(timeout=20.0, max_retries=1)


def _call(system, user_message, max_tokens, output_format=None):
    """One request to Claude. Returns the response, or None on any failure (logged)."""
    output_config = {"effort": "low"}  # a quick read of a few numbers, not deep reasoning
    if output_format:
        output_config["format"] = output_format
    try:
        return _client().beta.messages.create(
            model=settings.COACH_MODEL,
            max_tokens=max_tokens,
            output_config=output_config,
            system=system,
            messages=[{"role": "user", "content": user_message}],
            # If the model declines for safety reasons, Anthropic retries on its
            # default fallback model inside the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.APITimeoutError:
        logger.warning("Coach call timed out")
    except anthropic.RateLimitError:
        logger.warning("Coach call rate limited")
    except anthropic.AuthenticationError:
        logger.error("Coach API key missing or invalid")
    except anthropic.APIStatusError as error:
        logger.error("Coach API error %s (request %s)", error.status_code, getattr(error, "request_id", None))
    except anthropic.APIConnectionError:
        logger.warning("Coach call could not connect")
    return None


def _text(response):
    return "\n".join(block.text for block in response.content if block.type == "text").strip()


def _wrap(context):
    return "<training_data>\n" + json.dumps(context, indent=1) + "\n</training_data>\n\n"


def ask_coach(context, question):
    """Ask one question. Returns (reply_text, answered).

    answered is False for any failure or decline, so the question isn't counted.
    Each question stands alone (no chat history is sent), which keeps it cheap
    and keeps old messages from ever being re-sent.
    """
    response = _call(SYSTEM_PROMPT, _wrap(context) + "Question: " + question, max_tokens=1500)
    if response is None:
        return FAILED_REPLY, False
    if response.stop_reason == "refusal":
        return DECLINED_REPLY, False
    text = _text(response)
    if not text:
        return FAILED_REPLY, False
    return text, True


# ---------------------------------------------------------------------------
# A single logged workout, when the athlete asks about it. Drill names and
# targets come from the workout template, so nothing here identifies anyone.
# ---------------------------------------------------------------------------

def build_workout_context(workout):
    drills = []
    for drill in workout.workoutset_set.all():
        entry = {"drill": drill.drill_name, "target": drill.target, "done": drill.completed}
        if drill.made is not None:
            entry.update(made=drill.made, attempted=drill.attempted,
                         shooting_pct=shooting_pct(drill.made, drill.attempted))
        drills.append(entry)
    return {
        "date": workout.date.isoformat(),
        "focus": workout.focus,
        "minutes": workout.duration_min,
        "finished": workout.status == "completed",
        "drills": drills,
    }


# ---------------------------------------------------------------------------
# Planning a workout (step 36). Claude returns JSON in a fixed shape; we still
# check every field ourselves before anything is saved, and fall back to the
# standard workout if anything is off.
# ---------------------------------------------------------------------------

PLAN_LENGTHS = [30, 45, 60, 90]
PLAN_FOCUSES = ["Shooting", "Ball handling", "Mixed", "Finishing at the rim", "Defense and footwork"]
MIN_DRILLS, MAX_DRILLS = 3, 8

PLAN_SYSTEM_PROMPT = """You plan solo basketball workouts for a high school player using the \
AscendIQ app. Use their training data (between the <training_data> tags) to choose drills: \
for example more shooting volume after a run of weak percentages.

Rules:
- 3 to 8 drills that one player can do alone on a court with a ball, fitting the requested length.
- Each drill: a short name (under 60 characters), a target such as "3 x 45s" or "50 makes" \
(under 30 characters), and tracks_makes true only for shooting drills where makes and \
attempts are counted.
- No weights, sprints to exhaustion, medical or injury advice, and nothing needing equipment \
beyond a ball and a hoop.
- focus: a short label for the session, under 40 characters."""

PLAN_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "focus": {"type": "string"},
            "drills": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "target": {"type": "string"},
                        "tracks_makes": {"type": "boolean"},
                    },
                    "required": ["name", "target", "tracks_makes"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["focus", "drills"],
        "additionalProperties": False,
    },
}


def _clean_text(value, max_length):
    """A short, single-line string, or raise ValueError."""
    if not isinstance(value, str):
        raise ValueError("not text")
    value = " ".join(value.split())  # collapse newlines and runs of spaces
    if not value or len(value) > max_length:
        raise ValueError("empty or too long")
    return value


def validate_plan(data):
    """Check the model's JSON before it can go anywhere near the database.

    Returns a clean {"focus", "drills": [...]} or raises ValueError.
    """
    if not isinstance(data, dict):
        raise ValueError("plan is not an object")
    drills = data.get("drills")
    if not isinstance(drills, list) or not MIN_DRILLS <= len(drills) <= MAX_DRILLS:
        raise ValueError("wrong number of drills")
    clean = []
    for drill in drills:
        if not isinstance(drill, dict) or not isinstance(drill.get("tracks_makes"), bool):
            raise ValueError("bad drill")
        clean.append({
            "name": _clean_text(drill.get("name"), 60),
            "target": _clean_text(drill.get("target"), 30),
            "tracks_makes": drill["tracks_makes"],
        })
    return {"focus": _clean_text(data.get("focus"), 40), "drills": clean}


def plan_workout(context, minutes, focus, note=""):
    """Ask Claude for a workout. Returns (plan, answered).

    plan is always usable: Claude's if it passed validation, otherwise the
    standard workout. answered is True only when Claude's own plan was used.
    """
    request = f"Plan a {minutes}-minute workout. Focus: {focus}."
    if note:
        request += f" The player adds: {note}"
    response = _call(PLAN_SYSTEM_PROMPT, _wrap(context) + request, max_tokens=2000,
                     output_format=PLAN_SCHEMA)
    if response is not None and response.stop_reason not in ("refusal", "max_tokens"):
        try:
            return validate_plan(json.loads(_text(response))), True
        except (ValueError, json.JSONDecodeError) as error:
            logger.warning("Generated workout failed validation, using the standard one: %s", error)
    return standard_plan(), False


def standard_plan():
    """The fallback: the hard-coded workout from step 14."""
    from .workout_templates import GUARD_60, GUARD_60_FOCUS
    return {
        "focus": GUARD_60_FOCUS,
        "drills": [{"name": n, "target": t, "tracks_makes": m} for n, t, m in GUARD_60],
    }
