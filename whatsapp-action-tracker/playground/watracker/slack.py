"""Slack integration and cross-tracker sync.

Two integration surfaces:

1. **Slack webhook posting** — send any generated report to a Slack channel
   via an incoming webhook (``SLACK_WEBHOOK_URL`` or ``--webhook``).
   Markdown is converted to Slack mrkdwn and chunked under Slack's message
   size limit.

2. **Sync JSON (``action-tracker-sync/v1``)** — a platform-neutral task
   exchange format shared with the Slack assignment tracker (built in a
   sibling session).  ``export_sync`` writes this tracker's tasks;
   ``import_sync`` merges tasks produced by the Slack tracker (or any other
   tool emitting the same schema), so both trackers converge on one list.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import date, datetime
from typing import List, Optional

from . import SYNC_SCHEMA
from .store import Store

_CHUNK = 3800  # stay under Slack's ~4000-char text limit


def markdown_to_mrkdwn(text: str) -> str:
    out = []
    for line in text.splitlines():
        line = re.sub(r"^#{1,6}\s*(.+)$", r"*\1*", line)          # headers -> bold
        line = re.sub(r"\*\*(.+?)\*\*", r"*\1*", line)             # **bold** -> *bold*
        line = re.sub(r"~~(.+?)~~", r"~\1~", line)                 # strike
        line = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"_\1_", line)      # italics unchanged
        line = re.sub(r"^- ", "• ", line)                          # bullets
        out.append(line)
    return "\n".join(out)


def post_to_slack(text: str, webhook_url: Optional[str] = None) -> None:
    """Post markdown text to Slack via an incoming webhook."""
    url = webhook_url or os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        raise RuntimeError(
            "No Slack webhook configured. Set SLACK_WEBHOOK_URL or pass --webhook."
        )
    mrkdwn = markdown_to_mrkdwn(text)
    for chunk in _chunks(mrkdwn):
        payload = json.dumps({"text": chunk}).encode()
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status >= 300:
                raise RuntimeError(f"Slack webhook returned HTTP {resp.status}")


def _chunks(text: str) -> List[str]:
    if len(text) <= _CHUNK:
        return [text]
    chunks, current = [], ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > _CHUNK:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    return chunks


# -- cross-tracker sync (shared with the Slack assignment tracker) ----------


def task_to_sync(task: dict) -> dict:
    return {
        "uid": task["uid"],
        "title": task["title"],
        "assignee": task.get("assignee"),
        "requester": task.get("requester"),
        "status": task["status"],
        "due": task.get("due"),
        "priority": task.get("priority", "normal"),
        "channel": task.get("chat"),
        "kind": task.get("kind", "action"),
        "created_at": task["created_at"],
        "completed_at": task.get("completed_at"),
        "origin": {
            "platform": task.get("origin", "whatsapp"),
            "sender": task.get("source_sender"),
            "timestamp": task.get("source_ts"),
            "text": task.get("source_text"),
        },
    }


def export_sync(store: Store, path: Optional[str] = None) -> str:
    """Write all tasks as sync JSON; returns the JSON string."""
    doc = {
        "schema": SYNC_SCHEMA,
        "source": "whatsapp",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "tasks": [task_to_sync(t) for t in store.tasks()],
    }
    payload = json.dumps(doc, indent=2, ensure_ascii=False)
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
    return payload


def import_sync(store: Store, path: str, default_origin: str = "slack") -> dict:
    """Merge tasks from another tracker's sync JSON into this store.

    * New uids are inserted.
    * Existing tasks whose incoming status is 'done'/'cancelled' are closed
      (a remote completion wins over a local open state — the work happened).
    Returns counts: {"added": n, "updated": n, "skipped": n}.
    """
    with open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    if doc.get("schema") != SYNC_SCHEMA:
        raise ValueError(f"Unsupported sync schema: {doc.get('schema')!r} (expected {SYNC_SCHEMA})")

    added = updated = skipped = 0
    existing = {t["uid"]: t for t in store.tasks()}
    for item in doc.get("tasks", []):
        uid = item.get("uid")
        if not uid or not item.get("title"):
            skipped += 1
            continue
        current = existing.get(uid)
        if current is None:
            origin = (item.get("origin") or {}).get("platform") or doc.get("source") or default_origin
            src_ts = (item.get("origin") or {}).get("timestamp")
            store.add_task(
                item["title"],
                assignee=item.get("assignee"),
                requester=item.get("requester"),
                chat=item.get("channel") or "",
                due=date.fromisoformat(item["due"]) if item.get("due") else None,
                priority=item.get("priority", "normal"),
                kind=item.get("kind", "action"),
                origin=origin,
                source_ts=datetime.fromisoformat(src_ts) if src_ts else None,
                source_sender=(item.get("origin") or {}).get("sender"),
                source_text=(item.get("origin") or {}).get("text"),
                uid=uid,
                status=item.get("status", "open"),
                created_at=item.get("created_at"),
                completed_at=item.get("completed_at"),
            )
            added += 1
        elif item.get("status") in ("done", "cancelled") and current["status"] not in ("done", "cancelled"):
            store.update_status(current["id"], item["status"], note_ts=item.get("completed_at"))
            updated += 1
        else:
            skipped += 1
    return {"added": added, "updated": updated, "skipped": skipped}
