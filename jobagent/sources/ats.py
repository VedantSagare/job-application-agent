"""Company career portals via the public job-board APIs of common ATSs (no scraping, no login)."""
from __future__ import annotations

import html
from datetime import datetime, timezone

import httpx

from jobagent.db import Job
from jobagent.sources import ats_more
from jobagent.sources.common import html_to_text, log


def greenhouse(slug: str, http: httpx.Client) -> list[Job]:
    r = http.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", params={"content": "true"})
    r.raise_for_status()
    jobs = []
    for j in r.json().get("jobs", []):
        jobs.append(Job(
            source="greenhouse",
            external_id=f"{slug}:{j['id']}",
            company=j.get("company_name") or slug.title(),
            title=j["title"].strip(),
            location=(j.get("location") or {}).get("name"),
            url=j["absolute_url"],
            # The embeddable form never redirects to the company's own careers site
            # (the regular job-boards page often does), so the form is always on the page.
            apply_url=f"https://job-boards.greenhouse.io/embed/job_app?for={slug}&token={j['id']}",
            description=html_to_text(html.unescape(j.get("content") or "")),
            posted_at=j.get("first_published") or j.get("updated_at"),
        ))
    return jobs


def lever(slug: str, http: httpx.Client) -> list[Job]:
    r = http.get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
    r.raise_for_status()
    jobs = []
    for j in r.json():
        parts = [j.get("descriptionPlain") or ""]
        for lst in j.get("lists", []):
            parts.append(f"{lst.get('text', '')}\n{html_to_text(lst.get('content', ''))}")
        parts.append(j.get("additionalPlain") or "")
        created = j.get("createdAt")
        jobs.append(Job(
            source="lever",
            external_id=f"{slug}:{j['id']}",
            company=slug.title(),
            title=j["text"].strip(),
            location=(j.get("categories") or {}).get("location"),
            url=j["hostedUrl"],
            apply_url=j.get("applyUrl") or j["hostedUrl"] + "/apply",
            description="\n\n".join(p for p in parts if p.strip()),
            posted_at=datetime.fromtimestamp(created / 1000, timezone.utc).isoformat() if created else None,
        ))
    return jobs


def ashby(slug: str, http: httpx.Client) -> list[Job]:
    r = http.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    r.raise_for_status()
    jobs = []
    for j in r.json().get("jobs", []):
        if not j.get("isListed", True):
            continue
        locs = [j.get("location")] + [s.get("location") for s in j.get("secondaryLocations") or []]
        jobs.append(Job(
            source="ashby",
            external_id=f"{slug}:{j['id']}",
            company=slug.title(),
            title=j["title"].strip(),
            location=" / ".join(l for l in locs if l),
            url=j["jobUrl"],
            apply_url=j.get("applyUrl") or j["jobUrl"] + "/application",
            description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml") or ""),
            posted_at=j.get("publishedAt"),
        ))
    return jobs


FETCHERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}
# These search each company with your keywords (big employers list thousands of roles).
KEYWORD_FETCHERS = {"workday": ats_more.workday, "smartrecruiters": ats_more.smartrecruiters,
                    "workable": ats_more.workable}
ALL_ATS = {**FETCHERS, **KEYWORD_FETCHERS}


def fetch_companies(companies: dict[str, list[str]], http: httpx.Client,
                    keywords: list[str] | None = None) -> list[Job]:
    out: list[Job] = []
    for ats, slugs in (companies or {}).items():
        if ats == "portals":
            continue  # handled by sources/portals.py
        fetch = FETCHERS.get(ats)
        keyword_fetch = KEYWORD_FETCHERS.get(ats)
        if not fetch and not keyword_fetch:
            log.warning(f"Unknown ATS '{ats}' in config (supported: {', '.join(ALL_ATS)})")
            continue
        for slug in slugs or []:
            try:
                if keyword_fetch:
                    jobs = keyword_fetch(slug, http, keywords or [])
                    log.info(f"{ats}/{slug}: {len(jobs)} matching roles")
                else:
                    jobs = fetch(slug, http)
                    log.info(f"{ats}/{slug}: {len(jobs)} open roles")
                out.extend(jobs)
            except httpx.HTTPStatusError as e:
                log.warning(f"{ats}/{slug}: HTTP {e.response.status_code} - check the board name / careers URL")
            except ValueError as e:
                log.warning(f"{ats}/{slug}: {e}")
            except httpx.HTTPError as e:
                log.warning(f"{ats}/{slug}: {e}")
    return out
