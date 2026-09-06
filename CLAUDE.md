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
| Formato binário **OQ3D** (cabeçalho, classes, instâncias, unidades, escrever) | `docs/conhecimento/oq3d.md` + docstring de `www/apps/ingestao/pipeline/oq3d.py` + skill `leitor-biblioteca-aq` |
| Schema do `.aq`, **cp1252**, sentinelas, `DIAMETRO_PECA` é código, escrever `.aq` | `docs/conhecimento/read-aq.md` + skill `leitor-biblioteca-aq` |
| IFC4 → geometria (conversor da POC `ifc_to_geo.py`, round-trip do exportador do editor) | `docs/conhecimento/parse-ifc.md` + skill `leitor-ifc` |
| STEP e **IGES** → malha (OpenCASCADE), costura de faces soltas, orientação pelo volume, armadilhas de segfault | skill `docs/skills/leitor-step/` + `www/apps/ingestao/pipeline/step_to_geo.py` |
| **Plugin de AutoCAD** (plataforma Catallog/Collabo — TupyCAD) → catálogo: a DLL é casca de um catálogo web, API pública, formulário de download, IGES/RFA, Termos de Uso e escopo autorizado | `eng-reversa/tupy/estudo/01-plugin-tupycad-e-catalogo-web.md` + `www/apps/ingestao/pipeline/{catallog,rfa_partatom}.py` + `www/README.md` (rotas `plugin-autocad`) |
| Templates HTML, Three.js self-hosted, escape, design tokens | `docs/conhecimento/templates-html.md` + skill `pagina-biblioteca` |
| **Sintoma → causa** (tabela de diagnóstico, ~70 linhas) | `docs/conhecimento/diagnostico.md` |
| Contrato do ZIP consumido pela bilds.com | `docs/bilds-bim-3d-zip-spec.md` |
| **`www/`** — serviço de ingestão (pipeline Python + Chromium), API de catálogo e web: subir os três, contratos, fluxo do import, **estado da base**, decisões/pendências, `.env`, Atlas | `www/README.md` + `docs/arquitetura-www-servico-de-ingestao.md` (decisões A1–A10, etapas E0–E6) |
| Aprendizados da POC dinâmica (ADRs, diretrizes para a reconstrução na bilds.com) | `docs/solutions/architecture-patterns/` |
| Planos históricos | `docs/plano-produto-dinamico.md`, `docs/plano-integracao-bilds.md`, `docs/plans/` — **históricos**, não guiam nada |
| O que a bilds.com recebe deste pipeline (lado consumidor) | `docs/saida-bilds-com/pipeline-bim-dinamico-na-bilds-com.md` |
| Como a geometria do `.aq` foi descoberta e validada | `docs/estudo-oq3d/` |
| **Escrever** `.aq`/OQ3D do zero — uma peça (`geo_to_aq.py`) ou o **catálogo inteiro** (`catalogo_to_aq.py`, botão "baixar .aq") | `www/apps/ingestao/pipeline/{aq_writer,oq3d_writer,geo_to_aq,catalogo_to_aq}.py` + `docs/conhecimento/read-aq.md` ("Escrever um `.aq`", "Escrever um catálogo inteiro"); catálogo a partir de PDF (Akato) em `eng-reversa/README.md` |
| Vocabulário (OQ3D, Import, Parte, Bake, sentinela, código de diâmetro…) | `CONCEPTS.md` |
| **Pendências de sistema e ordem de ataque** (C1–C10, I1–I32, L1–L14) | `docs/auditoria-2026-09-03-pendencias.md`; o que fica/sai a caminho do repo limpo em `docs/inventario-2026-09-05-fica-ou-sai.md` |
| **Registro de cada sessão**, índice cronológico | `docs/sessoes/README.md` |
| Reescrita do histórico git (2026-09-03) e mapa de SHAs antigo → novo | `docs/sessoes/S7.5-push-e-reescrita-do-historico.md` |

### Skills — versionadas em `docs/skills/`

