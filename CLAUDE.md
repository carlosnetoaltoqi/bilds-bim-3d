# CLAUDE.md — bilds-bim-3d

Ponto de entrada para qualquer agente ou humano que trabalhe neste projeto.
Leia tudo antes de modificar qualquer arquivo.

---

## Regra fundamental: documentação primeiro

**Toda mudança de comportamento, bug corrigido ou decisão de arquitetura deve ser registrada neste arquivo antes de encerrar a sessão.**

Memória de agente e skills são auxiliares e podem não existir na próxima sessão — nem na próxima máquina. Este `CLAUDE.md` é a única fonte de verdade persistente e confiável. **Se a informação não está no repositório, ela não existe para o próximo agente.**

Fluxo obrigatório ao finalizar qualquer mudança:
1. Corrigir/implementar o código
2. Commitar
3. Atualizar este `CLAUDE.md` com o que mudou (seção "Histórico de sessões" e tabela de diagnóstico quando aplicável)
4. **Se aprendeu algo sobre ler `.aq`, ler IFC ou gerar as páginas de preview,
   atualizar também a skill correspondente** — ver "Skills" abaixo. Elas servem
   outros projetos e não podem ficar para trás.
5. Só então encerrar

---

## Este documento é autossuficiente

**Nada aqui depende de skills, memória de agente ou conhecimento de fora do repositório.**
Tudo o que é necessário para operar e evoluir o pipeline está neste `CLAUDE.md`, no
`README.md`, nos docstrings dos scripts e em `docs/`. Se você precisou de algo que
não está aqui, isso é uma falha desta documentação — registre-a antes de encerrar.

### Onde está cada conhecimento

| Assunto | Onde |
|---|---|
| Como usar o pipeline, os dois modos, layout da saída | `README.md` |
| Formato binário OQ3D, armadilhas do parser, API | este arquivo + docstring de `scripts/oq3d.py` |
| Schema do `.aq` e o que cada tabela guarda | este arquivo, "Conhecimento crítico: read_aq.py" |
| Inferência de fabricante e título | este arquivo + docstring de `peek_aq` em `scripts/build.py` |
| Parsing de IFC (só modo `--ifc`) | este arquivo + docstring de `scripts/parse_ifc.py` |
| Padrões dos templates HTML e Three.js | este arquivo, "Conhecimento crítico: templates HTML" |
| Contrato do ZIP consumido pela bilds.com | `docs/bilds-bim-3d-zip-spec.md` |
| Como a descoberta do OQ3D foi feita e validada | `docs/estudo-oq3d/` |
| Integração com dashboard e API | `docs/plano-integracao-bilds.md` — **histórico**, o módulo já foi shipado |
| Skills de agente (versionadas aqui) | `docs/skills/` |
| **POC de catálogo dinâmico (banco de dados, Node+React)** | **`docs/plano-produto-dinamico.md`** |
| Aprendizados arquiteturais da POC (ADRs, bugs, diretrizes para a reconstrução) | `docs/solutions/architecture-patterns/` |
| Vocabulário do domínio (GeometryStore, Import, Geometry Pointer) | `CONCEPTS.md` |
| **Como ESCREVER um `.aq` e OQ3D, e extrair catálogo de PDF** | **`eng-reversa/`** — ver `eng-reversa/README.md` |

### Skills — versionadas aqui, em `docs/skills/`

Três skills de agente cobrem o terreno técnico do projeto e **moram neste
repositório**:

| Skill | Assunto |
|---|---|
| `docs/skills/leitor-biblioteca-aq/` | ler `.aq`, schema do banco, formato OQ3D |
| `docs/skills/leitor-ifc/` | parsear IFC4, geometria, cores, armadilhas STEP |
| `docs/skills/pagina-biblioteca/` | gerar as páginas de catálogo com viewer 3D |

`~/.claude/skills/` recebe **symlinks** apontando para cá — existe uma cópia só,
e ela é versionada. Editar em qualquer um dos caminhos edita o arquivo do repo.

```bash
bash scripts/link_skills.sh     # recria os symlinks; idempotente
```

Rode isso depois de clonar. Se um diretório de mesmo nome já existir em
`~/.claude/skills/` com conteúdo diferente, o script o preserva como `.bak.<timestamp>`
em vez de sobrescrever.

**Para trabalhar neste projeto, as skills não são necessárias** — o `CLAUDE.md` e o
`README.md` bastam. Elas existem porque o conhecimento sobre `.aq`, IFC e viewers 3D
serve **outros projetos** também.

> **Ao descobrir qualquer coisa nova sobre leitura de `.aq`, leitura de IFC ou
> geração das páginas de preview, registre nos dois lugares: neste `CLAUDE.md` e na
> skill correspondente.** Vale para formato de arquivo, armadilha de parser,
> comportamento do AltoQi, padrão de template — qualquer aprendizado reaproveitável
> fora daqui. Bump a `version` no frontmatter da skill e anote no `## Histórico` dela.

Como as skills estão no git, essa atualização entra no mesmo commit da mudança que a
originou — e não se perde se a máquina sumir.

---

## 👉 Estado em 2026-09-02 — POC ENCERRADA, e a base está ZERADA

**A POC de catálogo dinâmico está encerrada, e em 2026-09-02 o banco e o storage foram
esvaziados de propósito.** Não há empresa, catálogo, importação nem produto. O código
está intacto e sobe normalmente — só não há dado nenhum dentro dele.

| O quê | Estado atual |
|---|---|
| `companies` · `bim_catalogs` · `bim_imports` · `bim_products` | **0 documentos em cada** |
| `www/storage/bim/{geo,thumbs,logos,geometrias}` | **0 arquivos** (os diretórios ficaram) |
| API e web | sobem e respondem certo no vazio — ver a tabela de estado vazio abaixo |

O que a API devolve nesse estado, conferido em 2026-09-02:

| Requisição | Resposta |
|---|---|
| `GET /catalogos/:empresa/:slug` | `404` |
| `GET /empresas/minha` | `404 empresa não encontrada` |
| `GET /importacoes/ultima` | `200` com corpo vazio |
| `POST /auth/login` | `200` com token — **não consulta o banco** (ADR 7.6) |
| `GET /{empresa}/{catalogo}` no web | `404` |
| `/empresa` sem sessão | `307` para `/login` |

> ⚠️ **Recarregar a POC exige os `.aq` da Dancor e da Amanco, que NÃO estão nesta
> máquina.** `input/` tem só as 7 bibliotecas da Intelbras e a Akato. Sem esses dois
> arquivos, o caminho de importação pela interface não tem o que ingerir — e as chaves em
> disco embutem o `importId`, então nada do que foi apagado é reconstituível a partir do
> que sobrou. Para exercitar a POC com o que existe aqui, importe uma biblioteca da
> Intelbras: são pequenas (10 a 60 peças) e atravessam o mesmo caminho.

### O que havia antes, e como foi validado (histórico)

A carga que existia até 2026-09-02 foi a da S5.2 — as duas bibliotecas reimportadas do
zero pela interface depois da correção do `oq3d.py` (S5.1). Ela **passou** em tudo o que
se pediu dela, e é a prova de que o caminho funciona ponta a ponta. Reconferido em
2026-09-02, antes de apagar:

| O quê | Estado então |
|---|---|
| Empresa | 1 em `companies` |
| Catálogo Dancor | `bomba-de-combate-a-incencio` — 13 produtos, `series-rows` |
| Catálogo Amanco | `pvc-esgoto-silentium` — 856 produtos, `catalog-grid` |
| Produtos | **869 — todos com `geoUrl` e `thumbUrl`** |
| Storage | 364 MB, 1.738 arquivos em `www/storage/bim` |
| Geometria | CAM-W21 2CV com **27.425 triângulos** = parser corrigido (seria 20.452 com o antigo) |
| Miniaturas | `200 image/webp`, imagem distinta por produto |
| Revalidação de cache (S6.1) | 1ª visita `200`, condicional com ETag `304` |
| Páginas públicas | ambas `200` no web (3000) e na API (4000) |

Registro da validação original em `docs/sessoes/S5.2-encerramento-poc.md`.

> **A resposta de `GET /catalogos/:empresa/:slug` tem raiz `{ catalog, products }`** — em
> inglês, e não `produtos` como o `catalog.json` do pipeline estático. Os campos do produto
> são `geoUrl`/`thumbUrl` (URLs relativas, que o Server Component converte em absolutas), e
> não `geoKey`/`thumbKey` — esses são os nomes no documento do Mongo. Vale saber antes de
> escrever qualquer cliente novo.

**Versão base estável:** o topo de `main`. Confira com `git log --oneline -1`.

### Duas linhas de trabalho

1. **Pipeline estático (esta é a linha madura).** `.aq` → catálogo → ZIP/preview → Vercel.
   É o que o resto deste arquivo documenta. Estável e em produção.
2. **POC de catálogo dinâmico** — **ENCERRADA em 2026-08-31.** As 14 sessões
   (S-rev a S4.3) mais a correção do parser (S5.1) e a validação final (S5.2) foram
   executadas. Aprendizados destilados em
   `docs/solutions/architecture-patterns/poc-catalogo-bim-dinamico-aprendizados.md`.
   O documento registra as respostas às cinco perguntas da POC, os bugs encontrados e
   as diretrizes para a reconstrução na bilds.com.

   O estado do banco e do storage está na tabela acima: **zerado desde 2026-09-02**. As
   duas bibliotecas que estavam carregadas — Dancor (13 produtos) e Amanco (856) — foram
   apagadas junto, e os `.aq` de origem não estão nesta máquina.

   **Miniaturas (S4.4, 2026-08-30) — resolvidas.** O rasterizador software foi substituído
   por Playwright + `templates/thumbs/harness.html` no `thumb-worker.ts`: a miniatura sai do
   **mesmo Three.js, mesmo `buildScene()` e mesma câmera** do viewer. Medido, contra o render
   do viewer: **47 dB de PSNR** (o piso da compressão WebP q=0,85) contra **27 dB** do
   rasterizador software. 13 produtos Dancor em **~6,3 s**. Ver
   `docs/solutions/architecture-patterns/thumb-qualidade-identica-ao-viewer.md` e
   `docs/sessoes/S4.4-thumbs-playwright.md`.

   Números de medição de S4.1 (para referência):
   - HTML inicial: 71.9 KB (SSR) vs 44 KB (estático) — 1.6× maior
   - 13 thumbs: 57 KB total (≈ igual nos dois modelos)
   - TTFB SSR: 177–254ms vs ~2ms local (CDN ~50ms)
   - LCP estimado: ~300ms (POC) vs ~100ms (CDN com thumbs) — 3× mais lento
   - Registro completo: `docs/sessoes/S4.1-medicao-comparativa.md`

   **Não há próxima sessão desta linha.** Quem for iniciar a reconstrução na bilds.com
   deve ler `docs/solutions/architecture-patterns/poc-catalogo-bim-dinamico-aprendizados.md`
   e `docs/plano-produto-dinamico.md` (seção 13 — o que a POC não implementa).

```bash
python3 scripts/build.py --all          # só as novas
python3 scripts/build.py --all --force  # refaz todas
```

> Versões antigas deste arquivo mandavam exportar
> `LD_LIBRARY_PATH=~/.local/chromium-libs/...` antes do build. **Nesta máquina esse
> diretório não existe** — as libs do Chromium (`libnss3`, `libnspr4`, `libasound2t64`)
> vieram do apt e já estão em `/usr/lib/x86_64-linux-gnu`. O export é inofensivo, mas
> inútil. A receita sem sudo continua documentada no `README.md`, para outras máquinas.

**`output/` está vazia** desde o commit `e391a8f` — só a landing da Vercel sobrevive.
Os 10 catálogos de `input/` são todos regeráveis com o comando acima.

### Dependência cruzada com o bilds.com

**A pasta `thumbs/` deixou de ser inerte:** a API do bilds.com (PR #1244, mergeado em
`develop` em 2026-08-28) agora extrai `thumbs/`, grava `thumbBaseUrl` no catálogo e o
viewer usa a imagem pronta em vez de gerar no browser. Consequência prática para este
repo: **um ZIP gerado sem `thumbs/` faz o catálogo voltar ao render dinâmico** — que
funciona, mas é o comportamento de 39,9 s de LCP que motivou toda a mudança. Se o build
avisar que pulou as miniaturas, resolva as dependências antes (ver “Miniaturas
pré-renderizadas”).

### Geometria — corrigida em 2026-08-30, já refletida em tudo

O `oq3d.py` e o `oq3d-parser.ts` emitiam menos geometria do que o `.aq` contém e
deslocavam instâncias rotacionadas. Resolvido (ver S5.1 no histórico) e **propagado**:
o banco da POC foi zerado e recarregado em 2026-08-31, então não há mais geometria do
parser antigo em lugar nenhum. Conferência rápida de que o dado é o novo:

```bash
python3 -c "import json;g=json.load(open('www/storage/bim/geo/<importId>/2cv-t-220-380v-inc-flg-ir3.json'));print(len(g['idx'])//3)"
# 27425 = parser corrigido   |   20452 = parser antigo
```

### Pendência conhecida

- **Deploy do preview na Vercel está sem catálogos** — `output/preview/` passou a ser
  gitignored (511 MB de geometria não entram no histórico), e a Vercel constrói a partir
  do git. Hoje ela serve só a landing. Decidir a estratégia: rodar o `build.py` na
  Vercel, servir a geometria de storage externo, ou aceitar o preview só local.
- **Catálogo não tem visibilidade — fica público no instante em que existe.**
  `bim-catalogs.schema.ts` não tem campo `status`/`visibility`, e
  `catalogos.controller.ts:31` filtra só por `companyId + slug`. O `publicado` da tabela de
  estado acima é status do *import* (`importacoes.service.ts:210`) — não existe equivalente
  no catálogo. Requisito para a bilds.com, não hardening opcional.

  > Isto **substitui** a antiga finding "GET /geometrias sem auth — adicionar guard".
  > Ela era inaplicável: um `AuthGuard` em `/geometrias` quebra a página pública, porque é
  > o viewer no browser do visitante que busca a geometria, sem token. E
  > `catalogos.controller.ts:22` também não tem guard — uma requisição anônima já devolve
  > os `geoUrl` de todos os produtos. Enumeração por adivinhação de id não é o risco:
  > `_id` é `crypto.randomUUID()` (`bim-products.schema.ts:8`). Análise completa em
  > `docs/sessoes/S6.1-cache-de-assets.md`, seção 6.
- **`STORAGE_PATH` é variável de ambiente, não commitada.** Está em `www/.env` (gitignored)
  como `STORAGE_PATH=../../storage/bim` (relativo a `apps/api/`). Sem ela a API lê de
  `apps/api/storage` e não encontra as geometrias. O `DiskGeometryStore` faz
  `path.resolve()` no construtor — caminhos relativos são aceitos desde que o `.env` exista.

### Variáveis de ambiente — `www/.env`

**O template versionado é `www/.env.example`.** Copie e preencha:

```bash
cp www/.env.example www/.env
```

| Variável | Para quê |
|---|---|
| `MONGODB_URI` | Conexão do Mongo. A POC usou um Atlas M0, mas **nada no código depende do Atlas** — um `mongodb://127.0.0.1:27017` local serve. |
| `MONGODB_DB` | Nome do banco (`bilds-bim-3d`). |
| `SEED_USER` / `SEED_PASSWORD` | Login da POC. **Não consultam o banco** — `auth.controller.ts` compara direto com as variáveis (ADR 7.6). |
| `JWT_SECRET` | Assina o token. Gere com `python3 -c "import secrets; print(secrets.token_hex(32))"`. |
| `STORAGE_PATH` | Onde o `DiskGeometryStore` grava. Relativo ao CWD da API (`www/apps/api`). |

O pipeline estático (`scripts/build.py`) **não usa nenhuma delas** — lê só o `.aq`.
A configuração daquele lado é o `config.example.json` da raiz.

### ⚠️ A API não sobe e o Mongoose culpa o whitelist — como saber se é isso mesmo

Documentado em 2026-09-02, depois de perder tempo com isso. O Atlas usado pela POC é um
M0 com **whitelist de IP**, e o IP de uma máquina doméstica ou de escritório muda. Quando
ele muda, a API entra em retry infinito e **não responde a nenhuma requisição**:

```
ERROR [MongooseModule] Unable to connect to the database. Retrying (1)...
MongooseServerSelectionError: Could not connect to any servers in your MongoDB Atlas
cluster. One common reason is that you're trying to access the database from an IP that
isn't whitelisted.
```

**Essa mensagem é um texto fixo do driver, não um diagnóstico** — ela aparece igual para
DNS quebrado, rede bloqueada, cluster pausado, credencial errada e IP não liberado. Não
acredite nela; meça as quatro camadas, de baixo para cima. Rode de `www/apps/api/`, onde
as dependências resolvem:

```bash
cd www/apps/api
NODE_PATH=$(pwd)/node_modules node -e "
require('dotenv').config({path:'../../.env'});
const {MongoClient}=require('mongodb');
new MongoClient(process.env.MONGODB_URI,{serverSelectionTimeoutMS:12000}).connect()
 .then(()=>console.log('CONECTOU'))
 .catch(e=>{console.log(e.name);
   if(e.reason&&e.reason.servers)for(const[k,v]of e.reason.servers)
     console.log(' ',k,'->',v.error?v.error.message.split('\n')[0]:v.type);});"
```

| Camada | Como conferir | Se falha aqui |
|---|---|---|
| DNS SRV | `dns.resolveSrv('_mongodb._tcp.<cluster>.mongodb.net')` | cluster apagado, ou DNS da máquina |
| TCP :27017 | `net.createConnection` no primeiro nó do SRV | firewall ou rede bloqueando saída |
| **TLS** | o comando acima | **é aqui que o whitelist aparece** |
| Autenticação | idem, erro seria `AuthenticationFailed` | usuário ou senha errados |

**A assinatura do IP não liberado é TLS, não autenticação:**

```
tlsv1 alert internal error ... SSL alert number 80
```

nos **três** nós do shard, **com o TCP abrindo normalmente**. O Atlas aceita a conexão e
derruba no handshake — nunca se chega a mandar credencial. Se o TCP conecta e o TLS morre
com alert 80, é whitelist (ou o cluster pausado, que dá o mesmo alert).

**Como resolver:** no Atlas, *Network Access → Add IP Address → Add Current IP Address*.
Descubra o IP com `curl -s https://api.ipify.org`. Num M0, confira também se o cluster não
foi pausado — o Atlas pausa por inatividade e o sintoma é idêntico.

**A API se recupera sozinha:** o `MongooseModule` fica em retry, então depois de liberar o
IP ela conecta no próximo ciclo. Não é preciso reiniciar o processo.

> **Nada no código depende do Atlas** — um `mongodb://127.0.0.1:27017` local serve e
> elimina o whitelist do caminho. O custo é reimportar as bibliotecas, o que exige os
> `.aq` de origem.

---

## O que é este projeto

Pipeline local para gerar catálogos BIM interativos com viewer 3D a partir de
bibliotecas `.aq` do AltoQi Builder. Produz dois artefatos:

