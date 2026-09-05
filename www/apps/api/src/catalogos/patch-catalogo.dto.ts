import { Transform } from 'class-transformer';
import { IsIn, IsNotEmpty, IsOptional, IsString, MaxLength } from 'class-validator';
import { LIMITES } from '../common/validation';

/** Corpo do `PATCH /catalogos/:catalogId` (I16): título, fabricante e layout. */
export class PatchCatalogoDto {
  @IsOptional()
  @IsString({ message: '"title" deve ser texto' })
  @Transform(({ value }) => (typeof value === 'string' ? value.trim() : value))
  @IsNotEmpty({ message: '"title" não pode ser vazio' })
  @MaxLength(LIMITES.texto, { message: `"title" passa de ${LIMITES.texto} caracteres` })
  title?: string;

  @IsOptional()
  @IsString({ message: '"manufacturer" deve ser texto' })
  @Transform(({ value }) => (typeof value === 'string' ? value.trim() : value))
  @IsNotEmpty({ message: '"manufacturer" não pode ser vazio' })
  @MaxLength(LIMITES.texto, { message: `"manufacturer" passa de ${LIMITES.texto} caracteres` })
  manufacturer?: string;

  @IsOptional()
  @IsIn(['series-rows', 'catalog-grid'], { message: '"layout" deve ser "series-rows" ou "catalog-grid"' })
  layout?: 'series-rows' | 'catalog-grid';
}
