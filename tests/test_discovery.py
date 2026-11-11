from pathlib import Path

import pytest

from il2cpp import find_game_files


def touch(root, relative):
    p = root / relative
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch()
    return str(p)


@pytest.mark.parametrize("binary", ["GameAssembly.dll", "libil2cpp.so"])
@pytest.mark.parametrize("target_kind", ["directory", "metadata", "binary"])
def test_flat_dump(tmp_path, binary, target_kind):
    meta = touch(tmp_path, "global-metadata.dat")
    native = touch(tmp_path, binary)
    target = {"directory": str(tmp_path), "metadata": meta, "binary": native}[target_kind]
    assert find_game_files(target) == (meta, native)


@pytest.mark.parametrize("target_kind", ["directory", "metadata", "binary"])
def test_unity_layout(tmp_path, target_kind):
    meta = touch(tmp_path, "Game_Data/il2cpp_data/Metadata/global-metadata.dat")
    native = touch(tmp_path, "GameAssembly.dll")
    target = {"directory": str(tmp_path), "metadata": meta, "binary": native}[target_kind]
    assert find_game_files(target) == (meta, native)


def test_pathlike_input(tmp_path):
    meta = touch(tmp_path, "global-metadata.dat")
    native = touch(tmp_path, "GameAssembly.dll")
    assert find_game_files(Path(meta)) == (meta, native)


def test_missing_inputs(tmp_path):
    assert find_game_files(str(tmp_path / "missing")) == (None, None)
    assert find_game_files(str(tmp_path)) == (None, None)


def test_metadata_without_binary(tmp_path):
    meta = touch(tmp_path, "global-metadata.dat")
    assert find_game_files(meta) == (meta, None)


def test_binary_without_metadata(tmp_path):
    native = touch(tmp_path, "GameAssembly.dll")
    assert find_game_files(native) == (None, native)


def test_explicit_pair_in_separate_directories(tmp_path):
    meta = touch(tmp_path, "metadata/renamed.dat")
    native = touch(tmp_path, "native/renamed.dll")
    assert find_game_files(None, metadata=meta, binary=native) == (meta, native)


def test_explicit_binary_prevents_accidental_neighbor_pairing(tmp_path):
    meta = touch(tmp_path, "global-metadata.dat")
    touch(tmp_path, "GameAssembly.dll")
    touch(tmp_path, "libil2cpp.so")
    native = touch(tmp_path, "selected/other.dll")
    assert find_game_files(meta, binary=native) == (meta, native)


def test_explicit_metadata_resolves_ambiguous_binary_directory(tmp_path):
    touch(tmp_path, "First/global-metadata.dat")
    meta = touch(tmp_path, "Second/global-metadata.dat")
    native = touch(tmp_path, "GameAssembly.dll")
    assert find_game_files(native, metadata=meta) == (meta, native)


def test_multiple_metadata_files_are_not_silently_guessed(tmp_path):
    touch(tmp_path, "First/global-metadata.dat")
    touch(tmp_path, "Second/global-metadata.dat")
    touch(tmp_path, "GameAssembly.dll")
    with pytest.raises(ValueError, match="metadata"):
        find_game_files(str(tmp_path))


def test_multiple_adjacent_binaries_are_not_silently_guessed(tmp_path):
    meta = touch(tmp_path, "global-metadata.dat")
    touch(tmp_path, "GameAssembly.dll")
    touch(tmp_path, "libil2cpp.so")
    with pytest.raises(ValueError, match="binar"):
        find_game_files(meta)


def test_directory_search_does_not_pair_with_parent_game(tmp_path):
    touch(tmp_path, "GameAssembly.dll")
    meta = touch(tmp_path, "unrelated/global-metadata.dat")
    assert find_game_files(str(tmp_path / "unrelated")) == (meta, None)