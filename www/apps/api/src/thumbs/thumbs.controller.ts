import { Controller, Get, Inject, NotFoundException, Param, Res } from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import { Response } from 'express';
import * as crypto from 'node:crypto';
import { BimProduct, BimProductDocument } from '../bim-products/bim-products.schema';
import { IGeometryStore } from '../geometry-store/geometry-store.interface';

@Controller('thumbs')
export class ThumbsController {
  constructor(
    @InjectModel(BimProduct.name) private readonly productModel: Model<BimProductDocument>,
    @Inject('GEOMETRY_STORE') private readonly store: IGeometryStore,
  ) {}

  @Get(':productId')
  async getThumb(@Param('productId') productId: string, @Res() res: Response) {
    const product = await this.productModel.findById(productId).lean().exec();
    if (!product) throw new NotFoundException('produto não encontrado');
    if (!product.thumbKey) throw new NotFoundException('miniatura não disponível');

    let blob: Buffer;
    try {
      blob = await this.store.get(product.thumbKey);
    } catch (err: any) {
      if (err.code === 'ENOENT') throw new NotFoundException('miniatura não encontrada');
      throw err;
    }

    const etag = `"${crypto.createHash('sha1').update(product.thumbKey).digest('hex').slice(0, 16)}"`;
    res.setHeader('Content-Type', 'image/webp');
    res.setHeader('ETag', etag);
    res.setHeader('Cache-Control', 'public, max-age=31536000, immutable');
    res.send(blob);
  }
}
