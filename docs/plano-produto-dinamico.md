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
> `input/`** — não o número histórico. Os 348,2 MB e as 622 geometrias hoje servem só
> como ordem de grandeza do volume de **arquivos** que o `GeometryStore` vai guardar em
> disco; o banco não os vê (ver seção 3).

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
| Reproduzir o www inteiro | São dezenas de rotas. A POC tem quatro telas. |

### O que a POC precisa de fato responder

1. **O catálogo dinâmico funciona?** Dados BIM do produto no MongoDB — buscáveis e
   filtráveis — com a geometria em arquivo referenciada por ponteiro. O pipeline
   consegue gravar arquivo e registro de forma associada, e servir de volta sem
   regredir contra o modelo estático de hoje?
2. **O parse do `.aq` roda no servidor?** Hoje é Python na máquina do dev. Na AWS/k8s
   precisa ser um serviço. Qual runtime, qual modelo de execução.
3. **As miniaturas sobrevivem à mudança?** O passo que hoje usa Playwright + Chromium é
   o mais difícil de levar para um cluster.
4. **A página fica boa lendo do banco?** Comparada com o modelo atual de CDN.
5. **Isso escala?** O que acontece com disco/S3, com o tamanho do banco e com o volume
   lido por página quando forem 200 catálogos em vez de 9. A POC roda com uma
   biblioteca — a resposta é uma **projeção** a partir do que S1.2 medir, não uma
   medição de carga.

Tudo o que não serve a essas cinco perguntas está fora de escopo.

### O caminho estático continua vivo

O pipeline Python → HTML → Vercel **não é substituído**. Fica como **ambiente de amostra
rápida**: gerar o catálogo de uma biblioteca nova e olhar em segundos, sem subir nada.
As duas trilhas convivem no mesmo repo.

---

## 2. Regras invioláveis e protocolo de sessão

### 2.1 O modelo de trabalho: sessões independentes e amnésicas

Este trabalho **não** é uma sessão longa. São **treze sessões curtas e independentes**,
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
decisões que contradizem as anteriores. Treze sessões de escopo estreito, cada uma lendo
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
| **S1.1** | `ce-plan` → `ce-work` → `ce-code-review` | com a arquitetura fechada (ADR-001), resta desenhar schemas e o contrato do `GeometryStore` — sem espaço de brainstorm |
| **S1.2** | `ce-work` → `ce-code-review` | prova a amarração arquivo↔registro do ADR-001 e produz a projeção de escala; um erro no script contamina as duas em silêncio |
| **S2.1 · S2.2** | `ce-plan` → `ce-work` → `ce-code-review` | são dois spikes comparativos — o desenho da fronteira e o do oráculo semântico têm o que planejar |
| **S2.3** | `ce-plan` → `ce-work` → `ce-code-review` | o modelo de execução tem alternativas reais |
| **S2.4** | `ce-plan` → `ce-work` → `ce-code-review` | dois caminhos com custos de produção diferentes — há o que planejar |
| **S3.1 · S3.2 · S3.3** | `ce-work` → `ce-code-review` | os formulários da bilds.com já servem de especificação |
| **S4.1** | `ce-work` | medição comparativa |
| **S4.2** | `ce-compound` | destilar aprendizado é literalmente o propósito da skill |

**`ce-brainstorm` não aparece em nenhuma sessão.** Depois do ADR-001 o escopo está
decidido em toda parte — e rodá-lo sobre trabalho já especificado convida a reabrir
decisões tomadas de propósito, sem que o agente saiba disso.

**`ce-work` para no commit.** Em uso avulso ele assume o "shipping tail" e pode abrir PR.
Aqui trabalhamos direto na `main`, sem PR: commitar, e parar.

#### Como disparar uma sessão

⚠️ **Nunca aponte uma skill do CE para este arquivo sem dizer qual sessão.** Ele descreve
treze sessões; sem escopo, o `ce-work` tenta executar o plano inteiro — exatamente o
super-contexto que a 2.1 existe para evitar. Use esta forma:

