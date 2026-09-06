import { BadRequestException, Body, Controller, Post, Res, UploadedFile, UseInterceptors } from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { Response } from 'express';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import {
  AqInfo, AqParte, armazenamentoTemporario, Biblioteca, enviarArquivo, GeoValidationError, nomeOriginalUtf8,
  normalizarSpecs, validateGeoBuffers,
} from '@bim/base';
import { ExportarAqDto, TesselarDto } from './conversores.dto';

/**
 * Conversões síncronas, de segundos, sem fila e sem estado:
 *
 *   POST /tesselar            — .stp/.step/.igs/.iges/.ifc → { pos, col, idx, partes, … } (contrato `geometria`)
 *   POST /aq                  — partes do editor (ou um {pos,col,idx}) → arquivo .aq de UMA peça (download)
 *   POST /plugin/inspecionar  — DLL de um plugin de CAD → host do catálogo web, plugin, versão, categorias (contrato `info-plugin`)
 *
 * Importar uma peça CAD ou um plugin como CATÁLOGO é do criador de catálogos (assíncrono, na fila).
 */
const MAX_CAD_BYTES = 1024 * 1024 * 1024;
const MAX_DLL_BYTES = 64 * 1024 * 1024;

@Controller()
export class ConversoresController {
  constructor(private readonly biblioteca: Biblioteca) {}

  @Post('tesselar')
  @UseInterceptors(FileInterceptor('file', { storage: armazenamentoTemporario('conv', '.stp'), limits: { fileSize: MAX_CAD_BYTES } }))
  async tesselar(@UploadedFile() file: Express.Multer.File, @Body() body: TesselarDto) {
    if (!file) throw new BadRequestException('campo "file" (.stp/.step/.igs/.iges/.ifc) obrigatório');
    try {
      return await this.biblioteca.tesselar(file.path, body?.deflexao ?? 0.2, nomeOriginalUtf8(file.originalname, file.filename));
    } finally {
      await fs.unlink(file.path).catch(() => {});
    }
  }

  @Post('aq')
  async aq(@Body() body: ExportarAqDto, @Res() res: Response) {
    const info: AqInfo = { ...(body.info ?? {}), specs: body.info?.specs ? normalizarSpecs(body.info.specs) : undefined };
    const partes: AqParte[] = (body.partes ?? []).map((p) => ({ nome: p.nome, pos: p.pos, col: p.col ?? null, idx: p.idx }));
    let geo;
    if (!partes.length) {
      try {
        geo = validateGeoBuffers(body);
      } catch (err) {
        if (err instanceof GeoValidationError) throw new BadRequestException(`sem "partes" e ${err.message}`);
        throw err;
      }
    } else {
      for (const [i, p] of partes.entries()) {
        try {
          validateGeoBuffers({ pos: p.pos, col: p.col ?? [], idx: p.idx });
        } catch (err) {
          if (err instanceof GeoValidationError) throw new BadRequestException(`partes[${i}]: ${err.message}`);
          throw err;
        }
      }
    }
    const { path: aqPath, resumo } = await this.biblioteca.gerarAq(info, partes, geo);
    const nome = (info.nome ?? 'peca').replace(/[^\w.-]+/g, '_') || 'peca';
    await enviarArquivo(res, aqPath, { nome: `${nome}.aq`, contentType: 'application/x-sqlite3',
                                       headers: { 'X-Aq-Resumo': encodeURIComponent(JSON.stringify(resumo)) } });
  }

  @Post('plugin/inspecionar')
  @UseInterceptors(FileInterceptor('file', { storage: armazenamentoTemporario('plugin', '.dll'), limits: { fileSize: MAX_DLL_BYTES } }))
  async inspecionar(@UploadedFile() file: Express.Multer.File) {
    if (!file) throw new BadRequestException('campo "file" obrigatório — a DLL do plugin de CAD');
    const nome = nomeOriginalUtf8(file.originalname, path.basename(file.path));
    if (path.extname(nome).toLowerCase() !== '.dll') {
      await fs.unlink(file.path).catch(() => {});
      throw new BadRequestException('envie a DLL do plugin (.dll)');
    }
    try {
      return await this.biblioteca.inspecionarPlugin(file.path);
    } finally {
      await fs.unlink(file.path).catch(() => {});
    }
  }
}
