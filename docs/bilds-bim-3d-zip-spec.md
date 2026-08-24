# Especificação do ZIP — Módulo BIM 3D (bilds.com)

> **Documento de engenharia reversa** — gerado a partir do código-fonte de
> `bilds.com/apps/api/src/b-bim-3d/` e `bilds.com/apps/web/src/components/b-bim-3d/`.
> Use este documento como contrato para qualquer pipeline que precise gerar
> um arquivo `.zip` compatível com o upload em `dashboard.bilds.com → BIM 3D`.

---

## 1. Estrutura do ZIP

```
bilds-upload.zip
├── manifest.json        ← obrigatório
├── catalog.json         ← obrigatório
└── geo/
    ├── produto-a.json   ← um arquivo por produto com geometria 3D
    ├── produto-b.json
    └── ...
```

Regras gerais:
- `manifest.json` e `catalog.json` devem estar na **raiz** do ZIP (não em subpastas).
- Os arquivos de geometria devem estar **exatamente** em `geo/<nome>.json` (um nível de profundidade).
- O ZIP não pode ter mais de **10.000 entradas** nem ultrapassar **500 MB** descomprimido.
- Cada arquivo geo não pode ultrapassar **10 MB**.
- O arquivo enviado ao endpoint deve ter MIME `application/zip` ou extensão `.zip`.
- Tamanho máximo do arquivo comprimido: **100 MB**.

---

## 2. `manifest.json`

Lido pelo servidor para registrar o catálogo no MongoDB. Todos os campos em inglês.

```json
{
  "slug":         "bombas-incendio",
  "title":        "Bombas de Combate a Incêndio",
  "manufacturer": "Dancor",
  "description":  "Linha CAM-W e TJM para sistemas de combate a incêndio.",
  "layout":       "series-rows",
  "filters":      ["W", "TJM"],
  "productCount": 12
}
```

### Campos

| Campo          | Tipo     | Obrigatório | Validação / Default                                              |
|----------------|----------|-------------|------------------------------------------------------------------|
| `slug`         | string   | **sim**     | Regex: `^[a-z0-9][a-z0-9\-_]{0,60}$`. Único por empresa.       |
| `title`        | string   | **sim**     | Título do catálogo exibido na página pública.                   |
| `manufacturer` | string   | não         | Nome do fabricante. Default: `""`.                              |
| `description`  | string   | não         | Descrição longa. Default: `""`.                                 |
| `layout`       | string   | não         | `"series-rows"` (default) ou `"catalog-grid"`. Ver seção 5.     |
| `filters`      | string[] | não         | Lista de séries/filtros. Default: `[]`. Usado pelos chips de filtro no `catalog-grid` e na eyebrow do hero. |
| `productCount` | number   | não         | Quantidade de produtos. Default: `0`. Apenas informativo no dashboard. |

### Regras de `slug`

- Apenas letras minúsculas, números, hífen e underscore.
- Deve começar com letra ou número.
- Máximo 61 caracteres no total.
- É usado como parte da URL pública: `/{customLink}/{slug}`.
- **Re-upload com o mesmo slug faz upsert** (substitui o catálogo existente).

---

## 3. `catalog.json`

Lido pelo browser para montar a página pública. Campos em **português** (convenção da plataforma bilds.com para dados apresentados ao usuário).

```json
{
  "slug":      "bombas-incendio",
  "titulo":    "Bombas de Combate a Incêndio",
  "fabricante":"Dancor",
  "descricao": "Linha CAM-W e TJM para sistemas de combate a incêndio.",
  "layout":    "series-rows",
  "filtros":   ["W", "TJM"],
  "produtos": [
    {
      "id":    "cam-w10",
      "nome":  "CAM-W10 1CV T 220/380V INC FLG IR3",
      "serie": "W",
      "geo":   "cam-w10.json",
      "specs": {
        "Tensão":   "Trifásico 220/380V",
        "Rotação":  "3.500 rpm · 60Hz",
        "Potência": "1 CV"
      },
      "curva": [
        [0,  30, 1.1,  0],
        [3,  25, 1.2, 42],
        [6,  18, 1.3, 58],
        [9,   8, 1.2, 48]
      ]
    }
  ]
}
```

### Campos raiz

| Campo      | Tipo       | Obrigatório | Descrição                                                         |
|------------|------------|-------------|-------------------------------------------------------------------|
| `slug`     | string     | sim         | Deve ser idêntico ao `slug` do `manifest.json`.                   |
| `titulo`   | string     | sim         | Título do catálogo.                                               |
| `fabricante`| string    | sim         | Nome do fabricante.                                               |
| `descricao`| string     | não         | Descrição longa. Pode ser `""`.                                   |
| `layout`   | string     | não         | `"series-rows"` ou `"catalog-grid"`. Pode ser omitido (o servidor usa o campo `layout` do `manifest.json`). |
| `filtros`  | string[]   | não         | Lista de rótulos de filtro/série. Deve espelhar `filters` do manifest. |
| `produtos` | Produto[]  | sim         | Array de produtos. Pode estar vazio `[]`.                         |