```
/ce-work Executar SOMENTE a sessão S0 de docs/plano-produto-dinamico.md.

Antes de qualquer coisa, leia:
  1. CLAUDE.md da raiz
  2. docs/plano-produto-dinamico.md inteiro
  3. docs/sessoes/S-rev-revisao-do-plano.md  (registro da última sessão)

Regras desta linha de trabalho (seção 2 do plano):
  - Não avance para a sessão seguinte, mesmo que sobre tempo.
  - Não edite nada em /home/foltz/bilds.com — é referência somente leitura.
  - Pare no commit: direto na main, sem push automático e sem PR.
  - Ao encerrar, deixe o registro em docs/sessoes/ seguindo o TEMPLATE.md,
    e atualize a tabela de progresso da seção 11.
  - Termine imprimindo, em bloco de código pronto para copiar, o prompt da
    PRÓXIMA sessão da seção 10 — mesma forma deste, com o identificador e a
    skill que a tabela da seção 2.4 manda usar nela.
```

Troque `S0` pelo identificador da sessão da vez, e a skill pelo que a tabela acima manda
usar naquela linha.

**O encadeamento é esse último item, e só ele.** Uma sessão nunca executa a seguinte —
ela deixa o prompt pronto para você abrir uma sessão limpa e colar. É o que mantém a
janela pequena e a amnésia intacta.

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

## 3. A arquitetura de dados — decidida, não a medir

> **Esta seção registra uma decisão fechada pelo dono do projeto em 2026-08-29
> (ADR-001, seção 9). Não é hipótese, não é recomendação, e nenhuma sessão a reabre
> sem uma evidência de inviabilidade.**

### 3.1 Que dado vai para onde

| Dado | Onde mora | Por quê |
|---|---|---|
| **Produtos, specs, curvas Q-H, série, filtros, layout, metadados do catálogo** — tudo o que aparece no modal como dado BIM | **MongoDB** | é sobre isso que se faz busca, filtro e atualização. É a mudança de produto que a POC existe para provar. |
| **Geometria (`pos`/`col`/`idx`) e miniaturas** | **arquivo** — disco local na POC, **S3 na bilds.com** | blob opaco: ninguém consulta, ninguém filtra. O viewer pede um e desenha. Guardar em banco só ocupa. |
| **O vínculo entre os dois** | **ponteiro no documento do produto** | é o que o pipeline precisa gravar para que a busca no banco chegue ao arquivo certo. |

### 3.2 A geometria continua sendo servida pela API

Não vai direto do storage para o browser. É o que a bilds.com já faz hoje, e por um
motivo concreto: `fetch()` exige CORS, e o proxy da API resolve isso. A miniatura é a
exceção — `<img src>` não passa por CORS, então pode ir direto ao CDN em produção.

### 3.3 O storage fica atrás de um driver

Na POC o destino é disco local; na bilds.com é S3. **Isso não é detalhe de
implementação — é a condição para o aprendizado viajar.** No k8s o filesystem do pod é
efêmero e some no restart, e com mais de uma réplica nem compartilhado é; "disco" lá vira
PersistentVolume RWX (EFS) ou S3. Se a POC gravar direto com `fs.writeFileSync` espalhado
pelo código, ela conclui "disco funciona bem" e a conclusão não sobrevive à mudança de
ambiente.

Por isso o acesso ao blob passa por uma interface — `GeometryStore`, com `put`, `get` e
`delete` — que a POC implementa em disco e a bilds.com implementaria em S3. A troca tem
de ser de uma linha.

### 3.4 O que sobrou do teto de 512 MB: nada

Versões anteriores deste plano tratavam os 512 MB do Atlas M0 como "a restrição que molda
o plano inteiro", a partir dos 348,2 MB de geometria medidos em produção. **Com a
geometria fora do banco isso deixa de existir**: o que fica são produtos, specs, curvas e
ponteiros — texto e arrays pequenos, uns poucos MB para as 10 bibliotecas.

Duas coisas morreram junto e não devem ser ressuscitadas por nenhuma sessão: o **codec
binário** da geometria (`Float32`/`Uint8`/`Uint16`, compressão, round-trip) e o **portão
go/no-go de volumetria**. Se aparecer referência a eles em algum lugar do repositório, é
resíduo — corrija.

> Registro do que não se confirmou, para ninguém refazer a conta: a justificativa
> original do binário era o espaço. Ela não se sustentava nem no desenho antigo — o M0
> cobra armazenamento **já comprimido** pelo WiredTiger, e medindo 4 geometrias reais da
> Dancor o JSON comprimido (2,21 MB) sai **menor que o binário cru** (2,93 MB). Os 9
> catálogos dariam ~110–140 MB em JSON comprimido: cabiam. O binário nunca foi requisito.

### 3.5 O cluster

Já criado e validado nesta sessão:

