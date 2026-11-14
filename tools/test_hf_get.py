#!/usr/bin/env python3
"""Tests for tools/v41/serve/hf_get.py (the download runner) with a fake "hf" command - no network, no model files.
Run: python -m unittest tools.test_hf_get"""
import io
import json
import os
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "v41" / "serve"))
import hf_get  # noqa: E402

FAKE = textwrap.dedent(r'''
    import json, os, sys, time
    args = sys.argv[2:]                       # after "download"
    d = args[args.index("--local-dir") + 1]
    name = args[1]
    mode = os.environ["FAKE_MODE"]
    size = int(os.environ["FAKE_SIZE"])
    log = os.path.join(d, "calls.jsonl")
    calls = sum(1 for _ in open(log)) if os.path.exists(log) else 0
    with open(log, "a") as f:
        f.write(json.dumps({"xet_off": os.environ.get("HF_HUB_DISABLE_XET") == "1",
                            "bars_off": os.environ.get("HF_HUB_DISABLE_PROGRESS_BARS") == "1"}) + "\n")
    part = os.path.join(d, ".cache", "huggingface", "download")
    os.makedirs(part, exist_ok=True)
    def finish():
        with open(os.path.join(d, name), "wb") as f:
            f.write(b"x" * size)
        sys.exit(0)
    if mode == "ok":
        finish()
    if mode == "buffered":
        with open(os.path.join(part, "abc.incomplete"), "wb") as f:
            f.write(b"x" * 10)
        # Like Xet: work continues without growing either the file or the on-disk cache.
        time.sleep(3)
    if mode == "missing" and calls == 0:
        sys.exit(0)                           # "finished", nothing written
    if mode == "fail" and calls < int(os.environ.get("FAKE_FAILS", "1")):
        sys.exit(3)
    finish()
''')


class Item:
    def __init__(self, path, size):
        self.path, self.size = path, size


class FakeApi:
    def __init__(self, items):
        self.items = items

    def get_paths_info(self, repo, files, **kw):
        return [Item(p, n) for p, n in self.items if p in files]

    def list_repo_tree(self, repo, recursive=True, **kw):
        return [Item(p, n) for p, n in self.items]


class HfGetTest(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.fake = os.path.join(self.dir, "fake_hf.py")
        Path(self.fake).write_text(FAKE)
        self.models = os.path.join(self.dir, "models")
        os.makedirs(self.models)
        os.environ["DS41_NO_TOAST"] = "1"
        os.environ["DS41_NO_KEEPAWAKE"] = "1"
        os.environ.pop("HF_HUB_DISABLE_XET", None)
        os.environ["HF_XET_CACHE"] = os.path.join(self.dir, "xet")    # an empty Xet cache: only the folder moves

    def tearDown(self):
        self.tmp.cleanup()

    def run_fake(self, mode, size=1000, **env):
        os.environ.update({"FAKE_MODE": mode, "FAKE_SIZE": str(size), **{k: str(v) for k, v in env.items()}})
        out = io.StringIO()
        rc = hf_get.run(["org/repo", "model.gguf", "--local-dir", self.models], hf_cmd=[sys.executable, self.fake],
                        stall_s=1.5, poll_s=0.2, backoff=(0, 0, 0), api=FakeApi([("model.gguf", size)]), out=out)
        calls = [json.loads(x) for x in Path(self.models, "calls.jsonl").read_text().splitlines()]
        return rc, calls, out.getvalue()

    def test_ok(self):
        rc, calls, text = self.run_fake("ok")
        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0]["bars_off"])                 # our own progress line instead of hf's bars
        self.assertIn("(0.0 MB)", text)

    def test_buffered_transfer_is_not_restarted(self):
        # The pause exceeds stall_s=1.5; the original watchdog killed this live transfer.
        rc, calls, text = self.run_fake("buffered", DS41_STALL_MIN="0.001")
        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 1)
        self.assertFalse(calls[0]["xet_off"])
        self.assertNotIn("has not moved", text)
        self.assertEqual(Path(self.models, "model.gguf").stat().st_size, 1000)

    def test_exit_0_with_files_missing_is_retried(self):
        rc, calls, text = self.run_fake("missing")
        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 2)
        self.assertIn("not complete", text)

    def test_failures_retried_then_given_up(self):
        rc, calls, text = self.run_fake("fail", FAKE_FAILS=1)
        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 2)
        Path(self.models, "calls.jsonl").unlink()
        Path(self.models, "model.gguf").unlink()
        rc, calls, text = self.run_fake("fail", FAKE_FAILS=10)
        self.assertEqual(rc, 3)
        self.assertEqual(len(calls), 4)                      # the first try + one per back-off step
        self.assertTrue(calls[-1]["xet_off"])
        self.assertIn("did not work after several tries", text)


