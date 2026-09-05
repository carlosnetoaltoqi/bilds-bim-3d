import { Injectable, BadRequestException, NotFoundException, Logger } from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Inject } from '@nestjs/common';
import { Model } from 'mongoose';
import { fork } from 'child_process';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import * as crypto from 'node:crypto';

import { BimImport, BimImportDocument, ImportStatus } from '../bim-imports/bim-imports.schema';
import { BimCatalog, BimCatalogDocument } from '../bim-catalogs/bim-catalogs.schema';
import { BimProduct, BimProductDocument } from '../bim-products/bim-products.schema';
import { Company, CompanyDocument } from '../companies/companies.schema';
import { IGeometryStore } from '../geometry-store/geometry-store.interface';
import { WorkerResult, ProductResult, CatalogMeta } from './parse-worker';
import { ThumbWorkerInput } from './thumb-worker';
import { aguardarResultado, aguardarMiniaturas, descreveResumo, ResumoMiniaturas } from './worker-ipc';
import { storagePath } from '../common/storage-path';
import { FILA_IMPORTACOES, Fila } from '../common/fila';

const WORKER_TIMEOUT_MS = 5 * 60 * 1000; // 5 min
/** thumb-worker sem mensagem por este tempo = Chromium travado: mata e registra (I15). */
const THUMB_OCIOSO_MS = 2 * 60 * 1000;

@Injectable()
export class ImportacoesService {
  private readonly logger = new Logger(ImportacoesService.name);

  constructor(
    @InjectModel(BimImport.name) private readonly importModel: Model<BimImportDocument>,
    @InjectModel(BimCatalog.name) private readonly catalogModel: Model<BimCatalogDocument>,
    @InjectModel(BimProduct.name) private readonly productModel: Model<BimProductDocument>,
    @InjectModel(Company.name) private readonly companyModel: Model<CompanyDocument>,
    @Inject('GEOMETRY_STORE') private readonly store: IGeometryStore,
    @Inject(FILA_IMPORTACOES) private readonly fila: Fila,
  ) {}

  async findById(importId: string) {
    const imp = await this.importModel.findById(importId).lean().exec();
    if (!imp) throw new NotFoundException('importação não encontrada');
    return imp;
  }

  /** Empresa por `customUrl`; vazio = a primeira cadastrada (sem auth não há "minha empresa"). */
  private async empresaDe(customUrl?: string) {
    return customUrl
      ? this.companyModel.findOne({ customUrl }).lean().exec()
      : this.companyModel.findOne().sort({ createdAt: 1 }).lean().exec();
  }

  async findLatest(empresa?: string) {
    const company = await this.empresaDe(empresa);
    if (!company) return null;
    const imp = await this.importModel
      .findOne({ companyId: company._id })
      .sort({ createdAt: -1 })
      .lean()
      .exec();
    if (!imp) return null;
    let catalogSlug: string | null = null;
    if (imp.catalogId) {
      const cat = await this.catalogModel.findById(imp.catalogId).select('slug').lean().exec();
      catalogSlug = cat?.slug ?? null;
    }
    return {
      importId: imp._id,
      status: imp.status,
      productCount: imp.productCount ?? null,
      error: imp.error ?? null,
      note: (imp as any).note ?? null,
      catalogId: imp.catalogId ?? null,
      catalogSlug,
      empresa: company.customUrl,
      createdAt: imp.createdAt,
      updatedAt: (imp as any).updatedAt ?? null,
    };
  }

