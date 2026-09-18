import re
from datetime import datetime, date, timedelta
from typing import Optional

WEEKDAY_MAP = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "wed": 2,
    "weds": 2,
    "wednesday": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}

DAYPART_MAP = {
    "morning": (8, 0),
    "noon": (12, 0),
    "afternoon": (16, 0),
    "evening": (20, 0),
}

# Relative day words -> offset from today (in days).
RELDAY_MAP = {
    "today": 0,
    "tonight": 0,
    "tomorrow": 1,
    "tmrw": 1,
    "tom": 1,
    "yesterday": -1,
}

# Month names/abbreviations -> month number.
MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

def _end_of_day(dt: datetime) -> datetime:
    return dt.replace(hour=23, minute=59, second=0, microsecond=0)

def _parse_time_token(tail: str):
    """Parse 'HH:MM' or 'HHMM' -> (hh, mm), else None. Returns None on out-of-range."""
    m = re.match(r'^(\d{1,2}):(\d{2})$', tail) or re.match(r'^(\d{3,4})$', tail)
    if not m:
        return None
    if ":" in tail:
        hh, mm = int(m.group(1)), int(m.group(2))
    else:
        raw = m.group(1)
        if len(raw) == 3:
            raw = "0" + raw
        hh, mm = int(raw[:2]), int(raw[2:])
    if hh > 23 or mm > 59:
        return None
    return hh, mm

def _combine_with_tail(target_date: date, tail_tokens):
    """Combine a resolved date with an optional trailing time/daypart/'midnight'.

    Returns a datetime (timed), a ('dateonly', datetime) tuple (no time given),
    or None when a tail was supplied but not understood.
    """
    base = datetime.combine(target_date, datetime.min.time())
    if not tail_tokens:
        return ("dateonly", base)
    tail = " ".join(tail_tokens).strip().lower()
    if tail == "midnight":
        return base.replace(hour=23, minute=59)
    if tail in DAYPART_MAP:
        hh, mm = DAYPART_MAP[tail]
        return base.replace(hour=hh, minute=mm)
    hm = _parse_time_token(tail)
    if hm is not None:
        return base.replace(hour=hm[0], minute=hm[1])
    return None

def _has_time_tokens(tokens):
    for tok in tokens:
        m = re.match(r'^[+-](\d+)([hm])$', tok.lower())
        if m:
            return True
    for tok in tokens:
        if tok.lower() in ('+0m', '+0h'):
            return True
    return False

def parse_due_flexible(s: Optional[str]):
    """Parse flexible due strings.
       Returns:
         - None for empty
         - datetime for precise
         - ('dateonly', datetime) for date-only precision

    Accepts:
      - 'YYYY-MM-DD' [ 'HHMM' | 'HH:MM' | 'midnight' ]
      - 'MM/DD' [ 'HHMM' | 'HH:MM' | 'midnight' ]
      - 'midnight'  (today 23:59)
      - relative tokens: '+2d +5h -3h +1w' (optional 'midnight' to force 23:59)
    """
    if not s or not s.strip():
        return None
    s = s.strip()

    # Plain 'midnight' -> today 23:59
    if s.lower() == "midnight":
        now = datetime.now()
        return now.replace(hour=23, minute=59, second=0, microsecond=0)

    # Plain dayparts -> today at a sensible time
    if s.lower() in DAYPART_MAP:
        now = datetime.now()
        hh, mm = DAYPART_MAP[s.lower()]
        return now.replace(hour=hh, minute=mm, second=0, microsecond=0)

    tokens = s.split()

    # Relative day words ('today', 'tomorrow', 'yesterday') with optional time/daypart
    if tokens and tokens[0].lower() in RELDAY_MAP:
        target_date = date.today() + timedelta(days=RELDAY_MAP[tokens[0].lower()])
        res = _combine_with_tail(target_date, tokens[1:])
        if res is not None:
            return res

    # Weekday names with optional time or daypart
    if tokens:
        day_key = tokens[0].lower()
        if day_key in WEEKDAY_MAP:
            today = date.today()
            target = WEEKDAY_MAP[day_key]
            days_ahead = (target - today.weekday()) % 7
            target_date = today + timedelta(days=days_ahead)
            res = _combine_with_tail(target_date, tokens[1:])
            if res is not None:
                return res

    # Month-name dates ('Sept 29', 'September 29 2026', 'sep 29 14:00')
    if len(tokens) >= 2:
        month_key = re.sub(r'\.$', '', tokens[0].lower())
        if month_key in MONTH_MAP and re.match(r'^\d{1,2}$', tokens[1]):
            mon, day = MONTH_MAP[month_key], int(tokens[1])
            rest = tokens[2:]
            year = datetime.now().year
            if rest and re.match(r'^\d{4}$', rest[0]):
                year = int(rest[0])
                rest = rest[1:]
            try:
                target_date = date(year, mon, day)
            except ValueError:
                return None
            res = _combine_with_tail(target_date, rest)
            if res is not None:
                return res

    # Absolute YYYY-MM-DD with optional time or 'midnight'
    m = re.match(r'^(\d{4}-\d{2}-\d{2})(?:\s+(\d{2})(?::?(\d{2}))|\s+midnight)?$', s, re.IGNORECASE)
    if m:
        d = datetime.strptime(m.group(1), "%Y-%m-%d")
        if m.group(2):
            hh = int(m.group(2)); mm = int(m.group(3) or 0)
            return d.replace(hour=hh, minute=mm)
        if s.lower().endswith("midnight"):
            return d.replace(hour=23, minute=59)
        return ('dateonly', d)

    # Absolute MM/DD with optional time or 'midnight'
    m2 = re.match(r'^(\d{1,2})/(\d{1,2})(?:\s+(\d{2})(?::?(\d{2}))?|\s+midnight)?$', s, re.IGNORECASE)
    if m2:
        y = datetime.now().year
        mon, day = int(m2.group(1)), int(m2.group(2))
        try:
            d = datetime(year=y, month=mon, day=day)
        except ValueError:
            return None
        if m2.group(3):
            hh = int(m2.group(3)); mm = int(m2.group(4) or 0)
            return d.replace(hour=hh, minute=mm)
        if s.lower().endswith("midnight"):
            return d.replace(hour=23, minute=59)
        return ('dateonly', d)

    # Relative tokens with optional 'midnight'
    tokens = s.split()
    midnight_flag = any(tok.lower() == 'midnight' for tok in tokens)
    tokens = [t for t in tokens if t.lower() != 'midnight']

    ok = True
    for tok in tokens:
        if re.match(r'^[+-]\d+[dhmw]$', tok.lower()) or tok.lower() in ('+0m', '+0h'):
            continue
        ok = False; break
    if not ok or not tokens:
        return None

    now = datetime.now()
    total = timedelta()
    for tok in tokens:
        tl = tok.lower()
        if tl in ('+0m', '+0h'):
            continue
        m = re.match(r'^([+-])(\d+)([dhmw])$', tl)
        sign = 1 if m.group(1) == '+' else -1
        amt = int(m.group(2)) * sign
        unit = m.group(3)
        if unit == 'm': total += timedelta(minutes=amt)
        elif unit == 'h': total += timedelta(hours=amt)
        elif unit == 'd': total += timedelta(days=amt)
        elif unit == 'w': total += timedelta(weeks=amt)

    result_dt = now + total
    if _has_time_tokens(tokens):
        return result_dt
    else:
        if midnight_flag:
            return result_dt.replace(hour=23, minute=59, second=0, microsecond=0)
        d = result_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        return ('dateonly', d)

