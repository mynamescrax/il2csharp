"""Native-backed assertions for Review 85's enum decode and argument fold.

fix 86 -- `enum_members` read the field default-value blob raw at four
widths (1/2/4/8) and kept whichever landed first. From metadata v29 an
i4/u4 member is stored in ReadCompressedInt32 form, a sign-in-low-bit
zigzag, so every non-negative member came back DOUBLED and three junk
keys were invented per member. Enum *declarations* were always correct
because they resolve through `parse_default`; every literal FOLD (field
stores, jcc compares, and the argument fold below) consumed the
corrupted table and so either declined or printed a confidently WRONG
member name. The doubling makes the wrong names recognisable: the name
that used to be printed belongs to the member worth exactly HALF.

fix 85 -- an enum-typed parameter fed a raw integer literal now names
its member, the same metadata proof the store and compare paths have
used since batch 39 but which the argument path never applied.
"""
import pytest

from test_game_goldens import game_decompiler

pytestmark = pytest.mark.game


def body(game_decompiler, mi):
    il, dec = game_decompiler
    method = il.meta.methods[mi]
    return "\n".join(dec.lift_method(method, il.meta.typedefs[method.declaring]))


def enum_table(il, namespace, name):
    hits = [i for i, td in enumerate(il.meta.typedefs)
            if td.name == name and td.namespace == namespace]
    assert len(hits) == 1, "%s.%s resolved to %r" % (namespace, name, hits)
    return il.enum_members(hits[0])


def test_enum_members_decodes_the_compressed_default_value_blob(game_decompiler):
    il, _ = game_decompiler

    # Exact equality is the assertion: the raw-width read produced doubled
    # keys (Open=3 arriving as 6) *plus* junk keys from the 2/4/8-byte
    # reads of the same bytes, so a subset check would have passed while
    # the table was still wrong.
    assert enum_table(il, "System.IO", "FileMode") == {
        1: "CreateNew",
        2: "Create",
        3: "Open",
        4: "OpenOrCreate",
        5: "Truncate",
        6: "Append",
    }
    assert enum_table(il, "System", "DateTimeKind") == {
        0: "Unspecified",
        1: "Utc",
        2: "Local",
    }


def test_enum_members_offers_no_member_for_a_value_nothing_names(game_decompiler):
    il, _ = game_decompiler
    table = enum_table(il, "System.IO", "FileMode")

    # FileMode runs 1..6. A fold has to decline on anything else rather
    # than invent a name, which is what keeps a [Flags] combination with
    # no single named member rendering as its integer.
    assert 0 not in table
    assert 7 not in table


@pytest.mark.parametrize("mi,named,bare", [
    (2157,
     "System.Math.Round(value, digits, MidpointRounding.ToEven)",
     "System.Math.Round(value, digits, 0)"),
    (4687,
     "System.Threading.ExecutionContext.Capture(ref obj1, CaptureOptions.None)",
     "System.Threading.ExecutionContext.Capture(ref obj1, 0)"),
    (18054,
     "this.GetStyleInt(StylePropertyId.UnitySliceType)",
     "this.GetStyleInt(196617)"),
])
def test_enum_typed_argument_names_its_member(game_decompiler, mi, named, bare):
    text = body(game_decompiler, mi)

    assert named in text
    assert bare not in text


@pytest.mark.parametrize("mi,correct,wrong", [
    # Token.XdrDatatype=37 vs XsdSchema=74, XdrExtends=39 vs XsdElement=78,
    # SchemaRef=59 vs XsdRedefine=118 -- each stale name is worth half.
    (42414,
     "if (builder.ParentElement != Token.XsdSchema)",
     "if (builder.ParentElement != Token.XdrDatatype)"),
    (42414,
     "if (builder.ParentElement != Token.XsdElement)",
     "if (builder.ParentElement != Token.XdrExtends)"),
    (42414,
     "if (builder.ParentElement == Token.XsdRedefine)",
     "if (builder.ParentElement == Token.SchemaRef)"),
    # SimulationStages.Forward=2 vs Resimulate=4
    (26747,
     "if (this._runner.Stage != SimulationStages.Resimulate)",
     "if (this._runner.Stage != SimulationStages.Forward)"),
    # ParsingFunction.ReaderClosed=12 vs InReadContentAsBinary=24, and
    # Eof=11 vs InReadAttributeValue=22
    (37191,
     "else if (this.parsingFunction != ParsingFunction.InReadContentAsBinary)",
     "else if (this.parsingFunction != ParsingFunction.ReaderClosed)"),
    (37191,
     "if (this.parsingFunction == ParsingFunction.InReadAttributeValue)",
     "if (this.parsingFunction == ParsingFunction.Eof)"),
])
def test_compare_folds_the_member_the_literal_actually_names(
        game_decompiler, mi, correct, wrong):
    text = body(game_decompiler, mi)

    assert correct in text
    # The stale render was not a magic number the reader could see through
    # -- it was a real member name belonging to a different value.
    assert wrong not in text


def test_datetime_kind_compares_and_arguments_agree_on_the_same_table(
        game_decompiler):
    text = body(game_decompiler, 86310)

    # Kind==2 is Local, not Utc; Kind==1 had no key in the doubled table
    # and stayed a bare literal.
    assert "if (dateTime2.Kind == DateTimeKind.Local)" in text
    assert "dateTime2.Kind == 1" not in text
    # fix 85 reaches the argument of the same call the compares guard.
    assert ("System.DateTime.SpecifyKind(dateTime2, DateTimeKind.Unspecified)"
            in text)
    assert "System.DateTime.SpecifyKind(dateTime2, 0)" not in text
