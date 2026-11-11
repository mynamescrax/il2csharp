"""The compiler smoke uses real lifter fragments and real project settings."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from csharp_smoke import execute, fixture, generated_fragments, generated_unsafe_project, source
from il2cpp import Expr


def test_smoke_lifts_both_scalar_widths():
    f = generated_fragments()
    assert f["sqrt_float"] == "(float)Math.Sqrt(value)"
    assert f["sqrt_double"] == "Math.Sqrt(value)"


def test_smoke_preserves_allocation_and_sret_identity():
    f = generated_fragments()
    assert f["first_array"] != f["second_array"]
    assert f["array_body"].count("new string[2]") == 2
    assert f["array_body"].count('= "left";') == 1
    assert f["array_body"].count('= "right";') == 1
    assert f["sret_body"] == "s_40 = s_20.point;"
    assert "static float SqrtFloat" in source(f)


def test_real_project_writer_enables_the_unsafe_blocks_it_emits(tmp_path):
    project = generated_unsafe_project(tmp_path)
    root = ET.parse(project).getroot()
    assert root.findtext("PropertyGroup/AllowUnsafeBlocks") == "true"
    assert root.findtext("PropertyGroup/TargetFramework") == "netstandard2.1"
    assert root.findtext("PropertyGroup/AssemblyName") == "UnsafeSmoke"


def test_unknown_sret_receiver_keeps_both_slots_and_does_not_select_buffer_owner():
    lift = fixture()
    # RCX's type would select the Ray candidate under the old receiver lookup.
    # RDX has no pointee proof, so retain the marker and both pointer arguments.
    lift.regs = {"RCX": Expr("&s_40", (2, 0x11 << 16), "ptr"),
                 "RDX": Expr("&s_20", None, "ptr")}
    execute(lift, "e8fb0f0000")
    assert [line for _, line, _ in lift.out] == [
        "var t0 = sub_2000/*shared body, 2 candidates*/(&s_40, &s_20);"
    ]