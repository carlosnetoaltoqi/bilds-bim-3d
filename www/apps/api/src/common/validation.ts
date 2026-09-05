/**
 * validation.ts — validação de entrada da API (I16, 2026-09-05).
 *
 * Até então não havia `ValidationPipe`: cada controller checava o corpo à mão, sem
 * limite de tamanho em `curva`/`partes`, e `produtos.controller.ts` transformava um
 * objeto em `"[object Object]"` dentro de `specs`. Agora o `main.ts` instala o pipe
 * global com estas opções e cada corpo JSON tem um DTO (`*.dto.ts`) — campos fora do
 * DTO são rejeitados (`forbidNonWhitelisted`), não silenciosamente descartados.
 *
 * O que continua fora do pipe, de propósito: `PUT /geometrias/:id` e os arrays
 * `pos/col/idx` (milhões de números — `validateGeoBuffers` em `geo-buffers.ts` faz isso
 * num loop simples; o class-validator por elemento seria lento demais). Corpos tipados
 * como `unknown`/`Record` não têm metatype de classe e o Nest pula a validação.
 *
 * Os limites abaixo são de POC: generosos para a Dancor/Maxbar, apertados o bastante
 * para um corpo malicioso ou um bug do editor não virar documento de MB no Mongo.
 */
import { ValidationPipe, ValidationPipeOptions } from '@nestjs/common';
import { registerDecorator, ValidationArguments, ValidationOptions } from 'class-validator';

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

/** O pipe que o `main.ts` instala — o harness `tests/paridade/validacao.cts` usa o mesmo. */
export const criarValidationPipe = () => new ValidationPipe(opcoesValidacao);

/**
 * `specs` é `{ chave: valor }` com valor texto (ou número/booleano, que viram texto no
 * controller). Objetos e arrays como valor são rejeitados — era o `"[object Object]"`.
 */
export function IsSpecs(options?: ValidationOptions) {
  return function (object: object, propertyName: string) {
    registerDecorator({
      name: 'isSpecs',
      target: object.constructor,
      propertyName,
      options,
      validator: {
        validate(value: unknown, _args: ValidationArguments) {
          return motivoSpecsInvalidas(value) === null;
        },
        defaultMessage(args: ValidationArguments) {
          return `"${args.property}" ${motivoSpecsInvalidas(args.value) ?? 'inválido'}`;
        },
      },
    });
  };
}

export function motivoSpecsInvalidas(value: unknown): string | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return 'deve ser um objeto { chave: valor }';
  const entradas = Object.entries(value as Record<string, unknown>);
  if (entradas.length > LIMITES.specsChaves) return `tem ${entradas.length} chaves; o limite é ${LIMITES.specsChaves}`;
  for (const [k, v] of entradas) {
    if (k.length > LIMITES.specChave) return `tem chave com ${k.length} caracteres; o limite é ${LIMITES.specChave}`;
    if (v === null || v === undefined) continue;
    const tipo = typeof v;
    if (tipo !== 'string' && tipo !== 'number' && tipo !== 'boolean') return `["${k}"] deve ser texto, número ou booleano — recebeu ${Array.isArray(v) ? 'array' : tipo}`;
    if (tipo === 'string' && (v as string).length > LIMITES.textoLongo) return `["${k}"] tem ${(v as string).length} caracteres; o limite é ${LIMITES.textoLongo}`;
    if (tipo === 'number' && !Number.isFinite(v)) return `["${k}"] não é um número finito`;
  }
  return null;
}

/** Normaliza `specs` já validadas: chaves sem espaços nas pontas, valores em texto, nulos fora. */
export function normalizarSpecs(value: Record<string, unknown>): Record<string, string> {
  const specs: Record<string, string> = {};
  for (const [k, v] of Object.entries(value)) {
    const chave = k.trim();
    if (!chave || v === null || v === undefined) continue;
    specs[chave] = typeof v === 'string' ? v : String(v);
  }
  return specs;
}

/** Curva Q-H: até `curvaPontos` pontos `[vazao, altura, potencia?, rendimento?]` de números finitos. */
export function IsCurva(options?: ValidationOptions) {
  return function (object: object, propertyName: string) {
    registerDecorator({
      name: 'isCurva',
      target: object.constructor,
      propertyName,
      options,
      validator: {
        validate(value: unknown) {
          return motivoCurvaInvalida(value) === null;
        },
        defaultMessage(args: ValidationArguments) {
          return `"${args.property}" ${motivoCurvaInvalida(args.value) ?? 'inválida'}`;
        },
      },
    });
  };
}

export function motivoCurvaInvalida(value: unknown): string | null {
  if (!Array.isArray(value)) return 'deve ser array de pontos ou null';
  if (value.length > LIMITES.curvaPontos) return `tem ${value.length} pontos; o limite é ${LIMITES.curvaPontos}`;
  for (const [i, ponto] of value.entries()) {
    if (!Array.isArray(ponto) || ponto.length < 2 || ponto.length > 4 || ponto.some((n) => typeof n !== 'number' || !Number.isFinite(n))) {
      return `[${i}] deve ser [vazao, altura, potencia?, rendimento?] numéricos`;
    }
  }
  return null;
}

/** Ordena por vazão e completa potência/rendimento com 0 — o gráfico assume isso. */
export function normalizarCurva(curva: number[][]): number[][] | null {
  if (!curva.length) return null;
  return curva.map((pt) => [pt[0], pt[1], pt[2] ?? 0, pt[3] ?? 0]).sort((a, b) => a[0] - b[0]);
}
