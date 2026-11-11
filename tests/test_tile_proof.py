"""Merge-side unanimous whole-tile proof pins (sidecar phase 1, record)."""
from il2cpp.expr import Expr, _tile_proof_for

VT = (7, 0x11 << 16)
INT = (0, 0x08 << 16)

KEY = lambda t: t


def frag(origin_text, ty, off, w, b=None):
    o = Expr(origin_text, ty, "obj")
    v = Expr("%s+%d" % (origin_text, off), ty, "obj")
    v._slice = (o, off, w)
    if b is not None:
        v._bytes = b
    return v


def test_fire_unanimous():
    b = b"12345678"
    assert _tile_proof_for(
        [frag("v", VT, 0, 8, b), frag("v", VT, 0, 8, b)], KEY) == \
        ("v", VT, 0, 8, b)


def test_fire_unanimous_no_bytes():
    assert _tile_proof_for(
        [frag("v", VT, 0, 8), frag("v", VT, 0, 8)], KEY) == \
        ("v", VT, 0, 8, None)


def test_decline_offset():
    assert _tile_proof_for(
        [frag("v", VT, 0, 8), frag("v", VT, 8, 8)], KEY) is None


def test_decline_origin():
    assert _tile_proof_for(
        [frag("v", VT, 0, 8), frag("w", VT, 0, 8)], KEY) is None


def test_decline_width():
    assert _tile_proof_for(
        [frag("v", VT, 0, 8), frag("v", VT, 0, 4)], KEY) is None


def test_decline_missing_slice():
    assert _tile_proof_for(
        [frag("v", VT, 0, 8), Expr("v", VT, "obj")], KEY) is None


def test_decline_non_expr():
    assert _tile_proof_for(
        [frag("v", VT, 0, 8), None], KEY) is None
    assert _tile_proof_for("nope", KEY) is None


def test_decline_empty():
    assert _tile_proof_for([], KEY) is None


def test_decline_bytes_vs_none():
    assert _tile_proof_for(
        [frag("v", VT, 0, 8, b"12345678"), frag("v", VT, 0, 8)],
        KEY) is None


def test_decline_uncomparable_key():
    assert _tile_proof_for(
        [frag("v", VT, 0, 8), frag("v", VT, 0, 8)],
        lambda t: None) is None


def test_decline_unhashable_bytes():
    assert _tile_proof_for(
        [frag("v", VT, 0, 8, bytearray(b"12345678")),
         frag("v", VT, 0, 8, bytearray(b"12345678"))], KEY) is None
