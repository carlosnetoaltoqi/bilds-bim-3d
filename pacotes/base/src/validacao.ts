/**
 * validacao.ts — o `ValidationPipe` global de todo serviço e os limites de tamanho dos corpos (I16).
 *
 * Cada corpo JSON tem um DTO (`*.dto.ts`); campos fora do DTO são rejeitados
 * (`forbidNonWhitelisted`), não silenciosamente descartados. O que continua fora do pipe, de
 * propósito: arrays `pos/col/idx` com milhões de números — `validateGeoBuffers` (dominio) faz isso
 * num loop simples. Corpos tipados como `unknown`/`Record` não têm metatype e o Nest pula a validação.
 *
 * Os limites são de POC: generosos para bibliotecas grandes, apertados o bastante para um corpo
 * malicioso ou um bug do editor não virar documento de MB no banco.
 */
import { ValidationPipe, ValidationPipeOptions } from '@nestjs/common';

export const LIMITES = {
  texto: 200,          // nome, serie, title, manufacturer, fabricante, linha, codigo…
  textoLongo: 2000,    // conexoes, descricao, origem, valor de spec
  specsChaves: 200,
  specChave: 100,
  curvaPontos: 1000,
  partes: 500,
  customUrl: 60,
} as const;

/** Opções do `ValidationPipe` global — também usadas pelo harness dos testes. */
export const opcoesValidacao: ValidationPipeOptions = {
  whitelist: true,
  forbidNonWhitelisted: true,
  transform: true,
  // com `transform` os objetos aninhados já viram instâncias; `true` rejeitaria objetos livres como `specs`
  forbidUnknownValues: false,
  stopAtFirstError: false,
};

/** O pipe que todo `main.ts` instala — o harness `tests/paridade/validacao.cts` usa o mesmo. */
export const criarValidationPipe = () => new ValidationPipe(opcoesValidacao);
