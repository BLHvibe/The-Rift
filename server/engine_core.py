"""
Draft Engine — shared champion analysis core.

Imported by:
- the_rift.ui.draft                  (local fast pass, shown immediately)
- the_rift.data.fetch_ranks_gsheets  (background richer pass)

Both paths produce results with the same dict shape so the UI swaps them in place.

Pure Python: no DPG, no sheet I/O. All data is hand-curated tables of LoL champion
properties, plus algorithms (Bayesian shrinkage, team identity vector, beam search,
counter/synergy scoring, enemy weakness modelling).
"""

from __future__ import annotations
import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

# ============================================================================
# Role definitions
# ============================================================================

ROLES_UPPER = ("TOP", "JGL", "MID", "BOT", "SUP")
ROLE_NORM = {"TOP": "Top", "JGL": "Jungle", "MID": "Mid", "BOT": "Bot", "SUP": "Support"}


# ============================================================================
# Champion subclasses (binary tags — what the champ can DO)
# ============================================================================

SUBCLASSES: Dict[str, Set[str]] = {
    "engage": {
        "Malphite","Amumu","Leona","Nautilus","Rakan","Rell","Alistar","Jarvan IV",
        "Sejuani","Maokai","Ornn","Zac","Sion","Gragas","Wukong","Diana","Galio",
        "Skarner","Yone","Kennen","Hecarim","Vi","Camille","Kled","Nocturne",
        "Rek'Sai","Pantheon","Ambessa","Aurora",
    },
    "aoe_damage": {
        "Orianna","Miss Fortune","Kennen","Rumble","Diana","Yone","Yasuo","Gangplank",
        "Samira","Karthus","Brand","Zyra","Viktor","Cassiopeia","Nilah","Fiddlesticks",
        "Aurora","Katarina","Vladimir","Lissandra","Wukong","Galio","Lillia","Briar",
        "Vex","Hwei","Ziggs","Seraphine","Twitch","Jinx",
    },
    "frontline": {
        "Malphite","Maokai","Ornn","Sion","Cho'Gath","Dr. Mundo","Tahm Kench","Shen",
        "Braum","Taric","Alistar","Leona","Nautilus","Rell","Sejuani","Amumu","Rammus",
        "Zac","Poppy","Skarner","K'Sante","Gragas","Volibear","Darius","Garen","Sett",
        "Mordekaiser","Illaoi","Urgot","Aatrox","Ambessa",
    },
    "assassin_or_burst": {
        "Zed","Talon","Qiyana","Akali","LeBlanc","Fizz","Katarina","Ekko","Kha'Zix",
        "Rengar","Evelynn","Shaco","Naafiri","Pyke","Syndra","Ahri","Veigar","Annie",
        "Lux","Neeko","Zoe","Vex","Aurora","Nocturne","Diana","Briar","Lee Sin",
        "Ambessa","Mel",
    },
    "cc": {
        "Thresh","Morgana","Lux","Ahri","Ashe","Jhin","Veigar","Neeko","Twisted Fate",
        "Blitzcrank","Pyke","Elise","Lee Sin","Hwei","Sejuani","Amumu","Leona",
        "Nautilus","Maokai","Zyra","Bard","Renata Glasc","Rakan","Rell","Skarner",
        "Annie","Morgana","Lissandra","Anivia","Cassiopeia","Galio",
    },
    "duelist": {
        "Fiora","Tryndamere","Jax","Camille","Gwen","Irelia","Riven","Yasuo","Yone",
        "Mordekaiser","Nasus","Yorick","Trundle","Volibear","Udyr","Kayle","Sett",
        "Gnar","Ambessa","Warwick","Shen","Illaoi","Olaf","Renekton","Kled",
    },
    "waveclear": {
        "Anivia","Ryze","Malzahar","Viktor","Ziggs","Sivir","Jinx","Orianna","Xerath",
        "Taliyah","Aurelion Sol","Hwei","Twisted Fate","Corki","Heimerdinger",
        "Seraphine","Veigar","Cassiopeia","Vladimir","Azir","Mel","Smolder",
    },
    "long_range": {
        "Xerath","Vel'Koz","Lux","Ziggs","Jayce","Ezreal","Varus","Kog'Maw","Nidalee",
        "Zoe","Hwei","Caitlyn","Senna","Seraphine","Karma","Viktor","Corki","Jhin","Ashe",
    },
    "disengage": {
        "Janna","Gragas","Poppy","Alistar","Thresh","Braum","Karma","Lulu","Zilean",
        "Anivia","Taliyah","Azir","Nami","Milio","Soraka",
    },
    "hypercarry": {
        "Kog'Maw","Jinx","Twitch","Aphelios","Vayne","Kayle","Kindred","Smolder",
        "Veigar","Cassiopeia","Karthus","Azir","Viktor","Tristana","Xayah","Zeri",
        "Kai'Sa","Draven","Nilah","Master Yi",
    },
    "peel": {
        "Lulu","Janna","Karma","Nami","Soraka","Yuumi","Milio","Renata Glasc","Taric",
        "Zilean","Ivern","Braum","Shen","Orianna","Seraphine","Sona","Bard",
    },
    # NEW subclasses below — used by enemy-weakness / synergy / damage models
    "mobile": {
        "Yasuo","Yone","Akali","LeBlanc","Fizz","Ekko","Zed","Talon","Qiyana","Camille",
        "Irelia","Fiora","Gnar","Lee Sin","Nidalee","Master Yi","Tristana","Vayne",
        "Kai'Sa","Zeri","Lucian","Samira","Diana","Riven","Sylas","Wukong","Briar",
        "Hecarim","Rakan","Nocturne","Aurora","Ambessa","Mel","Pantheon","Quinn","Volibear",
    },
    "immobile": {
        "Karthus","Annie","Veigar","Kog'Maw","Jinx","Ashe","Caitlyn","Xerath","Vel'Koz",
        "Senna","Brand","Anivia","Heimerdinger","Ziggs","Soraka","Sona","Nami","Janna",
        "Lux","Seraphine","Lulu","Yuumi","Milio","Zilean","Karma","Smolder","Mel","Hwei",
    },
    "squishy": {
        "Vayne","Twitch","Tristana","Jinx","Kog'Maw","Aphelios","Caitlyn","Smolder",
        "Zeri","Xayah","Kai'Sa","Draven","Senna","Lucian","Samira","Nilah",
        "Karthus","Annie","Veigar","Lux","Ahri","Syndra","Orianna","Ziggs","Xerath",
        "Vel'Koz","Hwei","Cassiopeia","Vex","Aurelion Sol","Zoe","Brand","Anivia","Heimerdinger",
        "Soraka","Sona","Nami","Janna","Lulu","Yuumi","Milio","Zilean","Karma","Seraphine",
    },
    "tank_buster": {  # true damage / %hp damage
        "Vayne","Fiora","Kayle","Kog'Maw","Gwen","Nilah","Olaf","Trundle","Smolder",
        "Yi","Master Yi","Yorick","Camille","Aurora","Briar","Belveth","Bel'Veth",
        "Cho'Gath","Vi","Lillia","Nasus","Senna",
    },
    "anti_carry": {  # CC or burst that locks down enemy hypercarry
        "Malzahar","Annie","Galio","Lissandra","Zed","Talon","Kha'Zix","Rengar","Akali",
        "Diana","Pantheon","Nocturne","Naafiri","Fizz","Maokai","Ahri","Veigar","LeBlanc",
        "Syndra","Vex","Camille","Wukong","Briar","Skarner","Ambessa",
    },
    "global_pressure": {
        "Twisted Fate","Pantheon","Shen","Karthus","Tahm Kench","Galio","Nocturne",
        "Aurelion Sol","Gangplank","Ashe","Senna","Quinn","Jhin",
    },
    "scaling": {
        "Kayle","Vladimir","Kassadin","Veigar","Smolder","Nasus","Kog'Maw","Vayne",
        "Aurelion Sol","Cassiopeia","Aphelios","Twitch","Karthus","Azir","Viktor",
        "Master Yi","Yorick","Mel","Anivia","Ryze",
    },
    "early_game": {  # strong laning + early skirmish
        "Renekton","Pantheon","Lee Sin","Elise","Olaf","Nocturne","Lucian","Draven",
        "Zed","Talon","LeBlanc","Vi","Kha'Zix","Rengar","Camille","Riven","Darius",
        "Sett","Kled","Diana","Quinn","Jax","Tryndamere","Graves","Xin Zhao","Ambessa",
        "Briar","Bel'Veth","Naafiri","Pyke","Blitzcrank","Leona","Nautilus",
    },
}


# ============================================================================
# Damage type (AP/AD/true/hybrid) — for damage profile coherence
# ============================================================================

DAMAGE_AP: Set[str] = {
    "Ahri","Akali","Anivia","Annie","Aurelion Sol","Aurora","Azir","Brand","Cassiopeia",
    "Diana","Elise","Evelynn","Fiddlesticks","Fizz","Galio","Heimerdinger","Hwei","Karma",
    "Karthus","Kassadin","Katarina","Kennen","LeBlanc","Lillia","Lissandra","Lulu","Lux",
    "Malzahar","Mel","Morgana","Naafiri","Neeko","Nidalee","Orianna","Rumble","Ryze",
    "Seraphine","Soraka","Swain","Sylas","Syndra","Taliyah","Twisted Fate","Veigar",
    "Vel'Koz","Vex","Viktor","Vladimir","Xerath","Yuumi","Ziggs","Zilean","Zoe","Zyra",
    "Skarner","Maokai","Ivern","Amumu","Cho'Gath","Mordekaiser","Singed","Teemo",
}
DAMAGE_AD: Set[str] = {
    "Aatrox","Aphelios","Ashe","Camille","Caitlyn","Darius","Draven","Ekko","Ezreal",
    "Fiora","Garen","Gnar","Graves","Gwen","Hecarim","Illaoi","Irelia","Jarvan IV","Jax",
    "Jayce","Jhin","Jinx","Kai'Sa","Kalista","Kayle","Kayn","Kha'Zix","Kindred","Kled",
    "Kog'Maw","Lee Sin","Lucian","Master Yi","Miss Fortune","Nasus","Nilah","Noc","Nocturne",
    "Olaf","Pantheon","Pyke","Qiyana","Quinn","Renekton","Rengar","Riven","Samira","Senna",
    "Sett","Shaco","Sivir","Smolder","Talon","Trundle","Tristana","Tryndamere","Twitch",
    "Udyr","Urgot","Varus","Vayne","Vi","Viego","Volibear","Warwick","Wukong","Xayah",
    "Xin Zhao","Yasuo","Yone","Yorick","Zed","Zeri","Briar","Bel'Veth","Ambessa","Mel",
    "Gangplank","Akshan",
}
DAMAGE_HYBRID: Set[str] = {  # significant both — counts half toward each side
    "Akali","Diana","Ekko","Jax","Kayle","Kayn","Kennen","Lillia","Mordekaiser","Pyke",
    "Sett","Sylas","Yone","Mel",
}
DAMAGE_TRUE: Set[str] = {
    "Vayne","Fiora","Kayle","Camille","Gwen","Olaf","Trundle","Master Yi","Senna",
    "Aphelios","Nilah","Yi","Kog'Maw","Briar","Ambessa",
}