| Skill | Assunto |
|---|---|
| `leitor-biblioteca-aq` | ler e escrever `.aq`, schema, OQ3D |
| `leitor-ifc` | IFC4: parse, escrita, cores, armadilhas STEP |
| `leitor-step` | STEP e IGES B-rep → malha com OpenCASCADE (1.1.0: costura do IGES) |
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
C6 (histórico reescrito — **todo SHA anterior a 2026-09-03 mudou**), I21. **S7.9 (2026-09-05):** I26 —
a conferência do exportador IFC no `testes-editor.sh` acusava fronteira de arredondamento (buckets a
10 µm) e saía 0 com FALHA; agora pareia vértices a ≤ 2 µm nos dois sentidos, sai 1, autoteste
`ROUNDTRIP_SABOTAR_IFC`. **S7.10 (2026-09-05):** I6 decidido — modo `--ifc` **removido** (`build.py`
1.727 → 1.290 linhas; `config.json` só com `slug/titulo/fabricante/descricao/layout/aq_file`).
**S7.11 (2026-09-05):** três itens de `www/` — I15 (morte de processo filho não é mais engolida:
`importacoes/worker-ipc.ts`, resumo das miniaturas no import, JSON órfão do STEP limpo), I17 (host,
`PORT` e `STORAGE_PATH` resolvidos em um lugar cada, com guarda de regressão) e I14 (`PUT`/`restaurar`
de geometria regeram a miniatura). **S7.12 (2026-09-05):** os três itens de `www/` que restavam — I16
(`ValidationPipe` global + um DTO por corpo), I11 (fila de importações em memória e recuperação no boot)
e I12 (`@nestjs/mongoose@11`, um só driver Mongo, health pela conexão). Com isso **todos os itens de
`www/` da auditoria estão fechados**. **S7.13 (2026-09-05):** teste de aceitação com API + Mongo + Chromium de pé
(os cenários de S7.11 §7 e S7.12 §7): fila, recuperação no boot, `PATCH` inválido, `/health` 503 e miniatura
regerada **confirmados** — e a execução achou cinco defeitos, corrigidos com teste (I27 fila liberava antes
das miniaturas, I28 nota `na fila` em import publicado, I29 workers órfãos após `kill -9`, I30 nome do arquivo
em latin1, I31 DTO do produto sem `thumbAtualizadaEm`) e uma pendência de decisão (I32: 500 após 30 s com o
Mongo fora). Suíte: **107 testes**, `python3 -m pytest` ≈ 60 s.

**S7.14 (2026-09-05) — nova direção:** o usuário decidiu que o que vai para o repositório limpo é o
**`www/` reestruturado**: um **serviço de ingestão** (`apps/ingestao`, :4100) que recebe `.aq`/`.zip`/STEP/IFC
e roda o **pipeline Python** (`apps/ingestao/pipeline/`, onde `read_aq.py`, `oq3d.py`, `dedup.py` e o
`thumbs.mjs` passaram a morar) + Chromium para catálogo, geometria e miniaturas; uma **API de catálogo**
(`apps/api`, :4000) só de leitura e edição (copy-on-write na geometria compartilhada, miniatura pedida ao
serviço); o **web** (`apps/web`, :3000) sem login, com chamada para edição em toda página de catálogo; e o
pacote `packages/dominio`. O port TypeScript do leitor `.aq` e toda a auth **saíram**. Seis etapas E0–E6,
todas feitas e commitadas uma a uma; aceitação com Dancor e **Amanco (856 produtos, 448 miniaturas em 58 s)**,
copy-on-write real e `kill -9` no meio do import. Registro: `docs/sessoes/S7.14-www-servico-de-ingestao.md`;
plano e pendências: `docs/arquitetura-www-servico-de-ingestao.md` (§4). O inventário fica-ou-sai
(`docs/inventario-2026-09-05-fica-ou-sai.md`) foi escrito antes e está anotado. `scripts/build.py` continua
gerando o ZIP da bilds.com, agora importando o pipeline de `www/apps/ingestao/pipeline/`.

**S7.15 (2026-09-05):** I32 (`MongoProntoGuard` em `@bim/dominio`, 503 na hora com o Mongo fora), C7 (preview
só local; `vercel.json` removido — o projeto na Vercel ainda existe) e I4 (`aq_writer.py`, `oq3d_writer.py` e
`schema-aq-607.sql` promovidos para o pipeline; `gerar_aq.py` da Akato herda de `EscritorAq`). Depois, a pedido:
STEP/IFC saem do editor (menu na home: importar `.aq`, importar peça CAD, **converter peça CAD** em `/cad`, criar
empresa) e **apagar em cada nível** (empresa, catálogo, peça, importação — `dominio/remocao.ts`). Suíte **115**.

