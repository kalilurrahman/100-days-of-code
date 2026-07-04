"""Additional ingestion sources beyond WhatsApp exports.

All sources normalise to :class:`watracker.parser.Message`, so the extractor,
tracker and reports work identically regardless of where a message came from.

Supported:

* **Email** — a single ``.eml`` file or an mbox mailbox. Each mail becomes one
  message (subject prepended for context).
* **Meeting transcripts** — WebVTT ``.vtt`` files as produced by Teams/Zoom,
  in both ``Speaker: text`` and ``<v Speaker>text</v>`` cue styles. Cue
  offsets are anchored to a reference date (default: the file's mtime).
* **Telegram** — Telegram Desktop's ``result.json`` chat export.

``load_messages`` dispatches on file extension (override with ``source=``).
"""

from __future__ import annotations

import email
import email.policy
import json
import mailbox
import os
import re
from datetime import date, datetime, timedelta
from typing import List, Optional

from .parser import Message, parse_file

_VTT_TIME_RE = re.compile(
    r"^(?P<start>(?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3})\s+-->\s+(?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3}"
)
_VTT_VOICE_RE = re.compile(r"<v\s+([^>]+)>(.*?)(?:</v>)?$", re.S)


# -- email -------------------------------------------------------------------


def _email_to_message(msg, chat: str) -> Optional[Message]:
    sender = msg.get("From", "")
    name = email.utils.parseaddr(sender)[0] or email.utils.parseaddr(sender)[1]
    try:
        ts = email.utils.parsedate_to_datetime(msg.get("Date"))
        ts = ts.replace(tzinfo=None)
    except (TypeError, ValueError):
        return None
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_content()
                break
    else:
        body = msg.get_content() if msg.get_content_type() == "text/plain" else ""
    # Drop quoted reply history — only the new text carries actions.
    lines = []
    for line in (body or "").splitlines():
        if line.startswith(">") or line.startswith("On ") and line.rstrip().endswith("wrote:"):
            break
        lines.append(line)
    text = "\n".join(lines).strip()
    subject = (msg.get("Subject") or "").strip()
    if subject and not subject.lower().startswith("re:"):
        text = f"{subject}. {text}" if text else subject
    if not text:
        return None
    return Message(timestamp=ts, sender=name or None, text=text, chat=chat)


def parse_email_file(path: str, chat: str = "") -> List[Message]:
    chat = chat or os.path.splitext(os.path.basename(path))[0]
    messages: List[Message] = []
    if path.endswith(".mbox") or os.path.isdir(path):
        box = mailbox.mbox(path, factory=None)
        for item in box:
            parsed = email.message_from_bytes(bytes(item), policy=email.policy.default)
            m = _email_to_message(parsed, chat)
            if m:
                messages.append(m)
    else:
        with open(path, "rb") as fh:
            parsed = email.message_from_binary_file(fh, policy=email.policy.default)
        m = _email_to_message(parsed, chat)
        if m:
            messages.append(m)
    messages.sort(key=lambda m: m.timestamp)
    return messages


# -- WebVTT transcripts --------------------------------------------------------


def _vtt_offset(stamp: str) -> timedelta:
    stamp = stamp.replace(",", ".")
    parts = stamp.split(":")
    if len(parts) == 2:
        parts = ["0"] + parts
    hours, minutes = int(parts[0]), int(parts[1])
    seconds = float(parts[2])
    return timedelta(hours=hours, minutes=minutes, seconds=seconds)


def parse_vtt_file(path: str, chat: str = "", ref_date: Optional[date] = None) -> List[Message]:
    """Parse a WebVTT transcript; cue offsets are anchored to *ref_date*."""
    chat = chat or os.path.splitext(os.path.basename(path))[0]
    if ref_date is None:
        ref_date = date.fromtimestamp(os.path.getmtime(path))
    base = datetime(ref_date.year, ref_date.month, ref_date.day, 9, 0)

    messages: List[Message] = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()

    i = 0
    while i < len(lines):
        m = _VTT_TIME_RE.match(lines[i].strip())
        if not m:
            i += 1
            continue
        ts = base + _vtt_offset(m.group("start"))
        i += 1
        cue_lines = []
        while i < len(lines) and lines[i].strip():
            cue_lines.append(lines[i].strip())
            i += 1
        cue = " ".join(cue_lines)
        sender: Optional[str] = None
        voice = _VTT_VOICE_RE.search(cue)
        if voice:
            sender, text = voice.group(1).strip(), voice.group(2).strip()
        elif ": " in cue:
            candidate, rest = cue.split(": ", 1)
            if len(candidate) <= 60:
                sender, text = candidate.strip(), rest
            else:
                text = cue
        else:
            text = cue
        text = re.sub(r"</?[a-z][^>]*>", "", text).strip()
        if text:
            # Merge consecutive cues from the same speaker into one utterance.
            if messages and messages[-1].sender == sender and (ts - messages[-1].timestamp) < timedelta(seconds=30):
                messages[-1].text += " " + text
            else:
                messages.append(Message(timestamp=ts, sender=sender, text=text, chat=chat))
    return messages


# -- Telegram ------------------------------------------------------------------


def _telegram_text(raw) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):  # rich text: list of strings and entity dicts
        return "".join(p if isinstance(p, str) else p.get("text", "") for p in raw)
    return ""


def parse_telegram_file(path: str, chat: str = "") -> List[Message]:
    """Parse a Telegram Desktop export (result.json)."""
    with open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    chat = chat or doc.get("name") or "Telegram"
    messages: List[Message] = []
    for item in doc.get("messages", []):
        if item.get("type") != "message":
            continue
        text = _telegram_text(item.get("text", "")).strip()
        if not text:
            continue
        try:
            ts = datetime.fromisoformat(item["date"])
        except (KeyError, ValueError):
            continue
        messages.append(
            Message(timestamp=ts, sender=item.get("from"), text=text, chat=chat)
        )
    return messages


# -- dispatcher ----------------------------------------------------------------

SOURCES = ("auto", "whatsapp", "email", "vtt", "telegram")


def load_messages(
    path: str,
    chat: str = "",
    source: str = "auto",
    date_order: str = "auto",
    ref_date: Optional[date] = None,
) -> List[Message]:
    if source == "auto":
        ext = os.path.splitext(path)[1].lower()
        source = {
            ".eml": "email", ".mbox": "email",
            ".vtt": "vtt",
            ".json": "telegram",
        }.get(ext, "whatsapp")
    if source == "email":
        return parse_email_file(path, chat=chat)
    if source == "vtt":
        return parse_vtt_file(path, chat=chat, ref_date=ref_date)
    if source == "telegram":
        return parse_telegram_file(path, chat=chat)
    return parse_file(path, chat=chat, date_order=date_order)
