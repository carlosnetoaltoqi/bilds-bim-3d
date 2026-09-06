"""Apagar em cada nível (2026-09-05, S7.15): empresa, catálogo, peça, importação.

`pacotes/dominio/src/remocao.ts` é a lógica compartilhada pela API (`DELETE /empresas/:customUrl`,
`/catalogos/:id`, `/produtos/:id`) e pelo serviço de ingestão (`DELETE /importacoes/:id`). O que
importa provar: apagar um produto não leva a geometria que outros produtos compartilham (o pipeline
grava uma por simbologia); a cópia copy-on-write e o `.orig.json` saem; catálogo e empresa levam o
storage dos imports; importação em andamento é recusada. Harness `tests/paridade/remocao.cts`
(ts-node de `www/apps/api`, modelos e store falsos). Marcador `paridade`.
"""
import json
import subprocess

import pytest

from conftest import ROOT, node_para_ts

pytestmark = pytest.mark.paridade
API = ROOT / 'www' / 'apps' / 'api'


@pytest.fixture(scope='module')
def c():
    node = node_para_ts()
    if not node:
        pytest.skip('precisa de Node >= 22')
    if not (API / 'node_modules' / 'ts-node').is_dir():
        pytest.skip('precisa de ts-node em www/apps/api/node_modules (pnpm install na raiz)')
    proc = subprocess.run([node, '--no-warnings', '--require', 'ts-node/register/transpile-only', '--require', 'reflect-metadata',
                           str(ROOT / 'tests' / 'paridade' / 'remocao.cts')], capture_output=True, text=True, cwd=API, timeout=120)
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(proc.stdout)


def test_produto_que_compartilha_geometria_deixa_a_geometria(c):
    r = c['produto_compartilhado']
    assert r['r']['produtos'] == 1 and r['r']['arquivos'] == []           # nada sai do storage: p2 ainda usa g
    assert r['produtos'] == ['p2', 'p3', 'p4']
    assert 'geo/imp1/g.json' in r['arquivos'] and 'thumbs/imp1/g.webp' in r['arquivos']
    assert r['catalogo']['productCount'] == 2 and sorted(r['catalogo']['filters']) == ['Joelhos', 'Luvas']


def test_produto_exclusivo_leva_geometria_orig_e_miniatura(c):
    r = c['produto_exclusivo']
    assert sorted(r['r']['arquivos']) == ['geo/imp1/h.json', 'geo/imp1/h.orig.json', 'thumbs/imp1/h.webp']
    assert not any(a.startswith('geo/imp1/h') or a == 'thumbs/imp1/h.webp' for a in r['arquivos'])
    assert r['catalogo']['productCount'] == 2 and r['catalogo']['filters'] == ['Joelhos']    # a série Luvas sumiu


def test_produto_copy_on_write_leva_so_a_copia(c):
    r = c['produto_cow']
    assert r['r']['arquivos'] == ['geo/imp1/p1.json']
    assert 'geo/imp1/g.json' in r['arquivos'] and 'geo/imp1/p1.json' not in r['arquivos']


def test_catalogo_leva_produtos_storage_dos_imports_e_os_imports(c):
    r = c['catalogo']
    assert r['r']['produtos'] == 3 and r['r']['catalogos'] == 1 and r['r']['imports'] == 1
    assert r['produtos'] == ['p4'] and r['catalogos'] == ['cat2'] and r['imports'] == ['imp2', 'imp3', 'imp4']
    assert r['arquivos'] == ['geo/imp2/peca.json', 'geo/imp3/lixo.json', 'logos/emp.png', 'thumbs/imp2/peca.webp']


def test_importacao_terminada_e_recontagem(c):
    r = c['importacao']
    assert r['r']['produtos'] == 1 and r['r']['imports'] == 1
    assert r['produtos'] == ['p1', 'p2', 'p3'] and r['imports'] == ['imp1', 'imp3', 'imp4']
    assert r['catalogo'] == {'_id': 'cat2', 'companyId': 'emp', 'slug': 'pecas-step', 'productCount': 0, 'filters': []}   # o catálogo fica, vazio
    assert not any(a.startswith('geo/imp2') or a.startswith('thumbs/imp2') for a in r['arquivos'])


def test_importacao_em_andamento_e_recusada(c):
    r = c['importacao_andamento']
    assert r['tipo'] == 'ImportacaoEmAndamento' and "em 'parseando'" in r['message']
    assert r['imports'] == ['imp1', 'imp2', 'imp3', 'imp4']


def test_empresa_leva_tudo(c):
    r = c['empresa']
    assert r['r']['catalogos'] == 2 and r['r']['produtos'] == 4 and r['r']['imports'] == 4
    assert r['companies'] == [] and r['catalogos'] == [] and r['produtos'] == [] and r['imports'] == []
    assert r['arquivos'] == []      # storage e logo limpos


def test_inexistentes_dao_nao_encontrado(c):
    assert c['inexistentes'] == ['NaoEncontrado'] * 4
