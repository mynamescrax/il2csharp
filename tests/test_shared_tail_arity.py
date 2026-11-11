"""One shared body, one argument list: unresolved shared tails are bounded
by the same arity proof `_call` uses.

`_call` trims an ambiguous shared body's argument list to the largest
declared arity among its candidates (batch 21j), because every candidate
names a call into the same compiled machine code and therefore consumes the
same argument registers. Tails never got that bound, so one VA printed
`(x)` when called and `(x, 0)` when tail-jumped -- e.g. mscorlib
`ConstructorInfo.GetHashCode` (mi 8752, `xor edx,edx; jmp 0x181b14c10`)
rendered `sub_181b14c10/*shared body, 13 candidates*/(this, 0)` while
`Delegate.GetHashCode` called the same address with `(this.m_target)`.

The trim is deliberately narrow: only a trailing run of literal zeros goes,
which is the plumbing value a shared forwarder zeroed into a register no
candidate declares. A non-zero extra argument keeps today's spelling, so a
registry-missed sharer whose extra register really is read (probed:
`List`1.CopyTo`'s R8 at 0x180df9c30) is untouched.
"""
import struct
from types import SimpleNamespace as NS

from iced_x86 import Decoder

from il2cpp import Expr, Lifter, MethodDef

VOID = (0, 0x01 << 16)
INT = (0, 0x08 << 16)
VALUETYPE = (0, 0x11 << 16)  # a class the ABI passes through a hidden buffer

TAIL_T = 0x3000


def _md(index, param_count=0, static=False, return_type=1):
    return MethodDef(index, 'M%d' % index, 0, return_type, 0, -1, 0,
                     0x10 if static else 0, 0, 0, param_count)


def _lifter(methods, cands, sret_type=None, specs=()):
    """Lifter with just the metadata the two helpers read."""
    lift = Lifter.__new__(Lifter)
    lift.meta = NS(methods=methods)
    lift.il = NS(
        addr_candidates={TAIL_T: list(cands)},
        addr_to_method={},
        types=[VOID, INT, VALUETYPE],
        method_specs=list(specs),
        returns_sret=lambda t: t == sret_type,
    )
    return lift


def _two_instance_zero_param():
    """The GetHashCode shape: two instance no-arg owners, one body."""
    return _lifter([_md(0), _md(1)],
                   [('method', 0), ('method', 1)])


# ---------------------------------------------------------------- cap


def test_cap_is_largest_declared_arity_with_receiver():
    lift = _lifter([_md(0, param_count=0), _md(1, param_count=1)],
                   [('method', 0), ('method', 1)])
    assert lift._shared_arity_cap([('method', 0), ('method', 1)]) == 2


def test_cap_does_not_count_a_receiver_for_static_candidates():
    lift = _lifter([_md(0, param_count=2, static=True), _md(1, param_count=1)],
                   [('method', 0), ('method', 1)])
    assert lift._shared_arity_cap([('method', 0), ('method', 1)]) == 2


def test_cap_counts_the_hidden_sret_slot_of_the_signature():
    lift = _lifter([_md(0, return_type=2), _md(1, return_type=2)],
                   [('method', 0), ('method', 1)], sret_type=VALUETYPE)
    # receiver + hidden buffer, and no param
    assert lift._shared_arity_cap([('method', 0), ('method', 1)]) == 2


def test_cap_prefers_the_consensus_return_over_the_signature():
    # a root VAR/MVAR return cannot classify the ABI; the caller's
    # all-candidate consensus can, exactly as in `_call`
    lift = _lifter([_md(0, return_type=1), _md(1, return_type=1)],
                   [('method', 0), ('method', 1)], sret_type=VALUETYPE)
    cands = [('method', 0), ('method', 1)]
    assert lift._shared_arity_cap(cands) == 1
    assert lift._shared_arity_cap(cands, VALUETYPE) == 2


def test_cap_reads_generic_candidates_through_their_spec():
    lift = _lifter([_md(i) for i in range(7)] + [_md(7, param_count=3)],
                   [('generic', 0), ('generic', 1)], specs=[(0, 0, -1), (7, 0, -1)])
    assert lift._shared_arity_cap([('generic', 0), ('generic', 1)]) == 4


def test_cap_skips_an_unreadable_candidate():
    lift = _lifter([_md(0, param_count=1)], [('method', 0), ('method', 9)])
    assert lift._shared_arity_cap([('method', 0), ('method', 9)]) == 2


def test_cap_declines_when_nothing_is_readable():
    lift = _lifter([_md(0)], [('method', 4), ('method', 9)])
    assert lift._shared_arity_cap([('method', 4), ('method', 9)]) is None
    assert lift._shared_arity_cap([]) is None
    assert lift._shared_arity_cap(None) is None


# ---------------------------------------------------------------- keep


def test_keep_drops_a_trailing_plumbing_zero():
    lift = _two_instance_zero_param()
    assert lift._shared_tail_keep(TAIL_T, ['this', '0']) == 1


