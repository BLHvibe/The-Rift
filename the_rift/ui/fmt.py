"""
fmt.py — Phase 0b: shared number / text formatting helpers.

One place for consistent data presentation so every surface formats values the
same way — thousands separators, percentages, signed deltas, compact K/M
abbreviations, safe truncation. Part of the polish standard ("data reads
clean"). All helpers are pure and pass non-numeric input through gracefully.
"""


def commas(n):
    """1234567 -> '1,234,567'. Non-numeric input passes through as str."""
    try:
        return f"{int(round(float(n))):,}"
    except (TypeError, ValueError):
        return str(n)


def compact(n, digits=1):
    """Large number -> short form: 18240 -> '18.2K', 2300000 -> '2.3M'."""
    try:
        v = float(n)
    except (TypeError, ValueError):
        return str(n)
    neg = v < 0
    v = abs(v)
    if v < 1000:
        s = str(int(round(v)))
    elif v < 1_000_000:
        s = f"{v / 1000:.{digits}f}".rstrip("0").rstrip(".") + "K"
    elif v < 1_000_000_000:
        s = f"{v / 1_000_000:.{digits}f}".rstrip("0").rstrip(".") + "M"
    else:
        s = f"{v / 1_000_000_000:.{digits}f}".rstrip("0").rstrip(".") + "B"
    return ("-" + s) if neg else s


def pct(v, digits=0, of=100.0):
    """Format a percentage. pct(53) -> '53%'; pct(0.532, of=1) -> '53%'."""
    try:
        x = float(v) / float(of) * 100.0
    except (TypeError, ValueError, ZeroDivisionError):
        return str(v)
    return f"{x:.{digits}f}%"


def signed(n, digits=0):
    """Signed number with an explicit '+' on positives. signed(3) -> '+3'."""
    try:
        v = float(n)
    except (TypeError, ValueError):
        return str(n)
    if digits == 0:
        return f"{int(round(v)):+d}"
    return f"{v:+.{digits}f}"


def ordinal(n):
    """1 -> '1st', 2 -> '2nd', 11 -> '11th', 23 -> '23rd'."""
    try:
        v = int(n)
    except (TypeError, ValueError):
        return str(n)
    if 10 <= v % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(v % 10, "th")
    return f"{v}{suf}"


def clamp_text(s, max_chars):
    """Truncate with an ellipsis so text never overruns its box."""
    s = str(s)
    if max_chars <= 1 or len(s) <= max_chars:
        return s
    return s[:max_chars - 1].rstrip() + "…"


def kda(k, d, a):
    """KDA ratio: (k + a) / max(d, 1), one decimal. 'Perfect' when d == 0."""
    try:
        k, d, a = float(k), float(d), float(a)
    except (TypeError, ValueError):
        return "—"
    if d <= 0:
        return "Perfect"
    return f"{(k + a) / d:.1f}"


def duration(seconds):
    """Seconds -> 'M:SS' game-clock form. 1875 -> '31:15'."""
    try:
        s = int(seconds)
    except (TypeError, ValueError):
        return str(seconds)
    return f"{s // 60}:{s % 60:02d}"
