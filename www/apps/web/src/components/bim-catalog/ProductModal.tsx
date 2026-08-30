'use client'

import { PocProduct } from './types'
import { BimViewer } from './BimViewer'
import { CurveChart } from './CurveChart'

interface Props {
  product: PocProduct
  onClose: () => void
}

export function ProductModal({ product, onClose }: Props) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={product.nome}
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/55"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl max-w-[860px] w-[95vw] max-h-[90vh] overflow-y-auto p-6 relative"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          aria-label="Fechar"
          className="absolute top-4 right-4 bg-transparent border-none cursor-pointer text-xl text-gray-500 hover:text-gray-700 leading-none"
        >
          ✕
        </button>

        <h2 className="text-xl font-bold mb-4 pr-8">{product.nome}</h2>

        <div className="h-[300px] bg-gray-100 rounded-lg mb-6 overflow-hidden">
          <BimViewer geoUrl={product.geoUrl} mode="modal" />
        </div>

        <div className={`grid gap-6 ${product.curva ? 'grid-cols-2' : 'grid-cols-1'}`}>
          <div>
            <h3 className="text-sm font-semibold mb-3 text-gray-700">Especificações</h3>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
              {Object.entries(product.specs).map(([key, val]) => (
                <div key={key}>
                  <dt className="text-[11px] text-gray-400 uppercase tracking-wide">{key}</dt>
                  <dd className="text-[13px] font-medium text-gray-900">{String(val)}</dd>
                </div>
              ))}
            </dl>
          </div>

          {product.curva && product.curva.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold mb-3 text-gray-700">Curva Q-H</h3>
              <CurveChart curva={product.curva} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
