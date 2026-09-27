"""Shared Playwright setup: a persistent Chrome (or Edge) profile so logins (LinkedIn, Naukri) survive runs."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from playwright.sync_api import BrowserContext, sync_playwright

from jobagent.config import ROOT, cfg


@contextmanager
def browser_context(headless: bool = False) -> Iterator[BrowserContext]:
    profile = ROOT / cfg("browser.profile_dir", ".browser_profile")
    profile.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(profile),
            channel=cfg("browser.channel", "chrome"),
            headless=headless,
            viewport=None,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
        )
        try:
            yield ctx
        finally:
            ctx.close()


@contextmanager
def pdf_page() -> Iterator:
    """Headless page used only for rendering HTML resumes to PDF."""
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=cfg("browser.channel", "chrome"), headless=True)
        try:
            yield browser.new_page()
        finally:
            browser.close()
