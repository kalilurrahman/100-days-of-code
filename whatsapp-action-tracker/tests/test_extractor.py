import unittest
from datetime import date, datetime

from watracker.extractor import StatusSignal, extract, match_signal_to_task
from watracker.parser import Message

TS = datetime(2026, 7, 1, 9, 0)  # Wednesday


def msg(text, sender="Alice", ts=TS):
    return Message(timestamp=ts, sender=sender, text=text, chat="Team")


class ExtractorTests(unittest.TestCase):
    def test_please_request(self):
        r = extract([msg("Please send the pricing deck to the client by Friday")])
        self.assertEqual(len(r.actions), 1)
        a = r.actions[0]
        self.assertIn("pricing deck", a.title)
        self.assertEqual(a.due, date(2026, 7, 3))
        self.assertEqual(a.requester, "Alice")

    def test_mention_assignment(self):
        r = extract([msg("@Priya please review the landing page copy tomorrow, it's urgent")])
        self.assertEqual(len(r.actions), 1)
        a = r.actions[0]
        self.assertEqual(a.assignee, "Priya")
        self.assertEqual(a.priority, "high")
        self.assertEqual(a.due, date(2026, 7, 2))

    def test_named_assignment(self):
        r = extract([msg("Bob will send the final report on Monday")])
        self.assertEqual(len(r.actions), 1)
        self.assertEqual(r.actions[0].assignee, "Bob")

    def test_first_person_commitment(self):
        r = extract([msg("I'll book the venue by end of the week", sender="Chen")])
        self.assertEqual(len(r.actions), 1)
        self.assertEqual(r.actions[0].assignee, "Chen")
        self.assertIn("book the venue", r.actions[0].title)

    def test_reminder(self):
        r = extract([msg("Don't forget to update the FAQ section")])
        self.assertEqual(len(r.actions), 1)
        self.assertIn("update the FAQ", r.actions[0].title)

    def test_follow_up_kind(self):
        r = extract([msg("Need to follow up with the vendor about the invoice")])
        self.assertEqual(len(r.actions), 1)
        self.assertEqual(r.actions[0].kind, "follow_up")

    def test_outcome(self):
        r = extract([msg("We decided to go ahead with the July 15 launch")])
        self.assertEqual(len(r.outcomes), 1)

    def test_done_signal(self):
        r = extract([msg("Landing page copy reviewed and done ✅", sender="Priya")])
        self.assertEqual(len(r.actions), 0)
        self.assertEqual(len(r.signals), 1)
        self.assertEqual(r.signals[0].status, "done")

    def test_blocked_signal(self):
        r = extract([msg("Venue booking is stuck, waiting on the vendor")])
        self.assertTrue(any(s.status == "blocked" for s in r.signals))

    def test_smalltalk_ignored(self):
        r = extract([msg("Morning team!"), msg("haha nice one"), msg("<Media omitted>")])
        self.assertEqual(len(r.actions), 0)

    def test_question_ignored(self):
        r = extract([msg("What time is the meeting?")])
        self.assertEqual(len(r.actions), 0)

    def test_signal_matching_by_keywords(self):
        tasks = [
            {"id": 1, "title": "send the pricing deck to the client", "assignee": "Bob", "source_sender": "Alice"},
            {"id": 2, "title": "update the FAQ section", "assignee": None, "source_sender": "Alice"},
        ]
        sig = StatusSignal("done", TS, "Bob", "Pricing deck sent to the client ✅", "Team")
        match = match_signal_to_task(sig, tasks)
        self.assertIsNotNone(match)
        self.assertEqual(match["id"], 1)

    def test_bare_done_matches_assignee_task(self):
        tasks = [{"id": 7, "title": "review the landing page copy", "assignee": "Priya", "source_sender": "Alice"}]
        sig = StatusSignal("done", TS, "Priya", "done ✅", "Team")
        match = match_signal_to_task(sig, tasks)
        self.assertIsNotNone(match)

    def test_unrelated_done_no_match(self):
        tasks = [{"id": 9, "title": "prepare quarterly budget forecast", "assignee": "Bob", "source_sender": "Alice"}]
        sig = StatusSignal("done", TS, "Zed", "lunch order sent", "Team")
        self.assertIsNone(match_signal_to_task(sig, tasks))


if __name__ == "__main__":
    unittest.main()