def champ_damage_split(champ: str) -> Tuple[float, float]:
    """Return (ap_weight, ad_weight) summing to ~1.0. Hybrid splits 50/50."""
    if champ in DAMAGE_HYBRID:
        return (0.5, 0.5)
    if champ in DAMAGE_AP:
        return (1.0, 0.0)
    if champ in DAMAGE_AD:
        return (0.0, 1.0)
    return (0.5, 0.5)  # unknown → neutral


# ============================================================================
# Synergies & anti-synergies (champion pairs)
# ============================================================================

def _pair(a: str, b: str) -> Tuple[str, str]:
    return (a, b) if a < b else (b, a)


def _build_pairs(entries: Iterable[Tuple[str, str, float]]) -> Dict[Tuple[str, str], float]:
    out: Dict[Tuple[str, str], float] = {}
    for a, b, v in entries:
        out[_pair(a, b)] = v
    return out


# Synergy bonus (added to team score). 0.10 = noticeable, 0.30 = strong combo.
SYNERGIES: Dict[Tuple[str, str], float] = _build_pairs([
    # Knockup chain enablers (anyone + Yasuo/Yone)
    ("Yasuo", "Malphite", 0.35), ("Yasuo", "Alistar", 0.30), ("Yasuo", "Gragas", 0.30),
    ("Yasuo", "Rell", 0.30), ("Yasuo", "Diana", 0.28), ("Yasuo", "Wukong", 0.28),
    ("Yasuo", "Jarvan IV", 0.30), ("Yasuo", "Nautilus", 0.22), ("Yasuo", "Orianna", 0.25),
    ("Yasuo", "Kennen", 0.28), ("Yasuo", "Hecarim", 0.22), ("Yasuo", "Sejuani", 0.22),
    ("Yone", "Malphite", 0.30), ("Yone", "Alistar", 0.25), ("Yone", "Gragas", 0.25),
    ("Yone", "Diana", 0.28), ("Yone", "Wukong", 0.25), ("Yone", "Jarvan IV", 0.28),
    ("Yone", "Orianna", 0.25), ("Yone", "Kennen", 0.25),
    # Ult combos
    ("Orianna", "Malphite", 0.30), ("Orianna", "Wukong", 0.25), ("Orianna", "Amumu", 0.25),
    ("Miss Fortune", "Amumu", 0.32), ("Miss Fortune", "Sejuani", 0.28),
    ("Miss Fortune", "Malphite", 0.28), ("Miss Fortune", "Galio", 0.25),
    ("Kennen", "Diana", 0.28), ("Kennen", "Galio", 0.25), ("Kennen", "Wukong", 0.25),
    ("Karthus", "Maokai", 0.22), ("Karthus", "Amumu", 0.25),
    ("Galio", "Akali", 0.25), ("Galio", "Diana", 0.25), ("Galio", "Katarina", 0.25),
    ("Galio", "LeBlanc", 0.22), ("Galio", "Zed", 0.22),
    # Hypercarry + peel
    ("Kog'Maw", "Lulu", 0.40), ("Kog'Maw", "Janna", 0.30), ("Kog'Maw", "Yuumi", 0.30),
    ("Kog'Maw", "Milio", 0.30), ("Vayne", "Lulu", 0.35), ("Vayne", "Janna", 0.32),
    ("Vayne", "Yuumi", 0.28), ("Vayne", "Milio", 0.28),
    ("Twitch", "Lulu", 0.32), ("Twitch", "Yuumi", 0.32),
    ("Jinx", "Lulu", 0.28), ("Jinx", "Janna", 0.28), ("Jinx", "Thresh", 0.25),
    ("Aphelios", "Soraka", 0.30), ("Aphelios", "Lulu", 0.28),
    ("Master Yi", "Lulu", 0.40), ("Master Yi", "Zilean", 0.32),
    ("Kayle", "Lulu", 0.30), ("Kayle", "Zilean", 0.32), ("Kayle", "Soraka", 0.25),
    ("Tristana", "Lulu", 0.25),
    # Pick / catch combos
    ("Thresh", "Lucian", 0.35), ("Nautilus", "Lucian", 0.28),
    ("Leona", "Lucian", 0.30), ("Leona", "Draven", 0.25), ("Leona", "Miss Fortune", 0.25),
    ("Blitzcrank", "Caitlyn", 0.22), ("Blitzcrank", "Lucian", 0.22),
    ("Pyke", "Draven", 0.28), ("Pyke", "Lucian", 0.25),
    # Globals / TP plays
    ("Twisted Fate", "Shen", 0.30), ("Twisted Fate", "Pantheon", 0.25),
    ("Shen", "Karthus", 0.20), ("Pantheon", "Ashe", 0.20),
    ("Nocturne", "Tristana", 0.25), ("Nocturne", "Ashe", 0.22),
    # Engage + follow-up
    ("Maokai", "Kennen", 0.25), ("Hecarim", "Galio", 0.25),
    ("Sejuani", "Orianna", 0.22), ("Sejuani", "Miss Fortune", 0.25),
    ("Amumu", "Yasuo", 0.30), ("Amumu", "Brand", 0.25),
    ("Zac", "Yasuo", 0.25), ("Zac", "Karthus", 0.22),
    # Bot lane kill combos
    ("Senna", "Tahm Kench", 0.30), ("Senna", "Lucian", 0.25),
    ("Xayah", "Rakan", 0.45),  # racial bonus
    # AP backline ult combos
    ("Diana", "Hecarim", 0.28), ("Diana", "Sejuani", 0.22),
    ("Lissandra", "Yasuo", 0.22), ("Lissandra", "Karthus", 0.22),
    ("Anivia", "Karthus", 0.20),
])


# Anti-synergy penalty (negative team score). Used for compositions that fight themselves.
ANTI_SYNERGIES: Dict[Tuple[str, str], float] = _build_pairs([
    # Two immobile late-game carries with no peel implication — overrelies on team
    ("Karthus", "Kog'Maw", 0.15), ("Karthus", "Veigar", 0.12),
    # Yasuo with no knockup partner is handled at the comp-vector level, not pair level
    # Double engage that shares CDs (overkill, leaves nothing for re-engage)
    ("Malphite", "Amumu", 0.10), ("Malphite", "Sejuani", 0.10),
    ("Leona", "Nautilus", 0.08),
    # Overlapping ult zones (both want to combo same enemy, wasted CDs)
    ("Orianna", "Lux", 0.08), ("Orianna", "Veigar", 0.08),
    # Two heal-supports (impossible in 1 game) — symmetry catch
    ("Soraka", "Sona", 0.10), ("Soraka", "Yuumi", 0.10),
    # Yuumi with non-hypercarry — Yuumi needs a host that scales
    ("Yuumi", "Garen", 0.15), ("Yuumi", "Darius", 0.15),
])


def synergy_score(champs: Sequence[str]) -> float:
    """Sum of pair synergies minus anti-synergies for a 5-champ team."""
    s = 0.0
    n = len(champs)
    for i in range(n):
        for j in range(i + 1, n):
            p = _pair(champs[i], champs[j])
            s += SYNERGIES.get(p, 0.0)
            s -= ANTI_SYNERGIES.get(p, 0.0)
    return s


# ============================================================================
# Counter matrix: COUNTERS[(your_champ, enemy_champ)] = strength
# Your champ counters enemy. Strength in [0.1, 0.5].
# ============================================================================

