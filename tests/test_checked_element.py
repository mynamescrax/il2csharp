"""Copy of a different-sized first element with independent stack homes."""
from iced_x86 import Decoder
import pytest

from il2cpp.checked_element import _tiles


def test_copy_invalidates_overlapping_address_and_argument_word():
    from types import SimpleNamespace as NS
    from il2cpp.expr import Expr
    from il2cpp.indexed_binary import store_value
    old=Expr('old',None,'ptr');new=Expr('fresh',(7,0x11<<16),'obj')
    l=NS(rsp_delta=-64,slot_var=lambda _: 'dst',_kill_stale=lambda _:None,emit=lambda *a:None,_stack_store=lambda *a:None,
         stack_map={-36:'previous',-32:'dst',-16:'after'},stack_values=dict(previous=old,dst=old,after=old),addr_of=dict(previous='v1',dst='v2',after='v3'))
    store_value(l,123,32,new,12)
    assert l.stack_values==dict(dst=new,after=old) and l.addr_of==dict(after='v3')


@pytest.mark.parametrize('size,change',[(32,'none'),(32,'reverse transfers'),(48,'short'),(24,'past element'),
                                        (32,'gap'),(32,'load next element'),(32,'duplicate source'),
                                        (32,'changed store'),(32,'nonvolatile lane'),(32,'wrong hidden'),(32,'indexed')])
def test_checked_element_is_one_whole_value(size,change):
    # Two unaligned tiles; home and hidden return definitions are scheduled
    # between them. Either order represents one complete value snapshot.
    lo='0f105820';hi='0f106030';store_lo='0f115c2438';store_hi='0f11642448'
    if change=='reverse transfers':lo,hi=hi,lo;store_lo,store_hi=store_hi,store_lo
    if change=='gap':store_hi=store_hi[:-2]+'4c'
    if change=='load next element':hi=hi[:-2]+'40'
    if change=='duplicate source':hi=hi[:-2]+'20'
    if change=='changed store':store_hi='0f115c2448'
    if change=='nonvolatile lane':hi='0f107030';store_hi='0f11742448'
    if change=='indexed':lo='0f105c0820'
    seq=list(Decoder(64,bytes.fromhex(' '.join((lo,'488d4c2460',hi,'488d542438',store_lo,
                       '4533c9' if change=='wrong hidden' else '4533c0',store_hi))),ip=0x52900))
    got=_tiles(seq,size)
    if change in ('none','reverse transfers'):
        home,out,tiles,stores=got
        assert (home,out)==(56,96) and sorted((o,w) for _,_,o,w in tiles)==[(0,16),(16,16)] and len(stores)==2
    else:assert got is None
