import { Inject, Injectable, InternalServerErrorException, Logger, NotFoundException } from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import { execFile } from 'node:child_process';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import * as crypto from 'node:crypto';
import { BimCatalog, BimCatalogDocument } from '../bim-catalogs/bim-catalogs.schema';
import { BimImport, BimImportDocument } from '../bim-imports/bim-imports.schema';
import { BimProduct, BimProductDocument } from '../bim-products/bim-products.schema';
import { Company, CompanyDocument } from '../companies/companies.schema';
import { IGeometryStore } from '../geometry-store/geometry-store.interface';
import { ImportacoesService } from '../importacoes/importacoes.service';
import { GeoBuffers } from '../common/geo-buffers';

/**
 * STEP ↔ geometria do viewer, e geometria → `.aq` (POC de edição — sem auth).
 *
 * Os dois conversores são scripts Python do próprio projeto, chamados como
 * processo filho:
 *
 *   scripts/step_to_geo.py   .stp → { pos, col, idx } (m, Y-up)   — OpenCASCADE (OCP)
 *   scripts/geo_to_aq.py     { partes | pos,col,idx } → .aq       — eng-reversa (OQ3D + schema 607)
 *
 * Python em processo filho e não no handler: o OpenCASCADE bloqueia o event loop
 * e é código nativo — o mesmo motivo do `parse-worker.ts`. A raiz do repositório é
 * resolvida a partir deste arquivo (`www/apps/api/src/step` → cinco níveis acima).
 */

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..', '..');
const SCRIPTS = path.join(REPO_ROOT, 'scripts');
const PYTHON = process.env.PYTHON ?? 'python3';
const TIMEOUT_MS = 5 * 60 * 1000;

export interface StepGeo extends GeoBuffers {
  partes: Array<{ nome: string; cor?: number[]; tipo?: string; triangulos?: number; triangulo_inicial?: number }>;
  unidade: string;
  bbox_mm: number[];
  fonte: string;
  /** só STEP */
  deflexao_mm?: number;
  /** só IFC — 1, 0.001 ou 0.01 */
  escala_aplicada?: number;
  cor_por_face?: boolean;
  segundos: number;
  formato?: 'step' | 'ifc';
}

export interface AqInfo {
  fabricante?: string;
  linha?: string;
  nome?: string;
  descricao?: string;
  codigo?: string;
  specs?: Record<string, string>;
  origem?: string;
}

export interface AqParte {
  nome: string;
  pos: number[];
  col: number[] | null;
  idx: number[];
}

