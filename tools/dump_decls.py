"""Canonical declaration dump for the Cpp2IL cross-check gate (side A).

Dumps every type + method + field declaration of the selected images
in a stable, sorted, fixture-independent text form. Intended uses:
(a) signature-drift detection across commits (diff two dumps);
(b) the metadata side of the Cpp2IL declaration cross-check -- a
Cpp2IL-reconstructed tree is reduced to the same grammar (side B,
external binary) and diffed. Type spellings use Il2Cpp.type_name
(the emitter's own convention); owner paths are CLR-style
(NS.Outer+Inner, backtick arity kept).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from corpus_common import load


def nest_parent(meta):
    """Child typedef index -> parent typedef index, from nested_types ranges.

    Mirrors emit_type (il2cpp/emitter.py), which nests structure solely
    through this table; the declaring field is consulted for visibility
    only and disagrees here (ProbabilisticMap: declaring unresolvable,
    table says child of String). Built once per dump run.
    """
    try:
        parent = {}
        for ti, td in enumerate(meta.typedefs):
            try:
                ns, nc = td.nested_start, td.nested_count
            except Exception:
                continue
            for k in range(nc or 0):
                try:
                    ni = meta.nested_types[ns + k]
                except Exception:
                    continue
                if isinstance(ni, int) and 0 <= ni < len(meta.typedefs):
                    parent.setdefault(ni, ti)
        return parent
    except Exception:
        return {}


def owner_path(meta, nest, td, idx):
    try:
        chain = [td.name or "?"]
        seen = {idx}
        cur = idx
        depth = 0
        while depth < 8:
            p = nest.get(cur)
            if p is None or p in seen or not (0 <= p < len(meta.typedefs)):
                break
            seen.add(p)
            chain.append(meta.typedefs[p].name or "?")
            cur = p
            depth += 1
        chain.reverse()
        outer = meta.typedefs[cur] if 0 <= cur < len(meta.typedefs) else td
        ns = outer.namespace or ""
        return (ns + "." if ns else "") + "+".join(chain)
    except Exception:
        return (td.namespace + "." if td.namespace else "") + (td.name or "?")


def type_name(il, ty):
    try:
        if ty is None:
            return "void"
        return il.type_name(ty)
    except Exception:
        return "?"


def generic_arity(meta, m):
    try:
        gc = m.generic_container
        if gc is None or gc == -1:
            return 0
        return meta.generic_containers[gc][1]
    except Exception:
        return 0


def type_kind(il, meta, td):
    """class/struct/interface/enum/delegate, mirroring the emitter."""
    try:
        if (td.namespace, td.name) not in (("System", "Delegate"),
                                            ("System", "MulticastDelegate")):
            try:
                chain = il.base_chain_tds(td.index)
            except Exception:
                chain = ()
            for ti in chain[1:]:
                t2 = meta.typedefs[ti] if 0 <= ti < len(meta.typedefs) else None
                if t2 is not None and t2.name in ("MulticastDelegate", "Delegate"):
                    return "delegate"
    except Exception:
        pass
    if td.flags & 0x20:
        return "interface"
    if td.is_enum:
        return "enum"
    if td.is_valuetype:
        return "struct"
    return "class"


def delegate_covered(meta, il, td):
    """Method names the delegate declaration covers (mirror skip_delegate)."""
    try:
        if type_kind(il, meta, td) != "delegate":
            return set()
        inv = None
        try:
            for mi in meta.type_methods(td):
                m = meta.methods[mi]
                if m.name == "Invoke" and not m.is_static:
                    inv = m
                    break
        except Exception:
            inv = None
        if inv is None:
            return set()
        try:
            has_fields = bool(list(meta.type_fields(td)))
        except Exception:
            try:
                has_fields = td.field_count not in (None, 0)
            except Exception:
                has_fields = True
        if has_fields or td.property_count or td.event_count or td.nested_count:
            return set()
        return {"ctor", "cctor", "Invoke", "BeginInvoke", "EndInvoke"}
    except Exception:
        return set()


def enum_ebase(il, td):
    """Underlying keyword for enums (mirror type_decl_line), else None."""
    try:
        if not td.is_enum:
            return None
        _et = il.types[td.element] \
            if 0 <= td.element < len(il.types) else None
        _te = il._type_enum(_et) if _et is not None else 0x08
        return {0x04: "sbyte", 0x05: "byte", 0x06: "short",
                0x07: "ushort", 0x09: "uint", 0x0a: "long",
                0x0b: "ulong"}.get(_te)
    except Exception:
        return None


def _rel_acc(meta, td, rel):
    """Absolute MethodDef for a relative property/event accessor row."""
    try:
        if rel is None or rel < 0:
            return None
        mi = td.method_start + rel
        return meta.methods[mi] if 0 <= mi < len(meta.methods) else None
    except Exception:
        return None


def accessor_methods(meta, td):
    """Absolute MethodDef indices folded into property/event decls."""
    out = set()
    try:
        for k in range(td.property_count or 0):
            pr = meta.properties[td.property_start + k]
            for rel in (pr[1], pr[2]):
                if rel is not None and rel >= 0:
                    mi = td.method_start + rel
                    if 0 <= mi < len(meta.methods):
                        out.add(mi)
    except Exception:
        pass
    try:
        for k in range(td.event_count or 0):
            ev = meta.events[td.event_start + k]
            for rel in (ev[2], ev[3]):
                if rel is not None and rel >= 0:
                    mi = td.method_start + rel
                    if 0 <= mi < len(meta.methods):
                        out.add(mi)
    except Exception:
        pass
    return out


def dump_image(il, meta, img, nest):
    out = ["A " + img.name]
    try:
        from il2cpp.csharp import source_field_name as _sfn
    except Exception:
        _sfn = None
    try:
        from il2cpp.csharp import field_attrs as _fattrs, FA_STATIC as _FA_S
    except Exception:
        _fattrs, _FA_S = None, 0x10
    tds = []
    try:
        t0, tn = img.type_start, img.type_count
        tds = [(t0 + k, meta.typedefs[t0 + k]) for k in range(tn)
               if 0 <= t0 + k < len(meta.typedefs)]
    except Exception:
        return out
    tds.sort(key=lambda p: ((p[1].namespace or ""), (p[1].name or ""), p[0]))
    for ti, td in tds:
        if (td.name or "") in ("<Module>",):
            continue
        tkind = type_kind(il, meta, td)
        try:
            base = None
            if tkind != "delegate" and not td.is_enum and not td.is_valuetype \
                    and not (td.flags & 0x20):
                if td.parent is not None and td.parent >= 0:
                    try:
                        pt = il.types[td.parent] \
                            if td.parent < len(il.types) else None
                        pn = il.type_name(pt) if pt else None
                    except Exception:
                        pn = None
                    if pn and pn != "object":
                        base = pn
            ifaces = []
            try:
                for k in range(td.interfaces_count):
                    ii = meta.interfaces[td.interfaces_start + k]
                    t = il.types[ii] if 0 <= ii < len(il.types) else None
                    ifaces.append(type_name(il, t))
            except Exception:
                pass
            eb = enum_ebase(il, td)
            out.append("T %s kind=%s base=%s ebase=%s ifaces=%s" % (
                owner_path(meta, nest, td, ti), tkind,
                base if base else "-",
                eb if eb else "-",
                ",".join(ifaces) if ifaces else "-"))
        except Exception:
            continue
        try:
            ms = [(td.method_start + k, meta.methods[td.method_start + k])
                  for k in range(td.method_count)
                  if 0 <= td.method_start + k < len(meta.methods)]
        except Exception:
            ms = []
        acc = accessor_methods(meta, td)
        ms = [(mi, m) for mi, m in ms if mi not in acc]
        dskip = delegate_covered(meta, il, td)
        if dskip:
            ms = [(mi, m) for mi, m in ms
                  if not (m.name in (".ctor", ".cctor")
                          or m.name.startswith(("BeginInvoke", "EndInvoke")))]
        rows = []
        for mi, m in ms:
            try:
                ps = meta.method_params(m)
            except Exception:
                ps = []
            try:
                pns = []
                for p in ps:
                    pt = il.types[p.type] if 0 <= p.type < len(il.types) else None
                    pns.append(type_name(il, pt))
            except Exception:
                pns = ["?"] * len(ps)
            try:
                rt = il.types[m.return_type] \
                    if 0 <= m.return_type < len(il.types) else None
            except Exception:
                rt = None
            rows.append("M %s.%s s=%d g=%d f=0x%x (%s)->%s" % (
                owner_path(meta, nest, td, ti), m.name,
                1 if m.is_static else 0, generic_arity(meta, m),
                m.flags, ",".join(pns), type_name(il, rt)))
        rows.sort()
        out.extend(rows)
        try:
            fs = [(td.field_start + k, meta.fields[td.field_start + k])
                  for k in range(td.field_count)
                  if 0 <= td.field_start + k < len(meta.fields)]
        except Exception:
            fs = []
        frows = []
        for fi, f in fs:
            try:
                fn = f.name
            except Exception:
                fn = "?"
            if fn == "value__":
                continue
            if _sfn is not None:
                try:
                    fn = _sfn(il, fi)
                except Exception:
                    pass
            try:
                ft = il.types[f.type] if 0 <= f.type < len(il.types) else None
            except Exception:
                ft = None
            try:
                _fst = 0 if getattr(td, "is_enum", False) else (
                    1 if (_fattrs is not None and _fattrs(il, f) & _FA_S)
                    else 0)
            except Exception:
                _fst = 0
            frows.append("F %s.%s s=%d %s" % (
                owner_path(meta, nest, td, ti), fn, _fst, type_name(il, ft)))
        frows.sort()
        out.extend(frows)
        try:
            prs = [(td.property_start + k,
                    meta.properties[td.property_start + k])
                   for k in range(td.property_count or 0)
                   if 0 <= td.property_start + k < len(meta.properties)]
        except Exception:
            prs = []
        prows = []
        for pi, pr in prs:
            try:
                raw = meta.getstr(pr[0])
            except Exception:
                continue
            g = _rel_acc(meta, td, pr[1])
            s = _rel_acc(meta, td, pr[2])
            try:
                gp = list(meta.method_params(g)) if g is not None else []
            except Exception:
                gp = []
            try:
                sp = list(meta.method_params(s)) if s is not None else []
            except Exception:
                sp = []
            idx = gp if g is not None else sp[:-1]
            if idx:
                nm = (raw.rpartition(".")[0] + ".") if "." in raw else ""
                nm += "this"
            else:
                nm = raw
            try:
                pt = None
                if g is not None:
                    pt = il.types[g.return_type] \
                        if 0 <= g.return_type < len(il.types) else None
                if pt is None and sp:
                    vt = sp[-1].type
                    pt = il.types[vt] if 0 <= vt < len(il.types) else None
                pty = type_name(il, pt)
            except Exception:
                pty = "object"
            try:
                present = [a for a in (g, s) if a is not None]
                st = 1 if (present and all(a.is_static for a in present)) else 0
            except Exception:
                st = 0
            prows.append("P %s.%s s=%d get=%d set=%d %s" % (
                owner_path(meta, nest, td, ti), nm, st,
                1 if g is not None else 0, 1 if s is not None else 0, pty))
        prows.sort()
        out.extend(prows)
        try:
            evs = [(td.event_start + k, meta.events[td.event_start + k])
                   for k in range(td.event_count or 0)
                   if 0 <= td.event_start + k < len(meta.events)]
        except Exception:
            evs = []
        erows = []
        for ei, ev in evs:
            add = _rel_acc(meta, td, ev[2])
            rem = _rel_acc(meta, td, ev[3])
            if add is None or rem is None:
                continue
            try:
                raw = meta.getstr(ev[0])
            except Exception:
                continue
            try:
                et = il.types[ev[1]] if 0 <= ev[1] < len(il.types) else None
                ety = type_name(il, et)
            except Exception:
                ety = "System.Action"
            try:
                st = 1 if (add.is_static and rem.is_static) else 0
            except Exception:
                st = 0
            erows.append("E %s.%s s=%d add=1 rem=1 %s" % (
                owner_path(meta, nest, td, ti), raw, st, ety))
        erows.sort()
        out.extend(erows)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--metadata", required=True)
    ap.add_argument("--binary", required=True)
    ap.add_argument("--only", default=None,
                    help="comma-separated image substring filter")
    ap.add_argument("--out", default=None)
    ap.add_argument("--source", default=None)
    args = ap.parse_args()
    import os as _os
    if _os.environ.get("PYTHONHASHSEED") != "0":
        raise SystemExit("Run with PYTHONHASHSEED=0.")
    root = args.source or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    il = load(root, args.metadata, args.binary)
    meta = il.meta
    nest = nest_parent(meta)
    only = [s.strip().casefold() for s in (args.only or "").split(",") if s.strip()]
    lines = []
    for img in meta.images:
        if only and not any(s in img.name.casefold() for s in only):
            continue
        lines.extend(dump_image(il, meta, img, nest))
    text = "\n".join(lines) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("wrote %d lines to %s" % (len(lines), args.out))
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
