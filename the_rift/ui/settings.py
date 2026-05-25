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
    "picker":      False,   # True when gameName not in summoner_map > show WHO ARE YOU
}

# ---------------------------------------------------------------------------
# Persistent settings state — loaded from config.json at import time
# ---------------------------------------------------------------------------
class SettingsState:
    def __init__(self):
        cfg = load_config()
        self.api_key       = cfg.get("api_key",    "")
        self.sheet_url     = cfg.get("sheet_url",  "")
        self.region        = cfg.get("region",     "na1")
        self.routing       = cfg.get("routing",    "americas")
        self.creds_path    = cfg.get("creds_path", "credentials.json")
        # Phase 5 — Draft Board UI cues (pygame.mixer wrapper). Mute toggle.
        self.audio_enabled = bool(cfg.get("audio_enabled", True))
        # Phase 3 — master volume scaler (0.0-1.0).
        self.audio_volume  = float(cfg.get("audio_volume", 1.0))
        # Phase 0a — global animation-intensity multiplier (0.0-1.0).
        self.anim_intensity = float(cfg.get("anim_intensity", 1.0))

    def save(self):
        cfg = load_config()
        cfg["api_key"]       = self.api_key
        cfg["sheet_url"]     = self.sheet_url
        cfg["region"]        = self.region
        cfg["routing"]       = self.routing
        cfg["creds_path"]    = self.creds_path
        cfg["audio_enabled"] = self.audio_enabled
        cfg["audio_volume"]  = self.audio_volume
        cfg["anim_intensity"] = self.anim_intensity
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
    _txt(dl, PAD, 12, "SETTINGS", (*C["gold"][:3],220), 22, "cinzel_22")

    # Settings form lives in a DPG window overlay for native input widgets.
    # Add a left inset so the content doesn't hug the sidebar (looked misplaced).
    LEFT_INSET = 32
    vp_w = dpg.get_viewport_width()
    sb_w = vp_w - vw   # actual current sidebar pixel width
    win_x = sb_w + LEFT_INSET
    win_w = max(360, vw - LEFT_INSET)
    if not dpg.does_item_exist(_SETTINGS_WIN):
        _build_settings_window(win_x, win_w, vh)
    else:
        # Reposition if viewport or sidebar width changed
        dpg.configure_item(_SETTINGS_WIN, pos=(win_x, TOP_BAR_H),
                           width=win_w, height=vh-TOP_BAR_H)


