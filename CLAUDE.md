# CLAUDE.md — bilds-bim-3d

Ponto de entrada para quem trabalha neste projeto, agente ou humano. É um **mapa**: o que o projeto é,
como rodar, onde está cada conhecimento e qual é o estado atual. O conhecimento em si mora em
`docs/conhecimento/`, nos READMEs de cada serviço e nas skills — este arquivo aponta, não repete.

> **`docs/historico/` não é para ser lido ao carregar o projeto.** É arquivo (sessões antigas, estudos,
> planos superados, lições de processo) para consulta pontual do operador. Só abra um arquivo de lá
> quando precisar da evidência de um número ou do raciocínio de uma decisão antiga.

---

## Regra fundamental: documentação primeiro

Se a informação não está no repositório, ela não existe para o próximo agente. Memória de agente e
skills fora do repo são auxiliares. O que vale é o **estado atual**, não a trilha de como se chegou nele:

1. Código corrigido e commitado — **um commit por item**, com o teste em `tests/` no mesmo commit
   quando há comportamento novo.
2. Conhecimento novo sobre formato, algoritmo ou padrão vai para o documento certo de
   `docs/conhecimento/` (ou o README do serviço, se for operação dele) — nunca para cá, nunca para o histórico.
3. Decisão nova ou revista é um ADR em `docs/decisoes/`; uma decisão superada ganha status
   "Substituída por ADR-nnn", não é apagada.
4. Se algo aqui ou em `docs/` se mostrou falso, corrigir **no documento de origem**, sem "antes dizia…".
   Documentação oficial não carrega narrativa do que deu errado; se uma lição de processo merece ficar,
   vai para `docs/historico/licoes-de-processo.md`.
5. Se aprendeu algo sobre `.aq`, OQ3D, IFC, STEP/IGES ou páginas de catálogo, a **skill** em
   `docs/skills/` recebe a linha e o bump de `version`.
6. **Sem fabricantes, arquivos ou caminhos da POC** em código, contratos, conhecimento ou skills
   (ADR-016; a lista está em `tests/arquitetura/termos_efemeros.txt`). Isso só cabe em `docs/historico/`,
   `docs/integracoes/` e `tests/fixtures.local.json`.
7. O bloco **"Estado atual e pendências"** no fim deste arquivo é atualizado ao encerrar — só fatos
   verificáveis e o que falta fazer.

## O que é este projeto

Catálogos BIM com viewer 3D a partir de bibliotecas `.aq` do AltoQi Builder — e o caminho de volta
(escrever `.aq`, converter CAD, ler catálogos de plugins e famílias Revit, gerar o ZIP que a bilds.com consome).
**A decisão central: a geometria vem do `.aq`, não do IFC** — o BLOB `SIMBOLOGIA_3D` guarda a malha
completa, com cor, no formato OQ3D; vínculo peça → geometria por chave estrangeira, zero matching por nome.

**Arquitetura (`docs/arquitetura.md`):** uma **biblioteca Python comum** (`biblioteca/`, pacote
`bim_pipeline`, stateless) e **um serviço por contexto** em `servicos/` — criador de catálogos (:4100),
API de catálogo (:4000), editor de peças (:4400), gerador de ZIP (:4200, stateless), conversores
(:4300, stateless) — mais o `web/` (:3000) com um cliente por serviço e os pacotes TypeScript comuns
(`pacotes/base`, `pacotes/dominio`). Cada contexto pode ser portado levando só o que é seu (§4 da
arquitetura). Enquanto viver aqui é POC: sem auth, sem admin (ADR-007).

## Como rodar

```bash
bash scripts/bootstrap.sh --check        # a tabela do ambiente; sem --check instala o que falta (nunca sudo)
sudo apt-get install -y libnss3 libnspr4 libasound2t64     # libs do Chromium — único passo com sudo
python3 -m bim_pipeline.cli.zip_bilds biblioteca.aq --saida saida.zip   # só o ZIP, sem serviços
cp .env.example .env && pnpm dev          # cinco serviços + web (compila os pacotes antes)
python3 -m pytest                         # 240 testes, ≈ 4 min; -m "not thumbs" sem Chromium
```

Detalhes de uso em `README.md`; rotas e variáveis de cada serviço no `README.md` dele; roteiro de
aceitação com tudo de pé em `docs/aceitacao.md`.

## Onde está cada conhecimento