| Item | Valor |
|---|---|
| Host | `bilds-bim-3d.ivrkmbe.mongodb.net` |
| Base | `bilds-bim-3d` |
| Versão | MongoDB **8.0.30** |
| Usuário da aplicação | `bilds-bim-3d` |
| Tier | M0 free — agora folgado, ver 3.4 |
| Acesso de rede | IP desta máquina liberado; conexão testada |

Credenciais em `www/.env` (gitignored, `chmod 600`).

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

**Frontend público — `apps/web/src/components/b-bim-3d/`** (13 arquivos, dos quais 3 são
testes — a superfície de port são 9 arquivos / ~925 linhas): `BimCatalogView`,
**`BimViewer`**, `SeriesRowsLayout`, `CatalogGridLayout`, `LazyBimCard`, `ProductModal`,
`CurveChart`, `bim-viewer-engine.ts`, `types.ts`. O `buildCatalogJsonLd.ts` é SEO e fica
fora da POC. Rota
`apps/web/src/app/[customLink]/[catalogSlug]/page.tsx`.
**Estes são os componentes que mais valem ser aproveitados** — a lógica de viewer,
layouts e curva Q-H é a mesma; só muda de onde vêm os dados.

> **Atenção ao copiar — vale o mesmo aviso do wizard.** Cinco deles importam
> `react-i18next`, que a seção 1 exclui do escopo da POC. Copie a lógica, não o import.
> Levantado arquivo a arquivo em 2026-08-29:
>
> | Componente | Linhas | Dependências externas | A remover |
> |---|---|---|---|
> | `BimCatalogView` | 36 | — | — |
> | `BimViewer` | 154 | react, **react-i18next**, three, OrbitControls | i18n |
> | `SeriesRowsLayout` | 98 | react, **react-i18next** | i18n |
> | `CatalogGridLayout` | 134 | react, **react-i18next** | i18n |
> | `LazyBimCard` | 133 | react | — |
> | `ProductModal` | 77 | **react-i18next** | i18n |
> | `CurveChart` | 123 | **react-i18next** | i18n |
> | `bim-viewer-engine` | 133 | three | — |
> | `types` | 37 | — | — |
>
> Só `three` e o `OrbitControls` são dependências de verdade — precisam entrar no
> `www/apps/web`. Todo o resto é local ou removível.

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

> **Atenção ao copiar.** São 5.269 linhas no wizard, e elas arrastam `@workspace/ui`,
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

### 7.1 · 7.2 Onde mora cada dado — FECHADO

**Decidido em 2026-08-29 pelo dono do projeto. Ver seção 3 e ADR-001.**
Produtos e dados BIM no MongoDB; geometria e miniaturas em arquivo atrás do
`GeometryStore`; ponteiro no documento do produto; a API serve a geometria.

Não há nada a medir nem a escolher aqui. O que resta para S1.1 é **desenhar os schemas e
o contrato do `GeometryStore`**, não comparar formatos.

### 7.3 Onde o parse roda — a questão é portabilidade, não linguagem

**Python nunca foi a objeção.** O critério é: o que a POC construir tem de funcionar na
AWS **como ela é lá**, sem depender de nenhuma liberdade que só uma máquina local tem.
Python containerizado direito passa nesse critério.

Isso desloca a decisão da linguagem para a **fronteira de execução**:

| Formato | Portabilidade | Custo |
|---|---|---|
| **A. Tudo em TypeScript, um processo** | trivial: uma imagem, um runtime | port de ~720 linhas, com dois riscos concretos (ver abaixo) |
| **B. Python como worker separado**, contrato por fila ou HTTP | **formato nativo do k8s** — Deployment de worker ou Job, imagem própria com as próprias deps | reusa ~3.000 linhas testadas, zero risco de port. Preço: dois artefatos de deploy e um contrato |
| **C. Python como subprocesso dentro da imagem Node** | **a armadilha** | mais fácil localmente, pior no pod: uma imagem com dois runtimes. É exatamente a liberdade local que não viaja |

Note que **B é o mesmo formato que a decisão 7.5 já quer para a importação**: o worker de
parse e o worker de importação são a mesma coisa.

**Decidido: provar A e B e comparar.** S2.1 é o spike da fronteira (worker Python isolado)
e S2.2 é o spike do port (uma biblioteca, atravessando o ponto de risco). O ADR registra
o custo real de cada um, em vez de escolher no papel. C não é testado — está aqui só para
ser reconhecido e recusado quando alguém propuser.

