/**
 * e2e-cad-import.mjs — sobe um STEP ou IFC pelo serviço de ingestão, acompanha o
 * status até publicar e abre o produto no editor, medindo o carregamento.
 *
 * É o teste de `POST /importacoes` + `GET /importacoes/:id` (apps/ingestao) + editor, o
 * mesmo caminho da página /importar-step. Serve tanto para uma peça de 33 KB
 * (2831A09.stp, ~3 s) quanto para um Revit de 124 MB (Projeto4.ifc, ~4 min).
 *
 * Uso (da raiz do repo, API e web rodando):
 *   node tests/e2e/e2e-cad-import.mjs input/STEP/2831A09.stp [--nome "…"] [--catalogo "…"]
 *        [--fabricante "…"] [--deflexao 0.2] [--out /tmp/e2e-cad] [--sem-browser]
 */
import { mkdirSync, openAsBlob, statSync } from 'node:fs'
import { basename, dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..')
const arg = (nome, padrao) => {
  const i = process.argv.indexOf(`--${nome}`)
  return i >= 0 ? (process.argv[i + 1] ?? true) : padrao
}
const API = process.env.API_URL ?? 'http://localhost:4000'
const INGESTAO = process.env.INGESTAO_URL ?? 'http://localhost:4100'
const WEB = process.env.WEB_URL ?? 'http://localhost:3000'
const ARQUIVO = process.argv[2]
if (!ARQUIVO || ARQUIVO.startsWith('--')) throw new Error('uso: e2e-cad-import.mjs <arquivo.stp|.ifc> [opções]')
const OUT = resolve(arg('out', '/tmp/e2e-cad'))
mkdirSync(OUT, { recursive: true })

// 1. upload
const fd = new FormData()
fd.append('file', await openAsBlob(ARQUIVO), basename(ARQUIVO))
for (const k of ['nome', 'catalogo', 'fabricante', 'deflexao', 'empresa']) if (arg(k)) fd.append(k, arg(k))
const tamanhoMb = statSync(ARQUIVO).size / 1024 / 1024
const t0 = Date.now()
const r = await fetch(`${INGESTAO}/importacoes`, { method: 'POST', body: fd })
const inicio = await r.json()
if (!r.ok) throw new Error(`importar: ${r.status} ${JSON.stringify(inicio)}`)
console.log(`upload de ${tamanhoMb.toFixed(1)} MB em ${Date.now() - t0} ms → ${inicio.status} ${inicio.importId}`)

// 2. status até publicar
let st
let ultimaNota = ''
while (true) {
  await new Promise((ok) => setTimeout(ok, 3000))
  st = await (await fetch(`${INGESTAO}/importacoes/${inicio.importId}`)).json()
  const linha = `${st.status} | ${st.note ?? ''}`
  if (linha !== ultimaNota) { console.log(`  ${((Date.now() - t0) / 1000).toFixed(0)}s ${linha}`); ultimaNota = linha }
  if (st.status === 'publicado' || st.status === 'falhou') break
}
if (st.status === 'falhou') { console.error('FALHOU:', st.error); process.exit(1) }
console.log('publicado:', st.nome, '|', Object.entries(st.specs ?? {}).map(([k, v]) => `${k}: ${v}`).join(' · '))

// 3. miniatura — é fire-and-forget depois de publicar; espera até 60 s
let th
for (let i = 0; i < 20; i++) {
  th = await fetch(`${API}/thumbs/${st.produtoId}`)
  if (th.ok) break
  await new Promise((ok) => setTimeout(ok, 3000))
}
console.log(`thumb: ${th.status} ${th.headers.get('content-type')} ${(await th.arrayBuffer()).byteLength} B`)

if (process.argv.includes('--sem-browser')) process.exit(0)

// 4. editor
const { chromium } = await import(resolve(REPO, 'node_modules/playwright/index.mjs'))
const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--no-sandbox'] })
const page = await browser.newPage({ viewport: { width: 1500, height: 900 } })
const erros = []
page.on('console', (m) => { if (m.type() === 'error') erros.push(m.text()) })
page.on('pageerror', (e) => erros.push('PAGEERROR ' + e.message))
const t1 = Date.now()
await page.goto(`${WEB}${st.editorUrl}`, { waitUntil: 'domcontentloaded' })
await page.getByText(/parte\(s\) ·/).waitFor({ timeout: 600000 })
console.log(`editor carregado em ${((Date.now() - t1) / 1000).toFixed(1)} s —`, await page.getByText(/parte\(s\) ·/).textContent())
await page.waitForTimeout(2000)
await page.screenshot({ path: `${OUT}/${basename(ARQUIVO)}.editor.png` })
const heap = await page.evaluate(() => (performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1048576) : -1)).catch(() => -1)
console.log(`heap JS: ${heap} MB · erros: ${erros.length ? erros.slice(0, 3).join(' | ') : 'nenhum'} · captura em ${OUT}`)
await browser.close()
if (erros.length) process.exit(1)
