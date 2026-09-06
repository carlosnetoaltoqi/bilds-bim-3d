"""
familias_revit — famílias Revit (.rfa + type catalog .txt) → catálogo, SEM o Revit e sem rede.

O que se prova aqui, offline e sem `.rfa` real:
  * `type_catalog`: cabeçalho `NOME##TIPO##UNIDADE`, vírgula e TAB, aspas, cp1252 sem BOM e UTF-16 com
    BOM, conversão para mm (comprimento sem unidade é pé), rótulo de unidade;
  * `rfa_partatom.info_basica`: a versão nos dois formatos do `BasicFileInfo` (texto corrido até 2019,
    "Format:/Build:" de 2020 em diante) e o locale;
  * `perfis`: todo sólido gerado é FECHADO (zero arestas de borda) com o volume analítico — a checagem
    de `formas-representativas.md`; `deitar` e `assentar` são rotações próprias (volume continua positivo);
  * `familias_revit`: valores com unidade → mm (inclusive polegada fracionária), sinônimos EN/PT das
    cotas, a escolha da forma (I, U, tubo retangular/redondo, caixa, chapa perfilada com capa), a fusão
    type catalog × PartAtom (o tipo-molde do .rfa não vira produto), `cp1252_seguro`, e o catálogo
    inteiro a partir de famílias sintéticas: contrato `catalogo`, um `<geo>.json` válido por geometria,
    geometria compartilhada entre tipos de mesma cota mas NÃO entre viga e pilar, série com a ressalva,
    specs com "Geometria 3D" e "Fonte 3D", geometria irmã ilegível cai na forma representativa com aviso,
    tipo sem cota fica fora com aviso, `.zip` com caminho suspeito ignorado, `.rvt` recusado;
  * com a fixture `rfa_familias` (um .zip/pasta real de famílias com type catalogs), o caminho inteiro
    pela CLI: `inspecionar` emite o contrato `info-familias-revit` e `importar` publica tudo.
"""
import json
import os
import subprocess
import sys
import zipfile

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, 'biblioteca'))
sys.path.insert(0, os.path.join(RAIZ, 'tests'))

from bim_pipeline import contratos                                     # noqa: E402
from bim_pipeline.catalogo.fontes import familias_revit as fr          # noqa: E402
from bim_pipeline.conversores import rfa_partatom, type_catalog        # noqa: E402
from bim_pipeline.geometria import perfis                              # noqa: E402
from fixtures import caminho as fixture                                # noqa: E402

FAMILIAS_REAIS = fixture('rfa_familias')


# ─── type catalog ─────────────────────────────────────────────────────────────

TXT = (',Largura##SECTION_PROPERTY##MILLIMETERS,Altura##SECTION_PROPERTY##MILLIMETERS,Peso nominal##WEIGHT_PER_UNIT_LENGTH##KILOGRAMS_FORCE_PER_METER,'
       'Descrição##OTHER##,Vão##LENGTH##\r\n'
       'Tubo ret 25 x 15 x 0.75,15,25,0.44,"Perfil, retangular",2\r\n'
       'Tubo ret 30 x 20 x 0.9,20,30,0.66,Perfil retangular,\r\n\r\n')


def test_type_catalog_virgula_cp1252():
    r = type_catalog.parsear(type_catalog.decodificar(TXT.encode('cp1252')))
    assert [c['nome'] for c in r['colunas']] == ['Largura', 'Altura', 'Peso nominal', 'Descrição', 'Vão']
    assert r['colunas'][0] == {'nome': 'Largura', 'tipo': 'SECTION_PROPERTY', 'unidade': 'MILLIMETERS'}
    assert r['colunas'][3]['unidade'] is None
    assert [t['titulo'] for t in r['tipos']] == ['Tubo ret 25 x 15 x 0.75', 'Tubo ret 30 x 20 x 0.9']
    p = r['tipos'][0]['parametros']
    assert p['Largura']['mm'] == 15.0 and p['Altura']['mm'] == 25.0
    assert p['Peso nominal'] == {'valor': '0.44', 'tipo': 'WEIGHT_PER_UNIT_LENGTH', 'unidade': 'KILOGRAMS_FORCE_PER_METER', 'mm': None}
    assert p['Descrição']['valor'] == 'Perfil, retangular'          # aspas protegem a vírgula
    assert p['Vão']['mm'] == pytest.approx(2 * 304.8)               # comprimento sem unidade é pé
    assert r['tipos'][1]['parametros']['Vão']['mm'] is None         # célula vazia


