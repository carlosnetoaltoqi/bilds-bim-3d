import { Controller, Get, Inject, NotFoundException, Param, Req, Res } from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import { Request, Response } from 'express';
import { BimProduct, BimProductDocument } from '../bim-products/bim-products.schema';
import { AssetStat, IGeometryStore } from '../geometry-store/geometry-store.interface';
import { ASSET_CACHE_CONTROL, assetEtag, ifNoneMatchSatisfied } from '../common/asset-cache';

@Controller('thumbs')
export class ThumbsController {
  constructor(
    @InjectModel(BimProduct.name) private readonly productModel: Model<BimProductDocument>,
    @Inject('GEOMETRY_STORE') private readonly store: IGeometryStore,
  ) {}

  @Get(':productId')
  async getThumb(
    @Param('productId') productId: string,
    @Req() req: Request,
    @Res() res: Response,
  ) {
    const product = await this.productModel.findById(productId).lean().exec();
    if (!product) throw new NotFoundException('produto não encontrado');
    if (!product.thumbKey) throw new NotFoundException('miniatura não disponível');

    let stat: AssetStat;
    try {
      stat = await this.store.stat(product.thumbKey);
    } catch (err: any) {
      if (err.code === 'ENOENT') throw new NotFoundException('miniatura não encontrada');
      throw err;
    }

    const etag = assetEtag(product.thumbKey, stat);
    res.setHeader('ETag', etag);
    res.setHeader('Cache-Control', ASSET_CACHE_CONTROL);

    // 304 antes de ler o arquivo — o caminho comum custa só o stat acima.
    if (ifNoneMatchSatisfied(req.headers['if-none-match'], etag)) {
      res.status(304).end();
      return;
    }

    let blob: Buffer;
    try {
      blob = await this.store.get(product.thumbKey);
    } catch (err: any) {
      if (err.code === 'ENOENT') throw new NotFoundException('miniatura não encontrada');
      throw err;
    }

    res.setHeader('Content-Type', 'image/webp');
    res.send(blob);
  }
}
