import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { ThumbsController } from './thumbs.controller';
import { BimProduct, BimProductSchema } from '@bim/dominio';
import { GeometryStoreModule } from '@bim/dominio';

@Module({
  imports: [
    MongooseModule.forFeature([{ name: BimProduct.name, schema: BimProductSchema }]),
    GeometryStoreModule,
  ],
  controllers: [ThumbsController],
})
export class ThumbsModule {}
