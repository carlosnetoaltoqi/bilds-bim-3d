"""bim_pipeline.catalogo — a geração tem de ACUSAR erro (critério da fase 'passar a limpo').

I2: peças sem 3D separadas por motivo (tubos/kits × simbologia descartada).
I3: OQ3DAvisoParse agregado por simbologia e impresso no resumo.
Inferência: fabricante/título/slug/layout saem do .aq e do caminho, sem perguntas.
Fixture real: `aq_pequena` (uma biblioteca inteira com geometria em toda peça — ver tests/fixtures).
"""
import json
import shutil
import sqlite3

import pytest

from bim_pipeline.aq import read_aq
from bim_pipeline.catalogo.catalogo import build_catalog_from_aq, diag_vazio, montar_resultado, resumo_diag
from bim_pipeline.catalogo.inferencia import auto_config, find_aq_paths
from fixtures import FIXTURAS
from oq3d_sintetico import com_raizes_declaradas, com_versao_malha, triangulo


def _config(aq):
    return auto_config(aq)[0]


def test_auto_config_so_descreve_o_aq(aq_pequena):
    config, hints = auto_config(aq_pequena)
    esperado = FIXTURAS['aq_pequena']
    assert (config['fabricante'], config['titulo'], config['slug'], config['layout']) == \
        (esperado['fabricante'], esperado['titulo'], esperado['slug'], esperado['layout'])
    assert set(config) == {'slug', 'titulo', 'fabricante', 'descricao', 'layout', 'aq_file'}
    assert hints['n_pecas'] == esperado['pecas']
    assert find_aq_paths('/caminho/que/nao/existe') == []


def test_build_catalog_from_aq(saida, aq_pequena):
    n = FIXTURAS['aq_pequena']['pecas']
    geo_dir = saida / 'geo' / 'x'
    catalog, n_geo, diag = build_catalog_from_aq(_config(aq_pequena), aq_pequena, str(geo_dir))
    assert n_geo == n and len(catalog['produtos']) == n
    assert diag == diag_vazio()
    ids = [p['id'] for p in catalog['produtos']]
    assert len(set(ids)) == n
    geos = {p['geo'] for p in catalog['produtos']}
    assert len(geos) == n and all((geo_dir / g).is_file() for g in geos)
    g = json.loads((geo_dir / catalog['produtos'][0]['geo']).read_text())
    assert set(g) == {'pos', 'col', 'idx'} and len(g['col']) == len(g['pos'])
    assert catalog['filtros'] == sorted(catalog['filtros']) and catalog['filtros']
    r = montar_resultado(_config(aq_pequena), catalog, n_geo, diag, {'n_pecas': n, 'schema': 607})
    assert set(r) == {'config', 'catalog', 'n_geometrias', 'diag', 'hints'} and r['hints']['n_pecas'] == n
    assert isinstance(r['diag']['sim_ilegivel'], list)


@pytest.fixture
def aq_corrompida(tmp_path, aq_pequena):
    """Cópia da fixture com cinco simbologias estragadas de propósito e uma peça
    desvinculada. Devolve (caminho, ids) para o teste conferir o diagnóstico."""
    copia = tmp_path / 'corrompida.aq'
    shutil.copy(aq_pequena, copia)
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
    pid_solto = con.execute('SELECT ID_PECA FROM PECA_SIMBOLOGIA_3D ORDER BY ID_PECA DESC LIMIT 1').fetchone()[0]
    con.execute('DELETE FROM PECA_SIMBOLOGIA_3D WHERE ID_PECA=?', (pid_solto,))
    con.commit()
    con.close()
    return str(copia), ids


def test_diag_separa_tubos_de_simbologia_descartada(saida, aq_corrompida, capsys):
    aq, ids = aq_corrompida
    n = FIXTURAS['aq_pequena']['pecas']
    _, por_peca = read_aq.extract_simbologias(aq)
    descartadas = {ids['nulo'], ids['nao_oq3d'], ids['truncado'], ids['versao9']}
    pecas_descartadas = sum(1 for sid in por_peca.values() if sid in descartadas)

    catalog, n_geo, diag = build_catalog_from_aq(_config(aq), aq, str(saida / 'geo' / 'x'))

    assert diag['pecas_sem_simbologia'] == 1
    assert diag['pecas_sim_descartada'] == pecas_descartadas
    assert diag['sim_sem_blob'] == 1 and diag['sim_nao_oq3d'] == 1
    assert [s for s, _, _ in diag['sim_ilegivel']] == [ids['truncado']]
    assert 'truncado' in diag['sim_ilegivel'][0][2]
    assert [s for s, _ in diag['sim_vazia']] == [ids['versao9']]
    assert {s for s, _, _ in diag['avisos']} == {ids['versao9'], ids['raizes']}
    # a simbologia com raízes divergentes TEM geometria e entra no catálogo
    assert n_geo == n - len(descartadas)
    assert len(catalog['produtos']) == n - 1 - pecas_descartadas

    assert resumo_diag(diag) is True
    out = capsys.readouterr().out
    assert '1 peça(s) sem simbologia 3D (tubos/kits)' in out
    assert '4 simbologia(s) descartada(s)' in out and '1 sem blob' in out
    assert f'sim {ids["truncado"]} ' in out and 'truncado' in out
    assert '2 simbologia(s) com aviso de parse' in out
    assert f'sim {ids["raizes"]} ' in out and 'declara 7 objetos-raiz' in out


def test_resumo_diag_limpo_nao_imprime(capsys):
    assert resumo_diag(diag_vazio()) is False
    assert capsys.readouterr().out == ''


def test_resumo_diag_so_tubos_nao_e_problema(capsys):
    d = diag_vazio()
    d['pecas_sem_simbologia'] = 312
    assert resumo_diag(d) is False
    assert '312 peça(s) sem simbologia 3D (tubos/kits) puladas — esperado' in capsys.readouterr().out
