"""
Generates a lightly-tailored CV and an optional cover letter for a specific
job, using the candidate's real CV as the only source of truth.

The prompt is deliberately strict about NOT inventing skills or experience:
the model may re-order, re-emphasise, and re-word, but every fact must
already exist in the source CV.
"""
import json

from app.models import JobListing, Profile
from app.services.llm_client import get_client, get_model

TAILOR_CV_PROMPT = """You are helping a candidate lightly tailor their CV for a specific job.

STRICT RULES:
- Do NOT invent skills, tools, employers, dates, titles or achievements that are not
  already in the source CV below.
- You MAY reorder bullet points, re-emphasise relevant existing experience, tighten
  wording, and adjust the professional summary so it speaks directly to this job.
- Keep it honest -- this is a light tailoring pass, not a rewrite that changes what is true.
- Keep the same overall structure/sections as the source CV.

--- SOURCE CV ---
{cv_text}

--- TARGET JOB ---
Title: {title}
Company: {company}
Description:
{description}

Return ONLY a JSON object of this exact shape (no extra text):
{{
  "summary": "<2-4 sentence tailored professional summary>",
  "sections": [
    {{"heading": "<section heading, e.g. 'Experience'>", "content": "<tailored section text, plain text with newlines between bullets/entries>"}}
  ],
  "change_notes": "<one or two sentences on what you emphasised/reordered and why>"
}}
"""

COVER_LETTER_PROMPT = """Write a concise, honest cover letter (250-350 words) for this candidate
applying to this specific job. Use only facts present in the CV below -- do not invent
experience. Professional but not stiff; no generic filler like "I am writing to express
my interest". Address why their actual background fits this actual role.

--- CANDIDATE CV ---
{cv_text}

--- CANDIDATE NAME ---
{full_name}

--- TARGET JOB ---
Title: {title}
Company: {company}
Description:
{description}

Return ONLY the cover letter text, no preamble, no markdown formatting, no JSON.
"""


def generate_tailored_cv(job: JobListing, profile: Profile) -> dict:
    client = get_client()
    prompt = TAILOR_CV_PROMPT.format(
        cv_text=profile.cv_raw_text[:8000] or "(no CV uploaded)",
        title=job.title,
        company=job.company,
        description=job.description[:4000],
    )
    response = client.messages.create(
        model=get_model(),
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw_text = "".join(b.text for b in response.content if b.type == "text").strip()
    return json.loads(raw_text)


def generate_cover_letter(job: JobListing, profile: Profile) -> str:
    client = get_client()
    prompt = COVER_LETTER_PROMPT.format(
        cv_text=profile.cv_raw_text[:8000] or "(no CV uploaded)",
        full_name=profile.full_name or "the candidate",
        title=job.title,
        company=job.company,
        description=job.description[:4000],
    )
    response = client.messages.create(
        model=get_model(),
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in response.content if b.type == "text").strip()
