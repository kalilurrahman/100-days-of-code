"""GitHub Issues adapter — mirror the tracker onto a repo's issue board.

``watracker github --repo owner/name`` performs a bidirectional sync:

* open tracker tasks with no issue yet → a new issue (labelled
  ``watracker``, plus ``priority:high`` when applicable), and the issue
  number is stored on the task as ``external_ref``;
* tasks completed/cancelled locally → their issue is closed;
* issues closed on GitHub → the matching local task is marked done
  (a completion anywhere wins, same rule as the Slack sync).

Auth: a token with ``repo`` (or fine-grained *Issues: read & write*) scope in
``GITHUB_TOKEN`` or ``--token``. Standard library only.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import List, Optional

from .store import Store

API = "https://api.github.com"
LABEL = "watracker"
_REF_PREFIX = "github:"


class GitHubError(RuntimeError):
    pass


def _request(method: str, url: str, token: str, body: Optional[dict] = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = resp.read().decode() or "{}"
            return json.loads(payload)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise GitHubError(f"GitHub API {exc.code} on {method} {url}: {detail}") from exc


def _issue_body(task: dict) -> str:
    lines = []
    if task.get("assignee"):
        lines.append(f"**Assignee (chat):** {task['assignee']}")
    if task.get("requester"):
        lines.append(f"**Requested by:** {task['requester']}")
    if task.get("due"):
        lines.append(f"**Due:** {task['due']}")
    origin = task.get("origin", "whatsapp")
    lines.append(f"**Source:** {origin} · {task.get('chat') or '-'}")
    if task.get("source_text"):
        lines.append(f"\n> {task['source_text']}")
    lines.append(f"\n<sub>synced by watracker · uid `{task['uid']}`</sub>")
    return "\n".join(lines)


def sync(store: Store, repo: str, token: Optional[str] = None) -> dict:
    """Run one bidirectional sync pass. Returns counts."""
    token = token or os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise GitHubError("No GitHub token. Set GITHUB_TOKEN or pass --token.")
    if "/" not in repo:
        raise GitHubError("Repo must be 'owner/name'.")

    created = closed = pulled = 0
    all_tasks = store.tasks()

    # 1. Push new open tasks as issues.
    for task in all_tasks:
        if task["status"] in ("done", "cancelled") or task.get("external_ref"):
            continue
        labels = [LABEL]
        if task.get("priority") == "high":
            labels.append("priority:high")
        issue = _request(
            "POST", f"{API}/repos/{repo}/issues", token,
            {"title": task["title"], "body": _issue_body(task), "labels": labels},
        )
        store.set_external_ref(task["id"], f"{_REF_PREFIX}{issue['number']}")
        created += 1

    # 2. Close issues for tasks finished locally.
    for task in all_tasks:
        ref = task.get("external_ref") or ""
        if task["status"] in ("done", "cancelled") and ref.startswith(_REF_PREFIX):
            number = ref[len(_REF_PREFIX):]
            issue = _request("GET", f"{API}/repos/{repo}/issues/{number}", token)
            if issue.get("state") == "open":
                _request("PATCH", f"{API}/repos/{repo}/issues/{number}", token,
                         {"state": "closed", "state_reason": "completed"})
                closed += 1

    # 3. Pull completions made on GitHub back into the tracker.
    open_by_ref = {
        t["external_ref"]: t
        for t in store.tasks(open_only=True)
        if (t.get("external_ref") or "").startswith(_REF_PREFIX)
    }
    if open_by_ref:
        issues: List[dict] = _request(
            "GET",
            f"{API}/repos/{repo}/issues?labels={LABEL}&state=closed&per_page=100",
            token,
        )
        for issue in issues:
            ref = f"{_REF_PREFIX}{issue['number']}"
            task = open_by_ref.get(ref)
            if task:
                store.update_status(task["id"], "done", note_ts=issue.get("closed_at"))
                pulled += 1

    return {"created": created, "closed": closed, "pulled": pulled}
