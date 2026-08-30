import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { ImportacoesController } from './importacoes.controller';
import { ImportacoesService } from './importacoes.service';
import { BimImport, BimImportSchema } from '../bim-imports/bim-imports.schema';
import { BimCatalog, BimCatalogSchema } from '../bim-catalogs/bim-catalogs.schema';
import { BimProduct, BimProductSchema } from '../bim-products/bim-products.schema';
import { Company, CompanySchema } from '../companies/companies.schema';
import { GeometryStoreModule } from '../geometry-store/geometry-store.module';

@Module({
  imports: [
    MongooseModule.forFeature([
      { name: BimImport.name, schema: BimImportSchema },
      { name: BimCatalog.name, schema: BimCatalogSchema },
      { name: BimProduct.name, schema: BimProductSchema },
      { name: Company.name, schema: CompanySchema },
    ]),
    GeometryStoreModule,
  ],
  controllers: [ImportacoesController],
  providers: [ImportacoesService],
})
export class ImportacoesModule {}
