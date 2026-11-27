#!/usr/bin/env python3
"""`architecture_public.reason` cuts every host path to its last name, wherever it sits (og-dev-hub#10).

Run from the repository root:
    python3 tests/project-site/test_host_path_scrub.py
"""

from __future__ import annotations

import re
import unittest

from project_site import architecture_public

LEFT = re.compile(r"(?<!:/)(?<![\w.~-])/data/|file:/|(?<=:)/(?!/)", re.IGNORECASE)


class Reason(unittest.TestCase):
    def test_a_host_path_is_cut_wherever_it_is(self) -> None:
        for raw, expected in (
            ("/data/x/y.json at the start", "…/y.json at the start"),
            ("see /data/x/y.json", "see …/y.json"),
            ("'/data/x/y.json'", "'…/y.json'"),
            ('"/data/x/y.json"', '"…/y.json"'),
            ("receipt:/data/x/y.json", "receipt:…/y.json"),
            ("https://h/?f=/data/x/y.json", "https://h/?f=…/y.json"),
            ("file:///data/x/y.json", "…/y.json"),
            ("a;/data/x/y.json", "a;…/y.json"),
            ("file:///tmp/work/foo", "…/foo"),
            ("see file:///home/u/a b", "see …/a b"),
            ("see file://localhost/private/log.txt", "see …/log.txt"),
            ("FILE://build-host/private/log.txt?path=/tmp/other", "…/log.txt"),
            ("see file:///", "see …"),
            ("receipt:/tmp/work/x", "receipt:…/x"),
            ("see:/home/u/secret", "see:…/secret"),
            ("see file:/tmp/work/x", "see …/x"),
            ("FILE:/tmp/work/log.txt?path=/tmp/other", "…/log.txt"),
            ("clone at /home/u/repo.git failed", "clone at …/repo.git failed"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(architecture_public.reason(raw), expected)
                self.assertIsNone(LEFT.search(architecture_public.reason(raw)))

    def test_a_relative_path_and_a_url_are_kept(self) -> None:
        for kept in ("from resources/data/derived/x.tsv", "https://github.com/opengwas/opengwasdb-stores/blob/abc/stores/ld/x.yaml",
                     "https://example.org/tmp/work/x", "https://data/archive/x", "ogld#7", "a/b/c"):
            with self.subTest(kept=kept):
                self.assertEqual(architecture_public.reason(kept), kept)

    def test_scrubbing_twice_changes_nothing_more(self) -> None:
        once = architecture_public.reason("Built from /data/x/receipt.json (log:/data/y/log.txt)")
        self.assertEqual(architecture_public.reason(once), once)
        self.assertNotIn("……", once)

    def test_a_value_that_is_not_text_is_returned_as_it_is(self) -> None:
        self.assertEqual(architecture_public.reason(5), 5)
        self.assertIsNone(architecture_public.reason(None))


if __name__ == "__main__":
    unittest.main()
