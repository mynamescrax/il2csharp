"""Structured decompiler core for il2csharp.

CFG -> symbolic block execution with phi-merges -> structured control flow
(if/else, while, do-while, break) -> rendered C# body.
"""

from il2cpp.prelude import *  # noqa: F401,F403





class Block:
    __slots__ = ('bid', 'insns', 'succs', 'preds', 'stmts', 'end_state',
                 'term', 'cond', 'ret', 'consumed', 'is_entry', 'switch_targets',
                 'switch_idx', 'switch_idx_reg', 'switch_snap_ip')

    def __init__(self, bid, insns):
        self.bid = bid
        self.insns = insns
        self.succs: List[int] = []
        self.preds: List[int] = []
        self.stmts: List[str] = []
        self.end_state = None
        self.term = None      # ('jcc',t,f)|('jmp',t)|('ret',)|('switch',)|('stop',)|('fall',t)
        self.cond: Optional[str] = None
        self.ret: Optional[str] = None   # return expr; '' means bare; 'tail' marker unused here
        self.consumed = False
        self.is_entry = False
        self.switch_targets = None
        self.switch_idx = None       # rendered index expression
        self.switch_idx_reg = None   # register holding the index at switch_snap_ip
        self.switch_snap_ip = None   # ip to sample switch_idx_reg *before*


class _Sink:
    """Adapts Lifter.emit tuples -> plain statement strings on a block."""
    def __init__(self, block):
        self.block = block

    def append(self, item):
        if isinstance(item, tuple):
            ip, code, asm = item
            if code:
                self.block.stmts.append(code)
        else:
            self.block.stmts.append(item)


INT_TY = (0, 0x08 << 16)   # synthetic System.Int32 type tuple for inferred counters
LBL = '@@'                 # prefix of a provisional label line, resolved after structuring


def _match_brace(lines, open_idx):
    """Index of the `}` closing the `{` at open_idx, or -1."""
    depth = 0
    for j in range(open_idx, len(lines)):
        t = lines[j].strip()
        if t == '{':
            depth += 1
        elif t == '}' or t.startswith('} while'):
            depth -= 1
            if depth == 0:
                return j
    return -1


def _header_idx(lines, open_idx):
    """Index of the statement line that owns the `{` at open_idx, or -1."""
    k = open_idx - 1
    while k >= 0 and not lines[k].strip():
        k -= 1
    return k if k >= 0 else -1


def _hoist_point(lines, ac):
    """Index to hoist a shared tail to: just past the construct whose arm
    closes at `ac` (a following `else {...}` arm included). -1 when the
    construct continues into an `else if` chain."""
    j = ac + 1
    while j < len(lines) and not lines[j].strip():
        j += 1
    if j < len(lines) and lines[j].strip() == 'else':
        k = j + 1
        while k < len(lines) and not lines[k].strip():
            k += 1
        if k < len(lines) and lines[k].strip() == '{':
            ec = _match_brace(lines, k)
            return ec + 1 if (ec is not None and ec > 0) else -1
        return -1
    return ac + 1


_LOOP_HDR_RX = re.compile(r'^(?:while|for|foreach|do)\b')


# todo lead 2 (_elseif_flatten): a single, uncompounded top-level
# !=/== comparison -- LHS/RHS parens must independently balance so
# the one match found is genuinely the top-level operator.
_ELSEIF_CMP_RX = re.compile(r'^(.+?)\s*(!=|==)\s*(.+)$')

# todo lead #3 (_name_interface_dispatch): the interfaceOffsets search
# block il2cpp emits ahead of an interface-dispatch call -- a typeof()
# decl, a linear scan for a matching interfaceType, landing on the
# absolute class-vtable slot where that interface's own method block
# begins.
_ITF_TYPEOF_RX = re.compile(r'^\S+ (\w+) = typeof\((.+)\);$')
# slot lines carry a declaration prefix at _render stage
# (`object obj19 = ...`); the bare `tok = ...` form still matches.
_ITF_SLOT_RX = re.compile(r'^(?:[A-Za-z_][\w<>,\[\]\.\s]*?\s+)?(\w+) = \(.*<< 4\) \+ 0x138 \+ .+;$')
_ITF_CALL_RX = re.compile(
    r'\(\(byte\*\)(\w+) \+ (0x[0-9a-fA-F]+)\)\[0\]\(\) /\*indirect\*/\((.*)\);$')


