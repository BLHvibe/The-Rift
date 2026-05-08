"""
Live data reader for The Rift.
Reads parsed data from Google Sheets tabs after a fetch_ranks run.
All functions return plain dicts/lists — no DPG dependencies.
"""
import threading
from collections import defaultdict
from data.config import load_config

# ---------------------------------------------------------------------------
# Shared live data — written by background loader, read by UI tabs
# ---------------------------------------------------------------------------
class LiveData:
    def __init__(self):
        self.rankings       = []   # list of player dicts for rankings tab
        self.scout          = []   # list of player dicts for scout tab
        self.inhouse        = []   # list of player dicts for inhouse tab
        self.inhouse_champs = {}   # player_name → list of champ dicts
        self.primary_roles  = {}   # player_name → "TOP"/"JGL"/"MID"/"BOT"/"SUP"
        self.loaded     = False
        self.loading    = False
        self.error      = None
        self._lock      = threading.Lock()

    def set(self, rankings, scout, inhouse, inhouse_champs, primary_roles=None):
        with self._lock:
            self.rankings        = rankings
            self.scout           = scout
            self.inhouse         = inhouse
            self.inhouse_champs  = inhouse_champs
            self.primary_roles   = primary_roles or {}
            self.loaded          = True
            self.loading         = False
            self.error           = None

    def set_error(self, msg):
        with self._lock:
            self.loading = False
            self.error   = msg


live = LiveData()


# ---------------------------------------------------------------------------
# Background loader
# ---------------------------------------------------------------------------

def load_live_data(on_done=None, on_error=None):
    """
    Kick off a background thread to read sheets data.
    on_done() is called on the main thread when data is ready.
    on_error(msg) is called on failure.
    """
    if live.loading:
        return
    live.loading = True
    live.error   = None

    def _bg():
        try:
            cfg = load_config()
            rankings, scout, inhouse, inhouse_champs, primary_roles = _read_sheets(cfg)
            live.set(rankings, scout, inhouse, inhouse_champs, primary_roles)
            if on_done:
                on_done()
        except Exception as e:
            live.set_error(str(e))
            if on_error:
                on_error(str(e))

    threading.Thread(target=_bg, daemon=True, name="live_data_loader").start()


def _read_sheets(cfg):
    import gspread
    from google.oauth2.service_account import Credentials

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(
        cfg.get("creds_path", "credentials.json"), scopes=SCOPES)
    gc   = gspread.authorize(creds)
    sh   = gc.open_by_url(cfg["sheet_url"]) if cfg["sheet_url"].startswith("http") \
           else gc.open(cfg["sheet_url"])

    rankings                  = _read_final_rankings(sh)
    scout                     = _read_player_stats(sh, rankings)
    known_names               = {r["name"] for r in rankings}
    inhouse, ih_ch, prim_roles = _read_inhouse(sh, known_names)
    return rankings, scout, inhouse, ih_ch, prim_roles


# ---------------------------------------------------------------------------
# Final Rankings tab → rankings
# ---------------------------------------------------------------------------

def _read_final_rankings(sh):
    """
    Read 'Final Rankings' tab — the authoritative post-processed rankings.
    Columns: rank, name, avg_tier, tier_score, rank_score_raw, rank_score, final, rating
    Falls back to 'Rank Data' tab if Final Rankings doesn't exist.
    """
    try:
        ws = sh.worksheet("Final Rankings")
    except Exception:
        return _read_rank_data(sh)

    rows = ws.get_all_values()
    if len(rows) < 2:
        return _read_rank_data(sh)

    results = []
    pos = 0
    for row in rows[1:]:
        if len(row) < 8:
            continue
        r = [str(c).strip() for c in row[:8]]
        rank_str, name, avg_tier, tier_score, rank_score_raw, rank_score, final, rating = r

        if not name or name.lower() in ("name", "player"):
            continue
        # Stop at blank rank or separator rows
        if not rank_str and not name:
            continue
        # Skip rows that are clearly non-player (headers re-appearing, etc.)
        if rank_str.lower() in ("rank", "#", ""):
            continue

        try:
            ts = float(tier_score) if tier_score else 0.0
            rs = float(rank_score) if rank_score else 0.0
        except ValueError:
            ts, rs = 0.0, 0.0

        # Skip placeholder rows with no signal
        if ts <= 10.0 and rs <= 0.0 and not avg_tier:
            continue

        pos += 1
        tier = _tier_from_avg(avg_tier)
        results.append({
            "rank":       pos,
            "name":       name,
            "tier":       tier,
            "avg_tier":   avg_tier,
            "tier_score": tier_score,
            "rank_score": rank_score,
            "final_score":final,
            "rating":     rating or "?",
            "score":      final,  # final = tier_score + rank_score
        })

    return results


