from il2cpp.prelude import *  # noqa: F401,F403

class _EhMixin:
    def load_function_bounds(self):
        self.func_starts = set()
        self.func_next = {}
        b = self.bin
        pd = next((s for s in b.sections if s.name == '.pdata'), None)
        if pd:
            o, n = pd.offset, pd.size // 12
            ranges = []
            for i in range(n):
                s_rva, e_rva, _ = struct.unpack_from('<IIH', b.d, o + i * 12)
                if s_rva and e_rva > s_rva:
                    ranges.append((b.image_base + s_rva, b.image_base + e_rva))
            ranges.sort()
            self.func_ranges = ranges
            import bisect
            starts = [r[0] for r in ranges]
            self._starts = starts
            self._bisect = bisect
        else:
            self.func_ranges = []
            self._starts = []

    def function_extent(self, va) -> Tuple[int, int]:
        """best-effort (start,end) of the function containing va."""
        if not self._starts:
            return va, va + 0x1000
        bi = self._bisect.bisect_right(self._starts, va) - 1
        if bi >= 0:
            s, e = self.func_ranges[bi]
            if s <= va < e:
                return s, e
        return va, va + 0x1000

    def next_function_start(self, va) -> Optional[int]:
        if not self._starts:
            return None
        bi = self._bisect.bisect_right(self._starts, va)
        return self._starts[bi] if bi < len(self._starts) else None

    # ---------------- Windows x64 __CxxFrameHandler4 region recovery -----
    # The compressed FuncInfo4 blob uses a "back-shift" primitive everywhere:
    # a nibble at the cursor says how far back the value's bits live, and the
    # value is the preceding u32 right-shifted. The two 16-entry tables
    # (back-distance / shift) sit adjacent in .rdata and are located by
    # signature so other CRT builds can shift them.
    EH_TBL1 = (-1, -2, -1, -3, -1, -2, -1, -4, -1, -2, -1, -3, -1, -2, -1, -5)
    EH_TBL2 = (25, 18, 25, 11, 25, 18, 25, 4, 25, 18, 25, 11, 25, 18, 25, 0)

    def _eh4_init(self):
        if getattr(self, '_eh4_state', None) is not None:
            return self._eh4_state
        self._eh4_state = False
        b = self.bin
        pd = next((s for s in b.sections if s.name == '.pdata'), None)
        if pd is None:
            return False
        sig = bytes(self.EH_TBL2)
        best = None
        for sec in b.sections:
            if sec.is_bss or sec.rawsize < 64:
                continue
            data = b.read(sec.addr, sec.rawsize)
            i = data.find(sig)
            if i >= 0:
                j = data.find(sig, i + 1)
                best = (sec, i, j)
                if j >= 0:
                    break
        if best is None:
            return False
        sec, i, j = best
        if j >= 0:
            for k in (i, j):
                if b.read(sec.addr + k - 16, 16) == bytes(x & 0xFF for x in self.EH_TBL1):
                    i = k
                    break
        elif b.read(sec.addr + i - 16, 16) != bytes(x & 0xFF for x in self.EH_TBL1):
            return False
        self._eh4_t2 = sec.addr + i
        raw = b.read(pd.addr, pd.size)
        entries = []
        from collections import Counter
        hcnt = Counter()
        for k in range(pd.size // 12):
            bg, en, un = struct.unpack_from('<III', raw, k * 12)
            entries.append((bg, en, un))
        self._eh4_entries = entries
        self._eh4_begins = [e[0] for e in entries]
        for bg, en, un in entries:
            uo = b.va2off(b.image_base + un)
            if uo is None:
                continue
            flags = (b.d[uo] >> 3) & 7
            if flags & 3:
                cnt = b.d[uo + 2]
                hoff = uo + 4 + ((2 * cnt + 3) // 4) * 4
                hva = struct.unpack_from('<I', b.d, hoff)[0]
                hcnt[hva] += 1
        self._eh4_handler = hcnt.most_common(1)[0][0] if hcnt else None
        self._eh4_cache = {}
        self._eh4_state = True
        return True

    def _eh4_nib(self, rva):
        """Back-shift decode at rva -> (value, cursor_after)."""
        b = self.bin
        o = b.va2off(b.image_base + rva)
        n = b.d[o] & 0xF
        back = -self.EH_TBL1[n]
        v = struct.unpack_from('<I', b.d, b.va2off(b.image_base + rva + back - 4))[0] \
            >> self.EH_TBL2[n]
        return v, rva + back

    def eh_regions(self, va):
        """Try/catch structure for the function containing va (PE x64,
        __CxxFrameHandler4 compressed tables). None when absent:
        {'pads': [catch-funclet VAs], 'ntry': n, 'nhandlers': n}."""
        if not self._eh4_init() or self._eh4_handler is None:
            return None
        b = self.bin
        ib = b.image_base
        rva = va - ib
        cached = self._eh4_cache.get(rva, 0)
        if cached != 0:
            return cached
        try:
            out = self._eh4_parse(rva)
        except Exception:
            out = None
        self._eh4_cache[rva] = out
        return out

    def _eh4_parse(self, rva):
        b = self.bin
        ib = b.image_base
        bi = self._bisect.bisect_right(self._eh4_begins, rva) - 1
        if bi < 0:
            return None
        bg, en, un = self._eh4_entries[bi]
        if not (bg <= rva < en):
            return None
        uo = b.va2off(ib + un)
        flags = (b.d[uo] >> 3) & 7
        if not flags & 3:
            return None
        cnt = b.d[uo + 2]
        hoff = uo + 4 + ((2 * cnt + 3) // 4) * 4
        hva = struct.unpack_from('<I', b.d, hoff)[0]
        if hva != self._eh4_handler:
            return None
        fi = struct.unpack_from('<I', b.d, hoff + 4)[0]
        fo = b.va2off(ib + fi)
        hdr = b.d[fo]
        # FuncInfoHeader bits (ehdata4_export.h, read straight from the local
        # MSVC install -- VC/Tools/MSVC/*/include/ehdata4_export.h): 0x1
        # isCatch, 0x2 isSeparated, 0x4 BBT, 0x8 UnwindMap, 0x10 TryBlockMap,
        # 0x20 EHs, 0x40 NoExcept. Fields present, in order: bbtFlags (nibble,
        # BBT), dispUnwindMap (u32, UnwindMap), dispTryBlockMap (u32,
        # TryBlockMap), dispIPtoStateMap (u32, UNCONDITIONAL -- no header bit
        # gates it -- unless isSeparated, the PGO/BBT segment-table case,
        # which this build never sets and we don't decode), dispFrame
        # (nibble, isCatch). The old code folded UnwindMap and TryBlockMap
        # into one "trymap" slot by re-reading the same variable, which
        # happened to land correctly whenever TryBlockMap was set but
        # returned a function with UnwindMap-but-no-TryBlockMap as if it had
        # a try (reading dispUnwindMap's RVA as a try-block-map) -- 0
        # occurrences on this binary (validated: work/eh4_ipstate_probe.py),
        # but the explicit header check below closes that case for good.
        c2 = fi + 1
        if hdr & 4:
            _, c2 = self._eh4_nib(c2)          # bbtFlags
        if hdr & 8:
            c2 += 4                            # dispUnwindMap (unused)
        if not (hdr & 0x10):
            return None                        # no TryBlockMap -> no try here
        trymap = struct.unpack_from('<I', b.d, b.va2off(ib + c2))[0]
        c2 += 4
        if not trymap:
            return None
        ipmap = None
        if not (hdr & 2):                      # non-separated: field follows directly
            ipdisp = struct.unpack_from('<I', b.d, b.va2off(ib + c2))[0]
            if ipdisp:
                ipmap = ipdisp
        tc = trymap
        ntry, tc = self._eh4_nib(tc)
        pads = []
        nhandlers = 0
        trys = []
        try_pads = []                          # pads[i] belongs to trys[i]
        for _ in range(min(ntry, 32)):
            tlow, tc = self._eh4_nib(tc)       # tryLow  (EH state)
            thigh, tc = self._eh4_nib(tc)      # tryHigh (EH state)
            chigh, tc = self._eh4_nib(tc)      # catchHigh
            trys.append((tlow, thigh, chigh))
            tpads = []
            try_pads.append(tpads)
            harr = struct.unpack_from('<I', b.d, b.va2off(ib + tc))[0]
            tc += 4
            if not harr:
                continue
            hc = harr
            nh, hc = self._eh4_nib(hc)
            prev = bg                          # handler RVAs delta-chain from begin
            for _ in range(min(nh, 32)):
                fl = b.d[b.va2off(ib + hc)]
                hc += 1
                if fl & 1:
                    _, hc = self._eh4_nib(hc)
                if fl & 2:
                    hc += 4
                if fl & 4:
                    _, hc = self._eh4_nib(hc)
                hc += 4                        # always-present u32
                if (fl & 0x30) == 0x10:
                    v, hc = self._eh4_nib(hc)
                    prev = prev + v
                    if bg <= prev < en:
                        pads.append(ib + prev)
                        tpads.append(ib + prev)
                        nhandlers += 1
                elif (fl & 0x30) == 0x20:
                    _, hc = self._eh4_nib(hc)
                    v2, hc = self._eh4_nib(hc)
                    prev = prev + v2
        if not pads:
            return None
        states = self._eh4_ipstates(ib, bg, ipmap) if ipmap else None
        try_ranges = self._eh4_try_ranges(states, trys) if states else None
        regions = self._eh4_regions(trys, try_pads, try_ranges) if try_ranges else None
        return {'pads': pads, 'ntry': ntry, 'nhandlers': nhandlers,
                'trys': trys, 'states': states, 'try_ranges': try_ranges,
                'regions': regions, 'try_pads': try_pads}

    @staticmethod
    def _eh4_regions(trys, try_pads, try_ranges):
        """One dict per TryBlockMapEntry4, nesting-ordered outermost-first
        (a wider [tryLow,tryHigh] state range is never nested inside a
        narrower one, so sorting by range width descending is exactly
        outer-to-inner).

        Exact-region wiring needs a try resolved to a contiguous protected
        range. A single contiguous span is ideal; a multi-span try (the
        state re-enters its own range at disjoint IPs -- see try_ranges
        docstring) is bridged [first-span.start, last-span.end) ONLY when
        no SIBLING try's span overlaps the bridged range -- bridging an
        interleaved pair is unsound (one open/close pair wide enough to
        swallow the sibling's entire span, rendering it twice; that was
        tried and reverted in batch 11). The gap itself (the spans' own
        unprotected stretch -- e.g. the compiler leaving a call out of the
        protected range) over-renders inside the try braces, which is
        valid C# and honest enough; a try that can't be bridged safely is
        dropped here and `_seh_prepare` falls back to the structural scan
        for it.

        `start`/`end` are the bridged range (used verbatim in the common
        case); `end1` is the FIRST span's exclusive end, which a `finally`
        region uses instead: the extra spans of a finally-shaped try are
        the funclet-dedup tail (the compiled finally re-protects its own
        exit path, which usually sits far from the try inside foreign
        code), and pulling the close across to the last span lands the
        `} finally` after unrelated statements -- the try-follower scan's
        multi-span finally sites."""
        out = []
        n = len(trys)
        for i in range(n):
            (tlow, thigh, chigh), pads = trys[i], try_pads[i]
            if not pads:
                continue
            spans = try_ranges[i][3]
            if not spans:
                continue
            start, end1 = spans[0]
            end = end1
            if len(spans) > 1:
                start, end = spans[0][0], spans[-1][1]
                interleaved = False
                for j in range(n):
                    if j == i:
                        continue
                    for s2, e2 in try_ranges[j][3]:
                        if s2 < end and e2 > start:
                            interleaved = True
                            break
                    if interleaved:
                        break
                if interleaved:
                    continue
            out.append({'tlow': tlow, 'thigh': thigh, 'chigh': chigh,
                         'pads': pads, 'start': start, 'end': end,
                         'end1': end1, 'spans': spans})
        out.sort(key=lambda r: (r['thigh'] - r['tlow']), reverse=True)
        return out

    def _eh4_ipstates(self, ib, bg, ipmap_rva):
        """Decode IPtoStateMap4 at dispIPtoStateMap (image-relative) into a
        sorted list of (va, state) transition points, VA to match `pads`
        (block lookups key on absolute VA) -- ehdata4_export.h: NumEntries
        (nibble), then NumEntries * (Ip delta (nibble, cumulative and
        function-relative), State (nibble, encoded as State+1))."""
        c = ipmap_rva
        n, c = self._eh4_nib(c)
        out = []
        prev = 0
        for _ in range(min(n, 20000)):
            d, c = self._eh4_nib(c)
            prev += d
            st1, c = self._eh4_nib(c)
            out.append((ib + bg + prev, st1 - 1))
        return out

    @staticmethod
    def _eh4_try_ranges(states, trys):
        """[(tryLow, tryHigh, catchHigh, [(start_va, end_va), ...]), ...]
        -- the exact instruction ranges where the current EH state falls in
        [tryLow, tryHigh], derived from the IP-to-state transition points.
        Usually one contiguous range per try; more than one only if the
        compiler re-enters the try's state range at a later IP. A span still
        open at the last transition point closes there (untaken in
        practice: every sampled function's last transition is state -1)."""
        out = []
        for tlow, thigh, chigh in trys:
            spans = []
            span_start = None
            for ip, st in states:
                active = tlow <= st <= thigh
                if active and span_start is None:
                    span_start = ip
                elif not active and span_start is not None:
                    spans.append((span_start, ip))
                    span_start = None
            if span_start is not None:
                spans.append((span_start, states[-1][0]))
            out.append((tlow, thigh, chigh, spans))
        return out


