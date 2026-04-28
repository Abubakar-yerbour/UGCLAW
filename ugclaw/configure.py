"""
configure.py — UGCLAW interactive configuration TUI.

Usage:
  ugclaw configure              full menu
  ugclaw configure providers    jump to API keys
  ugclaw configure models       jump to model selection
  ugclaw configure telegram     jump to Telegram settings
  ugclaw configure active       set active provider/model
  ugclaw configure --help

Controls: ↑↓ navigate  SPACE select/deselect  ENTER confirm  Q cancel
Model search: type to filter, ESC clears search
"""

import curses
import json
import sys
from pathlib import Path

from ugclaw.paths import CONFIG_FILE
from ugclaw.config_manager import load_config, save_config, validate_config
from ugclaw.providers import PROVIDERS, fetch_models


# ── Colour pairs (initialised in _init_colors) ────────────────────────────────
C_HIGHLIGHT = 1   # selected row
C_SELECTED  = 2   # multi-select tick
C_TITLE     = 3   # header bar
C_WARN      = 4   # warnings / errors
C_DIM       = 5   # secondary text


def _init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_HIGHLIGHT, curses.COLOR_BLACK,  curses.COLOR_CYAN)
    curses.init_pair(C_SELECTED,  curses.COLOR_GREEN,  -1)
    curses.init_pair(C_TITLE,     curses.COLOR_CYAN,   -1)
    curses.init_pair(C_WARN,      curses.COLOR_RED,    -1)
    curses.init_pair(C_DIM,       curses.COLOR_WHITE,  -1)


# ── Generic menu ──────────────────────────────────────────────────────────────

def _menu(
    stdscr,
    title:     str,
    options:   list[str],
    multi:     bool  = False,
    selected:  set   = None,
    subtitle:  str   = "",
    searchable: bool = False,
) -> list[int] | int:
    """
    Arrow-key menu.
    Single select → int index (or -1 on cancel).
    Multi select  → list of selected indices.
    searchable    → type to filter options live.
    """
    curses.curs_set(0)
    _init_colors()

    chosen = set(selected or [])
    pos    = 0
    scroll = 0
    search = ""                    # live search string (searchable mode)

    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        max_vis = max(1, h - 8)

        # Title bar
        stdscr.attron(curses.color_pair(C_TITLE) | curses.A_BOLD)
        stdscr.addstr(0, 0, f"  ⚡ UGCLAW — {title}  ".ljust(w)[:w - 1])
        stdscr.attroff(curses.color_pair(C_TITLE) | curses.A_BOLD)

        row = 1
        if subtitle:
            stdscr.addstr(row, 2, subtitle[:w - 3])
            row += 1

        # Search bar
        if searchable:
            bar = f"  🔍 {search}█" if search else "  🔍 type to search…"
            stdscr.addstr(row, 0, bar[:w - 1])
            row += 1

        # Filter options
        visible_opts = options
        mapping: list[int] = list(range(len(options)))   # filtered index → original index
        if searchable and search:
            pairs = [
                (i, o) for i, o in enumerate(options)
                if search.lower() in o.lower()
            ]
            mapping      = [p[0] for p in pairs]
            visible_opts = [p[1] for p in pairs]

        if pos >= len(visible_opts):
            pos = max(0, len(visible_opts) - 1)
        if scroll > pos:
            scroll = pos
        if pos >= scroll + max_vis:
            scroll = pos - max_vis + 1

        page = visible_opts[scroll:scroll + max_vis]

        for i, opt in enumerate(page):
            real_i  = mapping[scroll + i]
            is_cur  = (scroll + i) == pos
            is_sel  = real_i in chosen
            marker  = "[●] " if (multi and is_sel) else ("[○] " if multi else "    ")
            label   = f"{marker}{opt}"[:w - 4]
            disp_row = row + i
            if disp_row >= h - 2:
                break
            if is_cur:
                stdscr.attron(curses.color_pair(C_HIGHLIGHT) | curses.A_BOLD)
                stdscr.addstr(disp_row, 2, label.ljust(w - 4)[:w - 4])
                stdscr.attroff(curses.color_pair(C_HIGHLIGHT) | curses.A_BOLD)
            elif is_sel:
                stdscr.attron(curses.color_pair(C_SELECTED))
                stdscr.addstr(disp_row, 2, label[:w - 4])
                stdscr.attroff(curses.color_pair(C_SELECTED))
            else:
                stdscr.addstr(disp_row, 2, label[:w - 4])

        # Footer
        footer = ("↑↓ move  SPACE select  ENTER confirm  Q cancel"
                  if multi else "↑↓ move  ENTER confirm  Q cancel")
        if searchable:
            footer += "  ESC clear search"
        stdscr.addstr(h - 2, 2, footer[:w - 3])
        if multi:
            stdscr.addstr(h - 1, 2, f"{len(chosen)} selected  |  {len(visible_opts)} shown"[:w - 3])
        elif searchable:
            stdscr.addstr(h - 1, 2, f"{len(visible_opts)} / {len(options)} models"[:w - 3])

        stdscr.refresh()
        key = stdscr.getch()

        if key in (curses.KEY_UP, ord('k')):
            pos = max(0, pos - 1)
            if pos < scroll:
                scroll = pos

        elif key in (curses.KEY_DOWN, ord('j')):
            pos = min(len(visible_opts) - 1, pos + 1)
            if pos >= scroll + max_vis:
                scroll += 1

        elif key == ord(' ') and multi:
            if visible_opts:
                real_i = mapping[pos]
                if real_i in chosen:
                    chosen.discard(real_i)
                else:
                    chosen.add(real_i)

        elif key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
            if not visible_opts:
                continue
            if multi:
                return sorted(chosen)
            return mapping[pos]

        elif key in (ord('q'), ord('Q'), 27):
            if searchable and search:
                search = ""   # ESC clears search first
            else:
                return [] if multi else -1

        elif searchable:
            if key == 127 or key == curses.KEY_BACKSPACE:
                search = search[:-1]
                pos    = 0
                scroll = 0
            elif 32 <= key <= 126:
                search += chr(key)
                pos     = 0
                scroll  = 0


