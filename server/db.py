"""
db.py — The Rift: persistent match store (Phase 0d).

A thin SQLite layer for the draft-sync server. Holds inhouse + scouted match
data at *match granularity* — the per-game participant rows the app and the
draft engine need, but which the Sheets pipeline currently aggregates away.

The DB file lives on the mounted Fly volume (/data) so it survives machine
suspend/restart; locally (no volume) it falls back to ./rift.db beside this
file. Zero third-party deps — sqlite3 is stdlib.

Purely additive: nothing in main.py's WebSocket draft path touches this.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

_LOCK = threading.Lock()
_CONN: Optional[sqlite3.Connection] = None


def _db_path() -> str:
    env = os.environ.get("RIFT_DB_PATH")
    if env:
        return env
    # The Fly volume is mounted at /data; fall back to cwd for local dev.
    if os.path.isdir("/data"):
        return "/data/rift.db"
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "rift.db")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    id          TEXT PRIMARY KEY,
    source      TEXT,
    queue       TEXT,
    patch       TEXT,
    duration    INTEGER,
    started_at  TEXT,
    winner      TEXT,
    ingested_at TEXT
);
CREATE TABLE IF NOT EXISTS participants (
    match_id  TEXT,
    slot      INTEGER,
    player    TEXT,
    riot_id   TEXT,
    team      TEXT,
    role      TEXT,
    champion  TEXT,
    win       INTEGER,
    kills     INTEGER,
    deaths    INTEGER,
    assists   INTEGER,
    cs        INTEGER,
    gold      INTEGER,
    damage    INTEGER,
    vision    INTEGER,
    PRIMARY KEY (match_id, team, slot)
);
CREATE TABLE IF NOT EXISTS drafts (
    match_id   TEXT PRIMARY KEY,
    blue_bans  TEXT,
    red_bans   TEXT,
    blue_picks TEXT,
    red_picks  TEXT
);
CREATE TABLE IF NOT EXISTS seasons (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    start_at    TEXT NOT NULL,
    end_at      TEXT,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS predictions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id    TEXT NOT NULL,
    voter       TEXT NOT NULL,
    predicted   TEXT NOT NULL,
    confidence  REAL,
    created_at  TEXT,
    UNIQUE(match_id, voter)
);
CREATE TABLE IF NOT EXISTS achievements (
    player     TEXT NOT NULL,
    code       TEXT NOT NULL,
    unlocked_at TEXT,
    match_id   TEXT,
    payload    TEXT,
    PRIMARY KEY (player, code)
);
CREATE INDEX IF NOT EXISTS ix_participants_player ON participants(player);
CREATE INDEX IF NOT EXISTS ix_participants_champ  ON participants(champion);
CREATE INDEX IF NOT EXISTS ix_matches_source      ON matches(source);
CREATE INDEX IF NOT EXISTS ix_matches_started     ON matches(started_at);
CREATE INDEX IF NOT EXISTS ix_predictions_match   ON predictions(match_id);
"""


