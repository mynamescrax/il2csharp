from il2cpp.prelude import *  # noqa: F401,F403

@dataclass
class CodeGenModule:
    name: str
    method_pointer_count: int
    method_pointers: int
    adjustor_thunk_count: int
    adjustor_thunks: int
    invoker_indices: int
    rgctx_ranges: int
    rgctxs: int



def meta_lit_repr(s: str) -> str:
    r = s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    r = re.sub(r'[\x00-\x1f\x7f]', lambda m: '\\u%04x' % ord(m.group(0)), r)
    if len(r) > 96:
        cut = 93
        while cut > 0 and r[cut - 1] == '\\':
            cut -= 1
        r = r[:cut] + '...'
    return '"%s"' % r
    return '"%s"' % r


# ----------------------------------------------------------------------------
# native -> pseudo-C# lifter
# ----------------------------------------------------------------------------



if HAVE_ICED:
    IMM_OPS = {OpKind.IMMEDIATE8, OpKind.IMMEDIATE16, OpKind.IMMEDIATE32, OpKind.IMMEDIATE64,
               OpKind.IMMEDIATE8TO16, OpKind.IMMEDIATE8TO32, OpKind.IMMEDIATE8TO64,
               OpKind.IMMEDIATE32TO64, OpKind.IMMEDIATE8_2ND}
else:
    IMM_OPS = set()
