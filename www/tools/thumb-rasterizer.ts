/**
 * thumb-rasterizer.ts — miniaturas idênticas ao viewer 3D (Playwright + harness.html)
 *
 * Substitui o rasterizador software (agora em `thumb-rasterizer-sw.ts`), que usava
 * flat shading e uma aproximação de iluminação e por isso divergia visivelmente do
 * que o usuário vê no viewer. Aqui a miniatura é produzida pelo MESMO Three.js,
 * com o MESMO `buildScene()` e a MESMA câmera do viewer — via
 * `www/apps/ingestao/pipeline/harness.html`, o mesmo harness do pipeline estático
 * (`www/apps/ingestao/pipeline/thumbs.mjs`).
 *
 * Arquitetura (docs/solutions/architecture-patterns/thumb-qualidade-identica-ao-viewer.md):
 *
 *   renderThumbPlaywright(geoData)
 *     └─ getSession()                     ← singleton por processo
 *          ├─ servidor HTTP efêmero sobre a raiz do repo (porta 0)
 *          ├─ chromium.launch({ args: SWIFTSHADER_ARGS })
 *          └─ page.goto('http://127.0.0.1:<porta>/www/apps/ingestao/pipeline/harness.html')
 *     └─ page.evaluate(d => window.renderThumbFromData(d, …), geoData)
 *     └─ data URL WebP → Buffer
 *
 * Por que um servidor HTTP e não `file://`: o harness carrega o Three.js como
 * módulo ES via importmap, e o Chromium recusa `import` sobre `file://` por CORS.
 * A porta é efêmera (`listen(0)`) — nunca colide com a API (4000) nem com o web (3000).
 *
 * O browser é reaproveitado entre chamadas do mesmo processo: o custo de subida
 * (~1 s) é pago uma vez por worker, não por miniatura. Quem usa este módulo deve
 * chamar `closeThumbRenderer()` antes de encerrar o processo.
 *
 * Compatibilidade: `renderThumbTs` continua exportado com a mesma assinatura de
 * antes — `(data, width?, height?) => Promise<Buffer>` — para não exigir mudança
 * em quem já importava.
 */

import { createReadStream, existsSync } from 'node:fs';
import { createServer, Server } from 'node:http';
import * as path from 'node:path';

export interface RasterBuffers {
  pos: number[];
  col: number[];
  idx: number[];
}

export const THUMB_W = 448;
export const THUMB_H = 324;
export const THUMB_MIME = 'image/webp';
export const THUMB_QUALITY = 0.85;

/**
 * Sem GPU (WSL, container, CI) o WebGL headless só inicializa por SwiftShader.
 * `--no-sandbox` é necessário quando o processo já roda sem privilégios de
 * namespace — caso do worker forkado dentro de container.
 */
const SWIFTSHADER_ARGS = [
  '--use-gl=angle',
  '--use-angle=swiftshader',
  '--enable-unsafe-swiftshader',
  '--no-sandbox',
];

/** www/tools/ → bilds-bim-3d/ — o harness e o Three.js vendorizado saem daqui. */
const REPO_ROOT = path.resolve(__dirname, '../..');
const HARNESS_PATH = '/www/apps/ingestao/pipeline/harness.html';

/** Módulos ES são rejeitados pelo Chromium com qualquer outro Content-Type. */
const MIMES: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
};

/**
 * O playwright vive em `bilds-bim-3d/node_modules/` (package.json da raiz, isolado
 * do workspace pnpm de `www/`). Tenta a resolução normal primeiro para o caso de
 * um dia virar dependência do workspace.
 */
function loadPlaywright(): any {
  try {
    return require('playwright');
  } catch {
    /* cai para a raiz do repo */
  }
  try {
    return require(path.join(REPO_ROOT, 'node_modules', 'playwright'));
  } catch (err: any) {
    throw new Error(
      `playwright não encontrado (nem no workspace nem em ${REPO_ROOT}/node_modules). ` +
        `Rode: npm install --prefix ${REPO_ROOT}  — detalhe: ${err.message}`,
    );
  }
}

function startServer(root: string): Promise<{ srv: Server; port: number }> {
  return new Promise((resolve, reject) => {
    const srv = createServer((req, res) => {
      const urlPath = decodeURIComponent(new URL(req.url!, 'http://x').pathname);
      const filePath = path.resolve(path.join(root, urlPath));
      // Impede escapar da raiz servida via ../
      if (!filePath.startsWith(path.resolve(root)) || !existsSync(filePath)) {
        res.writeHead(404).end('not found');
        return;
      }
      res.writeHead(200, {
        'Content-Type': MIMES[path.extname(filePath)] ?? 'application/octet-stream',
      });
      createReadStream(filePath).pipe(res);
    });
    srv.on('error', reject);
    srv.listen(0, '127.0.0.1', () => resolve({ srv, port: (srv.address() as any).port }));
  });
}

