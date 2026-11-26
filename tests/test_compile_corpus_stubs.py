import json
import shutil
from types import SimpleNamespace

import pytest

from il2cpp.emitter import Emitter
from tools.compile_corpus import compile_tree


@pytest.mark.skipif(not shutil.which('dotnet'), reason='Roslyn required')
def test_compiler_accepts_merged_emitter_stubs(tmp_path):
    emitter = Emitter.__new__(Emitter)
    emitter.il = SimpleNamespace(addr_candidates={})
    for image, targets in [('A', {'ab', 'cd'}), ('B', {'cd'})]:
        folder = tmp_path / image
        folder.mkdir()
        (folder / '__SharedBodyStubs.cs').write_text(emitter._stub_file_text(targets))
    (tmp_path / 'Caller.cs').write_text('using static __SharedBodyStubs;\n'
                                        'class Caller { object Run() => sub_ab(sub_cd()); }')
    report = tmp_path / 'report.json'
    assert compile_tree(tmp_path, report) == 0
    assert json.loads(report.read_text())['merged_stubs'] == 2
