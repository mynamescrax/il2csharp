from types import SimpleNamespace as NS

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
