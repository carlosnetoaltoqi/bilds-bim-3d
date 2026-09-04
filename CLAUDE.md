# CLAUDE.md — bilds-bim-3d

Ponto de entrada para qualquer agente ou humano que trabalhe neste projeto. É um **mapa**:
diz o que o projeto é, como rodar, onde está cada conhecimento e onde a última sessão parou.
O conhecimento em si mora em `docs/conhecimento/`, `www/README.md`, `docs/sessoes/` e nas
skills — este arquivo aponta, não repete. (Até 2026-09-04 tinha 3.086 linhas, 41% histórico;
a S7.8 o reescreveu — item I22 de `docs/auditoria-2026-09-03-pendencias.md`.)

---

## Regra fundamental: documentação primeiro

Se a informação não está no repositório, ela não existe para o próximo agente. Memória de
agente e skills fora do repo são auxiliares. **Toda sessão termina assim:**

1. Código corrigido e commitado — **um commit por item**, com o teste em `tests/` no mesmo
   commit quando há comportamento novo.
2. Registro da sessão em `docs/sessoes/S<id>-<slug>.md` (copiar `docs/sessoes/TEMPLATE.md`),
   com "o que foi verificado e como" e "onde a próxima sessão começa".
3. O bloco **"Fase atual"** abaixo atualizado; o conhecimento novo vai para o arquivo certo
   de `docs/conhecimento/` (ou `www/README.md` se for da POC) — nunca para cá.
4. Se aprendeu algo sobre `.aq`, IFC, STEP ou páginas de catálogo, a **skill** correspondente
   em `docs/skills/` recebe a linha e o bump de `version` + entrada no `## Histórico` dela.
   Na prática isso entra no commit `docs:` de fechamento da sessão, não no commit do fix
   (a regra antiga dizia "mesmo commit" e nunca foi cumprida — I24).
5. Se algo aqui ou em `docs/` se mostrou falso, corrigir **no documento de origem**, não
   acrescentar uma nota "versões antigas diziam…".

## Onde está cada conhecimento

| Assunto | Onde |
|---|---|
| Usar o pipeline: modos, opções, saída, requisitos, uma peça que não apareceu | `README.md` |
| Preparar/conferir a máquina | `bash scripts/bootstrap.sh --check` e a seção "Pré-requisitos" abaixo |
| Fluxo, `config.json`, `catalog.json`, layouts, conteúdo do ZIP, miniaturas, matching IFC → `.aq`, integração bilds.com | `docs/conhecimento/pipeline-estatico.md` |
| Formato binário **OQ3D** (cabeçalho, classes, instâncias, unidades, escrever) | `docs/conhecimento/oq3d.md` + docstring de `scripts/oq3d.py` + skill `leitor-biblioteca-aq` |
| Schema do `.aq`, **cp1252**, sentinelas, `DIAMETRO_PECA` é código, escrever `.aq` | `docs/conhecimento/read-aq.md` + skill `leitor-biblioteca-aq` |
| IFC4 → geometria (só modo `--ifc` e conversor CAD) | `docs/conhecimento/parse-ifc.md` + skill `leitor-ifc` |
| STEP → malha (OpenCASCADE), armadilhas de segfault | skill `docs/skills/leitor-step/` + `scripts/step_to_geo.py` |
| Templates HTML, Three.js self-hosted, escape, design tokens | `docs/conhecimento/templates-html.md` + skill `pagina-biblioteca` |
| **Sintoma → causa** (tabela de diagnóstico, ~70 linhas) | `docs/conhecimento/diagnostico.md` |
| Contrato do ZIP consumido pela bilds.com | `docs/bilds-bim-3d-zip-spec.md` |
| **POC `www/`** (NestJS + Next + Mongo): subir, rotas, **estado da base** (única versão válida), POC de edição, `.env`, Atlas, pendências | `www/README.md` |
| Aprendizados da POC dinâmica (ADRs, diretrizes para a reconstrução na bilds.com) | `docs/solutions/architecture-patterns/` |
| Planos históricos | `docs/plano-produto-dinamico.md`, `docs/plano-integracao-bilds.md`, `docs/plans/` — **históricos**, não guiam nada |
| O que a bilds.com recebe deste pipeline (lado consumidor) | `docs/saida-bilds-com/pipeline-bim-dinamico-na-bilds-com.md` |
| Como a geometria do `.aq` foi descoberta e validada | `docs/estudo-oq3d/` |
| **Escrever** `.aq`/OQ3D do zero; catálogo a partir de PDF | `eng-reversa/README.md` |
| Vocabulário (OQ3D, Import, Parte, Bake, sentinela, código de diâmetro…) | `CONCEPTS.md` |
| **Pendências de sistema e ordem de ataque** (C1–C10, I1–I25, L1–L14) | `docs/auditoria-2026-09-03-pendencias.md` |
| **Registro de cada sessão**, índice cronológico | `docs/sessoes/README.md` |
| Reescrita do histórico git (2026-09-03) e mapa de SHAs antigo → novo | `docs/sessoes/S7.5-push-e-reescrita-do-historico.md` |

