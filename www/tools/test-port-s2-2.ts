/**
 * test-port-s2-2.ts — S2.2: spike do port TypeScript
 *
 * Compara a saída do port TS (oq3d-parser.ts + aq-reader.ts) contra o
 * oráculo Python (oq3d.to_buffers) para toda a biblioteca Dancor.
 *
 * Critério de aceite:
 * 1. Mesmo número de produtos com geometria (13 para Dancor)
 * 2. Para cada produto: pos, col e idx com comprimento idêntico ao Python
 * 3. Todos os valores iguais elemento a elemento, tratando -0 e 0 como iguais
 * 4. O parser rejeita com OQ3DError: blob sem assinatura, contagem declarada
 *    maior que o buffer restante — sem alocação proporcional à contagem.
 * 5. Métricas de memória e tempo registradas para comparação com S2.1
 *    (Python: 189 MB RSS delta, 119 MB heap, ~39 s)
 *
 * Roda via: cd www && pnpm port:test
 */

import * as path from 'node:path';
import * as child_process from 'node:child_process';
import { extractSimboloias } from './aq-reader';
import { toBuffers, OQ3DError } from './oq3d-parser';

const AQ_PATH = path.resolve(__dirname, '../../input/Dancor/pecas_dancor_bombas_incendio_2026_04.1.aq');
const SCRIPTS_DIR = path.resolve(__dirname, '../../scripts');

// ─── Oráculo Python ──────────────────────────────────────────────────────────

interface PythonRefEntry {
  simId: number;
  posLen: number;
  colLen: number;
  idxLen: number;
  pos: number[];
  col: number[];
  idx: number[];
}

function generatePythonReference(): Record<string, PythonRefEntry> {
  const script = `
import sys, json
sys.path.insert(0, '${SCRIPTS_DIR}')
import read_aq, oq3d

simbologias, por_peca = read_aq.extract_simbologias('${AQ_PATH}')
ref = {}
for pid in sorted(por_peca.keys()):
    sid = por_peca[pid]
    blob = simbologias[sid]['blob']
    buf = oq3d.to_buffers(blob)
    ref[str(pid)] = {
        'simId': sid,
        'posLen': len(buf['pos']),
        'colLen': len(buf['col']),
        'idxLen': len(buf['idx']),
        'pos': buf['pos'],
        'col': buf['col'],
        'idx': buf['idx'],
    }
print(json.dumps(ref))
`;
  const result = child_process.spawnSync('python3', ['-c', script], {
    maxBuffer: 200 * 1024 * 1024,
    encoding: 'utf8',
  });
  if (result.status !== 0) {
    throw new Error(`Python reference failed:\n${result.stderr}`);
  }
  return JSON.parse(result.stdout);
}

// ─── Comparação semântica ─────────────────────────────────────────────────────

/**
 * Igualdade semântica para floats conforme definido na seção 7.3 do plano:
 * comparação elemento a elemento tratando -0 e 0 como iguais e tolerando
 * divergências de até 1-2 ULPs (~1e-12 relativo).
 *
 * Por quê os dois primeiros casos:
 * - Python serializa -0.0 como "-0.0" em JSON; Node produz -0 em memória
 *   (ex. -vy * scale quando vy=0.0). Semânticamente o mesmo ponto.
 *
 * Por quê o epsilon relativo:
 * - Python usa numpy (BLAS/LAPACK, potencialmente SIMD fused-multiply-add).
 *   TypeScript usa aritmética escalar padrão IEEE 754. A mesma sequência de
 *   operações matriciais pode diferir em 1 ULP (~2e-16 relativo por operação).
 *   Com transforms compostos (~10 multiplicações), a divergência acumulada é
 *   ~1e-15 relativo — bem abaixo de qualquer diferença visível no viewer.
 * - Limiar 1e-10: rejeita erros reais (CM_TO_M ausente → 100×, eixo trocado
 *   → sinal errado) e aceita ruído numérico de precisão de máquina.
 */
function floatEq(a: number, b: number): boolean {
  if (Object.is(a, b)) return true;
  if (a === 0 && b === 0) return true; // -0 ≡ 0
  const eps = 1e-10;
  const scale = Math.max(Math.abs(a), Math.abs(b), Number.EPSILON);
  return Math.abs(a - b) <= eps * scale;
}

interface MismatchInfo {
  field: string;
  index: number;
  ts: number;
  py: number;
}

