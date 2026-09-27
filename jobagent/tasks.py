"""Run `python -m jobagent ...` commands in the background for the dashboard.

One task at a time (they share your Claude usage and the browser profile). Output goes to
data/logs/<timestamp>_<name>.log; data/task.json records the current task so the dashboard
can show it even after a page reload or a dashboard restart.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from jobagent.config import DATA_DIR, ROOT

LOG_DIR = DATA_DIR / "logs"
STATE = DATA_DIR / "task.json"
CONTROL = DATA_DIR / "apply_control.txt"   # dashboard -> running `apply-one` browser session


def _alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True,
                         creationflags=subprocess.CREATE_NO_WINDOW)
    return str(pid) in out.stdout


def current() -> dict | None:
    """The running task, or the last finished one (with running=False)."""
    if not STATE.exists():
        return None
    try:
        t = json.loads(STATE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    t["running"] = _alive(t["pid"]) if t.get("running") else False
    if not t["running"] and t.get("ended") is None:
        t["ended"] = datetime.now().isoformat(timespec="seconds")
        STATE.write_text(json.dumps(t), encoding="utf-8")
    return t


def start(label: str, *args: str) -> dict:
    t = current()
    if t and t["running"]:
        raise RuntimeError(f"'{t['label']}' is still running - wait for it or stop it first.")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log = LOG_DIR / f"{stamp}_{args[0]}.log"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1",
           "NO_COLOR": "1", "COLUMNS": "140", "TERM": "dumb"}
    with log.open("w", encoding="utf-8") as fh:
        proc = subprocess.Popen(
            [sys.executable, "-m", "jobagent", *args], cwd=ROOT, env=env,
            stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    t = {"label": label, "args": list(args), "pid": proc.pid, "log": str(log), "running": True,
         "started": datetime.now().isoformat(timespec="seconds"), "ended": None}
    STATE.write_text(json.dumps(t), encoding="utf-8")
    return t


def stop() -> None:
    t = current()
    if t and t["running"]:
        # /T also ends child processes (browser, Claude CLI).
        subprocess.run(["taskkill", "/PID", str(t["pid"]), "/T", "/F"], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        with open(t["log"], "a", encoding="utf-8") as fh:
            fh.write("\n[stopped from dashboard]\n")


def read_log(path: str, max_chars: int = 30000) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:]


def send_apply_command(cmd: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONTROL.write_text(cmd, encoding="utf-8")