def init() -> sqlite3.Connection:
    """Open (once) and return the shared connection, creating schema if absent.
    Idempotent and safe to call from any thread."""
    global _CONN
    with _LOCK:
        if _CONN is None:
            conn = sqlite3.connect(_db_path(), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.executescript(_SCHEMA)
            _migrate_participants_slot(conn)
            conn.commit()
            _CONN = conn
        return _CONN


def _migrate_participants_slot(conn: sqlite3.Connection) -> None:
    """One-shot migration: old participants PK was (match_id, team, role), which
    silently dropped Riot-API duplicates (ADC/SUP both lane=BOTTOM → role=BOT →
    overwrite). The new PK is (match_id, team, slot), with slot 1..5 unique
    inside each team. Existing rows are kept and backfilled by rowid order
    inside (match_id, team) — they'll still have only ~3/team until REPAIR
    re-fetches the full LCU payload, but no data is dropped."""
    cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(participants)").fetchall()}
    if "slot" in cols:
        return
    conn.executescript("""
        CREATE TABLE participants_new (
            match_id  TEXT,
            slot      INTEGER,
            player    TEXT,
            riot_id   TEXT,
            team      TEXT,
            role      TEXT,
            champion  TEXT,
            win       INTEGER,
            kills     INTEGER,
            deaths    INTEGER,
            assists   INTEGER,
            cs        INTEGER,
            gold      INTEGER,
            damage    INTEGER,
            vision    INTEGER,
            PRIMARY KEY (match_id, team, slot)
        );
        INSERT INTO participants_new
            (match_id, slot, player, riot_id, team, role, champion, win,
             kills, deaths, assists, cs, gold, damage, vision)
        SELECT match_id,
               ROW_NUMBER() OVER (PARTITION BY match_id, team ORDER BY rowid)
                   AS slot,
               player, riot_id, team, role, champion, win,
               kills, deaths, assists, cs, gold, damage, vision
        FROM participants;
        DROP TABLE participants;
        ALTER TABLE participants_new RENAME TO participants;
        CREATE INDEX IF NOT EXISTS ix_participants_player ON participants(player);
        CREATE INDEX IF NOT EXISTS ix_participants_champ  ON participants(champion);
    """)


def _conn() -> sqlite3.Connection:
    return _CONN if _CONN is not None else init()


def _int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return 0


def _norm_eligible(eligible: Optional[Iterable[str]]) -> Optional[List[str]]:
    """Normalize a user-supplied roster whitelist. Returns None when the caller
    didn't filter; otherwise a de-duplicated, non-empty list of strings."""
    if eligible is None:
        return None
    seen: Dict[str, None] = {}
    for n in eligible:
        if n is None:
            continue
        s = str(n).strip()
        if s and s not in seen:
            seen[s] = None
    return list(seen.keys()) if seen else None


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def upsert_match(m: Dict[str, Any]) -> str:
    """Insert or replace one match (+ its participants + draft). Returns the
    match id. Raises ValueError when the payload has no id."""
    mid = str((m or {}).get("id") or "").strip()
    if not mid:
        raise ValueError("match id required")
    conn = _conn()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _LOCK:
        conn.execute(
            "INSERT OR REPLACE INTO matches "
            "(id, source, queue, patch, duration, started_at, winner, ingested_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (mid, m.get("source"), m.get("queue"), m.get("patch"),
             _int(m.get("duration")), m.get("started_at"), m.get("winner"), now))
        conn.execute("DELETE FROM participants WHERE match_id = ?", (mid,))
        auto_slot: Dict[str, int] = {}
        for p in (m.get("participants") or []):
            team = (p.get("team") or "").lower()
            slot = p.get("slot")
            try:
                slot = int(slot) if slot is not None else None
            except (TypeError, ValueError):
                slot = None
            if slot is None or slot <= 0:
                auto_slot[team] = auto_slot.get(team, 0) + 1
                slot = auto_slot[team]
            conn.execute(
                "INSERT OR REPLACE INTO participants "
                "(match_id, slot, player, riot_id, team, role, champion, win, "
                " kills, deaths, assists, cs, gold, damage, vision) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (mid, slot, p.get("player"), p.get("riot_id"), p.get("team"),
                 p.get("role"), p.get("champion"), _int(p.get("win")),
                 _int(p.get("kills")), _int(p.get("deaths")),
                 _int(p.get("assists")), _int(p.get("cs")), _int(p.get("gold")),
                 _int(p.get("damage")), _int(p.get("vision"))))
        d = m.get("draft") or {}
        if d:
            conn.execute(
                "INSERT OR REPLACE INTO drafts "
                "(match_id, blue_bans, red_bans, blue_picks, red_picks) "
                "VALUES (?,?,?,?,?)",
                (mid, json.dumps(d.get("blue_bans") or []),
                 json.dumps(d.get("red_bans") or []),
                 json.dumps(d.get("blue_picks") or {}),
                 json.dumps(d.get("red_picks") or {})))
        conn.commit()
    return mid


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def _draft_to_dict(dr: sqlite3.Row) -> Dict[str, Any]:
    return {
        "blue_bans":  json.loads(dr["blue_bans"]  or "[]"),
        "red_bans":   json.loads(dr["red_bans"]   or "[]"),
        "blue_picks": json.loads(dr["blue_picks"] or "{}"),
        "red_picks":  json.loads(dr["red_picks"]  or "{}"),
    }


