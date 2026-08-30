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

## Flagged Ambiguities

_"import" (the verb, as in "upload and process") and "Import" (the domain entity with a state machine) — these are the same thing but the entity sense should be capitalized to distinguish it._
