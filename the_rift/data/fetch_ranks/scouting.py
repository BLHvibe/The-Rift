"""Auto-generated module — split from fetch_ranks_gsheets.py."""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

import requests
import gspread
from google.oauth2.service_account import Credentials

# Optional engine import for shared synergy + counter data.
try:
    from data import draft_engine as _eng  # type: ignore
except Exception:
    try:
        import draft_engine as _eng  # type: ignore
    except Exception:
        _eng = None

from .constants import *
from .sheets import get_or_create_sheet, fmt_title, fmt_header, sheets_retry
from .scoring import compute_score, rank_to_chart_value
from .riot import riot_get, fetch_scouting_matches


# ── Scouting analysis + writers + DB ───────────────────────

def analyze_player(matches):
    """Full statistical analysis of a player's match history.

    Phase 2 rewrite: preserves per-champion chronological win/loss `results`
    list (last ~100 ranked+draft games, oldest→newest) so the draft engine's
    `recency_weighted_wr` can weight recent ranked form alongside customs.

    `matches` arrives from `fetch_scouting_matches` in NEWEST-FIRST order
    (that's how Riot's match-IDs endpoint returns them). We append in iter
    order then reverse when emitting so the persisted `results` is oldest→
    newest, matching the customs `results` convention.
    """
    if not matches:
        return None
    total = len(matches)
    wins = sum(1 for m in matches if m["win"])

    champ_stats = defaultdict(lambda: {
        "games": 0, "wins": 0, "kills": 0, "deaths": 0,
        "assists": 0, "cs_min": 0, "damage": 0, "gold": 0,
        "results": [],   # newest-first during iteration; reversed at emit
    })
    for m in matches:
        c = champ_stats[m["champion"]]
        c["games"] += 1
        c["wins"] += 1 if m["win"] else 0
        c["kills"] += m["kills"]
        c["deaths"] += m["deaths"]
        c["assists"] += m["assists"]
        c["cs_min"] += m["cs_min"]
        c["damage"] += m["damage"]
        c["gold"] += m["gold"]
        c["results"].append(1 if m["win"] else 0)

    champ_list = []
    for name, s in champ_stats.items():
        g = s["games"]
        champ_list.append({
            "name": name, "games": g, "wins": s["wins"], "losses": g - s["wins"],
            "wr": round(s["wins"] / g * 100, 1),
            "avg_kills": round(s["kills"] / g, 1),
            "avg_deaths": round(s["deaths"] / g, 1),
            "avg_assists": round(s["assists"] / g, 1),
            "kda": round((s["kills"] + s["assists"]) / max(s["deaths"], 1), 2),
            "avg_cs_min": round(s["cs_min"] / g, 1),
            "avg_damage": round(s["damage"] / g),
            "avg_gold": round(s["gold"] / g),
            # Phase 2: chronological win/loss list, oldest→newest, capped at
            # ~100 ranked+draft games. The engine reads this from the scout
            # sheet (column M) via reader._parse_scouting_sheet.
            "results": list(reversed(s["results"])),
        })
    champ_list.sort(key=lambda x: x["games"], reverse=True)

    unique_champs = len(champ_list)
    pool_label = ("ONE-TRICK" if unique_champs <= 4 else
                  "SMALL POOL" if unique_champs <= 9 else
                  "MODERATE POOL" if unique_champs <= 16 else "DEEP POOL")

    must_bans = sorted(
        [c for c in champ_list if c["games"] >= 5 and c["wr"] >= 65],
        key=lambda x: x["wr"], reverse=True)

    top3_names = set(c["name"] for c in champ_list[:3])
    remaining = [m for m in matches if m["champion"] not in top3_names]
    ban3_wr = round(sum(1 for m in remaining if m["win"]) / len(remaining) * 100, 1) if remaining else 0
    ban3_games = len(remaining)

    role_map = {"TOP": "Top", "JUNGLE": "Jungle", "MIDDLE": "Mid",
                "BOTTOM": "Bot", "UTILITY": "Support", "UNKNOWN": "Other"}
    role_counts = defaultdict(int)
    for m in matches:
        role_counts[role_map.get(m["role"], "Other")] += 1
    role_list = sorted(
        [{"role": r, "games": c, "pct": round(c / total * 100, 1)}
         for r, c in role_counts.items() if c > 0],
        key=lambda x: x["games"], reverse=True)

    role_champs = defaultdict(lambda: defaultdict(lambda: {"games": 0, "wins": 0}))
    for m in matches:
        role = role_map.get(m["role"], "Other")
        rc = role_champs[role][m["champion"]]
        rc["games"] += 1
        rc["wins"] += 1 if m["win"] else 0

    avg_kills = round(sum(m["kills"] for m in matches) / total, 1)
    avg_deaths = round(sum(m["deaths"] for m in matches) / total, 1)
    avg_assists = round(sum(m["assists"] for m in matches) / total, 1)
    avg_cs_min = round(sum(m["cs_min"] for m in matches) / total, 1)
    avg_damage = round(sum(m["damage"] for m in matches) / total)
    avg_vision = round(sum(m["vision"] for m in matches) / total, 1)
    avg_gold = round(sum(m["gold"] for m in matches) / total)
    overall_kda = round((avg_kills + avg_assists) / max(avg_deaths, 1), 2)
    overall_wr = round(wins / total * 100, 1)
    fb_rate = round(sum(1 for m in matches if m["first_blood"]) / total * 100, 1)

    recent = matches[:10]
    recent_wins = sum(1 for m in recent if m["win"])
    recent_wr = round(recent_wins / len(recent) * 100, 1) if recent else 0
    form = ("HOT" if recent_wr > overall_wr + 10 else
            "COLD" if recent_wr < overall_wr - 10 else "STEADY")

    return {
        "total": total, "wins": wins, "losses": total - wins,
        "wr": overall_wr, "overall_kda": overall_kda,
        "avg_kills": avg_kills, "avg_deaths": avg_deaths,
        "avg_assists": avg_assists, "avg_cs_min": avg_cs_min,
        "avg_damage": avg_damage, "avg_vision": avg_vision,
        "avg_gold": avg_gold, "fb_rate": fb_rate,
        "unique_champs": unique_champs, "pool_label": pool_label,
        "champ_list": champ_list, "must_bans": must_bans,
        "top3_names": list(top3_names), "ban3_wr": ban3_wr,
        "ban3_games": ban3_games,
        "role_list": role_list, "role_champs": dict(role_champs),
        "recent_wins": recent_wins, "recent_total": len(recent),
        "recent_wr": recent_wr, "form": form,
        "recent_matches": recent,
    }