# Phase 2 rewrite: values rescaled from the old 0.10-0.50 range to a wider
# 0.30-0.90 range so hard counters dominate scoring at counter-pick slots.
# Tiers:
#   0.30-0.40   soft tilt (counters but doesn't decide lane on its own)
#   0.45-0.55   solid counter (notable advantage)
#   0.60-0.75   hard counter (you should pick this if the slot allows)
#   0.80-0.90   devastating (perma-banned / unplayable matchup)
#
# Linear stretch used on legacy entries: new = 0.30 + (old - 0.10) * 1.5.
# `counter_value` / `blind_safety` normalization in draft_board.py is bumped
# in lockstep so `cv` and `bs` still land in 0..1.
COUNTERS: Dict[Tuple[str, str], float] = {
    # Anti-mobility / suppression / point-click vs Yasuo/Yone/Kassadin
    ("Malzahar", "Yasuo"): 0.85, ("Malzahar", "Yone"): 0.75, ("Malzahar", "Kassadin"): 0.70,
    ("Annie", "Yasuo"): 0.70, ("Annie", "Yone"): 0.60,
    ("Pantheon", "Yasuo"): 0.60, ("Renekton", "Yasuo"): 0.60,
    # Anti-assassin / shields / point-click CC
    ("Galio", "Zed"): 0.60, ("Galio", "Akali"): 0.60, ("Galio", "LeBlanc"): 0.60,
    ("Galio", "Diana"): 0.55, ("Galio", "Katarina"): 0.60,
    ("Lissandra", "Zed"): 0.70, ("Lissandra", "Akali"): 0.60, ("Lissandra", "Yasuo"): 0.55,
    ("Diana", "Zed"): 0.55, ("Diana", "Yasuo"): 0.55,
    ("Kassadin", "Xerath"): 0.75, ("Kassadin", "Vel'Koz"): 0.75, ("Kassadin", "Lux"): 0.70,
    ("Kassadin", "Anivia"): 0.60, ("Kassadin", "Cassiopeia"): 0.55,
    # Anti-tank (true damage / %hp)
    ("Vayne", "Cho'Gath"): 0.75, ("Vayne", "Skarner"): 0.60, ("Vayne", "Malphite"): 0.60,
    ("Vayne", "Ornn"): 0.60, ("Vayne", "Sion"): 0.60,
    ("Fiora", "Cho'Gath"): 0.85, ("Fiora", "Sion"): 0.75, ("Fiora", "Ornn"): 0.75,
    ("Fiora", "Tahm Kench"): 0.60, ("Fiora", "Dr. Mundo"): 0.60,
    ("Kayle", "Garen"): 0.55, ("Kayle", "Nasus"): 0.60,
    ("Kog'Maw", "Cho'Gath"): 0.85, ("Kog'Maw", "Sion"): 0.75, ("Kog'Maw", "Malphite"): 0.70,
    ("Olaf", "Vladimir"): 0.60, ("Olaf", "Fiora"): 0.60, ("Olaf", "Tryndamere"): 0.70,
    ("Trundle", "Cho'Gath"): 0.75, ("Trundle", "Sion"): 0.75, ("Trundle", "Ornn"): 0.75,
    # Anti-ranged top
    ("Jax", "Quinn"): 0.60, ("Jax", "Teemo"): 0.60, ("Jax", "Jayce"): 0.55,
    ("Jax", "Gnar"): 0.55, ("Jax", "Vayne"): 0.55, ("Jax", "Kennen"): 0.55,
    ("Irelia", "Lux"): 0.55, ("Irelia", "Karma"): 0.55,
    # Anti-juggernaut (kite + ranged)
    ("Quinn", "Darius"): 0.75, ("Quinn", "Sett"): 0.70, ("Quinn", "Garen"): 0.75,
    ("Quinn", "Aatrox"): 0.60, ("Quinn", "Mordekaiser"): 0.60,
    ("Vayne", "Darius"): 0.70, ("Vayne", "Mordekaiser"): 0.60, ("Vayne", "Aatrox"): 0.55,
    ("Gnar", "Darius"): 0.60, ("Gnar", "Aatrox"): 0.55, ("Gnar", "Sett"): 0.55,
    ("Jayce", "Darius"): 0.60, ("Jayce", "Sett"): 0.55, ("Jayce", "Aatrox"): 0.55,
    ("Teemo", "Darius"): 0.75, ("Teemo", "Garen"): 0.70,
    # Anti-immobile carry (assassins on backline)
    ("Zed", "Karthus"): 0.70, ("Zed", "Veigar"): 0.60, ("Zed", "Annie"): 0.60,
    ("Zed", "Xerath"): 0.60, ("Zed", "Anivia"): 0.60, ("Zed", "Orianna"): 0.55,
    ("Talon", "Karthus"): 0.60, ("Talon", "Veigar"): 0.60, ("Talon", "Lux"): 0.60,
    ("Kha'Zix", "Kog'Maw"): 0.70, ("Kha'Zix", "Jinx"): 0.55, ("Kha'Zix", "Karthus"): 0.60,
    ("Rengar", "Kog'Maw"): 0.60, ("Rengar", "Jinx"): 0.55,
    ("Akali", "Karthus"): 0.55, ("Akali", "Veigar"): 0.55,
    # Anti-AD lane bullies
    ("Vladimir", "Darius"): 0.60, ("Vladimir", "Renekton"): 0.60, ("Vladimir", "Riven"): 0.55,
    ("Cassiopeia", "Riven"): 0.55, ("Cassiopeia", "Yasuo"): 0.55,
    # Jungle counter-picks
    ("Rammus", "Master Yi"): 0.85, ("Rammus", "Tryndamere"): 0.70, ("Rammus", "Yasuo"): 0.60,
    ("Rammus", "Vayne"): 0.60, ("Rammus", "Jax"): 0.55,
    ("Nocturne", "Karthus"): 0.60, ("Nocturne", "Anivia"): 0.55,
    # Anti-engage / disengage
    ("Janna", "Malphite"): 0.60, ("Janna", "Hecarim"): 0.55, ("Janna", "Alistar"): 0.55,
    ("Anivia", "Sejuani"): 0.45, ("Anivia", "Hecarim"): 0.45,
    ("Tahm Kench", "Zed"): 0.60, ("Tahm Kench", "Akali"): 0.55, ("Tahm Kench", "Kha'Zix"): 0.55,
    # Anti-poke
    ("Galio", "Xerath"): 0.70, ("Galio", "Vel'Koz"): 0.60, ("Galio", "Varus"): 0.55,
    ("Sivir", "Xerath"): 0.55, ("Sivir", "Varus"): 0.55,
    # ADC-on-ADC
    ("Draven", "Kog'Maw"): 0.60, ("Draven", "Vayne"): 0.60, ("Draven", "Aphelios"): 0.55,
    ("Caitlyn", "Vayne"): 0.60, ("Caitlyn", "Kalista"): 0.55,
    ("Lucian", "Kog'Maw"): 0.55, ("Lucian", "Jinx"): 0.55,
    # Anti-hypercarry support
    ("Pyke", "Soraka"): 0.60, ("Pyke", "Yuumi"): 0.55, ("Pyke", "Janna"): 0.45,
    # Wide-purpose
    ("Mordekaiser", "Tryndamere"): 0.75, ("Mordekaiser", "Fiora"): 0.70,
    ("Mordekaiser", "Vladimir"): 0.60,
    ("Camille", "Vayne"): 0.55, ("Camille", "Kog'Maw"): 0.60, ("Camille", "Jinx"): 0.55,
    ("Wukong", "Yasuo"): 0.55,
    ("Garen", "Katarina"): 0.60, ("Garen", "Akali"): 0.55,

    # ─── 2025/2026 meta additions (Phase 2 expansion) ──────────────────────
    # Ambessa — bruiser with mobility + MR shred. Hard counters are ranged
    # poke tops and CC that ignores her dash. Counters squishy duelists.
    ("Quinn", "Ambessa"): 0.70, ("Vayne", "Ambessa"): 0.60, ("Teemo", "Ambessa"): 0.65,
    ("Pantheon", "Ambessa"): 0.55, ("Renekton", "Ambessa"): 0.55,
    ("Ambessa", "Yasuo"): 0.60, ("Ambessa", "Riven"): 0.55, ("Ambessa", "Fiora"): 0.55,
    # Mel — reflects projectiles. Countered by point-click + bursty assassins
    # without projectile primary. Counters skill-shot mages.
    ("Annie", "Mel"): 0.65, ("Ahri", "Mel"): 0.55, ("Talon", "Mel"): 0.60,
    ("Zed", "Mel"): 0.55, ("Fizz", "Mel"): 0.55,
    ("Mel", "Karthus"): 0.65, ("Mel", "Lux"): 0.60, ("Mel", "Xerath"): 0.65,
    ("Mel", "Vel'Koz"): 0.60,
    # Aurora — kite mage with self-peel. Countered by gap-closers + early CC.
    # Counters tanks (innate %hp damage), juggernauts that can't reach her.
    ("Camille", "Aurora"): 0.60, ("Yone", "Aurora"): 0.55, ("Malphite", "Aurora"): 0.60,
    ("Pantheon", "Aurora"): 0.55,
    ("Aurora", "Cho'Gath"): 0.65, ("Aurora", "Sion"): 0.60, ("Aurora", "Ornn"): 0.55,
    ("Aurora", "Darius"): 0.55,
    # Hwei — heavy zone control mid. Countered by mobile assassins, counters
    # the immobile mage class.
    ("Akali", "Hwei"): 0.60, ("Sylas", "Hwei"): 0.55, ("LeBlanc", "Hwei"): 0.60,
    ("Talon", "Hwei"): 0.55,
    ("Hwei", "Karthus"): 0.60, ("Hwei", "Veigar"): 0.55,
    # Smolder — late-game ADC. Countered by lane bullies. Counters most ADCs late.
    ("Draven", "Smolder"): 0.65, ("Caitlyn", "Smolder"): 0.55, ("Lucian", "Smolder"): 0.60,
    ("Smolder", "Vayne"): 0.55,
    # K'Sante — disruptor tank. Countered by true damage + sustain bruisers.
    ("Fiora", "K'Sante"): 0.70, ("Vayne", "K'Sante"): 0.60, ("Cassiopeia", "K'Sante"): 0.55,
    ("K'Sante", "Yone"): 0.55, ("K'Sante", "Yasuo"): 0.60, ("K'Sante", "Riven"): 0.55,
    # Briar — frenzy jungle bruiser. Countered by anti-heal / CC.
    ("Rammus", "Briar"): 0.65, ("Trundle", "Briar"): 0.55, ("Tahm Kench", "Briar"): 0.55,
    ("Olaf", "Briar"): 0.55,
    # Naafiri — pack-of-dogs assassin. Countered by point-click CC, big AOE.
    # Counters squishy single-target mages.
    ("Galio", "Naafiri"): 0.60, ("Lissandra", "Naafiri"): 0.55, ("Annie", "Naafiri"): 0.55,
    ("Naafiri", "Yasuo"): 0.55, ("Naafiri", "Zed"): 0.55, ("Naafiri", "Akali"): 0.55,
    # Bel'Veth — late-scaling jungler that snowballs early. Countered by tanky
    # jungles that can survive her tail-whip burst.
    ("Vi", "Bel'Veth"): 0.55, ("Lee Sin", "Bel'Veth"): 0.55, ("Rammus", "Bel'Veth"): 0.60,
    ("Bel'Veth", "Sett"): 0.55, ("Bel'Veth", "Aatrox"): 0.55, ("Bel'Veth", "Tryndamere"): 0.60,
    # Sylas — ult-stealer. Counters teams with one big ult; countered by
    # point-click burst.
    ("Annie", "Sylas"): 0.55, ("Pantheon", "Sylas"): 0.55,
    ("Sylas", "Galio"): 0.60, ("Sylas", "Karthus"): 0.60, ("Sylas", "Malphite"): 0.55,
    # Renata Glasc — anti-engage support, reverses target on death.
    ("Renata Glasc", "Yasuo"): 0.55, ("Renata Glasc", "Master Yi"): 0.55,
    ("Pyke", "Renata Glasc"): 0.55, ("Blitzcrank", "Renata Glasc"): 0.55,
    # Senna — scaling sup/bot, anti-heal innate. Countered by hard engage.
    ("Senna", "Soraka"): 0.55, ("Senna", "Yuumi"): 0.60,
    ("Pyke", "Senna"): 0.55, ("Blitzcrank", "Senna"): 0.55,
    # Akshan — revive support ADC. Counters channel ults; countered by burst.
    ("Akshan", "Karthus"): 0.65, ("Akshan", "Yasuo"): 0.55,
    ("Ahri", "Akshan"): 0.55, ("Diana", "Akshan"): 0.55,
}


def counter_score(your_champ: str, enemies: Sequence[str]) -> float:
    """Sum of counter strengths from your champ vs each enemy champ."""
    return sum(COUNTERS.get((your_champ, e), 0.0) for e in enemies if e)


def team_counter_coverage(your_team: Sequence[str], enemy_champ: str) -> float:
    """Max counter strength from any champ on your team against the enemy champ."""
    best = 0.0
    for c in your_team:
        if not c:
            continue
        v = COUNTERS.get((c, enemy_champ), 0.0)
        if v > best:
            best = v
    return best


# ============================================================================
# Archetypes — now with team identity vectors and win conditions
# ============================================================================

# Identity vector axes (each ≥0 contribution per champ):
#   frontline, engage, peel, aoe, burst, range, scaling, mobility
_AXES = ("frontline", "engage", "peel", "aoe", "burst", "range", "scaling", "mobility")

# Map champion → axis contributions (0..1 each). Derived from SUBCLASSES.
def _champ_vector(champ: str) -> Dict[str, float]:
    v = {a: 0.0 for a in _AXES}
    if champ in SUBCLASSES["frontline"]: v["frontline"] += 1.0
    if champ in SUBCLASSES["engage"]:    v["engage"]    += 1.0
    if champ in SUBCLASSES["peel"]:      v["peel"]      += 1.0
    if champ in SUBCLASSES["aoe_damage"]:v["aoe"]       += 1.0
    if champ in SUBCLASSES["assassin_or_burst"]: v["burst"] += 1.0
    if champ in SUBCLASSES["long_range"]:v["range"]     += 1.0
    if champ in SUBCLASSES["hypercarry"]:v["scaling"]   += 1.0
    if champ in SUBCLASSES["scaling"]:   v["scaling"]   += 1.0
    if champ in SUBCLASSES["mobile"]:    v["mobility"]  += 1.0
    if champ in SUBCLASSES["cc"]:        v["engage"]    += 0.3  # CC partial credit toward engage
    return v


