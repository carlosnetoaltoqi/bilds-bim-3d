import {
  Controller,
  Post,
  Get,
  Param,
  Body,
  Req,
  UseGuards,
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
import { Request, Response } from 'express';
import { AuthGuard } from '../auth/auth.guard';
import { Company, CompanyDocument } from '../companies/companies.schema';
import { storagePath } from '../common/storage-path';
import { CriarEmpresaDto } from './criar-empresa.dto';

@Controller()
export class EmpresasController {
  private readonly storageBase: string;

  constructor(
    @InjectModel(Company.name) private readonly companyModel: Model<CompanyDocument>,
  ) {
    this.storageBase = storagePath(); // mesma raiz do DiskGeometryStore (I17)
  }

  @UseGuards(AuthGuard)
  @Post('empresas')
  @UseInterceptors(FileInterceptor('logo', { limits: { fileSize: 2 * 1024 * 1024 } }))
  async create(
    @Req() req: Request,
    @UploadedFile() logo: Express.Multer.File | undefined,
    @Body() body: CriarEmpresaDto, // obrigatoriedade e tamanho no DTO (I16)
  ) {
    const slug = body.customUrl.toLowerCase().replace(/[^a-z0-9-]/g, '-');
    const existing = await this.companyModel.findOne({ customUrl: slug }).lean().exec();
    if (existing) throw new ConflictException(`URL "${slug}" já está em uso`);

    const ownerId = (req as any).user.sub as string;
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
      ownerId,
      logoKey,
    });

    return {
      id: company._id,
      name: company.name,
      customUrl: company.customUrl,
      logoUrl: logoKey ? `/logos/${companyId}` : null,
    };
  }

  @UseGuards(AuthGuard)
  @Get('empresas/minha')
  async minha(@Req() req: Request) {
    const ownerId = (req as any).user.sub as string;
    const company = await this.companyModel.findOne({ ownerId }).lean().exec();
    if (!company) throw new NotFoundException('empresa não encontrada');

    return {
      id: company._id,
      name: company.name,
      customUrl: company.customUrl,
      logoUrl: company.logoKey ? `/logos/${company._id}` : null,
    };
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

  private inferExt(mimetype: string, originalname: string): string {
    if (mimetype === 'image/png') return '.png';
    if (mimetype === 'image/gif') return '.gif';
    if (mimetype?.startsWith('image/')) return '.jpg';
    const ext = path.extname(originalname ?? '').toLowerCase();
    return ext || '.jpg';
  }
}
