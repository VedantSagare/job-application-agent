"""Discovery: pull jobs from every enabled source, filter by title/location, store new ones."""
from __future__ import annotations

import re

import httpx

from jobagent import db
from jobagent.config import cfg
from jobagent.db import Job
from jobagent.sources import ats, linkedin
from jobagent.sources.common import USER_AGENT, log
from jobagent.sources.location import keep_location


def _keep(job: Job) -> bool:
    if not keep_location(job.location, job.source, cfg("search.location_mode", "any")):
        return False
    title = job.title.lower()
    if any(x.lower() in title for x in cfg("search.title_exclude", [])):
        return False
    # Keyword searches (LinkedIn/Naukri) are already targeted; career portals list every role.
    if job.source in ats.FETCHERS:
        must = [x.lower() for x in cfg("search.title_must_include", [])]
        if must and not any(x in title for x in must):
            return False
        locs = [x.lower() for x in cfg("search.location_include", [])]
        if locs and not any(x in (job.location or "").lower() for x in locs):
            return False
    return bool(job.description and job.description.strip())


def discover(only: str | None = None) -> int:
    """`only`: None for every enabled source, or a comma-separated subset of
    companies,linkedin,naukri,instahyre."""
    wanted = set(only.split(",")) if only else {"companies", "linkedin", "naukri", "instahyre"}
    keywords = cfg("search.keywords", [])
    locations = cfg("search.locations", [])
    jobs: list[Job] = []

    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True) as http:
        if "companies" in wanted:
            jobs += ats.fetch_companies(cfg("sources.companies", {}), http)
        if "linkedin" in wanted and (only or cfg("sources.linkedin.enabled", True)):
            jobs += linkedin.search(keywords, locations, cfg("sources.linkedin.pages", 1),
                                    cfg("search.max_age_days", 14), http)
        if "instahyre" in wanted and (only or cfg("sources.instahyre.enabled", True)):
            from jobagent.sources import instahyre
            years = cfg("sources.instahyre.years")
            if years in (None, ""):  # default: the experience in your form answers
                m = re.search(r"\d+", str(cfg("applicant.total_experience_years", "")))
                years = int(m.group()) if m else None
            jobs += instahyre.search(cfg("sources.instahyre.skills", []) or keywords,
                                     cfg("sources.instahyre.job_functions", []), years,
                                     cfg("sources.instahyre.pages", 3), http)

    if "naukri" in wanted and (only or cfg("sources.naukri.enabled", True)):
        from jobagent.browser import browser_context
        from jobagent.sources import naukri
        with browser_context() as ctx:
            jobs += naukri.search(keywords, locations, cfg("sources.naukri.pages", 1), ctx)

    kept = [j for j in jobs if _keep(j)]
    inserted = db.upsert_jobs(kept)
    log.info(f"Discovered {len(jobs)} jobs, {len(kept)} passed filters, {inserted} new")
    return inserted
