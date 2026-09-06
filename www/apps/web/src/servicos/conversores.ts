/**
 * Cliente do serviço de CONVERSORES (servicos/conversores, :4300) — a única origem da URL dele no web.
 * `NEXT_PUBLIC_CONVERSORES_URL` no browser; `CONVERSORES_URL` tem precedência no servidor Next.
 */
const NO_SERVIDOR = typeof window === 'undefined'

export const CONVERSORES_URL: string =
  (NO_SERVIDOR ? process.env.CONVERSORES_URL ?? process.env.NEXT_PUBLIC_CONVERSORES_URL : process.env.NEXT_PUBLIC_CONVERSORES_URL) ??
  'http://localhost:4300'

/** `POST /tesselar` — CAD → geometria do viewer. */
export function tesselar(file: File, deflexao?: string): Promise<Response> {
  const fd = new FormData()
  fd.append('file', file)
  if (deflexao) fd.append('deflexao', deflexao)
  return fetch(`${CONVERSORES_URL}/tesselar`, { method: 'POST', body: fd })
}

/** `POST /aq` — partes do editor (ou um {pos,col,idx}) → `.aq` de uma peça (a resposta é o arquivo). */
export function gerarAq(corpo: unknown): Promise<Response> {
  return fetch(`${CONVERSORES_URL}/aq`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(corpo) })
}

/** `POST /plugin/inspecionar` — DLL de um plugin de CAD → host e categorias do catálogo web. */
export function inspecionarPlugin(file: File): Promise<Response> {
  const fd = new FormData()
  fd.append('file', file)
  return fetch(`${CONVERSORES_URL}/plugin/inspecionar`, { method: 'POST', body: fd })
}
