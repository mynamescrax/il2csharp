"""Independent Win64 kickoff: no game input, real decoded instructions and MethodSpec lookup."""
from types import SimpleNamespace as NS
from struct import pack

import pytest
from iced_x86 import Decoder

from il2cpp.async_start import async_task_start
from il2cpp.binary import PE


def independent_kickoff(base,spec_index,home,change=None):
    # Different frame, names, field order, builder width, capture and XMM
    # register from the game. All slot and call relocations use this image.
    flag,klass,spec,init,cinit,create,barrier,start,get=(base+0x1000+i*0x100 for i in range(9))
    code=bytearray();fixups=[];labels={}
    def put(h): code.extend(bytes.fromhex(h))
    def rel(h,t,suffix=b''):
        put(h);pos=len(code);code.extend(bytes(4)+suffix);fixups.append((pos,t,base+len(code)))
    def label(n):labels[n]=base+len(code)
    put('56 4881ec80000000');rel('803d',flag,b'\0');put('8bf2');rel('0f85','ready') # keep count in ESI
    for p in (klass,spec):rel('488d0d',p);rel('e8',init)
    rel('c605',flag,b'\1');label('ready');rel('488b0d',klass);put('0f57db') # XMM3 = 0
    for off in (home+16,home):put('0f115c24');code.append(off)
    put('83b9e400000000');rel('0f85','make');rel('e8',cinit);label('make')
    put('33d2 488d4c2420');rel('e8',create)
    put('0f1018');put('0f115c24');code.append(home) # one whole 16-byte builder from RAX
    put('488d4c24');code.append(home);put('31d2');rel('e8',barrier)
    rel('4c8b05',spec);put('488d5424');code.append(home);put('488d4c24');code.append(home)
    put('897424');code.append(home+20);put('c74424');code.append(home+16);put('ffffffff');rel('e8',start)
    put('33d2 488d4c24');code.append(0x20 if change=='detached' else home);rel('e8',get);put('4881c480000000 5e c3')
    for pos,t,end in fixups: code[pos:pos+4]=pack('<i',(labels[t] if isinstance(t,str) else t)-end)
    seq=list(Decoder(64,bytes(code),ip=base))

    # Types: void, Task, builder, state, byref MVAR, int. Public fields use
    # their actual metadata names rather than C# compiler naming conventions.
    types=[(0,1<<16),(3,0x12<<16),(2,0x11<<16|6),(1,0x11<<16),(0,0x1e<<16|1<<29),(0,8<<16|6),(4,0x12<<16)]
    def td(i,value):return NS(index=i,is_valuetype=value,generic_container=-1,flags=0,field_count=3,interfaces_start=0,interfaces_count=1)
    defs=[td(i,i in (1,2)) for i in range(5)]; names=['Depot','Depot.Parcel','System.Runtime.CompilerServices.AsyncTaskMethodBuilder','System.Threading.Tasks.Task','System.Runtime.CompilerServices.IAsyncStateMachine']
    def md(j,n,own,static,ret,params,addr):return NS(index=j,name=n,declaring=own,is_static=static,return_type=ret,params=params,param_count=len(params),flags=6,generic_container=-1,addr=addr)
    methods=[md(0,'Begin',0,False,1,[NS(name='count',type=5)],base),md(1,'Create',2,True,2,[],create),
             md(2,'get_Task',2,False,1,[],get),md(3,'Start',2,False,0,[NS(name='s',type=4)],0)]
    methods[3].generic_container=0
    fields=[NS(name=n,type=t) for n,t in [('pump',2),('phase',5),('quota',5)]]
    meta=NS(typedefs=defs,methods=methods,fields=fields,interfaces=[6],generic_containers=[(3,1,1,0)],
            method_params=lambda m:m.params,type_methods=lambda t:[1,2,3] if t.index==2 else [],type_fields=lambda t:range(3))
    image=PE.__new__(PE);image.is64=True;image.is_exec_va=lambda a:a in (create,start,get);image.exports={cinit:'il2cpp_runtime_class_init'}
    # Alternate zeroing register and different-sized builder. An extra write
    # outside the result must defeat the fold even with a matching signature.
    leaf='0f57d2 0f1111 '+('895110 ' if change=='extra write' else '')+'488bc1 c3'
    image.read=lambda a,n:bytes.fromhex(leaf)[:n] if a==create else None;image.qword=lambda a:start if a==base+0x5000 else None
    enum=lambda t:t[1]>>16&0xff if t else None
    key=lambda t:None if not t else (enum(t),t[0],0) if enum(t) in (0x11,0x12) else (enum(t),0)
    il=NS(bin=image,meta=meta,types=types,_type_enum=enum,_closed_type_key=key,td_of_ty=lambda t:t[0],
          typedef_full=lambda i:names[i],type_name=lambda t:names[t[0]],_nested_owner=lambda n:0 if n==1 else None,
          field_offsets=[[],[16,32,36]],value_type_size=lambda n:32 if n==1 else 16,_sf_field_size=lambda t,_:16 if t==types[2] else 4,
          instance_field_chain=lambda _: {k:(f.name,f.type) for k,f in zip((16,32,36),fields)},returns_sret=lambda t:t==types[2],
          method_specs=[(-1,-1,-1)]*spec_index+[(3,-1,0)],_method_spec_type_args=lambda n:(types[3],) if n==0 else None,
          generic_method_table_list=[(spec_index,0,0,0)],generic_method_pointers_count=1,generic_method_pointers=base+0x5000,
          addr_candidates={create:[('method',1),('generic',0)],get:[('method',2)]},function_extent=lambda a:(base,base+len(code)),
          decode_slot=lambda a:{spec:{'kind':6,'idx':spec_index},klass:{'kind':1,'td':2,'type':types[2]}}.get(a))
    lift=NS(il=il,rt_init_meta=init,rt_wbarrier={barrier},_accessor_prop=lambda _:('get','Task',0))
    return async_task_start(lift,methods[0],defs[0],seq,None)


@pytest.mark.parametrize('base,index,home',[(0x8000,5,0x30),(0x160000,21,0x48)])
def test_plain_task_kickoff_uses_supplied_metadata_and_layout(base,index,home):
    lines=independent_kickoff(base,index,home)
    assert lines and lines[0]=='Depot.Parcel stateMachine = default;'
    assert 'stateMachine.quota = count;' in lines and 'stateMachine.phase = -1;' in lines
    assert lines[-2:]==['stateMachine.pump.Start<Depot.Parcel>(ref stateMachine);','return stateMachine.pump.Task;']


@pytest.mark.parametrize('change',['detached','extra write'])
def test_synthetic_unproved_task_kickoff_declines(change):
    assert independent_kickoff(0x12000,9,0x40,change) is None
