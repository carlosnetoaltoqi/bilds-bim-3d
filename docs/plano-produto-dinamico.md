# Plano — POC de catálogo BIM com dados dinâmicos

> **Status:** entendimento e quebra em sessões. Nenhuma linha de código escrita ainda.
> **Criado em:** 2026-08-29 · **Reescrito em:** 2026-08-29 após definição do escopo real
> **Documento âncora:** toda sessão desta linha de trabalho começa lendo este arquivo e
> termina atualizando a tabela de progresso (seção 11).

---

## 0. Ponto de partida — leia antes de qualquer coisa

Estado do repositório em 2026-08-29, verificado. Uma sessão nova precisa disto para não
tropeçar:

| Fato | Consequência |
|---|---|
| **`output/` está vazia** — só `output/preview/index.html` (landing da Vercel) | Não há catálogo gerado no disco. S1.2, S2.1 e S2.2 dependem de artefatos do pipeline Python: **é preciso gerar antes**. |
| **`input/` tem 10 arquivos `.aq`** | Dancor (1), Amanco PVC Esgoto (1), Intelbras (7), Maxbar (1). |
| **`templates/vendor/` já tem o Three.js** | Não precisa rodar `setup_vendor.sh` nesta máquina. |
| **Chromium do Playwright instalado** (`playwright 1.62.1`, `~/.cache/ms-playwright`) e libs de sistema presentes via apt | O passo de miniaturas roda. **Ignore o `export LD_LIBRARY_PATH=~/.local/chromium-libs/...` que aparece no `CLAUDE.md`** — esse diretório não existe nesta máquina; as libs vieram do apt. |
| **`www/.env` já existe** com as credenciais do Atlas, `chmod 600` | Não precisa recriar. Está fora do git (`**/.env`) e fora da Vercel (`www/`). |
| **Sem Docker, mongod, mongosh ou mongodump** | Irrelevante: o banco é o Atlas remoto. |
| **O Atlas libera por IP público** | A conexão foi testada em 2026-08-29. Se um dia der `ServerSelectionError`/timeout, o IP desta máquina mudou: liberar de novo em Atlas → Network Access → IP Access List. Não é erro de credencial. |

Para gerar os artefatos do pipeline (leva alguns minutos):

```bash
cd /home/foltz/bilds-bim-3d
python3 scripts/build.py --all          # gera os 10 catálogos: geo/, thumbs/, preview e ZIPs
python3 scripts/build.py --all --force  # refaz mesmo os que já têm ZIP
```

Saída relevante para esta linha de trabalho:

```
output/geo/<origem>/<slug>/*.json      geometria por produto — o insumo de S1.2
output/thumbs/<origem>/<slug>/*.webp   miniaturas
output/<origem>/<slug>-catalog.json    catálogo solto
```

Para conferir o Atlas em dez segundos:

```bash
set -a; . www/.env; set +a
node -e "const {MongoClient}=require('/home/foltz/bilds.com/node_modules/mongodb');(async()=>{const c=new MongoClient(process.env.MONGODB_URI);await c.connect();console.log(await c.db().admin().command({buildInfo:1}).then(b=>b.version));await c.close()})()"
```

> ⚠️ **Cuidado com o número "622 geometrias".** Ele vem da medição de **9 catálogos em
> produção**, feita antes de a Maxbar entrar em `input/`. Regenerar hoje produz **10**
> catálogos e uma contagem diferente. Onde este plano fala em regressão contra o Python
> (S2.1, S2.2), o oráculo é **a saída que o pipeline Python produzir agora a partir de
> `input/`** — não o número histórico. Os 348,2 MB e as 622 geometrias servem só como
> ordem de grandeza para dimensionar o teto de 512 MB.

Leia também o `CLAUDE.md` da raiz: ele governa o repositório inteiro, inclusive a regra
de documentar antes de encerrar a sessão.

> **Antes de tocar em qualquer coisa, leia a seção 2.1.** Ela define como estas sessões
> se comunicam entre si — e este trabalho depende inteiramente disso funcionar. Cada
> sessão é amnésica: só sabe o que está em arquivo commitado.

---

