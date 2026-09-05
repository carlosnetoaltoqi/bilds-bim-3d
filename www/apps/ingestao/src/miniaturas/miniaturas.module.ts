import { Module } from '@nestjs/common';
import { MiniaturasController } from './miniaturas.controller';
import { ImportacoesModule } from '../importacoes/importacoes.module';

@Module({
  imports: [ImportacoesModule],
  controllers: [MiniaturasController],
})
export class MiniaturasModule {}
