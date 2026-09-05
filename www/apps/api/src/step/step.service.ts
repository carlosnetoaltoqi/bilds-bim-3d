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
import { FILA_IMPORTACOES, Fila } from '../common/fila';

/**
 * STEP ↔ geometria do viewer, e geometria → `.aq` (POC de edição — sem auth).
 *
 * Os dois conversores são scripts Python do próprio projeto, chamados como
 * processo filho:
 *
 *   pipeline/step_to_geo.py   .stp → { pos, col, idx } (m, Y-up)   — OpenCASCADE (OCP)
 *   pipeline/geo_to_aq.py     { partes | pos,col,idx } → .aq       — eng-reversa (OQ3D + schema 607)
 *
 * Python em processo filho e não no handler: o OpenCASCADE bloqueia o event loop
 * e é código nativo — o mesmo motivo do `parse-worker.ts`. A raiz do repositório é
 * resolvida a partir deste arquivo (`www/apps/api/src/step` → cinco níveis acima).
 */

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..', '..');
// os conversores moram no pipeline do serviço de ingestão desde 2026-09-05 (E2)
const SCRIPTS = path.join(REPO_ROOT, 'www', 'apps', 'ingestao', 'pipeline');
const PYTHON = process.env.PYTHON ?? 'python3';
const TIMEOUT_MS = 30 * 60 * 1000;   // um Revit de 130 MB leva minutos no ifcopenshell

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
  /** só IFC: 'parse_ifc' (exato) ou 'ifcopenshell' (rápido) */
  caminho?: string;
  tamanho_mb?: number;
  /** presente quando passou de --max-triangulos */
  aviso?: string;
}

