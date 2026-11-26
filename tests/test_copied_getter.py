import pytest
from iced_x86 import Decoder

from il2cpp.copied_getter import _copied_home


# A 40-byte value copied between independent stack slots. The final 8
# bytes move through XMM0 after its first 16 bytes have already been saved.
COPY = ('0f10442470 4531c0 488d542440 0f108c2480000000 488d4c2430 '
        '0f11442440 f20f10842490000000 f20f11442460 0f114c2450')


def copied(code):
    return _copied_home(list(Decoder(64,bytes.fromhex(code),ip=0x1000)),0x70,40)


def test_whole_receiver_preserves_all_three_chunks():
    assert copied(COPY) == (0x40,0x30)


@pytest.mark.parametrize('change',[None,'wrong frame','wrong last load','wrong last store','wrong borrow'])
def test_mixed_base_copy_needs_one_physical_coordinate_system(change):
    # BP = SP+0x100. BP-0x80 and SP+0x80 are the *same* last eight
    # bytes, immediately preceding the indexer return at SP+0x88.
    raw='0f104588 4531c0 488d542460 0f104d98 488d4de0 0f11442460 f20f1045a8 f20f114580 0f114c2470'
    if change=='wrong last load': raw=raw.replace('1045a8','1045a4')
    if change=='wrong last store': raw=raw.replace('114580','114584')
    if change=='wrong borrow': raw=raw.replace('488d542460','488d542468')
    result=_copied_home(list(Decoder(64,bytes.fromhex(raw))),0x88,40,0x108 if change=='wrong frame' else 0x100)
    assert result==((0x60,0xe0) if change is None else None)


@pytest.mark.parametrize('old,new', [
    ('80000000','78000000'),       # overlaps first input lane
    ('f20f11442460','0f11442460'), # writes 16 instead of eight
    ('0f114c2450','0f11442450'),   # stale source after the reload
    ('488d542440','488d542448'),   # this does not point to the copy
    ('488d4c2430','488d4c2440'),   # result overwrites receiver
    ('4531c0','4531c9'),           # not the instance MethodInfo slot
    ('4531c0','4531c0 e800200000'), # no outstanding call may observe/mutate a partial copy
])
def test_disputed_struct_copy_has_no_typed_receiver(old,new):
    assert copied(COPY.replace(old,new)) is None
