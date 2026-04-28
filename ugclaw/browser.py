"""
browser.py — real browser automation for UGCLAW.

Built on Playwright (sync API) — persists a browser context across tool calls
so cookies and session state survive between navigate/fill/click sequences.

If Playwright is not installed the tool returns a helpful error instead of
crashing the whole agent.
"""

import threading
from pathlib import Path
from typing import Optional


class BrowserSession:
    """
    Long-lived Chromium browser context.
    Lazily initialised on first use — no startup cost if browser tools aren't called.
    Thread-safe via a lock.
    """

    def __init__(self, workspace: Path, headless: bool = True):
        self.workspace = workspace
        self.headless  = headless
        self._lock     = threading.Lock()
        self._pw       = None
        self._browser  = None
        self._context  = None
        self._page     = None

    # ── Startup / teardown ────────────────────────────────────────────────────

    def _start(self):
        if self._page is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError(
                "Playwright is not installed.\n"
                "Run: pip install playwright && playwright install chromium"
            )
        self._pw      = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        self._page = self._context.new_page()

    def close(self):
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._page = self._browser = self._context = self._pw = None

    # ── Tools ─────────────────────────────────────────────────────────────────

    def navigate(self, url: str) -> str:
        with self._lock:
            self._start()
            self._page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            return f"✅ {url}\nTitle: {self._page.title()}"

    def fill(self, selector: str, value: str) -> str:
        with self._lock:
            self._start()
            self._page.wait_for_selector(selector, timeout=10_000)
            self._page.fill(selector, value)
            return f"✅ Filled [{selector}]"

    def click(self, selector: str) -> str:
        with self._lock:
            self._start()
            self._page.wait_for_selector(selector, timeout=10_000)
            self._page.click(selector)
            self._page.wait_for_load_state("domcontentloaded", timeout=15_000)
            return f"✅ Clicked [{selector}] — now at: {self._page.url}"

    def get_text(self) -> str:
        with self._lock:
            self._start()
            text = self._page.evaluate("""() => {
                document.querySelectorAll('script,style,noscript').forEach(e => e.remove());
                return document.body ? document.body.innerText : '';
            }""")
            return (text or "")[:8000]

    def get_html(self) -> str:
        with self._lock:
            self._start()
            return self._page.content()[:10_000]

    def screenshot(self, filename: str = "screenshot.png") -> str:
        with self._lock:
            self._start()
            # Avoid filename collisions
            dest = self.workspace / filename
            stem, suffix = dest.stem, dest.suffix
            c = 1
            while dest.exists():
                dest = self.workspace / f"{stem}_{c}{suffix}"
                c += 1
            self._page.screenshot(path=str(dest), full_page=True)
            return str(dest)

    def execute_js(self, code: str) -> str:
        with self._lock:
            self._start()
            result = self._page.evaluate(code)
            return str(result)

    def login(self, url: str, fields: dict, submit_selector: str) -> str:
        """High-level: navigate → fill all fields → click submit → return page state."""
        steps = [self.navigate(url)]
        for sel, val in fields.items():
            steps.append(self.fill(sel, val))
        steps.append(self.click(submit_selector))
        with self._lock:
            after = (self._page.evaluate("""() => document.body ? document.body.innerText : ''""") or "")[:2000]
            url_after = self._page.url
        steps.append(f"\n── After login ──\nURL: {url_after}\n{after}")
        return "\n".join(steps)

    def current_url(self) -> str:
        with self._lock:
            self._start()
            return self._page.url

    def select_option(self, selector: str, value: str) -> str:
        with self._lock:
            self._start()
            self._page.select_option(selector, value=value)
            return f"✅ Selected [{value}] in [{selector}]"