**S7.16 (2026-09-05):** a pedido — **o catálogo salvo vira um `.aq` novo** para o AltoQi Builder: `catalogo_to_aq.py`
(N peças; um grupo por série com códigos IFC inferidos do nome — `aq_writer.classificar_grupo`, 189/192 grupos da
Amanco —; uma simbologia por geometria compartilhada; uma propriedade por chave; curva Q-H), `GET /exportar/catalogo/:id`
no serviço (stream, nada fica no servidor) e o botão **"baixar .aq (AltoQi Builder)"** na edição do catálogo. Amanco:
854 peças (as 2 apagadas na interface não vão), 448 simbologias, 54 MB em 7 s, `NOME_PECA` e geometria iguais ao
original — e **o arquivo foi aceito pelo AltoQi Builder** (usuário, fim da sessão). Registro:
`docs/sessoes/S7.16-exportar-catalogo-aq.md`. Suíte **121**.

**S7.17 (2026-09-05, noite) — missão do usuário: plugin de AutoCAD → `.aq`.** O plugin TupyCAD (plataforma
**Catallog**) instalado no Windows é uma DLL .NET de 35 KB **sem geometria**: abre um catálogo web com API pública
que serve um **IGES** (SolidWorks, faces soltas) por produto e um `.rfa` Revit por família, atrás de um formulário
de lead. Os Termos de Uso do site proíbem redistribuição — a sessão parou e perguntou; o usuário autorizou **18
grupos (TupyGrooved)** com os dados reais dele. Feito: `step_to_geo.py` lê IGES (costura + **orientação pelo volume
assinado**, cor por face preservada); `catallog.py` (DLL → host/categorias; categoria → downloads + tesselação → o
mesmo JSON do `catalogo_de_aq.py`); `rfa_partatom.py`; import tipo **`plugin`** (`POST /importacoes/plugin-autocad[/inspecionar]`,
`processarCatalogo` comum ao `.aq`); botão **"Importar plugin do AutoCAD"** na home (`/importar/plugin`); `.igs` aceito
como peça CAD. Estudo e ferramentas em `eng-reversa/tupy/` (22 arquivos baixados, gitignored) →
`Tupy-TupyGrooved.aq` (10 peças) validado pelos leitores; ponta a ponta pelo serviço em 294 s, `.aq` exportado relido.
**Não aberto no AltoQi Builder ainda.** Registro: `docs/sessoes/S7.17-plugin-autocad-tupy.md`. Suíte **136**.

**Próxima sessão:** abrir o `.aq` da Tupy no AltoQi Builder (aceitação, como a Amanco na S7.16); depois
`docs/sessoes/S7.14-www-servico-de-ingestao.md`, seção 7 — build do `dist/` com o `@bim/dominio`, e2e reexecutados,
aceitação automatizada, Nest 11; depois o isolamento do serviço. Decisão antiga ainda em aberto: LICENSE.

**Estado da base:** em `www/README.md`, "Estado da base e do storage" — única versão.
A raiz está **sem `config.json`** (o build interativo recria).

---

## O que é este projeto

