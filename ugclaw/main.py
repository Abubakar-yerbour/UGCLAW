"""
main.py — UGCLAW command-line interface.

After installation:
  ugclaw start
  ugclaw stop / restart / status / logs
  ugclaw tui
  ugclaw configure [section]
  ugclaw telegram approve/deny/list/test <uid>
  ugclaw enable   (boot service)
  ugclaw disable  (remove boot service)
  ugclaw --version / --help
"""

import os
import sys
import json
import time
import socket
import signal
import subprocess
import threading
from pathlib import Path

from ugclaw import __version__, __author__, __email__
from ugclaw.paths import (
    ensure_dirs, CONFIG_FILE, SOCKET_PATH, PID_FILE, DAEMON_LOG, BASE_DIR
)


# ── Banner ────────────────────────────────────────────────────────────────────

BANNER = f"""
 ██╗   ██╗ ██████╗  ██████╗██╗      █████╗ ██╗    ██╗
 ██║   ██║██╔════╝ ██╔════╝██║     ██╔══██╗██║    ██║
 ██║   ██║██║  ███╗██║     ██║     ███████║██║ █╗ ██║
 ██║   ██║██║   ██║██║     ██║     ██╔══██║██║███╗██║
 ╚██████╔╝╚██████╔╝╚██████╗███████╗██║  ██║╚███╔███╔╝
  ╚═════╝  ╚═════╝  ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝

  Autonomous AI Agent System  v{__version__}
  {__author__} <{__email__}>
"""

HELP_TEXT = f"""
{BANNER}
Usage: ugclaw <command> [options]

Core commands:
  start              Start the UGCLAW daemon
  stop               Stop the daemon
  restart            Restart the daemon
  status             Show daemon and system status
  tui                Open the terminal chat interface
  logs               Tail the daemon log (Ctrl+C to exit)

Configuration:
  configure              Open full configuration menu
  configure providers    Configure API keys
  configure models       Fetch and select models
  configure active       Set active provider and model
  configure telegram     Configure Telegram bot
  configure advanced     Timeouts, token limits, etc.
  configure --help       Show configure help

Telegram management:
  telegram approve <uid>   Allow a user by Telegram ID
  telegram deny <uid>      Remove a user's access
  telegram list            List all allowed users
  telegram test            Test bot connection

System:
  enable             Install and enable as a boot service
  disable            Remove the boot service
  update             Check for updates and install if available
  --version          Show version
  --help             Show this help

TUI shortcuts (inside ugclaw tui):
  /reset             Clear conversation history
  /agents            List subagents
  /model <p> <m>     Switch model
  exit               Leave TUI (daemon keeps running)

Config file: {CONFIG_FILE}
Data dir:    {BASE_DIR}
"""


# ── Config helpers ────────────────────────────────────────────────────────────

def _load_config() -> dict:
    ensure_dirs()
    from ugclaw.config_manager import load_config
    return load_config()


# ── Daemon management ─────────────────────────────────────────────────────────

def _get_pid() -> int | None:
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return pid
    except Exception:
        return None


def cmd_start():
    if _get_pid():
        print("⚡ UGCLAW daemon is already running.")
        print(f"   Run: ugclaw tui   to open a terminal session")
        return

    # Silent background update check — prints one line if behind, never blocks
    from ugclaw.updater import check_silent
    check_silent()

    ensure_dirs()
    config = _load_config()
    print("⚡ Starting UGCLAW daemon…")

    daemon_mod = Path(__file__).parent / "daemon.py"
    DAEMON_LOG.parent.mkdir(parents=True, exist_ok=True)

    with open(str(DAEMON_LOG), "a") as lf:
        subprocess.Popen(
            [sys.executable, str(daemon_mod)],
            stdout=lf, stderr=lf,
            start_new_session=True,
            cwd=str(BASE_DIR),
        )

    # Wait for socket (up to 10s)
    for _ in range(20):
        if SOCKET_PATH.exists() and _get_pid():
            break
        time.sleep(0.5)

    pid = _get_pid()
    if pid:
        tg = config.get("telegram_bot_token", "")
        print(f"✅ UGCLAW started (PID {pid})")
        print(f"   Telegram : {'active' if tg else 'disabled — set token via: ugclaw configure telegram'}")
        print(f"   Log      : {DAEMON_LOG}")
        print(f"   Config   : {CONFIG_FILE}")
        print(f"\n   ugclaw tui   to open terminal interface")
    else:
        print("❌ Daemon failed to start.")
        print(f"   Check logs: {DAEMON_LOG}")
        sys.exit(1)


