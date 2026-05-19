"""
Draft Board v2.7 — Layout A right analytics rail + bottom narrative log
+ header action-queue preview (spec § 3 / § 4).

Every widget is defensive: a bad/empty datum draws an empty frame, never
raises, so the board can't be taken down by one analytics call. All engine
work is memoized by a picks-signature so re-running recommend_comps for the
win-probability gauge happens only when the board actually changes, not per
frame.

Text is drawn through a `txt` callback (pass ui.draft._txt) so this module
needs no font registry and stays import-cycle free. Shapes use ui.cyber.
"""
import math
import time
import dearpygui.dearpygui as dpg
from theme import C
from ui import cyber

try:
    from data import draft_engine as _eng
except Exception:                                    # pragma: no cover
    _eng = None


# ---------------------------------------------------------------------------
# Engine memo — recompute only when the locked picks/bans change
# ---------------------------------------------------------------------------
_cache = {
    "sig": None,
    "blue_combined": 0.0,
    "red_combined": 0.0,
    "winprob": 0.5,
    "history": [],          # last N win-prob samples (blue side)
}
_HIST_MAX = 24


def _state_sig(b):
    try:
        return (tuple(sorted(b.picks["BLUE"].items())),
                tuple(sorted(b.picks["RED"].items())),
                tuple(b.bans["BLUE"]), tuple(b.bans["RED"]))
    except Exception:
        return None


def _refresh_engine(b, inhouse, primary, scout=None):
    """Re-run recommend_comps for both sides when the board changed. Cheap
    because it is gated by the picks signature, not the frame clock."""
    sig = _state_sig(b)
    if sig == _cache["sig"]:
        return
    _cache["sig"] = sig
    bc = rc = 0.0
    scout = scout or {}
    if _eng is not None:
        for side, enemy, target_key in (("BLUE", "RED", "blue"),
                                        ("RED",  "BLUE", "red")):
            try:
                try:
                    res = _eng.recommend_comps(b.players[side], inhouse, primary,
                                               enemy_picks=b.locked_picks(enemy),
                                               n_results=1,
                                               scout_champs=scout)
                except TypeError:
                    res = _eng.recommend_comps(b.players[side], inhouse, primary,
                                               enemy_picks=b.locked_picks(enemy),
                                               n_results=1)
                val = float(res[0]["combined"]) if res else 0.0
            except Exception:
                val = 0.0
            if target_key == "blue":
                bc = val
            else:
                rc = val
    _cache["blue_combined"] = bc
    _cache["red_combined"] = rc
    tot = bc + rc
    wp = (bc / tot) if tot > 1e-6 else 0.5
    _cache["winprob"] = wp
    h = _cache["history"]
    h.append(wp)
    if len(h) > _HIST_MAX:
        del h[0:len(h) - _HIST_MAX]


# ---------------------------------------------------------------------------
# Small drawing helpers
# ---------------------------------------------------------------------------
def _panel(dl, x, y, w, h, title, txt, accent=None):
    """Corner-cut rail panel with a bracketed mono title. Returns the inner
    content top-y."""
    accent = accent or C["cy"][:3]
    cyber.draw_cut_rect(dl, x, y, x + w, y + h, cut=9,
                        fill=(*C["panel_dk"][:3], 225),
                        color=(*C["cy_dk"][:3], 200), thickness=1)
    cyber.draw_bracket_label(dl, x + 10, y + 7, title,
                             (*accent, 235), 12, txt, font_key="mono_12",
                             bracket_color=(*accent, 200), char_w=0.6)
    return y + 28


def _bar(dl, x, y, w, h, frac, col, bg=None):
    frac = max(0.0, min(1.0, frac))
    if bg is None:
        bg = (*C["bg"][:3], 150)
    cyber.draw_cut_rect(dl, x, y, x + w, y + h, cut=3, fill=bg, color=None)
    if frac > 0:
        cyber.draw_cut_rect(dl, x, y, x + max(2, int(w * frac)), y + h,
                            cut=3, fill=(*col[:3], 230), color=None)


def _poly(cx, cy, r, n, rot=-math.pi / 2):
    return [(cx + r * math.cos(rot + i * 2 * math.pi / n),
             cy + r * math.sin(rot + i * 2 * math.pi / n)) for i in range(n)]