class PartsTest(unittest.TestCase):
    def test_parse(self):
        p = hf_get.parse(["unsloth/X", "--revision", "60ad", "--include", "UD-IQ1_S/*", "--local-dir", "D:/m"])
        self.assertEqual((p["repo"], p["revision"], p["include"], p["local_dir"], p["files"]),
                         ("unsloth/X", "60ad", ["UD-IQ1_S/*"], "D:/m", []))
        p = hf_get.parse(["a/b", "f1", "f2", "--local-dir=D"])
        self.assertEqual((p["files"], p["local_dir"]), (["f1", "f2"], "D"))

    def test_plan_include(self):
        api = FakeApi([("UD-IQ1_S/a.gguf", 5), ("UD-IQ1_S/b.gguf", 7), ("UD-Q2/c.gguf", 9)])
        p = hf_get.parse(["u/X", "--include", "UD-IQ1_S/*", "--local-dir", "."])
        self.assertEqual(hf_get.plan(p, api), [("UD-IQ1_S/a.gguf", 5), ("UD-IQ1_S/b.gguf", 7)])

    def test_plan_offline(self):
        class Broken:
            def get_paths_info(self, *a, **k):
                raise OSError("offline")
        self.assertIsNone(hf_get.plan(hf_get.parse(["a/b", "f", "--local-dir", "."]), Broken()))

    def test_words(self):
        self.assertEqual(hf_get.duration(30), "30 s")
        self.assertEqual(hf_get.duration(600), "10 min")
        self.assertEqual(hf_get.duration(4800), "1 h 20 min")
        line = hf_get.progress_line(142e9, 365.7e9, 45e6)
        self.assertEqual(line, "142.0 of 365.7 GB (38%) - 45 MB/s - about 1 h 23 min left")
        self.assertEqual(hf_get.progress_line(1e9, None, None), "1.0 GB so far")

    def test_rate(self):
        r = hf_get.Rate(window=10)
        self.assertIsNone(r.add(0, 0))
        self.assertEqual(r.add(4, 400), 100)
        self.assertEqual(r.add(20, 2000), 2000 / 20)        # the window keeps two points at least
        self.assertAlmostEqual(r.add(30, 3000), (3000 - 2000) / 10)


class DownloadCleanupTests(unittest.TestCase):
    def run_download(self, proc, failure=None):
        awake = Mock()
        with patch.object(hf_get, "plan", return_value=None), \
                patch.object(hf_get, "keep_awake", return_value=awake), \
                patch.object(hf_get.subprocess, "Popen", return_value=proc) as launch, \
                patch.object(hf_get.time, "sleep", side_effect=failure), \
                patch.object(hf_get, "_kill") as kill:
            if failure is not None:
                with self.assertRaises(type(failure)):
                    hf_get.run(["example/model"], hf_cmd=["hf"], out=io.StringIO())
                kill.assert_called_once_with(proc)
            else:
                self.assertEqual(hf_get.run(["example/model"], hf_cmd=["hf"], out=io.StringIO()), 0)
                kill.assert_not_called()
            awake.close.assert_called_once()
            expected = hf_get.subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            self.assertEqual(launch.call_args.kwargs["creationflags"], expected)

    def test_interrupt_stops_downloader(self):
        self.run_download(Mock(poll=Mock(return_value=None)), KeyboardInterrupt())

    def test_monitor_error_stops_downloader(self):
        self.run_download(Mock(poll=Mock(return_value=None)), OSError("monitor failed"))

    def test_success_does_not_kill_finished_process(self):
        self.run_download(Mock(poll=Mock(return_value=0), returncode=0))

    def test_launch_error_releases_keepawake(self):
        awake = Mock()
        with patch.object(hf_get, "plan", return_value=None), \
                patch.object(hf_get, "keep_awake", return_value=awake), \
                patch.object(hf_get.subprocess, "Popen", side_effect=OSError("launch failed")), \
                patch.object(hf_get, "_kill") as kill:
            with self.assertRaises(OSError):
                hf_get.run(["example/model"], hf_cmd=["hf"], out=io.StringIO())
            awake.close.assert_called_once()
            kill.assert_not_called()

    def test_progress_uses_transfer_bars_in_terminal(self):
        for terminal, disabled, native in [(True, "", True), (False, "", False), (True, "1", False)]:
            with self.subTest(terminal=terminal, disabled=disabled):
                out = io.StringIO()
                out.isatty = lambda: terminal
                proc = Mock(poll=Mock(side_effect=[None, 0, 0]), returncode=0)
                with patch.dict(os.environ, {"HF_HUB_DISABLE_PROGRESS_BARS": disabled}), \
                        patch.object(hf_get, "plan", return_value=None), \
                        patch.object(hf_get, "keep_awake", return_value=Mock()), \
                        patch.object(hf_get.subprocess, "Popen", return_value=proc) as launch, \
                        patch.object(hf_get.time, "sleep"), \
                        patch.object(hf_get, "done_bytes", return_value=400_000_000):
                    self.assertEqual(hf_get.run(["example/model"], hf_cmd=["hf"], out=out), 0)
                env = launch.call_args.kwargs["env"]
                self.assertEqual(env["HF_HUB_DISABLE_PROGRESS_BARS"], "0" if native else "1")
                # Do not overwrite the live transfer bars with a misleading disk-only speed.
                self.assertEqual("(disk)" in out.getvalue(), not native)


if __name__ == "__main__":
    unittest.main()