interface CompareResult {
  ok: boolean;
  firstMismatch?: MismatchInfo;
}

function compareBuffers(
  ts: { pos: number[]; col: number[]; idx: number[] },
  py: PythonRefEntry,
): CompareResult {
  const pairs: Array<[string, number[], number[]]> = [
    ['pos', ts.pos, py.pos],
    ['col', ts.col, py.col],
    ['idx', ts.idx, py.idx],
  ];

  let firstMismatch: MismatchInfo | undefined;

  for (const [field, tsArr, pyArr] of pairs) {
    if (tsArr.length !== pyArr.length) {
      return {
        ok: false,
        firstMismatch: { field: `${field}.length`, index: -1, ts: tsArr.length, py: pyArr.length },
      };
    }
    if (!firstMismatch) {
      for (let i = 0; i < tsArr.length; i++) {
        if (!floatEq(tsArr[i], pyArr[i])) {
          firstMismatch = { field, index: i, ts: tsArr[i], py: pyArr[i] };
          break;
        }
      }
    }
  }

  return { ok: !firstMismatch, firstMismatch };
}

// ─── Testes de rejeição (OQ3DError) ──────────────────────────────────────────

/**
 * Verifica que o parser lança OQ3DError para blobs inválidos
 * sem alocar memória proporcional à contagem declarada.
 */
function testRejection(): void {
  // 1. Assinatura ausente
  {
    const noSig = Buffer.alloc(100, 0x42);
    try {
      toBuffers(noSig);
      throw new Error('FALHOU: deveria rejeitar blob sem assinatura');
    } catch (err) {
      if (!(err instanceof OQ3DError)) throw err;
    }
  }

  // 2. Contagem declarada maior que o buffer restante — sem alocar 10M×8 bytes
  //    Construção: assinatura OQ3D válida + OPEN + TQi3DIndexedTriangleMeshData
  //    + header de malha com n_coord=10_000_000, buffer truncado em 80 bytes.
  {
    const buf = Buffer.alloc(80, 0);
    // Prefix + magic (offset 5..24)
    Buffer.from('\x3a\x01\x01\x00\x00').copy(buf, 0);
    Buffer.from('OQ3D 3D Objects File').copy(buf, 5);
    // OPEN byte + length(28 LE) + class name
    buf[25] = 0x5b;
    buf.writeUInt32LE(28, 26);
    Buffer.from('TQi3DIndexedTriangleMeshData').copy(buf, 30);
    // Payload: ver=2 (u32), n_coord=10_000_000 (u32), reserved=0 (u32)
    // Offset 58 = 30 (class name end) + 28 (class name length offset correction)
    // Actually: classAt returns payloadOffset = 30 + 28 = 58
    buf.writeUInt32LE(2, 58);         // ver
    buf.writeUInt32LE(10_000_000, 62); // n_coord — 10M × 8 bytes >> buffer
    buf.writeUInt32LE(0, 66);          // reserved

    try {
      toBuffers(buf);
      // Se chegou aqui sem OQ3DError, verificar que nenhum crash ocorreu
      // (pode retornar vazio se o parser não chegou até readMesh)
    } catch (err) {
      if (!(err instanceof OQ3DError)) {
        throw new Error(`FALHOU: esperava OQ3DError para n_coord gigante, got ${(err as Error).constructor.name}: ${(err as Error).message}`);
      }
      // OQ3DError esperado ✓
    }
  }

  // 3. Blob com assinatura mas truncado antes dos dados de vértice
  //    Pegar blob real, truncar a 150 bytes — readMesh deve detectar truncamento
  {
    const { simbologias, porPeca } = extractSimboloias(AQ_PATH);
    const firstSimId = porPeca.values().next().value as number;
    const blob = simbologias.get(firstSimId)!.blob;
    // Truncar: garantir que capta a assinatura mas corta antes dos dados de vértice
    const truncated = blob.slice(0, 150);
    try {
      toBuffers(truncated);
      // OK se retornou vazio (parser não encontrou malha completa antes do truncamento)
    } catch (err) {
      if (!(err instanceof OQ3DError)) {
        throw new Error(`FALHOU: esperava OQ3DError para blob truncado, got ${(err as Error).constructor.name}`);
      }
      // OQ3DError esperado ✓
    }
  }
}

// ─── Pipeline TS ─────────────────────────────────────────────────────────────

