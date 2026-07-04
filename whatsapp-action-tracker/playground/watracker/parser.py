"""Parser for WhatsApp exported chat files (.txt).

Handles both common export layouts:

    Android:  31/12/23, 22:15 - Alice: message text
              12/31/23, 10:15 PM - Alice: message text
    iOS:      [31/12/2023, 22:15:42] Alice: message text
              [12/31/23, 10:15:42 PM] Alice: message text

Multi-line messages (continuation lines) are appended to the previous
message.  Lines without a "Sender: " part are treated as system messages
(group notices, encryption banner, "Alice added Bob", ...).

Day/month order is inferred across the whole file: if any date has a first
component > 12 the file is day-first; if any has a second component > 12 it
is month-first.  When the file never disambiguates, day-first is assumed
(override with ``date_order``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

# Invisible marks WhatsApp sprinkles into exports.
_STRIP_CHARS = "‎‏‪‬﻿"
# Narrow no-break space used before AM/PM in some exports.
_NNBSP = "  "

_ANDROID_RE = re.compile(
    r"^(?P<date>\d{1,4}[./-]\d{1,2}[./-]\d{1,4}),?\s+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s*"
    r"(?P<ampm>[AaPp]\.?\s?[Mm]\.?)?\s+-\s"
    r"(?P<rest>.*)$"
)

_IOS_RE = re.compile(
    r"^\[(?P<date>\d{1,4}[./-]\d{1,2}[./-]\d{1,4}),?\s+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s*"
    r"(?P<ampm>[AaPp]\.?\s?[Mm]\.?)?\]\s"
    r"(?P<rest>.*)$"
)

# Message bodies that carry no analysable content.
NOISE_BODIES = {
    "<media omitted>",
    "this message was deleted",
    "you deleted this message",
    "missed voice call",
    "missed video call",
    "null",
}


@dataclass
class Message:
    timestamp: datetime
    sender: Optional[str]  # None for system messages
    text: str
    chat: str = ""
    lines: List[str] = field(default_factory=list, repr=False)

    @property
    def is_system(self) -> bool:
        return self.sender is None

    @property
    def is_noise(self) -> bool:
        return self.text.strip().lower() in NOISE_BODIES


def _clean(line: str) -> str:
    for ch in _STRIP_CHARS:
        line = line.replace(ch, "")
    for ch in _NNBSP:
        line = line.replace(ch, " ")
    return line.rstrip("\n\r")


def _split_date(date_str: str):
    return [int(p) for p in re.split(r"[./-]", date_str)]


def _infer_dayfirst(date_strings) -> bool:
    for ds in date_strings:
        parts = _split_date(ds)
        if len(parts) != 3:
            continue
        a, b = parts[0], parts[1]
        if a > 31:  # year-first (rare: yyyy-mm-dd) — month is second
            continue
        if a > 12 >= b:
            return True
        if b > 12 >= a:
            return False
    return True  # most WhatsApp locales export day-first


def _parse_timestamp(date_str: str, time_str: str, ampm: Optional[str], dayfirst: bool) -> Optional[datetime]:
    parts = _split_date(date_str)
    if len(parts) != 3:
        return None
    if parts[0] > 31:  # yyyy-mm-dd
        year, month, day = parts
    else:
        if dayfirst:
            day, month, year = parts
        else:
            month, day, year = parts
    if year < 100:
        year += 2000
    tparts = [int(p) for p in time_str.split(":")]
    hour, minute = tparts[0], tparts[1]
    second = tparts[2] if len(tparts) > 2 else 0
    if ampm:
        ap = ampm.replace(".", "").replace(" ", "").lower()
        if ap.startswith("p") and hour != 12:
            hour += 12
        elif ap.startswith("a") and hour == 12:
            hour = 0
    try:
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


def parse_export(text: str, chat: str = "", date_order: str = "auto") -> List[Message]:
    """Parse the full text of a WhatsApp export into a list of Messages.

    date_order: "auto" (infer), "dmy" or "mdy".
    """
    matched = []  # (groupdict or None-for-continuation, raw_line)
    for raw in text.splitlines():
        line = _clean(raw)
        m = _ANDROID_RE.match(line) or _IOS_RE.match(line)
        matched.append((m.groupdict() if m else None, line))

    if date_order == "dmy":
        dayfirst = True
    elif date_order == "mdy":
        dayfirst = False
    else:
        dayfirst = _infer_dayfirst(g["date"] for g, _ in matched if g)

    messages: List[Message] = []
    for g, line in matched:
        if g is None:
            # continuation of the previous message
            if messages and line.strip():
                messages[-1].text += "\n" + line
                messages[-1].lines.append(line)
            continue
        ts = _parse_timestamp(g["date"], g["time"], g.get("ampm"), dayfirst)
        if ts is None:
            if messages and line.strip():
                messages[-1].text += "\n" + line
            continue
        rest = g["rest"]
        sender: Optional[str] = None
        body = rest
        if ": " in rest:
            candidate, maybe_body = rest.split(": ", 1)
            # Sender names never span very long or contain a URL scheme.
            if len(candidate) <= 60 and "http" not in candidate.lower():
                sender, body = candidate.strip(), maybe_body
        messages.append(Message(timestamp=ts, sender=sender, text=body, chat=chat, lines=[body]))
    return messages


def parse_file(path: str, chat: str = "", date_order: str = "auto") -> List[Message]:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    if not chat:
        # "WhatsApp Chat with Project Alpha.txt" -> "Project Alpha"
        import os

        base = os.path.splitext(os.path.basename(path))[0]
        chat = re.sub(r"^WhatsApp Chat (?:with|-)?\s*", "", base).strip() or base
    return parse_export(text, chat=chat, date_order=date_order)
