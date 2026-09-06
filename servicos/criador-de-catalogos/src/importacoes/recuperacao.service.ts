/**
 * recuperacao.service.ts — o que fazer no boot com o que a queda do serviço deixou (I11).
 *
 * A importação roda em memória (fila + promise); se o processo morre, o `BimImport` fica
 * em `recebido`/`parseando`/`gravando` para sempre, a página em "Convertendo…", os JSONs
 * de `geo/<importId>/` e os produtos meio-gravados ficam, e o multer não apaga o upload
 * em `os.tmpdir()`. A POC é UM processo: no boot, nada pode estar legitimamente em
 * andamento, então todo import não terminal é órfão — vira `falhou` com uma mensagem que
 * diz para enviar de novo, e a limpeza é a mesma de uma falha normal.
 *
 * Se um dia houver mais de uma instância na mesma base, isto precisa de lease/heartbeat
 * (`updatedAt` recente = viva). Por isso `recuperarImportsOrfaos` recebe `minIdadeMs`:
 * o boot usa 0; um sweep periódico usaria algo maior que a fase silenciosa mais longa
 * (o Python tem 30 min de timeout).
 */
import { Inject, Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { BimImport, BimImportDocument, BimProduct, BimProductDocument, IGeometryStore } from '@bim/dominio';

export const STATUS_NAO_TERMINAIS = ['recebido', 'parseando', 'gravando'] as const;
export const ERRO_REINICIO = 'a API foi reiniciada durante a importação — envie o arquivo de novo';

/** Uploads que o multer deixa em `os.tmpdir()`: `bim-<uuid>.aq|.zip` (biblioteca), `cad-<uuid>.<ext>` (peça), `plugin-<uuid>.dll` (plugin de AutoCAD) e `revit-<uuid>.rfa|.zip` (famílias Revit). */
export const UPLOAD_TEMPORARIO = /^(bim-[0-9a-f-]{36}\.(aq|zip)|cad-[0-9a-f-]{36}\.(stp|step|igs|iges|ifc|ifczip|ifcxml)|plugin-[0-9a-f-]{36}\.dll|revit-[0-9a-f-]{36}\.(rfa|rvt|zip))$/i;

export interface LogMinimo {
  log(msg: string): void;
  warn(msg: string): void;
  error(msg: string): void;
}

export interface ResultadoRecuperacao {
  marcados: string[];
  uploadsRemovidos: string[];
}

/** Só o que precisamos dos modelos e do store — para o harness passar falsos. */
type ImportModelMinimo = { find(filtro: unknown): { lean(): { exec(): Promise<Array<{ _id: string; status: string; updatedAt?: Date; createdAt?: Date }>> } };
                           findByIdAndUpdate(id: string, upd: unknown): { exec(): Promise<unknown> } };
type ProductModelMinimo = { deleteMany(filtro: unknown): Promise<unknown> | { exec(): Promise<unknown> } };
type StoreMinimo = Pick<IGeometryStore, 'deleteByPrefix'>;

export async function recuperarImportsOrfaos(
  importModel: ImportModelMinimo,
  productModel: ProductModelMinimo,
  store: StoreMinimo,
  logger: LogMinimo,
  minIdadeMs = 0,
  agora = Date.now(),
): Promise<string[]> {
  const abertos = await importModel.find({ status: { $in: [...STATUS_NAO_TERMINAIS] } }).lean().exec();
  const marcados: string[] = [];
  for (const imp of abertos) {
    const referencia = (imp.updatedAt ?? imp.createdAt)?.getTime?.() ?? 0;
    if (agora - referencia < minIdadeMs) continue;
    const tag = `[${String(imp._id).slice(0, 8)}]`;
    logger.warn(`${tag} import órfão em '${imp.status}' — marcando como falhou (${ERRO_REINICIO})`);
    await Promise.resolve(productModel.deleteMany({ importId: imp._id }))
      .then((r: any) => (typeof r?.exec === 'function' ? r.exec() : r))
      .catch((e: any) => logger.warn(`${tag} limpeza de produtos falhou — ${e?.message ?? e}`));
    await store.deleteByPrefix(`geo/${imp._id}`)
      .catch((e: any) => logger.warn(`${tag} limpeza de geo/${imp._id} falhou — ${e?.message ?? e}`));
    await importModel.findByIdAndUpdate(imp._id, {
      status: 'falhou',
      error: ERRO_REINICIO,
      note: `estava em '${imp.status}' quando a API reiniciou`,
      updatedAt: new Date(agora),
    }).exec();
    marcados.push(String(imp._id));
  }
  return marcados;
}

export async function limparUploadsTemporarios(dir: string, logger: LogMinimo): Promise<string[]> {
  let nomes: string[];
  try {
    nomes = await fs.readdir(dir);
  } catch (e: any) {
    logger.warn(`não listou ${dir} — ${e?.message ?? e}`);
    return [];
  }
  const removidos: string[] = [];
  for (const nome of nomes) {
    if (!UPLOAD_TEMPORARIO.test(nome)) continue;
    try {
      await fs.unlink(path.join(dir, nome));
      removidos.push(nome);
    } catch (e: any) {
      logger.warn(`não removeu ${nome} — ${e?.message ?? e}`);
    }
  }
  if (removidos.length) logger.log(`${removidos.length} upload(s) temporário(s) de importações mortas removido(s) de ${dir}`);
  return removidos;
}

@Injectable()
export class RecuperacaoService implements OnModuleInit {
  private readonly logger = new Logger(RecuperacaoService.name);

  constructor(
    @InjectModel(BimImport.name) private readonly importModel: Model<BimImportDocument>,
    @InjectModel(BimProduct.name) private readonly productModel: Model<BimProductDocument>,
    @Inject('GEOMETRY_STORE') private readonly store: IGeometryStore,
  ) {}

  async onModuleInit(): Promise<ResultadoRecuperacao> {
    const marcados = await recuperarImportsOrfaos(this.importModel as any, this.productModel as any, this.store, this.logger)
      .catch((e: any) => { this.logger.error(`recuperação de imports órfãos falhou — ${e?.message ?? e}`); return [] as string[]; });
    const uploadsRemovidos = await limparUploadsTemporarios(os.tmpdir(), this.logger);
    this.logger.log(`boot: ${marcados.length} import(s) órfão(s) marcado(s) como falhou, ${uploadsRemovidos.length} upload(s) temporário(s) removido(s)`);
    return { marcados, uploadsRemovidos };
  }
}
