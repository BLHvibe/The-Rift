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
CREATE TABLE IF NOT EXISTS players (
    display_name TEXT PRIMARY KEY COLLATE NOCASE,
    riot_id      TEXT,
    game_name    TEXT COLLATE NOCASE,
    tagline      TEXT,
    updated_at   TEXT
);
CREATE TABLE IF NOT EXISTS rankings (
    display_name  TEXT PRIMARY KEY COLLATE NOCASE,
    rank_position INTEGER,
    tier          TEXT,
    division      TEXT,
    avg_tier      TEXT,
    tier_score    TEXT,
    rank_score    TEXT,
    final_score   TEXT,
    rating        TEXT,
    lp            INTEGER,
    wins          INTEGER,
    losses        INTEGER,
    games         INTEGER,
    wr            REAL,
    updated_at    TEXT
);
CREATE TABLE IF NOT EXISTS scout_stats (
    display_name   TEXT PRIMARY KEY COLLATE NOCASE,
    kda            REAL,
    form           TEXT,
    top_champs     TEXT,       -- JSON array of champion names
    wr_from_stats  INTEGER,
    games_fallback INTEGER,
    wins_fallback  INTEGER,
    avg_kills      REAL,
    avg_deaths     REAL,
    avg_assists    REAL,
    updated_at     TEXT
);
CREATE TABLE IF NOT EXISTS rank_history (
    display_name TEXT,
    sampled_at   TEXT,
    value        INTEGER,
    tier         TEXT,
    division     TEXT,
    PRIMARY KEY (display_name, sampled_at)
);
CREATE TABLE IF NOT EXISTS tier_votes (
    rater_name  TEXT NOT NULL COLLATE NOCASE,
    player_name TEXT NOT NULL COLLATE NOCASE,
    rating      TEXT NOT NULL,        -- 'S','A','B','C','D','F'
    updated_at  TEXT,
    PRIMARY KEY (rater_name, player_name)
);
CREATE INDEX IF NOT EXISTS ix_tier_votes_player ON tier_votes(player_name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS ix_tier_votes_rater  ON tier_votes(rater_name  COLLATE NOCASE);
CREATE TABLE IF NOT EXISTS activity_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    actor       TEXT,
    details     TEXT,
    related     TEXT
);
CREATE INDEX IF NOT EXISTS ix_activity_occurred ON activity_events(occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_activity_actor    ON activity_events(actor);
CREATE TABLE IF NOT EXISTS scout_sheets (
    display_name TEXT PRIMARY KEY COLLATE NOCASE,
    payload      TEXT,
    updated_at   TEXT
);
CREATE INDEX IF NOT EXISTS ix_participants_player ON participants(player);
CREATE INDEX IF NOT EXISTS ix_participants_champ  ON participants(champion);
CREATE INDEX IF NOT EXISTS ix_matches_source      ON matches(source);
CREATE INDEX IF NOT EXISTS ix_matches_started     ON matches(started_at);
CREATE INDEX IF NOT EXISTS ix_predictions_match   ON predictions(match_id);
CREATE INDEX IF NOT EXISTS ix_players_game_name   ON players(game_name COLLATE NOCASE);
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


def h2h_matrix(players: Iterable[str]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Phase 3 (v4.0.5) — full head-to-head matrix for a roster, in one trip.

    For each ordered pair (A, B) where A != B, returns the same shape that
    `rivalries()` emits per opponent:
        {games_vs, wins_vs, games_with, wins_with, last_played}

    Result is keyed as `out[A][B]`. Pairs with zero shared games are omitted
    from the inner dict so the client can render a "no data" cell. Matches
    where neither side of the pair was present are skipped automatically by
    the JOIN.
    """
    elig = _norm_eligible(players)
    out: Dict[str, Dict[str, Dict[str, Any]]] = {}
    if not elig:
        return out
    for name in elig:
        out[name] = {}
    conn = _conn()
    ph = ",".join("?" * len(elig))
    args: List[Any] = list(elig) + list(elig)
    rows = conn.execute(
        f"""
        SELECT
            mine.player  AS me,
            other.player AS opp,
            mine.team    AS my_team,
            other.team   AS their_team,
            mine.win     AS my_win,
            m.started_at AS started_at
        FROM participants mine
        JOIN participants other
            ON other.match_id = mine.match_id
           AND other.player   != mine.player
        JOIN matches m ON m.id = mine.match_id
        WHERE mine.player IN ({ph})
          AND other.player IN ({ph})
        """,
        args).fetchall()
    for r in rows:
        me, opp = r["me"], r["opp"]
        if not me or not opp:
            continue
        slot = out[me].setdefault(opp, {
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
    return out


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
# Phase A (sheet decommission) — players roster + inhouse-from-participants
# ---------------------------------------------------------------------------
#
# Goal: eliminate the client's dependency on the "Players" + "_InhouseGameLog"
# Google Sheets. The Fly DB already has match-granular data in `participants`;
# the per-player aggregates the UI consumes (leaderboard, customs champ
# stats, primary role) are all derivable from that. The `players` table
# provides the display-name ↔ riot-game-name mapping that lets us resolve
# participants (stored as riot game names like "Chupacabra117") back to the
# group's display names (e.g. "Ben").

def upsert_players(rows: Iterable[Dict[str, Any]]) -> int:
    """Bulk replace the players roster. Each row needs at minimum a
    `display_name`; `riot_id` ("GameName#Tagline") is split into
    game_name/tagline. Returns the count written. Idempotent — same input
    leaves the table unchanged. Backfill from sheets calls this once."""
    conn = _conn()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    n = 0
    with _LOCK:
        for r in (rows or []):
            if not isinstance(r, dict):
                continue
            dn = (r.get("display_name") or r.get("name") or "").strip()
            if not dn:
                continue
            riot = (r.get("riot_id") or "").strip()
            game_name = (r.get("game_name") or "").strip()
            tagline   = (r.get("tagline")   or "").strip()
            if not game_name and "#" in riot:
                game_name, _, tagline = riot.partition("#")
                game_name = game_name.strip()
                tagline   = tagline.strip()
            conn.execute(
                "INSERT OR REPLACE INTO players "
                "(display_name, riot_id, game_name, tagline, updated_at) "
                "VALUES (?,?,?,?,?)",
                (dn, riot or None, game_name or None, tagline or None, now))
            n += 1
        conn.commit()
    return n


def get_players() -> Dict[str, Any]:
    """Return the roster in the shape the client's reader.py was building from
    the Players sheet:
        {"players": [display_name, ...],
         "summoner_map": {game_name: display_name, ...},
         "riot_ids": {display_name: "GameName#Tagline", ...}}
    `riot_ids` is the source of truth for the rank refresh — it preserves the
    real per-player tagline instead of forcing every player to `#NA1`.
    Order preserves insertion (latest update bumps to the end)."""
    conn = _conn()
    rows = conn.execute(
        "SELECT display_name, riot_id, game_name, tagline FROM players "
        "ORDER BY updated_at ASC, display_name ASC"
    ).fetchall()
    players: List[str] = []
    summoner_map: Dict[str, str] = {}
    riot_ids: Dict[str, str] = {}
    for r in rows:
        dn = r["display_name"]
        gn = r["game_name"]
        if dn:
            players.append(dn)
        if gn and dn:
            summoner_map[gn] = dn
        if dn:
            rid = (r["riot_id"] or "").strip()
            if "#" not in rid and gn and r["tagline"]:
                rid = f"{gn}#{r['tagline']}"
            if "#" in rid:
                riot_ids[dn] = rid
    return {"players": players, "summoner_map": summoner_map,
            "riot_ids": riot_ids}


def _resolved_display_case_sql() -> str:
    """SQL fragment that turns `participants.player` (a riot game name) into
    the corresponding display name via the players table. Falls back to the
    raw participant name when no mapping exists, so off-roster players still
    appear under their raw name rather than being dropped."""
    # NOCASE collation on game_name index gives us a cheap case-insensitive
    # join without LOWER() wrapping (which would defeat the index).
    return (
        "COALESCE("
        "  (SELECT pl.display_name FROM players pl "
        "   WHERE pl.game_name = pa.player COLLATE NOCASE LIMIT 1),"
        "  pa.player"
        ")"
    )


def inhouse_aggregates(
    eligible: Optional[Iterable[str]] = None,
    min_team_size: int = 2,
    max_team_size: int = 10,
) -> List[Dict[str, Any]]:
    """Per-player customs leaderboard, derived from `participants` joined
    against `players` for display-name resolution.

    Matches the shape `reader.py::_read_inhouse` returned for `live.inhouse`
    so the UI rendering stays identical:
        {player, games, wins, losses, wr ("xx.x%"), kda,
         cs_min, damage ("12,345"), gold ("8,765"),
         recent_results (last 10, 1=win/0=loss), rank}

    Filtering rules mirror the old sheet path:
      * Only matches with `source = 'inhouse'` count (skips Riot-API scout).
      * Games where the participant count is outside [min_team_size,
        max_team_size] are excluded (defends against partial/garbage rows).
      * `eligible`, when provided, restricts the output to that roster.
    """
    conn = _conn()
    disp = _resolved_display_case_sql()

    # Step 1: collect per-match (match_id, display, win, k/d/a/dmg/gold) for
    # matches whose participant count is in range and source is inhouse.
    rows = conn.execute(
        f"""
        WITH match_sizes AS (
            SELECT match_id, COUNT(*) AS n
            FROM participants
            GROUP BY match_id
        )
        SELECT
            pa.match_id      AS match_id,
            {disp}           AS display,
            pa.win           AS win,
            pa.kills         AS kills,
            pa.deaths        AS deaths,
            pa.assists       AS assists,
            pa.damage        AS damage,
            pa.gold          AS gold,
            m.started_at     AS started_at
        FROM participants pa
        JOIN matches m ON m.id = pa.match_id
        JOIN match_sizes ms ON ms.match_id = pa.match_id
        WHERE m.source = 'inhouse'
          AND ms.n BETWEEN ? AND ?
        ORDER BY m.started_at ASC, pa.match_id ASC
        """,
        (int(min_team_size), int(max_team_size))
    ).fetchall()

    agg: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        name = r["display"]
        if not name:
            continue
        slot = agg.setdefault(name, {
            "player": name, "games": 0, "wins": 0,
            "kills": 0, "deaths": 0, "assists": 0,
            "damage": 0, "gold": 0,
            "recent_results": [],
        })
        slot["games"]   += 1
        slot["wins"]    += 1 if r["win"] else 0
        slot["kills"]   += int(r["kills"] or 0)
        slot["deaths"]  += int(r["deaths"] or 0)
        slot["assists"] += int(r["assists"] or 0)
        slot["damage"]  += int(r["damage"] or 0)
        slot["gold"]    += int(r["gold"] or 0)
        slot["recent_results"].append(1 if r["win"] else 0)

    elig_set = None
    if eligible is not None:
        elig_set = {s.strip() for s in eligible if s}

    out: List[Dict[str, Any]] = []
    for name, slot in agg.items():
        if elig_set is not None and name not in elig_set:
            continue
        g = slot["games"]
        if g == 0:
            continue
        w = slot["wins"]
        l = g - w
        wr_pct = round(w / g * 100, 1)
        kda = round((slot["kills"] + slot["assists"])
                    / max(slot["deaths"], 1), 1)
        avg_dmg  = round(slot["damage"] / g)
        avg_gold = round(slot["gold"]   / g)
        out.append({
            "player":         name,
            "games":          g,
            "wins":           w,
            "losses":         l,
            "wr":             f"{wr_pct}%",
            "kda":            kda,
            "cs_min":         "—",        # not stored at participant level
            "damage":         f"{avg_dmg:,}",
            "gold":           f"{avg_gold:,}",
            "recent_results": slot["recent_results"][-10:],
        })

    def _wr_key(p):
        try:
            return float(str(p["wr"]).replace("%", ""))
        except (ValueError, TypeError):
            return 0.0

    out.sort(key=lambda p: (_wr_key(p), p["games"]), reverse=True)
    for i, p in enumerate(out):
        p["rank"] = i + 1
    return out


def inhouse_champs(
    eligible: Optional[Iterable[str]] = None,
    min_team_size: int = 2,
    max_team_size: int = 10,
    recency_cap: int = 100,
) -> Dict[str, List[Dict[str, Any]]]:
    """Per-player champion-comfort dict, derived from `participants`. Shape:
        {display_name: [{champ, games, wins, losses, wr, kda,
                         kills, deaths, assists, damage,
                         results (last `recency_cap` chronological 1/0),
                         recent_results (last 20),
                         roles {role: count}}]}

    This is the most important consumer of the data layer — the draft
    engine reads it as `inhouse_champs` and turns customs play into the
    strongest comfort signal. Sort: most games first, like the sheet path.
    """
    conn = _conn()
    disp = _resolved_display_case_sql()
    rows = conn.execute(
        f"""
        WITH match_sizes AS (
            SELECT match_id, COUNT(*) AS n
            FROM participants GROUP BY match_id
        )
        SELECT
            {disp}     AS display,
            pa.champion AS champion,
            pa.role     AS role,
            pa.win      AS win,
            pa.kills    AS kills,
            pa.deaths   AS deaths,
            pa.assists  AS assists,
            pa.damage   AS damage,
            m.started_at AS started_at
        FROM participants pa
        JOIN matches m ON m.id = pa.match_id
        JOIN match_sizes ms ON ms.match_id = pa.match_id
        WHERE m.source = 'inhouse'
          AND ms.n BETWEEN ? AND ?
          AND pa.champion IS NOT NULL AND pa.champion <> ''
        ORDER BY m.started_at ASC
        """,
        (int(min_team_size), int(max_team_size))
    ).fetchall()

    elig_set = None
    if eligible is not None:
        elig_set = {s.strip() for s in eligible if s}

    nested: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for r in rows:
        name = r["display"]
        if not name:
            continue
        if elig_set is not None and name not in elig_set:
            continue
        champ = r["champion"]
        if not champ:
            continue
        by_champ = nested.setdefault(name, {})
        slot = by_champ.setdefault(champ, {
            "champ": champ, "games": 0, "wins": 0,
            "kills": 0, "deaths": 0, "assists": 0,
            "damage": 0,
            "results": [],
            "roles":   {},
        })
        slot["games"]   += 1
        slot["wins"]    += 1 if r["win"] else 0
        slot["kills"]   += int(r["kills"]   or 0)
        slot["deaths"]  += int(r["deaths"]  or 0)
        slot["assists"] += int(r["assists"] or 0)
        slot["damage"]  += int(r["damage"]  or 0)
        slot["results"].append(1 if r["win"] else 0)
        role = (r["role"] or "").upper()
        if role in ("TOP", "JGL", "MID", "BOT", "SUP"):
            slot["roles"][role] = slot["roles"].get(role, 0) + 1

    out: Dict[str, List[Dict[str, Any]]] = {}
    for name, by_champ in nested.items():
        champs: List[Dict[str, Any]] = []
        for champ_name, slot in by_champ.items():
            g = slot["games"]
            if g == 0:
                continue
            wr = round(slot["wins"] / g * 100, 1)
            kda = round((slot["kills"] + slot["assists"])
                        / max(slot["deaths"], 1), 1)
            champs.append({
                "champ":          champ_name,
                "games":          g,
                "wins":           slot["wins"],
                "losses":         g - slot["wins"],
                "wr":             f"{wr}%",
                "kda":            kda,
                "kills":          round(slot["kills"]   / g, 1),
                "deaths":         round(slot["deaths"]  / g, 1),
                "assists":        round(slot["assists"] / g, 1),
                "damage":         f"{round(slot['damage'] / g):,}",
                "results":        slot["results"][-int(recency_cap):],
                "recent_results": slot["results"][-20:],
                "roles":          dict(slot["roles"]),
            })
        champs.sort(key=lambda x: x["games"], reverse=True)
        out[name] = champs
    return out


def primary_roles(
    eligible: Optional[Iterable[str]] = None,
    min_team_size: int = 2,
    max_team_size: int = 10,
) -> Dict[str, str]:
    """Per-player primary role (most-played role across customs). Shape
    `{display_name: "TOP"|"JGL"|"MID"|"BOT"|"SUP"}`. Players with no role
    data are omitted."""
    conn = _conn()
    disp = _resolved_display_case_sql()
    rows = conn.execute(
        f"""
        WITH match_sizes AS (
            SELECT match_id, COUNT(*) AS n
            FROM participants GROUP BY match_id
        )
        SELECT
            {disp}  AS display,
            pa.role AS role,
            COUNT(*) AS n
        FROM participants pa
        JOIN matches m ON m.id = pa.match_id
        JOIN match_sizes ms ON ms.match_id = pa.match_id
        WHERE m.source = 'inhouse'
          AND ms.n BETWEEN ? AND ?
          AND pa.role IN ('TOP','JGL','MID','BOT','SUP')
        GROUP BY display, pa.role
        """,
        (int(min_team_size), int(max_team_size))
    ).fetchall()

    elig_set = None
    if eligible is not None:
        elig_set = {s.strip() for s in eligible if s}

    by_player: Dict[str, Dict[str, int]] = {}
    for r in rows:
        name = r["display"]
        if not name:
            continue
        if elig_set is not None and name not in elig_set:
            continue
        by_player.setdefault(name, {})[r["role"]] = int(r["n"] or 0)

    out: Dict[str, str] = {}
    for name, roles in by_player.items():
        if not roles:
            continue
        out[name] = max(roles, key=roles.get)
    return out


# ---------------------------------------------------------------------------
# Phase B (sheet decommission) — rankings + scout stats storage
# ---------------------------------------------------------------------------
#
# These are the per-player aggregates the Riot-API fetcher used to write into
# the "Final Rankings" + "Player Stats" Google Sheets. Storing them here
# lets the client read them via REST instead of via gspread.
#
# Schemas intentionally store the "score" fields as text — the existing sheet
# pipeline keeps them as formatted strings (e.g. "5.08" for avg_tier) and the
# UI reads them that way. Migrating to typed numerics is a future cleanup.

def upsert_rankings(rows: Iterable[Dict[str, Any]]) -> int:
    """Bulk replace the per-player ranking aggregates. Each row maps to the
    'Final Rankings' sheet's columns plus the underlying rank info (LP /
    wins / losses) from 'Rank Data'.

    Required: `name` (or `display_name`).
    Optional: rank, tier, division, avg_tier, tier_score, rank_score,
              final_score (or score), rating, lp, wins, losses, games, wr."""
    conn = _conn()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    n = 0
    with _LOCK:
        for r in (rows or []):
            if not isinstance(r, dict):
                continue
            name = (r.get("display_name") or r.get("name") or "").strip()
            if not name:
                continue

            def _i(v):
                try:    return int(float(v))
                except (TypeError, ValueError): return None

            def _f(v):
                try:    return float(v)
                except (TypeError, ValueError): return None

            def _s(v):
                return None if v is None else str(v)

            conn.execute(
                "INSERT OR REPLACE INTO rankings "
                "(display_name, rank_position, tier, division, avg_tier, "
                " tier_score, rank_score, final_score, rating, lp, "
                " wins, losses, games, wr, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (name,
                 _i(r.get("rank") or r.get("rank_position")),
                 _s(r.get("tier")), _s(r.get("division")),
                 _s(r.get("avg_tier")), _s(r.get("tier_score")),
                 _s(r.get("rank_score")),
                 _s(r.get("final_score") if r.get("final_score") is not None
                    else r.get("score")),
                 _s(r.get("rating")),
                 _i(r.get("lp")), _i(r.get("wins")), _i(r.get("losses")),
                 _i(r.get("games")), _f(r.get("wr")),
                 now))
            n += 1
        conn.commit()
    return n


def get_rankings(eligible: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    """Per-player rankings list, sorted by rank_position (ascending). Mirrors
    the shape `reader.py::_read_final_rankings` produces for `live.rankings`,
    so a Phase D consumer can drop it in directly."""
    conn = _conn()
    rows = conn.execute(
        "SELECT display_name, rank_position, tier, division, avg_tier, "
        "       tier_score, rank_score, final_score, rating, lp, "
        "       wins, losses, games, wr "
        "FROM rankings "
        "ORDER BY rank_position IS NULL, rank_position ASC, display_name ASC"
    ).fetchall()
    elig_set = None
    if eligible is not None:
        elig_set = {s.strip() for s in eligible if s}
    out: List[Dict[str, Any]] = []
    for r in rows:
        name = r["display_name"]
        if elig_set is not None and name not in elig_set:
            continue
        out.append({
            "rank":        r["rank_position"] or 0,
            "name":        name,
            "tier":        r["tier"] or "Unranked",
            "division":    r["division"] or "",
            "avg_tier":    r["avg_tier"] or "",
            "tier_score":  r["tier_score"] or "",
            "rank_score":  r["rank_score"] or "",
            "final_score": r["final_score"] or "",
            "score":       r["final_score"] or "",
            "rating":      r["rating"] or "?",
            "lp":          r["lp"] or 0,
            "wins":        r["wins"] or 0,
            "losses":      r["losses"] or 0,
            "games":       r["games"] or 0,
            "wr":          r["wr"] or 0,
        })
    return out


def upsert_scout_stats(rows: Iterable[Dict[str, Any]]) -> int:
    """Bulk replace per-player scout stats (Player Stats sheet content).
    Required: `name` (or `display_name`).
    Optional: kda, form, top_champs (list[str]), wr_from_stats,
              games_fallback, wins_fallback, avg_kills/deaths/assists."""
    conn = _conn()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    n = 0
    with _LOCK:
        for r in (rows or []):
            if not isinstance(r, dict):
                continue
            name = (r.get("display_name") or r.get("name") or "").strip()
            if not name:
                continue
            tc_raw = r.get("top_champs") or []
            if not isinstance(tc_raw, list):
                tc_raw = []
            tc = [str(x) for x in tc_raw if x]
            def _f(v, default=None):
                try:    return float(v)
                except (TypeError, ValueError): return default
            def _i(v, default=None):
                try:    return int(float(v))
                except (TypeError, ValueError): return default
            conn.execute(
                "INSERT OR REPLACE INTO scout_stats "
                "(display_name, kda, form, top_champs, "
                " wr_from_stats, games_fallback, wins_fallback, "
                " avg_kills, avg_deaths, avg_assists, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (name, _f(r.get("kda")), (r.get("form") or "MIXED"),
                 json.dumps(tc),
                 _i(r.get("wr_from_stats")),
                 _i(r.get("games_fallback")),
                 _i(r.get("wins_fallback")),
                 _f(r.get("avg_kills")), _f(r.get("avg_deaths")),
                 _f(r.get("avg_assists")),
                 now))
            n += 1
        conn.commit()
    return n


def get_scout(eligible: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    """Per-player scout-tab data, returned in the shape `reader.py` produced
    by merging rankings + Player Stats. JOIN rankings ↔ scout_stats so the
    UI sees one row per player with all fields populated where possible."""
    conn = _conn()
    rows = conn.execute(
        "SELECT r.display_name AS name, "
        "       r.rank_position, r.tier, r.division, r.avg_tier, "
        "       r.tier_score, r.rank_score, r.final_score, r.rating, "
        "       r.lp, r.wins, r.losses, r.games, r.wr, "
        "       s.kda, s.form, s.top_champs, "
        "       s.wr_from_stats, s.games_fallback "
        "FROM rankings r "
        "LEFT JOIN scout_stats s ON s.display_name = r.display_name "
        "ORDER BY r.rank_position IS NULL, r.rank_position ASC, r.display_name ASC"
    ).fetchall()
    elig_set = None
    if eligible is not None:
        elig_set = {s.strip() for s in eligible if s}
    out: List[Dict[str, Any]] = []
    for r in rows:
        name = r["name"]
        if elig_set is not None and name not in elig_set:
            continue
        # Resolve wr / games with the same precedence reader.py used:
        #   wr  = rankings.wr → scout.wr_from_stats → 0
        #   games = rankings.games → scout.games_fallback → 0
        wr = r["wr"] or 0
        if not wr:
            wr = r["wr_from_stats"] or 0
        games_val = r["games"] or r["games_fallback"] or 0
        # final_score is text in the DB; surface as a float for the UI
        try:
            score_f = float(r["final_score"]) if r["final_score"] else 0.0
        except (ValueError, TypeError):
            score_f = 0.0
        try:
            top_champs = json.loads(r["top_champs"]) if r["top_champs"] else []
        except (json.JSONDecodeError, TypeError):
            top_champs = []
        out.append({
            "name":        name,
            "tier":        r["tier"] or "Unranked",
            "score":       score_f,
            "final_score": r["final_score"] or "",
            "tier_score":  r["tier_score"]  or "",
            "rank_score":  r["rank_score"]  or "",
            "rating":      r["rating"] or "?",
            "rank":        r["rank_position"] or 0,
            "wr":          int(wr) if wr else 0,
            "kda":         round(float(r["kda"] or 0.0), 1),
            "games":       int(games_val) if games_val else 0,
            "top_champs":  top_champs,
            "form":        r["form"] or "MIXED",
        })
    return out


def append_rank_history(
    rows: Iterable[Dict[str, Any]],
    sampled_at: Optional[str] = None,
) -> int:
    """Snapshot the current rank values into the time-series table. Each
    snapshot is keyed (display_name, sampled_at) so the UI can read the per-
    player sparkline. Pass `value` (the chart-friendly int 0..31) plus
    optional tier/division for label display."""
    conn = _conn()
    ts = sampled_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    n = 0
    with _LOCK:
        for r in (rows or []):
            if not isinstance(r, dict):
                continue
            name = (r.get("display_name") or r.get("name") or "").strip()
            if not name:
                continue
            try:    value = int(float(r.get("value") or 0))
            except (TypeError, ValueError): value = 0
            conn.execute(
                "INSERT OR REPLACE INTO rank_history "
                "(display_name, sampled_at, value, tier, division) "
                "VALUES (?,?,?,?,?)",
                (name, ts, value,
                 r.get("tier") or None, r.get("division") or None))
            n += 1
        conn.commit()
    return n


def get_rank_history(
    eligible: Optional[Iterable[str]] = None,
    limit_per_player: int = 30,
) -> Dict[str, List[Dict[str, Any]]]:
    """Per-player time-series of rank values (newest sample last). Returns
    `{display_name: [{sampled_at, value, tier, division}, ...]}` for sparkline
    rendering. `limit_per_player` caps the most recent samples (cheap when
    the table grows)."""
    conn = _conn()
    elig = _norm_eligible(eligible)
    if elig is None:
        rows = conn.execute(
            "SELECT display_name, sampled_at, value, tier, division "
            "FROM rank_history ORDER BY display_name ASC, sampled_at ASC"
        ).fetchall()
    else:
        ph = ",".join("?" * len(elig))
        rows = conn.execute(
            f"SELECT display_name, sampled_at, value, tier, division "
            f"FROM rank_history WHERE display_name IN ({ph}) "
            f"ORDER BY display_name ASC, sampled_at ASC", elig
        ).fetchall()
    out: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["display_name"], []).append({
            "sampled_at": r["sampled_at"],
            "value":      r["value"],
            "tier":       r["tier"] or "",
            "division":   r["division"] or "",
        })
    # Cap to most recent N per player
    if limit_per_player and limit_per_player > 0:
        for k, lst in out.items():
            if len(lst) > limit_per_player:
                out[k] = lst[-int(limit_per_player):]
    return out


# ---------------------------------------------------------------------------
# D1 (sheet decommission) — tier-list voting
# ---------------------------------------------------------------------------
#
# Replaces the Google "Tier Lists" sheet — a 2D table where rows are players
# being rated and columns are raters who submitted ratings. Each rater
# rates each player on the S/A/B/C/D/F scale. The per-player average (on
# the 1..6 numeric scale) is the `avg_tier` that historically blended into
# the Final Rankings score formula in the sheet.
#
# Drop in this migration: the legacy "Consensus & Controversy", "Hot Takes",
# and "Rater Bias" derived feeds (the tier list tab's secondary UI). The
# primary rankings blend still uses the per-player average computed here.

# S=6, A=5, B=4, C=3, D=2, F=1 — matches fetch_ranks.constants.TIER_TO_NUM.
_TIER_TO_NUM: Dict[str, int] = {"S": 6, "A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
_NUM_TO_TIER: Dict[int, str] = {v: k for k, v in _TIER_TO_NUM.items()}


def upsert_tier_votes(rater_name: str,
                      placements: Dict[str, Iterable[str]],
                      replace_rater: bool = True) -> int:
    """Persist one rater's full ballot.

    `placements` is the shape the client UI produces:
        {"S": [player1, player2], "A": [...], ..., "F": [...]}

    When `replace_rater` is True (the normal submit path) we delete every
    prior vote from this rater first so removing a player from the ballot
    drops their old rating. Set False for partial-update flows."""
    rater = (rater_name or "").strip()
    if not rater:
        raise ValueError("rater_name required")
    conn = _conn()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    n = 0
    with _LOCK:
        if replace_rater:
            conn.execute("DELETE FROM tier_votes WHERE rater_name = ?",
                         (rater,))
        for letter, names in (placements or {}).items():
            tier = str(letter or "").strip().upper()
            if tier not in _TIER_TO_NUM:
                continue
            for raw in (names or []):
                pname = str(raw or "").strip()
                if not pname:
                    continue
                conn.execute(
                    "INSERT OR REPLACE INTO tier_votes "
                    "(rater_name, player_name, rating, updated_at) "
                    "VALUES (?,?,?,?)",
                    (rater, pname, tier, now))
                n += 1
        conn.commit()
    return n


def upsert_tier_votes_grid(grid: Iterable[Dict[str, Any]]) -> int:
    """Bulk-import the existing Tier Lists sheet as a list of cells:
        [{"rater": "Ben", "player": "Luke", "rating": "A"}, ...]
    Used by the one-time backfill so nobody re-rates. Returns the row count."""
    conn = _conn()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    n = 0
    with _LOCK:
        for row in (grid or []):
            if not isinstance(row, dict):
                continue
            rater = str(row.get("rater") or "").strip()
            player = str(row.get("player") or "").strip()
            rating = str(row.get("rating") or "").strip().upper()
            if not rater or not player or rating not in _TIER_TO_NUM:
                continue
            conn.execute(
                "INSERT OR REPLACE INTO tier_votes "
                "(rater_name, player_name, rating, updated_at) "
                "VALUES (?,?,?,?)",
                (rater, player, rating, now))
            n += 1
        conn.commit()
    return n


def get_tier_votes(rater: Optional[str] = None,
                   player: Optional[str] = None,
                   ) -> List[Dict[str, Any]]:
    """List every (rater, player, rating) tuple, optionally filtered."""
    conn = _conn()
    where, args = [], []
    if rater:
        where.append("rater_name = ?")
        args.append(rater.strip())
    if player:
        where.append("player_name = ?")
        args.append(player.strip())
    sql = ("SELECT rater_name, player_name, rating, updated_at FROM tier_votes"
           + (" WHERE " + " AND ".join(where) if where else "")
           + " ORDER BY player_name ASC, rater_name ASC")
    rows = conn.execute(sql, args).fetchall()
    return [{"rater":  r["rater_name"],
             "player": r["player_name"],
             "rating": r["rating"],
             "updated_at": r["updated_at"]} for r in rows]


def tier_aggregate(eligible: Optional[Iterable[str]] = None,
                   min_votes: int = 1) -> Dict[str, Dict[str, Any]]:
    """Per-player aggregate: {player: {avg, avg_tier, votes, min, max,
                                       std, voters}}.

    `avg` is on the 1..6 numeric scale (S=6 .. F=1) — that's the `avg_tier`
    the old Final Rankings sheet formula consumed. `avg_tier` returned here
    is the rounded letter, for display. `voters` is the raters who rated
    this player. `std` (population) gives a controversy proxy.
    """
    conn = _conn()
    rows = conn.execute(
        "SELECT player_name, rater_name, rating FROM tier_votes "
        "ORDER BY player_name ASC"
    ).fetchall()
    elig_set = None
    if eligible is not None:
        elig_set = {s.strip() for s in eligible if s}
    by_player: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        pname = r["player_name"]
        if elig_set is not None and pname not in elig_set:
            continue
        by_player.setdefault(pname, []).append({
            "rater": r["rater_name"],
            "rating": r["rating"],
            "num":    _TIER_TO_NUM.get(r["rating"], 0),
        })
    out: Dict[str, Dict[str, Any]] = {}
    for pname, ballots in by_player.items():
        if len(ballots) < int(min_votes):
            continue
        nums = [b["num"] for b in ballots if b["num"] > 0]
        if not nums:
            continue
        n = len(nums)
        avg = sum(nums) / n
        mean = avg
        variance = sum((x - mean) ** 2 for x in nums) / n
        std = variance ** 0.5
        out[pname] = {
            "avg":      round(avg, 3),
            "avg_tier": _NUM_TO_TIER.get(round(avg), "?"),
            "votes":    n,
            "min":      _NUM_TO_TIER.get(min(nums), "?"),
            "max":      _NUM_TO_TIER.get(max(nums), "?"),
            "std":      round(std, 3),
            "voters":   [b["rater"] for b in ballots],
        }
    return out


def delete_tier_votes(rater: Optional[str] = None,
                      player: Optional[str] = None) -> int:
    """Remove votes by rater or player (or both). Returns rows deleted."""
    conn = _conn()
    where, args = [], []
    if rater:
        where.append("rater_name = ?")
        args.append(rater.strip())
    if player:
        where.append("player_name = ?")
        args.append(player.strip())
    if not where:
        raise ValueError("delete_tier_votes needs rater or player")
    with _LOCK:
        cur = conn.execute(
            "DELETE FROM tier_votes WHERE " + " AND ".join(where), args)
        conn.commit()
        return cur.rowcount or 0


# ---------------------------------------------------------------------------
# D1 — rankings recompute  (community votes + Riot rank → final_score)
# ---------------------------------------------------------------------------
#
# Formula reverse-engineered from the current "Final Rankings" sheet:
#   tier_score  = avg_tier × 10     (community vote avg 1..6 → 10..60)
#   rank_score  = riot_score × 4    (Riot rank 2.5..10 → 10..40)
#   final_score = tier_score + rank_score          (0..100 blend)
#   rating      = S / A / B / C / D / F            (final_score thresholds)
#
# This keeps the rankings page numerically identical to what the sheet was
# producing, just without the sheet round-trip. Called whenever a ballot is
# submitted (tier_score changes) or the Riot fetcher pushes new rank data.

# Tier base scores — matches fetch_ranks.constants.RANK_SCORES exactly so the
# Riot fetcher's `compute_score` and this server-side recompute agree.
_RIOT_RANK_BASE: Dict[str, float] = {
    "Challenger": 10.0, "Grandmaster": 9.5, "Master": 9.0,
    "Diamond": 8.0, "Emerald": 6.25, "Platinum": 5.5,
    "Gold": 4.75, "Silver": 4.0, "Bronze": 3.25, "Iron": 2.5,
    "Unranked": 4.75,  # treated as Gold I for scoring fairness
}
_DIV_OFFSET: Dict[str, float] = {"I": 0.0, "II": -0.25, "III": -0.5, "IV": -0.75}
_NO_DIV_TIERS = {"Challenger", "Grandmaster", "Master", "Unranked"}


def _riot_score(tier: str, division: str) -> float:
    base = _RIOT_RANK_BASE.get(tier or "Unranked", 1.0)
    if (tier or "") in _NO_DIV_TIERS:
        return round(base, 2)
    return round(base + _DIV_OFFSET.get(division or "", 0.0), 2)


def _rating_letter(final_score: float) -> str:
    s = float(final_score or 0.0)
    if s >= 85: return "S"
    if s >= 70: return "A"
    if s >= 55: return "B"
    if s >= 40: return "C"
    if s >= 25: return "D"
    return "F"


# ---------------------------------------------------------------------------
# D3 (sheet decommission) — activity feed events
# ---------------------------------------------------------------------------

def insert_activity_event(event_type: str,
                          actor: Optional[str] = None,
                          details: Optional[str] = None,
                          related: Optional[str] = None,
                          occurred_at: Optional[str] = None) -> int:
    """Append a single activity event. Returns the new row id."""
    et = (event_type or "").strip().upper()
    if not et:
        raise ValueError("event_type required")
    ts = occurred_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn = _conn()
    with _LOCK:
        cur = conn.execute(
            "INSERT INTO activity_events "
            "(occurred_at, event_type, actor, details, related) "
            "VALUES (?,?,?,?,?)",
            (ts, et, actor or None, details or None, related or None))
        conn.commit()
        return int(cur.lastrowid or 0)


def insert_activity_events(rows: Iterable[Dict[str, Any]]) -> int:
    """Bulk-insert events — backfill path. Each row: {event_type, actor,
    details, related, occurred_at}. Skips rows missing event_type."""
    conn = _conn()
    n = 0
    with _LOCK:
        for r in (rows or []):
            if not isinstance(r, dict):
                continue
            et = str(r.get("event_type") or "").strip().upper()
            if not et:
                continue
            ts = (r.get("occurred_at")
                  or r.get("timestamp")
                  or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            conn.execute(
                "INSERT INTO activity_events "
                "(occurred_at, event_type, actor, details, related) "
                "VALUES (?,?,?,?,?)",
                (ts, et,
                 (r.get("actor") or r.get("player") or None),
                 (r.get("details") or None),
                 (r.get("related") or r.get("related_player") or None)))
            n += 1
        conn.commit()
    return n


def upsert_scout_sheet(display_name: str,
                       payload: Dict[str, Any]) -> bool:
    """Replace the cached scout-sheet payload for one player. `payload` is
    the parsed dict the client's `_parse_scouting_sheet` used to return:
    {player, subtitle, power_rating, overview_headers, overview_values,
     must_bans, ban_impact, champ_pool, roles, form_state, matches, ...}.
    Stored as JSON so we don't have to schema every nested field."""
    name = (display_name or "").strip()
    if not name:
        raise ValueError("display_name required")
    conn = _conn()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _LOCK:
        conn.execute(
            "INSERT OR REPLACE INTO scout_sheets "
            "(display_name, payload, updated_at) VALUES (?,?,?)",
            (name, json.dumps(payload or {}), now))
        conn.commit()
    return True


def upsert_scout_sheets_bulk(rows: Iterable[Dict[str, Any]]) -> int:
    """Bulk replace many scout-sheet payloads. Each row: {name, payload}."""
    conn = _conn()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    n = 0
    with _LOCK:
        for r in (rows or []):
            if not isinstance(r, dict):
                continue
            name = (r.get("display_name") or r.get("name") or "").strip()
            if not name:
                continue
            payload = r.get("payload") or {}
            conn.execute(
                "INSERT OR REPLACE INTO scout_sheets "
                "(display_name, payload, updated_at) VALUES (?,?,?)",
                (name, json.dumps(payload), now))
            n += 1
        conn.commit()
    return n


def get_scout_sheet(display_name: str) -> Optional[Dict[str, Any]]:
    """Return the cached scout-sheet payload for one player, or None."""
    name = (display_name or "").strip()
    if not name:
        return None
    conn = _conn()
    r = conn.execute(
        "SELECT payload, updated_at FROM scout_sheets WHERE display_name = ?",
        (name,)).fetchone()
    if r is None or not r["payload"]:
        return None
    try:
        out = json.loads(r["payload"])
    except (json.JSONDecodeError, TypeError):
        return None
    out["updated_at"] = r["updated_at"]
    return out


def get_scout_sheets_batch(names: Iterable[str]
                           ) -> Dict[str, Optional[Dict[str, Any]]]:
    """Return many scout-sheet payloads in one round-trip. Missing names
    map to None so callers can detect 'no scout sheet yet for this player'."""
    elig = _norm_eligible(names)
    out: Dict[str, Optional[Dict[str, Any]]] = {}
    if not elig:
        return out
    conn = _conn()
    ph = ",".join("?" * len(elig))
    rows = conn.execute(
        f"SELECT display_name, payload, updated_at FROM scout_sheets "
        f"WHERE display_name IN ({ph})",
        elig).fetchall()
    found: Dict[str, Optional[Dict[str, Any]]] = {}
    for r in rows:
        try:
            d = json.loads(r["payload"]) if r["payload"] else None
        except (json.JSONDecodeError, TypeError):
            d = None
        if isinstance(d, dict):
            d["updated_at"] = r["updated_at"]
        found[r["display_name"]] = d
    for name in elig:
        out[name] = found.get(name)
    return out


def list_activity(limit: int = 200,
                  event_type: Optional[str] = None,
                  actor: Optional[str] = None) -> List[Dict[str, Any]]:
    """Newest-first list of events for the activity feed UI. Returns the
    shape `reader.py::_read_activity` used to produce so the feed.py
    consumer keeps working unchanged: keys `timestamp`, `event_type`,
    `player`, `details`, `related_player`."""
    conn = _conn()
    where, args = [], []
    if event_type:
        where.append("event_type = ?")
        args.append(event_type.strip().upper())
    if actor:
        where.append("actor = ?")
        args.append(actor.strip())
    sql = ("SELECT occurred_at, event_type, actor, details, related "
           "FROM activity_events "
           + (" WHERE " + " AND ".join(where) if where else "")
           + " ORDER BY occurred_at DESC, id DESC LIMIT ?")
    args.append(int(limit))
    rows = conn.execute(sql, args).fetchall()
    return [{
        "timestamp":      r["occurred_at"],
        "event_type":     r["event_type"],
        "player":         r["actor"] or "",
        "details":        r["details"] or "",
        "related_player": r["related"] or "",
    } for r in rows]


def recompute_rankings_blend() -> int:
    """Re-apply the tier_score + rank_score blend to every row in the
    rankings table, using the current tier_votes aggregate. Returns the
    number of rows updated.

    Triggered automatically on tier-vote submit + on Riot fetcher push, and
    exposed at POST /api/rankings/recompute for manual reruns."""
    conn = _conn()
    # Pull current ranks
    rank_rows = conn.execute(
        "SELECT display_name, tier, division FROM rankings"
    ).fetchall()
    if not rank_rows:
        return 0
    # Pull current per-player vote avg (1..6 scale)
    agg = tier_aggregate(min_votes=1)
    avg_by: Dict[str, float] = {name: float(d.get("avg") or 0.0)
                                for name, d in agg.items()}
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Compute new values
    new_rows: List[Tuple[Any, ...]] = []
    for r in rank_rows:
        name = r["display_name"]
        tier = r["tier"] or "Unranked"
        div  = r["division"] or ""
        riot = _riot_score(tier, div)
        rank_score = round(riot * 4.0, 2)
        avg = avg_by.get(name, 0.0)
        if avg > 0:
            tier_score = round(avg * 10.0, 2)
        else:
            tier_score = 0.0
        final = round(tier_score + rank_score, 2)
        rating = _rating_letter(final)
        new_rows.append((
            f"{avg:.2f}" if avg > 0 else "",
            f"{tier_score:.2f}" if tier_score else "",
            f"{rank_score:.2f}",
            f"{final:.2f}",
            rating, now, name,
        ))

    # Apply
    n = 0
    with _LOCK:
        for tup in new_rows:
            cur = conn.execute(
                "UPDATE rankings SET avg_tier=?, tier_score=?, rank_score=?, "
                "       final_score=?, rating=?, updated_at=? "
                "WHERE display_name=?", tup)
            n += cur.rowcount or 0
        # Re-sort rank_position by final_score desc so the leaderboard is right.
        # Pull names ordered by final_score (text -> float for sort).
        ordered = conn.execute(
            "SELECT display_name, final_score FROM rankings"
        ).fetchall()
        scored = []
        for r in ordered:
            try:
                s = float(r["final_score"]) if r["final_score"] else 0.0
            except (ValueError, TypeError):
                s = 0.0
            scored.append((r["display_name"], s))
        scored.sort(key=lambda x: -x[1])
        for pos, (name, _s) in enumerate(scored, 1):
            conn.execute(
                "UPDATE rankings SET rank_position=? WHERE display_name=?",
                (pos, name))
        conn.commit()
    return n


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
