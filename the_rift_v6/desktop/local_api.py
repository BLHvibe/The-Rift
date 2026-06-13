"""Local sidecar endpoints for The Rift v6 — the things a browser can't do.

Mounted by launcher.py under /local:

    GET  /local/lcu/summoner    LCU lockfile → current summoner gameName
    POST /local/log-game        scrape LCU custom-game history → /api/matches
    POST /local/fetch-ranks     Riot rank refresh (v5 rankings_refresh_api)
    POST /local/run-scout       same, with the full per-player scout pass
    GET  /local/jobs/{job_id}   poll a running job: progress, log, result

fetch-ranks / run-scout import the v5 `data` package (UI-free) from
the_rift/. In dev the repo layout provides it; the frozen exe bundles it via
PyInstaller --paths/--hidden-import (see build.ps1).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
import urllib3
from fastapi import APIRouter

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

router = APIRouter(prefix="/local")

FLY = "https://the-rift-draft-sync.fly.dev"

# Make the v5 data package importable in dev (frozen builds bundle it).
_V5_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "the_rift"))
if os.path.isdir(_V5_DIR) and _V5_DIR not in sys.path:
    sys.path.insert(0, _V5_DIR)


# ── LCU plumbing ────────────────────────────────────────────────────────────

def _find_lockfile() -> Optional[str]:
    candidates: List[str] = []
    local_app = os.environ.get("LOCALAPPDATA", "")
    if local_app:
        candidates.append(os.path.join(
            local_app, "Riot Games", "League of Legends", "lockfile"))
    for drive in ("C:\\", "D:\\", "E:\\"):
        for sub in ("Riot Games", "Program Files\\Riot Games",
                    "Program Files (x86)\\Riot Games"):
            candidates.append(os.path.join(
                drive, sub, "League of Legends", "lockfile"))
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


def _lcu_conn():
    """(base_url, auth) for the running League client, or (None, error)."""
    lockfile = _find_lockfile()
    if not lockfile:
        return None, "League client not running (lockfile not found)"
    try:
        with open(lockfile, "r") as f:
            parts = f.read().strip().split(":")
        if len(parts) < 5:
            return None, "Unexpected lockfile format"
        port, password, protocol = parts[2], parts[3], parts[4]
        return (f"{protocol}://127.0.0.1:{port}", ("riot", password)), ""
    except Exception as e:
        return None, f"Could not read lockfile: {e}"


@router.get("/lcu/summoner")
def lcu_summoner() -> Dict[str, Any]:
    conn, err = _lcu_conn()
    if not conn:
        return {"ok": False, "error": err}
    base, auth = conn
    try:
        r = requests.get(f"{base}/lol-summoner/v1/current-summoner",
                         auth=auth, verify=False, timeout=5)
        if r.status_code != 200:
            return {"ok": False, "error": f"LCU returned {r.status_code}"}
        j = r.json()
        name = j.get("gameName") or j.get("displayName") or ""
        if not name:
            return {"ok": False, "error": "No name in LCU response"}
        return {"ok": True, "gameName": name}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


# ── Job registry (fetch-ranks / scout / log-game run in threads) ───────────

_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _new_job(label: str) -> str:
    job_id = uuid.uuid4().hex[:10]
    with _jobs_lock:
        # keep the registry tidy
        for k in [k for k, v in _jobs.items() if v.get("done")][:-8]:
            _jobs.pop(k, None)
        _jobs[job_id] = {"label": label, "running": True, "done": False,
                         "ok": None, "progress": 0.0, "log": [],
                         "summary": None, "started": time.time()}
    return job_id


def _job_log(job_id: str, msg: str, pct: Optional[float] = None) -> None:
    with _jobs_lock:
        j = _jobs.get(job_id)
        if not j:
            return
        j["log"] = (j["log"] + [str(msg)[:200]])[-40:]
        if pct is not None:
            j["progress"] = max(j["progress"], min(1.0, float(pct)))


def _job_finish(job_id: str, ok: bool, summary: Any = None) -> None:
    with _jobs_lock:
        j = _jobs.get(job_id)
        if not j:
            return
        j.update(running=False, done=True, ok=ok, summary=summary,
                 progress=1.0 if ok else j["progress"])


@router.get("/jobs/{job_id}")
def job_status(job_id: str) -> Dict[str, Any]:
    with _jobs_lock:
        j = _jobs.get(job_id)
        if not j:
            return {"ok": False, "error": "unknown job"}
        return {"ok": True, **{k: v for k, v in j.items() if k != "started"}}


def _busy() -> Optional[str]:
    with _jobs_lock:
        for jid, j in _jobs.items():
            if j.get("running"):
                return jid
    return None


# ── LOG INHOUSE GAME — port of v5 reader.log_inhouse_games_from_client ─────

def _load_champion_map() -> Dict[int, str]:
    try:
        v = requests.get(
            "https://ddragon.leagueoflegends.com/api/versions.json",
            timeout=8).json()
        data = requests.get(
            f"https://ddragon.leagueoflegends.com/cdn/{v[0]}/data/en_US/champion.json",
            timeout=8).json()
        return {int(d["key"]): d["name"] for d in data["data"].values()}
    except Exception:
        return {}


def _log_games_worker(job_id: str) -> None:
    try:
        _job_log(job_id, "Finding League client…", 0.05)
        conn, err = _lcu_conn()
        if not conn:
            _job_log(job_id, err)
            _job_finish(job_id, False, {"error": err})
            return
        base, auth = conn

        r = requests.get(f"{base}/lol-summoner/v1/current-summoner",
                         auth=auth, verify=False, timeout=5)
        if r.status_code != 200:
            _job_finish(job_id, False,
                        {"error": f"Could not get summoner ({r.status_code})"})
            return
        summoner = r.json()
        logged_by = (summoner.get("gameName")
                     or summoner.get("displayName") or "Unknown")
        _job_log(job_id, f"Connected as {logged_by} — loading champions…", 0.15)
        champ_map = _load_champion_map()

        _job_log(job_id, "Checking existing game log…", 0.25)
        existing_ids: set = set()
        try:
            mr = requests.get(f"{FLY}/api/matches?source=inhouse&limit=2000",
                              timeout=20)
            for m in (mr.json().get("matches") or []):
                mid = m.get("id")
                if mid is None:
                    continue
                try:
                    existing_ids.add(int(mid))
                except (TypeError, ValueError):
                    existing_ids.add(mid)
        except Exception as e:
            _job_log(job_id, f"existing-ids fetch failed: {e}")

        _job_log(job_id,
                 f"{len(existing_ids)} games already logged — fetching history…",
                 0.35)
        cutoff = int((datetime.now() - timedelta(days=180)).timestamp() * 1000)
        url = (f"{base}/lol-match-history/v1/products/lol/current-summoner/"
               f"matches?begIndex=0&endIndex=500")
        try:
            resp = requests.get(url, auth=auth, verify=False, timeout=30)
            games = (resp.json().get("games", {}).get("games", [])
                     if resp.status_code == 200 else [])
        except Exception:
            games = []

        customs = [g for g in games
                   if g.get("gameCreation", 0) >= cutoff
                   and (g.get("queueId") in (0, 3130)
                        or g.get("gameType") == "CUSTOM_GAME")
                   and g.get("gameId") not in existing_ids]
        if not customs:
            _job_log(job_id, "No new custom games found.", 1.0)
            _job_finish(job_id, True, {"new_games": 0})
            return

        _job_log(job_id, f"Processing {len(customs)} new custom games…", 0.45)
        role_map = {"TOP": "TOP", "JUNGLE": "JGL", "MIDDLE": "MID",
                    "BOTTOM": "BOT", "UTILITY": "SUP", "SUPPORT": "SUP",
                    "NONE": "", "UNKNOWN": "", "": ""}
        api_matches: List[Dict[str, Any]] = []
        seen: set = set()
        for gi, g in enumerate(customs):
            gid = g.get("gameId")
            if not gid or gid in seen:
                continue
            seen.add(gid)
            try:
                dr = requests.get(f"{base}/lol-match-history/v1/games/{gid}",
                                  auth=auth, verify=False, timeout=15)
                d = dr.json() if dr.status_code == 200 else {}
            except Exception:
                continue
            participants = d.get("participants", [])
            identities = d.get("participantIdentities", [])
            if len(participants) != 10:
                continue
            duration = max(d.get("gameDuration", 1), 1)
            started_at = datetime.utcfromtimestamp(
                d.get("gameCreation", 0) / 1000).strftime("%Y-%m-%dT%H:%M:%SZ")
            patch = str(d.get("gameVersion") or "")
            team_slot = {100: 0, 200: 0}
            api_parts: List[Dict[str, Any]] = []
            winner = ""
            for idx, p in enumerate(participants):
                pname, riot_id = "Unknown", ""
                if idx < len(identities):
                    pl = identities[idx].get("player", {})
                    pname = (pl.get("gameName") or pl.get("summonerName")
                             or f"Player_{idx}")
                    tag = pl.get("tagLine") or ""
                    riot_id = f"{pname}#{tag}" if tag else pname
                stats = p.get("stats", {})
                cname = champ_map.get(p.get("championId", 0),
                                      f"Champ#{p.get('championId', 0)}")
                lane = str(p.get("timeline", {}).get("lane", "")).upper()
                role = role_map.get(lane, "")
                cs = (stats.get("totalMinionsKilled", 0)
                      + stats.get("neutralMinionsKilled", 0))
                team_id = p.get("teamId", 0)
                team = ("blue" if team_id == 100
                        else ("red" if team_id == 200 else "spec"))
                team_slot[team_id] = team_slot.get(team_id, 0) + 1
                is_win = bool(stats.get("win", False))
                if is_win and not winner:
                    winner = team
                api_parts.append({
                    "player": pname, "riot_id": riot_id, "team": team,
                    "slot": team_slot[team_id], "role": role,
                    "champion": cname, "win": 1 if is_win else 0,
                    "kills": stats.get("kills", 0),
                    "deaths": stats.get("deaths", 0),
                    "assists": stats.get("assists", 0),
                    "cs": cs, "gold": stats.get("goldEarned", 0),
                    "damage": stats.get("totalDamageDealtToChampions", 0),
                    "vision": stats.get("visionScore", 0),
                })
            api_matches.append({
                "id": str(gid), "source": "inhouse", "queue": "CUSTOM",
                "patch": patch, "duration": int(duration),
                "started_at": started_at, "winner": winner,
                "participants": api_parts,
            })
            _job_log(job_id, f"  parsed game {gid}",
                     0.45 + 0.4 * (gi + 1) / len(customs))

        if not api_matches:
            _job_log(job_id, "No complete 10-player customs found.", 1.0)
            _job_finish(job_id, True, {"new_games": 0})
            return

        n = len(api_matches)
        _job_log(job_id, f"Mirroring {n} game{'s' if n != 1 else ''} to data API…", 0.9)
        pr = requests.post(f"{FLY}/api/matches", json={"matches": api_matches},
                           timeout=60)
        if pr.status_code != 200:
            _job_finish(job_id, False,
                        {"error": f"ingest returned {pr.status_code}"})
            return
        try:
            requests.post(f"{FLY}/api/activity", json={
                "event_type": "INHOUSE", "actor": logged_by,
                "details": f"Logged {n} new inhouse game{'s' if n != 1 else ''}",
            }, timeout=15)
        except Exception:
            pass
        _job_log(job_id, f"✓ {n} new game{'s' if n != 1 else ''} logged.", 1.0)
        _job_finish(job_id, True, {"new_games": n})
    except Exception as e:
        _job_log(job_id, f"error: {e}")
        _job_finish(job_id, False, {"error": str(e)[:200]})


@router.post("/log-game")
def log_game() -> Dict[str, Any]:
    busy = _busy()
    if busy:
        return {"ok": False, "error": "a job is already running", "job": busy}
    job_id = _new_job("LOG INHOUSE GAME")
    threading.Thread(target=_log_games_worker, args=(job_id,),
                     daemon=True, name="log-game").start()
    return {"ok": True, "job": job_id}


# ── FETCH RANKS / RUN SCOUT — v5 rankings_refresh_api ───────────────────────

def _refresh_worker(job_id: str, do_scout: bool) -> None:
    try:
        from data.config import load_config
        from data.rankings_refresh_api import refresh_rankings
    except Exception as e:
        _job_finish(job_id, False,
                    {"error": f"v5 data package unavailable: {e}"})
        return
    cfg = load_config()
    api_key = (cfg.get("api_key") or "").strip()
    if not api_key:
        _job_finish(job_id, False,
                    {"error": "No Riot API key in config.json"})
        return

    done_evt = threading.Event()
    result: Dict[str, Any] = {}

    def on_progress(msg, pct):
        _job_log(job_id, msg, pct)

    def on_done(summary):
        result["summary"] = summary
        done_evt.set()

    def on_error(msg):
        result["error"] = msg
        done_evt.set()

    refresh_rankings(api_key,
                     region=cfg.get("region") or "na1",
                     routing=cfg.get("routing") or "americas",
                     do_scout=do_scout,
                     on_progress=on_progress, on_done=on_done,
                     on_error=on_error)
    done_evt.wait(timeout=3600)
    if "error" in result:
        _job_finish(job_id, False, {"error": result["error"]})
    elif result.get("summary", {}).get("ok"):
        _job_finish(job_id, True, result["summary"])
    else:
        _job_finish(job_id, False, result.get("summary")
                    or {"error": "timed out"})


def _start_refresh(label: str, do_scout: bool) -> Dict[str, Any]:
    busy = _busy()
    if busy:
        return {"ok": False, "error": "a job is already running", "job": busy}
    job_id = _new_job(label)
    threading.Thread(target=_refresh_worker, args=(job_id, do_scout),
                     daemon=True, name=label).start()
    return {"ok": True, "job": job_id}


@router.post("/fetch-ranks")
def fetch_ranks() -> Dict[str, Any]:
    return _start_refresh("FETCH RANKS", do_scout=False)


@router.post("/run-scout")
def run_scout() -> Dict[str, Any]:
    return _start_refresh("RUN SCOUT", do_scout=True)


# ── Update check — newest v6 release on GitHub ──────────────────────────────

GH_REPO = "BLHvibe/The-Rift"
_update_cache: Dict[str, Any] = {"ts": 0.0, "data": None}


def _semver(tag: str):
    nums = re.findall(r"\d+", tag or "")
    return tuple(int(n) for n in nums[:3]) + (0,) * (3 - len(nums[:3]))


@router.get("/update-check")
def update_check(current: str = "") -> Dict[str, Any]:
    """Latest v6 release tag on GitHub vs the running build's `current`
    version. /releases/latest stays pinned to v5 for the legacy auto-updater,
    so we scan the full release list for the newest v6* tag instead."""
    now = time.time()
    if _update_cache["data"] and now - _update_cache["ts"] < 1800:
        latest = _update_cache["data"]
    else:
        try:
            r = requests.get(
                f"https://api.github.com/repos/{GH_REPO}/releases?per_page=30",
                headers={"Accept": "application/vnd.github+json"}, timeout=10)
            rels = r.json() if r.status_code == 200 else []
            v6 = [x for x in rels
                  if str(x.get("tag_name", "")).lower().startswith("v6")
                  and not x.get("draft")]
            v6.sort(key=lambda x: _semver(x.get("tag_name", "")), reverse=True)
            latest = ({"tag": v6[0]["tag_name"], "url": v6[0].get("html_url", ""),
                       "name": v6[0].get("name", "")} if v6 else None)
            _update_cache.update(ts=now, data=latest)
        except Exception as e:
            return {"ok": False, "error": str(e)[:120]}
    if not latest:
        return {"ok": True, "update": False}
    update = _semver(latest["tag"]) > _semver(current) if current else False
    return {"ok": True, "update": update, "latest": latest,
            "current": current}
