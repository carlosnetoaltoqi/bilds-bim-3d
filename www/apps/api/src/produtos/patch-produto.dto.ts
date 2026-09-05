import { Transform } from 'class-transformer';
import { IsNotEmpty, IsNumber, IsOptional, IsString, MaxLength, ValidateIf } from 'class-validator';
import { IsCurva, IsSpecs, LIMITES } from '@bim/dominio';

/**
 * Corpo do `PATCH /produtos/:id` (I16). Só os campos presentes são alterados; `null`
 * em `curva`, `potencia` e `conexoes` apaga. Qualquer outro campo → 400.
 */
export class PatchProdutoDto {
  @IsOptional()
  @IsString({ message: '"nome" deve ser texto' })
  @Transform(({ value }) => (typeof value === 'string' ? value.trim() : value))
  @IsNotEmpty({ message: '"nome" não pode ser vazio' })
  @MaxLength(LIMITES.texto, { message: `"nome" passa de ${LIMITES.texto} caracteres` })
  nome?: string;

  @IsOptional()
  @IsString({ message: '"serie" deve ser texto' })
  @Transform(({ value }) => (typeof value === 'string' ? value.trim() : value))
  @MaxLength(LIMITES.texto, { message: `"serie" passa de ${LIMITES.texto} caracteres` })
  serie?: string;

  @IsOptional()
  @IsSpecs()
  specs?: Record<string, string | number | boolean | null>;

  @IsOptional()
  @ValidateIf((_, v) => v !== null)
  @IsCurva()
  curva?: number[][] | null;

  @IsOptional()
  @ValidateIf((_, v) => v !== null)
  @IsNumber({ allowNaN: false, allowInfinity: false }, { message: '"potencia" deve ser número ou null' })
  potencia?: number | null;

  @IsOptional()
  @ValidateIf((_, v) => v !== null)
  @IsString({ message: '"conexoes" deve ser texto ou null' })
  @MaxLength(LIMITES.textoLongo, { message: `"conexoes" passa de ${LIMITES.textoLongo} caracteres` })
  conexoes?: string | null;
}
