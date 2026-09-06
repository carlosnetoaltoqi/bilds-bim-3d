import { Module } from '@nestjs/common';
import { APP_GUARD } from '@nestjs/core';
import { MongooseModule } from '@nestjs/mongoose';
import { GeometryStoreModule, MongoProntoGuard } from '@bim/dominio';
import { HealthController } from './health/health.controller';
import { ImportacoesModule } from './importacoes/importacoes.module';
import { MiniaturasModule } from './miniaturas/miniaturas.module';
import { ExportacaoModule } from './exportacao/exportacao.module';

@Module({
  imports: [
    MongooseModule.forRoot(
      process.env.MONGODB_URI ?? (() => { throw new Error('MONGODB_URI env var is required'); })(),
      { dbName: process.env.MONGODB_DB ?? 'bilds-bim-3d' },
    ),
    GeometryStoreModule,
    ImportacoesModule,
    MiniaturasModule,
    ExportacaoModule,
  ],
  controllers: [HealthController],
  // I32: Mongo fora → 503 na hora em toda rota (menos /health), em vez de 500 após 30 s
  providers: [{ provide: APP_GUARD, useClass: MongoProntoGuard }],
})
export class AppModule {}
