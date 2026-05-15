"""
In-House Custom Game Tracker (via League Client API)
=====================================================
Anyone in the group can run this to log their custom games.
Games are tracked by ID so duplicates are impossible.

SETUP:
  pip install requests gspread google-auth
  Place credentials.json in the same folder

USAGE:
  python inhouse_tracker.py --sheet "YOUR_SHEET_URL"

OPTIONS:
  --count    Matches to search (default: 500)
  --days     Time window in days (default: 180)
  --debug    Show raw data for debugging
  --lol-path Custom League install path
"""

import argparse, time, random, sys, os, re, subprocess, urllib3
from datetime import datetime, timedelta
from collections import defaultdict

import requests
import gspread
from google.oauth2.service_account import Credentials

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]


# ── Sheets Retry Helper ───────────────────────────────────────

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


# ── LCU Connection ───────────────────────────────────────────

def find_lockfile():
    paths = []
    if sys.platform == "win32":
        for d in ["C","D","E"]:
            paths.extend([f"{d}:\\Riot Games\\League of Legends\\lockfile",
                         f"{d}:\\Program Files\\Riot Games\\League of Legends\\lockfile",
                         f"{d}:\\Program Files (x86)\\Riot Games\\League of Legends\\lockfile"])
    elif sys.platform == "darwin":
        paths.append("/Applications/League of Legends.app/Contents/LoL/lockfile")
    for p in paths:
        if os.path.exists(p): return p
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                'wmic process where "name=\'LeagueClientUx.exe\'" get commandline',
                shell=True, text=True, stderr=subprocess.DEVNULL)
            m = re.search(r'"([^"]*LeagueClientUx\.exe)"', out)
            if m:
                lf = os.path.join(os.path.dirname(m.group(1)), "lockfile")
                if os.path.exists(lf): return lf
        except Exception as e:
            print(f"Warning: lockfile lookup failed: {e}")
    return None


def connect_lcu(lockfile_path=None):
    path = lockfile_path or find_lockfile()
    if not path:
        print("  Could not find League client. Make sure it's OPEN.")
        return None, None
    with open(path) as f:
        parts = f.read().strip().split(":")
    if len(parts) < 5:
        print("  Invalid lockfile"); return None, None
    base = f"{parts[4]}://127.0.0.1:{parts[2]}"
    auth = ("riot", parts[3])
    try:
        r = requests.get(f"{base}/lol-summoner/v1/current-summoner",
                        auth=auth, verify=False, timeout=5)
        if r.status_code == 200:
            s = r.json()
            name = s.get("gameName", s.get("displayName", "?"))
            print(f"  Connected as: {name}")
            return base, auth
        print(f"  LCU error: {r.status_code}"); return None, None
    except Exception as e:
        print(f"  LCU connection attempt failed: {e}")
        print("  Can't connect to League client"); return None, None


# ── LCU Match History ────────────────────────────────────────

def fetch_all_matches(base_url, auth, max_count=500):
    seen_ids = set()
    all_games = []
    url = f"{base_url}/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex={max_count}"
    try:
        r = requests.get(url, auth=auth, verify=False, timeout=30)
        if r.status_code == 200:
            for g in r.json().get("games", {}).get("games", []):
                gid = g.get("gameId")
                if gid and gid not in seen_ids:
                    seen_ids.add(gid)
                    all_games.append(g)
            print(f"  Fetched {len(all_games)} unique matches")
    except Exception as e:
        print(f"  Fetch failed: {e}")
    if len(all_games) < 20:
        print("  Trying page-by-page...")
        for start in range(0, max_count, 20):
            url = f"{base_url}/lol-match-history/v1/products/lol/current-summoner/matches?begIndex={start}&endIndex={start+20}"
            try:
                r = requests.get(url, auth=auth, verify=False, timeout=15)
                if r.status_code != 200: break
                games = r.json().get("games", {}).get("games", [])
                if not games: break
                new = 0
                for g in games:
                    gid = g.get("gameId")
                    if gid and gid not in seen_ids:
                        seen_ids.add(gid); all_games.append(g); new += 1
                if new == 0: break
            except Exception as e:
                print(f"Warning: match page fetch failed: {e}")
                break
    return all_games


def fetch_detail(base_url, auth, game_id):
    try:
        r = requests.get(f"{base_url}/lol-match-history/v1/games/{game_id}",
                        auth=auth, verify=False, timeout=15)
        if r.status_code == 200: return r.json()
    except Exception as e:
        print(f"Warning: game detail fetch failed: {e}")
    return None


