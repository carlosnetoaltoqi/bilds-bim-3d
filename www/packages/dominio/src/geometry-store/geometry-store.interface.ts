export interface AssetStat {
  size: number;
  mtimeMs: number;
}

export interface IGeometryStore {
  put(key: string, data: Buffer): Promise<void>;
  get(key: string): Promise<Buffer>;
  /**
   * Metadados do blob sem ler os bytes — usado para montar a ETag e responder 304
   * antes de tocar no arquivo. Lança `ENOENT` quando a chave não existe, igual ao `get`.
   */
  stat(key: string): Promise<AssetStat>;
  delete(key: string): Promise<void>;
  deleteByPrefix(prefix: string): Promise<void>;
}
