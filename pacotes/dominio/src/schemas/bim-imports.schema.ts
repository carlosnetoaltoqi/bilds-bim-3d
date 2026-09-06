import { Prop, Schema, SchemaFactory } from '@nestjs/mongoose';
import { HydratedDocument, Schema as MongooseSchema } from 'mongoose';

export type BimImportDocument = HydratedDocument<BimImport>;

const IMPORT_STATUSES = [
  'recebido',
  'parseando',
  'gravando',
  'publicado',
  'vazio',
  'falhou',
] as const;

export type ImportStatus = (typeof IMPORT_STATUSES)[number];

/** 'aq' biblioteca .aq/.zip · 'cad' uma peça STEP/IGES/IFC · 'plugin' catálogo web de um plugin de CAD */
const IMPORT_TIPOS = ['aq', 'cad', 'plugin', 'revit'] as const;
export type ImportTipo = (typeof IMPORT_TIPOS)[number];

@Schema({ collection: 'bim_imports' })
export class BimImport {
  @Prop({ type: String, default: () => crypto.randomUUID() })
  _id: string;

  @Prop({ required: true })
  companyId: string;

  @Prop()
  catalogId: string;

  @Prop({ type: String, enum: IMPORT_STATUSES, required: true })
  status: ImportStatus;

  /** 'aq' (biblioteca .aq/.zip), 'cad' (uma peça STEP/IFC) ou 'plugin' (catálogo web de um plugin de AutoCAD) — todos pelo serviço de ingestão (E3) */
  @Prop({ type: String, enum: IMPORT_TIPOS, default: 'aq' })
  tipo: ImportTipo;

  /** Diagnóstico do pipeline (catalogo.py): peças sem 3D, simbologias descartadas e avisos de parse */
  @Prop({ type: MongooseSchema.Types.Mixed })
  diag: Record<string, unknown> | null;

  /** Mensagem de erro quando status === 'falhou' */
  @Prop()
  error: string;

  /** Nota informativa (ex: substituição de catálogo existente) */
  @Prop()
  note: string;

  @Prop()
  productCount: number;

  /** Miniaturas geradas pelo thumbs.mjs (I15) — preenchido ao fim do lote */
  @Prop()
  thumbCount: number;

  /** Produtos cuja miniatura falhou; cada um está no log (`miniatura falhou — <productId>`) */
  @Prop()
  thumbFailed: number;

  /** Mensagem quando o thumbs.mjs morreu antes de terminar (exit, ocioso, erro de processo) */
  @Prop()
  thumbError: string;

  @Prop({ required: true })
  fileName: string;

  @Prop({ default: Date.now })
  createdAt: Date;

  /** Atualizado manualmente a cada transição de estado */
  @Prop({ type: Date })
  updatedAt: Date;
}

export const BimImportSchema = SchemaFactory.createForClass(BimImport);
BimImportSchema.index({ companyId: 1, status: 1 });
