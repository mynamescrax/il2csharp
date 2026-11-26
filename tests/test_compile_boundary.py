"""The layout, not a visibility rewrite, determines which override is legal."""
import shutil

import pytest

from tools.compile_boundary import check_boundary


@pytest.mark.skipif(not shutil.which('dotnet'), reason='Roslyn required')
def test_accessibility_depends_on_image_boundary(tmp_path):
    base, derived = tmp_path / 'Library', tmp_path / 'Client'
    base.mkdir()
    derived.mkdir()
    (base / 'Root.cs').write_text('public class Root { protected internal virtual int Value => 0; }')
    target = derived / 'Child.cs'
    for access, expected_merged, expected_split in [('protected', 1, 0), ('protected internal', 0, 1)]:
        target.write_text(f'public class Child : Root {{ {access} override int Value => 1; }}')
        report = check_boundary(base, derived)
        assert report['base_reference']['exit_code'] == 0
        for stage, expected in [('merged_control', expected_merged), ('derived_reference', expected_split)]:
            assert report[stage]['errors_by_code'] == ({'CS0507': 1} if expected else {})
            assert report[stage]['exit_code'] == expected
