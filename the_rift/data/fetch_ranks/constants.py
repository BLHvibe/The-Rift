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

# ── Module-level constants (extracted from fetch_ranks_gsheets) ──

DEFAULT_CREDS_FILE = "credentials.json"
DEFAULT_REGION = "na1"
DEFAULT_ROUTING = "americas"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

RANK_SCORES = {
    "Challenger": 10, "Grandmaster": 9.5, "Master": 9,
    "Diamond": 8, "Emerald": 6.25, "Platinum": 5.5,
    "Gold": 4.75, "Silver": 4, "Bronze": 3.25, "Iron": 2.5,
    # Unranked players are treated as Gold I (4.75) for scoring purposes
    # so they aren't unfairly penalized for not having placement games yet.
    "Unranked": 4.75,
}
DIV_OFFSETS = {"I": 0, "II": -0.25, "III": -0.5, "IV": -0.75}

RANK_CHART_VALUES = {
    "Iron IV": 1, "Iron III": 2, "Iron II": 3, "Iron I": 4,
    "Bronze IV": 5, "Bronze III": 6, "Bronze II": 7, "Bronze I": 8,
    "Silver IV": 9, "Silver III": 10, "Silver II": 11, "Silver I": 12,
    "Gold IV": 13, "Gold III": 14, "Gold II": 15, "Gold I": 16,
    "Platinum IV": 17, "Platinum III": 18, "Platinum II": 19, "Platinum I": 20,
    "Emerald IV": 21, "Emerald III": 22, "Emerald II": 23, "Emerald I": 24,
    "Diamond IV": 25, "Diamond III": 26, "Diamond II": 27, "Diamond I": 28,
    "Master": 29, "Grandmaster": 30, "Challenger": 31, "Unranked": 0,
}

