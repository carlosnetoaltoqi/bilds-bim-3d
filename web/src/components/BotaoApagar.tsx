'use client'

/**
 * BotaoApagar — o "apagar" de cada nível (empresa, catálogo, peça, importação), com confirmação.
 * Faz `DELETE` em `base + rota` (por padrão a API de catálogo; o criador para importações) e, se der certo, recarrega a
 * página ou navega para `depois`. Sem auth (A7): quem vê, apaga.
 */
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { CATALOGO_URL } from '@/servicos/catalogo'

interface Props {
  /** rota, ex. `/empresas/poc` */
  rota: string
  /** base do serviço dono da rota (padrão: a API de catálogo) */
  base?: string
  /** pergunta do confirm(); descreva o que vai junto */
  confirmacao: string
  /** para onde ir depois; sem isso, `router.refresh()` */
  depois?: string
  rotulo?: string
  className?: string
  /** avisa quem renderizou (listas em client components) */
  onApagado?: () => void
}

export function BotaoApagar({ rota, base = CATALOGO_URL, confirmacao, depois, rotulo = 'apagar', className, onApagado }: Props) {
  const router = useRouter()
  const [ocupado, setOcupado] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  async function apagar() {
    if (!window.confirm(confirmacao)) return
    setOcupado(true); setErro(null)
    try {
      const r = await fetch(`${base}${rota}`, { method: 'DELETE' })
      if (!r.ok) {
        const body = await r.json().catch(() => ({}))
        throw new Error(body?.message ? (Array.isArray(body.message) ? body.message.join('; ') : String(body.message)) : `${r.status}`)
      }
      onApagado?.()
      if (depois) router.push(depois)
      else router.refresh()
    } catch (e: any) {
      setErro(e?.message ?? String(e))
    } finally {
      setOcupado(false)
    }
  }

  return (
    <span className="inline-flex items-center gap-2">
      <button type="button" onClick={() => void apagar()} disabled={ocupado} title={confirmacao}
        className={className ?? 'px-2 py-1 rounded border border-red-200 text-[12px] text-red-700 hover:bg-red-50 disabled:opacity-50'}>
        {ocupado ? 'apagando…' : rotulo}
      </button>
      {erro && <span className="text-[11px] text-red-700">{erro}</span>}
    </span>
  )
}
