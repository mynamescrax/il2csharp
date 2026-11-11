from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.text import _int_lit

GPRS = ['RAX', 'RCX', 'RDX', 'RBX', 'RSP', 'RBP', 'RSI', 'RDI',
        'R8', 'R9', 'R10', 'R11', 'R12', 'R13', 'R14', 'R15']
GPR_ALIAS = {
    'AL': 'RAX', 'CL': 'RCX', 'DL': 'RDX', 'BL': 'RBX', 'SIL': 'RSI', 'DIL': 'RDI',
    'BPL': 'RBP', 'SPL': 'RSP', 'R8B': 'R8', 'R9B': 'R9', 'R10B': 'R10', 'R11B': 'R11',
    'R12B': 'R12', 'R13B': 'R13', 'R14B': 'R14', 'R15B': 'R15',
    'AX': 'RAX', 'CX': 'RCX', 'DX': 'RDX', 'BX': 'RBX', 'SI': 'RSI', 'DI': 'RDI',
    'BP': 'RBP', 'SP': 'RSP', 'R8W': 'R8', 'R9W': 'R9', 'R10W': 'R10', 'R11W': 'R11',
    'R12W': 'R12', 'R13W': 'R13', 'R14W': 'R14', 'R15W': 'R15',
    'EAX': 'RAX', 'ECX': 'RCX', 'EDX': 'RDX', 'EBX': 'RBX', 'ESI': 'RSI', 'EDI': 'RDI',
    'EBP': 'RBP', 'ESP': 'RSP', 'R8D': 'R8', 'R9D': 'R9', 'R10D': 'R10', 'R11D': 'R11',
    'R12D': 'R12', 'R13D': 'R13', 'R14D': 'R14', 'R15D': 'R15',
}
GPR_NAMES = {getattr(IReg, n): n for n in GPRS} if HAVE_ICED else {}
# tuple, not set: _fresh_unknowns mints vN names in iteration order, and a
# set of strings iterates hash-seeded, numbering them differently every run
VOLATILE = ('RAX', 'RCX', 'RDX', 'R8', 'R9', 'R10', 'R11')
ARG_REGS = ['RCX', 'RDX', 'R8', 'R9']


def _reg_size(r):
    """Byte width of an iced Register, or 0 when unavailable (fix 61c:
    a zero-extension's mask must match the SOURCE width)."""
    try:
        from iced_x86 import RegisterExt
        return RegisterExt.size(r)
    except Exception:
        return 0


# --- flag-specific branch recovery (fix 60) ---------------------------
# The six jumps CMP_OPS deliberately never mapped -- JS/JNS/JO/JNO/JP/JNP --
# and their CMOV twins read a single flag rather than a comparison, so they
# have no operator to splice. What they mean is decidable from WHICH
# instruction set the flags, which `Lifter.flags`' property setter records
# in `_flags_mn`. Census: work/census_b52_unknown.py.
# SF|PF: the two flags fix 60 reads. An instruction writing either
# without a modelled handler must not leave an older setter standing.
_SFPF = 0
if HAVE_ICED:
    try:
        from iced_x86 import RflagsBits as _RB
        _SFPF = _RB.SF | _RB.PF
    except ImportError:
        _SFPF = 0
_SIGN_SETTERS = set()
_FLOAT_SETTERS = set()
_JS_MN = _JNS_MN = _JP_MN = _JNP_MN = _TEST_MN = None
if HAVE_ICED:
    # exactly the mnemonics whose handler assigns `flags = (result, 0)`.
    # NEG is deliberately absent: it writes SF on the real machine but the
    # lifter models no flag write for it, so trusting _flags_mn there would
    # derive the condition from an OLDER setter (see the NEG invalidation
    # below, which makes that impossible rather than merely unlikely).
    for _n in ('ADD', 'SUB', 'INC', 'DEC', 'AND', 'OR', 'XOR', 'SHL', 'SHR',
               'SAR'):
        _m = getattr(Mnemonic, _n, None)
        if _m is not None:
            _SIGN_SETTERS.add(_m)
    for _n in ('COMISS', 'COMISD', 'UCOMISS', 'UCOMISD'):
        _m = getattr(Mnemonic, _n, None)
        if _m is not None:
            _FLOAT_SETTERS.add(_m)
    _JS_MN = getattr(Mnemonic, 'JS', None)
    _JNS_MN = getattr(Mnemonic, 'JNS', None)
    _JP_MN = getattr(Mnemonic, 'JP', None)
    _JNP_MN = getattr(Mnemonic, 'JNP', None)
    _TEST_MN = getattr(Mnemonic, 'TEST', None)