1. **Preview HTML standalone** (`output/preview/`) — visualização local ou via Vercel
2. **ZIP para bilds.com** (`output/<origem>/<slug>-AAAAMMDDHHMM.zip`) — upload no dashboard

O projeto é independente do `bilds-code-vercel` (apps/lps, vagas, seo).
Clonado em qualquer máquina, produz o mesmo resultado dado os mesmos inputs.

### A decisão central: a geometria vem do .aq, não do IFC

**O `.aq` carrega a malha 3D completa, com cor e miniatura.** Está no BLOB
`SIMBOLOGIA_3D.SIMBOLOGIA_3D`, no formato binário proprietário **OQ3D** — o mesmo
sólido que o AltoQi exporta como IFC. Os IFCs deixaram de ser necessários.

Validado em três bibliotecas de domínios e schemas distintos; ver
"Sessão 2026-08-24 — estudo OQ3D" no histórico. Ganhos:

- **85× a 421× mais rápido** que parsear os IFCs equivalentes
- **um arquivo de entrada** em vez de um `.aq` mais uma árvore de IFCs
- **zero matching por nome** — o vínculo peça → geometria é chave estrangeira
- os cinco bugs de parsing STEP documentados abaixo deixam de existir

---

## Fluxo do usuário

```
1. Clonar este repo
2. bash scripts/setup_vendor.sh   (baixa Three.js para templates/vendor/)
3. pip install -r requirements.txt
3b. npm install                   (miniaturas; opcional — sem isso o build só as pula)
    sudo apt-get install -y libnss3 libnspr4 libasound2t64
4. Copiar as bibliotecas .aq para input/, organizadas por fabricante:
       input/Dancor/pecas_dancor_bombas.aq
       input/Amanco/PVC Esgoto SN, SR e Silentium/pecas_amanco.aq
5. python3 scripts/build.py --all      ← um ZIP por .aq, sem perguntas
   (ou: python3 scripts/build.py       ← uma biblioteca, com perguntas)
6. Preview local: python3 -m http.server 8080 --directory output/preview
7. Subir output/<origem>/<slug>-AAAAMMDDHHMM.zip no dashboard.bilds.com → BIM 3D
```

### Os dois modos

| Modo | Comando | Geometria vem de |
|---|---|---|
| **Padrão** | `build.py` / `build.py --all` | do próprio `.aq` (OQ3D) |
| **Compatibilidade** | `build.py --ifc` | dos arquivos `.IFC` da pasta |

**Quando usar `--ifc`** — só nestes dois casos:

1. **Há peças em IFC ausentes do banco.** Caso real: a bomba 89-62 TJM da Dancor
   tem `.IFC` na pasta mas não existe no `.aq`, nem como `PECA`. Sem `--ifc` ela
   fica de fora. É o mesmo cenário que o `products_override` cobre.
2. **Conferir uma fonte contra a outra**, ao validar uma biblioteca nova.

Fora isso não use: é mais lento, exige `ifcopenshell` para IFCs B-rep e depende
do matching por nome, que erra em catálogos grandes (ver `find_aq_product`).
Com `--ifc`, os IFCs precisam estar **na mesma pasta do `.aq`** correspondente.

### Modo lote (`--all`)

Varre `input/` recursivamente, gera um catálogo por `.aq` e **espelha a estrutura
de pastas na saída**:

```
input/Amanco/linha/pecas.aq  →  output/Amanco/linha/<slug>-<ts>.zip
input/Dancor/pecas.aq        →  output/Dancor/<slug>-<ts>.zip
```

Bibliotecas que já têm ZIP no destino são **puladas**; `--force` refaz. Nada é
perguntado — fabricante, título e layout saem da inferência. Uma falha não
interrompe o lote: é registrada e o build segue para a próxima.

### O que é inferido automaticamente

| Campo | Fonte | Pergunta? |
|---|---|---|
| Fabricante | Prefixo de `CLASSE_SIMBOLOGIA_3D.NOME_CLASSE` (`"AMANCO - PVC Esgoto SN"`) → pasta avô → pasta pai → 1º token do filename | Sim (não no `--all`) |
| Título | Pasta pai, se diferente do fabricante → tokens do filename → prefixo comum das linhas | Sim (não no `--all`) |
| Slug | `slugify(titulo)` — automático | Não, só exibido |
| Descrição | Nenhuma fonte automática | Sim, opcional |
| Layout | `series-rows` com curvas Q-H; `catalog-grid` acima de 6 peças | Sim (não no `--all`) |
| Geometria | `PECA_SIMBOLOGIA_3D` — chave estrangeira | Nunca |

> **Fabricante e título jamais podem sair vazios ou em forma de slug** — são o
> cabeçalho da página publicada. A cascata acima sempre produz algo legível.
> `PECA.BIBLIOTECA`, que era a fonte primária antiga, está **vazia nas três
> bibliotecas testadas**: não confie nela.

Quando o `.aq` detectado difere do `aq_file` do `config.json` (`aq_stale`),
fabricante, título e file_map são resetados — nunca herdam do catálogo anterior.

---

## Estrutura do projeto

```
bilds-bim-3d/
├── CLAUDE.md                    ← você está aqui
├── README.md                    ← guia para o usuário final
├── config.example.json          ← template de configuração
├── config.json                  ← criado pelo build, gitignored
├── requirements.txt             ← Jinja2 + numpy (ifcopenshell só p/ --ifc)
├── package.json                 ← playwright, só para o passo de miniaturas
├── vercel.json                  ← serve output/preview/ como site estático
├── scripts/
│   ├── build.py                 ← pipeline principal (entry point)
│   ├── oq3d.py                  ← OQ3D binário → malha 3D  ★ caminho padrão
│   ├── read_aq.py               ← .aq AltoQi → dados, metadados e simbologias
│   ├── parse_ifc.py             ← IFC4 → JSON de geometria (só no modo --ifc)
│   ├── dedup.py                 ← deduplicação de vértices (~79% redução)
│   ├── thumbs.mjs               ← render das miniaturas no Chromium (Node)
│   ├── setup_vendor.sh          ← baixa Three.js para templates/vendor/
│   └── link_skills.sh           ← liga docs/skills/ a ~/.claude/skills/
├── templates/
│   ├── layouts/
│   │   ├── series-rows.html     ← rows estilo Netflix por série (bombas)
│   │   └── catalog-grid.html    ← grid denso com filtros (conexões)
│   ├── thumbs/
│   │   └── harness.html         ← página de render das miniaturas (não vai ao ZIP)
│   └── vendor/                  ← vazio no repo; setup_vendor.sh baixa o Three.js aqui
├── input/                       ← bibliotecas do usuário — gitignored
│   └── <Fabricante>/[<Linha>/]<pecas>.aq
└── output/                      ← gerado pelo build
    ├── <origem>/<slug>-<ts>.zip        ← ZIP para bilds.com (gitignored)
    ├── <origem>/<slug>-catalog.json    ← catálogo solto (gitignored)
    ├── geo/<origem>/<slug>/*.json      ← geometria por produto (gitignored)
    ├── thumbs/<origem>/<slug>/*.webp   ← miniatura por geometria (gitignored)
    └── preview/                        ← site estático — gitignored, EXCETO index.html
        ├── index.html                  ← landing, feita à mão: a única coisa versionada aqui
        ├── catalogs.json               ← índice dos catálogos gerados
        ├── vendor/                     ← Three.js, copiado de templates/vendor/
        └── <slug>/
            ├── index.html
            ├── catalog.json
            └── data/*.json             ← geometria servida ao viewer
```

> **`output/` espelha a estrutura de `input/`.** Os padrões do `.gitignore`
> precisam de `**` (`output/**/*.zip`), porque a saída é aninhada — `output/*.zip`
> só pegaria a raiz.

⚠️ **`output/preview/index.html` é a única coisa em `output/` que NÃO é regenerável.**
É a landing do demo na Vercel — feita à mão, versionada, e **nenhum script a gera**. O
`build_preview()` só escreve `output/preview/<slug>/index.html`, um por catálogo.

Isso torna `output/` enganosa: parece descartável inteira, e não é. Ao limpar, preserve
esse arquivo:

```bash
cp output/preview/index.html /tmp/landing.html
find output -mindepth 1 -maxdepth 1 -exec rm -rf {} +
mkdir -p output/preview && cp /tmp/landing.html output/preview/index.html
```

Todo o resto — `geo/`, `thumbs/`, ZIPs, `catalog.json`, os `preview/<slug>/` e o
`preview/vendor/` — volta com `python3 scripts/build.py --all --force`. O `vendor/` é
copiado de `templates/vendor/`, então rode `scripts/setup_vendor.sh` antes se estiver
em clone novo.

---

## config.json — schema completo

```json
{
  "slug":        "bombas-incendio",
  "titulo":      "Bombas de Combate a Incêndio",
  "fabricante":  "Dancor",
  "descricao":   "Linha CAM-W e TJM para sistemas de combate a incêndio.",
  "layout":      "series-rows",
  "aq_file":     "input/pecas_dancor.aq",
  "ifc_dir":     "input/",
  "file_map": {
    "CAM-W10.IFC": "cam-w10",
    "CAM-W14.IFC": "cam-w14"
  },
  "products_override": [
    {
      "id": "89-62",
      "nome": "CAM 89-62 TJM 50CV",
      "serie": "TJM",
      "geo": "cam-89-62-tjm",
      "potencia": 50,
      "conexoes": "2½\" × 2½\"",
      "specs": { "Tensão": "Trifásico 220/380V", "Rotação": "3.500 rpm · 60Hz" },
      "curva": null
    }
  ]
}
```

`products_override`: produtos presentes nos IFCs mas ausentes no .aq.
`file_map`: mapeamento nome-exato-do-arquivo.IFC → slug-de-saída.

---

## catalog.json — schema de saída

```json
{
  "slug": "bombas-incendio",
  "titulo": "Bombas de Combate a Incêndio",
  "fabricante": "Dancor",
  "descricao": "...",
  "layout": "series-rows",
  "filtros": ["W", "TJM"],
  "produtos": [
    {
      "id": "cam-w10",
      "nome": "CAM-W10 1CV T 220/380V INC FLG IR3",
      "serie": "W",
      "geo": "cam-w10.json",
      "potencia": 1.0,
      "conexoes": "1½\" × 1½\"",
      "specs": { "Tensão": "Trifásico 220/380V", "Rotação": "3.500 rpm · 60Hz" },
      "curva": [[0,30,1.1,0],[3,25,1.2,42],[6,18,1.3,58],[9,8,1.2,48]]
    }
  ]
}
```

`curva`: lista de [vazao_m3h, altura_mca, potencia_cv, rendimento_%] por ponto.
`curva: null` para produtos sem curva Q-H.

---

## Layouts disponíveis

| Layout | Arquivo | Quando usar |
|---|---|---|
| `series-rows` | `templates/layouts/series-rows.html` | Poucas séries (2–4), muitas variantes, produto com curva Q-H. Ex: Dancor |
| `catalog-grid` | `templates/layouts/catalog-grid.html` | Muitos itens heterogêneos (20+), filtros por categoria. Ex: Amanco |

Para adicionar um novo layout:
1. Criar `templates/layouts/meu-layout.html` usando os mesmos padrões (ver seção abaixo)
2. Usar `"layout": "meu-layout"` no config.json

### Padrão obrigatório nos templates

Os templates usam **dois scripts** para resolver o timing do Three.js:

- **Script sync** (inline, sem `type="module"`): renderiza cards no DOM,
  dispara `CustomEvent('cards-rendered')` ao terminar.
- **Script module** (`type="module"`): importa Three.js, ouve o evento,
  acessa os `<canvas>` que já existem no DOM.

O importmap **deve vir antes** de qualquer `<script type="module">`:
```html
<script type="importmap">{"imports":{"three":"/vendor/three.module.js"}}</script>
```

Dados injetados via Jinja2:
```html
<script>
const CATALOG = {{ catalog | tojson | safe }};
const ITEMS   = CATALOG.produtos;
</script>
```

Fallback sem Jinja2: `build.py` substitui `{{ catalog | tojson | safe }}` por string literal.

---

## ZIP para bilds.com — conteúdo

O arquivo é gerado em `output/<slug>-AAAAMMDDHHMM.zip` (ex: `dancor-bombas-incendio-202608241530.zip`).

```
<slug>-AAAAMMDDHHMM.zip
├── manifest.json    { slug, title, manufacturer, description, layout, filters, productCount }
├── catalog.json     dados completos dos produtos (campos em português)
├── geo/
│   ├── cam-w10.json
│   └── cam-w14.json
│   ...
└── thumbs/          ← miniaturas pré-renderizadas (ver seção abaixo)
    ├── cam-w10.webp
    └── cam-w14.webp
    ...
```

O dashboard.bilds.com lê `manifest.json` para exibir o nome/slug antes de processar
o zip inteiro. `catalog.json` e `geo/*.json` vão para S3, registrados no MongoDB.

> **Atenção:** `manifest.json` usa campos em **inglês** (contrato da API bilds.com).
> `catalog.json` usa campos em **português** (convenção de dados apresentados ao usuário).

Contrato completo do ZIP: `docs/bilds-bim-3d-zip-spec.md`.

---

## Miniaturas pré-renderizadas — por que e como

### O problema que elas resolvem

O card do catálogo sempre foi `<img>`, mas a imagem era **gerada no browser do
visitante**: baixa o JSON de geometria, monta a `BufferGeometry`, renderiza com WebGL,
`toDataURL`. Por card visível, a cada carregamento — o cache do viewer é um `Map` em
memória, que morre no reload.

Lighthouse em produção, `bilds.com/dancor/bombas-incendio` (2026-08-27):

| Sinal | Valor |
|---|---|
| Elemento LCP | o próprio `<img src="data:image/jpeg;base64,…">` do card |
| LCP | **39,9 s** (score 0) — **7.230 ms** só de _element render delay_ |
| Geometria baixada | **3,75 MB para 2 cards** (viewport mobile) |
| Compressão | **nenhuma** — `transfer 1.765 KB / resource 1.763 KB` |
| Peso total | 6.610 KiB, 57% geometria |

No desktop são ~12 cards na primeira viewport: **40 MB** na Dancor.

### Como funciona

```
build.py  →  build_thumbs()  →  node scripts/thumbs.mjs <config.json>
                                    ├── sobe servidor estático sobre ROOT
                                    ├── abre templates/thumbs/harness.html no Chromium
                                    └── window.renderThumb(url) por geometria → .webp
```

`harness.html` carrega o **mesmo Three.js** de `templates/vendor/` e tem cópia literal do
`buildScene()` e da câmera dos layouts. É o que garante que a miniatura pré-gerada seja a
imagem que a página produziria.

**O harness tem dois consumidores** desde a S4.4:

| Consumidor | Função do harness | Origem dos dados |
|---|---|---|
| `scripts/thumbs.mjs` (pipeline estático) | `window.renderThumb(url, …)` | `fetch` do JSON servido |
| `www/tools/thumb-rasterizer.ts` (POC / API) | `window.renderThumbFromData(data, …)` | objeto já em memória |

`renderThumb` é um wrapper: faz o `fetch` e delega para `renderThumbFromData`, que é a
única função que toca WebGL. Os dois caminhos produzem a mesma imagem por construção.

> ⚠️ **Ao mexer em material, luz ou câmera nos layouts, mexa no `harness.html` junto.**
> São quatro cópias hoje — os dois layouts, o harness, o `bim-viewer-engine.ts` do
> bilds.com e o `bim-viewer-engine.ts` do POC (`www/apps/web/src/components/bim-catalog/`).
> Divergir faz o catálogo exibir dois visuais conforme o produto tenha ou não
> miniatura pronta.

### Parâmetros

| Item | Valor | Onde |
|---|---|---|
| Dimensão | 448 × 324 (2× o card de 224×162, para DPR 2) | `THUMB_W/H` em `build.py` |
| Formato | WebP q=0,85 | `THUMB_MIME/QUALITY` |
| Fundo | `#F3F4F6` opaco, igual ao `setClearColor` do viewer | `harness.html` |
| pixelRatio | fixo em 1 (no runtime é `min(dpr, 1.5)`) | `harness.html` |

**Uma miniatura por geometria, não por produto** — a câmera sai só do bounding box, então
geometria compartilhada dá imagem idêntica. Amanco: 856 produtos → 448 miniaturas.

### Dependências e degradação

Precisa de **Node >= 20** (exigência do Playwright) e do Chromium:

```bash
npm install                                            # playwright + Chromium
sudo apt-get install -y libnss3 libnspr4 libasound2t64  # libs de sistema
```

⚠️ **Armadilha do `sudo`.** A documentação do Playwright manda rodar
`sudo npx playwright install-deps chromium`. **Não funciona em máquina com nvm:** o
`sudo` do Ubuntu usa `secure_path` e descarta o PATH do usuário, então o `npx` resolve
`node` para `/usr/bin/node` — o do apt, v18 aqui — e o Playwright recusa com _"requires
Node.js 20 or higher"_. O engano é convincente porque `node --version` no shell mostra a
versão nova, e `nvm default` também. O `apt-get` acima instala as mesmas quatro libs
(`libnspr4.so`, `libnss3.so`, `libnssutil3.so`, `libasound.so.2`) sem envolver Node.
Querendo o comando do Playwright, repasse o PATH através do sudo:
`sudo env "PATH=$PATH" npx playwright install-deps chromium` — validado nesta máquina.

⚠️ **Armadilha dos dois Node** (distinta da anterior, e afeta o build, não a instalação). É comum a máquina ter o Node do apt em `/usr/bin/node`
(velho) e um do nvm (novo). O nvm só entra no PATH em shell interativo, então um
`subprocess` do Python pega o do apt — e o Playwright recusa com "requires Node.js 20 or
higher", sem dizer que existe um Node bom instalado. Por isso `_find_node()` procura, em
ordem: `$BILDS_NODE`, o `node` do PATH, e a maior versão em `~/.nvm/versions/node/`.

Sem sudo para as libs de sistema, dá para extrair os `.deb` localmente e exportar
`LD_LIBRARY_PATH` — receita no `README.md`, seção "Miniaturas".

**Sem isso o build não quebra.** `build_thumbs()` avisa e segue: os produtos ficam sem
`thumb`, o ZIP sai sem `thumbs/`, e o viewer do bilds.com usa o render dinâmico de
sempre. Mesma coisa com `--skip-thumbs`.

Em máquina sem GPU (WSL, CI, container) o Chromium roda WebGL por SwiftShader — os flags
`--use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader` estão no
`thumbs.mjs` e são obrigatórios; sem eles o WebGL não inicializa em headless. O
`thumb-rasterizer.ts` acrescenta `--no-sandbox`, necessário quando o processo já roda sem
privilégios de namespace (worker forkado em container).

### ⚠️ Nunca passe geometria como objeto para `page.evaluate`

O serializador de argumentos do Playwright anda o grafo do objeto — e a geometria é um
array de centenas de milhares de números. Medido numa peça Dancor de 4,8 MB (35 k
vértices, 52 k triângulos):

