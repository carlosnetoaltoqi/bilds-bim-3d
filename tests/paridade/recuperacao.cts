/**
 * Harness da recuperação no boot (I11): `recuperarImportsOrfaos` e `limparUploadsTemporarios`
 * de `servicos/criador-de-catalogos/src/importacoes/recuperacao.service.ts`, com modelos e store falsos e um
 * tmpdir de verdade. Imprime JSON para tests/test_www_importacao.py.
 *
 *   cd servicos/criador-de-catalogos && node --require ts-node/register/transpile-only --require reflect-metadata \
 *       ../../../tests/paridade/recuperacao.cts
 */
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import {
  ERRO_REINICIO,
  RecuperacaoService,
  limparUploadsTemporarios,
  recuperarImportsOrfaos,
} from '../../servicos/criador-de-catalogos/src/importacoes/recuperacao.service';

const silencio = { log() {}, warn() {}, error() {} };

function importModelFalso(docs: Array<{ _id: string; status: string; updatedAt?: Date; createdAt?: Date }>) {
  const updates: Array<[string, any]> = [];
  return {
    updates,
    find: (filtro: any) => ({
      lean: () => ({ exec: async () => docs.filter((d) => filtro.status.$in.includes(d.status)) }),
    }),
    findByIdAndUpdate: (id: string, upd: any) => {
      updates.push([id, JSON.parse(JSON.stringify(upd))]);
      const d = docs.find((x) => x._id === id);
      if (d) Object.assign(d, upd);
      return { exec: async () => d };
    },
  };
}

async function main() {
  const saida: Record<string, unknown> = {};
  const agora = Date.parse('2026-09-05T12:00:00Z');
  const h = (horas: number) => new Date(agora - horas * 3600_000);

  // ── boot: todo não terminal vira falhou; terminais ficam ────────────────────
  {
    const docs = [
      { _id: 'i-recebido', status: 'recebido', updatedAt: h(0.01) },
      { _id: 'i-parseando', status: 'parseando', updatedAt: h(2) },
      { _id: 'i-gravando', status: 'gravando', createdAt: h(5) },
      { _id: 'i-publicado', status: 'publicado', updatedAt: h(1) },
      { _id: 'i-falhou', status: 'falhou', updatedAt: h(1) },
      { _id: 'i-vazio', status: 'vazio', updatedAt: h(1) },
    ];
    const imports = importModelFalso(docs);
    const produtosApagados: any[] = [];
    const prefixos: string[] = [];
    const produtos = { deleteMany: async (f: any) => { produtosApagados.push(f); return { deletedCount: 1 }; } };
    const store = { deleteByPrefix: async (p: string) => { prefixos.push(p); } };
    const marcados = await recuperarImportsOrfaos(imports as any, produtos as any, store, silencio, 0, agora);
    saida.boot_marca_nao_terminais = {
      marcados,
      statusFinal: Object.fromEntries(docs.map((d) => [d._id, d.status])),
      erro: imports.updates.map(([, u]) => u.error),
      notes: imports.updates.map(([, u]) => u.note),
      produtosApagados, prefixos,
    };
  }

  // ── sweep com idade mínima: só os antigos ───────────────────────────────────
  {
    const docs = [
      { _id: 'novo', status: 'parseando', updatedAt: h(0.1) },
      { _id: 'velho', status: 'parseando', updatedAt: h(2) },
    ];
    const imports = importModelFalso(docs);
    const marcados = await recuperarImportsOrfaos(imports as any, { deleteMany: async () => ({}) } as any,
      { deleteByPrefix: async () => {} }, silencio, 3600_000, agora);
    saida.sweep_respeita_idade = { marcados, statusFinal: Object.fromEntries(docs.map((d) => [d._id, d.status])) };
  }

  // ── limpeza falha não impede marcar ─────────────────────────────────────────
  {
    const docs = [{ _id: 'x', status: 'gravando', updatedAt: h(1) }];
    const imports = importModelFalso(docs);
    const avisos: string[] = [];
    const marcados = await recuperarImportsOrfaos(imports as any,
      { deleteMany: async () => { throw new Error('Mongo fora'); } } as any,
      { deleteByPrefix: async () => { throw new Error('disco fora'); } },
      { ...silencio, warn: (m: string) => avisos.push(m) }, 0, agora);
    saida.limpeza_falha_nao_impede = { marcados, status: docs[0].status, avisos: avisos.filter((m) => m.includes('limpeza')).length };
  }

  // ── uploads temporários: só os nossos ───────────────────────────────────────
  {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'recuperacao-'));
    const nossos = ['bim-0f8fad5b-d9cb-469f-a165-70867728950e.aq', 'cad-0f8fad5b-d9cb-469f-a165-70867728950e.stp', 'cad-0f8fad5b-d9cb-469f-a165-70867728950e.IFC'];
    const alheios = ['bim-qualquer.aq', 'cad-0f8fad5b-d9cb-469f-a165-70867728950e.txt', 'outro.aq', 'notas.txt'];
    for (const n of [...nossos, ...alheios]) fs.writeFileSync(path.join(dir, n), 'x');
    const removidos = await limparUploadsTemporarios(dir, silencio);
    const restantes = fs.readdirSync(dir).sort();
    fs.rmSync(dir, { recursive: true, force: true });
    saida.uploads_temporarios = { removidos: removidos.sort(), restantes };
    saida.uploads_dir_inexistente = await limparUploadsTemporarios(path.join(dir, 'nao-existe'), silencio);
  }

  // ── o serviço Nest existe e chama os dois no onModuleInit ───────────────────
  {
    const imports = importModelFalso([{ _id: 'y', status: 'recebido', updatedAt: new Date() }]);
    const svc = new RecuperacaoService(imports as any, { deleteMany: async () => ({}) } as any, { deleteByPrefix: async () => {} } as any);
    (svc as any).logger = silencio;
    const r = await svc.onModuleInit();
    saida.servico_on_module_init = { marcados: r.marcados, uploadsRemovidosEhArray: Array.isArray(r.uploadsRemovidos), erroConstante: ERRO_REINICIO };
  }

  process.stdout.write(JSON.stringify(saida));
}

main().catch((e) => { console.error(e); process.exit(1); });