# Each archetype: target identity vector (what the team should look like) +
# metadata. Phase 2: added `game_plan` (3-sentence concrete actions) and
# `auto_pref` (slight tilt for archetypes the engine should prefer all else
# equal — currently Teamfight gets +5% because front-to-back is the most
# popular and reliable composition in modern competitive play).
ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "Teamfight": {
        "label": "Teamfight  (AoE + Engage)",
        "target": {"frontline": 1.5, "engage": 1.5, "aoe": 2.0, "peel": 0.5, "scaling": 0.5},
        "conflict_axes": {"mobility": 0.0},   # over-mobile = doesn't group
        "win_condition": "Group at 4 items, force 5v5 around objectives",
        "spike": "mid-game (3 items)",
        "auto_pref": 1.05,
        "game_plan": (
            "Group 5 around Dragon/Baron at 3 items. Frontline absorbs engage "
            "while your AoE casts a fight-winning ult. Avoid scattered fights "
            "before the frontline is online — your win condition is the 5v5."
        ),
    },
    "Pick": {
        "label": "Pick  (Catch + Burst)",
        "target": {"burst": 2.0, "engage": 1.5, "mobility": 1.5, "frontline": 0.5},
        "conflict_axes": {"scaling": 0.0},
        "win_condition": "Catch isolated targets, snowball mid-game off picks",
        "spike": "mid-game (level 11)",
        "auto_pref": 1.00,
        "game_plan": (
            "Ward deep, then hunt isolated targets across the map. After every "
            "pick, contest the next neutral objective 5v4. Don't engage 5v5 — "
            "force the enemy to step alone."
        ),
    },
    "Split Push": {
        "label": "Split Push  (1-3-1)",
        "target": {"scaling": 1.0, "peel": 0.5, "range": 1.0, "mobility": 1.0},
        "conflict_axes": {"engage": 0.5},
        "win_condition": "Apply side-lane pressure, force 4v4 ± duelist",
        "spike": "mid-game with TP/teleport timings",
        "auto_pref": 1.00,
        "game_plan": (
            "Send your duelist top, group 4 mid. Force the enemy to choose: "
            "send 2 to stop your splitter (you win mid 4v3), or let them "
            "siege (your duelist takes a tower). Track enemy TPs religiously."
        ),
    },
    "Poke / Siege": {
        "label": "Poke / Siege  (Range + Zone)",
        "target": {"range": 2.5, "peel": 1.0, "aoe": 1.0, "scaling": 0.5},
        "conflict_axes": {"engage": 0.0, "burst": 0.0},
        "win_condition": "Whittle HP at objectives, break tower before they engage",
        "spike": "mid-game with poke items (Manamune/Liandry)",
        "auto_pref": 1.00,
        "game_plan": (
            "Stand at max range and poke before each objective takedown. "
            "Once 2+ enemies are sub-50%, force tower / dragon. Never let "
            "them flank you — vision deep, fall back if poke isn't connecting."
        ),
    },
    "Protect the Carry": {
        "label": "Protect the Carry  (Shield/Peel)",
        "target": {"scaling": 2.0, "peel": 2.5, "frontline": 1.0, "engage": 0.5},
        "conflict_axes": {"burst": 0.0},
        "win_condition": "Survive to late, hypercarry wins 5v5 with peel",
        "spike": "late-game (4 items on carry)",
        "auto_pref": 1.00,
        "game_plan": (
            "Farm safely until your carry hits 4 items. Every fight, the team "
            "stacks on the carry — shields, peel, frontline soak. Never "
            "split off; protect the win condition at all costs."
        ),
    },
    "Dive": {
        "label": "Dive  (Hard Engage + Collapse)",
        "target": {"engage": 2.5, "burst": 1.5, "frontline": 1.0, "mobility": 1.5},
        "conflict_axes": {"scaling": 0.0, "range": 0.5},
        "win_condition": "Collapse on backline before they can position",
        "spike": "early-to-mid game (level 6-11)",
        "auto_pref": 1.00,
        "game_plan": (
            "Press the early game hard — your spike is level 6-11. Force "
            "fights before enemy carries hit 2 items. Engage tank flanks "
            "behind enemy frontline, burst collapses on the squishies."
        ),
    },
    "Scaling": {
        "label": "Scaling  (Late-game win)",
        "target": {"scaling": 2.5, "peel": 1.5, "aoe": 0.5, "range": 0.5},
        "conflict_axes": {"engage": 0.5, "burst": 0.0},
        "win_condition": "Survive lane, scale to 4 items, win every 5v5 after 25min",
        "spike": "late-game (35+ min)",
        "auto_pref": 1.00,
        "game_plan": (
            "Play safe in lane — losing 0/2/0 with CS is fine. Group only "
            "when forced, give up early objectives if the trade is unfair. "
            "After 25 minutes you out-stat every comp; force fights then."
        ),
    },
}


def _team_vector(champs: Sequence[str]) -> Dict[str, float]:
    out = {a: 0.0 for a in _AXES}
    for c in champs:
        if not c:
            continue
        cv = _champ_vector(c)
        for k, v in cv.items():
            out[k] += v
    return out


def _archetype_vector_score(champs: Sequence[str], arch_name: str) -> float:
    """0..1 score for how well a team meets the archetype's identity vector."""
    arch = ARCHETYPES[arch_name]
    target = arch["target"]
    tv = _team_vector(champs)
    score = 0.0
    weight_total = 0.0
    for axis, req in target.items():
        if req <= 0:
            continue
        got = tv.get(axis, 0.0)
        # Diminishing return past target — full credit at req, half credit past
        if got >= req:
            score += req + min(got - req, req) * 0.25
        else:
            score += got
        weight_total += req * 1.25
    base = (score / max(weight_total, 0.1))
    # Penalize axes the archetype explicitly conflicts with
    for axis, cap in arch.get("conflict_axes", {}).items():
        excess = tv.get(axis, 0.0) - cap
        if excess > 0:
            base -= 0.07 * excess
    return max(0.0, base)


# ============================================================================
# Role validity
# ============================================================================

ROLE_VALID: Dict[str, Set[str]] = {
    "TOP": {"Aatrox","Ambessa","Aurora","Camille","Cho'Gath","Darius","Dr. Mundo","Fiora",
            "Gangplank","Garen","Gnar","Gwen","Illaoi","Irelia","Jax","Jayce","K'Sante",
            "Kayle","Kennen","Kled","Malphite","Maokai","Mordekaiser","Nasus","Olaf","Ornn",
            "Pantheon","Poppy","Quinn","Renekton","Riven","Rumble","Sett","Shen","Sion",
            "Tahm Kench","Teemo","Trundle","Tryndamere","Urgot","Vladimir","Volibear",
            "Wukong","Yasuo","Yone","Yorick","Gragas","Akali","Warwick","Zac"},
    "JGL": {"Amumu","Ambessa","Bel'Veth","Briar","Diana","Ekko","Elise","Evelynn",
            "Fiddlesticks","Gragas","Graves","Hecarim","Ivern","Jarvan IV","Karthus","Kayn",
            "Kha'Zix","Kindred","Lee Sin","Lillia","Master Yi","Nidalee","Nocturne","Nunu",
            "Pantheon","Poppy","Rammus","Rek'Sai","Rengar","Sejuani","Shaco","Shyvana",
            "Skarner","Taliyah","Udyr","Vi","Viego","Volibear","Warwick","Wukong",
            "Xin Zhao","Zac","Maokai","Trundle","Sylas"},
    "MID": {"Ahri","Akali","Akshan","Anivia","Annie","Aurelion Sol","Azir","Cassiopeia",
            "Corki","Diana","Ekko","Fizz","Galio","Hwei","Irelia","Kassadin","Katarina",
            "LeBlanc","Lissandra","Lux","Malzahar","Mel","Naafiri","Neeko","Orianna",
            "Pantheon","Qiyana","Ryze","Sylas","Syndra","Taliyah","Talon","Tristana",
            "Twisted Fate","Veigar","Vex","Viktor","Vladimir","Xerath","Yasuo","Yone","Zed",
            "Zoe","Ziggs","Aurora","Jayce","Rumble","Heimerdinger","Zyra"},
    "BOT": {"Aphelios","Ashe","Caitlyn","Corki","Draven","Ezreal","Jhin","Jinx","Kai'Sa",
            "Kalista","Kog'Maw","Lucian","Miss Fortune","Nilah","Samira","Sivir","Smolder",
            "Tristana","Twitch","Varus","Vayne","Xayah","Zeri","Ziggs","Senna"},
    "SUP": {"Alistar","Bard","Blitzcrank","Braum","Janna","Karma","Leona","Lulu","Lux",
            "Mel","Milio","Morgana","Nami","Nautilus","Pyke","Rakan","Rell","Renata Glasc",
            "Senna","Seraphine","Sona","Soraka","Taric","Thresh","Yuumi","Zilean","Zyra",
            "Xerath","Vel'Koz","Maokai","Poppy","Tahm Kench","Galio"},
}


# ============================================================================
# Bayesian confidence shrinkage
# ============================================================================

# Prior: Beta(α, β) with mean=50%. Higher α+β = stronger prior (more shrinkage on small N).
_BAYES_ALPHA = 4.0
_BAYES_BETA  = 4.0


def shrink_wr(wins: float, games: float, prior_wr: float = 0.50) -> float:
    """Posterior winrate (0..1) given Beta prior. Pulls toward prior on small N."""
    if games <= 0:
        return prior_wr
    a = _BAYES_ALPHA * (prior_wr / 0.5)
    b = _BAYES_BETA  * ((1 - prior_wr) / 0.5)
    return (wins + a) / (games + a + b)


def shrink_wr_from_pct(wr_pct: float, games: float, prior_wr: float = 0.50) -> float:
    """Shrink a WR given as 0..100 with games count → returns 0..1 posterior."""
    wins = (wr_pct / 100.0) * games
    return shrink_wr(wins, games, prior_wr)


def recency_weighted_wr(results, half_life: float = 18.0):
    """Exponentially recency-weighted winrate from a chronological list of
    1=win/0=loss (oldest→newest, e.g. the per-champ customs `results` the
    reader now emits, capped to the last 100 games). The most recent game
    has weight 1.0; weight halves every `half_life` games back.

    Returns (wr_0to1, effective_n) or (None, 0.0) when there is no data.
    `effective_n` is the sum of weights — used to shrink small/stale samples.
    """
    if not results:
        return None, 0.0
    n = len(results)
    num = den = 0.0
    for i, r in enumerate(results):
        age = (n - 1) - i                       # 0 = most recent
        w = 0.5 ** (age / max(half_life, 1.0))
        den += w
        num += w * (1.0 if r else 0.0)
    if den <= 0:
        return None, 0.0
    return num / den, den


