import { Transform, Type } from 'class-transformer';
import { IsEmail, IsInt, IsNotEmpty, IsNumber, IsOptional, IsString, IsUrl, Matches, Max, MaxLength, Min } from 'class-validator';
import { LIMITES } from '@bim/dominio';

const trim = ({ value }: { value: unknown }) => (typeof value === 'string' ? value.trim() : value);

/**
 * Campos do `POST /importacoes/plugin-autocad` (multipart — tudo chega como texto). O arquivo é a
 * DLL do plugin (`@UploadedFile()`); dela sai o host do catálogo web (`catallog.py inspecionar`),
 * que `host` pode sobrepor quando o mesmo catálogo vive em outro domínio (a Tupy tem
 * `tupycad.catallog.digital` na DLL e `conexoes.tupy.com.br` com mais grupos).
 *
 * Os cinco campos do lead são os do formulário de download do site (nome, e-mail, telefone,
 * empresa, cargo): são enviados ao catálogo uma vez por arquivo, como o navegador faz, e NÃO são
 * gravados no Mongo — vão num JSON temporário para o `catallog.py` e o arquivo é apagado.
 */
export class ImportarPluginDto {
  /** customUrl da empresa dona do catálogo; vazio = a primeira cadastrada */
  @IsOptional() @IsString() @Transform(trim) @MaxLength(LIMITES.customUrl) empresa?: string;

  /** host do catálogo web (https://…); vazio = o que está na DLL */
  @IsOptional() @IsString() @Transform(trim) @MaxLength(LIMITES.texto)
  @IsUrl({ protocols: ['https'], require_protocol: true }, { message: '"host" deve ser uma URL https' })
  host?: string;

  /** slug da categoria do catálogo (ex. tupygrooved-173) — `inspecionar` lista as opções */
  @IsString() @Transform(trim) @IsNotEmpty({ message: '"categoria" é obrigatória' }) @MaxLength(LIMITES.texto)
  @Matches(/^[a-z0-9][a-z0-9-]*$/i, { message: '"categoria" deve ser o slug (letras, números e hífen)' })
  categoria: string;

  /** produtos por grupo com IGES baixado: 1 = o primeiro (padrão), -1 = todos, 0 = nenhum */
  @IsOptional()
  @Type(() => Number)
  @IsInt({ message: '"igsPorGrupo" deve ser inteiro' })
  @Min(-1, { message: '"igsPorGrupo" deve ser -1 (todos), 0 ou um positivo' })
  @Max(50, { message: '"igsPorGrupo" deve ser no máximo 50' })
  igsPorGrupo?: number;

  /** deflexão da tesselação em mm (0 < x ≤ 10; padrão 0,2) */
  @IsOptional()
  @Type(() => Number)
  @IsNumber({ allowNaN: false, allowInfinity: false }, { message: '"deflexao" deve ser um número em mm' })
  @Min(0.0001, { message: '"deflexao" deve ser maior que 0' })
  @Max(10, { message: '"deflexao" deve ser no máximo 10 mm' })
  deflexao?: number;

  // ── formulário de download do catálogo (lead) ──
  @IsString() @Transform(trim) @IsNotEmpty({ message: '"fullName" (nome) é obrigatório' }) @MaxLength(LIMITES.texto) fullName: string;
  @IsString() @Transform(trim) @IsEmail({}, { message: '"email" inválido' }) @MaxLength(LIMITES.texto) email: string;
  @IsString() @Transform(trim) @IsNotEmpty({ message: '"mobile" (telefone) é obrigatório' }) @MaxLength(LIMITES.texto) mobile: string;
  @IsString() @Transform(trim) @IsNotEmpty({ message: '"company" (empresa) é obrigatória' }) @MaxLength(LIMITES.texto) company: string;
  @IsString() @Transform(trim) @IsNotEmpty({ message: '"position" (cargo) é obrigatório' }) @MaxLength(LIMITES.texto) position: string;
}
