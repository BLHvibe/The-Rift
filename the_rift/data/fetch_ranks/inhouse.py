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


# ── Inhouse stats ──────────────────────────────────────────

def load_inhouse_db(spreadsheet):
    """Load inhouse stats by reading directly from _InhouseGameLog.
    This ensures all games from all contributors are included."""
    try:
        ws = spreadsheet.worksheet("_InhouseGameLog")
        values = ws.get_all_values()
        if len(values) < 2: return {}

        # Parse all game records
        # Header: gameId, timestamp, player, champion, teamId, win, kills, deaths, assists, cs, damage, gold, vision, role, duration, logged_by
        records = []
        for row in values[1:]:
            if len(row) < 14 or not row[0]: continue
            try:
                records.append({
                    "gameId": row[0],
                    "player": row[2],
                    "champion": row[3],
                    "teamId": int(row[4]) if row[4] else 0,
                    "win": str(row[5]).upper() in ("TRUE", "1"),
                    "kills": int(float(row[6])) if row[6] else 0,
                    "deaths": int(float(row[7])) if row[7] else 0,
                    "assists": int(float(row[8])) if row[8] else 0,
                    "damage": int(float(row[10])) if len(row) > 10 and row[10] else 0,
                    "role": row[13] if len(row) > 13 else "Fill",
                })
            except (ValueError, IndexError): continue

        if not records:
            return {}

        # Compute stats per player
        inhouse = {}
        player_games = defaultdict(lambda: {"games": set(), "wins": 0})
        champ_stats = defaultdict(lambda: defaultdict(lambda: {
            "games": 0, "wins": 0, "kills": 0, "deaths": 0, "assists": 0,
            "damage": 0, "roles": defaultdict(int)}))

        # Group by game to count unique games per player
        games_by_id = defaultdict(list)
        for r in records:
            games_by_id[r["gameId"]].append(r)

        for gid, game_records in games_by_id.items():
            # Only count 5v5 games (10 players)
            if len(game_records) != 10:
                continue
            for r in game_records:
                name = r["player"]
                player_games[name]["games"].add(gid)
                if r["win"]:
                    player_games[name]["wins"] += 1

                cs = champ_stats[name][r["champion"]]
                cs["games"] += 1
                cs["wins"] += 1 if r["win"] else 0
                cs["kills"] += r["kills"]
                cs["deaths"] += r["deaths"]
                cs["assists"] += r["assists"]
                cs["damage"] += r["damage"]
                cs["roles"][r["role"]] += 1

        # Build output format
        for name, pg in player_games.items():
            total_g = len(pg["games"])
            total_wr = round(pg["wins"] / total_g * 100, 1) if total_g > 0 else 0

            champs = []
            for champ_name, cs in champ_stats[name].items():
                cg = cs["games"]
                if cg == 0: continue
                champs.append({
                    "name": champ_name,
                    "games": cg,
                    "wins": cs["wins"],
                    "wr": round(cs["wins"] / cg * 100, 1),
                    "kda": round((cs["kills"] + cs["assists"]) / max(cs["deaths"], 1), 2),
                    "avg_kills": round(cs["kills"] / cg, 1),
                    "avg_deaths": round(cs["deaths"] / cg, 1),
                    "avg_assists": round(cs["assists"] / cg, 1),
                    "avg_damage": round(cs["damage"] / cg),
                    "roles": dict(cs["roles"]),
                })

            champs.sort(key=lambda x: x["games"], reverse=True)
            inhouse[name] = {"total_games": total_g, "total_wr": total_wr, "champs": champs}

        print(f"  Loaded {len(inhouse)} players from game log ({sum(len(pg['games']) for pg in player_games.values())} player-game records)")
        return inhouse

    except gspread.exceptions.WorksheetNotFound:
        # Fall back to _InhouseDB if game log doesn't exist
        try:
            ws = spreadsheet.worksheet("_InhouseDB")
            values = ws.get_all_values()
            if len(values) < 3: return {}
            inhouse = {}
            for row in values[2:]:
                if len(row) < 10 or not row[0]: continue
                name = row[0]
                if name not in inhouse:
                    inhouse[name] = {"total_games": 0, "total_wr": 0, "champs": []}
                try:
                    inhouse[name]["total_games"] = int(float(row[10])) if len(row) > 10 and row[10] else 0
                    inhouse[name]["total_wr"] = float(row[11]) if len(row) > 11 and row[11] else 0
                    roles = {}
                    if len(row) > 12 and row[12]:
                        for part in row[12].split(";"):
                            if ":" in part:
                                r, c = part.split(":")
                                roles[r] = int(c)
                    inhouse[name]["champs"].append({
                        "name": row[1], "games": int(float(row[2])) if row[2] else 0,
                        "wins": int(float(row[3])) if row[3] else 0,
                        "wr": float(row[4]) if row[4] else 0,
                        "kda": float(row[5]) if row[5] else 0,
                        "avg_kills": float(row[6]) if row[6] else 0,
                        "avg_deaths": float(row[7]) if row[7] else 0,
                        "avg_assists": float(row[8]) if row[8] else 0,
                        "avg_damage": int(float(row[9])) if row[9] else 0,
                        "roles": roles,
                    })
                except (ValueError, IndexError): continue
            for name in inhouse:
                inhouse[name]["champs"].sort(key=lambda x: x["games"], reverse=True)
            return inhouse
        except Exception as e:
            print(f"Warning: failed to load inhouse DB fallback: {e}")
            return {}
    except Exception as e:
        print(f"Warning: failed to load inhouse data: {e}")
        return {}




