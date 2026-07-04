"""Resolve natural-language due-date phrases relative to a reference time.

Understands: today, tonight, tomorrow, day after tomorrow, EOD, COB, EOW,
end of month, next week, weekday names ("by Friday", "next Tuesday"),
"in N days/weeks", and explicit dates (5/7, 05-07-2026, "July 9", "9th July").
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_WD_ABBR = {w[:3]: i for i, w in enumerate(WEEKDAYS)}

MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]
_MONTH_IDX = {m: i + 1 for i, m in enumerate(MONTHS)}
_MONTH_IDX.update({m[:3]: i + 1 for i, m in enumerate(MONTHS)})

_MONTH_PAT = "|".join(sorted(_MONTH_IDX, key=len, reverse=True))

_PATTERNS: Tuple[Tuple[re.Pattern, str], ...] = tuple(
    (re.compile(p, re.IGNORECASE), kind)
    for p, kind in [
        (r"\bday after tomorrow\b|\bpasado ma[ñn]ana\b|\bapr[eè]s-demain\b|\bparso\b", "day_after_tomorrow"),
        (r"\btomorrow\b|\btmrw\b|\btmr\b|\bma[ñn]ana\b|\bdemain\b|\bkal\b", "tomorrow"),
        (r"\btoday\b|\btonight\b|\bby eod\b|\beod\b|\bcob\b|\bend of (?:the )?day\b|\bhoy\b|\baujourd'hui\b|\baaj\b", "today"),
        (r"\bby (?:the )?end of (?:the |this )?week\b|\beow\b|\bthis week\b", "eow"),
        (r"\bend of (?:the |this )?month\b|\beom\b", "eom"),
        (r"\bnext week\b", "next_week"),
        (r"\bnext (monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\b", "next_weekday"),
        (r"\b(?:by|on|before|until|till)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\b", "weekday"),
        (r"\bin\s+(\d{1,2})\s+days?\b", "in_days"),
        (r"\bin\s+(\d{1,2})\s+weeks?\b", "in_weeks"),
        (r"\b(?:by|on|before|until|till|due)\s+(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", "numeric"),
        (rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH_PAT})\b", "day_month"),
        (rf"\b({_MONTH_PAT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", "month_day"),
    ]
)


def _weekday_index(token: str) -> int:
    token = token.lower()
    if token in WEEKDAYS:
        return WEEKDAYS.index(token)
    return _WD_ABBR[token[:3]]


def _next_weekday(ref: date, wd: int, strict_next_week: bool = False) -> date:
    days_ahead = (wd - ref.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    result = ref + timedelta(days=days_ahead)
    if strict_next_week and result.isocalendar()[1] == ref.isocalendar()[1]:
        result += timedelta(days=7)
    return result


def find_due_date(text: str, ref: datetime, dayfirst: bool = True) -> Optional[date]:
    """Return the due date implied by *text*, or None."""
    today = ref.date()
    for pattern, kind in _PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        if kind == "today":
            return today
        if kind == "tomorrow":
            return today + timedelta(days=1)
        if kind == "day_after_tomorrow":
            return today + timedelta(days=2)
        if kind == "eow":
            # end of working week: Friday (or today if already Fri-Sun)
            days = (4 - today.weekday()) % 7
            return today + timedelta(days=days)
        if kind == "eom":
            nxt = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
            return nxt - timedelta(days=1)
        if kind == "next_week":
            return today + timedelta(days=(7 - today.weekday()))  # next Monday
        if kind == "next_weekday":
            return _next_weekday(today, _weekday_index(m.group(1)), strict_next_week=True)
        if kind == "weekday":
            return _next_weekday(today, _weekday_index(m.group(1)))
        if kind == "in_days":
            return today + timedelta(days=int(m.group(1)))
        if kind == "in_weeks":
            return today + timedelta(weeks=int(m.group(1)))
        if kind == "numeric":
            a, b = int(m.group(1)), int(m.group(2))
            year = int(m.group(3)) if m.group(3) else today.year
            if year < 100:
                year += 2000
            if a > 12 >= b:
                day, month = a, b
            elif b > 12 >= a:
                day, month = b, a
            elif dayfirst:
                day, month = a, b
            else:
                day, month = b, a
            try:
                d = date(year, month, day)
            except ValueError:
                continue
            if not m.group(3) and d < today:
                d = date(year + 1, month, day)
            return d
        if kind in ("day_month", "month_day"):
            if kind == "day_month":
                day, month = int(m.group(1)), _MONTH_IDX[m.group(2).lower()]
            else:
                month, day = _MONTH_IDX[m.group(1).lower()], int(m.group(2))
            try:
                d = date(today.year, month, day)
            except ValueError:
                continue
            if d < today:
                try:
                    d = date(today.year + 1, month, day)
                except ValueError:
                    continue
            return d
    return None
