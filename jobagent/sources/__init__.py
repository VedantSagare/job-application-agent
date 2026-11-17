"""Discovery: pull jobs from every enabled source, filter by title/location, store new ones."""
from __future__ import annotations

import re

import httpx

from jobagent import db
from jobagent.config import cfg
from jobagent.db import Job
from jobagent.sources import ats, linkedin
from jobagent.sources.common import USER_AGENT, log
from jobagent.dates import is_recent
from jobagent.sources.location import keep_location


def _keep(job: Job) -> bool:
    if not keep_location(job.location, job.source, cfg("search.location_mode", "any")):
        return False
    # "Posted within" (search.max_age_days) applies to every source; jobs without a date are kept.
    if not is_recent(job.posted_at, cfg("search.max_age_days")):
        return False
    title = job.title.lower()
    if any(x.lower() in title for x in cfg("search.title_exclude", [])):
        return False
    # Keyword searches (LinkedIn/Naukri) are already targeted; career portals list every role.
    if job.source in ats.ALL_ATS:
        must = [x.lower() for x in cfg("search.title_must_include", [])]
        if must and not any(x in title for x in must):
            return False
        locs = [x.lower() for x in cfg("search.location_include", [])]
        if locs and not any(x in (job.location or "").lower() for x in locs):
            return False
    return bool(job.description and job.description.strip())


def discover(only: str | None = None) -> int:
    """`only`: None for every enabled source, or a comma-separated subset of
    companies,linkedin,naukri,instahyre.

    Each source is saved as soon as it finishes, and a failing source is logged and skipped, so one
    problem (e.g. the Naukri window being closed) never throws away what the other sources found."""
    from jobagent import prefit

    wanted = set(only.split(",")) if only else {"companies", "linkedin", "naukri", "instahyre"}
    keywords = cfg("search.keywords", [])
    locations = cfg("search.locations", [])
    totals = {"found": 0, "kept": 0, "new": 0}

    def save(name: str, fetch) -> None:
        try:
            jobs = fetch()
        except Exception as e:  # noqa: BLE001 - one source failing must not stop the search
            log.warning(f"{name}: failed ({type(e).__name__}: {str(e).splitlines()[0][:150]}) - "
                        "skipping it, other sources continue")
            return
        kept = [j for j in jobs if _keep(j)]
        new = db.upsert_jobs(kept)
        prefit.update()  # quick fit estimate for the new jobs (no Claude call)
        totals["found"] += len(jobs)
        totals["kept"] += len(kept)
        totals["new"] += new
        log.info(f"{name}: {len(jobs)} jobs, {len(kept)} passed filters (incl. posted within "
                 f"{cfg('search.max_age_days') or 'any'} days), {new} new - saved")

    # retries=3: reconnect on brief network drops (DNS / connection errors) instead of skipping a site
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True,
                      transport=httpx.HTTPTransport(retries=3)) as http:
        if "companies" in wanted:
            from jobagent.sources import portals
            save("Company career sites",
                 lambda: ats.fetch_companies(cfg("sources.companies", {}), http, keywords)
                 + portals.fetch_portals(cfg("sources.companies.portals", []), http, keywords))
        if "linkedin" in wanted and (only or cfg("sources.linkedin.enabled", True)):
            save("LinkedIn", lambda: linkedin.search(keywords, locations, cfg("sources.linkedin.pages", 1),
                                                     cfg("search.max_age_days", 14), http))
        if "instahyre" in wanted and (only or cfg("sources.instahyre.enabled", True)):
            from jobagent.sources import instahyre
            years = cfg("sources.instahyre.years")
            if years in (None, ""):  # default: the experience in your form answers
                m = re.search(r"\d+", str(cfg("applicant.total_experience_years", "")))
                years = int(m.group()) if m else None
            save("Instahyre", lambda: instahyre.search(cfg("sources.instahyre.skills", []) or keywords,
                                                       cfg("sources.instahyre.job_functions", []), years,
                                                       cfg("sources.instahyre.pages", 3), http))

    if "naukri" in wanted and (only or cfg("sources.naukri.enabled", True)):
        from jobagent.browser import browser_context
        from jobagent.sources import naukri

        def naukri_jobs():
            with browser_context() as ctx:
                return naukri.search(keywords, locations, cfg("sources.naukri.pages", 1), ctx,
                                     cfg("search.max_age_days"))
        save("Naukri", naukri_jobs)

    log.info(f"Discovered {totals['found']} jobs, {totals['kept']} passed filters, {totals['new']} new")
    return totals["new"]