def analyze_inhouse(inhouse_matches, player_puuid_map):
    """Crunch all in-house stats."""
    puuid_to_name = {v: k for k, v in player_puuid_map.items()}
    group_names = set(player_puuid_map.keys())

    # Per-player overall stats
    player_stats = defaultdict(lambda: {
        "games": 0, "wins": 0, "kills": 0, "deaths": 0, "assists": 0,
        "cs_min": 0, "damage": 0, "gold": 0, "vision": 0,
        "champs": defaultdict(lambda: {"games": 0, "wins": 0, "kills": 0,
                                        "deaths": 0, "assists": 0, "damage": 0}),
        "roles": defaultdict(lambda: {"games": 0, "wins": 0}),
    })

    # Head-to-head: h2h[playerA][playerB] = {"same_team": 0, "same_wins": 0,
    #                                         "vs": 0, "vs_wins": 0}
    h2h = defaultdict(lambda: defaultdict(lambda: {
        "same_team": 0, "same_wins": 0, "vs": 0, "vs_wins": 0}))

    role_map = {"TOP": "Top", "JUNGLE": "Jungle", "MIDDLE": "Mid",
                "BOTTOM": "Bot", "UTILITY": "Support", "UNKNOWN": "Fill"}

    for match in inhouse_matches:
        # Group players by team
        team_100 = []
        team_200 = []
        for p in match["players"]:
            if not p["is_group"]:
                continue
            name = p["name"]
            if p["team_id"] == 100:
                team_100.append(p)
            else:
                team_200.append(p)

            # Update player stats
            ps = player_stats[name]
            ps["games"] += 1
            ps["wins"] += 1 if p["win"] else 0
            ps["kills"] += p["kills"]
            ps["deaths"] += p["deaths"]
            ps["assists"] += p["assists"]
            ps["cs_min"] += p["cs_min"]
            ps["damage"] += p["damage"]
            ps["gold"] += p["gold"]
            ps["vision"] += p["vision"]

            # Champion stats
            cs = ps["champs"][p["champion"]]
            cs["games"] += 1
            cs["wins"] += 1 if p["win"] else 0
            cs["kills"] += p["kills"]
            cs["deaths"] += p["deaths"]
            cs["assists"] += p["assists"]
            cs["damage"] += p["damage"]

            # Role stats
            role = role_map.get(p["role"], "Fill")
            rs = ps["roles"][role]
            rs["games"] += 1
            rs["wins"] += 1 if p["win"] else 0

        # Head-to-head: same team pairs
        for team in [team_100, team_200]:
            for i in range(len(team)):
                for j in range(i + 1, len(team)):
                    a, b = team[i]["name"], team[j]["name"]
                    h2h[a][b]["same_team"] += 1
                    h2h[b][a]["same_team"] += 1
                    if team[i]["win"]:
                        h2h[a][b]["same_wins"] += 1
                        h2h[b][a]["same_wins"] += 1

        # Head-to-head: opposing team pairs
        for p1 in team_100:
            for p2 in team_200:
                a, b = p1["name"], p2["name"]
                h2h[a][b]["vs"] += 1
                h2h[b][a]["vs"] += 1
                if p1["win"]:
                    h2h[a][b]["vs_wins"] += 1
                else:
                    h2h[b][a]["vs_wins"] += 1

    return dict(player_stats), dict(h2h)