#### Os dois riscos concretos do caminho A

Levantados na revisão de 2026-08-29, verificados nos dois runtimes:

1. **`cp1252` não tem equivalente em Node.** O `read_aq.py` usa `con.text_factory`, hook
   de conexão do SQLite que não existe no `better-sqlite3` nem no `node:sqlite`. O port
   precisa de `CAST(col AS BLOB)` em toda coluna de texto e decodificação manual — e o
   `TextDecoder('windows-1252')` **não falha** nos cinco bytes indefinidos
   (0x81, 0x8D, 0x8F, 0x90, 0x9D) onde o Python falha e cai no fallback latin-1.
2. **Comparação textual com o Python é impossível.** Para o mesmo array, Python emite
   `[-0.0,0.0,1e-05,1e+21]` e Node emite `[0,0,0.00001,1e+21]`. Como o `to_buffers` faz
   `-verts[:,1]*scale`, **todo vértice com y=0 — modelo apoiado no plano, o caso comum**
   — produz `-0.0`. O oráculo tem de ser **semântico**: `JSON.parse` dos dois lados e
   igualdade elemento a elemento com `Object.is` tratando `-0` e `0` como iguais.

#### Portabilidade: vale para qualquer formato escolhido

O pipeline atual tem quebras que aparecem em A, B **e** C, e que são critério de aceite de
quem for dono do parse:

- o `.aq` é lido **de um caminho em `input/`**; num pod ele chega como stream de upload
- a saída vai **direto para `output/` no disco**, em vez de passar pelo `GeometryStore`
- a biblioteca inteira é carregada em memória — a Amanco tem 457 geometrias e **ninguém
  mediu o pico**
- o Chromium sobe dentro do processo (endereçado pela S2.4)

### 7.4 Miniaturas no servidor — sessão própria (S2.4)

É a **pergunta 3** das quatro que a POC existe para responder, então não pode ficar na
fila do "se sobrar tempo": ganha sessão dedicada, aberta pelo ADR-001 quando S1.1 perdeu
o codec binário.

Há **dois caminhos viáveis com custos de produção bem diferentes**, e S2.4 mede os dois:

**A — Chromium + SwiftShader**, o que o `thumbs.mjs` já faz. Roda na AWS sem GPU: o
pipeline já usa `--use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader`, que
é WebGL por software. Obstáculos conhecidos no k8s, nenhum impeditivo:

| Obstáculo | Custo |
|---|---|
| Imagem | Playwright + Chromium ≈ 1,5–2 GB — inviável no pod da API, daí o worker separado |
| `/dev/shm` | 64 MB por padrão em container derruba o Chromium: montar `emptyDir{medium:Memory}` em `/dev/shm` ou usar `--disable-dev-shm-usage` |
| Sandbox | `--no-sandbox` em pod isolado, ou seccomp permitindo user namespaces |
| **CPU** | SwiftShader rasteriza na CPU. **É o número que ninguém tem** — e é o que decide worker permanente × Job sob demanda |

**B — rasterizador em TypeScript, sem browser.** A geometria já está em `pos`/`col`/`idx`:
projeção, z-buffer, sombreamento plano, e `sharp` para o WebP. ~250 linhas, imagem
minúscula, milissegundos por peça. O preço é real: a spec exige que **câmera e material
batam com o viewer** (`docs/bilds-bim-3d-zip-spec.md`, seção 4.1), então B reimplementa
esse casamento — e é aí que nasce divergência entre a miniatura e o que o usuário vê ao
abrir o modal.

A miniatura continua **opcional em runtime** — falha de renderização nunca derruba a
importação. O que deixa de ser opcional é **medir**.

### 7.5 Modelo de execução da importação

Um `.aq` com 1.168 peças não processa dentro de um request HTTP. **Recomendação: uma
coleção `bim_imports` como máquina de estados** (`recebido → parseando → gravando →
publicado | falhou`), processada fora do request. Na POC pode ser in-process; o que
importa é que o **estado seja observável**, porque é isso que a tela de acompanhamento
consome e é isso que na AWS vira fila. Fecha em S2.3.

