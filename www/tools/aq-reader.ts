/**
 * aq-reader.ts — Port TypeScript de www/apps/ingestao/pipeline/read_aq.py (S2.2)
 *
 * Abre um .aq do AltoQi Builder (SQLite direto ou ZIP contendo SQLite)
 * e extrai dados de produto e geometria.
 *
 * Encoding: o .aq grava texto em Windows-1252 (cp1252) — não UTF-8.
 * Solução: CAST(col AS BLOB) em toda coluna de texto + TextDecoder('windows-1252').
 * O TextDecoder não lança exceção nos 5 bytes indefinidos do cp1252
 * (0x81, 0x8D, 0x8F, 0x90, 0x9D) — comportamento mais robusto que o
 * fallback latin-1 do Python.
 *
 * Limitação desta versão (spike S2.2): ZIP não é suportado.
 * A Dancor é SQLite direto; ZIP seria necessário para outros fabricantes.
 */

import { DatabaseSync } from 'node:sqlite';
import * as path from 'node:path';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as zlib from 'node:zlib';

const decoder = new TextDecoder('windows-1252');

function decodeText(bytes: Uint8Array | null | undefined): string {
  if (!bytes) return '';
  return decoder.decode(bytes);
}

function openSQLite(filePath: string): DatabaseSync {
  // Validate: try SELECT from a known table
  const db = new DatabaseSync(filePath);
  db.prepare('SELECT 1 FROM GRUPO_PECA LIMIT 1').get();
  return db;
}

/**
 * Extrai o SQLite de dentro de um ZIP de .aq usando zlib (deflate).
 * Suporta o caso comum: um único arquivo SQLite dentro do ZIP.
 * Lança Error se o formato não for reconhecido.
 */
function extractSQLiteFromZip(zipBuf: Buffer): Buffer {
  // ZIP Local File Header: PK\x03\x04 (0x04034b50 LE)
  const SIG_LOCAL = 0x04034b50;
  const SIG_END = 0x06054b50;
  let offset = 0;

  while (offset + 30 <= zipBuf.length) {
    const sig = zipBuf.readUInt32LE(offset);
    if (sig === SIG_END) break;
    if (sig !== SIG_LOCAL) {
      offset++;
      continue;
    }

    const compression = zipBuf.readUInt16LE(offset + 8); // 0=store, 8=deflate
    const compressedSize = zipBuf.readUInt32LE(offset + 18);
    const fileNameLen = zipBuf.readUInt16LE(offset + 26);
    const extraLen = zipBuf.readUInt16LE(offset + 28);
    const dataOffset = offset + 30 + fileNameLen + extraLen;
    const fileName = zipBuf.toString('utf8', offset + 30, offset + 30 + fileNameLen);

    if (!fileName.endsWith('.xml') && compressedSize > 0) {
      const compressed = zipBuf.slice(dataOffset, dataOffset + compressedSize);
      const data = compression === 8 ? zlib.inflateRawSync(compressed) : compressed;
      return data;
    }

    offset = dataOffset + compressedSize;
  }

  throw new Error('Nenhum SQLite encontrado dentro do ZIP do .aq');
}

interface OpenAqResult {
  db: DatabaseSync;
  cleanup: (() => void) | null;
}

function openAq(aqPath: string): OpenAqResult {
  // Tentativa 1: SQLite direto
  try {
    const db = openSQLite(aqPath);
    return { db, cleanup: null };
  } catch {
    // cai para ZIP
  }

  // Tentativa 2: ZIP contendo SQLite
  const raw = fs.readFileSync(aqPath);
  if (raw[0] !== 0x50 || raw[1] !== 0x4b) {
    throw new Error(`${aqPath} não é SQLite válido nem ZIP (PK)`);
  }

  const sqliteData = extractSQLiteFromZip(raw);
  const tmpPath = path.join(os.tmpdir(), `aq_${Date.now()}_${Math.random().toString(36).slice(2)}.db`);
  fs.writeFileSync(tmpPath, sqliteData);

  const db = new DatabaseSync(tmpPath);
  return {
    db,
    cleanup: () => {
      try { db.close(); } catch { /* ignore */ }
      try { fs.unlinkSync(tmpPath); } catch { /* ignore */ }
    },
  };
}

// ─── Tipos de saída ──────────────────────────────────────────────────────────

export interface AqGrupo {
  ID_GRUPO_PECA: number;
  NOME_GP: string;
  ATIVO: number;
}

