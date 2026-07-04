"""Tests for the nudge engine, GitHub sync, calendar feed, dashboard,
webhook payload handling, per-assignee digests, chase detection and
multilingual extraction."""

import json
import unittest
from datetime import date, datetime, timedelta
from unittest import mock

from watracker.cli import apply_extraction
from watracker.dashboard import build_dashboard
from watracker.extractor import extract
from watracker.github_sync import sync as github_sync
from watracker.ics import build_ics
from watracker.nudge import build_nudges, format_nudges, send_nudges
from watracker.parser import Message
from watracker.reports import all_digests, assignee_digest, daily_report
from watracker.store import Store
from watracker.webhook import messages_from_payload

TS = datetime(2026, 7, 1, 9, 0)


def msg(text, sender="Alice", ts=TS):
    return Message(timestamp=ts, sender=sender, text=text, chat="Team")


class NudgeTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.today = date(2026, 7, 10)

    def tearDown(self):
        self.store.close()

    def test_overdue_nudge_and_escalation(self):
        self.store.add_task("send the pricing deck", assignee="Bob", requester="Alice",
                            due=date(2026, 7, 5), source_ts=TS)
        nudges = build_nudges(self.store, today=self.today)
        self.assertEqual(len(nudges), 1)
        self.assertEqual(nudges[0].assignee, "Bob")
        self.assertIn("5 days overdue", nudges[0].lines[0])
        self.assertTrue(nudges[0].escalations)  # 5d > 3d escalation threshold
        self.assertIn("Alice", nudges[0].escalations[0])

    def test_blocked_and_stale(self):
        tid = self.store.add_task("book the venue", assignee="Chen", source_ts=TS)
        self.store.update_status(tid, "blocked")
        self.store.add_task("tidy the wiki", assignee="Dana",
                            source_ts=TS - timedelta(days=20))
        nudges = {n.assignee: n for n in build_nudges(self.store, today=self.today)}
        self.assertIn("blocked", nudges["Chen"].lines[0])
        self.assertIn("no due date", nudges["Dana"].lines[0])

    def test_rate_limiting(self):
        tid = self.store.add_task("send the deck", assignee="Bob", due=date(2026, 7, 5), source_ts=TS)
        self.store.mark_nudged(tid, when=datetime(2026, 7, 10, 8, 0).isoformat())
        nudges = build_nudges(self.store, today=self.today, now=datetime(2026, 7, 10, 9, 0))
        self.assertEqual(nudges, [])  # nudged an hour ago, min interval 20h

    def test_send_marks_nudged(self):
        tid = self.store.add_task("send the deck", assignee="Bob", due=date(2026, 7, 5), source_ts=TS)
        with mock.patch("watracker.slack.post_to_slack") as post:
            text = send_nudges(self.store, webhook_url="https://hooks.example/x",
                               today=self.today)
        self.assertTrue(post.called)
        self.assertIn("Bob", text)
        self.assertIsNotNone(self.store.get(tid)["last_nudged_at"])

    def test_format_empty(self):
        self.assertIn("All caught up", format_nudges([]))


class ChaseAndMultilingualTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def tearDown(self):
        self.store.close()

    def test_chase_marks_at_risk(self):
        msgs = [
            msg("Bob will send the pricing deck by Friday"),
            msg("any update on the pricing deck?", ts=TS + timedelta(days=2)),
            msg("gentle reminder on the pricing deck", ts=TS + timedelta(days=3)),
        ]
        apply_extraction(self.store, extract(msgs))
        task = self.store.tasks(open_only=True)[0]
        self.assertEqual(task["chases"], 2)
        report = daily_report(self.store, on=date(2026, 7, 4))
        self.assertIn("at risk", report)

    def test_spanish_request(self):
        r = extract([msg("Por favor envía el informe mañana")])
        self.assertEqual(len(r.actions), 1)
        self.assertIn("informe", r.actions[0].title)
        self.assertEqual(r.actions[0].due, date(2026, 7, 2))  # "mañana" -> tomorrow

    def test_hinglish_request_and_done(self):
        r = extract([msg("presentation bhej do by Friday", sender="Alice")])
        self.assertEqual(len(r.actions), 1)
        self.assertIn("presentation", r.actions[0].title.lower())
        r2 = extract([msg("presentation bhej diya", sender="Bob")])
        self.assertTrue(any(s.status == "done" for s in r2.signals))

    def test_french_request(self):
        r = extract([msg("Peux-tu partager le rapport tomorrow")])
        self.assertEqual(len(r.actions), 1)


class GitHubSyncTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def tearDown(self):
        self.store.close()

    def test_full_cycle(self):
        open_id = self.store.add_task("update the FAQ", assignee="Priya", source_ts=TS)
        done_id = self.store.add_task("send the deck", source_ts=TS + timedelta(minutes=1))
        self.store.set_external_ref(done_id, "github:7")
        self.store.update_status(done_id, "done")
        remote_id = self.store.add_task("review PR checklist", source_ts=TS + timedelta(minutes=2))
        self.store.set_external_ref(remote_id, "github:9")

        calls = []

        def fake_request(method, url, token, body=None):
            calls.append((method, url, body))
            if method == "POST" and url.endswith("/issues"):
                return {"number": 42}
            if method == "GET" and "/issues/7" in url:
                return {"number": 7, "state": "open"}
            if method == "GET" and "state=closed" in url:
                return [{"number": 9, "closed_at": "2026-07-03T10:00:00Z"}]
            return {}

        with mock.patch("watracker.github_sync._request", side_effect=fake_request):
            counts = github_sync(self.store, "owner/repo", token="t")

        self.assertEqual(counts, {"created": 1, "closed": 1, "pulled": 1})
        self.assertEqual(self.store.get(open_id)["external_ref"], "github:42")
        self.assertEqual(self.store.get(remote_id)["status"], "done")
        self.assertTrue(any(m == "PATCH" and "/issues/7" in u for m, u, _ in calls))

    def test_missing_token(self):
        from watracker.github_sync import GitHubError

        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(GitHubError):
                github_sync(self.store, "owner/repo", token=None)


class CalendarDashboardDigestTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.store.add_task("send the deck", assignee="Bob", due=date(2026, 7, 3),
                            priority="high", source_ts=TS)
        tid = self.store.add_task("review copy", assignee="Priya", due=date(2026, 7, 2), source_ts=TS)
        self.store.update_status(tid, "done")
        self.store.add_outcome("Agreed to launch July 15", TS, chat="Team", sender="Chen")

    def tearDown(self):
        self.store.close()

    def test_ics(self):
        ics = build_ics(self.store, now=datetime(2026, 7, 1, 12, 0))
        self.assertIn("BEGIN:VCALENDAR", ics)
        self.assertEqual(ics.count("BEGIN:VEVENT"), 2)
        self.assertIn("DTSTART;VALUE=DATE:20260703", ics)
        self.assertIn("STATUS:COMPLETED", ics)
        open_only = build_ics(self.store, open_only=True, now=datetime(2026, 7, 1, 12, 0))
        self.assertEqual(open_only.count("BEGIN:VEVENT"), 1)

    def test_dashboard(self):
        html_doc = build_dashboard(self.store, today=date(2026, 7, 4))
        self.assertIn("send the deck", html_doc)
        self.assertIn("Agreed to launch July 15", html_doc)
        self.assertIn("⚠️", html_doc)  # overdue flag
        self.assertIn("<!doctype html>", html_doc)

    def test_digests(self):
        digests = all_digests(self.store, on=date(2026, 7, 4))
        self.assertEqual(list(digests), ["Bob"])
        self.assertIn("Overdue", digests["Bob"])
        empty = assignee_digest(self.store, "Nobody", on=date(2026, 7, 4))
        self.assertIn("Nothing on your plate", empty)


class WebhookTests(unittest.TestCase):
    def test_payload_conversion(self):
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "metadata": {"display_phone_number": "15550001111"},
                        "contacts": [{"wa_id": "4477", "profile": {"name": "Alice"}}],
                        "messages": [
                            {"from": "4477", "timestamp": str(int(TS.timestamp())),
                             "type": "text", "text": {"body": "Please update the FAQ by Friday"}},
                            {"from": "4477", "timestamp": "0", "type": "image"},
                        ],
                    }
                }]
            }]
        }
        msgs = messages_from_payload(payload)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].sender, "Alice")
        self.assertIn("FAQ", msgs[0].text)
        # and it flows through the pipeline
        store = Store(":memory:")
        try:
            counts = apply_extraction(store, extract(msgs))
            self.assertEqual(counts["added"], 1)
        finally:
            store.close()

    def test_empty_payload(self):
        self.assertEqual(messages_from_payload({}), [])
        self.assertEqual(messages_from_payload(json.loads("{}")), [])


if __name__ == "__main__":
    unittest.main()
