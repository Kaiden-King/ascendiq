# Six-week plan — condensed

Machine-readable summary for Claude Code. Full detail is in the HTML guides.

## Week 1 — accounts to a live URL (steps 1–12)
Accounts, installs, Django project, first page, GitHub, deploy to Render,
Supabase connected, models, admin, signup/login/logout.
**Done when:** public URL loads, login persists overnight, two-account test passes.

## Week 2 — the workout loop (steps 13–21)
HTMX + CSRF header. Workout template as a plain Python dict. Today's workout
screen. Active session screen with per-row partials. Makes/attempts with
`inputmode="numeric"` and `delay:500ms`. Finish + summary. History with
pagination. Mobile pass at 375px.
**Done when:** a real workout is logged during a real practice, on a phone.

## Week 3 — charts and the public profile (steps 22–30)
Fix the practice list first. `stats.py` as pure functions — returns `None`, not
0, when there are no attempts. Django tests. Two charts via `json_script`.
Slugs + parent consent screen. Public profile at `/a/<slug>/`, no login, 404 if
private. Open Graph tags. Query and image performance.
**Done when:** a logged-out stranger opens it on a phone and asks how to get one.

## Week 4 — the AI coach (steps 31–38)
API key server-side only. Context = aggregates from `stats.py`, no identifying
data. System prompt with hard refusals. HTMX chat with indicator and failure
state. Rate limits + provider spend cap. Workout generator with validation and
fallback. Write the Recruiting Hub. **Code freeze Friday.**
**Done when:** it cites a real workout by date and refuses an NIL question three
different ways.

## Week 5 — no coding (steps 39–46)
Pilot with two teammates. Talk to the coach before the team. Sit next to each
person while they sign up — 25–30 across high school and AAU rosters. Watch,
don't explain. Track who returns unprompted.
**Done when:** everyone asked individually, four numbers written down, ranked
fix list built from what people actually hit.

## Week 6 — ship it (steps 47–55)
Top five fixes only. Security + mobile pass. Pricing page with waitlist.
Interest card. README with real numbers and screenshots. Launch. LinkedIn post.
Into the applications.
**Rule:** applications outrank the app. Every time.
