from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.common import csharp_type_name
from il2cpp.expr import Expr, _ARR_BIAS_RX, _BARE_TOKEN_RX, _BOOL_TY, _INT_TY, _R4_TY, _R8_TY, _USE_BIND_MIN, _recv_fold, _recv_shaped
from il2cpp.names import repr_f32, repr_f64
from il2cpp.runtime.meta import IMM_OPS, meta_lit_repr
from il2cpp.text import _ATOM_PREC, _BIN_PREC, _bin_txt, _fold_bin, _int_lit, _term_up, disp_add, imm_of, reg_name, sdisp, strip_outer
from il2cpp.x64 import ARG_REGS, RMW_OPS, STORE_MNEMONICS, VOLATILE, _CMOV_AS_J, _SFPF, _reg_size, flag_cond
try:
    _MN_NAME = {getattr(Mnemonic, n): n for n in ('MOV', 'MOVZX', 'MOVSX', 'MOVSXD', 'CMP', 'TEST')}
except Exception:                       # no iced (portable fakes)
    _MN_NAME = {}
# fix 134: bases whose raw field reads get a width mark
_W134_BASE_RX = re.compile(r'^[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*$')

if HAVE_ICED:
    _WIDE_FLOAT_MN = frozenset((Mnemonic.ADDSS, Mnemonic.ADDSD, Mnemonic.SUBSS,
                                Mnemonic.SUBSD, Mnemonic.MULSS, Mnemonic.MULSD,
                                Mnemonic.DIVSS, Mnemonic.DIVSD))
else:
    _WIDE_FLOAT_MN = frozenset()


def _unary_txt(op, text, prec):
    """Fix 132e: `op text` for a prefix unary operator (`-` / `~`).

    The operand keeps its bare spelling only when it is atomic for a
    unary prefix: outer-parenthesised, or free of composed precedence
    (prec None / _ATOM_PREC), not sign-led (`-` + `-x` would print the
    predecrement `--x`), and without top-level whitespace (a binary,
    ternary, `as`/`is` or comparison spelled elsewhere). Anything else is
    wrapped, which only ever adds redundant parentheses.
    """
    t = (text or '?').strip()
    try:
        from il2cpp.text import _outer_parens
        if _outer_parens(t):
            return op + t
        wrap = (prec is not None and prec < _ATOM_PREC) or t[:1] in '-+~!'
        if not wrap:
            depth = 0
            q = None
            for ch in t:
                if q:
                    if ch == q:
                        q = None
                    continue
                if ch in '"\'':
                    q = ch
                elif ch in '([{':
                    depth += 1
                elif ch in ')]}':
                    depth -= 1
                elif ch.isspace() and depth <= 0:
                    wrap = True
                    break
        return op + ('(' + t + ')' if wrap else t)
    except Exception:
        return op + '(' + t + ')'

