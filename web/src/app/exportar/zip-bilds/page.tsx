'use client'

/**
 * /exportar/zip-bilds — gera o ZIP no formato contratado com a bilds.com a partir
 * de um .aq ou .zip já editado. Usa o BotaoGerarZip que chama POST /exportar/zip-bilds
 * no gerador-zip (:4200, stateless).
 */

import { BotaoGerarZip } from '@/components/BotaoGerarZip'

export default function ExportarZipBildsPage() {
  return (
    <main className="min-h-screen bg-gray-50 text-gray-900 py-12 px-6" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
      <div className="max-w-[720px] mx-auto">
        <p className="text-[12px] text-gray-500 mb-1"><a href="/" className="hover:underline">← empresas e catálogos</a></p>
        <h1 className="text-2xl font-bold mb-1" style={{ fontFamily: 'Fira Sans, Inter, system-ui, sans-serif' }}>Gerar ZIP bilds.com</h1>

        <aside className="mb-6 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-[13px] text-gray-600 flex flex-col gap-2">
          <p><strong className="font-semibold text-gray-900">Para que serve:</strong> você tem uma biblioteca <code>.aq</code> (ou <code>.zip</code>) já revisada e quer gerar o pacote no formato que a bilds.com consome para publicar catálogos BIM.</p>
          <p><strong className="font-semibold text-gray-900">O que acontece:</strong> o serviço lê o <code>.aq</code>, monta o ZIP no formato contratado com a bilds.com e envia direto para download. Nada fica armazenado no servidor — o arquivo enviado e o ZIP gerado são descartados após a resposta.</p>
          <p><strong className="font-semibold text-gray-900">O que você precisa:</strong> um arquivo <code>.aq</code> ou <code>.zip</code> com o catálogo já revisado e pronto para publicação. Se ainda precisar editar o catálogo, use o editor 3D antes de gerar o ZIP.</p>
        </aside>

        <div className="bg-white border border-gray-200 rounded-lg p-5 text-[13px]">
          <p className="text-[12px] text-gray-600 mb-4">Selecione o arquivo <code>.aq</code> ou <code>.zip</code> — o ZIP é gerado e baixado automaticamente.</p>
          <BotaoGerarZip />
        </div>
      </div>
    </main>
  )
}
