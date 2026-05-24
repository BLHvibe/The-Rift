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


# ── Riot API client ────────────────────────────────────────

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