def _build_settings_window(sb_w, vw, vh):
    # Reset detection state for a fresh build
    _pfp_det["busy"]        = False
    _pfp_det["player_name"] = ""
    _pfp_det["summoner"]    = ""
    _pfp_det["picker"]      = False

    with dpg.window(tag=_SETTINGS_WIN,
                    pos=(sb_w, TOP_BAR_H),
                    width=vw, height=vh-TOP_BAR_H,
                    no_title_bar=True, no_resize=True,
                    no_move=True, no_focus_on_appearing=True):

        dpg.add_spacer(height=PAD)

        # ── API & Connection ──────────────────────────────────────────────
        _section_label("API & CONNECTION")

        _field_label("Riot API Key")
        api_inp = dpg.add_input_text(tag="set_api_key", default_value=settings.api_key,
                                     password=True, width=440, hint="RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        dpg.add_spacer(height=10)

        # Phase E (sheet decommission): the "Google Sheets URL" + "Credentials
        # JSON" config fields are gone — every data path goes through the
        # Fly REST API now. Region/routing stay, since the Riot fetcher
        # still needs them. Hidden inputs preserve the old tags so
        # _save_settings can read them without crashing the form.
        dpg.add_input_text(tag="set_sheet_url",  show=False,
                           default_value=settings.sheet_url)
        dpg.add_input_text(tag="set_creds_path", show=False,
                           default_value=settings.creds_path)
        dpg.add_text(tag="set_conn_status", show=False, default_value="")

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

        dpg.add_spacer(height=28)
        dpg.add_separator()
        dpg.add_spacer(height=20)

        # ── Profile Icons ─────────────────────────────────────────────────
        _section_label("PROFILE ICONS")

        with dpg.group():
            dpg.add_text(
                "Upload your avatar — every group member sees it next time their app refreshes.",
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
                    label=" Upload Avatar", callback=_save_icon,
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

        # ── Draft Board ───────────────────────────────────────────────────
        _section_label("DRAFT BOARD")
        with dpg.group():
            dpg.add_text(
                "AUDIO — six short UI cues fire as the draft progresses: pick "
                "lock, ban, your-turn chime, archetype stinger, pivot alert, "
                "and a draft-complete flourish. Uncheck to mute.",
                color=C["txt_dim"][:3], wrap=560)
            dpg.add_spacer(height=8)
            am = dpg.add_checkbox(tag="set_audio_enabled",
                                  label="  Enable audio cues",
                                  default_value=settings.audio_enabled,
                                  callback=_apply_audio_enabled)
            if "raj_sb_14" in _F:
                dpg.bind_item_font(am, _F["raj_sb_14"])

            # Phase 3 — master volume scaler
            dpg.add_spacer(height=10)
            dpg.add_text("MASTER VOLUME — scales every cue from quiet (0) "
                         "to full (1).",
                         color=C["txt_dim"][:3], wrap=560)
            dpg.add_spacer(height=4)
            with dpg.group(horizontal=True):
                vsld = dpg.add_slider_float(
                    tag="set_audio_volume",
                    default_value=settings.audio_volume,
                    min_value=0.0, max_value=1.0, format="%.2f",
                    width=300, callback=_apply_audio_volume)
                if "raj_r_16" in _F:
                    dpg.bind_item_font(vsld, _F["raj_r_16"])
                dpg.add_spacer(width=14)
                vlbl = dpg.add_text(f"{int(settings.audio_volume * 100)}%",
                                    tag="set_audio_volume_label",
                                    color=C["gold_lt"][:3])
                if "raj_sb_16" in _F:
                    dpg.bind_item_font(vlbl, _F["raj_sb_16"])

        dpg.add_spacer(height=28)
        dpg.add_separator()
        dpg.add_spacer(height=20)

        # ── Interface ─────────────────────────────────────────────────────
        _section_label("INTERFACE")
        with dpg.group():
            dpg.add_text(
                "ANIMATION — how much ambient and persistent motion the app "
                "shows. Lower it for a calmer, snappier feel; 0 turns ambient "
                "motion off entirely.",
                color=C["txt_dim"][:3], wrap=560)
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                sld = dpg.add_slider_float(
                    tag="set_anim_intensity",
                    default_value=settings.anim_intensity,
                    min_value=0.0, max_value=1.0, format="%.2f",
                    width=300, callback=_apply_anim_intensity)
                if "raj_r_16" in _F:
                    dpg.bind_item_font(sld, _F["raj_r_16"])
                dpg.add_spacer(width=14)
                il = dpg.add_text(tag="set_anim_intensity_lbl",
                                  default_value=_intensity_label(settings.anim_intensity),
                                  color=C["gold_lt"][:3])
                if "raj_sb_16" in _F:
                    dpg.bind_item_font(il, _F["raj_sb_16"])

        dpg.add_spacer(height=28)
        dpg.add_separator()
        dpg.add_spacer(height=20)

        # ── Data API (Phase 1) ────────────────────────────────────────────
        _section_label("DATA API")
        with dpg.group():
            dpg.add_text(
                "Match data mirrors into a SQLite store on the Fly server so "
                "the engine and future surfaces can read it directly. New "
                "inhouse logs go up automatically; use BACKFILL to push every "
                "row of _InhouseGameLog into the DB (idempotent — safe to "
                "re-run). BACK UP TO SHEET writes a faithful DB snapshot to "
                "_RiftDB_* tabs as a human-readable recovery source. REPAIR "
                "MATCH HISTORY scans the server for matches with fewer than "
                "10 participants (the role-collision bug) and re-posts the "
                "full LCU payload — needs the League client running.",
                color=C["txt_dim"][:3], wrap=560)
            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                bf_btn = dpg.add_button(label="BACKFILL FROM SHEET",
                                        callback=_backfill_db, width=200, height=28)
                if "raj_sb_14" in _F: dpg.bind_item_font(bf_btn, _F["raj_sb_14"])
                dpg.add_spacer(width=12)
                mr_btn = dpg.add_button(label="BACK UP TO SHEET",
                                        callback=_mirror_db, width=180, height=28)
                if "raj_sb_14" in _F: dpg.bind_item_font(mr_btn, _F["raj_sb_14"])
                dpg.add_spacer(width=12)
                rp_btn = dpg.add_button(label="REPAIR MATCH HISTORY",
                                        callback=_repair_matches, width=220, height=28)
                if "raj_sb_14" in _F: dpg.bind_item_font(rp_btn, _F["raj_sb_14"])
            dpg.add_spacer(height=6)
            dpg.add_text(tag="set_dataapi_status", default_value="",
                         color=C["txt_dim"][:3])

        dpg.add_spacer(height=28)
        dpg.add_separator()
        dpg.add_spacer(height=20)

        # ── Draft Engine (Phase 2) ────────────────────────────────────────
        _section_label("DRAFT ENGINE")
        with dpg.group():
            dpg.add_text(
                "Server-side engine — counters / synergies / champion strength "
                "are blended from DB data via Bayesian shrinkage and fall back "
                "to the hand-authored priors when sample is small. Refresh "
                "rebuilds the blended tables; backtest replays every logged "
                "match and reports the engine's hit-rate.",
                color=C["txt_dim"][:3], wrap=560)
            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                info_btn = dpg.add_button(label="ENGINE INFO",
                                          callback=_engine_info, width=140, height=28)
                if "raj_sb_14" in _F: dpg.bind_item_font(info_btn, _F["raj_sb_14"])
                dpg.add_spacer(width=10)
                rs_btn = dpg.add_button(label="REFRESH SIGNALS",
                                        callback=_engine_refresh, width=170, height=28)
                if "raj_sb_14" in _F: dpg.bind_item_font(rs_btn, _F["raj_sb_14"])
                dpg.add_spacer(width=10)
                bt_btn = dpg.add_button(label="RUN BACKTEST",
                                        callback=_engine_backtest, width=150, height=28)
                if "raj_sb_14" in _F: dpg.bind_item_font(bt_btn, _F["raj_sb_14"])
            dpg.add_spacer(height=6)
            dpg.add_text(tag="set_engine_status", default_value="",
                         color=C["txt_dim"][:3], wrap=560)

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


def _apply_audio_volume():
    """Phase 3 — master volume slider moved. Live-applies + persists."""
    if not dpg.does_item_exist("set_audio_volume"):
        return
    v = float(dpg.get_value("set_audio_volume"))
    settings.audio_volume = max(0.0, min(1.0, v))
    if dpg.does_item_exist("set_audio_volume_label"):
        dpg.set_value("set_audio_volume_label",
                      f"{int(settings.audio_volume * 100)}%")
    try:
        from ui import audio as _audio
        _audio.set_volume(settings.audio_volume)
    except Exception:
        pass
    settings.save()


def _apply_audio_enabled():
    """Audio toggle changed — persist and apply to the live audio module."""
    enabled = (bool(dpg.get_value("set_audio_enabled"))
               if dpg.does_item_exist("set_audio_enabled") else True)
    settings.audio_enabled = enabled
    settings.save()
    try:
        from ui import audio as _audio
        _audio.set_enabled(enabled)
    except Exception:
        pass


def _intensity_label(v):
    """Human-readable label for an animation-intensity value."""
    if v <= 0.01:
        return "Off"
    if v < 0.34:
        return "Subtle"
    if v < 0.67:
        return "Balanced"
    if v < 0.99:
        return "Lively"
    return "Full"


def _apply_anim_intensity():
    """Animation-intensity slider changed — persist and apply live."""
    v = (float(dpg.get_value("set_anim_intensity"))
         if dpg.does_item_exist("set_anim_intensity") else 1.0)
    settings.anim_intensity = v
    settings.save()
    if dpg.does_item_exist("set_anim_intensity_lbl"):
        dpg.configure_item("set_anim_intensity_lbl",
                           default_value=_intensity_label(v))
    try:
        from core.animations import anim
        anim.set_intensity(v)
    except Exception:
        pass


def _save_settings():
    settings.api_key    = dpg.get_value("set_api_key")
    settings.sheet_url  = dpg.get_value("set_sheet_url")
    settings.region     = dpg.get_value("set_region")
    settings.routing    = dpg.get_value("set_routing")
    settings.creds_path = dpg.get_value("set_creds_path")
    if dpg.does_item_exist("set_audio_enabled"):
        settings.audio_enabled = bool(dpg.get_value("set_audio_enabled"))
    if dpg.does_item_exist("set_anim_intensity"):
        settings.anim_intensity = float(dpg.get_value("set_anim_intensity"))
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
    Map Riot gameName > in-house display name.
    Same priority order as the tier list: live sheet map > config map > direct match.
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
    """Persist a new gameName > player_name mapping to config."""
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


def _engine_info():
    """Pull /api/engine/info on a background thread and show key counts."""
    if dpg.does_item_exist("set_engine_status"):
        dpg.configure_item("set_engine_status",
                           default_value="⟳  Querying engine…",
                           color=C["txt_dim"][:3])

    def _bg():
        try:
            from data import engine_api
            info = engine_api.info()
            if not info:
                _set_engine_status("✗  Engine unreachable.", C["loss"])
                return
            s = info.get("signals", {})
            msg = (f"✓  engine={info.get('engine','?')}  "
                   f"counters={s.get('counter_keys',0)}  "
                   f"synergies={s.get('synergy_keys',0)}  "
                   f"strength={s.get('strength_keys',0)}  "
                   f"k={s.get('shrinkage_k','?')}  "
                   f"refreshed={s.get('last_refresh','never')}")
            _set_engine_status(msg, C["win"])
        except Exception as e:
            _set_engine_status(f"✗  {str(e)[:80]}", C["loss"])

    threading.Thread(target=_bg, daemon=True, name="engine_info").start()


def _engine_refresh():
    """Force a rebuild of the blended signal tables."""
    if dpg.does_item_exist("set_engine_status"):
        dpg.configure_item("set_engine_status",
                           default_value="⟳  Rebuilding signal tables…",
                           color=C["txt_dim"][:3])

    def _bg():
        try:
            from data import engine_api
            r = engine_api.refresh_signals()
            if r and r.get("ok"):
                msg = (f"✓  refreshed at {r.get('at','?')}  "
                       f"counters={r.get('counter_keys',0)}  "
                       f"synergies={r.get('synergy_keys',0)}  "
                       f"strength={r.get('strength_keys',0)}")
                _set_engine_status(msg, C["win"])
            else:
                _set_engine_status("✗  refresh failed.", C["loss"])
        except Exception as e:
            _set_engine_status(f"✗  {str(e)[:80]}", C["loss"])

    threading.Thread(target=_bg, daemon=True, name="engine_refresh").start()


def _engine_backtest():
    """Replay every logged match through the engine and show the hit-rate."""
    if dpg.does_item_exist("set_engine_status"):
        dpg.configure_item("set_engine_status",
                           default_value="⟳  Running backtest…",
                           color=C["txt_dim"][:3])

    def _bg():
        try:
            from data import engine_api
            r = engine_api.backtest_run()
            if not r:
                _set_engine_status("✗  Backtest unreachable.", C["loss"])
                return
            s = r.get("summary", {})
            acc = s.get("accuracy", 0.0)
            msg = (f"✓  {s.get('correct',0)}/{s.get('matches',0)} "
                   f"({acc*100:.1f}% accuracy)  "
                   f"skipped={s.get('skipped',0)}  "
                   f"at={s.get('at','?')}")
            color = C["win"] if acc >= 0.5 else C["gold_dk"]
            _set_engine_status(msg, color)
        except Exception as e:
            _set_engine_status(f"✗  {str(e)[:80]}", C["loss"])

    threading.Thread(target=_bg, daemon=True, name="engine_backtest").start()


def _set_engine_status(msg, color):
    if dpg.does_item_exist("set_engine_status"):
        dpg.configure_item("set_engine_status",
                           default_value=msg, color=color[:3])


def _backfill_db():
    """Push every row of _InhouseGameLog into the REST API store."""
    if dpg.does_item_exist("set_dataapi_status"):
        dpg.configure_item("set_dataapi_status",
                           default_value="⟳  Reading sheet & posting…",
                           color=C["txt_dim"][:3])

    def _prog(msg):
        if dpg.does_item_exist("set_dataapi_status"):
            dpg.configure_item("set_dataapi_status",
                               default_value=f"⟳  {msg}",
                               color=C["txt_dim"][:3])

    def _done(counts):
        if dpg.does_item_exist("set_dataapi_status"):
            ok = counts.get("ingested", 0)
            bad = counts.get("failed", 0)
            n  = counts.get("games_found", 0)
            msg = f"✓  {ok} of {n} games ingested" + (
                  f" ({bad} failed)" if bad else "")
            dpg.configure_item("set_dataapi_status",
                               default_value=msg, color=C["win"][:3])
        # Invalidate cached match/records data so the freshly ingested rows
        # show up in HISTORY / RIVALS / RECORDS on next view.
        try:
            from data.reader import live, load_match_history, load_records
            with live._lock:
                live.match_history = []
                live.match_history_loaded = False
                live.match_history_error = None
                live.records = {}
                live.records_loaded = False
                live.records_error = None
                live.rivalries = {}
                live.rivalries_loaded = {}
                live.rivalries_error = None
            if counts.get("ingested", 0):
                load_match_history()
                load_records()
        except Exception:
            pass

    def _err(msg):
        if dpg.does_item_exist("set_dataapi_status"):
            dpg.configure_item("set_dataapi_status",
                               default_value=f"✗  {str(msg)[:80]}",
                               color=C["loss"][:3])

    try:
        from data.sheet_mirror import backfill_from_sheets
        backfill_from_sheets(on_progress=_prog, on_done=_done, on_error=_err)
    except Exception as e:
        _err(str(e))


def _mirror_db():
    """Pull /api/export and rewrite the _RiftDB_* mirror tabs."""
    if dpg.does_item_exist("set_dataapi_status"):
        dpg.configure_item("set_dataapi_status",
                           default_value="⟳  Pulling export & writing sheets…",
                           color=C["txt_dim"][:3])

    def _prog(msg):
        if dpg.does_item_exist("set_dataapi_status"):
            dpg.configure_item("set_dataapi_status",
                               default_value=f"⟳  {msg}",
                               color=C["txt_dim"][:3])

    def _done(counts):
        if dpg.does_item_exist("set_dataapi_status"):
            msg = (f"✓  Backed up {counts.get('matches',0)} matches, "
                   f"{counts.get('participants',0)} participants, "
                   f"{counts.get('drafts',0)} drafts")
            dpg.configure_item("set_dataapi_status",
                               default_value=msg, color=C["win"][:3])

    def _err(msg):
        if dpg.does_item_exist("set_dataapi_status"):
            dpg.configure_item("set_dataapi_status",
                               default_value=f"✗  {str(msg)[:80]}",
                               color=C["loss"][:3])

    try:
        from data.sheet_mirror import full_refresh
        full_refresh(on_progress=_prog, on_done=_done, on_error=_err)
    except Exception as e:
        _err(str(e))


def _repair_matches():
    """Walk every server-side match, re-fetch any with <10 participants from
    the local LCU, and post the full payload back. Needs the League client
    running. Idempotent and safe to re-run."""
    if dpg.does_item_exist("set_dataapi_status"):
        dpg.configure_item("set_dataapi_status",
                           default_value="⟳  Scanning matches…",
                           color=C["txt_dim"][:3])

    def _prog(msg):
        if dpg.does_item_exist("set_dataapi_status"):
            dpg.configure_item("set_dataapi_status",
                               default_value=f"⟳  {msg}",
                               color=C["txt_dim"][:3])

    def _done(counts):
        if dpg.does_item_exist("set_dataapi_status"):
            chk = counts.get("checked", 0)
            rep = counts.get("repaired", 0)
            sk  = counts.get("skipped", 0)
            fl  = counts.get("failed", 0)
            msg = (f"✓  Checked {chk}, repaired {rep}"
                   + (f", skipped {sk}" if sk else "")
                   + (f", failed {fl}" if fl else ""))
            dpg.configure_item("set_dataapi_status",
                               default_value=msg, color=C["win"][:3])
        # Invalidate cached views so the user sees the freshly repaired
        # participants when they next open HISTORY / RIVALS / RECORDS.
        try:
            from data.reader import live, load_match_history, load_records
            with live._lock:
                live.match_history = []
                live.match_history_loaded = False
                live.match_history_error = None
                live.records = {}
                live.records_loaded = False
                live.records_error = None
                live.rivalries = {}
                live.rivalries_loaded = {}
                live.rivalries_error = None
            # Kick off a fresh fetch in the background so the data is warm.
            if rep:
                load_match_history()
                load_records()
        except Exception:
            pass

    def _err(msg):
        if dpg.does_item_exist("set_dataapi_status"):
            dpg.configure_item("set_dataapi_status",
                               default_value=f"✗  {str(msg)[:80]}",
                               color=C["loss"][:3])

    try:
        from data.reader import repair_match_participants
        repair_match_participants(on_progress=_prog,
                                  on_done=_done, on_error=_err)
    except Exception as e:
        _err(str(e))


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
