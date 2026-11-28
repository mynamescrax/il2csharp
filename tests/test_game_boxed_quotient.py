import pytest
from dotnet_case import run_case
from il2cpp.emitter import Emitter
from test_game_shift_shared_flags import shift_runtime

pytestmark = pytest.mark.game


def test_three_emitted_time_formatters_preserve_signed_quotient_and_remainder(shift_runtime, tmp_path):
    meta, il = shift_runtime
    em = Emitter(il,str(tmp_path/'out')); shells=[]; invocations=[]
    for mi in (27003,27188,27817):
        m=meta.methods[mi];td=meta.typedefs[m.declaring];lines=[];em.emit_method(m,td,lines,'    ')
        shells.append('class '+td.name+' {public static string Run(int x)=>FormatTime(x);\n'+'\n'.join(lines)+'\n}')
        invocations.append(td.name+'.Run')
    src='''using System;using System.Globalization;
foreach(string culture in new[]{"en-US","fr-FR"}){
    CultureInfo.CurrentCulture=CultureInfo.GetCultureInfo(culture);
    var formatters=new Func<int,string>[]{'''+','.join(invocations)+'''};
    foreach(var f in formatters){
        void Check(int n){
            string expected=string.Format("{0:D2}:{1:D2}",n/60,n%60), actual=f(n);
            if(actual!=expected)throw new Exception($"{n}: '{actual}' != '{expected}'");
        }
        foreach(int n in new[]{int.MinValue,int.MinValue+1,int.MaxValue-1,int.MaxValue,-121,-120,-119,-61,-60,-59,-1,0,1,59,60,61,119,120,121})Check(n);
        for(int q=-1024;q<=1024;q++)for(int r=-1;r<=1;r++)Check(q*60+r);
        var rng=new Random(1403);for(int i=0;i<2000;i++)Check((int)rng.NextInt64(int.MinValue,(long)int.MaxValue+1));
    }
}
Console.WriteLine("three complete signed formatters: boundaries, extrema, signed random and both cultures");
'''+ '\n'.join(shells)
    runner=tmp_path/'r';runner.mkdir();(runner/'Program.cs').write_text(src,encoding='utf8');print(run_case(tmp_path,runner))


@pytest.fixture(scope='module')
def plan(shift_runtime):
    from il2cpp import Decompiler,Lifter
    from il2cpp.boxed_quotient import boxed_divisions
    meta,il=shift_runtime;m=meta.methods[27003];d=Decompiler(Lifter(il));d.lift_method(m,meta.typedefs[m.declaring]);bs=d.L._blocks
    return bs, lambda: boxed_divisions(d.L,m,bs,())


@pytest.mark.parametrize('change',['none','unsigned correction','wrong multiplier','wrong source',
                                    'wrong box class','unregistered lookup','wrong export','different home','saved home','partial save overlap',
                                    'observe corrected flags','observe full remainder'])
def test_boxed_division_needs_the_arithmetic_home_and_consumers(plan, shift_runtime, monkeypatch, change):
    from iced_x86 import Decoder, Register as R
    bs,scan=plan;meta,il=shift_runtime;first,second=0x1805967b8,0x1805967e3
    assert set(scan())=={first,second}
    if change=='none':return
    if change=='unregistered lookup':
        monkeypatch.delitem(il.__dict__,'_boxed_int_lookup_cells',raising=False)
        va,=(va for va,n in il.bin.exports.items() if n=='il2cpp_class_from_name')
        monkeypatch.delitem(il.bin.exports,va)
        assert not scan();return
    if change=='wrong box class':
        original=il.decode_slot
        monkeypatch.setattr(il,'decode_slot',lambda a:dict(kind=2,td=0,text='typeof(int)') if a==0x183e9f1d8 else original(a))
        assert not scan();return
    def edit(ip,fn):
        b,j=next((b,j) for b in bs for j,i in enumerate(b.insns) if i.ip==ip);i=fn(b.insns[j].copy())
        assert i.len==b.insns[j].len
        monkeypatch.setattr(b,'insns',b.insns[:j]+[i]+b.insns[j+1:])
    def decode(h):return lambda i:Decoder(64,bytes.fromhex(h),ip=i.ip).decode()
    def replace(k,v):
        def mutate(i):setattr(i,k,v);return i
        return mutate
    if change=='unsigned correction':edit(0x1805967c6,decode('c1f91f'))  # SAR instead of logical SHR
    elif change=='wrong multiplier':edit(first,replace('immediate32',0x88888899))
    elif change=='wrong source':edit(0x1805967bf,replace('op1_register',R.ESI))
    elif change=='wrong export':edit(0x1805967db,replace('near_branch64',0x180436160))
    elif change=='different home':edit(0x1805967d6,replace('memory_displacement',0x34))
    elif change in ('saved home','partial save overlap'):
        for ip in (0x1805967d2,0x1805967d6):edit(ip,replace('memory_displacement',0x38 if change=='saved home' else 0x36))
    elif change=='observe corrected flags':edit(0x1805967e0,decode('0f92c3'))  # SETC BL, between box and next multiply
    elif change=='observe full remainder':edit(0x18059681d,decode('488bd7'))  # mov rdx,rdi after boxing remainder
    assert (second if change=='observe full remainder' else first) not in scan()
