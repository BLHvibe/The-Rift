"""
League of Legends Power Rankings - Full Analytics Suite
========================================================
Fetches rank data, champion mastery, match history, and generates
analytics sheets including consensus, hot takes, bias reports,
and rank history tracking with chart data.

SETUP:
  pip install gspread google-auth requests

USAGE:
  python3 fetch_ranks_gsheets.py --key "RGAPI-xxxx" --sheet "URL_OR_NAME"

OPTIONS:
  --creds    Path to Google credentials JSON (default: credentials.json)
  --region   Platform routing (default: na1)
  --routing  Regional routing (default: americas)
  --skip-matches  Skip match history fetch (faster, fewer API calls)
"""

import argparse
import time
import random
import sys
import re
import json
from datetime import datetime, timezone
from collections import defaultdict
import math

import requests
import gspread
from google.oauth2.service_account import Credentials

# Optional engine import for shared synergy + counter data. The backend can run
# standalone (subprocess), so this falls back silently if package layout differs.
try:
    from data import draft_engine as _eng  # type: ignore
except Exception:
    try:
        import draft_engine as _eng  # type: ignore
    except Exception:
        _eng = None

DEFAULT_CREDS_FILE = "credentials.json"
DEFAULT_REGION = "na1"
DEFAULT_ROUTING = "americas"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

RANK_SCORES = {
    "Challenger": 10, "Grandmaster": 9.5, "Master": 9,
    "Diamond": 8, "Emerald": 6.25, "Platinum": 5.5,
    "Gold": 4.75, "Silver": 4, "Bronze": 3.25, "Iron": 2.5,
    # Unranked players are treated as Gold I (4.75) for scoring purposes
    # so they aren't unfairly penalized for not having placement games yet.
    "Unranked": 4.75,
}
DIV_OFFSETS = {"I": 0, "II": -0.25, "III": -0.5, "IV": -0.75}

RANK_CHART_VALUES = {
    "Iron IV": 1, "Iron III": 2, "Iron II": 3, "Iron I": 4,
    "Bronze IV": 5, "Bronze III": 6, "Bronze II": 7, "Bronze I": 8,
    "Silver IV": 9, "Silver III": 10, "Silver II": 11, "Silver I": 12,
    "Gold IV": 13, "Gold III": 14, "Gold II": 15, "Gold I": 16,
    "Platinum IV": 17, "Platinum III": 18, "Platinum II": 19, "Platinum I": 20,
    "Emerald IV": 21, "Emerald III": 22, "Emerald II": 23, "Emerald I": 24,
    "Diamond IV": 25, "Diamond III": 26, "Diamond II": 27, "Diamond I": 28,
    "Master": 29, "Grandmaster": 30, "Challenger": 31, "Unranked": 0,
}

TIER_TO_NUM = {"S": 6, "A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
NUM_TO_TIER = {6: "S", 5: "A", 4: "B", 3: "C", 2: "D", 1: "F"}


# ── Retry helper ──────────────────────────────────────────────

def sheets_retry(fn, *args, max_attempts=6, **kwargs):
    """Call fn(*args, **kwargs) with exponential backoff on quota/server errors."""
    for attempt in range(max_attempts):
        try:
            return fn(*args, **kwargs)
        except gspread.exceptions.APIError as e:
            status = getattr(e.response, "status_code", None)
            if status in (429, 500, 503) and attempt < max_attempts - 1:
                time.sleep((2 ** attempt) + random.uniform(0, 1))
            else:
                raise


# ── Google Sheets helpers ─────────────────────────────────────

def connect_to_sheet(creds_file, sheet_identifier):
    credentials = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
    gc = gspread.authorize(credentials)
    if "docs.google.com" in sheet_identifier:
        return gc.open_by_url(sheet_identifier)
    elif re.match(r'^[a-zA-Z0-9_-]{30,}$', sheet_identifier):
        return gc.open_by_key(sheet_identifier)
    else:
        return gc.open(sheet_identifier)


def get_or_create_sheet(spreadsheet, name, rows=100, cols=30):
    try:
        return spreadsheet.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        return sheets_retry(spreadsheet.add_worksheet, name, rows=rows, cols=cols)


def fmt_title(ws, end_col):
    sheets_retry(ws.format, f"A1:{end_col}1", {
        "backgroundColor": {"red": 0.11, "green": 0.11, "blue": 0.18},
        "textFormat": {"bold": True, "fontSize": 14,
                       "foregroundColor": {"red": 0.91, "green": 0.72, "blue": 0.29}},
        "horizontalAlignment": "CENTER",
    })


def fmt_header(ws, row, end_col):
    sheets_retry(ws.format, f"A{row}:{end_col}{row}", {
        "backgroundColor": {"red": 0.09, "green": 0.14, "blue": 0.28},
        "textFormat": {"bold": True,
                       "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
        "horizontalAlignment": "CENTER",
    })


# ── Riot API helpers ──────────────────────────────────────────

def riot_get(url, api_key, retries=3):
    for attempt in range(retries):
        resp = requests.get(url, headers={"X-Riot-Token": api_key})
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 5))
            print(f"    ... rate limited, waiting {wait}s")
            time.sleep(wait)
            continue
        if resp.status_code == 404:
            return None
        if attempt < retries - 1:
            time.sleep(2)
            continue
        print(f"    x API error {resp.status_code}: {resp.text[:120]}")
        return None
    return None


def compute_score(tier, division):
    base = RANK_SCORES.get(tier, 1)
    offset = DIV_OFFSETS.get(division, 0) if tier not in [
        "Challenger", "Grandmaster", "Master", "Unranked"] else 0
    return round(base + offset, 2)


def rank_to_chart_value(tier, division):
    if tier in ["Master", "Grandmaster", "Challenger", "Unranked"]:
        return RANK_CHART_VALUES.get(tier, 0)
    key = f"{tier} {division}" if division != "N/A" else tier
    return RANK_CHART_VALUES.get(key, 0)


# ── Data Dragon ───────────────────────────────────────────────

def load_champion_map():
    try:
        versions = requests.get(
            "https://ddragon.leagueoflegends.com/api/versions.json", timeout=10).json()
        latest = versions[0]
        url = f"https://ddragon.leagueoflegends.com/cdn/{latest}/data/en_US/champion.json"
        data = requests.get(url, timeout=10).json()
        champ_map = {}
        champ_tags = {}  # name -> [tags]
        for cname, cdata in data["data"].items():
            cid = int(cdata["key"])
            name = cdata["name"]
            champ_map[cid] = name
            champ_tags[name] = cdata.get("tags", [])
        print(f"  Loaded {len(champ_map)} champion names (patch {latest})")
        return champ_map, champ_tags
    except Exception as e:
        print(f"  Warning: could not load champion names: {e}")
        return {}, {}


# ── Fetch functions ───────────────────────────────────────────

def fetch_account(game_name, tag_line, routing, api_key):
    data = riot_get(
        f"https://{routing}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/"
        f"{game_name}/{tag_line}", api_key)
    return data.get("puuid") if data else None


def fetch_ranked(puuid, region, api_key):
    entries = riot_get(
        f"https://{region}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}",
        api_key)
    if not entries:
        return "Unranked", "N/A", 0, 0, 0
    if isinstance(entries, dict):
        entries = [entries]
    for entry in entries:
        if entry.get("queueType") == "RANKED_SOLO_5x5":
            tier = entry["tier"].capitalize()
            rank = entry.get("rank", "I")
            lp = entry.get("leaguePoints", 0)
            wins = entry.get("wins", 0)
            losses = entry.get("losses", 0)
            division = rank if tier not in [
                "Challenger", "Grandmaster", "Master"] else "N/A"
            return tier, division, lp, wins, losses
    return "Unranked", "N/A", 0, 0, 0


def fetch_top_champions(puuid, region, api_key, champ_map, count=3):
    data = riot_get(
        f"https://{region}.api.riotgames.com/lol/champion-mastery/v4/"
        f"champion-masteries/by-puuid/{puuid}/top?count={count}", api_key)
    if not data:
        return []
    champs = []
    for entry in data[:count]:
        cid = entry.get("championId", 0)
        champs.append({
            "name": champ_map.get(cid, f"Champ#{cid}"),
            "points": entry.get("championPoints", 0),
            "level": entry.get("championLevel", 0),
        })
    return champs


def fetch_recent_matches(puuid, routing, region, api_key, count=10):
    # Fetch extra to account for filtered-out ARAMs
    fetch_count = min(count * 3, 100)
    match_ids = riot_get(
        f"https://{routing}.api.riotgames.com/lol/match/v5/matches/"
        f"by-puuid/{puuid}/ids?count={fetch_count}", api_key)
    if not match_ids:
        return []
    # Valid queues: 400=Normal Draft, 420=Ranked Solo, 430=Blind, 490=Quickplay
    VALID_QUEUES = {400, 420, 430, 490}
    matches = []
    for mid in match_ids:
        if len(matches) >= count:
            break
        time.sleep(0.5)
        mdata = riot_get(
            f"https://{routing}.api.riotgames.com/lol/match/v5/matches/{mid}",
            api_key)
        if not mdata:
            continue
        info = mdata.get("info", {})
        queue_id = info.get("queueId", 0)
        if queue_id not in VALID_QUEUES:
            continue
        for p in info.get("participants", []):
            if p.get("puuid") == puuid:
                matches.append({
                    "win": p.get("win", False),
                    "kills": p.get("kills", 0),
                    "deaths": p.get("deaths", 0),
                    "assists": p.get("assists", 0),
                    "champion": p.get("championName", "?"),
                    "cs": p.get("totalMinionsKilled", 0) + p.get("neutralMinionsKilled", 0),
                    "damage": p.get("totalDamageDealtToChampions", 0),
                })
                break
    return matches


# ── Analytics ─────────────────────────────────────────────────

def compute_tier_analytics(tier_data, player_names, rater_names):
    num_raters = len(rater_names)
    num_players = len(player_names)

    # CONSENSUS & CONTROVERSY
    consensus = []
    for i in range(num_players):
        tiers = tier_data.get(i, [])
        nums = [TIER_TO_NUM.get(t, 0) for t in tiers if t in TIER_TO_NUM]
        if not nums:
            consensus.append({"name": player_names[i], "avg": 0, "std": 0,
                              "min": "-", "max": "-", "range": 0,
                              "avg_tier": "?"})
            continue
        avg = sum(nums) / len(nums)
        std = math.sqrt(sum((x - avg)**2 for x in nums) / len(nums))
        consensus.append({
            "name": player_names[i],
            "avg": round(avg, 2),
            "avg_tier": NUM_TO_TIER.get(round(avg), "?"),
            "std": round(std, 2),
            "min": NUM_TO_TIER.get(min(nums), "?"),
            "max": NUM_TO_TIER.get(max(nums), "?"),
            "range": max(nums) - min(nums),
        })

    # HOT TAKE DETECTOR
    hot_takes = []
    for i in range(num_players):
        tiers = tier_data.get(i, [])
        nums = [TIER_TO_NUM.get(t, 0) for t in tiers if t in TIER_TO_NUM]
        if not nums:
            continue
        avg = sum(nums) / len(nums)
        for j, t in enumerate(tiers):
            if j >= num_raters:
                break
            val = TIER_TO_NUM.get(t, 0)
            diff = val - avg
            if abs(diff) >= 1.5:
                hot_takes.append({
                    "rater": rater_names[j] if j < len(rater_names) else f"Rater {j+1}",
                    "player": player_names[i],
                    "rated": t,
                    "avg": NUM_TO_TIER.get(round(avg), "?"),
                    "diff": round(abs(diff), 1),
                    "direction": "higher" if diff > 0 else "lower",
                })
    hot_takes.sort(key=lambda x: x["diff"], reverse=True)

    # RATER BIAS
    rater_bias = []
    for j in range(num_raters):
        rater_tiers = []
        for i in range(num_players):
            tiers = tier_data.get(i, [])
            if j < len(tiers) and tiers[j] in TIER_TO_NUM:
                rater_tiers.append(TIER_TO_NUM[tiers[j]])
        if not rater_tiers:
            continue
        avg = sum(rater_tiers) / len(rater_tiers)
        std = math.sqrt(sum((x - avg)**2 for x in rater_tiers) / len(rater_tiers))
        rater_bias.append({
            "rater": rater_names[j] if j < len(rater_names) else f"Rater {j+1}",
            "avg": round(avg, 2),
            "avg_tier": NUM_TO_TIER.get(round(avg), "?"),
            "s_count": sum(1 for t in rater_tiers if t == 6),
            "f_count": sum(1 for t in rater_tiers if t == 1),
            "std": round(std, 2),
        })

    if rater_bias:
        overall = sum(r["avg"] for r in rater_bias) / len(rater_bias)
        for r in rater_bias:
            d = r["avg"] - overall
            r["diff_from_avg"] = round(d, 2)
            r["label"] = "Generous" if d > 0.3 else ("Harsh" if d < -0.3 else "Balanced")

    return consensus, hot_takes, rater_bias


