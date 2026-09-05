/**
 * Harness do processamento de uma importação DENTRO da vaga da fila (S7.13 — achados do teste
 * de aceitação da POC):
 *
 *   1. ao começar (`parseando`) a nota "na fila — N à frente" é apagada — antes ficava no import
 *      publicado e a página mostrava "na fila" para um catálogo pronto;
 *   2. a promise que a fila espera só resolve depois das miniaturas — antes a vaga liberava em
 *      `publicado` e o Chromium do import anterior rodava junto com o parse (e o Chromium) do
 *      seguinte, exatamente o que `common/fila.ts` promete evitar. Vale para `.aq`
 *      (`ImportacoesService.processAsync`) e para CAD (`StepService.processar`).
 *
 * Instancia os dois serviços à mão (sem Nest, sem Mongo, sem worker): `runWorker`,
 * `spawnThumbWorker`, `tesselar` e `publicar` são substituídos na instância; a fila é a real.
 * Imprime JSON para tests/test_www_importacao.py.
 *
 *   cd www/apps/api && node --require ts-node/register/transpile-only --require reflect-metadata \
 *       ../../../tests/paridade/importacoes_processo.cts
 *
 * .cts e CWD em www/apps/api pelos mesmos motivos de geometrias_thumb.cts.
 */
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { ImportacoesService } from '../../www/apps/api/src/importacoes/importacoes.service';
import { StepService } from '../../www/apps/api/src/step/step.service';
import { Fila } from '../../www/apps/api/src/common/fila';

const tick = (ms: number) => new Promise((r) => setTimeout(r, ms));
const silencio = { log() {}, warn() {}, error() {} };

/** Modelo Mongoose falso: guarda cada findByIdAndUpdate e anota o status em `eventos`. */
function modeloFalso(docs: Record<string, any>, eventos: string[]) {
  const updates: Array<[string, any]> = [];
  const consulta = (v: any) => {
    const q: any = { exec: async () => v, lean: () => q, select: () => q, sort: () => q, distinct: () => q };
    return q;
  };
  return {
    updates,
    findById: (id: string) => consulta(docs[id] ?? null),
    findOne: () => consulta(null),
    find: () => consulta([]),
    create: async (d: any) => { docs[d._id] = d; return d; },
    insertMany: async (ds: any[]) => { for (const d of ds) docs[d._id] = d; return ds; },
    deleteMany: async () => ({ deletedCount: 0 }),
    findByIdAndUpdate: (id: string, upd: any) => {
      updates.push([id, JSON.parse(JSON.stringify(upd))]);
      if (upd.status) eventos.push(`update:${upd.status}`);
      docs[id] = { ...(docs[id] ?? {}), ...upd };
      return consulta(docs[id]);
    },
  };
}

/** Roda `trabalho` numa fila de concorrência 1 com um segundo pedido atrás; devolve a ordem dos eventos. */
async function comSegundoNaFila(eventos: string[], trabalho: () => Promise<unknown>) {
  const fila = new Fila(1);
  let posicaoSegundo = -1;
  const primeiro = fila.executar('primeiro', trabalho).then(() => eventos.push('processo:fim'));
  const segundo = fila.executar('segundo', async () => { eventos.push('segundo:inicio'); }, (n) => { posicaoSegundo = n; });
  await Promise.all([primeiro, segundo]);
  return posicaoSegundo;
}

async function main() {
  const saida: Record<string, unknown> = {};

  // ── .aq: ImportacoesService.processAsync ─────────────────────────────────────
  {
    const eventos: string[] = [];
    const imports = modeloFalso({ imp1: { _id: 'imp1', status: 'recebido', note: 'na fila — 1 importação(ões) à frente' } }, eventos);
    const catalogos = modeloFalso({}, []);
    const produtos = modeloFalso({}, []);
    const svc = new ImportacoesService(imports as any, catalogos as any, produtos as any, {} as any, {} as any, {} as any);
    (svc as any).logger = silencio;
    (svc as any).runWorker = async () => {
      eventos.push('worker');
      return {
        status: 'ok', productCount: 1,
        products: [{ id: 'a', nome: 'A', serie: 'S', specs: {}, curva: null, potencia: null, geoKey: 'geo/imp1/a.json' }],
        catalogMeta: { slug: 'cat', titulo: 'T', fabricante: 'F', layout: 'series-rows', filters: ['S'] },
      };
    };
    (svc as any).spawnThumbWorker = async () => {
      eventos.push('thumbs:inicio'); await tick(30); eventos.push('thumbs:fim');
      return { geradas: 1, total: 1, falhas: [] };
    };
    const aq = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'importacoes-processo-')), 'bim-x.aq');
    fs.writeFileSync(aq, 'sqlite falso');
    const posicaoSegundo = await comSegundoNaFila(eventos, () => (svc as any).processAsync('imp1', aq, 'c1'));
    saida.aq = { eventos, posicaoSegundo, updates: imports.updates, aqRemovido: !fs.existsSync(aq) };
    fs.rmSync(path.dirname(aq), { recursive: true, force: true });
  }

  // ── CAD: StepService.processar ───────────────────────────────────────────────
  {
    const eventos: string[] = [];
    const imports = modeloFalso({ imp2: { _id: 'imp2', status: 'recebido', note: 'na fila — 1 importação(ões) à frente' } }, eventos);
    const importacoes = {
      gerarMiniaturas: async (importId: string, products: any[]) => {
        eventos.push(`thumbs:inicio(${importId},${products.length})`); await tick(30); eventos.push('thumbs:fim');
        return null;
      },
    };
    const svc = new StepService(imports as any, {} as any, {} as any, {} as any, {} as any, importacoes as any, {} as any);
    (svc as any).logger = silencio;
    (svc as any).tesselar = async () => { eventos.push('python'); return { formato: 'step', partes: [1], idx: [0, 1, 2], caminho: null, aviso: null }; };
    (svc as any).publicar = async () => ({ productId: 'p1', geoKey: 'geo/imp2/p1.json', slug: 'pecas-step', nome: 'peça', catalogId: 'c' });
    const stp = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'importacoes-processo-')), 'cad-x.stp');
    fs.writeFileSync(stp, 'ISO-10303-21;');
    const posicaoSegundo = await comSegundoNaFila(eventos, () =>
      (svc as any).processar('imp2', { _id: 'c1', customUrl: 'poc' }, { stpPath: stp, fileName: 'peça.stp' }));
    saida.cad = { eventos, posicaoSegundo, updates: imports.updates, stpRemovido: !fs.existsSync(stp) };
    fs.rmSync(path.dirname(stp), { recursive: true, force: true });
  }

  process.stdout.write(JSON.stringify(saida));
}

main().catch((e) => { console.error(e); process.exit(1); });
