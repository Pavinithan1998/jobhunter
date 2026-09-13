# Frontend brief — building this in Lovable

This is a prompt-ready brief. Paste the relevant sections into Lovable
along with `API_DOCUMENTATION.md` (or a link to your deployed
`/openapi.json`) so it has the exact request/response shapes.

## One-time setup Lovable needs to know

- **Backend base URL**: wherever you deployed the FastAPI app (see
  README.md → "Deploying it so Lovable can reach it"). Not `localhost` once
  it's live — Lovable's hosted frontend can't reach your laptop.
- **Auth**: every request needs header `X-API-Key: <key>`. Store the key in
  a settings/config screen the user fills in once (e.g. localStorage or a
  simple config context), not hardcoded — it's a secret.
- **CORS**: make sure the backend's `CORS_ORIGINS` includes the exact URL
  Lovable publishes the app at, or every request will fail silently in the
  browser console with a CORS error.

## Suggested screens

### 1. Setup / Onboarding
Shown when `GET /api/profile` returns 404.
- Form: name, email, phone, location, target titles (chip input →
  comma-joined string), target locations (chip input), remote preference
  (segmented control: Remote/Hybrid/Onsite/Any — this one is just a scoring
  nudge; the **hard** filter is on the Settings screen below, don't
  conflate the two), seniority, salary range, must-have keywords, exclude
  keywords.
- Submit → `POST /api/profile`.
- CV upload (drag-and-drop or file picker, accept `.pdf,.docx,.txt`) →
  `POST /api/profile/cv` as multipart form data.
- Optionally roll straight into the Settings screen (below) as step 2 of
  onboarding, since it's just as important before the first fetch.

### 2. Settings — country, work mode, sponsorship
A dedicated screen, separate from Profile. `GET /api/settings` (fine if it
404s — show the defaults below and let `POST` create the row on save).

- **Country**: a country picker or comma-tag input, pre-filled `"GB"`.
  Label it clearly as "search & apply in" — this drives both which
  countries get queried and whether UK sponsorship checking is active
  (only runs when GB is included). Offer Canada, US, etc. as easy presets.
- **Work mode**: segmented control — Remote / Hybrid / Onsite / Any. This
  is a hard filter: jobs that clearly conflict get auto-dismissed on the
  next scoring pass. Worth a one-line note: "Jobs we can't confidently
  classify are kept, not dismissed."
- **Require visa sponsorship**: a toggle. When on, jobs whose description
  reads as unlikely to sponsor get auto-dismissed. Pair this with a small
  status line reading from `GET /api/sources/uk-sponsor-register/status`:
  if `downloaded` is `false`, show "Sponsorship checking isn't set up yet"
  with a "Set up now" button → `POST /api/sources/uk-sponsor-register/refresh`
  (takes a few seconds, show a spinner). If `downloaded` is `true`, show
  "Checked against N companies as of \<date\>" with a manual "Refresh" button.
- **Excluded companies**: a tag input, comma-joined on save.
- **Digest threshold**: a slider 0-100, defaults to 60 — "only show me
  jobs scoring above this in my daily digest."
- Save → `POST /api/settings`.

### 3. Dashboard (home screen)
- Call `GET /api/dashboard/summary` and `GET /api/jobs/digest/today` on load.
- Stat tiles: total jobs, new today, shortlisted (not yet applied), applied
  in last 7 days.
- "Today's digest" list: today's top relevant jobs, each as a job card (see
  the Job Card component spec below). Card actions: Shortlist / Dismiss
  (both `PATCH .../status`), View detail.
- A "Refresh jobs now" button: `POST /api/jobs/fetch` → `POST
  /api/jobs/score-batch` → re-fetch the digest. Show a loading spinner —
  10-30 seconds depending on volume.