**A transição para `falhou` limpa.** Antes do ADR-001, uma importação abortada no meio
deixava documentos órfãos no Mongo — achaveis com uma query. Agora ela deixa **arquivos
órfãos em disco, que nenhuma query encontra** e que ninguém nota até o disco encher. Por
isso `falhou` é um estado com trabalho: apagar, pelo `GeometryStore`, todo arquivo
gravado sob aquele `importId`, e só então encerrar. O banco e o disco voltam ao estado
anterior ao upload.

**O parse roda em processo filho.** In-process, um `.aq` que estoure memória ou entre em
laço mata o mesmo processo que deveria escrever `falhou` — e o import fica preso em
`parseando` para sempre, com a tela de acompanhamento mentindo. O filho tem teto de
memória e timeout; a API marca `falhou` quando ele morre ou estoura o prazo. É também o
formato que o worker separado da 7.3 exige, então as duas decisões convergem.

#### A máquina de estados, fechada

| Estado | Significa | Transições |
|---|---|---|
| `recebido` | upload aceito, limites validados, `.aq` em disco temporário | → `parseando` |
| `parseando` | lendo o `.aq`, extraindo peças e geometrias | → `gravando` · `falhou` · `vazio` |
| `gravando` | escrevendo arquivos pelo `GeometryStore` e documentos no banco | → `publicado` · `falhou` |
| `publicado` | catálogo consultável pelas rotas de S2.3 | terminal |
| `vazio` | parseou sem erro e não achou **nenhuma** geometria | terminal |
| `falhou` | erro em qualquer ponto; **limpou** arquivos e documentos do `importId` | terminal |

Três casos que a versão anterior não tratava:

- **`vazio` é um estado próprio, não `falhou`.** Um `.aq` só de tubos e kits parseia
  perfeitamente e não rende geometria — é o comportamento correto do pipeline, não erro.
  Sem esse estado, a tela mostra "falhou" para um arquivo que está certo.
- **Upload duplicado.** Subir o mesmo `.aq` sobre um catálogo publicado: ver a pendência
  correspondente na seção 12.
- **Geometria acima do teto do BSON.** Não se aplica mais desde o ADR-001 — a geometria
  vai para arquivo. Fica registrado para ninguém reintroduzir a preocupação.

#### A tela de acompanhamento (S3.2)

A referência de UX do plano (`LibrariesAndFiles.tsx`) cobre upload **síncrono** de ZIP já
processado — **não resolve nada disto**, que é a parte genuinamente nova:

- **um estado visual por valor da máquina** acima, com `vazio` distinto de `falhou`
- **atualização por polling em intervalo fixo** — a POC roda in-process, não há evento a
  assinar; SSE é complexidade que não responde a nenhuma das cinco perguntas
- **em `falhou`, o motivo** (qual limite estourou, em que etapa), não uma mensagem
  genérica; e o botão de subir de novo, já que `falhou` deixou tudo limpo
- **reabrir a página recupera o estado** lendo `bim_imports` — o progresso não vive na
  memória do browser


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
| **ADR-001** | **Onde mora cada dado.** Produtos e dados BIM no MongoDB (é o que se busca); geometria e miniaturas em arquivo atrás do driver `GeometryStore` — disco na POC, S3 na bilds.com; ponteiro no documento do produto; a API serve a geometria para evitar CORS. Rejeitado: geometria em `BinData` no Mongo, e com ela o codec binário e o portão de volumetria. Detalhe na seção 3. | **fechada** — decisão do dono do projeto | S-rev (2026-08-29) |
| **ADR-002** | **Port TS vs worker Python para parsing de `.aq` + OQ3D.** Medido na S2.2 com a Dancor (13 produtos, 10,9 M elementos). Port TS: 658 ms, RSS +422 MB. Worker Python (S2.1): ~39 000 ms, RSS +189 MB. Ganho de latência: **59×**. Custo de memória: **2,2×** (representação intermédia em arrays JS antes de achatar). **Decisão: port TS (Formato A).** Eliminação da dependência de Python e do cold start de 2-5 s superam o aumento de memória, que é gerenciável e otimizável (candidato: substituir `Array<[number,number,number]>` por `Float64Array` na representação interna). Não reabrir sem medição nova. | **fechada** | S2.2 (2026-08-30) |
| **ADR-003** | **Abordagem de geração de miniaturas no servidor.** Medido em S2.4 com 39 produtos Dancor (geometrias reais do Atlas). **Abordagem A — Playwright + Chromium + SwiftShader:** 240 ms/geo, 5,5 KB/WebP, +startup de ~2-5 s, imagem Docker ~1,5 GB, PBR idêntico ao viewer. **Abordagem B — rasterizador TS + ffmpeg:** 65 ms/geo, 4,3 KB/WebP, sem browser, sem startup; sombreamento plano (ambient + 2 luzes direcionais, z-buffer, projeção perspectiva). **Decisão: Abordagem B.** B é 3,7× mais rápido por geometria, imagens menores, sem dependência de Chromium no pod. A diferença visual (flat shading vs. PBR) é aceitável para miniaturas de catálogo. A abordagem A vence em fidelidade, perde em operação. Não reabrir sem mudança no requisito de fidelidade. | **fechada** | S2.4 (2026-08-30) |

