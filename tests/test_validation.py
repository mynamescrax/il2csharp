import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from validate_corpus import audit_body, mask_literals


def test_literals_and_comments_do_not_affect_structural_audit():
    body = [
        'var a = "L_dead: { goto L_missing; f(a, , b) }";',
        'var b = @"quoted "" { text";',
        "var c = '}';",
        'var d = $"{{ literal }} {value}";',
        '// goto L_missing; }',
        '/* { f(,); */',
    ]
    assert not any(audit_body(body).values())


def test_mask_preserves_offsets_and_newlines():
    text = 'a("x\\\"y", \'{\'); // ignored\n/*\n}*/ z'
    masked = mask_literals(text)
    assert len(text) == len(masked)
    assert [i for i, ch in enumerate(text) if ch == "\n"] == [
        i for i, ch in enumerate(masked) if ch == "\n"
    ]
    assert "z" in masked


def test_into_block_and_sibling_scope_jumps():
    assert audit_body(["goto L_1;", "if (x) {", "L_1: ;", "}"])["into_block_gotos"] == 1
    assert audit_body(["{ goto L_1; }", "{ L_1: ; }"])["into_block_gotos"] == 1


def test_same_or_outer_scope_jump_is_not_into_block():
    assert audit_body(["{ goto L_1; }", "L_1: ;"])["into_block_gotos"] == 0
    assert audit_body(["L_1: ;", "goto L_1;"])["into_block_gotos"] == 0


def test_dangling_goto_and_brace_underflow():
    result = audit_body(["}", "{", "goto L_dead;"])
    assert result["brace_unclosed"] == result["brace_underflow"] == result["dangling_gotos"] == 1


def test_empty_argument_detection():
    assert audit_body(["f(a, , b);", "g(, a);", "h(a, );"])["empty_args"] == 3


def test_literals_are_real_arguments_not_empty_slots():
    assert audit_body(['f(a, "text", b);', "g('x', 'y');", 'h(@"quoted "" text");'])["empty_args"] == 0


def test_array_ranks_and_unbound_generics_are_not_empty_arguments():
    assert audit_body(["object[,,] a;", "var t = typeof(Generic<,,>);"])["empty_args"] == 0


def test_comment_without_an_operand_really_is_an_empty_argument():
    assert audit_body(["f(a, /* absent */, b);"])["empty_args"] == 1


def test_parser_gate_rejects_hidden_zero_width_recovery(tmp_path):
    import json
    from types import SimpleNamespace
    from validate_corpus import parse_tree
    (tmp_path / "broken.cs").write_text(
        "class C { void M() { var x = ((byte*)? + p + 4 : default)[0]; } }"
    )
    report_path = tmp_path / "gate.json"
    assert parse_tree(SimpleNamespace(tree=str(tmp_path), report=str(report_path))) == 1
    report = json.loads(report_path.read_text())
    assert report["bad_files"] == 1
    assert report["errors"] + report["missing"] + report["recovery_nodes"] > 0

def test_sweep_comparison_works_after_reports_are_moved(tmp_path):
    import gzip
    import json
    from types import SimpleNamespace
    from validate_corpus import compare
    for name, body_hash in [('before', 'old'), ('after', 'new')]:
        manifest = tmp_path / (name + '.methods.jsonl.gz')
        with gzip.open(manifest, 'wt') as f:
            f.write(json.dumps({'mi': 7, 'va': '0x1000', 'type': 'T', 'name': 'M',
                                'sha256': body_hash, 'lines': 1}) + '\n')
        (tmp_path / (name + '.json')).write_text(json.dumps({
            'metadata_sha256': 'metadata', 'binary_sha256': 'binary',
            'method_manifest': '/old/machine/' + manifest.name,
        }))
    report = tmp_path / 'comparison.json'
    assert compare(SimpleNamespace(before=str(tmp_path/'before.json'),
                                   after=str(tmp_path/'after.json'), report=str(report))) == 0
    assert json.loads(report.read_text())['changed_method_count'] == 1
