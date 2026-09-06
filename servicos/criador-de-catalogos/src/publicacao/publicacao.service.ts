import { Inject, Injectable, Logger } from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import * as crypto from 'node:crypto';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import { BimCatalog, BimCatalogDocument, BimImport, BimImportDocument, BimProduct, BimProductDocument, IGeometryStore, ImportStatus, storagePath } from '@bim/dominio';
import type { ProdutoPipeline, ResultadoCatalogo, StepGeo } from '@bim/base';
import { ImportarDto } from '../importacoes/importar.dto';
import { MiniaturasService } from '../miniaturas/miniaturas.service';
import { PipelineService } from '../pipeline/pipeline.service';
import { descreveDiag, slugify, stemDe } from './descricoes';

export interface ArquivoRecebido { path: string; size: number; fileName: string }
export type Empresa = { _id: string; customUrl: string };

/**
 * PublicacaoService — o que vira CATÁLOGO E PRODUTOS no banco (docs/arquitetura.md §5: o criador é o
 * dono de bim_catalogs/bim_products na publicação):
 *
 *   recebido → [fila] → parseando (biblioteca Python) → gravando (Mongo) → publicado | vazio | falhou
 *                                                                          └→ miniaturas, ainda na vaga da fila
 *
 *   processarAq / processarCatalogo   biblioteca .aq/.zip e catálogo web de plugin: a biblioteca grava uma
 *                                     geometria por simbologia em geo/<importId>/ e devolve o catálogo
 *                                     (contrato `catalogo`); upsert do catálogo, insertMany dos produtos,
 *                                     substituição do import anterior de mesmo slug, miniaturas.
 *   processarCad / publicarCad        uma peça CAD → um produto num catálogo "Peças STEP/IFC" da empresa.
 */
@Injectable()
export class PublicacaoService {
  private readonly logger = new Logger(PublicacaoService.name);

  constructor(
    @InjectModel(BimImport.name) private readonly importModel: Model<BimImportDocument>,
    @InjectModel(BimCatalog.name) private readonly catalogModel: Model<BimCatalogDocument>,
    @InjectModel(BimProduct.name) private readonly productModel: Model<BimProductDocument>,
    @Inject('GEOMETRY_STORE') private readonly store: IGeometryStore,
    private readonly pipeline: PipelineService,
    private readonly miniaturas: MiniaturasService,
  ) {}

  // ── biblioteca .aq / .zip ────────────────────────────────────────────────

  processarAq(importId: string, arquivo: ArquivoRecebido, company: Empresa) {
    return this.processarCatalogo(importId, company, {
      rotulo: 'catalogo_de_aq.py',
      produzir: (geoDir, onProgresso) => this.pipeline.catalogoDeAq({ aqPath: arquivo.path, geoDir, nomeOriginal: arquivo.fileName, onProgresso }),
      aoTerminar: () => fs.unlink(arquivo.path),
    });
  }

