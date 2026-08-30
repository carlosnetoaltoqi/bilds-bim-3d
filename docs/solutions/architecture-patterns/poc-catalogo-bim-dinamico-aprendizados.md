---
title: "POC catálogo BIM dinâmico — aprendizados e decisões para a reconstrução"
date: "2026-08-30"
category: "architecture-patterns"
module: "bilds-bim-3d-poc"
problem_type: architecture_pattern
component: documentation
severity: high
applies_when:
  - "Ao iniciar a reconstrução (produção) do catálogo BIM dinâmico após a POC, para garantir que ADRs e armadilhas conhecidas sejam endereçados desde o início"
  - "Ao avaliar trade-offs de performance entre SSR e geração estática de páginas de catálogo com dados vindos do MongoDB Atlas"
  - "Ao desenhar o pipeline de importação de arquivos .aq — especialmente deduplicação de geometria, encoding cp1252 e comunicação por IPC com processos filhos"
tags:
  - bim
  - mongodb
  - nestjs
  - nextjs
  - typescript-parser
  - geometry-store
  - dynamic-catalog
  - poc
---

# POC catálogo BIM dinâmico — aprendizados e decisões para a reconstrução

## Context

The bilds.com BIM catalog has historically served product data (geometries, thumbnails, metadata) as static files from a CDN. This model works at small scale but creates a hard coupling: updating a product means regenerating static files, re-deploying, and waiting for CDN propagation. There is no server-side search, no filtering by attribute, and no programmatic update path. As the number of manufacturers onboarded to bilds.com grows, the manual static-file workflow becomes a bottleneck.

The bilds-bim-3d POC set out to answer five concrete questions before committing to a full reconstruction:

1. Does a dynamic catalog (data from MongoDB) work at all?
2. Can the `.aq` binary parser run on the server in TypeScript?
3. Do thumbnails survive the move from CDN to server-side generation?
4. Is page performance acceptable when data comes from a database rather than a CDN edge?
5. Does the model scale to the number of manufacturers bilds.com expects to onboard?

All five questions were answered affirmatively with measured data, not estimates. This document records those answers, the architectural decisions made along the way, the bugs found, what was deliberately left out, and what the reconstruction for bilds.com must do differently.

---

## Guidance

### Architecture: data split and storage abstraction

The POC proved one foundational decision above all others: geometry and thumbnail data must live in file storage (disk in development, S3 in production), not in MongoDB. A product document in the `bim_products` collection holds only a `geoKey` and a `thumbKey` — pointers into the file store. The MongoDB document carries all searchable, filterable, human-readable fields. The binary blobs live elsewhere.

Storing geometry as `BinData` in MongoDB was evaluated and rejected. It killed the binary codec, hit document-size gates, and produced a system that was harder to reason about and impossible to serve efficiently via HTTP range requests.

The abstraction that makes this portable is `GeometryStore`, a four-method interface:

```typescript
interface GeometryStore {
  put(key: string, buffer: Buffer): Promise<void>;
  get(key: string): Promise<Buffer | null>;
  delete(key: string): Promise<void>;
  deleteByPrefix(prefix: string): Promise<void>;
}
```

The POC implements `DiskGeometryStore`. The reconstruction implements `S3GeometryStore` with the same interface — one line of change at the dependency-injection site. The API layer serves geometry over HTTP (`GET /geometrias/:id`) to avoid CORS issues when the frontend fetches from a different origin than the storage bucket.

### The `.aq` parser in TypeScript

The `.aq` binary format is the input to every import. The POC ported the parser from a Python subprocess to native TypeScript. The performance difference is decisive:

| Implementation | Time (13 Dancor products, 10.9M elements) | Memory (RSS delta) |
|---|---|---|
| Python worker (S2.1) | ~39,000ms | +189 MB |
| TypeScript port (ADR-002) | 658ms | +422 MB |

The TypeScript port is 59× faster. The memory cost (2.2× higher) is the primary risk to monitor in production. The candidate optimization is replacing `Array<[number, number, number]>` with `Float64Array` for the internal vertex representation — this reduces GC pressure and memory allocation overhead significantly for large models.

The worker runs in a child process spawned with `child_process.fork()` and a 5-minute timeout. The critical fix discovered in the POC: **never call `process.exit(0)` immediately after `process.send!(result)`**. The IPC message is written to a kernel pipe, and if the process exits before the buffer flushes, the message is dropped silently. For small payloads (13 Dancor products) this was synchronous in practice and did not manifest. For large payloads (Amanco, 856 products), `child.on('message')` never fired — the import hung in "parseando" until the 5-minute timeout expired. The correct pattern:

