import { Prop, Schema, SchemaFactory } from '@nestjs/mongoose';
import { HydratedDocument } from 'mongoose';

export type CompanyDocument = HydratedDocument<Company>;

@Schema({ collection: 'companies' })
export class Company {
  @Prop({ type: String, default: () => crypto.randomUUID() })
  _id: string;

  @Prop({ required: true })
  name: string;

  @Prop({ required: true, unique: true })
  customUrl: string;

  /** Resquício da POC com login; sem auth ninguém é dono. Fica opcional para ler documentos antigos. */
  @Prop()
  ownerId?: string;

  @Prop()
  logoKey?: string;

  @Prop({ default: Date.now })
  createdAt: Date;
}

export const CompanySchema = SchemaFactory.createForClass(Company);
