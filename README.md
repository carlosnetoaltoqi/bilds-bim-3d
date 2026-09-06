# bilds-bim-3d

Catálogos BIM com viewer 3D a partir de bibliotecas `.aq` do AltoQi Builder — e o caminho de volta:
escrever `.aq`, converter STEP/IGES/IFC, ler catálogos de plugins de CAD, gerar o ZIP que a bilds.com consome.

**Você só precisa do arquivo `.aq`.** Ele carrega a malha 3D, a cor e os dados de cada peça — não é
preciso ter os IFCs.

## Como o projeto é organizado

Uma **biblioteca Python comum** e **um serviço por contexto** (docs/arquitetura.md):

| Camada | O quê | Porta |
|---|---|---|
| `biblioteca/` — pacote `bim_pipeline` | ler/escrever `.aq` e OQ3D, geometria `{pos,col,idx}`, catálogo, miniaturas (Chromium), conversores CAD, escritor do ZIP. Stateless: arquivo entra, arquivo/JSON sai | — |
| `servicos/criador-de-catalogos` | importa `.aq`/`.zip`, peça CAD ou plugin de CAD; publica catálogo e produtos no Mongo, geometria e miniaturas no storage; exporta catálogo salvo → `.aq` | 4100 |
| `servicos/catalogo-api` | leitura: empresas, catálogos, produtos, geometria, miniaturas; remoção em cascata | 4000 |
| `servicos/editor-de-pecas` | edição: informações do produto, geometria (copy-on-write), restaurar | 4400 |
| `servicos/gerador-zip` | `.aq` → ZIP da bilds.com, stateless | 4200 |
| `servicos/conversores` | STEP/IGES/IFC → geometria; geometria → `.aq` de uma peça; DLL de plugin → catálogo web; stateless | 4300 |
| `web/` | páginas de catálogo, importação, `/cad` e o editor 3D — um cliente por serviço | 3000 |
| `pacotes/base`, `pacotes/dominio` | o que os serviços Nest compartilham (processo filho, porta para o Python, upload, validação, download; schemas Mongoose, storage, remoção) | — |

Cada serviço tem README próprio com as rotas. Decisões em `docs/decisoes/`; conhecimento sobre os
formatos em `docs/conhecimento/`; mapa para agentes em `CLAUDE.md`.

## Início rápido

```bash
git clone https://github.com/carlosnetoaltoqi/bilds-bim-3d.git && cd bilds-bim-3d
bash scripts/bootstrap.sh                 # pip install -e biblioteca, pnpm install, Playwright + three das miniaturas; --check só confere
sudo apt-get install -y libnss3 libnspr4 libasound2t64   # libs do Chromium — o único passo com sudo
```

### Só o ZIP para a bilds.com (sem serviços)

```bash
python3 -m bim_pipeline.cli.zip_bilds biblioteca.aq --saida saida.zip   # uma biblioteca
python3 -m bim_pipeline.cli.zip_bilds --all                                 # todas as de input/ → output/, espelhando as subpastas
python3 -m bim_pipeline.cli.zip_bilds --all --force                         # refaz as que já têm ZIP
python3 -m bim_pipeline.cli.zip_bilds --all --skip-thumbs                   # nem tenta miniaturas
python3 -m bim_pipeline.cli.zip_bilds --all --allow-no-thumbs               # tenta; se falhar, avisa e segue
```

Fabricante, título, slug e layout são inferidos do `.aq` e da pasta (`bim_pipeline.catalogo.inferencia`).
**Sem miniaturas a geração falha** (exit 1) — um ZIP sem `thumbs/` faz a página renderizar no browser
do visitante, dezenas de segundos de LCP. As duas flags são as saídas explícitas; `thumbCount` no
`manifest.json` registra o que saiu. `input/` e `output/` são gitignored.

### Os serviços e o web

```bash
cp .env.example .env                      # Mongo (qualquer MongoDB; Atlas tem whitelist de IP), STORAGE_PATH
pnpm dev                                  # compila os pacotes e sobe os cinco serviços + web
# ou um por vez: pnpm dev:criador | dev:catalogo | dev:editor | dev:zip | dev:conversores | dev:web
pnpm -r build && pnpm start:criador       # o mesmo, do dist/ (cada serviço tem start:<nome>)
```

Abrir http://localhost:3000 → importar uma biblioteca → ver o catálogo → editar uma peça →
**Gerar ZIP bilds.com** na home. Os serviços stateless (`gerador-zip`, `conversores`) sobem sem
`MONGODB_URI`. `dev:*` dos serviços Nest não tem watch — mudou TypeScript, reinicie o serviço.

## Ferramentas da biblioteca

