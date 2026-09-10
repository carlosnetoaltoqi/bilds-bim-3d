import { Transform, Type } from 'class-transformer';
import { IsIn, IsNumber, IsOptional, IsString, Max, MaxLength, Min } from 'class-validator';
import { LIMITES, SLUGS_DISCIPLINA } from '@bim/base';

const trim = ({ value }: { value: unknown }) => (typeof value === 'string' ? value.trim() : value);

/**
 * Campos de formulário do `POST /importacoes` (multipart — tudo chega como texto; `deflexao`
 * vira número). O arquivo é o `@UploadedFile()`; o tipo (biblioteca `.aq`/`.zip` ou peça
 * STEP/IFC) sai da extensão. Os campos além de `empresa` só valem para peça CAD.
 */
export class ImportarDto {
  /** customUrl da empresa dona do catálogo; vazio = a primeira cadastrada */
  @IsOptional() @IsString() @Transform(trim) @MaxLength(LIMITES.customUrl) empresa?: string;

  /**
   * Disciplina do Builder — **obrigatória** (ADR-024). É ela que decide em que projeto a peça
   * aparece no lançamento; o campo chega da tela pré-preenchido com o palpite da fonte, e quem
   * importa confirma ou troca. Sem ela a peça entrava como hidráulica calada.
   */
  @IsString()
  @Transform(trim)
  @IsIn(SLUGS_DISCIPLINA as string[], { message: `"disciplina" deve ser uma de: ${SLUGS_DISCIPLINA.join(', ')}` })
  disciplina!: string;

  /** só CAD: série no catálogo (padrão "STEP"/"IFC") */
  @IsOptional() @IsString() @Transform(trim) @MaxLength(LIMITES.texto) fabricante?: string;
  /** só CAD: título do catálogo (padrão "Peças STEP"/"Peças IFC") */
  @IsOptional() @IsString() @Transform(trim) @MaxLength(LIMITES.texto) catalogo?: string;
  /** só CAD: nome da peça (padrão: nome do arquivo) */
  @IsOptional() @IsString() @Transform(trim) @MaxLength(LIMITES.texto) nome?: string;

  /** só STEP: deflexão da tesselação em mm (0 < x ≤ 10; padrão 0,2) */
  @IsOptional()
  @Type(() => Number)
  @IsNumber({ allowNaN: false, allowInfinity: false }, { message: '"deflexao" deve ser um número em mm' })
  @Min(0.0001, { message: '"deflexao" deve ser maior que 0' })
  @Max(10, { message: '"deflexao" deve ser no máximo 10 mm' })
  deflexao?: number;
}
