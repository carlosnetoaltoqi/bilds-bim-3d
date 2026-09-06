/**
 * Cliente da API DE CATÁLOGO (servicos/catalogo-api, :4000) — a única origem da URL dela no web.
 * Leitura: empresas, catálogos, produtos, geometria, miniaturas; remoção em cascata.
 * `NEXT_PUBLIC_CATALOGO_URL` no browser; `CATALOGO_URL` tem precedência no servidor Next.
 */
const NO_SERVIDOR = typeof window === 'undefined'

export const CATALOGO_URL: string =
  (NO_SERVIDOR ? process.env.CATALOGO_URL ?? process.env.NEXT_PUBLIC_CATALOGO_URL : process.env.NEXT_PUBLIC_CATALOGO_URL) ??
  'http://localhost:4000'

/** fetch JSON com a mensagem de erro do Nest no `Error` — para qualquer serviço (`base`). */
export async function servicoJson<T>(base: string, path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    let msg = `${res.status}`
    try {
      const body = await res.json()
      if (body?.message) msg = Array.isArray(body.message) ? body.message.join('; ') : String(body.message)
    } catch { /* corpo não-JSON */ }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

export const catalogoJson = <T,>(path: string, init?: RequestInit) => servicoJson<T>(CATALOGO_URL, path, init)
