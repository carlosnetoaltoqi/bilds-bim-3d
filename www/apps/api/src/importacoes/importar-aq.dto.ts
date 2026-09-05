import { Transform } from 'class-transformer';
import { IsOptional, IsString, MaxLength } from 'class-validator';
import { LIMITES } from '../common/validation';

/** Campos de formulário do `POST /importacoes` (multipart). O arquivo é o `@UploadedFile()`. */
export class ImportarAqDto {
  /** customUrl da empresa dona do catálogo; vazio = a primeira cadastrada */
  @IsOptional()
  @IsString()
  @Transform(({ value }) => (typeof value === 'string' ? value.trim() : value))
  @MaxLength(LIMITES.customUrl)
  empresa?: string;
}
