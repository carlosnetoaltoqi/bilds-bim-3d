# Formato do pacote ZIP — manifest, catálogo, geometria, miniaturas

Formato genérico de um pacote de catálogo BIM: um `.zip` com dois JSONs de metadados e duas
pastas de arquivo por produto (geometria e, opcionalmente, miniatura). Este documento descreve a
**forma do arquivo**, sem depender de quem o consome — o lado que recebe esse ZIP por upload HTTP
está em `docs/integracoes/bilds-com.md`.

## 1. Estrutura

```
pacote.zip
├── manifest.json     ← obrigatório, na raiz
├── catalog.json      ← obrigatório, na raiz
├── geo/
│   ├── produto-a.json   ← um arquivo por GEOMETRIA (não por produto — ver "geometria compartilhada")
│   └── produto-b.json
└── thumbs/            ← opcional
    ├── produto-a.webp  ← miniatura pré-renderizada da geometria correspondente
    └── produto-b.webp
```

Regras gerais:

- `manifest.json` e `catalog.json` ficam na **raiz** do ZIP, nunca em subpasta.
- Arquivos de geometria ficam exatamente em `geo/<nome>.json` — um nível de profundidade, nada
  mais fundo.
- Miniaturas, quando existirem, ficam em `thumbs/<nome>.webp`, no mesmo nível único.
- Todo arquivo referenciado por um produto precisa existir dentro do ZIP; todo arquivo dentro de
  `geo/`/`thumbs/` precisa ser referenciado por pelo menos um produto (sem órfãos).

## 2. `manifest.json` — metadados para registro

Campos **em inglês** por convenção (é o formato de registro, lido antes de processar o pacote
inteiro):

```json
{
  "slug":         "linha-principal",
  "title":        "Linha Principal de Equipamentos",
  "manufacturer": "Fabricante Exemplo",
  "description":  "Descrição geral do catálogo.",
  "layout":       "series-rows",
  "filters":      ["Serie-A", "Serie-B"],
  "productCount": 3,
  "thumbCount":   3
}
```

| Campo | Tipo | Obrigatório | Observação |
|---|---|---|---|
| `slug` | string | sim | identificador único; ver regras abaixo |
| `title` | string | sim | nunca vazio nem em forma de slug — é o cabeçalho da página |
| `manufacturer` | string | não | default `""` |
| `description` | string | não | default `""` |
| `layout` | string | não | `"series-rows"` (padrão) ou `"catalog-grid"` — ver §5 |
| `filters` | string[] | não | espelha as séries distintas dos produtos |
| `productCount` | number | não | quantidade de produtos |
| `thumbCount` | number | não | quantidade de arquivos em `thumbs/` — **uma miniatura por geometria, não por produto** |

`thumbCount` denuncia degradação silenciosa: um catálogo com produtos mas `thumbCount: 0` (ou
menor que a contagem de geometrias distintas) diz que a etapa de miniaturas foi pulada ou falhou
— quem consome vai cair no render dinâmico no browser para aqueles produtos.

### Regras de `slug`

- Apenas letras minúsculas, dígitos, hífen e underscore: `^[a-z0-9][a-z0-9\-_]{0,60}$`.
- Deve começar com letra ou dígito; até 61 caracteres.
- Um pacote com o mesmo `slug` de um já registrado substitui o anterior (upsert) — comportamento
  do lado que recebe, documentado em `docs/integracoes/bilds-com.md`.

## 3. `catalog.json` — dados para a página

Campos **em português** por convenção (é o formato que a página pública consome e apresenta ao
usuário final):

```json
{
  "slug":       "linha-principal",
  "titulo":     "Linha Principal de Equipamentos",
  "fabricante": "Fabricante Exemplo",
  "descricao":  "Descrição geral do catálogo.",
  "layout":     "series-rows",
  "filtros":    ["Serie-A", "Serie-B"],
  "produtos": [
    {
      "id":     "produto-a1",
      "nome":   "Produto A1 — Variante 1",
      "serie":  "Serie-A",
      "geo":    "produto-a1.json",
      "thumb":  "produto-a1.webp",
      "specs":  { "Propriedade 1": "Valor 1" },
      "curva":  null
    }
  ]
}
```

| Campo do produto | Tipo | Obrigatório | Observação |
|---|---|---|---|
| `id` | string | sim | único dentro do catálogo, sem espaços |
| `nome` | string | sim | nome completo exibido no card e no modal |
| `serie` | string | sim | agrupamento (linhas em `series-rows`, filtro em `catalog-grid`) |
| `geo` | string | sim | **nome do arquivo**, não caminho — `"produto-a1.json"`, nunca `"geo/produto-a1.json"` |
| `thumb` | string | não | nome do arquivo em `thumbs/`; ausente = render dinâmico no consumidor |
| `specs` | objeto | não | pares chave/valor de texto, número ou booleano |
| `curva` | array \| null | não | pontos da curva Q-H — ver §8 |

`slug`, `titulo`/`title`, `layout` e `filtros`/`filters` devem ser idênticos entre os dois
arquivos — `catalog.json` é o detalhe, `manifest.json` é o resumo para registro.

