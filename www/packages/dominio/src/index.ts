/**
 * @bim/dominio — o que `apps/api` (catálogo: leitura + edição) e `apps/ingestao`
 * (importação: pipeline Python + Chromium) compartilham. Criado na E3 de
 * docs/arquitetura-www-servico-de-ingestao.md (2026-09-05); até então tudo vivia
 * em apps/api/src.
 *
 * Aqui só entra o que os DOIS lados precisam para falar do mesmo dado: schemas,
 * storage, contrato `{pos,col,idx}`, ETag, validação, nome de upload. Regra de
 * negócio fica em cada app.
 */
export * from './schemas/companies.schema';
export * from './schemas/bim-catalogs.schema';
export * from './schemas/bim-products.schema';
export * from './schemas/bim-imports.schema';
export * from './storage-path';
export * from './geo-buffers';
export * from './asset-cache';
export * from './validation';
export * from './upload';
export * from './mongo-pronto.guard';
export * from './remocao';
export * from './geometry-store/geometry-store.interface';
export * from './geometry-store/disk-geometry-store';
export * from './geometry-store/geometry-store.module';
