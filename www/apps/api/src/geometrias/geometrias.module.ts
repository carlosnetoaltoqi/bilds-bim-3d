import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { BimProduct, BimProductSchema, GeometryStoreModule } from '@bim/dominio';
import { GeometriasController } from './geometrias.controller';
import { IngestaoClient } from '../common/ingestao-client';

@Module({
  imports: [
    MongooseModule.forFeature([{ name: BimProduct.name, schema: BimProductSchema }]),
    GeometryStoreModule,
  ],
  controllers: [GeometriasController],
  providers: [IngestaoClient], // pede ao serviço de ingestão a miniatura nova após PUT/restaurar (I14, A6)
})
export class GeometriasModule {}
