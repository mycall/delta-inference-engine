"""Host-memory sizing regression tests; no model files, downloads or GPU."""
import os
import unittest
from unittest.mock import patch

import ds41_local


class ArenaSizingTests(unittest.TestCase):
    def arena(self, ram_gib, **env):
        with patch.dict(os.environ, env, clear=True), \
             patch.object(ds41_local, "total_ram_gib", return_value=ram_gib):
            return ds41_local.arena_gib()

    def test_small_host_respects_default_reserve(self):
        # Windows reports only the host part after a dedicated GPU reservation.
        self.assertEqual(self.arena(32), 4)
        self.assertEqual(self.arena(30.5), 2)

    def test_existing_large_host_defaults(self):
        for ram_gib, expected in [(64, 36), (96, 68), (128, 100), (192, 140)]:
            with self.subTest(ram_gib=ram_gib):
                self.assertEqual(self.arena(ram_gib), expected)

    def test_custom_reserve_on_small_host(self):
        self.assertEqual(self.arena(32, DS41_RAM_RESERVE_GIB="20"), 12)

    def test_fixed_arena_keeps_explicit_value(self):
        self.assertEqual(self.arena(32, DS41_ARENA_GIB="12.5"), 12.5)
        self.assertEqual(self.arena(128, DS41_ARENA_GIB="64"), 64)
        self.assertEqual(self.arena(32, DS41_ARENA_GIB="29"), 29)

    def test_fixed_arena_requires_host_headroom(self):
        for ram_gib, fixed in [(30.5, "64"), (32, "30"), (128, "126")]:
            with self.subTest(ram_gib=ram_gib, fixed=fixed), self.assertRaises(SystemExit) as error:
                self.arena(ram_gib, DS41_ARENA_GIB=fixed)
            message = str(error.exception)
            self.assertIn(f"DS41_ARENA_GIB={fixed}", message)
            self.assertIn("host-visible physical RAM", message)
            self.assertIn("ds41-paths.bat", message)
            self.assertIn("reduce", message)


if __name__ == "__main__":
    unittest.main()