# ── Sheet writers ─────────────────────────────────────────────

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


def write_consensus(spreadsheet, consensus_data):
    ws = get_or_create_sheet(spreadsheet, "Consensus & Controversy", rows=30, cols=9)
    title = ["CONSENSUS & CONTROVERSY"] + [""]*8
    header = ["#", "Player", "Avg Tier Score", "Avg Tier", "Std Deviation",
              "Lowest Rating", "Highest Rating", "Tier Spread", "Verdict"]
    rows = [title, header]
    sorted_data = sorted(consensus_data, key=lambda x: x["std"], reverse=True)
    for i, c in enumerate(sorted_data, 1):
        if c["std"] >= 1.5:
            verdict = "VERY Controversial"
        elif c["std"] >= 1.0:
            verdict = "Controversial"
        elif c["std"] >= 0.5:
            verdict = "Mixed"
        else:
            verdict = "Consensus"
        rows.append([i, c["name"], c["avg"], c.get("avg_tier", "?"),
                     c["std"], c["min"], c["max"], c["range"], verdict])
    ws.clear()
    sheets_retry(ws.update, range_name="A1", values=rows)
    fmt_title(ws, "I")
    fmt_header(ws, 2, "I")
    if len(rows) > 2:
        sheets_retry(ws.format, f"A3:I{len(rows)}", {"horizontalAlignment": "CENTER"})
    print("  Consensus & Controversy updated")


def write_hot_takes(spreadsheet, hot_takes):
    ws = get_or_create_sheet(spreadsheet, "Hot Take Detector", rows=100, cols=7)
    title = ["HOT TAKE DETECTOR"] + [""]*6
    subtitle = ["Ratings 1.5+ tiers away from group average"] + [""]*6
    header = ["#", "Rater", "Player", "Their Rating", "Group Average",
              "Tiers Off", "Direction"]
    rows = [title, subtitle, header]
    for i, ht in enumerate(hot_takes, 1):
        rows.append([i, ht["rater"], ht["player"], ht["rated"], ht["avg"],
                     ht["diff"], ht["direction"].upper()])
    if not hot_takes:
        rows.append(["", "No hot takes found - everyone agrees!", "", "", "", "", ""])
    ws.clear()
    sheets_retry(ws.update, range_name="A1", values=rows)
    fmt_title(ws, "G")
    sheets_retry(ws.format, "A2:G2", {
        "backgroundColor": {"red": 0.15, "green": 0.15, "blue": 0.25},
        "textFormat": {"italic": True,
                       "foregroundColor": {"red": 0.7, "green": 0.7, "blue": 0.7}},
        "horizontalAlignment": "CENTER",
    })
    fmt_header(ws, 3, "G")
    if len(rows) > 3:
        sheets_retry(ws.format, f"A4:G{len(rows)}", {"horizontalAlignment": "CENTER"})
    print(f"  Hot Take Detector updated ({len(hot_takes)} hot takes)")


def write_rater_bias(spreadsheet, rater_bias):
    ws = get_or_create_sheet(spreadsheet, "Rater Bias Report", rows=30, cols=9)
    title = ["RATER BIAS REPORT"] + [""]*8
    header = ["#", "Rater", "Avg Tier Score", "Avg Tier", "# S Ratings",
              "# F Ratings", "Spread (Std Dev)", "vs Group Avg", "Label"]
    rows = [title, header]
    sorted_bias = sorted(rater_bias, key=lambda x: x["avg"], reverse=True)
    for i, rb in enumerate(sorted_bias, 1):
        ds = f"+{rb['diff_from_avg']}" if rb["diff_from_avg"] > 0 else str(rb["diff_from_avg"])
        rows.append([i, rb["rater"], rb["avg"], rb["avg_tier"],
                     rb["s_count"], rb["f_count"], rb["std"], ds, rb["label"]])
    ws.clear()
    sheets_retry(ws.update, range_name="A1", values=rows)
    fmt_title(ws, "I")
    fmt_header(ws, 2, "I")
    if len(rows) > 2:
        sheets_retry(ws.format, f"A3:I{len(rows)}", {"horizontalAlignment": "CENTER"})
    print("  Rater Bias Report updated")


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

def fetch_scouting_matches(puuid, routing, region, api_key, count=100):
    """Fetch last N ranked/normal matches (skips ARAM, Arena, etc).

    Paginates the match-ID endpoint (max 100 IDs per call) so we can reach
    100+ valid games even if a player has many filtered-out ARAM/Arena games.
    """
    VALID_QUEUES = {400, 420, 430, 490}  # Normal Draft, Ranked Solo, Blind, Quickplay
    matches = []
    skipped = 0
    checked = 0
    start = 0
    BATCH = 100  # Riot API max IDs per call

    while len(matches) < count:
        match_ids = riot_get(
            f"https://{routing}.api.riotgames.com/lol/match/v5/matches/"
            f"by-puuid/{puuid}/ids?start={start}&count={BATCH}", api_key)
        if not match_ids:
            break

        for mid in match_ids:
            if len(matches) >= count:
                break
            time.sleep(0.5)
            mdata = riot_get(
                f"https://{routing}.api.riotgames.com/lol/match/v5/matches/{mid}",
                api_key)
            if not mdata:
                checked += 1
                continue
            info = mdata.get("info", {})
            queue_id = info.get("queueId", 0)
            checked += 1
            if queue_id not in VALID_QUEUES:
                skipped += 1
                continue
            for p in info.get("participants", []):
                if p.get("puuid") == puuid:
                    dur = info.get("gameDuration", 1) / 60
                    if dur < 0.1:
                        dur = 1
                    cs = p.get("totalMinionsKilled", 0) + p.get("neutralMinionsKilled", 0)
                    matches.append({
                        "win": p.get("win", False),
                        "champion": p.get("championName", "?"),
                        "kills": p.get("kills", 0),
                        "deaths": p.get("deaths", 0),
                        "assists": p.get("assists", 0),
                        "cs": cs,
                        "cs_min": round(cs / dur, 1),
                        "damage": p.get("totalDamageDealtToChampions", 0),
                        "vision": p.get("visionScore", 0),
                        "gold": p.get("goldEarned", 0),
                        "role": p.get("teamPosition", "UNKNOWN"),
                        "duration_min": round(dur, 1),
                        "first_blood": p.get("firstBloodKill", False),
                    })
                    break
            if checked % 10 == 0:
                print(f"      {len(matches)} valid / {checked} checked (skipped {skipped} ARAM/other)")

        # Stop if the API returned fewer IDs than requested (no more history)
        if len(match_ids) < BATCH:
            break
        start += BATCH

    if skipped:
        print(f"      Filtered out {skipped} non-standard games (ARAM, Arena, etc)")
    return matches


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

    ws = sheets_retry(spreadsheet.add_worksheet, sheet_name, rows=120, cols=12)

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


# ── Champion archetype database ───────────────────────────────

COMP_ARCHETYPES = {
    "Teamfight": {
        "description": "Group and win 5v5s with AoE and engage",
        "needs": {"engage": 1, "aoe_damage": 2, "frontline": 1},
        "ideal_tags": {"Tank", "Mage"},
    },
    "Pick": {
        "description": "Catch enemies with CC and burst them 1-by-1",
        "needs": {"assassin_or_burst": 2, "cc": 2},
        "ideal_tags": {"Assassin", "Mage"},
    },
    "Split Push": {
        "description": "1-3-1 or 1-4 with strong duelists in side lanes",
        "needs": {"duelist": 1, "waveclear": 1},
        "ideal_tags": {"Fighter"},
    },
    "Poke / Siege": {
        "description": "Chunk enemies before fights with long-range abilities",
        "needs": {"long_range": 2, "disengage": 1},
        "ideal_tags": {"Mage", "Marksman"},
    },
    "Protect the Carry": {
        "description": "Peel and buff your strongest damage dealer",
        "needs": {"hypercarry": 1, "peel": 2},
        "ideal_tags": {"Support", "Marksman"},
    },
    "Dive": {
        "description": "Hard engage onto backline, collapse and delete carries",
        "needs": {"engage": 2, "assassin_or_burst": 1, "frontline": 1},
        "ideal_tags": {"Tank", "Assassin", "Fighter"},
    },
    "Scaling": {
        "description": "Play safe early, outscale with late-game champions",
        "needs": {"hypercarry": 1, "waveclear": 1, "disengage": 1},
        "ideal_tags": {"Mage", "Marksman"},
    },
}

ARCHETYPE_CONFLICTS = {
    "Dive": ["hypercarry", "disengage"],        # hypercarry/peel in dive = bad
    "Teamfight": ["disengage", "duelist"],       # selfish fighters in TF = bad
    "Poke / Siege": ["engage", "assassin_or_burst"],  # dive in poke = contradictory
    "Protect the Carry": ["assassin_or_burst"],  # assassins in protect = bad
    "Split Push": ["engage", "aoe_damage"],      # AoE teamfight in split = bad
}

CHAMP_SUBCLASSES = {
    "engage": {"Malphite","Amumu","Leona","Nautilus","Rakan","Rell","Alistar",
               "Jarvan IV","Sejuani","Maokai","Ornn","Zac","Sion","Gragas",
               "Wukong","Diana","Galio","Skarner","Yone","Kennen","Hecarim",
               "Vi","Camille","Kled","Nocturne","Rek'Sai","Pantheon",
               "Ambessa","Aurora"},
    "aoe_damage": {"Orianna","Miss Fortune","Kennen","Rumble","Diana","Yone",
                   "Yasuo","Gangplank","Samira","Karthus","Brand","Zyra",
                   "Viktor","Cassiopeia","Nilah","Fiddlesticks","Aurora","Katarina",
                   "Vladimir","Lissandra","Wukong","Galio","Lillia","Briar",
                   "Vex","Hwei","Ziggs","Seraphine","Twitch","Jinx"},
    "frontline": {"Malphite","Maokai","Ornn","Sion","Cho'Gath","Dr. Mundo",
                  "Tahm Kench","Shen","Braum","Taric","Alistar","Leona",
                  "Nautilus","Rell","Sejuani","Amumu","Rammus","Zac",
                  "Poppy","Skarner","K'Sante","Gragas","Volibear","Darius",
                  "Garen","Sett","Mordekaiser","Illaoi","Urgot","Aatrox","Ambessa"},
    "assassin_or_burst": {"Zed","Talon","Qiyana","Akali","LeBlanc","Fizz",
                          "Katarina","Ekko","Kha'Zix","Rengar","Evelynn",
                          "Shaco","Naafiri","Pyke","Syndra","Ahri","Veigar",
                          "Annie","Lux","Neeko","Zoe","Vex","Aurora",
                          "Nocturne","Diana","Briar","Lee Sin",
                          "Ambessa","Mel"},
    "cc": {"Thresh","Morgana","Lux","Ahri","Ashe","Jhin","Veigar","Neeko",
           "Twisted Fate","Blitzcrank","Pyke","Elise","Lee Sin","Hwei",
           "Sejuani","Amumu","Leona","Nautilus","Maokai","Zyra","Bard",
           "Renata Glasc","Rakan","Rell","Skarner"},
    "duelist": {"Fiora","Tryndamere","Jax","Camille","Gwen","Irelia","Riven",
                "Yasuo","Yone","Mordekaiser","Nasus","Yorick","Trundle",
                "Volibear","Udyr","Kayle","Sett","Gnar","Ambessa","Warwick",
                "Shen","Illaoi","Olaf","Renekton","Kled"},
    "waveclear": {"Anivia","Ryze","Malzahar","Viktor","Ziggs","Sivir",
                  "Jinx","Orianna","Xerath","Taliyah","Aurelion Sol","Hwei",
                  "Twisted Fate","Corki","Heimerdinger","Seraphine","Veigar",
                  "Cassiopeia","Vladimir","Azir","Mel","Smolder"},
    "long_range": {"Xerath","Vel'Koz","Lux","Ziggs","Jayce","Ezreal","Varus",
                   "Kog'Maw","Nidalee","Zoe","Hwei","Caitlyn","Senna",
                   "Seraphine","Karma","Viktor","Corki","Jhin","Ashe"},
    "disengage": {"Janna","Gragas","Poppy","Alistar","Thresh","Braum",
                  "Karma","Lulu","Zilean","Anivia","Taliyah","Azir",
                  "Nami","Milio","Soraka"},
    "hypercarry": {"Kog'Maw","Jinx","Twitch","Aphelios","Vayne","Kayle",
                   "Kindred","Smolder","Veigar","Cassiopeia","Karthus",
                   "Azir","Viktor","Tristana","Xayah","Zeri","Kai'Sa",
                   "Draven","Nilah","Master Yi"},
    "peel": {"Lulu","Janna","Karma","Nami","Soraka","Yuumi","Milio",
             "Renata Glasc","Taric","Zilean","Ivern","Braum","Shen",
             "Orianna","Seraphine","Sona","Bard"},
}


