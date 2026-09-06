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
 *   inspecionarPlugin / catalogoDePlugin
 *                  python3 pipeline/catallog.py         DLL de plugin de AutoCAD (Catallog) → host e categorias;
 *                                                       categoria → download dos IGES/RFA + tesselação → o MESMO
 *                                                       JSON do catalogo_de_aq.py (S7.17)
 *   tesselar       python3 pipeline/step_to_geo.py | ifc_to_geo.py   CAD (STEP, IGES, IFC) → {pos,col,idx,partes,…}
 *   gerarAq        python3 pipeline/geo_to_aq.py       partes do editor → .aq
 *   catalogoParaAq python3 pipeline/catalogo_to_aq.py  catálogo salvo (produtos + geometria do storage) → .aq
 *   miniaturas     node    pipeline/thumbs.mjs         geometrias → WebP por geometria (Chromium)
 *
 * A biblioteca é o pacote Python `bim_pipeline` em `biblioteca/` (`BIBLIOTECA_DIR`); cada método roda
 * `python -m bim_pipeline.cli.<nome>` ou o `thumbs.mjs` dela. Só Python e Node aqui — nenhum parser
 * em TypeScript (ADR-002).
 */

/**
 * Onde está a biblioteca Python (`biblioteca/`, com o pacote `bim_pipeline`). `BIBLIOTECA_DIR`
 * aponta para ela quando o serviço roda fora do repositório; por padrão é `../../../../../biblioteca`
 * a partir de `src/pipeline/`. Vai no PYTHONPATH do filho, então funciona instalada ou não (S8/F1).
 */
export function pipelineDir(env: NodeJS.ProcessEnv = process.env): string {
  return path.resolve(env.BIBLIOTECA_DIR ?? path.join(__dirname, '..', '..', '..', '..', '..', 'biblioteca'));
}

/** Ambiente do filho Python: a biblioteca no PYTHONPATH. */
function envPython(dir: string): NodeJS.ProcessEnv {
  const atual = process.env.PYTHONPATH;
  return { ...process.env, PYTHONPATH: atual ? `${dir}${path.delimiter}${atual}` : dir };
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
  formato?: 'step' | 'iges' | 'ifc';
  caminho?: string;
  tamanho_mb?: number;
  aviso?: string;
  volume_cm3?: number;
  costurado?: boolean;        // IGES: faces soltas costuradas num sólido (S7.17)
  arestas_livres?: number;
}

export interface AqInfo {
  fabricante?: string; linha?: string; nome?: string; descricao?: string; codigo?: string;
  specs?: Record<string, string>; origem?: string;
}

export interface AqParte { nome: string; pos: number[]; col: number[] | null; idx: number[] }

/** Entrada do `catalogo_to_aq.py` — o que o serviço monta a partir do Mongo (ver docstring do script). */
export interface ManifestoCatalogoAq {
  catalogo: { fabricante: string; titulo: string; slug: string; descricao?: string; origem?: string };
  geo_dir: string;
  produtos: Array<{
    id: string; nome: string; serie: string; conexoes: string;
    specs: Record<string, string>; curva: number[][] | null; potencia: number | null;
    codigo?: string; geo: string;
  }>;
}

export interface ResumoMiniaturas {
  total: number;
  geradas: string[];                            // stems
  falhas: Array<{ geo: string; message: string }>;
}

/** O que `catallog.py inspecionar` tira da DLL (e, com rede, do catálogo web). */
export interface PluginInfo {
  arquivo: string;
  bytes: number;
  host: string;
  hosts: string[];
  plugin: string | null;
  empresa: string | null;
  versao: string | null;
  dotnet: boolean;
  titulo?: string;
  formulario_download?: string | null;
  categorias?: Array<{ slug: string; name: string; grupos: number; grupos_nomes: string[] }>;
}

/** Os cinco campos do formulário de download do catálogo Catallog — nunca persistidos. */
export interface LeadDownload { full_name: string; email: string; mobile: string; company: string; position: string }

export function formatoDe(nome: string): 'step' | 'iges' | 'ifc' {
  if (/\.ifc(zip|xml)?$/i.test(nome)) return 'ifc';
  return /\.ige?s$/i.test(nome) ? 'iges' : 'step';
}

@Injectable()
export class PipelineService {
  private readonly logger = new Logger(PipelineService.name);
  readonly dir = pipelineDir();

  constructor() {
    if (!fs.existsSync(path.join(this.dir, 'bim_pipeline', 'cli', 'catalogo_de_aq.py'))) {
      throw new Error(`biblioteca/ não encontrada em ${this.dir} — defina BIBLIOTECA_DIR (veja www/.env.example)`);
    }
  }

