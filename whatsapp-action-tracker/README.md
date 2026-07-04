# 📋 WhatsApp Action Tracker (`watracker`)

Automatically analyses WhatsApp group chats and DMs (exported `.txt` files, forwards included), extracts **actions, follow-ups, commitments and assignments**, tracks them in a local database, and generates **daily and weekly outstanding summaries** plus **key-outcomes status** reports — which it can post straight to **Slack** and sync with a Slack-based assignment tracker.

Pure Python 3.8+ standard library — **zero dependencies** to install. (An optional Claude-API mode improves extraction accuracy.)

```
WhatsApp export (.txt)                             ┌────────────────┐
        │                                     ┌──▶ │ daily report   │──┐
        ▼                                     │    ├────────────────┤  │   Slack
┌──────────────┐   ┌──────────────┐   ┌───────┴─┐  │ weekly report  │──┼─▶ webhook
│ parser       │──▶│ extractor    │──▶│ SQLite  │  ├────────────────┤  │
│ (both export │   │ actions      │   │ tracker │  │ status report  │──┘
│  formats)    │   │ follow-ups   │   └───────┬─┘  └────────────────┘
└──────────────┘   │ assignments  │           │
                   │ due dates    │           ▼  action-tracker-sync/v1 JSON
                   │ completions  │      export / import  ◀──▶  Slack assignment
                   │ decisions    │                             tracker (sibling
                   └──────────────┘                             project)
```

## Quick start

```bash
cd whatsapp-action-tracker

# 1. Export a chat from WhatsApp (chat ⋮ menu → More → Export chat → Without media)
# 2. Ingest it — actions, assignees, due dates and completions are detected
python3 -m watracker ingest "WhatsApp Chat with Launch Team.txt"

# 3. See what's outstanding
python3 -m watracker list

# 4. Generate summaries
python3 -m watracker report daily
python3 -m watracker report weekly
python3 -m watracker report status        # key-outcomes snapshot on demand
```

Try it immediately with the bundled sample:

```bash
python3 -m watracker --db /tmp/demo.db ingest samples/sample_chat.txt --chat "Launch Team"
python3 -m watracker --db /tmp/demo.db report daily --date 2026-07-03
```

## What gets detected

| Signal | Example message | Result |
|---|---|---|
| Request | "Please send the pricing deck **by Friday**" | Task with due date |
| Mention assignment | "@Priya please review the copy, **it's urgent**" | Task → Priya, high priority |
| Named assignment | "**Bob will** send the final report on Monday" | Task → Bob |
| Commitment | "**I'll** book the venue by end of the week" | Task → sender |
| Reminder | "**Don't forget to** update the FAQ" | Task |
| Follow-up | "Need to **follow up with** the vendor" | Follow-up item |
| Completion | "Pricing deck sent ✅" / "done" | Matching open task → **done** |
| Progress / blocker | "working on it" / "stuck, **waiting on** vendor" | Status → in progress / blocked |
| Decision | "**We decided** to launch July 15" / "**Agreed to** …" | Key outcome record |

Due-date phrases are resolved against the message timestamp: `today`, `EOD`, `tomorrow`, `by Friday`, `next Tuesday`, `end of week/month`, `in 3 days`, `15/07`, `July 9th`, …

Both Android (`31/12/23, 22:15 - Name: …`) and iOS (`[31/12/23, 10:15:42 PM] Name: …`) export formats are handled, with automatic day-first/month-first inference (`--date-order dmy|mdy` to force).

## Commands

```text
watracker ingest FILE [--chat NAME] [--date-order auto|dmy|mdy] [--ai]
watracker list [--status open|in_progress|blocked|done|cancelled] [--assignee X] [--chat Y]
watracker add TITLE [--assignee X] [--due YYYY-MM-DD] [--high]
watracker done|start|block|cancel|reopen ID
watracker report daily|weekly|status [--date YYYY-MM-DD] [--out FILE] [--post-slack] [--webhook URL]
watracker export [--out FILE]          # action-tracker-sync/v1 JSON
watracker import FILE                  # merge tasks from another tracker
```

