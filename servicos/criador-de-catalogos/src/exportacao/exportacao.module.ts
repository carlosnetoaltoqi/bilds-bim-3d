import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { BimCatalog, BimCatalogSchema, BimProduct, BimProductSchema } from '@bim/dominio';
import { ExportacaoController } from './exportacao.controller';
import { ExportacaoService } from './exportacao.service';
import { PipelineService } from '../pipeline/pipeline.service';

@Module({
  imports: [
    MongooseModule.forFeature([
      { name: BimCatalog.name, schema: BimCatalogSchema },
      { name: BimProduct.name, schema: BimProductSchema },
    ]),
  ],
  controllers: [ExportacaoController],
  providers: [ExportacaoService, PipelineService],
})
export class ExportacaoModule {}
