import { Module } from '@nestjs/common';
import { CadController } from './cad.controller';
import { ImportacoesModule } from '../importacoes/importacoes.module';

@Module({
  imports: [ImportacoesModule], // PipelineService
  controllers: [CadController],
})
export class CadModule {}
