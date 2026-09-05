import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { BimProduct, BimProductSchema } from '@bim/dominio';
import { BimCatalog, BimCatalogSchema } from '@bim/dominio';
import { ProdutosController } from './produtos.controller';

@Module({
  imports: [
    MongooseModule.forFeature([
      { name: BimProduct.name, schema: BimProductSchema },
      { name: BimCatalog.name, schema: BimCatalogSchema },
    ]),
  ],
  controllers: [ProdutosController],
})
export class ProdutosModule {}
