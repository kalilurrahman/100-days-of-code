"""End-to-end tests: parse the sample chat -> extract -> store -> reports -> sync."""

import json
import os
import tempfile
import unittest
from datetime import date, datetime

from watracker.cli import apply_extraction
from watracker.extractor import extract
from watracker.parser import parse_file
from watracker.reports import daily_report, status_report, weekly_report
from watracker.slack import export_sync, import_sync, markdown_to_mrkdwn
from watracker.store import Store

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "samples", "sample_chat.txt")


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def tearDown(self):
        self.store.close()

    def _ingest_sample(self):
        messages = parse_file(SAMPLE, chat="Launch Team")
        result = extract(messages)
        return apply_extraction(self.store, result)

    def test_sample_ingest(self):
        counts = self._ingest_sample()
        self.assertGreaterEqual(counts["added"], 4)
        self.assertGreaterEqual(counts["outcomes"], 2)
        titles = [t["title"].lower() for t in self.store.tasks()]
        self.assertTrue(any("pricing deck" in t for t in titles))
        self.assertTrue(any("landing page" in t for t in titles))
        self.assertTrue(any("faq" in t for t in titles))

    def test_completion_closes_task(self):
        self._ingest_sample()
        done = [t for t in self.store.tasks(status="done")]
        done_titles = " ".join(t["title"].lower() for t in done)
        self.assertIn("pricing deck", done_titles)
        self.assertIn("landing page", done_titles)

    def test_reingest_is_idempotent(self):
        first = self._ingest_sample()
        second = self._ingest_sample()
        self.assertGreaterEqual(first["added"], 1)
        self.assertEqual(second["added"], 0)

    def test_reports_render(self):
        self._ingest_sample()
        daily = daily_report(self.store, on=date(2026, 7, 3))
        weekly = weekly_report(self.store, week_ending=date(2026, 7, 5))
        status = status_report(self.store)
        self.assertIn("Daily Action Summary", daily)
        self.assertIn("Weekly Action Report", weekly)
        self.assertIn("Tracker Status", status)
        self.assertIn("outstanding", daily)
        self.assertIn("Outstanding by assignee", weekly)

    def test_sync_round_trip(self):
        self._ingest_sample()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sync.json")
            export_sync(self.store, path=path)
            with open(path) as fh:
                doc = json.load(fh)
            self.assertEqual(doc["schema"], "action-tracker-sync/v1")
            self.assertEqual(len(doc["tasks"]), len(self.store.tasks()))

            other = Store(":memory:")
            try:
                counts = import_sync(other, path)
                self.assertEqual(counts["added"], len(doc["tasks"]))
                # second import is a no-op
                counts2 = import_sync(other, path)
                self.assertEqual(counts2["added"], 0)
            finally:
                other.close()

    def test_import_remote_completion_wins(self):
        self.store.add_task("ship the newsletter", uid="abc123", source_ts=datetime(2026, 7, 1, 9))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "slack.json")
            with open(path, "w") as fh:
                json.dump(
                    {
                        "schema": "action-tracker-sync/v1",
                        "source": "slack",
                        "tasks": [
                            {"uid": "abc123", "title": "ship the newsletter", "status": "done",
                             "completed_at": "2026-07-02T10:00:00"},
                            {"uid": "zzz999", "title": "post launch recap in #general", "status": "open",
                             "channel": "#launch"},
                        ],
                    },
                    fh,
                )
            counts = import_sync(self.store, path)
        self.assertEqual(counts["updated"], 1)
        self.assertEqual(counts["added"], 1)
        task = [t for t in self.store.tasks() if t["uid"] == "abc123"][0]
        self.assertEqual(task["status"], "done")

    def test_markdown_to_mrkdwn(self):
        out = markdown_to_mrkdwn("# Title\n- **bold** item\n~~gone~~")
        self.assertIn("*Title*", out)
        self.assertIn("• *bold* item", out)
        self.assertIn("~gone~", out)


if __name__ == "__main__":
    unittest.main()
