from types import SimpleNamespace as NS

from il2cpp import Decompiler,Expr


def test_dword_phi_needs_all_final_incoming_int_types():
    i4=(0,8<<16);u4=(0,9<<16)
    for right,want in [(i4,True),(u4,False),(None,False)]:
        d=Decompiler.__new__(Decompiler);d._var_types={'v1':i4};d.L=NS(_type_hints={'v2':right},il=NS(_closed_type_key=lambda t:(t[1]>>16,0)))
        s=[NS(end_state={'RSI':Expr('v1',None,'int')}),NS(end_state={'RSI':Expr('v2',None,'int')}),NS(preds=[0,1])]
        d._finish_int_copies(s,{(2,'RSI'):'v3'});assert (d._var_types.get('v3')==i4)==want
