"""
paths.py — central path definitions for UGCLAW.

Every component imports from here so paths are never scattered or hardcoded.
The base directory is ~/.ugclaw — created on install, survives project deletion.
"""

from pathlib import Path
import os

# ── Base ──────────────────────────────────────────────────────────────────────

BASE_DIR     = Path.home() / ".ugclaw"
CONFIG_FILE  = BASE_DIR / "config.json"
AGENT_MD     = BASE_DIR / "AGENT.md"
FACTS_FILE   = BASE_DIR / "facts.json"
WORKSPACE    = BASE_DIR / "workspace"
SESSIONS_DIR = BASE_DIR / "sessions"
LOGS_DIR     = BASE_DIR / "logs"
DAEMON_LOG   = LOGS_DIR / "daemon.log"
SOCKET_PATH  = Path("/tmp/ugclaw.sock")
PID_FILE     = Path("/tmp/ugclaw.pid")

# Default config template (inside the package)
DEFAULT_CONFIG = Path(__file__).parent.parent / "config" / "default_config.json"


def ensure_dirs():
    """Create ~/.ugclaw directory structure if missing."""
    for d in (BASE_DIR, WORKSPACE, SESSIONS_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)