## 1. O que estamos fazendo — e o que explicitamente não estamos

Hoje o `bilds-bim-3d` é um **pipeline local em Python** que lê uma biblioteca `.aq` e
cospe arquivos estáticos: `catalog.json`, um `geo/<peça>.json` por geometria, miniaturas
`thumbs/*.webp` e um HTML de preview. Na bilds.com esses arquivos viram um ZIP que um
administrador da plataforma sobe pelo backoffice, e vão para S3/CloudFront. O browser do
visitante busca os JSONs por HTTP e monta a página.

Vamos construir aqui uma **prova de conceito** de outro modelo:

> Um usuário entra na aplicação, cria uma empresa, sobe um arquivo `.aq`, e daquilo nasce
> uma página de catálogo — com as peças e as geometrias 3D **vindas do banco de dados**,
> não de arquivos estáticos.

### Esta POC é descartável

**Nada daqui será migrado para a bilds.com.** Lá o módulo será **reconstruído do zero**,
com os aprendizados desta POC. Isso muda tudo no que diz respeito a esforço:

| Não fazemos aqui | Por quê |
|---|---|
| SuperTokens, sessões, papéis, permissão fina | Na bilds.com isso já existe e é obrigatório por padrão. Reproduzir aqui não ensina nada. |
| Copiar o schema de `companies` da bilds | Empresa aqui é genérica: o mínimo para ter dono, nome e URL pública. |
| Espelhar `companies`/`profiles` do banco da bilds | O dado real não acrescenta nada à pergunta que a POC responde. |
| i18n, `@workspace/ui`, RTK Query, soft delete rigoroso, Swagger, dupla validação | Convenções da casa. Lá serão obedecidas por padrão; aqui só atrapalham. |
| Reproduzir o www inteiro | São dezenas de rotas. A POC tem três telas. |

### O que a POC precisa de fato responder

1. **Cabe no banco?** Geometria 3D em MongoDB — em que formato, com que custo de espaço
   e de leitura, comparado com arquivo estático em CDN.
2. **O parse do `.aq` roda no servidor?** Hoje é Python na máquina do dev. Na AWS/k8s
   precisa ser um serviço. Qual runtime, qual modelo de execução.
3. **As miniaturas sobrevivem à mudança?** O passo que hoje usa Playwright + Chromium é
   o mais difícil de levar para um cluster.
4. **A página fica boa lendo do banco?** Comparada com o modelo atual de CDN.

Tudo o que não serve a essas quatro perguntas está fora de escopo.

### O caminho estático continua vivo

O pipeline Python → HTML → Vercel **não é substituído**. Fica como **ambiente de amostra
rápida**: gerar o catálogo de uma biblioteca nova e olhar em segundos, sem subir nada.
As duas trilhas convivem no mesmo repo.

---

## 2. Regras invioláveis e protocolo de sessão

### 2.1 O modelo de trabalho: sessões independentes e amnésicas

Este trabalho **não** é uma sessão longa. São **onze sessões curtas e independentes**,
cada uma com uma janela de contexto pequena, ligadas **exclusivamente pela documentação
versionada no repositório**.

> **A sessão que vem depois desta não lembra de nada.** Não tem o contexto desta
> conversa, não tem memória de agente, não tem o histórico do terminal, não sabe o que
> foi decidido "há pouco". Ela sabe **apenas o que está escrito em arquivos commitados**.

Disso saem três regras absolutas:

**R1 — Ao iniciar, leia; não lembre.** A sessão começa lendo, nesta ordem:

1. `CLAUDE.md` da raiz — governa o repositório inteiro
2. **este plano, inteiro**
3. o registro da **última sessão concluída** em `docs/sessoes/` (só o último — não a pilha toda)
4. os ADRs já fechados (seção 9)

É proibido tratar como fonte de verdade: memória de agente, `~/.claude`, histórico de
sessões anteriores da máquina, "eu me lembro que", ou qualquer coisa fora do repositório.
Se a informação não está num arquivo commitado, **ela não existe**.