# ── Input box ─────────────────────────────────────────────────────────────────

def _input_box(stdscr, prompt: str, current: str = "", secret: bool = False) -> str:
    curses.curs_set(1)
    _init_colors()
    h, w = stdscr.getmaxyx()
    stdscr.clear()
    stdscr.attron(curses.color_pair(C_TITLE) | curses.A_BOLD)
    stdscr.addstr(0, 0, "  ⚡ UGCLAW — Input  ".ljust(w)[:w - 1])
    stdscr.attroff(curses.color_pair(C_TITLE) | curses.A_BOLD)

    for i, line in enumerate(prompt.split("\n")):
        if 2 + i < h - 4:
            stdscr.addstr(2 + i, 2, line[:w - 3])

    stdscr.addstr(h - 4, 2, "ENTER to confirm  ESC to cancel")
    stdscr.addstr(h - 3, 2, "> ")

    buf = list(current)
    col = len(buf)

    while True:
        disp = ("*" * len(buf) if secret else "".join(buf))[:w - 6]
        stdscr.addstr(h - 3, 4, " " * (w - 6))
        stdscr.addstr(h - 3, 4, disp)
        stdscr.move(h - 3, 4 + min(col, w - 7))
        stdscr.refresh()

        key = stdscr.getch()
        if key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
            curses.curs_set(0)
            return "".join(buf)
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            if col > 0:
                buf.pop(col - 1)
                col -= 1
        elif key == 27:
            curses.curs_set(0)
            return current
        elif 32 <= key <= 126:
            buf.insert(col, chr(key))
            col += 1


# ── Message box ───────────────────────────────────────────────────────────────

def _message(stdscr, msg: str, wait: bool = True, is_error: bool = False):
    _init_colors()
    h, w = stdscr.getmaxyx()
    stdscr.clear()
    color = C_WARN if is_error else C_TITLE
    stdscr.attron(curses.color_pair(color) | curses.A_BOLD)
    stdscr.addstr(0, 0, "  ⚡ UGCLAW  ".ljust(w)[:w - 1])
    stdscr.attroff(curses.color_pair(color) | curses.A_BOLD)
    for i, line in enumerate(msg.split("\n")):
        if 2 + i < h - 2:
            stdscr.addstr(2 + i, 2, line[:w - 3])
    if wait:
        stdscr.addstr(h - 2, 2, "Press any key to continue…")
    stdscr.refresh()
    if wait:
        stdscr.getch()


