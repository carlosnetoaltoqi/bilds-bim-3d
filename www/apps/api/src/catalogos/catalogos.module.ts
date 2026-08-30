import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { CatalogosController } from './catalogos.controller';
import { Company, CompanySchema } from '../companies/companies.schema';
import { BimCatalog, BimCatalogSchema } from '../bim-catalogs/bim-catalogs.schema';
import { BimProduct, BimProductSchema } from '../bim-products/bim-products.schema';

@Module({
  imports: [
    MongooseModule.forFeature([
      { name: Company.name, schema: CompanySchema },
      { name: BimCatalog.name, schema: BimCatalogSchema },
      { name: BimProduct.name, schema: BimProductSchema },
    ]),
  ],
  controllers: [CatalogosController],
})
export class CatalogosModule {}