# ---------------------------------------------------------------------------
# § 3 #1 — win-probability gauge + sparkline
# ---------------------------------------------------------------------------
def _w_winprob(dl, x, y, w, h, b, txt):
    cy0 = _panel(dl, x, y, w, h, "WIN PROBABILITY", txt)
    wp = _cache["winprob"]
    bar_y = cy0 + 6
    bar_h = 22
    bx, bw = x + 12, w - 24
    split = int(bw * wp)
    cyber.draw_cut_rect(dl, bx, bar_y, bx + split, bar_y + bar_h, cut=4,
                        fill=(*C["cy"][:3], 230), color=None)
    cyber.draw_cut_rect(dl, bx + split, bar_y, bx + bw, bar_y + bar_h, cut=4,
                        fill=(*C["mg"][:3], 230), color=None)
    cyber.draw_cut_rect(dl, bx, bar_y, bx + bw, bar_y + bar_h, cut=4,
                        fill=None, color=(*C["cy_dk"][:3], 200), thickness=1)
    txt(dl, bx, bar_y + bar_h + 6, f"BLUE {wp*100:4.1f}%",
        (*C["cy_lt"][:3], 240), 13, "mono_12")
    rs = f"{(1-wp)*100:4.1f}% RED"
    txt(dl, bx + bw - len(rs) * 8, bar_y + bar_h + 6, rs,
        (*C["mg_lt"][:3], 240), 13, "mono_12")
    # Sparkline of recent samples
    hist = _cache["history"][-16:]
    sp_y = bar_y + bar_h + 28
    sp_h = max(14, (y + h) - sp_y - 10)
    if len(hist) >= 2 and sp_h > 6:
        n = len(hist)
        step = bw / (n - 1)
        pts = [(bx + i * step, sp_y + sp_h - hist[i] * sp_h)
               for i in range(n)]
        for i in range(n - 1):
            dpg.draw_line(pts[i], pts[i + 1],
                          color=(*C["cy_lt"][:3], 200), thickness=2,
                          parent=dl)
        dpg.draw_line((bx, sp_y + sp_h * 0.5),
                      (bx + bw, sp_y + sp_h * 0.5),
                      color=(*C["cy_dk"][:3], 110), thickness=1, parent=dl)


# ---------------------------------------------------------------------------
# § 3 #3 — recommendation explanation (score-breakdown bars)
# ---------------------------------------------------------------------------
# (factor key, label, bar color) — the real per-suggestion "why".
_WHY_ROWS = (
    ("comfort",    "COMFORT",  "cy_lt"),
    ("counter",    "COUNTER",  "term_g"),
    ("lane",       "LANE",     "term_g"),
    ("contested",  "CONTEST",  "amb"),
    ("blind_safe", "SAFE",     "cy"),
    ("flex",       "FLEX",     "cy"),
    ("steer",      "FIT",      "cy"),
)