ROLE_VALID = {
    "Top": {"Aatrox","Ambessa","Aurora","Camille","Cho'Gath","Darius","Dr. Mundo",
            "Fiora","Gangplank","Garen","Gnar","Gwen","Illaoi","Irelia","Jax",
            "Jayce","K'Sante","Kayle","Kennen","Kled","Malphite","Maokai",
            "Mordekaiser","Nasus","Olaf","Ornn","Pantheon","Poppy","Quinn",
            "Renekton","Rengar","Riven","Rumble","Sett","Shen","Singed",
            "Sion","Tahm Kench","Teemo","Trundle","Tryndamere","Urgot",
            "Vladimir","Volibear","Wukong","Yasuo","Yone","Yorick","Gragas",
            "Heimerdinger","Akali","Sylas","Warwick","Zac"},
    "Jungle": {"Amumu","Ambessa","Bel'Veth","Briar","Diana","Ekko","Elise","Evelynn",
               "Fiddlesticks","Gragas","Graves","Hecarim","Ivern","Jarvan IV",
               "Karthus","Kayn","Kha'Zix","Kindred","Lee Sin","Lillia",
               "Master Yi","Nidalee","Nocturne","Nunu","Pantheon","Poppy",
               "Rammus","Rek'Sai","Rengar","Sejuani","Shaco","Shyvana",
               "Skarner","Taliyah","Udyr","Vi","Viego","Volibear","Warwick",
               "Wukong","Xin Zhao","Zac","Maokai","Trundle","Sylas"},
    "Mid": {"Ahri","Akali","Akshan","Anivia","Annie","Aurelion Sol","Azir",
            "Cassiopeia","Corki","Diana","Ekko","Fizz","Galio","Hwei",
            "Irelia","Kassadin","Katarina","LeBlanc","Lissandra","Lux",
            "Malzahar","Mel","Naafiri","Neeko","Orianna","Pantheon","Qiyana",
            "Ryze","Sylas","Syndra","Taliyah","Talon","Tristana","Twisted Fate",
            "Veigar","Vex","Viktor","Vladimir","Xerath","Yasuo","Yone",
            "Zed","Zoe","Ziggs","Aurora","Jayce","Rumble","Heimerdinger","Zyra"},
    "Bot": {"Aphelios","Ashe","Caitlyn","Corki","Draven","Ezreal","Jhin",
            "Jinx","Kai'Sa","Kalista","Kog'Maw","Lucian","Miss Fortune",
            "Nilah","Samira","Sivir","Smolder","Tristana","Twitch","Varus",
            "Vayne","Xayah","Zeri","Ziggs","Senna"},
    "Support": {"Alistar","Bard","Blitzcrank","Braum","Janna","Karma","Leona",
                "Lulu","Lux","Mel","Milio","Morgana","Nami","Nautilus","Pyke",
                "Rakan","Rell","Renata Glasc","Senna","Seraphine","Sona",
                "Soraka","Taric","Thresh","Yuumi","Zilean","Zyra","Xerath",
                "Vel'Koz","Maokai","Poppy","Tahm Kench","Galio"},
}


def score_champ_for_archetype(champ_name, archetype, champ_tags_data):
    """Score how well a champion fits an archetype (0-1).

    Positive score from subclass needs + tag overlap; penalty when champion
    subclass conflicts with the archetype's style.
    """
    arch = COMP_ARCHETYPES[archetype]
    total_needs = sum(arch["needs"].values())
    matches = sum(1 for need in arch["needs"]
                  if champ_name in CHAMP_SUBCLASSES.get(need, set()))

    # Tag match bonus
    tags = set(champ_tags_data.get(champ_name, []))
    ideal = arch.get("ideal_tags", set())
    tag_overlap = len(tags & ideal)

    score = (matches / max(total_needs, 1)) * 0.7 + (tag_overlap / max(len(ideal), 1)) * 0.3

    # Conflict penalty: subclasses that contradict this archetype subtract 0.2
    conflicts = ARCHETYPE_CONFLICTS.get(archetype, [])
    for conflict_class in conflicts:
        if champ_name in CHAMP_SUBCLASSES.get(conflict_class, set()):
            score -= 0.2
            break  # only penalize once even if multiple conflicts

    return max(score, 0.0)


def score_team_synergy(picks, champ_tags_data):
    """Score overall team synergy (0-100)."""
    champ_names = [p["champion"].replace(" (off-meta)", "") for p in picks if p["champion"] != "?"]
    if len(champ_names) < 3:
        return 0

    score = 0

    # 1. Damage type balance (AD/AP mix) — 25 points
    ad_count = 0
    ap_count = 0
    for c in champ_names:
        tags = champ_tags_data.get(c, [])
        if "Marksman" in tags or "Fighter" in tags or "Assassin" in tags:
            ad_count += 1
        if "Mage" in tags:
            ap_count += 1
    if ad_count >= 2 and ap_count >= 1:
        score += 25
    elif ad_count >= 1 and ap_count >= 1:
        score += 15
    else:
        score += 5

    # 2. Frontline presence — 25 points
    frontline = sum(1 for c in champ_names if c in CHAMP_SUBCLASSES.get("frontline", set()))
    if frontline >= 2:
        score += 25
    elif frontline == 1:
        score += 15
    else:
        score += 0

    # 3. CC count — 25 points
    cc = sum(1 for c in champ_names if c in CHAMP_SUBCLASSES.get("cc", set())
             or c in CHAMP_SUBCLASSES.get("engage", set()))
    if cc >= 3:
        score += 25
    elif cc >= 2:
        score += 18
    elif cc >= 1:
        score += 10

    # 4. Win condition clarity — 25 points
    has_carry = any(c in CHAMP_SUBCLASSES.get("hypercarry", set())
                    or c in CHAMP_SUBCLASSES.get("assassin_or_burst", set())
                    or c in CHAMP_SUBCLASSES.get("duelist", set())
                    for c in champ_names)
    has_peel = any(c in CHAMP_SUBCLASSES.get("peel", set())
                   or c in CHAMP_SUBCLASSES.get("engage", set())
                   for c in champ_names)
    if has_carry and has_peel:
        score += 25
    elif has_carry:
        score += 15
    else:
        score += 5

    # 5. Engine-based pair synergy + anti-synergy bonus (up to ±20)
    if _eng is not None and champ_names:
        try:
            raw = _eng.synergy_score(champ_names)   # typical range -0.5..+2.0
            score += max(-15, min(20, raw * 12))
        except Exception:
            pass

    return score


def _engine_counter_bonus(your_picks, enemy_picks):
    """Engine-derived counter coverage bonus for a comp vs locked enemy picks.
    Returns a 0..15 point bump representing how well our team counters enemies.
    """
    if _eng is None or not enemy_picks or not your_picks:
        return 0
    try:
        total = 0.0
        for ep in enemy_picks:
            total += _eng.team_counter_coverage(your_picks, ep)
        avg = total / max(len(enemy_picks), 1)
        return min(15, avg * 30)
    except Exception:
        return 0


def compute_ban_recommendations(team_players, all_scouting, rankings):
    """Compute ban recommendations. Requires 5+ games to be ban-worthy.

    Improvements over v1:
    - Off-role champions penalized 0.4x (player won't play them this game)
    - Role specialists boosted 1.3x (existing behaviour kept)
    - must-ban champions guaranteed to appear in phases 1-3
    """
    ban_candidates = []
    for player_name, role in team_players:
        scout = all_scouting.get(player_name)
        rank_info = rankings.get(player_name, {})
        player_rank = rank_info.get("position", 15)
        rank_weight = max(0.5, 2.0 - (player_rank - 1) * 0.06)
        if not scout: continue

        role_valid = ROLE_VALID.get(role, set())
        role_champs = scout.get("role_champs_flat", {})
        player_role_champs = role_champs.get(role, set()) if role else set()

        for champ in scout.get("champ_list", []):
            games = champ["games"]; wr = champ["wr"]
            if games < 5: continue
            kda_factor = min(champ["kda"] / 3, 1.5)
            base_threat = (wr / 100) * math.sqrt(games) * kda_factor

            # Role-aware modifiers: if we know what the player plays in this role,
            # skip any champion they don't actually play there
            if player_role_champs:
                if champ["name"] not in player_role_champs:
                    continue
                role_boost = 1.3  # filtered to role champs — all are specialists
            else:
                is_role_specialist = role and champ["name"] in role_champs.get(role, set())
                is_in_role_valid   = not role_valid or champ["name"] in role_valid
                role_boost = 1.3 if is_role_specialist else (0.4 if (role and not is_in_role_valid) else 1.0)

            is_must_ban = any(mb["name"] == champ["name"] for mb in scout.get("must_bans", []))
            must_ban_boost = 1.5 if is_must_ban else 1.0

            priority = base_threat * rank_weight * role_boost * must_ban_boost
            ban_candidates.append({
                "champion": champ["name"], "player": player_name,
                "role": role, "games": games, "wr": wr,
                "kda": champ["kda"], "priority": round(priority, 2),
                "player_rank": player_rank,
                "is_must_ban": is_must_ban})

    # Sort: must-bans first within their priority tier, then by priority
    ban_candidates.sort(key=lambda x: (x["is_must_ban"], x["priority"]), reverse=True)
    seen = set(); final = []
    for b in ban_candidates:
        if b["champion"] not in seen:
            seen.add(b["champion"]); final.append(b)
        if len(final) >= 10: break

    # Assign phase labels for display
    for i, ban in enumerate(final):
        if i < 3:
            ban["phase"] = 1
            if ban["is_must_ban"]:
                ban["phase_reason"] = "Must ban — dominant in assigned role"
            elif ban["wr"] >= 65:
                ban["phase_reason"] = f"High WR threat ({ban['wr']:.0f}% WR)"
            elif ban["kda"] >= 4:
                ban["phase_reason"] = f"High KDA threat ({ban['kda']:.1f} KDA)"
            else:
                ban["phase_reason"] = "High threat flexible pick"
        elif i < 7:
            ban["phase"] = 2
            if ban["wr"] >= 60:
                ban["phase_reason"] = f"Counter-pick threat ({ban['wr']:.0f}% WR)"
            else:
                ban["phase_reason"] = "Phase 2 — likely counter-pick"
        else:
            ban["phase"] = 3
            ban["phase_reason"] = "Comfort pick — monitor this player"

    return final


