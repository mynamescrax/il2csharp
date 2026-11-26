"""A synthetic Win64 routine with two pushes, a caller home and two late saves."""
from types import SimpleNamespace as NS

from iced_x86 import Decoder
import pytest

from il2cpp.binary import PE, Section
from il2cpp.stack_local_frame import stack_local_frame


# R13 uses incoming home 4, then R12 and RBP are pushed. A diamond inside
# SizeOfProlog joins before RBX and XMM9 are parked in separate local slots.
PREFIX = '4c896c2420 4154 55 4883ec58 7502 31c0 48895c2428 440f294c2440'
EPILOGUE = '440f284c2440 4c8bac2488000000 488b5c2428 4883c458 5d 415c c3'
UNWIND = '011b0900 1b980400 15340500 0cd41100 0ca2 0850 07c0'


def prove(prefix=PREFIX, body='e800100000', epilogue=EPILOGUE, unwind=UNWIND,
          pads=(), end_delta=0, start_delta=0, is64=True, base=0x140001000):
    code = bytes.fromhex(' '.join((prefix, body, epilogue)))
    seq = list(Decoder(64, code, ip=base))
    # Read the registered unwind record through the real VA-to-file mapping.
    pe = PE.__new__(PE)
    pe.d = bytes.fromhex(unwind)
    pe.image_base = base - 0x1000
    pe.is64 = is64
    pe.sections = [Section('.xdata', base+0x1000, len(pe.d), 0, len(pe.d), 0x40000040)]
    entry = (0x1000+start_delta, 0x1000+len(code)+end_delta, 0x2000)
    il = NS(bin=pe, _eh4_begins=[entry[0]], _eh4_entries=[entry])
    # Native branch destinations matter even when a lifter suppressed edges.
    blocks = [NS(insns=seq[:5], preds=[]), NS(insns=seq[5:], preds=[0])]
    return stack_local_frame(NS(il=il), NS(addr=base), blocks, pads)


@pytest.mark.parametrize('base', [0x140001000, 0x45670000])
@pytest.mark.parametrize('exit_code', ['c3', 'e900100000'])
def test_spans_include_full_simd_slot_pushes_and_incoming_home(base, exit_code):
    assert prove(epilogue=EPILOGUE[:-2]+exit_code, base=base) == (
        0x58, 0x68, ((0x28, 8), (0x40, 16), (0x58, 8), (0x60, 8), (0x88, 8)))


@pytest.mark.parametrize('old,new', [
    ('011b0900', '211b0900'),  # chained unwind, no local handler pad
    ('011b0900', '091b0900'),  # handler flag
    ('011b0900', '011b0905'),  # established frame register
    ('011b0900', '011c0900'),  # prologue end is not last save end
    ('1b980400', '1a980400'),  # points inside an instruction
    ('1b980400', '1b880400'),  # wrong XMM register
    ('15340500', '15340600'),  # wrong late GPR offset
    ('0cd41100', '0cd40400'),  # entry displacement used as final displacement
    ('0cd41100', '05d41100'),  # home row not tied to the allocation
    ('0ca2', '0cb2'), ('07c0', '07d0'), ('07c0', ''),
])
def test_unwind_must_describe_each_transfer(old, new):
    assert prove(unwind=UNWIND.replace(old, new)) is None


@pytest.mark.parametrize('extra', [dict(pads=(1,)), dict(start_delta=-1), dict(end_delta=1), dict(is64=False)])
def test_only_plain_complete_registered_frame(extra):
    assert prove(**extra) is None


@pytest.mark.parametrize('old,new', [
    ('4883c458', '4883c450'), ('5d 415c', '415c 5d'), ('c3', 'c21000'),
    ('440f284c2440', '440f284c2430'),  # same XMM, wrong sixteen bytes
    ('488b5c2428', '8b5c2428'),        # partial EBX restore
    ('4c8bac2488000000', '90'),        # missing early home restore
])
def test_every_saved_register_and_rsp_are_restored(old, new):
    assert prove(epilogue=EPILOGUE.replace(old, new)) is None


@pytest.mark.parametrize('body', [
    '4883ec10 4883c410', '9c 9d', '50 58', '83c401', '4887c4',  # unregistered RSP change
    'c3', 'e900100000', 'ffe0',   # alternate exits without restoration
    '7506', '7401',               # branch skips first reload or enters its encoding
    '7400 c3',                     # one bad exit even when the trailing one is good
    '4c89642427',                  # qword starts before RBX save and overlaps it
    '8944244f',                    # straddles the far end of the XMM save
    'b840000000 480fbb442420',     # bit 64 at RSP+32 modifies the RBX save at +40
    '4088742468',                  # overwrite return address
    '89440420', '4889e0', '488d6c2420',  # indexed access / copy of RSP / biased second base
    '4531f6',                      # never saved R14 (partial register write)
])
def test_unaccounted_frame_change_or_access_declines(body):
    assert prove(body=body) is None


def test_delayed_saves_must_be_reached_with_the_original_values():
    assert prove(prefix=PREFIX.replace('7502', '7507')) is None  # branch over RBX save
    assert prove(prefix=PREFIX.replace('31c0', '31db')) is None  # EBX already redefined
    assert prove(prefix=PREFIX.replace('31c0', 'ebfe')) is not None  # harmless pre-save loop


def test_consistent_unwind_offsets_still_cannot_reserve_aliasing_storage():
    # Both native transfers AND the unwind row agree. But RBX's eight bytes
    # are now inside the XMM save, so its apparent reload is not a restore.
    assert prove(prefix=PREFIX.replace('5c2428', '5c2448'),
                 epilogue=EPILOGUE.replace('5c2428', '5c2448'),
                 unwind=UNWIND.replace('15340500', '15340900')) is None


def test_multiple_complete_exits_and_explicit_trap():
    n = len(bytes.fromhex(EPILOGUE))
    assert prove(body=f'75{n:02x}', epilogue=EPILOGUE+' '+EPILOGUE)
    assert prove(body=f'75{n:02x}', epilogue=EPILOGUE+' 0f0b')
    assert prove(body=f'75{n:02x}', epilogue=EPILOGUE+' 90') is None  # runs off extent