---

## 10. As sessões

Treze sessões, a começar pela S-rev, que não escreve código. Cada uma com entregável fechado e verificável, que não obriga a próxima a
carregar o contexto da anterior além deste documento.

### Fase de revisão — antes de escrever qualquer código

| # | Sessão | Entregável | Pronto quando |
|---|---|---|---|
| **S-rev** | Revisão do plano com `ce-doc-review` | emendas a este plano, ADRs que a revisão conseguir fechar, registro em `docs/sessoes/` | o plano incorporou o que a revisão apontou — ou registrou por que não incorporou |

> S-rev não escreve código. O entregável é o próprio plano, melhor.

### Fase 0 — Fundação

| # | Sessão | Entregável | Pronto quando |
|---|---|---|---|
| **S0** | Scaffold da POC | `www/` com workspace pnpm, `apps/api` (NestJS) e `apps/web` (Next.js) mínimos, lendo o `www/.env` que já existe | `GET /health` responde mostrando a versão do Mongo lida do Atlas, **e a página inicial do `apps/web` carrega no navegador** |

### Fase 1 — Modelo de dados

| # | Sessão | Entregável | Pronto quando |
|---|---|---|---|
| **S1.1** | Schemas e contrato do storage | schemas `companies`, `bim_catalogs`, `bim_products` (dados BIM completos + ponteiro), `bim_imports`; interface `GeometryStore` (`put`/`get`/`delete`) com implementação em disco; índices que sustentam a busca por specs | os schemas existem em arquivo commitado, o `GeometryStore` grava e lê um blob de teste, e os índices de busca estão declarados |
| **S1.2** | Carga de prova ponta a ponta | script que ingere **uma** biblioteca real: grava os arquivos pelo `GeometryStore`, cria os documentos com o ponteiro, e mede tempo de escrita, ocupação do banco, ocupação em disco e tempo de leitura de uma geometria **pela API** contra o arquivo estático como baseline. **Mais a projeção da pergunta 5** para 10, 50 e 200 catálogos | toda geometria ingerida é recuperável pelo ponteiro, uma busca por spec devolve os produtos certos, há tabela comparando a leitura via API contra o baseline estático, **e a projeção de escala está registrada** |

> S1.2 deixou de ser portão de volumetria — com a geometria fora do banco não há teto a
> testar. Ela agora prova a **amarração arquivo↔registro**, que é o coração do ADR-001, e
> estabelece o baseline de leitura que S4.1 vai reusar.

### Fase 2 — O núcleo: `.aq` → arquivo + banco

| # | Sessão | Entregável | Pronto quando |
|---|---|---|---|
| **S2.1** | Spike da fronteira (formato B) | o pipeline Python empacotado como **worker isolado**, recebendo o `.aq` como stream e escrevendo pelo `GeometryStore` — do jeito que rodaria como Deployment/Job no k8s, com contrato de fila | uma biblioteca entra pelo contrato do worker e sai como arquivos + documentos, sem o worker tocar em `input/` nem em `output/`; pico de memória medido e registrado |
| **S2.2** | Spike do port (formato A) | port TypeScript de `oq3d.py` + `read_aq.py` para **uma** biblioteca (Dancor), atravessando os dois riscos da 7.3: `CAST AS BLOB` + cp1252 manual, e comparação **semântica** com o Python | a Dancor gera em TS o mesmo catálogo que em Python sob comparação semântica; **o parser rejeita com erro tipado blob truncado, contagem maior que o buffer restante e assinatura ausente, sem alocar buffer proporcional à contagem declarada**; e o ADR registra o custo real do port contra o do worker de S2.1 |
| **S2.3** | Importação server-side **e as rotas de leitura** | `POST` do `.aq` → `bim_imports` → processamento fora do request → arquivos no `GeometryStore` + documentos no banco; decisão 7.4 sobre miniaturas e decisão 7.5 sobre modelo de execução. Mais as três rotas de leitura (contrato abaixo) | subir um `.aq` gera catálogo consultável com status observável do início ao fim, **as três rotas respondem via `curl` com o `ETag` correto**, **os limites de entrada abaixo rejeitam sem gravar nada**, e **subir o mesmo `.aq` uma segunda vez sobre o catálogo publicado deixa registrado o que aconteceu com documentos e arquivos antigos** |
| **S2.4** | Miniaturas no servidor | worker de miniaturas isolado do fluxo de upload, medindo os dois caminhos da 7.4: Chromium+SwiftShader (tempo por geometria, memória, tamanho de imagem) e o rasterizador TS | há números para os dois caminhos e um ADR dizendo qual sai mais barato em produção — ou, se um deles falhar, o registro do fracasso, que também responde à pergunta 3 |