### Campos de cada produto

| Campo   | Tipo                              | Obrigatório | Descrição                                                                 |
|---------|-----------------------------------|-------------|---------------------------------------------------------------------------|
| `id`    | string                            | sim         | Identificador único do produto dentro do catálogo. Sem espaços.           |
| `nome`  | string                            | sim         | Nome completo exibido no card e no modal.                                 |
| `serie` | string                            | sim         | Série ou família do produto (ex.: `"W"`, `"TJM"`). Usado para agrupamento no `series-rows` e filtro no `catalog-grid`. |
| `geo`   | string                            | sim         | Nome do arquivo de geometria dentro da pasta `geo/` do ZIP. Deve terminar em `.json`. Exemplo: `"cam-w10.json"`. |
| `specs` | Record\<string, string \| number\>| não         | Especificações técnicas em pares chave/valor. Exibidos na aba "Especificações" do modal. |
| `curva` | [Q, H, P, eff][] \| null          | não         | Pontos da curva Q-H para o gráfico. Cada ponto é `[vazão_m³/h, altura_mca, potência_cv, rendimento_%]`. `null` ou ausente = sem gráfico. |

> **Atenção:** `produto.geo` é apenas o **nome do arquivo** (ex.: `"cam-w10.json"`), não um caminho. A URL final é montada pelo frontend como `{geoBaseUrl}{produto.geo}`.

---

## 4. Arquivos de geometria — `geo/<nome>.json`

Cada produto com geometria 3D tem um arquivo JSON correspondente. O viewer usa **Three.js `BufferGeometry`** com arrays flat.

```json
{
  "pos": [x0,y0,z0, x1,y1,z1, x2,y2,z2, ...],
  "col": [r0,g0,b0, r1,g1,b1, r2,g2,b2, ...],
  "idx": [0,1,2, 0,2,3, ...]
}
```

### Campos

| Campo | Tipo      | Obrigatório | Descrição                                                                                                |
|-------|-----------|-------------|----------------------------------------------------------------------------------------------------------|
| `pos` | number[]  | **sim**     | Posições de vértices em array flat: `[x, y, z, x, y, z, ...]`. Valores em **metros**, eixo Y-up (Three.js). |
| `col` | number[]  | não         | Cores por vértice em array flat: `[r, g, b, r, g, b, ...]`. Componentes normalizados em `[0, 1]`. Array vazio `[]` = sem cor (viewer usa cinza `#8896AA`). |
| `idx` | number[]  | não         | Índices de triângulos (indexed geometry). Array flat: `[i0, i1, i2, ...]`. Omitir quando os vértices já estão expandidos (non-indexed). |

### Regras

- **`pos.length` deve ser múltiplo de 3.**
- Se `col` for fornecido, `col.length` deve ser igual a `pos.length` (uma cor por vértice).
- Se `idx` for fornecido, cada índice deve referenciar um vértice válido em `pos`.
- **Cores e `idx` são mutuamente exclusivos na prática:** quando há cor por face (IFCINDEXEDCOLOURMAP), gerar vértices expandidos (non-indexed) para que cada vértice carregue a cor da sua face. Não fornecer `idx` nesse caso.
- O viewer chama `geom.computeVertexNormals()` — não é necessário incluir normais no JSON.
- O viewer centraliza automaticamente a geometria usando o bounding box — não é necessário pré-centrar.

### Convenção de eixos (IFC → Three.js)

Se o pipeline fonte usa IFC (Z-up):

```
THREE.x =  IFC.x
THREE.y =  IFC.z   ← Z do IFC vira Y no Three.js
THREE.z = -IFC.y   ← Y do IFC inverte e vira Z
```

### Nome do arquivo

O nome deve corresponder exatamente ao valor do campo `geo` no produto de `catalog.json`.

Regex de validação do servidor: `^[a-z0-9][a-z0-9\-_.]{0,100}\.json$` (case-insensitive).

---

## 5. Layouts disponíveis

O campo `layout` (em `manifest.json`) determina como a página pública renderiza o catálogo.

| Valor           | Comportamento                                                                                                          |
|-----------------|------------------------------------------------------------------------------------------------------------------------|
| `series-rows`   | Uma linha horizontal por série (`produto.serie`), scroll horizontal. Stats: Fabricante / Modelos / **Séries** / Formato. Ideal para poucas séries (2–4) com muitas variantes. |
| `catalog-grid`  | Grid denso com chips de filtro por série. Stats: Fabricante / Produtos / **Famílias** / Formato. Ideal para 20+ itens heterogêneos. |

