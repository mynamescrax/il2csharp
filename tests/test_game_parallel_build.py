"""`--workers N` must not change the tree, only the schedule.

The portable tests in `test_parallel_build.py` cover the arithmetic and the
declines with stubs; this one runs the real CLI over the fixture twice --
once serially, once across a process pool -- and requires the two output
trees to hash the same, file for file, with the same `bodies lifted` total in
the log. Two tiny images are enough: `_worker_count` keeps a single image
serial, so a one-image fixture would never engage the pool.

The images are deliberately trivial (`--only` on two 1-4 type modules) so
this stays a determinism test rather than a second full build.
"""
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.game

ROOT = Path(__file__).resolve().parents[1]
ONLY = 'Unity.Burst.Unsafe,UnityEngine.JSONSerializeModule'
# big enough that the chunked pool cuts one image into several slices
SPLIT_ONLY = 'Unity.Collections'


def _build(tmp_path, workers, only=ONLY):
    out = tmp_path / ('w%d%s' % (workers, '' if only == ONLY else '_split'))
    result = subprocess.run(
        [sys.executable, str(ROOT / 'il2csharp.py'), 'testgame',
         '-o', str(out), '--only', only, '--strict',
         '--workers', str(workers)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=900,
        env=dict(os.environ, PYTHONHASHSEED='0'))
    assert result.returncode == 0, result.stdout + result.stderr
    return out, result.stdout


def _tree(tree):
    return {p.relative_to(tree).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(tree.rglob('*')) if p.is_file()}


def _done_line(log):
    """The `done:` line with the elapsed time removed.

    Everything in it but the duration must match: file count, bodies
    lifted, failures, fallbacks, type-emission failures. The duration is
    the one field a pool is supposed to change, so comparing it verbatim
    would fail the very thing this test exists to prove.
    """
    line = next(l for l in log.splitlines() if l.startswith('done:'))
    return re.sub(r'in \d+ ms', 'in <t> ms', line)


def test_parallel_build_is_byte_identical_to_serial(tmp_path):
    serial, serial_log = _build(tmp_path, 1)
    parallel, parallel_log = _build(tmp_path, 2)
    assert 'workers: 2 processes' in parallel_log
    assert 'workers:' not in serial_log
    assert _tree(serial) == _tree(parallel)
    assert _tree(serial), 'the scoped build emitted nothing'
    assert _done_line(serial_log) == _done_line(parallel_log)


def test_scoped_parallel_build_engages_the_pool(tmp_path):
    _, log = _build(tmp_path, 3)
    assert 'workers: 3 processes' in log
    assert 'bodies lifted:' in _done_line(log)


def test_chunked_pool_splits_an_image_and_stays_byte_identical(tmp_path):
    """The pool hands out slices of one image's file plan, not whole images.

    `Unity.Collections*` is ~1,500 bodies over a few images: far more
    slices than images, so a file's neighbours are emitted by other
    processes and the `sub_<va>` stub class, the project file and the log
    still have to match the serial build exactly.
    """
    serial, serial_log = _build(tmp_path, 1, SPLIT_ONLY)
    parallel, parallel_log = _build(tmp_path, 2, SPLIT_ONLY)
    m = re.search(r'workers: 2 processes \| (\d+) images \| (\d+) slices', parallel_log)
    assert m, parallel_log
    images, slices = int(m.group(1)), int(m.group(2))
    assert slices > images >= 2
    assert _tree(serial) == _tree(parallel)
    assert any(k.endswith('__SharedBodyStubs.cs') for k in _tree(serial))
    assert any(k.endswith('.csproj') for k in _tree(serial))
    assert _done_line(serial_log) == _done_line(parallel_log)
