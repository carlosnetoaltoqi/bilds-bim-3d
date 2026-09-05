import {
  BadRequestException,
  Body,
  Controller,
  Get,
  HttpCode,
  Param,
  Post,
  Query,
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
import { normalizarSpecs } from '../common/validation';
import { ExportarAqDto, ImportarCadDto } from './cad.dto';
import { nomeOriginalUtf8 } from '../common/upload';

/**
 * POST /cad/tesselar   — .stp/.step/.ifc → { pos, col, idx, partes, … }  (para "adicionar parte" no editor)
 * POST /cad/importar   — .stp/.step/.ifc → cria a importação e devolve 202 { importId, statusUrl };
 *                        a conversão roda em background. `?sync=1` espera e devolve o produto (arquivos pequenos)
 * GET  /cad/importacoes/:importId — status: recebido → parseando → gravando → publicado | falhou
 * POST /exportar/aq    — partes do editor → arquivo .aq (download)
 *
 * `/step/tesselar` e `/step/importar` continuam válidos (aliases). O formato é
 * decidido pela extensão do nome original. Sem auth: POC de edição, local.
 */

const MAX_STEP_BYTES = 1024 * 1024 * 1024;   // um Revit exportado passa fácil de 100 MB
const storage = diskStorage({
  destination: (_req, _file, cb) => cb(null, os.tmpdir()),
  // preserva a extensão: é por ela que o serviço escolhe STEP ou IFC
  filename: (_req, file, cb) => cb(null, `cad-${crypto.randomUUID()}${(path.extname(file.originalname ?? '') || '.stp').toLowerCase()}`),
});

/** `deflexao` já validada pelo DTO (0 < mm ≤ 10); o padrão é 0,2 mm. */
const deflexaoDe = (body: ImportarCadDto | undefined): number => body?.deflexao ?? 0.2;

@Controller()
export class StepController {
  constructor(private readonly step: StepService) {}

  @Post(['cad/tesselar', 'step/tesselar'])
  @UseInterceptors(FileInterceptor('file', { storage, limits: { fileSize: MAX_STEP_BYTES } }))
  async tesselar(@UploadedFile() file: Express.Multer.File, @Body() body: ImportarCadDto) {
    if (!file) throw new BadRequestException('campo "file" (.stp/.step/.ifc) obrigatório');
    try {
      return await this.step.tesselar(file.path, deflexaoDe(body), nomeOriginalUtf8(file.originalname, file.filename));
    } finally {
      await fs.unlink(file.path).catch(() => {});
    }
  }

  @Post(['cad/importar', 'step/importar'])
  @HttpCode(202)
  @UseInterceptors(FileInterceptor('file', { storage, limits: { fileSize: MAX_STEP_BYTES } }))
  async importar(
    @UploadedFile() file: Express.Multer.File,
    @Body() body: ImportarCadDto,
    @Query('sync') sync: string | undefined,
    @Res({ passthrough: true }) res: Response,
  ) {
    if (!file) throw new BadRequestException('campo "file" (.stp/.step/.ifc) obrigatório');
    const opts = {
      stpPath: file.path,
      fileName: nomeOriginalUtf8(file.originalname, file.filename),
      fileSize: file.size,
      empresa: body?.empresa,
      fabricante: body?.fabricante,
      catalogo: body?.catalogo,
      nome: body?.nome,
      deflexaoMm: deflexaoDe(body),
    };
    if (sync === '1' || sync === 'true') {
      try {
        res.status(201);
        return await this.step.importar(opts);
      } finally {
        await fs.unlink(file.path).catch(() => {});
      }
    }
    // assíncrono: o serviço apaga o arquivo quando terminar
    try {
      return await this.step.importarAsync(opts);
    } catch (err) {
      await fs.unlink(file.path).catch(() => {});
      throw err;
    }
  }

  @Get('cad/importacoes/:importId')
  status(@Param('importId') importId: string) {
    return this.step.status(importId);
  }

  @Post('exportar/aq')
  async exportarAq(
    @Body() body: ExportarAqDto, // forma e limites no DTO (I16); os números dos arrays, abaixo
    @Res() res: Response,
  ) {
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
