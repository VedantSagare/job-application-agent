"""Score each new job against the master resume and skip poor fits."""
from __future__ import annotations

from jobagent import db
from jobagent.config import cfg
from jobagent.llm import LLMError, structured
from jobagent.models import MatchResult, Resume
from jobagent.sources.common import log

SCORE_SYSTEM = """You screen jobs for one candidate and rate how well they fit, as a strict but fair recruiter would.

Scoring guide:
- 85-100: meets essentially all must-haves; strong interview chance.
- 70-84: meets most must-haves; worth applying.
- 50-69: notable gaps (years of experience, core stack, domain) - long shot.
- 0-49: wrong role, level, or location/work-authorization mismatch.
Treat hard requirements (years of experience, required degree, location/visa, must-have tech) as decisive.
Judge only from the resume; do not assume skills it doesn't show.

Candidate facts beyond the resume:
{facts}

<resume>
{resume}
</resume>"""


def _priority(job) -> int:
    """Lower = scored first: jobs matching search.priority_locations, in list order."""
    loc = f"{job['location'] or ''} {job['source']}".lower()
    prefs = [p.lower() for p in cfg("search.priority_locations", [])]
    return next((i for i, p in enumerate(prefs) if p in loc), len(prefs))


def score_new(master: Resume, limit: int | None = None, job_id: str | None = None) -> None:
    if job_id:
        jobs = [j for j in [db.get(job_id)] if j]
    else:
        from jobagent import prefit
        prefit.update()
        # Best estimated fit first (then preferred locations), so a limited run scores the most promising jobs.
        jobs = sorted(db.by_status("new", order="discovered_at DESC"),
                      key=lambda j: (-(j["prefit"] or 0), _priority(j)))[:limit]
    if not jobs:
        log.info("No new jobs to score.")
        return
    threshold = cfg("search.min_match_score", 70)
    facts = "\n".join(f"- {k}: {v}" for k, v in (cfg("applicant", {}) or {}).items() if v)
    system = SCORE_SYSTEM.format(facts=facts, resume=master.model_dump_json(indent=1))
    for i, job in enumerate(jobs, 1):
        try:
            m = structured(
                MatchResult,
                system=system,
                content=(f"Company: {job['company']}\nRole: {job['title']}\nLocation: {job['location']}\n\n"
                         f"<job_description>\n{job['description']}\n</job_description>"),
                effort=cfg("llm.score_effort", "low"),
                max_tokens=4000,
            )
        except LLMError as e:
            db.update(job["id"], status="error", error=str(e))
            log.error(f"[{i}/{len(jobs)}] {job['company']} - {job['title']}: {e}")
            continue
        status = "scored" if m.score >= threshold and m.verdict != "skip" else "skipped"
        db.update(job["id"], status=status, score=m.score, match_json=m.model_dump())
        log.info(f"[{i}/{len(jobs)}] {m.score:>3}  {status:<8} {job['company']} - {job['title']}")
