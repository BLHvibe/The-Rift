"""
Commands / Admin Tab — Phase 7.
Fetch Ranks and Log Inhouse run real subprocesses via data scripts.
"""
import threading, time, queue, subprocess, sys, os, re
import dearpygui.dearpygui as dpg
from theme import C
from data.config import load_config, save_config, script_path
from data.reader import live

_F = {}
def set_fonts(f): global _F; _F = f

_CMD_WIN = "commands_overlay_win"

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class CommandsState:
    def __init__(self):
        self._log_q    = queue.SimpleQueue()
        self.running   = False
        self._lines    = []     # list of (text, color)
        self._max_lines = 500
        self._proc     = None   # current subprocess (for Stop button)
        self._last_run = {}     # script_name → "HH:MM:SS" timestamp string
        self.progress  = 0.0   # 0.0–1.0, drives the progress bar

    def log(self, text, color=None):
        self._log_q.put((text, color or C["txt"][:3]))

    def tick(self):
        changed = False
        while not self._log_q.empty():
            try:
                line = self._log_q.get_nowait()
                self._lines.append(line)
                if len(self._lines) > self._max_lines:
                    self._lines = self._lines[-self._max_lines:]
                changed = True
            except Exception:
                break
        return changed

    def clear(self):
        self._lines.clear()
        if dpg.does_item_exist("cmd_console"):
            dpg.delete_item("cmd_console", children_only=True)


cmds = CommandsState()

TOP_BAR_H = 52
PAD       = 20
BTN_W     = 260
BTN_H     = 44


def _txt(dl, x, y, text, color, size, font_key=None):
    tag = dpg.draw_text((x, y), text, color=color, size=size, parent=dl)
    if font_key and font_key in _F:
        dpg.bind_item_font(tag, _F[font_key])
    return tag


# ---------------------------------------------------------------------------
# Main draw
# ---------------------------------------------------------------------------

def draw_commands(dl, vw, vh, fonts=None):
    if fonts:
        set_fonts(fonts)

    # Drain queue once; use result to decide whether to refresh the console
    changed = cmds.tick()

    dpg.delete_item(dl, children_only=True)
    dpg.draw_rectangle((0,0),(vw,vh), fill=C["bg"], color=(0,0,0,0), parent=dl)

    # Top bar
    dpg.draw_rectangle((0,0),(vw,TOP_BAR_H), fill=(*C["panel"][:3],220),
                        color=(0,0,0,0), parent=dl)
    dpg.draw_line((0,TOP_BAR_H-1),(vw,TOP_BAR_H-1),
                  color=C["rule_dark"], thickness=1, parent=dl)
    _txt(dl, PAD, 12, "ADMIN / COMMANDS", (*C["gold"][:3],220), 22, "raj_24")

    # Overlay window: position relative to actual sidebar width, not hardcoded 68
    vp_w = dpg.get_viewport_width()
    sb_w = vp_w - vw   # actual current sidebar pixel width
    if not dpg.does_item_exist(_CMD_WIN):
        _build_commands_window(sb_w, vw, vh)
    else:
        dpg.configure_item(_CMD_WIN, pos=(sb_w, TOP_BAR_H), width=vw, height=vh-TOP_BAR_H)

    # Flush pending log lines into console widget (main thread only)
    if changed and dpg.does_item_exist("cmd_console"):
        _refresh_console()


