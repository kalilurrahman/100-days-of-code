"""watracker — WhatsApp action, task and assignment tracker.

Parses exported WhatsApp chats, extracts action items, follow-ups and
assignments, tracks them in a local SQLite database, and produces daily /
weekly outstanding summaries that can be posted to Slack or exchanged with
other trackers via a shared sync-JSON format.
"""

__version__ = "1.0.0"

SYNC_SCHEMA = "action-tracker-sync/v1"
