import { Injectable, Logger } from '@nestjs/common';

/**
 * Cliente da API para o serviço de ingestão (apps/ingestao). A ÚNICA leitura de
 * `INGESTAO_URL` na API (mesma regra do I17 para `PORT`/`STORAGE_PATH`).
 *
 * Hoje só um uso: depois de `PUT /geometrias/:id` ou `restaurar`, pedir a miniatura nova
 * (A6 de docs/arquitetura-www-servico-de-ingestao.md — a API não tem Chromium nem Python).
 * Nunca rejeita: o chamador registra `thumbErro` no produto quando o serviço não responde.
 */
export const INGESTAO_URL_PADRAO = 'http://localhost:4100';

export function ingestaoUrl(env: NodeJS.ProcessEnv = process.env): string {
  return (env.INGESTAO_URL ?? INGESTAO_URL_PADRAO).replace(/\/+$/, '');
}

export interface RespostaIngestao {
  ok: boolean;
  erro?: string;
}

@Injectable()
export class IngestaoClient {
  private readonly logger = new Logger(IngestaoClient.name);
  readonly base = ingestaoUrl();

  /** `POST /miniaturas/regerar {productId}` — 202 quando entrou na fila do serviço. */
  async regerarMiniatura(productId: string): Promise<RespostaIngestao> {
    return this.post('/miniaturas/regerar', { productId });
  }

  private async post(rota: string, corpo: unknown): Promise<RespostaIngestao> {
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
        return { ok: false, erro: `serviço de ingestão respondeu ${res.status} em ${rota}${texto ? ` — ${texto}` : ''}` };
      }
      return { ok: true };
    } catch (e: any) {
      const erro = `serviço de ingestão indisponível em ${this.base} — ${e?.message ?? e}`;
      this.logger.warn(erro);
      return { ok: false, erro };
    }
  }
}
