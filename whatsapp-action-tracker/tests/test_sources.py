import json
import os
import tempfile
import unittest
from datetime import date, datetime

from watracker.sources import load_messages, parse_email_file, parse_telegram_file, parse_vtt_file

EML = """\
From: Alice Smith <alice@example.com>
To: team@example.com
Date: Wed, 01 Jul 2026 09:16:00 +0000
Subject: Pricing deck
Content-Type: text/plain

Please send the final pricing deck to the client by Friday.

Thanks,
Alice

On Tue, 30 Jun 2026, Bob wrote:
> old quoted stuff that should be dropped
"""

VTT = """\
WEBVTT

00:00:01.000 --> 00:00:04.000
<v Alice>Bob will send the final report on Monday</v>

00:00:05.000 --> 00:00:08.000
<v Alice>and please update the FAQ before launch</v>

00:01:00.000 --> 00:01:03.000
Chen: I'll book the venue by end of the week
"""

TELEGRAM = {
    "name": "Launch Team",
    "messages": [
        {"id": 1, "type": "message", "date": "2026-07-01T09:14:00", "from": "Alice",
         "text": "Please review the landing page copy tomorrow"},
        {"id": 2, "type": "message", "date": "2026-07-01T09:15:00", "from": "Bob",
         "text": [{"type": "mention", "text": "@Priya"}, " can you share the analytics report"]},
        {"id": 3, "type": "service", "date": "2026-07-01T09:16:00", "action": "pin_message"},
    ],
}


class SourcesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, content, mode="w"):
        path = os.path.join(self.tmp.name, name)
        with open(path, mode, encoding=None if "b" in mode else "utf-8") as fh:
            fh.write(content)
        return path

    def test_eml(self):
        path = self._write("mail.eml", EML)
        msgs = parse_email_file(path)
        self.assertEqual(len(msgs), 1)
        m = msgs[0]
        self.assertEqual(m.sender, "Alice Smith")
        self.assertEqual(m.timestamp, datetime(2026, 7, 1, 9, 16))
        self.assertIn("pricing deck", m.text)
        self.assertIn("Pricing deck.", m.text)  # subject prepended
        self.assertNotIn("old quoted stuff", m.text)

    def test_vtt(self):
        path = self._write("meeting.vtt", VTT)
        msgs = parse_vtt_file(path, ref_date=date(2026, 7, 1))
        senders = [m.sender for m in msgs]
        self.assertIn("Chen", senders)
        alice = [m for m in msgs if m.sender == "Alice"]
        # consecutive close cues merged into one utterance
        self.assertEqual(len(alice), 1)
        self.assertIn("update the FAQ", alice[0].text)
        self.assertEqual(msgs[0].timestamp.date(), date(2026, 7, 1))

    def test_telegram(self):
        path = self._write("result.json", json.dumps(TELEGRAM))
        msgs = parse_telegram_file(path)
        self.assertEqual(len(msgs), 2)  # service message skipped
        self.assertEqual(msgs[0].chat, "Launch Team")
        self.assertIn("@Priya can you share", msgs[1].text)

    def test_dispatch_by_extension(self):
        path = self._write("result.json", json.dumps(TELEGRAM))
        msgs = load_messages(path)
        self.assertEqual(len(msgs), 2)
        path = self._write("mail.eml", EML)
        self.assertEqual(len(load_messages(path)), 1)


if __name__ == "__main__":
    unittest.main()
