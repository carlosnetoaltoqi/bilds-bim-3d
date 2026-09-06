import { Module } from '@nestjs/common';
import { Biblioteca } from '@bim/base';
import { ConversoresController } from './conversores.controller';
import { HealthController } from './health.controller';

/** Sem MongooseModule, sem GeometryStore: os conversores são stateless. */
@Module({
  controllers: [ConversoresController, HealthController],
  providers: [{ provide: Biblioteca, useFactory: () => new Biblioteca() }],
})
export class AppModule {}
