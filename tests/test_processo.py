"""Processos filhos do serviço de ingestão não morrem em silêncio (I15/I29, refeito na E3).

O serviço roda o pipeline Python e o `thumbs.mjs` com `executar()` de
`apps/ingestao/src/pipeline/processo.ts`: saída ≠ 0, sinal, timeout total, ociosidade e
comando inexistente viram `ProcessoError` com o motivo e as últimas linhas do stderr; as
linhas de saída chegam ao chamador na hora (progresso, uma miniatura por linha). E o filho
recebe o stdin em pipe: se o serviço morrer, o pipe fecha e o filho para sozinho —
`processo.py:vigiar_stdin()` no Python, `sairComStdin` no thumbs.mjs. Harness Node em
`tests/paridade/processo.mts` (só builtins, strip-types); o lado Python roda o módulo real.
"""
import json
import os
import subprocess
import time

import pytest

from conftest import ROOT, PIPELINE, node_para_ts

HARNESS = ROOT / 'tests' / 'paridade' / 'processo.mts'


@pytest.fixture(scope='module')
def casos():
    node = node_para_ts()
    if not node:
        pytest.skip('precisa de Node >= 22 para rodar o processo.ts sem transpilar')
    proc = subprocess.run([node, '--no-warnings', '--experimental-strip-types', str(HARNESS)],
                          capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(proc.stdout)


@pytest.mark.paridade
def test_sucesso_entrega_linhas_na_hora_e_o_stdout_inteiro(casos):
    r = casos['ok']
    assert r['ok']['code'] == 0 and r['ok']['stdout'] == 'a\nb\nsem-newline\n' and r['ok']['stderr'] == 'e1'
    assert r['linhas'] == ['a', 'b', 'sem-newline']     # o resto sem \n também chega, no fim


@pytest.mark.paridade
def test_saida_diferente_de_zero_vira_erro_com_o_stderr(casos):
    e = casos['saida3']['erro']
    assert e['motivo'] == 'saida' and e['code'] == 3 and e['signal'] is None
    assert e['message'].startswith('teste.py saiu com código 3') and 'motivo real' in e['message']
    assert e['stderr'] == 'x\nmotivo real'
    assert casos['aceita3']['ok']['code'] == 3      # aceito explicitamente (thumbs.mjs sai com 2 quando uma geometria falha)


@pytest.mark.paridade
def test_sinal_timeout_ocioso_e_spawn_tem_motivo_proprio(casos):
    assert casos['sinal']['erro']['motivo'] == 'sinal' and casos['sinal']['erro']['signal'] == 'SIGTERM'
    t = casos['timeout']
    assert t['erro']['motivo'] == 'timeout' and 'SIGKILL' in t['erro']['message'] and t['ms'] < 3000
    o = casos['ocioso']
    assert o['erro']['motivo'] == 'ocioso' and 'sem saída há 0s' in o['erro']['message'] and o['ms'] < 3000
    assert casos['spawn']['erro']['motivo'] == 'spawn' and 'nao-existe-bilds-xyz' in casos['spawn']['erro']['message']


@pytest.mark.paridade
def test_stdin_do_filho_fica_aberto_enquanto_o_pai_vive(casos):
    # o filho sairia com 2 no EOF do stdin; como o pai está vivo, chega ao fim e sai com 0
    assert casos['stdinAberto']['ok']['code'] == 0


def _python_vigiado():
    codigo = ("import sys, time; sys.path.insert(0, sys.argv[1]); from processo import vigiar_stdin; "
              "vigiar_stdin(); print('pronto', flush=True); time.sleep(30)")
    return subprocess.Popen(['python3', '-c', codigo, str(PIPELINE)], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_python_sai_com_2_quando_o_stdin_fecha():
    p = _python_vigiado()
    assert p.stdout.readline().strip() == 'pronto'
    p.stdin.close()
    assert p.wait(timeout=10) == 2
    assert 'fechou o stdin' in p.stderr.read()


def test_python_continua_enquanto_o_stdin_esta_aberto():
    p = _python_vigiado()
    assert p.stdout.readline().strip() == 'pronto'
    time.sleep(0.5)
    assert p.poll() is None
    p.kill()
    p.wait(timeout=10)


@pytest.mark.thumbs
def test_thumbs_mjs_para_quando_o_stdin_fecha(tmp_path):
    """Com `sairComStdin`, o thumbs.mjs não renderiza o que ninguém vai registrar."""
    node = node_para_ts()
    if not node:
        pytest.skip('precisa de Node >= 22')
    geo_dir = ROOT / 'www' / 'storage' / 'bim' / 'geo'
    geos = sorted(str(p.relative_to(geo_dir)) for p in geo_dir.rglob('*.json') if not p.name.endswith('.orig.json')) if geo_dir.is_dir() else []
    if not geos:
        pytest.skip('sem geometria em www/storage/bim/geo')
    vendor = ROOT / 'templates' / 'vendor'
    if not (vendor / 'three.module.js').is_file():
        pytest.skip('templates/vendor sem three.module.js')
    cfg = tmp_path / 'cfg.json'
    cfg.write_text(json.dumps({'harnessDir': str(PIPELINE), 'vendorDir': str(vendor), 'geoDir': str(geo_dir),
                               'outDir': str(tmp_path / 'thumbs'), 'geos': geos[:1], 'sairComStdin': True}))
    p = subprocess.Popen([node, str(PIPELINE / 'thumbs.mjs'), str(cfg)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, cwd=ROOT)
    out, err = p.communicate(input='', timeout=120)      # fecha o stdin na hora: o "pai" morreu antes do Chromium subir
    assert p.returncode == 2 and 'fechou o stdin' in err, (p.returncode, err[-500:])
    assert out.strip() == '' and not list((tmp_path / 'thumbs').glob('*.webp'))