def test_type_catalog_tab_e_utf16():
    tab = TXT.replace(',', '\t').replace('"Perfil\t retangular"', '"Perfil, retangular"')
    r = type_catalog.parsear(type_catalog.decodificar(('\ufeff' + tab).encode('utf-16')))
    assert type_catalog.separador(tab) == '\t'
    assert len(r['tipos']) == 2 and r['tipos'][0]['parametros']['Altura']['mm'] == 25.0
    assert type_catalog.eh_type_catalog(tab) and type_catalog.eh_type_catalog(TXT)
    assert not type_catalog.eh_type_catalog('leia-me: instale a família no Revit')
    assert type_catalog.rotulo_unidade('KILOGRAMS_FORCE_PER_METER') == 'kgf/m'
    assert type_catalog.rotulo_unidade(None) == '' and type_catalog.rotulo_unidade('FURLONGS') == 'furlongs'
    assert type_catalog.para_mm('1 1/2', 'LENGTH', 'INCHES') == pytest.approx(38.1)   # polegada fracionária
    assert type_catalog.para_mm('3/4"', 'LENGTH', 'INCHES') == pytest.approx(19.05)
    assert type_catalog.para_mm('2,5', 'LENGTH', 'METERS') == 2500.0 and type_catalog.para_mm('x', 'LENGTH', 'METERS') is None


# ─── BasicFileInfo ────────────────────────────────────────────────────────────

def test_info_basica_nos_dois_formatos():
    antigo = 'x\x00Autodesk Revit MEP 2014 (Build: 20130308_1515(x64))\x00C:\\x\\f.rfa\x00'
    i = rfa_partatom.info_basica(antigo)
    assert i['formato'] == 2014 and i['build'] == '20130308_1515(x64)' and i['revit'].startswith('Autodesk Revit 2014')
    novo = ('\x0e\x04 2021 20220517_1515(x64) C:\\a\\Familia.rfa\nAutodesk Revit\nRevitApplication\nFormat: 2021\nBuild: 20220517_1515(x64)\n'
            'Last Save Path: C:\\a\\Familia.rfa\nOpen Workset Default: 3\nLocale when saved: PTB\n')
    i = rfa_partatom.info_basica(novo)
    assert i == {'revit': 'Autodesk Revit 2021 (Build: 20220517_1515(x64))', 'formato': 2021, 'build': '20220517_1515(x64)',
                 'caminho_original': 'C:\\a\\Familia.rfa', 'locale': 'PTB'}
    assert rfa_partatom.info_basica('nada')['formato'] is None
    # os dois alinhamentos de um bloco UTF-16LE que começa em byte ímpar
    b = b'\x00' + 'Format: 2019'.encode('utf-16-le')
    assert 'Format: 2019' in rfa_partatom._texto_utf16_ambos(b)


