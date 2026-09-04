# Concepts

Shared domain vocabulary for this project — entities, named processes, and status concepts with project-specific meaning. Seeded with core domain vocabulary from the dynamic BIM catalog POC (S4.2), then accretes as ce-compound and ce-compound-refresh process learnings; direct edits are fine. Glossary only, not a spec or catch-all.

---

## BIM Dynamic Catalog Domain

### GeometryStore
The interface that abstracts where BIM geometry and thumbnail blobs are stored. Exposes four operations: put, get, delete, and deleteByPrefix. The POC implements it against local disk (`DiskGeometryStore`); the reconstruction is intended to implement it against S3 (`S3GeometryStore`, not yet in this codebase). Code that writes or reads geometry files must go through this interface — never write directly to a filesystem path — so the storage backend can be swapped without touching the caller.

### Import
A pipeline run that ingests a `.aq` library file and produces a publishable catalog: documents in `bim_products`, a record in `bim_catalogs`, and geometry files written through GeometryStore. An Import has a state machine (recebido → parseando → gravando → publicado | vazio | falhou). The `falhou` terminal state carries a cleanup obligation: all geometry files written under this import's prefix must be deleted before the state is recorded. An import that reaches `vazio` parsed without error but found no geometry — this is a valid outcome for certain `.aq` files (tubes, fixture kits), not an error.

### Geometry Pointer
The fields `geoKey` and `thumbKey` on a product document. They are the only coupling between a MongoDB product document and its binary files. Key formats: `geo/{importId}/{slugifiedProductName}.json` for geometry (where the slug is derived from `NOME_PECA` in the `.aq` file), and `thumbs/{importId}/{mongoProductId}.webp` for thumbnails (where the id is the MongoDB `_id`). Queries on products never need to know the storage backend; the API layer resolves the pointer to a byte stream via GeometryStore.

---

## Escrita de `.aq` (eng-reversa)

### Código de diâmetro
O número que o AltoQi grava em `PECA.DIAMETRO_PECA`, `ENTRADA_PECA.DIAMETRO_EP` e `ENTRADA_3D.DIAMETRO`. **Não é uma medida** — é um índice numa escala de diâmetros nominais do AltoQi: 8 = 40 mm, 9 = 50 mm, 10 = 60 mm, 11 = 75 mm, 12 = 100 mm, 14 = 150 mm, 15 = 200 mm. Os códigos 1 a 7 não são observáveis nas bibliotecas disponíveis. Chamar de "diâmetro em cm" é o erro que esta entrada existe para evitar: a chave do `build_product_map` se chamava `diametro_cm` até 2026-09-02, e hoje é `diametro_codigo`.

### Sentinela
O valor que o AltoQi usa no lugar de `NULL` para dizer "não definido": `-2147483647` em coluna inteira e `-1.7976931348623157e+308` (`-DBL_MAX`) em coluna real. Uma coluna com sentinela **não** está vazia no sentido do SQL, então `IS NULL` não a encontra e qualquer aritmética sobre ela produz lixo. Aparece em `TIPO_CONFIGURACAO_GP`, `SECAO_EP` e, em 82% das peças da Amanco (963 de 1.168), em `DIAMETRO_PECA`.

### Forma representativa
Malha 3D gerada por parâmetro a partir do diâmetro nominal do catálogo e de proporções normativas ou inventadas, quando o fabricante não publica cota de forma. Distingue-se da **geometria de fabricante**, que vem do `.aq`, do IFC ou de medição. Uma forma representativa serve para visualizar, contar peça e detectar interferência grosseira, e **não** serve para conferir encaixe ou colisão fina. Toda peça que carrega uma traz a ressalva gravada no nome do `GRUPO_SIMBOLOGIA_3D` e numa propriedade personalizada, para que a distinção sobreviva até a ficha do produto na página publicada.

---

## Editor 3D e conversores CAD (POC de edição, `www/`)

### Parte
Unidade de edição no editor 3D: `{ pos, col, idx, matrix, visible, marker }`. Nasce da
**re-segmentação** do `{pos,col,idx}` plano em componentes conexos do grafo de triângulos.
Funciona porque o dedup do import põe a cor na chave — triângulos de cores diferentes nunca
compartilham vértice — logo cada componente tem cor uniforme e aproxima uma
`TQi3DTriangleMesh` do `.aq`. Uma parte com `marker = true` é um **bocal**: marcador de
conexão do AltoQi (verde `1,154,63`, azuis `10,84,152` e `0,116,232`), não produto. Uma
parte oculta não entra no arquivo salvo nem nos exports.

### Bake
Aplicar as matrizes das partes visíveis, concatenar, arredondar a 1 µm e deduplicar com a
mesma quantização float32 do import. É o que "Salvar geometria", "Exportar IFC" e
"Exportar .aq" fazem antes de escrever. Round-trip sem edição preserva os triângulos e
reduz o JSON pela metade.

