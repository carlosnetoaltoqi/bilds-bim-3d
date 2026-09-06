/**
 * Harness de remocao.ts (@bim/dominio): apagar produto, catálogo, empresa e importação com modelos e
 * store falsos em memória. Imprime JSON para tests/test_www_remocao.py.
 *
 *   cd servicos/catalogo-api && node --require ts-node/register/transpile-only --require reflect-metadata \
 *       ../../../tests/paridade/remocao.cts
 */
import { apagarCatalogo, apagarEmpresa, apagarImportacao, apagarProduto, ImportacaoEmAndamento, NaoEncontrado } from '../../pacotes/dominio/src/remocao';

type Doc = Record<string, any>;

function casa(doc: Doc, filtro: Doc): boolean {
  return Object.entries(filtro).every(([k, v]) => {
    if (v && typeof v === 'object' && '$ne' in v) return doc[k] !== v.$ne;
    return doc[k] === v;
  });
}

function modelo(docs: Doc[]) {
  const q = (calc: () => any) => { const c: any = { exec: async () => calc(), lean: () => c, select: () => c }; return c; };
  return {
    docs,
    findById: (id: string) => q(() => docs.find((d) => d._id === id) ?? null),
    findOne: (f: Doc) => q(() => docs.find((d) => casa(d, f)) ?? null),
    find: (f: Doc) => Object.assign(q(() => docs.filter((d) => casa(d, f))), { distinct: (campo: string) => ({ exec: async () => [...new Set(docs.filter((d) => casa(d, f)).map((d) => d[campo]))] }) }),
    countDocuments: (f: Doc) => ({ exec: async () => docs.filter((d) => casa(d, f)).length }),
    deleteOne: (f: Doc) => ({ exec: async () => { const i = docs.findIndex((d) => casa(d, f)); if (i >= 0) docs.splice(i, 1); return {}; } }),
    deleteMany: (f: Doc) => ({ exec: async () => { const antes = docs.length; for (let i = docs.length - 1; i >= 0; i--) if (casa(docs[i], f)) docs.splice(i, 1); return { deletedCount: antes - docs.length }; } }),
    updateOne: (f: Doc, upd: Doc) => ({ exec: async () => { const d = docs.find((x) => casa(x, f)); if (d) Object.assign(d, upd.$set ?? upd); return {}; } }),
  };
}

function store(chaves: string[]) {
  const arquivos = new Set(chaves);
  const enoent = () => Object.assign(new Error('ENOENT'), { code: 'ENOENT' });
  return {
    arquivos,
    put: async (k: string) => { arquivos.add(k); },
    get: async (k: string) => { if (!arquivos.has(k)) throw enoent(); return Buffer.alloc(0); },
    stat: async (k: string) => { if (!arquivos.has(k)) throw enoent(); return { size: 0, mtimeMs: 0 }; },
    delete: async (k: string) => { if (!arquivos.has(k)) throw enoent(); arquivos.delete(k); },
    deleteByPrefix: async (p: string) => { for (const k of [...arquivos]) if (k === p || k.startsWith(p + '/')) arquivos.delete(k); },
  };
}

/** Uma empresa com dois catálogos: um do pipeline (geometria compartilhada) e um CAD; três imports. */
function cenario() {
  const companies = modelo([{ _id: 'emp', customUrl: 'poc', logoKey: 'logos/emp.png' }]);
  const catalogs = modelo([
    { _id: 'cat1', companyId: 'emp', slug: 'esgoto', productCount: 3, filters: ['Joelhos', 'Luvas'] },
    { _id: 'cat2', companyId: 'emp', slug: 'pecas-step', productCount: 1, filters: ['STEP'] },
  ]);
  const products = modelo([
    // p1 e p2 compartilham a geometria g; p3 tem a própria (copy-on-write de g) e a exclusiva h ninguém
    { _id: 'p1', catalogId: 'cat1', importId: 'imp1', serie: 'Joelhos', geoKey: 'geo/imp1/g.json', geoKeyCompartilhada: null, thumbKey: 'thumbs/imp1/g.webp' },
    { _id: 'p2', catalogId: 'cat1', importId: 'imp1', serie: 'Joelhos', geoKey: 'geo/imp1/g.json', geoKeyCompartilhada: null, thumbKey: 'thumbs/imp1/g.webp' },
    { _id: 'p3', catalogId: 'cat1', importId: 'imp1', serie: 'Luvas', geoKey: 'geo/imp1/h.json', geoKeyCompartilhada: null, thumbKey: 'thumbs/imp1/h.webp' },
    { _id: 'p4', catalogId: 'cat2', importId: 'imp2', serie: 'STEP', geoKey: 'geo/imp2/peca.json', geoKeyCompartilhada: null, thumbKey: 'thumbs/imp2/peca.webp' },
  ]);
  const imports = modelo([
    { _id: 'imp1', companyId: 'emp', catalogId: 'cat1', status: 'publicado' },
    { _id: 'imp2', companyId: 'emp', catalogId: 'cat2', status: 'publicado' },
    { _id: 'imp3', companyId: 'emp', catalogId: null, status: 'falhou' },
    { _id: 'imp4', companyId: 'emp', catalogId: null, status: 'parseando' },
  ]);
  const st = store([
    'geo/imp1/g.json', 'geo/imp1/h.json', 'geo/imp1/h.orig.json', 'thumbs/imp1/g.webp', 'thumbs/imp1/h.webp',
    'geo/imp2/peca.json', 'thumbs/imp2/peca.webp', 'geo/imp3/lixo.json', 'logos/emp.png',
  ]);
  return { m: { companies, catalogs, products, imports }, st };
}

