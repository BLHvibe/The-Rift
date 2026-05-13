"""
Live data reader for The Rift.
Reads parsed data from Google Sheets tabs after a fetch_ranks run.
All functions return plain dicts/lists — no DPG dependencies.
"""
import os, sys, threading
from collections import defaultdict
from data.config import load_config


def _resolve_creds_path(path):
    """
    Resolve a credentials.json path at runtime.
    Priority: absolute path (if it exists) → sys._MEIPASS (frozen bundle)
    → next to exe → relative to this file → as-is.
    """
    if os.path.isabs(path) and os.path.exists(path):
        return path
    if getattr(sys, "frozen", False):
        bundled = os.path.join(sys._MEIPASS, path)
        if os.path.exists(bundled):
            return bundled
        beside_exe = os.path.join(os.path.dirname(sys.executable), path)
        if os.path.exists(beside_exe):
            return beside_exe
    if os.path.exists(path):
        return path
    here = os.path.dirname(os.path.abspath(__file__))
    local = os.path.join(here, path)
    if os.path.exists(local):
        return local
    root = os.path.normpath(os.path.join(here, "..", ".."))
    root_path = os.path.join(root, path)
    if os.path.exists(root_path):
        return root_path
    return path

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
        self.activity       = []   # list of activity event dicts (newest first)
        self.players        = []   # ordered list of real player display names (from Players sheet)
        self.summoner_map   = {}   # gameName (Riot ID game part) → display name
        self.loaded     = False
        self.loading    = False
        self.error      = None
        self._lock      = threading.Lock()

    def set(self, rankings, scout, inhouse, inhouse_champs, primary_roles=None,
            players=None, summoner_map=None):
        with self._lock:
            self.rankings        = rankings
            self.scout           = scout
            self.inhouse         = inhouse
            if players      is not None: self.players      = players
            if summoner_map is not None: self.summoner_map = summoner_map
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
            rankings, scout, inhouse, inhouse_champs, primary_roles, players, summoner_map = _read_sheets(cfg)
            live.set(rankings, scout, inhouse, inhouse_champs, primary_roles,
                     players=players, summoner_map=summoner_map)
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
        _resolve_creds_path(cfg.get("creds_path", "credentials.json")), scopes=SCOPES)
    gc   = gspread.authorize(creds)
    sh   = gc.open_by_url(cfg["sheet_url"]) if cfg["sheet_url"].startswith("http") \
           else gc.open(cfg["sheet_url"])

    players, summoner_map      = _read_players_sheet(sh)
    rankings = _read_final_rankings(sh)
    # Supplement rankings with games count from Rank Data if Final Rankings has none
    if not any(r.get("games", 0) for r in rankings):
        rank_games = _read_rank_data_games(sh)
        for r in rankings:
            if r["name"] in rank_games:
                r["games"] = rank_games[r["name"]]
    scout                      = _read_player_stats(sh, rankings)
    known_names                = {r["name"] for r in rankings}
    inhouse, ih_ch, prim_roles = _read_inhouse(sh, known_names)
    return rankings, scout, inhouse, ih_ch, prim_roles, players, summoner_map


def _read_rank_data_games(sh):
    """Read games count per player from Rank Data tab (supplemental source)."""
    try:
        ws   = sh.worksheet("Rank Data")
        rows = ws.get_all_values()
        result = {}
        for row in rows[2:]:
            if len(row) < 11 or not row[1]:
                continue
            name = str(row[1]).strip()
            try:
                games = int(float(row[10]))
                if games > 0:
                    result[name] = games
            except (ValueError, IndexError):
                pass
        return result
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Players tab → roster + summoner map
# ---------------------------------------------------------------------------

