import { IsNotEmpty, IsString, MaxLength } from 'class-validator';
import { LIMITES } from '../common/validation';

/** Corpo do `POST /auth/login`. A comparação é com `SEED_USER`/`SEED_PASSWORD` (ADR 7.6). */
export class LoginDto {
  @IsString({ message: '"email" deve ser texto' })
  @IsNotEmpty({ message: 'campo "email" obrigatório' })
  @MaxLength(LIMITES.texto)
  email: string;

  @IsString({ message: '"password" deve ser texto' })
  @IsNotEmpty({ message: 'campo "password" obrigatório' })
  @MaxLength(LIMITES.texto)
  password: string;
}
