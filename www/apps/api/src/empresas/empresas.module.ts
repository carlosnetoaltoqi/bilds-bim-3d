import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { EmpresasController } from './empresas.controller';
import { Company, CompanySchema } from '@bim/dominio';
import { BimCatalog, BimCatalogSchema } from '@bim/dominio';

@Module({
  imports: [
    MongooseModule.forFeature([
      { name: Company.name, schema: CompanySchema },
      { name: BimCatalog.name, schema: BimCatalogSchema },
    ]),
  ],
  controllers: [EmpresasController],
})
export class EmpresasModule {}