# ── Main configure entry ──────────────────────────────────────────────────────

def run_configure(section: str = None):
    curses.wrapper(_configure_main, section)


def _configure_main(stdscr, section: str):
    cfg = load_config()

    if section:
        section = section.lower().strip()
        _jump_to(stdscr, cfg, section)
        return

    MAIN_OPTS = [
        "🔑  API Keys          — set keys for each provider",
        "🤖  Models            — fetch and select available models",
        "⚡  Active provider   — choose which model to use right now",
        "📱  Telegram          — bot token, allowed users, test connection",
        "⚙️   Advanced          — timeouts, browser, iteration limits",
        "📋  View config       — show current settings",
        "💾  Save & exit",
        "❌  Exit without saving",
    ]

    while True:
        choice = _menu(stdscr, "Configure", MAIN_OPTS)
        if choice in (-1, 7):
            break
        elif choice == 0:
            _section_keys(stdscr, cfg)
        elif choice == 1:
            _section_models(stdscr, cfg)
        elif choice == 2:
            _section_active(stdscr, cfg)
        elif choice == 3:
            _section_telegram(stdscr, cfg)
        elif choice == 4:
            _section_advanced(stdscr, cfg)
        elif choice == 5:
            _section_view(stdscr, cfg)
        elif choice == 6:
            save_config(cfg)
            warns = validate_config(cfg)
            msg = "✅ Configuration saved."
            if warns:
                msg += "\n\n⚠️  Warnings:\n" + "\n".join(f"• {w}" for w in warns)
            _message(stdscr, msg)
            break


def _jump_to(stdscr, cfg, section):
    dispatch = {
        "providers": _section_keys,
        "keys":      _section_keys,
        "models":    _section_models,
        "active":    _section_active,
        "telegram":  _section_telegram,
        "advanced":  _section_advanced,
    }
    fn = dispatch.get(section)
    if fn:
        fn(stdscr, cfg)
        save_config(cfg)
        _message(stdscr, "✅ Saved.")
    else:
        _message(stdscr, f"Unknown section: {section}\n\nAvailable: providers, models, active, telegram, advanced", is_error=True)


# ── Sections ──────────────────────────────────────────────────────────────────

def _section_keys(stdscr, cfg):
    names = [f"{PROVIDERS[p]['label']}" for p in PROVIDERS]
    ids   = list(PROVIDERS.keys())

    while True:
        idx = _menu(stdscr, "API Keys — Select Provider", names,
                    subtitle="Select a provider to set its API key")
        if idx < 0:
            return
        pid       = ids[idx]
        key_field = PROVIDERS[pid]["key_field"]
        current   = cfg.get(key_field, "")
        masked    = (f"***{current[-4:]}" if len(current) > 4 else "(not set)")

        new_val = _input_box(
            stdscr,
            f"{PROVIDERS[pid]['label']} API Key\nCurrent: {masked}\n\n"
            "Leave blank to keep current value.",
            "",
            secret=True,
        )
        if new_val.strip():
            cfg[key_field] = new_val.strip()
            _message(stdscr, f"✅ Key set for {PROVIDERS[pid]['label']}")
        else:
            _message(stdscr, "No change.")


