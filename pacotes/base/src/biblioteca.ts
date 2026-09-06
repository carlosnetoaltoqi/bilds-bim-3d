/**
 * biblioteca.ts — o cliente TIPADO da biblioteca Python `bim_pipeline`: um método por CLI, com o
 * contrato de entrada/saída validado (`validarContrato`). Todo serviço que precisa da biblioteca
 * instancia `Biblioteca` (ou a injeta) e chama o que é do seu contexto:
 *
 *   catalogoDeAq / catalogoDePlugin / inspecionarPlugin   criador de catálogos (e conversores, o inspecionar)
 *   inspecionarFamiliasRevit / catalogoDeFamiliasRevit    criador de catálogos (famílias .rfa, soltas ou em .zip)
 *   tesselar / gerarAq                                    conversores (e o criador, para peça CAD)
 *   catalogoParaAq                                        criador de catálogos (exportar catálogo salvo → .aq)
 *   gerarZipBilds                                         gerador de ZIP
 *   miniaturas                                            criador de catálogos
 *
 * Só Python e Node aqui — nenhum parser em TypeScript (ADR-002). Nasceu como `PipelineService` do
 * serviço de ingestão (S7.14) e virou parte da base na S8/F3, para que os serviços stateless não
 * copiassem os métodos.
 */
import { Logger } from '@nestjs/common';
import * as crypto from 'node:crypto';
import * as fsp from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { BibliotecaCli } from './biblioteca-cli';
import { validarContrato } from './contratos';
import { GeoBuffers } from './geo-buffers';
import { ProcessoError } from './processo';

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

/** O que `plugin_catalogo_web inspecionar` tira da DLL (e, com rede, do catálogo web). */
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

/** O que `familias_revit inspecionar` tira de um .rfa, pasta ou .zip de famílias Revit (contrato `info-familias-revit`). */
export interface FamiliasRevitInfo {
  entrada: string;
  bytes: number;
  n_familias: number;
  n_tipos: number;
  com_geometria_irma: number;
  n_projetos: number;
  projetos_sem_ifc: number;        // projetos .rvt que só entram com a tradução pela APS
  ignorados: number;
  avisos: string[];
  familias: Array<{
    arquivo: string; titulo: string; revit?: string | null; formato?: number | null; categoria?: string | null; fabricante?: string | null;
    tipos: number; type_catalog: boolean; geometria_irma?: string | null; preview: boolean;
  }>;
  projetos: Array<{ arquivo: string; revit?: string | null; formato?: number | null; bytes: number; ifc_irmao?: string | null }>;
}

/** Credenciais de um app APS (Model Derivative) — só existem em memória e num JSON temporário 0600 para o filho. */
export interface CredenciaisAps { client_id: string; client_secret: string }

/** Os cinco campos do formulário de download do catálogo web — nunca persistidos. */
export interface LeadDownload { full_name: string; email: string; mobile: string; company: string; position: string }

export function formatoDe(nome: string): 'step' | 'iges' | 'ifc' {
  if (/\.ifc(zip|xml)?$/i.test(nome)) return 'ifc';
  return /\.ige?s$/i.test(nome) ? 'iges' : 'step';
}

export class Biblioteca extends BibliotecaCli {
  private readonly logger = new Logger(Biblioteca.name);

  /** `.aq`/`.zip` → geometrias em `geoDir` + catálogo. Progresso do Python linha a linha em `onProgresso`. */
  async catalogoDeAq(opts: { aqPath: string; geoDir: string; nomeOriginal?: string; onProgresso?: (linha: string) => void }): Promise<ResultadoCatalogo> {
    const saida = path.join(os.tmpdir(), `catalogo-${crypto.randomUUID()}.json`);
    const args = [opts.aqPath, '--geo-dir', opts.geoDir, '--saida', saida, '--sair-com-stdin'];
    if (opts.nomeOriginal) args.push('--nome-original', opts.nomeOriginal);
    try {
      await this.rodar('catalogo_de_aq', args, {
        onStderr: (l) => { if (l.trim()) opts.onProgresso?.(l.trim()); },
      });
      return validarContrato<ResultadoCatalogo>('catalogo', JSON.parse(await fsp.readFile(saida, 'utf8')));
    } finally {
      await fsp.unlink(saida).catch(() => {});
    }
  }

