#!/usr/bin/env node
/**
 * thumbs.mjs — renderiza as miniaturas do catálogo com o mesmo Three.js da página.
 *
 * Chamado por scripts/build.py. Recebe UM argumento: o caminho de um JSON com
 *
 *   { root, geoDir, outDir, geos[], width, height, mime, quality, ext, concurrency }
 *
 * Sobe um servidor estático sobre `root` (os módulos ES do harness precisam de
 * http:// — file:// esbarra em CORS), abre templates/thumbs/harness.html no
 * Chromium e chama window.renderThumb() uma vez por geometria.
 *
 * Escreve <outDir>/<geo-sem-extensao>.<ext> e imprime uma linha JSON por
 * geometria em stdout, para o build.py relatar progresso e falhas.
 *
 * Saída: 0 = tudo renderizado; 2 = alguma geometria falhou (o build segue sem
 * as thumbs que faltaram); 1 = erro de infraestrutura (sem browser, etc).
 */
import { createServer } from 'node:http'
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { createReadStream, existsSync } from 'node:fs'
import { extname, join, relative, resolve, basename } from 'node:path'

const MIMES = {
  '.html': 'text/html; charset=utf-8',
  // Módulos ES são rejeitados pelo Chromium com qualquer outro Content-Type
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
}

function startServer(root) {
  return new Promise((ok, fail) => {
    const srv = createServer((req, res) => {
      const urlPath = decodeURIComponent(new URL(req.url, 'http://x').pathname)
      const filePath = resolve(join(root, urlPath))
      // Impede escapar da raiz servida via ../
      if (!filePath.startsWith(resolve(root)) || !existsSync(filePath)) {
        res.writeHead(404).end('not found')
        return
      }
      res.writeHead(200, {
        'Content-Type': MIMES[extname(filePath)] ?? 'application/octet-stream',
      })
      createReadStream(filePath).pipe(res)
    })
    srv.on('error', fail)
    srv.listen(0, '127.0.0.1', () => ok({ srv, port: srv.address().port }))
  })
}

const cfg = JSON.parse(await readFile(process.argv[2], 'utf8'))
const {
  root,
  geoDir,
  outDir,
  geos,
  width = 448,
  height = 324,
  mime = 'image/webp',
  quality = 0.85,
  ext = 'webp',
} = cfg

let chromium
try {
  ;({ chromium } = await import('playwright'))
} catch {
  console.error('playwright ausente — rode: npm install')
  process.exit(1)
}

await mkdir(outDir, { recursive: true })
const { srv, port } = await startServer(root)

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
      ? `Chromium não sobe: falta ${lib[1]}. Rode: sudo npx playwright install-deps chromium`
      : `Chromium não sobe: ${msg.split('\n')[0]}`
  )
  process.exit(1)
}

let falhas = 0
try {
  const page = await browser.newPage()
  page.on('pageerror', (e) => console.error('pageerror:', e.message))
  await page.goto(
    `http://127.0.0.1:${port}/templates/thumbs/harness.html`,
    { waitUntil: 'load' }
  )
  await page.waitForFunction('window.__thumbReady === true', { timeout: 30_000 })

  for (const geo of geos) {
    const stem = basename(geo).replace(/\.json$/i, '')
    // Segmentos são encodados um a um: há pastas com espaço e vírgula
    // ("Amanco/PVC Esgoto SN, SR e Silentium") e a barra não pode ser escapada.
    const geoUrl =
      '/' +
      relative(root, join(geoDir, geo))
        .split(/[\\/]/)
        .map(encodeURIComponent)
        .join('/')
    try {
      const dataUrl = await page.evaluate(
        ([u, w, h, m, q]) => window.renderThumb(u, w, h, m, q),
        [geoUrl, width, height, mime, quality]
      )
      const b64 = dataUrl.slice(dataUrl.indexOf(',') + 1)
      const buf = Buffer.from(b64, 'base64')
      const dest = join(outDir, `${stem}.${ext}`)
      await writeFile(dest, buf)
      console.log(JSON.stringify({ geo: stem, bytes: buf.length }))
    } catch (err) {
      falhas++
      console.log(JSON.stringify({ geo: stem, error: String(err.message ?? err) }))
    }
  }
} finally {
  await browser.close()
  srv.close()
}

process.exit(falhas ? 2 : 0)
