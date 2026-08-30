import {
  Controller,
  Post,
  Get,
  Param,
  UploadedFile,
  UseInterceptors,
  UseGuards,
  BadRequestException,
  Req,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { diskStorage } from 'multer';
import * as os from 'node:os';
import * as crypto from 'node:crypto';
import { Request } from 'express';
import { ImportacoesService } from './importacoes.service';
import { AuthGuard } from '../auth/auth.guard';

// .aq são SQLite raw: Dancor ~153 MB, Amanco ~394 MB, Maxbar ~618 MB.
// diskStorage evita buffer inteiro em RAM; multer escreve direto em /tmp.
const MAX_FILE_BYTES = 750 * 1024 * 1024;

const storage = diskStorage({
  destination: (_req, _file, cb) => cb(null, os.tmpdir()),
  filename: (_req, _file, cb) => cb(null, `bim-${crypto.randomUUID()}.aq`),
});

@Controller('importacoes')
export class ImportacoesController {
  constructor(private readonly importacoesService: ImportacoesService) {}

  @UseGuards(AuthGuard)
  @Post()
  @UseInterceptors(FileInterceptor('file', { storage, limits: { fileSize: MAX_FILE_BYTES } }))
  async upload(@Req() req: Request, @UploadedFile() file: Express.Multer.File) {
    if (!file) throw new BadRequestException('campo "file" obrigatório');
    const ownerId = (req as any).user.sub as string;
    return this.importacoesService.create(ownerId, file.path, file.size, file.originalname ?? 'upload.aq');
  }

  // Deve vir antes de :importId para não capturar "ultima" como param
  @UseGuards(AuthGuard)
  @Get('ultima')
  async ultima(@Req() req: Request) {
    const ownerId = (req as any).user.sub as string;
    return this.importacoesService.findLatestByOwnerId(ownerId);
  }

  @UseGuards(AuthGuard)
  @Get(':importId')
  async status(@Req() req: Request, @Param('importId') importId: string) {
    const ownerId = (req as any).user.sub as string;
    const imp = await this.importacoesService.findByIdAndVerifyOwner(importId, ownerId);
    return {
      importId: imp._id,
      status: imp.status,
      productCount: imp.productCount ?? null,
      error: imp.error ?? null,
      note: (imp as any).note ?? null,
      catalogId: imp.catalogId ?? null,
      createdAt: imp.createdAt,
      updatedAt: (imp as any).updatedAt ?? null,
    };
  }
}
