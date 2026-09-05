import { Injectable, Logger } from '@nestjs/common';
import * as crypto from 'node:crypto';
import * as fs from 'node:fs';
import * as fsp from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { GeoBuffers } from '@bim/dominio';
import { executar, ProcessoError } from './processo';

/**
 * PipelineService — a fronteira entre o Nest e o pipeline (A2/A3 de
 * docs/arquitetura-www-servico-de-ingestao.md): cada método roda um processo filho de
 * `pipeline/` (Python ou o `thumbs.mjs` no Node) e devolve o que ele produziu, tipado.
 *
 *   catalogoDeAq   python3 pipeline/catalogo_de_aq.py   .aq|.zip → geo/<importId>/*.json + catálogo em JSON
 *   tesselar       python3 pipeline/step_to_geo.py | ifc_to_geo.py   CAD → {pos,col,idx,partes,…}
 *   gerarAq        python3 pipeline/geo_to_aq.py       partes do editor → .aq
 *   miniaturas     node    pipeline/thumbs.mjs         geometrias → WebP por geometria (Chromium)
 *
 * `PIPELINE_DIR` aponta para a pasta quando o serviço roda fora do repositório; por padrão é
 * `../../pipeline` a partir de `src/` (dev com ts-node). Só Python e Node aqui — nenhum parser
 * em TypeScript (A2).
 */

export function pipelineDir(env: NodeJS.ProcessEnv = process.env): string {
  return path.resolve(env.PIPELINE_DIR ?? path.join(__dirname, '..', '..', 'pipeline'));
}

const PYTHON = process.env.PYTHON ?? 'python3';
const TIMEOUT_MS = 30 * 60 * 1000;      // um Revit de 130 MB leva minutos no ifcopenshell
const OCIOSO_PYTHON_MS = 10 * 60 * 1000;
const OCIOSO_CHROMIUM_MS = 2 * 60 * 1000;   // thumbs.mjs sem uma linha por 2 min = Chromium travado

export interface ProdutoPipeline {
  id: string;
  nome: string;
  serie: string;
  geo: string;            // "<stem>.json", relativo ao geo-dir
  potencia: number | null;
  conexoes: string;
  specs: Record<string, string>;
  curva: number[][] | null;
  thumb?: string;
}

export interface ResultadoCatalogo {
  config: { slug: string; titulo: string; fabricante: string; descricao: string; layout: string };
  catalog: { slug: string; titulo: string; fabricante: string; descricao: string; layout: string; filtros: string[]; produtos: ProdutoPipeline[] };
  n_geometrias: number;
  diag: Record<string, unknown>;
  hints: { n_pecas: number; n_simbologias: number; schema: unknown; grupos: string[]; linhas: string[]; has_curves: boolean };
}

export interface StepGeo extends GeoBuffers {
  partes: Array<{ nome: string; cor?: number[]; tipo?: string; triangulos?: number; triangulo_inicial?: number }>;
  unidade: string;
  bbox_mm: number[];
  fonte: string;
  deflexao_mm?: number;
  escala_aplicada?: number;
  cor_por_face?: boolean;
  segundos: number;
  formato?: 'step' | 'ifc';
  caminho?: string;
  tamanho_mb?: number;
  aviso?: string;
}

export interface AqInfo {
  fabricante?: string; linha?: string; nome?: string; descricao?: string; codigo?: string;
  specs?: Record<string, string>; origem?: string;
}

export interface AqParte { nome: string; pos: number[]; col: number[] | null; idx: number[] }

export interface ResumoMiniaturas {
  total: number;
  geradas: string[];                            // stems
  falhas: Array<{ geo: string; message: string }>;
}

export function formatoDe(nome: string): 'step' | 'ifc' {
  return /\.ifc(zip|xml)?$/i.test(nome) ? 'ifc' : 'step';
}

@Injectable()
export class PipelineService {
  private readonly logger = new Logger(PipelineService.name);
  readonly dir = pipelineDir();

  constructor() {
    if (!fs.existsSync(path.join(this.dir, 'catalogo_de_aq.py'))) {
      throw new Error(`pipeline/ não encontrado em ${this.dir} — defina PIPELINE_DIR (veja www/.env.example)`);
    }
  }

  private script(nome: string) { return path.join(this.dir, nome); }

  /** `.aq`/`.zip` → geometrias em `geoDir` + catálogo. Progresso do Python linha a linha em `onProgresso`. */
  async catalogoDeAq(opts: { aqPath: string; geoDir: string; nomeOriginal?: string; onProgresso?: (linha: string) => void }): Promise<ResultadoCatalogo> {
    const saida = path.join(os.tmpdir(), `catalogo-${crypto.randomUUID()}.json`);
    const args = [this.script('catalogo_de_aq.py'), opts.aqPath, '--geo-dir', opts.geoDir, '--saida', saida, '--sair-com-stdin'];
    if (opts.nomeOriginal) args.push('--nome-original', opts.nomeOriginal);
    try {
      await executar(PYTHON, args, {
        nome: 'catalogo_de_aq.py', cwd: this.dir, timeoutMs: TIMEOUT_MS, ociosoMs: OCIOSO_PYTHON_MS,
        onStderr: (l) => { if (l.trim()) opts.onProgresso?.(l.trim()); },
      });
      return JSON.parse(await fsp.readFile(saida, 'utf8')) as ResultadoCatalogo;
    } finally {
      await fsp.unlink(saida).catch(() => {});
    }
  }

