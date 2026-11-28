import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from replay_shift_gates import classify,gates


def test_replay_keeps_compiler_failures_and_failed_observations_separate():
    assert classify(1,'foo.cs(2,4): error CS1001: Identifier expected\n1 failed in 1.0s')=='C# compile failure'
    assert classify(1,'Unhandled exception. System.Exception: stale receiver\n1 failed in 2.0s')=='C# runtime mismatch'
    assert classify(1,'E       assert False\n1 failed in 1.2s')=='pre-run assertion'
    assert classify(1,'tests/test_game_x.py:17: in test_a\nE   ValueError: substring not found\n1 failed in 1.2s')=='pre-run extraction'
    assert classify(0,'1 skipped in 1.1s')=='other (inspect log)'
    with pytest.raises(ValueError):gates('whole 42 tests/test_game_x.py::test_a\nwhole 43 tests/test_game_x.py::test_a')