def cmd_stop():
    pid = _get_pid()
    if not pid:
        print("⚠️  UGCLAW daemon is not running.")
        return
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"✅ UGCLAW stopped (PID {pid}).")
    except ProcessLookupError:
        print("⚠️  Process already gone — cleaning up.")
    for p in (PID_FILE, SOCKET_PATH):
        try:
            p.unlink()
        except Exception:
            pass


def cmd_restart():
    cmd_stop()
    time.sleep(1)
    cmd_start()


def cmd_status():
    config = _load_config()
    pid    = _get_pid()
    print(BANNER)
    print(f"  Daemon   : {'✅ running (PID ' + str(pid) + ')' if pid else '❌ stopped'}")
    print(f"  Socket   : {'✅ ' + str(SOCKET_PATH) if SOCKET_PATH.exists() else '❌ not found'}")
    print(f"  Provider : {config.get('active_provider', '?')} / {config.get('active_model', '?')}")
    tg   = config.get("telegram_bot_token", "")
    ids  = config.get("allowed_telegram_ids", [])
    print(f"  Telegram : {'✅ configured' if tg else '❌ not configured'}")
    if ids:
        print(f"  Allowed  : {ids}")
    print(f"  Config   : {CONFIG_FILE}")
    print(f"  Data     : {BASE_DIR}")
    print(f"  Log      : {DAEMON_LOG}")


def cmd_logs():
    if not DAEMON_LOG.exists():
        print(f"No log file yet: {DAEMON_LOG}")
        print("Start the daemon first: ugclaw start")
        return
    try:
        subprocess.run(["tail", "-f", str(DAEMON_LOG)])
    except KeyboardInterrupt:
        pass


# ── TUI socket client ─────────────────────────────────────────────────────────

def cmd_update():
    from ugclaw.updater import run_update
    run_update()


def cmd_tui():
    if not _get_pid():
        print("⚡ Daemon not running — starting it…")
        cmd_start()
        time.sleep(1)

    # Silent background update check
    from ugclaw.updater import check_silent
    check_silent()

    if not SOCKET_PATH.exists():
        print("❌ Cannot connect to daemon. Run: ugclaw start")
        sys.exit(1)

    config = _load_config()
    print(BANNER)
    print(f"  Provider : {config.get('active_provider','?')} / {config.get('active_model','?')}")
    print("  Tip: close this terminal anytime — the daemon keeps running.")
    print("  Commands: /reset  /agents  /model <provider> <model>  exit")
    print("─" * 56)

    # Greeting
    resp = _send("terminal", "Introduce yourself in 2 sentences: your name, what you can do.")
    if resp:
        print(f"\n🤖  {resp}\n")
    print("─" * 56 + "\n")

    while True:
        try:
            text = input("▶  ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n👋  TUI closed. Daemon still running.\n")
            break

        if not text:
            continue
        if text.lower() in ("exit", "quit", "/exit", "/quit"):
            print("👋  TUI closed. Daemon still running.\n")
            break

        # TUI shortcuts
        if text == "/reset":
            print(_send("terminal", "__RESET__") or "Reset.")
            print()
            continue
        if text == "/agents":
            print(_send("terminal", "__LIST_AGENTS__") or "No subagents.")
            print()
            continue
        if text.startswith("/model "):
            parts = text.split()
            if len(parts) == 3:
                print(_send("terminal", f"__SWITCH_MODEL__ {parts[1]} {parts[2]}"))
            else:
                print("Usage: /model <provider> <model>")
            print()
            continue

        print()
        resp = _send("terminal", text)
        print(f"🤖  {resp}\n" if resp else "⚠️  No response.\n")