**R2 — Confirme o estado; não confie no que está escrito.** Documentação envelhece. Antes
de agir, verifique no disco e no banco o que o documento afirma — pasta existe mesmo?
coleção tem os documentos que o registro diz? o comando ainda roda?

> Isto não é zelo teórico. Ao auditar este plano em 2026-08-29 apareceram **três desvios
> reais**: o `CLAUDE.md` dizia que o `output/` estava limpo quando as deleções nunca
> tinham sido commitadas; mandava exportar um `LD_LIBRARY_PATH` apontando para um
> diretório inexistente; e um critério de aceite citava "622 geometrias" quando o
> `input/` já tinha uma biblioteca a mais. Documento é ponto de partida, não prova.

**R3 — Ao encerrar, persista tudo.** Uma sessão só termina quando o próximo agente
consegue continuar sem perguntar nada a ninguém. Antes de encerrar, obrigatoriamente:

1. Código implementado **e commitado**
2. **Registro da sessão** criado em `docs/sessoes/S<id>-<slug>.md`, seguindo
   `docs/sessoes/TEMPLATE.md`
3. **ADRs** da seção 9 preenchidos, se alguma decisão de arquitetura foi tomada
4. **Tabela de progresso** (seção 11) atualizada, com o link para o registro
5. Se o plano se mostrou errado em algo, **corrija o plano** — ele é vivo
6. Se aprendeu algo sobre `.aq`, IFC ou páginas de catálogo, atualize também a skill
   correspondente em `docs/skills/`, como manda o `CLAUDE.md`

**Sessão sem registro é sessão perdida.** O trabalho pode até estar no disco, mas o
próximo agente não vai saber por que ele está lá, nem o que ficou pela metade.

### 2.2 Por que assim

O objetivo é **contexto pequeno e trabalho atômico e incremental**. Uma janela grande
carregando o repositório inteiro degrada: o agente perde precisão, mistura camadas e toma
decisões que contradizem as anteriores. Onze sessões de escopo estreito, cada uma lendo
um plano estável e o registro da anterior, produzem trabalho mais previsível — e deixam
um rastro auditável que é, ele próprio, o entregável da POC: é isso que a reconstrução na
bilds.com vai consumir.

Por isso o custo de leitura é **limitado de propósito**: o plano é estável (muda pouco),
os registros de sessão ficam em arquivos separados, e cada sessão lê **só o último**.
A pilha cresce sem que o custo de entrada cresça junto.

### 2.3 Regras de escopo

1. **Não editar nada em `/home/foltz/bilds.com`.** Somente leitura — é referência de
   arquitetura e fonte dos formulários. Toda implementação acontece em `bilds-bim-3d`.
2. **A POC não vai para a Vercel.** A Vercel serve `output/preview/` e só. `www/` está
   no `.vercelignore`.
3. **Uma sessão = um passo da seção 10.** Sem emendar passos para "adiantar". Se sobrar
   tempo, use para verificar e documentar melhor — não para invadir a sessão seguinte.
   Se um passo não couber, **divida-o** e registre a divisão no plano.
4. **Credenciais só em `.env` gitignored.** Nunca no git, nunca neste documento.
5. **Toda decisão de arquitetura vira ADR na seção 9** antes de virar código.
6. **Simples por padrão.** Numa POC descartável, a solução mais direta que responde à
   pergunta vence a mais correta. Quando a diferença importar, registre o porquê no ADR —
   é justamente esse registro que a reconstrução na bilds.com vai consumir.

### 2.4 Compound engineering — qual skill entra em cada sessão

O pipeline do `compound-engineering` é usado **por sessão, nunca sobre o plano inteiro**.
Rodar brainstorm + plan + work + review de uma vez reconstrói exatamente o super-contexto
que a seção 2.1 existe para evitar.

