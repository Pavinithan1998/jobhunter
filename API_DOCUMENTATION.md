# JobHunter API — Reference

Base URL (local dev): `http://localhost:8000`
Base URL (deployed): whatever host you deploy to (see README.md)

Interactive docs auto-generated from the live code: `GET /docs`
Machine-readable schema (importable into Lovable or any codegen tool): `GET /openapi.json`

This document exists so a frontend can be built **without reading the
backend code** — every endpoint, every field, every status code you'll
actually see.

---

## Authentication

Every endpoint except `/api/health` requires this header on every request:

```
X-API-Key: <the value of API_KEY in the backend's .env>
```

Missing or wrong key → `401 Unauthorized`:
```json
{ "detail": "Invalid or missing API key. Send it as the 'X-API-Key' header." }
```

This is a **single-user app** — there is no login screen, no signup, no
per-user accounts. The frontend should store this one key (e.g. in an env
var at build time, or a settings field the user pastes in once) and attach
it to every request.

## Error format

All errors follow FastAPI's standard shape:

```json
{ "detail": "Human-readable message" }
```

Validation errors (bad request body/params) return `422` with a `detail`
array describing each field problem — this is standard FastAPI/Pydantic
behaviour and shows up automatically if a required field is missing, or an
enum field (like `work_mode` or `application_stage`) gets a value outside
its allowed set.

Common status codes used throughout: `200` success, `400` bad request
(e.g. "no CV uploaded yet"), `401` bad API key, `404` not found, `410` file
gone from disk, `422` validation error, `502` an external fetch (e.g. the
UK sponsor register download) failed.

## CORS

The backend only accepts browser requests from origins listed in its
`CORS_ORIGINS` setting. If your Lovable app's requests fail with a CORS
error in the browser console, add its URL to that setting on the backend
and restart it.

---

## Data model overview

Everything revolves around one **Profile** (identity + CV), one
**SearchSettings** row (search-wide preferences — the Settings page), and
many **JobListing** rows, each of which can have **GeneratedDocument**s
(tailored CV / cover letter) and **ApplicationEvent**s (a timeline: applied,
interview, offer, rejected, stage changes, notes) attached. There's only
ever one Profile row and one SearchSettings row — this is a personal tool,
not a multi-tenant product.

### JobStatus (the coarse triage lifecycle of a job)
```
new → scored → shortlisted → applied → interviewing → offer
                     ↘ dismissed              ↘ rejected
```
- `new`: just fetched, not yet scored
- `scored`: has a relevance_score and relevance_reasoning
- `shortlisted`: you've decided you want to apply
- `dismissed`: not interesting (either you said so, or it failed the
  keyword/settings pre-filter — see `relevance_reasoning` for which)
- `applied` / `interviewing` / `offer` / `rejected`: your actual pipeline
  (kept in sync with the more granular `application_stage` below once a
  job reaches `applied`)

### ApplicationStage (the Applications page's tracking stages)
Set to `no_response` automatically the moment a job is marked applied.
Move it forward yourself as you hear back:
```
no_response → responded → interviewing → offer
                                 ↘ rejected
```
This is separate from `JobStatus` because "applied, but no word yet" is a
real, common state that the coarser status alone can't express. Setting
the stage also updates `JobStatus` where they overlap (`interviewing`,
`offer`, `rejected`); `no_response` and `responded` both keep `JobStatus`
at `applied`.

### ApplicationChannel (derived, not stored)
`manual_search` — you found and pasted this job in yourself.
`automated_search` — the app fetched it (Adzuna, Jooble, Greenhouse, Lever,
or the on-demand web search). Computed from `source`; use it on the
Applications page to separate the two categories the way you'd expect.

### SourceType
`adzuna` | `jooble` | `greenhouse` | `lever` | `manual` | `web_search`

### WorkMode
`remote` | `hybrid` | `onsite` | `unclear` (jobs) — Settings additionally
allows `any` (no filter).