def load_champion_map():
    try:
        v = requests.get("https://ddragon.leagueoflegends.com/api/versions.json", timeout=10).json()
        data = requests.get(f"https://ddragon.leagueoflegends.com/cdn/{v[0]}/data/en_US/champion.json", timeout=10).json()
        return {int(d["key"]): d["name"] for d in data["data"].values()}
    except Exception as e:
        print(f"Warning: failed to load champion map from DDragon: {e}")
        return {}


def connect_sheet(creds, sheet):
    cred = Credentials.from_service_account_file(creds, scopes=SCOPES)
    gc = gspread.authorize(cred)
    if "docs.google.com" in sheet: return gc.open_by_url(sheet)
    return gc.open(sheet)


# ── Game Log Database ────────────────────────────────────────

def load_existing_game_ids(spreadsheet):
    """Load all already-logged game IDs from the _InhouseGameLog sheet."""
    try:
        ws = spreadsheet.worksheet("_InhouseGameLog")
        values = ws.get_all_values()
        existing = set()
        for row in values[1:]:  # skip header
            if row and row[0]:
                try: existing.add(int(row[0]))
                except Exception: existing.add(row[0])
        return existing
    except gspread.exceptions.WorksheetNotFound:
        return set()


def append_game_log(spreadsheet, new_records, logged_by="Unknown"):
    """Append new game records to the _InhouseGameLog sheet. Creates if needed."""
    try:
        ws = spreadsheet.worksheet("_InhouseGameLog")
    except gspread.exceptions.WorksheetNotFound:
        ws = sheets_retry(spreadsheet.add_worksheet, "_InhouseGameLog", rows=5000, cols=16)
        header = ["gameId", "timestamp", "player", "champion", "teamId",
                  "win", "kills", "deaths", "assists", "cs", "damage",
                  "gold", "vision", "role", "duration", "logged_by"]
        sheets_retry(ws.update, values=[header], range_name="A1")
        sheets_retry(ws.format, "A1:P1", {
            "backgroundColor": {"red": 0.09, "green": 0.14, "blue": 0.28},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
            "horizontalAlignment": "CENTER"})

    if not new_records:
        return

    # Find next empty row
    existing = ws.get_all_values()
    next_row = len(existing) + 1

    # Batch write new records
    rows = []
    for r in new_records:
        rows.append([
            r["gameId"], r["timestamp"], r["player"], r["champion"],
            r["teamId"], r["win"], r["kills"], r["deaths"], r["assists"],
            r["cs"], r["damage"], r["gold"], r["vision"], r["role"],
            r["duration"], r["logged_by"],
        ])

    # Write in chunks of 500 to avoid API limits
    for i in range(0, len(rows), 500):
        chunk = rows[i:i+500]
        sheets_retry(ws.update, values=chunk, range_name=f"A{next_row + i}")

    print(f"  Appended {len(rows)} new records to game log")
    _log_activity(spreadsheet, "INHOUSE", logged_by,
                  f"Logged {len(rows)} new games ({next_row - 1 + len(rows)} total)")


def load_full_game_log(spreadsheet):
    """Load all game records from the log."""
    try:
        ws = spreadsheet.worksheet("_InhouseGameLog")
        values = ws.get_all_values()
        records = []
        for row in values[1:]:
            if len(row) < 15 or not row[0]: continue
            try:
                records.append({
                    "gameId": row[0], "timestamp": row[1],
                    "player": row[2], "champion": row[3],
                    "teamId": int(row[4]) if row[4] else 0,
                    "win": row[5] == "True" or row[5] == "TRUE",
                    "kills": int(row[6]) if row[6] else 0,
                    "deaths": int(row[7]) if row[7] else 0,
                    "assists": int(row[8]) if row[8] else 0,
                    "cs": int(row[9]) if row[9] else 0,
                    "damage": int(row[10]) if row[10] else 0,
                    "gold": int(row[11]) if row[11] else 0,
                    "vision": int(row[12]) if row[12] else 0,
                    "role": row[13], "duration": row[14],
                })
            except (ValueError, IndexError): continue
        return records
    except Exception as e:
        print(f"Warning: failed to load game log: {e}")
        return []