| Sessão | Skills | Por quê |
|---|---|---|
| **S-rev** | `ce-doc-review` | revisar este plano com lentes de papéis |
| **S0** | `ce-work` → `ce-code-review` | scaffold é mecânico; não há o que planejar |
| **S1.1** | **ciclo completo** — `ce-brainstorm` → `ce-plan` → `ce-work` → `ce-code-review` | único ponto com espaço de design real e consequência dura (512 MB): precisão, cor, índices, compressão |
| **S1.2** | `ce-work` | é medição: o script ou mede, ou não mede |
| **S2.1 · S2.2** | `ce-work` → `ce-code-review` | o critério é "saída idêntica ao Python". Não há o que brainstormar |
| **S2.3** | `ce-plan` → `ce-work` → `ce-code-review` | o modelo de execução tem alternativas reais |
| **S3.1 · S3.2 · S3.3** | `ce-work` → `ce-code-review` | os formulários da bilds.com já servem de especificação |
| **S4.1** | `ce-work` | medição comparativa |
| **S4.2** | `ce-compound` | destilar aprendizado é literalmente o propósito da skill |

**`ce-brainstorm` só aparece em S1.1.** Nas demais o escopo já está decidido — e rodá-lo
sobre trabalho já especificado convida a reabrir decisões que foram tomadas de propósito,
sem que o agente saiba disso.

**`ce-work` para no commit.** Em uso avulso ele assume o "shipping tail" e pode abrir PR.
Aqui trabalhamos direto na `main`, sem PR: commitar, e parar.

#### Autoridade documental

O compound-engineering grava artefatos próprios (`spec.md`, `acceptance.md`,
`review-*.md`), tipicamente em `.claude/sessions/<slug>/`. Sem uma regra, o projeto
termina com dois sistemas paralelos de documentação — e é assim que nasce o desvio que a
R2 tenta pegar.

1. **`docs/plano-produto-dinamico.md` é autoridade única.** Em qualquer divergência, o
   plano vence — ou o plano é corrigido. Nunca "os dois valem".
2. **Artefatos do CE são insumo de trabalho, não documentação do projeto.** O que
   sobrevive deles é **destilado** no registro da sessão (`docs/sessoes/`) e nos ADRs.
3. **Se o CE gravar em `.claude/`, esse diretório é commitado.** Artefato não commitado
   viola a R1 — para a próxima sessão, ele não existe. (Precedente: na bilds.com
   `.claude/sessions/` é rastreado no git.)

---

## 3. O banco — Atlas, e o teto que ele impõe

Cluster já criado e **validado nesta sessão**:

| Item | Valor |
|---|---|
| Host | `bilds-bim-3d.ivrkmbe.mongodb.net` |
| Base | `bilds-bim-3d` |
| Coleção existente | `catalog` (vazia) |
| Versão | MongoDB **8.0.30** |
| Usuário da aplicação | `bilds-bim-3d` — `readWriteAnyDatabase` |
| Tier | **M0 free** |
| Acesso de rede | IP desta máquina já liberado — conexão testada e funcionando |

Credenciais já estão em `www/.env` (gitignored, `chmod 600`) — criado em 2026-08-29.

### ⚠️ A restrição que molda o plano inteiro: 512 MB

O tier **M0 gratuito tem teto de 512 MB de armazenamento**. Contra isso, a volumetria
real medida nos 9 catálogos em produção:

| Métrica | Valor |
|---|---|
| Geometrias | 622 |
| **Geometria total, como JSON** | **348,2 MB** — média ~560 KB por geometria |
| Miniaturas (WebP 448×324) | 2,5 MB — média ~4 KB cada |

Ou seja: **os 9 catálogos em JSON consomem 68% do cluster inteiro** — e isso ignorando
índices e overhead do BSON. Três consequências diretas:

1. **Codificar a geometria em binário deixa de ser otimização e vira requisito.** Em
   JSON um float custa ~12 bytes; em `Float32` custa 4.
2. **A POC começa com uma ou duas bibliotecas, não com nove.** Só depois de medir é que
   se sabe quantas cabem.
3. **A medição vira portão, não etapa.** A sessão **S1.2** é go/no-go: se nem uma
   biblioteca couber com folga, a decisão de armazenamento muda antes de existir API.

---

## 4. O que existe hoje — o produtor

