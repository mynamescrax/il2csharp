from dotnet_case import run_case
from il2cpp import Decompiler


def test_preheader_copy_can_disagree_after_backedge(tmp_path):
    d=Decompiler.__new__(Decompiler)
    # Both copies are true before the loop. A conditional ref write breaks
    # the first equality; changing the other copy itself breaks the second.
    lines=['int num1 = 2;','int num2 = num1;','int num3 = num1;',
           'do','{','Observe(num2,num3);','if (num2 == 2)','{','Replace(ref num1);','}',
           'num2 -= 1;','}','while (num2 >= 0);']
    rendered=d._copy_prop(lines);runner=tmp_path/'runner';runner.mkdir()
    src='''using System;using System.Collections.Generic;
var seen=new List<string>();void Observe(int i,int origin)=>seen.Add(i+":"+origin);void Replace(ref int n)=>n=8;
'''+ '\n'.join(rendered)+'''\nif(string.Join(",",seen)!="2:2,1:2,0:2")throw new Exception(string.Join(",",seen));
Console.WriteLine("descending counter and independent saved value passed");'''
    (runner/'Program.cs').write_text(src,encoding='utf8');run_case(tmp_path,runner)


def test_immutable_alias_can_still_propagate_in_loop():
    d=Decompiler.__new__(Decompiler);out=d._copy_prop(['int num2 = num1;','while (More())','{','Use(num2);','}'])
    assert 'Use(num1);' in out


def test_loop_cannot_replay_mutated_struct_as_saved_copy():
    d=Decompiler.__new__(Decompiler);out=d._copy_prop(['Point obj2 = obj1;','do','{','Observe(obj2.X);','obj1.X++;','}','while (More());'])
    assert 'Observe(obj2.X);' in out and 'Point obj2 = obj1;' in out