export interface AqPeca {
  ID_PECA: number;
  ID_GRUPO_PECA: number;
  NOME_PECA: string;
  DESCRICAO_DADOS: string;
  DIAMETRO_PECA: number | null;
  COMPRIMENTO_PECA: number | null;
  ALTURA_PECA: number | null;
  LARGURA_PECA: number | null;
}

export interface AqCurvaPonto {
  ID_PECA: number;
  potencia_cv: number | null;
  VAZAO_ICB: number;
  ALTURA_ICB: number;
  POTENCIA_ICB: number | null;
  RENDIMENTO_ICB: number | null;
}

export interface AqPropriedade {
  ID_PECA: number;
  propriedade: string;
  VALOR: string;
}

export interface AqData {
  grupos: AqGrupo[];
  pecas: AqPeca[];
  curvas: AqCurvaPonto[];
  propriedades: AqPropriedade[];
}

export interface AqSimbologia {
  nome: string;
  blob: Buffer; // CAST(SIMBOLOGIA_3D AS BLOB)
  imagem: Buffer | null;
  grupo: string;
  classe: string;
}

export interface AqSimboloiasResult {
  simbologias: Map<number, AqSimbologia>;
  porPeca: Map<number, number>; // id_peca → id_simbologia_3d
}

// ─── extract() — equivalente de read_aq.extract() ────────────────────────────

export function extract(aqPath: string): AqData {
  const { db, cleanup } = openAq(aqPath);

  try {
    const grupos: AqGrupo[] = db
      .prepare(
        'SELECT ID_GRUPO_PECA, CAST(NOME_GP AS BLOB) AS nome_blob, ATIVO ' +
        'FROM GRUPO_PECA WHERE ATIVO = 1 ORDER BY ID_GRUPO_PECA',
      )
      .all()
      .map((r: any) => ({
        ID_GRUPO_PECA: r.ID_GRUPO_PECA,
        NOME_GP: decodeText(r.nome_blob),
        ATIVO: r.ATIVO,
      }));

    const pecas: AqPeca[] = db
      .prepare(
        'SELECT ID_PECA, ID_GRUPO_PECA, ' +
        'CAST(NOME_PECA AS BLOB) AS nome_blob, ' +
        'CAST(DESCRICAO_DADOS AS BLOB) AS desc_blob, ' +
        'DIAMETRO_PECA, COMPRIMENTO_PECA, ALTURA_PECA, LARGURA_PECA ' +
        'FROM PECA WHERE ATIVO = 1 ORDER BY ID_GRUPO_PECA, ID_PECA',
      )
      .all()
      .map((r: any) => ({
        ID_PECA: r.ID_PECA,
        ID_GRUPO_PECA: r.ID_GRUPO_PECA,
        NOME_PECA: decodeText(r.nome_blob),
        DESCRICAO_DADOS: decodeText(r.desc_blob),
        DIAMETRO_PECA: r.DIAMETRO_PECA ?? null,
        COMPRIMENTO_PECA: r.COMPRIMENTO_PECA ?? null,
        ALTURA_PECA: r.ALTURA_PECA ?? null,
        LARGURA_PECA: r.LARGURA_PECA ?? null,
      }));

    let curvas: AqCurvaPonto[] = [];
    try {
      curvas = db
        .prepare(
          'SELECT p.ID_PECA, mb.POTENCIA_MB AS potencia_cv, ' +
          'icb.VAZAO_ICB, icb.ALTURA_ICB, icb.POTENCIA_ICB, icb.RENDIMENTO_ICB ' +
          'FROM PECA p ' +
          'JOIN GRUPO_PECA gp ON gp.ID_GRUPO_PECA = p.ID_GRUPO_PECA ' +
          'JOIN DADOS_HIDRAULICOS dh ON dh.ID_PECA = p.ID_PECA ' +
          'JOIN MODELO_BOMBA mb ON mb.ID_MODELO_BOMBA = dh.ID_MODELO_BOMBA ' +
          'JOIN ITEM_CURVA_BOMBA icb ON icb.ID_MODELO_BOMBA = mb.ID_MODELO_BOMBA ' +
          'WHERE p.ATIVO = 1 ' +
          'ORDER BY p.ID_PECA, icb.VAZAO_ICB',
        )
        .all()
        .map((r: any): AqCurvaPonto => ({
          ID_PECA: r.ID_PECA,
          potencia_cv: r.potencia_cv ?? null,
          VAZAO_ICB: r.VAZAO_ICB,
          ALTURA_ICB: r.ALTURA_ICB,
          POTENCIA_ICB: r.POTENCIA_ICB ?? null,
          RENDIMENTO_ICB: r.RENDIMENTO_ICB ?? null,
        }));
    } catch {
      // Tabelas de bomba ausentes em bibliotecas não-hidráulicas
    }

    let propriedades: AqPropriedade[] = [];
    try {
      propriedades = db
        .prepare(
          'SELECT p.ID_PECA, ' +
          'CAST(prop.NOME AS BLOB) AS prop_nome, ' +
          'CAST(vprop.VALOR AS BLOB) AS valor_blob ' +
          'FROM VALOR_PROPRIEDADE_PERSONALIZADA vprop ' +
          'JOIN PROPRIEDADE_PERSONALIZADA prop ' +
          '  ON prop.ID_PROPRIEDADE_PERSONALIZADA = vprop.ID_PROPRIEDADE_PERSONALIZADA ' +
          'JOIN GRUPO_PROPRIEDADE_PERSONALIZADA gprop ' +
          '  ON gprop.ID_GRUPO_PROPRIEDADE_PERSONALIZADA = prop.ID_GRUPO_PROPRIEDADE_PERSONALIZADA ' +
          'JOIN PECA p ON p.ID_PECA = vprop.ID_PECA ' +
          'ORDER BY p.ID_PECA, prop.NOME',
        )
        .all()
        .map((r: any) => ({
          ID_PECA: r.ID_PECA,
          propriedade: decodeText(r.prop_nome),
          VALOR: decodeText(r.valor_blob),
        }));
    } catch {
      // Tabelas de propriedades ausentes em algumas bibliotecas
    }

    return { grupos, pecas, curvas, propriedades };
  } finally {
    if (!cleanup) db.close();
    else cleanup();
  }
}

