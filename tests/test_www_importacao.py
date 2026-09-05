"""Fila e recuperação das importações da POC (I11).

Até 2026-09-05 dois uploads rodavam dois workers/Chromiums/Pythons ao mesmo tempo, e uma queda
da API deixava o `BimImport` em `recebido/parseando/gravando` para sempre (página em
"Convertendo…"), com JSONs e produtos meio-gravados e o upload do multer em `/tmp`. Agora
`common/fila.ts` serializa as importações (concorrência `IMPORTACOES_CONCORRENCIA`, padrão 1)
e `importacoes/recuperacao.service.ts` marca `falhou` no boot o que ficou aberto e apaga os
uploads temporários. Harnesses: `tests/paridade/fila.mts` (puro, strip-types) e
`tests/paridade/recuperacao.cts` (ts-node de `www/apps/api`). Marcador `paridade`.

S7.13 (teste de aceitação com a API de pé) acrescentou `tests/paridade/importacoes_processo.cts`:
a nota "na fila — N à frente" é apagada quando o processamento começa (ficava no import publicado)
e a vaga da fila só libera depois das miniaturas (o Chromium do import anterior rodava junto com o
parse do seguinte) — para `.aq` e para CAD.
"""
import json
import subprocess

import pytest

from conftest import ROOT, node_para_ts

pytestmark = pytest.mark.paridade
API = ROOT / 'www' / 'apps' / 'api'


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
    if not (API / 'node_modules' / 'ts-node').is_dir():
        pytest.skip('precisa de ts-node em www/apps/api/node_modules (pnpm install em www/)')
    proc = subprocess.run(
        [node, '--no-warnings', '--require', 'ts-node/register/transpile-only', '--require', 'reflect-metadata',
         str(ROOT / 'tests' / 'paridade' / 'recuperacao.cts')],
        capture_output=True, text=True, cwd=API, timeout=300)
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(proc.stdout)


@pytest.fixture(scope='module')
def processo(node):
    if not (API / 'node_modules' / 'ts-node').is_dir():
        pytest.skip('precisa de ts-node em www/apps/api/node_modules (pnpm install em www/)')
    proc = subprocess.run(
        [node, '--no-warnings', '--require', 'ts-node/register/transpile-only', '--require', 'reflect-metadata',
         str(ROOT / 'tests' / 'paridade' / 'importacoes_processo.cts')],
        capture_output=True, text=True, cwd=API, timeout=300)
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


# ── processamento dentro da vaga da fila (S7.13) ─────────────────────────────

def _ordem(eventos, *nomes):
    """Índice de cada evento (o primeiro que começa com o nome), para comparar a ordem."""
    return [next(i for i, e in enumerate(eventos) if e.startswith(n)) for n in nomes]


def test_nota_da_fila_e_apagada_quando_o_processamento_comeca(processo):
    (import_id, primeiro), *_ = processo['aq']['updates']
    assert import_id == 'imp1' and primeiro['status'] == 'parseando'
    assert 'note' in primeiro and primeiro['note'] is None, primeiro
    # o CAD já sobrescrevia com "convertendo…" — continua assim
    (_, primeiro_cad), *_ = processo['cad']['updates']
    assert primeiro_cad['status'] == 'parseando' and primeiro_cad['note'] == 'convertendo…'


def test_vaga_da_fila_so_libera_depois_das_miniaturas_do_aq(processo):
    r = processo['aq']
    ev = r['eventos']
    publicado, t_ini, t_fim, fim, segundo = _ordem(ev, 'update:publicado', 'thumbs:inicio', 'thumbs:fim', 'processo:fim', 'segundo:inicio')
    # o segundo só começa depois que as miniaturas do primeiro acabaram (a fila libera a vaga
    # antes de resolver a promise externa — por isso `segundo` pode vir antes de `processo:fim`)
    assert publicado < t_ini < t_fim < segundo and t_fim < fim, ev
    assert r['posicaoSegundo'] == 1 and r['aqRemovido'] is True
    # o resultado das miniaturas foi registrado no import (I15) — depois de publicado
    assert any(u.get('thumbCount') == 1 for _, u in r['updates'])


def test_vaga_da_fila_so_libera_depois_da_miniatura_do_cad(processo):
    r = processo['cad']
    ev = r['eventos']
    publicado, t_ini, t_fim, fim, segundo = _ordem(ev, 'update:publicado', 'thumbs:inicio', 'thumbs:fim', 'processo:fim', 'segundo:inicio')
    assert publicado < t_ini < t_fim < segundo and t_fim < fim, ev
    assert 'thumbs:inicio(imp2,1)' in ev
    assert r['posicaoSegundo'] == 1 and r['stpRemovido'] is True