| Assunto | Onde |
|---|---|
| **Arquitetura**: camadas, sete regras de fronteira, quem grava o quê, guia de porte, regras de mudança | `docs/arquitetura.md`; decisões em `docs/decisoes/` (ADR-001…026) |
| Formato `.aq` (SQLite/ZIP, cp1252, sentinelas, código de diâmetro, enums, versões de schema, leitura; **o que desenha em planta**) | `docs/conhecimento/aq-formato.md` |
| Escrever `.aq` — uma peça e o catálogo inteiro (cinco regras, erros que abortam, validação) | `docs/conhecimento/aq-escrita.md` |
| Formato binário **OQ3D** — leitura tolerante e escrita | `docs/conhecimento/oq3d.md` |
| Contrato de geometria `{pos,col,idx}`, eixos, dedup, partes, **bocais** (achar na malha os pontos de ligação) | `docs/conhecimento/geometria.md` |
| IFC4 — leitura (placement, cores, unidades), escrita (o exportador do editor), verificação a 2 µm | `docs/conhecimento/ifc.md` |
| STEP e IGES → malha (OpenCASCADE), costura de faces soltas, orientação pelo volume | `docs/conhecimento/step-iges.md` |
| Plugin de CAD que é casca de um catálogo web (DLL, API, formulário de lead, IGES/RFA, termos de uso) | `docs/conhecimento/plugin-cad-catalogo-web.md` |
| Famílias Revit `.rfa` (OLE2, PartAtom, BasicFileInfo, type catalog `.txt`; o que não se lê; geometria irmã ou forma representativa) e projetos `.rvt` via IFC (APS Model Derivative, opt-in; `.rfa` não é aceito pela APS) | `docs/conhecimento/revit-familias.md`; decisões em ADR-018 e ADR-019 |
| Catálogo comercial em PDF → tabelas; o que um PDF nunca determina | `docs/conhecimento/pdf-catalogo.md` |
| Forma representativa por parâmetro (dado × norma × invenção; os dois defeitos que passam em teste) | `docs/conhecimento/formas-representativas.md` |
| **Aplicação e disciplina** — `PROJETO_APLICACAO` (bitmask), `TIPO_APLICACAO_PECA` (enum 1…84), a ponte `ENTIDADE_IFC` → aplicação, `POSICIONAR_SIMBOLOGIA_3D`, e como o pipeline classifica hoje | `docs/conhecimento/aplicacoes-builder.md`; ADR-024 |
| **Código de bitola** — a escala é em **polegada** (0…17), e 40/50/75 mm dependem da série | `docs/conhecimento/aq-formato.md` §`DIAMETRO_PECA`; ADR-025 |
| Inferência de fabricante, título, slug e layout | `docs/conhecimento/inferencia.md` |
| Miniaturas — mesma cena do viewer no Chromium, `page.evaluate` com string, harness por `http://` | `docs/conhecimento/miniaturas.md` |
| Modelo do catálogo — Import como máquina de estados, ponteiro de geometria, copy-on-write, remoção | `docs/conhecimento/catalogo-modelo.md` |
| Processos filhos — stdin EOF, stdout × stderr, timeouts, códigos | `docs/conhecimento/processos-filhos.md` |
| Fatos de serviço Nest/Next e de ferramentas (201, Ajv 2020, tsbuildinfo, project references, Atlas) | `docs/conhecimento/servicos-web.md` |
| Formato do ZIP (pacote genérico, com exemplo completo) · lado consumidor (bilds.com) | `docs/conhecimento/zip-bilds-formato.md` · `docs/integracoes/bilds-com.md` |
| **As duas fontes externas de verdade** (bibliotecas nativas + catálogo oficial do Builder; a ajuda em HTML), como distinguir nativa de saída nossa, e o método: medir → ajuda → experimento subtrativo | `docs/conhecimento/aq-formato.md` §"As duas fontes externas"; ferramenta `ferramentas.ajuda_builder` |
| **Sintoma → causa** (formatos e biblioteca) | `docs/conhecimento/diagnostico.md` |
| Contratos biblioteca ↔ serviços (JSON Schema) | `biblioteca/bim_pipeline/contratos/README.md` |
| Biblioteca: mapa de módulos, CLIs, regras | `biblioteca/README.md` |
| Cada serviço: rotas, variáveis, o que leva ao ser portado | `servicos/<nome>/README.md`, `web/README.md` |
| Vocabulário | `CONCEPTS.md` |
| Arquivo (sessões antigas, estudos, planos, spec original do ZIP, lições de processo) | `docs/historico/` — **não carregar**; consulta pontual |

### Skills — versionadas em `docs/skills/`

`leitor-biblioteca-aq` (ler e escrever `.aq`, OQ3D), `leitor-ifc`, `leitor-step`, `pagina-biblioteca`.
São how-tos curtos que apontam para `docs/conhecimento/` (cada uma leva `referencias/`, symlink para
lá). `bash scripts/link_skills.sh` cria symlinks em `~/.claude/skills/`. Servem outros projetos; **para
trabalhar aqui não são necessárias** — este mapa e `docs/` bastam.

## Estrutura

