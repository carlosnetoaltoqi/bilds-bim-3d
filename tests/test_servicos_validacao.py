"""Validação de entrada da API da POC (I16).

Até 2026-09-05 não havia `ValidationPipe`: cada controller checava o corpo à mão, `curva` e
`partes` não tinham limite e `specs` transformava um objeto em `"[object Object]"`. Agora
`servicos/catalogo-api/src/common/validation.ts` define o pipe global e cada corpo tem um DTO. O harness
`tests/paridade/validacao.cts` passa corpos pelo MESMO pipe do `main.ts` e devolve o valor
transformado ou as mensagens de 400. Marcador `paridade`; pula sem Node ou sem `ts-node`.
"""
import json
import subprocess

import pytest

from conftest import ROOT, node_para_ts

pytestmark = pytest.mark.paridade
API = ROOT / 'servicos' / 'catalogo-api'
HARNESS = ROOT / 'tests' / 'paridade' / 'validacao.cts'


@pytest.fixture(scope='module')
def c():
    node = node_para_ts()
    if not node:
        pytest.skip('precisa de Node >= 22')
    if not (API / 'node_modules' / 'ts-node').is_dir():
        pytest.skip('precisa de ts-node em servicos/catalogo-api/node_modules (pnpm install na raiz)')
    proc = subprocess.run(
        [node, '--no-warnings', '--require', 'ts-node/register/transpile-only', '--require', 'reflect-metadata',
         str(HARNESS)],
        capture_output=True, text=True, cwd=API, timeout=300)
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(proc.stdout)


def _erros(r):
    assert 'erros' in r and r['status'] == 400, r
    return ' | '.join(r['erros'])


# ── PATCH /produtos/:id ──────────────────────────────────────────────────────

def test_produto_corpo_valido_e_normalizado(c):
    assert c['produto_ok'] == {
        'nome': 'Bomba 20cv', 'serie': 'Linha A',
        'specs': {'Tensão': '220V', 'Peso': '12.5', 'Trifásica': 'true'},   # número/booleano → texto; null fora
        'curva': [[1, 20, 5, 0], [2, 10, 0, 0]],                             # ordenada por vazão, completada com 0
        'potencia': 3, 'conexoes': None,
    }


def test_produto_specs_rejeita_objeto_e_array_como_valor(c):
    # era o "[object Object]" da auditoria
    assert 'recebeu object' in _erros(c['produto_specs_objeto'])
    assert 'recebeu array' in _erros(c['produto_specs_array'])
    assert 'limite é 200' in _erros(c['produto_specs_muitas'])


def test_produto_texto_vazio_ou_longo(c):
    assert '"nome" não pode ser vazio' in _erros(c['produto_nome_vazio'])
    assert 'passa de 200' in _erros(c['produto_nome_longo'])


def test_produto_curva_com_limite_e_pontos_numericos(c):
    assert 'limite é 1000' in _erros(c['produto_curva_grande'])
    assert '[1] deve ser [vazao, altura' in _erros(c['produto_curva_ponto_ruim'])
    assert '[0] deve ser' in _erros(c['produto_curva_nan'])
    assert c['produto_curva_null'] == {'ok': {'curva': None}}


def test_produto_potencia_numero_ou_null(c):
    assert 'número ou null' in _erros(c['produto_potencia_texto'])
    assert c['produto_potencia_null'] == {'ok': {'potencia': None}}


def test_produto_campo_fora_do_dto_e_400_nao_descartado(c):
    assert 'geoKey should not exist' in _erros(c['produto_campo_desconhecido'])
    assert c['produto_vazio'] == {'ok': {}}   # o controller responde "nenhum campo editável"


# ── PATCH /catalogos/:id ─────────────────────────────────────────────────────

def test_catalogo(c):
    assert c['catalogo_ok'] == {'ok': {'title': 'Bombas', 'manufacturer': 'Dancor', 'layout': 'series-rows'}}
    assert '"series-rows" ou "catalog-grid"' in _erros(c['catalogo_layout_invalido'])
    assert '"title" não pode ser vazio' in _erros(c['catalogo_title_vazio'])