# ─── perfis ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('nome, aneis, volume', [
    ('caixa', [perfis.retangulo(10, 20)], 10 * 20 * 100),
    ('tubo retangular', [perfis.retangulo(10, 20), perfis.retangulo(8, 18)], (200 - 144) * 100),
    ('perfil I', [perfis.secao_i(14, 35, 0.63, 0.475)], (2 * 14 * 0.63 + (35 - 1.26) * 0.475) * 100),
    ('perfil U', [perfis.secao_u(5, 15, 0.5, 0.4)], (2 * 5 * 0.5 + (15 - 1.0) * 0.4) * 100),
    ('cantoneira', [perfis.secao_l(5, 5, 0.5)], (5 * 0.5 + 4.5 * 0.5) * 100),
])
def test_extrusao_fechada_com_volume_analitico(nome, aneis, volume):
    verts, tris = perfis.extrudar(aneis, 100)
    assert perfis.arestas_de_borda(tris) == 0, nome
    assert perfis.volume_assinado(verts, tris) == pytest.approx(volume, rel=1e-9), nome
    # rotações próprias: o volume continua positivo (normais para fora) e o comprimento muda de eixo
    assert perfis.volume_assinado(perfis.deitar(verts), tris) == pytest.approx(volume, rel=1e-9)
    assert perfis.bbox(perfis.deitar(verts))[0] == 100.0
    assert perfis.volume_assinado(perfis.assentar(verts, 100), tris) == pytest.approx(volume, rel=1e-9)


def test_tubo_redondo_e_chapa_fechados():
    verts, tris = perfis.extrudar([perfis.circulo(10, 48), perfis.circulo(8, 48)], 100)
    assert perfis.arestas_de_borda(tris) == 0
    import math
    assert perfis.volume_assinado(verts, tris) == pytest.approx(math.pi * (25 - 16) * 100, rel=0.01)
    placas = perfis.chapa_trapezoidal(84, 5.9, 0.08, 28, comprimento=100)
    assert placas and all(perfis.arestas_de_borda(t) == 0 for _v, t in placas)
    assert all(perfis.volume_assinado(v, t) > 0 for v, t in placas)
    assert perfis.bbox([p for v, _t in placas for p in v])[0] == pytest.approx(84.0)
    with pytest.raises(ValueError):
        perfis.extrudar([perfis.retangulo(1, 1), perfis.circulo(0.5, 8)], 10)   # furo com contagem diferente
    assert perfis.triangular([(0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4)]) and len(perfis.triangular(perfis.secao_i(10, 20, 1, 1))) == 10


# ─── familias_revit: valores, cotas, formas ───────────────────────────────────

def test_valor_em_mm():
    assert fr.valor_em_mm('350.00 mm') == 350.0
    assert fr.valor_em_mm('0.84 m') == pytest.approx(840.0)
    assert fr.valor_em_mm('29 7/8"') == pytest.approx(758.825)
    assert fr.valor_em_mm('3/4"') == pytest.approx(19.05)
    assert fr.valor_em_mm('15') == 15.0
    assert fr.valor_em_mm('15', 'Length') == 15.0 and fr.valor_em_mm('15', 'Text') is None
    assert fr.valor_em_mm('Aço ASTM A36') is None and fr.valor_em_mm('') is None


def _p(**kv):
    return {k: {'valor': v, 'tipo': None, 'unidade': None, 'mm': None} for k, v in kv.items()}


def test_dimensoes_por_sinonimo_en_pt():
    d = fr.dimensoes(_p(**{'Width': '140.00 mm', 'Height': '350.00 mm', 'Flange Thickness': '6.3 mm', 'Web Thickness': '4.75 mm', 'Manufacturer': 'X'}))
    assert d == {'largura': 140.0, 'altura': 350.0, 'espessura_flange': 6.3, 'espessura_alma': 4.75}
    d = fr.dimensoes(_p(**{'Largura': '15', 'Altura': '25', 'Espessura nominal da parede': '0.75', 'Espessura de projeto da parede': '0.75'}))
    assert d == {'largura': 15.0, 'altura': 25.0, 'espessura_parede': 0.75}          # o primeiro sinônimo fica com a cota
    d = fr.dimensoes(_p(**{'Espessura da chapa': '0.80 mm', 'Largura do módulo': '0.84 m', 'Capa de concreto': 'Yes', 'Espessura capa de concreto': '50 mm'}))
    assert d == {'espessura_chapa': 0.8, 'largura_modulo': 840.0, 'capa': True, 'espessura_capa': 50.0}
    d = fr.dimensoes(_p(**{'Depth': '300 mm', 'Width': '100 mm', 'Flange Thickness': '10 mm', 'Web Thickness': '6 mm'}))
    assert d['altura'] == 300.0 and 'profundidade' not in d                              # "Depth" de perfil é a altura