### SponsorshipStatus
`likely` | `unlikely` | `unclear` — a read of the job **description's
wording** (see `sponsorship_reasoning`). Independent of `uk_sponsor_licensed`
below.

### DocType
`cv` | `cover_letter`

---

## Profile

### `GET /api/profile`
Returns the single profile row. **404 if it hasn't been created yet** —
the frontend's first-run flow should POST here before anything else works.

Response `200`:
```json
{
  "full_name": "Your Name",
  "email": "you@example.com",
  "phone": "",
  "location": "Watford, UK",
  "target_titles": "ML Engineer, MLOps Engineer, AI Engineer",
  "target_locations": "London, Hatfield, Remote UK",
  "remote_preference": "any",
  "seniority": "mid",
  "min_salary": 45000,
  "max_salary": 65000,
  "currency": "GBP",
  "must_have_keywords": "python",
  "exclude_keywords": "unpaid, internship",
  "id": 1,
  "cv_filename": "cv.pdf",
  "has_cv": true,
  "updated_at": "2026-09-12T10:00:00"
}
```

### `POST /api/profile`
Creates the profile on first call, updates it on every call after (upsert
— there's only ever one row). All fields optional, but scoring quality
depends on `target_titles` and a CV being uploaded.

Request body: same shape as the response above minus `id`/`cv_filename`/
`has_cv`/`updated_at`. `remote_preference` must be one of: `remote`,
`hybrid`, `onsite`, `any` — this nudges the LLM's scoring prompt; the
**hard** work-mode filter lives on Settings (below), not here.
`target_titles`, `target_locations`, `must_have_keywords`, `exclude_keywords`
are all comma-separated free text — offer them as tag/chip inputs and join
with commas before sending.

### `POST /api/profile/cv`
Uploads the master CV. `multipart/form-data` with a single field `file`.
Accepts `.pdf`, `.docx`, `.txt`. Parses it to plain text server-side and
stores that text — this is what every scoring/tailoring call actually reads.

Response `200`: the updated profile (`has_cv` now `true`).
`400` if the file extension isn't supported.

### `GET /api/profile/cv/text`
Returns the raw parsed CV text, in case the frontend wants to show/let the
user sanity-check what was extracted.
```json
{ "filename": "cv.pdf", "text": "Your Name\nML Engineer..." }
```
`404` if no CV has been uploaded yet.

---

## Settings — the Settings page

One row, same upsert pattern as Profile. This is where country, work mode,
sponsorship requirement, and the excluded-companies list live — **build a
dedicated screen for this**, separate from the Profile/CV screen.

### `GET /api/settings`
**404 if it hasn't been created yet** — unlike Profile, it's fine to treat
this as optional and let defaults apply (GB, any work mode, no
sponsorship requirement) until the user visits the Settings screen.

Response `200`:
```json
{
  "target_countries": "gb",
  "work_mode": "any",
  "require_sponsorship": true,
  "excluded_companies": "Bad Corp, Some Agency",
  "digest_min_score": 60.0,
  "id": 1,
  "updated_at": "2026-09-12T10:00:00"
}
```

### `POST /api/settings`
Creates on first call, updates after (upsert).

| Field | Type | Default | Notes |
|---|---|---|---|
| `target_countries` | string | `"GB"` | Comma-separated ISO country codes, e.g. `"gb"` or `"gb,ca,us"`. **Defaults to the UK** — this app is UK-sponsorship-first; switching to Canada, the US, etc. is an explicit opt-in. Drives which countries Adzuna is queried for, and gates the UK sponsor-register check (only runs when `gb` is in this list). |
| `work_mode` | enum | `"any"` | `"remote"`, `"hybrid"`, `"onsite"`, or `"any"`. A **hard filter**: during scoring, any job whose classified `work_mode` conflicts with this is auto-dismissed. Jobs classified `unclear` are never auto-dismissed by this filter (see WorkMode above). |
| `require_sponsorship` | bool | `false` | Hard filter: auto-dismisses jobs whose `sponsorship_status` (description-language read) comes back `unlikely`. |
| `excluded_companies` | string | `""` | Comma-separated company names to never show — auto-dismissed on scoring. |
| `digest_min_score` | float | `60.0` | Default relevance threshold for `GET /api/jobs/digest/today` when you don't pass `min_score` explicitly. Range 0-100. |

Build the country field as a multi-select or a comma-tag input seeded with
`"GB"`; build `work_mode` as a segmented control (Remote / Hybrid / Onsite
/ Any).

---

## Job sources

### `GET /api/sources/status`
Tells the frontend which connectors are actually usable right now.
```json
{
  "adzuna": false,
  "jooble": false,
  "greenhouse": "configure via tracked companies (no key needed)",
  "lever": "configure via tracked companies (no key needed)",
  "web_search": true,
  "uk_sponsor_register": false,
  "linkedin": "not supported for auto-fetch/auto-apply -- use /api/sources/manual-job to add a listing by hand",
  "indeed": "not supported for auto-fetch/auto-apply -- use /api/sources/manual-job to add a listing by hand"
}
```
`adzuna`/`jooble`/`web_search`/`uk_sponsor_register` are booleans (key
configured, or register downloaded). `greenhouse`/`lever`/`linkedin`/
`indeed` are always the descriptive strings shown above.

### `GET /api/sources/greenhouse` / `GET /api/sources/lever`
List currently tracked companies for that source.
```json
[
  { "id": 1, "source_type": "greenhouse", "slug": "stripe", "display_name": "Stripe", "active": true, "created_at": "2026-09-12T10:00:00" }
]
```

### `POST /api/sources/greenhouse` / `POST /api/sources/lever`
Add a company to track. The `slug` is the part of the company's public
careers URL — e.g. `boards.greenhouse.io/stripe` → slug `stripe`;
`jobs.lever.co/netflix` → slug `netflix`. Let the user paste either the
slug or the full URL and extract the slug from it.

Request: `{ "slug": "stripe", "display_name": "Stripe" }`
Response `200`: the created `TrackedCompanyOut` object. `400` if that slug
is already tracked for that source.

### `DELETE /api/sources/greenhouse/{company_id}` / `DELETE /api/sources/lever/{company_id}`
Stop tracking a company. Response: `{ "deleted": 1 }`. `404` if not found.

### `POST /api/sources/manual-job`
**This is how LinkedIn/Indeed listings enter the app.** The user finds a
job themselves and pastes its details here.

Request:
```json
{
  "title": "Machine Learning Engineer",
  "company": "Acme Ltd",
  "location": "London, UK",
  "country": "GB",
  "description": "Full job description text, pasted in...",
  "url": "https://www.linkedin.com/jobs/view/12345",
  "salary_text": "£50,000 - £65,000",
  "remote": false
}
```
Only `title`, `company`, and `description` are required. `country` is
optional but drives country filtering and gates the UK sponsor-register
check — worth prompting for it if the user knows it. Response `200`: a
`JobListingOut` (see Jobs section) with `source: "manual"`,
`application_channel: "manual_search"`, and `status: "new"` — work-mode
classification, the sponsorship-language heuristic, and (if applicable)
the UK sponsor-register lookup all run immediately, same as fetched jobs.

### UK Sponsor Register

The UK Home Office publishes a public list of companies licensed to
sponsor Worker/Temporary Worker visas. This app downloads and caches it
locally so `uk_sponsor_licensed` on job listings reflects real data, not a
guess.

#### `POST /api/sources/uk-sponsor-register/refresh`
Downloads the current register and rebuilds the local cache. Run this
periodically (weekly is plenty — the register itself doesn't change
daily). Takes a few seconds.

Response `200`:
```json
{ "downloaded": true, "record_count": 84213, "refreshed_at": "2026-09-12T10:00:00", "source_url": "https://assets.publishing.service.gov.uk/.../register.csv" }
```
`502` if the download failed (e.g. gov.uk restructured their page — see
README's `UK_SPONSOR_REGISTER_CSV_URL` override).

#### `GET /api/sources/uk-sponsor-register/status`
Whether it's been downloaded yet, and when.
```json
{ "downloaded": false, "record_count": 0, "refreshed_at": null, "source_url": null }
```
Show a "Set up sponsorship checking" prompt in Settings when `downloaded`
is `false`.

---

## Jobs

### `POST /api/jobs/fetch`
Triggers an immediate fetch across every configured **standing** source
(Adzuna, Jooble, and any tracked Greenhouse/Lever companies), scoped to
the countries in Settings (defaults to GB). This is what the daily
scheduler runs automatically — call it any time you don't want to wait.

No request body. Response `200`:
```json
{ "fetched": 87, "new": 34, "duplicates": 53, "sources_queried": ["adzuna", "jooble", "greenhouse", "lever"], "errors": [] }
```
`errors` holds one string per source that failed — a failure in one source
never blocks the others; surface these as non-fatal warnings, not a failed
request.

### `POST /api/jobs/search-web`
**On-demand internet-wide search** — this is the "search the internet for
jobs right now" feature, distinct from the standing daily sources above.
Runs a live query through SerpApi's Google Jobs engine (which itself
aggregates LinkedIn, Indeed, Glassdoor, company career pages, and more).
Requires `SERPAPI_KEY`; returns a clean `400` if it's not configured.

Request:
```json
{ "query": "Machine Learning Engineer", "location": "London, UK", "country": "gb", "remote_only": false }
```
Only `query` is required. Response `200`:
```json
{
  "fetched": 12,
  "new": 9,
  "duplicates": 3,
  "scored": 9,
  "jobs": [ /* JobListingOut[] -- the newly created ones */ ],
  "errors": []
}
```
New jobs are de-duplicated and classified (work mode, sponsorship,
UK register) exactly like standing-source jobs. If `ANTHROPIC_API_KEY` is
set and a CV is uploaded, they're **scored immediately** (`scored` count
reflects this) so results come back ready to triage — no separate
`score-batch` call needed for these. Takes a few seconds; show a loading
state.

