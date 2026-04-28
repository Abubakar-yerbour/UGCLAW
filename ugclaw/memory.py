"""
memory.py — persistent memory layer for UGCLAW.

Files (all under ~/.ugclaw/):
  AGENT.md       — agent identity: name, user nicknames, personal notes
  facts.json     — key-value long-term facts across all sessions
  sessions/      — per-session conversation history (JSON)

On every new Agent session, build_context_prefix() injects all of this
into the system prompt so the LLM always has full context.
"""

import json
import time
from pathlib import Path

from ugclaw.paths import BASE_DIR, AGENT_MD, FACTS_FILE, SESSIONS_DIR


_AGENT_MD_DEFAULT = """\
# AGENT.md — UGCLAW Identity

## Agent Name
UGCLAW

## User Nicknames
_Not set — the agent will update this when the user introduces themselves._

## Notes
_Auto-updated by the agent across sessions._

## Remembered Facts
_See facts.json for structured key-value facts._
"""


class Memory:
    def __init__(self):
        self._ensure_files()

    # ── Bootstrap ─────────────────────────────────────────────────────────────

    def _ensure_files(self):
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        if not AGENT_MD.exists():
            AGENT_MD.write_text(_AGENT_MD_DEFAULT, encoding="utf-8")
        if not FACTS_FILE.exists():
            FACTS_FILE.write_text("{}", encoding="utf-8")

    # ── AGENT.md ──────────────────────────────────────────────────────────────

    def read_agent_md(self) -> str:
        return AGENT_MD.read_text(encoding="utf-8", errors="replace")

    def write_agent_md(self, content: str):
        AGENT_MD.write_text(content, encoding="utf-8")

    def patch_agent_md(self, section: str, value: str):
        """Update or append a named ## section in AGENT.md."""
        content = self.read_agent_md()
        header  = f"## {section}"

        if header in content:
            lines     = content.split("\n")
            new_lines = []
            skip      = False
            for line in lines:
                if line.strip() == header:
                    new_lines.append(line)
                    new_lines.append(value)
                    skip = True
                    continue
                if skip and line.startswith("## "):
                    skip = False
                if not skip:
                    new_lines.append(line)
            self.write_agent_md("\n".join(new_lines))
        else:
            self.write_agent_md(content.rstrip() + f"\n\n{header}\n{value}\n")

    # ── Facts ─────────────────────────────────────────────────────────────────

    def load_facts(self) -> dict:
        try:
            return json.loads(FACTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_facts(self, facts: dict):
        FACTS_FILE.write_text(json.dumps(facts, indent=2, ensure_ascii=False))

    def set_fact(self, key: str, value: str):
        facts = self.load_facts()
        facts[key] = value
        self.save_facts(facts)

    def delete_fact(self, key: str) -> bool:
        facts = self.load_facts()
        if key in facts:
            del facts[key]
            self.save_facts(facts)
            return True
        return False

    # ── Session history ───────────────────────────────────────────────────────

    def _session_path(self, session_id: str) -> Path:
        safe = str(session_id).replace("/", "_").replace("\\", "_")
        return SESSIONS_DIR / f"{safe}.json"

    def load_session(self, session_id: str) -> list:
        p = self._session_path(session_id)
        if not p.exists():
            return []
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data[-80:]   # cap at 80 messages
        except Exception:
            return []

    def save_session(self, session_id: str, history: list):
        p = self._session_path(session_id)
        p.write_text(json.dumps(history, indent=2, ensure_ascii=False))

    def delete_session(self, session_id: str) -> bool:
        p = self._session_path(session_id)
        if p.exists():
            p.unlink()
            return True
        return False

    def list_sessions(self) -> list[dict]:
        out = []
        for f in SESSIONS_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                out.append({
                    "id":       f.stem,
                    "messages": len(data),
                    "modified": time.strftime(
                        "%Y-%m-%d %H:%M",
                        time.localtime(f.stat().st_mtime),
                    ),
                })
            except Exception:
                pass
        return sorted(out, key=lambda x: x["modified"], reverse=True)

    # ── Context injection ─────────────────────────────────────────────────────

    def build_context_prefix(self) -> str:
        """
        Rich prefix injected at top of every system prompt.
        Tells the agent who it is, what it remembers, and how to behave.
        """
        sections = []

        agent_md = self.read_agent_md().strip()
        if agent_md:
            sections.append(f"## Identity\n{agent_md}")

        facts = self.load_facts()
        if facts:
            lines = "\n".join(f"- **{k}**: {v}" for k, v in facts.items())
            sections.append(f"## Remembered Facts\n{lines}")

        sections.append(
            "## Memory Instructions\n"
            "- When the user shares their name or nickname, call update_memory immediately.\n"
            "- When asked to remember something, call update_memory.\n"
            "- Address returning users by their nickname if known.\n"
            "- When the user gives you a name, update AGENT.md via update_memory."
        )

        return "\n\n".join(sections)
