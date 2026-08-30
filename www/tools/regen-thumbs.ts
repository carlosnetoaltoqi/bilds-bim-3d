/**
 * regen-thumbs.ts — S4.3
 *
 * Regenera as miniaturas WebP de um import específico (ou do mais recente
 * catálogo Dancor ativo no Atlas) usando o rasterizador atualizado (com
 * supersampling 2×). Sobrescreve os arquivos existentes sem alterar o banco —
 * o thumbKey já está correto.
 *
 * Uso:
 *   pnpm --filter api exec node --require ts-node/register \
 *     --require reflect-metadata ../../tools/regen-thumbs.ts [importId]
 */

import * as fs from 'node:fs/promises';
import * as path from 'node:path';
import * as dotenv from 'dotenv';
import { MongoClient, ObjectId } from 'mongodb';
import { renderThumbTs } from './thumb-rasterizer';

// Carrega .env do diretório www/
dotenv.config({ path: path.resolve(__dirname, '../.env') });

const MONGODB_URI = process.env.MONGODB_URI!;
const MONGODB_DB = process.env.MONGODB_DB ?? 'bilds-bim-3d';
const STORAGE_PATH = path.resolve(
  path.dirname(__filename),
  '../apps/api',
  process.env.STORAGE_PATH ?? '../../storage/bim',
);

async function main() {
  if (!MONGODB_URI) throw new Error('MONGODB_URI não definido em .env');

  const targetImportId = process.argv[2] ?? null;

  const client = new MongoClient(MONGODB_URI);
  await client.connect();
  const db = client.db(MONGODB_DB);

  let importId: string;
  let products: Array<{ _id: string; geoKey: string; thumbKey: string | null }>;

  if (targetImportId) {
    importId = targetImportId;
    console.log(`Usando importId fornecido: ${importId}`);
  } else {
    // Busca o catálogo Dancor mais recente no Atlas
    const catalog = await db
      .collection('bim_catalogs')
      .findOne({}, { sort: { _id: -1 } });
    if (!catalog) throw new Error('Nenhum catálogo encontrado no Atlas');
    console.log(`Catálogo: ${catalog.title} (${catalog._id})`);

    // Pega qualquer produto para descobrir o importId
    const sample = await db
      .collection('bim_products')
      .findOne({ catalogId: catalog._id });
    if (!sample) throw new Error('Nenhum produto encontrado');
    importId = sample.importId as string;
    console.log(`ImportId descoberto: ${importId}`);
  }

  products = await db
    .collection<{ _id: string; geoKey: string; thumbKey: string | null }>('bim_products')
    .find({ importId })
    .project({ _id: 1, geoKey: 1, thumbKey: 1 })
    .toArray() as any;

  console.log(`Produtos encontrados: ${products.length}`);

  let ok = 0;
  let fail = 0;
  const t0 = Date.now();

  for (const product of products) {
    const productId = product._id as string;
    const geoKey = product.geoKey as string;

    if (!geoKey) {
      console.warn(`  [skip] ${productId} — sem geoKey`);
      continue;
    }

    const geoPath = path.join(STORAGE_PATH, geoKey);

    try {
      const raw = await fs.readFile(geoPath, 'utf8');
      const geoData = JSON.parse(raw);

      const t1 = Date.now();
      const webpBuf = await renderThumbTs(geoData);
      const elapsed = Date.now() - t1;

      // Determina o thumbKey: usa o existente ou cria no padrão
      const thumbKey = (product.thumbKey as string | null)
        ?? `thumbs/${importId}/${productId}.webp`;
      const thumbPath = path.join(STORAGE_PATH, thumbKey);

      await fs.mkdir(path.dirname(thumbPath), { recursive: true });
      await fs.writeFile(thumbPath, webpBuf);

      // Atualiza thumbKey no banco se estava null
      if (!product.thumbKey) {
        await db.collection('bim_products').updateOne(
          { _id: productId as any },
          { $set: { thumbKey } },
        );
        console.log(`  [ok] ${productId} — ${webpBuf.length} bytes (${elapsed}ms) [thumbKey novo]`);
      } else {
        console.log(`  [ok] ${productId} — ${webpBuf.length} bytes (${elapsed}ms)`);
      }

      ok++;
    } catch (err: any) {
      console.error(`  [err] ${productId} — ${err.message}`);
      fail++;
    }
  }

  await client.close();

  const totalMs = Date.now() - t0;
  console.log(`\nConcluído: ${ok} ok, ${fail} erros em ${(totalMs / 1000).toFixed(1)}s`);
  if (ok > 0) {
    console.log(`Média: ${(totalMs / ok).toFixed(0)} ms/thumb`);
  }
}

main().catch((err) => {
  console.error('FATAL:', err);
  process.exit(1);
});