def compute_comp_suggestions(team_players, all_scouting, rankings,
                             champ_tags_data=None, inhouse_db=None,
                             enemy_team_players=None, enemy_scouting=None):
    """Smart comp engine. Balances player comfort (33%), archetype fit (33%), win condition (33%).

    Improvements over v1:
    - Uses module-level ROLE_VALID (shared with ban engine)
    - Role specialist comfort boost (1.25x) for champions played in assigned role
    - Scaled in-house boost based on games + WR
    - In-house-only champions included as synthetic candidates
    - Enemy context: counter_potential score added per archetype
    - inhouse_db: dict from load_inhouse_db(), keyed by player name
    - enemy_team_players: list of (name, role) for the opposing team
    - enemy_scouting: all_scouting dict (used to evaluate enemy champ pools)
    """
    if champ_tags_data is None:
        champ_tags_data = {}
    if inhouse_db is None:
        inhouse_db = {}
    if enemy_scouting is None:
        enemy_scouting = all_scouting

    # Pre-compute enemy tendencies for counter scoring
    enemy_squishy_count = 0
    enemy_diver_count = 0
    enemy_frontline_count = 0
    if enemy_team_players:
        squishy_subs   = (CHAMP_SUBCLASSES.get("assassin_or_burst", set()) |
                          CHAMP_SUBCLASSES.get("hypercarry", set()) |
                          CHAMP_SUBCLASSES.get("long_range", set()))
        diver_subs     = (CHAMP_SUBCLASSES.get("engage", set()) |
                          CHAMP_SUBCLASSES.get("assassin_or_burst", set()))
        frontline_subs = CHAMP_SUBCLASSES.get("frontline", set())
        for e_name, _e_role in enemy_team_players:
            e_scout = enemy_scouting.get(e_name)
            if not e_scout:
                continue
            # Check top 5 champs (was top 3) for better coverage
            top_champs = [c["name"] for c in e_scout.get("champ_list", [])[:5]]
            if any(c in squishy_subs for c in top_champs):
                enemy_squishy_count += 1
            if any(c in diver_subs for c in top_champs):
                enemy_diver_count += 1
            if any(c in frontline_subs for c in top_champs):
                enemy_frontline_count += 1

    suggestions = {}

    for archetype, arch_data in COMP_ARCHETYPES.items():
        used_champs = set()

        # Sort players: best ranked first so they get priority
        ranked_players = []
        for player_name, role in team_players:
            rank_info = rankings.get(player_name, {})
            ranked_players.append((player_name, role, rank_info.get("position", 99)))
        ranked_players.sort(key=lambda x: x[2])

        arch_picks = []

        for player_name, role, player_rank in ranked_players:
            scout = all_scouting.get(player_name)
            if not scout:
                arch_picks.append({
                    "player": player_name, "role": role,
                    "champion": "?", "games": 0, "wr": 0, "kda": 0,
                    "fit": "No data", "comp_score": 0})
                continue

            valid_for_role = ROLE_VALID.get(role, set())

            # Score each candidate champion
            candidates = []
            for champ in scout.get("champ_list", []):
                cname = champ["name"]
                if cname in used_champs:
                    continue
                if valid_for_role and cname not in valid_for_role:
                    continue

                # --- COMFORT SCORE (33%) ---
                # Role specialist boost: player plays this champ in their assigned role
                role_spec = scout.get("role_champs_flat", {})
                role_spec_boost = 1.25 if (role and cname in role_spec.get(role, set())) else 1.0

                # Scaled inhouse boost: more games + higher WR = stronger boost
                ih = inhouse_db.get(player_name)
                inhouse_boost = 1.0
                if ih:
                    ih_champ = next((c for c in ih.get("champs", []) if c.get("name") == cname), None)
                    if ih_champ:
                        ih_games = ih_champ.get("games", 0)
                        ih_wr = ih_champ.get("wr", 0)
                        if ih_games >= 5 and ih_wr >= 60:
                            inhouse_boost = 2.5
                        elif ih_games >= 3:
                            inhouse_boost = 1.8
                        else:
                            inhouse_boost = 1.5

                comfort = min((champ["wr"] / 100) * math.log(champ["games"] + 1) *
                             min(champ["kda"] / 2.5, 1.5), 3.0) / 3.0
                comfort = min(comfort * role_spec_boost * inhouse_boost, 1.0)

                # --- ARCHETYPE FIT SCORE (33%) ---
                arch_fit = score_champ_for_archetype(cname, archetype, champ_tags_data)

                # --- WIN CONDITION SCORE (33%) ---
                # Best players should be on carries
                is_carry = (cname in CHAMP_SUBCLASSES.get("hypercarry", set()) or
                           cname in CHAMP_SUBCLASSES.get("assassin_or_burst", set()) or
                           cname in CHAMP_SUBCLASSES.get("duelist", set()))
                is_top_player = player_rank <= 5
                if is_carry and is_top_player:
                    win_cond = 1.0
                elif is_carry:
                    win_cond = 0.7
                elif not is_carry and not is_top_player:
                    win_cond = 0.6  # utility on weaker player is fine
                else:
                    win_cond = 0.4

                total = (comfort * 0.33 + arch_fit * 0.33 + win_cond * 0.33)
                candidates.append((champ, total, arch_fit))

            # Include in-house-only champions not in ranked data
            ih = inhouse_db.get(player_name)
            if ih and ih.get("champs"):
                ih_names_in_candidates = {c[0]["name"] for c in candidates if c}
                for ih_champ in ih["champs"]:
                    cname = ih_champ.get("name", "")
                    if cname in used_champs or cname in ih_names_in_candidates:
                        continue
                    if valid_for_role and cname not in valid_for_role:
                        continue
                    # Create a synthetic champ entry from in-house data
                    synth = {"name": cname, "games": ih_champ.get("games", 0),
                             "wr": ih_champ.get("wr", 50), "kda": ih_champ.get("kda", 2.0)}
                    # Apply strong inhouse boost since this is custom-only
                    inhouse_boost_synth = 2.0 if ih_champ.get("games", 0) >= 3 else 1.5
                    comfort = min((synth["wr"] / 100) * math.log(synth["games"] + 1) *
                                 min(synth["kda"] / 2.5, 1.5), 3.0) / 3.0 * inhouse_boost_synth
                    comfort = min(comfort, 1.0)
                    arch_fit = score_champ_for_archetype(cname, archetype, champ_tags_data)
                    # Use conservative win condition since no ranked data
                    win_cond = 0.5
                    total = (comfort * 0.33 + arch_fit * 0.33 + win_cond * 0.33)
                    candidates.append((synth, total, arch_fit))

            candidates.sort(key=lambda x: x[1], reverse=True)

            if candidates:
                best_champ, best_score, best_fit = candidates[0]
                used_champs.add(best_champ["name"])
                fit = ("MAIN" if best_champ["games"] >= 5 else
                       "Comfort" if best_champ["games"] >= 3 else
                       "Playable" if best_fit > 0.3 else "Off-meta")
                arch_picks.append({
                    "player": player_name, "role": role,
                    "champion": best_champ["name"] if best_fit > 0.1 else f"{best_champ['name']} (off-meta)",
                    "games": best_champ["games"],
                    "wr": best_champ["wr"],
                    "kda": best_champ["kda"],
                    "fit": fit,
                    "comp_score": round(best_score, 2),
                })
            else:
                arch_picks.append({
                    "player": player_name, "role": role,
                    "champion": "?", "games": 0, "wr": 0, "kda": 0,
                    "fit": "No data", "comp_score": 0})

        # Sort by role for display
        role_order = {"Top": 0, "Jungle": 1, "Mid": 2, "Bot": 3, "Support": 4}
        arch_picks.sort(key=lambda x: role_order.get(x["role"], 5))

        # Score team synergy
        synergy = score_team_synergy(arch_picks, champ_tags_data)
        on_meta = sum(1 for p in arch_picks
                      if "off-meta" not in str(p.get("champion", ""))
                      and p["fit"] != "No data")
        avg_comfort = sum(p.get("comp_score", 0) for p in arch_picks) / max(len(arch_picks), 1)

        # Combined viability score
        combined = synergy * 0.5 + avg_comfort * 50 * 0.3 + on_meta * 10 * 0.2

        # Counter potential: bonus score when this comp counters the enemy
        counter_bonus = 0.0
        if enemy_team_players:
            pick_names = [p["champion"].replace(" (off-meta)", "") for p in arch_picks
                          if p["champion"] != "?"]
            engage_subs = CHAMP_SUBCLASSES.get("engage", set())
            frontline_subs = CHAMP_SUBCLASSES.get("frontline", set())
            long_range_subs = CHAMP_SUBCLASSES.get("long_range", set())
            poke_subs = CHAMP_SUBCLASSES.get("long_range", set()) | \
                        CHAMP_SUBCLASSES.get("waveclear", set())
            if enemy_squishy_count >= 2:
                counter_bonus += sum(0.12 for c in pick_names if c in engage_subs)
                counter_bonus += sum(0.10 for c in pick_names
                                     if c in CHAMP_SUBCLASSES.get("cc", set()))
            if enemy_diver_count >= 2:
                counter_bonus += sum(0.12 for c in pick_names if c in frontline_subs)
                counter_bonus += sum(0.08 for c in pick_names if c in poke_subs)
            if enemy_frontline_count >= 2:
                counter_bonus += sum(0.12 for c in pick_names
                                     if c in long_range_subs or c in poke_subs)
        counter_potential = min(int(counter_bonus * 100), 100)

        # Engine-derived enhancements: pair-level counter coverage + win condition.
        pick_names = [p["champion"].replace(" (off-meta)", "") for p in arch_picks
                      if p["champion"] != "?"]
        enemy_pick_names = []
        if enemy_team_players and enemy_scouting:
            for (en_name, _en_role) in enemy_team_players:
                en_scout = enemy_scouting.get(en_name, {}) if isinstance(enemy_scouting, dict) else {}
                for tc in (en_scout.get("top_champs") or [])[:3]:
                    if tc:
                        enemy_pick_names.append(tc)
        eng_counter_pts = _engine_counter_bonus(pick_names, enemy_pick_names)
        combined += eng_counter_pts          # 0..15 bump
        counter_potential = min(100, counter_potential + int(eng_counter_pts * 4))

        # Win-condition / spike (engine archetype data, falls back to description)
        eng_arch = (_eng.ARCHETYPES.get(archetype, {}) if _eng is not None else {})
        win_condition = eng_arch.get("win_condition", arch_data.get("description", ""))
        spike = eng_arch.get("spike", "")

        suggestions[archetype] = {
            "description": arch_data["description"],
            "picks": arch_picks,
            "synergy": synergy,
            "on_meta_count": on_meta,
            "combined_score": round(combined, 1),
            "counter_potential": counter_potential,
            "win_condition": win_condition,
            "spike": spike,
            "viability": ("STRONG" if combined >= 35 else
                          "VIABLE" if combined >= 25 else
                          "WEAK" if combined >= 15 else "NOT RECOMMENDED"),
        }

    # ── Filter out comps with 3+ off-meta picks (they don't represent the archetype) ──
    to_remove = []
    for archetype, comp in suggestions.items():
        off_meta_count = sum(1 for p in comp["picks"]
                            if "off-meta" in str(p.get("champion", ""))
                            or p["fit"] == "Off-meta"
                            or p["fit"] == "No data")
        if off_meta_count >= 3:
            to_remove.append(archetype)
    for a in to_remove:
        del suggestions[a]

    # ── Select top 5 comps, then enforce diversity on them ──
    top5 = dict(sorted(suggestions.items(),
        key=lambda x: x[1].get("combined_score", 0), reverse=True)[:5])

    # Enforce diversity: each player must have 3+ unique champs in the 5 shown comps
    for _pass in range(3):  # multiple passes to handle cascading swaps
        player_champ_usage = defaultdict(lambda: defaultdict(list))
        for archetype, comp in top5.items():
            for pick in comp["picks"]:
                pname = pick["player"]
                cname = pick["champion"].replace(" (off-meta)", "")
                player_champ_usage[pname][cname].append(archetype)

        any_swapped = False
        for player_name, champ_usage in player_champ_usage.items():
            if len(champ_usage) >= 3:
                continue

            scout = all_scouting.get(player_name)
            if not scout: continue
            role = ""
            for tp in team_players:
                if tp[0] == player_name: role = tp[1]; break
            valid_for_role = ROLE_VALID.get(role, set())

            used_champs = set(champ_usage.keys())
            alternatives = [c for c in scout.get("champ_list", [])
                           if c["name"] not in used_champs and
                           (not valid_for_role or c["name"] in valid_for_role)]

            # Sort shown comps weakest first for swapping
            sorted_archetypes = sorted(top5.keys(),
                key=lambda a: top5[a].get("combined_score", 0))

            swaps_needed = 3 - len(champ_usage)
            alt_idx = 0
            for arch in sorted_archetypes:
                if swaps_needed <= 0 or alt_idx >= len(alternatives):
                    break
                for pick in top5[arch]["picks"]:
                    if pick["player"] == player_name:
                        cname = pick["champion"].replace(" (off-meta)", "")
                        if len(champ_usage.get(cname, [])) > 1:
                            alt = alternatives[alt_idx]
                            arch_fit = score_champ_for_archetype(alt["name"], arch, champ_tags_data)
                            pick["champion"] = alt["name"] if arch_fit > 0.1 else f"{alt['name']} (off-meta)"
                            pick["games"] = alt["games"]
                            pick["wr"] = alt["wr"]
                            pick["kda"] = alt["kda"]
                            pick["fit"] = ("MAIN" if alt["games"] >= 5 else
                                           "Comfort" if alt["games"] >= 3 else
                                           "Off-meta" if arch_fit <= 0.1 else "Playable")
                            alt_idx += 1
                            swaps_needed -= 1
                            any_swapped = True
                        break

        if not any_swapped:
            break

    return top5