class _InsnMixin:
    def _lane_value(self, origin, offset, expected):
        """A modeled SIMD lane must be spellable as a binary operand.

        `_piece_value` provenance can still carry the bare `?`/`_`
        placeholder text (an unproven value that happens to have parts);
        stamping it into arithmetic renders `real27 * ?`, which is
        unparseable (LegsAnimator VA 0x180644EF0 gate). Decline those
        to today's spelling; `unknown`-text lanes still render (they
        parse).
        """
        if origin is None:
            return None
        v = self._piece_value(origin, offset, 4, expected)
        if v is None or not v.text or v.text in ('?', '_'):
            return None
        return v

    def _insn(self, ins, insns, idx, fmt, end):
        mn = ins.mnemonic
        asm = fmt.format(ins) if fmt else None
        ip = ins.ip
        self._cur_ip = ip
        self._cur_mn = mn            # fix 60: stamped onto self.flags
        # fix 60b: an instruction that writes (or undefines) SF/PF on
        # the real machine invalidates fix 60's derivation whether or
        # not a handler below models it. Clearing only the recorded
        # SETTER -- never the pair -- means a modelled write re-stamps
        # it one line later, an unmodelled one degrades to the honest
        # `unknown`, and every ordinary mapped-operator branch reads
        # exactly what it read before this fix existed.
        if _SFPF and (ins.rflags_written | ins.rflags_undefined) & _SFPF:
            self._flags_mn = None

        def A(i):  # operand helpers
            return ins.op_kind(i)

        # --- branches ---------------------------------------------------
        if ins.flow_control in (FlowControl.CONDITIONAL_BRANCH,) and A(0) == OpKind.NEAR_BRANCH64:
            t = ins.near_branch_target
            op = self.CMP_OPS.get(mn)
            lhs, rhs = (self.flags or (Expr('?', None, '?'), Expr('?', None, '?')))
            self._note_use(lhs)
            self._note_use(rhs)
            if op is None:
                # the rare flag-specific jumps (JS/JNS/JO/JNO/JP/JNP --
                # CMP_OPS has never mapped them) can't splice a bare '?'
                # in as if it were a comparison operator: it collides with
                # C#'s own ternary token once `lhs`/`rhs` is itself
                # ternary-shaped (a CMOV-derived value, batch 27) --
                # `if (X ? 0) goto` isn't even a complete ternary, let
                # alone a valid condition. `unknown` is honest and always
                # parses. fix 60 recovers the derivable ones first.
                _c = flag_cond(getattr(self, '_flags_mn', None), mn,
                               strip_outer(lhs.text) if lhs else '?',
                               strip_outer(rhs.text) if rhs else '?')
                self.emit(ip, 'if (%s) goto L_%x;' % (_c or 'unknown', t), asm)
            else:
                lt = strip_outer(lhs.text) if lhs else '?'
                rt = strip_outer(rhs.text) if rhs else '?'
                if rt == 'null':
                    self.emit(ip, 'if (%s %s null) goto L_%x;' % (lt, op, t), asm)
                else:
                    self.emit(ip, 'if (%s %s %s) goto L_%x;' % (lt, op, rt, t), asm)
            self.flags = None
            return
        if mn == Mnemonic.JMP and A(0) == OpKind.NEAR_BRANCH64:
            t = ins.near_branch_target
            fs, fe = self.il.function_extent(t)
            if t < self.cur_va or t >= end:
                # jump outside this method: tail call
                # A direct jump to the proved scalar sqrt wrapper is
                # its return path, not a GPR-argument helper call.
                if t == getattr(self, 'rt_sqrt', None):
                    value = self.reg('XMM0')
                    self._hint_tok(value, _R8_TY)
                    text = value.text if value is not None and not value._unk else '?'
                    self.emit(ip, 'return Math.Sqrt(%s); /* tail */' % text, asm)
                    for r in VOLATILE:
                        self.regs.pop(r, None)
                    return
                cands = self.il.addr_candidates.get(t)
                recv0 = self.regs.get('RCX')
                info = None
                if cands and len(cands) == 1:
                    info = cands[0]
                elif cands:
                    info = self._shared_parameterless_ctor_target(cands, recv0)
                    if info is None:
                        # same receiver-chain disambiguation as _call for
                        # non-constructor shared methods
                        recv_td = self._td_of(recv0.ty) if recv0 is not None else None
                        if recv_td is None and recv0 is not None:
                            recv_td = self._array_receiver_td(recv0.ty)
                        chain = self._legacy_shared_receiver_chain(recv_td)
                        hits = [c for c in cands if c[0] == 'method'
                                and self.meta.methods[c[1]].declaring in chain]
                        if len(hits) == 1:
                            info = hits[0]
                        if info is None:
                            info = self._shared_same_render_target(cands)
                if info is None and not cands:
                    info = self.il.addr_to_method.get(t)
                if info or self.bin.is_exec_va(t):
                    args = []
                    arg_exprs = []
                    for r in ARG_REGS:
                        e = self.regs.get(r)
                        args.append(e.text if e else '_')
                        arg_exprs.append(e)
                    while args and args[-1] == '_':
                        args.pop()
                        arg_exprs.pop()
                    args = [a if a and a.strip() else '_' for a in args]
                    # fix 94: a shared tail's hidden instantiation
                    # argument is compiler plumbing (same proof as
                    # `_call`), and trailing stale unknowns are not
                    # arguments (fix 58). Both lists stay parallel.
                    tail_gen = None
                    tail_nm = None
                    tail_ret = None
                    if info is None and cands and len(cands) > 1:
                        tail_ret = self._shared_tail_return_target(cands)
                        tail_gen = self._tail_hidden_generic(cands, args, arg_exprs)
                        if tail_gen is not None:
                            tail_nm = tail_gen[0]
                            _tgi = tail_gen[2]
                            if _tgi < len(args):
                                args = args[:_tgi] + args[_tgi + 1:]
                            if _tgi < len(arg_exprs):
                                arg_exprs = arg_exprs[:_tgi] + arg_exprs[_tgi + 1:]
                        self._tail_trim_stale(args, arg_exprs)
                        if info is None and tail_ret is not None and tail_ret[0] == 'method' \
                                and (tail_gen is None or tail_gen[1] is None):
                            info = tail_ret
                    if info is not None and info[0] == 'method':
                        m2 = self.meta.methods[info[1]]
                        args = self._tail_method_args(info[1], args, arg_exprs)
                        init_kind = self._constructor_initializer_kind(
                            m2, arg_exprs[0] if arg_exprs else None)
                        if init_kind is not None:
                            self.emit(ip, '%s..ctor(%s); return;' %
                                      (init_kind, ', '.join(args[1:])), asm)
                            return
                        if not m2.is_static and args and args[0] != '?' \
                                and (args[0] == 'this' or '.' in args[0]
                                     or _BARE_TOKEN_RX.match(args[0])
                                     or (_recv_shaped(args[0])
                                         and not m2.name.startswith('.'))):
                            # m2.name is '.ctor'/'.cctor' from metadata; the
                            # join adds the dot (base..ctor is the excepted
                            # literal pair above); the _recv_shaped arm is
                            # fix 40c, the main-path fix-40 rule
                            nm2 = m2.name[1:] if m2.name.startswith('.') else m2.name
                            call = '%s.%s(%s)' % (_recv_fold(args[0]), nm2, ', '.join(args[1:]))
                        else:
                            call = '%s(%s)' % (self._info_name(info), ', '.join(args))
                        _sg137 = self._tail_accessor(info[1], args)  # fix 137
                        if _sg137 is not None:
                            call = _sg137
                        rti = m2.return_type
                        void = 0 <= rti < len(self.il.types) and \
                            ((self.il.types[rti][1] >> 16) & 0xFF) == 0x01
                        self._emit_tail(ip, call, asm, void=void)
                        for r in VOLATILE:
                            self.regs.pop(r, None)
                        return
                    if tail_gen is not None and tail_gen[1] is not None:
                        # fix 94: resolved through the hidden
                        # instantiation argument -- render the true
                        # generic callee, never the shared marker.
                        _tg_call, _tg_m = self._tail_generic_call(
                            tail_gen[0], tail_gen[1], args, arg_exprs)
                        _tg_rti = _tg_m.return_type
                        _tg_void = 0 <= _tg_rti < len(self.il.types) and \
                            ((self.il.types[_tg_rti][1] >> 16) & 0xFF) == 0x01
                        self._emit_tail(ip, _tg_call, asm, void=_tg_void)
                        for r in VOLATILE:
                            self.regs.pop(r, None)
                        return
                    if tail_ret is not None and tail_ret[0] == 'generic':
                        _sv_xmm = list(getattr(self, '_xmm_pending', []) or [])
                        _sv_cca = getattr(self, '_call_class_args', None)
                        _sv_slot = dict(getattr(self, 'slot_types', {}) or {})
                        _sv_hints = dict(getattr(self, '_type_hints', {}) or {})
                        try:
                            _tr_call, _tr_m = self._tail_generic_call(tail_ret[1], tail_ret[2], args, arg_exprs)
                        except Exception:
                            self._xmm_pending = _sv_xmm
                            self._call_class_args = _sv_cca
                            self.slot_types = _sv_slot
                            self._type_hints = _sv_hints
                            tail_ret = None
                        else:
                            _tr_rti = _tr_m.return_type
                            _tr_void = 0 <= _tr_rti < len(self.il.types) and ((self.il.types[_tr_rti][1] >> 16) & 0xFF) == 0x01
                            self._emit_tail(ip, _tr_call, asm, void=_tr_void)
                            for r in VOLATILE:
                                self.regs.pop(r, None)
                            return
                    nm = self._call_name(t)
                    raise_exc = self._named_raise_throw(t, nm)
                    if raise_exc is not None:
                        self.emit(ip, 'throw new %s();' % raise_exc, asm)
                        for r in VOLATILE:
                            self.regs.pop(r, None)
                        return
                    if t in self.rt_wbarrier and args:
                        # a write barrier can be the very last thing a void
                        # method does (`return
                        # il2cpp_codegen_write_barrier(&f, v);`, compiled as
                        # a tail jmp) -- same conversion `_call` does for the
                        # ordinary (non-tail) case, via the shared helper.
                        dst, src2 = self._wb_operands(args, arg_exprs)
                        self._wb_finish(ip, dst, src2, asm, tail=True)
                        for r in VOLATILE:
                            self.regs.pop(r, None)
                        return
                    if nm == 'il2cpp_array_new' and args and args[0].startswith('typeof('):
                        m0 = re.search(r'typeof\(([^[]+)(\[(,*)\])\)', args[0])
                        if m0:
                            rank = 1 + len(m0.group(3))
                            dims = [a for a in args[1:1 + rank] if a and a != '_']
                            self._emit_tail(ip, 'new %s[%s]' % (
                                m0.group(1), ']['.join(dims) if dims else '0'), asm)
                            for r in VOLATILE:
                                self.regs.pop(r, None)
                            return
                    _eff_nm = tail_nm or nm
                    if tail_nm is None and '/*shared body,' in _eff_nm:
                        # one shared body, one argument list: an
                        # unresolved tail is bounded exactly like
                        # `_call`'s by the 21j arity proof, so a
                        # trailing plumbing zero stops being an
                        # invented `(this, 0)` (see _shared_tail_keep).
                        _keep = self._shared_tail_keep(t, args)
                        if _keep is not None and 0 < _keep < len(args):
                            args = args[:_keep]
                            arg_exprs = arg_exprs[:_keep]
                    if _eff_nm in self.RT_ARITY and len(args) > self.RT_ARITY[_eff_nm]:
                        args = args[:self.RT_ARITY[_eff_nm]]
                    elif tail_nm is None and re.fullmatch(r'sub_[0-9a-f]+', nm) and len(args) > 4:
                        args = args[:4]
                    self._emit_tail(ip, '%s(%s)' % (_eff_nm, ', '.join(args)), asm)
                    for r in VOLATILE:
                        self.regs.pop(r, None)
                    return
            self.emit(ip, 'goto L_%x;' % t, asm)
            return
        if ins.flow_control == FlowControl.RETURN:
            rax = self.reg('RAX')
            xmm0 = self.reg('XMM0')
            selected = getattr(self, '_return_reg', None)
            if selected == 'XMM0':
                rv = xmm0 if xmm0 is not None else rax
            elif selected == 'RAX':
                rv = rax if rax is not None else xmm0
            else:
                # Standalone instruction tests may not carry MethodDef
                # context; retain the old conservative fallback for them.
                rv = xmm0 if (xmm0 is not None and rax is None) else rax
            if rv is not None and rv.kind not in ('int',) or (rv is not None and rax is not None):
                self.emit(ip, 'return %s;' % strip_outer(self._materialize(rv, 160)), asm)
            else:
                self.emit(ip, 'return;', asm) if rv is None else self.emit(ip, 'return %s;' % strip_outer(rv.text), asm)
            return
        if mn == Mnemonic.CALL:
            if ins.op0_kind == OpKind.NEAR_BRANCH64 \
                    and self._is_stack_probe(ins.near_branch_target):
                # MSVC __chkstk preserves every register except RAX,
                # which it returns UNCHANGED -- the generic CALL path's
                # volatile pop kills the receiver in RCX before the
                # `mov rdi,rcx` save after a big-frame prologue, and
                # renders the probe as a managed call with an argument
                # spray. Frame setup is not source code: no statement.
                if self.asm_comments and asm:
                    self.emit(ip, '', asm)
                return
            self._call(ins, asm)
            return
        if mn in (Mnemonic.NOP, Mnemonic.INT3, Mnemonic.ENDBR64):
            return
        if mn == Mnemonic.PUSH:
            self.rsp_delta -= 8
            return
        if mn == Mnemonic.POP:
            self.rsp_delta += 8
            return

        # --- memory destinations ------------------------------------------
        # Must precede the register-move handlers: those key off op0_register,
        # which is NONE for a memory destination, so they would swallow the
        # store and write a bogus register instead.
        if A(0) == OpKind.MEMORY:
            if mn in STORE_MNEMONICS:
                self._write_mem(ins, asm)
                return
            rmw = RMW_OPS.get(mn)
            if rmw is not None:
                self._rmw_mem(ins, asm, rmw)
                return

        # --- gpr moves ----------------------------------------------------
        if mn in (Mnemonic.MOV, Mnemonic.MOVZX, Mnemonic.MOVSX, Mnemonic.MOVSXD):
            dst = reg_name(ins.op0_register)
            if A(0) == OpKind.REGISTER and A(1) in (OpKind.REGISTER,):
                src = reg_name(ins.op1_register)
                if mn == Mnemonic.MOV and src == 'RSP' and dst != 'RBP' \
                        and _reg_size(ins.op0_register) == 8 \
                        and _reg_size(ins.op1_register) == 8:
                    # `mov r11,rsp` parks the frame base in a GPR so later
                    # [copy+N] traffic names one home across `sub rsp`
                    # shifts (NetBitBuffer mi 117615: mem[8]/mem_8/obj2
                    # twins). Track the copy's stack offset instead of
                    # dropping it to None; arithmetic/index uses decline
                    # back to the unknown-base shapes below. Text stays
                    # '?' so any unforeseen consumer renders what a None
                    # register renders today.
                    e = Expr('?', None, 'ptr')
                    e._stack_offset = self.rsp_delta
                    self.set_reg(dst, e)
                    return
                self._copying = True
                try:
                    e = self.reg(src)
                finally:
                    self._copying = False
                if dst == 'RBP' and e is not None \
                        and getattr(e, '_stack_offset', None) is not None:
                    # a frame-copy artifact landing in RBP: today the
                    # source was untracked, so RBP stayed unreadable and
                    # _rbp_is_frame() held. Keep None, not a '?'-text
                    # copy that would flip the frame predicate.
                    e = None
                if dst == 'RBP' and src == 'RSP':
                    # `mov rbp,rsp`: the value stays unreadable (RSP is
                    # never tracked) so the None arm of _rbp_is_frame()
                    # keeps holding -- but record the FACT, because the
                    # pass-2 merge replaces that None with Expr('?') and
                    # every [rbp+N] in a merged block would then fabricate
                    # pointer arithmetic on the never-written seed.
                    self._rbp_frame = True
                if mn != Mnemonic.MOV:
                    # a sign/zero extension moves an integer (chars and
                    # bools included -- both are int-promoted anyway)
                    self._hint_tok(e, _INT_TY)
                if mn == Mnemonic.MOVZX:
                    if (ins.op0_register & 0x0F) == (ins.op1_register & 0x0F)\
                            and e is not None and e.text and e.text != '?':
                        # movzx r32, r8 of the same architectural register
                        # is a width no-op for bool/int values: skip the
                        # self-copy `num4 = (num4 & 0xFF);` entirely.
                        return
                    # fix 61c: the mask has to match the SOURCE width.
                    # `movzx eax,cx` is a 16-bit zero-extension and was
                    # rendering an 8-bit mask (disasm-proven at
                    # <GenerateNight>g__ContainsAny|4_0 0x1806c65a0,
                    # where every movzx in the method is 16-bit).
                    _w = _reg_size(ins.op1_register)
                    _msk = '0xFFFF' if _w == 2 else '0xFF'
                    e = self._mk('(%s & %s/*z*/)' % (e.text, _msk),
                                 e.ty, e.kind) if e else None
                    if e is not None:
                        # fix 61a: without this the Expr keeps _prec
                        # None, every composition reads it as an atom,
                        # and _bin_txt STRIPS the parens it was handed --
                        # `(x & 0xFF) + i*8` collapses to
                        # `x & 0xFF + i*8`, which C# groups as
                        # `x & (0xFF + i*8)`: different expression, still
                        # parses, invisible to the parse gate. It is also
                        # why _bool_sugar could not strip these -- its
                        # regex needs the parenthesised group.
                        e._prec = _BIN_PREC['&']
                self.set_reg(dst, e)
                return
            if A(1) in IMM_OPS:
                try:
                    v = ins.immediate(1)
                except Exception:
                    v = 0
                if v > 0x7FFFFFFFFFFFFFFF:
                    v -= 1 << 64
                self.set_reg(dst, Expr(str(v), None, 'int'))
                return
            if A(1) == OpKind.MEMORY:
                e = self._read_mem(ins, asm)
                self.set_reg(dst, e)
                return
            return
        if mn in (Mnemonic.MOVSS, Mnemonic.MOVSD, Mnemonic.MOVUPS, Mnemonic.MOVAPS, Mnemonic.MOVUPD, Mnemonic.MOVAPD):
            dst = reg_name(ins.op0_register)
            if A(1) == OpKind.MEMORY:
                e = self._read_mem(ins, asm)
                if e is not None and self.il._type_enum(e.ty) not in (0x0c, 0x0d):
                    e = self._copy_expr(e)
                    if getattr(e, '_slice', None) is None:
                        e.kind = 'float'
                self.set_reg(dst, e)
                return
            if A(1) == OpKind.REGISTER:
                self._copying = True
                try:
                    src_e = self.reg(reg_name(ins.op1_register))
                finally:
                    self._copying = False
                if mn == Mnemonic.MOVSS:
                    # Scalar single merge: low lane from src, lanes 1..3
                    # preserved from dst. Hardware truth; the old full copy
                    # dropped the dst high lanes. Decline (any lane
                    # unproven) keeps today's full copy -- a copy is closer
                    # to truth than unknown, so never pop here.
                    _dst_e = self.reg(dst)
                    _parts = []
                    _ok = src_e is not None and _dst_e is not None
                    if _ok:
                        _v0 = self._lane_value(src_e, 0, _R4_TY)
                        _ok = _v0 is not None
                        if _ok:
                            _parts.append((0, _v0, 0, 4))
                            for _lo, _off in ((4, 4), (8, 8), (12, 12)):
                                _v = self._lane_value(_dst_e, _off, _R4_TY)
                                if _v is None:
                                    _ok = False
                                    break
                                _parts.append((_lo, _v, 0, 4))
                    if _ok:
                        _me = Expr('?', None, 'bits')
                        _me._parts = _parts
                        self.set_reg(dst, _me)
                        return
                self.set_reg(dst, src_e)
                return
            return
        if mn in (Mnemonic.MOVQ, Mnemonic.MOVD, Mnemonic.MOVDQA, Mnemonic.MOVDQU):
            # GPR<->XMM/XMM<->XMM data moves (struct-field extraction out of
            # a value loaded via an earlier movups/movsd, a boxed-pointer
            # round-trip through an XMM temp, etc). Previously unhandled
            # entirely for a register destination (STORE_MNEMONICS only
            # covers the memory-destination case) -- the destination
            # register's PRIOR binding survived untouched, so a register
            # reused across a class-init guard and then legitimately
            # overwritten by a movq kept rendering the guard's stale
            # `typeof(X)` class-token value at every later read. An opaque
            # same-text copy (matching the MOVSS/MOVD reg-copy convention a
            # few lines up) does not model the bit reinterpretation, but it
            # is a real, current value instead of an arbitrarily-old one --
            # confirmed live on VolumeManager.CheckStack (VA 0x182878F40)
            # and structurally, ~10 sites in one method, on
            # SendMouseEvents's OnMouseUpdate (VA 0x182C7E2B0).
            dst = reg_name(ins.op0_register)
            if A(1) == OpKind.REGISTER:
                self._copying = True
                try:
                    src_e = self.reg(reg_name(ins.op1_register))
                finally:
                    self._copying = False
                self.set_reg(dst, src_e)
                return
            if A(1) == OpKind.MEMORY:
                self.set_reg(dst, self._read_mem(ins, asm))
                return
            return
        if mn == Mnemonic.PSRLDQ:
            # Packed byte-granularity shift of a 128-bit XMM register --
            # commonly used right before a movq to pull the SECOND field of
            # a 16-byte struct (loaded whole via an earlier movups) into a
            # GPR. Modeling the actual byte shift would need a real
            # struct-field model this Expr shape doesn't have; the honest
            # move is to invalidate the destination so the following movq
            # renders '?' / drops the arg (matching the `?addr`/omitted-arg
            # conventions elsewhere in this file) instead of silently
            # keeping the PRE-shift value, which is a confidently wrong
            # answer (the first field, not the second) rather than an
            # honestly missing one.
            self.regs.pop(reg_name(ins.op0_register), None)
            return
        if mn == Mnemonic.LEA:
            dst = reg_name(ins.op0_register)
            if A(1) == OpKind.MEMORY:
                if ins.memory_base == IReg.RIP:
                    slot = ins.ip_rel_memory_address
                    usg = self.il.decode_slot(slot)
                    if usg:
                        e = Expr(usg.get('text', 'usage_%#x' % slot),
                                 usg.get('type'), 'usage')
                        if usg.get('td') is not None:
                            e._td = usg['td']
                        self.set_reg(dst, e)
                        return
                    s = self._rip_str(slot)
                    if s is not None:
                        self.set_reg(dst, Expr('&' + s, None, 'ptr'))
                        return
                    self.set_reg(dst, Expr('&data_%x' % slot, None, 'ptr'))
                    return
                if ins.memory_base == IReg.RSP or (ins.memory_base == IReg.RBP
                        and self._rbp_is_frame()):
                    address = self._stack_address(ins)
                    name = self.stack_map.get(address) if address is not None else None
                    if name is None:
                        name = self.slot_var(ins.memory_displacement)
                    value = Expr('&' + name, None, 'ptr')
                    value._stack_offset = address
                    self.set_reg(dst, value)
                    return
                _lb = self.reg(reg_name(ins.memory_base)) \
                    if ins.memory_base not in (IReg.NONE, IReg.RIP) else None
                if _lb is not None and getattr(_lb, '_stack_offset', None) is not None \
                        and ins.memory_index == IReg.NONE and dst != 'RBP':
                    # address of an RSP-copy home: the &slot shape of
                    # the RSP path above, keyed by absolute address. RBP
                    # stays legacy: the frame path owns its disp keys.
                    _caddr = _lb._stack_offset + sdisp(ins.memory_displacement)
                    _cname = self.stack_map.get(_caddr)
                    if _cname is None:
                        _cname = self.slot_var(_caddr - self.rsp_delta)
                    _cval = Expr('&' + _cname, None, 'ptr')
                    _cval._stack_offset = _caddr
                    self.set_reg(dst, _cval)
                    return
                if dst == 'RBP' and _lb is not None \
                        and getattr(_lb, '_stack_offset', None) is not None:
                    # frame pointer from a copy: today's unknown-base
                    # shape, so _rbp_is_frame() still holds.
                    self.set_reg(dst, self._indexed_lea(ins, None))
                    return
                base = self.reg(reg_name(ins.memory_base))
                if base is not None and getattr(base, '_stack_offset', None) is not None \
                        and ins.memory_index != IReg.NONE and ins.memory_base != IReg.RBP:
                    # index arithmetic on a frame copy: provenance
                    # unproved, keep the unknown-base shape.
                    self.set_reg(dst, self._indexed_lea(ins, None))
                    return
                disp = sdisp(ins.memory_displacement)
                if base is not None and ins.memory_index == IReg.NONE:
                    _bte = self.il._type_enum(base.ty) if isinstance(base.ty, tuple) else 0
                    if _bte != 0x0f and base.kind == 'int' and _int_lit(base.text) is None:
                        # `lea r,[ireg+N]` over an integer (the aligned-size
                        # `+3 & -4` idiom) is integer arithmetic: keep the
                        # integer kind so offset chains stay int-typed
                        # instead of degrading to object temps. A stale int
                        # kind on a pointer-typed base (call results predate
                        # ptr kinds) still takes the cursor path below, and
                        # literal bases keep the constant-fold path below.
                        dtxt = disp_add(disp)
                        ne = self._mk('(%s %s)' % (base.text, dtxt),
                                       self._arty(base), 'int')
                        ne._prec = _BIN_PREC['+']
                        self.set_reg(dst, ne)
                        return
                    fe = self._field_expr(base, disp, 8)
                    # a named field taken by address: `lea rcx,[this+0x20]` is the
                    # byref receiver of a value-type instance call (int.ToString)
                    if fe.kind in ('obj', 'arr', 'str') or ('->' in fe.text) \
                            or ('.' in fe.text
                                and not fe.text.startswith('*')):
                        self.set_reg(dst, self._mk('&' + fe.text, fe.ty, 'ptr'))
                    else:
                        # `lea r,[reg+N]` with a constant base is how the
                        # compiler materialises a small constant. Unfolded it
                        # reaches every literal consumer (enum member fold,
                        # bool fold, _fimm) as the composite text `(0 + 0x3)`,
                        # which none of them can parse -- which is why
                        # `FileMode.Open` printed as a bare `3`. Only a
                        # literal base folds; a symbolic base keeps the exact
                        # pointer text it had, including the `+ 0x0` form -- fix 88
                        dtxt = disp_add(disp)
                        fold = (_fold_bin(base.text, _ATOM_PREC, dtxt[0],
                                          dtxt[2:], _ATOM_PREC)
                                if _int_lit(base.text) is not None else None)
                        if fold is not None:
                            ce = self._mk(fold[0], fe.ty, 'int')
                            ce._prec = fold[1]
                            self.set_reg(dst, ce)
                        else:
                            prefix, ty = '', fe.ty
                            if fe.text.startswith('*') and isinstance(base.ty, tuple) \
                                    and self.il._type_enum(base.ty) == 0x0f:
                                # chain-miss offset from a typed pointer addresses
                                # variable payload: a byte offset, so the honest
                                # rvalue casts first (the convention raw stores
                                # use). An already-byte base needs no cast.
                                try:
                                    _pte = self.il._type_enum(self.il.type_from_ptr(base.ty[0]))
                                except Exception:
                                    _pte = None
                                if _pte == 0x05:
                                    ty = base.ty
                                else:
                                    _bt = self._byte_ptr_ty()
                                    if _bt is not None:
                                        prefix, ty = '(byte*)', _bt
                            if prefix:
                                self.set_reg(dst, self._mk('(byte*)%s %s' % (base.text, dtxt),
                                                           ty, 'ptr'))
                            else:
                                self.set_reg(dst, self._mk('(%s %s)' % (base.text, dtxt),
                                                           ty, 'ptr'))
                else:
                    self.set_reg(dst, self._indexed_lea(ins, base))
                return
            return

        # --- binops -----------------------------------------------------
        if mn in (Mnemonic.ADD, Mnemonic.SUB, Mnemonic.IMUL, Mnemonic.AND, Mnemonic.OR,
                  Mnemonic.XOR, Mnemonic.SHL, Mnemonic.SHR, Mnemonic.SAR):
            dst = reg_name(ins.op0_register)
            if dst == 'RSP' and mn in (Mnemonic.ADD, Mnemonic.SUB) and A(1) in IMM_OPS:
                # Stack locals/arguments are keyed by offset from the entry RSP.
                # Track fixed-frame alloc/free so the same slot keeps one name
                # across prologue setup and later call-site stack arguments.
                adj = imm_of(ins, 1)
                self.rsp_delta += adj if mn == Mnemonic.ADD else -adj
                return
            # 3-operand `imul dst, src, imm` (MSVC's scaled-index
            # idiom): the left operand is op1, NOT the destination's
            # stale old value, and the multiplier is operand 2 --
            # mishandled, an array held in dst renders `arr * idx`
            # with kind 'arr' and every later [dst + base + disp]
            # deref mangles (InputDeviceBuilder 0x1825AA5B0)
            if mn == Mnemonic.IMUL and A(2) in IMM_OPS:
                if A(1) == OpKind.MEMORY:
                    se = (None if getattr(self, '_memory_rhs_loop_guard', False)
                          else self._read_mem(ins, asm))
                else:
                    se = self.reg(reg_name(ins.op1_register))
                self._hint_tok(se, _INT_TY)
                st = se.text if se else '?'
                sp = (se._prec if se is not None else None) or _ATOM_PREC
                v3 = str(imm_of(ins, 2))
                fr = _fold_bin(st, sp, '*', v3, _ATOM_PREC)
                if fr is not None:
                    e = self._mk(fr[0], self._arty(se), 'int')
                    e._prec = fr[1]
                else:
                    e = self._mk(_bin_txt(st, sp, '*', v3, _ATOM_PREC),
                                 self._arty(se), 'int')
                    e._prec = _BIN_PREC['*']
                self.set_reg(dst, e)
                return
            a = self.reg(dst)
            be = None
            if A(1) in IMM_OPS:
                v = imm_of(ins, 1)
                # pointer-kind adds/sub are address math: render the offset in
                # the same hex as disp_add (`add rcx, 0x20` after a LEA prints
                # `+ 0x20` like _mem_lvalue's `*(b + i*8 + 0x20)`), so a
                # write-barrier twin lands byte-identical to the plain store
                # and the exact-text twin dedup in the barrier path catches it
                a0 = self.reg(dst)
                if mn in (Mnemonic.ADD, Mnemonic.SUB) and a0 is not None \
                        and a0.kind == 'ptr' and -0x80000000 < v < 0x80000000:
                    btxt = '%+d' % v if v < 0 else '%#x' % v
                else:
                    btxt = str(v)
            elif A(1) == OpKind.REGISTER:
                be = self.reg(reg_name(ins.op1_register))
                btxt = be.text if be else '?'
            elif A(1) == OpKind.MEMORY:
                # A register destination does not imply a register source:
                # sub ecx,[ammo+slot*4+20h] is the real ReloadSMG capacity
                # calculation, not subtraction of an unmodelled value.
                # Structured direct loops replay their native header, so
                # this operand is recomputed on every back edge (ReadSpan,
                # mi 11974). Potential indirect dispatch still keeps the
                # honest unknown because its hidden control flow is unproved.
                if not getattr(self, '_memory_rhs_loop_guard', False):
                    be = self._read_mem(ins, asm)
                btxt = be.text if be else '?'
            else:
                btxt = '?'
            op = {Mnemonic.ADD: '+', Mnemonic.SUB: '-', Mnemonic.IMUL: '*', Mnemonic.AND: '&',
                  Mnemonic.OR: '|', Mnemonic.XOR: '^', Mnemonic.SHL: '<<', Mnemonic.SHR: '>>',
                  Mnemonic.SAR: '>>'}[mn]
            # `imul r,idx,S; add r, arr` -- the scaled index lands in
            # the base slot; keep the composite ARRAY-typed so a later
            # [r + D] deref folds to `(arr + idx*S)[k]` element syntax
            # instead of raw byte-pointer arithmetic
            if mn == Mnemonic.ADD and be is not None and be.kind == 'arr' \
                    and (a is None or a.kind in ('int', '?')):
                e = self._mk('%s + %s' % (be.text,
                                           _term_up(a.text, mul=True) if a else '?'), be.ty, 'arr')
                self.set_reg(dst, e)
                self.flags = (e, Expr('0', None, 'int'))
                return
            # self-operand folds: xor/sub with itself -> 0; and/or with itself -> itself
            if A(1) == OpKind.REGISTER and reg_name(ins.op0_register) == reg_name(ins.op1_register)                 and mn in (Mnemonic.XOR, Mnemonic.SUB):
                e = Expr('0', a.ty if a else None, 'int')
                self.set_reg(dst, e)
                self.flags = (e, Expr('0', None, 'int'))
                return
            # ADD/SUB of an object address and a constant is also how
            # native code forms a field address for a GC write barrier.
            if mn in (Mnemonic.ADD, Mnemonic.SUB) and a is not None \
                    and a.kind in ('obj', 'sfblob') and A(1) in IMM_OPS \
                    and _reg_size(ins.op0_register) == 8:
                offset = imm_of(ins, 1) * (1 if mn == Mnemonic.ADD else -1)
                field = self._field_expr(a, offset, 8)
                if field.ty is not None and not field.text.startswith('*') \
                        and (field.text.startswith(_recv_fold(a.text) + '.') or a.kind == 'sfblob'):
                    e = self._mk('&' + field.text, field.ty, 'ptr')
                    self.set_reg(dst, e)
                    self.flags = (e, Expr('0', None, 'int'))
                    return
            if mn == Mnemonic.XOR and btxt == '1' and a is not None \
                    and a.ty is not None and self.il._type_enum(a.ty) == 0x02:
                self.set_reg(dst, self._mk('!(%s)' % a.text, a.ty, 'int'))
                self.flags = None
                return
            # GPR arithmetic/logic is integer by construction (floats go
            # through SSE): type the operands and, when nothing better is
            # known, the result
            self._hint_tok(a, _INT_TY)
            self._hint_tok(be, _INT_TY)
            rty = self._arty(a)
            rkind = a.kind if a else '?'
            if mn == Mnemonic.ADD and be is not None and be.kind == 'ptr' \
                    and (a is None or a.kind in ('int', '?')):
                # integer offset plus a pointer (`off + cursor` payload
                # destinations) composes an address: pointer kind so uses
                # render compilable arithmetic. The type only when the
                # pointer is byte-proven; otherwise honestly untyped.
                rkind = 'ptr'
                rty = be.ty if self._is_byte_ptr_ty(be.ty) else None
            a_txt = a.text if a else '?'
            ap = a._prec if a is not None else None
            bp = be._prec if be is not None else None
            if len(a_txt) + len(btxt) > 160:
                if a is not None and not getattr(self, 'dry', False) \
                        and not getattr(a, '_no_bind', False) \
                        and getattr(a, '_alloc', None) is None \
                        and len(a.text or '') >= _USE_BIND_MIN:
                    # the operand re-renders at every later use; bind it
                    # so one typed temp is shared. Minting an anonymous
                    # twin here would sit outside a later bind's rewrite
                    # window and duplicate the full text. Dry keeps the
                    # old spelling so phi discovery sees today's texts.
                    self._bind(a)
                    a_txt, ap = a.text, None
                else:
                    v = self.new_var()
                    self.emit(ip, 'var %s = %s;' % (v, a_txt), None)
                    a_txt = v
                    ap = None
            if mn in (Mnemonic.ADD, Mnemonic.SUB) and btxt == '1':
                e = self._mk(_bin_txt(a_txt, ap or _ATOM_PREC, op, '1', _ATOM_PREC),
                             rty, rkind)
                e._prec = _BIN_PREC[op]
                self.set_reg(dst, e)
            elif op in ('&', '|') and btxt == a_txt:
                e = a
                self.set_reg(dst, a)
            else:
                # Shape B: `lea r,[arr+i*S]; add r, 0x20` -- the array
                # header bias lands after the index term; fold to `&arr[i]`
                # when the base is array-typed and the bias aligns.
                if mn == Mnemonic.ADD and a is not None and a.ty is not None \
                        and btxt not in ('?',) and _int_lit(btxt) is not None:
                    af = self._arr_add_fold(a.text, btxt, a.ty)
                    if af is not None:
                        self.set_reg(dst, self._mk('&' + af.text, af.ty, 'ptr'))
                        self.flags = (af, Expr('0', None, 'int'))
                        return
                fr = _fold_bin(a_txt, ap or _ATOM_PREC, op, btxt,
                               bp or _ATOM_PREC)
                if fr is not None:
                    ftxt, fprec = fr
                    e = self._mk(ftxt, rty,
                                 rkind if rkind != '?' else 'int')
                    e._prec = fprec
                else:
                    e = self._mk(_bin_txt(a_txt, ap or _ATOM_PREC, op, btxt,
                                          bp or _ATOM_PREC), rty, rkind)
                    e._prec = _BIN_PREC[op]
                self.set_reg(dst, e)
            # GPR arithmetic also writes ZF/SF/OF/CF in real x64; without
            # this a jcc after `sub rsi,1` (loop counter) reads the STALE
            # flags of some earlier test/cmp and the loop condition renders
            # against the wrong variable (BitVector32.ToString). IMUL
            # leaves ZF/SF undefined, so it stays out.
            if mn != Mnemonic.IMUL:
                self.flags = (e, Expr('0', None, 'int'))
            return
        if mn in (Mnemonic.INC, Mnemonic.DEC):
            dst = reg_name(ins.op0_register)
            a = self.reg(dst)
            self._hint_tok(a, _INT_TY)
            e = self._mk(_bin_txt(a.text if a else '?', (a._prec if a else None) or _ATOM_PREC,
                                  '+' if mn == Mnemonic.INC else '-', '1', _ATOM_PREC),
                         self._arty(a), a.kind if a else '?')
            e._prec = _BIN_PREC['+'] if mn == Mnemonic.INC else _BIN_PREC['-']
            self.set_reg(dst, e)
            # inc/dec write ZF/SF/OF (not CF): keep the result for jcc
            self.flags = (e, Expr('0', None, 'int'))
            return
        if mn in (Mnemonic.NEG, Mnemonic.NOT):
            dst = reg_name(ins.op0_register)
            a = self.reg(dst)
            self._hint_tok(a, _INT_TY)
            # 132e: NOT is the bitwise complement, not negation
            op = '-' if mn == Mnemonic.NEG else '~'
            self.set_reg(dst, self._mk(_unary_txt(op, a.text if a else '?', a._prec if a else None),
                                       self._arty(a), a.kind if a else '?'))
            # NEG writes SF/ZF/CF and nothing here models it; fix 60b's
            # generic `_flags_mn` guard in _insn handles that without
            # disturbing the pair itself (which ordinary je/jne
            # consumers still read).
            return
        if mn in (Mnemonic.MAXSS, Mnemonic.MINSS, Mnemonic.MAXSD, Mnemonic.MINSD):
            # MAXSS/MINSS were absent from every handler, so the destination
            # kept a stale live value (usually a fabricated `0f`). Hardware
            # semantics: return the SECOND operand on equal or unordered
            # (NaN), which is exactly this conditional -- not Math.Max,
            # which propagates NaN differently.
            dst = reg_name(ins.op0_register)
            a = self.reg(dst)
            if A(1) == OpKind.REGISTER:
                be = self.reg(reg_name(ins.op1_register))
            else:
                be = self._read_mem(ins, asm)
            fty = _R4_TY if mn in (Mnemonic.MAXSS, Mnemonic.MINSS) else _R8_TY
            self._hint_tok(a, fty)
            self._hint_tok(be, fty)
            av = self._fp_operand(a)
            bv = self._fp_operand(be)
            if len(av.text) + len(bv.text) > 40:
                # a nested max/min doubles both operand texts at every
                # level; bind long operand expressions to real temps once
                # (never the fabricated = 0 overflow placeholder that
                # _mk emits past its cap).
                for _e in (av, bv):
                    if len(_e.text) > 12 and not _e._unk:
                        self._bind(_e)
            cmp_op = '>' if mn in (Mnemonic.MAXSS, Mnemonic.MAXSD) else '<'
            e = self._mk('(%s %s %s ? %s : %s)' % (
                av.text, cmp_op, bv.text, av.text, bv.text),
                av.ty if (av is not None and isinstance(av.ty, tuple)) else fty,
                'float')
            self.set_reg(dst, e)
            return
        if mn in (Mnemonic.ADDSS, Mnemonic.ADDSD, Mnemonic.SUBSS, Mnemonic.SUBSD,
                  Mnemonic.MULSS, Mnemonic.MULSD, Mnemonic.DIVSS, Mnemonic.DIVSD):
            dst = reg_name(ins.op0_register)
            a = self.reg(dst)
            if A(1) == OpKind.REGISTER:
                be = self.reg(reg_name(ins.op1_register))
            else:
                e = self._read_mem(ins, asm)
                be = e
            op = {Mnemonic.ADDSS: '+', Mnemonic.ADDSD: '+', Mnemonic.SUBSS: '-', Mnemonic.SUBSD: '-',
                  Mnemonic.MULSS: '*', Mnemonic.MULSD: '*', Mnemonic.DIVSS: '/', Mnemonic.DIVSD: '/'}[mn]
            sfx = 'f' if mn in (Mnemonic.ADDSS, Mnemonic.SUBSS, Mnemonic.MULSS, Mnemonic.DIVSS) else 'd'
            # SSE arithmetic is float by construction; SS operates on R4 and
            # SD on R8
            fty = _R4_TY if sfx == 'f' else _R8_TY
            aparts = getattr(a, '_parts', None)
            a_lane = getattr(a, '_slice', None) is not None
            b_lane = getattr(be, '_slice', None) is not None
            if (not aparts and not a_lane and not b_lane) or (
                    aparts and not all(self.il._type_enum(v.ty) == 0x0c
                                       for _, v, _, _ in aparts)):
                self._hint_tok(a, fty)
                self._hint_tok(be, fty)
                b_txt = self._fp_operand(be).text
                if op == '+' and _int_lit(b_txt) is not None and _int_lit(b_txt) < 0:
                    op, b_txt = '-', str(-_int_lit(b_txt))
                fe = self._mk(_bin_txt(self._fp_operand(a).text,
                                       (a._prec if a else None) or _ATOM_PREC,
                                       op, b_txt,
                                       (be._prec if be else None) or _ATOM_PREC),
                              a.ty if (a is not None and isinstance(a.ty, tuple)) else fty,
                              'float')
                fe._prec = _BIN_PREC.get(op)
                self.set_reg(dst, fe)
                return
            width = 4 if sfx == 'f' else 8
            # Scalar SSE arithmetic changes only the low lane.  Keep the
            # untouched high lanes as provenance for a later shuffle/unpack
            # instead of replacing the whole symbolic XMM register.
            a0 = self._piece_value(a, 0, width, fty) if a is not None else None
            b0 = self._piece_value(be, 0, width, fty) if be is not None else None
            a0 = a0 or a
            b0 = b0 or be
            self._hint_tok(a0, fty)
            self._hint_tok(b0, fty)
            b_txt = self._fp_operand(b0).text
            if op == '+' and _int_lit(b_txt) is not None and _int_lit(b_txt) < 0:
                op, b_txt = '-', str(-_int_lit(b_txt))
            low = self._mk(_bin_txt(self._fp_operand(a0).text,
                                    (a0._prec if a0 else None) or _ATOM_PREC,
                                    op, b_txt,
                                    (b0._prec if b0 else None) or _ATOM_PREC),
                           a0.ty if (a0 is not None and isinstance(a0.ty, tuple)) else fty,
                           'float')
            low._prec = _BIN_PREC.get(op)
            fe = self._copy_expr(low)
            parts = [(0, low, 0, width)]
            for off in range(width, 16, width):
                high = self._piece_value(a, off, width, fty) if a is not None else None
                if high is not None:
                    parts.append((off, high, 0, width))
            if len(parts) > 1:
                fe._parts = parts
            self.set_reg(dst, fe)
            return
        if mn == Mnemonic.UNPCKLPS:
            dst = reg_name(ins.op0_register)
            left = self.reg(dst)
            right = (self.reg(reg_name(ins.op1_register)) if A(1) == OpKind.REGISTER
                     else self._read_mem(ins, asm))
            packed = Expr('?', None, 'bits')
            parts = []
            for lo, origin, offset in ((0, left, 0), (4, right, 0),
                                       (8, left, 4), (12, right, 4)):
                if origin is not None:
                    value = self._piece_value(origin, offset, 4, _R4_TY)
                    if value is not None:
                        parts.append((lo, value, 0, 4))
            packed._parts = parts
            self.set_reg(dst, packed)
            return
        if mn == Mnemonic.SHUFPS and A(2) in (OpKind.IMMEDIATE8, OpKind.IMMEDIATE8TO32):
            # dst[i] = dst[sel] for i<2, src[sel] for i>=2, sel=(imm>>(2i))&3.
            # The reverted fault decoded one origin/selector for all lanes
            # (every channel from .a); the per-lane map below pins identity
            # 0xE4, broadcast 0x00 and 0x1B in tests. Any unproven lane
            # keeps today's spelling (fall through) -- never partial-model,
            # never pop: invalidation stays open (mi80548 gate).
            dst = reg_name(ins.op0_register)
            left = self.reg(dst)
            right = (self.reg(reg_name(ins.op1_register)) if A(1) == OpKind.REGISTER
                     else self._read_mem(ins, asm))
            try:
                imm8 = imm_of(ins, 2) & 0xFF
            except Exception:
                imm8 = None
            parts = []
            ok = left is not None and right is not None and imm8 is not None
            if ok:
                for i in range(4):
                    sel = (imm8 >> (2 * i)) & 3
                    origin = left if i < 2 else right
                    value = self._lane_value(origin, sel * 4, _R4_TY)
                    if value is None:
                        ok = False
                        break
                    parts.append((i * 4, value, 0, 4))
            if ok:
                packed = Expr('?', None, 'bits')
                packed._parts = parts
                self.set_reg(dst, packed)
                return
        if mn == Mnemonic.PSHUFD and A(2) in (OpKind.IMMEDIATE8, OpKind.IMMEDIATE8TO32):
            # All four lanes from src under the same imm8 map.
            dst = reg_name(ins.op0_register)
            right = (self.reg(reg_name(ins.op1_register)) if A(1) == OpKind.REGISTER
                     else self._read_mem(ins, asm))
            try:
                imm8 = imm_of(ins, 2) & 0xFF
            except Exception:
                imm8 = None
            parts = []
            ok = right is not None and imm8 is not None
            if ok:
                for i in range(4):
                    sel = (imm8 >> (2 * i)) & 3
                    value = self._lane_value(right, sel * 4, _R4_TY)
                    if value is None:
                        ok = False
                        break
                    parts.append((i * 4, value, 0, 4))
            if ok:
                packed = Expr('?', None, 'bits')
                packed._parts = parts
                self.set_reg(dst, packed)
                return
        if mn == Mnemonic.UNPCKHPS:
            # Interleave UPPER halves: dst = [d2, s2, d3, s3].
            dst = reg_name(ins.op0_register)
            left = self.reg(dst)
            right = (self.reg(reg_name(ins.op1_register)) if A(1) == OpKind.REGISTER
                     else self._read_mem(ins, asm))
            parts = []
            ok = left is not None and right is not None
            if ok:
                for lo, origin, offset in ((0, left, 8), (4, right, 8),
                                          (8, left, 12), (12, right, 12)):
                    value = self._lane_value(origin, offset, _R4_TY)
                    if value is None:
                        ok = False
                        break
                    parts.append((lo, value, 0, 4))
            if ok:
                packed = Expr('?', None, 'bits')
                packed._parts = parts
                self.set_reg(dst, packed)
                return
        if mn == Mnemonic.CVTDQ2PS:
            # Integer-lane to float-lane conversion. Model lanes only when
            # each 4B source lane slices to an int-typed value; render
            # (float)(lane) per lane, never a whole-register cast. Any
            # unproven lane keeps today's spelling instead of fabricating.
            dst = reg_name(ins.op0_register)
            right = (self.reg(reg_name(ins.op1_register)) if A(1) == OpKind.REGISTER
                     else self._read_mem(ins, asm))
            parts = []
            ok = right is not None
            if ok:
                for lo in (0, 4, 8, 12):
                    lane = self._lane_value(right, lo, _INT_TY)
                    if lane is None:
                        ok = False
                        break
                    fe = Expr('(float)(' + lane.text + ')', _R4_TY, 'float')
                    parts.append((lo, fe, 0, 4))
            if ok:
                packed = Expr('?', None, 'bits')
                packed._parts = parts
                self.set_reg(dst, packed)
                return
        if mn in (Mnemonic.XORPS, Mnemonic.XORPD, Mnemonic.ANDPS, Mnemonic.ANDNPS,
                  Mnemonic.ORPS, Mnemonic.PXOR):
            dst = reg_name(ins.op0_register)
            a = self.reg(dst)
            if A(1) == OpKind.REGISTER:
                be = self.reg(reg_name(ins.op1_register))
            else:
                be = self._read_mem(ins, asm)
            op = {Mnemonic.XORPS: '^', Mnemonic.XORPD: '^', Mnemonic.PXOR: '^',
                  Mnemonic.ANDPS: '&', Mnemonic.ANDNPS: '&', Mnemonic.ORPS: '|'}[mn]
            # the packed logicals are float-class even though they operate
            # on raw bits; self-xor is the compiler's float zero
            if mn in (Mnemonic.XORPS, Mnemonic.XORPD, Mnemonic.PXOR) \
                    and A(1) == OpKind.REGISTER \
                    and ins.op0_register == ins.op1_register \
                    and (a is None or be is None or a.text == be.text
                         or (a.text == '0f' and be.text == '0f')):
                e = Expr('0f', a.ty if a else None, 'float')
                self.set_reg(dst, e)
                self.flags = (e, Expr('0', None, 'int'))
                return
            # xor of two materialized float zeros folds (ctor zeroing
            # sprays `xor xmm0,xmm0` after both sides were already
            # loaded as 0f by earlier moves)
            if mn in (Mnemonic.XORPS, Mnemonic.XORPD, Mnemonic.PXOR) \
                    and a is not None and be is not None \
                    and a.text == '0f' and be.text == '0f':
                e = Expr('0f', a.ty, 'float')
                self.set_reg(dst, e)
                self.flags = (e, Expr('0', None, 'int'))
                return
            self._hint_tok(a, _R4_TY)
            self._hint_tok(be, _R4_TY)
            b_txt = self._fp_operand(be).text
            fe = self._mk(_bin_txt(self._fp_operand(a).text, (a._prec if a else None) or _ATOM_PREC,
                                   op, b_txt, (be._prec if be else None) or _ATOM_PREC),
                          a.ty if (a is not None and isinstance(a.ty, tuple)) else _R4_TY, 'float')
            fe._prec = _BIN_PREC.get(op)
            self.set_reg(dst, fe)
            return
        # Packed opcodes used as scalar low-lane operations in the
        # compiler's proved sqrt/helper diamond.  Decompiler records only the
        # exact native IPs whose alternate arm calls the structurally
        # recognized scalar helper; that alternate cannot produce an
        # observable high lane, which proves the packed high lane is dead.
        sqrt_sites = getattr(self, '_sqrt_low_sites', {})
        if (mn in (Mnemonic.CVTPS2PD, Mnemonic.CVTDQ2PD)
                and ip in sqrt_sites.get('convert', ())):
            dst = reg_name(ins.op0_register)
            if A(1) == OpKind.REGISTER:
                value = self.reg(reg_name(ins.op1_register))
            else:
                value = self._read_mem(ins, asm)
            sty = _R4_TY if mn == Mnemonic.CVTPS2PD else _INT_TY
            self._hint_tok(value, sty)
            self.set_reg(dst, self._mk('(double)(%s)' % (
                value.text if value else '?'), _R8_TY, 'float'))
            return
        if mn == Mnemonic.SQRTPD and ip in sqrt_sites.get('root', ()):
            dst = reg_name(ins.op0_register)
            if A(1) == OpKind.REGISTER:
                value = self.reg(reg_name(ins.op1_register))
            else:
                value = self._read_mem(ins, asm)
            self._hint_tok(value, _R8_TY)
            result = self._mk('Math.Sqrt(%s)' % (
                value.text if value else '?'), _R8_TY, 'float')
            result._no_bind = True
            self.set_reg(dst, result)
            return
        if mn == Mnemonic.CVTPD2PS and ip in sqrt_sites.get('narrow', ()):
            dst = reg_name(ins.op0_register)
            if A(1) == OpKind.REGISTER:
                value = self.reg(reg_name(ins.op1_register))
            else:
                value = self._read_mem(ins, asm)
            self._hint_tok(value, _R8_TY)
            result = self._mk('(float)(%s)' % (
                value.text if value else '?'), _R4_TY, 'float')
            self.set_reg(dst, result)
            return
        if mn in (Mnemonic.SQRTSS, Mnemonic.SQRTSD):
            dst = reg_name(ins.op0_register)
            if A(1) == OpKind.REGISTER:
                a = self.reg(reg_name(ins.op1_register))
            else:
                a = self._read_mem(ins, asm)
            fty = _R4_TY if mn == Mnemonic.SQRTSS else _R8_TY
            self._hint_tok(a, fty)
            # Math.Sqrt returns Double; SQRTSS produces a Single. Keep
            # that narrowing explicit so the recovered expression compiles
            # in a float return/assignment on Unity profiles without MathF.
            text = 'Math.Sqrt(%s)' % (a.text if a else '?')
            if mn == Mnemonic.SQRTSS:
                text = '(float)' + text
            fe = self._mk(text, fty, 'float')
            self.set_reg(dst, fe)
            return
        if mn in (Mnemonic.CVTSS2SD, Mnemonic.CVTSD2SS, Mnemonic.CVTSI2SS, Mnemonic.CVTSI2SD,
                  Mnemonic.CVTTSS2SI, Mnemonic.CVTTSD2SI):
            dst = reg_name(ins.op0_register)
            if A(1) == OpKind.REGISTER:
                a = self.reg(reg_name(ins.op1_register))
            else:
                a = self._read_mem(ins, asm)
            if mn == Mnemonic.CVTSS2SD:
                t, txt, sty, dty = 'float', '(double)(%s)', _R4_TY, _R8_TY
            elif mn == Mnemonic.CVTSD2SS:
                t, txt, sty, dty = 'float', '(float)(%s)', _R8_TY, _R4_TY
            elif mn in (Mnemonic.CVTSI2SS,):
                t, txt, sty, dty = 'float', '(float)(%s)', _INT_TY, _R4_TY
            elif mn in (Mnemonic.CVTSI2SD,):
                t, txt, sty, dty = 'float', '(double)(%s)', _INT_TY, _R8_TY
            else:
                t, txt, sty, dty = 'int', '(int)(%s)', \
                    (_R4_TY if mn == Mnemonic.CVTTSS2SI else _R8_TY), _INT_TY
            self._hint_tok(a, sty)
            self.set_reg(dst, self._mk(txt % (a.text if a else '?'), dty, t))
            return
        if mn == Mnemonic.PXOR:
            dst = reg_name(ins.op0_register)
            if A(1) == OpKind.REGISTER and ins.op0_register == ins.op1_register:
                self.set_reg(dst, Expr('0', None, 'float'))
                return
            return
        if mn == Mnemonic.XOR:
            dst = reg_name(ins.op0_register)
            if A(1) == OpKind.REGISTER and reg_name(ins.op0_register) == reg_name(ins.op1_register):
                self.set_reg(dst, Expr('0', None, 'int'))
                return
            a = self.reg(dst)
            be = self.reg(reg_name(ins.op1_register))
            self.set_reg(dst, self._mk('(%s ^ %s)' % (a.text if a else '?', be.text if be else '?')))
            return
        if mn in (Mnemonic.CDQ, Mnemonic.CQO, Mnemonic.CQO if False else Mnemonic.CDQE):
            return
        if mn in (Mnemonic.DIV, Mnemonic.IDIV, Mnemonic.MUL):
            return  # rare in managed code; ignore

        # --- float compares ---------------------------------------------
        if mn in (Mnemonic.COMISS, Mnemonic.UCOMISS, Mnemonic.COMISD, Mnemonic.UCOMISD):
            # flag-operand reads render nothing: the jcc/setcc/cmov
            # consumer counts the comparison text's single rendering,
            # so these reads must not also count (batch 37)
            self._copying = True
            a = self.reg(reg_name(ins.op0_register)) if A(0) == OpKind.REGISTER else None
            if A(1) == OpKind.REGISTER:
                be = self.reg(reg_name(ins.op1_register))
            else:
                be = self._read_mem(ins, asm)
            self._copying = False
            # SSE compares are float compares; SS pairs with R4, SD with R8
            fty = _R4_TY if mn in (Mnemonic.COMISS, Mnemonic.UCOMISS) else _R8_TY
            self._hint_tok(a, fty)
            self._hint_tok(be, fty)
            self.flags = (a, be)
            return

        # --- cmp/test/flags ---------------------------------------------
        if mn in (Mnemonic.CMP, Mnemonic.TEST):
            # same counting rule as COMISS above: the consumer counts
            # the render, the setter's operand reads do not (batch 37)
            self._copying = True
            if A(0) == OpKind.MEMORY:
                a = self._read_mem(ins, asm)
                self._copying = False
                if A(1) in IMM_OPS:
                    v = imm_of(ins, 1)
                    # a GPR compare against a non-zero literal is an integer
                    # compare; zero may be a null test, so it types nothing
                    if v != 0:
                        self._hint_tok(a, _INT_TY)
                    self.flags = (a, Expr(str(v), None, 'int'))
                else:
                    be = self.reg(reg_name(ins.op1_register))
                    self.flags = (a, be)
                return
            a = self.reg(reg_name(ins.op0_register)) if A(0) == OpKind.REGISTER else None
            if A(1) in IMM_OPS:
                v = imm_of(ins, 1)
                if v != 0:
                    self._hint_tok(a, _INT_TY)
                be = Expr(str(v), None, 'int')
            elif A(1) == OpKind.REGISTER:
                be = self.reg(reg_name(ins.op1_register))
            elif A(1) == OpKind.MEMORY:
                be = self._read_mem(ins, asm)
            else:
                be = None
            self._copying = False
            if mn == Mnemonic.TEST:
                if be is not None and a is not None and be.text == a.text:
                    self.flags = (a, Expr('0' if self._test_is_value(a) else 'null', None, 'int'))
                else:
                    self.flags = (a, Expr('null' if (be and be.text == '0') else (be.text if be else '0'), None, 'int'))
            else:
                self.flags = (a, be or Expr('0', None, 'int'))
            return
        if mn in (Mnemonic.SETA, Mnemonic.SETAE, Mnemonic.SETB, Mnemonic.SETBE, Mnemonic.SETG,
                  Mnemonic.SETGE, Mnemonic.SETL, Mnemonic.SETLE, Mnemonic.SETE, Mnemonic.SETNE):
            dst = reg_name(ins.op0_register)
            op = {Mnemonic.SETA: '>', Mnemonic.SETAE: '>=', Mnemonic.SETB: '<', Mnemonic.SETBE: '<=',
                  Mnemonic.SETG: '>', Mnemonic.SETGE: '>=', Mnemonic.SETL: '<', Mnemonic.SETLE: '<=',
                  Mnemonic.SETE: '==', Mnemonic.SETNE: '!='}[mn]
            lhs, rhs = (self.flags or (Expr('?', None, '?'), Expr('?', None, '?')))
            self._note_use(lhs)
            self._note_use(rhs)
            # setcc materialises a C# bool
            self.set_reg(dst, self._mk('(%s %s %s ? 1 : 0)' % (
                lhs.text if lhs else '?', op, rhs.text if rhs else '?'), _BOOL_TY, 'int'))
            self.flags = None
            return
        if mn in (Mnemonic.CMOVA, Mnemonic.CMOVAE, Mnemonic.CMOVB, Mnemonic.CMOVBE,
                  Mnemonic.CMOVE, Mnemonic.CMOVNE, Mnemonic.CMOVG, Mnemonic.CMOVGE,
                  Mnemonic.CMOVL, Mnemonic.CMOVLE, Mnemonic.CMOVS, Mnemonic.CMOVNS,
                  Mnemonic.CMOVO, Mnemonic.CMOVNO, Mnemonic.CMOVP, Mnemonic.CMOVNP):
            # SHIPPED (batch 29, see todo.md 0l): `dst = cond ? src : dst` --
