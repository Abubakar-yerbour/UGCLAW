"""
tools.py — every tool UGCLAW can call.

Tools are defined in OpenAI function-calling schema and implemented
as methods on ToolsHandler. All methods follow:
    _tool_name(args, context) -> (result_str, ctx_update | None)
"""

import subprocess
import json
import requests
from pathlib import Path
from typing import Tuple, Optional

from ugclaw.paths import WORKSPACE

try:
    from bs4 import BeautifulSoup
    _BS4 = True
except ImportError:
    _BS4 = False


# ── Tool definitions ──────────────────────────────────────────────────────────

TOOL_DEFINITIONS = [

    # Shell
    {
        "type": "function",
        "function": {
            "name": "exec",
            "description": (
                "Run a shell command (with timeout). Use for recon, nmap, curl, "
                "whois, ping, scripting, file operations, and any system task. "
                "Runs inside the workspace directory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout": {"type": "integer", "description": "Max seconds (default 30)"},
                },
                "required": ["command"],
            },
        },
    },

    # Web
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch a URL and return readable text. Optionally extract all links.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url":           {"type": "string"},
                    "extract_links": {"type": "boolean"},
                },
                "required": ["url"],
            },
        },
    },

    # Files
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the workspace. Path relative to workspace or absolute.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file. Creates parent directories if needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in the workspace or a subdirectory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Subdirectory (optional, default: workspace root)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file from the workspace.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },

    # Browser
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Open a URL in a real Chromium browser. Handles JavaScript, cookies, and sessions.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_fill",
            "description": (
                "Fill an input field by CSS selector. "
                "Examples: '#username', 'input[name=email]', '.login-input'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "value":    {"type": "string"},
                },
                "required": ["selector", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Click an element by CSS selector. Waits for page load after click.",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": "string"}},
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_login",
            "description": (
                "High-level login: navigate to URL, fill all credential fields, "
                "click submit — all in one call. Returns page state after login."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url":             {"type": "string"},
                    "fields":          {
                        "type":                 "object",
                        "description":          "CSS selector → value, e.g. {'#user': 'admin', '#pass': 'secret'}",
                        "additionalProperties": {"type": "string"},
                    },
                    "submit_selector": {"type": "string"},
                },
                "required": ["url", "fields", "submit_selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_get_text",
            "description": "Get readable text content of the current browser page.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_get_html",
            "description": "Get raw HTML of the current browser page (first 10k chars).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Screenshot the current page. Returns the saved file path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_execute_js",
            "description": "Execute JavaScript in the browser and return the result.",
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
            },
        },
    },

    # Subagents
    {
        "type": "function",
        "function": {
            "name": "create_subagent",
            "description": (
                "Spawn a background AI subagent for a long-running task. "
                "Does not block the conversation. Optionally assign a specific model."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task":        {"type": "string"},
                    "target":      {"type": "string"},
                    "provider_id": {"type": "string"},
                    "model":       {"type": "string"},
                },
                "required": ["task"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_subagents",
            "description": "List all subagents and their current status.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_subagent_status",
            "description": "Get status of a subagent. Omit agent_id to use the last spawned one.",
            "parameters": {
                "type": "object",
                "properties": {"agent_id": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_subagent_logs",
            "description": "Get full logs from a subagent. Omit agent_id for the last one.",
            "parameters": {
                "type": "object",
                "properties": {"agent_id": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kill_subagent",
            "description": "Stop a running subagent.",
            "parameters": {
                "type": "object",
                "properties": {"agent_id": {"type": "string"}},
            },
        },
    },

    # Memory
    {
        "type": "function",
        "function": {
            "name": "update_memory",
            "description": (
                "Persist a fact or update AGENT.md. "
                "Call this when the user shares their name, nickname, preferences, "
                "or explicitly asks you to remember something."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "type":  {
                        "type": "string",
                        "enum": ["fact", "agent_md_section"],
                    },
                    "key":   {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["type", "key", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_memory",
            "description": "Read AGENT.md, stored facts, or session list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["agent_md", "facts", "sessions"]},
                },
                "required": ["type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_memory",
            "description": "Delete a stored fact by key.",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            },
        },
    },

    # Telegram access management
    {
        "type": "function",
        "function": {
            "name": "manage_telegram_access",
            "description": (
                "Add or remove a Telegram user ID from the allowlist. "
                "Changes take effect immediately and are saved to config."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action":  {"type": "string", "enum": ["add", "remove", "list"]},
                    "user_id": {"type": "integer"},
                },
                "required": ["action"],
            },
        },
    },

    # Telegram send
    {
        "type": "function",
        "function": {
            "name": "send_file",
            "description": "Send a file to a Telegram chat.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string"},
                    "chat_id": {"type": "string"},
                    "caption": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Send a text message to a Telegram chat.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text":    {"type": "string"},
                    "chat_id": {"type": "string"},
                },
                "required": ["text"],
            },
        },
    },
]


# ── ToolsHandler ──────────────────────────────────────────────────────────────

class ToolsHandler:
    def __init__(self, config: dict, subagent_manager, memory, config_path: Path):
        self.config      = config
        self.subagents   = subagent_manager
        self.memory      = memory
        self.config_path = config_path
        self.workspace   = WORKSPACE
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._timeout    = config.get("tool_timeout", 30)
        self.telegram       = None   # injected by daemon after TelegramBot is created
        self.spawn_subagent = None   # injected by daemon; wrapper that forwards chat_id
        self._browser       = None   # lazy-init BrowserSession

    def definitions(self) -> list:
        return TOOL_DEFINITIONS

    def call(self, name: str, args: dict, context: dict) -> Tuple[str, Optional[dict]]:
        dispatch = {
            "exec":                   self._exec,
            "web_fetch":              self._web_fetch,
            "read_file":              self._read_file,
            "write_file":             self._write_file,
            "list_files":             self._list_files,
            "delete_file":            self._delete_file,
            "browser_navigate":       self._browser_navigate,
            "browser_fill":           self._browser_fill,
            "browser_click":          self._browser_click,
            "browser_login":          self._browser_login,
            "browser_get_text":       self._browser_get_text,
            "browser_get_html":       self._browser_get_html,
            "browser_screenshot":     self._browser_screenshot,
            "browser_execute_js":     self._browser_execute_js,
            "create_subagent":        self._create_subagent,
            "list_subagents":         self._list_subagents,
            "get_subagent_status":    self._get_subagent_status,
            "get_subagent_logs":      self._get_subagent_logs,
            "kill_subagent":          self._kill_subagent,
            "update_memory":          self._update_memory,
            "read_memory":            self._read_memory,
            "delete_memory":          self._delete_memory,
            "manage_telegram_access": self._manage_telegram_access,
            "send_file":              self._send_file,
            "send_message":           self._send_message,
        }
        fn = dispatch.get(name)
        if not fn:
            return f"❌ Unknown tool: {name}", None
        try:
            return fn(args, context)
        except Exception as e:
            return f"❌ [{name}] error: {e}", None

    # ── Shell ─────────────────────────────────────────────────────────────────

    def _exec(self, args, ctx):
        cmd     = args["command"]
        timeout = int(args.get("timeout", self._timeout))
        try:
            proc = subprocess.run(
                cmd, shell=True,
                capture_output=True, text=True,
                timeout=timeout,
                cwd=str(self.workspace),
            )
            out = (proc.stdout + proc.stderr).strip()
            return (out[:8000] if out else "(no output)"), None
        except subprocess.TimeoutExpired:
            return f"⏰ Timed out after {timeout}s.", None

    # ── Web ───────────────────────────────────────────────────────────────────

    def _web_fetch(self, args, ctx):
        url   = args["url"]
        links = args.get("extract_links", False)
        try:
            r = requests.get(
                url, timeout=15,
                headers={"User-Agent": "Mozilla/5.0 UGCLAW/3.0"},
            )
        except requests.RequestException as e:
            return f"❌ Fetch failed: {e}", None

        ct = r.headers.get("content-type", "")
        if "text" not in ct and "json" not in ct:
            return f"[Binary content — {len(r.content)} bytes — {ct}]", None

        if _BS4:
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            found_links = (
                [a.get("href", "") for a in soup.find_all("a", href=True)][:60]
                if links else []
            )
        else:
            text        = r.text
            found_links = []

        result = f"URL: {url}\nHTTP {r.status_code}\n\n{text[:6000]}"
        if found_links:
            result += "\n\n── Links ──\n" + "\n".join(found_links)
        return result, None

    # ── Files ─────────────────────────────────────────────────────────────────

    def _read_file(self, args, ctx):
        p = self._resolve(args["path"])
        if not p.exists():
            return f"❌ Not found: {p}", None
        return p.read_text(errors="replace")[:8000], None

    def _write_file(self, args, ctx):
        p = self._resolve(args["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(args["content"], encoding="utf-8")
        return f"✅ Written: {p} ({len(args['content'])} chars)", None

    def _list_files(self, args, ctx):
        base = self._resolve(args.get("path", "."))
        if not base.exists():
            return f"❌ Path not found: {base}", None
        entries = sorted(base.iterdir(), key=lambda x: (x.is_file(), x.name))
        lines = [
            f"{'📁' if e.is_dir() else '📄'} {e.name}"
            + (f"  ({e.stat().st_size} bytes)" if e.is_file() else "")
            for e in entries
        ]
        return f"📂 {base}\n" + "\n".join(lines) if lines else "(empty)", None

    def _delete_file(self, args, ctx):
        p = self._resolve(args["path"])
        if not p.exists():
            return f"❌ Not found: {p}", None
        p.unlink()
        return f"✅ Deleted: {p}", None

    # ── Browser ───────────────────────────────────────────────────────────────

    def _get_browser(self):
        if self._browser is None:
            from ugclaw.browser import BrowserSession
            headless = self.config.get("browser_headless", True)
            self._browser = BrowserSession(self.workspace, headless=headless)
        return self._browser

    def _browser_navigate(self, args, ctx):
        return self._get_browser().navigate(args["url"]), None

    def _browser_fill(self, args, ctx):
        return self._get_browser().fill(args["selector"], args["value"]), None

    def _browser_click(self, args, ctx):
        return self._get_browser().click(args["selector"]), None

    def _browser_login(self, args, ctx):
        return self._get_browser().login(
            args["url"], args["fields"], args["submit_selector"]
        ), None

    def _browser_get_text(self, args, ctx):
        return self._get_browser().get_text(), None

    def _browser_get_html(self, args, ctx):
        return self._get_browser().get_html(), None

    def _browser_screenshot(self, args, ctx):
        path = self._get_browser().screenshot(args.get("filename", "screenshot.png"))
        return f"✅ Screenshot saved: {path}", {"last_screenshot": path}

    def _browser_execute_js(self, args, ctx):
        return self._get_browser().execute_js(args["code"]), None

    # ── Subagents ─────────────────────────────────────────────────────────────

    def _create_subagent(self, args, ctx):
        chat_id = ctx.get("chat_id")
        aid = self.spawn_subagent(
            task=args["task"],
            target=args.get("target", ""),
            provider_id=args.get("provider_id"),
            model=args.get("model"),
            chat_id=chat_id,
        )
        pid  = args.get("provider_id", "default")
        mod  = args.get("model", "default")
        return (
            f"🚀 Subagent spawned — id: `{aid}`\n"
            f"Task  : {args['task']}\n"
            f"Model : {pid}/{mod}",
            {"last_agent_id": aid},
        )

    def _list_subagents(self, args, ctx):
        agents = self.subagents.list_all()
        if not agents:
            return "No subagents running.", None
        rows = [
            f"• `{a['id']}` [{a['status']}] {a['task'][:55]}"
            for a in agents
        ]
        return "\n".join(rows), None

    def _get_subagent_status(self, args, ctx):
        aid = args.get("agent_id") or ctx.get("last_agent_id")
        if not aid:
            return "❌ No agent_id — spawn a subagent first.", None
        return json.dumps(self.subagents.status(aid), indent=2), None

    def _get_subagent_logs(self, args, ctx):
        aid = args.get("agent_id") or ctx.get("last_agent_id")
        if not aid:
            return "❌ No agent_id specified.", None
        return self.subagents.logs(aid), None

    def _kill_subagent(self, args, ctx):
        aid = args.get("agent_id") or ctx.get("last_agent_id")
        if not aid:
            return "❌ No agent_id specified.", None
        return self.subagents.kill(aid), None

    # ── Memory ────────────────────────────────────────────────────────────────

    def _update_memory(self, args, ctx):
        t = args["type"]
        if t == "fact":
            self.memory.set_fact(args["key"], args["value"])
            return f"✅ Remembered: {args['key']} = {args['value']}", None
        elif t == "agent_md_section":
            self.memory.patch_agent_md(args["key"], args["value"])
            return f"✅ AGENT.md updated: [{args['key']}]", None
        return "❌ Unknown memory type.", None

    def _read_memory(self, args, ctx):
        t = args["type"]
        if t == "agent_md":
            return self.memory.read_agent_md(), None
        if t == "facts":
            facts = self.memory.load_facts()
            return json.dumps(facts, indent=2) if facts else "(no facts stored)", None
        if t == "sessions":
            sessions = self.memory.list_sessions()
            if not sessions:
                return "(no saved sessions)", None
            return "\n".join(
                f"• {s['id']}  {s['messages']} messages  {s['modified']}"
                for s in sessions
            ), None
        return "❌ Unknown type.", None

    def _delete_memory(self, args, ctx):
        deleted = self.memory.delete_fact(args["key"])
        return (
            f"✅ Deleted fact: {args['key']}"
            if deleted
            else f"❌ Fact not found: {args['key']}"
        ), None

    # ── Telegram access ───────────────────────────────────────────────────────

    def _manage_telegram_access(self, args, ctx):
        action = args["action"]

        try:
            from ugclaw.config_manager import load_config, save_config
            cfg = load_config()
        except Exception as e:
            return f"❌ Could not load config: {e}", None

        allowed: list = cfg.get("allowed_telegram_ids", [])

        if action == "list":
            if not allowed:
                return "All Telegram users are currently allowed (no restrictions).", None
            return "Allowed IDs:\n" + "\n".join(f"• `{uid}`" for uid in allowed), None

        uid = args.get("user_id")
        if uid is None:
            return "❌ user_id required for add/remove.", None

        if action == "add":
            if uid not in allowed:
                allowed.append(uid)
                cfg["allowed_telegram_ids"] = allowed
                save_config(cfg)
                self.config["allowed_telegram_ids"] = allowed
                if self.telegram:
                    self.telegram.allowed_ids.add(uid)
            return f"✅ User `{uid}` approved.", None

        if action == "remove":
            if uid in allowed:
                allowed.remove(uid)
                cfg["allowed_telegram_ids"] = allowed
                save_config(cfg)
                self.config["allowed_telegram_ids"] = allowed
                if self.telegram:
                    self.telegram.allowed_ids.discard(uid)
            return f"✅ User `{uid}` removed.", None

        return "❌ Unknown action.", None

    # ── Telegram send ─────────────────────────────────────────────────────────

    def _send_file(self, args, ctx):
        if not self.telegram:
            return "⚠️ Telegram not connected.", None
        chat_id = args.get("chat_id") or ctx.get("chat_id")
        if not chat_id:
            return "❌ No chat_id available.", None
        p = self._resolve(args["path"])
        if not p.exists():
            return f"❌ File not found: {p}", None
        self.telegram.send_file(chat_id, str(p), args.get("caption"))
        return f"✅ Sent: {p.name}", None

    def _send_message(self, args, ctx):
        if not self.telegram:
            return "⚠️ Telegram not connected.", None
        chat_id = args.get("chat_id") or ctx.get("chat_id")
        if not chat_id:
            return "❌ No chat_id available.", None
        self.telegram.send_text(chat_id, args["text"])
        return "✅ Sent.", None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _resolve(self, path_str: str) -> Path:
        p = Path(str(path_str))
        return p if p.is_absolute() else self.workspace / p