### `POST /api/jobs/score-batch?limit=100`
Runs relevance scoring (plus the settings-driven auto-dismiss checks) on
every job currently in `new` status (up to `limit`, default 100, max 500).

Response `200`: `{ "scored": 34, "errors": [] }`. If
`ANTHROPIC_API_KEY` isn't configured, `errors` explains that and `scored`
reflects only jobs dismissed by the free keyword/settings pre-filter (LLM
scoring is skipped, not crashed).

### `GET /api/jobs`
The main job list, with filters as query parameters (all optional):

| Param | Type | Meaning |
|---|---|---|
| `status` | string | One of the JobStatus values above |
| `min_score` | number | Only jobs scored ≥ this (0-100) |
| `search` | string | Matches title, company, or description |
| `work_mode` | string | `remote` \| `hybrid` \| `onsite` \| `unclear` |
| `country` | string | ISO country code, e.g. `GB` |
| `sponsorship` | string | `likely` \| `unlikely` \| `unclear` (description-language read) |
| `uk_sponsor_licensed` | bool | `true`/`false` — filter by the UK register match |
| `limit` | int | Default 50, max 500 |
| `offset` | int | For pagination |

Sorted by relevance score (highest first, unscored last), then most
recently fetched. Example:
`GET /api/jobs?work_mode=remote&sponsorship=likely&uk_sponsor_licensed=true`

