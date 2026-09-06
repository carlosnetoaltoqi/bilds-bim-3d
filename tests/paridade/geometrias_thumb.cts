/**
 * Harness do I14/A5/A6: `PUT /geometrias/:id` e `POST /geometrias/:id/restaurar` da API
 *
 *   1. pedem a miniatura nova ao serviço de ingestão (IngestaoClient) — a API não tem Chromium;
 *   2. fazem copy-on-write quando a geometria é compartilhada com outros produtos (o pipeline
 *      grava uma por simbologia): o produto ganha `geo/<importId>/<productId>.json` e guarda a
 *      chave compartilhada em `geoKeyCompartilhada`; restaurar desfaz;
 *   3. quando o serviço não responde, registram `thumbErro` no produto e devolvem
 *      `miniatura: 'nao-solicitada'`;
 *   4. `GET /produtos/:id` devolve `thumbAtualizadaEm`/`thumbErro` (I31).
 *
 * Instancia os controllers à mão (sem Nest, sem Mongo, sem rede), com modelos, store e cliente
 * falsos em memória. Imprime JSON para tests/test_geometrias_thumb.py.
 *
 *   cd servicos/editor-de-pecas && node --require ts-node/register/transpile-only --require reflect-metadata \
 *       ../../../tests/paridade/geometrias_thumb.cts
 *
 * Extensão .cts porque o package.json da raiz tem "type": "module".
 */
import * as path from 'node:path';
import { GeometriasEdicaoController as GeometriasController } from '../../servicos/editor-de-pecas/src/geometrias-edicao.controller';
import { ProdutosEdicaoController as ProdutosController } from '../../servicos/editor-de-pecas/src/produtos-edicao.controller';
import { ProdutosController as ProdutosLeituraController } from '../../servicos/catalogo-api/src/produtos/produtos.controller';

// ── falsos ───────────────────────────────────────────────────────────────────
function modeloFalso(docs: Record<string, any>) {
  const updates: Array<[string, any]> = [];
  const consulta = (v: any) => {
    const q: any = { exec: async () => v, lean: () => q, select: () => q };
    return q;
  };
  return {
    docs,
    updates,
    findById: (id: string) => consulta(docs[id] ?? null),
    findByIdAndUpdate: (id: string, upd: any) => {
      updates.push([id, JSON.parse(JSON.stringify(upd))]);
      docs[id] = { ...(docs[id] ?? {}), ...upd };
      return consulta(docs[id]);
    },
    countDocuments: (filtro: any) => consulta(Object.values(docs).filter((d: any) => d.geoKey === filtro.geoKey && d._id !== filtro._id.$ne).length),
  };
}

function storeFalso() {
  const arquivos = new Map<string, Buffer>();
  const enoent = () => Object.assign(new Error('ENOENT'), { code: 'ENOENT' });
  return {
    arquivos,
    put: async (k: string, b: Buffer) => { arquivos.set(k, b); },
    get: async (k: string) => { if (!arquivos.has(k)) throw enoent(); return arquivos.get(k)!; },
    stat: async (k: string) => { if (!arquivos.has(k)) throw enoent(); return { size: arquivos.get(k)!.length, mtimeMs: 1 }; },
    delete: async (k: string) => { if (!arquivos.has(k)) throw enoent(); arquivos.delete(k); },
    deleteByPrefix: async (p: string) => { for (const k of [...arquivos.keys()]) if (k.startsWith(p)) arquivos.delete(k); },
  };
}

function clienteFalso(resposta: { ok: boolean; erro?: string } = { ok: true }) {
  const chamadas: string[] = [];
  return { chamadas, regerarMiniatura: async (id: string) => { chamadas.push(id); return resposta; } };
}

// o Logger do Nest escreve no stdout e sujaria o JSON que o pytest lê (resolvido a partir de apps/api: este arquivo mora em tests/)
const { Logger } = require(require.resolve('@nestjs/common', { paths: [path.resolve(__dirname, '../../servicos/editor-de-pecas')] }));
Logger.overrideLogger(false);

const geoValida = { pos: [0, 0, 0, 1, 0, 0, 0, 1, 0], col: [], idx: [0, 1, 2] };
const geoNova = { pos: [0, 0, 0, 2, 0, 0, 0, 2, 0], col: [], idx: [0, 1, 2] };

