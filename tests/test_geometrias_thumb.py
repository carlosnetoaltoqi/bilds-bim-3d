"""Miniatura regerada depois de editar a geometria (I14).

Até 2026-09-05 o `PUT /geometrias/:id` gravava a geometria nova e o `thumbKey` seguia
apontando para a imagem do import — o catálogo mostrava a peça antiga. Agora o PUT e o
restaurar disparam `ImportacoesService.regerarMiniatura`, que reaproveita o thumb-worker e
registra `thumbAtualizadaEm` ou `thumbErro` no produto. O harness
`tests/paridade/geometrias_thumb.cts` instancia controller e service sem Nest nem Mongo (ts-node
de `www/apps/api`) e, no último cenário, dispara o thumb-worker real com um geoKey inexistente.
Marcador `paridade`; pula sem Node ou sem `ts-node` em `www/apps/api/node_modules`.
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


def test_put_e_restaurar_disparam_a_regeneracao_da_miniatura(cenarios):
    r = cenarios['put_e_restaurar']
    assert r['putMiniatura'] == 'regerando' and r['restaurarMiniatura'] == 'regerando'
    # uma chamada por operação, com o produto, o import (prefixo da chave) e a geometria viva
    assert r['chamadas'] == [['p1', 'imp1', 'geo/imp1/p1.json'], ['p1', 'imp1', 'geo/imp1/p1.json']]
    assert r['backupFeito'] is True and r['origRemovido'] is True


def test_regerar_miniatura_registra_a_falha_no_produto(cenarios):
    r = cenarios['regerar_real_geo_inexistente']
    if 'skip' in r:
        pytest.skip(r['skip'])
    assert r['resumo']['geradas'] == 0 and len(r['resumo']['falhas']) == 1
    assert 'ENOENT' in r['resumo']['falhas'][0]['message']
    (update,) = [u for u in r['updates'] if 'thumbErro' in u[1]]
    assert update[0] == 'p1' and 'ENOENT' in update[1]['thumbErro']
    assert 'thumbAtualizadaEm' not in update[1]
    # nada é escrito no documento do import — a regeneração é do produto
    assert r['importUpdates'] == []