# ============================================================================
# Form modifier
# ============================================================================

def form_multiplier(form: Optional[str]) -> float:
    """Form → multiplier on comfort score."""
    if not form:
        return 1.0
    f = str(form).upper()
    if "HOT" in f:   return 1.10
    if "COLD" in f:  return 0.90
    return 1.0       # MIXED / unknown


# ============================================================================
# Helpers
# ============================================================================

def parse_wr(val: Any) -> float:
    """Parse '68.3%' or 68.3 → float 0..100. Returns 50.0 on garbage."""
    try:
        return float(str(val).replace("%", "").strip())
    except (ValueError, TypeError):
        return 50.0


def parse_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


# ============================================================================
# Player comfort scoring with Bayesian shrinkage + form + role mastery
# ============================================================================

def champion_comfort(
    games: float,
    wr_pct: float,
    kda: float,
    role_match: bool = True,
    form: Optional[str] = None,
    inhouse: bool = False,
    results=None,
    recency_half_life: float = 18.0,
    recency_weight: float = 0.65,
) -> float:
    """
    Composite 0..1 comfort score for a player on a champion.

    Combines:
      - Bayesian-shrunk winrate (so 1g/100% != 50g/70%)
      - Sample size signal (log-scaled)
      - KDA modifier
      - Role match bonus
      - Form modifier (HOT/COLD)
      - Inhouse data weighting (own-team data > general ranked)
      - Optional recency weighting (when `results` chronology is provided)

    Phase 2: `recency_half_life` is parameterised so the scout-pool path can
    use a slightly longer half-life (24 games) than customs (18 games),
    reflecting ranked being a lower-stakes/slower-changing signal. The
    `recency_weight` likewise lets the caller decide how dominant recent form
    is — customs uses 0.65 (default), scout-pool callers pass ~0.55.
    """
    if games <= 0:
        return 0.0
    wr_post = shrink_wr_from_pct(wr_pct, games)
    # Recency: when per-game results are available, let recent form dominate
    # (shrunk by its own recency-weighted effective N) while the all-time
    # posterior stays as an anchor.
    rec_wr, eff_n = (recency_weighted_wr(results, half_life=recency_half_life)
                     if results else (None, 0.0))
    if rec_wr is not None and eff_n > 0:
        rec_post = shrink_wr(rec_wr * eff_n, eff_n)
        wr_eff = recency_weight * rec_post + (1.0 - recency_weight) * wr_post
    else:
        wr_eff = wr_post
    sample  = math.log(1.0 + games) / math.log(1.0 + 30.0)  # 0..~1 over 30 games
    sample  = min(sample, 1.0)
    kda_mod = max(0.6, min(1.4, (kda or 1.5) / 2.5))
    base    = wr_eff * (0.55 + 0.45 * sample) * kda_mod
    if role_match:
        base *= 1.20
    base *= form_multiplier(form)
    if inhouse:
        base *= 1.25
    return min(base, 1.0)


# ============================================================================
# Champion priors (small handcrafted nudges, used only when player has 0 data)
# ============================================================================

# Champions with notably above-average "any-player" win likelihood right now.
# Used only when a player has zero inhouse + zero top_champs data so the engine
# isn't stuck recommending '?'. Numbers are seeds, not measured.
CHAMP_PRIORS: Dict[str, float] = {
    "Garen": 0.52, "Darius": 0.52, "Master Yi": 0.53, "Tryndamere": 0.52,
    "Annie": 0.52, "Ashe": 0.52, "Brand": 0.52, "Morgana": 0.52,
}


# ============================================================================
# Team scoring (the heart of beam search)
# ============================================================================

def score_team(
    champs: Sequence[str],
    comforts: Sequence[float],
    arch_name: str,
    enemy_picks: Sequence[str] = (),
) -> Dict[str, float]:
    """
    Score a 5-champ team for an archetype. Returns a breakdown dict so the UI
    can show *why* a comp was ranked.

    Components (each 0..1 roughly):
      identity     — fits archetype vector
      synergy      — pair synergies − anti-synergies
      damage       — AP/AD balance (~30/70 to 70/30 is healthy, single-type penalised)
      counter      — counters vs locked enemy picks
      comfort      — average player comfort across the 5
      coherence    — penalty for axis-gaps the archetype needs but team lacks
    """
    identity = _archetype_vector_score(champs, arch_name)
    syn      = synergy_score(champs)
    # Damage profile
    ap = ad = 0.0
    for c in champs:
        a, d = champ_damage_split(c)
        ap += a; ad += d
    tot  = ap + ad if (ap + ad) > 0 else 1.0
    ap_r = ap / tot
    # Healthy band: 0.30 ≤ ap_ratio ≤ 0.70 = full credit
    if 0.30 <= ap_r <= 0.70:
        damage = 1.0
    elif 0.20 <= ap_r <= 0.80:
        damage = 0.70
    else:
        damage = 0.35

    # Counter score (your team vs each enemy pick — sum of best matchups)
    counter = 0.0
    if enemy_picks:
        for ep in enemy_picks:
            counter += team_counter_coverage(champs, ep)
        counter = min(counter / max(len(enemy_picks), 1), 1.0)

    comfort = sum(comforts) / max(len(comforts), 1)

    # Coherence: penalize critical axis gaps
    tv = _team_vector(champs)
    target = ARCHETYPES[arch_name]["target"]
    gaps = 0.0
    for axis, req in target.items():
        if req >= 1.0:
            shortfall = max(0.0, req - tv.get(axis, 0.0))
            gaps += shortfall
    coherence = max(0.0, 1.0 - 0.20 * gaps)

    # Final weighted score
    total = (
        identity * 0.28 +
        comfort  * 0.32 +
        synergy_normalize(syn) * 0.15 +
        damage   * 0.08 +
        counter  * 0.10 +
        coherence* 0.07
    )

    return {
        "total":     total,
        "identity":  identity,
        "synergy":   syn,
        "damage":    damage,
        "counter":   counter,
        "comfort":   comfort,
        "coherence": coherence,
        "ap_ratio":  ap_r,
    }


def synergy_normalize(s: float) -> float:
    """Map raw synergy sum (typically -0.5..+2.0) into 0..1."""
    return max(0.0, min(1.0, (s + 0.5) / 2.5))


# ============================================================================
# Beam search comp recommender
# ============================================================================

def customs_champs(p: Dict[str, Any],
                   inhouse_champs: Dict[str, List[Dict]],
                   min_games: int = 3) -> Dict[str, float]:
    """{champ: recency-weighted comfort} for champs this player has actually
    played in customs ≥ `min_games` times. Excludes ranked mastery / priors —
    this is the strict "they really play it" signal that `contested` needs."""
    out: Dict[str, float] = {}
    for ch in (inhouse_champs.get(p.get("name", ""), []) or []):
        cname = ch.get("champ")
        if not cname:
            continue
        if parse_float(ch.get("games", 0)) < min_games:
            continue
        out[cname] = champion_comfort(
            parse_float(ch.get("games", 0)), parse_wr(ch.get("wr", "50%")),
            parse_float(ch.get("kda"), 1.5), role_match=True,
            form=p.get("form"), inhouse=True, results=ch.get("results"))
    return out


# Multiplier on scout-sheet (ranked + draft) comfort relative to customs:
# scout-sheet data covers ranked/draft games (no inhouse weighting, no
# per-game recency). It is a stronger signal than name-only top_champs but
# weaker than demonstrated customs play.
_SCOUT_CHAMPS_WEIGHT = 0.85


def scout_pool_champs(p: Dict[str, Any],
                      scout_champs: Dict[str, List[Dict]],
                      min_games: int = 3) -> Dict[str, float]:
    """{champ: comfort} from a player's scout-sheet FULL CHAMPION POOL
    (ranked + draft, pooled across roles). Used as a secondary signal when
    a champ has no customs play. Weighted below customs via _SCOUT_CHAMPS_WEIGHT."""
    out: Dict[str, float] = {}
    pname = p.get("name", "")
    for ch in (scout_champs.get(pname, []) or []):
        cname = ch.get("champ")
        if not cname:
            continue
        g = parse_float(ch.get("games", 0))
        if g < min_games:
            continue
        # Phase 2: pass scout-pool `results` chronology + ranked half-life.
        out[cname] = _SCOUT_CHAMPS_WEIGHT * champion_comfort(
            g, parse_wr(ch.get("wr", "50%")),
            parse_float(ch.get("kda"), 1.5), role_match=True,
            form=p.get("form"), inhouse=False,
            results=ch.get("results"),
            recency_half_life=24.0, recency_weight=0.55)
    return out


# ============================================================================
# Off-role + pool-depth + sample-size helpers (Phase 2)
# ============================================================================

def off_role_severity(
    player: Dict[str, Any],
    role: str,
    inhouse_champs: Dict[str, List[Dict]],
    primary_roles: Optional[Dict[str, str]] = None,
    scout_champs: Optional[Dict[str, List[Dict]]] = None,
) -> float:
    """
    0..1 score for how off-role a player is at the given assigned role.

      0.00  on primary role (no penalty)
      0.20  on primary, but has shown they can also play this role in customs
      0.45  off-primary but has 2+ customs champs at the role / 8+ games
      0.65  off-primary, has 1 customs champ at role or a deep ranked pool
      0.90  off-primary with no real history at this role (severe)

    Used to decay comfort scores so off-role recommendations don't beat
    on-role demonstrated play. The UI consumes the same signal via
    `pool_depth(...)` for the team-builder badge.
    """
    pname = player.get("name", "")
    role_norm = ROLE_NORM.get(role, role)
    primary = primary_roles.get(pname) if primary_roles else None
    is_primary = bool(primary and primary == role_norm)

    # Count customs champs played AT this role (using per-champ role breakdown).
    customs_at_role = 0
    customs_games_at_role = 0.0
    for ch in (inhouse_champs.get(pname) or []):
        ch_roles = ch.get("roles") or {}
        if not isinstance(ch_roles, dict) or not ch_roles:
            continue
        g_at_role = parse_float(ch_roles.get(role_norm, 0))
        if g_at_role >= 3:
            customs_at_role += 1
            customs_games_at_role += g_at_role

    # Scout pool is across-role (no role breakdown) — use total breadth as a
    # mild rescue signal: a player with a deep ranked pool isn't *quite* as
    # off-role as someone with nothing.
    scout_pool_size = 0
    if scout_champs:
        for ch in (scout_champs.get(pname) or []):
            if parse_float(ch.get("games", 0)) >= 3:
                scout_pool_size += 1

    if is_primary:
        return 0.0
    # Off-primary tiers
    if customs_at_role >= 3 and customs_games_at_role >= 15:
        return 0.20
    if customs_at_role >= 2 or customs_games_at_role >= 8:
        return 0.45
    if customs_at_role >= 1 or scout_pool_size >= 4:
        return 0.65
    return 0.90


_OFF_ROLE_DECAY = 0.40   # multiplier impact: comfort *= (1 - _OFF_ROLE_DECAY * sev)


