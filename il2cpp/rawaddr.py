"""Fix 128, opt-in `--raw-addr`: compilable raw-address spelling.

The lifter spells a native field/slot access off a managed reference as
`((byte*)obj + 0x10)[0]`. C# rejects the `(byte*)` cast of a managed
reference (CS0030, ~111k gate errors), so the whole statement fails to
bind. Under `--raw-addr` the operand of every `(byte*)` cast is routed
through an explicit helper, `(byte*)__addr(obj)`, declared once per
assembly in `__RawAddr.cs`. Integer and pointer operands keep their
exact meaning (the helper overloads just perform the same cast); a
managed operand binds to the `object` overload, which throws: the
native address of a managed object is not something C# can produce, and
the output says so instead of guessing. Default output is unchanged.
"""
import re

CAST = '(byte*)'
HELPER = '__addr'
CLASS = '__RawAddr'

_IDENT = re.compile(r'@?[A-Za-z_]\w*')
_KEEP = frozenset(('null', 'true', 'false', 'default', 'new', 'sizeof',
                   'typeof', 'checked', 'unchecked', 'stackalloc', 'ref',
                   'out', 'in', 'await'))


def _match(line, i, open_ch, close_ch):
    """Index just past the bracket closing the one at `i`, or -1."""
    depth = 0
    n = len(line)
    j = i
    while j < n:
        c = line[j]
        if c == '"' or c == "'":
            j = _skip_literal(line, j)
            if j < 0:
                return -1
            continue
        if c == '/' and line.startswith('/*', j):
            e = line.find('*/', j + 2)
            if e < 0:
                return -1
            j = e + 2
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return -1


def _skip_literal(line, i):
    q = line[i]
    verbatim = q == '"' and i > 0 and line[i - 1] == '@'
    j = i + 1
    n = len(line)
    while j < n:
        c = line[j]
        if verbatim:
            if c == '"':
                if j + 1 < n and line[j + 1] == '"':
                    j += 2
                    continue
                return j + 1
        elif c == '\\':
            j += 2
            continue
        elif c == q:
            return j + 1
        j += 1
    return -1


def _operand_end(line, j):
    """End of the unary operand of a cast starting at `j`, or -1 when the
    operand is not a plain primary expression (literal, prefix operator,
    keyword...) and must stay as written."""
    n = len(line)
    if j >= n:
        return -1
    c = line[j]
    if c == '(':
        k = _match(line, j, '(', ')')
        if k < 0:
            return -1
        if k < n and (line[k].isalnum() or line[k] in '_@('):
            # `(T)e`: a nested cast; its operand ends the expression
            return _operand_end(line, k)
    else:
        m = _IDENT.match(line, j)
        if not m or m.group(0).lstrip('@') in _KEEP:
            return -1
        k = m.end()
    while k < n:
        c = line[k]
        if c == '.' and k + 1 < n and (line[k + 1].isalpha() or line[k + 1] in '_@'):
            m = _IDENT.match(line, k + 1)
            if not m:
                return -1
            k = m.end()
        elif c == '[':
            k2 = _match(line, k, '[', ']')
            if k2 < 0:
                return -1
            k = k2
        elif c == '(':
            k2 = _match(line, k, '(', ')')
            if k2 < 0:
                return -1
            k = k2
        elif c == '<':
            # `F<T>(x)` generic call or a glued comparison: leave as is
            return -1
        else:
            break
    return k


def rewrite_line(line):
    """Wrap each `(byte*)E` operand outside literals/comments."""
    if CAST not in line:
        return line
    out = []
    i = 0
    n = len(line)
    last = 0
    while i < n:
        c = line[i]
        if c == '"' or c == "'":
            j = _skip_literal(line, i)
            if j < 0:
                break
            i = j
            continue
        if c == '/' and i + 1 < n and line[i + 1] == '/':
            break
        if c == '/' and i + 1 < n and line[i + 1] == '*':
            j = line.find('*/', i + 2)
            if j < 0:
                break
            i = j + 2
            continue
        if line.startswith(CAST, i):
            j = i + len(CAST)
            k = _operand_end(line, j)
            if k > j and not line.startswith(HELPER + '(', j):
                operand = rewrite_line(line[j:k])
                out.append(line[last:j])
                out.append('%s(%s)' % (HELPER, operand))
                last = k
                i = k
                continue
            i = j
            continue
        i += 1
    if not out:
        return line
    out.append(line[last:])
    return ''.join(out)


def rewrite_lines(lines):
    """Rewrite a buffer; returns (new_lines, changed)."""
    changed = False
    res = []
    for ln in lines:
        s = ln.lstrip()
        if s.startswith('//'):
            res.append(ln)
            continue
        new = rewrite_line(ln)
        if new != ln:
            changed = True
        res.append(new)
    return res, changed


def helper_file_text():
    return '\n'.join([
        '// <auto-generated>',
        '// Raw native addresses used by the recovered bodies of this',
        '// assembly (`--raw-addr`). `(byte*)__addr(e)` marks a raw native',
        '// access whose base is `e`. Integer and pointer bases keep their',
        '// plain C# cast meaning; a managed reference has no C# address,',
        '// so the `object` overload throws instead of guessing one.',
        '// Generated by il2csharp; never hand-edit.',
        'internal static unsafe class %s' % CLASS,
        '{',
        '    internal static byte* %s(object o)' % HELPER,
        '    {',
        '        throw new System.NotSupportedException('
        '"raw native address of a managed object");',
        '    }',
        '    internal static byte* %s(void* p) { return (byte*)p; }' % HELPER,
        '    internal static byte* %s(long v) { return (byte*)v; }' % HELPER,
        '    internal static byte* %s(ulong v) { return (byte*)v; }' % HELPER,
        '    internal static byte* %s(System.IntPtr p) { return (byte*)p; }' % HELPER,
        '    internal static byte* %s(System.UIntPtr p) { return (byte*)p; }' % HELPER,
        '}',
    ]) + '\n'