```
scripts/read_aq.py    405 linhas   .aq (ZIP→SQLite ou SQLite direto, cp1252) → JSON
scripts/oq3d.py       317 linhas   BLOB SIMBOLOGIA_3D → malha (cm, Z-up, cor uniforme)
scripts/build.py    1.552 linhas   orquestra: catálogo, geo/, thumbs, preview, ZIP
scripts/thumbs.mjs    ~120 linhas  Playwright + Chromium + Three.js → WebP 448×324
scripts/parse_ifc.py  572 linhas   caminho alternativo --ifc (só quando falta peça no .aq)
templates/            Jinja2 + Three.js self-hosted (CDN é bloqueado por CSP)
```

Contrato completo em `docs/bilds-bim-3d-zip-spec.md`.

**Formato da geometria** — arrays flat prontos para `THREE.BufferGeometry`:

```json
{ "pos": [x,y,z, ...], "col": [r,g,b, ...], "idx": [i0,i1,i2, ...] }
```

`pos` em metros, Y-up. Conversão a partir do OQ3D: `x, y=z, z=-y`, tudo × 0,01 — o OQ3D
grava em **centímetros**, e esquecer o fator é o erro mais fácil de cometer.

Bibliotecas em `input/`: **10 arquivos `.aq`** — Dancor (1), Amanco PVC Esgoto (1),
Intelbras (7), Maxbar (1).

---

## 5. O que existe hoje — o consumidor na bilds.com (referência)

Serve como **referência de forma**, não como código a copiar.

**Backend — `apps/api/src/b-bim-3d/`** (NestJS): a coleção `bim_catalogs` guarda **só
metadados e URLs** (`companyId`, `companyCustomLink`, `slug`, `title`, `manufacturer`,
`layout`, `filters`, `productCount`, `catalogUrl`, `geoBaseUrl`, `thumbBaseUrl`). Nenhum
dado de produto entra no Mongo — é exatamente isso que a POC inverte. O serviço recebe o
ZIP, valida (zip bomb, path traversal, 10 MB/geo, 2 MB/thumb) e grava em S3 ou disco.

**Frontend público — `apps/web/src/components/b-bim-3d/`** (13 arquivos):
`BimCatalogView`, `SeriesRowsLayout`, `CatalogGridLayout`, `LazyBimCard`, `ProductModal`,
`CurveChart`, `bim-viewer-engine.ts`, `types.ts`. Rota
`apps/web/src/app/[customLink]/[catalogSlug]/page.tsx`.
**Estes são os componentes que mais valem ser aproveitados** — a lógica de viewer,
layouts e curva Q-H é a mesma; só muda de onde vêm os dados.

**Upload hoje:** `apps/admin/src/app/b-bim-3d/[companyId]/novo/page.tsx` — backoffice,
admin da plataforma, aceita `.zip`. A POC inverte para: **www, dono da empresa, `.aq`**.

### Formulários a usar como referência

Caminhos exatos, para a sessão que precisar deles não ter de procurar:

| O quê | Onde |
|---|---|
| Wizard de criação de empresa | `apps/web/src/containers/Company/CreateCompany/CreateCompany.tsx` (1.256 linhas) |
| Passos do wizard | `.../CreateCompany/steps/` — `CompanieInfo` (915), `ContactInfo` (518), `PageCustomization` (664), `LibrariesAndFiles` (1.445), `CertificationsAndAssociations` (471) |
| **Upload de biblioteca** | `.../CreateCompany/steps/LibrariesAndFiles.tsx` — é o mais próximo do que a POC precisa |
| Seção BIM na página da empresa | `apps/web/src/containers/Company/sections/CompanyBimSection.tsx` (421) |
| Edição da empresa | `apps/web/src/containers/Company/EditCompany/EditCompany.tsx` |

> **Atenção ao copiar.** São 5.690 linhas no wizard, e elas arrastam `@workspace/ui`,
> i18next, Redux, drawer, modais de descarte e rascunho automático. Copiar literalmente
> traz o monorepo inteiro junto. **A POC copia o conjunto de campos e o fluxo**, com UI
> mínima — e usa o original como especificação do que perguntar ao usuário.

