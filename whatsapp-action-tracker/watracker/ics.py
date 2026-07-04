"""iCalendar feed — surface task due dates in Google/Outlook/Apple Calendar.

``watracker calendar --out tasks.ics`` writes an all-day VEVENT per task
that has a due date. Subscribe to the file (host it anywhere static) or
import it once. Completed tasks are included with STATUS:COMPLETED so a
re-import updates them; pass ``open_only=True`` to skip them.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from .store import Store


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """RFC 5545 line folding at 75 octets."""
    out = []
    while len(line.encode("utf-8")) > 75:
        cut = 75
        while len(line[:cut].encode("utf-8")) > 75:
            cut -= 1
        out.append(line[:cut])
        line = " " + line[cut:]
    out.append(line)
    return "\r\n".join(out)


def build_ics(store: Store, open_only: bool = False, now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    stamp = now.strftime("%Y%m%dT%H%M%S")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//watracker//action tracker//EN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:Action Tracker",
    ]
    tasks = store.tasks(open_only=True) if open_only else store.tasks()
    for task in tasks:
        if not task.get("due"):
            continue
        due = date.fromisoformat(task["due"])
        summary = task["title"]
        if task.get("assignee"):
            summary += f" ({task['assignee']})"
        if task.get("priority") == "high":
            summary = "❗ " + summary
        desc_bits = [f"Status: {task['status']}"]
        if task.get("chat"):
            desc_bits.append(f"Chat: {task['chat']}")
        if task.get("source_text"):
            desc_bits.append(f"From: {task['source_text']}")
        status = "COMPLETED" if task["status"] == "done" else (
            "CANCELLED" if task["status"] == "cancelled" else "CONFIRMED"
        )
        lines += [
            "BEGIN:VEVENT",
            f"UID:{task['uid']}@watracker",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{due:%Y%m%d}",
            f"DTEND;VALUE=DATE:{(due + timedelta(days=1)):%Y%m%d}",
            _fold(f"SUMMARY:{_escape(summary)}"),
            _fold(f"DESCRIPTION:{_escape(' | '.join(desc_bits))}"),
            f"STATUS:{status}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