- A separate, prominent **"Search the internet"** box: a text input +
  optional location/country fields → `POST /api/jobs/search-web`. This is
  explicitly a different action from "Refresh jobs now" (that's the
  standing daily sources; this is an on-demand, broader search) — label it
  distinctly, e.g. "Search the whole internet for a specific role" vs.
  "Refresh my tracked sources." Results come back scored already (a few
  seconds' wait) — show them inline or route straight to the Browse screen
  filtered to `source=web_search`.

### 4. Browse / All Jobs
- Filter bar: status dropdown, minimum score slider, work-mode filter
  (Remote/Hybrid/Onsite/Any), country filter, sponsorship filter
  (Likely/Unlikely/Unclear), a "UK sponsor licensed" toggle, search box —
  all map directly to `GET /api/jobs` query params.
- Infinite scroll or pagination using `limit`/`offset`.
- Same job card component as the dashboard digest.
- "+ Add job manually" button opens a form (title, company, location,
  country, description, url, salary, remote checkbox) → `POST
  /api/sources/manual-job`. Label this clearly as **"Paste a job from
  LinkedIn, Indeed, or anywhere else"** — it's the intended way those two
  platforms' listings get into the app (tooltip: "LinkedIn/Indeed don't
  allow automatic fetching, so paste jobs you find there manually").

### 5. Job Card component (reused everywhere)
Every `JobListingOut` has everything needed for one consistent card:
- Title, company, location, salary_text.
- **Score badge**: `relevance_score` 0-100 or `null` → render `null` as
  "Not scored yet", not 0. Colour-code: green ≥80, amber 50-79, grey <50.
- **Status pill**: map each `JobStatus` to a colour once, reuse everywhere
  — new (grey), scored (blue), shortlisted (purple), dismissed (light
  grey/strikethrough), applied (yellow), interviewing (orange), offer
  (green), rejected (red).
- **Work mode chip**: Remote / Hybrid / Onsite / Unclear (grey, less
  prominent than the others since it's uncertain by definition).
- **Two separate sponsorship indicators — don't merge these into one:**
  - a chip for `sponsorship_status` (Likely/Unlikely/Unclear), sourced from
    the job description's own wording — tooltip shows `sponsorship_reasoning`.
  - a chip for `uk_sponsor_licensed` (true/false/null → "Licensed sponsor",
    "Not on register", "Not checked"), sourced from the actual UK Home
    Office register — tooltip shows `uk_sponsor_reasoning`. Only show this
    chip at all when `uk_sponsor_licensed` isn't `null`, since `null` means
    "not applicable" (e.g. non-UK job) as much as "not checked yet."

### 6. Job detail
- `GET /api/jobs/{id}` for the full description and all the fields above,
  shown with more room (e.g. full reasoning text, not just tooltips).
- Status changer (buttons or dropdown) → `PATCH .../status`.
- "Generate tailored CV & cover letter" button → `POST .../tailor` (loading
  state — a few seconds). On success, render both documents'
  `content_text` inline and show download buttons using `download_url`.
  If documents already exist (`GET .../documents` on load), show them
  immediately instead of the generate button, with a "Regenerate" option.
- "Mark as applied" button → `POST .../apply`. Copy: this records that
  *you* submitted it — the app doesn't submit anything on its own.
- Timeline section: `GET .../events`, oldest-to-newest. A small form to add
  a free-text note → `POST .../events` with `event_type: "note"`.

### 7. Applications page (dedicated — this is its own nav item, not a tab of Browse)
- Top-level toggle or tabs: **Manual** vs **Automated** →
  `GET /api/applications?channel=manual_search` /
  `?channel=automated_search`. Omit `channel` for an "All" view.
- Below that, a 5-column board by `application_stage`: **No response**,
  **Responded**, **Interviewing**, **Offer**, **Rejected**. Populate by
  grouping the response, or issue one filtered call per column
  (`?stage=interviewing` etc.) if that's simpler for your data layer.
- Each card uses the same Job Card component as elsewhere, plus the stage
  is implied by its column.
- Moving a card between columns (drag, or a "Move to..." menu) →
  `PATCH /api/jobs/{id}/application-stage` with the target stage. Note this
  endpoint 400s if the job somehow isn't in `applied`+ state yet — shouldn't
  happen from this screen since everything here already passed through
  `POST .../apply`, but handle the error gracefully anyway.
- Clicking a card opens the Job detail screen (screen 6) for that job.

## Component notes

- **Loading states matter** on `/fetch`, `/score-batch`, `/search-web`,
  `/tailor`, and `/uk-sponsor-register/refresh` — all of these call
  external APIs/LLMs and take real time (seconds to tens of seconds),
  unlike the rest of the API which responds instantly.
- **Empty states**: no profile yet → onboarding; no settings yet → show
  defaults (GB, Any, no sponsorship requirement) rather than blank fields;
  no jobs yet → prompt to add tracked companies, try "Search the internet",
  or hit "Refresh jobs now"; no CV yet → tailoring button disabled with a
  tooltip pointing at Profile.
- Don't let the two "search" actions blur together in the UI: **Refresh**
  (standing sources, daily-scheduled, no query needed) and **Search the
  internet** (on-demand, needs a typed query) do genuinely different
  things and should look different, not just be two buttons side by side
  with similar labels.

## What NOT to build

- No login/signup screen — it's single-user, API-key only.
- No "auto-apply" button that submits anything on an external site. The
  furthest this app goes is generating documents and letting the user mark
  a job applied after they've done it themselves.
- No in-app payment/API-key entry for Adzuna/Jooble/SerpApi/Anthropic —
  those are backend `.env` values, not something the frontend collects.
- Don't build sponsorship as a single yes/no field — it's genuinely two
  separate signals (description wording vs. official register match) and
  collapsing them into one loses information the user asked for.
