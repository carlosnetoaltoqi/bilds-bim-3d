"""
plugin_catalogo_web (S7.17) — plugin de AutoCAD que é casca de um catálogo web → catálogo, SEM rede.

O que se prova aqui, offline:
  * `strings_utf16`/`inspecionar_dll` leem o host, o nome e a versão do plugin de um "PE" sintético
    com as strings UTF-16 que a DLL .NET tem (e uma DLL real, fixture `dll_plugin`, quando está na máquina);
    arquivo que não é PE ou não tem URL → `SystemExit` com a causa;
  * `specs_do_produto` tira do JSON da API e do HTML `details` o que vira spec: código, tamanhos,
    atributos do grupo, dimensões e peso da tabela "Dimensionais", material/normas, Tipos Revit;
  * `catalogo_de_downloads` monta o JSON do `catalogo_de_aq.py` a partir de um `manifesto.json`
    com UM IGES de verdade (uma caixa escrita pelo OpenCASCADE) — geometria em `geo/<codigo>.json`,
    produto com série = grupo, grupos sem IGES avisados, `hints.origem`;
  * `validar_lead` recusa lead incompleto e e-mail sem @.
A parte com rede (API, formulário, download) foi exercitada à mão na sessão S7.17 (registro em
`docs/historico/sessoes/`).
"""
import glob
import json
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, 'biblioteca'))
sys.path.insert(0, os.path.join(RAIZ, 'tests'))

from bim_pipeline.catalogo.fontes import plugin_catalogo_web as catallog
from fixtures import caminho as fixture

DLL_REAL = fixture('dll_plugin')
MANIFESTO_REAL = fixture('manifesto_plugin')


def _utf16(*textos):
    return b''.join(t.encode('utf-16-le') + b'\x00\x00' for t in textos)


@pytest.fixture
def dll_sintetica(tmp_path):
    p = tmp_path / 'Fake.dll'
    p.write_bytes(b'MZ' + b'\x00' * 62 + b'mscorlib' + _utf16(
        'https://exemplo.catallog.digital/pt/home', 'https://exemplo.catallog.digital', 'FileDescription', 'Exemplo CAD',
        'CompanyName', 'Catallog Software Ltda', '2.0.0.0',
    ) + b'\x00' * 16)
    return str(p)


def test_inspecionar_dll_sintetica(dll_sintetica):
    info = catallog.inspecionar_dll(dll_sintetica)
    assert info['host'] == 'https://exemplo.catallog.digital'
    assert info['hosts'] == ['https://exemplo.catallog.digital']
    assert info['plugin'] == 'Exemplo CAD'
    assert info['empresa'] == 'Catallog Software Ltda'
    assert info['versao'] == '2.0.0.0'
    assert info['dotnet'] is True


def test_inspecionar_dll_rejeita_nao_pe_e_sem_url(tmp_path):
    p = tmp_path / 'x.dll'
    p.write_bytes(b'nao e PE')
    with pytest.raises(SystemExit, match='não é um executável Windows'):
        catallog.inspecionar_dll(str(p))
    p.write_bytes(b'MZ' + b'\x00' * 100 + _utf16('sem url aqui'))
    with pytest.raises(SystemExit, match='nenhuma URL'):
        catallog.inspecionar_dll(str(p))


@pytest.mark.skipif(not DLL_REAL, reason='fixture "dll_plugin" não configurada (tests/fixtures.py)')
def test_inspecionar_dll_real():
    info = catallog.inspecionar_dll(DLL_REAL)
    assert info['host'].startswith('https://') and info['plugin'] and info['versao']
    assert isinstance(info['hosts'], list) and info['host'] in info['hosts']


