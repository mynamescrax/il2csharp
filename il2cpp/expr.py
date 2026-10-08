from il2cpp.prelude import *  # noqa: F401,F403

class Expr:
    __slots__ = ('text', 'ty', 'kind', 'recv',
                 # use-binding / precedence state, read through __getattr__
                 # until first set, so creation stays allocation-free
                 '_uses', '_use_ip', '_defpos', '_prec', '_usg_idx',
                 '_sites',
                 # fix 58: minted by the entry seed or by _fresh_unknowns,
                 # i.e. this register has NOT been written since. Set only
                 # at those two mint sites; any instruction that writes the
                 # register replaces the Expr and clears the mark with it.
                 '_unk',
                 # fix 66: the MethodDef index behind an `fptr` minted
                 # from an icall thunk cell -- `_call` seats it as `mi`
                 # so the site takes the resolved-call path
                 '_mi',
                 # Pure sqrt expressions from two native diamond arms must
                 # stay inline through their merge; binding either arm at its
                 # conditional definition would create an out-of-scope temp.
                 '_no_bind',
                 # fix 71c: the owner TypeDef stamped onto a
                 # klass/usage-kind typeof Expr at usage-slot decode
                 # time; _field_expr's sfblob branch reads it when the
                 # Expr's own .ty could not be derived
                 '_td',
                 # Review 84: the original `new T()` belonging to this exact
                 # allocation Expr. It survives temp binding so the following
                 # .ctor can complete that allocation instead of creating T
                 # for a second time.
                 '_alloc', '_slice', '_stack_offset', '_bytes', '_parts',
                 # element-class fold: `_newarr` proves a same-method
                 # newarr (exact runtime klass); `_arr_klass` carries an
                 # array's (type, exactness) on its klass-pointer load.
                 '_newarr', '_arr_klass',
                  # element-class fold: dry unanimous-merge proof that a
                  # value is a same-method newarr of the carried array
                  # type. Pass 2 reads dry end_states at loop back-edges,
                  # so without this the proof dies at every loop header.
                  '_dry_proof',
                  # sidecar phase 1: merge-side unanimous whole-tile
                  # proof (origin text, offset, width, closed type key,
                  # bytes). Consumers reroot exact tiles through it;
                  # nothing reads it yet (record-only).
                  '_tile_proof')

    def __init__(self, text, ty=None, kind='?', recv=None):
        self.text = text      # rendered C# expression
        self.ty = ty          # (data,bits) Il2CppType tuple or None
        self.kind = kind      # 'obj','klass','int','float','str','arr','ptr','?','null','initflag'
        self.recv = recv      # for klass exprs: the object it was loaded from

    def __getattr__(self, name):
        # defaults for the use-binding slots: unset means "never used".
        # __getattr__ only fires on a miss, so bound expressions pay nothing
        # extra after the first assignment.
        if name == '_use_ip':
            return -1
        if name in ('_uses', '_defpos', '_prec', '_usg_idx', '_sites'):
            return None
        if name == '_unk':
            return False
        if name == '_mi':
            return None
        if name == '_no_bind':
            return False
        if name == '_alloc':
            return None
        if name == '_newarr':
            return False
        if name == '_arr_klass':
            return None
        if name == '_dry_proof':
            return None
        if name == '_tile_proof':
            return None
        raise AttributeError(name)

    def __repr__(self):
        return 'E(%s)' % self.text


def _merge_arr_proof(v):
    """Array type a merge input proves exact, else None.

    A same-method newarr fixes the runtime klass, so every input proving
    the SAME array type proves the merged value on all paths. Array
    covariance is why params, fields, statics and `as`-refinements never
    prove: an `E[]`-typed local can hold a `D[]` at runtime. Inputs prove
    through the live `_newarr` flag or a dry unanimous-merge `_dry_proof`
    (pass 2 reads dry end_states at loop back-edges, structurally).
    """
    if not isinstance(v, Expr):
        return None
    if getattr(v, '_newarr', False) and isinstance(v.ty, tuple):
        return v.ty
    dp = getattr(v, '_dry_proof', None)
    if dp is not None and isinstance(dp, tuple) and len(dp) == 2 \
            and isinstance(dp[0], tuple):
        return dp[0]
    return None