> **Contrato das rotas de leitura (S2.3).** Com o ADR-001, é a API que serve a
> geometria — então estas rotas são o produto, não encanamento:
>
> | Rota | Devolve | Cabeçalhos |
> |---|---|---|
> | `GET /catalogos/:empresa/:slug` | metadados + produtos, com filtro por spec | — |
> | `GET /geometrias/:id` | o blob lido pelo `GeometryStore` | `ETag`, `Cache-Control` longo |
> | `GET /thumbs/:id` | a miniatura (WebP) | `ETag`, `Cache-Control` longo |
>
> S3.3 assume estas rotas prontas e cuida só de adaptar os componentes.

> **Limites de entrada (S2.3).** O `.aq` é um ZIP arbitrário chegando por HTTP e
> extraído para disco antes de virar SQLite. O endpoint rejeita, **com erro tipado e sem
> gravar nada**: arquivo acima de um teto de bytes declarado; ZIP com mais de N entradas
> ou soma descomprimida acima de um teto; entrada cujo nome resolvido saia do diretório
> temporário. São as mesmas classes de defesa que a bilds.com já aplica ao caminho ZIP
> (seção 5), com números menores.

### Fase 3 — A aplicação

| # | Sessão | Entregável | Pronto quando |
|---|---|---|---|
| **S3.1** | Login e empresa | usuário semente, sessão por cookie, criação de empresa com o punhado de campos de `CreateCompany` | dá para entrar e criar uma empresa com nome, URL pública e logo |
| **S3.2** | Upload da biblioteca | tela de upload do `.aq` na empresa + acompanhamento do job, tomando `LibrariesAndFiles.tsx` como referência de UX | o dono da empresa sobe um `.aq` e acompanha até "publicado" |
| **S3.3** | Página pública do catálogo | componentes `b-bim-3d` adaptados para consumir as rotas de S2.3 em vez de `catalogUrl`/`geoBaseUrl`, **com `react-i18next` removido** (tabela na seção 5) | `/{empresa}/{catalogo}` renderiza com viewer 3D lendo geometria pela API, sem nenhum import de i18n |

### Fase 4 — Colher o aprendizado

| # | Sessão | Entregável | Pronto quando |
|---|---|---|---|
| **S4.1** | Medição comparativa | bytes na rede, LCP e tempo até o primeiro card: banco × o modelo atual de CDN | há veredito com números, não com impressão |
| **S4.2** | Documento de aprendizados | as respostas às cinco perguntas da seção 1, o que deu errado, o que a reconstrução deve fazer diferente, **e a seção obrigatória "o que a POC não implementou" destilada da seção 13** | dá para desenhar o módulo definitivo lendo só esse documento, **e nenhuma omissão da POC chega lá sem explicação** |

---

## 11. Progresso

Preenchido ao **encerrar** cada sessão (regra R3). O campo "Registro" é o que a sessão
seguinte lê — e ela lê **só o mais recente**.