> O layout pode ser sobrescrito via `PATCH /companies/:id/b-bim-3d/:slug` no dashboard admin sem re-upload.

---

## 6. Endpoint de upload

```
POST /companies/{companyId}/b-bim-3d
Content-Type: multipart/form-data
Authorization: cookie SuperTokens (sessão autenticada)

Campo:  zip    ← arquivo .zip
Campo:  layout ← (opcional) "series-rows" | "catalog-grid"
                  Sobrescreve o layout do manifest.json se fornecido.
```

- **Re-upload** com o mesmo `slug` faz **upsert** (sobrescreve o catálogo e os arquivos).
- O campo `layout` do form tem precedência sobre o `layout` do `manifest.json`.
- Apenas o **criador** ou **administrador** da empresa podem fazer upload. Usuários com role `Admin` na plataforma bypassam essa verificação.

---

## 7. Exemplo genérico completo

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

---

## 8. Curva Q-H (campo `curva`)  

### Quando usar

O campo `curva` é **específico de domínio hidráulico** — representa a curva de desempenho de equipamentos como bombas centrífugas, onde a relação entre vazão e altura manométrica é uma propriedade técnica fundamental do produto.

**Use `curva` apenas quando:**
- A biblioteca de origem tiver dados hidráulicos (curva Q-H) associados ao produto.
- O produto for um equipamento com desempenho variável em função de vazão (bombas, ventiladores, compressores com curva).

**Não use `curva` (omita ou defina como `null`) quando:**
- O produto não tem comportamento hidráulico (conexões, flanges, válvulas de bloqueio, acessórios estruturais, etc.).
- A biblioteca não exporta dados de curva para aquele produto.
- O produto tem apenas dados de ponto de operação fixo, sem variação de vazão.

A ausência de `curva` não é um erro — o viewer simplesmente não exibe a aba de gráfico para esses produtos.

### Formato

```json
"curva": [
  [Q,  H,   P,   eff],
  [0,  35,  1.1, 0  ],
  [3,  30,  1.2, 42 ],
  [6,  22,  1.3, 58 ],
  [9,  12,  1.3, 52 ],
  [12,  0,  1.2, 0  ]
]
```

Cada elemento é um array de 4 números na ordem: `[Q, H, P, eff]`.

