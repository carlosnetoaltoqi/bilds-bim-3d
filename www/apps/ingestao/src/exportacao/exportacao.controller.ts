import { Controller, Get, Param, Res } from '@nestjs/common';
import { Response } from 'express';
import { createReadStream } from 'node:fs';
import * as fs from 'node:fs/promises';
import { ExportacaoService } from './exportacao.service';

/**
 * GET /exportar/catalogo/:catalogId — download do catálogo salvo como `.aq` (AltoQi Builder).
 *
 * Síncrono: gera, faz stream do arquivo e apaga (nada fica no servidor). Um catálogo grande leva
 * dezenas de segundos — o `requestTimeout` do serviço é de uma hora (main.ts). Resumo do gerador
 * no header `X-Aq-Resumo` (exposto no CORS), nome do arquivo em `Content-Disposition`.
 * O `POST /exportar/aq` (uma peça, partes do editor) continua no `cad.controller.ts`.
 */
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
}
