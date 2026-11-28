"""Count native TEST candidates and real-pass byte-mask proofs on a bounded Win64 sample.

Loads the fixture statically and emits only the selected method bodies in memory.
The optional JSON contains counts and site addresses, not disassembly or source.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

from corpus_common import load


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', default=str(Path(__file__).resolve().parents[1]))
    p.add_argument('--metadata', required=True); p.add_argument('--binary', required=True)
    p.add_argument('--first', type=int, required=True, help='first MethodDef, inclusive')
    p.add_argument('--stop', type=int, required=True, help='last MethodDef, exclusive')
    p.add_argument('--max-insns', type=int, default=800); p.add_argument('--save')
    args = p.parse_args()
    if args.first < 0 or args.stop <= args.first or args.max_insns < 4:
        p.error('need a nonempty row interval and at least four instructions')
    il = load(args.source, args.metadata, args.binary)
    from iced_x86 import Mnemonic as M, OpKind as K
    from il2cpp import Decompiler, Lifter
    from il2cpp import low_byte_test
    dec = Decompiler(Lifter(il)); rows = []; counts = Counter(); accepted = {}
    formatter = low_byte_test.predicate

    def record(lift, test, plan, samples):
        result = formatter(lift, test, plan, samples)
        if result is not None and not lift.dry:
            accepted[hex(test.ip)] = 'int' if plan[2] == 8 else 'bool'
        return result

    consumers = {M.JE, M.JNE, M.JBE, M.JA, M.SETE, M.SETNE, M.SETA, M.SETBE}
    immediates = {K.IMMEDIATE8, K.IMMEDIATE16, K.IMMEDIATE32, K.IMMEDIATE32TO64}
    low_byte_test.predicate = record
    try:
        for m in il.meta.methods[args.first:args.stop]:
            if not m.addr or m.name.startswith(('.ctor', '.cctor')):
                continue
            ins, _ = dec._decode(m)
            if not 4 <= len(ins) <= args.max_insns:
                continue
            counts['decoded'] += 1
            sites = {'immediate': [], 'pair': []}
            for t, j in zip(ins, ins[1:]):
                if (t.mnemonic != M.TEST or t.op0_kind != K.REGISTER or t.next_ip != j.ip or
                        j.mnemonic not in consumers or t.op1_kind == K.REGISTER and t.op0_register == t.op1_register):
                    continue
                if t.op1_kind in immediates:
                    sites['immediate'].append(hex(t.ip))
                elif t.op1_kind == K.REGISTER:
                    sites['pair'].append(hex(t.ip))
            if not any(sites.values()):
                continue
            for family, values in sites.items():
                counts[family + '_rows'] += bool(values)
                counts[family + '_sites'] += len(values)
            accepted.clear()
            dec.lift_method(m, il.meta.typedefs[m.declaring])
            counts['candidate_rows'] += 1
            counts['applied_rows'] += bool(accepted)
            counts.update(accepted.values())
            rows.append(dict(mi=m.index, candidates=sites, applied=dict(accepted)))
    finally:
        low_byte_test.predicate = formatter
    print(json.dumps(counts, sort_keys=True))
    if args.save:
        Path(args.save).write_text(json.dumps(dict(counts=counts, rows=rows), indent=2), encoding='utf8')


if __name__ == '__main__':
    main()
