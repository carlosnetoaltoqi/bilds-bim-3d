#!/usr/bin/env node
/**
 * thumbs.mjs — renderiza miniaturas com o mesmo Three.js da página.
 *
 * Chamado pelo `miniaturas.py` (pipeline estático e CLI) e pelo serviço de ingestão
 * (`apps/ingestao`, do Node). Recebe UM argumento: o caminho de um JSON com
 *
 *   { harnessDir, vendorDir, geoDir, outDir, geos[], width, height, mime, quality, ext, sairComStdin }
 *
 *   harnessDir  pasta com harness.html (este diretório)
 *   vendorDir   pasta com three.module.js (opcional: por padrão a build/ do `three` instalado ao lado deste arquivo)
 *   geoDir      pasta com os JSONs de geometria; `geos` são caminhos relativos a ela
 *   outDir      onde escrever <geo-sem-extensão>.<ext>
 *
 * Sobe um servidor estático efêmero com três montagens — /harness.html, /vendor/*, /geo/*
 * (os módulos ES do harness precisam de http:// — file:// esbarra em CORS) — abre o
 * harness no Chromium e chama window.renderThumb() uma vez por geometria.
 *
 * Imprime uma linha JSON por geometria em stdout ({geo, bytes} ou {geo, error}) para o
 * chamador relatar progresso e falhas.
 *
 * Saída: 0 = tudo renderizado; 2 = alguma geometria falhou (o chamador decide);
 * 1 = erro de infraestrutura (sem browser, etc).
 *
 * Com `sairComStdin: true` (o serviço de ingestão liga), se o stdin fechar (o pai morreu) fecha
 * o Chromium e sai com 2 — ver processo.py. Fora do serviço o stdin pode ser /dev/null, e aí
 * a vigia não pode estar ligada.
 */
