import { Controller, Get } from '@nestjs/common';
import { Biblioteca } from '@bim/base';

/** GET /health — só confere que a biblioteca está onde deve (não há banco para conferir). */
@Controller()
export class HealthController {
  constructor(private readonly biblioteca: Biblioteca) {}

  @Get('health')
  health() {
    return { status: 'ok', servico: 'gerador-zip', biblioteca: this.biblioteca.dir };
  }
}