function slugify(s: string): string {
  return (s ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

@Injectable()
export class StepService {
  private readonly logger = new Logger(StepService.name);

  constructor(
    @InjectModel(BimImport.name) private readonly importModel: Model<BimImportDocument>,
    @InjectModel(BimCatalog.name) private readonly catalogModel: Model<BimCatalogDocument>,
    @InjectModel(BimProduct.name) private readonly productModel: Model<BimProductDocument>,
    @InjectModel(Company.name) private readonly companyModel: Model<CompanyDocument>,
    @Inject('GEOMETRY_STORE') private readonly store: IGeometryStore,
    private readonly importacoes: ImportacoesService,
  ) {}

  // ── Python ───────────────────────────────────────────────────────────────

  private runPython(script: string, args: string[]): Promise<{ stdout: string; stderr: string }> {
    return new Promise((resolve, reject) => {
      execFile(
        PYTHON,
        [path.join(SCRIPTS, script), ...args],
        { cwd: REPO_ROOT, timeout: TIMEOUT_MS, maxBuffer: 64 * 1024 * 1024, env: { ...process.env } },
        (err, stdout, stderr) => {
          if (err) {
            const detalhe = (stderr || stdout || err.message).toString().trim().split('\n').slice(-6).join('\n');
            reject(new InternalServerErrorException(`${script} falhou: ${detalhe}`));
            return;
          }
          resolve({ stdout: stdout.toString(), stderr: stderr.toString() });
        },
      );
    });
  }

  /** STEP ou IFC, pela extensão do nome original (ou do caminho). */
  static formatoDe(nome: string): 'step' | 'ifc' {
    return /\.ifc(zip|xml)?$/i.test(nome) ? 'ifc' : 'step';
  }

  /**
   * Converte um arquivo CAD já em disco na geometria do viewer (apaga os temporários).
   * `.stp/.step` → `step_to_geo.py` (OpenCASCADE, tessela B-rep com a deflexão dada);
   * `.ifc`       → `ifc_to_geo.py` (o `parse_ifc.py` do projeto + dedup; deflexão não se aplica).
   */
  async tesselar(stpPath: string, deflexaoMm = 0.2, nomeOriginal?: string): Promise<StepGeo> {
    const outJson = path.join(os.tmpdir(), `cad-${crypto.randomUUID()}.json`);
    const t0 = Date.now();
    const formato = StepService.formatoDe(nomeOriginal ?? stpPath);
    try {
      if (formato === 'ifc') await this.runPython('ifc_to_geo.py', [stpPath, outJson]);
      else await this.runPython('step_to_geo.py', [stpPath, outJson, '--deflexao', String(deflexaoMm)]);
      const geo = JSON.parse(await fs.readFile(outJson, 'utf8')) as StepGeo;
      // o script grava o nome do arquivo temporário do multer; o que interessa é o original
      if (nomeOriginal) geo.fonte = path.basename(nomeOriginal);
      geo.formato = formato;
      this.logger.log(
        `${formato.toUpperCase()} convertido — ${geo.fonte}: ${geo.partes.length} parte(s), ${geo.idx.length / 3} triângulos, ` +
          `bbox ${geo.bbox_mm.map((v) => v.toFixed(0)).join('×')} mm, ${((Date.now() - t0) / 1000).toFixed(1)}s`,
      );
      return geo;
    } finally {
      await fs.unlink(outJson).catch(() => {});
    }
  }

  /** Gera um `.aq` a partir das partes do editor; devolve o caminho do arquivo temporário. */
  async gerarAq(info: AqInfo, partes: AqParte[], geo?: GeoBuffers): Promise<{ path: string; resumo: Record<string, unknown> }> {
    const id = crypto.randomUUID();
    const inJson = path.join(os.tmpdir(), `aq-in-${id}.json`);
    const outAq = path.join(os.tmpdir(), `aq-out-${id}.aq`);
    await fs.writeFile(inJson, JSON.stringify({ info, partes: partes.length ? partes : undefined, ...(geo ?? {}) }));
    try {
      const { stdout } = await this.runPython('geo_to_aq.py', [inJson, outAq, '--quiet']);
      const linhaJson = stdout.trim().split('\n').reverse().find((l) => l.startsWith('{')) ?? '{}';
      const resumo = JSON.parse(linhaJson);
      this.logger.log(`.aq gerado — ${resumo.peca}: ${resumo.malhas} malha(s), ${resumo.triangulos} triângulos, ${(resumo.bytes / 1024).toFixed(0)} KB`);
      return { path: outAq, resumo };
    } finally {
      await fs.unlink(inJson).catch(() => {});
    }
  }

  // ── Importar como produto ────────────────────────────────────────────────

  /**
   * Cria (ou acrescenta a) um catálogo com o STEP como produto, para abrir no
   * editor "como fizemos com os catálogos". Um `BimImport` próprio por STEP,
   * porque `geoKey` e miniatura embutem o `importId`.
   */
  async importar(opts: {
    stpPath: string;
    fileName: string;
    empresa?: string;
    fabricante?: string;
    catalogo?: string;
    nome?: string;
    deflexaoMm?: number;
  }) {
    const company = opts.empresa
      ? await this.companyModel.findOne({ customUrl: opts.empresa }).lean().exec()
      : await this.companyModel.findOne().sort({ createdAt: 1 }).lean().exec();
    if (!company) throw new NotFoundException(opts.empresa ? `empresa "${opts.empresa}" não encontrada` : 'nenhuma empresa cadastrada — crie uma em /empresa/criar');

    const geo = await this.tesselar(opts.stpPath, opts.deflexaoMm ?? 0.2, opts.fileName);

    const ehIfc = geo.formato === 'ifc';
    const fabricante = (opts.fabricante ?? '').trim() || (ehIfc ? 'IFC' : 'STEP');
    const titulo = (opts.catalogo ?? '').trim() || (ehIfc ? 'Peças IFC' : 'Peças STEP');
    const slug = slugify(titulo) || (ehIfc ? 'pecas-ifc' : 'pecas-step');
    const nome = (opts.nome ?? '').trim() || path.basename(opts.fileName).replace(/\.(stp|step|ifc)$/i, '');

    const importId = crypto.randomUUID();
    await this.importModel.create({
      _id: importId,
      companyId: company._id,
      status: 'publicado',
      fileName: opts.fileName,
      productCount: 1,
      note: ehIfc
        ? `IFC convertido pelo parse_ifc.py — ${geo.partes.length} produto(s), unidade ${geo.unidade}, escala ${geo.escala_aplicada}`
        : `STEP tesselado (deflexão ${geo.deflexao_mm} mm) — ${geo.partes.length} sólido(s), unidade ${geo.unidade}`,
      updatedAt: new Date(),
    });

    let catalog = await this.catalogModel.findOne({ companyId: company._id, slug }).lean().exec();
    if (!catalog) {
      const catalogId = crypto.randomUUID();
      await this.catalogModel.create({
        _id: catalogId,
        companyId: company._id,
        slug,
        title: titulo,
        manufacturer: fabricante,
        layout: 'catalog-grid',
        filters: [],
        productCount: 0,
      });
      catalog = await this.catalogModel.findById(catalogId).lean().exec();
    }
    await this.importModel.findByIdAndUpdate(importId, { catalogId: catalog!._id }).exec();

    // id único dentro do catálogo (mesmo STEP importado duas vezes)
    const baseId = slugify(nome) || 'peca-step';
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
            Cores: geo.cor_por_face ? 'por face (IFCINDEXEDCOLOURMAP)' : 'uniforme',
          }
        : {
            Fonte: geo.fonte,
            Formato: 'STEP (ISO 10303-21)',
            'Unidade do arquivo': geo.unidade,
            'Dimensões (mm)': `${bb[0].toFixed(1)} × ${bb[1].toFixed(1)} × ${bb[2].toFixed(1)}`,
            Sólidos: String(geo.partes.length),
            Triângulos: String(geo.idx.length / 3),
            'Deflexão (mm)': String(geo.deflexao_mm),
          },
      curva: null,
      potencia: null,
      conexoes: null,
      geoKey,
      thumbKey: null,
    });

    const series = (await this.productModel.find({ catalogId: catalog!._id }).distinct('serie').exec()) as string[];
    const count = await this.productModel.countDocuments({ catalogId: catalog!._id }).exec();
    await this.catalogModel.findByIdAndUpdate(catalog!._id, { productCount: count, filters: series.filter(Boolean) }).exec();

    // miniatura: fire-and-forget, como no import de .aq
    this.importacoes.spawnThumbWorker(importId, [{ productId, geoKey }]).catch(() => {});

    this.logger.log(`${ehIfc ? 'IFC' : 'STEP'} importado — ${nome} → ${company.customUrl}/${slug} (produto ${productId})`);
    return {
      produtoId: productId,
      importId,
      empresa: company.customUrl,
      catalogSlug: slug,
      catalogId: catalog!._id,
      editorUrl: `/${company.customUrl}/${slug}/editar/${productId}`,
      catalogoUrl: `/${company.customUrl}/${slug}`,
      triangulos: geo.idx.length / 3,
      partes: geo.partes.length,
      bbox_mm: geo.bbox_mm,
      unidade: geo.unidade,
      formato: geo.formato,
    };
  }
}