def sample_confidence(games: float) -> str:
    """Categorical sample-size confidence for the engine's `factors` dict.
    The UI's sample-size badge consumes this directly.

      "strong"  ≥30 games
      "ok"      8-29 games
      "thin"    <8 games
    """
    try:
        g = float(games)
    except (TypeError, ValueError):
        g = 0.0
    if g >= 30:
        return "strong"
    if g >= 8:
        return "ok"
    return "thin"


def pool_depth(
    player: Dict[str, Any],
    role: str,
    inhouse_champs: Dict[str, List[Dict]],
    primary_roles: Optional[Dict[str, str]] = None,
    scout_champs: Optional[Dict[str, List[Dict]]] = None,
) -> str:
    """
    Categorical pool-depth label for the team-builder slot badge.

      "DEEP"      6+ champs at this role between customs + scout-pool
      "OK"        3-5 champs at this role
      "SHALLOW"   1-2 champs at this role
      "OFF-ROLE"  not the player's primary role AND <3 unique champs

    Driven by the same customs role-breakdown the engine uses for comfort
    scoring. Scout pool acts as a soft rescue (only matters when customs at
    role is empty but the player has demonstrated ranked breadth).
    """
    pname = player.get("name", "")
    role_norm = ROLE_NORM.get(role, role)
    primary = primary_roles.get(pname) if primary_roles else None
    is_primary = bool(primary and primary == role_norm)

    champs_at_role: set = set()
    for ch in (inhouse_champs.get(pname) or []):
        cname = ch.get("champ")
        if not cname:
            continue
        ch_roles = ch.get("roles") or {}
        g_at_role = (parse_float(ch_roles.get(role_norm, 0))
                     if isinstance(ch_roles, dict) and ch_roles else 0.0)
        total_g = parse_float(ch.get("games", 0))
        # Either has explicit role breakdown showing 3+ games, OR has no
        # breakdown (legacy) but appears in customs with meaningful play —
        # assume those are on-role (primary or assigned).
        if g_at_role >= 3 or (not ch_roles and total_g >= 3 and is_primary):
            champs_at_role.add(cname)

    scout_breadth = 0
    if scout_champs:
        for ch in (scout_champs.get(pname) or []):
            if parse_float(ch.get("games", 0)) >= 3:
                scout_breadth += 1

    n = len(champs_at_role)
    if not is_primary and n < 3:
        return "OFF-ROLE"
    if n >= 6:
        return "DEEP"
    if n >= 3:
        return "OK"
    if n >= 1 or scout_breadth >= 5:
        return "SHALLOW"
    return "OFF-ROLE"


def _player_candidates(
    p: Dict[str, Any],
    inhouse_champs: Dict[str, List[Dict]],
    primary_roles: Dict[str, str],
    max_candidates: int = 8,
    scout_champs: Optional[Dict[str, List[Dict]]] = None,
) -> List[Tuple[str, float]]:
    """Return list of (champ, comfort) candidates for a player, sorted high→low.

    Comfort sources, in order of signal strength (each only used if previous
    didn't already cover the champ with a higher score):
      1. inhouse_champs — customs games, full per-champ stats + last-100 recency
      2. scout_champs   — scout-sheet FULL CHAMPION POOL (ranked + draft, pooled)
      3. top_champs     — name-only top 3 from rankings sheet, sample size guessed
      4. CHAMP_PRIORS   — global priors fallback when player has zero data
    """
    role = p.get("role", "")
    valid = ROLE_VALID.get(role, set())
    pname = p.get("name", "")
    form  = p.get("form")
    primary = primary_roles.get(pname) if primary_roles else None
    role_match = (primary == ROLE_NORM.get(role, role))

    # Random placeholder: pick from role pool with neutral comfort
    if p.get("is_random"):
        return [(c, 0.35) for c in sorted(valid)][:max_candidates * 3]

    ih_list = inhouse_champs.get(pname, []) or []
    ih_map  = {ch.get("champ"): ch for ch in ih_list if ch.get("champ")}

    seen: Dict[str, float] = {}
    # Inhouse champs (richer signal)
    for cname, ch in ih_map.items():
        if cname not in valid:
            continue
        g  = parse_float(ch.get("games", 0))
        wr = parse_wr(ch.get("wr", "50%"))
        kda = parse_float(ch.get("kda"), 1.5)
        # Check if their inhouse role for this champ matches assigned role
        ch_roles = ch.get("roles") or {}
        role_norm = ROLE_NORM.get(role, role)
        ch_role_match = role_match
        if isinstance(ch_roles, dict) and ch_roles:
            # If champ has been played in this exact role > 30% of the time, boost.
            ch_total = sum(parse_float(v) for v in ch_roles.values())
            if ch_total > 0:
                this_role_pct = parse_float(ch_roles.get(role_norm, 0)) / ch_total
                if this_role_pct >= 0.30:
                    ch_role_match = True
                elif this_role_pct < 0.10 and ch_total >= 5:
                    ch_role_match = False
        seen[cname] = champion_comfort(g, wr, kda,
                                       role_match=ch_role_match, form=form,
                                       inhouse=True, results=ch.get("results"))

    # Scout-sheet champion pool (ranked + draft). Per-champ games/wr/kda but
    # pooled across roles, so role-match falls back to player primary. Phase 2:
    # `results` (chronological win/loss) now flows through from the scout
    # sheet (column M) when present, so recency-weighted WR applies to recent
    # ranked form too — not just customs.
    if scout_champs:
        for ch in (scout_champs.get(pname, []) or []):
            cname = ch.get("champ")
            if not cname or cname not in valid:
                continue
            g = parse_float(ch.get("games", 0))
            if g < 3:
                continue
            score = _SCOUT_CHAMPS_WEIGHT * champion_comfort(
                g, parse_wr(ch.get("wr", "50%")),
                parse_float(ch.get("kda"), 1.5),
                role_match=role_match, form=form,
                inhouse=False, results=ch.get("results"),
                recency_half_life=24.0, recency_weight=0.55)
            # Only add if it beats whatever we already have (customs wins ties).
            if score > seen.get(cname, 0.0):
                seen[cname] = score

    # Top champs (ranked-tier; no per-champ stats — use Bayesian-shrunk player WR)
    pwr  = parse_wr(p.get("winrate", p.get("wr", 50.0)))
    pg   = parse_float(p.get("games", 20))
    for cname in (p.get("top_champs") or [])[:8]:
        if not cname or cname in seen or cname not in valid:
            continue
        # Assume ~half the player's ranked games on this champ proportionally.
        # Ranked mastery is a weaker signal than demonstrated customs play, so
        # it is demoted — it can never out-rank a real inhouse comfort score.
        c_games = max(5.0, pg / 4.0)
        seen[cname] = 0.75 * champion_comfort(c_games, pwr, 2.0,
                                              role_match=role_match,
                                              form=form, inhouse=False)

    # Champion priors fallback (only if seen is empty) — weakest signal.
    if not seen:
        for cname, prior_wr in CHAMP_PRIORS.items():
            if cname in valid:
                seen[cname] = 0.50 * champion_comfort(8.0, prior_wr * 100, 2.0,
                                                      role_match=role_match,
                                                      form=form)
        # Plus a couple of safe meta picks for the role
        for cname in sorted(valid):
            if cname not in seen and len(seen) < 6:
                seen[cname] = 0.20

    # Phase 2: off-role decay. A TOP main slotted JGL with 4 lifetime games
    # there shouldn't have their tiny pool ranked alongside a JGL main's deep
    # pool. Scales all candidate comforts down for off-role assignments;
    # severity 0 leaves scores untouched, severity 1 cuts by 40%.
    sev = off_role_severity(p, role, inhouse_champs, primary_roles, scout_champs)
    if sev > 0.0:
        decay = max(0.0, 1.0 - _OFF_ROLE_DECAY * sev)
        if decay < 1.0:
            seen = {c: s * decay for c, s in seen.items()}

    ranked = sorted(seen.items(), key=lambda kv: -kv[1])
    return ranked[:max_candidates]


