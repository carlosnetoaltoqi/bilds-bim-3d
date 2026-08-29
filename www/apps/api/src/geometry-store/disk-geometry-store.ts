import * as fs from 'fs/promises';
import * as path from 'path';
import { IGeometryStore } from './geometry-store.interface';

export class DiskGeometryStore implements IGeometryStore {
  private readonly baseDir: string;

  constructor() {
    this.baseDir = process.env.STORAGE_PATH ?? path.join(process.cwd(), 'storage');
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
  }
}
