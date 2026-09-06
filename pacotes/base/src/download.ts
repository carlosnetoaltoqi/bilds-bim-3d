/**
 * download.ts — servir um arquivo gerado como download e apagá-lo depois.
 *
 * Armadilha registrada na S7.18: um `@Post` do Nest responde **201** por padrão; um download
 * precisa de `res.status(200)` explícito, ou o cliente que confere `=== 200` falha em silêncio.
 * O arquivo é apagado quando o stream fecha (ou falha); se falhar antes de mandar cabeçalho,
 * responde 500 com a mensagem.
 */
import { Response } from 'express';
import { createReadStream } from 'node:fs';
import * as fs from 'node:fs/promises';

export async function enviarArquivo(
  res: Response,
  caminho: string,
  opts: { nome: string; contentType: string; headers?: Record<string, string>; apagar?: boolean },
): Promise<void> {
  const { size } = await fs.stat(caminho);
  const limpar = () => (opts.apagar ?? true) ? fs.unlink(caminho).catch(() => {}) : Promise.resolve();
  res.status(200);
  res.setHeader('Content-Type', opts.contentType);
  res.setHeader('Content-Length', String(size));
  res.setHeader('Content-Disposition', `attachment; filename="${opts.nome}"`);
  for (const [k, v] of Object.entries(opts.headers ?? {})) res.setHeader(k, v);
  const stream = createReadStream(caminho);
  stream.on('close', () => void limpar());
  stream.on('error', (e) => {
    void limpar();
    if (!res.headersSent) res.status(500).json({ message: `falha ao ler o arquivo gerado — ${e.message}` });
    else res.destroy(e);
  });
  stream.pipe(res);
}
