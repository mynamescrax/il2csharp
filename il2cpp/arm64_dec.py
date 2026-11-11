from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.dec import Decompiler

class Arm64Decompiler(Decompiler):
    """ARM64 bodies, scaffold milestone: real capstone CFG + asm-comment
    statements through the shared _structure/_final_text pipeline.
    Symbolic execution (an _analyze twin) replaces the comment fill next;
    _lift_asm_block goes away then."""

    def lift_method(self, m, td):
        self._var_types = {}
        L = self.L
        self.eh = None
        inss = L._decode_method(m)
        if not inss:
            return ['/* no code */']
        self.skip_ips = set()
        self.entry_ip = inss[0].ip
        self.last_ip = inss[-1].next_ip
        self._flat_insns = inss
        self._flat_ip_idx = {ins.ip: i for i, ins in enumerate(inss)}
        self._pad_bids = set()
        kept, _over = self._trace_reachable(inss, self.entry_ip, self.last_ip)
        if not kept:
            return ['/* empty */']
        blocks, bmap = self._make_blocks(kept, self.skip_ips)
        if not blocks:
            return ['/* empty */']
        if len(blocks) > 3000:
            raise RuntimeError('cfg too large (%d blocks)' % len(blocks))
        self.rpo = self._rpo(blocks)
        self.phi_pre = {}
        L._var_types = {}
        L._type_hints = {}
        returns = self._returns_value(m)
        for b in blocks:
            self._lift_asm_block(b)
            last = b.insns[-1]
            if b.term and b.term[0] == 'jcc':
                b.cond = self._scaffold_cond(last)
            elif b.term and b.term[0] == 'ret':
                b.ret = 'x0' if returns else ''
        if not any(b.stmts or b.cond is not None or b.ret is not None for b in blocks):
            return ['/* nothing */']
        return self._final_text(self._structure(blocks, bmap, m))

    def _lift_asm_block(self, b):
        for ins in b.insns:
            b.stmts.append('// %#x: %s %s' % (ins.ip, ins.mnemonic, ins.op_str))

    @staticmethod
    def _scaffold_cond(last):
        # capstone renders immediates as #N -- '#' is not lexable C#
        # outside a comment (one bad cond cascades whole-file)
        if last.kind == 'cb':
            reg = last.op_str.split(',')[0].strip().lstrip('#')
            return '%s == 0' % reg if last.mnemonic == 'cbz' else '%s != 0' % reg
        if last.kind == 'tb':
            parts = [p.strip().lstrip('#') for p in last.op_str.split(',')]
            if len(parts) == 3:
                if last.mnemonic == 'tbz':
                    return '((%s >> %s) & 1) == 0' % (parts[0], parts[1])
                return '((%s >> %s) & 1) != 0' % (parts[0], parts[1])
        return 'unknown'
