import { Transform } from 'class-transformer';
import { IsNotEmpty, IsString, MaxLength } from 'class-validator';
import { LIMITES } from '@bim/base';

/** Campos de formulário do `POST /empresas` (multipart: `name`, `customUrl`, arquivo `logo`). */
export class CriarEmpresaDto {
  @IsString({ message: '"name" deve ser texto' })
  @Transform(({ value }) => (typeof value === 'string' ? value.trim() : value))
  @IsNotEmpty({ message: 'campo "name" obrigatório' })
  @MaxLength(LIMITES.texto, { message: `"name" passa de ${LIMITES.texto} caracteres` })
  name: string;

  /** Vira o segmento da URL pública; o controller ainda normaliza para minúsculas e hífens. */
  @IsString({ message: '"customUrl" deve ser texto' })
  @Transform(({ value }) => (typeof value === 'string' ? value.trim() : value))
  @IsNotEmpty({ message: 'campo "customUrl" obrigatório' })
  @MaxLength(LIMITES.customUrl, { message: `"customUrl" passa de ${LIMITES.customUrl} caracteres` })
  customUrl: string;
}