| Forma do argumento | Tempo por thumb |
|---|---|
| objeto `{pos, col, idx}` | ~2 200 ms |
| **string JSON**, com `JSON.parse` dentro da página | **~370 ms** (dos quais ~120 ms são o WebGL) |

`JSON.stringify` no Node custa 40 ms e o `JSON.parse` na página, 13 ms — o resto é puro
ganho. No lote de 13 produtos da Dancor: **24,5 s → 6,2 s**. É a diferença entre estourar
e cumprir o orçamento de tempo do import.

---

## Conhecimento crítico: oq3d.py — a geometria dentro do .aq

Formato **OQ3D** (`OQ3D 3D Objects File`), no BLOB `SIMBOLOGIA_3D.SIMBOLOGIA_3D`.

### Cabeçalho — 37 bytes, e um deles é informação

Documentado em 2026-09-02, junto com o escritor. O `oq3d.py` só procura a assinatura e
pula direto para a árvore, mas o cabeçalho tem um campo útil:

```
offset  bytes                      significado
0       3a 01 01 00 00             5 bytes OPACOS, idênticos nas 12 bibliotecas
5       'OQ3D 3D Objects File'     20 bytes de assinatura
25      02 00 00 00                u32 = 2, versão do arquivo
29      N  00 00 00                u32 = NÚMERO DE OBJETOS-RAIZ
33      00 00 00 00                u32 = 0
```

Os 5 primeiros bytes são constantes nas 12 bibliotecas e nas 6 versões de schema
(552–607). Não se sabe o que significam; sabe-se que não variam.

> **O campo em +29 serve de verificação de parse, e revela um defeito real.**
> O parse encontra **sempre mais** raízes do que o cabeçalho declara, nunca menos.
> Medido em **todas** as 783 geometrias das 12 bibliotecas de fabricante: **54 divergem
> (6,9%), em 6 bibliotecas** — as cinco da Intelbras que têm geometria e a Maxbar, esta com
> 31 de 135.
> 
> A diferença vai de **+2 a +10 e não é sempre par** (+7 e +9 aparecem), o que descarta
> "um `0x5D` desempilha um nível e promove dois filhos" como regra única: o
> desempilhamento espúrio acontece em quantidade variável dentro do mesmo blob.
>
> A geometria emitida não muda — o `_collect` desce a árvore toda —, mas a hierarquia
> muda, e com ela a composição dos transforms dos nós promovidos. Nas seis bibliotecas
> afetadas (Intelbras e Maxbar, ambas de equipamento) as malhas já vêm em coordenadas de
> mundo, então não aparece; numa biblioteca de conexões deslocaria a peça.
>
> O `parse()` passou a avisar com `OQ3DAvisoParse` quando isso acontece (2026-09-02).

Árvore de objetos serializada no estilo Delphi:

```
0x5B <len:u32> <ClassName>   abre um objeto
...payload...
0x5D                         fecha
```

### Classes que carregam dados

```
TQi3DIndexedTriangleMeshData
    u32 versao(=2) | u32 nCoords | u32 reservado
    nCoords doubles                 → nCoords/3 vértices (x,y,z)
    u32 nIdx | u32 reservado
    nIdx u32                        → nIdx/3 triângulos
TCoatingColor
    u32 versao | u32 flag | u8 R | u8 G | u8 B | u8 A    (cor UNIFORME da malha)
TCoordinateTransformation3D
    u32 versao | 12 doubles         → rotação 3×3 COLUMN-major + translação
```

**A rotação é column-major:** o elemento `(i, j)` está em `r[j*3 + i]`. Lida como
row-major, sai transposta e desloca toda instância cuja rotação não seja
simétrica. `parse()` já devolve transposta para row-major.

Hierarquia: `TQi3DReusedObject(guid)` → `TQi3DReusableObject` (definição inline,
opcional) → `TQi3DTriangleMesh` → `TCoatingColor` + malha. O **último**
`TCoordinateTransformation3D` filho direto é o que posiciona; o par origem/alvo
espelha `MappingOrigin`/`MappingTarget` do IFC.

### Correspondência com o IFC

| OQ3D | IFC4 |
|---|---|
| `TQi3DObjectGroup` | `IFCELEMENTASSEMBLY` |
| `TQi3DReusableObject` | `IFCREPRESENTATIONMAP` |
| `TQi3DReusedObject` | `IFCMAPPEDITEM` |
| `TQi3DIndexedTriangleMeshData` | `IFCTRIANGULATEDFACESET` |
| `TCoordinateTransformation3D` | `IFCLOCALPLACEMENT` |
| `TCoatingColor` | `IFCINDEXEDCOLOURMAP` |

A contagem de entidades bate exatamente (18 `TQi3DReusedObject` ↔ 18
`IFCMAPPEDITEM`): o exportador IFC é tradução direta desta estrutura.

### Unidades

**Centímetros, Z-up** — a mesma orientação do IFC nativo.
Para Three.js: `x, y=z, z=-y`, multiplicado por 0.01.
Para **escrever** OQ3D a partir de geometria de viewer, o inverso:
`oq3d_x = three_x·100`, `oq3d_y = −three_z·100`, `oq3d_z = three_y·100`.

### Escrever OQ3D

Feito em 2026-09-02: `eng-reversa/tools/oq3d_writer.py`. Anatomia byte a byte em
`eng-reversa/estudo/02-escrever-oq3d.md`. O que muda em relação a ler:

O `oq3d.py` é um leitor **tolerante** — varre à procura de `0x5B`/`0x5D` e consome por
inteiro só os três blocos de tamanho conhecido (malha, cor, transform), pulando todo o
resto. Um escritor não tem essa liberdade, e o resto é justamente o que ele precisa
saber. A moldura foi copiada byte a byte da `SIMBOLOGIA_3D` 169 da Amanco, com buracos
só nos dados que se controla.

Três coisas que só aparecem escrevendo:

- **A cor é gravada duas vezes** — no payload de `TQi3DTriangleMesh` e em
  `TCoatingColor`, com os mesmos 4 bytes. O leitor usa só a segunda; o escritor tem de
  pôr as duas.
- **A rotação tem de ser transposta de volta para colunas.** O `parse()` devolve
  row-major; gravar assim produz a transposta, e a instância sai do lugar **sem mudar
  nenhuma contagem** — o bug da S5.1, do lado da escrita. O teste que pega isso grava a
  rotação e a sua transposta e confere que dão resultados diferentes; sem essa
  contraprova, uma rotação simétrica passaria e não provaria nada.
- **Nada é alinhado.** O `double` do payload de `TQi3DReusedObject` começa num offset
  que não é múltiplo de 8.

O escritor emite uma malha por objeto-raiz, sempre com a definição inline
(discriminador `0x02`). Não gera instância por referência (`0x01`), `TQi3DObjectGroup`
nem `WIREFRAME`. Custo de não reaproveitar malha: reescrever a `SIMBOLOGIA_3D` 169 da
Amanco dá 52.249 bytes contra 51.927 do original — **1,01×**.

> **Malha inventada precisa de checagem topológica, e de olhar.** `eng-reversa` gerou
> forma paramétrica para 262 peças, e dois defeitos passaram por bounding box, contagem
> de triângulos e round-trip binário: (a) perfis de revolução que fecham em si mesmos
> ficavam com `2 × lados` arestas de borda — sólido que parece fechado e mostra o
> interior pela costura; (b) malhas corretas em posições relativas erradas — colar de
> joelho solto do corpo, sifão desmontado. A primeira classe se pega contando arestas
> compartilhadas por exatamente dois triângulos; **a segunda só se pega abrindo e
> olhando** (`eng-reversa/tools/olhar_preview.mjs`).

### Armadilhas

| Armadilha | Consequência |
|---|---|
| Ignorar os transforms | Funciona em equipamentos (malhas já em coordenadas de mundo) e **quebra** em conexões, montadas de malhas reaproveitadas — joelhos saem retos. Use sempre o parser de árvore. |
| Buscar `0x5B` junto do byte anterior | O byte que precede varia (`\x02\x5b`, `\x01\x09\x00\x00\x00\x5b`…). Ancore só no `0x5B`. |
| Varrer delimitadores byte a byte | `0x5B`/`0x5D` ocorrem dentro de doubles. Consuma por inteiro os blocos de tamanho conhecido antes de varrer. |
| Somar bocais na bounding box | Verde `(1,154,63)` e azul `(10,84,152)` são marcadores de conexão, não produto — inflam a bbox em ~2 cm. Use `skip_markers=True`. |
| `SELECT *` em `SIMBOLOGIA_3D` | Traz o `WIREFRAME`: 69–71% do arquivo (285 MB dos 412 MB da Amanco), inútil para viewer web. |
| Esquecer o `dedup()` | O caminho `.aq` **precisa** dedupar como o IFC faz. Sem isso o preview foi de 148 MB para 571 MB. |
| Ler a rotação como row-major | Ela é **column-major**. Sai transposta: instância rotacionada fora do lugar, sem mudar a contagem de triângulos. |
| Ignorar instâncias que referenciam a definição | 1.096 das 2.960 instâncias não trazem malha inline — some ~31% dos triângulos na Amanco. |

### API

```python
import oq3d
oq3d.is_oq3d(blob)                     # valida assinatura
oq3d.parse(blob)                       # árvore de nós
oq3d.extract(blob, skip_markers=True)  # [(verts_cm, tris, rgba)] com transforms
oq3d.to_buffers(blob)                  # {'pos','col','idx'} em metros, Y-up
oq3d.bbox(blob) / oq3d.stats(blob)     # validação e logs
```

### Instâncias repetidas — RESOLVIDO em 2026-08-30

A maioria dos `TQi3DReusedObject` **não** traz a definição inline: referencia uma
`TQi3DReusableObject` já serializada. Layout do payload:

```
+0   u32 versão (2 ou 3)
+28  u32 tamanho do GUID (sempre 36)
+32  GUID, 36 bytes ASCII    ← ÚNICO POR INSTÂNCIA, nunca foi a chave
...  bloco de 15 bytes (versão 2) ou 16 bytes (versão 3)
+B   u8 discriminador:  0x02 = definição inline  |  0x01 = seguem 4 bytes de referência
```

**A referência é o índice de serialização, base 1, contado sobre TODOS os objetos
da árvore em ordem de documento.** As duas hipóteses antigas foram testadas e
refutadas: o `u32` em `+8` é um id de instância (valores 2..19 na CAM-W21 2CV,
todos distintos — não índice de definição), e "a última definição vista" não
explica o padrão. Só as sete classes de `CLASSES` aparecem no fluxo, então o
contador não dessincroniza — verificado varrendo as 10 bibliotecas.

Validado: 2.960 `TQi3DReusedObject`, dos quais **1.096 por referência — todos**
resolvem para uma `TQi3DReusableObject`.

> Junto com este bug havia um segundo, que só apareceu ao conferir contra o IFC:
> a rotação de `TCoordinateTransformation3D` é **column-major**. Ele não muda a
> contagem de triângulos, só a posição — por isso passou despercebido. Era ele o
> responsável pela peça "solta no ar", não o das instâncias repetidas.

### Como conferir o parser contra o IFC

```bash
python3 docs/estudo-oq3d/valida_ifc.py Dancor        # exato: 13/13 pontos idênticos
python3 docs/estudo-oq3d/valida_ifc.py Amanco --limite 80
```

Em biblioteca tessellated (`IFCTRIANGULATEDFACESET`, ex. Dancor) a conferência é
exata: reconstrói-se o IFC do STEP (placement do produto × mapped item) e
compara-se o **conjunto de pontos**. Em B-rep (`IFCADVANCEDBREP`, ex. Amanco) a
tesselação é independente e só a forma é comparável.

Três armadilhas ao comparar, todas já resolvidas dentro do script:

| Armadilha | Por quê |
|---|---|
| Comparar só a bounding box | Uma rotação e a sua transposta podem gerar a **mesma** caixa. Compare os pontos. |
| Alinhar pelo centróide | O OQ3D guarda várias malhas como sopa de triângulos, o IFC solda os vértices — os centróides têm pesos diferentes. Alinhe pelo canto da bbox. |
| Igualdade de conjunto arredondado | Coordenadas na fronteira de arredondamento caem para lados diferentes. Compare por tolerância (~10 µm). |

O `MappingTarget` do IFC costuma ser **identidade**: quem posiciona cada
instância é o `ObjectPlacement` do `IfcProduct` — cada instância é um produto.

---

## Conhecimento crítico: parse_ifc.py (modo `--ifc`)

> Só usado com `--ifc`. No caminho padrão nada disto é executado — e os cinco
> bugs abaixo, todos de parsing de texto STEP, deixam de existir.

### O bug mais comum — IFCLOCALPLACEMENT ignorado

Parsers ingênuos aplicam só `IFCCARTESIANTRANSFORMATIONOPERATOR3D` (identidade em
muitos exportadores) e ignoram `IFCLOCALPLACEMENT`. Resultado: cada sub-peça renderiza
na sua origem local — motor, voluta e flanges aparecem separados por metros.

**A transform correta:**
```
v_world = T_LP_hierarquia × T_mapping_target × inv(T_mapping_origin) × v_local
```
Na maioria dos exportadores CAD: T_mapping_target = T_mapping_origin = identidade.
Então: `v_world = T_LP × v_local`

`resolve_lp()` em `parse_ifc.py` acumula a hierarquia recursivamente com cache.

### Dois caminhos de geometria (Caminho A e B)

**A — face set direto:**
```
IFCBUILDINGELEMENTPROXY → IFCPRODUCTDEFINITIONSHAPE →
  IFCSHAPEREPRESENTATION (Tessellation) → IFCTRIANGULATEDFACESET
```

**B — instância compartilhada (peças repetidas):**
```
IFCBUILDINGELEMENTPROXY → IFCPRODUCTDEFINITIONSHAPE →
  IFCSHAPEREPRESENTATION (MappedRepresentation) →
    IFCMAPPEDITEM
      MappingSource → IFCREPRESENTATIONMAP → IFCTRIANGULATEDFACESET
      MappingTarget → IFCCARTESIANTRANSFORMATIONOPERATOR3D
```

### IFCAXIS2PLACEMENT3D → Matriz 4×4

```
Z = normalize(Axis)
X = normalize(RefDirection − (RefDirection·Z)·Z)
Y = cross(Z, X)

M (row-major) =
  [ Xx  Yx  Zx  Tx ]
  [ Xy  Yy  Zy  Ty ]
  [ Xz  Yz  Zz  Tz ]
  [  0   0   0   1 ]
```

### Conversão de eixos: IFC (Z-up) → Three.js (Y-up)

```python
THREE_x =  v[0]
THREE_y =  v[2]   # Z do IFC vira Y no Three.js
THREE_z = -v[1]   # Y do IFC inverte e vira Z
```

### split_top() — obrigatório para formato STEP

`split(',')` simples quebra strings STEP com vírgulas internas como
`'MOTOR WEG 3,0CV T 220V'`. Usar sempre `split_top()` que respeita
profundidade de parênteses e strings.

### IFCINDEXEDCOLOURMAP — cores por face

Entidades standalone no arquivo IFC, não filhas de nenhuma outra.
A ligação vai do mapa para o face set, não o contrário.

```
IFCCOLOURRGBLIST(((r,g,b),(r,g,b),...))
IFCINDEXEDCOLOURMAP(FaceSetRef, Opacity, ColourRGBListRef, ColourIndex)
```
`ColourIndex[i]` (1-based) = índice da cor na paleta para o triângulo `i`.

Quando há IFCINDEXEDCOLOURMAP: emitir triângulos expandidos (sem compartilhar
vértices) para que cada vértice tenha a cor correta. O dedup.py depois compacta.

### Armadilha: unidades

Alguns exportadores (CATIA) declaram `MILLIMETRE` mas escrevem em metros.
Verificar a magnitude: coordenadas industriais em metros ficam em 0.01–5.0.
Se estiver em 10–5000, realmente está em mm — dividir por 1000.

### Filtrar vértices outlier

Alguns exportadores produzem IFCLOCALPLACEMENT aberrante (translação de 5m, 16m)
em sub-componentes. O parser aplica corretamente — o problema está nos dados.
Identificar pelo bounding box do JSON e filtrar com threshold por tipo de equipamento:
- Bomba compacta: 3m
- Válvula/fitting: 2m
- Equipamento grande (chiller): 10m

---

## Conhecimento crítico: read_aq.py

### Encoding é cp1252, não latin-1

O AltoQi Builder é aplicação Windows: o texto no SQLite é **cp1252**. Latin-1 e cp1252
são idênticos em toda a tabela **exceto na faixa 0x80–0x9F** — que é exatamente onde
moram travessão (0x96), aspas curvas (0x93/0x94) e reticências (0x85).

Lido como latin-1, `5U – 19” x 570mm MRD 557` vira `5U \x96 19\x94 x 570mm MRD 557` e
chega assim na página pública. O erro é silencioso: latin-1 nunca lança exceção, então
nada quebra — só sai errado.

`_decode_texto()` decodifica cp1252 com fallback para latin-1. O fallback existe porque
cp1252 deixa cinco bytes indefinidos (0x81, 0x8D, 0x8F, 0x90, 0x9D) e falha neles; sem o
fallback, uma biblioteca com esses bytes derrubaria o build inteiro.

⚠️ **Não troque o `text_factory` sem olhar as colunas binárias.** O latin-1 era
byte-preserving, e o código dependia disso para reconstruir o BLOB da geometria quando
ele voltava como `str`. Com cp1252 esse round-trip **não é reversível** — corromperia a
malha 3D em silêncio. Por isso as queries de `SIMBOLOGIA_3D` usam `CAST(... AS BLOB)`:
força bytes e elimina a ambiguidade.

### Literal acentuado numa query também tem de ir em cp1252

O banco **declara** `PRAGMA encoding = UTF-8` e guarda **bytes cp1252**. O SQLite não
valida a codificação do que se manda gravar, e o `typeof()` continua `'text'`:

```
SELECT NOME_CP FROM CLASSE_PECA  →  b'Bomba de Combate a Inc\xeancio - Dancor'
```

Consequência para quem consulta: o módulo `sqlite3` do Python vincula um `str` como
UTF-8, então `WHERE NOME_GP = 'Joelho 90° Soldável'` **nunca casa** — no banco é
`b'...Sold\xe1vel'` e o parâmetro chega como `b'...Sold\xc3\xa1vel'`. A query volta
vazia, sem erro. O jeito certo:

```python
con.execute('... WHERE g.NOME_GP = CAST(? AS TEXT)', (nome.encode('cp1252'),))
```

O `read_aq.py` nunca precisou disso porque varre tabelas inteiras e decodifica em
Python — só aparece quando se compara literal acentuado dentro do SQL.

### .aq pode ser ZIP ou SQLite direto

Sempre tentar SQLite direto primeiro (alguns .aq são extraídos de outro ZIP).
O `text_factory` cp1252 tem de ser configurado antes de qualquer query — ver a
seção de encoding acima.

### Tabelas — catálogo de produto

- `GRUPO_PECA` — séries/famílias (`NOME_GP` = "CAM-W10", "Cap", "Pontos de comando")
- `PECA` — variantes individuais (`NOME_PECA`, `DESCRICAO_DADOS`, dimensões em cm —
  **exceto `DIAMETRO_PECA`, que é um código**, ver abaixo)