def write_scouting_sheet(spreadsheet, player_name, rank_str, lp, analysis, ranking_info=None, inhouse_data=None):
    """Create a detailed, styled scouting sheet for one player."""
    a = analysis
    sheet_name = f"Scout - {player_name}"[:30]
    try:
        old = spreadsheet.worksheet(sheet_name)
        sheets_retry(spreadsheet.del_worksheet, old)
    except gspread.exceptions.WorksheetNotFound:
        pass

    # Phase 2: provision 14 columns (A:N) so the chronological win/loss
    # "Results" string at column M lands inside the worksheet bounds. Older
    # sheets created with cols=12 silently truncated column M, leaving the
    # engine's ranked-recency boost dataless.
    ws = sheets_retry(spreadsheet.add_worksheet, sheet_name, rows=120, cols=14)

    DARK = {"red": 0.11, "green": 0.11, "blue": 0.18}
    HEADER = {"red": 0.09, "green": 0.14, "blue": 0.28}
    SECTION = {"red": 0.13, "green": 0.17, "blue": 0.30}
    GOLD_TEXT = {"red": 0.91, "green": 0.72, "blue": 0.29}
    WHITE = {"red": 1, "green": 1, "blue": 1}
    L_BLUE = {"red": 0.88, "green": 0.92, "blue": 0.98}
    L_GREEN = {"red": 0.85, "green": 0.95, "blue": 0.85}
    L_RED = {"red": 0.98, "green": 0.88, "blue": 0.88}
    L_GOLD = {"red": 1.0, "green": 0.97, "blue": 0.88}

    rows = []
    fmts = []
    merges = []  # collect merge ranges to apply at end

    def rn():
        return len(rows)

    pad = lambda d: d + [""] * (12 - len(d))

    # ── HEADER ──
    # Timestamp is in col L (index 11). Merge only A:K so that L stays
    # unmerged and readable by the launcher via get_all_values().
    hdr_row = [f"SCOUTING REPORT: {player_name.upper()}"] + [""] * 10
    hdr_row.append(f"Scouted: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    rows.append(hdr_row)
    merges.append(f"A{rn()}:K{rn()}")
    fmts.append((f"A{rn()}:K{rn()}", {
        "backgroundColor": DARK,
        "textFormat": {"bold": True, "fontSize": 18, "foregroundColor": GOLD_TEXT},
        "horizontalAlignment": "CENTER"}))
    fmts.append((f"L{rn()}", {
        "backgroundColor": DARK,
        "textFormat": {"fontSize": 9, "italic": True, "foregroundColor": GOLD_TEXT},
        "horizontalAlignment": "RIGHT", "verticalAlignment": "MIDDLE"}))

    # Build subtitle with ranking info if available
    subtitle_parts = [rank_str, f"{lp} LP", f"{a['wins']}W-{a['losses']}L",
                      f"{a['wr']}% WR", f"{a['total']} games analyzed"]
    rows.append(pad(["  |  ".join(subtitle_parts)]))
    merges.append(f"A{rn()}:L{rn()}")
    fmts.append((f"A{rn()}:L{rn()}", {
        "backgroundColor": DARK,
        "textFormat": {"fontSize": 12, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    # ── POWER RANKING BAR ──
    if ranking_info:
        ri = ranking_info
        rank_bar = (f"POWER RANKING: #{ri['position']}  |  "
                    f"Final Score: {ri['score']}  |  "
                    f"Rating: {ri['rating']}  |  "
                    f"Tier Score (60%): {ri.get('tier_component', '?')}  |  "
                    f"Rank Score (40%): {ri.get('rank_component', '?')}")
        rows.append(pad([rank_bar]))
        merges.append(f"A{rn()}:L{rn()}")
        # Color based on rating
        rating_colors = {
            "S": {"red": 1.0, "green": 0.27, "blue": 0.27},
            "A": {"red": 1.0, "green": 0.55, "blue": 0.0},
            "B": {"red": 1.0, "green": 0.84, "blue": 0.0},
            "C": {"red": 0.2, "green": 0.8, "blue": 0.2},
            "D": {"red": 0.25, "green": 0.41, "blue": 0.88},
            "F": {"red": 0.5, "green": 0.5, "blue": 0.5},
        }
        bar_color = rating_colors.get(ri.get("rating", ""), SECTION)
        fmts.append((f"A{rn()}:L{rn()}", {
            "backgroundColor": bar_color,
            "textFormat": {"bold": True, "fontSize": 13, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

    # ── OVERVIEW STATS ──
    rows.append(pad([""]))
    rows.append(pad(["KDA", "Avg Kills", "Avg Deaths", "Avg Assists",
                     "CS/min", "Avg Damage", "Avg Vision", "Avg Gold",
                     "FB %", "Form", "Pool Depth", "Unique Champs"]))
    fmts.append((f"A{rn()}:L{rn()}", {
        "backgroundColor": HEADER,
        "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    form_lbl = f"{a['form']} ({a['recent_wins']}/{a['recent_total']})"
    rows.append(pad([a["overall_kda"], a["avg_kills"], a["avg_deaths"],
                     a["avg_assists"], a["avg_cs_min"], f"{a['avg_damage']:,}",
                     a["avg_vision"], f"{a['avg_gold']:,}", f"{a['fb_rate']}%",
                     form_lbl, a["pool_label"], a["unique_champs"]]))
    fmts.append((f"A{rn()}:L{rn()}", {
        "backgroundColor": L_BLUE,
        "textFormat": {"bold": True, "fontSize": 11},
        "horizontalAlignment": "CENTER"}))

    # ── MUST-BAN ──
    rows.append(pad([""]))
    rows.append(pad(["BAN THESE CHAMPIONS"]))
    merges.append(f"A{rn()}:L{rn()}")
    fmts.append((f"A{rn()}:L{rn()}", {
        "backgroundColor": {"red": 0.6, "green": 0.1, "blue": 0.1},
        "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    if a["must_bans"]:
        rows.append(pad(["Champion", "Games", "Wins", "Losses", "Win Rate",
                         "KDA", "Avg Kills", "Avg Deaths", "Avg Assists",
                         "CS/min", "Avg Damage", "Threat"]))
        fmts.append((f"A{rn()}:L{rn()}", {
            "backgroundColor": HEADER,
            "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))
        for c in a["must_bans"]:
            threat = ("PERMABAN" if c["wr"] >= 75 and c["games"] >= 5 else
                      "HIGH" if c["wr"] >= 70 else "ELEVATED")
            rows.append(pad([c["name"], c["games"], c["wins"], c["losses"],
                             f"{c['wr']}%", c["kda"], c["avg_kills"], c["avg_deaths"],
                             c["avg_assists"], c["avg_cs_min"], f"{c['avg_damage']:,}",
                             threat]))
            fmts.append((f"A{rn()}:L{rn()}", {
                "backgroundColor": L_RED,
                "textFormat": {"bold": True, "fontSize": 11},
                "horizontalAlignment": "CENTER"}))
    else:
        rows.append(pad(["No standout ban targets (no champ with 5+ games AND 65%+ WR)"]))
        merges.append(f"A{rn()}:L{rn()}")
        fmts.append((f"A{rn()}:L{rn()}", {
            "backgroundColor": L_GREEN,
            "textFormat": {"italic": True, "fontSize": 11},
            "horizontalAlignment": "CENTER"}))

    # ── BAN IMPACT ──
    rows.append(pad([""]))
    top3_str = ", ".join(a["top3_names"])
    rows.append(pad([f"BAN IMPACT: If you ban {top3_str} ...", "", "", "", "",
                     f"Remaining WR: {a['ban3_wr']}%", "", "", "",
                     f"({a['ban3_games']} games)"]))
    merges.append(f"A{rn()}:E{rn()}")
    merges.append(f"F{rn()}:L{rn()}")
    bg = L_GREEN if a["ban3_wr"] < 50 else L_RED
    fmts.append((f"A{rn()}:L{rn()}", {
        "backgroundColor": bg,
        "textFormat": {"bold": True, "fontSize": 11},
        "horizontalAlignment": "CENTER"}))

    # ── FULL CHAMPION POOL ──
    rows.append(pad([""]))
    rows.append(pad(["FULL CHAMPION POOL"]))
    merges.append(f"A{rn()}:L{rn()}")
    fmts.append((f"A{rn()}:L{rn()}", {
        "backgroundColor": SECTION,
        "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": GOLD_TEXT},
        "horizontalAlignment": "CENTER"}))

    # Phase 2: header now includes a 13th column "Results" at M containing
    # the chronological win/loss list (oldest→newest, comma-separated). The
    # `pad` lambda pads to 12; a 13-element list is returned unchanged, so M
    # sits outside the A:L styled range as plain text. Reader parses M into
    # the engine's `results` field; older sheets without column M fall back
    # to empty `results` and the engine uses aggregate WR as today.
    rows.append(pad(["Champion", "Games", "Wins", "Losses", "Win Rate",
                     "KDA", "Avg Kills", "Avg Deaths", "Avg Assists",
                     "CS/min", "Avg Damage", "Avg Gold", "Results"]))
    fmts.append((f"A{rn()}:L{rn()}", {
        "backgroundColor": HEADER,
        "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    for i, c in enumerate(a["champ_list"]):
        bg_c = L_BLUE if i % 2 == 0 else {"red": 1, "green": 1, "blue": 1}
        results_str = ",".join(str(r) for r in (c.get("results") or []))
        rows.append(pad([c["name"], c["games"], c["wins"], c["losses"],
                         f"{c['wr']}%", c["kda"], c["avg_kills"], c["avg_deaths"],
                         c["avg_assists"], c["avg_cs_min"], f"{c['avg_damage']:,}",
                         f"{c['avg_gold']:,}", results_str]))
        fmts.append((f"A{rn()}", {"backgroundColor": bg_c,
                                   "textFormat": {"bold": True, "fontSize": 11}}))
        fmts.append((f"B{rn()}:L{rn()}", {"backgroundColor": bg_c,
                                            "textFormat": {"fontSize": 11},
                                            "horizontalAlignment": "CENTER"}))

    # ── ROLE BREAKDOWN ──
    rows.append(pad([""]))
    rows.append(pad(["ROLE BREAKDOWN"]))
    merges.append(f"A{rn()}:L{rn()}")
    fmts.append((f"A{rn()}:L{rn()}", {
        "backgroundColor": SECTION,
        "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": GOLD_TEXT},
        "horizontalAlignment": "CENTER"}))

    rows.append(pad(["Role", "Games", "% of Total", "Top Champions in Role"]))
    fmts.append((f"A{rn()}:L{rn()}", {
        "backgroundColor": HEADER,
        "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    for ri, r in enumerate(a["role_list"]):
        rc = a["role_champs"].get(r["role"], {})
        sorted_rc = sorted(rc.items(), key=lambda x: x[1]["games"], reverse=True)[:3]
        champ_str = ", ".join(f"{n} ({s['wins']}/{s['games']})" for n, s in sorted_rc)
        rows.append(pad([r["role"], r["games"], f"{r['pct']}%", champ_str]))
        merges.append(f"D{rn()}:L{rn()}")
        bg_r = L_GOLD if ri == 0 else {"red": 1, "green": 1, "blue": 1}
        fmts.append((f"A{rn()}:L{rn()}", {
            "backgroundColor": bg_r,
            "textFormat": {"fontSize": 11},
            "horizontalAlignment": "CENTER"}))

    # ── RECENT FORM ──
    rows.append(pad([""]))
    fc = ({"red": 0.1, "green": 0.5, "blue": 0.1} if a["form"] == "HOT"
          else {"red": 0.6, "green": 0.1, "blue": 0.1} if a["form"] == "COLD"
          else SECTION)
    rows.append(pad([f"RECENT FORM: {a['form']}  ({a['recent_wr']}% last {a['recent_total']} games)"]))
    merges.append(f"A{rn()}:L{rn()}")
    fmts.append((f"A{rn()}:L{rn()}", {
        "backgroundColor": fc,
        "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    rows.append(pad(["Game", "Result", "Champion", "Role", "K/D/A",
                     "KDA", "CS/min", "Damage", "Vision", "Gold", "Duration"]))
    fmts.append((f"A{rn()}:K{rn()}", {
        "backgroundColor": HEADER,
        "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    for i, m in enumerate(a["recent_matches"]):
        result = "WIN" if m["win"] else "LOSS"
        kda_s = f"{m['kills']}/{m['deaths']}/{m['assists']}"
        kda_r = round((m["kills"] + m["assists"]) / max(m["deaths"], 1), 2)
        role = {"TOP": "Top", "JUNGLE": "Jng", "MIDDLE": "Mid",
                "BOTTOM": "Bot", "UTILITY": "Sup"}.get(m["role"], "?")
        bg_m = L_GREEN if m["win"] else L_RED
        rows.append(pad([i + 1, result, m["champion"], role, kda_s,
                         kda_r, m["cs_min"], f"{m['damage']:,}",
                         m["vision"], f"{m['gold']:,}", f"{m['duration_min']}m"]))
        fmts.append((f"A{rn()}:K{rn()}", {
            "backgroundColor": bg_m,
            "textFormat": {"fontSize": 11, "bold": m["win"]},
            "horizontalAlignment": "CENTER"}))

    # ── IN-HOUSE CUSTOMS ──
    if inhouse_data:
        ih = inhouse_data
        rows.append(pad([""]))
        rows.append(pad([f"IN-HOUSE CUSTOM GAMES  ({ih['total_games']} games  |  {ih['total_wr']}% WR)"]))
        merges.append(f"A{rn()}:L{rn()}")
        fmts.append((f"A{rn()}:L{rn()}", {
            "backgroundColor": {"red": 0.4, "green": 0.2, "blue": 0.6},
            "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        rows.append(pad(["Champion", "Games", "Wins", "Losses", "Win Rate",
                         "KDA", "Avg Kills", "Avg Deaths", "Avg Assists",
                         "Avg Damage"]))
        fmts.append((f"A{rn()}:J{rn()}", {
            "backgroundColor": HEADER,
            "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        for i, c in enumerate(ih["champs"]):
            bg_c = {"red": 0.92, "green": 0.88, "blue": 0.98} if i % 2 == 0 else {"red": 1, "green": 1, "blue": 1}
            rows.append(pad([c["name"], c["games"], c["wins"], c["games"] - c["wins"],
                             f"{c['wr']}%", c["kda"], c["avg_kills"], c["avg_deaths"],
                             c["avg_assists"], f"{c['avg_damage']:,}"]))
            fmts.append((f"A{rn()}", {"backgroundColor": bg_c,
                                       "textFormat": {"bold": True, "fontSize": 11}}))
            fmts.append((f"B{rn()}:J{rn()}", {"backgroundColor": bg_c,
                                                "textFormat": {"fontSize": 11},
                                                "horizontalAlignment": "CENTER"}))

    # ── WRITE + FORMAT ──
    sheets_retry(ws.update, range_name="A1", values=rows)

    # Apply all tracked merges
    for m in merges:
        sheets_retry(ws.merge_cells, m)

    # Column widths
    col_px = [160, 80, 80, 80, 90, 80, 90, 100, 100, 90, 100, 120]
    reqs = []
    for ci, px in enumerate(col_px):
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                      "startIndex": ci, "endIndex": ci + 1},
            "properties": {"pixelSize": px}, "fields": "pixelSize"}})
    reqs.append({"updateDimensionProperties": {
        "range": {"sheetId": ws.id, "dimension": "ROWS",
                  "startIndex": 0, "endIndex": 1},
        "properties": {"pixelSize": 50}, "fields": "pixelSize"}})
    sheets_retry(spreadsheet.batch_update, {"requests": reqs})

    # Apply formats in batches
    for i in range(0, len(fmts), 15):
        batch = [{"range": r, "format": f} for r, f in fmts[i:i+15]]
        sheets_retry(ws.batch_format, batch)

    # Tab color by form
    tc = ({"red": 0.2, "green": 0.8, "blue": 0.2} if a["form"] == "HOT"
          else {"red": 0.8, "green": 0.2, "blue": 0.2} if a["form"] == "COLD"
          else {"red": 0.3, "green": 0.5, "blue": 0.9})
    sheets_retry(spreadsheet.batch_update, {"requests": [{
        "updateSheetProperties": {
            "properties": {"sheetId": ws.id, "tabColor": tc},
            "fields": "tabColor"}}]})

    print(f"  Scout - {player_name} done")


# ── Rankings lookup ────────────────────────────────────────────


def write_scouting_database(spreadsheet, all_scouting, rankings):
    """Save scouting data to a hidden sheet so --draft can use it later."""
    sheet_name = "_ScoutDB"
    try:
        old = spreadsheet.worksheet(sheet_name)
        sheets_retry(spreadsheet.del_worksheet, old)
    except gspread.exceptions.WorksheetNotFound:
        pass

    ws = sheets_retry(spreadsheet.add_worksheet, sheet_name, rows=500, cols=15)

    rows = [["SCOUTING DATABASE - DO NOT EDIT", "", "", "", "", "",
             datetime.now().strftime("%Y-%m-%d %H:%M")]]
    rows.append(["player", "champ", "games", "wins", "wr", "kda",
                 "avg_kills", "avg_deaths", "avg_assists", "avg_cs_min",
                 "avg_damage", "avg_gold", "role_data", "rank_pos", "rank_score"])

    for player_name, analysis in all_scouting.items():
        rank_info = rankings.get(player_name, {})
        rank_pos = rank_info.get("position", 99)
        rank_score = rank_info.get("score", 0)

        for champ in analysis.get("champ_list", []):
            # Build role data string
            role_str = ""
            for role, champs in analysis.get("role_champs", {}).items():
                if champ["name"] in champs:
                    role_str += f"{role}:{champs[champ['name']]['games']};"

            rows.append([
                player_name, champ["name"], champ["games"], champ["wins"],
                champ["wr"], champ["kda"], champ["avg_kills"], champ["avg_deaths"],
                champ["avg_assists"], champ["avg_cs_min"], champ["avg_damage"],
                champ["avg_gold"], role_str, rank_pos, rank_score,
            ])

    sheets_retry(ws.update, range_name="A1", values=rows)
    print(f"  Scouting database saved ({len(all_scouting)} players)")


def load_scouting_database(spreadsheet):
    """Load scouting data from the hidden database sheet."""
    try:
        ws = spreadsheet.worksheet("_ScoutDB")
    except gspread.exceptions.WorksheetNotFound:
        return {}, {}

    values = ws.get_all_values()
    if len(values) < 3:
        return {}, {}

    all_scouting = {}
    rankings = {}

    for row in values[2:]:  # skip header rows
        if len(row) < 12 or not row[0]:
            continue
        player = row[0]
        if player not in all_scouting:
            all_scouting[player] = {
                "champ_list": [], "must_bans": [], "role_champs": {},
            }

        try:
            games = int(row[2]) if row[2] else 0
            wins = int(row[3]) if row[3] else 0
            wr = float(row[4]) if row[4] else 0
            kda = float(row[5]) if row[5] else 0
            rank_pos = int(row[13]) if len(row) > 13 and row[13] else 99
            rank_score = float(row[14]) if len(row) > 14 and row[14] else 0
        except (ValueError, IndexError):
            continue

        champ = {
            "name": row[1], "games": games, "wins": wins,
            "losses": games - wins, "wr": wr, "kda": kda,
            "avg_kills": float(row[6]) if row[6] else 0,
            "avg_deaths": float(row[7]) if row[7] else 0,
            "avg_assists": float(row[8]) if row[8] else 0,
            "avg_cs_min": float(row[9]) if row[9] else 0,
            "avg_damage": int(float(row[10])) if row[10] else 0,
            "avg_gold": int(float(row[11])) if row[11] else 0,
        }

        all_scouting[player]["champ_list"].append(champ)
        if games >= 5 and wr >= 65:
            all_scouting[player]["must_bans"].append(champ)

        # Parse role data
        if len(row) > 12 and row[12]:
            for part in row[12].split(";"):
                if ":" in part:
                    role, count = part.split(":")
                    if role not in all_scouting[player]["role_champs"]:
                        all_scouting[player]["role_champs"][role] = {}
                    all_scouting[player]["role_champs"][role][row[1]] = {
                        "games": int(count), "wins": 0}

        rankings[player] = {"position": rank_pos, "score": rank_score,
                            "rating": "?"}

    return all_scouting, rankings



# ── In-House Stats Tracker ────────────────────────────────────
