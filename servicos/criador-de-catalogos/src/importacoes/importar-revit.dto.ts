import { Transform, Type } from 'class-transformer';
import { IsNumber, IsOptional, IsString, Max, MaxLength, Min } from 'class-validator';
import { LIMITES } from '@bim/base';

const trim = ({ value }: { value: unknown }) => (typeof value === 'string' ? value.trim() : value);

/**
 * Campos do `POST /importacoes/familias-revit` (multipart — tudo chega como texto). O arquivo é um
 * `.rfa` solto ou um `.zip` com as famílias, os type catalogs `.txt` e, quando houver, a geometria
 * irmã (`.ifc`/`.stp`/`.igs` de mesmo nome). A geometria de um `.rfa` não é legível fora do Revit;
 * sem arquivo irmão cada tipo recebe uma forma representativa por parâmetro
 * (`docs/conhecimento/revit-familias.md`).
 */
export class ImportarRevitDto {
  /** customUrl da empresa dona do catálogo; vazio = a primeira cadastrada */
  @IsOptional() @IsString() @Transform(trim) @MaxLength(LIMITES.customUrl) empresa?: string;

  /** título do catálogo (padrão: nome do arquivo enviado, sem extensão) */
  @IsOptional() @IsString() @Transform(trim) @MaxLength(LIMITES.texto) catalogo?: string;

  /** fabricante (padrão: o parâmetro Manufacturer mais frequente nas famílias) */
  @IsOptional() @IsString() @Transform(trim) @MaxLength(LIMITES.texto) fabricante?: string;

  /** trecho das formas representativas, em mm (100 ≤ x ≤ 20000; padrão 1000) */
  @IsOptional()
  @Type(() => Number)
  @IsNumber({ allowNaN: false, allowInfinity: false }, { message: '"comprimentoMm" deve ser um número em mm' })
  @Min(100, { message: '"comprimentoMm" deve ser pelo menos 100 mm' })
  @Max(20000, { message: '"comprimentoMm" deve ser no máximo 20000 mm' })
  comprimentoMm?: number;

  /** deflexão da tesselação da geometria irmã STEP/IGES, em mm (0 < x ≤ 10; padrão 0,2) */
  @IsOptional()
  @Type(() => Number)
  @IsNumber({ allowNaN: false, allowInfinity: false }, { message: '"deflexao" deve ser um número em mm' })
  @Min(0.0001, { message: '"deflexao" deve ser maior que 0' })
  @Max(10, { message: '"deflexao" deve ser no máximo 10 mm' })
  deflexao?: number;
}