def write_draft_tool(spreadsheet, player_names):
    """Create the Draft Tool sheet with player/role dropdowns."""
    sheet_name = "Draft Tool"
    try:
        old = spreadsheet.worksheet(sheet_name)
        sheets_retry(spreadsheet.del_worksheet, old)
    except gspread.exceptions.WorksheetNotFound:
        pass

    ws = sheets_retry(spreadsheet.add_worksheet, sheet_name, rows=120, cols=14)

    DARK = {"red": 0.11, "green": 0.11, "blue": 0.18}
    HEADER = {"red": 0.09, "green": 0.14, "blue": 0.28}
    GOLD_TEXT = {"red": 0.91, "green": 0.72, "blue": 0.29}
    WHITE = {"red": 1, "green": 1, "blue": 1}
    BLUE_TEAM = {"red": 0.15, "green": 0.25, "blue": 0.55}
    RED_TEAM = {"red": 0.55, "green": 0.15, "blue": 0.15}
    L_BLUE = {"red": 0.85, "green": 0.9, "blue": 1.0}
    L_RED = {"red": 1.0, "green": 0.88, "blue": 0.88}

    rows = []
    fmts = []

    pad = lambda d, n=14: d + [""] * (n - len(d))

    # Title
    rows.append(pad(["IN-HOUSE 5v5 DRAFT TOOL"]))
    fmts.append(("A1:N1", {
        "backgroundColor": DARK,
        "textFormat": {"bold": True, "fontSize": 18, "foregroundColor": GOLD_TEXT},
        "horizontalAlignment": "CENTER"}))

    rows.append(pad(["Select players and roles, then run: python fetch_ranks_gsheets.py --draft"]))
    fmts.append(("A2:N2", {
        "backgroundColor": DARK,
        "textFormat": {"italic": True, "fontSize": 11, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    rows.append(pad([""]))

    # ── TEAM 1 (Blue Side) ──
    rows.append(pad(["TEAM 1 (BLUE SIDE)", "", "", "", "", "", "",
                     "TEAM 2 (RED SIDE)"]))
    fmts.append(("A4:G4", {
        "backgroundColor": BLUE_TEAM,
        "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))
    fmts.append(("H4:N4", {
        "backgroundColor": RED_TEAM,
        "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    rows.append(pad(["Slot", "Player", "Role", "", "", "", "",
                     "Slot", "Player", "Role"]))
    fmts.append(("A5:C5", {
        "backgroundColor": HEADER,
        "textFormat": {"bold": True, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))
    fmts.append(("H5:J5", {
        "backgroundColor": HEADER,
        "textFormat": {"bold": True, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    roles = ["Top", "Jungle", "Mid", "Bot", "Support"]
    for i, role in enumerate(roles):
        r = pad([i + 1, "", role, "", "", "", "", i + 1, "", role])
        rows.append(r)
        fmts.append((f"A{6+i}:C{6+i}", {
            "backgroundColor": L_BLUE,
            "textFormat": {"fontSize": 12},
            "horizontalAlignment": "CENTER"}))
        fmts.append((f"H{6+i}:J{6+i}", {
            "backgroundColor": L_RED,
            "textFormat": {"fontSize": 12},
            "horizontalAlignment": "CENTER"}))

    # Spacer
    rows.append(pad([""]))
    rows.append(pad([""]))

    # ── BAN RECOMMENDATIONS (filled by --draft) ──
    ban_start = len(rows) + 1
    rows.append(pad(["RECOMMENDED BANS VS TEAM 2", "", "", "", "", "", "",
                     "RECOMMENDED BANS VS TEAM 1"]))
    fmts.append((f"A{ban_start}:G{ban_start}", {
        "backgroundColor": BLUE_TEAM,
        "textFormat": {"bold": True, "fontSize": 13, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))
    fmts.append((f"H{ban_start}:N{ban_start}", {
        "backgroundColor": RED_TEAM,
        "textFormat": {"bold": True, "fontSize": 13, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    rows.append(pad(["Phase", "Ban", "Target Player", "WR%", "Games", "Priority", "",
                     "Phase", "Ban", "Target Player", "WR%", "Games", "Priority"]))
    fmts.append((f"A{ban_start+1}:F{ban_start+1}", {
        "backgroundColor": HEADER,
        "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))
    fmts.append((f"H{ban_start+1}:N{ban_start+1}", {
        "backgroundColor": HEADER,
        "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    ban_labels = ["1st Ban", "2nd Ban", "3rd Ban", "4th Ban", "5th Ban"]
    for i, label in enumerate(ban_labels):
        phase = "FIRST PHASE" if i < 3 else "SECOND PHASE"
        rows.append(pad([phase, "(run --draft)", "", "", "", "", "",
                         phase, "(run --draft)", "", "", "", ""]))
        bg = {"red": 0.95, "green": 0.92, "blue": 1.0} if i < 3 else {"red": 0.92, "green": 0.95, "blue": 1.0}
        fmts.append((f"A{ban_start+2+i}:F{ban_start+2+i}", {
            "backgroundColor": bg,
            "textFormat": {"fontSize": 11},
            "horizontalAlignment": "CENTER"}))
        fmts.append((f"H{ban_start+2+i}:N{ban_start+2+i}", {
            "backgroundColor": bg,
            "textFormat": {"fontSize": 11},
            "horizontalAlignment": "CENTER"}))

    # Spacer
    rows.append(pad([""]))
    rows.append(pad([""]))

    # ── COMP SUGGESTIONS HEADER ──
    comp_start = len(rows) + 1
    rows.append(pad(["TEAM 1 COMP SUGGESTIONS"]))
    fmts.append((f"A{comp_start}:N{comp_start}", {
        "backgroundColor": BLUE_TEAM,
        "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    rows.append(pad(["(Run --draft to generate comp suggestions based on selected players)"]))
    fmts.append((f"A{comp_start+1}:N{comp_start+1}", {
        "backgroundColor": {"red": 0.2, "green": 0.3, "blue": 0.5},
        "textFormat": {"italic": True, "fontSize": 11, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    # Spacer for comp data (will be filled by --draft)
    for _ in range(35):
        rows.append(pad([""]))

    comp2_start = len(rows) + 1
    rows.append(pad(["TEAM 2 COMP SUGGESTIONS"]))
    fmts.append((f"A{comp2_start}:N{comp2_start}", {
        "backgroundColor": RED_TEAM,
        "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    rows.append(pad(["(Run --draft to generate comp suggestions based on selected players)"]))

    # Write all data
    sheets_retry(ws.update, range_name="A1", values=rows)
    sheets_retry(ws.merge_cells, "A1:N1")
    sheets_retry(ws.merge_cells, "A2:N2")

    # Add data validation dropdowns for player selection
    role_list = "Top,Jungle,Mid,Bot,Support"

    # Use Sheets API for data validation
    reqs = []
    for row_idx in range(5, 10):  # 0-indexed rows 5-9 = sheet rows 6-10
        # Team 1 player (column B = index 1)
        reqs.append({
            "setDataValidation": {
                "range": {"sheetId": ws.id, "startRowIndex": row_idx, "endRowIndex": row_idx + 1,
                          "startColumnIndex": 1, "endColumnIndex": 2},
                "rule": {"condition": {"type": "ONE_OF_LIST",
                                       "values": [{"userEnteredValue": n} for n in player_names]},
                         "showCustomUi": True, "strict": False}
            }
        })
        # Team 1 role (column C = index 2)
        reqs.append({
            "setDataValidation": {
                "range": {"sheetId": ws.id, "startRowIndex": row_idx, "endRowIndex": row_idx + 1,
                          "startColumnIndex": 2, "endColumnIndex": 3},
                "rule": {"condition": {"type": "ONE_OF_LIST",
                                       "values": [{"userEnteredValue": r} for r in roles]},
                         "showCustomUi": True, "strict": False}
            }
        })
        # Team 2 player (column I = index 8)
        reqs.append({
            "setDataValidation": {
                "range": {"sheetId": ws.id, "startRowIndex": row_idx, "endRowIndex": row_idx + 1,
                          "startColumnIndex": 8, "endColumnIndex": 9},
                "rule": {"condition": {"type": "ONE_OF_LIST",
                                       "values": [{"userEnteredValue": n} for n in player_names]},
                         "showCustomUi": True, "strict": False}
            }
        })
        # Team 2 role (column J = index 9)
        reqs.append({
            "setDataValidation": {
                "range": {"sheetId": ws.id, "startRowIndex": row_idx, "endRowIndex": row_idx + 1,
                          "startColumnIndex": 9, "endColumnIndex": 10},
                "rule": {"condition": {"type": "ONE_OF_LIST",
                                       "values": [{"userEnteredValue": r} for r in roles]},
                         "showCustomUi": True, "strict": False}
            }
        })

    # Column widths
    col_px = [80, 130, 150, 110, 70, 70, 110, 80, 130, 150, 110, 70, 70, 110]
    for ci, px in enumerate(col_px):
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                      "startIndex": ci, "endIndex": ci + 1},
            "properties": {"pixelSize": px}, "fields": "pixelSize"}})

    # Row 1 height
    reqs.append({"updateDimensionProperties": {
        "range": {"sheetId": ws.id, "dimension": "ROWS",
                  "startIndex": 0, "endIndex": 1},
        "properties": {"pixelSize": 50}, "fields": "pixelSize"}})

    sheets_retry(spreadsheet.batch_update, {"requests": reqs})

    # Apply formats
    for i in range(0, len(fmts), 15):
        batch = [{"range": r, "format": f} for r, f in fmts[i:i+15]]
        sheets_retry(ws.batch_format, batch)

    print("  Draft Tool created with dropdowns")


def run_draft(spreadsheet, all_scouting, rankings, champ_tags_data=None):
    """Read team selections from Draft Tool and compute bans + comps."""
    try:
        ws = spreadsheet.worksheet("Draft Tool")
    except gspread.exceptions.WorksheetNotFound:
        print("  Draft Tool sheet not found. Run --setup-draft first.")
        return [], []

    values = ws.get_all_values()

    team1 = []
    team2 = []
    for i in range(5, 10):
        if i < len(values):
            row = values[i]
            p1 = row[1].strip() if len(row) > 1 else ""
            r1 = row[2].strip() if len(row) > 2 else ""
            if p1:
                team1.append((p1, r1))
            p2 = row[8].strip() if len(row) > 8 else ""
            r2 = row[9].strip() if len(row) > 9 else ""
            if p2:
                team2.append((p2, r2))

    if not team1 and not team2:
        print("  No players selected. Fill in the Draft Tool dropdowns first.")
        return [], []

    print(f"  Team 1: {', '.join(f'{p} ({r})' for p, r in team1)}")
    print(f"  Team 2: {', '.join(f'{p} ({r})' for p, r in team2)}")

    for name, scout in all_scouting.items():
        role_champs_flat = {}
        for role, champs in scout.get("role_champs", {}).items():
            role_champs_flat[role] = set(champs.keys())
        scout["role_champs_flat"] = role_champs_flat

    # Load in-house data first so comp suggestions can use it
    print("  Loading in-house custom game data...")
    inhouse_db = load_inhouse_db(spreadsheet)
    if inhouse_db:
        print(f"  Found inhouse data for {len(inhouse_db)} players")

    print("\n  Computing ban recommendations...")
    bans_vs_t2 = compute_ban_recommendations(team2, all_scouting, rankings)
    bans_vs_t1 = compute_ban_recommendations(team1, all_scouting, rankings)

    print("  Computing comp suggestions...")
    comps_t1 = compute_comp_suggestions(team1, all_scouting, rankings,
                                        champ_tags_data, inhouse_db=inhouse_db,
                                        enemy_team_players=team2,
                                        enemy_scouting=all_scouting)
    comps_t2 = compute_comp_suggestions(team2, all_scouting, rankings,
                                        champ_tags_data, inhouse_db=inhouse_db,
                                        enemy_team_players=team1,
                                        enemy_scouting=all_scouting)

    # Build name-to-riot-name mapping from Players sheet
    riot_name_map = {}
    try:
        ws_p = spreadsheet.worksheet("Players")
        pv = ws_p.get_all_values()
        for row in pv[2:]:
            if len(row) >= 3 and "#" in str(row[2]):
                riot_name_map[row[1].strip()] = row[2].rsplit("#", 1)[0]
    except Exception as e:
        print(f"Warning: riot name map build failed: {e}")

    def get_inhouse(player_name):
        ih = inhouse_db.get(player_name)
        if ih: return ih
        riot_name = riot_name_map.get(player_name, "")
        if riot_name:
            ih = inhouse_db.get(riot_name)
            if ih: return ih
        return None

    def get_top_custom_champ(player_name, role=""):
        ih = get_inhouse(player_name)
        if ih and ih["champs"]:
            # Try role-specific first
            if role:
                for c in ih["champs"]:
                    if c.get("roles", {}).get(role, 0) > 0:
                        return f"{c['name']} ({c['games']}g / {c['wr']}% WR)"
            # Fallback to overall top
            c = ih["champs"][0]
            return f"{c['name']} ({c['games']}g / {c['wr']}% WR)"
        return "No custom data"

    # ── Delete and recreate sheet to avoid write limit issues ──
    sheet_id = ws.id
    sheets_retry(spreadsheet.del_worksheet, ws)
    ws = sheets_retry(spreadsheet.add_worksheet, "Draft Tool", rows=200, cols=14)
    time.sleep(1)  # needed for the sheet to be available after recreation

    DARK = {"red": 0.11, "green": 0.11, "blue": 0.18}
    HEADER = {"red": 0.09, "green": 0.14, "blue": 0.28}
    BLUE_TEAM = {"red": 0.15, "green": 0.25, "blue": 0.55}
    RED_TEAM = {"red": 0.55, "green": 0.15, "blue": 0.15}
    WHITE = {"red": 1, "green": 1, "blue": 1}
    GOLD_TEXT = {"red": 0.91, "green": 0.72, "blue": 0.29}
    L_RED = {"red": 1.0, "green": 0.88, "blue": 0.88}
    L_BLUE = {"red": 0.88, "green": 0.92, "blue": 1.0}
    L_GREEN = {"red": 0.85, "green": 0.95, "blue": 0.85}
    L_GOLD = {"red": 1.0, "green": 0.97, "blue": 0.88}
    SECTION = {"red": 0.13, "green": 0.17, "blue": 0.30}

    rows = []
    fmts = []
    merges = []
    pad = lambda d, n=14: d + [""] * (n - len(d))

    def rn():
        return len(rows)

    # ── TITLE ──
    rows.append(pad(["IN-HOUSE 5v5 DRAFT TOOL"]))
    merges.append(f"A{rn()}:N{rn()}")
    fmts.append((f"A{rn()}:N{rn()}", {
        "backgroundColor": DARK,
        "textFormat": {"bold": True, "fontSize": 18, "foregroundColor": GOLD_TEXT},
        "horizontalAlignment": "CENTER"}))

    rows.append(pad([""]))

    # ── TEAM ROSTERS ──
    rows.append(pad(["TEAM 1 (BLUE SIDE)", "", "", "", "", "", "",
                     "TEAM 2 (RED SIDE)"]))
    merges.append(f"A{rn()}:F{rn()}")
    merges.append(f"H{rn()}:N{rn()}")
    fmts.append((f"A{rn()}:F{rn()}", {
        "backgroundColor": BLUE_TEAM,
        "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))
    fmts.append((f"H{rn()}:N{rn()}", {
        "backgroundColor": RED_TEAM,
        "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    rows.append(pad(["Role", "Player", "Rank", "Top Custom Champ", "", "", "",
                     "Role", "Player", "Rank", "Top Custom Champ"]))
    fmts.append((f"A{rn()}:D{rn()}", {
        "backgroundColor": HEADER,
        "textFormat": {"bold": True, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))
    fmts.append((f"H{rn()}:K{rn()}", {
        "backgroundColor": HEADER,
        "textFormat": {"bold": True, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    for i in range(5):
        t1_role = team1[i][1] if i < len(team1) else ""
        t1_name = team1[i][0] if i < len(team1) else ""
        t1_rank = f"#{rankings.get(t1_name, {}).get('position', '?')}" if t1_name else ""
        t1_champ = get_top_custom_champ(t1_name, t1_role) if t1_name else ""
        t2_role = team2[i][1] if i < len(team2) else ""
        t2_name = team2[i][0] if i < len(team2) else ""
        t2_rank = f"#{rankings.get(t2_name, {}).get('position', '?')}" if t2_name else ""
        t2_champ = get_top_custom_champ(t2_name, t2_role) if t2_name else ""

        rows.append(pad([t1_role, t1_name, t1_rank, t1_champ, "", "", "",
                         t2_role, t2_name, t2_rank, t2_champ]))
        bg = L_BLUE if i % 2 == 0 else {"red": 0.92, "green": 0.95, "blue": 1.0}
        fmts.append((f"A{rn()}:D{rn()}", {
            "backgroundColor": bg,
            "textFormat": {"bold": True, "fontSize": 12},
            "horizontalAlignment": "CENTER"}))
        bg2 = L_RED if i % 2 == 0 else {"red": 1.0, "green": 0.93, "blue": 0.93}
        fmts.append((f"H{rn()}:K{rn()}", {
            "backgroundColor": bg2,
            "textFormat": {"bold": True, "fontSize": 12},
            "horizontalAlignment": "CENTER"}))

    rows.append(pad([""]))
    rows.append(pad([""]))

    # ── BAN RECOMMENDATIONS ──
    rows.append(pad(["RECOMMENDED BANS vs TEAM 2 (Blue bans)", "", "", "", "", "",
                     "", "RECOMMENDED BANS vs TEAM 1 (Red bans)"]))
    merges.append(f"A{rn()}:F{rn()}")
    merges.append(f"H{rn()}:N{rn()}")
    fmts.append((f"A{rn()}:F{rn()}", {
        "backgroundColor": BLUE_TEAM,
        "textFormat": {"bold": True, "fontSize": 13, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))
    fmts.append((f"H{rn()}:N{rn()}", {
        "backgroundColor": RED_TEAM,
        "textFormat": {"bold": True, "fontSize": 13, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    rows.append(pad(["Phase", "BAN", "Target", "WR%", "Games", "Priority",
                     "", "Phase", "BAN", "Target", "WR%", "Games", "Priority"]))
    fmts.append((f"A{rn()}:F{rn()}", {
        "backgroundColor": HEADER,
        "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))
    fmts.append((f"H{rn()}:N{rn()}", {
        "backgroundColor": HEADER,
        "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
        "horizontalAlignment": "CENTER"}))

    for i in range(5):
        phase = "1st Phase" if i < 3 else "2nd Phase"
        b1 = bans_vs_t2[i] if i < len(bans_vs_t2) else None
        b2 = bans_vs_t1[i] if i < len(bans_vs_t1) else None

        def _ban_label(b):
            if not b: return "-"
            return f"⚠ {b['champion']}" if b.get("is_must_ban") else b["champion"]

        row_data = [
            phase,
            _ban_label(b1),
            b1["player"] if b1 else "-",
            f"{b1['wr']}%" if b1 else "-",
            b1["games"] if b1 else "-",
            round(b1["priority"], 1) if b1 else "-",
            "",
            phase,
            _ban_label(b2),
            b2["player"] if b2 else "-",
            f"{b2['wr']}%" if b2 else "-",
            b2["games"] if b2 else "-",
            round(b2["priority"], 1) if b2 else "-",
            "",
        ]
        rows.append(row_data)
        bg = L_RED if i < 3 else L_BLUE
        fmts.append((f"A{rn()}:F{rn()}", {
            "backgroundColor": bg,
            "textFormat": {"bold": True, "fontSize": 11},
            "horizontalAlignment": "CENTER"}))
        fmts.append((f"H{rn()}:N{rn()}", {
            "backgroundColor": bg,
            "textFormat": {"bold": True, "fontSize": 11},
            "horizontalAlignment": "CENTER"}))

    rows.append(pad([""]))
    rows.append(pad([""]))

    # ── COMP SUGGESTIONS ──
    for team_label, comps, team_color in [
        ("TEAM 1", comps_t1, BLUE_TEAM),
        ("TEAM 2", comps_t2, RED_TEAM),
    ]:
        rows.append(pad([f"{team_label} COMP SUGGESTIONS"]))
        merges.append(f"A{rn()}:N{rn()}")
        fmts.append((f"A{rn()}:N{rn()}", {
            "backgroundColor": team_color,
            "textFormat": {"bold": True, "fontSize": 15, "foregroundColor": WHITE},
            "horizontalAlignment": "CENTER"}))

        sorted_comps = sorted(comps.items(),
                              key=lambda x: x[1].get("combined_score", 0), reverse=True)

        for archetype, comp in sorted_comps:
            viability = comp["viability"]
            v_colors = {
                "STRONG": {"red": 0.1, "green": 0.5, "blue": 0.1},
                "VIABLE": {"red": 0.3, "green": 0.5, "blue": 0.2},
                "WEAK": {"red": 0.6, "green": 0.4, "blue": 0.1},
                "NOT RECOMMENDED": {"red": 0.5, "green": 0.2, "blue": 0.2},
            }

            ctr = comp.get("counter_potential", 0)
            ctr_str = f" | Counter: {ctr}/100" if ctr > 0 else ""
            rows.append(pad([f"{archetype.upper()} — {comp['description']}",
                             "", "", "", "", "", "",
                             f"{viability} | Synergy: {comp.get('synergy', 0)}/100 | {comp['on_meta_count']}/5 on-meta{ctr_str}"]))
            merges.append(f"A{rn()}:G{rn()}")
            merges.append(f"H{rn()}:N{rn()}")
            fmts.append((f"A{rn()}:N{rn()}", {
                "backgroundColor": v_colors.get(viability, SECTION),
                "textFormat": {"bold": True, "fontSize": 12, "foregroundColor": WHITE},
                "horizontalAlignment": "CENTER"}))

            rows.append(pad(["Player", "Role", "Champion", "Games", "Win Rate",
                             "KDA", "Fit Level"]))
            fmts.append((f"A{rn()}:G{rn()}", {
                "backgroundColor": HEADER,
                "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": WHITE},
                "horizontalAlignment": "CENTER"}))

            for pick in comp["picks"]:
                bg = (L_GREEN if pick["fit"] == "MAIN" else
                      L_GOLD if pick["fit"] == "Comfort" else
                      L_RED if pick["fit"] == "Off-meta" else
                      {"red": 1, "green": 1, "blue": 1})
                rows.append(pad([pick["player"], pick["role"], pick["champion"],
                                 pick.get("games", 0),
                                 f"{pick.get('wr', 0)}%",
                                 pick.get("kda", 0),
                                 pick["fit"]]))
                fmts.append((f"A{rn()}:G{rn()}", {
                    "backgroundColor": bg,
                    "textFormat": {"fontSize": 11},
                    "horizontalAlignment": "CENTER"}))

            rows.append(pad([""]))  # spacer

        rows.append(pad([""]))

    # ── SINGLE BATCH WRITE ──
    sheets_retry(ws.update, values=rows, range_name="A1")

    # Apply merges
    for m in merges:
        sheets_retry(ws.merge_cells, m)

    # Column widths
    col_px = [80, 130, 150, 110, 70, 70, 110, 80, 130, 150, 110, 70, 70, 110]
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

    print("\n  Draft Tool updated with bans and comp suggestions!")
    return team1, team2


def append_activity_event(spreadsheet, event_type, player_name, details):
    """Append one event row to the _Activity log sheet."""
    sheet_name = "_Activity"
    try:
        ws = get_or_create_sheet(spreadsheet, sheet_name, rows=200, cols=4)
        # Write header row if the sheet is brand new
        if not ws.get_all_values():
            sheets_retry(ws.append_row, ["_ACTIVITY LOG", "", "", ""],
                         value_input_option="RAW")
        sheets_retry(ws.append_row,
                     [datetime.now().strftime("%Y-%m-%d %H:%M"), event_type,
                      player_name or "", details],
                     value_input_option="RAW")
    except Exception as e:
        print(f"  (Activity log write skipped: {e})")


def load_activity_log(spreadsheet, limit=50):
    """Return the most recent `limit` activity events as a list of dicts."""
    try:
        ws = spreadsheet.worksheet("_Activity")
    except Exception as e:
        print(f"Warning: could not load activity log: {e}")
        return []
    rows = ws.get_all_values()
    # Skip header row; rows are oldest-first
    data_rows = [r for r in rows if len(r) >= 4 and r[0] != "_ACTIVITY LOG" and r[0]]
    recent = data_rows[-limit:]
    recent.reverse()  # newest first
    return [
        {"ts": r[0], "type": r[1], "player": r[2], "details": r[3]}
        for r in recent
    ]


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

def fetch_custom_matches(puuid, routing, api_key, count=25):
    """Fetch ALL match IDs from the last 60 days using time-based pagination."""
    # Go back 60 days
    end_time = int(time.time())
    start_time = end_time - (60 * 24 * 60 * 60)

    all_ids = []
    start_idx = 0

    while True:
        ids = riot_get(
            f"https://{routing}.api.riotgames.com/lol/match/v5/matches/"
            f"by-puuid/{puuid}/ids?startTime={start_time}&endTime={end_time}"
            f"&start={start_idx}&count=100", api_key)
        if not ids:
            break
        all_ids.extend(ids)
        if len(ids) < 100:
            break  # no more pages
        start_idx += 100
        time.sleep(0.5)

    return all_ids


def fetch_and_filter_inhouse(all_puuids, player_puuid_map, routing, region, api_key, count=25):
    """
    Fetch custom games across all players, deduplicate, and filter for
    true in-house games (5v5 with multiple group members).
    Returns list of match dicts with full participant data.
    """
    all_match_ids = set()
    player_match_ids = {}

    # Collect match IDs from all players
    print("\n  Collecting custom game IDs from all players...")
    for name, puuid in player_puuid_map.items():
        ids = fetch_custom_matches(puuid, routing, api_key, count)
        player_match_ids[name] = ids
        all_match_ids.update(ids)
        print(f"    {name}: {len(ids)} custom games found")
        time.sleep(0.8)

    print(f"\n  {len(all_match_ids)} unique matches found across all players (last 60 days)")

    # Pre-filter: in-house 5v5 must appear in many players' histories
    # A game with 5+ group members will show up in 5+ match lists
    match_count = defaultdict(int)
    for name, ids in player_match_ids.items():
        for mid in ids:
            match_count[mid] += 1

    # Games in 5+ players' histories are almost certainly in-houses
    candidates = [mid for mid, cnt in match_count.items() if cnt >= 5]
    # Also check games in 3-4 players' histories (could be customs with some non-group members)
    maybe_candidates = [mid for mid, cnt in match_count.items() if cnt >= 3 and cnt < 5]

    all_candidates = candidates + maybe_candidates
    print(f"  {len(candidates)} matches in 5+ players' histories (very likely in-house)")
    print(f"  {len(maybe_candidates)} matches in 3-4 players' histories (possible in-house)")
    print(f"  Checking {len(all_candidates)} candidate matches...")

    # Fetch each candidate match
    inhouse_matches = []
    checked = 0
    queue_ids_seen = defaultdict(int)
    group_puuids = set(all_puuids)
    for mid in all_candidates:
        time.sleep(0.5)
        mdata = riot_get(
            f"https://{routing}.api.riotgames.com/lol/match/v5/matches/{mid}",
            api_key)
        checked += 1
        if not mdata:
            continue

        info = mdata.get("info", {})
        participants = info.get("participants", [])
        queue_id = info.get("queueId", -1)
        game_mode = info.get("gameMode", "")
        game_type = info.get("gameType", "")
        queue_ids_seen[f"{queue_id} ({game_mode}/{game_type})"] += 1

        # Must be 10 participants (5v5)
        if len(participants) != 10:
            continue

        # Count group members in this game
        game_puuids = set(p.get("puuid", "") for p in participants)
        overlap = group_puuids & game_puuids
        group_count = len(overlap)

        # Detection:
        # - Queue 0/3130/CUSTOM_GAME with 3+ group = custom in-house
        # - Any non-ranked-solo queue with 5+ group members = likely in-house
        is_custom_queue = (queue_id == 0 or queue_id == 3130 or game_type == "CUSTOM_GAME")

        if is_custom_queue and group_count >= 3:
            pass  # accept
        elif group_count >= 6 and queue_id != 420:
            pass  # accept
        else:
            continue

        # This is an in-house game — extract all data
        match_data = {
            "match_id": mid,
            "duration_min": round(info.get("gameDuration", 0) / 60, 1),
            "timestamp": info.get("gameCreation", 0),
            "players": [],
        }

        for p in participants:
            puuid = p.get("puuid", "")
            # Reverse lookup name
            pname = None
            for name, pid in player_puuid_map.items():
                if pid == puuid:
                    pname = name
                    break

            cs = p.get("totalMinionsKilled", 0) + p.get("neutralMinionsKilled", 0)
            dur = max(info.get("gameDuration", 1) / 60, 0.1)

            match_data["players"].append({
                "puuid": puuid,
                "name": pname or p.get("riotIdGameName", "Unknown"),
                "is_group": puuid in group_puuids,
                "champion": p.get("championName", "?"),
                "team_id": p.get("teamId", 0),
                "win": p.get("win", False),
                "kills": p.get("kills", 0),
                "deaths": p.get("deaths", 0),
                "assists": p.get("assists", 0),
                "cs": cs,
                "cs_min": round(cs / dur, 1),
                "damage": p.get("totalDamageDealtToChampions", 0),
                "gold": p.get("goldEarned", 0),
                "vision": p.get("visionScore", 0),
                "role": p.get("teamPosition", "UNKNOWN"),
            })

        inhouse_matches.append(match_data)

        if checked % 20 == 0:
            print(f"    Checked {checked}/{len(all_candidates)}, found {len(inhouse_matches)} in-house games")

    print(f"\n  Found {len(inhouse_matches)} in-house 5v5 games total")
    print(f"  Queue types seen across all matches:")
    for qt, cnt in sorted(queue_ids_seen.items(), key=lambda x: x[1], reverse=True):
        print(f"    {qt}: {cnt} games")
    return inhouse_matches


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

def main():
    parser = argparse.ArgumentParser(description="LoL Power Rankings - Full Analytics")
    parser.add_argument("--key", required=True, help="Riot API key")
    parser.add_argument("--sheet", required=True, help="Google Sheet name, URL, or key")
    parser.add_argument("--creds", default=DEFAULT_CREDS_FILE)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--routing", default=DEFAULT_ROUTING)
    parser.add_argument("--skip-matches", action="store_true",
                        help="Skip match history (faster, fewer API calls)")
    parser.add_argument("--scout", action="store_true",
                        help="Generate per-player scouting reports (100 games each)")
    parser.add_argument("--scout-only", action="store_true",
                        help="Only run scouting reports, skip rank/analytics updates")
    parser.add_argument("--draft", action="store_true",
                        help="Read Draft Tool selections and compute bans + comp suggestions")
    parser.add_argument("--setup-draft", action="store_true",
                        help="Just create/recreate the Draft Tool sheet with dropdowns")
    parser.add_argument("--inhouse", action="store_true",
                        help="Track in-house custom game stats")
    parser.add_argument("--scout-new", action="store_true",
                        help="Scout only players not already in _ScoutDB, then merge into existing data")
    parser.add_argument("--scout-player", default="",
                        help="Re-scout a single named player and merge into existing _ScoutDB")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  LoL Power Rankings - Full Analytics Suite")
    print(f"  Region: {args.region}  |  Routing: {args.routing}")
    print(f"{'='*60}\n")

    # Connect
    print("Connecting to Google Sheets...")
    try:
        spreadsheet = connect_to_sheet(args.creds, args.sheet)
        print(f"  Connected to: {spreadsheet.title}\n")
    except FileNotFoundError:
        print(f"  x Credentials file '{args.creds}' not found.")
        sys.exit(1)
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"  x Sheet not found. Share it with your service account email.")
        sys.exit(1)

    # Champion map
    print("Loading champion data...")
    champ_map, champ_tags = load_champion_map()

    # Read players
    try:
        ws_players = spreadsheet.worksheet("Players")
    except gspread.exceptions.WorksheetNotFound:
        print("  x 'Players' sheet not found.")
        sys.exit(1)

    all_values = ws_players.get_all_values()
    players = []
    for row_idx, row in enumerate(all_values):
        if len(row) >= 3 and "#" in str(row[2]) and row_idx >= 2:
            players.append({"row": row_idx - 1, "name": row[1], "riot_id": row[2]})

    if not players:
        print("  No valid Riot IDs found.")
        sys.exit(1)

    print(f"\nFound {len(players)} players.\n")

    # Read tier list data for analytics
    if not args.scout_only and not args.draft and not args.setup_draft and not args.inhouse and not args.scout_player:
        print("Reading tier list data...")
        try:
            ws_tiers = spreadsheet.worksheet("Tier Lists")
            tier_values = ws_tiers.get_all_values()
            rater_names = []
            if len(tier_values) > 2:
                for c in range(2, len(tier_values[2])):
                    val = tier_values[2][c]
                    if val in ("Avg Score", "Normalized", ""):
                        break
                    rater_names.append(val)
            tier_data = {}
            player_names_tiers = []
            for i, row in enumerate(tier_values[3:]):
                tiers = []
                for c in range(2, 2 + len(rater_names)):
                    if c < len(row) and row[c] in TIER_TO_NUM:
                        tiers.append(row[c])
                tier_data[i] = tiers
                if len(row) > 1 and row[1]:
                    player_names_tiers.append(row[1])
            print(f"  Read {len(rater_names)} raters x {len(player_names_tiers)} players")
        except Exception as e:
            print(f"  Warning: could not read tier lists: {e}")
            tier_data, rater_names, player_names_tiers = {}, [], []

        # Fetch from Riot API
        print(f"\n{'='*60}")
        print("FETCHING RIOT API DATA")
        print(f"{'='*60}\n")

        results = []
        for idx, player in enumerate(players, 1):
            game_name, tag_line = player["riot_id"].rsplit("#", 1)
            print(f"[{idx}/{len(players)}] {player['name']} ({player['riot_id']})")

            puuid = fetch_account(game_name.strip(), tag_line.strip(), args.routing, args.key)
            if not puuid:
                results.append({
                    "row": idx, "name": player["name"],
                    "tier": "Unranked", "division": "N/A",
                    "lp": 0, "wins": 0, "losses": 0,
                    "score": 0, "normalized": 0,
                    "top_champs": [], "recent_matches": [],
                })
                continue
            time.sleep(0.8)

            tier, division, lp, wins, losses = fetch_ranked(puuid, args.region, args.key)
            score = compute_score(tier, division)
            normalized = round(score / 10 * 100, 1)
            rs = f"{tier} {division}" if division != "N/A" else tier
            print(f"    Rank: {rs} ({lp} LP) - {wins}W / {losses}L")
            time.sleep(0.8)

            top_champs = fetch_top_champions(puuid, args.region, args.key, champ_map)
            if top_champs:
                print(f"    Champs: {', '.join(c['name'] for c in top_champs)}")
            time.sleep(0.8)

            recent_matches = []
            if not args.skip_matches:
                recent_matches = fetch_recent_matches(
                    puuid, args.routing, args.region, args.key)
                if recent_matches:
                    rw = sum(1 for m in recent_matches if m["win"])
                    print(f"    Recent: {rw}W-{len(recent_matches)-rw}L")
            else:
                print(f"    Skipping match history")

            results.append({
                "row": idx, "name": player["name"],
                "tier": tier, "division": division,
                "lp": lp, "wins": wins, "losses": losses,
                "score": score, "normalized": normalized,
                "top_champs": top_champs, "recent_matches": recent_matches,
            })

        # Compute analytics
        print(f"\n{'='*60}")
        print("COMPUTING ANALYTICS")
        print(f"{'='*60}\n")

        consensus, hot_takes, rater_bias = [], [], []
        if tier_data and player_names_tiers:
            consensus, hot_takes, rater_bias = compute_tier_analytics(
                tier_data, player_names_tiers, rater_names)
            print(f"  {len(consensus)} players analyzed")
            print(f"  {len(hot_takes)} hot takes found")
            print(f"  {len(rater_bias)} raters analyzed")
        else:
            print("  No tier data for analytics")

        # Write to Google Sheets
        print(f"\n{'='*60}")
        print("WRITING TO GOOGLE SHEETS")
        print(f"{'='*60}\n")

        ts = datetime.now().strftime("%Y-%m-%d %H:%M")

        write_rank_data(spreadsheet, results, ts)
        write_player_stats(spreadsheet, results, champ_map)
        if consensus:
            write_consensus(spreadsheet, consensus)
        write_hot_takes(spreadsheet, hot_takes)
        if rater_bias:
            write_rater_bias(spreadsheet, rater_bias)
        write_rank_history(spreadsheet, results, ts)
        append_activity_event(spreadsheet, "UPDATE", "",
                              f"{len(results)} players updated")
    else:
        results = []

    # Scouting reports
    if args.scout or args.scout_only:
        # Read final rankings for scouting headers
        print("\nReading Final Rankings...")
        final_rankings = get_final_rankings(spreadsheet)
        if final_rankings:
            print(f"  Found rankings for {len(final_rankings)} players")
        else:
            print("  No final rankings found (run without --scout-only first)")

        # Load inhouse data if available
        print("\nLoading In-House custom game data...")
        inhouse_db = load_inhouse_db(spreadsheet)
        if inhouse_db:
            print(f"  Found inhouse data for {len(inhouse_db)} players")
        else:
            print("  No inhouse data found (run inhouse_tracker.py first)")

        print(f"\n{'='*60}")
        print("GENERATING SCOUTING REPORTS (100 games per player)")
        print(f"{'='*60}")
        print(f"This will make ~{len(players) * 50} API calls. Estimated time: {len(players) * 2}-{len(players) * 4} minutes.\n")

        all_scouting = {}

        for idx, player in enumerate(players, 1):
            game_name, tag_line = player["riot_id"].rsplit("#", 1)
            print(f"\n[{idx}/{len(players)}] Scouting {player['name']}...")

            puuid = fetch_account(game_name.strip(), tag_line.strip(), args.routing, args.key)
            if not puuid:
                print(f"    Could not find account, skipping")
                continue
            time.sleep(0.8)

            scout_matches = fetch_scouting_matches(puuid, args.routing, args.region, args.key, count=100)
            if not scout_matches:
                print(f"    No matches found, skipping")
                continue

            analysis = analyze_player(scout_matches)
            if not analysis:
                print(f"    Analysis failed, skipping")
                continue

            # Store for draft tool
            all_scouting[player["name"]] = analysis

            # Find this player's rank info
            pr = next((r for r in results if r["name"] == player["name"]), None)
            if pr:
                rs = f"{pr['tier']} {pr['division']}" if pr['division'] != "N/A" else pr['tier']
                plp = pr["lp"]
            else:
                # Scout-only mode: fetch rank directly
                tier, division, plp, _, _ = fetch_ranked(puuid, args.region, args.key)
                rs = f"{tier} {division}" if division != "N/A" else tier
                time.sleep(0.8)

            # Get ranking info for this player
            ranking_info = final_rankings.get(player["name"])

            # Get inhouse data - try player name and riot game name
            player_inhouse = inhouse_db.get(player["name"])
            if not player_inhouse:
                riot_name = player["riot_id"].rsplit("#", 1)[0] if "#" in player["riot_id"] else ""
                player_inhouse = inhouse_db.get(riot_name)

            write_scouting_sheet(spreadsheet, player["name"], rs, plp, analysis, ranking_info, player_inhouse)

        # Create Draft Tool sheet with dropdowns
        print(f"\nCreating Draft Tool...")
        player_name_list = [p["name"] for p in players]
        write_draft_tool(spreadsheet, player_name_list)

        # Save scouting data for draft use
        # Store as a hidden data sheet for --draft to use later
        write_scouting_database(spreadsheet, all_scouting, final_rankings)

        append_activity_event(spreadsheet, "SCOUT", "",
                              f"Full scout: {len(all_scouting)} players updated")
        print(f"\nAll scouting reports generated!")

    # Scout new players only (merge into existing _ScoutDB)
    if args.scout_new:
        print(f"\n{'='*60}")
        print("SCOUTING NEW PLAYERS")
        print(f"{'='*60}\n")

        # Load existing scouting database
        print("Loading existing scouting database...")
        existing_scouting, existing_rankings = load_scouting_database(spreadsheet)
        already_scouted = set(existing_scouting.keys())
        print(f"  {len(already_scouted)} players already scouted: {', '.join(sorted(already_scouted)) or 'none'}")

        # Determine which players are missing
        new_players = [p for p in players[::-1] if p["name"] not in already_scouted]
        if not new_players:
            print("\nAll players are already scouted. Nothing to do.")
            print("Tip: run the full Scout command to refresh existing players.")
            return

        print(f"\n  {len(new_players)} new player(s) to scout (bottom to top): {', '.join(p['name'] for p in new_players)}\n")

        # Load ranking info for the new players
        final_rankings = get_final_rankings(spreadsheet)

        # Load inhouse data
        print("Loading In-House custom game data...")
        inhouse_db = load_inhouse_db(spreadsheet)
        if inhouse_db:
            print(f"  Found inhouse data for {len(inhouse_db)} players")
        else:
            print("  No inhouse data found")

        print(f"\nScouting {len(new_players)} new player(s) (100 games each)...\n")

        new_scouting = {}
        for idx, player in enumerate(new_players, 1):
            game_name, tag_line = player["riot_id"].rsplit("#", 1)
            print(f"\n[{idx}/{len(new_players)}] Scouting {player['name']}...")

            puuid = fetch_account(game_name.strip(), tag_line.strip(), args.routing, args.key)
            if not puuid:
                print(f"    Could not find account, skipping")
                continue
            time.sleep(0.8)

            scout_matches = fetch_scouting_matches(puuid, args.routing, args.region, args.key, count=100)
            if not scout_matches:
                print(f"    No matches found, skipping")
                continue

            analysis = analyze_player(scout_matches)
            if not analysis:
                print(f"    Analysis failed, skipping")
                continue

            new_scouting[player["name"]] = analysis

            # Fetch rank for scouting sheet header
            tier, division, plp, _, _ = fetch_ranked(puuid, args.region, args.key)
            rs = f"{tier} {division}" if division != "N/A" else tier
            time.sleep(0.8)

            ranking_info = final_rankings.get(player["name"])
            player_inhouse = inhouse_db.get(player["name"])
            if not player_inhouse:
                riot_name = player["riot_id"].rsplit("#", 1)[0] if "#" in player["riot_id"] else ""
                player_inhouse = inhouse_db.get(riot_name)

            write_scouting_sheet(spreadsheet, player["name"], rs, plp, analysis, ranking_info, player_inhouse)

        if not new_scouting:
            print("\nNo new players could be scouted.")
            return

        # Merge new data into existing and save
        merged_scouting = {**existing_scouting, **new_scouting}
        merged_rankings = {**existing_rankings, **final_rankings}
        write_scouting_database(spreadsheet, merged_scouting, merged_rankings)
        new_names = ", ".join(new_scouting.keys())
        append_activity_event(spreadsheet, "SCOUT_NEW", new_names,
                              f"Added {len(new_scouting)} new player(s): {new_names}")
        print(f"\nScouting complete! Added {len(new_scouting)} new player(s). Database now covers {len(merged_scouting)} players.")
        return

    # Re-scout a single named player and merge into existing _ScoutDB
    if args.scout_player:
        target_name = args.scout_player.strip()
        print(f"\n{'='*60}")
        print(f"RE-SCOUTING PLAYER: {target_name.upper()}")
        print(f"{'='*60}\n")

        # Find the player in the Players sheet
        player = next((p for p in players if p["name"].lower() == target_name.lower()), None)
        if not player:
            print(f"  ERROR: '{target_name}' not found in Players sheet.")
            print(f"  Available: {', '.join(p['name'] for p in players)}")
            return

        print(f"  Found: {player['name']} ({player['riot_id']})")

        game_name, tag_line = player["riot_id"].rsplit("#", 1)
        puuid = fetch_account(game_name.strip(), tag_line.strip(), args.routing, args.key)
        if not puuid:
            print(f"  ERROR: Could not find Riot account for {player['riot_id']}.")
            return
        time.sleep(0.8)

        print(f"  Fetching last 100 games...")
        scout_matches = fetch_scouting_matches(puuid, args.routing, args.region, args.key, count=100)
        if not scout_matches:
            print(f"  ERROR: No matches found for {player['name']}.")
            return

        analysis = analyze_player(scout_matches)
        if not analysis:
            print(f"  ERROR: Analysis failed for {player['name']}.")
            return

        # Fetch current rank
        tier, division, plp, _, _ = fetch_ranked(puuid, args.region, args.key)
        rs = f"{tier} {division}" if division != "N/A" else tier
        time.sleep(0.8)

        # Load supporting data
        final_rankings = get_final_rankings(spreadsheet)
        ranking_info = final_rankings.get(player["name"])

        print("  Loading In-House custom game data...")
        inhouse_db = load_inhouse_db(spreadsheet)
        player_inhouse = inhouse_db.get(player["name"])
        if not player_inhouse:
            riot_name = player["riot_id"].rsplit("#", 1)[0] if "#" in player["riot_id"] else ""
            player_inhouse = inhouse_db.get(riot_name)

        # Write/overwrite the scout sheet for this player
        print(f"  Writing scouting sheet...")
        write_scouting_sheet(spreadsheet, player["name"], rs, plp, analysis, ranking_info, player_inhouse)

        # Load existing _ScoutDB, replace this player's entry, save merged result
        print(f"  Updating _ScoutDB...")
        existing_scouting, existing_rankings = load_scouting_database(spreadsheet)
        existing_scouting[player["name"]] = analysis
        existing_rankings.update(final_rankings)
        write_scouting_database(spreadsheet, existing_scouting, existing_rankings)
        rank_str = f" ({rs} {plp} LP)" if rs and rs not in ("Unranked", "") else ""
        append_activity_event(spreadsheet, "SCOUT", player["name"],
                              f"Re-scouted {player['name']}{rank_str}")
        print(f"\nDone! {player['name']} has been re-scouted and _ScoutDB updated.")
        return

    # Setup draft tool only
    if args.setup_draft:
        print("\nCreating Draft Tool sheet...")
        player_name_list = [p["name"] for p in players]
        write_draft_tool(spreadsheet, player_name_list)
        print(f"\nDone! Go to the Draft Tool tab and select players from the dropdowns.\n")
        return

    # Draft mode
    if args.draft:
        print(f"\n{'='*60}")
        print("RUNNING DRAFT TOOL")
        print(f"{'='*60}\n")

        # Load scouting database
        all_scouting, db_rankings = load_scouting_database(spreadsheet)
        if not all_scouting:
            print("  No scouting data found. Run --scout first.")
        else:
            # Also get latest final rankings
            final_rankings = get_final_rankings(spreadsheet)
            if final_rankings:
                db_rankings.update(final_rankings)
            team1, team2 = run_draft(spreadsheet, all_scouting, db_rankings, champ_tags)
            t1_str = ", ".join(p for p, r in team1) if team1 else "?"
            t2_str = ", ".join(p for p, r in team2) if team2 else "?"
            append_activity_event(spreadsheet, "DRAFT", "",
                                  f"Draft: Team 1 [{t1_str}] vs Team 2 [{t2_str}]")

    # In-house stats tracker
    if args.inhouse:
        print(f"\n{'='*60}")
        print("IN-HOUSE STATS TRACKER")
        print(f"{'='*60}\n")

        # First get all PUUIDs
        print("  Looking up player accounts...")
        player_puuid_map = {}
        for player in players:
            game_name, tag_line = player["riot_id"].rsplit("#", 1)
            puuid = fetch_account(game_name.strip(), tag_line.strip(), args.routing, args.key)
            if puuid:
                player_puuid_map[player["name"]] = puuid
                print(f"    {player['name']}: found")
            else:
                print(f"    {player['name']}: not found, skipping")
            time.sleep(0.8)

        all_puuids = list(player_puuid_map.values())

        # Fetch and filter in-house matches
        inhouse_matches = fetch_and_filter_inhouse(
            all_puuids, player_puuid_map, args.routing, args.region, args.key, count=25)

        if not inhouse_matches:
            print("\n  No in-house games found. Make sure you've played custom 5v5s recently.")
        else:
            # Analyze
            print("\n  Analyzing in-house stats...")
            player_stats, h2h = analyze_inhouse(inhouse_matches, player_puuid_map)

            # Write sheets
            print(f"\n{'='*60}")
            print("WRITING TO GOOGLE SHEETS")
            print(f"{'='*60}\n")

            write_inhouse_overview(spreadsheet, player_stats, len(inhouse_matches))
            write_inhouse_h2h(spreadsheet, h2h, player_stats)

            # Print summary
            print(f"\n{'='*60}")
            print("IN-HOUSE SUMMARY")
            print(f"{'='*60}")
            print(f"\n{len(inhouse_matches)} in-house games found\n")
            print(f"{'Player':<14} {'Games':<7} {'W-L':<8} {'WR%':<7} {'KDA'}")
            print(f"{'_'*45}")
            sorted_ps = sorted(player_stats.items(),
                                key=lambda x: x[1]["wins"] / max(x[1]["games"], 1),
                                reverse=True)
            for name, ps in sorted_ps:
                g = ps["games"]
                if g == 0:
                    continue
                wr = round(ps["wins"] / g * 100, 1)
                kda = round((ps["kills"] + ps["assists"]) / max(ps["deaths"], 1), 2)
                print(f"{name:<14} {g:<7} {ps['wins']}W-{g-ps['wins']}L  {wr}%   {kda}")

            append_activity_event(spreadsheet, "INHOUSE", "",
                                  f"{len(inhouse_matches)} in-house game(s) logged")
            print(f"\nDone! Check 'In-House Stats' and 'In-House Head-to-Head' tabs.\n")
            return

    # Summary
    if not args.scout_only and not args.draft and not args.setup_draft and not args.inhouse:
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        print(f"\n{'#':<4} {'Player':<14} {'Rank':<16} {'WR%':<7} {'Top Champ':<14} {'Recent'}")
        print(f"{'_'*70}")
        for r in results:
            rs = f"{r['tier']} {r['division']}" if r['division'] != "N/A" else r['tier']
            g = r["wins"] + r["losses"]
            wr = f"{round(r['wins']/g*100,1)}%" if g > 0 else "-"
            top = r["top_champs"][0]["name"] if r.get("top_champs") else "-"
            mt = r.get("recent_matches", [])
            rec = f"{sum(1 for m in mt if m['win'])}W-{sum(1 for m in mt if not m['win'])}L" if mt else "-"
            print(f"{r['row']:<4} {r['name']:<14} {rs:<16} {wr:<7} {top:<14} {rec}")

        if hot_takes:
            print(f"\nTOP HOT TAKES:")
            for ht in hot_takes[:5]:
                print(f"  {ht['rater']} rated {ht['player']} as {ht['rated']} "
                      f"(avg: {ht['avg']}) - {ht['diff']} tiers {ht['direction']}")

        if rater_bias:
            mg = max(rater_bias, key=lambda x: x["avg"])
            mh = min(rater_bias, key=lambda x: x["avg"])
            print(f"\nMOST GENEROUS: {mg['rater']} (avg {mg['avg_tier']}, {mg['avg']})")
            print(f"MOST HARSH:    {mh['rater']} (avg {mh['avg_tier']}, {mh['avg']})")

    print(f"\nDone! Check your Google Sheet.\n")


if __name__ == "__main__":
    main()