def _read_rank_data(sh):
    """
    Fallback: read 'Rank Data' tab when Final Rankings is unavailable.
    """
    try:
        ws = sh.worksheet("Rank Data")
    except Exception:
        return []

    rows = ws.get_all_values()
    if len(rows) < 3:
        return []

    results = []
    for row in rows[2:]:
        if len(row) < 9 or not row[0]:
            continue
        try:
            tier_raw = str(row[2]).strip()
            div_raw  = str(row[3]).strip()
            tier = _normalise_tier(tier_raw)
            games = int(float(row[10])) if row[10] else 0
            wins  = int(float(row[5]))  if row[5]  else 0
            losses= int(float(row[6]))  if row[6]  else 0
            wr    = round(wins / games * 100, 1) if games > 0 else 0
            score = str(row[7]) if row[7] else "0"
            results.append({
                "rank":       int(row[0]),
                "name":       str(row[1]).strip(),
                "tier":       tier,
                "avg_tier":   tier,
                "tier_score": str(int(float(row[7]))) if row[7] else "0",
                "rank_score": str(int(float(row[8]))) if row[8] else "0",
                "final_score":score,
                "rating":     "?",
                "score":      score,
                "wins":       wins,
                "losses":     losses,
                "wr":         wr,
                "games":      games,
            })
        except (ValueError, IndexError):
            continue

    results.sort(key=lambda r: r["rank"])
    return results


def _tier_from_avg(avg_tier_str):
    """Convert a numeric avg_tier (e.g. '5.08') to a display tier name."""
    try:
        v = float(avg_tier_str)
    except (ValueError, TypeError):
        return _normalise_tier(str(avg_tier_str))
    # Approximate mapping: Iron=1, Bronze=2, Silver=3, Gold=4, Emerald=5,
    # Platinum=6 (pre-Emerald legacy), Diamond=7, Master=8, GM=9, Chall=10
    if v >= 9.5:  return "Challenger"
    if v >= 8.5:  return "Grandmaster"
    if v >= 7.5:  return "Master"
    if v >= 6.5:  return "Diamond"
    if v >= 5.5:  return "Emerald"
    if v >= 4.5:  return "Platinum"
    if v >= 3.5:  return "Gold"
    if v >= 2.5:  return "Silver"
    if v >= 1.5:  return "Bronze"
    return "Iron"


def _normalise_tier(raw):
    mapping = {
        "challenger":"Challenger","grandmaster":"Grandmaster","master":"Master",
        "diamond":"Diamond","emerald":"Emerald","platinum":"Platinum",
        "gold":"Gold","silver":"Silver","bronze":"Bronze","iron":"Iron",
        "unranked":"Unranked",
    }
    return mapping.get(raw.lower(), raw.title())


# ---------------------------------------------------------------------------
# Player Stats tab → extended scout data
# ---------------------------------------------------------------------------

