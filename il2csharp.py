"""il2csharp: IL2CPP metadata + native code to C# source.

Entry point only.  The implementation lives in the il2cpp package:
  il2cpp/runtime/  metadata, registrations, type/field/EH tables (Il2Cpp)
  il2cpp/lifter/   x86-64 -> pseudo-C# expression lifter (Lifter)
  il2cpp/dec/      CFG -> structured control flow -> C# text (Decompiler)
  il2cpp/emitter.py, headers.py, cli.py   output assembly

Usage: python il2csharp.py <game-dir|metadata> -o <outdir>
"""
import sys

from il2cpp.cli import main

if __name__ == '__main__':
    sys.exit(main(sys.argv))
