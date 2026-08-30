import {
  Controller,
  Post,
  Get,
  Param,
  Query,
  UploadedFile,
  UseInterceptors,
  BadRequestException,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { ImportacoesService } from './importacoes.service';

// .aq contém BLOBs de geometria raw (SQLite): Dancor ~153 MB, Amanco >400 MB.
// ZIP na bilds.com é comprimido e pós-processado — limites não comparáveis.
const MAX_FILE_BYTES = 300 * 1024 * 1024;

@Controller('importacoes')
export class ImportacoesController {
  constructor(private readonly importacoesService: ImportacoesService) {}

  @Post()
  @UseInterceptors(FileInterceptor('file', { limits: { fileSize: MAX_FILE_BYTES } }))
  async upload(
    @UploadedFile() file: any,
    @Query('empresa') empresa: string,
  ) {
    if (!file) throw new BadRequestException('campo "file" obrigatório');
    if (!empresa) throw new BadRequestException('query param "empresa" obrigatório');

    return this.importacoesService.create(empresa, file.buffer, file.originalname ?? 'upload.aq');
  }

  @Get(':importId')
  async status(@Param('importId') importId: string) {
    const imp = await this.importacoesService.findById(importId);
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
