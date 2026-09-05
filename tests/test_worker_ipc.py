"""worker-ipc (I15): a POC não pode engolir a morte de um processo filho.

Até 2026-09-05 o `ImportacoesService` ignorava o `type:'error'` do thumb-worker, deixava
a promise presa quando o filho saía com código 0 sem mandar mensagem, e os chamadores
faziam `.catch(() => {})`. `www/apps/api/src/importacoes/worker-ipc.ts` concentra a
espera pelos dois workers; este teste roda `tests/paridade/worker_ipc.mts` no Node, que
simula cada forma de o filho morrer e também dispara o thumb-worker real com um geoKey
que não existe. Marcador `paridade` (precisa de Node >= 22); pula sem ele.
"""
import json
import subprocess

import pytest

from conftest import ROOT, node_para_ts

pytestmark = pytest.mark.paridade
HARNESS = ROOT / 'tests' / 'paridade' / 'worker_ipc.mts'


@pytest.fixture(scope='module')
def cenarios():
    node = node_para_ts()
    if not node:
        pytest.skip('precisa de Node >= 22 para rodar o worker-ipc.ts sem transpilar')
    proc = subprocess.run([node, '--no-warnings', '--experimental-strip-types', str(HARNESS)],
                          capture_output=True, text=True, cwd=ROOT, timeout=300)
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(proc.stdout)


# ── parse-worker ─────────────────────────────────────────────────────────────

def test_parse_worker_resolve_com_a_mensagem_e_ignora_o_exit_depois(cenarios):
    r = cenarios['parse_ok']
    assert r['ok'] == {'status': 'ok', 'productCount': 3}
    assert r['mortos'] == []
    # mensagem, depois exit 1 e error: nada disso vira rejeição — já resolveu
    assert cenarios['parse_settle_uma_vez']['ok'] == {'status': 'vazio'}


def test_parse_worker_exit_0_sem_mensagem_e_erro_imediato(cenarios):
    # antes: promise presa até o timeout de 5 min
    erro = cenarios['parse_exit0_sem_mensagem']['erro']
    assert 'código 0' in erro and 'sem enviar resultado' in erro


def test_parse_worker_exit_1_sinal_e_erro_de_processo_rejeitam_com_o_motivo(cenarios):
    assert 'código 1' in cenarios['parse_exit1']['erro']
    assert 'pelo sinal SIGKILL' in cenarios['parse_sinal']['erro']
    assert 'spawn ENOENT' in cenarios['parse_erro_processo']['erro']


def test_parse_worker_timeout_mata_com_sigkill(cenarios):
    r = cenarios['parse_timeout']
    assert 'não respondeu' in r['erro'] and r['mortos'] == ['SIGKILL']


# ── thumb-worker ─────────────────────────────────────────────────────────────

def test_thumb_worker_conta_cada_falha_e_chama_os_ganchos(cenarios):
    r = cenarios['thumb_ok_com_falhas']
    assert r['ok'] == {'total': 3, 'geradas': 2,
                       'falhas': [{'productId': 'b', 'message': 'ENOENT: geo/b.json'}]}
    assert r['ganchos'] == {'miniaturas': ['a=thumbs/i/a.webp', 'c=thumbs/i/c.webp'],
                            'falhas': ['b: ENOENT: geo/b.json']}
    assert r['descricao'] == 'miniaturas: 2/3 geradas, 1 falha(s) — b: ENOENT: geo/b.json'
    assert r['mortos'] == []


def test_thumb_worker_gancho_que_rejeita_vira_falha_do_produto(cenarios):
    # a imagem existe mas o produto não aponta para ela — não pode contar como gerada
    r = cenarios['thumb_gancho_rejeita']['ok']
    assert r['geradas'] == 0
    assert r['falhas'] == [{'productId': 'a', 'message': 'gravar thumbKey: Mongo fora'}]


def test_thumb_worker_done_espera_os_ganchos_pendentes(cenarios):
    r = cenarios['thumb_done_espera_ganchos']
    assert r['ok']['geradas'] == 1 and r['ganchoTerminou'] is True


def test_thumb_worker_exit_antes_do_done_rejeita_com_resumo_parcial(cenarios):
    r = cenarios['thumb_exit0_sem_done']
    assert "antes do 'done'" in r['erro'] and 'código 0' in r['erro']
    assert r['resumo'] == {'total': 2, 'geradas': 1, 'falhas': []}
    assert 'pelo sinal SIGKILL' in cenarios['thumb_sinal']['erro']
    assert 'spawn EACCES' in cenarios['thumb_erro_processo']['erro']


def test_thumb_worker_ocioso_e_morto_e_rejeita(cenarios):
    r = cenarios['thumb_ocioso']
    assert 'sem mensagens' in r['erro'] and r['mortos'] == ['SIGKILL']
    assert r['resumo']['geradas'] == 1


def test_descreve_resumo(cenarios):
    assert cenarios['descreve_sem_falhas'] == 'miniaturas: 4/4 geradas'
    assert cenarios['descreve_com_falhas'] == 'miniaturas: 2/4 geradas, 2 falha(s) — x: ENOENT (+1)'


def test_thumb_worker_real_reporta_geo_inexistente_e_termina(cenarios):
    r = cenarios['real_thumb_worker_geo_inexistente']
    if 'skip' in r:
        pytest.skip(r['skip'])
    assert 'erro' not in r, r
    assert r['ok']['geradas'] == 0 and r['ok']['total'] == 1
    (falha,) = r['ok']['falhas']
    assert falha['productId'] == 'inexistente' and 'ENOENT' in falha['message']
    assert r['ganchoFalhas'] and r['ganchoFalhas'][0].startswith('inexistente: ')
    assert r['exitCode'] == 0, r['stderr']
