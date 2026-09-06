import { BadRequestException, Inject, Injectable, Logger, NotFoundException } from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import * as crypto from 'node:crypto';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import { BimCatalog, BimCatalogDocument, BimImport, BimImportDocument, BimProduct, BimProductDocument, Company, CompanyDocument, IGeometryStore, ImportStatus, ImportTipo, apagarImportacao, storagePath } from '@bim/dominio';
import type { FamiliasRevitInfo, PluginInfo } from '@bim/base';
import { FILA_IMPORTACOES, Fila } from './fila';
import { ImportarDto } from './importar.dto';
import { ImportarPluginDto } from './importar-plugin.dto';
import { ImportarRevitDto } from './importar-revit.dto';
import { PipelineService } from '../pipeline/pipeline.service';
import { ArquivoRecebido, Empresa, PublicacaoService } from '../publicacao/publicacao.service';

export type { ArquivoRecebido } from '../publicacao/publicacao.service';
export { descreveDiag, descreveResumo } from '../publicacao/descricoes';

/**
 * ImportacoesService — a ENTRADA e a CONSULTA de importações (criador de catálogos):
 * recebe o upload (biblioteca `.aq`/`.zip`, peça CAD, plugin de CAD, famílias Revit), cria o `BimImport`
 * em `recebido`, enfileira o trabalho (uma importação por vez, I11 — as demais esperam com a posição no
 * `note`) e responde status/lista/apagar. O trabalho em si é do `PublicacaoService`; as miniaturas, do
 * `MiniaturasService`.
 */

const EXT_AQ = /\.(aq|zip)$/i;
const EXT_CAD = /\.(stp|step|igs|iges|ifc|ifczip|ifcxml)$/i;
const EXT_DLL = /\.dll$/i;
const EXT_RFA = /\.rfa$/i;
const EXT_REVIT = /\.(rfa|zip)$/i;   // na rota própria, `.zip` é um pacote de famílias (na rota geral, `.zip` é biblioteca .aq)

