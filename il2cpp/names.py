from il2cpp.prelude import *  # noqa: F401,F403

def sanitize(n: str) -> str:
    if not n:
        return '_'
    n = n.replace('`', '_').replace('-', '_')
    n = re.sub(r'[^A-Za-z0-9_.<>-]', '_', n)
    if re.match(r'^\d', n):
        return '_' + n
    return n


CSHARP_KEYWORDS = frozenset("""abstract as async await base bool break byte case catch char checked class
const continue decimal default delegate do double dynamic else enum event explicit extern false
finally fixed float for foreach goto if implicit in int interface internal is lock long
nameof namespace new null object operator out override params private protected public readonly
ref return sbyte sealed short sizeof stackalloc static string struct switch this throw
true try typeof uint ulong unchecked unsafe ushort using virtual void volatile while yield
""".split())


def safe_ident(n: str) -> str:
    s = sanitize(n)
    return s if s not in CSHARP_KEYWORDS else s + '_'


def sanitize_qualifier(s: str) -> str:
    """sanitize() for explicit-interface qualifiers (`A.B.IFoo<T, U[]>`):
    generic structure (``<>[],``) survives while every identifier segment
    is sanitized. Plain sanitize() would eat the commas and brackets
    (`KeyValuePair<TKey, TValue>` -> `KeyValuePair<TKey__TValue>`, `T[]`
    -> `T__`), which no longer resolve to the implemented interface."""
    out = []
    cur = []
    def flush():
        if cur:
            out.append(sanitize(''.join(cur)))
            del cur[:]
    skip_spaces = False
    for ch in s:
        if ch == ' ':
            if skip_spaces:
                continue
            flush()
            skip_spaces = True
            continue
        skip_spaces = False
        if ch == ',':
            flush()
            out.append(', ')
            skip_spaces = True
        elif ch in '<>()[].*?&':
            flush()
            out.append(ch)
        else:
            cur.append(ch)
    flush()
    return ''.join(out)


def _repr_special_float(v, ty):
    """inf/nan have no literal form in C# — repr() would emit `inf.0d`/`nanf`,
    neither of which lexes. float/double expose them as const fields."""
    if v != v:
        return ty + '.NaN'
    if v == float('inf'):
        return ty + '.PositiveInfinity'
    if v == float('-inf'):
        return ty + '.NegativeInfinity'
    return None


def repr_f32(v):
    sp = _repr_special_float(v, 'float')
    if sp is not None:
        return sp
    try:
        orig = struct.unpack('<I', struct.pack('<f', v))[0]
    except Exception:
        s = repr(v)
        return s + 'f' if ('.' in s or 'e' in s or 'E' in s) else s + '.0f'
    best = None
    for prec in (1, 2, 3, 4, 5, 6, 7, 8, 9):
        s = format(v, '.' + str(prec) + 'g')
        try:
            bits = struct.unpack('<I', struct.pack('<f', float(s)))[0]
        except (ValueError, OverflowError, struct.error):
            continue
        if bits != orig:
            continue
        # shortest wins; ties prefer fixed point over exponent
        # (`10000` over `1e+04` -- the exponent form is never what
        # source says at equal length), then fewer digits.
        key = (len(s), 'e' in s.lower(), prec)
        if best is None or key < best[0]:
            best = (key, s)
    if best is None:
        s = repr(v)
    else:
        s = best[1]
    return s + 'f' if ('.' in s or 'e' in s or 'E' in s) else s + '.0f'


def repr_f64(v):
    sp = _repr_special_float(v, 'double')
    if sp is not None:
        return sp
    s = repr(v)
    return s + 'd' if ('.' in s or 'e' in s) else s + '.0d'


# ----------------------------------------------------------------------------
# il2cpp.h-style C header emitter (Il2CppDumper-compatible struct layout)
# ----------------------------------------------------------------------------