def get_match(match_id: str) -> Optional[Dict[str, Any]]:
    """Full match — header + participants + draft — or None if not found."""
    conn = _conn()
    mr = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    if mr is None:
        return None
    out = dict(mr)
    out["participants"] = [dict(p) for p in conn.execute(
        "SELECT * FROM participants WHERE match_id = ?", (match_id,)).fetchall()]
    dr = conn.execute("SELECT * FROM drafts WHERE match_id = ?",
                      (match_id,)).fetchone()
    out["draft"] = _draft_to_dict(dr) if dr is not None else None
    return out


def list_matches(source: Optional[str] = None,
                 limit: int = 200) -> List[Dict[str, Any]]:
    """Match headers, newest first. Optionally filtered by source."""
    conn = _conn()
    if source:
        rows = conn.execute(
            "SELECT * FROM matches WHERE source = ? "
            "ORDER BY started_at DESC LIMIT ?", (source, int(limit))).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM matches ORDER BY started_at DESC LIMIT ?",
            (int(limit),)).fetchall()
    return [dict(r) for r in rows]


def player_matches(name: str, limit: int = 200) -> List[Dict[str, Any]]:
    """Match headers a given player appears in, newest first."""
    conn = _conn()
    rows = conn.execute(
        "SELECT m.* FROM matches m "
        "JOIN participants p ON p.match_id = m.id "
        "WHERE p.player = ? ORDER BY m.started_at DESC LIMIT ?",
        (name, int(limit))).fetchall()
    return [dict(r) for r in rows]


