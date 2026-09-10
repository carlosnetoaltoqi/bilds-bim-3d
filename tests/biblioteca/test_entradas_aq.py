"""bim_pipeline.aq.entradas_aq — os pontos de ligação que o `.aq` grava.

Sem `ENTRADA_3D`/`ENTRADA_PECA` a peça abre com "Pontos de ligação 3D: Não", não encaixa
em tubulação e o Builder não gera o wireframe que a desenha em planta e corte. O que
estes testes provam:

- o raio interno do bocal vira **código** de bitola na escala do AltoQi, e raio fora da
  escala fica sem código, em vez de virar o vizinho errado;
- o `ANGULO_EP` é o azimute do bocal, derivado da normal (que o detector orienta para fora);
- exportar uma malha de tubo pelo `gerar_aq` grava as duas tabelas, com a `ENTRADA_3D`
  no centro de cada ponta — em centímetro Z-up, que é o frame da `ENTRADA_3D`;
- a peça que ganha entrada sai com `CONEXAO_VOLUMETRICA = 1` — o "Pontos de ligação 3D:
  Sim" do Cadastro — e com `SECAO`/`DIAMETRO_INTERNO` **nulas**, que é de onde o Builder
  tira a seção quando a peça liga por pontos.
"""
import json
import sqlite3
import subprocess
import sys

import numpy as np
import pytest

from bim_pipeline.aq.aq_writer import SENT_INT
from bim_pipeline.aq.entradas_aq import (LIMITE_POR_SIMBOLOGIA, azimute, codigo_diametro,
                                          derivar, plausivel)
from conftest import ROOT
from malhas_sinteticas import tubo


@pytest.mark.parametrize('raio_cm, codigo', [
    (2.50, 9),      # 50 mm exato
    (2.56, 9),      # o raio interno medido numa nativa de conexões para a bitola de 50
    (5.08, 12),     # idem, 100 mm
    (10.00, 15),    # idem, 200 mm
    (3.78, 11),     # idem, 75 mm
    (0.90, None),   # 18 mm: abaixo da escala observada (20/25/32 não aparecem em nativa)
    (1.60, None),   # 32 mm, mesma razão
    (6.00, None),   # 120 mm: entre 100 e 150, longe dos dois
])
def test_codigo_de_bitola_pelo_nominal_mais_proximo(raio_cm, codigo):
    assert codigo_diametro(raio_cm) == codigo


@pytest.mark.parametrize('normal, grau', [
    ((1, 0, 0), 0.0),
    ((0, 1, 0), 90.0),
    ((-1, 0, 0), 180.0),
    ((0, -1, 0), 270.0),
    ((0, 0, 1), 0.0),        # bocal vertical não tem azimute
    ((0, 0, -1), 0.0),
])
def test_azimute_do_bocal(normal, grau):
    assert azimute(normal) == pytest.approx(grau)


def test_derivar_de_um_tubo_da_dois_bocais_opostos():
    entradas = derivar(tubo(r_int=2.56, r_ext=2.80, comprimento=20.0))
    assert len(entradas) == 2
    assert {e['codigo'] for e in entradas} == {9}
    assert sorted(round(e['posicao'][2], 6) for e in entradas) == [0.0, 20.0]
    # as normais apontam para fora, em sentidos opostos
    n = [e['normal'] for e in entradas]
    assert np.dot(n[0], n[1]) == pytest.approx(-1.0, abs=1e-6)


