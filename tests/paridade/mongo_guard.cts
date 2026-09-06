/**
 * Harness do I32: `MongoProntoGuard` (@bim/dominio) recusa com 503 imediato enquanto a conexão do
 * Mongoose não está pronta, exceto /health. Sem Nest de pé: instancia o guard com uma conexão
 * falsa e um ExecutionContext mínimo. Imprime JSON para tests/test_www_mongo_guard.py.
 *
 *   cd servicos/catalogo-api && node --require ts-node/register/transpile-only --require reflect-metadata \
 *       ../../../tests/paridade/mongo_guard.cts
 */
import { MongoProntoGuard, motivoMongoIndisponivel, ROTAS_SEM_MONGO } from '../../pacotes/dominio/src/mongo-pronto.guard';

function ctx(path: string) {
  return { switchToHttp: () => ({ getRequest: () => ({ path, url: path }) }) } as any;
}

function tenta(readyState: number, path: string) {
  const guard = new MongoProntoGuard({ readyState } as any);
  try {
    return { ok: guard.canActivate(ctx(path)) };
  } catch (e: any) {
    return { status: e.getStatus?.(), message: e.getResponse?.()?.message ?? e.message };
  }
}

const saida = {
  rotasSemMongo: ROTAS_SEM_MONGO,
  conectado_catalogos: tenta(1, '/catalogos/x/y'),
  desconectado_catalogos: tenta(0, '/catalogos/x/y'),
  conectando_importacoes: tenta(2, '/importacoes'),
  desconectando_put: tenta(3, '/geometrias/p1'),
  desconectado_health: tenta(0, '/health'),
  desconectado_health_query: tenta(0, '/health?x=1'),
  motivo_puro: motivoMongoIndisponivel(0, '/produtos/abc'),
  motivo_puro_ok: motivoMongoIndisponivel(1, '/produtos/abc'),
};
process.stdout.write(JSON.stringify(saida));
