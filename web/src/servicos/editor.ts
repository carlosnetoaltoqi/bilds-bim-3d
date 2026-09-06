/**
 * Cliente do EDITOR DE PEÇAS (servicos/editor-de-pecas, :4400) — a única origem da URL dele no web.
 * PATCH produto, PUT geometria (copy-on-write), restaurar, geometria original.
 */
import { servicoJson } from './catalogo'

const NO_SERVIDOR = typeof window === 'undefined'

export const EDITOR_URL: string =
  (NO_SERVIDOR ? process.env.EDITOR_URL ?? process.env.NEXT_PUBLIC_EDITOR_URL : process.env.NEXT_PUBLIC_EDITOR_URL) ??
  'http://localhost:4400'

export const editorJson = <T,>(path: string, init?: RequestInit) => servicoJson<T>(EDITOR_URL, path, init)
