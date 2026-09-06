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

API_SRC = ROOT / 'servicos' / 'catalogo-api' / 'src'
INGESTAO_SRC = ROOT / 'servicos' / 'criador-de-catalogos' / 'src'
DOMINIO_SRC = ROOT / 'pacotes' / 'dominio' / 'src'
BASE_SRC = ROOT / 'pacotes' / 'base' / 'src'
WEB_SRC = ROOT / 'web' / 'src'
STORAGE_PATH_TS = DOMINIO_SRC / 'storage-path.ts'
EDITOR_SRC = ROOT / 'servicos' / 'editor-de-pecas' / 'src'
CRIADOR_CLIENT_TS = EDITOR_SRC / 'criador-client.ts'
LIB_API = WEB_SRC / 'servicos' / 'catalogo.ts'


def _fontes(raiz):
    return [p for p in raiz.rglob('*') if p.suffix in ('.ts', '.tsx', '.mts') and 'node_modules' not in p.parts]


SERVICOS_WEB = WEB_SRC / 'servicos'


def test_web_um_cliente_por_servico():
    """Regra 5 de docs/arquitetura.md §3: cada serviço tem UM cliente no web (lib/api.ts para API e criador;
    src/servicos/<nome>.ts para os demais) e nenhuma URL fixa mora fora deles."""
    clientes = set(SERVICOS_WEB.glob('*.ts'))
    culpados = [str(p.relative_to(ROOT)) for p in _fontes(WEB_SRC)
                if p not in clientes and re.search(r"https?://localhost:4[0-9]00", p.read_text(encoding='utf8'))]
    assert culpados == [], f'URL de serviço fixa fora dos clientes: {culpados}'
    for nome, porta, env in (('catalogo', 4000, 'CATALOGO_URL'), ('criador', 4100, 'CRIADOR_URL'), ('zip', 4200, 'ZIP_URL'), ('conversores', 4300, 'CONVERSORES_URL'), ('editor', 4400, 'EDITOR_URL')):
        cli = (SERVICOS_WEB / f'{nome}.ts').read_text(encoding='utf8')
        assert f'localhost:{porta}' in cli and f'NEXT_PUBLIC_{env}' in cli and f'process.env.{env}' in cli
    # o cliente de um serviço não importa o de outro, e cada URL aparece num cliente só
    for c in clientes:
        codigo = '\n'.join(l for l in c.read_text(encoding='utf8').splitlines() if not l.lstrip().startswith(('*', '/*', '//')))
        assert codigo.count("'http://localhost:4") == 1, c
    # o web não tem rotas-proxy nem login (ADR-007): tudo vai direto aos serviços
    assert not (WEB_SRC / 'app' / 'api').exists() and not (WEB_SRC / 'middleware.ts').exists()


def test_servicos_stateless_nao_conhecem_dados():
    """Regra 3: gerador-zip e conversores não importam @bim/dominio, não têm Mongoose, não leem STORAGE_PATH."""
    for servico in ('gerador-zip', 'conversores'):
        raiz = ROOT / 'servicos' / servico
        pkg = json.loads((raiz / 'package.json').read_text(encoding='utf8'))
        assert '@bim/dominio' not in pkg['dependencies'] and 'mongoose' not in pkg['dependencies'] and '@nestjs/mongoose' not in pkg['dependencies'], servico
        for p in _fontes(raiz / 'src'):
            txt = p.read_text(encoding='utf8')
            assert not re.search(r"from '@bim/dominio'|from '@nestjs/mongoose'|MongooseModule\.for|process\.env\.STORAGE_PATH|storagePath\(", txt), p
        main = (raiz / 'src' / 'main.ts').read_text(encoding='utf8')
        assert 'iniciarServico(' in main and ('ZIP_PORT' in main or 'CONVERSORES_PORT' in main)


def test_api_nao_conhece_outros_servicos_e_so_o_editor_fala_com_o_criador():
    culpados = [str(p.relative_to(ROOT)) for p in _fontes(API_SRC)
                if re.search(r"localhost:4[1-9]00|CRIADOR_URL|INGESTAO_URL|fetch\(", p.read_text(encoding='utf8'))]
    assert culpados == [], f'a API de catálogo fala com outro serviço: {culpados}'
    culpados = [str(p.relative_to(ROOT)) for p in _fontes(EDITOR_SRC)
                if p != CRIADOR_CLIENT_TS and ('localhost:4100' in p.read_text(encoding='utf8') or 'CRIADOR_URL' in p.read_text(encoding='utf8'))]
    assert culpados == [], f'URL do criador fora de criador-client.ts: {culpados}'
    assert 'CRIADOR_URL' in CRIADOR_CLIENT_TS.read_text(encoding='utf8')
    # a API não roda Python nem Chromium — isso é do serviço (A2/A6)
    culpados = [str(p.relative_to(ROOT)) for p in _fontes(API_SRC)
                if re.search(r"child_process|playwright|python3", p.read_text(encoding='utf8'))]
    assert culpados == [], f'a API voltou a rodar processo filho: {culpados}'