## 4. `geo/<nome>.json` — geometria

Um arquivo por **geometria**, no contrato que todo viewer consome:

```json
{
  "pos": [x0,y0,z0, x1,y1,z1, ...],
  "col": [r0,g0,b0, r1,g1,b1, ...],
  "idx": [0,1,2, 0,2,3, ...]
}
```

| Campo | Obrigatório | Regra |
|---|---|---|
| `pos` | sim | posições em **metros**, eixo **Y-up**; `pos.length` múltiplo de 3 |
| `col` | não | cor RGB por vértice, componentes em `[0, 1]`; `col.length === pos.length` quando presente; `[]` = sem cor (o consumidor usa cinza uniforme) |
| `idx` | não | índices de triângulo; omitido = vértices já expandidos (non-indexed) |

**Cor e `idx` podem coexistir só quando a deduplicação leva a cor em conta.** A chave de
deduplicação de vértice precisa ser posição **+** cor:

```
key = (q(px), q(py), q(pz), q(cr), q(cg), q(cb))   # correto
key = (q(px), q(py), q(pz))                        # perde cor na fronteira entre materiais
```

Sem isso, dois vértices na mesma posição com cores diferentes — a costura entre duas peças de
cor distinta, por exemplo — são fundidos e uma das cores desaparece. Quando a cor é **por face**
(não por malha), a alternativa correta é expandir os vértices e **omitir `idx`**: um vértice
compartilhado entre duas faces de cor diferente é genuinamente ambíguo se indexado. Geometria
expandida custa ~5× mais bytes — prefira a versão indexada sempre que a cor for uniforme por
malha.

O nome do arquivo segue o regex `^[a-z0-9][a-z0-9\-_.]{0,100}\.json$` (case-insensitive) e deve
corresponder exatamente ao campo `geo` do produto em `catalog.json`.

## 4.1. `thumbs/<nome>.webp` — miniaturas (opcional)

Quando presente, é uma imagem WebP **448 × 324 px**, qualidade 0,85, com fundo opaco na mesma cor
do `clearColor` usado para renderizá-la — o fundo opaco é o que permite ao consumidor usar
`object-fit: contain` sem costura visível quando o card é mais largo que a proporção da imagem.

**Uma miniatura por geometria, não por produto** — a mesma regra de `geo/`: produtos que
compartilham geometria (variantes que mudam só em dado, nunca em forma) compartilham também a
miniatura. O nome do arquivo é o de `geo` com a extensão trocada (`produto-a1.json` →
`produto-a1.webp`).

A pasta inteira pode faltar, e produtos individuais podem ficar sem `thumb` mesmo dentro de um
pacote que tem `thumbs/` — nos dois casos o consumidor cai no render dinâmico de sempre. Isso é o
que mantém compatível todo pacote publicado antes de este campo existir. Ver
`docs/conhecimento/miniaturas.md` para como o arquivo é gerado e por que a mesma cena que o
renderiza precisa bater exatamente com a do viewer.

## 5. Layouts

O campo `layout` determina como o consumidor renderiza a lista de produtos:

| Valor | Comportamento | Quando usar |
|---|---|---|
| `series-rows` | uma linha horizontal por série, scroll horizontal | poucas séries (2–4) com muitas variantes cada |
| `catalog-grid` | grade densa com filtros por série | 20+ itens heterogêneos |

## 7. Exemplo completo

Estrutura de um ZIP com dois produtos de duas séries distintas, usando `series-rows`:

```
catalogo-exemplo.zip
├── manifest.json
├── catalog.json
└── geo/
    ├── produto-a1.json
    ├── produto-a2.json
    └── produto-b1.json
```

**manifest.json:**
```json
{
  "slug":         "linha-principal",
  "title":        "Linha Principal de Equipamentos",
  "manufacturer": "Fabricante Exemplo",
  "description":  "Descrição geral do catálogo.",
  "layout":       "series-rows",
  "filters":      ["Serie-A", "Serie-B"],
  "productCount": 3
}
```

**catalog.json:**
```json
{
  "slug":       "linha-principal",
  "titulo":     "Linha Principal de Equipamentos",
  "fabricante": "Fabricante Exemplo",
  "descricao":  "Descrição geral do catálogo.",
  "layout":     "series-rows",
  "filtros":    ["Serie-A", "Serie-B"],
  "produtos": [
    {
      "id":    "produto-a1",
      "nome":  "Produto A1 — Variante 1",
      "serie": "Serie-A",
      "geo":   "produto-a1.json",
      "specs": {
        "Propriedade 1": "Valor 1",
        "Propriedade 2": "Valor 2"
      },
      "curva": [
        [0,  30, 1.1,  0],
        [3,  25, 1.2, 42],
        [6,  18, 1.3, 58],
        [9,   8, 1.2, 48]
      ]
    },
    {
      "id":    "produto-a2",
      "nome":  "Produto A2 — Variante 2",
      "serie": "Serie-A",
      "geo":   "produto-a2.json",
      "specs": {
        "Propriedade 1": "Valor 3"
      },
      "curva": null
    },
    {
      "id":    "produto-b1",
      "nome":  "Produto B1",
      "serie": "Serie-B",
      "geo":   "produto-b1.json",
      "specs": {},
      "curva": null
    }
  ]
}
```

