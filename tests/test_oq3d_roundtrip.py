"""eng-reversa/tools/oq3d_roundtrip.py — o escritor OQ3D provado contra o leitor.

I8 da auditoria (2026-09-04): o caso 6 (blob real da Amanco) apontava uma subpasta
inexistente, era pulado em silêncio e o script saía 0 com "todos os casos passaram".
Agora .aq ausente é FALHA (exit 1) a menos que se peça `--sem-real`.

Roda o script como processo, como a pessoa roda — o módulo acumula falhas em
estado global e não vale a pena importá-lo duas vezes no mesmo processo.
"""
import subprocess
import sys

import pytest

from conftest import ROOT

SCRIPT = ROOT / 'eng-reversa' / 'tools' / 'oq3d_roundtrip.py'


def _roda(*args):
    r = subprocess.run([sys.executable, str(SCRIPT), *args],
                       capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout + r.stderr


def test_caminho_padrao_e_o_da_amanco_nesta_arvore():
    import oq3d_roundtrip
    assert oq3d_roundtrip.PADRAO_AQ.endswith(
        'input/Amanco/pecas_Amanco_Esgoto_SN_SR_Silentium.aq')
    assert '/PVC Esgoto' not in oq3d_roundtrip.PADRAO_AQ   # a subpasta que não existia


def test_padrao_roda_os_seis_casos_e_passa(aq_grande):
    codigo, out = _roda()
    assert codigo == 0, out
    assert '6. reescrita de geometria real' in out and 'DN150 - QUADRADA' in out
    assert 'todos os casos passaram' in out and 'pulado' not in out


def test_aq_ausente_e_falha_nao_pulado():
    codigo, out = _roda('--aq', '/nao/existe.aq')
    assert codigo == 1
    assert '[FALHA] biblioteca do caso real existe' in out
    assert '--sem-real' in out                      # diz como pular de propósito
    assert 'todos os casos passaram' not in out


def test_sem_real_pula_explicitamente_e_passa():
    codigo, out = _roda('--aq', '/nao/existe.aq', '--sem-real')
    assert codigo == 0, out
    assert 'pulado de propósito' in out and 'todos os casos passaram' in out