  /** `python -m bim_pipeline.cli.<nome>` — a única forma de chegar à biblioteca. */
  private script(nome: string): string[] { return ['-m', `bim_pipeline.cli.${nome}`]; }
  private readonly env = envPython(pipelineDir());
  private get thumbsMjs() { return path.join(this.dir, 'bim_pipeline', 'miniaturas', 'thumbs.mjs'); }

  /** `.aq`/`.zip` → geometrias em `geoDir` + catálogo. Progresso do Python linha a linha em `onProgresso`. */
  async catalogoDeAq(opts: { aqPath: string; geoDir: string; nomeOriginal?: string; onProgresso?: (linha: string) => void }): Promise<ResultadoCatalogo> {
    const saida = path.join(os.tmpdir(), `catalogo-${crypto.randomUUID()}.json`);
    const args = [...this.script('catalogo_de_aq'), opts.aqPath, '--geo-dir', opts.geoDir, '--saida', saida, '--sair-com-stdin'];
    if (opts.nomeOriginal) args.push('--nome-original', opts.nomeOriginal);
    try {
      await executar(PYTHON, args, {
        nome: 'catalogo_de_aq.py', cwd: this.dir, env: this.env, timeoutMs: TIMEOUT_MS, ociosoMs: OCIOSO_PYTHON_MS,
        onStderr: (l) => { if (l.trim()) opts.onProgresso?.(l.trim()); },
      });
      return JSON.parse(await fsp.readFile(saida, 'utf8')) as ResultadoCatalogo;
    } finally {
      await fsp.unlink(saida).catch(() => {});
    }
  }

  /**
   * DLL de um plugin de AutoCAD → host do catálogo web, nome/versão do plugin e, salvo `semRede`,
   * título do catálogo e categorias (com o número de grupos de cada). Síncrono, segundos.
   */
  async inspecionarPlugin(dllPath: string, opts: { semRede?: boolean } = {}): Promise<PluginInfo> {
    const args = [...this.script('plugin_catalogo_web'), 'inspecionar', dllPath];
    if (opts.semRede) args.push('--sem-rede');
    const { stdout } = await executar(PYTHON, args, { nome: 'catallog.py inspecionar', cwd: this.dir, env: this.env, timeoutMs: 5 * 60 * 1000 });
    const linha = stdout.trim().split('\n').reverse().find((l) => l.startsWith('{'));
    if (!linha) throw new Error('catallog.py inspecionar terminou sem o JSON');
    return JSON.parse(linha) as PluginInfo;
  }

  /**
   * Categoria de um catálogo Catallog → arquivos baixados em `downloads` (IGES/RFA + manifesto) e
   * geometrias em `geoDir`, devolvendo o mesmo `ResultadoCatalogo` do `catalogo_de_aq.py`. O lead
   * vai num JSON temporário apagado no `finally` — não fica em disco nem no log.
   */
  async catalogoDePlugin(opts: {
    host: string; categoria: string; lead: LeadDownload; downloads: string; geoDir: string;
    igsPorGrupo?: number; deflexao?: number; plugin?: PluginInfo | null; onProgresso?: (linha: string) => void;
  }): Promise<ResultadoCatalogo> {
    const id = crypto.randomUUID();
    const leadPath = path.join(os.tmpdir(), `catallog-lead-${id}.json`);
    const pluginPath = path.join(os.tmpdir(), `catallog-plugin-${id}.json`);
    const saida = path.join(os.tmpdir(), `catallog-catalogo-${id}.json`);
    await fsp.writeFile(leadPath, JSON.stringify(opts.lead), { mode: 0o600 });
    const args = [
      ...this.script('plugin_catalogo_web'), 'importar', '--host', opts.host, '--categoria', opts.categoria, '--lead', leadPath,
      '--downloads', opts.downloads, '--geo-dir', opts.geoDir, '--saida', saida,
      '--igs-por-grupo', String(opts.igsPorGrupo ?? 1), '--deflexao', String(opts.deflexao ?? 0.2), '--sair-com-stdin',
    ];
    if (opts.plugin) {
      await fsp.writeFile(pluginPath, JSON.stringify(opts.plugin));
      args.push('--plugin', pluginPath);
    }
    try {
      await executar(PYTHON, args, {
        nome: 'catallog.py importar', cwd: this.dir, env: this.env, timeoutMs: TIMEOUT_MS, ociosoMs: OCIOSO_PYTHON_MS,
        onStderr: (l) => { if (l.trim()) opts.onProgresso?.(l.trim()); },
      });
      return JSON.parse(await fsp.readFile(saida, 'utf8')) as ResultadoCatalogo;
    } finally {
      await Promise.all([leadPath, pluginPath, saida].map((p) => fsp.unlink(p).catch(() => {})));
    }
  }

