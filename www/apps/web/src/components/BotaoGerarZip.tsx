'use client'

/**
 * BotaoGerarZip — envia um .aq ou .zip para POST /exportar/zip-bilds no serviço de ingestão
 * e dispara o download do ZIP gerado. Mostra progresso de upload e estado de processamento.
 * Nada é armazenado no servidor: o arquivo enviado e o ZIP gerado são temporários.
 */

import { useRef, useState } from 'react'
import { INGESTAO_URL } from '@/lib/api'

type Estado = 'idle' | 'enviando' | 'processando' | 'erro'

export function BotaoGerarZip() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [estado, setEstado] = useState<Estado>('idle')
  const [progresso, setProgresso] = useState(0)
  const [erro, setErro] = useState<string | null>(null)
  const xhrRef = useRef<XMLHttpRequest | null>(null)

  function iniciar() {
    setErro(null)
    inputRef.current?.click()
  }

  function cancelar() {
    xhrRef.current?.abort()
    setEstado('idle')
    setProgresso(0)
    if (inputRef.current) inputRef.current.value = ''
  }

  function onArquivo(e: React.ChangeEvent<HTMLInputElement>) {
    const arquivo = e.target.files?.[0]
    if (!inputRef.current) inputRef.current = null   // satisfaz lint
    if (inputRef.current) inputRef.current.value = ''
    if (!arquivo) return

    const form = new FormData()
    form.append('file', arquivo)

    const xhr = new XMLHttpRequest()
    xhrRef.current = xhr
    setEstado('enviando')
    setProgresso(0)
    setErro(null)

    xhr.upload.addEventListener('progress', (ev) => {
      if (ev.lengthComputable) setProgresso(Math.round((ev.loaded / ev.total) * 100))
    })

    xhr.upload.addEventListener('load', () => {
      setEstado('processando')
    })

    xhr.responseType = 'blob'

    xhr.addEventListener('load', () => {
      xhrRef.current = null
      if (xhr.status === 200) {
        const blob = xhr.response as Blob
        const nomeHeader = xhr.getResponseHeader('Content-Disposition') ?? ''
        const match = nomeHeader.match(/filename="([^"]+)"/)
        const nome = match?.[1] ?? `${arquivo.name.replace(/\.(aq|zip)$/i, '')}-bilds.zip`
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = nome
        a.click()
        URL.revokeObjectURL(url)
        setEstado('idle')
        setProgresso(0)
      } else {
        // tenta extrair a mensagem de erro do JSON (mesmo que o responseType seja blob)
        const reader = new FileReader()
        reader.onload = () => {
          try {
            const json = JSON.parse(reader.result as string)
            setErro(json?.message ?? `erro ${xhr.status}`)
          } catch {
            setErro(`erro ${xhr.status}`)
          }
          setEstado('erro')
        }
        reader.readAsText(xhr.response as Blob)
      }
    })

    xhr.addEventListener('error', () => {
      xhrRef.current = null
      setErro('falha de rede — verifique se o serviço de ingestão está no ar')
      setEstado('erro')
    })

    xhr.addEventListener('abort', () => {
      xhrRef.current = null
      setEstado('idle')
      setProgresso(0)
    })

    xhr.open('POST', `${INGESTAO_URL}/exportar/zip-bilds`)
    xhr.send(form)
  }

  const emAndamento = estado === 'enviando' || estado === 'processando'

  return (
    <span className="inline-flex items-center gap-1.5">
      <input
        ref={inputRef}
        type="file"
        accept=".aq,.zip,.AQ,.ZIP"
        className="sr-only"
        onChange={onArquivo}
      />

      {!emAndamento && (
        <button
          onClick={iniciar}
          className="px-3 py-1.5 rounded border border-gray-300 text-[12px] font-semibold text-gray-700 hover:bg-gray-50"
        >
          Gerar ZIP bilds.com
        </button>
      )}

      {estado === 'enviando' && (
        <>
          <span className="text-[12px] text-gray-600">
            Enviando… {progresso}%
          </span>
          <button onClick={cancelar} className="text-[11px] text-gray-400 hover:text-gray-700">cancelar</button>
        </>
      )}

      {estado === 'processando' && (
        <span className="text-[12px] text-gray-600 italic">
          Processando… (pode levar alguns minutos)
        </span>
      )}

      {estado === 'erro' && (
        <>
          <button
            onClick={iniciar}
            className="px-3 py-1.5 rounded border border-red-300 text-[12px] font-semibold text-red-700 hover:bg-red-50"
          >
            Gerar ZIP bilds.com
          </button>
          <span className="text-[11px] text-red-600" title={erro ?? ''}>
            {(erro ?? 'erro desconhecido').slice(0, 60)}
          </span>
        </>
      )}
    </span>
  )
}
