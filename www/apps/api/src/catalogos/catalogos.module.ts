import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { CatalogosController } from './catalogos.controller';
import { Company, CompanySchema } from '@bim/dominio';
import { BimCatalog, BimCatalogSchema } from '@bim/dominio';
import { BimProduct, BimProductSchema } from '@bim/dominio';

@Module({
  imports: [
    MongooseModule.forFeature([
      { name: Company.name, schema: CompanySchema },
      { name: BimCatalog.name, schema: BimCatalogSchema },
      { name: BimProduct.name, schema: BimProductSchema },
    ]),
  ],
  controllers: [CatalogosController],
})
export class CatalogosModule {}
