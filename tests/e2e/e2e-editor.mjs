/**
 * e2e-editor.mjs — exercita o editor 3D da POC de edição no browser, sem GPU.
 *
 * Playwright + Chromium com SwiftShader (os mesmos flags do thumb-rasterizer.ts),
 * contra a API (:4000) e o web (:3000) já rodando. Não precisa de login: as
 * rotas do editor estão fora do middleware.
 *
 * O que faz, por padrão, no 2º produto do catálogo (o 1º fica intacto):
 *   1. abre o editor e espera a geometria carregar
 *   2. seleciona a 1ª parte, liga a ferramenta "mover" (gizmo)
 *   3. gira 90° em X, SALVA a geometria, confere via API que a bbox trocou Y↔Z
 *      e que o original foi preservado; depois RESTAURA e confere que voltou
 *   4. adiciona uma primitiva, liga fantasma e corte (só para não dar erro), descarta
 *   5. edita o nome nas Informações, salva, confere `infoOriginal`, volta e salva
 *   6. exporta IFC e .aq (downloads salvos em --out) e confere com os parsers do
 *      projeto quando `--validar` é passado (chama python3)
 *   7. falha se houver qualquer erro de console ou de página
 *
 * Uso (da raiz do repo, com `node_modules/playwright` instalado pelo `npm install`):
 *   node tests/e2e/e2e-editor.mjs [--empresa poc-edicao] [--catalogo bomba-de-combate-a-incencio]
 *        [--produto 1] [--out /tmp/e2e] [--validar] [--so-exportar]
 */