- `DADOS_HIDRAULICOS` — parâmetros hidráulicos por peça
- `MODELO_BOMBA` — nome e potência nominal do modelo
- `ITEM_CURVA_BOMBA` — pontos Q-H (`VAZAO_ICB`, `ALTURA_ICB`, `POTENCIA_ICB`, `RENDIMENTO_ICB`)
- `PROPRIEDADE_PERSONALIZADA` / `VALOR_PROPRIEDADE_PERSONALIZADA` — specs livres
- `DADOS_ELETRICOS` / `PONTO_ELETRICO` / `SUB_TIPO_PONTO` — bibliotecas elétricas

### ⚠️ `DIAMETRO_PECA` é um CÓDIGO, não um centímetro

Corrigido em 2026-09-02. A skill `leitor-biblioteca-aq` 2.2.0 dizia "diâmetro nominal
(cm)" e **está errado**. É um índice numa escala de diâmetros nominais do AltoQi:

| `NOME_PECA` (Amanco) | `DIAMETRO_PECA` |
|---|---|
| `40 mm - 1.1/2"` | 8 |
| `50 mm - 2"` | 9 |
| `75 mm - 3"` | 11 |
| `100 mm - 4"` | 12 |
| `150 mm - 6"` | 14 |
| `200 mm - 8"` | 15 |

`ENTRADA_PECA.DIAMETRO_EP` e `ENTRADA_3D.DIAMETRO` usam a mesma escala: a Dancor grava
7 a 11 nos bocais das suas bombas, cujas sucções e recalques vão de 1.1/4" a 3" — o que
encaixa em 32, 40, 50, 60 e 75 mm, e confirma o código 10 como 60 mm.

**Os códigos 1 a 7 não são observáveis** nas 12 bibliotecas de `input/`. As bitolas de
água fria de 20, 25 e 32 mm não aparecem em nenhuma delas.

**A distribuição real na Amanco, nas 1.168 peças:** 963 (82%) trazem a sentinela
`-1.7976931348623157e+308` (`-DBL_MAX`), 93 trazem zero e **112 trazem código** — as 48
de tubo, 52 de caixa sifonada e afins (`TIPO_APLICACAO_PECA=9`) e 12 de ralo (tipo 10).

**Nenhuma das 700 conexões (tipo 2) tem código.** É isso que sustenta a regra: o diâmetro
de uma conexão mora em `ENTRADA_PECA.DIAMETRO_EP`, não aqui.

> **Corrigido no pipeline em 2026-09-02:** a chave do `build_product_map` passou de
> `'diametro_cm'` para `'diametro_codigo'`, e as quatro chaves numéricas passam por
> `_sem_sentinela()` — antes o mapa entregava `-1.8e308` como se fosse medida.

`PECA.DIAMETRO_INTERNO`, ao contrário, é milímetro de verdade: 192,8 / 144,8 / 98,0 /
47,5.

### As sentinelas: o AltoQi não usa `NULL` para "não definido"

| Sentinela | Onde aparece |
|---|---|
| `-2147483647` | `GRUPO_PECA.TIPO_CONFIGURACAO_GP` (265 de 265 na Amanco), `ENTRADA_PECA.SECAO_EP` (1.871 de 2.627) |
| `-1.7976931348623157e+308` (`-DBL_MAX`) | `PECA.DIAMETRO_PECA` em 963 de 1.168 na Amanco (82%) |

Ler essas colunas como número útil sem testar a sentinela produz lixo. E ao escrever um
`.aq`, gravar `NULL` onde a biblioteca real grava a sentinela é uma divergência
silenciosa — não se sabe se o Builder trata as duas igual.

### Tabelas — geometria 3D (as que importam para o caminho padrão)

| Tabela | Papel |
|---|---|
| **`SIMBOLOGIA_3D`** | a geometria. Colunas: `SIMBOLOGIA_3D` (BLOB OQ3D — a malha), `IMAGEM` (BMP 100×100 pré-renderizado), `WIREFRAME` (arestas p/ CAD — **69–71% do arquivo, descartável**), `NOME`, `USA_CORES_PECA` |
| **`PECA_SIMBOLOGIA_3D`** | o vínculo peça → geometria (`ID_PECA`, `ID_SIMBOLOGIA_3D`). Chave estrangeira: dispensa qualquer matching por nome. Várias peças compartilham a mesma malha |
| `GRUPO_SIMBOLOGIA_3D` | agrupa geometrias (`NOME_GRUPO`, `ID_CLASSE`) |
| **`CLASSE_SIMBOLOGIA_3D`** | `NOME_CLASSE` segue o padrão `"FABRICANTE - Linha"` (`'AMANCO - PVC Esgoto SN'`) — **a fonte confiável de fabricante** |
| `ENTRADA_3D` | pontos de conexão hidráulica: `POSICAO_X/Y/Z`, `DIAMETRO`, `TIPO_SECAO`, `ID_SIMBOLOGIA_3D`. **O IFC não carrega isso.** Ainda não consumido pelo pipeline — oportunidade para conectividade BIM |
| `CONTEUDO_SIMBOLOGIA` | símbolo 2D de planta baixa, formato proprietário distinto do OQ3D |
| `IMAGEM` | **ícones da interface do AltoQi**, não fotos de produto. Vazia nas bibliotecas hidráulicas; preenchida nas elétricas, onde há `SUB_TIPO_PONTO` |

> **Nunca use `SELECT *` em `SIMBOLOGIA_3D`** — traz o `WIREFRAME` (285 MB dos 412 MB
> da Amanco). Selecione as colunas explicitamente.

> A imagem do produto é **sempre** `SIMBOLOGIA_3D.IMAGEM`, nunca a tabela `IMAGEM`.

### Propriedades personalizadas observadas

**Bombas:** Tensão, Corrente, Grau de Proteção, Isolamento, Sucção x Recalque,
Altura Máxima, Temperatura máxima, Motor, Rotor, Rotação.

**Conexões:** Bolsa, Classe de rigidez, Temperatura máxima de operação, Encaixe,
Distância máxima entre apoios, Fecho Hídrico, Vazão, Inclinação.

**Elétrica:** Corrente máxima, Potência máxima da carga, Conectividade,
Aplicativo compatível, Material do painel, Touch, Tensão de alimentação,
Temperatura de cor, Vida útil, Dimerizável.

### Peças sem geometria — comportamento correto

Peças sem linha em `PECA_SIMBOLOGIA_3D` não têm forma fixa: **tubos** (o AltoQi gera
o cilindro a partir de diâmetro × comprimento) e **kits de aparelho sanitário**
(ramal de ventilação, tanque de lavar, vaso com tê) — entradas de projeto. Na Amanco
são 312 de 1.168 (27%). Pular é o esperado; o build informa quantas.

### Escrever um `.aq` — o inverso do `read_aq.py`

Estudado em 2026-09-02. O corpo completo está em `eng-reversa/estudo/01-escrever-um-aq.md`;
o essencial:

**O texto tem de ser gravado em cp1252, e errar isso corrompe o arquivo em silêncio.**
O módulo `sqlite3` do Python vincula `str` como UTF-8 e `bytes` como BLOB — nenhum dos
dois serve. A saída é o `CAST`:

```python
con.execute('INSERT INTO PECA (NOME_PECA) VALUES (CAST(? AS TEXT))',
            (nome.encode('cp1252'),))
```

`CAST(blob AS TEXT)` reinterpreta os bytes sem converter: `typeof()` volta `'text'`, os
bytes ficam idênticos aos de uma biblioteca real, e o `_decode_texto` devolve a string
original. Gravar em UTF-8 faz `'Soldável'` voltar `'SoldÃ¡vel'` — **sem levantar exceção
em lugar nenhum**, passando no `integrity_check` e chegando ao nome do produto na página
pública. É o bug de 2026-08-28, do lado de quem escreve. Encode **estrito**, nunca
`errors='replace'`.

**Uma biblioteca de fabricante preenche 16 a 25 das 77 tabelas.** A ordem de inserção
que fecha as chaves estrangeiras: `VERSAO_BANCO_CADASTRO` → `CLASSE_PECA` → `GRUPO_PECA`
→ `PECA` → (`DADOS_HIDRAULICOS`, `ENTRADA_PECA`, `ITEM_ASSOCIADO`);
`CLASSE_SIMBOLOGIA_3D` → `GRUPO_SIMBOLOGIA_3D` → `SIMBOLOGIA_3D` → `PECA_SIMBOLOGIA_3D`;
`GRUPO_PROPRIEDADE_PERSONALIZADA` → `PROPRIEDADE_PERSONALIZADA` →
`VALOR_PROPRIEDADE_PERSONALIZADA`; `CLASSE_ITEM` → `GRUPO_ITEM` → `ITEM`.

> O SQLite **não** aplica chaves estrangeiras por padrão: um `ID_GRUPO_PECA` órfão passa
> pelo `INSERT` sem erro e só aparece no AltoQi. Rodar `PRAGMA foreign_key_check` no fim.

**O DDL não se escreve à mão** — são 77 tabelas e 84 índices, e uma coluna faltando faz o
AltoQi recusar o arquivo. Está versionado em `eng-reversa/dados/schema-aq-607.sql`,
extraído do `sqlite_master` da Dancor.

**`ITEM.CODIGO_ITEM` é onde vive o código comercial do fabricante** — `'14808'` na
Amanco, `'10652511'` na Dancor, `'KO 16D GLP'` na Komeco. Não é propriedade
personalizada.

**Enums, com os valores observados.** `GRUPO_PECA.PROJETO_APLICACAO`: 8 esgoto, 12 água
fria, 22 incêndio, 36 gás, 64/76 elétrico. `ENTIDADE_IFC` (com `TIPO_ENTIDADE_IFC` e
`ENTIDADE_IFC_2X3`, que andam juntos): 2071 `IfcPipeFitting`, 2072 `IfcPipeSegment`,
2075 bomba, 2076 aparelho sanitário, 2084 válvula, 2085 terminal de descarte, 2090
aquecedor. `SUBTIPO_IFC` dentro de 2071: 0 curva/joelho, 1 luva, 3 cap, 4 tê, 6 redução.
`PECA.TIPO_APLICACAO_PECA`: 1 tubo, 2 conexão, 6 bomba, 8 aparelho, 9 caixa sifonada,
10 ralo, 55 ramal.

**Preencha `PECA.BIBLIOTECA`.** É o passo 2 da cascata de inferência de fabricante do
`build.py`, está vazio nas 12 bibliotecas reais, e é a **única fonte que sobrevive a uma
biblioteca sem geometria** — sem `CLASSE_SIMBOLOGIA_3D` o passo 1 não existe e a cascata
cai no nome da pasta.

### Diferenças entre versões de schema

| Versão | Bibliotecas | Diferença notada |
|---|---|---|
| 552–582 | Komeco, Intelbras | `ENTRADA_3D` **não tem** a coluna `DIAMETRO` |
| 595 | Amanco | — |
| 607 | Dancor | `ENTRADA_3D.DIAMETRO` existe |

Uma query que use `ENTRADA_3D.DIAMETRO` quebra com `no such column` nas bibliotecas
antigas.

---

## Conhecimento crítico: templates HTML

### Three.js self-hosted — obrigatório

CSP da Vercel bloqueia `cdn.jsdelivr.net`, `unpkg.com`, `cdnjs.cloudflare.com`
silenciosamente. Sempre self-host em `templates/vendor/` e copiar para `output/preview/vendor/`.
Nenhum dos dois está no git — `scripts/setup_vendor.sh` é obrigatório em clone novo.

### Padrão de thumbnail estática + click-to-3D

Não inicializar todos os viewers simultaneamente — GPU explode com 10+ contextos WebGL.
- `IntersectionObserver` com `rootMargin:'120px'` para lazy load
- `renderer.render()` uma vez → thumbnail estática
- OrbitControls + loop de animação só ao clicar

### Cache de geometria

```javascript
const geoCache = new Map(); // filename → data
async function fetchGeo(geo) {
  if (geoCache.has(geo)) return geoCache.get(geo);
  const data = await fetch('./data/' + geo).then(r => r.json());
  geoCache.set(geo, data); return data;
}
```

Quando o modal abre, o JSON já está em memória se o thumbnail foi carregado.

### vertexColors no Three.js

```javascript
const hasCol = data.col && data.col.length > 0;
const mat = new THREE.MeshStandardMaterial({
  vertexColors: hasCol,
  color: hasCol ? 0xffffff : 0x8896AA,  // branca com vertexColors (multiplicação), cinza sem
});
if (data.idx) geom.setIndex(data.idx);  // guard — ausente em geo expandida
```

### Design tokens bilds.com

```css
--orange: #FF4F1F   /* só em botão CTA primário */
--blue:   #1E40AF   /* botão secundário, link */
--radius: 4px       /* universal; badge é exceção: 9999px */
```
Fontes: **Fira Sans** (título de seção, hero) + **Inter** (todo o resto).
Ícones: Lucide SVG, stroke 2px, outline, currentColor.
Sombra: só no hover de cards clicáveis. Cards sem borda de hover por padrão.

---

## Integração com bilds.com (fase 2 — não implementada neste repo)

O ZIP gerado por este projeto será consumido por:

**dashboard.bilds.com** (`bilds.com/apps/admin`):
- Menu item "BIM 3D" em `bilds.com/apps/admin/src/components/Menu/menuConfig.tsx`
- Rotas: `/bim-3d` (grid de empresas), `/bim-3d/[companyId]/novo` (upload)
- Stack: Next.js 16, RTK Query, react-dropzone, react-hook-form + zod

**API NestJS** (`bilds.com/apps/api`):
- `POST /companies/:id/bim-catalogs` — recebe ZIP, extrai, salva no S3
- MongoDB Company: novo campo `bimCatalogs: BimCatalog[]`
- Storage: S3 + CloudFront (`S3Service`, `AWS_CLOUD_FRONT_BASE_URL`)

**bilds.com web** (`bilds.com/apps/web`):
- Rota `app/[customLink]/[catalogSlug]/page.tsx` — Server Component
- `generateMetadata()` lê `catalog.json` do S3 para SEO (title, description)
- `ProductGrid` renderizado server-side (SSR — indexável por crawlers)
- `BimViewer` React com `three` via npm, `dynamic(() => ..., {ssr:false})`

**Seleção de layout no dashboard:**
- Campo `layout` gravado no MongoDB (não no catalog.json)
- Admin pode trocar o layout sem re-upload dos arquivos
- Seletor visual com SVGs wireframe por layout no formulário

---

## Conhecimento crítico: build.py — matching IFC → .aq

### find_aq_product — como o match funciona

```python
find_aq_product(slug, product_map, ifc_path_hint=None)
```

Quando o `file_map` usa caminhos relativos como chave (ex: `"Cap/PVC Esgoto SN/100mm.ifc"`),
o `ifc_path_hint` é passado automaticamente por `build_catalog()`. O algoritmo extrai tokens
de **todos** os componentes do caminho (pasta + filename) e calcula cobertura contra o GRUPO_PECA:

```
caminho: "Cap/PVC Esgoto SN/100mm.ifc"
tokens query: {cap, pvc, esgoto, sn, 100mm}

GRUPO_PECA "Cap" → tokens {cap} → cobertura 1/1 = 100% ✓
→ dentro do grupo: PECA com maior sobreposição com leaf "100mm"
→ nome final: "Cap 100mm" (gp + peca quando grupo não está no nome da peça)
```

Tenta cobertura ≥ 100%, relaxa para ≥ 75% se não encontrar. Se ainda falhar,
cai no fallback por prefixo/número (compatível com IFCs flat como Dancor).

**Para maximizar o match rate em catálogos hierárquicos:** a chave do `file_map`
deve ser o caminho relativo completo a partir do `ifc_dir`, não só o filename.
Para catálogos com > 50 produtos, o `interactive_config()` gera isso automaticamente
via modo `'recursive'` do `scan_input()`.

---

## Diagnóstico rápido de problemas

