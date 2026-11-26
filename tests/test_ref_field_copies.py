from types import SimpleNamespace as NS

from iced_x86 import Decoder
import pytest

from il2cpp import byref_fields as bf


def proof(monkeypatch, *, prefix='31ff', after='', field_type=8, segment='', pad=False,
          bad_guard=False, cast_sites=None):
    # Independent metadata and field offset. RCX is the only ref parameter,
    # parked in R15; the type-checked result travels through RDI across a call.
    va = 0x4000
    pre = bytes.fromhex('4c8bf9 ' + prefix)
    slot = 0x2400
    rel = slot - (va + len(pre) + len(bf._HEAD) + 4)
    pattern = bf._HEAD + rel.to_bytes(4, 'little', signed=True) + bf._TAIL
    if bad_guard:
        pattern = pattern.replace(b'\x72\x15', b'\x72\x11')
    tail = bytes.fromhex('ffd0 ' + after + ' 8b4724 ' + segment + '418907 c3')
    data = pre + pattern + tail
    types = [(0, 0x12 << 16), (0, (field_type << 16) | 6)]
    td = NS(byval=0, field_start=0, field_count=1, flags=1, generic_container=-1,
            is_valuetype=False, declaring=-1)
    meta = NS(version=31, typedefs=[td], fields=[NS(type=1, name='count')])
    il = NS(meta=meta, types=types, field_offsets=[[0x24]], type_name=lambda t:'Example.Record',
            instance_field_chain=lambda t:{0x24:('count', 1)}, _type_enum=lambda t:t[1] >> 16 & 255,
            bin=NS(read=lambda ip,n:data[ip-va:ip-va+n]),
            decode_slot=lambda p:{'type':types[0], 'kind':1, 'td':0} if p == slot else None)
    monkeypatch.setattr(bf, 'entry_ref_args', lambda *args:{'RCX':('result','0')})
    ins = list(Decoder(64, data, ip=va))
    return bf.ref_field_copies(NS(il=il), NS(param_count=1), ins, [ins[-2].ip] if pad else [],
                               cast_sites=cast_sites)


def test_checked_field_copy_proof(monkeypatch):
    assert list(proof(monkeypatch).values()) == [('result','RDI',0x24,'Example.Record','count')]


@pytest.mark.parametrize('changes', [dict(prefix=''), dict(bad_guard=True), dict(field_type=12),
                                     dict(after='448bfa'), dict(after='488bfb'),
                                     dict(segment='65'), dict(pad=True)])
def test_unproved_source_or_destination_declines(monkeypatch, changes):
    assert not proof(monkeypatch, **changes)


@pytest.mark.parametrize('changes', [dict(prefix=''), dict(bad_guard=True)])
def test_unproven_type_select_keeps_native_conditional_move(monkeypatch, changes):
    casts = {}
    proof(monkeypatch, cast_sites=casts, **changes)
    assert not casts


@pytest.mark.parametrize('extra', ['Use(obj4);', 'obj1 = Replace();', 'L_4100:'])
def test_checked_select_cleanup_preserves_live_statements(extra):
    from il2cpp import Decompiler
    dec = Decompiler.__new__(Decompiler)
    dec._checked_selects = {0x4100: (0x4110, 'T')}
    dec.L = NS(il=NS(type_name=lambda t: t))
    lines = ['object obj1 = Read();', 'T obj2 = obj1 as T;', 'if (!(obj1 == null))', '{',
             'if (!(obj1 is T))', '{', 'object obj4 = obj1.getClass().typeHierarchy;', extra, '}', '}']
    assert dec._drop_checked_select_scratch(lines) == lines
