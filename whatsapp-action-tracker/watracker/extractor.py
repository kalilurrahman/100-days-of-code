"""Rule-based extraction of actions, follow-ups, status updates and outcomes
from parsed WhatsApp messages.

The extractor walks messages chronologically and produces:

* ``Action`` items — requests, commitments and assignments, with the
  detected assignee, requester, due date and priority.
* Status signals — completion ("done", "✅", "sent it"), progress
  ("working on it") and blockers ("stuck", "waiting on") that are matched
  back to open actions by token overlap.
* ``Outcome`` records — decisions and agreements ("we decided...",
  "approved", "finalized") that feed the key-outcomes summary.

For higher-accuracy extraction, see :mod:`watracker.ai` (optional Claude
API enhancement); this module has no dependencies and is the default.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, List, Optional, Sequence

from .dates import find_due_date
from .parser import Message

MENTION_RE = re.compile(r"@([\w.\-]+)")
URL_RE = re.compile(r"https?://\S+")

# (pattern, confidence).  Each pattern must expose a "task" group.
REQUEST_PATTERNS = [
    (re.compile(r"(?:^|\b)(?:todo|to-do|action item|action|task)\s*[:\-]\s*(?P<task>.+)", re.I), 0.95),
    (re.compile(r"\b(?:please|pls|plz|kindly)[,\s]+(?P<task>.{4,})", re.I), 0.9),
    (re.compile(r"\b(?:don'?t forget to|remember to|make sure (?:to|you|we))\s+(?P<task>.+)", re.I), 0.9),
    (re.compile(r"\b(?:can|could|will|would)\s+(?:you|u|someone|somebody|anyone)\s+(?:please\s+)?(?P<task>.{4,}?)\s*\??$", re.I | re.M), 0.85),
    (re.compile(r"\b(?:we|you)\s+(?:need|have)\s+to\s+(?P<task>.+)", re.I), 0.75),
    (re.compile(r"\b(?:need to|have to|must)\s+(?:follow up|chase|check)\s*(?P<task>.*)", re.I), 0.8),
    (re.compile(r"\bfollow(?:ing)?[ -]up\s+(?:on|with)\s+(?P<task>.+)", re.I), 0.85),
    (re.compile(r"\blet'?s\s+(?P<task>.{6,})", re.I), 0.55),
    # -- multilingual request packs (common in mixed-language group chats) --
    # Spanish: "por favor envía…", "puedes revisar…"
    (re.compile(r"\b(?:por favor|puedes|podr[ií]as|puede usted)[,\s]+(?P<task>.{4,})", re.I), 0.8),
    (re.compile(r"\bno (?:te )?olvides de\s+(?P<task>.{4,})", re.I), 0.85),
    # French: "peux-tu envoyer…", "n'oublie pas de…"
    (re.compile(r"\b(?:s'il te pla[iî]t|s'il vous pla[iî]t|peux-tu|pouvez-vous|pourrais-tu)[,\s]+(?P<task>.{4,})", re.I), 0.8),
    (re.compile(r"\bn'oublie(?:z)? pas de\s+(?P<task>.{4,})", re.I), 0.85),
    # Hinglish: "report bhej do", "presentation ready kar dena", "… karna hai"
    (re.compile(r"(?P<task>[\w @#&/'-]{4,}?)\s+(?:bhej(?:o| do| dena| dijiye)|kar(?: do| dena| dijiye| lena)|bana(?: do| dena| lo))\b", re.I), 0.7),
    (re.compile(r"(?P<task>[\w @#&/'-]{4,}?)\s+karn[ae] (?:hai|hoga|padega)\b", re.I), 0.7),
    (re.compile(r"\byaad se\s+(?P<task>.{4,})", re.I), 0.75),
]

# "Bob will send the deck" / "@bob to review the PR" — task with an assignee.
ASSIGNMENT_RE = re.compile(
    r"^(?P<who>@?[A-Z][\w.\-]*(?:\s[A-Z][\w.\-]*)?)\s+"
    r"(?:will|shall|to|should|has to|needs to|is going to|is gonna|can)\s+"
    r"(?P<task>.{4,})$",
    re.M,
)

# First-person commitments: "I'll share the report tomorrow".
COMMITMENT_RE = re.compile(r"\b(?:i'?ll|i will|i can|i am going to|i'?m going to|i shall)\s+(?P<task>.{4,})", re.I)

DONE_RE = re.compile(
    r"\b(?:done|completed|complete|finished|closed|sorted|resolved|deployed|"
    r"sent|shared|submitted|uploaded|fixed|delivered|merged|booked|paid|"
    # es / fr / hinglish completion markers
    r"hecho|listo|enviado|terminado|fait|termin[ée]|envoy[ée]|"
    r"ho gaya|kar diya|bhej diya|bana diya|hogaya)\b|✅|✔|☑",
    re.I,
)

# Chasing / repeated follow-ups on something already asked — a risk signal.
CHASE_RE = re.compile(
    r"\b(?:any update|any progress|gentle reminder|reminder|still waiting|"
    r"following up again|bump(?:ing)?(?: this)?|status\s*\?|"
    r"asked (?:this |you )?(?:before|already|twice|again)|"
    r"(?:2nd|3rd|second|third) (?:reminder|time asking))\b",
    re.I,
)
PROGRESS_RE = re.compile(r"\b(?:working on|started (?:on|with)?|in progress|wip|picking (?:this|it) up|on it)\b", re.I)
BLOCKED_RE = re.compile(r"\b(?:blocked|stuck|waiting (?:on|for)|on hold|can'?t proceed)\b", re.I)

OUTCOME_RE = re.compile(
    r"\b(?:decided|we agreed|agreed to|agreed that|approved|confirmed|finalized|finalised|"
    r"signed off|go ahead with|greenlit|concluded)\b",
    re.I,
)

URGENT_RE = re.compile(
    r"\b(?:urgent|urgently|asap|critical|high priority|top priority|immediately|right away|"
    r"urgente|tr[eè]s urgent|jaldi|turant)\b",
    re.I,
)

QUESTION_ONLY_RE = re.compile(r"^\s*(?:what|why|when|where|who|how|is|are|was|were|do|does|did|any update)\b.*\?\s*$", re.I | re.S)

# Capitalised sentence-starters that are not people's names.
NOT_A_NAME = {
    "we", "it", "there", "this", "that", "the", "i", "you", "http", "https",
    "need", "needs", "want", "wants", "have", "has", "must", "remember",
    "make", "let", "lets", "also", "please", "pls", "don't", "dont", "going",
    "try", "everyone", "someone", "anybody", "somebody", "anyone", "who",
    "what", "when", "maybe", "perhaps", "ok", "okay", "yes", "no",
    "agreed", "decided", "approved", "confirmed", "finalized", "finalised",
}

STOPWORDS = {
    "the", "a", "an", "and", "for", "with", "this", "that", "will", "please",
    "you", "your", "our", "from", "them", "then", "have", "has", "need",
    "needs", "can", "could", "would", "should", "before", "after", "about",
    "there", "here", "when", "what", "into", "onto", "also", "just",
}


@dataclass
class Action:
    title: str
    requester: Optional[str]
    assignee: Optional[str]
    due: Optional[date]
    priority: str  # "high" | "normal"
    chat: str
    source_ts: datetime
    source_sender: Optional[str]
    source_text: str
    confidence: float
    kind: str = "action"  # "action" | "follow_up"


@dataclass
class StatusSignal:
    status: str  # "done" | "in_progress" | "blocked"
    ts: datetime
    sender: Optional[str]
    text: str
    chat: str


@dataclass
class Outcome:
    text: str
    ts: datetime
    sender: Optional[str]
    chat: str


@dataclass
class ExtractionResult:
    actions: List[Action] = field(default_factory=list)
    signals: List[StatusSignal] = field(default_factory=list)
    outcomes: List[Outcome] = field(default_factory=list)


def _clean_title(raw: str) -> str:
    title = raw.strip()
    title = URL_RE.sub(lambda m: m.group(0), title)  # keep URLs verbatim
    title = re.sub(r"\s+", " ", title)
    title = title.strip(" \t.?!,;:-")
    title = re.sub(r"^(?:to|and|also)\s+", "", title, flags=re.I)
    if len(title) > 140:
        title = title[:137].rstrip() + "..."
    return title


def keywords(text: str) -> set:
    return {
        w
        for w in re.findall(r"[\w'-]+", text.lower())
        if len(w) > 3 and w not in STOPWORDS
    }


def similarity(a: str, b: str) -> float:
    """Keyword overlap with light prefix-stemming (booking ~ book)."""
    ka, kb = keywords(a), keywords(b)
    if not ka or not kb:
        return 0.0
    matches = sum(1 for w in ka if any(w[:4] == v[:4] for v in kb))
    return matches / min(len(ka), len(kb))


def _first_mention(text: str, exclude: Optional[str] = None) -> Optional[str]:
    for m in MENTION_RE.finditer(text):
        name = m.group(1)
        if exclude and name.lower() == exclude.lower():
            continue
        return name
    return None


def extract(messages: Iterable[Message]) -> ExtractionResult:
    result = ExtractionResult()
    for msg in messages:
        if msg.is_system or msg.is_noise:
            continue
        text = msg.text.strip()
        if not text:
            continue

        # Outcomes / decisions are recorded regardless of other matches.
        outcome_match = OUTCOME_RE.search(text)
        if outcome_match:
            result.outcomes.append(
                Outcome(text=_clean_title(text)[:280], ts=msg.timestamp, sender=msg.sender, chat=msg.chat)
            )
            # A message that *opens* with a decision verb ("Agreed to...",
            # "We decided...") is a record of the past, not a new task.
            if outcome_match.start() < 12:
                continue

        action = _extract_action(msg, text)
        if action:
            result.actions.append(action)
            continue

        # Only treat as a status signal when it isn't itself a new request.
        if DONE_RE.search(text) and len(text) < 200:
            result.signals.append(StatusSignal("done", msg.timestamp, msg.sender, text, msg.chat))
        elif BLOCKED_RE.search(text):
            result.signals.append(StatusSignal("blocked", msg.timestamp, msg.sender, text, msg.chat))
        elif PROGRESS_RE.search(text):
            result.signals.append(StatusSignal("in_progress", msg.timestamp, msg.sender, text, msg.chat))
        elif CHASE_RE.search(text):
            # Repeated chasing marks the referenced task as at-risk.
            result.signals.append(StatusSignal("chase", msg.timestamp, msg.sender, text, msg.chat))
    return result


def _extract_action(msg: Message, text: str) -> Optional[Action]:
    if QUESTION_ONLY_RE.match(text) and not MENTION_RE.search(text):
        return None
    # A pure completion report is not a new task.
    if DONE_RE.search(text) and not any(p.search(text) for p, _ in REQUEST_PATTERNS[:4]):
        if not ASSIGNMENT_RE.search(text):
            return None

    priority = "high" if URGENT_RE.search(text) else "normal"
    due = find_due_date(text, msg.timestamp)
    mention = _first_mention(text)

    # 1. Explicit assignment: "Bob will ..." / "@bob to ..."
    m = ASSIGNMENT_RE.search(text)
    if m:
        who = m.group("who").lstrip("@").strip()
        task = _clean_title(m.group("task"))
        if task and who.lower() not in NOT_A_NAME:
            assignee = msg.sender if who.lower() in ("i", "i'll") else who
            return Action(
                title=task, requester=msg.sender, assignee=assignee, due=due,
                priority=priority, chat=msg.chat, source_ts=msg.timestamp,
                source_sender=msg.sender, source_text=text, confidence=0.8,
            )

    # 2. First-person commitment: "I'll send the deck tomorrow"
    m = COMMITMENT_RE.search(text)
    if m:
        task = _clean_title(m.group("task"))
        if task and len(keywords(task)) >= 1:
            return Action(
                title=task, requester=msg.sender, assignee=msg.sender, due=due,
                priority=priority, chat=msg.chat, source_ts=msg.timestamp,
                source_sender=msg.sender, source_text=text, confidence=0.7,
            )

    # 3. Requests / reminders / follow-ups
    best = None
    for pattern, conf in REQUEST_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        task = _clean_title(m.group("task"))
        if not task or len(keywords(task)) == 0:
            continue
        if best is None or conf > best[1]:
            best = (task, conf, pattern)
    if best:
        task, conf, pattern = best
        kind = "follow_up" if "follow" in pattern.pattern else "action"
        return Action(
            title=task, requester=msg.sender, assignee=mention, due=due,
            priority=priority, chat=msg.chat, source_ts=msg.timestamp,
            source_sender=msg.sender, source_text=text, confidence=conf, kind=kind,
        )
    return None


def match_signal_to_task(signal: StatusSignal, open_tasks: Sequence[dict]) -> Optional[dict]:
    """Pick the open task a status signal most plausibly refers to.

    ``open_tasks`` are store rows (dicts with 'title', 'assignee', 'source_sender').
    Returns the best match or None.
    """
    scored = []
    for task in open_tasks:
        score = similarity(signal.text, task["title"])
        # A bare "done ✅" from the person the task is assigned to counts too.
        sender = (signal.sender or "").lower()
        involved = sender and sender in ((task.get("assignee") or "").lower(), (task.get("source_sender") or "").lower())
        if score == 0 and involved and len(keywords(signal.text)) <= 2:
            score = 0.45
        elif involved:
            score += 0.15
        if score > 0:
            scored.append((score, task))
    if not scored:
        return None
    scored.sort(key=lambda s: s[0], reverse=True)
    best_score, best_task = scored[0]
    return best_task if best_score >= 0.45 else None
