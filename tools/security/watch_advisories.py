"""Read published llama.cpp advisories; retain local changes for operator review."""
import datetime
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'logs' / 'advisory-monitor'


def poll():
    advisories = []
    for page in range(1, 21):
        request = urllib.request.Request(
            f'https://api.github.com/repos/ggml-org/llama.cpp/security-advisories?per_page=100&page={page}',
            headers={'User-Agent': 'Delta-local-advisory-monitor', 'Accept': 'application/vnd.github+json'})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            raise ValueError('Advisory response exceeds bound')
        batch = json.loads(data)
        if not isinstance(batch, list):
            raise ValueError('Unexpected advisory response')
        advisories.extend(batch)
        if len(batch) < 100:
            break
    else:
        raise ValueError('Advisory pagination exceeded bound')
    return advisories


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    at = datetime.datetime.now(datetime.timezone.utc)
    stamp = at.strftime('%Y%m%dT%H%M%S%fZ')
    previous_path = OUTPUT / 'latest.json'
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
    try:
        advisories = poll()
        fingerprints = {item['ghsa_id']: hashlib.sha256(json.dumps(item, sort_keys=True,
            separators=(',', ':')).encode()).hexdigest() for item in advisories}
        if len(fingerprints) != len(advisories):
            raise ValueError('Duplicate advisory identity')
        old = previous.get('fingerprints', {})
        changes = [dict(ghsa=key, kind='changed' if key in old else 'new',
                        url=item['html_url'], severity=item.get('severity'))
                   for item in advisories if old.get(key := item['ghsa_id']) != fingerprints[key]]
        # First observation is deliberately review-required: an earlier dated
        # review is not proof that today's advisory content is identical.
        pending = {item['ghsa']: item for item in previous.get('pending_review', [])}
        pending.update({item['ghsa']: item for item in changes})
        reviewed_path = ROOT / 'tools/security/advisory-reviewed.json'
        reviewed = json.loads(reviewed_path.read_text()).get('fingerprints', {}) if reviewed_path.exists() else {}
        # A review acknowledges exact advisory content only. Any later update
        # changes its fingerprint and returns it to the pending list.
        pending = {key: value for key, value in pending.items()
                   if reviewed.get(key) != fingerprints.get(key)}
        report = dict(schema=1, at=at.isoformat(), status='review_required' if pending else 'unchanged',
                      count=len(advisories), changes=changes, pending_review=list(pending.values()),
                      fingerprints=fingerprints, scope='Published advisories only; applicability requires patch/source review')
        (OUTPUT / (stamp + '-advisories.json')).write_text(json.dumps(advisories, indent=2) + '\n')
        (OUTPUT / (stamp + '-report.json')).write_text(json.dumps(report, indent=2) + '\n')
        temporary = OUTPUT / 'latest.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(previous_path)
        print(json.dumps({key: report[key] for key in ('status', 'count', 'changes')}))
        return 0
    except Exception as error:
        # Preserve the last successful snapshot and all outstanding findings.
        report = dict(schema=1, at=at.isoformat(), status='error', error=str(error))
        (OUTPUT / (stamp + '-error.json')).write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
