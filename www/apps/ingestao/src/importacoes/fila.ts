/**
 * fila.ts — fila FIFO em processo com concorrência limitada (I11, 2026-09-05).
 *
 * As importações (`.aq` e CAD, ambas pelo pipeline Python) rodavam todas ao mesmo tempo:
 * dois uploads = dois Pythons + dois Chromiums disputando CPU e RAM, e nada dizia ao usuário
 * que ele estava esperando. Agora todo import passa por UMA instância desta fila
 * (`FILA_IMPORTACOES`), concorrência 1 por padrão (`IMPORTACOES_CONCORRENCIA` no env); a
 * regeneração de miniatura após edição tem a sua (`FILA_MINIATURAS`).
 *
 * É só em memória — a fila morre com o processo. O que estava na fila ou em execução
 * quando o serviço caiu é tratado pelo `RecuperacaoService` no boot (marca `falhou`).
 * Sem Nest aqui: testável direto em `tests/paridade/fila.mts`.
 */

export interface EntradaFila {
  nome: string;
  enfileiradaEm: number;
}

export class Fila {
  private readonly espera: Array<{ entrada: EntradaFila; iniciar: () => void }> = [];
  private ativos = 0;

  readonly concorrencia: number;

  // sem parameter property (`constructor(readonly x)`): o Node com strip-types não aceita, e o harness roda assim
  constructor(concorrencia = 1) {
    if (!Number.isInteger(concorrencia) || concorrencia < 1) {
      throw new Error(`concorrência da fila inválida: ${concorrencia}`);
    }
    this.concorrencia = concorrencia;
  }

  /** Quantos estão esperando (não conta os em execução). */
  get tamanho(): number {
    return this.espera.length;
  }

  get emExecucao(): number {
    return this.ativos;
  }

  /** Nomes dos que esperam, na ordem em que vão rodar. */
  get esperando(): string[] {
    return this.espera.map((e) => e.entrada.nome);
  }

  /**
   * Enfileira `fn`. `aoEsperar(posicao)` é chamado uma vez, na hora de entrar na fila, com
   * quantos estão na frente (0 = roda já) — o serviço usa para escrever "na fila" no import.
   * A promise devolvida segue a de `fn` (resolve ou rejeita igual); a fila nunca engole.
   */
  executar<T>(nome: string, fn: () => Promise<T>, aoEsperar?: (naFrente: number) => void): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      aoEsperar?.(this.ativos < this.concorrencia ? 0 : this.espera.length + this.ativos);
      const iniciar = () => {
        this.ativos++;
        // libera a vaga ANTES de resolver: quem espera a promise vê a fila já consistente
        const concluir = () => {
          this.ativos--;
          this.proximo();
        };
        Promise.resolve()
          .then(fn)
          .then(
            (v) => { concluir(); resolve(v); },
            (e) => { concluir(); reject(e); },
          );
      };
      if (this.ativos < this.concorrencia) iniciar();
      else this.espera.push({ entrada: { nome, enfileiradaEm: Date.now() }, iniciar });
    });
  }

  private proximo() {
    while (this.ativos < this.concorrencia && this.espera.length) {
      this.espera.shift()!.iniciar();
    }
  }
}

export const FILA_IMPORTACOES = 'FILA_IMPORTACOES';
export const FILA_MINIATURAS = 'FILA_MINIATURAS';

/** Lê `IMPORTACOES_CONCORRENCIA` (padrão 1) — inválido derruba o boot, como `PORT`. */
export function concorrenciaDoEnv(env: NodeJS.ProcessEnv = process.env): number {
  const bruto = env.IMPORTACOES_CONCORRENCIA;
  if (bruto === undefined || bruto === '') return 1;
  const n = Number(bruto);
  if (!Number.isInteger(n) || n < 1 || n > 8) {
    throw new Error(`IMPORTACOES_CONCORRENCIA inválida: ${JSON.stringify(bruto)} — use um inteiro entre 1 e 8`);
  }
  return n;
}
