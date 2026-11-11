from types import SimpleNamespace as NS

import pytest

import il2cpp.cli as app  # main() resolves Emitter/Metadata/... in this module


class Backend:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    def lift(self, *args):
        self.calls += 1
        if self.fail:
            raise RuntimeError("test failure")
        return ["return;"]

    lift_method = lift


def emitter(structured_fails=False, linear_fails=False, limit=None):
    em = app.Emitter.__new__(app.Emitter)
    em.with_bodies, em.verbose = True, False
    em.max_methods = limit
    em.il = NS(types=[(0, 0x01 << 16)])
    em.lifter, em.decompiler = Backend(linear_fails), Backend(structured_fails)
    em.lifted = em.failed = em.fallbacks = 0
    method = NS(index=7, addr=0x180001000, return_type=0, name="Example")
    return em, method, NS(name="Demo")


def test_structured_success_is_not_a_fallback():
    em, method, td = emitter()
    assert em._lift_body(method, td) == []
    assert (em.lifted, em.failed, em.fallbacks) == (1, 0, 0)
    assert em.lifter.calls == 0


def test_linear_recovery_is_visible_in_fallback_count():
    em, method, td = emitter(structured_fails=True)
    assert em._lift_body(method, td) == []
    assert (em.lifted, em.failed, em.fallbacks) == (1, 0, 1)
    assert em.lifter.calls == 1


def test_double_failure_counts_both_the_fallback_attempt_and_failed_body():
    em, method, td = emitter(structured_fails=True, linear_fails=True)
    assert "lift failed" in em._lift_body(method, td)[0]
    assert (em.lifted, em.failed, em.fallbacks) == (0, 1, 1)


def test_verbose_fallback_identifies_method(capsys):
    em, method, td = emitter(structured_fails=True)
    em.verbose = True
    em._lift_body(method, td)
    output = capsys.readouterr().err
    assert "mi=7" in output and "0x180001000" in output and "Demo.Example" in output


def test_method_limit_does_not_count_a_skipped_body():
    em, method, td = emitter(limit=0)
    assert em._lift_body(method, td) == [
        'throw new global::System.NotImplementedException("Method body was not recovered.");'
    ]
    assert (em.lifted, em.failed, em.fallbacks) == (0, 0, 0)


def test_cli_rejects_negative_limit():
    with pytest.raises(SystemExit) as ex:
        app.main(["il2csharp", "not-needed", "--max-methods", "-1"])
    assert ex.value.code == 2


def test_cli_requires_input():
    with pytest.raises(SystemExit) as ex:
        app.main(["il2csharp"])
    assert ex.value.code == 2


def test_cli_missing_file_returns_error_without_traceback(tmp_path, capsys):
    rc = app.main(["il2csharp", "--metadata", str(tmp_path / "missing.dat"),
                   "--binary", str(tmp_path / "missing.dll")])
    assert rc == 1
    assert "error:" in capsys.readouterr().out


@pytest.mark.parametrize(
    "strict,failed,fallbacks,emit_failed,backend,expected",
    [
        (False, 0, 0, 0, True, 0),
        (False, 0, 1, 0, True, 0),
        (True, 0, 1, 0, True, 1),
        (True, 0, 0, 0, True, 0),
        (False, 1, 0, 0, True, 1),
        (False, 0, 0, 1, True, 1),
        (True, 0, 0, 0, False, 1),
    ],
)
def test_cli_failure_exit_policy(tmp_path, monkeypatch, strict, failed, fallbacks,
                                 emit_failed, backend, expected):
    metadata = tmp_path / "global-metadata.dat"
    binary = tmp_path / "GameAssembly.dll"
    metadata.touch()
    binary.touch()
    meta = NS(version=31, typedefs=[], methods=[], images=[], string_literals=[])
    image = NS(sections=[], exports=[])
    il = NS(meta=meta, bin=image, _mod_ptr_cache={}, assign_images=lambda: None,
            find_registrations=lambda: None, load_function_bounds=lambda: None,
            resolve_method_addrs=lambda: None)
    em = NS(lifted=1, failed=failed, fallbacks=fallbacks, emit_failed=emit_failed,
            lifter=object() if backend else None, decompiler_error=None,
            write_script_json=lambda p: None, write_string_literals=lambda p: None)
    monkeypatch.setattr(app, "Metadata", lambda p: meta)
    monkeypatch.setattr(app, "load_binary", lambda p: image)
    monkeypatch.setattr(app, "Il2Cpp", lambda m, b: il)
    monkeypatch.setattr(app, "Emitter", lambda *a, **kw: em)
    monkeypatch.setattr(app, "is_arm64_binary", lambda b: False)
    argv = ["il2csharp", str(tmp_path), "-o", str(tmp_path / "out")]
    if strict:
        argv.append("--strict")
    assert app.main(argv) == expected
