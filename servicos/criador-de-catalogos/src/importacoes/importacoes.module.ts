import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { BimCatalog, BimCatalogSchema, BimImport, BimImportSchema, BimProduct, BimProductSchema, Company, CompanySchema, GeometryStoreModule } from '@bim/dominio';
import { ImportacoesController } from './importacoes.controller';
import { ImportacoesService } from './importacoes.service';
import { RecuperacaoService } from './recuperacao.service';
import { FILA_IMPORTACOES, FILA_MINIATURAS, Fila, concorrenciaDoEnv } from './fila';
import { PipelineService } from '../pipeline/pipeline.service';
import { PublicacaoService } from '../publicacao/publicacao.service';
import { MiniaturasService } from '../miniaturas/miniaturas.service';

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
    PublicacaoService,
    MiniaturasService,
    PipelineService,
    RecuperacaoService, // no boot marca `falhou` os imports que a queda anterior deixou abertos (I11)
    // uma fila para .aq e CAD: concorrência IMPORTACOES_CONCORRENCIA (padrão 1) — um Python + um Chromium por vez
    { provide: FILA_IMPORTACOES, useFactory: () => new Fila(concorrenciaDoEnv()) },
    // regeneração de miniatura após edição: fila própria, para não esperar um import de minutos
    { provide: FILA_MINIATURAS, useFactory: () => new Fila(1) },
  ],
  exports: [ImportacoesService, MiniaturasService, PipelineService, FILA_IMPORTACOES, FILA_MINIATURAS],
})
export class ImportacoesModule {}
