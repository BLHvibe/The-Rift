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
# Phase E (sheet decommission): gspread imports are optional now.
try:
    import gspread  # noqa: F401
    from google.oauth2.service_account import Credentials  # noqa: F401
except Exception:
    gspread = None        # type: ignore
    Credentials = None    # type: ignore

from .constants import *
from .sheets import get_or_create_sheet, fmt_title, fmt_header, sheets_retry
from .scoring import compute_score, rank_to_chart_value


# ── Rank writers + readers ─────────────────────────────────

def write_rank_data(spreadsheet, results, timestamp):
    ws = get_or_create_sheet(spreadsheet, "Rank Data", rows=30, cols=12)
    title = ["LEAGUE OF LEGENDS RANK DATA"] + [""]*11
    header = ["#", "Player Name", "Rank", "Division", "LP", "Wins", "Losses",
              "Rank Score", "Normalized (0-100)", "Win Rate %", "Games Played",
              "Last Updated"]
    rows = [title, header]
    for r in results:
        games = r["wins"] + r["losses"]
        wr = round(r["wins"] / games * 100, 1) if games > 0 else 0
        rows.append([r["row"], r["name"], r["tier"], r["division"],
                     r["lp"], r["wins"], r["losses"], r["score"],
                     r["normalized"], wr, games, timestamp])
    ws.clear()
    sheets_retry(ws.update, range_name="A1", values=rows)
    fmt_title(ws, "L")
    fmt_header(ws, 2, "L")
    if len(rows) > 2:
        sheets_retry(ws.format, f"A3:L{len(rows)}", {"horizontalAlignment": "CENTER"})
    print("  Rank Data updated")


def write_player_stats(spreadsheet, results, champ_map):
    ws = get_or_create_sheet(spreadsheet, "Player Stats", rows=30, cols=16)
    title = ["PLAYER STATS - CHAMPIONS & RECENT PERFORMANCE"] + [""]*15
    header = ["#", "Player", "Win Rate %",
              "Top Champ 1", "Mastery 1", "Top Champ 2", "Mastery 2",
              "Top Champ 3", "Mastery 3",
              "Recent W-L", "Recent WR%", "Avg KDA", "Avg Kills",
              "Avg Deaths", "Avg Assists", "Hot/Cold"]
    rows = [title, header]
    for r in results:
        games = r["wins"] + r["losses"]
        wr = round(r["wins"] / games * 100, 1) if games > 0 else 0
        ch = r.get("top_champs", [])
        c1 = ch[0]["name"] if len(ch) > 0 else "-"
        m1 = f'{ch[0]["points"]:,}' if len(ch) > 0 else "-"
        c2 = ch[1]["name"] if len(ch) > 1 else "-"
        m2 = f'{ch[1]["points"]:,}' if len(ch) > 1 else "-"
        c3 = ch[2]["name"] if len(ch) > 2 else "-"
        m3 = f'{ch[2]["points"]:,}' if len(ch) > 2 else "-"
        matches = r.get("recent_matches", [])
        if matches:
            rw = sum(1 for m in matches if m["win"])
            rl = len(matches) - rw
            rwr = round(rw / len(matches) * 100, 1)
            ak = round(sum(m["kills"] for m in matches) / len(matches), 1)
            ad = round(sum(m["deaths"] for m in matches) / len(matches), 1)
            aa = round(sum(m["assists"] for m in matches) / len(matches), 1)
            kda = round((ak + aa) / max(ad, 1), 2)
            rwl = f"{rw}W-{rl}L"
            if rwr > wr + 10:
                hc = "HOT"
            elif rwr < wr - 10:
                hc = "COLD"
            else:
                hc = "Steady"
        else:
            rwl = rwr = kda = ak = ad = aa = "-"
            hc = "-"
        rows.append([r["row"], r["name"], wr, c1, m1, c2, m2, c3, m3,
                     rwl, rwr, kda, ak, ad, aa, hc])
    ws.clear()
    sheets_retry(ws.update, range_name="A1", values=rows)
    fmt_title(ws, "P")
    fmt_header(ws, 2, "P")
    if len(rows) > 2:
        sheets_retry(ws.format, f"A3:P{len(rows)}", {"horizontalAlignment": "CENTER"})
    print("  Player Stats updated")




def write_rank_history(spreadsheet, results, timestamp):
    """
    Chart-friendly layout:
    Row 1: Title
    Row 2: "Date/Time", Player1, Player2, ...  (header)
    Row 3+: one row of numeric rank values per run
    """
    ws = get_or_create_sheet(spreadsheet, "Rank History", rows=200, cols=50)
    existing = ws.get_all_values()
    result_map = {r["name"]: r for r in results}
    player_names = [r["name"] for r in results]
    num_players = len(results)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    ref_col = num_players + 3

    if not existing or len(existing) < 2:
        title = ["RANK HISTORY"] + [""] * num_players
        header = ["Date/Time"] + player_names
        data_row = [now_str]
        for r in results:
            data_row.append(rank_to_chart_value(r["tier"], r["division"]))

        all_rows = [title, header, data_row]
        ws.clear()
        sheets_retry(ws.update, range_name="A1", values=all_rows)
        fmt_title(ws, chr(64 + min(num_players + 1, 26)))

        ref_labels = [
            "Y-Axis Reference", "Rank = Value", "",
            "Challenger = 31", "Grandmaster = 30", "Master = 29",
            "Diamond I = 28", "Diamond IV = 25",
            "Emerald I = 24", "Emerald IV = 21",
            "Platinum I = 20", "Platinum IV = 17",
            "Gold I = 16", "Gold IV = 13",
            "Silver I = 12", "Silver IV = 9",
            "Bronze I = 8", "Bronze IV = 5",
            "Iron I = 4", "Iron IV = 1", "Unranked = 0",
        ]
        for i, label in enumerate(ref_labels):
            sheets_retry(ws.update_cell, i + 1, ref_col, label)

        print("  Rank History created (first snapshot)")
    else:
        next_row = len(existing) + 1
        header_names = existing[1][1:] if len(existing) > 1 else player_names

        data_row = [now_str]
        for name in header_names:
            r = result_map.get(name)
            if r:
                data_row.append(rank_to_chart_value(r["tier"], r["division"]))
            else:
                data_row.append("")

        sheets_retry(ws.update, range_name=f"A{next_row}", values=[data_row])

        data_points = next_row - 2
        print(f"  Rank History updated ({data_points} data points)")




# ── Scouting system ───────────────────────────────────────────


def get_final_rankings(spreadsheet):
    """Read Final Rankings sheet to get each player's position and score."""
    try:
        ws = spreadsheet.worksheet("Final Rankings")
        values = ws.get_all_values()
        rankings = {}
        for row in values[3:]:  # skip title, subtitle, header
            if len(row) >= 8 and row[0] and row[1]:
                try:
                    rankings[row[1].strip()] = {
                        "position": int(row[0]),
                        "score": float(row[6]) if row[6] else 0,
                        "rating": row[7] if len(row) > 7 else "?",
                        "tier_component": row[3] if len(row) > 3 else "?",
                        "rank_component": row[5] if len(row) > 5 else "?",
                    }
                except (ValueError, IndexError):
                    continue
        return rankings
    except Exception as e:
        print(f"  Could not read Final Rankings: {e}")
        return {}


