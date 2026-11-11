"""Chunked process pool: slices of one image's file plan per job.

Per-file emission reads nothing another file wrote. What lives outside a
type file -- the `sub_<va>` stub class, the `--raw-addr` helper, the
.csproj -- is written once per image by the parent from what each slice
returns. These tests drive the parent-side logic with an in-process fake
executor and a stub emitter (no processes, no fixture); the byte-identity
proof against a serial build is the game test.
"""
from concurrent.futures import Future
from types import SimpleNamespace as NS

import pytest

import il2cpp.cli as cli
from il2cpp.cli import _chunk_ranges, _emit_assemblies, _worker_emit_chunk


# ------------------------------------------------------------ _chunk_ranges

def _covers(ranges, n):
    flat = [i for lo, hi in ranges for i in range(lo, hi)]
    return flat == list(range(n))


def test_chunk_ranges_cover_every_index_once_in_order():
    for ws in ([1] * 10, [5, 1, 1, 9, 2], [100], [3, 3, 3, 3], list(range(1, 30))):
        for target in (1, 2, 5, 7, 50, 10_000):
            r = _chunk_ranges(ws, target)
            assert _covers(r, len(ws)), (ws, target, r)


def test_chunk_ranges_close_at_the_target():
    assert _chunk_ranges([1] * 10, 3) == [(0, 3), (3, 6), (6, 9), (9, 10)]
    assert _chunk_ranges([2, 2, 2, 2], 4) == [(0, 2), (2, 4)]


def test_a_heavy_item_is_its_own_range_and_never_splits():
    assert _chunk_ranges([1, 1, 500, 1, 1], 10) == [(0, 3), (3, 5)]
    assert _chunk_ranges([500, 500], 10) == [(0, 1), (1, 2)]


def test_chunk_ranges_edge_cases():
    assert _chunk_ranges([], 10) == []
    assert _chunk_ranges([4], 10) == [(0, 1)]
    assert _chunk_ranges([1, 1, 1], 10_000) == [(0, 3)]
    assert _chunk_ranges([1, 1, 1], 1) == [(0, 1), (1, 2), (2, 3)]


# ------------------------------------------------------------ stubs

class _Emitter:
    """Counts like the real Emitter and records every call."""

    def __init__(self, plans, boom_on=None, lifter=True):
        self.plans = plans                       # image name -> [(td, base)]
        self.boom_on = boom_on                   # base name that raises
        self.lifter = object() if lifter else None
        self.lifted = self.failed = self.fallbacks = self.emit_failed = 0
        self.emitted = []
        self.tails = []

    def _plan_top_files(self, img):
        return list(self.plans[img.name])

    def _top_weight(self, td):
        return td.w

    def _emit_one_top(self, td, img, base):
        if base == self.boom_on:
            raise RuntimeError('boom ' + base)
        self.emitted.append((img.name, base))
        self.lifted += td.w
        return {'sub_%s_%s' % (img.name, base)}, td.raw

    def write_assembly_tail(self, img, subs, raw):
        self.tails.append((img.name, set(subs), raw, len(self.emitted)))
        return 2


def _td(w, raw=False):
    return NS(w=w, raw=raw)


def _plan(name, spec):
    return [(_td(w, raw), '%s_t%d' % (name, i)) for i, (w, raw) in enumerate(spec)]


class _FakePool:
    """Runs each submitted job inline, in submission order."""
    submitted = []

    def __init__(self, max_workers=None, initializer=None, initargs=()):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def submit(self, fn, *args):
        type(self).submitted.append(args)
        fut = Future()
        try:
            fut.set_result(fn(*args))
        except BaseException as ex:          # a real pool re-raises at .result()
            fut.set_exception(ex)
        return fut


@pytest.fixture
def pool(monkeypatch):
    import concurrent.futures
    _FakePool.submitted = []
    monkeypatch.setattr(concurrent.futures, 'ProcessPoolExecutor', _FakePool)
    return _FakePool


def _args(**kw):
    base = dict(workers=4, max_methods=None, asm=False, decls_only=False,
                verbose=False, types=None, out='out', quiet=False, bodies=None,
                publicize=False, raw_addr=False)
    base.update(kw)
    return NS(**base)


def _setup(monkeypatch, em):
    monkeypatch.setattr(cli, '_W', {'em': em, 'meta': NS(images=IMAGES)},
                        raising=False)


IMAGES = [NS(name='big.dll'), NS(name='small.dll'), NS(name='empty.dll')]


def _stub(**kw):
    plans = {
        # target = max(25, 90 // 64) = 25: big splits into slices of 30 / 30 / 5
        'big.dll': _plan('big', [(30, False), (30, True), (5, False), (5, False)]),
        'small.dll': _plan('small', [(10, False)]),
        'empty.dll': [],
    }
    return _Emitter(plans, **kw)


# ------------------------------------------------------------ parent logic

def test_every_file_is_emitted_exactly_once(pool, monkeypatch):
    em = _stub()
    _setup(monkeypatch, em)
    stats = _emit_assemblies(IMAGES, em, _args(), 'gmd', 'bp')
    names = [b for _img, b in em.emitted]
    assert sorted(names) == sorted(['big_t0', 'big_t1', 'big_t2', 'big_t3', 'small_t0'])
    assert len(names) == len(set(names))
    assert stats['errors'] == []


