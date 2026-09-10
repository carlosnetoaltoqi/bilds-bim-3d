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

from bim_pipeline.aq import cadastro
from bim_pipeline.aq.aq_writer import SENT_INT
from bim_pipeline.aq.entradas_aq import (LIMITE_POR_SIMBOLOGIA, azimute, codigo_diametro,
                                          derivar, plausivel)
from conftest import ROOT
from malhas_sinteticas import tubo


@pytest.mark.parametrize('raio_cm, serie, codigo', [
    # a escala do AltoQi é em POLEGADA: o código é o índice da bitola nominal em polegada.
    (5.08, None, 12),       # 100 mm = 4" — inequívoco, não depende de série
    (10.00, None, 15),      # 200 mm = 8"
    (1.60, None, 6),        # 32 mm = 1"
    (1.40, None, 6),        # 28 mm (cobre) = 1"
    # 40, 50 e 75 mm são uma polegada em PVC soldável e outra em PVC esgoto: sem a série,
    # o bocal fica SEM código, porque gravar o palpite põe a peça na bitola errada calada.
    (2.50, None, None),
    (2.50, 'esgoto', 9),      # 50 mm esgoto = 2"
    (2.50, 'soldavel', 8),    # 50 mm soldável = 1.1/2"
    (2.56, 'esgoto', 9),      # o raio interno medido numa nativa de conexões de esgoto
    (3.78, 'esgoto', 11),     # 75 mm esgoto = 3"
    (3.78, 'soldavel', 10),   # 75 mm soldável = 2.1/2"
    (2.00, 'soldavel', 7),    # 40 mm soldável = 1.1/4"
    (2.00, 'esgoto', 8),      # 40 mm esgoto = 1.1/2"
    (0.90, None, None),       # 18 mm: longe de qualquer bitola da escala
])
def test_codigo_de_bitola_pela_escala_em_polegada(raio_cm, serie, codigo):
    assert codigo_diametro(raio_cm, serie) == codigo


@pytest.mark.parametrize('texto, codigo', [
    ('50 mm - 2"', 9), ('1.1/4"', 7), ('1 1/2"', 8), ('3/4"', 5), ('4"', 12),
    ('12"', 17), ('1/2"', 3), ('50 mm', None), ('Joelho 90', None),
])
def test_polegada_no_nome_da_a_bitola_sem_ambiguidade(texto, codigo):
    """A polegada declarada é o caminho mais confiável: a escala é em polegada."""
    assert cadastro.codigo_de_polegada(texto) == codigo


def test_serie_sai_do_titulo_da_biblioteca():
    assert cadastro.serie_do_titulo('Tubos e Conexões PVC Soldável') == 'soldavel'
    assert cadastro.serie_do_titulo('PVC Esgoto Série Normal') == 'esgoto'
    assert cadastro.serie_do_titulo('Válvulas e Atuadores HVAC') is None


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
    entradas = derivar(tubo(r_int=2.56, r_ext=2.80, comprimento=20.0), serie='esgoto')
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
    # a série ('esgoto') está no nome da linha: sem ela, 50 mm é ambíguo (1.1/2" em soldável,
    # 2" em esgoto) e o bocal sai sem código — o que o teste seguinte confere.
    geo = {'info': {'fabricante': 'Teste', 'linha': 'Tubos de PVC Esgoto', 'nome': 'Tubo 50'},
           'pos': pos.ravel().tolist(), 'col': [0.5, 0.5, 0.5] * len(V),
           'idx': F.ravel().tolist()}
    entrada = tmp_path / 'geo.json'
    saida = tmp_path / 'tubo.aq'
    entrada.write_text(json.dumps(geo), encoding='utf8')
    proc = subprocess.run([sys.executable, '-m', 'bim_pipeline.cli.gerar_aq',
                           str(entrada), str(saida), '--disciplina', 'sanitario', '--quiet'],
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


def test_bitola_ambigua_sem_serie_sai_sem_codigo_e_com_aviso(tmp_path):
    """40, 50 e 75 mm são uma polegada em PVC soldável e outra em esgoto.

    Sem a série declarada no título, o escritor **não escolhe**: grava a sentinela e avisa.
    Chutar poria a peça uma bitola inteira fora, e ninguém veria.
    """
    (V, F, _), = tubo(r_int=2.56, r_ext=2.80, comprimento=20.0)
    pos = np.stack([V[:, 0] / 100.0, V[:, 2] / 100.0, -V[:, 1] / 100.0], axis=1)
    geo = {'info': {'fabricante': 'Teste', 'linha': 'Tubos de teste', 'nome': 'Tubo 50'},
           'pos': pos.ravel().tolist(), 'col': [0.5, 0.5, 0.5] * len(V),
           'idx': F.ravel().tolist()}
    entrada, saida = tmp_path / 'geo.json', tmp_path / 'tubo.aq'
    entrada.write_text(json.dumps(geo), encoding='utf8')
    proc = subprocess.run([sys.executable, '-m', 'bim_pipeline.cli.gerar_aq',
                           str(entrada), str(saida), '--disciplina', 'sanitario', '--quiet'],
                          capture_output=True, text=True, cwd=ROOT, timeout=300)
    assert proc.returncode == 0, proc.stderr[-2000:]
    resumo = json.loads([l for l in proc.stdout.splitlines() if l.startswith('{')][-1])
    assert resumo['pecasSemBitola'] == 2
    assert any('sem código de bitola' in a for a in resumo['avisos'])

    con = sqlite3.connect(saida)
    ep = con.execute('SELECT DIAMETRO_EP FROM ENTRADA_PECA').fetchall()
    con.close()
    assert {r[0] for r in ep} == {SENT_INT}


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
                           str(entrada), str(saida), '--disciplina', 'sanitario', '--quiet'],
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
