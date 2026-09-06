/**
 * biblioteca-cli.ts — a ÚNICA porta dos serviços para a biblioteca Python `bim_pipeline`
 * (docs/arquitetura.md §3, regra 2; ADR-003/ADR-004).
 *
 * Só aqui se sabe onde a biblioteca está (`BIBLIOTECA_DIR`), qual Python roda (`PYTHON`) e como
 * uma CLI se chama (`python -m bim_pipeline.cli.<nome>`). Toda CLI recebe `--sair-com-stdin`
 * quando quem chama é um serviço (ADR-010): o filho morre com o pai. O `thumbs.mjs` da biblioteca
 * roda no próprio Node do serviço (`process.execPath`).
 */
import * as fs from 'node:fs';
import * as path from 'node:path';
import { executar, OpcoesProcesso, ResultadoProcesso } from './processo';

export const PYTHON = process.env.PYTHON ?? 'python3';
export const TIMEOUT_PADRAO_MS = 30 * 60 * 1000;       // um IFC de 130 MB leva minutos no ifcopenshell
export const OCIOSO_PYTHON_MS = 10 * 60 * 1000;
export const OCIOSO_CHROMIUM_MS = 2 * 60 * 1000;      // thumbs.mjs sem uma linha por 2 min = Chromium travado

/**
 * Pasta `biblioteca/` (a que contém `bim_pipeline/`). `BIBLIOTECA_DIR` quando o serviço roda fora
 * do repositório; por padrão, a raiz do repositório a partir deste pacote (`pacotes/base/src` → `../../..`).
 * Vai no PYTHONPATH do filho, então funciona com a biblioteca instalada ou não.
 */
export function bibliotecaDir(env: NodeJS.ProcessEnv = process.env): string {
  return path.resolve(env.BIBLIOTECA_DIR ?? path.join(__dirname, '..', '..', '..', 'biblioteca'));
}

export function envBiblioteca(dir: string, env: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
  const atual = env.PYTHONPATH;
  return { ...env, PYTHONPATH: atual ? `${dir}${path.delimiter}${atual}` : dir };
}

export class BibliotecaCli {
  readonly dir: string;
  readonly env: NodeJS.ProcessEnv;

  constructor(dir = bibliotecaDir()) {
    this.dir = dir;
    if (!fs.existsSync(path.join(dir, 'bim_pipeline', 'cli', '__init__.py'))) {
      throw new Error(`biblioteca/ não encontrada em ${dir} — defina BIBLIOTECA_DIR`);
    }
    this.env = envBiblioteca(dir);
  }

  /** `python -m bim_pipeline.cli.<nome> <args>` com a biblioteca no PYTHONPATH. */
  rodar(cli: string, args: string[], opts: OpcoesProcesso = {}): Promise<ResultadoProcesso> {
    return executar(PYTHON, ['-m', `bim_pipeline.cli.${cli}`, ...args], {
      nome: cli, cwd: this.dir, env: this.env,
      timeoutMs: TIMEOUT_PADRAO_MS, ociosoMs: OCIOSO_PYTHON_MS,
      ...opts,
    });
  }

  /** O harness de miniaturas da biblioteca, no Node deste processo. */
  rodarThumbs(cfgPath: string, opts: OpcoesProcesso = {}): Promise<ResultadoProcesso> {
    const mjs = this.thumbsMjs;
    return executar(process.execPath, [mjs, cfgPath], {
      nome: 'thumbs.mjs', cwd: path.dirname(mjs),
      timeoutMs: TIMEOUT_PADRAO_MS, ociosoMs: OCIOSO_CHROMIUM_MS,
      aceitarCodigos: [0, 2],
      ...opts,
    });
  }

  get thumbsMjs(): string { return path.join(this.dir, 'bim_pipeline', 'miniaturas', 'thumbs.mjs'); }

  /** A última linha do stdout que é um objeto JSON — o resumo que as CLIs imprimem ao fim. */
  static ultimoJson<T = Record<string, any>>(stdout: string, oQue = 'resumo'): T {
    const linha = stdout.trim().split('\n').reverse().find((l) => l.startsWith('{'));
    if (!linha) throw new Error(`a CLI terminou sem o ${oQue} em JSON`);
    return JSON.parse(linha) as T;
  }
}
