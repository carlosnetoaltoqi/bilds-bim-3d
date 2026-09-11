/**
 * Harness da saída pós-falha de uma importação de plugin: **apagar o que ficou pela metade** e
 * **retomar** (`importacoes.service.ts`), com modelos falsos e um `STORAGE_PATH` de verdade.
 *
 * O que se protege aqui: o cache de download sobrevive à falha de propósito (é o ativo caro —
 * rede lenta e um formulário de lead por arquivo), então apagá-lo só pode acontecer quando quem
 * importa manda, e **nunca** por baixo de outra importação que ainda o está usando.
 *
 *   cd servicos/criador-de-catalogos && node --require ts-node/register/transpile-only --require reflect-metadata \
 *       ../../tests/paridade/retomada.cts
 */
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

const raiz = fs.mkdtempSync(path.join(os.tmpdir(), 'retomada-'));
process.env.STORAGE_PATH = raiz;

import { ImportacoesService, pastaDeDownloads } from '../../servicos/criador-de-catalogos/src/importacoes/importacoes.service';

const ORIGEM = { host: 'https://catalogo.exemplo.com', categoria: 'conexoes-17', igsPorGrupo: 1, deflexao: 0.2, disciplina: 'hidraulico' };
const PASTA = pastaDeDownloads(ORIGEM.host, ORIGEM.categoria);

function semearCache(arquivos: number, bytes: number) {
  const dir = path.join(raiz, 'catallog', PASTA);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'manifesto.json'), JSON.stringify({
    host: ORIGEM.host,
    arquivos: Array.from({ length: arquivos }, (_, i) => ({ arquivo: `p${i}.igs`, tamanho: bytes / arquivos })),
  }));
  return dir;
}

function modelos(docs: any[]) {
  return {
    imports: {
      findById: (id: string) => ({ lean: () => ({ exec: async () => docs.find((d) => d._id === id) ?? null }) }),
      countDocuments: (filtro: any) => ({
        exec: async () => docs.filter((d) =>
          d._id !== filtro._id.$ne && filtro.status.$in.includes(d.status)
          && d.origem?.host === filtro['origem.host'] && d.origem?.categoria === filtro['origem.categoria']).length,
      }),
      deleteOne: () => ({ exec: async () => ({ deletedCount: 1 }) }),
      find: () => ({ lean: () => ({ exec: async () => [] }) }),
    },
    vazio: {
      find: () => ({ lean: () => ({ exec: async () => [] }) }),
      findById: () => ({ lean: () => ({ exec: async () => null }), select: () => ({ lean: () => ({ exec: async () => null }) }) }),
      deleteMany: () => ({ exec: async () => ({ deletedCount: 0 }) }),
      countDocuments: () => ({ exec: async () => 0 }),
      findOne: () => ({ lean: () => ({ exec: async () => null }) }),
      updateOne: () => ({ exec: async () => ({}) }),
    },
  };
}

function servico(docs: any[]) {
  const m = modelos(docs);
  const store = { deleteByPrefix: async () => {}, delete: async () => {}, put: async () => {}, get: async () => null } as any;
  return new (ImportacoesService as any)(m.imports, m.vazio, m.vazio, m.vazio, store, { executar: async () => {} }, {}, {});
}

const saida: Record<string, unknown> = {};

async function main() {

  // a pasta é estável e segura: mesmo par (host, categoria) → mesmo nome; acento e barra somem
  saida.pasta = {
    igual: pastaDeDownloads(ORIGEM.host, ORIGEM.categoria) === PASTA,
    nome: pastaDeDownloads('https://Catálogo.Exemplo.com/', 'Conexões Ranhuradas 17'),
    categoriasDiferentes: pastaDeDownloads(ORIGEM.host, 'a-1') !== pastaDeDownloads(ORIGEM.host, 'a-2'),
  };

  // apagar uma importação falhada leva o cache junto
  {
    const dir = semearCache(41, 214_000_000);
    const docs = [{ _id: 'i1', status: 'falhou', tipo: 'plugin', origem: ORIGEM, companyId: 'c1' }];
    const r = await servico(docs).apagar('i1');
    saida.apagouCache = { removidos: r.downloadsRemovidos, pastaSumiu: !fs.existsSync(dir) };
  }

  // mas NÃO quando outra importação da mesma origem ainda está viva
  {
    const dir = semearCache(41, 214_000_000);
    const docs = [
      { _id: 'i1', status: 'falhou', tipo: 'plugin', origem: ORIGEM, companyId: 'c1' },
      { _id: 'i2', status: 'parseando', tipo: 'plugin', origem: ORIGEM, companyId: 'c1' },
    ];
    const r = await servico(docs).apagar('i1');
    saida.preservouCacheEmUso = { removidos: r.downloadsRemovidos, pastaFicou: fs.existsSync(dir) };
  }

  // retomar só vale para plugin com origem, e não enquanto a importação está em andamento
  {
    const lead = { fullName: 'A', email: 'a@b.c', mobile: '1', company: 'X', position: 'Y' };
    const tentar = async (docs: any[], id: string) => {
      try { await servico(docs).retomar(id, lead as any); return 'ok'; } catch (e: any) { return e?.name ?? String(e?.message ?? e); }
    };
    saida.retomarAq = await tentar([{ _id: 'i9', status: 'falhou', tipo: 'aq', origem: null }], 'i9');
    saida.retomarEmAndamento = await tentar([{ _id: 'i8', status: 'parseando', tipo: 'plugin', origem: ORIGEM }], 'i8');
  }

  process.stdout.write(JSON.stringify(saida));
}

main().catch((e) => { console.error(e); process.exit(1); });
