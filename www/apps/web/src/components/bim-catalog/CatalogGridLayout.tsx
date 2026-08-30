'use client'

import { useState } from 'react'
import { PocCatalog, PocProduct } from './types'
import { ProductModal } from './ProductModal'
import { LazyBimCard } from './LazyBimCard'

interface Props {
  catalog: PocCatalog
  products: PocProduct[]
}

export function CatalogGridLayout({ catalog, products }: Props) {
  const [activeFilter, setActiveFilter] = useState<string | null>(null)
  const [selectedProduct, setSelectedProduct] = useState<PocProduct | null>(null)

  const uniqueSeries = Array.from(new Set(products.map((p) => p.serie)))

  const filtered = activeFilter
    ? products.filter((p) => p.serie === activeFilter)
    : products

  return (
    <>
      <section className="bg-gradient-to-br from-[#002D72] to-[#00245B] px-8 pt-14 pb-12 text-white">
        <div className="max-w-[960px] mx-auto">
          <p className="text-[13px] text-blue-300 mb-3 tracking-[0.04em]">
            {catalog.manufacturer} · Biblioteca BIM
          </p>
          <h1 className="text-[32px] font-bold mb-3" style={{ fontFamily: 'Fira Sans, Inter, system-ui, sans-serif' }}>
            {catalog.title}
          </h1>
          <div className="flex gap-8 flex-wrap">
            {[
              { label: 'Fabricante', value: catalog.manufacturer },
              { label: 'Produtos', value: products.length },
              { label: 'Famílias', value: uniqueSeries.length },
            ].map(({ label, value }) => (
              <div key={label}>
                <div className="text-[11px] text-blue-300 uppercase tracking-[0.07em]">{label}</div>
                <div className="text-[22px] font-bold text-white">{value}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section aria-labelledby="bim-products-heading" className="px-8 py-8 max-w-[960px] mx-auto">
        <h2 id="bim-products-heading" className="text-base font-bold text-gray-900 mb-4">
          Produtos
        </h2>

        {catalog.filters && catalog.filters.length > 0 && (
          <div className="flex gap-2 flex-wrap mb-6">
            <button
              onClick={() => setActiveFilter(null)}
              className={`px-4 py-1.5 rounded-full border text-[13px] font-medium cursor-pointer transition-colors ${
                activeFilter === null
                  ? 'border-[#002D72] bg-[#002D72] text-white'
                  : 'border-gray-300 bg-white text-gray-700 hover:border-gray-400'
              }`}
            >
              Todos
            </button>
            {uniqueSeries.map((serie) => (
              <button
                key={serie}
                onClick={() => setActiveFilter(serie)}
                className={`px-4 py-1.5 rounded-full border text-[13px] font-medium cursor-pointer transition-colors ${
                  activeFilter === serie
                    ? 'border-[#002D72] bg-[#002D72] text-white'
                    : 'border-gray-300 bg-white text-gray-700 hover:border-gray-400'
                }`}
              >
                {serie}
              </button>
            ))}
          </div>
        )}

        <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4">
          {filtered.map((product) => (
            <LazyBimCard
              key={product._id}
              product={product}
              onOpen={() => setSelectedProduct(product)}
            />
          ))}
        </div>
      </section>

      {selectedProduct && (
        <ProductModal product={selectedProduct} onClose={() => setSelectedProduct(null)} />
      )}
    </>
  )
}