  /**
   * CAD já em disco → geometria do viewer. `.stp/.step` → `step_to_geo.py` (OpenCASCADE, deflexão
   * em mm); `.ifc` → `ifc_to_geo.py` (parse_ifc.py exato ou ifcopenshell para arquivo grande).
   */
  async tesselar(caminho: string, deflexaoMm = 0.2, nomeOriginal?: string, onProgresso?: (linha: string) => void): Promise<StepGeo> {
    const outJson = path.join(os.tmpdir(), `cad-${crypto.randomUUID()}.json`);
    const t0 = Date.now();
    const formato = formatoDe(nomeOriginal ?? caminho);
    const args = formato === 'ifc'
      ? [this.script('ifc_to_geo.py'), caminho, outJson]
      : [this.script('step_to_geo.py'), caminho, outJson, '--deflexao', String(deflexaoMm)];
    try {
      await executar(PYTHON, args, {
        nome: path.basename(args[0]), cwd: this.dir, timeoutMs: TIMEOUT_MS, ociosoMs: OCIOSO_PYTHON_MS,
        onStderr: (l) => { if (l.trim()) onProgresso?.(l.trim()); },
      });
      const geo = JSON.parse(await fsp.readFile(outJson, 'utf8')) as StepGeo;
      if (nomeOriginal) geo.fonte = path.basename(nomeOriginal);   // o script grava o nome temporário do multer
      geo.formato = formato;
      this.logger.log(
        `${formato.toUpperCase()} convertido — ${geo.fonte}: ${geo.partes.length} parte(s), ${geo.idx.length / 3} triângulos, ` +
          `bbox ${geo.bbox_mm.map((v) => v.toFixed(0)).join('×')} mm, ${((Date.now() - t0) / 1000).toFixed(1)}s`,
      );
      return geo;
    } finally {
      await fsp.unlink(outJson).catch(() => {});
    }
  }

  /** Partes do editor → `.aq` temporário (quem chama apaga). */
  async gerarAq(info: AqInfo, partes: AqParte[], geo?: GeoBuffers): Promise<{ path: string; resumo: Record<string, any> }> {
    const id = crypto.randomUUID();
    const inJson = path.join(os.tmpdir(), `aq-in-${id}.json`);
    const outAq = path.join(os.tmpdir(), `aq-out-${id}.aq`);
    await fsp.writeFile(inJson, JSON.stringify({ info, partes: partes.length ? partes : undefined, ...(geo ?? {}) }));
    try {
      const { stdout } = await executar(PYTHON, [this.script('geo_to_aq.py'), inJson, outAq, '--quiet'], {
        nome: 'geo_to_aq.py', cwd: this.dir, timeoutMs: 10 * 60 * 1000,
      });
      const linhaJson = stdout.trim().split('\n').reverse().find((l) => l.startsWith('{')) ?? '{}';
      const resumo = JSON.parse(linhaJson);
      this.logger.log(`.aq gerado — ${resumo.peca}: ${resumo.malhas} malha(s), ${resumo.triangulos} triângulos, ${(resumo.bytes / 1024).toFixed(0)} KB`);
      return { path: outAq, resumo };
    } finally {
      await fsp.unlink(inJson).catch(() => {});
    }
  }

  /**
   * Uma miniatura WebP por geometria, no Chromium (A2/A6). `geos` são caminhos relativos a
   * `geoDir`; a saída é `<outDir>/<stem>.webp`. Cada geometria que falha vem em `falhas`
   * (o thumbs.mjs continua as outras); se o Chromium nem sobe, lança `ProcessoError`.
   */
  async miniaturas(opts: {
    geoDir: string; geos: string[]; outDir: string;
    onMiniatura?: (stem: string, bytes: number) => void;
    onFalha?: (stem: string, message: string) => void;
  }): Promise<ResumoMiniaturas> {
    const resumo: ResumoMiniaturas = { total: opts.geos.length, geradas: [], falhas: [] };
    if (!opts.geos.length) return resumo;
    await fsp.mkdir(opts.outDir, { recursive: true });
    const cfgPath = path.join(opts.outDir, `.thumbs-${crypto.randomUUID()}.json`);
    const cfg = {
      harnessDir: this.dir,
      vendorDir: path.dirname(require.resolve('three/build/three.module.js')),
      geoDir: opts.geoDir,
      outDir: opts.outDir,
      geos: opts.geos,
      sairComStdin: true,
    };
    await fsp.writeFile(cfgPath, JSON.stringify(cfg));
    try {
      const r = await executar(process.execPath, [this.script('thumbs.mjs'), cfgPath], {
        nome: 'thumbs.mjs', cwd: this.dir, timeoutMs: TIMEOUT_MS, ociosoMs: OCIOSO_CHROMIUM_MS,
        aceitarCodigos: [0, 2], guardarStdout: false,
        onStdout: (linha) => {
          let msg: any;
          try { msg = JSON.parse(linha); } catch { return; }
          if (msg.error) {
            resumo.falhas.push({ geo: msg.geo, message: String(msg.error) });
            opts.onFalha?.(msg.geo, String(msg.error));
          } else {
            resumo.geradas.push(msg.geo);
            opts.onMiniatura?.(msg.geo, msg.bytes);
          }
        },
      });
      // saiu com 2 sem relatar falha por geometria = parou porque o pai fechou o stdin (não acontece com o pai vivo)
      if (r.code === 2 && resumo.geradas.length + resumo.falhas.length < opts.geos.length) {
        const faltam = opts.geos.length - resumo.geradas.length - resumo.falhas.length;
        throw new ProcessoError(`thumbs.mjs parou antes do fim — ${faltam} geometria(s) sem miniatura`, 'saida', 2, null, r.stderr);
      }
      return resumo;
    } finally {
      await fsp.unlink(cfgPath).catch(() => {});
    }
  }
}