  // filePath: caminho em disco escrito pelo multer diskStorage (evita buffer em RAM)
  async create(empresa: string | undefined, filePath: string, fileSize: number, fileName: string) {
    const sizeMb = (fileSize / 1024 / 1024).toFixed(1);
    this.logger.log(`upload recebido — ${fileName} (${sizeMb} MB) empresa=${empresa ?? '(primeira)'}`);

    const company = await this.empresaDe(empresa);
    if (!company) {
      throw new BadRequestException(empresa ? `empresa "${empresa}" não encontrada` : 'nenhuma empresa cadastrada — crie uma em /empresa/criar');
    }

    const importId = crypto.randomUUID();
    await this.importModel.create({
      _id: importId,
      companyId: company._id,
      status: 'recebido' as ImportStatus,
      fileName,
    });

    this.logger.log(`import ${importId} criado — disparando processamento`);
    // Uma importação por vez (I11): as demais esperam em `recebido` com a posição no `note`.
    // processAsync registra as falhas no documento; se nem isso conseguir, fica no log.
    this.fila
      .executar(importId, () => this.processAsync(importId, filePath, company._id as string), (naFrente) => {
        if (naFrente > 0) {
          this.logger.log(`[${importId.slice(0, 8)}] na fila — ${naFrente} à frente`);
          this.importModel.findByIdAndUpdate(importId, { note: `na fila — ${naFrente} importação(ões) à frente`, updatedAt: new Date() })
            .exec().catch(() => undefined);
        }
      })
      .catch((e: any) => this.logger.error(`[${importId.slice(0, 8)}] processAsync escapou — ${e?.message ?? e}`));

    return { importId, status: 'recebido' };
  }

  private async processAsync(
    importId: string,
    aqPath: string,
    companyId: string,
  ) {
    const t0 = Date.now();
    const lap = (label: string) => this.logger.log(`[${importId.slice(0, 8)}] ${label} — +${((Date.now() - t0) / 1000).toFixed(1)}s`);

    const setStatus = (status: ImportStatus, extra?: Partial<Record<keyof BimImport, unknown>>) =>
      this.importModel.findByIdAndUpdate(importId, {
        status,
        updatedAt: new Date(),
        ...extra,
      });

    // As miniaturas rodam DEPOIS do try/catch, ainda dentro da vaga da fila (S7.13): assim dois
    // uploads nunca têm dois Chromiums ao mesmo tempo, e uma falha nelas não vira `falhou`.
    let paraMiniaturas: Array<{ productId: string; geoKey: string }> | null = null;

    try {
      // `note: null` apaga o "na fila — N à frente" que a espera escreveu (S7.13)
      await setStatus('parseando', { note: null });
      lap('→ parseando (worker fork iniciado)');

      const result = await this.runWorker(importId, aqPath);
      lap(`worker retornou — status=${result.status} produtos=${result.productCount ?? 0}`);

      if (result.status === 'vazio') {
        await setStatus('vazio', { productCount: 0 });
        lap('→ vazio (sem geometrias)');
        return;
      }

      if (result.status === 'error') {
        throw new Error(result.error ?? 'erro desconhecido no parse');
      }

      // status: 'ok'
      const { products, catalogMeta } = result as { products: ProductResult[]; catalogMeta: CatalogMeta };

      await setStatus('gravando');
      lap(`→ gravando — ${products.length} produtos para MongoDB`);

      // Upsert catalog (create or replace existing)
      const existingCatalog = await this.catalogModel
        .findOne({ companyId, slug: catalogMeta.slug })
        .lean()
        .exec();

      let catalogId: string;
      let prevImportId: string | null = null;

      if (existingCatalog) {
        // Find old import to track
        const oldProducts = await this.productModel
          .find({ catalogId: existingCatalog._id })
          .distinct('importId')
          .exec();
        prevImportId = oldProducts[0] ?? null;

        await this.catalogModel.findByIdAndUpdate(existingCatalog._id, {
          title: catalogMeta.titulo,
          manufacturer: catalogMeta.fabricante,
          layout: catalogMeta.layout,
          filters: catalogMeta.filters,
          productCount: products.length,
        });
        catalogId = existingCatalog._id;
      } else {
        catalogId = crypto.randomUUID();
        await this.catalogModel.create({
          _id: catalogId,
          companyId,
          slug: catalogMeta.slug,
          title: catalogMeta.titulo,
          manufacturer: catalogMeta.fabricante,
          layout: catalogMeta.layout,
          filters: catalogMeta.filters,
          productCount: products.length,
        });
      }

      lap(`catálogo upsert concluído — catalogId=${catalogId} prevImport=${prevImportId ?? 'nenhum'}`);

      // Insert new products
      const productDocs = products.map((p) => ({
        _id: crypto.randomUUID(),
        catalogId,
        importId,
        id: p.id,
        nome: p.nome,
        serie: p.serie,
        specs: p.specs,
        curva: p.curva,
        potencia: p.potencia,
        conexoes: null,
        geoKey: p.geoKey,
        thumbKey: null,
      }));
      await this.productModel.insertMany(productDocs);
      lap(`insertMany concluído — ${productDocs.length} produtos`);

      // Clean up old import's products + files
      let note: string | undefined;
      if (prevImportId) {
        const deleted = await this.productModel.deleteMany({
          catalogId,
          importId: { $ne: importId },
        });
        await this.store.deleteByPrefix(`geo/${prevImportId}`).catch((e: any) =>
          this.logger.warn(`[${importId.slice(0, 8)}] não removeu geo/${prevImportId} do import anterior — ${e?.message ?? e}`),
        );
        note = `Substituiu catálogo existente (import anterior: ${prevImportId}, ${deleted.deletedCount} produtos removidos)`;
      }

      await this.importModel.findByIdAndUpdate(importId, {
        status: 'publicado' as ImportStatus,
        catalogId,
        productCount: products.length,
        updatedAt: new Date(),
        ...(note ? { note } : {}),
      });

      lap(`→ publicado — total ${((Date.now() - t0) / 1000).toFixed(1)}s`);

      // Miniaturas não mudam o status do import (S2.4), mas o resultado — inclusive cada
      // falha — vai para o log e para o documento (I15). Rodam abaixo, fora do try.
      paraMiniaturas = productDocs.map((p) => ({ productId: p._id, geoKey: p.geoKey! }));
    } catch (err: any) {
      // Limpeza best-effort do que o worker gravou — falha aqui é logada, não escondida
      await this.store.deleteByPrefix(`geo/${importId}`).catch((e: any) =>
        this.logger.warn(`[${importId.slice(0, 8)}] limpeza de geo/${importId} falhou — ${e?.message ?? e}`),
      );
      await this.productModel.deleteMany({ importId }).catch((e: any) =>
        this.logger.warn(`[${importId.slice(0, 8)}] limpeza de produtos falhou — ${e?.message ?? e}`),
      );

      this.logger.error(`[${importId.slice(0, 8)}] FALHOU — ${err.message} — +${((Date.now() - t0) / 1000).toFixed(1)}s`);
      await setStatus('falhou', { error: err.message ?? String(err) });
    } finally {
      await fs.unlink(aqPath).catch(() => {});
    }

    // Só agora a fila libera a vaga: quem espera vê "na fila" até o Chromium deste import fechar.
    if (paraMiniaturas) await this.gerarMiniaturas(importId, paraMiniaturas); // nunca rejeita
  }

