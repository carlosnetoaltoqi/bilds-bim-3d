'use client'

import { useState, useEffect, useRef } from 'react'
import { PocProduct } from './types'
import {
  thumbCache,
  enqueueRender,
  renderThumbToDataUrl,
  fetchGeo,
} from './bim-viewer-engine'

interface Props {
  product: PocProduct
  onOpen: () => void
  containerClassName?: string
}

export function LazyBimCard({ product, onOpen, containerClassName }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null)

  // Miniatura pré-gerada pelo pipeline (S2.4): sem WebGL, sem fila
  const staticThumbUrl = product.thumbUrl ?? null

  // Inicializa do cache imediatamente — evita flash em navegações
  const [thumbUrl, setThumbUrl] = useState<string | null>(
    () => thumbCache.get(product._id) ?? null
  )

  useEffect(() => {
    if (staticThumbUrl) return

    const wrap = wrapRef.current
    if (!wrap || thumbUrl) return

    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          io.unobserve(wrap)
          enqueueRender(product._id, renderCard)
        }
      },
      { rootMargin: '120px' }
    )
    io.observe(wrap)
    return () => io.disconnect()
  }, [product._id, thumbUrl, staticThumbUrl]) // eslint-disable-line react-hooks/exhaustive-deps

  async function renderCard() {
    if (thumbCache.has(product._id)) {
      setThumbUrl(thumbCache.get(product._id)!)
      return
    }
    const wrap = wrapRef.current
    if (!wrap) return
    const W = wrap.offsetWidth || 224
    const geoData = await fetchGeo(product.geoUrl)
    const url = await renderThumbToDataUrl(product._id, geoData, W, 162)
    setThumbUrl(url)
  }

  const src = staticThumbUrl ?? thumbUrl

  return (
    <div
      ref={wrapRef}
      data-card-id={product._id}
      onClick={onOpen}
      className={`border border-gray-200 rounded-[10px] overflow-hidden cursor-pointer bg-white transition-shadow hover:shadow-md ${containerClassName ?? ''}`}
    >
      <div className="group/viewer relative h-[162px] bg-gray-100">
        {src ? (
          <img
            src={src}
            alt=""
            loading="lazy"
            decoding="async"
            className={`w-full h-full block ${
              staticThumbUrl ? 'object-contain' : 'object-fill'
            }`}
          />
        ) : (
          <div className="w-full h-full animate-pulse bg-gray-200" />
        )}

        <div className="absolute top-2 right-2 w-[26px] h-[26px] rounded-full bg-white/85 flex items-center justify-center pointer-events-none">
          <svg
            viewBox="0 0 24 24"
            width="14"
            height="14"
            fill="none"
            stroke="#F97316"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
            <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
            <line x1="12" y1="22.08" x2="12" y2="12" />
          </svg>
        </div>
      </div>
      <div className="px-3.5 py-3">
        <div className="font-semibold text-[13px] text-gray-900 mb-0.5">
          {product.nome}
        </div>
        <div className="text-[11px] text-gray-500">{product.serie}</div>
      </div>
    </div>
  )
}
