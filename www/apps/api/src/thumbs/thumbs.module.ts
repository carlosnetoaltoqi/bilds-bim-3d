import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { ThumbsController } from './thumbs.controller';
import { BimProduct, BimProductSchema } from '../bim-products/bim-products.schema';
import { GeometryStoreModule } from '../geometry-store/geometry-store.module';

@Module({
  imports: [
    MongooseModule.forFeature([{ name: BimProduct.name, schema: BimProductSchema }]),
    GeometryStoreModule,
  ],
  controllers: [ThumbsController],
})
export class ThumbsModule {}
