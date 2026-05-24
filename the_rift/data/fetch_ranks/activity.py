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

from .sheets import get_or_create_sheet, sheets_retry


# ── Activity log ───────────────────────────────────────────

def append_activity_event(spreadsheet, event_type, player_name, details):
    """Append one event row to the _Activity log sheet."""
    sheet_name = "_Activity"
    try:
        ws = get_or_create_sheet(spreadsheet, sheet_name, rows=200, cols=4)
        # Write header row if the sheet is brand new
        if not ws.get_all_values():
            sheets_retry(ws.append_row, ["_ACTIVITY LOG", "", "", ""],
                         value_input_option="RAW")
        sheets_retry(ws.append_row,
                     [datetime.now().strftime("%Y-%m-%d %H:%M"), event_type,
                      player_name or "", details],
                     value_input_option="RAW")
    except Exception as e:
        print(f"  (Activity log write skipped: {e})")


def load_activity_log(spreadsheet, limit=50):
    """Return the most recent `limit` activity events as a list of dicts."""
    try:
        ws = spreadsheet.worksheet("_Activity")
    except Exception as e:
        print(f"Warning: could not load activity log: {e}")
        return []
    rows = ws.get_all_values()
    # Skip header row; rows are oldest-first
    data_rows = [r for r in rows if len(r) >= 4 and r[0] != "_ACTIVITY LOG" and r[0]]
    recent = data_rows[-limit:]
    recent.reverse()  # newest first
    return [
        {"ts": r[0], "type": r[1], "player": r[2], "details": r[3]}
        for r in recent
    ]


