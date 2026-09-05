# Inventário — o que fica e o que sai (2026-09-05, S7.14)

> **Estado: proposta para decisão do usuário.** Este projeto foi uma POC grande que provou várias
> viabilidades. O próximo passo é levar o que vale para um repositório limpo. Antes disso, este
> documento classifica **cada área do repositório atual** em um de quatro vereditos, com a evidência
> (linhas, dependências, quem usa). As colunas "Veredito" marcadas com **D** dependem de uma decisão
> listada na seção 5; as demais são recomendação direta.

Números de `git ls-files` em 2026-09-05 (3,7 MB versionados; `input/`, `output/` e `www/storage/`
são gitignored e não entram na conta).

| Área | Arquivos | Linhas | Veredito resumido |
|---|---|---|---|
| raiz (CLAUDE.md, README, CONCEPTS, configs) | 17 | 854 | fica, reescrito para o repo limpo |
| `scripts/` | 12 | 3.996 | fica (núcleo) |
| `templates/` | 4 | 1.382 | fica |
| `tests/` | 23 | 2.437 | fica o que prova o que fica; 8 de 13 arquivos dependem de `www/` |
| `docs/conhecimento/` + `zip-spec` + `CONCEPTS` | 8 | 1.783 | fica — é o conhecimento destilado |
| `docs/skills/` | 4 | 2.995 | fica (D4) |
| `docs/sessoes/` | 49 | 6.889 | arquivo — não migra |
| `docs/estudo-oq3d/`, planos, `plans/`, `solutions/`, `saida-bilds-com/`, auditoria | 13 | 7.603 | arquivo — não migra (exceto `saida-bilds-com`, ver D6) |
| `eng-reversa/tools/` | 12 | 4.000 | 5 arquivos ficam promovidos (I4); 4 saem; 3 arquivo |
| `eng-reversa/dados/` + `estudo/` | 11 | 21.052 | arquivo (os `dados/akato-*` podem sair, D7) |
| `www/apps/api/src` | 44 | 3.482 | **D1/D2** — POC dinâmica encerrada; bilds.com reconstrói |
| `www/apps/web/src` | 38 | 4.745 | **D3** — `bim-catalog` (761) sai; `bim-editor` (2.528) é decisão |
| `www/tools/` | 15 | 3.072 | 958 linhas ficam (port TS); 7 arquivos saem como legado |
| `www/workers/` | 2 | 188 | sai (legado L4) |
| `output/preview/index.html`, `vercel.json`, `.vercelignore` | 3 | 544 | **D5** — deploy do preview (C7) |

---

## 1. O que a POC provou — e onde cada prova mora

A classificação parte disto: o repo limpo carrega **o código que materializa cada viabilidade
provada** e **o conhecimento destilado**; o caminho até a prova (sessões, estudos, spikes, medições)
fica aqui como arquivo.

