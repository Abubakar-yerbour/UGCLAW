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
import time
import threading
from pathlib import Path


# ── Colours ───────────────────────────────────────────────────────────────────

def _c(code, text):
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text

def green(t):   return _c("32;1", t)
def red(t):     return _c("31;1", t)
def yellow(t):  return _c("33;1", t)
def cyan(t):    return _c("36;1", t)
def blue(t):    return _c("34;1", t)
def magenta(t): return _c("35;1", t)
def dim(t):     return _c("2", t)
def bold(t):    return _c("1", t)
def white(t):   return _c("97;1", t)


# ── Banner ────────────────────────────────────────────────────────────────────

BANNER_LINES = [
    r" ██╗   ██╗ ██████╗  ██████╗██╗      █████╗ ██╗    ██╗",
    r" ██║   ██║██╔════╝ ██╔════╝██║     ██╔══██╗██║    ██║",
    r" ██║   ██║██║  ███╗██║     ██║     ███████║██║ █╗ ██║",
    r" ██║   ██║██║   ██║██║     ██║     ██╔══██║██║███╗██║",
    r" ╚██████╔╝╚██████╔╝╚██████╗███████╗██║  ██║╚███╔███╔╝",
    r"  ╚═════╝  ╚═════╝  ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝",
]

def print_banner():
    print()
    colors = [cyan, cyan, blue, blue, magenta, magenta]
    for color, line in zip(colors, BANNER_LINES):
        print(color(line))
        time.sleep(0.06)
    print()
    print(white("  ─" * 28))
    print(f"  {bold('Autonomous AI Agent')}  {dim('—')}  {cyan('Installation Wizard')}")
    print(f"  {dim('Channel :')} {blue('https://t.me/UGCLAW')}")
    print(white("  ─" * 28))
    print()


# ── Spinner ───────────────────────────────────────────────────────────────────

class Spinner:
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str):
        self.message  = message
        self._stop    = threading.Event()
        self._thread  = threading.Thread(target=self._spin, daemon=True)

    def _spin(self):
        i = 0
        while not self._stop.is_set():
            frame = cyan(self.FRAMES[i % len(self.FRAMES)])
            print(f"\r  {frame}  {self.message} ", end="", flush=True)
            time.sleep(0.08)
            i += 1

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join()
        print("\r" + " " * (len(self.message) + 10) + "\r", end="", flush=True)


# ── Progress bar ──────────────────────────────────────────────────────────────

def progress_bar(label: str, total_steps: int = 20, delay: float = 0.04):
    bar_width = 30
    print(f"  {dim(label)}")
    for i in range(total_steps + 1):
        filled  = int(bar_width * i / total_steps)
        bar     = cyan("█" * filled) + dim("░" * (bar_width - filled))
        pct     = int(100 * i / total_steps)
        print(f"\r  [{bar}] {white(f'{pct:3d}%')}", end="", flush=True)
        time.sleep(delay)
    print()


# ── Print helpers ─────────────────────────────────────────────────────────────

def section(title: str):
    print()
    print(f"  {cyan('┌─')} {bold(title)}")

def ok(msg: str):
    print(f"  {cyan('│')}  {green('✔')}  {msg}")

def warn(msg: str):
    print(f"  {cyan('│')}  {yellow('⚠')}  {msg}")

def fail(msg: str):
    print(f"  {cyan('│')}  {red('✘')}  {msg}")

def info(msg: str):
    print(f"  {cyan('│')}     {dim(msg)}")

def section_end():
    print(f"  {cyan('└─')} {dim('done')}")

def ask(prompt: str) -> str:
    try:
        return input(f"\n  {cyan('?')}  {bold(prompt)} ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        abort()


def abort():
    print()
    print(f"  {red('Installation cancelled.')}")
    sys.exit(0)


def divider():
    print(f"\n  {dim('─' * 54)}\n")


# ── Virtual environment helper ────────────────────────────────────────────────

def _in_virtualenv() -> bool:
    return (
        hasattr(sys, "real_prefix")
        or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)
        or os.environ.get("VIRTUAL_ENV") is not None
        or os.environ.get("CONDA_DEFAULT_ENV") is not None
    )


def _print_venv_help():
    python = sys.executable
    print()
    print(f"  {yellow('─' * 54)}")
    print(f"  {yellow('Tip: Use a virtual environment to avoid conflicts.')}")
    print(f"  {yellow('─' * 54)}")
    print()
    print(f"  {bold('Create and activate one, then re-run:')} \n")
    print(f"    {cyan('python3 -m venv myenv')}")
    print(f"    {cyan('source myenv/bin/activate')}   {dim('# Linux / macOS')}")
    print(f"    {cyan(r'myenv\Scripts\activate')}      {dim('# Windows')}")
    print(f"    {cyan('python install.py')}")
    print()
    print(f"  {dim('Or with conda:')}")
    print(f"    {cyan('conda create -n ugclaw python=3.11')}")
    print(f"    {cyan('conda activate ugclaw')}")
    print(f"    {cyan('python install.py')}")
    print()


# ── Checks ────────────────────────────────────────────────────────────────────