Pipeline local que gera catálogos BIM interativos com viewer 3D a partir de bibliotecas `.aq`
do AltoQi Builder. Produz um **preview HTML** (`output/preview/`) e um **ZIP para a bilds.com**
(`output/<origem>/<slug>-AAAAMMDDHHMM.zip`), consumido em produção desde 2026-08-28 (PR #1244).

**A decisão central: a geometria vem do `.aq`, não do IFC.** O BLOB `SIMBOLOGIA_3D.SIMBOLOGIA_3D`
guarda a malha completa, com cor, no formato proprietário OQ3D — o mesmo sólido que o AltoQi
exporta como IFC. Resultado: 85× a 421× mais rápido, um arquivo de entrada, vínculo peça →
geometria por chave estrangeira (zero matching por nome). O modo `--ifc` (geometria dos IFCs da
pasta, matching por nome) foi **removido em 2026-09-05** (I6); `parse_ifc.py` fica para a POC.

**Linhas de trabalho:** (1) pipeline estático — a linha madura, em produção; (2) engenharia
reversa da **escrita** de `.aq` (`eng-reversa/`, 2026-09-02; o `.aq` gerado abre no AltoQi
Builder); (3) **`www/`: serviço de ingestão + API de catálogo + web com editor** (reestruturado em
2026-09-05, S7.14 — é o que vai para o repositório limpo; `docs/arquitetura-www-servico-de-ingestao.md`);
(4) POC de catálogo dinâmico — **encerrada em 2026-08-31**, aprendizados em
`docs/solutions/architecture-patterns/`. Desde a S7.14 o pipeline (leitura do `.aq`, catálogo,
miniaturas) mora em `www/apps/ingestao/pipeline/` e o `build.py` da linha (1) o importa.

## Fluxo em sete passos

```
1. git clone … && cd bilds-bim-3d
2. bash scripts/bootstrap.sh            # pip, Three.js (templates/vendor/), Playwright; --check só confere
   sudo apt-get install -y libnss3 libnspr4 libasound2t64    # libs do Chromium — único passo com sudo
3. copiar as bibliotecas para input/<Fabricante>/[<Linha>/]<pecas>.aq   (input/ é gitignored)
4. python3 scripts/build.py --all       # um ZIP por .aq, sem perguntas (build.py sem --all pergunta)
5. python3 -m http.server 8080 --directory output/preview      # preview local
6. subir output/<origem>/<slug>-<ts>.zip no dashboard.bilds.com → BIM 3D
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
├── requirements.txt (jinja2, numpy) · requirements-dev.txt (pytest) · requirements-cad.txt (ifcopenshell, OCP, pypdf, olefile)
├── .github/workflows/ci.yml     ← pytest -m "not thumbs" + py_compile; pnpm -r build em www/
├── config.example.json
├── scripts/
│   ├── build.py                 ← pipeline estático: .aq → catalog.json → preview → thumbs → ZIP (consome www/apps/ingestao/pipeline)
│   ├── bootstrap.sh · setup_vendor.sh · link_skills.sh
├── templates/layouts/{series-rows,catalog-grid}.html · templates/vendor/ (Three.js, baixado)
├── tests/                       ← pytest; conftest põe scripts/, www/apps/ingestao/pipeline/ e eng-reversa/tools/ no path; paridade/ tem os harnesses Node
├── docs/
│   ├── conhecimento/            ← pipeline-estatico, oq3d, read-aq, parse-ifc, templates-html, diagnostico
│   ├── sessoes/                 ← um registro por sessão + README.md (índice) + TEMPLATE.md
│   ├── skills/                  ← as quatro skills (symlinkadas de ~/.claude/skills)
│   ├── auditoria-2026-09-03-pendencias.md · bilds-bim-3d-zip-spec.md · estudo-oq3d/ · solutions/ · saida-bilds-com/
│   └── plano-*.md, plans/       ← históricos
├── eng-reversa/                 ← escrever .aq/OQ3D, formas paramétricas, PDF → catálogo (README próprio)
│   └── tupy/                    ← S7.17: plugin de AutoCAD (Catallog) → IGES → .aq; estudo/, tools/, dados/ (downloads/ e saida/ gitignored)
├── www/                         ← em reestruturação (docs/arquitetura-www-servico-de-ingestao.md) — README próprio
│   ├── apps/ingestao/pipeline/  ← ★ O PIPELINE PYTHON: read_aq.py, oq3d.py, dedup.py, catalogo.py, inferencia.py, miniaturas.py,
│   │                               catalogo_de_aq.py (CLI), step_to_geo.py (STEP+IGES), ifc_to_geo.py, parse_ifc.py, geo_to_aq.py, aq_writer.py,
│   │                               oq3d_writer.py, catalogo_to_aq.py (catálogo salvo → .aq novo), catallog.py (plugin de AutoCAD → catálogo),
│   │                               rfa_partatom.py, schema-aq-607.sql, thumbs.mjs + harness.html
│   ├── apps/api (Nest :4000) · apps/web (Next :3000) · tools/ (testes do editor)
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
| `www/` com `pnpm install` e `www/.env` (Mongo, `STORAGE_PATH`) | serviço de ingestão, API e web | `bash scripts/bootstrap.sh --www --check`; subir com `pnpm dev:ingestao`, `dev:api`, `dev:web` |
| `requirements-cad.txt` (ifcopenshell, cadquery-ocp, pypdf, olefile) | importar/tesselar STEP, IGES e IFC no serviço (`step_to_geo.py`, `ifc_to_geo.py`), plugin de AutoCAD (`catallog.py`; `olefile` só para os tipos do `.rfa`), PDF | `python3 -c 'import OCP, ifcopenshell, olefile'` |

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
python3 -m pytest                                   # 136 testes, 1–4 min (abre o Chromium duas vezes; ida e volta da Akato; IGES da Tupy se baixados)
python3 -m pytest -m "not thumbs"                   # sem Chromium — é o que o CI roda
python3 -m pytest -m "not thumbs and not paridade"  # só Python, sem Node
```

| Arquivo | O que prova |
|---|---|
| `test_oq3d.py` | contrato do parser: truncado → `OQ3DError`; layout desconhecido → pulado + aviso; versões 2 e 3 iguais; raízes do cabeçalho; Akato 262/262; Maxbar versão 3 |
| `test_read_aq.py` | `open_aq` não cria arquivo, read-only, rejeita lixo; contagens da Akato; cp1252 sem `\x80–\x9f`/U+FFFD |
| `test_build.py` | `auto_config` (só chaves do `.aq`; `--ifc` recusado — I6); `build_catalog_from_aq` + `diag` em Akato corrompida; render dos dois layouts com `1" x 1" <script>`; sem Jinja2/template → `RuntimeError`; `thumbCount`; `ThumbsError` sem Node, `--allow-no-thumbs`, `--skip-thumbs`, `run_all` exit 1; uma miniatura real |
| `test_geo_to_aq.py` | I4: o pipeline não importa nada de fora do próprio diretório; `geo_to_aq.py` gera um `.aq` de uma malha que `read_aq.py` e `oq3d.py` leem de volta (nome com acento em cp1252, specs, um triângulo, cores) |
| `test_step_to_geo.py` | S7.17: IGES de uma caixa escrita pelo próprio OCC (6 faces soltas) → `costurado`, volume igual ao da caixa, 12 △ com as normais para fora (volume assinado da malha positivo); o STEP da mesma caixa não costura; CLI; IGES da Tupy (se baixados): sólido fechado, volume > 0, cor preservada. Pula sem OCP |
| `test_catallog.py` | S7.17, sem rede: `inspecionar_dll` numa DLL sintética (host, plugin, versão) e na TupyCAD.dll real (se instalada); não-PE/sem URL acusam; `validar_lead`; `specs_do_produto` (tabela Dimensionais com cabeçalho `colspan`/`rowspan`, Tipos Revit); `catalogo_de_downloads` com um IGES real → JSON do `catalogo_de_aq.py`, avisos de grupo sem IGES, idempotente; manifesto real da Tupy |
| `test_catalogo_to_aq.py` | S7.16: `catalogo_to_aq.py` — manifesto com geometria compartilhada, cores, acentos, curva Q-H → relido por `read_aq`/`oq3d`/`catalogo.py` (uma simbologia por geometria, uma propriedade por chave, bomba 2075, cp1252 nos bytes); `--manter-prefixo-serie`; geometria ausente, caractere fora do cp1252 e catálogo vazio → exit 1 sem arquivo parcial; **ida e volta com a Akato inteira** (262 peças: nomes, séries, specs, bbox e triângulos iguais) |
| `test_oq3d_roundtrip.py` | `eng-reversa/tools/oq3d_roundtrip.py` como processo: caminho padrão da Amanco, seis casos, `.aq` ausente → exit 1, `--sem-real` |
| `test_editor_roundtrips.py` | `www/tools/testes-editor.sh`: round-trip do `mesh-model` por agrupamento a 2 µm; IFC exportado → `parse_ifc.py` com todo vértice pareado a ≤ 2 µm nos dois sentidos; `ROUNDTRIP_SABOTAR=1` e `ROUNDTRIP_SABOTAR_IFC=1` têm de falhar |
| `test_processo.py` | E3: `executar()` do serviço — saída ≠ 0 com o stderr, sinal, timeout, ocioso, comando inexistente, stdin do filho aberto enquanto o pai vive; `vigiar_stdin` sai com 2 no EOF e continua com o stdin aberto; `thumbs.mjs` com `sairComStdin` para sem renderizar (marcador `thumbs`) |
| `test_www_config.py` | I17/E3: só `lib/api.ts` conhece `localhost:4000`/`4100`; só `common/ingestao-client.ts` da API conhece o serviço, e a API não roda processo filho; só `dominio/src/storage-path.ts` lê `STORAGE_PATH` (mesma pasta para api e ingestao); cada serviço escuta a porta do env; `PIPELINE_DIR`/`--sair-com-stdin` só no `pipeline.service.ts`. I30: `nomeOriginalUtf8` e todo `originalname` passa por ele |
| `test_geometrias_thumb.py` | I14/A5/A6: geometria exclusiva → `.orig.json` e miniatura pedida ao serviço no `PUT` e no `restaurar`; geometria compartilhada → copy-on-write (`geo/<importId>/<productId>.json`, `geoKeyCompartilhada`, irmão intacto, restaurar desfaz); serviço fora → `thumbErro` no produto e `miniatura: 'nao-solicitada'`; `GET /produtos/:id` devolve `thumbAtualizadaEm`/`thumbErro` (I31) |
| `test_www_validacao.py` | I16: 47 corpos pelo mesmo `ValidationPipe` (agora em `@bim/dominio`) contra cada DTO da API e do serviço (`ImportarDto`, `ImportarPluginDto`, `ExportarAqDto`, `PatchProdutoDto`…) — aceitos saem normalizados, rejeitados dão 400; campo fora do DTO é 400 |
| `test_www_importacao.py` | I11 (no serviço de ingestão): `Fila` (FIFO, posição informada, rejeição repassada, concorrência 2, `IMPORTACOES_CONCORRENCIA` inválida derruba); recuperação no boot marca `falhou` todo não terminal, limpa produtos/`geo/`, apaga só `bim-*.aq|.zip`/`cad-*` do tmp |
| `test_www_remocao.py` | apagar em cascata (`dominio/remocao.ts`): produto que compartilha geometria deixa a geometria; exclusivo leva geometria, `.orig` e miniatura; copy-on-write leva só a cópia; catálogo leva produtos, storage e imports; importação terminada e recontagem; em andamento → recusada; empresa leva tudo; inexistentes → `NaoEncontrado` |
| `test_www_mongo_guard.py` | I32: `MongoProntoGuard` — conectado passa; `readyState` 0/2/3 → 503 na hora com o estado e o ponteiro para `/health`; `/health` passa desconectado; registrado como `APP_GUARD` nos dois apps |
| `test_www_deps.py` | I12/E3: lê `pnpm-lock.yaml` — peers satisfeitas nos importers `apps/api` e `apps/ingestao`; os três importers (com `packages/dominio`) resolvem as MESMAS versões de Nest/Mongoose/class-validator; `@bim/dominio` só nos dois apps; sem pacote `mongodb`; health pela conexão; nenhum parser `.aq`/OQ3D em TypeScript (A2) |
| `test_bootstrap.py` | `bootstrap.sh --check` imprime a tabela e acusa Node ausente com exit 1 |

Fixtures reais são os `.aq` de `input/` e o `www/storage/` — gitignored, então esses testes
**pulam com motivo** onde não existem (no CI: ~50 passam, 20+ pulam). Os testes de `www/` rodam os
harnesses de `tests/paridade/` com o `ts-node` de cada app (`apps/api`, `apps/ingestao`). Saída em
`output/.pytest-tmp/` — tem de ficar **dentro da raiz** porque `thumbs.mjs` serve a geometria
por HTTP relativo à raiz. `pytest.ini` restringe a coleta a `tests/` (o `.venv` do worker tem
os testes do numpy dentro). **Regra:** comportamento novo entra aqui no mesmo commit.

## CI — `.github/workflows/ci.yml`

Roda em push para `main` e em PR. Job `pipeline-estatico`: Python do `.python-version`, Node do
`.nvmrc`, `pip install -r requirements-dev.txt`, `py_compile` de `scripts/`, `www/apps/ingestao/pipeline/`
e `eng-reversa/tools/`, `pytest -m "not thumbs" -rs`. Job `www`: pnpm do `packageManager`,
`pnpm install --frozen-lockfile`, `pnpm -r build` (ingestao, api e web). Não sobe Mongo nem Chromium. Reproduzir
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
- **Preview é só local** (C7, decidido em 2026-09-05): `vercel.json`/`.vercelignore` saíram; o projeto
  `bilds/bilds-bim-3d` na Vercel pode ser apagado. A bilds.com consome o ZIP, não o preview.
- **Preview local:** `python3 -m http.server 8080 --directory output/preview`.

---

## Histórico de sessões

Está em `docs/sessoes/` — um arquivo por sessão e o índice cronológico em
`docs/sessoes/README.md`. O registro mais recente é o que "Fase atual" aponta.
