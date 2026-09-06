"""Dependências dos apps de `www/` coerentes (I12, estendido na E3).

Até 2026-09-05 `@nestjs/mongoose@12` exigia Nest ^11||^12 sobre um Nest 10 instalado (peer
violada, sem aviso porque o pnpm só reporta na instalação), e havia dois drivers Mongo: o
`mongodb@6` do `health.controller.ts` e o `mongodb@7` que o `mongoose@9` embute. Desde a E3
há três importers no lockfile — `apps/api`, `apps/ingestao` e `packages/dominio` — e eles têm
de resolver as MESMAS versões de Nest e Mongoose: o `@bim/dominio` é fonte TypeScript compilada
dentro de cada app, e duas cópias de `@nestjs/common` ou de `mongoose` quebrariam a injeção e
os schemas em silêncio.

Estes testes leem `package.json` e `pnpm-lock.yaml` — nada de rede. Só Python.
"""
import json
import re

from conftest import ROOT

API = ROOT / 'servicos' / 'catalogo-api'
INGESTAO = ROOT / 'servicos' / 'criador-de-catalogos'
WEB = ROOT / 'web'
DOMINIO = ROOT / 'pacotes' / 'dominio'
BASE = ROOT / 'pacotes' / 'base'
LOCK = (ROOT / 'pnpm-lock.yaml').read_text(encoding='utf8')     # um só lockfile, na raiz (S8/F2)
IMPORTERS = ('servicos/catalogo-api', 'servicos/criador-de-catalogos', 'servicos/editor-de-pecas', 'pacotes/dominio', 'pacotes/base', 'servicos/gerador-zip', 'servicos/conversores')


def _bloco_importer(importer):
    i = LOCK.index(f'  {importer}:\n')
    resto = LOCK[i + len(importer) + 4:]
    m = re.search(r'^  \S', resto, flags=re.M)     # próximo importer (indentação 2)
    return resto[: m.start()] if m else resto


def _versao_instalada(nome, importer='servicos/catalogo-api'):
    """Versão resolvida no importer do lockfile (ex.: '10.4.22')."""
    bloco = _bloco_importer(importer)
    m = re.search(rf"^      '?{re.escape(nome)}'?:\n        specifier: .*\n        version: (\d+\.\d+\.\d+)", bloco, flags=re.M)
    assert m, f'{nome} não está no importer {importer} do pnpm-lock.yaml'
    return m.group(1)


def _peers(nome, versao):
    """peerDependencies declaradas no lockfile para `nome@versao`."""
    m = re.search(rf"^  '?{re.escape(nome)}@{re.escape(versao)}'?:\n(?:    .*\n)*?    peerDependencies:\n((?:      .*\n)+)", LOCK, flags=re.M)
    assert m, f'{nome}@{versao} sem peerDependencies no lockfile'
    return dict(re.findall(r"^      '?([^':\s]+)'?: (.+)$", m.group(1), flags=re.M))


def _satisfaz(versao, faixa):
    """Só o que precisamos: faixas `^N.x.y` unidas por `||` — compara o major."""
    major = int(versao.split('.')[0])
    majors = {int(x) for x in re.findall(r'\^(\d+)\.', faixa)}
    assert majors, f'faixa não reconhecida: {faixa}'
    return major in majors


def test_nestjs_mongoose_satisfaz_o_nest_instalado():
    for importer in ('servicos/catalogo-api', 'servicos/criador-de-catalogos'):
        mongoose_nest = _versao_instalada('@nestjs/mongoose', importer)
        peers = _peers('@nestjs/mongoose', mongoose_nest)
        for pacote in ('@nestjs/common', '@nestjs/core', 'mongoose'):
            instalado = _versao_instalada(pacote, importer)
            assert _satisfaz(instalado, peers[pacote]), (
                f'{importer}: @nestjs/mongoose@{mongoose_nest} exige {pacote} {peers[pacote]}, instalado {instalado}')


def test_platform_express_satisfaz_o_nest_instalado():
    for importer in ('servicos/catalogo-api', 'servicos/criador-de-catalogos'):
        v = _versao_instalada('@nestjs/platform-express', importer)
        peers = _peers('@nestjs/platform-express', v)
        for pacote in ('@nestjs/common', '@nestjs/core'):
            assert _satisfaz(_versao_instalada(pacote, importer), peers[pacote]), (importer, pacote, peers[pacote])


