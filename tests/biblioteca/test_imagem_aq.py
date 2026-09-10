"""2026-09-08: sem `SIMBOLOGIA_3D.IMAGEM` o AltoQi Builder NÃO desenha a peça.

As quatro bibliotecas exportadas em 2026-09-08 (conexões, dois pacotes de famílias Revit e um
projeto `.rvt`) abriram no Builder com nome, código, descrição e propriedades de cada peça — e
sem forma nenhuma, apesar de megabytes de OQ3D válido. O experimento que isolou o campo está no
docstring de `bim_pipeline.aq.imagem_aq`: numa biblioteca nativa, apagar só a `IMAGEM` (mantendo
o `WIREFRAME`) faz a peça parar de desenhar; apagar só o `WIREFRAME` (mantendo a `IMAGEM`) não.

Estes testes prendem os dois lados do achado:
  - o formato do BMP é o dos nativos (100×100, 24 bits, 30.054 bytes) — o Builder não aceita outro;
  - os dois caminhos de escrita (`geo_to_aq`, `catalogo_to_aq`) gravam a `IMAGEM` de toda
    simbologia, e o `validar_aq` FALHA quando ela está nula.
"""
import json
import sqlite3
import struct
import subprocess
import sys

from bim_pipeline.aq import imagem_aq
from bim_pipeline.aq import read_aq
from conftest import ROOT

# um tetraedro em centímetros, Z-up, no contrato de `oq3d_writer.escrever`
MALHA_TETRAEDRO = [([(0, 0, 0), (10, 0, 0), (0, 10, 0), (0, 0, 10)],
                    [(0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)],
                    (200, 30, 40, 255), None)]


def _cabecalho(bmp):
    largura, altura, planos, bits, compressao = struct.unpack_from('<iiHHI', bmp, 18)
    return {'assinatura': bmp[:2], 'bytes': len(bmp), 'largura': largura, 'altura': altura,
            'planos': planos, 'bits': bits, 'compressao': compressao,
            'offset_dados': struct.unpack_from('<I', bmp, 10)[0]}


def test_bmp_sai_no_formato_exato_dos_nativos():
    """100×100, 24 bits, sem compressão, 54 + 100×300 = 30.054 bytes — como as 16 nativas medidas."""
    bmp = imagem_aq.render(MALHA_TETRAEDRO)
    assert _cabecalho(bmp) == {'assinatura': b'BM', 'bytes': 30054, 'largura': 100, 'altura': 100,
                               'planos': 1, 'bits': 24, 'compressao': 0, 'offset_dados': 54}


def test_a_peca_aparece_no_bmp_e_com_a_cor_da_malha():
    """O rasterizador tem que pintar de fato: fundo branco, peça na cor da malha, e nem tudo branco."""
    bmp = imagem_aq.render(MALHA_TETRAEDRO)
    pixels = bmp[54:]
    trincas = {tuple(pixels[i:i + 3]) for i in range(0, len(pixels), 3)}      # BGR
    assert (255, 255, 255) in trincas, 'o fundo dos nativos é branco'
    assert len(trincas) > 1, 'saiu uma imagem chapada — o rasterizador não pintou nada'
    # a malha é (200, 30, 40) em RGB; com sombreamento o vermelho domina o azul em todo pixel pintado
    pintados = [t for t in trincas if t != (255, 255, 255)]
    assert all(t[2] >= t[0] for t in pintados), f'cor da malha não sobreviveu: {pintados[:5]}'


def test_malha_vazia_nao_gera_imagem():
    """Sem triângulo não há preview — e quem chama grava NULL em vez de um BMP branco mentiroso."""
    assert imagem_aq.render([]) is None
    assert imagem_aq.render([([], [], (0, 0, 0, 255), None)]) is None


def test_transform_da_malha_entra_no_preview():
    """Se a imagem ignorasse o `xform`, o preview mostraria a peça montada errada e o 3D certo."""
    deslocado = [(MALHA_TETRAEDRO[0][0], MALHA_TETRAEDRO[0][1], MALHA_TETRAEDRO[0][2],
                  ((0, -1, 0, 1, 0, 0, 0, 0, 1), (0, 0, 0)))]      # 90° em torno de Z
    assert imagem_aq.render(deslocado) != imagem_aq.render(MALHA_TETRAEDRO)


def test_geo_to_aq_grava_a_imagem_de_toda_simbologia(tmp_path):
    """O caminho de uma peça (o "Exportar .aq" do editor) não pode sair sem preview."""
    geo = {'info': {'fabricante': 'Teste', 'linha': 'Peças de teste', 'nome': 'Peça com preview'},
           'pos': [0, 0, 0, 0.1, 0, 0, 0, 0.1, 0, 0, 0, 0.1], 'col': [0, 0.6, 1] * 4,
           'idx': [0, 1, 2, 0, 1, 3, 0, 2, 3, 1, 2, 3]}
    entrada = tmp_path / 'geo.json'; saida = tmp_path / 'peca.aq'
    entrada.write_text(json.dumps(geo), encoding='utf8')
    proc = subprocess.run([sys.executable, '-m', 'bim_pipeline.cli.gerar_aq',
                           str(entrada), str(saida), '--disciplina', 'hidraulico', '--quiet'],
                          capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]

    simbologias, _ = read_aq.extract_simbologias(str(saida))
    assert simbologias, 'nenhuma simbologia gravada'
    for s in simbologias.values():
        assert s['imagem'], f"simbologia {s['nome']!r} sem IMAGEM — o Builder não desenharia"
        assert _cabecalho(bytes(s['imagem']))['bytes'] == 30054


def test_validar_aq_falha_quando_a_imagem_e_apagada(tmp_path):
    """A checagem que faltava: é o `validar_aq` que tem de acusar a biblioteca invisível."""
    geo = {'info': {'fabricante': 'Teste', 'linha': 'Peças de teste', 'nome': 'Peça sem preview'},
           'pos': [0, 0, 0, 0.1, 0, 0, 0, 0.1, 0], 'col': [1, 0, 0] * 3, 'idx': [0, 1, 2]}
    entrada = tmp_path / 'geo.json'; saida = tmp_path / 'peca.aq'
    entrada.write_text(json.dumps(geo), encoding='utf8')
    assert subprocess.run([sys.executable, '-m', 'bim_pipeline.cli.gerar_aq',
                           str(entrada), str(saida), '--disciplina', 'hidraulico', '--quiet'],
                          capture_output=True, text=True, cwd=ROOT, timeout=120).returncode == 0

    def validar():
        return subprocess.run([sys.executable, '-m', 'bim_pipeline.cli.ferramentas.validar_aq', str(saida)],
                              capture_output=True, text=True, cwd=ROOT, timeout=120)

    assert validar().returncode == 0, 'o .aq recém-gerado já devia passar'

    con = sqlite3.connect(str(saida))
    con.execute('UPDATE SIMBOLOGIA_3D SET IMAGEM = NULL')
    con.commit(); con.close()

    proc = validar()
    assert proc.returncode == 1, 'validar_aq passou numa biblioteca que o Builder não desenha'
    assert 'toda simbologia tem IMAGEM' in proc.stdout