def _forma(dims, titulo='Viga X', cat=None, material='Aço'):
    r = fr.forma_representativa(dims, titulo, cat, material)
    assert r, 'sem forma'
    nome, malhas, regra = r
    for v, t, rgba in malhas:
        assert perfis.arestas_de_borda(t) == 0 and perfis.volume_assinado(v, t) > 0 and len(rgba) == 4
    return nome, malhas, regra


def test_escolha_da_forma():
    nome, m, regra = _forma({'largura': 140, 'altura': 350, 'espessura_flange': 6.3, 'espessura_alma': 4.75})
    assert nome == 'perfil_i' and 'aprox' in regra and perfis.bbox(m[0][0]) == (100.0, 14.0, 35.0)   # viga: deitada, 1 m
    nome, m, _ = _forma({'largura': 140, 'altura': 350, 'espessura_flange': 6.3, 'espessura_alma': 4.75}, 'Pilar X')
    assert nome == 'perfil_i' and perfis.bbox(m[0][0]) == (14.0, 35.0, 100.0)                          # pilar: em pé
    assert _forma({'largura': 50, 'altura': 100, 'espessura_flange': 5, 'espessura_alma': 4}, 'Perfil U 100')[0] == 'perfil_u'
    assert _forma({'largura': 50, 'altura': 50, 'espessura_parede': 5}, 'Cantoneira L 50x5')[0] == 'cantoneira'
    assert _forma({'largura': 15, 'altura': 25, 'espessura_parede': 0.75})[0] == 'tubo_retangular'
    assert _forma({'diametro': 12.7, 'espessura_parede': 0.75})[0] == 'tubo_redondo'
    assert _forma({'diametro': 12.7})[0] == 'barra_redonda'
    nome, m, regra = _forma({'largura': 600, 'altura': 850, 'profundidade': 700}, 'Forno de embutir')
    assert nome == 'caixa' and 'aprox' not in regra
    nome, m, regra = _forma({'largura': 600, 'altura': 850}, 'Painel')
    assert nome == 'caixa' and 'profundidade 600 mm (aprox.)' in regra
    assert _forma({'largura': 100, 'altura': 200}, 'Viga de madeira')[0] == 'barra_retangular'
    nome, m, regra = _forma({'espessura_chapa': 0.8, 'largura_modulo': 840, 'capa': True, 'espessura_capa': 50}, 'Telha-forma', material='Aço galvanizado')
    assert nome == 'chapa_perfilada' and 'capa de concreto' in regra and m[-1][2] == perfis.COR['concreto']
    bb = perfis.bbox([p for v, _t, _c in m for p in v])
    assert bb[0] == pytest.approx(84.0) and bb[2] == pytest.approx(6.0 + 5.0 + 0.08, abs=0.1)         # 60 mm de nervura + capa
    assert fr.forma_representativa({'comprimento': 3000}, 'Só comprimento') is None
    assert fr.forma_representativa({}, 'Nada') is None
    # comprimento do tipo, quando plausível, substitui o trecho inventado
    _n, m, regra = _forma({'largura': 50, 'altura': 100, 'espessura_parede': 3, 'comprimento': 6000})
    assert 'comprimento do tipo' in regra and perfis.bbox(m[0][0])[0] == 600.0


