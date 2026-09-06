"""Regra 6 de docs/arquitetura.md §3 (ADR-016): nenhum fabricante, domínio ou caminho efêmero da POC em código,
contratos, conhecimento ou skills. Os termos estão em `termos_efemeros.txt`; os únicos lugares permitidos são
`docs/historico/`, `docs/integracoes/`, `tests/fixtures.local.json` e o próprio arquivo de termos."""
import re

from conftest import ROOT

TERMOS = [l.strip().lower() for l in (ROOT / 'tests' / 'arquitetura' / 'termos_efemeros.txt').read_text(encoding='utf8').splitlines()
          if l.strip() and not l.startswith('#')]
PADRAO = re.compile('|'.join(re.escape(t) for t in TERMOS), re.I)
EXTS = {'.py', '.ts', '.tsx', '.mts', '.cts', '.mjs', '.js', '.sh', '.json', '.yaml', '.yml', '.html', '.md', '.toml', '.sql', '.txt', '.css'}
# F6 acrescenta docs/conhecimento e docs/skills quando forem reescritos
RAIZES = ['biblioteca/bim_pipeline', 'pacotes/base/src', 'pacotes/dominio/src', 'servicos', 'web/src', 'web/tools', 'tests', '.github', 'scripts', '.env.example']
IGNORAR_PARTES = {'node_modules', 'dist', '.next', '__pycache__', 'e2e'}
PERMITIDOS = {ROOT / 'tests' / 'fixtures.local.json', ROOT / 'tests' / 'arquitetura' / 'termos_efemeros.txt'}


def _arquivos():
    for r in RAIZES:
        base = ROOT / r
        if base.is_file():
            yield base
            continue
        for p in base.rglob('*'):
            if p.is_file() and p.suffix in EXTS and not (set(p.parts) & IGNORAR_PARTES) and p not in PERMITIDOS:
                yield p


def test_nenhum_termo_da_poc_em_codigo_e_testes():
    culpados = []
    for p in _arquivos():
        for n, linha in enumerate(p.read_text(encoding='utf8', errors='replace').splitlines(), 1):
            if PADRAO.search(linha):
                culpados.append(f'{p.relative_to(ROOT)}:{n}: {linha.strip()[:110]}')
    assert culpados == [], '\n'.join(culpados)
