import { Body, Controller, HttpCode, Post } from '@nestjs/common';
import { IsNotEmpty, IsString, MaxLength } from 'class-validator';
import { MiniaturasService } from './miniaturas.service';

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
 * O editor de peças chama depois de `PUT /geometrias/:id` e de `restaurar` (ADR-006): o editor não
 * tem Chromium. O resultado vai para o produto (`thumbKey`, `thumbAtualizadaEm` ou `thumbErro`).
 */
@Controller('miniaturas')
export class MiniaturasController {
  constructor(private readonly miniaturas: MiniaturasService) {}

  @Post('regerar')
  @HttpCode(202)
  regerar(@Body() body: RegerarMiniaturaDto) {
    return this.miniaturas.regerarMiniatura(body.productId);
  }
}
