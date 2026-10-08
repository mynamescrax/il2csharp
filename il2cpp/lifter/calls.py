from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.common import csharp_type_name
from il2cpp.expr import acc_get, acc_lhs, acc_set
from il2cpp.expr import Expr, _BARE_TOKEN_RX, _R4_TY, _R8_TY, _REFARG_RX, _USE_BIND_MIN, _byref_arg_render, _is_unresolved_gp, _recv_fold, _recv_shaped
from il2cpp.runtime.meta import IMM_OPS
from il2cpp.text import _int_lit, _deref_spans_all, _norm_twin, _paren_spans_all, _term_up, disp_add, reg_name, rty_has_value, strip_outer
from il2cpp.x64 import ARG_REGS, ARG_XMM, KLASS_VTABLE, VOLATILE
from il2cpp.entrylive import entry_live_args, xmm0_result_width

def _fp32_arg_ok(text):
    """True when an argument text is spellable enough to print.

    A bare `?` never parses, so an argument containing one is not a
    proven argument and the call keeps today's spelling. Null-conditional
    `?.`, coalescing `??`, and the honest `unknown` marker all parse and
    pass; declining a valid text (a ternary, a quoted `?`) only keeps an
    old spelling, never invents a wrong one.
    """
    try:
        t = text or ''
        if '?' not in t:
            return True
        return re.search(r'(?<![\w?])\?(?![?])', t) is None
    except Exception:
        return False


