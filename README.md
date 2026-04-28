<div align="center">

```
 ██╗   ██╗ ██████╗  ██████╗██╗      █████╗ ██╗    ██╗
 ██║   ██║██╔════╝ ██╔════╝██║     ██╔══██╗██║    ██║
 ██║   ██║██║  ███╗██║     ██║     ███████║██║ █╗ ██║
 ██║   ██║██║   ██║██║     ██║     ██╔══██║██║███╗██║
 ╚██████╔╝╚██████╔╝╚██████╗███████╗██║  ██║╚███╔███╔╝
  ╚═════╝  ╚═════╝  ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝
```

**Autonomous AI Agent System**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Telegram](https://img.shields.io/badge/Channel-@UGCLAW-26A5E4?style=flat-square&logo=telegram)](https://t.me/UGCLAW)
[![Version](https://img.shields.io/badge/Version-3.0.0-purple?style=flat-square)](https://github.com/Abubakar-yerbour/UGCLAW/releases)

*A persistent, tool-calling AI agent you control entirely from Telegram or your terminal — runs 24/7 as a background daemon on your own server.*

</div>

---

## What is UGCLAW?

UGCLAW is a self-hosted autonomous AI agent that runs as a persistent background daemon on your Linux server or machine. You interact with it through Telegram or a terminal interface, and it can execute shell commands, browse the web, manage files, and spawn parallel background subagents to handle long-running tasks — all without blocking your conversation.

It is provider-agnostic: you can use OpenAI, Anthropic, or any compatible LLM, and switch models mid-session without losing history. Subagents can even run on a different model than your main session.

---

## Features

- **Persistent daemon** — runs in the background, survives terminal exits, auto-restarts on boot
- **Telegram interface** — full agent control from your phone, anywhere in the world
- **Terminal UI** — interactive chat directly in your terminal
- **Tool-calling agent** — executes real tools: shell, web fetch, file read/write, browser automation
- **Parallel subagents** — spawn multiple background AI workers for long tasks; get notified on Telegram when they finish
- **Multi-provider** — OpenAI, Anthropic Claude, and any OpenAI-compatible API; hot-swap mid-session
- **Persistent memory** — facts and `AGENT.md` survive across sessions
- **Browser automation** — full Chromium via Playwright: navigate, login, screenshot, execute JS
- **Auto-update** — checks GitHub for new releases on startup and notifies via Telegram daily
- **Boot service** — one command to install as a systemd or launchd service

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/Abubakar-yerbour/UGCLAW.git
cd UGCLAW

# Recommended: use a virtual environment
python3 -m venv myenv
source myenv/bin/activate

python install.py
```

### 2. Configure

```bash
ugclaw configure
```

This walks you through:
- Setting your LLM provider API keys (OpenAI, Anthropic, etc.)
- Setting your Telegram bot token (get one from [@BotFather](https://t.me/BotFather))
- Fetching and selecting your model

Or jump to a specific section:

```bash
ugclaw configure providers   # API keys
ugclaw configure telegram    # Telegram bot token
ugclaw configure models      # fetch and select models
ugclaw configure active      # set active provider and model
```

### 3. Start

```bash
ugclaw start
```

### 4. Use it

```bash
ugclaw tui        # terminal chat interface
```

Or open Telegram and start talking to your bot.

---

## Telegram Commands

| Command | Description |
|---|---|
| `/start` | Initialise or resume your session |
| `/help` | Show all available commands |
| `/status` | Daemon and model status |
| `/models` | Switch AI provider and model |
| `/agents` | List all background subagents |
| `/kill <id>` | Kill a running subagent |
| `/reset` | Clear current conversation history |
| `/new` | Start a fresh session (keeps memory) |
| `/restart` | Restart the agent brain for this chat |
| `/usage` | Show session usage statistics |
| `/tools` | List all tools the agent can use |
| `/memory` | Show what the agent remembers |
| `/approve <uid>` | Approve a Telegram user |
| `/deny <uid>` | Remove a user's access |
| `/allowed` | List approved Telegram user IDs |

Or just talk naturally — no slash command needed for regular messages.

---

## Available Tools

| Tool | Description |
|---|---|
| `exec` | Run shell commands (nmap, curl, scripts, anything) |
| `web_fetch` | Fetch a URL and return readable text + links |
| `read_file` | Read a file from the workspace |
| `write_file` | Write content to a file |
| `list_files` | List files in the workspace |
| `delete_file` | Delete a file |
| `browser_navigate` | Open a URL in real Chromium |
| `browser_fill` | Fill a form field by CSS selector |
| `browser_click` | Click an element |
| `browser_login` | High-level login in one call |
| `browser_get_text` | Get readable text of current page |
| `browser_get_html` | Get raw HTML of current page |
| `browser_screenshot` | Screenshot the current page |
| `browser_execute_js` | Execute JavaScript in the browser |
| `create_subagent` | Spawn a background AI subagent |
| `list_subagents` | List all running subagents |
| `get_subagent_status` | Get status of a subagent |
| `get_subagent_logs` | Get full logs from a subagent |
| `kill_subagent` | Stop a running subagent |
| `update_memory` | Persist a fact or update AGENT.md |
| `read_memory` | Read stored facts and AGENT.md |
| `delete_memory` | Delete a stored fact |
| `send_message` | Send a Telegram message to a chat |
| `send_file` | Send a file to a Telegram chat |
| `manage_telegram_access` | Add/remove Telegram users from allowlist |

---

## Subagents

Subagents are background AI workers you can spawn for long-running tasks. They run in parallel without blocking your main conversation, and notify you on Telegram when they finish with their full result.

**Example usage** (just talk naturally):

```
Spawn a subagent to do a full nmap scan on 192.168.1.1 and report findings
```

```
Create a subagent using GPT-4o to write a full penetration testing report
for the findings in /workspace/scan.txt
```

```
Spawn three subagents: one to scan port 80, one for port 443, one to check DNS
```

Each subagent can use a different model or provider than your main session.

---

## CLI Reference

```
ugclaw start              Start the daemon
ugclaw stop               Stop the daemon
ugclaw restart            Restart the daemon
ugclaw status             Show daemon and system status
ugclaw tui                Open terminal chat interface
ugclaw logs               Tail the daemon log (Ctrl+C to exit)
ugclaw update             Check for updates and install
ugclaw configure          Full configuration menu
ugclaw telegram approve <uid>   Allow a Telegram user
ugclaw telegram deny <uid>      Remove a user's access
ugclaw telegram list            List allowed users
ugclaw telegram test            Test bot connection
ugclaw enable             Install as a boot service (systemd/launchd)
ugclaw disable            Remove boot service
ugclaw --version          Show version
ugclaw --help             Show help
```

---

## Project Structure

```
UGCLAW/
├── install.py              # Installer
├── requirements.txt        # Python dependencies
├── setup.py                # Package setup
├── default_config.json     # Config template
└── ugclaw/
    ├── __init__.py         # Version info
    ├── agent.py            # LLM tool-calling loop
    ├── browser.py          # Playwright browser session
    ├── config_manager.py   # Config load/save
    ├── configure.py        # Interactive configuration wizard
    ├── daemon.py           # Persistent background daemon
    ├── main.py             # CLI entry point
    ├── memory.py           # Persistent memory (facts + AGENT.md)
    ├── paths.py            # Filesystem paths
    ├── providers.py        # LLM provider clients
    ├── subagents.py        # Background subagent manager
    ├── telegram_bot.py     # Telegram bot interface
    ├── tools.py            # All agent tools
    └── updater.py          # Auto-update checker
```

---

## Data & Config

All runtime data lives in `~/.ugclaw/`:

```
~/.ugclaw/
├── config.json         # Your configuration (API keys, tokens, settings)
├── workspace/          # Agent working directory (files, downloads)
├── sessions/           # Conversation history per session
└── logs/
    └── daemon.log      # Daemon log
```

---

## Boot Service

Install UGCLAW as a system service so it starts automatically:

```bash
ugclaw enable    # install and start service
ugclaw disable   # remove service
```

Supports **systemd** (Linux) and **launchd** (macOS).

---

## Updating

```bash
ugclaw update
```

UGCLAW also checks for updates silently on every `ugclaw start` and `ugclaw tui`, and sends a Telegram notification to active sessions once per day if a newer version is available.

---

## Requirements

- Python 3.10+
- Linux or macOS (Windows not officially supported)
- An API key for at least one supported LLM provider
- A Telegram bot token (optional but recommended) — get one from [@BotFather](https://t.me/BotFather)

---

## License

MIT — see [LICENSE](LICENSE)

---

<div align="center">

**Built by [Abubakar Bello](mailto:abubakarbello3914@gmail.com)**

[Telegram Channel](https://t.me/UGCLAW) · [Report a Bug](https://github.com/Abubakar-yerbour/UGCLAW/issues) · [Request a Feature](https://github.com/Abubakar-yerbour/UGCLAW/issues)

</div>
