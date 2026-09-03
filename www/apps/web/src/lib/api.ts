/** Base da API NestJS da POC. No browser e no servidor Next apontam para o mesmo host. */
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:4000'

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
