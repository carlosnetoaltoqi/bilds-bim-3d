/**
 * Harness do I16: passa corpos pelo MESMO `ValidationPipe` que o `main.ts` instala
 * (`criarValidationPipe()` de `common/validation.ts`), contra cada DTO, e imprime JSON {cenario: {ok: valorTransformado} | {erros}}.
 * Sem Nest de pé, sem Mongo.
 *
 *   cd www/apps/api && node --require ts-node/register/transpile-only --require reflect-metadata \
 *       ../../../tests/paridade/validacao.cts
 *
 * `.cts` porque a raiz tem "type":"module" (ver geometrias_thumb.cts).
 */
import { criarValidationPipe, normalizarCurva, normalizarSpecs } from '../../www/apps/api/src/common/validation';
import { PatchProdutoDto } from '../../www/apps/api/src/produtos/patch-produto.dto';
import { PatchCatalogoDto } from '../../www/apps/api/src/catalogos/patch-catalogo.dto';
import { ExportarAqDto, ImportarCadDto } from '../../www/apps/api/src/step/cad.dto';
import { CriarEmpresaDto } from '../../www/apps/api/src/empresas/criar-empresa.dto';
import { ImportarAqDto } from '../../www/apps/api/src/importacoes/importar-aq.dto';

const pipe = criarValidationPipe();

async function valida(metatype: any, body: unknown) {
  try {
    const ok = await pipe.transform(body, { type: 'body', metatype, data: undefined });
    return { ok };
  } catch (e: any) {
    const r = e.getResponse?.() ?? {};
    const erros = Array.isArray(r.message) ? r.message : [r.message ?? e.message];
    return { erros, status: e.getStatus?.() };
  }
}

async function main() {
  const s: Record<string, unknown> = {};
  const muitasSpecs = Object.fromEntries(Array.from({ length: 201 }, (_, i) => [`k${i}`, 'v']));

  // ── PATCH /produtos/:id ──────────────────────────────────────────────────────
  {
    const r = await valida(PatchProdutoDto, {
      nome: '  Bomba 20cv  ', serie: ' Linha A ', specs: { Tensão: '220V', Peso: 12.5, Trifásica: true, Nada: null },
      curva: [[2, 10], [1, 20, 5]], potencia: 3, conexoes: null,
    });
    s.produto_ok = r.ok
      ? { ...r.ok, specs: normalizarSpecs((r.ok as any).specs), curva: normalizarCurva((r.ok as any).curva) }
      : r;
  }
  s.produto_specs_objeto = await valida(PatchProdutoDto, { specs: { Dimensões: { a: 1 } } });
  s.produto_specs_array = await valida(PatchProdutoDto, { specs: { Lista: [1, 2] } });
  s.produto_specs_muitas = await valida(PatchProdutoDto, { specs: muitasSpecs });
  s.produto_nome_vazio = await valida(PatchProdutoDto, { nome: '   ' });
  s.produto_nome_longo = await valida(PatchProdutoDto, { nome: 'x'.repeat(201) });
  s.produto_curva_grande = await valida(PatchProdutoDto, { curva: Array.from({ length: 1001 }, (_, i) => [i, 1]) });
  s.produto_curva_ponto_ruim = await valida(PatchProdutoDto, { curva: [[1, 2], [3]] });
  s.produto_curva_nan = await valida(PatchProdutoDto, { curva: [[1, 'x']] });
  s.produto_curva_null = await valida(PatchProdutoDto, { curva: null });
  s.produto_potencia_texto = await valida(PatchProdutoDto, { potencia: '5' });
  s.produto_potencia_null = await valida(PatchProdutoDto, { potencia: null });
  s.produto_campo_desconhecido = await valida(PatchProdutoDto, { nome: 'ok', geoKey: 'geo/hack.json' });
  s.produto_vazio = await valida(PatchProdutoDto, {});

  // ── PATCH /catalogos/:id ─────────────────────────────────────────────────────
  s.catalogo_ok = await valida(PatchCatalogoDto, { title: ' Bombas ', manufacturer: 'Dancor', layout: 'series-rows' });
  s.catalogo_layout_invalido = await valida(PatchCatalogoDto, { layout: 'grid' });
  s.catalogo_title_vazio = await valida(PatchCatalogoDto, { title: '' });

  // ── POST /exportar/aq ────────────────────────────────────────────────────────
  const parte = { nome: 'corpo', pos: [0, 0, 0, 1, 0, 0, 0, 1, 0], col: null, idx: [0, 1, 2] };
  s.exportar_ok = await valida(ExportarAqDto, {
    info: { fabricante: 'Dancor', nome: ' 20cv ', specs: { Peso: 12 }, origem: 'poc' },
    partes: [parte, { ...parte, nome: 'bocal', col: [1, 0, 0, 1, 0, 0, 1, 0, 0] }],
  });
  s.exportar_partes_excesso = await valida(ExportarAqDto, { partes: Array.from({ length: 501 }, () => parte) });
  s.exportar_parte_sem_nome = await valida(ExportarAqDto, { partes: [{ ...parte, nome: '' }] });
  s.exportar_parte_pos_nao_array = await valida(ExportarAqDto, { partes: [{ ...parte, pos: 'abc' }] });
  s.exportar_parte_campo_extra = await valida(ExportarAqDto, { partes: [{ ...parte, matriz: [1] }] });
  s.exportar_info_specs_objeto = await valida(ExportarAqDto, { info: { specs: { a: { b: 1 } } }, partes: [parte] });
  s.exportar_so_geo = await valida(ExportarAqDto, { pos: parte.pos, col: [], idx: parte.idx });

  // ── POST /cad/importar (multipart → tudo texto) ──────────────────────────────
  s.cad_ok = await valida(ImportarCadDto, { deflexao: '0.5', nome: ' peça ', fabricante: 'X' });
  s.cad_sem_deflexao = await valida(ImportarCadDto, { nome: 'p' });
  s.cad_deflexao_zero = await valida(ImportarCadDto, { deflexao: '0' });
  s.cad_deflexao_grande = await valida(ImportarCadDto, { deflexao: '11' });
  s.cad_deflexao_texto = await valida(ImportarCadDto, { deflexao: 'abc' });

  // ── POST /empresas e POST /importacoes (sem auth desde S7.14) ────────────────
  s.empresa_ok = await valida(CriarEmpresaDto, { name: ' POC ', customUrl: ' Minha Empresa ' });
  s.empresa_sem_nome = await valida(CriarEmpresaDto, { name: '', customUrl: 'x' });
  s.empresa_sem_url = await valida(CriarEmpresaDto, { name: 'x' });
  s.importar_aq_ok = await valida(ImportarAqDto, { empresa: ' poc ' });
  s.importar_aq_vazio = await valida(ImportarAqDto, {});
  s.importar_aq_campo_estranho = await valida(ImportarAqDto, { ownerId: 'x' });

  process.stdout.write(JSON.stringify(s));
}

main().catch((e) => { console.error(e); process.exit(1); });
