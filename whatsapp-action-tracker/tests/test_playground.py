"""Guard: the playground's copies of the package must match the source.

If this fails, run ``playground/build.sh`` to refresh the copies.
"""

import os
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
SRC = os.path.join(ROOT, "watracker")
COPY = os.path.join(ROOT, "playground", "watracker")


class PlaygroundSyncTests(unittest.TestCase):
    def test_package_copies_in_sync(self):
        for name in sorted(os.listdir(SRC)):
            if not name.endswith(".py"):
                continue
            with self.subTest(file=name):
                copy_path = os.path.join(COPY, name)
                self.assertTrue(
                    os.path.exists(copy_path),
                    f"{name} missing from playground — run playground/build.sh",
                )
                with open(os.path.join(SRC, name)) as a, open(copy_path) as b:
                    self.assertEqual(
                        a.read(), b.read(),
                        f"{name} out of date in playground — run playground/build.sh",
                    )

    def test_sample_in_sync(self):
        with open(os.path.join(ROOT, "samples", "sample_chat.txt")) as a, \
                open(os.path.join(ROOT, "playground", "sample_chat.txt")) as b:
            self.assertEqual(a.read(), b.read())


if __name__ == "__main__":
    unittest.main()