  private runWorker(importId: string, aqPath: string): Promise<WorkerResult> {
    const workerPath = path.resolve(__dirname, 'parse-worker.ts');
    const child = fork(workerPath, [], {
      execArgv: [
        '--require',
        'ts-node/register/transpile-only',
        '--require',
        'reflect-metadata',
      ],
      env: { ...process.env },
      silent: false,
    });
    // Sair com 0 sem ter mandado o resultado também é erro — antes prendia a promise até o timeout (I15)
    const resultado = aguardarResultado<WorkerResult>(child, 'parse-worker', WORKER_TIMEOUT_MS);
    child.send({ aqPath, importId });
    return resultado;
  }

  /**
   * Gera as miniaturas de um import e **registra o resultado** no documento do import
   * (`thumbCount`, `thumbFailed`, `thumbError`, uma linha no `note`) e no log. Nunca
   * rejeita — é o que os chamadores disparam em segundo plano. Público desde a POC de
   * edição: o import de STEP/IFC usa o mesmo worker.
   */
  async gerarMiniaturas(
    importId: string,
    products: Array<{ productId: string; geoKey: string }>,
  ): Promise<ResumoMiniaturas | null> {
    const tag = `[${importId.slice(0, 8)}]`;
    let resumo: ResumoMiniaturas | null = null;
    let erro: string | null = null;
    try {
      resumo = await this.spawnThumbWorker(importId, products);
    } catch (err: any) {
      erro = err?.message ?? String(err);
      resumo = err?.resumo ?? null;
      this.logger.error(`${tag} ${erro}`);
    }
    const linha = erro ?? descreveResumo(resumo!);
    if (!erro && resumo!.falhas.length) this.logger.warn(`${tag} ${linha}`);
    try {
      const imp = await this.importModel.findById(importId).select('note').lean().exec();
      const note = imp?.note ? `${imp.note} — ${linha}` : linha;
      await this.importModel.findByIdAndUpdate(importId, {
        note,
        thumbCount: resumo?.geradas ?? 0,
        thumbFailed: resumo ? resumo.falhas.length : products.length,
        ...(erro ? { thumbError: erro } : {}),
        updatedAt: new Date(),
      }).exec();
    } catch (e: any) {
      this.logger.error(`${tag} não registrou o resultado das miniaturas no import — ${e?.message ?? e}`);
    }
    return resumo;
  }