def _w_breakdown(dl, x, y, w, h, rec, txt):
    cy0 = _panel(dl, x, y, w, h, "WHY THIS CALL", txt)
    f = {}
    champ = ""
    try:
        s0 = (rec.get("suggestions") or [{}])[0]
        f = s0.get("factors") or {}
        champ = s0.get("champion", "")
    except Exception:
        f = {}
    if not f:
        # bans (and any pre-action state) have no per-pick factor breakdown
        msg = ("ban phase - see ban reason"
               if (rec.get("kind") == "ban") else "no suggestion yet")
        txt(dl, x + 12, cy0 + 8, msg, (*C["txt_dim"][:3], 200), 12, "mono_12")
        return
    if champ:
        txt(dl, x + 12, cy0, champ[:16], (*C["cy_lt"][:3], 235),
            13, "mono_12")
        cy0 += 18
    avail = (y + h) - cy0 - 6
    rh = max(13, min(19, avail // len(_WHY_ROWS)))
    ry = cy0 + 2
    lab_w = 64
    for key, lbl, col in _WHY_ROWS:
        try:
            v = max(0.0, min(1.0, float(f.get(key, 0.0))))
        except (TypeError, ValueError):
            v = 0.0
        # LANE: 0.5 == even lane; show deviation from even both ways.
        if key == "lane":
            cmid = x + 12 + lab_w + (w - 24 - lab_w - 34) // 2
            txt(dl, x + 12, ry, lbl, (*C[col][:3], 215), 11, "mono_11")
            half = (w - 24 - lab_w - 34) // 2
            adv = v - 0.5
            bx = x + 12 + lab_w
            cyber.draw_cut_rect(dl, bx, ry + 1, bx + half * 2, ry + rh - 5,
                                cut=3, fill=(*C["bg"][:3], 150), color=None)
            if adv >= 0:
                cyber.draw_cut_rect(dl, cmid, ry + 1,
                                    cmid + int(half * adv * 2), ry + rh - 5,
                                    cut=3, fill=(*C["term_g"][:3], 230),
                                    color=None)
            else:
                cyber.draw_cut_rect(dl, cmid + int(half * adv * 2), ry + 1,
                                    cmid, ry + rh - 5, cut=3,
                                    fill=(*C["mg_lt"][:3], 230), color=None)
            dpg.draw_line((cmid, ry), (cmid, ry + rh - 4),
                          color=(*C["txt2"][:3], 200), thickness=1, parent=dl)
        else:
            txt(dl, x + 12, ry, lbl, (*C[col][:3], 215), 11, "mono_11")
            _bar(dl, x + 12 + lab_w, ry + 1, w - 24 - lab_w - 34, rh - 6,
                 v, C[col])
        vs = f"{v:.2f}"
        txt(dl, x + w - 12 - len(vs) * 7, ry, vs,
            (*C["txt"][:3], 220), 11, "mono_11")
        ry += rh


# ---------------------------------------------------------------------------
# § 3 #11 — team-strength radar (overlaid cyan/magenta octagons)
# ---------------------------------------------------------------------------
_AXIS_ABBR = {
    "frontline": "FRONT", "engage": "ENGAGE", "peel": "PEEL",
    "aoe": "AOE", "burst": "BURST", "range": "RANGE",
    "scaling": "SCALE", "mobility": "MOBIL",
}


def _w_radar(dl, x, y, w, h, b, txt):
    cy0 = _panel(dl, x, y, w, h, "TEAM STRENGTH", txt)
    # Legend in the panel header row
    txt(dl, x + w - 98, y + 7, "BLUE", (*C["cy_lt"][:3], 235), 11, "mono_11")
    txt(dl, x + w - 50, y + 7, "RED", (*C["mg_lt"][:3], 235), 11, "mono_11")
    if _eng is None or not hasattr(_eng, "_team_vector"):
        return
    axes = list(getattr(_eng, "_AXES", ()))
    if not axes:
        return
    try:
        bv = _eng._team_vector(b.locked_picks("BLUE"))
        rv = _eng._team_vector(b.locked_picks("RED"))
    except Exception:
        return
    n = len(axes)
    cx = x + w // 2
    ccy = cy0 + ((y + h) - cy0) // 2 + 4
    r = min(w // 2 - 46, ((y + h) - cy0) // 2 - 14)
    if r < 14:
        return
    # Per-axis normalisation: a single dominant axis can't flatten the rest.
    amax = {ax: max(1.0, bv.get(ax, 0.0), rv.get(ax, 0.0)) for ax in axes}
    for ring in (0.5, 1.0):
        dpg.draw_polygon(_poly(cx, ccy, r * ring, n), fill=(0, 0, 0, 0),
                         color=(*C["cy_dk"][:3], 130), thickness=1,
                         parent=dl)
    for i, ax in enumerate(axes):
        ang = -math.pi / 2 + i * 2 * math.pi / n
        ex, ey = cx + r * math.cos(ang), ccy + r * math.sin(ang)
        dpg.draw_line((cx, ccy), (ex, ey),
                      color=(*C["cy_dk"][:3], 90), thickness=1, parent=dl)
        lab = _AXIS_ABBR.get(ax, ax[:5].upper())
        lx = cx + (r + 13) * math.cos(ang) - len(lab) * 3
        ly = ccy + (r + 13) * math.sin(ang) - 6
        lx = max(x + 4, min(x + w - len(lab) * 6 - 4, lx))
        txt(dl, lx, ly, lab, (*C["txt2"][:3], 215), 10, "mono_11")
    for vec, col in ((bv, C["cy_lt"]), (rv, C["mg_lt"])):
        pts = []
        for i, ax in enumerate(axes):
            f = max(0.05, vec.get(ax, 0.0) / amax[ax])
            ang = -math.pi / 2 + i * 2 * math.pi / n
            pts.append((cx + r * f * math.cos(ang),
                        ccy + r * f * math.sin(ang)))
        dpg.draw_polygon(pts, fill=(*col[:3], 50),
                         color=(*col[:3], 235), thickness=2, parent=dl)


# ---------------------------------------------------------------------------
# § 3 #15 — counter-coverage donut
# ---------------------------------------------------------------------------
def _w_coverage(dl, x, y, w, h, b, txt):
    cy0 = _panel(dl, x, y, w, h, "COUNTER COVERAGE", txt)
    our = b.locked_picks(b.our_side)
    enemy = b.locked_picks("RED" if b.our_side == "BLUE" else "BLUE")
    frac = 0.0
    if enemy and _eng is not None and hasattr(_eng, "COUNTERS"):
        ctr = _eng.COUNTERS
        covered = 0
        for e in enemy:
            if any(ctr.get((o, e), 0.0) >= 0.30 for o in our):
                covered += 1
        frac = covered / max(1, len(enemy))
    cx = x + w // 2
    ccy = cy0 + ((y + h) - cy0) // 2
    r = min(w // 2 - 24, ((y + h) - cy0) // 2 - 6)
    if r < 14:
        return
    seg = 48
    for i in range(seg):
        a0 = -math.pi / 2 + i * 2 * math.pi / seg
        a1 = -math.pi / 2 + (i + 1) * 2 * math.pi / seg
        on = (i / seg) < frac
        col = C["term_g"][:3] if on else C["cy_dk"][:3]
        dpg.draw_line((cx + r * math.cos(a0), ccy + r * math.sin(a0)),
                      (cx + r * math.cos(a1), ccy + r * math.sin(a1)),
                      color=(*col, 235 if on else 150), thickness=6,
                      parent=dl)
    ps = f"{int(round(frac*100))}%"
    txt(dl, cx - len(ps) * 6, ccy - 10, ps,
        (*C["term_g"][:3], 245), 18, "mono_18")


# ---------------------------------------------------------------------------
# § 3 #19 — AP / AD / True damage profile
# ---------------------------------------------------------------------------
def _w_damage(dl, x, y, w, h, b, txt):
    cy0 = _panel(dl, x, y, w, h, "DAMAGE PROFILE", txt)
    if _eng is None:
        return
    ap = ad = tr = 0.0
    for c in b.locked_picks(b.our_side):
        if c in getattr(_eng, "DAMAGE_HYBRID", set()):
            ap += 0.5
            ad += 0.5
        elif c in getattr(_eng, "DAMAGE_AP", set()):
            ap += 1
        elif c in getattr(_eng, "DAMAGE_TRUE", set()):
            tr += 1
        else:
            ad += 1
    tot = ap + ad + tr
    bx, bw = x + 12, w - 24
    by = cy0 + 8
    bh = 22
    if tot <= 0:
        cyber.draw_cut_rect(dl, bx, by, bx + bw, by + bh, cut=4,
                            fill=(*C["bg"][:3], 150), color=None)
        txt(dl, bx + 6, by + 3, "no picks yet",
            (*C["txt_dim"][:3], 200), 12, "mono_12")
        return
    segs = ((ap, C["mg_lt"], "AP"), (ad, C["amb"], "AD"),
            (tr, C["scan_gy"], "TR"))
    cxp = bx
    for val, col, lbl in segs:
        sw = int(bw * (val / tot))
        if sw <= 0:
            continue
        cyber.draw_cut_rect(dl, cxp, by, cxp + sw, by + bh, cut=3,
                            fill=(*col[:3], 230), color=None)
        if sw > 26:
            txt(dl, cxp + 5, by + 3, lbl, (*C["bg"][:3], 235), 12, "mono_12")
        cxp += sw
    txt(dl, bx, by + bh + 8,
        f"AP {int(ap)}  AD {int(ad)}  TRUE {int(tr)}",
        (*C["txt"][:3], 220), 12, "mono_12")


# ---------------------------------------------------------------------------
# § 3 #9 — contested champion ladder
# ---------------------------------------------------------------------------
def _w_contested(dl, x, y, w, h, b, rec, txt):
    cy0 = _panel(dl, x, y, w, h, "CONTESTED", txt)
    used_b = set(b.picks["BLUE"].values()) | set(b.bans["BLUE"])
    used_r = set(b.picks["RED"].values()) | set(b.bans["RED"])
    banned = set(b.bans["BLUE"]) | set(b.bans["RED"])
    picked = set(b.picks["BLUE"].values()) | set(b.picks["RED"].values())
    rows = []
    for s in (rec.get("suggestions") or []):
        ch = s.get("champion")
        if not ch or ch in [r[0] for r in rows]:
            continue
        if s.get("tag") in ("POWER", "FLEX") or ch in picked or ch in banned:
            st = ("BANNED" if ch in banned else
                  "PICKED" if ch in picked else "FREE")
            rows.append((ch, st))
        if len(rows) >= 6:
            break
    ry = cy0 + 4
    for ch, st in rows:
        if ry + 20 > y + h - 4:
            break
        scol = (C["mg"][:3] if st == "BANNED" else
                C["amb"][:3] if st == "PICKED" else C["term_g"][:3])
        txt(dl, x + 12, ry, ch[:12], (*C["txt"][:3], 230), 13, "raj_sb_14")
        txt(dl, x + w - 12 - len(st) * 8, ry, st,
            (*scol, 230), 11, "mono_11")
        ry += 21
    if not rows:
        txt(dl, x + 12, cy0 + 8, "no contested picks",
            (*C["txt_dim"][:3], 200), 12, "mono_12")


# ---------------------------------------------------------------------------
# § 3 #18 — synergy network graph (our locked picks)
# ---------------------------------------------------------------------------
def _w_synergy(dl, x, y, w, h, b, txt):
    cy0 = _panel(dl, x, y, w, h, "SYNERGY WEB", txt)
    picks = [c for c in b.locked_picks(b.our_side) if c]
    if _eng is None or len(picks) < 2:
        txt(dl, x + 12, cy0 + 8, "need 2+ picks",
            (*C["txt_dim"][:3], 200), 12, "mono_12")
        return
    syn = getattr(_eng, "SYNERGIES", {}) or {}
    anti = getattr(_eng, "ANTI_SYNERGIES", {}) or {}
    cx = x + w // 2
    ccy = cy0 + ((y + h) - cy0) // 2 + 2
    r = min(w // 2 - 26, ((y + h) - cy0) // 2 - 12)
    if r < 16:
        return
    n = len(picks)
    node = []
    for i in range(n):
        ang = -math.pi / 2 + i * 2 * math.pi / n
        node.append((cx + r * math.cos(ang), ccy + r * math.sin(ang)))
    for i in range(n):
        for j in range(i + 1, n):
            a, c = picks[i], picks[j]
            s = syn.get((a, c), syn.get((c, a), 0.0))
            an = anti.get((a, c), anti.get((c, a), 0.0))
            if s:
                dpg.draw_line(node[i], node[j],
                              color=(*C["term_g"][:3],
                                     min(235, 90 + int(s * 320))),
                              thickness=max(1, min(5, 1 + s * 8)),
                              parent=dl)
            elif an:
                dpg.draw_line(node[i], node[j],
                              color=(*C["mg_lt"][:3], 200),
                              thickness=2, parent=dl)
    for i, (nx, ny_) in enumerate(node):
        dpg.draw_polygon(_poly(nx, ny_, 11, 6),
                         fill=(*C["cy_dk"][:3], 230),
                         color=(*C["cy_lt"][:3], 235), thickness=2,
                         parent=dl)
        txt(dl, nx - 10, ny_ - 7, picks[i][:3].upper(),
            (*C["cy_lt"][:3], 240), 11, "mono_11")


# ---------------------------------------------------------------------------
# § 3 #2 — counter-pick predictor
# ---------------------------------------------------------------------------
def _w_predictor(dl, x, y, w, h, b, txt):
    cy0 = _panel(dl, x, y, w, h, "COUNTER PREDICTOR", txt)
    if _eng is None or not hasattr(_eng, "COUNTERS"):
        return
    ctr = _eng.COUNTERS
    our = set(b.locked_picks(b.our_side))
    enemy = [c for c in b.locked_picks("RED" if b.our_side == "BLUE"
                                       else "BLUE") if c]
    used = b.used_champs()
    rows = []
    for e in enemy:
        if any(ctr.get((o, e), 0.0) >= 0.30 for o in our):
            continue                                  # already covered
        best, bestv = None, 0.0
        for (atk, vic), v in ctr.items():
            if vic == e and v > bestv and atk not in used:
                best, bestv = atk, v
        if best:
            rows.append((e, best))
        if len(rows) >= 3:
            break
    ry = cy0 + 6
    if not rows:
        txt(dl, x + 12, ry, "enemy threats covered",
            (*C["term_g"][:3], 215), 12, "mono_12")
        return
    for e, ans in rows:
        if ry + 20 > y + h - 4:
            break
        txt(dl, x + 12, ry, e[:8], (*C["mg_lt"][:3], 230), 13, "raj_sb_14")
        txt(dl, x + 12 + 76, ry, "→", (*C["txt2"][:3], 210), 13, "mono_12")
        txt(dl, x + 12 + 98, ry, ans[:9],
            (*C["term_g"][:3], 235), 13, "raj_sb_14")
        ry += 22


# ---------------------------------------------------------------------------
# Public — right rail
# ---------------------------------------------------------------------------
def draw_rail(dl, x, y, w, h, b, rec, txt, inhouse, primary, scout=None):
    """Stack the analytics widgets down the right rail."""
    try:
        _refresh_engine(b, inhouse or {}, primary or {}, scout or {})
    except Exception:
        pass
    gap = 8
    cur = y
    plan = [
        (_w_winprob,   118, (b,)),
        (_w_breakdown, 146, (rec,)),
        (_w_radar,     148, (b,)),
        (_w_damage,    94,  (b,)),
        (_w_coverage,  112, (b,)),
        (_w_predictor, 116, (b,)),
        (_w_synergy,   150, (b,)),
        (_w_contested, 140, (b, rec)),
    ]
    for fn, ph, args in plan:
        if cur + 60 > y + h:
            break
        ph = min(ph, (y + h) - cur)
        try:
            fn(dl, x, cur, w, ph, *args, txt)
        except Exception:
            cyber.draw_cut_rect(dl, x, cur, x + w, cur + ph, cut=9,
                                fill=(*C["panel_dk"][:3], 220),
                                color=(*C["mg_dk"][:3], 180), thickness=1)
        cur += ph + gap


# ---------------------------------------------------------------------------
# § 3 #12 — draft narrative log (bottom terminal strip)
# ---------------------------------------------------------------------------
def draw_narrative(dl, x, y, w, h, b, txt):
    cyber.draw_cut_rect(dl, x, y, x + w, y + h, cut=6,
                        fill=(*C["panel_dk"][:3], 225),
                        color=(*C["cy_dk"][:3], 190), thickness=1)
    parts = []
    try:
        for hentry in list(b._history)[-7:]:
            side = "B" if hentry.side == "BLUE" else "R"
            verb = "BAN" if hentry.kind == "ban" else "PICK"
            parts.append(f"{side}{verb[:1]} {verb} {hentry.champ}")
    except Exception:
        parts = []
    line = "  ·  ".join(parts) if parts else "draft start — awaiting first action"
    txt(dl, x + 12, y + (h - 16) // 2, ("> " + line)[:max(8, (w - 24) // 8)],
        (*C["term_g"][:3], 225), 13, "mono_12")


# ---------------------------------------------------------------------------
# § 3 #27 — action-queue preview (header strip)
# ---------------------------------------------------------------------------
def draw_action_queue(dl, x, y, w, b, txt, seq):
    """Next few actions: B-PICK · R-PICK …  side-colored, drawn in the header."""
    try:
        ptr = b.pointer
        nxt = [a for a in seq if a.idx >= ptr][:4]
    except Exception:
        nxt = []
    cxp = x
    txt(dl, cxp, y, "QUEUE", (*C["cy"][:3], 200), 12, "mono_12")
    cxp += 56
    for a in nxt:
        col = C["cy_lt"][:3] if a.side == "BLUE" else C["mg_lt"][:3]
        lbl = f"{'B' if a.side=='BLUE' else 'R'}-{a.kind[:4].upper()}"
        cw = len(lbl) * 8 + 14
        cyber.draw_cut_rect(dl, cxp, y - 3, cxp + cw, y + 17, cut=4,
                            fill=(*col, 36), color=(*col, 170), thickness=1)
        txt(dl, cxp + 7, y, lbl, (*col, 235), 12, "mono_12")
        cxp += cw + 6