Response `200`: array of `JobListingOut`:
```json
{
  "id": 42,
  "source": "adzuna",
  "title": "Machine Learning Engineer",
  "company": "Acme Ltd",
  "location": "London, UK",
  "country": "GB",
  "remote": false,
  "work_mode": "hybrid",
  "description": "Full description text...",
  "url": "https://www.adzuna.co.uk/jobs/...",
  "salary_text": "50,000 - 65,000",
  "posted_date": "2026-09-10T00:00:00",
  "status": "scored",
  "relevance_score": 82.0,
  "relevance_reasoning": "Strong match on LangChain/RAG experience and seniority.",
  "sponsorship_status": "unclear",
  "sponsorship_reasoning": "Sponsorship isn't mentioned either way in the listing.",
  "uk_sponsor_licensed": true,
  "uk_sponsor_reasoning": "Exact name match found in the current UK Home Office sponsor register.",
  "application_stage": null,
  "application_channel": "automated_search",
  "fetched_at": "2026-09-12T18:00:03"
}
```
This one payload shape covers every job everywhere in the app (browse
list, digest, applications) — build one job-card component around it.

### `GET /api/jobs/digest/today?min_score=60`
The "end of day, show me what's new and relevant" view — jobs fetched
today, at or above `min_score` (defaults to Settings' `digest_min_score`,
itself defaulting to 60), best first. Also applies Settings' `work_mode`
and `require_sponsorship` filters automatically if set.