interface Session {
  browser: any;
  page: any;
  srv: Server;
}

let sessionPromise: Promise<Session> | null = null;

async function openSession(): Promise<Session> {
  const { chromium } = loadPlaywright();
  const { srv, port } = await startServer(REPO_ROOT);

  let browser: any;
  try {
    browser = await chromium.launch({ args: SWIFTSHADER_ARGS });
  } catch (err: any) {
    srv.close();
    // A falha típica é lib de sistema ausente, e o stack do Playwright tem
    // centenas de linhas que enterram a única linha acionável.
    const msg = String(err?.message ?? err);
    const lib = msg.match(/error while loading shared libraries: ([^\s:]+)/);
    throw new Error(
      lib
        ? `Chromium não sobe: falta ${lib[1]}. Rode: sudo apt-get install -y libnss3 libnspr4 libasound2t64`
        : `Chromium não sobe: ${msg.split('\n')[0]}`,
    );
  }

  try {
    const page = await browser.newPage();
    page.on('pageerror', (e: Error) => {
      // eslint-disable-next-line no-console
      console.error('[thumb harness pageerror]', e.message);
    });
    await page.goto(`http://127.0.0.1:${port}${HARNESS_PATH}`, { waitUntil: 'load' });
    // O import de `three` é assíncrono: sem esperar, renderThumbFromData não existe.
    await page.waitForFunction('window.__thumbReady === true', { timeout: 30_000 });
    return { browser, page, srv };
  } catch (err) {
    await browser.close().catch(() => {});
    srv.close();
    throw err;
  }
}

function getSession(): Promise<Session> {
  if (!sessionPromise) {
    sessionPromise = openSession().catch((err) => {
      // Não deixa uma sessão morta grudada: a próxima chamada tenta subir de novo.
      sessionPromise = null;
      throw err;
    });
  }
  return sessionPromise;
}

/**
 * Serializa os renders: há uma única página e um único contexto WebGL por
 * processo, e `renderThumbFromData` compartilha o renderer entre chamadas.
 */
let queue: Promise<unknown> = Promise.resolve();

function enqueue<T>(fn: () => Promise<T>): Promise<T> {
  const run = queue.then(fn, fn);
  queue = run.catch(() => {});
  return run;
}

/**
 * Renderiza {pos, col, idx} no Chromium com o Three.js do viewer e devolve WebP.
 * Lança se o Chromium não subir ou se o harness falhar.
 *
 * A geometria vai como STRING JSON e é parseada dentro da página, não como objeto.
 * Medido nesta máquina com geometria Dancor de 4,8 MB (35 k vértices, 52 k triângulos):
 *
 *   argumento como objeto : ~2 200 ms   ← o serializador do Playwright anda o grafo
 *   argumento como string : ~  370 ms   ← dos quais ~120 ms são o render WebGL
 *
 * O `JSON.stringify` aqui custa ~40 ms e o `JSON.parse` do outro lado ~13 ms. Sem
 * essa troca, o lote de 13 produtos da Dancor leva ~25 s em vez de ~7 s.
 */
export async function renderThumbPlaywright(
  data: RasterBuffers,
  width = THUMB_W,
  height = THUMB_H,
): Promise<Buffer> {
  const { page } = await getSession();
  const json = JSON.stringify(data);
  return enqueue(async () => {
    const dataUrl: string = await page.evaluate(
      ([j, w, h, m, q]: [string, number, number, string, number]) =>
        (window as any).renderThumbFromData(JSON.parse(j), w, h, m, q),
      [json, width, height, THUMB_MIME, THUMB_QUALITY] as [
        string,
        number,
        number,
        string,
        number,
      ],
    );
    const comma = dataUrl.indexOf(',');
    if (!dataUrl.startsWith('data:image/webp') || comma < 0) {
      throw new Error(`harness devolveu data URL inesperada: ${dataUrl.slice(0, 40)}`);
    }
    return Buffer.from(dataUrl.slice(comma + 1), 'base64');
  });
}

/** Nome antigo, mantido para não quebrar quem já importava. */
export const renderThumbTs = renderThumbPlaywright;

/**
 * Fecha o Chromium e o servidor. Obrigatório antes de `process.exit()` — sem isso
 * o processo fica preso no handle do servidor ou deixa o browser órfão.
 */
export async function closeThumbRenderer(): Promise<void> {
  const pending = sessionPromise;
  sessionPromise = null;
  if (!pending) return;
  let session: Session;
  try {
    session = await pending;
  } catch {
    return; // nunca chegou a abrir
  }
  await session.browser.close().catch(() => {});
  session.srv.close();
}
