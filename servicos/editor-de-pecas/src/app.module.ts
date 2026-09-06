import { Module } from '@nestjs/common';
import { APP_GUARD } from '@nestjs/core';
import { MongooseModule } from '@nestjs/mongoose';
import { GeometryStoreModule, MongoProntoGuard } from '@bim/dominio';
import { EdicaoModule } from './edicao.module';
import { HealthController } from './health.controller';

@Module({
  imports: [
    MongooseModule.forRoot(
      process.env.MONGODB_URI ?? (() => { throw new Error('MONGODB_URI env var is required'); })(),
      { dbName: process.env.MONGODB_DB ?? 'bilds-bim-3d' },
    ),
    GeometryStoreModule,
    EdicaoModule,
  ],
  controllers: [HealthController],
  // I32: Mongo fora → 503 na hora em toda rota (menos /health)
  providers: [{ provide: APP_GUARD, useClass: MongoProntoGuard }],
})
export class AppModule {}
