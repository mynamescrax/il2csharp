"""MethodSpec instantiation indices are zero based; -1 means absent.

Fix 92.  ``method_specs[i]`` is ``(methodDefinitionIndex, classIndexIndex,
methodIndexIndex)`` and the last two index ``generic_insts_list``
directly.  Reading them one based -- ``[index - 1]``, with 0 treated as
"no instantiation" -- named every generic site after the *previous*
registered instantiation, which is how ``Instantiate<GameObject>`` was
printed as ``Instantiate<UnityEngine.Font>`` at 66 call sites.

The base is proved, not assumed.  Over all 175736 specs in the fixture
the zero based read agrees with the declared generic arity of the
container each spec belongs to in 100% of cases (32671 method rows,
144977 class rows, zero exceptions); the one based read contradicts 2749
of those declarations.  Absence is spelled -1 (30759 class rows, 143065
method rows) and never 0 -- two real specs carry classIndexIndex 0 -- so
0 must not be read as a sentinel.  See work/review89_spec_arity_census.py.
"""
from types import SimpleNamespace as NS

from il2cpp import Il2Cpp, MethodDef

INT = (0, 0x08 << 16)
STRING = (0, 0x0E << 16)

ROW0_ARGV = 0x1000
ROW1_ARGV = 0x2000
TWO_ROWS = [(1, ROW0_ARGV), (1, ROW1_ARGV)]


class FakeBin:
    def __init__(self):
        self.qwords = {}

    def va2off(self, va):
        return None

    def qword(self, va):
        return self.qwords.get(va, 0)


def setup(specs, insts):
    """One non-generic holder type, one method, and a spec table."""
    il = Il2Cpp.__new__(Il2Cpp)
    il.bin = FakeBin()
    il.types = [INT]
    il.meta = NS(
        methods=[MethodDef(index=0, name='Method', declaring=0,
                           return_type=0, parameter_start=0,
                           generic_container=-1, token=1, flags=0x10,
                           iflags=0, slot=0, param_count=0)],
        typedefs=[NS(name='Holder', namespace='Test')],
        generic_parameters=[],
    )
    il.method_specs = list(specs)
    il.generic_insts_list = list(insts)
    il._type_by_ptr = {}
    # Which GenericInst row the reader picked is what is under test, not
    # how a type argument renders, so report the row's argv pointer.
    il._argv_names = lambda argv, argc, depth: ['row_%#x' % argv]
    return il


def typed(il):
    """Give each row one readable closed type argument."""
    il.bin.qwords = {ROW0_ARGV: 0x9000, ROW1_ARGV: 0x9100}
    il._type_by_ptr = {0x9000: INT, 0x9100: STRING}
    return il


def test_method_index_zero_names_the_first_row_not_absence():
    # One based read declined here, dropping the type argument entirely.
    il = setup([(0, -1, 0)], TWO_ROWS)
    assert il.generic_method_name(0) == 'Test.Holder.Method<row_0x1000>'


def test_method_index_one_names_the_second_row_not_the_first():
    # One based read answered row 0 here: the off-by-one itself.
    il = setup([(0, -1, 1)], TWO_ROWS)
    assert il.generic_method_name(0) == 'Test.Holder.Method<row_0x2000>'


def test_class_index_zero_names_the_first_row():
    il = setup([(0, 0, -1)], TWO_ROWS)
    assert il.generic_method_name(0) == 'Test.Holder<row_0x1000>.Method'


def test_class_index_one_names_the_second_row():
    il = setup([(0, 1, -1)], TWO_ROWS)
    assert il.generic_method_name(0) == 'Test.Holder<row_0x2000>.Method'


def test_absent_instantiation_is_minus_one():
    il = setup([(0, -1, -1)], TWO_ROWS)
    assert il.generic_method_name(0) == 'Test.Holder.Method'


def test_out_of_range_instantiation_is_declined_not_wrapped():
    il = setup([(0, 9, 9)], TWO_ROWS)
    assert il.generic_method_name(0) == 'Test.Holder.Method'


def test_unreadable_row_does_not_raise_while_naming():
    # generic_insts_list holds None where registration data was
    # unreadable; the reader must not unpack it.
    il = setup([(0, 0, 0)], [None])
    assert il.generic_method_name(0) == 'Test.Holder.Method'


def test_type_args_read_rows_zero_based():
    il = typed(setup([], TWO_ROWS))
    assert il._method_spec_type_args(0) == (INT,)
    assert il._method_spec_type_args(1) == (STRING,)


def test_type_args_treat_minus_one_as_absent():
    il = typed(setup([], TWO_ROWS))
    assert il._method_spec_type_args(-1) is None


def test_type_args_decline_out_of_range_rows():
    il = typed(setup([], TWO_ROWS))
    assert il._method_spec_type_args(2) is None


def test_type_args_decline_unreadable_rows_without_raising():
    il = typed(setup([], [None]))
    assert il._method_spec_type_args(0) is None