| Sintoma | Causa provável |
|---|---|
| Uma peça isolada, "solta no ar", sem mudar a contagem de triângulos | Rotação do OQ3D lida como row-major — ela é column-major |
| Parafusos/detalhes faltando, ~30% menos triângulos que o IFC | Instâncias `TQi3DReusedObject` por referência não resolvidas |
| Peças separadas por metros | resolve_lp() não acumula hierarquia recursivamente |
| Fragmentos a 5–16m do corpo | LP aberrante no IFC exportado — filtrar outliers |
| Modelo ~1000× maior | Conversão mm→m desnecessária — verificar magnitude das coordenadas brutas |
| Modelo cinza (tem cores no IFC) | build_face_color_map() não chamado, ou IFCINDEXEDCOLOURMAP não encontrado |
| 0 cores do IFCCOLOURRGBLIST | Regex espera inteiros mas floats têm casas decimais |
| `col[]` presente mas Three.js ignora | Material sem `vertexColors: true` ou `color` não é 0xffffff |
| `import * as THREE from 'three'` falha | importmap ausente ou fora de ordem no HTML |
| Canvas não encontrado no init | Módulo rodou antes de 'cards-rendered' — verificar handshake |
| GPU trava | Loop de animação em todos os cards — thumbnail estática + loop só no click |
| ZIP vazio de geo files | IFCs não foram parseados — verificar output/geo/ após o build |
| .aq não abre como SQLite | Tentar abrir como ZIP; se falhar: arquivo corrompido |
| Texto com lixo | Encoding não configurado — usar `latin-1` |
| Taxa de match IFC → .aq baixa | `file_map` usa só filename — chave deve ser o caminho relativo completo (`Cap/PVC SN/100mm.ifc`) para enriquecer tokens da busca fuzzy |
| Nome do produto é só dimensão ("100mm") | Esperado para catálogos flat no .aq — build.py prefixa com GRUPO_PECA automaticamente |
| ZIP 0KB + "X não encontrado em input/" | scan_input escolheu modo subdir com múltiplos IFCs — fix: modo subdir só ativa quando cada subdir tem exatamente 1 IFC; caso contrário cai em recursive |
| Fabricante/título stale do catálogo anterior | aq_stale não estava resetando titulo/slug — fix em commit 056e729; deletar config.json corrompido se necessário |
| `Fabricante []` sem sugestão | BIBLIOTECA vazia no .aq e pasta avô é genérica — peek_aq tenta pasta avô, depois filename |
| Título sugerido ruim (ex: `"Esgoto Sn Sr"`) | Pasta pai do .aq é genérica (`input/`, `.`) — organizar como `input/Fabricante/Nome da Linha/pecas.aq` |
| Slug com acento (`inc-ndio`) | slugify não normalizava unicode — corrigido com NFD + strip combining marks (commit 8e2f67d) |
| Slug mostra valor antigo do config.json | ec.get('slug') tomava precedência sobre titulo atual — removido; slug sempre = slugify(titulo) (commit fefb627) |
| **Fabricante vazio na página publicada** | `PECA.BIBLIOTECA` está vazia nas três bibliotecas testadas — usar o prefixo de `CLASSE_SIMBOLOGIA_3D.NOME_CLASSE` |
| **Título vira o nome do fabricante** | Pasta pai é o fabricante (`input/Intelbras/pecas_Intelbras_*.aq`) — comparar o slug da pasta com o 1º token do arquivo antes de usá-la como título |
| **Título em forma de slug** na página | Derivado do filename sem limpeza — remover ruído (`pecas`, anos, versões), preservar siglas (CFTV, PPCI) e separar CamelCase |
| **Título colado** (`"Barramentoblindado"`) | Filename com palavra composta toda-minúscula (ex: `pecas_maxbar_barramentoblindado.aq`) — CamelCase split não actua, token fica capitalizado só na 1ª letra. Fix (commit 48a0f65): token único todo-minúsculo > 10 chars é ignorado; a cascata cai para `linhas` do banco, que devolve `'Barramento Blindado'`. Organizar o filename como `barramento_blindado.aq` ou `BarramentoBlindado.aq` evita o problema. |
| Nome do produto redundante (`Pontos de comando Interruptor…`) | Prefixo do grupo aplicado sem necessidade — prefixar só quando o nome é ambíguo, decidindo **por grupo** |
| **Preview 404 em `data/*.json`, erro `Unexpected token 'T'`** | Template usava `./data/`; com `cleanUrls` a página é servida em `/<slug>` sem barra final e o relativo vai para a raiz. Usar caminho absoluto `'/' + CATALOG.slug + '/data/'`. O `'T'` é a página 404 da Vercel ("The page…") caindo no `JSON.parse` |
| Preview gigante (centenas de MB) | Faltou `dedup()` no caminho `.aq` — reduz ~79% dos vértices |
| ZIPs entrando no commit | `output/*.zip` não cobre subpastas; a saída é aninhada — usar `output/**/*.zip` |
| Joelhos e curvas retos no viewer | Transforms do OQ3D ignorados — usar o parser de árvore de `oq3d.py` |
| Peças 100× maiores/menores | OQ3D é **centímetros**; multiplicar por 0.01 |
| Menos produtos que peças no banco | Peças sem `PECA_SIMBOLOGIA_3D` são tubos e kits — sem forma fixa, pular é o correto |
| Parafusos faltando / um solto no ar | Bug aberto do OQ3D — ver "instâncias repetidas não emitem geometria" |
| Miniatura chapada, sem relevo, diferente do viewer | Está saindo do rasterizador software — o caminho de produção é `www/tools/thumb-rasterizer.ts` (Playwright). Confira com `grep chromium.launch www/tools/thumb-rasterizer.ts` |
| Thumb leva ~2 s cada e o import estoura o tempo | Geometria passada como **objeto** para `page.evaluate` — passar como string JSON e dar `JSON.parse` dentro da página (6×) |
| Worker de thumbs não sai / Chromium órfão | Faltou `await closeThumbRenderer()` antes do `process.exit()` — o handle do servidor HTTP prende o event loop |
| Thumb regenerada não aparece no browser | ETag de `/thumbs/:productId` deriva só do `thumbKey` e o `Cache-Control` é `immutable` — hard reload |
| `pnpm thumb:regen <id>` ignora o importId | `sh -c 'cmd' arg` faz `arg` virar `$0` — o script precisa de `"$@"` e um `--` de placeholder (corrigido em 2026-08-30) |
| WebGL não inicializa em headless | Faltam os flags SwiftShader — obrigatórios em WSL/CI/container; sem eles **todas** as geometrias falham de uma vez |
| Query com `WHERE NOME_x = 'algo acentuado'` volta vazia, sem erro | O texto no `.aq` é cp1252 e o `sqlite3` vincula `str` como UTF-8 — usar `CAST(? AS TEXT)` com `.encode('cp1252')` |
| Diâmetro do mapa vale ~2× o esperado, ou vem `-1.8e308` | `PECA.DIAMETRO_PECA` é um **código**, não centímetro, e `-DBL_MAX` é sentinela. A chave é `diametro_codigo` desde 2026-09-02 e já filtra a sentinela |
| `no such column: DIAMETRO` em `ENTRADA_3D` | Coluna só existe no schema 607; as bibliotecas 552–582 não a têm |
| `.aq` gerado abre e valida, mas os nomes saem como `SoldÃ¡vel` | Texto gravado em UTF-8 — o AltoQi grava **cp1252**; usar `CAST(? AS TEXT)` com bytes cp1252 |
| `.aq` gerado publica com o título errado (ex.: "Saida") | O título vem da pasta pai do `.aq`, e `saida`/`output` não estão em `_GENERIC_DIRS` (`build.py:922`) — pôr o `.aq` numa pasta com nome descritivo |
| `.aq` sem geometria publica com fabricante vindo do nome da pasta | Sem `CLASSE_SIMBOLOGIA_3D` o passo 1 da cascata não existe e `PECA.BIBLIOTECA` está vazio nas 12 bibliotecas reais — preencher `PECA.BIBLIOTECA` ao gerar |
| Sólido gerado mostra o interior por uma emenda | Perfil de revolução que fecha em si mesmo sem soldar o último anel no primeiro: `2 × lados` arestas de borda |
| Peça gerada com partes soltas ou flutuando | Malhas corretas em posição relativa errada — não aparece em bbox, contagem nem round-trip; conferir abrindo o preview |
| Sobrou um `.aq` de 0 byte onde não havia arquivo | `open_aq` tenta `sqlite3.connect()` primeiro, e o `sqlite3` **cria** o arquivo num caminho inexistente cujo diretório existe. O fallback para ZIP então falha com `BadZipFile` |
| API em `Retrying (n)...` eterno, sem responder request nenhum | Não conecta no Mongo. A mensagem do Mongoose culpa o whitelist, mas é texto fixo — meça DNS, TCP, TLS e auth separadamente (ver "A API não sobe e o Mongoose culpa o whitelist") |
| `tlsv1 alert internal error` / `SSL alert number 80` nos 3 nós, com o TCP abrindo | **IP não liberado no Atlas** (ou cluster M0 pausado). O handshake morre antes da autenticação, então não é credencial. Liberar em *Network Access*; a API reconecta sozinha no próximo retry |
| Página pública `404` e `/empresas/minha` `404` com a API saudável | A base está **vazia** — é o estado desde 2026-09-02, não um defeito. Ver "Estado em 2026-09-02" |

---

## Git e deploy

**Identidade:** commits neste repo usam `carlosnetoaltoqi`.
Verificar com `git config user.name` e `git config user.email`.
Se necessário: `git config user.name "carlosnetoaltoqi"`

**`output/preview/` é gitignored, exceto `index.html`.**

> ⚠️ Versões antigas deste arquivo diziam o contrário — que o preview inteiro era
> versionado e que `output/preview/vendor/` era a cópia oficial do Three.js. **Nunca
> foi verdade no git**: `git ls-files output/preview` sempre devolveu só `.gitignore`,
> `.gitkeep` e `index.html`. Corrigido em 2026-08-30, quando a pasta local chegou a
> **511 MB** em 705 JSONs de geometria e a decisão foi mantê-la fora do histórico.

O que é gerado e portanto ignorado:

- `output/preview/<slug>/data/` — geometria de cada catálogo (dentro do catálogo,
  não na raiz: o template resolve `'/' + slug + '/data/'`, e nomes como `50mm.json`
  colidiriam entre bibliotecas)
- `output/preview/<slug>/index.html`, `catalog.json`, `catalogs.json`
- `output/preview/vendor/` — cópia de `templates/vendor/`, que por sua vez vem do
  `setup_vendor.sh`. **Não há cópia do Three.js versionada em lugar nenhum**: rode
  `bash scripts/setup_vendor.sh` depois de clonar.

Tudo isso volta com `python3 scripts/build.py --all --force`.

**Consequência para o deploy:** a Vercel constrói a partir do git, então hoje ela serve
só a landing. Publicar os catálogos exige subir os arquivos por outro caminho (build na
Vercel, ou storage externo) — **decisão em aberto**, ver "Pendência conhecida".

**Também gitignored** (regeráveis a partir do `.aq`): `output/geo/`, `output/thumbs/`,
`output/**/*.zip`, `output/**/*-catalog.json`, `output/*.json`. Os padrões precisam de
`**` porque a saída espelha a estrutura de `input/`.

### Deploy na Vercel

**Projeto:** `bilds/bilds-bim-3d` — **não criar outro projeto, nunca.**
**URL de produção:** https://bilds-bim-3d.vercel.app

O repositório está conectado à Vercel via integração git — **o push para `main` dispara o
deploy automaticamente**. Fluxo normal:

```bash
git add output/preview/
git commit -m "build: catálogo {slug}"
git push
```

O `vercel.json` na raiz configura `"outputDirectory": "output/preview"` — a Vercel serve
esse diretório. Para deploy manual via CLI (ex: sem commit):

```bash
# SEMPRE da RAIZ do repo
vercel --prod --yes
```

**Nunca** passar `output/preview` como argumento posicional (`vercel deploy output/preview --prod`)
— isso ignora o `.vercel/project.json` da raiz e cria um projeto novo indesejado.

**Preview local:**
```bash
python3 -m http.server 8080 --directory output/preview
```

---

## Histórico de sessões

### 2026-09-02 — POC subida local, armadilha do Atlas e limpeza da base

Sessão sem mudança de código: subir a POC nesta máquina, documentar o que barrou, e
**zerar banco e storage** a pedido.

**A POC subiu, depois de um bloqueio de 15 minutos no Atlas.** O web (`:3000`) levantou
normal; a API (`:4000`) ficou em retry infinito com o Mongoose acusando whitelist de IP. A
mensagem é texto fixo do driver e cobre cinco causas distintas, então medi as camadas
separadamente: DNS SRV resolvia os três nós, o TCP em `:27017` **conectava**, e o TLS
morria com `tlsv1 alert internal error` (SSL alert 80) nos três. Essa combinação — TCP
abrindo, TLS caindo com alert 80 — é a assinatura de IP não liberado: o handshake termina
antes de qualquer credencial trafegar. Liberado o IP no Atlas, a API **reconectou sozinha**
no ciclo de retry seguinte, sem reinício. Receita completa em "A API não sobe e o Mongoose
culpa o whitelist"; três linhas novas na tabela de diagnóstico.

**Validação da carga que existia, antes de apagar.** Confirmou a S5.2 integralmente: 869
produtos, todos com `geoUrl` e `thumbUrl`; geometria da CAM-W21 2CV com **27.425
triângulos** (o número do parser corrigido, não os 20.452 do antigo); miniaturas em
`image/webp` distintas por produto; revalidação da S6.1 devolvendo `304` com a ETag; as
duas páginas públicas em `200` e slug inexistente em `404`.

**Limpeza.** `deleteMany({})` nas quatro coleções — `bim_products` (869), `bim_catalogs`
(2), `bim_imports` (2) e `companies` (1) — e todos os 1.738 arquivos de
`www/storage/bim/`, preservando os diretórios. Conferido depois: 0 documentos, 0 arquivos,
e a API respondendo certo no vazio (`404` nas páginas e em `/empresas/minha`, `200` com
corpo vazio em `/importacoes/ultima`, login seguindo em `200` porque não consulta o banco).

> **A limpeza é irreversível nesta máquina.** Os `.aq` da Dancor e da Amanco não estão em
> `input/`, e as chaves de storage embutem o `importId` — nada do que foi apagado se
> reconstitui a partir do que sobrou. Quem quiser exercitar a POC aqui deve importar uma
> das 7 bibliotecas da Intelbras, que são pequenas e atravessam o mesmo caminho.

**Duas coisas que o arquivo afirmava e não eram mais verdade** — ambas corrigidas: os
`importId` documentados (`d5a4acb5`, `28826de9`) já não existiam desde antes desta sessão
(eram `4180e887` e `5c2dc29a`, e agora nenhum), e a coleção de empresa chama-se
`companies`, não `bim_companies`. Ficou registrado também o formato da resposta de
`GET /catalogos/:empresa/:slug`: raiz `{ catalog, products }` em inglês, com
`geoUrl`/`thumbUrl` no produto — diferente do `catalog.json` do pipeline estático e dos
`geoKey`/`thumbKey` do documento do Mongo.

### 2026-09-02 — Engenharia reversa da ESCRITA de `.aq` (Akato, PDF → biblioteca)

Terceira linha de trabalho, e a primeira que **escreve** `.aq` em vez de ler. Tudo em
`eng-reversa/`, que não altera o pipeline existente. Corpo completo em
`eng-reversa/README.md` e nos seis documentos de `eng-reversa/estudo/`.

**O que foi entregue.** PDF comercial da Akato (24 páginas) → `.aq` → catálogo
publicável com viewer 3D, atravessando o `build.py` do próprio projeto. 87 famílias,
**269 produtos**, 0 códigos repetidos, 0 linhas incompletas. Três variantes de `.aq`:
sem geometria (a fiel, 848 KB), com os 12 tubos (944 KB) e com forma paramétrica para
as 262 peças (6,8 MB). As três passam nas 20 checagens do `validar_aq.py`, que usa o
`read_aq.py` e o `oq3d.py` deste projeto sem modificação.

**Os quatro achados que mudaram este arquivo:**

1. **`PECA.DIAMETRO_PECA` é um CÓDIGO, não centímetro.** A skill 2.2.0 estava errada.
   `50 mm` → 9, `100 mm` → 12; e em 963 das 1.168 peças da Amanco o valor é a
   sentinela `-DBL_MAX`, com nenhuma das 700 conexões trazendo código. Corrigido aqui e
   na skill (2.3.0).
2. **O `.aq` declara UTF-8 e guarda cp1252** — o mecanismo por trás da armadilha de
   encoding já conhecida. Duas consequências novas: gravar exige
   `CAST(? AS TEXT)` com bytes cp1252, e **comparar literal acentuado dentro do SQL
   exige o mesmo**, senão a query volta vazia sem erro.
3. **O cabeçalho OQ3D tem, no offset 29, o número de objetos-raiz** — nunca
   documentado. Serve de verificação de parse, e revelou um defeito real: medido em
   todas as 783 geometrias de fabricante, o `oq3d.py` conta raízes a mais em **54
   (6,9%), em 6 das 12 bibliotecas** — Maxbar com 31 de 135. A diferença vai de +2 a
   +10 e não é sempre par.
4. **`saida` e `output` faltam em `_GENERIC_DIRS`** (`build.py:922`), então um `.aq`
   numa pasta chamada `saida/` publica com o título "Saida" — e a validação não acusa,
   porque "Saida" de fato é diferente do fabricante.

**Sobre validar geometria inventada.** O escritor OQ3D fecha round-trip contra o
`oq3d.py`, inclusive reescrevendo uma geometria real da Amanco vértice a vértice. Mas
round-trip, bounding box e contagem de triângulos **não pegam** duas classes de erro que
apareceram: perfil de revolução não soldado (`2 × lados` arestas de borda, 15 das 21
formas) e malhas corretas em posição relativa errada (colar de joelho solto, sifão
desmontado, 56 + 8 peças). A primeira se pega contando arestas; a segunda só abrindo o
preview e olhando — daí `eng-reversa/tools/olhar_preview.mjs`.

**ZIP.** `output/akato-construcao-civil-202609021348.zip`, 2.775 KB, conforme em 17 de
17 itens de `docs/bilds-bim-3d-zip-spec.md`, com 262 miniaturas WebP.

**Correções que este estudo levou ao código, no mesmo dia:**

- `read_aq.build_product_map()` — `diametro_cm` → `diametro_codigo`, e as quatro chaves
  numéricas passam por `_sem_sentinela()`: antes o mapa entregava `-1.8e308` como medida;
- `oq3d.parse()` — `n_raizes_declarado()` lê o campo do offset 29 e o parse avisa com
  `OQ3DAvisoParse` na divergência;
- `build._GENERIC_DIRS` — `saida`, `output`, `out`, `dist`, `build`.

**O que segue em aberto:** a simbologia 2D (`CONTEUDO_SIMBOLOGIA`) e o `WIREFRAME`
**não foram decifrados** — um `.aq` gerado não tem representação em planta —, e a causa
das 54 divergências de contagem de raízes do OQ3D é conhecida por sintoma, não por
mecanismo.

### 2026-08-31 — S6.1: validador de cache dos assets do storage

Fechada a pendência da miniatura regenerada que não invalidava o cache do browser.
Registro completo em `docs/sessoes/S6.1-cache-de-assets.md`.

`GET /thumbs/:productId` e `GET /geometrias/:productId` tinham ETag derivada só da **chave**
do store (`<tipo>/<importId>/<productId>`) mais `Cache-Control: immutable`. Como o
`thumb:regen` reescreve os bytes na mesma chave, a ETag não mudava — e com `immutable` o
browser nem chegava a perguntar. Trocar só a ETag não resolveria nada por esse motivo.

Agora os dois controllers usam `www/apps/api/src/common/asset-cache.ts`: ETag de
`sha1(key:size:mtimeMs)` via o novo `IGeometryStore.stat()`, `Cache-Control: public,
max-age=0, must-revalidate`, e o `304` é decidido **antes de ler o blob** — a geometria de
2,7 MB não sai do disco à toa.

| Verificação | Resultado |
|---|---|
| Playwright, `goto` + `reload` na página do Dancor | 1ª visita 13×`200` · reload 13×`304` |
| `thumb:regen` no mesmo import, condicional com a ETag antiga | `200` com ETag nova — era isto que falhava |
| Thumb de import não regenerado | segue `304` |
| Geometria 2,7 MB · condicional | `200` ≈ 35 ms · `304` ≈ 29 ms, 0 b |
| `If-None-Match` com lista, `W/` e `*` | `304` nos três |
| Baseline S5.2 | duas páginas `200`, `2cv-t-220-380v-inc-flg-ir3` com 27.425 triângulos |

Escolha consciente de **`mtime + size` em vez de hash do conteúdo**: hashear obrigaria a ler
o arquivo inteiro para responder "não mudou". O preço é um `200` extra quando os bytes são
idênticos e o mtime mudou — nunca conteúdo errado. E de **`must-revalidate` em vez de URL
content-addressed**: a URL com hash é o padrão certo *com CDN na frente* e fica registrada
para a bilds.com, mas aqui exigiria mexer no `thumb-worker`, no `regen-thumbs` e migrar os
869 produtos — desproporcional numa POC encerrada.

A outra pendência, "GET /geometrias sem auth", foi **investigada e não aplicada**: era
inaplicável como estava escrita. Ver "Pendência conhecida" acima e a seção 6 do registro.

### 2026-08-31 — S5.3: auditoria de autocontenção

Varredura para garantir que nada do conhecimento do projeto vive fora do repositório.
O que estava furado, e foi corrigido:

1. **`www/.env.example` não existia.** As seis variáveis (`MONGODB_URI`, `MONGODB_DB`,
   `SEED_USER`, `SEED_PASSWORD`, `JWT_SECRET`, `STORAGE_PATH`) só apareciam espalhadas
   pelo histórico de sessões — um clone novo não conseguia subir a POC sem garimpar.
   Agora há template versionado e uma tabela em "Variáveis de ambiente".
