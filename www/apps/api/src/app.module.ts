import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { HealthController } from './health/health.controller';
import { Company, CompanySchema } from './companies/companies.schema';
import { BimCatalog, BimCatalogSchema } from './bim-catalogs/bim-catalogs.schema';
import { BimProduct, BimProductSchema } from './bim-products/bim-products.schema';
import { BimImport, BimImportSchema } from './bim-imports/bim-imports.schema';

@Module({
  imports: [
    MongooseModule.forRoot(process.env.MONGODB_URI as string),
    MongooseModule.forFeature([
      { name: Company.name, schema: CompanySchema },
      { name: BimCatalog.name, schema: BimCatalogSchema },
      { name: BimProduct.name, schema: BimProductSchema },
      { name: BimImport.name, schema: BimImportSchema },
    ]),
  ],
  controllers: [HealthController],
})
export class AppModule {}
