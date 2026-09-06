"""Regra 1 de docs/arquitetura.md §3: a biblioteca não importa nada de fora de `bim_pipeline`, não conhece
Mongo, HTTP de serviço nem caminhos do repositório; toda CLI que um serviço roda aceita `--sair-com-stdin`."""
import re

from conftest import PIPELINE


def test_biblioteca_nao_importa_de_fora_de_si():
    culpados = []
    for p in sorted(PIPELINE.rglob('*.py')):
        for n, linha in enumerate(p.read_text(encoding='utf8').splitlines(), 1):
            linha = linha.split('#', 1)[0]      # só o código: comentários podem citar a origem
            if re.match(r'\s*(import|from)\s+\w', linha) and re.search(r'servicos|pacotes|historico|docs|estudos', linha):
                culpados.append(f'{p.relative_to(PIPELINE)}:{n}: {linha.strip()}')
            if 'sys.path.insert' in linha and 'tests' not in str(p):
                culpados.append(f'{p.relative_to(PIPELINE)}:{n}: {linha.strip()}')
    assert culpados == [], culpados
    assert (PIPELINE / 'aq' / 'schema-aq-607.sql').is_file() and (PIPELINE / 'aq' / 'aq_writer.py').is_file() and (PIPELINE / 'aq' / 'oq3d_writer.py').is_file()


def test_biblioteca_nao_conhece_mongo_nem_servicos():
    culpados = []
    for p in sorted(PIPELINE.rglob('*.py')):
        for n, linha in enumerate(p.read_text(encoding='utf8').splitlines(), 1):
            codigo = linha.split('#', 1)[0]
            if re.search(r"\b(pymongo|motor\.motor|mongoose|MONGODB_URI|localhost:4[0-9]00|STORAGE_PATH|servicos/|www/)", codigo):
                culpados.append(f'{p.relative_to(PIPELINE)}:{n}: {codigo.strip()}')
    assert culpados == [], culpados


def test_clis_dos_servicos_aceitam_sair_com_stdin():
    for nome in ('catalogo_de_aq', 'zip_bilds', 'plugin_catalogo_web'):
        fonte = (PIPELINE / 'cli' / f'{nome}.py').read_text(encoding='utf8')
        alvo = fonte
        m = re.search(r"run_module\('([\w.]+)'", fonte)      # wrapper → o módulo real
        if m:
            alvo = (PIPELINE / (m.group(1).split('bim_pipeline.', 1)[1].replace('.', '/') + '.py')).read_text(encoding='utf8')
        assert '--sair-com-stdin' in alvo and 'vigiar_stdin' in alvo, nome
