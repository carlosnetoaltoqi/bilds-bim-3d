'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import type { PocCatalog } from '../bim-catalog/types'
import { CatalogForm } from './InfoForm'
import { BotaoApagar } from '../BotaoApagar'

export function CatalogEditHeader({ catalog: inicial, publicUrl }: { catalog: PocCatalog; publicUrl: string }) {
  const router = useRouter()
  const [catalog, setCatalog] = useState(inicial)
  return (
    <header className="bg-gradient-to-br from-[#002D72] to-[#00245B] px-8 pt-10 pb-8 text-white">
      <div className="max-w-[960px] mx-auto flex gap-10 flex-wrap items-start">
        <div className="flex-1 min-w-[280px]">
          <p className="text-[13px] text-blue-300 mb-2 tracking-[0.04em]">{catalog.manufacturer} · edição do catálogo</p>
          <h1 className="text-[28px] font-bold mb-2" style={{ fontFamily: 'Fira Sans, Inter, system-ui, sans-serif' }}>{catalog.title}</h1>
          <p className="text-[12px] text-blue-200">
            layout <code>{catalog.layout}</code> · {catalog.productCount} produtos ·{' '}
            <a href={publicUrl} target="_blank" rel="noopener noreferrer" className="underline hover:text-white">ver página pública ↗</a>
            {' · '}<a href="/" className="underline hover:text-white">início</a>
          </p>
          <div className="mt-3">
            <BotaoApagar rota={`/catalogos/${catalog.id}`} rotulo="apagar catálogo" depois="/"
              className="px-2 py-1 rounded border border-red-300/60 text-[12px] text-red-200 hover:bg-red-500/20"
              confirmacao={`Apagar o catálogo "${catalog.title}" com ${catalog.productCount} produto(s), geometria, miniaturas e as importações dele? Não tem volta.`} />
          </div>
        </div>
        <div className="bg-white text-gray-900 rounded-lg p-4 w-full max-w-[420px]">
          <CatalogForm catalog={catalog} onSaved={(c) => { setCatalog(c); router.refresh() }} />
        </div>
      </div>
    </header>
  )
}
