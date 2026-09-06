"""Fila e recuperação das importações da POC (I11).

Até 2026-09-05 dois uploads rodavam dois workers/Chromiums/Pythons ao mesmo tempo, e uma queda
da API deixava o `BimImport` em `recebido/parseando/gravando` para sempre (página em
"Convertendo…"), com JSONs e produtos meio-gravados e o upload do multer em `/tmp`. Agora
`importacoes/fila.ts` serializa as importações (concorrência `IMPORTACOES_CONCORRENCIA`, padrão 1)
e `importacoes/recuperacao.service.ts` marca `falhou` no boot o que ficou aberto e apaga os
uploads temporários. Desde a E3 (S7.14) os dois moram no serviço de ingestão,
`www/apps/ingestao`. Harnesses: `tests/paridade/fila.mts` (puro, strip-types) e
`tests/paridade/recuperacao.cts` (ts-node de `www/apps/ingestao`). Marcador `paridade`.
"""
import json
import subprocess

import pytest

from conftest import ROOT, node_para_ts

pytestmark = pytest.mark.paridade
INGESTAO = ROOT / 'www' / 'apps' / 'ingestao'


@pytest.fixture(scope='module')
def node():
    n = node_para_ts()
    if not n:
        pytest.skip('precisa de Node >= 22')
    return n


@pytest.fixture(scope='module')
def fila(node):
    proc = subprocess.run([node, '--no-warnings', '--experimental-strip-types', str(ROOT / 'tests' / 'paridade' / 'fila.mts')],
                          capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(proc.stdout)


@pytest.fixture(scope='module')
def recuperacao(node):
    if not (INGESTAO / 'node_modules' / 'ts-node').is_dir():
        pytest.skip('precisa de ts-node em www/apps/ingestao/node_modules (pnpm install na raiz)')
    proc = subprocess.run(
        [node, '--no-warnings', '--require', 'ts-node/register/transpile-only', '--require', 'reflect-metadata',
         str(ROOT / 'tests' / 'paridade' / 'recuperacao.cts')],
        capture_output=True, text=True, cwd=INGESTAO, timeout=300)
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(proc.stdout)


# ── fila ─────────────────────────────────────────────────────────────────────

def test_fila_roda_um_por_vez_em_ordem_e_informa_a_posicao(fila):
    r = fila['fifo_um_por_vez']
    # fn roda num microtask, então quando `a` começa `b` e `c` já esperam
    assert r['eventos'] == ['a:inicio(ativos=1,espera=2)', 'a:fim',
                            'b:inicio(ativos=1,espera=1)', 'b:fim',
                            'c:inicio(ativos=1,espera=0)', 'c:fim']
    assert r['posicoes'] == {'a': 0, 'b': 1, 'c': 2}     # 0 = rodou já; N = quantos à frente
    assert r['esperandoLogo'] == ['b', 'c']
    assert r['resultados'] == ['A', 'B', 'C']
    assert r['depois'] == {'ativos': 0, 'espera': 0}


def test_fila_repassa_a_rejeicao_e_segue(fila):
    r = fila['rejeicao_nao_trava']
    assert r['erro'] == 'worker morreu' and r['ok'] == 1
    assert r['ordem'] == ['erro', 'ok'] and r['depois'] == {'ativos': 0, 'espera': 0}


def test_fila_concorrencia_2(fila):
    assert fila['concorrencia_2'] == {'pico': 2, 'posicoes': [0, 0, 2, 3]}


def test_concorrencia_do_env(fila):
    e = fila['env']
    assert e['ausente'] == 1 and e['vazio'] == 1 and e['tres'] == 3
    for k in ('zero', 'texto', 'nove'):
        assert e[k].startswith('erro: IMPORTACOES_CONCORRENCIA inválida'), (k, e[k])
    assert 'inválida: 0' in fila['construtor_invalido']


# ── recuperação no boot ──────────────────────────────────────────────────────

def test_boot_marca_falhou_todo_import_nao_terminal(recuperacao):
    r = recuperacao['boot_marca_nao_terminais']
    assert r['marcados'] == ['i-recebido', 'i-parseando', 'i-gravando']
    assert r['statusFinal'] == {'i-recebido': 'falhou', 'i-parseando': 'falhou', 'i-gravando': 'falhou',
                                'i-publicado': 'publicado', 'i-falhou': 'falhou', 'i-vazio': 'vazio'}
    assert set(r['erro']) == {'a API foi reiniciada durante a importação — envie o arquivo de novo'}
    assert r['notes'] == ["estava em 'recebido' quando a API reiniciou", "estava em 'parseando' quando a API reiniciou",
                          "estava em 'gravando' quando a API reiniciou"]
    # limpeza igual à de uma falha normal: produtos e geo/<importId>/
    assert r['produtosApagados'] == [{'importId': i} for i in r['marcados']]
    assert r['prefixos'] == [f'geo/{i}' for i in r['marcados']]


def test_sweep_com_idade_minima_so_pega_os_antigos(recuperacao):
    r = recuperacao['sweep_respeita_idade']
    assert r['marcados'] == ['velho'] and r['statusFinal'] == {'novo': 'parseando', 'velho': 'falhou'}


def test_limpeza_que_falha_nao_impede_marcar(recuperacao):
    r = recuperacao['limpeza_falha_nao_impede']
    assert r['marcados'] == ['x'] and r['status'] == 'falhou' and r['avisos'] == 2


def test_uploads_temporarios_so_os_nossos(recuperacao):
    r = recuperacao['uploads_temporarios']
    assert r['removidos'] == sorted(['bim-0f8fad5b-d9cb-469f-a165-70867728950e.aq',
                                     'cad-0f8fad5b-d9cb-469f-a165-70867728950e.stp',
                                     'cad-0f8fad5b-d9cb-469f-a165-70867728950e.IFC'])
    assert r['restantes'] == sorted(['bim-qualquer.aq', 'cad-0f8fad5b-d9cb-469f-a165-70867728950e.txt', 'outro.aq', 'notas.txt'])
    assert recuperacao['uploads_dir_inexistente'] == []


def test_servico_nest_chama_a_recuperacao_no_on_module_init(recuperacao):
    r = recuperacao['servico_on_module_init']
    assert r['marcados'] == ['y'] and r['uploadsRemovidosEhArray'] is True
