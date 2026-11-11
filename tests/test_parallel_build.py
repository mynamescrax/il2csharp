"""`--workers`: the same tree from a process pool, and the combinations
that must decline to run in one.

An image owns its output directory, its `__SharedBodyStubs.cs` and its
`.csproj`, and reads nothing another image wrote, so the emitted tree does
not depend on the schedule. What does depend on the schedule is the
*accounting*: the serial build prints one running `bodies` total, so each
worker reports per-image deltas and the parent accumulates them in image
order -- otherwise a parallel log would report a different total than the
tree contains, which is exactly the kind of plausible-wrong-number this
repo refuses to ship.

The declines matter as much as the pool: `--max-methods` is a whole-build
brake, and a per-worker cap would lift up to N times the bodies asked for.
"""
from types import SimpleNamespace as NS

import pytest

from il2cpp.cli import (_auto_workers, _emit_assemblies, _weighted_order,
                        _worker_count, _worker_emit)


def _args(**kw):
    base = dict(workers=1, max_methods=None, asm=False, decls_only=False,
                verbose=False, types=None, out='out', quiet=False, bodies=None)
    base.update(kw)
    return NS(**base)


def _images(n):
    return [NS(name='a%d.dll' % i) for i in range(n)]


# ------------------------------------------------------------ worker count

def test_auto_workers_is_half_the_cores_capped_at_eight(monkeypatch):
    import il2cpp.cli as cli
    for cpus, expected in ((12, 6), (16, 8), (8, 4), (4, 2), (1, 1), (2, 1)):
        monkeypatch.setattr(cli.os, 'cpu_count', lambda c=cpus: c, raising=False)
        assert _auto_workers() == expected, cpus
    # auto must never take the whole machine, whatever the core count
    monkeypatch.setattr(cli.os, 'cpu_count', lambda: 64, raising=False)
    assert _auto_workers() == 8


def test_default_is_serial():
    assert _worker_count(_args(), _images(88)) == (1, None)


def test_auto_workers_caps_at_twelve():
    workers, note = _worker_count(_args(workers=0), _images(88))
    assert note is None
    assert workers == _auto_workers()


def test_explicit_worker_count_is_kept():
    assert _worker_count(_args(workers=8), _images(88)) == (8, None)


def test_a_single_image_stays_serial():
    # one image cannot be parallel, and must not pay for a pool
    assert _worker_count(_args(workers=8), _images(1)) == (1, None)


def test_max_methods_forces_serial_and_says_why():
    workers, note = _worker_count(_args(workers=8, max_methods=10), _images(88))
    assert workers == 1
    assert '--max-methods' in note


def test_negative_worker_count_is_reported_not_silently_clamped():
    workers, note = _worker_count(_args(workers=-1), _images(88))
    assert workers == 0
    assert '--workers' in note


def test_bodies_forces_serial_and_says_why():
    # --bodies is written by the parent's own Emitter; a worker's bodies
    # live in another process, so a pool would write the empty dict
    workers, note = _worker_count(_args(workers=8, bodies='bodies.json'),
                                  _images(88))
    assert workers == 1
    assert '--bodies' in note


# --------------------------------------------------------- schedule order

def _meta(names, weights):
    methods = []
    for i, w in enumerate(weights):
        methods.extend(NS(addr=0x1000, image=i) for _ in range(w))
    return NS(images=[NS(name=n) for n in names], methods=methods)


def test_weighted_order_is_heaviest_first_and_stable():
    meta = _meta(['a.dll', 'b.dll', 'c.dll'], [3, 9, 3])
    imgs = [NS(name=n) for n in ['a.dll', 'b.dll', 'c.dll']]
    assert [i.name for i in _weighted_order(imgs, meta)] == \
        ['b.dll', 'a.dll', 'c.dll']


def test_weighted_order_counts_only_native_methods():
    meta = NS(images=[NS(name='a.dll'), NS(name='b.dll')],
              methods=[NS(addr=0, image=0), NS(addr=0x1000, image=1)])
    imgs = [NS(name=n) for n in ['a.dll', 'b.dll']]
    assert [i.name for i in _weighted_order(imgs, meta)] == ['b.dll', 'a.dll']


