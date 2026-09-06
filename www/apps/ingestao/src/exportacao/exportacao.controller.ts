import { BadRequestException, Controller, Get, Param, Post, Res, UploadedFile, UseInterceptors } from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { Response } from 'express';
import { createReadStream } from 'node:fs';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { armazenamentoTemporario, enviarArquivo, nomeOriginalUtf8 } from '@bim/base';
import { ExportacaoService } from './exportacao.service';

/**
 * GET  /exportar/catalogo/:catalogId — catálogo salvo (Mongo) → download `.aq` (AltoQi Builder).
 * POST /exportar/zip-bilds           — upload `.aq`/`.zip` → download ZIP para bilds.com.
 *
 * Os dois endpoints são síncronos e fazem stream direto: nada fica no servidor. Um catálogo
 * grande leva dezenas de segundos — o `requestTimeout` do serviço é de uma hora (main.ts).
 * O `POST /exportar/aq` (uma peça, partes do editor) continua no `cad.controller.ts`.
 */

const MAX_AQ_BYTES = 1024 * 1024 * 1024;   // mesmo limite do importar (Maxbar 618 MB)

const storageAq = armazenamentoTemporario('exp', '.aq');

@Controller('exportar')
export class ExportacaoController {
  constructor(private readonly exportacao: ExportacaoService) {}

  @Get('catalogo/:catalogId')
  async catalogo(@Param('catalogId') catalogId: string, @Res() res: Response) {
    const { path: aqPath, nomeArquivo, resumo } = await this.exportacao.catalogoParaAq(catalogId);
    const limpar = () => fs.unlink(aqPath).catch(() => {});
    try {
      const { size } = await fs.stat(aqPath);
      res.setHeader('Content-Type', 'application/x-sqlite3');
      res.setHeader('Content-Length', String(size));
      res.setHeader('Content-Disposition', `attachment; filename="${nomeArquivo}"`);
      res.setHeader('X-Aq-Resumo', encodeURIComponent(JSON.stringify(resumo)));
    } catch (e) {
      await limpar();
      throw e;
    }
    const stream = createReadStream(aqPath);
    stream.on('close', () => void limpar());
    stream.on('error', (e) => {
      void limpar();
      if (!res.headersSent) res.status(500).json({ message: `falha ao ler o .aq gerado — ${e.message}` });
      else res.destroy(e);
    });
    stream.pipe(res);
  }

  /**
   * POST /exportar/zip-bilds — multipart `file` (.aq ou .zip) → ZIP bilds.com como download.
   *
   * O arquivo enviado é apagado logo após o pipeline ler; o ZIP gerado é apagado depois do
   * stream. Nada fica no servidor. A geração inclui geometrias e miniaturas (Chromium); se o
   * Chromium não estiver disponível o ZIP sai sem `thumbs/` e o viewer renderiza no browser.
   */
  @Post('zip-bilds')
  @UseInterceptors(FileInterceptor('file', { storage: storageAq, limits: { fileSize: MAX_AQ_BYTES } }))
  async zipBilds(@UploadedFile() file: Express.Multer.File, @Res() res: Response) {
    if (!file) throw new BadRequestException('campo "file" obrigatório (.aq ou .zip)');
    const nomeOriginal = nomeOriginalUtf8(file.originalname, path.basename(file.path));
    const ext = path.extname(nomeOriginal).toLowerCase();
    if (ext !== '.aq' && ext !== '.zip') {
      await fs.unlink(file.path).catch(() => {});
      throw new BadRequestException('apenas arquivos .aq ou .zip são aceitos');
    }

    let zipPath: string | null = null;
    let r: { path: string; nomeArquivo: string };
    const limparUpload = () => fs.unlink(file.path).catch(() => {});
    const limparZip = () => zipPath ? fs.unlink(zipPath).catch(() => {}) : Promise.resolve();

    try {
      r = await this.exportacao.zipBilds(file.path, nomeOriginal);
      zipPath = r.path;
      await limparUpload();   // .aq/zip de entrada não é mais necessário

    } catch (e) {
      await limparUpload();
      await limparZip();
      throw e;
    }
    await enviarArquivo(res, zipPath!, { nome: r.nomeArquivo, contentType: 'application/zip' });
  }
}
