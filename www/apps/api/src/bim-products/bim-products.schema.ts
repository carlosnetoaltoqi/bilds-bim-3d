import { Prop, Schema, SchemaFactory } from '@nestjs/mongoose';
import { HydratedDocument, Schema as MongooseSchema } from 'mongoose';

export type BimProductDocument = HydratedDocument<BimProduct>;

@Schema({ collection: 'bim_products' })
export class BimProduct {
  @Prop({ type: String, default: () => crypto.randomUUID() })
  _id: string;

  @Prop({ required: true })
  catalogId: string;

  @Prop({ required: true })
  importId: string;

  /** Slug do produto dentro do .aq */
  @Prop({ required: true })
  id: string;

  @Prop({ required: true })
  nome: string;

  @Prop()
  serie: string;

  /** Especificações técnicas: { "Tensão": "220V", "Rotação": "3500 rpm" } */
  @Prop({ type: MongooseSchema.Types.Mixed })
  specs: Record<string, string>;

  /** Pontos da curva Q-H: [[vazao, altura, potencia, rendimento]] */
  @Prop({ type: [[Number]], default: null })
  curva: number[][] | null;

  @Prop()
  conexoes: string;

  @Prop()
  potencia: number;

  /** Chave para o GeometryStore (ADR-001) */
  @Prop({ required: true })
  geoKey: string;

  /** Chave da miniatura no GeometryStore */
  @Prop()
  thumbKey: string;

  @Prop({ default: Date.now })
  createdAt: Date;
}

export const BimProductSchema = SchemaFactory.createForClass(BimProduct);
BimProductSchema.index({ catalogId: 1 });
BimProductSchema.index({ catalogId: 1, serie: 1 });
BimProductSchema.index({ importId: 1 });
