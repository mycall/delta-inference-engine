"""Durable review state must survive unchanged polls and network failures."""
import contextlib
import io
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import watch_advisories as monitor


class MonitorTests(unittest.TestCase):
    def test_exact_review_acknowledgement_reopens_on_content_change(self):
        item = dict(ghsa_id='GHSA-test-0000-0000', html_url='https://example.invalid/advisory', severity='high')
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            root = Path(temporary)
            review = root / 'tools/security/advisory-reviewed.json'
            review.parent.mkdir(parents=True)
            digest = hashlib.sha256(json.dumps(item, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            review.write_text(json.dumps({'fingerprints': {item['ghsa_id']: digest}}))
            with patch.object(monitor, 'ROOT', root), patch.object(monitor, 'OUTPUT', root / 'logs'):
                with patch.object(monitor, 'poll', return_value=[item]):
                    self.assertEqual(monitor.main(), 0)
                self.assertEqual(json.loads((root / 'logs/latest.json').read_text())['pending_review'], [])
                with patch.object(monitor, 'poll', return_value=[{**item, 'severity': 'critical'}]):
                    self.assertEqual(monitor.main(), 0)
                result = json.loads((root / 'logs/latest.json').read_text())
                self.assertEqual(result['status'], 'review_required')
                self.assertEqual(result['pending_review'][0]['severity'], 'critical')

    def test_changes_remain_pending_and_failure_preserves_success(self):
        item = dict(ghsa_id='GHSA-test-0000-0000', html_url='https://example.invalid/advisory', severity='high')
        with tempfile.TemporaryDirectory() as temporary, patch.object(monitor, 'OUTPUT', Path(temporary)), contextlib.redirect_stdout(io.StringIO()):
            with patch.object(monitor, 'poll', return_value=[item]):
                self.assertEqual(monitor.main(), 0)
                self.assertEqual(monitor.main(), 0)
            latest = Path(temporary) / 'latest.json'
            result = json.loads(latest.read_text())
            self.assertEqual(result['changes'], [])
            self.assertEqual(len(result['pending_review']), 1)
            before = latest.read_bytes()
            with patch.object(monitor, 'poll', side_effect=OSError('fixture offline')):
                self.assertEqual(monitor.main(), 1)
            self.assertEqual(latest.read_bytes(), before)
            self.assertEqual(len(list(Path(temporary).glob('*-error.json'))), 1)
            with patch.object(monitor, 'poll', return_value=[{**item, 'severity': 'critical'}]):
                self.assertEqual(monitor.main(), 0)
            result = json.loads(latest.read_text())
            self.assertEqual(result['changes'][0]['kind'], 'changed')
            self.assertEqual(result['pending_review'][0]['severity'], 'critical')

    def test_duplicate_advisories_cannot_replace_snapshot(self):
        item = dict(ghsa_id='GHSA-test-0000-0000', html_url='https://example.invalid/advisory')
        with tempfile.TemporaryDirectory() as temporary, patch.object(monitor, 'OUTPUT', Path(temporary)), contextlib.redirect_stdout(io.StringIO()):
            with patch.object(monitor, 'poll', return_value=[item, item]):
                self.assertEqual(monitor.main(), 1)
            self.assertFalse((Path(temporary) / 'latest.json').exists())


if __name__ == '__main__':
    unittest.main()