def test_validar_lead():
    lead = {'full_name': ' A ', 'email': 'a@b.c', 'mobile': '1', 'company': 'x', 'position': 'y'}
    assert catallog.validar_lead(lead)['full_name'] == 'A'
    with pytest.raises(SystemExit, match="faltam \\['mobile'\\]"):
        catallog.validar_lead({**lead, 'mobile': ''})
    with pytest.raises(SystemExit, match='e-mail'):
        catallog.validar_lead({**lead, 'email': 'sem-arroba'})


DETAILS = (
    '<div><h5 class="tabs-detail-title"><span class="icon-angle"></span> Dimensionais</h5></div>'
    '<div class="tabs-detail-content"><table><thead><tr><th colspan="2">Di&acirc;metro nominal</th><th>Dimens&otilde;es em mm</th>'
    '<th rowspan="2">Peso em g</th></tr><tr><th>Polegada</th><th>mm</th><th>L</th></tr></thead>'
    '<tbody><tr><td>2.1/2"</td><td>65mm</td><td>76,5</td><td>875</td></tr></tbody></table></div></div>'
    '<div><h5 class="tabs-detail-title"><span></span> Material</h5></div><div class="tabs-detail-content"><p>Ferro male&aacute;vel ASTM A47</p></div></div>'
)
PRODUTO = {
    'code': '131601136', 'slug': 'adaptador-x', 'name': 'Adaptador 2.1/2"', 'details': DETAILS,
    'attributes': [
        {'attribute': {'name': 'Tamanho (imperial)'}, 'values': [{'value': '2.1/2"'}]},
        {'attribute': {'name': 'Tamanho (métrico)'}, 'values': [{'value': '65mm'}]},
    ],
    'brand': {'name': 'Fabricante'},
}
GRUPO = {'name': 'ADAPTADOR', 'slug': 'adaptador-1', 'description': 'Conexões grooved classe 150.',
         'hierarchy': [[{'type': 'category', 'name': 'Ranhuradas', 'slug': 'ranhuradas-17'}]],
         'attributes': [{'attribute': {'name': 'Acabamento'}, 'values': [{'value': 'Pintado'}]},
                        {'attribute': {'name': 'Diâmetro nominal'}, 'values': [{'value': '1"'}, {'value': '2"'}]}]}
PARTATOM = {'revit': 'Autodesk Revit 2017', 'partatom': {'titulo': 'Adaptador', 'tipos': [{'titulo': 'Adaptador - DN65'}, {'titulo': 'Adaptador - DN80'}]}}


def test_specs_do_produto():
    s = catallog.specs_do_produto(PRODUTO, GRUPO, PARTATOM)
    assert s['Código'] == '131601136'
    assert s['Tamanho (imperial)'] == '2.1/2"' and s['Tamanho (métrico)'] == '65mm'
    assert s['Acabamento'] == 'Pintado' and 'Diâmetro nominal' not in s   # o do grupo é a lista de todos os tamanhos
    assert s['Dimensões (mm)'] == 'L 76,5'
    assert s['Peso (g)'] == '875'
    assert s['Material'] == 'Ferro maleável ASTM A47'
    assert s['Família Revit'] == 'Adaptador (Autodesk Revit 2017)'
    assert s['Tipos Revit'] == 'DN65, DN80'