def test_cp1252_seguro():
    assert fr.cp1252_seguro('Aço ASTM A36 – ½"') == ('Aço ASTM A36 – ½"', False)
    assert fr.cp1252_seguro('DN ≥ 50 → 60 ∅') == ('DN >= 50 -> 60 diam.', True)
    assert fr.cp1252_seguro('日本') == ('??', True)
    assert fr.cp1252_seguro(None) == ('', False)
    assert fr.humanizar('Viga_PerfilSoldado-VS_Empresa') == 'Viga PerfilSoldado-VS Empresa'


def test_fundir_tipos_type_catalog_manda():
    partatom = {'Molde': {'Width': {'valor': '15.00 mm', 'tipo': 'Section Property', 'unidade': None, 'mm': 15.0},
                          'Manufacturer': {'valor': 'Empresa', 'tipo': 'Text', 'unidade': None, 'mm': None}}}
    txt = {'tipos': [{'titulo': 'A', 'parametros': {'Width': {'valor': '20', 'tipo': 'SECTION_PROPERTY', 'unidade': 'MILLIMETERS', 'mm': 20.0}}},
                     {'titulo': 'B', 'parametros': {'Width': {'valor': '30', 'tipo': 'SECTION_PROPERTY', 'unidade': 'MILLIMETERS', 'mm': 30.0}}}]}
    fund = fr.fundir_tipos(partatom, txt)
    assert [t for t, _ in fund] == ['A', 'B']                                   # o tipo-molde do .rfa não é produto
    assert fund[0][1]['Width']['mm'] == 20.0                                    # o .txt manda na cota
    assert fund[0][1]['Manufacturer']['valor'] == 'Empresa'                     # constante do PartAtom vai a todos
    # sem type catalog, os tipos do PartAtom são os produtos; com vários tipos no .rfa, todos entram
    assert [t for t, _ in fr.fundir_tipos(partatom, None)] == ['Molde']
    dois = {**partatom, 'Outro': {'Width': {'valor': '99 mm', 'tipo': 'Section Property', 'unidade': None, 'mm': 99.0}}}
    assert [t for t, _ in fr.fundir_tipos(dois, txt)] == ['A', 'B', 'Molde', 'Outro']


# ─── o catálogo inteiro, com famílias sintéticas ──────────────────────────────

def _familia(titulo, tipos, categoria='23.25.30.11.14.14', pasta='perfis', geometria=None, txt=True):
    """Uma família como `ler_familia` devolve, sem precisar de um .rfa."""
    return {
        'rfa': f'/x/{pasta}/{titulo}.rfa', 'rel': f'{pasta}/{titulo}.rfa', 'pasta': pasta, 'txt': f'/x/{pasta}/{titulo}.txt' if txt else None,
        'geometria': geometria, 'titulo': titulo, 'categoria': fr._categoria({'categorias': [{'termo': categoria, 'esquema': 'adsk:revit:grouping'}]}),
        'revit': 'Autodesk Revit 2021 (Build: 1)', 'formato': 2021, 'locale': 'PTB', 'preview': True, 'type_catalog': txt,
        'parametros_familia': {}, 'avisos': [],
        'tipos': [(t, {k: {'valor': v, 'tipo': 'SECTION_PROPERTY' if k not in ('Manufacturer', 'Structural Material', 'Model') else 'TEXT',
                           'unidade': 'MILLIMETERS' if k not in ('Manufacturer', 'Structural Material', 'Model') else None,
                           'mm': float(v) if k not in ('Manufacturer', 'Structural Material', 'Model') else None} for k, v in p.items()})
                  for t, p in tipos],
    }


