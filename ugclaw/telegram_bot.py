"""
telegram_bot.py — UGCLAW Telegram interface.

Commands (all registered with BotFather for autocomplete):
  /start   /help    /status  /models  /agents  /tasks
  /kill    /reset   /new     /restart /usage   /tools
  /memory  /approve /deny    /allowed

Unauthorized users see their UID with copy-paste-ready approve instructions.
"""

import json
import threading
import time
import requests
from pathlib import Path
from typing import Callable, Set


# ── Command list sent to BotFather ────────────────────────────────────────────

BOT_COMMANDS = [
    ("start",   "Initialise or resume your session"),
    ("help",    "Show all available commands"),
    ("status",  "Daemon and model status"),
    ("models",  "Switch AI provider and model"),
    ("agents",  "List all background subagents"),
    ("tasks",   "Alias for /agents"),
    ("kill",    "Kill a subagent — usage: /kill <id>"),
    ("reset",   "Clear current conversation history"),
    ("new",     "Start a fresh session (keeps memory)"),
    ("restart", "Restart the agent brain for this chat"),
    ("usage",   "Show session usage statistics"),
    ("tools",   "List all tools the agent can use"),
    ("memory",  "Show what the agent remembers"),
    ("approve", "Approve a user — usage: /approve <uid>"),
    ("deny",    "Deny a user   — usage: /deny <uid>"),
    ("allowed", "List approved Telegram user IDs"),
]