def test_weighted_order_handles_an_only_filtered_subset():
    # --only filters the list; weights still key by image NAME, never by
    # the filtered position
    meta = _meta(['a.dll', 'b.dll', 'c.dll'], [1, 5, 3])
    imgs = [NS(name='c.dll'), NS(name='a.dll')]
    assert [i.name for i in _weighted_order(imgs, meta)] == ['c.dll', 'a.dll']


def test_weighted_order_without_metadata_keeps_the_order():
    imgs = [NS(name=n) for n in ['a.dll', 'b.dll']]
    assert [i.name for i in _weighted_order(imgs, None)] == ['a.dll', 'b.dll']
    assert [i.name for i in _weighted_order(imgs, NS())] == ['a.dll', 'b.dll']


# ------------------------------------------------------------ worker deltas

class _StubEmitter:
    """Stands in for the per-process Emitter: counts like the real one."""

    def __init__(self, files=3, lift=10, fail=0, boom=None):
        self.files, self.lift, self.fail = files, lift, fail
        self.boom = boom
        self.lifted = self.failed = self.fallbacks = self.emit_failed = 0
        self.lifter = object()
        self.seen = []

    def write_assembly_split(self, img):
        if self.boom is not None:
            raise self.boom
        self.seen.append(img.name)
        self.lifted += self.lift
        self.failed += self.fail
        return self.files


def _worker(em, images, monkeypatch):
    import il2cpp.cli as cli
    monkeypatch.setattr(cli, '_W', {'em': em, 'meta': NS(images=images)},
                        raising=False)
    return cli


def test_worker_reports_deltas_not_cumulative_totals(monkeypatch):
    em = _StubEmitter(lift=7)
    cli = _worker(em, [NS(name='a.dll')], monkeypatch)
    first = cli._worker_emit('a.dll')
    assert (first['files'], first['lifted']) == (3, 7)
    assert first['error'] is None and first['lifter'] is True
    second = cli._worker_emit('a.dll')
    # the same Emitter now holds a total; the delta is this image only
    assert second['lifted'] == 7


def test_worker_reports_an_image_it_cannot_find(monkeypatch):
    em = _StubEmitter()
    cli = _worker(em, [NS(name='a.dll')], monkeypatch)
    r = cli._worker_emit('missing.dll')
    assert r['files'] == 0 and r['error']
    assert em.seen == []


def test_worker_captures_an_emission_failure(monkeypatch):
    em = _StubEmitter(boom=ValueError('boom'))
    cli = _worker(em, [NS(name='a.dll')], monkeypatch)
    r = cli._worker_emit('a.dll')
    assert r['files'] == 0
    assert 'ValueError' in r['error'] and 'boom' in r['error']


# ------------------------------------------------------------ serial totals

def test_serial_emission_sums_files_and_keeps_the_running_total(capsys):
    em = _StubEmitter(files=4, lift=5)
    images = _images(3)
    stats = _emit_assemblies(images, em, _args(), 'gmd', 'bp')
    assert stats['files'] == 12
    assert stats['lifted'] == 15
    assert stats['failed'] == 0
    assert stats['errors'] == []
    assert stats['lifter'] is True
    out = capsys.readouterr().out
    # the log is the serial one: a running total, not a per-image count
    assert '(5 bodies, 0 failed)' in out
    assert '(15 bodies, 0 failed)' in out


def test_serial_emission_reports_a_missing_lifter():
    em = _StubEmitter()
    em.lifter = None
    stats = _emit_assemblies(_images(2), em, _args(), 'gmd', 'bp')
    assert stats['lifter'] is False


def test_max_methods_note_is_printed_once(capsys):
    _emit_assemblies(_images(4), _StubEmitter(), _args(workers=4, max_methods=5),
                     'gmd', 'bp')
    out = capsys.readouterr().out
    assert out.count('--max-methods is a per-build cap') == 1
    assert 'workers:' not in out


def test_quiet_serial_emission_prints_nothing(capsys):
    stats = _emit_assemblies(_images(2), _StubEmitter(), _args(quiet=True),
                             'gmd', 'bp')
    assert stats['files'] == 6
    assert capsys.readouterr().out == ''


def test_quiet_suppresses_a_decline_note(capsys):
    _emit_assemblies(_images(4), _StubEmitter(),
                     _args(workers=4, max_methods=5, quiet=True), 'gmd', 'bp')
    assert capsys.readouterr().out == ''
