#!/usr/bin/env python3
"""
install.py — UGCLAW installer.

Handles:
  - Python version check (≥3.10)
  - pip install -r requirements.txt
  - pip install -e .   (registers the `ugclaw` CLI command)
  - Playwright chromium install (optional)
  - ~/.ugclaw directory structure creation
  - Initial config setup
  - Prints usage guide when done
"""

import sys
import os
import subprocess
import shutil
from pathlib import Path

# ── Colours ───────────────────────────────────────────────────────────────────

def _c(code, text):
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text

def green(t):  return _c("32;1", t)
def red(t):    return _c("31;1", t)
def yellow(t): return _c("33;1", t)
def cyan(t):   return _c("36;1", t)
def bold(t):   return _c("1", t)


BANNER = """
 ██╗   ██╗ ██████╗  ██████╗██╗      █████╗ ██╗    ██╗
 ██║   ██║██╔════╝ ██╔════╝██║     ██╔══██╗██║    ██║
 ██║   ██║██║  ███╗██║     ██║     ███████║██║ █╗ ██║
 ██║   ██║██║   ██║██║     ██║     ██╔══██║██║███╗██║
 ╚██████╔╝╚██████╔╝╚██████╗███████╗██║  ██║╚███╔███╔╝
  ╚═════╝  ╚═════╝  ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝

  Autonomous AI Agent  —  Installation
  Channel : https://t.me/UGCLAW\n
"""


def step(msg):
    print(f"  {cyan('→')} {msg}")


def ok(msg):
    print(f"  {green('✔')} {msg}")


def warn(msg):
    print(f"  {yellow('⚠')}  {msg}")


def fail(msg):
    print(f"  {red('✘')} {msg}")


def ask(prompt) -> str:
    try:
        return input(f"  {bold('?')} {prompt} ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        sys.exit(0)


# ── Checks ────────────────────────────────────────────────────────────────────

def check_python():
    step("Checking Python version…")
    v = sys.version_info
    if v < (3, 10):
        fail(f"Python 3.10+ required. You have {v.major}.{v.minor}.{v.micro}")
        sys.exit(1)
    ok(f"Python {v.major}.{v.minor}.{v.micro}")


def check_pip():
    step("Checking pip…")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            check=True, capture_output=True,
        )
        ok("pip available")
    except subprocess.CalledProcessError:
        fail("pip not found. Install pip and re-run this script.")
        sys.exit(1)


# ── Installation ──────────────────────────────────────────────────────────────

def install_requirements():
    req = Path(__file__).parent / "requirements.txt"
    step(f"Installing dependencies from {req.name}…")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(req), "--quiet"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        fail("Dependency installation failed.")
        print(result.stderr[-2000:])
        sys.exit(1)
    ok("Dependencies installed")


def install_package():
    step("Installing ugclaw as a system command…")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", ".", "--quiet"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).parent),
    )
    if result.returncode != 0:
        fail("Package installation failed.")
        print(result.stderr[-2000:])
        sys.exit(1)
    ok("'ugclaw' command registered")


def install_playwright():
    print()
    step("Playwright browser (for web automation / login tools)")
    print(f"       This downloads ~150MB of Chromium.")
    ans = ask("Install Playwright Chromium? [Y/n]").lower()
    if ans in ("", "y", "yes"):
        step("Installing Chromium via Playwright…")
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            ok("Chromium installed — browser tools are ready")
        else:
            warn("Playwright install had issues. Browser tools may not work.")
            warn("Fix manually: playwright install chromium")
    else:
        warn("Skipped. Browser tools (login, screenshot) will not work until installed.")
        warn("To install later: playwright install chromium")


# ── Data directory ────────────────────────────────────────────────────────────

def setup_data_dir():
    base         = Path.home() / ".ugclaw"
    workspace    = base / "workspace"
    sessions_dir = base / "sessions"
    logs_dir     = base / "logs"

    step(f"Creating data directory: {base}")
    for d in (base, workspace, sessions_dir, logs_dir):
        d.mkdir(parents=True, exist_ok=True)
    ok(f"~/.ugclaw structure ready")

    # Copy default config if none exists
    config_file   = base / "config.json"
    default_config = Path(__file__).parent / "config" / "default_config.json"

    if not config_file.exists():
        if default_config.exists():
            shutil.copy(default_config, config_file)
            ok("Default config created at ~/.ugclaw/config.json")
        else:
            warn("Default config template not found — config.json not created")
    else:
        ok("Config already exists — not overwritten")


# ── Post-install summary ──────────────────────────────────────────────────────

def print_summary():
    print()
    print("─" * 56)
    print(green("  Installation complete! ✔"))
    print("─" * 56)
    print("""
  Next steps:

  1. Configure your API keys and Telegram bot:

       ugclaw configure

     Or jump straight to a section:
       ugclaw configure providers   ← set OpenAI / Anthropic / etc keys
       ugclaw configure telegram    ← set Telegram bot token
       ugclaw configure models      ← fetch and select models

  2. Start the daemon:

       ugclaw start

  3. Open the terminal chat:

       ugclaw tui

  4. (Optional) Enable UGCLAW on system boot:

       ugclaw enable

  Full command reference:

       ugclaw --help

  Config file : ~/.ugclaw/config.json
  Data dir    : ~/.ugclaw/
  Logs        : ~/.ugclaw/logs/daemon.log
  
  Channel : https://t.me/UGCLAW\n
  Author : Abubakar Bello <abubakarbello3914@gmail.com>
""")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(cyan(BANNER))
    print()

    check_python()
    check_pip()
    print()

    install_requirements()
    install_package()
    print()

    install_playwright()
    print()

    setup_data_dir()
    print()

    print_summary()


if __name__ == "__main__":
    main()
