/**
 * worker-ipc.ts — espera pelos processos filhos (parse-worker e thumb-worker) sem
 * engolir nada (I15, 2026-09-05).
 *
 * Até a S7.10 o ImportacoesService fazia isso inline e tinha três buracos:
 *   - o `type:'error'` do thumb-worker era ignorado (nem log, nem contagem);
 *   - um filho que saía com código 0 sem ter enviado mensagem deixava a promise
 *     presa (no parse-worker até o timeout de 5 min; no thumb-worker para sempre);
 *   - os chamadores faziam `.catch(() => {})` na geração de miniaturas.
 *
 * Este módulo não conhece Nest nem Mongo — recebe qualquer EventEmitter com a cara
 * de um ChildProcess (`on`, `kill`) — para poder ser testado com um filho falso em
 * `tests/paridade/worker_ipc.mts`. Regras:
 *   - a promise sempre se resolve ou rejeita uma única vez;
 *   - `exit` antes do resultado é erro, com o código/sinal na mensagem, mesmo se 0;
 *   - timeout mata o filho com SIGKILL e rejeita;
 *   - nenhuma falha individual é descartada: o thumb-worker devolve um resumo com
 *     cada `productId` que falhou e a mensagem.
 */

import type { EventEmitter } from 'node:events';

/** O que precisamos de um `ChildProcess` — o suficiente para simular nos testes. */
export interface FilhoIpc extends EventEmitter {
  kill(signal?: NodeJS.Signals | number): boolean;
}

function descreveSaida(code: number | null, signal: string | null): string {
  if (signal) return `pelo sinal ${signal}`;
  return `com código ${code}`;
}

/**
 * Espera a única mensagem de resultado de um worker "uma pergunta, uma resposta"
 * (o parse-worker). Resolve na primeira mensagem; rejeita em `error`, em `exit`
 * antes da mensagem (qualquer código) e em timeout (mata com SIGKILL).
 */
export function aguardarResultado<R>(child: FilhoIpc, nome: string, timeoutMs: number): Promise<R> {
  return new Promise<R>((resolve, reject) => {
    let encerrado = false;
    const timer = setTimeout(() => {
      if (encerrado) return;
      encerrado = true;
      child.kill('SIGKILL');
      reject(new Error(`${nome} não respondeu em ${timeoutMs / 1000}s — morto com SIGKILL`));
    }, timeoutMs);

    const fim = (fn: () => void) => {
      if (encerrado) return;
      encerrado = true;
      clearTimeout(timer);
      fn();
    };

    child.on('message', (msg: R) => fim(() => resolve(msg)));
    child.on('error', (err: Error) => fim(() => reject(new Error(`${nome}: ${err.message}`))));
    child.on('exit', (code: number | null, signal: string | null) =>
      fim(() => reject(new Error(`${nome} encerrou ${descreveSaida(code, signal)} sem enviar resultado`))),
    );
  });
}

export interface FalhaMiniatura {
  productId: string;
  message: string;
}

export interface ResumoMiniaturas {
  total: number;
  geradas: number;
  falhas: FalhaMiniatura[];
}

export interface GanchosMiniaturas {
  /** Chamado a cada miniatura gravada pelo filho; se rejeitar, vira uma falha do produto. */
  onMiniatura?: (productId: string, thumbKey: string) => Promise<void> | void;
  /** Chamado a cada `type:'error'` do filho — para logar na hora, não só no fim. */
  onFalha?: (productId: string, message: string) => void;
}

/** Protocolo do thumb-worker (espelho de `ThumbWorkerMessage`, sem importar o worker). */
type MensagemMiniatura =
  | { type: 'thumb'; productId: string; thumbKey: string }
  | { type: 'done'; count: number }
  | { type: 'error'; productId: string; message: string };

/**
 * Acompanha o thumb-worker até o `done`. Resolve com o resumo (geradas + cada falha);
 * rejeita se o filho sair antes do `done` (com o resumo parcial em `err.resumo`), em
 * `error` do processo, ou se ficar `ociosoMs` sem mandar mensagem (mata com SIGKILL —
 * um Chromium travado não sai sozinho).
 */
export function aguardarMiniaturas(
  child: FilhoIpc,
  total: number,
  ganchos: GanchosMiniaturas = {},
  ociosoMs = 2 * 60 * 1000,
): Promise<ResumoMiniaturas> {
  return new Promise<ResumoMiniaturas>((resolve, reject) => {
    const resumo: ResumoMiniaturas = { total, geradas: 0, falhas: [] };
    const pendentes: Promise<void>[] = [];
    let encerrado = false;
    let timer: NodeJS.Timeout | undefined;

    const rejeitar = (mensagem: string) => {
      const err = new Error(mensagem) as Error & { resumo: ResumoMiniaturas };
      err.resumo = resumo;
      reject(err);
    };

    const armarOcioso = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        if (encerrado) return;
        encerrado = true;
        child.kill('SIGKILL');
        rejeitar(
          `thumb-worker sem mensagens há ${ociosoMs / 1000}s — morto com SIGKILL após ` +
            `${resumo.geradas}/${total} miniaturas e ${resumo.falhas.length} falha(s)`,
        );
      }, ociosoMs);
    };

    const fim = (fn: () => void) => {
      if (encerrado) return;
      encerrado = true;
      if (timer) clearTimeout(timer);
      fn();
    };

    armarOcioso();

    child.on('message', (msg: MensagemMiniatura) => {
      if (encerrado) return;
      armarOcioso();
      if (msg.type === 'thumb') {
        resumo.geradas++;
        pendentes.push(
          Promise.resolve()
            .then(() => ganchos.onMiniatura?.(msg.productId, msg.thumbKey))
            .then(
              () => undefined,
              (err: any) => {
                // a imagem existe mas o produto não aponta para ela — é falha do produto
                resumo.geradas--;
                resumo.falhas.push({ productId: msg.productId, message: `gravar thumbKey: ${err?.message ?? err}` });
                ganchos.onFalha?.(msg.productId, `gravar thumbKey: ${err?.message ?? err}`);
              },
            ),
        );
      } else if (msg.type === 'error') {
        resumo.falhas.push({ productId: msg.productId, message: msg.message });
        ganchos.onFalha?.(msg.productId, msg.message);
      } else if (msg.type === 'done') {
        fim(() => {
          Promise.all(pendentes).then(() => resolve(resumo));
        });
      }
    });

    child.on('error', (err: Error) => fim(() => rejeitar(`thumb-worker: ${err.message}`)));
    child.on('exit', (code: number | null, signal: string | null) =>
      fim(() =>
        rejeitar(
          `thumb-worker encerrou ${descreveSaida(code, signal)} antes do 'done' — ` +
            `${resumo.geradas}/${total} miniaturas e ${resumo.falhas.length} falha(s)`,
        ),
      ),
    );
  });
}

/** Uma linha para o `note` do import e para o log. */
export function descreveResumo(r: ResumoMiniaturas): string {
  if (r.falhas.length === 0) return `miniaturas: ${r.geradas}/${r.total} geradas`;
  const primeira = r.falhas[0];
  return (
    `miniaturas: ${r.geradas}/${r.total} geradas, ${r.falhas.length} falha(s) — ` +
    `${primeira.productId}: ${primeira.message}` +
    (r.falhas.length > 1 ? ` (+${r.falhas.length - 1})` : '')
  );
}