def compute_stats_from_log(records):
    """Compute all stats from the game log records."""
    player_stats = defaultdict(lambda: {
        "games": 0, "wins": 0, "kills": 0, "deaths": 0, "assists": 0,
        "cs": 0, "damage": 0, "gold": 0,
        "champs": defaultdict(lambda: {"games": 0, "wins": 0, "kills": 0,
                                        "deaths": 0, "assists": 0, "damage": 0}),
        "roles": defaultdict(lambda: {"games": 0, "wins": 0}),
        "champ_roles": defaultdict(lambda: defaultdict(int)),
        "win_streak": 0, "best_streak": 0, "mvp_count": 0,
        "recent_wr": None,
    })
    # Keyed by player name; holds (timestamp, win) tuples for post-processing
    game_results: dict[str, list] = defaultdict(list)

    h2h = defaultdict(lambda: defaultdict(lambda: {
        "same_team": 0, "same_wins": 0, "vs": 0, "vs_wins": 0}))

    # Group records by gameId
    games = defaultdict(list)
    for r in records:
        games[r["gameId"]].append(r)

    total_games = 0
    for gid, players in games.items():
        if len(players) != 10: continue
        total_games += 1

        mvp_name = None
        mvp_score = None
        for p in players:
            name = p["player"]
            ps = player_stats[name]
            ps["games"] += 1
            ps["wins"] += 1 if p["win"] else 0
            ps["kills"] += p["kills"]
            ps["deaths"] += p["deaths"]
            ps["assists"] += p["assists"]
            ps["cs"] += p["cs"]
            ps["damage"] += p["damage"]
            ps["gold"] += p["gold"]

            game_results[name].append((p["timestamp"], p["win"]))

            ce = ps["champs"][p["champion"]]
            ce["games"] += 1
            ce["wins"] += 1 if p["win"] else 0
            ce["kills"] += p["kills"]
            ce["deaths"] += p["deaths"]
            ce["assists"] += p["assists"]
            ce["damage"] += p["damage"]

            role = p["role"]
            rs = ps["roles"][role]
            rs["games"] += 1
            rs["wins"] += 1 if p["win"] else 0

            ps["champ_roles"][p["champion"]][role] += 1

            # MVP: player with highest kills*3 + assists - deaths + damage/1000
            score = p["kills"] * 3 + p["assists"] - p["deaths"] + p["damage"] / 1000
            if mvp_score is None or score > mvp_score:
                mvp_score = score
                mvp_name = name

        if mvp_name:
            player_stats[mvp_name]["mvp_count"] += 1

        # Head-to-head
        t100 = [p for p in players if p["teamId"] == 100]
        t200 = [p for p in players if p["teamId"] == 200]

        for team in [t100, t200]:
            for i in range(len(team)):
                for j in range(i + 1, len(team)):
                    a, b = team[i]["player"], team[j]["player"]
                    h2h[a][b]["same_team"] += 1
                    h2h[b][a]["same_team"] += 1
                    if team[i]["win"]:
                        h2h[a][b]["same_wins"] += 1
                        h2h[b][a]["same_wins"] += 1

        for p1 in t100:
            for p2 in t200:
                a, b = p1["player"], p2["player"]
                h2h[a][b]["vs"] += 1
                h2h[b][a]["vs"] += 1
                if p1["win"]:
                    h2h[a][b]["vs_wins"] += 1
                else:
                    h2h[b][a]["vs_wins"] += 1

    # Post-process streaks and recent WR for each player
    for name, ps in player_stats.items():
        outcomes = [win for _, win in sorted(game_results[name], key=lambda x: x[0])]

        streak = 0
        for win in reversed(outcomes):
            if win:
                streak += 1
            else:
                break
        ps["win_streak"] = streak

        # Signed current streak: positive = win streak, negative = loss streak.
        # Surfaces "on fire" / "in slump" medallions in the UI.
        if outcomes:
            last = outcomes[-1]
            run = 0
            for w in reversed(outcomes):
                if w == last:
                    run += 1
                else:
                    break
            ps["current_streak"] = run if last else -run
        else:
            ps["current_streak"] = 0

        best = cur = 0
        for win in outcomes:
            cur = cur + 1 if win else 0
            best = max(best, cur)
        ps["best_streak"] = best

        recent = outcomes[-10:]
        ps["recent_wr"] = round(sum(recent) / len(recent) * 100, 1) if len(recent) >= 3 else None

    return dict(player_stats), dict(h2h), total_games


# ── Activity Log ─────────────────────────────────────────────

