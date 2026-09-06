import {
  Controller,
  Delete,
  Post,
  Get,
  Inject,
  Logger,
  Param,
  Body,
  UseInterceptors,
  UploadedFile,
  NotFoundException,
  ConflictException,
  Res,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import * as path from 'path';
import * as fs from 'fs';
import { Response } from 'express';
import { BimCatalog, BimCatalogDocument, BimImport, BimImportDocument, BimProduct, BimProductDocument, Company, CompanyDocument, IGeometryStore, NaoEncontrado, apagarEmpresa, storagePath } from '@bim/dominio';
import { CriarEmpresaDto } from './criar-empresa.dto';

/**
 * Empresas (organizações) — sem auth (A7 de docs/arquitetura-www-servico-de-ingestao.md).
 *
 * GET  /empresas                      — todas, com a quantidade de catálogos
 * POST /empresas                      — cria (multipart: name, customUrl, logo?)
 * GET  /empresas/:customUrl           — uma, com os catálogos
 * GET  /empresas/:customUrl/catalogos — só os catálogos
 * GET  /logos/:companyId              — o logo
 * DELETE /empresas/:customUrl        — apaga a empresa com catálogos, produtos, imports, storage e logo
 *
 * A empresa é só um agrupador de catálogos: quem importa escolhe por `customUrl`.
 */
@Controller()
export class EmpresasController {
  private readonly storageBase: string;

  constructor(
    @InjectModel(Company.name) private readonly companyModel: Model<CompanyDocument>,
    @InjectModel(BimCatalog.name) private readonly catalogModel: Model<BimCatalogDocument>,
    @InjectModel(BimProduct.name) private readonly productModel: Model<BimProductDocument>,
    @InjectModel(BimImport.name) private readonly importModel: Model<BimImportDocument>,
    @Inject('GEOMETRY_STORE') private readonly store: IGeometryStore,
  ) {
    this.storageBase = storagePath(); // mesma raiz do DiskGeometryStore (I17)
  }

  private readonly logger = new Logger(EmpresasController.name);

  @Delete('empresas/:customUrl')
  async apagar(@Param('customUrl') customUrl: string) {
    const company = await this.companyModel.findOne({ customUrl }).lean().exec();
    if (!company) throw new NotFoundException(`empresa "${customUrl}" não encontrada`);
    try {
      const r = await apagarEmpresa(
        { companies: this.companyModel as any, catalogs: this.catalogModel as any, products: this.productModel as any, imports: this.importModel as any },
        this.store, company._id,
      );
      this.logger.log(`empresa ${customUrl} apagada — ${r.catalogos} catálogos, ${r.produtos} produtos, ${r.imports} imports${r.avisos.length ? ` (${r.avisos.length} avisos)` : ''}`);
      for (const a of r.avisos) this.logger.warn(a);
      return { ok: true, customUrl, ...r };
    } catch (e) {
      if (e instanceof NaoEncontrado) throw new NotFoundException(e.message);
      throw e;
    }
  }

  @Get('empresas')
  async listar() {
    const companies = await this.companyModel.find().sort({ createdAt: 1 }).lean().exec();
    const catalogos = await this.catalogModel.find().select('companyId').lean().exec();
    const porEmpresa = new Map<string, number>();
    for (const c of catalogos) porEmpresa.set(c.companyId, (porEmpresa.get(c.companyId) ?? 0) + 1);
    return companies.map((c) => ({ ...this.toDto(c), catalogCount: porEmpresa.get(c._id) ?? 0 }));
  }

  @Post('empresas')
  @UseInterceptors(FileInterceptor('logo', { limits: { fileSize: 2 * 1024 * 1024 } }))
  async create(
    @UploadedFile() logo: Express.Multer.File | undefined,
    @Body() body: CriarEmpresaDto, // obrigatoriedade e tamanho no DTO (I16)
  ) {
    const slug = body.customUrl.toLowerCase().replace(/[^a-z0-9-]/g, '-');
    const existing = await this.companyModel.findOne({ customUrl: slug }).lean().exec();
    if (existing) throw new ConflictException(`URL "${slug}" já está em uso`);

    const companyId = crypto.randomUUID();

    let logoKey: string | undefined;
    if (logo) {
      const ext = this.inferExt(logo.mimetype, logo.originalname);
      logoKey = `logos/${companyId}${ext}`;
      const logoPath = path.join(this.storageBase, logoKey);
      fs.mkdirSync(path.dirname(logoPath), { recursive: true });
      fs.writeFileSync(logoPath, logo.buffer);
    }

    const company = await this.companyModel.create({
      _id: companyId,
      name: body.name,
      customUrl: slug,
      logoKey,
    });
    return this.toDto(company.toObject());
  }

  @Get('empresas/:customUrl')
  async uma(@Param('customUrl') customUrl: string) {
    const company = await this.companyModel.findOne({ customUrl }).lean().exec();
    if (!company) throw new NotFoundException(`empresa "${customUrl}" não encontrada`);
    return { ...this.toDto(company), catalogos: await this.catalogosDe(company._id) };
  }

  @Get('empresas/:customUrl/catalogos')
  async catalogos(@Param('customUrl') customUrl: string) {
    const company = await this.companyModel.findOne({ customUrl }).lean().exec();
    if (!company) throw new NotFoundException(`empresa "${customUrl}" não encontrada`);
    return this.catalogosDe(company._id);
  }

  @Get('logos/:companyId')
  async logo(@Param('companyId') companyId: string, @Res() res: Response) {
    const company = await this.companyModel.findById(companyId).lean().exec();
    if (!company?.logoKey) throw new NotFoundException();

    const logoPath = path.join(this.storageBase, company.logoKey);
    if (!fs.existsSync(logoPath)) throw new NotFoundException();

    const ext = path.extname(company.logoKey).toLowerCase();
    const contentType = ext === '.png' ? 'image/png'
      : ext === '.gif' ? 'image/gif'
      : 'image/jpeg';

    res.setHeader('Content-Type', contentType);
    res.setHeader('Cache-Control', 'public, max-age=86400');
    res.send(fs.readFileSync(logoPath));
  }

  private async catalogosDe(companyId: string) {
    const cats = await this.catalogModel.find({ companyId }).sort({ createdAt: 1 }).lean().exec();
    return cats.map((c) => ({
      id: c._id,
      slug: c.slug,
      title: c.title,
      manufacturer: c.manufacturer,
      layout: c.layout,
      productCount: c.productCount,
      createdAt: c.createdAt,
    }));
  }

  private toDto(c: { _id: string; name: string; customUrl: string; logoKey?: string; createdAt?: Date }) {
    return {
      id: c._id,
      name: c.name,
      customUrl: c.customUrl,
      logoUrl: c.logoKey ? `/logos/${c._id}` : null,
      createdAt: c.createdAt ?? null,
    };
  }

  private inferExt(mimetype: string, originalname: string): string {
    if (mimetype === 'image/png') return '.png';
    if (mimetype === 'image/gif') return '.gif';
    if (mimetype?.startsWith('image/')) return '.jpg';
    const ext = path.extname(originalname ?? '').toLowerCase();
    return ext || '.jpg';
  }
}