def _read_players_sheet(sh):
    """
    Read the 'Players' sheet.
    Expected columns: [index, display_name, riot_id, ...]
    Only rows with a '#' in the riot_id column are real players (others are placeholders).
    Returns:
        players     – ordered list of display names
        summoner_map – {gameName (part before '#'): display_name}
    """
    try:
        ws   = sh.worksheet("Players")
        rows = ws.get_all_values()
    except Exception:
        return [], {}

    players      = []
    summoner_map = {}
    for row in rows:
        if len(row) < 3:
            continue
        name    = str(row[1]).strip()
        riot_id = str(row[2]).strip()
        if not name or not riot_id or "#" not in riot_id:
            continue
        if name.upper() in ("PLAYER NAME", "NAME", "PLAYER", "TBD", "TBA", ""):
            continue
        players.append(name)
        game_name = riot_id.split("#")[0].strip()
        if game_name:
            summoner_map[game_name] = name
    return players, summoner_map


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

    results    = []
    seen_names = set()
    pos = 0
    for row in rows[1:]:
        if len(row) < 8:
            continue
        r = [str(c).strip() for c in row[:8]]
        rank_str, name, avg_tier, tier_score, rank_score_raw, rank_score, final, rating = r

        if not name or name.lower() in ("name", "player", "tbd", "tba") \
                or name.upper().startswith("PLAYER"):
            continue
        # Stop at blank rank or separator rows
        if not rank_str and not name:
            continue
        # Skip rows that are clearly non-player (headers re-appearing, etc.)
        if rank_str.lower() in ("rank", "#", ""):
            continue
        # Skip duplicate player rows (keep first / highest-ranked occurrence)
        if name.lower() in seen_names:
            continue
        seen_names.add(name.lower())

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

    results    = []
    seen_names = set()
    for row in rows[2:]:
        if len(row) < 9 or not row[0]:
            continue
        try:
            name = str(row[1]).strip()
            if name.lower() in seen_names:
                continue
            seen_names.add(name.lower())
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
                "name":       name,
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
            if len(row) < 2 or not row[1]:
                continue
            name = str(row[1]).strip()
            top_champs = []
            for i in range(3):
                cn = str(row[3 + i*2]).strip() if len(row) > 3+i*2 else ""
                if cn and cn != "-":
                    top_champs.append(cn)
            try:
                kda = float(row[11]) if len(row) > 11 and row[11] else 0.0
            except ValueError:
                kda = 0.0
            form = str(row[15]).strip().upper() if len(row) > 15 else "MIXED"
            if form not in ("HOT","COLD","MIXED"):
                form = "MIXED"
            # Parse WR% from col 2
            wr_from_stats = 0
            try:
                wr_raw = str(row[2]).strip().replace("%", "") if len(row) > 2 else ""
                if wr_raw:
                    wr_from_stats = int(float(wr_raw))
            except (ValueError, TypeError):
                pass
            # Parse games from "Recent W-L" column (e.g. "24-16")
            games_fallback = 0
            wins_fallback  = 0
            recent_wl = str(row[9]).strip() if len(row) > 9 else ""
            if recent_wl and "-" in recent_wl:
                try:
                    parts = recent_wl.split("-", 1)
                    w2 = int(parts[0].strip())
                    l2 = int(parts[1].strip())
                    games_fallback = w2 + l2
                    wins_fallback  = w2
                except (ValueError, IndexError):
                    pass
            stats_by_name[name] = {
                "top_champs":      top_champs,
                "kda":             kda,
                "form":            form,
                "wr_from_stats":   wr_from_stats,
                "games_fallback":  games_fallback,
                "wins_fallback":   wins_fallback,
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
        # WR: prefer rankings value, then Player Stats WR%, then 0
        try:
            wr = int(float(r.get("wr") or 0))
        except (ValueError, TypeError):
            wr = 0
        if wr == 0:
            wr = stats.get("wr_from_stats", 0)
        # Games: prefer rankings supplement, then Player Stats W-L parse
        games_val = r.get("games", 0) or stats.get("games_fallback", 0)
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
            "games":       games_val,
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

    # Group records by gameId; accept games with 2–10 players (relaxed from strict 10)
    games_by_id = defaultdict(list)
    for r in records:
        games_by_id[r["gameId"]].append(r)

    valid_records = []
    for gid, recs in games_by_id.items():
        if 2 <= len(recs) <= 10:
            valid_records.extend(recs)

    if not valid_records:
        return [], {}, {}

    # Per-player aggregates
    player_agg = defaultdict(lambda: {
        "games": set(), "wins": 0, "kills": 0, "deaths": 0,
        "assists": 0, "damage": 0, "gold": 0,
        "game_results": [],  # chronological list of 1=win / 0=loss
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
        pa["game_results"].append(1 if r["win"] else 0)
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
            "player":         name,
            "games":          g,
            "wins":           w,
            "losses":         l,
            "wr":             f"{wr}%",
            "kda":            kda,
            "cs_min":         "—",
            "damage":         f"{avg_dmg:,}",
            "gold":           f"{avg_gold:,}",
            "recent_results": pa["game_results"][-10:],
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

    # If _InhouseGameLog was empty, fall back to the pre-computed display sheet
    if not leaderboard:
        return _read_inhouse_stats_tab(sh, known_names)

    return leaderboard, inhouse_champs, primary_roles


def _parse_inhouse_stats_rows(rows, known_names=None):
    """
    Parse the 'In-House Stats' display sheet into the same leaderboard/champs
    structure that _read_inhouse returns.  Used as a fallback when _InhouseGameLog
    is missing or empty.

    Sheet layout (matches the CSV attached by the user):
      Row 0:  "IN-HOUSE 5v5 STATS"
      Row 3:  "IN-HOUSE LEADERBOARD"
      Row 4:  column headers (#, Player, Games, Wins, Losses, Win Rate, KDA, …)
      Row 5+: leaderboard data until blank rows
      …
      "IN-HOUSE CHAMPION STATS" section with per-player champion blocks
    """
    leaderboard    = []
    inhouse_champs = {}

    # ── Leaderboard section ──────────────────────────────────────────────────
    lb_header_row = None
    for i, row in enumerate(rows):
        first = str(row[0]).strip().upper() if row else ""
        if first.startswith("IN-HOUSE LEADERBOARD"):
            lb_header_row = i + 1   # next row = column headers
            break

    if lb_header_row is not None:
        for row in rows[lb_header_row + 1:]:   # +1 to skip column header row
            if not row or not str(row[0]).strip():
                break
            try:
                int(str(row[0]).strip())
            except ValueError:
                break  # hit next section header

            try:
                rank     = int(str(row[0]).strip())
                name     = str(row[1]).strip()
                games    = int(str(row[2]).strip())   if len(row) > 2  and row[2]  else 0
                wins     = int(str(row[3]).strip())   if len(row) > 3  and row[3]  else 0
                losses   = int(str(row[4]).strip())   if len(row) > 4  and row[4]  else 0
                wr_str   = str(row[5]).strip()        if len(row) > 5  else "0%"
                kda      = float(str(row[6]).strip()) if len(row) > 6  and row[6]  else 0.0
                avg_dmg  = str(row[11]).strip()       if len(row) > 11 and row[11] else "0"
                avg_gold = str(row[12]).strip()       if len(row) > 12 and row[12] else "0"
            except (ValueError, IndexError):
                continue

            leaderboard.append({
                "rank":           rank,
                "player":         name,
                "games":          games,
                "wins":           wins,
                "losses":         losses,
                "wr":             wr_str,
                "kda":            kda,
                "cs_min":         "—",
                "damage":         avg_dmg,
                "gold":           avg_gold,
                "recent_results": [],
            })

    # ── Champion stats section ───────────────────────────────────────────────
    champ_section_row = None
    for i, row in enumerate(rows):
        first = str(row[0]).strip().upper() if row else ""
        if first.startswith("IN-HOUSE CHAMPION STATS"):
            champ_section_row = i + 1
            break

    if champ_section_row is not None:
        current_player = None
        current_champs = []
        i = champ_section_row
        while i < len(rows):
            row = rows[i]
            first = str(row[0]).strip() if row else ""

            if not first:
                # Blank row: flush current player
                if current_player and current_champs:
                    inhouse_champs[current_player] = current_champs
                current_player = None
                current_champs = []
                i += 1
                continue

            upper = first.upper()
            if upper.startswith("IN-HOUSE ROLE"):
                break   # role section starts — we're done

            # Player header: "PlayerName  -  N games  |  XX.X% WR"
            if "  -  " in first and "games" in first.lower():
                if current_player and current_champs:
                    inhouse_champs[current_player] = current_champs
                current_player = first.split("  -  ")[0].strip()
                current_champs = []
                i += 1
                continue

            # Champion column header row
            if upper.startswith("CHAMPION"):
                i += 1
                continue

            # Champion data row
            if current_player:
                try:
                    cg   = int(str(row[1]).strip())   if len(row) > 1 and row[1] else 0
                    cw   = int(str(row[2]).strip())   if len(row) > 2 and row[2] else 0
                    cl   = int(str(row[3]).strip())   if len(row) > 3 and row[3] else 0
                    cwr  = str(row[4]).strip()         if len(row) > 4 else "0%"
                    ckda = float(str(row[5]).strip())  if len(row) > 5 and row[5] else 0.0
                    ck   = float(str(row[6]).strip())  if len(row) > 6 and row[6] else 0.0
                    cd   = float(str(row[7]).strip())  if len(row) > 7 and row[7] else 0.0
                    ca   = float(str(row[8]).strip())  if len(row) > 8 and row[8] else 0.0
                    cdmg = str(row[9]).strip()         if len(row) > 9 and row[9] else "0"
                    if cg > 0:
                        current_champs.append({
                            "champ":   first,
                            "games":   cg,
                            "wins":    cw,
                            "losses":  cl,
                            "wr":      cwr,
                            "kda":     ckda,
                            "kills":   ck,
                            "deaths":  cd,
                            "assists": ca,
                            "damage":  cdmg,
                        })
                except (ValueError, IndexError):
                    pass

            i += 1

        if current_player and current_champs:
            inhouse_champs[current_player] = current_champs

    # ── Filter to roster ─────────────────────────────────────────────────────
    if known_names:
        leaderboard    = [p for p in leaderboard    if p["player"] in known_names]
        inhouse_champs = {k: v for k, v in inhouse_champs.items() if k in known_names}

    # Re-sort + re-rank after filtering
    def _wr_key(p):
        try:
            return float(str(p["wr"]).replace("%", ""))
        except (ValueError, TypeError):
            return 0.0

    leaderboard.sort(key=lambda p: (_wr_key(p), p["games"]), reverse=True)
    for idx, p in enumerate(leaderboard):
        p["rank"] = idx + 1

    return leaderboard, inhouse_champs, {}


def _read_inhouse_stats_tab(sh, known_names=None):
    """Read leaderboard from the 'In-House Stats' display sheet."""
    try:
        ws   = sh.worksheet("In-House Stats")
        rows = ws.get_all_values()
        return _parse_inhouse_stats_rows(rows, known_names)
    except Exception:
        return [], {}, {}


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
        _resolve_creds_path(cfg.get("creds_path", "credentials.json")), scopes=SCOPES)
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


_ROLE_DISPLAY = {
    "TOP": "Top", "JGL": "Jungle", "MID": "Mid", "BOT": "Bot", "SUP": "Support",
    # pass-through for already-display-format values
    "Top": "Top", "Jungle": "Jungle", "Mid": "Mid", "Bot": "Bot", "Support": "Support",
}


def write_draft_picks(blue_players, red_players, on_done=None, on_error=None):
    """
    Write blue/red team selections to 'Draft Tool' sheet (rows 6–10).
    Columns A–C = slot#, player, role  |  H–J = slot#, player, role
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
                b_role = _ROLE_DISPLAY.get(bp.get("role", ""), bp.get("role", ""))
                r_role = _ROLE_DISPLAY.get(rp.get("role", ""), rp.get("role", ""))
                ws.update(values=[[i + 1, bp.get("name",""), b_role]],
                          range_name=f"A{row}:C{row}")
                ws.update(values=[[i + 1, rp.get("name",""), r_role]],
                          range_name=f"H{row}:J{row}")
            if on_done:
                on_done()
        except Exception as e:
            if on_error:
                on_error(str(e))

    threading.Thread(target=_bg, daemon=True, name="draft_write").start()


def run_draft_subprocess(on_done=None, on_error=None, on_line=None):
    """
    Run fetch_ranks_gsheets draft analysis.
    When frozen (exe), imports the module directly — subprocess won't work.
    When running from source, spawns a subprocess so stdout streams line-by-line.
    """
    import subprocess

    cfg = load_config()
    key = cfg.get("api_key", "")
    if not key:
        if on_error:
            on_error("No API key set — add your Riot API key in Settings.")
        return

    creds_path = _resolve_creds_path(cfg.get("creds_path", "credentials.json"))

    # Frozen exe: import module directly (subprocess can't run .py files)
    if getattr(sys, "frozen", False):
        def _bg_frozen():
            try:
                import data.fetch_ranks_gsheets as fg
                if on_line:
                    on_line("Running draft analysis…")
                # Simulate the CLI args that the subprocess path would pass
                _old_argv = sys.argv[:]
                sys.argv = [
                    "fetch_ranks_gsheets",
                    "--key",     key,
                    "--sheet",   cfg.get("sheet_url", ""),
                    "--creds",   creds_path,
                    "--region",  cfg.get("region", "na1"),
                    "--routing", cfg.get("routing", "americas"),
                    "--draft",
                ]
                try:
                    fg.main()
                finally:
                    sys.argv = _old_argv
                try:
                    sh = _gspread_connect(cfg)
                    if on_done:
                        on_done(sh)
                except Exception as e:
                    if on_error:
                        on_error(f"Couldn't reconnect to sheet after draft: {e}")
            except Exception as e:
                if on_error:
                    on_error(f"Draft analysis error: {e}")
        threading.Thread(target=_bg_frozen, daemon=True, name="draft_frozen").start()
        return

    # Dev mode: subprocess with stdout streaming
    script = _find_draft_script()
    if not script:
        if on_error:
            on_error("fetch_ranks_gsheets.py not found — rich draft analysis unavailable.")
        return

    cmd = [
        sys.executable, script,
        "--key",     key,
        "--sheet",   cfg.get("sheet_url", ""),
        "--creds",   creds_path,
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


# ---------------------------------------------------------------------------
# Phase 3 — Scout: on-demand per-player sheet read
# ---------------------------------------------------------------------------

def load_scout_sheet(player_name, on_done=None, on_error=None):
    """
    Background fetch of 'Scout - {player_name}' sheet + 'Rank History' column.
    on_done(data, history) — data = parsed scout dict, history = [(date_str, float), ...]
    on_error(msg)          — called if sheet is missing or auth fails
    Falls back gracefully: if Rank History unavailable, history=[]
    """
    def _bg():
        try:
            cfg  = load_config()
            sh   = _gspread_connect(cfg)
            sheet_name = f"Scout - {player_name}"[:30]
            try:
                ws = sh.worksheet(sheet_name)
            except Exception:
                if on_error:
                    on_error(
                        f"No scouting sheet found for {player_name}.\n"
                        f"Run 'Full Scout' from the Commands tab first."
                    )
                return

            data    = _parse_scouting_sheet(ws.get_all_values())
            history = _read_rank_history_for_player(sh, player_name)

            if on_done:
                on_done(data, history)
        except Exception as e:
            if on_error:
                on_error(f"Couldn't load scouting report: {e}")

    threading.Thread(target=_bg, daemon=True,
                     name=f"scout_{player_name[:12]}").start()


def _read_rank_history_for_player(sh, player_name):
    """
    Return [(date_str, rank_value), ...] for a specific player from 'Rank History'.
    Row 0 may be title; Row 1 = header; Row 2+ = data rows, col 0 = date.
    """
    try:
        ws   = sh.worksheet("Rank History")
        rows = ws.get_all_values()
        if len(rows) < 3:
            return []
        header  = rows[1]
        col_idx = None
        for ci, col_name in enumerate(header):
            if str(col_name).strip().lower() == player_name.strip().lower():
                col_idx = ci
                break
        if col_idx is None:
            return []
        result = []
        for row in rows[2:]:
            if col_idx < len(row) and row[col_idx]:
                try:
                    result.append((str(row[0]).strip(), float(row[col_idx])))
                except ValueError:
                    pass
        return result
    except Exception:
        return []


def _parse_scouting_sheet(values):
    """
    Parse all rows of a 'Scout - PlayerName' sheet into a structured dict.
    Ported from old launcher._parse_scouting_sheet().
    """
    import re
    from datetime import datetime as _dt

    _SECTION_MARKERS = (
        "BAN THESE CHAMPIONS", "BAN IMPACT:", "FULL CHAMPION POOL",
        "ROLE BREAKDOWN", "RECENT FORM:", "IN-HOUSE CUSTOM GAMES",
        "POWER RANKING:",
    )

    def _is_section(cell):
        return any(cell.startswith(m) for m in _SECTION_MARKERS)

    def _cell(row, idx, default=""):
        return str(row[idx]).strip() if len(row) > idx and row[idx] is not None else default

    result = {
        "player":           "",
        "subtitle":         "",
        "power_rating":     None,   # dict: position, score, rating, tier_score, rank_score
        "overview_headers": [],
        "overview_values":  [],
        "must_bans":        [],     # [{name, games, wr, kda, threat, ...}]
        "must_bans_msg":    None,
        "ban_impact":       None,   # dict: text, wr, games
        "champ_pool":       [],     # [{name, games, wins, losses, wr, kda, cs_min, damage}]
        "roles":            [],     # [{role, games, pct, top_champs}]
        "form_state":       "MIXED",
        "matches":          [],     # [{game, result, champion, role, kda_str, cs_min, damage, gold, duration}]
        "inhouse_champs":   [],     # in-sheet version (may be stale); prefer live.inhouse_champs
        "scouted_at":       None,   # datetime or None
    }

    if not values:
        return result

    # Row 0: "SCOUTING REPORT: Name"  +  col L (idx 11) "Scouted: YYYY-MM-DD HH:MM"
    if values[0] and values[0][0]:
        m = re.match(r"SCOUTING REPORT:\s*(.+)", str(values[0][0]))
        if m:
            result["player"] = m.group(1).strip()
        if len(values[0]) > 11 and values[0][11]:
            ts_raw = str(values[0][11]).strip()
            if ts_raw.startswith("Scouted:"):
                try:
                    result["scouted_at"] = _dt.strptime(
                        ts_raw.replace("Scouted:", "").strip(), "%Y-%m-%d %H:%M")
                except ValueError:
                    pass

    if len(values) > 1 and values[1]:
        result["subtitle"] = _cell(values[1], 0)

    i = 2
    while i < len(values):
        row  = values[i]
        cell = _cell(row, 0) if row else ""

        if not cell:
            i += 1; continue

        # ── Power ranking ─────────────────────────────────────────────────
        if cell.startswith("POWER RANKING:"):
            result["power_rating"] = _parse_power_rating_text(cell)
            i += 1; continue

        # ── Overview stats (header row starts with "KDA") ─────────────────
        if cell == "KDA" and len(row) > 1 and _cell(row, 1) == "Avg Kills":
            result["overview_headers"] = [_cell(row, c) for c in range(12)]
            if i + 1 < len(values):
                result["overview_values"] = [
                    (_cell(values[i+1], c)) for c in range(12)]
            i += 2; continue

        # ── Ban targets ───────────────────────────────────────────────────
        if cell == "BAN THESE CHAMPIONS":
            i += 1
            if i >= len(values):
                continue
            nxt = _cell(values[i], 0)
            if nxt == "Champion":
                i += 1
                while i < len(values):
                    r  = values[i]
                    c0 = _cell(r, 0)
                    if not c0 or _is_section(c0):
                        break
                    result["must_bans"].append({
                        "name":    c0,
                        "games":   _cell(r, 1), "wins":    _cell(r, 2),
                        "losses":  _cell(r, 3), "wr":      _cell(r, 4),
                        "kda":     _cell(r, 5), "kills":   _cell(r, 6),
                        "deaths":  _cell(r, 7), "assists": _cell(r, 8),
                        "cs_min":  _cell(r, 9), "damage":  _cell(r,10),
                        "threat":  _cell(r,11),
                    })
                    i += 1
            else:
                result["must_bans_msg"] = nxt
                i += 1
            continue

        # ── Ban impact ────────────────────────────────────────────────────
        if cell.startswith("BAN IMPACT:"):
            result["ban_impact"] = _parse_ban_impact_row(row)
            i += 1; continue

        # ── Full champion pool ────────────────────────────────────────────
        if cell == "FULL CHAMPION POOL":
            i += 1
            if i < len(values) and _cell(values[i], 0) == "Champion":
                i += 1
            while i < len(values):
                r  = values[i]
                c0 = _cell(r, 0)
                if not c0 or _is_section(c0):
                    break
                result["champ_pool"].append({
                    "name":    c0,
                    "games":   _cell(r, 1), "wins":    _cell(r, 2),
                    "losses":  _cell(r, 3), "wr":      _cell(r, 4),
                    "kda":     _cell(r, 5), "kills":   _cell(r, 6),
                    "deaths":  _cell(r, 7), "assists": _cell(r, 8),
                    "cs_min":  _cell(r, 9), "damage":  _cell(r,10),
                    "gold":    _cell(r,11),
                })
                i += 1
            continue

        # ── Role breakdown ────────────────────────────────────────────────
        if cell == "ROLE BREAKDOWN":
            i += 1
            if i < len(values) and _cell(values[i], 0) == "Role":
                i += 1
            while i < len(values):
                r  = values[i]
                c0 = _cell(r, 0)
                if not c0 or _is_section(c0):
                    break
                result["roles"].append({
                    "role":       c0,
                    "games":      _cell(r, 1),
                    "pct":        _cell(r, 2),
                    "top_champs": _cell(r, 3),
                })
                i += 1
            continue

        # ── Recent form (last 10 matches) ─────────────────────────────────
        if cell.startswith("RECENT FORM:"):
            m = re.match(r"RECENT FORM:\s*(\S+)", cell)
            if m:
                fs = m.group(1).upper()
                result["form_state"] = fs if fs in ("HOT","COLD","MIXED") else "MIXED"
            i += 1
            if i < len(values) and _cell(values[i], 0) == "Game":
                i += 1
            while i < len(values):
                r  = values[i]
                c0 = _cell(r, 0)
                if not c0 or _is_section(c0):
                    break
                result["matches"].append({
                    "game":     c0,
                    "result":   _cell(r, 1),
                    "champion": _cell(r, 2),
                    "role":     _cell(r, 3),
                    "kda_str":  _cell(r, 4),
                    "kda":      _cell(r, 5),
                    "cs_min":   _cell(r, 6),
                    "damage":   _cell(r, 7),
                    "vision":   _cell(r, 8),
                    "gold":     _cell(r, 9),
                    "duration": _cell(r,10),
                })
                i += 1
            continue

        # ── In-house customs (in-sheet version, prefer live.inhouse_champs) ─
        if cell.startswith("IN-HOUSE CUSTOM GAMES"):
            i += 1
            if i < len(values) and _cell(values[i], 0) == "Champion":
                i += 1
            while i < len(values):
                r  = values[i]
                c0 = _cell(r, 0)
                if not c0 or _is_section(c0):
                    break
                result["inhouse_champs"].append({
                    "name":    c0,
                    "games":   _cell(r, 1), "wins":    _cell(r, 2),
                    "losses":  _cell(r, 3), "wr":      _cell(r, 4),
                    "kda":     _cell(r, 5), "damage":  _cell(r, 9),
                })
                i += 1
            continue

        i += 1

    return result


def _parse_power_rating_text(text):
    """Extract position/score/rating from a 'POWER RANKING: ...' cell string."""
    import re
    out = {"position": "", "score": "", "rating": "", "tier_score": "", "rank_score": ""}
    m = re.search(r"#(\S+)", text)
    if m: out["position"] = m.group(1)
    m = re.search(r"Final Score:\s*([^|]+)", text)
    if m: out["score"] = m.group(1).strip()
    m = re.search(r"Rating:\s*([^|]+)", text)
    if m: out["rating"] = m.group(1).strip()
    m = re.search(r"Tier Score[^:]*:\s*([^|]+)", text)
    if m: out["tier_score"] = m.group(1).strip()
    m = re.search(r"Rank Score[^:]*:\s*([^|]+)", text)
    if m: out["rank_score"] = m.group(1).strip()
    return out


def _parse_ban_impact_row(row):
    """Parse the 'BAN IMPACT:' row into {text, wr, games}."""
    import re
    text = " ".join(str(c) for c in row if c)
    out  = {"text": "", "wr": "", "games": ""}
    m = re.match(r"(BAN IMPACT:[^|]*?)(?:Remaining|$)", text)
    if m: out["text"] = m.group(1).strip()
    m = re.search(r"Remaining WR:\s*(\d+(?:\.\d+)?%)", text)
    if m: out["wr"] = m.group(1)
    m = re.search(r"\((\d+)\s*games?\)", text)
    if m: out["games"] = m.group(1)
    return out


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
    # All known role spellings across sheet variants
    ROLES = {"TOP", "JGL", "MID", "BOT", "SUP",
             "Top", "Jungle", "Mid", "Bot", "Support"}
    _SKIP = {"", "Player", "Role", "Champion", "player", "role", "champion"}

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

        # Pick data rows — detect by non-empty player name + non-empty champion,
        # regardless of what is in the "Role" column (may be rank tier or lane name)
        if (current_comp is not None
                and r[0].strip() not in _SKIP
                and r[2].strip() not in _SKIP
                and r[2].strip()):
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


# ---------------------------------------------------------------------------
# Activity feed reader
# ---------------------------------------------------------------------------

def _read_activity(sh):
    """
    Read '_Activity' tab → list of event dicts, newest first.
    Columns: Timestamp, Event Type, Player, Details, Related Player
    """
    try:
        ws   = sh.worksheet("_Activity")
        rows = ws.get_all_values()
        if len(rows) < 2:
            return []
        events = []
        for row in rows[1:]:
            if not row or not row[0]:
                continue
            events.append({
                "timestamp":      str(row[0]).strip(),
                "event_type":     str(row[1]).strip().upper() if len(row) > 1 else "",
                "player":         str(row[2]).strip()         if len(row) > 2 else "",
                "details":        str(row[3]).strip()         if len(row) > 3 else "",
                "related_player": str(row[4]).strip()         if len(row) > 4 else "",
            })
        return list(reversed(events))   # newest first
    except Exception:
        return []


def load_activity(on_done=None, on_error=None):
    """Background load of _Activity sheet into live.activity."""
    def _bg():
        try:
            cfg    = load_config()
            sh     = _gspread_connect(cfg)
            events = _read_activity(sh)
            with live._lock:
                live.activity = events
            if on_done:
                on_done(events)
        except Exception as e:
            if on_error:
                on_error(str(e))
    threading.Thread(target=_bg, daemon=True, name="activity_loader").start()


def write_activity_event(event_type, player, details, on_done=None, on_error=None):
    """Append one event row to _Activity sheet and refresh live.activity."""
    from datetime import datetime as _dt
    def _bg():
        try:
            cfg = load_config()
            sh  = _gspread_connect(cfg)
            try:
                ws = sh.worksheet("_Activity")
            except Exception:
                ws = sh.add_worksheet(title="_Activity", rows=500, cols=5)
                ws.update(values=[["Timestamp","Event Type","Player","Details","Related Player"]],
                          range_name="A1")
            ts = _dt.now().strftime("%Y-%m-%d %H:%M")
            ws.append_row([ts, event_type, player or "", details or "", ""],
                          value_input_option="RAW")
            # Refresh live activity
            events = _read_activity(sh)
            with live._lock:
                live.activity = events
            if on_done:
                on_done()
        except Exception as e:
            if on_error:
                on_error(str(e))
    threading.Thread(target=_bg, daemon=True, name="activity_write").start()


def get_most_games_logged(on_done=None, on_error=None):
    """
    Read _InhouseGameLog and find which logged_by name appears most.
    Calls on_done(player_name, count) or on_error(msg).
    """
    def _bg():
        try:
            cfg = load_config()
            sh  = _gspread_connect(cfg)
            ws  = sh.worksheet("_InhouseGameLog")
            rows = ws.get_all_values()
            counts = {}
            for row in rows[1:]:
                if len(row) < 16 or not row[15]:
                    continue
                lb = str(row[15]).strip()
                counts[lb] = counts.get(lb, 0) + 1
            if counts:
                top = max(counts, key=counts.get)
                if on_done:
                    on_done(top, counts[top])
            else:
                if on_done:
                    on_done(None, 0)
        except Exception as e:
            if on_error:
                on_error(str(e))
    threading.Thread(target=_bg, daemon=True, name="most_games_logged").start()


def log_inhouse_games_from_client(on_progress=None, on_done=None, on_error=None):
    """
    Connect to the League client, fetch recent custom games, append only NEW
    records to _InhouseGameLog (duplicate-safe by gameId), then reload inhouse data.

    on_progress(msg) — called with status updates during the operation
    on_done(new_count) — called with the number of new games added
    on_error(msg) — called on failure
    """
    import os, re, subprocess, urllib3, requests
    from datetime import datetime as _dt, timedelta
    from collections import defaultdict

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _find_lockfile():
        candidates = []
        local_app = os.environ.get("LOCALAPPDATA", "")
        if local_app:
            candidates.append(os.path.join(local_app, "Riot Games", "League of Legends", "lockfile"))
        for drive in ("C:\\", "D:\\", "E:\\"):
            for sub in ("Riot Games", "Program Files\\Riot Games", "Program Files (x86)\\Riot Games"):
                candidates.append(os.path.join(drive, sub, "League of Legends", "lockfile"))
        for p in candidates:
            if os.path.isfile(p):
                return p
        try:
            out = subprocess.check_output(
                'wmic process where "name=\'LeagueClientUx.exe\'" get commandline',
                shell=True, text=True, stderr=subprocess.DEVNULL)
            m = re.search(r'"([^"]*LeagueClientUx\.exe)"', out)
            if m:
                lf = os.path.join(os.path.dirname(m.group(1)), "lockfile")
                if os.path.isfile(lf):
                    return lf
        except Exception:
            pass
        return None

    def _load_champion_map():
        try:
            v    = requests.get("https://ddragon.leagueoflegends.com/api/versions.json", timeout=8).json()
            data = requests.get(f"https://ddragon.leagueoflegends.com/cdn/{v[0]}/data/en_US/champion.json", timeout=8).json()
            return {int(d["key"]): d["name"] for d in data["data"].values()}
        except Exception:
            return {}

    def _bg():
        try:
            if on_progress: on_progress("Finding League client…")
            lockfile = _find_lockfile()
            if not lockfile:
                if on_error: on_error("League client not running — open the client first.")
                return

            with open(lockfile) as f:
                parts = f.read().strip().split(":")
            if len(parts) < 5:
                if on_error: on_error("Unexpected lockfile format.")
                return

            port, password, protocol = parts[2], parts[3], parts[4]
            base_url = f"{protocol}://127.0.0.1:{port}"
            auth     = ("riot", password)

            r = requests.get(f"{base_url}/lol-summoner/v1/current-summoner",
                             auth=auth, verify=False, timeout=5)
            if r.status_code != 200:
                if on_error: on_error(f"Could not get summoner (status {r.status_code}).")
                return
            summoner    = r.json()
            logged_by   = summoner.get("gameName") or summoner.get("displayName") or "Unknown"
            if on_progress: on_progress(f"Connected as {logged_by} — loading champions…")

            champ_map = _load_champion_map()

            cfg = load_config()
            sh  = _gspread_connect(cfg)

            # Load existing game IDs to prevent duplicates
            if on_progress: on_progress("Checking existing game log…")
            try:
                ws_log  = sh.worksheet("_InhouseGameLog")
                all_rows = ws_log.get_all_values()
                existing_ids = set()
                for row in all_rows[1:]:
                    if row and row[0]:
                        try:    existing_ids.add(int(row[0]))
                        except Exception: existing_ids.add(row[0])
            except Exception:
                ws_log      = None
                existing_ids = set()
                all_rows     = []

            if on_progress: on_progress(f"{len(existing_ids)} games already logged — fetching history…")

            # Fetch match history
            cutoff = int((_dt.now() - timedelta(days=180)).timestamp() * 1000)
            url = f"{base_url}/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex=500"
            try:
                resp   = requests.get(url, auth=auth, verify=False, timeout=30)
                games  = resp.json().get("games", {}).get("games", []) if resp.status_code == 200 else []
            except Exception:
                games = []

            customs = [g for g in games
                       if g.get("gameCreation", 0) >= cutoff
                       and (g.get("queueId") in (0, 3130) or g.get("gameType") == "CUSTOM_GAME")
                       and g.get("gameId") not in existing_ids]

            if not customs:
                if on_done: on_done(0)
                return

            if on_progress: on_progress(f"Processing {len(customs)} new custom games…")

            role_map = {"TOP":"TOP","JUNGLE":"JGL","MIDDLE":"MID","BOTTOM":"BOT",
                        "UTILITY":"SUP","SUPPORT":"SUP","NONE":"","UNKNOWN":"","":""}
            new_records = []
            seen = set()
            for g in customs:
                gid = g.get("gameId")
                if not gid or gid in seen: continue
                seen.add(gid)
                try:
                    dr = requests.get(f"{base_url}/lol-match-history/v1/games/{gid}",
                                      auth=auth, verify=False, timeout=15)
                    d  = dr.json() if dr.status_code == 200 else {}
                except Exception:
                    continue
                participants = d.get("participants", [])
                identities   = d.get("participantIdentities", [])
                if len(participants) != 10: continue
                duration  = max(d.get("gameDuration", 1), 1)
                timestamp = _dt.fromtimestamp(d.get("gameCreation", 0) / 1000).strftime("%Y-%m-%d %H:%M")
                for idx, p in enumerate(participants):
                    pname = "Unknown"
                    if idx < len(identities):
                        pl    = identities[idx].get("player", {})
                        pname = pl.get("gameName") or pl.get("summonerName") or f"Player_{idx}"
                    stats  = p.get("stats", {})
                    cid    = p.get("championId", 0)
                    cname  = champ_map.get(cid, f"Champ#{cid}")
                    lane   = str(p.get("timeline", {}).get("lane", "")).upper()
                    role   = role_map.get(lane, "")
                    cs     = stats.get("totalMinionsKilled", 0) + stats.get("neutralMinionsKilled", 0)
                    new_records.append({
                        "gameId":    gid,
                        "timestamp": timestamp,
                        "player":    pname,
                        "champion":  cname,
                        "teamId":    p.get("teamId", 0),
                        "win":       stats.get("win", False),
                        "kills":     stats.get("kills", 0),
                        "deaths":    stats.get("deaths", 0),
                        "assists":   stats.get("assists", 0),
                        "cs":        cs,
                        "damage":    stats.get("totalDamageDealtToChampions", 0),
                        "gold":      stats.get("goldEarned", 0),
                        "vision":    stats.get("visionScore", 0),
                        "role":      role,
                        "duration":  round(duration / 60, 1),
                        "logged_by": logged_by,
                    })

            if not new_records:
                if on_done: on_done(0)
                return

            # Append to sheet (create if needed, never overwrite existing)
            if on_progress: on_progress(f"Saving {len(new_records)//10} new games to sheet…")
            if ws_log is None:
                ws_log = sh.add_worksheet(title="_InhouseGameLog", rows=5000, cols=16)
                ws_log.update(values=[["gameId","timestamp","player","champion","teamId",
                                        "win","kills","deaths","assists","cs","damage",
                                        "gold","vision","role","duration","logged_by"]],
                              range_name="A1")
                all_rows = [["header"]]
            next_row = len(all_rows) + 1
            rows_to_write = []
            for rec in new_records:
                rows_to_write.append([
                    rec["gameId"], rec["timestamp"], rec["player"], rec["champion"],
                    rec["teamId"], str(rec["win"]), rec["kills"], rec["deaths"],
                    rec["assists"], rec["cs"], rec["damage"], rec["gold"],
                    rec["vision"], rec["role"], rec["duration"], rec["logged_by"],
                ])
            for i in range(0, len(rows_to_write), 500):
                chunk = rows_to_write[i:i+500]
                ws_log.update(values=chunk, range_name=f"A{next_row + i}")

            new_game_count = len(new_records) // 10

            # Write activity event
            write_activity_event("INHOUSE", logged_by,
                                 f"Logged {new_game_count} new inhouse game{'s' if new_game_count!=1 else ''}")

            # Reload inhouse data into live
            known_names = {r["name"] for r in live.rankings}
            ib, ic, pr  = _read_inhouse(sh, known_names if known_names else None)
            with live._lock:
                live.inhouse        = ib
                live.inhouse_champs = ic
                if pr:
                    live.primary_roles.update(pr)

            if on_done: on_done(new_game_count)

        except Exception as e:
            if on_error: on_error(str(e))

    threading.Thread(target=_bg, daemon=True, name="log_inhouse").start()


# ---------------------------------------------------------------------------
# Tier list sheet persistence
# ---------------------------------------------------------------------------

def write_tier_list(placements, submitter_name, on_done=None, on_error=None):
    """
    Write a player's tier list ratings to the 'Tier Lists' sheet.

    Sheet layout (as exported from Google Sheets):
      Row 1 : "Player" label  (ignored)
      Row 2 : Tier value legend  (ignored)
      Row 3 : "#, Player Name, Ben, Luke, Chips, …"  ← rater names header
      Row 4+ : "#, <player name>, <Ben rating>, <Luke rating>, …"
               col A = row #, col B = player display name, col C+ = tier ratings

    placements : dict  {tier_letter: [player_names]}
    submitter_name : must match a column header in row 3 of the sheet.
    """
    _HEADER_ROW = 3   # 1-based row that contains rater names
    _PLAYER_COL = 2   # 1-based column B — player display names

    def _bg():
        try:
            import gspread
            cfg = load_config()
            sh  = _gspread_connect(cfg)
            ws  = sh.worksheet("Tier Lists")

            # --- Locate the submitter's column from row 3 ---
            header = ws.row_values(_HEADER_ROW)
            if submitter_name not in header:
                if on_error:
                    on_error(
                        f"'{submitter_name}' not found in Tier Lists header (row 3). "
                        f"Add their name to row 3 of the sheet first."
                    )
                return
            col_idx = header.index(submitter_name) + 1   # convert to 1-based

            # --- Build player → tier letter lookup ---
            player_to_tier = {}
            for tier_letter, names in placements.items():
                for n in names:
                    player_to_tier[n] = tier_letter

            # --- Read column B to find each player's row ---
            col_b = ws.col_values(_PLAYER_COL)   # index 0 = row 1

            # --- Batch all cell writes into one API call ---
            updates = []
            missing = []
            for pname, tier_letter in player_to_tier.items():
                if pname in col_b:
                    row_idx = col_b.index(pname) + 1   # 1-based
                    cell    = gspread.utils.rowcol_to_a1(row_idx, col_idx)
                    updates.append({"range": cell, "values": [[tier_letter]]})
                else:
                    missing.append(pname)

            if updates:
                ws.batch_update(updates)

            if missing:
                print(f"[tier_list write] players not found in sheet col B: {missing}")

            if on_done:
                on_done()
        except Exception as e:
            if on_error:
                on_error(str(e))

    threading.Thread(target=_bg, daemon=True, name="tier_write").start()


# ---------------------------------------------------------------------------
# Settings: test Google Sheets connection
# ---------------------------------------------------------------------------

def test_sheets_connection(on_done=None, on_error=None):
    """
    Try to open the configured spreadsheet.
    on_done(title: str) on success; on_error(msg: str) on failure.
    """
    def _bg():
        try:
            cfg = load_config()
            if not cfg.get("sheet_url"):
                if on_error:
                    on_error("No sheet URL configured.")
                return
            if not cfg.get("creds_path"):
                if on_error:
                    on_error("No credentials path configured.")
                return
            sh = _gspread_connect(cfg)
            if on_done:
                on_done(sh.title)
        except Exception as e:
            if on_error:
                on_error(str(e))
    threading.Thread(target=_bg, daemon=True, name="test_conn").start()


# ---------------------------------------------------------------------------
# Player avatar sync — Google Sheets "Player Avatars" tab
# ---------------------------------------------------------------------------
_AVATAR_SHEET = "Player Avatars"
_AVATAR_COLS  = [["Player Name", "Image Data (base64)", "Last Updated"]]


def upload_player_avatar(player_name, image_path, on_done=None, on_error=None):
    """
    Hex-crop image_path to 128×128, encode as base64 JPEG, write/update
    the "Player Avatars" sheet row for player_name.
    Also saves the cropped PNG locally to assets/profile_icons/<name>.png.
    on_done() or on_error(msg).
    """
    import base64, os
    from io import BytesIO

    def _bg():
        try:
            from PIL import Image, ImageDraw
            size = 128
            img  = Image.open(image_path).convert("RGBA")
            img  = img.resize((size, size), Image.LANCZOS)

            # Hex mask
            mask = Image.new("L", (size, size), 0)
            draw = ImageDraw.Draw(mask)
            import math as _m
            cx2, cy2, r = size // 2, size // 2, size // 2 - 2
            pts = [
                (cx2 + r * _m.cos(_m.pi / 6 + i * _m.pi / 3),
                 cy2 + r * _m.sin(_m.pi / 6 + i * _m.pi / 3))
                for i in range(6)
            ]
            draw.polygon(pts, fill=255)
            result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            result.paste(img, mask=mask)

            # Save locally
            safe = "".join(c for c in player_name if c.isalnum() or c in " _-").strip()
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            local_path = os.path.join(root, "assets", "profile_icons", f"{safe}.png")
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            result.save(local_path, "PNG")

            # Encode for Sheets (as JPEG for size, with transparent bg turned white)
            rgb = Image.new("RGB", (size, size), (20, 16, 32))
            rgb.paste(result, mask=result.split()[3])
            buf = BytesIO()
            rgb.save(buf, format="JPEG", quality=80)
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

            # Write to sheet
            from datetime import datetime as _dt
            ts  = _dt.now().strftime("%Y-%m-%d %H:%M")
            cfg = load_config()
            sh  = _gspread_connect(cfg)
            try:
                ws = sh.worksheet(_AVATAR_SHEET)
            except Exception:
                ws = sh.add_worksheet(title=_AVATAR_SHEET, rows=200, cols=3)
                ws.update(values=_AVATAR_COLS, range_name="A1")

            rows = ws.get_all_values()
            for idx, row in enumerate(rows[1:], start=2):
                if row and row[0].strip().lower() == player_name.strip().lower():
                    ws.update(values=[[player_name, b64, ts]], range_name=f"A{idx}")
                    if on_done: on_done(local_path)
                    return
            ws.append_row([player_name, b64, ts], value_input_option="RAW")
            if on_done: on_done(local_path)

        except ImportError:
            if on_error: on_error("Pillow not installed — run: pip install Pillow")
        except Exception as e:
            if on_error: on_error(str(e))

    threading.Thread(target=_bg, daemon=True, name="avatar_upload").start()


def download_all_avatars(on_done=None, on_error=None):
    """
    Read every row in "Player Avatars" sheet, decode base64, save to
    assets/profile_icons/<name>.png.  Calls on_done({name: local_path}) or
    on_error(msg).  Safe to call repeatedly — skips rows with no data.
    """
    import base64, os

    def _bg():
        try:
            cfg = load_config()
            sh  = _gspread_connect(cfg)
            try:
                ws = sh.worksheet(_AVATAR_SHEET)
            except Exception:
                if on_done: on_done({})
                return

            rows  = ws.get_all_values()
            root  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            adir  = os.path.join(root, "assets", "profile_icons")
            os.makedirs(adir, exist_ok=True)

            result = {}
            for row in rows[1:]:
                if len(row) < 2 or not row[0] or not row[1]:
                    continue
                name = row[0].strip()
                b64  = row[1].strip()
                try:
                    data = base64.b64decode(b64)
                    safe = "".join(c for c in name if c.isalnum() or c in " _-").strip()
                    # Save as .jpg (decoded data is JPEG)
                    path = os.path.join(adir, f"{safe}.jpg")
                    with open(path, "wb") as f:
                        f.write(data)
                    result[name] = path
                except Exception:
                    pass

            if on_done: on_done(result)
        except Exception as e:
            if on_error: on_error(str(e))

    threading.Thread(target=_bg, daemon=True, name="avatar_download").start()


def detect_lcu_summoner():
    """
    Synchronous LCU lockfile read → returns (display_name, error_str).
    Safe to call from a background thread.
    """
    import os, requests, urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    candidates = []
    local_app = os.environ.get("LOCALAPPDATA", "")
    if local_app:
        candidates.append(os.path.join(local_app, "Riot Games", "League of Legends", "lockfile"))
    for drive in ("C:\\", "D:\\", "E:\\"):
        for sub in ("Riot Games", os.path.join("Program Files", "Riot Games"),
                    os.path.join("Program Files (x86)", "Riot Games")):
            candidates.append(os.path.join(drive, sub, "League of Legends", "lockfile"))

    lockfile = next((p for p in candidates if os.path.isfile(p)), None)
    if not lockfile:
        return None, "League client not running (lockfile not found)"

    try:
        with open(lockfile) as f:
            parts = f.read().strip().split(":")
        if len(parts) < 5:
            return None, "Unexpected lockfile format"
        port, password = parts[2], parts[3]
    except Exception as e:
        return None, f"Could not read lockfile: {e}"

    try:
        url = f"https://127.0.0.1:{port}/lol-summoner/v1/current-summoner"
        from requests.auth import HTTPBasicAuth
        r = requests.get(url, auth=HTTPBasicAuth("riot", password), verify=False, timeout=5)
        if r.status_code == 200:
            j    = r.json()
            name = j.get("gameName") or j.get("displayName") or ""
            return (name or None), ("" if name else "No name in LCU response")
        return None, f"LCU returned {r.status_code}"
    except Exception as e:
        return None, str(e)


# ---------------------------------------------------------------------------
# Auto-update: check GitHub Releases
# ---------------------------------------------------------------------------

def check_for_update(current_version, repo="BLHvibe/The-Rift", on_done=None):
    """
    Background check for a newer GitHub release.
    on_done(latest_tag, download_url) if a newer version exists.
    on_done(None, None) if up-to-date or check fails.
    Versions compared as raw strings; tags like 'v1.2' match '1.2'.
    """
    def _parse(v):
        parts = v.lstrip("v").split(".")
        try:
            return tuple(int(x) for x in parts)
        except ValueError:
            return (0,)

    def _bg():
        try:
            import urllib.request, json, ssl
            url = f"https://api.github.com/repos/{repo}/releases/latest"
            req = urllib.request.Request(
                url, headers={"User-Agent": "TheRift/updater"})
            # Use an unverified SSL context so the check works inside
            # PyInstaller frozen bundles, which lack the system CA bundle.
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
                data = json.loads(resp.read())
            latest_tag   = data.get("tag_name", "")
            assets       = data.get("assets", [])
            download_url = assets[0]["browser_download_url"] if assets else data.get("html_url", "")
            if latest_tag and _parse(latest_tag) > _parse(current_version):
                if on_done:
                    on_done(latest_tag, download_url)
            else:
                if on_done:
                    on_done(None, None)
        except Exception:
            if on_done:
                on_done(None, None)
    threading.Thread(target=_bg, daemon=True, name="update_check").start()
