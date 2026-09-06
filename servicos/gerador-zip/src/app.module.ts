import { Module } from '@nestjs/common';
import { Biblioteca } from '@bim/base';
import { HealthController } from './health.controller';
import { ZipController } from './zip.controller';

/** Sem MongooseModule, sem GeometryStore, sem guarda de Mongo: o gerador de ZIP é stateless. */
@Module({
  controllers: [ZipController, HealthController],
  providers: [{ provide: Biblioteca, useFactory: () => new Biblioteca() }],
})
export class AppModule {}
