"""x86-64 -> pseudo-C# expression lifter (split into mixins by concern)."""

from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.lifter.aggregates import _AggregatesMixin
from il2cpp.lifter.calls import _CallsMixin
from il2cpp.lifter.insn import _InsnMixin
from il2cpp.lifter.render import _RenderMixin
from il2cpp.lifter.state import _StateMixin
from il2cpp.lifter.values import _ValuesMixin



class Lifter(_AggregatesMixin, _StateMixin, _ValuesMixin, _InsnMixin, _CallsMixin, _RenderMixin):
    """Per-method native code lifter; see il2cpp/lifter/ for the parts."""


__all__ = ['Lifter']
