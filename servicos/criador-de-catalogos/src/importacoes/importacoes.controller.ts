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
import { ImportarRevitDto } from './importar-revit.dto';

/**
 * POST /importacoes                 — multipart `file` (.aq | .zip | .stp | .step | .igs | .ifc | .rfa) + campos do ImportarDto
 *                                     → 202 { importId, tipo, status:'recebido', statusUrl }   (um .rfa solto vira importação 'revit')
 * POST /importacoes/plugin-autocad  — multipart `file` (DLL) + ImportarPluginDto (categoria, lead…) → 202 como acima, tipo 'plugin' (S7.17)
 * POST /importacoes/familias-revit  — multipart `file` (.rfa, .rvt ou .zip de famílias/projetos) + ImportarRevitDto → 202 como acima, tipo 'revit'
 * GET  /importacoes/familias-revit/aps — { disponivel } : o serviço tem APS_CLIENT_ID/APS_CLIENT_SECRET para traduzir .rvt (ADR-019)
 * GET  /importacoes/:importId       — status: recebido → parseando → gravando → publicado | vazio | falhou
 * GET  /importacoes?empresa=&limite= — últimas importações (da empresa, ou de todas)
 * DELETE /importacoes/:importId    — apaga a importação terminada com produtos e storage (409 se em andamento)
 *
 * Sem auth (ADR-007). O arquivo vai direto para o disco (`os.tmpdir()`): uma biblioteca real tem de
 * 150 a 600 MB — nada disso cabe em RAM. O nome temporário preserva a extensão e o
 * prefixo (`bim-` biblioteca, `cad-` peça) que a recuperação no boot reconhece.
 */
const MAX_FILE_BYTES = 1024 * 1024 * 1024;   // 1 GB: um IFC exportado do Revit passa fácil de 100 MB; bibliotecas chegam a 600 MB

const storage = armazenamentoTemporario((ext) => (tipoDe(ext) === 'cad' ? 'cad' : tipoDe(ext) === 'revit' ? 'revit' : 'bim'), '.aq');

// A DLL de um plugin tem dezenas de KB; prefixo `plugin-` reconhecido pela recuperação no boot
const MAX_DLL_BYTES = 64 * 1024 * 1024;
const storagePlugin = armazenamentoTemporario('plugin', '.dll');

// Famílias Revit: um .rfa solto ou um .zip com dezenas delas (mais type catalogs e geometria irmã); prefixo `revit-`
const storageRevit = armazenamentoTemporario('revit', '.zip');

@Controller('importacoes')
export class ImportacoesController {
  constructor(private readonly importacoes: ImportacoesService) {}

  @Post()
  @HttpCode(202)
  @UseInterceptors(FileInterceptor('file', { storage, limits: { fileSize: MAX_FILE_BYTES } }))
  async upload(@UploadedFile() file: Express.Multer.File, @Body() body: ImportarDto) {
    if (!file) throw new BadRequestException('campo "file" obrigatório (.aq, .zip, .stp, .step, .igs, .ifc ou .rfa)');
    const fileName = nomeOriginalUtf8(file.originalname, path.basename(file.path));
    return this.importacoes.create({ path: file.path, size: file.size, fileName }, body ?? {});
  }

  @Post('familias-revit')
  @HttpCode(202)
  @UseInterceptors(FileInterceptor('file', { storage: storageRevit, limits: { fileSize: MAX_FILE_BYTES } }))
  async familiasRevit(@UploadedFile() file: Express.Multer.File, @Body() body: ImportarRevitDto) {
    if (!file) throw new BadRequestException('campo "file" obrigatório — um .rfa, um projeto .rvt ou um .zip com as famílias Revit');
    const fileName = nomeOriginalUtf8(file.originalname, path.basename(file.path));
    return this.importacoes.createFamiliasRevit({ path: file.path, size: file.size, fileName }, body ?? {});
  }

  /** A página pergunta "usar a APS?" só quando o serviço tem credenciais (antes de `:importId`, senão a rota paramétrica engole). */
  @Get('familias-revit/aps')
  aps() {
    return { disponivel: this.importacoes.apsDisponivel() };
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
