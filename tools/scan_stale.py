"""Count stale-expression sites in emitted bodies: a store `Lv = RHS;`
whose RHS reads `Lv`, with the same RHS text reused later in the body.
Reads as C#, the later reuse picks up the post-store value -- exactly what
kill-on-write is supposed to eliminate.

Only symbolic lvalues count (fields, array elements, derefs): their reads
re-render at each use, so a store between two uses changes what the text
means. A named local is a real variable with sequential semantics --
`num2 = num2 + 1; ... num2 + 1` reads the incremented value, which is
correct, not stale.

Usage: python tools/scan_stale.py <output_root>
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from il2cpp import _mentions

STORE_RX = re.compile(r'^\s*([^=]+?) = (.+);\s*$')
# a renamed local or raw temp: variables, not symbolic locations
LOCAL_RX = re.compile(r'^(?:obj|num|flag|real|t|v)\d+$|^s_[0-9a-fA-F]+$')


def scan(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        text = f.read()
    lines = text.splitlines(True)
    cands = []
    for i, ln in enumerate(lines):
        m = STORE_RX.match(ln.rstrip('\n'))
        if m:
            lv, rhs = m.group(1).strip(), m.group(2).strip()
            if lv and rhs != lv and _mentions(rhs, lv) \
                    and not LOCAL_RX.match(lv):
                cands.append((i, ln.strip(), rhs))
    if not cands:
        return 0
    n = 0
    for i, own, rhs in cands:
        if any(rhs in lines[j] and lines[j].strip() != own
               for j in range(i + 1, len(lines))):
            n += 1
    return n


def main():
    root = sys.argv[1]
    total = files = 0
    for dirpath, _, fns in os.walk(root):
        for fn in fns:
            if fn.endswith('.cs'):
                total += scan(os.path.join(dirpath, fn))
                files += 1
    print('stale-expression sites: %d across %d files' % (total, files))


if __name__ == '__main__':
    main()
