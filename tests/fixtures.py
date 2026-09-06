"""
Fixtures reais por PAPEL, não por empresa (ADR-016).

`tests/fixtures.local.json` (gitignored) diz, nesta máquina, qual arquivo faz cada papel e o que
se espera dele. Sem o arquivo, ou sem o papel, os testes que dependem dele PULAM com motivo — é o
que acontece no CI. Modelo em `tests/fixtures.example.json`.

Papéis:
  aq_pequena   um .aq inteiro, com geometria em TODA peça (sem tubos/kits): {caminho, pecas, fabricante, titulo, slug, layout}
  aq_grande    um .aq grande, com peças sem geometria e simbologias compartilhadas: {caminho, pecas, simbologias}
  aq_schema_antigo  um .aq de schema <= 582 (sem ENTRADA_3D.DIAMETRO): {caminho}
  aq_malha_v3  um .aq cujo OQ3D tem malhas versão 3: {caminho}
  step_peca    um .stp de uma peça: {caminho, bbox_mm}
  iges_pasta   pasta com .igs de faces soltas: {caminho}
  dll_plugin   DLL de um plugin de CAD que é casca de catálogo web: {caminho}
  manifesto_plugin  manifesto.json de um download real do plugin web: {caminho}
  rfa_familias  .zip (ou pasta) de famílias Revit .rfa de um fabricante, com type catalogs .txt ao lado: {caminho}
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_ARQ = Path(__file__).with_name('fixtures.local.json')
FIXTURAS = json.loads(_ARQ.read_text(encoding='utf8')) if _ARQ.is_file() else {}


def caminho(papel):
    """Caminho absoluto da fixture do papel, ou None se não está nesta máquina."""
    f = FIXTURAS.get(papel)
    if not f or not f.get('caminho'):
        return None
    p = Path(f['caminho'])
    p = p if p.is_absolute() else ROOT / p
    return str(p) if p.exists() else None


def exigir(papel):
    """Para usar em fixtures do pytest: o caminho, ou `pytest.skip` com o motivo."""
    c = caminho(papel)
    if not c:
        pytest.skip(f'fixture "{papel}" não configurada em tests/fixtures.local.json (veja tests/fixtures.py)')
    return c
