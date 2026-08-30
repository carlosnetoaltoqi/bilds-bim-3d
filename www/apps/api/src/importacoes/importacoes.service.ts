import { Injectable, BadRequestException, NotFoundException } from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Inject } from '@nestjs/common';
import { Model } from 'mongoose';
import { fork } from 'child_process';
import * as fs from 'node:fs/promises';
import * as fsSync from 'node:fs';
import * as path from 'node:path';
import * as os from 'node:os';
import * as crypto from 'node:crypto';

import { BimImport, BimImportDocument, ImportStatus } from '../bim-imports/bim-imports.schema';
import { BimCatalog, BimCatalogDocument } from '../bim-catalogs/bim-catalogs.schema';
import { BimProduct, BimProductDocument } from '../bim-products/bim-products.schema';
import { Company, CompanyDocument } from '../companies/companies.schema';
import { IGeometryStore } from '../geometry-store/geometry-store.interface';
import { WorkerResult, ProductResult, CatalogMeta } from './parse-worker';
import { ThumbWorkerInput, ThumbWorkerMessage } from './thumb-worker';

const MAX_FILE_BYTES = 300 * 1024 * 1024; // .aq raw SQLite (Dancor ~153 MB)
const MAX_ZIP_ENTRIES = 200;
const MAX_ZIP_UNCOMPRESSED = 500 * 1024 * 1024;
const WORKER_TIMEOUT_MS = 5 * 60 * 1000; // 5 min

const ZIP_SIG_LFH = 0x04034b50;
const ZIP_SIG_CDH = 0x02014b50;
const ZIP_SIG_EOCD = 0x06054b50;

@Injectable()
export class ImportacoesService {
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

  async create(ownerId: string, fileBuffer: Buffer, fileName: string) {
    // File size check
    if (fileBuffer.length > MAX_FILE_BYTES) {
      throw new BadRequestException(
        `arquivo acima do teto de ${MAX_FILE_BYTES / 1024 / 1024} MB`,
      );
    }

    // ZIP validation (if applicable)
    this.validateZipBuffer(fileBuffer);

    // Find company by owner
    const company = await this.companyModel.findOne({ ownerId }).lean().exec();
    if (!company) throw new BadRequestException('empresa não encontrada para este usuário');

    // Write temp file for worker
    const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), 'bim-import-'));
    const aqPath = path.join(tmpDir, fileName.replace(/[^a-zA-Z0-9._-]/g, '_'));
    await fs.writeFile(aqPath, fileBuffer);

    // Create import record
    const importId = crypto.randomUUID();
    await this.importModel.create({
      _id: importId,
      companyId: company._id,
      status: 'recebido' as ImportStatus,
      fileName,
    });

    // Fire-and-forget
    this.processAsync(importId, aqPath, tmpDir, company._id as string).catch(() => {
      /* errors are recorded in the import document */
    });

    return { importId, status: 'recebido' };
  }

  private async processAsync(
    importId: string,
    aqPath: string,
    tmpDir: string,
    companyId: string,
  ) {
    const setStatus = (status: ImportStatus, extra?: Partial<BimImport>) =>
      this.importModel.findByIdAndUpdate(importId, {
        status,
        updatedAt: new Date(),
        ...extra,
      });

    try {
      await setStatus('parseando');

      const result = await this.runWorker(importId, aqPath);

      if (result.status === 'vazio') {
        await setStatus('vazio', { productCount: 0 });
        return;
      }

      if (result.status === 'error') {
        throw new Error(result.error ?? 'erro desconhecido no parse');
      }

      // status: 'ok'
      const { products, catalogMeta } = result as { products: ProductResult[]; catalogMeta: CatalogMeta };

      await setStatus('gravando');

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

      await setStatus('falhou', { error: err.message ?? String(err) });
    } finally {
      // Remove temp file
      await fs.rm(tmpDir, { recursive: true, force: true }).catch(() => {});
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

      child.on('message', (msg: ThumbWorkerMessage) => {
        if (msg.type === 'thumb') {
          // Atualiza thumbKey no banco — best-effort
          this.productModel
            .findByIdAndUpdate(msg.productId, { thumbKey: msg.thumbKey })
            .exec()
            .catch(() => {});
        } else if (msg.type === 'done') {
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

  private validateZipBuffer(buf: Buffer): void {
    // Check if it looks like a ZIP (PK signature)
    if (buf.length < 4 || buf[0] !== 0x50 || buf[1] !== 0x4b) return;

    let offset = 0;
    let entryCount = 0;
    let totalUncompressed = 0;

    while (offset + 30 <= buf.length) {
      const sig = buf.readUInt32LE(offset);
      if (sig === ZIP_SIG_EOCD || sig === ZIP_SIG_CDH) break;
      if (sig !== ZIP_SIG_LFH) {
        offset++;
        continue;
      }

      const compressedSize = buf.readUInt32LE(offset + 18);
      const uncompressedSize = buf.readUInt32LE(offset + 22);
      const fileNameLen = buf.readUInt16LE(offset + 26);
      const extraLen = buf.readUInt16LE(offset + 28);

      if (offset + 30 + fileNameLen > buf.length) break;
      const fileName = buf.toString('utf8', offset + 30, offset + 30 + fileNameLen);

      // Path traversal
      const normalized = path.normalize(fileName);
      if (normalized.includes('..') || path.isAbsolute(normalized)) {
        throw new BadRequestException(
          `entrada ZIP com path traversal rejeitada: ${fileName}`,
        );
      }

      entryCount++;
      totalUncompressed += uncompressedSize;

      if (entryCount > MAX_ZIP_ENTRIES) {
        throw new BadRequestException(
          `ZIP com mais de ${MAX_ZIP_ENTRIES} entradas`,
        );
      }
      if (totalUncompressed > MAX_ZIP_UNCOMPRESSED) {
        throw new BadRequestException(
          `ZIP com soma descomprimida acima de ${MAX_ZIP_UNCOMPRESSED / 1024 / 1024} MB`,
        );
      }

      const dataOffset = offset + 30 + fileNameLen + extraLen;
      const next = dataOffset + compressedSize;
      if (next <= offset) break;
      offset = next;
    }
  }
}
