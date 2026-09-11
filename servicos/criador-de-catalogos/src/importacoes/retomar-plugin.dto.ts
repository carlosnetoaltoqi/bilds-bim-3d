import { Transform } from 'class-transformer';
import { IsEmail, IsNotEmpty, IsString, MaxLength } from 'class-validator';
import { LIMITES } from '@bim/base';

const trim = ({ value }: { value: unknown }) => (typeof value === 'string' ? value.trim() : value);

/**
 * Campos do `POST /importacoes/:importId/retomar` — **só o lead**.
 *
 * Host, categoria, disciplina e as opções de conversão vêm da `origem` gravada na importação que
 * falhou, e a DLL não é pedida de novo: o host já é conhecido. O lead, ao contrário, nunca é
 * gravado (é dado pessoal do formulário do fabricante, enviado uma vez por arquivo baixado), então
 * quem retoma decide entregá-lo outra vez — é essa decisão que a tela pede.
 */
export class RetomarPluginDto {
  @IsString() @Transform(trim) @IsNotEmpty({ message: '"fullName" (nome) é obrigatório' }) @MaxLength(LIMITES.texto) fullName: string;
  @IsString() @Transform(trim) @IsEmail({}, { message: '"email" inválido' }) @MaxLength(LIMITES.texto) email: string;
  @IsString() @Transform(trim) @IsNotEmpty({ message: '"mobile" (telefone) é obrigatório' }) @MaxLength(LIMITES.texto) mobile: string;
  @IsString() @Transform(trim) @IsNotEmpty({ message: '"company" (empresa) é obrigatória' }) @MaxLength(LIMITES.texto) company: string;
  @IsString() @Transform(trim) @IsNotEmpty({ message: '"position" (cargo) é obrigatório' }) @MaxLength(LIMITES.texto) position: string;
}
