"""Shared static-only loading for the optional real-binary validation tools."""
import hashlib
import sys
from pathlib import Path


def load(source, metadata, binary):
    sys.path.insert(0, str(Path(source).resolve()))
    from il2cpp import Il2Cpp, Metadata, load_binary

    meta = Metadata(str(metadata))
    image = load_binary(str(binary))
    if image is None:
        raise ValueError("unsupported binary format")
    il = Il2Cpp(meta, image)
    il.assign_images()
    try:
        il.find_registrations()
    except RuntimeError:
        il.find_registrations_android()
    il.load_function_bounds()
    il.resolve_method_addrs()
    il.__dict__.setdefault('_mod_ptr_cache', {}).clear()
    return il


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def source_fingerprints(source):
    """Digest of every core source file: the launcher plus the il2cpp package.

    Replaces the old two-entry {il2csharp.py, decompiler.py} map, so a sweep
    report still pins the exact code that produced it.
    """
    root = Path(source)
    out = {}
    launcher = root / "il2csharp.py"
    if launcher.exists():
        out["il2csharp.py"] = sha256(launcher)
    for path in sorted((root / "il2cpp").rglob("*.py")):
        out[path.relative_to(root).as_posix()] = sha256(path)
    return out