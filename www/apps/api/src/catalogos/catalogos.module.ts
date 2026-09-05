import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { CatalogosController } from './catalogos.controller';
import { BimCatalog, BimCatalogSchema, BimImport, BimImportSchema, BimProduct, BimProductSchema, Company, CompanySchema, GeometryStoreModule } from '@bim/dominio';

@Module({
  imports: [
    MongooseModule.forFeature([
      { name: Company.name, schema: CompanySchema },
      { name: BimCatalog.name, schema: BimCatalogSchema },
      { name: BimProduct.name, schema: BimProductSchema },
      { name: BimImport.name, schema: BimImportSchema },
    ]),
    GeometryStoreModule, // apagar em cascata limpa geometria e miniaturas (remocao.ts)
  ],
  controllers: [CatalogosController],
})
export class CatalogosModule {}
