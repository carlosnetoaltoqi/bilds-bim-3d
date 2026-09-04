"""Paridade Python ↔ TypeScript.

O bilds.com (www/) importa .aq com `www/tools/aq-reader.ts` + `oq3d-parser.ts`,
ports do `scripts/read_aq.py` + `oq3d.py`. Os dois lados têm de ler a mesma
biblioteca e produzir os mesmos bytes/valores — senão o catálogo estático e o
dinâmico divergem sem ninguém notar. Até 2026-09-03 isso só era conferido pelo
`www/tools/test-port-s2-2.ts` (Dancor, manual).
"""
import hashlib
import json
import subprocess
import warnings

import pytest

import oq3d
import read_aq
from conftest import ROOT, node_para_ts
from oq3d_sintetico import (com_n_idx, com_raizes_declaradas, com_versao_malha,
                            duas_malhas, triangulo, truncado_nas_coords)

pytestmark = pytest.mark.paridade
HARNESS = ROOT / 'tests' / 'paridade' / 'dump_ts.mjs'


@pytest.fixture(scope='module')
def node():
    n = node_para_ts()
    if not n:
        pytest.skip('precisa de Node >= 22 para rodar os .ts de www/tools sem transpilar')
    return n


def _dump(node, *argv):
    proc = subprocess.run([node, '--no-warnings', str(HARNESS), *argv],
                          capture_output=True, text=True, cwd=ROOT, timeout=600)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout)


def _py_buffers_ou_erro(blob):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', oq3d.OQ3DAvisoParse)
        try:
            return oq3d.to_buffers(blob)
        except oq3d.OQ3DError as e:
            return {'error': 'OQ3DError', 'message': str(e)}


def _mesmos_buffers(py, ts, ctx=''):
    assert set(py) == set(ts) == {'pos', 'col', 'idx'}, ctx
    for k in ('pos', 'col', 'idx'):
        assert len(py[k]) == len(ts[k]), (ctx, k, len(py[k]), len(ts[k]))
        # `==` em float trata 0.0 e -0.0 como iguais (o JSON do Node grava -0 como 0)
        assert py[k] == ts[k], (ctx, k)


# ── oq3d: blobs sintéticos, inclusive os defeituosos ──────────────────────────

def test_oq3d_sintetico_mesmo_resultado_e_mesmos_erros(node, tmp_path):
    casos = {
        'ok': triangulo(),
        'duas': duas_malhas(),
        'v3': com_versao_malha(triangulo(), 3),
        'v9': com_versao_malha(triangulo(), 9),           # ambos: bloco pulado
        'nidx4': com_n_idx(triangulo(), 4),               # ambos: bloco pulado
        'raizes7': com_raizes_declaradas(triangulo(), 7),  # ambos: geometria normal
        'truncado': truncado_nas_coords(triangulo()),     # ambos: OQ3DError
    }
    arquivos = {}
    for nome, blob in casos.items():
        f = tmp_path / f'{nome}.bin'
        f.write_bytes(blob)
        arquivos[nome] = str(f)
    ts = _dump(node, 'blobs', *arquivos.values())
    for nome, blob in casos.items():
        py, t = _py_buffers_ou_erro(blob), ts[arquivos[nome]]
        if 'error' in py or 'error' in t:
            assert py.get('error') == t.get('error') == 'OQ3DError', (nome, py, t)
        else:
            _mesmos_buffers(py, t, nome)
    assert ts[arquivos['v9']]['pos'] == [] and ts[arquivos['nidx4']]['pos'] == []
    assert 'error' in ts[arquivos['truncado']]


# ── biblioteca real: read_aq ↔ aq-reader e oq3d ↔ oq3d-parser ─────────────────

def _texto(v):
    return v if v is not None else ''


def test_akato_read_aq_e_oq3d_identicos_ao_ts(node, akato_aq):
    ts = _dump(node, 'aq', akato_aq)
    py = read_aq.extract(akato_aq)

    assert [(g['ID_GRUPO_PECA'], g['NOME_GP']) for g in py['grupos']] == \
        [(g['ID_GRUPO_PECA'], g['NOME_GP']) for g in ts['grupos']]
    campos = ('ID_PECA', 'ID_GRUPO_PECA', 'DIAMETRO_PECA', 'COMPRIMENTO_PECA',
              'ALTURA_PECA', 'LARGURA_PECA')
    assert [tuple(p[c] for c in campos) + (_texto(p['NOME_PECA']), _texto(p['DESCRICAO_DADOS']))
            for p in py['pecas']] == \
        [tuple(p[c] for c in campos) + (p['NOME_PECA'], p['DESCRICAO_DADOS']) for p in ts['pecas']]
    assert [(p['ID_PECA'], p['propriedade'], _texto(p['VALOR'])) for p in py['propriedades']] == \
        [(p['ID_PECA'], p['propriedade'], p['VALOR']) for p in ts['propriedades']]
    assert len(py['curvas']) == len(ts['curvas']) == 0

    sims, por_peca = read_aq.extract_simbologias(akato_aq)
    ts_sims = {int(k): v for k, v in ts['simbologias']}
    assert set(sims) == set(ts_sims)
    for sid, s in sims.items():
        t = ts_sims[sid]
        assert (s['nome'], s['grupo'], s['classe']) == (t['nome'], t['grupo'], t['classe']), sid
        assert hashlib.sha1(s['blob']).hexdigest() == t['blobSha1'], sid
        assert (hashlib.sha1(s['imagem']).hexdigest() if s['imagem'] else None) == t['imagemSha1'], sid
    assert por_peca == {int(k): v for k, v in ts['porPeca']}

    for sid, s in sims.items():
        _mesmos_buffers(_py_buffers_ou_erro(s['blob']), ts['buffers'][str(sid)], f'sim {sid}')


def test_dancor_curvas_identicas_ao_ts(node, dancor_aq):
    """A Dancor é a única com curva Q-H; o mapeamento de colunas difere de nome
    entre os dois lados (vazao ↔ VAZAO_ICB), então se compara por valor."""
    ts = _dump(node, 'aq', dancor_aq, '--sem-geometria')
    py = read_aq.extract(dancor_aq)
    assert len(py['curvas']) == len(ts['curvas']) > 0
    for a, b in zip(py['curvas'], ts['curvas']):
        assert (a['ID_PECA'], a['potencia_cv'], a['vazao'], a['altura'], a['potencia_ponto'], a['rendimento']) == \
            (b['ID_PECA'], b['potencia_cv'], b['VAZAO_ICB'], b['ALTURA_ICB'], b['POTENCIA_ICB'], b['RENDIMENTO_ICB'])
    assert [g['NOME_GP'] for g in py['grupos']] == [g['NOME_GP'] for g in ts['grupos']]
