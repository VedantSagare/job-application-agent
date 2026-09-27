"""SQLite job tracker. One row per job; `status` moves through the pipeline:

new -> scored | skipped -> tailored -> applied | dismissed   (error on failures)
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from jobagent.config import DATA_DIR

DB_PATH = DATA_DIR / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    source        TEXT NOT NULL,          -- greenhouse | lever | ashby | linkedin | naukri
    company       TEXT NOT NULL,
    title         TEXT NOT NULL,
    location      TEXT,
    url           TEXT NOT NULL,          -- job posting page
    apply_url     TEXT,                   -- where the application form lives
    description   TEXT,
    posted_at     TEXT,
    status        TEXT NOT NULL DEFAULT 'new',
    score         INTEGER,
    match_json    TEXT,
    resume_path   TEXT,
    cover_path    TEXT,
    changes_json  TEXT,
    error         TEXT,
    notes         TEXT,
    discovered_at TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    applied_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_dedupe ON jobs(company, title);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def job_id(source: str, external_id: str) -> str:
    return hashlib.sha1(f"{source}:{external_id}".encode()).hexdigest()[:16]


@dataclass
class Job:
    source: str
    external_id: str
    company: str
    title: str
    url: str
    location: str | None = None
    apply_url: str | None = None
    description: str | None = None
    posted_at: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return job_id(self.source, self.external_id)


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert_jobs(jobs: Iterable[Job]) -> int:
    """Insert new jobs; skip ones already stored or duplicated across sources. Returns # inserted."""
    inserted = 0
    with connect() as conn:
        for j in jobs:
            if conn.execute("SELECT 1 FROM jobs WHERE id = ?", (j.id,)).fetchone():
                continue
            # Same company + title seen from another source (e.g. LinkedIn mirror of a Greenhouse post).
            dup = conn.execute(
                "SELECT 1 FROM jobs WHERE lower(company) = lower(?) AND lower(title) = lower(?)",
                (j.company, j.title),
            ).fetchone()
            if dup:
                continue
            ts = now()
            conn.execute(
                """INSERT INTO jobs (id, source, company, title, location, url, apply_url,
                   description, posted_at, discovered_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (j.id, j.source, j.company, j.title, j.location, j.url, j.apply_url or j.url,
                 j.description, j.posted_at, ts, ts),
            )
            inserted += 1
    return inserted


def update(job_id_: str, **fields: Any) -> None:
    for k, v in list(fields.items()):
        if isinstance(v, (dict, list)):
            fields[k] = json.dumps(v)
    fields["updated_at"] = now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    with connect() as conn:
        conn.execute(f"UPDATE jobs SET {cols} WHERE id = ?", (*fields.values(), job_id_))


def get(job_id_: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id_,)).fetchone()


def by_status(*statuses: str, order: str = "score DESC, discovered_at DESC") -> list[sqlite3.Row]:
    q = ",".join("?" * len(statuses))
    with connect() as conn:
        return conn.execute(
            f"SELECT * FROM jobs WHERE status IN ({q}) ORDER BY {order}", statuses
        ).fetchall()


def all_jobs() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute("SELECT * FROM jobs ORDER BY discovered_at DESC").fetchall()
