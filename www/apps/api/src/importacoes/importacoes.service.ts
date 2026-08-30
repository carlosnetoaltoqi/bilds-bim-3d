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
import { ThumbWorkerInput, ThumbWorkerMessage } from './thumb-worker';

const WORKER_TIMEOUT_MS = 5 * 60 * 1000; // 5 min

@Injectable()
export class ImportacoesService {
  private readonly logger = new Logger(ImportacoesService.name);

  constructor(
    @InjectModel(BimImport.name) private readonly importModel: Model<BimImportDocument>,
    @InjectModel(BimCatalog.name) private readonly catalogModel: Model<BimCatalogDocument>,
    @InjectModel(BimProduct.name) private readonly productModel: Model<BimProductDocument>,
    @InjectModel(Company.name) private readonly companyModel: Model<CompanyDocument>,
    @Inject('GEOMETRY_STORE') private readonly store: IGeometryStore,
  ) {}

  async findById(importId: string) {
    const imp = await this.importModel.findById(importId).lean().exec();
    if (!imp) throw new NotFoundException('importação não encontrada');
    return imp;
  }

  async findByIdAndVerifyOwner(importId: string, ownerId: string) {
    const imp = await this.importModel.findById(importId).lean().exec();
    if (!imp) throw new NotFoundException('importação não encontrada');
    const company = await this.companyModel.findById(imp.companyId).lean().exec();
    if (!company || company.ownerId !== ownerId) throw new NotFoundException('importação não encontrada');
    return imp;
  }

  async findLatestByOwnerId(ownerId: string) {
    const company = await this.companyModel.findOne({ ownerId }).lean().exec();
    if (!company) return null;
    const imp = await this.importModel
      .findOne({ companyId: company._id })
      .sort({ createdAt: -1 })
      .lean()
      .exec();
    if (!imp) return null;
    return {
      importId: imp._id,
      status: imp.status,
      productCount: imp.productCount ?? null,
      error: imp.error ?? null,
      note: (imp as any).note ?? null,
      catalogId: imp.catalogId ?? null,
      createdAt: imp.createdAt,
      updatedAt: (imp as any).updatedAt ?? null,
    };
  }

  // filePath: caminho em disco escrito pelo multer diskStorage (evita buffer em RAM)
  async create(ownerId: string, filePath: string, fileSize: number, fileName: string) {
    const sizeMb = (fileSize / 1024 / 1024).toFixed(1);
    this.logger.log(`upload recebido — ${fileName} (${sizeMb} MB) owner=${ownerId}`);

    const company = await this.companyModel.findOne({ ownerId }).lean().exec();
    if (!company) throw new BadRequestException('empresa não encontrada para este usuário');

    const importId = crypto.randomUUID();
    await this.importModel.create({
      _id: importId,
      companyId: company._id,
      status: 'recebido' as ImportStatus,
      fileName,
    });

    this.logger.log(`import ${importId} criado — disparando processamento`);
    this.processAsync(importId, filePath, company._id as string).catch(() => {
      /* errors are recorded in the import document */
    });

    return { importId, status: 'recebido' };
  }

  private async processAsync(
    importId: string,
    aqPath: string,
    companyId: string,
  ) {
    const t0 = Date.now();
    const lap = (label: string) => this.logger.log(`[${importId.slice(0, 8)}] ${label} — +${((Date.now() - t0) / 1000).toFixed(1)}s`);

    const setStatus = (status: ImportStatus, extra?: Partial<BimImport>) =>
      this.importModel.findByIdAndUpdate(importId, {
        status,
        updatedAt: new Date(),
        ...extra,
      });

    try {
      await setStatus('parseando');
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
        try {
          await this.store.deleteByPrefix(`geo/${prevImportId}`);
        } catch {
          /* best-effort */
        }
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

      // Dispara geração de miniaturas fire-and-forget (S2.4)
      // Falhas não mudam o status do import — miniaturas são opcionais
      this.spawnThumbWorker(importId, productDocs.map((p) => ({ productId: p._id, geoKey: p.geoKey! }))).catch(
        () => { /* silencioso */ },
      );
    } catch (err: any) {
      // Cleanup files written by worker
      try {
        await this.store.deleteByPrefix(`geo/${importId}`);
      } catch {
        /* ignore */
      }
      // Remove any products inserted
      await this.productModel.deleteMany({ importId }).catch(() => {});

      this.logger.error(`[${importId.slice(0, 8)}] FALHOU — ${err.message} — +${((Date.now() - t0) / 1000).toFixed(1)}s`);
      await setStatus('falhou', { error: err.message ?? String(err) });
    } finally {
      await fs.unlink(aqPath).catch(() => {});
    }
  }

  private runWorker(importId: string, aqPath: string): Promise<WorkerResult> {
    return new Promise((resolve, reject) => {
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

      const timer = setTimeout(() => {
        child.kill('SIGKILL');
        reject(new Error(`parse-worker timeout após ${WORKER_TIMEOUT_MS / 1000}s`));
      }, WORKER_TIMEOUT_MS);

      child.on('message', (msg: WorkerResult) => {
        clearTimeout(timer);
        resolve(msg);
      });

      child.on('error', (err) => {
        clearTimeout(timer);
        reject(err);
      });

      child.on('exit', (code) => {
        clearTimeout(timer);
        if (code !== 0) {
          reject(new Error(`parse-worker encerrou com código ${code}`));
        }
      });

      child.send({ aqPath, importId });
    });
  }

  private spawnThumbWorker(
    importId: string,
    products: Array<{ productId: string; geoKey: string }>,
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      const workerPath = path.resolve(__dirname, 'thumb-worker.ts');
      const storagePath = path.resolve(
        process.env.STORAGE_PATH ?? path.join(process.cwd(), 'storage'),
      );
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
      this.logger.log(`[${importId.slice(0, 8)}] thumb-worker iniciado — ${products.length} produtos`);

      child.on('message', (msg: ThumbWorkerMessage) => {
        if (msg.type === 'thumb') {
          thumbCount++;
          this.productModel
            .findByIdAndUpdate(msg.productId, { thumbKey: msg.thumbKey })
            .exec()
            .catch(() => {});
          if (thumbCount === 1 || thumbCount % 50 === 0) {
            this.logger.log(`[${importId.slice(0, 8)}] thumbs: ${thumbCount}/${products.length} — +${((Date.now() - tThumb) / 1000).toFixed(1)}s`);
          }
        } else if (msg.type === 'done') {
          this.logger.log(`[${importId.slice(0, 8)}] thumbs concluídas — ${thumbCount} em ${((Date.now() - tThumb) / 1000).toFixed(1)}s`);
          resolve();
        }
      });

      child.on('error', reject);
      child.on('exit', (code) => {
        if (code !== 0) reject(new Error(`thumb-worker encerrou com código ${code}`));
        else resolve();
      });

      const input: ThumbWorkerInput = { products, storagePath, importId };
      child.send(input);
    });
  }

}