  /**
   * O caminho comum a tudo que vira um CATÁLOGO INTEIRO (biblioteca `.aq` e catálogo web de um
   * plugin): `produzir` roda o pipeline e devolve o JSON do `catalogo_de_aq.py`; daí em diante é
   * upsert do catálogo, produtos, limpeza do import anterior de mesmo slug e miniaturas.
   * `aoFalhar` limpa o que só este tipo criou (os downloads do plugin); `aoTerminar` roda sempre.
   */
  async processarCatalogo(importId: string, company: Empresa, o: {
    rotulo: string;
    produzir: (geoDir: string, onProgresso: (linha: string) => void) => Promise<ResultadoCatalogo>;
    aoTerminar: () => Promise<unknown>;
    aoFalhar?: () => Promise<unknown>;
    notaExtra?: (r: ResultadoCatalogo) => string | null;
  }) {
    const tag = `[${importId.slice(0, 8)}]`;
    const t0 = Date.now();
    const lap = (label: string) => this.logger.log(`${tag} ${label} — +${((Date.now() - t0) / 1000).toFixed(1)}s`);
    const setStatus = (status: ImportStatus, extra: Record<string, unknown> = {}) =>
      this.importModel.findByIdAndUpdate(importId, { status, updatedAt: new Date(), ...extra }).exec();
    const geoDir = path.join(storagePath(), 'geo', importId);

    // As miniaturas rodam DEPOIS do try/catch, ainda dentro da vaga da fila (S7.13)
    let paraMiniaturas: { geos: string[]; porStem: Map<string, string[]> } | null = null;

    try {
      // `note: null` apaga o "na fila — N à frente" que a espera escreveu
      await setStatus('parseando', { note: null });
      lap(`→ parseando (${o.rotulo})`);

      let ultimoProgresso = 0;
      const resultado = await o.produzir(geoDir, (linha) => {
        if (Date.now() - ultimoProgresso > 1000) {   // no máximo uma atualização por segundo no Mongo
          ultimoProgresso = Date.now();
          this.importModel.findByIdAndUpdate(importId, { note: linha, updatedAt: new Date() }).exec().catch(() => {});
        }
      });
      const { config, catalog, n_geometrias, diag } = resultado;
      lap(`pipeline retornou — ${catalog.produtos.length} produtos, ${n_geometrias} geometrias`);

      if (catalog.produtos.length === 0) {
        await this.store.deleteByPrefix(`geo/${importId}`).catch(() => {});
        await setStatus('vazio', { productCount: 0, diag, note: descreveDiag(diag) });
        lap('→ vazio (sem geometrias)');
        return;
      }

      await setStatus('gravando', { note: `${catalog.produtos.length} produtos — gravando no banco…` });

      // Upsert do catálogo (cria ou substitui o de mesmo slug na empresa)
      const existing = await this.catalogModel.findOne({ companyId: company._id, slug: config.slug }).lean().exec();
      let catalogId: string;
      let prevImportId: string | null = null;
      const meta = { title: config.titulo, manufacturer: config.fabricante, layout: config.layout, filters: catalog.filtros, productCount: catalog.produtos.length };
      if (existing) {
        const oldImports = await this.productModel.find({ catalogId: existing._id }).distinct('importId').exec();
        prevImportId = (oldImports[0] as string) ?? null;
        await this.catalogModel.findByIdAndUpdate(existing._id, meta).exec();
        catalogId = existing._id as string;
      } else {
        catalogId = crypto.randomUUID();
        await this.catalogModel.create({ _id: catalogId, companyId: company._id, slug: config.slug, ...meta });
      }
      lap(`catálogo ${existing ? 'substituído' : 'criado'} — ${catalogId} (import anterior: ${prevImportId ?? 'nenhum'})`);

      const productDocs = catalog.produtos.map((p: ProdutoPipeline) => ({
        _id: crypto.randomUUID(),
        catalogId,
        importId,
        id: p.id,
        nome: p.nome,
        serie: p.serie,
        specs: p.specs ?? {},
        curva: p.curva ?? null,
        potencia: p.potencia ?? null,
        conexoes: p.conexoes || null,
        geoKey: `geo/${importId}/${p.geo}`,
        geoKeyCompartilhada: null,
        thumbKey: null,
      }));
      await this.productModel.insertMany(productDocs);
      lap(`insertMany — ${productDocs.length} produtos`);

      let note = [descreveDiag(diag), o.notaExtra?.(resultado) ?? null].filter(Boolean).join(' · ');
      if (prevImportId) {
        const deleted = await this.productModel.deleteMany({ catalogId, importId: { $ne: importId } });
        for (const prefixo of [`geo/${prevImportId}`, `thumbs/${prevImportId}`, `catallog/${prevImportId}`]) {
          await this.store.deleteByPrefix(prefixo).catch((e: any) =>
            this.logger.warn(`${tag} não removeu ${prefixo} do import anterior — ${e?.message ?? e}`));
        }
        note = `${note ? note + ' — ' : ''}substituiu o catálogo existente (import anterior ${prevImportId}, ${deleted.deletedCount} produtos removidos)`;
      }

      await setStatus('publicado', { catalogId, productCount: productDocs.length, diag, note: note || null });
      lap(`→ publicado — total ${((Date.now() - t0) / 1000).toFixed(1)}s`);

      const porStem = new Map<string, string[]>();
      for (const d of productDocs) {
        const stem = stemDe(d.geoKey);
        if (!porStem.has(stem)) porStem.set(stem, []);
        porStem.get(stem)!.push(d._id);
      }
      paraMiniaturas = { geos: [...new Set(catalog.produtos.map((p) => p.geo))], porStem };
    } catch (err: any) {
      // Limpeza best-effort do que o pipeline gravou — falha aqui é logada, não escondida
      await this.store.deleteByPrefix(`geo/${importId}`).catch((e: any) =>
        this.logger.warn(`${tag} limpeza de geo/${importId} falhou — ${e?.message ?? e}`));
      await this.productModel.deleteMany({ importId }).catch((e: any) =>
        this.logger.warn(`${tag} limpeza de produtos falhou — ${e?.message ?? e}`));
      if (o.aoFalhar) {
        await o.aoFalhar().catch((e: any) => this.logger.warn(`${tag} limpeza específica falhou — ${e?.message ?? e}`));
      }
      const msg = (err?.message ?? String(err)).slice(0, 2000);
      this.logger.error(`${tag} FALHOU — ${msg} — +${((Date.now() - t0) / 1000).toFixed(1)}s`);
      await setStatus('falhou', { error: msg, note: `falhou após ${((Date.now() - t0) / 1000).toFixed(0)} s` });
    } finally {
      await o.aoTerminar().catch(() => {});
    }

    // Só agora a fila libera a vaga: quem espera vê "na fila" até o Chromium deste import fechar.
    if (paraMiniaturas) await this.miniaturas.gerarMiniaturas(importId, geoDir, paraMiniaturas.geos, paraMiniaturas.porStem); // nunca rejeita
  }

