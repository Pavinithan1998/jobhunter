"""
Relevance scoring.

Two stages, to keep LLM calls (and cost) down:
  1. Cheap keyword/settings pre-filter (exclude/must-have keywords, excluded
     companies, remote-only, visa-sponsorship-required). Anything that fails
     this never reaches the LLM and is marked dismissed automatically with a
     reasoning string explaining why.
  2. An LLM pass (Claude) that reads the CV + job description and returns a
     0-100 relevance score, a short human-readable reason, AND a refined
     visa-sponsorship assessment (overwriting the fast keyword heuristic
     applied at fetch time with a fuller read of the whole description).
"""
import json
import logging
from typing import List, Optional

from sqlmodel import Session, select

from app.models import JobListing, JobStatus, Profile, SearchSettings, SponsorshipStatus, WorkMode
from app.schemas import ScoreResult
from app.services.llm_client import LLMNotConfigured, get_client, get_model

logger = logging.getLogger("jobhunter.matching")

SCORING_PROMPT = """You are helping a job seeker triage job listings. Score how well \
this specific job matches their CV and stated preferences, and separately assess \
whether the employer is likely to sponsor a work visa.

--- CANDIDATE CV ---
{cv_text}

--- CANDIDATE PREFERENCES ---
Target titles: {target_titles}
Target locations: {target_locations}
Remote preference: {remote_preference}
Seniority: {seniority}
Salary range: {salary_range}

--- JOB LISTING ---
Title: {title}
Company: {company}
Location: {location}
Remote: {remote}
Salary: {salary}
Description:
{description}

Score the fit from 0-100, where 100 means an excellent, apply-immediately match,
and 0 means completely unrelated to this candidate's background. Consider actual
skill/experience overlap, not just title similarity. Be honest and a little
critical -- the candidate would rather skip a bad match than waste time applying.

Separately, read the description for any signal about visa/work-authorization
sponsorship. Classify it as "likely" (sponsorship mentioned as available or
implied, e.g. mentions of a licensed sponsor or skilled worker visa support),
"unlikely" (explicitly requires existing right to work, or says sponsorship is
not offered), or "unclear" (not mentioned either way -- this is the most common
case, since most listings don't mention it).

Respond with ONLY a JSON object, no other text, in exactly this shape:
{{
  "score": <integer 0-100>,
  "reasoning": "<one or two sentences, plain and specific>",
  "visa_sponsorship": "<likely|unlikely|unclear>",
  "visa_sponsorship_reasoning": "<one sentence citing what in the text supports this, or noting it wasn't mentioned>"
}}
"""


def _keyword_prefilter(job: JobListing, profile: Profile, settings_row: Optional[SearchSettings]) -> Optional[str]:
    """Return a rejection reason string if the job should be auto-dismissed, else None."""
    text = f"{job.title} {job.description}".lower()

    exclude = [k.strip().lower() for k in (profile.exclude_keywords or "").split(",") if k.strip()]
    for kw in exclude:
        if kw in text:
            return f"Auto-dismissed: contains excluded keyword '{kw}'."

    must_have = [k.strip().lower() for k in (profile.must_have_keywords or "").split(",") if k.strip()]
    if must_have and not any(kw in text for kw in must_have):
        return f"Auto-dismissed: missing all required keywords ({', '.join(must_have)})."

    if settings_row:
        excluded_companies = [
            c.strip().lower() for c in (settings_row.excluded_companies or "").split(",") if c.strip()
        ]
        if excluded_companies and job.company.strip().lower() in excluded_companies:
            return f"Auto-dismissed: '{job.company}' is on your excluded companies list."

        if settings_row.work_mode != WorkMode.any and job.work_mode != WorkMode.unclear:
            if job.work_mode != settings_row.work_mode:
                return f"Auto-dismissed: settings require {settings_row.work_mode.value}-only and this job is {job.work_mode.value}."

        if settings_row.require_sponsorship and job.sponsorship_status == SponsorshipStatus.unlikely:
            return "Auto-dismissed: settings require visa sponsorship and this job's listing suggests it won't."

        target_countries = [
            c.strip().upper() for c in (settings_row.target_countries or "").split(",") if c.strip()
        ]
        if target_countries and job.country and job.country.upper() not in target_countries:
            return f"Auto-dismissed: job is in {job.country}, outside your target countries ({', '.join(target_countries)})."

    return None


def score_job(job: JobListing, profile: Profile) -> tuple[float, str, SponsorshipStatus, str]:
    client = get_client()
    salary_range = ""
    if profile.min_salary or profile.max_salary:
        salary_range = f"{profile.min_salary or '?'} - {profile.max_salary or '?'} {profile.currency}"

    prompt = SCORING_PROMPT.format(
        cv_text=profile.cv_raw_text[:6000] or "(no CV uploaded yet)",
        target_titles=profile.target_titles or "(none specified)",
        target_locations=profile.target_locations or "(none specified)",
        remote_preference=profile.remote_preference,
        seniority=profile.seniority or "(not specified)",
        salary_range=salary_range or "(not specified)",
        title=job.title,
        company=job.company,
        location=job.location,
        remote=job.remote,
        salary=job.salary_text or "(not listed)",
        description=job.description[:4000],
    )

    response = client.messages.create(
        model=get_model(),
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    raw_text = "".join(block.text for block in response.content if block.type == "text").strip()

    try:
        parsed = json.loads(raw_text)
        sponsorship_value = str(parsed.get("visa_sponsorship", "unclear")).lower()
        if sponsorship_value not in (s.value for s in SponsorshipStatus):
            sponsorship_value = "unclear"
        return (
            float(parsed["score"]),
            str(parsed["reasoning"]),
            SponsorshipStatus(sponsorship_value),
            str(parsed.get("visa_sponsorship_reasoning", "")),
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        logger.warning("Could not parse LLM scoring response: %r", raw_text)
        return 0.0, "Could not parse model response; treat as unscored.", SponsorshipStatus.unclear, ""


def score_pending_jobs(session: Session, limit: int = 100) -> ScoreResult:
    profile = session.exec(select(Profile)).first()
    if profile is None:
        return ScoreResult(scored=0, errors=["No profile set up yet. POST /api/profile first."])

    settings_row = session.exec(select(SearchSettings)).first()

    pending: List[JobListing] = session.exec(
        select(JobListing).where(JobListing.status == JobStatus.new).limit(limit)
    ).all()

    scored_count = 0
    errors: List[str] = []

    for job in pending:
        rejection_reason = _keyword_prefilter(job, profile, settings_row)
        if rejection_reason:
            job.status = JobStatus.dismissed
            job.relevance_score = 0
            job.relevance_reasoning = rejection_reason
            session.add(job)
            scored_count += 1
            continue

        try:
            score, reasoning, sponsorship_status, sponsorship_reasoning = score_job(job, profile)
        except LLMNotConfigured as exc:
            errors.append(str(exc))
            break  # no point retrying every job if the key just isn't set
        except Exception as exc:  # noqa: BLE001
            logger.exception("Scoring failed for job %s", job.id)
            errors.append(f"Job {job.id}: {exc}")
            continue

        job.relevance_score = score
        job.relevance_reasoning = reasoning
        job.sponsorship_status = sponsorship_status
        if sponsorship_reasoning:
            job.sponsorship_reasoning = sponsorship_reasoning
        job.status = JobStatus.scored
        session.add(job)
        scored_count += 1

    session.commit()
    return ScoreResult(scored=scored_count, errors=errors)
