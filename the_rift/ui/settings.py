"""
Settings Tab — Phase 7.
Config fields wired to data/config.py (reads/writes config.json).
"""
import threading, os, sys, math
import dearpygui.dearpygui as dpg
from theme import C
from data.config import load_config, save_config
from data.reader import test_sheets_connection, upload_player_avatar, download_all_avatars, detect_lcu_summoner


def _app_root():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _hex_crop(src_path, dst_path, size=200):
    """Crop an image to a flat-top hexagon and save as PNG."""
    try:
        from PIL import Image, ImageDraw
        img = Image.open(src_path).convert("RGBA")
        img = img.resize((size, size), Image.LANCZOS)

        mask = Image.new("L", (size, size), 0)
        draw = ImageDraw.Draw(mask)
        cx, cy, r = size // 2, size // 2, size // 2 - 2
        pts = [
            (cx + r * math.cos(math.pi / 6 + i * math.pi / 3),
             cy + r * math.sin(math.pi / 6 + i * math.pi / 3))
            for i in range(6)
        ]
        draw.polygon(pts, fill=255)

        result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        result.paste(img, mask=mask)
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        result.save(dst_path, "PNG")
        return True, ""
    except ImportError:
        return False, "Pillow not installed — run: pip install Pillow"
    except Exception as e:
        return False, str(e)

_F = {}
def set_fonts(f): global _F; _F = f

_SETTINGS_WIN = "settings_overlay_win"

# ---------------------------------------------------------------------------
# PFP detection state  (persists for the lifetime of the settings window)
# ---------------------------------------------------------------------------
_pfp_det = {
    "busy":        False,
    "player_name": "",      # resolved display name (e.g. "Ben")
    "summoner":    "",      # raw Riot gameName returned by LCU
    "picker":      False,   # True when gameName not in summoner_map → show WHO ARE YOU
}

# ---------------------------------------------------------------------------
# Persistent settings state — loaded from config.json at import time
# ---------------------------------------------------------------------------
class SettingsState:
    def __init__(self):
        cfg = load_config()
        self.api_key    = cfg.get("api_key",    "")
        self.sheet_url  = cfg.get("sheet_url",  "")
        self.region     = cfg.get("region",     "na1")
        self.routing    = cfg.get("routing",    "americas")
        self.creds_path = cfg.get("creds_path", "credentials.json")

    def save(self):
        cfg = load_config()
        cfg["api_key"]    = self.api_key
        cfg["sheet_url"]  = self.sheet_url
        cfg["region"]     = self.region
        cfg["routing"]    = self.routing
        cfg["creds_path"] = self.creds_path
        save_config(cfg)

settings = SettingsState()

REGIONS  = ["na1","euw1","eun1","kr","jp1","br1","la1","la2","oc1","tr1","ru"]
ROUTINGS = ["americas","europe","asia","sea"]

TOP_BAR_H = 52
PAD       = 28


def _txt(dl, x, y, text, color, size, font_key=None):
    tag = dpg.draw_text((x, y), text, color=color, size=size, parent=dl)
    if font_key and font_key in _F:
        dpg.bind_item_font(tag, _F[font_key])
    return tag


def draw_settings(dl, vw, vh, fonts=None):
    if fonts:
        set_fonts(fonts)
    dpg.delete_item(dl, children_only=True)
    dpg.draw_rectangle((0,0),(vw,vh), fill=C["bg"], color=(0,0,0,0), parent=dl)

    # Top bar
    dpg.draw_rectangle((0,0),(vw,TOP_BAR_H), fill=(*C["panel"][:3],220),
                        color=(0,0,0,0), parent=dl)
    dpg.draw_line((0,TOP_BAR_H-1),(vw,TOP_BAR_H-1),
                  color=C["rule_dark"], thickness=1, parent=dl)
    _txt(dl, PAD, 12, "SETTINGS", (*C["gold"][:3],220), 22, "raj_24")

    # Settings form lives in a DPG window overlay for native input widgets
    if not dpg.does_item_exist(_SETTINGS_WIN):
        _build_settings_window(vw, vh)
    else:
        # Reposition if viewport resized
        dpg.configure_item(_SETTINGS_WIN,
                           pos=(68, TOP_BAR_H),
                           width=vw-68, height=vh-TOP_BAR_H)


