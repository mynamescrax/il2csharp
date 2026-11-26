from types import SimpleNamespace as NS

from il2cpp.codegen_ident import codegen_names,render_codegen_idents


def context(*others):
    names=['Codec@Vector`1<Packed>',*others]
    rows=[NS(index=i,namespace='Demo.Code',name=n,declaring=-1,generic_container=-1) for i,n in enumerate(names)]
    return NS(meta=NS(typedefs=rows))


def test_codegen_literal_name_is_one_type_and_only_rewrites_code():
    il=context();old='Codec_Vector_1<Packed>';new='Codec_Vector_1_Packed'
    lines=[f'struct {old} {{',f'string text = "{old}"; /* {old}',f'{old} */ {old} value;',f'Other.{old}.Run(); }}']
    assert render_codegen_idents(il,'Demo.Code',lines)==[
        f'struct {new} {{',lines[1],f'{old} */ {new} value;',lines[3]]
    assert render_codegen_idents(il,'Other',[f'Demo.Code.{old}.Run(); {old}.Run();'])==[f'Demo.Code.{new}.Run(); {old}.Run();']
    assert il.meta.typedefs[0].name=='Codec@Vector`1<Packed>'


def test_monomorphic_type_alias_avoids_real_names_and_ambiguous_generic_heads():
    old='Codec_Vector_1<Packed>'
    assert codegen_names(context('Codec_Vector_1_Packed'))[('Demo.Code',old)]=='Codec_Vector_1_Packed_0'
    assert not codegen_names(context('Codec_Vector`1'))
