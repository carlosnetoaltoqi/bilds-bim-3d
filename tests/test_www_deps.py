"""Dependências da API da POC coerentes (I12).

Até 2026-09-05 `@nestjs/mongoose@12` exigia Nest ^11||^12 sobre um Nest 10 instalado (peer
violada, sem aviso porque o pnpm só reporta na instalação), e havia dois drivers Mongo: o
`mongodb@6` do `health.controller.ts` e o `mongodb@7` que o `mongoose@9` embute. Agora
`@nestjs/mongoose` é 11 (peers ^10||^11), o pacote `mongodb` saiu de `apps/api`, o health
responde pela conexão do Mongoose e as ferramentas de `www/tools` usam `mongoose.mongo`.

Estes testes leem `package.json` e `pnpm-lock.yaml` — nada de rede — e acusam a volta de
qualquer uma das duas situações. Só Python.
"""
import json
import re
from pathlib import Path

from conftest import ROOT

WWW = ROOT / 'www'
API = WWW / 'apps' / 'api'
LOCK = (WWW / 'pnpm-lock.yaml').read_text(encoding='utf8')
PKG = json.loads((API / 'package.json').read_text(encoding='utf8'))


def _versao_instalada(nome):
    """Versão resolvida no importer apps/api do lockfile (ex.: '10.4.22')."""
    bloco = LOCK[LOCK.index('  apps/api:'):]
    m = re.search(rf"^      '?{re.escape(nome)}'?:\n        specifier: .*\n        version: (\d+\.\d+\.\d+)", bloco, flags=re.M)
    assert m, f'{nome} não está no importer apps/api do pnpm-lock.yaml'
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
    mongoose_nest = _versao_instalada('@nestjs/mongoose')
    peers = _peers('@nestjs/mongoose', mongoose_nest)
    for pacote in ('@nestjs/common', '@nestjs/core', 'mongoose'):
        instalado = _versao_instalada(pacote)
        assert _satisfaz(instalado, peers[pacote]), (
            f'@nestjs/mongoose@{mongoose_nest} exige {pacote} {peers[pacote]}, instalado {instalado}')


def test_platform_express_satisfaz_o_nest_instalado():
    v = _versao_instalada('@nestjs/platform-express')
    peers = _peers('@nestjs/platform-express', v)
    for pacote in ('@nestjs/common', '@nestjs/core'):
        assert _satisfaz(_versao_instalada(pacote), peers[pacote]), (pacote, peers[pacote], _versao_instalada(pacote))


def test_um_so_driver_mongo():
    assert 'mongodb' not in PKG['dependencies'] and 'mongodb' not in PKG.get('devDependencies', {}), \
        'o pacote mongodb voltou a apps/api — o mongoose já embute o driver'
    culpados = [str(p.relative_to(ROOT)) for base in (API / 'src', WWW / 'tools')
                for p in base.rglob('*.ts') if 'node_modules' not in p.parts and re.search(r"from ['\"]mongodb['\"]", p.read_text(encoding='utf8'))]
    assert culpados == [], f"import direto de 'mongodb' — use mongoose.mongo: {culpados}"


def test_health_responde_pela_conexao_do_mongoose():
    src = (API / 'src' / 'health' / 'health.controller.ts').read_text(encoding='utf8')
    assert '@InjectConnection()' in src and 'readyState' in src and 'ServiceUnavailableException' in src
    assert 'new MongoClient' not in src
