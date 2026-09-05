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

  // ── POC de edição (branch poc-edicao) ─────────────────────────────────────
  /** Última edição das informações (PATCH /produtos/:id) */
  @Prop({ type: Date })
  editadoEm: Date | null;

  /** Última escrita da geometria (PUT /geometrias/:id) */
  @Prop({ type: Date })
  geoEditadoEm: Date | null;

  /** Miniatura regerada depois de editar/restaurar a geometria (I14) — null = ainda a do import */
  @Prop({ type: Date })
  thumbAtualizadaEm: Date | null;

  /** Por que a última regeneração da miniatura falhou; null quando deu certo */
  @Prop({ type: String })
  thumbErro: string | null;

  /** Snapshot dos campos editáveis como vieram do .aq, gravado na 1ª edição */
  @Prop({ type: MongooseSchema.Types.Mixed })
  infoOriginal: Record<string, unknown> | null;
}

export const BimProductSchema = SchemaFactory.createForClass(BimProduct);
BimProductSchema.index({ catalogId: 1 });
BimProductSchema.index({ catalogId: 1, serie: 1 });
BimProductSchema.index({ importId: 1 });
