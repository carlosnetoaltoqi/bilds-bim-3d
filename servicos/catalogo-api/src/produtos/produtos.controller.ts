import { Controller, Delete, Get, Inject, Logger, NotFoundException, Param } from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import { BimCatalog, BimCatalogDocument, BimImport, BimImportDocument, BimProduct, BimProductDocument, Company, CompanyDocument, IGeometryStore, NaoEncontrado, apagarProduto } from '@bim/dominio';

/**
 * Leitura e remoção de um produto (API de catálogo).
 *
 * GET   /produtos/:id   — documento completo, com `infoOriginal` quando já editado e
 *                         `thumbAtualizadaEm`/`thumbErro` da última regeneração da miniatura
 * DELETE /produtos/:id  — apaga o produto; a geometria e a miniatura só se nenhum outro produto as usa
 *
 * O `PATCH` (edição das informações) é do editor de peças (:4400, ADR-014).
 */

@Controller('produtos')
export class ProdutosController {
  constructor(
    @InjectModel(BimProduct.name) private readonly productModel: Model<BimProductDocument>,
    @InjectModel(BimCatalog.name) private readonly catalogModel: Model<BimCatalogDocument>,
    @InjectModel(BimImport.name) private readonly importModel: Model<BimImportDocument>,
    @InjectModel(Company.name) private readonly companyModel: Model<CompanyDocument>,
    @Inject('GEOMETRY_STORE') private readonly store: IGeometryStore,
  ) {}

  private readonly logger = new Logger(ProdutosController.name);

  @Delete(':id')
  async apagar(@Param('id') id: string) {
    try {
      const r = await apagarProduto(
        { companies: this.companyModel as any, catalogs: this.catalogModel as any, products: this.productModel as any, imports: this.importModel as any },
        this.store, id,
      );
      this.logger.log(`produto ${id} apagado — ${r.arquivos.length} arquivo(s)${r.avisos.length ? ` (${r.avisos.length} avisos)` : ''}`);
      for (const a of r.avisos) this.logger.warn(a);
      return { ok: true, productId: id, ...r };
    } catch (e) {
      if (e instanceof NaoEncontrado) throw new NotFoundException(e.message);
      throw e;
    }
  }

  @Get(':id')
  async get(@Param('id') id: string) {
    const p = await this.productModel.findById(id).lean().exec();
    if (!p) throw new NotFoundException('produto não encontrado');
    return this.toDto(p);
  }

  private toDto(p: any) {
    return {
      _id: p._id,
      catalogId: p.catalogId,
      importId: p.importId,
      id: p.id,
      nome: p.nome,
      serie: p.serie,
      specs: p.specs ?? {},
      curva: p.curva ?? null,
      potencia: p.potencia ?? null,
      conexoes: p.conexoes ?? null,
      geoKey: p.geoKey,
      geoUrl: `/geometrias/${p._id}`,
      thumbUrl: p.thumbKey ? `/thumbs/${p._id}` : null,
      editadoEm: p.editadoEm ?? null,
      geoEditadoEm: p.geoEditadoEm ?? null,
      // I14 grava os dois no produto; até a S7.13 o DTO não os devolvia e a edição parecia não regerar a miniatura
      thumbAtualizadaEm: p.thumbAtualizadaEm ?? null,
      thumbErro: p.thumbErro ?? null,
      infoOriginal: p.infoOriginal ?? null,
      createdAt: p.createdAt,
    };
  }
}