class TelegramBot:
    def __init__(
        self,
        token: str,
        on_message:      Callable[[int, str], str],
        on_model_switch: Callable[[int, str, str], str],
        config: dict,
        config_path: Path,
    ):
        self.token          = token
        self.api            = f"https://api.telegram.org/bot{token}"
        self.on_message     = on_message
        self.on_model_switch = on_model_switch
        self.config         = config
        self.config_path    = config_path
        self.offset         = 0
        self.allowed_ids: Set[int] = set()
        self._model_flow: dict = {}   # per-chat inline-keyboard state

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def run_async(self) -> threading.Thread:
        self._register_commands()
        t = threading.Thread(target=self._poll_loop, daemon=True)
        t.start()
        return t

    def _register_commands(self):
        """Push command list to BotFather so Telegram shows autocomplete."""
        commands = [{"command": c, "description": d} for c, d in BOT_COMMANDS]
        self._post("setMyCommands", json={"commands": commands})

    # ── Sending ───────────────────────────────────────────────────────────────

    def send_text(self, chat_id, text: str, reply_markup=None, parse_mode="Markdown"):
        for i, chunk in enumerate(_chunks(str(text), 4096)):
            payload = {
                "chat_id":    chat_id,
                "text":       chunk,
                "parse_mode": parse_mode,
            }
            if reply_markup and i == 0:
                payload["reply_markup"] = json.dumps(reply_markup)
            self._post("sendMessage", json=payload)

    def send_file(self, chat_id, path: str, caption: str = None):
        with open(path, "rb") as f:
            self._post("sendDocument", data={
                "chat_id": str(chat_id),
                "caption": caption or "",
            }, files={"document": f})

    def send_typing(self, chat_id):
        self._post("sendChatAction", json={"chat_id": chat_id, "action": "typing"})

    def edit_text(self, chat_id, message_id: int, text: str, reply_markup=None):
        payload = {
            "chat_id":    chat_id,
            "message_id": message_id,
            "text":       text[:4096],
            "parse_mode": "Markdown",
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        self._post("editMessageText", json=payload)

    def answer_callback(self, cb_id: str, text: str = ""):
        self._post("answerCallbackQuery", json={
            "callback_query_id": cb_id,
            "text": text,
        })

    # ── Polling ───────────────────────────────────────────────────────────────

    def _poll_loop(self):
        print("🤖 Telegram: polling started")
        while True:
            try:
                resp = self._post("getUpdates", json={
                    "offset":          self.offset,
                    "timeout":         30,
                    "allowed_updates": ["message", "callback_query"],
                })
                for update in (resp or {}).get("result", []):
                    self.offset = update["update_id"] + 1
                    if "callback_query" in update:
                        self._handle_callback(update["callback_query"])
                    elif "message" in update:
                        self._handle_message(update["message"])
            except Exception as e:
                print(f"[Telegram] poll error: {e}")
                time.sleep(5)

    # ── Message routing ───────────────────────────────────────────────────────

    def _handle_message(self, msg: dict):
        chat_id  = msg["chat"]["id"]
        username = msg.get("from", {}).get("username", "")
        text     = msg.get("text", "").strip()

        # ── Unauthorised ──────────────────────────────────────────────────────
        if self.allowed_ids and chat_id not in self.allowed_ids:
            owner_cmd = "ugclaw telegram approve"
            self.send_text(
                chat_id,
                f"⛔ *You are not authorised to use this agent.*\n\n"
                f"Your Telegram ID:\n`{chat_id}`\n\n"
                f"Ask the owner to run:\n"
                f"```\n{owner_cmd} {chat_id}\n```\n"
                f"Or if the owner is on Telegram:\n"
                f"`/approve {chat_id}`",
            )
            return

        uploaded = []

        # Handle file/photo uploads
        if doc := msg.get("document"):
            from ugclaw.paths import WORKSPACE
            path = self._download(doc["file_id"], doc.get("file_name", "upload"))
            uploaded.append(path)
            text = text or f"[File uploaded: {path}]"

        if photos := msg.get("photo"):
            from ugclaw.paths import WORKSPACE
            photo = max(photos, key=lambda p: p.get("file_size", 0))
            path  = self._download(photo["file_id"], "photo.jpg")
            uploaded.append(path)
            text = text or f"[Photo uploaded: {path}]"

        if not text:
            return

        # ── Built-in commands (only if message starts with /) ─────────────────
        if text.startswith("/"):
            cmd  = text.split()[0].lower().lstrip("/").split("@")[0]
            args = text.split()[1:]

            handlers = {
                "start":   self._cmd_start,
                "help":    self._cmd_help,
                "status":  self._cmd_status,
                "models":  self._cmd_models,
                "agents":  self._cmd_agents,
                "tasks":   self._cmd_agents,
                "kill":    self._cmd_kill,
                "reset":   self._cmd_reset,
                "new":     self._cmd_new,
                "restart": self._cmd_restart,
                "usage":   self._cmd_usage,
                "tools":   self._cmd_tools,
                "memory":  self._cmd_memory,
                "approve": self._cmd_approve,
                "deny":    self._cmd_deny,
                "allowed": self._cmd_allowed,
            }

            if cmd in handlers:
                threading.Thread(
                    target=handlers[cmd],
                    args=(chat_id, args),
                    daemon=True,
                ).start()
                return

        # Regular message → agent
        threading.Thread(
            target=self._respond,
            args=(chat_id, text, uploaded),
            daemon=True,
        ).start()

    # ── Callback handler ──────────────────────────────────────────────────────

    def _handle_callback(self, cb: dict):
        chat_id = cb["from"]["id"]
        data    = cb.get("data", "")
        cb_id   = cb["id"]
        msg_id  = cb["message"]["message_id"]

        self.answer_callback(cb_id)

        if self.allowed_ids and chat_id not in self.allowed_ids:
            return

        if data.startswith("prov:"):
            pid = data[5:]
            self._show_model_list(chat_id, pid, msg_id)

        elif data.startswith("model:"):
            parts = data[6:].split("|", 1)
            if len(parts) == 2:
                provider_id, model = parts
                result = self.on_model_switch(chat_id, provider_id, model)
                self._model_flow.pop(chat_id, None)
                self.edit_text(
                    chat_id, msg_id,
                    f"✅ Switched to `{provider_id}` / `{model}`\n\n{result}",
                )

        elif data == "cancel":
            self._model_flow.pop(chat_id, None)
            self.edit_text(chat_id, msg_id, "❌ Cancelled.")

    # ── Command handlers ──────────────────────────────────────────────────────

    def _cmd_start(self, chat_id, args):
        self.send_text(
            chat_id,
            "⚡ *UGCLAW online.*\n\n"
            "I'm your autonomous AI agent. I can run commands, browse the web, "
            "spawn background tasks, and remember things across sessions.\n\n"
            "Type `/help` to see all commands, or just talk to me naturally.",
        )

    def _cmd_help(self, chat_id, args):
        lines = ["⚡ *UGCLAW — Commands*\n"]
        for cmd, desc in BOT_COMMANDS:
            lines.append(f"`/{cmd}` — {desc}")
        lines.append("\nOr just type naturally — I'll figure out what you need.")
        self.send_text(chat_id, "\n".join(lines))

    def _cmd_status(self, chat_id, args):
        provider = self.config.get("active_provider", "?")
        model    = self.config.get("active_model", "?")
        tg_ids   = self.config.get("allowed_telegram_ids", [])
        self.send_text(
            chat_id,
            f"⚡ *UGCLAW Status*\n\n"
            f"Provider : `{provider}`\n"
            f"Model    : `{model}`\n"
            f"Access   : {'restricted to ' + str(len(tg_ids)) + ' users' if tg_ids else 'open'}\n",
        )

    def _cmd_models(self, chat_id, args):
        from ugclaw.providers import PROVIDERS
        saved = self.config.get("saved_models", {})
        buttons = []
        for pid, meta in PROVIDERS.items():
            count = len(saved.get(pid, []))
            label = f"{meta['label']}  ({count} saved)"
            buttons.append([{"text": label, "callback_data": f"prov:{pid}"}])
        buttons.append([{"text": "❌ Cancel", "callback_data": "cancel"}])
        self.send_text(chat_id, "🔧 *Select a provider:*", reply_markup={"inline_keyboard": buttons})

    def _show_model_list(self, chat_id, provider_id, msg_id):
        from ugclaw.providers import PROVIDERS
        saved = self.config.get("saved_models", {}).get(provider_id, [])
        meta  = PROVIDERS.get(provider_id, {})
        if not saved:
            self.edit_text(
                chat_id, msg_id,
                f"⚠️ No saved models for *{meta.get('label', provider_id)}*.\n"
                "Run `ugclaw configure models` on your terminal to add models.",
            )
            return
        buttons = [
            [{"text": m, "callback_data": f"model:{provider_id}|{m}"}]
            for m in saved
        ]
        buttons.append([{"text": "❌ Cancel", "callback_data": "cancel"}])
        self.edit_text(
            chat_id, msg_id,
            f"🤖 *{meta.get('label', provider_id)}* — pick a model:",
            reply_markup={"inline_keyboard": buttons},
        )

    def _cmd_agents(self, chat_id, args):
        result = self.on_message(chat_id, "__LIST_AGENTS__")
        self.send_text(chat_id, result or "No subagents running.")

    def _cmd_kill(self, chat_id, args):
        if not args:
            self.send_text(chat_id, "Usage: `/kill <agent_id>`")
            return
        result = self.on_message(chat_id, f"__KILL_AGENT__ {args[0]}")
        self.send_text(chat_id, result)

    def _cmd_reset(self, chat_id, args):
        self.on_message(chat_id, "__RESET__")
        self.send_text(chat_id, "🔄 Session cleared. Memory is preserved.")

    def _cmd_new(self, chat_id, args):
        self.on_message(chat_id, "__NEW_SESSION__")
        self.send_text(chat_id, "✨ Fresh session started.")

    def _cmd_restart(self, chat_id, args):
        self.on_message(chat_id, "__RESTART__")
        self.send_text(chat_id, "🔁 Agent restarted.")

    def _cmd_usage(self, chat_id, args):
        result = self.on_message(chat_id, "__USAGE__")
        self.send_text(chat_id, result)

    def _cmd_tools(self, chat_id, args):
        from ugclaw.tools import TOOL_DEFINITIONS
        lines = ["🔧 *Available Tools*\n"]
        for t in TOOL_DEFINITIONS:
            fn   = t["function"]
            desc = fn.get("description", "")[:70]
            lines.append(f"• `{fn['name']}` — {desc}")
        self.send_text(chat_id, "\n".join(lines))

    def _cmd_memory(self, chat_id, args):
        result = self.on_message(chat_id, "__READ_MEMORY__")
        self.send_text(chat_id, result)

    def _cmd_approve(self, chat_id, args):
        if not args:
            self.send_text(chat_id, "Usage: `/approve <telegram_uid>`")
            return
        result = self.on_message(chat_id, f"__APPROVE__ {args[0]}")
        self.send_text(chat_id, result)

    def _cmd_deny(self, chat_id, args):
        if not args:
            self.send_text(chat_id, "Usage: `/deny <telegram_uid>`")
            return
        result = self.on_message(chat_id, f"__DENY__ {args[0]}")
        self.send_text(chat_id, result)

    def _cmd_allowed(self, chat_id, args):
        result = self.on_message(chat_id, "__LIST_ALLOWED__")
        self.send_text(chat_id, result)

    # ── Subagent completion callback ──────────────────────────────────────────

    def on_subagent_complete(self, sa):
        """Called by SubagentManager when a subagent finishes or fails."""
        chat_id = getattr(sa, "chat_id", None)
        if not chat_id:
            return
        aid    = getattr(sa, "id",     "?")
        status = getattr(sa, "status", "done")
        task   = getattr(sa, "task",   "")
        result = getattr(sa, "result", None)
        if status == "failed":
            icon = "❌"
            label = "failed"
        else:
            icon = "✅"
            label = "finished"
        msg = (
            f"{icon} *Subagent {label}*\n"
            f"ID   : `{aid}`\n"
            f"Task : {task[:120]}"
        )
        if result:
            msg += f"\n\n{result}"
        self.send_text(chat_id, msg)

    

    def _respond(self, chat_id: int, text: str, files: list):
        stop = threading.Event()

        def keep_typing():
            while not stop.is_set():
                self.send_typing(chat_id)
                time.sleep(4)

        typing = threading.Thread(target=keep_typing, daemon=True)
        typing.start()
        try:
            full = text
            if files:
                full += "\n\n[Uploaded files saved to: " + ", ".join(files) + "]"
            response = self.on_message(chat_id, full)
            self.send_text(chat_id, response)
        except Exception as e:
            self.send_text(chat_id, f"⚠️ Agent error: {e}")
        finally:
            stop.set()

    # ── File download ─────────────────────────────────────────────────────────

    def _download(self, file_id: str, filename: str) -> str:
        from ugclaw.paths import WORKSPACE
        info    = self._post("getFile", json={"file_id": file_id})
        tg_path = info["result"]["file_path"]
        url     = f"https://api.telegram.org/file/bot{self.token}/{tg_path}"
        r       = requests.get(url, timeout=30)

        dest   = WORKSPACE / filename
        stem, suffix = dest.stem, dest.suffix
        c = 1
        while dest.exists():
            dest = WORKSPACE / f"{stem}_{c}{suffix}"
            c += 1
        dest.write_bytes(r.content)
        print(f"[Telegram] Downloaded: {dest}")
        return str(dest)

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _post(self, method: str, **kwargs) -> dict:
        try:
            r = requests.post(f"{self.api}/{method}", timeout=35, **kwargs)
            return r.json()
        except Exception as e:
            print(f"[Telegram] {method} failed: {e}")
            return {}


def _chunks(text: str, size: int) -> list:
    return [text[i:i+size] for i in range(0, len(text), size)]
