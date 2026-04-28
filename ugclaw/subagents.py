"""
subagents.py — UGCLAW background subagent manager.

Each subagent is a daemon thread running its own Agent instance.
The main conversation is never blocked.
Subagents can be assigned a specific provider/model independently.
"""

import uuid
import threading
import time
from typing import Dict, Optional, Callable


class Subagent:
    def __init__(
        self,
        agent_id: str,
        task:     str,
        target:   str,
        provider_id: Optional[str] = None,
        model:       Optional[str] = None,
        chat_id:     Optional[int] = None,   # ← NEW: originating chat
    ):
        self.id          = agent_id
        self.task        = task
        self.target      = target
        self.provider_id = provider_id
        self.model       = model
        self.chat_id     = chat_id            # ← NEW
        self.status      = "pending"   # pending | running | done | failed | killed
        self.created_at  = time.strftime("%H:%M:%S")
        self._logs: list = []
        self.result: Optional[str] = None
        self.stop_event  = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def log(self, msg: str):
        self._logs.append(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def get_logs(self) -> str:
        return "\n".join(self._logs) if self._logs else "(no logs yet)"

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "task":       self.task,
            "target":     self.target,
            "status":     self.status,
            "provider":   self.provider_id or "default",
            "model":      self.model or "default",
            "created_at": self.created_at,
            "log_lines":  len(self._logs),
            "result":     (self.result or "")[:200],
        }


class SubagentManager:
    def __init__(self, config: dict):
        self.config   = config
        self._agents: Dict[str, Subagent] = {}
        self._lock    = threading.Lock()
        self._factory: Optional[Callable] = None
        self._on_complete: Optional[Callable] = None   # ← NEW

    def set_factory(self, factory: Callable):
        self._factory = factory

    def set_on_complete(self, callback: Callable):
        """
        Register a callback invoked when a subagent finishes or fails.

        Signature:  callback(sa: Subagent)

        The callback is called from the subagent's background thread, so it
        must be thread-safe (TelegramBot.send_text already is).
        """
        self._on_complete = callback   # ← NEW

    # ── Public API ────────────────────────────────────────────────────────────

    def spawn(
        self,
        task:        str,
        target:      str = "",
        provider_id: Optional[str] = None,
        model:       Optional[str] = None,
        chat_id:     Optional[int] = None,   # ← NEW
    ) -> str:
        agent_id = uuid.uuid4().hex[:8]
        sa = Subagent(agent_id, task, target, provider_id, model, chat_id)  # ← pass chat_id

        with self._lock:
            self._agents[agent_id] = sa

        t = threading.Thread(target=self._run, args=(sa,), daemon=True)
        sa._thread = t
        t.start()
        return agent_id

    def status(self, agent_id: str) -> dict:
        sa = self._get(agent_id)
        return sa.to_dict() if sa else {"error": f"Unknown agent: {agent_id}"}

    def logs(self, agent_id: str) -> str:
        sa = self._get(agent_id)
        return sa.get_logs() if sa else f"❌ Unknown agent: {agent_id}"

    def kill(self, agent_id: str) -> str:
        sa = self._get(agent_id)
        if not sa:
            return f"❌ Unknown agent: {agent_id}"
        sa.stop_event.set()
        sa.status = "killed"
        sa.log("⛔ Killed by user.")
        return f"Agent `{agent_id}` killed."

    def list_all(self) -> list:
        with self._lock:
            return [sa.to_dict() for sa in self._agents.values()]

    def get_last_id(self) -> Optional[str]:
        with self._lock:
            if not self._agents:
                return None
            return list(self._agents.keys())[-1]

    # ── Internal ──────────────────────────────────────────────────────────────

    def _get(self, agent_id: str) -> Optional[Subagent]:
        with self._lock:
            return self._agents.get(agent_id)

    def _run(self, sa: Subagent):
        sa.status = "running"
        sa.log(f"Task: {sa.task}")
        if sa.target:
            sa.log(f"Target: {sa.target}")
        if sa.provider_id or sa.model:
            sa.log(f"Model: {sa.provider_id or 'default'}/{sa.model or 'default'}")
        try:
            if not self._factory:
                raise RuntimeError("No agent factory set.")
            result = self._factory(sa)
            if sa.status == "killed":
                return
            sa.result = result
            sa.status = "done"
            sa.log("✅ Done.")
        except Exception as e:
            sa.status = "failed"
            sa.log(f"❌ Error: {e}")
        finally:
            # ── NEW: fire completion callback regardless of outcome ──────────
            if sa.status != "killed" and self._on_complete:
                try:
                    self._on_complete(sa)
                except Exception as cb_err:
                    print(f"[SubagentManager] on_complete callback error: {cb_err}")
