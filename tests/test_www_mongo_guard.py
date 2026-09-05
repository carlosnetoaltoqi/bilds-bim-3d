"""I32: com o Mongo fora, toda rota responde 503 na hora — não 500 depois de 30 s.

Até 2026-09-05 só `GET /health` sabia dizer que a conexão do Mongoose não estava pronta; as
demais rotas esperavam o `serverSelectionTimeoutMS` do driver. `MongoProntoGuard`
(`www/packages/dominio/src/mongo-pronto.guard.ts`) é `APP_GUARD` na API e no serviço de
ingestão: `readyState ≠ 1` → `ServiceUnavailableException` antes de chegar ao controller,
exceto nas rotas de `ROTAS_SEM_MONGO`. Harness `tests/paridade/mongo_guard.cts` (ts-node de
`www/apps/api`); os dois últimos testes leem os `app.module.ts` para garantir o registro.
"""
import json
import subprocess

import pytest

from conftest import ROOT, node_para_ts

API = ROOT / 'www' / 'apps' / 'api'
INGESTAO = ROOT / 'www' / 'apps' / 'ingestao'


@pytest.fixture(scope='module')
def casos():
    node = node_para_ts()
    if not node:
        pytest.skip('precisa de Node >= 22')
    if not (API / 'node_modules' / 'ts-node').is_dir():
        pytest.skip('precisa de ts-node em www/apps/api/node_modules (pnpm install em www/)')
    proc = subprocess.run(
        [node, '--no-warnings', '--require', 'ts-node/register/transpile-only', '--require', 'reflect-metadata',
         str(ROOT / 'tests' / 'paridade' / 'mongo_guard.cts')],
        capture_output=True, text=True, cwd=API, timeout=120)
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(proc.stdout)


@pytest.mark.paridade
def test_conectado_passa_desconectado_da_503_na_hora(casos):
    assert casos['conectado_catalogos'] == {'ok': True}
    for k in ('desconectado_catalogos', 'conectando_importacoes', 'desconectando_put'):
        assert casos[k]['status'] == 503, (k, casos[k])
        assert casos[k]['message'].startswith('Mongo ') and '/health' in casos[k]['message'], casos[k]
    assert 'desconectado' in casos['desconectado_catalogos']['message']
    assert 'conectando' in casos['conectando_importacoes']['message']


@pytest.mark.paridade
def test_health_passa_mesmo_desconectado(casos):
    assert casos['rotasSemMongo'] == ['/health']
    assert casos['desconectado_health'] == {'ok': True}
    assert casos['desconectado_health_query'] == {'ok': True}
    assert casos['motivo_puro_ok'] is None and casos['motivo_puro'].startswith('Mongo desconectado')


def test_guard_registrado_como_app_guard_nos_dois_apps():
    for app in (API, INGESTAO):
        src = (app / 'src' / 'app.module.ts').read_text(encoding='utf8')
        assert 'MongoProntoGuard' in src and 'APP_GUARD' in src and 'useClass: MongoProntoGuard' in src, app
