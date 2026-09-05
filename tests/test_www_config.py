"""Configuração da POC `www/` (I17): host, porta e storage vêm de UM lugar cada.

Até 2026-09-05 três páginas do web tinham `http://localhost:4000` fixo (ignoravam
`lib/api.ts`), a API escutava `listen(4000)` sem `PORT`, e `STORAGE_PATH` era resolvida em
quatro arquivos com dois defaults diferentes (logos numa pasta, geometria em outra). Estes
testes são guardas de regressão: leem o código-fonte e acusam a volta de qualquer um dos três.
O último roda o resolvedor real no Node (marcador `paridade`).
"""
import json
import re
import subprocess

import pytest

from conftest import ROOT, node_para_ts

WWW = ROOT / 'www'
API_SRC = WWW / 'apps' / 'api' / 'src'
WEB_SRC = WWW / 'apps' / 'web' / 'src'
STORAGE_PATH_TS = API_SRC / 'common' / 'storage-path.ts'
LIB_API = WEB_SRC / 'lib' / 'api.ts'


def _fontes(raiz):
    return [p for p in raiz.rglob('*') if p.suffix in ('.ts', '.tsx', '.mts') and 'node_modules' not in p.parts]


def test_web_so_lib_api_conhece_localhost_4000():
    culpados = [str(p.relative_to(ROOT)) for p in _fontes(WEB_SRC)
                if p != LIB_API and re.search(r"https?://localhost:4000", p.read_text(encoding='utf8'))]
    assert culpados == [], f'`localhost:4000` fixo fora de lib/api.ts: {culpados}'
    lib = LIB_API.read_text(encoding='utf8')
    assert 'NEXT_PUBLIC_API_URL' in lib and 'process.env.API_URL' in lib


def test_api_le_storage_path_so_em_storage_path_ts():
    culpados = [str(p.relative_to(ROOT)) for p in _fontes(API_SRC)
                if p != STORAGE_PATH_TS and 'process.env.STORAGE_PATH' in p.read_text(encoding='utf8')]
    assert culpados == [], f'STORAGE_PATH resolvida fora de common/storage-path.ts: {culpados}'
    # e quem precisa da raiz usa o resolvedor
    for rel in ('geometry-store/disk-geometry-store.ts', 'importacoes/parse-worker.ts',
                'importacoes/importacoes.service.ts', 'empresas/empresas.controller.ts'):
        assert 'storagePath()' in (API_SRC / rel).read_text(encoding='utf8'), rel


def test_api_escuta_na_porta_do_env():
    main = (API_SRC / 'main.ts').read_text(encoding='utf8')
    assert 'process.env.PORT' in main and 'app.listen(PORT)' in main
    assert not re.search(r'listen\(\s*4000\s*\)', main)
    assert 'PORT=4000' in (WWW / '.env.example').read_text(encoding='utf8')


@pytest.mark.paridade
def test_storage_path_resolve_relativo_ao_cwd_com_e_sem_variavel():
    node = node_para_ts()
    if not node:
        pytest.skip('precisa de Node >= 22 para importar o storage-path.ts')
    script = (
        f"import('{STORAGE_PATH_TS.as_posix()}').then(m => console.log(JSON.stringify(["
        "m.storagePath({}, '/srv/api'),"
        "m.storagePath({STORAGE_PATH: '../../storage/bim'}, '/repo/www/apps/api'),"
        "m.storagePath({STORAGE_PATH: '/abs/storage'}, '/qualquer'),"
        "m.storagePathDefinido({}), m.storagePathDefinido({STORAGE_PATH: 'x'})])))"
    )
    proc = subprocess.run([node, '--no-warnings', '--experimental-strip-types', '-e', script],
                          capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert json.loads(proc.stdout) == ['/srv/api/storage', '/repo/www/storage/bim', '/abs/storage', False, True]