```
bilds-bim-3d/
├── biblioteca/bim_pipeline/{aq,geometria,catalogo(/fontes: plugin_catalogo_web, familias_revit),conversores,miniaturas,saida,cli(/ferramentas),contratos}
│   ← ★ a biblioteca comum (README próprio); miniaturas/ tem package.json próprio (playwright + three)
├── pacotes/base (@bim/base) · pacotes/dominio (@bim/dominio)   ← TypeScript compilado para dist/ (project references)
├── servicos/{criador-de-catalogos :4100, catalogo-api :4000, editor-de-pecas :4400, gerador-zip :4200, conversores :4300}
├── web/ :3000                    ← Next; src/servicos/<nome>.ts = um cliente por serviço; tools/ = round-trips do editor
├── tests/{biblioteca,servicos,arquitetura}/ · tests/paridade/ (harnesses Node) · tests/e2e/ · fixtures por papel
├── docs/{arquitetura.md, decisoes/, conhecimento/, integracoes/, skills/, aceitacao.md, historico/ (não carregar)}
├── scripts/bootstrap.sh · link_skills.sh
├── .env.example (portas por contexto, URLs, Mongo, STORAGE_PATH, APS_CLIENT_ID/SECRET opcionais) · pnpm-workspace.yaml · pyproject em biblioteca/
├── storage/ · input/ · output/   ← gitignored: storage dos serviços, .aq do usuário, saída do lote
```

## Pré-requisitos e armadilhas de ambiente

`bash scripts/bootstrap.sh --check` confere tudo. Versões nos arquivos: `.python-version` (3.12),
`.nvmrc` (24), `packageManager` (pnpm 11). `pip install -r requirements.txt` instala a biblioteca em
modo editável; `requirements-cad.txt` traz OpenCASCADE/ifcopenshell (STEP/IGES/IFC); `pnpm install` na
raiz instala pacotes, serviços, web e as dependências Node das miniaturas.

- **Dois Node na máquina** (apt v18 e nvm): um subprocess pega o do apt e o Playwright recusa. A
  biblioteca procura sozinha em `~/.nvm` (`miniaturas.render.find_node`); senão `BILDS_NODE=…`.
- **`sudo npx playwright install-deps` falha** com nvm (o sudo descarta o PATH): use o `apt-get` acima.
- **PEP 668**: `pip install` fora de venv pede `--user --break-system-packages`; o bootstrap tenta.
- **Só pnpm**; `npm install` gera lockfile que não é versionado.
- **Atlas com whitelist de IP**: o Mongoose culpa o whitelist para qualquer causa; diagnóstico no
  README do `catalogo-api`. Um Mongo local tira isso do caminho.
- **`dev:*` dos serviços Nest não tem watch**: mudou TypeScript, reinicie (`ss -ltnp | grep ':4100 '`).
- **`storage/`, `input/`, `output/` são dados não rastreados**: antes de qualquer `git clean`, confira o
  `.gitignore` com `git clean -ndq` (dry-run).

## Testes — `tests/` em três camadas

`tests/biblioteca/` (Python puro + fixtures por papel), `tests/servicos/` (harnesses Node em
`tests/paridade/` com ts-node de cada serviço; round-trips do editor), `tests/arquitetura/` (as sete
regras de `docs/arquitetura.md` §3: `test_biblioteca_isolada`, `test_fronteiras`, `test_sem_empresas`
com `termos_efemeros.txt`, `test_contratos`, `test_deps`). O que cada arquivo prova está no docstring
dele. Fixtures reais por **papel** em `tests/fixtures.local.json` (gitignored; modelo
`fixtures.example.json`; papéis em `tests/fixtures.py`) — sem elas os testes pulam com motivo.
**Regra:** comportamento novo entra em `tests/` no mesmo commit. Depois de mexer na configuração do
pytest, confira a contagem de coleta (240).

## CI — `.github/workflows/ci.yml`

Job `biblioteca`: `pip install -e biblioteca`, `py_compile`, `pytest tests/biblioteca tests/arquitetura -m "not thumbs"`.
Job `servicos`: `pnpm install --frozen-lockfile`, `pnpm -r build`, `pytest tests/servicos`. Não sobe Mongo nem Chromium.
Push com arquivo em `.github/workflows/` exige o escopo `workflow` no token do `gh`.

## Git

Identidade `carlosnetoaltoqi`; branch `main`, histórico linear; nada de push sem pedido. `*.aq` é
`binary` no `.gitattributes`. Gitignored e regerável: `input/`, `output/`, `storage/`, `.env`, `dist/`,
`node_modules/`, `tests/fixtures.local.json`. Nunca commitar `.env` nem `tests/fixtures.local.json`.

---

## 👉 Estado atual e pendências

