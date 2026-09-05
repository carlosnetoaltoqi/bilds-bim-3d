/**
 * Bases dos dois serviços que o web consome — a ÚNICA origem de `localhost:4000`/`4100` no web (I17).
 *
 *   API_URL       API de catálogo (apps/api, :4000): empresas, catálogos, produtos, geometria, miniaturas
 *   INGESTAO_URL  serviço de ingestão (apps/ingestao, :4100): upload/status de importação, tesselar CAD, exportar .aq
 *
 * No browser só `NEXT_PUBLIC_*` existe (o Next inlina no bundle). No servidor Next (server
 * components) `API_URL`/`INGESTAO_URL` têm precedência, para o caso de a rede interna ter outro
 * endereço. Padrões: http://localhost:4000 e http://localhost:4100.
 */
const NO_SERVIDOR = typeof window === 'undefined'

export const API_URL: string =
  (NO_SERVIDOR ? process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL : process.env.NEXT_PUBLIC_API_URL) ??
  'http://localhost:4000'

export const INGESTAO_URL: string =
  (NO_SERVIDOR ? process.env.INGESTAO_URL ?? process.env.NEXT_PUBLIC_INGESTAO_URL : process.env.NEXT_PUBLIC_INGESTAO_URL) ??
  'http://localhost:4100'

export async function apiJson<T>(path: string, init?: RequestInit, base: string = API_URL): Promise<T> {
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    let msg = `API ${res.status}`
    try {
      const body = await res.json()
      if (body?.message) msg = Array.isArray(body.message) ? body.message.join('; ') : String(body.message)
    } catch { /* corpo não-JSON */ }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}
