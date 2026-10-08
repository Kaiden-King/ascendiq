# Later

Everything cut, so it stays out of the six weeks without being forgotten.
Add to this instead of building. Nothing here is a bad idea.

## Week 4 — Recruiting Hub
- "Where to find rankings" page: links to each outlet's official basketball
  class rankings (ESPN, 247Sports, On3, Rivals, MaxPreps, USA Today) and a line
  on how each ranks players. Links only — never copy their lists (their content,
  often paywalled, and full of other people's kids). Verify each outlet still
  publishes individual player rankings before listing it. Decided 2026-10-04.

## Before sending the link to coaches (step 30) — 2026-10-08
- Render free plan sleeps after ~15 min idle; first visit then waits ~30–60s.
  Measured awake: ~0.1s to first byte, ~80 KB of files. Fix: Render's cheapest
  paid plan (~$7/mo, needs a parent) or a keep-alive ping if Render's terms allow.
- Supabase free projects can pause after about a week of no activity — check
  their current rules and keep the app in use, or upgrade.

## Public profile — known limits (2026-10-07)
- Parent consent is a tick on the athlete's device. Real verification: email the
  parent a confirmation link and only publish once they click it (needs the app
  to send email — Render + an email provider).
- Public profiles send "noindex" (search engines asked not to list them). Option
  for confirmed 18+ athletes to allow search listing.
- Profile photo, and an image on the link preview card (step 28) — needs file
  uploads, resizing, and storage.
- Re-ask for consent if what's shown changes a lot after publishing (today the
  consent record keeps the list from the moment of publishing).

## Team leaderboards — gamified (Kaiden's request, 2026-10-04)
- High school teams: a team join code from the coach or captain; each team
  gets its own board, seen only by its members.
- Gamified: points for finished workouts, streaks and shots logged; weekly
  team challenges; badges (first 500 shots, 7-day streak, most improved).
- Keep the grade boards' safety rules: opt-in, first name + last initial,
  hidden under 4 members, 8th grade and up.
- Decide first: who can create a team (coach account? see "Coach accounts"),
  and whether adults can see a team board at all (no adult–minor channel).

## Next — after the November deadlines
- Game stats and season line (PPG, rebounds, box scores) — unlocks My Season,
  Recent Games and most achievements
- Coach accounts, team dashboard, stat verification
- Parent view
- Stripe payments (needs an adult account representative)
- Recruiting CRM — target schools, contacts, deadlines, visits

## Video
- Film upload, clip library, highlight links
- AI highlight generation
- On-device pose analysis (MediaPipe) — the honest source for form feedback

## Needs scale first
- College coach accounts and athlete search
- Profile view tracking, offer tracking, interest tracking
- Coach directory (also a data-licensing question, not just code)

## Needs a safety design first
- **Inbox / athlete–coach DMs.** Parent on every thread, coaches cannot
  initiate, verified coach identity, text only, everything logged.
- **"Run It" pickup games.** Courts not people — never show one athlete how
  far away another is.
- **Connections and followers.** Who can follow a minor, whether follower lists
  are visible, how adults are kept out. A follower list shows strangers who a
  teenager is connected to. Decided 2026-10-02: leave out until this is designed.

## Second sport
- Football, then soccer. Sport config seam is already in the schema:
  positions, skill ratings, stat lines, combine metrics, season calendar.

## From week 2 onward — things I wanted and didn't build
- Password reset by email — sign up doesn't ask for an email yet, so a
  forgotten password is reset by hand in /admin
- Limit login attempts (stop password guessing) — week 6 security pass
- Workout time when the app is left open: duration runs Start → Finish, so a
  forgotten Finish reads 185 min. Let athletes adjust it on the summary, or cap it
- Profile pictures without sending the athlete's name to an outside service
  (app-starter's base.html uses dicebear.com — replace before week 2)
