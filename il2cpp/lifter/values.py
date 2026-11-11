from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.common import csharp_type_name, u64
from il2cpp.expr import Expr, _BARE_HINT_RX, _BARE_TOKEN_RX, _INT_TY, _byref_arg_render, _is_unresolved_gp, _mentions, _merge_arr_proof, _recv_fold
from il2cpp.text import _int_lit, disp_add, strip_outer
from il2cpp.x64 import ARG_XMM, KLASS_ELEMENT_CLASS, KLASS_INITIALIZED, KLASS_STATIC_FIELDS, KLASS_VTABLE

class _ValuesMixin:
    def _stack_arg_texts(self, count, *, callee=False):
        """Current Win64 stack-argument texts, in ABI order.

        Caller-side stack arguments start at [rsp+0x20]. Callee-side stack
        parameters start one slot higher because the return address sits at
        [rsp+0x0], then the 32-byte shadow space, so arg5 is [rsp+0x28].
        Only existing contiguous slots are returned; missing earlier slots are
        not guessed later.
        """
        out = []
        base = 0x28 if callee else 0x20
        sv = getattr(self, 'stack_values', {})
        sm = getattr(self, 'stack_map', {})
        delta = getattr(self, 'rsp_delta', 0)
        for i in range(count):
            key = base + 8 * i + delta
            name = sm.get(key)
            if name is None:
                break
            txt = name
            e = sv.get(name)
            if e is not None and e.text:
                et = e.text
                if re.fullmatch(r'(?:&)?[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*|\[[^\]]+\])*', et) \
                        or re.fullmatch(r'-?(?:0x[0-9A-Fa-f]+|\d+)', et) \
                        or et in ('true', 'false', 'null'):
                    txt = et
            out.append(txt)
        return out

    def _materialize(self, expr: Optional[Expr], limit=100) -> str:
        if expr is None:
            return '???'
        if len(expr.text) > limit:
            v = self.new_var()
            if expr.ty is not None and expr.kind != 'ptr' and not expr.text.startswith('&'):
                if _is_unresolved_gp(expr.ty):
                    self._gp_blocked.add(v)
                else:
                    vt = getattr(self, '_var_types', None)
                    if vt is None:
                        vt = self._var_types = {}
                    vt.setdefault(v, expr.ty)
            if not getattr(self, 'dry', False):
                self.emit(0, 'var %s = %s;' % (v, expr.text), None)
            expr = Expr(v, expr.ty, 'ptr' if expr.text.startswith('&') else expr.kind)
            # keep in a temp so later uses can reference
            self._last_tmp = v
            self._tmp_expr = expr
            return v
        return expr.text

    def _hint_tok(self, e, ty):
        """Type a bare-token operand from its instruction class: a GPR or
        SSE operand has a fixed kind even when no call argument, return or
        typed store ever mentions it. Stack-slot tokens are included: the
        renaming pass reads merged hints for them too."""
        if e is None or e.kind in ('ptr', 'klass', 'arr'):
            return
        if isinstance(getattr(e, 'ty', None), tuple):
            return
        t = e.text
        if not t or t[0] == '&' or not _BARE_HINT_RX.match(t):
            return
        h = getattr(self, '_type_hints', None)
        if h is not None:
            h.setdefault(t, ty)

    def _arty(self, a):
        """Result type for GPR arithmetic: the operand's type when known,
        Int32 when unknown, nothing when the operand smells like a native
        pointer (its arithmetic is address math, not integer math)."""
        if a is None:
            return _INT_TY
        if isinstance(a.ty, tuple):
            return a.ty
        return None if a.kind == 'ptr' else _INT_TY

    def _positional_args(self, args, m2, rty):
        """Render a resolved Win64 call by ABI position, not raw register order.

        The raw call-site list is GPR-first with any live XMM values appended,
        so a direct trim can drop real stack arguments and keep a stale XMM tail
        as a bogus fifth parameter. Rebuild the visible argument list from the
        signature's actual positions: receiver/sret first, float params from
        their XMM slot when they live in the first four positions, and 5th+
        arguments from the stack home area.
        """
        want = m2.param_count + (0 if m2.is_static else 1)
        if self.il.returns_sret(rty):
            want += 1
        gpr_want = min(want, 4)
        out = list(args[:gpr_want])
        if len(out) < gpr_want:
            out.extend(['_'] * (gpr_want - len(out)))
        if want > 4:
            out.extend(self._stack_arg_texts(want - 4))
        xmm = getattr(self, '_xmm_pending', None) or []
        ri = 0 if m2.is_static else 1      # RCX is the receiver when instance
        if self.il.returns_sret(rty):
            ri += 1                        # hidden sret buffer in RCX
        base = ri
        for pi, p in enumerate(self.meta.method_params(m2)):
            pt = self.il.types[p.type] if 0 <= p.type < len(self.il.types) else None
            pt = self._class_type_subst(pt)
            if pt is None:
                break
            bits = pt[1]
            te = (bits >> 16) & 0xFF
            is_float = te in (0x0c, 0x0d) \
                and not ((bits >> 29) & 1) and te != 0x10
            if not is_float:
                continue
            pos = base + pi
            if pos > 3 or pos >= len(out):
                continue
            xe = None
            for k, e in xmm:
                if k == pos:
                    xe = e
                    break
            out[pos] = xe.text if xe is not None and xe.text else '_'
        while len(out) > gpr_want and out[-1] == '_':
            out.pop()
        return out

    def _hint_arg_types(self, args, arg_exprs, mi, rty):
        """Type inference from call sites: a bare-token argument carrying a
        parameter's metadata type. The Win64 assignment is reconstructed
        exactly (receiver/integers fill RCX,RDX,R8,R9, floats fill XMM0-3,
        both in signature order), so each parameter maps to its true slot:
        args[0..3] are the GPR slots (always populated, `_` when unset) and
        the XMM tail was recorded in _xmm_pending. Params on the stack
        (5th+ integer), slots whose register was never set and pointer-kind
        expressions are skipped: the latter hold the *address* for a byref
        parameter, not its value. A valuetype return means RCX carries the
        hidden sret buffer -- including when that buffer is a register-held
        local rather than `&s_N`, which the sret fold above does not catch
        -- so the GPR walk starts one slot later."""
        m2 = self.meta.methods[mi]
        xmm = getattr(self, '_xmm_pending', None) or []
        ri = 0 if m2.is_static else 1      # RCX is the receiver when instance
        # fix 59c: size-tested, see _positional_args -- an enum or other
        # 1/2/4/8-byte struct return spends no slot on a buffer.
        if self.il.returns_sret(rty):
            ri += 1                        # hidden sret buffer in RCX
        base = ri
        # fix 54: the sret test one line up is size-tested 0x11 only, so a
        # GENERICINST return that is really a struct would consume RCX
        # without `ri` knowing, shifting every parameter one slot left.
        # A mis-slotted type HINT is invisible; a mis-slotted `ref` is
        # visible wrongness -- so the arg rewrite below stands down
        # entirely on that shape rather than guess.
        trust = rty is None or self.il._type_enum(rty) != 0x15
        for pi, p in enumerate(self.meta.method_params(m2)):
            pt = self.il.types[p.type] if 0 <= p.type < len(self.il.types) else None
            pt = self._class_type_subst(pt)
            if pt is None:
                break
            e = None
            ai = -1
            # byref (bit 29 or enum 0x10) is pointer-class even when its
            # pointee is float: the machine passes an address in a GPR
            bits = pt[1]
            is_float = (bits >> 16) & 0xFF in (0x0c, 0x0d)                 and not ((bits >> 29) & 1) and ((bits >> 16) & 0xFF) != 0x10
            # fix 53 (todo lead #7, mirrors 42b/_positional_args): register
            # index == parameter position, one shared counter -- NOT a
            # per-class ordinal. An interleaved signature (float, int, ...)
            # would otherwise put the int at RDX instead of R8.
            slot = base + pi
            if is_float:
                for q, (k, xe) in enumerate(xmm):
                    if k == slot:
                        ai = 4 + q
                        e = xe
                        break
            else:
                if slot <= 3:
                    ai = slot
                    e = arg_exprs[slot] if slot < len(arg_exprs) else None
            if ai < 0 or ai >= len(args):
                continue
            # a byref parameter's argument holds the *address*; the pointee
            # type still types the local or stack slot being addressed
            at = args[ai]
            # a bool parameter receives `(cond ? 1 : 0)` (a setcc render of
            # the condition); the ternary is the 0/1 materialization and the
            # param is already bool, so the condition stands alone. Byref
            # params are excluded: their arg is an address render, not a value
            if (bits >> 16) & 0xFF == 0x02 and not ((bits >> 29) & 1) \
                    and ((bits >> 16) & 0xFF) != 0x10:
                m = re.match(r'^\(([^?]+?) \? 1 : 0\)$', at)
                if m:
                    args[ai] = '(%s)' % m.group(1)
                    continue
                # fix 48 (todo lead #3): a Boolean parameter fed the
                # raw int literal the lifter renders for xor edx,edx /
                # mov edx,1 -- the machine passed false/true
                if at in ('0', '1'):
                    args[ai] = 'true' if at == '1' else 'false'
                    continue
            # fix 85: an enum-typed parameter fed a raw integer literal
            # names the member -- the SAME metadata proof the store path
            # (`_fimm`) and the jcc compare path (decompiler.py) have
            # used since batch 39, which the argument path never
            # applied. `new FileStream(text2, 3)` is really
            # `new FileStream(text2, FileMode.Open)`, and the bare 3 is
            # a magic number the reader cannot resolve. Declines unless
            # a constant matches EXACTLY, so a [Flags] combination with
            # no single named member keeps its integer instead of
            # inventing a name. Byref params are excluded exactly as the
            # bool fold above excludes them: their argument renders an
            # address, not a value.
            if (bits >> 16) & 0xFF in (0x11, 0x12, 0x15) \
                    and not ((bits >> 29) & 1):
                ev = _int_lit(at)
                etd = None
                if ev is not None:
                    etd = self._td_of(pt)
                    em = self.il.enum_members(etd) if etd is not None else None
                    if em and ev in em:
                        args[ai] = '%s.%s' % (
                            csharp_type_name(self.meta.typedefs[etd].name),
                            em[ev])
                        continue
                # A typed integer expression is not implicitly convertible to
                # an enum parameter. Shared getter resolution exposes this
                # at StyleEnum<SliceType>.ctor(styleInt.value, keyword): the
                # former object stub supplied a cast at the caller. Keep the
                # conversion where the parameter's closed type proves it.
                if e is not None and not e._unk and e.text == at \
                        and e.ty is not None and not (e.ty[1] >> 29) & 1 \
                        and self.il._type_enum(e.ty) in (
                            0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b):
                    if etd is None:
                        etd = self._td_of(pt)
                    if etd is not None and getattr(
                            self.meta.typedefs[etd], 'is_enum', False):
                        args[ai] = '(%s)(%s)' % (self.il.type_name(pt), at)
                        continue
            if at.startswith('&') and hasattr(self.il, '_sf_field_size'):
                aggregate = self._copied_struct_arg(at, pt)
                if aggregate is not None:
                    args[ai] = aggregate
                    continue
            if at.startswith('&'):
                if (bits >> 29) & 1:
                    pointee = (pt[0], pt[1] & ~(1 << 29))
                elif (bits >> 16) & 0xFF in (0x10, 0x0f):
                    pointee = self.il.type_from_ptr(pt[0])
                else:
                    pointee = None
                if pointee is not None:
                    nm = at[1:]
                    if nm.startswith('s_'):
                        # slot_types is what the renamer reads for slots;
                        # _type_hints is what live deref resolution reads
                        self.slot_types.setdefault(nm, pointee)
                        self._type_hints.setdefault(nm, pointee)
                    elif _BARE_HINT_RX.match(nm):
                        self._type_hints.setdefault(nm, pointee)
                else:
                    ck = getattr(self.il, '_closed_type_key', None)
                    trust_ok = trust and self._byval_struct(pt) \
                        and (ck is None or ck(pt) is not None)
                    if trust_ok:
                        # a by-VALUE struct travels by hidden pointer: `&s_N`
                        # is the value's home, not an address the callee keeps
                        # (the byref case above already returned). The declared
                        # substituted parameter type proves the home's content --
                        # the saved Navigation at Dictionary.Add. setdefault:
                        # first writer wins, same as the byref-slot convention.
                        nm = at[1:]
                        if nm.startswith('s_'):
                            self.slot_types.setdefault(nm, pt)
                            self._type_hints.setdefault(nm, pt)
                # fix 54: now that the declared parameter is in hand,
                # spell the `&` the way C# would. The old render came
                # from decompiler.py's `_ADDR_LOCAL_RX`, whose lookbehind
                # is `(?<=[(,])` while args join with ', ' -- so only the
                # argument right after `(` could ever become `ref`, and
                # all 21,955 such renders in b47_out1 were 'argument 0'
                # regardless of the signature.
                rep = _byref_arg_render(
                    at, bool(((bits >> 29) & 1) or (bits >> 16) & 0xFF == 0x10),
                    self._byval_struct(pt), trust)
                if rep is not None:
                    args[ai] = rep
                continue
            if not _BARE_TOKEN_RX.match(at):
                continue
            if e is not None and (e.kind == 'ptr' or (e.text or '').startswith('&')):
                continue
            self._type_hints.setdefault(at, pt)

    def _tail_method_args(self, mi, args, arg_exprs):
        """Prepare a resolved Win64 direct tail from its declared signature.

        Tails need the same positional rebuild as ordinary calls, but they do
        not naturally arrive with an appended XMM tail. Reconstruct that tail
        here, then let `_positional_args` place floats and stack arguments by
        ABI position. Hidden-sret and generic-return tails retain their legacy
        ABI until their argument/return-buffer model is implemented together.
        """
        m2 = self.meta.methods[mi]
        rty = self.il.types[m2.return_type] if 0 <= m2.return_type < len(self.il.types) else None
        want = m2.param_count + (0 if m2.is_static else 1)
        legacy = list(args[:want])
        while legacy and legacy[-1] == '_':
            legacy.pop()
        self._call_class_args = None
        self._xmm_pending = []
        if self.il.returns_sret(rty) or (rty is not None and self.il._type_enum(rty) == 0x15):
            return legacy
        prepared = list(args[:4])
        prepared.extend(['_'] * (4 - len(prepared)))
        for k, reg in enumerate(ARG_XMM):
            e = self.regs.get(reg)
            if e is not None and e.text and not e._unk:
                self._xmm_pending.append((k, e))
                prepared.append(e.text)
        self._hint_arg_types(prepared, arg_exprs, mi, rty)
        out = self._positional_args(prepared, m2, rty)
        return self._materialize_float_lanes(out, arg_exprs, m2, rty)

    def _materialize_float_lanes(self, out, arg_exprs, m2, rty):
        """Render GPR `?` args with byte-proven float lanes as composites.

        Shared by tails and resolved direct calls (same ri walk
        `_hint_arg_types`/`_positional_args` use, so receivers and
        hidden sret buffers keep their skip): a slot holding an unknown
        rendering over byte-proven float lanes materializes the
        composite at a closed all-float vector slot (67525 saturate).
        Width-4 renders the literal, width-8 the house `(float2)(l0,l1)`
        for Unity.Mathematics.float2 only. Instance/sret/stack/byref/
        double/open/unresolved/uncovered/part-less/text-mismatched all
        decline; the 80548 integer carries decline by construction.
        """
        base = 0 if m2.is_static else 1
        try:
            if self.il.returns_sret(rty):
                base += 1
        except Exception:
            pass
        try:
            params = self.meta.method_params(m2)
        except Exception:
            return out
        for pi, p in enumerate(params):
            pos = base + pi
            if pos > 3 or pos >= len(out) or pos >= len(arg_exprs):
                continue
            if (out[pos] or '').strip() not in ('?', '_', 'unknown'):
                continue
            pty = self.il.types[p.type] \
                if 0 <= p.type < len(self.il.types) else None
            if pty is None or ((pty[1] >> 29) & 1):
                continue
            te = self.il._type_enum(pty)
            width = None
            tname = None
            if te == 0x0c:
                width = 4
            elif te == 0x11:
                td = self._td_of(pty)
                chain = self.il.instance_field_chain(td) \
                    if td is not None else None
                if not chain:
                    continue
                offs = sorted(chain)
                try:
                    width = self.il._sf_field_size(pty, 0)
                except Exception:
                    width = None
                if width == 4 and offs != [0x10]:
                    continue
                if width == 8 and offs != [0x10, 0x14]:
                    continue
                if width not in (4, 8):
                    continue
                fts = []
                for _off in offs:
                    _ti = chain[_off][1]
                    _ft = self.il.types[_ti] \
                        if 0 <= _ti < len(self.il.types) else None
                    fts.append(self.il._type_enum(_ft)
                               if _ft is not None else None)
                if any(_f != 0x0c for _f in fts):
                    continue
                if width == 8:
                    _ttd = self.meta.typedefs[td] \
                        if 0 <= td < len(self.meta.typedefs) else None
                    if _ttd is None or _ttd.namespace != 'Unity.Mathematics' \
                            or _ttd.name != 'float2':
                        continue
                    tname = 'float2'
            else:
                continue
            e = arg_exprs[pos]
            if e is None or getattr(e, '_unk', False):
                continue
            if (e.text or '') != out[pos]:
                continue
            lanes = self._float_lane_texts(e, width)
            if lanes is None:
                continue
            out[pos] = lanes[0] if width == 4 \
                else '(%s)(%s, %s)' % (tname, lanes[0], lanes[1])
        return out

    def _float_lane_texts(self, e, width):
        """Float-suffixed lane texts covering [0, width), else None.

        Consumer-side SIMD recovery: lanes must come from byte-proven
        parts; integer-tainted values (80548: PSRLDQ-popped sources,
        GPR-binop rebuilds that drop parts) carry none and decline.
        """
        if e is None or getattr(e, '_unk', False):
            return None
        if width == 4:
            spans = [(0, 4)]
        elif width == 8:
            spans = [(0, 4), (4, 4)]
        else:
            return None
        f32 = (0, 0x0c << 16)
        out = []
        for off, sz in spans:
            try:
                v = self._piece_value(e, off, sz, f32)
            except Exception:
                return None
            if v is None or not (v.text or '').endswith(('f', 'F')):
                return None
            out.append(v.text)
        return out

    def _kill_one(self, e, lv, seen):
        """Materialize one expression to a temp when its text reads `lv`.
        Identical texts share a temp: text is the value model, so a register
        and a comparison operand holding the same expression are the same
        value and must not print twice."""
        if e is None or not e.text or e.text == '?':
            return e
        if e.text.startswith('&'):
            return e
        if not _mentions(e.text, lv):
            return e
        t = seen.get(e.text)
        if t is not None:
            return t
        v = self.new_var()
        if isinstance(e.ty, tuple) and e.kind != 'ptr' and not e.text.startswith('&'):
            if _is_unresolved_gp(e.ty):
                self._gp_blocked.add(v)
            else:
                vt = getattr(self, '_var_types', None)
                if vt is None:
                    vt = self._var_types = {}
                vt.setdefault(v, e.ty)
        self.emit(0, 'var %s = %s;' % (v, strip_outer(e.text)), None)
        # an address-of temp stays pointer-kind: call-arg type hints must
        # not type it as the pointee
        t = Expr(v, e.ty, 'ptr' if e.text.startswith('&') else e.kind, e.recv)
        # the temp freezes this exact value: identity proofs survive the
        # move (a methodinfo temp that loses `_mi` crashes the delegate
        # path indexing it -- 8 sweep failures -- instead of resolving).
        if getattr(e, '_mi', None) is not None:
            t._mi = e._mi
        if getattr(e, '_usg_idx', None) is not None:
            t._usg_idx = e._usg_idx
        # the temp freezes this exact value, so newarr-exactness and
        # array-klass provenance ride along (same value, same klass).
        if getattr(e, '_newarr', None) is not None:
            t._newarr = e._newarr
        if getattr(e, '_arr_klass', None) is not None:
            t._arr_klass = e._arr_klass
        if getattr(e, '_dry_proof', None) is not None:
            t._dry_proof = e._dry_proof
        # Scalar SSE writes preserve upper lanes.  If kill-on-write freezes
        # the low expression, retain only higher packed lanes that do not
        # themselves read the overwritten lvalue; disputed lanes stay
        # honestly absent.
        parts = getattr(e, '_parts', None)
        if parts:
            frozen = Expr(v, e.ty, e.kind)
            kept = []
            for lo, value, off, count in parts:
                if lo == 0 and off == 0 and value.text == e.text:
                    kept.append((lo, frozen, off, count))
                elif _mentions(value.text, lv):
                    saved = self._kill_one(value, lv, seen)
                    if saved is not value:
                        kept.append((lo, saved, off, count))
                else:
                    kept.append((lo, value, off, count))
            if kept:
                t._parts = kept
        seen[e.text] = t
        return t

    def _kill_stale(self, lv):
        """Kill-on-write: a store to `lv` invalidates every live register --
        and every captured comparison operand -- whose symbolic text reads
        `lv`: that text re-renders at each later use and would pick up the
        post-store value once the store lands. Materialize each such
        expression to a temp before the store and rebind it, so the
        pre-store value survives under a stable name."""
        seen = {}
        # items(), not a keyed loop: this walks every register looking for
        # stale text, and reads through the counting dict would count as uses
        for r, e in list(self.regs.items()):
            # `lv not in e.text` is the C-speed miss filter; _mentions only
            # settles the token boundary on actual substring hits
            if e is None or not e.text or e.text == '?' or lv not in e.text:
                continue
            if r == '!flags':
                # fix 131: the cross-block flags sentinel is a merge token
                # (`lhs<0x01>rhs`), not a value; freezing it emitted an
                # `object objN = <cond operand>` twin. The pair itself is
                # handled below.
                continue
            self.regs[r] = self._kill_one(e, lv, seen)
        if self.flags is not None \
                and self.flags is getattr(self, '_carried_flags', None):
            # fix 131: a pair inherited from the predecessor's jcc was
            # already rendered there; freezing it here would evaluate its
            # text a second time (`object objN = call(...)` twins). The
            # later reader, if any, sees no flags -- the honest unknown.
            _lhs, _rhs = self.flags
            if any(x is not None and x.text and lv in x.text for x in (_lhs, _rhs)):
                self.flags = None
        if self.flags is not None:
            lhs, rhs = self.flags
            nl = lhs if (lhs is None or not lhs.text or lv not in lhs.text) \
                else self._kill_one(lhs, lv, seen)
            nr = rhs if (rhs is None or not rhs.text or lv not in rhs.text) \
                else self._kill_one(rhs, lv, seen)
            if nl is not lhs or nr is not rhs:
                # fix 60: re-rendering stale text is not a new flag
                # write, so the recorded setter must survive it
                _mn0 = getattr(self, '_flags_mn', None)
                self.flags = (nl, nr)
                self._flags_mn = _mn0

    # ------------------------------------------------------------------
    # (mem_expr used to sit here: a klass/sfblob-aware [base+disp] folder
    # with no callers -- every deref went through _field_expr instead,
    # which is why *(typeof(X) + 0xb8) rendered raw until its branches
    # moved into _field_expr.)

    def _recv_is_vt(self, base: Expr) -> bool:
        """True when base's (hinted) type is a value type -- its
        field chain offsets carry the 0x10 boxed header, and it has
        no object header to load a klass from."""
        ty = base.ty
        if ty is None and base.text and getattr(self, '_type_hints', None):
            ty = self._type_hints.get(base.text)
        td_idx = self._td_of(ty)
        return td_idx is not None and self.meta.typedefs[td_idx].is_valuetype

    def _field_expr(self, base: Expr, disp: int, size: int, elem_fold=False) -> Expr:
        _ifm = getattr(base, '_ifm', None)
        if _ifm is not None and len(_ifm) == 4 and disp in (0, 8) and size == 8:
            # fix 139: VirtualInvokeData.{methodPtr, method} of a resolved
            # interface slot; `_call` renders `call reg` through the first,
            # the second is the hidden MethodInfo the arity trim drops.
            # Neither may bind a temp when it rides an argument register.
            pe = Expr('*(%s %s)' % (base.text, disp_add(disp)), None, 'ptr')
            pe._ifm = _ifm + ('methodPtr' if disp == 0 else 'method',)
            pe._no_bind = True
            return pe
        if size == 8 and getattr(self, '_xor_twin_loads', None) \
                and getattr(self, '_cur_ip', None) in self._xor_twin_loads:
            # proved packed-xor twin lane (double3 negate): the
            # packed twins keep member sugar, the scalar lane stays
            # a raw deref -- refining it also mistypes its store.
            return Expr('*(%s %s)' % (base.text, disp_add(disp)), None, 'ptr')
        if base.kind == 'ptr' and (base.text or '').startswith('&'):
            # &s_N addressing a typed valuetype slot (the sret buffer
            # echoed in RAX after a struct-return call): member loads
            # and stores read the slot's struct fields, not raw byte
            # offsets -- normalize onto the kind-'local' slot path
            nm = base.text[1:]
            sty = self.slot_types.get(nm)
            if sty is not None:
                std_idx = self._td_of(sty)
                if std_idx is not None and self.meta.typedefs[std_idx].is_valuetype:
                    # an access WIDER than the member it starts at spans
                    # more than one field (`movsd [rcx],xmm0` writes
                    # Vector3.x AND .y): naming only the first member
                    # silently drops the rest, so keep the raw deref
                    _fm = self.il.instance_field_chain(std_idx)
                    _fe = _fm.get(disp + 0x10) if _fm else None
                    _fsz = None
                    if _fe is not None and hasattr(self.il, '_sf_field_size'):
                        _fti = _fe[1]
                        _fsz = self.il._sf_field_size(
                            self.il.types[_fti] if 0 <= _fti < len(self.il.types)
                            else None, 0)
                    if _fsz is not None and size and size > _fsz:
                        return Expr('*(%s %s)' % (base.text, disp_add(disp)), None, 'ptr')
                    base = Expr(nm, sty, 'local')
        if base.kind == 'obj' and disp == 0 and not self._recv_is_vt(base):
            # klass pointer load: mov rax,[obj] -- never for a value
            # type receiver: an unboxed struct has no header, [r+0]
            # is its first field
            ke = self._mk('%s.getClass()' % _recv_fold(base.text), base.ty, 'klass')
            ke.recv = base
            return ke
        # klass layout: the static-fields blob, vtable slots, name/init flags.
        # A typeof usage loaded via LEA carries kind 'usage' -- same layout.
        if base.kind == 'klass' or (base.kind == 'usage'
                                    and (base.text or '').startswith('typeof(')):
            if disp == KLASS_STATIC_FIELDS:
                se = Expr('%s.__static_fields' % base.text, base.ty, 'sfblob')
                if getattr(base, '_td', None) is not None:
                    se._td = base._td
                return se
            if disp >= KLASS_VTABLE and (disp - KLASS_VTABLE) % 16 == 0:
                ve = Expr('%s.vtable[%d]' % (base.text, (disp - KLASS_VTABLE) // 16),
                          None, 'vtmethod')
                ve.recv = base.recv
                return ve
            km = self._klass_member(disp)
            if km != '%#x' % disp:
                kme = Expr('%s.%s' % (base.text, km), base.ty, 'kmember')
                # fix 140: the hierarchy check names its object
                kme._hobj = getattr(base, 'recv', None)
                return kme
            return Expr('*(%s %s)' % (base.text, disp_add(disp)), None, 'ptr')
        if base.kind == 'sfblob':
            td_idx = self._td_of(base.ty)
            if td_idx is None:
                # 71c: the owner type stamped at usage-slot decode time
                # -- the only witness when the typeof Expr's own .ty
                # could not be derived (BSS runtime-cache cells).
                td_idx = getattr(base, '_td', None)
            nm = None
            fty = None
            if td_idx is not None:
                # fix 72: static_off_path resolves an inner component
                # through the owning static field's own value type
                # (unboxed blob storage) where the raw base-offset map
                # missed -- zeroVector.z, upVector.y, matrix elements.
                ent = self.il.static_off_path(td_idx, disp,
                                                base.ty)
                if ent is not None:
                    # fix 74: the second element is the field's
                    # Il2CppType tuple itself (a substituted
                    # genericinst field has no field-table index)
                    nm, fty = ent
            if nm:
                fte = self.il._type_enum(fty)
                fkind = 'arr' if fte in (0x1d, 0x14) else (
                    'str' if fte == 0x0e else (
                        'float' if fte in (0x0c, 0x0d) else (
                            'obj' if fte >= 0x10 else 'int')))
                owner = base.text.replace('.__static_fields', '')
                if owner.startswith('typeof(') and owner.endswith(')'):
                    owner = owner[7:-1]
                return Expr('%s.%s' % (owner, nm), fty, fkind)
            return Expr('%s.__static_%x' % (base.text, disp), None, 'obj')
        if base.kind == 'local' and base.text in self.slot_types:
            # a typed stack slot (&s_N given to a byref/sret) resolves its
            # struct members; chain offsets carry the 0x10 header
            sty = self.slot_types[base.text]
            std_idx = self._td_of(sty)
            if std_idx is not None and self.meta.typedefs[std_idx].is_valuetype:
                fm = self.il.instance_field_chain(std_idx)
                if fm is not None and (disp + 0x10) in fm:
                    name, ti = fm[disp + 0x10]
                    ty = self.il.types[ti]
                    return Expr('%s.%s' % (_recv_fold(base.text), name), ty, self._ty_kind(ty))
        ty = base.ty
        text = base.text
        # type inference, live: a bare temp hinted by an earlier call/store
        # resolves this deref to a real member instead of *(tok + 0x18)
        if ty is None and text and getattr(self, '_type_hints', None):
            ty = self._type_hints.get(text)
        # arrays
        if base.kind == 'arr':
            if disp in (0x10, 0x18):
                return Expr('%s.Length' % _recv_fold(text), _INT_TY, 'int')
            if disp >= 0x20:
                ety = self._elem_type(base.ty)
                # the index divides by the ELEMENT STRIDE, never the
                # access width: an 8-byte read from [arr+0x2c] of a
                # 12-byte Vector3 element is element 1, not element 4.
                # An unknown stride or a mid-element offset keeps the
                # raw deref instead of a plausible-wrong index.
                _sf = getattr(self.il, '_sf_field_size', None)
                stride = _sf(ety, 0) if (_sf is not None and ety is not None) else None
                if stride:
                    k = disp - 0x20
                    if k % stride == 0:
                        return Expr('%s[%#x]' % (_recv_fold(text), k // stride),
                                    ety, self._ty_kind(ety))
                return Expr('*(%s %s)' % (text, disp_add(disp)), None, 'ptr')
        if base.kind == 'str':
            if disp in (0x10, 0x18):
                return Expr('%s.Length' % _recv_fold(text), _INT_TY, 'int')
            if disp == 0x14:
                return Expr('%s[0]' % _recv_fold(text), None, 'char')
        # instance fields by type offsets (whole inheritance chain).
        # A PTR/BYREF base (a typed native pointer -- `SimulationMessage*
        # obj10` off Allocate's typed return; ground truth BabyDoll.
        # Rpc_ChangeHittableHealth 0x18060A690) resolves members through
        # its POINTEE. Unwrap HERE, at the member-resolution site, not in
        # _td_of (which feeds receiver folding and vtable dispatch, where
        # a pointer must not silently act as its pointee). An unmanaged T*
        # to a value type targets UNBOXED data (Allocate allocates
        # capacity + sizeof(T): the struct sits at raw 0, payload after),
        # so it shares the local-slot boxed-offset convention (disp+0x10);
        # a T* to a class targets the object and uses raw disp. Pointer
        # members render `->`; offsets past the struct (variable-length
        # payload) miss the chain and keep the honest raw deref.
        _ptr_base = ty is not None and self.il._type_enum(ty) in (0x0f, 0x10)
        td_idx = None
        if _ptr_base:
            _pt = self.il.type_from_ptr(ty[0])
            td_idx = self._td_of(_pt) if _pt is not None else None
        if td_idx is None:
            td_idx = self._td_of(ty)
        if td_idx is not None:
            chain = self.il.instance_field_chain(td_idx)
            if chain:
                _vt = self.meta.typedefs[td_idx].is_valuetype
                _sep = '->' if _ptr_base else '.'
                if not _vt and disp in chain:
                    fname, ftype_idx = chain[disp]
                    fty0 = self.il.types[ftype_idx] if 0 <= ftype_idx < len(self.il.types) else None
                    fty = self._recv_member_ty(td_idx, ty, fty0)
                    fte = self.il._type_enum(fty if fty is not None else fty0)
                    fkind = 'arr' if fte in (0x1d, 0x14) else (
                        'str' if fte == 0x0e else (
                            'float' if fte in (0x0c, 0x0d) else (
                            'obj' if fte >= 0x10 else 'int')))
                    fe = Expr('%s%s%s' % (_recv_fold(text), _sep, fname), fty, fkind)
                    if fname == 'invoke_impl' and self._delegate_invoke_method(ty) is not None:
                        fe.kind = 'delegate_impl'
                        fe.recv = base
                    return fe
                if _vt and (disp + 0x10) in chain:
                    fname, ftype_idx = chain[disp + 0x10]
                    fty0 = self.il.types[ftype_idx] if 0 <= ftype_idx < len(self.il.types) else None
                    fty = self._recv_member_ty(td_idx, ty, fty0)
                    fte = self.il._type_enum(fty if fty is not None else fty0)
                    fkind = 'arr' if fte in (0x1d, 0x14) else ('obj' if fte >= 0x10 else 'int')
                    if _ptr_base and fte in (0x0c, 0x0d):
                        fkind = 'float'
                    elif _ptr_base and fte == 0x0e:
                        fkind = 'str'
                    return Expr('%s%s%s' % (_recv_fold(text), _sep, fname), fty, fkind)
        if elem_fold and disp == KLASS_ELEMENT_CLASS and base.kind == 'ptr':
            # element klass of a newarr-proven array: [arrklass+0x40] is
            # Il2CppClass.element_class. The provenance was captured when
            # the klass pointer was loaded ([arr+0] below); the fold fires
            # only on the load path, so stores, LEA and CMP keep today's
            # raw spelling. A proved node renders `typeof(E)`, which the
            # existing IsInst fold in `_call` turns into `obj as E`.
            ak = getattr(base, '_arr_klass', None)
            if ak is not None:
                en = self._elem_klass_name(ak[0], ak[1])
                if en is not None:
                    return Expr('typeof(%s)' % en[0], en[1], 'klass')
        e = Expr('*(%s %s)' % (text, disp_add(disp)), None, 'ptr')
        if base.kind == 'arr' and disp == 0:
            # klass-pointer load off a managed array (Il2CppArray.klass is
            # at offset 0): record the array's type and newarr-exactness
            # for the +0x40 fold above. The effective proof covers a
            # dry-vintage array base too (loop-carried arrays read dry
            # end_states). Provenance only -- the text, kind and type
            # this returns are byte-identical to today's.
            pt = _merge_arr_proof(base)
            e._arr_klass = (pt if pt is not None else base.ty, pt is not None)
        return e

    def _field_index_for_offset(self, td_idx, disp):
        td = self.meta.typedefs[td_idx]
        fo = self.il.field_offsets[td_idx]
        for k, off in enumerate(fo):
            if off == disp:
                return td.field_start + k
        return None

    def _elem_type(self, ty):
        """Element type of an szarray/multidim type tuple."""
        if not isinstance(ty, tuple):
            return None
        te = (ty[1] >> 16) & 0xFF
        if te in (0x1d, 0x14):
            return self.il.type_from_ptr(ty[0])
        return None

    def _elem_klass_name(self, arr_ty, exact):
        """`(name, ety)` for `[arrklass+0x40]` at an IsInst site, else None.

        Soundness rests on exactness: array covariance lets an `E[]`-typed
        local hold a `D[]` (D : E) at runtime, in which case element_class
        is D, not E. Only a same-method newarr (`exact`, from `_newarr`)
        fixes the runtime klass to exactly E[], so params, fields, statics
        and `as`-refinements all decline here. The element itself must be
        directly nameable too: a reference type (C# `as` is illegal on
        value types), closed (no VAR/MVAR), and not System.Object (an `as
        object` fold is noise, and `type_name` also spells its own
        fallback as `object`). Generic-instance and nested-array elements
        decline in this slice -- honest markers, follow-up work.
        """
        if not exact:
            return None
        ety = self._elem_type(arr_ty)
        if ety is None:
            return None
        te = self.il._type_enum(ety)
        if te == 0x0e:
            return (self.il.type_name(ety), ety)
        if te == 0x15:
            return self._geninst_as_target(ety)
        if te not in (0x11, 0x12):
            return None
        td = self._td_of(ety)
        if td is None:
            return None
        tdt = self.meta.typedefs[td] \
            if 0 <= td < len(self.meta.typedefs) else None
        if tdt is None or tdt.is_valuetype or tdt.is_enum:
            return None
        try:
            nm = self.il.type_name(ety)
        except Exception:
            return None
        if not nm or nm in ('object', 'System.Object') \
                or nm.startswith('object<') or '(' in nm or ')' in nm:
            return None
        return (nm, ety)

    def _geninst_as_target(self, ety):
        """`(name, ety)` for a closed generic-instance class element.

        Slice 1 of the IsInst remainder (see `_elem_klass_name`):
        landing-9's newarr proof fixes the array's runtime klass to
        exactly `E[]`, so `[klass+0x40]` is definitionally `E` and
        `isinst(obj, E)` renders `obj as E`. The gate admits only
        closed instantiations of non-valuetype, non-enum definitions
        with a nameable spelling; everything else keeps the honest
        marker (open VAR/MVAR, unreadable args, nested-definition
        bases, `Nullable<T>` and other valuetypes by construction,
        `object`, paren spellings, nested arrays).
        """
        if self._open_generic(ety):
            return None
        args = self._generic_class_args(ety)
        if not args:
            return None
        try:
            o = self.bin.va2off(ety[0])
        except Exception:
            return None
        if o is None:
            return None
        try:
            basep = u64(self.bin.d, o)
        except Exception:
            return None
        base = self.il.type_from_ptr(basep) if basep else None
        if base is None or self.il._type_enum(base) not in (0x11, 0x12):
            return None
        td = self._td_of(base)
        tdt = self.meta.typedefs[td] \
            if td is not None and 0 <= td < len(self.meta.typedefs) else None
        if tdt is None or tdt.is_valuetype or tdt.is_enum:
            return None
        try:
            nm = self.il.type_name(ety)
        except Exception:
            return None
        if not nm or nm in ('object', 'System.Object') \
                or nm.startswith('object<') or '(' in nm or ')' in nm:
            return None
        return (nm, ety)

    def _open_generic(self, ty, depth=0):
        """True if VAR/MVAR (0x13/0x1e) occurs in `ty` at any depth."""
        if depth > 8:
            return True
        if ty is None:
            return True
        if not isinstance(ty, tuple) or len(ty) != 2:
            return False
        te = self.il._type_enum(ty)
        if te in (0x13, 0x1e):
            return True
        if te == 0x15:
            # unreadable args (no bin/va2off in test doubles, corrupt
            # rows) decline: openness is unprovable, never assumed.
            try:
                args = self._generic_class_args(ty)
            except Exception:
                return True
            if not args:
                return True
            return any(self._open_generic(a, depth + 1) for a in args)
        if te in (0x1d, 0x14):
            inner = self._elem_type(ty)
            if inner is None:
                return True
            return self._open_generic(inner, depth + 1)
        if te in (0x0f, 0x10):
            inner = self.il.type_from_ptr(ty[0])
            if inner is None:
                return True
            return self._open_generic(inner, depth + 1)
        return False

    def _is_byte_ptr_ty(self, ty) -> bool:
        """A genuine metadata `byte*` tuple (PTR-to-U1), reused for
        untyped payload cursors -- never fabricated, so type_name
        spells `byte*` through the ordinary declaration path."""
        if not isinstance(ty, tuple) or self.il._type_enum(ty) != 0x0f:
            return False
        try:
            inner = self.il.type_from_ptr(ty[0])
        except Exception:
            return False
        return self.il._type_enum(inner) == 0x05

    def _byte_ptr_ty(self):
        """First metadata `byte*` row, cached per Lifter instance
        (binary-local, like all lifter state). None when the binary
        declares no byte pointer -- callers keep today's spelling."""
        t = getattr(self, '_byte_ptr_cache', None)
        if t is None:
            for ty in self.il.types:
                if self._is_byte_ptr_ty(ty):
                    t = self._byte_ptr_cache = ty
                    break
        return t

    def _is_byte_cursor(self, e) -> bool:
        """A bound `(byte*)P + N` payload cursor declares `byte*`.
        Arithmetic on byte* is always byte-exact, so the declaration
        is honest where a scaled T* spelling would invent semantics
        (see _bind). Other pointer temps stay `object`."""
        return e is not None and e.kind == 'ptr' \
            and self._is_byte_ptr_ty(e.ty)

    def _test_is_value(self, value):
        if value is None:
            return False
        ty = value.ty
        if ty is None:
            ty = getattr(self, '_type_hints', {}).get(value.text)
        if ty is not None:
            te = self.il._type_enum(ty)
            if te in (0x11, 0x18, 0x19):
                try:
                    tn = self.il.type_name(ty)
                except Exception:
                    tn = ''
                if tn in ('System.IntPtr', 'System.UIntPtr'):
                    return False
            if te == 0x11:
                return True
            return te in range(0x02, 0x0e) or te in (0x18, 0x19)
        return False

    def _ty_kind(self, ty):
        te = self.il._type_enum(ty) if ty else 0
        if te in (0x1d, 0x14):
            return 'arr'
        if te == 0x0e:
            return 'str'
        if te in (0x0c, 0x0d):
            return 'float'
        if te >= 0x10:
            return 'obj'
        return 'int'

    def _td_of(self, ty):
        """TypeDef for CLASS/VALUETYPE/OBJECT or GENERICINST-of-class."""
        if ty is None:
            return None
        data, bits = ty
        te = (bits >> 16) & 0xFF
        if te in (0x11, 0x12):
            return data if 0 <= data < len(self.meta.typedefs) else None
        if te == 0x1c:
            find_object = getattr(self.il, '_system_object_td', None)
            return find_object() if find_object is not None else None
        if te == 0x15:
            synth = getattr(self.il, '_synthetic_lookup', lambda v: None)(data)
            if synth is not None:
                base_tup = synth[0]
                if base_tup:
                    te2 = self.il._type_enum(base_tup)
                    if te2 in (0x11, 0x12) and base_tup[0] < len(self.meta.typedefs):
                        return base_tup[0]
                return None
            o = self.bin.va2off(data)
            if o is None:
                return None
            t = self.il.type_from_ptr(u64(self.bin.d, o))
            if t:
                te2 = self.il._type_enum(t)
                if te2 in (0x11, 0x12) and t[0] < len(self.meta.typedefs):
                    return t[0]
        return None

    def _delegate_invoke_method(self, ty):
        """Return the MethodDef row for a delegate type's Invoke method."""
        td_idx = self._td_of(ty)
        if td_idx is None:
            return None
        td = self.meta.typedefs[td_idx]
        for mi in range(td.method_start, td.method_start + td.method_count):
            if 0 <= mi < len(self.meta.methods):
                m = self.meta.methods[mi]
                if m.name == 'Invoke' and not m.is_static:
                    return mi
        return None

    def _type_param_owners(self, ty, out, depth=0):
        """Fix 133b: collect the generic-container owner of every VAR in
        `ty` into `out`; False when an MVAR occurs or a shape is
        unreadable (the caller then declines)."""
        if depth > 8 or ty is None or not isinstance(ty, tuple) or len(ty) != 2:
            return False
        te = self.il._type_enum(ty)
        if te == 0x1e:
            return False
        if te == 0x13:
            gi = ty[0]
            if not (0 <= gi < len(self.meta.generic_parameters)):
                return False
            out.add(self.meta.generic_parameters[gi][0])
            return True
        if te == 0x15:
            args = self._generic_class_args(ty)
            if not args:
                return False
            return all(self._type_param_owners(a, out, depth + 1) for a in args)
        if te in (0x1d, 0x14):
            return self._type_param_owners(self._elem_type(ty), out, depth + 1)
        if te in (0x0f, 0x10):
            return self._type_param_owners(self.il.type_from_ptr(ty[0]), out, depth + 1)
        return True

    def _recv_member_ty(self, td_idx, recv_ty, fty):
        """Fix 133b: a member's field type as seen through its receiver.

        Closed field types pass through. An open one (`T[]`) is kept
        only when all its parameters belong to the receiver typedef's
        own container: closed through a GENERICINST receiver's
        arguments, or left in scope for the definition's own `this`.
        Otherwise None -- the member keeps its name, not a foreign `T`.
        """
        try:
            if fty is None or not self._open_generic(fty):
                return fty
            owners = set()
            if not self._type_param_owners(fty, owners) or not owners:
                return None
            gc = self.meta.typedefs[td_idx].generic_container
            if gc < 0 or owners != {gc}:
                return None
            if recv_ty is None or self.il._type_enum(recv_ty) != 0x15:
                return fty
            args = self._generic_class_args(recv_ty)
            if not args or any(a is None for a in args):
                return None
            if self.il._type_enum(fty) == 0x1d and not (fty[1] >> 29) & 1:
                se = self.il._subst_closed(self.il.type_from_ptr(fty[0]), tuple(args), None)
                row = self._closed_szarray_row(se)
                if row is None and se is not None and self._is_ref_elem(se):
                    row = self._closed_szarray_row((0, 0x1c << 16))
                return row
            return self.il._subst_closed(fty, tuple(args), None)
        except Exception:
            return None

    def _is_ref_elem(self, ty):
        """Fix 133b: a non-byref reference type (class, string, object,
        array, class GENERICINST) -- covariant into `object[]`."""
        if ty is None or (ty[1] >> 29) & 1:
            return False
        te = self.il._type_enum(ty)
        if te in (0x0e, 0x12, 0x1c, 0x1d, 0x14):
            return True
        if te == 0x15:
            return not self._byval_struct(ty)
        return False

    def _closed_szarray_row(self, elem):
        """Fix 133b: the binary's non-byref SZARRAY row whose element is
        structurally `elem` (closed), else None. Index built once."""
        if elem is None:
            return None
        ek = self.il._closed_type_key(elem)
        if ek is None:
            return None
        idx = self.il.__dict__.get('_szarray_by_elem')
        if idx is None:
            idx = {}
            for t in self.il.types:
                if not t or ((t[1] >> 16) & 0xFF) != 0x1d or (t[1] >> 29) & 1:
                    continue
                try:
                    k = self.il._closed_type_key(self.il.type_from_ptr(t[0]))
                except Exception:
                    k = None
                if k is not None:
                    idx.setdefault(k, t)
            self.il.__dict__['_szarray_by_elem'] = idx
        return idx.get(ek)

    def _generic_class_args(self, ty):
        """Concrete Il2CppType arguments of a GENERICINST, if readable."""
        if ty is None or self.il._type_enum(ty) != 0x15:
            return None
        synth = getattr(self.il, '_synthetic_lookup', lambda v: None)(ty[0])
        if synth is not None:
            return list(synth[1])
        o = self.bin.va2off(ty[0])
        if o is None:
            return None
        io = self.bin.va2off(u64(self.bin.d, o + 8))
        if io is None:
            return None
        argc = u64(self.bin.d, io)
        argv = u64(self.bin.d, io + 8)
        out = []
        for k in range(min(argc, 16)):
            tp = self.bin.qword(argv + k * 8) if argv else None
            out.append(self.il.type_from_ptr(tp) if tp else None)
        return out

    def _proved_struct_home(self, info, args, rty):
        """(slot, type) for a proved-generic struct home, else None.

        A closed valuetype instantiation passed by hidden pointer proves
        the home's content: for an instance method RCX is this-or-buffer
        and for a struct return RCX is the buffer -- in both cases args[0]
        names the struct home when it spells `&s_N` (23762: the
        enumerator homes fed to GetEnumerator/MoveNext/Dispose, whose
        MethodRef slots prove closed `Enumerator<Selectable,Navigation>`
        identities). Static non-struct calls keep today's spelling
        (parameter territory, covered by arg hints), and any byref- or
        pointer-typed formal parameter declines (the `&s_N` could be its
        argument, not a struct home). Only slot_types/_type_hints gain
        entries; rendering, sret and trust paths are untouched."""
        if not info or info[0] != 'generic':
            return None
        synth_fn = getattr(self.il, '_synthetic_inst', None)
        spec_args_fn = getattr(self.il, '_method_spec_type_args', None)
        specs = getattr(self.il, 'method_specs', None)
        methods = getattr(self.meta, 'methods', None)
        typedefs = getattr(self.meta, 'typedefs', None)
        types = getattr(self.il, 'types', None)
        if None in (synth_fn, spec_args_fn, specs, methods, typedefs, types):
            return None
        if not isinstance(info, tuple) or len(info) != 2:
            return None
        if not (0 <= info[1] < len(specs)):
            return None
        spec = specs[info[1]]
        if not isinstance(spec, tuple) or len(spec) != 3:
            return None
        if not (0 <= spec[0] < len(methods)):
            return None
        m = methods[spec[0]]
        td_idx = getattr(m, 'declaring', -1)
        if not (0 <= td_idx < len(typedefs)):
            return None
        td = typedefs[td_idx]
        if not getattr(td, 'is_valuetype', False):
            return None
        class_args = spec_args_fn(spec[1])
        if not class_args:
            return None
        gdecl = synth_fn((td_idx, 0x11 << 16), tuple(class_args))
        if gdecl is None:
            return None
        if getattr(m, 'is_static', True):
            if not isinstance(rty, tuple) or len(rty) != 2:
                return None
            if ((rty[1] >> 16) & 0xFF) != 0x11 or ((rty[1] >> 29) & 1):
                return None
            try:
                params = self.meta.method_params(m)
            except Exception:
                return None
            for p in params:
                pti = getattr(p, 'type', -1)
                pt = types[pti] if 0 <= pti < len(types) else None
                if not isinstance(pt, tuple) or len(pt) != 2:
                    return None
                if ((pt[1] >> 29) & 1) or ((pt[1] >> 16) & 0xFF) in (0x0f, 0x10):
                    return None
        if not args or not re.fullmatch(r'&s_[0-9a-fA-F]+', args[0] or ''):
            return None
        return (args[0][1:], gdecl)

    def _hint_accessor_recv(self, recv, m2):
        """(slot, type) for a property-accessor receiver, else None.

        A resolved instance accessor call proves its receiver's type
        through the declaring typedef (23762: `set_navigation` on an
        untyped `s_90` home proves Selectable). Only slots and bare
        temps qualify; dotted receivers already resolve through their
        base, and `this` needs nothing. Address-taken `&s_N` records on
        the home when the owner is a value type (byref-`this` homes hold
        the struct). Open generic owners decline (instantiation proof
        is separate machinery), as do type-token, address and method
        kinds. The caller records the pair with setdefault."""
        if recv is None or m2 is None:
            return None
        if getattr(m2, 'is_static', True):
            return None
        td_idx = getattr(m2, 'declaring', -1)
        typedefs = getattr(self.meta, 'typedefs', None)
        if typedefs is None or not (0 <= td_idx < len(typedefs)):
            return None
        td = typedefs[td_idx]
        if getattr(td, 'generic_container', -1) != -1:
            return None
        text = getattr(recv, 'text', None) or ''
        kind = getattr(recv, 'kind', None)
        if kind in ('ptr', 'klass', 'usage', 'sfblob', 'initflag',
                    'methodinfo', 'fptr', 'vtmethod', 'null'):
            if not (kind == 'ptr' and text.startswith('&')
                    and getattr(td, 'is_valuetype', False)):
                return None
            nm = text[1:]
        else:
            nm = text
        if not re.fullmatch(r's_[0-9a-fA-F]+|t\d+', nm):
            return None
        ty = (td_idx, (0x11 << 16) if getattr(td, 'is_valuetype', False)
              else (0x12 << 16))
        return (nm, ty)

    def _class_type_subst(self, ty):
        """Substitute a delegate TypeDef's VAR with its instance argument."""
        args = getattr(self, '_call_class_args', None)
        if ty is None or not args or self.il._type_enum(ty) != 0x13:
            return ty
        gi = ty[0]
        if not (0 <= gi < len(self.meta.generic_parameters)):
            return ty
        ordinal = self.meta.generic_parameters[gi][4]
        return args[ordinal] if 0 <= ordinal < len(args) and args[ordinal] else ty

    def _byval_struct(self, ty):
        """fix 54: True when `ty` is a non-byref VALUETYPE -- including a
        GENERICINST whose open type is a struct (ReadOnlySpan<char>,
        Nullable<T>, the 616+595 -site shapes in the b48 census). The
        0x15 unwrap mirrors `_td_of` exactly. A generic CLASS
        instantiation (List<int>) is a reference passed in the register
        directly and is deliberately excluded: a `&` at such a slot
        means the mapping is wrong, not that the struct is big."""
        if ty is None:
            return False
        bits = ty[1]
        if (bits >> 29) & 1:
            return False
        te = (bits >> 16) & 0xFF
        if te == 0x11:
            return True
        if te != 0x15:
            return False
        synth = getattr(self.il, '_synthetic_lookup', lambda v: None)(ty[0])
        if synth is not None:
            base_tup = synth[0]
            return bool(base_tup) and self.il._type_enum(base_tup) == 0x11
        try:
            o = self.bin.va2off(ty[0])
            if o is None:
                return False
            t = self.il.type_from_ptr(u64(self.bin.d, o))
        except Exception:
            return False
        return bool(t) and self.il._type_enum(t) == 0x11

    def _struct_home_ty(self, e):
        """Proved struct type for a value stored into a stack home.

        A whole-field XMM/GPR value (e.g. an m_Navigation load) carries
        its struct type through the register; recording it on the slot
        lets the renamer declare the home honestly instead of `object`.
        Partial aggregate slices never qualify; open generics, byrefs
        and address-kind values decline, same as the call-site hints.
        """
        if e is None or not isinstance(getattr(e, 'ty', None), tuple):
            return None
        if getattr(e, 'kind', None) not in ('obj', 'local', 'float'):
            return None
        if getattr(e, '_slice', None) is not None \
                or getattr(e, '_parts', None) is not None:
            return None
        ty = e.ty
        if ((ty[1] >> 29) & 1) or ((ty[1] >> 16) & 0xFF) != 0x11:
            return None
        if self.il._closed_type_key(ty) is None:
            return None
        td = self._td_of(ty)
        if td is None or not self.meta.typedefs[td].is_valuetype:
            return None
        return ty

    def _klass_member(self, disp):
        return {KLASS_STATIC_FIELDS: 'static_fields', KLASS_INITIALIZED: 'initialized',
                0x10: 'name', 0x18: 'namespace',
                # v31 layout, confirmed against the compiled IsInst fast
                # path: the depth byte at 0x130 indexes the hierarchy array
                # at 0xc8 (hierarchy[target.depth - 1] == target)
                0xc8: 'typeHierarchy', 0x130: 'typeHierarchyDepth'}.get(disp, '%#x' % disp)

    # ------------------------------------------------------------------
    CMP_OPS = {Mnemonic.JE: '==', Mnemonic.JNE: '!=', Mnemonic.JL: '<', Mnemonic.JGE: '>=',
               Mnemonic.JG: '>', Mnemonic.JLE: '<=', Mnemonic.JA: '>', Mnemonic.JBE: '<=',
               Mnemonic.JB: '<', Mnemonic.JAE: '>='}
    # same op set as CMP_OPS/SETcc, for CMOVcc's flags-derived condition
    # (batch 29). The six flag-specific variants (S/NS/O/NO/P/NP) are
    # deliberately absent -- CMOVcc.get(mn) returns None for them, and the
    # dispatch below renders `unknown` rather than guessing a comparison.
    CMOV_OPS = {Mnemonic.CMOVA: '>', Mnemonic.CMOVAE: '>=', Mnemonic.CMOVB: '<',
                Mnemonic.CMOVBE: '<=', Mnemonic.CMOVE: '==', Mnemonic.CMOVNE: '!=',
                Mnemonic.CMOVG: '>', Mnemonic.CMOVGE: '>=', Mnemonic.CMOVL: '<',
                Mnemonic.CMOVLE: '<='}