def _section_models(stdscr, cfg):
    names = [f"{PROVIDERS[p]['label']}" for p in PROVIDERS]
    ids   = list(PROVIDERS.keys())

    while True:
        idx = _menu(stdscr, "Models — Select Provider", names,
                    subtitle="Choose a provider to fetch and save models from")
        if idx < 0:
            return

        pid     = ids[idx]
        meta    = PROVIDERS[pid]
        api_key = cfg.get(meta["key_field"], "")

        if not api_key:
            _message(stdscr, f"⚠️  No API key for {meta['label']}.\nSet it first via 'API Keys'.", is_error=True)
            continue

        _message(stdscr, f"⏳ Fetching models from {meta['label']}…", wait=False)

        try:
            models = fetch_models(pid, api_key)
        except Exception as e:
            _message(stdscr, f"❌ Failed to fetch models:\n{e}", is_error=True)
            continue

        if not models:
            _message(stdscr, f"❌ No models returned for {meta['label']}.", is_error=True)
            continue

        already = set(cfg.get("saved_models", {}).get(pid, []))
        pre_sel = {i for i, m in enumerate(models) if m in already}

        chosen_idx = _menu(
            stdscr,
            f"{meta['label']} — Select Models",
            models,
            multi=True,
            selected=pre_sel,
            subtitle=f"{len(models)} available  •  SPACE=select  ENTER=confirm  type=search",
            searchable=True,
        )

        chosen_models = [models[i] for i in chosen_idx]
        if "saved_models" not in cfg:
            cfg["saved_models"] = {}
        cfg["saved_models"][pid] = chosen_models

        _message(stdscr,
            f"✅ Saved {len(chosen_models)} model(s) for {meta['label']}:\n" +
            "\n".join(f"  • {m}" for m in chosen_models[:15])
        )


def _section_active(stdscr, cfg):
    names = [f"{PROVIDERS[p]['label']}" for p in PROVIDERS]
    ids   = list(PROVIDERS.keys())

    pidx = _menu(stdscr, "Active Provider", names,
                 subtitle="This provider will be used for all conversations")
    if pidx < 0:
        return

    pid   = ids[pidx]
    saved = cfg.get("saved_models", {}).get(pid, [])

    if not saved:
        _message(stdscr, f"⚠️  No saved models for {PROVIDERS[pid]['label']}.\nSave models first.", is_error=True)
        return

    midx = _menu(stdscr, f"Active Model — {PROVIDERS[pid]['label']}", saved,
                 searchable=True)
    if midx < 0:
        return

    cfg["active_provider"] = pid
    cfg["active_model"]    = saved[midx]
    _message(stdscr, f"✅ Active: {PROVIDERS[pid]['label']} / {saved[midx]}")


def _section_telegram(stdscr, cfg):
    while True:
        current_token = cfg.get("telegram_bot_token", "")
        masked        = f"***{current_token[-6:]}" if len(current_token) > 6 else "(not set)"
        owner_id      = cfg.get("telegram_owner_id") or "(not set)"
        allowed       = cfg.get("allowed_telegram_ids", [])

        opts = [
            f"Bot token        [{masked}]",
            f"Owner ID         [{owner_id}]",
            f"Allowed users    [{len(allowed)} configured]",
            "Add allowed user",
            "Remove allowed user",
            "Test connection",
            "◀  Back",
        ]
        choice = _menu(stdscr, "Telegram Settings", opts)

        if choice in (-1, 6):
            return

        elif choice == 0:
            val = _input_box(
                stdscr,
                "Telegram Bot Token\nGet one from @BotFather on Telegram.\n\nLeave blank to keep current.",
                "",
                secret=True,
            )
            if val.strip():
                cfg["telegram_bot_token"] = val.strip()
                _message(stdscr, "✅ Bot token saved.")

        elif choice == 1:
            val = _input_box(
                stdscr,
                "Your Telegram User ID\nGet it from @userinfobot on Telegram.\nThis ID gets permanent owner access.\n",
                str(owner_id) if owner_id != "(not set)" else "",
            )
            if val.strip().isdigit():
                uid = int(val.strip())
                cfg["telegram_owner_id"] = uid
                if uid not in allowed:
                    allowed.append(uid)
                    cfg["allowed_telegram_ids"] = allowed
                _message(stdscr, f"✅ Owner ID set: {uid}")

        elif choice == 2:
            if not allowed:
                _message(stdscr, "No allowed users configured.\nEmpty = all users allowed.")
            else:
                _message(stdscr, "Allowed users:\n" + "\n".join(f"  • {uid}" for uid in allowed))

        elif choice == 3:
            val = _input_box(stdscr, "Enter Telegram user ID to allow:")
            if val.strip().isdigit():
                uid = int(val.strip())
                if uid not in allowed:
                    allowed.append(uid)
                    cfg["allowed_telegram_ids"] = allowed
                _message(stdscr, f"✅ User {uid} added.")

        elif choice == 4:
            if not allowed:
                _message(stdscr, "No users to remove.")
            else:
                labels = [str(uid) for uid in allowed]
                ridx   = _menu(stdscr, "Remove User", labels)
                if ridx >= 0:
                    removed = allowed.pop(ridx)
                    cfg["allowed_telegram_ids"] = allowed
                    _message(stdscr, f"✅ Removed: {removed}")

        elif choice == 5:
            token = cfg.get("telegram_bot_token", "")
            if not token:
                _message(stdscr, "❌ No bot token set.", is_error=True)
                continue
            _message(stdscr, "⏳ Testing connection…", wait=False)
            try:
                import requests as req
                r = req.get(f"https://api.telegram.org/bot{token}/getMe", timeout=8)
                data = r.json()
                if data.get("ok"):
                    info = data["result"]
                    _message(stdscr,
                        f"✅ Connected!\n\n"
                        f"Bot name : {info.get('first_name')}\n"
                        f"Username : @{info.get('username')}\n"
                        f"ID       : {info.get('id')}"
                    )
                else:
                    _message(stdscr, f"❌ Connection failed:\n{data.get('description')}", is_error=True)
            except Exception as e:
                _message(stdscr, f"❌ Error: {e}", is_error=True)


