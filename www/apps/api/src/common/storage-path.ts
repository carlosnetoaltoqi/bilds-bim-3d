import * as path from 'node:path';

/**
 * Raiz do storage em disco (`geo/`, `thumbs/`, `logos/`) — a ÚNICA leitura de
 * `STORAGE_PATH` na API (I17, 2026-09-05). Até então quatro arquivos resolviam a
 * variável por conta própria e `empresas.controller.ts` usava outro default
 * (`../../storage/bim`), então sem `.env` os logos iam para uma pasta e a geometria
 * para outra.
 *
 * Relativo ao CWD da API (`www/apps/api` com `pnpm dev:api`). O `.env.example`
 * define `STORAGE_PATH=../../storage/bim` → `www/storage/bim`; sem a variável cai em
 * `<cwd>/storage`, e o `main.ts` avisa no boot.
 */
export const STORAGE_PATH_PADRAO = 'storage';

export function storagePath(env: NodeJS.ProcessEnv = process.env, cwd: string = process.cwd()): string {
  return path.resolve(cwd, env.STORAGE_PATH ?? STORAGE_PATH_PADRAO);
}

export function storagePathDefinido(env: NodeJS.ProcessEnv = process.env): boolean {
  return Boolean(env.STORAGE_PATH);
}
