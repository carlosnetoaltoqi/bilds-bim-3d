import {
  Controller,
  Get,
  Param,
  Query,
  NotFoundException,
} from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import { Company, CompanyDocument } from '../companies/companies.schema';
import { BimCatalog, BimCatalogDocument } from '../bim-catalogs/bim-catalogs.schema';
import { BimProduct, BimProductDocument } from '../bim-products/bim-products.schema';

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
      })),
    };
  }
}