def _tile_proof_for(vals, type_key):
    """Unanimous whole-tile proof for merge-side preservation, else None.

    Sidecar phase 1 (record side): at a CFG merge, per-pred fragment
    values that agree exactly -- same origin text, same closed type,
    same slice offset and width, same bytes -- prove the merged value
    is that whole tile on every path, so a later consumer may reroot
    to the origin instead of dying to unknown (F1 lanes) or
    miscompiling through a lossy whole-vector phi (piece0 offset-0).
    Anything else (missing/non-Expr inputs, sliceless values,
    disagreement, uncomparable keys) declines: the honest phi stands.
    No merge here, no rendering: pure per-pred evidence check.
    """
    try:
        if not vals:
            return None
        ids = []
        for v in vals:
            if not isinstance(v, Expr):
                return None
            sl = getattr(v, '_slice', None)
            if sl is None or len(sl) != 3:
                return None
            o, off, w = sl
            ot = getattr(o, 'text', None)
            oty = getattr(o, 'ty', None)
            if not ot or not isinstance(oty, tuple):
                return None
            try:
                ck = type_key(oty)
            except Exception:
                return None
            if ck is None:
                return None
            ids.append((ot, ck, off, w, getattr(v, '_bytes', None)))
        if len(set(ids)) != 1:
            return None
        return ids[0]
    except Exception:
        return None


def e_const(v, ty=None, kind='int'):
    return Expr(str(v), ty, kind)


