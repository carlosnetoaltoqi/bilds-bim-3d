import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { BimProduct, BimProductSchema, GeometryStoreModule } from '@bim/dominio';
import { GeometriasController } from './geometrias.controller';

@Module({
  imports: [
    MongooseModule.forFeature([{ name: BimProduct.name, schema: BimProductSchema }]),
    GeometryStoreModule,
  ],
  controllers: [GeometriasController],
})
export class GeometriasModule {}
