"""bim_pipeline.cli.ferramentas (validar_aq, aq_referencia, oq3d_anatomy, preencher_entradas_aq) e bim_pipeline.aq.formas_parametricas.

As ferramentas rodam sobre um .aq escrito pela própria biblioteca (geo_to_aq), então o
teste não depende de fixture real. As formas paramétricas têm de gerar malhas fechadas que o escritor
OQ3D grava e o leitor relê. A `preencher_entradas_aq` é a única que escreve: ela conserta um
`.aq` exportado antes de 2026-09-09, quando nenhum ponto de ligação era gravado.
"""
import json
import sqlite3
import subprocess
import sys

import numpy as np
import pytest

from bim_pipeline.aq import formas_parametricas as fp
from bim_pipeline.aq import oq3d, oq3d_writer
from malhas_sinteticas import tubo


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


def test_preencher_entradas_aq_recupera_os_bocais_de_um_aq_sem_entradas(tmp_path):
    """O `.aq` de quem exportou antes da correção não tem ponto de ligação nenhum. A
    ferramenta acha os bocais na malha que já está no arquivo, e não duplica se rodar de
    novo."""
    (V, F, _), = tubo(r_int=2.56, r_ext=2.80, comprimento=20.0)
    pos = np.stack([V[:, 0] / 100.0, V[:, 2] / 100.0, -V[:, 1] / 100.0], axis=1)
    geo = {'info': {'fabricante': 'Fabricante Exemplo', 'linha': 'Linha Exemplo', 'nome': 'Tubo'},
           'pos': pos.ravel().tolist(), 'col': [0.5, 0.5, 0.5] * len(V), 'idx': F.ravel().tolist()}
    (tmp_path / 'geo.json').write_text(json.dumps(geo), encoding='utf8')
    aq = str(tmp_path / 'tubo.aq')
    r = subprocess.run([sys.executable, '-m', 'bim_pipeline.cli.gerar_aq',
                        str(tmp_path / 'geo.json'), aq, '--quiet'],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr

    def conta():
        con = sqlite3.connect(aq)
        try:
            return tuple(con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
                         for t in ('ENTRADA_3D', 'ENTRADA_PECA'))
        finally:
            con.close()

    def cadastro():
        con = sqlite3.connect(aq)
        try:
            return con.execute('SELECT CONEXAO_VOLUMETRICA, SECAO, DIAMETRO_INTERNO'
                               ' FROM PECA').fetchall()
        finally:
            con.close()

    con = sqlite3.connect(aq)                      # o estado de quem exportou antes
    con.execute('DELETE FROM ENTRADA_3D')
    con.execute('DELETE FROM ENTRADA_PECA')
    con.execute('UPDATE PECA SET CONEXAO_VOLUMETRICA = 0, SECAO = 10, DIAMETRO_INTERNO = 10')
    con.commit()
    con.close()
    assert conta() == (0, 0)
    assert cadastro() == [(0, 10, 10.0)]

    codigo, out = _roda('preencher_entradas_aq', aq, '--quiet')
    assert codigo == 0, out
    assert conta() == (2, 2)
    # a ferramenta também marca "Pontos de ligação 3D" e devolve a seção para as entradas,
    # senão o Cadastro continua dizendo "Não" com os pontos gravados e desenhados
    assert cadastro() == [(1, None, None)]
    codigo, out = _roda('preencher_entradas_aq', aq, '--quiet')     # idempotente
    assert codigo == 0, out
    assert conta() == (2, 2)
    assert cadastro() == [(1, None, None)]

    # O caso das bibliotecas de 2026-09-09: as entradas JÁ estão gravadas e desenham os
    # pontos, mas a seção ficou no cadastro da peça e o Builder diz "Pontos de ligação
    # 3D: Não". A ferramenta pula a detecção (a simbologia já tem entrada) e ainda assim
    # tem de marcar a peça e devolver a seção para as entradas.
    con = sqlite3.connect(aq)
    con.execute('UPDATE PECA SET CONEXAO_VOLUMETRICA = 0, SECAO = 10, DIAMETRO_INTERNO = 10')
    con.commit()
    con.close()
    codigo, out = _roda('preencher_entradas_aq', aq)
    assert codigo == 0, out
    assert '1 peças com pontos de ligação 3D (1 corrigidas agora)' in out
    assert conta() == (2, 2) and cadastro() == [(1, None, None)]


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
