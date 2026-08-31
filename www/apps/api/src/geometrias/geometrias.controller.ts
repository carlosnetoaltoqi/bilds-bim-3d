import { Controller, Get, Inject, NotFoundException, Param, Req, Res } from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import { Request, Response } from 'express';
import { BimProduct, BimProductDocument } from '../bim-products/bim-products.schema';
import { AssetStat, IGeometryStore } from '../geometry-store/geometry-store.interface';
import { ASSET_CACHE_CONTROL, assetEtag, ifNoneMatchSatisfied } from '../common/asset-cache';

@Controller('geometrias')
export class GeometriasController {
  constructor(
    @InjectModel(BimProduct.name) private readonly productModel: Model<BimProductDocument>,
    @Inject('GEOMETRY_STORE') private readonly store: IGeometryStore,
  ) {}

  @Get(':productId')
  async getGeometry(
    @Param('productId') productId: string,
    @Req() req: Request,
    @Res() res: Response,
  ) {
    const product = await this.productModel.findById(productId).lean().exec();
    if (!product) throw new NotFoundException('produto não encontrado');

    let stat: AssetStat;
    try {
      stat = await this.store.stat(product.geoKey);
    } catch (err: any) {
      if (err.code === 'ENOENT') throw new NotFoundException('geometria não encontrada');
      throw err;
    }

    const etag = assetEtag(product.geoKey, stat);
    res.setHeader('ETag', etag);
    res.setHeader('Cache-Control', ASSET_CACHE_CONTROL);

    // 304 antes de ler o arquivo — evita puxar vários MB do disco a cada navegação.
    if (ifNoneMatchSatisfied(req.headers['if-none-match'], etag)) {
      res.status(304).end();
      return;
    }

    let blob: Buffer;
    try {
      blob = await this.store.get(product.geoKey);
    } catch (err: any) {
      if (err.code === 'ENOENT') throw new NotFoundException('geometria não encontrada');
      throw err;
    }

    res.setHeader('Content-Type', 'application/json');
    res.send(blob);
  }
}