  /**
   * DLL de um plugin de AutoCAD → host do catálogo web, nome/versão do plugin e, salvo `semRede`,
   * título do catálogo e categorias (com o número de grupos de cada). Síncrono, segundos.
   */
  async inspecionarPlugin(dllPath: string, opts: { semRede?: boolean } = {}): Promise<PluginInfo> {
    const args = ['inspecionar', dllPath];
    if (opts.semRede) args.push('--sem-rede');
    const { stdout } = await this.rodar('plugin_catalogo_web', args, { timeoutMs: 5 * 60 * 1000 });
    const linha = stdout.trim().split('\n').reverse().find((l) => l.startsWith('{'));
    if (!linha) throw new Error('plugin_catalogo_web inspecionar terminou sem o JSON');
    return validarContrato<PluginInfo>('info-plugin', JSON.parse(linha));
  }

  /**
   * Categoria de um catálogo web → arquivos baixados em `downloads` (IGES/RFA + manifesto) e
   * geometrias em `geoDir`, devolvendo o mesmo `ResultadoCatalogo` do `catalogo_de_aq.py`. O lead
   * vai num JSON temporário apagado no `finally` — não fica em disco nem no log.
   */
  async catalogoDePlugin(opts: {
    host: string; categoria: string; lead: LeadDownload; downloads: string; geoDir: string;
    igsPorGrupo?: number; deflexao?: number; plugin?: PluginInfo | null; onProgresso?: (linha: string) => void;
  }): Promise<ResultadoCatalogo> {
    const id = crypto.randomUUID();
    const leadPath = path.join(os.tmpdir(), `plugin-lead-${id}.json`);
    const pluginPath = path.join(os.tmpdir(), `plugin-info-${id}.json`);
    const saida = path.join(os.tmpdir(), `plugin-catalogo-${id}.json`);
    await fsp.writeFile(leadPath, JSON.stringify(opts.lead), { mode: 0o600 });
    const args = [
      'importar', '--host', opts.host, '--categoria', opts.categoria, '--lead', leadPath,
      '--downloads', opts.downloads, '--geo-dir', opts.geoDir, '--saida', saida,
      '--igs-por-grupo', String(opts.igsPorGrupo ?? 1), '--deflexao', String(opts.deflexao ?? 0.2), '--sair-com-stdin',
    ];
    if (opts.plugin) {
      await fsp.writeFile(pluginPath, JSON.stringify(opts.plugin));
      args.push('--plugin', pluginPath);
    }
    try {
      await this.rodar('plugin_catalogo_web', args, {
        onStderr: (l) => { if (l.trim()) opts.onProgresso?.(l.trim()); },
      });
      return validarContrato<ResultadoCatalogo>('catalogo', JSON.parse(await fsp.readFile(saida, 'utf8')));
    } finally {
      await Promise.all([leadPath, pluginPath, saida].map((p) => fsp.unlink(p).catch(() => {})));
    }
  }

  /**
   * `.rfa`, pasta ou `.zip` de famílias Revit → famílias, tipos, categorias, quais têm type catalog e
   * geometria irmã. Síncrono, segundos (só lê os streams OLE — nunca a geometria, que é proprietária).
   */
  async inspecionarFamiliasRevit(entrada: string): Promise<FamiliasRevitInfo> {
    const { stdout } = await this.rodar('familias_revit', ['inspecionar', entrada], { timeoutMs: 5 * 60 * 1000 });
    const linha = stdout.trim().split('\n').reverse().find((l) => l.startsWith('{'));
    if (!linha) throw new Error('familias_revit inspecionar terminou sem o JSON');
    return validarContrato<FamiliasRevitInfo>('info-familias-revit', JSON.parse(linha));
  }

