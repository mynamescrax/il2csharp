"""Byte-range provenance for stack copies of metadata-proven value types."""
from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.expr import Expr
from il2cpp.text import sdisp, reg_name, _int_lit
from il2cpp.names import repr_f32, repr_f64


_COLOR_NAMES = {
    (1.0, 0.0, 0.0, 1.0): 'UnityEngine.Color.red',
    (0.0, 1.0, 0.0, 1.0): 'UnityEngine.Color.green',
    (0.0, 0.0, 1.0, 1.0): 'UnityEngine.Color.blue',
    (0.0, 1.0, 1.0, 1.0): 'UnityEngine.Color.cyan',
    (1.0, 1.0, 1.0, 1.0): 'UnityEngine.Color.white',
    (0.0, 0.0, 0.0, 1.0): 'UnityEngine.Color.black',
}


def _color_text(raw16, type_name='UnityEngine.Color'):
    if len(raw16) != 16:
        return None
    vals = struct.unpack('<4f', raw16)
    if type_name == 'UnityEngine.Color':
        name = _COLOR_NAMES.get(vals)
        if name is not None:
            return name
    return 'new %s(%s, %s, %s, %s)' % ((type_name,) + tuple(repr_f32(v) for v in vals))


class _AggregatesMixin:
    def _stack_address(self, ins):
        if ins.memory_index != IReg.NONE:
            return None
        base = reg_name(ins.memory_base)
        if base == 'RSP':
            return self.rsp_delta + sdisp(ins.memory_displacement)
        value = dict.get(self.regs, base)
        offset = getattr(value, '_stack_offset', None)
        return None if offset is None else offset + sdisp(ins.memory_displacement)

    def _fragment(self, origin, offset, width):
        # Preserve all bytes of a SIMD copy even when its display text names
        # the first scalar field. Only exact scalar consumers may use that text.
        scalar = self._piece_value(origin, offset, width, None)
        result = Expr(scalar.text if scalar is not None else origin.text,
                      scalar.ty if scalar is not None else origin.ty,
                      scalar.kind if scalar is not None else 'bits')
        result._slice = (origin, offset, width)
        return result

    def _is_rgba_struct(self, td):
        try:
            chain = self.il.instance_field_chain(td)
        except Exception:
            return False
        if not chain or len(chain) != 4:
            return False
        for off, want in ((0x10, 'r'), (0x14, 'g'), (0x18, 'b'), (0x1C, 'a')):
            hit = chain.get(off)
            if hit is None or hit[0] != want:
                return False
            try:
                ft = self.il.types[hit[1]]
            except Exception:
                return False
            if self.il._type_enum(ft) != 0x0c:
                return False
            try:
                w = self.il._sf_field_size(ft, 0)
            except Exception:
                w = None
            if w is not None and w != 4:
                return False
        return True

    def _piece_value(self, origin, offset, width, expected, depth=0):
        if depth > 8:
            return None
        sources = getattr(self, '_aggregate_phi_sources', {}).get(origin.text)
        if expected is not None and sources and all(v is not None for v in sources):
            values = [self._piece_value(v, offset, width, expected, depth + 1)
                      for v in sources]
            if all(v is not None for v in values):
                if offset == 0:
                    self._aggregate_phi_types[origin.text] = expected
                    self._type_hints[origin.text] = expected
                    return Expr(origin.text, expected, self._ty_kind(expected))
                # A scalar phi names lane zero only, but class-init and
                # similar diamonds preserve the other XMM lanes verbatim.
                # Recover an offset lane only when every predecessor proves
                # the same typed value; disagreement remains unknown.
                key = getattr(self.il, '_closed_type_key', lambda t: t)
                if len({(v.text, key(v.ty)) for v in values}) == 1:
                    return values[0]
        sl = getattr(origin, '_slice', None)
        if sl is not None and sl[1] != 0:
            return self._piece_value(sl[0], sl[1] + offset, width, expected, depth + 1)
        data = getattr(origin, '_bytes', None)
        if data is not None:
            if offset + width > len(data) or expected is None:
                return None
            raw = data[offset:offset + width]
            te = self.il._type_enum(expected)
            if te == 0x11:
                td = self._td_of(expected)
                if td is not None and self.meta.typedefs[td].is_valuetype:
                    tn = self.il.type_name(expected)
                    if tn == 'UnityEngine.Color' or self._is_rgba_struct(td):
                        if offset == 0 and width == 16:
                            return Expr(_color_text(raw, tn), expected, self._ty_kind(expected))
                        return None
                    return None
            if te == 0x0c and width == 4:
                text = repr_f32(struct.unpack('<f', raw)[0])
            elif te == 0x0d and width == 8:
                text = repr_f64(struct.unpack('<d', raw)[0])
            else:
                text = self._fimm(str(int.from_bytes(raw, 'little')), expected)
            return Expr(text, expected, self._ty_kind(expected))
        parts = getattr(origin, '_parts', None)
        if parts is not None:
            for tlo, po, poff, pw in parts:
                if tlo <= offset and offset + width <= tlo + pw:
                    return self._piece_value(po, poff + (offset - tlo), width, expected, depth + 1)
            return None
        ty = origin.ty
        if ty is None:
            if offset == 0 and expected is not None and _int_lit(origin.text) is not None:
                return Expr(self._fimm(origin.text, expected), expected, self._ty_kind(expected))
            return None
        size = self.il._sf_field_size(ty, 0)
        if offset == 0 and size == width:
            if expected is None or self.il._closed_type_key(ty) == self.il._closed_type_key(expected):
                return origin
            if _int_lit(origin.text) is not None:
                return Expr(self._fimm(origin.text, expected), expected, self._ty_kind(expected))
        td = self._td_of(ty)
        if td is None or not self.meta.typedefs[td].is_valuetype:
            return None
        chain = self.il.instance_field_chain(td) or {}
        for field_offset, (name, ti) in sorted(chain.items()):
            start = field_offset - 0x10
            ft = self.il.types[ti]
            size = self.il._sf_field_size(ft, 0)
            if size is not None and start <= offset and offset + width <= start + size:
                value = Expr(origin.text + '.' + name, ft, self._ty_kind(ft))
                return self._piece_value(value, offset - start, width, expected, depth + 1)
        return None

    def _scalar_parts(self, origin, offset, width, depth=0):
        """Split a copied value at metadata field boundaries before CFG merging."""
        if depth > 8:
            return [(0, origin, offset, width)]
        if offset == 0 and origin.ty is not None \
                and self.il._sf_field_size(origin.ty, 0) == width \
                and self.il._type_enum(origin.ty) not in (0x11, 0x15):
            return [(0, origin, 0, width)]
        sl = getattr(origin, '_slice', None)
        if sl is not None:
            return self._scalar_parts(sl[0], sl[1] + offset, min(width, sl[2]), depth + 1)
        parts = getattr(origin, '_parts', None)
        if parts is not None:
            result = []
            for lo, po, off, size in parts:
                begin, end = max(offset, lo), min(offset + width, lo + size)
                if begin < end:
                    for sub, val, voff, count in self._scalar_parts(
                            po, off + begin - lo, end - begin, depth + 1):
                        result.append((begin - offset + sub, val, voff, count))
            return result
        td = self._td_of(origin.ty) if origin.ty is not None else None
        if td is None or not self.meta.typedefs[td].is_valuetype:
            return [(0, origin, offset, width)]
        result = []
        chain = getattr(self.il, 'instance_field_chain', lambda _: {})(td) or {}
        for off, (name, ti) in chain.items():
            ft = self.il.types[ti]
            size = self.il._sf_field_size(ft, 0)
            lo = off - 0x10
            if size is None or lo < 0:
                continue
            begin, end = max(offset, lo), min(offset + width, lo + size)
            if begin < end:
                field = Expr(origin.text + '.' + name, ft, self._ty_kind(ft))
                for sub, val, voff, count in self._scalar_parts(
                        field, begin - lo, end - begin, depth + 1):
                    result.append((begin - offset + sub, val, voff, count))
        return result or [(0, origin, offset, width)]

    def _stack_store(self, start, width, value):
        # Memory facts live with register facts, so CFG merges cannot reuse
        # another path's packed bytes. Overlapping stores retain only the
        # unaffected ranges of the previous value.
        for key, old in list(self.regs.items()):
            if not key.startswith('!mem:'):
                continue
            _, lo, n = key.split(':'); lo, n = int(lo), int(n)
            hi = lo + n
            if lo >= start + width or hi <= start:
                continue
            del self.regs[key]
            part = getattr(old, '_slice', None)
            if part is None:
                continue
            origin, offset, _ = part
            if lo < start:
                self.regs[f'!mem:{lo}:{start-lo}'] = self._fragment(origin, offset, start-lo)
            if hi > start + width:
                cut = start + width - lo
                self.regs[f'!mem:{start+width}:{hi-start-width}'] = self._fragment(origin, offset+cut, hi-start-width)
        if value is not None:
            part = getattr(value, '_slice', None)
            if part is None:
                part = (value, 0, width)
            take = part[2] if part[2] < width else width
            if take > 0:
                for delta, origin, offset, count in self._scalar_parts(value, 0, take):
                    self.regs[f'!mem:{start+delta}:{count}'] = self._fragment(origin, offset, count)

    def _stack_piece(self, start, width, expected=None, allow_gaps=False):
        for key, value in self.regs.items():
            if not key.startswith('!mem:'):
                continue
            _, lo, n = key.split(':'); lo, n = int(lo), int(n)
            part = getattr(value, '_slice', None)
            if part is not None and lo <= start and start + width <= lo + n:
                origin, offset, _ = part
                if expected is not None:
                    return self._piece_value(origin, offset + start - lo, width, expected)
                return self._fragment(origin, offset + start - lo, width)
        tiles = []
        for key, value in self.regs.items():
            if not key.startswith('!mem:'):
                continue
            _, lo, n = key.split(':'); lo, n = int(lo), int(n)
            if n <= 0:
                continue
            part = getattr(value, '_slice', None)
            if part is None:
                continue
            tiles.append((lo, part[0], part[1], n))
        tiles.sort(key=lambda t: t[0])
        cur, acc = start, []
        for lo, origin, off, n in tiles:
            if allow_gaps:
                begin, end = max(start, lo), min(start + width, lo + n)
                if begin < end:
                    acc.append((begin - start, origin, off + begin - lo,
                                end - begin))
                continue
            if lo + n <= cur:
                continue
            if lo != cur:
                break
            take = min(n, start + width - cur)
            acc.append((cur - start, origin, off + cur - lo, take))
            cur += take
            if cur >= start + width:
                break
        if not acc or (not allow_gaps and acc[0][0] != 0):
            return None
        result = Expr('', None, 'bits')
        result._parts = acc
        return result

    def _stack_struct(self, address, ty):
        size = self.il._sf_field_size(ty, 0)
        if size is None:
            return None
        whole = self._stack_piece(address, size, ty)
        if whole is not None and whole.text:
            return whole.text
        td = self._td_of(ty)
        if td is None or not self.meta.typedefs[td].is_valuetype:
            return None
        chain = self.il.instance_field_chain(td) or {}
        fields = []
        any_clean = False
        for off, (name, ti) in sorted(chain.items()):
            ft = self.il.types[ti]
            width = self.il._sf_field_size(ft, 0)
            if width is None or off < 0x10 or off - 0x10 + width > size:
                return None
            value = self._stack_piece(address + off - 0x10, width, ft)
            if value is not None and not value.text and getattr(value, '_parts', None):
                value = self._piece_value(value, 0, width, ft)
            if value is None or not value.text:
                # Phi-merge fallback: both arms stored 16B RGBA here but the
                # merged phi text lost provenance. Unanimous 16B across every
                # recorded pred may stand in; any disagreement declines.
                _ct = None
                if size == 16:
                    try:
                        _tn = self.il.type_name(ty)
                    except Exception:
                        _tn = None
                    if _tn and (_tn == 'UnityEngine.Color'
                               or (td is not None and self._is_rgba_struct(td))):
                        _names = set()
                        _frag = self._stack_piece(address, size)
                        if _frag is not None:
                            _sl = getattr(_frag, '_slice', None)
                            if _sl is not None and len(_sl) == 3 \
                                    and getattr(_sl[0], 'text', None):
                                _names.add(_sl[0].text)
                            for _, _po, _, _ in getattr(_frag, '_parts', None) or []:
                                if getattr(_po, 'text', None):
                                    _names.add(_po.text)
                        for _key, _per in (getattr(self, '_phi_bytes', None) or {}).items():
                            if _key[1] not in _names:
                                continue
                            _vals = list(_per.values())
                            if _vals and all(isinstance(_v, (bytes, bytearray)) and len(_v) == 16
                                             for _v in _vals) \
                                    and all(bytes(_v) == bytes(_vals[0]) for _v in _vals[1:]):
                                _ct = _color_text(bytes(_vals[0]), _tn)
                                break
                if _ct is not None:
                    return _ct
                return None
            fields.append(name + ' = ' + value.text)
        return ('new ' + self.il.type_name(ty) + ' { ' + ', '.join(fields) + ' }') if fields else None

    def _copied_struct_arg(self, text, ty):
        if not text.startswith('&') or not self._byval_struct(ty):
            return None
        addresses = [key for key, name in self.stack_map.items() if name == text[1:]]
        r = self._stack_struct(addresses[0], ty) if len(addresses) == 1 else None
        return r

    def _aggregate_load(self, ins):
        width = MemorySizeExt.size(ins.memory_size)
        if width == 8 and getattr(self, '_xor_twin_loads', None) \
                and ins.ip in self._xor_twin_loads:
            # proved packed-xor twin lane: decline the container
            # fragment so the load falls through to the raw deref.
            return None
        address = self._stack_address(ins)
        if address is not None:
            frag = self._stack_piece(address, width, allow_gaps=width >= 16)
            if frag is not None and not frag.text:
                slot = self.slot_var(ins.memory_displacement)
                frag.text = slot
                sty = self.slot_types.get(slot)
                if sty is not None and frag.ty is None:
                    frag.ty = sty
            if frag is not None and frag.text:
                # side-effect-free slot lookup: slot_var CREATES a
                # stack_map entry, so it must not run eagerly here.
                # No entry -> decline, today's spelling.
                slot = getattr(self, 'stack_map', {}).get(
                    ins.memory_displacement + getattr(self, 'rsp_delta', 0))
                if slot is not None and frag.text != slot:
                    # a whole-struct reload of a ctor-constructed home
                    # is the home itself, not a stale scalar or
                    # first-field slice: `mov eax,[rsp+48h]` moves all
                    # 4 bytes of FourCC (34279 `return s_48.m_Code`
                    # changed the return type), and a default-init tile
                    # survives under the ctor writes (18054 `return 0`
                    # dropped the constructed value). Gated on the
                    # _ctor_slots proof plus a proved struct size equal
                    # to the load width; anything else keeps today's
                    # spelling.
                    sty = self.slot_types.get(slot)
                    try:
                        size = self.il._sf_field_size(sty, 0) if isinstance(sty, tuple) else None
                    except Exception:
                        size = None
                    if size == width and size:
                        td = self._td_of(sty)
                        if td is not None and self.meta.typedefs[td].is_valuetype:
                            if slot in getattr(self, '_ctor_slots', set()):
                                return Expr(slot, sty, 'obj')
            return frag
        if ins.memory_base == IReg.RIP or ins.memory_index != IReg.NONE:
            return None
        base = dict.get(self.regs, reg_name(ins.memory_base))
        if base is None:
            return None
        if base.kind in ('sfblob', 'klass', 'usage'):
            return None
        td = self._td_of(base.ty)
        if td is None:
            return None
        offset = sdisp(ins.memory_displacement)
        _te0 = (base.ty[1] >> 16) & 0xFF if isinstance(base.ty, tuple) else None
        if self.meta.typedefs[td].is_valuetype and _te0 in (0x11, 0x15):
            frag = self._fragment(base, offset, width)
            if frag.text != base.text:
                return frag
            # A load that covers EXACTLY the whole value type is the value:
            # returning the fragment stops the fall-through to `_field_expr`,
            # which resolves the first field and renders a narrower access
            # than the instruction (audit F2). An `&x` base is an ADDRESS,
            # not a value; a single field covering the whole load keeps its
            # own precise spelling; and a typedef marked valuetype under a
            # CLASS tuple is a type-confusion, not a value load.
            try:
                size = self.il._sf_field_size(base.ty, 0)
            except Exception:
                size = None
            if size is not None and width == size and offset == 0 \
                    and not str(base.text).startswith('&'):
                fsize = None
                try:
                    td0 = self._td_of(base.ty)
                    chain0 = self.il.instance_field_chain(td0) if td0 is not None else None
                    first = (chain0 or {}).get(0x10)
                    if first is not None:
                        fsize = self.il._sf_field_size(self.il.types[first[1]], 0)
                except Exception:
                    fsize = None
                if fsize != width:
                    return frag
            return None
        chain = self.il.instance_field_chain(td) or {}
        if offset in chain:
            return None
        for off, (name, ti) in chain.items():
            ft = self.il.types[ti]
            ftd = self._td_of(ft)
            if ftd is None or not self.meta.typedefs[ftd].is_valuetype:
                continue
            size = self.il._sf_field_size(ft, 0)
            if size is not None and off <= offset and offset + width <= off + size:
                container = Expr(base.text + '.' + name, ft, 'obj')
                frag = self._fragment(container, offset - off, width)
                if frag.text != container.text or frag.ty is not None:
                    return frag
        return None