#            a reconstruction of batch 27's ternary modeling, with the
#            condition ALWAYS parenthesized (batch 29's own failed build
#            emitted the bare `unknown >= unknown ? a : b` spelling, whose
#            select-mark `?` a downstream unknowns pass then ate -- the one
#            bad row that blocked it; the parenthesized form gates clean),
#            the six flag-specific variants rendering `unknown`, and _mk's
#            cap as the growth guard.
            dst = reg_name(ins.op0_register)
            old = self.regs.get(dst)
            op = self.CMOV_OPS.get(mn)
            if op is None:
                # flag-specific variants (S/NS/O/NO/P/NP) have no mapped
                # comparison operator. fix 60 derives the ones that ARE
                # decidable from the flag SETTER (CMOVS/CMOVNS after a
                # test or arithmetic is a sign test); anything else stays
                # the syntax-safe placeholder, never a bare '?'
                _lhs0, _rhs0 = (self.flags
                                or (Expr('?', None, '?'), Expr('?', None, '?')))
                cond = flag_cond(
                    getattr(self, '_flags_mn', None), _CMOV_AS_J.get(mn),
                    strip_outer(_lhs0.text) if _lhs0 else '?',
                    strip_outer(_rhs0.text) if _rhs0 else '?')
                cond = '(%s)' % cond if cond else 'unknown'
            else:
                lhs, rhs = (self.flags or (Expr('?', None, '?'), Expr('?', None, '?')))
                self._note_use(lhs)
                self._note_use(rhs)
                cond = '(%s %s %s)' % (lhs.text if lhs else '?', op,
                                       rhs.text if rhs else '?')
            if A(1) == OpKind.REGISTER:
                src = self.reg(reg_name(ins.op1_register))
            elif A(1) == OpKind.MEMORY:
                src = self._read_mem(ins, asm)
            else:
                src = None
            ty = src.ty if (src is not None and src.ty is not None) else (old.ty if old is not None else None)
            kind = src.kind if src is not None else (old.kind if old is not None else '?')
            if mn == Mnemonic.CMOVE:
                # exact-klass selection proves the selected value's
                # runtime type: `dst = (recv.getClass() == typeof(T))
                # ? recv : dst` selects recv only when its klass IS T
                # exactly (pointer equality, not `is`). The compared
                # typeof usage already carries the typedef, so the
                # merge stamps it (GetChars mi 5769: the decoder proves
                # Decoder, resolving bits/bitCount/firstByte). Only
                # plain class rows qualify; anything else keeps the
                # src/old fallback above.
                _fl, _fr = (self.flags or (None, None))
                _rv = getattr(_fl, 'recv', None)
                if (_fl is not None and _fr is not None
                        and getattr(_fl, 'kind', None) == 'klass'
                        and (_fl.text or '').endswith('.getClass()')
                        and _rv is not None and src is not None
                        and src.text == _rv.text):
                    _rty = getattr(_fr, 'ty', None)
                    if (isinstance(_rty, tuple) and len(_rty) == 2
                            and ((_rty[1] >> 16) & 0xFF) in (0x11, 0x12)
                            and 0 <= _rty[0] < len(self.meta.typedefs)
                            and not self.meta.typedefs[_rty[0]].is_valuetype):
                        ty = (_rty[0], 0x12 << 16)
                        kind = 'obj'
            self.set_reg(dst, self._mk('(%s ? %s : %s)' % (
                cond, src.text if src is not None else '?',
                old.text if old is not None else '?'), ty, kind))
            self.flags = None
            return
        if mn == Mnemonic.XCHG:
            return

        # --- memory writes ------------------------------------------------
        if mn in (Mnemonic.MOV,) and A(0) == OpKind.MEMORY:
            self._write_mem(ins, asm)
            return
        if mn in (Mnemonic.MOVSS, Mnemonic.MOVSD, Mnemonic.MOVUPS, Mnemonic.MOVAPS) and A(0) == OpKind.MEMORY:
            self._write_mem(ins, asm)
            return

        # ignore the rest silently (leave asm comment if enabled)
        if asm:
            self.emit(ip, '', asm)

    # ------------------------------------------------------------------
    def _indexed_lea(self, ins, base) -> Expr:
        """`lea r,[b+i*s+d]`: compose the real text; '?addr' only when the
        base register is genuinely untracked. base==index is the compiler's
        multiply idiom (`lea rcx,[rax+rax*2]` == rax*3, integer by
        construction); a distinct base+index is address math (array-element
        addressing) or plain integer addition. An arr base resolves to the
        element (or element member) whose address the LEA computes."""
        if base is None:
            if ins.memory_base != IReg.NONE:
                return Expr('?addr', None, 'ptr')
            base = Expr('0', None, 'int')   # [idx*s+d] with no base register
        idx = self.reg(reg_name(ins.memory_index))
        itxt = idx.text if idx is not None else '?'
        ip = (idx._prec if idx is not None else None) or _ATOM_PREC
        scale = ins.memory_index_scale or 1
        disp = sdisp(ins.memory_displacement)
        if idx is not None and reg_name(ins.memory_base) == reg_name(ins.memory_index):
            # x*(1+scale): the same text `imul r, x, 1+scale` would give
            if base.kind != 'ptr':
                self._hint_tok(idx, _INT_TY)
            rty = None if base.kind == 'ptr' else _INT_TY
            fr = _fold_bin(itxt, ip, '*', str(1 + scale), _ATOM_PREC)
            if fr is not None:
                txt, prec = fr
            else:
                txt = _bin_txt(itxt, ip, '*', str(1 + scale), _ATOM_PREC)
                prec = _BIN_PREC['*']
            e = self._mk(txt, rty, 'int')
            e._prec = prec
            return e
        if base.kind == 'arr':
            be0, d0 = self._arr_unbias(base, disp)
            fe = self._arr_elem_expr(be0, idx, scale, d0, None)
            if fe is not None:
                return self._mk('&' + fe.text, fe.ty, 'ptr')
        bp = base._prec or _ATOM_PREC
        if scale == 1:
            mtxt, mp = itxt, ip
        else:
            fr = _fold_bin(itxt, ip, '*', str(scale), _ATOM_PREC)
            if fr is not None:
                mtxt, mp = fr
            else:
                mtxt = _bin_txt(itxt, ip, '*', str(scale), _ATOM_PREC)
                mp = _BIN_PREC['*']
        fr = _fold_bin(base.text, bp, '+', mtxt, mp)
        if fr is not None:
            txt, prec = fr
        else:
            txt = _bin_txt(base.text, bp, '+', mtxt, mp)
            prec = _BIN_PREC['+']
        if disp:
            txt = '%s %s' % (txt, disp_add(disp))
            prec = _BIN_PREC['+']
        ptrish = base.kind not in ('int', 'float', '?')
        if not ptrish and idx is not None:
            self._hint_tok(idx, _INT_TY)
        e = self._mk(txt, base.ty if base.kind == 'arr' else (None if ptrish else _INT_TY),
                     'ptr' if ptrish else 'int')
        e._prec = prec
        return e

    def _arr_unbias(self, be, disp):
        """MSVC often `add r, 0x20` an array base before indexing it; the
        header bias then sits in the register TEXT (`arr + 32`) and blinds
        _arr_elem_expr's D-0x20 element fold (k goes negative). Lift a
        trailing positive constant back into the displacement when the
        head is a plain token; anything else passes through unchanged."""
        if be is not None and be.kind == 'arr':
            m = _ARR_BIAS_RX.match(be.text)
            if m is not None:
                v = _int_lit(m.group(2))
                if v is not None and v > 0:
                    return Expr(m.group(1), be.ty, 'arr'), disp + v
        return be, disp

    def _arr_add_fold(self, a_txt, btxt, ty):
        """`lea r,[arr+i*S]; add r, 0x20` composes `arr + i*S + 0x20`: the
        array header bias lands AFTER the index term (Shape B). Fold it to
        the element address `&arr[i]` (generalised: any positive bias whose
        (bias-0x20) is a multiple of S folds into the index). Requires the
        head to be a plain token and the type to be array-typed."""
        try:
            vb = int(btxt, 0)
        except (ValueError, TypeError):
            return None
        m = re.match(r'^([\w.\[\]]+) \+ (.+?) \* (\d+)$', a_txt)
        if m is None or self._ty_kind(ty) != 'arr':
            return None
        head, itxt, s_txt = m.group(1), m.group(2), m.group(3)
        try:
            S = int(s_txt, 0)
        except (ValueError, TypeError):
            return None
        k = vb - 0x20
        if S <= 0 or not (0 <= k < 0x100000) or k % S != 0:
            return None
        if k:
            itxt = '(%s + %d)' % (itxt, k // S)
        return Expr('%s[%s]' % (head, itxt), self._elem_type(ty), self._ty_kind(self._elem_type(ty)))

    def _arr_elem_expr(self, be, ie, scale, disp, size) -> Optional[Expr]:
        """[arr + i*S + D] as an element access. Multidim indexing multiplies
        the row stride into the index first, so D-0x20 lands on an element
        boundary and folds back into the index (the same bias fold jump
        tables use); a partial offset resolves to a member of a valuetype
        element (chain offsets carry the 0x10 header). size=None means the
        caller wants the element's *address* (LEA), not its value."""
        if ie is None or scale <= 0:
            return None
        itxt = ie.text
        ip = ie._prec or _ATOM_PREC
        k = sdisp(disp) - 0x20
        if not (0 <= k < 0x100000):
            return None
        if k == 0:
            ety = self._elem_type(be.ty)
            return Expr('%s[%s]' % (be.text, itxt), ety, self._ty_kind(ety))
        td_idx = self._td_of(be.ty)
        if td_idx is not None and self.meta.typedefs[td_idx].is_valuetype \
                and (size is None or size < scale):
            chain = self.il.instance_field_chain(td_idx)
            ent = chain.get(k + 0x10) if chain else None
            if ent is not None:
                fty = self.il.types[ent[1]] if 0 <= ent[1] < len(self.il.types) else None
                return Expr('%s[%s].%s' % (be.text, itxt, ent[0]), fty, 'obj')
        if k % scale == 0:
            bias = k // scale
            fr = _fold_bin(itxt, ip, '+', str(bias), _ATOM_PREC)
            if fr is not None:
                txt = fr[0]
            else:
                txt = _bin_txt(itxt, ip, '+', str(bias), _ATOM_PREC)
            ety = self._elem_type(be.ty)
            return Expr('%s[%s]' % (be.text, txt), ety, self._ty_kind(ety))
        return None

    def _rip_str(self, slot):
        """A string constant whose ADDRESS is taken (`lea reg,[rel wstr]` --
        native-api names, interface strings). Printable + NUL-terminated
        within 48 bytes; UTF-16LE first (IL2CPP wide strings), then ASCII."""
        o = self.bin.va2off(slot)
        if o is None:
            return None
        d = self.bin.d[o:o + 96]
        if len(d) >= 6 and d[1] == 0 and 0x20 <= d[0] <= 0x7e:
            chars = []
            for i in range(0, len(d) - 1, 2):
                lo, hi = d[i], d[i + 1]
                if lo == 0 and hi == 0:
                    break
                if hi != 0 or not (0x20 <= lo <= 0x7e):
                    chars = None
                    break
                chars.append(chr(lo))
            if chars and 3 <= len(chars) <= 48:
                return meta_lit_repr(''.join(chars))
        cs = self.bin.cstr(slot, 97)
        if cs and 3 <= len(cs) <= 96 and all(0x20 <= ord(ch) <= 0x7e for ch in cs):
            return meta_lit_repr(cs)
        return None

    # fix 134: (mnemonic, memory bytes) -> (C# type, element type) of a
    # load whose width the instruction proves; absent = keep raw
    _W134 = {
        ('MOVZX', 2): ('ushort', 0x07), ('MOVSX', 1): ('sbyte', 0x04),
        ('MOVSX', 2): ('short', 0x06), ('MOVSXD', 4): ('int', 0x08),
        ('MOV', 2): ('short', 0x06), ('MOV', 4): ('int', 0x08),
        ('CMP', 2): ('short', 0x06), ('CMP', 4): ('int', 0x08),
        ('TEST', 2): ('short', 0x06), ('TEST', 4): ('int', 0x08),
    }

    def _read_mem(self, ins, asm) -> Optional[Expr]:
        return self._read_mem_raw(ins, asm)

    def _width_mark(self, ins, e):
        """Fix 134: tag a whole raw deref `*(...)` with the width the
        instruction proves (`(__w_int)*(E + N)`, typed); else `e`."""
        if e is None or e.ty is not None or e.kind != 'ptr':
            return e
        t = e.text or ''
        if not t.startswith('*(') or not t.endswith(')'):
            return e
        depth = 0
        for k in range(1, len(t)):
            ch = t[k]
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0 and k != len(t) - 1:
                    return e            # `*(a) + b`: not one deref
        if '"' in t or "'" in t or '?' in t:
            return e
        name = _MN_NAME.get(ins.mnemonic)
        if name in ('MOV', 'MOVZX', 'MOVSX', 'MOVSXD'):
            if ins.op_kind(0) != OpKind.REGISTER or _reg_size(ins.op0_register) not in (2, 4, 8):
                return e
        elif name in ('CMP', 'TEST'):
            if not any(ins.op_kind(k) == OpKind.MEMORY for k in range(ins.op_count)):
                return e
        else:
            return e
        w = self._W134.get((name, MemorySizeExt.size(ins.memory_size) or 0))
        if w is None:
            return e
        return Expr('(__w_%s)%s' % (w[0], t), (0, w[1] << 16), 'int')

    def _read_mem_raw(self, ins, asm) -> Optional[Expr]:
        if hasattr(self.il, '_sf_field_size'):
            packed = self._aggregate_load(ins)
            if packed is not None:
                return packed
        if ins.memory_base == IReg.RIP:
            slot = ins.ip_rel_memory_address
            usg = self.il.decode_slot(slot)
            if usg:
                ty = usg.get('type')
                k = usg['kind']
                if k == 5:
                    return Expr(usg.get('text', '?'), None, 'str')
                if k in (1, 2):
                    e = Expr(usg.get('text', '?'), ty, 'klass')
                    if usg.get('td') is not None:
                        e._td = usg['td']
                    return e
                # fix 66: an icall thunk cell holds the NATIVE function
                # pointer for `Type::Method`, resolved once from the
                # signature string that fills it (scan_icall_cache).  A
                # call through it IS a call to that managed method, so
                # hand `_call` the identity: the `fptr` kind drops the
                # `/*indirect*/` marker and `_mi` puts the site on the
                # ordinary resolved-call path.  Gated on the signature
                # having actually resolved -- an unresolved one keeps the
                # honest `Type.Method() /*indirect*/(...)` render.
                if k == 3 and usg.get('icall') \
                        and usg.get('method') is not None:
                    e = Expr(usg.get('text', '?'), None, 'fptr')
                    e._mi = usg['method']
                    return e
                e = Expr(usg.get('text', '?'), ty, 'obj')
                if k == 6:
                    e._usg_idx = usg['idx']
                elif k == 3 and usg.get('method') is not None:
                    e.kind = 'methodinfo'
                    e._mi = usg['method']
                return e
            q = self.bin.qword(slot)
            if q is not None and self.bin.is_exec_va(q):
                return Expr('fnptr_%x' % q, None, 'fptr')
            if q is not None and self.bin.valid_va(q):
                cs = self.bin.cstr(q, 64)
                if cs and len(cs) > 2:
                    return Expr(meta_lit_repr(cs), None, 'str')
            # constant pool loads: render the raw constant. memory_size is
            # iced's MemorySize *enum* (UINT32=3, UINT64=5, FLOAT32=29,
            # FLOAT64=30, PACKED128_FLOAT32=74) -- byte counts never occur,
            # so the old `in (4, 8)` check matched nothing and every pool
            # constant rendered as data_NNN
            msz = ins.memory_size
            if msz in (3, 5, 29, 30, 74) \
                    and not (q and (q & 1) and (q >> 32) == 0):
                o = self.bin.va2off(slot)
                if o is not None:
                    if msz == 29:
                        fv = struct.unpack_from('<f', self.bin.d, o)[0]
                        scalar = Expr(repr_f32(fv), None, 'float')
                        # byte provenance for float-lane readers
                        # (67525): mirrors the PACKED128 _bytes
                        # attach below; integer consumers never
                        # call _piece_value, and expected=None
                        # still returns None there.
                        scalar._bytes = bytes(self.bin.d[o:o + 4])
                        return scalar
                    if msz == 74:
                        f1, f2 = struct.unpack_from('<2f', self.bin.d, o)
                        value = Expr('(float2)(%s, %s)' % (repr_f32(f1), repr_f32(f2)),
                                     None, 'float')
                        value._bytes = bytes(self.bin.d[o:o + 16])
                        return value
                    if msz == 3:
                        return Expr(str(struct.unpack_from('<I', self.bin.d, o)[0]),
                                    None, 'int')
                    if msz == 5 and (q == 0 or not self.bin.valid_va(q)):
                        return Expr('%#x' % q, None, 'int')
                    dv = struct.unpack_from('<d', self.bin.d, o)[0]
                    dscalar = Expr(repr_f64(dv), None, 'float')
                    dscalar._bytes = bytes(self.bin.d[o:o + 8])
                    return dscalar
            return Expr('data_%x' % slot, None, 'ptr')
        base = reg_name(ins.memory_base) if ins.memory_base != IReg.NONE else None
        idxr = reg_name(ins.memory_index) if ins.memory_index != IReg.NONE else None
        disp = ins.memory_displacement
        # iced reports a MemorySize enum here, not a byte count:
        # ask MemorySizeExt for the true width (an unknown/unmapped
        # size keeps the old 8-byte default).
        size = MemorySizeExt.size(ins.memory_size) or 8
        _cbe = self.reg(base) if base and base != 'RBP' else None
        _caddr = self._stack_address(ins) \
            if _cbe is not None and getattr(_cbe, '_stack_offset', None) is not None \
            and idxr is None else None
        if ((base == 'RSP' or (base == 'RBP' and self._rbp_is_frame()))
                and idxr is None) or _caddr is not None:
            # loads through an RSP-copy register key the slot by absolute
            # address so [copy+N] aliases [rsp+M] of the same home; the
            # RSP-path key is identical to today's.
            var = self.slot_var(disp) if _caddr is None else self.slot_var(_caddr - self.rsp_delta)
            # a recorded slot type restores the reload's kind the way
            # entry classification does (state._setup_entry): a stack
            # parameter reload keeps its declared type instead of
            # degrading to untyped 'local' (GetChars mi 5769: the
            # baseDecoder reload fed an untyped cmov merge). A spilled
            # array register still resolves `&arr[i]`; other kinds
            # follow the same entry mapping (float/arr/obj/int).
            sty = self.slot_types.get(var)
            if sty is not None:
                sbits = sty[1] if isinstance(sty, tuple) and len(sty) == 2 else 0
                ste = (sbits >> 16) & 0xFF
                if ste in (0x0c, 0x0d) and not ((sbits >> 29) & 1):
                    skind = 'float'
                elif ste in (0x1d, 0x14):
                    skind = 'arr'
                elif ste >= 0x10:
                    skind = 'obj'
                else:
                    skind = 'int'
                return Expr(var, sty, skind)
            return Expr(var, None, 'local')
        if base is None and idxr is not None:
            ie = self.reg(idxr)
            return Expr('*(%s %s)' % (ie.text if ie else '?', disp_add(disp)), None, 'ptr')
        be = self.reg(base) if base else None
        if be is not None and getattr(be, '_stack_offset', None) is not None and idxr is not None \
                and base != 'RBP':
            # index arithmetic on a frame copy: the honest unknown-base shape.
            _cie = self.reg(idxr)
            return Expr('*(%s %s)' % (_cie.text if _cie else '?', disp_add(disp)), None, 'ptr')
        if be is not None and idxr is not None:
            ie = self.reg(idxr)
            scale = ins.memory_index_scale
            if (scale or 1) == 1 and be.kind == 'int' and ie is not None \
                    and ie.kind == 'ptr' and self._is_byte_ptr_ty(ie.ty):
                # cursor-as-index: the encoder put the integer offset in
                # the base slot and the byte* cursor in the index slot
                # ([rdx+r15] stores at cursor+offset). Render
                # pointer-first: value-identical at scale 1 and the
                # only compilable order (ptr*int does not exist).
                be, ie = ie, be
            if be.kind == 'arr':
                be0, d0 = self._arr_unbias(be, disp)
                fe = self._arr_elem_expr(be0, ie, scale or 1, d0, size)
                if fe is not None:
                    return fe
            # scaled index in the BASE slot, array in the INDEX slot
            # (`imul r,idx,S; ... [r + arr + D]`): roles swap
            if be.kind == 'int' and ie is not None and ie.kind == 'arr':
                be0, d0 = self._arr_unbias(ie, disp)
                fe = self._arr_elem_expr(be0, be, 1, d0, size)
                if fe is not None:
                    return fe
            if be.kind == 'ptr' and be.text.startswith('&data_'):
                try:
                    tab = int(be.text[6:], 16)
                    self._last_tabread = (tab, ie, scale, disp)
                except ValueError:
                    pass
            return self._mk('*(%s + %s*%d %s)' % (
                _term_up(be.text), _term_up(ie.text, mul=True) if ie else '?',
                scale, disp_add(disp)), None, 'ptr')
        if be is None:
            return Expr('mem_%x' % disp, None, 'ptr')
        fe = self._field_expr(be, disp, size, elem_fold=True)
        # fix 134: field-form raw reads spell their native width; arrays
        # and strings keep the raw text later passes fold (`.Length`)
        if be.kind not in ('arr', 'str') and _W134_BASE_RX.match(be.text or '') and not (
                isinstance(be.ty, tuple) and len(be.ty) == 2
                and ((be.ty[1] >> 16) & 0xFF) in (0x0e, 0x14, 0x1d)):
            try:
                fe = self._width_mark(ins, fe)
            except Exception:
                pass
        return fe

    def _mem_lvalue(self, ins) -> Optional[str]:
        """Assignable text for a memory destination, or None when the write is
        runtime bookkeeping that should not appear in the body."""
        self._lv_ty = None
        # fix 102: native width + (base, disp) parts for a raw
        # `*(...)` lvalue, so _write_mem/_rmw_mem can render a
        # width-preserving cast. Bookkeeping keeps raw text.
        # fix 103: the indexed branch additionally records
        # (index text, scale); None for plain stores.
        self._lv_width = None
        self._lv_raw_parts = None
        self._lv_raw_idx = None
        if ins.memory_base == IReg.RIP:
            slot = ins.ip_rel_memory_address
            q = self.bin.qword(slot)
            usg = self.il.decode_slot(slot)
            if usg is not None and usg.get('kind') == 3:
                return None            # icall cache fill -- runtime bookkeeping
            if ins.memory_size == 1 and (q is None or q == 0):
                return None            # per-method initialized flag byte
            return 'data_%x' % slot
        base = reg_name(ins.memory_base) if ins.memory_base != IReg.NONE else None
        idxr = reg_name(ins.memory_index) if ins.memory_index != IReg.NONE else None
        disp = ins.memory_displacement
        # iced reports a MemorySize enum here, not a byte count:
        # ask MemorySizeExt for the true width (an unknown/unmapped
        # size keeps the old 8-byte default).
        size = MemorySizeExt.size(ins.memory_size) or 8
        _cbe = self.reg(base) if base and base != 'RBP' else None
        _caddr = self._stack_address(ins) \
            if _cbe is not None and getattr(_cbe, '_stack_offset', None) is not None \
            and idxr is None else None
        if ((base == 'RSP' or (base == 'RBP' and self._rbp_is_frame()))
                and idxr is None) or _caddr is not None:
            # stores through an RSP-copy register key the slot by absolute
            # address (same aliasing as the load path); RSP-key identical.
            return self.slot_var(disp) if _caddr is None else self.slot_var(_caddr - self.rsp_delta)
        be = self.reg(base) if base else None
        if be is None:
            return 'mem[%d]' % sdisp(disp)
        if be is not None and getattr(be, '_stack_offset', None) is not None and idxr is not None \
                and base != 'RBP':
            # indexed store through a frame copy: unknown-base shape.
            return 'mem[%d]' % sdisp(disp)
        if be.kind == 'klass':
            return None                # static/klass bookkeeping
        if idxr is not None:
            ie = self.reg(idxr)
            if (ins.memory_index_scale or 1) == 1 and be.kind == 'int' \
                    and ie is not None and ie.kind == 'ptr' \
                    and self._is_byte_ptr_ty(ie.ty):
                # same cursor-as-index swap as the load path.
                be, ie = ie, be
            if be.kind == 'int' and ie is not None and ie.kind == 'arr':
                # scaled index in the BASE slot, array in the INDEX
                # slot -- swap roles before the element fold
                be0, d0 = self._arr_unbias(ie, disp)
                fe = self._arr_elem_expr(be0, be, 1, d0, size)
                if fe is not None:
                    self._lv_ty = fe.ty
                    return fe.text
            if be.kind == 'arr':
                fe = self._arr_elem_expr(be, ie, ins.memory_index_scale or 1, disp, size)
                if fe is not None:
                    self._lv_ty = fe.ty
                    return fe.text
            itxt = ie.text if ie else '?'
            scale = ins.memory_index_scale or 1
            self._lv_width = MemorySizeExt.size(ins.memory_size)
            self._lv_raw_parts = (be.text, disp_add(disp))
            self._lv_raw_idx = (itxt, scale)
            return '*(%s + %s*%d %s)' % (_term_up(be.text), _term_up(itxt, mul=True), scale, disp_add(disp))
        fe = self._field_expr(be, disp, size)
        if fe.kind == 'klass' and fe.text.endswith('.getClass()'):
            return None            # object-header klass store -- bookkeeping
        if be.kind == 'arr' and disp >= 0x20:
            # `_field_expr` already decided: a stride-verified element
            # access (possibly with a primitive-kind element, which the
            # generic branch below would miss) or a raw deref. Never
            # re-derive the index from the ACCESS WIDTH here -- that
            # legacy formula is the F4 bug's second home and would
            # override the stride-correct result.
            self._lv_ty = fe.ty if fe.kind != 'ptr' else None
            if fe.kind == 'ptr':
                self._lv_width = MemorySizeExt.size(ins.memory_size)
                self._lv_raw_parts = (be.text, disp_add(disp))
            return fe.text
        if fe.kind in ('obj', 'arr', 'str') or ('.' in fe.text) \
                or ('->' in fe.text):
            self._lv_ty = fe.ty
            if fe.text == '*(%s %s)' % (be.text, disp_add(disp)):
                # fix 102c: _field_expr's raw passthrough over a
                # dotted base (`*(this.field + disp)` on a field
                # map miss); the raw branch below would record
                # these identical parts. Same text either way.
                self._lv_width = MemorySizeExt.size(ins.memory_size)
                self._lv_raw_parts = (be.text, disp_add(disp))
            return fe.text
        self._lv_width = MemorySizeExt.size(ins.memory_size)
        self._lv_raw_parts = (be.text, disp_add(disp))
        return '*(%s %s)' % (be.text, disp_add(disp))

    def _coalesced_bool_store(self, ins, asm):
        """Split a constant store only when every byte is a named Boolean.

        MSVC combines adjacent fields into word/dword/qword stores. The
        immediate 0x0101 means *two* true fields, not one unknown/257 value.
        Require exact, non-overlapping metadata coverage and canonical 0/1
        bytes; mixed fields, padding, unknown layouts and indexed writes
        deliberately keep a width-preserving raw store instead.
        """
        if ins.mnemonic != Mnemonic.MOV or ins.op1_kind not in IMM_OPS:
            return False
        width = MemorySizeExt.size(ins.memory_size)
        if width not in (2, 4, 8) or ins.memory_index != IReg.NONE:
            return False
        if ins.memory_base in (IReg.NONE, IReg.RIP, IReg.RSP, IReg.RBP):
            return False
        # Proof reads must not increment the use-binding register counter.
        be = dict.get(self.regs, reg_name(ins.memory_base))
        if be is None or be.kind not in ('obj', 'local'):
            return False
        ty = be.ty or self._type_hints.get(be.text) or self.slot_types.get(be.text)
        ti = self._td_of(ty)
        if ti is None:
            return False
        td = self.meta.typedefs[ti]
        if getattr(td, 'flags', 0) & 0x18 == 0x10:  # explicit/overlapping layout
            return False
        chain = self.il.instance_field_chain(ti)
        offset = sdisp(ins.memory_displacement) + (0x10 if td.is_valuetype else 0)
        value = imm_of(ins, 1) & ((1 << (width * 8)) - 1)
        fields = []
        for i in range(width):
            ent = chain.get(offset + i) if chain else None
            if ent is None or not 0 <= ent[1] < len(self.il.types):
                return False
            fty = self.il.types[ent[1]]
            byte = (value >> (8 * i)) & 0xFF
            if self.il._type_enum(fty) != 0x02 or (fty[1] >> 29) & 1 or byte not in (0, 1):
                return False
            fields.append((ent[0], 'true' if byte else 'false'))
        if len({name for name, _ in fields}) != width:
            return False
        # The base appears once per recovered field store. Bind any live
        # expression before rendering, so an allocation/call is not repeated.
        for _ in range(width - 1):
            self._note_use(be)
        stores = [('%s.%s' % (_recv_fold(be.text), name), value)
                  for name, value in fields]
        for lv, _ in stores:
            self._kill_stale(lv)
        for lv, value in stores:
            self.emit(ins.ip, '%s = %s;' % (lv, value), asm)
        return True

    _WIDE_SIGNED = {2: 'short', 4: 'int', 8: 'long'}
    _WIDE_UNSIGNED = {2: 'ushort', 4: 'uint', 8: 'ulong'}
    _WIDE_INT_RX = re.compile(r'^([+-]?)(?:(0[xX][0-9a-fA-F]+)|(\d+))([uUlL]*|[fFdD])?$')
    _WIDE_FLOAT_RX = re.compile(r'^[+-]?(?:\d+\.\d*|\.\d+|\d+[eE][+-]?\d+)(?:[eE][+-]?\d+)?[fFdD]?$')
    # il2cpp element type -> (signedness, size); only primitives with C#
    # implicit conversions. Natives, enums, references, strings, bools
    # and pointers decline.
    _WIDE_SRC_KIND = {
        0x03: ('u', 2),  # char
        0x04: ('s', 1), 0x05: ('u', 1),
        0x06: ('s', 2), 0x07: ('u', 2),
        0x08: ('s', 4), 0x09: ('u', 4),
        0x0a: ('s', 8), 0x0b: ('u', 8),
        0x0c: ('f', 4), 0x0d: ('f', 8),
    }
    _WIDE_EXACT = {
        0x08: ('int', 4), 0x09: ('uint', 4),
        0x0a: ('long', 8), 0x0b: ('ulong', 8),
        0x0c: ('float', 4), 0x0d: ('double', 8),
    }

    def _wide_int_cast(self, width, v):
        """Signed/unsigned `width` cast accepting integer `v`, else None.

        Signed first when the value fits (the default C# integral
        family); unsigned for the wrapped upper half. Out-of-width
        values decline: no cast can hold them.
        """
        if width not in (2, 4, 8):
            return None
        bits = width * 8
        if -(1 << (bits - 1)) <= v <= (1 << (bits - 1)) - 1:
            return self._WIDE_SIGNED[width]
        if 0 <= v <= (1 << bits) - 1:
            return self._WIDE_UNSIGNED[width]
        return None

    @staticmethod
    def _wide_float_cast(width, src):
        """Float/double cast for a float-literal `src` at `width`, else None.

        The lifter always suffixes float texts (`1.0f`, `1.0d`), so the
        suffix decides: `f` is 4 bytes, `d`/bare is 8. A 4-byte float
        widened to 8 (or the reverse) would change the value.
        """
        if width == 4 and src[-1:] in ('f', 'F'):
            return 'float'
        if width == 8 and (src[-1:] in ('d', 'D')
                           or src[-1:].isdigit()):
            return 'double'
        return None

    def _wide_src_cast(self, width, src, src_ty):
        """Pointer cast rendering a raw native-width store compilable, else None. -- fix 102

        A raw `*(base + disp)` lvalue renders `((byte*)base + disp)[0]`,
        which fails to compile whenever the stored value is not a byte.
        The native width is ground truth from the store instruction, so a
        same-width cast preserves address, value and width: integer
        literals pick signedness by fit (constant expressions convert
        implicitly when representable), float literals keep their
        suffixed width, and register sources are accepted only when the
        source type's size equals the native width, so every rendered
        byte is value-determined (a narrower source would leave upper
        bytes unexplained). Unknown, reference, enum, bool and
        over-wide sources decline and keep today's spelling. Never
        invents a width: only 2/4/8 native widths render.
        """
        if width not in (2, 4, 8):
            return None
        if not src:
            return None
        m = self._WIDE_INT_RX.match(src)
        if m:
            try:
                v = int(m.group(1) + (m.group(2) or m.group(3)), 0)
            except ValueError:
                return None
            return self._wide_int_cast(width, v)
        if self._WIDE_FLOAT_RX.match(src):
            return self._wide_float_cast(width, src)
        if not isinstance(src_ty, tuple) or len(src_ty) != 2:
            return None
        if (src_ty[1] >> 29) & 1:
            return None
        kind = self._WIDE_SRC_KIND.get((src_ty[1] >> 16) & 0xFF)
        if kind is None:
            return None
        sign, size = kind
        if size != width:
            return None
        if sign == 'f':
            return {4: 'float', 8: 'double'}[width]
        return (self._WIDE_SIGNED if sign == 's' else self._WIDE_UNSIGNED)[width]

    def _wide_rmw_cast(self, width, mn, src, src_ty):
        """Pointer cast for a raw read-modify-write store, else None. -- fix 102

        `C = C op S` must stay `C`: integer mnemonics take int-literal
        sources fitting the signed width (an unsigned target would
        promote the arithmetic result away) or a register whose type
        maps exactly to the width cast; float mnemonics take suffixed
        float sources onto float/double. Width 2 never unifies (short
        + int is int) and declines, like everything unproven.
        """
        if width not in (4, 8):
            return None
        if not src:
            return None
        if mn in _WIDE_FLOAT_MN:
            if self._WIDE_FLOAT_RX.match(src):
                return self._wide_float_cast(width, src)
            if isinstance(src_ty, tuple) and len(src_ty) == 2 \
                    and not (src_ty[1] >> 29) & 1:
                exact = self._WIDE_EXACT.get((src_ty[1] >> 16) & 0xFF)
                if exact is not None and exact[1] == width \
                        and exact[0] in ('float', 'double'):
                    return exact[0]
            return None
        m = self._WIDE_INT_RX.match(src)
        if m:
            try:
                v = int(m.group(1) + (m.group(2) or m.group(3)), 0)
            except ValueError:
                return None
            bits = width * 8
            if -(1 << (bits - 1)) <= v <= (1 << (bits - 1)) - 1:
                return self._WIDE_SIGNED[width]
            return None
        if isinstance(src_ty, tuple) and len(src_ty) == 2 \
                and not (src_ty[1] >> 29) & 1:
            exact = self._WIDE_EXACT.get((src_ty[1] >> 16) & 0xFF)
            if exact is not None and exact[1] == width \
                    and exact[0] in ('int', 'uint', 'long', 'ulong'):
                return exact[0]
        return None

    def _wide_store_disp(self, ins, lv, src):
        """Wide display lvalue for one raw plain store, else None. -- fix 102

        Bookkeeping (kills, slots, barriers, twin dedup) keeps the raw
        `*(...)` text; only the emitted statement spells the width. The
        `__static_fields` blob keeps its byte spelling so the sfblob
        twin machinery matches exactly what it always did.
        """
        if not lv.startswith('*('):
            return None
        parts = getattr(self, '_lv_raw_parts', None)
        if parts is None or '__static_fields' in parts[0]:
            return None
        st = strip_outer(src)
        src_ty = None
        if ins.op_kind(1) == OpKind.REGISTER:
            se = dict.get(self.regs, reg_name(ins.op1_register))
            src_ty = se.ty if se is not None else None
        cast = self._wide_src_cast(getattr(self, '_lv_width', None), st, src_ty)
        if cast is None:
            return None
        idx = getattr(self, '_lv_raw_idx', None)
        if idx is not None:
            # fix 124: cast AFTER the byte-addressed sum -- `(T*)E + N`
            # scales N by sizeof(T) (0x18 on float* is byte 0x60).
            return '((%s*)((byte*)%s + %s*%d %s))[0]' % (
                cast, _term_up(parts[0]), _term_up(idx[0], mul=True),
                idx[1], parts[1]), st
        # fix 124: byte-addressed displacement, then the width cast.
        return '((%s*)((byte*)%s %s))[0]' % (cast, parts[0], parts[1]), st

    def _wide_rmw_disp(self, ins, lv, op, src):
        """Wide display lvalue for one raw RMW store, else None. -- fix 102"""
        if not lv.startswith('*('):
            return None
        parts = getattr(self, '_lv_raw_parts', None)
        if parts is None or '__static_fields' in parts[0]:
            return None
        if op in ('++', '--'):
            src, src_ty = '1', None
        else:
            src_ty = None
            if ins.op_kind(1) == OpKind.REGISTER:
                se = dict.get(self.regs, reg_name(ins.op1_register))
                src_ty = se.ty if se is not None else None
        cast = self._wide_rmw_cast(getattr(self, '_lv_width', None), ins.mnemonic,
                                   strip_outer(src), src_ty)
        if cast is None:
            return None
        idx = getattr(self, '_lv_raw_idx', None)
        if idx is not None:
            # fix 124: cast AFTER the byte-addressed sum -- `(T*)E + N`
            # scales N by sizeof(T) (0x18 on float* is byte 0x60).
            return '((%s*)((byte*)%s + %s*%d %s))[0]' % (
                cast, _term_up(parts[0]), _term_up(idx[0], mul=True),
                idx[1], parts[1])
        # fix 124: byte-addressed displacement, then the width cast.
        return '((%s*)((byte*)%s %s))[0]' % (cast, parts[0], parts[1])

    def _wide_raw_lvalue(self, ins, width):
        """Keep the complete native write when a Boolean blob cannot split."""
        be = self.reg(reg_name(ins.memory_base)) if ins.memory_base != IReg.NONE else None
        base = _term_up(be.text) if be is not None else 'unknown'
        address = '(byte*)%s' % base
        if ins.memory_index != IReg.NONE:
            ie = self.reg(reg_name(ins.memory_index))
            address += ' + %s*%d' % (_term_up(ie.text, mul=True) if ie else 'unknown',
                                    ins.memory_index_scale or 1)
        address += ' ' + disp_add(ins.memory_displacement)
        unsigned_type = {2: 'ushort', 4: 'uint', 8: 'ulong'}[width]
        return '((%s*)(%s))[0]' % (unsigned_type, address)

    def _write_mem(self, ins, asm):
        if hasattr(self.il, '_sf_field_size'):
            address = self._stack_address(ins)
            if address is not None:
                value = None
                if ins.op_kind(1) == OpKind.REGISTER:
                    value = self.reg(reg_name(ins.op1_register))
                elif ins.op_kind(1) in IMM_OPS:
                    value = Expr(str(imm_of(ins, 1)), None, 'int')
                self._stack_store(address, MemorySizeExt.size(ins.memory_size), value)
        lv = self._mem_lvalue(ins)
        if lv is None:
            if self.asm_comments and asm:
                self.emit(ins.ip, '', asm)
            return
        if self._coalesced_bool_store(ins, asm):
            return
        width = MemorySizeExt.size(ins.memory_size)
        if self._lv_ty is not None and self.il._type_enum(self._lv_ty) == 0x02 \
                and width in (2, 4, 8):
            # Do not turn a rejected packed store into one wrong Boolean
            # assignment. Preserve its address, value AND native width.
            self._kill_stale(lv)  # preserve reads of the known first field
            lv = self._wide_raw_lvalue(ins, width)
            self._lv_ty = None
        self._kill_stale(lv)
        # spill typing: a register with a type stored into a stack slot
        # records the slot's type so a reload restores the kind ('arr' for
        # arrays) instead of degrading to 'local' -- the raw-pointer LEA
        # receiver bug ((this.inventoryAmounts + 32 + num2*4).ToString())
        # was exactly a spilled-and-reloaded array register. setdefault:
        # first writer wins, same as the byref-slot convention.
        if lv.startswith('s_') and ins.op_kind(1) == OpKind.REGISTER:
            se = self.reg(reg_name(ins.op1_register))
            hty = self._struct_home_ty(se) if se is not None else None
            if se is not None and se.ty is not None \
                    and (se.kind == 'arr' or hty is not None):
                ty = se.ty if se.kind == 'arr' else hty
                self.slot_types.setdefault(lv, ty)
                self._type_hints.setdefault(lv, ty)
        src = self._src_text(ins)
        src = self._fimm(src, self._lv_ty)
        if self._lv_ty is None and (ins.op_kind(1) in IMM_OPS
                or (ins.op_kind(1) == OpKind.REGISTER
                    and _int_lit(src) is not None)):
            # a scalar immediate at a struct-typed home's base addresses
            # the home's first field, not the whole struct (`mov [home],0`
            # zeroes Navigation.m_Mode). Render it field-precisely so the
            # line still compiles once the home is struct-typed; decline
            # (today's scalar) when the proof fails anywhere.
            fp = self._home_field_store(lv, MemorySizeExt.size(ins.memory_size), src)
            if fp is not None:
                lv, src = fp[0], fp[1]
                self._lv_ty = fp[2]
            # single-field whole store (F2-S2): `X.f = Y` displays as
            # `X = Y` when the holder X and Y resolve to the same closed
            # non-enum single-field valuetype, f is its field at the
            # written displacement, and the width covers the struct.
            # Display-only: every bookkeeping key below stays on raw `lv`.
            _fold = None
            try:
                _mx = re.fullmatch(r'([A-Za-z_]\w*)\.([A-Za-z_]\w*)',
                                    (lv or '').strip())
                if _mx is not None and ins.op_kind(1) == OpKind.REGISTER:
                    _re2 = self.reg(reg_name(ins.op1_register))
                    _rty = _re2.ty if _re2 is not None else None
                    _hty = None
                    for _mp in ('_var_types', '_type_hints', 'slot_types'):
                        try:
                            _mm = getattr(self, _mp, None)
                            _hty = _mm.get(_mx.group(1)) if _mm else None
                        except Exception:
                            _hty = None
                        if isinstance(_hty, tuple):
                            break
                    if isinstance(_hty, tuple):
                        _xtd = self._td_of(_hty) if hasattr(self, '_td_of') else None
                        _xtdo = self.meta.typedefs[_xtd] \
                            if _xtd is not None and 0 <= _xtd < len(self.meta.typedefs) else None
                        if _xtdo is not None:
                            _ch = self.il.instance_field_chain(_xtd) \
                                if _xtd is not None else None
                            _en = bool(getattr(_xtdo, 'is_enum', False))
                            _vt = bool(getattr(_xtdo, 'is_valuetype', False))
                            try:
                                _sz = self.il.value_type_size(_xtd)
                            except Exception:
                                _sz = None
                            _fold = self._single_field_store(
                                lv, _hty, _rty, width, _sz,
                                ins.memory_displacement, _ch or {}, _en, _vt)
            except Exception:
                _fold = None
        if lv in self.stack_map.values():
            sev = None
            if ins.op_kind(1) in IMM_OPS:
                sev = Expr(src, self._lv_ty, 'float' if isinstance(self._lv_ty, tuple)
                           and self.il._type_enum(self._lv_ty) in (0x0c, 0x0d) else 'int')
            elif ins.op_kind(1) == OpKind.REGISTER:
                sev = self._copy_expr(self.reg(reg_name(ins.op1_register)))
            if sev is None:
                self.stack_values.pop(lv, None)
            else:
                self.stack_values[lv] = sev
        # address-of alias tracking: a bare slot stored `&pointee` records
        # addr_of[slot] = pointee; a non-address store to the slot pops it
        addr_of = getattr(self, 'addr_of', None)
        if addr_of is not None:
            if src.startswith('&'):
                addr_of[lv] = src[1:]
            elif lv in addr_of:
                addr_of.pop(lv, None)
        # storing a bare temp into a typed location types the temp
        if self._lv_ty is not None and _BARE_TOKEN_RX.match(src):
            self._type_hints.setdefault(src, self._lv_ty)
        wide = self._wide_store_disp(ins, lv, src)
        st = wide[1] if wide is not None else strip_outer(src)
        stmt = '%s = %s;' % (wide[0] if wide is not None else lv, st)
        if self._last_stmt_text() == stmt:
            if self.asm_comments and asm:
                self.emit(ins.ip, '', asm)
            return
        self.emit(ins.ip, stmt, asm)

    def _pointee_of(self, e) -> Expr:
        """Chain-walk addr_of to the slot an address aliases, cycle-guarded,
        so a boxed value passed via a slot reload resolves to its pointee."""
        ao = getattr(self, 'addr_of', None)
        if not ao or e is None or not e.text:
            return e
        seen = set()
        cur = e.text
        while cur in ao and cur not in seen:
            seen.add(cur)
            cur = ao[cur]
        if cur == e.text:
            return e
        return Expr(cur, e.ty, e.kind, e.recv)

    def _rmw_mem(self, ins, asm, op):
        """`add [this+0x20], 11` -> `this.num = this.num + 11;`"""
        lv = self._mem_lvalue(ins)
        if lv is None:
            return
        if lv in self.stack_map.values():
            self.stack_values.pop(lv, None)
        self._kill_stale(lv)
        if op in ('++', '--'):
            dsp = self._wide_rmw_disp(ins, lv, op, '1')
            dd = dsp if dsp is not None else lv
            self.emit(ins.ip, '%s = %s %s 1;' % (dd, dd, op[0]), asm)
            self._rmw_flags(lv)
            return
        src = self._src_text(ins)
        src = self._fimm(src, self._lv_ty)
        if op == '+':
            v = _int_lit(src)
            if v is not None and v < 0:
                op, src = '-', str(-v)
        dsp = self._wide_rmw_disp(ins, lv, op, src)
        dd = dsp if dsp is not None else lv
        self.emit(ins.ip, '%s = %s %s %s;' % (dd, dd, op, src), asm)
        self._rmw_flags(lv)

    def _rmw_flags(self, lv):
        """fix 60b: `add/sub/inc/dec/and/or/xor [mem], x` writes ZF/SF
        just like its register-destination twin, and the lvalue holds
        the RESULT once the statement above is emitted -- so park it in
        the lhs slot with a 0 rhs, the same convention the register path
        uses. Without this a following jcc read some earlier compare's
        pair: InventoryManager.Update's `this.currentInventoryIndex -= 1;
        if (!(unknown))` is exactly that, and reads
        `if (this.currentInventoryIndex < 0)` with it."""
        self.flags = (Expr(lv, self._lv_ty, 'int'),
                      Expr('0', None, 'int'))

    def _fimm(self, src, ty):
        """An integer immediate stored into a float/double-typed location is
        the value's bit pattern (`mov [x+off], 0x3D4CCCCD` is 0.05f):
        reinterpret instead of printing the integer."""
        v = _int_lit(src)
        if v is None or not isinstance(ty, tuple):
            return src
        te = (ty[1] >> 16) & 0xFF
        # a 0/1 immediate stored into a Boolean location is the
        # literal (`this.InvokeRpc = 0;` -> `= false;`), and an int
        # immediate into an enum-typed location is the member
        # (`Stage = 4;` -> `Stage = SimulationStage.X;`) -- batch 39
        if v == 0 and not ((ty[1] >> 29) & 1):
            td_index = self._td_of(ty) if te == 0x15 else None
            if te in (0x0e, 0x12, 0x14, 0x1c, 0x1d) or (td_index is not None
                    and not self.meta.typedefs[td_index].is_valuetype):
                return 'null'
        if te == 0x02 and v in (0, 1):
            return 'true' if v else 'false'
        # Signed integer immediates arrive as unsigned bit patterns at every
        # width, not only Int16: the compiler stores -2 as 0xFFFFFFFE, which
        # printed as `__1__state = 4294967294`. Reinterpret at the declared
        # width; values already in range (and already-negative ones) round
        # trip unchanged, so this only ever rewrites a genuine wrap -- fix 89
        if te in (0x04, 0x06, 0x08, 0x0a):
            width = {0x04: 8, 0x06: 16, 0x08: 32, 0x0a: 64}[te]
            half = 1 << (width - 1)
            return str(((v + half) & ((1 << width) - 1)) - half)
        if te in (0x11, 0x12, 0x15):
            etd = self._td_of(ty)
            em = self.il.enum_members(etd) if etd is not None else None
            if em and v in em:
                return '%s.%s' % (csharp_type_name(self.meta.typedefs[etd].name),
                                  em[v])
        try:
            if te == 0x0c:
                return repr_f32(struct.unpack('<f', struct.pack('<I', v & 0xFFFFFFFF))[0])
            if te == 0x0d:
                return repr_f64(struct.unpack('<d', struct.pack('<Q', v & 0xFFFFFFFFFFFFFFFF))[0])
        except struct.error:
            pass
        return src

    def _home_field_store(self, lv, width, src):
        """Field-precise (lvalue, text, type) for a scalar immediate at a
        struct-typed home's base, or None to keep today's scalar spelling.

        Every step is proved from metadata, never guessed: the home's
        recorded struct type must be an exact closed valuetype, the store
        must be strictly smaller than the struct (a full-home zero is not
        one field), the offset-0 field must exist at its exact width, and
        the rendered literal must compile there (integer fields always do;
        enum/bool/float fields only when `_fimm` names the member)."""
        if not isinstance(lv, str) or not re.fullmatch(r's_[0-9a-fA-F]+', lv):
            return None
        ty = (getattr(self, 'slot_types', None) or {}).get(lv)
        if not isinstance(ty, tuple) or ((ty[1] >> 29) & 1) \
                or ((ty[1] >> 16) & 0xFF) != 0x11:
            return None
        if self.il._closed_type_key(ty) is None:
            return None
        td = self._td_of(ty)
        if td is None or not self.meta.typedefs[td].is_valuetype:
            return None
        size = self.il.value_type_size(td)
        if size is None or not (width < size):
            return None
        chain = self.il.instance_field_chain(td) or {}
        ent = chain.get(0x10)
        if ent is None:
            return None
        name, ti = ent
        fty = self.il.types[ti] if 0 <= ti < len(self.il.types) else None
        if fty is None or self.il._sf_field_size(fty, 0) != width:
            return None
        fte = (fty[1] >> 16) & 0xFF
        text = self._fimm(src, fty)
        if text == src and fte not in (0x04, 0x05, 0x06, 0x07, 0x08, 0x09,
                                      0x0a, 0x0b, 0x18, 0x19):
            return None
        return ('%s.%s' % (lv, name), text, fty)

    def _src_text(self, ins) -> str:
        k = ins.op_kind(1)
        if k in IMM_OPS:
            return str(imm_of(ins, 1))
        if k == OpKind.REGISTER:
            e = self.reg(reg_name(ins.op1_register))
            return e.text if e else '?'
        if k == OpKind.MEMORY:
            # mov [mem],[mem] impossible on x86
            return '?'
        return '?'

    # ------------------------------------------------------------------