_SIGN_JUMPS = {x for x in (_JS_MN, _JNS_MN) if x is not None}
# a CMOVcc reads the same flag as the Jcc of the same suffix, so the
# two consumers share one derivation
_CMOV_AS_J = {}
if HAVE_ICED:
    for _c, _j in (('CMOVS', 'JS'), ('CMOVNS', 'JNS'),
                   ('CMOVP', 'JP'), ('CMOVNP', 'JNP')):
        _cm, _jm = getattr(Mnemonic, _c, None), getattr(Mnemonic, _j, None)
        if _cm is not None and _jm is not None:
            _CMOV_AS_J[_cm] = _jm
_NEG_JUMPS = {x for x in (_JS_MN,) if x is not None}
_PARITY_JUMPS = {x for x in (_JP_MN, _JNP_MN) if x is not None}
_UNORDERED_JUMPS = {x for x in (_JP_MN,) if x is not None}
_DBL_SETTERS = set()
if HAVE_ICED:
    for _n in ('COMISD', 'UCOMISD'):
        _m = getattr(Mnemonic, _n, None)
        if _m is not None:
            _DBL_SETTERS.add(_m)

# characters that mean the text is a composite expression, so `X < 0` would
# re-associate: C# binds `&`, `|`, `^` and the shifts LOOSER than `<`, so an
# unparenthesised `a & b < 0` silently means `a & (b < 0)`.
_NEEDS_PAREN = set(' +-*/%&|^<>=!?:')


def _paren(t):
    return t if not (set(t) & _NEEDS_PAREN) else '(%s)' % t


def _is_non_nan_literal(t):
    """True when `t` parses as a numeric literal (never NaN). -- fix 106

    No numeric literal spelling denotes NaN (NaN renders as
    `float.NaN`/`double.NaN`), so an `IsNaN(<literal>)` arm is
    provably false and the parity-jump fold drops it. Integer
    spellings reuse `_int_lit` (hex/decimal, fix87 `0f`/`1d`
    identities); anything else must float-parse finite. Names,
    unknowns, member access and exotic spellings keep their arm.
    """
    if not t:
        return False
    try:
        if _int_lit(t) is not None:
            return True
    except Exception:
        pass
    try:
        s = t.strip()
        if s[:1] in ('+', '-'):
            s = s[1:]
        if not s or s[:2].lower() == '0x':
            return False
        if not s[:1].isdigit() and s[:1] != '.':
            return False
        s = s.rstrip('uUlL')
        if s[-1:] in ('f', 'F', 'd', 'D'):
            s = s[:-1]
        v = float(s)
        return v == v
    except (ValueError, OverflowError):
        return False


