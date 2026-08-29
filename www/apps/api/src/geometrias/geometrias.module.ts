import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { GeometryStoreModule } from '../geometry-store/geometry-store.module';
import { BimProduct, BimProductSchema } from '../bim-products/bim-products.schema';
import { GeometriasController } from './geometrias.controller';

@Module({
  imports: [
    MongooseModule.forFeature([{ name: BimProduct.name, schema: BimProductSchema }]),
    GeometryStoreModule,
  ],
  controllers: [GeometriasController],
})
export class GeometriasModule {}
