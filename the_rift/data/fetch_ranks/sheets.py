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

# Phase E (sheet decommission): gspread is optional now. The functions
# below all need it when called — they raise at runtime if it's missing —
# but importing this module no longer requires gspread.
try:
    import gspread  # noqa: F401
    from google.oauth2.service_account import Credentials  # noqa: F401
except Exception:                                              # pragma: no cover
    gspread = None        # type: ignore
    Credentials = None    # type: ignore

from .constants import SCOPES


# ── Sheets helpers ─────────────────────────────────────────

# ── Retry helper ──────────────────────────────────────────────

def sheets_retry(fn, *args, max_attempts=6, **kwargs):
    """Call fn(*args, **kwargs) with exponential backoff on quota/server errors."""
    for attempt in range(max_attempts):
        try:
            return fn(*args, **kwargs)
        except gspread.exceptions.APIError as e:
            status = getattr(e.response, "status_code", None)
            if status in (429, 500, 503) and attempt < max_attempts - 1:
                time.sleep((2 ** attempt) + random.uniform(0, 1))
            else:
                raise


# ── Google Sheets helpers ─────────────────────────────────────

def connect_to_sheet(creds_file, sheet_identifier):
    credentials = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
    gc = gspread.authorize(credentials)
    if "docs.google.com" in sheet_identifier:
        return gc.open_by_url(sheet_identifier)
    elif re.match(r'^[a-zA-Z0-9_-]{30,}$', sheet_identifier):
        return gc.open_by_key(sheet_identifier)
    else:
        return gc.open(sheet_identifier)


def get_or_create_sheet(spreadsheet, name, rows=100, cols=30):
    try:
        return spreadsheet.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        return sheets_retry(spreadsheet.add_worksheet, name, rows=rows, cols=cols)


def fmt_title(ws, end_col):
    sheets_retry(ws.format, f"A1:{end_col}1", {
        "backgroundColor": {"red": 0.11, "green": 0.11, "blue": 0.18},
        "textFormat": {"bold": True, "fontSize": 14,
                       "foregroundColor": {"red": 0.91, "green": 0.72, "blue": 0.29}},
        "horizontalAlignment": "CENTER",
    })


def fmt_header(ws, row, end_col):
    sheets_retry(ws.format, f"A{row}:{end_col}{row}", {
        "backgroundColor": {"red": 0.09, "green": 0.14, "blue": 0.28},
        "textFormat": {"bold": True,
                       "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
        "horizontalAlignment": "CENTER",
    })


# ── Riot API helpers ──────────────────────────────────────────
