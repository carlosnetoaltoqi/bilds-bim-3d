import * as crypto from 'node:crypto';

/**
 * Validador de cache para os blobs servidos do storage — geometria e miniatura.
 *
 * Por que não `immutable`: as chaves do store são `<tipo>/<importId>/<productId>`,
 * derivadas do import e não do conteúdo. Um `pnpm thumb:regen` sobre o *mesmo*
 * import reescreve os bytes na mesma chave, então uma ETag derivada só da chave
 * — mais `Cache-Control: immutable` — deixava o browser servindo a miniatura velha
 * por um ano. Trocar a ETag sozinho não resolveria: com `immutable` o browser não
 * revalida, logo nunca chega a comparar.
 *
 * O validador vem de tamanho + mtime do arquivo, que mudam quando os bytes mudam,
 * e o `must-revalidate` obriga o browser a perguntar. `mtime` em vez de hash do
 * conteúdo porque a resposta 304 é decidida antes de ler o blob — no caminho comum
 * só acontece o `stat`, e a geometria de vários MB nunca sai do disco à toa. O
 * preço é uma ETag nova quando os bytes são idênticos mas o mtime mudou (uma cópia
 * de storage sem preservar timestamps): custa um 200 extra, nunca conteúdo errado.
 */
export const ASSET_CACHE_CONTROL = 'public, max-age=0, must-revalidate';

export function assetEtag(key: string, stat: { size: number; mtimeMs: number }): string {
  const digest = crypto
    .createHash('sha1')
    .update(`${key}:${stat.size}:${stat.mtimeMs}`)
    .digest('hex')
    .slice(0, 16);
  return `"${digest}"`;
}

/** Compara o `If-None-Match` da requisição com a ETag atual do blob. */
export function ifNoneMatchSatisfied(header: string | undefined, etag: string): boolean {
  if (!header) return false;
  return header
    .split(',')
    .map((raw) => raw.trim().replace(/^W\//, ''))
    .some((candidate) => candidate === '*' || candidate === etag);
}
