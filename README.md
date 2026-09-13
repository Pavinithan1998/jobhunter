# JobHunter API

A personal job-search automation backend: it pulls in job listings from
several sources, scores them against your CV and preferences, flags visa
sponsorship signals (including a real check against the UK's public
register of licensed sponsors), and generates a lightly-tailored CV +
cover letter for anything you decide to apply to. You review and submit
each application yourself; the app prepares everything up to that point
and then tracks the outcome.

This is a **backend API only**. It's built so you can point a
[Lovable](https://lovable.dev) (or any other) frontend at it — see
`LOVABLE_FRONTEND_BRIEF.md` for that part, and `API_DOCUMENTATION.md` for
the full endpoint reference.

## Why no database to install

The app uses **SQLite** through SQLModel: a single file
(`storage/jobhunter.db`) that's created automatically on first run. There is
no database server to install, configure, or deploy — the whole app,
including its data, is this one folder. If you outgrow SQLite later, the
`DATABASE_URL` setting is the only thing you'd need to change to point at
Postgres or similar.

## What it does

- **Fetches jobs** from Adzuna, Jooble, and any Greenhouse/Lever company
  boards you tell it to track (daily, on a schedule) — plus an on-demand
  **internet-wide search** (`POST /api/jobs/search-web`, via SerpApi's
  Google Jobs engine) and a manual-entry endpoint for anything you find
  yourself (see the LinkedIn/Indeed note below).
- **Scores every new job 0-100** against your CV and stated preferences
  using an LLM, with a free keyword pre-filter to cut cost on obvious
  non-matches.
- **A Settings page's worth of hard filters**: which country/countries to
  search in (defaults to the UK, switchable to Canada, the US, etc.),
  remote/hybrid/onsite work mode, a visa-sponsorship requirement, and an
  excluded-companies list — all enforced automatically during scoring, not
  just stored as preferences nobody reads.
- **Two independent visa sponsorship signals** on every job: a
  description-language read (does the listing itself mention
  sponsorship?), and — for UK jobs — a lookup against the real, public
  **UK Home Office register of licensed Worker/Temporary Worker
  sponsors**, so you can see whether a company is actually licensed to
  sponsor right now, not just guess from wording.
- **Generates a tailored CV + cover letter** (as real `.docx` files) for
  any job you shortlist — reworded and re-emphasised, never fabricated.
- **Tracks your applications** on a dedicated pipeline: which channel each
  came from (found yourself vs. auto-fetched) and a stage
  (no response → responded → interviewing → offer/rejected), independent
  of the job's broader triage status.
- **Runs on a schedule** (default 6pm daily) so you get an end-of-day
  digest of new, relevant jobs — or trigger it manually any time.

## About LinkedIn and Indeed

There is deliberately no connector that logs into LinkedIn or Indeed to
scrape jobs or submit applications automatically. Neither platform offers a
public API for that, and both prohibit automating the logged-in site in
their terms — doing it anyway risks your account. See
`app/services/sources/base.py` for the full reasoning.

What you get instead: `POST /api/sources/manual-job` lets you paste in a
job's title/company/description/URL from LinkedIn or Indeed, and it flows
through the exact same work-mode classification, sponsorship checks,
scoring, and tailoring pipeline as everything else. You still find the
listing yourself on those two platforms; the app takes over from there.
On the Applications page, anything added this way is tagged
`manual_search` so it's easy to tell apart from jobs the app fetched for
you (`automated_search`).

## Setup

### 1. Install dependencies

Requires Python 3.11+.

```bash
cd jobhunter-api
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Then edit `.env`:

| Variable | Required? | Notes |
|---|---|---|
| `API_KEY` | **Yes** | Any random string. Your frontend sends this on every request. |
| `ANTHROPIC_API_KEY` | Yes, for scoring/tailoring | Get one at console.anthropic.com. Without it, fetching and manual job entry still work (including work-mode and sponsorship-heuristic classification), but LLM-based relevance scoring and document generation return a clear error instead of crashing. |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Optional | Free at developer.adzuna.com. Skipped if blank. |
| `JOOBLE_API_KEY` | Optional | Free at jooble.org/api/about. Skipped if blank. |
| `SERPAPI_KEY` | Optional | Free tier at serpapi.com. Powers `POST /api/jobs/search-web` (on-demand internet-wide search). Without it, that endpoint returns a clear 400 rather than failing oddly. |
| `UK_SPONSOR_REGISTER_CSV_URL` | Optional | Manual override for the UK sponsor register CSV link — only needed if gov.uk restructures their page and auto-discovery breaks. Leave blank normally. |
| `CORS_ORIGINS` | Yes, once you have a frontend | Add your Lovable app's URL here. |

Greenhouse and Lever need no API key — you just tell the app which
companies to track (see `API_DOCUMENTATION.md`).

### 3. Run

```bash
uvicorn app.main:app --reload --port 8000
```

The API is now at `http://localhost:8000`. Interactive docs (auto-generated
from the code, always up to date) are at `http://localhost:8000/docs`, and
the raw OpenAPI schema — useful for feeding into Lovable — is at
`http://localhost:8000/openapi.json`.

### 4. First calls

