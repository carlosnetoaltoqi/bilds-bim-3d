import * as fs from 'fs/promises';
import * as path from 'path';
import { AssetStat, IGeometryStore } from './geometry-store.interface';
import { storagePath } from '../storage-path';

export class DiskGeometryStore implements IGeometryStore {
  private readonly baseDir: string;

  constructor() {
    this.baseDir = storagePath();
  }

  private validateKey(key: string): void {
    const resolved = path.resolve(this.baseDir, key);
    if (!resolved.startsWith(this.baseDir + path.sep)) {
      throw Object.assign(new Error(`Key escapes storage root: ${key}`), { code: 'ETRAVERSAL' });
    }
  }

  async put(key: string, data: Buffer): Promise<void> {
    this.validateKey(key);
    const filePath = path.join(this.baseDir, key);
    await fs.mkdir(path.dirname(filePath), { recursive: true });
    await fs.writeFile(filePath, data);
  }

  async get(key: string): Promise<Buffer> {
    this.validateKey(key);
    const filePath = path.join(this.baseDir, key);
    return fs.readFile(filePath);
  }

  async stat(key: string): Promise<AssetStat> {
    this.validateKey(key);
    const filePath = path.join(this.baseDir, key);
    const stat = await fs.stat(filePath);
    return { size: stat.size, mtimeMs: stat.mtimeMs };
  }

  async delete(key: string): Promise<void> {
    this.validateKey(key);
    const filePath = path.join(this.baseDir, key);
    await fs.unlink(filePath);
  }

  async deleteByPrefix(prefix: string): Promise<void> {
    this.validateKey(prefix + '/placeholder');
    let entries: import('fs').Dirent[];
    try {
      entries = await fs.readdir(this.baseDir, { recursive: true, withFileTypes: true }) as import('fs').Dirent[];
    } catch (err: any) {
      if (err.code === 'ENOENT') return;
      throw err;
    }
    const toDelete = entries
      .filter((e) => e.isFile())
      .map((e) => path.relative(this.baseDir, path.join(e.parentPath ?? (e as any).path, e.name)))
      .filter((rel) => rel === prefix || rel.startsWith(prefix + '/'));
    await Promise.all(
      toDelete.map((rel) =>
        fs.unlink(path.join(this.baseDir, rel)).catch((err: any) => {
          if (err.code !== 'ENOENT') throw err;
        }),
      ),
    );
    // o diretório do prefixo (geo/<importId>, thumbs/<importId>) não fica vazio para trás
    await fs.rm(path.join(this.baseDir, prefix), { recursive: true, force: true }).catch(() => undefined);
  }
}