// ─── extractSimboloias() — equivalente de read_aq.extract_simbologias() ──────

export function extractSimboloias(aqPath: string): AqSimboloiasResult {
  const { db, cleanup } = openAq(aqPath);

  try {
    const simbologias = new Map<number, AqSimbologia>();

    let rows: any[];
    try {
      rows = db
        .prepare(
          'SELECT s.ID_SIMBOLOGIA_3D, ' +
          'CAST(s.NOME AS BLOB) AS nome_blob, ' +
          'CAST(s.SIMBOLOGIA_3D AS BLOB) AS blob_data, ' +
          'CAST(s.IMAGEM AS BLOB) AS img_data, ' +
          'CAST(g.NOME_GRUPO AS BLOB) AS grupo_blob, ' +
          'CAST(c.NOME_CLASSE AS BLOB) AS classe_blob ' +
          'FROM SIMBOLOGIA_3D s ' +
          'LEFT JOIN GRUPO_SIMBOLOGIA_3D g ' +
          '  ON g.ID_GRUPO_SIMBOLOGIA_3D = s.ID_GRUPO_SIMBOLOGIA_3D ' +
          'LEFT JOIN CLASSE_SIMBOLOGIA_3D c ' +
          '  ON c.ID_CLASSE_SIMBOLOGIA_3D = g.ID_CLASSE',
        )
        .all();
    } catch {
      rows = db
        .prepare(
          'SELECT ID_SIMBOLOGIA_3D, ' +
          'CAST(NOME AS BLOB) AS nome_blob, ' +
          'CAST(SIMBOLOGIA_3D AS BLOB) AS blob_data, ' +
          'CAST(IMAGEM AS BLOB) AS img_data, ' +
          'NULL AS grupo_blob, NULL AS classe_blob ' +
          'FROM SIMBOLOGIA_3D',
        )
        .all();
    }

    for (const r of rows as any[]) {
      simbologias.set(r.ID_SIMBOLOGIA_3D, {
        nome: decodeText(r.nome_blob),
        blob: Buffer.from(r.blob_data as Uint8Array),
        imagem: r.img_data ? Buffer.from(r.img_data as Uint8Array) : null,
        grupo: decodeText(r.grupo_blob),
        classe: decodeText(r.classe_blob),
      });
    }

    const porPeca = new Map<number, number>();
    try {
      const links = db.prepare('SELECT ID_PECA, ID_SIMBOLOGIA_3D FROM PECA_SIMBOLOGIA_3D').all();
      for (const row of links as any[]) {
        porPeca.set(row.ID_PECA, row.ID_SIMBOLOGIA_3D);
      }
    } catch {
      // PECA_SIMBOLOGIA_3D ausente em schemas antigos
    }

    return { simbologias, porPeca };
  } finally {
    if (!cleanup) db.close();
    else cleanup();
  }
}