2. **O estudo do BILDS-552 era um ponteiro para `.claude/sessions/` do bilds.com** —
   estado de sessão de agente, de outro repositório. As medições que importam (40,4 MB
   na primeira viewport da Dancor, peso por geometria, os 3 contextos WebGL, o S3 sem
   `ContentEncoding: gzip`) foram trazidas para dentro deste arquivo.
3. **Caminhos `/home/foltz/...` em comandos executáveis** no plano, inclusive um
   `require()` apontando para o `node_modules` do bilds.com. Trocados por
   `git rev-parse --show-toplevel` e pelo driver local.

Conferido também: nenhum segredo em arquivo versionado, `www/.env` segue ignorado,
as 278 referências a arquivo nos `.md` resolvem (as que sobram são ou de outro
repositório, explicitamente prefixadas, ou artefatos gerados por build).

Skill `leitor-ifc` 1.4.0 → **1.5.0**: nova seção "O IFC como gabarito", com a
reconstrução exata a partir do STEP e as quatro armadilhas de comparação que
apareceram em S5.1.

### 2026-08-31 — S5.2: encerramento da POC, carga limpa e validação

Banco Atlas e `www/storage/bim` zerados e recarregados do zero pela interface, já com o
parser corrigido em S5.1. Registro completo em `docs/sessoes/S5.2-encerramento-poc.md`.

| Verificação | Resultado |
|---|---|
| Produtos | **869 — todos com `geoKey` e `thumbKey`, 0 arquivo faltando em disco** |
| Catálogos | Dancor (13, `series-rows`) e Amanco (856, `catalog-grid`) |
| Geometria | CAM-W21 2CV com **27.425 triângulos** — parser corrigido (o antigo dava 20.452) |
| Miniaturas | `image/webp` pela API, anel de parafusos completo, nada solto |
| Páginas públicas | 200 nas duas, no web e na API |
| Login | token OK, `/auth/me` 200 |

Três coisas que o `CLAUDE.md` afirmava e não eram mais verdade — todas corrigidas: o
catálogo Amanco "não está nesta máquina" (está, com 856 produtos), os `importId`
documentados já não existiam, e o campo do produto é `geoKey`, não `geometryKey`.

**A POC está encerrada.** Não há próxima sessão nesta linha.

### 2026-08-30 — S5.1: instâncias repetidas do OQ3D (dois bugs, não um)

Fechado o bug em aberto do `oq3d.py`. Registro completo em
`docs/sessoes/S5.1-instancias-repetidas-oq3d.md`.

**Bug 1 — a chave de resolução.** `TQi3DReusedObject` sem definição inline referencia
uma `TQi3DReusableObject` pelo **índice de serialização, base 1, sobre todos os objetos
em ordem de documento**, com um discriminador logo após o GUID (`0x01` = referência +
u32, `0x02` = inline). O GUID nunca foi a chave. As duas hipóteses antigas — o `u32` em
`+8` e "a última definição vista" — foram testadas e refutadas.

**Bug 2 — a rotação é column-major.** A 3×3 de `TCoordinateTransformation3D` era lida
como row-major, o que a transpõe. Não muda a contagem de triângulos, só a posição —
por isso sobreviveu ao estudo original, cuja validação era por bounding box, e **uma
bbox não distingue uma rotação da sua transposta**. Era ele o responsável pela peça
"solta no ar".

Corrigido nos dois parsers (`scripts/oq3d.py` e `www/tools/oq3d-parser.ts`), com a
rotação transposta na leitura para não mexer na composição.

| Verificação | Resultado |
|---|---|
| Dancor × IFC, peça a peça | **13/13 com conjunto de pontos idêntico** |
| CAM-W21 2CV | 18/18 instâncias emitem; 20.452 → **27.425** triângulos, o total exato do IFC |
| Amanco (B-rep), 100 IFCs | mediana do erro de forma 0,473 → **0,094 cm** |
| Malhas soltas no ar | Amanco 10 → **0**; demais bibliotecas já eram 0 |
| Paridade Python × TS | `pnpm port:test` passa nas 13 peças |
| 10 bibliotecas | 2.960 instâncias, **1.096 por referência, todas resolvem**; +8,2% de triângulos no total, +30,9% na Amanco |

Ferramenta nova: `docs/estudo-oq3d/valida_ifc.py` — confere o parser contra o IFC
comparando **conjunto de pontos** (tessellated) ou forma (B-rep). Existe porque a
ausência dessa conferência foi o que deixou o bug 2 passar.

### 2026-08-30 — S4.4: miniaturas idênticas ao viewer (Playwright no thumb-worker)

Fecha a pendência de qualidade que a S4.3 deixou aberta. Registro completo em
`docs/sessoes/S4.4-thumbs-playwright.md`; arquitetura e medições em
`docs/solutions/architecture-patterns/thumb-qualidade-identica-ao-viewer.md`.

**O que mudou:**

| Arquivo | Mudança |
|---|---|
| `templates/thumbs/harness.html` | extraída `window.renderThumbFromData(data, W, H, mime, quality)` — recebe `{pos, col, idx}` em memória e é a única função que toca WebGL. `renderThumb(url, …)` virou wrapper (`fetch` + delegação). Material, luz e câmera intocados. |
| `www/tools/thumb-rasterizer.ts` | **reimplementado sobre Playwright.** Mesmo nome e mesma assinatura pública (`renderThumbTs(data, w?, h?) → Promise<Buffer>`); dentro, servidor HTTP efêmero + Chromium + harness. Novo: `renderThumbPlaywright`, `closeThumbRenderer`. |
| `www/tools/thumb-rasterizer-sw.ts` | o rasterizador software de antes, agora histórico (`renderThumbTs` → `renderThumbSw`). Só `measure-thumbs.ts` o importa, para manter reproduzível a comparação A × B do ADR-003. |
| `www/apps/api/src/importacoes/thumb-worker.ts` | laço em `try/finally` com `await closeThumbRenderer()`. Interface IPC inalterada. |
| `www/tools/regen-thumbs.ts` | fecha o renderer no fim. |
| `www/package.json` | `thumb:regen` passou a repassar o argumento (`"$@"` + `--`). Antes o `importId` virava `$0` do `sh` e sumia — limitação registrada na S4.3. |

**Resultado medido** (13 produtos Dancor, import real pela API):

| Critério | Antes (rasterizador software) | Agora |
|---|---|---|
| PSNR contra o render do viewer | 27 dB | **47 dB** — o piso da compressão WebP q=0,85 |
| Tempo do lote | ~2 s | **~6,3 s** (a 1ª thumb paga a subida do Chromium, ~1,2 s; as demais 220–470 ms) |
| Erros | 0 | 0 — 13/13 com `thumbKey` |
| Cards com thumb estática | 13/13 | 13/13 |

Os dois consumidores do harness produzem o **mesmo arquivo byte a byte**: rodado o
`scripts/thumbs.mjs` sobre geometrias que também estão no import da API, os WebP batem no
MD5. A refatoração (`renderThumb` virou wrapper de `renderThumbFromData`) não introduziu
divergência entre o pipeline estático e o POC.

**Três aprendizados que valem para além desta sessão:**

1. **Nunca passe geometria como objeto para `page.evaluate`.** O serializador do Playwright
   anda o grafo; a geometria é um array de centenas de milhares de números. Objeto: ~2 200 ms
   por thumb. String JSON com `JSON.parse` dentro da página: ~370 ms. No lote, 24,5 s → 6,2 s.
   O doc de arquitetura previa 60–100 ms por thumb e estava certo sobre o **render** (~120 ms)
   — o que ele não previu foi o **transporte**.
2. **`file://` não serve.** O harness importa o Three.js como módulo ES e o Chromium recusa
   `import` sobre `file://` por CORS. Servidor HTTP efêmero (`listen(0)` em `127.0.0.1`) —
   nunca colide com a API (4000) nem com o web (3000).
3. **Alinhar a versão do Three.js não era necessário.** Harness usa o vendor do repo (r170),
   viewer do POC usa r185. Medido: PSNR 71 dB entre os dois, MSE 0,01 — imperceptível.
   Servir o r185 traria uma segunda cópia do Three.js no caminho de render e um caminho
   diferente do pipeline estático, exatamente a divergência que o harness existe para impedir.

### 2026-08-23 — Diagnóstico e correção de bugs do parse_ifc.py

**Contexto:** primeira vez que o pipeline foi rodado do zero após limpeza total do `output/`.
Os arquivos de geo que existiam localmente (gitignored) nunca tinham sido regenerados desde
a criação do projeto — esta sessão revelou que o código commitado nunca havia sido validado
contra os IFCs reais.

**Bug 1 — Índices errados no parser STEP (Dancor / CATIA / 3DEXPERIENCE)**

`parse_ifc.py` lia `parts[4]` como `ObjectPlacement` e `parts[5]` como `Representation`.
No IFC4 exportado pelo 3DEXPERIENCE, o índice 4 (0-based) é `ObjectType`
(`'AECARCHITECTURALELEMENT'`), deslocando tudo em +1:

```
[4] ObjectType       = 'AECARCHITECTURALELEMENT'  ← o que estava sendo lido como LP
[5] ObjectPlacement  = #id do IFCLOCALPLACEMENT   ← correto
[6] Representation   = #id do IFCPRODUCTDEFINITIONSHAPE
```

O parser tentava `int('AECARCHITECTURALELEMENT')` → `ValueError` → pulava todos os
`IFCBUILDINGELEMENTPROXY` → 0 vértices para todos os 14 IFCs da Dancor.

**Correção aplicada:** `parts[4]→parts[5]` (ObjectPlacement) e `parts[5]→parts[6]`
(Representation). Guard `len(parts) < 7` atualizado de `< 6`.

**Bug 2 — IFCs da Amanco usam IFCADVANCEDBREP, não IFCTRIANGULATEDFACESET**

O `parse_ifc.py` só tratava geometria tessellada (`IFCTRIANGULATEDFACESET`).
Os IFCs da Amanco (exportados pelo AltoQi Hidráulico/Elétrico) usam B-rep paramétrico
(`IFCADVANCEDBREP`) — incompatível com o parser STEP puro.
Os geo files da Amanco em commits anteriores foram gerados em sessão com código diferente.

**Correção aplicada:** adicionado `_parse_ifc_brep()` que usa `ifcopenshell.geom`
para tessellizar B-rep automaticamente, com fallback de cor por material.
`parse_ifc_file()` detecta o tipo de geometria e roteia para o método correto.
`ifcopenshell>=0.8.0` adicionado ao `requirements.txt`.

**Bug 3 — `build_entity_index` capturava `) ;` como parte dos args**

A regex primária de `build_entity_index` usava `(.*)(?:\)\s*;?)?` onde o grupo opcional
nunca fazia backtrack — o `(.*)` greedy consumia o `) ;` final da linha.
Resultado: args de `IFCLOCALPLACEMENT(#27,#46) ;` eram indexados como `'#27,#46) ;'`.

Ao chamar `resolve_lp` → `split_top('#27,#46) ;')` → `['#27', '#46) ;']` →
`int('#46) ;'.lstrip('#'))` → `int('46) ;')` → `ValueError` → todas as entidades puladas.

**Correção aplicada:** substituição da regex bugada pela regex de fallback (que já estava
correta, usando `(.*)\)\s*;?\s*$` com backtracking forçado até o último `)` da linha):
```python
# Antes (bugado):
m = re.match(r'#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)(?:\)\s*;?)?\s*$', line)
if not m:
    m = re.match(r'#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)\)\s*;?\s*$', line, re.DOTALL)

# Depois (correto — uma única regex):
m = re.match(r'#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)\)\s*;?\s*$', line)
```

**Bug 4 — `_process_faceset` lia CoordIndex do campo errado**

`IFCTRIANGULATEDFACESET` tem 5 atributos: `Coordinates, Normals, Closed, CoordIndex, PnIndex`.
O código lia `fs_parts[1]` (Normals) como CoordIndex em vez de `fs_parts[3]`.
Nos arquivos Dancor/CATIA, `Normals` contém vetores float (`((0.3,0.9,...),...)`) —
`parse_ints` extraía dígitos desses floats como "índices", gerando `IndexError` ao
acessar `coord_list[vi-1]`.

**Correção aplicada:** `coord_index_str = fs_parts[1]` → `fs_parts[3]`.
Guard atualizado de `len(fs_parts) < 2` → `< 4`.

**Estado pós-correção e validação:**
- Dancor: todos os 14 IFCs parseados com 50k–150k vértices cada; redução ~79% pelo dedup
- Pipeline completo rodou com sucesso: parse → dedup → catalog.json → preview HTML → ZIP
- Amanco: código de B-rep implementado (ifcopenshell), mas estrutura de dirs aninhada ainda
  limita quais categorias são detectadas pelo `scan_input` (problema arquitetural separado)

### 2026-08-24 — Bug 5: parse_floats quebrava em notação científica sem dígito fracionário (commit 2bf5607)

Coordenadas IFC exportadas pelo CATIA usam formato `-4.E-16` e `1.E+00` — notação científica
sem dígitos entre o ponto decimal e o expoente. A regex `[0-9]*\.?[0-9]+` exigia ao menos
um dígito após o ponto, então `-4.E-16` era extraído como dois números: `-4` e `-16`.

Resultado: sub-peças com esse valor de coordenada (INTERMEDIARIA, MOTOR) apareciam
deslocadas exatamente em 16m do corpo da bomba.

Bombas afetadas: 105-50 TJM, 51-30W TJM, 109_40 TJM.

```python
# Regex corrigida — aceita ponto sem dígito fracionário
r'[-+]?(?:[0-9]+\.?[0-9]*|[0-9]*\.[0-9]+)(?:[eE][-+]?[0-9]+)?'
```

### 2026-08-24 — Correções de documentação e pipeline

- `build_zip()` em `build.py`: manifest.json gerado com campos em **inglês** conforme
  contrato da API bilds.com (`title`, `manufacturer`, `description`, `filters`, `productCount`).
  Antes usava os mesmos campos em português do `catalog.json`.
- ZIP renomeado de `bilds-upload.zip` para `<slug>-AAAAMMDDHHMM.zip`.
- `output/preview/.gitignore` criado para excluir `*_raw.json` (artefatos do CLI do parse_ifc).
- Skill `leitor-ifc` atualizada para v1.3.0 com todos os 5 bugs e suas correções documentadas.

### 2026-08-24 — Matching fuzzy IFC → .aq por cobertura de tokens (commit d75cf7b)

`find_aq_product(slug, product_map, ifc_path_hint=None)` — substituição do match por
prefixo simples por scoring de cobertura de tokens:

- **Tokenização do caminho**: todos os componentes do path relativo do IFC viram tokens
  (ex: `"Cap/PVC Esgoto SN/100mm.ifc"` → `{cap, pvc, esgoto, sn, 100mm}`).
- **Score de grupo**: `covered_tokens / total_gp_tokens`. Exige ≥ 100%; relaxa para ≥ 75%
  se não encontrar nada. Em empate, prefere o grupo com mais tokens (mais específico).
- **Score de peça**: dentro do grupo vencedor, a PECA com maior sobreposição com o leaf
  (nome do arquivo sem extensão e sem pasta) é selecionada.
- **Nome composto**: se o nome do GRUPO_PECA não está contido no nome da PECA, o build
  produz `f"{nome_gp} {peca['nome']}"` como nome do produto (ex: `"Cap 100mm"`).
- **Fallback**: prefixo/número preservado para IFCs flat sem hierarquia (Dancor).

`build_catalog()` passa `ifc_name` (a chave do `file_map`) como `ifc_path_hint`.

### 2026-08-24 — interactive_config: aq_stale, scan_input e inferência do .aq (commits 572956a…8c2deff)

**Bug 7 — scan_input modo subdir com múltiplos IFCs quebrava o parse (commit fb7dcc8)**

`input/Dancor/` com 14 IFCs era detectado como modo `subdir` (1 produto = subdir inteiro).
O display name `"Dancor/ (14 IFCs)"` ia como chave do `file_map`; o parser tentava abrir
esse string como arquivo → AVISO + ZIP 0KB.

Correção: modo `subdir` só ativo quando cada subdir tem **exatamente 1 IFC**; caso contrário
cai em modo `recursive` (cada IFC = um produto).

**Bug 8 — aq_stale não resetava titulo/slug (commit 056e729)**

Quando o .aq mudava (ex: Amanco → Dancor), `fabricante` era resetado mas `titulo` e `slug`
continuavam vindo do `config.json` stale. Slugs errados (ex: `"amanco-conexoes"`) persistiam
para o novo catálogo.

Correção: quando `aq_stale=True`, `sug_titulo` e `sug_slug` derivam apenas dos hints/filename
do novo .aq, não do `ec` (config existente).

**Bug 9 — fabricante e título não inferidos do filename do .aq (commit 8c2deff)**

Campo `BIBLIOTECA` na Dancor .aq está vazio → `hints['fabricante'] = ''` → prompt sem default.

Correção: `peek_aq()` analisa o filename após falha no banco:
- `pecas_dancor_bombas_incendio_2026_04.1.aq` → remove ruído (`pecas`, anos `2026`, versão `04`)
- 1º token restante = fabricante (`Dancor`)
- Tokens restantes = título (`Bombas Incendio`)

Resultado: usuário passa por `--interactive` só com Enter em todos os campos.

**Bug 10 — slugify não normalizava acentos (commit 8e2f67d)**

`re.sub(r'[^a-z0-9]+', '-', s.lower())` convertia `ê` em `-` (não é ASCII).
`"Incêndio"` → `"inc-ndio"`. Corrigido com NFD + strip combining marks:
```python
s = unicodedata.normalize('NFD', s)
s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
```
Agora: `"Bombas de Combate a Incêndio"` → `"bombas-de-combate-a-incendio"`.

**Bug 11 — slug derivava de fabricante+1ªpalavra, não do título completo (commits 8e2f67d, fefb627)**

`sug_slug` usava `f"{fabricante}-{titulo.split()[0]}"` → `"dancor-bombas"` em vez de
`"bombas-de-combate-a-incendio"`. Além disso, `ec.get('slug')` tomava precedência e
exibia o slug antigo do `config.json` mesmo após o usuário alterar o título.

Correção: `sug_slug = slugify(titulo or fabricante or 'catalogo')` — sempre re-calculado
a partir do título confirmado na pergunta anterior, sem herdar valor do config.

### 2026-08-24 — Refinamentos do modo interativo (sessão 2, commit c740086 → 5f2f2d2)

**Slug removido do fluxo interativo**

A pergunta `Slug da URL [...]` foi removida — o slug é calculado automaticamente de
`slugify(titulo)` e apenas exibido. O usuário não precisa confirmar nem editar.

Motivação: slug é derivado do título; pedir os dois é redundante. Para alterar o slug
basta alterar o título.

**peek_aq usa hierarquia de pastas como fonte primária de título e fabricante**

Antes, `peek_aq` usava o campo `BIBLIOTECA` do banco e o filename do `.aq` como fallback,
produzindo títulos de baixa qualidade (ex: `"Esgoto Sn Sr Silentium"` do filename).

