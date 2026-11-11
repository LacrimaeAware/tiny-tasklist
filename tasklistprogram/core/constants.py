# constants.py
PRIORITY_ORDER = {"U": 5, "H": 4, "M": 3, "L": 2, "D": 1, "X": 0}  # X = Misc (blue), U = Ultra
PRIO_ICON = {"U": "🚨 U", "H": "🔴 H", "M": "🟠 M", "L": "🟡 L", "D": "🟢 D", "X": "🔵 Mi"}

def normalize_priority(code) -> str:
    """Map a user-facing priority ('Misc', 'm', etc.) to its canonical letter code."""
    if isinstance(code, str) and code.strip().lower() == "misc":
        return "X"
    return (code or "M").upper()

def priority_rank(code) -> int:
    """Rank a priority for comparisons (higher = more important)."""
    return PRIORITY_ORDER.get(normalize_priority(code), 0)