Campos do cadastro no original (`name`, `companyType`, `country`, `city`, `area`,
`productSegments`, `enterpriseTypes`, `foundationYear`, `employeesQuantity`, `tools`,
`coAdmins`, `administrator`, `businessPhone`, `businessEmail`, `website`, `linkedin`,
`facebook`, `instagram`, `customUrl`, `companyLogo`, `coverImage`,
`institutionalSummary`, `about`). **A POC usa um punhado deles** — o que S3.1 decidir,
provavelmente `name`, `customUrl`, `companyLogo` e o administrador.

---

## 6. O ambiente alvo — o que a POC precisa ter em mente

Não para reproduzir agora, mas porque a POC não pode chegar a uma conclusão que não
sobreviva lá:

| Camada | bilds.com |
|---|---|
| Monorepo | pnpm workspaces + Turbo, `pnpm@10.28.1`, Node >= 22 |
| Backend | NestJS + Mongoose, camadas `controllers/services/repositories/schemas/dtos` |
| Frontend | Next.js App Router + RTK Query, react-hook-form + Zod |
| Banco | MongoDB, `_id` string UUID v4, `deletedAt` para soft delete |
| Storage | S3 + CloudFront |
| 3D | `three` como dependência direta de `apps/web` |
| **Infra** | **Kubernetes na AWS** |

O item que realmente restringe é o último: **o que roda na POC tem de ser plausível num
pod**. Um passo que só funciona porque existe um `python3` no PATH do dev, ou porque há
um `.aq` no disco local, não sobrevive à mudança — e descobrir isso agora é parte do
valor da POC.

Ambiente local (levantado em 2026-08-29): Node v24.18.0 (nvm, também v20.20.2), pnpm
10.28.1, Python 3.12.3. **Sem Docker, sem mongod, sem mongosh, sem mongodump.** Como o
banco é o Atlas remoto, nada disso faz falta.

---

## 7. Decisões a tomar

Cada uma vira ADR na seção 9 quando fechada.

### 7.1 Como a geometria é gravada — a decisão central

| Opção | A favor | Contra |
|---|---|---|
| **A.** JSON como está, num documento | trivial | ~560 KB por geometria: **9 catálogos = 348 MB de um teto de 512 MB** |
| **B.** Binário (`Float32Array` + índices) em `BinData`, coleção própria | ~3–4× menor que JSON de texto; um doc por geometria, longe do teto de 16 MB | precisa de encoder/decoder dos dois lados |
| **C.** GridFS | feito para blob grande | complexidade sem ganho — as geometrias cabem num documento |
| **D.** Continuar em object storage | é o que já escala hoje | contraria a pergunta que a POC existe para responder |

**Recomendação: B.** Não por elegância — por caber. Fecha em **S1.1**, com o número
medido em **S1.2**.

Subdecisões de B, todas para S1.1: `Float32` basta para as posições (precisão de ~7
dígitos em peça de 0,01–5 m) ou precisa `Float64`? Cor como `Uint8` (3 bytes/vértice em
vez de 12)? Índices em `Uint16` quando cabem? Comprimir por cima, ou o ganho não paga a
CPU na leitura?

### 7.2 Onde moram as miniaturas

~4 KB cada, 2,5 MB nos 9 catálogos. **Recomendação: `BinData` no Mongo**, coleção
própria, servidas por rota com `Cache-Control` longo e `ETag`. Nesse tamanho não há o que
discutir. Fecha em S1.1.

### 7.3 Em que runtime o `.aq` é parseado

Esta é a pergunta nº 2 da POC, então merece resposta real e não atalho.

| Opção | Nota |
|---|---|
| **Portar `read_aq.py` + `oq3d.py` para TypeScript** | `oq3d.py` são 317 linhas de parsing binário puro, muito portável; `read_aq.py` são consultas SQLite (`better-sqlite3` ou `node:sqlite`). Resultado: um serviço Node só, imagem enxuta, sem Python no pod |
| Manter Python como worker separado | preserva código testado, mas são duas stacks, duas imagens e um contrato entre elas |

**Recomendação: portar para TypeScript**, com o **Python como oráculo de regressão** — o
port só é aceito quando produz saída idêntica à do Python em toda a saída gerada a partir
de `input/` (ver seção 0 sobre o número 622).
O pipeline Python continua no repo servindo a trilha Vercel.

