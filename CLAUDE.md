# AscendIQ

Training and recruiting profiles for high school basketball players.
Solo build by a first-time developer. College applications due November — the
app is second priority when the two collide.

## Current focus

**Week 1 — accounts, database, authentication, live URL.**

Do not build ahead of this. If something later in the plan would help, say so;
don't write it.

## Stack

- Python 3.12 · Django · HTMX · plain CSS (no Tailwind, no Node, no build step)
- PostgreSQL on Supabase · app on Render · Cloudflare in front for DNS/CDN
- Views return **HTML fragments** for HTMX. There is no JSON API.
- Design tokens live in `static/css/ascendiq.css`. Never a raw hex in a component.

## Hard rules

1. **Every query filters by the logged-in user.**
   `Workout.objects.get(id=pk, athlete__user=request.user)` — never
   `Workout.objects.get(id=pk)`. Users are minors. A leak is not a bug, it's an
   incident.

2. **No secrets in code.** Keys live in `.env` locally and Render environment
   variables in production. Never in a template, never in anything committed.

3. **Mobile first.** Every screen works at 375px, one-handed, in a gym.
   Tap targets 44px minimum. Body text 16px minimum. Test before saying done.

4. **The AI coach speaks only about logged training data.** It never claims
   video or biomechanical analysis. It refuses eligibility, transfer, NIL and
   scholarship questions and points to the Recruiting Hub instead.

5. **Public profiles are private by default.** Publishing requires a parent's
   acknowledgement. A private profile returns **404**, never "this profile is
   private" — a 403 confirms the account exists.

6. **Aggregates, not rows, go to the model.** Session counts and percentages —
   never a name, school, city or date of birth.

## Style

- Explain what changed and why, briefly, before showing code.
- One screen or one view at a time. Don't refactor unasked.
- If something needs a package, say so and why before installing it.
- **If I'm about to do something that will cause a problem later, say so.**
- Prefer boring and readable over clever. I have to explain this in an interview.

## Definition of done

Deployed, working on a phone at 375px, and the two-account test still passes.

## Files that matter

- `DECISIONS.md` — engineering log. Real choices and overrides, dated.
- `LATER.md` — every cut feature. Add to it instead of building.
- `athletes/stats.py` — all calculations. Pure functions, no DB calls inside.
