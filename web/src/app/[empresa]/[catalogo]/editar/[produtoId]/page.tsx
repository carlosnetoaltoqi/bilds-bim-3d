import { notFound } from 'next/navigation'
import { CATALOGO_URL } from '@/servicos/catalogo'
import { ProductEditor } from '@/components/bim-editor/ProductEditor'
import type { ProdutoDto } from '@/components/bim-editor/InfoForm'
import type { PocCatalog, PocProduct } from '@/components/bim-catalog/types'

/**
 * /:empresa/:catalogo/editar/:produtoId — editor de um produto (POC de edição).
 * Sem login: a rota não está no matcher do middleware, e a API não exige token
 * nos endpoints de edição.
 */

interface PageProps {
  params: Promise<{ empresa: string; catalogo: string; produtoId: string }>
}

export default async function EditarProdutoPage({ params }: PageProps) {
  const { empresa, catalogo, produtoId } = await params

  let catalog: PocCatalog
  let products: PocProduct[]
  let produto: ProdutoDto
  try {
    const [catRes, prodRes] = await Promise.all([
      fetch(`${CATALOGO_URL}/catalogos/${empresa}/${catalogo}`, { cache: 'no-store' }),
      fetch(`${CATALOGO_URL}/produtos/${produtoId}`, { cache: 'no-store' }),
    ])
    if (catRes.status === 404 || prodRes.status === 404) return notFound()
    if (!catRes.ok || !prodRes.ok) throw new Error(`API ${catRes.status}/${prodRes.status}`)
    const raw = await catRes.json()
    catalog = raw.catalog
    products = raw.products
    produto = await prodRes.json()
    if (produto.catalogId !== catalog.id) return notFound()
  } catch {
    return notFound()
  }

  return (
    <ProductEditor
      key={produto._id}
      empresa={empresa}
      catalogSlug={catalogo}
      catalog={catalog}
      products={products}
      produto={produto}
    />
  )
}
