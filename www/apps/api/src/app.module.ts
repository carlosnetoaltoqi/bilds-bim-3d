import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { HealthController } from './health/health.controller';
import { GeometryStoreModule } from './geometry-store/geometry-store.module';
import { GeometriasModule } from './geometrias/geometrias.module';
import { ImportacoesModule } from './importacoes/importacoes.module';
import { CatalogosModule } from './catalogos/catalogos.module';
import { ThumbsModule } from './thumbs/thumbs.module';
import { AuthModule } from './auth/auth.module';
import { EmpresasModule } from './empresas/empresas.module';
import { Company, CompanySchema } from './companies/companies.schema';
import { BimCatalog, BimCatalogSchema } from './bim-catalogs/bim-catalogs.schema';
import { BimProduct, BimProductSchema } from './bim-products/bim-products.schema';
import { BimImport, BimImportSchema } from './bim-imports/bim-imports.schema';

@Module({
  imports: [
    MongooseModule.forRoot(
      process.env.MONGODB_URI ?? (() => { throw new Error('MONGODB_URI env var is required'); })(),
      { dbName: process.env.MONGODB_DB ?? 'bilds-bim-3d' },
    ),
    GeometryStoreModule,
    GeometriasModule,
    ImportacoesModule,
    CatalogosModule,
    ThumbsModule,
    AuthModule,
    EmpresasModule,
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
