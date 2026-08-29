import * as fs from 'fs/promises';
import * as path from 'path';
import { IGeometryStore } from './geometry-store.interface';

export class DiskGeometryStore implements IGeometryStore {
  private readonly baseDir: string;

  constructor() {
    this.baseDir = process.env.STORAGE_PATH ?? path.join(process.cwd(), 'storage');
  }

  async put(key: string, data: Buffer): Promise<void> {
    const filePath = path.join(this.baseDir, key);
    await fs.mkdir(path.dirname(filePath), { recursive: true });
    await fs.writeFile(filePath, data);
  }

  async get(key: string): Promise<Buffer> {
    const filePath = path.join(this.baseDir, key);
    return fs.readFile(filePath);
  }

  async delete(key: string): Promise<void> {
    const filePath = path.join(this.baseDir, key);
    await fs.unlink(filePath);
  }

  async deleteByPrefix(prefix: string): Promise<void> {
    const entries = await fs.readdir(this.baseDir, { recursive: true });
    const toDelete = (entries as string[]).filter((e) => e.startsWith(prefix));
    await Promise.all(
      toDelete.map((e) => fs.unlink(path.join(this.baseDir, e)).catch(() => undefined)),
    );
  }
}