@pytest.fixture
def downloads(tmp_path):
    """Um `manifesto.json` com um IGES real (caixa 20×30×40 mm) num grupo, e um segundo grupo sem IGES."""
    step_to_geo = pytest.importorskip('bim_pipeline.conversores.step_iges')
    if not step_to_geo.HAS_OCP:
        pytest.skip('OCP não instalado')
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.IGESControl import IGESControl_Writer, IGESControl_Controller
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    d = tmp_path / 'downloads'
    (d / 'ADAPTADOR').mkdir(parents=True)
    IGESControl_Controller.Init_s()
    w = IGESControl_Writer('MM', 0)
    ex = TopExp_Explorer(BRepPrimAPI_MakeBox(20.0, 30.0, 40.0).Shape(), TopAbs_FACE)
    while ex.More():
        w.AddShape(ex.Current())
        ex.Next()
    w.ComputeModel()
    assert w.Write(str(d / 'ADAPTADOR' / 'caixa.igs'))
    manifesto = {'host': 'https://exemplo.catallog.digital', 'arquivos': [{
        'grupo': {'name': 'ADAPTADOR', 'slug': 'adaptador-1', 'code': 'TG05'}, 'produto': None, 'produto_detalhe': PRODUTO,
        'resource_id': 'r1', 'tipo': '.igs', 'titulo': 'caixa', 'bytes': 1234, 'sha256': 'x', 'arquivo': 'ADAPTADOR/caixa.igs', 'url': 'u',
    }]}
    (d / 'manifesto.json').write_text(json.dumps(manifesto), encoding='utf-8')
    (d / 'grupos.json').write_text(json.dumps([GRUPO, {'name': 'CRUZETA', 'slug': 'cruzeta-1', 'hierarchy': GRUPO['hierarchy']}]), encoding='utf-8')
    return d


def test_catalogo_de_downloads(downloads, tmp_path):
    geo_dir = tmp_path / 'geo'
    r = catallog.catalogo_de_downloads(str(downloads), str(geo_dir), progresso=lambda _m: None,
                                       extra_specs={'Plugin AutoCAD': 'Exemplo CAD 2.0.0.0'}, origem={'categoria': 'ranhuradas-17'})
    assert r['config'] == {'slug': 'ranhuradas', 'titulo': 'Ranhuradas', 'fabricante': 'Fabricante',
                           'descricao': 'Conexões grooved classe 150.', 'layout': 'catalog-grid'}
    assert r['n_geometrias'] == 1 and r['catalog']['filtros'] == ['ADAPTADOR']
    p = r['catalog']['produtos'][0]
    assert p['id'] == 'adaptador-x' and p['nome'] == 'Adaptador 2.1/2"' and p['serie'] == 'ADAPTADOR' and p['codigo'] == '131601136'
    assert p['geo'] == '131601136.json' and (geo_dir / '131601136.json').exists()
    geo = json.loads((geo_dir / '131601136.json').read_text())
    assert set(geo) == {'pos', 'col', 'idx'} and len(geo['idx']) // 3 == 12
    assert p['specs']['Fonte 3D'] == 'caixa.igs' and p['specs']['Plugin AutoCAD'] == 'Exemplo CAD 2.0.0.0'
    assert p['specs']['URL'] == 'https://exemplo.catallog.digital/pt/product/adaptador-x'
    assert any('CRUZETA' in a and 'sem IGES' in a for a in r['diag']['avisos'])
    o = r['hints']['origem']
    assert o['host'] == 'https://exemplo.catallog.digital' and o['grupos'] == 2 and o['grupos_sem_igs'] == ['CRUZETA'] and o['categoria'] == 'ranhuradas-17'
    # segunda chamada reaproveita a geometria (não tessela de novo) e dá o mesmo catálogo
    r2 = catallog.catalogo_de_downloads(str(downloads), str(geo_dir), progresso=lambda _m: None)
    assert r2['catalog']['produtos'][0]['geo'] == p['geo']


def test_catalogo_sem_manifesto_acusa(tmp_path):
    with pytest.raises(FileNotFoundError):
        catallog.catalogo_de_downloads(str(tmp_path), str(tmp_path / 'geo'), progresso=lambda _m: None)


@pytest.mark.skipif(not MANIFESTO_REAL, reason='fixture "manifesto_plugin" não configurada (tests/fixtures.py)')
def test_manifesto_real_tem_igs_e_rfa():
    man = json.load(open(MANIFESTO_REAL, encoding='utf-8'))
    tipos = {a['tipo'] for a in man['arquivos']}
    assert {'.igs', '.rfa'} <= tipos
    for a in man['arquivos']:
        assert os.path.exists(os.path.join(os.path.dirname(MANIFESTO_REAL), a['arquivo'])), a['arquivo']
