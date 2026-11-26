from types import SimpleNamespace as NS
import re

from il2cpp import Decompiler


def test_duplicated_temporaries_keep_only_uncontested_type_evidence():
    dec = Decompiler.__new__(Decompiler)
    ref, fp = (7, 0x12 << 16), (0, 0x0c << 16)
    dec._var_types = {}
    dec.L = NS(_var_types={'t1': ref, 't3': fp, 't4': fp}, _type_hints={'t3': ref},
               _current_method=object(), meta=NS(method_params=lambda m: [NS(name='t5')]))
    lines = ['if (jump)', '{', 'goto L_100;', '}', 'else', '{', 'if (skip)', '{',
             'Other();', '}', 'else', '{', 'L_100:',
             'var t1 = Read();', 'var t2 = Unknown();', 'var t3 = Ambiguous();',
             'Use(t1, t2, t3);', '}', '}', 'End();']
    out = dec._hoist_shared_tails(lines)
    assert out[2:6] == ['var t6 = Read();', 'var t7 = Unknown();', 'var t8 = Ambiguous();',
                        'Use(t6, t7, t8);']
    assert dec._var_types == {'t6': ref}
    assert out.count('Use(t1, t2, t3);') == 1


def test_tail_private_struct_slot_and_array_phi_keep_their_types():
    dec=Decompiler.__new__(Decompiler);vec=(0x1234,0x11<<16);arr=(0x6780,0x1d<<16)
    dec._var_types={'v1':arr,'v2':arr,'v3':arr};dec.L=NS(_var_types={'t1':vec},
            _type_hints={'v1':(arr[0],arr[1]|2),'v2':(arr[0],arr[1]|1<<29)})
    lines=['if (jump)','{','goto L_100;','}','else','{','if (skip)','{','Other();','}','else','{','L_100:',
           't1 = ReadStruct();','v1 = Values();','v2 = Conflicted();','Use(t1, v1, v2, v3);','}','}','Keep(v3);']
    out=dec._hoist_shared_tails(lines)
    uses=[re.fullmatch(r'Use\((t\d+), (v\d+), (v\d+), v3\);',s) for s in out if s.startswith('Use(')]
    assert len(uses)==2 and all(uses)
    copied,= [m for m in uses if m[1]!='t1']
    assert dec._var_types[copied[1]]==vec and dec._var_types[copied[2]]==arr
    assert copied[3] not in dec._var_types  # byref hint conflicts; external v3 was never renamed