### Skills — versionadas em `docs/skills/`

| Skill | Assunto |
|---|---|
| `leitor-biblioteca-aq` | ler e escrever `.aq`, schema, OQ3D |
| `leitor-ifc` | IFC4: parse, escrita, cores, armadilhas STEP |
| `leitor-step` | STEP B-rep → malha com OpenCASCADE |
| `pagina-biblioteca` | páginas de catálogo com viewer 3D e miniaturas |

`bash scripts/link_skills.sh` cria symlinks de `~/.claude/skills/` para cá (idempotente; preserva
um diretório diferente como `.bak.<ts>`). As skills servem outros projetos; **para trabalhar aqui
elas não são necessárias** — este mapa, `README.md` e `docs/` bastam.

---

## 👉 Fase atual — "passar o projeto a limpo" (desde 2026-09-03, S7.4)

Os catálogos gerados são POC e ninguém os consome: **o que importa é a geração acusar erro** e
código + conhecimento serem corrigidos. Lista de pendências, evidência e ordem em
`docs/auditoria-2026-09-03-pendencias.md`. Branch de trabalho: **`main`** (a `poc-edicao` foi
mergeada por fast-forward em 2026-09-04 e ficou só como marcador).

**Feito (S7.4 → S7.8, 2026-09-03/04):** passo 1 (push), passo 2 (geração acusa erro: C1–C3,
I1–I3, I7, I8; suíte `tests/`, I9), passo 3 (C4, I13, CI mínimo I20), passo 4 (documentação:
C8, C9, C10, I22, I23, I24, I25) e passo 5 (ambiente: I5, I18, I19, `bootstrap.sh`). Também C5,
C6 (histórico reescrito — **todo SHA anterior a 2026-09-03 mudou**), I21. Suíte: **57 testes**,
`python3 -m pytest` ≈ 25 s; CI verde em `main`.

**Próxima sessão:** ver `docs/sessoes/S7.8-passo-4-e-5-documentacao-e-ambiente.md`, seção 7. Em resumo: os itens de `www/`
(I11, I12, I14–I17), a limpeza L1–L14 conforme cada área for tocada, e as **decisões que só o
usuário toma**: C7 (deploy do preview), I10 (auth na POC), I6 (modo `--ifc`: matar ou arquivar),
I4 (promover o writer de `.aq`), LICENSE, se vale um `--strict`.

**Estado da base da POC:** em `www/README.md`, "Estado da base e do storage" — única versão.
A raiz está **sem `config.json`** (o build interativo recria).

---

## O que é este projeto

