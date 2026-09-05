# Pipeline estático — fluxo, `config.json`, `catalog.json`, layouts, ZIP, miniaturas, matching IFC

> Movido do `CLAUDE.md` em 2026-09-04 (S7.8, item I22 da auditoria). O conteúdo é o que estava lá,
> com as afirmações desatualizadas de I23 corrigidas no lugar; onde diz "este arquivo", "acima" ou
> "no histórico", leia-se o `CLAUDE.md` antigo — o histórico está em `docs/sessoes/`. **Manter aqui**
> a partir de agora: o `CLAUDE.md` só aponta para este arquivo.

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

### Um só modo

A geometria vem sempre do próprio `.aq` (OQ3D). O modo de compatibilidade `build.py --ifc`
— geometria dos `.IFC` da pasta, `file_map` e matching por nome (`find_aq_product`) — foi
**removido em 2026-09-05** (I6 da auditoria, decisão do usuário): ~440 linhas sem fixture nem
teste, para dois casos que nunca mais ocorreram (peça só em IFC, como a bomba 89-62 TJM da
Dancor; conferir uma fonte contra a outra). O matcher sobrevive em
`docs/estudo-oq3d/valida_ifc.py`, que é o estudo que o usa. Peça que existe só como IFC entra
pela POC (`www/apps/ingestao/pipeline/ifc_to_geo.py`) ou é cadastrada no `.aq`.

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
fabricante e título são resetados — nunca herdam do catálogo anterior.

## config.json — schema completo

```json
{
  "slug":        "bombas-de-combate-a-incendio",
  "titulo":      "Bombas de Combate a Incêndio",
  "fabricante":  "Dancor",
  "descricao":   "Linha CAM-W e TJM para sistemas de combate a incêndio.",
  "layout":      "series-rows",
  "aq_file":     "input/Dancor/pecas_dancor_bombas_incendio_2026_04.1.aq"
}
```

Seis chaves, todas inferíveis do `.aq` e da pasta (`config.example.json` é este exemplo). As
chaves `ifc_dir`, `file_map` e `products_override` saíram com o modo `--ifc` (I6, 2026-09-05);
um `config.json` antigo que ainda as tenha é ignorado nesses campos.

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

**Jinja2 é obrigatório** (desde 2026-09-04, S7.7, I7): sem ele `build_preview()` lança
`RuntimeError` antes de copiar qualquer coisa, e `run_build` para — não sai ZIP sem preview.
O antigo "fallback" só trocava `{{ catalog | tojson | safe }}` por texto e entregava um
`index.html` com `{% for %}` cru e nenhum card. Template inexistente também lança, listando
os disponíveis; antes devolvia `False` e `run_build` ignorava.

## ZIP para bilds.com — conteúdo

O arquivo é gerado em `output/<origem>/<slug>-AAAAMMDDHHMM.zip` (ex: `dancor-bombas-incendio-202608241530.zip`).

```
<slug>-AAAAMMDDHHMM.zip
├── manifest.json    { slug, title, manufacturer, description, layout, filters, productCount, thumbCount }
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
build.py  →  build_thumbs()  →  node www/apps/ingestao/pipeline/thumbs.mjs <config.json>
                                    ├── sobe servidor estático sobre ROOT
                                    ├── abre www/apps/ingestao/pipeline/harness.html no Chromium
                                    └── window.renderThumb(url) por geometria → .webp
```

`harness.html` carrega o **mesmo Three.js** de `templates/vendor/` e tem cópia literal do
`buildScene()` e da câmera dos layouts. É o que garante que a miniatura pré-gerada seja a
imagem que a página produziria.

**O harness tem dois consumidores** desde a S4.4:

| Consumidor | Função do harness | Origem dos dados |
|---|---|---|
| `www/apps/ingestao/pipeline/thumbs.mjs` (pipeline estático) | `window.renderThumb(url, …)` | `fetch` do JSON servido |
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

**Sem isso o build QUEBRA — desde 2026-09-03 (S7.6, I1).** `build_thumbs()` lança
`ThumbsError` quando não há Node >= 20, Playwright ou Chromium, quando o render estoura
30 min ou quando **qualquer** geometria falha no render; `run_build` imprime `ERRO:
miniaturas — …` e o processo sai com código 1 (no lote, a biblioteca entra em `falhas`).
Antes era um `AVISO` com exit 0, e o ZIP sem `thumbs/` subia para o bilds.com — o cenário
dos 39,9 s de LCP. Duas saídas explícitas:

| Flag | O que faz |
|---|---|
| `--allow-no-thumbs` | tenta; se falhar, avisa e segue (produtos sem `thumb` usam render dinâmico) |
| `--skip-thumbs` | nem tenta |

Nos dois casos o `manifest.json` do ZIP sai com `thumbCount` (novo campo) menor que
`productCount`, para quem consome o ZIP ver que as miniaturas faltam. Testes:
`tests/test_build.py::test_run_build_*`.

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

## Matching IFC → .aq — histórico

`find_aq_product` (cobertura de tokens do caminho do IFC contra `GRUPO_PECA`, fallback por
prefixo/número) saiu do `build.py` em 2026-09-05 com o modo `--ifc` (I6). A implementação e a
explicação vivem em `docs/estudo-oq3d/valida_ifc.py`, o único consumidor que restou; a skill
`leitor-biblioteca-aq` mantém o resumo do algoritmo como histórico.

## Integração com bilds.com — em produção desde 2026-08-28 (PR #1244)

> **Atualização (I23, 2026-09-04):** este texto foi escrito quando a integração era plano. A API da
> bilds.com consome o ZIP **em produção desde o PR #1244 (2026-08-28)**, inclusive a pasta `thumbs/`.
> Vale como descrição da intenção; o contrato formal é `docs/bilds-bim-3d-zip-spec.md`.

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
