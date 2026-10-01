#!/usr/bin/env python3
"""Negative checks for corrupt assets, broken links, and mutable Action references."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

spec = importlib.util.spec_from_file_location("checks", Path(__file__).with_name("check-repository.py"))
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)


class ChecksTests(unittest.TestCase):
    def test_valid_png_and_corrupt_or_truncated_png(self):
        png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        png += chunk(b"IDAT", zlib.compress(b"\0\0\0\0")) + chunk(b"IEND", b"")
        checks.check_png(png)
        for bad in (b"not png", png[:-1], png[:-12], png + b"trailing", png[:30] + b"x" + png[31:]):
            with self.subTest(data=bad), self.assertRaises(ValueError):
                checks.check_png(bad)

    def test_local_links_require_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "target.md").write_text("target")
            checks.check_markdown(root / "README.md", "[valid](target.md#section) [external](https://example.com) [anchor](#section)")
            with self.assertRaises(ValueError):
                checks.check_markdown(root / "README.md", "[missing](missing.md)")

    def test_external_actions_require_full_shas(self):
        checks.check_actions("uses: actions/checkout@" + "a" * 40 + "\nuses: ./local-action")
        for reference in ("actions/checkout@v7", "actions/checkout@abc123", "actions/checkout@main"):
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                checks.check_actions("uses: " + reference)


if __name__ == "__main__":
    unittest.main()
