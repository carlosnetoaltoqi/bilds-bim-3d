import { Transform, Type } from 'class-transformer';
import {
  ArrayMaxSize,
  IsArray,
  IsNotEmpty,
  IsOptional,
  IsString,
  MaxLength,
  ValidateIf,
  ValidateNested,
} from 'class-validator';
import { IsSpecs } from '@bim/dominio';
import { LIMITES } from '@bim/base';

const trim = ({ value }: { value: unknown }) => (typeof value === 'string' ? value.trim() : value);

/** Metadados da peça para o `.aq` gerado (`POST /exportar/aq`). Tudo opcional. */
export class AqInfoDto {
  @IsOptional() @IsString() @Transform(trim) @MaxLength(LIMITES.texto) fabricante?: string;
  @IsOptional() @IsString() @Transform(trim) @MaxLength(LIMITES.texto) linha?: string;
  @IsOptional() @IsString() @Transform(trim) @MaxLength(LIMITES.texto) nome?: string;
  @IsOptional() @IsString() @Transform(trim) @MaxLength(LIMITES.textoLongo) descricao?: string;
  @IsOptional() @IsString() @Transform(trim) @MaxLength(LIMITES.texto) codigo?: string;
  @IsOptional() @IsSpecs() specs?: Record<string, string | number | boolean | null>;
  @IsOptional() @IsString() @Transform(trim) @MaxLength(LIMITES.textoLongo) origem?: string;
}

/**
 * Uma parte do editor. Os arrays só são conferidos como arrays aqui — os números (milhões
 * deles) passam pelo `validateGeoBuffers` no controller, num loop simples.
 */
export class AqParteDto {
  @IsString({ message: '"partes[].nome" deve ser texto' })
  @Transform(trim)
  @IsNotEmpty({ message: '"partes[].nome" não pode ser vazio' })
  @MaxLength(LIMITES.texto)
  nome: string;

  @IsArray({ message: '"partes[].pos" deve ser array' })
  pos: number[];

  @IsOptional()
  @ValidateIf((_, v) => v !== null)
  @IsArray({ message: '"partes[].col" deve ser array ou null' })
  col?: number[] | null;

  @IsArray({ message: '"partes[].idx" deve ser array' })
  idx: number[];
}

/** Corpo do `POST /exportar/aq`: `info` + `partes`, ou `info` + um único `{pos,col,idx}`. */
export class ExportarAqDto {
  @IsOptional()
  @ValidateNested()
  @Type(() => AqInfoDto)
  info?: AqInfoDto;

  @IsOptional()
  @IsArray({ message: '"partes" deve ser array' })
  @ArrayMaxSize(LIMITES.partes, { message: `"partes" passa de ${LIMITES.partes} itens` })
  @ValidateNested({ each: true })
  @Type(() => AqParteDto)
  partes?: AqParteDto[];

  @IsOptional() @IsArray() pos?: number[];
  @IsOptional() @IsArray() col?: number[];
  @IsOptional() @IsArray() idx?: number[];
}