def _log_activity(spreadsheet, event_type, player_name, details):
    """Write one row to the _Activity sheet for cross-user feed visibility."""
    try:
        sheet_name = "_Activity"
        try:
            ws = spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            ws = sheets_retry(spreadsheet.add_worksheet, sheet_name, rows=500, cols=4)
            sheets_retry(ws.append_row, ["_ACTIVITY LOG", "", "", ""], value_input_option="RAW")
        sheets_retry(ws.append_row,
            [datetime.now().strftime("%Y-%m-%d %H:%M"), event_type, player_name or "", details],
            value_input_option="RAW")
    except Exception as e:
        print(f"  (Activity log write skipped: {e})")


# ── Main ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="In-House Custom Game Tracker")
    parser.add_argument("--sheet", required=True)
    parser.add_argument("--creds", default="credentials.json")
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--lol-path", default=None)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  In-House Custom Game Tracker")
    print(f"  Anyone can run this — games are tracked by ID")
    print(f"  Duplicates are automatically prevented")
    print(f"{'='*60}\n")

    champ_map = {}
    print("Loading champions...")
    champ_map = load_champion_map()
    if champ_map:
        print(f"  Loaded {len(champ_map)} champion names")

    print("\nConnecting to League client...")
    lf = args.lol_path
    if lf and not lf.endswith("lockfile"): lf = os.path.join(lf, "lockfile")
    base_url, auth = connect_lcu(lf)
    if not base_url: sys.exit(1)

    # Get current player name for logging
    try:
        r = requests.get(f"{base_url}/lol-summoner/v1/current-summoner",
                        auth=auth, verify=False, timeout=5)
        logged_by = r.json().get("gameName", "Unknown") if r.status_code == 200 else "Unknown"
    except Exception as e:
        print(f"Warning: could not fetch summoner name: {e}")
        logged_by = "Unknown"

    # Connect to Google Sheets early to check existing games
    print("\nConnecting to Google Sheets...")
    try:
        spreadsheet = connect_sheet(args.creds, args.sheet)
        print(f"  Connected to: {spreadsheet.title}")
    except Exception as e:
        print(f"Error: Could not connect to Google Sheets. Check your credentials file and sheet name.")
        print(f"  Detail: {e}")
        sys.exit(1)

    # Load existing game IDs to skip duplicates
    print("\nChecking for existing game data...")
    existing_ids = load_existing_game_ids(spreadsheet)
    print(f"  {len(existing_ids)} games already logged")

    # Fetch match history from client
    print(f"\nFetching match history from client...")
    all_games = fetch_all_matches(base_url, auth, args.count)
    print(f"  {len(all_games)} unique matches found")

    # Filter for customs
    cutoff = int((datetime.now() - timedelta(days=args.days)).timestamp() * 1000)
    customs = []
    queue_counts = defaultdict(int)
    for g in all_games:
        qid = g.get("queueId", -1)
        gt = g.get("gameType", "")
        queue_counts[f"{qid} ({g.get('gameMode','')}/{gt})"] += 1
        if g.get("gameCreation", 0) < cutoff: continue
        if qid == 0 or qid == 3130 or gt == "CUSTOM_GAME":
            gid = g.get("gameId")
            # Skip if already logged
            if gid in existing_ids:
                continue
            customs.append(g)

    print(f"\n  Queue breakdown:")
    for qt, cnt in sorted(queue_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"    {qt}: {cnt}")
    print(f"\n  {len(customs)} NEW custom games to process (skipped {len(existing_ids)} already logged)")

    if customs:
        # Fetch full details for new games
        print(f"\nFetching details for {len(customs)} new custom games...")
        role_map = {"TOP": "Top", "JUNGLE": "Jungle", "MIDDLE": "Mid",
                   "BOTTOM": "Bot", "UTILITY": "Support", "NONE": "Fill",
                   "UNKNOWN": "Fill", "": "Fill"}

        new_records = []
        seen = set()
        valid_count = 0
        for i, g in enumerate(customs):
            gid = g.get("gameId")
            if not gid or gid in seen: continue
            seen.add(gid)

            d = fetch_detail(base_url, auth, gid)
            if not d: continue

            participants = d.get("participants", [])
            identities = d.get("participantIdentities", [])

            if len(participants) != 10:
                print(f"  [{i+1}] Game {gid}: {len(participants)} players — skipped (not 5v5)")
                continue

            valid_count += 1
            duration = max(d.get("gameDuration", 1), 1)
            timestamp = datetime.fromtimestamp(
                d.get("gameCreation", 0) / 1000).strftime("%Y-%m-%d %H:%M")

            print(f"  [{valid_count}] Game {gid}: 5v5 custom on {timestamp}")

            for idx, p in enumerate(participants):
                pname = "Unknown"
                if idx < len(identities):
                    pl = identities[idx].get("player", {})
                    pname = pl.get("gameName") or pl.get("summonerName") or f"Player_{idx}"

                stats = p.get("stats", {})
                cid = p.get("championId", 0)
                cname = champ_map.get(cid, f"Champ#{cid}")
                lane = p.get("timeline", {}).get("lane", "UNKNOWN")
                role = role_map.get(lane.upper() if isinstance(lane, str) else "", "Fill")
                cs = stats.get("totalMinionsKilled", 0) + stats.get("neutralMinionsKilled", 0)

                new_records.append({
                    "gameId": gid,
                    "timestamp": timestamp,
                    "player": pname,
                    "champion": cname,
                    "teamId": p.get("teamId", 0),
                    "win": stats.get("win", False),
                    "kills": stats.get("kills", 0),
                    "deaths": stats.get("deaths", 0),
                    "assists": stats.get("assists", 0),
                    "cs": cs,
                    "damage": stats.get("totalDamageDealtToChampions", 0),
                    "gold": stats.get("goldEarned", 0),
                    "vision": stats.get("visionScore", 0),
                    "role": role,
                    "duration": round(duration / 60, 1) if duration > 300 else duration,
                    "logged_by": logged_by,
                })

        # Append new records to game log
        if new_records:
            print(f"\n  {valid_count} new 5v5 games, {len(new_records)} player records")
            print(f"\nSaving to game log...")
            append_game_log(spreadsheet, new_records, logged_by)
        else:
            print(f"\n  No new valid 5v5 games found")
    else:
        print("\n  No new games to process")

    # Rebuild stats from FULL game log (existing + new)
    print(f"\nRebuilding stats from complete game log...")
    all_records = load_full_game_log(spreadsheet)
    print(f"  {len(all_records)} total records in log")

    if not all_records:
        print("  No game data to analyze")
        sys.exit(0)

    player_stats, h2h, total_games = compute_stats_from_log(all_records)
    print(f"  {total_games} total 5v5 games, {len(player_stats)} unique players")

    # Write stats sheets
    print(f"\n{'='*60}")
    print("WRITING TO GOOGLE SHEETS")
    print(f"{'='*60}\n")

    write_overview(spreadsheet, player_stats, total_games, champ_map)
    write_h2h(spreadsheet, h2h, player_stats)
    write_inhouse_db(spreadsheet, player_stats)

    # Summary
    print(f"\n{'='*60}")
    print(f"IN-HOUSE SUMMARY — {total_games} total games")
    if customs:
        print(f"  ({len([r for r in (new_records if 'new_records' in dir() else [])]) // 10} new games added this run)")
    print(f"{'='*60}\n")
    print(f"{'Player':<20} {'Games':<6} {'W-L':<9} {'WR%':<7} {'KDA'}")
    print("_" * 52)
    for name, ps in sorted(player_stats.items(),
        key=lambda x: (x[1]["wins"]/max(x[1]["games"],1), x[1]["games"]), reverse=True):
        g = ps["games"]
        if g == 0: continue
        wr = round(ps["wins"]/g*100, 1)
        kda = round((ps["kills"]+ps["assists"])/max(ps["deaths"],1), 2)
        print(f"{name:<20} {g:<6} {ps['wins']}W-{g-ps['wins']}L   {wr:<7} {kda}")
    print(f"\nDone! Check 'In-House Stats' and 'In-House Head-to-Head' tabs.")
    print(f"Logged by: {logged_by}\n")


