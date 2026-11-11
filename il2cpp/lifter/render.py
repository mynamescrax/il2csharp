from il2cpp.prelude import *  # noqa: F401,F403

class _RenderMixin:
    def _render(self) -> List[str]:
        lines = []
        last_ip = None
        for ip, code, asm in self.out:
            if ip in self.targets and ip != last_ip:
                lines.append('')
                lines.append('L_%x:' % ip)
            last_ip = ip
            if not code and not asm:
                continue
            if asm and not code:
                lines.append('        // %s' % asm)
            elif code and asm and self.asm_comments:
                lines.append('        %-70s // %s' % (code, asm))
            elif code:
                lines.append('        ' + code)
        return lines

