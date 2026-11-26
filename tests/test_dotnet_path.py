"""Windows SDK first-run check; read the saved PATH without expanding %variables%."""
import sys
from subprocess import run

import pytest

import dotnet_case


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows user environment registry')
def test_fresh_cli_home_preserves_user_path(tmp_path, monkeypatch):
    import winreg

    def saved_path():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
                return winreg.QueryValueEx(key, 'Path')  # raw value and registry type
        except FileNotFoundError:
            return None

    home = tmp_path / 'home'
    assert not home.exists()
    runner = tmp_path / 'runner'
    runner.mkdir()
    (runner / 'Program.cs').write_text('System.Console.WriteLine("path-check-ok");', encoding='utf-8')

    # Check before allowing even `dotnet --version` to execute. A regression
    # should fail the test without exposing the real user's PATH to first run.
    def guarded_run(*args, **kwargs):
        env = kwargs['env']
        assert env.get('DOTNET_ADD_GLOBAL_TOOLS_TO_PATH') == 'false'
        assert env.get('DOTNET_CLI_HOME') == str(home)
        return run(*args, **kwargs)

    monkeypatch.delenv('DOTNET_ADD_GLOBAL_TOOLS_TO_PATH', raising=False)
    monkeypatch.setattr(dotnet_case.subprocess, 'run', guarded_run)
    before = saved_path()
    try:
        assert 'path-check-ok' in dotnet_case.run_case(tmp_path, runner).splitlines()
    finally:
        if saved_path() != before:
            pytest.fail('Saved HKCU\\Environment\\Path value or registry type changed')
