'use client'

import { PocCatalog, PocProduct } from './types'
import { CatalogGridLayout } from './CatalogGridLayout'
import { SeriesRowsLayout } from './SeriesRowsLayout'

interface Props {
  catalog: PocCatalog
  products: PocProduct[]
}

export function BimCatalogView({ catalog, products }: Props) {
  if (catalog.layout === 'catalog-grid') {
    return <CatalogGridLayout catalog={catalog} products={products} />
  }
  return <SeriesRowsLayout catalog={catalog} products={products} />
}
