"""scripts/bootstrap.sh --check — o ambiente declarado (passo 5 da auditoria, 2026-09-04).

Não instala nada: só prova que o modo --check roda, imprime a tabela com as linhas
obrigatórias e devolve 0/1 conforme o que encontra. O caso "sem Node nem nvm" usa
HOME e PATH falsos para forçar a falha e conferir a mensagem.
"""
import os
import subprocess

from conftest import ROOT

SCRIPT = ROOT / 'scripts' / 'bootstrap.sh'


def _check(**env):
    r = subprocess.run(['bash', str(SCRIPT), '--check'], capture_output=True, text=True,
                       timeout=120, env={**os.environ, **env})
    return r.returncode, r.stdout + r.stderr


def test_sintaxe_bash():
    assert subprocess.run(['bash', '-n', str(SCRIPT)]).returncode == 0


def test_check_imprime_a_tabela_e_sai_0_ou_1():
    codigo, out = _check()
    assert codigo in (0, 1), out
    for item in ('| Python |', '| biblioteca (bim_pipeline) |', '| Node |', '| pnpm |',
                 '| miniaturas (playwright + three) |', '| libs do Chromium |'):
        assert item in out, item
    assert '| Item | Estado | Como conferir |' in out


def test_check_sem_node_acusa_falta_e_sai_1(tmp_path):
    # PATH só com /usr/bin e /bin (o Node do apt, se existir, é 18) e HOME sem ~/.nvm
    codigo, out = _check(HOME=str(tmp_path), PATH='/usr/bin:/bin', BILDS_NODE='')
    assert codigo == 1
    assert '| Node | FALTA' in out and 'nvm install' in out
    assert 'FALTA algo obrigatório' in out


def test_argumento_desconhecido_sai_2():
    r = subprocess.run(['bash', str(SCRIPT), '--nao-existe'], capture_output=True, text=True)
    assert r.returncode == 2 and '--check' in r.stdout
