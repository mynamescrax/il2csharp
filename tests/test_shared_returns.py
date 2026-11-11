"""All-candidate return consensus without guessing a shared method identity."""
import struct
from types import SimpleNamespace as NS

from il2cpp import Il2Cpp, MethodDef

VOID = (0, 0x01 << 16)
BOOL = (0, 0x02 << 16)
INT = (0, 0x08 << 16)
FLOAT = (0, 0x0C << 16)
STRING = (0, 0x0E << 16)
MVAR = (0, 0x1E << 16)
VAR = (0, 0x13 << 16)


class FakeBin:
    def __init__(self):
        self.d = bytearray(64)
        self.offsets = {}
        self.qwords = {}

    def va2off(self, va):
        return self.offsets.get(va)

    def qword(self, va):
        return self.qwords.get(va, 0)


def setup(return_types, candidates=None):
    il = Il2Cpp.__new__(Il2Cpp)
    il.bin = FakeBin()
    il.types = list(return_types)
    il.meta = NS(
        methods=[MethodDef(i, f'M{i}', 0, i, 0, -1, i + 1,
                           0x10, 0, 0, i + 1)
                 for i in range(len(return_types))],
        generic_parameters=[],
        typedefs=[NS(is_valuetype=False) for _ in range(8)],
    )
    il.type_sizes = [None] * 8
    il.method_specs = []
    il.generic_insts_list = []
    il._type_by_ptr = {}
    cands = candidates or [('method', i) for i in range(len(return_types))]
    il.addr_candidates = {0x1234: cands}
    return il


def test_same_closed_return_type_is_recovered():
    il = setup([BOOL, BOOL])
    assert il.shared_return_type(0x1234) == BOOL


def test_metadata_attributes_do_not_change_type_identity():
    attributed = (BOOL[0], BOOL[1] | 0x1234)
    il = setup([BOOL, attributed])
    assert il.shared_return_type(0x1234) == BOOL


def test_different_return_types_remain_unknown():
    il = setup([BOOL, INT])
    assert il.shared_return_type(0x1234) is None


def test_byref_and_by_value_returns_do_not_agree():
    il = setup([INT, (INT[0], INT[1] | (1 << 29))])
    assert il.shared_return_type(0x1234) is None


def test_unreadable_candidate_invalidates_the_whole_proof():
    il = setup([STRING], [('method', 0), ('method', 99)])
    assert il.shared_return_type(0x1234) is None


def test_open_generic_method_definition_remains_unknown():
    il = setup([MVAR, MVAR])
    il.meta.generic_parameters = [(0, 'T', 0, 0, 0, 0)]
    assert il.shared_return_type(0x1234) is None


def generic_setup(kind, actuals):
    generic = VAR if kind == 'class' else MVAR
    il = setup([generic, generic], [('generic', 0), ('generic', 1)])
    il.meta.generic_parameters = [(0, 'T', 0, 0, 0, 0)]
    # MethodSpec instantiation indices are zero based, and "no
    # instantiation" is spelled -1, never 0, because row 0 is itself a
    # real instantiation.  Proved over all 175736 specs in the fixture
    # by work/review89_spec_arity_census.py: read zero based, every
    # spec agreed with its generic container's declared arity (144977
    # class, 32671 method); read one based, 2749 disagreed.
    absent = -1
    cls_inst = [0, 1] if kind == 'class' else [absent, absent]
    mth_inst = [0, 1] if kind == 'method' else [absent, absent]
    il.method_specs = [
        (0, cls_inst[0], mth_inst[0]),
        (1, cls_inst[1], mth_inst[1]),
    ]
    il.generic_insts_list = [(1, 0x1000), (1, 0x1010)]
    il.bin.qwords = {0x1000: 0x2000, 0x1010: 0x2010}
    il._type_by_ptr = {0x2000: actuals[0], 0x2010: actuals[1]}
    return il


def test_method_generic_returns_are_inflated_before_comparison():
    il = generic_setup('method', [INT, INT])
    assert il.shared_return_type(0x1234) == INT


def test_class_generic_returns_are_inflated_before_comparison():
    il = generic_setup('class', [STRING, STRING])
    assert il.shared_return_type(0x1234) == STRING


def test_different_generic_instantiations_do_not_form_consensus():
    il = generic_setup('method', [INT, FLOAT])
    assert il.shared_return_type(0x1234) is None


def nested_generic_setup(arg):
    generic_inst = (0x3000, 0x15 << 16)
    il = setup([generic_inst, generic_inst])
    il.bin.offsets = {0x3000: 0, 0x5000: 16}
    struct.pack_into('<QQ', il.bin.d, 0, 0x4000, 0x5000)
    struct.pack_into('<QQ', il.bin.d, 16, 1, 0x6000)
    il.bin.qwords = {0x6000: 0x7000}
    il._type_by_ptr = {
        0x4000: (7, 0x12 << 16),
        0x7000: arg,
    }
    return il


def test_open_generic_nested_inside_return_type_is_rejected():
    il = nested_generic_setup(MVAR)
    assert il.shared_return_type(0x1234) is None


def test_closed_generic_return_type_is_accepted_structurally():
    il = nested_generic_setup(INT)
    assert il.shared_return_type(0x1234) == (0x3000, 0x15 << 16)


def test_void_consensus_is_a_real_type_not_an_unknown():
    il = setup([VOID, VOID])
    assert il.shared_return_type(0x1234) == VOID


def test_unsupported_compound_return_class_declines_even_when_payload_matches():
    function_pointer = (0x9000, 0x1A << 16)
    il = setup([function_pointer, function_pointer])
    assert il.shared_return_type(0x1234) is None


def test_matching_byref_returns_stay_unknown_until_ref_locals_are_modelled():
    byref_int = (INT[0], INT[1] | (1 << 29))
    il = setup([byref_int, byref_int])
    assert il.shared_return_type(0x1234) is None


def test_value_type_consensus_requires_an_exact_size():
    value_type = (3, 0x11 << 16)
    il = setup([value_type, value_type])
    il.meta.typedefs[3].is_valuetype = True
    assert il.shared_return_type(0x1234) is None


def test_exact_size_makes_value_type_return_abi_provable():
    value_type = (3, 0x11 << 16)
    il = setup([value_type, value_type])
    il.meta.typedefs[3].is_valuetype = True
    il.type_sizes[3] = 16
    assert il.shared_return_type(0x1234) == value_type


def test_closed_generic_value_type_is_rejected_without_instantiated_size():
    il = nested_generic_setup(INT)
    il.meta.typedefs[7].is_valuetype = True
    assert il.shared_return_type(0x1234) is None


def test_equivalent_closed_generic_types_compare_structurally():
    left = (0x3000, 0x15 << 16)
    right = (0x3100, 0x15 << 16)
    il = setup([left, right])
    il.bin.offsets = {0x3000: 0, 0x3100: 16, 0x5000: 32, 0x5100: 48}
    struct.pack_into('<QQ', il.bin.d, 0, 0x4000, 0x5000)
    struct.pack_into('<QQ', il.bin.d, 16, 0x4000, 0x5100)
    struct.pack_into('<QQ', il.bin.d, 32, 1, 0x6000)
    struct.pack_into('<QQ', il.bin.d, 48, 1, 0x6010)
    il.bin.qwords = {0x6000: 0x7000, 0x6010: 0x7010}
    il._type_by_ptr = {
        0x4000: (7, 0x12 << 16),
        0x7000: INT,
        0x7010: INT,
    }
    assert il.shared_return_type(0x1234) == left