# ── POST /exportar/aq ────────────────────────────────────────────────────────

def test_exportar_aq_partes_e_info(c):
    ok = c['exportar_ok']['ok']
    assert ok['info'] == {'fabricante': 'Dancor', 'nome': '20cv', 'specs': {'Peso': 12}, 'origem': 'poc'}
    assert [p['nome'] for p in ok['partes']] == ['corpo', 'bocal']
    assert ok['partes'][0]['col'] is None and len(ok['partes'][1]['col']) == 9
    assert c['exportar_so_geo']['ok'] == {'pos': [0, 0, 0, 1, 0, 0, 0, 1, 0], 'col': [], 'idx': [0, 1, 2]}


def test_exportar_aq_limites_e_forma(c):
    assert 'passa de 500 itens' in _erros(c['exportar_partes_excesso'])
    assert 'nome" não pode ser vazio' in _erros(c['exportar_parte_sem_nome'])
    assert 'pos" deve ser array' in _erros(c['exportar_parte_pos_nao_array'])
    assert 'matriz should not exist' in _erros(c['exportar_parte_campo_extra'])
    assert 'recebeu object' in _erros(c['exportar_info_specs_objeto'])


# ── POST /cad/importar (multipart) ───────────────────────────────────────────

def test_cad_deflexao_vira_numero_entre_0_e_10(c):
    assert c['cad_ok'] == {'ok': {'deflexao': 0.5, 'nome': 'peça', 'fabricante': 'X'}}
    assert c['cad_sem_deflexao'] == {'ok': {'nome': 'p'}}          # o controller aplica 0,2 mm
    assert 'maior que 0' in _erros(c['cad_deflexao_zero'])
    assert 'no máximo 10' in _erros(c['cad_deflexao_grande'])
    assert 'deve ser um número' in _erros(c['cad_deflexao_texto'])


# ── POST /empresas, POST /importacoes ────────────────────────────────────────

def test_empresa_e_importar_aq(c):
    assert c['empresa_ok'] == {'ok': {'name': 'POC', 'customUrl': 'Minha Empresa'}}   # o controller vira slug
    assert 'campo "name" obrigatório' in _erros(c['empresa_sem_nome'])
    assert 'campo "customUrl" obrigatório' in _erros(c['empresa_sem_url'])
    # sem auth (S7.14): o import recebe a empresa por `customUrl`; campo fora do DTO é 400
    assert c['importar_aq_ok'] == {'ok': {'empresa': 'poc'}}
    assert c['importar_aq_vazio'] == {'ok': {}}
    assert c['importar_aq_campo_estranho']['status'] == 400


# ── POST /importacoes/plugin-autocad (multipart) — S7.17 ─────────────────────

def test_importar_plugin_lead_categoria_e_limites(c):
    ok = c['plugin_ok']['ok']
    assert ok['empresa'] == 'poc' and ok['categoria'] == 'tupygrooved-173' and ok['host'] == 'https://conexoes.tupy.com.br'
    assert ok['igsPorGrupo'] == 3 and ok['deflexao'] == 0.5          # texto do multipart → número
    assert ok['fullName'] == 'Carlos' and ok['email'] == 'c@x.com'  # trim
    assert set(c['plugin_minimo']['ok']) == {'categoria', 'fullName', 'email', 'mobile', 'company', 'position'}
    e = _erros(c['plugin_sem_lead'])
    for campo in ('fullName', 'email', 'mobile', 'company', 'position'):
        assert campo in e
    assert '"email" inválido' in _erros(c['plugin_email_invalido'])
    assert 'URL https' in _erros(c['plugin_host_http'])
    assert 'slug' in _erros(c['plugin_categoria_invalida'])
    assert '"categoria" é obrigatória' in _erros(c['plugin_sem_categoria'])
    assert '-1 (todos)' in _erros(c['plugin_igs_fora'])
    assert 'deve ser inteiro' in _erros(c['plugin_igs_fracao'])
    assert c['plugin_campo_estranho']['status'] == 400
