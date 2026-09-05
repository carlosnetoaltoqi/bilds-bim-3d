/**
 * Base da API NestJS da POC — a ÚNICA origem de `http://localhost:4000` no web (I17).
 *
 * No browser só `NEXT_PUBLIC_*` existe (o Next inlina no bundle). No servidor Next
 * (route handlers, server components) `API_URL` tem precedência, para o caso de a API
 * ter um endereço interno diferente do público. Os dois caem em `http://localhost:4000`.
 */
const NO_SERVIDOR = typeof window === 'undefined'
export const API_URL: string =
  (NO_SERVIDOR ? process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL : process.env.NEXT_PUBLIC_API_URL) ??
  'http://localhost:4000'

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
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
