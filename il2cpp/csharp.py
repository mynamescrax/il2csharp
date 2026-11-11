from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.names import safe_ident, sanitize

MEMBER_VIS = {0: '', 1: 'private ', 2: 'private protected ', 3: 'internal ',
              4: 'protected ', 5: 'protected internal ', 6: 'public ',
              7: 'public '}
METH_VIS = MEMBER_VIS
FIELD_VIS = MEMBER_VIS
# TypeAttributes visibility is a DIFFERENT table (ECMA-335 II.23.1.15):
# 0 NotPublic, 1 Public, then the six nested forms.
TYPE_VIS = {0: 'internal ', 1: 'public ', 2: 'public ', 3: 'private ',
            4: 'protected ', 5: 'internal ', 6: 'private protected ',
            7: 'protected internal '}
# CLI FieldAttributes (ECMA-335 II.23.1.5), as IL2CPP stores them
FA_STATIC = 0x0010
FA_INITONLY = 0x0020
FA_LITERAL = 0x0040
FA_HASRVA = 0x0100


def field_attrs(il, f) -> int:
    """FieldAttributes of a field row. IL2CPP does not carry field flags
    in the field table -- they live in the low 16 bits of the field's
    Il2CppType (`attrs:16`, below the type enum at bits 16-23 and the
    byref bit at 29). static/readonly/const/visibility all come from
    here; the offset-threshold and has-a-default-value heuristics this
    replaced misread 7,085 fields on the reference corpus."""
    t = il.types[f.type] if 0 <= f.type < len(il.types) else None
    return (t[1] & 0xFFFF) if t else 0


def source_field_name(il, fi):
    """Keep storage distinct from properties/events, by FieldDef identity.

    Do not rewrite metadata: reflection strings and native symbol maps retain
    their original spelling. The same per-binary map serves declarations and
    every offset/usage-slot path in the lifter.
    """
    names = getattr(il, '_source_field_names', None)
    if names is None:
        names = {}
        meta = il.meta
        for td in meta.typedefs:
            props = {meta.getstr(meta.properties[td.property_start + k][0])
                     for k in range(getattr(td, 'property_count', 0))}
            events = {meta.getstr(meta.events[td.event_start + k][0])
                      for k in range(getattr(td, 'event_count', 0))}
            members = props | events
            if not members:
                continue
            fields = list(meta.type_fields(td))
            occupied = {safe_ident(sanitize(n)) for n in members}
            occupied.update(safe_ident(sanitize(meta.fields[i].name)) for i in fields)
            occupied.update(safe_ident(sanitize(meta.methods[i].name))
                            for i in meta.type_methods(td))
            for k in range(getattr(td, 'nested_count', 0)):
                ni = meta.nested_types[td.nested_start + k]
                if 0 <= ni < len(meta.typedefs):
                    occupied.add(safe_ident(sanitize(meta.typedefs[ni].name)))
            for i in fields:
                raw = meta.fields[i].name
                backing = re.fullmatch(r'<(.+)>k__BackingField', raw)
                member = backing.group(1) if backing else raw
                if member not in members:
                    continue
                # Explicit-interface members carry dots (A.B.C.name) no field
                # identifier can spell; flatten every non-word char so storage
                # stays one token the backing-field fold matches.
                stem = '__field_' + safe_ident(re.sub(r'[^A-Za-z0-9_]', '_', member))
                name = stem
                suffix = 2
                while name in occupied:
                    name = stem + '_' + str(suffix)
                    suffix += 1
                occupied.add(name)
                names[i] = name
        il._source_field_names = names
    return names.get(fi, il.meta.fields[fi].name)


class UsingTracker:
    """Namespace references used by one emitted file, rendered as sorted,
    de-duplicated using statements. Sources are the file's rendered text --
    field types, parameter and return types, base and interface types, and
    dotted call targets inside bodies. Only namespaces that actually exist
    in the game metadata are emitted, so string literals and member paths
    can't smuggle in fake ones."""
    _DOTID_RX = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+')
    _STR_RX = re.compile(r'"(?:[^"\\]|\\.)*"')

    def __init__(self, il2: 'Il2Cpp' = None):
        self._valid = il2.all_namespaces if il2 is not None else None
        self.used: set = set()

    def add_name(self, dotted: str):
        """Collect the namespace prefix of one dotted identifier: the longest
        prefix that is a real namespace (System.Collections.Generic for
        System.Collections.Generic.List`1, never the type itself)."""
        name = dotted.strip()
        if '.' not in name:
            return
        for chunk in re.split(r'[<>\[\],*]', name):
            chunk = chunk.strip()
            if '.' not in chunk:
                continue
            parts = chunk.split('.')
            for k in range(len(parts) - 1, 0, -1):
                cand = '.'.join(parts[:k])
                if self._valid is None or cand in self._valid:
                    self.used.add(cand)
                    break

    def add_text(self, text: str):
        """Collect every dotted identifier in a chunk of rendered source;
        string literals are masked out first."""
        for m in self._DOTID_RX.finditer(self._STR_RX.sub('', text)):
            self.add_name(m.group(0))

    def render(self, skip=()) -> List[str]:
        skip = set(skip or ())
        return ['using %s;' % n for n in sorted(self.used - skip)]


_NS_CHAIN_RX = re.compile(r'(?<![\w.:])([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)')


def _visible_ns(ns, file_ns, uses):
    if not ns:
        return True
    if ns in uses or ns == file_ns:
        return True
    return bool(file_ns) and file_ns.startswith(ns + ".")


