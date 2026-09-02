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

## Flagged Ambiguities

_"import" (the verb, as in "upload and process") and "Import" (the domain entity with a state machine) — these are the same thing but the entity sense should be capitalized to distinguish it._