import { createServer } from 'node:http'
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { createReadStream, existsSync, statSync } from 'node:fs'
import { extname, join, resolve, basename, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'

const AQUI = dirname(fileURLToPath(import.meta.url))

const MIMES = {
  '.html': 'text/html; charset=utf-8',
  // Módulos ES são rejeitados pelo Chromium com qualquer outro Content-Type
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
}

/** Serve `/harness.html`, `/vendor/<f>` e `/geo/<caminho>` de três pastas distintas. */
function startServer(montagens) {
  return new Promise((ok, fail) => {
    const srv = createServer((req, res) => {
      const urlPath = decodeURIComponent(new URL(req.url, 'http://x').pathname)
      let filePath = null
      if (urlPath === '/harness.html') filePath = join(montagens.harnessDir, 'harness.html')
      else if (urlPath.startsWith('/vendor/')) filePath = resolve(join(montagens.vendorDir, urlPath.slice('/vendor/'.length)))
      else if (urlPath.startsWith('/geo/')) filePath = resolve(join(montagens.geoDir, urlPath.slice('/geo/'.length)))
      const raiz = urlPath.startsWith('/vendor/') ? montagens.vendorDir : urlPath.startsWith('/geo/') ? montagens.geoDir : montagens.harnessDir
      // Impede escapar da pasta montada via ../
      if (!filePath || !filePath.startsWith(resolve(raiz)) || !existsSync(filePath) || !statSync(filePath).isFile()) {
        res.writeHead(404).end('not found')
        return
      }
      res.writeHead(200, { 'Content-Type': MIMES[extname(filePath)] ?? 'application/octet-stream' })
      createReadStream(filePath).pipe(res)
    })
    srv.on('error', fail)
    srv.listen(0, '127.0.0.1', () => ok({ srv, port: srv.address().port }))
  })
}

const cfg = JSON.parse(await readFile(process.argv[2], 'utf8'))
const {
  harnessDir = AQUI,
  vendorDir: vendorDirCfg,
  geoDir,
  outDir,
  geos,
  width = 448,
  height = 324,
  mime = 'image/webp',
  quality = 0.85,
  ext = 'webp',
  sairComStdin = false,
} = cfg

// `three/build/three.module.js` não está no `exports` do pacote: resolve-se o pacote e toma-se a pasta.
// O `three` vem do package.json deste diretório (mesma cena do viewer; a versão exata não afeta o render).
let vendor = vendorDirCfg ?? process.env.BILDS_THREE_DIR
if (!vendor) {
  try { vendor = dirname(createRequire(import.meta.url).resolve('three')) } catch { vendor = undefined }
}
if (!vendor || !existsSync(join(vendor, 'three.module.js'))) {
  console.error(`three.module.js não encontrado (vendorDir=${vendor}) — rode \`pnpm install\` em ${AQUI} ou aponte BILDS_THREE_DIR`)
  process.exit(1)
}
const vendorDir = vendor

let chromium
try {
  ;({ chromium } = await import('playwright'))
} catch {
  console.error(`playwright ausente — rode: pnpm install em ${AQUI}`)
  process.exit(1)
}

await mkdir(outDir, { recursive: true })
const { srv, port } = await startServer({ harnessDir, vendorDir, geoDir })

// SwiftShader: não há GPU nesta classe de máquina (CI, WSL, container).
// Sem estes flags o WebGL simplesmente não inicializa em headless.
let browser
try {
  browser = await chromium.launch({
    args: [
      '--use-gl=angle',
      '--use-angle=swiftshader',
      '--enable-unsafe-swiftshader',
    ],
  })
} catch (err) {
  srv.close()
  // A falha típica é lib de sistema ausente; o stack do Playwright tem centenas
  // de linhas e enterra a única linha acionável.
  const msg = String(err.message ?? err)
  const lib = msg.match(/error while loading shared libraries: ([^\s:]+)/)
  console.error(
    lib
      ? `Chromium não sobe: falta ${lib[1]}. Rode: sudo apt-get install -y libnss3 libnspr4 libasound2t64`
      : `Chromium não sobe: ${msg.split('\n')[0]}`
  )
  process.exit(1)
}

// Pai morto (stdin fechado): não seguir renderizando o que ninguém vai registrar
let abortado = false
if (sairComStdin) {
  process.stdin.on('end', () => { abortado = true })
  process.stdin.on('close', () => { abortado = true })
  process.stdin.resume()
}

let falhas = 0
try {
  const page = await browser.newPage()
  page.on('pageerror', (e) => console.error('pageerror:', e.message))
  await page.goto(`http://127.0.0.1:${port}/harness.html`, { waitUntil: 'load' })
  await page.waitForFunction('window.__thumbReady === true', { timeout: 30_000 })

  for (const geo of geos) {
    if (abortado) {
      console.error('thumbs.mjs: o processo pai fechou o stdin — fechando o Chromium e saindo (2)')
      break
    }
    const stem = geo.replace(/\.json$/i, '')
    // Segmentos são encodados um a um: há pastas com espaço e vírgula
    // ("Fabricante/PVC Esgoto SN, SR e Silentium") e a barra não pode ser escapada.
    const geoUrl = '/geo/' + geo.split(/[\\/]/).map(encodeURIComponent).join('/')
    try {
      const dataUrl = await page.evaluate(
        ([u, w, h, m, q]) => window.renderThumb(u, w, h, m, q),
        [geoUrl, width, height, mime, quality]
      )
      const b64 = dataUrl.slice(dataUrl.indexOf(',') + 1)
      const buf = Buffer.from(b64, 'base64')
      const dest = join(outDir, `${basename(stem)}.${ext}`)
      await writeFile(dest, buf)
      console.log(JSON.stringify({ geo: basename(stem), bytes: buf.length }))
    } catch (err) {
      falhas++
      console.log(JSON.stringify({ geo: basename(stem), error: String(err.message ?? err) }))
    }
  }
} finally {
  await browser.close()
  srv.close()
}

process.exit(falhas || abortado ? 2 : 0)