  /**
   * Famílias Revit → geometrias em `geoDir` (uma por família com geometria irmã; uma por conjunto de
   * cotas nas formas representativas) e o mesmo `ResultadoCatalogo` do `catalogo_de_aq.py`.
   * `comprimentoMm` é o trecho das formas representativas (padrão da biblioteca: 1000).
   */
  async catalogoDeFamiliasRevit(opts: {
    entrada: string; geoDir: string; titulo?: string; fabricante?: string; comprimentoMm?: number; deflexao?: number;
    /** projetos .rvt → IFC pela APS (cobrado por projeto); `apsCache` evita pagar duas vezes pelo mesmo .rvt */
    aps?: CredenciaisAps | null; apsCache?: string;
    onProgresso?: (linha: string) => void;
  }): Promise<ResultadoCatalogo> {
    const id = crypto.randomUUID();
    const saida = path.join(os.tmpdir(), `familias-revit-${id}.json`);
    const credPath = path.join(os.tmpdir(), `familias-revit-aps-${id}.json`);
    const args = ['importar', opts.entrada, '--geo-dir', opts.geoDir, '--saida', saida, '--sair-com-stdin'];
    if (opts.titulo) args.push('--titulo', opts.titulo);
    if (opts.fabricante) args.push('--fabricante', opts.fabricante);
    if (opts.comprimentoMm) args.push('--comprimento-mm', String(opts.comprimentoMm));
    if (opts.deflexao) args.push('--deflexao', String(opts.deflexao));
    if (opts.aps) {
      await fsp.writeFile(credPath, JSON.stringify(opts.aps), { mode: 0o600 });
      args.push('--aps-credenciais', credPath);
      if (opts.apsCache) args.push('--aps-cache', opts.apsCache);
    }
    try {
      await this.rodar('familias_revit', args, {
        onStderr: (l) => { if (l.trim()) opts.onProgresso?.(l.trim()); },
      });
      return validarContrato<ResultadoCatalogo>('catalogo', JSON.parse(await fsp.readFile(saida, 'utf8')));
    } finally {
      await Promise.all([saida, credPath].map((p) => fsp.unlink(p).catch(() => {})));
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
    const [cli, args] = formato === 'ifc'
      ? ['ifc', [caminho, outJson]] as const
      : ['step_iges', [caminho, outJson, '--deflexao', String(deflexaoMm)]] as const;
    try {
      await this.rodar(cli, [...args], {
        onStderr: (l) => { if (l.trim()) onProgresso?.(l.trim()); },
      });
      const geo = validarContrato<StepGeo>('geometria', JSON.parse(await fsp.readFile(outJson, 'utf8')));
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
      const { stdout } = await this.rodar('gerar_aq', [inJson, outAq, '--quiet'], {
        timeoutMs: 10 * 60 * 1000,
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
    validarContrato('manifesto-catalogo-aq', manifesto);
    await fsp.writeFile(inJson, JSON.stringify(manifesto));
    try {
      const { stdout } = await this.rodar('catalogo_para_aq', [inJson, outAq], {
        
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
    const args = [opts.aqPath, '--saida', outZip, '--sair-com-stdin'];
    if (opts.nomeOriginal) args.push('--nome-original', opts.nomeOriginal);
    args.push(opts.skipThumbs ? '--skip-thumbs' : '--allow-no-thumbs');   // quem pediu está esperando um download
    try {
      await this.rodar('zip_bilds', args, {
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
      const r = await this.rodarThumbs(cfgPath, {
        guardarStdout: false,
        onStdout: (linha) => {
          let msg: any;
          try { msg = validarContrato('resumo-miniaturas', JSON.parse(linha)); } catch { return; }
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
