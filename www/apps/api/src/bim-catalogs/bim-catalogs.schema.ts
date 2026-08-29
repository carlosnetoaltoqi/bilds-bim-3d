import { Prop, Schema, SchemaFactory } from '@nestjs/mongoose';
import { HydratedDocument } from 'mongoose';

export type BimCatalogDocument = HydratedDocument<BimCatalog>;

@Schema({ collection: 'bim_catalogs' })
export class BimCatalog {
  @Prop({ type: String, default: () => crypto.randomUUID() })
  _id: string;

  @Prop({ required: true })
  companyId: string;

  @Prop({ required: true })
  slug: string;

  @Prop({ required: true })
  title: string;

  @Prop({ required: true })
  manufacturer: string;

  @Prop({ required: true })
  layout: string;

  @Prop({ type: [String], default: [] })
  filters: string[];

  @Prop({ default: 0 })
  productCount: number;

  @Prop({ default: Date.now })
  createdAt: Date;
}

export const BimCatalogSchema = SchemaFactory.createForClass(BimCatalog);
BimCatalogSchema.index({ companyId: 1, slug: 1 }, { unique: true });
