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

from .constants import *
from .sheets import get_or_create_sheet, fmt_title, fmt_header, sheets_retry
from .scoring import compute_score, rank_to_chart_value
from .inhouse import load_inhouse_db


# ── Draft tool logic ───────────────────────────────────────

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