```json
{ "date": "2026-09-12", "count": 6, "jobs": [ /* JobListingOut[] */ ] }
```

### `GET /api/jobs/{job_id}`
Single job detail. `404` if not found.

### `PATCH /api/jobs/{job_id}/status`
Move a job through the coarse pipeline manually (e.g. user clicks
"Shortlist" or "Dismiss").

Request: `{ "status": "shortlisted", "notes": "Good fit, apply this week" }`
`notes` is optional — if present, also logged as a timeline note.
Response `200`: the updated `JobListingOut`.

### `DELETE /api/jobs/{job_id}`
Remove a job entirely. Response: `{ "deleted": 42 }`.

---

## Documents (tailored CV & cover letter)

### `POST /api/jobs/{job_id}/tailor`
Generates a tailored CV (and, unless disabled, a cover letter) for this
job from the profile's master CV, as real `.docx` files.

Request: `{ "generate_cover_letter": true }`
Response `200`: array of `GeneratedDocumentOut` (one or two items):
```json
[
  { "id": 5, "job_id": 42, "doc_type": "cv", "content_text": "Tailored summary + notes on what was emphasised...", "download_url": "/api/documents/5/download", "created_at": "2026-09-12T18:05:00" },
  { "id": 6, "job_id": 42, "doc_type": "cover_letter", "content_text": "Full cover letter text...", "download_url": "/api/documents/6/download", "created_at": "2026-09-12T18:05:03" }
]
```
`400` if no master CV has been uploaded yet, or if `ANTHROPIC_API_KEY`
isn't configured. Takes a few seconds (1-2 LLM calls) — show a loading state.

### `GET /api/jobs/{job_id}/documents`
List every document generated for a job so far. Same shape as above.

### `GET /api/documents/{document_id}/download`
Downloads the actual `.docx` file. Use `download_url` from the responses
above. `410` if the file was somehow removed from disk after being recorded.

---

## Applications — the Applications page

Every job that's been applied to lives here, tagged with which **channel**
it came through and its current **stage**.

