"""Compile-gate scope repair: escaping locals hoist, empty class-init
guards drop (il2cpp/dec/build.py)."""
from il2cpp.dec.build import drop_empty_init_guards, hoist_escaping_locals


def test_hoists_arm_declared_local_used_after_join():
    body = [
        'if (flag1)',
        '{',
        '    object obj6 = a;',
        '}',
        'else',
        '{',
        '    object obj6 = b;',
        '}',
        'Use(obj6);',
    ]
    out, n = hoist_escaping_locals(body)
    assert n == 1
    assert out[0] == 'object obj6;'
    assert '    obj6 = a;' in out and '    obj6 = b;' in out
    assert not any(l.strip().startswith('object obj6 =') for l in out)


def test_leaves_well_scoped_locals_alone():
    body = ['int num1 = 3;', 'if (num1 > 2)', '{', '    int num2 = num1;',
            '    Use(num2);', '}']
    out, n = hoist_escaping_locals(body)
    assert n == 0 and out == body


def test_conflicting_types_decline():
    body = ['if (x)', '{', '    int num1 = 1;', '}', 'else', '{',
            '    float num1 = 2f;', '}', 'Use(num1);']
    out, n = hoist_escaping_locals(body)
    assert n == 0 and out == body


def test_never_hoists_into_switch_block():
    body = [
        'switch (k)',
        '{',
        '    case 0:',
        '    {',
        '        string text1 = "a";',
        '        break;',
        '    }',
        '    case 1:',
        '    {',
        '        string text1 = "b";',
        '        break;',
        '    }',
        '}',
    ]
    out, n = hoist_escaping_locals(body)
    assert n == 1
    assert out[0] == 'string text1;'      # above the switch, not inside


def test_parameters_and_pattern_vars_untouched():
    body = ['if (x)', '{', '    int a1 = 1;', '}', 'Use(a1);']
    out, n = hoist_escaping_locals(body, params={'a1'})
    assert n == 0


def test_empty_init_guard_dropped_only_when_empty():
    lines = [
        'if (typeof(UnityEngine.Object).initialized == 0)',
        '{',
        '}',
        'Foo();',
        'if (typeof(Bar).initialized == 0)',
        '{',
        '    Baz();',
        '}',
        'if (typeof(Q).initialized == 0)',
        '{',
        '}',
        'else',
        '{',
        '}',
    ]
    out = drop_empty_init_guards(lines)
    assert out[0] == 'Foo();'
    assert 'if (typeof(Bar).initialized == 0)' in out
    assert 'if (typeof(Q).initialized == 0)' in out
