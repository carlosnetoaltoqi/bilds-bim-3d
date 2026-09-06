"""
Suíte em três camadas (docs/arquitetura.md): `tests/biblioteca/` (Python puro + fixtures por papel), `tests/servicos/`
(harnesses Node em tests/paridade/ e round-trips do editor), `tests/arquitetura/` (as sete regras de fronteira,
termos da POC, contratos, dependências).
Criada em 2026-09-03 (I9 da auditoria); reorganizada em 2026-09-06 (S8/F1).

Como rodar, na raiz do repositório:

    python3 -m pytest                 # tudo (≈ 3 min com as fixtures reais e o Chromium)
    python3 -m pytest -m "not thumbs" # sem abrir o Chromium
    python3 -m pytest -m "not paridade and not thumbs"   # só Python

Fixtures reais são referenciadas por PAPEL em `tests/fixtures.local.json` (gitignored; modelo em
`tests/fixtures.example.json`; papéis em `tests/fixtures.py`) — nenhum nome de fabricante ou
caminho de arquivo mora nos testes (ADR-016). Sem o arquivo, esses testes pulam com motivo.
Os testes de formato usam blobs OQ3D sintéticos escritos pela própria biblioteca e rodam em
qualquer máquina.

Saída: `output/.pytest-tmp/<aleatório>/` (apagado ao fim).
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BIBLIOTECA = ROOT / 'biblioteca'                 # o pacote `bim_pipeline` (S8/F1, 2026-09-06)
PIPELINE = BIBLIOTECA / 'bim_pipeline'           # a pasta do pacote (para os testes que olham os arquivos)
# A biblioteca é instalável (`pip install -e biblioteca`); aqui garantimos que a suíte e os
# subprocessos `python -m bim_pipeline.cli.*` a achem mesmo sem instalar.
sys.path.insert(0, str(BIBLIOTECA))
os.environ['PYTHONPATH'] = str(BIBLIOTECA) + (os.pathsep + os.environ['PYTHONPATH'] if os.environ.get('PYTHONPATH') else '')
sys.path.insert(0, str(ROOT / 'tests'))

from fixtures import exigir   # noqa: E402


@pytest.fixture(scope='session')
def aq_pequena():
    return exigir('aq_pequena')


@pytest.fixture(scope='session')
def aq_grande():
    return exigir('aq_grande')


@pytest.fixture(scope='session')
def aq_malha_v3():
    return exigir('aq_malha_v3')


@pytest.fixture
def saida():
    """Pasta descartável dentro da raiz (output/.pytest-tmp/) para o que um teste gravar."""
    base = ROOT / 'output' / '.pytest-tmp'
    base.mkdir(parents=True, exist_ok=True)
    d = Path(tempfile.mkdtemp(dir=base))
    yield d
    shutil.rmtree(d, ignore_errors=True)


def node_para_ts():
    """Caminho de um Node capaz de rodar os .ts/.mts dos harnesses direto, ou None.

    Node >= 22.6 remove tipos sem flag (>= 23.6 sem aviso). Nesta máquina há v24 via nvm.
    """
    from bim_pipeline.miniaturas.render import find_node, node_versao
    node = find_node()
    if not node:
        return None
    return node if (node_versao(node) or 0) >= 22 else None
