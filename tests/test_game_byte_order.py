"""Check the framework implementation itself, not a call to the host BCL."""
import os
import shutil

import pytest

from dotnet_case import run_case
from il2cpp.cli import main


@pytest.mark.game
def test_emitted_shift_binary_primitives(tmp_path):
    metadata = os.getenv('IL2CSHARP_METADATA')
    binary = os.getenv('IL2CSHARP_BINARY')
    if not metadata or not binary:
        pytest.skip('set fixture paths to a Shift At Midnight build')
    out = tmp_path / 'out'
    assert main(['il2csharp', '--metadata', metadata, '--binary', binary, '--strict',
                 '--only', 'mscorlib', '--types', 'System.Buffers.Binary.BinaryPrimitives',
                 '-o', str(out)]) == 0
    source, = out.rglob('BinaryPrimitives.cs')
    runner = tmp_path / 'runner'
    runner.mkdir()
    shutil.copy(source, runner)
    (runner / 'Program.cs').write_text('''
using System;
using BP = System.Buffers.Binary.BinaryPrimitives;
if (typeof(BP).Assembly != typeof(Program).Assembly) throw new Exception("wrong assembly");
for (int i = 0; i <= ushort.MaxValue; ++i)
    if (BP.ReverseEndianness((ushort)i) != (i % 256) * 256 + i / 256)
        throw new Exception("ushort: " + i);
foreach (uint n in new uint[] {0, 1, 0x80, 0x80000000, 0x12345678, 0xfffffffe, uint.MaxValue})
{
    byte[] bytes = BitConverter.GetBytes(n);
    Array.Reverse(bytes);
    if (BP.ReverseEndianness(n) != BitConverter.ToUInt32(bytes) ||
        BP.ReverseEndianness(unchecked((int)n)) != BitConverter.ToInt32(bytes))
        throw new Exception("32-bit: " + n);
}
Console.WriteLine("byte order OK");
''', encoding='utf-8')
    assert 'byte order OK' in run_case(tmp_path, runner)