  /**
   * CAD já em disco → geometria do viewer. `.stp/.step/.igs/.iges` → `step_to_geo.py` (OpenCASCADE,
   * deflexão em mm; IGES costurado); `.ifc` → `ifc_to_geo.py` (parse_ifc.py exato ou ifcopenshell para arquivo grande).
   */
  async tesselar(caminho: string, deflexaoMm = 0.2, nomeOriginal?: string, onProgresso?: (linha: string) => void): Promise<StepGeo> {
    const outJson = path.join(os.tmpdir(), `cad-${crypto.randomUUID()}.json`);
    const t0 = Date.now();
    const formato = formatoDe(nomeOriginal ?? caminho);
    const args = formato === 'ifc'
      ? [...this.script('ifc'), caminho, outJson]
      : [...this.script('step_iges'), caminho, outJson, '--deflexao', String(deflexaoMm)];
    try {
      await executar(PYTHON, args, {
        nome: path.basename(args[0]), cwd: this.dir, env: this.env, timeoutMs: TIMEOUT_MS, ociosoMs: OCIOSO_PYTHON_MS,
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
      const { stdout } = await executar(PYTHON, [...this.script('gerar_aq'), inJson, outAq, '--quiet'], {
        nome: 'geo_to_aq.py', cwd: this.dir, env: this.env, timeoutMs: 10 * 60 * 1000,
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
   * Catálogo salvo → `.aq` temporário com todas as peças (quem chama serve e apaga). O Python
   * imprime o progresso no stderr (uma linha a cada 50 geometrias) e o resumo em JSON na última
   * linha do stdout; qualquer erro (geometria ausente, caractere fora do cp1252, FK órfã) sai
   * com 1 e vira `ProcessoError` com o stderr — nada é engolido.
   */
  async catalogoParaAq(manifesto: ManifestoCatalogoAq, onProgresso?: (linha: string) => void): Promise<{ path: string; resumo: Record<string, any> }> {
    const id = crypto.randomUUID();
    const inJson = path.join(os.tmpdir(), `aq-catalogo-in-${id}.json`);
    const outAq = path.join(os.tmpdir(), `aq-catalogo-out-${id}.aq`);
    await fsp.writeFile(inJson, JSON.stringify(manifesto));
    try {
      const { stdout } = await executar(PYTHON, [...this.script('catalogo_para_aq'), inJson, outAq], {
        nome: 'catalogo_to_aq.py', cwd: this.dir, env: this.env, timeoutMs: TIMEOUT_MS, ociosoMs: OCIOSO_PYTHON_MS,
        onStderr: (l) => { if (l.trim()) onProgresso?.(l.trim()); },
      });
      const linhaJson = stdout.trim().split('\n').reverse().find((l) => l.startsWith('{'));
      if (!linhaJson) throw new Error('catalogo_to_aq.py terminou sem o resumo em JSON');
      return { path: outAq, resumo: JSON.parse(linhaJson) };
    } catch (e) {
      await fsp.unlink(outAq).catch(() => {});
      throw e;
    } finally {
      await fsp.unlink(inJson).catch(() => {});
    }
  }

  /**
   * `.aq` ou `.zip` → ZIP do formato bilds.com (manifest + catalog + geo/ + thumbs/).
   * O ZIP de saída é temporário: quem chama serve como download e apaga.
   * `skipThumbs` passa `--skip-thumbs`; sem ele o Chromium roda mas uma falha de miniatura
   * não aborta o build — o ZIP sai sem `thumbs/` e o viewer renderiza no browser.
   */
  async gerarZipBilds(opts: {
    aqPath: string;
    nomeOriginal?: string;
    skipThumbs?: boolean;
    onProgresso?: (linha: string) => void;
  }): Promise<{ path: string }> {
    const outZip = path.join(os.tmpdir(), `bilds-zip-${crypto.randomUUID()}.zip`);
    const args = [...this.script('zip_bilds'), opts.aqPath, '--saida', outZip, '--sair-com-stdin'];
    if (opts.nomeOriginal) args.push('--nome-original', opts.nomeOriginal);
    if (opts.skipThumbs) args.push('--skip-thumbs');
    try {
      await executar(PYTHON, args, {
        nome: 'zip_bilds.py', cwd: this.dir, env: this.env, timeoutMs: TIMEOUT_MS, ociosoMs: OCIOSO_PYTHON_MS,
        onStderr: (l) => { if (l.trim()) opts.onProgresso?.(l.trim()); },
      });
      return { path: outZip };
    } catch (e) {
      await fsp.unlink(outZip).catch(() => {});
      throw e;
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
      geoDir: opts.geoDir,
      outDir: opts.outDir,
      geos: opts.geos,
      sairComStdin: true,
    };
    await fsp.writeFile(cfgPath, JSON.stringify(cfg));
    try {
      const r = await executar(process.execPath, [this.thumbsMjs, cfgPath], {
        nome: 'thumbs.mjs', cwd: path.dirname(this.thumbsMjs), timeoutMs: TIMEOUT_MS, ociosoMs: OCIOSO_CHROMIUM_MS,
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
