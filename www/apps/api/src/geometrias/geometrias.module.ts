import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { GeometryStoreModule } from '../geometry-store/geometry-store.module';
import { BimProduct, BimProductSchema } from '../bim-products/bim-products.schema';
import { ImportacoesModule } from '../importacoes/importacoes.module';
import { GeometriasController } from './geometrias.controller';

@Module({
  imports: [
    MongooseModule.forFeature([{ name: BimProduct.name, schema: BimProductSchema }]),
    GeometryStoreModule,
    ImportacoesModule, // thumb-worker para regerar a miniatura após PUT/restaurar (I14)
  ],
  controllers: [GeometriasController],
})
export class GeometriasModule {}
