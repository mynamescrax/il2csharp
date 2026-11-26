"""Independent Win64 out producers and private result joins."""
from types import SimpleNamespace as NS

from iced_x86 import Decoder,Register as R
import pytest

from il2cpp.joined_sret import _borrow,_dominated,_edge_defs,_out_owner,_predecessors


@pytest.mark.parametrize('base,first,second',[(0x5800,32,64),(0x7ff12400,48,112)])
@pytest.mark.parametrize('change',['ok','bypass','wrong result register','escaped byref','not out'])
def test_edges_and_registered_out_position(base,first,second,change):
    # The synthetic producer passes its out value in RDX (parameter 2),
    # and no Unity, raycast, fixed frame size or fixture index is supplied.
    def block(j,pc,raw):return NS(bid=j,insns=list(Decoder(64,bytes.fromhex(raw),ip=pc)),term=None,succs=[])
    entry=block(0,base,'488d5570 '+('488bca' if change=='escaped byref' else '4531c0')+' e800010000 84c0 7411')
    pc=entry.insns[-1].next_ip
    split=block(1,pc,'84c9 7406');pc+=4
    left=block(2,pc,'488d4d%02x eb04'%first);pc+=6
    right=block(3,pc,('488d55' if change=='wrong result register' else '488d4d')+'%02x'%second);pc+=4
    use=block(4,pc,'31c0 c3');end=block(5,pc+2,'90 c3');blocks=[entry,split,left,right,use,end]
    # Miss edge targets the RET block, never the use, for the valid graph.
    entry.insns[-1].near_branch64=pc if change=='bypass' else pc+2
    pred=_predecessors(blocks);owner=NS(name='Measurement',index=0,is_valuetype=True,generic_container=-1)
    ty=(0,0x20110000|(0 if change=='not out' else 2));md=NS(is_static=True,return_type=1,param_count=2)
    il=NS(types=[ty,(0,2<<16)],meta=NS(typedefs=[owner],method_params=lambda m:[NS(type=1),NS(type=0)]),
          _closed_type_key=lambda t:(17,0,1) if t==ty else (2,0))
    valid=(_borrow(il,entry,0) and _out_owner(il,md,R.RDX) is owner and _dominated(pred,4,1) and _edge_defs(blocks,pred,use))
    assert bool(valid)==(change=='ok')