def _build_commands_window(sb_w, vw, vh):
    with dpg.window(tag=_CMD_WIN,
                    pos=(sb_w, TOP_BAR_H),
                    width=vw, height=vh-TOP_BAR_H,
                    no_title_bar=True, no_resize=True,
                    no_move=True, no_focus_on_appearing=True):

        dpg.add_spacer(height=PAD)

        with dpg.group(horizontal=True):
            # ── Left: action buttons ──────────────────────────────────────
            with dpg.child_window(width=BTN_W+PAD*2, border=False, height=-1,
                                   no_scrollbar=True):
                dpg.add_spacer(height=4)

                _section_hdr("DATA COMMANDS")

                _cmd_button("▶  FETCH RANKS",
                            "Fetch latest ranks from Google Sheets + Riot API.",
                            _run_fetch_ranks)
                dpg.add_text(tag="ts_fetch_ranks", default_value="",
                             color=C["txt_dim"][:3])
                if "raj_r_12" in _F:
                    dpg.bind_item_font(dpg.last_item(), _F["raj_r_12"])
                dpg.add_spacer(height=8)

                _cmd_button("▶  RUN SCOUT",
                            "Fetch scouting data for all players.",
                            _run_scout)
                dpg.add_text(tag="ts_scout", default_value="",
                             color=C["txt_dim"][:3])
                if "raj_r_12" in _F:
                    dpg.bind_item_font(dpg.last_item(), _F["raj_r_12"])
                dpg.add_spacer(height=8)

                _cmd_button("▶  SETUP DRAFT",
                            "Prepare the Draft Tool sheet with current roster.",
                            _run_setup_draft)
                dpg.add_text(tag="ts_draft", default_value="",
                             color=C["txt_dim"][:3])
                if "raj_r_12" in _F:
                    dpg.bind_item_font(dpg.last_item(), _F["raj_r_12"])
                dpg.add_spacer(height=8)

                _cmd_button("▶  LOG INHOUSE GAME",
                            "Connect to LCU and log the last custom game.",
                            _run_inhouse)
                dpg.add_text(tag="ts_inhouse", default_value="",
                             color=C["txt_dim"][:3])
                if "raj_r_12" in _F:
                    dpg.bind_item_font(dpg.last_item(), _F["raj_r_12"])
                dpg.add_spacer(height=24)

                # ── Stop button ───────────────────────────────────────────
                dpg.add_button(label="⬛  STOP PROCESS",
                               callback=_stop_process,
                               width=BTN_W, height=BTN_H)
                if "raj_sb_16" in _F:
                    dpg.bind_item_font(dpg.last_item(), _F["raj_sb_16"])
                dpg.add_text("Kill the currently running command.",
                             color=C["txt_dim"][:3], wrap=BTN_W)
                if "raj_r_12" in _F:
                    dpg.bind_item_font(dpg.last_item(), _F["raj_r_12"])
                dpg.add_spacer(height=10)
                dpg.add_progress_bar(tag="cmd_progress", default_value=0.0,
                                     width=BTN_W, height=14)
                dpg.add_spacer(height=14)

                _section_hdr("ROSTER")
                _cmd_button("▶  JOIN TIER LIST",
                            "Register a new player into the tier list.",
                            _open_join_dialog)
                dpg.add_spacer(height=24)
                _section_hdr("CONSOLE")
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Clear console", callback=_clear_console,
                                   width=130, height=30)

            dpg.add_spacer(width=PAD)

            # ── Right: console output ─────────────────────────────────────
            with dpg.child_window(border=True, height=-1, horizontal_scrollbar=False,
                                   tag="cmd_console_outer"):
                with dpg.group(tag="cmd_console"):
                    t = dpg.add_text("Console ready.", color=C["txt_dim"][:3])
                    if "raj_r_12" in _F:
                        dpg.bind_item_font(t, _F["raj_r_12"])


def _section_hdr(text):
    t = dpg.add_text(text, color=C["gold"][:3])
    if "raj_sb_16" in _F:
        dpg.bind_item_font(t, _F["raj_sb_16"])
    dpg.add_separator()
    dpg.add_spacer(height=8)


def _cmd_button(label, tooltip, callback):
    btn = dpg.add_button(label=label, callback=callback,
                         width=BTN_W, height=BTN_H)
    if "raj_sb_16" in _F:
        dpg.bind_item_font(btn, _F["raj_sb_16"])
    t = dpg.add_text(tooltip, color=C["txt_dim"][:3], wrap=BTN_W)
    if "raj_r_12" in _F:
        dpg.bind_item_font(t, _F["raj_r_12"])
    dpg.add_spacer(height=2)