def _read_player_stats(sh, rankings):
    """
    Read 'Player Stats' tab to get top champions, recent KDA, form.
    Merges with rankings data into the scout row format.
    """
    rank_by_name = {r["name"]: r for r in rankings}
    stats_by_name = {}

    try:
        ws   = sh.worksheet("Player Stats")
        rows = ws.get_all_values()
        # Row 0 = title, Row 1 = header, Row 2+ = data
        # Cols: #, Player, WR%, TopChamp1, Mastery1, TopChamp2, Mastery2,
        #       TopChamp3, Mastery3, Recent W-L, Recent WR%, Avg KDA,
        #       Avg Kills, Avg Deaths, Avg Assists, Hot/Cold
        for row in rows[2:]:
            if len(row) < 12 or not row[1]:
                continue
            name = str(row[1]).strip()
            top_champs = []
            for i in range(3):
                cn = str(row[3 + i*2]).strip() if len(row) > 3+i*2 else ""
                if cn and cn != "-":
                    top_champs.append(cn)
            try:
                kda = float(row[11]) if row[11] else 0.0
            except ValueError:
                kda = 0.0
            form = str(row[15]).strip().upper() if len(row) > 15 else "MIXED"
            if form not in ("HOT","COLD","MIXED"):
                form = "MIXED"
            stats_by_name[name] = {
                "top_champs": top_champs,
                "kda":        kda,
                "form":       form,
            }
    except Exception:
        pass

    # Build scout rows combining both sources
    scout = []
    for r in rankings:
        name  = r["name"]
        stats = stats_by_name.get(name, {})
        # Use final_score (tier+rank) to match the power rankings page
        try:
            score = float(r.get("final_score") or r.get("score") or 0)
        except (ValueError, TypeError):
            score = 0.0
        try:
            wr = int(float(r.get("wr") or 0))
        except (ValueError, TypeError):
            wr = 0
        scout.append({
            "name":        name,
            "tier":        r["tier"],
            "score":       score,
            "final_score": r.get("final_score", r.get("score", 0)),
            "tier_score":  r.get("tier_score", ""),
            "rank_score":  r.get("rank_score", ""),
            "rating":      r.get("rating", "?"),
            "rank":        r.get("rank", 0),
            "wr":          wr,
            "kda":         round(stats.get("kda", 0.0), 1),
            "games":       r.get("games", 0),
            "top_champs":  stats.get("top_champs", []),
            "form":        stats.get("form", "MIXED"),
        })
    return scout


# ---------------------------------------------------------------------------
# Inhouse game log → leaderboard + champion breakdown
# ---------------------------------------------------------------------------

