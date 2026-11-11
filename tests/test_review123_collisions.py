"""Fix 123: collision-aware namespace stripping.

Shortening `System.Collections.Hashtable` to `Hashtable` in a file that
also imports another `Hashtable` rebinds it (CS0104); shortening to a head
matching a visible namespace final segment rebinds to the namespace
(CS0234/CS0426). Strip now keeps the full chain for ambiguous heads,
proven per file against the metadata short-name table.
"""
from il2cpp.csharp import collision_heads, strip_namespaces

from test_game_goldens import game_decompiler  # noqa: F401 (fixture)
import pytest


@pytest.mark.game
def test_fulldepth_generic_args_resolve(game_decompiler):
    il, dec = game_decompiler
    from il2cpp import Emitter
    em = Emitter(il, None, with_bodies=False)
    td = next(t for t in il.meta.typedefs
              if (t.name or "") == "JsonSerializer"
              and t.namespace == "Newtonsoft.Json")
    out = []
    em.emit_type(td, out)
    hits = [l.strip() for l in out if "ErrorEventArgs> Error" in l]
    assert hits, [l.strip()[:100] for l in out if "Error;" in l]
    assert "EventHandler_1<Newtonsoft.Json.Serialization.ErrorEventArgs>" in hits[0]


SHORT_TO_NS = {
    "Hashtable": {"System.Collections", "ExitGames.Client.Photon"},
    "Object": {"System", "UnityEngine"},
    "Transform": {"UnityEngine"},
}


def test_duplicate_short_is_ambiguous():
    buf = "private System.Collections.Hashtable t;"
    uses = {"System.Collections", "ExitGames.Client.Photon"}
    assert collision_heads(buf, "Game", uses, SHORT_TO_NS) == {"Hashtable"}


def test_unique_short_is_clean():
    buf = "private UnityEngine.Transform t;"
    uses = {"UnityEngine"}
    assert collision_heads(buf, "Game", uses, SHORT_TO_NS) == set()


def test_namespace_final_collides():
    buf = "public UnityEngine.InputSystem.HID.HID.HIDDeviceDescriptor h;"
    uses = {"UnityEngine.InputSystem.HID"}
    assert collision_heads(buf, "Game", uses, {}) == {"HID"}


def test_strip_keeps_ambiguous_full_chain():
    line = "    private System.Collections.Hashtable t;"
    uses = {"System.Collections", "ExitGames.Client.Photon"}
    assert strip_namespaces([line], uses, "Game", {"Hashtable"}) == [line]


def test_strip_still_shortens_clean_names():
    assert strip_namespaces(["    private System.IntPtr _p;"],
                            {"System"}, "Game", set()) == \
        ["    private IntPtr _p;"]
