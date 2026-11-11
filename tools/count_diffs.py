import os
import sys
import hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # il2csharp/ project root after 2026-09-08 consolidation

def get_files_with_content(root):
    files = {}
    for dp, dnames, fnames in os.walk(root):
        for f in fnames:
            path = os.path.join(dp, f)
            rel = os.path.relpath(path, root)
            with open(path, 'r', encoding='utf-8', errors='replace') as fh:
                content = fh.read()
            files[rel] = content
    return files

final_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'final_out', 'Assembly-CSharp')
b70_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'b70_out1', 'Assembly-CSharp')
# NOTE: b70_out1 was reaped at the b42_out1 promotion; pass explicit paths or it reports missing.

final_files = get_files_with_content(final_dir)
b70_files = get_files_with_content(b70_dir)

same_names = final_files.keys() & b70_files.keys()
diff_count = 0
same_count = 0

for name in same_names:
    if final_files[name] != b70_files[name]:
        diff_count += 1
    else:
        same_count += 1

print(f'Files with same names: {len(same_names)}')
print(f'Different content: {diff_count}')
print(f'Same content: {same_count}')

# Show some examples of differences
diff_examples = 0
for name in same_names:
    if final_files[name] != b70_files[name]:
        if diff_examples < 5:
            final_lines = final_files[name].split('\n')[:3]
            b70_lines = b70_files[name].split('\n')[:3]
            print(f'\n--- {name} ---')
            print('final_out:')
            for l in final_lines:
                print(f'  {l[:80]}')
            print('b70_out1:')
            for l in b70_lines:
                print(f'  {l[:80]}')
            diff_examples += 1