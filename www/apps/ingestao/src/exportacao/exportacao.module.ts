import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { BimCatalog, BimCatalogSchema, BimProduct, BimProductSchema } from '@bim/dominio';
import { ExportacaoController } from './exportacao.controller';
import { ExportacaoService } from './exportacao.service';
import { ImportacoesModule } from '../importacoes/importacoes.module';

@Module({
  imports: [
    MongooseModule.forFeature([
      { name: BimCatalog.name, schema: BimCatalogSchema },
      { name: BimProduct.name, schema: BimProductSchema },
    ]),
    ImportacoesModule, // PipelineService
  ],
  controllers: [ExportacaoController],
  providers: [ExportacaoService],
})
export class ExportacaoModule {}