**geo/produto-a1.json — com cores por vértice, sem índices (non-indexed):**
```json
{
  "pos": [0.0, 0.0, 0.0,  1.0, 0.0, 0.0,  0.5, 1.0, 0.0],
  "col": [0.8, 0.2, 0.2,  0.8, 0.2, 0.2,  0.8, 0.2, 0.2],
  "idx": []
}
```

**geo/produto-b1.json — sem cores, com índices (indexed, geometria compartilhada):**
```json
{
  "pos": [0.0, 0.0, 0.0,  1.0, 0.0, 0.0,  1.0, 1.0, 0.0,  0.0, 1.0, 0.0],
  "col": [],
  "idx": [0, 1, 2,  0, 2, 3]
}
```

> **Nota sobre `idx` vazio vs. omitido:** o viewer aceita `[]` (array vazio) e `idx` ausente como equivalentes — ambos resultam em non-indexed geometry. A distinção relevante é: fornecer `idx` preenchido só faz sentido quando **não** há cores por face (campo `col` vazio ou ausente).

## 8. Curva Q-H (campo `curva`)

Campo específico de domínio hidráulico — representa a curva de desempenho de um equipamento onde
a relação entre vazão e altura manométrica é uma propriedade técnica do produto (bombas
centrífugas, ventiladores, compressores com curva).

```json
"curva": [
  [0,  35, 1.1,  0],
  [5,  28, 1.2, 55],
  [10, 18, 1.3, 62],
  [15,  5, 1.2, 40],
  [18,  0, 1.1,  0]
]
```

Cada ponto é `[Q, H, P, eff]`:

| Posição | Símbolo | Unidade | Descrição |
|---|---|---|---|
| 0 | Q | m³/h | vazão volumétrica |
| 1 | H | m.c.a | altura manométrica total |
| 2 | P | CV | potência no eixo |
| 3 | eff | % | rendimento hidráulico — `0` nos extremos (vazão nula ou máxima) é esperado |

Regras: no mínimo 2 pontos; ordenados por Q crescente; incluir o ponto de shut-off (`Q = 0`) e o
de vazão máxima (`H ≈ 0`) quando disponíveis; 5 a 15 pontos já descrevem qualquer curva real com
fidelidade suficiente. Produtos sem comportamento hidráulico (conexões, flanges, acessórios
estruturais) omitem o campo ou gravam `null` — ausência não é erro, só significa que a aba de
gráfico não aparece.

## 12. Checklist de validação antes de empacotar

- [ ] `manifest.slug` passa no regex de slug; `manifest.title` não vazio
- [ ] `manifest.layout` é um dos dois valores válidos (ou omitido)
- [ ] `manifest.productCount === catalog.produtos.length`; `manifest.filters === catalog.filtros`
- [ ] Cada `produto.geo` existe em `geo/`, passa no regex de nome, e `produto.id` é único
- [ ] Cada `geo/<nome>.json`: `pos.length % 3 === 0`; `col` vazio ou do mesmo tamanho de `pos`;
      se tem `col` **e** `idx`, a dedup usou posição + cor como chave (§4)
- [ ] Nenhum arquivo órfão em `geo/` ou `thumbs/` — todos referenciados por algum produto
- [ ] Se há `thumbs/`: todo `produto.thumb` preenchido existe; uma miniatura por geometria, não
      por produto; 448×324 WebP com fundo opaco

> Vários produtos podem apontar para o mesmo arquivo de geometria — é o caso normal quando peças
> diferem só em dado, não em forma (orientação de montagem, cor de acabamento). O ZIP deve conter
> **uma cópia** de cada arquivo, não uma por produto: numa biblioteca real de conexões,
> 856 produtos → 448 arquivos de geometria.

## Onde está no código

- `biblioteca/bim_pipeline/cli/zip_bilds.py` — CLI que monta o ZIP a partir de um `.aq` (um
  arquivo, ou em lote).
- `biblioteca/bim_pipeline/contratos/catalogo.schema.json` — o JSON Schema de `catalog.json`.
- `biblioteca/bim_pipeline/contratos/manifesto-catalogo-aq.schema.json` — o schema de
  `manifest.json`.
- `biblioteca/bim_pipeline/contratos/geometria.schema.json` — o schema de `geo/<nome>.json`.
- `biblioteca/bim_pipeline/miniaturas/` — a geração de `thumbs/<nome>.webp` (ver
  `docs/conhecimento/miniaturas.md`).

## Ver também

- `docs/conhecimento/miniaturas.md` — como o arquivo de `thumbs/` é gerado.
- `docs/conhecimento/catalogo-modelo.md` — como `geo`/`thumb` viram `geoKey`/`thumbKey` no lado
  de quem grava esse formato num banco de dados.
- `docs/integracoes/bilds-com.md` — o lado que recebe este ZIP por upload HTTP.
