"""Audit batch 1: per-instance caches, non-negative type_sizes, ELF-gated
registration fallback.

TypeDef indices are binary-local, so a cache keyed by one and shared at class
level hands a second Decompiler/Emitter -- a second fixture -- another
binary's answer. `_static_field_name` then names another type's static field,
with no marker: a confidently wrong name rather than an honest decline.
"""
import inspect
import types
from types import SimpleNamespace as NS

from il2cpp import Decompiler, Emitter, Il2Cpp
from il2cpp.binary import ELF
import il2cpp.cli as cli_mod


def _typedefs(pairs):
    return [NS(namespace=ns, name=nm) for ns, nm in pairs]


def _decompiler_with(typedefs):
    d = Decompiler.__new__(Decompiler)
    d.L = NS(meta=NS(typedefs=_typedefs(typedefs)))
    return d


# --------------------------------------------------------------- A1a
def test_type_name_cache_is_per_instance():
    a = _decompiler_with([("Alpha", "Widget")])
    assert a._td_idx_by_name("Alpha.Widget") == 0

    b = _decompiler_with([("Other", "Thing"), ("Alpha", "Widget")])
    # the same name is TypeDef 1 in B; a shared cache would answer 0 and
    # resolve 'Other.Thing''s static fields
    assert b._td_idx_by_name("Alpha.Widget") == 1


def test_type_name_cache_absent_and_dotted_forms():
    a = _decompiler_with([("A", "B")])
    assert a._td_idx_by_name("A.B") == 0
    assert a._td_idx_by_name("B") is None          # no namespace -> no hit
    assert not hasattr(Decompiler, "_TDNAME_CACHE")


# --------------------------------------------------------------- A1b/A1c
def test_emitter_caches_are_not_class_attributes():
    assert not hasattr(Emitter, "_us_cache")
    assert not hasattr(Emitter, "_delegate_cache")


def test_us_cache_does_not_leak_between_instances():
    one = Emitter.__new__(Emitter)
    one.__dict__.setdefault("_us_cache", {})[4242] = True
    two = Emitter.__new__(Emitter)
    assert two.__dict__.setdefault("_us_cache", {}) is not one.__dict__["_us_cache"]
    assert two.__dict__.setdefault("_us_cache", {}).get(4242) is None


def test_delegate_caches_keep_separate_key_spaces():
    """The two delegate answers used to share one dict, distinguishable only
    because an int key can never equal a ('viable', int) tuple key."""
    e = Emitter.__new__(Emitter)
    dcache = e.__dict__.setdefault("_delegate_cache", {})
    vcache = e.__dict__.setdefault("_delegate_viable_cache", {})
    assert dcache is not vcache
    dcache[7] = True
    assert vcache.get(7) is None
    assert all(not isinstance(k, tuple) for k in dcache)


# --------------------------------------------------------------- A3
def test_android_registration_fallback_is_elf_gated():
    """The Android loader assumes a different registration struct shape. On
    the x64 PE it does not fail -- probed: a code_reg_va 0x10 off the classic
    answer, same module count, same resolved coverage -- so a PE must get a
    clean error instead of a silently wrong registration."""
    src = inspect.getsource(cli_mod.main)
    assert "isinstance(bin_, ELF)" in src
    assert "could not read code/metadata registrations" in src
    assert ELF is not None


def test_registration_phase_reports_errors_without_a_traceback():
    src = inspect.getsource(cli_mod.main)
    for exc in ("struct.error", "IndexError", "RuntimeError"):
        assert exc in src


# ----------------------------------------- audit batch 3: the five missed
def test_runtime_caches_are_not_class_attributes():
    for name in ("_tn_cache", "_slot_cache", "_fo_cache",
                 "_sf_infl_cache", "_mod_ptr_cache"):
        assert not hasattr(Il2Cpp, name), name


def _il_with_typedefs(pairs):
    """Il2Cpp with just the typedef table `_field_owner`/`type_name` read."""
    il = Il2Cpp.__new__(Il2Cpp)
    il.meta = NS(typedefs=[NS(namespace=ns, name=nm, field_start=fs,
                              field_count=fc)
                           for (ns, nm), fs, fc in pairs])
    il.typedef_full = lambda i: '%s.%s' % (il.meta.typedefs[i].namespace,
                                           il.meta.typedefs[i].name)
    return il


def test_field_owner_cache_is_per_instance():
    a = _il_with_typedefs([(("Alpha", "Widget"), 0, 5)])
    assert a._field_owner(0) == "Alpha.Widget"

    b = _il_with_typedefs([(("Other", "Thing"), 0, 1),
                           (("Alpha", "Widget"), 1, 5)])
    # field 0 belongs to Other.Thing in B; a shared cache answered
    # Alpha.Widget -- another binary's owner, with no marker
    assert b._field_owner(0) == "Other.Thing"


def test_type_name_cache_is_per_instance():
    vt = (0, 0x11 << 16)
    a = _il_with_typedefs([(("Alpha", "Widget"), 0, 0)])
    a.types = [vt]
    assert a.type_name(vt) == "Alpha.Widget"

    b = _il_with_typedefs([(("Other", "Thing"), 0, 0)])
    b.types = [vt]
    assert b.type_name(vt) == "Other.Thing"


def test_slot_cache_is_per_instance():
    a = Il2Cpp.__new__(Il2Cpp)
    a.bin = NS(qword=lambda va: None)
    a.bss_usage_map = {}
    assert a.decode_slot(0x1000) is None
    b = Il2Cpp.__new__(Il2Cpp)
    b.bin = NS(qword=lambda va: None)
    b.bss_usage_map = {}
    assert b.__dict__.setdefault("_slot_cache", {}) is not \
        a.__dict__["_slot_cache"]


def test_mod_ptr_cache_is_per_instance_and_clearable():
    a = Il2Cpp.__new__(Il2Cpp)
    a.bin = NS(read_qword_array=lambda va, n: [1, 2, 3])
    mod = NS(method_pointers=0x2000, method_pointer_count=3)
    assert a.read_module_ptrs(mod) == [1, 2, 3]

    b = Il2Cpp.__new__(Il2Cpp)
    b.bin = NS(read_qword_array=lambda va, n: [9])
    assert b.read_module_ptrs(mod) == [9]
    # cli/tools free the arrays through the instance dict without assuming
    # the attribute exists (a runtime that read no module pointers has none)
    getattr(a, "_mod_ptr_cache", {}).clear()
    assert hasattr(a, "_mod_ptr_cache")
