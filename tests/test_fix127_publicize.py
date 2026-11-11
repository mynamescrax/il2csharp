"""Fix 127: opt-in --publicize renders every declared accessibility public.

Native bodies read private backing fields and internal members across images
(IL2CPP inlines accessors and ignores accessibility), so a faithful body cannot
compile against faithful declarations (CS0122, 86k on the fixture gate). The
default tree is unchanged; the flag is a recompilation aid.
"""
from types import SimpleNamespace

from il2cpp import Emitter


def _em(publicize):
    em = Emitter.__new__(Emitter)
    em.publicize = publicize
    return em


def _acc(flags, static=False):
    return SimpleNamespace(flags=flags, is_static=static)


def test_pub_maps_every_nonempty_visibility_to_public():
    em = _em(True)
    for vis in ('private ', 'internal ', 'protected ', 'protected internal ',
                'private protected ', 'public '):
        assert em._pub(vis) == 'public '


def test_pub_keeps_empty_modifier():
    # explicit interface impls, interface members, static ctors: no modifier
    assert _em(True)._pub('') == ''


def test_default_keeps_metadata_accessibility():
    em = _em(False)
    assert em._pub('private ') == 'private '
    assert Emitter.__new__(Emitter)._pub('internal ') == 'internal '


def test_accessor_modifiers_publicized_and_default():
    td = SimpleNamespace(flags=0)
    present = [_acc(0x1)]          # private, non-virtual getter
    assert _em(False)._accessor_modifiers(td, present) == 'private '
    assert _em(True)._accessor_modifiers(td, present) == 'public '
    # override dispatch flags survive: Virtual (0x40) without NewSlot
    present = [_acc(0x4 | 0x40)]   # protected override
    assert _em(True)._accessor_modifiers(td, present) == 'public override '


def test_interface_and_explicit_accessors_stay_bare():
    iface = SimpleNamespace(flags=0x20)
    assert _em(True)._accessor_modifiers(iface, [_acc(0x6 | 0x400 | 0x40)]) == ''
    td = SimpleNamespace(flags=0)
    assert _em(True)._accessor_modifiers(td, [_acc(0x1)], explicit=True) == ''


def test_publicize_drops_readonly_only_under_the_flag():
    # inlined native ctors store init-only fields from other types (CS0191)
    import inspect
    src = inspect.getsource(Emitter)
    assert "if fa & FA_INITONLY and not getattr(self, 'publicize', False):" in src