Correção: lê `parent_dir` (pasta pai do `.aq`) como título e `grandpa_dir` (avô) como
fabricante, antes de qualquer fallback por filename. Pasta pai é o nome real da linha de produto.

```
input/Amanco/PVC Esgoto SN, SR e Silentium/pecas.aq
              ↑ grandpa → fabricante        ↑ parent → título
```

Resultado: título sugerido passa a ser `"PVC Esgoto SN, SR e Silentium"` (correto) em vez de
`"Esgoto Sn Sr Silentium"` (ruim). Diretórios genéricos (`input`, `bim`, `.`) são ignorados.

**Regra de commits estabelecida**

Mensagens de commit devem descrever features e decisões, nunca associar a fabricantes ou
dados de input (fabricantes são variáveis e efêmeros).
- Correto: `feat(peek_aq): inferir título da pasta pai do .aq`
- Errado: `feat: pipeline validado com Amanco 502 IFCs`

**Ponto estável: commit `6336f60`** — pipeline completo, documentação autocontida, preview dos dois catálogos no repo.
Para retornar: `git checkout 6336f60`.

### 2026-08-24 — Bug WebGL: shared renderer + JPEG capture (commits b73ee8a, 35d63db)

**Problema:** ao rolar para baixo e carregar muitos cards 3D, depois voltar para cima,
as miniaturas desapareciam. Console exibia: `WARNING: Too many active WebGL contexts. Oldest context will be lost.`

O código anterior criava um `WebGLRenderer` por card via `IntersectionObserver` e nunca
destruía o contexto — o browser limita a ~8–16 contextos simultâneos.

**Arquitetura nova: shared renderer + JPEG capture**

- `sharedRenderer`: um único `WebGLRenderer` com `preserveDrawingBuffer: true`, criado
  sob demanda e reutilizado sequencialmente para todos os thumbnails.
- Após render: `canvas.toDataURL('image/jpeg', 0.88)` → `<img>` tag. Zero contextos WebGL
  persistentes por card.
- `thumbCache (Map<id, dataURL>)`: sobrevive a filtros (DOM é destruído/recriado ao filtrar).
  Quando card volta ao DOM, restaura do cache sem re-render.
- `renderQueue + processQueue`: fila sequencial garante um render por vez.
- `activeCard`: viewer interativo ao clicar no thumb (OrbitControls + loop de animação).
  `IntersectionObserver` deativa automaticamente ao sair da viewport e restaura o thumb.
- `disposeScene`: libera geometrias e materiais da GPU após cada thumbnail.
- Máximo 3 contextos WebGL em qualquer momento: `sharedRenderer` + `activeCard.renderer`
  + `modalViewer.renderer`.

**Bug 12 — `observeCards()` não chamado no carregamento inicial (commit 35d63db)**

O evento `cards-rendered` disparava no script síncrono (durante o parse do HTML), mas
o listener no módulo ES só registrava após `DOMContentLoaded` — chegava tarde demais.
Resultado: Amanco não carregava miniaturas até o primeiro clique em filtro.

Correção: adicionar `observeCards()` direto após o `addEventListener` no módulo, além
de manter o listener para re-renders (ao filtrar).

**Ponto estável: commit `35d63db`** — WebGL context overflow resolvido, validado em produção.
Para retornar: `git checkout 35d63db`.

### 2026-08-24 — Estudo OQ3D: a geometria sai do .aq (commits 912bf38, 8414bb2, 9b85f6c)

**A descoberta.** O `.aq` não é só o banco de dados de produto: carrega a malha 3D
completa, com cor e miniatura, no BLOB `SIMBOLOGIA_3D.SIMBOLOGIA_3D`, em formato
binário proprietário (OQ3D). É o mesmo sólido que o AltoQi exporta como IFC.
Consequência: **os IFCs deixaram de ser necessários** no caminho padrão.

**Como foi validado.** Três bibliotecas de naturezas opostas, mais um teste cego:

| Biblioteca | Schema | Peças | Geometrias | IFCs de contraprova |
|---|---|---|---|---|
| Dancor (bombas) | 607 | 13 | 13 | 14, tessellated |
| Amanco (conexões PVC) | 595 | 1.168 | 457 | 502, `IFCADVANCEDBREP` |
| Intelbras (elétrica) | 572 | 32 | 18 | nenhum — teste cego |

Onde o IFC é tessellated, os triângulos batem **exatamente** (37-40 TJM: 44.951 em
ambos). Onde é B-rep, a forma converge a 0,3 mm mas a tesselação é independente —
o IFC guarda o sólido exato e é retessellizado a cada leitura, o `.aq` traz a malha
que o AltoQi fixou. O lote final rodou sobre **9 bibliotecas e seis versões de
schema** (552, 562, 572, 582, 595, 607) sem uma falha.

**Bug do parser linear (achado na Amanco).** Nas bombas, as malhas já vêm em
coordenadas de mundo — dá para ignorar os transforms e ainda renderizar certo. Nas
conexões **não**: cada peça é montada de malhas reaproveitadas e posicionadas por
`TCoordinateTransformation3D`. O primeiro parser produzia joelhos retos. Exigiu
parser de árvore com pilha (`scripts/oq3d.py`).

**Bug colateral no `parse_ifc.py` — ainda aberto.** Ao resolver o Caminho B, o
código procura o face set direto dentro do `IFCREPRESENTATIONMAP`, mas falta um
nível: `IFCMAPPEDITEM → IFCREPRESENTATIONMAP → IFCSHAPEREPRESENTATION →
IFCTRIANGULATEDFACESET`. Na CAM-W21 isso descarta 3.231 triângulos (13,8%) — as
peças instanciadas. Afeta só o modo `--ifc`.

**O `file_map` morreu.** O vínculo `PECA → PECA_SIMBOLOGIA_3D → SIMBOLOGIA_3D` é
chave estrangeira. O matching por tokens do `find_aq_product` é comprovadamente
frágil: ao tentar parear os 502 caminhos de IFC da Amanco com os nomes do banco,
`Junção Simples + Joelho 45/Com luva` casou com `Luva Simples 200MM` — cobertura
100%, peça errada.

**Variantes com e sem luva.** O AltoQi exporta **dois IFCs por peça** (com e sem a
luva de encaixe) e o banco guarda só a canônica — a com luva. Explica os 502 IFCs
para 457 geometrias. Medindo por bounding box: 76% de cobertura nos "com luva",
1,5% nos "sem luva".

**Peças sem forma fixa.** 312 das 1.168 peças da Amanco (27%) não têm geometria, e
é o correto: tubos (cilindro paramétrico por diâmetro × comprimento) e kits de
aparelho sanitário. O build informa quantas pulou.

**Erros cometidos nesta sessão, e o que ensinaram:**

- **Faltou o `dedup()`** no caminho `.aq` — só o caminho IFC aplicava. O preview
  foi para 571 MB; com dedup, 347 MB para 9 catálogos (antes: 155 MB para 2).
- **`output/*.zip` não cobre subpastas.** Como a saída passou a espelhar o input,
  os 9 ZIPs escaparam do gitignore. Corrigido com `output/**/*.zip`.
- **`./data/` quebra com `cleanUrls`.** Mover o `data/` para dentro do catálogo
  (necessário: `50mm.json` colide entre bibliotecas) expôs que a página é servida
  em `/<slug>` sem barra final, e o relativo resolve para a raiz. O sintoma
  enganoso era `Unexpected token 'T'` — a página 404 da Vercel caindo no
  `JSON.parse`. Agora o `fetch` checa `r.ok` antes de parsear.

**Pendência da época (resolvida em 2026-08-30):** parafusos faltando na Dancor —
13 de 18 instâncias não emitiam geometria, e uma peça aparecia solta no ar. Eram
dois bugs distintos: a referência da instância repetida e a rotação column-major.
Ver "Instâncias repetidas — RESOLVIDO" na seção do `oq3d.py`.

**Ponto estável: commit `9b85f6c`** — 9 catálogos em produção, geometria servindo
200 em todos. Para retornar: `git checkout 9b85f6c`.

### 2026-08-27 — Miniaturas pré-renderizadas no build (BILDS-552)

**O gatilho.** Lighthouse em `bilds.com/dancor/bombas-incendio` mostrou LCP de 39,9 s com
score 0. O elemento LCP é o `<img src="data:image/jpeg;base64,…">` do card — a miniatura
que o próprio browser gera. Decomposição: 259 ms de TTFB e **7.230 ms de element render
delay**. Ou seja, 96,5% do LCP é esperar o browser baixar geometria e rodar WebGL.

**O que a medição mostrou, além do LCP:**

- **Zero compressão nos `geo/*.json`.** `transfer 1.765 KB / resource 1.763 KB` — razão
  1,00×. A API serve cru. No ZIP o deflate dá 5,8×, então há um ganho grande parado ali.
- **3,75 MB para desenhar 2 miniaturas** em viewport mobile; 57% das 6.610 KiB da página.
- As geometrias carregam **em série** — a fila de render é um `while` sequencial.

**O que foi construído.** `build_thumbs()` em `build.py`, dirigindo
`scripts/thumbs.mjs` (Node + Playwright), que abre `templates/thumbs/harness.html` no
Chromium e chama `window.renderThumb()` por geometria. Saída em
`output/thumbs/<origem>/<slug>/*.webp`, empacotada em `thumbs/` no ZIP, com o campo
`produto.thumb` anotado no `catalog.json`.

**Por que browser e não rasterizador em Python.** O pedido era usar *a imagem que a página
gera*, não uma aproximação. `MeshStandardMaterial` é PBR com metalness/roughness sobre três
luzes; reproduzir isso em numpy daria algo parecido e diferente. Dirigir o mesmo Three.js
no Chromium dá a imagem idêntica — ao custo de uma dependência de browser, que foi isolada
num `package.json` próprio e degrada em silêncio quando ausente.

**Decisões que valem lembrar:**

- **Uma miniatura por geometria, não por produto.** A câmera sai só do bounding box, então
  geometria compartilhada produz imagem idêntica. Amanco: 856 produtos → 448 arquivos.
- **`pixelRatio` fixo em 1** no harness, com `setSize(448, 324)`. No runtime é
  `min(devicePixelRatio, 1.5)` porque lá o alvo é a tela do visitante; aqui o alvo é um
  arquivo de dimensão previsível.
- **Fundo `#F3F4F6` opaco**, igual ao `setClearColor` do viewer e ao `bg-gray-100` do card.
  É o que permite letterbox invisível quando o card é mais largo que a proporção da imagem.
- **Tudo opcional.** Sem Node, sem Playwright, sem browser ou com `--skip-thumbs`, o build
  avisa e segue. Produto sem `thumb` cai no render dinâmico. Catálogo publicado antes disso
  continua funcionando sem re-upload.

**Armadilhas pagas:**

- O Chromium headless não inicializa WebGL sem
  `--use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader`. Não há GPU em
  WSL, CI nem container; sem os flags o `renderThumb` falha em todas as geometrias.
- **Dois Node na mesma máquina.** `/usr/bin/node` é v18 aqui e o nvm tem v24; o nvm só
  entra no PATH de shell interativo, então o `subprocess` do `build.py` pegava o v18 e o
  Playwright recusava. Daí o `_find_node()`.
- **Libs de sistema sem sudo.** `apt-get download` + `dpkg-deb -x` + `LD_LIBRARY_PATH`
  resolve sem root — foi como esta sessão validou. Receita no `README.md`.
- **`sudo` descarta o PATH e derruba o `install-deps`.** `sudo npx playwright
  install-deps chromium` — o comando que a própria documentação do Playwright manda —
  falha em máquina com nvm: o `secure_path` do sudo faz o `npx` cair no Node do apt e o
  Playwright recusa por versão. O sintoma engana, porque `node --version` e `nvm default`
  no shell mostram a versão nova. Use `sudo apt-get install -y libnss3 libnspr4
  libasound2t64`, ou `sudo env "PATH=$PATH" npx playwright install-deps chromium`.

**Validado nos 9 catálogos — 622 geometrias, zero falhas:**

| Catálogo | Geometrias | geo | thumbs | Razão |
|---|---|---|---|---|
| `pvc-esgoto-sn-sr-e-silentium` | 457 | 145,0 MB | 1.858 KB | 80× |
| `cftv` | 55 | 54,3 MB | 222 KB | 251× |
| `sdai-fiacao` | 25 | 29,2 MB | 111 KB | 270× |
| `sensor-alarme` | 16 | 16,6 MB | 61 KB | 281× |
| `equipamento-de-rede-rack` | 17 | 17,0 MB | 68 KB | 256× |
| `ppci-incendio` | 11 | 15,3 MB | 48 KB | 328× |
| `cont-acesso-cond` | 10 | 19,9 MB | 46 KB | 442× |
| `bombas-incendio` | 13 | 44,7 MB | 74 KB | **620×** |
| `dispositivos-eletricos-inteligentes` | 18 | 6,3 MB | 70 KB | 92× |
| **TOTAL** | **622** | **348,2 MB** | **2,5 MB** | **136×** |

Média de **4 KB por miniatura**. Render a ~0,08 s por geometria depois do browser subir
(os 457 do Amanco em 36 s).

O que isso faz com a primeira viewport da Dancor, que era o pior caso: **3,75 MB → 12 KB**
em mobile (2 cards) e **40 MB → ~72 KB** em desktop (12 cards).

