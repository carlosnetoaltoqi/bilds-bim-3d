/**
 * remocao.ts — apagar em cada nível (2026-09-05, S7.15): empresa → catálogos → produtos, e
 * importação. Funções puras sobre os modelos e o store (sem Nest), compartilhadas pela API de
 * catálogo (empresa, catálogo, peça) e pelo serviço de ingestão (importação).
 *
 * O que cada remoção leva junto:
 *
 *   produto      o documento; o arquivo de geometria SÓ se nenhum outro produto o usa (o pipeline
 *                grava uma geometria por simbologia — A5); a cópia copy-on-write e o `.orig.json`
 *                sempre (são só dele); a miniatura só se nenhum outro produto aponta para ela;
 *                depois recalcula `productCount`/`filters` do catálogo
 *   catálogo     todos os produtos, `geo/<importId>` e `thumbs/<importId>` de cada import que
 *                alimentou o catálogo, os documentos de import desse catálogo, o catálogo
 *   empresa      cada catálogo (acima), os imports que sobraram (falhou/vazio) e o storage deles,
 *                o logo, a empresa
 *   importação   recusada se ainda está em andamento (`recebido`/`parseando`/`gravando`); senão os
 *                produtos dela, `geo/<importId>`, `thumbs/<importId>`, o documento; o catálogo fica
 *                (recontado — pode ficar com 0 produtos; apagá-lo é outra decisão)
 */
import { IGeometryStore } from './geometry-store/geometry-store.interface';
import { originalKeyFor } from '@bim/base';

/** O mínimo dos modelos Mongoose que usamos — para os harnesses passarem falsos. */
export interface ConsultaMinima<T> {
  lean(): ConsultaMinima<T>;
  select(campos: string): ConsultaMinima<T>;
  exec(): Promise<T>;
}
export interface ModeloMinimo<T = any> {
  findById(id: string): ConsultaMinima<T | null>;
  findOne(filtro: Record<string, unknown>): ConsultaMinima<T | null>;
  find(filtro: Record<string, unknown>): ConsultaMinima<T[]> & { distinct(campo: string): { exec(): Promise<unknown[]> } };
  countDocuments(filtro: Record<string, unknown>): { exec(): Promise<number> };
  deleteOne(filtro: Record<string, unknown>): { exec(): Promise<unknown> };
  deleteMany(filtro: Record<string, unknown>): { exec(): Promise<{ deletedCount?: number }> };
  updateOne(filtro: Record<string, unknown>, upd: Record<string, unknown>): { exec(): Promise<unknown> };
}
export interface Modelos {
  companies: ModeloMinimo;
  catalogs: ModeloMinimo;
  products: ModeloMinimo;
  imports: ModeloMinimo;
}

export const STATUS_EM_ANDAMENTO: readonly string[] = ['recebido', 'parseando', 'gravando'];

export class NaoEncontrado extends Error {
  constructor(message: string) { super(message); this.name = 'NaoEncontrado'; }
}
export class ImportacaoEmAndamento extends Error {
  constructor(message: string) { super(message); this.name = 'ImportacaoEmAndamento'; }
}

export interface Removido {
  arquivos: string[];       // chaves apagadas do store (ou prefixos, com `/…`)
  produtos: number;
  catalogos: number;
  imports: number;
  avisos: string[];         // falhas de storage que não impediram a remoção
}

const vazio = (): Removido => ({ arquivos: [], produtos: 0, catalogos: 0, imports: 0, avisos: [] });

async function apagarChave(store: IGeometryStore, chave: string, r: Removido) {
  try {
    await store.delete(chave);
    r.arquivos.push(chave);
  } catch (e: any) {
    if (e?.code !== 'ENOENT') r.avisos.push(`não removeu ${chave} — ${e?.message ?? e}`);
  }
}

async function apagarPrefixo(store: IGeometryStore, prefixo: string, r: Removido) {
  try {
    await store.deleteByPrefix(prefixo);
    r.arquivos.push(`${prefixo}/…`);
  } catch (e: any) {
    r.avisos.push(`não removeu ${prefixo} — ${e?.message ?? e}`);
  }
}

/** `productCount` e `filters` (séries distintas) do catálogo, depois de mexer nos produtos. */
export async function recomputarCatalogo(m: Modelos, catalogId: string): Promise<void> {
  const series = (await m.products.find({ catalogId }).distinct('serie').exec()) as string[];
  const count = await m.products.countDocuments({ catalogId }).exec();
  await m.catalogs.updateOne({ _id: catalogId }, { $set: { productCount: count, filters: series.filter(Boolean) } }).exec();
}