def _section_advanced(stdscr, cfg):
    while True:
        opts = [
            f"Max tool iterations  [{cfg.get('max_tool_iterations', 15)}]",
            f"Tool timeout (s)     [{cfg.get('tool_timeout', 30)}]",
            f"Max tokens           [{cfg.get('max_tokens', 4096)}]",
            f"Browser headless     [{cfg.get('browser_headless', True)}]",
            "◀  Back",
        ]
        choice = _menu(stdscr, "Advanced Settings", opts)
        if choice in (-1, 4):
            return

        if choice == 0:
            val = _input_box(stdscr, "Max tool iterations (default: 15)\nHigher = longer tasks, more API usage.")
            if val.strip().isdigit():
                cfg["max_tool_iterations"] = int(val.strip())

        elif choice == 1:
            val = _input_box(stdscr, "Tool timeout in seconds (default: 30)\nShell commands will be killed after this time.")
            if val.strip().isdigit():
                cfg["tool_timeout"] = int(val.strip())

        elif choice == 2:
            val = _input_box(stdscr, "Max tokens per LLM response (default: 4096).")
            if val.strip().isdigit():
                cfg["max_tokens"] = int(val.strip())

        elif choice == 3:
            current = cfg.get("browser_headless", True)
            cfg["browser_headless"] = not current
            _message(stdscr, f"Browser headless: {not current}")


def _section_view(stdscr, cfg):
    lines = [
        f"Active : {cfg.get('active_provider', '?')} / {cfg.get('active_model', '?')}",
        "",
        "API Keys:",
    ]
    for pid, meta in PROVIDERS.items():
        key    = cfg.get(meta["key_field"], "")
        status = "✅ set" if key else "❌ not set"
        lines.append(f"  {meta['label']:<18} {status}")

    lines += ["", "Saved models:"]
    for pid, models in cfg.get("saved_models", {}).items():
        label = PROVIDERS.get(pid, {}).get("label", pid)
        lines.append(f"  {label:<18} {len(models)} model(s)")

    lines += [
        "",
        f"Telegram token : {'✅ set' if cfg.get('telegram_bot_token') else '❌ not set'}",
        f"Owner ID       : {cfg.get('telegram_owner_id') or 'not set'}",
        f"Allowed IDs    : {cfg.get('allowed_telegram_ids') or 'all'}",
        "",
        f"Max iterations : {cfg.get('max_tool_iterations', 15)}",
        f"Tool timeout   : {cfg.get('tool_timeout', 30)}s",
        f"Max tokens     : {cfg.get('max_tokens', 4096)}",
        f"Browser        : {'headless' if cfg.get('browser_headless', True) else 'visible'}",
    ]
    _message(stdscr, "\n".join(lines))
