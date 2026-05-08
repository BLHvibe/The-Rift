"""
Settings Tab — Phase 7.
Config fields wired to data/config.py (reads/writes config.json).
"""
import threading
import dearpygui.dearpygui as dpg
from theme import C
from data.config import load_config, save_config
from data.reader import test_sheets_connection

_F = {}
def set_fonts(f): global _F; _F = f

_SETTINGS_WIN = "settings_overlay_win"

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
            dpg.add_text("Link a summoner name to a player to enable profile icon upload.",
                         color=C["txt_dim"][:3])
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                with dpg.group():
                    _field_label("Display Name (from player list)")
                    dpg.add_input_text(tag="set_icon_display_name", width=220,
                                       hint="e.g. Ben")
                dpg.add_spacer(width=16)
                with dpg.group():
                    _field_label("Riot ID  (name#tag)")
                    dpg.add_input_text(tag="set_icon_riot_id", width=220,
                                       hint="PlayerName#NA1")
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Verify with Riot API", callback=_verify_riot,
                               width=180, height=32)
                dpg.add_spacer(width=12)
                dpg.add_text(tag="set_riot_verify_status", default_value="",
                             color=C["txt_dim"][:3])
            dpg.add_spacer(height=10)
            _field_label("Profile Image  (will be hex-cropped)")
            with dpg.group(horizontal=True):
                dpg.add_input_text(tag="set_icon_path", width=400,
                                   hint="C:\\path\\to\\image.png or .jpg")
                dpg.add_spacer(width=8)
                dpg.add_button(label="Browse…", callback=_browse_icon, width=90, height=28)
            dpg.add_spacer(height=10)
            dpg.add_button(label="Save Profile Icon", callback=_save_icon,
                           width=160, height=34)
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
        root = tk.Tk(); root.withdraw()
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
        root = tk.Tk(); root.withdraw()
        path = filedialog.askopenfilename(
            title="Select profile image",
            filetypes=[("Images","*.png *.jpg *.jpeg"),("All files","*.*")])
        root.destroy()
        if path:
            dpg.set_value("set_icon_path", path)
    except Exception:
        pass


def _verify_riot():
    riot_id = dpg.get_value("set_icon_riot_id").strip()
    api_key = dpg.get_value("set_api_key").strip() or settings.api_key
    if not riot_id or "#" not in riot_id:
        dpg.configure_item("set_riot_verify_status", default_value="⚠  Enter a Riot ID (Name#TAG)")
        return
    name, tag = riot_id.split("#", 1)
    dpg.configure_item("set_riot_verify_status", default_value="⟳  Verifying...")
    import requests
    def _bg():
        try:
            url = f"https://{settings.routing}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{name}/{tag}"
            r = requests.get(url, headers={"X-Riot-Token": api_key}, timeout=8)
            if r.status_code == 200:
                data = r.json()
                dpg.configure_item("set_riot_verify_status",
                    default_value=f"✓  Found: {data['gameName']}#{data['tagLine']}")
            elif r.status_code == 404:
                dpg.configure_item("set_riot_verify_status", default_value="✗  Riot ID not found.")
            else:
                dpg.configure_item("set_riot_verify_status",
                    default_value=f"✗  API error {r.status_code}")
        except Exception as e:
            dpg.configure_item("set_riot_verify_status", default_value=f"✗  {e}")
    threading.Thread(target=_bg, daemon=True).start()


def _save_icon():
    name  = dpg.get_value("set_icon_display_name")
    riot  = dpg.get_value("set_icon_riot_id")
    path  = dpg.get_value("set_icon_path")
    if not name or not path:
        dpg.configure_item("set_icon_status", default_value="⚠  Fill in display name and image path.")
        return
    dpg.configure_item("set_icon_status",
                        default_value=f"✓  Icon queued for {name}. (Riot API wiring in Phase 7)")


def close_settings_window():
    if dpg.does_item_exist(_SETTINGS_WIN):
        dpg.delete_item(_SETTINGS_WIN)
