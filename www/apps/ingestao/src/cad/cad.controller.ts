import { BadRequestException, Body, Controller, Post, Res, UploadedFile, UseInterceptors } from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { diskStorage } from 'multer';
import { Response } from 'express';
import * as crypto from 'node:crypto';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { GeoValidationError, nomeOriginalUtf8, normalizarSpecs, validateGeoBuffers } from '@bim/dominio';
import { AqInfo, AqParte, PipelineService } from '../pipeline/pipeline.service';
import { ExportarAqDto } from './cad.dto';
import { ImportarDto } from '../importacoes/importar.dto';

/**
 * Conversões síncronas para o editor (sem passar pela fila — são de segundos):
 *
 *   POST /cad/tesselar  — .stp/.step/.ifc → { pos, col, idx, partes, … }   ("adicionar parte")
 *   POST /exportar/aq   — partes do editor → arquivo .aq (download)
 *
 * Importar uma peça CAD como produto é `POST /importacoes` (assíncrono, na fila).
 */
const MAX_CAD_BYTES = 1024 * 1024 * 1024;
const storage = diskStorage({
  destination: (_req, _file, cb) => cb(null, os.tmpdir()),
  // preserva a extensão: é por ela que o pipeline escolhe STEP ou IFC
  filename: (_req, file, cb) => cb(null, `cad-${crypto.randomUUID()}${(path.extname(file.originalname ?? '') || '.stp').toLowerCase()}`),
});

@Controller()
export class CadController {
  constructor(private readonly pipeline: PipelineService) {}

  @Post('cad/tesselar')
  @UseInterceptors(FileInterceptor('file', { storage, limits: { fileSize: MAX_CAD_BYTES } }))
  async tesselar(@UploadedFile() file: Express.Multer.File, @Body() body: ImportarDto) {
    if (!file) throw new BadRequestException('campo "file" (.stp/.step/.ifc) obrigatório');
    try {
      return await this.pipeline.tesselar(file.path, body?.deflexao ?? 0.2, nomeOriginalUtf8(file.originalname, file.filename));
    } finally {
      await fs.unlink(file.path).catch(() => {});
    }
  }

  @Post('exportar/aq')
  async exportarAq(@Body() body: ExportarAqDto, @Res() res: Response) {
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
    const { path: aqPath, resumo } = await this.pipeline.gerarAq(info, partes, geo);
    try {
      const nome = (info.nome ?? 'peca').replace(/[^\w.-]+/g, '_') || 'peca';
      const buf = await fs.readFile(aqPath);
      res.setHeader('Content-Type', 'application/x-sqlite3');
      res.setHeader('Content-Disposition', `attachment; filename="${nome}.aq"`);
      res.setHeader('X-Aq-Resumo', encodeURIComponent(JSON.stringify(resumo)));
      res.send(buf);
    } finally {
      await fs.unlink(aqPath).catch(() => {});
    }
  }
}