def _read_inhouse(sh, known_names=None):
    """
    Read '_InhouseGameLog' tab and compute leaderboard + per-player champ stats.
    known_names: optional set of display names from Final Rankings — used to
    filter out log entries from players not in the group roster.
    """
    records = []
    try:
        ws   = sh.worksheet("_InhouseGameLog")
        rows = ws.get_all_values()
        # Header: gameId, timestamp, player, champion, teamId, win,
        #         kills, deaths, assists, cs, damage, gold, vision, role, duration, logged_by
        for row in rows[1:]:
            if len(row) < 6 or not row[0]:
                continue
            try:
                role_raw = str(row[13]).strip().upper() if len(row) > 13 and row[13] else ""
                records.append({
                    "gameId":   row[0],
                    "player":   str(row[2]).strip(),
                    "champion": str(row[3]).strip(),
                    "teamId":   int(row[4]) if row[4] else 0,
                    "win":      str(row[5]).upper() in ("TRUE","1"),
                    "kills":    int(float(row[6])) if len(row)>6 and row[6] else 0,
                    "deaths":   int(float(row[7])) if len(row)>7 and row[7] else 0,
                    "assists":  int(float(row[8])) if len(row)>8 and row[8] else 0,
                    "damage":   int(float(row[10])) if len(row)>10 and row[10] else 0,
                    "gold":     int(float(row[11])) if len(row)>11 and row[11] else 0,
                    "role":     role_raw if role_raw in ("TOP","JGL","MID","BOT","SUP") else "",
                })
            except (ValueError, IndexError):
                continue
    except Exception:
        pass

    if not records:
        return [], {}, {}

    # Only count full 5v5 games (10 players per gameId)
    games_by_id = defaultdict(list)
    for r in records:
        games_by_id[r["gameId"]].append(r)

    valid_records = []
    for gid, recs in games_by_id.items():
        if len(recs) == 10:
            valid_records.extend(recs)

    if not valid_records:
        return [], {}, {}

    # Per-player aggregates
    player_agg = defaultdict(lambda: {
        "games": set(), "wins": 0, "kills": 0, "deaths": 0,
        "assists": 0, "damage": 0, "gold": 0,
    })
    champ_agg = defaultdict(lambda: defaultdict(lambda: {
        "games": 0, "wins": 0, "kills": 0, "deaths": 0,
        "assists": 0, "damage": 0,
    }))
    role_freq = defaultdict(lambda: defaultdict(int))

    for r in valid_records:
        name = r["player"]
        pa   = player_agg[name]
        pa["games"].add(r["gameId"])
        if r["win"]:
            pa["wins"] += 1
        pa["kills"]   += r["kills"]
        pa["deaths"]  += r["deaths"]
        pa["assists"] += r["assists"]
        pa["damage"]  += r["damage"]
        pa["gold"]    += r["gold"]

        ca = champ_agg[name][r["champion"]]
        ca["games"]   += 1
        ca["wins"]    += 1 if r["win"] else 0
        ca["kills"]   += r["kills"]
        ca["deaths"]  += r["deaths"]
        ca["assists"] += r["assists"]
        ca["damage"]  += r["damage"]

        if r.get("role"):
            role_freq[name][r["role"]] += 1

    leaderboard = []
    inhouse_champs = {}

    for name, pa in player_agg.items():
        g = len(pa["games"])
        if g == 0:
            continue
        w = pa["wins"]
        l = g - w
        wr = round(w / g * 100, 1)
        kda = round((pa["kills"] + pa["assists"]) / max(pa["deaths"], 1), 1)
        avg_dmg = round(pa["damage"] / g)
        avg_gold= round(pa["gold"] / g)

        leaderboard.append({
            "player":  name,
            "games":   g,
            "wins":    w,
            "losses":  l,
            "wr":      f"{wr}%",
            "kda":     kda,
            "cs_min":  "—",
            "damage":  f"{avg_dmg:,}",
            "gold":    f"{avg_gold:,}",
        })

        # Champion breakdown
        champs = []
        for champ_name, ca in champ_agg[name].items():
            cg = ca["games"]
            if cg == 0:
                continue
            champs.append({
                "champ":   champ_name,
                "games":   cg,
                "wins":    ca["wins"],
                "losses":  cg - ca["wins"],
                "wr":      f"{round(ca['wins']/cg*100,1)}%",
                "kda":     round((ca["kills"]+ca["assists"])/max(ca["deaths"],1),1),
                "kills":   round(ca["kills"]/cg, 1),
                "deaths":  round(ca["deaths"]/cg, 1),
                "assists": round(ca["assists"]/cg, 1),
                "damage":  f"{round(ca['damage']/cg):,}",
            })
        champs.sort(key=lambda x: x["games"], reverse=True)
        inhouse_champs[name] = champs

    # Primary role per player (most-played role in inhouse games)
    primary_roles = {}
    for name, roles in role_freq.items():
        if roles:
            primary_roles[name] = max(roles, key=roles.get)

    # Filter to known roster players if provided
    if known_names:
        leaderboard    = [p for p in leaderboard    if p["player"] in known_names]
        inhouse_champs = {k: v for k, v in inhouse_champs.items() if k in known_names}
        primary_roles  = {k: v for k, v in primary_roles.items()  if k in known_names}

    # Sort by win rate desc, then games desc as tiebreaker
    def _wr_key(p):
        try:
            return float(str(p["wr"]).replace("%", ""))
        except (ValueError, TypeError):
            return 0.0

    leaderboard.sort(key=lambda p: (_wr_key(p), p["games"]), reverse=True)
    for i, p in enumerate(leaderboard):
        p["rank"] = i + 1

    return leaderboard, inhouse_champs, primary_roles


# ---------------------------------------------------------------------------
# Shared gspread connection helper
# ---------------------------------------------------------------------------

def _gspread_connect(cfg):
    """Return an authenticated gspread Spreadsheet object from config dict."""
    import gspread
    from google.oauth2.service_account import Credentials
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(
        cfg.get("creds_path", "credentials.json"), scopes=SCOPES)
    gc  = gspread.authorize(creds)
    url = cfg.get("sheet_url", "")
    return gc.open_by_url(url) if url.startswith("http") else gc.open(url)


