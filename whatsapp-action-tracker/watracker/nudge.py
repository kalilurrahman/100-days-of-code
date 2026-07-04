"""Nudge & escalation engine — actively drives open work to completion.

``watracker nudge`` scans the tracker and composes a per-person nudge for:

* **overdue** tasks (escalated to the requester once overdue ≥ N days),
* **blocked** tasks that have sat blocked for a while,
* **stale** tasks open longer than the stale threshold with no due date,
* **at-risk** tasks that have been chased repeatedly in chat.

Nudges are rate-limited per task (``last_nudged_at``) so a cron running the
command hourly won't spam anyone. Output goes to stdout by default, or to
Slack with ``--post-slack``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from .store import Store

DEFAULT_STALE_DAYS = 7
DEFAULT_ESCALATE_DAYS = 3
DEFAULT_MIN_INTERVAL_HOURS = 20
AT_RISK_CHASES = 2


@dataclass
class Nudge:
    assignee: str
    lines: List[str] = field(default_factory=list)
    escalations: List[str] = field(default_factory=list)  # lines cc'ing the requester
    task_ids: List[int] = field(default_factory=list)


def _days_open(task: dict, today: date) -> int:
    ref = task.get("source_ts") or task.get("created_at") or ""
    try:
        return (today - datetime.fromisoformat(ref).date()).days
    except ValueError:
        return 0


def _recently_nudged(task: dict, now: datetime, min_interval_hours: int) -> bool:
    last = task.get("last_nudged_at")
    if not last:
        return False
    try:
        return now - datetime.fromisoformat(last) < timedelta(hours=min_interval_hours)
    except ValueError:
        return False


def build_nudges(
    store: Store,
    today: Optional[date] = None,
    now: Optional[datetime] = None,
    stale_days: int = DEFAULT_STALE_DAYS,
    escalate_days: int = DEFAULT_ESCALATE_DAYS,
    min_interval_hours: int = DEFAULT_MIN_INTERVAL_HOURS,
) -> List[Nudge]:
    today = today or date.today()
    now = now or datetime.now()
    per_person: Dict[str, Nudge] = {}

    def bucket(task: dict) -> Nudge:
        who = task.get("assignee") or task.get("requester") or "team"
        if who not in per_person:
            per_person[who] = Nudge(assignee=who)
        return per_person[who]

    for task in store.tasks(open_only=True):
        if _recently_nudged(task, now, min_interval_hours):
            continue
        due = date.fromisoformat(task["due"]) if task.get("due") else None
        chased = (task.get("chases") or 0) >= AT_RISK_CHASES
        n = None

        if due and due < today:
            days_over = (today - due).days
            n = bucket(task)
            n.lines.append(
                f"⚠️ *{task['title']}* is {days_over} day{'s' if days_over != 1 else ''} overdue "
                f"(was due {due:%d %b}). Can you update its status?"
            )
            requester = task.get("requester")
            if days_over >= escalate_days and requester and requester != n.assignee:
                n.escalations.append(
                    f"↑ {requester}: '{task['title']}' ({n.assignee}) is {days_over}d overdue — may need your help."
                )
        elif task["status"] == "blocked":
            n = bucket(task)
            n.lines.append(
                f"⛔ *{task['title']}* is still blocked. Is there anything the group can do to unblock it?"
            )
        elif chased:
            n = bucket(task)
            n.lines.append(
                f"🔥 *{task['title']}* has been chased {task['chases']} times in chat — worth a quick status update."
            )
        elif not due and _days_open(task, today) > stale_days:
            n = bucket(task)
            n.lines.append(
                f"🕸 *{task['title']}* has been open {_days_open(task, today)} days with no due date. "
                f"Still relevant? Add a date or close it."
            )
        if n is not None:
            n.task_ids.append(task["id"])

    return [n for n in per_person.values() if n.lines]


def format_nudges(nudges: List[Nudge]) -> str:
    if not nudges:
        return "_All caught up — nothing to nudge._"
    blocks = []
    for n in sorted(nudges, key=lambda x: x.assignee.lower()):
        lines = [f"👋 **{n.assignee}** — friendly nudge:"]
        lines += [f"- {line}" for line in n.lines]
        lines += [f"- {line}" for line in n.escalations]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def send_nudges(
    store: Store,
    webhook_url: Optional[str] = None,
    dry_run: bool = False,
    **thresholds,
) -> str:
    """Build, optionally deliver, and record nudges. Returns the text sent."""
    nudges = build_nudges(store, **thresholds)
    text = format_nudges(nudges)
    if not dry_run and nudges:
        if webhook_url is not None or os.environ.get("SLACK_WEBHOOK_URL"):
            from .slack import post_to_slack

            post_to_slack(text, webhook_url=webhook_url)
        for n in nudges:
            for task_id in n.task_ids:
                store.mark_nudged(task_id)
    return text
