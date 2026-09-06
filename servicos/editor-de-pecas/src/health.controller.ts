import { Controller, Get, ServiceUnavailableException } from '@nestjs/common';
import { InjectConnection } from '@nestjs/mongoose';
import { Connection } from 'mongoose';

const READY_STATE: readonly string[] = ['desconectado', 'conectado', 'conectando', 'desconectando'];

/** GET /health — estado da conexão que o serviço realmente usa. */
@Controller()
export class HealthController {
  constructor(@InjectConnection() private readonly connection: Connection) {}

  @Get('health')
  async health() {
    const estado = READY_STATE[this.connection.readyState] ?? `readyState=${this.connection.readyState}`;
    if (this.connection.readyState !== 1 || !this.connection.db) {
      throw new ServiceUnavailableException(`Mongo ${estado} — o serviço está em retry; veja o README do serviço`);
    }
    const { version } = await this.connection.db.admin().command({ buildInfo: 1 });
    return { status: 'ok', servico: 'editor-de-pecas', mongo: version, conexao: estado, banco: this.connection.name };
  }
}
