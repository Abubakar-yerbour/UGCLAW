"""
config_manager.py — robust config loader for UGCLAW.

Handles:
  - JSON syntax errors (show exact line, offer reset)
  - Missing keys (fill from defaults silently)
  - Path expansion (~ in paths)
  - Live reload (daemon rereads on each request)
"""

import json
import shutil
import sys
from pathlib import Path
from typing import Any

from ugclaw.paths import CONFIG_FILE, DEFAULT_CONFIG


# Keys that must never be missing — filled from defaults if absent
_REQUIRED_KEYS = [
    "active_provider", "active_model",
    "openai_api_key", "anthropic_api_key", "gemini_api_key",
    "groq_api_key", "openrouter_api_key",
    "telegram_bot_token", "telegram_owner_id", "allowed_telegram_ids",
    "max_tokens", "tool_timeout", "max_tool_iterations",
    "browser_headless", "saved_models", "system_prompt", "daemon",
]


def load_config(path: Path = CONFIG_FILE, strict: bool = False) -> dict:
    """
    Load config from disk.

    On JSON syntax error:
      - strict=True  → raise immediately (used by install/configure)
      - strict=False → print a clear error and exit with helpful message

    Missing keys are filled from defaults automatically.
    """
    raw = _read_raw(path, strict)
    defaults = _read_defaults()
    return _merge(defaults, raw)


def save_config(cfg: dict, path: Path = CONFIG_FILE):
    """Write config to disk, removing internal comment keys cleanly."""
    out = {k: v for k, v in cfg.items() if not k.startswith("_")}
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))


def validate_config(cfg: dict) -> list[str]:
    """
    Return a list of human-readable warnings about the config.
    Empty list = all good.
    """
    warnings = []

    if not cfg.get("openai_api_key") and cfg.get("active_provider") == "openai":
        warnings.append("OpenAI is active provider but openai_api_key is not set.")

    providers = ["openai", "anthropic", "gemini", "groq", "openrouter"]
    active = cfg.get("active_provider", "")
    if active not in providers:
        warnings.append(f"active_provider '{active}' is not recognised.")

    tg = cfg.get("telegram_bot_token", "")
    if not tg:
        warnings.append("telegram_bot_token not set — Telegram bot will be disabled.")

    if cfg.get("max_tool_iterations", 15) < 3:
        warnings.append("max_tool_iterations is very low — tools may not complete tasks.")

    return warnings


# ── Internal ──────────────────────────────────────────────────────────────────

def _read_raw(path: Path, strict: bool) -> dict:
    if not path.exists():
        # First run — copy default
        if DEFAULT_CONFIG.exists():
            shutil.copy(DEFAULT_CONFIG, path)
            return json.loads(path.read_text())
        return {}

    text = path.read_text(encoding="utf-8")

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        msg = (
            f"\n  ❌  Config file has a JSON syntax error:\n"
            f"      File : {path}\n"
            f"      Error: {e.msg} at line {e.lineno}, column {e.colno}\n\n"
            f"  Fix the file manually, or reset it:\n"
            f"      ugclaw configure --reset-config\n"
        )
        if strict:
            raise ValueError(msg) from e
        print(msg)
        sys.exit(1)


def _read_defaults() -> dict:
    if DEFAULT_CONFIG.exists():
        try:
            return json.loads(DEFAULT_CONFIG.read_text())
        except Exception:
            pass
    return {}


def _merge(defaults: dict, user: dict) -> dict:
    """User values override defaults; missing keys fall back to defaults."""
    result = dict(defaults)
    result.update(user)

    # Expand ~ in daemon paths
    daemon = result.get("daemon", {})
    for key in ("log_file",):
        if key in daemon:
            daemon[key] = str(Path(daemon[key]).expanduser())
    result["daemon"] = daemon

    return result