def test_tail_runs_once_per_image_after_all_its_slices(pool, monkeypatch):
    em = _stub()
    _setup(monkeypatch, em)
    _emit_assemblies(IMAGES, em, _args(), 'gmd', 'bp')
    assert [t[0] for t in em.tails] == ['big.dll', 'small.dll', 'empty.dll']
    by_img = {t[0]: t for t in em.tails}
    # big's tail sees the union of every slice's stubs and the raw flag of slice 2
    assert by_img['big.dll'][1] == {'sub_big.dll_big_t%d' % i for i in range(4)}
    assert by_img['big.dll'][2] is True
    assert by_img['small.dll'][2] is False
    assert by_img['empty.dll'][1] == set()          # no files still gets its project


def test_counters_sum_in_image_order_like_the_serial_log(pool, monkeypatch, capsys):
    em = _stub()
    _setup(monkeypatch, em)
    stats = _emit_assemblies(IMAGES, em, _args(), 'gmd', 'bp')
    assert stats['lifted'] == 30 + 30 + 5 + 5 + 10
    assert stats['files'] == (4 + 2) + (1 + 2) + (0 + 2)   # emitted files + tail files
    out = capsys.readouterr().out.splitlines()
    rows = [l for l in out if l.startswith('  ') and 'bodies' in l]
    assert [r.split()[0] for r in rows] == ['big.dll', 'small.dll', 'empty.dll']
    assert '(70 bodies, 0 failed)' in rows[0] and '(80 bodies, 0 failed)' in rows[1]
    assert '(80 bodies, 0 failed)' in rows[2]
    assert any(l.startswith('workers: 4 processes | 3 images | ') and 'slices' in l for l in out)


def test_heaviest_slice_is_submitted_first(pool, monkeypatch):
    em = _stub()
    _setup(monkeypatch, em)
    _emit_assemblies(IMAGES, em, _args(), 'gmd', 'bp')
    weights = []
    for name, lo, hi, n in pool.submitted:
        plan = em.plans[name]
        weights.append(sum(plan[i][0].w for i in range(lo, hi)))
    assert weights == sorted(weights, reverse=True)


def test_a_failing_slice_is_reported_and_blocks_only_its_own_tail(pool, monkeypatch):
    em = _stub(boom_on='big_t2')
    _setup(monkeypatch, em)
    stats = _emit_assemblies(IMAGES, em, _args(), 'gmd', 'bp')
    assert len(stats['errors']) == 1
    assert stats['errors'][0].startswith('big.dll: ') and 'boom big_t2' in stats['errors'][0]
    assert [t[0] for t in em.tails] == ['small.dll', 'empty.dll']


def test_a_pool_level_failure_is_reported_per_image(pool, monkeypatch):
    class _Dying(_FakePool):
        def submit(self, fn, *args):
            fut = Future()
            fut.set_exception(RuntimeError('worker died'))
            return fut
    import concurrent.futures
    monkeypatch.setattr(concurrent.futures, 'ProcessPoolExecutor', _Dying)
    em = _stub()
    _setup(monkeypatch, em)
    stats = _emit_assemblies(IMAGES, em, _args(), 'gmd', 'bp')
    assert any('worker died' in e for e in stats['errors'])
    assert [t[0] for t in em.tails] == ['empty.dll']      # the only image with no slices


def test_missing_lifter_in_a_slice_is_reported(pool, monkeypatch):
    em = _stub(lifter=False)
    _setup(monkeypatch, em)
    stats = _emit_assemblies(IMAGES, em, _args(), 'gmd', 'bp')
    assert stats['lifter'] is False


def test_quiet_pool_prints_nothing(pool, monkeypatch, capsys):
    em = _stub()
    _setup(monkeypatch, em)
    _emit_assemblies(IMAGES, em, _args(quiet=True), 'gmd', 'bp')
    assert capsys.readouterr().out == ''


# ------------------------------------------------------------ the worker job

def test_worker_slice_reports_deltas_products_and_files(monkeypatch):
    em = _stub()
    _setup(monkeypatch, em)
    em.lifted = 1000                                   # a previous slice's total
    r = _worker_emit_chunk('big.dll', 1, 3, 4)
    assert (r['files'], r['lifted'], r['error']) == (2, 35, None)
    assert r['subs'] == ['sub_big.dll_big_t1', 'sub_big.dll_big_t2']
    assert r['raw'] is True and r['lifter'] is True
    assert [b for _i, b in em.emitted] == ['big_t1', 'big_t2']


def test_worker_slice_rejects_a_plan_the_parent_does_not_share(monkeypatch):
    em = _stub()
    _setup(monkeypatch, em)
    r = _worker_emit_chunk('big.dll', 0, 2, 3)
    assert 'plan mismatch' in r['error'] and em.emitted == []


def test_worker_slice_reports_a_missing_image(monkeypatch):
    em = _stub()
    _setup(monkeypatch, em)
    r = _worker_emit_chunk('nope.dll', 0, 1, 1)
    assert r['error'] and r['files'] == 0


def test_worker_slice_keeps_what_it_finished_when_a_file_raises(monkeypatch):
    em = _stub(boom_on='big_t1')
    _setup(monkeypatch, em)
    r = _worker_emit_chunk('big.dll', 0, 3, 4)
    assert 'RuntimeError' in r['error'] and r['files'] == 1
    assert r['subs'] == ['sub_big.dll_big_t0']


def test_worker_caches_the_plan_per_image(monkeypatch):
    em = _stub()
    _setup(monkeypatch, em)
    calls = []
    orig = em._plan_top_files
    em._plan_top_files = lambda img: calls.append(img.name) or orig(img)
    _worker_emit_chunk('big.dll', 0, 1, 4)
    _worker_emit_chunk('big.dll', 1, 2, 4)
    assert calls == ['big.dll']