```bash
python3 -m bim_pipeline.cli.read_aq pecas.aq --meta               # fabricante, linhas, peças, geometrias, schema
python3 -m bim_pipeline.cli.catalogo_de_aq pecas.aq --geo-dir /tmp/geo --saida /tmp/cat.json [--thumbs-dir /tmp/thumbs]
python3 -m bim_pipeline.cli.step_iges peca.stp saida.json          # CAD → geometria do viewer
python3 -m bim_pipeline.cli.familias_revit inspecionar familias.zip   # famílias Revit .rfa: tipos, categorias, type catalogs, geometria irmã
python3 -m bim_pipeline.cli.familias_revit importar familias.zip --geo-dir /tmp/geo --saida /tmp/cat.json   # → catálogo (geometria irmã ou forma representativa)
python3 -m bim_pipeline.cli.ferramentas.validar_aq gerado.aq      # um .aq gerado passa pelos leitores da biblioteca?
python3 -m bim_pipeline.cli.ferramentas.oq3d_anatomy pecas.aq 12  # dissecar um blob OQ3D byte a byte
```

Lista completa em `biblioteca/README.md`.

## Testes

```bash
python3 -m pytest                                   # ~170 testes, ≈ 4 min com Chromium
python3 -m pytest -m "not thumbs"                   # sem abrir o Chromium
python3 -m pytest tests/biblioteca                  # só a biblioteca (Python)
python3 -m pytest tests/arquitetura                 # as regras de fronteira, contratos, dependências, termos da POC
python3 -m pytest tests/servicos                    # harnesses Node dos serviços (ts-node), round-trips do editor
```

Fixtures reais são referenciadas por **papel** em `tests/fixtures.local.json` (gitignored; modelo em
`tests/fixtures.example.json`); sem elas os testes pulam com motivo. Roteiro de aceitação com os
serviços de pé em `docs/aceitacao.md`.

## Requisitos

`bash scripts/bootstrap.sh --check` confere e diz como corrigir cada linha (`--www` e `--cad` instalam os opcionais):

- Python 3.12 (`.python-version`): `pip install -r requirements.txt` (a biblioteca, em modo editável) e `requirements-dev.txt` (pytest, jsonschema)
- Node 24 (`.nvmrc`) e pnpm 11 (`packageManager`): `pnpm install` na raiz — **só pnpm**, `npm install` gera um lockfile que não é versionado
- miniaturas: `biblioteca/bim_pipeline/miniaturas/node_modules` (Playwright + three, instalado pelo workspace) + Chromium + `libnss3 libnspr4 libasound2t64`
- opcional (`requirements-cad.txt` ou `pip install -e 'biblioteca[cad]'`): `cadquery-ocp` (STEP/IGES), `ifcopenshell` (IFC B-rep e IFC grande), `pypdf` (`olefile`, das famílias Revit, já vem com a biblioteca)

⚠️ **Não use `sudo npx playwright install-deps`**: o `sudo` descarta o PATH do nvm e cai no Node do apt.
Use o `apt-get` acima, ou `sudo env "PATH=$PATH" npx playwright install-deps chromium`.

⚠️ **Dois Node na máquina** (apt e nvm): um subprocess pega o do apt e o Playwright recusa. A biblioteca
procura sozinha um Node ≥ 20 em `~/.nvm`; em outro lugar, `BILDS_NODE=/caminho/node`.

**Sem sudo?** Baixe os `.deb` (`apt-get download libnspr4 libnss3 libasound2t64`), extraia com
`dpkg-deb -x` numa pasta local e aponte `LD_LIBRARY_PATH` para `…/usr/lib/x86_64-linux-gnu`.

## Uma peça não apareceu no catálogo

Peças sem geometria no banco são puladas e a geração informa quantas: normalmente **tubos** (o AltoQi os
gera como cilindro a partir do diâmetro e do comprimento) e **kits** — entradas de projeto, não peças com
forma. Sai como `N peça(s) sem simbologia 3D (tubos/kits) puladas — esperado`.

Se em vez disso aparecer `AVISO: N simbologia(s) descartada(s)` ou `… com aviso de parse`, **não é tubo**:
a peça tem geometria e o leitor não conseguiu lê-la (blob nulo, sem assinatura OQ3D, truncado, sem malha,
ou layout que o `oq3d` não conhece). O aviso traz o id e o nome da simbologia — é a pista para corrigir o
leitor, não para ignorar. `docs/conhecimento/diagnostico.md` tem a tabela sintoma → causa.

## Documentação

- `docs/arquitetura.md` — as camadas, as sete regras de fronteira, quem grava o quê, o que cada contexto leva ao ser portado
- `docs/decisoes/` — ADR-001 a ADR-017
- `docs/conhecimento/` — formatos (`.aq`, OQ3D, IFC, STEP/IGES), geometria, catálogo, miniaturas, ZIP, processos filhos, diagnóstico
- `docs/skills/` — skills de agente sobre `.aq`, IFC, STEP e páginas de catálogo (`bash scripts/link_skills.sh` cria os symlinks em `~/.claude/skills/`)
- `docs/integracoes/bilds-com.md` — o upload do ZIP na bilds.com (endpoint, erros, upsert, URL)
- `docs/historico/` — registro arquivado (sessões, estudos, planos, spec original do ZIP); consulta pontual, **não carregar ao iniciar uma sessão**
- `CLAUDE.md` — mapa para quem trabalha no projeto