  // ── peça CAD (.stp / .ifc) ───────────────────────────────────────────────

  async processarCad(importId: string, arquivo: ArquivoRecebido, company: Empresa, body: ImportarDto) {
    const tag = `[${importId.slice(0, 8)}]`;
    const t0 = Date.now();
    const setStatus = (status: ImportStatus, extra: Record<string, unknown> = {}) =>
      this.importModel.findByIdAndUpdate(importId, { status, updatedAt: new Date(), ...extra }).exec();
    let paraMiniatura: { geoKey: string; productId: string } | null = null;
    try {
      await setStatus('parseando', { note: 'convertendo…' });
      let ultimoProgresso = 0;
      const geo = await this.pipeline.tesselar(arquivo.path, body.deflexao ?? 0.2, arquivo.fileName, (linha) => {
        if (Date.now() - ultimoProgresso > 1000) {
          ultimoProgresso = Date.now();
          this.importModel.findByIdAndUpdate(importId, { note: linha, updatedAt: new Date() }).exec().catch(() => {});
        }
      });
      await setStatus('gravando', { note: `${geo.idx.length / 3} triângulos convertidos em ${((Date.now() - t0) / 1000).toFixed(0)} s — gravando…` });
      const r = await this.publicarCad(importId, company, arquivo.fileName, body, geo);
      await setStatus('publicado', {
        catalogId: r.catalogId,
        productCount: 1,
        note: [
          `${geo.formato?.toUpperCase()} · ${geo.partes.length} ${geo.formato === 'ifc' ? 'produto(s)' : 'sólido(s)'} · ${geo.idx.length / 3} triângulos · ${((Date.now() - t0) / 1000).toFixed(0)} s`,
          geo.caminho ? `via ${geo.caminho}` : null,
          geo.aviso ?? null,
        ].filter(Boolean).join(' — '),
      });
      this.logger.log(`${tag} ${geo.formato?.toUpperCase()} importado — ${r.nome} → ${company.customUrl}/${r.slug} (produto ${r.productId}) em ${((Date.now() - t0) / 1000).toFixed(1)}s`);
      paraMiniatura = { geoKey: r.geoKey, productId: r.productId };
    } catch (err: any) {
      const msg = (err?.message ?? String(err)).slice(0, 2000);
      this.logger.error(`${tag} FALHOU — ${msg}`);
      await this.productModel.deleteMany({ importId }).catch((e: any) => this.logger.warn(`${tag} limpeza de produtos falhou — ${e?.message ?? e}`));
      await this.store.deleteByPrefix(`geo/${importId}`).catch((e: any) => this.logger.warn(`${tag} limpeza de geo/${importId} falhou — ${e?.message ?? e}`));
      await setStatus('falhou', { error: msg, note: `falhou após ${((Date.now() - t0) / 1000).toFixed(0)} s` });
    } finally {
      await fs.unlink(arquivo.path).catch(() => {});
    }
    if (paraMiniatura) {
      const geoAbs = path.join(storagePath(), paraMiniatura.geoKey);
      const porStem = new Map([[stemDe(paraMiniatura.geoKey), [paraMiniatura.productId]]]);
      await this.miniaturas.gerarMiniaturas(importId, path.dirname(geoAbs), [path.basename(geoAbs)], porStem);
    }
  }

