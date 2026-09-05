"""Editar geometria na API: copy-on-write e miniatura pedida ao serviço (I14, A5, A6).

Até 2026-09-05 o `PUT /geometrias/:id` gravava a geometria nova e o `thumbKey` seguia
apontando para a imagem do import — o catálogo mostrava a peça antiga. Desde a E3 a API não
tem Chromium: PUT e restaurar pedem a miniatura ao serviço de ingestão (`IngestaoClient`) e,
se ele não responder, gravam `thumbErro` no produto. E como o pipeline grava UMA geometria
por simbologia (Amanco: 856 produtos em 448 geometrias), editar um produto que compartilha
geometria faz copy-on-write: arquivo próprio em `geoKey`, chave compartilhada em
`geoKeyCompartilhada`; restaurar desfaz. O harness `tests/paridade/geometrias_thumb.cts`
instancia os controllers sem Nest nem Mongo (ts-node de `www/apps/api`). Marcador `paridade`.
"""
import json
import subprocess

import pytest

from conftest import ROOT, node_para_ts

pytestmark = pytest.mark.paridade
API = ROOT / 'www' / 'apps' / 'api'
HARNESS = ROOT / 'tests' / 'paridade' / 'geometrias_thumb.cts'


@pytest.fixture(scope='module')
def cenarios():
    node = node_para_ts()
    if not node:
        pytest.skip('precisa de Node >= 22')
    if not (API / 'node_modules' / 'ts-node').is_dir():
        pytest.skip('precisa de ts-node em www/apps/api/node_modules (pnpm install em www/)')
    proc = subprocess.run(
        [node, '--no-warnings', '--require', 'ts-node/register/transpile-only', '--require', 'reflect-metadata',
         str(HARNESS)],
        capture_output=True, text=True, cwd=API, timeout=300)
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(proc.stdout)


def test_geometria_exclusiva_faz_backup_e_pede_miniatura_no_put_e_no_restaurar(cenarios):
    r = cenarios['exclusiva']
    assert r['putMiniatura'] == 'regerando' and r['restaurarMiniatura'] == 'regerando'
    assert r['putGeoKey'] == 'geo/imp1/p1.json' and r['backupFeito'] is True and r['copiaFeita'] is False
    assert r['temOrigDepoisDoPut'] is True and r['restaurado'] is True
    assert r['origRemovido'] is True and r['vivoVoltouAoOriginal'] is True
    assert r['chamadas'] == ['p1', 'p1']     # uma por operação, com o produto


def test_geometria_compartilhada_faz_copy_on_write_e_restaurar_desfaz(cenarios):
    r = cenarios['compartilhada']
    assert r['put'] == {'geoKey': 'geo/imp1/p1.json', 'copiaFeita': True, 'backupFeito': False,
                        'geoKeyCompartilhada': 'geo/imp1/g.json', 'miniatura': 'regerando'}
    d = r['depoisDoPut']
    assert d['p1'] == {'geoKey': 'geo/imp1/p1.json', 'compartilhada': 'geo/imp1/g.json'}
    assert d['p2'] == {'geoKey': 'geo/imp1/g.json', 'compartilhada': None}       # o outro produto não muda
    assert d['arquivos'] == ['geo/imp1/g.json', 'geo/imp1/p1.json']
    assert d['compartilhadoIntacto'] is True and d['proprioNovo'] is True
    # segunda edição do mesmo produto: já é dele — nada de copiar de novo nem .orig.json
    assert r['put2'] == {'geoKey': 'geo/imp1/p1.json', 'copiaFeita': False, 'backupFeito': False}
    assert r['semOrigJson'] is True
    assert r['restaurar'] == {'restaurado': True, 'geoKey': 'geo/imp1/g.json', 'miniatura': 'regerando'}
    assert r['depoisDoRestaurar']['p1'] == {'geoKey': 'geo/imp1/g.json', 'compartilhada': None, 'geoEditadoEm': None}
    assert r['depoisDoRestaurar']['arquivos'] == ['geo/imp1/g.json']
    assert r['chamadas'] == ['p1', 'p1', 'p1']


def test_servico_de_ingestao_fora_registra_thumb_erro_e_nao_perde_a_geometria(cenarios):
    r = cenarios['ingestao_fora']
    assert r['miniatura'] == 'nao-solicitada' and 'indisponível' in r['miniaturaErro']
    assert r['geometriaGravada'] is True
    assert 'indisponível' in r['thumbErroNoProduto']
    assert r['chamadas'] == ['p1']


def test_get_produto_expoe_o_resultado_da_regeneracao(cenarios):
    r = cenarios['get_produto_expoe_miniatura']
    assert r['ok'] == {'thumbAtualizadaEm': '2026-09-05T17:09:44.859Z', 'thumbErro': None, 'thumbUrl': '/thumbs/ok'}
    assert r['falhou'] == {'thumbAtualizadaEm': None, 'thumbErro': 'EACCES: permission denied', 'thumbUrl': None}
