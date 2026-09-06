"""build.py — a geração tem de ACUSAR erro (critério da fase 'passar a limpo').

I1: miniaturas indisponíveis derrubam o build, salvo --allow-no-thumbs/--skip-thumbs;
    thumbCount no manifest.
I2: peças sem 3D separadas por motivo (tubos/kits × simbologia descartada).
I3: OQ3DAvisoParse agregado por simbologia e impresso no resumo.
C1: série com aspas não quebra o HTML.
"""
import json
import os
import shutil
import sqlite3
import zipfile

import pytest

import build
from bim_pipeline.miniaturas import render as miniaturas
from bim_pipeline.aq import oq3d
from bim_pipeline.aq import read_aq
from conftest import ROOT, args_build
from oq3d_sintetico import com_raizes_declaradas, com_versao_malha, triangulo


def _config_akato(aq):
    config, _ = build.auto_config(aq)
    return config


def _diag_vazio():
    return {'pecas_sem_simbologia': 0, 'pecas_sim_descartada': 0, 'sim_sem_blob': 0,
            'sim_nao_oq3d': 0, 'sim_ilegivel': [], 'sim_vazia': [], 'avisos': []}


# ── inferência e catálogo ─────────────────────────────────────────────────────

def test_auto_config_akato(akato_aq):
    config = _config_akato(akato_aq)
    assert (config['fabricante'], config['titulo'], config['slug'], config['layout']) == \
        ('Akato', 'PVC Construção Civil', 'pvc-construcao-civil', 'catalog-grid')
    # I6 (S7.10): sem ifc_dir/file_map/products_override — o config só descreve o .aq
    assert set(config) == {'slug', 'titulo', 'fabricante', 'descricao', 'layout', 'aq_file'}


def test_modo_ifc_removido(capsys):
    # I6 (S7.10): a CLI recusa --ifc e o módulo não tem mais o caminho IFC
    with pytest.raises(SystemExit) as e:
        build.build_parser().parse_args(['--ifc'])
    assert e.value.code == 2 and 'unrecognized arguments: --ifc' in capsys.readouterr().err
    for nome in ('run_ifc_parse', 'find_aq_product', 'build_catalog', 'scan_input', 'match_slug_to_aq'):
        assert not hasattr(build, nome), nome
    assert build.find_aq_paths('/caminho/que/nao/existe') == []


def test_build_catalog_from_aq_akato(saida, akato_aq):
    geo_dir = saida / 'geo' / 'akato'
    catalog, n_geo, diag = build.build_catalog_from_aq(_config_akato(akato_aq), akato_aq, str(geo_dir))
    assert n_geo == 262 and len(catalog['produtos']) == 262
    assert diag == _diag_vazio()
    ids = [p['id'] for p in catalog['produtos']]
    assert len(set(ids)) == 262
    geos = {p['geo'] for p in catalog['produtos']}
    assert len(geos) == 262 and all((geo_dir / g).is_file() for g in geos)
    g = json.loads((geo_dir / catalog['produtos'][0]['geo']).read_text())
    assert set(g) == {'pos', 'col', 'idx'} and len(g['col']) == len(g['pos'])
    assert catalog['filtros'] == sorted(catalog['filtros']) and catalog['filtros']


# ── I2 + I3: diagnóstico separado por motivo ──────────────────────────────────