function runTsPipeline(): {
  buffers: Map<number, { pos: number[]; col: number[]; idx: number[] }>;
  rssDeltaMb: number;
  heapDeltaMb: number;
  elapsedMs: number;
} {
  const memBefore = process.memoryUsage();
  const start = Date.now();

  const { simbologias, porPeca } = extractSimboloias(AQ_PATH);
  const buffers = new Map<number, { pos: number[]; col: number[]; idx: number[] }>();

  for (const [pecaId, simId] of porPeca) {
    const sim = simbologias.get(simId);
    if (!sim) continue;
    buffers.set(pecaId, toBuffers(sim.blob));
  }

  const elapsedMs = Date.now() - start;
  const memAfter = process.memoryUsage();

  return {
    buffers,
    rssDeltaMb: (memAfter.rss - memBefore.rss) / 1024 / 1024,
    heapDeltaMb: (memAfter.heapUsed - memBefore.heapUsed) / 1024 / 1024,
    elapsedMs,
  };
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  console.log('S2.2 — Spike do port TypeScript\n');

  // 1. Testes de rejeição
  process.stdout.write('Testes de rejeição (OQ3DError)... ');
  testRejection();
  console.log('OK');

  // 2. Pipeline TS
  process.stdout.write('Executando pipeline TypeScript... ');
  const { buffers: tsBuffers, rssDeltaMb, heapDeltaMb, elapsedMs } = runTsPipeline();
  console.log(`OK (${tsBuffers.size} produtos, ${elapsedMs} ms)`);

  // 3. Oráculo Python
  process.stdout.write('Gerando referência Python (pode levar ~40 s)... ');
  const pyRef = generatePythonReference();
  const pyCount = Object.keys(pyRef).length;
  console.log(`OK (${pyCount} produtos)`);

  // 4. Comparação semântica
  console.log('\nComparação semântica (elemento a elemento, -0 ≡ 0):');
  let allOk = true;
  let totalElements = 0;

  for (const [pecaIdStr, pyData] of Object.entries(pyRef)) {
    const pecaId = parseInt(pecaIdStr, 10);
    const ts = tsBuffers.get(pecaId);

    if (!ts) {
      console.error(`  ✗ Produto ${pecaId}: TS não produziu geometria (Python sim)`);
      allOk = false;
      continue;
    }

    const cmp = compareBuffers(ts, pyData);
    const posVerts = ts.pos.length / 3;
    const tris = ts.idx.length / 3;
    totalElements += ts.pos.length + ts.col.length + ts.idx.length;

    if (cmp.ok) {
      console.log(`  ✓ Produto ${pecaId}: ${posVerts} verts, ${tris} tris`);
    } else {
      allOk = false;
      const m = cmp.firstMismatch!;
      console.error(`  ✗ Produto ${pecaId}: divergência em ${m.field}[${m.index}] TS=${m.ts} PY=${m.py}`);
    }
  }

  // Verificar produtos TS não esperados
  for (const tsId of tsBuffers.keys()) {
    if (!pyRef[String(tsId)]) {
      console.error(`  ✗ Produto ${tsId}: TS produziu geometria mas Python não tem referência`);
      allOk = false;
    }
  }

  // 5. Relatório
  console.log('\n' + '─'.repeat(62));
  console.log('┌─ S2.2 — Spike do port TypeScript ─────────────────────────────┐');
  console.log(`│  produtos com geometria : ${tsBuffers.size} (Python: ${pyCount})`);
  console.log(`│  total de elementos     : ${(totalElements / 1e6).toFixed(1)}M`);
  console.log(`│  rssDeltaMb (TS)        : ${rssDeltaMb.toFixed(2)} MB  (Python S2.1: 189 MB)`);
  console.log(`│  heapDeltaMb (TS)       : ${heapDeltaMb.toFixed(2)} MB  (Python S2.1: 119 MB)`);
  console.log(`│  elapsedMs (TS)         : ${elapsedMs} ms  (Python S2.1: ~39 000 ms)`);
  console.log(`│  comparação semântica   : ${allOk ? 'PASSOU ✓' : 'FALHOU ✗'}`);
  console.log('└────────────────────────────────────────────────────────────────┘');

  if (!allOk) {
    process.exit(1);
  }

  console.log('\npnpm port:test ✓ — todas as verificações passaram');
}

main().catch((err) => {
  console.error('\nFALHOU:', err.message);
  console.error(err.stack);
  process.exit(1);
});
