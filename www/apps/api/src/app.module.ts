/**
 * API de catálogo — leitura e edição (docs/arquitetura-www-servico-de-ingestao.md).
 * Importar biblioteca/peça, converter CAD e renderizar miniatura são do serviço de
 * ingestão (apps/ingestao, :4100); esta API só pede a miniatura nova depois de uma
 * edição de geometria (common/ingestao-client.ts).
 */
import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { HealthController } from './health/health.controller';
import { GeometryStoreModule } from '@bim/dominio';
import { GeometriasModule } from './geometrias/geometrias.module';
import { CatalogosModule } from './catalogos/catalogos.module';
import { ThumbsModule } from './thumbs/thumbs.module';
import { EmpresasModule } from './empresas/empresas.module';
import { ProdutosModule } from './produtos/produtos.module';
import { Company, CompanySchema } from '@bim/dominio';
import { BimCatalog, BimCatalogSchema } from '@bim/dominio';
import { BimProduct, BimProductSchema } from '@bim/dominio';
import { BimImport, BimImportSchema } from '@bim/dominio';

@Module({
  imports: [
    MongooseModule.forRoot(
      process.env.MONGODB_URI ?? (() => { throw new Error('MONGODB_URI env var is required'); })(),
      { dbName: process.env.MONGODB_DB ?? 'bilds-bim-3d' },
    ),
    GeometryStoreModule,
    GeometriasModule,
    CatalogosModule,
    ThumbsModule,
    EmpresasModule,
    ProdutosModule,
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