export async function apagarProduto(m: Modelos, store: IGeometryStore, productId: string): Promise<Removido> {
  const p = await m.products.findById(productId).lean().exec();
  if (!p) throw new NaoEncontrado('produto não encontrado');
  const r = vazio();
  if (p.geoKeyCompartilhada) {
    // copy-on-write: o arquivo em geoKey é só dele; o compartilhado fica com os outros
    await apagarChave(store, p.geoKey, r);
  } else {
    const outros = await m.products.countDocuments({ geoKey: p.geoKey, _id: { $ne: productId } }).exec();
    if (outros === 0) {
      await apagarChave(store, p.geoKey, r);
      await apagarChave(store, originalKeyFor(p.geoKey), r);
    }
  }
  if (p.thumbKey) {
    const outros = await m.products.countDocuments({ thumbKey: p.thumbKey, _id: { $ne: productId } }).exec();
    if (outros === 0) await apagarChave(store, p.thumbKey, r);
  }
  await m.products.deleteOne({ _id: productId }).exec();
  r.produtos = 1;
  await recomputarCatalogo(m, p.catalogId);
  return r;
}

export async function apagarCatalogo(m: Modelos, store: IGeometryStore, catalogId: string): Promise<Removido> {
  const cat = await m.catalogs.findById(catalogId).lean().exec();
  if (!cat) throw new NaoEncontrado('catálogo não encontrado');
  const r = vazio();
  const importIds = new Set<string>(
    (await m.products.find({ catalogId }).distinct('importId').exec()) as string[],
  );
  for (const imp of await m.imports.find({ catalogId }).select('_id').lean().exec()) importIds.add(String(imp._id));
  const del = await m.products.deleteMany({ catalogId }).exec();
  r.produtos = del.deletedCount ?? 0;
  for (const id of importIds) {
    await apagarPrefixo(store, `geo/${id}`, r);
    await apagarPrefixo(store, `thumbs/${id}`, r);
    await apagarPrefixo(store, `catallog/${id}`, r);   // arquivos baixados do catálogo web de um plugin de CAD
  }
  const imps = await m.imports.deleteMany({ catalogId }).exec();
  r.imports = imps.deletedCount ?? 0;
  await m.catalogs.deleteOne({ _id: catalogId }).exec();
  r.catalogos = 1;
  return r;
}

export async function apagarEmpresa(m: Modelos, store: IGeometryStore, companyId: string): Promise<Removido> {
  const c = await m.companies.findById(companyId).lean().exec();
  if (!c) throw new NaoEncontrado('empresa não encontrada');
  const r = vazio();
  for (const cat of await m.catalogs.find({ companyId }).select('_id').lean().exec()) {
    const parcial = await apagarCatalogo(m, store, String(cat._id));
    r.arquivos.push(...parcial.arquivos); r.avisos.push(...parcial.avisos);
    r.produtos += parcial.produtos; r.catalogos += parcial.catalogos; r.imports += parcial.imports;
  }
  // imports sem catálogo (falhou, vazio, ou em andamento) e o storage que possam ter deixado
  for (const imp of await m.imports.find({ companyId }).select('_id').lean().exec()) {
    await apagarPrefixo(store, `geo/${imp._id}`, r);
    await apagarPrefixo(store, `thumbs/${imp._id}`, r);
    await apagarPrefixo(store, `catallog/${imp._id}`, r);
  }
  const imps = await m.imports.deleteMany({ companyId }).exec();
  r.imports += imps.deletedCount ?? 0;
  if (c.logoKey) await apagarChave(store, c.logoKey, r);
  await m.companies.deleteOne({ _id: companyId }).exec();
  return r;
}

export async function apagarImportacao(m: Modelos, store: IGeometryStore, importId: string): Promise<Removido> {
  const imp = await m.imports.findById(importId).lean().exec();
  if (!imp) throw new NaoEncontrado('importação não encontrada');
  if (STATUS_EM_ANDAMENTO.includes(imp.status)) {
    throw new ImportacaoEmAndamento(`importação em '${imp.status}' — espere terminar (ou reinicie o serviço, que a marca como falhou) antes de apagar`);
  }
  const r = vazio();
  const del = await m.products.deleteMany({ importId }).exec();
  r.produtos = del.deletedCount ?? 0;
  await apagarPrefixo(store, `geo/${importId}`, r);
  await apagarPrefixo(store, `thumbs/${importId}`, r);
  await apagarPrefixo(store, `catallog/${importId}`, r);
  await m.imports.deleteOne({ _id: importId }).exec();
  r.imports = 1;
  if (imp.catalogId) {
    const cat = await m.catalogs.findById(imp.catalogId).lean().exec();
    if (cat) await recomputarCatalogo(m, imp.catalogId);
  }
  return r;
}
