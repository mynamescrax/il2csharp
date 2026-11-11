"""Print metadata, native instructions, and a fresh lift for MethodDefs or VAs."""
import argparse
import json
from pathlib import Path

from corpus_common import load


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--metadata", required=True)
    ap.add_argument("--binary", required=True)
    selection = ap.add_mutually_exclusive_group(required=True)
    selection.add_argument("--va", nargs="+", type=lambda x: int(x, 0),
                           help="native addresses; includes every shared owner")
    selection.add_argument("--mi", nargs="+", type=int,
                           help="exact MethodDef rows (unambiguous snapshot identity)")
    ap.add_argument("--save")
    args = ap.parse_args()
    il = load(args.source, args.metadata, args.binary)
    from il2cpp import Lifter
    from il2cpp import Decompiler

    dec = Decompiler(Lifter(il))
    results = []
    for m in il.meta.methods:
        if not m.addr or (m.index not in args.mi if args.mi is not None else m.addr not in args.va):
            continue
        td = il.meta.typedefs[m.declaring]
        result = {
            "mi": m.index, "va": hex(m.addr),
            "type": f"{td.namespace}.{td.name}".lstrip("."),
            "name": m.name,
            "return": il.type_name(il.types[m.return_type]),
            "params": [{"name": p.name, "type": il.type_name(il.types[p.type])}
                       for p in il.meta.method_params(m)],
        }
        insns, _ = dec._decode(m)
        result["asm"] = [f"{ins.ip:#x} {ins}" for ins in insns]
        result["body"] = dec.lift_method(m, td)
        results.append(result)
    text = json.dumps(results, indent=2, ensure_ascii=False)
    if args.save:
        Path(args.save).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()