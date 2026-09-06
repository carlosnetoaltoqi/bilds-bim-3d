import { Injectable, Logger } from '@nestjs/common';

/**
 * Cliente do editor para o CRIADOR DE CATÁLOGOS. A ÚNICA leitura de `CRIADOR_URL` no editor.
 *
 * Um uso: depois de `PUT /geometrias/:id` ou `restaurar`, pedir a miniatura nova (ADR-006 — o editor
 * não tem Chromium nem Python). Nunca rejeita: o chamador registra `thumbErro` no produto quando o
 * criador não responde.
 */
export const CRIADOR_URL_PADRAO = 'http://localhost:4100';

export function criadorUrl(env: NodeJS.ProcessEnv = process.env): string {
  return (env.CRIADOR_URL ?? CRIADOR_URL_PADRAO).replace(/\/+$/, '');
}

export interface RespostaCriador {
  ok: boolean;
  erro?: string;
}

@Injectable()
export class CriadorClient {
  private readonly logger = new Logger(CriadorClient.name);
  readonly base = criadorUrl();

  /** `POST /miniaturas/regerar {productId}` — 202 quando entrou na fila do criador. */
  async regerarMiniatura(productId: string): Promise<RespostaCriador> {
    return this.post('/miniaturas/regerar', { productId });
  }

  private async post(rota: string, corpo: unknown): Promise<RespostaCriador> {
    const url = `${this.base}${rota}`;
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(corpo),
        signal: AbortSignal.timeout(10_000),
      });
      if (!res.ok) {
        const texto = (await res.text().catch(() => '')).slice(0, 300);
        return { ok: false, erro: `criador de catálogos respondeu ${res.status} em ${rota}${texto ? ` — ${texto}` : ''}` };
      }
      return { ok: true };
    } catch (e: any) {
      const erro = `criador de catálogos indisponível em ${this.base} — ${e?.message ?? e}`;
      this.logger.warn(erro);
      return { ok: false, erro };
    }
  }
}