# ── Inhouse Database (for scouting/draft integration) ────────

def write_inhouse_db(spreadsheet, player_stats):
    try:
        spreadsheet.del_worksheet(spreadsheet.worksheet("_InhouseDB"))
    except gspread.exceptions.WorksheetNotFound:
        pass  # sheet doesn't exist yet, that's fine
    ws = sheets_retry(spreadsheet.add_worksheet, "_InhouseDB", rows=500, cols=13)
    rows = [["INHOUSE DATABASE - DO NOT EDIT", "", "", "", "", "",
             datetime.now().strftime("%Y-%m-%d %H:%M")],
            ["player", "champion", "games", "wins", "wr", "kda",
             "avg_kills", "avg_deaths", "avg_assists", "avg_damage",
             "total_games", "total_wr", "roles"]]
    for name, ps in player_stats.items():
        g = ps["games"]
        if g == 0: continue
        total_wr = round(ps["wins"] / g * 100, 1)
        for champ, cs in ps["champs"].items():
            cg = cs["games"]
            cwr = round(cs["wins"] / cg * 100, 1)
            ckda = round((cs["kills"] + cs["assists"]) / max(cs["deaths"], 1), 2)
            champ_role_data = ps.get("champ_roles", {}).get(champ, {})
            role_str = ";".join(f"{r}:{c}" for r, c in champ_role_data.items() if c > 0)
            rows.append([name, champ, cg, cs["wins"], cwr, ckda,
                         round(cs["kills"]/cg, 1), round(cs["deaths"]/cg, 1),
                         round(cs["assists"]/cg, 1), round(cs["damage"]/cg),
                         g, total_wr, role_str])
    sheets_retry(ws.update, values=rows, range_name="A1")
    print("  Inhouse DB saved (for scouting/draft)")


