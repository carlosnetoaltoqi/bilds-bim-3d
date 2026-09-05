/**
 * Harness do I14: o PUT /geometrias/:id e o POST /geometrias/:id/restaurar têm de disparar a
 * regeneração da miniatura, e `regerarMiniatura` tem de registrar o resultado no produto.
 *
 * Instancia o GeometriasController e o ImportacoesService à mão (sem Nest, sem Mongo), com
 * modelos e store falsos em memória; o thumb-worker do último cenário é o REAL (fork via
 * ts-node) com um geoKey inexistente — falha sem precisar de Chromium. Imprime JSON.
 *
 *   cd www/apps/api && node --require ts-node/register/transpile-only --require reflect-metadata \
 *       ../../../tests/paridade/geometrias_thumb.cts
 *
 * Precisa rodar com CWD em www/apps/api (o ts-node lê o tsconfig com decorators de lá).
 * Extensão .cts porque o package.json da raiz tem "type": "module": um .ts aqui seria ESM
 * para o Node 24 (imports sem extensão falham e o hook do ts-node não é consultado).
 */
import * as path from 'node:path';
import * as os from 'node:os';
import * as fs from 'node:fs';
import { GeometriasController } from '../../www/apps/api/src/geometrias/geometrias.controller';
import { ImportacoesService } from '../../www/apps/api/src/importacoes/importacoes.service';
import { ProdutosController } from '../../www/apps/api/src/produtos/produtos.controller';

// ── falsos ───────────────────────────────────────────────────────────────────
function modeloFalso(docs: Record<string, any>) {
  const updates: Array<[string, any]> = [];
  const consulta = (v: any) => {
    const q: any = { exec: async () => v, lean: () => q, select: () => q };
    return q;
  };
  return {
    updates,
    findById: (id: string) => consulta(docs[id] ?? null),
    findByIdAndUpdate: (id: string, upd: any) => {
      updates.push([id, JSON.parse(JSON.stringify(upd))]);
      docs[id] = { ...(docs[id] ?? {}), ...upd };
      return consulta(docs[id]);
    },
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
    delete: async (k: string) => { arquivos.delete(k); },
    deleteByPrefix: async (p: string) => { for (const k of [...arquivos.keys()]) if (k.startsWith(p)) arquivos.delete(k); },
  };
}

const geoValida = { pos: [0, 0, 0, 1, 0, 0, 0, 1, 0], col: [], idx: [0, 1, 2] };

async function main() {
  const saida: Record<string, unknown> = {};

  // ── 1. PUT e restaurar chamam regerarMiniatura com (productId, importId, geoKey) ──
  {
    const produtos = modeloFalso({ p1: { _id: 'p1', importId: 'imp1', geoKey: 'geo/imp1/p1.json' } });
    const store = storeFalso();
    await store.put('geo/imp1/p1.json', Buffer.from(JSON.stringify(geoValida)));
    const chamadas: any[] = [];
    const importacoes = { regerarMiniatura: async (...a: any[]) => { chamadas.push(a); return null; } };
    const ctrl = new GeometriasController(produtos as any, store as any, importacoes as any);
    (ctrl as any).logger = { log() {}, warn() {}, error() {} }; // o Nest Logger escreve no stdout e suja o JSON

    const r1 = await ctrl.putGeometry('p1', { ...geoValida, pos: geoValida.pos.map((v) => v * 2) });
    const r2 = await ctrl.restaurar('p1');
    saida.put_e_restaurar = {
      putMiniatura: (r1 as any).miniatura,
      restaurarMiniatura: (r2 as any).miniatura,
      chamadas,
      backupFeito: (r1 as any).backupFeito,
      origRemovido: !store.arquivos.has('geo/imp1/p1.orig.json'),
    };
  }

  // ── 2. regerarMiniatura com o thumb-worker REAL e geoKey inexistente → thumbErro no produto ──
  {
    const tsNode = path.join(process.cwd(), 'node_modules', 'ts-node');
    if (!fs.existsSync(tsNode)) {
      saida.regerar_real_geo_inexistente = { skip: 'sem ts-node em www/apps/api/node_modules' };
    } else {
      const storage = fs.mkdtempSync(path.join(os.tmpdir(), 'geometrias-thumb-'));
      process.env.STORAGE_PATH = storage;
      const produtos = modeloFalso({ p1: { _id: 'p1' } });
      const imports = modeloFalso({});
      const svc = new ImportacoesService(imports as any, {} as any, produtos as any, {} as any, storeFalso() as any);
      (svc as any).logger = { log() {}, warn() {}, error() {} }; // silencia o Nest Logger no stdout
      const resumo = await svc.regerarMiniatura('p1', 'imp1', 'geo/imp1/nao-existe.json');
      fs.rmSync(storage, { recursive: true, force: true });
      saida.regerar_real_geo_inexistente = { resumo, updates: produtos.updates, importUpdates: imports.updates };
    }
  }

  // ── 3. GET /produtos/:id devolve o que regerarMiniatura gravou (S7.13) ──────────────
  {
    const quando = new Date('2026-09-05T17:09:44.859Z');
    const produtos = modeloFalso({
      ok: { _id: 'ok', catalogId: 'c', importId: 'imp1', id: 'x', nome: 'X', geoKey: 'geo/imp1/x.json', thumbKey: 'thumbs/imp1/ok.webp', thumbAtualizadaEm: quando, thumbErro: null },
      falhou: { _id: 'falhou', catalogId: 'c', importId: 'imp1', id: 'y', nome: 'Y', geoKey: 'geo/imp1/y.json', thumbErro: 'EACCES: permission denied' },
    });
    const ctrl = new ProdutosController(produtos as any, {} as any);
    const ok: any = await ctrl.get('ok');
    const falhou: any = await ctrl.get('falhou');
    saida.get_produto_expoe_miniatura = {
      ok: { thumbAtualizadaEm: ok.thumbAtualizadaEm, thumbErro: ok.thumbErro, thumbUrl: ok.thumbUrl },
      falhou: { thumbAtualizadaEm: falhou.thumbAtualizadaEm, thumbErro: falhou.thumbErro, thumbUrl: falhou.thumbUrl },
    };
  }

  process.stdout.write(JSON.stringify(saida));
}

main().catch((e) => { console.error(e); process.exit(1); });