> Vale notar a tensão: a POC é descartável, mas o port não é trabalho jogado fora — ele
> **é** a resposta à pergunta nº 2, e o que a reconstrução na bilds.com vai reaproveitar
> como conhecimento. Sessões **S2.1** e **S2.2**.

### 7.4 Miniaturas no servidor

Playwright + Chromium é o passo mais difícil de levar para k8s: imagem grande, memória,
`--no-sandbox`. **Recomendação preliminar: manter a miniatura opcional** — o catálogo já
sabe funcionar sem ela, caindo no render no browser. Assim uma falha de Chromium nunca
derruba a importação. Se couber no tempo, testar como passo separado do fluxo de upload.
Fecha em **S2.3**.

### 7.5 Modelo de execução da importação

Um `.aq` com 1.168 peças não processa dentro de um request HTTP. **Recomendação: uma
coleção `bim_imports` como máquina de estados** (`recebido → parseando → gravando →
publicado | falhou`), processada fora do request. Na POC pode ser in-process; o que
importa é que o **estado seja observável**, porque é isso que a tela de acompanhamento
consome e é isso que na AWS vira fila. Fecha em S2.3.

### 7.6 Autenticação

**Recomendação: o mínimo que existe.** Usuário semente com as mesmas credenciais do
banco, sessão por cookie assinado, um único usuário. Sem cadastro, sem recuperação de
senha, sem papéis. A empresa tem um `ownerId` e o dono faz tudo. Fecha em S3.1.

---

## 8. Estrutura proposta no repositório

```
bilds-bim-3d/
├── scripts/ templates/ output/     ← pipeline Python (trilha Vercel) — INTOCADO
├── docs/
│   ├── plano-produto-dinamico.md   ← este arquivo: plano estável, muda pouco
│   └── sessoes/                    ← um registro por sessão (regra R3)
│       ├── TEMPLATE.md             ← copie ao encerrar
│       └── S<id>-<slug>.md
└── www/                            ← A POC — fora do deploy Vercel
    ├── .env                        ← credenciais do Atlas (gitignored)
    ├── package.json                ← workspace pnpm
    ├── apps/
    │   ├── api/                    ← NestJS: empresas, importação, catálogo, geometria
    │   └── web/                    ← Next.js: login, empresa, upload, catálogo público
    └── tools/                      ← scripts de carga e medição
```

---

## 9. Registro de decisões (ADR)

| # | Decisão | Status | Sessão |
|---|---|---|---|
| — | — | _nenhuma fechada ainda_ | — |

---

## 10. As sessões

Onze sessões. Cada uma com entregável fechado e verificável, que não obriga a próxima a
carregar o contexto da anterior além deste documento.

### Fase de revisão — antes de escrever qualquer código

| # | Sessão | Entregável | Pronto quando |
|---|---|---|---|
| **S-rev** | Revisão do plano com `ce-doc-review` | emendas a este plano, ADRs que a revisão conseguir fechar, registro em `docs/sessoes/` | o plano incorporou o que a revisão apontou — ou registrou por que não incorporou |

> S-rev não escreve código. O entregável é o próprio plano, melhor.

### Fase 0 — Fundação

| # | Sessão | Entregável | Pronto quando |
|---|---|---|---|
| **S0** | Scaffold da POC | `www/` com workspace pnpm, `apps/api` (NestJS) e `apps/web` (Next.js) mínimos, lendo o `www/.env` que já existe | `GET /health` responde e mostra a versão do Mongo lida do Atlas |

### Fase 1 — Modelo de dados e o portão de volumetria

| # | Sessão | Entregável | Pronto quando |
|---|---|---|---|
| **S1.1** | Desenho do schema | ADR fechando 7.1 e 7.2 + schemas: `companies`, `bim_catalogs`, `bim_products`, `bim_geometries`, `bim_thumbnails`, `bim_imports`; codec binário da geometria especificado | o ADR responde precisão, cor, índices e compressão com justificativa |
| **S1.2** | **Portão de volumetria** | script que ingere **uma** biblioteca real medindo JSON × binário × binário comprimido: bytes no banco, tempo de escrita, tempo de leitura de uma geometria | há tabela com números reais e uma projeção de **quantas bibliotecas cabem em 512 MB** |

