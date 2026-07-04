import unittest
from datetime import datetime

from watracker.parser import parse_export


class ParserTests(unittest.TestCase):
    def test_android_24h(self):
        msgs = parse_export("31/12/2023, 22:15 - Alice: Hello world", chat="c")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].timestamp, datetime(2023, 12, 31, 22, 15))
        self.assertEqual(msgs[0].sender, "Alice")
        self.assertEqual(msgs[0].text, "Hello world")

    def test_android_ampm(self):
        msgs = parse_export("12/31/23, 10:15 PM - Bob: hi")
        self.assertEqual(msgs[0].timestamp, datetime(2023, 12, 31, 22, 15))
        self.assertEqual(msgs[0].sender, "Bob")

    def test_ios_bracketed(self):
        msgs = parse_export("[31/12/2023, 22:15:42] Alice: Hello")
        self.assertEqual(msgs[0].timestamp, datetime(2023, 12, 31, 22, 15, 42))

    def test_system_message(self):
        msgs = parse_export("01/07/2026, 09:12 - Alice added Bob")
        self.assertTrue(msgs[0].is_system)

    def test_multiline_continuation(self):
        text = "01/07/2026, 09:12 - Alice: line one\nline two\nline three"
        msgs = parse_export(text)
        self.assertEqual(len(msgs), 1)
        self.assertIn("line two", msgs[0].text)
        self.assertIn("line three", msgs[0].text)

    def test_dayfirst_inference(self):
        # 13 in first position forces day-first for the whole file
        text = "13/01/2026, 09:00 - A: x\n05/01/2026, 09:00 - A: y"
        msgs = parse_export(text)
        self.assertEqual(msgs[1].timestamp.month, 1)
        self.assertEqual(msgs[1].timestamp.day, 5)

    def test_monthfirst_inference(self):
        # 13 in second position forces month-first
        text = "01/13/2026, 09:00 - A: x\n01/05/2026, 09:00 - A: y"
        msgs = parse_export(text)
        self.assertEqual(msgs[0].timestamp.month, 1)
        self.assertEqual(msgs[0].timestamp.day, 13)
        self.assertEqual(msgs[1].timestamp.day, 5)

    def test_noise_detection(self):
        msgs = parse_export("01/07/2026, 09:12 - Bob: <Media omitted>")
        self.assertTrue(msgs[0].is_noise)

    def test_message_with_colon_in_body(self):
        msgs = parse_export("01/07/2026, 09:12 - Alice: Note: check this link")
        self.assertEqual(msgs[0].sender, "Alice")
        self.assertEqual(msgs[0].text, "Note: check this link")


if __name__ == "__main__":
    unittest.main()