# ---------------------------------------------------------------------------
# Phase 1 — Draft win prediction (Rank History + live inhouse stats)
# ---------------------------------------------------------------------------

def load_prediction_data(blue_names, red_names, on_done=None):
    """
    Background read of 'Rank History' sheet.
    Combines with live.inhouse (already loaded) for inhouse WR weighting.
    Calls on_done(prediction_dict) when complete.
    prediction_dict keys: blue_prob, red_prob, strengths, rank_vals, inhouse_stats
    On failure, blue_prob / red_prob will be 50.0 and 'error' key will be set.
    """
    def _bg():
        cfg = load_config()
        rank_vals = {}
        try:
            sh        = _gspread_connect(cfg)
            rank_vals = _read_rank_history_latest(sh)
        except Exception:
            pass  # silent fallback — local score ratio used instead

        # Use already-loaded live.inhouse rather than re-reading "In-House Stats"
        inhouse_stats = {}
        for p in live.inhouse:
            name  = p.get("player", "")
            games = p.get("games", 0)
            wins  = p.get("wins", 0)
            if name and games > 0:
                inhouse_stats[name] = {"games": games, "wr": wins / games}

        all_names = list(blue_names) + list(red_names)
        strengths = {n: _player_strength(n, rank_vals, inhouse_stats)
                     for n in all_names}

        t1 = sum(strengths.get(n, 0.5) for n in blue_names) / max(len(list(blue_names)), 1)
        t2 = sum(strengths.get(n, 0.5) for n in red_names)  / max(len(list(red_names)),  1)
        total   = t1 + t2
        t1_prob = round(t1 / total * 100, 1) if total > 0 else 50.0
        t1_prob = max(25.0, min(75.0, t1_prob))

        result = {
            "blue_prob":     t1_prob,
            "red_prob":      round(100 - t1_prob, 1),
            "strengths":     strengths,
            "rank_vals":     rank_vals,
            "inhouse_stats": inhouse_stats,
        }
        if not rank_vals:
            result["error"] = "Rank History sheet unavailable — using score ratio"
        if on_done:
            on_done(result)

    threading.Thread(target=_bg, daemon=True, name="draft_prediction").start()


def _read_rank_history_latest(sh):
    """
    Return {player_name: rank_value} from the most recent row of 'Rank History'.
    Row 0 may be a title; Row 1 = header with player names; Row 2+ = data.
    Last data row = most recent snapshot.
    """
    try:
        ws   = sh.worksheet("Rank History")
        rows = ws.get_all_values()
        if len(rows) < 3:
            return {}
        header   = rows[1]
        last_row = rows[-1]
        result   = {}
        for ci, col_name in enumerate(header[1:], start=1):
            col_name = str(col_name).strip()
            if col_name and ci < len(last_row) and last_row[ci]:
                try:
                    result[col_name] = float(last_row[ci])
                except ValueError:
                    pass
        return result
    except Exception:
        return {}


def _player_strength(name, rank_vals, inhouse_stats):
    """
    Composite strength score in [0, 1].
    65% from rank position (normalised to ~30-player group),
    35% from inhouse WR (confidence-weighted by games played).
    """
    rv        = rank_vals.get(name, 13.0)   # default = mid-table of ~25 players
    rank_norm = rv / 31.0
    ih = inhouse_stats.get(name)
    if ih and ih["games"] >= 1:
        conf    = min(ih["games"] / 10.0, 1.0)
        wr_norm = ih["wr"] * conf + 0.5 * (1 - conf)
    else:
        wr_norm = 0.5
    return 0.65 * rank_norm + 0.35 * wr_norm


# ---------------------------------------------------------------------------
# Phase 2 — Draft sheet write + subprocess + result parser
# ---------------------------------------------------------------------------

_DRAFT_SCRIPT_PATH = None   # resolved once and cached


