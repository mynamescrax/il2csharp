import json

from il2cpp.cli import main
from il2cpp.emitter import Emitter


def test_help_lists_machine_flags():
    try:
        main(['il2csharp', '--help'])
    except SystemExit as ex:
        assert ex.code == 0


def test_missing_target_is_a_usage_error():
    try:
        main(['il2csharp'])
        raise AssertionError('expected argparse to exit')
    except SystemExit as ex:
        assert ex.code == 2


def test_write_bodies_is_address_keyed(tmp_path):
    class _M:
        addr = 0x180001000

    em = Emitter.__new__(Emitter)
    em.bodies = {}
    em._record_body(_M(), ['return 1;', 'return 2;'])
    path = tmp_path / 'bodies.json'
    em.write_bodies(str(path))
    payload = json.loads(path.read_text(encoding='utf-8'))
    assert payload == {'0x180001000': 'return 1;\nreturn 2;'}