def check_python():
    section("System Check")
    v = sys.version_info
    if v < (3, 10):
        fail(f"Python 3.10+ required — you have {v.major}.{v.minor}.{v.micro}")
        section_end()
        sys.exit(1)
    ok(f"Python {v.major}.{v.minor}.{v.micro}")

    # Warn if not in a virtualenv (but don't block)
    if not _in_virtualenv():
        warn("Not inside a virtual environment.")
        info("Recommended: use 'python3 -m venv myenv' to avoid conflicts.")
    else:
        ok(f"Virtual environment active  {dim('(' + sys.prefix + ')')}")

    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            check=True, capture_output=True,
        )
        ok("pip available")
    except subprocess.CalledProcessError:
        fail("pip not found.")
        info("Install pip: https://pip.pypa.io/en/stable/installation/")
        section_end()
        sys.exit(1)

    section_end()


# ── Installation ──────────────────────────────────────────────────────────────

def install_requirements():
    section("Installing Dependencies")
    req = Path(__file__).parent / "requirements.txt"

    if not req.exists():
        fail(f"requirements.txt not found at {req}")
        section_end()
        sys.exit(1)

    info(f"Reading {req.name}…")

    with Spinner("Installing packages from requirements.txt"):
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req),
             "--quiet", "--break-system-packages"],
            capture_output=True, text=True,
        )

    if result.returncode != 0:
        fail("Dependency installation failed.")
        print()
        # Show the actual pip error
        err = result.stderr.strip()
        if err:
            for line in err.splitlines()[-15:]:
                info(line)
        print()
        _print_venv_help()
        print(f"  {dim('If the problem persists, install manually:')}")
        print(f"    {cyan(f'pip install -r {req}')}")
        section_end()
        sys.exit(1)

    ok("All dependencies installed")
    section_end()


def install_package():
    section("Registering CLI Command")

    with Spinner("Running pip install -e ."):
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", ".",
             "--quiet", "--break-system-packages"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent),
        )

    if result.returncode != 0:
        fail("Package installation failed.")
        print()
        err = result.stderr.strip()
        if err:
            for line in err.splitlines()[-15:]:
                info(line)
        print()
        _print_venv_help()
        print(f"  {dim('Try manually:')}")
        print(f"    {cyan('pip install -e .')}")
        section_end()
        sys.exit(1)

    ok(f"{bold('ugclaw')} command registered system-wide")
    section_end()


def install_playwright():
    section("Browser Automation  (Optional)")
    info("Playwright Chromium enables web login, screenshots, and JS automation.")
    info("Download size: ~150MB")
    print()

    ans = ask("Install Playwright Chromium? [Y/n]").lower()
    if ans not in ("", "y", "yes"):
        warn("Skipped — browser tools will not work until you run:")
        info("playwright install chromium")
        section_end()
        return

    with Spinner("Downloading Chromium (this may take a minute)"):
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True, text=True,
        )

    if result.returncode == 0:
        ok("Chromium installed — browser tools are ready")
    else:
        warn("Playwright install encountered issues.")
        info("Browser tools may not work until fixed.")
        info("Fix manually: playwright install chromium")

    section_end()


# ── Data directory ────────────────────────────────────────────────────────────

def setup_data_dir():
    section("Setting Up Data Directory")

    base         = Path.home() / ".ugclaw"
    workspace    = base / "workspace"
    sessions_dir = base / "sessions"
    logs_dir     = base / "logs"

    dirs = [base, workspace, sessions_dir, logs_dir]

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    progress_bar("Creating directory structure…", total_steps=len(dirs) * 5, delay=0.02)
    ok(f"~/.ugclaw/  structure ready")

    # Copy default config if none exists
    config_file    = base / "config.json"
    default_config = Path(__file__).parent / "default_config.json"

    if not config_file.exists():
        if default_config.exists():
            shutil.copy(default_config, config_file)
            ok(f"Default config created")
            info(str(config_file))
        else:
            warn("Default config template not found — config.json not created")
            info("Run: ugclaw configure  to create it")
    else:
        ok("Existing config preserved")
        info(str(config_file))

    section_end()


# ── Post-install summary ──────────────────────────────────────────────────────

def print_summary():
    divider()
    print(f"  {green('✔')}  {bold(green('Installation complete!'))}")
    divider()

    steps = [
        ("1", "Configure API keys and Telegram bot",
         ["ugclaw configure",
          "ugclaw configure providers   ← API keys",
          "ugclaw configure telegram    ← Telegram bot token",
          "ugclaw configure models      ← fetch & select models"]),
        ("2", "Start the daemon",
         ["ugclaw start"]),
        ("3", "Open the terminal chat",
         ["ugclaw tui"]),
        ("4", "Enable on system boot  (optional)",
         ["ugclaw enable"]),
    ]

    for num, title, cmds in steps:
        print(f"  {cyan(num + '.')}  {bold(title)}")
        print()
        for cmd in cmds:
            print(f"       {cyan(cmd)}")
        print()

    divider()
    print(f"  {dim('Config  :')}  ~/.ugclaw/config.json")
    print(f"  {dim('Data    :')}  ~/.ugclaw/")
    print(f"  {dim('Logs    :')}  ~/.ugclaw/logs/daemon.log")
    print(f"  {dim('Help    :')}  ugclaw --help")
    print()
    print(f"  {dim('Channel :')}  {blue('https://t.me/UGCLAW')}")
    print(f"  {dim('Author  :')}  Abubakar Bello {dim('<abubakarbello3914@gmail.com>')}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Clear screen for a clean start
    os.system("clear" if os.name != "nt" else "cls")

    print_banner()

    try:
        check_python()
        install_requirements()
        install_package()
        install_playwright()
        setup_data_dir()
        print_summary()

    except KeyboardInterrupt:
        print()
        print(f"\n  {yellow('Installation interrupted.')} Run again to retry.")
        sys.exit(1)


if __name__ == "__main__":
    main()
