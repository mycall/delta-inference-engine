"""Launcher architecture regression tests; no downloads, compiler or GPU."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cpu_level
import get_engine


class CpuLevelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch.object(cpu_level, "ROOT", self.temp.name)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def build(self, folder, level=None):
        p = self.root / folder
        p.mkdir()
        (p / "ds41_generate.exe").write_bytes(cpu_level.ENGINE_MARK + cpu_level.UTF8_MARK)
        if level:
            (p / "cpu-level.txt").write_text(level, encoding="utf-8")

    def test_arm_is_not_sse(self):
        with patch.dict(os.environ, {"DS41_CPU_LEVEL": ""}), patch.object(cpu_level, "native_arm64", return_value=True):
            self.assertEqual(cpu_level.level(), "arm64")
            self.assertIsNone(cpu_level.release_zip())

    def test_arm_does_not_pick_x86_builds(self):
        for folder, floor in cpu_level.BUILDS:
            if floor != "arm64":
                self.build(folder, floor)
        with patch.dict(os.environ, {"DS41_CPU_LEVEL": "arm64"}):
            folder, why = cpu_level.pick_build()
            self.assertIsNone(folder)
            self.assertIn("ARM64", why)
            self.build("build-ds41-arm64", "arm64")
            self.assertEqual(cpu_level.pick_build(), ("build-ds41-arm64", None))

    def test_x86_does_not_pick_arm(self):
        self.build("build-ds41-arm64", "arm64")
        self.build("build-ds41-compat", "sse")
        with patch.dict(os.environ, {"DS41_CPU_LEVEL": "avx2"}):
            self.assertEqual(cpu_level.pick_build(), ("build-ds41-compat", None))

    def test_x86_release_selection_preserved(self):
        for level, name in [("sse", "compat"), ("avx", "compat-avx"),
                            ("avx2", "portable"), ("avx512", "portable")]:
            with self.subTest(level=level), patch.dict(os.environ, {"DS41_CPU_LEVEL": level}):
                self.assertEqual(cpu_level.release_zip(), f"build-ds41-{name}.zip")

    def test_arm_download_stops_before_network(self):
        with patch.dict(os.environ, {"DS41_CPU_LEVEL": "arm64"}), \
             patch.object(get_engine, "release_base", side_effect=AssertionError("release lookup")), \
             patch.object(get_engine, "download", side_effect=AssertionError("download")):
            self.assertEqual(get_engine.main(), 2)


if __name__ == "__main__":
    unittest.main()