**Estado.** O pipeline lê `.aq`, IFC, STEP/IGES, famílias e projetos Revit e catálogos de plugin de
CAD, e **escreve `.aq` que o AltoQi Builder abre, desenha, lança em projeto e representa em planta** —
as quatro coisas verificadas no Builder, a última em 2026-09-10. A arquitetura de
`docs/arquitetura.md` está implementada por inteiro; suíte em **278** na coleta (19 pulam nesta
máquina porque as fixtures de `tests/fixtures.local.json` não estão em `input/`), `pnpm -r build` e
`pnpm start:*` verdes nos 9 workspaces.

O que o escritor decide sobre cada peça está em `biblioteca/bim_pipeline/aq/cadastro.py`, num lugar
só, e se lê em `docs/conhecimento/aplicacoes-builder.md`: disciplina (bitmask, **perguntada** na
importação — ADR-024), aplicação (entidade IFC declarada → vocabulário da disciplina, em português
**ou inglês** → genérico com aviso), entidade IFC (42 nomeadas), bitola (escala em **polegada**,
hidráulica — ADR-025), posicionamento (peça com ligação 3D só aceita os modos 2 e 6) e os pontos de
ligação, derivados da malha (ADR-021/023). A `SIMBOLOGIA_3D.IMAGEM` é requisito para desenhar
(ADR-020) e a entidade IFC de origem atravessa o pipeline (ADR-026).

**Entradas que exigem operação de fora:** famílias `.rfa` e projetos `.rvt` (ADR-018/019 — a APS
**não aceita `.rfa`**; credenciais só no `.env` do criador, cache em `storage/bim/aps/`) e o plugin
de CAD que é casca de catálogo web (ADR-016; o download é um **cache retomável** por
`(host, categoria)` e depende de autorização de Termos de Uso — `plugin-cad-catalogo-web.md`).


**Pendências do usuário:**

**No Builder, com a biblioteca de válvulas e atuadores de HVAC já reexportada** (2026-09-11, com
engenheiro do Builder acompanhando). Verificados e corretos: disciplina (só Climatização),
"Pontos de ligação 3D" acendendo Sim/Não conforme a peça tem bocal, e a Aplicação — esta última
depois do conserto do vocabulário em inglês, **ainda a reconferir**. Faltam três:

1. **Posicionar simbologia 3D** — só se vê **lançando** a peça num projeto: ela entra orientada ou
   torta? A regra nova (modos 2 e 6) aparece de verdade numa biblioteca **hidráulica**, onde a
   conexão saía no modo 0 e agora sai no 6 — a curva tem de aceitar ficar deitada e de ponta-cabeça.
2. **Desenhar em 3D** (ADR-020) — a peça lançada mostra a geometria real no ambiente 3D.
3. **Planta e corte** (ADR-021) — sai o desenho da peça, não o símbolo padrão. Só nas peças com
   "Pontos de ligação 3D: Sim"; nas com "Não", o símbolo padrão é o esperado.

Também aguardam retestes as duas correções de 2026-09-11 (aplicação em inglês e posicionamento),
que só precisam de **reexportação** — o catálogo salvo já tem nome, geometria e disciplina certos.

**Três perguntas que só a engenharia do Builder responde**, todas com a medição pronta em
`docs/historico/sessoes/2026-09-11-auditoria-cruzada-da-documentacao.md`:

- o que é **"Ligação"** na aba de Entradas (`LIGACAO_EP`, 0 a 3, que gravamos fixo em 0; medido:
  **não** é índice da entrada);
- o Builder **usa o diâmetro da entrada em peça não-hidráulica**? No catálogo oficial o valor 2
  aparece em 10.097 de 13.665 entradas elétricas, qualquer que seja a bitola — parece omissão;
- **"Caixa de Cabos"** tem aplicação própria? O termo não existe no catálogo oficial, então hoje cai
  no genérico e não foi posto no vocabulário (seria ajustar o classificador a uma biblioteca só).

**Decisões abertas:**

- **Bitola em biblioteca elétrica:** `entradas_aq` converte raio → código em qualquer disciplina, e
  a escala é hidráulica. Copiar o **2** do catálogo é palpite sobre valor não documentado.
- **Traduzir a classe IFC de arquivo importado** (`IFCVALVE` → 2084): é o que falta para as fontes
  que não são `.aq` atravessarem a ponte da ADR-026. Depende de fechar nome → código das entidades
  de climatização, que são as que a ajuda não lista.
- Famílias Revit: as formas representativas de equipamento bastam? O trecho padrão de 1000 mm é o
  desejado? **APS: revogar e regerar o client secret** que passou pelo chat em 2026-09-06.
- LICENSE.
- Leitura humana dos 19 documentos de `docs/conhecimento/` e das quatro skills.
- Aceitação final (`docs/aceitacao.md` §4) do `.aq` do catálogo de plugin web e do de famílias Revit.
