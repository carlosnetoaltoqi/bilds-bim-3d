import {
  BadRequestException,
  Body,
  Controller,
  Get,
  Param,
  Patch,
  Query,
  NotFoundException,
} from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import { Company, CompanyDocument } from '../companies/companies.schema';
import { BimCatalog, BimCatalogDocument } from '../bim-catalogs/bim-catalogs.schema';
import { BimProduct, BimProductDocument } from '../bim-products/bim-products.schema';
import { PatchCatalogoDto } from './patch-catalogo.dto';

@Controller('catalogos')
export class CatalogosController {
  constructor(
    @InjectModel(Company.name) private readonly companyModel: Model<CompanyDocument>,
    @InjectModel(BimCatalog.name) private readonly catalogModel: Model<BimCatalogDocument>,
    @InjectModel(BimProduct.name) private readonly productModel: Model<BimProductDocument>,
  ) {}

  @Get(':empresa/:slug')
  async get(
    @Param('empresa') empresa: string,
    @Param('slug') slug: string,
    @Query('serie') serie?: string,
  ) {
    const company = await this.companyModel.findOne({ customUrl: empresa }).lean().exec();
    if (!company) throw new NotFoundException(`empresa "${empresa}" não encontrada`);

    const catalog = await this.catalogModel
      .findOne({ companyId: company._id, slug })
      .lean()
      .exec();
    if (!catalog) throw new NotFoundException(`catálogo "${slug}" não encontrado`);

    const filter: Record<string, any> = { catalogId: catalog._id };
    if (serie) filter['serie'] = serie;

    const products = await this.productModel.find(filter).lean().exec();

    return {
      catalog: {
        id: catalog._id,
        slug: catalog.slug,
        title: catalog.title,
        manufacturer: catalog.manufacturer,
        layout: catalog.layout,
        filters: catalog.filters,
        productCount: catalog.productCount,
        createdAt: catalog.createdAt,
      },
      products: products.map((p) => ({
        _id: p._id,
        id: p.id,
        nome: p.nome,
        serie: p.serie,
        specs: p.specs,
        curva: p.curva,
        potencia: p.potencia,
        conexoes: p.conexoes,
        geoUrl: `/geometrias/${p._id}`,
        thumbUrl: p.thumbKey ? `/thumbs/${p._id}` : null,
        editadoEm: (p as any).editadoEm ?? null,
        geoEditadoEm: (p as any).geoEditadoEm ?? null,
      })),
    };
  }

  /**
   * Edição dos metadados do catálogo (POC de edição — sem auth).
   * Aceita title, manufacturer e layout ('series-rows' | 'catalog-grid').
   */
  @Patch(':catalogId')
  async patch(
    @Param('catalogId') catalogId: string,
    @Body() body: PatchCatalogoDto, // tipos e limites no DTO, aplicados pelo ValidationPipe (I16)
  ) {
    const catalog = await this.catalogModel.findById(catalogId).lean().exec();
    if (!catalog) throw new NotFoundException('catálogo não encontrado');

    const set: Record<string, string> = {};
    if (body.title !== undefined) set.title = body.title;
    if (body.manufacturer !== undefined) set.manufacturer = body.manufacturer;
    if (body.layout !== undefined) set.layout = body.layout;
    if (Object.keys(set).length === 0) throw new BadRequestException('nenhum campo editável no corpo');

    const atualizado = await this.catalogModel.findByIdAndUpdate(catalogId, { $set: set }, { new: true }).lean().exec();
    return {
      id: atualizado!._id,
      slug: atualizado!.slug,
      title: atualizado!.title,
      manufacturer: atualizado!.manufacturer,
      layout: atualizado!.layout,
      filters: atualizado!.filters,
      productCount: atualizado!.productCount,
    };
  }
}
