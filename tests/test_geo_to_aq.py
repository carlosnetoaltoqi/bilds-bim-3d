"""I4 (2026-09-05): o "Exportar .aq" do editor não depende mais de uma pasta de estudo.

`geo_to_aq.py` importava `gerar_aq.py`/`oq3d_writer.py` de `eng-reversa/tools/` e lia o DDL em
`eng-reversa/dados/`. Agora o genérico mora no pipeline do serviço — `aq_writer.py` (schema 607,
constantes do AltoQi, escritor cp1252), `oq3d_writer.py`, `schema-aq-607.sql` — e o
`gerar_aq.py` da Akato herda dele (`Gerador(EscritorAq)`). Dois guardas: o pipeline não importa
nada de fora do próprio diretório, e um `.aq` gerado a partir de uma malha é lido de volta pelo
`read_aq.py` e pelo `oq3d.py` com a mesma geometria.
"""
import json
import re
import subprocess
import sys

import oq3d
import read_aq
from conftest import PIPELINE, ROOT


def test_pipeline_nao_importa_de_fora_do_proprio_diretorio():
    culpados = []
    for p in sorted(PIPELINE.glob('*.py')):
        for n, linha in enumerate(p.read_text(encoding='utf8').splitlines(), 1):
            linha = linha.split('#', 1)[0]      # só o código: comentários podem citar a origem
            if re.match(r'\s*(import|from)\s+\w', linha) and 'eng-reversa' in linha:
                culpados.append(f'{p.name}:{n}: {linha.strip()}')
            if 'sys.path.insert' in linha and ('eng-reversa' in linha or "'..'" in linha):
                culpados.append(f'{p.name}:{n}: {linha.strip()}')
    assert culpados == [], culpados
    assert (PIPELINE / 'schema-aq-607.sql').is_file() and (PIPELINE / 'aq_writer.py').is_file() and (PIPELINE / 'oq3d_writer.py').is_file()


def test_geo_to_aq_gera_um_aq_que_o_leitor_do_projeto_le(tmp_path):
    # um triângulo em metros, Y-up, com cor por vértice — o formato do viewer
    geo = {'info': {'fabricante': 'Teste', 'linha': 'Peças de teste', 'nome': 'Peça Ímpar ç', 'codigo': 'T-1',
                    'specs': {'Material': 'PVC'}},
           'pos': [0, 0, 0, 0.1, 0, 0, 0, 0.1, 0], 'col': [1, 0, 0] * 3, 'idx': [0, 1, 2]}
    entrada = tmp_path / 'geo.json'; saida = tmp_path / 'peca.aq'
    entrada.write_text(json.dumps(geo), encoding='utf8')
    proc = subprocess.run([sys.executable, str(PIPELINE / 'geo_to_aq.py'), str(entrada), str(saida), '--quiet'],
                          capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    resumo = json.loads([l for l in proc.stdout.splitlines() if l.startswith('{')][-1])
    assert resumo['malhas'] == 1 and resumo['triangulos'] == 1 and saida.stat().st_size == resumo['bytes']

    dados = read_aq.extract(str(saida))
    assert [p['NOME_PECA'] for p in dados['pecas']] == ['Peça Ímpar ç']      # cp1252 gravado e lido de volta
    assert dados['grupos'][0]['NOME_GP'] == 'Peças de teste'
    assert {p['propriedade']: p['VALOR'] for p in dados['propriedades']}['Material'] == 'PVC'
    simbologias, por_peca = read_aq.extract_simbologias(str(saida))
    assert len(simbologias) == 1 and list(por_peca.values()) == [next(iter(simbologias))]
    blob = next(iter(simbologias.values()))['blob']
    assert oq3d.is_oq3d(blob)
    b = oq3d.to_buffers(blob)
    assert len(b['idx']) == 3 and len(b['pos']) == 9
    # ida e volta em metros: o OQ3D grava em cm e o leitor converte de volta
    assert max(abs(a - e) for a, e in zip(b['pos'], geo['pos'])) < 1e-6
    assert [round(c, 3) for c in b['col'][:3]] == [1.0, 0.0, 0.0]
