import {
  BadRequestException,
  Body,
  ConflictException,
  Controller,
  Delete,
  Get,
  HttpCode,
  NotFoundException,
  Param,
  Post,
  Query,
  UploadedFile,
  UseInterceptors,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import * as os from 'node:os';
import * as path from 'node:path';
import { ImportacaoEmAndamento, NaoEncontrado } from '@bim/dominio';
import { armazenamentoTemporario, nomeOriginalUtf8 } from '@bim/base';
import { ImportacoesService, tipoDe } from './importacoes.service';
import { ImportarDto } from './importar.dto';
import { ImportarPluginDto } from './importar-plugin.dto';

/**
 * POST /importacoes                 — multipart `file` (.aq | .zip | .stp | .step | .igs | .ifc) + campos do ImportarDto
 *                                     → 202 { importId, tipo, status:'recebido', statusUrl }
 * POST /importacoes/plugin-autocad/inspecionar — multipart `file` (a DLL do plugin) → { host, plugin, versao, titulo, categorias[] }
 * POST /importacoes/plugin-autocad  — multipart `file` (DLL) + ImportarPluginDto (categoria, lead…) → 202 como acima, tipo 'plugin' (S7.17)
 * GET  /importacoes/:importId       — status: recebido → parseando → gravando → publicado | vazio | falhou
 * GET  /importacoes?empresa=&limite= — últimas importações (da empresa, ou de todas)
 * DELETE /importacoes/:importId    — apaga a importação terminada com produtos e storage (409 se em andamento)
 *
 * Sem auth (A7). O arquivo vai direto para o disco (`os.tmpdir()`): Dancor ~153 MB, Amanco
 * ~394 MB, Maxbar ~618 MB — nada disso cabe em RAM. O nome temporário preserva a extensão e o
 * prefixo (`bim-` biblioteca, `cad-` peça) que a recuperação no boot reconhece.
 */
const MAX_FILE_BYTES = 1024 * 1024 * 1024;   // 1 GB: um Revit exportado passa fácil de 100 MB; Maxbar 618 MB

const storage = armazenamentoTemporario((ext) => (tipoDe(ext) === 'cad' ? 'cad' : 'bim'), '.aq');

// A DLL de um plugin (TupyCAD.dll tem 35 KB); prefixo `plugin-` reconhecido pela recuperação no boot
const MAX_DLL_BYTES = 64 * 1024 * 1024;
const storagePlugin = armazenamentoTemporario('plugin', '.dll');

@Controller('importacoes')
export class ImportacoesController {
  constructor(private readonly importacoes: ImportacoesService) {}

  @Post()
  @HttpCode(202)
  @UseInterceptors(FileInterceptor('file', { storage, limits: { fileSize: MAX_FILE_BYTES } }))
  async upload(@UploadedFile() file: Express.Multer.File, @Body() body: ImportarDto) {
    if (!file) throw new BadRequestException('campo "file" obrigatório (.aq, .zip, .stp, .step, .igs ou .ifc)');
    const fileName = nomeOriginalUtf8(file.originalname, path.basename(file.path));
    return this.importacoes.create({ path: file.path, size: file.size, fileName }, body ?? {});
  }

  @Post('plugin-autocad/inspecionar')
  @UseInterceptors(FileInterceptor('file', { storage: storagePlugin, limits: { fileSize: MAX_DLL_BYTES } }))
  async inspecionarPlugin(@UploadedFile() file: Express.Multer.File) {
    if (!file) throw new BadRequestException('campo "file" obrigatório — a DLL do plugin de AutoCAD');
    const fileName = nomeOriginalUtf8(file.originalname, path.basename(file.path));
    return this.importacoes.inspecionarPlugin({ path: file.path, size: file.size, fileName });
  }

  @Post('plugin-autocad')
  @HttpCode(202)
  @UseInterceptors(FileInterceptor('file', { storage: storagePlugin, limits: { fileSize: MAX_DLL_BYTES } }))
  async plugin(@UploadedFile() file: Express.Multer.File, @Body() body: ImportarPluginDto) {
    if (!file) throw new BadRequestException('campo "file" obrigatório — a DLL do plugin de AutoCAD');
    const fileName = nomeOriginalUtf8(file.originalname, path.basename(file.path));
    return this.importacoes.createPlugin({ path: file.path, size: file.size, fileName }, body);
  }

  @Get()
  async listar(@Query('empresa') empresa?: string, @Query('limite') limite?: string) {
    const n = Math.min(Math.max(Number(limite) || 20, 1), 100);
    return this.importacoes.listar(empresa || undefined, n);
  }

  @Get(':importId')
  async status(@Param('importId') importId: string) {
    return this.importacoes.status(importId);
  }

  @Delete(':importId')
  async apagar(@Param('importId') importId: string) {
    try {
      return await this.importacoes.apagar(importId);
    } catch (e) {
      if (e instanceof NaoEncontrado) throw new NotFoundException(e.message);
      if (e instanceof ImportacaoEmAndamento) throw new ConflictException(e.message);
      throw e;
    }
  }
}
