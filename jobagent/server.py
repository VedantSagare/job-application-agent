"""HTTP API for the React dashboard (web/). Serves the built app from web/dist too.

Run: python -m jobagent web   (or double-click "Job Agent Dashboard.bat")
Long operations run as background tasks (see tasks.py); the UI polls /api/task for live progress.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from ruamel.yaml import YAML

from jobagent import db, tasks
from jobagent.config import BASE_RESUME_PDF, CONFIG_PATH, MASTER_RESUME_JSON, PROFILE_DIR, ROOT, load_config

app = FastAPI(title="Job agent")
yaml = YAML()  # round-trip: keeps the comments in config.yaml
yaml.width = 120

STATUSES = ["new", "scored", "tailored", "applied", "skipped", "dismissed", "error"]
LIST_FIELDS = ("id", "source", "company", "title", "location", "status", "score", "url", "apply_url",
               "posted_at", "discovered_at", "applied_at")


def _job_summary(r) -> dict[str, Any]:
    d = {k: r[k] for k in LIST_FIELDS}
    d["has_resume"] = bool(r["resume_path"]) and Path(r["resume_path"]).exists()
    return d


def _require(job_id: str):
    job = db.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


def _start(label: str, *args: str) -> dict:
    try:
        return tasks.start(label, *args)
    except RuntimeError as e:
        raise HTTPException(409, str(e))


# ---------------------------------------------------------------- jobs

@app.get("/api/stats")
def stats() -> dict:
    counts = Counter(r["status"] for r in db.all_jobs())
    return {"total": sum(counts.values()), **{s: counts.get(s, 0) for s in STATUSES},
            "has_resume": MASTER_RESUME_JSON.exists()}


@app.get("/api/jobs")
def list_jobs() -> list[dict]:
    return [_job_summary(r) for r in db.all_jobs()]


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: str) -> dict:
    r = _require(job_id)
    d = _job_summary(r)
    d["description"] = r["description"]
    d["error"] = r["error"]
    d["match"] = json.loads(r["match_json"]) if r["match_json"] else None
    d["changes"] = json.loads(r["changes_json"]) if r["changes_json"] else []
    cover = Path(r["cover_path"]) if r["cover_path"] else None
    d["cover_letter"] = cover.read_text(encoding="utf-8") if cover and cover.exists() else None
    d["resume_file"] = Path(r["resume_path"]).name if d["has_resume"] else None
    return d


class StatusBody(BaseModel):
    status: str


@app.post("/api/jobs/{job_id}/status")
def set_status(job_id: str, body: StatusBody) -> dict:
    job = _require(job_id)
    if body.status not in STATUSES:
        raise HTTPException(400, "Unknown status")
    extra = {"applied_at": db.now()} if body.status == "applied" else {}
    if body.status == "scored" and job["resume_path"]:
        body.status = "tailored"
    db.update(job_id, status=body.status, error=None, **extra)
    return {"ok": True}


@app.get("/api/jobs/{job_id}/resume.pdf")
def resume_pdf(job_id: str):
    r = _require(job_id)
    if not r["resume_path"] or not Path(r["resume_path"]).exists():
        raise HTTPException(404, "No tailored resume")
    p = Path(r["resume_path"])
    return FileResponse(p, media_type="application/pdf", filename=p.name, content_disposition_type="inline")


@app.get("/api/jobs/{job_id}/cover.pdf")
def cover_pdf(job_id: str):
    r = _require(job_id)
    p = Path(r["cover_path"]).with_suffix(".pdf") if r["cover_path"] else None
    if not p or not p.exists():
        raise HTTPException(404, "No cover letter")
    return FileResponse(p, media_type="application/pdf", filename=p.name, content_disposition_type="inline")


@app.post("/api/jobs/{job_id}/open-folder")
def open_folder(job_id: str) -> dict:
    r = _require(job_id)
    if not r["resume_path"]:
        raise HTTPException(404, "No tailored resume")
    os.startfile(str(Path(r["resume_path"]).parent))  # type: ignore[attr-defined]  (runs on your PC)
    return {"ok": True}


# ---------------------------------------------------------------- operations (background tasks)

class SearchBody(BaseModel):
    keywords: list[str]
    locations: list[str]
    sources: list[str]            # subset of companies, linkedin, naukri
    max_age_days: int = 14
    score_limit: int = 0          # 0 = find only
    tailor_limit: int = 0


@app.post("/api/search")
def search(body: SearchBody) -> dict:
    if not body.sources:
        raise HTTPException(400, "Pick at least one source")
    if {"linkedin", "naukri"} & set(body.sources) and not body.keywords:
        raise HTTPException(400, "Add at least one keyword for LinkedIn/Naukri")
    # Remember the search so the next visit (and CLI runs) start from it.
    doc = _load_yaml()
    doc["search"]["keywords"] = body.keywords
    doc["search"]["locations"] = body.locations
    doc["search"]["max_age_days"] = body.max_age_days
    _save_yaml(doc)
    names = {"companies": "career sites", "linkedin": "LinkedIn", "naukri": "Naukri"}
    label = "Search " + ", ".join(names.get(s, s) for s in body.sources)
    return _start(label, "search", "--sources", ",".join(body.sources),
                  "--score-limit", str(body.score_limit), "--tailor-limit", str(body.tailor_limit))


class LimitBody(BaseModel):
    limit: int = 30


@app.post("/api/score")
def score(body: LimitBody) -> dict:
    return _start(f"Score {body.limit} jobs", "score", "--limit", str(body.limit))


@app.post("/api/tailor")
def tailor(body: LimitBody) -> dict:
    return _start(f"Tailor {body.limit} resumes", "tailor", "--limit", str(body.limit))


@app.post("/api/jobs/{job_id}/score")
def score_one(job_id: str) -> dict:
    j = _require(job_id)
    return _start(f"Score: {j['company']} - {j['title']}", "score", "--job", job_id)


@app.post("/api/jobs/{job_id}/tailor")
def tailor_one(job_id: str) -> dict:
    j = _require(job_id)
    return _start(f"Tailor: {j['company']} - {j['title']}", "tailor", "--job", job_id)


class ApplyBody(BaseModel):
    tailor: bool = False  # tailor the resume first, then auto-fill


@app.post("/api/jobs/{job_id}/apply")
def apply_one(job_id: str, body: ApplyBody | None = None) -> dict:
    j = _require(job_id)
    if not MASTER_RESUME_JSON.exists():
        raise HTTPException(400, "Upload your resume first (My resume page)")
    tailor = bool(body and body.tailor)
    label = ("Tailor & apply: " if tailor else "Apply: ") + f"{j['company']} - {j['title']}"
    return _start(label, "apply-one", job_id, *(["--tailor"] if tailor else []))


class ApplyCommand(BaseModel):
    command: str  # fill | close


@app.post("/api/apply/command")
def apply_command(body: ApplyCommand) -> dict:
    if body.command not in ("fill", "close"):
        raise HTTPException(400, "Unknown command")
    tasks.send_apply_command(body.command)
    return {"ok": True}


@app.get("/api/task")
def task() -> dict:
    t = tasks.current()
    if not t:
        return {"task": None, "log": ""}
    return {"task": t, "log": tasks.read_log(t["log"], 20000)}


@app.post("/api/task/stop")
def stop_task() -> dict:
    tasks.stop()
    return {"ok": True}


# ---------------------------------------------------------------- config + resume

def _load_yaml():
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.load(f)


def _save_yaml(doc) -> None:
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        yaml.dump(doc, f)
    load_config.cache_clear()


def _plain(node):
    return json.loads(json.dumps(node, default=list))


@app.get("/api/config")
def get_config() -> dict:
    doc = _load_yaml()
    return {k: _plain(doc.get(k)) for k in ("search", "sources", "applicant", "llm")}


class ConfigBody(BaseModel):
    search: dict[str, Any] = {}
    sources: dict[str, Any] = {}
    applicant: dict[str, Any] = {}
    llm: dict[str, Any] = {}


def _merge(target, updates: dict) -> None:
    """Update the ruamel document in place so comments survive."""
    for k, v in updates.items():
        if isinstance(v, dict) and k in target and isinstance(target[k], dict):
            _merge(target[k], v)
        else:
            target[k] = v


@app.put("/api/config")
def put_config(body: ConfigBody) -> dict:
    doc = _load_yaml()
    for section in ("search", "sources", "applicant", "llm"):
        _merge(doc[section], getattr(body, section))
    _save_yaml(doc)
    return {"ok": True}


@app.get("/api/resume")
def get_resume() -> dict:
    if not MASTER_RESUME_JSON.exists():
        return {"resume": None}
    return {"resume": json.loads(MASTER_RESUME_JSON.read_text(encoding="utf-8")),
            "has_preview": MASTER_RESUME_JSON.with_name("master_preview.pdf").exists(),
            "has_original": BASE_RESUME_PDF.exists()}


@app.get("/api/resume/original.pdf")
def resume_original():
    if not BASE_RESUME_PDF.exists():
        raise HTTPException(404, "No resume uploaded")
    return FileResponse(BASE_RESUME_PDF, media_type="application/pdf", content_disposition_type="inline")


@app.get("/api/resume/preview.pdf")
def resume_preview():
    p = MASTER_RESUME_JSON.with_name("master_preview.pdf")
    if not p.exists():
        raise HTTPException(404, "No preview yet")
    return FileResponse(p, media_type="application/pdf", content_disposition_type="inline")


@app.post("/api/resume/upload")
async def upload_resume(file: UploadFile = File(...)) -> dict:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Please upload a PDF")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    src = BASE_RESUME_PDF
    src.write_bytes(await file.read())
    return _start("Read resume", "parse-resume", str(src))


@app.post("/api/resume/open")
def open_resume_json() -> dict:
    os.startfile(str(MASTER_RESUME_JSON))  # type: ignore[attr-defined]
    return {"ok": True}


# ---------------------------------------------------------------- React app

DIST = ROOT / "web" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
