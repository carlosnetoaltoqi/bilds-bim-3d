import { BadRequestException, Injectable, Logger, NotFoundException } from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import { BimCatalog, BimCatalogDocument, BimProduct, BimProductDocument, storagePath } from '@bim/dominio';
import { PipelineService, ManifestoCatalogoAq } from '../pipeline/pipeline.service';

/**
 * ExportacaoService — o catálogo salvo (Mongo + storage) vira um `.aq` novo do AltoQi Builder, gerado
 * do zero pelo `catalogo_para_aq` da biblioteca. Sai tudo o que a tela de edição mostra. O arquivo é
 * temporário: quem chama serve como download e apaga. (O ZIP da bilds.com é do gerador-zip, S8/F3.)
 */
@Injectable()
export class ExportacaoService {
  private readonly logger = new Logger(ExportacaoService.name);

  constructor(
    @InjectModel(BimCatalog.name) private readonly catalogModel: Model<BimCatalogDocument>,
    @InjectModel(BimProduct.name) private readonly productModel: Model<BimProductDocument>,
    private readonly pipeline: PipelineService,
  ) {}

  async catalogoParaAq(catalogId: string): Promise<{ path: string; nomeArquivo: string; resumo: Record<string, any> }> {
    const cat = await this.catalogModel.findById(catalogId).lean().exec();
    if (!cat) throw new NotFoundException(`catálogo "${catalogId}" não encontrado`);
    // ordem natural = ordem de inserção do import (a ordem das peças no .aq de origem)
    const produtos = await this.productModel.find({ catalogId }).lean().exec();
    if (!produtos.length) throw new BadRequestException(`o catálogo "${cat.title}" não tem produtos — nada a exportar`);

    const manifesto: ManifestoCatalogoAq = {
      catalogo: {
        fabricante: cat.manufacturer,
        titulo: cat.title,
        slug: cat.slug,
        origem: `bilds-bim-3d — catálogo ${cat.slug} exportado em ${new Date().toISOString()}`,
      },
      geo_dir: storagePath(),
      produtos: produtos.map((p) => ({
        id: p.id,
        nome: p.nome,
        serie: p.serie ?? '',
        conexoes: p.conexoes ?? '',
        specs: p.specs ?? {},
        curva: p.curva ?? null,
        potencia: p.potencia ?? null,
        geo: p.geoKey,
      })),
    };
    const tag = `[${catalogId.slice(0, 8)}]`;
    const t0 = Date.now();
    this.logger.log(`${tag} exportar .aq — ${cat.manufacturer} / ${cat.title}: ${produtos.length} produtos`);
    const r = await this.pipeline.catalogoParaAq(manifesto, (linha) => this.logger.log(`${tag} ${linha}`));
    this.logger.log(`${tag} .aq gerado — ${r.resumo.pecas} peças, ${r.resumo.simbologias} simbologias, ${(r.resumo.bytes / 1024 / 1024).toFixed(1)} MB em ${((Date.now() - t0) / 1000).toFixed(1)}s`);
    return { ...r, nomeArquivo: nomeDoArquivoAq(cat.manufacturer, cat.title) };
  }
}

/** `pecas_Amanco_Esgoto_SN_SR_Silentium.aq` — o padrão dos arquivos do AltoQi, só ASCII (vai num header). */
export function nomeDoArquivoAq(fabricante: string, titulo: string): string {
  const limpo = (s: string) => (s ?? '')
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[^A-Za-z0-9.-]+/g, '_').replace(/^_+|_+$/g, '');
  return `pecas_${[limpo(fabricante), limpo(titulo)].filter(Boolean).join('_') || 'catalogo'}.aq`;
}