Global: `--db PATH` (default `~/.watracker/watracker.db`).

Re-ingesting a growing export is **idempotent** — tasks are deduplicated on a stable fingerprint of (chat, message timestamp, title).

## Slack integration

### 1. Post summaries to a Slack channel

Create an [incoming webhook](https://api.slack.com/messaging/webhooks) for your channel, then:

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T000/B000/XXXX"
python3 -m watracker report daily --post-slack
python3 -m watracker report weekly --post-slack
```

Markdown is converted to Slack mrkdwn and chunked under Slack's message-size limit.

### 2. Sync with the Slack assignment tracker

`watracker` speaks a platform-neutral exchange format, **`action-tracker-sync/v1`**, designed to be shared with the Slack assignment tracker built in the sibling session (and any other tool). Both sides read and write the same schema, so the two trackers converge on a single task list:

```bash
# publish WhatsApp-sourced tasks for the Slack tracker to import
python3 -m watracker export --out sync/whatsapp-tasks.json

# merge tasks (and completions) produced by the Slack tracker
python3 -m watracker import sync/slack-tasks.json
```

Merge rules: unknown `uid`s are added; a remote `done`/`cancelled` status closes the local copy (a completion anywhere wins — the work happened). Everything else is left untouched, so repeated syncs are safe.

<details>
<summary><code>action-tracker-sync/v1</code> schema</summary>

```json
{
  "schema": "action-tracker-sync/v1",
  "source": "whatsapp",
  "generated_at": "2026-07-04T12:00:00",
  "tasks": [
    {
      "uid": "18df98eff7db1133",
      "title": "send the final pricing deck to the client",
      "assignee": "Bob",
      "requester": "Alice",
      "status": "open",
      "due": "2026-07-03",
      "priority": "normal",
      "channel": "Launch Team",
      "kind": "action",
      "created_at": "2026-07-01T09:16:00",
      "completed_at": null,
      "origin": {
        "platform": "whatsapp",
        "sender": "Alice",
        "timestamp": "2026-07-01T09:16:00",
        "text": "Bob will send the final pricing deck to the client by Friday"
      }
    }
  ]
}
```

`status` ∈ `open | in_progress | blocked | done | cancelled` · `priority` ∈ `normal | high` · `kind` ∈ `action | follow_up`.
</details>

## Regular summaries on a schedule

**cron** (see `examples/crontab.example`):

```cron
# daily digest at 08:00, weekly wrap-up Friday 17:00 — posted to Slack
0 8 * * *   cd ~/tracker && python3 -m watracker report daily  --post-slack
0 17 * * 5  cd ~/tracker && python3 -m watracker report weekly --post-slack
```

**GitHub Actions**: `examples/github-action.yml` is a ready-made scheduled workflow — copy it to `.github/workflows/`, commit your exports (or fetch them in a step), and add a `SLACK_WEBHOOK_URL` repository secret.

## Optional: Claude-powered extraction

The default extractor is rule-based and dependency-free. For messier chats (mixed languages, implicit assignments), `--ai` sends the transcript to the Claude API (model `claude-opus-4-8`) with a strict JSON schema and merges the results into the same tracker:

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
python3 -m watracker ingest chat.txt --ai
```

## Getting chats out of WhatsApp

- **Chat export (recommended, used here):** WhatsApp → chat → ⋮ → *More* → *Export chat* → *Without media*. Works for groups and DMs; forwards arrive as ordinary messages and are analysed like any other text.
- **Automation note:** WhatsApp's terms don't allow scraping the app; for continuous ingestion, use the official [WhatsApp Business Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api) webhooks and feed each message into `parse_export`/`extract` — the pipeline is format-agnostic once you have `Message` objects.

## Development

```bash
python3 -m unittest discover -s tests -v   # 37 tests, no dependencies
```

Layout: `parser.py` (export formats) → `extractor.py` (+ `dates.py`) → `store.py` (SQLite) → `reports.py` / `slack.py` (outputs & sync) → `cli.py`; `ai.py` is the optional Claude extractor.
