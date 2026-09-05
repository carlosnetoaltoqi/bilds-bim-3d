"""Configuração de `www/` (I17): host, porta e storage vêm de UM lugar cada.

Até 2026-09-05 três páginas do web tinham `http://localhost:4000` fixo (ignoravam
`lib/api.ts`), a API escutava `listen(4000)` sem `PORT`, e `STORAGE_PATH` era resolvida em
quatro arquivos com dois defaults diferentes (logos numa pasta, geometria em outra). Desde a
E3 (S7.14) há três apps — API de catálogo (:4000), serviço de ingestão (:4100), web (:3000) —
e um pacote compartilhado (`packages/dominio`); a regra continua: o resolvedor de
`STORAGE_PATH` é um só (`dominio/src/storage-path.ts`), a API conhece o serviço só em
`common/ingestao-client.ts`, o web conhece as duas URLs só em `lib/api.ts`. Estes testes
leem o código-fonte e acusam a volta de qualquer atalho. O do resolvedor roda no Node
(marcador `paridade`).
"""
import json
import re
import subprocess

import pytest

from conftest import ROOT, node_para_ts

WWW = ROOT / 'www'
API_SRC = WWW / 'apps' / 'api' / 'src'
INGESTAO_SRC = WWW / 'apps' / 'ingestao' / 'src'
DOMINIO_SRC = WWW / 'packages' / 'dominio' / 'src'
WEB_SRC = WWW / 'apps' / 'web' / 'src'
STORAGE_PATH_TS = DOMINIO_SRC / 'storage-path.ts'
INGESTAO_CLIENT_TS = API_SRC / 'common' / 'ingestao-client.ts'
LIB_API = WEB_SRC / 'lib' / 'api.ts'


def _fontes(raiz):
    return [p for p in raiz.rglob('*') if p.suffix in ('.ts', '.tsx', '.mts') and 'node_modules' not in p.parts]


def test_web_so_lib_api_conhece_as_urls_dos_servicos():
    culpados = [str(p.relative_to(ROOT)) for p in _fontes(WEB_SRC)
                if p != LIB_API and re.search(r"https?://localhost:4[01]00", p.read_text(encoding='utf8'))]
    assert culpados == [], f'`localhost:4000`/`4100` fixo fora de lib/api.ts: {culpados}'
    lib = LIB_API.read_text(encoding='utf8')
    assert 'NEXT_PUBLIC_API_URL' in lib and 'process.env.API_URL' in lib


def test_api_so_o_cliente_conhece_o_servico_de_ingestao():
    culpados = [str(p.relative_to(ROOT)) for p in _fontes(API_SRC)
                if p != INGESTAO_CLIENT_TS and ('localhost:4100' in p.read_text(encoding='utf8') or 'INGESTAO_URL' in p.read_text(encoding='utf8'))]
    assert culpados == [], f'URL do serviço de ingestão fora de common/ingestao-client.ts: {culpados}'
    assert 'INGESTAO_URL' in INGESTAO_CLIENT_TS.read_text(encoding='utf8')
    # a API não roda Python nem Chromium — isso é do serviço (A2/A6)
    culpados = [str(p.relative_to(ROOT)) for p in _fontes(API_SRC)
                if re.search(r"child_process|playwright|python3", p.read_text(encoding='utf8'))]
    assert culpados == [], f'a API voltou a rodar processo filho: {culpados}'


def test_storage_path_resolvida_so_em_storage_path_ts():
    culpados = [str(p.relative_to(ROOT)) for raiz in (API_SRC, INGESTAO_SRC, DOMINIO_SRC) for p in _fontes(raiz)
                if p != STORAGE_PATH_TS and 'process.env.STORAGE_PATH' in p.read_text(encoding='utf8')]
    assert culpados == [], f'STORAGE_PATH resolvida fora de dominio/src/storage-path.ts: {culpados}'
    # e quem precisa da raiz usa o resolvedor
    for arq in (DOMINIO_SRC / 'geometry-store' / 'disk-geometry-store.ts',
                INGESTAO_SRC / 'importacoes' / 'importacoes.service.ts',
                API_SRC / 'empresas' / 'empresas.controller.ts'):
        assert 'storagePath()' in arq.read_text(encoding='utf8'), arq


