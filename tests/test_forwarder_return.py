"""Noreturn-shared forwarder return: `call; int3/ud2` shared bodies with one
proven target and matching returns render `return Target(args);`.

Ground truth: Neon vmvn/vand/vorn families share one 3-insn body each
(`sub rsp,28h; xor r32,r32; call s8-variant; int3`) whose target
provably throws NotImplementedException on x64. MSVC's own abort is the
noreturn evidence; the target identity, args, and return tuple are all
proven, so the tail return compiles and names nothing unproven.
"""
from types import SimpleNamespace as NS

from il2cpp import Lifter

V64 = (7, 0x11 << 16)
INT = (0, 0x08 << 16)
VOID = (0, 0x01 << 16)


def _lift(caller_rt=V64, target_rt=V64, target_cands=(("method", 3),),
          next_byte=0xCC, caller_n=2):
    lift = Lifter.__new__(Lifter)
    lift.il = NS(
        addr_candidates={0x1000: [("method", 1)] * caller_n,
                         0x2000: list(target_cands)},
        types=[VOID, INT, V64],
        _type_enum=lambda t: (t[1] >> 16) & 0xFF)
    lift.meta = NS(methods=[None] * 4)
    lift.meta.methods[3] = NS(return_type=2 if target_rt is V64 else 1)
    lift._current_method = NS(
        addr=0x1000,
        return_type={VOID: 0, INT: 1, V64: 2}[caller_rt])
    lift.bin = NS(is_exec_va=lambda va: True,
                  read=lambda va, n: bytes([next_byte]) * n)
    return lift, NS(next_ip=0x1005)


def test_forwarder_return_fires():
    lift, ins = _lift()
    assert lift._dead_shared_forwarder_return(
        0x2000, ins, "Neon.vmvn_s8(a0)", V64) == "return Neon.vmvn_s8(a0);"


def test_forwarder_return_declines():
    lift, ins = _lift()
    assert lift._dead_shared_forwarder_return(
        0x2000, ins, "Neon.vmvn_s8(a0)", INT) is None
    lift_v, ins_v = _lift(caller_rt=VOID, target_rt=VOID)
    assert lift_v._dead_shared_forwarder_return(
        0x2000, ins_v, "Neon.vmvn_s8(a0)", VOID) is None
    assert lift._dead_shared_forwarder_return(
        0x2000, ins, "sub_2000/*shared body, 2 candidates*/(a0)", V64) is None
    assert lift._dead_shared_forwarder_return(0x2000, ins, "", V64) is None
    assert lift._dead_shared_forwarder_return(0x2000, ins, "Neon.f(a0)", None) is None
    lift_g, ins_g = _lift(target_cands=(("generic", 0),))
    assert lift_g._dead_shared_forwarder_return(
        0x2000, ins_g, "Neon.f(a0)", V64) is None
    lift_1, ins_1 = _lift(caller_n=1)
    assert lift_1._dead_shared_forwarder_return(
        0x2000, ins_1, "Neon.f(a0)", V64) is None
    lift_n, ins_n = _lift(next_byte=0x90)
    assert lift_n._dead_shared_forwarder_return(
        0x2000, ins_n, "Neon.f(a0)", V64) is None
