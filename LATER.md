# Later

Everything cut, so it stays out of the six weeks without being forgotten.
Add to this instead of building. Nothing here is a bad idea.

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

## Second sport
- Football, then soccer. Sport config seam is already in the schema:
  positions, skill ratings, stat lines, combine metrics, season calendar.

## From week 2 onward — things I wanted and didn't build
- Password reset by email — sign up doesn't ask for an email yet, so a
  forgotten password is reset by hand in /admin
- Limit login attempts (stop password guessing) — week 6 security pass
- "You've got 2 drills left — finish anyway?" prompt on Finish (right now an
  unfinished drill just shows as 3/5 on the summary)
- Workout time when the app is left open: duration runs Start → Finish, so a
  forgotten Finish reads 185 min. Let athletes adjust it on the summary, or cap it
- Profile pictures without sending the athlete's name to an outside service
  (app-starter's base.html uses dicebear.com — replace before week 2)
