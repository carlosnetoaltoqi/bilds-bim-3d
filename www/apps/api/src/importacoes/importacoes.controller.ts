import {
  Controller,
  Post,
  Get,
  Param,
  Query,
  Body,
  UploadedFile,
  UseInterceptors,
  BadRequestException,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { diskStorage } from 'multer';
import * as os from 'node:os';
import * as crypto from 'node:crypto';
import { ImportacoesService } from './importacoes.service';
import { nomeOriginalUtf8 } from '../common/upload';
import { ImportarAqDto } from './importar-aq.dto';

// .aq são SQLite raw: Dancor ~153 MB, Amanco ~394 MB, Maxbar ~618 MB.
// diskStorage evita buffer inteiro em RAM; multer escreve direto em /tmp.
const MAX_FILE_BYTES = 750 * 1024 * 1024;

const storage = diskStorage({
  destination: (_req, _file, cb) => cb(null, os.tmpdir()),
  filename: (_req, _file, cb) => cb(null, `bim-${crypto.randomUUID()}.aq`),
});

/**
 * Importação de bibliotecas `.aq` — sem auth (A7). A empresa vem no campo `empresa`
 * (customUrl); vazio = a primeira cadastrada, como no import CAD.
 *
 * Esta é a versão que ainda usa o port TypeScript (parse-worker/thumb-worker). Ela
 * sai na etapa E3 de docs/arquitetura-www-servico-de-ingestao.md, quando o serviço
 * `apps/ingestao` assumir a rota com o pipeline Python.
 */
@Controller('importacoes')
export class ImportacoesController {
  constructor(private readonly importacoesService: ImportacoesService) {}

  @Post()
  @UseInterceptors(FileInterceptor('file', { storage, limits: { fileSize: MAX_FILE_BYTES } }))
  async upload(@UploadedFile() file: Express.Multer.File, @Body() body: ImportarAqDto) {
    if (!file) throw new BadRequestException('campo "file" obrigatório');
    return this.importacoesService.create(body?.empresa, file.path, file.size, nomeOriginalUtf8(file.originalname, 'upload.aq'));
  }

  // Deve vir antes de :importId para não capturar "ultima" como param
  @Get('ultima')
  async ultima(@Query('empresa') empresa?: string) {
    return this.importacoesService.findLatest(empresa);
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