```typescript
// WRONG — drops IPC payload on large responses
process.send!(result);
process.exit(0);

// CORRECT — exits only after IPC flush confirms
process.send!(result, () => process.exit(0));
```

### Vertex deduplication is mandatory

Raw `.aq` files contain duplicate vertex entries. Without deduplication, geometry files are approximately 4× larger than necessary. The POC's active Dancor import was made before `dedupBuffers()` was implemented in `parse-worker.ts` — those geo files are 14 MB per product on average instead of 3.4 MB. The `dedupBuffers()` function has since been validated: running it on the same Dancor input produces 44.7 MB total, identical to the output of the reference Python `dedup.py` script.

Deduplication must run on every import. The reconstruction must also implement a re-processing route for existing imports that were ingested without dedup.

### Server-side thumbnail generation

Thumbnails are generated server-side after import completes, in a fire-and-forget worker (`spawnThumbWorker`). Two approaches were evaluated:

**Approach A — Playwright + Chromium + SwiftShader**: renders the full three.js scene. Output: 240ms per geometry, 5.5 KB/WebP. Startup penalty: 2–5s cold start, ~1.5 GB Docker image. Produces PBR-identical thumbnails to the live viewer.

**Approach B — TypeScript rasterizer + ffmpeg**: software z-buffer rasterizer with ambient (0.7) + key (0.9) + fill (0.35) lighting, perspective projection, exported via ffmpeg to WebP. Output: 65ms per geometry, 4.3 KB/WebP. No browser, no startup penalty. Flat shading — visually distinct from the PBR viewer but acceptable for catalog cards.

ADR-003 chose Approach B: 3.7× faster per geometry, smaller output, and no Chromium in the production pod. The visual quality gap (flat shading vs PBR) is the one remaining differentiator between the static and dynamic catalog models. If the SSR catalog page is cached at the CDN (see below), LCP of both models converges — the thumbnail visual fidelity becomes the only user-facing difference.

### Page performance: SSR with CDN caching

The POC renders the catalog page via Next.js SSR reading directly from MongoDB. Measured performance vs the static CDN baseline:

**Initial page load:**

| Metric | Static (CDN) | POC (database) | Difference |
|---|---|---|---|
| HTML size | 44 KB | 71.9 KB | 1.6× larger |
| 13 thumbs (total) | ~56 KB | 57.3 KB | ≈ equal |
| Total initial bytes | ~100 KB | ~129 KB | 1.3× larger |
| TTFB (production est.) | ~50ms (CDN edge) | ~150–300ms (SSR) | 3–6× slower |
| Time to first card | ~100ms | ~280–380ms | ~3× slower |

**Modal (opens a product):**

| Metric | Static (CDN) | POC without dedup | POC with dedup |
|---|---|---|---|
| Geo size | 3.4–4.8 MB | 7–19 MB | 3.4–4.8 MB |
| Geo TTFB (production) | ~50ms (CDN) | ~80–150ms (API+disk) | ~80–150ms |

The raw SSR TTFB of 177–254ms is 3–6× slower than the CDN edge baseline. This is manageable, not a blocker. Adding `Cache-Control` headers to the catalog page allows a CDN to cache the SSR-generated HTML — on cache hit, the overhead drops to zero and LCP converges with the static model. The geometry endpoint (`GET /geometrias/:id`) can also be cached independently.

**Historical LCP context** (not measured with real Lighthouse — WSL has no headless browser for Web Vitals; values are sums of components measured with `curl`):

| Scenario | LCP | Source |
|---|---|---|
| bilds.com without thumbs (pre-BILDS-552) | 39.9s | Real Lighthouse |
| bilds.com with thumbs (post-BILDS-552) | ~100ms (estimated) | TTFB CDN + thumb CDN |
| POC with thumbs (S2.4 rasterizer) | ~300ms (estimated) | TTFB SSR + thumb API |

LCP must be measured with real Lighthouse in the production environment before the reconstruction is considered complete.

### Import state machine

The import lifecycle follows a state machine: `recebido → parseando → gravando → publicado | vazio | falhou`. The cleanup path on `falhou` is critical: it calls `deleteByPrefix` on geo files and `deleteMany` on product documents to prevent orphaned binary data. This pattern is solid and carries forward to the reconstruction unchanged.

### Scalability

Linear projection from the measured 1-catalog baseline (13 Dancor products, 44.7 MB with dedup):

| Scale | Documents (bim_products) | Geo on disk (with dedup) | Thumbs |
|---|---|---|---|
| 1 catalog | 13 docs | 44.7 MB | ~56 KB |
| 10 catalogs | ~130 docs | ~447 MB | ~560 KB |
| 50 catalogs | ~650 docs | ~2.2 GB | ~2.8 MB |
| 200 catalogs | ~2,600 docs | ~8.9 GB | ~11 MB |

