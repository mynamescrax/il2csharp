"""State-machine note and compile-gate header (il2cpp/emitter.py).

Both are comment-only additions. The note labels a compiler-generated
`<Foo>d__N` type; the header marks `--publicize` / `--raw-addr` output as
not faithful source. Default output must not change.
"""
from types import SimpleNamespace

from il2cpp.emitter import Emitter

ASYNC = 'System.Runtime.CompilerServices.IAsyncStateMachine'
ITER = 'System.Collections.Generic.IEnumerator_1<System.Object>'
ITER_PLAIN = 'System.Collections.IEnumerator'
DISPOSABLE = 'System.IDisposable'


def _emitter(type_name, iface_names, methods=('MoveNext',), **flags):
    """An Emitter shell with just the metadata surface the note reads."""
    names = list(iface_names)
    types = {i: names[i] for i in range(len(names))}
    meta = SimpleNamespace(
        methods=[SimpleNamespace(name=n) for n in methods],
        interfaces=list(range(len(names))),
        type_methods=lambda td: range(len(methods)))
    il = SimpleNamespace(types=list(range(len(names))),
                         type_name=lambda tup: types[tup])
    em = Emitter.__new__(Emitter)
    em.meta, em.il = meta, il
    for k, v in flags.items():
        setattr(em, k, v)
    td = SimpleNamespace(name=type_name, interfaces_start=0,
                         interfaces_count=len(names))
    return em, td


def test_iterator_note():
    em, td = _emitter('<LerpLookAtTarget>d__12', [ITER, DISPOSABLE, ITER_PLAIN])
    assert em._state_machine_note(td) == (
        '// iterator state machine for LerpLookAtTarget (compiler-generated; '
        'MoveNext drives the inlined original body)')


def test_async_note():
    em, td = _emitter('<WaitUntilCountOrTimeoutAsync>d__32', [ASYNC])
    assert em._state_machine_note(td).startswith(
        '// async state machine for WaitUntilCountOrTimeoutAsync (')


def test_note_requires_a_movenext_method():
    em, td = _emitter('<Foo>d__1', [ASYNC], methods=('Reset', 'Dispose'))
    assert em._state_machine_note(td) is None


def test_explicit_interface_movenext_counts():
    em, td = _emitter('<Foo>d__1', [ITER_PLAIN],
                      methods=('System.Collections.IEnumerator.MoveNext',))
    assert em._state_machine_note(td) is not None


def test_ambiguous_or_unlisted_interfaces_decline():
    em, td = _emitter('<Foo>d__1', [ASYNC, ITER_PLAIN])
    assert em._state_machine_note(td) is None
    em, td = _emitter('<Foo>d__1', [DISPOSABLE])
    assert em._state_machine_note(td) is None
    em, td = _emitter('<Foo>d__1', [])
    assert em._state_machine_note(td) is None


def test_only_the_compiler_naming_scheme_is_nominated():
    for name in ('Foo', '<Foo>d__', '<Foo>d__x', '<>c', '<Foo>b__1_0', 'Foo<Bar>d__1',
                 '<Foo>d__12_extra', ''):
        em, td = _emitter(name, [ASYNC])
        assert em._state_machine_note(td) is None, name


def test_lookup_failures_decline_instead_of_raising():
    em, td = _emitter('<Foo>d__1', [ASYNC])
    em.meta.interfaces = [99]                 # index outside the type table
    assert em._state_machine_note(td) is None
    em.il = None                              # broken runtime
    assert em._state_machine_note(td) is None


def test_gate_header_only_in_gate_builds():
    em, _ = _emitter('X', [])
    assert em._gate_header() is None
    em.publicize = False
    em.raw_addr = False
    assert em._gate_header() is None


def test_gate_header_names_the_flags():
    em, _ = _emitter('X', [], publicize=True)
    h = em._gate_header()
    assert h.startswith('// COMPILE-GATE OUTPUT -- NOT FAITHFUL SOURCE: ')
    assert '--publicize' in h and '--raw-addr' not in h
    em, _ = _emitter('X', [], raw_addr=True)
    assert '--raw-addr' in em._gate_header() and '--publicize' not in em._gate_header()
    em, _ = _emitter('X', [], publicize=True, raw_addr=True)
    h = em._gate_header()
    assert '--publicize' in h and '--raw-addr' in h
    assert '\n' not in h