def _send(session: str, text: str, timeout: int = 120) -> str | None:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(str(SOCKET_PATH))
            s.settimeout(timeout)
            payload = json.dumps({"session": session, "text": text}) + "\n"
            s.sendall(payload.encode("utf-8"))
            buf = b""
            while b"\n" not in buf:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
            line = buf.split(b"\n")[0]
            data = json.loads(line)
            return data.get("text") or data.get("error")
    except ConnectionRefusedError:
        print("❌ Daemon not reachable. Run: ugclaw start")
        return None
    except Exception as e:
        print(f"❌ Socket error: {e}")
        return None


# ── Configure ─────────────────────────────────────────────────────────────────

def cmd_configure(args: list):
    if args and args[0] == "--help":
        print("ugclaw configure [section]\n")
        print("Sections: providers, models, active, telegram, advanced")
        return

    if args and args[0] == "--reset-config":
        _reset_config()
        return

    section = args[0] if args else None
    from ugclaw.configure import run_configure
    run_configure(section)


def _reset_config():
    from ugclaw.paths import DEFAULT_CONFIG
    import shutil
    backup = CONFIG_FILE.with_suffix(".json.bak")
    if CONFIG_FILE.exists():
        shutil.copy(CONFIG_FILE, backup)
        print(f"  Backup saved: {backup}")
    if DEFAULT_CONFIG.exists():
        shutil.copy(DEFAULT_CONFIG, CONFIG_FILE)
        print(f"✅ Config reset to defaults.")
    else:
        print("❌ Default config template not found.")


# ── Telegram CLI ──────────────────────────────────────────────────────────────

def cmd_telegram(args: list):
    if not args:
        print("Usage: ugclaw telegram <approve|deny|list|test> [uid]")
        return

    sub = args[0].lower()
    config = _load_config()

    if sub == "list":
        allowed = config.get("allowed_telegram_ids", [])
        if not allowed:
            print("All users are allowed (no restrictions).")
        else:
            print("Allowed Telegram IDs:")
            for uid in allowed:
                print(f"  {uid}")
        return

    if sub == "test":
        token = config.get("telegram_bot_token", "")
        if not token:
            print("❌ No bot token configured. Run: ugclaw configure telegram")
            return
        import requests
        try:
            r    = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=8)
            data = r.json()
            if data.get("ok"):
                info = data["result"]
                print(f"✅ Bot connected: @{info['username']} (ID {info['id']})")
            else:
                print(f"❌ Failed: {data.get('description')}")
        except Exception as e:
            print(f"❌ Error: {e}")
        return

    if sub in ("approve", "deny"):
        if len(args) < 2:
            print(f"Usage: ugclaw telegram {sub} <telegram_uid>")
            return
        try:
            uid = int(args[1])
        except ValueError:
            print("❌ UID must be a number.")
            return

        from ugclaw.config_manager import save_config
        allowed = config.get("allowed_telegram_ids", [])

        if sub == "approve":
            if uid not in allowed:
                allowed.append(uid)
                config["allowed_telegram_ids"] = allowed
                save_config(config)
                print(f"✅ User {uid} approved.")
                # If daemon is running, notify it live
                if _get_pid():
                    _send("cli", f"__APPROVE__ {uid}")
            else:
                print(f"ℹ️  User {uid} is already approved.")

        elif sub == "deny":
            if uid in allowed:
                allowed.remove(uid)
                config["allowed_telegram_ids"] = allowed
                save_config(config)
                print(f"✅ User {uid} denied.")
                if _get_pid():
                    _send("cli", f"__DENY__ {uid}")
            else:
                print(f"ℹ️  User {uid} is not in the allowed list.")
        return

    print(f"❌ Unknown telegram subcommand: {sub}")
    print("Usage: ugclaw telegram <approve|deny|list|test> [uid]")


# ── Boot service ──────────────────────────────────────────────────────────────

def cmd_enable():
    import platform
    plat = platform.system()

    if plat == "Linux":
        _enable_systemd()
    elif plat == "Darwin":
        _enable_launchd()
    else:
        print(f"⚠️  Boot service not supported on {plat}.")
        print("   You can manually add 'ugclaw start' to your startup scripts.")