| # | Viabilidade provada | Código que a materializa | Prova / registro | Situação |
|---|---|---|---|---|
| V1 | **A geometria sai do `.aq`** (formato OQ3D decodificado; IFC dispensável) | `www/apps/ingestao/pipeline/oq3d.py`, `www/apps/ingestao/pipeline/read_aq.py`, `www/apps/ingestao/pipeline/dedup.py` | `docs/estudo-oq3d/`, `docs/conhecimento/{oq3d,read-aq}.md`, `tests/test_oq3d.py`, `test_read_aq.py` | em produção |
| V2 | **Pipeline estático `.aq` → ZIP + preview com miniaturas** | `scripts/build.py`, `www/apps/ingestao/pipeline/thumbs.mjs`, `templates/` | `docs/conhecimento/pipeline-estatico.md`, `docs/bilds-bim-3d-zip-spec.md`, `tests/test_build.py` | em produção na bilds.com desde 2026-08-28 (PR #1244) |
| V3 | **Escrever `.aq`/OQ3D** que o AltoQi Builder abre | `eng-reversa/tools/{oq3d_writer,gerar_aq,validar_aq,formas}.py` | `eng-reversa/estudo/01,02,06`, `oq3d_roundtrip.py`, `tests/test_oq3d_roundtrip.py`, screenshot do Builder | provado, ainda em pasta de estudo (I4) |
| V4 | **CAD (STEP/IFC) → malha → `.aq`** | `scripts/{step_to_geo,ifc_to_geo,geo_to_aq,parse_ifc}.py` | skill `leitor-step`, `docs/conhecimento/parse-ifc.md`, `test_editor_roundtrips.py` | provado (S7.2) |
| V5 | **Leitor `.aq`/OQ3D em TypeScript, idêntico ao Python** | `www/tools/{aq-reader,oq3d-parser}.ts` | `tests/test_paridade_ts.py` (campo a campo, SHA-1) | provado; a bilds.com planeja portar (`saida-bilds-com` §4.2–4.3) |
| V6 | **Miniatura no servidor idêntica ao viewer** (Playwright + harness) | `www/tools/thumb-rasterizer.ts`, `www/apps/ingestao/pipeline/harness.html` | `docs/solutions/…/thumb-qualidade-identica-ao-viewer.md` (47 dB PSNR) | provado; a bilds.com planeja portar (§ 892) |
| V7 | **Catálogo dinâmico** (NestJS + Next + Mongo) | `www/apps/api`, `www/apps/web/components/bim-catalog` | `docs/solutions/…/poc-catalogo-bim-dinamico-aprendizados.md` | **encerrada em 2026-08-31**; conclusão: a bilds.com reconstrói, não herda o código |
| V8 | **Editor 3D no browser** (mesh-model, exportar IFC4, importar STEP) | `www/apps/web/components/bim-editor`, `www/apps/api/src/{step,geometrias,produtos}` | `docs/sessoes/S7.1`, `S7.2`, `testes-editor.sh` | provado (S7.1–S7.2); destino não decidido |
| V9 | **PDF comercial → catálogo → `.aq`** (Akato) | `eng-reversa/tools/{pdf_coords,pdf_akato}.py`, `dados/akato-*` | `eng-reversa/estudo/03,04` | provado uma vez, específico da Akato; conclusão do estudo: PDF não traz cota de forma |

---

## 2. Vereditos

Legenda: **Fica** = vai para o repo limpo · **Arquivo** = permanece neste repo como registro, não
migra · **Sai** = apagar já, aqui (o git guarda) · **D** = depende de decisão da seção 5.

### 2.1 Raiz

| Item | Veredito | Por quê |
|---|---|---|
| `README.md`, `CONCEPTS.md` | Fica (reescritos) | `README` hoje mistura pipeline, POC e editor; no repo limpo descreve só o que foi |
| `CLAUDE.md` | Fica (reescrito) | é mapa; o bloco "Fase atual" e as referências a `www/`/`eng-reversa/` mudam conforme D1–D3 |
| `requirements*.txt`, `.python-version`, `.nvmrc`, `package.json`, `pnpm-lock.yaml`, `pytest.ini`, `.editorconfig`, `.gitattributes`, `.gitignore` | Fica | declaração de ambiente (I5/I18/I19). `requirements-cad.txt` só se V4 ficar (fica) |
| `config.example.json` | Fica | contrato do `config.json` |
| `vercel.json`, `.vercelignore` | **D5** | só fazem sentido se o preview continuar na Vercel (C7) |
| `.github/workflows/ci.yml` | Fica (ajustado) | o job `www` cai ou muda conforme D2/D3 |

### 2.2 `scripts/` — núcleo, tudo fica

| Arquivo | Linhas | Veredito | Observação |
|---|---|---|---|
| `build.py` | 1.290 | Fica | levar junto a limpeza L1 (import duplo, `_potencia_de` duplicada, ramo inalcançável, `--interactive`/`--skip-ifc` mortos, cópia de `vendor/`) |
| `oq3d.py`, `read_aq.py`, `dedup.py` | 1.020 | Fica | V1; L3 (dedup em 4 implementações) e L5 (`ATIVO=1` vs `COUNT(*)`) |
| `thumbs.mjs` | 141 | Fica | V2; L5 (`concurrency` documentado e não lido) |
| `parse_ifc.py` | 572 | Fica | V4; sem ele não há `ifc_to_geo.py` nem round-trip do exportador IFC; L2 |
| `step_to_geo.py`, `ifc_to_geo.py`, `geo_to_aq.py` | 776 | Fica | V4; `geo_to_aq.py` importa `eng-reversa/tools/{gerar_aq,oq3d_writer}` — **só fica se I4 for feito** (promover o writer). Sem `www/` eles viram CLI puro, o que já são |
| `bootstrap.sh`, `setup_vendor.sh` | 147 | Fica | `--www` e `--cad` seguem D2/V4 |
| `link_skills.sh` | 50 | Fica se D4 = skills ficam no repo |

### 2.3 `templates/` — fica

`layouts/{series-rows,catalog-grid}.html`, `thumbs/harness.html`, `vendor/.gitkeep`. Levar L3 (a
cena Three.js está copiada nos três; extrair `templates/shared/viewer.js`) e L8 (a landing
`output/preview/index.html` é o único arquivo manual num diretório de build — mover para
`templates/` e copiar no build). `harness.html` também é a base do `thumb-rasterizer.ts` (V6).

### 2.4 `tests/`

| Arquivo | Prova | Veredito |
|---|---|---|
| `test_oq3d.py`, `test_read_aq.py`, `test_build.py`, `oq3d_sintetico.py`, `conftest.py`, `test_bootstrap.py` | V1, V2, ambiente | Fica |
| `test_oq3d_roundtrip.py` | V3 (roda `eng-reversa/tools/oq3d_roundtrip.py`) | Fica, com o caminho novo do writer (I4) |
| `test_paridade_ts.py` + `paridade/dump_ts.mjs` | V5 | Fica **se** o port TS ficar (recomendado — D2) |
| `test_editor_roundtrips.py` | V4 + V8 (`www/tools/testes-editor.sh`, `mesh-model.ts`, `ifc-export.ts`) | **D3** |
| `test_worker_ipc.py`, `test_www_config.py`, `test_geometrias_thumb.py`, `test_www_validacao.py`, `test_www_importacao.py`, `test_www_deps.py` + `paridade/*.cts|.mts` (exceto `dump_ts`) | infra da POC `www/` (I11–I17, I27–I31) | **D2** — seguem o destino da API. Foram o investimento da S7.11–S7.13; se a API não migra, viram arquivo |

### 2.5 `docs/`

| Item | Linhas | Veredito | Por quê |
|---|---|---|---|
| `conhecimento/` (6 + README) | 1.085 | Fica | conhecimento destilado, fonte única por assunto (I22). `parse-ifc.md` fica com V4; `diagnostico.md` perde as linhas de `www/` conforme D2 |
| `bilds-bim-3d-zip-spec.md` | 599 | Fica | contrato com a bilds.com em produção |
| `skills/` (4) | 2.995 | **D4** | servem outros projetos; hoje symlinkadas de `~/.claude/skills`. Ficam no repo limpo **ou** ganham repo próprio; nunca somem |
| `sessoes/` (48 registros + índice + template) | 6.889 | Arquivo | história da POC. O repo limpo começa com uma sessão S1 que aponta para cá |
| `estudo-oq3d/` (html + 3 scripts) | 1.697 | Arquivo | a investigação que gerou V1; o resultado está em `conhecimento/oq3d.md`. `render.py`/`massval.py` usam nome antigo `oq3dtree` — já são fósseis |
| `auditoria-2026-09-03-pendencias.md` | 383 | Arquivo | os itens abertos (I32, C7, I10, I4, L1–L14) são transcritos para o repo limpo como issues ou seção do README, não o documento |
| `plano-produto-dinamico.md`, `plano-integracao-bilds.md`, `plans/` | 2.976 | Arquivo | já marcados históricos (I25); L9 (dois "## 9.") deixa de importar |
| `solutions/architecture-patterns/` (2) | 508 | Arquivo, **mas** o conteúdo migra | são as diretrizes para a reconstrução na bilds.com; no repo limpo entram como `docs/decisoes/` ou vão direto para o repo da bilds.com (D6) |
| `saida-bilds-com/pipeline-bim-dinamico-na-bilds-com.md` | 2.039 | **D6** | escrito **para o repo da bilds.com** (entrada de `ce-plan`); é o único documento cujo destino natural é outro repositório |

### 2.6 `eng-reversa/` — V3 e V9

| Arquivo | Linhas | Veredito | Por quê |
|---|---|---|---|
| `tools/oq3d_writer.py` | 301 | **Fica, promovido** (I4) | o inverso de `oq3d.py`; `geo_to_aq.py` depende |
| `tools/gerar_aq.py` | 868 | **Fica, promovido** (I4) | schema 607, cp1252, enums, constantes do AltoQi — é *o* writer de `.aq`. Hoje está amarrado ao catálogo Akato; ao promover, separar "escrever `.aq`" de "montar a Akato" |
| `tools/validar_aq.py` | 265 | Fica, promovido | valida um `.aq` gerado com os leitores do projeto — vira teste/CLI |
| `tools/formas.py` + `formas_teste.py` | 950 | Fica (D7 para o `_teste`) | 23 geradores paramétricos; `formas_teste.py` lê `dados/akato-catalogo.json` — sem os dados vira teste sobre fixture sintética |
| `tools/oq3d_roundtrip.py` | 240 | Fica | já é a prova de V3 via `tests/` |
| `tools/pipeline_ponta_a_ponta.py`, `olhar_preview.mjs` | 310 | Arquivo | rodam o pipeline sobre a Akato gerada; a prova já foi feita |
| `tools/{aq_referencia,oq3d_anatomy}.py` | 379 | Arquivo (L4) | ferramentas de dissecação usadas para chegar ao writer; o achado está em `conhecimento/oq3d.md` e `read-aq.md` |
| `tools/{pdf_coords,pdf_akato}.py` | 687 | **Sai** ou Arquivo (D7) | V9, específico da Akato; a conclusão do estudo é que PDF não determina forma. Se algum dia houver "catálogo a partir de PDF", recomeça de outro jeito |
| `dados/schema-aq-607.sql` | 167 | Fica, junto do writer | o schema que `gerar_aq.py` cria |
| `dados/akato-{celulas,catalogo}.json`, `akato-pdf-texto.txt` | 19.360 | **Sai** ou Arquivo (D7) | saída gerada a partir de um PDF; 75 % das linhas versionadas do diretório |
| `estudo/01–06.md` + `img/` | 1.525 | Arquivo | `05-achados-para-a-documentacao` já foi aplicado (2026-09-02) |
| `README.md` | 189 | Arquivo | reescrever como "o que este estudo foi" apontando para o writer promovido |

### 2.7 `www/` — V5, V6, V7, V8

| Item | Linhas | Veredito | Por quê |
|---|---|---|---|
| `tools/aq-reader.ts`, `tools/oq3d-parser.ts` | 717 | **Fica** (como biblioteca, sem Nest) | V5; a bilds.com vai portar (`saida-bilds-com` §4.2–4.3); `test_paridade_ts.py` garante paridade com o Python |
| `tools/thumb-rasterizer.ts` | 241 | **Fica** (biblioteca) | V6; usa `www/apps/ingestao/pipeline/harness.html` |
| `tools/{roundtrip-mesh-model,roundtrip-ifc-export}.mts`, `testes-editor.sh`, `e2e/*.mjs` | 418 | **D3** | provas do editor (V8) |
| `tools/{test-worker,test-port-s2-2,thumb-rasterizer-sw,ingest-library,measure-thumbs,smoke-geometry-store,regen-thumbs}.ts` | 1.696 | **Sai** (L4) | spikes S1.2–S4.3 e o rasterizador software aposentado; `thumb-rasterizer-sw.ts` já se declara HISTÓRICO; nenhum é importado pela API |
| `workers/aq-parser/` (Flask) | 188 | **Sai** (L4) | substituído pelo `parse-worker.ts`; só `test-worker.ts` (que sai) o usa |
| `apps/api/src/{auth,companies,empresas,bim-catalogs,bim-imports,bim-products,catalogos,importacoes,thumbs,health,geometry-store,common}` | ≈ 2.700 | **D2** | V7 — POC dinâmica encerrada; a conclusão registrada é "a bilds.com reconstrói". A infra endurecida em S7.11–S7.13 (fila, recuperação, validação, IPC) é conhecimento a transcrever para `solutions/`, não código a migrar |
| `apps/api/src/{step,geometrias,produtos}` | ≈ 780 | **D3** | backend do editor (V8): importa STEP/IFC pela API, `PUT`/`restaurar` geometria, `PATCH` produto |
| `apps/web/components/bim-catalog/` + páginas `[empresa]/[catalogo]`, `empresa/*`, `login` | ≈ 1.900 | **D2** (tendência: Sai) | viewer público e fluxos da POC dinâmica; `bim-editor` importa `bim-viewer-engine.ts` e `types.ts` de `bim-catalog` — se o editor fica, esses dois arquivos vão junto |
| `apps/web/components/bim-editor/` + `importar-step`, `editar/*` | ≈ 2.800 | **D3** | V8. `mesh-model.ts` (486) e `ifc-export.ts` (333) são puros e testados fora do browser; o resto é React acoplado à API da POC |
| `README.md` | 482 | Arquivo | "Estado da base" e "armadilha do Atlas" só valem enquanto a POC existir aqui |
| `.env.example`, `pnpm-workspace.yaml`, `package.json` | 80 | D2/D3 | L7 (`WORKER_PORT` descrito errado) morre com o worker |

### 2.8 `output/` e deploy

| Item | Veredito | Por quê |
|---|---|---|
| `output/preview/index.html` (landing, 514 linhas) | Fica em `templates/` (L8) | único arquivo manual em diretório gerado |
| `output/.gitkeep`, `output/preview/.gitignore` | Fica | estrutura |
| deploy na Vercel (`vercel.json`, projeto `bilds/bilds-bim-3d`) | **D5** | C7: hoje é irreproduzível (serve o `output/preview` desta máquina, 511 MB) |

---

## 3. Dependências que amarram os vereditos

```
geo_to_aq.py ──► eng-reversa/tools/gerar_aq.py, oq3d_writer.py        (I4: promover, senão V4 não fecha)
step.service.ts (www/api) ──► www/apps/ingestao/pipeline/step_to_geo.py, geo_to_aq.py     (D3: o editor depende dos conversores; os conversores não dependem do editor)
parse-worker.ts (www/api) ──► www/tools/aq-reader.ts, oq3d-parser.ts   (o port TS é biblioteca; a API é um consumidor)
thumb-worker.ts (www/api) ──► www/tools/thumb-rasterizer.ts ──► www/apps/ingestao/pipeline/harness.html
www/apps/ingestao/pipeline/thumbs.mjs ──► www/apps/ingestao/pipeline/harness.html                   (mesmo harness: pipeline e POC)
tests/test_paridade_ts.py ──► tests/paridade/dump_ts.mjs ──► www/tools/{aq-reader,oq3d-parser}.ts
tests/test_editor_roundtrips.py ──► www/tools/testes-editor.sh ──► mesh-model.ts, ifc-export.ts, www/apps/ingestao/pipeline/parse_ifc.py
8 de 13 tests/test_*.py ──► www/                                       (6 são só da infra da API — D2)
bim-editor ──► bim-catalog/{bim-viewer-engine,types}.ts               (o editor arrasta 2 arquivos do viewer público)
docs/skills ◄── ~/.claude/skills (symlinks)                            (D4)
```

Consequência: **o port TS (V5) e o rasterizador (V6) não precisam da API para existir** — ficam como
`lib/` com os testes de paridade, independentemente de D2. Já o editor (V8) precisa de *alguma* API
para gravar; sem a API da POC ele não roda.

---

## 4. O que já pode sair hoje, sem depender de decisão

Nenhum destes é importado por código vivo nem citado por teste que passe:

1. `www/workers/aq-parser/` (Flask, 188 linhas) e `www/tools/test-worker.ts`, `pnpm worker:test`.
2. `www/tools/thumb-rasterizer-sw.ts` (declara-se histórico; ADR-003 já registra a decisão).
3. `www/tools/{test-port-s2-2,ingest-library,measure-thumbs,smoke-geometry-store,regen-thumbs}.ts`
   e os scripts `port:test`, `ingest`, `thumb:measure`, `smoke:geo`, `thumb:regen` do `www/package.json`.
   `test_paridade_ts.py` **não** usa o `test-port-s2-2.ts` (só o cita na docstring); usa `dump_ts.mjs`.
4. `eng-reversa/tools/{aq_referencia,oq3d_anatomy,pipeline_ponta_a_ponta}.py`, `olhar_preview.mjs`
   — ferramentas de investigação cujo achado já está em `docs/conhecimento/`.
5. Linhas de `.env.example` sobre `WORKER_PORT` (L7).

Total: ≈ 2.400 linhas. Cada remoção é um commit (`chore:`), com a linha correspondente em
`www/README.md`/`eng-reversa/README.md` apontando para o SHA.

---

## 5. Decisões do usuário

| # | Pergunta | Opções | Recomendação |
|---|---|---|---|
| **D1** | **O que é o repo limpo?** | (a) só o pipeline estático em produção (V1+V2); (b) toolbox `.aq`/OQ3D: ler, escrever, converter CAD, gerar catálogo (V1–V4) + libs TS (V5–V6); (c) (b) + editor (V8) | **(b)**. É o que a bilds.com não tem e vai consumir; o editor sem a API da POC não roda e a bilds.com vai ter a sua |
| **D2** | **A API/web da POC dinâmica (V7) migra?** | migra inteira / migra só o que o editor precisa / não migra | **Não migra.** A própria POC concluiu "a bilds.com reconstrói". O que vale (fila, recuperação, IPC, validação, thumbs no servidor) vira um documento em `solutions/` e os 6 testes de infra viram arquivo |
| **D3** | **O editor 3D (V8) migra?** | sim, com a fatia mínima da API (`step`, `geometrias`, `produtos`) / só `mesh-model.ts` + `ifc-export.ts` como lib / não | **Só as libs puras** (`mesh-model.ts`, `ifc-export.ts`, round-trips). A UI React e a fatia de API ficam como arquivo até a bilds.com decidir se quer o editor |
| **D4** | **Skills (`docs/skills/`)** | ficam no repo limpo / repo próprio / ficam aqui | **Repo limpo**, porque toda sessão as atualiza junto do conhecimento (regra 4 do CLAUDE.md); um repo separado repete o problema do I24 |
| **D5** | **Preview na Vercel (C7)** | manter e resolver (build na Vercel ou storage externo) / aceitar só local e apagar `vercel.json` | **Só local.** Ninguém consome o preview; a bilds.com consome o ZIP. Apagar `vercel.json`/`.vercelignore` e o projeto na Vercel encerra C7 |
| **D6** | **`saida-bilds-com/` e `solutions/`** | vão para o repo da bilds.com / ficam aqui como arquivo / vão para o repo limpo | **Repo da bilds.com** (é o público-alvo declarado); cópia fica aqui como arquivo |
| **D7** | **Dados e ferramentas da Akato (V9)** | apagar já / arquivo | **Arquivo aqui, não migra.** 19 k linhas de saída de PDF não servem a mais nada; `formas_teste.py` passa a usar fixture sintética |
| **D8** | **Este repositório depois da migração** | arquivar no GitHub (read-only) / manter como "laboratório" | **Arquivar** quando o repo limpo tiver CI verde e a bilds.com apontar para ele |

Depois de D1–D8 respondidos, a seção 2 vira definitiva, a seção 4 é executada aqui (um commit por
item), e I4 (promover o writer) é o primeiro trabalho de código — é a única dependência que impede
V4 de ficar autocontida.
