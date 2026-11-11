"""Structured decompiler (split into mixins by pass group)."""

from il2cpp.prelude import *  # noqa: F401,F403
from il2cpp.dec.analyze import _AnalyzeMixin
from il2cpp.dec.build import _BuildMixin
from il2cpp.dec.dataflow import _DataflowMixin
from il2cpp.dec.emit import _EmitMixin
from il2cpp.dec.flow import _FlowMixin
from il2cpp.dec.highlevel import _HighLevelMixin
from il2cpp.dec.seh import _SehMixin
from il2cpp.dec.structure import _StructureMixin
from il2cpp.dec.sugar import _SugarMixin
from il2cpp.dec.textpass import _TextPassMixin



class Decompiler(_BuildMixin, _AnalyzeMixin, _StructureMixin, _SugarMixin,
                 _SehMixin, _FlowMixin, _DataflowMixin, _HighLevelMixin,
                 _TextPassMixin, _EmitMixin):
    """CFG -> symbolic exec -> structured control flow -> C# text.

    Pass order is load-bearing and lives in _structure()/_final_text();
    moving methods between mixin files does not change it.
    """


__all__ = ['Decompiler']