def parse_due_entry(s: Optional[str]):
    """Canonical parser for user-typed due values.

    Accepts a bare time ('HH:MM' or 'HHMM' -> today at that time) in addition to
    everything ``parse_due_flexible`` handles. Use this for every text entry point
    (Add box, Edit dialog, Set Due, import) so they all behave the same.

    Returns None, a datetime, or a ('dateonly', datetime) tuple.
    """
    if not s or not s.strip():
        return None
    ts = s.strip()
    if re.match(r'^(\d{1,2}):(\d{2})$', ts) or re.match(r'^(\d{3,4})$', ts):
        hm = _parse_time_token(ts)
        if hm is None:
            return None
        return datetime.now().replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
    return parse_due_flexible(ts)

def fmt_due_for_store(parsed):
    if parsed is None:
        return ""
    if isinstance(parsed, tuple) and parsed and parsed[0] == 'dateonly':
        dt = parsed[1]
        return dt.strftime("%Y-%m-%d")
    if isinstance(parsed, datetime):
        return parsed.strftime("%Y-%m-%d %H:%M")
    return ""

def parse_stored_due(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        if len(s) == 10:
            d = datetime.strptime(s, "%Y-%m-%d")
            return d  # date-only, 00:00
        return datetime.strptime(s, "%Y-%m-%d %H:%M")
    except Exception:
        return None

def month_add(base: date) -> date:
    m = base.month + 1
    y = base.year + (m - 1)//12
    m = ((m - 1)%12) + 1
    days = [31,29 if y%4==0 and (y%100!=0 or y%400==0) else 28,31,30,31,30,31,31,30,31,30,31][m-1]
    day = min(base.day, days)
    return date(y, m, day)

def next_due(d: Optional[date], repeat: str) -> Optional[date]:
    if repeat in ("", "none", None):
        return d
    base = d or date.today()
    if repeat == "daily":
        return base + timedelta(days=1)
    if repeat == "weekdays":
        nd = base + timedelta(days=1)
        while nd.weekday() >= 5:
            nd += timedelta(days=1)
        return nd
    interval_days = repeat_interval_days(repeat)
    if interval_days is not None:
        return base + timedelta(days=interval_days)
    if repeat == "monthly":
        return month_add(base)
    return base


def repeat_interval_days(repeat: Optional[str]) -> Optional[int]:
    """Return day interval for fixed-day repeat modes, else None."""
    rep = (repeat or "").strip().lower()
    if rep == "weekly":
        return 7
    if rep in ("bi-weekly", "biweekly"):
        return 14
    if rep.startswith("custom:"):
        raw = rep.split(":", 1)[1].strip()
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
    return None

# Kept as an alias for backwards-compatible imports; see month_add above.
def add_months_dateonly(d: date) -> date:
    return month_add(d)
