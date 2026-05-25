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

from .constants import RANK_SCORES, DIV_OFFSETS, RANK_CHART_VALUES


# ── Rank scoring helpers ───────────────────────────────────

def compute_score(tier, division):
    base = RANK_SCORES.get(tier, 1)
    offset = DIV_OFFSETS.get(division, 0) if tier not in [
        "Challenger", "Grandmaster", "Master", "Unranked"] else 0
    return round(base + offset, 2)


def rank_to_chart_value(tier, division):
    if tier in ["Master", "Grandmaster", "Challenger", "Unranked"]:
        return RANK_CHART_VALUES.get(tier, 0)
    key = f"{tier} {division}" if division != "N/A" else tier
    return RANK_CHART_VALUES.get(key, 0)


# ── Data Dragon ───────────────────────────────────────────────