**Dependência do outro lado.** `thumbs/` e `produto.thumb` nasceram como extensão
proposta: a API do bilds.com ainda não extraía a pasta. O trabalho correspondente ficou
na branch `perf/BILDS-552-bim-3d-miniatura-estatica` do bilds.com — hoje mergeada
(PR #1244, ver "Dependência cruzada com o bilds.com" no topo deste arquivo).

**O estudo que motivou tudo isso está resumido abaixo — não é preciso abrir nada fora
deste repositório.** Ele foi medido sobre `output/preview/` desta própria árvore.

Custo da **primeira viewport** (grid de ~4 colunas, ~12 cards antes de rolar), antes das
miniaturas, quando cada card baixava o JSON de geometria e rodava WebGL + `toDataURL`:

| Catálogo | Produtos | Geometrias na 1ª viewport | Cru | ~gzip |
|---|---|---|---|---|
| `bombas-incendio` (Dancor) | 13 | 12 | **40,4 MB** | ~7,0 MB |
| `cftv` | 60 | 11 | 10,9 MB | ~1,9 MB |
| `sdai-fiacao` | 51 | 7 | 9,9 MB | ~1,7 MB |
| `dispositivos-eletricos-inteligentes` | 32 | 8 | 3,2 MB | ~0,6 MB |
| `pvc-esgoto-sn-sr-e-silentium` | 856 | 12 | 2,7 MB | ~0,5 MB |

Peso por geometria: de **324 KB** de média (Amanco) a **3,5 MB** (Dancor); maior arquivo
4,8 MB. Razão de compressão medida no ZIP: **5,8×**.

Dois achados do estudo que continuam valendo:

- **Contextos WebGL simultâneos eram 3, não 2.** O `sharedRenderer` é um contexto
  persistente de módulo e costuma não ser contado; somam-se a ele o viewer do card ativo
  (montado no `onMouseEnter`) e o do modal. Remover o viewer do card leva a 2.
- **As geometrias são gravadas cruas no S3**, sem `ContentEncoding: 'gzip'`. Se há
  compressão, ela vem da opção "Compress objects automatically" do CloudFront — o que não
  dá para verificar por nenhum repositório. No pior caso é a diferença entre 40 MB e 7 MB.
  Confirmar no console AWS.

### 2026-08-28 — Encoding cp1252: nomes de peça chegavam quebrados na bilds.com

**Achado durante a verificação do BILDS-552.** Com a página do catálogo finalmente
carregando rápido, deu para ler os nomes — e eles estavam errados:
`5U \x96 19\x94 x 570mm MRD 557` em vez de `5U – 19” x 570mm MRD 557`.

**A causa estava escrita no próprio docstring:** _"Encoding: latin-1 (Windows-1252)"_.
Os dois não são a mesma coisa. Diferem só na faixa 0x80–0x9F, que é justamente onde estão
os caracteres tipográficos que aparecem em nome de produto. A confusão vinha desde o
primeiro commit do `read_aq.py`, e nunca deu erro — latin-1 decodifica qualquer byte.

**Escopo real:** 2 das 9 bibliotecas têm caracteres nessa faixa, mas o defeito era
visível em produção para qualquer catálogo com travessão ou aspas no nome.

**O que quase deu errado no conserto.** Trocar o `text_factory` direto para cp1252 teria
corrompido a geometria: o latin-1 era byte-preserving e o código reconstruía o BLOB com
`.encode('latin-1')` quando a coluna voltava como `str`. Com cp1252 esse caminho não é
reversível. Resolvido com `CAST(... AS BLOB)` nas queries de `SIMBOLOGIA_3D`, que força
bytes e dispensa o re-encode.

**Verificação:** hash SHA-256 de todos os blobs de geometria e imagem, antes e depois —
idêntico em Dancor e Intelbras CFTV. E zero bytes de controle nos nomes das 9
bibliotecas (1.441 peças).

**Regra que fica:** ao mexer em decodificação, medir o binário antes e depois. Texto
errado é visível; binário corrompido não é.

### 2026-08-29 — S1.2: carga de prova ponta a ponta (POC dinâmico)

**Contexto:** primeira carga real de dados no Atlas. Três entregáveis independentes,
todos no `www/`.

**1 — Proteção anti-path-traversal no `DiskGeometryStore`**
(`www/apps/api/src/geometry-store/disk-geometry-store.ts`)

`validateKey(key)` adicionado como método privado e chamado na entrada de todos os quatro
métodos públicos (`put`, `get`, `delete`, `deleteByPrefix`). Usa `path.resolve(baseDir,
key).startsWith(baseDir + path.sep)` — verificação léxica, não segue symlinks.
Para `deleteByPrefix`, valida `prefix + '/placeholder'` em vez do prefix nu (que não
terminaria dentro do baseDir pelo critério de `sep`). Código de erro: `ETRAVERSAL`.

O smoke test (`www/tools/smoke-geometry-store.ts`) ganhou três padrões de traversal
(`'../etc/passwd'`, `'geo/../../etc/passwd'`, `'/etc/passwd'`), todos via `store.get()`.
Saída mudou de `'OK'` para `'smoke test passed'`.

**Limitação conhecida e aceita:** `path.resolve` é léxico — um symlink dentro de
`STORAGE_PATH` criado por outro processo escaparia a proteção. Requer `fs.realpath` para
fechar completamente; postergado (registrado no review S1.2 como finding A1 suprimido).

**2 — Endpoint `GET /geometrias/:productId` e `GeometriasModule`**
(`www/apps/api/src/geometrias/`)

Novo módulo NestJS com `GeometriasController` e `GeometriasModule`. O controller:
- Busca o `BimProduct` por `_id` via Mongoose `findById(productId).lean()`
- Chama `store.get(product.geoKey)` e devolve o Buffer com `Content-Type: application/json`
- Converte `ENOENT` em 404; outros erros propagam como 500
- Usa `@Res()` (bypassa interceptors NestJS — trade-off aceito para POC)

`GeometriasModule` importado em `AppModule`. Endpoint disponível em `http://localhost:4000/geometrias/:id`.

**Pendências abertas do endpoint** (registradas no review S1.2):
- Sem `@UseGuards()` — intencional para POC; **não expor em rede sem adicionar guard**
- `findById` com string bruta → CastError vira HTTP 500 em vez de 400; corrigir em S2.x
  com `Types.ObjectId.isValid(productId)` antes da query

**3 — Script de ingestão `ingest-library.ts`**
(`www/tools/ingest-library.ts`, `www/package.json`)

Script TypeScript que lê `output/Dancor/bombas-incendio-catalog.json`, chama o pipeline
Python para gerar os JSONs de geometria, grava no `GeometryStore` e insere documentos no
Atlas (`bim_companies`, `bim_catalogs`, `bim_products`). Roda com `pnpm ingest`.

**Armadilha nova — NODE_PATH para scripts fora do workspace pnpm:**
`www/tools/` fica fora do workspace pnpm (`www/apps/api`, `www/apps/web`), então os
módulos do `node_modules` não são encontrados por `ts-node` normalmente. Workaround:

```bash
NODE_PATH=$(pwd)/node_modules node --require ts-node/register/transpile-only \
  --require reflect-metadata ../../tools/ingest-library.ts
```

Encapsulado no script `pnpm ingest` via filtro `--filter api exec sh -c '...'`.

**Medições registradas** (Dancor, 13 produtos com geometria):
- Gravação: ~722 ms total (~55 ms/produto), pico de memória ~45 MB
- Leitura via API (`GET /geometrias/:id`): mediana ~30,5 ms
- Leitura estática de arquivo: mediana ~1,9 ms
- Overhead da API (NestJS + Mongoose + disco): ~28,6 ms por request no POC local

**Estado do Atlas após S1.2:** 1 empresa (`Dancor`), 1 catálogo (`bombas-incendio`),
13 produtos com `geoKey` no formato `geo/{importId}/{p.id}.json`.

### 2026-08-30 — S3.3: página pública do catálogo (POC dinâmico)

**Entregável:** `/{empresa}/{catalogo}` renderizando com viewer 3D lendo geometria da API,
sem nenhum import de `react-i18next`. Commit `d4f6b1e`.

**`www/apps/web/src/components/bim-catalog/`** — 9 arquivos novos, todos sem i18n:
`types.ts`, `bim-viewer-engine.ts`, `BimViewer.tsx`, `LazyBimCard.tsx`, `CurveChart.tsx`,
`ProductModal.tsx`, `SeriesRowsLayout.tsx`, `CatalogGridLayout.tsx`, `BimCatalogView.tsx`.

**`www/apps/web/src/app/[empresa]/[catalogo]/page.tsx`** — Server Component. Busca
`/catalogos/{empresa}/{catalogo}`, converte `geoUrl`/`thumbUrl` para URLs absolutas
(`http://localhost:4000`), passa para `BimCatalogView`. `notFound()` em 404 ou erro.

**Tailwind v4:** `postcss.config.mjs` + `globals.css` + import em `layout.tsx`.
`pnpm add --filter web tailwindcss @tailwindcss/postcss` + `three @types/three`.

**`findLatestByOwnerId` enriquecido** com `catalogSlug` (join com `bim_catalogs`);
empresa page mostra link "Ver catálogo" quando status é `publicado`.

**Decisões de arquitetura:**
- Tipos próprios `PocProduct`/`PocCatalog` em vez de reutilizar tipos da bilds.com —
  a interface da POC difere (`geoUrl` absoluto por produto vs. `geo` filename + baseUrl)
- URLs absolutas no Server Component, não em cada componente cliente
- Strings em português hardcoded ("Fechar", "Especificações", "Curva Q-H", etc.)

**Verificado:** `pnpm smoke:geo` → passed; `curl localhost:3000/dancor/bomba-de-combate-a-incencio`
→ HTTP 200 com 13 produtos; rota inexistente → 404.

### 2026-08-30 — S3.2b: deduplicação, fix de IPC e progresso de upload (POC dinâmico)

**Deduplicação de vértices implementada em `parse-worker.ts`.** O `dedupBuffers()` em
TypeScript é equivalente ao `scripts/dedup.py` Python: usa bit-cast float32 (mesmo `DataView`
trick que o Three.js `Float32BufferAttribute` usa internamente) como chave de lookup.
Redução de 61–83% nos vértices; geometrias 3–5× menores. Validado com Amanco 393 MB →
856 produtos em 12 s.

**Bug crítico de IPC corrigido.** `process.send!(result)` seguido de `process.exit(0)` imediato
descartava o payload IPC quando o buffer não tinha terminado de ser entregue ao pipe do kernel.
Para a Dancor (13 produtos, payload pequeno) o flush era síncrono na prática e não se manifestava.
Para a Amanco (856 produtos) o `child.on('message')` nunca disparava — import ficava preso
em `parseando` até o timeout de 5 min. Fix: `process.send!(result, () => process.exit(0))`.

**Progresso de upload com XHR.** `fetch()` não tem `upload.onprogress`; migrado para
`XMLHttpRequest`. Barra de progresso CSS com `transition` e label que muda de
`"Enviando… X%"` para `"Processando…"` quando o upload termina.

### 2026-08-30 — S3.2: upload da biblioteca (POC dinâmico)

**Endpoints de importação protegidos por auth.** `POST /importacoes` agora exige Bearer
token e deriva a empresa do `ownerId` do JWT (elimina possibilidade de subir para empresa
de outro usuário via query param). `GET /importacoes/ultima` retorna a última importação
do usuário para recovery de página. `GET /importacoes/:id` verifica dono.

**Página `/empresa/importar`.** Upload de `.aq` com acompanhamento visual dos estados da
máquina (`recebido → parseando → gravando → publicado | vazio | falhou`). Polling a cada
3 s. Recovery: ao recarregar, chama `GET /api/importacoes/ultima` e retoma polling se
estado não-terminal. `vazio` (arquivo sem geometrias) exibe box amarelo distinto de `falhou`.

**Armadilha nova: Next.js dev mode trunca body em 10 MB.** O arquivo `.aq` da Dancor tem
~153 MB — o proxy `POST /api/importacoes` no Next.js dev mode tronca o body e o parse
falha. Workaround: o browser faz upload direto para `http://localhost:4000/importacoes`
(CORS configurado); o Bearer token é obtido via `GET /api/auth/token` (expõe JWT ao JS
do cliente — aceitável na POC). Em produção: upload direto para S3 com presigned URL.

**Armadilha confirmada: processo antigo na porta 3000 OU 4000.** Matar e reiniciar antes
de testar qualquer mudança nos dois servidores.

### 2026-08-30 — S3.1: login e empresa (POC dinâmico)

**Auth mínima para a POC:** JWT assinado com `JWT_SECRET` (env). `POST /auth/login` valida
`SEED_USER`/`SEED_PASSWORD` (env). `AuthGuard` NestJS lê `Authorization: Bearer <token>`.

**Padrão de auth em dev (portas diferentes):** NestJS (`:4000`) retorna `{ token }` no body;
Next.js route handler (`/api/auth/login` em `:3000`) define cookie `session` httpOnly para
`:3000`. Requests protegidos passam pelo route handler que adiciona o header `Authorization`.
Em produção (mesmo domínio), o token poderia ir direto como cookie da API.

**Empresas criadas via `POST /empresas` (guarded).** Slug de `customUrl` sanitizado no servidor
(`lowercase + [^a-z0-9-] → '-'`). Logo: multipart opcional até 2 MB, armazenado em
`STORAGE_PATH/logos/{companyId}.{ext}` via `fs.writeFileSync`. Servido por `GET /logos/:id`.

**Armadilha: `@types/multer` ausente causa falha `TS2694`** no `ts-node` ao usar
`FileInterceptor` (o tipo `Express.Multer.File` não é exportado sem ele). Solução:
`pnpm add --filter api -D @types/multer`. Já instalado.

**Novos env vars em `www/.env`:** `JWT_SECRET` (gerado com `secrets.token_hex(32)`). Já
existiam `SEED_USER` e `SEED_PASSWORD`.

### 2026-08-30 — S2.4: miniaturas no servidor (ADR-003)

**Abordagem escolhida: rasterizador TS software (Abordagem B).**

Medição comparativa com 39 produtos Dancor:

| Abordagem | Média ms/geo | KB/WebP | Notas |
|---|---|---|---|
| **B (TS rasterizador)** | **65 ms** | **4,3 KB** | sem browser, flat shading |
| A (Playwright + SwiftShader) | 240 ms | 5,5 KB | PBR idêntico ao viewer; +startup 2-5 s; +1,5 GB Docker |

B é **3,7× mais rápido** por geometria. Imagens menores. Sem Chromium no pod.
ADR-003 fechado. Ver `docs/plano-produto-dinamico.md` seção 9.

**Arquivos criados:**
- `www/tools/thumb-rasterizer.ts` — rasterizador TS puro. Projeta vértices em
  perspectiva (FOV 38°, câmera em `size*[0.85, 0.32, 0.85]`), z-buffer, flat shading
  (ambient 0.7 + key 0.9 + fill 0.35), fundo #F3F4F6. Codifica via ffmpeg `libwebp`.
  Exporta `renderThumbTs(data, w?, h?)`. Dimensão padrão: 448×324.
- `www/tools/measure-thumbs.ts` — script de medição (`pnpm thumb:measure`).
- `www/apps/api/src/importacoes/thumb-worker.ts` — worker fork que lê geo JSON,
  chama `renderThumbTs`, grava `.webp` e reporta `thumbKey` via IPC.

**Modificado:**
- `www/apps/api/src/importacoes/importacoes.service.ts` — após publicar, dispara
  `spawnThumbWorker` fire-and-forget. Erros são silenciados — miniaturas são opcionais.
- `www/package.json` — script `thumb:measure`.

**Verificado ponta a ponta:** `POST /importacoes` → publicado → 13 WebPs gerados em
~1 s → `thumbKey` salvo no Atlas → `GET /thumbs/:productId` retorna HTTP 200 image/webp
com ETag + Cache-Control imutável (4.178 bytes).

**Armadilha: API precisa rodar com o código atual.** O processo que estava em porta 4000
ao iniciar esta sessão era o da S2.3 (sem `spawnThumbWorker`). Upload funcionou, mas
thumbs não foram gerados. Solução: matar o processo antigo antes de subir novo. Não é
problema em produção (deploy reinicia o processo).

**ffmpeg para WebP:** `sharp` não está instalado. O `ffmpeg` em
`~/.local/bin/ffmpeg` tem `libwebp`. Sem `-vf vflip` — rawvideo rgba no ffmpeg é
top-to-bottom, igual ao buffer do rasterizador.

**Playwright (`bilds-bim-3d/node_modules/`):** o playwright está em dois níveis acima
de `www/tools/`, não três. `path.resolve(__dirname, '../../node_modules/playwright')`.

### 2026-08-30 — S2.3: importação server-side e rotas de leitura

**Novos módulos em `www/apps/api/src/`:**

- `importacoes/` — `POST /importacoes`: recebe `.aq` (até 300 MB), valida ZIP se ZIP
  (parsing manual de LFH sem lib externa), grava temp, cria registro de importação e
  dispara `processAsync()` fire-and-forget.
- `importacoes/parse-worker.ts` — worker em `child_process.fork()` para isolar o
  `DatabaseSync` bloqueante. Recebe `{ aqPath, importId }` via IPC, usa `extract()` +
  `extractSimboloias()` + `toBuffers()` do port TS, escreve arquivos geo em
  `$STORAGE_PATH/geo/{importId}/{id}.json`. Timeout de 5 min (SIGKILL).
- `catalogos/` — `GET /catalogos/:empresa/:slug?serie=`
- `thumbs/` — `GET /thumbs/:productId` → 404 (S2.4)

**Modificados:**
- `geometrias/geometrias.controller.ts` — ETag (`sha1(geoKey)[0:16]`) + `Cache-Control: public, max-age=31536000, immutable`
- `bim-imports/bim-imports.schema.ts` — campo `note: string` para registrar substituição de catálogo

**Máquina de estados:** `recebido → parseando → gravando → publicado | vazio | falhou`.
Cleanup em `falhou`: `store.deleteByPrefix('geo/{importId}')` + `productModel.deleteMany({ importId })`.
Upload duplicado (mesmo `companyId + slug`): deleta produtos antigos, apaga arquivos geo do
import anterior, registra `note` no documento de importação.

**Limite de 300 MB para `.aq`:** o `.aq` é SQLite raw com BLOBs de geometria (Dancor ~153 MB,
Amanco >400 MB) — diferente dos ZIPs comprimidos da bilds.com. Limite inicial de 50 MB deu
413 no primeiro upload.

**multer via transitive dep:** multer v2.0.2 chega como transitive dep de
`@nestjs/platform-express`. `FileInterceptor` de `@nestjs/platform-express` o resolve do
virtual store do pnpm — sem necessidade de dependência direta.

**`deleteByPrefix` apaga arquivos, não diretórios.** O diretório do import substituído fica
vazio no disco. Comportamento aceitável — inofensivo, e o custo de remover o diretório não
vale a complexidade.

### 2026-08-30 — S2.2: spike do port TypeScript

**Port TypeScript de `oq3d.py` + `read_aq.py` (Dancor).**

**Arquivos criados:**
- `www/tools/oq3d-parser.ts` — parser OQ3D binário. Exporta `isOQ3D`, `parse`,
  `toBuffers`, `OQ3DError`. Segurança: valida `nCoord × 8` e `nIdx × 4` contra
  `buf.length` antes de qualquer `new Array(n)`.
- `www/tools/aq-reader.ts` — leitor `.aq` via `node:sqlite` (`DatabaseSync`, Node v24,
  sem flags). Usa `CAST(col AS BLOB)` em toda coluna de texto +
  `TextDecoder('windows-1252')`. Exporta `extract` e `extractSimboloias`.
- `www/tools/test-port-s2-2.ts` — teste de comparação semântica contra oráculo Python.

**Resultado do teste (`pnpm port:test`):**
- 13/13 produtos Dancor passam na comparação elemento a elemento
- Rejeição de blobs maliciosos: OK (sem assinatura, contagem > buffer, blob truncado)
- Tempo: 658 ms (Python S2.1: ~39 000 ms) — **59× mais rápido**
- RSS delta: 422 MB (Python S2.1: 189 MB) — 2.2× mais

**ADR-002 fechado:** prosseguir com port TS. Ganho de latência e eliminação de Python
superam o custo de memória (gerenciável; candidato a otimização com `Float64Array`
na representação interna em vez de `Array<[number,number,number]>`).

**Sobre `node:sqlite`:** `DatabaseSync` está disponível em Node v24 sem flags
experimentais. Retorna `Uint8Array` para colunas BLOB. `TextDecoder('windows-1252')`
não lança nos 5 bytes indefinidos do cp1252 (0x81, 0x8D, 0x8F, 0x90, 0x9D).

**Sobre a comparação semântica:** divergências de 1-2 ULPs (~10⁻¹⁵ relativo) são
esperadas entre numpy (BLAS/FMA) e aritmética escalar JS. A tolerância 1e-10 relativo
é usada no teste — rejeita erros reais (CM_TO_M ausente → 100×) e aceita ruído de
precisão de máquina.

### 2026-08-30 — S4.1: medição comparativa (POC dinâmico)

**Sessão de medição, sem código.** Entregável: `docs/sessoes/S4.1-medicao-comparativa.md`.

**Números principais (modelo banco vs estático CDN, catálogo Dancor 13 produtos):**

| Métrica | Estático (CDN) | POC (banco) |
|---|---|---|
| HTML size | 44 KB | 71.9 KB (1.6×) |
| 13 thumbs total | ~56 KB | 57 KB (≈ igual) |
| Bytes iniciais (com thumbs) | ~100 KB | ~129 KB (1.3×) |
| TTFB produção estimado | ~50ms (CDN) | ~150-300ms (SSR) |
| Tempo ao primeiro card | ~100ms | ~300ms (3×) |
| Geo por modal (com dedup) | 3.4 MB | 3.4 MB (≈ igual) |
| Geo por modal (sem dedup) | — | 14 MB (4×) |

**Achado — import ativo sem dedup.** O catálogo Dancor ativo no Atlas (`importId: 563e5794`)
foi importado antes da implementação do `dedupBuffers` em `parse-worker.ts`. Geo files têm
14 MB/produto (ratio vértices/triângulos = 3.0, mesh expandida) vs 3.4 MB com dedup
(import `5c60cb4e`, ratio 0.67 ≡ Python dedup.py). O código de dedup funciona — só o
import ativo é o legado sem dedup.

**LCP não medido com Lighthouse real** (WSL sem browser headless para Web Vitals). Estimativas
baseadas na soma de componentes medidos com `curl`.

**Respostas às 5 perguntas da seção 1:** ver registro da sessão §5.

### 2026-08-30 — S4.3: resolução das miniaturas (POC dinâmico)

**Causa raiz da baixa qualidade visual:** ausência de antialiasing no rasterizador TS.
O frame buffer era gerado em 448×324 sem supersampling, produzindo bordas serrilhadas.

**Diagnóstico:**
- CSS e dimensionamento OK: imagem 448×324 (ratio 1.383) + container h-[162px] min-w-[200px]
  com bg-gray-100 (#F3F4F6) bate o background da imagem → sem letterboxing visível
- Serviço `/thumbs/:productId` OK: HTTP 200, ETag, Cache-Control corretos
- Bug IPC em `thumb-worker.ts`: `process.exit(0)` imediato após `process.send!` (padrão errado)

**Correção: supersampling 2× em `www/tools/thumb-rasterizer.ts`:**
- `const SS = 2` adicionado — frame buffer interno: `width×SS` × `height×SS` = 896×648
- `encodeWebP` atualizado para receber srcW/srcH + outW/outH
- ffmpeg usa `-vf scale=448:324:flags=lanczos` quando src ≠ out → AA natural por downscaling
- Resultado: WebP 448×324 com bordas suaves; ~50% menor que antes (~2000–2500 vs ~4000–5500 bytes)
  (downscaling elimina ruído de borda → melhor compressão WebP)
- Tempo: ~90ms/thumb vs 65ms anterior (+38%; aceitável para fire-and-forget)

**Bug IPC corrigido em `www/apps/api/src/importacoes/thumb-worker.ts`:**
- `process.send!(...); process.exit(0)` → `process.send!(..., () => process.exit(0))`
- Padrão consistente com S2.2 e ADR do IPC

**Thumbs regenerados:**
- Dancor: 13 produtos (importId `5c60cb4e`) — o catálogo ativo no Atlas aponta para esse import
- Amanco: 856 produtos (importId `f7097e2e`)
- Nota: o importId `563e5794` existe no disco mas NÃO está ativo no banco (produtos do catálogo Dancor usam `5c60cb4e`)

**Arquivos modificados:** `www/tools/thumb-rasterizer.ts`, `www/apps/api/src/importacoes/thumb-worker.ts`,
`www/tools/regen-thumbs.ts` (novo), `www/package.json` (script `thumb:regen`)
