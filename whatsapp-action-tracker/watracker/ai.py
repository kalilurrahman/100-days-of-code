"""Optional Claude-powered extraction (higher accuracy than the rule engine).

Requires the official Anthropic SDK (``pip install anthropic``) and
credentials (``ANTHROPIC_API_KEY`` or an ``ant auth login`` profile).
Enabled with ``watracker ingest --ai``; the rule-based extractor in
:mod:`watracker.extractor` remains the zero-dependency default.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import List, Sequence

from .extractor import Action, ExtractionResult, Outcome
from .parser import Message

MODEL = "claude-opus-4-8"
_BATCH_CHARS = 24000  # transcript characters per API call

_SCHEMA = {
    "type": "object",
    "properties": {
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "assignee": {"type": ["string", "null"]},
                    "requester": {"type": ["string", "null"]},
                    "due": {"type": ["string", "null"], "description": "ISO date YYYY-MM-DD or null"},
                    "priority": {"type": "string", "enum": ["high", "normal"]},
                    "kind": {"type": "string", "enum": ["action", "follow_up"]},
                    "source_index": {"type": "integer", "description": "index of the [N] message it came from"},
                },
                "required": ["title", "assignee", "requester", "due", "priority", "kind", "source_index"],
                "additionalProperties": False,
            },
        },
        "completions": {
            "type": "array",
            "description": "titles of previously-listed actions reported as done in this transcript",
            "items": {"type": "string"},
        },
        "outcomes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "source_index": {"type": "integer"},
                },
                "required": ["text", "source_index"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["actions", "completions", "outcomes"],
    "additionalProperties": False,
}

_SYSTEM = """You extract action items from WhatsApp group-chat transcripts.

Each transcript line is: [N] TIMESTAMP SENDER: text

Extract:
- actions: concrete tasks, requests, commitments and assignments. Write a
  short imperative title. Set assignee to the person expected to do it
  (resolve "I'll..." to the sender; resolve @mentions and "X will ...");
  null if unclear. requester is the sender asking. Resolve relative
  deadlines ("by Friday", "EOD", "tomorrow") to ISO dates using the
  message timestamp. priority is "high" only for urgent/ASAP items.
  kind is "follow_up" for chase/check-in items, else "action".
- completions: titles of actions (from this same transcript) that a later
  message reports as finished.
- outcomes: decisions, agreements and approvals worth recording.

Ignore greetings, small talk, media placeholders and pure questions.
Do not invent tasks that are not clearly implied."""


def extract_ai(messages: Sequence[Message]) -> ExtractionResult:
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(
            "--ai requires the Anthropic SDK: pip install anthropic"
        ) from exc

    client = anthropic.Anthropic()
    usable = [m for m in messages if not m.is_system and not m.is_noise and m.text.strip()]
    result = ExtractionResult()

    for batch in _batches(usable):
        transcript = "\n".join(
            f"[{i}] {m.timestamp.isoformat(timespec='minutes')} {m.sender}: {m.text.replace(chr(10), ' / ')}"
            for i, m in enumerate(batch)
        )
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=_SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            messages=[{"role": "user", "content": transcript}],
        )
        if response.stop_reason == "refusal":
            continue
        text = next((b.text for b in response.content if b.type == "text"), "{}")
        data = json.loads(text)
        _merge(result, data, batch)
    return result


def _batches(messages: Sequence[Message]) -> List[List[Message]]:
    batches: List[List[Message]] = [[]]
    size = 0
    for m in messages:
        if size + len(m.text) > _BATCH_CHARS and batches[-1]:
            batches.append([])
            size = 0
        batches[-1].append(m)
        size += len(m.text)
    return [b for b in batches if b]


def _merge(result: ExtractionResult, data: dict, batch: Sequence[Message]) -> None:
    completed_titles = {t.strip().lower() for t in data.get("completions", [])}
    for item in data.get("actions", []):
        idx = item.get("source_index", 0)
        src = batch[idx] if 0 <= idx < len(batch) else batch[0]
        due = None
        if item.get("due"):
            try:
                due = date.fromisoformat(item["due"])
            except ValueError:
                due = None
        action = Action(
            title=item["title"],
            requester=item.get("requester") or src.sender,
            assignee=item.get("assignee"),
            due=due,
            priority=item.get("priority", "normal"),
            chat=src.chat,
            source_ts=src.timestamp,
            source_sender=src.sender,
            source_text=src.text,
            confidence=0.95,
            kind=item.get("kind", "action"),
        )
        if action.title.strip().lower() in completed_titles:
            # already reported done within the same transcript window
            action.kind = "done:" + action.kind
        result.actions.append(action)
    for item in data.get("outcomes", []):
        idx = item.get("source_index", 0)
        src = batch[idx] if 0 <= idx < len(batch) else batch[0]
        result.outcomes.append(
            Outcome(text=item["text"], ts=src.timestamp, sender=src.sender, chat=src.chat)
        )


def _now() -> datetime:  # kept for testability
    return datetime.now()


def narrative(report_md: str) -> str:
    """Executive-summary paragraph for a generated report (``report --ai``)."""
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(
            "--ai requires the Anthropic SDK: pip install anthropic"
        ) from exc

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        thinking={"type": "adaptive"},
        system=(
            "You write the executive summary for a team's action-tracker report. "
            "In 3-5 plain sentences: overall trajectory, the one or two items most "
            "at risk (overdue, blocked, or repeatedly chased) and who owns them, and "
            "any decision worth flagging. No headers, no bullets, no preamble."
        ),
        messages=[{"role": "user", "content": report_md}],
    )
    if response.stop_reason == "refusal":
        return ""
    return next((b.text for b in response.content if b.type == "text"), "").strip()
