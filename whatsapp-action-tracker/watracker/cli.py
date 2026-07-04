"""Command-line interface.

    python -m watracker ingest chat.txt --chat "Project Alpha"
    python -m watracker list --status open
    python -m watracker report daily --post-slack
    python -m watracker export --out sync/whatsapp-tasks.json
    python -m watracker import sync/slack-tasks.json
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

from . import __version__
from .extractor import ExtractionResult, extract, match_signal_to_task
from .parser import parse_file
from .reports import daily_report, status_report, weekly_report
from .slack import export_sync, import_sync, post_to_slack
from .store import Store


def apply_extraction(store: Store, result: ExtractionResult, min_confidence: float = 0.5) -> dict:
    """Persist an extraction result; returns counts."""
    added = closed = duplicates = 0
    for action in result.actions:
        if action.confidence < min_confidence:
            continue
        status = "open"
        kind = action.kind
        if kind.startswith("done:"):  # AI extractor: completed within the same window
            status, kind = "done", kind[5:]
        if status == "open" and store.find_similar_open(action.title):
            duplicates += 1
            continue
        row_id = store.add_task(
            action.title,
            assignee=action.assignee,
            requester=action.requester,
            chat=action.chat,
            due=action.due,
            priority=action.priority,
            kind=kind,
            confidence=action.confidence,
            source_ts=action.source_ts,
            source_sender=action.source_sender,
            source_text=action.source_text,
            status=status,
            completed_at=action.source_ts.isoformat(timespec="seconds") if status == "done" else None,
        )
        if row_id is None:
            duplicates += 1
        else:
            added += 1

    # Match status signals (done / in progress / blocked) to open tasks,
    # in chronological order so later signals see earlier tasks.
    for signal in sorted(result.signals, key=lambda s: s.ts):
        task = match_signal_to_task(signal, store.tasks(open_only=True))
        if task:
            store.update_status(task["id"], signal.status, note_ts=signal.ts.isoformat(timespec="seconds"))
            if signal.status == "done":
                closed += 1

    outcomes = 0
    for outcome in result.outcomes:
        if store.add_outcome(outcome.text, outcome.ts, chat=outcome.chat, sender=outcome.sender):
            outcomes += 1
    return {"added": added, "closed": closed, "duplicates": duplicates, "outcomes": outcomes}


def _cmd_ingest(args, store: Store) -> int:
    messages = parse_file(args.file, chat=args.chat or "", date_order=args.date_order)
    if not messages:
        print("No messages parsed — is this a WhatsApp export .txt?", file=sys.stderr)
        return 1
    if args.ai:
        from .ai import extract_ai

        try:
            result = extract_ai(messages)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    else:
        result = extract(messages)
    counts = apply_extraction(store, result)
    chat = messages[0].chat or args.chat or "(unnamed chat)"
    print(
        f"Ingested {len(messages)} messages from '{chat}': "
        f"{counts['added']} new tasks, {counts['closed']} closed, "
        f"{counts['outcomes']} outcomes, {counts['duplicates']} duplicates skipped."
    )
    return 0


def _cmd_list(args, store: Store) -> int:
    tasks = store.tasks(
        status=args.status,
        assignee=args.assignee,
        chat=args.chat,
        open_only=(args.status is None),
    )
    if not tasks:
        print("No matching tasks.")
        return 0
    today = date.today()
    for t in tasks:
        due = ""
        if t.get("due"):
            d = date.fromisoformat(t["due"])
            due = f"  due {d:%d %b}" + (" ⚠️OVERDUE" if d < today and t["status"] not in ("done", "cancelled") else "")
        who = f"  @{t['assignee']}" if t.get("assignee") else ""
        pri = " 🔴" if t.get("priority") == "high" else ""
        print(f"[{t['id']:>4}] {t['status']:<11} {t['title']}{who}{due}{pri}  ({t.get('chat') or t.get('origin')})")
    return 0


def _cmd_add(args, store: Store) -> int:
    row_id = store.add_task(
        args.title,
        assignee=args.assignee,
        due=date.fromisoformat(args.due) if args.due else None,
        priority="high" if args.high else "normal",
        chat=args.chat or "",
        origin="manual",
        source_ts=datetime.now(),
    )
    print(f"Added task [{row_id}] {args.title}" if row_id else "Task already exists.")
    return 0


def _cmd_status(args, store: Store) -> int:
    ok = store.update_status(args.id, args.to)
    print(f"Task [{args.id}] -> {args.to}" if ok else f"No task with id {args.id}", file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


def _cmd_report(args, store: Store) -> int:
    if args.kind == "daily":
        text = daily_report(store, on=date.fromisoformat(args.date) if args.date else None)
    elif args.kind == "weekly":
        text = weekly_report(store, week_ending=date.fromisoformat(args.date) if args.date else None)
    else:
        text = status_report(store)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"Report written to {args.out}")
    else:
        print(text)
    if args.post_slack:
        post_to_slack(text, webhook_url=args.webhook)
        print("Posted to Slack.", file=sys.stderr)
    return 0


def _cmd_export(args, store: Store) -> int:
    payload = export_sync(store, path=args.out)
    if args.out:
        print(f"Sync export written to {args.out}")
    else:
        print(payload)
    return 0


def _cmd_import(args, store: Store) -> int:
    counts = import_sync(store, args.file)
    print(f"Imported: {counts['added']} added, {counts['updated']} updated, {counts['skipped']} unchanged.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="watracker",
        description="WhatsApp action, task & assignment tracker with daily/weekly summaries and Slack integration.",
    )
    p.add_argument("--db", help="path to the SQLite database (default: ~/.watracker/watracker.db)")
    p.add_argument("--version", action="version", version=f"watracker {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("ingest", help="analyse a WhatsApp export .txt and track its actions")
    sp.add_argument("file", help="path to the exported chat file")
    sp.add_argument("--chat", help="chat/group name (default: derived from the filename)")
    sp.add_argument("--date-order", choices=("auto", "dmy", "mdy"), default="auto")
    sp.add_argument("--ai", action="store_true", help="use the Claude API for higher-accuracy extraction")
    sp.set_defaults(func=_cmd_ingest)

    sp = sub.add_parser("list", help="list tasks (open tasks by default)")
    sp.add_argument("--status", choices=("open", "in_progress", "blocked", "done", "cancelled"))
    sp.add_argument("--assignee")
    sp.add_argument("--chat")
    sp.set_defaults(func=_cmd_list)

    sp = sub.add_parser("add", help="manually add a task")
    sp.add_argument("title")
    sp.add_argument("--assignee")
    sp.add_argument("--due", help="YYYY-MM-DD")
    sp.add_argument("--high", action="store_true", help="mark high priority")
    sp.add_argument("--chat")
    sp.set_defaults(func=_cmd_add)

    for name, target in (("done", "done"), ("cancel", "cancelled"), ("block", "blocked"), ("start", "in_progress"), ("reopen", "open")):
        sp = sub.add_parser(name, help=f"mark a task {target}")
        sp.add_argument("id", type=int)
        sp.set_defaults(func=_cmd_status, to=target)

    sp = sub.add_parser("report", help="generate a summary report")
    sp.add_argument("kind", choices=("daily", "weekly", "status"))
    sp.add_argument("--date", help="report date / week-ending date (YYYY-MM-DD)")
    sp.add_argument("--out", help="write the report to a file")
    sp.add_argument("--post-slack", action="store_true", help="also post to Slack (SLACK_WEBHOOK_URL)")
    sp.add_argument("--webhook", help="Slack incoming-webhook URL (overrides env)")
    sp.set_defaults(func=_cmd_report)

    sp = sub.add_parser("export", help="export tasks as action-tracker-sync/v1 JSON")
    sp.add_argument("--out", help="output path (default: stdout)")
    sp.set_defaults(func=_cmd_export)

    sp = sub.add_parser("import", help="merge tasks from another tracker's sync JSON (e.g. the Slack tracker)")
    sp.add_argument("file")
    sp.set_defaults(func=_cmd_import)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    store = Store(args.db)
    try:
        return args.func(args, store)
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