def cmd_disable():
    import platform
    plat = platform.system()
    if plat == "Linux":
        _disable_systemd()
    elif plat == "Darwin":
        _disable_launchd()
    else:
        print(f"⚠️  Boot service not supported on {plat}.")


def _enable_systemd():
    unit_dir  = Path.home() / ".config" / "systemd" / "user"
    unit_file = unit_dir / "ugclaw.service"
    unit_dir.mkdir(parents=True, exist_ok=True)

    ugclaw_bin = subprocess.run(
        ["which", "ugclaw"], capture_output=True, text=True
    ).stdout.strip() or "ugclaw"

    unit = f"""[Unit]
Description=UGCLAW Autonomous Agent Daemon
After=network.target

[Service]
Type=simple
ExecStart={ugclaw_bin} start
ExecStop={ugclaw_bin} stop
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""
    unit_file.write_text(unit)
    print(f"✅ Service file written: {unit_file}")

    ret = subprocess.run(
        ["systemctl", "--user", "enable", "--now", "ugclaw"],
        capture_output=True, text=True,
    )
    if ret.returncode == 0:
        print("✅ UGCLAW enabled and started as user service.")
        print("   It will start automatically on login.")
    else:
        print(f"⚠️  systemctl returned an error:\n{ret.stderr}")
        print(f"   You can enable manually:\n   systemctl --user enable --now ugclaw")


def _disable_systemd():
    subprocess.run(["systemctl", "--user", "disable", "--now", "ugclaw"])
    unit = Path.home() / ".config" / "systemd" / "user" / "ugclaw.service"
    if unit.exists():
        unit.unlink()
    print("✅ UGCLAW boot service disabled.")


def _enable_launchd():
    plist_dir  = Path.home() / "Library" / "LaunchAgents"
    plist_file = plist_dir / "com.ugclaw.daemon.plist"
    plist_dir.mkdir(parents=True, exist_ok=True)

    ugclaw_bin = subprocess.run(
        ["which", "ugclaw"], capture_output=True, text=True
    ).stdout.strip() or "ugclaw"

    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>             <string>com.ugclaw.daemon</string>
  <key>ProgramArguments</key>  <array><string>{ugclaw_bin}</string><string>start</string></array>
  <key>RunAtLoad</key>         <true/>
  <key>KeepAlive</key>         <true/>
  <key>StandardErrorPath</key> <string>{DAEMON_LOG}</string>
  <key>StandardOutPath</key>   <string>{DAEMON_LOG}</string>
</dict>
</plist>
"""
    plist_file.write_text(plist)
    subprocess.run(["launchctl", "load", str(plist_file)])
    print(f"✅ LaunchAgent installed: {plist_file}")
    print("   UGCLAW will start automatically at login.")


def _disable_launchd():
    plist = Path.home() / "Library" / "LaunchAgents" / "com.ugclaw.daemon.plist"
    if plist.exists():
        subprocess.run(["launchctl", "unload", str(plist)])
        plist.unlink()
    print("✅ LaunchAgent removed.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    if not args or args[0] in ("--help", "-h", "help"):
        print(HELP_TEXT)
        return

    if args[0] in ("--version", "-v", "version"):
        print(f"ugclaw {__version__}")
        return

    cmd = args[0].lower()
    rest = args[1:]

    commands = {
        "start":     lambda: cmd_start(),
        "stop":      lambda: cmd_stop(),
        "restart":   lambda: cmd_restart(),
        "status":    lambda: cmd_status(),
        "logs":      lambda: cmd_logs(),
        "tui":       lambda: cmd_tui(),
        "update":    lambda: cmd_update(),
        "configure": lambda: cmd_configure(rest),
        "telegram":  lambda: cmd_telegram(rest),
        "enable":    lambda: cmd_enable(),
        "disable":   lambda: cmd_disable(),
    }

    fn = commands.get(cmd)
    if fn:
        fn()
    else:
        print(f"❌ Unknown command: {cmd}")
        print(f"   Run: ugclaw --help")
        sys.exit(1)


if __name__ == "__main__":
    main()