# ── Sheet Writers ────────────────────────────────────────────

DARK = {"red":0.11,"green":0.11,"blue":0.18}
HEADER = {"red":0.09,"green":0.14,"blue":0.28}
SECTION = {"red":0.13,"green":0.17,"blue":0.30}
GOLD = {"red":0.91,"green":0.72,"blue":0.29}
WHITE = {"red":1,"green":1,"blue":1}
LB = {"red":0.88,"green":0.92,"blue":0.98}
LG = {"red":0.85,"green":0.95,"blue":0.85}

def write_overview(spreadsheet, player_stats, total, champ_map):
    try:
        spreadsheet.del_worksheet(spreadsheet.worksheet("In-House Stats"))
    except gspread.exceptions.WorksheetNotFound:
        pass  # sheet doesn't exist yet, that's fine
    ws = sheets_retry(spreadsheet.add_worksheet, "In-House Stats", rows=300, cols=17)
    rows=[]; fmts=[]; merges=[]
    # 17 columns: # Player Games Wins Losses WinRate Last10 KDA AvgK AvgD AvgA AvgCS AvgDmg AvgGold CurStreak BestStreak MVPs
    NCOLS = 17
    pad=lambda d,n=NCOLS: d+[""]*(n-len(d))
    rn=lambda: len(rows)

    last_col = chr(64 + NCOLS)  # 'Q'

    rows.append(pad(["IN-HOUSE 5v5 STATS"])); merges.append(f"A{rn()}:{last_col}{rn()}")
    fmts.append((f"A{rn()}:{last_col}{rn()}", {"backgroundColor":DARK,"textFormat":{"bold":True,"fontSize":18,"foregroundColor":GOLD},"horizontalAlignment":"CENTER"}))
    ts=datetime.now().strftime("%Y-%m-%d %H:%M")
    rows.append(pad([f"{total} custom 5v5 games (all contributors combined)  |  Updated: {ts}"])); merges.append(f"A{rn()}:{last_col}{rn()}")
    fmts.append((f"A{rn()}:{last_col}{rn()}", {"backgroundColor":DARK,"textFormat":{"fontSize":11,"foregroundColor":WHITE},"horizontalAlignment":"CENTER"}))
    rows.append(pad([""]))

    rows.append(pad(["IN-HOUSE LEADERBOARD"])); merges.append(f"A{rn()}:{last_col}{rn()}")
    fmts.append((f"A{rn()}:{last_col}{rn()}", {"backgroundColor":SECTION,"textFormat":{"bold":True,"fontSize":14,"foregroundColor":GOLD},"horizontalAlignment":"CENTER"}))
    rows.append(pad(["#","Player","Games","Wins","Losses","Win Rate","Last 10","KDA","Avg K","Avg D","Avg A","Avg CS","Avg Dmg","Avg Gold","Cur Streak","Best Streak","MVPs"]))
    fmts.append((f"A{rn()}:{last_col}{rn()}", {"backgroundColor":HEADER,"textFormat":{"bold":True,"fontSize":10,"foregroundColor":WHITE},"horizontalAlignment":"CENTER"}))

    sp=sorted(player_stats.items(), key=lambda x:(x[1]["wins"]/max(x[1]["games"],1),x[1]["games"]), reverse=True)
    for i,(name,ps) in enumerate(sp,1):
        g=ps["games"]
        if g==0: continue
        wr=round(ps["wins"]/g*100,1)
        kda=round((ps["kills"]+ps["assists"])/max(ps["deaths"],1),2)
        recent_wr = ps.get("recent_wr")
        last10 = f"{int(recent_wr)}%" if recent_wr is not None else "—"
        bg=LG if i<=3 else(LB if i%2==0 else {"red":1,"green":1,"blue":1})
        rows.append(pad([i,name,g,ps["wins"],g-ps["wins"],f"{wr}%",last10,kda,
            round(ps["kills"]/g,1),round(ps["deaths"]/g,1),round(ps["assists"]/g,1),
            round(ps["cs"]/g),f"{round(ps['damage']/g):,}",f"{round(ps['gold']/g):,}",
            ps.get("win_streak",0),ps.get("best_streak",0),ps.get("mvp_count",0)]))
        fmts.append((f"A{rn()}:{last_col}{rn()}", {"backgroundColor":bg,"textFormat":{"fontSize":11,"bold":i<=3},"horizontalAlignment":"CENTER"}))

    rows.append(pad([""])); rows.append(pad([""]))
    rows.append(pad(["IN-HOUSE CHAMPION STATS"])); merges.append(f"A{rn()}:{last_col}{rn()}")
    fmts.append((f"A{rn()}:{last_col}{rn()}", {"backgroundColor":SECTION,"textFormat":{"bold":True,"fontSize":14,"foregroundColor":GOLD},"horizontalAlignment":"CENTER"}))

    for name,ps in sp:
        if ps["games"]==0: continue
        wr=round(ps["wins"]/ps["games"]*100,1)
        rows.append(pad([f"{name}  -  {ps['games']} games  |  {wr}% WR"])); merges.append(f"A{rn()}:{last_col}{rn()}")
        fmts.append((f"A{rn()}:{last_col}{rn()}", {"backgroundColor":{"red":0.2,"green":0.3,"blue":0.5},"textFormat":{"bold":True,"fontSize":12,"foregroundColor":WHITE},"horizontalAlignment":"CENTER"}))
        rows.append(pad(["Champion","Games","Wins","Losses","WR%","KDA","Avg K","Avg D","Avg A","Avg Dmg"]))
        fmts.append((f"A{rn()}:J{rn()}", {"backgroundColor":HEADER,"textFormat":{"bold":True,"fontSize":10,"foregroundColor":WHITE},"horizontalAlignment":"CENTER"}))
        for j,(ch,cs) in enumerate(sorted(ps["champs"].items(), key=lambda x:x[1]["games"], reverse=True)):
            cg=cs["games"]; cwr=round(cs["wins"]/cg*100,1); ckda=round((cs["kills"]+cs["assists"])/max(cs["deaths"],1),2)
            bg=LB if j%2==0 else {"red":1,"green":1,"blue":1}
            rows.append(pad([ch,cg,cs["wins"],cg-cs["wins"],f"{cwr}%",ckda,
                round(cs["kills"]/cg,1),round(cs["deaths"]/cg,1),round(cs["assists"]/cg,1),f"{round(cs['damage']/cg):,}"]))
            fmts.append((f"A{rn()}:J{rn()}", {"backgroundColor":bg,"textFormat":{"fontSize":11},"horizontalAlignment":"CENTER"}))
        rows.append(pad([""]))

    rows.append(pad([""])); rows.append(pad([""]))
    rows.append(pad(["IN-HOUSE ROLE PERFORMANCE"])); merges.append(f"A{rn()}:{last_col}{rn()}")
    fmts.append((f"A{rn()}:{last_col}{rn()}", {"backgroundColor":SECTION,"textFormat":{"bold":True,"fontSize":14,"foregroundColor":GOLD},"horizontalAlignment":"CENTER"}))
    rows.append(pad(["Player","Top","","Jungle","","Mid","","Bot","","Support",""]))
    fmts.append((f"A{rn()}:K{rn()}", {"backgroundColor":HEADER,"textFormat":{"bold":True,"fontSize":10,"foregroundColor":WHITE},"horizontalAlignment":"CENTER"}))
    rows.append(pad(["","G","WR%","G","WR%","G","WR%","G","WR%","G","WR%"]))
    fmts.append((f"A{rn()}:K{rn()}", {"backgroundColor":HEADER,"textFormat":{"bold":True,"fontSize":9,"foregroundColor":WHITE},"horizontalAlignment":"CENTER"}))
    for name,ps in sp:
        if ps["games"]==0: continue
        rd=[name]
        for role in ["Top","Jungle","Mid","Bot","Support"]:
            rs=ps["roles"].get(role,{"games":0,"wins":0}); rg=rs["games"]
            rd.extend([rg if rg>0 else "-", f"{round(rs['wins']/rg*100)}%" if rg>0 else "-"])
        rows.append(pad(rd))
        fmts.append((f"A{rn()}:K{rn()}", {"backgroundColor":LB,"textFormat":{"fontSize":11},"horizontalAlignment":"CENTER"}))

    sheets_retry(ws.update, values=rows, range_name="A1")
    for m in merges:
        sheets_retry(ws.merge_cells, m)
    col_px=[50,120,60,55,60,70,65,55,60,60,60,70,95,90,80,85,55]
    reqs=[{"updateDimensionProperties":{"range":{"sheetId":ws.id,"dimension":"COLUMNS","startIndex":ci,"endIndex":ci+1},"properties":{"pixelSize":px},"fields":"pixelSize"}} for ci,px in enumerate(col_px)]
    reqs.append({"updateDimensionProperties":{"range":{"sheetId":ws.id,"dimension":"ROWS","startIndex":0,"endIndex":1},"properties":{"pixelSize":50},"fields":"pixelSize"}})
    sheets_retry(spreadsheet.batch_update, {"requests":reqs})
    for i in range(0,len(fmts),15):
        sheets_retry(ws.batch_format, [{"range":r,"format":f} for r,f in fmts[i:i+15]])
    print("  In-House Stats written")


