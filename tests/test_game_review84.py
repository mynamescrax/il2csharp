"""Native-backed Review 84 constructor-chain and allocation-identity proofs."""
import pytest

from test_game_goldens import game_decompiler
from test_game_review78 import body

pytestmark = pytest.mark.game


def test_object_parent_encoding_completes_the_base_chain(game_decompiler):
    il, _ = game_decompiler
    assert il.base_chain_tds(3418) == (3418, 444)
    assert il.typedef_full(444) == "System.Object"


def test_trivial_constructor_tail_recovers_base_initializer(game_decompiler):
    assert body(game_decompiler, 24161) == "base..ctor(); return;"


def test_fresh_closure_allocation_has_one_identity(game_decompiler):
    text = body(game_decompiler, 24160)
    assert text.count("new Outline.<>c()") == 1
    assert "Outline.<>c obj1 = new Outline.<>c();" in text
    assert "Outline.<>c.<>9 = obj1;" in text
    assert "sub_180506120" not in text


def test_resolved_ancestor_constructor_is_not_printed_as_this_method(game_decompiler):
    text = body(game_decompiler, 127430)
    assert text.startswith("base..ctor();\n")
    assert "this.ctor(" not in text
    assert "Create_Internal(this, name)" in text


def test_parameterized_ancestor_constructor_keeps_its_argument(game_decompiler):
    text = body(game_decompiler, 128526)
    assert text.startswith("base..ctor(name);\n")
    assert "this.ctor(name)" not in text


def test_same_type_constructor_chain_recovers_this_initializer(game_decompiler):
    assert body(game_decompiler, 2411) == \
        "this..ctor(System.Random.GenerateSeed()); return;"


def test_preinitialized_object_fields_and_final_store_share_one_allocation(game_decompiler):
    text = body(game_decompiler, 128708)
    assert text.count("new OutlineFx.Optional_1<string>") == 1
    assert "new OutlineFx.Optional_1<string>(\"_globalTex\", false)" in text
    assert text.count("new OutlineFx.OutlineFxFeature.SolidMask()") == 1
    assert "OutlineFx.OutlineFxFeature.SolidMask solidMask1 = new OutlineFx.OutlineFxFeature.SolidMask();" in text
    assert "solidMask1._scale = 50.0f;" in text
    assert "this._solidMask = solidMask1;" in text
    assert "sub_180506120" not in text


def test_nonconstructor_shared_wrapper_remains_honestly_unresolved(game_decompiler):
    text = body(game_decompiler, 24996)
    assert "sub_180506120/*shared body, 6469 candidates*/" in text
    assert "base..ctor" not in text and "this..ctor" not in text