_WORDCH = frozenset(
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')


def _mentions(text, name):
    """True when `text` reads `name` as a whole token: `this.num` is
    mentioned by `(this.num + 1)` and by `this.num.ToString()`, but not by
    `this.num2` or `mythis.num`."""
    if not name or not text or len(name) > len(text):
        return False
    n = len(name)
    i = text.find(name)
    while i != -1:
        j = i + n
        if (i == 0 or text[i - 1] not in _WORDCH) and \
                (j == len(text) or text[j] not in _WORDCH):
            return True
        i = text.find(name, i + 1)
    return False


def _bind_replace(text, old, new):
    """Rewrite whole-token occurrences of `old` with `new`.

    `_bind` materializes a twice-rendered expression to a temp and
    rewrites later renderings. A plain substring replace cuts inside
    longer identifiers sharing the prefix: binding
    `ConsoleUINavigation.<>c.<>9` rewrote the static-field store
    `ConsoleUINavigation.<>c.<>9__1_0 = ...` into the undeclared
    `t1012__1_0`. A match extended by an identifier character on the
    right is a longer name, not this value; a match preceded by an
    identifier character, `.` or `>` is a member suffix (`x.old`,
    `p->old`), not this value either. Member access ON the value
    (`old.member`, `old(...)`, `old[...]`) still rewrites."""
    if not old or old not in text:
        return text
    out = []
    i = 0
    n = len(old)
    while True:
        j = text.find(old, i)
        if j == -1:
            out.append(text[i:])
            break
        before = text[j - 1] if j > 0 else ''
        after = text[j + n] if j + n < len(text) else ''
        if (before and (before in _WORDCH or before in '.>')) \
                or (after and after in _WORDCH):
            out.append(text[i:j + 1])
            i = j + 1
            continue
        out.append(text[i:j])
        out.append(new)
        i = j + n
    return ''.join(out)


_BARE_TOKEN_RX = re.compile(r'^(v\d+|t\d+)$')


def _recv_fold(t: str) -> str:
    """Parenthesize a receiver expression when it isn't a bare token,
    `this`, or a plain dotted member (so `.Method()` can't bind to a
    trailing operand)."""
    if t == 'this' or re.match(r'^[\w.]+$', t) or re.match(r'^s_[0-9a-fA-F]+$', t) \
            or re.match(r'^[\w.]+(?:\[[^\[\]]*\])+$', t):
        return t
    return '(%s)' % t

# arg0 of a resolved instance call is receiver-shaped unless it renders
# as a placeholder, literal, class token, or byref composite (fix 40):
# leading digit/sign/dot covers numeric literals, quote starts string
# and char literals, typeof( a klass token, & a byref the dedicated
# strip-and-fold branch above already handles when clean.
_RECV_UNSHAPED_RX = re.compile(r'^(?:[-+.0-9]|typeof\(|"|\'|&)')


def _recv_shaped(t: str) -> bool:
    return bool(t) and t not in ('_', '?', 'null', 'true', 'false') \
        and not _RECV_UNSHAPED_RX.match(t)


# fix 137b: accessor sugar travels the pipeline call-shaped. Every text
# purity test (dataflow._impure, CSE's _IMPURE, kill-on-write) keys on
# `ident(`; a bare `R.X` / `R[i]` getter reads as a pure load and was
# DCE'd when unused or re-evaluated into a loop head (AppendFormatHelper's
# `format.get_Chars(i)` -- a call that can throw -- vanished). The lifter
# emits `__accget(R.X)` / `__accset(R.X)(v)` and lift_method unwraps them
# last, after every pass that judges purity.
_ACC_GET = '__accget('
_ACC_SET = '__accset('


def acc_get(text: str) -> str:
    return _ACC_GET + text + ')'


def acc_set(lhs: str, value: str) -> str:
    return '%s%s)(%s)' % (_ACC_SET, lhs, value)


def acc_lhs(text: str) -> str:
    """The member lvalue of an `__accset(LHS)(v)` marker (kill target)."""
    if text.startswith(_ACC_SET):
        e = _acc_close(text, len(_ACC_SET))
        if e > 0:
            return text[len(_ACC_SET):e]
    return text.split(' = ', 1)[0]


def _acc_close(s: str, i: int) -> int:
    """Index of the bracket closing the one opened just before s[i]
    (string/char literals skipped); -1 when unbalanced."""
    depth, q, j, n = 1, None, i, len(s)
    while j < n:
        c = s[j]
        if q:
            if c == '\\':
                j += 2
                continue
            if c == q:
                q = None
        elif c == '"' or c == "'":
            q = c
        elif c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return -1


def unwrap_accessor_markers(ln: str) -> str:
    """`__accget(X)` -> `X`, `__accset(L)(v)` -> `L = v`, innermost (right-
    most) first; a `(__accget(X)).M` grouping left by _recv_fold drops its
    redundant parens. An unbalanced marker is left as is (never guessed)."""
    if '__acc' not in ln:
        return ln
    while True:
        k = max(ln.rfind(_ACC_GET), ln.rfind(_ACC_SET))
        if k < 0:
            return ln
        a = k + len(_ACC_GET)
        e = _acc_close(ln, a)
        if e < 0:
            return ln
        inner = ln[a:e]
        if ln.startswith(_ACC_SET, k):
            if e + 1 >= len(ln) or ln[e + 1] != '(':
                return ln
            e2 = _acc_close(ln, e + 2)
            if e2 < 0:
                return ln
            rep, end = '%s = %s' % (inner, ln[e + 2:e2]), e2 + 1
        else:
            rep, end = inner, e + 1
            if k >= 1 and ln[k - 1] == '(' and ln[end:end + 1] == ')' \
                    and ln[end + 1:end + 2] in ('.', '[') and ln[end + 1:end + 2] \
                    and not (k >= 2 and (ln[k - 2].isalnum() or ln[k - 2] in '_)]>')):
                k, end = k - 1, end + 1
        ln = ln[:k] + rep + ln[end:]


# fix 54: an lvalue a C# `ref` may legally name -- a bare local/slot, a
# dotted member chain, or one of those indexed once. `data_NNN` (a static
# data address) is excluded: it has its own render path (_DATA_ADDR_RX).
_REFARG_RX = re.compile(
    r'^(?!data_)(?:[A-Za-z_$][\w$]*)(?:\.[A-Za-z_$][\w$]*)*'
    r'(?:\[[^\[\]]*\])?$')


def _byref_arg_render(at, is_byref, is_byval_struct, trust):
    """fix 54 (batch 48): how a `&X` call argument should render given
    what the callee DECLARES at that position. Returns the replacement
    text, or None to keep the raw `&` untouched.

    Win64 passes anything that is not 1/2/4/8 bytes by hidden pointer,
    so a BY-VALUE struct argument and a genuine `ref`/`out` argument
    reach the callee through the identical instruction. Disasm-proven
    at DEMO_LegsAnim_KeepOnGround.FixedUpdate 0x180671800: the 6-param
    Physics.Raycast at 0x180671a30 gets `lea rcx,[rsp+50h]` (Vector3
    origin, BY VALUE), `lea rdx,[rsp+40h]` (Vector3 direction, BY
    VALUE) and `lea r8,[rsp+60h]` (out RaycastHit) -- three identical
    leas, and only the byref bit tells them apart.

      byref param            -> `ref X`   (metadata carries no
                                ParamAttributes in v31, so `out` is not
                                separable from `ref`; the DECLARATION
                                side spells both `ref ` too, so the
                                tree stays self-consistent)
      non-byref value type   -> `X`       (the & is ABI noise)
      anything else          -> None

    That last row is load-bearing: a lea landing on a string/int/float
    parameter (5.4% of the corpus census) means the parameter->register
    mapping is wrong for that call, and printing a confident `ref`
    there is exactly the failure mode the shared-body rule exists to
    prevent (CLAUDE.md). `trust` is False when the mapping itself is in
    doubt -- see the caller."""
    if not trust or not at.startswith('&'):
        return None
    inner = at[1:]
    if not _REFARG_RX.match(inner):
        return None
    if is_byref:
        return 'ref ' + inner
    if is_byval_struct:
        return inner
    return None

# ---- use-count expression binding ------------------------------------
# An expression whose text renders into the output twice is materialized to
# a temp at its definition. Only "expensive" texts qualify: short ones and
# bare tokens re-render cheaply, and a temp would cost more lines than it
# saves.
_USE_BIND_MIN = 16
_BINDABLE_KINDS = frozenset(
    ('obj', 'klass', 'int', 'float', 'str', 'arr', 'ptr'))
_FLAGS_KEY = '!flags'   # the decompiler's cross-block flags sentinel

# ---- type inference, round two ----------------------------------------
# Synthetic Il2CppType tuples for inference from instruction classes: on
# x64, GPR arithmetic/logic is integer by construction and SSE arithmetic
# is float -- the codegen never mixes the two domains.
_INT_TY = (0, 0x08 << 16)
_R4_TY = (0, 0x0c << 16)
_R8_TY = (0, 0x0d << 16)
_BOOL_TY = (0, 0x02 << 16)
# tokens a hint can key on: renamable locals and stack slots
_BARE_HINT_RX = re.compile(r'^(v\d+|t\d+|s_[0-9a-fA-F]+)$')
# an array base whose text carries a folded header bias (`arr + 32` from a
# prior `add r, 0x20`): head is a plain token, bias a positive constant
_ARR_BIAS_RX = re.compile(r'^([\w.\[\]]+)\s*\+\s*(0x[0-9a-fA-F]+|\d+)$')


class _RegState(dict):
    """The register file, with use-counting on reads and definition stamping
    on writes. Registers hold symbolic text that re-renders at each read, so
    a read *is* a rendering: the dict is the single choke point through which
    every handler consumes register values. `_note_use` may bind the
    expression (mutating its text to a temp name) before the read returns, so
    the statement being composed picks the temp up automatically."""
    __slots__ = ('L',)

    def __init__(self, L, init=None):
        super().__init__(init or {})
        self.L = L

    def __getitem__(self, k):
        e = super().__getitem__(k)
        if e is not None and k != _FLAGS_KEY and len(e.text) >= _USE_BIND_MIN:
            self.L._note_use(e)
        return e

    def get(self, k, d=None):
        e = super().get(k, d)
        if e is not None and k != _FLAGS_KEY and len(e.text) >= _USE_BIND_MIN:
            self.L._note_use(e)
        return e

    def __setitem__(self, k, v):
        super().__setitem__(k, v)
        if v is not None and k != _FLAGS_KEY:
            self.L._stamp(v)


def _is_unresolved_gp(ty) -> bool:
    """True when `ty` (an il2cpp (data, bits) type tuple) is an unbound
    generic parameter (IL2CPP_TYPE_VAR/MVAR, 0x13/0x1e) -- the type as
    written in a generic method's own signature (`T`, `TArg`), before any
    call-site substitution. Binding a temp's DECLARED type to this is
    strictly worse than leaving it unset: it wins the `setdefault` race
    and locks out a later, more useful hint (e.g. from the concretely-
    typed variable/field the temp gets immediately stored into)."""
    return isinstance(ty, tuple) and ((ty[1] >> 16) & 0xFF) in (0x13, 0x1e)