def write_h2h(spreadsheet, h2h, player_stats):
    try:
        spreadsheet.del_worksheet(spreadsheet.worksheet("In-House Head-to-Head"))
    except gspread.exceptions.WorksheetNotFound:
        pass  # sheet doesn't exist yet, that's fine
    active=sorted([n for n,ps in player_stats.items() if ps["games"]>0])
    n=len(active)
    ws=sheets_retry(spreadsheet.add_worksheet, "In-House Head-to-Head", rows=n*2+15, cols=n+3)
    rows=[]; fmts=[]
    pad_n=n+2; ec=chr(64+min(pad_n,26))
    pad=lambda d: d+[""]*(pad_n-len(d))
    rn=lambda: len(rows)

    rows.append(pad(["IN-HOUSE HEAD-TO-HEAD"]))
    fmts.append((f"A{rn()}:{ec}{rn()}", {"backgroundColor":DARK,"textFormat":{"bold":True,"fontSize":16,"foregroundColor":GOLD},"horizontalAlignment":"CENTER"}))
    rows.append(pad([""]))

    for title, ks, kw in [("TEAMMATE WIN RATE","same_team","same_wins"),("HEAD-TO-HEAD (opposing)","vs","vs_wins")]:
        rows.append(pad([title]))
        fmts.append((f"A{rn()}:{ec}{rn()}", {"backgroundColor":SECTION,"textFormat":{"bold":True,"fontSize":13,"foregroundColor":GOLD},"horizontalAlignment":"CENTER"}))
        rows.append(pad([""]+active))
        fmts.append((f"A{rn()}:{chr(64+n+1)}{rn()}", {"backgroundColor":HEADER,"textFormat":{"bold":True,"fontSize":9,"foregroundColor":WHITE},"horizontalAlignment":"CENTER"}))
        for a in active:
            rd=[a]
            for b in active:
                if a==b: rd.append("-")
                else:
                    d=h2h.get(a,{}).get(b,{ks:0,kw:0}); t=d.get(ks,0); w=d.get(kw,0)
                    rd.append(f"{round(w/t*100)}% ({t})" if t>0 else "-")
            rows.append(pad(rd))
            fmts.append((f"A{rn()}:{chr(64+n+1)}{rn()}", {"backgroundColor":LB,"textFormat":{"fontSize":10},"horizontalAlignment":"CENTER"}))
            fmts.append((f"A{rn()}", {"backgroundColor":HEADER,"textFormat":{"bold":True,"fontSize":9,"foregroundColor":WHITE}}))
        rows.append(pad([""])); rows.append(pad([""]))

    sheets_retry(ws.update, values=rows, range_name="A1")
    reqs=[{"updateDimensionProperties":{"range":{"sheetId":ws.id,"dimension":"COLUMNS","startIndex":0,"endIndex":1},"properties":{"pixelSize":100},"fields":"pixelSize"}}]
    for ci in range(1,n+1):
        reqs.append({"updateDimensionProperties":{"range":{"sheetId":ws.id,"dimension":"COLUMNS","startIndex":ci,"endIndex":ci+1},"properties":{"pixelSize":85},"fields":"pixelSize"}})
    sheets_retry(spreadsheet.batch_update, {"requests":reqs})
    for i in range(0,len(fmts),15):
        sheets_retry(ws.batch_format, [{"range":r,"format":f} for r,f in fmts[i:i+15]])
    print("  Head-to-Head written")


if __name__ == "__main__":
    main()
