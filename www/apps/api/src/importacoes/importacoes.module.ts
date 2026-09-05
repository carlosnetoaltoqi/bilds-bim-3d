import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { ImportacoesController } from './importacoes.controller';
import { ImportacoesService } from './importacoes.service';
import { RecuperacaoService } from './recuperacao.service';
import { FILA_IMPORTACOES, Fila, concorrenciaDoEnv } from '../common/fila';
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
  providers: [
    ImportacoesService,
    RecuperacaoService, // no boot marca `falhou` os imports que a queda anterior deixou abertos (I11)
    // uma fila para .aq e CAD: concorrência IMPORTACOES_CONCORRENCIA (padrão 1)
    { provide: FILA_IMPORTACOES, useFactory: () => new Fila(concorrenciaDoEnv()) },
  ],
  exports: [ImportacoesService, FILA_IMPORTACOES],
})
export class ImportacoesModule {}