MongoDB scales trivially for this document volume. The limiter is file storage. On S3 at ~$0.023/GB/month, 200 catalogs at the Dancor average (44.7 MB per catalog) costs ~$0.21/month. The Amanco import (856 products with dedup) generated 248 MB — if 250 MB per catalog is the average, 200 catalogs = 50 GB → ~$1.15/month. Both projections are economically viable.

---

## Why This Matters

The static CDN model will not scale to the number of manufacturers bilds.com intends to onboard. Each new catalog today requires manual file generation, deployment, and CDN propagation. With a dynamic catalog backed by MongoDB and S3-abstracted geometry storage:

- Products are updated programmatically without redeployment.
- The catalog is searchable and filterable server-side.
- Onboarding a new manufacturer is an import operation, not a deployment.
- The storage cost at 200 catalogs is under $2/month.

The performance cost of SSR over CDN-static is real but manageable: 3–6× higher TTFB on cold hits, converging to zero on CDN cache hits. This is a known, solvable problem. The alternative — scaling the manual static workflow — is not solvable without rebuilding the import pipeline anyway.

The TypeScript `.aq` parser is 59× faster than the Python subprocess it replaces and eliminates a Python runtime dependency from the production container. The 2.2× memory increase is the main operational risk — it must be monitored in production, with `Float64Array` as the first optimization candidate if RSS becomes problematic at scale.

---

## When to Apply

This guidance applies whenever:

- A new manufacturer catalog is being onboarded to bilds.com.
- The import pipeline (`parse-worker.ts`, `GeometryStore`, thumbnail worker) is being modified or extended.
- The definitive bilds.com BIM module is being designed or reconstructed.
- A decision is being made about geometry storage backends (disk vs S3 vs MongoDB BinData).
- Performance of the catalog page is being evaluated or optimized.

It does not apply to parts of bilds.com that do not handle BIM geometry (e.g., the project collaboration features, authentication, billing).

---

## Examples

### Correct IPC exit pattern in the parse worker

```typescript
// parse-worker.ts — after serializing the parse result
const result: ParseResult = {
  products: parsedProducts,
  buffers: serializedBuffers,
};

// Always flush IPC before exit — critical for large payloads
process.send!(result, () => process.exit(0));
```

### GeometryStore interface and swap point

```typescript
// geometry-store.ts
export interface GeometryStore {
  put(key: string, buffer: Buffer): Promise<void>;
  get(key: string): Promise<Buffer | null>;
  delete(key: string): Promise<void>;
  deleteByPrefix(prefix: string): Promise<void>;
}

// In production, swap this one line at the DI site:
// const store = new DiskGeometryStore(process.env.GEO_DIR!);
// const store = new S3GeometryStore(process.env.GEO_BUCKET!);
```

### Deduplication validation

The `dedupBuffers()` function in `parse-worker.ts` is validated against the Python reference: both produce 44.7 MB for the Dancor input (13 products). The active Dancor import (the one recorded in `bim_imports` before dedupBuffers was implemented) was made without dedup and produces 182.7 MB (4× larger). Any import pipeline change must verify that dedup runs before writing to GeometryStore.

### -0.0 vs 0.0 in cross-language geometry validation

When comparing geometry output between Python and JavaScript (`to_buffers()` produces `[-0.0, 0.0, ...]` for vertices resting on the y=0 plane, while Node emits `[0, 0, ...]`), strict equality fails. Use a semantic comparator:

```typescript
function geometricEqual(a: number, b: number): boolean {
  if (Object.is(a, b)) return true;
  if (Object.is(a, -0) && Object.is(b, 0)) return true;
  if (Object.is(a, 0) && Object.is(b, -0)) return true;
  return Math.abs(a - b) < Number.EPSILON;
}
```

### cp1252 BLOB reading in Node.js

When reading `.aq` file fields encoded in Windows-1252 via `node:sqlite` (Node v24):

```typescript
// Force BLOB return to avoid text round-trip issues
const row = db.prepare('SELECT CAST(name AS BLOB) as name FROM products').get();
const name = new TextDecoder('windows-1252').decode(row.name as Uint8Array);
// TextDecoder('windows-1252') handles the 5 undefined cp1252 bytes
// (0x81, 0x8D, 0x8F, 0x90, 0x9D) without throwing — correct behavior
```

---

## What the POC Did Not Implement

The following items were deliberately excluded from the POC. They are listed here so the reconstruction team knows which absences were intentional and which are mandatory additions:

