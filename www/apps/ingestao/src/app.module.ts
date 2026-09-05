import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { GeometryStoreModule } from '@bim/dominio';
import { HealthController } from './health/health.controller';
import { ImportacoesModule } from './importacoes/importacoes.module';
import { CadModule } from './cad/cad.module';
import { MiniaturasModule } from './miniaturas/miniaturas.module';

@Module({
  imports: [
    MongooseModule.forRoot(
      process.env.MONGODB_URI ?? (() => { throw new Error('MONGODB_URI env var is required'); })(),
      { dbName: process.env.MONGODB_DB ?? 'bilds-bim-3d' },
    ),
    GeometryStoreModule,
    ImportacoesModule,
    CadModule,
    MiniaturasModule,
  ],
  controllers: [HealthController],
})
export class AppModule {}