def test_storage_path_resolvida_so_em_storage_path_ts():
    culpados = [str(p.relative_to(ROOT)) for raiz in (API_SRC, INGESTAO_SRC, EDITOR_SRC, DOMINIO_SRC, BASE_SRC) for p in _fontes(raiz)
                if p != STORAGE_PATH_TS and 'process.env.STORAGE_PATH' in p.read_text(encoding='utf8')]
    assert culpados == [], f'STORAGE_PATH resolvida fora de dominio/src/storage-path.ts: {culpados}'
    # e quem precisa da raiz usa o resolvedor
    for arq in (DOMINIO_SRC / 'geometry-store' / 'disk-geometry-store.ts',
                INGESTAO_SRC / 'publicacao' / 'publicacao.service.ts'):
        assert 'storagePath()' in arq.read_text(encoding='utf8'), arq
    # e ninguém escreve no storage por fora do IGeometryStore (S8/F4: o logo era o último)
    culpados = [str(p.relative_to(ROOT)) for raiz in (API_SRC, INGESTAO_SRC, EDITOR_SRC) for p in _fontes(raiz)
                if re.search(r"writeFileSync|readFileSync|fs\.writeFile\(|createWriteStream", p.read_text(encoding='utf8'))]
    assert culpados == [], f'escrita no storage por fora do IGeometryStore: {culpados}'


def test_cada_servico_escuta_na_porta_do_env():
    main = (API_SRC / 'main.ts').read_text(encoding='utf8')
    assert "envPorta: 'CATALOGO_PORT'" in main and 'iniciarServico(' in main
    main_ing = (INGESTAO_SRC / 'main.ts').read_text(encoding='utf8')
    assert "envPorta: 'CRIADOR_PORT'" in main_ing and 'iniciarServico(' in main_ing
    for m in (main, main_ing):
        assert not re.search(r'listen\(\s*4[01]00\s*\)', m)
    env = (ROOT / '.env.example').read_text(encoding='utf8')
    for chave in ('CATALOGO_PORT=4000', 'CRIADOR_PORT=4100', 'ZIP_PORT=4200', 'CONVERSORES_PORT=4300', 'EDITOR_PORT=4400', 'CRIADOR_URL=', 'NEXT_PUBLIC_CATALOGO_URL='):
        assert chave in env, chave


def test_biblioteca_alcancada_so_pela_base():
    """Regra 2 de docs/arquitetura.md §3: só `pacotes/base/src/biblioteca-cli.ts` sabe onde a biblioteca
    está (BIBLIOTECA_DIR), qual Python roda e como uma CLI se chama; nenhum serviço spawna processo."""
    cli_ts = BASE_SRC / 'biblioteca-cli.ts'
    culpados = [str(p.relative_to(ROOT)) for raiz in (API_SRC, INGESTAO_SRC, DOMINIO_SRC, BASE_SRC, ROOT / 'servicos') for p in _fontes(raiz)
                if p != cli_ts and re.search(r"BIBLIOTECA_DIR|process\.env\.PYTHON|bim_pipeline\.cli", p.read_text(encoding='utf8'))]
    assert culpados == [], culpados
    culpados = [str(p.relative_to(ROOT)) for raiz in (API_SRC, INGESTAO_SRC, DOMINIO_SRC, ROOT / 'servicos') for p in _fontes(raiz)
                if re.search(r"child_process|spawn\(", p.read_text(encoding='utf8'))]
    assert culpados == [], f'processo filho fora de pacotes/base: {culpados}'
    cli = cli_ts.read_text(encoding='utf8')
    assert 'process.env.PYTHON' in cli and 'BIBLIOTECA_DIR' in cli and 'bim_pipeline.cli.' in cli
    svc = (BASE_SRC / 'biblioteca.ts').read_text(encoding='utf8')
    assert "'--sair-com-stdin'" in svc and 'sairComStdin: true' in svc and 'extends BibliotecaCli' in svc


@pytest.mark.paridade
def test_storage_path_resolve_relativo_ao_cwd_com_e_sem_variavel():
    node = node_para_ts()
    if not node:
        pytest.skip('precisa de Node >= 22 para importar o storage-path.ts')
    script = (
        f"import('{STORAGE_PATH_TS.as_posix()}').then(m => console.log(JSON.stringify(["
        "m.storagePath({}, '/srv/api'),"
        "m.storagePath({STORAGE_PATH: '../../storage/bim'}, '/repo/servicos/catalogo-api'),"
        "m.storagePath({STORAGE_PATH: '../../storage/bim'}, '/repo/servicos/criador-de-catalogos'),"
        "m.storagePath({STORAGE_PATH: '/abs/storage'}, '/qualquer'),"
        "m.storagePathDefinido({}), m.storagePathDefinido({STORAGE_PATH: 'x'})])))"
    )
    proc = subprocess.run([node, '--no-warnings', '--experimental-strip-types', '-e', script],
                          capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert proc.returncode == 0, proc.stderr[-2000:]
    # os dois serviços, com o mesmo valor relativo do .env.example, caem na MESMA pasta
    assert json.loads(proc.stdout) == ['/srv/api/storage', '/repo/storage/bim', '/repo/storage/bim', '/abs/storage', False, True]


def test_nome_do_arquivo_enviado_volta_a_utf8():
    """S7.13: o multer 2.0.2 embutido no Nest 10 lê o `filename` do multipart como latin1 (e não
    conhece `defParamCharset`) — `gás.aq` virava `gÃ¡s.aq` no log, no `fileName` do import e no
    nome do produto CAD. `pacotes/base/src/upload.ts` refaz a decodificação com guarda de ida e volta."""
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
    for raiz in (API_SRC, INGESTAO_SRC, EDITOR_SRC, BASE_SRC):
        for p in _fontes(raiz):
            for n, linha in enumerate(p.read_text(encoding='utf8').splitlines(), 1):
                if '.originalname' in linha and not any(ok in linha for ok in ('nomeOriginalUtf8(', 'extname(', 'inferExt(')):
                    culpados.append(f'{p.relative_to(ROOT)}:{n}: {linha.strip()}')
    assert culpados == [], culpados