def _build_settings_window(vw, vh):
    # Reset detection state for a fresh build
    _pfp_det["busy"]        = False
    _pfp_det["player_name"] = ""
    _pfp_det["summoner"]    = ""
    _pfp_det["picker"]      = False

    with dpg.window(tag=_SETTINGS_WIN,
                    pos=(68, TOP_BAR_H),
                    width=vw-68, height=vh-TOP_BAR_H,
                    no_title_bar=True, no_resize=True,
                    no_move=True, no_focus_on_appearing=True):

        dpg.add_spacer(height=PAD)

        # ── API & Connection ──────────────────────────────────────────────
        _section_label("API & CONNECTION")

        _field_label("Riot API Key")
        api_inp = dpg.add_input_text(tag="set_api_key", default_value=settings.api_key,
                                     password=True, width=440, hint="RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        dpg.add_spacer(height=10)

        _field_label("Google Sheets URL or Sheet Name")
        dpg.add_input_text(tag="set_sheet_url", default_value=settings.sheet_url,
                            width=560, hint="https://docs.google.com/spreadsheets/d/... or sheet name")
        dpg.add_spacer(height=6)
        with dpg.group(horizontal=True):
            test_btn = dpg.add_button(label="TEST CONNECTION", callback=_test_connection,
                                       width=160, height=28)
            if "raj_sb_14" in _F:
                dpg.bind_item_font(test_btn, _F["raj_sb_14"])
            dpg.add_spacer(width=12)
            dpg.add_text(tag="set_conn_status", default_value="",
                         color=C["txt_dim"][:3])
        dpg.add_spacer(height=6)

        with dpg.group(horizontal=True):
            with dpg.group():
                _field_label("Region")
                dpg.add_combo(tag="set_region", items=REGIONS,
                              default_value=settings.region, width=160)
            dpg.add_spacer(width=24)
            with dpg.group():
                _field_label("Routing")
                dpg.add_combo(tag="set_routing", items=ROUTINGS,
                              default_value=settings.routing, width=160)

        dpg.add_spacer(height=10)

        _field_label("Google Credentials JSON Path")
        with dpg.group(horizontal=True):
            dpg.add_input_text(tag="set_creds_path", default_value=settings.creds_path,
                                width=480, hint="C:\\path\\to\\credentials.json")
            dpg.add_spacer(width=8)
            dpg.add_button(label="Browse…", callback=_browse_creds,
                           width=90, height=28)

        dpg.add_spacer(height=28)
        dpg.add_separator()
        dpg.add_spacer(height=20)

        # ── Profile Icons ─────────────────────────────────────────────────
        _section_label("PROFILE ICONS")

        with dpg.group():
            dpg.add_text(
                "Upload your avatar — it syncs to Google Sheets so every group member sees it.",
                color=C["txt_dim"][:3])
            dpg.add_spacer(height=10)

            # Identity row — detected automatically from LoL client, no manual entry
            _field_label("Identity (detected from LoL Client)")
            with dpg.group(horizontal=True):
                dpg.add_text(tag="pfp_det_status",
                             default_value="⟳  Detecting from LoL client…",
                             color=C["txt_dim"][:3])
                dpg.add_spacer(width=14)
                retry_btn = dpg.add_button(label="⟳  Re-detect",
                                           callback=_trigger_pfp_detect,
                                           width=110, height=24)
                if "raj_sb_14" in _F: dpg.bind_item_font(retry_btn, _F["raj_sb_14"])
            dpg.add_spacer(height=8)

            # WHO ARE YOU picker — shown only when gameName isn't in summoner_map
            with dpg.group(tag="pfp_picker_group", show=False):
                dpg.add_text(tag="pfp_picker_label", default_value="",
                             color=C["txt_dim"][:3])
                dpg.add_spacer(height=6)
                with dpg.group(horizontal=True):
                    dpg.add_combo(tag="pfp_picker_combo", items=[], width=200)
                    dpg.add_spacer(width=10)
                    confirm_btn = dpg.add_button(label="Confirm",
                                                 callback=_confirm_pfp_picker,
                                                 width=90, height=28)
                    if "raj_sb_14" in _F: dpg.bind_item_font(confirm_btn, _F["raj_sb_14"])
                dpg.add_spacer(height=8)

            # Image upload row
            _field_label("Profile Image  (hex-cropped to 128×128 automatically)")
            with dpg.group(horizontal=True):
                dpg.add_input_text(tag="set_icon_path", width=400,
                                   hint="C:\\path\\to\\image.png or .jpg")
                dpg.add_spacer(width=8)
                dpg.add_button(label="Browse…", callback=_browse_icon, width=90, height=28)
            dpg.add_spacer(height=12)

            # Action buttons
            with dpg.group(horizontal=True):
                save_btn = dpg.add_button(
                    label="◆  Upload Avatar", callback=_save_icon,
                    width=160, height=34,
                )
                if "raj_sb_14" in _F: dpg.bind_item_font(save_btn, _F["raj_sb_14"])
                dpg.add_spacer(width=14)
                sync_btn = dpg.add_button(
                    label="↓  Sync All Avatars", callback=_sync_all_avatars,
                    width=180, height=34,
                )
                if "raj_sb_14" in _F: dpg.bind_item_font(sync_btn, _F["raj_sb_14"])
            dpg.add_spacer(height=6)
            dpg.add_text(tag="set_icon_status", default_value="",
                         color=C["win"][:3])

        dpg.add_spacer(height=28)
        dpg.add_separator()
        dpg.add_spacer(height=20)

        # ── Save row ──────────────────────────────────────────────────────
        with dpg.group(horizontal=True):
            save_btn = dpg.add_button(label="  SAVE SETTINGS  ",
                                      callback=_save_settings,
                                      width=180, height=40)
            dpg.add_spacer(width=16)
            dpg.add_text(tag="set_save_status", default_value="",
                         color=C["win"][:3])

        dpg.add_spacer(height=40)

    # Auto-trigger mandatory LCU detection now that widgets exist
    _trigger_pfp_detect()


def _section_label(text):
    t = dpg.add_text(text, color=C["gold"][:3])
    if "raj_sb_18" in _F:
        dpg.bind_item_font(t, _F["raj_sb_18"])
    dpg.add_spacer(height=6)


def _field_label(text):
    t = dpg.add_text(text, color=C["txt_dim"][:3])
    if "raj_sb_14" in _F:
        dpg.bind_item_font(t, _F["raj_sb_14"])
    dpg.add_spacer(height=3)


def _test_connection():
    # Save current URL/creds to config first so the test uses live values
    settings.sheet_url  = dpg.get_value("set_sheet_url")
    settings.creds_path = dpg.get_value("set_creds_path")
    settings.save()
    if dpg.does_item_exist("set_conn_status"):
        dpg.configure_item("set_conn_status",
                           default_value="⟳  Connecting…",
                           color=C["txt_dim"][:3])
    def _done(title):
        if dpg.does_item_exist("set_conn_status"):
            dpg.configure_item("set_conn_status",
                               default_value=f"✓  Connected: {title}",
                               color=C["win"][:3])
    def _err(msg):
        if dpg.does_item_exist("set_conn_status"):
            dpg.configure_item("set_conn_status",
                               default_value=f"✗  {msg[:80]}",
                               color=C["loss"][:3])
    test_sheets_connection(on_done=_done, on_error=_err)


def _save_settings():
    settings.api_key    = dpg.get_value("set_api_key")
    settings.sheet_url  = dpg.get_value("set_sheet_url")
    settings.region     = dpg.get_value("set_region")
    settings.routing    = dpg.get_value("set_routing")
    settings.creds_path = dpg.get_value("set_creds_path")
    try:
        settings.save()
        dpg.configure_item("set_save_status", default_value="✓  Settings saved.")
    except Exception as e:
        dpg.configure_item("set_save_status", default_value=f"⚠  Save failed: {e}")


def _browse_creds():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        root.update()
        path = filedialog.askopenfilename(
            title="Select credentials.json",
            filetypes=[("JSON files","*.json"),("All files","*.*")])
        root.destroy()
        if path:
            dpg.set_value("set_creds_path", path)
    except Exception:
        pass


def _browse_icon():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        root.update()
        path = filedialog.askopenfilename(
            title="Select profile image",
            filetypes=[("Images","*.png *.jpg *.jpeg"),("All files","*.*")])
        root.destroy()
        if path:
            dpg.set_value("set_icon_path", path)
    except Exception:
        pass




def _resolve_pfp_summoner(game_name):
    """
    Map Riot gameName → in-house display name.
    Same priority order as the tier list: live sheet map → config map → direct match.
    Returns matched name or None.
    """
    from data.reader import live
    from data.config import load_config
    if live.loaded and live.summoner_map:
        result = live.summoner_map.get(game_name)
        if result:
            return result
    cfg  = load_config()
    smap = cfg.get("summoner_map", {})
    if game_name in smap:
        return smap[game_name]
    # Direct match — gameName == display name
    if live.loaded and live.players and game_name in live.players:
        return game_name
    return None


def _save_pfp_summoner_link(game_name, player_name):
    """Persist a new gameName → player_name mapping to config."""
    from data.config import load_config, save_config
    cfg  = load_config()
    smap = cfg.setdefault("summoner_map", {})
    smap[game_name] = player_name
    save_config(cfg)


def _trigger_pfp_detect():
    """Start mandatory LCU detection (also called automatically on first build)."""
    if _pfp_det["busy"]:
        return
    _pfp_det["busy"]        = True
    _pfp_det["player_name"] = ""
    _pfp_det["picker"]      = False

    if dpg.does_item_exist("pfp_det_status"):
        dpg.configure_item("pfp_det_status",
                           default_value="⟳  Detecting from LoL client…",
                           color=C["txt_dim"][:3])
    if dpg.does_item_exist("pfp_picker_group"):
        dpg.configure_item("pfp_picker_group", show=False)

    def _bg():
        game_name, err = detect_lcu_summoner()
        _pfp_det["busy"] = False

        if not game_name:
            if dpg.does_item_exist("pfp_det_status"):
                dpg.configure_item("pfp_det_status",
                                   default_value=f"✗  {err[:70]}",
                                   color=C["loss"][:3])
            return

        matched = _resolve_pfp_summoner(game_name)
        if matched:
            _pfp_det["player_name"] = matched
            if dpg.does_item_exist("pfp_det_status"):
                dpg.configure_item("pfp_det_status",
                                   default_value=f"✓  Detected as:  {matched}",
                                   color=C["win"][:3])
        else:
            # Unknown summoner — show WHO ARE YOU picker
            _pfp_det["summoner"] = game_name
            _pfp_det["picker"]   = True
            from data.reader import live
            players = list(live.players) if live.loaded and live.players else []
            if dpg.does_item_exist("pfp_det_status"):
                dpg.configure_item("pfp_det_status",
                                   default_value=f"⚠  '{game_name}' not in player list — select your name below:",
                                   color=(*C["gold_dk"][:3],))
            if dpg.does_item_exist("pfp_picker_label"):
                dpg.configure_item("pfp_picker_label",
                                   default_value=f"Detected Riot ID: '{game_name}'  — who are you?")
            if dpg.does_item_exist("pfp_picker_combo"):
                dpg.configure_item("pfp_picker_combo", items=players,
                                   default_value=players[0] if players else "")
            if dpg.does_item_exist("pfp_picker_group"):
                dpg.configure_item("pfp_picker_group", show=True)

    threading.Thread(target=_bg, daemon=True).start()


def _confirm_pfp_picker():
    """Called when user picks their name from the WHO ARE YOU combo."""
    selected = dpg.get_value("pfp_picker_combo") if dpg.does_item_exist("pfp_picker_combo") else ""
    selected = selected.strip()
    if not selected:
        return
    game_name = _pfp_det.get("summoner", "")
    if game_name:
        _save_pfp_summoner_link(game_name, selected)
    _pfp_det["player_name"] = selected
    _pfp_det["picker"]      = False
    if dpg.does_item_exist("pfp_det_status"):
        dpg.configure_item("pfp_det_status",
                           default_value=f"✓  Detected as:  {selected}",
                           color=C["win"][:3])
    if dpg.does_item_exist("pfp_picker_group"):
        dpg.configure_item("pfp_picker_group", show=False)


def _save_icon():
    name = _pfp_det.get("player_name", "").strip()
    if not name:
        if dpg.does_item_exist("set_icon_status"):
            dpg.configure_item("set_icon_status",
                               default_value="⚠  Identity not detected yet — use ⟳ Re-detect.")
        return

    path = dpg.get_value("set_icon_path").strip() if dpg.does_item_exist("set_icon_path") else ""
    if not path:
        if dpg.does_item_exist("set_icon_status"):
            dpg.configure_item("set_icon_status",
                               default_value="⚠  Select a profile image first.")
        return
    if not os.path.isfile(path):
        if dpg.does_item_exist("set_icon_status"):
            dpg.configure_item("set_icon_status",
                               default_value=f"⚠  File not found: {path}")
        return

    if dpg.does_item_exist("set_icon_status"):
        dpg.configure_item("set_icon_status", default_value="⟳  Uploading to cloud…")

    def _done(local_path):
        if dpg.does_item_exist("set_icon_status"):
            dpg.configure_item("set_icon_status",
                               default_value=f"✓  Avatar uploaded for {name}!")
        try:
            from ui.inhouse import queue_avatar_reload
            queue_avatar_reload(name, local_path)
        except Exception:
            pass

    def _err(msg):
        if dpg.does_item_exist("set_icon_status"):
            dpg.configure_item("set_icon_status",
                               default_value=f"✗  {msg[:80]}")

    upload_player_avatar(name, path, on_done=_done, on_error=_err)


def _sync_all_avatars():
    """Download all avatars from the cloud and refresh the inhouse display."""
    dpg.configure_item("set_icon_status", default_value="⟳  Downloading all avatars…")

    def _done(avatar_map):
        count = len(avatar_map)
        if dpg.does_item_exist("set_icon_status"):
            dpg.configure_item("set_icon_status",
                               default_value=f"✓  Synced {count} avatar{'s' if count != 1 else ''}")
        try:
            from ui.inhouse import queue_avatars_reload_all
            queue_avatars_reload_all(avatar_map)
        except Exception:
            pass

    def _err(msg):
        if dpg.does_item_exist("set_icon_status"):
            dpg.configure_item("set_icon_status",
                               default_value=f"✗  {msg[:80]}")

    download_all_avatars(on_done=_done, on_error=_err)


def close_settings_window():
    if dpg.does_item_exist(_SETTINGS_WIN):
        dpg.delete_item(_SETTINGS_WIN)