class _CallsMixin:
    def _info_name(self, info):
        """info tuple -> C# name for a resolved call target, or None."""
        if info is None:
            return None
        kind, payload = info
        if kind == 'method':
            m = self.meta.methods[payload]
            td = self.meta.typedefs[m.declaring] if 0 <= m.declaring < len(self.meta.typedefs) else None
            ns = td.namespace + '.' if td and td.namespace else ''
            tpart = csharp_type_name(ns + td.name if td else '?')
            nm = m.name.lstrip('.')
            nm = nm.replace('|', '_')
            nm = nm.replace('@', '_')
            return '%s.%s' % (tpart, nm)
        if kind == 'generic':
            return self.il.generic_method_name(payload)
        if kind == 'thunk':
            mod_name, token = payload
            mod = re.sub(r'[^A-Za-z0-9]', '', mod_name or '') or 'dll'
            return 'adjustor%s_%06x' % (mod, token & 0xFFFFFF)
        return None

    def _thunk_final(self, va):
        """Follow chains of `jmp <imm32>` + padding thunks to the real
        callee. The IL2CPP VM layer routes through hundreds of these; the
        shim address is an implementation detail, not a code location."""
        cache = self._thunk_cache
        if va in cache:
            return cache[va]
        cur = va
        for _ in range(8):
            if not self.bin.is_exec_va(cur):
                break
            code = self.bin.read(cur, 16)
            if not code:
                break
            try:
                dec = Decoder(64, code, DecoderOptions.NONE)
                dec.ip = cur
                ins = next(iter(dec))
            except Exception:
                break
            if ins.mnemonic != Mnemonic.JMP \
                    or ins.op0_kind != OpKind.NEAR_BRANCH64 \
                    or ins.len > 6:
                break
            cur = ins.near_branch_target
        # noreturn forwarders: `sub rsp,X; call T; <int3 pad>` wrappers just
        # forward into T with the same registers; T is the real callee.
        for _ in range(4):
            if not self.bin.is_exec_va(cur):
                break
            code = self.bin.read(cur, 32)
            if not code:
                break
            try:
                dec = Decoder(64, code, DecoderOptions.NONE)
                dec.ip = cur
                ii = [next(iter(dec)) for _ in range(3)]
            except Exception:
                break
            if ii[0].mnemonic != Mnemonic.SUB \
                    or ii[0].op0_kind != OpKind.REGISTER \
                    or reg_name(ii[0].op0_register) != 'RSP' \
                    or ii[1].mnemonic != Mnemonic.CALL \
                    or ii[1].op0_kind != OpKind.NEAR_BRANCH64 \
                    or ii[2].mnemonic not in (Mnemonic.INT3, Mnemonic.UD2):
                break
            cur = ii[1].near_branch_target
        res = cur if cur != va else None
        cache[va] = res
        return res

    def _fp32_scalar_next(self, ins):
        """Width of the scalar XMM0 consume after `ins`, if any.

        Walks forward from the next instruction (at most 16) to a scalar
        FP consume of XMM0 (`mulss/addss/subss/divss xmm0, ...`, or a
        `movss` spill/copy from XMM0): the caller expects the call's float
        result there. Skipped instructions must not touch the value
        channel -- no XMM0/YMM0 mention (reg_name folds YMM into XMM),
        no calls (volatile clobber), no returns, unconditional jumps,
        indirect flow, or kernel transitions; flag tests, conditional
        branches, NOPs, constant loads, and unrelated moves all skip
        (memory effects between call and consume do not disturb XMM0,
        and the bind stays pinned at the call). A conditional branch
        whose target lands between the call and the consume declines
        (the consume would read a merge, not the call's value), as does
        any revisit (loops), decode failure, or running past the cap.
        Anything else declines and the call keeps today's spelling.
        """
        if not HAVE_ICED:
            return None
        try:
            call_ip = ins.ip
            ip = ins.next_ip
        except Exception:
            return False
        targets = []
        seen = set()
        for _ in range(16):
            if ip in seen:
                return False
            seen.add(ip)
            try:
                code = self.bin.read(ip, 16)
                if not code:
                    return None
                dec = Decoder(64, code, DecoderOptions.NONE)
                dec.ip = ip
                nx = next(iter(dec))
            except Exception:
                return False
            try:
                m = nx.mnemonic
                width = None
                if m in (Mnemonic.MULSS, Mnemonic.ADDSS,
                         Mnemonic.SUBSS, Mnemonic.DIVSS) \
                        and nx.op0_kind == OpKind.REGISTER \
                        and reg_name(nx.op0_register) == 'XMM0':
                    width = 'f'
                elif m == Mnemonic.MOVSS and nx.op_count == 2 \
                        and nx.op1_kind == OpKind.REGISTER \
                        and reg_name(nx.op1_register) == 'XMM0':
                    width = 'f'
                elif m in (Mnemonic.CVTSS2SD, Mnemonic.CVTSS2SI,
                            Mnemonic.CVTTSS2SI) and nx.op_count == 2 \
                        and nx.op1_kind == OpKind.REGISTER \
                        and reg_name(nx.op1_register) == 'XMM0':
                    width = 'f'
                elif m == Mnemonic.MOVAPS and nx.op_count == 2 \
                        and nx.op0_kind == OpKind.REGISTER \
                        and nx.op1_kind == OpKind.REGISTER \
                        and reg_name(nx.op1_register) == 'XMM0':
                    width = 'f'
                elif m in (Mnemonic.CVTSD2SI, Mnemonic.CVTTSD2SI) \
                        and nx.op_count == 2 \
                        and nx.op1_kind == OpKind.REGISTER \
                        and reg_name(nx.op1_register) == 'XMM0':
                    width = 'd'
            except Exception:
                return None
            if width is not None:
                for t in targets:
                    if call_ip < t <= ip:
                        return None
                return width
            if not self._fp32_skip_next(nx):
                return None
            if nx.flow_control == FlowControl.CONDITIONAL_BRANCH:
                try:
                    targets.append(nx.near_branch_target)
                except Exception:
                    return False
            ip = nx.next_ip
        return None

    @staticmethod
    def _fp32_skip_next(nx):
        """True when walking past `nx` cannot disturb an XMM0 value."""
        try:
            m = nx.mnemonic
            if m == Mnemonic.CALL or m == Mnemonic.RET:
                return False
            if m in (Mnemonic.SYSCALL, Mnemonic.SYSENTER, Mnemonic.INT,
                      Mnemonic.HLT) or nx.has_lock_prefix:
                return False
            if m == Mnemonic.CPUID:
                return False
            if nx.flow_control == FlowControl.INDIRECT_BRANCH:
                return False
            if nx.flow_control == FlowControl.UNCONDITIONAL_BRANCH:
                return False
            for i in range(nx.op_count):
                if getattr(nx, 'op%d_kind' % i) != OpKind.REGISTER:
                    continue
                if reg_name(getattr(nx, 'op%d_register' % i)) == 'XMM0':
                    return False
            return True
        except Exception:
            return False

    def _dead_shared_forwarder(self, target, ins):
        """True when a pending bare-statement must be declined: the caller
        address has several metadata owners (a shared body), the call
        target has exactly one, and the instruction after the call is
        an abort (int3/ud2) -- the result is dead by construction and
        naming one sibling for all arms repeats the batch-11
        confidently-wrong-name fault. Every gate declines to the old
        flush behavior."""
        if target is None:
            return False
        il = getattr(self, 'il', None)
        m = getattr(self, '_current_method', None)
        if il is None or m is None:
            return False
        try:
            cands = getattr(il, 'addr_candidates', None) or {}
            own = cands.get(m.addr)
            if not own or len(own) < 2:
                return False
            tgt = cands.get(target)
            if tgt is None or len(tgt) != 1:
                return False
        except Exception:
            return False
        try:
            b = getattr(self, 'bin', None)
            nx_ip = ins.next_ip
            if b is None or not b.is_exec_va(nx_ip):
                return False
            code = b.read(nx_ip, 16)
            if not code:
                return False
            dec = Decoder(64, code, DecoderOptions.NONE)
            dec.ip = nx_ip
            nx = next(iter(dec))
            if nx.mnemonic not in (Mnemonic.INT3, Mnemonic.UD2):
                return False
        except Exception:
            return False
        return True

    def _dead_shared_forwarder_return(self, target, ins, call, rty):
        """`return <call>;` for a noreturn-shared forwarder, else None.

        Same shape `_dead_shared_forwarder` declines (shared caller body,
        exactly one target owner, abort right after the call): the call is
        the whole reachable behavior and MSVC's own `call; int3/ud2` is
        the noreturn evidence, so spelling it as a tail `return` compiles
        and names only proven identities. Fires only when the target is
        one readable MethodDef whose exact return tuple equals the
        caller's (so `return` type-checks), both non-void, and the call
        text carries no honesty marker. Everything else declines to the
        old drop."""
        if not call or '/*' in call or rty is None:
            return None
        if not self._dead_shared_forwarder(target, ins):
            return None
        try:
            cands = (getattr(self.il, 'addr_candidates', None) or {}).get(target) or []
            if len(cands) != 1 or cands[0][0] != 'method':
                return None
            tmi = cands[0][1]
            m = getattr(self, '_current_method', None)
            if m is None or not 0 <= tmi < len(self.meta.methods):
                return None
            if self.il._type_enum(rty) == 0x01:
                return None
            crt = self.il.types[m.return_type] \
                if 0 <= m.return_type < len(self.il.types) else None
            if crt is None or crt != rty:
                return None
            return 'return %s;' % call
        except Exception:
            return None

    # fix 93: the noreturn raisers the discovery pass names from the
    # exception-class string their wrapper chain lea's
    # (`raise_IndexOutOfRangeException`,
    # `raise_NullReferenceException`). Each raises one specific new
    # exception, so the honest render is `throw new <Exc>();` -- not a
    # bare `throw;` (which loses which exception is thrown) and not a
    # named call with a fabricated `object` result (they never return).
    _NAMED_RAISE_THROW = {
        'raise_IndexOutOfRangeException': 'System.IndexOutOfRangeException',
        'raise_NullReferenceException': 'System.NullReferenceException',
    }

    def _named_raise_throw(self, target, name):
        """Fully-qualified exception for a proved named-raise call, else None.

        Every gate is a property of the callee, never the call site: the
        exact evidence-derived name, arity 0, unregistered native code,
        and the `sub rsp,X; call T; int3/ud2` noreturn-forwarder shape
        (the same trailing-int3 gate `_thunk_final` uses). Only positive
        proof renders; an unreadable target keeps the old named call.
        """
        exc = self._NAMED_RAISE_THROW.get(name)
        if exc is None or target is None:
            return None
        if self.RT_ARITY.get(name, 0) != 0:
            return None
        il = getattr(self, 'il', None)
        if il is not None:
            if target in (getattr(il, 'addr_to_method', None) or {}):
                return None
            cands = getattr(il, 'addr_candidates', None)
            if cands is not None:
                try:
                    if cands.get(target):
                        return None
                except Exception:
                    pass
        b = getattr(self, 'bin', None)
        if b is not None and target in (getattr(b, 'exports', None) or {}):
            return None
        try:
            if b is None or not b.is_exec_va(target):
                return None
            code = b.read(target, 32)
            if not code:
                return None
            dec = Decoder(64, code, DecoderOptions.NONE)
            dec.ip = target
            ii = [next(iter(dec)) for _ in range(3)]
        except Exception:
            return None
        if not (ii[0].mnemonic == Mnemonic.SUB
                and ii[0].op0_kind == OpKind.REGISTER
                and reg_name(ii[0].op0_register) == 'RSP'
                and ii[1].mnemonic == Mnemonic.CALL
                and ii[1].op0_kind == OpKind.NEAR_BRANCH64
                and ii[2].mnemonic in (Mnemonic.INT3, Mnemonic.UD2)):
            return None
        return exc

    def _caller_is_void(self):
        """True when the method being lifted returns void.

        A tail call in a void method is `<call>; return;`: `return
        <call>;` has nowhere to put the value and is not C#. Only an
        exact metadata void proves it; anything unreadable keeps the
        old rendering. -- fix 95
        """
        m = getattr(self, '_current_method', None)
        il = getattr(self, 'il', None)
        if m is None or il is None:
            return False
        try:
            rti = m.return_type
            types = il.types
            rt = types[rti] if 0 <= rti < len(types) else None
            enum = il._type_enum(rt) if rt is not None else None
        except Exception:
            return False
        return enum == 0x01

    def _accessor_prop(self, mi):
        """fix 137: the property row a MethodDef accessor belongs to.

        Returns ``(kind, name, n_index)`` -- kind 'get'/'set', the
        property's emitted member name and its index-parameter count --
        when MethodDef ``mi`` is the getter or setter of a property row
        on its own declaring type, else None. The emitter declares exactly
        these rows as properties (index parameters -> ``this[...]``), so
        a call naming one can use the member syntax the declaration
        provides: ``s.get_Chars(i)`` -> ``s[i]`` (String's indexer row is
        named Chars), ``Gizmos.set_color(c)`` -> ``Gizmos.color = c``.
        Explicit (dotted) rows, a row whose accessor name disagrees, and
        unreadable metadata decline. Per instance: MethodDef indices are
        binary-local.
        """
        cache = self.__dict__.setdefault('_acc_prop_cache', {})
        if mi in cache:
            return cache[mi]
        res = None
        try:
            m = self.meta.methods[mi]
            if m.declaring >= 0:
                td = self.meta.typedefs[m.declaring]
                rel = mi - td.method_start
                for k in range(td.property_count):
                    pr = self.meta.properties[td.property_start + k]
                    if rel == pr[1]:
                        kind, nidx = 'get', m.param_count
                    elif rel == pr[2]:
                        kind, nidx = 'set', m.param_count - 1
                    else:
                        continue
                    raw = self.meta.getstr(pr[0])
                    if raw and '.' not in raw and nidx >= 0 \
                            and m.name == kind + '_' + raw:
                        from il2cpp.names import safe_ident, sanitize
                        res = (kind, safe_ident(sanitize(csharp_type_name(raw))), nidx)
                    break
        except Exception:
            res = None
        cache[mi] = res
        return res

    def _accessor_sugar(self, mi, recv, rest):
        """fix 137: member spelling of a proved accessor call.

        ``recv`` is the receiver text of an instance accessor (a leading
        ``&`` already stripped by the caller) or the owner type text of a
        static one; ``rest`` is the declared argument list without the
        receiver. Returns ``('expr', text)`` for a getter, ``('stmt',
        text)`` (no ``;``) for a setter, or None: not an accessor row,
        arity disagreeing with the row, a placeholder argument, a static
        indexer, or a receiver text that is not receiver-shaped.
        """
        ap = self._accessor_prop(mi) if mi is not None else None
        if ap is None or not recv:
            return None
        kind, pname, nidx = ap
        if self.meta.methods[mi].is_static:
            if nidx:
                return None
            head = recv
        else:
            if not _recv_shaped(recv):
                return None
            head = _recv_fold(recv)
        if any(a in ('?', '', '_') for a in rest):
            return None
        if kind == 'get':
            if len(rest) != nidx:
                return None
            if nidx == 0:
                return ('expr', acc_get('%s.%s' % (head, pname)))
            return ('expr', acc_get('%s[%s]' % (head, ', '.join(rest))))
        if len(rest) != nidx + 1:
            return None
        if nidx == 0:
            return ('stmt', acc_set('%s.%s' % (head, pname), rest[-1]))
        return ('stmt', acc_set('%s[%s]' % (head, ', '.join(rest[:-1])), rest[-1]))

    def _static_owner(self, name, mi):
        """fix 137: the owner text of a resolved static call `Owner.method`."""
        try:
            suf = '.' + self.meta.methods[mi].name
        except Exception:
            return None
        if name and name.endswith(suf) and len(name) > len(suf):
            return name[:-len(suf)]
        return None

    def _tail_accessor(self, mi, args):
        """fix 137: accessor spelling of a resolved tail call's printed
        argument list (receiver first for instance accessors). A getter
        tail in a void caller declines: `R.X; return;` is not a statement.
        """
        try:
            m = self.meta.methods[mi]
        except Exception:
            return None
        if '.' in m.name:
            return None
        if m.is_static:
            own = self._static_owner(self._info_name(('method', mi)), mi)
            sg = self._accessor_sugar(mi, own, list(args)) if own else None
        elif args:
            r = args[0]
            if r.startswith('&') and _REFARG_RX.match(r[1:]):
                r = r[1:]
            sg = self._accessor_sugar(mi, r, list(args[1:]))
        else:
            sg = None
        if sg is None or (sg[0] == 'expr' and self._caller_is_void()):
            return None
        return sg[1]

    def _emit_tail(self, ip, call, asm, void=False, marker=True):
        """Emit a tail call, honoring a void caller. -- fix 95

        `void` is the callee-side proof the existing tails already
        carry; the caller side is new: a value-returning tail in a void
        method renders `<call>; return;`. Each site keeps its own
        `/* tail */` marker habit.
        """
        if void or self._caller_is_void():
            self.emit(ip, '%s; return;' % call, asm)
        elif marker:
            self.emit(ip, 'return %s; /* tail */' % call, asm)
        else:
            self.emit(ip, 'return %s;' % call, asm)

    def _spec_md(self, si):
        """MethodDef row for a MethodSpec index, or None when unreadable."""
        try:
            md = self.il.method_specs[si][0]
        except Exception:
            return None
        try:
            if 0 <= md < len(self.meta.methods):
                return md
        except Exception:
            pass
        return None

    def _tail_hidden_generic(self, cands, args, arg_exprs):
        """Resolve a shared tail through its hidden instantiation argument.

        Mirrors the `_call` generic-identity proof -- IL2CPP passes the
        exact instantiation as an argument whose text is exactly what
        `generic_method_name()` renders for it -- with two tightenings
        tails need. First, the match must be trailing: the instantiation
        travels last, so an identity with a real (written,
        non-placeholder) argument after it is a stale leftover, not this
        call's callee. Ground-truthed at AudioVolumeSliders.Start, whose
        `mov r8,[slot]` sits immediately before the tail jmp. Second,
        every identity in play must name one spec: conflicting
        identities decline. Candidate MEMBERSHIP is deliberately not
        required: the same method proves the registry can miss a true
        sharer (eight listed candidates are all zero-arg TypeTraits
        getters while R8 selects UnityEvent<float>.AddListener, which the
        body dispatches through). Returns (display_name, md_row_or_None,
        drop_index) or None. The row is set only for one distinct spec,
        so a shared rendering never trims to the wrong signature. --
        fix 94
        """
        if not cands or len(cands) < 2:
            return None
        try:
            generics = [c for c in cands if c[0] == 'generic']
        except Exception:
            return None
        gname = getattr(self.il, 'generic_method_name', None)
        if gname is None:
            return None
        exprs = arg_exprs or []
        argv = args or []

        def _written(j):
            if j < 0 or j >= len(exprs):
                return False
            if j < len(argv) and (not argv[j] or not argv[j].strip()
                                 or argv[j] == '_'):
                return False
            ae = exprs[j]
            return ae is not None and not getattr(ae, '_unk', False)

        matches = []  # (index, spec_slot, name)
        for i, ae in enumerate(exprs):
            if ae is None or not ae.text:
                continue
            si = getattr(ae, '_usg_idx', None)
            if si is not None:
                try:
                    nm6 = gname(si)
                except Exception:
                    nm6 = None
                if nm6 is not None and ae.text == nm6:
                    matches.append((i, si, nm6))
                    continue
            for c in generics:
                try:
                    nm = gname(c[1])
                except Exception:
                    continue
                if ae.text == nm:
                    matches.append((i, c[1], nm))
                    break
        if not matches:
            return None
        if len({mm[1] for mm in matches}) != 1:
            return None
        valid = [mm for mm in matches
                 if not any(_written(j) for j in range(mm[0] + 1, len(exprs)))]
        if not valid:
            return None
        return (valid[0][2], self._spec_md(valid[0][1]), valid[0][0])

    def _tail_trim_stale(self, args, arg_exprs):
        """Drop trailing placeholder/stale tail arguments (fix-58 mirror).

        A tail call's argument registers must be written at the jump: a
        trailing slot still holding its entry-seed/clobber unknown (or
        never written at all) carries no argument. `_call` trims exactly
        these; tails never did. Both lists stay parallel (tails carry no
        appended XMM tail, unlike `_call`). -- fix 94
        """
        try:
            width = len(ARG_REGS)
        except Exception:
            width = 4
        unk = [(a is not None and getattr(a, '_unk', False))
               for a in (arg_exprs or [])[:width]]
        while args and (args[-1] == '_'
                        or (len(args) <= len(unk) and unk[len(args) - 1])):
            args.pop()
            if len(arg_exprs or []) > len(args):
                arg_exprs.pop()

    def _shared_arity_cap(self, cands, rty=None):
        """Largest declared argument-slot count across shared-body candidates.

        Batch 21j's proof, factored out of `_call` so tails can trim with
        it too: every candidate names a call into the same compiled
        machine code, so they all consume the same argument registers,
        and the largest declared arity among them -- receiver included,
        plus the hidden sret buffer whenever `rty` is the all-candidates
        consensus return -- bounds the slots the call can use. A
        candidate the registry cannot read is skipped (the inline loop
        this came from bounded only the generic row's index and let a
        malformed method row propagate); `None` means nothing was
        readable and the caller keeps its legacy spelling.
        """
        if not cands:
            return None
        wants = []
        for c in cands:
            m3 = None
            try:
                if c[0] == 'method':
                    if 0 <= c[1] < len(self.meta.methods):
                        m3 = self.meta.methods[c[1]]
                elif c[0] == 'generic':
                    md3 = self.il.method_specs[c[1]][0]
                    if 0 <= md3 < len(self.meta.methods):
                        m3 = self.meta.methods[md3]
            except Exception:
                continue
            if m3 is None:
                continue
            rt3 = self.il.types[m3.return_type] \
                if 0 <= m3.return_type < len(self.il.types) else None
            abi_rt3 = rty if rty is not None else rt3
            wants.append(m3.param_count + (0 if m3.is_static else 1)
                         + int(self.il.returns_sret(abi_rt3)))
        return max(wants) if wants else None

    def _shared_slot_classes(self, cands, rty=None):
        """All-candidate agreement on each argument slot's register class.

        Every candidate names a call into the same compiled machine code,
        so they consume the same argument registers.  `_shared_arity_cap`
        bounds HOW MANY slots that is; this bounds WHICH LANE each slot
        uses -- but only when every candidate is a readable non-generic
        MethodDef that agrees on the class of every slot: 'g' for the
        receiver, the hidden sret buffer, integers, pointers and byrefs,
        'x' for a by-value float/double parameter (R4/R8).  A generic
        spec, an unreadable row, or any disagreement returns None and the
        caller keeps the raw GPR-first spelling.  The hidden sret buffer
        is classified exactly like `_shared_arity_cap` does when `rty` is
        the consensus return, so the two agree on the slot count.
        """
        if not cands:
            return None
        sigs = []
        for c in cands:
            if c[0] != 'method' or not 0 <= c[1] < len(self.meta.methods):
                return None
            m3 = self.meta.methods[c[1]]
            rt3 = self.il.types[m3.return_type] \
                if 0 <= m3.return_type < len(self.il.types) else None
            abi_rt3 = rty if rty is not None else rt3
            cls = []
            if not m3.is_static:
                cls.append('g')          # receiver in the first free GPR
            if self.il.returns_sret(abi_rt3):
                cls.append('g')          # hidden return buffer in RCX
            for p in self.meta.method_params(m3):
                if not 0 <= p.type < len(self.il.types):
                    return None
                bits = self.il.types[p.type][1]
                te = (bits >> 16) & 0xFF
                is_float = te in (0x0c, 0x0d) and not ((bits >> 29) & 1)
                cls.append('x' if is_float else 'g')
            sigs.append(''.join(cls))
        if len(set(sigs)) != 1:
            return None
        return sigs[0]

    def _shared_positional_args(self, args, classes):
        """Rebuild a shared body's printed arguments by ABI position.

        `args` is the raw GPR-first spray with any tracked XMM values
        appended, so truncating it to the all-candidates arity cap prints
        the stale RCX value where a float parameter lives and drops the
        real XMM argument (mi 20081: the `op_Implicit` triple at
        0x182da54f0 takes one float; the `mulss xmm0,xmm0` square leaf
        0x1826e1660 likewise).  With `_shared_slot_classes` proving every
        candidate agrees on the class sequence, position k is XMMk when
        classes[k] == 'x' and the k-th GPR slot otherwise.  An untracked
        slot prints the same `_` placeholder the raw path uses.
        """
        xmm = getattr(self, '_xmm_pending', None) or []
        out = []
        for k, cls in enumerate(classes):
            if cls == 'x':
                xe = None
                for kk, e in xmm:
                    if kk == k:
                        xe = e
                        break
                out.append(xe.text if xe is not None and xe.text else '_')
            else:
                out.append(args[k] if k < len(args) else '_')
        return out

    def _shared_tail_keep(self, target, args):
        """How many arguments an unresolved shared-body tail may print.

        `_call` bounds every ambiguous shared body's list by the largest
        declared arity among its candidates (batch 21j); tails printed the
        whole register spray instead, so one VA rendered `(x)` when called
        and `(x, 0)` when tail-jumped, though both name the same compiled
        code. Reuse that proof here, narrowly: only a trailing run of
        literal zeros is dropped -- the plumbing value a shared forwarder
        wrote into a register no candidate declares (`xor edx,edx` / `mov
        r8d,0` right ahead of the jmp), which is never something the
        source wrote. A non-zero trailing argument keeps today's spelling,
        so a registry-missed sharer whose extra register really is read
        (probed: List`1.CopyTo's R8 at 0x180df9c30) is untouched.
        Returns the keep count, or None to leave the list alone.
        """
        cands = self.il.addr_candidates.get(target) if target else None
        if not cands or len(cands) < 2 or len(args) <= 1:
            return None
        cap = self._shared_arity_cap(cands)
        if cap is None or not 0 < cap < len(args):
            return None
        for i in range(cap, min(len(args), len(ARG_REGS))):
            if args[i] != '0':
                return None
        return cap

    def _tail_generic_call(self, tg_name, tg_md, args, arg_exprs):
        """Render a tail resolved through its hidden instantiation argument.

        Signature-trimmed via `_tail_method_args` and instance-folded
        exactly like a resolved method tail, but named for the true
        generic instantiation instead of the shared marker. A resolved
        constructor takes the initializer pseudo-form (`this..ctor` /
        `base..ctor`) the emitter promotes -- a single-dot `this.ctor`
        would be dead legacy text no pass owns. Returns (call_text,
        method). -- fix 94
        """
        m2 = self.meta.methods[tg_md]
        init_kind = self._constructor_initializer_kind(
            m2, arg_exprs[0] if arg_exprs else None)
        if init_kind is not None:
            targs = self._tail_method_args(tg_md, args, arg_exprs)
            return ('%s..ctor(%s)' % (init_kind, ', '.join(targs[1:])), m2)
        targs = self._tail_method_args(tg_md, args, arg_exprs)
        if not m2.is_static and targs and targs[0] != '?' \
                and (targs[0] == 'this' or '.' in targs[0]
                     or _BARE_TOKEN_RX.match(targs[0])
                     or (_recv_shaped(targs[0])
                         and not m2.name.startswith('.'))):
            base = m2.name.rpartition('.')[2] if '.' in m2.name else m2.name
            return ('%s.%s(%s)' % (_recv_fold(targs[0]), base, ', '.join(targs[1:])), m2)
        return ('%s(%s)' % (tg_name, ', '.join(targs)), m2)

    def _tail_subst_closed(self, ty, spec):
        """Closed type tuple for one signature type under a MethodSpec.

        Single-level VAR/MVAR substitution through the spec's class
        (0x13) or method (0x1e) instantiation, mirroring
        `candidate_return_type` including byref preservation; anything
        else passes through for `_closed_type_key` gating (nested-open
        and unreadable rows gate to None there). Any failure declines
        with None. -- fix 100
        """
        try:
            if spec is not None and ty is not None and isinstance(ty, tuple) and len(ty) == 2:
                te = (ty[1] >> 16) & 0xFF
                if te in (0x13, 0x1e) and 0 <= ty[0] < len(self.meta.generic_parameters):
                    ordinal = self.meta.generic_parameters[ty[0]][4]
                    inst = spec[1] if te == 0x13 else spec[2]
                    args = self.il._method_spec_type_args(inst)
                    actual = args[ordinal] if args is not None and 0 <= ordinal < len(args) else None
                    if actual is None:
                        return None
                    return (actual[0], (actual[1] & ~(1 << 29)) | (ty[1] & (1 << 29)))
            return ty
        except Exception:
            return None

    def _tail_sig_key(self, cand):
        """Canonical rendering key for one shared-tail candidate.

        Two candidates share a key only if the resolved-tail renderer
        prints them identically from the same call-site state (same
        name text, staticness, closed parameter types, callee
        voidness). Anything unrenderable -- unreadable rows, unbound
        VARs (open generic definitions need receiver instantiation, a
        separate proof), unknown names, generic owners on static
        method candidates (the bare owner spelling would drop `<T>`) --
        declines with None, so it can only ever block a resolution,
        never join one. -- fix 100
        """
        try:
            kind = cand[0]
        except Exception:
            return None
        try:
            if kind == 'method':
                mi = cand[1]
                m = self.meta.methods[mi]
                owner = self.meta.typedefs[m.declaring] if 0 <= m.declaring < len(self.meta.typedefs) else None
                if owner is None or m.generic_container != -1 or owner.generic_container != -1:
                    return None
                nm = self._info_name(('method', mi))
                if nm is None:
                    return None
                pkeys = []
                for p in self.meta.method_params(m):
                    if not (0 <= p.type < len(self.il.types)):
                        return None
                    k = self.il._closed_type_key(self.il.types[p.type])
                    if k is None:
                        return None
                    pkeys.append(k)
                rti = m.return_type
                rty = self.il.types[rti] if 0 <= rti < len(self.il.types) else None
                void = rty is not None and ((rty[1] >> 16) & 0xFF) == 0x01
                return (('m', nm, bool(m.is_static), tuple(pkeys), bool(void)), ('method', mi))
            if kind == 'generic':
                si = cand[1]
                spec = self.il.method_specs[si]
                md = self._spec_md(si)
                if md is None:
                    return None
                m = self.meta.methods[md]
                nm = self.il.generic_method_name(si)
                if nm is None:
                    return None
                pkeys = []
                for p in self.meta.method_params(m):
                    if not (0 <= p.type < len(self.il.types)):
                        return None
                    ty = self._tail_subst_closed(self.il.types[p.type], spec)
                    if ty is None:
                        return None
                    k = self.il._closed_type_key(ty)
                    if k is None:
                        return None
                    pkeys.append(k)
                rti = m.return_type
                rty = self.il.types[rti] if 0 <= rti < len(self.il.types) else None
                void = rty is not None and ((rty[1] >> 16) & 0xFF) == 0x01
                return (('g', nm, md, bool(m.is_static), tuple(pkeys), bool(void)), ('generic', nm, md))
            return None
        except Exception:
            return None

    def _shared_tail_return_target(self, cands):
        """Resolve an ambiguous shared tail by the caller's return type.

        A `return <call>` tail delivers the callee's value as the
        caller's own, so the true callee's closed, spec-inflated return
        must equal the caller's exact metadata return. Keep nothing on
        speculation: open or unreadable candidate returns decline the
        whole resolution (a fully-closed-or-decline rule -- an unbound
        row might be the true callee), closed mismatches drop, and only
        one distinct rendering (`_tail_sig_key`) across every survivor
        resolves, in the render form the existing resolved-tail
        emitters consume (`('method', mi)` for the `info` path,
        `('generic', name, md)` for `_tail_generic_call`). Decline on
        void callers (fix 95 owns voids, where a value filter is both
        vacuous and unsound), on open or unknown caller returns, on
        empty or split survivors, and on any non-method/generic row.
        Never invents a name: winners always come from the listed set,
        and identical renderings make the pick unobservable. -- fix 100
        """
        try:
            m = getattr(self, '_current_method', None)
            if m is None or self._caller_is_void():
                return None
            il = self.il
            crt = il.types[m.return_type] if 0 <= m.return_type < len(il.types) else None
            ckey = il._closed_type_key(crt)
            if ckey is None:
                return None
            keys = []
            for c in cands:
                try:
                    kind = c[0]
                except Exception:
                    return None
                if kind == 'method':
                    cm = self.meta.methods[c[1]]
                    rt = il.types[cm.return_type] if 0 <= cm.return_type < len(il.types) else None
                elif kind == 'generic':
                    si = c[1]
                    spec = il.method_specs[si]
                    md = self._spec_md(si)
                    if md is None:
                        return None
                    cm = self.meta.methods[md]
                    rt = self._tail_subst_closed(
                        il.types[cm.return_type] if 0 <= cm.return_type < len(il.types) else None, spec)
                    if rt is None:
                        return None
                else:
                    return None
                if rt is None:
                    return None
                try:
                    rkey = il._closed_type_key(rt)
                except Exception:
                    return None
                if rkey is None:
                    return None
                if rkey != ckey:
                    continue
                built = self._tail_sig_key(c)
                if built is None:
                    return None
                keys.append(built)
            if not keys:
                return None
            first = keys[0][0]
            if any(k != first for k, _r in keys):
                return None
            return keys[0][1]
        except Exception:
            return None

    _IMM_KINDS = (OpKind.IMMEDIATE8, OpKind.IMMEDIATE8TO16,
              OpKind.IMMEDIATE8TO32, OpKind.IMMEDIATE8TO64,
              OpKind.IMMEDIATE16, OpKind.IMMEDIATE32, OpKind.IMMEDIATE64)

    def _is_class_init_twin(self, va):
        """The out-of-line copy of the class-init fast path the compiler
        usually inlines: `cmp dword [rcx+0E4h],0; je <export>; ret`.
        Tail-jmps land here far more often than calls, so the init census
        misses it; check lazily and memoize."""
        c = self._twin_cache
        if va in c:
            return c[va]
        ex = self._cls_init_export
        res = False
        if ex and self.bin.is_exec_va(va):
            code = self.bin.read(va, 16)
            if code:
                try:
                    dec5 = Decoder(64, code, DecoderOptions.NONE)
                    dec5.ip = va
                    ins0 = next(iter(dec5))
                    ins1 = next(iter(dec5))
                    if ins0.mnemonic == Mnemonic.CMP \
                            and ins0.op0_kind == OpKind.MEMORY \
                            and ins0.memory_base == IReg.RCX \
                            and ins0.memory_displacement == 0xE4 \
                            and ins0.op1_kind in self._IMM_KINDS \
                            and ins1.mnemonic in (Mnemonic.JE, Mnemonic.JNE) \
                            and ins1.op0_kind == OpKind.NEAR_BRANCH64 \
                            and ins1.near_branch_target == ex:
                        res = True
                except Exception:
                    pass
        c[va] = res
        return res

    def _is_stack_probe(self, va):
        """True when VA is the MSVC stack probe (__chkstk). Three call
        shapes share one callee on this corpus (1,094 sites / 392 method
        extents, work/probe_census.py): the constant big-frame prologue
        `mov eax,imm; call; sub rsp,rax`, and the dynamic-alloca twins
        `mov rax,r8; call; sub rsp,r8` / `and rax,~0xF; call; sub rsp,rax`.
        Identified by SIGNATURE -- a gs-relative TEB stack read plus the
        1-byte [r11] page-touch store -- so a different build's chkstk
        address still matches; memoized per VA."""
        c = getattr(self, '_probe_va_cache', None)
        if c is None:
            c = self._probe_va_cache = {}
        if va in c:
            return c[va]
        res = False
        try:
            if va and self.bin.is_exec_va(va) \
                    and not self.il.addr_to_method.get(va) \
                    and not self.il.addr_candidates.get(va):
                code = self.bin.read(va, 96)
                if code:
                    d = Decoder(64, code, DecoderOptions.NONE)
                    d.ip = va
                    saw_gs = saw_touch = False
                    for pin in d:
                        if pin.memory_segment == IReg.GS:
                            saw_gs = True
                        if pin.mnemonic == Mnemonic.MOV \
                                and pin.op0_kind == OpKind.MEMORY \
                                and pin.memory_base == IReg.R11 \
                                and int(pin.memory_size) == 1 \
                                and pin.op1_kind in IMM_OPS \
                                and pin.immediate(1) == 0:
                            saw_touch = True
                        if saw_gs and saw_touch:
                            res = True
                            break
        except Exception:
            res = False
        c[va] = res
        return res

    def _shared_static_arg_target(self, cands, arg_exprs):
        """Resolve only the identical-ABI, one-struct-argument static case.

        A LayerMask argument distinguishes op_Implicit(LayerMask) from the
        folded int/uint/other-struct identity functions. All candidates must
        consume exactly one GPR value and return one GPR value: otherwise a
        typed RCX may just be stale beside a float argument or a hidden sret
        buffer. Generic, pointer, receiver and stack-argument cases stay
        unresolved. Match metadata identity, never a printed name or arity.
        """
        if not cands or not arg_exprs:
            return None
        actual = arg_exprs[0]
        ty = actual.ty if actual is not None else None
        if ty is None or actual._unk or actual.kind in ('ptr', 'klass', 'usage') \
                or (actual.text or '').startswith('&'):
            return None
        if self.il._type_enum(ty) != 0x11 or (ty[1] >> 29) & 1:
            return None
        ti = self._td_of(ty)
        if ti is None or not self.meta.typedefs[ti].is_valuetype:
            return None
        scalar = {0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
                  0x08, 0x09, 0x0a, 0x0b, 0x11}
        hits = []
        for kind, mi in cands:
            if kind != 'method' or not 0 <= mi < len(self.meta.methods):
                return None
            method = self.meta.methods[mi]
            if not method.is_static or method.param_count != 1:
                return None
            params = list(self.meta.method_params(method))
            if len(params) != 1 or not 0 <= params[0].type < len(self.il.types) \
                    or not 0 <= method.return_type < len(self.il.types):
                return None
            pt, rt = self.il.types[params[0].type], self.il.types[method.return_type]
            for candidate_ty in (pt, rt):
                if self.il._type_enum(candidate_ty) not in scalar \
                        or (candidate_ty[1] >> 29) & 1 \
                        or self.il.returns_sret(candidate_ty):
                    return None
            # Field/parameter attributes live in the low 16 bits; they
            # differ without changing the underlying Il2CppType identity.
            if pt[0] == ty[0] and self.il._type_enum(pt) == 0x11:
                hits.append(('method', mi))
        return hits[0] if len(hits) == 1 else None

    def _shared_static_signature_target(self, cands, arg_exprs):
        """Select one static owner from exact typed GPR arguments.

        Only a common, non-sret, non-generic ABI is considered. Unknown
        operands give no evidence; known operands must all fit a candidate's
        declared parameter types. Class arguments may match ancestors, so a
        derived operand cannot silently prefer an overload on that class.
        """
        if not cands or not arg_exprs:
            return None
        evidence = []
        strong = False
        for i, expr in enumerate(arg_exprs[:4]):
            if expr is None or expr._unk or expr.ty is None \
                    or not expr.text or expr.text in ('0', 'null', '_'):
                continue
            if expr.kind in ('ptr', 'klass', 'usage') \
                    or expr.text.startswith('&') or (expr.ty[1] >> 29) & 1:
                return None
            te = self.il._type_enum(expr.ty)
            if te not in (0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
                          0x08, 0x09, 0x0a, 0x0b, 0x0e, 0x11, 0x12,
                          0x18, 0x19):
                return None
            evidence.append((i, expr.ty))
            strong |= te in (0x0e, 0x11, 0x12)
        if not strong:
            return None
        methods = []
        arity = None
        for kind, mi in cands:
            if kind != 'method' or not 0 <= mi < len(self.meta.methods):
                return None
            method = self.meta.methods[mi]
            if not method.is_static or method.generic_container != -1 \
                    or not 1 <= method.param_count <= 4 \
                    or not 0 <= method.return_type < len(self.il.types) \
                    or self.il.returns_sret(self.il.types[method.return_type]):
                return None
            if arity is None:
                arity = method.param_count
            elif arity != method.param_count:
                return None
            params = list(self.meta.method_params(method))
            if len(params) != arity:
                return None
            ptys = []
            for p in params:
                if not 0 <= p.type < len(self.il.types):
                    return None
                pt = self.il.types[p.type]
                pte = self.il._type_enum(pt)
                if (pt[1] >> 29) & 1 or pte in (
                        0x0f, 0x10, 0x0c, 0x0d, 0x13, 0x15, 0x1c):
                    return None
                # Object accepts any reference (and boxed values), while
                # interface compatibility needs the implemented-interface
                # table. Neither may be excluded by an exact argument type.
                if pte == 0x12:
                    tds = getattr(self.meta, 'typedefs', ())
                    find_object = getattr(self.il, '_system_object_td', None)
                    object_td = find_object() if find_object is not None else None
                    if not 0 <= pt[0] < len(tds) \
                            or getattr(tds[pt[0]], 'flags', 0) & 0x20 \
                            or pt[0] == object_td:
                        return None
                ptys.append(pt)
            methods.append((kind, mi, ptys))
        if any(i >= arity for i, _ in evidence):
            return None
        hits = []
        for kind, mi, ptys in methods:
            matches = True
            for i, actual in evidence:
                expected = ptys[i]
                ate, pte = self.il._type_enum(actual), self.il._type_enum(expected)
                if ate == pte and actual[0] == expected[0]:
                    continue
                if ate == 0x12 and pte == 0x12:
                    chain = self.il.base_chain_tds(actual[0])
                    if expected[0] in chain:
                        continue
                matches = False
                break
            if matches:
                hits.append((kind, mi))
        return hits[0] if len(hits) == 1 else None

    def _shared_same_render_target(self, cands):
        """Collapse method-only twins that render identically.

        When every candidate is a non-generic MethodDef with the same
        rendered owner-qualified name, the same static/instance shape,
        the same exact parameter types and the same return, the emitted
        call text, arity trim and result type are identical no matter
        which row is picked -- choosing the first is unobservable, not
        a guess at identity. Constructors, generic methods, sret
        returns and mixed generic specs all decline; anything else
        keeps today's honest shared-body marker.
        """
        if not cands or len(cands) < 2:
            return None
        names = set()
        sigs = set()
        first = None
        for kind, mi in cands:
            if kind != 'method' or not 0 <= mi < len(self.meta.methods):
                return None
            m = self.meta.methods[mi]
            if m.name in ('.ctor', '.cctor') or m.generic_container != -1:
                return None
            if not 0 <= m.declaring < len(self.meta.typedefs):
                return None
            if not 0 <= m.return_type < len(self.il.types):
                return None
            if self.il.returns_sret(self.il.types[m.return_type]):
                return None
            nm = self._info_name(('method', mi))
            if nm is None:
                return None
            names.add(nm)
            if len(names) > 1:
                return None
            try:
                ptypes = tuple(p.type for p in self.meta.method_params(m))
            except Exception:
                return None
            sigs.add((m.name, m.is_static, ptypes, m.return_type))
            if len(sigs) > 1:
                return None
            if first is None:
                first = ('method', mi)
        if len(names) != 1 or len(sigs) != 1:
            return None
        return first

    def _shared_sret_receiver_target(self, cands, arg_exprs):
        """Prove the two-pointer Win64 shared-body family, never from RCX.

        RCX is the return buffer, RDX the receiver (or a static pointer
        parameter). Every owner must return a *known*, equally-sized sret
        value and consume exactly that one source pointer. A unique exact
        pointee identity then selects the owner. Unknown/generic layouts,
        by-value statics and duplicate matches keep the shared marker.
        Stack LEAs carry their type in slot_types, not in Expr.ty.
        """
        if not cands or len(arg_exprs) < 2:
            return None
        buf, source = arg_exprs[:2]
        for arg in (buf, source):
            if arg is None or arg._unk or arg.kind in ('klass', 'usage') \
                    or not (arg.text or '').startswith('&') \
                    or not _REFARG_RX.fullmatch(arg.text[1:]):
                return None
        tok = source.text[1:]
        evidence = [source.ty, getattr(self, 'slot_types', {}).get(tok),
                    getattr(self, '_type_hints', {}).get(tok)]
        keys = {(ty[0], self.il._type_enum(ty)) for ty in evidence if ty is not None}
        if len(keys) != 1:
            return None
        actual = next(iter(keys))
        if actual[1] not in (0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
                             0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x11):
            return None
        hits, sizes = [], set()
        for kind, mi in cands:
            if kind != 'method' or not 0 <= mi < len(self.meta.methods):
                return None
            method = self.meta.methods[mi]
            if method.generic_container != -1 \
                    or not 0 <= method.declaring < len(self.meta.typedefs) \
                    or not 0 <= method.return_type < len(self.il.types):
                return None
            owner = self.meta.typedefs[method.declaring]
            if owner.generic_container != -1:
                return None
            rt = self.il.types[method.return_type]
            if self.il._type_enum(rt) != 0x11 or not self.il.returns_sret(rt):
                return None
            size = self.il.value_type_size(rt[0])
            if size is None or size <= 0:
                return None
            sizes.add(size)
            if len(sizes) != 1:
                return None
            params = list(self.meta.method_params(method))
            if method.is_static:
                if method.param_count != 1 or len(params) != 1 \
                        or not 0 <= params[0].type < len(self.il.types):
                    return None
                pt = self.il.types[params[0].type]
                if (pt[1] >> 29) & 1:
                    pointee = (pt[0], pt[1] & ~(1 << 29))
                elif self.il._type_enum(pt) in (0x0f, 0x10):
                    pointee = self.il.type_from_ptr(pt[0])
                else:
                    return None
                if pointee is None or self.il._type_enum(pointee) not in (
                        0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
                        0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x11):
                    return None
                expected = (pointee[0], self.il._type_enum(pointee))
            else:
                if method.param_count != 0 or params or not owner.is_valuetype:
                    return None
                expected = (method.declaring, 0x11)
            if expected == actual:
                hits.append((kind, mi))
        return hits[0] if len(hits) == 1 else None

    def _legacy_shared_receiver_chain(self, recv_td):
        """The pre-Review-84 chain used by the broad shared-call heuristic.

        IL2CPP_TYPE_OBJECT support completes base_chain_tds, but System.Object
        was absent from derived receivers when that heuristic was designed.
        Keep that old specificity here; constructor proof uses the complete
        chain separately. An actual System.Object receiver still retains it.
        """
        if recv_td is None:
            return set()
        chain = set(self.il.base_chain_tds(recv_td))
        find_object = getattr(self.il, '_system_object_td', None)
        object_td = find_object() if find_object is not None else None
        if object_td is not None and recv_td != object_td:
            chain.discard(object_td)
        return chain

    def _shared_object_receiver_target(self, cands, recv):
        """Resolve Object's method only when every other owner is excluded.

        The broad receiver heuristic omits Object because it would make an
        unrelated typed receiver look like a match. Here the full candidate
        set is checked: each owner has the same parameterless instance ABI,
        and exactly one belongs to the receiver's complete base chain.
        """
        if recv is None or recv._unk or recv.ty is None or not cands:
            return None
        if (recv.ty[1] >> 29) & 1 or self.il._type_enum(recv.ty) != 0x12:
            return None
        td = self._td_of(recv.ty)
        find_object = getattr(self.il, '_system_object_td', None)
        object_td = find_object() if find_object is not None else None
        if td is None or object_td is None or td == object_td:
            return None
        chain = set(self.il.base_chain_tds(td))
        if object_td not in chain:
            return None
        hits = []
        for kind, mi in cands:
            if kind != 'method' or not 0 <= mi < len(self.meta.methods):
                return None
            method = self.meta.methods[mi]
            if method.is_static or method.param_count != 0 or (
                    method.generic_container != -1):
                return None
            if not 0 <= method.return_type < len(self.il.types):
                return None
            if self.il.returns_sret(self.il.types[method.return_type]):
                return None
            if method.declaring in chain:
                hits.append((kind, mi))
        if len(hits) == 1 and self.meta.methods[hits[0][1]].declaring == object_td:
            return hits[0]
        return None

    def _shared_value_receiver_target(self, cands, recv):
        """Use an exact stack pointee to distinguish folded value-type getters.

        A stack LEA has no Expr.ty; its slot retains the value type. Every
        candidate must use RCX as an instance receiver (never a static
        argument or sret buffer). A MethodSpec with the same declaring
        TypeDef blocks selection until its instantiation is proved.
        """
        if recv is None or recv._unk or recv.kind != 'ptr' \
                or not (recv.text or '').startswith('&') \
                or not _REFARG_RX.fullmatch(recv.text[1:]):
            return None
        tok = recv.text[1:]
        evidence = (recv.ty, getattr(self, 'slot_types', {}).get(tok),
                    getattr(self, '_type_hints', {}).get(tok))
        keys = {(ty[0], self.il._type_enum(ty))
                for ty in evidence if ty is not None}
        if len(keys) != 1:
            return None
        td, enum = next(iter(keys))
        if enum != 0x11 or not 0 <= td < len(self.meta.typedefs) \
                or not self.meta.typedefs[td].is_valuetype \
                or self.meta.typedefs[td].generic_container != -1:
            return None
        hits = []
        for candidate in cands:
            kind, index = candidate
            if kind == 'method':
                mi = index
            elif kind == 'generic':
                specs = getattr(self.il, 'method_specs', ())
                if not 0 <= index < len(specs):
                    return None
                mi = specs[index][0]
            else:
                return None
            if not 0 <= mi < len(self.meta.methods):
                return None
            method = self.meta.methods[mi]
            if method.is_static or not 0 <= method.return_type < len(self.il.types):
                return None
            rty = (self.il.candidate_return_type(candidate)
                   if kind == 'generic' else self.il.types[method.return_type])
            if rty is None or self.il.returns_sret(rty):
                return None
            if method.declaring == td:
                if kind != 'method' or method.generic_container != -1 \
                        or method.param_count != 0:
                    return None
                hits.append(candidate)
        return hits[0] if len(hits) == 1 else None

    def _array_receiver_td(self, ty):
        """System.Array typedef for an SZARRAY/ARRAY receiver type.

        `_td_of` maps only CLASS/VALUETYPE/OBJECT/GENERICINST, so an
        array-typed receiver (e.g. a `byte[]` field home) never reaches
        the chain filter. Arrays have no subclasses and Array owns
        their instance dispatch, so the Array typedef roots the chain;
        rank and element openness cannot change which Clone/CopyTo body
        runs. Byref markers, non-array types, and a missing/ambiguous
        Array row decline to None.
        """
        if ty is None or (ty[1] >> 29) & 1:
            return None
        if self.il._type_enum(ty) not in (0x1d, 0x14):
            return None
        find = getattr(self.il, '_system_array_td', None)
        return find() if find is not None else None

    def _shared_parameterless_ctor_target(self, cands, recv):
        """Resolve a folded zero-argument constructor from exact identity.

        A typed `this` is accepted only while lifting that type's constructor,
        and only ancestor owners are eligible. A fresh allocation must be the
        exact Expr minted by il2cpp_object_new. Candidate methods and generic
        specs are both examined: any constructor on the eligible chain with a
        different ABI blocks the proof, and a generic match blocks false
        uniqueness. Only one concrete, closed MethodDef can win.
        """
        if not cands or recv is None or recv._unk or recv.kind != 'obj' \
                or recv.ty is None or ((recv.ty[1] >> 29) & 1):
            return None
        is_this = recv.text == 'this'
        allocation = getattr(recv, '_alloc', None)
        is_fresh = bool(allocation and re.fullmatch(r'new .+\(\)', allocation))
        if not is_this and not is_fresh:
            return None
        te = self.il._type_enum(recv.ty)
        if te not in (0x12, 0x15, 0x1c):
            return None
        recv_td = self._td_of(recv.ty)
        if recv_td is None or not 0 <= recv_td < len(self.meta.typedefs) \
                or self.meta.typedefs[recv_td].is_valuetype:
            return None
        chain = self.il.base_chain_tds(recv_td)
        if not chain or chain[0] != recv_td:
            return None
        if is_this:
            caller = getattr(self, '_current_method', None)
            current_td = getattr(self, '_current_td', None)
            if caller is None or caller.name != '.ctor' or caller.is_static \
                    or caller.declaring != recv_td \
                    or current_td is None or current_td.index != recv_td:
                return None
            allowed = set(chain[1:])
        else:
            allowed = set(chain)
        if not allowed:
            return None

        matches = []
        for candidate in cands:
            kind, index = candidate
            if kind == 'method':
                mi = index
            elif kind == 'generic':
                specs = getattr(self.il, 'method_specs', ())
                if not 0 <= index < len(specs):
                    return None
                mi = specs[index][0]
            else:
                return None
            if not 0 <= mi < len(self.meta.methods):
                return None
            method = self.meta.methods[mi]
            if method.name != '.ctor' or method.declaring not in allowed:
                continue
            if method.is_static or method.param_count != 0 \
                    or not 0 <= method.return_type < len(self.il.types) \
                    or self.il._type_enum(self.il.types[method.return_type]) != 0x01:
                return None
            matches.append((candidate, method))
        if len(matches) != 1 or matches[0][0][0] != 'method':
            return None
        candidate, method = matches[0]
        owner = self.meta.typedefs[method.declaring]
        if method.generic_container != -1 or owner.generic_container != -1:
            return None
        return candidate

    def _constructor_initializer_kind(self, callee, recv):
        """Return `this`/`base` only for a proved current-constructor call."""
        caller = getattr(self, '_current_method', None)
        current_td = getattr(self, '_current_td', None)
        if caller is None or current_td is None or caller.name != '.ctor' \
                or caller.is_static or callee.name != '.ctor' or callee.is_static \
                or recv is None or recv._unk or recv.text != 'this':
            return None
        recv_td = self._td_of(recv.ty)
        if recv_td is None or recv_td != caller.declaring \
                or current_td.index != caller.declaring:
            return None
        if callee.declaring == caller.declaring:
            return 'this'
        chain = self.il.base_chain_tds(recv_td)
        return 'base' if callee.declaring in chain[1:] else None

    def _complete_fresh_constructor(self, recv, ctor_args):
        """Turn this allocation Expr's `new T()` into `new T(args)` once."""
        if recv is None or recv._unk or recv.kind != 'obj':
            return False
        allocation = getattr(recv, '_alloc', None)
        if not allocation or not re.fullmatch(r'new .+\(\)', allocation):
            return False
        completed = allocation[:-1] + ', '.join(ctor_args) + ')'
        current = recv.text
        if getattr(self, 'dry', False):
            recv.text = self.new_var()
            recv._prec = None
            recv._alloc = None
            return True
        if current == allocation:
            recv.text = completed
            recv._prec = None
            recv._alloc = None
            self._bind(recv)
            return True
        if not _BARE_TOKEN_RX.fullmatch(current):
            return False

        old_line = 'var %s = %s;' % (current, strip_outer(allocation))
        new_line = 'var %s = %s;' % (current, strip_outer(completed))
        dp = recv._defpos
        dblk = dp[0] if dp is not None else getattr(self.out, 'block', None)
        sink = self._stmt_sink(dblk)
        found = []
        for i, statement in enumerate(sink):
            text = statement if type(statement) is str \
                else (statement[1] if type(statement) is tuple else None)
            if text == old_line:
                found.append(i)
        if len(found) != 1:
            return False
        i = found[0]
        statement = sink[i]
        sink[i] = new_line if type(statement) is str \
            else (statement[0], new_line, statement[2])
        recv._alloc = None
        return True

    def _array_allocation(self, text, ty, ip, asm):
        """Give one native allocation one identity, even for short new T[n].

        The generic use-binder deliberately skips short/non-call text; it
        must not duplicate an allocation at every element store or Concat.
        Emit at the allocation instruction, not at a later text-matched use.
        Cyclic/indirect structured bodies retain the old representation until
        dominance, per-iteration identity and alias lifetime are proved. Correct
        loop-header placement alone does not establish those properties.
        """
        if getattr(self, '_array_allocation_loop_guard',
                   getattr(self, '_memory_rhs_loop_guard', False)):
            # the loop guard keeps the old full-text representation (no
            # per-allocation temp until per-iteration identity is proved),
            # but the value is still this exact newarr on every execution,
            # so the exactness proof rides along identically.
            ge = Expr(text, ty, 'arr')
            ge._newarr = True
            return ge
        name = self.new_var()
        if ty is not None and not getattr(self, 'dry', False):
            self._var_types[name] = ty
        self.emit(ip, 'var %s = %s;' % (name, text), asm)
        e = Expr(name, ty, 'arr')
        # exactness proof for the element-class fold (`_elem_klass_name`):
        # a same-method newarr fixes the array's runtime klass to exactly
        # E[], so [klass+0x40] is provably E's klass. Array covariance lets
        # a param/field/static/`as`-refined E[] hold a D[] at runtime, so
        # only an allocation carries this flag. `_copy_expr`/`_kill_one`
        # preserve it because both freeze the identical value under a new
        # name; any other value drops it and the site keeps today's marker.
        e._newarr = True
        return e

    def _call_name(self, target) -> str:
        # MSVC folds identical bodies, and IL2CPP shares one body across
        # generic instantiations, so an address can carry more than one true
        # owner (measured on the real target: 6.3% of direct-method addrs,
        # 18% of generic addrs). Picking one and printing it as fact is how
        # `Guid.cs` ends up calling `ReadOnlySpan<Obi.BurstCollisionMaterial>`
        # -- receiver-blind here, so stay honest instead of guessing; `_call`
        # tries harder once it knows the receiver's type (see below).
        cands = self.il.addr_candidates.get(target)
        info = cands[0] if cands and len(cands) == 1 else None
        ambiguous = bool(cands) and len(cands) > 1
        if info is None and not ambiguous:
            info = self.il.addr_to_method.get(target)
        if info:
            nm = self._info_name(info)
            if nm is not None:
                return nm
        if target in self.il.bin.exports:
            return self.il.bin.exports[target]
        nm = self.rt_names.get(target)
        if nm is not None:
            return nm
        if target and self._is_class_init_twin(target):
            self.rt_names[target] = 'il2cpp_runtime_class_init'
            return 'il2cpp_runtime_class_init'
        try:
            _aan = self._array_addr_name(target)
        except Exception:
            _aan = None
        if _aan is not None:
            return _aan
        if self.rt_init_meta and target == self.rt_init_meta:
            return 'il2cpp_codegen_initialize_runtime_metadata'
        tgt = self._thunk_final(target) if target else None
        if tgt is not None and tgt != target:
            if tgt in self.il.bin.exports:
                return self.il.bin.exports[tgt]
            nm = self.rt_names.get(tgt)
            if nm is not None:
                return nm
            cf = self.il.addr_candidates.get(tgt)
            if cf and len(cf) == 1:
                nf = self._info_name(cf[0])
                if nf is not None:
                    return nf
        if ambiguous:
            return 'sub_%x/*shared body, %d candidates*/' % (target, len(cands))
        return 'sub_%x' % target

    _IDENTITY_PURE_ARG = re.compile(
        r'(?:&)?[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*|-?(?:0x[0-9a-fA-F]+|[0-9]+)')

    def _shared_identity_value(self, target, cands, arg_exprs, xmm):
        """Prove a shared native leaf copies RCX to RAX without effects.

        Dropped register values must be pure because their expressions may
        not have been materialized yet. The result itself is bound at the
        call instruction, preserving the copied value across later writes.
        This proves machine semantics only; it never selects a MethodDef.
        """
        if target is None or not cands or len(cands) < 2 \
                or not getattr(self.bin, 'is_exec_va', lambda _va: False)(target):
            return None
        cache = getattr(self, '_shared_identity_cache', None)
        if cache is None:
            cache = self._shared_identity_cache = {}
        if target not in cache:
            cache[target] = self.bin.read(target, 4) == b'\x48\x8b\xc1\xc3'
        if not cache[target] or not arg_exprs:
            return None
        value = arg_exprs[0]
        if value is None or value._unk or value.kind not in (
                'obj', 'int', 'str', 'arr', 'local', '?') \
                or not value.text or value.text.startswith('&') \
                or not self._IDENTITY_PURE_ARG.fullmatch(value.text):
            return None
        for extra in list(arg_exprs[1:4]) + [e for _, e in xmm]:
            if extra is None or extra._unk:
                continue
            if not extra.text or not self._IDENTITY_PURE_ARG.fullmatch(extra.text):
                return None
        return value

    def _shared_string_equality(self, cands, arg_exprs, xmm):
        """Prove the common behavior of the exact System.String aliases.

        Both metadata owners point to the same native body and declare the
        same (string, string) -> bool ABI. The operator does not identify
        the source spelling or select one MethodDef.
        """
        if not cands or len(cands) != 2 or len(arg_exprs) < 2:
            return False
        names = set()
        owner_idx = None
        for kind, mi in cands:
            if kind != 'method' or not 0 <= mi < len(self.meta.methods):
                return False
            method = self.meta.methods[mi]
            if (not method.is_static or method.param_count != 2
                    or method.generic_container != -1
                    or not 0 <= method.declaring < len(self.meta.typedefs)
                    or not 0 <= method.return_type < len(self.il.types)):
                return False
            if owner_idx is None:
                owner_idx = method.declaring
            elif owner_idx != method.declaring:
                return False
            owner = self.meta.typedefs[method.declaring]
            ret = self.il.types[method.return_type]
            if ((owner.namespace, owner.name) != ('System', 'String')
                    or self.il._type_enum(ret) != 0x02
                    or (ret[1] >> 29) & 1):
                return False
            params = list(self.meta.method_params(method))
            if len(params) != 2:
                return False
            for param in params:
                if not 0 <= param.type < len(self.il.types):
                    return False
                pty = self.il.types[param.type]
                if self.il._type_enum(pty) != 0x0e or (pty[1] >> 29) & 1:
                    return False
            names.add(method.name)
        if names != {'Equals', 'op_Equality'}:
            return False
        for expr in arg_exprs[:2]:
            if (expr is None or expr._unk or not expr.text
                    or expr.kind in ('ptr', 'klass', 'usage')
                    or expr.text.startswith('&')):
                return False
            if expr.text in ('0', 'null'):
                continue
            if (expr.kind == 'str' and expr.text.startswith('"')
                    and expr.text.endswith('"')):
                continue
            if (expr.ty is None or (expr.ty[1] >> 29) & 1
                    or self.il._type_enum(expr.ty) != 0x0e):
                return False
        for extra in list(arg_exprs[2:4]) + [e for _, e in xmm]:
            if (extra is not None and not extra._unk
                    and (not extra.text
                         or not self._IDENTITY_PURE_ARG.fullmatch(extra.text))):
                return False
        return True

    def _nullary_interface_dispatch(self, target, arg_exprs):
        """Recognize the Win64 interface-offset search and shared tail call.

        The template fixes slot/type/receiver in RCX/RDX/R8. Only the slow
        lookup's relative call displacement varies; all loads, branches,
        slot arithmetic and both paths to invoke_impl must match. A body
        admitted by `_iface_dispatch_arity` as a nullary member (same
        arithmetic, no R9 read, different prologue -- 0x180002210 and
        0x180002380 on the fixture) takes that structural proof instead of
        the byte template.
        """
        if target is None or len(arg_exprs) < 3:
            return None
        slot, iface, receiver = arg_exprs[:3]
        if slot is None or iface is None or receiver is None:
            return None
        offset = _int_lit(slot.text)
        if offset is None or not 0 <= offset <= 0xffff \
                or iface.kind != 'klass' or not iface.text.startswith('typeof('):
            return None
        if self._iface_arity(target) != 0:
            prefix = bytes.fromhex(
                '48895c2408574883ec20498b184533c9498bf8440fb7932e010000'
                '66453bca73264c8b9bb00000000f1f840000000000410fb7c14803c0'
                '493914c3742d6641ffc166453bca72e9440fb7c1488bcfe8')
            suffix = bytes.fromhex(
                '4c8b00488bcf488b5008488b5c24304883c4205f49ffe0410fb7d1'
                '4803d20fb7c9418b44d30803c1489848c1e0044805380100004803c3ebc7')
            code = self.bin.read(target, len(prefix) + 4 + len(suffix))
            if code is None or not code.startswith(prefix) \
                    or code[len(prefix) + 4:] != suffix:
                return None
        td_index = self._td_of(iface.ty)
        if td_index is None:
            return None
        td = self.meta.typedefs[td_index]
        if not td.flags & 0x20 or not 0 <= offset < td.method_count:
            return None
        mi = td.method_start + offset
        method = self.meta.methods[mi]
        if method.is_static or method.param_count \
                or not 0 <= method.return_type < len(self.il.types):
            return None
        rty = self.il.types[method.return_type]
        # `IEnumerable<T>.GetEnumerator()` returns `IEnumerator<T>`: close
        # the declaring interface's VAR/MVAR from the generic instantiation
        # the call site named. Printing the open tuple would render
        # `IEnumerator_1<T>` with no T in scope; an unclosable return keeps
        # the honest `sub_` fallback instead.
        closed_key = getattr(self.il, '_closed_type_key', None)
        if closed_key is not None and closed_key(rty) is None:
            class_args = None
            gen_fn = getattr(self, '_generic_class_args', None)
            if gen_fn is not None:
                try:
                    class_args = gen_fn(iface.ty)
                except Exception:
                    class_args = None
            subst = getattr(self.il, '_subst_closed', None)
            rty = subst(rty, class_args, None) if class_args and subst else None
        if rty is None or not self.il._return_abi_is_known(rty) \
                or self.il.returns_sret(rty):
            return None
        return mi, receiver, rty

    def _iface_ty_match(self, a, b):
        """Exact-or-closed type equality for the typed-unknown R9 proof.

        A merged `default`-poisoned local (kind '?') may still carry the
        exact declared type; accept it only on proof, never on text.
        """
        try:
            if a is not None and b is not None and a == b:
                return True
            ck = getattr(self.il, '_closed_type_key', None)
            if ck is None:
                return False
            ka, kb = ck(a), ck(b)
            return ka is not None and ka == kb
        except Exception:
            return False

    def _param_interface_dispatch(self, target, arg_exprs):
        """(mi, receiver, rty[, r9arg]) for a forwarded interface call.

        The A-family twin of `_nullary_interface_dispatch`: same slot /
        typeof / receiver triple in RCX/RDX/R8, plus the managed
        argument the helper forwards through R9 (proved live on entry
        by `_iface_dispatch_arity`, never by address). A zero-parameter
        target drops the R9 spray the same way arity trimming drops
        unread registers. Multi-parameter targets recover params 1..
        from the Win64 stack homes [rsp+0x20+8k] behind per-parameter
        GPR-class, width and spelling gates. Byref parameters,
        non-GPR R9 values and unclosable returns keep the honest
        `sub_` fallback. A different runtime keeps `sub_` too.
        """
        if target is None or len(arg_exprs) < 4:
            return None
        slot, iface, receiver = arg_exprs[:3]
        r9e = arg_exprs[3]
        if slot is None or iface is None or receiver is None or r9e is None:
            return None
        offset = _int_lit(slot.text)
        if offset is None or not 0 <= offset <= 0xffff \
                or iface.kind != 'klass' or not iface.text.startswith('typeof('):
            return None
        if self._iface_arity(target) != 1:
            return None
        td_index = self._td_of(iface.ty)
        if td_index is None:
            return None
        td = self.meta.typedefs[td_index]
        if not td.flags & 0x20 or not 0 <= offset < td.method_count:
            return None
        mi = td.method_start + offset
        method = self.meta.methods[mi]
        if method.is_static or not 0 <= method.return_type < len(self.il.types):
            return None
        # Zero-parameter targets never consult the parameter table
        # (the landed arity-0 path predates it); consistency between
        # the table and the declared arity binds only param >= 1.
        _ps = []
        if method.param_count >= 1:
            try:
                _ps = self.meta.method_params(method)
            except Exception:
                return None
            if len(_ps) != method.param_count:
                return None
        try:
            _pts = [self.il.types[p.type] if 0 <= p.type < len(self.il.types) else None
                    for p in _ps]
        except Exception:
            return None
        if any(t is None or ((t[1] >> 29) & 1) for t in _pts):
            return None
        # Word-sized GPR parameter types only: floats travel in XMM (a
        # stack home holds shadow garbage, not the argument) and structs
        # span homes. The arity-1 path below keeps its landed gates;
        # the class allowlist binds only the new multi-parameter shape.
        _GPR_TES = (0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09,
                    0x0a, 0x0b, 0x0e, 0x0f, 0x12, 0x14, 0x1b, 0x1c, 0x1d)
        _STK_TES = {0x08: 4, 0x09: 4, 0x0a: 8, 0x0b: 8, 0x0e: 8, 0x0f: 8,
                    0x12: 8, 0x14: 8, 0x1b: 8, 0x1c: 8, 0x1d: 8}
        if method.param_count >= 1:
            try:
                r9t = (r9e.text or '').strip()
            except Exception:
                return None
            if not r9t or r9t in ('_', '?'):
                return None
            if getattr(r9e, 'kind', None) not in ('obj', 'int', 'ptr', 'arr', 'str', 'local'):
                # A merged `default`-poisoned local keeps the exact
                # declared type under kind '?': accept it only when the
                # type closes to the parameter's own type (mi 104027
                # `action1` vs `System.Action`), never on text alone.
                if getattr(r9e, 'kind', None) != '?' \
                        or not self._iface_ty_match(getattr(r9e, 'ty', None), _pts[0]):
                    return None
            if method.param_count >= 2:
                try:
                    _te0 = self.il._type_enum(_pts[0])
                except Exception:
                    return None
                if _te0 not in _GPR_TES:
                    return None
        _stack_args = []
        if method.param_count >= 2:
            try:
                _rsp = self.rsp_delta
            except Exception:
                return None
            # Tile proving records phi-source types in the ambient
            # hint tables; a speculative recovery must not leak
            # those into statements the twin never names -- snapshot
            # and restore around the loop, resolve or decline.
            _hint_mark = None
            try:
                _hint_mark = (dict(self._type_hints),
                              dict(getattr(self, '_aggregate_phi_types', None) or {}))
            except Exception:
                _hint_mark = None
            try:
                for _i in range(1, method.param_count):
                    try:
                        _te = self.il._type_enum(_pts[_i])
                    except Exception:
                        return None
                    _w = _STK_TES.get(_te)
                    if _w is None:
                        return None
                    try:
                        _sa = self._stack_piece(_rsp + 0x20 + 8 * (_i - 1), _w, _pts[_i])
                    except Exception:
                        return None
                    if _sa is None:
                        return None
                    try:
                        _sat = (_sa.text or '').strip()
                    except Exception:
                        return None
                    if not _sat or _sat in ('_', '?'):
                        return None
                    _sak = getattr(_sa, 'kind', None)
                    if _sak not in ('obj', 'int', 'ptr', 'arr', 'str', 'local'):
                        # Stack tiles of bare constants carry kind 'bits':
                        # accept only a provable integer-literal spelling.
                        if not (_sak == 'bits' and _int_lit(_sat) is not None):
                            return None
                    _stack_args.append(_sa)
            finally:
                if _hint_mark is not None:
                    try:
                        self._type_hints.clear()
                        self._type_hints.update(_hint_mark[0])
                        _pht = getattr(self, '_aggregate_phi_types', None)
                        if _pht is not None:
                            _pht.clear()
                            _pht.update(_hint_mark[1])
                    except Exception:
                        pass
        rty = self.il.types[method.return_type]
        closed_key = getattr(self.il, '_closed_type_key', None)
        if closed_key is not None and closed_key(rty) is None:
            class_args = None
            gen_fn = getattr(self, '_generic_class_args', None)
            if gen_fn is not None:
                try:
                    class_args = gen_fn(iface.ty)
                except Exception:
                    class_args = None
            subst = getattr(self.il, '_subst_closed', None)
            rty = subst(rty, class_args, None) if class_args and subst else None
        if rty is None or not self.il._return_abi_is_known(rty) \
                or self.il.returns_sret(rty):
            return None
        # Single-field struct returns flow whole unless a consumer
        # provably wants the lane: struct-typed declarations fold
        # through F2-C1 and struct-typed call args through F2-C2,
        # while int/ulong/object consumers keep lane spellings.
        # Unreadable typedefs/chains stay declined; enums flow
        # cleanly (mi 104498 `ProcessRegularUpdates`).
        try:
            _rte = self.il._type_enum(rty)
        except Exception:
            _rte = None
        if _rte in (0x11, 0x15):
            try:
                _rtd = self._td_of(rty)
                _rtdo = self.meta.typedefs[_rtd] if _rtd is not None else None
                _rfm = self.il.instance_field_chain(_rtd) if _rtd is not None else None
            except Exception:
                _rtdo, _rfm = None, None
            if _rtdo is None or _rfm is None:
                return None
        if method.param_count == 0:
            return mi, receiver, rty
        if method.param_count == 1:
            return mi, receiver, rty, r9e
        return (mi, receiver, rty, r9e) + tuple(_stack_args)

    def _wb_operands(self, args, arg_exprs):
        """`il2cpp_codegen_write_barrier(&field, value)` -> (lvalue text,
        rvalue text) for the assignment it really is. Shared between `_call`
        (the ordinary case) and the tail-jmp handler (a write barrier can be
        the very last thing a void method does, compiled as a tail call --
        5,797 sites tree-wide render the raw helper call unconverted without
        this, one of the "spaghetti" complaints a bare tail-call render
        produces)."""
        dst = args[0][1:] if args[0].startswith('&') else args[0]
        src2 = args[1] if len(args) > 1 else '?'
        # a constant-folded null-base address (`16`, `(16)`) is not a
        # variable: `16 = v;` never parses and `*16 = v;` breaks the
        # tree-sitter grammar. Spell it as the deref the plain-store
        # twin uses (`((byte*)16)[0]` parses); the twin comparison
        # canonicalizes primitive casts, so the duplicate still drops.
        mnum = re.fullmatch(r'\(?((?:0[xX][0-9a-fA-F]+|\d+))\)?', dst or '')
        if mnum:
            return '((byte*)%s)[0]' % mnum.group(1), src2
        # storing a bare temp into a typed location types the temp -- the
        # write-barrier idiom is a SEPARATE emit path from _write_mem (a
        # reference-typed store almost always compiles through the barrier,
        # not a plain mov), so it needs its own copy of the same hint: the
        # address arg's Expr carries its pointee's type (the "address-of
        # expression carries its pointee's type" convention _bind
        # documents), which is usually far more useful than a shared/
        # unresolved generic return type on the value being stored
        # (GetComponent<T>() and friends -- fix 21f's other half).
        dst_e = arg_exprs[0] if arg_exprs else None
        if dst_e is not None and isinstance(dst_e.ty, tuple) \
                and not _is_unresolved_gp(dst_e.ty) and _BARE_TOKEN_RX.match(src2):
            self._type_hints.setdefault(src2, dst_e.ty)
        # the lvalue must read exactly like _mem_lvalue's render of the
        # same write: a paren/address composite gets the leading `*` (the
        # plain store `mov [r+0x20],v` prints `*(r + 0x20) = v;`, and the
        # compiled barrier is its GC twin). Without this the twin renders
        # `(r + 0x20) = v;` -- invalid C#, and the plain/barrier dedup
        # in `_call` misses.
        # a bare value-typed address register targets the struct's
        # first field (raw disp 0, no header) -- fold it so the
        # lvalue reads like the paired plain store and the twin
        # dedup in _wb_finish fires (`this` -> `this.this_`)
        if dst_e is not None and re.match(r'[A-Za-z_$][\w$]*$', dst) and self._recv_is_vt(dst_e):
            fe = self._field_expr(dst_e, 0, 8)
            if ('.' in fe.text or '->' in fe.text) \
                    and fe.kind in ('obj', 'arr', 'str'):
                dst = fe.text
        if _paren_spans_all(dst):
            dst = '*' + dst
        elif re.search(r'[+\-*/%]', dst) and not re.match(r'[\w$.]+$', dst):
            # an address composite (or a PARTIAL deref/paren like
            # `*(x) + i*8 + 0x20` or `(x << 4) + i`, whose `*`/parens cover
            # only the first term) must read as the WHOLE write:
            # `*(...) = v;`
            if not _deref_spans_all(dst):
                dst = '*(%s)' % dst
        # single-field whole store through a barrier (F2-S2 twin of the
        # plain fold): `X.f` displays as `X` under the same closed-type
        # proof. Barrier writes are pointer-sized, so the struct must be
        # 8 bytes; the field name (not a displacement) selects the single
        # field. Dedups in `_wb_finish` then see the same spelling as a
        # paired plain store instead of a permanent twin.
        try:
            _mx = re.fullmatch(r'([A-Za-z_]\w*)\.([A-Za-z_]\w*)', (dst or '').strip())
            if _mx is not None and len(arg_exprs) > 1:
                _ve = arg_exprs[1]
                _rty = _ve.ty if _ve is not None else None
                _hty = None
                for _mp in ('_var_types', '_type_hints', 'slot_types'):
                    try:
                        _mm = getattr(self, _mp, None)
                        _hty = _mm.get(_mx.group(1)) if _mm else None
                    except Exception:
                        _hty = None
                    if isinstance(_hty, tuple):
                        break
                if isinstance(_hty, tuple) and isinstance(_rty, tuple):
                    _xtd = self._td_of(_hty) if hasattr(self, '_td_of') else None
                    _xtdo = self.meta.typedefs[_xtd] \
                        if _xtd is not None and 0 <= _xtd < len(self.meta.typedefs) else None
                    if _xtdo is not None:
                        _ch = self.il.instance_field_chain(_xtd) \
                            if _xtd is not None else None
                        try:
                            _sz = self.il.value_type_size(_xtd)
                        except Exception:
                            _sz = None
                        if _sz == 8:
                            _got = self._single_field_store(
                                dst, _hty, _rty, 8, 8, 0,
                                _ch or {},
                                bool(getattr(_xtdo, 'is_enum', False)),
                                bool(getattr(_xtdo, 'is_valuetype', False)))
                            if _got is not None:
                                dst = _got
        except Exception:
            pass
        return dst, src2

    def _wb_finish(self, ip, dst, src2, asm, tail=False):
        """Emit (or dedup-skip) the assignment statement `_wb_operands`
        built, shared by every write-barrier call site: ordinary (`_call`)
        and tail-jmp (the tail call can be the very last thing a void
        method does; `tail=True` closes it with `return;`)."""
        stmt = '%s = %s;' % (dst, src2)
        if self._last_stmt_text() == stmt:   # twin of the plain store
            if self.asm_comments and asm:
                self.emit(ip, '', asm)
            return
        # the plain store and its barrier twin can render the same address
        # differently (`v + i * 8 + 32` from the lea/add chain vs
        # `v + i*8 + 0x20` from the memory operand): compare a whitespace/
        # radix-normalized form so the twin still dedups
        if _norm_twin(self._last_stmt_text()) == _norm_twin(stmt):
            if self.asm_comments and asm:
                self.emit(ip, '', asm)
            return
        # a barrier whose target was written by the immediately preceding
        # store is the GC hook of THAT write: the reference store already
        # rendered (the paired value register is often clobbered -- xor
        # edx,edx sprays a junk `= 0;` twin). Skip it by lvalue, not by
        # value: the jump-address twin (same target, same value) landed in
        # the exact-text dedup above.
        last = self._last_stmt_text()
        if last is not None:
            lm = re.match(r'^(.*?) = .*;$', last)
            if lm is not None and _norm_twin(lm.group(1).strip()) == _norm_twin(dst):
                if self.asm_comments and asm:
                    self.emit(ip, '', asm)
                return
        self._kill_stale(dst)
        self.emit(ip, (stmt + ' return;') if tail else stmt, asm)

    def _kill_byref_slots(self, mi, rty, arg_exprs):
        """A byref parameter is a proved write through the passed address.
        Drop the slot's cached value so later reads reload instead of
        reusing the pre-call constant. Same slot walk as _hint_arg_types
        (GPR positions only -- byref is pointer-class, never float); the
        sret early-return fold does not reach here and keeps old behavior."""
        if not hasattr(self.il, '_sf_field_size'):
            return
        m2 = self.meta.methods[mi]
        trust = rty is None or self.il._type_enum(rty) != 0x15
        if not trust:
            return
        ri = 0 if m2.is_static else 1
        if self.il.returns_sret(rty):
            ri += 1
        for pi, p in enumerate(self.meta.method_params(m2)):
            pt = self.il.types[p.type] if 0 <= p.type < len(self.il.types) else None
            if pt is None:
                break
            bits = pt[1]
            if not ((bits >> 29) & 1) and ((bits >> 16) & 0xFF) != 0x10:
                continue
            slot = ri + pi
            if slot > 3 or slot >= len(arg_exprs):
                continue
            e = arg_exprs[slot]
            if e is None:
                continue
            off = getattr(e, '_stack_offset', None)
            if off is None:
                continue
            name = e.text[1:] if e.text.startswith('&') and _REFARG_RX.fullmatch(e.text[1:]) else None
            if name is None:
                for addr, nm in self.stack_map.items():
                    if addr == off:
                        name = nm
                        break
            if name is None:
                continue
            pointee = (pt[0], pt[1] & ~(1 << 29))
            size = self.il._sf_field_size(pointee, 0)
            if size is not None:
                self._stack_store(off, size, None)
            self.stack_values.pop(name, None)
            self._kill_stale(name)

    @staticmethod
    def _single_field_arg(arg_text, param_ty, param_byref, x_ty, chain, is_enum, is_valuetype=True):
        """Folded `X` for a single-field lane arg, else None (F2-C2).

        Pure decision: `X.f` becomes `X` when the parameter declares
        the same closed value type X resolves to, that type is a
        non-enum single-field valuetype struct, and f is the field.
        Everything else (byref, mismatched/unknown types, multi-field,
        enums, non-valuetype holders, non-`X.f` shapes) keeps today's
        spelling.
        """
        try:
            import re as _re
            m = _re.fullmatch(r'([A-Za-z_]\w*)\.([A-Za-z_]\w*)',
                               (arg_text or '').strip())
            if not m or param_byref:
                return None
            x, f = m.group(1), m.group(2)
            if not isinstance(x_ty, tuple) or x_ty != param_ty:
                return None
            if is_enum or not is_valuetype or not chain or len(chain) != 1:
                return None
            try:
                (_fo, (_fn, _fti)), = chain.items()
            except Exception:
                return None
            if _fn != f:
                return None
            return x
        except Exception:
            return None

    @staticmethod
    def _single_field_store(lv_text, lv_ty, rhs_ty, width, size, disp,
                            chain, is_enum, is_valuetype=True):
        """Folded `X` for a single-field whole store, else None (F2-S2).

        Pure decision: `X.f = Y` becomes `X = Y` when the holder and
        the RHS resolve to the same closed value type, that type is a
        non-enum single-field valuetype, f is its single field at the
        written displacement, and the access width covers the whole
        struct (size caller-proven, mirroring the C1 unanimity gate).
        Open holders decline via chain resolution at the call site
        (no chain, no fold). Everything else (partial stores,
        mismatched/unknown types, multi-field, enums, non-valuetypes,
        non-`X.f` shapes) keeps today's spelling.
        """
        try:
            import re as _re
            m = _re.fullmatch(r'([A-Za-z_]\w*)\.([A-Za-z_]\w*)',
                               (lv_text or '').strip())
            if not m:
                return None
            x, f = m.group(1), m.group(2)
            if not isinstance(lv_ty, tuple) or not isinstance(rhs_ty, tuple):
                return None
            if lv_ty != rhs_ty:
                return None
            if is_enum or not is_valuetype:
                return None
            if not chain or len(chain) != 1:
                return None
            try:
                (_fo, (_fn, _fti)), = chain.items()
            except Exception:
                return None
            if _fn != f:
                return None
            try:
                if disp + 0x10 != _fo:
                    return None
            except Exception:
                return None
            if size is None:
                return None
            try:
                if width != size:
                    return None
            except Exception:
                return None
            return x
        except Exception:
            return None

    @staticmethod
    def _bare_typeof_target(text):
        """Inner `T` of a whole-string `typeof(T)`, else None (slice 2).

        Pure string fence: blanks `"..."`/`'...'` spans (a quoted
        `typeof` inside a string literal must never shape-match),
        then walks parens from `typeof(` to its match. Fires only
        when the close paren ends the string (member/call wraps like
        `typeof(T).Get()` decline) and `T` is non-empty. Mirrors the
        dec-side `_fence_bare_typeof` walk without importing dec.
        """
        try:
            import re as _re
            s = text if isinstance(text, str) else ''
            if not s:
                return None
            muted = list(s)
            _q = None
            _i = 0
            while _i < len(s):
                ch = s[_i]
                if _q is None and ch in ('"', "'"):
                    _q = ch
                    muted[_i] = '#'
                elif _q is not None and ch == _q:
                    muted[_i] = '#'
                    _q = None
                elif _q is not None:
                    muted[_i] = '#'
                _i += 1
            if _q is not None:
                return None
            m = _re.match(r'typeof\s*\(', ''.join(muted))
            if not m:
                return None
            depth = 0
            for _j in range(m.end() - 1, len(s)):
                c = muted[_j]
                if c == '(':
                    depth += 1
                elif c == ')':
                    depth -= 1
                    if depth == 0:
                        if _j != len(s) - 1:
                            return None
                        inner = s[m.end():_j].strip()
                        return inner if inner else None
            return None
        except Exception:
            return None

    def _entry_live_call_args(self, target, gexprs, gtexts, xexprs):
        """Fix 132: positional argument texts for a plain `sub_` call,
        or None to keep the register spray.

        Position i carries RCX/RDX/R8/R9 when the callee reads that GPR
        on entry, XMM0-3 when it reads the XMM; the list ends at the last
        read position. A dead interior position (the callee provably
        never reads either register) renders `0`. Declines (None) when
        the callee has no proof, reads both registers of one position,
        or reads a register whose value the lifter does not hold.
        Never raises.
        """
        try:
            if target is None or self.il.addr_candidates.get(target) \
                    or target in self.bin.exports:
                return None
            sig = entry_live_args(self.il, target)
            if sig is None:
                return None
            n = max([i + 1 for i, k in enumerate(sig) if k] or [0])
            out = []
            for i in range(n):
                k = sig[i]
                if k == '':
                    out.append('0')
                elif k == 'g':
                    e = gexprs[i]
                    if e is None or e._unk or not gtexts[i] or gtexts[i] == '_':
                        return None
                    out.append(gtexts[i])
                elif k == 'x':
                    e = xexprs[i]
                    if e is None or e._unk or not e.text or not e.text.strip():
                        return None
                    # 132e: placeholder spellings (`GenericMethod#N`, a
                    # bare `?`) do not parse; keep the spray instead
                    if '#' in e.text or not _fp32_arg_ok(e.text):
                        return None
                    out.append(e.text)
                else:
                    return None
            return out
        except Exception:
            return None

    def _call(self, ins, asm):
        target = None
        self.ind_slot = None
        self.ic_mi = None
        self.delegate_mi = None
        self.delegate_recv = None
        self._call_class_args = None
        if ins.op0_kind == OpKind.NEAR_BRANCH64:
            target = ins.near_branch_target
            name = self._call_name(target)
        elif ins.op0_kind == OpKind.REGISTER:
            e = self.reg(reg_name(ins.op0_register))
            if e is not None and e.kind == 'vtmethod':
                name = 'VIRT_CALL'
                # `mov rax,[klass+0x138+16N]; call rax` -- the
                # vtmethod expr's own text carries the slot (its
                # recv the receiver); without this the site renders
                # `/*vtable slot None*/` and no arity bound applies
                mvt = re.search(r'\.vtable\[(\d+)\]$', e.text)
                if mvt is not None:
                    self.vt_recv_slot = int(mvt.group(1))
                    if getattr(e, 'recv', None) is not None:
                        self.vt_recv = e.recv
            elif e is not None and e.kind == 'fptr':
                name = e.text
                # fix 66: an icall thunk cell resolved to a real MethodDef
                self.ic_mi = e._mi
            elif e is not None and e.kind == 'delegate_impl' \
                    and getattr(e, 'recv', None) is not None:
                self.delegate_recv = e.recv
                self.delegate_mi = self._delegate_invoke_method(e.recv.ty)
                self._call_class_args = self._generic_class_args(e.recv.ty)
                name = 'DELEGATE_CALL' if self.delegate_mi is not None \
                    else (e.text + '() /*indirect*/')
            else:
                name = (e.text + '() /*indirect*/') if e else 'indirect()'
                # batch 38b: constant-displacement vtable dispatch
                # through a klass chain the type tracker can't name --
                # the outer `+ 0xNNN` is 0x138 + 16*slot. Only when the
                # base under it is a klass-load chain (`)[0]` tail or a
                # folded getClass()): a bare pointer-field base
                # (`((byte*)bounds.m_Center + 0x338)[0]()`, a native
                # callback table) must not be treated as a vtable.
                if e is not None:
                    # lifter-side text is `*(base + 0xNNN)`; the
                    # `)[0]` tail only appears later in _unsafify
                    mvt2 = re.search(r'\+ (0x[0-9a-f]+)\)(?:\[0\])?$', e.text or '')
                    if mvt2 is not None:
                        c2 = int(mvt2.group(1), 16)
                        b2 = e.text[:mvt2.start()].rstrip()
                        if c2 >= 0x138 and (c2 - 0x138) % 16 == 0 \
                                and (b2.endswith('+ 0x0)')
                                    or b2.endswith('getClass()')):
                            self.ind_slot = (c2 - 0x138) // 16
        elif ins.op0_kind == OpKind.MEMORY:
            if ins.memory_base == IReg.RIP:
                slot = ins.ip_rel_memory_address
                q = self.bin.qword(slot)
                name = self._call_name(q) if (q and self.bin.is_exec_va(q)) else ('sub_%x' % slot)
            else:
                base = self.reg(reg_name(ins.memory_base)) if ins.memory_base != IReg.NONE else None
                idxr = reg_name(ins.memory_index) if ins.memory_index != IReg.NONE else None
                disp = ins.memory_displacement
                if base is not None and base.kind == 'klass' and disp >= KLASS_VTABLE                         and (disp - KLASS_VTABLE) % 16 == 0:
                    slotn = (disp - KLASS_VTABLE) // 16
                    self.vt_recv = base.recv if base.recv is not None else None
                    self.vt_recv_slot = slotn
                    name = 'VIRT_CALL'
                elif base is not None:
                    name = '*(%s %s)()' % (_term_up(base.text), disp_add(disp)) if base.kind != 'klass' else '?'
                else:
                    name = 'call_ptr_%x' % ins.ip
        else:
            name = 'call_%x' % ins.ip

        if target is not None and target == getattr(self, 'rethrow_va', None):
            self.emit(ins.ip, 'throw;', asm)
            for r in VOLATILE:
                self.regs.pop(r, None)
            self._fresh_unknowns()
            return
        if target is not None and target == getattr(self, 'raise_va', None):
            e = self.regs.get('RCX')
            self.emit(ins.ip, 'throw %s;' % (e.text if e else '?'), asm)
            for r in VOLATILE:
                self.regs.pop(r, None)
            self._fresh_unknowns()
            return
        if target is not None:
            # the pad shapes above are this method's own evidence, and a
            # method with no EH pad has none -- fall back to the helpers
            # proven across the whole binary, each in its dominant role,
            # so a pad-less caller stops printing a bare helper call for
            # a throw -- fix 91
            role = (getattr(self, 'eh_helper_set', None) or {}).get(target)
            if role == 'raise_va':
                e = self.regs.get('RCX')
                self.emit(ins.ip, 'throw %s;' % (e.text if e else '?'), asm)
                for r in VOLATILE:
                    self.regs.pop(r, None)
                self._fresh_unknowns()
                return
            if role:
                self.emit(ins.ip, 'throw;', asm)
                for r in VOLATILE:
                    self.regs.pop(r, None)
                self._fresh_unknowns()
                return

        if target is not None:
            # fix 93: the two evidence-named noreturn raisers raise one
            # specific new exception each -- render the throw, not a named
            # call with a fabricated object result.
            raise_exc = self._named_raise_throw(target, name)
            if raise_exc is not None:
                self.emit(ins.ip, 'throw new %s();' % raise_exc, asm)
                for r in VOLATILE:
                    self.regs.pop(r, None)
                self._fresh_unknowns()
                return

        if target is not None and target == self.rt_init_meta:
            # slot init: side effect only
            if self.asm_comments and asm:
                self.emit(ins.ip, '', asm)
            for r in VOLATILE:
                self.regs.pop(r, None)
            for i in range(6):
                self.regs.pop('XMM%d' % i, None)
            self._fresh_unknowns()
            return

        # Fix 130: the jmp-thunk band named after the same routine is
        # `InitializeRuntimeMetadata(slot, true)` and RETURNS the slot's
        # metadata item (`lea rcx,[TypeInfo slot]; call thunk; mov rcx,
        # rax; call il2cpp_object_new` -- EnumBuilder.GetMembers 0x181BD4E80;
        # `lea rcx,[method slot]; call thunk; mov rdx,rax` feeds the raise
        # helper its MethodInfo). Rendering it as an ordinary call bound the
        # result to a fresh `object objN = il2cpp_codegen_initialize_runtime_
        # metadata(typeof(T));` temp, so the allocation read
        # `il2cpp_object_new(objN)` instead of `new T()` (8.5k CS0103 +
        # 3.3k on the fixture gate). The lazy init is runtime plumbing (the
        # wrapper above already drops it); RAX carries the slot's own
        # expression, exactly what a direct `mov rax,[slot]` load reads.
        if target is not None and name == 'il2cpp_codegen_initialize_runtime_metadata':
            slot_e = self.regs.get('RCX')
            for r in VOLATILE:
                self.regs.pop(r, None)
            for i in range(6):
                self.regs.pop('XMM%d' % i, None)
            self._fresh_unknowns()
            if slot_e is not None and not slot_e._unk and slot_e.text \
                    and slot_e.text.strip() not in ('?', '_'):
                res = self._mk(slot_e.text, slot_e.ty, slot_e.kind)
                res._no_bind = True
                self.regs['RAX'] = res
            if self.asm_comments and asm:
                self.emit(ins.ip, '', asm)
            return

        # Unregistered scalar sqrt/domain wrapper.  The structural
        # recognizer proves a double in XMM0 and a double result in XMM0;
        # treating it as an ordinary unknown call would instead spray stale
        # GPR arguments and put a fabricated result in RAX.  Math.Sqrt is the
        # source-level operation on both the hardware and helper arms.
        if target is not None and target == getattr(self, 'rt_sqrt', None):
            value = self.reg('XMM0')
            self._hint_tok(value, _R8_TY)
            text = value.text if value is not None and not value._unk else '?'
            result = self._mk('Math.Sqrt(%s)' % text, _R8_TY, 'float')
            result._no_bind = True
            for r in VOLATILE:
                self.regs.pop(r, None)
            for i in range(6):
                self.regs.pop('XMM%d' % i, None)
            self._fresh_unknowns()
            self.regs['XMM0'] = result
            if self.asm_comments and asm:
                self.emit(ins.ip, '', asm)
            return

        # Unregistered pure-FP32-unary leaf (ground truth 0x1804cdb00,
        # proved per callee, never by address): the callee reads exactly
        # XMM0 and no GPR/stack argument with no caller-visible effects,
        # and the next instruction consumes a scalar float from XMM0 (see
        # above). Render that shape -- one float argument, a float XMM0
        # result -- instead of the stale-GPR spray with a fabricated
        # `object` RAX result that drops the value (`0f * 20.0f`). The
        # name stays `sub_X`; the managed identity is never inferred.
        if target is not None and re.fullmatch(r'sub_[0-9a-f]+', name) is not None \
                and self._is_fp32_unary_leaf(target):
            value = self.reg('XMM0')
            width = None
            if value is not None and not value._unk and value.text \
                    and value.text.strip() \
                    and value.text.strip() not in ('?', '_') \
                    and _fp32_arg_ok(value.text):
                width = self._fp32_scalar_next(ins)
            if width is not None:
                rty = _R4_TY if width == 'f' else _R8_TY
                self._hint_tok(value, rty)
                call = '%s(%s)' % (name, value.text)
                for r in VOLATILE:
                    self.regs.pop(r, None)
                for i in range(1, 6):
                    self.regs.pop('XMM%d' % i, None)
                self._fresh_unknowns()
                result = Expr(call, rty, 'float')
                self.regs['XMM0'] = result
                self._bind(result)
                if self.asm_comments and asm:
                    self.emit(ins.ip, '', asm)
                return

        # build arg list
        args = []
        arg_exprs = []
        # fix 58: an argument register still holding the unknown its entry
        # seed / post-call clobber minted has not been written since --
        # and every one of these registers is volatile, so argument setup
        # MUST write it at the call site. Such a slot therefore carries no
        # argument (see work/patch_b58_unkargs.py for the full argument).
        unk_slot = []
        for r in ARG_REGS:
            e = self.regs.get(r)
            arg_exprs.append(e)
            unk_slot.append(e is not None and e._unk)
            args.append(self._materialize(e, 110) if e else '_')
        gpr_texts = list(args)
        gpr_exprs = list(arg_exprs)
        xmm_exprs = [self.regs.get(x) for x in ARG_XMM]
        self._xmm_pending = []
        for k, x in enumerate(ARG_XMM):
            e = self.regs.get(x)
            if e is not None and not e._unk:
                args.append(e.text)
                self._xmm_pending.append((k, e))
        while args and (args[-1] == '_'
                        or (len(args) <= len(unk_slot) and unk_slot[len(args) - 1])):
            args.pop()
        # an expression that rendered to nothing (killed text, empty slot read)
        # must still occupy its argument position -- `f(a, , b)` is not C#;
        # `_` is the placeholder the absent-register path above already uses.
        args = [a if a and a.strip() else '_' for a in args]

        # The native body itself can settle a shared identity leaf even
        # when thousands of MethodSpecs own its address. Bind the copied
        # RCX value where the call executes; no method name is invented.
        if target is not None and '/*shared body,' in name:
            identity = self._shared_identity_value(
                target, self.il.addr_candidates.get(target), arg_exprs,
                self._xmm_pending)
            if identity is not None:
                if identity._defpos is None:
                    blk = getattr(self.out, 'block', None)
                    identity._defpos = (
                        blk, len(blk.stmts) if blk is not None else len(self.out))
                self._bind(identity)
                for r in VOLATILE:
                    self.regs.pop(r, None)
                for i in range(6):
                    self.regs.pop('XMM%d' % i, None)
                self._fresh_unknowns()
                self.regs['RAX'] = identity
                if self.asm_comments and asm:
                    self.emit(ins.ip, '', asm)
                return

        # These two System.String names share one native string-equality
        # body. Emit its string == behavior without assigning a MethodDef.
        if (target is not None and '/*shared body,' in name
                and self._shared_string_equality(
                    self.il.addr_candidates.get(target), arg_exprs,
                    self._xmm_pending)):
            left, right = [('null' if a == '0' else a) for a in args[:2]]
            bool_ty = self.il.types[
                self.meta.methods[self.il.addr_candidates[target][0][1]].return_type]
            result = Expr('(%s == %s)' % (left, right), bool_ty, 'int')
            self._bind(result)
            for r in VOLATILE:
                self.regs.pop(r, None)
            for i in range(6):
                self.regs.pop('XMM%d' % i, None)
            self._fresh_unknowns()
            self.regs['RAX'] = result
            if self.asm_comments and asm:
                self.emit(ins.ip, '', asm)
            return

        # --- value boxing: il2cpp_value_box(klass, &value) -> (object)(value)
        # the box is an allocation, so a standalone box statement is dead code
        # and dropped; only the value travels on
        rt_box = getattr(self, 'rt_value_box', None)
        if target is not None and rt_box is not None and target == rt_box and len(args) >= 2:
            v = args[1]
            if v.startswith('&'):
                v = v[1:]
            else:
                pe = arg_exprs[1] if len(arg_exprs) > 1 else None
                if pe is not None:
                    p = self._pointee_of(pe)
                    if p is not None and p.text != pe.text:
                        v = p.text
            for r in VOLATILE:
                self.regs.pop(r, None)
            for i in range(6):
                self.regs.pop('XMM%d' % i, None)
            self._fresh_unknowns()
            self.regs['RAX'] = Expr('(object)(%s)' % v, None, 'obj')
            if self.asm_comments and asm:
                self.emit(ins.ip, '', asm)
            return

        icall_helper = getattr(self.il, 'rt_icall_resolve', None)
        if target is not None and icall_helper is not None and target == icall_helper:
            # il2cpp_codegen_resolve_icall(sig): the result is the native
            # function pointer; render the managed method it names so the
            # cached-cell store and the indirect call through it read right
            ann = None
            a0 = args[0] if args else ''
            s = None
            m = re.match(r'&data_([0-9a-f]+)', a0)
            if m:
                s = self.bin.cstr(int(m.group(1), 16), 512)
            else:
                m = re.match(r'&"([^"]*)"', a0)
                if m:
                    s = m.group(1)
            ann_mi = None
            if s and '::' in s:
                r = self.il._icall_annotation(s)
                if isinstance(r, dict):
                    ann = r.get('text')
                    ann_mi = r.get('method')
            if ann:
                ex = Expr(ann, None, 'fptr')
                # fix 66: the eager-resolve twin of the cached-cell read --
                # same identity, so the call through it trims the same way
                ex._mi = ann_mi
                self.regs['RAX'] = ex
                if self.asm_comments and asm:
                    self.emit(ins.ip, '', asm)
                return

        info = self.il.addr_to_method.get(target) if target else None
        recv = arg_exprs[0] if arg_exprs else None
        # A shared-address target: `_call_name` already rendered the honest
        # `sub_x/*shared body*/` fallback above (receiver-blind). Now that
        # args are known, a collision can often be settled for good:
        #  - direct (non-generic) methods: arg0 of an instance/ctor call is
        #    declared by exactly one candidate somewhere in the receiver's
        #    own base chain -- not just its exact type. A `: base()`
        #    constructor call is the common case this exact-match-only
        #    missed: MonoBehaviour's trivial ctor is folded with dozens of
        #    other Unity component ctors, and the receiver is the DERIVED
        #    script, never MonoBehaviour itself, so an exact match never
        #    fires. `call` targets a compile-time-fixed declaration the
        #    same way a vtable slot resolves through the base chain, so
        #    walking it here is the same kind of lookup, not a guess.
        #  - shared generic bodies: IL2CPP v27.1+ passes the exact
        #    instantiation as a hidden trailing argument, resolved through a
        #    lazy metadata usage slot (decode_slot kind 6 / MethodRef) --
        #    the same mechanism that already names typeof()/string-literal
        #    slots elsewhere. If one of this call's raw arguments is that
        #    slot's value (its text is exactly what generic_method_name()
        #    renders for one candidate), that argument IS the callee's
        #    identity -- use it, and drop it from the printed args since
        #    it's compiler plumbing, not something the source wrote.
        cands = self.il.addr_candidates.get(target) if target else None
        if cands and len(cands) > 1:
            recv_td = self._td_of(recv.ty) if recv is not None else None
            if recv_td is None and recv is not None:
                # array-typed receivers (mi 275/326/4047): _td_of maps
                # no array type; Array owns their instance dispatch.
                recv_td = self._array_receiver_td(recv.ty)
            chain = self._legacy_shared_receiver_chain(recv_td)
            hits = [c for c in cands if c[0] == 'method'
                    and self.meta.methods[c[1]].declaring in chain]
            # An sret owner makes RCX buffer evidence, never receiver
            # evidence. Do not let the legacy base-chain match select an
            # owner from the buffer's type when the stricter proof declines.
            if any(c[0] == 'method' and self.il.returns_sret(
                    self.il.types[self.meta.methods[c[1]].return_type]) for c in cands):
                hits = []
            sret_info = self._shared_sret_receiver_target(cands, arg_exprs)
            ctor_info = self._shared_parameterless_ctor_target(cands, recv)
            generics = [c for c in cands if c[0] == 'generic']
            gi, ghit = None, None
            for i, ae in enumerate(arg_exprs):
                if ae is None or not ae.text:
                    continue
                for c in generics:
                    if ae.text == self.il.generic_method_name(c[1]):
                        gi, ghit = i, c
                        break
                if gi is not None:
                    break
            if gi is not None:
                info = ghit
                name = self.il.generic_method_name(ghit[1])
                arg_exprs = arg_exprs[:gi] + arg_exprs[gi + 1:]
                if gi < len(args):
                    args = args[:gi] + args[gi + 1:]
            elif sret_info is not None:
                info = sret_info
                name = self._info_name(info)
            elif ctor_info is not None:
                info = ctor_info
                name = self._info_name(info)
            elif len(hits) == 1:
                info = hits[0]
                m2 = self.meta.methods[info[1]]
                t2 = self.meta.typedefs[m2.declaring]
                ns2 = (t2.namespace + '.') if t2.namespace else ''
                name = '%s%s.%s' % (ns2, t2.name,
                                     m2.name.lstrip('.').replace('|', '_').replace('@', '_'))
            else:
                info = self._shared_object_receiver_target(cands, recv)
                if info is None:
                    info = self._shared_value_receiver_target(cands, recv)
                if info is None:
                    info = self._shared_static_arg_target(cands, arg_exprs)
                if info is None:
                    info = self._shared_static_signature_target(cands, arg_exprs)
                if info is None:
                    info = self._shared_same_render_target(cands)
                if info is not None:
                    name = self._info_name(info)
        # Fully shared generic bodies: the address may carry one registered
        # owner (or several) while the hidden trailing argument -- a decoded
        # MethodRef usage slot -- names the true instantiation. Trust the
        # slot: it is the callee's identity the runtime itself receives.
        if info is None or info[0] == 'generic':
            for i, ae in enumerate(arg_exprs):
                si = getattr(ae, '_usg_idx', None) if ae is not None else None
                if si is None or not ae.text:
                    continue
                nm6 = self.il.generic_method_name(si)
                if ae.text == nm6:
                    info = ('generic', si)
                    name = nm6
                    arg_exprs = arg_exprs[:i] + arg_exprs[i + 1:]
                    if i < len(args):
                        args = args[:i] + args[i + 1:]
                    break
        # A fresh delegate plus its metadata method pointer proves the ctor,
        # even when the native body is shared with Invoke specializations.
        delegate_target = None
        if recv is not None and len(arg_exprs) > 1:
            ptr_index = next((i for i, value in enumerate(arg_exprs[1:], 1)
                              if value is not None and value.kind == 'methodinfo'), None)
            ptr = arg_exprs[ptr_index] if ptr_index is not None else None
            invoke = self._delegate_invoke_method(recv.ty) if ptr is not None else None
            if invoke is not None and ptr is not None and ptr.kind == 'methodinfo' \
                    and getattr(ptr, '_mi', None) is not None:
                td = self._td_of(recv.ty)
                ctors = [ci for ci in self.meta.type_methods(self.meta.typedefs[td])
                         if self.meta.methods[ci].name == '.ctor'
                         and self.meta.methods[ci].param_count == 2]
                if len(set(ctors)) == 1:
                    info = ('method', ctors[0])
                    name = self.il.method_simple_name(ctors[0])
                    target_method = self.meta.methods[ptr._mi]
                    target_owner = self.meta.typedefs[target_method.declaring]
                    receiver = arg_exprs[ptr_index - 1] if ptr_index > 1 else None
                    if target_method.is_static:
                        owner = ((target_owner.namespace + '.') if target_owner.namespace else '') + target_owner.name
                    else:
                        owner = _recv_fold(receiver.text) if receiver is not None else None
                    if owner is not None:
                        delegate_target = owner + '.' + target_method.name
        rty = None
        mi = None
        shared_rty = False
        if info and info[0] in ('method', 'generic'):
            mi = info[1] if info[0] == 'method' else self.il.method_specs[info[1]][0]
            if mi is not None and 0 <= mi < len(self.meta.methods):
                rt_idx = self.meta.methods[mi].return_type
                rty = self.il.types[rt_idx] if 0 <= rt_idx < len(self.il.types) else None
                if info[0] == 'generic':
                    closed_return = self.il.candidate_return_type(info)
                    if closed_return is not None:
                        rty = closed_return
                    self._call_class_args = self.il._method_spec_type_args(
                        self.il.method_specs[info[1]][1])
        if info and info[0] == 'generic':
            home = self._proved_struct_home(info, args, rty)
            if home is not None:
                self.slot_types.setdefault(home[0], home[1])
                self._type_hints.setdefault(home[0], home[1])
        # The callee identity can remain honestly ambiguous while every
        # registered owner still declares the exact same closed return type.
        # Use only that all-candidates consensus: it fixes the result register,
        # sret handling, and local declaration without inventing a method name.
        if mi is None and cands and len(cands) > 1:
            consensus = getattr(self.il, 'shared_return_type', None)
            if consensus is not None:  # lightweight test doubles may omit it
                agreed = consensus(target)
                # A managed struct call can be rendered confidently only
                # when its hidden return buffer is an observed address.
                # Otherwise the buffer would leak into the source argument
                # list and RAX is merely its echoed native pointer.
                if agreed is not None and (not self.il.returns_sret(agreed)
                                           or (args and args[0].startswith('&'))):
                    rty = agreed
                    shared_rty = True
        interface_call = self._nullary_interface_dispatch(target, arg_exprs) if mi is None else None
        iface_identity = interface_call is not None
        if interface_call is not None:
            mi, recv, iface_rty = interface_call
            rty = iface_rty
            name = self.il.method_simple_name(mi)
            args, arg_exprs = [recv.text], [recv]
        else:
            _pif = self._param_interface_dispatch(target, arg_exprs) if mi is None else None
            if _pif is not None:
                mi, recv, iface_rty = _pif[:3]
                rty = iface_rty
                name = self.il.method_simple_name(mi)
                if len(_pif) > 3:
                    args, arg_exprs = [recv.text] + [a.text for a in _pif[3:]], [recv] + list(_pif[3:])
                else:
                    args, arg_exprs = [recv.text], [recv]
                iface_identity = True
        # Resolve a vtable slot to its metadata method up front, so arg trimming,
        # instance-style rendering and property-accessor folding below apply to
        # virtual calls exactly as they do to direct ones.
        vt_slot = self.vt_recv_slot
        if name == 'VIRT_CALL' and vt_slot is not None:
            recv0 = recv if recv is not None else getattr(self, 'vt_recv', None)
            recv_td = self._td_of(recv0.ty) if recv0 is not None else None
            vm = self.il.vtable_method(recv_td, vt_slot) if recv_td is not None else None
            if vm is not None and 0 <= vm < len(self.meta.methods):
                mi = vm
                m2 = self.meta.methods[vm]
                t2 = self.meta.typedefs[m2.declaring]
                ns2 = (t2.namespace + '.') if t2.namespace else ''
                name = '%s%s.%s' % (ns2, t2.name,
                                     m2.name.lstrip('.').replace('|', '_').replace('@', '_'))
                rt_idx = m2.return_type
                rty = self.il.types[rt_idx] if 0 <= rt_idx < len(self.il.types) else None
                # fix 129b: a slot declared on the receiver's own generic
                # definition sees its class VARs bound by the receiver's
                # GENERICINST arguments (Comparer<float>.Compare(T, T)
                # takes XMM1/XMM2, not RDX/R8).  An ancestor-declared
                # slot maps VARs through the base chain: left unbound.
                if self._call_class_args is None and m2.declaring == recv_td:
                    _cca = self._generic_class_args(recv0.ty)
                    if _cca:
                        self._call_class_args = _cca
                        rty = self._class_type_subst(rty)
        # An icall thunk cell (fix 66) names its method as firmly as a
        # vtable slot does: seat it the same way, so everything below --
        # the arity trim, `_hint_arg_types`, `_positional_args`, the
        # byref/`ref` render, the sret and property folds -- applies.
        # Without this `mi` stays None and the site prints its already
        # resolved name as `Foo.Bar() /*indirect*/(...)` followed by every
        # stale GPR/XMM slot the register file happened to be holding.
        if mi is None and self.ic_mi is not None \
                and 0 <= self.ic_mi < len(self.meta.methods):
            mi = self.ic_mi
            m2 = self.meta.methods[mi]
            t2 = self.meta.typedefs[m2.declaring] \
                if 0 <= m2.declaring < len(self.meta.typedefs) else None
            if t2 is None:
                mi = None
            else:
                ns2 = (t2.namespace + '.') if t2.namespace else ''
                name = '%s%s.%s' % (ns2, t2.name,
                                    m2.name.lstrip('.').replace('|', '_').replace('@', '_'))
                rt_idx = m2.return_type
                rty = self.il.types[rt_idx] \
                    if 0 <= rt_idx < len(self.il.types) else None
        # Delegate invoke_impl is called with method_code in the managed
        # receiver slot, then the real arguments and trailing runtime
        # plumbing.  The delegate TypeDef's Invoke declaration supplies the
        # exact signature: replace method_code with the delegate receiver and
        # let the ordinary resolved-call path trim and render it.  A hidden
        # sret buffer stays in args[0] and shifts the replacement to args[1].
        if mi is None and self.delegate_mi is not None \
                and 0 <= self.delegate_mi < len(self.meta.methods):
            mi = self.delegate_mi
            m2 = self.meta.methods[mi]
            rt_idx = m2.return_type
            rty = self.il.types[rt_idx] \
                if 0 <= rt_idx < len(self.il.types) else None
            rty = self._class_type_subst(rty)
            dri = 1 if self.il.returns_sret(rty) else 0
            drecv = self.delegate_recv
            if drecv is not None and dri < len(args):
                args[dri] = drecv.text
                if dri < len(arg_exprs):
                    arg_exprs[dri] = drecv
                recv = drecv
                name = 'Invoke'
        for r in VOLATILE:
            self.regs.pop(r, None)
        for i in range(6):
            self.regs.pop('XMM%d' % i, None)
        self._fresh_unknowns()

        # --- IsInst intrinsic: sub_x(obj, typeof(T)) -> obj as T
        if target is not None and target in getattr(self, 'rt_isinst', ()) \
                and len(arg_exprs) >= 2:
            _obj, _klass = arg_exprs[0], arg_exprs[1]
            if _obj is not None and _klass is not None \
                    and _klass.kind == 'klass' \
                    and isinstance(_klass.text, str) \
                    and _klass.text.startswith('typeof(') \
                    and _klass.text.endswith(')'):
                _tname = _klass.text[len('typeof('):-1]
                _e = self._mk('(%s as %s)' % (_obj.text, _tname),
                              _klass.ty, 'obj')
                self.regs['RAX'] = _e
                if self.asm_comments and asm:
                    self.emit(ins.ip, '', asm)
                return

        # --- Interlocked.CompareExchange(ref loc, value, comparand)
        if target is not None and target in getattr(self, 'rt_interlocked', ()) \
                and len(arg_exprs) >= 3:
            _loc, _val, _cmp = arg_exprs[0], arg_exprs[1], arg_exprs[2]
            if _loc is not None and _val is not None and _cmp is not None \
                    and isinstance(_loc.text, str) and _loc.text.startswith('&'):
                _e = self._mk(
                    'System.Threading.Interlocked.CompareExchange(ref %s, %s, %s)'
                    % (_loc.text[1:], _val.text, _cmp.text),
                    _val.ty if isinstance(_val.ty, tuple) else None, 'obj')
                self.regs['RAX'] = _e
                if self.asm_comments and asm:
                    self.emit(ins.ip, '', asm)
                return

        # --- object allocation helper: sub_x(typeof(T)) -> new T()
        if target is not None and target == self.rt_alloc and recv is not None                 and recv.kind == 'klass':
            tn = self.il.type_name(recv.ty)
            allocation = Expr('new %s()' % tn, recv.ty, 'obj')
            allocation._alloc = allocation.text
            self.regs['RAX'] = allocation
            if self.asm_comments and asm:
                self.emit(ins.ip, '', asm)
            return

        # --- array allocation: new T[len]
        if target is not None and target in self.rt_arrnew and recv is not None                 and recv.kind == 'klass':
            tn = self.il.type_name(recv.ty)
            dim_rank = 0
            while tn.endswith('[]') or tn.endswith('[,]'):
                dim_rank += 1
                tn = tn[:-2]
            dims = [a for a in args[1:1 + dim_rank] if a and a != '_']
            self.regs['RAX'] = self._array_allocation(
                'new %s[%s]' % (tn, ']['.join(dims) if dims else '0'),
                recv.ty, ins.ip, asm)
            if self.asm_comments and asm:
                self.emit(ins.ip, '', asm)
            return

        # --- write barrier: store(&field, value) -> field = value
        if target is not None and target in self.rt_wbarrier and args:
            dst, src2 = self._wb_operands(args, arg_exprs)
            self._wb_finish(ins.ip, dst, src2, asm)
            ae0 = arg_exprs[0] if arg_exprs else None
            off = getattr(ae0, '_stack_offset', None)
            if off is not None and hasattr(self.il, '_sf_field_size') and len(arg_exprs) > 1:
                self._stack_store(off, 8, arg_exprs[1])
            return
        # --- ambiguous shared body (the `sub_x/*shared body, N
        # candidates*/` honest-fallback case): `mi` is unknown, but every
        # candidate names a call into the SAME compiled machine code, so
        # they all consume the SAME argument registers regardless of which
        # metadata identity is the true one -- trimming to the largest
        # declared arity among them is sound (not a guess at WHICH
        # candidate), and stops a call that actually reads 2-3 registers
        # from dragging along whatever stale GPR/XMM values a `_bind`
        # elsewhere in the method happened to leave behind as bogus extra
        # "arguments" (unrelated read-before-def temps in the render).
        if mi is None and cands and len(cands) > 1:
            # Consensus applies to every candidate, including a root
            # VAR/MVAR inflated to a concrete struct.  Use it for the
            # hidden-buffer slot when available; the raw MethodDef
            # signature cannot classify that ABI.
            want0 = self._shared_arity_cap(cands, rty if shared_rty else None)
            classes = self._shared_slot_classes(cands, rty if shared_rty else None)
            if classes is not None and 'x' in classes \
                    and len(classes) == want0 and len(classes) <= len(ARG_REGS):
                args = self._shared_positional_args(args, classes)
            elif want0 is not None and len(args) > want0:
                args = args[:want0]
            shapes = set()
            for c in cands:
                m3 = None
                if c[0] == 'method':
                    m3 = self.meta.methods[c[1]]
                elif c[0] == 'generic':
                    md3 = self.il.method_specs[c[1]][0]
                    if 0 <= md3 < len(self.meta.methods):
                        m3 = self.meta.methods[md3]
                if m3 is not None:
                    rt3 = self.il.types[m3.return_type] \
                        if 0 <= m3.return_type < len(self.il.types) else None
                    shapes.add((m3.is_static, m3.param_count,
                                bool(rt3 is not None and self.il.returns_sret(rt3))))
            if len(shapes) > 1 and hasattr(self.il, '_sf_field_size'):
                ae0 = arg_exprs[0] if arg_exprs else None
                off = getattr(ae0, '_stack_offset', None)
                if off is not None:
                    for key in [k for k in self.regs if k.startswith('!mem:')]:
                        _, lo, n = key.split(':'); lo, n = int(lo), int(n)
                        if lo <= off < lo + n:
                            del self.regs[key]
                    for addr, slot in self.stack_map.items():
                        if addr == off:
                            self.stack_values.pop(slot, None)
                            break

        # --- struct-return: Foo(&s_N, ...) with valuetype return -> s_N = Foo(...)
        # When the callee is an instance property getter, the sret buffer is
        # arg0 and the RECEIVER is arg1: fold `buf = recv.get_Prop()` to
        # `buf = recv.Prop` (Transform.get_position -> transform.position).
        if args and args[0].startswith('&') and self.il.returns_sret(rty):
            buf = args[0][1:]
            stack_address = getattr(arg_exprs[0], '_stack_offset', None) if arg_exprs else None
            if stack_address is not None and hasattr(self.il, '_sf_field_size'):
                prev = getattr(self, '_sret_home_buf', {}).get(stack_address)
                if prev is not None and prev[1] == rty:
                    buf = prev[0]
                else:
                    buf = self.new_var()
                    self._var_types[buf] = rty
                    hb = getattr(self, '_sret_home_buf', None)
                    if hb is not None:
                        hb[stack_address] = (buf, rty)
            rest = args[1:]
            short2 = None
            if mi is not None and 0 <= mi < len(self.meta.methods):
                m2 = self.meta.methods[mi]
                # This early-return path must rebuild Win64 positions too:
                # parameters five and later live in the stack home area, not
                # in the stale XMM tail of the raw argument list.
                self._hint_arg_types(args, arg_exprs, mi, rty)
                rest = self._positional_args(args, m2, rty)[1:]
                want = m2.param_count + (0 if m2.is_static else 1)
                if len(rest) > want:
                    rest = rest[:want]
                # fix 54c: same declared-parameter render as fix 54's
                # `_hint_arg_types` hook -- which this branch never
                # reaches, because it returns below. Here the sret
                # question is SETTLED rather than inferred (arg0 was
                # peeled off as the buffer), so `rest` is
                # [receiver?] + params exactly and no trust guard is
                # needed. rest[0] of an instance call is the receiver,
                # never a declared param, so the fold below is safe.
                b2 = 0 if m2.is_static else 1
                for pi2, p2 in enumerate(self.meta.method_params(m2)):
                    ai2 = b2 + pi2
                    if ai2 >= len(rest) or not rest[ai2].startswith('&'):
                        continue
                    pt2 = self.il.types[p2.type] \
                        if 0 <= p2.type < len(self.il.types) else None
                    pt2 = self._class_type_subst(pt2)
                    if pt2 is None:
                        break
                    aggregate2 = self._copied_struct_arg(rest[ai2], pt2) \
                        if hasattr(self.il, '_sf_field_size') else None
                    if aggregate2 is not None:
                        rest[ai2] = aggregate2
                        continue
                    bits2 = pt2[1]
                    rep2 = _byref_arg_render(
                        rest[ai2],
                        bool(((bits2 >> 29) & 1)
                             or (bits2 >> 16) & 0xFF == 0x10),
                        self._byval_struct(pt2), True)
                    if rep2 is not None:
                        rest[ai2] = rep2
                mbase2 = m2.name.rpartition('.')[2] if '.' in m2.name else m2.name
                if not m2.is_static and rest and rest[0] not in ('?', ''):
                    rt2 = rest[0][1:] if rest[0].startswith('&') else rest[0]
                    if rt2 == 'this' or '.' in rt2 or _BARE_TOKEN_RX.match(rt2) \
                            or re.match(r'^s_[0-9a-fA-F]+$', rt2):
                        if mbase2 == 'get_Item' and len(rest) == 2:
                            short2 = '%s[%s]' % (rt2, rest[1])
                        elif mbase2.startswith('get_') and len(rest) == 1:
                            short2 = '%s.%s' % (rt2, mbase2[4:].replace('|', '_').replace('@', '_'))
                        elif not mbase2.startswith(('set_', 'get_')) \
                                and mbase2 != '.ctor':
                            short2 = '%s.%s(%s)' % (_recv_fold(rt2), mbase2, ', '.join(rest[1:]))
                # fix 137: static getters, indexer rows and parameter /
                # local receivers (`hits[0]`, `Random.onUnitSphere`)
                if (short2 is None or short2.endswith(')')) and '.' not in m2.name:
                    _sg2 = None
                    if m2.is_static:
                        _own2 = self._static_owner(name, mi)
                        _sg2 = self._accessor_sugar(mi, _own2, list(rest)) if _own2 else None
                    elif rest and rest[0] not in ('?', ''):
                        _r2 = rest[0][1:] if rest[0].startswith('&') \
                            and _REFARG_RX.match(rest[0][1:]) else rest[0]
                        _sg2 = self._accessor_sugar(mi, _r2, list(rest[1:]))
                    if _sg2 is not None and _sg2[0] == 'expr':
                        short2 = _sg2[1]
            self._kill_stale(buf)
            if short2 is not None:
                self.emit(ins.ip, '%s = %s;' % (buf, short2), asm)
            else:
                self.emit(ins.ip, '%s = %s(%s);' % (buf, name, ', '.join(rest)), asm)
            self.slot_types[buf] = rty
            if stack_address is not None and hasattr(self.il, '_sf_field_size'):
                # unknown layout sizes record no facts (an open generic
                # definition has no row): storing a None width crashes the
                # span math below, and piece reads off it would be guesses.
                _sz = self.il._sf_field_size(rty, 0)
                if _sz is not None:
                    self._stack_store(stack_address, _sz, Expr(buf, rty, 'obj'))
            # Win64 sret ABI: the callee echoes the hidden buffer
            # pointer back in RAX, and MSVC callers read the result
            # through it (`movsd xmm1,[rax]`) -- without this binding
            # every such read dereferences a fresh vN unknown, the
            # *(v80 + 0x0) / ((byte*)obj11 + 0x0)[0] family.
            # Size guard (b35c): structs of size <= 8 come back IN RAX
            # by value (MSVC) -- binding those to the buffer invents a
            # pointer (`if (&s_890 != 256)`, 7 sites in the TMP
            # flat-lift files at b35_out1). fix 59d: that guard was a
            # field-offset guess for "spans past 8 bytes"; the exact
            # size now gates the whole fold one level up, so reaching
            # here already means a real buffer. Keeping the old guess
            # too would re-lose the cases it cannot see (a struct whose
            # single field is a 64-byte struct has no offset >= 0x18).
            self.regs['RAX'] = Expr('&%s' % buf, rty, 'ptr')
            self.regs['RAX']._stack_offset = stack_address
            return



        # --- class-init helpers take just the class
        if ('class_init' in name or name.startswith('il2cpp_runtime_class_init')
                or 'ClassInit' in name) and args:
            args = args[:1]

        # --- trim args to the known signature; instance-style rendering
        short = None
        if mi is not None and 0 <= mi < len(self.meta.methods):
            m2 = self.meta.methods[mi]
            want = m2.param_count + (0 if m2.is_static else 1)
            # fix 69 (todo lead 5c): a hidden sret buffer that reaches
            # here (the struct-return fold above returns whenever it
            # fires, so getting this far already means it did NOT --
            # register-held buffer, not a literal `&s_N`) still spends
            # args[0] on the buffer. Mirrors _hint_arg_types/
            # _positional_args' own unconditional `ri += 1` two lines
            # below -- they already assume this slot; the trim was the
            # one returns_sret call site that didn't.
            if self.il.returns_sret(rty):
                want += 1
            # hint first: _hint_arg_types reads the raw GPR + XMM-tail
            # layout; `_positional_args` then rebuilds the visible list by
            # ABI position so float params, stack args and the hidden sret
            # slot all land in the right place before any arity trim.
            self._hint_arg_types(args, arg_exprs, mi, rty)
            self._kill_byref_slots(mi, rty, arg_exprs)
            args = self._positional_args(args, m2, rty)
            if len(args) > want:
                args = args[:want]
            args = self._materialize_float_lanes(args, arg_exprs, m2, rty)
            recv_txt = recv.text if recv is not None else ''
            bare_inner = recv_txt[1:] if recv_txt.startswith('&') else recv_txt
            byref = recv_txt.startswith('&') and ('.' in recv_txt
                                                  or _BARE_TOKEN_RX.match(bare_inner))
            if byref:
                recv_txt = recv_txt[1:]
            mname = m2.name
            # metadata ctor names carry a leading dot (`.ctor`); the
            # instance join below adds its own
            mdot = (mname[1:] if mname.startswith('.') else mname)
            mdot = mdot.replace('|', '_').replace('@', '_')
            # explicit interface implementations carry dotted accessor names
            # (IFace.get_X); the accessor checks read the last segment
            mbase = mname.rpartition('.')[2] if '.' in mname else mname
            # fix 137: a parameterized property is declared `this[...]`
            # whatever its metadata name (String.Chars), so its accessors
            # fold through the indexer branches below exactly like Item.
            _ap137 = self._accessor_prop(mi) if '.' not in mname else None
            if _ap137 is not None and _ap137[2] >= 1:
                mbase = 'get_Item' if _ap137[0] == 'get' else 'set_Item'
            # a proved generic identity (exact hidden-slot match) prints its
            # closed token; the metadata open name feeds only the guards
            if info is not None and info[0] == 'generic':
                try:
                    gname = self.il.generic_method_name(info[1])
                except Exception:
                    gname = None
                if gname is not None and gname == name:
                    lt = gname.find('<')
                    if 0 < lt and lt > gname.rfind('.'):
                        mdot = gname[gname.rfind('.') + 1:]
            # fix 69b: args[0] is the receiver only when the return
            # does NOT need a hidden sret buffer -- Win64 puts the
            # buffer in RCX and shifts the receiver to RDX when it
            # does. Same `ri` walk as _hint_arg_types/_positional_args
            # two sections up (only consumed below where `not
            # m2.is_static`, so the static+sret case -- buffer only,
            # no receiver to skip -- never reaches it).
            rest_off = 0 if m2.is_static else 1
            if self.il.returns_sret(rty):
                rest_off += 1
            rest = args[rest_off:] if args else []
            # F2-C2: single-field lane args at struct-typed params.
            # `Foo(X.f, ...)` becomes `Foo(X, ...)` when X resolves
            # to the same closed non-enum single-field value type
            # the parameter declares (exact tuple match) and f is
            # that field. Dotted args are never type-hinted, so no
            # stale hint survives; evaluation count is unchanged
            # (one read either way). Generic/sret/arity-mismatched
            # calls, byref params/args, call/complex bases and
            # unknown types keep today's spelling.
            try:
                _c2ps = self.meta.method_params(m2)
            except Exception:
                _c2ps = None
            if _c2ps is not None and m2.generic_container == -1 \
                    and not self.il.returns_sret(rty) \
                    and len(rest) == len(_c2ps):
                for _i, (_a, _p) in enumerate(zip(rest, _c2ps)):
                    try:
                        _pt = self.il.types[_p.type] \
                            if 0 <= _p.type < len(self.il.types) else None
                    except Exception:
                        _pt = None
                    if _pt is None:
                        continue
                    try:
                        _pb = bool((_pt[1] >> 29) & 1)
                    except Exception:
                        continue
                    _m = re.fullmatch(r'([A-Za-z_]\w*)\.([A-Za-z_]\w*)', (_a or '').strip())
                    if not _m:
                        continue
                    _x = _m.group(1)
                    _xt = None
                    for _mp in ('_var_types', '_type_hints', 'slot_types'):
                        try:
                            _mm = getattr(self, _mp, None)
                            _xt = _mm.get(_x) if _mm else None
                        except Exception:
                            _xt = None
                        if isinstance(_xt, tuple):
                            break
                    if not isinstance(_xt, tuple):
                        continue
                    try:
                        _xtd = self._td_of(_xt) if hasattr(self, '_td_of') else None
                        _xtdo = self.meta.typedefs[_xtd] \
                            if _xtd is not None and 0 <= _xtd < len(self.meta.typedefs) else None
                        _ch = self.il.instance_field_chain(_xtd) if _xtd is not None else None
                        _en = bool(getattr(_xtdo, 'is_enum', False)) if _xtdo is not None else True
                        _vt = bool(getattr(_xtdo, 'is_valuetype', False)) if _xtdo is not None else False
                    except Exception:
                        continue
                    if _xtdo is None:
                        continue
                    _got = self._single_field_arg(_a, _pt, _pb, _xt, _ch or {}, _en, _vt)
                    if _got is None:
                        continue
                    rest[_i] = _got
                    try:
                        args[rest_off + _i] = _got
                    except Exception:
                        pass
            # Constructors are not callable members in C#. Recover the source
            # initializer when the receiver is this, or complete the exact
            # il2cpp_object_new Expr in place so every alias observes one
            # allocation rather than `new T(args); ... = new T();`.
            init_kind = self._constructor_initializer_kind(m2, recv)
            if init_kind is not None:
                self.emit(ins.ip, '%s..ctor(%s);' %
                          (init_kind, ', '.join(rest)), asm)
                return
            if delegate_target is not None:
                rest = [delegate_target]
            if m2.name == '.ctor' and not m2.is_static \
                    and self._complete_fresh_constructor(recv, rest):
                return
            # property accessors fold through ANY receiver: the accessor's
            # own metadata declares arg0 an instance of the declaring type,
            # so an untyped `*(x + 0x40)` pointee or a `&local` byref still
            # reads correctly as a member (byref receivers: strip the '&')
            acc = (not m2.is_static and recv is not None
                   and recv_txt and recv_txt != '?'
                   and ((mbase.startswith('get_') and not rest)
                        or (mbase.startswith('set_') and len(rest) == 1
                            and not rty_has_value(self, rty))
                        or (mbase == 'get_Item' and 1 <= len(rest) <= 2)
                        or ((mbase.startswith('add_') or mbase.startswith('remove_')) and len(rest) == 1 and not rty_has_value(self, rty)) or (mbase == 'set_Item' and len(rest) == 2)))
            if acc and recv_txt.startswith('&'):
                recv_txt = recv_txt[1:]
            if not m2.is_static and args and recv is not None \
                    and (acc
                         or (recv.kind in ('obj', 'arr', 'str')
                             and ('.' in recv_txt or recv_txt == 'this'
                                  or _BARE_TOKEN_RX.match(recv_txt)))
                         or (recv.kind == 'byref' and byref
                             and ('.' in recv_txt or recv_txt == 'this'
                                  or _BARE_TOKEN_RX.match(recv_txt)))):
                # property accessors
                if mbase.startswith('get_') and not rest:
                    cand = '%s.%s' % (_recv_fold(recv_txt), mbase[4:])
                    if len(cand) < 150:
                        short = cand
                elif mbase.startswith('set_') and len(rest) == 1 and not rty_has_value(self, rty):
                    cand = None
                    lv = '%s.%s' % (_recv_fold(recv_txt), mbase[4:])
                    acc_hint = self._hint_accessor_recv(recv, m2)
                    if acc_hint is not None:
                        self.slot_types.setdefault(acc_hint[0], acc_hint[1])
                        self._type_hints.setdefault(acc_hint[0], acc_hint[1])
                    self._kill_stale(lv)
                    self.emit(ins.ip, '%s = %s;' % (lv, rest[0]), asm)
                    for rr in VOLATILE:
                        self.regs.pop(rr, None)
                    return
                elif (mbase.startswith('add_') or mbase.startswith('remove_')) and len(rest) == 1 and not rty_has_value(self, rty):
                    cand = None
                    lv = '%s.%s' % (_recv_fold(recv_txt), mbase[4:] if mbase.startswith('add_') else mbase[7:])
                    self._kill_stale(lv)
                    self.emit(ins.ip, '%s %s= %s;' % (lv, '+' if mbase.startswith('add_') else '-', rest[0]), asm)
                    for rr in VOLATILE:
                        self.regs.pop(rr, None)
                    return
                elif mbase == 'get_Item' and 1 <= len(rest) <= 2:
                    # indexer accessors: recv.get_Item(k) -> recv[k]
                    cand = '%s[%s]' % (_recv_fold(recv_txt), ', '.join(rest))
                    if len(cand) < 150:
                        short = cand
                elif mbase == 'set_Item' and len(rest) == 2:
                    lv = '%s[%s]' % (_recv_fold(recv_txt), rest[0])
                    self._kill_stale(lv)
                    self.emit(ins.ip, '%s = %s;' % (lv, rest[1]), asm)
                    for rr in VOLATILE:
                        self.regs.pop(rr, None)
                    return
                else:
                    cand = '%s.%s(%s)' % (_recv_fold(recv_txt), mdot, ', '.join(rest))
                    if len(cand) < 150:
                        short = cand
        if short is None and mi is not None and 0 <= mi < len(self.meta.methods):
            m2 = self.meta.methods[mi]
            if m2.is_static and m2.name.startswith('get_') and m2.param_count == 0:
                short = '%s.%s' % (name.rsplit('.', 1)[0], m2.name[4:])
            # fix 137: a static property setter is an assignment
            # (`Gizmos.set_color(c)` -> `Gizmos.color = c;`)
            if short is None and m2.is_static:
                _own = self._static_owner(name, mi)
                _sg = self._accessor_sugar(mi, _own, list(args)) if _own else None
                if _sg is not None and _sg[0] == 'stmt':
                    self._kill_stale(acc_lhs(_sg[1]))
                    self.emit(ins.ip, _sg[1] + ';', asm)
                    for rr in VOLATILE:
                        self.regs.pop(rr, None)
                    return
        # receiver-tracked but not folded, or receiver untracked (byref
        # receivers loaded through usage slots, or plain obj receivers the
        # register tracking missed): for non-static calls arg0 IS the
        # receiver by IL2CPP convention -- fold when it reads as a safe
        # receiver (bare token, dotted member, this, or & of those)
        if short is None and mi is not None and 0 <= mi < len(self.meta.methods) \
                and not self.meta.methods[mi].is_static and args:
            a0 = args[0]
            if a0.startswith('&') and ('.' in a0
                                       or _BARE_TOKEN_RX.match(a0[1:])
                                       or re.match(r'^s_[0-9a-fA-F]+$', a0[1:])):
                a0 = a0[1:]
            if a0 != args[0] or a0 == 'this' or '.' in a0 \
                    or _BARE_TOKEN_RX.match(a0) \
                    or re.match(r'^s_[0-9a-fA-F]+$', a0):
                args[0] = a0
                cand = '%s.%s(%s)' % (_recv_fold(args[0]), mdot, ', '.join(args[1:]))
                # fix 137: proved accessor rows use member syntax
                _sg = self._accessor_sugar(mi, a0, list(args[1:])) \
                    if '.' not in m2.name else None
                if _sg is not None and _sg[0] == 'stmt':
                    self._kill_stale(acc_lhs(_sg[1]))
                    self.emit(ins.ip, _sg[1] + ';', asm)
                    for rr in VOLATILE:
                        self.regs.pop(rr, None)
                    return
                if _sg is not None:
                    cand = _sg[1]
                if len(cand) < 150:
                    short = cand
            elif _recv_shaped(a0) and not m2.name.startswith('.'):
                # fix 40: a resolved instance method's arg0 IS the
                # receiver even when it renders as a raw deref, array
                # element, or call result -- the same any-receiver
                # rule the accessor branch above applies
                # (`GameObject.SetActive(obj22[num2], 0)` ->
                # `obj22[num2].SetActive(0)`). ctor names keep their
                # dedicated paths; unshaped texts stay static-style.
                cand = '%s.%s(%s)' % (_recv_fold(a0), mdot, ', '.join(args[1:]))
                # fix 137: proved accessor rows use member syntax
                _sg = self._accessor_sugar(mi, a0, list(args[1:])) \
                    if '.' not in m2.name else None
                if _sg is not None and _sg[0] == 'stmt':
                    self._kill_stale(acc_lhs(_sg[1]))
                    self.emit(ins.ip, _sg[1] + ';', asm)
                    for rr in VOLATILE:
                        self.regs.pop(rr, None)
                    return
                if _sg is not None:
                    cand = _sg[1]
                if len(cand) < 150:
                    short = cand
        # --- runtime-helper arity: `name` from rt_names knows the true
        # signature; the register spray's leftover residues exceed it.
        # array_new additionally recovers the `new T[n]` shape even when
        # the klass arg was a nested init call instead of a klass-tracked
        # register (see the klass-kind branch above).
        if name == 'il2cpp_array_new' and args:
            m0 = re.search(r'typeof\(([^[]+)(\[(,*)\])\)', args[0])
            if m0:
                rank = 1 + len(m0.group(3))
                if len(args) > 1 + rank:
                    args = args[:1 + rank]
                dims = [a for a in args[1:1 + rank] if a and a != '_']
                # fix 130: one allocation, one identity -- the same binder
                # the klass-kind branch uses; a bare `new T[n]` Expr is
                # re-printed at every use (each a fresh array).
                self.regs['RAX'] = self._array_allocation(
                    'new %s[%s]' % (m0.group(1), ']['.join(dims) if dims else '0'),
                    None, ins.ip, asm)
                if self.asm_comments and asm:
                    self.emit(ins.ip, '', asm)
                return
        if name == 'il2cpp_object_new' and args and \
                re.match(r'^\w+\(', args[0]) and 'typeof(' in args[0]:
            m0 = re.search(r'typeof\(([^)]+)\)', args[0])
            if m0:
                allocation = Expr('new %s()' % m0.group(1), None, 'obj')
                allocation._alloc = allocation.text
                self.regs['RAX'] = allocation
                if self.asm_comments and asm:
                    self.emit(ins.ip, '', asm)
                return
        if name in self.RT_ARITY and len(args) > self.RT_ARITY[name]:
            args = args[:self.RT_ARITY[name]]
        elif re.fullmatch(r'sub_[0-9a-f]+', name):
            # fix 132: the callee's entry-live registers decide the
            # positional list (see il2cpp/entrylive.py); no proof keeps
            # the four-GPR spray.
            proven = self._entry_live_call_args(target, gpr_exprs, gpr_texts, xmm_exprs)
            if proven is not None:
                args = proven
            elif len(args) > 4:
                args = args[:4]
        elif getattr(self, 'ind_slot', None) is not None:
            # batch 38b: the indirect vtable-dispatch bound -- same
            # max-arity-across-all-types proof as VIRT_CALL's
            mx2 = self.il.slot_max_arity(self.ind_slot)
            if mx2 is not None and len(args) > mx2:
                args = args[:mx2]
            self.ind_slot = None
        call = short if short is not None else '%s(%s)' % (name, ', '.join(args))
        # conversion-operator twins (Decimal.op_Explicit x4...): decls
        # render as `explicit/implicit operator`, so a `T.op_X(a)` call
        # names a member that no longer exists. Recast `(R)(a)` for the
        # resolved single-arg collision only; a leading `ref `/`&` (byref
        # group homes) strips to the value, matching the by-value
        # operator decl. ponytail: mi + shape gated; non-colliding op_
        # call spellings keep rendering.
        _m2c = self.meta.methods[mi] \
            if mi is not None and 0 <= mi < len(self.meta.methods) else None
        if _m2c is not None and _m2c.name in ('op_Explicit', 'op_Implicit') \
                and _m2c.is_static and '.' not in _m2c.name and _m2c.generic_container == -1 \
                and len(args) == 1 and args[0] not in ('_', '?', '') and rty is not None:
            try:
                _pc = self.meta.method_params(_m2c)
                _ptc = tuple(self.il.types[p.type] for p in _pc)
                _cc = self.il.op_collision_conv(_m2c.declaring, _m2c.name, _ptc) \
                    if len(_ptc) == 1 else None
                _rtn = self.il.type_name(rty) if _cc is not None else None
            except Exception:
                _cc, _rtn = None, None
            if _cc is not None and _rtn:
                _av = args[0][4:] if args[0].startswith('ref ') else args[0]
                if _av.startswith('&'):
                    _av = _av[1:]
                call = '(%s)(%s)' % (_rtn, _av)
        # --- unresolved vtable slot (receiver type unknown)
        if name == 'VIRT_CALL':
            recv0 = recv if recv is not None else getattr(self, 'vt_recv', None)
            if vt_slot is not None:
                mx = self.il.slot_max_arity(vt_slot)
                if mx is not None and len(args) > mx:
                    args = args[:mx]
            call = '/*vtable slot %s*/ %s(%s)' % (
                vt_slot, recv0.text if recv0 else '?', ', '.join(args))
        self.vt_recv_slot = None
        self.vt_recv = None

        if rty is not None:
            te = self.il._type_enum(rty)
            if te == 0x01:
                self.emit(ins.ip, call + ';', asm)
                if mi is not None and m2.name == '.ctor' and not m2.is_static \
                        and hasattr(self.il, '_sf_field_size'):
                    re0 = arg_exprs[0] if arg_exprs else None
                    off = getattr(re0, '_stack_offset', None)
                    dt = self.meta.typedefs[m2.declaring] \
                        if 0 <= m2.declaring < len(self.meta.typedefs) else None
                    sz = self.il._sf_field_size((m2.declaring, 0x11 << 16), 0) \
                        if dt is not None and dt.is_valuetype else None
                    slot = args[0][1:] if args and args[0].startswith('&') else None
                    if slot is None and args and re.match(r'^s_[0-9a-fA-F]+$', args[0]):
                        # the member fold strips the `&` (1899-1912);
                        # a slot-shaped receiver still names its home
                        # (18054: `s_48.ctor(t0, t1)` lost both `&`
                        # and the receiver's stack offset).
                        slot = args[0]
                    if slot is None and off is not None:
                        for addr, slot_nm in self.stack_map.items():
                            if addr == off:
                                slot = slot_nm
                                break
                    if slot is not None:
                        # construction proof, sizing-independent: the
                        # sized store below still needs off+sz (an open
                        # genericinst ctor has no provable size), but
                        # the home is constructed either way.
                        cs = getattr(self, '_ctor_slots', None)
                        if cs is not None:
                            cs.add(slot)
                    if off is not None and sz is not None and slot is not None:
                        self._stack_store(off, sz, Expr(slot, (m2.declaring, 0x11 << 16), 'obj'))
                        self.slot_types[slot] = (m2.declaring, 0x11 << 16)
                return
            dstreg = self._return_value_register(rty)
            isf = dstreg == 'XMM0'
            result = Expr(call, rty,
                          'obj' if te >= 0x10 else ('float' if isf else 'int'))
            self.regs[dstreg] = result
            # An unresolved shared call was always materialized at its call
            # instruction.  Keep that ordering guarantee when consensus adds
            # its type: identity/purity is still unknown, and delaying a
            # one-use expression could move the call across visible effects.
            if shared_rty:
                self._bind(result)
                return
            # An interface dispatch result regularly flows through a stack
            # home (the enumerator) and a phi copy; left lazy, the home's
            # own declaration and the later `_bind` both materialize the
            # call (a duplicated GetEnumerator whose second instance is the
            # one actually iterated). Materialize once at the call
            # instruction instead, like the shared-return path above.
            # Getters keep the inline property render.
            if iface_identity and not getattr(self, 'dry', False):
                base = self.meta.methods[mi].name.rpartition('.')[2]
                if not base.startswith('get_'):
                    self._bind(result)
                    return
            # An ignored non-void result would otherwise vanish: the call
            # runs for effect, so hold it pending and flush a bare statement
            # at the next emit when no use renders it first. Used calls keep
            # their inline render (use-counted by _RegState reads); getters
            # stay lazy since a bare `obj.Prop;` is noise. Short texts cannot
            # be use-traced, so they keep the old drop behavior.
            if not getattr(self, 'dry', False) and mi is not None and not \
                    self.meta.methods[mi].name.rpartition('.')[2].startswith('get_') \
                    and len(call) >= _USE_BIND_MIN:
                if self._dead_shared_forwarder(target, ins):
                    ret = self._dead_shared_forwarder_return(target, ins, call, rty)
                    if ret is not None:
                        self.emit(ins.ip, ret, asm)
                    return
                pc = getattr(self, '_pending_calls', None)
                if pc is None:
                    pc = self._pending_calls = []
                pc.append((result, ins.ip, asm))
            return
        # unresolved-return calls cannot be emitted bare AND kept as a
        # value: the next store/read would re-render the entire call text
        # (`sub_X(...);` then `*(...) = sub_X(...);` -- twin junk). Bind
        # the result: `var s_N = sub_X(...);` is the one statement that
        # carries the call, and every consumer reads s_N. The register
        # map stamps the def position, so the materialization lands
        # exactly where the call instruction sits; a dead result leaves
        # the line in place, which is also correct (the call executes
        # for effect). Dead-var passes keep call-lines.
        # fix 132b: the caller's own code reads XMM0 -- a volatile
        # register the call just clobbered -- as the result, with a
        # scalar width, before touching RAX: the value lives in XMM0.
        if re.fullmatch(r'sub_[0-9a-f]+', name):
            fw = xmm0_result_width(self.bin, ins.next_ip)
            if fw is not None:
                r = Expr('(%s)%s' % ('float' if fw == 4 else 'double', call),
                         _R4_TY if fw == 4 else _R8_TY, 'float')
                self.regs['XMM0'] = r
                self._bind(r)
                return
        r = Expr(call, None, '?')
        self.regs['RAX'] = r
        self._bind(r)
        return

    # ------------------------------------------------------------------