export function tipoDe(nomeOuExt: string): ImportTipo | null {
  if (EXT_AQ.test(nomeOuExt)) return 'aq';
  if (EXT_CAD.test(nomeOuExt)) return 'cad';
  if (EXT_RFA.test(nomeOuExt)) return 'revit';
  return null;
}

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
    private readonly pipeline: PipelineService,
    private readonly publicacao: PublicacaoService,
  ) {}

  // ── entrada ──────────────────────────────────────────────────────────────

  /** Empresa por `customUrl`; vazio = a primeira cadastrada (sem auth não há "minha empresa"). */
  private async empresaDe(customUrl?: string) {
    const company = customUrl
      ? await this.companyModel.findOne({ customUrl }).lean().exec()
      : await this.companyModel.findOne().sort({ createdAt: 1 }).lean().exec();
    if (!company) {
      throw new BadRequestException(customUrl ? `empresa "${customUrl}" não encontrada` : 'nenhuma empresa cadastrada — crie uma em /empresa/criar');
    }
    return company as Empresa;
  }

  async create(arquivo: ArquivoRecebido, body: ImportarDto) {
    const tipo = tipoDe(arquivo.fileName) ?? tipoDe(arquivo.path);
    if (!tipo) {
      await fs.unlink(arquivo.path).catch(() => {});
      throw new BadRequestException(`extensão não suportada em "${arquivo.fileName}" — envie .aq, .zip, .stp, .step, .igs, .ifc ou .rfa`);
    }
    if (tipo === 'revit') return this.createFamiliasRevit(arquivo, { empresa: body.empresa });
    let company;
    try {
      company = await this.empresaDe(body.empresa);
    } catch (e) {
      await fs.unlink(arquivo.path).catch(() => {});
      throw e;
    }
    const sizeMb = (arquivo.size / 1024 / 1024).toFixed(1);
    this.logger.log(`upload recebido — ${arquivo.fileName} (${sizeMb} MB, ${tipo}) empresa=${company.customUrl}`);

    const importId = crypto.randomUUID();
    await this.importModel.create({
      _id: importId,
      companyId: company._id,
      tipo,
      status: 'recebido' as ImportStatus,
      fileName: arquivo.fileName,
      note: `${tipo === 'aq' ? 'biblioteca' : 'peça CAD'} de ${sizeMb} MB recebida`,
      updatedAt: new Date(),
    });

    // Uma importação por vez (I11): as demais esperam em `recebido` com a posição no `note`.
    // O processamento registra as falhas no documento; se nem isso conseguir, fica no log.
    const trabalho = tipo === 'aq'
      ? () => this.publicacao.processarAq(importId, arquivo, company)
      : () => this.publicacao.processarCad(importId, arquivo, company, body);
    this.fila
      .executar(importId, trabalho, (naFrente) => {
        if (naFrente > 0) {
          this.logger.log(`[${importId.slice(0, 8)}] na fila — ${naFrente} à frente`);
          this.importModel.findByIdAndUpdate(importId, { note: `na fila — ${naFrente} importação(ões) à frente`, updatedAt: new Date() })
            .exec().catch(() => undefined);
        }
      })
      .catch((e: any) => this.logger.error(`[${importId.slice(0, 8)}] processamento escapou — ${e?.message ?? e}`));

    return { importId, tipo, status: 'recebido', statusUrl: `/importacoes/${importId}` };
  }

  // ── plugin de CAD que é casca de um catálogo web ─────────────────────────

  /**
   * DLL + categoria + dados do formulário → uma importação `plugin` na fila: a biblioteca baixa os
   * arquivos da categoria para `catallog/<importId>/` e devolve o catálogo, que é publicado como
   * uma biblioteca. O lead só existe no processo filho (JSON temporário) — nunca no Mongo.
   */
  async createPlugin(arquivo: ArquivoRecebido, body: ImportarPluginDto) {
    let company: Empresa;
    let info: PluginInfo;
    try {
      if (!EXT_DLL.test(arquivo.fileName)) throw new BadRequestException(`"${arquivo.fileName}" não é a DLL do plugin — envie o .dll do bundle do plugin`);
      company = await this.empresaDe(body.empresa);
      try {
        info = { ...(await this.pipeline.inspecionarPlugin(arquivo.path, { semRede: true })), arquivo: arquivo.fileName };
      } catch (e: any) {
        throw new BadRequestException(`não li o plugin: ${(e?.message ?? String(e)).split('\n').slice(-3).join(' ').slice(0, 500)}`);
      }
    } catch (e) {
      await fs.unlink(arquivo.path).catch(() => {});
      throw e;
    }
    const host = (body.host || info.host).replace(/\/+$/, '');
    const rotulo = [info.plugin ?? arquivo.fileName, info.versao].filter(Boolean).join(' ');
    this.logger.log(`plugin recebido — ${rotulo} → ${host} · categoria ${body.categoria} · igs/grupo ${body.igsPorGrupo ?? 1} · empresa=${company.customUrl}`);

    const importId = crypto.randomUUID();
    await this.importModel.create({
      _id: importId,
      companyId: company._id,
      tipo: 'plugin' as ImportTipo,
      status: 'recebido' as ImportStatus,
      fileName: `${rotulo} · ${body.categoria}`,
      note: `plugin ${rotulo} → ${host} · categoria ${body.categoria}`,
      updatedAt: new Date(),
    });
    const lead = { full_name: body.fullName, email: body.email, mobile: body.mobile, company: body.company, position: body.position };
    const downloads = path.join(storagePath(), 'catallog', importId);
    const trabalho = () => this.publicacao.processarCatalogo(importId, company, {
      rotulo: 'plugin_catalogo_web importar',
      produzir: (geoDir, onProgresso) => this.pipeline.catalogoDePlugin({
        host, categoria: body.categoria, lead, downloads, geoDir, igsPorGrupo: body.igsPorGrupo ?? 1, deflexao: body.deflexao ?? 0.2, plugin: info, onProgresso,
      }),
      aoTerminar: () => fs.unlink(arquivo.path),
      aoFalhar: () => fs.rm(downloads, { recursive: true, force: true }),
      notaExtra: (r) => {
        const o = (r.hints as any)?.origem;
        if (!o) return null;
        const semIgs = Array.isArray(o.grupos_sem_igs) && o.grupos_sem_igs.length ? ` · ${o.grupos_sem_igs.length} grupo(s) sem IGES ficaram fora` : '';
        return `${r.n_geometrias} peça(s) de ${o.grupos} grupo(s) · ${o.arquivos} arquivo(s), ${(o.bytes / 1e6).toFixed(0)} MB de ${o.host}${semIgs}`;
      },
    });
    this.fila
      .executar(importId, trabalho, (naFrente) => {
        if (naFrente > 0) {
          this.importModel.findByIdAndUpdate(importId, { note: `na fila — ${naFrente} importação(ões) à frente`, updatedAt: new Date() })
            .exec().catch(() => undefined);
        }
      })
      .catch((e: any) => this.logger.error(`[${importId.slice(0, 8)}] processamento escapou — ${e?.message ?? e}`));
    return { importId, tipo: 'plugin', status: 'recebido', statusUrl: `/importacoes/${importId}`, host, plugin: info };
  }

  // ── famílias Revit (.rfa solto ou .zip de famílias) ──────────────────────

  /**
   * `.rfa`/`.zip` → uma importação `revit` na fila: a biblioteca lê PartAtom e type catalogs, converte a
   * geometria irmã quando há (IFC/STEP/IGES de mesmo nome) e gera forma representativa quando não há,
   * e devolve o catálogo, publicado como uma biblioteca. A inspeção síncrona recusa na hora o que não
   * tem nenhuma família (um `.zip` de outra coisa, um projeto `.rvt`).
   */
  async createFamiliasRevit(arquivo: ArquivoRecebido, body: ImportarRevitDto) {
    let company: Empresa;
    let info: FamiliasRevitInfo;
    try {
      if (!EXT_REVIT.test(arquivo.fileName)) throw new BadRequestException(`"${arquivo.fileName}" não é .rfa nem .zip — envie a família ou um .zip com as famílias`);
      company = await this.empresaDe(body.empresa);
      try {
        info = await this.pipeline.inspecionarFamiliasRevit(arquivo.path);
      } catch (e: any) {
        throw new BadRequestException(`não li as famílias: ${(e?.message ?? String(e)).split('\n').slice(-3).join(' ').slice(0, 500)}`);
      }
      if (info.n_familias === 0) {
        throw new BadRequestException(`"${arquivo.fileName}" não tem nenhuma família .rfa legível${info.avisos.length ? ` — ${info.avisos.slice(0, 3).join('; ').slice(0, 400)}` : ''}`);
      }
    } catch (e) {
      await fs.unlink(arquivo.path).catch(() => {});
      throw e;
    }
    const sizeMb = (arquivo.size / 1024 / 1024).toFixed(1);
    const titulo = body.catalogo || arquivo.fileName.replace(EXT_REVIT, '');
    this.logger.log(`famílias Revit recebidas — ${arquivo.fileName} (${sizeMb} MB): ${info.n_familias} família(s), ${info.n_tipos} tipo(s), ${info.com_geometria_irma} com geometria irmã · empresa=${company.customUrl}`);

    const importId = crypto.randomUUID();
    await this.importModel.create({
      _id: importId,
      companyId: company._id,
      tipo: 'revit' as ImportTipo,
      status: 'recebido' as ImportStatus,
      fileName: arquivo.fileName,
      note: `${info.n_familias} família(s) Revit, ${info.n_tipos} tipo(s), ${info.com_geometria_irma} com geometria irmã — ${sizeMb} MB recebidos`,
      updatedAt: new Date(),
    });
    const trabalho = () => this.publicacao.processarCatalogo(importId, company, {
      rotulo: 'familias_revit importar',
      produzir: (geoDir, onProgresso) => this.pipeline.catalogoDeFamiliasRevit({
        entrada: arquivo.path, geoDir, titulo, fabricante: body.fabricante, comprimentoMm: body.comprimentoMm, deflexao: body.deflexao, onProgresso,
      }),
      aoTerminar: () => fs.unlink(arquivo.path),
      notaExtra: (r) => {
        const o = (r.hints as any)?.origem;
        if (!o) return null;
        const semCota = o.sem_cota ? ` · ${o.sem_cota} tipo(s) sem cota ficaram fora` : '';
        return `${r.hints.n_pecas} peça(s) de ${o.familias} família(s) · ${o.com_geometria_irma} com geometria irmã, ${o.representativas} com forma representativa${semCota}`;
      },
    });
    this.fila
      .executar(importId, trabalho, (naFrente) => {
        if (naFrente > 0) {
          this.importModel.findByIdAndUpdate(importId, { note: `na fila — ${naFrente} importação(ões) à frente`, updatedAt: new Date() })
            .exec().catch(() => undefined);
        }
      })
      .catch((e: any) => this.logger.error(`[${importId.slice(0, 8)}] processamento escapou — ${e?.message ?? e}`));
    return { importId, tipo: 'revit', status: 'recebido', statusUrl: `/importacoes/${importId}`, familias: info };
  }

  // ── apagar ───────────────────────────────────────────────────────────────

  /** Apaga uma importação terminada: produtos, `geo/`, `thumbs/`, documento; reconta o catálogo (remocao.ts). */
  async apagar(importId: string) {
    const r = await apagarImportacao(
      { companies: this.companyModel as any, catalogs: this.catalogModel as any, products: this.productModel as any, imports: this.importModel as any },
      this.store, importId,
    );
    this.logger.log(`[${importId.slice(0, 8)}] importação apagada — ${r.produtos} produtos${r.avisos.length ? ` (${r.avisos.length} avisos)` : ''}`);
    for (const a of r.avisos) this.logger.warn(a);
    return { ok: true, importId, ...r };
  }

  // ── consulta ─────────────────────────────────────────────────────────────

  async status(importId: string) {
    const imp = await this.importModel.findById(importId).lean().exec();
    if (!imp) throw new NotFoundException('importação não encontrada');
    return this.toDto(imp);
  }

  async listar(empresa: string | undefined, limite: number) {
    const filtro: Record<string, unknown> = {};
    if (empresa) {
      const company = await this.companyModel.findOne({ customUrl: empresa }).lean().exec();
      if (!company) throw new NotFoundException(`empresa "${empresa}" não encontrada`);
      filtro.companyId = company._id;
    }
    const imps = await this.importModel.find(filtro).sort({ createdAt: -1 }).limit(limite).lean().exec();
    return Promise.all(imps.map((i) => this.toDto(i)));
  }

  private async toDto(imp: any) {
    const company = await this.companyModel.findById(imp.companyId).select('customUrl').lean().exec();
    const cat = imp.catalogId ? await this.catalogModel.findById(imp.catalogId).select('slug title').lean().exec() : null;
    const empresa = company?.customUrl ?? null;
    const catalogoUrl = empresa && cat ? `/${empresa}/${cat.slug}` : null;
    let produto: Record<string, unknown> = {};
    if (imp.tipo === 'cad' && imp.status === 'publicado') {   // 'aq', 'plugin' e 'revit' são catálogos inteiros — nada por produto aqui
      const p = await this.productModel.findOne({ importId: imp._id }).lean().exec();
      if (p && catalogoUrl) {
        produto = { produtoId: p._id, nome: p.nome, editorUrl: `${catalogoUrl}/editar/${p._id}`, specs: p.specs, thumbUrl: p.thumbKey ? `/thumbs/${p._id}` : null };
      }
    }
    const updatedAt = imp.updatedAt ?? null;
    return {
      importId: imp._id,
      tipo: imp.tipo ?? 'aq',
      status: imp.status,
      fileName: imp.fileName,
      note: imp.note ?? null,
      error: imp.error ?? null,
      productCount: imp.productCount ?? null,
      thumbCount: imp.thumbCount ?? null,
      thumbFailed: imp.thumbFailed ?? null,
      thumbError: imp.thumbError ?? null,
      diag: imp.diag ?? null,
      catalogId: imp.catalogId ?? null,
      catalogSlug: cat?.slug ?? null,
      catalogTitle: cat?.title ?? null,
      empresa,
      catalogoUrl,
      editorUrl: catalogoUrl ? `${catalogoUrl}/editar` : null,
      createdAt: imp.createdAt,
      updatedAt,
      segundos: Math.round(((updatedAt ?? new Date()).getTime() - new Date(imp.createdAt).getTime()) / 1000),
      ...produto,
    };
  }
}
