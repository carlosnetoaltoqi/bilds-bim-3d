import { BadRequestException, Inject, Injectable, Logger, NotFoundException } from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import * as crypto from 'node:crypto';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import { BimCatalog, BimCatalogDocument, BimImport, BimImportDocument, BimProduct, BimProductDocument, Company, CompanyDocument, IGeometryStore, ImportStatus, ImportTipo, apagarImportacao, storagePath } from '@bim/dominio';
import { FILA_IMPORTACOES, FILA_MINIATURAS, Fila } from './fila';
import { ImportarDto } from './importar.dto';
import { ImportarPluginDto } from './importar-plugin.dto';
import { PipelineService, PluginInfo, ProdutoPipeline, ResultadoCatalogo, ResumoMiniaturas, StepGeo } from '../pipeline/pipeline.service';

/**
 * ImportacoesService — o fluxo de uma importação (docs/arquitetura-www-servico-de-ingestao.md, §2):
 *
 *   recebido → [fila] → parseando (pipeline Python) → gravando (Mongo) → publicado | vazio | falhou
 *                                                                        └→ miniaturas (Chromium), ainda na vaga da fila
 *
 * Biblioteca (`.aq`/`.zip`): `catalogo_de_aq.py` grava uma geometria por simbologia em
 * `geo/<importId>/` e devolve o catálogo; os produtos apontam para `geo/<importId>/<geo>`
 * (vários podem compartilhar — A5). Plugin de AutoCAD (S7.17): `catallog.py` descobre o catálogo
 * web na DLL, baixa os IGES/RFA de uma categoria para `catallog/<importId>/` (ficam — são a
 * fonte), tessela em `geo/<importId>/` e devolve o MESMO JSON — os dois passam por
 * `processarCatalogo`. Peça CAD (`.stp`/`.igs`/`.ifc`): `step_to_geo.py`/`ifc_to_geo.py` → um produto
 * num catálogo "Peças STEP/IFC" da empresa.
 *
 * Miniaturas são por geometria (`thumbs/<importId>/<stem>.webp`) e nunca mudam o status do
 * import; cada falha fica em `note`/`thumbFailed`/`thumbError` (I15). A vaga da fila só libera
 * depois delas (S7.13: dois Chromiums ao mesmo tempo). `regerarMiniatura` (pedida pela API após
 * editar geometria — A6) usa uma fila própria para não esperar um import de minutos.
 */

const EXT_AQ = /\.(aq|zip)$/i;
const EXT_CAD = /\.(stp|step|igs|iges|ifc|ifczip|ifcxml)$/i;
const EXT_DLL = /\.dll$/i;

export function tipoDe(nomeOuExt: string): ImportTipo | null {
  if (EXT_AQ.test(nomeOuExt)) return 'aq';
  if (EXT_CAD.test(nomeOuExt)) return 'cad';
  return null;
}