def _refresh_console():
    if not dpg.does_item_exist("cmd_console"):
        return
    dpg.delete_item("cmd_console", children_only=True)
    for text, color in cmds._lines[-200:]:
        t = dpg.add_text(text, color=color, parent="cmd_console", wrap=0)
        if "raj_r_12" in _F:
            dpg.bind_item_font(t, _F["raj_r_12"])


def _log(text, color=None):
    cmds.log(text, color)


def _clear_console():
    cmds.clear()


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------

def _py():
    """Return the Python executable path (works frozen and dev)."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return sys.executable


_TS_TAG = {
    "fetch_ranks_gsheets.py": "ts_fetch_ranks",
    "inhouse_tracker.py":     "ts_inhouse",
    "fetch_ranks_gsheets.py--scout": "ts_scout",
    "fetch_ranks_gsheets.py--draft": "ts_draft",
}


def _run_script(label, script_name, extra_args=None):
    """Run a data script as a subprocess, streaming output to console."""
    if cmds.running:
        _log("[!] A command is already running.", C["loss"][:3])
        return
    cfg = load_config()
    if not cfg.get("api_key"):
        _log("[!] No Riot API key set — configure it in Settings.", C["loss"][:3])
        return
    if not cfg.get("sheet_url"):
        _log("[!] No Google Sheet URL set — configure it in Settings.", C["loss"][:3])
        return

    cmds.running  = True
    cmds.progress = 0.0
    if dpg.does_item_exist("cmd_progress"):
        dpg.set_value("cmd_progress", 0.0)
    _log(f"▶  {label}", C["gold"][:3])

    # Build timestamp-widget tag key
    ts_key = script_name
    if extra_args:
        ts_key += "".join(extra_args)

    def _bg():
        proc = None
        try:
            sp = script_path(script_name)
            cmd = [
                _py(), sp,
                "--key",     cfg["api_key"],
                "--sheet",   cfg["sheet_url"],
                "--creds",   cfg.get("creds_path", "credentials.json"),
                "--region",  cfg.get("region",  "na1"),
                "--routing", cfg.get("routing", "americas"),
            ]
            if extra_args:
                cmd.extend(extra_args)
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            cmds._proc = proc
            _PROGRESS_RE = re.compile(r'\[(\d+)/(\d+)\]')
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    col = C["win"][:3] if line.startswith("✓") or "complete" in line.lower() \
                          else C["loss"][:3] if line.startswith("[ERR") or "error" in line.lower() \
                          else C["txt"][:3]
                    _log(line, col)
                    m = _PROGRESS_RE.search(line)
                    if m:
                        n, total = int(m.group(1)), int(m.group(2))
                        if total > 0:
                            pct = n / total
                            cmds.progress = pct
                            if dpg.does_item_exist("cmd_progress"):
                                dpg.set_value("cmd_progress", pct)
            try:
                proc.wait(timeout=300)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                _log("[ERR] Timed out after 5 minutes.", C["loss"][:3])
                return
            if proc.returncode == 0:
                _log(f"✓  {label} complete.", C["win"][:3])
                ts_str = time.strftime("Last run: %H:%M:%S")
                cmds._last_run[ts_key] = ts_str
                tag = _TS_TAG.get(ts_key)
                if tag and dpg.does_item_exist(tag):
                    dpg.configure_item(tag, default_value=ts_str)
                cmds.progress = 1.0
                if dpg.does_item_exist("cmd_progress"):
                    dpg.set_value("cmd_progress", 1.0)
            else:
                _log(f"[!] Exited with code {proc.returncode}.", C["loss"][:3])
                cmds.progress = 0.0
                if dpg.does_item_exist("cmd_progress"):
                    dpg.set_value("cmd_progress", 0.0)
        except FileNotFoundError:
            _log(f"[ERR] Script not found: {script_name}", C["loss"][:3])
        except Exception as e:
            _log(f"[ERR] {e}", C["loss"][:3])
        finally:
            cmds.running = False
            cmds._proc   = None

    threading.Thread(target=_bg, daemon=True, name=label).start()


def _stop_process():
    proc = cmds._proc
    if proc is None:
        _log("[!] No process is running.", C["txt_dim"][:3])
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        _log("[!] Process stopped.", C["loss"][:3])
    except Exception as e:
        _log(f"[ERR] Stop failed: {e}", C["loss"][:3])
    finally:
        cmds.running = False
        cmds._proc   = None


def _run_fetch_ranks():
    _run_script("Fetching ranks…", "fetch_ranks_gsheets.py")


def _run_scout():
    _run_script("Running full scout…", "fetch_ranks_gsheets.py", extra_args=["--scout"])


def _run_setup_draft():
    _run_script("Setting up draft…", "fetch_ranks_gsheets.py", extra_args=["--setup-draft"])


def _run_inhouse():
    _run_script("Logging inhouse game…", "inhouse_tracker.py")


_JOIN_WIN = "cmd_join_dialog"

def _open_join_dialog():
    if dpg.does_item_exist(_JOIN_WIN):
        dpg.delete_item(_JOIN_WIN)
    vp = dpg.get_viewport_width(), dpg.get_viewport_height()
    w, h = 400, 280
    px = (vp[0] - w) // 2
    py = (vp[1] - h) // 2
    with dpg.window(tag=_JOIN_WIN, label="Join Tier List",
                    pos=(px, py), width=w, height=h,
                    no_resize=True, modal=True):
        dpg.add_spacer(height=12)
        t = dpg.add_text("JOIN THE TIER LIST", color=C["gold"][:3])
        if "raj_sb_18" in _F: dpg.bind_item_font(t, _F["raj_sb_18"])
        dpg.add_spacer(height=12)
        dpg.add_text("Display Name", color=C["txt_dim"][:3])
        dpg.add_input_text(tag="join_name", width=360, hint="Your in-game display name")
        dpg.add_spacer(height=10)
        dpg.add_text("Riot ID  (Name#TAG)", color=C["txt_dim"][:3])
        dpg.add_input_text(tag="join_riot", width=360, hint="PlayerName#NA1")
        dpg.add_spacer(height=18)
        with dpg.group(horizontal=True):
            dpg.add_button(label="  JOIN  ", callback=_submit_join,
                           width=120, height=36)
            dpg.add_spacer(width=12)
            dpg.add_button(label="Cancel",
                           callback=lambda: dpg.delete_item(_JOIN_WIN),
                           width=80, height=36)
        dpg.add_spacer(height=8)
        dpg.add_text(tag="join_status", default_value="", color=C["txt_dim"][:3])


def _submit_join():
    name = dpg.get_value("join_name").strip()
    riot = dpg.get_value("join_riot").strip()
    if not name or not riot:
        dpg.configure_item("join_status", default_value="⚠  Both fields are required.")
        return
    # Check against live sheet roster first, fall back to config
    current_players = list(live.players) if (live.loaded and live.players) \
                      else load_config().get("players", [])
    if name in current_players:
        dpg.configure_item("join_status", default_value=f"⚠  {name} is already in the roster.")
        return
    # Persist to config as local cache (sheet is the authoritative source)
    cfg = load_config()
    players = cfg.get("players", [])
    if name not in players:
        players.append(name)
    cfg["players"] = players
    riot_map = cfg.get("summoner_map", {})
    game_name = riot.split("#")[0].strip() if "#" in riot else riot
    if game_name:
        riot_map[game_name] = name
    cfg["summoner_map"] = riot_map
    save_config(cfg)
    _log(f"✓  {name} ({riot}) added to roster.", C["win"][:3])
    dpg.configure_item("join_status", default_value=f"✓  {name} added.")
