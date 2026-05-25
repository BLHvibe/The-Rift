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
# Phase E (sheet decommission): gspread imports are optional now.
try:
    import gspread  # noqa: F401
    from google.oauth2.service_account import Credentials  # noqa: F401
except Exception:
    gspread = None        # type: ignore
    Credentials = None    # type: ignore

from .constants import *
from .sheets import fmt_title, fmt_header, get_or_create_sheet, sheets_retry


# ── Tier list analytics + writers ──────────────────────────

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