def test_os_tres_importers_resolvem_as_mesmas_versoes():
    """Uma só cópia de Nest, Mongoose e class-validator: o dominio é compilado dentro de cada app."""
    for pacote in ('@nestjs/common', 'class-validator', 'class-transformer', 'reflect-metadata'):
        versoes = {imp: _versao_instalada(pacote, imp) for imp in IMPORTERS}
        assert len(set(versoes.values())) == 1, f'{pacote} resolvido em versões diferentes: {versoes}'
    for pacote in ('@nestjs/mongoose', 'mongoose'):
        versoes = {imp: _versao_instalada(pacote, imp) for imp in ('servicos/catalogo-api', 'servicos/criador-de-catalogos', 'servicos/editor-de-pecas', 'pacotes/dominio')}
        assert len(set(versoes.values())) == 1, f'{pacote} resolvido em versões diferentes: {versoes}'
    for pacote in ('@nestjs/core', '@nestjs/platform-express', 'multer'):
        # o editor não recebe upload: não declara multer
        imps = [i for i in ('servicos/catalogo-api', 'servicos/criador-de-catalogos', 'servicos/editor-de-pecas', 'pacotes/base', 'servicos/gerador-zip', 'servicos/conversores') if not (pacote == 'multer' and i == 'servicos/editor-de-pecas')]
        versoes = {imp: _versao_instalada(pacote, imp) for imp in imps}
        assert len(set(versoes.values())) == 1, f'{pacote}: {versoes}'


EDITOR = ROOT / 'servicos' / 'editor-de-pecas'


def test_dominio_e_dependencia_dos_dois_apps_e_so_deles():
    for app in (API, INGESTAO, EDITOR):
        pkg = json.loads((app / 'package.json').read_text(encoding='utf8'))
        assert pkg['dependencies'].get('@bim/dominio') == 'workspace:*', app
        assert pkg['dependencies'].get('@bim/base') == 'workspace:*', app
    base = json.loads((BASE / 'package.json').read_text(encoding='utf8'))
    assert '@bim/dominio' not in base['dependencies'] and 'mongoose' not in base['dependencies'], 'a base não sabe de Mongo'
    web = json.loads((WEB / 'package.json').read_text(encoding='utf8'))
    assert '@bim/dominio' not in web.get('dependencies', {}), 'o web não consome schemas do Mongo — fala com a API'


def test_um_so_driver_mongo():
    for base in (API, INGESTAO, EDITOR, DOMINIO, BASE):
        pkg = json.loads((base / 'package.json').read_text(encoding='utf8'))
        assert 'mongodb' not in pkg.get('dependencies', {}) and 'mongodb' not in pkg.get('devDependencies', {}), \
            f'o pacote mongodb voltou a {base.relative_to(ROOT)} — o mongoose já embute o driver'
    culpados = [str(p.relative_to(ROOT)) for base in (API / 'src', INGESTAO / 'src', EDITOR / 'src', DOMINIO / 'src', BASE / 'src', WEB / 'tools')
                for p in base.rglob('*.ts') if 'node_modules' not in p.parts and re.search(r"from ['\"]mongodb['\"]", p.read_text(encoding='utf8'))]
    assert culpados == [], f"import direto de 'mongodb' — use mongoose.mongo: {culpados}"


def test_health_responde_pela_conexao_do_mongoose():
    for app, arq in ((API, 'health/health.controller.ts'), (INGESTAO, 'health/health.controller.ts'), (EDITOR, 'health.controller.ts')):
        src = (app / 'src' / arq).read_text(encoding='utf8')
        assert '@InjectConnection()' in src and 'readyState' in src and 'ServiceUnavailableException' in src, app
        assert 'new MongoClient' not in src


def test_nenhum_parser_em_typescript():
    """A2: o `.aq`/OQ3D é lido só pelo Python do pipeline — o port TS saiu na E3."""
    for base in (API / 'src', INGESTAO / 'src', EDITOR / 'src', DOMINIO / 'src', BASE / 'src', WEB / 'tools'):
        for p in base.rglob('*.ts'):
            if 'node_modules' in p.parts:
                continue
            txt = p.read_text(encoding='utf8')
            assert 'node:sqlite' not in txt and 'DatabaseSync' not in txt and '0x5B' not in txt, f'{p.relative_to(ROOT)} lê .aq/OQ3D em TypeScript'
