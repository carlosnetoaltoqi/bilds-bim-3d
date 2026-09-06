import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { BimCatalog, BimCatalogSchema, BimProduct, BimProductSchema, GeometryStoreModule } from '@bim/dominio';
import { CriadorClient } from './criador-client';
import { GeometriasEdicaoController } from './geometrias-edicao.controller';
import { ProdutosEdicaoController } from './produtos-edicao.controller';

@Module({
  imports: [
    MongooseModule.forFeature([
      { name: BimProduct.name, schema: BimProductSchema },
      { name: BimCatalog.name, schema: BimCatalogSchema },
    ]),
    GeometryStoreModule,
  ],
  controllers: [GeometriasEdicaoController, ProdutosEdicaoController],
  providers: [CriadorClient], // pede ao criador a miniatura nova após PUT/restaurar (ADR-006)
})
export class EdicaoModule {}