### Original preservado
Na primeira escrita de `PUT /geometrias/:id` o arquivo vivo é copiado para
`<id>.orig.json` no mesmo prefixo do import; "restaurar original" copia de volta e apaga
o backup. Para as informações, o equivalente é `infoOriginal` no documento do produto.

### Importação CAD
Um STEP ou IFC que entra como produto de um catálogo pelo `POST /cad/importar`. Tem um
`BimImport` próprio (porque `geoKey` e miniatura embutem o `importId`) e passa pelo mesmo
estado do import de `.aq`: recebido → parseando → gravando → publicado | falhou. É
**assíncrona**: um Revit de 124 MB leva ~4 min. O progresso do conversor vai em
`BimImport.note`.

### Caminho exato e caminho rápido (IFC)
O `ifc_to_geo.py` escolhe entre o `parse_ifc.py` do projeto (exato: `IFCINDEXEDCOLOURMAP`,
placements, instâncias) para arquivo ≤ 20 MB com `IFCTRIANGULATEDFACESET`, e o
`ifcopenshell.geom.iterator` (C++, cor por material) para o resto. O rápido descarta
triângulos degenerados e já entrega metros.

### Arestas de borda
Arestas com um só triângulo. Zero em sólido fechado gerado (tubo, caixa). Em malha de
fabricante **não** mede qualidade: a Dancor tem 25–32% de arestas de borda porque a
tesselação chega como sopa de triângulos. O painel mostra o número; só é alarme em parte
gerada ou importada.

---

## Termos usados em todo o repositório (acrescentados em 2026-09-04, S7.8)

A auditoria (I25/CONCEPTS) apontou termos usados em dezenas de arquivos sem definição. Uma linha cada:

| Termo | Significado aqui |
|---|---|
| **OQ3D** | Formato binário proprietário do AltoQi para a malha 3D dentro do `.aq` (BLOB `SIMBOLOGIA_3D.SIMBOLOGIA_3D`). Assinatura de 37 bytes, árvore de nós com transforms column-major, unidades em **centímetros**. Leitor: `scripts/oq3d.py` e `www/tools/oq3d-parser.ts`; escritor: `eng-reversa/tools/oq3d_writer.py`. Ver `docs/conhecimento/oq3d.md`. |
| **Simbologia 3D** | Registro de `SIMBOLOGIA_3D` no `.aq`: uma malha OQ3D com nome, ligada às peças por `PECA_SIMBOLOGIA_3D`. Peça sem simbologia (tubo, kit) não tem forma fixa e é pulada por design. |
| **TQi3DReusedObject** | Nó do OQ3D que reaproveita por referência uma malha já lida (parafusos, repetições). Não resolvê-lo custava ~30% dos triângulos (S5.1, 2026-08-30). |
| **ADR** | *Architecture Decision Record* — decisão numerada com contexto e consequência. Vivem em `docs/plano-produto-dinamico.md` §9 e em `docs/solutions/architecture-patterns/`. |
| **importId** | UUID de um `BimImport` da POC. Entra nas chaves de storage (`geo/<importId>/…`, `thumbs/<importId>/…`), então apagar e reimportar produz chaves novas. |
| **slug** | Identificador em minúsculas com hifens, derivado do título (`slugify`, com normalização NFD). Nomeia o catálogo na URL, a pasta do preview e o ZIP. |
| **dedup** | Deduplicação de vértices por chave exata (posição quantizada em float32, e cor quando há) — `scripts/dedup.py` e o equivalente no `parse-worker.ts`/`mesh-model.ts`. Reduz ~79% dos vértices; **não** solda emendas de malha de fabricante. |
| **series-rows / catalog-grid** | Os dois layouts de página: fileiras por série (bombas, com curva Q-H) e grade densa com filtros (conexões). Escolhido pela inferência do `build.py`. |
| **Q-H** | Curva vazão × altura manométrica de uma bomba, lida de `CURVA_BOMBA` do `.aq` e desenhada em SVG no layout `series-rows`. |
| **bocal** | Marcador de conexão do AltoQi dentro da malha: partes verdes `(1,154,63)` e azuis `(10,84,152)`, `(0,116,232)`. Não é produto; o leitor pode filtrá-los (`skip_markers`) e o editor os lista como "Bocal N". |
| **customUrl** | Campo da empresa na POC que vira o primeiro segmento da URL pública (`/<customUrl>/<slug>`). |
| **SwiftShader** | Renderizador WebGL por software do Chromium; obrigatório (flags) para o Playwright renderizar miniaturas e rodar os testes e2e em WSL/CI sem GPU. |
| **harness** | `templates/thumbs/harness.html`: página mínima com o mesmo Three.js, `buildScene()` e câmera do viewer, aberta pelo Playwright para fotografar cada geometria. |
| **Import** (POC) vs **importar** | Ver "Flagged Ambiguities" abaixo. |

## Flagged Ambiguities

_"import" (the verb, as in "upload and process") and "Import" (the domain entity with a state machine) — these are the same thing but the entity sense should be capitalized to distinguish it._