def _perfis(prefixo):
    return [(f'{prefixo}350X26', {'Width': '140', 'Height': '350', 'Flange Thickness': '6.3', 'Web Thickness': '4.75', 'Manufacturer': 'Empresa', 'Structural Material': 'Aço ASTM A36', 'Model': f'{prefixo}350X26'}),
            (f'{prefixo}350X30', {'Width': '140', 'Height': '350', 'Flange Thickness': '8', 'Web Thickness': '4.75', 'Manufacturer': 'Empresa', 'Structural Material': 'Aço ASTM A36'}),
            (f'{prefixo}350X26 bis', {'Width': '140', 'Height': '350', 'Flange Thickness': '6.3', 'Web Thickness': '4.75', 'Manufacturer': 'Empresa', 'Structural Material': 'Aço ASTM A36'})]


def test_catalogo_de_familias_sinteticas(tmp_path):
    fams = [
        _familia('Viga_PerfilSoldado-VS_Empresa', _perfis('VS')),
        _familia('Coluna_PerfilSoldado-VS_Empresa', _perfis('VS'), categoria='23.25.30.11.14.11'),
        _familia('Telha-Forma_Empresa', [('Esp 0.80', {'Espessura da chapa': '0.80', 'Largura do módulo': '840', 'Structural Material': 'Aço galvanizado'})], categoria='Modelos genéricos', pasta='telhas', txt=False),
        _familia('Sem_Cota', [('Tipo estranho', {'Manufacturer': 'Empresa'})]),
        _familia('Nao_Converte', _perfis('NC')[:1], geometria=str(tmp_path / 'lixo.stp')),
    ]
    (tmp_path / 'lixo.stp').write_text('isto não é um STEP')
    geo_dir = tmp_path / 'geo'
    r = fr.catalogo_de_familias(fams, str(geo_dir), titulo='Perfis ≥ teste', progresso=lambda _m: None, origem={'entrada': 'x.zip'})
    contratos.validar('catalogo', r)
    prods = r['catalog']['produtos']
    assert len(prods) == 3 + 3 + 1 + 0 + 1 and r['hints']['n_pecas'] == 8
    assert r['config']['fabricante'] == 'Empresa' and r['config']['titulo'] == 'Perfis >= teste' and r['config']['slug'] == 'perfis-teste'
    assert r['hints']['schema'] == 'familias-revit' and r['hints']['origem']['entrada'] == 'x.zip'
    assert r['hints']['origem'] == {**r['hints']['origem'], 'familias': 5, 'tipos': 9, 'com_geometria_irma': 0, 'representativas': 8, 'sem_cota': 1}
    # geometria: compartilhada entre tipos de mesma cota, não entre viga e pilar; um JSON válido por geometria
    viga = {p['nome']: p for p in prods if p['serie'].startswith('Viga')}
    pilar = {p['nome']: p for p in prods if p['serie'].startswith('Coluna')}
    assert viga['VS350X26']['geo'] == viga['VS350X26 bis']['geo'] != viga['VS350X30']['geo']
    assert viga['VS350X26']['geo'] != pilar['VS350X26']['geo']
    geos = {p['geo'] for p in prods}
    assert len(geos) == r['n_geometrias'] == 2 + 2 + 1 + 0        # a família que caiu na representativa tem a cota da viga: compartilha
    for g in geos:
        d = json.loads((geo_dir / g).read_text(encoding='utf8'))
        contratos.validar('geometria', d)
        assert len(d['col']) == len(d['pos']) and len(d['idx']) % 3 == 0
    pv = json.loads((geo_dir / viga['VS350X26']['geo']).read_text())['pos']
    pp = json.loads((geo_dir / pilar['VS350X26']['geo']).read_text())['pos']
    assert max(pv[0::3]) - min(pv[0::3]) == pytest.approx(1.0) and max(pp[1::3]) - min(pp[1::3]) == pytest.approx(1.0)   # viga em X, pilar em Y (viewer Y-up)
    # série com a ressalva, specs com a regra e a fonte, código do Model, conexões = categoria
    p = viga['VS350X26']
    assert p['serie'] == 'Viga PerfilSoldado-VS Empresa (forma representativa)'
    assert p['specs']['Fonte 3D'] == 'forma representativa (perfil_i)' and p['specs']['Geometria 3D'].startswith(fr.RESSALVA)
    assert p['specs']['Width'] == '140 mm' and p['specs']['OmniClass'] == '23.25.30.11.14.14' and p['specs']['Revit'].startswith('Autodesk Revit 2021')
    assert p['specs']['Família Revit'] == 'Viga PerfilSoldado-VS Empresa' and p['specs']['Tipo Revit'] == 'VS350X26'
    assert p['codigo'] == 'VS350X26' and viga['VS350X30']['codigo'] is None and p['conexoes'] == '23.25.30.11.14.14'
    assert p['id'] == 'viga-perfilsoldado-vs-empresa-vs350x26' and viga['VS350X26 bis']['id'] == 'viga-perfilsoldado-vs-empresa-vs350x26-bis'
    telha = next(p for p in prods if p['serie'].startswith('Telha'))
    assert telha['specs']['Categoria Revit'] == 'Modelos genéricos' and telha['conexoes'] == 'Modelos genéricos' and 'OmniClass' not in telha['specs']
    # avisos: tipo sem cota fora, geometria irmã ilegível caiu na representativa, texto ajustado para o cp1252
    avisos = ' | '.join(r['diag']['avisos'])
    assert 'Sem_Cota / Tipo estranho: sem cota reconhecível' in avisos
    assert 'lixo.stp não convertida' in avisos and next(p for p in prods if p['serie'].startswith('Nao')) ['specs']['Fonte 3D'].startswith('forma representativa')
    assert 'fora do cp1252' in avisos
    for p in prods:
        for k, v in list(p['specs'].items()) + [('n', p['nome']), ('s', p['serie'])]:
            k.encode('cp1252'); v.encode('cp1252')


