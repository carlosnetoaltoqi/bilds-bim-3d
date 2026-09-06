import { BadRequestException, Controller, Logger, Post, Res, UploadedFile, UseInterceptors } from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { Response } from 'express';
import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import { armazenamentoTemporario, Biblioteca, enviarArquivo, nomeOriginalUtf8 } from '@bim/base';

/**
 * POST /zip — multipart `file` (.aq ou .zip) → ZIP da bilds.com como download.
 *
 * Nada fica no servidor: o arquivo enviado é apagado assim que a biblioteca termina de lê-lo e o
 * ZIP é apagado depois do stream. As miniaturas são geradas no Chromium; se ele não estiver
 * disponível o ZIP sai sem `thumbs/` e a página renderiza no browser (`--allow-no-thumbs`: quem
 * pediu está esperando um download). Um `.aq` grande leva o tempo do build — o serviço não tem
 * fila; o `requestTimeout` é de uma hora.
 */
const MAX_BYTES = 1024 * 1024 * 1024;   // uma biblioteca .aq passa de 600 MB

@Controller()
export class ZipController {
  private readonly logger = new Logger(ZipController.name);
  constructor(private readonly biblioteca: Biblioteca) {}

  @Post('zip')
  @UseInterceptors(FileInterceptor('file', { storage: armazenamentoTemporario('zip', '.aq'), limits: { fileSize: MAX_BYTES } }))
  async zip(@UploadedFile() file: Express.Multer.File, @Res() res: Response) {
    if (!file) throw new BadRequestException('campo "file" obrigatório (.aq ou .zip)');
    const nomeOriginal = nomeOriginalUtf8(file.originalname, path.basename(file.path));
    const ext = path.extname(nomeOriginal).toLowerCase();
    if (ext !== '.aq' && ext !== '.zip') {
      await fs.unlink(file.path).catch(() => {});
      throw new BadRequestException('apenas arquivos .aq ou .zip são aceitos');
    }
    const tag = `[zip/${nomeOriginal}]`;
    const t0 = Date.now();
    let zipPath: string | null = null;
    try {
      const r = await this.biblioteca.gerarZipBilds({ aqPath: file.path, nomeOriginal, onProgresso: (l) => this.logger.log(`${tag} ${l}`) });
      zipPath = r.path;
    } finally {
      await fs.unlink(file.path).catch(() => {});   // o .aq/.zip de entrada não é mais necessário
    }
    this.logger.log(`${tag} ZIP gerado em ${((Date.now() - t0) / 1000).toFixed(1)}s`);
    const nome = `${nomeOriginal.replace(/\.(aq|zip)$/i, '')}-bilds.zip`;
    await enviarArquivo(res, zipPath, { nome, contentType: 'application/zip' });
  }
}
