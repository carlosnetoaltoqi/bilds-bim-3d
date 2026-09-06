import { notFound } from 'next/navigation'
import { BimCatalogView } from '@/components/bim-catalog/BimCatalogView'
import { PocCatalog, PocProduct } from '@/components/bim-catalog/types'
import { CATALOGO_URL } from '@/servicos/catalogo'

interface PageProps {
  params: Promise<{ empresa: string; catalogo: string }>
}

export default async function CatalogPage({ params }: PageProps) {
  const { empresa, catalogo } = await params

  let data: { catalog: PocCatalog; products: PocProduct[] }
  try {
    const res = await fetch(`${CATALOGO_URL}/catalogos/${empresa}/${catalogo}`, {
      cache: 'no-store',
    })
    if (res.status === 404) return notFound()
    if (!res.ok) throw new Error(`API ${res.status}`)
    const raw = await res.json()
    data = {
      catalog: raw.catalog,
      products: raw.products.map((p: PocProduct) => ({
        ...p,
        geoUrl: `${CATALOGO_URL}${p.geoUrl}`,
        thumbUrl: p.thumbUrl ? `${CATALOGO_URL}${p.thumbUrl}` : null,
      })),
    }
  } catch {
    return notFound()
  }

  return (
    <main style={{ minHeight: '100vh', background: '#fff', fontFamily: 'Inter, system-ui, sans-serif' }}>
      <BimCatalogView catalog={data.catalog} products={data.products} />
    </main>
  )
}