function slugify(s: string): string {
  return (s ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

const stemDe = (geo: string) => path.basename(geo).replace(/\.json$/i, '');

export interface ArquivoRecebido { path: string; size: number; fileName: string }

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
    @Inject(FILA_MINIATURAS) private readonly filaMiniaturas: Fila,
    private readonly pipeline: PipelineService,
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
    return company as { _id: string; customUrl: string };
  }

  async create(arquivo: ArquivoRecebido, body: ImportarDto) {
    const tipo = tipoDe(arquivo.fileName) ?? tipoDe(arquivo.path);
    if (!tipo) {
      await fs.unlink(arquivo.path).catch(() => {});
      throw new BadRequestException(`extensão não suportada em "${arquivo.fileName}" — envie .aq, .zip, .stp, .step ou .ifc`);
    }
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
      ? () => this.processarAq(importId, arquivo, company)
      : () => this.processarCad(importId, arquivo, company, body);
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

  // ── plugin de AutoCAD (S7.17) ─────────────────────────────────────────────

  /** Só inspeciona a DLL (host, plugin, versão, título e categorias do catálogo web). Apaga o upload. */
  async inspecionarPlugin(arquivo: ArquivoRecebido): Promise<PluginInfo> {
    try {
      if (!EXT_DLL.test(arquivo.fileName)) throw new BadRequestException(`"${arquivo.fileName}" não é a DLL do plugin — envie o .dll do bundle (ex. TupyCAD.dll)`);
      const info = await this.pipeline.inspecionarPlugin(arquivo.path);
      return { ...info, arquivo: arquivo.fileName };   // o Python vê o nome temporário do multer
    } catch (e: any) {
      if (e instanceof BadRequestException) throw e;
      throw new BadRequestException(`não li o plugin: ${(e?.message ?? String(e)).split('\n').slice(-3).join(' ').slice(0, 500)}`);
    } finally {
      await fs.unlink(arquivo.path).catch(() => {});
    }
  }

  /**
   * DLL + categoria + dados do formulário → uma importação `plugin` na fila: `catallog.py` baixa os
   * arquivos da categoria para `catallog/<importId>/` e devolve o catálogo, que é publicado como
   * uma biblioteca. O lead só existe no processo filho (JSON temporário) — nunca no Mongo.
   */
  async createPlugin(arquivo: ArquivoRecebido, body: ImportarPluginDto) {
    let company: { _id: string; customUrl: string };
    let info: PluginInfo;
    try {
      if (!EXT_DLL.test(arquivo.fileName)) throw new BadRequestException(`"${arquivo.fileName}" não é a DLL do plugin — envie o .dll do bundle (ex. TupyCAD.dll)`);
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
    const trabalho = () => this.processarCatalogo(importId, company, {
      rotulo: 'catallog.py importar',
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

  // ── biblioteca .aq / .zip ────────────────────────────────────────────────

  private processarAq(importId: string, arquivo: ArquivoRecebido, company: { _id: string; customUrl: string }) {
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
  private async processarCatalogo(importId: string, company: { _id: string; customUrl: string }, o: {
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
    if (paraMiniaturas) await this.gerarMiniaturas(importId, geoDir, paraMiniaturas.geos, paraMiniaturas.porStem); // nunca rejeita
  }

  /**
   * Miniaturas de um import: uma por geometria, gravada em cada produto que a usa. Registra o
   * resultado no documento do import (`thumbCount`, `thumbFailed`, `thumbError`, linha no `note`)
   * e no log. Nunca rejeita.
   */
  private async gerarMiniaturas(importId: string, geoDir: string, geos: string[], porStem: Map<string, string[]>): Promise<ResumoMiniaturas | null> {
    const tag = `[${importId.slice(0, 8)}]`;
    const outDir = path.join(storagePath(), 'thumbs', importId);
    const t0 = Date.now();
    let resumo: ResumoMiniaturas | null = null;
    let erro: string | null = null;
    this.logger.log(`${tag} miniaturas — ${geos.length} geometria(s)`);
    try {
      let n = 0;
      resumo = await this.pipeline.miniaturas({
        geoDir, geos, outDir,
        onMiniatura: () => {
          n++;
          if (n === 1 || n % 50 === 0) this.logger.log(`${tag} thumbs: ${n}/${geos.length} — +${((Date.now() - t0) / 1000).toFixed(1)}s`);
        },
        onFalha: (stem, message) => this.logger.warn(`${tag} miniatura falhou — ${stem}: ${message}`),
      });
      if (resumo.geradas.length) {
        await this.productModel.bulkWrite(resumo.geradas.map((stem) => ({
          updateMany: { filter: { _id: { $in: porStem.get(stem) ?? [] } }, update: { $set: { thumbKey: `thumbs/${importId}/${stem}.webp` } } },
        })));
      }
    } catch (err: any) {
      erro = err?.message ?? String(err);
      this.logger.error(`${tag} ${erro}`);
    }
    const linha = erro ?? descreveResumo(resumo!);
    if (!erro && resumo!.falhas.length) this.logger.warn(`${tag} ${linha}`);
    else if (!erro) this.logger.log(`${tag} ${linha} em ${((Date.now() - t0) / 1000).toFixed(1)}s`);
    try {
      const imp = await this.importModel.findById(importId).select('note').lean().exec();
      const note = imp?.note ? `${imp.note} — ${linha}` : linha;
      await this.importModel.findByIdAndUpdate(importId, {
        note,
        thumbCount: resumo?.geradas.length ?? 0,
        thumbFailed: resumo ? resumo.falhas.length : geos.length,
        ...(erro ? { thumbError: erro } : {}),
        updatedAt: new Date(),
      }).exec();
    } catch (e: any) {
      this.logger.error(`${tag} não registrou o resultado das miniaturas no import — ${e?.message ?? e}`);
    }
    return resumo;
  }

  // ── peça CAD (.stp / .ifc) ───────────────────────────────────────────────

  private async processarCad(importId: string, arquivo: ArquivoRecebido, company: { _id: string; customUrl: string }, body: ImportarDto) {
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
      await this.gerarMiniaturas(importId, path.dirname(geoAbs), [path.basename(geoAbs)], porStem);
    }
  }

  /** Catálogo "Peças STEP/IFC" (upsert por slug) + um produto + geometria no storage. */
  private async publicarCad(importId: string, company: { _id: string; customUrl: string }, fileName: string, body: ImportarDto, geo: StepGeo) {
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

  // ── miniatura de UM produto (após edição — A6) ───────────────────────────

  /**
   * Enfileira a miniatura nova de um produto (a API chama depois do PUT/restaurar). Volta na
   * hora com a posição na fila; o resultado vai para `thumbAtualizadaEm` ou `thumbErro` no produto.
   */
  async regerarMiniatura(productId: string): Promise<{ productId: string; naFrente: number }> {
    const p = await this.productModel.findById(productId).lean().exec();
    if (!p) throw new NotFoundException('produto não encontrado');
    let naFrente = 0;
    this.filaMiniaturas
      .executar(`thumb:${productId}`, () => this.renderizarMiniaturaDoProduto(p as any), (n) => { naFrente = n; })
      .catch((e: any) => this.logger.error(`[${productId.slice(0, 8)}] regeneração escapou — ${e?.message ?? e}`));
    return { productId, naFrente };
  }

  private async renderizarMiniaturaDoProduto(p: { _id: string; importId: string; geoKey: string }) {
    const tag = `[${p._id.slice(0, 8)}]`;
    const geoAbs = path.join(storagePath(), p.geoKey);
    const stem = stemDe(p.geoKey);
    const outDir = path.join(storagePath(), 'thumbs', p.importId);
    let erro: string | null = null;
    try {
      const r = await this.pipeline.miniaturas({ geoDir: path.dirname(geoAbs), geos: [path.basename(geoAbs)], outDir });
      if (r.falhas.length) erro = r.falhas[0].message;
      else if (!r.geradas.length) erro = 'thumbs.mjs terminou sem gerar a miniatura';
    } catch (err: any) {
      erro = err?.message ?? String(err);
    }
    if (erro) this.logger.error(`${tag} miniatura NÃO regerada após edição — ${erro}`);
    else this.logger.log(`${tag} miniatura regerada após edição — thumbs/${p.importId}/${stem}.webp`);
    try {
      await this.productModel.findByIdAndUpdate(p._id, erro
        ? { thumbErro: erro }
        : { thumbKey: `thumbs/${p.importId}/${stem}.webp`, thumbAtualizadaEm: new Date(), thumbErro: null }).exec();
    } catch (e: any) {
      this.logger.error(`${tag} não registrou o resultado da miniatura no produto — ${e?.message ?? e}`);
    }
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
    if (imp.tipo === 'cad' && imp.status === 'publicado') {   // 'aq' e 'plugin' são catálogos inteiros — nada por produto aqui
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

/** Uma linha sobre o diagnóstico do pipeline: só o que não é o esperado (tubos/kits). */
export function descreveDiag(diag: any): string {
  if (!diag) return '';
  const partes: string[] = [];
  if (diag.pecas_sem_simbologia) partes.push(`${diag.pecas_sem_simbologia} peça(s) sem 3D (tubos/kits)`);
  const descartadas = (diag.sim_sem_blob ?? 0) + (diag.sim_nao_oq3d ?? 0) + (diag.sim_ilegivel?.length ?? 0) + (diag.sim_vazia?.length ?? 0);
  if (descartadas) partes.push(`AVISO: ${descartadas} simbologia(s) descartada(s), ${diag.pecas_sim_descartada ?? 0} peça(s) sem 3D por isso`);
  if (diag.avisos?.length) partes.push(`AVISO: ${diag.avisos.length} aviso(s) de parse`);
  return partes.join(' · ');
}

export function descreveResumo(r: ResumoMiniaturas): string {
  return r.falhas.length
    ? `${r.geradas.length} de ${r.total} miniatura(s) geradas — ${r.falhas.length} falharam`
    : `${r.geradas.length} miniatura(s) geradas`;
}
