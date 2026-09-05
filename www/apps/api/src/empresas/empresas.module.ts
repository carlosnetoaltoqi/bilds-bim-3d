import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { EmpresasController } from './empresas.controller';
import { Company, CompanySchema } from '../companies/companies.schema';
import { BimCatalog, BimCatalogSchema } from '../bim-catalogs/bim-catalogs.schema';

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
