"""Markdown report generation: daily and weekly outstanding summaries, plus
an on-demand key-outcomes status snapshot."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional

from .store import Store


def _fmt_task(task: dict, today: date) -> str:
    parts = [f"**{task['title']}**"]
    if task.get("assignee"):
        parts.append(f"→ {task['assignee']}")
    if task.get("due"):
        due = date.fromisoformat(task["due"])
        if due < today:
            parts.append(f"⚠️ overdue (was due {due:%d %b})")
        elif due == today:
            parts.append("due **today**")
        else:
            parts.append(f"due {due:%d %b}")
    if task.get("priority") == "high":
        parts.insert(0, "🔴")
    if task.get("status") == "blocked":
        parts.append("_(blocked)_")
    elif task.get("status") == "in_progress":
        parts.append("_(in progress)_")
    if task.get("chat"):
        parts.append(f"· _{task['chat']}_")
    return "- " + " ".join(parts)


def _age_days(task: dict, today: date) -> int:
    ref = task.get("source_ts") or task.get("created_at") or ""
    try:
        return (today - datetime.fromisoformat(ref).date()).days
    except ValueError:
        return 0


def _partition(open_tasks: List[dict], today: date):
    overdue, due_soon, rest = [], [], []
    for t in open_tasks:
        if t.get("due"):
            due = date.fromisoformat(t["due"])
            if due < today:
                overdue.append(t)
            elif due <= today + timedelta(days=2):
                due_soon.append(t)
            else:
                rest.append(t)
        else:
            rest.append(t)
    return overdue, due_soon, rest


def daily_report(store: Store, on: Optional[date] = None) -> str:
    today = on or date.today()
    day_start, day_end = f"{today}T00:00:00", f"{today}T23:59:59"

    open_tasks = store.tasks(open_only=True)
    all_tasks = store.tasks()
    completed_today = [
        t for t in all_tasks
        if t["status"] == "done" and (t.get("completed_at") or "") >= day_start
        and (t.get("completed_at") or "") <= day_end
    ]
    created_today = [t for t in all_tasks if day_start <= t["created_at"] <= day_end]
    outcomes_today = store.outcomes(since=day_start, until=day_end)
    overdue, due_soon, rest = _partition(open_tasks, today)

    lines = [f"# 📋 Daily Action Summary — {today:%A, %d %B %Y}", ""]
    lines.append(
        f"**{len(open_tasks)} outstanding** · {len(overdue)} overdue · "
        f"{len(completed_today)} completed today · {len(created_today)} new today"
    )
    lines.append("")
    if overdue:
        lines.append("## ⚠️ Overdue")
        lines += [_fmt_task(t, today) for t in overdue]
        lines.append("")
    if due_soon:
        lines.append("## ⏰ Due today / next 2 days")
        lines += [_fmt_task(t, today) for t in due_soon]
        lines.append("")
    if rest:
        lines.append("## 📌 Other outstanding")
        lines += [_fmt_task(t, today) for t in rest]
        lines.append("")
    if completed_today:
        lines.append("## ✅ Completed today")
        lines += [f"- ~~{t['title']}~~" + (f" ({t['assignee']})" if t.get("assignee") else "") for t in completed_today]
        lines.append("")
    if outcomes_today:
        lines.append("## 🎯 Key outcomes & decisions today")
        lines += [f"- {o['text']}" + (f" — _{o['sender']}_" if o.get("sender") else "") for o in outcomes_today]
        lines.append("")
    if not open_tasks and not completed_today:
        lines.append("_Nothing tracked today — inbox zero!_ 🎉")
    return "\n".join(lines).rstrip() + "\n"


def weekly_report(store: Store, week_ending: Optional[date] = None) -> str:
    end = week_ending or date.today()
    start = end - timedelta(days=6)
    span_start, span_end = f"{start}T00:00:00", f"{end}T23:59:59"

    all_tasks = store.tasks()
    open_tasks = store.tasks(open_only=True)
    created = [t for t in all_tasks if span_start <= t["created_at"] <= span_end]
    completed = [
        t for t in all_tasks
        if t["status"] == "done" and span_start <= (t.get("completed_at") or "") <= span_end
    ]
    outcomes = store.outcomes(since=span_start, until=span_end)
    overdue, due_soon, rest = _partition(open_tasks, end)

    total_touched = len(created) or 1
    rate = round(100 * len(completed) / max(len(created), len(completed), 1))

    lines = [f"# 🗓 Weekly Action Report — {start:%d %b} → {end:%d %b %Y}", ""]
    lines.append(
        f"**New:** {len(created)} · **Completed:** {len(completed)} · "
        f"**Outstanding:** {len(open_tasks)} · **Throughput:** ~{rate}%"
    )
    lines.append("")

    # Outstanding grouped by assignee
    if open_tasks:
        lines.append("## 👥 Outstanding by assignee")
        by_assignee: dict = {}
        for t in open_tasks:
            by_assignee.setdefault(t.get("assignee") or "Unassigned", []).append(t)
        for who in sorted(by_assignee, key=lambda k: (k == "Unassigned", k.lower())):
            lines.append(f"**{who}** ({len(by_assignee[who])})")
            lines += [_fmt_task(t, end) for t in by_assignee[who]]
            lines.append("")

    if overdue:
        lines.append("## ⚠️ Overdue carry-overs")
        for t in overdue:
            lines.append(_fmt_task(t, end) + f" · {_age_days(t, end)}d old")
        lines.append("")

    # Aging of open tasks
    stale = [t for t in open_tasks if _age_days(t, end) > 7]
    if stale:
        lines.append(f"## 🕸 Stale (open > 1 week): {len(stale)}")
        lines += [f"- {t['title']} — {_age_days(t, end)}d" for t in stale[:10]]
        lines.append("")

    if completed:
        lines.append("## ✅ Completed this week")
        lines += [f"- ~~{t['title']}~~" + (f" ({t['assignee']})" if t.get("assignee") else "") for t in completed]
        lines.append("")
    if outcomes:
        lines.append("## 🎯 Key outcomes & decisions this week")
        lines += [f"- {o['text']}" + (f" — _{o['sender']}_" if o.get("sender") else "") for o in outcomes]
        lines.append("")
    _ = total_touched
    return "\n".join(lines).rstrip() + "\n"


def status_report(store: Store, recent_outcomes: int = 10) -> str:
    """Point-in-time snapshot: everything open plus recent key outcomes."""
    today = date.today()
    open_tasks = store.tasks(open_only=True)
    overdue, due_soon, rest = _partition(open_tasks, today)
    outcomes = store.outcomes()[-recent_outcomes:]

    lines = [f"# 📊 Tracker Status — {datetime.now():%d %b %Y %H:%M}", ""]
    lines.append(
        f"**{len(open_tasks)} open** · {len(overdue)} overdue · {len(due_soon)} due soon · "
        f"{sum(1 for t in open_tasks if t['status'] == 'blocked')} blocked"
    )
    lines.append("")
    for header, bucket in (("## ⚠️ Overdue", overdue), ("## ⏰ Due soon", due_soon), ("## 📌 Open", rest)):
        if bucket:
            lines.append(header)
            lines += [f"- [{t['id']}] " + _fmt_task(t, today)[2:] for t in bucket]
            lines.append("")
    if outcomes:
        lines.append("## 🎯 Recent key outcomes")
        lines += [f"- {o['text']}" for o in outcomes]
        lines.append("")
    if not open_tasks:
        lines.append("_No open tasks._")
    return "\n".join(lines).rstrip() + "\n"