def test_catalogo_com_geometria_irma_step(tmp_path):
    step_iges = pytest.importorskip('bim_pipeline.conversores.step_iges')
    if not step_iges.HAS_OCP:
        pytest.skip('OCP não instalado')
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
    caixa = tmp_path / 'Caixa_Empresa.stp'
    w = STEPControl_Writer(); w.Transfer(BRepPrimAPI_MakeBox(100.0, 200.0, 300.0).Shape(), STEPControl_AsIs); w.Write(str(caixa))
    fam = _familia('Caixa_Empresa', [('A', {'Width': '100', 'Height': '300', 'Manufacturer': 'Empresa'}), ('B', {'Width': '100', 'Height': '300', 'Manufacturer': 'Empresa'})],
                   geometria=str(caixa))
    r = fr.catalogo_de_familias([fam], str(tmp_path / 'geo'), progresso=lambda _m: None)
    contratos.validar('catalogo', r)
    a, b = r['catalog']['produtos']
    assert a['geo'] == b['geo'] == 'caixa-empresa.json' and r['n_geometrias'] == 1
    assert a['serie'] == 'Caixa Empresa' and a['specs']['Fonte 3D'] == 'Caixa_Empresa.stp' and 'compartilhada' in a['specs']['Geometria 3D']
    assert r['hints']['origem']['com_geometria_irma'] == 2 and r['hints']['origem']['representativas'] == 0
    contratos.validar('geometria', json.loads((tmp_path / 'geo' / a['geo']).read_text()))