def _find_draft_script():
    """
    Locate fetch_ranks_gsheets.py.
    Searches: parent of the_rift/, directory of running .exe, cwd.
    """
    global _DRAFT_SCRIPT_PATH
    if _DRAFT_SCRIPT_PATH:
        return _DRAFT_SCRIPT_PATH
    import os, sys
    here = os.path.dirname(os.path.abspath(__file__))   # the_rift/data/
    candidates = [
        os.path.normpath(os.path.join(here, "..", "..", "fetch_ranks_gsheets.py")),
        os.path.normpath(os.path.join(os.path.dirname(sys.executable), "fetch_ranks_gsheets.py")),
        os.path.normpath(os.path.join(os.getcwd(), "fetch_ranks_gsheets.py")),
    ]
    for c in candidates:
        if os.path.exists(c):
            _DRAFT_SCRIPT_PATH = c
            return c
    return None


def write_draft_picks(blue_players, red_players, on_done=None, on_error=None):
    """
    Write blue/red team selections to 'Draft Tool' sheet (rows 6–10).
    Columns A–C = slot#, player, tier/rank  |  H–J = slot#, player, tier/rank
    blue_players / red_players: list of dicts with keys 'name', 'tier', 'role'.
    on_done() called on success; on_error(msg) called on failure.
    """
    def _bg():
        try:
            cfg = load_config()
            sh  = _gspread_connect(cfg)
            ws  = sh.worksheet("Draft Tool")
            for i in range(5):
                row = i + 6
                bp  = blue_players[i] if i < len(blue_players) else {}
                rp  = red_players[i]  if i < len(red_players)  else {}
                ws.update(values=[[i + 1, bp.get("name",""), bp.get("tier","")]],
                          range_name=f"A{row}:C{row}")
                ws.update(values=[[i + 1, rp.get("name",""), rp.get("tier","")]],
                          range_name=f"H{row}:J{row}")
            if on_done:
                on_done()
        except Exception as e:
            if on_error:
                on_error(str(e))

    threading.Thread(target=_bg, daemon=True, name="draft_write").start()


def run_draft_subprocess(on_done=None, on_error=None, on_line=None):
    """
    Run `fetch_ranks_gsheets.py --draft` as a subprocess.
    on_done(sh)   — called with an open Spreadsheet object when exit code == 0
    on_error(msg) — called on failure / script not found / timeout
    on_line(text) — optional, called for each stdout line (for console streaming)
    """
    import subprocess, sys, os

    script = _find_draft_script()
    if not script:
        if on_error:
            on_error("fetch_ranks_gsheets.py not found — rich draft analysis unavailable.")
        return

    cfg = load_config()
    key = cfg.get("api_key", "")
    if not key:
        if on_error:
            on_error("No API key set — add your Riot API key in Settings.")
        return

    py  = sys.executable   # use same Python that's running the app
    cmd = [
        py, script,
        "--key",     key,
        "--sheet",   cfg.get("sheet_url", ""),
        "--creds",   cfg.get("creds_path", "credentials.json"),
        "--region",  cfg.get("region",  "na1"),
        "--routing", cfg.get("routing", "americas"),
        "--draft",
    ]

    def _bg():
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
                cwd=os.path.dirname(script),
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            for line in iter(proc.stdout.readline, ""):
                if on_line:
                    on_line(line.rstrip())
            try:
                proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                if on_error:
                    on_error("Draft subprocess timed out after 120 s.")
                return
            if proc.returncode != 0:
                if on_error:
                    on_error(f"Draft subprocess exited with code {proc.returncode}.")
                return
            # Re-open sheet so caller can read results
            try:
                sh = _gspread_connect(cfg)
                if on_done:
                    on_done(sh)
            except Exception as e:
                if on_error:
                    on_error(f"Couldn't reconnect to sheet after draft: {e}")
        except Exception as e:
            if on_error:
                on_error(f"Draft subprocess error: {e}")

    threading.Thread(target=_bg, daemon=True, name="draft_subprocess").start()


def read_draft_results(sh, on_done=None, on_error=None):
    """
    Read and parse the 'Draft Tool' sheet after the subprocess has written results.
    Calls on_done(results_dict) or on_error(msg) from a background thread.
    """
    def _bg():
        try:
            ws   = sh.worksheet("Draft Tool")
            data = _parse_draft_sheet(ws.get_all_values())
            if on_done:
                on_done(data)
        except Exception as e:
            if on_error:
                on_error(str(e))

    threading.Thread(target=_bg, daemon=True, name="draft_read").start()