def _ambiguous_head(head, file_ns, uses, short_to_ns, ns_finals):
    for key in (head, re.sub(r"_\d+$", "", head)):
        nss = set(short_to_ns.get(key, ()))
        # Global-namespace typedefs never win against using-imported names
        # (the probe's ambiguity census never shows them); counting them
        # would keep every common short name qualified.
        if sum(1 for ns in nss if ns and _visible_ns(ns, file_ns, uses)) >= 2:
            return True
    return head in ns_finals


def collision_heads(buf_text, file_ns, uses, short_to_ns):
    """Short heads that shortening must never produce, mirroring rep():
    for every dotted chain and every using-prefix strip rep() would apply,
    the remaining head must resolve unambiguously (one visible typedef and
    no visible namespace final-segment match). Computed on masked text so
    strings/comments can only over-keep."""
    try:
        masked = UsingTracker._STR_RX.sub("", buf_text)
    except Exception:
        masked = buf_text
    vis_ns = set(uses or ())
    if file_ns:
        parts = file_ns.split(".")
        for k in range(1, len(parts) + 1):
            vis_ns.add(".".join(parts[:k]))
    ns_finals = set(ns.split(".")[-1] for ns in vis_ns if ns)
    order = sorted(uses or (), key=lambda u: (-len(u), u))
    dup = set()
    for m in UsingTracker._DOTID_RX.finditer(masked):
        chain = m.group(0)
        for u in order:
            if chain.startswith(u + "."):
                rest = chain[len(u) + 1:]
                head = rest.split(".")[0]
                if _ambiguous_head(head, file_ns, uses, short_to_ns, ns_finals):
                    dup.add(head)
    return dup


def strip_namespaces(lines: List[str], uses: set, file_ns="", dup=()) -> List[str]:
    """Drop the namespace prefix of every dotted reference the file's own
    using set imports (longest imported prefix wins), so a body carrying
    `UnityEngine.Transform` under `using UnityEngine;` reads `Transform`.
    String literals and // comments are left untouched."""
    order = sorted(uses, key=lambda u: (-len(u), u))

    def rewrite(s: str) -> str:
        out = []
        i = 0
        n = len(s)
        while i < n:
            ch = s[i]
            if ch in ('"', "'"):
                j = i + 1
                while j < n and s[j] != ch:
                    j += 2 if s[j] == '\\' else 1
                out.append(s[i:min(j + 1, n)])
                i = j + 1
                continue
            if ch == '/' and i + 1 < n and s[i + 1] == '/':
                out.append(s[i:])
                break
            j = i
            while j < n and s[j] not in '"\'':
                if s[j] == '/' and j + 1 < n and s[j + 1] == '/':
                    break
                j += 1
            code = s[i:j]

            def rep(m):
                chain = m.group(0)
                for u in order:
                    if chain.startswith(u + '.'):
                        rest = chain[len(u) + 1:]
                        # Self-shadow: the stripped prefix ends where the
                        # remainder begins (`HID.HIDDeviceDescriptor` from
                        # `...HID.HID...`). Shortening rebinds the head to
                        # the namespace instead of the nested owner, so the
                        # full chain stays.
                        if rest.split('.')[0] == u.split('.')[-1]:
                            return chain
                        if rest.split('.')[0] in dup:
                            return chain
                        return rest
                return chain

            out.append(_NS_CHAIN_RX.sub(rep, code))
            i = j
        return ''.join(out)

    return [rewrite(l) for l in lines]


_NAMEOF_DENY = {
    'None', 'All', 'Default', 'Name', 'Value', 'True', 'False', 'Auto',
    'Other', 'Unknown', 'Normal', 'Custom', 'Left', 'Right', 'Center',
    'Top', 'Bottom', 'Start', 'End', 'None1', 'First', 'Last', 'Empty',
}
_NAMEOF_LIT_RX = re.compile(r'"([A-Za-z_]\w{2,})"')


def nameof_sugar(lines: List[str], members) -> List[str]:
    """Rewrite string literals that name an enum member (of an enum the
    file imports) into nameof(Enum.Member). `nameof` always evaluates to
    the identifier text, so the runtime value is unchanged; the denylist
    keeps common-word members out. Only whole arguments convert (the
    literal is preceded by '(' or ',' and followed by ')' or ',')."""
    out = []
    for raw in lines:
        i = 0
        n = len(raw)
        res = []
        while i < n:
            ch = raw[i]
            if ch in ('"', "'"):
                j = i + 1
                while j < n and raw[j] != ch:
                    j += 2 if raw[j] == '\\' else 1
                lit = raw[i:min(j + 1, n)]
                if ch == '"' and i > 0 and raw[i - 1] in '(,' \
                        and min(j + 1, n) < n and raw[j + 1] in '),':
                    m = _NAMEOF_LIT_RX.match(lit)
                    if m and m.group(1) in members and m.group(1) not in _NAMEOF_DENY:
                        # the enum member declaration escapes keywords
                        # (safe_ident), so the nameof text must match it.
                        res.append('nameof(%s.%s)' % (members[m.group(1)], safe_ident(m.group(1))))
                        i = j + 1
                        continue
                res.append(lit)
                i = j + 1
                continue
            if ch == '/' and i + 1 < n and raw[i + 1] == '/':
                res.append(raw[i:])
                i = n
                break
            j = i
            while j < n and raw[j] not in '"\'':
                if raw[j] == '/' and j + 1 < n and raw[j + 1] == '/':
                    break
                j += 1
            res.append(raw[i:j])
            i = j
        out.append(''.join(res))
    return out

