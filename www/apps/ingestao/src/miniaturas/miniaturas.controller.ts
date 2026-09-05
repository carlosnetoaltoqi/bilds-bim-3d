import { Body, Controller, HttpCode, Post } from '@nestjs/common';
import { IsNotEmpty, IsString, MaxLength } from 'class-validator';
import { ImportacoesService } from '../importacoes/importacoes.service';

/** Corpo do `POST /miniaturas/regerar`. */
export class RegerarMiniaturaDto {
  @IsString({ message: '"productId" deve ser texto' })
  @IsNotEmpty({ message: 'campo "productId" obrigatório' })
  @MaxLength(64)
  productId: string;
}

/**
 * POST /miniaturas/regerar {productId} → 202 { productId, naFrente }
 *
 * A API de catálogo chama depois de `PUT /geometrias/:id` e de `restaurar` (A6): a API não
 * tem Chromium. O resultado vai para o produto (`thumbKey`, `thumbAtualizadaEm` ou `thumbErro`).
 */
@Controller('miniaturas')
export class MiniaturasController {
  constructor(private readonly importacoes: ImportacoesService) {}

  @Post('regerar')
  @HttpCode(202)
  regerar(@Body() body: RegerarMiniaturaDto) {
    return this.importacoes.regerarMiniatura(body.productId);
  }
}
