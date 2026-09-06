/**
 * contratos.ts — validação do que chega da biblioteca contra os JSON Schema que ELA define
 * (`biblioteca/bim_pipeline/contratos/*.schema.json`, ADR-015). A biblioteca prova em teste que
 * emite conforme; aqui provamos que o que lemos é o que esperamos — um contrato quebrado vira
 * `ContratoInvalido` com o caminho do campo, não um `undefined` três camadas depois.
 */
import Ajv2020, { ValidateFunction } from 'ajv/dist/2020';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { bibliotecaDir } from './biblioteca-cli';

export type NomeContrato = 'catalogo' | 'geometria' | 'manifesto-catalogo-aq' | 'resumo-miniaturas' | 'info-plugin' | 'info-familias-revit';

export class ContratoInvalido extends Error {
  constructor(readonly contrato: NomeContrato, readonly detalhes: string) {
    super(`contrato "${contrato}" violado: ${detalhes}`);
    this.name = 'ContratoInvalido';
  }
}

// os schemas são draft 2020-12 — o `Ajv` padrão só conhece o draft-07 e recusa o `$schema` deles
const ajv = new Ajv2020({ allErrors: false, strict: false });
const cache = new Map<string, ValidateFunction>();

export function contratosDir(dir = bibliotecaDir()): string {
  return path.join(dir, 'bim_pipeline', 'contratos');
}

function validador(nome: NomeContrato): ValidateFunction {
  let v = cache.get(nome);
  if (!v) {
    const schema = JSON.parse(fs.readFileSync(path.join(contratosDir(), `${nome}.schema.json`), 'utf8'));
    v = ajv.compile(schema);
    cache.set(nome, v);
  }
  return v;
}

/** Devolve `obj` tipado se segue o contrato; lança `ContratoInvalido` se não. */
export function validarContrato<T = unknown>(nome: NomeContrato, obj: unknown): T {
  const v = validador(nome);
  if (!v(obj)) {
    const e = v.errors?.[0];
    throw new ContratoInvalido(nome, e ? `${e.instancePath || '/'} ${e.message ?? ''}`.trim() : 'inválido');
  }
  return obj as T;
}