def rivalries(name: str, limit: int = 50,
              eligible: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    """Phase 3 — head-to-head record between `name` and every other player
    they've shared a match with. Returns rows sorted by total games together
    (vs + with) descending. Each row:
      {opponent, games_vs, wins_vs, games_with, wins_with, last_played}.

    `eligible`, when provided, restricts opponents to the roster set so random
    fill players don't show up in the rivalries view.
    """
    conn = _conn()
    elig = _norm_eligible(eligible)
    args: List[Any] = [name]
    if elig is None:
        opp_filter = ""
    else:
        ph = ",".join("?" * len(elig))
        opp_filter = f" AND other.player IN ({ph})"
        args.extend(elig)
    rows = conn.execute(
        f"""
        SELECT
            other.player AS opponent,
            mine.team    AS my_team,
            other.team   AS their_team,
            mine.win     AS my_win,
            m.started_at AS started_at
        FROM participants mine
        JOIN participants other
            ON other.match_id = mine.match_id
           AND other.player   != mine.player
        JOIN matches m ON m.id = mine.match_id
        WHERE mine.player = ?{opp_filter}
        """,
        args).fetchall()

    agg: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        opp = r["opponent"]
        if not opp:
            continue
        slot = agg.setdefault(opp, {
            "opponent":    opp,
            "games_vs":    0, "wins_vs":   0,
            "games_with":  0, "wins_with": 0,
            "last_played": None,
        })
        same_team = (r["my_team"] == r["their_team"])
        win = bool(r["my_win"])
        if same_team:
            slot["games_with"] += 1
            if win: slot["wins_with"] += 1
        else:
            slot["games_vs"] += 1
            if win: slot["wins_vs"] += 1
        ts = r["started_at"]
        if ts and (slot["last_played"] is None or ts > slot["last_played"]):
            slot["last_played"] = ts

    out = list(agg.values())
    out.sort(key=lambda x: -(x["games_vs"] + x["games_with"]))
    return out[:int(limit)]


def records(eligible: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Phase 3 — curated league records / superlatives. Each entry is None
    (no data yet) or a dict with the holder + numeric value + match context.
    Cheap to compute against a small inhouse DB; safe to call per request.

    `eligible`, when provided, restricts player-keyed records to that roster
    set, and restricts match-keyed records (longest/shortest/blowout) to
    matches that include at least one eligible player. Fill-only customs
    drop out entirely."""
    conn = _conn()
    elig = _norm_eligible(eligible)
    out: Dict[str, Any] = {}

    # SQL fragments + bind args for the player / match filters.
    if elig is None:
        p_filter, p_args = "", []
        m_exists_filter, m_args = "", []
    else:
        ph = ",".join("?" * len(elig))
        p_filter = f" AND p.player IN ({ph})"
        p_args = list(elig)
        m_exists_filter = (
            f" AND EXISTS (SELECT 1 FROM participants pp "
            f"WHERE pp.match_id = m.id AND pp.player IN ({ph}))")
        m_args = list(elig)

    # --- Single-game per-row maxes ---
    def _top(col: str) -> Optional[Dict[str, Any]]:
        r = conn.execute(
            f"SELECT p.player, p.champion, p.role, p.{col} AS value, "
            f"       p.match_id, m.started_at, p.win "
            f"FROM participants p JOIN matches m ON m.id = p.match_id "
            f"WHERE p.{col} IS NOT NULL AND p.{col} > 0{p_filter} "
            f"ORDER BY p.{col} DESC LIMIT 1",
            p_args,
        ).fetchone()
        return dict(r) if r else None

    out["most_kills"]   = _top("kills")
    out["most_assists"] = _top("assists")
    out["most_damage"]  = _top("damage")
    out["most_gold"]    = _top("gold")
    out["most_cs"]      = _top("cs")
    out["most_vision"]  = _top("vision")

    # Highest KDA in a single game (Perfect KDA = deaths == 0 treated as kills+assists).
    r = conn.execute(
        "SELECT p.player, p.champion, p.role, p.kills, p.deaths, p.assists, "
        "       p.match_id, m.started_at, p.win, "
        "       CASE WHEN p.deaths = 0 THEN (p.kills + p.assists) * 1.0 "
        "            ELSE (p.kills + p.assists) * 1.0 / p.deaths END AS value "
        "FROM participants p JOIN matches m ON m.id = p.match_id "
        f"WHERE p.kills + p.deaths + p.assists > 0{p_filter} "
        "ORDER BY value DESC LIMIT 1",
        p_args,
    ).fetchone()
    out["best_kda_game"] = dict(r) if r else None

    # --- Match-level records ---
    r = conn.execute(
        "SELECT m.id AS match_id, m.duration AS value, m.started_at, m.winner "
        f"FROM matches m WHERE m.duration > 0{m_exists_filter} "
        "ORDER BY m.duration DESC LIMIT 1",
        m_args,
    ).fetchone()
    out["longest_match"] = dict(r) if r else None

    r = conn.execute(
        "SELECT m.id AS match_id, m.duration AS value, m.started_at, m.winner "
        f"FROM matches m WHERE m.duration > 0{m_exists_filter} "
        "ORDER BY m.duration ASC LIMIT 1",
        m_args,
    ).fetchone()
    out["shortest_match"] = dict(r) if r else None

    # Biggest blowout — match where the winning team's combined kills exceeds
    # the losing team's by the widest margin.
    r = conn.execute(
        "SELECT m.id AS match_id, m.started_at, m.winner, "
        "       (SELECT COALESCE(SUM(kills), 0) FROM participants "
        "          WHERE match_id = m.id AND team = m.winner) "
        "     - (SELECT COALESCE(SUM(kills), 0) FROM participants "
        "          WHERE match_id = m.id AND team != m.winner) AS value "
        "FROM matches m "
        f"WHERE m.winner IS NOT NULL{m_exists_filter} "
        "ORDER BY value DESC LIMIT 1",
        m_args,
    ).fetchone()
    out["biggest_blowout"] = dict(r) if r else None

    # --- Per-player streaks (longest win / longest loss) ---
    rows = conn.execute(
        "SELECT p.player, p.win, m.started_at "
        "FROM participants p JOIN matches m ON m.id = p.match_id "
        f"WHERE p.player IS NOT NULL AND p.win IS NOT NULL{p_filter} "
        "ORDER BY p.player ASC, m.started_at ASC",
        p_args,
    ).fetchall()
    streaks: Dict[str, Dict[str, int]] = {}
    for r in rows:
        p = r["player"]
        s = streaks.setdefault(p, {"longest_win": 0, "longest_loss": 0,
                                   "cur_win": 0, "cur_loss": 0})
        if r["win"]:
            s["cur_win"] += 1
            s["cur_loss"] = 0
            if s["cur_win"] > s["longest_win"]:
                s["longest_win"] = s["cur_win"]
        else:
            s["cur_loss"] += 1
            s["cur_win"] = 0
            if s["cur_loss"] > s["longest_loss"]:
                s["longest_loss"] = s["cur_loss"]

    out["longest_win_streak"] = None
    out["longest_loss_streak"] = None
    if streaks:
        top_w = max(streaks.items(), key=lambda x: x[1]["longest_win"])
        if top_w[1]["longest_win"] > 0:
            out["longest_win_streak"] = {"player": top_w[0],
                                         "value":  top_w[1]["longest_win"]}
        top_l = max(streaks.items(), key=lambda x: x[1]["longest_loss"])
        if top_l[1]["longest_loss"] > 0:
            out["longest_loss_streak"] = {"player": top_l[0],
                                          "value":  top_l[1]["longest_loss"]}

    # Most games logged (per player).
    r = conn.execute(
        "SELECT p.player, COUNT(*) AS value "
        "FROM participants p "
        f"WHERE p.player IS NOT NULL{p_filter} "
        "GROUP BY p.player ORDER BY value DESC LIMIT 1",
        p_args,
    ).fetchone()
    out["most_games"] = dict(r) if r else None

    return out


def stats() -> Dict[str, Any]:
    """Quick health/coverage numbers for the data API's /stats endpoint."""
    conn = _conn()
    nm    = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    npart = conn.execute("SELECT COUNT(*) FROM participants").fetchone()[0]
    last  = conn.execute("SELECT MAX(ingested_at) FROM matches").fetchone()[0]
    return {"matches": nm, "participants": npart, "last_ingest": last,
            "db_path": _db_path()}


# ---------------------------------------------------------------------------
# Phase 4c — Seasons
# ---------------------------------------------------------------------------

def list_seasons() -> List[Dict[str, Any]]:
    """All seasons in chronological order (oldest first). Each row gains a
    `match_count` and `is_active` (no end_at, or end_at in the future)."""
    conn = _conn()
    rows = conn.execute(
        "SELECT id, name, start_at, end_at, created_at FROM seasons "
        "ORDER BY start_at ASC"
    ).fetchall()
    out: List[Dict[str, Any]] = []
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for r in rows:
        d = dict(r)
        # Match count for this date window
        end_filter = d["end_at"] or now
        cnt = conn.execute(
            "SELECT COUNT(*) FROM matches "
            "WHERE started_at IS NOT NULL "
            "  AND started_at >= ? AND started_at <= ?",
            (d["start_at"], end_filter)).fetchone()[0]
        d["match_count"] = cnt
        d["is_active"] = (d["end_at"] is None) or (d["end_at"] > now)
        out.append(d)
    return out


def create_season(name: str, start_at: str,
                  end_at: Optional[str] = None) -> Dict[str, Any]:
    """Create a new season. If another season is active and end_at is None,
    closes the previous one automatically at the new season's start."""
    if not name or not start_at:
        raise ValueError("season name and start_at required")
    conn = _conn()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _LOCK:
        if end_at is None:
            # Close any currently-active season at this start point so windows
            # don't overlap.
            conn.execute(
                "UPDATE seasons SET end_at = ? "
                "WHERE end_at IS NULL AND start_at < ?",
                (start_at, start_at))
        cur = conn.execute(
            "INSERT INTO seasons (name, start_at, end_at, created_at) "
            "VALUES (?,?,?,?)",
            (name, start_at, end_at, now))
        sid = cur.lastrowid
        conn.commit()
    return {"id": sid, "name": name, "start_at": start_at,
            "end_at": end_at, "created_at": now,
            "match_count": 0, "is_active": end_at is None}


def _season_window(season_id: int) -> Optional[tuple]:
    conn = _conn()
    r = conn.execute(
        "SELECT start_at, end_at FROM seasons WHERE id = ?",
        (int(season_id),)).fetchone()
    if r is None:
        return None
    end = r["end_at"] or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return (r["start_at"], end)


def season_standings(season_id: int,
                     eligible: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Per-player standings inside a season window — games, wins, losses,
    win-rate, KDA. Sorted by wins desc, then WR desc, then games desc.

    `eligible`, when provided, restricts the per-player aggregation to the
    roster set."""
    win = _season_window(season_id)
    if win is None:
        return {"season_id": int(season_id), "standings": [],
                "error": "season not found"}
    start_at, end_at = win
    conn = _conn()
    elig = _norm_eligible(eligible)
    args: List[Any] = [start_at, end_at]
    if elig is None:
        elig_filter = ""
    else:
        ph = ",".join("?" * len(elig))
        elig_filter = f" AND p.player IN ({ph})"
        args.extend(elig)
    rows = conn.execute(
        f"""
        SELECT p.player AS player,
               COUNT(*) AS games,
               SUM(CASE WHEN p.win = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(p.kills)   AS kills,
               SUM(p.deaths)  AS deaths,
               SUM(p.assists) AS assists
        FROM participants p
        JOIN matches m ON m.id = p.match_id
        WHERE p.player IS NOT NULL
          AND m.started_at >= ?
          AND m.started_at <= ?{elig_filter}
        GROUP BY p.player
        """,
        args).fetchall()
    out = []
    for r in rows:
        games = int(r["games"] or 0)
        wins  = int(r["wins"] or 0)
        if not games:
            continue
        losses = games - wins
        wr = wins / games * 100.0
        k = int(r["kills"] or 0)
        d = int(r["deaths"] or 0)
        a = int(r["assists"] or 0)
        kda = ((k + a) / d) if d > 0 else float(k + a)
        out.append({
            "player": r["player"],
            "games": games, "wins": wins, "losses": losses,
            "wr": round(wr, 1), "kda": round(kda, 2),
            "k": k, "d": d, "a": a,
        })
    out.sort(key=lambda x: (-x["wins"], -x["wr"], -x["games"]))
    for i, row in enumerate(out):
        row["rank"] = i + 1
    return {"season_id": int(season_id),
            "window": {"start_at": start_at, "end_at": end_at},
            "standings": out}


def auto_seed_season() -> Optional[Dict[str, Any]]:
    """If no seasons exist yet, create a default Season 1 covering every match
    in the DB. The start date is the earliest logged match (or today if the
    DB is empty), so the existing inhouse history shows up immediately.

    Also self-heals an old Season 1 whose start_at is AFTER its earliest match
    — that misconfiguration happened on the first deploy when the seed was
    written before any matches existed.

    Returns the (possibly updated) Season 1 dict, or None when there are
    multiple seasons (don't touch user-curated state)."""
    conn = _conn()
    cnt = conn.execute("SELECT COUNT(*) FROM seasons").fetchone()[0]
    if cnt > 1:
        return None
    earliest = conn.execute(
        "SELECT MIN(started_at) AS s FROM matches WHERE started_at IS NOT NULL"
    ).fetchone()
    earliest_at = earliest["s"] if earliest else None

    if cnt == 0:
        start = earliest_at or time.strftime(
            "%Y-%m-%dT00:00:00Z", time.gmtime())
        return create_season("Season 1", start, None)

    # Exactly one season — self-heal if its start excludes existing matches.
    row = conn.execute(
        "SELECT id, name, start_at, end_at FROM seasons LIMIT 1").fetchone()
    if row is None or earliest_at is None:
        return None
    if row["start_at"] > earliest_at:
        with _LOCK:
            conn.execute("UPDATE seasons SET start_at = ? WHERE id = ?",
                         (earliest_at, row["id"]))
            conn.commit()
    return None


# ---------------------------------------------------------------------------
# Phase 5a — Achievements (server-side derivation)
# ---------------------------------------------------------------------------

# (code, label, description, predicate name)
_ACHIEVEMENT_CATALOG = [
    ("first_blood",     "First Steps",   "Logged your first inhouse game.",          "any_game"),
    ("first_win",       "First Win",     "Picked up your first inhouse win.",        "any_win"),
    ("pentakill",       "Pentakill",     "Recorded 5+ kills with 0 deaths.",         "ace"),
    ("flawless",        "Flawless",      "Survived a full game without dying.",      "no_deaths"),
    ("carry",           "Carry Mode",    "20+ kills in a single game.",              "twenty_kills"),
    ("damage_dealer",   "Damage Dealer", "Dealt 30K+ damage in one game.",           "thirty_k_dmg"),
    ("vision_warden",   "Vision Warden", "Posted 30+ vision score in one game.",     "high_vision"),
    ("streak3",         "Heating Up",    "Won 3 inhouse games in a row.",            "streak3"),
    ("streak5",         "On Fire",       "Won 5 inhouse games in a row.",            "streak5"),
    ("century",         "Centurion",     "Played 100 inhouse games.",                "century"),
    ("comeback",        "Comeback Kid",  "Won a game after being down 10+ kills.",   "comeback"),
]


def list_achievements() -> List[Dict[str, str]]:
    return [{"code": c, "label": l, "description": d}
            for (c, l, d, _) in _ACHIEVEMENT_CATALOG]


def _player_first_win(conn, player) -> Optional[Dict[str, Any]]:
    r = conn.execute(
        "SELECT p.match_id, m.started_at FROM participants p "
        "JOIN matches m ON m.id = p.match_id "
        "WHERE p.player = ? AND p.win = 1 "
        "ORDER BY m.started_at ASC LIMIT 1", (player,)).fetchone()
    return dict(r) if r else None


def _player_first_game(conn, player) -> Optional[Dict[str, Any]]:
    r = conn.execute(
        "SELECT p.match_id, m.started_at FROM participants p "
        "JOIN matches m ON m.id = p.match_id "
        "WHERE p.player = ? "
        "ORDER BY m.started_at ASC LIMIT 1", (player,)).fetchone()
    return dict(r) if r else None


def player_achievements(player: str) -> List[Dict[str, Any]]:
    """Compute the set of achievements unlocked by `player` from match data."""
    if not player:
        return []
    conn = _conn()
    unlocked: List[Dict[str, Any]] = []

    def _add(code: str, ctx: Optional[Dict[str, Any]] = None):
        meta = next((a for a in _ACHIEVEMENT_CATALOG if a[0] == code), None)
        if not meta:
            return
        unlocked.append({
            "code": code,
            "label": meta[1],
            "description": meta[2],
            "match_id": (ctx or {}).get("match_id"),
            "unlocked_at": (ctx or {}).get("started_at"),
        })

    # first_blood / first_win
    fg = _player_first_game(conn, player)
    if fg:
        _add("first_blood", fg)
    fw = _player_first_win(conn, player)
    if fw:
        _add("first_win", fw)

    # Per-game predicates
    rows = conn.execute(
        "SELECT p.match_id, m.started_at, p.kills, p.deaths, p.assists, "
        "       p.damage, p.vision, p.win, p.team "
        "FROM participants p JOIN matches m ON m.id = p.match_id "
        "WHERE p.player = ? ORDER BY m.started_at ASC", (player,)).fetchall()
    has_ace = has_flawless = has_carry = has_30k = has_vis = has_comeback = False
    games_count = len(rows)
    cur_win = 0
    longest_win = 0
    for r in rows:
        k = r["kills"] or 0
        d = r["deaths"] or 0
        a = r["assists"] or 0
        dmg = r["damage"] or 0
        vis = r["vision"] or 0
        win = bool(r["win"])

        ctx = {"match_id": r["match_id"], "started_at": r["started_at"]}
        if k >= 5 and d == 0 and not has_ace:
            has_ace = True; _add("pentakill", ctx)
        if d == 0 and (k + a) > 0 and not has_flawless:
            has_flawless = True; _add("flawless", ctx)
        if k >= 20 and not has_carry:
            has_carry = True; _add("carry", ctx)
        if dmg >= 30000 and not has_30k:
            has_30k = True; _add("damage_dealer", ctx)
        if vis >= 30 and not has_vis:
            has_vis = True; _add("vision_warden", ctx)

        # Comeback: won the game with a team kill-deficit at start... approximate
        # using total team kills vs opponent total being lower at end is not
        # comeback; lacking timeline, we treat 'comeback' as won with -10+ KD
        # vs opp on a per-player basis (kills - assists - deaths).
        if win and not has_comeback:
            tot = conn.execute(
                "SELECT team, SUM(kills) AS k FROM participants "
                "WHERE match_id = ? GROUP BY team",
                (r["match_id"],)).fetchall()
            blue = next((x["k"] for x in tot if x["team"] == "blue"), 0) or 0
            red  = next((x["k"] for x in tot if x["team"] == "red"),  0) or 0
            my_team = r["team"]
            my_k    = blue if my_team == "blue" else red
            opp_k   = red  if my_team == "blue" else blue
            # If my team won but team kills are within 2 of opponent it's not
            # really a comeback; but if my team won with a >=10 team-kill deficit
            # at some point... we don't have intermediate. Use: my team won and
            # opp had MORE total kills than mine (negative net) — proxy.
            if my_k + 10 <= opp_k:
                has_comeback = True; _add("comeback", ctx)

        # Streaks
        if win:
            cur_win += 1
            longest_win = max(longest_win, cur_win)
        else:
            cur_win = 0

    if longest_win >= 3:
        _add("streak3")
    if longest_win >= 5:
        _add("streak5")
    if games_count >= 100:
        _add("century")

    return unlocked


# ---------------------------------------------------------------------------
# Phase 5b — Predictions
# ---------------------------------------------------------------------------

def add_prediction(match_id: str, voter: str, predicted: str,
                   confidence: Optional[float] = None) -> Dict[str, Any]:
    if not match_id or not voter or not predicted:
        raise ValueError("match_id, voter, predicted are required")
    if predicted not in ("blue", "red"):
        raise ValueError("predicted must be 'blue' or 'red'")
    conn = _conn()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _LOCK:
        conn.execute(
            "INSERT OR REPLACE INTO predictions "
            "(match_id, voter, predicted, confidence, created_at) "
            "VALUES (?,?,?,?,?)",
            (match_id, voter, predicted, confidence, now))
        conn.commit()
    return {"ok": True, "match_id": match_id, "voter": voter,
            "predicted": predicted, "created_at": now}


def match_predictions(match_id: str) -> List[Dict[str, Any]]:
    if not match_id:
        return []
    conn = _conn()
    rows = conn.execute(
        "SELECT voter, predicted, confidence, created_at "
        "FROM predictions WHERE match_id = ?", (match_id,)).fetchall()
    return [dict(r) for r in rows]


def prediction_leaderboard(limit: int = 50,
                           eligible: Optional[Iterable[str]] = None
                           ) -> List[Dict[str, Any]]:
    """Per-voter prediction accuracy. A prediction is correct when the match's
    `winner` matches `predicted`. Only counts matches that have a winner.

    `eligible`, when provided, restricts the leaderboard to voters in the
    roster set."""
    conn = _conn()
    elig = _norm_eligible(eligible)
    args: List[Any] = []
    if elig is None:
        voter_filter = ""
    else:
        ph = ",".join("?" * len(elig))
        voter_filter = f" AND pr.voter IN ({ph})"
        args.extend(elig)
    args.append(int(limit))
    rows = conn.execute(
        f"""
        SELECT pr.voter AS voter,
               COUNT(*) AS total,
               SUM(CASE WHEN m.winner = pr.predicted THEN 1 ELSE 0 END) AS correct
        FROM predictions pr
        JOIN matches m ON m.id = pr.match_id
        WHERE m.winner IS NOT NULL AND m.winner != ''{voter_filter}
        GROUP BY pr.voter
        ORDER BY correct DESC, total DESC
        LIMIT ?
        """, args).fetchall()
    out = []
    for r in rows:
        total = int(r["total"] or 0)
        correct = int(r["correct"] or 0)
        acc = (correct / total * 100.0) if total else 0.0
        out.append({"voter": r["voter"], "total": total,
                    "correct": correct, "accuracy": round(acc, 1)})
    return out


def export_all() -> Dict[str, Any]:
    """Dump every row — used by the Sheet-mirror backup job."""
    conn = _conn()
    return {
        "matches": [dict(r) for r in
                    conn.execute("SELECT * FROM matches").fetchall()],
        "participants": [dict(r) for r in
                         conn.execute("SELECT * FROM participants").fetchall()],
        "drafts": [dict(r) for r in
                   conn.execute("SELECT * FROM drafts").fetchall()],
    }
