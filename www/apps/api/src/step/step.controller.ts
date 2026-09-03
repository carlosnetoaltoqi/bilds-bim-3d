import {
  BadRequestException,
  Body,
  Controller,
  Post,
  Res,
  UploadedFile,
  UseInterceptors,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { diskStorage } from 'multer';
import { Response } from 'express';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as crypto from 'node:crypto';
import * as path from 'node:path';
import { AqInfo, AqParte, StepService } from './step.service';
import { GeoValidationError, validateGeoBuffers } from '../common/geo-buffers';

/**
 * POST /cad/tesselar   — .stp/.step/.ifc → { pos, col, idx, partes, … }  (para "adicionar parte" no editor)
 * POST /cad/importar   — .stp/.step/.ifc → produto novo num catálogo, pronto para o editor
 * POST /exportar/aq    — partes do editor → arquivo .aq (download)
 *
 * `/step/tesselar` e `/step/importar` continuam válidos (aliases). O formato é
 * decidido pela extensão do nome original. Sem auth: POC de edição, local.
 */

const MAX_STEP_BYTES = 200 * 1024 * 1024;
const storage = diskStorage({
  destination: (_req, _file, cb) => cb(null, os.tmpdir()),
  // preserva a extensão: é por ela que o serviço escolhe STEP ou IFC
  filename: (_req, file, cb) => cb(null, `cad-${crypto.randomUUID()}${(path.extname(file.originalname ?? '') || '.stp').toLowerCase()}`),
});

function deflexaoDe(body: Record<string, string> | undefined): number {
  const v = Number(body?.deflexao ?? 0.2);
  if (!Number.isFinite(v) || v <= 0 || v > 10) throw new BadRequestException('"deflexao" deve ser um número em mm entre 0 e 10');
  return v;
}

@Controller()
export class StepController {
  constructor(private readonly step: StepService) {}

  @Post(['cad/tesselar', 'step/tesselar'])
  @UseInterceptors(FileInterceptor('file', { storage, limits: { fileSize: MAX_STEP_BYTES } }))
  async tesselar(@UploadedFile() file: Express.Multer.File, @Body() body: Record<string, string>) {
    if (!file) throw new BadRequestException('campo "file" (.stp/.step/.ifc) obrigatório');
    try {
      return await this.step.tesselar(file.path, deflexaoDe(body), file.originalname);
    } finally {
      await fs.unlink(file.path).catch(() => {});
    }
  }

  @Post(['cad/importar', 'step/importar'])
  @UseInterceptors(FileInterceptor('file', { storage, limits: { fileSize: MAX_STEP_BYTES } }))
  async importar(@UploadedFile() file: Express.Multer.File, @Body() body: Record<string, string>) {
    if (!file) throw new BadRequestException('campo "file" (.stp/.step/.ifc) obrigatório');
    try {
      return await this.step.importar({
        stpPath: file.path,
        fileName: file.originalname ?? file.filename,
        empresa: body?.empresa,
        fabricante: body?.fabricante,
        catalogo: body?.catalogo,
        nome: body?.nome,
        deflexaoMm: deflexaoDe(body),
      });
    } finally {
      await fs.unlink(file.path).catch(() => {});
    }
  }

  @Post('exportar/aq')
  async exportarAq(
    @Body() body: { info?: AqInfo; partes?: AqParte[]; pos?: number[]; col?: number[]; idx?: number[] },
    @Res() res: Response,
  ) {
    const info = body?.info ?? {};
    const partes = Array.isArray(body?.partes) ? body.partes : [];
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
    const { path: aqPath, resumo } = await this.step.gerarAq(info, partes, geo);
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
