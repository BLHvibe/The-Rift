"""
Commands / Admin Tab — Phase 7.
Fetch Ranks and Log Inhouse run real subprocesses via data scripts.
"""
import threading, time, queue, subprocess, sys, os
import dearpygui.dearpygui as dpg
from theme import C
from data.config import load_config, script_path

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

    cmds.tick()

    dpg.delete_item(dl, children_only=True)
    dpg.draw_rectangle((0,0),(vw,vh), fill=C["bg"], color=(0,0,0,0), parent=dl)

    # Top bar
    dpg.draw_rectangle((0,0),(vw,TOP_BAR_H), fill=(*C["panel"][:3],220),
                        color=(0,0,0,0), parent=dl)
    dpg.draw_line((0,TOP_BAR_H-1),(vw,TOP_BAR_H-1),
                  color=C["rule_dark"], thickness=1, parent=dl)
    _txt(dl, PAD, 12, "ADMIN / COMMANDS", (*C["gold"][:3],220), 22, "raj_24")

    if not dpg.does_item_exist(_CMD_WIN):
        _build_commands_window(vw, vh)
    else:
        dpg.configure_item(_CMD_WIN,
                           pos=(0, TOP_BAR_H),
                           width=vw, height=vh-TOP_BAR_H)

    # Flush pending log lines into console widget
    if cmds.tick() and dpg.does_item_exist("cmd_console"):
        _refresh_console()


def _build_commands_window(vw, vh):
    with dpg.window(tag=_CMD_WIN,
                    pos=(0, TOP_BAR_H),
                    width=vw, height=vh-TOP_BAR_H,
                    no_title_bar=True, no_resize=True,
                    no_move=True, no_bring_to_display_on_focus=True):

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
                dpg.add_spacer(height=8)
                _cmd_button("▶  LOG INHOUSE GAME",
                            "Connect to LCU and log the last custom game.",
                            _run_inhouse)
                dpg.add_spacer(height=24)
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
    if dpg.does_item_exist("cmd_console"):
        _refresh_console()


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

    cmds.running = True
    _log(f"▶  {label}", C["gold"][:3])

    def _bg():
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
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    col = C["win"][:3] if line.startswith("✓") or "complete" in line.lower() \
                          else C["loss"][:3] if line.startswith("[ERR") or "error" in line.lower() \
                          else C["txt"][:3]
                    _log(line, col)
            proc.wait(timeout=300)
            if proc.returncode == 0:
                _log(f"✓  {label} complete.", C["win"][:3])
            else:
                _log(f"[!] Exited with code {proc.returncode}.", C["loss"][:3])
        except FileNotFoundError:
            _log(f"[ERR] Script not found: {script_name}", C["loss"][:3])
        except subprocess.TimeoutExpired:
            proc.kill()
            _log("[ERR] Timed out after 5 minutes.", C["loss"][:3])
        except Exception as e:
            _log(f"[ERR] {e}", C["loss"][:3])
        finally:
            cmds.running = False

    threading.Thread(target=_bg, daemon=True, name=label).start()


def _run_fetch_ranks():
    _run_script("Fetching ranks…", "fetch_ranks_gsheets.py")


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
    _log(f"▶  Joining tier list: {name}  ({riot})", C["gold"][:3])
    _log("  (Stub: write to Google Sheet in Phase 7)", C["txt_dim"][:3])
    dpg.configure_item("join_status",
                        default_value=f"✓  {name} queued for addition.")
    dpg.add_spacer(height=6, parent=_JOIN_WIN)