def write_inhouse_overview(spreadsheet, player_stats, total_games):
    """Write the main in-house stats overview sheet."""
    sheet_name = "In-House Stats"
    try:
        old = spreadsheet.worksheet(sheet_name)
        sheets_retry(spreadsheet.del_worksheet, old)
    except gspread.exceptions.WorksheetNotFound:
        pass

    ws = sheets_retry(spreadsheet.add_worksheet, sheet_name, rows=80, cols=14)

    DARK = {"red": 0.11, "green": 0.11, "blue": 0.18}
    HEADER = {"red": 0.09, "green": 0.14, "blue": 0.28}
    SECTION = {"red": 0.13, "green": 0.17, "blue": 0.30}
    GOLD_TEXT = {"red": 0.91, "green": 0.72, "blue": 0.29}
    WHITE = {"red": 1, "green": 1, "blue": 1}
    L_BLUE = {"red": 0.88, "green": 0.92, "blue": 0.98}
    L_GREEN = {"red": 0.85, "green": 0.95, "blue": 0.85}
    L_RED = {"red": 0.98, "green": 0.88, "blue": 0.88}

    rows = []
    fmts = []
    merges = []
    pad = lambda d, n=14: d + [""] * (n - len(d))
    rn = lambda: len(rows)

    # Title
    rows.append(pad(["IN-HOUSE 5v5 STATS"]))
    merges.append(f"A{rn()}:N{rn()}")
    fmts.append((f"A{rn()}:N{rn()}", {
        "backgroundColor": DARK,
        "textFormat": {"bold": True, "fontSize": 18, "foregroundColor": GOLD_TEXT},
        "horizontalAlignment": "CENTER"}))

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows.append(pad([f"{total_games} in-house games tracked  |  Last updated: {ts}"]))
    merges.append(f"A{rn()}:N{rn()}")
    fmts.append((f"A{rn()}:N{rn()}", {
        "backgroundColor": DARK,
        "textFormat": {"fontSize": 11, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    rows.append(pad([""]))

    # ── LEADERBOARD ──
    rows.append(pad(["IN-HOUSE LEADERBOARD"]))
    merges.append(f"A{rn()}:N{rn()}")
    fmts.append((f"A{rn()}:N{rn()}", {
        "backgroundColor": SECTION,
        "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": GOLD_TEXT},
        "horizontalAlignment": "CENTER"}))

    rows.append(pad(["#", "Player", "Games", "Wins", "Losses", "Win Rate",
                     "KDA", "Avg Kills", "Avg Deaths", "Avg Assists",
                     "Avg CS/min", "Avg Damage", "Avg Vision", "Avg Gold"]))
    fmts.append((f"A{rn()}:N{rn()}", {
        "backgroundColor": HEADER,
        "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    # Sort by win rate (min 3 games), then by games played
    sorted_players = sorted(
        player_stats.items(),
        key=lambda x: (
            x[1]["wins"] / max(x[1]["games"], 1) if x[1]["games"] >= 3 else 0,
            x[1]["games"]
        ),
        reverse=True
    )

    for i, (name, ps) in enumerate(sorted_players, 1):
        g = ps["games"]
        if g == 0:
            continue
        wr = round(ps["wins"] / g * 100, 1)
        kda = round((ps["kills"] + ps["assists"]) / max(ps["deaths"], 1), 2)
        bg = L_GREEN if i <= 3 else (L_BLUE if i % 2 == 0 else {"red": 1, "green": 1, "blue": 1})

        rows.append(pad([i, name, g, ps["wins"], g - ps["wins"],
                         f"{wr}%",
                         kda,
                         round(ps["kills"] / g, 1),
                         round(ps["deaths"] / g, 1),
                         round(ps["assists"] / g, 1),
                         round(ps["cs_min"] / g, 1),
                         f"{round(ps['damage'] / g):,}",
                         round(ps["vision"] / g, 1),
                         f"{round(ps['gold'] / g):,}"]))
        fmts.append((f"A{rn()}:N{rn()}", {
            "backgroundColor": bg,
            "textFormat": {"fontSize": 11, "bold": i <= 3},
            "horizontalAlignment": "CENTER"}))

    rows.append(pad([""]))
    rows.append(pad([""]))

    # ── PER-PLAYER CHAMPION STATS ──
    rows.append(pad(["IN-HOUSE CHAMPION STATS (per player)"]))
    merges.append(f"A{rn()}:N{rn()}")
    fmts.append((f"A{rn()}:N{rn()}", {
        "backgroundColor": SECTION,
        "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": GOLD_TEXT},
        "horizontalAlignment": "CENTER"}))

    for name, ps in sorted_players:
        if ps["games"] == 0:
            continue

        wr = round(ps["wins"] / ps["games"] * 100, 1)
        rows.append(pad([f"{name}  —  {ps['games']} games  |  {wr}% WR"]))
        merges.append(f"A{rn()}:N{rn()}")
        fmts.append((f"A{rn()}:N{rn()}", {
            "backgroundColor": {"red": 0.2, "green": 0.3, "blue": 0.5},
            "textFormat": {"bold": True, "fontSize": 12, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        rows.append(pad(["Champion", "Games", "Wins", "Losses", "Win Rate",
                         "KDA", "Avg Kills", "Avg Deaths", "Avg Assists",
                         "Avg Damage"]))
        fmts.append((f"A{rn()}:J{rn()}", {
            "backgroundColor": HEADER,
            "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        sorted_champs = sorted(ps["champs"].items(),
                                key=lambda x: x[1]["games"], reverse=True)
        for j, (champ, cs) in enumerate(sorted_champs):
            cg = cs["games"]
            cwr = round(cs["wins"] / cg * 100, 1)
            ckda = round((cs["kills"] + cs["assists"]) / max(cs["deaths"], 1), 2)
            bg = L_BLUE if j % 2 == 0 else {"red": 1, "green": 1, "blue": 1}

            rows.append(pad([champ, cg, cs["wins"], cg - cs["wins"],
                             f"{cwr}%", ckda,
                             round(cs["kills"] / cg, 1),
                             round(cs["deaths"] / cg, 1),
                             round(cs["assists"] / cg, 1),
                             f"{round(cs['damage'] / cg):,}"]))
            fmts.append((f"A{rn()}:J{rn()}", {
                "backgroundColor": bg,
                "textFormat": {"fontSize": 11},
                "horizontalAlignment": "CENTER"}))

        rows.append(pad([""]))

    rows.append(pad([""]))

    # ── ROLE STATS ──
    rows.append(pad(["IN-HOUSE ROLE PERFORMANCE"]))
    merges.append(f"A{rn()}:N{rn()}")
    fmts.append((f"A{rn()}:N{rn()}", {
        "backgroundColor": SECTION,
        "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": GOLD_TEXT},
        "horizontalAlignment": "CENTER"}))

    rows.append(pad(["Player", "Top", "", "Jungle", "", "Mid", "",
                     "Bot", "", "Support", ""]))
    fmts.append((f"A{rn()}:K{rn()}", {
        "backgroundColor": HEADER,
        "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    rows.append(pad(["", "Games", "WR%", "Games", "WR%", "Games", "WR%",
                     "Games", "WR%", "Games", "WR%"]))
    fmts.append((f"A{rn()}:K{rn()}", {
        "backgroundColor": HEADER,
        "textFormat": {"bold": True, "fontSize": 9, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    for name, ps in sorted_players:
        if ps["games"] == 0:
            continue
        row_data = [name]
        for role in ["Top", "Jungle", "Mid", "Bot", "Support"]:
            rs = ps["roles"].get(role, {"games": 0, "wins": 0})
            rg = rs["games"]
            rwr = f"{round(rs['wins'] / rg * 100)}%" if rg > 0 else "-"
            row_data.extend([rg if rg > 0 else "-", rwr])
        rows.append(pad(row_data))
        fmts.append((f"A{rn()}:K{rn()}", {
            "backgroundColor": L_BLUE,
            "textFormat": {"fontSize": 11},
            "horizontalAlignment": "CENTER"}))

    # Write everything in one batch
    sheets_retry(ws.update, values=rows, range_name="A1")

    for m in merges:
        sheets_retry(ws.merge_cells, m)

    col_px = [50, 120, 65, 60, 65, 75, 60, 75, 80, 80, 80, 100, 80, 100]
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

    for i in range(0, len(fmts), 15):
        batch = [{"range": r, "format": f} for r, f in fmts[i:i+15]]
        sheets_retry(ws.batch_format, batch)

    print("  In-House Stats overview written")




def write_inhouse_h2h(spreadsheet, h2h, player_stats):
    """Write head-to-head matrix sheet."""
    sheet_name = "In-House Head-to-Head"
    try:
        old = spreadsheet.worksheet(sheet_name)
        sheets_retry(spreadsheet.del_worksheet, old)
    except gspread.exceptions.WorksheetNotFound:
        pass

    # Only include players with games
    active = [n for n, ps in player_stats.items() if ps["games"] > 0]
    active.sort()
    n = len(active)

    ws = sheets_retry(spreadsheet.add_worksheet, sheet_name, rows=n * 2 + 10, cols=n + 3)

    DARK = {"red": 0.11, "green": 0.11, "blue": 0.18}
    HEADER = {"red": 0.09, "green": 0.14, "blue": 0.28}
    SECTION = {"red": 0.13, "green": 0.17, "blue": 0.30}
    GOLD_TEXT = {"red": 0.91, "green": 0.72, "blue": 0.29}
    WHITE = {"red": 1, "green": 1, "blue": 1}
    L_GREEN = {"red": 0.85, "green": 0.95, "blue": 0.85}
    L_RED = {"red": 0.98, "green": 0.88, "blue": 0.88}
    L_BLUE = {"red": 0.88, "green": 0.92, "blue": 0.98}

    rows = []
    fmts = []
    merges = []
    pad_n = n + 2
    pad = lambda d: d + [""] * (pad_n - len(d))
    rn = lambda: len(rows)

    # Title
    rows.append(pad(["IN-HOUSE HEAD-TO-HEAD"]))
    fmts.append((f"A{rn()}:{chr(64+pad_n)}{rn()}", {
        "backgroundColor": DARK,
        "textFormat": {"bold": True, "fontSize": 16, "foregroundColor": GOLD_TEXT},
        "horizontalAlignment": "CENTER"}))

    rows.append(pad([""]))

    # ── TEAMMATE WIN RATE MATRIX ──
    rows.append(pad(["TEAMMATE WIN RATE (when on same team)"]))
    fmts.append((f"A{rn()}:{chr(64+pad_n)}{rn()}", {
        "backgroundColor": SECTION,
        "textFormat": {"bold": True, "fontSize": 13, "foregroundColor": GOLD_TEXT},
        "horizontalAlignment": "CENTER"}))

    # Header row with player names
    header = [""] + active
    rows.append(pad(header))
    fmts.append((f"A{rn()}:{chr(64+n+1)}{rn()}", {
        "backgroundColor": HEADER,
        "textFormat": {"bold": True, "fontSize": 9, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    for a in active:
        row_data = [a]
        for b in active:
            if a == b:
                row_data.append("-")
            else:
                d = h2h.get(a, {}).get(b, {"same_team": 0, "same_wins": 0})
                if d["same_team"] > 0:
                    wr = round(d["same_wins"] / d["same_team"] * 100)
                    row_data.append(f"{wr}% ({d['same_team']})")
                else:
                    row_data.append("-")
        rows.append(pad(row_data))
        fmts.append((f"A{rn()}:{chr(64+n+1)}{rn()}", {
            "backgroundColor": L_BLUE,
            "textFormat": {"fontSize": 10},
            "horizontalAlignment": "CENTER"}))
        fmts.append((f"A{rn()}", {
            "backgroundColor": HEADER,
            "textFormat": {"bold": True, "fontSize": 9, "foregroundColor": WHITE}}))

    rows.append(pad([""]))
    rows.append(pad([""]))

    # ── VS WIN RATE MATRIX ──
    rows.append(pad(["HEAD-TO-HEAD (when on opposing teams — row player's WR vs column player)"]))
    fmts.append((f"A{rn()}:{chr(64+pad_n)}{rn()}", {
        "backgroundColor": SECTION,
        "textFormat": {"bold": True, "fontSize": 13, "foregroundColor": GOLD_TEXT},
        "horizontalAlignment": "CENTER"}))

    rows.append(pad(header))
    fmts.append((f"A{rn()}:{chr(64+n+1)}{rn()}", {
        "backgroundColor": HEADER,
        "textFormat": {"bold": True, "fontSize": 9, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    for a in active:
        row_data = [a]
        for b in active:
            if a == b:
                row_data.append("-")
            else:
                d = h2h.get(a, {}).get(b, {"vs": 0, "vs_wins": 0})
                if d["vs"] > 0:
                    wr = round(d["vs_wins"] / d["vs"] * 100)
                    row_data.append(f"{wr}% ({d['vs']})")
                else:
                    row_data.append("-")
        rows.append(pad(row_data))
        fmts.append((f"A{rn()}:{chr(64+n+1)}{rn()}", {
            "backgroundColor": L_BLUE,
            "textFormat": {"fontSize": 10},
            "horizontalAlignment": "CENTER"}))
        fmts.append((f"A{rn()}", {
            "backgroundColor": HEADER,
            "textFormat": {"bold": True, "fontSize": 9, "foregroundColor": WHITE}}))

    # Write
    sheets_retry(ws.update, values=rows, range_name="A1")

    # Column widths
    reqs = [{"updateDimensionProperties": {
        "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                  "startIndex": 0, "endIndex": 1},
        "properties": {"pixelSize": 100}, "fields": "pixelSize"}}]
    for ci in range(1, n + 1):
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                      "startIndex": ci, "endIndex": ci + 1},
            "properties": {"pixelSize": 85}, "fields": "pixelSize"}})
    reqs.append({"updateDimensionProperties": {
        "range": {"sheetId": ws.id, "dimension": "ROWS",
                  "startIndex": 0, "endIndex": 1},
        "properties": {"pixelSize": 45}, "fields": "pixelSize"}})
    sheets_retry(spreadsheet.batch_update, {"requests": reqs})

    for i in range(0, len(fmts), 15):
        batch = [{"range": r, "format": f} for r, f in fmts[i:i+15]]
        sheets_retry(ws.batch_format, batch)

    print("  In-House Head-to-Head matrix written")


# ── Main ──────────────────────────────────────────────────────