| Not implemented | Reason | Status in reconstruction |
|---|---|---|
| SuperTokens, sessions, roles, fine-grained permissions | Already exists and mandatory in bilds.com | **mandatory** |
| Authorization by company owner/admin (`assertPermission`) | POC has only one user | **mandatory** |
| Soft delete (`deletedAt`) on all entities | House convention, no learning value here | **mandatory** |
| Two-layer validation (DTO + schema) | House convention | **mandatory** |
| i18n, `@workspace/ui`, RTK Query, Swagger | House conventions | **mandatory** |
| Atlas grant restricted by database | POC cluster is throwaway | **mandatory** |
| Rate limiting on upload endpoint | One user, no hostile input | **mandatory** |
| Visual fidelity of server-side thumbnails | ADR-003 chose flat shading (65ms) over PBR (240ms). If SSR is cached at CDN, LCP of both models converges — visual fidelity is the only remaining differentiator. | **evaluate with product team** |
| Re-processing of legacy imports | The active Dancor import was made before dedup was implemented — geo files 4× larger (182.7 MB vs 44.7 MB). No re-processing route exists. | **mandatory** |
| LCP measured with real Lighthouse | WSL has no headless browser with DevTools for Web Vitals. S4.1 estimated LCP via sum of components measured with `curl`. | **measure in production** |

Items marked **mandatory** must be present in the first production-bound increment of the reconstruction. The thumbnail fidelity question should be revisited with the product team once the reconstruction is in staging.

---

## For the Reconstruction

The reconstruction for bilds.com builds directly on the decisions proven in the POC. The load-bearing choices:

**1. GeometryStore as the single storage interface.** The `DiskGeometryStore` (put/get/delete/deleteByPrefix) is the right abstraction. Swap to `S3GeometryStore` with the same interface at the dependency-injection site. Validate with real S3 presigned URLs in staging before go-live.

**2. SSR with CDN caching.** The catalog page renders via SSR reading from MongoDB. Add `Cache-Control: public, max-age=300, stale-while-revalidate=60` (or equivalent) to allow the CDN to cache SSR output. On cache hit, TTFB converges with the static CDN model. Measure LCP with real Lighthouse in the production environment — do not rely on `curl`-based estimates.

**3. Import state machine with cleanup and queue.** The state machine (`recebido → parseando → gravando → publicado | vazio | falhou`) carries forward unchanged. The reconstruction adds: presigned S3 URL for direct browser upload (bypasses the Next.js 10 MB body limit in dev/proxy), a proper job queue (BullMQ on Redis, or SQS if the team is already on AWS), and a re-processing route for existing imports that were ingested without dedup.

**4. TypeScript parser is production-ready.** ADR-002 is closed: 658ms for 13 products, 59× faster than Python. Memory consumption (422 MB RSS delta for Dancor) is the primary operational risk. Monitor RSS in production. Optimize with `Float64Array` for internal vertex arrays if RSS becomes a problem at scale. Do not reintroduce the Python subprocess.

**5. Thumbnail generation as a separate queue consumer.** The fire-and-forget pattern is correct in principle. In production, thumbnail generation moves to a separate queue consumer so that thumbnail failure never blocks catalog publication. The rasterizer parameters (ambient 0.7 + key 0.9 + fill 0.35, perspective projection, z-buffer) are validated and carry forward.

**6. Vertex deduplication on every import.** Without dedup, geo files are 4× larger. `dedupBuffers()` in `parse-worker.ts` is validated. The reconstruction ensures dedup runs on every import path and implements a re-processing route (re-parse + re-store + update `geoKey`) for the existing Dancor import (the one ingested before dedupBuffers was implemented, identifiable in `bim_imports` by its `createdAt` timestamp from 2026-08-30 and the absence of the `dedupApplied` flag) and any future imports made before the reconstruction is complete.

**7. Mandatory items from the "not implemented" list.** SuperTokens integration, `assertPermission` checks, soft delete, DTO + schema validation, i18n, `@workspace/ui`, RTK Query, Swagger, Atlas database-scoped grants, and rate limiting on the upload endpoint are all required in the first production increment. None of these were learned in the POC — they are house conventions that must be applied.

**8. IPC exit discipline.** Every child process that sends a result over IPC must use `process.send!(result, () => process.exit(0))`, not the two-statement form. This is a silent data-loss bug at scale and must be enforced in code review.

## Related

- `docs/plano-produto-dinamico.md` — POC plan with full session log, ADRs 001-003, and progress table
- `docs/sessoes/S4.1-medicao-comparativa.md` — measurement session with raw numbers
- `docs/sessoes/S4.2-documento-de-aprendizados.md` — session record for this documentation pass
