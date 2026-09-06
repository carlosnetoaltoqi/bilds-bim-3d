/**
 * processo.ts — roda um processo filho (uma CLI da biblioteca Python ou o `thumbs.mjs`) e NÃO engole
 * como ele morre. Herdeiro do `worker-ipc.ts` (I15/I29), sem `fork`/IPC:
 *
 *   - saída ≠ 0 (ou fora de `aceitarCodigos`), sinal, `error` do spawn, timeout total e
 *     ociosidade (sem nenhuma linha por `ociosoMs`) viram `ProcessoError` com o motivo e
 *     as últimas linhas do stderr — nada de promise presa;
 *   - cada linha de stdout/stderr vai para `onStdout`/`onStderr` na hora (progresso do
 *     Python, uma miniatura por linha no thumbs.mjs);
 *   - o stdin do filho fica em pipe e aberto: se ESTE processo morrer (inclusive SIGKILL),
 *     o pipe fecha e o filho para sozinho (`processo.py:vigiar_stdin`, `sairComStdin` do
 *     thumbs.mjs) — o que o `disconnect` do IPC fazia.
 *
 * Sem Nest aqui: testável direto (tests/paridade/processo.mts). Vive em @bim/base porque todo serviço
 * que chega à biblioteca passa por aqui (regra 2 de docs/arquitetura.md §3).
 */
import { spawn } from 'node:child_process';
import * as path from 'node:path';

export interface OpcoesProcesso {
  /** nome nas mensagens (padrão: basename do comando) */
  nome?: string;
  cwd?: string;
  env?: NodeJS.ProcessEnv;
  /** tempo total; padrão 30 min */
  timeoutMs?: number;
  /** sem NENHUMA linha de saída por este tempo = travado (Chromium, OCP); padrão 0 = não vigia */
  ociosoMs?: number;
  /** códigos de saída que contam como sucesso; padrão [0] */
  aceitarCodigos?: number[];
  onStdout?: (linha: string) => void;
  onStderr?: (linha: string) => void;
  /** guardar o stdout inteiro no resultado (até 16 MB); padrão true */
  guardarStdout?: boolean;
}

export type MotivoFalha = 'saida' | 'sinal' | 'timeout' | 'ocioso' | 'spawn';

export class ProcessoError extends Error {
  readonly motivo: MotivoFalha;
  readonly code: number | null;
  readonly signal: NodeJS.Signals | null;
  readonly stderr: string;

  // sem parameter property (`constructor(readonly x)`): o Node com strip-types não aceita, e o harness roda assim
  constructor(message: string, motivo: MotivoFalha, code: number | null, signal: NodeJS.Signals | null, stderr: string) {
    super(message);
    this.name = 'ProcessoError';
    this.motivo = motivo;
    this.code = code;
    this.signal = signal;
    this.stderr = stderr;
  }
}

export interface ResultadoProcesso {
  code: number;
  stdout: string;
  stderr: string;
  ms: number;
}

const STDOUT_MAX = 16 * 1024 * 1024;
const STDERR_LINHAS = 200;

export function descreveSaida(code: number | null, signal: NodeJS.Signals | null): string {
  return signal ? `morreu com ${signal}` : `saiu com código ${code}`;
}

export function executar(cmd: string, args: string[], opts: OpcoesProcesso = {}): Promise<ResultadoProcesso> {
  const nome = opts.nome ?? path.basename(cmd);
  const timeoutMs = opts.timeoutMs ?? 30 * 60 * 1000;
  const ociosoMs = opts.ociosoMs ?? 0;
  const aceitar = opts.aceitarCodigos ?? [0];
  const guardar = opts.guardarStdout ?? true;

  return new Promise<ResultadoProcesso>((resolve, reject) => {
    const t0 = Date.now();
    let child;
    try {
      child = spawn(cmd, args, { cwd: opts.cwd, env: opts.env ?? process.env, stdio: ['pipe', 'pipe', 'pipe'] });
    } catch (e: any) {
      reject(new ProcessoError(`${nome}: ${e?.message ?? e}`, 'spawn', null, null, ''));
      return;
    }
    const stderrLinhas: string[] = [];
    let stdout = '';
    let terminou = false;
    let motivoKill: 'timeout' | 'ocioso' | null = null;
    let tOcioso: NodeJS.Timeout | undefined;

    const matar = (motivo: 'timeout' | 'ocioso') => {
      if (terminou) return;
      motivoKill = motivo;
      child.kill('SIGKILL');
    };
    const tTotal = setTimeout(() => matar('timeout'), timeoutMs);
    const rearmar = () => {
      if (!ociosoMs) return;
      clearTimeout(tOcioso);
      tOcioso = setTimeout(() => matar('ocioso'), ociosoMs);
    };
    rearmar();

    const porLinha = (stream: NodeJS.ReadableStream, cb: (l: string) => void) => {
      let resto = '';
      stream.setEncoding('utf8');
      stream.on('data', (chunk: string) => {
        rearmar();
        resto += chunk;
        const linhas = resto.split('\n');
        resto = linhas.pop() ?? '';
        for (const l of linhas) cb(l);
      });
      stream.on('end', () => { if (resto) cb(resto); });
    };
    porLinha(child.stdout, (l) => {
      if (guardar && stdout.length < STDOUT_MAX) stdout += l + '\n';
      opts.onStdout?.(l);
    });
    porLinha(child.stderr, (l) => {
      const limpa = l.replace(/\x1b\[[0-9;]*m/g, '');
      stderrLinhas.push(limpa);
      if (stderrLinhas.length > STDERR_LINHAS) stderrLinhas.shift();
      opts.onStderr?.(limpa);
    });

    // o filho pode fechar o stdin antes de nós (EPIPE) — não é erro nosso
    child.stdin.on('error', () => {});

    const fim = (fn: () => void) => {
      if (terminou) return;
      terminou = true;
      clearTimeout(tTotal);
      clearTimeout(tOcioso);
      fn();
    };

    child.on('error', (err: Error) => fim(() => reject(new ProcessoError(`${nome}: ${err.message}`, 'spawn', null, null, stderrLinhas.join('\n')))));
    child.on('close', (code: number | null, signal: NodeJS.Signals | null) => fim(() => {
      const stderr = stderrLinhas.join('\n');
      if (motivoKill === 'timeout') {
        reject(new ProcessoError(`${nome} excedeu ${Math.round(timeoutMs / 1000)}s — morto com SIGKILL`, 'timeout', code, signal, stderr));
        return;
      }
      if (motivoKill === 'ocioso') {
        reject(new ProcessoError(`${nome} sem saída há ${Math.round(ociosoMs / 1000)}s — morto com SIGKILL`, 'ocioso', code, signal, stderr));
        return;
      }
      if (code !== null && aceitar.includes(code)) {
        resolve({ code, stdout, stderr, ms: Date.now() - t0 });
        return;
      }
      const detalhe = stderrLinhas.filter((l) => l.trim()).slice(-6).join('\n');
      reject(new ProcessoError(
        `${nome} ${descreveSaida(code, signal)}${detalhe ? `:\n${detalhe}` : ''}`,
        signal ? 'sinal' : 'saida', code, signal, stderr,
      ));
    }));
  });
}
