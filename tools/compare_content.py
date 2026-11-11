import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # il2csharp/ project root after 2026-09-08 consolidation

def get_files_relative(root):
    files = set()
    for dp, dnames, fnames in os.walk(root):
        for f in fnames:
            rel = os.path.relpath(os.path.join(dp, f), root)
            files.add(rel)
    return files

final_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'final_out', 'Assembly-CSharp')
b70_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'b70_out1', 'Assembly-CSharp')
# NOTE: b70_out1 was reaped at the b42_out1 promotion; pass explicit paths or it reports missing.

final_rel = get_files_relative(final_dir)
b70_rel = get_files_relative(b70_dir)

same_names = final_rel & b70_rel
only_final = final_rel - b70_rel
only_b70 = b70_rel - final_rel

print(f'final_out relative files: {len(final_rel)}')
print(f'b70_out1 relative files: {len(b70_rel)}')
print(f'Same file names: {len(same_names)}')
print(f'Only in final: {len(only_final)}')
print(f'Only in b70: {len(only_b70)}')

# Check a few same-named files for content differences
same_list = sorted(same_names)[:5]
print(f'\nChecking same-named files for content differences:')
for name in same_list:
    final_path = os.path.join(final_dir, name)
    b70_path = os.path.join(b70_dir, name)
    if os.path.exists(final_path) and os.path.exists(b70_path):
        with open(final_path, 'r', encoding='utf-8', errors='replace') as f:
            final_content = f.read()
        with open(b70_path, 'r', encoding='utf-8', errors='replace') as f:
            b70_content = f.read()
        if final_content != b70_content:
            print(f'  {name}: DIFFERENT')
            # Show first difference in line count or first few lines
            final_lines = final_content.split('\n')
            b70_lines = b70_content.split('\n')
            print(f'    final: {len(final_lines)} lines, b70: {len(b70_lines)} lines')
            if len(final_lines) != len(b70_lines):
                print(f'    Line count differs!')
            else:
                for i in range(min(5, len(final_lines))):
                    if final_lines[i] != b70_lines[i]:
                        print(f'    Line {i} differs')
                        print(f'    final: {final_lines[i][:100]}')
                        print(f'    b70: {b70_lines[i][:100]}')
        else:
            print(f'  {name}: same content')