def test_descobrir_zip_e_recusas(tmp_path):
    z = tmp_path / 'fam.zip'
    with zipfile.ZipFile(z, 'w') as zf:
        zf.writestr('pasta/Fam_A.rfa', b'nao e OLE')
        zf.writestr('pasta/Fam_A.txt', TXT.encode('cp1252'))
        zf.writestr('pasta/Fam_A.ifc', b'ISO-10303-21;')
        zf.writestr('pasta/leia-me.txt', 'instrucoes')
        zf.writestr('pasta/planilha.xlsx', b'PK')
        zf.writestr('outra/Fam_B.rfa', b'nao e OLE')
        zf.writestr('geo/Fam_B.stp', b'ISO-10303-21;')
        zf.writestr('modelo.rvt', b'x')
        zf.writestr('../fora.rfa', b'x')
    raiz, ignorados, temp = fr.preparar(str(z), progresso=lambda _m: None)
    assert temp and sorted(ignorados) == ['../fora.rfa', 'pasta/planilha.xlsx']
    d = fr.descobrir(raiz)
    assert [f['rel'] for f in d['familias']] == ['outra/Fam_B.rfa', 'pasta/Fam_A.rfa']
    a = next(f for f in d['familias'] if f['rel'].endswith('Fam_A.rfa'))
    assert a['txt'].endswith('Fam_A.txt') and a['geometria'].endswith('pasta/Fam_A.ifc') and a['pasta'] == 'pasta'
    b = next(f for f in d['familias'] if f['rel'].endswith('Fam_B.rfa'))
    assert b['txt'] is None and b['geometria'].endswith('geo/Fam_B.stp')           # irmã em outra pasta, pelo nome
    assert d['projetos'] == ['modelo.rvt']
    import shutil; shutil.rmtree(raiz)
    # .rvt direto é recusado com a explicação; extensão desconhecida também; .rfa ilegível não derruba o resto
    (tmp_path / 'm.rvt').write_bytes(b'x')
    with pytest.raises(SystemExit, match='projeto/modelo Revit'):
        fr.preparar(str(tmp_path / 'm.rvt'))
    (tmp_path / 'fam.dwg').write_bytes(b'x')
    with pytest.raises(SystemExit, match='envie um .rfa'):
        fr.preparar(str(tmp_path / 'fam.dwg'))
    with pytest.raises(SystemExit, match='nenhuma família legível'):
        fr.importar(str(z), str(tmp_path / 'geo'), progresso=lambda _m: None)


# ─── com famílias reais ───────────────────────────────────────────────────────

@pytest.mark.skipif(not FAMILIAS_REAIS, reason='fixture "rfa_familias" não configurada (tests/fixtures.py)')
def test_familias_reais_pela_cli(tmp_path):
    if not rfa_partatom.HAS_OLEFILE:
        pytest.skip('olefile não instalado')
    r = subprocess.run([sys.executable, '-m', 'bim_pipeline.cli.familias_revit', 'inspecionar', FAMILIAS_REAIS], capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    info = json.loads(r.stdout.strip().splitlines()[-1])
    contratos.validar('info-familias-revit', info)
    assert info['n_familias'] >= 1 and info['n_tipos'] >= info['n_familias']
    assert all(f['formato'] and f['formato'] >= 2011 for f in info['familias'])
    saida = tmp_path / 'c.json'
    r = subprocess.run([sys.executable, '-m', 'bim_pipeline.cli.familias_revit', 'importar', FAMILIAS_REAIS, '--geo-dir', str(tmp_path / 'geo'),
                        '--saida', str(saida), '--titulo', 'Famílias'], capture_output=True, text=True, timeout=1200)
    assert r.returncode == 0, r.stderr[-2000:]
    res = json.loads(saida.read_text(encoding='utf8'))
    contratos.validar('catalogo', res)
    prods = res['catalog']['produtos']
    assert len(prods) == info['n_tipos'] - res['hints']['origem']['sem_cota']
    assert res['n_geometrias'] == len({p['geo'] for p in prods}) == len(list((tmp_path / 'geo').glob('*.json')))
    for p in prods[::max(1, len(prods) // 20)]:
        contratos.validar('geometria', json.loads((tmp_path / 'geo' / p['geo']).read_text(encoding='utf8')))
        for k, v in p['specs'].items():
            k.encode('cp1252'); v.encode('cp1252')
        assert p['specs']['Fonte 3D'] and p['specs']['Geometria 3D'] and p['specs']['Família Revit']