  /** Catálogo "Peças STEP/IFC" (upsert por slug) + um produto + geometria no storage. */
  private async publicarCad(importId: string, company: Empresa, fileName: string, body: ImportarDto, geo: StepGeo) {
    const ehIfc = geo.formato === 'ifc';
    const fabricante = (body.fabricante ?? '').trim() || (ehIfc ? 'IFC' : 'STEP');
    const titulo = (body.catalogo ?? '').trim() || (ehIfc ? 'Peças IFC' : 'Peças STEP');
    const slug = slugify(titulo) || (ehIfc ? 'pecas-ifc' : 'pecas-step');
    const nome = (body.nome ?? '').trim() || path.basename(fileName).replace(/\.(stp|step|igs|iges|ifc)$/i, '');

    let catalog = await this.catalogModel.findOne({ companyId: company._id, slug }).lean().exec();
    if (!catalog) {
      const catalogId = crypto.randomUUID();
      await this.catalogModel.create({ _id: catalogId, companyId: company._id, slug, title: titulo, manufacturer: fabricante, layout: 'catalog-grid', filters: [], productCount: 0 });
      catalog = await this.catalogModel.findById(catalogId).lean().exec();
    }

    // id único dentro do catálogo (mesmo STEP importado duas vezes)
    const baseId = slugify(nome) || 'peca-cad';
    const existentes = await this.productModel.find({ catalogId: catalog!._id, id: new RegExp(`^${baseId}(-\\d+)?$`) }).select('id').lean().exec();
    const prodSlug = existentes.length ? `${baseId}-${existentes.length}` : baseId;
    const geoKey = `geo/${importId}/${prodSlug}.json`;
    await this.store.put(geoKey, Buffer.from(JSON.stringify({ pos: geo.pos, col: geo.col, idx: geo.idx })));

    const bb = geo.bbox_mm;
    const productId = crypto.randomUUID();
    await this.productModel.create({
      _id: productId,
      catalogId: catalog!._id,
      importId,
      id: prodSlug,
      nome,
      serie: fabricante,
      specs: ehIfc
        ? {
            Fonte: geo.fonte,
            Formato: 'IFC4 (ISO 10303-21)',
            'Unidade do arquivo': geo.unidade,
            'Escala aplicada': String(geo.escala_aplicada ?? 1),
            'Dimensões (mm)': `${bb[0].toFixed(1)} × ${bb[1].toFixed(1)} × ${bb[2].toFixed(1)}`,
            Produtos: String(geo.partes.length),
            Triângulos: String(geo.idx.length / 3),
            Cores: geo.caminho === 'ifcopenshell' ? 'por material (ifcopenshell)' : geo.cor_por_face ? 'por face (IFCINDEXEDCOLOURMAP)' : 'uniforme',
            Conversor: geo.caminho ?? 'parse_ifc',
            'Tamanho do arquivo (MB)': String(geo.tamanho_mb ?? ''),
          }
        : {
            Fonte: geo.fonte,
            Formato: geo.formato === 'iges' ? 'IGES (faces costuradas em sólido)' : 'STEP (ISO 10303-21)',
            'Unidade do arquivo': geo.unidade,
            'Dimensões (mm)': `${bb[0].toFixed(1)} × ${bb[1].toFixed(1)} × ${bb[2].toFixed(1)}`,
            Sólidos: String(geo.partes.length),
            Triângulos: String(geo.idx.length / 3),
            'Deflexão (mm)': String(geo.deflexao_mm),
            ...(geo.volume_cm3 != null ? { 'Volume (cm³)': geo.volume_cm3.toFixed(1) } : {}),
            ...(geo.arestas_livres ? { 'Arestas livres após costura': String(geo.arestas_livres) } : {}),
          },
      curva: null,
      potencia: null,
      conexoes: null,
      geoKey,
      geoKeyCompartilhada: null,
      thumbKey: null,
    });

    const series = (await this.productModel.find({ catalogId: catalog!._id }).distinct('serie').exec()) as string[];
    const count = await this.productModel.countDocuments({ catalogId: catalog!._id }).exec();
    await this.catalogModel.findByIdAndUpdate(catalog!._id, { productCount: count, filters: series.filter(Boolean) }).exec();

    return { productId, geoKey, slug, nome, catalogId: catalog!._id as string };
  }

}