def flag_cond(setter, br, lt, rt):
    """C# text for a flag-specific branch, or None when it is not derivable.

    `setter` is the mnemonic that last wrote the flags (Lifter._flags_mn),
    `br` the branch/CMOV mnemonic, `lt`/`rt` the rendered flags operands.
    """
    if setter is None or br is None:
        return None
    sign = None
    if br in _SIGN_JUMPS:
        if setter in _SIGN_SETTERS:
            # arithmetic parks its RESULT in the lhs slot with a 0 rhs, so
            # SF is simply the sign of that result
            sign = lt
        elif setter == _TEST_MN:
            # `test a,a` (the overwhelmingly common form) sets SF to the
            # sign of a; `test a,b` to the sign of a & b
            sign = lt if rt in ('null', '0', lt, '?') else '%s & %s' % (lt, rt)
        else:
            # cmp a,b sets SF to sign(a-b), which is NOT `a < b` when the
            # subtraction can overflow -- and the census finds no such site
            # in this corpus, so it stays honest rather than guessed
            return None
        if not sign or sign == '?':
            return None
        return '%s %s 0' % (_paren(sign), '<' if br in _NEG_JUMPS else '>=')
    if br in _PARITY_JUMPS and setter in _FLOAT_SETTERS:
        # PF after an SSE compare means UNORDERED: at least one operand is
        # NaN. This is the `x != x` idiom MSVC emits for float equality.
        if not lt or not rt or lt == '?' or rt in ('?', 'null'):
            return None
    if br in _PARITY_JUMPS and setter in _FLOAT_SETTERS:
        # PF after an SSE compare means UNORDERED: at least one operand is
        # NaN. This is the `x != x` idiom MSVC emits for float equality.
        if not lt or not rt or lt == '?' or rt in ('?', 'null'):
            return None
        ty = 'double' if setter in _DBL_SETTERS else 'float'
        arms = []
        if not _is_non_nan_literal(lt):
            arms.append('%s.IsNaN(%s)' % (ty, lt))
        if not _is_non_nan_literal(rt):
            arms.append('%s.IsNaN(%s)' % (ty, rt))
        if not arms:
            return None
        c = ' || '.join(arms)
        return c if br in _UNORDERED_JUMPS else '!(%s)' % c
    return None
ARG_XMM = ['XMM0', 'XMM1', 'XMM2', 'XMM3']

# Il2CppClass field offsets for this Unity generation (6000.0 / metadata v31, x64).
# KLASS_VTABLE is the trailing VirtualInvokeData[] -- NOT the same as
# KLASS_STATIC_FIELDS; treating them as one offset shifts every virtual call by
# 8 slots. Verified two ways on Unity 6000.0.69f1: TextMeshProUGUI.set_text is
# vtable slot 66 and is called through [klass+0x558] (0x558 - 66*16 = 0x138),
# and 0x138 keeps 343/349 observed call sites inside the receiver's
# vtable_count where 0xB8 keeps only 247.
KLASS_STATIC_FIELDS = 0xB8
KLASS_INITIALIZED = 0xE4
KLASS_VTABLE = 0x138
# Il2CppClass_1.element_class: image@0, gc_desc@8, name@16, namespaze@24,
# byval_arg@32 (16 bytes: pointer + bits + padding), this_arg@48 (16
# bytes), element_class@64. For an array klass this is the element type's
# klass; for any other klass it is NULL, which is why the fold in
# `_elem_klass_name` requires an array-typed base. Same Unity 6000.0/v31
# calibration as the offsets above.
KLASS_ELEMENT_CLASS = 0x40

# instructions that store to a memory destination, and the C# operator for the
# read-modify-write forms (`add [this+0x20], 11`)
if HAVE_ICED:
    STORE_MNEMONICS = {
        Mnemonic.MOV, Mnemonic.MOVSS, Mnemonic.MOVSD, Mnemonic.MOVUPS,
        Mnemonic.MOVAPS, Mnemonic.MOVUPD, Mnemonic.MOVAPD, Mnemonic.MOVQ,
        Mnemonic.MOVD, Mnemonic.MOVDQA, Mnemonic.MOVDQU,
    }
    RMW_OPS = {
        Mnemonic.ADD: '+', Mnemonic.SUB: '-', Mnemonic.IMUL: '*',
        Mnemonic.AND: '&', Mnemonic.OR: '|', Mnemonic.XOR: '^',
        Mnemonic.SHL: '<<', Mnemonic.SHR: '>>', Mnemonic.SAR: '>>',
        Mnemonic.ADDSS: '+', Mnemonic.ADDSD: '+', Mnemonic.SUBSS: '-',
        Mnemonic.SUBSD: '-', Mnemonic.MULSS: '*', Mnemonic.MULSD: '*',
        Mnemonic.DIVSS: '/', Mnemonic.DIVSD: '/',
        Mnemonic.INC: '++', Mnemonic.DEC: '--',
    }
else:
    STORE_MNEMONICS = set()
    RMW_OPS = {}

