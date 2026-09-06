/**
 * olhar_preview.mjs — abre a página de preview e fotografa as peças.
 *
 * As formas de `formas.py` foram validadas por topologia (arestas de borda),
 * escala (bounding box) e round-trip binário. Nada disso diz se a peça PARECE
 * um joelho. Este script usa o Playwright — o mesmo que o `thumb-worker` do
 * projeto usa — para abrir a página, esperar o Three.js montar as malhas e
 * gravar imagens.
 *
 * Grava também o console e os erros de rede: uma geometria que não carrega
 * aparece como card vazio, e sem ler o console isso passa por "renderizou".
 *
 * Uso:
 *   node olhar_preview.mjs <url> <dir-de-saida> [--cards=N] [--ids=a,b,c]
 *
 * `--ids` fotografa só o visor 3D dos produtos indicados, em 2× — é como se
 * confere uma forma de cada tipo. Rodar de dentro do repositório: o
 * `playwright` está no `node_modules` da raiz.
 */
import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';

const url = process.argv[2] || 'http://localhost:8080/akato-formas/';
const saida = process.argv[3] || 'eng-reversa/saida/olhada';
const nCards = Number(
  (process.argv.find((a) => a.startsWith('--cards')) || '').split('=')[1] || 12,
);
const idsPedidos = ((process.argv.find((a) => a.startsWith('--ids')) || '')
  .split('=')[1] || '').split(',').filter(Boolean);

await mkdir(saida, { recursive: true });

const browser = await chromium.launch({
  args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'],
});
const page = await browser.newPage({
  viewport: { width: 1500, height: 1000 },
  deviceScaleFactor: idsPedidos.length ? 2 : 1,
});

const erros = [];
page.on('console', (m) => {
  if (m.type() === 'error') erros.push(`console: ${m.text()}`);
});
page.on('pageerror', (e) => erros.push(`pageerror: ${e.message}`));
page.on('requestfailed', (r) =>
  erros.push(`rede: ${r.url()} — ${r.failure()?.errorText}`),
);
page.on('response', (r) => {
  if (r.status() >= 400) erros.push(`http ${r.status()}: ${r.url()}`);
});

await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });

if (idsPedidos.length) {
  for (const id of idsPedidos) {
    const card = page.locator(`.card[data-id="${id}"]`);
    if (!(await card.count())) { console.log(`  AUSENTE  ${id}`); continue; }
    await card.scrollIntoViewIfNeeded();
    await page.waitForTimeout(1400);
    const visor = card.locator('.card-canvas-wrap, canvas').first();
    const alvo = (await visor.count()) ? visor : card;
    await alvo.screenshot({ path: `${saida}/${id}.png` });
    console.log(`  ok       ${id}`);
  }
  if (erros.length) {
    console.log(`\n${erros.length} erro(s):`);
    for (const e of [...new Set(erros)].slice(0, 10)) console.log(`  - ${e}`);
  }
  await browser.close();
  process.exit(0);
}

const titulo = await page.title();
const info = await page.evaluate(() => ({
  cards: document.querySelectorAll('.card').length,
  canvas: document.querySelectorAll('canvas').length,
  filtros: document.querySelectorAll('[data-filtro], .filtro, .chip').length,
}));
console.log(`título : ${titulo}`);
console.log(`cards  : ${info.cards}`);
console.log(`canvas : ${info.canvas}`);

// A grade renderiza sob demanda: rolar a página força as primeiras peças a
// montar. Sem isso o canvas fica em branco e a foto não prova nada.
for (let y = 0; y < 4; y++) {
  await page.mouse.wheel(0, 700);
  await page.waitForTimeout(900);
}
await page.evaluate(() => window.scrollTo(0, 0));
await page.waitForTimeout(2500);

await page.screenshot({ path: `${saida}/grade.png`, fullPage: false });
console.log(`grade  : ${saida}/grade.png`);

// Quantos canvas de fato têm pixel desenhado — um canvas em branco significa
// malha que não chegou ou câmera fora do sólido.
const pintados = await page.evaluate(() => {
  let n = 0;
  const vazios = [];
  document.querySelectorAll('canvas').forEach((c, i) => {
    try {
      const g = c.getContext('webgl2') || c.getContext('webgl');
      if (!g) return;
      const px = new Uint8Array(4 * 64 * 64);
      g.readPixels(
        Math.max(0, (c.width >> 1) - 32),
        Math.max(0, (c.height >> 1) - 32),
        64, 64, g.RGBA, g.UNSIGNED_BYTE, px,
      );
      let soma = 0;
      for (let k = 0; k < px.length; k += 4) soma += px[k] + px[k + 1] + px[k + 2];
      if (soma > 0) n++; else vazios.push(i);
    } catch (e) { /* canvas sem contexto legível */ }
  });
  return { n, vazios: vazios.slice(0, 8) };
});
console.log(`canvas com pixel desenhado: ${pintados.n}`);
if (pintados.vazios.length) console.log(`  vazios: ${pintados.vazios}`);

// Fotografa peças individuais, no tamanho do card.
const cards = await page.locator('.card').all();
const alvos = cards.slice(0, nCards);
let i = 0;
for (const card of alvos) {
  const id = (await card.getAttribute('data-id')) || `card-${i}`;
  try {
    await card.scrollIntoViewIfNeeded();
    await page.waitForTimeout(700);
    await card.screenshot({ path: `${saida}/${String(i).padStart(2, '0')}-${id}.png` });
    console.log(`  peça ${String(i).padStart(2, '0')}: ${id}`);
  } catch (e) {
    console.log(`  peça ${String(i).padStart(2, '0')}: ${id} — falhou: ${e.message}`);
  }
  i++;
}

if (erros.length) {
  console.log(`\n${erros.length} erro(s) na página:`);
  for (const e of [...new Set(erros)].slice(0, 12)) console.log(`  - ${e}`);
} else {
  console.log('\nnenhum erro de console ou de rede');
}

await browser.close();
