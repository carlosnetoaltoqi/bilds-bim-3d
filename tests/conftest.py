"""
Suíte de testes do pipeline estático (scripts/) — criada em 2026-09-03 (I9 da
auditoria). Antes dela não havia nenhum teste; a "geração acusa erro" era
verificada rodando o build inteiro à mão.

Como rodar, na raiz do repositório:

    python3 -m pytest                 # tudo (≈ 30 s com a Akato e o Chromium)
    python3 -m pytest -m "not thumbs" # sem abrir o Chromium
    python3 -m pytest -m "not paridade and not thumbs"   # só Python

Fixtures reais: os `.aq` de `input/` (gitignored, 15 bibliotecas nesta máquina).
Testes que precisam de um deles usam `akato_aq` (7 MB, gerado pelo próprio
projeto na S6/S7, 262 peças com 262 geometrias, sem tubos/kits) e pulam com
motivo claro se o arquivo não existir. Os testes de formato usam blobs OQ3D
sintéticos escritos por `eng-reversa/tools/oq3d_writer.py`, então rodam em
qualquer máquina.

Saída: `output/.pytest-tmp/<aleatório>/` (apagado ao fim). Precisa ficar DENTRO
da raiz porque o `scripts/thumbs.mjs` serve a geometria por HTTP relativo à
raiz do projeto e recusa caminhos fora dela.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'eng-reversa' / 'tools'))

AKATO_AQ = ROOT / 'input' / 'Akato' / 'PVC Construção Civil' / 'pecas_akato_construcao_civil.aq'
MAXBAR_AQ = ROOT / 'input' / 'Maxbar' / 'pecas_maxbar_barramentoblindado.aq'
DANCOR_AQ = ROOT / 'input' / 'Dancor' / 'pecas_dancor_bombas_incendio_2026_04.1.aq'
AMANCO_AQ = ROOT / 'input' / 'Amanco' / 'pecas_Amanco_Esgoto_SN_SR_Silentium.aq'


def _fixture_aq(caminho):
    if not caminho.is_file():
        pytest.skip(f'fixture ausente: {caminho.relative_to(ROOT)} (input/ é gitignored)')
    return str(caminho)


@pytest.fixture(scope='session')
def akato_aq():
    return _fixture_aq(AKATO_AQ)


@pytest.fixture(scope='session')
def maxbar_aq():
    return _fixture_aq(MAXBAR_AQ)


@pytest.fixture(scope='session')
def dancor_aq():
    return _fixture_aq(DANCOR_AQ)


@pytest.fixture(scope='session')
def amanco_aq():
    return _fixture_aq(AMANCO_AQ)


@pytest.fixture
def saida(monkeypatch):
    """Redireciona toda a saída do build.py para uma pasta descartável."""
    import build
    base = ROOT / 'output' / '.pytest-tmp'
    base.mkdir(parents=True, exist_ok=True)
    d = Path(tempfile.mkdtemp(dir=base))
    monkeypatch.setattr(build, 'OUTPUT_DIR', str(d))
    monkeypatch.setattr(build, 'PREVIEW_DIR', str(d / 'preview'))
    monkeypatch.setattr(build, 'GEO_DIR', str(d / 'geo'))
    monkeypatch.setattr(build, 'THUMBS_DIR', str(d / 'thumbs'))
    yield d
    shutil.rmtree(d, ignore_errors=True)


def args_build(*flags):
    """Namespace igual ao da linha de comando do build.py."""
    import build
    return build.build_parser().parse_args(list(flags))


def node_para_ts():
    """Caminho de um Node capaz de rodar os .ts de www/tools direto, ou None.

    Node >= 22.6 remove tipos sem flag (>= 23.6 sem aviso) e traz node:sqlite;
    o aq-reader.ts precisa dos dois. Nesta máquina há v24 via nvm.
    """
    import build
    node = build._find_node()
    if not node:
        return None
    return node if (build._node_versao(node) or 0) >= 22 else None