```bash
# Set up your profile
curl -X POST http://localhost:8000/api/profile \
  -H "X-API-Key: <your key>" -H "Content-Type: application/json" \
  -d '{"full_name":"Your Name","target_titles":"ML Engineer, MLOps Engineer","target_locations":"London, Remote UK","remote_preference":"any"}'

# Upload your master CV
curl -X POST http://localhost:8000/api/profile/cv \
  -H "X-API-Key: <your key>" -F "file=@/path/to/cv.pdf"

# Set your search preferences -- defaults to GB/"any" work mode if you skip this
curl -X POST http://localhost:8000/api/settings \
  -H "X-API-Key: <your key>" -H "Content-Type: application/json" \
  -d '{"target_countries":"gb","work_mode":"any","require_sponsorship":true}'

# Download the UK sponsor register once, so sponsorship checks have data to match against
curl -X POST http://localhost:8000/api/sources/uk-sponsor-register/refresh -H "X-API-Key: <your key>"

# Track some companies (Greenhouse/Lever, no key needed)
curl -X POST http://localhost:8000/api/sources/greenhouse \
  -H "X-API-Key: <your key>" -H "Content-Type: application/json" \
  -d '{"slug":"stripe","display_name":"Stripe"}'

# Fetch + score right now (instead of waiting for the daily schedule)
curl -X POST http://localhost:8000/api/jobs/fetch -H "X-API-Key: <your key>"
curl -X POST http://localhost:8000/api/jobs/score-batch -H "X-API-Key: <your key>"

# See today's relevant jobs
curl http://localhost:8000/api/jobs/digest/today -H "X-API-Key: <your key>"
```

### 5. Run the test suite

64 tests cover auth, profile/CV upload+parsing, job filtering, settings-
driven auto-dismissal (country/work-mode/sponsorship/excluded companies),
the UK sponsor register (mocked download + matching), the applications
pipeline (stage + channel tracking), document-tailoring error handling,
and the dashboard — all against a temporary throwaway database, never your
real `storage/jobhunter.db`.

```bash
pip install -r requirements.txt   # pytest is already in there
pytest -v
```

## Deploying it so Lovable can reach it

Lovable builds and hosts your frontend; it needs a live URL for this
backend to call. Three ways to run it, easiest first:

1. **Render, using the included blueprint** — push this folder to a GitHub
   repo, then in Render: New → Blueprint → point it at the repo. It reads
   `render.yaml` and provisions the service (including a persistent disk
   for the SQLite file) automatically. You just fill in the secret env
   vars (`API_KEY`, `ANTHROPIC_API_KEY`, etc.) in the dashboard afterward.
2. **Any Docker host (Railway, Fly.io, a VPS)** — the included `Dockerfile`
   builds and runs as-is: `docker build -t jobhunter-api . && docker run
   -p 8000:8000 --env-file .env -v $(pwd)/storage:/app/storage
   jobhunter-api`. Or use `docker compose up --build -d`, which does the
   same thing with a persistent volume already wired up. Whichever
   platform you use, make sure its filesystem (or an attached volume)
   persists across restarts — SQLite (and the cached sponsor register)
   need that to keep your data.
3. **Local + tunnel, for testing only** — `ngrok http 8000` gives you a
   temporary public URL. Fine for trying the frontend against the API,
   not for daily real use since the tunnel dies when your machine sleeps.

Whichever you pick, set `CORS_ORIGINS` in `.env` to your Lovable app's
published URL, and use that same backend URL as the API base in Lovable.
Once it's live, also run `POST /api/sources/uk-sponsor-register/refresh`
once (and roughly weekly after that) so sponsorship lookups have current
data — the app never downloads it automatically on its own.

## Project structure

```
jobhunter-api/
  app/
    main.py            FastAPI app setup, CORS, router registration
    config.py          All settings (reads from .env)
    database.py         SQLite engine/session (the "no server to deploy" part)
    models.py           Database tables (jobs, profile, settings, applications, documents)
    schemas.py           Request/response shapes
    auth.py              API key check
    routers/
      profile.py          Identity + CV
      settings.py          The Settings page: country, work mode, sponsorship, etc.
      sources.py            Tracked companies, manual-job entry, UK sponsor register
      jobs.py                Fetch, on-demand web search, scoring, filtering, digest
      documents.py            Tailored CV/cover-letter generation + download
      applications.py          Apply, application-stage tracking, events
      dashboard.py              Summary counts
    services/
      sources/            One connector per job source (Adzuna, Jooble, Greenhouse,
                           Lever, SerpApi web search)
      aggregator.py        Runs connectors, de-dupes, classifies, saves new jobs
      matching.py           LLM relevance scoring + settings-driven auto-dismiss
      work_mode.py           Heuristic remote/hybrid/onsite classifier
      sponsorship.py          Heuristic sponsorship-language classifier
      uk_sponsor_register.py  Downloads/caches/matches the UK Home Office register
      tailoring.py             CV/cover letter generation (LLM)
      documents.py              Renders tailored content into .docx files
      scheduler.py               Daily automatic fetch+score
    utils/cv_parser.py    Extracts text from uploaded PDF/DOCX/TXT
  storage/
    jobhunter.db              The SQLite database (created on first run)
    documents/                 Generated .docx files
    uploads/                    Your uploaded master CV
    uk_sponsor_register.csv      Cached UK sponsor register (after first refresh)
  API_DOCUMENTATION.md    Full endpoint reference for building a frontend
  LOVABLE_FRONTEND_BRIEF.md   Screen-by-screen brief for Lovable
  tests/                  64 pytest tests, run against a throwaway DB
  Dockerfile              Container build (used by docker-compose and Render)
  docker-compose.yml       Local/VPS run with persistent storage
  render.yaml               One-click-ish Render deployment blueprint
  Procfile                  For Railway/Heroku-style platforms
```
