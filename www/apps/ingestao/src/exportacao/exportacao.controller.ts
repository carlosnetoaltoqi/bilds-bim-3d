import { Controller, Get, Param, Res } from '@nestjs/common';
import { Response } from 'express';
import * as fs from 'node:fs/promises';
import { enviarArquivo } from '@bim/base';
import { ExportacaoService } from './exportacao.service';

/**
 * GET /exportar/catalogo/:catalogId — catálogo salvo (Mongo) → download `.aq` (AltoQi Builder).
 *
 * Síncrono, stream direto, nada fica no servidor. Um catálogo grande leva dezenas de segundos — o
 * `requestTimeout` do serviço é de uma hora. O ZIP da bilds.com é do serviço gerador-zip e o `.aq`
 * de uma peça é dos conversores (S8/F3).
 */

@Controller('exportar')
export class ExportacaoController {
  constructor(private readonly exportacao: ExportacaoService) {}

  @Get('catalogo/:catalogId')
  async catalogo(@Param('catalogId') catalogId: string, @Res() res: Response) {
    const { path: aqPath, nomeArquivo, resumo } = await this.exportacao.catalogoParaAq(catalogId);
    try {
      await enviarArquivo(res, aqPath, { nome: nomeArquivo, contentType: 'application/x-sqlite3',
                                         headers: { 'X-Aq-Resumo': encodeURIComponent(JSON.stringify(resumo)) } });
    } catch (e) {
      await fs.unlink(aqPath).catch(() => {});
      throw e;
    }
  }
}
