'use client'

/**
 * BotaoExportarAq — baixa o catálogo salvo (com as peças que restaram, editadas ou acrescentadas)
 * como uma biblioteca `.aq` nova do AltoQi Builder. O serviço de ingestão gera o arquivo do zero
 * (`GET /exportar/catalogo/:catalogId` → `pipeline/catalogo_to_aq.py`), faz stream e apaga —
 * nada fica no servidor; o browser recebe o download. Um catálogo grande leva dezenas de segundos.
 */
import { useState } from 'react'
import { CRIADOR_URL } from '@/servicos/criador'

interface Props {
  catalogId: string
  productCount: number
  className?: string
}

const fmt = (n: unknown) => Number(n ?? 0).toLocaleString('pt-BR')

export function BotaoExportarAq({ catalogId, productCount, className }: Props) {
  const [ocupado, setOcupado] = useState(false)
  const [msg, setMsg] = useState<{ tipo: 'ok' | 'erro'; texto: string } | null>(null)

  async function exportar() {
    setOcupado(true); setMsg(null)
    try {
      const r = await fetch(`${CRIADOR_URL}/exportar/catalogo/${catalogId}`)
      if (!r.ok) {
        const b = await r.json().catch(() => ({}))
        throw new Error(b?.message ? (Array.isArray(b.message) ? b.message.join('; ') : String(b.message)) : `serviço respondeu ${r.status}`)
      }
      const nome = /filename="([^"]+)"/.exec(r.headers.get('Content-Disposition') ?? '')?.[1] ?? 'catalogo.aq'
      const resumoRaw = r.headers.get('X-Aq-Resumo')
      const resumo = resumoRaw ? JSON.parse(decodeURIComponent(resumoRaw)) : null
      const url = URL.createObjectURL(await r.blob())
      const a = document.createElement('a')
      a.href = url; a.download = nome
      document.body.appendChild(a); a.click(); a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 30_000)
      setMsg({
        tipo: 'ok',
        texto: resumo
          ? `${nome}: ${fmt(resumo.pecas)} peças em ${fmt(resumo.grupos)} grupos, ${fmt(resumo.simbologias)} geometrias (${fmt(resumo.triangulos)} triângulos), ${fmt(resumo.propriedades)} propriedades, ${(resumo.bytes / 1024 / 1024).toFixed(1)} MB em ${resumo.segundos} s.`
          : `${nome} gerado.`,
      })
    } catch (e: any) {
      setMsg({ tipo: 'erro', texto: `.aq: ${e?.message ?? e}` })
    } finally {
      setOcupado(false)
    }
  }

  return (
    <span className="inline-flex items-center gap-2 flex-wrap">
      <button type="button" onClick={() => void exportar()} disabled={ocupado || productCount === 0}
        title="Gera uma biblioteca .aq nova com as peças deste catálogo como estão agora, para adicionar no AltoQi Builder"
        className={className ?? 'px-2 py-1 rounded border border-gray-300 text-[12px] hover:bg-gray-50 disabled:opacity-50'}>
        {ocupado ? 'gerando .aq… (pode levar um minuto)' : 'baixar .aq (AltoQi Builder)'}
      </button>
      {msg && <span className={`text-[11px] ${msg.tipo === 'ok' ? 'text-green-200' : 'text-red-200'}`}>{msg.texto}</span>}
    </span>
  )
}
