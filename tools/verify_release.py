"""Verify the replacement-folder checksums (standard library only).

Run from any directory: python path/to/il2csharp/tools/verify_release.py
Checks only files listed in SHA256SUMS.txt (kept in validation_reports/, with
a fallback to the tree root); extra local outputs are permitted.
Manifest paths stay relative to the verified tree, not to the manifest.
After intentionally editing source or output, mismatches are expected.
"""
import hashlib
from pathlib import Path
import sys


def find_manifest(root):
    """Prefer validation_reports/SHA256SUMS.txt; accept a root-level manifest."""
    for candidate in (root / 'validation_reports' / 'SHA256SUMS.txt',
                      root / 'SHA256SUMS.txt'):
        if candidate.is_file():
            return candidate
    raise SystemExit('no SHA256SUMS.txt found under ' + str(root))


def verify(root, manifest=None):
    root = Path(root).resolve()
    manifest = Path(manifest) if manifest else find_manifest(root)
    failures = []
    checked = 0
    for line in manifest.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        digest, relative = line.split('  ', 1)
        target = (root / relative).resolve()
        if not target.is_relative_to(root):
            failures.append(relative + ': invalid manifest path')
            continue
        try:
            with target.open('rb') as f:
                h = hashlib.sha256()
                for chunk in iter(lambda: f.read(1024 * 1024), b''):
                    h.update(chunk)
                actual = h.hexdigest()
        except OSError as error:
            failures.append(relative + ': ' + str(error))
            continue
        checked += 1
        if actual != digest:
            failures.append(relative + ': checksum mismatch')
    return checked, failures


if __name__ == '__main__':
    count, failures = verify(Path(__file__).resolve().parents[1])
    for failure in failures:
        print(failure)
    print(f'{count} files checked; {len(failures)} failures')
    sys.exit(1 if failures else 0)