  /**
   * Regera a miniatura de UM produto depois que a geometria mudou (PUT/restaurar —
   * I14). Mesma chave `thumbs/<importId>/<productId>.webp`, bytes novos: o ETag por
   * tamanho+mtime (`asset-cache.ts`) faz o browser revalidar. Registra no produto
   * `thumbAtualizadaEm` ou `thumbErro`; nunca rejeita.
   */
  async regerarMiniatura(productId: string, importId: string, geoKey: string): Promise<ResumoMiniaturas | null> {
    const tag = `[${productId.slice(0, 8)}]`;
    let resumo: ResumoMiniaturas | null = null;
    let erro: string | null = null;
    try {
      resumo = await this.spawnThumbWorker(importId, [{ productId, geoKey }]);
      if (resumo.falhas.length) erro = resumo.falhas[0].message;
    } catch (err: any) {
      erro = err?.message ?? String(err);
      resumo = err?.resumo ?? null;
    }
    if (erro) this.logger.error(`${tag} miniatura NÃO regerada após edição — ${erro}`);
    else this.logger.log(`${tag} miniatura regerada após edição`);
    try {
      await this.productModel.findByIdAndUpdate(productId, erro
        ? { thumbErro: erro }
        : { thumbAtualizadaEm: new Date(), thumbErro: null }).exec();
    } catch (e: any) {
      this.logger.error(`${tag} não registrou o resultado da miniatura no produto — ${e?.message ?? e}`);
    }
    return resumo;
  }

  /**
   * Fork do thumb-worker. Resolve com o resumo (geradas + cada falha por produto);
   * rejeita se o filho sair antes do `done`, se ficar ocioso ou se o processo falhar.
   * Use `gerarMiniaturas` a menos que queira tratar a rejeição você mesmo.
   */
  spawnThumbWorker(
    importId: string,
    products: Array<{ productId: string; geoKey: string }>,
  ): Promise<ResumoMiniaturas> {
    const tag = `[${importId.slice(0, 8)}]`;
    const workerPath = path.resolve(__dirname, 'thumb-worker.ts');
    const child = fork(workerPath, [], {
      execArgv: [
        '--require',
        'ts-node/register/transpile-only',
        '--require',
        'reflect-metadata',
      ],
      env: { ...process.env },
      silent: false,
    });

    const tThumb = Date.now();
    let thumbCount = 0;
    this.logger.log(`${tag} thumb-worker iniciado — ${products.length} produtos`);

    const resultado = aguardarMiniaturas(
      child,
      products.length,
      {
        onMiniatura: async (productId, thumbKey) => {
          // se o update falhar, o worker-ipc conta como falha do produto
          await this.productModel.findByIdAndUpdate(productId, { thumbKey }).exec();
          thumbCount++;
          if (thumbCount === 1 || thumbCount % 50 === 0) {
            this.logger.log(`${tag} thumbs: ${thumbCount}/${products.length} — +${((Date.now() - tThumb) / 1000).toFixed(1)}s`);
          }
        },
        onFalha: (productId, message) => this.logger.warn(`${tag} miniatura falhou — ${productId}: ${message}`),
      },
      THUMB_OCIOSO_MS,
    ).then((resumo) => {
      this.logger.log(`${tag} thumbs concluídas — ${descreveResumo(resumo)} em ${((Date.now() - tThumb) / 1000).toFixed(1)}s`);
      return resumo;
    });

    const input: ThumbWorkerInput = { products, storagePath: storagePath(), importId };
    child.send(input);
    return resultado;
  }
}