TIER_TO_NUM = {"S": 6, "A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
NUM_TO_TIER = {6: "S", 5: "A", 4: "B", 3: "C", 2: "D", 1: "F"}



# ── Champion archetype database ───────────────────────────────

COMP_ARCHETYPES = {
    "Teamfight": {
        "description": "Group and win 5v5s with AoE and engage",
        "needs": {"engage": 1, "aoe_damage": 2, "frontline": 1},
        "ideal_tags": {"Tank", "Mage"},
    },
    "Pick": {
        "description": "Catch enemies with CC and burst them 1-by-1",
        "needs": {"assassin_or_burst": 2, "cc": 2},
        "ideal_tags": {"Assassin", "Mage"},
    },
    "Split Push": {
        "description": "1-3-1 or 1-4 with strong duelists in side lanes",
        "needs": {"duelist": 1, "waveclear": 1},
        "ideal_tags": {"Fighter"},
    },
    "Poke / Siege": {
        "description": "Chunk enemies before fights with long-range abilities",
        "needs": {"long_range": 2, "disengage": 1},
        "ideal_tags": {"Mage", "Marksman"},
    },
    "Protect the Carry": {
        "description": "Peel and buff your strongest damage dealer",
        "needs": {"hypercarry": 1, "peel": 2},
        "ideal_tags": {"Support", "Marksman"},
    },
    "Dive": {
        "description": "Hard engage onto backline, collapse and delete carries",
        "needs": {"engage": 2, "assassin_or_burst": 1, "frontline": 1},
        "ideal_tags": {"Tank", "Assassin", "Fighter"},
    },
    "Scaling": {
        "description": "Play safe early, outscale with late-game champions",
        "needs": {"hypercarry": 1, "waveclear": 1, "disengage": 1},
        "ideal_tags": {"Mage", "Marksman"},
    },
}

ARCHETYPE_CONFLICTS = {
    "Dive": ["hypercarry", "disengage"],        # hypercarry/peel in dive = bad
    "Teamfight": ["disengage", "duelist"],       # selfish fighters in TF = bad
    "Poke / Siege": ["engage", "assassin_or_burst"],  # dive in poke = contradictory
    "Protect the Carry": ["assassin_or_burst"],  # assassins in protect = bad
    "Split Push": ["engage", "aoe_damage"],      # AoE teamfight in split = bad
}

CHAMP_SUBCLASSES = {
    "engage": {"Malphite","Amumu","Leona","Nautilus","Rakan","Rell","Alistar",
               "Jarvan IV","Sejuani","Maokai","Ornn","Zac","Sion","Gragas",
               "Wukong","Diana","Galio","Skarner","Yone","Kennen","Hecarim",
               "Vi","Camille","Kled","Nocturne","Rek'Sai","Pantheon",
               "Ambessa","Aurora"},
    "aoe_damage": {"Orianna","Miss Fortune","Kennen","Rumble","Diana","Yone",
                   "Yasuo","Gangplank","Samira","Karthus","Brand","Zyra",
                   "Viktor","Cassiopeia","Nilah","Fiddlesticks","Aurora","Katarina",
                   "Vladimir","Lissandra","Wukong","Galio","Lillia","Briar",
                   "Vex","Hwei","Ziggs","Seraphine","Twitch","Jinx"},
    "frontline": {"Malphite","Maokai","Ornn","Sion","Cho'Gath","Dr. Mundo",
                  "Tahm Kench","Shen","Braum","Taric","Alistar","Leona",
                  "Nautilus","Rell","Sejuani","Amumu","Rammus","Zac",
                  "Poppy","Skarner","K'Sante","Gragas","Volibear","Darius",
                  "Garen","Sett","Mordekaiser","Illaoi","Urgot","Aatrox","Ambessa"},
    "assassin_or_burst": {"Zed","Talon","Qiyana","Akali","LeBlanc","Fizz",
                          "Katarina","Ekko","Kha'Zix","Rengar","Evelynn",
                          "Shaco","Naafiri","Pyke","Syndra","Ahri","Veigar",
                          "Annie","Lux","Neeko","Zoe","Vex","Aurora",
                          "Nocturne","Diana","Briar","Lee Sin",
                          "Ambessa","Mel"},
    "cc": {"Thresh","Morgana","Lux","Ahri","Ashe","Jhin","Veigar","Neeko",
           "Twisted Fate","Blitzcrank","Pyke","Elise","Lee Sin","Hwei",
           "Sejuani","Amumu","Leona","Nautilus","Maokai","Zyra","Bard",
           "Renata Glasc","Rakan","Rell","Skarner"},
    "duelist": {"Fiora","Tryndamere","Jax","Camille","Gwen","Irelia","Riven",
                "Yasuo","Yone","Mordekaiser","Nasus","Yorick","Trundle",
                "Volibear","Udyr","Kayle","Sett","Gnar","Ambessa","Warwick",
                "Shen","Illaoi","Olaf","Renekton","Kled"},
    "waveclear": {"Anivia","Ryze","Malzahar","Viktor","Ziggs","Sivir",
                  "Jinx","Orianna","Xerath","Taliyah","Aurelion Sol","Hwei",
                  "Twisted Fate","Corki","Heimerdinger","Seraphine","Veigar",
                  "Cassiopeia","Vladimir","Azir","Mel","Smolder"},
    "long_range": {"Xerath","Vel'Koz","Lux","Ziggs","Jayce","Ezreal","Varus",
                   "Kog'Maw","Nidalee","Zoe","Hwei","Caitlyn","Senna",
                   "Seraphine","Karma","Viktor","Corki","Jhin","Ashe"},
    "disengage": {"Janna","Gragas","Poppy","Alistar","Thresh","Braum",
                  "Karma","Lulu","Zilean","Anivia","Taliyah","Azir",
                  "Nami","Milio","Soraka"},
    "hypercarry": {"Kog'Maw","Jinx","Twitch","Aphelios","Vayne","Kayle",
                   "Kindred","Smolder","Veigar","Cassiopeia","Karthus",
                   "Azir","Viktor","Tristana","Xayah","Zeri","Kai'Sa",
                   "Draven","Nilah","Master Yi"},
    "peel": {"Lulu","Janna","Karma","Nami","Soraka","Yuumi","Milio",
             "Renata Glasc","Taric","Zilean","Ivern","Braum","Shen",
             "Orianna","Seraphine","Sona","Bard"},
}


ROLE_VALID = {
    "Top": {"Aatrox","Ambessa","Aurora","Camille","Cho'Gath","Darius","Dr. Mundo",
            "Fiora","Gangplank","Garen","Gnar","Gwen","Illaoi","Irelia","Jax",
            "Jayce","K'Sante","Kayle","Kennen","Kled","Malphite","Maokai",
            "Mordekaiser","Nasus","Olaf","Ornn","Pantheon","Poppy","Quinn",
            "Renekton","Rengar","Riven","Rumble","Sett","Shen","Singed",
            "Sion","Tahm Kench","Teemo","Trundle","Tryndamere","Urgot",
            "Vladimir","Volibear","Wukong","Yasuo","Yone","Yorick","Gragas",
            "Heimerdinger","Akali","Sylas","Warwick","Zac"},
    "Jungle": {"Amumu","Ambessa","Bel'Veth","Briar","Diana","Ekko","Elise","Evelynn",
               "Fiddlesticks","Gragas","Graves","Hecarim","Ivern","Jarvan IV",
               "Karthus","Kayn","Kha'Zix","Kindred","Lee Sin","Lillia",
               "Master Yi","Nidalee","Nocturne","Nunu","Pantheon","Poppy",
               "Rammus","Rek'Sai","Rengar","Sejuani","Shaco","Shyvana",
               "Skarner","Taliyah","Udyr","Vi","Viego","Volibear","Warwick",
               "Wukong","Xin Zhao","Zac","Maokai","Trundle","Sylas"},
    "Mid": {"Ahri","Akali","Akshan","Anivia","Annie","Aurelion Sol","Azir",
            "Cassiopeia","Corki","Diana","Ekko","Fizz","Galio","Hwei",
            "Irelia","Kassadin","Katarina","LeBlanc","Lissandra","Lux",
            "Malzahar","Mel","Naafiri","Neeko","Orianna","Pantheon","Qiyana",
            "Ryze","Sylas","Syndra","Taliyah","Talon","Tristana","Twisted Fate",
            "Veigar","Vex","Viktor","Vladimir","Xerath","Yasuo","Yone",
            "Zed","Zoe","Ziggs","Aurora","Jayce","Rumble","Heimerdinger","Zyra"},
    "Bot": {"Aphelios","Ashe","Caitlyn","Corki","Draven","Ezreal","Jhin",
            "Jinx","Kai'Sa","Kalista","Kog'Maw","Lucian","Miss Fortune",
            "Nilah","Samira","Sivir","Smolder","Tristana","Twitch","Varus",
            "Vayne","Xayah","Zeri","Ziggs","Senna"},
    "Support": {"Alistar","Bard","Blitzcrank","Braum","Janna","Karma","Leona",
                "Lulu","Lux","Mel","Milio","Morgana","Nami","Nautilus","Pyke",
                "Rakan","Rell","Renata Glasc","Senna","Seraphine","Sona",
                "Soraka","Taric","Thresh","Yuumi","Zilean","Zyra","Xerath",
                "Vel'Koz","Maokai","Poppy","Tahm Kench","Galio"},
}