| Sessão | Status | Data | Registro | Deixou pendente |
|---|---|---|---|---|
| S-rev | **concluída** | 2026-08-29 | [S-rev](sessoes/S-rev-revisao-do-plano.md) | grant do Atlas (pendência 1); 3 achados recusados pelo dono, ver §5 do registro |
| S0 | **concluída** | 2026-08-29 | [S0](sessoes/S0-scaffold-poc.md) | — |
| S1.1 | **concluída com ressalva** | 2026-08-29 | [S1.1](sessoes/S1.1-schemas-geometry-store.md) | path traversal latente (achado #1 do review — ver registro S1.1 §5) |
| S1.2 | **concluída** | 2026-08-29 | [S1.2](sessoes/S1.2-carga-prova-ponta-a-ponta.md) | endpoint GET /geometrias sem teste HTTP; projeção linear (ver §5 do registro) |
| S2.1 | **concluída** | 2026-08-29 | [S2.1](sessoes/S2.1-spike-fronteira-python-worker.md) | peakMemoryMb=189 MB (RSS delta) / 119 MB heap; elapsedWorker≈39s Dancor |
| S2.2 | **concluída** | 2026-08-30 | [S2.2](sessoes/S2.2-spike-port-typescript.md) | port TS: 658 ms / 422 MB RSS; memória 2.2× maior que Python mas latência 59×; ADR-002 fechado |
| S2.3 | **concluída** | 2026-08-30 | [S2.3](sessoes/S2.3-importacao-server-side.md) | diretórios geo vazios não removidos (inofensivo); endpoint sem auth (finding A1 aberto); sem teste HTTP automatizado |
| S2.4 | **concluída** | 2026-08-30 | [S2.4](sessoes/S2.4-miniaturas-servidor.md) | rasterizador TS (B) escolhido: 65 ms/geo, 4,3 KB/WebP, 3,7× mais rápido que Playwright (A); ADR-003 fechado; GET /thumbs/:productId retorna 200 WebP |
| S3.1 | **concluída** | 2026-08-30 | [S3.1](sessoes/S3.1-login-e-empresa.md) | refresh de token não tratado na UI; auth no POST /importacoes para S3.2 |
| S3.2 | não iniciada | — | — | — |
| S3.3 | não iniciada | — | — | — |
| S4.1 | não iniciada | — | — | — |
| S4.2 | não iniciada | — | — | — |

Status possíveis: `não iniciada` · `em andamento` · `concluída` · `concluída com ressalva`
· `bloqueada`. As três últimas **exigem** registro em `docs/sessoes/`.

---

## 12. Pontos em aberto

Nenhum bloqueia a S0.

1. **Restringir o grant do usuário do Atlas.** Hoje é `readWriteAnyDatabase` — escrita
   em qualquer base do cluster. Como a URI circula por scripts e pelo `.env` de treze
   sessões, um bug de script alcança o cluster inteiro, não só os dados descartáveis da
   POC. Correção: no console do Atlas, Database Access → `bilds-bim-3d` → `readWrite`
   restrito à base `bilds-bim-3d`. **Depende de ação no console, fora do repositório.**
2. **Guardar o `.aq` original (S2.3)?** Permite reprocessar sem novo upload, mas ocupa
   espaço em disco. Provável: guardar só o hash, para deduplicação.
3. **Quantas bibliotecas a POC carrega?** Começar por Dancor (a menor, com curva Q-H,
   exercita o layout `series-rows`).
3. _(resolvido em 2026-08-29: a miniatura ganhou a sessão S2.4 — ver 7.4.)_

---

## 13. O que a POC não implementa — lista viva

Alimentada **por qualquer sessão** que decidir deixar algo de fora, e destilada por S4.2
no documento final. Existe porque a ausência é silenciosa: quem reconstruir na bilds.com
não tem como distinguir "decidimos não fazer aqui" de "não é necessário".

Uma linha por item: o que é, por que ficou de fora, e se é obrigatório na reconstrução.

| Não implementado na POC | Por quê | Na reconstrução |
|---|---|---|
| SuperTokens, sessões, papéis, permissão fina | Já existe e é obrigatório na bilds.com; reproduzir não ensina nada | **obrigatório** |
| Autorização por dono/administrador da empresa (`assertPermission`) | A POC tem um usuário só | **obrigatório** |
| Soft delete (`deletedAt`) em todas as entidades | Convenção da casa, sem valor de aprendizado aqui | **obrigatório** |
| Validação em duas camadas (DTO + schema) | Idem | **obrigatório** |
| i18n, `@workspace/ui`, RTK Query, Swagger | Convenções da casa | **obrigatório** |
| Grant do Atlas restrito por base | Cluster descartável da POC; ver pendência 1 da seção 12 | **obrigatório** |
| Rate limiting no endpoint de upload | Um usuário, sem entrada hostil | **obrigatório** |

_Sessões: acrescentem linhas aqui em vez de deixar a decisão só no registro da sessão._

---