def test_cada_servico_escuta_na_porta_do_env():
    main = (API_SRC / 'main.ts').read_text(encoding='utf8')
    assert 'process.env.PORT' in main and 'app.listen(PORT)' in main
    assert not re.search(r'listen\(\s*4000\s*\)', main)
    main_ing = (INGESTAO_SRC / 'main.ts').read_text(encoding='utf8')
    assert 'process.env.INGESTAO_PORT' in main_ing and 'app.listen(PORT)' in main_ing
    assert not re.search(r'listen\(\s*4100\s*\)', main_ing)
    env = (WWW / '.env.example').read_text(encoding='utf8')
    assert 'PORT=4000' in env and 'INGESTAO_PORT=4100' in env and 'INGESTAO_URL=' in env


def test_pipeline_dir_resolvido_so_no_pipeline_service():
    culpados = [str(p.relative_to(ROOT)) for p in _fontes(INGESTAO_SRC)
                if p.name != 'pipeline.service.ts' and 'PIPELINE_DIR' in p.read_text(encoding='utf8')]
    assert culpados == [], culpados
    svc = (INGESTAO_SRC / 'pipeline' / 'pipeline.service.ts').read_text(encoding='utf8')
    assert 'process.env.PYTHON' in svc and "'--sair-com-stdin'" in svc and 'sairComStdin: true' in svc


@pytest.mark.paridade
def test_storage_path_resolve_relativo_ao_cwd_com_e_sem_variavel():
    node = node_para_ts()
    if not node:
        pytest.skip('precisa de Node >= 22 para importar o storage-path.ts')
    script = (
        f"import('{STORAGE_PATH_TS.as_posix()}').then(m => console.log(JSON.stringify(["
        "m.storagePath({}, '/srv/api'),"
        "m.storagePath({STORAGE_PATH: '../../storage/bim'}, '/repo/www/apps/api'),"
        "m.storagePath({STORAGE_PATH: '../../storage/bim'}, '/repo/www/apps/ingestao'),"
        "m.storagePath({STORAGE_PATH: '/abs/storage'}, '/qualquer'),"
        "m.storagePathDefinido({}), m.storagePathDefinido({STORAGE_PATH: 'x'})])))"
    )
    proc = subprocess.run([node, '--no-warnings', '--experimental-strip-types', '-e', script],
                          capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert proc.returncode == 0, proc.stderr[-2000:]
    # os dois serviços, com o mesmo valor relativo do .env.example, caem na MESMA pasta
    assert json.loads(proc.stdout) == ['/srv/api/storage', '/repo/www/storage/bim', '/repo/www/storage/bim', '/abs/storage', False, True]


def test_nome_do_arquivo_enviado_volta_a_utf8():
    """S7.13: o multer 2.0.2 embutido no Nest 10 lê o `filename` do multipart como latin1 (e não
    conhece `defParamCharset`) — `gás.aq` virava `gÃ¡s.aq` no log, no `fileName` do import e no
    nome do produto CAD. `dominio/src/upload.ts` refaz a decodificação com guarda de ida e volta."""
    node = node_para_ts()
    if not node:
        pytest.skip('precisa de Node >= 22')
    proc = subprocess.run([node, '--no-warnings', '--experimental-strip-types', str(ROOT / 'tests' / 'paridade' / 'upload_nome.mts')],
                          capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert proc.returncode == 0, proc.stderr[-2000:]
    r = json.loads(proc.stdout)
    assert r == {
        'mojibake_corrigido': 'pecas_komeco_aquecimento_agua_a_gás.aq',
        'ascii_intacto': 'pecas_dancor_bombas_incendio_2026_04.1.aq',
        'ja_correto_intacto': 'peça — gás.stp',
        'fora_do_latin1_intacto': 'peça — x.ifc',
        'ausente_usa_padrao': 'upload.aq',
        'vazio_usa_padrao': 'upload.aq',
    }


def test_originalname_so_e_guardado_via_nome_original_utf8():
    """Guarda de regressão: todo `originalname` que vira nome (não só extensão) passa por `nomeOriginalUtf8`."""
    culpados = []
    for raiz in (API_SRC, INGESTAO_SRC):
        for p in _fontes(raiz):
            for n, linha in enumerate(p.read_text(encoding='utf8').splitlines(), 1):
                if '.originalname' in linha and not any(ok in linha for ok in ('nomeOriginalUtf8(', 'extname(', 'inferExt(')):
                    culpados.append(f'{p.relative_to(ROOT)}:{n}: {linha.strip()}')
    assert culpados == [], culpados