const ids = (m: any) => m.docs.map((d: Doc) => d._id).sort();

async function main() {
  const saida: Record<string, unknown> = {};

  // produto que compartilha geometria: só o documento sai
  { const { m, st } = cenario(); const r = await apagarProduto(m as any, st as any, 'p1');
    saida.produto_compartilhado = { r, produtos: ids(m.products), arquivos: [...st.arquivos].sort(), catalogo: m.catalogs.docs[0] }; }
  // produto de geometria exclusiva: geometria, .orig e miniatura saem
  { const { m, st } = cenario(); const r = await apagarProduto(m as any, st as any, 'p3');
    saida.produto_exclusivo = { r, arquivos: [...st.arquivos].sort(), catalogo: m.catalogs.docs[0] }; }
  // produto com copy-on-write: a cópia sai, a compartilhada fica
  { const { m, st } = cenario(); m.products.docs[0].geoKey = 'geo/imp1/p1.json'; m.products.docs[0].geoKeyCompartilhada = 'geo/imp1/g.json'; st.arquivos.add('geo/imp1/p1.json');
    const r = await apagarProduto(m as any, st as any, 'p1'); saida.produto_cow = { r, arquivos: [...st.arquivos].sort() }; }
  // catálogo: produtos, storage dos imports e os imports
  { const { m, st } = cenario(); const r = await apagarCatalogo(m as any, st as any, 'cat1');
    saida.catalogo = { r, produtos: ids(m.products), catalogos: ids(m.catalogs), imports: ids(m.imports), arquivos: [...st.arquivos].sort() }; }
  // importação terminada: produtos, storage, documento; catálogo recontado
  { const { m, st } = cenario(); const r = await apagarImportacao(m as any, st as any, 'imp2');
    saida.importacao = { r, produtos: ids(m.products), imports: ids(m.imports), catalogo: m.catalogs.docs[1], arquivos: [...st.arquivos].sort() }; }
  // importação em andamento: recusada
  { const { m, st } = cenario(); try { await apagarImportacao(m as any, st as any, 'imp4'); saida.importacao_andamento = 'passou'; }
    catch (e: any) { saida.importacao_andamento = { tipo: e instanceof ImportacaoEmAndamento ? 'ImportacaoEmAndamento' : e.name, message: e.message, imports: ids(m.imports) }; } }
  // empresa: tudo
  { const { m, st } = cenario(); const r = await apagarEmpresa(m as any, st as any, 'emp');
    saida.empresa = { r, companies: ids(m.companies), catalogos: ids(m.catalogs), produtos: ids(m.products), imports: ids(m.imports), arquivos: [...st.arquivos] }; }
  // inexistentes
  { const { m, st } = cenario(); const erros: string[] = [];
    for (const fn of [() => apagarProduto(m as any, st as any, 'x'), () => apagarCatalogo(m as any, st as any, 'x'), () => apagarEmpresa(m as any, st as any, 'x'), () => apagarImportacao(m as any, st as any, 'x')]) {
      try { await fn(); erros.push('passou'); } catch (e: any) { erros.push(e instanceof NaoEncontrado ? 'NaoEncontrado' : e.name); } }
    saida.inexistentes = erros; }

  process.stdout.write(JSON.stringify(saida));
}
main().catch((e) => { console.error(e); process.exit(1); });
