# UGCLAW — Autonomous AI Agent

A minimal, self-hostable AI agent with a terminal interface, Telegram remote control,
browser automation, background subagents, and support for five LLM providers.

**Author:** Abubakar Bello — abubakarbello3914@gmail.com

---

## Features

- **Multi-provider LLM** — OpenAI, Anthropic, Google Gemini, Groq, OpenRouter
- **Always-on daemon** — survives terminal close, keeps Telegram active
- **Telegram bot** — full remote control with 15+ commands and autocomplete
- **Browser automation** — login to pages, fill forms, take screenshots
- **Background subagents** — spawn parallel AI tasks that run independently
- **Persistent memory** — AGENT.md identity file, long-term facts, session history
- **Interactive config TUI** — arrow-key model browser with live search

---

## Installation

```bash
git clone https://github.com/abubakarbello3914/ugclaw
cd ugclaw
python3 install.py
```

The installer will:
- Check Python version (3.10+ required)
- Install all dependencies
- Register the `ugclaw` command system-wide
- Install Playwright Chromium (optional, for browser tools)
- Create `~/.ugclaw/` data directory

---

## Quick start

```bash
# 1. Configure (interactive TUI)
ugclaw configure

# 2. Start the daemon
ugclaw start

# 3. Open terminal chat
ugclaw tui

# 4. (Optional) Start automatically at login
ugclaw enable
```

---

## Commands

```
ugclaw start              Start the background daemon
ugclaw stop               Stop the daemon
ugclaw restart            Restart the daemon
ugclaw status             Show system status
ugclaw tui                Open terminal chat interface
ugclaw logs               Tail the daemon log

ugclaw configure              Full configuration menu
ugclaw configure providers    Set API keys
ugclaw configure models       Fetch and select models
ugclaw configure telegram     Configure Telegram bot
ugclaw configure active       Set active provider/model
ugclaw configure advanced     Timeouts, limits, etc.

ugclaw telegram approve <uid>   Allow a Telegram user
ugclaw telegram deny <uid>      Block a Telegram user
ugclaw telegram list            Show allowed users
ugclaw telegram test            Test bot connection

ugclaw enable             Install as boot service (Linux/macOS)
ugclaw disable            Remove boot service
```

---

## Telegram Setup

1. Message **@BotFather** on Telegram → `/newbot`
2. Copy the token it gives you
3. Get your user ID from **@userinfobot**
4. Run:

```bash
ugclaw configure telegram
```

Enter the token and your user ID. The bot will register all commands with
Telegram automatically so you get autocomplete.

### Telegram Commands

| Command | Description |
|---|---|
| `/start` | Initialise session |
| `/help` | Show all commands |
| `/status` | Daemon and model status |
| `/models` | Switch provider and model |
| `/agents` | List background subagents |
| `/kill <id>` | Kill a subagent |
| `/reset` | Clear conversation history |
| `/new` | Fresh session (keeps memory) |
| `/restart` | Restart agent brain |
| `/usage` | Session statistics |
| `/tools` | List available tools |
| `/memory` | Show remembered facts |
| `/approve <uid>` | Approve a user |
| `/deny <uid>` | Remove a user's access |
| `/allowed` | List allowed users |

---

## Providers

| Provider | Models fetched from API |
|---|---|
| OpenAI | Yes |
| Anthropic | Static list |
| Google Gemini | Yes |
| Groq | Yes |
| OpenRouter | Yes (1000+ models, searchable) |

Run `ugclaw configure models` to fetch and save the models you want,
then switch between them anytime from TUI or Telegram.

---

## Project Structure

```
ugclaw/                   ← installable Python package
├── __init__.py           version, author info
├── __main__.py           python -m ugclaw support
├── main.py               CLI dispatcher
├── daemon.py             persistent gateway process
├── agent.py              LLM brain, tool-call loop
├── providers.py          unified multi-provider LLM client
├── tools.py              all tool definitions and implementations
├── subagents.py          background subagent manager
├── memory.py             AGENT.md, facts, session history
├── browser.py            Playwright browser automation
├── configure.py          interactive curses configuration TUI
├── telegram_bot.py       Telegram polling and command handling
├── config_manager.py     robust config load/save/validate
└── paths.py              central path definitions (~/.ugclaw)

config/
└── default_config.json   template, copied to ~/.ugclaw on install

install.py                one-shot installer
setup.py                  pip package entry point
```

Data is stored in `~/.ugclaw/` — independent of the project directory.

---

## Data Directory

```
~/.ugclaw/
├── config.json           your configuration
├── AGENT.md              agent identity file (auto-updated)
├── facts.json            long-term key-value memory
├── workspace/            files, screenshots, tool output
├── sessions/             per-session conversation history
└── logs/daemon.log       daemon log file
```

---

## License

MIT — see [LICENSE](LICENSE)

