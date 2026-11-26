from types import SimpleNamespace as NS
import re

import pytest

from il2cpp.allocation_sink import allocation_sinks


@pytest.mark.parametrize('case',['ok','other allocation','value field','extra use','invocation result','not adjacent','no ctor proof'])
def test_fresh_type_requires_the_whole_rhs_and_only_an_object_store(case):
    obj=(1,0x1c<<16); wait=(2,0x12<<16)
    meta=NS(typedefs=[NS()],type_fields=lambda _:[0],fields=[NS(name='current',type=0)])
    il=NS(meta=meta,types=[obj if case!='value field' else wait],_source_field_names={0:'current'},
          _closed_type_key=lambda t:(0x1c,0) if t==obj else (0x12,2,0),type_name=lambda t:'Tests.Wait')
    lift=NS(il=il,_bound_constructor_types={} if case=='no ctor proof' else {'t2':wait})
    init={'other allocation':'new Tests.Other()', 'invocation result':'new Tests.Wait().Other()'}.get(case,'new Tests.Wait(Delay())')
    lines=['var t2 = '+init+';','this.current = t2;']
    if case=='extra use': lines.append('SelectOverload(t2);')
    if case=='not adjacent': lines.insert(1,'if (choose)')
    tokens=re.findall(r'\bt\d+\b','\n'.join(lines))
    assert allocation_sinks(lift,NS(declaring=0,is_static=False),lines,tokens)==({'t2':'Tests.Wait'} if case=='ok' else {})