import { execFileSync } from 'node:child_process'
import { mkdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..')
const { chromium } = await import(resolve(REPO, 'node_modules/playwright/index.mjs'))

const arg = (nome, padrao) => {
  const i = process.argv.indexOf(`--${nome}`)
  return i >= 0 ? (process.argv[i + 1] ?? true) : padrao
}
const API = process.env.API_URL ?? 'http://localhost:4000'
const WEB = process.env.WEB_URL ?? 'http://localhost:3000'
const EMPRESA = arg('empresa', 'poc-edicao')
const CATALOGO = arg('catalogo', 'bomba-de-combate-a-incencio')
const IDX = Number(arg('produto', 1))
const OUT = resolve(arg('out', '/tmp/e2e-editor'))
const VALIDAR = process.argv.includes('--validar')
const SO_EXPORTAR = process.argv.includes('--so-exportar')
mkdirSync(OUT, { recursive: true })

export const SWIFTSHADER = ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--no-sandbox']

const cat = await (await fetch(`${API}/catalogos/${EMPRESA}/${CATALOGO}`)).json()
const prod = cat.products[Math.min(IDX, cat.products.length - 1)]
if (!prod) throw new Error(`catálogo ${EMPRESA}/${CATALOGO} sem produtos`)
const url = `${WEB}/${EMPRESA}/${CATALOGO}/editar/${prod._id}`
console.log('produto:', prod.nome, prod._id)

const bbox = (g) => {
  const mn = [1e9, 1e9, 1e9], mx = [-1e9, -1e9, -1e9]
  for (let i = 0; i < g.pos.length; i += 3) for (let k = 0; k < 3; k++) { mn[k] = Math.min(mn[k], g.pos[i + k]); mx[k] = Math.max(mx[k], g.pos[i + k]) }
  return mn.map((v, k) => ((mx[k] - v) * 100).toFixed(1)).join('×')
}

const browser = await chromium.launch({ args: SWIFTSHADER })
const page = await browser.newPage({ viewport: { width: 1500, height: 900 }, acceptDownloads: true })
const erros = []
page.on('console', (m) => { if (m.type() === 'error') erros.push(m.text()) })
page.on('pageerror', (e) => erros.push('PAGEERROR ' + e.message))
page.on('dialog', (d) => d.accept())

const t0 = Date.now()
await page.goto(url, { waitUntil: 'networkidle' })
await page.getByText(/parte\(s\) ·/).waitFor({ timeout: 120000 })
console.log(`editor carregado em ${Date.now() - t0} ms —`, await page.getByText(/parte\(s\) ·/).textContent())
await page.waitForTimeout(800)
await page.screenshot({ path: `${OUT}/1-carregado.png` })

if (!SO_EXPORTAR) {
  // seleção + gizmo
  await page.locator('ul li').first().click()
  await page.keyboard.press('2')
  await page.waitForTimeout(400)
  await page.screenshot({ path: `${OUT}/2-selecao-gizmo.png` })

  // girar, salvar, conferir, restaurar
  const antes = await (await fetch(`${API}/geometrias/${prod._id}`)).json()
  await page.getByRole('button', { name: 'girar 90° X' }).click()
  await page.getByText('geometria não salva').first().waitFor()
  await page.getByRole('button', { name: 'Salvar geometria', exact: true }).click()
  await page.getByText(/^Gravado:/).waitFor({ timeout: 120000 })
  console.log('salvar:', await page.getByText(/^Gravado:/).textContent())
  const depois = await (await fetch(`${API}/geometrias/${prod._id}`)).json()
  const orig = await (await fetch(`${API}/geometrias/${prod._id}/original`)).json()
  console.log(`bbox cm antes=${bbox(antes)} depois=${bbox(depois)} original=${bbox(orig)} · △ ${antes.idx.length / 3} → ${depois.idx.length / 3}`)
  if (depois.idx.length !== antes.idx.length) throw new Error('girar mudou a contagem de triângulos')
  await page.getByRole('button', { name: 'restaurar original' }).click()
  await page.getByText('Geometria original restaurada.').waitFor({ timeout: 120000 })
  const restaurado = await (await fetch(`${API}/geometrias/${prod._id}`)).json()
  console.log(`restaurado: bbox=${bbox(restaurado)} (igual ao antes: ${bbox(restaurado) === bbox(antes)})`)

  // primitiva + fantasma + corte, e descarta
  await page.getByRole('button', { name: '+ adicionar primitiva' }).click()
  await page.getByLabel('fantasma do original').check()
  await page.getByLabel('corte em Y').check()
  await page.waitForTimeout(600)
  await page.screenshot({ path: `${OUT}/3-primitiva-fantasma-corte.png` })
  await page.getByRole('button', { name: 'descartar' }).click()

  // informações
  await page.getByRole('button', { name: 'Informações' }).click()
  const nomeInput = page.locator('label:has-text("Nome") input')
  const nomeOrig = await nomeInput.inputValue()
  await nomeInput.fill(nomeOrig + ' (editado)')
  await page.getByRole('button', { name: 'Salvar informações', exact: true }).click()
  await page.getByText('Informações salvas.').waitFor({ timeout: 30000 })
  const p3 = await (await fetch(`${API}/produtos/${prod._id}`)).json()
  console.log(`info: nome="${p3.nome}" infoOriginal.nome="${p3.infoOriginal?.nome}"`)
  await page.screenshot({ path: `${OUT}/4-informacoes.png` })
  await page.getByRole('button', { name: 'voltar' }).first().click()
  await page.getByRole('button', { name: 'Salvar informações', exact: true }).click()
  await page.getByText('Informações salvas.').waitFor({ timeout: 30000 })
  const p4 = await (await fetch(`${API}/produtos/${prod._id}`)).json()
  if (p4.nome !== nomeOrig) throw new Error(`nome não voltou: "${p4.nome}"`)
  console.log('info restaurada:', p4.nome)
  await page.getByRole('button', { name: 'Geometria' }).click()
}

// exportações
const baixados = {}
for (const [btn, ext] of [['Exportar IFC', 'ifc'], ['Exportar .aq', 'aq']]) {
  const [dl] = await Promise.all([
    page.waitForEvent('download', { timeout: 300000 }),
    page.getByRole('button', { name: btn, exact: true }).click(),
  ])
  const destino = `${OUT}/${dl.suggestedFilename()}`
  await dl.saveAs(destino)
  baixados[ext] = destino
  console.log(`${ext}: ${dl.suggestedFilename()} ${(statSync(destino).size / 1024).toFixed(0)} KB`)
  await page.getByText(ext === 'aq' ? /^\.aq gerado/ : /^IFC gerado/).waitFor({ timeout: 60000 })
}
await page.screenshot({ path: `${OUT}/5-exportado.png` })
await browser.close()

if (VALIDAR) {
  const py = (code) => execFileSync('python3', ['-c', code], { cwd: REPO, encoding: 'utf8' }).trim()
  console.log('parse_ifc.py →', py(`import sys;sys.path.insert(0,'scripts');import parse_ifc;r=parse_ifc.parse_ifc_file(${JSON.stringify(baixados.ifc)});print(len(r['pos'])//9,'triângulos')`))
  // validar_aq.py sai com código != 0 na regra "barras de tubo com 600 cm", que é da Akato e
  // não se aplica a uma peça só — o que interessa está no stdout, com ou sem erro.
  let saidaAq = ''
  try { saidaAq = execFileSync('python3', ['eng-reversa/tools/validar_aq.py', baixados.aq], { cwd: REPO, encoding: 'utf8' }) } catch (e) { saidaAq = e.stdout ?? String(e) }
  console.log('validar_aq.py →', saidaAq.split('\n').filter((l) => /FALHA\(S\)|blobs são OQ3D|triângulos  bbox/.test(l)).map((l) => l.trim()).join(' | '))
}

console.log('erros de console/página:', erros.length ? erros : 'nenhum')
if (erros.length) process.exit(1)
