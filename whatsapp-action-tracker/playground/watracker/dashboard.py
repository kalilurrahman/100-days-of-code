"""Static HTML dashboard — a self-contained, shareable view of the tracker.

``watracker dashboard --out dashboard.html`` renders summary tiles, an
open-task table grouped by urgency, per-assignee counts and recent outcomes
into a single file with inline CSS (light/dark via prefers-color-scheme).
Host it anywhere static — e.g. this repo's GitHub Pages.
"""

from __future__ import annotations

import html
from datetime import date, datetime
from typing import List

from .store import Store

_CSS = """
:root{--bg:#F6F8F5;--ink:#17251D;--soft:#4A5C52;--line:#D8E2DA;--card:#fff;
--green:#1E9E58;--amber:#B26B12;--red:#C0392B;--blue:#2563EB}
@media(prefers-color-scheme:dark){:root{--bg:#101915;--ink:#E2EDE5;--soft:#93A89B;
--line:#24352B;--card:#16231C;--green:#3CC176;--amber:#E0A050;--red:#E5766A;--blue:#7DBEF0}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 "Avenir Next","Segoe UI",system-ui,sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:36px 20px 72px}
h1{font-size:26px;margin:0 0 4px}.sub{color:var(--soft);font-size:13px;margin:0 0 24px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:28px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.tile b{display:block;font-size:26px;font-variant-numeric:tabular-nums}
.tile span{color:var(--soft);font-size:12px;text-transform:uppercase;letter-spacing:.08em}
.tile.warn b{color:var(--amber)}.tile.bad b{color:var(--red)}.tile.ok b{color:var(--green)}
h2{font-size:17px;margin:32px 0 10px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);
border-radius:10px;overflow:hidden;font-size:14px}
.scroll{overflow-x:auto}
th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line)}
th{color:var(--soft);font-size:11px;text-transform:uppercase;letter-spacing:.08em}
tr:last-child td{border-bottom:none}
td.num{font-variant-numeric:tabular-nums;white-space:nowrap}
.pill{display:inline-block;padding:1px 9px;border-radius:999px;font-size:11.5px;font-weight:600}
.pill.open{background:color-mix(in srgb,var(--green) 15%,transparent);color:var(--green)}
.pill.blocked{background:color-mix(in srgb,var(--amber) 18%,transparent);color:var(--amber)}
.pill.in_progress{background:color-mix(in srgb,var(--blue) 15%,transparent);color:var(--blue)}
.pill.done{background:var(--line);color:var(--soft)}
.overdue{color:var(--red);font-weight:600}.high{color:var(--red)}
.risk{color:var(--amber);font-weight:600}
ul{padding-left:20px}li{margin:4px 0}
footer{margin-top:40px;color:var(--soft);font-size:12px;border-top:1px solid var(--line);padding-top:14px}
"""


def _row(task: dict, today: date) -> str:
    due_html = "—"
    if task.get("due"):
        due = date.fromisoformat(task["due"])
        overdue = due < today and task["status"] not in ("done", "cancelled")
        due_html = f'<span class="{"overdue" if overdue else ""}">{due:%d %b}{" ⚠️" if overdue else ""}</span>'
    flags = []
    if task.get("priority") == "high":
        flags.append('<span class="high">high</span>')
    if (task.get("chases") or 0) >= 2:
        flags.append(f'<span class="risk">🔥 chased ×{task["chases"]}</span>')
    return (
        "<tr>"
        f'<td>{html.escape(task["title"])}</td>'
        f'<td>{html.escape(task.get("assignee") or "—")}</td>'
        f'<td><span class="pill {task["status"]}">{task["status"].replace("_", " ")}</span></td>'
        f'<td class="num">{due_html}</td>'
        f'<td>{" ".join(flags) or "—"}</td>'
        f'<td>{html.escape(task.get("chat") or task.get("origin") or "")}</td>'
        "</tr>"
    )


def build_dashboard(store: Store, today: date = None) -> str:
    today = today or date.today()
    open_tasks = store.tasks(open_only=True)
    all_tasks = store.tasks()
    done = [t for t in all_tasks if t["status"] == "done"]
    overdue = [
        t for t in open_tasks
        if t.get("due") and date.fromisoformat(t["due"]) < today
    ]
    blocked = [t for t in open_tasks if t["status"] == "blocked"]
    at_risk = [t for t in open_tasks if (t.get("chases") or 0) >= 2]
    outcomes = store.outcomes()[-8:]

    by_assignee: dict = {}
    for t in open_tasks:
        by_assignee[t.get("assignee") or "Unassigned"] = by_assignee.get(t.get("assignee") or "Unassigned", 0) + 1

    def table(tasks: List[dict]) -> str:
        if not tasks:
            return "<p class='sub'>Nothing here.</p>"
        rows = "".join(_row(t, today) for t in tasks)
        return (
            '<div class="scroll"><table><thead><tr><th>Task</th><th>Assignee</th><th>Status</th>'
            f'<th>Due</th><th>Flags</th><th>Source</th></tr></thead><tbody>{rows}</tbody></table></div>'
        )

    assignee_rows = "".join(
        f'<tr><td>{html.escape(k)}</td><td class="num">{v}</td></tr>'
        for k, v in sorted(by_assignee.items(), key=lambda kv: -kv[1])
    )
    outcome_items = "".join(
        f"<li>{html.escape(o['text'])} <span class='sub'>— {html.escape(o.get('sender') or '')}</span></li>"
        for o in outcomes
    )

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Action Tracker Dashboard</title><style>{_CSS}</style></head><body><div class="wrap">
<h1>📋 Action Tracker</h1>
<p class="sub">Generated {datetime.now():%d %b %Y %H:%M} · {len(all_tasks)} tasks tracked</p>
<div class="tiles">
<div class="tile"><b>{len(open_tasks)}</b><span>Open</span></div>
<div class="tile bad"><b>{len(overdue)}</b><span>Overdue</span></div>
<div class="tile warn"><b>{len(blocked)}</b><span>Blocked</span></div>
<div class="tile warn"><b>{len(at_risk)}</b><span>At risk</span></div>
<div class="tile ok"><b>{len(done)}</b><span>Done</span></div>
</div>
<h2>Open tasks</h2>{table(open_tasks)}
<h2>Open by assignee</h2>
<div class="scroll"><table><thead><tr><th>Assignee</th><th>Open</th></tr></thead><tbody>{assignee_rows or '<tr><td colspan="2">—</td></tr>'}</tbody></table></div>
<h2>Recent key outcomes</h2>{f'<ul>{outcome_items}</ul>' if outcome_items else "<p class='sub'>None recorded.</p>"}
<h2>Recently completed</h2>{table(done[-10:])}
<footer>watracker — WhatsApp action &amp; assignment tracker</footer>
</div></body></html>"""