def _falls_to(lines, gi, gstack, H):
    """Does control fall from the goto at gi out to line H with nothing
    else executing? No non-blank statement may follow the goto at any
    crossed level, and no crossed level may be a loop, switch, or SEH
    region (falling out of a loop re-tests; a switch section's fall-out
    only lands at H when EVERY section breaks flow -- sibling cases
    would otherwise execute; out of a finally is illegal)."""
    lvl = len(gstack)
    cur = gi
    while lvl > 0:
        op = gstack[lvl - 1]
        cl = _match_brace(lines, op)
        if cl is None or cl < 0:
            return False
        hdr_i = _header_idx(lines, op)
        hdr = lines[hdr_i].strip() if hdr_i >= 0 else ''
        if _LOOP_HDR_RX.match(hdr) or hdr.startswith('switch'):
            return False
        if hdr in ('try', 'finally') or hdr.startswith('catch'):
            return False
        for k in range(cur + 1, cl):
            if lines[k].strip():
                return False
        if cl + 1 >= H:
            nxt = cl + 1
            while nxt < len(lines) and not lines[nxt].strip():
                nxt += 1
            if nxt == H or cl + 1 == H:
                return True
            if nxt >= len(lines) or lines[nxt].strip() != 'else':
                return False
        cur = cl
        nx = cl + 1
        while nx < len(lines) and not lines[nx].strip():
            nx += 1
        if nx < len(lines) and lines[nx].strip() == 'else':
            if nx + 1 >= len(lines) or lines[nx + 1].strip() != '{':
                return False
            ec = _match_brace(lines, nx + 1)
            if ec is None or ec < 0:
                return False
            cur = ec
            if ec + 1 == H:
                return True
        lvl -= 1
    return cur + 1 == H


def _arm_open_of_close(lines, close_idx):
    """Index of the `{` matching the `}` at close_idx, or -1."""
    d = 0
    for k in range(close_idx, -1, -1):
        t = lines[k].strip()
        if t == '}' or t.startswith('} while'):
            d += 1
        elif t == '{':
            d -= 1
            if d == 0:
                return k
    return -1


def _construct_arms(lines, arm_open):
    """[(open_idx, close_idx)] of every arm of the construct owning the
    arm brace at arm_open, else-chains followed forward AND backward
    (an else-arm backs up to its if-arm so the sibling if-arm is
    included). [] on shapes we bail on."""
    a = arm_open
    while True:
        hi = _header_idx(lines, a)
        if hi < 0:
            return []
        if lines[hi].strip() == 'else':
            prev = hi - 1
            while prev >= 0 and not lines[prev].strip():
                prev -= 1
            if prev < 0 or lines[prev].strip() != '}':
                return []
            a = _arm_open_of_close(lines, prev)
            if a < 0:
                return []
            continue
        break
    arms = []
    cur = a
    while True:
        cl = _match_brace(lines, cur)
        if cl is None or cl < 0:
            return []
        arms.append((cur, cl))
        j = cl + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j < len(lines) and lines[j].strip() == 'else':
            k = j + 1
            while k < len(lines) and not lines[k].strip():
                k += 1
            if k >= len(lines) or lines[k].strip() != '{':
                return []
            cur = k
            continue
        break
    return arms


_FLOWBREAK_RX = re.compile(r'^(?:return|goto|break|continue|throw)\b')
# raw pass input packs `stmt; return;` on one line -- the trailing
# statement is what decides fall-through (a string containing the
# pattern false-positives into the safe, rejecting, direction)
_FLOWTAIL_RX = re.compile(r';\s*(?:return|goto|break|continue|throw)\b[^;]*;\s*$')
_LBLDEF_LINE_RX = re.compile(r'^L_[0-9a-fA-F]+:$')