| Posição | Símbolo | Unidade  | Descrição                                             |
|---------|---------|----------|-------------------------------------------------------|
| 0       | Q       | m³/h     | Vazão volumétrica                                     |
| 1       | H       | m.c.a    | Altura manométrica total (metros de coluna d'água)    |
| 2       | P       | CV       | Potência no eixo                                      |
| 3       | eff     | %        | Rendimento hidráulico (0–100). `0` em pontos extremos (vazão nula ou máxima) é correto. |

### Regras de construção

- A lista deve ter **no mínimo 2 pontos** para que o gráfico trace uma linha.
- Os pontos devem estar ordenados por **Q crescente** (vazão de menor para maior).
- O ponto de vazão nula (`Q = 0`) representa a altura de shut-off — incluir quando disponível.
- O ponto de vazão máxima (`H = 0` ou próximo de zero) representa o limite da curva — incluir quando disponível.
- `eff = 0` nos extremos (shut-off e runout) é esperado e correto; o viewer trata isso sem divisão por zero.
- Não há limite de quantidade de pontos, mas 5–15 pontos já descrevem qualquer curva com fidelidade suficiente.

### Exemplo com e sem curva no mesmo catálogo

```json
"produtos": [
  {
    "id":    "bomba-x",
    "nome":  "Bomba X — com curva Q-H",
    "serie": "Serie-A",
    "geo":   "bomba-x.json",
    "specs": { "Rotação": "3.500 rpm" },
    "curva": [
      [0, 35, 1.1, 0],
      [5, 28, 1.2, 55],
      [10, 18, 1.3, 62],
      [15, 5,  1.2, 40],
      [18, 0,  1.1, 0]
    ]
  },
  {
    "id":    "flange-y",
    "nome":  "Flange Y — sem curva",
    "serie": "Serie-A",
    "geo":   "flange-y.json",
    "specs": { "DN": "50 mm" },
    "curva": null
  }
]
```

### O que o viewer faz com `curva`

- `curva` com dados → exibe aba **"Curva Q-H"** no modal do produto com gráfico SVG mostrando curva de altura (H × Q) e, se todos os pontos `eff > 0`, curva de rendimento pontilhada sobreposta.
- `curva: null` ou campo ausente → aba **"Curva Q-H"** não é exibida. Sem erro.

---

## 9. Erros retornados pelo servidor

| Código HTTP | Mensagem                                                     | Causa                                                                |
|-------------|--------------------------------------------------------------|----------------------------------------------------------------------|
| 400         | `Arquivo ZIP inválido`                                       | Buffer não é um ZIP válido.                                          |
| 400         | `ZIP excede limites permitidos`                              | Mais de 10.000 entradas ou mais de 500 MB descomprimido.             |
| 400         | `ZIP deve conter manifest.json e catalog.json`               | Um dos dois arquivos obrigatórios está ausente.                      |
| 400         | `Erro ao ler manifest.json ou catalog.json`                  | JSON malformado.                                                     |
| 400         | `manifest.json inválido: slug e title são obrigatórios`      | `slug` ou `title` ausentes ou vazios.                                |
| 400         | `manifest.json: slug inválido — use apenas letras minúsculas...` | Slug não passa no regex `^[a-z0-9][a-z0-9\-_]{0,60}$`.          |
| 400         | `manifest.json: layout inválido: {valor}`                    | `layout` não é `"series-rows"` nem `"catalog-grid"`.                |
| 400         | `Empresa não possui customLink`                              | A empresa de destino não tem `customLink` configurado.               |
| 400         | `geo/{nome} excede 10 MB`                                    | Arquivo de geometria maior que 10 MB.                                |
| 400         | `Apenas arquivos ZIP são permitidos`                         | MIME ou extensão não é ZIP.                                          |
| 400         | `Arquivo ZIP obrigatório`                                    | Campo `zip` ausente no multipart.                                    |
| 403         | `Sem permissão para editar esta empresa`                     | Usuário não é criador nem administrador da empresa.                  |
| 404         | `Empresa não encontrada`                                     | `companyId` inválido ou empresa deletada.                            |
| 413         | _(Multer)_                                                   | ZIP comprimido maior que 100 MB.                                     |
| 500         | `Erro ao salvar arquivos do catálogo localmente`             | Falha de filesystem (modo local).                                    |
| 500         | `Erro ao enviar arquivos do catálogo para o S3`              | Falha de upload S3.                                                  |
| 500         | `Erro ao persistir catálogo no banco de dados`               | Falha no MongoDB após storage bem-sucedido (storage é revertido).    |

---

## 10. Comportamento de upsert

Se a empresa já possui um catálogo com o mesmo `slug`:

1. Os arquivos antigos são **substituídos** (S3: `deletePrefix` + re-upload; local: overwrite).
2. O documento MongoDB é atualizado via `upsert` (mesmo `_id`).
3. O campo `publishedAt` é atualizado para `new Date()`.
4. O campo `layout` no banco usa a precedência: `form.layout` > `manifest.layout` > `"series-rows"`.

---

## 11. URL pública resultante

Após o upload bem-sucedido, o catálogo fica disponível em:

```
https://bilds.com/{customLink}/{slug}
```

Onde `{customLink}` é o campo `customLink` da empresa fabricante na plataforma bilds.com.

---

## 12. Checklist de validação do pipeline

Antes de gerar o ZIP, verificar:

- [ ] `manifest.slug` passa no regex `^[a-z0-9][a-z0-9\-_]{0,60}$`
- [ ] `manifest.title` não está vazio
- [ ] `manifest.layout` é `"series-rows"` ou `"catalog-grid"` (ou omitido)
- [ ] `manifest.productCount` é igual a `catalog.produtos.length`
- [ ] `manifest.filters` é igual a `catalog.filtros`
- [ ] Para cada produto em `catalog.produtos`:
  - [ ] `produto.geo` existe em `geo/` dentro do ZIP
  - [ ] `produto.geo` passa no regex `^[a-z0-9][a-z0-9\-_.]{0,100}\.json$`
  - [ ] `produto.id` é único dentro do catálogo
- [ ] Para cada arquivo `geo/<nome>.json`:
  - [ ] `pos.length % 3 === 0`
  - [ ] `col` é vazio `[]` ou `col.length === pos.length`
  - [ ] Tamanho do arquivo ≤ 10 MB
  - [ ] Nome do arquivo referenciado por exatamente um produto em `catalog.produtos`
- [ ] ZIP total ≤ 100 MB comprimido
- [ ] ZIP descomprimido ≤ 500 MB
- [ ] ZIP tem ≤ 10.000 entradas

---

_Gerado por engenharia reversa em: 2026-08-23_
_Fonte: `bilds.com/apps/api/src/b-bim-3d/` · `bilds.com/apps/web/src/components/b-bim-3d/` · `bilds.com/docs/modules/bim-3d-module.md`_
