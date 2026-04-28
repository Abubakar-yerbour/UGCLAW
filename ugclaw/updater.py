import re
import threading
from typing import Optional, Tuple

from ugclaw import __version__

GITHUB_REPO  = "Abubakar-yerbour/UGCLAW"
RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
INSTALL_URL  = f"https://github.com/{GITHUB_REPO}"


def _parse_version(tag: str) -> Tuple[int, ...]:
    """Convert 'v3.1.2' or '3.1.2' to (3, 1, 2) for comparison."""
    digits = re.findall(r"\d+", tag)
    return tuple(int(d) for d in digits)


def check_for_update(timeout: int = 8) -> Optional[dict]:
    """
    Query GitHub for the latest release.

    Returns a dict if a newer version is available:
        {
            "current":  "3.0.0",
            "latest":   "3.1.0",
            "tag":      "v3.1.0",
            "url":      "https://github.com/.../releases/tag/v3.1.0",
            "notes":    "Release notes snippet…",
        }

    Returns None if already up to date, or if the check fails silently.
    """
    try:
        import requests
        r = requests.get(
            RELEASES_URL,
            timeout=timeout,
            headers={"Accept": "application/vnd.github+json"},
        )
        if r.status_code != 200:
            return None

        data       = r.json()
        latest_tag = data.get("tag_name", "")
        html_url   = data.get("html_url", "")
        notes      = (data.get("body") or "")[:300].strip()

        if not latest_tag:
            return None

        current_v = _parse_version(__version__)
        latest_v  = _parse_version(latest_tag)

        if latest_v > current_v:
            return {
                "current": __version__,
                "latest":  latest_tag.lstrip("v"),
                "tag":     latest_tag,
                "url":     html_url,
                "notes":   notes,
            }
        return None

    except Exception:
        return None


def check_silent(callback=None):
    """
    Run check_for_update() in a background thread so startup isn't delayed.

    If an update is found and callback is provided, calls callback(info).
    Otherwise prints a one-line notice to stdout.
    """
    def _run():
        info = check_for_update()
        if not info:
            return
        if callback:
            callback(info)
        else:
            print(
                f"\n⬆️  Update available: v{info['current']} → v{info['latest']}\n"
                f"   Run: ugclaw update\n"
		f"Channel : https://t.me/UGCLAW\n"
            )

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def run_update():
    """
    Interactive update: check then install if the user confirms.
    Called by `ugclaw update`.
    """
    print(f"🔍 Checking for updates… (current: v{__version__})")
    info = check_for_update()

    if not info:
        print(f"✅ You're already on the latest version (v{__version__}).")
        return

    print(f"\n⬆️  New version available!")
    print(f"   Current : v{info['current']}")
    print(f"   Latest  : v{info['latest']}")
    print(f"   Release : {info['url']}")
    if info["notes"]:
        print(f"\n   What's new:\n   {info['notes']}\n")

    try:
        answer = input("Install now? [y/N] ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        return

    if answer != "y":
        print("Update skipped.")
        return

    _do_install(info)


def _do_install(info: dict):
    """Run pip install to pull the latest version from GitHub."""
    import subprocess, sys

    print(f"\n📦 Installing v{info['latest']}…")
    cmd = [
        sys.executable, "-m", "pip", "install", "--upgrade",
        f"git+https://github.com/{GITHUB_REPO}.git",
        "--break-system-packages",
    ]
    try:
        result = subprocess.run(cmd, check=True)
        print(f"\n✅ UGCLAW updated to v{info['latest']}.")
        print("   Restart the daemon to apply: ugclaw restart")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Install failed (exit code {e.returncode}).")
        print(f"   Try manually:\n   pip install git+https://github.com/{GITHUB_REPO}.git")