### `POST /api/jobs/{job_id}/apply?notes=...`
Call this **after** the user has actually submitted the application on the
real site. Sets `status` to `applied` and `application_stage` to
`no_response` (the page's default starting point). The app never submits
anything itself — this just records that it happened.

Response `200`: the updated `JobListingOut`.

### `PATCH /api/jobs/{job_id}/application-stage`
**The dedicated setter for the Applications page.** Moves a job through:
`no_response` → `responded` → `interviewing` → `offer` / `rejected`.

Request: `{ "stage": "interviewing", "notes": "Phone screen Thursday 2pm" }`
`notes` is optional. Response `200`: the updated `JobListingOut` — note
that `status` is kept in sync too (`interviewing`/`offer`/`rejected` stages
set the matching `status`; `no_response`/`responded` both keep `status` at
`applied`). `400` if the job hasn't been marked applied yet — call
`POST .../apply` first.

Build this as the drag targets or the status buttons on the Applications
board: 5 columns (No response, Responded, Interviewing, Offer, Rejected),
this one endpoint moves a card between any of them.

### `POST /api/jobs/{job_id}/events`
Log an event against a job's timeline: `applied`, `interview`, `offer`,
`rejected`, or a free-text `note`. This is the older, coarser sibling of
`application-stage` above (kept for compatibility and for plain notes) —
`interview`/`offer`/`rejected` here also update `application_stage`
correspondingly.

Request: `{ "event_type": "note", "notes": "Recruiter said 2 more weeks" }`
Response `200`: the created `ApplicationEventOut`.

### `GET /api/jobs/{job_id}/events`
Full timeline for one job, oldest first — render as a per-job activity feed.
Stage changes made via `PATCH .../application-stage` appear here too, as
`event_type: "stage_change"`.

### `GET /api/applications?status=applied&stage=interviewing&channel=automated_search`
All jobs currently in the applications pipeline. All three filters are
optional and combine:
- `status` — one JobStatus value; omitting it defaults to all of
  `applied`/`interviewing`/`offer`/`rejected`.
- `stage` — one ApplicationStage value (`no_response`, `responded`,
  `interviewing`, `offer`, `rejected`).
- `channel` — `manual_search` or `automated_search`.

This is the endpoint for the Applications page. Build it as a board with
**channel as a top-level tab or toggle** (Manual / Automated) and
**stage as the columns** within each — every job response already carries
both `application_channel` and `application_stage` so no extra lookups
are needed to render this.

---

## Dashboard

### `GET /api/dashboard/summary`
```json
{
  "total_jobs": 214,
  "by_status": { "new": 12, "scored": 45, "shortlisted": 8, "dismissed": 130, "applied": 15, "interviewing": 3, "offer": 1, "rejected": 0 },
  "new_today": 34,
  "shortlisted_unapplied": 8,
  "applied_last_7_days": 6
}
```

---

## Health

### `GET /api/health`
No auth required. `{ "status": "ok" }`.

---

## Suggested request flow for a frontend

1. On first load: `GET /api/profile`. If `404`, show a setup form → `POST /api/profile`, then prompt for `POST /api/profile/cv`.
2. Settings screen: `GET /api/settings` (fine to 404 and show defaults). Let the user set `target_countries` (defaults to GB), `work_mode`, `require_sponsorship`, `excluded_companies` → `POST /api/settings`. Also surface `GET /api/sources/uk-sponsor-register/status` here with a "Refresh now" button → `POST .../refresh`.
3. Sources screen: `GET /api/sources/status`, let the user add Greenhouse/Lever companies.
4. Home/dashboard: `GET /api/dashboard/summary` + `GET /api/jobs/digest/today`.
5. "Refresh now" button: `POST /api/jobs/fetch` → `POST /api/jobs/score-batch` → re-fetch the digest. A separate "Search the internet" box calls `POST /api/jobs/search-web` directly with a typed query.
6. Job list/browse screen: `GET /api/jobs` with filters (including the new `work_mode`, `country`, `sponsorship`, `uk_sponsor_licensed`); card actions call `PATCH /api/jobs/{id}/status`.
7. Job detail screen: `GET /api/jobs/{id}` — show both sponsorship indicators clearly as separate badges (description-language vs. UK register match). "Tailor documents" button → `POST /api/jobs/{id}/tailor`.
8. After the user actually applies elsewhere: `POST /api/jobs/{id}/apply`.
9. Applications page: `GET /api/applications` with `channel`/`stage` filters; a 5-column board per channel, cards moved via `PATCH /api/jobs/{id}/application-stage`.
