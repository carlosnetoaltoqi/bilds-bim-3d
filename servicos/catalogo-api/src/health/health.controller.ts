import { Controller, Get, ServiceUnavailableException } from '@nestjs/common';
import { InjectConnection } from '@nestjs/mongoose';
import { Connection } from 'mongoose';

/**
 * GET /health — estado da conexão que a API realmente usa (I12, 2026-09-05).
 *
 * Até então abria um `MongoClient` novo do pacote `mongodb@6` a cada chamada — um
 * segundo driver ao lado do que o `mongoose@9` embute (mongodb 7), e um health que
 * dizia "ok" mesmo com o Mongoose da API em retry. Agora responde pela conexão do
 * `MongooseModule`: desconectado → 503 com o `readyState`; conectado → versão do
 * servidor via `buildInfo`.
 */
const READY_STATE: readonly string[] = ['desconectado', 'conectado', 'conectando', 'desconectando'];

@Controller()
export class HealthController {
  constructor(@InjectConnection() private readonly connection: Connection) {}

  @Get('health')
  async health() {
    const estado = READY_STATE[this.connection.readyState] ?? `readyState=${this.connection.readyState}`;
    if (this.connection.readyState !== 1 || !this.connection.db) {
      throw new ServiceUnavailableException(`Mongo ${estado} — a API está em retry; veja o README do serviço, "A API não sobe e o Mongoose culpa o whitelist"`);
    }
    const { version } = await this.connection.db.admin().command({ buildInfo: 1 });
    return { status: 'ok', mongo: version, conexao: estado, banco: this.connection.name };
  }
}
