/**
 * Cliente do serviço GERADOR DE ZIP (servicos/gerador-zip, :4200) — a única origem da URL dele no web.
 * `NEXT_PUBLIC_ZIP_URL` no browser; `ZIP_URL` tem precedência no servidor Next.
 */
const NO_SERVIDOR = typeof window === 'undefined'

export const ZIP_URL: string =
  (NO_SERVIDOR ? process.env.ZIP_URL ?? process.env.NEXT_PUBLIC_ZIP_URL : process.env.NEXT_PUBLIC_ZIP_URL) ??
  'http://localhost:4200'

/** `POST /zip` — o caminho para um XHR com progresso de upload (o componente monta o FormData). */
export const ROTA_ZIP = `${ZIP_URL}/zip`