def test_keep_drops_one_of_two_trailing_zeros():
    # cap 2 (receiver + one param): the third slot is the plumbing one
    lift = _lifter([_md(0, param_count=1), _md(1, param_count=1)],
                   [('method', 0), ('method', 1)])
    assert lift._shared_tail_keep(TAIL_T, ['a', 'b', '0']) == 2
    assert lift._shared_tail_keep(TAIL_T, ['a', '0', '0']) == 2


def test_keep_leaves_a_read_extra_register_alone():
    # the probed List`1.CopyTo shape: the registry missed a sharer that
    # really does read R8, so a non-zero extra argument is not invented
    lift = _two_instance_zero_param()
    assert lift._shared_tail_keep(TAIL_T, ['this', 'num5']) is None


def test_keep_declines_a_zero_run_broken_by_a_later_argument():
    lift = _two_instance_zero_param()
    assert lift._shared_tail_keep(TAIL_T, ['this', '0', 'num5']) is None


def test_keep_declines_when_the_cap_does_not_below_the_list():
    lift = _two_instance_zero_param()
    assert lift._shared_tail_keep(TAIL_T, ['this']) is None
    lift = _lifter([_md(0, param_count=2), _md(1, param_count=2)],
                   [('method', 0), ('method', 1)])
    assert lift._shared_tail_keep(TAIL_T, ['a', 'b', 'c']) is None


def test_keep_needs_two_candidates():
    # one owner is not ambiguous: the registry already names the callee
    lift = _lifter([_md(0)], [('method', 0)])
    assert lift._shared_tail_keep(TAIL_T, ['this', '0']) is None


def test_keep_declines_an_unknown_or_unlisted_target():
    lift = _two_instance_zero_param()
    assert lift._shared_tail_keep(0x9999, ['this', '0']) is None
    assert lift._shared_tail_keep(None, ['this', '0']) is None
    assert lift._shared_tail_keep(0, ['this', '0']) is None


def test_keep_declines_an_empty_argument_list():
    lift = _two_instance_zero_param()
    assert lift._shared_tail_keep(TAIL_T, []) is None


def test_keep_checks_only_the_four_argument_registers():
    # arguments past ARG_REGS live on the stack, where no candidate's
    # declared arity can reach; the cap still bounds them
    lift = _two_instance_zero_param()
    assert lift._shared_tail_keep(TAIL_T, ['this', '0', '0', '0', 's_20']) == 1


# ---------------------------------------------------------------- render


class _Unresolved(Lifter):
    """A shared tail every disambiguation step declines by design."""

    def _shared_parameterless_ctor_target(self, cands, recv):
        return None

    def _td_of(self, ty):
        return None

    def _array_receiver_td(self, ty):
        return None

    def _legacy_shared_receiver_chain(self, td):
        return []

    def _shared_same_render_target(self, cands):
        return None

    def _shared_tail_return_target(self, cands):
        return None


def _tail_lifter(regs):
    lift = _Unresolved.__new__(_Unresolved)
    lift.meta = NS(methods=[_md(0), _md(1)])
    lift.il = NS(
        addr_candidates={TAIL_T: [('method', 0), ('method', 1)]},
        addr_to_method={},
        types=[VOID, INT, VALUETYPE],
        method_specs=[],
        returns_sret=lambda t: False,
        _type_enum=lambda t: ((t[1] >> 16) & 0xFF) if t else None,
        function_extent=lambda va: (va, va + 16),
        bin=NS(exports={}),
    )
    lift.bin = NS(is_exec_va=lambda va: True,
                  read=lambda va, n: b"\xcc" * n, exports={})
    lift.regs = dict(regs)
    lift.out = []
    lift.dry = False
    lift.asm_comments = False
    lift.rt_names = {}
    lift._twin_cache = {}
    lift._cls_init_export = None
    lift.rt_wbarrier = {}
    lift.rt_init_meta = None
    lift.rethrow_va = None
    lift.raise_va = None
    lift.eh_helper_set = {}
    lift._thunk_cache = {}
    lift.cur_va = 0x1000
    lift._current_method = NS(return_type=1, addr=0x1000)
    lift._type_hints = {}
    lift._call_class_args = None
    lift._xmm_pending = []
    lift.vt_recv_slot = None
    lift.vt_recv = None
    lift.flags = None
    lift._cur_ip = 0
    return lift


def _jmp(target=TAIL_T, ip=0x1000):
    return Decoder(64, b"\xe9" + struct.pack("<i", target - (ip + 5)),
                   ip=ip).decode()


def test_unresolved_shared_tail_drops_the_plumbing_zero():
    lift = _tail_lifter({"RCX": Expr("this", None, "obj"),
                         "RDX": Expr("0", None, "int")})
    lift._insn(_jmp(), [_jmp()], 0, None, 0x1010)
    assert lift.out == [(0x1000, 'return sub_3000/*shared body, 2 candidates*/'
                                 '(this); /* tail */', None)]


def test_unresolved_shared_tail_keeps_a_written_extra_argument():
    lift = _tail_lifter({"RCX": Expr("this", None, "obj"),
                         "RDX": Expr("num5", None, "int")})
    lift._insn(_jmp(), [_jmp()], 0, None, 0x1010)
    assert lift.out == [(0x1000, 'return sub_3000/*shared body, 2 candidates*/'
                                 '(this, num5); /* tail */', None)]