def _parse_draft_sheet(values):
    """
    Parse rows from the 'Draft Tool' sheet into a structured results dict.
    Ported from old launcher._parse_draft_sheet().
    Returns dict with keys:
      team1_roster, team2_roster,
      bans_blue, bans_red,
      blue_comps, red_comps
    """
    import re
    ROLES = {"TOP", "JGL", "MID", "BOT", "SUP"}

    team1_roster, team2_roster = [], []
    bans_blue,    bans_red     = [], []
    blue_comps,   red_comps    = [], []

    def _pad(row, n=14):
        return (list(row) + [""] * n)[:n]

    # ── Roster rows ──────────────────────────────────────────────
    for i, row in enumerate(values):
        if not row:
            continue
        first = str(row[0])
        if "TEAM 1" in first and "BLUE" in first:
            for j in range(i + 2, min(i + 7, len(values))):
                r = _pad(values[j])
                if r[1].strip():
                    team1_roster.append({"role": r[0].strip(), "player": r[1].strip(),
                                         "rank": r[2].strip(), "top_champ": r[3].strip()})
                if r[8].strip():
                    team2_roster.append({"role": r[7].strip(), "player": r[8].strip(),
                                         "rank": r[9].strip(), "top_champ": r[10].strip()})
            break

    # ── Ban rows ──────────────────────────────────────────────────
    for i, row in enumerate(values):
        if not row:
            continue
        first = str(row[0])
        if "RECOMMENDED BANS" in first:
            for j in range(i + 2, min(i + 7, len(values))):
                r = _pad(values[j])
                if r[1] and r[1] != "-":
                    bans_blue.append({"phase": r[0], "champion": r[1], "target": r[2],
                                      "wr": r[3], "games": r[4], "priority": r[5]})
                if r[8] and r[8] != "-":
                    bans_red.append({"phase": r[7], "champion": r[8], "target": r[9],
                                     "wr": r[10], "games": r[11], "priority": r[12]})
            break

    # ── Comp suggestion rows ──────────────────────────────────────
    current_team = None
    current_comp = None
    for row in values:
        if not row:
            continue
        r      = _pad(row)
        first  = r[0].strip()
        eighth = r[7].strip()

        if "TEAM 1 COMP SUGGESTIONS" in first:
            current_team, current_comp = "blue", None
            continue
        if "TEAM 2 COMP SUGGESTIONS" in first:
            current_team, current_comp = "red", None
            continue
        if current_team is None:
            continue

        # Archetype header: "NAME — description" in col A, viability in col H
        if "—" in first and any(v in eighth for v in
                                 ["STRONG", "VIABLE", "WEAK", "NOT RECOMMENDED", "Synergy"]):
            parts     = first.split("—", 1)
            archetype = parts[0].strip()
            desc      = parts[1].strip() if len(parts) > 1 else ""
            viability = "VIABLE"
            for v in ["NOT RECOMMENDED", "STRONG", "VIABLE", "WEAK"]:
                if eighth.startswith(v):
                    viability = v
                    break
            syn  = re.search(r"Synergy:\s*(\d+)", eighth)
            meta = re.search(r"(\d+)/5\s*on-meta", eighth)
            current_comp = {
                "archetype":   archetype,
                "description": desc,
                "viability":   viability,
                "synergy":     int(syn.group(1))  if syn  else 0,
                "on_meta":     meta.group(1)       if meta else "0",
                "picks":       [],
            }
            (blue_comps if current_team == "blue" else red_comps).append(current_comp)
            continue

        # Skip column-header rows
        if first == "Player" and r[1].strip() == "Role":
            continue

        # Pick data rows
        if current_comp is not None and r[1].strip() in ROLES:
            current_comp["picks"].append({
                "player":   r[0], "role": r[1], "champion": r[2],
                "games":    r[3], "wr":   r[4], "kda":      r[5], "fit": r[6],
            })

    return {
        "team1_roster": team1_roster,
        "team2_roster": team2_roster,
        "bans_blue":    bans_blue,
        "bans_red":     bans_red,
        "blue_comps":   blue_comps,
        "red_comps":    red_comps,
    }
