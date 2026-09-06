/**
 * Cliente do CRIADOR DE CATÁLOGOS (servicos/criador-de-catalogos, :4100) — a única origem da URL dele no web.
 * Importações (upload, status, lista, apagar), exportar catálogo salvo → .aq.
 */
const NO_SERVIDOR = typeof window === 'undefined'

export const CRIADOR_URL: string =
  (NO_SERVIDOR ? process.env.CRIADOR_URL ?? process.env.NEXT_PUBLIC_CRIADOR_URL : process.env.NEXT_PUBLIC_CRIADOR_URL) ??
  'http://localhost:4100'