Pipeline local que gera catálogos BIM interativos com viewer 3D a partir de bibliotecas `.aq`
do AltoQi Builder. Produz um **preview HTML** (`output/preview/`) e um **ZIP para a bilds.com**
(`output/<origem>/<slug>-AAAAMMDDHHMM.zip`), consumido em produção desde 2026-08-28 (PR #1244).

**A decisão central: a geometria vem do `.aq`, não do IFC.** O BLOB `SIMBOLOGIA_3D.SIMBOLOGIA_3D`
guarda a malha completa, com cor, no formato proprietário OQ3D — o mesmo sólido que o AltoQi
exporta como IFC. Resultado: 85× a 421× mais rápido, um arquivo de entrada, vínculo peça →
geometria por chave estrangeira (zero matching por nome). O modo `--ifc` sobrevive só para os
dois casos em que o IFC tem peça que o banco não tem, ou para conferir uma fonte contra a outra.

**Linhas de trabalho:** (1) pipeline estático — a linha madura, em produção; (2) engenharia
reversa da **escrita** de `.aq` (`eng-reversa/`, 2026-09-02; o `.aq` gerado abre no AltoQi
Builder); (3) POC de edição de informações e modelo 3D sobre a POC dinâmica (`www/`,
2026-09-03); (4) POC de catálogo dinâmico — **encerrada em 2026-08-31**, aprendizados em
`docs/solutions/architecture-patterns/`.

## Fluxo em sete passos

```
1. git clone … && cd bilds-bim-3d
2. bash scripts/bootstrap.sh            # pip, Three.js (templates/vendor/), Playwright; --check só confere
   sudo apt-get install -y libnss3 libnspr4 libasound2t64    # libs do Chromium — único passo com sudo
3. copiar as bibliotecas para input/<Fabricante>/[<Linha>/]<pecas>.aq   (input/ é gitignored)
4. python3 scripts/build.py --all       # um ZIP por .aq, sem perguntas (build.py sem --all pergunta)
5. python3 -m http.server 8080 --directory output/preview      # preview local
6. subir output/<origem>/<slug>-<ts>.zip no dashboard.bilds.com → BIM 3D
7. (opcional) vercel --prod --yes, da raiz  — publica o preview; push NÃO publica (integração git desligada)
```

Fabricante, título, slug e layout são inferidos do `.aq` e da pasta (cascata em
`docs/conhecimento/pipeline-estatico.md`, "O que é inferido"). **Sem miniaturas o build falha**
(exit 1) — `--allow-no-thumbs` ou `--skip-thumbs` são as saídas explícitas. `--all` pula
bibliotecas que já têm ZIP; `--force` refaz. Tubos e kits não têm simbologia 3D e são pulados
por design; `AVISO: … descartada(s)` ou `… com aviso de parse` **não** é tubo — é peça com
geometria que o parser não leu (foi assim que apareceu a malha OQ3D versão 3 da Maxbar).

## Estrutura do projeto

```
bilds-bim-3d/
├── CLAUDE.md · README.md · CONCEPTS.md
├── .nvmrc (24) · .python-version (3.12) · package.json (packageManager pnpm@11, playwright para as miniaturas)
├── requirements.txt (jinja2, numpy) · requirements-dev.txt (pytest) · requirements-cad.txt (ifcopenshell, OCP, pypdf)
├── .github/workflows/ci.yml     ← pytest -m "not thumbs" + py_compile; pnpm -r build em www/
├── config.example.json · vercel.json (serve output/preview, cleanUrls)
├── scripts/
│   ├── build.py                 ← entry point: .aq → catalog.json → preview → thumbs → ZIP
│   ├── oq3d.py · read_aq.py     ← OQ3D binário → malha; .aq → dados/metadados/simbologias   ★ caminho padrão
│   ├── dedup.py                 ← deduplicação de vértices (~79%)
│   ├── parse_ifc.py             ← IFC4 → geometria (modo --ifc e ifc_to_geo.py)
│   ├── step_to_geo.py · ifc_to_geo.py · geo_to_aq.py   ← conversores da POC de edição (STEP/IFC → malha; malha → .aq)
│   ├── thumbs.mjs               ← miniaturas no Chromium (Playwright); templates/thumbs/harness.html
│   ├── bootstrap.sh · setup_vendor.sh · link_skills.sh
├── templates/layouts/{series-rows,catalog-grid}.html · templates/thumbs/harness.html · templates/vendor/ (Three.js, baixado)
├── tests/                       ← pytest; conftest põe scripts/ e eng-reversa/tools/ no path; paridade py ↔ ts via Node
├── docs/
│   ├── conhecimento/            ← pipeline-estatico, oq3d, read-aq, parse-ifc, templates-html, diagnostico
│   ├── sessoes/                 ← um registro por sessão + README.md (índice) + TEMPLATE.md
│   ├── skills/                  ← as quatro skills (symlinkadas de ~/.claude/skills)
│   ├── auditoria-2026-09-03-pendencias.md · bilds-bim-3d-zip-spec.md · estudo-oq3d/ · solutions/ · saida-bilds-com/
│   └── plano-*.md, plans/       ← históricos
├── eng-reversa/                 ← escrever .aq/OQ3D, formas paramétricas, PDF → catálogo (README próprio)
├── www/                         ← POC dinâmica + edição: apps/api (Nest :4000), apps/web (Next :3000), tools/ (port TS, testes) — README próprio
├── input/                       ← .aq do usuário — gitignored
└── output/                      ← gerado; só preview/index.html (landing feita à mão) é versionado
    ├── <origem>/<slug>-<ts>.zip · <origem>/<slug>-catalog.json · geo/… · thumbs/…
    └── preview/<slug>/{index.html,catalog.json,data/*.json} · preview/vendor/ · preview/catalogs.json
```

`output/` espelha `input/`; por isso o `.gitignore` usa `output/**/*.zip`. **`output/preview/index.html`
é a única coisa em `output/` que não se regenera** — ao limpar, preserve-a. Tudo o mais volta
com `python3 scripts/build.py --all --force` (rode `setup_vendor.sh` antes num clone novo).

---

## Pré-requisitos e ambiente

`bash scripts/bootstrap.sh --check` imprime a tabela abaixo preenchida para esta máquina e sai
com 1 se falta algo obrigatório; sem `--check` instala o que falta (nunca usa sudo). As versões
esperadas estão **nos arquivos**, não em texto: `.python-version`, `.nvmrc`, `packageManager` e
`engines` do `package.json`.

| Item | Obrigatório para | Como conferir |
|---|---|---|
| Python ≥ 3.12, `requirements.txt` (jinja2, numpy) | tudo | `python3 -c 'import jinja2, numpy'` |
| Node ≥ 22.6 (24 no `.nvmrc`) e pnpm 11 | miniaturas, `www/`, testes de paridade | `node -v; pnpm -v` |
| `templates/vendor/` com Three.js | preview | `ls templates/vendor` (`bash scripts/setup_vendor.sh`) |
| `node_modules/playwright` + Chromium + libs `libnss3 libnspr4 libasound2t64` | miniaturas (o build **falha** sem) | `ls node_modules/playwright; ldconfig -p \| grep libnss3` |
| `requirements-dev.txt` (pytest) | `tests/` | `python3 -m pytest -q` |
| `www/` com `pnpm install` e `www/.env` | POC | `bash scripts/bootstrap.sh --www --check` |
| `requirements-cad.txt` (ifcopenshell, cadquery-ocp, pypdf) | `--ifc` B-rep, STEP, IFC grande, PDF | `python3 -c 'import OCP, ifcopenshell'` |

**Armadilhas de ambiente que já custaram tempo:**
- **Dois Node na máquina.** O do apt (`/usr/bin/node`, v18) e o do nvm; o nvm só entra no PATH
  de shell interativo, então um subprocess pega o velho e o Playwright recusa. `build.py` procura
  sozinho um Node bom em `~/.nvm` (`_find_node`); em outro lugar, `BILDS_NODE=/caminho/node`.
- **`sudo npx playwright install-deps` falha** com nvm: o `sudo` descarta o PATH e cai no Node do
  apt. Use o `apt-get` acima (mesmas libs) ou `sudo env "PATH=$PATH" npx …`. Sem sudo: baixar os
  `.deb` e extrair em `~/.local/chromium-libs` com `LD_LIBRARY_PATH` (receita no `README.md`).
- **PEP 668** no Ubuntu: `pip install` fora de venv exige `--user --break-system-packages`; o
  `bootstrap.sh` tenta sem e repete com as flags.
- **Só pnpm.** `npm install` cria um `package-lock.json` que não é versionado (I18).
- **Atlas M0 com whitelist de IP** derruba a API da POC em retry infinito com uma mensagem que
  culpa o whitelist para qualquer causa — o diagnóstico por camadas está em `www/README.md`.

## Testes — `tests/`

```bash
python3 -m pytest                                   # 57 testes, ≈ 25 s (abre o Chromium uma vez)
python3 -m pytest -m "not thumbs"                   # sem Chromium — é o que o CI roda
python3 -m pytest -m "not thumbs and not paridade"  # só Python, sem Node
```

| Arquivo | O que prova |
|---|---|
| `test_oq3d.py` | contrato do parser: truncado → `OQ3DError`; layout desconhecido → pulado + aviso; versões 2 e 3 iguais; raízes do cabeçalho; Akato 262/262; Maxbar versão 3 |
| `test_read_aq.py` | `open_aq` não cria arquivo, read-only, rejeita lixo; contagens da Akato; cp1252 sem `\x80–\x9f`/U+FFFD |
| `test_build.py` | `auto_config`; `build_catalog_from_aq` + `diag` em Akato corrompida; render dos dois layouts com `1" x 1" <script>`; sem Jinja2/template → `RuntimeError`; `thumbCount`; `ThumbsError` sem Node, `--allow-no-thumbs`, `--skip-thumbs`, `run_all` exit 1; uma miniatura real |
| `test_oq3d_roundtrip.py` | `eng-reversa/tools/oq3d_roundtrip.py` como processo: caminho padrão da Amanco, seis casos, `.aq` ausente → exit 1, `--sem-real` |
| `test_editor_roundtrips.py` | `www/tools/testes-editor.sh`: round-trip do `mesh-model` por agrupamento a 2 µm; `ROUNDTRIP_SABOTAR=1` tem de falhar |
| `test_paridade_ts.py` | Python ↔ TypeScript (`www/tools`): blobs sintéticos e a Akato inteira, campo a campo e SHA-1; curvas Q-H da Dancor |
| `test_bootstrap.py` | `bootstrap.sh --check` imprime a tabela e acusa Node ausente com exit 1 |

Fixtures reais são os `.aq` de `input/` e o `www/storage/` — gitignored, então esses testes
**pulam com motivo** onde não existem (no CI: 32 passam, 20+ pulam). Saída em
`output/.pytest-tmp/` — tem de ficar **dentro da raiz** porque `thumbs.mjs` serve a geometria
por HTTP relativo à raiz. `pytest.ini` restringe a coleta a `tests/` (o `.venv` do worker tem
os testes do numpy dentro). **Regra:** comportamento novo entra aqui no mesmo commit.

## CI — `.github/workflows/ci.yml`

Roda em push para `main` e em PR. Job `pipeline-estatico`: Python do `.python-version`, Node do
`.nvmrc`, `pip install -r requirements-dev.txt`, `py_compile` de `scripts/` e
`eng-reversa/tools/`, `pytest -m "not thumbs" -rs`. Job `www`: pnpm do `packageManager`,
`pnpm install --frozen-lockfile`, `pnpm -r build`. Não sobe Mongo nem Chromium. Reproduzir
localmente: `git worktree add /tmp/ci HEAD && cd /tmp/ci && python3 -m pytest -m "not thumbs"`.
Push com arquivo em `.github/workflows/` exige o escopo `workflow` no token do `gh`
(`gh auth refresh -h github.com -s workflow`).

## Git e deploy

- **Identidade:** `carlosnetoaltoqi` (`git config user.name`). **Branch:** `main`, histórico linear.
- **Histórico reescrito em 2026-09-03 (S7.5):** `git filter-repo` removeu 398 MB de
  `output/preview/**` e `eng-reversa/saida/`; `main` e `poc-edicao` foram reenviadas com `--force`.
  Um clone antigo não faz `pull` — clone de novo. Mapa de SHAs em
  `docs/sessoes/S7.5-push-e-reescrita-do-historico.md`; backup da história antiga em
  `/home/foltz/backups/` (só nesta máquina).
- **Gitignored e regerável:** `input/`, `output/**` exceto `preview/index.html`, `templates/vendor/`,
  `www/storage/`, `.env`, `config.json`, `output/.pytest-tmp/`. `*.aq` é `binary` no `.gitattributes`.
- **Deploy do preview** (`bilds-bim-3d.vercel.app`, projeto `bilds/bilds-bim-3d` — nunca criar outro):
  só pelo CLI, **da raiz**, `vercel --prod --yes`, depois de um build local. A integração git da
  Vercel está **desligada** desde 2026-09-02 (o push sobrescrevia o deploy com só a landing).
  Nunca passar `output/preview` como argumento posicional. Estratégia definitiva = C7, em aberto.
- **Preview local:** `python3 -m http.server 8080 --directory output/preview`.

---

## Histórico de sessões

Está em `docs/sessoes/` — um arquivo por sessão e o índice cronológico em
`docs/sessoes/README.md`. O registro mais recente é o que "Fase atual" aponta.