def test_gerar_aq_grava_as_duas_tabelas_de_entrada(tmp_path):
    """Ponta a ponta pelo CLI: malha do viewer (metros, Y-up) → `.aq` com entradas.

    O tubo entra deitado no eixo Y do viewer, que é o Z do `.aq` — é a conversão
    `(x·100, −z·100, y·100)`, e o teste confere que a entrada sai no frame do `.aq`.
    """
    (V, F, _), = tubo(r_int=2.56, r_ext=2.80, comprimento=20.0)
    pos = np.stack([V[:, 0] / 100.0, V[:, 2] / 100.0, -V[:, 1] / 100.0], axis=1)  # cm Z-up → m Y-up
    geo = {'info': {'fabricante': 'Teste', 'linha': 'Tubos de teste', 'nome': 'Tubo 50'},
           'pos': pos.ravel().tolist(), 'col': [0.5, 0.5, 0.5] * len(V),
           'idx': F.ravel().tolist()}
    entrada = tmp_path / 'geo.json'
    saida = tmp_path / 'tubo.aq'
    entrada.write_text(json.dumps(geo), encoding='utf8')
    proc = subprocess.run([sys.executable, '-m', 'bim_pipeline.cli.gerar_aq',
                           str(entrada), str(saida), '--quiet'],
                          capture_output=True, text=True, cwd=ROOT, timeout=300)
    assert proc.returncode == 0, proc.stderr[-2000:]
    resumo = json.loads([l for l in proc.stdout.splitlines() if l.startswith('{')][-1])
    assert resumo['entradas'] == 2

    con = sqlite3.connect(saida)
    e3 = con.execute('SELECT POSICAO_X, POSICAO_Y, POSICAO_Z, TIPO_SECAO, DIAMETRO'
                     ' FROM ENTRADA_3D ORDER BY POSICAO_Z').fetchall()
    ep = con.execute('SELECT LIGACAO_EP, DIAMETRO_EP, SECAO_EP, ANGULO_EP'
                     ' FROM ENTRADA_PECA').fetchall()
    con.close()
    assert len(e3) == 2 and len(ep) == 2
    assert [round(r[2], 4) for r in e3] == [0.0, 20.0]          # centímetro, Z-up
    assert all(round(r[0], 4) == 0.0 and round(r[1], 4) == 0.0 for r in e3)
    assert {r[4] for r in e3} == {9}                            # bitola de 50 mm
    assert {r[1] for r in ep} == {9} and SENT_INT not in {r[1] for r in ep}


def test_peca_com_entrada_sai_marcada_e_sem_secao_no_cadastro(tmp_path):
    """Duas marcas da peça que liga por pontos, medidas no catálogo oficial do Builder.

    `CONEXAO_VOLUMETRICA = 1` é o "Pontos de ligação 3D: Sim" do Cadastro — 4.206 de 4.206
    peças com ele têm `ENTRADA_3D`; e `SECAO`/`DIAMETRO_INTERNO` ficam nulas na peça com
    entrada (15.321 de 15.321). Enquanto os escritores gravavam 0 e o *default* 10, a peça
    abria no Builder com "Pontos de ligação 3D: Não" mesmo desenhando os pontos.
    """
    (V, F, _), = tubo(r_int=2.56, r_ext=2.80, comprimento=20.0)
    pos = np.stack([V[:, 0] / 100.0, V[:, 2] / 100.0, -V[:, 1] / 100.0], axis=1)
    geo = {'info': {'fabricante': 'Teste', 'linha': 'Tubos de teste', 'nome': 'Tubo 50'},
           'pos': pos.ravel().tolist(), 'col': [0.5, 0.5, 0.5] * len(V),
           'idx': F.ravel().tolist()}
    entrada, saida = tmp_path / 'geo.json', tmp_path / 'tubo.aq'
    entrada.write_text(json.dumps(geo), encoding='utf8')
    proc = subprocess.run([sys.executable, '-m', 'bim_pipeline.cli.gerar_aq',
                           str(entrada), str(saida), '--quiet'],
                          capture_output=True, text=True, cwd=ROOT, timeout=300)
    assert proc.returncode == 0, proc.stderr[-2000:]

    con = sqlite3.connect(saida)
    pecas = con.execute('SELECT CONEXAO_VOLUMETRICA, SECAO, DIAMETRO_INTERNO'
                        ' FROM PECA').fetchall()
    secoes = con.execute('SELECT DISTINCT SECAO_EP FROM ENTRADA_PECA').fetchall()
    con.close()
    assert pecas == [(1, None, None)]     # marcada, e sem o default 10 do schema
    assert secoes == [(10,)]              # a seção está na entrada, que é onde a nativa põe


@pytest.mark.parametrize('n, ok', [
    (2, True),                             # uma luva
    (LIMITE_POR_SIMBOLOGIA, True),         # o máximo que uma simbologia nativa tem
    (LIMITE_POR_SIMBOLOGIA + 1, False),
    (107, False),                          # um projeto .rvt inteiro numa simbologia
])
def test_quantidade_de_bocais_fora_da_distribuicao_nativa_e_descartada(n, ok):
    """107 bocais não são uma peça: é um projeto inteiro virando simbologia, e a malha tem
    dezenas de pontas de tubo que não ligam em nada. Quem chama descarta e reporta, em vez
    de truncar — escolher 38 dos 107 seria inventar quais são ponto de ligação."""
    assert plausivel([{'posicao': (0, 0, 0)}] * n) is ok
