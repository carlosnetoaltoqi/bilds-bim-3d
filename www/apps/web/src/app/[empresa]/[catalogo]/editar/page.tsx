import { notFound } from 'next/navigation'
import { API_URL } from '@/lib/api'
import type { PocCatalog, PocProduct } from '@/components/bim-catalog/types'
import { CatalogEditHeader } from '@/components/bim-editor/CatalogEditHeader'
import { BotaoApagar } from '@/components/BotaoApagar'

/**
 * /:empresa/:catalogo/editar — lista dos produtos do catálogo com link para o
 * editor de cada um, e o formulário dos metadados do catálogo.
 */

interface PageProps {
  params: Promise<{ empresa: string; catalogo: string }>
}

export default async function EditarCatalogoPage({ params }: PageProps) {
  const { empresa, catalogo } = await params
  let catalog: PocCatalog
  let products: Array<PocProduct & { editadoEm?: string | null; geoEditadoEm?: string | null }>
  try {
    const res = await fetch(`${API_URL}/catalogos/${empresa}/${catalogo}`, { cache: 'no-store' })
    if (res.status === 404) return notFound()
    if (!res.ok) throw new Error(`API ${res.status}`)
    const raw = await res.json()
    catalog = raw.catalog
    products = raw.products
  } catch {
    return notFound()
  }

  const base = `/${empresa}/${catalogo}`
  const porSerie = new Map<string, typeof products>()
  for (const p of products) {
    const k = p.serie || '—'
    if (!porSerie.has(k)) porSerie.set(k, [])
    porSerie.get(k)!.push(p)
  }

  return (
    <main className="min-h-screen bg-gray-50 text-gray-900" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
      <CatalogEditHeader catalog={catalog} publicUrl={base} />
      <section className="max-w-[960px] mx-auto px-8 py-8">
        <h2 className="text-base font-bold mb-4">Produtos ({products.length})</h2>
        {[...porSerie.entries()].map(([serie, lista]) => (
          <div key={serie} className="mb-6">
            <h3 className="text-[12px] uppercase tracking-wide text-gray-500 mb-2">{serie}</h3>
            <ul className="bg-white border border-gray-200 rounded-lg divide-y divide-gray-100">
              {lista.map((p) => (
                <li key={p._id} className="flex items-center gap-3 px-4 py-2.5">
                  {p.thumbUrl ? (
                    <img src={`${API_URL}${p.thumbUrl}`} alt="" className="w-14 h-10 object-contain bg-gray-100 rounded" />
                  ) : (
                    <span className="w-14 h-10 bg-gray-100 rounded" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] font-semibold truncate">{p.nome}</div>
                    <div className="text-[11px] text-gray-500 truncate">
                      {Object.keys(p.specs ?? {}).length} specs
                      {p.curva && p.curva.length > 0 && <> · curva Q-H ({p.curva.length} pts)</>}
                      {p.editadoEm && <> · <span className="text-amber-700">info editada</span></>}
                      {p.geoEditadoEm && <> · <span className="text-amber-700">geometria editada</span></>}
                    </div>
                  </div>
                  <a href={`${base}/editar/${p._id}`} className="px-3 py-1.5 rounded bg-[#1e40af] text-white text-[12px] font-semibold">Editar</a>
                  <BotaoApagar rota={`/produtos/${p._id}`} confirmacao={`Apagar a peça "${p.nome}"? A geometria e a miniatura só saem se nenhuma outra peça as compartilha.`} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>
    </main>
  )
}
