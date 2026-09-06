/**
 * @bim/dominio — o que os serviços COM DADOS compartilham (criador de catálogos, API de catálogo,
 * editor de peças — docs/arquitetura.md §2). Criado na E3 (2026-09-05) como packages/dominio;
 * pacote compilado desde a F2 da S8 (2026-09-06). Infraestrutura sem dado de negócio é do @bim/base.
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
export * from './asset-cache';
export * from './mongo-pronto.guard';
export * from './remocao';
export * from './geometry-store/geometry-store.interface';
export * from './geometry-store/disk-geometry-store';
export * from './geometry-store/geometry-store.module';
