import { CanActivate, ExecutionContext, Injectable, ServiceUnavailableException } from '@nestjs/common';
import { InjectConnection } from '@nestjs/mongoose';
import { Connection } from 'mongoose';

/**
 * MongoProntoGuard — I32 (2026-09-05). Com o Mongo fora (Atlas bloqueado, rede, cluster
 * pausado) toda rota que consulta a base esperava os 30 s do `serverSelectionTimeoutMS` do
 * driver e respondia `500 Internal server error`; só `/health` sabia dizer 503 na hora. Este
 * guard, registrado como `APP_GUARD` na API e no serviço de ingestão, recusa com **503 imediato**
 * qualquer requisição enquanto a conexão do Mongoose não está em `readyState === 1`, exceto as
 * rotas de `ROTAS_SEM_MONGO` (o próprio `/health`, que explica o estado).
 *
 * Por que guard e não `bufferCommands: false`: o guard dá uma mensagem única e acionável e
 * não muda o comportamento do Mongoose nas reconexões curtas (o buffer continua absorvendo
 * um piscar de conexão no meio de uma requisição que já passou).
 */
export const ROTAS_SEM_MONGO: readonly string[] = ['/health'];

const READY_STATE: readonly string[] = ['desconectado', 'conectado', 'conectando', 'desconectando'];

/** Lógica pura, testável sem Nest: null = pode seguir; string = motivo do 503. */
export function motivoMongoIndisponivel(readyState: number, caminho: string): string | null {
  const rota = caminho.split('?')[0].replace(/\/+$/, '') || '/';
  if (ROTAS_SEM_MONGO.includes(rota)) return null;
  if (readyState === 1) return null;
  const estado = READY_STATE[readyState] ?? `readyState=${readyState}`;
  return `Mongo ${estado} — o serviço está em retry e não pode atender ${rota} agora; veja GET /health e www/README.md, "A API não sobe e o Mongoose culpa o whitelist"`;
}

@Injectable()
export class MongoProntoGuard implements CanActivate {
  constructor(@InjectConnection() private readonly connection: Connection) {}

  canActivate(ctx: ExecutionContext): boolean {
    const req = ctx.switchToHttp().getRequest<{ url?: string; path?: string }>();
    const motivo = motivoMongoIndisponivel(this.connection.readyState, req?.path ?? req?.url ?? '/');
    if (motivo) throw new ServiceUnavailableException(motivo);
    return true;
  }
}