export interface ImportarOpts {
  stpPath: string;
  fileName: string;
  fileSize?: number;
  empresa?: string;
  fabricante?: string;
  catalogo?: string;
  nome?: string;
  deflexaoMm?: number;
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
    @Inject(FILA_IMPORTACOES) private readonly fila: Fila,
  ) {}

  // ── Python ───────────────────────────────────────────────────────────────

  private runPython(script: string, args: string[], onProgress?: (linha: string) => void): Promise<{ stdout: string; stderr: string }> {
    return new Promise((resolve, reject) => {
      const child = execFile(
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
      // o ifc_to_geo.py escreve o progresso no stderr ("  500 formas, 120.000 triângulos, 40s")
      if (onProgress && child.stderr) {
        let resto = '';
        child.stderr.on('data', (chunk: Buffer) => {
          resto += chunk.toString();
          const linhas = resto.split('\n');
          resto = linhas.pop() ?? '';
          for (const l of linhas) {
            const t = l.replace(/\x1b\[[0-9;]*m/g, '').trim();
            if (t) onProgress(t);
          }
        });
      }
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
  async tesselar(stpPath: string, deflexaoMm = 0.2, nomeOriginal?: string, onProgress?: (linha: string) => void): Promise<StepGeo> {
    const outJson = path.join(os.tmpdir(), `cad-${crypto.randomUUID()}.json`);
    const t0 = Date.now();
    const formato = StepService.formatoDe(nomeOriginal ?? stpPath);
    try {
      if (formato === 'ifc') await this.runPython('ifc_to_geo.py', [stpPath, outJson], onProgress);
      else await this.runPython('step_to_geo.py', [stpPath, outJson, '--deflexao', String(deflexaoMm)], onProgress);
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
   * Importação ASSÍNCRONA: cria o `BimImport` em `recebido`, devolve na hora e
   * processa em background (parseando → gravando → publicado | falhou), com o
   * progresso do Python em `note`. Um Revit de 130 MB leva minutos — a versão
   * síncrona morria no timeout do servidor e o browser via "Failed to fetch".
   * Acompanhe em `GET /cad/importacoes/:importId`.
   */
  async importarAsync(opts: ImportarOpts): Promise<{ importId: string; status: string; statusUrl: string }> {
    const company = await this.empresaDe(opts.empresa);
    const importId = crypto.randomUUID();
    await this.importModel.create({
      _id: importId,
      companyId: company._id,
      status: 'recebido',
      fileName: opts.fileName,
      note: `${StepService.formatoDe(opts.fileName).toUpperCase()} de ${((opts.fileSize ?? 0) / 1024 / 1024).toFixed(1)} MB recebido`,
      updatedAt: new Date(),
    });
    // não aguarda: erros vão para o documento do import. Mesma fila dos imports de .aq (I11);
    // processar registra a falha no documento; se nem isso conseguir, fica no log
    this.fila
      .executar(importId, () => this.processar(importId, company as any, opts), (naFrente) => {
        if (naFrente > 0) {
          this.logger.log(`import ${importId.slice(0, 8)} na fila — ${naFrente} à frente`);
          this.importModel.findByIdAndUpdate(importId, { note: `na fila — ${naFrente} importação(ões) à frente`, updatedAt: new Date() })
            .exec().catch(() => undefined);
        }
      })
      .catch((e: any) => this.logger.error(`import ${importId.slice(0, 8)} — processar escapou: ${e?.message ?? e}`));
    return { importId, status: 'recebido', statusUrl: `/cad/importacoes/${importId}` };
  }

  /** Estado de uma importação CAD, com os links quando publicada. */
  async status(importId: string) {
    const imp = await this.importModel.findById(importId).lean().exec();
    if (!imp) throw new NotFoundException('importação não encontrada');
    let produto: Record<string, unknown> | null = null;
    if (imp.status === 'publicado') {
      const p = await this.productModel.findOne({ importId }).lean().exec();
      const cat = imp.catalogId ? await this.catalogModel.findById(imp.catalogId).lean().exec() : null;
      const company = await this.companyModel.findById(imp.companyId).lean().exec();
      if (p && cat && company) {
        produto = {
          produtoId: p._id,
          nome: p.nome,
          catalogSlug: cat.slug,
          empresa: company.customUrl,
          editorUrl: `/${company.customUrl}/${cat.slug}/editar/${p._id}`,
          catalogoUrl: `/${company.customUrl}/${cat.slug}`,
          specs: p.specs,
          thumbUrl: p.thumbKey ? `/thumbs/${p._id}` : null,
        };
      }
    }
    return {
      importId: imp._id,
      status: imp.status,
      fileName: imp.fileName,
      note: (imp as any).note ?? null,
      error: imp.error ?? null,
      createdAt: imp.createdAt,
      updatedAt: (imp as any).updatedAt ?? null,
      segundos: Math.round((((imp as any).updatedAt ?? new Date()).getTime() - new Date(imp.createdAt).getTime()) / 1000),
      ...(produto ?? {}),
    };
  }

  private async empresaDe(customUrl?: string) {
    const company = customUrl
      ? await this.companyModel.findOne({ customUrl }).lean().exec()
      : await this.companyModel.findOne().sort({ createdAt: 1 }).lean().exec();
    if (!company) throw new NotFoundException(customUrl ? `empresa "${customUrl}" não encontrada` : 'nenhuma empresa cadastrada — crie uma em /empresa/criar');
    return company;
  }

  private async processar(importId: string, company: { _id: string; customUrl: string }, opts: ImportarOpts) {
    const t0 = Date.now();
    const setStatus = (status: string, extra: Record<string, unknown> = {}) =>
      this.importModel.findByIdAndUpdate(importId, { status, updatedAt: new Date(), ...extra }).exec();
    // miniatura depois do try/catch, ainda dentro da vaga da fila — mesmo motivo do processAsync dos .aq (S7.13)
    let paraMiniatura: { productId: string; geoKey: string } | null = null;
    try {
      await setStatus('parseando', { note: 'convertendo…' });
      let ultimoProgresso = 0;
      const geo = await this.tesselar(opts.stpPath, opts.deflexaoMm ?? 0.2, opts.fileName, (linha) => {
        // no máximo uma atualização por segundo no Mongo
        if (Date.now() - ultimoProgresso > 1000) {
          ultimoProgresso = Date.now();
          this.importModel.findByIdAndUpdate(importId, { note: linha, updatedAt: new Date() }).exec().catch(() => {});
        }
      });
      await setStatus('gravando', { note: `${geo.idx.length / 3} triângulos convertidos em ${((Date.now() - t0) / 1000).toFixed(0)} s — gravando…` });
      const r = await this.publicar(importId, company, opts, geo);
      await setStatus('publicado', {
        catalogId: r.catalogId,
        productCount: 1,
        note: [
          `${geo.formato?.toUpperCase()} · ${geo.partes.length} ${geo.formato === 'ifc' ? 'produto(s)' : 'sólido(s)'} · ${geo.idx.length / 3} triângulos · ${((Date.now() - t0) / 1000).toFixed(0)} s`,
          geo.caminho ? `via ${geo.caminho}` : null,
          geo.aviso ?? null,
        ].filter(Boolean).join(' — '),
      });
      this.logger.log(`${geo.formato?.toUpperCase()} importado — ${r.nome} → ${company.customUrl}/${r.slug} (produto ${r.productId}) em ${((Date.now() - t0) / 1000).toFixed(1)}s`);
      paraMiniatura = { productId: r.productId, geoKey: r.geoKey };
    } catch (err: any) {
      const msg = (err?.message ?? String(err)).slice(0, 2000);
      this.logger.error(`import ${importId.slice(0, 8)} FALHOU — ${msg}`);
      await this.limparImport(importId);
      await setStatus('falhou', { error: msg, note: `falhou após ${((Date.now() - t0) / 1000).toFixed(0)} s` });
    } finally {
      await fs.unlink(opts.stpPath).catch(() => {});
    }
    if (paraMiniatura) await this.importacoes.gerarMiniaturas(importId, [paraMiniatura]); // nunca rejeita
  }

  /**
   * Versão SÍNCRONA (usada por `?sync=1` e pelos testes): converte e publica na
   * mesma requisição. Só para arquivos pequenos.
   */
  async importar(opts: ImportarOpts) {
    const company = await this.empresaDe(opts.empresa);
    const geo = await this.tesselar(opts.stpPath, opts.deflexaoMm ?? 0.2, opts.fileName);
    const importId = crypto.randomUUID();
    await this.importModel.create({
      _id: importId,
      companyId: company._id,
      status: 'publicado',
      fileName: opts.fileName,
      productCount: 1,
      note: geo.formato === 'ifc'
        ? `IFC convertido (${geo.caminho}) — ${geo.partes.length} produto(s), unidade ${geo.unidade}, escala ${geo.escala_aplicada}`
        : `STEP tesselado (deflexão ${geo.deflexao_mm} mm) — ${geo.partes.length} sólido(s), unidade ${geo.unidade}`,
      updatedAt: new Date(),
    });
    let r: Awaited<ReturnType<StepService['publicar']>>;
    try {
      r = await this.publicar(importId, company as any, opts, geo);
    } catch (err: any) {
      const msg = (err?.message ?? String(err)).slice(0, 2000);
      this.logger.error(`import ${importId.slice(0, 8)} (sync) FALHOU ao publicar — ${msg}`);
      await this.limparImport(importId);
      await this.importModel.findByIdAndUpdate(importId, { status: 'falhou', error: msg, updatedAt: new Date() }).exec().catch(() => undefined);
      throw err;
    }
    await this.importModel.findByIdAndUpdate(importId, { catalogId: r.catalogId }).exec();
    void this.importacoes.gerarMiniaturas(importId, [{ productId: r.productId, geoKey: r.geoKey }]);
    this.logger.log(`${geo.formato?.toUpperCase()} importado — ${r.nome} → ${company.customUrl}/${r.slug} (produto ${r.productId})`);
    return {
      produtoId: r.productId,
      importId,
      empresa: company.customUrl,
      catalogSlug: r.slug,
      catalogId: r.catalogId,
      editorUrl: `/${company.customUrl}/${r.slug}/editar/${r.productId}`,
      catalogoUrl: `/${company.customUrl}/${r.slug}`,
      triangulos: geo.idx.length / 3,
      partes: geo.partes.length,
      bbox_mm: geo.bbox_mm,
      unidade: geo.unidade,
      formato: geo.formato,
      aviso: geo.aviso ?? null,
    };
  }

  /**
   * Remove o que `publicar` pode ter deixado pela metade: o JSON em `geo/<importId>/` é
   * gravado ANTES do `productModel.create`, então uma falha entre os dois deixava um
   * arquivo órfão sem produto (I15). O prefixo é determinístico — não precisa saber a chave.
   */
  private async limparImport(importId: string) {
    await this.productModel.deleteMany({ importId }).catch((e: any) =>
      this.logger.warn(`import ${importId.slice(0, 8)} — limpeza de produtos falhou: ${e?.message ?? e}`),
    );
    await this.store.deleteByPrefix(`geo/${importId}`).catch((e: any) =>
      this.logger.warn(`import ${importId.slice(0, 8)} — limpeza de geo/${importId} falhou: ${e?.message ?? e}`),
    );
  }

  /** Catálogo (upsert) + produto + geometria no storage. Comum aos dois modos. */
  private async publicar(importId: string, company: { _id: string; customUrl: string }, opts: ImportarOpts, geo: StepGeo) {

    const ehIfc = geo.formato === 'ifc';
    const fabricante = (opts.fabricante ?? '').trim() || (ehIfc ? 'IFC' : 'STEP');
    const titulo = (opts.catalogo ?? '').trim() || (ehIfc ? 'Peças IFC' : 'Peças STEP');
    const slug = slugify(titulo) || (ehIfc ? 'pecas-ifc' : 'pecas-step');
    const nome = (opts.nome ?? '').trim() || path.basename(opts.fileName).replace(/\.(stp|step|ifc)$/i, '');

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
            Cores: geo.caminho === 'ifcopenshell' ? 'por material (ifcopenshell)' : geo.cor_por_face ? 'por face (IFCINDEXEDCOLOURMAP)' : 'uniforme',
            Conversor: geo.caminho ?? 'parse_ifc',
            'Tamanho do arquivo (MB)': String(geo.tamanho_mb ?? ''),
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

    return { productId, geoKey, slug, nome, catalogId: catalog!._id as string };
  }
}
