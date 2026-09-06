"""bim_pipeline.cli.ferramentas.oq3d_roundtrip — o escritor OQ3D provado contra o leitor.

I8 da auditoria (2026-09-04): o caso 6 (blob real) apontava um caminho inexistente, era pulado em
silêncio e o script saía 0 com "todos os casos passaram". Regra: `--aq` apontado e ausente é FALHA
(exit 1) a menos que se peça `--sem-real`; sem `--aq` o caso 6 simplesmente não é pedido.

Roda a ferramenta como processo, como a pessoa roda — o módulo acumula falhas em estado global.
"""
import subprocess
import sys


def _roda(*args):
    r = subprocess.run([sys.executable, '-m', 'bim_pipeline.cli.ferramentas.oq3d_roundtrip', *args],
                       capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout + r.stderr


def test_sem_aq_roda_os_casos_sinteticos_e_passa():
    codigo, out = _roda()
    assert codigo == 0, out
    assert '6. reescrita de geometria real: não pedido' in out and 'todos os casos passaram' in out


def test_com_aq_real_reescreve_uma_simbologia(aq_grande):
    codigo, out = _roda('--aq', aq_grande)
    assert codigo == 0, out
    assert '6. reescrita de geometria real' in out and 'reescrita' in out and 'sem WIREFRAME' in out
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
