import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { BimImport, BimImportSchema } from '../bim-imports/bim-imports.schema';
import { BimCatalog, BimCatalogSchema } from '../bim-catalogs/bim-catalogs.schema';
import { BimProduct, BimProductSchema } from '../bim-products/bim-products.schema';
import { Company, CompanySchema } from '../companies/companies.schema';
import { GeometryStoreModule } from '../geometry-store/geometry-store.module';
import { ImportacoesModule } from '../importacoes/importacoes.module';
import { StepController } from './step.controller';
import { StepService } from './step.service';

@Module({
  imports: [
    MongooseModule.forFeature([
      { name: BimImport.name, schema: BimImportSchema },
      { name: BimCatalog.name, schema: BimCatalogSchema },
      { name: BimProduct.name, schema: BimProductSchema },
      { name: Company.name, schema: CompanySchema },
    ]),
    GeometryStoreModule,
    ImportacoesModule,
  ],
  controllers: [StepController],
  providers: [StepService],
})
export class StepModule {}
