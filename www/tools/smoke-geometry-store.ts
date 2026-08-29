import * as path from 'path';
import * as fs from 'fs/promises';
import { DiskGeometryStore } from '../apps/api/src/geometry-store/disk-geometry-store';

// Usa subdiretório dedicado para não sujar o storage de produção
process.env.STORAGE_PATH = path.join(process.cwd(), 'storage', 'smoke-test');

async function run() {
  const store = new DiskGeometryStore();

  // Happy path: put → get → conteúdo idêntico
  const key1 = 'geo/import1/piece.json';
  const data = Buffer.from('{"test":true}', 'utf8');
  await store.put(key1, data);
  const got = await store.get(key1);
  if (!got.equals(data)) throw new Error('get: conteúdo diferente do put');

  // delete: arquivo não existe mais
  await store.delete(key1);
  try {
    await store.get(key1);
    throw new Error('delete: arquivo ainda existe');
  } catch (err: any) {
    if (err.code !== 'ENOENT') throw err;
  }

  // deleteByPrefix: remove só arquivos do prefixo
  await store.put('geo/import1/a.bin', Buffer.from('a'));
  await store.put('geo/import1/b.bin', Buffer.from('b'));
  await store.put('geo/import2/c.bin', Buffer.from('c'));
  await store.deleteByPrefix('geo/import1');
  try {
    await store.get('geo/import1/a.bin');
    throw new Error('deleteByPrefix: a.bin ainda existe');
  } catch (err: any) {
    if (err.code !== 'ENOENT') throw err;
  }
  // import2/c.bin deve continuar intacto
  const cBuf = await store.get('geo/import2/c.bin');
  if (cBuf.toString() !== 'c') throw new Error('deleteByPrefix: apagou arquivo de outro prefixo');

  // put com subdiretório criado automaticamente (não existia antes)
  await store.put('nested/deep/file.bin', Buffer.from('deep'));
  const deepBuf = await store.get('nested/deep/file.bin');
  if (deepBuf.toString() !== 'deep') throw new Error('put aninhado: conteúdo incorreto');

  // Limpeza do diretório de smoke test
  await fs.rm(process.env.STORAGE_PATH as string, { recursive: true, force: true });

  console.log('OK');
}

run().catch((err) => {
  console.error('FALHOU:', err.message);
  process.exit(1);
});
