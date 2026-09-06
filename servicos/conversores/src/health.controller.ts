import { Controller, Get } from '@nestjs/common';
import { Biblioteca } from '@bim/base';

@Controller()
export class HealthController {
  constructor(private readonly biblioteca: Biblioteca) {}

  @Get('health')
  health() {
    return { status: 'ok', servico: 'conversores', biblioteca: this.biblioteca.dir };
  }
}