> S1.2 é go/no-go. Se a projeção não fechar, a decisão 7.1 é revista **antes** de existir
> qualquer API. Medir é barato agora e caríssimo depois.

### Fase 2 — O núcleo: `.aq` → banco

| # | Sessão | Entregável | Pronto quando |
|---|---|---|---|
| **S2.1** | Port do OQ3D para TS | parser TypeScript do formato binário + suíte de regressão contra o Python | saída idêntica à do Python em **todas as geometrias que `build.py --all` produzir a partir de `input/`** (ver seção 0) |
| **S2.2** | Port do leitor `.aq` para TS | SQLite, cp1252, peças, specs, curvas Q-H, vínculo peça→geometria | catálogo gerado em TS == catálogo gerado em Python, nos 10 `.aq` de `input/` |
| **S2.3** | Importação server-side | `POST` do `.aq` → `bim_imports` → processamento fora do request → catálogo no banco; decisão 7.4 sobre miniaturas | subir um `.aq` gera catálogo consultável, com status observável do início ao fim |

### Fase 3 — A aplicação

| # | Sessão | Entregável | Pronto quando |
|---|---|---|---|
| **S3.1** | Login e empresa | usuário semente, sessão por cookie, criação de empresa com o punhado de campos de `CreateCompany` | dá para entrar e criar uma empresa com nome, URL pública e logo |
| **S3.2** | Upload da biblioteca | tela de upload do `.aq` na empresa + acompanhamento do job, tomando `LibrariesAndFiles.tsx` como referência de UX | o dono da empresa sobe um `.aq` e acompanha até "publicado" |
| **S3.3** | Página pública do catálogo | componentes `b-bim-3d` adaptados para consumir a API/banco em vez de `catalogUrl`/`geoBaseUrl` | `/{empresa}/{catalogo}` renderiza com viewer 3D lendo do banco |

### Fase 4 — Colher o aprendizado

| # | Sessão | Entregável | Pronto quando |
|---|---|---|---|
| **S4.1** | Medição comparativa | bytes na rede, LCP e tempo até o primeiro card: banco × o modelo atual de CDN | há veredito com números, não com impressão |
| **S4.2** | Documento de aprendizados | as respostas às quatro perguntas da seção 1, o que deu errado, e o que a reconstrução na bilds.com deve fazer diferente | dá para desenhar o módulo definitivo lendo só esse documento |

---

## 11. Progresso

Preenchido ao **encerrar** cada sessão (regra R3). O campo "Registro" é o que a sessão
seguinte lê — e ela lê **só o mais recente**.

| Sessão | Status | Data | Registro | Deixou pendente |
|---|---|---|---|---|
| S-rev | não iniciada | — | — | — |
| S0 | não iniciada | — | — | — |
| S1.1 | não iniciada | — | — | — |
| S1.2 | não iniciada | — | — | — |
| S2.1 | não iniciada | — | — | — |
| S2.2 | não iniciada | — | — | — |
| S2.3 | não iniciada | — | — | — |
| S3.1 | não iniciada | — | — | — |
| S3.2 | não iniciada | — | — | — |
| S3.3 | não iniciada | — | — | — |
| S4.1 | não iniciada | — | — | — |
| S4.2 | não iniciada | — | — | — |

Status possíveis: `não iniciada` · `em andamento` · `concluída` · `concluída com ressalva`
· `bloqueada`. As três últimas **exigem** registro em `docs/sessoes/`.

---

## 12. Pontos em aberto

Nenhum bloqueia a S0.

1. **Guardar o `.aq` original (S2.3)?** Permite reprocessar sem novo upload, mas ocupa
   espaço num cluster de 512 MB. Provável: guardar só o hash, para deduplicação.
2. **Quantas bibliotecas a POC carrega?** Depende de S1.2. Começar por Dancor (a menor,
   com curva Q-H, exercita o layout `series-rows`).
3. **Miniatura entra na POC ou fica de fora (7.4)?** Decidir em S2.3, à luz do tempo.