@pytest.fixture
def akato_corrompida(tmp_path, akato_aq):
    """Cópia da Akato com cinco simbologias estragadas de propósito e uma peça
    desvinculada. Devolve (caminho, ids) para o teste conferir o diagnóstico."""
    copia = tmp_path / 'akato_corrompida.aq'
    shutil.copy(akato_aq, copia)
    con = sqlite3.connect(copia)
    sids = [r[0] for r in con.execute('SELECT ID_SIMBOLOGIA_3D FROM SIMBOLOGIA_3D ORDER BY 1')]
    ids = dict(zip(['nulo', 'nao_oq3d', 'truncado', 'versao9', 'raizes'], sids[:5]))
    sim_orig = con.execute('SELECT SIMBOLOGIA_3D FROM SIMBOLOGIA_3D WHERE ID_SIMBOLOGIA_3D=?',
                           (ids['truncado'],)).fetchone()[0]
    upd = 'UPDATE SIMBOLOGIA_3D SET SIMBOLOGIA_3D=? WHERE ID_SIMBOLOGIA_3D=?'
    con.execute(upd, (None, ids['nulo']))
    con.execute(upd, (b'isto nao e OQ3D' * 4, ids['nao_oq3d']))
    con.execute(upd, (bytes(sim_orig)[: len(sim_orig) // 2], ids['truncado']))
    con.execute(upd, (com_versao_malha(triangulo(), 9), ids['versao9']))
    con.execute(upd, (com_raizes_declaradas(triangulo(), 7), ids['raizes']))
    # uma peça perde o vínculo: vira "tubo/kit" (esperado, não é defeito)
    pid_solto = con.execute('SELECT ID_PECA FROM PECA_SIMBOLOGIA_3D ORDER BY ID_PECA DESC LIMIT 1').fetchone()[0]
    con.execute('DELETE FROM PECA_SIMBOLOGIA_3D WHERE ID_PECA=?', (pid_solto,))
    con.commit()
    con.close()
    return str(copia), ids


def test_diag_separa_tubos_de_simbologia_descartada(saida, akato_corrompida, capsys):
    aq, ids = akato_corrompida
    _, por_peca = read_aq.extract_simbologias(aq)
    descartadas = {ids['nulo'], ids['nao_oq3d'], ids['truncado'], ids['versao9']}
    pecas_descartadas = sum(1 for sid in por_peca.values() if sid in descartadas)

    catalog, n_geo, diag = build.build_catalog_from_aq(
        _config_akato(aq), aq, str(saida / 'geo' / 'x'))

    assert diag['pecas_sem_simbologia'] == 1
    assert diag['pecas_sim_descartada'] == pecas_descartadas
    assert diag['sim_sem_blob'] == 1 and diag['sim_nao_oq3d'] == 1
    assert [s for s, _, _ in diag['sim_ilegivel']] == [ids['truncado']]
    assert 'truncado' in diag['sim_ilegivel'][0][2]
    assert [s for s, _ in diag['sim_vazia']] == [ids['versao9']]
    avisos_por_sim = {s for s, _, _ in diag['avisos']}
    assert avisos_por_sim == {ids['versao9'], ids['raizes']}
    # a simbologia com raízes divergentes TEM geometria e entra no catálogo
    assert n_geo == 262 - len(descartadas)
    assert len(catalog['produtos']) == 262 - 1 - pecas_descartadas

    assert build.resumo_diag(diag) is True
    out = capsys.readouterr().out
    assert '1 peça(s) sem simbologia 3D (tubos/kits)' in out
    assert '4 simbologia(s) descartada(s)' in out and '1 sem blob' in out
    assert f'sim {ids["truncado"]} ' in out and 'truncado' in out
    assert '2 simbologia(s) com aviso de parse' in out
    assert f'sim {ids["raizes"]} ' in out and 'declara 7 objetos-raiz' in out


def test_resumo_diag_limpo_nao_imprime(capsys):
    assert build.resumo_diag(_diag_vazio()) is False
    assert capsys.readouterr().out == ''


def test_resumo_diag_so_tubos_nao_e_problema(capsys):
    d = _diag_vazio()
    d['pecas_sem_simbologia'] = 312
    assert build.resumo_diag(d) is False
    assert '312 peça(s) sem simbologia 3D (tubos/kits) puladas — esperado' in capsys.readouterr().out


# ── C1: render dos dois layouts com aspas e HTML na série ─────────────────────

def _catalog_minimo(saida, layout, serie):
    geo_dir = saida / 'geo' / 'mini'
    geo_dir.mkdir(parents=True)
    (geo_dir / 'g.json').write_text(json.dumps({'pos': [0, 0, 0, 1, 0, 0, 0, 1, 0],
                                                'col': [1, 0, 0] * 3, 'idx': [0, 1, 2]}))
    catalog = {
        'slug': 'mini', 'titulo': 'Título <mini>', 'fabricante': 'Fab "X"', 'descricao': '',
        'layout': layout, 'filtros': [serie],
        'produtos': [{'id': 'p1', 'nome': 'Peça 1" <b>', 'serie': serie, 'geo': 'g.json',
                      'potencia': None, 'conexoes': '', 'specs': {}, 'curva': None}],
    }
    return catalog, geo_dir


@pytest.mark.parametrize('layout', ['catalog-grid', 'series-rows'])
def test_render_escapa_aspas_e_html(saida, layout):
    serie = 'Adaptador 1" x 1" <script>'
    catalog, geo_dir = _catalog_minimo(saida, layout, serie)
    assert build.build_preview(catalog, layout, geo_dir=str(geo_dir), thumbs_dir=None)
    html = (saida / 'preview' / 'mini' / 'index.html').read_text(encoding='utf-8')
    assert '{%' not in html and '{{' not in html          # Jinja de fato renderizou
    assert '<script>' not in serie or '<script>' in html   # o do template existe…
    assert serie not in html                               # …mas a série nunca sai crua
    assert '&#34; x 1&#34;' in html or '&quot; x 1&quot;' in html
    assert '\\u003cscript\\u003e' in html                  # tojson sob autoescape
    assert (saida / 'preview' / 'mini' / 'data' / 'g.json').is_file()



# ── I7: sem Jinja2 (ou sem template) o preview falha alto ─────────────────────

def test_render_sem_jinja2_lanca_e_nao_escreve_html(saida, monkeypatch):
    # Antes da S7.7 um "fallback" trocava só `{{ catalog | tojson }}` por texto e
    # entregava um index.html com `{% for %}` cru e nenhum card — e run_build
    # ignorava o `return False` e seguia gerando o ZIP.
    catalog, geo_dir = _catalog_minimo(saida, 'catalog-grid', 'S')
    monkeypatch.setattr(build, 'HAS_JINJA2', False)
    with pytest.raises(RuntimeError, match='Jinja2'):
        build.build_preview(catalog, 'catalog-grid', geo_dir=str(geo_dir), thumbs_dir=None)
    assert not (saida / 'preview' / 'mini').exists()   # falha antes de copiar nada


def test_render_layout_inexistente_lanca_listando_os_disponiveis(saida):
    catalog, geo_dir = _catalog_minimo(saida, 'nao-existe', 'S')
    with pytest.raises(RuntimeError, match='nao-existe.*catalog-grid'):
        build.build_preview(catalog, 'nao-existe', geo_dir=str(geo_dir), thumbs_dir=None)


def test_run_build_sem_jinja2_nao_gera_zip(saida, akato_aq, monkeypatch):
    monkeypatch.setattr(build, 'HAS_JINJA2', False)
    config = _config_akato(akato_aq)
    with pytest.raises(RuntimeError, match='Jinja2'):
        build.run_build(config, akato_aq, str(saida / 'geo' / config['slug']),
                        str(saida / 'zips'), args_build('--skip-thumbs'))
    assert not list(saida.glob('zips/*.zip'))

# ── ZIP / manifest ────────────────────────────────────────────────────────────

def test_build_zip_manifest_com_thumbcount(saida):
    catalog, geo_dir = _catalog_minimo(saida, 'catalog-grid', 'S')
    catalog['produtos'].append(dict(catalog['produtos'][0], id='p2', thumb='g.webp'))
    catalog['produtos'][0]['thumb'] = 'g.webp'
    thumbs_dir = saida / 'thumbs' / 'mini'
    thumbs_dir.mkdir(parents=True)
    (thumbs_dir / 'g.webp').write_bytes(b'RIFF....WEBP')
    zip_path = build.build_zip(catalog, out_dir=str(saida / 'zips'), geo_dir=str(geo_dir),
                               thumbs_dir=str(thumbs_dir))
    with zipfile.ZipFile(zip_path) as z:
        nomes = z.namelist()
        manifest = json.loads(z.read('manifest.json'))
    assert manifest['productCount'] == 2 and manifest['thumbCount'] == 1
    assert nomes.count('geo/g.json') == 1 and nomes.count('thumbs/g.webp') == 1
    assert set(manifest) >= {'slug', 'title', 'manufacturer', 'layout', 'filters'}


def test_build_zip_sem_thumbs_dir_thumbcount_zero(saida):
    catalog, geo_dir = _catalog_minimo(saida, 'catalog-grid', 'S')
    zip_path = build.build_zip(catalog, out_dir=str(saida / 'zips'), geo_dir=str(geo_dir),
                               thumbs_dir=None)
    with zipfile.ZipFile(zip_path) as z:
        assert json.loads(z.read('manifest.json'))['thumbCount'] == 0
        assert not [n for n in z.namelist() if n.startswith('thumbs/')]


# ── I1: miniaturas indisponíveis ──────────────────────────────────────────────

@pytest.fixture
def sem_node(monkeypatch):
    # build_thumbs mora em miniaturas.py (E2) e procura o Node pelo módulo dele
    monkeypatch.setattr(miniaturas, '_find_node', lambda: None)


def _run_akato(saida, aq, *flags):
    config = _config_akato(aq)
    return build.run_build(config, aq, str(saida / 'geo' / config['slug']),
                           str(saida / 'zips'), args_build('--skip-preview', *flags))


def test_build_thumbs_sem_node_lanca(saida, sem_node):
    catalog, geo_dir = _catalog_minimo(saida, 'catalog-grid', 'S')
    with pytest.raises(build.ThumbsError, match='Node >= 20'):
        build.build_thumbs(catalog, str(geo_dir), str(saida / 'thumbs' / 'mini'))
    assert not (saida / 'thumbs' / 'mini' / '.thumbs-config.json').exists()


def test_run_build_sem_thumbs_falha_por_padrao(saida, akato_aq, sem_node, capsys):
    with pytest.raises(build.ThumbsError):
        _run_akato(saida, akato_aq)
    out = capsys.readouterr().out
    assert 'ERRO: miniaturas' in out and '--allow-no-thumbs' in out
    assert not list(saida.glob('zips/*.zip'))


def test_run_build_allow_no_thumbs_segue_com_aviso(saida, akato_aq, sem_node, capsys):
    catalog, zip_path = _run_akato(saida, akato_aq, '--allow-no-thumbs')
    assert zip_path and len(catalog['produtos']) == 262
    assert 'AVISO: miniaturas' in capsys.readouterr().out
    with zipfile.ZipFile(zip_path) as z:
        m = json.loads(z.read('manifest.json'))
    assert m['thumbCount'] == 0 and m['productCount'] == 262
    assert not any(p.get('thumb') for p in catalog['produtos'])


def test_run_build_skip_thumbs_nem_tenta(saida, akato_aq, monkeypatch, capsys):
    def explode(*a, **k):
        raise AssertionError('build_thumbs não devia ser chamado com --skip-thumbs')
    monkeypatch.setattr(build, 'build_thumbs', explode)
    _, zip_path = _run_akato(saida, akato_aq, '--skip-thumbs')
    assert zip_path and 'Miniaturas puladas (--skip-thumbs)' in capsys.readouterr().out


def test_run_all_sem_thumbs_sai_com_1(saida, akato_aq, sem_node, tmp_path, capsys):
    entrada = tmp_path / 'input' / 'Akato' / 'PVC Construção Civil'
    entrada.mkdir(parents=True)
    os.symlink(akato_aq, entrada / os.path.basename(akato_aq))
    with pytest.raises(SystemExit) as e:
        build.run_all(str(tmp_path / 'input'), args_build('--all', '--skip-preview'))
    assert e.value.code == 1
    out = capsys.readouterr().out
    assert 'falhas  : 1' in out and 'Node >= 20' in out


def test_cli_tem_as_flags():
    a = args_build('--allow-no-thumbs')
    assert a.allow_no_thumbs and not a.skip_thumbs
    a = args_build()
    assert not a.allow_no_thumbs and not a.skip_thumbs


# ── miniatura de verdade (Chromium) ───────────────────────────────────────────

@pytest.mark.thumbs
def test_build_thumbs_renderiza_uma_geometria(saida, akato_aq):
    if not build._find_node():
        pytest.skip('sem Node >= 20 (nvm) — o passo de miniaturas não roda aqui')
    if not (ROOT / 'node_modules' / 'playwright').is_dir():
        pytest.skip('playwright não instalado na raiz (npm install)')
    sims, _ = read_aq.extract_simbologias(akato_aq)
    # Uma peça compacta, não um tubo de 6 m: o tubo renderiza como uma linha de
    # 1 px (926 bytes de WebP) e não prova nada. Bounding box com proporção < 5.
    sid = next(s for s in sorted(sims)
               if max(oq3d.bbox(sims[s]['blob'])) / max(min(oq3d.bbox(sims[s]['blob'])), 1e-9) < 5)
    geo_dir = saida / 'geo' / 'um'
    geo_dir.mkdir(parents=True)
    (geo_dir / 'a.json').write_text(json.dumps(oq3d.to_buffers(sims[sid]['blob'])))
    catalog = {'produtos': [{'id': 'a', 'geo': 'a.json'}, {'id': 'b', 'geo': 'a.json'}]}
    n = build.build_thumbs(catalog, str(geo_dir), str(saida / 'thumbs' / 'um'))
    assert n == 1
    webp = saida / 'thumbs' / 'um' / f'a.{build.THUMB_EXT}'
    assert webp.is_file() and webp.read_bytes()[:4] == b'RIFF' and webp.stat().st_size > 1000
    assert all(p['thumb'] == f'a.{build.THUMB_EXT}' for p in catalog['produtos'])
