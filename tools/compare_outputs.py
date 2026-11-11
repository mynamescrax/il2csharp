import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # il2csharp/ project root after 2026-09-08 consolidation

def get_files(root):
    files = set()
    for dp, dnames, fnames in os.walk(root):
        for f in fnames:
            files.add(os.path.join(dp, f))
    return files

final_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'final_out', 'Assembly-CSharp')
b70_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'b70_out1', 'Assembly-CSharp')
# NOTE: b70_out1 was reaped at the b42_out1 promotion; pass explicit paths or it reports missing.

final_files = get_files(final_dir)
b70_files = get_files(b70_dir)

only_final = final_files - b70_files
only_b70 = b70_files - final_files

print(f'final_out files: {len(final_files)}')
print(f'b70_out1 files: {len(b70_files)}')
print(f'Files only in final_out: {len(only_final)}')
print(f'Files only in b70_out1: {len(only_b70)}')

if only_final:
    print('\nFiles only in final_out:')
    for f in sorted(only_final)[:20]:
        print(f'  {os.path.relpath(f, final_dir)}')

if only_b70:
    print('\nFiles only in b70_out1:')
    for f in sorted(only_b70)[:20]:
        print(f'  {os.path.relpath(f, b70_dir)}')