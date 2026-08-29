import { Prop, Schema, SchemaFactory } from '@nestjs/mongoose';
import { HydratedDocument } from 'mongoose';

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

  /** Mensagem de erro quando status === 'falhou' */
  @Prop()
  error: string;

  @Prop()
  productCount: number;

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
