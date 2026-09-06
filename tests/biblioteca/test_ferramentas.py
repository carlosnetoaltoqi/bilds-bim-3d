"""bim_pipeline.cli.ferramentas (validar_aq, aq_referencia, oq3d_anatomy) e bim_pipeline.aq.formas_parametricas.

As ferramentas são só leitura e rodam sobre um .aq escrito pela própria biblioteca (geo_to_aq), então o
teste não depende de fixture real. As formas paramétricas têm de gerar malhas fechadas que o escritor
OQ3D grava e o leitor relê.
"""
import json
import subprocess
import sys

import pytest

from bim_pipeline.aq import formas_parametricas as fp
from bim_pipeline.aq import oq3d, oq3d_writer


@pytest.fixture(scope='module')
def aq_gerado(tmp_path_factory):
    d = tmp_path_factory.mktemp('aq')
    geo = {'info': {'fabricante': 'Fabricante Exemplo', 'linha': 'Linha Exemplo', 'nome': 'Peça Ç', 'codigo': 'X-1',
                    'specs': {'Material': 'PVC'}},
           'pos': [0, 0, 0, 0.1, 0, 0, 0, 0.1, 0], 'col': [1, 0, 0] * 3, 'idx': [0, 1, 2]}
    (d / 'geo.json').write_text(json.dumps(geo), encoding='utf8')
    r = subprocess.run([sys.executable, '-m', 'bim_pipeline.cli.gerar_aq', str(d / 'geo.json'), str(d / 'p.aq'), '--quiet'],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return str(d / 'p.aq')


def _roda(mod, *args):
    r = subprocess.run([sys.executable, '-m', f'bim_pipeline.cli.ferramentas.{mod}', *args],
                       capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout + r.stderr


def test_validar_aq_aceita_um_aq_da_biblioteca(aq_gerado):
    codigo, out = _roda('validar_aq', aq_gerado)
    assert codigo == 0, out
    assert 'lido pela biblioteca sem ressalvas' in out and 'FALHA' not in out
    # as conferências de tamanho só rodam quando pedidas, e falham quando não batem
    codigo, out = _roda('validar_aq', aq_gerado, '--max-conexao-cm', '0.001')
    assert codigo == 1 and 'nenhuma conexão maior que 0.001 cm' in out


def test_aq_referencia_e_anatomy_leem_o_aq(aq_gerado):
    codigo, out = _roda('aq_referencia', aq_gerado, '--limite', '2')
    assert codigo == 0, out
    assert 'PROJETO_APLICACAO' in out or 'TIPO_APLICACAO_PECA' in out
    codigo, out = _roda('oq3d_anatomy', aq_gerado, '1')
    assert codigo == 0, out
    assert 'TQi3D' in out


@pytest.mark.parametrize('forma', sorted(fp.GERADORES))
def test_formas_parametricas_geram_malhas_que_o_oq3d_le(forma):
    peca = fp.Peca(50, 25, 'ESGOTO', f'{forma.upper()} 50 x 25mm 6M', comprimento_cm=60)
    malhas = fp.gerar(forma, peca)
    assert malhas, forma
    for verts, tris, rgba in malhas:
        assert len(verts) >= 3 and len(tris) >= 1 and len(rgba) == 4
        assert all(len(v) == 3 for v in verts) and all(0 <= i < len(verts) for t in tris for i in t)
    dx, dy, dz = fp.bbox(malhas)
    assert max(dx, dy, dz) > 0 and max(dx, dy, dz) < 700     # cm: nada absurdo
    blob = oq3d_writer.escrever([(v, t, c, None) for v, t, c in malhas])
    relido = oq3d.extract(blob)
    assert len(relido) == len(malhas)
    assert sum(len(t) for _, t, _ in relido) == sum(len(t) for _, t, _ in malhas)