def beam_search_comp(
    players: Sequence[Dict[str, Any]],
    inhouse_champs: Dict[str, List[Dict]],
    primary_roles: Dict[str, str],
    arch_name: str,
    enemy_picks: Sequence[str] = (),
    beam_width: int = 16,
    max_candidates: int = 6,
    scout_champs: Optional[Dict[str, List[Dict]]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Find the best 5-champion assignment for an archetype via beam search.

    Each beam state is (champs_so_far, comforts_so_far, used_set).
    At each player step, expand each beam state with that player's top candidates,
    score the partial team optimistically, and keep the top `beam_width`.
    """
    if not players:
        return None

    candidates_per_player = [
        _player_candidates(p, inhouse_champs, primary_roles, max_candidates,
                           scout_champs=scout_champs)
        for p in players
    ]

    # Initial beam: empty assignment
    beams: List[Tuple[List[str], List[float], Set[str]]] = [([], [], set())]

    for cands in candidates_per_player:
        next_beams: List[Tuple[List[str], List[float], Set[str], float]] = []
        if not cands:
            # No candidates: pad with placeholder
            for champs, comforts, used in beams:
                next_beams.append((champs + ["?"], comforts + [0.0], used, 0.0))
        else:
            for champs, comforts, used in beams:
                added_any = False
                for cname, comfort in cands:
                    if cname in used:
                        continue
                    new_champs   = champs + [cname]
                    new_comforts = comforts + [comfort]
                    new_used     = used | {cname}
                    # Optimistic partial score (just identity + comfort so far)
                    partial = sum(new_comforts) / max(len(new_comforts), 1)
                    if new_champs:
                        partial = partial * 0.5 + _archetype_vector_score(new_champs, arch_name) * 0.5
                    next_beams.append((new_champs, new_comforts, new_used, partial))
                    added_any = True
                    if len(next_beams) > beam_width * max_candidates:
                        break
                if not added_any:
                    next_beams.append((champs + ["?"], comforts + [0.0], used, 0.0))
        # Keep top `beam_width` partial states
        next_beams.sort(key=lambda t: -t[3])
        beams = [(c, k, u) for (c, k, u, _) in next_beams[:beam_width]]

    # Score each final beam fully and pick the best
    best: Optional[Dict[str, Any]] = None
    for champs, comforts, _used in beams:
        s = score_team(champs, comforts, arch_name, enemy_picks=enemy_picks)
        if (best is None) or (s["total"] > best["score"]["total"]):
            best = {
                "champs": champs,
                "comforts": comforts,
                "score": s,
            }
    return best


# ============================================================================
# Public: recommend_comps  → list of archetype recommendations with picks
# ============================================================================

def recommend_comps(
    players: Sequence[Dict[str, Any]],
    inhouse_champs: Optional[Dict[str, List[Dict]]] = None,
    primary_roles: Optional[Dict[str, str]] = None,
    enemy_picks: Sequence[str] = (),
    n_results: int = 5,
    beam_width: int = 16,
    scout_champs: Optional[Dict[str, List[Dict]]] = None,
) -> List[Dict[str, Any]]:
    """
    Returns ranked archetype recommendations. Each entry has:
      archetype, label, viability, synergy (0..5 dot count), combined,
      picks: [{champion, fit_score}], win_condition, spike, score_breakdown

    `scout_champs` is the scout-sheet FULL CHAMPION POOL per player
    (`{name: [{champ, games, wr, kda, ...}, ...]}`) — ranked + draft data
    used as a secondary comfort source after customs.
    """
    inhouse_champs = inhouse_champs or {}
    primary_roles  = primary_roles  or {}
    scout_champs   = scout_champs   or {}

    results: List[Dict[str, Any]] = []
    for arch_name, arch_data in ARCHETYPES.items():
        beam = beam_search_comp(players, inhouse_champs, primary_roles, arch_name,
                                enemy_picks=enemy_picks, beam_width=beam_width,
                                scout_champs=scout_champs)
        if not beam:
            continue
        champs   = beam["champs"]
        comforts = beam["comforts"]
        s        = beam["score"]

        # Viability buckets — anchored to total score. Phase 2: apply the
        # archetype's `auto_pref` multiplier so meta-favored compositions
        # (currently Teamfight ×1.05) tilt slightly upward when all else is
        # roughly equal. Manual archetype selection isn't affected — only
        # the auto-recommendation order is.
        raw_total = s["total"]
        pref = float(arch_data.get("auto_pref", 1.0))
        total = min(1.0, raw_total * pref)
        if   total >= 0.62: viab = "STRONG"
        elif total >= 0.48: viab = "VIABLE"
        elif total >= 0.32: viab = "WEAK"
        else:               viab = "NOT RECOMMENDED"

        picks = []
        for c, k in zip(champs, comforts):
            picks.append({
                "champion": c if c else "?",
                "fit_score": round(k, 2),
            })

        synergy_dots = max(1, min(5, int(round(total * 5))))

        results.append({
            "archetype":   arch_name,
            "label":       arch_data["label"],
            "viability":   viab,
            "synergy":     synergy_dots,
            "combined":    round(total * 100, 1),
            "picks":       picks,
            "win_condition": arch_data.get("win_condition", ""),
            "spike":       arch_data.get("spike", ""),
            "game_plan":   arch_data.get("game_plan", ""),
            "score_breakdown": {
                "identity":  round(s["identity"], 2),
                "synergy":   round(s["synergy"], 2),
                "damage":    round(s["damage"],   2),
                "counter":   round(s["counter"],  2),
                "comfort":   round(s["comfort"],  2),
                "coherence": round(s["coherence"],2),
                "ap_ratio":  round(s["ap_ratio"], 2),
            },
        })

    # Filter obvious junk
    results = [r for r in results if r["viability"] != "NOT RECOMMENDED" or len(results) <= 2]
    results.sort(key=lambda x: -x["combined"])
    return results[:n_results]


# ============================================================================
# Public: recommend_bans (counter-coverage-aware)
# ============================================================================

def recommend_bans(
    opposing_players: Sequence[Dict[str, Any]],
    inhouse_champs: Optional[Dict[str, List[Dict]]] = None,
    own_picks: Sequence[str] = (),
    primary_roles: Optional[Dict[str, str]] = None,
    n_bans: int = 5,
    scout_champs: Optional[Dict[str, List[Dict]]] = None,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Bans use Bayesian-shrunk threat, role-context, and counter-coverage.

    threat = shrunk_wr × log(games+1) × kda_factor × rank_weight × role_factor
    coverage_discount = up to -40% if your team strongly counters this champ

    `scout_champs` (optional) augments customs data with the scout-sheet
    FULL CHAMPION POOL (ranked + draft) so threats that show up in ranked
    but not customs still get surfaced.
    """
    inhouse_champs = inhouse_champs or {}
    primary_roles  = primary_roles  or {}
    scout_champs   = scout_champs   or {}

    seen: Dict[str, Dict[str, Any]] = {}
    for p in opposing_players:
        # v3.0.4: skip enemy players who have already locked a pick. Their
        # remaining champion pool is irrelevant — they can't make another
        # pick this draft, so banning to deny them is wasted. Filtering
        # at the player level (vs. just at the candidate-champion level
        # via `used_champs`) also avoids surfacing OTHER champions from
        # the locked player's pool that aren't real threats.
        if p.get("locked_champ"):
            continue
        pname = p.get("name", "")
        rank_weight = max(0.5, min(2.0, parse_float(p.get("final_score",
                                                           p.get("score", 50))) / 50.0))
        form = p.get("form")
        primary = primary_roles.get(pname)
        prole = p.get("role", "")
        # Only consider champions valid for the player's ASSIGNED role this draft.
        # Stops e.g. recommending Yasuo ban for a player slotted SUP just because
        # they have ranked Yasuo games from mid.
        role_pool = ROLE_VALID.get(prole, set())

        ih_list = inhouse_champs.get(pname, []) or []
        any_data = False
        for ch in ih_list:
            cname = ch.get("champ")
            if not cname:
                continue
            if role_pool and cname not in role_pool:
                continue
            g = parse_float(ch.get("games", 0))
            if g < 3:
                continue
            any_data = True
            wr   = parse_wr(ch.get("wr", "50%"))
            kda  = parse_float(ch.get("kda"), 1.5)
            wr_post = shrink_wr_from_pct(wr, g)
            kda_factor = min(kda / 2.5, 1.6)
            # Sample-size weight (sqrt-like but log-based, more conservative on big N)
            ssz = math.log(1.0 + g) / math.log(11.0)   # 1.0 at 10 games
            ssz = min(ssz * 1.2, 1.4)
            role_factor = 1.0
            if primary and primary == ROLE_NORM.get(prole, prole):
                role_factor = 1.15
            threat = wr_post * ssz * kda_factor * rank_weight * role_factor
            threat *= form_multiplier(form)
            if cname not in seen or threat > seen[cname]["threat_raw"]:
                seen[cname] = {
                    "champion": cname, "player": pname,
                    "games": int(g), "wr": round(wr, 1),
                    "kda": round(kda, 2),
                    "threat_raw": threat,
                    "phase_reason": "",
                }

        # Scout-sheet champion pool (ranked + draft). Real per-champ games/wr/kda
        # — much stronger threat signal than the name-only top_champs fallback.
        # Discount slightly vs customs since pool is across-role and lower stakes.
        # Phase 2: when the scout sheet provides per-game `results` chronology
        # (column M, last ~100 ranked+draft games), blend recency-weighted WR
        # into the threat so a hot streak on a champion bumps its threat above
        # a lifetime-aggregate equivalent.
        for ch in (scout_champs.get(pname, []) or []):
            cname = ch.get("champ")
            if not cname:
                continue
            if role_pool and cname not in role_pool:
                continue
            g = parse_float(ch.get("games", 0))
            if g < 3:
                continue
            wr   = parse_wr(ch.get("wr", "50%"))
            kda  = parse_float(ch.get("kda"), 1.5)
            wr_post = shrink_wr_from_pct(wr, g)
            # Ranked recency: half-life 24 games (vs 18 for customs) reflects
            # ranked being a lower-stakes signal that decays slower.
            results = ch.get("results")
            if results:
                rec_wr, eff_n = recency_weighted_wr(results, half_life=24.0)
                if rec_wr is not None and eff_n > 0:
                    rec_post = shrink_wr(rec_wr * eff_n, eff_n)
                    wr_post = 0.55 * rec_post + 0.45 * wr_post
            kda_factor = min(kda / 2.5, 1.6)
            ssz = math.log(1.0 + g) / math.log(11.0)
            ssz = min(ssz * 1.2, 1.4)
            role_factor = 1.0
            if primary and primary == ROLE_NORM.get(prole, prole):
                role_factor = 1.15
            # 0.85 multiplier mirrors _SCOUT_CHAMPS_WEIGHT — customs threat wins
            # on the same champion, but ranked-only threats still register.
            threat = wr_post * ssz * kda_factor * rank_weight * role_factor * _SCOUT_CHAMPS_WEIGHT
            threat *= form_multiplier(form)
            any_data = True
            if cname not in seen or threat > seen[cname]["threat_raw"]:
                seen[cname] = {
                    "champion": cname, "player": pname,
                    "games": int(g), "wr": round(wr, 1),
                    "kda": round(kda, 2),
                    "threat_raw": threat,
                    "phase_reason": "",
                }

        # Top champs fallback (player has no inhouse or scout-sheet history)
        if not any_data:
            for champ in (p.get("top_champs") or [])[:5]:
                if not champ or champ in seen:
                    continue
                # Same role-pool filter — don't recommend ranked-champs that
                # aren't a fit for the player's assigned role this draft.
                if role_pool and champ not in role_pool:
                    continue
                seen[champ] = {
                    "champion": champ, "player": pname,
                    "games": 0, "wr": 50.0, "kda": 2.0,
                    "threat_raw": 0.20 * rank_weight,
                    "phase_reason": "",
                }

    # Apply coverage discount (your picks counter this champ → safer to leave open)
    own_picks = [c for c in (own_picks or []) if c and c != "?"]
    for cname, info in seen.items():
        coverage = team_counter_coverage(own_picks, cname) if own_picks else 0.0
        # Up to 40% threat reduction if perfectly countered
        info["threat"] = info["threat_raw"] * (1.0 - 0.40 * min(coverage * 2.0, 1.0))
        info["coverage"] = round(coverage, 2)

    final = sorted(seen.values(), key=lambda x: -x["threat"])

    # Add phase / priority labels
    for i, b in enumerate(final[:n_bans]):
        if   i < 2: b["priority"] = "HIGH"
        elif i < 4: b["priority"] = "MEDIUM"
        else:       b["priority"] = "LOW"

        cov = b.get("coverage", 0.0)
        g = b.get("games", 0)
        wr = b.get("wr", 50.0)
        if cov >= 0.30:
            b["phase_reason"] = f"Threat exists but {b.get('player','team')} pick counters it"
        elif g >= 8 and wr >= 65:
            b["phase_reason"] = f"Must ban — {int(wr)}% WR over {g} games"
        elif i < 3 and g >= 3:
            b["phase_reason"] = f"High threat — {int(wr)}% WR / {b.get('kda',0):.1f} KDA"
        elif g >= 3:
            b["phase_reason"] = f"Counter-pick threat — {int(wr)}% WR"
        else:
            b["phase_reason"] = "Comfort pick — monitor this player"

        b["threat"] = round(b["threat"], 2)
        b.pop("threat_raw", None)

    top = final[:n_bans]
    return [b["champion"] for b in top], top


# ============================================================================
# Enemy weakness vector (for late-pick draft assist; also flavours comp scores)
# ============================================================================

def enemy_weakness_vector(enemy_champs: Sequence[str]) -> Dict[str, float]:
    """
    Given locked enemy picks, return a 0..1 weight per exploit axis:
      kite_them      — they have no mobility, vulnerable to kiting comps
      burst_them     — they're squishy, vulnerable to assassins
      tank_bust_them — they stack tanks, vulnerable to %hp damage
      poke_them      — they have no engage, vulnerable to poke siege
      lockdown_carry — they have a fed hypercarry to delete
      pop_engage     — they have hard engage, you need disengage
    """
    out = {k: 0.0 for k in ("kite_them","burst_them","tank_bust_them",
                            "poke_them","lockdown_carry","pop_engage")}
    if not enemy_champs:
        return out
    immobile = sum(1 for c in enemy_champs if c in SUBCLASSES["immobile"])
    squishy  = sum(1 for c in enemy_champs if c in SUBCLASSES["squishy"])
    frontln  = sum(1 for c in enemy_champs if c in SUBCLASSES["frontline"])
    engage   = sum(1 for c in enemy_champs if c in SUBCLASSES["engage"])
    hcarry   = sum(1 for c in enemy_champs if c in SUBCLASSES["hypercarry"])

    out["kite_them"]      = min(1.0, immobile / 3.0)
    out["burst_them"]     = min(1.0, squishy  / 3.0)
    out["tank_bust_them"] = min(1.0, max(0.0, (frontln - 1) / 2.0))
    out["poke_them"]      = 1.0 if engage == 0 else max(0.0, 1.0 - engage * 0.4)
    out["lockdown_carry"] = min(1.0, hcarry / 1.0)
    out["pop_engage"]     = min(1.0, engage / 2.0)
    return out


# ============================================================================
# Matchup logic (per-lane 1v1 with champion + form awareness)
# ============================================================================

# Lane matchup ratings: lane_matchups[(your_champ, enemy_champ)] = blue_adv ± 8
LANE_MATCHUPS: Dict[Tuple[str, str], float] = {
    # Top lane
    ("Darius","Yasuo"): 6, ("Darius","Kennen"): -5, ("Darius","Quinn"): -7,
    ("Darius","Gnar"): -6, ("Darius","Vladimir"): -5, ("Darius","Renekton"): 4,
    ("Garen","Vladimir"): -6, ("Garen","Akali"): 5, ("Garen","Teemo"): -7,
    ("Fiora","Sion"): 7, ("Fiora","Cho'Gath"): 7, ("Fiora","Malphite"): -3,
    ("Fiora","Jax"): -4, ("Fiora","Camille"): -4,
    ("Jax","Teemo"): 6, ("Jax","Quinn"): 5, ("Jax","Gnar"): 5, ("Jax","Vayne"): 5,
    ("Jax","Renekton"): -3, ("Jax","Pantheon"): -3,
    ("Renekton","Yasuo"): 5, ("Renekton","Vladimir"): 5, ("Renekton","Ryze"): 5,
    ("Renekton","Fiora"): 3, ("Renekton","Gnar"): -4,
    ("Riven","Yasuo"): 5, ("Riven","Garen"): 4, ("Riven","Fiora"): -3,
    ("Camille","Fiora"): 4, ("Camille","Sett"): 5,
    ("Sett","Yasuo"): 5, ("Sett","Riven"): 4, ("Sett","Fiora"): 3,
    ("Mordekaiser","Tryndamere"): 7, ("Mordekaiser","Fiora"): 6, ("Mordekaiser","Vladimir"): 5,
    ("Quinn","Darius"): 7, ("Quinn","Sett"): 6, ("Quinn","Garen"): 6, ("Quinn","Aatrox"): 5,
    ("Teemo","Darius"): 7, ("Teemo","Garen"): 6, ("Teemo","Sett"): 4,
    ("Gnar","Darius"): 6, ("Gnar","Aatrox"): 5, ("Gnar","Sett"): 5,
    # Mid lane
    ("Zed","Karthus"): 6, ("Zed","Veigar"): 5, ("Zed","Annie"): -4,
    ("Zed","Lissandra"): -5, ("Zed","Malzahar"): -7,
    ("Talon","Karthus"): 5, ("Talon","Lux"): 5, ("Talon","Xerath"): 5,
    ("Yasuo","Annie"): -5, ("Yasuo","Malzahar"): -7, ("Yasuo","Lissandra"): -4,
    ("Yasuo","Pantheon"): -5, ("Yasuo","Renekton"): -4,
    ("Malzahar","Yasuo"): 7, ("Malzahar","Kassadin"): 6, ("Malzahar","Yone"): 6,
    ("Kassadin","Xerath"): 7, ("Kassadin","Vel'Koz"): 6, ("Kassadin","Lux"): 6,
    ("Kassadin","Annie"): 4, ("Kassadin","Pantheon"): -5,
    ("Galio","Zed"): 5, ("Galio","Akali"): 5, ("Galio","Yasuo"): 4,
    ("Galio","Xerath"): 6, ("Galio","Vel'Koz"): 5,
    ("LeBlanc","Annie"): 4, ("LeBlanc","Veigar"): 4, ("LeBlanc","Vladimir"): -4,
    ("Akali","Annie"): -3, ("Akali","Galio"): -4, ("Akali","Lissandra"): -3,
    ("Annie","Yasuo"): 5, ("Annie","Kassadin"): 5,
    ("Veigar","Zed"): -5, ("Veigar","Talon"): -4, ("Veigar","Yasuo"): -3,
    ("Anivia","Talon"): -3, ("Anivia","Zed"): -3, ("Anivia","Sejuani"): 3,
    ("Lissandra","Zed"): 6, ("Lissandra","Yasuo"): 4, ("Lissandra","Kassadin"): 5,
    # Bot lane
    ("Caitlyn","Vayne"): 5, ("Caitlyn","Kalista"): 4, ("Caitlyn","Senna"): 3,
    ("Draven","Vayne"): 5, ("Draven","Kog'Maw"): 5, ("Draven","Aphelios"): 4,
    ("Vayne","Caitlyn"): -5, ("Vayne","Draven"): -5, ("Vayne","Kalista"): -3,
    ("Lucian","Kog'Maw"): 5, ("Lucian","Jinx"): 4, ("Lucian","Vayne"): 4,
    ("Jinx","Lucian"): -4, ("Jinx","Draven"): -3, ("Jinx","Vayne"): 3,
    ("Kog'Maw","Caitlyn"): -3, ("Kog'Maw","Draven"): -5, ("Kog'Maw","Vayne"): 3,
    # Support
    ("Pyke","Soraka"): 4, ("Pyke","Yuumi"): 5, ("Pyke","Sona"): 4, ("Pyke","Nami"): 3,
    ("Leona","Lulu"): 4, ("Leona","Yuumi"): 4, ("Leona","Karma"): 3,
    ("Janna","Leona"): 4, ("Janna","Pyke"): 3, ("Janna","Nautilus"): 3,
    ("Thresh","Yuumi"): 4, ("Thresh","Soraka"): 3,
    ("Lulu","Leona"): -4, ("Lulu","Pyke"): -4,
}


def compute_matchups(
    blue: Sequence[Dict[str, Any]],
    red: Sequence[Dict[str, Any]],
    primary_roles: Optional[Dict[str, str]] = None,
    blue_picks: Sequence[str] = (),
    red_picks: Sequence[str] = (),
) -> List[Tuple[str, str, str, float, str]]:
    """
    Per-lane matchup. Player-score diff + role-main bonus + champion matchup +
    form modifier. Returns list of (role, blue_name, red_name, blue_win_pct, note).
    """
    primary_roles = primary_roles or {}
    rows: List[Tuple[str, str, str, float, str]] = []
    for i, (bp, rp) in enumerate(zip(blue, red)):
        role = ROLES_UPPER[i]
        bs   = parse_float(bp.get("final_score", bp.get("score", 50)), 50)
        rs   = parse_float(rp.get("final_score", rp.get("score", 50)), 50)
        diff = bs - rs

        blue_adv = 50.0 + diff * 0.5

        bn = bp.get("name", "?")
        rn = rp.get("name", "?")

        b_main = primary_roles.get(bn)
        r_main = primary_roles.get(rn)
        role_norm = ROLE_NORM.get(role, role)
        if b_main == role_norm: blue_adv += 4.0
        if r_main == role_norm: blue_adv -= 4.0

        # Champion matchup
        bc = blue_picks[i] if i < len(blue_picks) and blue_picks[i] not in (None, "?") else None
        rc = red_picks[i]  if i < len(red_picks)  and red_picks[i]  not in (None, "?") else None
        cm = 0.0
        if bc and rc:
            cm += LANE_MATCHUPS.get((bc, rc), 0.0)
            cm -= LANE_MATCHUPS.get((rc, bc), 0.0)
        blue_adv += cm

        # Form
        bf = form_multiplier(bp.get("form")); rf = form_multiplier(rp.get("form"))
        # Hot form adds ~3%, cold form subtracts ~3%
        blue_adv += (bf - 1.0) * 30.0 - (rf - 1.0) * 30.0

        blue_adv = max(20.0, min(80.0, blue_adv))

        # Note generation
        parts = []
        if   abs(diff) >= 20: parts.append(f"{'Blue' if diff>0 else 'Red'} +{abs(diff):.0f} score")
        elif abs(diff) >= 8:  parts.append("Close skill match")
        else:                 parts.append("Even matchup")
        if   b_main == role_norm:        parts.append(f"{bn} on main")
        elif b_main and b_main != role_norm: parts.append(f"{bn} off-role ({b_main})")
        if   r_main == role_norm:        parts.append(f"{rn} on main")
        elif r_main and r_main != role_norm: parts.append(f"{rn} off-role ({r_main})")
        if bc and rc and abs(cm) >= 3:
            parts.append(f"{'Blue' if cm>0 else 'Red'} champ edge")
        if bp.get("form","").upper() == "HOT": parts.append(f"{bn} HOT")
        if rp.get("form","").upper() == "HOT": parts.append(f"{rn} HOT")

        note = "  ·  ".join(parts[:3])
        rows.append((role, bn, rn, round(blue_adv, 1), note))
    return rows


# ============================================================================
# Random-player helper: fill gap based on team identity
# ============================================================================

def random_player_gap_fill(
    role: str,
    team_so_far: Sequence[str],
    arch_name: str,
    used: Set[str],
) -> Optional[Tuple[str, float]]:
    """
    Pick the champion that best fills the team's biggest gap toward the archetype's
    target vector. Returns (champ, fit_score) or None.
    """
    valid = ROLE_VALID.get(role, set())
    if not valid:
        return None
    target = ARCHETYPES[arch_name]["target"]
    current = _team_vector(team_so_far)
    # Identify biggest deficit
    deficits = {ax: max(0.0, target.get(ax, 0.0) - current.get(ax, 0.0)) for ax in _AXES}
    if all(v == 0 for v in deficits.values()):
        # No gap — just pick any valid champ that contributes to scaling
        deficits["scaling"] = 0.5

    best, best_score = None, -1.0
    for cname in valid:
        if cname in used:
            continue
        cv = _champ_vector(cname)
        score = sum(deficits[a] * cv[a] for a in _AXES)
        if score > best_score:
            best, best_score = cname, score
    if best is None:
        return None
    return best, max(0.20, min(0.50, best_score / 2.0 + 0.20))
