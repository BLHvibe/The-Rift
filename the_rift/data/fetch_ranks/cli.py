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

import os

from .constants import *
from .sheets import connect_to_sheet, get_or_create_sheet, sheets_retry
from .scoring import compute_score, rank_to_chart_value
from .riot import (riot_get, load_champion_map, fetch_account, fetch_ranked,
                   fetch_top_champions, fetch_recent_matches,
                   fetch_scouting_matches, fetch_custom_matches,
                   fetch_and_filter_inhouse)
from .tier_analytics import (compute_tier_analytics, write_consensus,
                              write_hot_takes, write_rater_bias)
from .rankings import (write_rank_data, write_player_stats, write_rank_history,
                        get_final_rankings)
from .scouting import (analyze_player, write_scouting_sheet,
                        write_scouting_database, load_scouting_database)
from .inhouse import (load_inhouse_db, analyze_inhouse,
                       write_inhouse_overview, write_inhouse_h2h)
from .activity import append_activity_event, load_activity_log
from .draft import (score_champ_for_archetype, score_team_synergy,
                     compute_ban_recommendations, compute_comp_suggestions,
                     write_draft_tool, run_draft)


# ── Main entrypoint ────────────────────────────────────────

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