async function main() {
  const saida: Record<string, unknown> = {};

  // ── 1. geometria exclusiva: backup .orig.json, miniatura pedida no PUT e no restaurar ──
  {
    const produtos = modeloFalso({ p1: { _id: 'p1', importId: 'imp1', geoKey: 'geo/imp1/p1.json', geoKeyCompartilhada: null } });
    const store = storeFalso();
    await store.put('geo/imp1/p1.json', Buffer.from(JSON.stringify(geoValida)));
    const cliente = clienteFalso();
    const ctrl = new GeometriasController(produtos as any, store as any, cliente as any);
    const put = await ctrl.putGeometry('p1', geoNova);
    const temOrig = store.arquivos.has('geo/imp1/p1.orig.json');
    const rest = await ctrl.restaurar('p1');
    saida.exclusiva = {
      putMiniatura: put.miniatura, putGeoKey: put.geoKey, backupFeito: put.backupFeito, copiaFeita: put.copiaFeita,
      temOrigDepoisDoPut: temOrig,
      restaurarMiniatura: (rest as any).miniatura, restaurado: (rest as any).restaurado,
      origRemovido: !store.arquivos.has('geo/imp1/p1.orig.json'),
      vivoVoltouAoOriginal: JSON.parse(store.arquivos.get('geo/imp1/p1.json')!.toString()).pos[3] === 1,
      chamadas: cliente.chamadas,
    };
  }

  // ── 2. geometria compartilhada: copy-on-write no PUT, desfeito no restaurar ──
  {
    const produtos = modeloFalso({
      p1: { _id: 'p1', importId: 'imp1', geoKey: 'geo/imp1/g.json', geoKeyCompartilhada: null, thumbKey: 'thumbs/imp1/g.webp' },
      p2: { _id: 'p2', importId: 'imp1', geoKey: 'geo/imp1/g.json', geoKeyCompartilhada: null, thumbKey: 'thumbs/imp1/g.webp' },
    });
    const store = storeFalso();
    await store.put('geo/imp1/g.json', Buffer.from(JSON.stringify(geoValida)));
    const cliente = clienteFalso();
    const ctrl = new GeometriasController(produtos as any, store as any, cliente as any);
    const put = await ctrl.putGeometry('p1', geoNova);
    const depoisDoPut = {
      p1: { geoKey: produtos.docs.p1.geoKey, compartilhada: produtos.docs.p1.geoKeyCompartilhada },
      p2: { geoKey: produtos.docs.p2.geoKey, compartilhada: produtos.docs.p2.geoKeyCompartilhada ?? null },
      arquivos: [...store.arquivos.keys()].sort(),
      compartilhadoIntacto: JSON.parse(store.arquivos.get('geo/imp1/g.json')!.toString()).pos[3] === 1,
      proprioNovo: JSON.parse(store.arquivos.get('geo/imp1/p1.json')!.toString()).pos[3] === 2,
    };
    // segundo PUT no mesmo produto: já tem arquivo próprio — não copia de novo nem faz .orig
    const put2 = await ctrl.putGeometry('p1', geoValida);
    const rest = await ctrl.restaurar('p1');
    saida.compartilhada = {
      put: { geoKey: put.geoKey, copiaFeita: put.copiaFeita, backupFeito: put.backupFeito, geoKeyCompartilhada: put.geoKeyCompartilhada, miniatura: put.miniatura },
      depoisDoPut,
      put2: { geoKey: put2.geoKey, copiaFeita: put2.copiaFeita, backupFeito: put2.backupFeito },
      semOrigJson: ![...store.arquivos.keys()].some((k) => k.endsWith('.orig.json')),
      restaurar: { restaurado: (rest as any).restaurado, geoKey: (rest as any).geoKey, miniatura: (rest as any).miniatura },
      depoisDoRestaurar: {
        p1: { geoKey: produtos.docs.p1.geoKey, compartilhada: produtos.docs.p1.geoKeyCompartilhada, geoEditadoEm: produtos.docs.p1.geoEditadoEm },
        arquivos: [...store.arquivos.keys()].sort(),
      },
      chamadas: cliente.chamadas,
    };
  }

  // ── 3. serviço de ingestão fora: thumbErro no produto, resposta diz que não pediu ──
  {
    const produtos = modeloFalso({ p1: { _id: 'p1', importId: 'imp1', geoKey: 'geo/imp1/p1.json', geoKeyCompartilhada: null } });
    const store = storeFalso();
    await store.put('geo/imp1/p1.json', Buffer.from(JSON.stringify(geoValida)));
    const cliente = clienteFalso({ ok: false, erro: 'serviço de ingestão indisponível em http://localhost:4100 — fetch failed' });
    const ctrl = new GeometriasController(produtos as any, store as any, cliente as any);
    const put = await ctrl.putGeometry('p1', geoNova);
    saida.ingestao_fora = {
      miniatura: put.miniatura, miniaturaErro: put.miniaturaErro, geometriaGravada: JSON.parse(store.arquivos.get('geo/imp1/p1.json')!.toString()).pos[3] === 2,
      thumbErroNoProduto: produtos.docs.p1.thumbErro, chamadas: cliente.chamadas,
    };
  }

  // ── 4. GET /produtos/:id expõe thumbAtualizadaEm e thumbErro (I31) ──
  {
    const quando = new Date('2026-09-05T17:09:44.859Z');
    const produtos = modeloFalso({
      ok: { _id: 'ok', catalogId: 'c', importId: 'imp1', id: 'x', nome: 'X', geoKey: 'geo/imp1/x.json', thumbKey: 'thumbs/imp1/ok.webp', thumbAtualizadaEm: quando, thumbErro: null },
      falhou: { _id: 'falhou', catalogId: 'c', importId: 'imp1', id: 'y', nome: 'Y', geoKey: 'geo/imp1/y.json', thumbErro: 'EACCES: permission denied' },
    });
    // a LEITURA do produto (GET /produtos/:id) é da API de catálogo; o editor só tem o PATCH
    const ctrl = new ProdutosLeituraController(produtos as any, {} as any, {} as any, {} as any, {} as any);
    const pick = (d: any) => ({ thumbAtualizadaEm: d.thumbAtualizadaEm, thumbErro: d.thumbErro, thumbUrl: d.thumbUrl });
    saida.get_produto_expoe_miniatura = { ok: pick(await ctrl.get('ok')), falhou: pick(await ctrl.get('falhou')) };
  }

  process.stdout.write(JSON.stringify(saida));
}

main().catch((e) => { console.error(e); process.exit(1); });
