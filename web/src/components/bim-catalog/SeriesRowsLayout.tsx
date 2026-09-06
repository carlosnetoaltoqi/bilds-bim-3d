'use client'

import { useState } from 'react'
import { usePathname } from 'next/navigation'
import { PocCatalog, PocProduct } from './types'
import { ProductModal } from './ProductModal'
import { LazyBimCard } from './LazyBimCard'

interface Props {
  catalog: PocCatalog
  products: PocProduct[]
}

export function SeriesRowsLayout({ catalog, products }: Props) {
  const [selectedProduct, setSelectedProduct] = useState<PocProduct | null>(null)
  const pathname = usePathname()

  const seriesMap = products.reduce<Record<string, PocProduct[]>>((acc, p) => {
    const key = p.serie
    if (!acc[key]) acc[key] = []
    acc[key]!.push(p)
    return acc
  }, {})

  const seriesNames = Array.from(new Set(products.map((p) => p.serie)))

  return (
    <>
      <section className="bg-gradient-to-br from-[#002D72] to-[#00245B] px-8 pt-14 pb-12 text-white">
        <div className="max-w-[960px] mx-auto">
          <p className="text-[13px] text-blue-300 mb-3 tracking-[0.04em] flex items-center gap-3">
            <span>{catalog.manufacturer} · Biblioteca BIM</span>
            <a href={`${pathname}/editar`} className="text-[11px] px-2 py-0.5 rounded border border-blue-300/50 hover:bg-white/10">editar catálogo</a>
          </p>
          <h1 className="text-[32px] font-bold mb-3" style={{ fontFamily: 'Fira Sans, Inter, system-ui, sans-serif' }}>
            {catalog.title}
          </h1>
          <div className="flex gap-8 flex-wrap">
            {[
              { label: 'Fabricante', value: catalog.manufacturer },
              { label: 'Modelos', value: products.length },
              { label: 'Séries', value: seriesNames.length },
            ].map(({ label, value }) => (
              <div key={label}>
                <div className="text-[11px] text-blue-300 uppercase tracking-[0.07em]">{label}</div>
                <div className="text-[22px] font-bold text-white">{value}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="px-8 py-8 max-w-[960px] mx-auto">
        {seriesNames.map((serie) => (
          <div key={serie} className="mb-10">
            <h2 className="text-base font-bold text-gray-900 mb-4">{serie}</h2>
            <div className="flex gap-4 overflow-x-auto pb-2">
              {(seriesMap[serie] ?? []).map((product) => (
                <LazyBimCard
                  key={product._id}
                  product={product}
                  onOpen={() => setSelectedProduct(product)}
                  containerClassName="min-w-[200px] max-w-[220px] shrink-0"
                />
              ))}
            </div>
          </div>
        ))}
      </section>

      {selectedProduct && (
        <ProductModal product={selectedProduct} onClose={() => setSelectedProduct(null)} />
      )}
    </>
  )
}