def _can_fall(lines, arm_open):
    """Can control flowing through this arm reach past its close?
    Conservative: only an arm whose execution provably ends in an
    unconditional flow break (possibly through an if/else chain every
    arm of which breaks) cannot fall. Label lines are transparent to
    fall-through."""
    cl = _match_brace(lines, arm_open)
    if cl is None or cl < 0:
        return True
    depth = 0
    last = None
    for k in range(arm_open + 1, cl):
        s = lines[k].strip()
        if not s:
            continue
        if depth == 0:
            if s == '{':
                depth += 1
                continue
            if _LBLDEF_LINE_RX.match(s) or s == 'else':
                continue
            last = k
        elif s == '{':
            depth += 1
        elif s == '}' or s.startswith('} while'):
            depth -= 1
    if last is None:
        return True
    s = lines[last].strip()
    if _FLOWBREAK_RX.match(s) or _FLOWTAIL_RX.search(s):
        return False
    if s.startswith('if'):
        j = last + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j < len(lines) and lines[j].strip() == '{':
            if _can_fall(lines, j):
                return True
            c = _match_brace(lines, j)
            e = c + 1
            while e < len(lines) and not lines[e].strip():
                e += 1
            while e < len(lines) and lines[e].strip() == 'else':
                eb = e + 1
                while eb < len(lines) and not lines[eb].strip():
                    eb += 1
                if eb >= len(lines) or lines[eb].strip() != '{':
                    return True
                if _can_fall(lines, eb):
                    return True
                c = _match_brace(lines, eb)
                e = c + 1
                while e < len(lines) and not lines[e].strip():
                    e += 1
            return False
    return True


_TEMP_RX = re.compile(r'^v\d+$')


def _in_string(s, i):
    """True if index i of s is inside a string/char literal (backslash-aware)."""
    q = None
    j = 0
    while j < i:
        c = s[j]
        if c == '\\':
            j += 2
            continue
        if c in ('"', "'"):
            q = None if q == c else (c if q is None else q)
        j += 1
    return q is not None

_LIT_RX = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')


def _has_arrow(s):
    """True if s contains a `->` pointer member access outside any
    string literal -- _field_expr's PTR-base path renders `obj->field`,
    which needs the unsafe wrapper exactly like the raw byte-pointer
    forms (a string literal containing `->` must not trigger it)."""
    i = s.find('->')
    while i != -1:
        if not _in_string(s, i):
            return True
        i = s.find('->', i + 2)
    return False

def _split_args(s, i):
    """Split the top-level comma-separated arguments of a call whose
    opening paren sits at s[i]; returns (args, end_index_after_close)."""
    depth = 0
    args = []
    seg = i + 1
    j = i
    n = len(s)
    while j < n:
        if _in_string(s, j):
            j += 1
            continue
        c = s[j]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                args.append(s[seg:j].strip())
                return args, j + 1
        elif c == ',' and depth == 1:
            args.append(s[seg:j].strip())
            seg = j + 1
        j += 1
    return None, j


_OBJOP_RX = re.compile(r'[\w.]*Object\.op_(Equality|Inequality)\(')


def _objop_fold(ln):
    """`Object.op_Equality(A, B)` -> `(A == B)`; a bare `0` argument is
    the compiled null of an object comparison and renders `null`."""
    while True:
        m2 = None
        for m2 in _OBJOP_RX.finditer(ln):
            if not _in_string(ln, m2.start()):
                break
        else:
            return ln
        if m2 is None:
            return ln
        args, end = _split_args(ln, m2.end() - 1)
        if not args or len(args) != 2:
            return ln
        a, b = args
        if a == '0':
            a = 'null'
        if b == '0':
            b = 'null'
        op = '==' if m2.group(1) == 'Equality' else '!='
        for _k, _v in enumerate((a, b)):
            if any(ch == '?' and not _in_string(_v, j2) for j2, ch in enumerate(_v)):
                if _k == 0:
                    a = '(%s)' % a
                else:
                    b = '(%s)' % b
        repl = '(%s %s %s)' % (a, op, b)
        ln = ln[:m2.start()] + repl + ln[end:]


def _ends_flow(line):
    s = line.strip()
    return s in ('break;', 'return;', 'continue;') or s.startswith('return ') \
        or s.startswith('goto ')


def _abandon_at_region_close(blocks, cur, in_loop, stop, regions):
    """A loop-body walk reached the close block of a try that opened AT the
    loop header (its `try {` is emitted before the loop's own `do`/`{`), so
    the region's `}`/clause must appear after the loop's `}`/while, not
    inside the body. Only the latch block (back-edge to the header) is
    ambiguous -- an in-body try closes on a plain body block."""
    hdr = next(iter(stop), -1)
    if hdr < 0 or hdr not in in_loop:
        return False
    if hdr not in blocks[cur].succs or cur not in in_loop:
        return False
    return any(s['opened'] and not s['closed'] and cur == s['close']
               and s['open'] == hdr for s in regions)

